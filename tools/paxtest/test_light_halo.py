"""paxtest: light halo billboards (Session AF, ER-013 — nav-light
readability at range).

pipeline.set_light_halo(np, color, size_m, min_px, intensity) attaches
a camera-facing additive quad at the node's position: true world
diameter close up, clamped to min_px pixels on screen at distance, so
a blinking cm-scale nav bulb stays readable at km ranges. Depth-tested
(occlusion = the depth test, no occluder lists), never depth-written,
excluded from the shadow caster mask, and it inherits the
set_blink/set_emission_scale registry (u_emission_factor) so halos
flash in sync with their circuit.

Scene: PERSPECTIVE camera (the size-clamp math is the point), black
background, sun black, no ambient — the halo shader is unlit, so every
center-pixel value is analytic: curve(intensity * color * envelope)
(the falloff (1-r^2)^2 is exactly 1.0 with zero slope at the center).

Checks:
  1. baseline_black — empty scene anchors the byte-identity checks.
  2. near_center_analytic + near_size — world-size regime: center
     pixel exact, half-max diameter matches the projected world size.
  3. far_min_px_clamp — the SAME halo far away: half-max diameter
     tracks min_px, not the (sub-pixel) world size; center brightness
     unchanged (sprite semantics).
  4. occlusion_by_depth — an opaque card in front: the halo vanishes,
     image == baseline (rms 0). No occluder list was ever registered.
  5. blink_composition — set_blink on the bulb: mid-pulse bright at
     the exact analytic, in the gap dark == baseline (pinned clock).
  6. emission_scale_composition — set_emission_scale(bulb, 2) doubles
     the linear center value.
  7. clear_restores — clear_light_halo(): byte-identical to baseline,
     registry empty.
  8. (@directional adds) shadow_mask_exclusion — the quad is hidden
     from the sun's shadow caster mask.

Runs in both sun modes (run.py adds @directional). Only meaningful for
pax3d_render (set_light_halo lives there).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

COLOR = (1.0, 0.25, 0.25)      # nav red
INTENSITY = 0.8                # LDR-analytic-friendly
SIZE_M = 1.0
MIN_PX = 8.0
NEAR_D = 10.0
FAR_D = 400.0


def half_max_diameter(img, cx, cy, center_lum):
    """Pixel width of the region along row cy whose luminance exceeds
    half the center value (in OUTPUT space — compare against
    half_max_r() times the full on-screen diameter)."""
    thresh = center_lum * 0.5
    n = 0
    for x in range(img.get_x_size()):
        if common.lum_at(img, x, cy) > thresh:
            n += 1
    return n


def half_max_r(curve):
    """The normalized radius where the TONEMAPPED halo profile drops to
    half its center luminance. The falloff (1-r^2)^2 is linear-space;
    the capture is post-curve, so solve
    mean_ch(curve(I*c*(1-r^2)^2)) = mean_ch(curve(I*c)) / 2 by
    bisection — fully analytic, no magic constants."""
    def out_lum(fall):
        return sum(curve(INTENSITY * c * fall) for c in COLOR) / 3.0
    target = out_lum(1.0) * 0.5
    lo, hi = 0.0, 1.0
    for _ in range(48):
        mid = 0.5 * (lo + hi)
        if out_lum((1.0 - mid * mid) ** 2) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default=None,
                        choices=['uniforms', 'directional'])
    args = parser.parse_args()

    h = common.Harness(args, 'light_halo')
    if args.pipeline != 'pax3d_render':
        h.report.skip('set_light_halo lives in pax3d_render (ER-013)')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_light_halo'):
        h.report.skip('pipeline has no set_light_halo (ER-013)')
    base = h.base
    curve = common.CURVES['hejl_dawson']
    tag = args.sun_mode or 'uniforms'

    # Pin the clock: blink envelopes advance by frame time.
    clock = p3d.ClockObject.get_global_clock()
    clock.set_mode(p3d.ClockObject.M_non_real_time)
    clock.set_dt(1.0 / 30.0)

    h.adapter.update_sun((0, -1, 0), (0, 0, 0))    # sun black
    # A BLACK AmbientLight: its LightAttrib suppresses the zero-light
    # GSG quirk (nodes with no light attrib draw with a default WHITE
    # slot-0 light — Session Y, on record) without adding any light.
    alight = p3d.AmbientLight('paxtest_black_ambient')
    alight.set_color(p3d.LColor(0, 0, 0, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    base.camera.set_pos(0, 0, 0)
    base.camera.set_hpr(0, 0, 0)
    cx, cy = h.win_w // 2, h.win_h // 2

    def center_analytic(scale=1.0):
        return tuple(curve(INTENSITY * c * scale) for c in COLOR)

    def check_center(name, img, want, tol=0.03, extra=''):
        got = tuple(img.get_xel(cx, cy))
        err = max(abs(g - w) for g, w in zip(got, want))
        h.report.check(name, err < tol,
                       f'got ({got[0]:.3f},{got[1]:.3f},{got[2]:.3f}) '
                       f'want ({want[0]:.3f},{want[1]:.3f},{want[2]:.3f}) '
                       f'err {err:.3f}{extra}')

    # --- 1. Baseline: empty black scene ---------------------------------
    h.step(5)
    img_base = h.capture()
    h.save_capture(img_base, f'{tag}_baseline')
    base_lum = common.avg_lum(img_base, cx, cy)
    h.report.check('baseline_black', base_lum < 0.005,
                   f'empty scene center lum {base_lum:.4f}')

    # --- 2. Near halo: world-size regime --------------------------------
    bulb = base.render.attach_new_node('paxtest_bulb')
    bulb.set_pos(0, NEAR_D, 0)
    pipeline.set_light_halo(bulb, color=COLOR, size_m=SIZE_M,
                            min_px=MIN_PX, intensity=INTENSITY)
    h.step(5)
    img_near = h.capture()
    h.save_capture(img_near, f'{tag}_near')
    check_center('near_center_analytic', img_near, center_analytic(),
                 extra=' (unlit additive sprite through the tonemap)')

    lens = base.camLens
    proj11 = 1.0 / math.tan(math.radians(lens.get_fov()[1]) * 0.5)
    r_half = half_max_r(curve)
    px_per_world_near = proj11 * h.win_h / (2.0 * NEAR_D)
    want_near = r_half * SIZE_M * px_per_world_near
    got_near = half_max_diameter(img_near, cx, cy,
                                 common.lum_at(img_near, cx, cy))
    h.report.check('near_size', abs(got_near - want_near) < 0.25 * want_near,
                   f'half-max diameter {got_near}px, predicted '
                   f'{want_near:.1f}px (world-size regime, {SIZE_M}m at '
                   f'{NEAR_D}m; tonemapped half-max r={r_half:.3f})')

    # --- 3. Far halo: min-px clamp regime -------------------------------
    bulb.set_pos(0, FAR_D, 0)
    h.step(5)
    img_far = h.capture()
    h.save_capture(img_far, f'{tag}_far')
    world_px_far = SIZE_M * proj11 * h.win_h / (2.0 * FAR_D)
    want_far = r_half * MIN_PX
    got_far = half_max_diameter(img_far, cx, cy,
                                common.lum_at(img_far, cx, cy))
    h.report.check('far_min_px_clamp',
                   abs(got_far - want_far) <= 3
                   and world_px_far < 0.5 * MIN_PX,
                   f'half-max diameter {got_far}px, clamp predicts '
                   f'{want_far:.1f}px (world size would be '
                   f'{world_px_far:.2f}px < half of min_px {MIN_PX:.0f} '
                   f'— the clamp regime)')
    # In an 8-px halo the nearest pixel center sits ~0.7 px off the
    # projected peak (falloff ~0.94) — wider tolerance, same contract.
    check_center('far_center_analytic', img_far, center_analytic(),
                 tol=0.08,
                 extra=' (brightness independent of distance — sprite '
                       'semantics; sub-pixel peak offset tolerated)')

    # --- 4. Occlusion is the depth test ---------------------------------
    cm = p3d.CardMaker('paxtest_wall')
    cm.set_frame(-5, 5, -5, 5)
    wall = base.render.attach_new_node(cm.generate())
    wall.set_pos(0, 50, 0)                          # camera - wall - halo
    h.step(5)
    rms = common.image_rms_diff(img_base, h.capture(), step=1)
    h.report.check('occlusion_by_depth', rms == 0.0,
                   f'halo behind an opaque card: rms vs empty baseline = '
                   f'{rms:.2e} (no occluder was registered anywhere)')
    wall.remove_node()

    # --- 5. Blink composition (the ER-013 contract) ---------------------
    bulb.set_pos(0, NEAR_D, 0)
    now = clock.get_frame_time()
    # Phase the cycle so the CURRENT time sits mid-pulse (0.25 of a
    # (0.0, 0.5) pulse in a 1.0 s period), then step half a period into
    # the gap.
    pipeline.set_blink(bulb, period=1.0, pulses=((0.0, 0.5),),
                       phase=(0.25 - now) % 1.0, off_scale=0.0)
    h.step(2)
    check_center('blink_mid_pulse_bright', h.capture(), center_analytic(),
                 extra=' (envelope 1.0: halo inherits u_emission_factor)')
    h.step(15)                                      # +0.5 s -> the gap
    img_gap = h.capture()
    gap_lum = common.avg_lum(img_gap, cx, cy)
    h.report.check('blink_gap_dark', gap_lum < 0.005,
                   f'envelope 0.0: center lum {gap_lum:.4f} (halo flashes '
                   f'with its circuit, no extra wiring)')
    pipeline.clear_blink(bulb)

    # --- 6. Emission-scale composition ----------------------------------
    pipeline.set_emission_scale(bulb, 2.0)
    h.step(2)
    check_center('emission_scale_composition', h.capture(),
                 center_analytic(scale=2.0),
                 extra=' (set_emission_scale(bulb, 2) doubles the halo)')
    pipeline.clear_emission(bulb)

    # --- 7. Byte-identical opt-out --------------------------------------
    pipeline.clear_light_halo(bulb)
    bulb.remove_node()
    h.step(3)
    rms = common.image_rms_diff(img_base, h.capture(), step=1)
    h.report.check('clear_restores',
                   rms == 0.0 and not pipeline._halo_nodes,
                   f'clear_light_halo: rms vs baseline = {rms:.2e}, '
                   f'registry empty = {not pipeline._halo_nodes}')

    # --- 8. Shadow-mask exclusion (@directional) ------------------------
    if args.sun_mode == 'directional':
        pipeline.set_shadow_caster_mask(4)
        bulb2 = base.render.attach_new_node('paxtest_bulb2')
        bulb2.set_pos(0, NEAR_D, 0)
        quad = pipeline.set_light_halo(bulb2, color=COLOR)
        hidden = quad.is_hidden(pipeline.shadow_caster_mask)
        h.report.check('shadow_mask_exclusion', hidden,
                       f'halo quad hidden from the shadow caster mask = '
                       f'{hidden} (the depth pass never reads alpha — '
                       f'fact #17)')
        pipeline.clear_light_halo(bulb2)
        bulb2.remove_node()

    h.report.finish()


if __name__ == '__main__':
    main()
