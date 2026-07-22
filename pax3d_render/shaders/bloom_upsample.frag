#version 330


uniform sampler2D src_tex;         // same-res downsample (this mip's detail)
uniform sampler2D bloom_accum_tex; // coarser accumulated result (half res)
uniform vec2 texel_size;           // one texel of bloom_accum_tex
uniform vec3 mip_tint;

in vec2 v_texcoord;

out vec4 o_color;

void main() {
    vec2 uv = v_texcoord;
    vec2 ts = texel_size;

    // 9-tap tent filter (3x3, corners=1 edges=2 center=4, /16) applied to
    // the COARSER accumulator — the texture being magnified. A single
    // bilinear tap here is what produced the blocky halo (F3); Jimenez
    // tents the coarser mip on the way up.
    vec3 accum = vec3(0.0);
    accum += texture(bloom_accum_tex, uv + vec2(-ts.x, -ts.y)).rgb * 1.0;
    accum += texture(bloom_accum_tex, uv + vec2(  0.0, -ts.y)).rgb * 2.0;
    accum += texture(bloom_accum_tex, uv + vec2( ts.x, -ts.y)).rgb * 1.0;
    accum += texture(bloom_accum_tex, uv + vec2(-ts.x,   0.0)).rgb * 2.0;
    accum += texture(bloom_accum_tex, uv                      ).rgb * 4.0;
    accum += texture(bloom_accum_tex, uv + vec2( ts.x,   0.0)).rgb * 2.0;
    accum += texture(bloom_accum_tex, uv + vec2(-ts.x,  ts.y)).rgb * 1.0;
    accum += texture(bloom_accum_tex, uv + vec2(  0.0,  ts.y)).rgb * 2.0;
    accum += texture(bloom_accum_tex, uv + vec2( ts.x,  ts.y)).rgb * 1.0;
    accum /= 16.0;

    // This mip's detail, same resolution as the target — one tap is exact.
    // Per-mip color tint (artistic warm-cool bloom fringe) stays on this
    // contribution, matching the pre-fix tint semantics.
    vec3 s = texture(src_tex, uv).rgb * mip_tint;

    vec3 result = s + accum;

    o_color = vec4(result, 1.0);
}
