"""paxtest: aerial perspective / height haze (Session J, R5.1).

The planetside atmosphere: an exponential-height medium evaluated
analytically in the PBR shader (define ENABLE_ATMOSPHERE), opt-in and
byte-identical when off — the spaceflight path must be untouched.

Checks, in order:
  1. Baseline capture with the feature off (the shipped default).
  2. Runtime enable with density=0 is byte-identical to off (tau == 0 is an
     exact no-op) — this also exercises the recompile-preserves-inputs
     invariant (arch doc §3).
  3. Analytic transmittance: a BLACK card at distance d through a uniform
     medium (scale_height >> scene) must render at
     curve(haze * (1 - exp(-density * d))) — checked at three distances,
     plus monotonicity.
  4. Height falloff: the same horizontal ray high above the scale height
     carries a small fraction of the ground-level inscatter (mountains poke
     out of the haze).
  5. Sun-forward tint: looking sunward picks up sun_haze_color, looking
     anti-sunward stays at haze_color (checked by channel ordering with a
     red sun-lobe over a blue haze).
  6. Full opt-out: disable restores the baseline capture exactly.

Only meaningful for pipelines exposing set_enable_atmosphere
(pax3d_render).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


HAZE = (0.5, 0.7, 0.9)
DENSITY = 0.002
DISTANCES = [100.0, 400.0, 1600.0]

# Height-falloff phase
H_SCALE = 30.0
H_DENSITY = 0.01
H_DIST = 300.0
H_LOW_Z = 1.0
H_HIGH_Z = 150.0

# Sun-tint phase
TINT_HAZE = (0.1, 0.1, 0.8)
TINT_SUN = (0.9, 0.2, 0.1)
TINT_DIST = 400.0


def make_facing_card(parent, half, y, z, rgb, name):
    """A camera-facing card (XZ plane) centered at (0, y, z)."""
    cm = p3d.CardMaker(name)
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    np.set_pos(0, y, z)
    np.set_two_sided(True)
    scenes.apply_flat_pbr_surface(np, rgb=rgb)
    return np


def avg_rgb(img, cx, cy, half=2):
    r = g = b = 0.0
    n = 0
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            c = img.get_xel(int(cx + dx), int(cy + dy))
            r += c[0]
            g += c[1]
            b += c[2]
            n += 1
    return r / n, g / n, b / n


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'atmosphere')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_enable_atmosphere'):
        h.report.skip('pipeline has no set_enable_atmosphere (R5.1)')
    base = h.base
    curve = common.CURVES['hejl_dawson']

    # Harness gotcha: with no lights attached p3d_LightModel.ambient floods
    # white. Keep it tiny so the black card stays ~black.
    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(0.005, 0.005, 0.005, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    # Sun pointing away from the view axis, black — no direct lighting; the
    # tint phase re-aims it explicitly.
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))

    base.camLens.set_near_far(0.5, 5000.0)
    base.camera.set_pos(0, 0, 1)
    base.camera.set_hpr(0, 0, 0)      # looking +y

    # One black card per distance, sized to cover the screen center; only
    # the nearest is visible (they occlude down the +y axis), so phases
    # show/hide them one at a time.
    cards = [make_facing_card(base.render, 0.2 * d, d, 1.0, (0, 0, 0),
                              f'black_{int(d)}')
             for d in DISTANCES]
    for c in cards[1:]:
        c.hide()
    cx, cy = h.win_w // 2, h.win_h // 2

    # --- 1. Baseline: feature off (shipped default) ---------------------
    h.step(5)
    img_off = h.capture()
    h.save_capture(img_off, 'off')
    base_lum = common.avg_lum(img_off, cx, cy)
    h.report.check('baseline_black', base_lum < 0.15,
                   f'black card, atmosphere off: lum={base_lum:.3f} '
                   f'(dither+tiny ambient only)')

    # --- 2. Enabled with density 0 == off, byte-identical ---------------
    pipeline.set_enable_atmosphere(True)
    pipeline.set_atmosphere_params(haze_color=HAZE, density=0.0)
    h.step(5)
    img_d0 = h.capture()
    rms = common.image_rms_diff(img_off, img_d0, step=1)
    h.report.check('density_zero_identical', rms == 0.0,
                   f'ENABLE_ATMOSPHERE compiled in, density=0: rms vs off '
                   f'= {rms:.2e} (tau=0 is an exact no-op; recompile '
                   f'preserved every shader input)')

    # --- 3. Analytic transmittance at three distances -------------------
    # Uniform medium: scale_height huge => density constant along the ray.
    pipeline.set_atmosphere_params(haze_color=HAZE, density=DENSITY,
                                   scale_height=1e9, base_height=0.0)
    lums = []
    for i, d in enumerate(DISTANCES):
        for j, c in enumerate(cards):
            if j == i:
                c.show()
            else:
                c.hide()
        h.step(5)
        img = h.capture()
        h.save_capture(img, f'dist_{int(d)}')
        got = avg_rgb(img, cx, cy)
        inscatter = 1.0 - math.exp(-DENSITY * d)
        want = tuple(curve(ch * inscatter) for ch in HAZE)
        err = max(abs(g - w) for g, w in zip(got, want))
        lums.append(sum(got) / 3.0)
        h.report.check(
            f'analytic_d{int(d)}', err < 0.05,
            f'black card at {d:.0f}: rgb=({got[0]:.3f},{got[1]:.3f},'
            f'{got[2]:.3f}) expected ({want[0]:.3f},{want[1]:.3f},'
            f'{want[2]:.3f}) [1-T={inscatter:.3f}], max channel err '
            f'{err:.3f}')
    h.report.check('haze_monotonic_with_distance',
                   lums[0] < lums[1] < lums[2],
                   f'inscatter grows with distance: '
                   f'{lums[0]:.3f} < {lums[1]:.3f} < {lums[2]:.3f}')

    # --- 4. Height falloff ---------------------------------------------
    # Same horizontal ray length at two altitudes; density at altitude z is
    # density * exp(-z / H), so the high ray carries almost no inscatter.
    pipeline.set_atmosphere_params(density=H_DENSITY, scale_height=H_SCALE,
                                   base_height=0.0)
    card = make_facing_card(base.render, 0.2 * H_DIST, 0, 0, (0, 0, 0),
                            'height_card')
    for c in cards:
        c.hide()
    results = []
    for z in (H_LOW_Z, H_HIGH_Z):
        base.camera.set_pos(0, 0, z)
        card.set_pos(0, H_DIST, z)
        h.step(5)
        img = h.capture()
        h.save_capture(img, f'height_z{int(z)}')
        got = common.avg_lum(img, cx, cy)
        tau = H_DENSITY * H_DIST * math.exp(-z / H_SCALE)
        want_lum = sum(curve(ch * (1.0 - math.exp(-tau)))
                       for ch in HAZE) / 3.0
        results.append((z, got, want_lum))
        h.report.check(
            f'height_analytic_z{int(z)}', abs(got - want_lum) < 0.05,
            f'horizontal ray at z={z:.0f} (H={H_SCALE:.0f}): lum='
            f'{got:.3f} expected {want_lum:.3f} (tau={tau:.2f})')
    h.report.check('haze_thins_with_altitude',
                   results[1][1] < 0.2 * max(results[0][1], 1e-6),
                   f'inscatter {results[0][1]:.3f} at z={H_LOW_Z:.0f} -> '
                   f'{results[1][1]:.3f} at z={H_HIGH_Z:.0f}: above the '
                   f'scale height the haze is gone')
    card.hide()

    # --- 5. Sun-forward tint --------------------------------------------
    base.camera.set_pos(0, 0, 1)
    cards[1].show()                   # 400-unit card
    pipeline.set_atmosphere_params(haze_color=TINT_HAZE,
                                   sun_haze_color=TINT_SUN, sun_power=4.0,
                                   density=DENSITY, scale_height=1e9)
    h.adapter.update_sun((0, 1, 0), (0, 0, 0))     # sun dead ahead
    h.step(5)
    r_sun, _, b_sun = avg_rgb(h.capture(), cx, cy)
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))    # sun behind the camera
    h.step(5)
    img_anti = h.capture()
    h.save_capture(img_anti, 'anti_sunward')
    r_anti, _, b_anti = avg_rgb(img_anti, cx, cy)
    h.report.check('sunward_tint', r_sun > b_sun and b_anti > r_anti,
                   f'looking sunward rgb ordering red>blue '
                   f'({r_sun:.3f} vs {b_sun:.3f}); anti-sunward blue>red '
                   f'({b_anti:.3f} vs {r_anti:.3f}) — forward-scatter '
                   f'lobe follows the sun')

    # --- 5b. Per-node atmosphere scale (Session S — hull interiors) -----
    # Two black cards side by side at the same distance; scale only the
    # left one. The right card is the sibling that must keep full haze.
    if hasattr(pipeline, 'set_atmosphere_scale'):
        for c in cards:
            c.hide()
        d2 = DISTANCES[1]
        card_l = make_facing_card(base.render, 0.08 * d2, d2, 1.0,
                                  (0, 0, 0), 'scale_left')
        card_r = make_facing_card(base.render, 0.08 * d2, d2, 1.0,
                                  (0, 0, 0), 'scale_right')
        card_l.set_x(-0.12 * d2)
        card_r.set_x(0.12 * d2)
        h.adapter.update_sun((0, -1, 0), (0, 0, 0))   # mu=0: pure haze color

        def project_px(np):
            ndc = p3d.Point2()
            base.camLens.project(base.camera.get_relative_point(
                base.render, np.get_pos(base.render)), ndc)
            return (int((ndc.x * 0.5 + 0.5) * h.win_w),
                    int((ndc.y * 0.5 + 0.5) * h.win_h))

        lx, ly = project_px(card_l)
        rx, ry = project_px(card_r)
        ray_d = math.hypot(d2, 0.12 * d2)   # camera (0,0,1) -> card center

        # density=0 reference for the exact scale-0 comparison
        pipeline.set_atmosphere_params(haze_color=HAZE, density=0.0,
                                       scale_height=1e9, base_height=0.0)
        h.step(5)
        left_d0 = avg_rgb(h.capture(), lx, ly)

        # Full haze on both cards
        pipeline.set_atmosphere_params(density=DENSITY)
        h.step(5)
        img_full = h.capture()
        h.save_capture(img_full, 'scale_full')

        # scale 1.0 is an exact no-op (IEEE x*1.0)
        pipeline.set_atmosphere_scale(card_l, 1.0)
        h.step(5)
        rms = common.image_rms_diff(img_full, h.capture(), step=1)
        h.report.check('atmo_scale_one_noop', rms == 0.0,
                       f'set_atmosphere_scale(np, 1.0): rms vs untouched '
                       f'= {rms:.2e} (exact no-op)')

        # scale 0.5: tau scales linearly -> analytic; sibling keeps full
        pipeline.set_atmosphere_scale(card_l, 0.5)
        h.step(5)
        img_half = h.capture()
        h.save_capture(img_half, 'scale_half')
        got_l = avg_rgb(img_half, lx, ly)
        got_r = avg_rgb(img_half, rx, ry)
        want_l = tuple(curve(ch * (1.0 - math.exp(-DENSITY * ray_d * 0.5)))
                       for ch in HAZE)
        want_r = tuple(curve(ch * (1.0 - math.exp(-DENSITY * ray_d)))
                       for ch in HAZE)
        err_l = max(abs(g - w) for g, w in zip(got_l, want_l))
        err_r = max(abs(g - w) for g, w in zip(got_r, want_r))
        h.report.check(
            'atmo_scale_half_analytic', err_l < 0.05 and err_r < 0.05,
            f'scale 0.5: left rgb=({got_l[0]:.3f},{got_l[1]:.3f},'
            f'{got_l[2]:.3f}) expected ({want_l[0]:.3f},{want_l[1]:.3f},'
            f'{want_l[2]:.3f}) err {err_l:.3f}; sibling keeps full haze '
            f'err {err_r:.3f} (tau scales linearly, per-node only)')

        # scale 0.0 == density 0 for those fragments, exactly
        pipeline.set_atmosphere_scale(card_l, 0.0)
        h.step(5)
        img_zero = h.capture()
        h.save_capture(img_zero, 'scale_zero')
        got_l0 = avg_rgb(img_zero, lx, ly)
        err0 = max(abs(g - w) for g, w in zip(got_l0, left_d0))
        got_r0 = avg_rgb(img_zero, rx, ry)
        err_r0 = max(abs(g - w) for g, w in zip(got_r0, want_r))
        h.report.check(
            'atmo_scale_zero_no_haze', err0 < 1e-3 and err_r0 < 0.05,
            f'scale 0.0: left matches the density=0 render to '
            f'{err0:.2e} (tau exactly 0 — no haze on the subtree); '
            f'sibling still full haze (err {err_r0:.3f})')

        # clear restores byte-identically
        pipeline.clear_atmosphere_scale(card_l)
        h.step(5)
        rms = common.image_rms_diff(img_full, h.capture(), step=1)
        h.report.check('atmo_scale_clear_restores', rms == 0.0,
                       f'clear_atmosphere_scale(): rms vs untouched = '
                       f'{rms:.2e} (byte-identical restore)')
        card_l.remove_node()
        card_r.remove_node()

    # --- 6. Opt-out restores the baseline exactly -----------------------
    for c in cards:
        c.hide()
    cards[0].show()
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))
    pipeline.set_enable_atmosphere(False)
    h.step(5)
    img_restored = h.capture()
    rms = common.image_rms_diff(img_off, img_restored, step=1)
    h.report.check('opt_out_restores', rms == 0.0,
                   f'set_enable_atmosphere(False): rms vs the pre-enable '
                   f'baseline = {rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
