#version 330
// Pax3D light halo (Session AF, ER-013 — distance-readable light points).
//
// A camera-facing quad expanded in VIEW SPACE around the node's origin:
// true world size (u_halo_size, the diameter) close up, clamping to
// u_halo_min_px pixels on screen at distance so a blinking nav bulb
// stays readable at km ranges. The pixels-per-world-unit factor is
// derived from the projection matrix's [1][1] element and the clip-w at
// the node's depth, which is exact for BOTH perspective (w = -z) and
// orthographic (w = 1) lenses — the paxtest ortho scenes and the game's
// perspective camera share one formula.
//
// The quad is authored as a unit card spanning [-1, 1]^2; p3d_Vertex.xz
// carries the corner. Model/parent rotation is deliberately ignored
// (view-space expansion = always camera-facing); only the node's
// POSITION matters.

uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ProjectionMatrix;
uniform float u_halo_size;     // world-space diameter at the node
uniform float u_halo_min_px;   // minimum on-screen diameter, pixels
uniform float u_halo_vp_h;     // viewport height, pixels (pipeline-pushed)

in vec4 p3d_Vertex;

out vec2 v_corner;             // [-1, 1]^2 across the quad
#ifdef LOG_DEPTH
out float v_log_depth_w;
#endif

void main() {
    vec2 corner = p3d_Vertex.xz;
    v_corner = corner;
    vec3 center = (p3d_ModelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
    float w_clip = (p3d_ProjectionMatrix * vec4(center, 1.0)).w;
    float px_per_world = p3d_ProjectionMatrix[1][1] * u_halo_vp_h
                         / (2.0 * max(w_clip, 1e-6));
    float size = max(u_halo_size,
                     u_halo_min_px / max(px_per_world, 1e-9));
    vec3 pos = center + vec3(corner * 0.5 * size, 0.0);
    gl_Position = p3d_ProjectionMatrix * vec4(pos, 1.0);
#ifdef LOG_DEPTH
    // Same encoding as pax_pbr.vert: the fragment writes
    // gl_FragDepth = log2(1 + w) * u_log_depth_coef so the halo's
    // depth TEST composes with log-depth scene geometry.
    v_log_depth_w = 1.0 + gl_Position.w;
#endif
}
