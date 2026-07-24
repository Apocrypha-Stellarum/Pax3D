#version 330
// Pax3D light halo fragment (Session AF, ER-013).
//
// Soft radial falloff, additive HDR: the quad draws with
// ColorBlendAttrib(add, one, one), depth-TESTED against the scene
// (occlusion by hulls/terrain is the depth test — no occluder lists)
// but never depth-written. The falloff (1 - r^2)^2 is exactly 1.0 at
// the center with zero slope, so the paxtest center-pixel analytic is
// immune to half-pixel sampling offsets.
//
// u_emission_factor is the pipeline's per-node emission registry input
// (root default 1,1,1): a halo parented under a set_blink circuit node
// INHERITS the blink envelope — halos flash in sync with their bulbs
// with no extra wiring (the ER-013 composition contract).

uniform vec3 u_halo_color;      // linear color
uniform float u_halo_intensity; // HDR scale (feeds bloom when > 1)
uniform vec3 u_emission_factor; // inherited blink/emission envelope

in vec2 v_corner;
#ifdef LOG_DEPTH
uniform float u_log_depth_coef;
in float v_log_depth_w;
#endif

out vec4 o_color;

void main() {
    float r2 = dot(v_corner, v_corner);
    if (r2 >= 1.0) {
        discard;
    }
    float fall = 1.0 - r2;
    fall *= fall;
    vec3 c = u_halo_color * u_halo_intensity * u_emission_factor * fall;
    o_color = vec4(c, 0.0);
#ifdef LOG_DEPTH
    gl_FragDepth = log2(v_log_depth_w) * u_log_depth_coef;
#endif
}
