#version 120
// Pax3D lens flare (Session S — the R5 lens-polish finale).
//
// Pseudo lens flare sourced from the BLOOM BRIGHT EXTRACT (a blurred
// downsample level), John-Chapman-style: each ghost samples the source
// at a center-scaled UV, so a bright source at p produces ghost blobs
// at analytically predictable positions
//
//     x_k = center + (p - center) / c_k
//
// (negative c_k = across the center — the classic internal-reflection
// look). Sourcing from the extract makes occlusion implicit: a sun
// hidden behind a hull contributes no extract energy, so its flare
// vanishes with it, and ANY bright emitter (twin suns, engine trails)
// flares consistently. Ghost weights fade with the SAMPLE's distance
// from the optical center. Screen-space lens dirt modulates the
// result (u_dirt_strength 0 = clean lens, exact).

#ifdef USE_330
    #define texture2D texture
#endif

uniform sampler2D src_tex;      // blurred bright extract (bloom down chain)
uniform sampler2D u_dirt_tex;   // screen-space dirt (1x1 white = clean)
uniform float u_dirt_strength;

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

vec3 ghost_sample(vec2 uv, float c) {
    vec2 s = vec2(0.5) + (uv - vec2(0.5)) * c;
    // Fade samples originating far off-center: kills edge streaks and
    // keeps the flare energy tied to sources near the view axis.
    float w = pow(max(0.0, 1.0 - length(s - vec2(0.5)) / 0.75), 2.0);
    return texture2D(src_tex, clamp(s, 0.0, 1.0)).rgb * w;
}

void main() {
    vec3 flare = vec3(0.0);
    // Four ghosts, mixed signs/scales, subtle per-ghost tints. The
    // paxtest predicts blob positions from these exact constants —
    // change them only together with test_lens_flare.
    flare += ghost_sample(v_texcoord, -2.0) * vec3(1.0, 0.8, 0.6);
    flare += ghost_sample(v_texcoord, -3.5) * vec3(0.7, 0.9, 1.0);
    flare += ghost_sample(v_texcoord,  1.7) * vec3(0.9, 1.0, 0.8) * 0.7;
    flare += ghost_sample(v_texcoord,  3.0) * vec3(1.0, 0.7, 0.9) * 0.5;

    vec3 dirt = mix(vec3(1.0), texture2D(u_dirt_tex, v_texcoord).rgb,
                    u_dirt_strength);
    vec4 result = vec4(flare * dirt, 1.0);
#ifdef USE_330
    o_color = result;
#else
    gl_FragColor = result;
#endif
}
