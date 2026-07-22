// Pax3D orbital scattering vertex shader (R5.5)
//
// Minimal transform for the per-planet atmosphere billboard quads. The
// fragment shader reconstructs the world-space view ray per pixel from
// v_world_position, so the only job here is placing the quad and keeping
// its depth in the same space as the scene (LOG_DEPTH must match the PBR
// shader's convention or the quads would depth-test wrongly against
// planet geometry).

#version 330

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;

in vec4 p3d_Vertex;

out vec3 v_world_position;
#ifdef LOG_DEPTH
out float v_log_depth_w;
#endif

void main() {
    v_world_position = (p3d_ModelMatrix * p3d_Vertex).xyz;
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
#ifdef LOG_DEPTH
    v_log_depth_w = 1.0 + gl_Position.w;
#endif
}
