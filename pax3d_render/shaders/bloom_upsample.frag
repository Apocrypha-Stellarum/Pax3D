#version 120

#ifdef USE_330
    #define texture2D texture
#endif

uniform sampler2D src_tex;
uniform sampler2D bloom_accum_tex;
uniform vec2 texel_size;
uniform vec3 mip_tint;

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

void main() {
    vec2 uv = v_texcoord;
    vec2 ts = texel_size;

    // 9-tap tent filter (3x3 kernel)
    // Weights: corners=1, edges=2, center=4, total=16
    vec3 s = vec3(0.0);
    s += texture2D(src_tex, uv + vec2(-ts.x, -ts.y)).rgb * 1.0;
    s += texture2D(src_tex, uv + vec2(  0.0, -ts.y)).rgb * 2.0;
    s += texture2D(src_tex, uv + vec2( ts.x, -ts.y)).rgb * 1.0;
    s += texture2D(src_tex, uv + vec2(-ts.x,   0.0)).rgb * 2.0;
    s += texture2D(src_tex, uv                      ).rgb * 4.0;
    s += texture2D(src_tex, uv + vec2( ts.x,   0.0)).rgb * 2.0;
    s += texture2D(src_tex, uv + vec2(-ts.x,  ts.y)).rgb * 1.0;
    s += texture2D(src_tex, uv + vec2(  0.0,  ts.y)).rgb * 2.0;
    s += texture2D(src_tex, uv + vec2( ts.x,  ts.y)).rgb * 1.0;
    s /= 16.0;

    // Apply per-mip color tint (artistic warm-cool bloom fringe)
    s *= mip_tint;

    // Accumulate with previous upsample level
    vec3 accum = texture2D(bloom_accum_tex, uv).rgb;
    vec3 result = s + accum;

#ifdef USE_330
    o_color = vec4(result, 1.0);
#else
    gl_FragColor = vec4(result, 1.0);
#endif
}
