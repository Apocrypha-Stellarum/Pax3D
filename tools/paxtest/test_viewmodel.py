"""paxtest: foreground viewmodel display region (FPS lane ask, 2026-07-19).

The FPS weapons package holds first-person hands ~0.04 m from the camera
while the world camera's near plane is 0.3 m (planetside) — untouched,
forearms near-clip. The standard FPS solution is a second display region
with its own camera/near-far drawn after the world. This test gates the
pax3d_render implementation (pipeline.register_viewmodel_camera):

  * the defect first: with only the world camera, viewmodel-range
    geometry is near-clipped and invisible (asserted, so the constraint
    that motivates the API stays measured);
  * registered: the viewmodel renders THROUGH the full post chain
    (tonemap analytics hold on viewmodel pixels; a bright viewmodel
    emitter feeds bloom = pre-post placement) with the pipeline's PBR
    lighting reaching it (luminance parity with an identical world
    surface lit by the same sun);
  * the world image outside the viewmodel silhouette is untouched;
  * depth_mode='clear' draws over closer world geometry; 'range' does
    too WITHOUT stomping the scene depth texture (SSAO-friendly) —
    both proven by scene depth-texture readback;
  * unregister restores the frame byte-identically and the main camera
    mask exactly; region + depth-range state survive FilterManager
    rebuilds (SSAO toggle, bloom toggle);
  * @directional (+shadows): the viewmodel contributes ZERO texels to
    the sun depth map (VIEWMODEL_BIT reservation) and the sun camera's
    mask has the bit cleared.

Geometry: wall (albedo .8) at y=20, box (blue) at y=1 covering screen
center — the box is CLOSER in the shared depth buffer than the
viewmodel's own depth values, so "viewmodel visible at center" is only
true if the depth strategy (clear or range-compress) actually worked.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes

HFOV = 45.0
TAN_HALF = math.tan(math.radians(HFOV / 2.0))

VM_Y = 0.12          # viewmodel content distance (well inside near 0.3)
VM_EMISSIVE = 0.5    # linear HDR value of the center viewmodel quad
WALL_ALBEDO = 0.8


def px_of(x, y, win):
    """Screen x pixel of world point (x, y, 0) through the HFOV lens."""
    return int(round((0.5 + 0.5 * (x / y) / TAN_HALF) * (win - 1)))


def corner_boxes(w, h, size=48, margin=24):
    return [(margin, margin, size), (w - margin - size, margin, size),
            (margin, h - margin - size, size),
            (w - margin - size, h - margin - size, size)]


def region_max_diff(a, b, boxes):
    worst = 0.0
    for (x0, y0, size) in boxes:
        for yy in range(y0, y0 + size, 2):
            for xx in range(x0, x0 + size, 2):
                d = abs(common.lum_at(a, xx, yy) - common.lum_at(b, xx, yy))
                worst = max(worst, d)
    return worst


def scene_depth_texture(pipeline):
    buf = pipeline._scene_buffer()
    if buf is None:
        return None
    for i in range(buf.count_textures()):
        plane = buf.get_texture_plane(i)
        if plane in (p3d.GraphicsOutput.RTP_depth,
                     p3d.GraphicsOutput.RTP_depth_stencil):
            return buf.get_texture(i)
    return None


def depth_at(img, x, y):
    return img.get_gray(x, y) if img is not None else -1.0


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default=None,
                        help='pax3d_render: uniforms|directional')
    args = parser.parse_args()

    h = common.Harness(args, 'viewmodel')
    if not h.adapter.supports_camera_registration:
        h.report.skip('pipeline has no camera-registration API')

    sun_mode = args.sun_mode or 'uniforms'
    directional = sun_mode == 'directional'
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=sun_mode, shadows=directional)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'register_viewmodel_camera'):
        h.report.skip('pipeline has no register_viewmodel_camera')

    # World lens: the planetside shape — perspective, near 0.3
    lens = p3d.PerspectiveLens()
    lens.set_fov(HFOV)
    lens.set_near_far(0.3, 100.0)
    h.base.cam.node().set_lens(lens)

    h.adapter.update_sun((0, -1, 0), (1, 1, 1))

    render = h.base.render
    # Wall: fills the view at 20 m
    wall = scenes._make_card(render, 15.0, 15.0, 'vm_wall')
    scenes.apply_flat_pbr_surface(wall, (WALL_ALBEDO,) * 3)
    wall.set_pos(0, 20, 0)
    # Box: covers screen center at 1 m — CLOSER in shared window depth
    # than the viewmodel's own writes; discriminates the depth strategy
    box = scenes._make_card(render, 0.08, 0.08, 'vm_box')
    scenes.apply_flat_pbr_surface(box, (0.1, 0.25, 0.8))
    box.set_pos(0, 1.0, 0)
    # Lighting-parity reference card in the WORLD, screen-left
    world_card = scenes._make_card(render, 0.5, 0.5, 'vm_parity_world')
    scenes.apply_flat_pbr_surface(world_card, (WALL_ALBEDO,) * 3)
    world_card.set_pos(-2.1, 10.0, 0)
    # Black backdrop ring for the bloom-halo measurement: an unlit black
    # card behind the box — the lit wall is tonemap-saturated (~0.85) and
    # ambient keeps it bright even with the sun dimmed, so the halo must
    # land on true black to be measurable. Covers screen radius ~52-111px;
    # the box hides its center, the parity/corner samples sit outside it.
    dark = scenes.make_emissive_quad(render, h.use_330, 0.0, 0.9)
    dark.set_pos(0, 5.0, 0)

    # Viewmodel subtree, parented to the main camera (the blessed spot)
    vm_root = h.base.cam.attach_new_node('vm_root')
    vm_quad = scenes.make_emissive_quad(vm_root, h.use_330,
                                        VM_EMISSIVE, 0.006)
    vm_quad.set_pos(0, VM_Y, 0)
    vm_card = scenes._make_card(vm_root, 0.006, 0.006, 'vm_parity_vm')
    scenes.apply_flat_pbr_surface(vm_card, (WALL_ALBEDO,) * 3)
    vm_card.set_pos(-0.0255, VM_Y, 0)
    vm_root.stash()

    w, hgt = h.win_w, h.win_h
    cx, cy = w // 2, hgt // 2
    parity_world_px = px_of(-2.1, 10.0, w)
    parity_vm_px = px_of(-0.0255, VM_Y, w)
    corners = corner_boxes(w, hgt)

    h.step(3)
    img_a0 = h.capture()
    h.save_capture(img_a0, f'{sun_mode}_baseline')
    box_lum = common.avg_lum(img_a0, cx, cy)

    # --- The defect: near plane 0.3 clips viewmodel-range content -------
    vm_root.unstash()
    h.step(2)
    img = h.capture()
    c = common.avg_lum(img, cx, cy)
    h.report.check('near_clip_hides_vm_without_region',
                   abs(c - box_lum) < 0.01,
                   f'center {c:.3f} vs box {box_lum:.3f} '
                   f'(vm at {VM_Y}m, near 0.3m)')

    # --- Register: viewmodel visible, tonemapped, lit, world untouched --
    prev_mask = p3d.DrawMask(h.base.cam.node().get_camera_mask())
    reg = pipeline.register_viewmodel_camera(vm_root, near=0.02, far=8.0)
    h.step(2)
    img_b = h.capture()
    h.save_capture(img_b, f'{sun_mode}_registered')

    expected = common.expected_output('hejl_dawson', VM_EMISSIVE)
    c = common.avg_lum(img_b, cx, cy)
    h.report.check('vm_tonemapped_over_closer_world',
                   abs(c - expected) < 0.02,
                   f'center {c:.3f} vs analytic {expected:.3f} '
                   f'(box at 1m would read {box_lum:.3f})')

    lw = common.avg_lum(img_b, parity_world_px, cy)
    lv = common.avg_lum(img_b, parity_vm_px, cy)
    h.report.check('world_lit_sanity', lw > 0.15, f'world card {lw:.3f}')
    h.report.check('vm_lighting_parity', abs(lw - lv) < 0.03,
                   f'world {lw:.3f} vs viewmodel {lv:.3f}')

    d = region_max_diff(img_a0, img_b, corners)
    h.report.check('world_unchanged_outside_vm', d < 0.005,
                   f'corner max diff {d:.5f}')

    # --- Unregister: byte-identical restore, mask restore ---------------
    pipeline.unregister_viewmodel_camera(reg)
    h.step(2)
    img_c = h.capture()
    rms = common.image_rms_diff(img_a0, img_c, step=2)
    h.report.check('unregister_restores_frame', rms < 1e-6,
                   f'rms vs baseline {rms:.7f}')
    h.report.check('unregister_restores_camera_mask',
                   h.base.cam.node().get_camera_mask() == prev_mask,
                   str(h.base.cam.node().get_camera_mask()))

    # --- depth_mode='range': wins depth without clearing ----------------
    # Stock 1.10 has no DisplayRegion.set_depth_range (1.11 API); the
    # pipeline falls back to 'clear' there — proven usable either way.
    has_range = hasattr(p3d.DisplayRegion, 'set_depth_range')
    reg = pipeline.register_viewmodel_camera(vm_root, near=0.02, far=8.0,
                                             depth_mode='range')
    h.step(2)
    img_d = h.capture()
    c = common.avg_lum(img_d, cx, cy)
    tag = 'range_mode' if has_range else 'range_fallback_to_clear'
    h.report.check(f'{tag}_draws_over_world', abs(c - expected) < 0.02,
                   f'center {c:.3f} vs analytic {expected:.3f}')

    # --- SSAO rebuild: region + depth range survive; depth readback -----
    pipeline.set_enable_ssao(True)
    h.step(3)
    img_e = h.capture()
    h.save_capture(img_e, f'{sun_mode}_ssao_range')
    c = common.avg_lum(img_e, cx, cy)
    h.report.check('vm_survives_ssao_rebuild', abs(c - expected) < 0.04,
                   f'center {c:.3f} (depth_range must be re-applied '
                   f'on the rebuilt buffer)' if has_range
                   else f'center {c:.3f}')

    dtex = scene_depth_texture(pipeline)
    d_reg = common.read_depth_image(h.base, dtex)
    pipeline.unregister_viewmodel_camera(reg)
    h.step(2)
    dtex = scene_depth_texture(pipeline)
    d_ref = common.read_depth_image(h.base, dtex)
    if d_reg is None or d_ref is None:
        h.report.info('depth_readback', 'unavailable — skipping depth checks')
    elif has_range:
        corner_diff = abs(depth_at(d_reg, 40, 40) - depth_at(d_ref, 40, 40))
        h.report.check('range_mode_preserves_world_depth',
                       corner_diff < 1e-5,
                       f'corner depth diff {corner_diff:.6f}')
        # PNM y is top-down; depth image rows are bottom-up vs screenshot,
        # but dead center is dead center either way.
        zc_vm = depth_at(d_reg, cx, cy)
        zc_ref = depth_at(d_ref, cx, cy)
        h.report.check('range_mode_vm_writes_front_slice',
                       zc_vm < 0.06 and zc_ref > 0.5,
                       f'center depth vm {zc_vm:.3f} vs box {zc_ref:.3f}')

        # 'clear' stomps the whole depth target — asserted as the
        # documented limitation (a future depth strategy change must
        # true this row up, alpha-mask defect-row style)
        reg = pipeline.register_viewmodel_camera(vm_root,
                                                 near=0.02, far=8.0)
        h.step(2)
        dtex = scene_depth_texture(pipeline)
        d_clear = common.read_depth_image(h.base, dtex)
        stomp = abs(depth_at(d_clear, 40, 40) - depth_at(d_ref, 40, 40))
        h.report.check('clear_mode_stomps_world_depth_documented',
                       stomp > 1e-4,
                       f'corner depth diff {stomp:.4f} (SSAO needs '
                       f'depth_mode="range")')
        pipeline.unregister_viewmodel_camera(reg)
    else:
        # Fallback engine: the registered region cleared depth — the
        # stomp is the expected (documented) shape here
        stomp = abs(depth_at(d_reg, 40, 40) - depth_at(d_ref, 40, 40))
        h.report.check('clear_fallback_stomps_world_depth_documented',
                       stomp > 1e-4,
                       f'corner depth diff {stomp:.4f} (no set_depth_range '
                       f'on this engine; SSAO+viewmodel needs Pax3D)')

    pipeline.set_enable_ssao(False)
    h.step(3)
    img_h = h.capture()
    rms = common.image_rms_diff(img_a0, img_h, step=2)
    h.report.check('full_restore_after_churn', rms < 1e-6,
                   f'rms vs baseline {rms:.7f}')

    # --- Bloom: rebuild survival + the viewmodel feeds the extract ------
    reg = pipeline.register_viewmodel_camera(vm_root, near=0.02, far=8.0)
    h.adapter.set_bloom_enabled(True)
    h.step(3)
    img_dim = h.capture()
    c = common.avg_lum(img_dim, cx, cy)
    h.report.check('vm_survives_bloom_rebuild', abs(c - expected) < 0.04,
                   f'center {c:.3f}')
    halo_px = 70
    halo_dim = (common.avg_lum(img_dim, cx + halo_px, cy)
                + common.avg_lum(img_dim, cx - halo_px, cy)) / 2.0
    vm_quad.set_shader_input('u_value', 4.0)
    h.step(2)
    img_hot = h.capture()
    h.save_capture(img_hot, f'{sun_mode}_bloom_hot')
    halo_hot = (common.avg_lum(img_hot, cx + halo_px, cy)
                + common.avg_lum(img_hot, cx - halo_px, cy)) / 2.0
    h.report.check('vm_feeds_bloom', halo_hot > halo_dim + 0.02,
                   f'halo {halo_dim:.3f} -> {halo_hot:.3f} '
                   f'(viewmodel rides the HDR buffer pre-post)')
    vm_quad.set_shader_input('u_value', VM_EMISSIVE)
    h.adapter.set_bloom_enabled(False)
    h.step(2)

    # --- @directional: zero texels in the sun depth map -----------------
    if directional and pipeline.sun_light_np is not None:
        bit = p3d.DrawMask.bit(pipeline.VIEWMODEL_BIT)
        mask = pipeline.sun_light_np.node().get_camera_mask()
        h.report.check('shadow_mask_clears_vm_bit', (mask & bit).is_zero(),
                       str(mask))
        # Make the viewmodel BIG so any leak would rasterize decisively
        vm_quad.set_scale(20)
        h.step(2)
        ltex = common.find_light_depth_texture(pipeline.sun_light_np)
        m1 = common.read_depth_image(h.base, ltex)
        pipeline.unregister_viewmodel_camera(reg)
        h.step(2)
        ltex = common.find_light_depth_texture(pipeline.sun_light_np)
        m0 = common.read_depth_image(h.base, ltex)
        n = common.count_gray_diff(m0, m1)
        h.report.check('vm_absent_from_shadow_map', n == 0,
                       f'{n} texels differ with viewmodel registered')
    else:
        pipeline.unregister_viewmodel_camera(reg)

    h.report.finish()


if __name__ == '__main__':
    main()
