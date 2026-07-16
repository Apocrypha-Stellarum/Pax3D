#version 120

#ifdef USE_330
    #define texture2D texture
#endif

uniform sampler2D src_tex;
uniform vec2 texel_size;

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

void main() {
    vec2 uv = v_texcoord;
    vec2 ts = texel_size;

    // Center sample
    vec3 a = texture2D(src_tex, uv).rgb;

    // Inner ring (offset by 1 texel diagonally)
    vec3 b = texture2D(src_tex, uv + vec2(-ts.x, -ts.y)).rgb;
    vec3 c = texture2D(src_tex, uv + vec2( ts.x, -ts.y)).rgb;
    vec3 d = texture2D(src_tex, uv + vec2(-ts.x,  ts.y)).rgb;
    vec3 e = texture2D(src_tex, uv + vec2( ts.x,  ts.y)).rgb;

    // Outer ring (offset by 2 texels along axes and diagonals)
    vec3 f = texture2D(src_tex, uv + vec2(-2.0 * ts.x, -2.0 * ts.y)).rgb;
    vec3 g = texture2D(src_tex, uv + vec2(        0.0, -2.0 * ts.y)).rgb;
    vec3 h = texture2D(src_tex, uv + vec2( 2.0 * ts.x, -2.0 * ts.y)).rgb;
    vec3 i = texture2D(src_tex, uv + vec2(-2.0 * ts.x,         0.0)).rgb;
    vec3 j = texture2D(src_tex, uv + vec2( 2.0 * ts.x,         0.0)).rgb;
    vec3 k = texture2D(src_tex, uv + vec2(-2.0 * ts.x,  2.0 * ts.y)).rgb;
    vec3 l = texture2D(src_tex, uv + vec2(        0.0,  2.0 * ts.y)).rgb;
    vec3 m = texture2D(src_tex, uv + vec2( 2.0 * ts.x,  2.0 * ts.y)).rgb;

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

#ifdef USE_330
    o_color = vec4(result, 1.0);
#else
    gl_FragColor = vec4(result, 1.0);
#endif
}
