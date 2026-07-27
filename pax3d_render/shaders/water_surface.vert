#version 330
// pax3d_render water surface — vertex stage (engine promotion of the
// planetside/paxcraft shared water, 2026-07-28 voxel-lane ask).
//
// Descended from the sfb2 terrain-demo water (sessions 449-453) via
// planetside/shaders/water.vert and the paxcraft ocean.py port.  Three
// Gerstner swells displace a camera-following grid; the wave field is a
// function of WORLD position (p3d_ModelMatrix), so the surface never
// swims as the follow mesh re-centres.  Analytical normals; a
// camera-distance amplitude fade keeps sparse horizon geometry below
// its Nyquist limit; swells shoal (lose amplitude) over rising seafloor.
//
// Game-specific tuning arrives as uniforms (defaults = the planetside
// ocean; the voxel game compresses wavelengths and fades nearer):
//   u_swell_scale   wavenumber multiplier (1.0 = 57-120 m ocean swells)
//   u_swell_fade    (full-amplitude dist, zero-amplitude dist) in metres
//   u_rim_half      >0: alpha-fade the outer 20% of a single follow grid
//                   (model-space half extent); <=0: no rim fade
//   u_uncovered_dz  floor z RELATIVE TO water z where the seafloor map
//                   has no data: -40 reads "deep open water" (planetside
//                   horizon annulus), +100 reads "dry, render nothing"
//                   (voxel far-field land lives beyond the window)

uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
uniform float u_time;
uniform vec3 u_camera_pos;
uniform float u_wave_amp;
uniform float u_swell_scale;
uniform vec2 u_swell_fade;
uniform float u_rim_half;

// Player-following seafloor height map (absolute world z, metres).
// origin_size.xy = SW corner, .z = window size (<= 0 -> no map yet).
uniform sampler2D u_seafloor;
uniform vec3 u_sf_origin_size;
uniform float u_water_z;
uniform float u_uncovered_dz;

in vec4 p3d_Vertex;

out vec3 v_worldPos;
out vec3 v_waveNormal;
out float v_crest;
out float v_edge;

float seaDepth(vec2 xy) {
    vec2 uv = (xy - u_sf_origin_size.xy) / max(u_sf_origin_size.z, 1.0);
    float h = textureLod(u_seafloor, clamp(uv, 0.0, 1.0), 0.0).r;
    bool covered = u_sf_origin_size.z > 0.0 && uv == clamp(uv, 0.0, 1.0);
    return covered ? max(u_water_z - h, 0.0) : max(-u_uncovered_dz, 0.0);
}

// One Gerstner wave: accumulates height, horizontal displacement,
// height gradient and the crest pinch term.
void gerstner(vec2 pos, vec2 dir, float k, float amp, float speed, float q,
              float t, inout float h, inout vec2 disp, inout vec2 grad,
              inout float pinch) {
    float phase = k * dot(dir, pos) - speed * t;
    float s = sin(phase);
    float c = cos(phase);
    h += amp * s;
    disp += q * amp * dir * c;
    grad += k * amp * dir * c;
    pinch += q * k * amp * s;
}

void main() {
    // World position of the flat vertex (before displacement)
    vec4 flatWorld = p3d_ModelMatrix * p3d_Vertex;
    vec2 pos = flatWorld.xy;
    float t = u_time;

    // Swell fade: beyond u_swell_fade.y only the fragment noise normals
    // (per-pixel, non-periodic) animate the surface.
    float camd = distance(flatWorld.xyz, u_camera_pos);
    float amp_scale = u_wave_amp
        * (1.0 - smoothstep(u_swell_fade.x, u_swell_fade.y, camd));

    // Shoaling: swells lose amplitude over rising ground.  A small
    // residual keeps shore water alive (fragment ripples do the rest).
    float depth = seaDepth(pos);
    amp_scale *= mix(0.10, 1.0, smoothstep(0.4, 12.0, depth));

    // Large ocean swells only — base wavelengths 57-120 m, directions
    // spread ~120 degrees apart to avoid interference gridding.
    // Steepness Q_i = 0.65 / (k_i * A_i * 3), well under the crest-loop
    // self-intersection limit.
    float h = 0.0;
    float pinch = 0.0;
    vec2 disp = vec2(0.0);
    vec2 grad = vec2(0.0);
    float ks = u_swell_scale;
    gerstner(pos, normalize(vec2(0.95, 0.30)), 0.052 * ks,
             1.20 * amp_scale, 0.40, 3.47, t, h, disp, grad, pinch);
    gerstner(pos, normalize(vec2(-0.40, 0.90)), 0.068 * ks,
             0.80 * amp_scale, 0.50, 3.98, t, h, disp, grad, pinch);
    gerstner(pos, normalize(vec2(-0.55, -0.65)), 0.110 * ks,
             0.45 * amp_scale, 0.70, 4.38, t, h, disp, grad, pinch);

    // The water root is translation-only, so world-space displacement can
    // be applied directly in model space.
    vec4 displaced = p3d_Vertex;
    displaced.xy += disp;
    displaced.z += h;

    v_worldPos = (p3d_ModelMatrix * displaced).xyz;
    // Gerstner normal: the pinch term flattens N.z at compressed crests.
    v_waveNormal = normalize(
        vec3(-grad, 1.0 - clamp(pinch, 0.0, 0.8)));
    v_crest = max(pinch, 0.0);
    // Rim fade (single-grid consumers): model-space extent IS the follow
    // grid's own frame, so the fade rides the re-centring mesh.
    float rim = max(abs(p3d_Vertex.x), abs(p3d_Vertex.y))
                / max(u_rim_half, 1.0);
    v_edge = (u_rim_half > 0.0)
        ? 1.0 - smoothstep(0.80, 0.97, rim) : 1.0;
    gl_Position = p3d_ModelViewProjectionMatrix * displaced;
}
