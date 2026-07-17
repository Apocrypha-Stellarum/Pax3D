"""paxtest: shadow-frustum texel snapping (Session J, backlog item).

The planetside shimmer killer: a shadow frustum that follows the camera
(the openworld pattern) re-rasterizes the depth map on every sub-texel
center move, which makes every shadow edge crawl while the viewer walks.
`shadow_texel_snap` quantizes the frustum center to the shadow-map texel
grid along the light's film axes, so the depth map only changes on whole-
texel steps — the openworld `_follow_shadow_frustum` workaround, moved
into the engine for everyone.

Checks:
  1. Default off; a sub-texel center move re-rasterizes the depth map
     (teeth: this IS the shimmer source, measured).
  2. Enabling snap at an on-grid center is byte-identical on screen.
  3. With snap on, a sweep of sub-texel center moves leaves the depth map
     AND the screen exactly unchanged (the anti-shimmer property).
  4. A whole-texel move does re-rasterize (snap must not freeze the
     frustum — it has to follow the camera in texel steps).
  5. Disabling snap restores the requested center exactly.

Only meaningful for pipelines with a directional sun mode + the snap API
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


MAP = 512
EXTENT, DEPTH = 30.0, 200.0
TEXEL = 2.0 * EXTENT / MAP           # 0.117 world units
SUN = (0.5, 0.3, 0.8)                # oblique: film axes not world-aligned
CASTER_H = 2.0
CASTER_HALF = 2.0


def make_flat_card(parent, half, name, z=0.0, rgb=(0.8, 0.8, 0.8)):
    cm = p3d.CardMaker(name)
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    np.set_p(-90)
    np.set_z(z)
    np.set_two_sided(True)
    scenes.apply_flat_pbr_surface(np, rgb=rgb)
    return np


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'shadow_snap')
    if not getattr(h.adapter, 'supports_sun_modes', False):
        h.report.skip('pipeline has no directional sun mode')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode='directional', shadows=True,
                    extra_pipeline_kwargs={'shadow_map_size': MAP})
    pipeline = h.adapter.pipeline
    if not hasattr(pipeline, 'set_shadow_texel_snap'):
        h.report.skip('pipeline has no set_shadow_texel_snap')
    base = h.base

    pipeline.set_shadow_bias(0.05, world_units=True)
    pipeline.set_shadow_extent(EXTENT, DEPTH, center=(0, 0, 0))

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(0.02, 0.02, 0.02, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    make_flat_card(base.render, 100, 'ground', z=0.0)
    make_flat_card(base.render, CASTER_HALF, 'caster', z=CASTER_H,
                   rgb=(0.9, 0.15, 0.15))

    base.camera.set_pos(0, 0, 40)
    base.camera.set_hpr(0, -90, 0)
    h.set_ortho(film_h=40.0)

    h.adapter.update_sun(SUN, (3, 3, 3))
    h.step(5)

    def depth_map():
        tex = common.find_light_depth_texture(pipeline.sun_light_np)
        return common.read_depth_image(base, tex)

    def recenter(offset_vec):
        pipeline.set_shadow_extent(EXTENT, DEPTH, center=offset_vec)
        h.step(3)

    # The light's film-x axis in world space: moving the center along it by
    # k*TEXEL projects to exactly k texels on the snap grid — makes every
    # threshold in this test exact instead of sun-angle-dependent.
    right = pipeline.sun_light_np.get_quat(base.render).get_right()

    h.report.check('snap_defaults_off',
                   pipeline.shadow_texel_snap is False,
                   'shadow_texel_snap defaults to False (byte-identical '
                   'shipped behavior)')

    d_origin = depth_map()
    img_off = h.capture()
    h.save_capture(img_off, 'nosnap_origin')
    if d_origin is None:
        h.report.skip('depth-map readback unavailable on this driver')

    # --- 1. Teeth: sub-texel move re-rasterizes without snap ------------
    recenter(p3d.Vec3(right) * (0.3 * TEXEL))
    d_sub = depth_map()
    diff = common.count_gray_diff(d_origin, d_sub)
    h.report.check('nosnap_subtexel_rerasters', diff > 0,
                   f'0.3-texel center move, snap off: {diff} depth texels '
                   f'changed — every sub-texel step redraws the map (the '
                   f'shimmer source)')
    recenter(p3d.Vec3(0, 0, 0))

    # --- 2. Enabling snap on-grid is byte-identical ---------------------
    pipeline.set_shadow_texel_snap(True)
    h.step(3)
    img_snap_origin = h.capture()
    rms = common.image_rms_diff(img_off, img_snap_origin, step=1)
    h.report.check('snap_on_grid_identical', rms == 0.0,
                   f'snap enabled at an on-grid center: screen rms='
                   f'{rms:.2e} (no behavior change until the center '
                   f'actually moves)')

    # --- 3. Anti-shimmer: sub-texel sweep is depth- and screen-stable ---
    d_snap = depth_map()
    stable = True
    details = []
    for frac in (0.15, 0.3, 0.45):
        recenter(p3d.Vec3(right) * (frac * TEXEL))
        d_i = depth_map()
        img_i = h.capture()
        ddiff = common.count_gray_diff(d_snap, d_i)
        srms = common.image_rms_diff(img_snap_origin, img_i, step=1)
        details.append(f'{frac:.2f}tx: depth diff {ddiff}, rms {srms:.1e}')
        if ddiff != 0 or srms != 0.0:
            stable = False
    h.report.check('snap_subtexel_stable', stable,
                   f'sub-texel center sweep with snap on: depth map and '
                   f'screen unchanged [{"; ".join(details)}] — shadow '
                   f'edges cannot shimmer while the frustum follows a '
                   f'walking camera')

    # --- 4. Whole-texel step still re-rasterizes ------------------------
    recenter(p3d.Vec3(right) * (2.0 * TEXEL))
    d_two = depth_map()
    diff = common.count_gray_diff(d_snap, d_two)
    h.report.check('snap_whole_texel_moves', diff > 0,
                   f'2-texel center move with snap on: {diff} depth texels '
                   f'changed — the frustum follows in whole-texel steps, '
                   f'it is not frozen')

    # --- 5. Disable restores the requested center exactly ---------------
    recenter(p3d.Vec3(0, 0, 0))
    pipeline.set_shadow_texel_snap(False)
    h.step(3)
    img_restored = h.capture()
    rms = common.image_rms_diff(img_off, img_restored, step=1)
    h.report.check('snap_off_restores', rms == 0.0,
                   f'snap disabled, center restored: screen rms={rms:.2e} '
                   f'vs the original no-snap capture')

    h.report.finish()


if __name__ == '__main__':
    main()
