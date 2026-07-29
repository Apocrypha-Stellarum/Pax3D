// Shadow depth-pass vertex shader.
//
// Derived from panda3d-simplepbr 0.13.1 (shadow.vert), Copyright (c) 2019,
// Mitchell Stokes, used under the BSD 3-Clause License. See
// THIRD_PARTY_NOTICES.md at the repository root.

#version 330

uniform mat4 p3d_ModelViewProjectionMatrix;
#ifdef ENABLE_SKINNING
// Same MAX_SKINNING_BONES knob as pax_pbr.vert (Session S) — the depth
// pass must carry the same palette or big rigs would shadow wrong.
#ifndef MAX_SKINNING_BONES
    #define MAX_SKINNING_BONES 100
#endif
uniform mat4 p3d_TransformTable[MAX_SKINNING_BONES];
#endif

in vec4 p3d_Vertex;
in vec4 p3d_Color;
in vec2 p3d_MultiTexCoord0;
#ifdef ENABLE_SKINNING
in vec4 transform_weight;
in vec4 transform_index;
#endif
#ifdef INSTANCING
// Same instancing discipline as pax_pbr.vert (ER-002): the depth pass
// must apply the same per-instance transform or instanced casters would
// all shadow from the node origin. Non-instanced casters get the
// identity fallback — behavior-identical to the pre-INSTANCING compile.
in mat4x3 p3d_InstanceMatrix;
#endif


out vec4 v_color;
out vec2 v_texcoord;

void main() {
#ifdef ENABLE_SKINNING
    mat4 skin_matrix = (
        p3d_TransformTable[int(transform_index.x)] * transform_weight.x +
        p3d_TransformTable[int(transform_index.y)] * transform_weight.y +
        p3d_TransformTable[int(transform_index.z)] * transform_weight.z +
        p3d_TransformTable[int(transform_index.w)] * transform_weight.w
    );
    vec4 vert_pos4 = skin_matrix * p3d_Vertex;
#else
    vec4 vert_pos4 = p3d_Vertex;
#endif
#ifdef INSTANCING
    vert_pos4 = vec4(p3d_InstanceMatrix * vert_pos4, 1.0);
#endif
    v_color = p3d_Color;
    v_texcoord = p3d_MultiTexCoord0;
    gl_Position = p3d_ModelViewProjectionMatrix * vert_pos4;
}
