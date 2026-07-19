#version 120

uniform mat4 p3d_ModelViewProjectionMatrix;
#ifdef ENABLE_SKINNING
// Same MAX_SKINNING_BONES knob as pax_pbr.vert (Session S) — the depth
// pass must carry the same palette or big rigs would shadow wrong.
#ifndef MAX_SKINNING_BONES
    #define MAX_SKINNING_BONES 100
#endif
uniform mat4 p3d_TransformTable[MAX_SKINNING_BONES];
#endif

attribute vec4 p3d_Vertex;
attribute vec4 p3d_Color;
attribute vec2 p3d_MultiTexCoord0;
#ifdef ENABLE_SKINNING
attribute vec4 transform_weight;
attribute vec4 transform_index;
#endif
#ifdef INSTANCING
// Same instancing discipline as pax_pbr.vert (ER-002): the depth pass
// must apply the same per-instance transform or instanced casters would
// all shadow from the node origin. Non-instanced casters get the
// identity fallback — behavior-identical to the pre-INSTANCING compile.
attribute mat4x3 p3d_InstanceMatrix;
#endif


varying vec4 v_color;
varying vec2 v_texcoord;

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
