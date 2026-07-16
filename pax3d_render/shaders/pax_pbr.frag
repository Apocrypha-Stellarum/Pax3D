// Pax PBR Fragment Shader
// Forked from simplepbr 0.13.1 (KhronosGroup glTF-Sample-Viewer based)
//
// Key changes from simplepbr:
// 1. Sun directional light uses custom u_sun_dir_world / u_sun_color uniforms
//    in world space, bypassing the Panda3D C++ DirectionalLight bug.
// 2. Sun direction and world normals (from mat3(p3d_ModelMatrix)) are both
//    in the same coordinate space — no CS conversion applied to either.
// Point/spot lights still use p3d_LightSource in view space (correct path).

#version 120

#ifndef MAX_LIGHTS
    #define MAX_LIGHTS 8
#endif

#ifdef USE_330
    #define texture2D texture
    #define textureCube texture
    #define textureCubeLod textureLod
#else
    #extension GL_ARB_shader_texture_lod : require
#endif

uniform struct p3d_MaterialParameters {
    vec4 baseColor;
    vec4 emission;
    float roughness;
    float metallic;
} p3d_Material;

uniform struct p3d_LightSourceParameters {
    vec4 position;
    vec4 diffuse;
    vec4 specular;
    vec3 attenuation;
    vec3 spotDirection;
    float spotCosCutoff;
#ifdef ENABLE_SHADOWS
    sampler2DShadow shadowMap;
    mat4 shadowViewMatrix;
#endif
} p3d_LightSource[MAX_LIGHTS];

uniform struct p3d_LightModelParameters {
    vec4 ambient;
} p3d_LightModel;

#ifdef ENABLE_FOG
uniform struct p3d_FogParameters {
    vec4 color;
    float density;
} p3d_Fog;
#endif

uniform vec4 p3d_ColorScale;
uniform vec4 p3d_TexAlphaOnly;

uniform vec3 sh_coeffs[9];
uniform vec3 camera_world_position;

// Custom sun uniforms (bypass p3d_LightSource for directional light)
uniform vec3 u_sun_dir_world;  // world-space, normalized, toward sun
uniform vec3 u_sun_color;      // linear RGB * intensity

// Debug: 0=normal, 1=world normals as RGB, 2=n_dot_l grayscale, 3=light dir
uniform float u_debug_lighting;

// Individual float components of sun_dir — bypasses Vec3 CS conversion.
uniform float u_sun_dir_x;
uniform float u_sun_dir_y;
uniform float u_sun_dir_z;

// Limb darkening — Eddington coefficient (0=off, 0.6=Sol G-type, 0.8=M-type)
// Set per-node on stellar surfaces; unset nodes default to 0 (no effect).
uniform float u_limb_darkening;

struct FunctionParamters {
    float n_dot_l;
    float n_dot_v;
    float n_dot_h;
    float l_dot_h;
    float v_dot_h;
    float roughness;
    float metallic;
    vec3 reflection0;
    vec3 diffuse_color;
    vec3 specular_color;
};

uniform sampler2D p3d_TextureBaseColor;
uniform sampler2D p3d_TextureMetalRoughness;
uniform sampler2D p3d_TextureNormal;
uniform sampler2D p3d_TextureEmission;

uniform sampler2D brdf_lut;
uniform samplerCube filtered_env_map;
uniform float max_reflection_lod;

#ifdef ENABLE_SHADOWS
uniform float global_shadow_bias;
#endif

const vec3 F0 = vec3(0.04);
const float PI = 3.141592653589793;
const float SPOTSMOOTH = 0.001;
const float LIGHT_CUTOFF = 0.001;

varying vec3 v_view_position;
varying vec3 v_world_position;
varying vec4 v_color;
varying vec2 v_texcoord;
varying mat3 v_view_tbn;
varying mat3 v_world_tbn;
varying vec3 v_world_normal;
#ifdef ENABLE_SHADOWS
varying vec4 v_shadow_pos[MAX_LIGHTS];
#endif
#ifdef LOG_DEPTH
// Logarithmic depth (R4.1): u_log_depth_coef = 1.0 / log2(1.0 + far),
// kept in sync with the camera lens by the pipeline's per-frame update.
uniform float u_log_depth_coef;
varying float v_log_depth_w;
#endif

#ifdef USE_330
out vec4 o_color;
#endif


// Schlick's Fresnel approximation with Spherical Gaussian approximation
vec3 specular_reflection(FunctionParamters func_params) {
    vec3 f0 = func_params.reflection0;
    float v_dot_h= func_params.v_dot_h;
    return f0 + (vec3(1.0) - f0) * pow(2.0, (-5.55473 * v_dot_h - 6.98316) * v_dot_h);
}

vec3 fresnelSchlickRoughness(float u, vec3 f0, float roughness) {
    return f0 + (max(vec3(1.0 - roughness), f0) - f0) * pow(clamp(1.0 - u, 0.0, 1.0), 5.0);
}

// Smith GGX
float visibility_occlusion(FunctionParamters func_params) {
    float r = func_params.roughness;
    float n_dot_l = func_params.n_dot_l;
    float n_dot_v = func_params.n_dot_v;
#ifdef SMITH_SQRT_APPROX
    float ggxv = n_dot_l * (n_dot_v * (1.0 - r) + r);
    float ggxl = n_dot_v * (n_dot_l * (1.0 - r) + r);
#else
    float r2 = r * r;
    float ggxv = n_dot_l * sqrt(n_dot_v * n_dot_v * (1.0 - r2) + r2);
    float ggxl = n_dot_v * sqrt(n_dot_l * n_dot_l * (1.0 - r2) + r2);
#endif

    float ggx = ggxv + ggxl;
    if (ggx > 0.0) {
        return 0.5 / ggx;
    }
    return 0.0;
}

// GGX/Trowbridge-Reitz
float microfacet_distribution(FunctionParamters func_params) {
    float roughness2 = func_params.roughness * func_params.roughness;
    float f = (func_params.n_dot_h * func_params.n_dot_h) * (roughness2 - 1.0) + 1.0;
    return roughness2 / (PI * f * f);
}

// Lambert
float diffuse_function() {
    return 1.0 / PI;
}

#ifdef ENABLE_SHADOWS
float shadow_caster_contrib(sampler2DShadow shadowmap, vec4 shadowpos) {
    vec3 light_space_coords = shadowpos.xyz / shadowpos.w;
    light_space_coords.z -= global_shadow_bias;
#ifdef USE_330
    float shadow = texture(shadowmap, light_space_coords);
#else
    float shadow = shadow2D(shadowmap, light_space_coords).r;
#endif
    return shadow;
}
#endif

vec3 get_normalmap_data() {
#ifdef CALC_NORMAL_Z
    vec2 normalXY = 2.0 * texture2D(p3d_TextureNormal, v_texcoord).rg - 1.0;
    float normalZ = sqrt(clamp(1.0 - dot(normalXY, normalXY), 0.0, 1.0));
    return vec3(
        normalXY,
        normalZ
    );
#else
    return 2.0 * texture2D(p3d_TextureNormal, v_texcoord).rgb - 1.0;
#endif
}

vec3 irradiance_from_sh(vec3 normal) {
    return
        + sh_coeffs[0] * 0.282095
        + sh_coeffs[1] * 0.488603 * normal.x
        + sh_coeffs[2] * 0.488603 * normal.z
        + sh_coeffs[3] * 0.488603 * normal.y
        + sh_coeffs[4] * 1.092548 * normal.x * normal.z
        + sh_coeffs[5] * 1.092548 * normal.y * normal.z
        + sh_coeffs[6] * 1.092548 * normal.y * normal.x
        + sh_coeffs[7] * (0.946176 * normal.z * normal.z - 0.315392)
        + sh_coeffs[8] * 0.546274 * (normal.x * normal.x - normal.y * normal.y);
}

void main() {
    vec4 metal_rough = texture2D(p3d_TextureMetalRoughness, v_texcoord);
    float metallic = clamp(p3d_Material.metallic * metal_rough.b, 0.0, 1.0);
    float perceptual_roughness = clamp(p3d_Material.roughness * metal_rough.g,  0.0, 1.0);
    float alpha_roughness = perceptual_roughness * perceptual_roughness;
    vec4 base_color = p3d_Material.baseColor * v_color * p3d_ColorScale * (texture2D(p3d_TextureBaseColor, v_texcoord) + p3d_TexAlphaOnly);
    vec3 diffuse_color = (base_color.rgb * (vec3(1.0) - F0)) * (1.0 - metallic);
    vec3 spec_color = mix(F0, base_color.rgb, metallic);
#ifdef USE_NORMAL_MAP
    vec3 normalmap = get_normalmap_data();
    vec3 n = normalize(v_view_tbn * normalmap);
    vec3 world_normal = normalize(v_world_tbn * normalmap);
#else
    // No normal map: use direct varyings instead of TBN extraction.
    // TBN may contain NaN when geometry lacks tangent data (planet spheres).
    vec3 n = normalize(v_view_tbn[2]);  // View-space normal = column 2
    vec3 world_normal = normalize(v_world_normal);
#endif

    // Geometric Specular Anti-Aliasing (Kaplanyan & Hill, JCGT 2016)
    // When normals vary faster than the pixel rate (distant geometry,
    // normal maps, hard edges), specular highlights alias/shimmer.
    // Fix: measure screen-space normal variance via partial derivatives
    // and widen the roughness to blur out sub-pixel specular peaks.
    {
        vec3 dNdx = dFdx(world_normal);
        vec3 dNdy = dFdy(world_normal);
        float variance = max(dot(dNdx, dNdx), dot(dNdy, dNdy));
        float kernel_roughness = min(2.0 * variance, 0.18);
        alpha_roughness = clamp(alpha_roughness + kernel_roughness, 0.0, 1.0);
        perceptual_roughness = sqrt(alpha_roughness);
    }

    vec3 v = normalize(-v_view_position);
    vec3 world_view = normalize(camera_world_position - v_world_position);

#ifdef USE_OCCLUSION_MAP
    float ambient_occlusion = metal_rough.r;
#else
    float ambient_occlusion = 1.0;
#endif

#ifdef USE_EMISSION_MAP
    vec3 emission = p3d_Material.emission.rgb * texture2D(p3d_TextureEmission, v_texcoord).rgb;
#else
    vec3 emission = vec3(0.0);
#endif

    vec4 color = vec4(vec3(0.0), base_color.a);

    float n_dot_v = clamp(abs(dot(n, v)), 0.0, 1.0);

#ifndef SUN_FROM_LIGHTSOURCE
    // ---- Pax sun directional light (world-space, custom uniforms) ----
    // Legacy mode: no shadow support on the sun. R2 replaces this with a
    // real DirectionalLight processed by the p3d_LightSource loop below
    // (define SUN_FROM_LIGHTSOURCE).
    {
        vec3 l = normalize(u_sun_dir_world);
        vec3 h = normalize(l + world_view);

        FunctionParamters func_params;
        func_params.n_dot_l = clamp(dot(world_normal, l), 0.0, 1.0);
        func_params.n_dot_v = n_dot_v;
        func_params.n_dot_h = clamp(dot(world_normal, h), 0.0, 1.0);
        func_params.l_dot_h = clamp(dot(l, h), 0.0, 1.0);
        func_params.v_dot_h = clamp(dot(world_view, h), 0.0, 1.0);
        func_params.roughness = alpha_roughness;
        func_params.metallic = metallic;
        func_params.reflection0 = spec_color;
        func_params.diffuse_color = diffuse_color;
        func_params.specular_color = spec_color;

        vec3 F = specular_reflection(func_params);
        float V = visibility_occlusion(func_params);
        float D = microfacet_distribution(func_params);

        vec3 diffuse_contrib = diffuse_color * diffuse_function();
        vec3 spec_contrib = vec3(F * V * D);
        color.rgb += func_params.n_dot_l * u_sun_color * (diffuse_contrib + spec_contrib);
    }
#endif

    // ---- Lights from the Panda3D light system ----
    // Point and spot lights always. With SUN_FROM_LIGHTSOURCE, directional
    // lights (position.w == 0) are handled here too: the w-multiply below
    // makes light_pos the view-space toward-light direction, attenuation
    // resolves to 1, and the shadow path works via shadowViewMatrix.
    for (int i = 0; i < p3d_LightSource.length(); ++i) {
#ifndef SUN_FROM_LIGHTSOURCE
        // Legacy mode: directional lights use the uniform sun block above
        if (p3d_LightSource[i].position.w < 0.5) continue;
#endif

        vec3 lightcol = p3d_LightSource[i].diffuse.rgb;

        if (dot(lightcol, lightcol) < LIGHT_CUTOFF) {
            continue;
        }

        vec3 light_pos = p3d_LightSource[i].position.xyz - v_view_position * p3d_LightSource[i].position.w;
        vec3 l = normalize(light_pos);
        vec3 h = normalize(l + v);
        float dist = length(light_pos);
        vec3 att_const = p3d_LightSource[i].attenuation;
        float attenuation_factor = 1.0 / (att_const.x + att_const.y * dist + att_const.z * dist * dist);
        float spotcos = dot(normalize(p3d_LightSource[i].spotDirection), -l);
        float spotcutoff = p3d_LightSource[i].spotCosCutoff;
        float shadowSpot = (spotcutoff > SPOTSMOOTH) ? smoothstep(spotcutoff-SPOTSMOOTH, spotcutoff+SPOTSMOOTH, spotcos) : 1.0;
#ifdef ENABLE_SHADOWS
        float shadow_caster = shadow_caster_contrib(p3d_LightSource[i].shadowMap, v_shadow_pos[i]);
#else
        float shadow_caster = 1.0;
#endif
        float shadow = shadowSpot * shadow_caster * attenuation_factor;

        FunctionParamters func_params;
        func_params.n_dot_l = clamp(dot(n, l), 0.0, 1.0);
        func_params.n_dot_v = n_dot_v;
        func_params.n_dot_h = clamp(dot(n, h), 0.0, 1.0);
        func_params.l_dot_h = clamp(dot(l, h), 0.0, 1.0);
        func_params.v_dot_h = clamp(dot(v, h), 0.0, 1.0);
        func_params.roughness = alpha_roughness;
        func_params.metallic =  metallic;
        func_params.reflection0 = spec_color;
        func_params.diffuse_color = diffuse_color;
        func_params.specular_color = spec_color;

        vec3 F = specular_reflection(func_params);
        float V = visibility_occlusion(func_params);
        float D = microfacet_distribution(func_params);

        vec3 diffuse_contrib = diffuse_color * diffuse_function();
        vec3 spec_contrib = vec3(F * V * D);
        color.rgb += func_params.n_dot_l * lightcol * (diffuse_contrib + spec_contrib) * shadow;
    }

    // Indirect diffuse + specular (IBL)
    vec3 ibl_f = fresnelSchlickRoughness(n_dot_v, spec_color, perceptual_roughness);
    vec3 ibl_kd = (1.0 - ibl_f) * (1.0 - metallic);
    vec3 ibl_diff = base_color.rgb * max(irradiance_from_sh(world_normal), 0.0) * diffuse_function();

    vec3 ibl_r = reflect(-world_view, world_normal);
    vec2 env_brdf = texture2D(brdf_lut, vec2(n_dot_v, perceptual_roughness)).rg;
    vec3 ibl_spec_color = textureCubeLod(filtered_env_map, ibl_r, perceptual_roughness * max_reflection_lod).rgb;
    vec3 ibl_spec = ibl_spec_color * (ibl_f * env_brdf.x + env_brdf.y);
    color.rgb += (ibl_kd * ibl_diff  + ibl_spec) * ambient_occlusion;

    // Indirect diffuse (ambient light)
    color.rgb += (diffuse_color + spec_color) * p3d_LightModel.ambient.rgb * ambient_occlusion;

    // Emission with optional limb darkening (Solar mode)
    // Eddington approximation: I(θ) = I₀ · (1 - u·(1 - cosθ))
    // u_limb_darkening defaults to 0 (no effect on non-stellar objects)
    if (u_limb_darkening > 0.0) {
        float ld_cos_theta = clamp(dot(world_normal, world_view), 0.0, 1.0);
        emission *= 1.0 - u_limb_darkening * (1.0 - ld_cos_theta);
    }
    color.rgb += emission;

#ifdef ENABLE_FOG
    // Exponential fog
    float fog_distance = length(v_view_position);
    float fog_factor = clamp(1.0 / exp(fog_distance * p3d_Fog.density), 0.0, 1.0);
    color = mix(p3d_Fog.color, color, fog_factor);
#endif

    // Debug visualization modes (V key cycles when Ctrl+L debug is on)
    if (u_debug_lighting > 0.5 && u_debug_lighting < 1.5) {
        // Mode 1: World normals from TBN as RGB (R=X, G=Y, B=Z, 0.5=zero)
        color = vec4(world_normal * 0.5 + 0.5, 1.0);
    } else if (u_debug_lighting > 1.5 && u_debug_lighting < 2.5) {
        // Mode 2: n_dot_l as grayscale (white=lit, black=dark)
        float ndl = clamp(dot(world_normal, normalize(u_sun_dir_world)), 0.0, 1.0);
        color = vec4(vec3(ndl), 1.0);
    } else if (u_debug_lighting > 2.5 && u_debug_lighting < 3.5) {
        // Mode 3: Light direction as uniform color (verify what shader receives)
        color = vec4(normalize(u_sun_dir_world) * 0.5 + 0.5, 1.0);
    } else if (u_debug_lighting > 3.5 && u_debug_lighting < 4.5) {
        // Mode 4: Position-derived normals (bypass normal matrix entirely)
        // For a sphere at origin this IS the correct normal — compare with mode 1
        vec3 pos_normal = normalize(v_world_position);
        color = vec4(pos_normal * 0.5 + 0.5, 1.0);
    } else if (u_debug_lighting > 4.5 && u_debug_lighting < 5.5) {
        // Mode 5: n_dot_l using position-derived normals (bypass normal matrix)
        vec3 pos_normal = normalize(v_world_position);
        float ndl = clamp(dot(pos_normal, normalize(u_sun_dir_world)), 0.0, 1.0);
        color = vec4(vec3(ndl), 1.0);
    } else if (u_debug_lighting > 5.5 && u_debug_lighting < 6.5) {
        // Mode 6: SIGNED n_dot_l — GREEN=lit (positive), RED=backlit (negative)
        // If center is RED, normals and sun_dir are in OPPOSITE directions
        // If center is BLACK, they're perpendicular (CS mismatch)
        float ndl_raw = dot(world_normal, normalize(u_sun_dir_world));
        if (ndl_raw >= 0.0)
            color = vec4(0.0, ndl_raw * 2.0, 0.0, 1.0);
        else
            color = vec4(-ndl_raw * 2.0, 0.0, 0.0, 1.0);
    } else if (u_debug_lighting > 6.5 && u_debug_lighting < 7.5) {
        // Mode 7: Normal axis magnitudes — R=|X|, G=|Y|, B=|Z|
        // Center should be GREEN if normals are in P3D Z-up (Y=forward)
        // Center will be BLUE if normals are in GL Y-up (Z=forward)
        // This tells us which coordinate system the normals are in
        vec3 n_abs = abs(world_normal);
        color = vec4(n_abs, 1.0);
    } else if (u_debug_lighting > 7.5 && u_debug_lighting < 8.5) {
        // Mode 8: HARDCODED SUN TEST — bypass u_sun_dir_world entirely
        // Uses a hardcoded direction so we can verify normals independently.
        // If this mode lights the planet correctly, the problem is in the
        // u_sun_dir_world uniform value.  If it's still wrong, the normals
        // are the issue.
        vec3 test_sun = vec3(0.0, 1.0, 0.0);  // +Y = south in game
        float ndl_test = dot(world_normal, test_sun);
        if (ndl_test >= 0.0)
            color = vec4(0.0, ndl_test, ndl_test * 0.5, 1.0);  // CYAN-GREEN = lit
        else
            color = vec4(-ndl_test, 0.0, 0.0, 1.0);  // RED = backlit
    } else if (u_debug_lighting > 8.5 && u_debug_lighting < 9.5) {
        // Mode 9: FLOAT COMPONENTS TEST — reconstruct sun_dir from individual
        // float uniforms instead of the Vec3 u_sun_dir_world.
        // If mode 9 works but mode 2 doesn't → set_shader_input transforms Vec3!
        // If mode 9 also fails → problem is elsewhere (normals or convention)
        vec3 float_sun = normalize(vec3(u_sun_dir_x, u_sun_dir_y, u_sun_dir_z));
        float ndl_float = clamp(dot(world_normal, float_sun), 0.0, 1.0);
        color = vec4(vec3(ndl_float), 1.0);  // Same as mode 2 but from floats
    }
#ifdef ENABLE_SHADOWS
    else if (u_debug_lighting > 9.5 && u_debug_lighting < 10.5) {
        // Mode 10: shadow-map UV of light 0 (R=u, G=v, B=depth ref).
        // In-frustum fragments show a smooth 0..1 gradient; solid saturated
        // colors mean the shadowViewMatrix maps them off-map.
        vec3 suv = v_shadow_pos[0].xyz / max(abs(v_shadow_pos[0].w), 1e-6);
        color = vec4(suv, 1.0);
    } else if (u_debug_lighting > 10.5 && u_debug_lighting < 11.5) {
        // Mode 11: shadow term of light 0 (white=lit, black=shadowed).
        float s = shadow_caster_contrib(p3d_LightSource[0].shadowMap,
                                        v_shadow_pos[0]);
        color = vec4(vec3(s), 1.0);
    }
#endif

#ifdef LOG_DEPTH
    // Window-space depth in [0,1], logarithmic in view distance: resolves
    // ~mm at planetary range where a 24-bit linear buffer resolves ~2 IEU
    // (paxtest test_scale zfight_at_range is the acceptance check).
    // Costs early-Z for this shader — acceptable in sparse space scenes.
    gl_FragDepth = log2(max(v_log_depth_w, 1e-6)) * u_log_depth_coef;
#endif

#ifdef USE_330
    o_color = color;
#else
    gl_FragColor = color;
#endif
}
