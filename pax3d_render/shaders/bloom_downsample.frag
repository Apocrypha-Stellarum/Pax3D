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

    // 13-tap Jimenez kernel: center box weight 0.5, four corner boxes 0.125 each
    vec3 result = a * 0.125;
    result += (b + c + d + e) * 0.125;
    result += (f + g + b + i) * 0.03125;
    result += (g + h + c + j) * 0.03125;
    result += (i + b + k + l) * 0.03125;
    result += (c + j + l + m) * 0.03125;

    // Energy compensation — boost to counteract resolution halving
    result *= 1.3;

#ifdef USE_330
    o_color = vec4(result, 1.0);
#else
    gl_FragColor = vec4(result, 1.0);
#endif
}
