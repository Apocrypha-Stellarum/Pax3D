#version 330


uniform sampler2D src_tex;
uniform vec2 texel_size;

in vec2 v_texcoord;

out vec4 o_color;

void main() {
    vec2 uv = v_texcoord;
    vec2 ts = texel_size;

    // Center sample
    vec3 a = texture(src_tex, uv).rgb;

    // Inner ring (offset by 1 texel diagonally)
    vec3 b = texture(src_tex, uv + vec2(-ts.x, -ts.y)).rgb;
    vec3 c = texture(src_tex, uv + vec2( ts.x, -ts.y)).rgb;
    vec3 d = texture(src_tex, uv + vec2(-ts.x,  ts.y)).rgb;
    vec3 e = texture(src_tex, uv + vec2( ts.x,  ts.y)).rgb;

    // Outer ring (offset by 2 texels along axes and diagonals)
    vec3 f = texture(src_tex, uv + vec2(-2.0 * ts.x, -2.0 * ts.y)).rgb;
    vec3 g = texture(src_tex, uv + vec2(        0.0, -2.0 * ts.y)).rgb;
    vec3 h = texture(src_tex, uv + vec2( 2.0 * ts.x, -2.0 * ts.y)).rgb;
    vec3 i = texture(src_tex, uv + vec2(-2.0 * ts.x,         0.0)).rgb;
    vec3 j = texture(src_tex, uv + vec2( 2.0 * ts.x,         0.0)).rgb;
    vec3 k = texture(src_tex, uv + vec2(-2.0 * ts.x,  2.0 * ts.y)).rgb;
    vec3 l = texture(src_tex, uv + vec2(        0.0,  2.0 * ts.y)).rgb;
    vec3 m = texture(src_tex, uv + vec2( 2.0 * ts.x,  2.0 * ts.y)).rgb;

    // 13-tap Jimenez kernel: five overlapping 4-tap boxes — the inner box
    // (b,c,d,e) at weight 0.5, four corner boxes at 0.125 each. Every
    // corner box includes the CENTER sample a (not b/c — that typo
    // overweighted the -y taps and skewed the halo vertically, F3).
    // Weights sum to exactly 1.0.
    vec3 result = (b + c + d + e) * 0.125;
    result += (f + g + i + a) * 0.03125;
    result += (g + h + a + j) * 0.03125;
    result += (i + a + k + l) * 0.03125;
    result += (a + j + l + m) * 0.03125;

    // Energy compensation — boost to counteract resolution halving
    result *= 1.3;

    o_color = vec4(result, 1.0);
}
