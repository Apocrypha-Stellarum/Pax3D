// Pax3D orbital scattering fragment shader (R5.5)
//
// The planet seen from space: limb glow, halo beyond the disk, aerial
// haze over the disk, terminator tinting. Single scattering through an
// exponential-density spherical shell, evaluated per pixel on a
// camera-facing billboard quad (analytic ray-vs-sphere — the limb
// profile is polygon-free, unlike a tessellated shell mesh).
//
// THE MODEL (replicated independently by paxtest test_orbital — any
// change here must change the test's reference integrator too):
//
//   rho(P)   = exp(-max(|P - C| - R, 0) / H)      relative density
//   segment  = view ray clipped to the shell [R, R_top], truncated at
//              the planet surface if the ray hits it
//   D_view   = integral of rho ds over the segment (trapezoid,
//              ORB_VIEW_STEPS intervals)
//   T_view   = exp(-beta_rgb * D_view)             per-channel
//   P*       = closest approach of the segment to C (clamped to it) —
//              the density-weighted heart of the ray, where the single
//              stated approximation is made: sun transmittance is
//              evaluated once, at P*.
//   D_sun    = integral of rho along +sun from P* to the shell top
//              (trapezoid, ORB_SUN_STEPS intervals; rho clamps h >= 0,
//              so a sun ray "through" the planet saturates naturally)
//   occl     = smoothstep(0, 2H, grazing altitude of the sun ray) —
//              soft terminator; 1 when the sun ray never approaches
//   T_sun    = exp(-beta_rgb * D_sun) * occl
//   phase    = 0.75 * (1 + mu^2), mu = dot(view, sun) — the Rayleigh
//              lobe normalized to sphere-average exactly 1, so
//              u_orb_intensity directly scales mean inscatter
//   L        = sun_color * intensity * phase * T_sun * (1 - T_view)
//
// Given constant T_sun along the segment and scattering albedo 1, the
// (1 - T_view) form is the EXACT single-scatter integral, not an ad-hoc
// blend (d/ds T_cam = -beta rho T_cam telescopes the sum).
//
// Two passes over the same quad, selected by ORB_INSCATTER:
//   extinction (default): outputs (T_rgb, 1), blend dst *= src.rgb
//   inscatter:            outputs (L_rgb, 0), blend dst += src.rgb
// Extinction must draw first (its own inscatter is not extinguished).
// Alpha outputs (1 and 0) leave the framebuffer alpha byte-identical.
//
// With density = 0: beta = 0, T = 1, L = 0 — both passes are exact
// framebuffer no-ops (dst * 1.0 and dst + 0.0), the opt-out contract.

#version 120

#ifndef ORB_VIEW_STEPS
    #define ORB_VIEW_STEPS 24
#endif
#ifndef ORB_SUN_STEPS
    #define ORB_SUN_STEPS 12
#endif

uniform vec3 u_orb_center;            // planet center, world space
uniform float u_orb_planet_radius;    // R, world units
uniform float u_orb_top_radius;       // R_top = R + thickness
uniform float u_orb_inv_scale_height; // 1 / H
uniform vec3 u_orb_beta;              // extinction = density * tint, rgb
uniform float u_orb_intensity;        // inscatter brightness multiplier

// Inherited pipeline inputs (set on the render node)
uniform vec3 u_sun_dir_world;         // toward the sun
uniform vec3 u_sun_color;             // linear RGB * intensity
uniform vec3 camera_world_position;

varying vec3 v_world_position;
#ifdef LOG_DEPTH
uniform float u_log_depth_coef;
varying float v_log_depth_w;
#endif
#ifdef USE_330
out vec4 o_color;
#endif

float orb_rho(vec3 p) {
    float h = max(length(p - u_orb_center) - u_orb_planet_radius, 0.0);
    return exp(-min(h * u_orb_inv_scale_height, 60.0));
}

void main() {
    vec3 ray = v_world_position - camera_world_position;
    float ray_len = length(ray);
    vec3 dir = (ray_len > 1e-6) ? ray / ray_len : vec3(0.0, 1.0, 0.0);

    vec3 trans = vec3(1.0);
    vec3 inscatter = vec3(0.0);

    // View ray vs the shell top sphere
    vec3 oc = camera_world_position - u_orb_center;
    float b = dot(oc, dir);
    float c_top = dot(oc, oc) - u_orb_top_radius * u_orb_top_radius;
    float disc = b * b - c_top;
    if (disc > 0.0) {
        float sq = sqrt(disc);
        float t0 = max(-b - sq, 0.0);
        float t1 = -b + sq;
        // Truncate at the planet surface
        float c_pl = dot(oc, oc)
                     - u_orb_planet_radius * u_orb_planet_radius;
        float disc_p = b * b - c_pl;
        if (disc_p > 0.0) {
            float tp = -b - sqrt(disc_p);
            if (tp > 0.0) {
                t1 = min(t1, tp);
            }
        }
        if (t1 > t0) {
            // Optical depth along the view segment
            float dt = (t1 - t0) / float(ORB_VIEW_STEPS);
            float d_view = 0.0;
            for (int i = 0; i <= ORB_VIEW_STEPS; ++i) {
                float w = (i == 0 || i == ORB_VIEW_STEPS) ? 0.5 : 1.0;
                d_view += w * orb_rho(camera_world_position
                                      + dir * (t0 + dt * float(i)));
            }
            d_view *= dt;
            vec3 tau = min(u_orb_beta * d_view, vec3(60.0));
            trans = exp(-tau);

            // Sun transmittance at the segment's closest approach P*
            vec3 sdir = normalize(u_sun_dir_world);
            float t_star = clamp(-b, t0, t1);
            vec3 pstar = camera_world_position + dir * t_star;
            vec3 pc = pstar - u_orb_center;

            float m = -dot(pc, sdir);       // >0: sun ray heads planet-ward
            float occl = 1.0;
            if (m > 0.0) {
                float b_alt = length(pc + sdir * m) - u_orb_planet_radius;
                float x = clamp(b_alt * u_orb_inv_scale_height * 0.5,
                                0.0, 1.0);  // 2H terminator width
                occl = x * x * (3.0 - 2.0 * x);
            }

            float sb = dot(pc, sdir);
            float sc = dot(pc, pc) - u_orb_top_radius * u_orb_top_radius;
            float sdisc = sb * sb - sc;
            float u_exit = (sdisc > 0.0) ? max(-sb + sqrt(sdisc), 0.0)
                                         : 0.0;
            float du = u_exit / float(ORB_SUN_STEPS);
            float d_sun = 0.0;
            for (int i = 0; i <= ORB_SUN_STEPS; ++i) {
                float w = (i == 0 || i == ORB_SUN_STEPS) ? 0.5 : 1.0;
                d_sun += w * orb_rho(pstar + sdir * (du * float(i)));
            }
            d_sun *= du;
            vec3 tau_sun = min(u_orb_beta * d_sun, vec3(60.0));
            vec3 t_sun = exp(-tau_sun) * occl;

            float mu = dot(dir, sdir);
            float phase = 0.75 * (1.0 + mu * mu);
            inscatter = u_sun_color * u_orb_intensity * phase * t_sun
                        * (vec3(1.0) - trans);
        }
    }

#ifdef ORB_INSCATTER
    vec4 color = vec4(inscatter, 0.0);
#else
    vec4 color = vec4(trans, 1.0);
#endif

#ifdef LOG_DEPTH
    gl_FragDepth = log2(max(v_log_depth_w, 1e-6)) * u_log_depth_coef;
#endif

#ifdef USE_330
    o_color = color;
#else
    gl_FragColor = color;
#endif
}
