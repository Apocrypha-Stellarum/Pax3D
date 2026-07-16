#version 120

#ifdef USE_330
    #define texture2D texture
#endif

uniform sampler2D scene_tex;
uniform float bloom_strength;

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

void main() {
    vec3 color = texture2D(scene_tex, v_texcoord).rgb;

    // Scale by bloom strength — no hard threshold, physically proportional
    color *= bloom_strength * 0.005;

    // Firefly clamp to prevent single bright pixels from dominating
    color = clamp(color, vec3(0.0), vec3(25000.0));

#ifdef USE_330
    o_color = vec4(color, 1.0);
#else
    gl_FragColor = vec4(color, 1.0);
#endif
}
