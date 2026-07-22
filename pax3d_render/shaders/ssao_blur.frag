#version 330
// Pax3D SSAO blur (Session S): 3x3 tent over the raw obscurance to
// suppress the spiral kernel's per-pixel rotation noise. AO is a
// smooth scalar field, so a plain tent is enough for the first slice
// (a depth-aware bilateral is the quality upgrade path). A field that
// is exactly 1.0 everywhere stays exactly 1.0 — the plane gate's
// byte-identity survives the blur.


uniform sampler2D ao_tex;
uniform vec2 u_texel;

in vec2 v_texcoord;

out vec4 o_color;

void main() {
    float sum = 0.0;
    // 3x3 tent: corner 1, edge 2, center 4 (total 16)
    for (int dy = -1; dy <= 1; dy++) {
        for (int dx = -1; dx <= 1; dx++) {
            float w = (dx == 0 ? 2.0 : 1.0) * (dy == 0 ? 2.0 : 1.0);
            vec2 uv = v_texcoord + vec2(float(dx), float(dy)) * u_texel;
            sum += w * texture(ao_tex, uv).r;
        }
    }
    float ao = sum / 16.0;
    vec4 result = vec4(ao, ao, ao, 1.0);
    o_color = result;
}
