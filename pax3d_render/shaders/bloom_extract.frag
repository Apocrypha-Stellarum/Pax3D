#version 330


uniform sampler2D scene_tex;
uniform float bloom_strength;

in vec2 v_texcoord;

out vec4 o_color;

void main() {
    vec3 color = texture(scene_tex, v_texcoord).rgb;

    // Scale by bloom strength — no hard threshold, physically proportional
    color *= bloom_strength * 0.005;

    // Firefly clamp to prevent single bright pixels from dominating
    color = clamp(color, vec3(0.0), vec3(25000.0));

    o_color = vec4(color, 1.0);
}
