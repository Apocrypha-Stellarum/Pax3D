#version 330

// Temporal Anti-Aliasing resolve shader.
// Blends current tonemapped frame with reprojected history using
// neighbourhood clamping to prevent ghosting.
//
// v1: No motion vectors / reprojection — history sampled at same UV.
// Neighbourhood clamp gracefully rejects stale history during camera motion.


uniform sampler2D current_frame;
uniform sampler2D history;
uniform vec2 u_resolution;
uniform float u_taa_frame;   // 0 on first frame, 1+ after
uniform float u_debug_taa;   // >0.5 = visualize rejection amount

in vec2 v_texcoord;

out vec4 o_color;

void main() {
    vec2 uv = v_texcoord;
    vec3 current = texture(current_frame, uv).rgb;

    // Sample history at same UV (no reprojection in v1)
    vec3 hist = texture(history, uv).rgb;

    // 3x3 neighbourhood AABB — prevents ghosting by clamping history
    // to the range of colours in the current frame's local neighbourhood
    vec2 texel = 1.0 / u_resolution;
    vec3 nb_min = current;
    vec3 nb_max = current;

    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            vec3 s = texture(current_frame, uv + vec2(float(x), float(y)) * texel).rgb;
            nb_min = min(nb_min, s);
            nb_max = max(nb_max, s);
        }
    }

    vec3 clamped_hist = clamp(hist, nb_min, nb_max);

    // First frame: use current entirely (history is empty/black)
    float blend = mix(1.0, 0.1, clamp(u_taa_frame, 0.0, 1.0));
    vec3 result = mix(clamped_hist, current, blend);

    // Debug: visualize how much history was rejected (red = full rejection)
    if (u_debug_taa > 0.5) {
        vec3 rejection = abs(hist - clamped_hist);
        float reject_amount = dot(rejection, vec3(0.333));
        result = vec3(reject_amount * 5.0, 1.0 - reject_amount * 5.0, 0.0);
    }

    o_color = vec4(result, 1.0);
}
