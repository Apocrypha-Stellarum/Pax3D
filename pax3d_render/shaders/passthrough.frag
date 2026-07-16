#version 120

// Simple texture passthrough — used by TAA history copy and display passes.

#ifdef USE_330
    #define texture2D texture
#endif

uniform sampler2D tex;

varying vec2 v_texcoord;

#ifdef USE_330
out vec4 o_color;
#endif

void main() {
#ifdef USE_330
    o_color = texture2D(tex, v_texcoord);
#else
    gl_FragColor = texture2D(tex, v_texcoord);
#endif
}
