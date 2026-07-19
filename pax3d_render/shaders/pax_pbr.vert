#version 120

#ifndef MAX_LIGHTS
    #define MAX_LIGHTS 8
#endif

#ifdef USE_330
    #define texture2D texture
#endif

#ifdef ENABLE_SHADOWS
uniform struct p3d_LightSourceParameters {
    vec4 position;
    vec4 diffuse;
    vec4 specular;
    vec3 attenuation;
    vec3 spotDirection;
    float spotCosCutoff;
    sampler2DShadow shadowMap;
    mat4 shadowViewMatrix;
} p3d_LightSource[MAX_LIGHTS];
#endif

#ifdef ENABLE_SKINNING
// Session S: the joint-palette ceiling is a knob (max_skinning_bones).
// The GL layer identity-pads tables shorter than the declaration
// (engine fact #10), so raising it is safe for small rigs; the cost is
// vertex-uniform budget (16 components per mat4 — 100 = 1600, 200 =
// 3200; typical desktop GL_MAX_VERTEX_UNIFORM_COMPONENTS is 4096).
#ifndef MAX_SKINNING_BONES
    #define MAX_SKINNING_BONES 100
#endif
uniform mat4 p3d_TransformTable[MAX_SKINNING_BONES];
#endif

uniform mat4 p3d_ProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ViewMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat3 p3d_NormalMatrix;
uniform mat4 p3d_TextureMatrix;
uniform mat4 p3d_ModelMatrixInverseTranspose;

attribute vec4 p3d_Vertex;
attribute vec4 p3d_Color;
attribute vec3 p3d_Normal;
attribute vec4 p3d_Tangent;
attribute vec2 p3d_MultiTexCoord0;
#ifdef ENABLE_SKINNING
attribute vec4 transform_weight;
attribute vec4 transform_index;
#endif
#ifdef GPU_MORPHS
// Session Z: morph targets on the GPU (fact #15's missing half — the
// hardware-skinning path used to drop sliders). Deltas live in a
// per-vdata RGB32F data texture: width = vertex rows, height =
// 2 * targets, position delta at row 2t, normal delta at row 2t+1.
// morph_index is a plain float32 column (the vertex's own row id) —
// one addressing mechanism on BOTH GLSL baselines instead of
// gl_VertexID, which 120 does not have. Nearest filtering + texel
// centers make every fetch exact (the ER-003 data-texture pattern).
#ifndef MORPH_LIVE
    #define MORPH_LIVE 16
#endif
uniform sampler2D u_morph_tex;
uniform vec2 u_morph_texel;        // (1/W, 1/H)
// x = target row t, y = slider weight. The pipeline fills live slots
// first (compact) so the shader may stop at the first zero weight.
uniform vec2 u_morphs[MORPH_LIVE];
attribute float morph_index;
#endif
#ifdef INSTANCING
// Per-instance transform under an InstancedNode (ER-002). The engine
// feeds this as a divisor-1 vertex attrib from InstanceList
// (cullableObject munge_instances); draws WITHOUT an instance list get
// the identity (glShaderContext fallback), so this declaration is safe
// for every draw that reaches an INSTANCING compile. Panda row-major
// affine memory reads as GL column-major mat4x3 with translation in
// column 3 — M * vec4(v, 1) is the correct application.
attribute mat4x3 p3d_InstanceMatrix;
#endif


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
varying float v_log_depth_w;
#endif

void main() {
    vec4 base_vertex = p3d_Vertex;
    vec3 base_normal = p3d_Normal;
#ifdef GPU_MORPHS
    // Morphs displace the bind pose BEFORE skinning (glTF semantics,
    // and what the CPU path does via animate_vertices). Tangents keep
    // their base values — the loader ships no tangent deltas
    // (measured: vertex.morph.* + normal.morph.* only). base_normal
    // stays unnormalized here exactly like the CPU path's column sum;
    // the normalize() calls below handle both paths identically.
    float morph_u = (morph_index + 0.5) * u_morph_texel.x;
    for (int i = 0; i < MORPH_LIVE; ++i) {
        float w = u_morphs[i].y;
        if (w == 0.0) break;   // slots are compact by contract
        float v_pos = (u_morphs[i].x * 2.0 + 0.5) * u_morph_texel.y;
        base_vertex.xyz += w * texture2D(u_morph_tex,
                                         vec2(morph_u, v_pos)).xyz;
        base_normal += w * texture2D(u_morph_tex,
                                     vec2(morph_u,
                                          v_pos + u_morph_texel.y)).xyz;
    }
#endif
#ifdef ENABLE_SKINNING
    mat4 skin_matrix = (
        p3d_TransformTable[int(transform_index.x)] * transform_weight.x +
        p3d_TransformTable[int(transform_index.y)] * transform_weight.y +
        p3d_TransformTable[int(transform_index.z)] * transform_weight.z +
        p3d_TransformTable[int(transform_index.w)] * transform_weight.w
    );
    vec4 model_position = skin_matrix * base_vertex;
    mat3 skin_matrix3 = mat3(skin_matrix);
    vec3 model_normal = skin_matrix3 * base_normal;
    vec3 model_tangent = skin_matrix3 * p3d_Tangent.xyz;
#else
    vec4 model_position = base_vertex;
    vec3 model_normal = base_normal;
    vec3 model_tangent = p3d_Tangent.xyz;
#endif
#ifdef INSTANCING
    // Instance transform applies between the node transform (inside
    // p3d_ModelViewMatrix / p3d_ModelMatrix) and the vertex — which is
    // why children under an InstancedNode must be flattened (a child
    // transform would land on the wrong side of the instance one).
    // Skinning composes first: joint space -> model -> instance.
    model_position = vec4(p3d_InstanceMatrix * model_position, 1.0);
    mat3 instance_rot = mat3(p3d_InstanceMatrix[0],
                             p3d_InstanceMatrix[1],
                             p3d_InstanceMatrix[2]);
    // Rotation + UNIFORM scale assumed (normalize() strips the scale,
    // same contract as the world_normal_mat note below).
    model_normal = instance_rot * model_normal;
    model_tangent = instance_rot * model_tangent;
#endif
    vec4 view_position = p3d_ModelViewMatrix * model_position;
    v_view_position = (view_position).xyz;
    v_world_position = (p3d_ModelMatrix * model_position).xyz;
    v_color = p3d_Color;
    v_texcoord = (p3d_TextureMatrix * vec4(p3d_MultiTexCoord0, 0, 1)).xy;
#ifdef ENABLE_SHADOWS
    for (int i = 0; i < p3d_LightSource.length(); ++i) {
        v_shadow_pos[i] = p3d_LightSource[i].shadowViewMatrix * view_position;
    }
#endif

    vec3 view_normal = normalize(p3d_NormalMatrix * model_normal);
    vec3 view_tangent = normalize(p3d_NormalMatrix * model_tangent);
    vec3 view_bitangent = cross(view_normal, view_tangent) * p3d_Tangent.w;
    v_view_tbn = mat3(
        view_tangent,
        view_bitangent,
        view_normal
    );

    // World-space normals via mat3(p3d_ModelMatrix).
    // For uniform scale (planets, moons, GLTF models), mat3(ModelMatrix)
    // differs from mat3(InverseTranspose) only by a scalar factor that
    // normalize() removes.
    mat3 world_normal_mat = mat3(p3d_ModelMatrix);
    vec3 world_normal = normalize(world_normal_mat * model_normal);

    // Pass world normal directly — TBN may contain NaN when geometry
    // lacks tangent data (e.g. procedural planet spheres use V3n3t2 format).
    v_world_normal = world_normal;

    // World-space TBN: only valid when geometry provides tangent data.
    // When p3d_Tangent is zero (no tangent column), normalize() produces
    // NaN which contaminates the TBN matrix.  The fragment shader uses
    // v_world_normal as fallback when USE_NORMAL_MAP is off.
    vec3 world_tangent = normalize(world_normal_mat * model_tangent);
    vec3 world_bitangent = cross(world_normal, world_tangent) * p3d_Tangent.w;
    v_world_tbn = mat3(
            world_tangent,
            world_bitangent,
            world_normal
    );

    gl_Position = p3d_ProjectionMatrix * view_position;
#ifdef LOG_DEPTH
    // Logarithmic depth (R4.1): pass 1+w to the fragment shader, which
    // writes gl_FragDepth = log2(1+w) * u_log_depth_coef. Fragment-level
    // (not vertex-level) so depth stays correct across long triangles.
    v_log_depth_w = 1.0 + gl_Position.w;
#endif
}
