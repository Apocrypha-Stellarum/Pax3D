#version 330

// Simple texture passthrough — used by TAA history copy and display passes.


uniform sampler2D tex;

in vec2 v_texcoord;

out vec4 o_color;

void main() {
    o_color = texture(tex, v_texcoord);
}
