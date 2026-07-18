#version 120

#ifdef USE_330
    #define texture2D texture
    #define texture3D texture
#endif

uniform sampler2D tex;
#ifdef ENABLE_BLOOM
    uniform sampler2D bloom_tex;
    uniform float bloom_intensity;
#endif
#ifdef ENABLE_SSAO
    uniform sampler2D ao_tex;
#endif
#ifdef USE_SDR_LUT
    uniform sampler3D sdr_lut;
    uniform float sdr_lut_factor;
#endif
uniform float exposure;
uniform int tonemap_operator;

// FTL warp distortion: radial motion blur + chromatic aberration.
// Both strengths default to 0.0 = single-tap passthrough (the multi-tap
// loop is skipped entirely; cost is one coherent branch per pixel).
uniform float radial_blur_strength;
uniform float chroma_strength;
uniform vec2 radial_blur_center;

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

// ACES filmic tonemap (Stephen Hill's fitted approximation)
vec3 aces_tonemap(vec3 x) {
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

// Reinhard tonemap
vec3 reinhard_tonemap(vec3 x) {
    return x / (x + vec3(1.0));
}

// Uncharted 2 tonemap (John Hable)
vec3 uncharted2_partial(vec3 x) {
    float A = 0.15;
    float B = 0.50;
    float C = 0.10;
    float D = 0.20;
    float E = 0.02;
    float F = 0.30;
    return ((x * (A * x + C * B) + D * E) / (x * (A * x + B) + D * F)) - E / F;
}

vec3 uncharted2_tonemap(vec3 x) {
    float W = 11.2;
    vec3 curr = uncharted2_partial(x * 2.0);
    vec3 white_scale = vec3(1.0) / uncharted2_partial(vec3(W));
    return curr * white_scale;
}

// Hejl-Dawson tonemap (legacy simplepbr default, includes sRGB baked in)
vec3 hejl_dawson_tonemap(vec3 x) {
    x = max(vec3(0.0), x - vec3(0.004));
    return (x * (vec3(6.2) * x + vec3(0.5))) / (x * (vec3(6.2) * x + vec3(1.7)) + vec3(0.06));
}

// Interleaved gradient noise (Jimenez 2014) — cheap per-pixel hash
float interleavedGradientNoise(vec2 p) {
    vec3 magic = vec3(0.06711056, 0.00583715, 52.9829189);
    return fract(magic.z * fract(dot(p, magic.xy)));
}

void main() {
    vec4 tex_color = texture2D(tex, v_texcoord);
    vec3 color = tex_color.rgb;

    // FTL warp distortion: N-tap radial smear toward radial_blur_center
    // with per-channel radial offsets for chromatic fringing.  Runs in
    // HDR space (before exposure/tonemap) so highlights streak
    // realistically.  Zero at the center, growing radially — the
    // vanishing point of motion stays sharp.
    if (radial_blur_strength > 0.0005 || chroma_strength > 0.0005) {
        // dir is unnormalized, so tap offsets (dir * t) already grow
        // linearly with distance from the center — zero at the center
        vec2 dir = v_texcoord - radial_blur_center;
        float amt = radial_blur_strength * 0.22;
        float ca = chroma_strength * 0.012;
        vec3 acc = vec3(0.0);
        const int TAPS = 8;
        for (int i = 0; i < TAPS; i++) {
            float t = (float(i) / float(TAPS - 1) - 0.5) * amt;
            vec2 base_uv = v_texcoord - dir * t;
            acc.r += texture2D(tex, base_uv - dir * ca).r;
            acc.g += texture2D(tex, base_uv).g;
            acc.b += texture2D(tex, base_uv + dir * ca).b;
        }
        color = acc / float(TAPS);
    }

    // SSAO (Session S): obscure the scene radiance BEFORE the bloom add
    // (bloom sources are bright emitters where AO ~ 1) and before the
    // curve. AO == 1.0 multiplies exactly — flat scenes stay
    // byte-identical (the paxtest plane gate).
#ifdef ENABLE_SSAO
    color *= texture2D(ao_tex, v_texcoord).r;
#endif

    // Bloom composite (additive, before tonemapping for correct rolloff)
#ifdef ENABLE_BLOOM
    vec3 bloom = texture2D(bloom_tex, v_texcoord).rgb;
    color += bloom * bloom_intensity;
#endif

    // Exposure
    color *= exposure;

    // Tonemap
    // 0 = ACES (default), 1 = Reinhard, 2 = Uncharted2, 3 = Hejl-Dawson (legacy)
    if (tonemap_operator == 1) {
        color = reinhard_tonemap(color);
        color = pow(color, vec3(1.0 / 2.2));
    } else if (tonemap_operator == 2) {
        color = uncharted2_tonemap(color);
        color = pow(color, vec3(1.0 / 2.2));
    } else if (tonemap_operator == 3) {
        color = hejl_dawson_tonemap(color);
        // Hejl-Dawson bakes in sRGB gamma — no additional pow needed
    } else {
        // Default: ACES
        color = aces_tonemap(color);
        color = pow(color, vec3(1.0 / 2.2));
    }

#ifdef USE_SDR_LUT
    vec3 lut_size = vec3(textureSize(sdr_lut, 0));
    vec3 lut_uvw = (color.rgb * float(lut_size - 1.0) + 0.5) / lut_size;
    vec3 lut_color = texture3D(sdr_lut, lut_uvw).rgb;
    color = mix(color, lut_color, sdr_lut_factor);
#endif

    // Per-channel dither to break 8-bit banding (±0.5/255 per channel, independent)
    float ditherR = (interleavedGradientNoise(gl_FragCoord.xy) - 0.5) / 255.0;
    float ditherG = (interleavedGradientNoise(gl_FragCoord.xy + vec2(17.0, 31.0)) - 0.5) / 255.0;
    float ditherB = (interleavedGradientNoise(gl_FragCoord.xy + vec2(43.0, 59.0)) - 0.5) / 255.0;
    color += vec3(ditherR, ditherG, ditherB);

#ifdef USE_330
    o_color = vec4(color, tex_color.a);
#else
    gl_FragColor = vec4(color, tex_color.a);
#endif
}
