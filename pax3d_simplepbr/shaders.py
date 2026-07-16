# Pax3D fork of simplepbr 0.13.1 (Moguri) — adds bloom, ACES tonemapping
#
# New shaders: bloom_extract.frag, bloom_downsample.frag, bloom_upsample.frag
# Modified shader: tonemap.frag (ACES + bloom composite + selectable operators)

shaders={
# ============================================================================
# VERTEX SHADERS (unchanged from simplepbr)
# ============================================================================

'simplepbr.vert': '#version 120\n\n#ifndef MAX_LIGHTS\n    #define MAX_LIGHTS 8\n#endif\n\n#ifdef ENABLE_SHADOWS\nuniform struct p3d_LightSourceParameters {\n    vec4 position;\n    vec4 diffuse;\n    vec4 specular;\n    vec3 attenuation;\n    vec3 spotDirection;\n    float spotCosCutoff;\n    sampler2DShadow shadowMap;\n    mat4 shadowViewMatrix;\n} p3d_LightSource[MAX_LIGHTS];\n#endif\n\n#ifdef ENABLE_SKINNING\nuniform mat4 p3d_TransformTable[100];\n#endif\n\nuniform mat4 p3d_ProjectionMatrix;\nuniform mat4 p3d_ModelViewMatrix;\nuniform mat4 p3d_ViewMatrix;\nuniform mat4 p3d_ModelMatrix;\nuniform mat3 p3d_NormalMatrix;\nuniform mat4 p3d_TextureMatrix;\nuniform mat4 p3d_ModelMatrixInverseTranspose;\n\nattribute vec4 p3d_Vertex;\nattribute vec4 p3d_Color;\nattribute vec3 p3d_Normal;\nattribute vec4 p3d_Tangent;\nattribute vec2 p3d_MultiTexCoord0;\n#ifdef ENABLE_SKINNING\nattribute vec4 transform_weight;\nattribute vec4 transform_index;\n#endif\n\n\nvarying vec3 v_view_position;\nvarying vec3 v_world_position;\nvarying vec4 v_color;\nvarying vec2 v_texcoord;\nvarying mat3 v_view_tbn;\nvarying mat3 v_world_tbn;\n#ifdef ENABLE_SHADOWS\nvarying vec4 v_shadow_pos[MAX_LIGHTS];\n#endif\n\nvoid main() {\n#ifdef ENABLE_SKINNING\n    mat4 skin_matrix = (\n        p3d_TransformTable[int(transform_index.x)] * transform_weight.x +\n        p3d_TransformTable[int(transform_index.y)] * transform_weight.y +\n        p3d_TransformTable[int(transform_index.z)] * transform_weight.z +\n        p3d_TransformTable[int(transform_index.w)] * transform_weight.w\n    );\n    vec4 model_position = skin_matrix * p3d_Vertex;\n    mat3 skin_matrix3 = mat3(skin_matrix);\n    vec3 model_normal = skin_matrix3 * p3d_Normal;\n    vec3 model_tangent = skin_matrix3 * p3d_Tangent.xyz;\n#else\n    vec4 model_position = p3d_Vertex;\n    vec3 model_normal = p3d_Normal;\n    vec3 model_tangent = p3d_Tangent.xyz;\n#endif\n    vec4 view_position = p3d_ModelViewMatrix * model_position;\n    v_view_position = (view_position).xyz;\n    v_world_position = (p3d_ModelMatrix * model_position).xyz;\n    v_color = p3d_Color;\n    v_texcoord = (p3d_TextureMatrix * vec4(p3d_MultiTexCoord0, 0, 1)).xy;\n#ifdef ENABLE_SHADOWS\n    for (int i = 0; i < p3d_LightSource.length(); ++i) {\n        v_shadow_pos[i] = p3d_LightSource[i].shadowViewMatrix * view_position;\n    }\n#endif\n\n    vec3 view_normal = normalize(p3d_NormalMatrix * model_normal);\n    vec3 view_tangent = normalize(p3d_NormalMatrix * model_tangent);\n    vec3 view_bitangent = cross(view_normal, view_tangent) * p3d_Tangent.w;\n    v_view_tbn = mat3(\n        view_tangent,\n        view_bitangent,\n        view_normal\n    );\n\n    mat3 world_normal_mat = mat3(p3d_ModelMatrixInverseTranspose);\n    vec3 world_normal = normalize(world_normal_mat * model_normal);\n    vec3 world_tangent = normalize(world_normal_mat * model_tangent);\n    vec3 world_bitangent = cross(world_normal, world_tangent) * p3d_Tangent.w;\n    v_world_tbn = mat3(\n            world_tangent,\n            world_bitangent,\n            world_normal\n    );\n\n    gl_Position = p3d_ProjectionMatrix * view_position;\n}\n',

'shadow.vert': '#version 120\n\nuniform mat4 p3d_ModelViewProjectionMatrix;\n#ifdef ENABLE_SKINNING\nuniform mat4 p3d_TransformTable[100];\n#endif\n\nattribute vec4 p3d_Vertex;\nattribute vec4 p3d_Color;\nattribute vec2 p3d_MultiTexCoord0;\n#ifdef ENABLE_SKINNING\nattribute vec4 transform_weight;\nattribute vec4 transform_index;\n#endif\n\n\nvarying vec4 v_color;\nvarying vec2 v_texcoord;\n\nvoid main() {\n#ifdef ENABLE_SKINNING\n    mat4 skin_matrix = (\n        p3d_TransformTable[int(transform_index.x)] * transform_weight.x +\n        p3d_TransformTable[int(transform_index.y)] * transform_weight.y +\n        p3d_TransformTable[int(transform_index.z)] * transform_weight.z +\n        p3d_TransformTable[int(transform_index.w)] * transform_weight.w\n    );\n    vec4 vert_pos4 = skin_matrix * p3d_Vertex;\n#else\n    vec4 vert_pos4 = p3d_Vertex;\n#endif\n    v_color = p3d_Color;\n    v_texcoord = p3d_MultiTexCoord0;\n    gl_Position = p3d_ModelViewProjectionMatrix * vert_pos4;\n}\n',

'post.vert': '#version 120\n\nuniform mat4 p3d_ModelViewProjectionMatrix;\n\nattribute vec4 p3d_Vertex;\nattribute vec2 p3d_MultiTexCoord0;\n\nvarying vec2 v_texcoord;\n\nvoid main() {\n    v_texcoord = p3d_MultiTexCoord0;\n    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;\n}\n',

'skybox.vert': '#version 120\n\nuniform mat4 p3d_ProjectionMatrixInverse;\nuniform mat4 p3d_ModelViewMatrix;\n\nattribute vec4 p3d_Vertex;\n\nvarying vec3 v_texcoord;\n\nvoid main() {\n    mat3 inv_view = transpose(mat3(p3d_ModelViewMatrix));\n    v_texcoord = inv_view * (p3d_ProjectionMatrixInverse * p3d_Vertex).xyz;\n    gl_Position = p3d_Vertex;\n}\n',

# ============================================================================
# FRAGMENT SHADERS (unchanged from simplepbr)
# ============================================================================

'shadow.frag': '#version 120\n\n#ifdef USE_330\n    #define texture2D texture\n#endif\n\nuniform struct p3d_MaterialParameters {\n    vec4 baseColor;\n} p3d_Material;\n\nuniform vec4 p3d_ColorScale;\n\nuniform sampler2D p3d_TextureBaseColor;\nvarying vec4 v_color;\nvarying vec2 v_texcoord;\n\n#ifdef USE_330\nout vec4 o_color;\n#endif\n\nvoid main() {\n    vec4 base_color = p3d_Material.baseColor * v_color * p3d_ColorScale * texture2D(p3d_TextureBaseColor, v_texcoord);\n#ifdef USE_330\n    o_color = base_color;\n#else\n    gl_FragColor = base_color;\n#endif\n}\n',

'simplepbr.frag': "// Based on code from https://github.com/KhronosGroup/glTF-Sample-Viewer\n\n#version 120\n\n#ifndef MAX_LIGHTS\n    #define MAX_LIGHTS 8\n#endif\n\n#ifdef USE_330\n    #define texture2D texture\n    #define textureCube texture\n    #define textureCubeLod textureLod\n#else\n    #extension GL_ARB_shader_texture_lod : require\n#endif\n\nuniform struct p3d_MaterialParameters {\n    vec4 baseColor;\n    vec4 emission;\n    float roughness;\n    float metallic;\n} p3d_Material;\n\nuniform struct p3d_LightSourceParameters {\n    vec4 position;\n    vec4 diffuse;\n    vec4 specular;\n    vec3 attenuation;\n    vec3 spotDirection;\n    float spotCosCutoff;\n#ifdef ENABLE_SHADOWS\n    sampler2DShadow shadowMap;\n    mat4 shadowViewMatrix;\n#endif\n} p3d_LightSource[MAX_LIGHTS];\n\nuniform struct p3d_LightModelParameters {\n    vec4 ambient;\n} p3d_LightModel;\n\n#ifdef ENABLE_FOG\nuniform struct p3d_FogParameters {\n    vec4 color;\n    float density;\n} p3d_Fog;\n#endif\n\nuniform vec4 p3d_ColorScale;\nuniform vec4 p3d_TexAlphaOnly;\n\nuniform vec3 sh_coeffs[9];\nuniform vec3 camera_world_position;\n\nstruct FunctionParamters {\n    float n_dot_l;\n    float n_dot_v;\n    float n_dot_h;\n    float l_dot_h;\n    float v_dot_h;\n    float roughness;\n    float metallic;\n    vec3 reflection0;\n    vec3 diffuse_color;\n    vec3 specular_color;\n};\n\nuniform sampler2D p3d_TextureBaseColor;\nuniform sampler2D p3d_TextureMetalRoughness;\nuniform sampler2D p3d_TextureNormal;\nuniform sampler2D p3d_TextureEmission;\n\nuniform sampler2D brdf_lut;\nuniform samplerCube filtered_env_map;\nuniform float max_reflection_lod;\n\n#ifdef ENABLE_SHADOWS\nuniform float global_shadow_bias;\n#endif\n\nconst vec3 F0 = vec3(0.04);\nconst float PI = 3.141592653589793;\nconst float SPOTSMOOTH = 0.001;\nconst float LIGHT_CUTOFF = 0.001;\n\nvarying vec3 v_view_position;\nvarying vec3 v_world_position;\nvarying vec4 v_color;\nvarying vec2 v_texcoord;\nvarying mat3 v_view_tbn;\nvarying mat3 v_world_tbn;\n#ifdef ENABLE_SHADOWS\nvarying vec4 v_shadow_pos[MAX_LIGHTS];\n#endif\n\n#ifdef USE_330\nout vec4 o_color;\n#endif\n\n\n// Schlick's Fresnel approximation with Spherical Gaussian approximation to replace the power\nvec3 specular_reflection(FunctionParamters func_params) {\n    vec3 f0 = func_params.reflection0;\n    float v_dot_h= func_params.v_dot_h;\n    return f0 + (vec3(1.0) - f0) * pow(2.0, (-5.55473 * v_dot_h - 6.98316) * v_dot_h);\n}\n\nvec3 fresnelSchlickRoughness(float u, vec3 f0, float roughness) {\n    return f0 + (max(vec3(1.0 - roughness), f0) - f0) * pow(clamp(1.0 - u, 0.0, 1.0), 5.0);\n}\n\n// Smith GGX with optional fast sqrt approximation (see https://google.github.io/filament/Filament.md.html#materialsystem/specularbrdf/geometricshadowing(specularg))\nfloat visibility_occlusion(FunctionParamters func_params) {\n    float r = func_params.roughness;\n    float n_dot_l = func_params.n_dot_l;\n    float n_dot_v = func_params.n_dot_v;\n#ifdef SMITH_SQRT_APPROX\n    float ggxv = n_dot_l * (n_dot_v * (1.0 - r) + r);\n    float ggxl = n_dot_v * (n_dot_l * (1.0 - r) + r);\n#else\n    float r2 = r * r;\n    float ggxv = n_dot_l * sqrt(n_dot_v * n_dot_v * (1.0 - r2) + r2);\n    float ggxl = n_dot_v * sqrt(n_dot_l * n_dot_l * (1.0 - r2) + r2);\n#endif\n\n    float ggx = ggxv + ggxl;\n    if (ggx > 0.0) {\n        return 0.5 / ggx;\n    }\n    return 0.0;\n}\n\n// GGX/Trowbridge-Reitz\nfloat microfacet_distribution(FunctionParamters func_params) {\n    float roughness2 = func_params.roughness * func_params.roughness;\n    float f = (func_params.n_dot_h * func_params.n_dot_h) * (roughness2 - 1.0) + 1.0;\n    return roughness2 / (PI * f * f);\n}\n\n// Lambert\nfloat diffuse_function() {\n    return 1.0 / PI;\n}\n\n#ifdef ENABLE_SHADOWS\nfloat shadow_caster_contrib(sampler2DShadow shadowmap, vec4 shadowpos) {\n    vec3 light_space_coords = shadowpos.xyz / shadowpos.w;\n    light_space_coords.z -= global_shadow_bias;\n#ifdef USE_330\n    float shadow = texture(shadowmap, light_space_coords);\n#else\n    float shadow = shadow2D(shadowmap, light_space_coords).r;\n#endif\n    return shadow;\n}\n#endif\n\nvec3 get_normalmap_data() {\n#ifdef CALC_NORMAL_Z\n    vec2 normalXY = 2.0 * texture2D(p3d_TextureNormal, v_texcoord).rg - 1.0;\n    float normalZ = sqrt(clamp(1.0 - dot(normalXY, normalXY), 0.0, 1.0));\n    return vec3(\n        normalXY,\n        normalZ\n    );\n#else\n    return 2.0 * texture2D(p3d_TextureNormal, v_texcoord).rgb - 1.0;\n#endif\n}\n\nvec3 irradiance_from_sh(vec3 normal) {\n    return\n        + sh_coeffs[0] * 0.282095\n        + sh_coeffs[1] * 0.488603 * normal.x\n        + sh_coeffs[2] * 0.488603 * normal.z\n        + sh_coeffs[3] * 0.488603 * normal.y\n        + sh_coeffs[4] * 1.092548 * normal.x * normal.z\n        + sh_coeffs[5] * 1.092548 * normal.y * normal.z\n        + sh_coeffs[6] * 1.092548 * normal.y * normal.x\n        + sh_coeffs[7] * (0.946176 * normal.z * normal.z - 0.315392)\n        + sh_coeffs[8] * 0.546274 * (normal.x * normal.x - normal.y * normal.y);\n}\n\nvoid main() {\n    vec4 metal_rough = texture2D(p3d_TextureMetalRoughness, v_texcoord);\n    float metallic = clamp(p3d_Material.metallic * metal_rough.b, 0.0, 1.0);\n    float perceptual_roughness = clamp(p3d_Material.roughness * metal_rough.g,  0.0, 1.0);\n    float alpha_roughness = perceptual_roughness * perceptual_roughness;\n    vec4 base_color = p3d_Material.baseColor * v_color * p3d_ColorScale * (texture2D(p3d_TextureBaseColor, v_texcoord) + p3d_TexAlphaOnly);\n    vec3 diffuse_color = (base_color.rgb * (vec3(1.0) - F0)) * (1.0 - metallic);\n    vec3 spec_color = mix(F0, base_color.rgb, metallic);\n#ifdef USE_NORMAL_MAP\n    vec3 normalmap = get_normalmap_data();\n#else\n    vec3 normalmap = vec3(0, 0, 1);\n#endif\n    vec3 n = normalize(v_view_tbn * normalmap);\n    vec3 world_normal = normalize(v_world_tbn * normalmap);\n    vec3 v = normalize(-v_view_position);\n\n#ifdef USE_OCCLUSION_MAP\n    float ambient_occlusion = metal_rough.r;\n#else\n    float ambient_occlusion = 1.0;\n#endif\n\n#ifdef USE_EMISSION_MAP\n    vec3 emission = p3d_Material.emission.rgb * texture2D(p3d_TextureEmission, v_texcoord).rgb;\n#else\n    vec3 emission = vec3(0.0);\n#endif\n\n    vec4 color = vec4(vec3(0.0), base_color.a);\n\n    float n_dot_v = clamp(abs(dot(n, v)), 0.0, 1.0);\n\n    for (int i = 0; i < p3d_LightSource.length(); ++i) {\n        vec3 lightcol = p3d_LightSource[i].diffuse.rgb;\n\n        if (dot(lightcol, lightcol) < LIGHT_CUTOFF) {\n            continue;\n        }\n\n        vec3 light_pos = p3d_LightSource[i].position.xyz - v_view_position * p3d_LightSource[i].position.w;\n        vec3 l = normalize(light_pos);\n        vec3 h = normalize(l + v);\n        float dist = length(light_pos);\n        vec3 att_const = p3d_LightSource[i].attenuation;\n        float attenuation_factor = 1.0 / (att_const.x + att_const.y * dist + att_const.z * dist * dist);\n        float spotcos = dot(normalize(p3d_LightSource[i].spotDirection), -l);\n        float spotcutoff = p3d_LightSource[i].spotCosCutoff;\n        float shadowSpot = (spotcutoff > SPOTSMOOTH) ? smoothstep(spotcutoff-SPOTSMOOTH, spotcutoff+SPOTSMOOTH, spotcos) : 1.0;\n#ifdef ENABLE_SHADOWS\n        float shadow_caster = shadow_caster_contrib(p3d_LightSource[i].shadowMap, v_shadow_pos[i]);\n#else\n        float shadow_caster = 1.0;\n#endif\n        float shadow = shadowSpot * shadow_caster * attenuation_factor;\n\n        FunctionParamters func_params;\n        func_params.n_dot_l = clamp(dot(n, l), 0.0, 1.0);\n        func_params.n_dot_v = n_dot_v;\n        func_params.n_dot_h = clamp(dot(n, h), 0.0, 1.0);\n        func_params.l_dot_h = clamp(dot(l, h), 0.0, 1.0);\n        func_params.v_dot_h = clamp(dot(v, h), 0.0, 1.0);\n        func_params.roughness = alpha_roughness;\n        func_params.metallic =  metallic;\n        func_params.reflection0 = spec_color;\n        func_params.diffuse_color = diffuse_color;\n        func_params.specular_color = spec_color;\n\n        vec3 F = specular_reflection(func_params);\n        float V = visibility_occlusion(func_params); // V = G / (4 * n_dot_l * n_dot_v)\n        float D = microfacet_distribution(func_params);\n\n        vec3 diffuse_contrib = diffuse_color * diffuse_function();\n        vec3 spec_contrib = vec3(F * V * D);\n        color.rgb += func_params.n_dot_l * lightcol * (diffuse_contrib + spec_contrib) * shadow;\n    }\n\n    // Indirect diffuse + specular (IBL)\n    vec3 ibl_f = fresnelSchlickRoughness(n_dot_v, spec_color, perceptual_roughness);\n    vec3 ibl_kd = (1.0 - ibl_f) * (1.0 - metallic);\n    vec3 ibl_diff = base_color.rgb * max(irradiance_from_sh(world_normal), 0.0) * diffuse_function();\n\n    vec3 world_view = normalize(camera_world_position - v_world_position);\n    vec3 ibl_r = reflect(-world_view, world_normal);\n    vec2 env_brdf = texture2D(brdf_lut, vec2(n_dot_v, perceptual_roughness)).rg;\n    vec3 ibl_spec_color = textureCubeLod(filtered_env_map, ibl_r, perceptual_roughness * max_reflection_lod).rgb;\n    vec3 ibl_spec = ibl_spec_color * (ibl_f * env_brdf.x + env_brdf.y);\n    color.rgb += (ibl_kd * ibl_diff  + ibl_spec) * ambient_occlusion;\n\n    // Indirect diffuse (ambient light)\n    color.rgb += (diffuse_color + spec_color) * p3d_LightModel.ambient.rgb * ambient_occlusion;\n\n    // Emission\n    color.rgb += emission;\n\n#ifdef ENABLE_FOG\n    // Exponential fog\n    float fog_distance = length(v_view_position);\n    float fog_factor = clamp(1.0 / exp(fog_distance * p3d_Fog.density), 0.0, 1.0);\n    color = mix(p3d_Fog.color, color, fog_factor);\n#endif\n\n#ifdef USE_330\n    o_color = color;\n#else\n    gl_FragColor = color;\n#endif\n}\n",

'skybox.frag': '#version 120\n\n#ifdef USE_330\n    #define textureCube texture\n\n    out vec4 o_color;\n#endif\n\nuniform samplerCube skybox;\n\nvarying vec3 v_texcoord;\n\nvoid main() {\n    vec4 color = textureCube(skybox, v_texcoord);\n#ifdef USE_330\n    o_color = color;\n#else\n    gl_FragColor = color;\n#endif\n}\n',

# ============================================================================
# PAX3D BLOOM SHADERS (new)
# ============================================================================

# Bloom extract — scales scene luminance into bloom input.
# No hard threshold: everything blooms proportionally to its brightness.
# bloom_strength controls the overall feed into the bloom chain.
'bloom_extract.frag': """#version 120

#ifdef USE_330
    #define texture2D texture
#endif

uniform sampler2D scene_tex;
uniform float bloom_strength;

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

void main() {
    vec3 color = texture2D(scene_tex, v_texcoord).rgb;

    // Scale by bloom strength — no hard threshold, physically proportional
    color *= bloom_strength * 0.005;

    // Firefly clamp to prevent single bright pixels from dominating
    color = clamp(color, vec3(0.0), vec3(25000.0));

#ifdef USE_330
    o_color = vec4(color, 1.0);
#else
    gl_FragColor = vec4(color, 1.0);
#endif
}
""",

# Kawase dual-filter downsample (CoD:AW / Jimenez 2014).
# 13-tap kernel: 5 overlapping 2x2 box sub-kernels.
# Center box weighted 0.5, corner boxes weighted 0.125 each.
# 1.3x energy compensation per level to counteract resolution loss.
'bloom_downsample.frag': """#version 120

#ifdef USE_330
    #define texture2D texture
#endif

uniform sampler2D src_tex;
uniform vec2 texel_size;

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

void main() {
    vec2 uv = v_texcoord;
    vec2 ts = texel_size;

    // Center sample
    vec3 a = texture2D(src_tex, uv).rgb;

    // Inner ring (offset by 1 texel diagonally)
    vec3 b = texture2D(src_tex, uv + vec2(-ts.x, -ts.y)).rgb;
    vec3 c = texture2D(src_tex, uv + vec2( ts.x, -ts.y)).rgb;
    vec3 d = texture2D(src_tex, uv + vec2(-ts.x,  ts.y)).rgb;
    vec3 e = texture2D(src_tex, uv + vec2( ts.x,  ts.y)).rgb;

    // Outer ring (offset by 2 texels along axes and diagonals)
    vec3 f = texture2D(src_tex, uv + vec2(-2.0 * ts.x, -2.0 * ts.y)).rgb;
    vec3 g = texture2D(src_tex, uv + vec2(        0.0, -2.0 * ts.y)).rgb;
    vec3 h = texture2D(src_tex, uv + vec2( 2.0 * ts.x, -2.0 * ts.y)).rgb;
    vec3 i = texture2D(src_tex, uv + vec2(-2.0 * ts.x,         0.0)).rgb;
    vec3 j = texture2D(src_tex, uv + vec2( 2.0 * ts.x,         0.0)).rgb;
    vec3 k = texture2D(src_tex, uv + vec2(-2.0 * ts.x,  2.0 * ts.y)).rgb;
    vec3 l = texture2D(src_tex, uv + vec2(        0.0,  2.0 * ts.y)).rgb;
    vec3 m = texture2D(src_tex, uv + vec2( 2.0 * ts.x,  2.0 * ts.y)).rgb;

    // 13-tap Jimenez kernel: center box weight 0.5, four corner boxes 0.125 each
    // Center (a): 0.125, inner ring (b,c,d,e): 0.125 each of 4 = 0.5 total
    // Four corner 2x2 boxes: 0.03125 each of 4 samples = 0.125 per box
    vec3 result = a * 0.125;
    result += (b + c + d + e) * 0.125;
    result += (f + g + b + i) * 0.03125;  // top-left box
    result += (g + h + c + j) * 0.03125;  // top-right box
    result += (i + b + k + l) * 0.03125;  // bottom-left box
    result += (c + j + l + m) * 0.03125;  // bottom-right box

    // Energy compensation — boost to counteract resolution halving
    result *= 1.3;

#ifdef USE_330
    o_color = vec4(result, 1.0);
#else
    gl_FragColor = vec4(result, 1.0);
#endif
}
""",

# 9-tap tent filter upsample with per-mip color tinting.
# Tent weights: center 4, edges 2, corners 1, all /16.
# Adds tinted upsampled result to accumulated bloom from previous level.
'bloom_upsample.frag': """#version 120

#ifdef USE_330
    #define texture2D texture
#endif

uniform sampler2D src_tex;
uniform sampler2D bloom_accum_tex;
uniform vec2 texel_size;
uniform vec3 mip_tint;

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

void main() {
    vec2 uv = v_texcoord;
    vec2 ts = texel_size;

    // 9-tap tent filter (3x3 kernel)
    // Weights: corners=1, edges=2, center=4, total=16
    vec3 s = vec3(0.0);
    s += texture2D(src_tex, uv + vec2(-ts.x, -ts.y)).rgb * 1.0;  // top-left
    s += texture2D(src_tex, uv + vec2(  0.0, -ts.y)).rgb * 2.0;  // top
    s += texture2D(src_tex, uv + vec2( ts.x, -ts.y)).rgb * 1.0;  // top-right
    s += texture2D(src_tex, uv + vec2(-ts.x,   0.0)).rgb * 2.0;  // left
    s += texture2D(src_tex, uv                      ).rgb * 4.0;  // center
    s += texture2D(src_tex, uv + vec2( ts.x,   0.0)).rgb * 2.0;  // right
    s += texture2D(src_tex, uv + vec2(-ts.x,  ts.y)).rgb * 1.0;  // bottom-left
    s += texture2D(src_tex, uv + vec2(  0.0,  ts.y)).rgb * 2.0;  // bottom
    s += texture2D(src_tex, uv + vec2( ts.x,  ts.y)).rgb * 1.0;  // bottom-right
    s /= 16.0;

    // Apply per-mip color tint (artistic warm-cool bloom fringe)
    s *= mip_tint;

    // Accumulate with previous upsample level
    vec3 accum = texture2D(bloom_accum_tex, uv).rgb;
    vec3 result = s + accum;

#ifdef USE_330
    o_color = vec4(result, 1.0);
#else
    gl_FragColor = vec4(result, 1.0);
#endif
}
""",

# ============================================================================
# PAX3D TONEMAP SHADER (modified — replaces simplepbr's Hejl-Dawson)
# ============================================================================

# Tonemap + bloom composite.
# Supports ACES (default), Reinhard, Uncharted2, and legacy Hejl-Dawson.
# Bloom is composited additively before tonemapping for physically correct rolloff.
'tonemap.frag': """#version 120

#ifdef USE_330
    #define texture2D texture
    #define texture3D texture
#endif

uniform sampler2D tex;
#ifdef ENABLE_BLOOM
    uniform sampler2D bloom_tex;
    uniform float bloom_intensity;
#endif
#ifdef USE_SDR_LUT
    uniform sampler3D sdr_lut;
    uniform float sdr_lut_factor;
#endif
uniform float exposure;
uniform int tonemap_operator;

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

// ACES filmic tonemap (Stephen Hill's fitted approximation)
vec3 aces_tonemap(vec3 x) {
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

// Reinhard tonemap
vec3 reinhard_tonemap(vec3 x) {
    return x / (x + vec3(1.0));
}

// Uncharted 2 tonemap (John Hable)
vec3 uncharted2_partial(vec3 x) {
    float A = 0.15;  // shoulder strength
    float B = 0.50;  // linear strength
    float C = 0.10;  // linear angle
    float D = 0.20;  // toe strength
    float E = 0.02;  // toe numerator
    float F = 0.30;  // toe denominator
    return ((x * (A * x + C * B) + D * E) / (x * (A * x + B) + D * F)) - E / F;
}

vec3 uncharted2_tonemap(vec3 x) {
    float W = 11.2;  // linear white point
    vec3 curr = uncharted2_partial(x * 2.0);
    vec3 white_scale = vec3(1.0) / uncharted2_partial(vec3(W));
    return curr * white_scale;
}

// Hejl-Dawson tonemap (legacy simplepbr default, includes sRGB baked in)
vec3 hejl_dawson_tonemap(vec3 x) {
    x = max(vec3(0.0), x - vec3(0.004));
    return (x * (vec3(6.2) * x + vec3(0.5))) / (x * (vec3(6.2) * x + vec3(1.7)) + vec3(0.06));
}

void main() {
    vec4 tex_color = texture2D(tex, v_texcoord);
    vec3 color = tex_color.rgb;

    // Bloom composite (additive, before tonemapping for correct rolloff)
#ifdef ENABLE_BLOOM
    vec3 bloom = texture2D(bloom_tex, v_texcoord).rgb;
    color += bloom * bloom_intensity;
#endif

    // Exposure
    color *= exposure;

    // Tonemap
    // 0 = ACES (default), 1 = Reinhard, 2 = Uncharted2, 3 = Hejl-Dawson (legacy)
    if (tonemap_operator == 1) {
        color = reinhard_tonemap(color);
        color = pow(color, vec3(1.0 / 2.2));  // linear -> sRGB
    } else if (tonemap_operator == 2) {
        color = uncharted2_tonemap(color);
        color = pow(color, vec3(1.0 / 2.2));  // linear -> sRGB
    } else if (tonemap_operator == 3) {
        color = hejl_dawson_tonemap(color);
        // Hejl-Dawson bakes in sRGB gamma — no additional pow needed
    } else {
        // Default: ACES
        color = aces_tonemap(color);
        color = pow(color, vec3(1.0 / 2.2));  // linear -> sRGB
    }

#ifdef USE_SDR_LUT
    vec3 lut_size = vec3(textureSize(sdr_lut, 0));
    vec3 lut_uvw = (color.rgb * float(lut_size - 1.0) + 0.5) / lut_size;
    vec3 lut_color = texture3D(sdr_lut, lut_uvw).rgb;
    color = mix(color, lut_color, sdr_lut_factor);
#endif

#ifdef USE_330
    o_color = vec4(color, tex_color.a);
#else
    gl_FragColor = vec4(color, tex_color.a);
#endif
}
""",

}
