"""paxtest: SSAO first slice (Session S).

`enable_ssao` — depth-only screen-space ambient obscurance
(ssao.frag documents the estimator), blurred and multiplied into the
scene HDR color in tonemap BEFORE the bloom add and tone curve.
Opt-in; the defining property gated here is that FLAT geometry
produces AO exactly 1.0, so the multiply is an exact no-op — SSAO can
only ever darken actual concavities.

Scene: a wall facing the camera plus a floor and ceiling forming a
horizontal slot — two wall/slab creases symmetric about the screen
center (sampling both crease rows makes the checks independent of the
screenshot row-order convention).

Checks:
  1. Baselines with the feature off (plane / slot scenes).
  2. plane_byte_identical — SSAO ON over the constant-depth wall
     renders rms 0.0 vs off: every tap lies in the tangent plane,
     dot(v, n) == 0, AO == 1.0 exactly, exact multiply.
  3. corner_darkens — both crease rows darken vs the off capture.
  4. far_region_unaffected — the wall center (>= 3 units from either
     crease, ao_radius 1) is unchanged within 8-bit AO tolerance.
  5. intensity_monotonic — ao_intensity 2.0 deepens the crease vs 1.0.
  6. intensity_zero_exact_noop — ao_intensity 0.0 renders rms 0.0 vs
     off even with the feature compiled in (clamp(1 - 0*occ) == 1).
  7. opt_out_restores — set_enable_ssao(False) restores the off
     capture exactly (the rebuild-class toggle round-trips).

Variants: --log-depth runs the same checks with the log-depth
inversion under a wide 0.1/1e9 frustum (the R4.1 composition);
--msaa 4 measures the multisampled-depth resolve path (the game's
default msaa_samples=4).

Only meaningful for pipelines exposing set_enable_ssao (pax3d_render
and the routed pax_pbr adapter).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


AMB = 0.5           # flat ambient so surfaces carry mid-gray luminance
SLOT_HALF = 3.0     # floor/ceiling at z = -/+ 3
CAM_DIST = 30.0


def make_card(parent, half, name):
    cm = p3d.CardMaker(name)
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    np.set_two_sided(True)
    scenes.apply_flat_pbr_surface(np, rgb=(1, 1, 1))
    return np


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--log-depth', action='store_true',
                        help='run the same checks under enable_log_depth '
                             'with a wide 0.1/1e9 frustum (R4.1)')
    args = parser.parse_args()

    h = common.Harness(args, 'ssao')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    log_depth=args.log_depth)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_enable_ssao'):
        h.report.skip('pipeline has no set_enable_ssao (Session S)')
    base = h.base

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))     # sun black

    base.camera.set_pos(0, -CAM_DIST, 0)
    base.camera.set_hpr(0, 0, 0)
    if args.log_depth:
        base.camLens.set_near_far(0.1, 1e9)

    wall = make_card(base.render, 12, 'wall')          # XZ plane at y=0
    floor = make_card(base.render, 12, 'floor')
    floor.set_p(-90)
    floor.set_z(-SLOT_HALF)
    ceil = make_card(base.render, 12, 'ceiling')
    ceil.set_p(-90)
    ceil.set_z(SLOT_HALF)

    cx, cy = h.win_w // 2, h.win_h // 2
    # Crease rows: the wall/slab junction lines at z = -/+ SLOT_HALF
    # project to +/- SLOT_HALF / (CAM_DIST * tan(fov/2)) in NDC. Sample
    # BOTH candidate rows — the slot is symmetric, so both are creases
    # under either screenshot row-order convention.
    import math
    fov = base.camLens.get_fov()
    ndc_off = SLOT_HALF / (CAM_DIST * math.tan(math.radians(fov[1]) * 0.5))
    row_a = int((0.5 - ndc_off * 0.5) * h.win_h)
    row_b = int((0.5 + ndc_off * 0.5) * h.win_h)

    def lum_at(img, x, y):
        return common.avg_lum(img, x, y)

    def crease_lum(img, x, row):
        """Min luminance within +/-3 rows of the analytic crease line —
        the MSAA depth resolve (and int() truncation) can shift the
        darkest line by a pixel, so pin the SAMPLE to the measured
        minimum near the prediction (fact-#12 discipline: verify the
        sample point actually lies on the feature)."""
        return min(common.avg_lum(img, x, r)
                   for r in range(row - 3, row + 4))

    # --- 1. Baselines: feature off ---------------------------------------
    floor.hide()
    ceil.hide()
    h.step(5)
    img_off_plane = h.capture()
    h.save_capture(img_off_plane, 'off_plane')
    floor.show()
    ceil.show()
    h.step(5)
    img_off_slot = h.capture()
    h.save_capture(img_off_slot, 'off_slot')
    off_a = crease_lum(img_off_slot, cx, row_a)
    off_b = crease_lum(img_off_slot, cx, row_b)
    off_c = lum_at(img_off_slot, cx, cy)

    # --- 2. Plane: SSAO on == off, byte-identical -------------------------
    pipeline.set_enable_ssao(True)
    floor.hide()
    ceil.hide()
    h.step(5)
    img_ao_plane = h.capture()
    h.save_capture(img_ao_plane, 'ao_plane')
    rms = common.image_rms_diff(img_off_plane, img_ao_plane, step=1)
    h.report.check('plane_byte_identical', rms == 0.0,
                   f'constant-depth wall with SSAO on: rms vs off = '
                   f'{rms:.2e} (flat geometry -> AO exactly 1.0, exact '
                   f'multiply)')

    # --- 3/4. Slot: creases darken, wall center untouched -----------------
    floor.show()
    ceil.show()
    h.step(5)
    img_ao = h.capture()
    h.save_capture(img_ao, 'ao_slot')
    ao_a = crease_lum(img_ao, cx, row_a)
    ao_b = crease_lum(img_ao, cx, row_b)
    ao_c = lum_at(img_ao, cx, cy)
    h.report.check(
        'corner_darkens', ao_a < off_a - 0.02 and ao_b < off_b - 0.02,
        f'crease rows darken: {off_a:.3f}->{ao_a:.3f} and '
        f'{off_b:.3f}->{ao_b:.3f} (screen-space obscurance in the '
        f'wall/slab junctions)')
    h.report.check(
        'far_region_unaffected', abs(ao_c - off_c) < 0.02,
        f'wall center ({SLOT_HALF:.0f} units from either crease, radius '
        f'1.0): lum {off_c:.3f} -> {ao_c:.3f} (within 8-bit AO '
        f'tolerance)')

    # --- 5. Intensity is monotonic ----------------------------------------
    pipeline.set_ao_intensity(2.0)
    h.step(5)
    img_ao2 = h.capture()
    h.save_capture(img_ao2, 'ao_slot_x2')
    ao2_a = crease_lum(img_ao2, cx, row_a)
    h.report.check('intensity_monotonic', ao2_a < ao_a - 0.005,
                   f'ao_intensity 1.0 -> 2.0 deepens the crease: '
                   f'{ao_a:.3f} -> {ao2_a:.3f}')

    # --- 6. Intensity 0 is an exact no-op ---------------------------------
    pipeline.set_ao_intensity(0.0)
    h.step(5)
    img_zero = h.capture()
    rms = common.image_rms_diff(img_off_slot, img_zero, step=1)
    h.report.check('intensity_zero_exact_noop', rms == 0.0,
                   f'ao_intensity 0.0 with the feature on: rms vs off = '
                   f'{rms:.2e} (clamp(1 - 0*occ) == 1 exactly)')

    # --- 7. Opt-out restores ----------------------------------------------
    pipeline.set_ao_intensity(1.0)
    pipeline.set_enable_ssao(False)
    h.step(5)
    img_restored = h.capture()
    rms = common.image_rms_diff(img_off_slot, img_restored, step=1)
    h.report.check('opt_out_restores', rms == 0.0,
                   f'set_enable_ssao(False): rms vs the pre-enable '
                   f'capture = {rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
