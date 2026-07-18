#version 120
// Pax3D SSAO — first slice (Session S).
//
// Alchemy/SAO-style screen-space ambient obscurance from the DEPTH
// BUFFER ALONE (normals reconstructed from depth derivatives — zero
// scene-shader changes, so default rendering stays byte-identical by
// construction). Spiral tap kernel around each pixel; each tap's
// view-space offset vector v contributes
//
//     max(0, dot(v, n) - bias * z) / (dot(v, v) + eps)
//
// (McGuire et al., "Scalable Ambient Obscurance", HPG 2012 — the
// obscurance estimator; the sum is normalized by radius so AO is
// scene-scale-invariant). On a FLAT surface every tap lies in the
// tangent plane: dot(v, n) == 0 up to depth quantization, which the
// depth-proportional bias absorbs — so planes produce AO == 1.0
// EXACTLY, and the tonemap multiply is an exact no-op (the paxtest
// plane gate).
//
// Depth conventions: standard perspective depth linearized via
// near/far; under LOG_DEPTH the PBR shader wrote
// gl_FragDepth = log2(1 + w) * u_log_depth_coef, inverted here.
// Background (cleared depth == 1.0) always yields AO 1.

#ifdef USE_330
    #define texture2D texture
#endif

uniform sampler2D depth_tex;
uniform vec2 u_proj_tan;        // tan(fov_x/2), tan(fov_y/2)
uniform vec2 u_near_far;        // lens near, far (non-log path)
uniform float u_log_depth_coef; // 1/log2(1+far) (log path; unused otherwise)
uniform float u_ao_radius;      // world-unit sampling radius
uniform float u_ao_intensity;   // obscurance strength (0 = exact no-op)
uniform float u_ao_bias;        // depth-proportional self-occlusion bias
uniform vec2 u_texel;           // 1/width, 1/height of the depth buffer

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

#ifndef AO_SAMPLES
#define AO_SAMPLES 12
#endif

#define AO_SPIRAL_TURNS 7.0
#define AO_PI2 6.28318530718

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

vec3 view_pos(vec2 uv) {
    float z = linear_depth(texture2D(depth_tex, uv).x);
    vec2 ndc = uv * 2.0 - 1.0;
    return vec3(ndc * u_proj_tan * z, z);
}

// Interleaved gradient noise (Jimenez 2014) — per-pixel kernel rotation
float ign(vec2 p) {
    vec3 magic = vec3(0.06711056, 0.00583715, 52.9829189);
    return fract(magic.z * fract(dot(p, magic.xy)));
}

void main() {
    float d0 = texture2D(depth_tex, v_texcoord).x;
    vec3 P = view_pos(v_texcoord);
    // Face-the-camera normal from depth derivatives (computed BEFORE any
    // branch — derivatives are undefined in non-uniform control flow)
    vec3 n = cross(dFdx(P), dFdy(P));
    float nlen = length(n);
    n = (nlen > 1e-12) ? (n / nlen) : vec3(0.0, 0.0, -1.0);
    if (dot(n, P) > 0.0) n = -n;

    // Screen-space footprint of the world-space radius at this depth
    vec2 r_uv = vec2(u_ao_radius) / (2.0 * u_proj_tan * max(P.z, 1e-6));
    float rot = AO_PI2 * ign(gl_FragCoord.xy);

    float occ = 0.0;
    for (int i = 0; i < AO_SAMPLES; i++) {
        float a = (float(i) + 0.5) / float(AO_SAMPLES);
        float ang = AO_PI2 * a * AO_SPIRAL_TURNS + rot;
        vec2 uv = v_texcoord + vec2(cos(ang), sin(ang)) * a * r_uv;
        uv = clamp(uv, u_texel * 0.5, 1.0 - u_texel * 0.5);
        vec3 v = view_pos(uv) - P;
        occ += max(0.0, dot(v, n) - u_ao_bias * P.z)
               / (dot(v, v) + 1e-4);
    }
    // Radius-normalized obscurance -> scale-invariant AO
    float ao = clamp(1.0 - u_ao_intensity * u_ao_radius
                           * (2.0 / float(AO_SAMPLES)) * occ, 0.0, 1.0);

    // Background (cleared depth): no geometry, no obscurance
    ao = mix(ao, 1.0, step(0.9999999, d0));

    vec4 result = vec4(ao, ao, ao, 1.0);
#ifdef USE_330
    o_color = result;
#else
    gl_FragColor = result;
#endif
}
