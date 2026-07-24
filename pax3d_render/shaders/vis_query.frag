#version 330
// Pax3D depth-tap visibility query (Session AF — the lens-flare
// occluder retirement).
//
// Renders into a VIS_MAX_QUERIES x 1 buffer: fragment x = query index.
// Each query samples the SCENE DEPTH buffer in a spiral disc of
// radius_px around a target's projected screen position and reports
// the fraction of taps where the scene is NOT in front of the target —
// i.e. how visible the target is. Any depth-writing geometry occludes
// (hull walls from inside, ships, planets, terrain); partial coverage
// fades smoothly. The game multiplies its sprite flare by this instead
// of maintaining analytic occluder lists.
//
// The pass renders BEFORE the scene buffer (pipeline sorts it first),
// reading LAST frame's depth — so the RTM_copy_ram readback stalls on
// nothing but this quad, and results are ~2 frames latent.
//
// u_queries[i] = (u, v, target_eye_depth * 0.995, radius_px); a
// non-positive depth forces visibility 0 (target behind the camera or
// off-frustum). The 0.995 pre-scale (applied pipeline-side) keeps a
// target that itself writes depth (a sun billboard) from occluding its
// own query. u_query_far[i]: scene depth at or beyond this counts as
// OPEN SKY (set it below your sky-dome radius; default just under the
// lens far plane). Cleared depth (1.0) always counts open.

uniform sampler2D depth_tex;
uniform vec4 u_queries[VIS_MAX_QUERIES];
uniform float u_query_far[VIS_MAX_QUERIES];
uniform vec2 u_texel;           // 1 / depth buffer size
uniform vec2 u_near_far;        // lens near/far (non-log path)
uniform float u_log_depth_coef; // 1/log2(1+far) (log path)

in vec2 v_texcoord;

out vec4 o_color;

#ifndef VIS_TAPS
#define VIS_TAPS 16
#endif

#define VIS_PI2 6.28318530718
#define VIS_SPIRAL_TURNS 5.0

float linear_depth(float d) {
#ifdef LOG_DEPTH
    // gl_FragDepth = log2(1 + w) * coef  =>  w = 2^(d/coef) - 1
    return exp2(d / max(u_log_depth_coef, 1e-9)) - 1.0;
#else
    float n = u_near_far.x;
    float f = u_near_far.y;
    return (n * f) / max(f - d * (f - n), 1e-9);
#endif
}

void main() {
    int idx = clamp(int(gl_FragCoord.x), 0, VIS_MAX_QUERIES - 1);
    vec4 q = u_queries[idx];
    if (q.z <= 0.0) {
        o_color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    float vis = 0.0;
    for (int i = 0; i < VIS_TAPS; ++i) {
        // sqrt(a) radius ramp = uniform tap density over the disc
        float a = (float(i) + 0.5) / float(VIS_TAPS);
        float ang = VIS_PI2 * a * VIS_SPIRAL_TURNS;
        vec2 uv = q.xy + vec2(cos(ang), sin(ang)) * sqrt(a) * q.w * u_texel;
        float d = texture(depth_tex, clamp(uv, vec2(0.0), vec2(1.0))).x;
        float scene = linear_depth(d);
        float open = max(step(0.9999999, d),          // cleared: open sky
                         step(u_query_far[idx], scene)); // beyond horizon
        vis += max(open, step(q.z, scene));           // scene behind target
    }
    vis /= float(VIS_TAPS);
    o_color = vec4(vis, vis, vis, 1.0);
}
