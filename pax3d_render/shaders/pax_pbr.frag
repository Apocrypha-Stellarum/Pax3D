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
    #define texture2DArray texture
#else
    #extension GL_ARB_shader_texture_lod : require
#ifdef TERRAIN_SPLAT
    // sampler2DArray on the legacy path (GLSL 330 has it in core)
    #extension GL_EXT_texture_array : require
#endif
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

#ifdef ENABLE_ATMOSPHERE
// Aerial perspective / height haze (R5.1, planetside package). Exponential-
// height medium: density(z) = u_atmo_density * exp(-(z - base) / H), with
// the optical depth along the camera->fragment ray integrated analytically.
// Inscatter color blends toward u_atmo_sun_haze_color when looking sunward
// (forward-scattering lobe, pow(mu, u_atmo_sun_power)). World space here is
// the same frame as u_sun_dir_world / camera_world_position (Panda Z-up:
// +z is up, so height = world position z).
uniform vec3 u_atmo_haze_color;      // horizon inscatter, linear HDR
uniform vec3 u_atmo_sun_haze_color;  // inscatter when looking at the sun
uniform float u_atmo_sun_power;      // forward-lobe tightness
uniform float u_atmo_density;        // extinction per world unit at base height
uniform float u_atmo_inv_scale_height;  // 1 / H (world units)
uniform float u_atmo_base_height;    // world z of the density datum
uniform float u_atmo_scale;          // per-node haze scale (Session S):
                                     // scales optical depth; root default
                                     // 1.0 exact no-op, 0.0 = no haze on
                                     // the subtree (hull interiors)
#endif

uniform vec4 p3d_ColorScale;
uniform vec4 p3d_TexAlphaOnly;

uniform vec3 sh_coeffs[9];
uniform vec3 camera_world_position;

// Per-node indirect-light scale (Session L, hull interiors): damps the
// ambient terms (SH/IBL + flat AmbientLight) for enclosed spaces that
// the global sky ambient should not reach. Direct lights and emission
// are untouched. Root default 1.0 = exact no-op (IEEE x*1.0 == x);
// subtrees override via pipeline.set_ambient_scale(np, k).
uniform float u_ambient_scale;

// Per-node material UV transform (ER-005, Session V — powered displays):
// mat_uv = v_texcoord * zw + xy, applied to the STANDARD material samples
// (base color, metal-rough, normal, emission) — not the terrain-splat
// sample set, which has its own transform machinery. Root default
// (0,0,1,1) = exact no-op (IEEE x*1.0+0.0 == x); subtrees override via
// set_uv_transform / set_uv_scroll / play_flipbook (scrolling readouts,
// chase-light strips, flipbook screen playback).
uniform vec4 u_uv_transform;

// Per-node emission factor (ER-005): multiplies ONLY the emission term.
// Root default (1,1,1) = exact no-op; set_emission_scale/_color drive
// screen power states and blink/pulse without touching materials.
uniform vec3 u_emission_factor;

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

#ifdef TERRAIN_SPLAT
// ---- Terrain layer splatting (ER-001, pipeline.set_terrain_splat) ----
// Per-fragment blend of up to 4 material layers packed as 2D texture
// arrays (albedo required; normal/ORM optional), weighted by an RGBA
// splat map. Composes with everything downstream (sun, shadows, fog,
// aerial perspective, SH ambient, IBL) because it only replaces the
// MATERIAL INPUTS — the lighting math below is byte-for-byte the
// standard path.
uniform sampler2DArray terrain_albedo;
uniform sampler2D terrain_splat;
uniform vec4 u_terrain_uv_scales;       // per-layer detail UV scale
uniform vec4 u_terrain_splat_transform; // base UV -> splat UV: xy off, zw scale
uniform mat4 p3d_ViewMatrix;            // world -> view for the terrain normal
#ifdef TERRAIN_SPLAT_NORMALS
uniform sampler2DArray terrain_normal;
uniform vec2 u_terrain_normal_fade;     // (start, end) view distance
#endif
#ifdef TERRAIN_SPLAT_ORM
uniform sampler2DArray terrain_orm;     // r=occlusion g=roughness b=metallic
#endif
#ifdef TERRAIN_SPLAT_MACRO
uniform sampler2D terrain_macro;        // low-frequency albedo variation
uniform float u_terrain_macro_scale;    // base UV -> macro UV scale
uniform float u_terrain_macro_strength; // 0 = exact no-op
#endif

// THE v2 SEAM (user-ratified with the terrain dev, 2026-07-19): layer
// weights come from here and ONLY here. Hex-tiling (Mikkelsen JCGT
// 2022) and height-blend sharpening land later as new defines swapping
// this function's body — nothing else in the variant restructures.
vec4 terrain_layer_weights(vec2 base_uv) {
    vec2 suv = base_uv * u_terrain_splat_transform.zw
             + u_terrain_splat_transform.xy;
    vec4 w = texture2D(terrain_splat, suv);
    float total = w.x + w.y + w.z + w.w;
    // Renormalize (8-bit splat maps rarely sum to exactly 1); an empty
    // texel falls back to layer 0 rather than rendering black.
    return (total > 1e-5) ? w / total : vec4(1.0, 0.0, 0.0, 0.0);
}

vec4 terrain_blend_array(sampler2DArray layers, vec4 w, vec2 base_uv) {
    vec4 acc = vec4(0.0);
    for (int i = 0; i < 4; ++i) {
        acc += w[i] * texture2DArray(layers,
            vec3(base_uv * u_terrain_uv_scales[i], float(i)));
    }
    return acc;
}

#ifdef TERRAIN_HEX_TILING
// ---- Hex-tiling / stochastic detail sampling (ER-007) ----
// Mikkelsen "Practical Real-Time Hex-Tiling" (JCGT 2022) on the dual
// triangle lattice: each fragment blends the 3 nearest hex cells'
// samples, each cell hashed to a random phase offset (+ optional
// rotation about the cell center). The verbatim motif repetition of
// wrap-repeat tiling breaks up; wrap addressing and mip selection are
// untouched, so BOTH GLSL baselines work without textureGrad — a
// per-cell offset/rotation is constant across the cell, so every
// tap's UV is continuous wherever that tap's weight is nonzero (the
// tap whose cell assignment jumps at a blend-region boundary always
// carries weight ~0 there).
uniform vec2 u_terrain_hex;      // x = cell size in detail-UV repeats,
                                 // y = contrast (weight-sharpen exp)
uniform vec4 u_terrain_hex_rot;  // per-layer random-rotation range as
                                 // a fraction of +-180 deg (0 = off)

// Per-cell hash (Hoskins fract-mix): no sin(), so it stays well
// distributed at the large lattice ids planetary detail UVs produce
// (float-exact into the tens of thousands of repeats).
vec2 hex_hash(vec2 id) {
    vec3 p3 = fract(vec3(id.x, id.y, id.x)
                    * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

// The 3 nearest hex-cell ids + contrast-sharpened barycentric weights
// for st = detail_uv / cell_size. The pow sharpen is the cheap
// variance-preserving stand-in for histogram-preserving blending:
// blend zones narrow, so most of every cell shows one sample nearly
// pure and the material grain survives.
void hex_grid(vec2 st, out vec2 id0, out vec2 id1, out vec2 id2,
              out vec3 w) {
    vec2 skewed = vec2(st.x, -0.57735027 * st.x + 1.15470054 * st.y);
    vec2 base_id = floor(skewed);
    vec3 t = vec3(fract(skewed), 0.0);
    t.z = 1.0 - t.x - t.y;
    if (t.z > 0.0) {
        w = vec3(t.z, t.y, t.x);
        id0 = base_id;
        id1 = base_id + vec2(0.0, 1.0);
        id2 = base_id + vec2(1.0, 0.0);
    } else {
        w = vec3(-t.z, 1.0 - t.y, 1.0 - t.x);
        id0 = base_id + vec2(1.0, 1.0);
        id1 = base_id + vec2(1.0, 0.0);
        id2 = base_id + vec2(0.0, 1.0);
    }
    w = pow(w, vec3(u_terrain_hex.y));
    w /= (w.x + w.y + w.z);
}

// One cell's tap UV: random phase offset + rotation about the cell
// center. cs returns (cos, sin) of the tap rotation so normal taps
// can rotate the sampled tangent-space xy back into the surface frame.
vec2 hex_tap_uv(vec2 duv, vec2 id, float rot_range, out vec2 cs) {
    float ang = (hex_hash(id + 17.31).x - 0.5) * 6.28318530718
                * rot_range;
    cs = vec2(cos(ang), sin(ang));
    vec2 center = vec2(id.x, 0.5 * id.x + 0.8660254 * id.y)
                  * u_terrain_hex.x;
    vec2 d = duv - center;
    return center + hex_hash(id)
           + vec2(cs.x * d.x - cs.y * d.y,
                  cs.y * d.x + cs.x * d.y);
}

// Drop-in hex replacement for terrain_blend_array (albedo / ORM).
vec4 hex_blend_array(sampler2DArray layers, vec4 w, vec2 base_uv) {
    vec4 acc = vec4(0.0);
    for (int i = 0; i < 4; ++i) {
        vec2 duv = base_uv * u_terrain_uv_scales[i];
        vec2 id0, id1, id2;
        vec3 hw;
        hex_grid(duv / u_terrain_hex.x, id0, id1, id2, hw);
        float rot = u_terrain_hex_rot[i];
        vec2 cs;
        vec4 s = hw.x * texture2DArray(layers,
                     vec3(hex_tap_uv(duv, id0, rot, cs), float(i)))
               + hw.y * texture2DArray(layers,
                     vec3(hex_tap_uv(duv, id1, rot, cs), float(i)))
               + hw.z * texture2DArray(layers,
                     vec3(hex_tap_uv(duv, id2, rot, cs), float(i)));
        acc += w[i] * s;
    }
    return acc;
}
#endif  // TERRAIN_HEX_TILING
#endif

uniform sampler2D p3d_TextureBaseColor;
uniform sampler2D p3d_TextureMetalRoughness;
uniform sampler2D p3d_TextureNormal;
uniform sampler2D p3d_TextureEmission;

uniform sampler2D brdf_lut;
uniform samplerCube filtered_env_map;
uniform float max_reflection_lod;

// Specular-env controls (Round-5 asks). u_env_scale is per-node
// (subtree-inherited, like u_ambient_scale but env-only — SH diffuse
// and flat ambient untouched); u_env_intensity is global (sky
// brightness ramps / skybox crossfades track game-side SH scaling);
// u_env_yaw = (cos, sin) rotates the reflection lookup about world +Z
// so drift-rotating skies keep specular in sync with the yawed SH.
// Root defaults (1.0, 1.0, (1,0)) are exact no-ops.
uniform float u_env_scale;
uniform float u_env_intensity;
uniform vec2 u_env_yaw;

#ifdef ENABLE_SHADOWS
// Depth bias in NORMALIZED light-space depth (world offset = bias *
// shadow-extent depth); the pipeline rescales world-unit biases before
// upload. u_shadow_texel = 1/shadow_map_size, for the multi-tap filter.
uniform float global_shadow_bias;
// Slope-scaled (grazing-angle) shadow bias, also in NORMALIZED light-space
// depth per unit tan(theta): the pipeline uploads world_units/extent_depth.
// Added to global_shadow_bias scaled by tan(theta) between the receiver
// normal and the light, so grazing receivers (where one shadow texel spans
// a large depth and a constant bias self-shadows into acne bands) get just
// enough extra bias while normal-incidence receivers are untouched.
// Default 0 => byte-identical to the constant-bias-only path (opt-in).
uniform float u_shadow_normal_bias;
uniform float u_shadow_texel;
// world -> light-0 shadow-UV matrix, pushed by the pipeline (debug
// modes 12/13: fragment-recomputed shadow coords vs the interpolated
// v_shadow_pos varying).
uniform mat4 u_probe_shadow_world_mat;
// fixed (u, v, ref) for debug mode 15's constant-sample probe.
uniform vec3 u_probe_uvref;
#endif
#ifndef SHADOW_FILTER_SIZE
    #define SHADOW_FILTER_SIZE 1
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
// tan(theta) between the receiver normal and the light, from NdotL, clamped
// so a near-perpendicular receiver (ndl->0) does not blow the bias up. The
// full grazing bias = global_shadow_bias + u_shadow_normal_bias * slope.
float shadow_slope_from_ndl(float ndl) {
    float c = clamp(ndl, 0.0, 1.0);
    float slope = sqrt(max(1.0 - c * c, 0.0)) / max(c, 0.15);  // tan(theta)
    return min(slope, 8.0);
}

float slope_scaled_bias(float ndl) {
    return global_shadow_bias + u_shadow_normal_bias * shadow_slope_from_ndl(ndl);
}

float shadow_caster_contrib_biased(sampler2DShadow shadowmap, vec4 shadowpos,
                                   float bias) {
    vec3 light_space_coords = shadowpos.xyz / shadowpos.w;
    light_space_coords.z -= bias;
#if SHADOW_FILTER_SIZE == 3
    // 3x3 multi-tap PCF: 9 hardware-filtered taps, one texel apart.
    float shadow = 0.0;
    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            vec3 tap = light_space_coords
                     + vec3(float(dx) * u_shadow_texel,
                            float(dy) * u_shadow_texel, 0.0);
#ifdef USE_330
            shadow += texture(shadowmap, tap);
#else
            shadow += shadow2D(shadowmap, tap).r;
#endif
        }
    }
    return shadow / 9.0;
#else
#ifdef USE_330
    float shadow = texture(shadowmap, light_space_coords);
#else
    float shadow = shadow2D(shadowmap, light_space_coords).r;
#endif
    return shadow;
#endif
}
#endif

vec3 get_normalmap_data(vec2 uv) {
#ifdef CALC_NORMAL_Z
    vec2 normalXY = 2.0 * texture2D(p3d_TextureNormal, uv).rg - 1.0;
    float normalZ = sqrt(clamp(1.0 - dot(normalXY, normalXY), 0.0, 1.0));
    return vec3(
        normalXY,
        normalZ
    );
#else
    return 2.0 * texture2D(p3d_TextureNormal, uv).rgb - 1.0;
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
    // Per-node material UV (ER-005): identity at the root default —
    // v_texcoord exactly (x*1.0+0.0 == x). Terrain-splat sampling below
    // deliberately keeps raw v_texcoord.
    vec2 mat_uv = v_texcoord * u_uv_transform.zw + u_uv_transform.xy;
#ifdef TERRAIN_SPLAT
    // ---- Terrain splat material inputs (ER-001) ----
    vec4 terrain_w = terrain_layer_weights(v_texcoord);
#ifdef TERRAIN_HEX_TILING
    #define TERRAIN_SAMPLE hex_blend_array
#else
    #define TERRAIN_SAMPLE terrain_blend_array
#endif
#ifdef TERRAIN_SPLAT_ORM
    vec4 metal_rough = TERRAIN_SAMPLE(terrain_orm, terrain_w, v_texcoord);
#else
    vec4 metal_rough = vec4(1.0);  // material roughness/metallic drive
#endif
    float metallic = clamp(p3d_Material.metallic * metal_rough.b, 0.0, 1.0);
    float perceptual_roughness = clamp(p3d_Material.roughness * metal_rough.g,  0.0, 1.0);
    float alpha_roughness = perceptual_roughness * perceptual_roughness;
    vec4 terrain_albedo_px = TERRAIN_SAMPLE(terrain_albedo, terrain_w,
                                            v_texcoord);
#ifdef TERRAIN_SPLAT_MACRO
    // Macro variation: brightness modulation at 100-500 m scale kills
    // the wallpaper effect. A 0.5 macro texel is an EXACT no-op
    // (mix(1, 1, s) == 1), any strength.
    float terrain_macro_px = texture2D(terrain_macro,
        v_texcoord * u_terrain_macro_scale).r;
    terrain_albedo_px.rgb *= mix(1.0, 2.0 * terrain_macro_px,
                                 u_terrain_macro_strength);
#endif
    vec4 base_color = p3d_Material.baseColor * v_color * p3d_ColorScale * (terrain_albedo_px + p3d_TexAlphaOnly);
    vec3 diffuse_color = (base_color.rgb * (vec3(1.0) - F0)) * (1.0 - metallic);
    vec3 spec_color = mix(F0, base_color.rgb, metallic);

    // Terrain normals: chunk meshes carry no tangent column (v_*_tbn is
    // the NaN trap), so build the world TBN analytically from the
    // world-aligned planar UV convention (u -> +world_x, v -> +world_y;
    // on steep faces the basis Gram-Schmidts around the surface normal).
    vec3 world_normal = normalize(v_world_normal);
#ifdef TERRAIN_SPLAT_NORMALS
    {
        vec3 t_ws = normalize(vec3(1.0, 0.0, 0.0)
                              - world_normal * world_normal.x);
        vec3 b_ws = cross(world_normal, t_ws);
        vec3 n_ts = vec3(0.0);
#ifdef TERRAIN_HEX_TILING
        // Hex taps for normals: same cells/weights/rotations as the
        // albedo taps (material coherence), with each sampled tangent-
        // space xy rotated BACK by the tap rotation so the normal
        // follows the rotated motif.
        for (int i = 0; i < 4; ++i) {
            vec2 duv = v_texcoord * u_terrain_uv_scales[i];
            vec2 id0, id1, id2;
            vec3 hw;
            hex_grid(duv / u_terrain_hex.x, id0, id1, id2, hw);
            float rot = u_terrain_hex_rot[i];
            vec2 cs;
            vec3 s;
            vec3 acc = vec3(0.0);
            s = 2.0 * texture2DArray(terrain_normal,
                vec3(hex_tap_uv(duv, id0, rot, cs), float(i))).rgb - 1.0;
            acc += hw.x * vec3(cs.x * s.x + cs.y * s.y,
                               -cs.y * s.x + cs.x * s.y, s.z);
            s = 2.0 * texture2DArray(terrain_normal,
                vec3(hex_tap_uv(duv, id1, rot, cs), float(i))).rgb - 1.0;
            acc += hw.y * vec3(cs.x * s.x + cs.y * s.y,
                               -cs.y * s.x + cs.x * s.y, s.z);
            s = 2.0 * texture2DArray(terrain_normal,
                vec3(hex_tap_uv(duv, id2, rot, cs), float(i))).rgb - 1.0;
            acc += hw.z * vec3(cs.x * s.x + cs.y * s.y,
                               -cs.y * s.x + cs.x * s.y, s.z);
            n_ts += terrain_w[i] * acc;
        }
#else
        for (int i = 0; i < 4; ++i) {
            n_ts += terrain_w[i] * (2.0 * texture2DArray(terrain_normal,
                vec3(v_texcoord * u_terrain_uv_scales[i], float(i))).rgb - 1.0);
        }
#endif
        // Detail-normal distance fade: flat past fade_end so far-field
        // terrain (most of the frame) cannot sparkle/moire.
        float terrain_nf = smoothstep(u_terrain_normal_fade.x,
                                      u_terrain_normal_fade.y,
                                      length(v_view_position));
        n_ts = mix(n_ts, vec3(0.0, 0.0, 1.0), terrain_nf);
        world_normal = normalize(mat3(t_ws, b_ws, world_normal)
                                 * normalize(n_ts));
    }
#endif
    vec3 n = normalize(mat3(p3d_ViewMatrix) * world_normal);
#else
    vec4 metal_rough = texture2D(p3d_TextureMetalRoughness, mat_uv);
    float metallic = clamp(p3d_Material.metallic * metal_rough.b, 0.0, 1.0);
    float perceptual_roughness = clamp(p3d_Material.roughness * metal_rough.g,  0.0, 1.0);
    float alpha_roughness = perceptual_roughness * perceptual_roughness;
    vec4 base_color = p3d_Material.baseColor * v_color * p3d_ColorScale * (texture2D(p3d_TextureBaseColor, mat_uv) + p3d_TexAlphaOnly);
    vec3 diffuse_color = (base_color.rgb * (vec3(1.0) - F0)) * (1.0 - metallic);
    vec3 spec_color = mix(F0, base_color.rgb, metallic);
#ifdef USE_NORMAL_MAP
    vec3 normalmap = get_normalmap_data(mat_uv);
    vec3 n = normalize(v_view_tbn * normalmap);
    vec3 world_normal = normalize(v_world_tbn * normalmap);
#else
    // No normal map: use direct varyings instead of TBN extraction.
    // TBN may contain NaN when geometry lacks tangent data (planet spheres).
    vec3 n = normalize(v_view_tbn[2]);  // View-space normal = column 2
    vec3 world_normal = normalize(v_world_normal);
#endif
#endif  // TERRAIN_SPLAT

#ifdef ALPHA_MASK
    // glTF alphaMode MASK (pipeline.apply_alpha_masks): the loader's
    // AlphaTestAttrib only reaches fixed-function GL_ALPHA_TEST, which
    // core profile lacks — this variant applies the same keep-if-
    // greater-equal predicate in-shader, so both baselines agree.
    // Compat keeps the fixed-function test active too: identical
    // predicate on the same output alpha, so the double application
    // cannot change a pixel.
    if (base_color.a < ALPHA_MASK_CUTOFF) {
        discard;
    }
#endif

#ifdef DOUBLE_SIDED_LIGHTING
    // glTF doubleSided semantic (Khronos sample-viewer behavior): shade
    // backfaces with the inverted normal, so two-sided geometry seen
    // from behind lights from the side actually facing the light.
    // gl_FrontFacing is uniform per triangle — front faces take the
    // no-op path and are bit-identical to the flag-off compile.
    if (!gl_FrontFacing) {
        n = -n;
        world_normal = -world_normal;
    }
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
    // Fold the per-node ambient scale into the AO factor: AO multiplies
    // exactly the indirect terms (IBL + flat ambient) below — including
    // their GLASS-variant splits — and nothing else.
    ambient_occlusion *= u_ambient_scale;

#ifdef USE_EMISSION_MAP
    // u_emission_factor: per-node power/tint control (ER-005); root
    // default (1,1,1) is an exact no-op.
    vec3 emission = p3d_Material.emission.rgb * u_emission_factor * texture2D(p3d_TextureEmission, mat_uv).rgb;
#else
    vec3 emission = vec3(0.0);
#endif

    vec4 color = vec4(vec3(0.0), base_color.a);
#ifdef GLASS
    // Glass contract (pipeline.set_glass): specular reflections must
    // survive low alpha. Transmission-class terms (diffuse, ambient)
    // accumulate in color.rgb and are scaled by alpha at the compose
    // point below; reflection-class terms accumulate here and add at
    // full strength. The pipeline pairs this variant with
    // M_premultiplied_alpha blending, so color.rgb leaves this shader
    // already coverage-weighted.
    vec3 glass_spec = vec3(0.0);
#endif

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
#ifdef GLASS
        color.rgb += func_params.n_dot_l * u_sun_color * diffuse_contrib;
        glass_spec += func_params.n_dot_l * u_sun_color * spec_contrib;
#else
        color.rgb += func_params.n_dot_l * u_sun_color * (diffuse_contrib + spec_contrib);
#endif
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
        // Slope-scaled bias: view-space NdotL == world-space NdotL (the
        // receiver/light angle is frame-invariant), so dot(n, l) here is the
        // grazing measure. With u_shadow_normal_bias=0 this is exactly the
        // constant-bias path (opt-in, byte-identical when off).
        float shadow_caster = shadow_caster_contrib_biased(
            p3d_LightSource[i].shadowMap, v_shadow_pos[i],
            slope_scaled_bias(dot(n, l)));
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
#ifdef GLASS
        color.rgb += func_params.n_dot_l * lightcol * diffuse_contrib * shadow;
        glass_spec += func_params.n_dot_l * lightcol * spec_contrib * shadow;
#else
        color.rgb += func_params.n_dot_l * lightcol * (diffuse_contrib + spec_contrib) * shadow;
#endif
    }

    // Indirect diffuse + specular (IBL)
    vec3 ibl_f = fresnelSchlickRoughness(n_dot_v, spec_color, perceptual_roughness);
    vec3 ibl_kd = (1.0 - ibl_f) * (1.0 - metallic);
    vec3 ibl_diff = base_color.rgb * max(irradiance_from_sh(world_normal), 0.0) * diffuse_function();

    vec3 ibl_r = reflect(-world_view, world_normal);
    // Env yaw: sample the map at Rz(-theta)*r — the environment reads
    // as rotated by +theta (the skybox set_h sense). (1,0) exact no-op.
    ibl_r = vec3(u_env_yaw.x * ibl_r.x - u_env_yaw.y * ibl_r.y,
                 u_env_yaw.y * ibl_r.x + u_env_yaw.x * ibl_r.y,
                 ibl_r.z);
    vec2 env_brdf = texture2D(brdf_lut, vec2(n_dot_v, perceptual_roughness)).rg;
    vec3 ibl_spec_color = textureCubeLod(filtered_env_map, ibl_r, perceptual_roughness * max_reflection_lod).rgb;
    vec3 ibl_spec = ibl_spec_color * (ibl_f * env_brdf.x + env_brdf.y)
                    * (u_env_scale * u_env_intensity);
#ifdef GLASS
    color.rgb += ibl_kd * ibl_diff * ambient_occlusion;
    glass_spec += ibl_spec * ambient_occlusion;
#else
    color.rgb += (ibl_kd * ibl_diff  + ibl_spec) * ambient_occlusion;
#endif

    // Indirect diffuse (ambient light)
#ifdef GLASS
    color.rgb += diffuse_color * p3d_LightModel.ambient.rgb * ambient_occlusion;
    glass_spec += spec_color * p3d_LightModel.ambient.rgb * ambient_occlusion;
#else
    color.rgb += (diffuse_color + spec_color) * p3d_LightModel.ambient.rgb * ambient_occlusion;
#endif

#ifdef GLASS
    // Glass compose: everything above is transmission-class and gets
    // coverage-weighted; reflections ride on top at full strength.
    // Emission (below) intentionally lands AFTER this point, also
    // unattenuated — an emissive element on glass is a light source,
    // not a filter.
    color.rgb = color.rgb * base_color.a + glass_spec;
#endif

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
#ifdef GLASS
    // Premultiplied surface: weight the fog color by coverage so clear
    // glass does not ADD opaque fog over the (already fogged) background.
    color.rgb = mix(p3d_Fog.color.rgb * color.a, color.rgb, fog_factor);
#else
    color = mix(p3d_Fog.color, color, fog_factor);
#endif
#endif

#ifdef ENABLE_ATMOSPHERE
    // Aerial perspective (R5.1). Applied after emission (extinction affects
    // emitters too) and, if both are compiled in, after the legacy fog.
    // With u_atmo_density = 0: tau = 0, trans = 1 -> color unchanged.
    {
        vec3 atmo_ray = v_world_position - camera_world_position;
        float atmo_dist = length(atmo_ray);
        // Optical depth of an exponential medium along the ray, analytic:
        //   tau = density * dist * exp(-a) * (1 - exp(-u)) / u
        // where a = (z_cam - base)/H and u = (z_frag - z_cam)/H; the
        // (1-exp(-u))/u factor -> 1 as the ray goes horizontal (u -> 0).
        float atmo_a = (camera_world_position.z - u_atmo_base_height)
                       * u_atmo_inv_scale_height;
        float atmo_u = (v_world_position.z - camera_world_position.z)
                       * u_atmo_inv_scale_height;
        float atmo_falloff = (abs(atmo_u) > 1e-4)
            ? (1.0 - exp(-clamp(atmo_u, -30.0, 30.0))) / atmo_u
            : 1.0;
        float atmo_tau = u_atmo_scale * u_atmo_density * atmo_dist
                         * exp(-clamp(atmo_a, -30.0, 30.0)) * atmo_falloff;
        float atmo_trans = exp(-clamp(atmo_tau, 0.0, 60.0));
        // Forward-scattering tint: mu = cos(view ray, toward-sun) — looking
        // AT the sun means the ray direction equals the toward-sun vector.
        float atmo_mu = (atmo_dist > 1e-6)
            ? clamp(dot(atmo_ray / atmo_dist, normalize(u_sun_dir_world)), 0.0, 1.0)
            : 0.0;
        vec3 atmo_inscatter = mix(u_atmo_haze_color, u_atmo_sun_haze_color,
                                  pow(atmo_mu, u_atmo_sun_power));
        // Alpha deliberately untouched (unlike the legacy fog mix).
#ifdef GLASS
        // Coverage-weighted inscatter, same reasoning as the fog path:
        // the background behind the glass already carries its own.
        color.rgb = color.rgb * atmo_trans
                    + atmo_inscatter * (1.0 - atmo_trans) * color.a;
#else
        color.rgb = color.rgb * atmo_trans + atmo_inscatter * (1.0 - atmo_trans);
#endif
    }
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
        // Uses the SAME slope-scaled bias as the lit pass, so this
        // instrument shows exactly what the shaded frame samples (grazing
        // acne visible with u_shadow_normal_bias=0, cleared when it is set).
        vec3 l0 = normalize(p3d_LightSource[0].position.xyz
                            - v_view_position * p3d_LightSource[0].position.w);
        float s = shadow_caster_contrib_biased(p3d_LightSource[0].shadowMap,
                                               v_shadow_pos[0],
                                               slope_scaled_bias(dot(n, l0)));
        color = vec4(vec3(s), 1.0);
    } else if (u_debug_lighting > 11.5 && u_debug_lighting < 12.5) {
        // Mode 12: |interpolated - recomputed| shadow coord of light 0.
        // v_shadow_pos is vertex-computed + interpolated; s2 is recomputed
        // per-fragment from v_world_position and the CPU-pushed world->UV
        // matrix. R/G = UV error x200 (0.005 UV = full red/green),
        // B = depth-ref error x2000 (0.0005 = full blue). Black = agree.
        vec4 s2 = u_probe_shadow_world_mat * vec4(v_world_position, 1.0);
        vec3 a = v_shadow_pos[0].xyz / max(abs(v_shadow_pos[0].w), 1e-6);
        vec3 b = s2.xyz / max(abs(s2.w), 1e-6);
        vec3 err = abs(a - b);
        color = vec4(err.x * 200.0, err.y * 200.0, err.z * 2000.0, 1.0);
    } else if (u_debug_lighting > 12.5 && u_debug_lighting < 13.5) {
        // Mode 13: shadow term of light 0 via the RECOMPUTED coord (the
        // candidate fix path). Compare with mode 11: if 13 is correct
        // where 11 is corrupted, the varying interpolation is the defect.
        // Same slope-scaled bias as mode 11 / the lit pass.
        vec3 l0 = normalize(p3d_LightSource[0].position.xyz
                            - v_view_position * p3d_LightSource[0].position.w);
        vec4 s2 = u_probe_shadow_world_mat * vec4(v_world_position, 1.0);
        float s = shadow_caster_contrib_biased(p3d_LightSource[0].shadowMap,
                                               s2, slope_scaled_bias(dot(n, l0)));
        color = vec4(vec3(s), 1.0);
    } else if (u_debug_lighting > 13.5 && u_debug_lighting < 14.5) {
        // Mode 14: 3-level probe of the GPU-BOUND depth texture at this
        // fragment's shadow UV. R = compare passes with ref pulled 2 m
        // toward the light, G = at ref (raw, no bias), B = ref pushed
        // 2 m deeper. Encodes which depth bucket the bound texel is in —
        // readable even if RAM extraction disagrees with the GPU.
        vec3 lsc = v_shadow_pos[0].xyz / v_shadow_pos[0].w;
        float dm = 0.5 / 600.0;
#ifdef USE_330
        float r = texture(p3d_LightSource[0].shadowMap,
                          vec3(lsc.xy, lsc.z - dm));
        float g = texture(p3d_LightSource[0].shadowMap, lsc);
        float b = texture(p3d_LightSource[0].shadowMap,
                          vec3(lsc.xy, lsc.z + dm));
#else
        float r = shadow2D(p3d_LightSource[0].shadowMap,
                           vec3(lsc.xy, lsc.z - dm)).r;
        float g = shadow2D(p3d_LightSource[0].shadowMap, lsc).r;
        float b = shadow2D(p3d_LightSource[0].shadowMap,
                           vec3(lsc.xy, lsc.z + dm)).r;
#endif
        color = vec4(r, g, b, 1.0);
    } else if (u_debug_lighting > 14.5 && u_debug_lighting < 15.5) {
        // Mode 15: sample the shadow map at ONE fixed uniform-supplied
        // (u, v, ref) — identical for every fragment. A healthy frame is
        // one flat color; per-geom color differences mean the bound
        // texture or sampler state differs between draws.
#ifdef USE_330
        float s = texture(p3d_LightSource[0].shadowMap, u_probe_uvref);
#else
        float s = shadow2D(p3d_LightSource[0].shadowMap, u_probe_uvref).r;
#endif
        color = vec4(vec3(s), 1.0);
    } else if (u_debug_lighting > 15.5 && u_debug_lighting < 16.5) {
        // Mode 16: distance of THIS fragment's shadow coord (signed-w
        // divide, the real sampling path) from the uniform probe point.
        // R/G = |du,dv| x100 (0.01 UV = 2.8 m saturates), B = |dref| x100.
        vec3 lsc = v_shadow_pos[0].xyz / v_shadow_pos[0].w;
        vec3 d = abs(lsc - u_probe_uvref);
        color = vec4(d.x * 100.0, d.y * 100.0, d.z * 100.0, 1.0);
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
