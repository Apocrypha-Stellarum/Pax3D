"""paxtest: photo-mode snapshot camera (Session AJ — the paxcraft
AI-building ask, 2026-07-27).

pipeline.render_snapshot(pos, hpr, size) renders ONE frame of the full
pipeline (PBR, shadows, SSAO, bloom, tonemap) from an arbitrary camera
pose into an offscreen buffer and returns a RAM-backed texture —
without perturbing the player's view. The driving use case is a
building AI screenshotting its own build to iterate; the same
machinery is photo mode / kill-cam for the games.

Scene (perspective camera at (0,-30,0) looking +Y): a white 'subject'
card at the origin fills the main view; a RED 'secret' card sits at
y=-60 — BEHIND the main camera, visible only from a snapshot pose
further back. Checks:

  1. returns_ram_texture — requested size, RAM image present,
     filename= writes the PNG.
  2. arbitrary_pose_sees_hidden — the snapshot from (0,-90,0) shows
     the red secret card (red-dominant center; the main capture shows
     only the white subject).
  3. player_view_unperturbed — window frame before vs after a
     snapshot: rms 0.0 (the player chain is deactivated for the shot;
     the window keeps its last presented image).
  4. full_pipeline_parity — a snapshot from the main camera's own
     pose at window size matches the window capture (the snapshot
     chain runs the same shaders at the same sizes).
  5. bloom_in_snapshot — with bloom OFF a hot HDR quad shows no halo
     in the snapshot; pipeline.set_enable_bloom(True) (rebuild-class —
     exercises the snapshot chain invalidation) and the halo appears.
  6. resize — a different size rebuilds the chain correctly.
  7. (@directional) THE SHADOW CONTRACT — a cluster at x=5000, far
     outside a tight shadow extent centered at the origin: the plain
     snapshot samples LIT ground (documented coupling — the extent is
     game-recentred on the main camera), shadow_center=(5000,0,0)
     recentres for the one frame and the caster's shadow appears, and
     the pipeline's shadow center is restored exactly afterwards.
  8. repeat-shot timing INFO (persistent chain: one extra rendered
     frame per shot, the AI-loop latency).
  9. FOLLOW CAMERAS (Session AK, the far-field lane): a separate-graph
     background scene (own root, own const shader — the horizon-ring
     recipe) with a BRIGHT quad due north and a DIM quad due east,
     drawn by an aux camera registered with follow='pose' at sort -50.
     Checks: the pipeline mirrors the main camera onto it each frame;
     background pixels survive the main region (bright north / dim
     east in the WINDOW); a snapshot aimed east shows the east
     background while the player looks north (snapshot re-aims follow
     cameras) and the follow camera's transform is restored after the
     shot; follow='hpr' copies rotation only (sky-dome idiom); and
     unregistering the last background camera restores the main
     region's original clears (the subject renders normally again).

Only meaningful for pipelines exposing render_snapshot (pax3d_render).
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes

AMB = 0.25
SUN = 0.6


def make_card(parent, name, half_w, half_h):
    cm = p3d.CardMaker(name)
    cm.set_frame(-half_w, half_w, -half_h, half_h)
    np = parent.attach_new_node(cm.generate())
    mat = p3d.Material(name + '_mat')
    mat.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat.set_metallic(0.0)
    mat.set_roughness(0.4)
    np.set_material(mat, 1)
    return np


def tex_to_img(tex):
    img = p3d.PNMImage()
    if not tex.store(img):
        raise RuntimeError('texture store failed (no RAM image?)')
    return img


def avg_rgb(img, cx, cy, half=2):
    r = g = b = 0.0
    n = 0
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            c = img.get_xel(int(cx) + dx, int(cy) + dy)
            r += c[0]
            g += c[1]
            b += c[2]
            n += 1
    return r / n, g / n, b / n


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default=None,
                        choices=['uniforms', 'directional'])
    args = parser.parse_args()

    directional = args.sun_mode == 'directional'
    h = common.Harness(args, 'snapshot')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode, shadows=directional)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'render_snapshot'):
        h.report.skip('pipeline has no render_snapshot (Session AJ)')
    base = h.base

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (SUN, SUN, SUN))

    base.camera.set_pos(0, -30, 0)
    base.camera.set_hpr(0, 0, 0)

    subject = make_card(base.render, 'subject', 8.0, 8.0)
    secret = make_card(base.render, 'secret', 6.0, 6.0)
    secret.set_pos(0, -60, 0)
    secret.find_material('secret_mat').set_base_color(
        p3d.LColor(1.0, 0.15, 0.15, 1))

    h.step(5)
    img_control = h.capture()
    h.save_capture(img_control, 'main_view')

    # --- 1/2. One shot from a pose the player cannot see ----------------
    os.makedirs(common.OUTPUT_DIR, exist_ok=True)
    png_path = os.path.join(
        common.OUTPUT_DIR,
        f'snapshot_{args.pipeline}_secret.png')
    tex = pipeline.render_snapshot((0, -90, 0), (0, 0, 0),
                                   size=(320, 240), filename=png_path)
    h.report.check('returns_ram_texture',
                   tex is not None and tex.has_ram_image()
                   and tex.get_x_size() == 320
                   and tex.get_y_size() == 240
                   and os.path.exists(png_path),
                   f'{tex.get_x_size()}x{tex.get_y_size()}, '
                   f'ram={tex.has_ram_image()}, png written='
                   f'{os.path.exists(png_path)}')
    snap = tex_to_img(tex)
    r, g, b = avg_rgb(snap, 160, 120)
    # White specular + ambient lift G/B on the red card, so the check
    # is red-DOMINANT, not red-pure (measured (0.73, 0.46, 0.46)).
    h.report.check('arbitrary_pose_sees_hidden',
                   r > 0.5 and r > g + 0.15,
                   f'snapshot center rgb=({r:.3f}, {g:.3f}, {b:.3f}) — '
                   f'the RED secret card behind the player renders '
                   f'from the snapshot pose (invisible to the main '
                   f'camera, its capture is the white subject)')

    # --- 3. The player view is untouched --------------------------------
    h.step(1)
    rms = common.image_rms_diff(img_control, h.capture(), step=1)
    h.report.check('player_view_unperturbed', rms == 0.0,
                   f'window frame after the snapshot vs before: '
                   f'rms={rms:.2e} (the player chain sat out exactly '
                   f'one engine frame)')

    # --- 4. Snapshot == the full pipeline -------------------------------
    tex = pipeline.render_snapshot((0, -30, 0), (0, 0, 0),
                                   size=(h.win_w, h.win_h))
    snap_main = tex_to_img(tex)
    h.save_capture(snap_main, 'parity')
    rms = common.image_rms_diff(img_control, snap_main, step=1)
    h.report.check('full_pipeline_parity', rms < 0.02,
                   f'snapshot from the main camera pose vs the window '
                   f'capture: rms={rms:.4f} (same shaders, same '
                   f'chain structure, same size)')

    # --- 5. Bloom reaches the snapshot; rebuild-class invalidation ------
    hot = scenes.make_emissive_quad(base.render, h.use_330, 1000.0, 0.5)
    hot.set_pos(0, -60, 20)
    snap_pos = (0, -90, 20)
    tex = pipeline.render_snapshot(snap_pos, (0, 0, 0), size=(320, 240))
    halo_off = common.avg_lum(tex_to_img(tex), 160 + 24, 120, half=2)
    pipeline.set_enable_bloom(True)     # rebuild-class: snapshot chain
    h.step(2)                           # must invalidate + rebuild
    tex = pipeline.render_snapshot(snap_pos, (0, 0, 0), size=(320, 240))
    snap_bloom = tex_to_img(tex)
    h.save_capture(snap_bloom, 'bloom')
    halo_on = common.avg_lum(snap_bloom, 160 + 24, 120, half=2)
    core = common.avg_lum(snap_bloom, 160, 120, half=2)
    h.report.check('bloom_in_snapshot',
                   core > 0.5 and halo_on > halo_off + 0.05,
                   f'hot-quad core={core:.3f}; halo pixel 24px off: '
                   f'{halo_off:.3f} (bloom off) -> {halo_on:.3f} '
                   f'(bloom on — the snapshot chain rebuilt with the '
                   f'bloom stages)')
    hot.remove_node()

    # --- 6. Resize rebuilds correctly -----------------------------------
    tex = pipeline.render_snapshot((0, -90, 0), (0, 0, 0),
                                   size=(160, 120))
    h.report.check('resize',
                   tex.get_x_size() == 160 and tex.get_y_size() == 120
                   and tex.has_ram_image(),
                   f'{tex.get_x_size()}x{tex.get_y_size()}, '
                   f'ram={tex.has_ram_image()}')

    # --- 6b. The SSAO branch of the snapshot chain ----------------------
    # Flat-scene identity is SSAO's defining property (test_ssao): with
    # the depth target + AO passes in the snapshot chain, a flat-card
    # scene must render identically to SSAO off.
    tex = pipeline.render_snapshot((0, -90, 0), (0, 0, 0),
                                   size=(320, 240))
    snap_no_ao = tex_to_img(tex)
    pipeline.set_enable_ssao(True)      # rebuild-class again
    h.step(2)
    tex = pipeline.render_snapshot((0, -90, 0), (0, 0, 0),
                                   size=(320, 240))
    rms = common.image_rms_diff(snap_no_ao, tex_to_img(tex), step=1)
    h.report.check('ssao_chain_flat_identity', rms < 0.005,
                   f'snapshot with SSAO on vs off, flat-card scene: '
                   f'rms={rms:.2e} (depth target + AO passes live in '
                   f'the snapshot chain; flat geometry is AO 1.0)')
    pipeline.set_enable_ssao(False)
    h.step(2)

    # --- 7. The shadow-extent contract (@directional) -------------------
    if directional:
        pipeline.set_shadow_extent(50.0, depth=200.0, center=(0, 0, 0))
        ground = make_card(base.render, 'far_ground', 12.0, 12.0)
        ground.set_p(-90)
        ground.set_pos(5000, 0, 0)
        caster = make_card(base.render, 'far_caster', 2.5, 2.5)
        caster.set_p(-90)
        caster.set_pos(5000, 0, 8)
        # Tilted sun: the shadow lands BESIDE the caster (straight
        # overhead, the caster hides its own shadow from a top-down
        # camera). dx/dz = 0.4 -> the z=8 caster's shadow shifts -3.2
        # in x; sample at x=4996 (inside the shadow band, clear of the
        # caster footprint).
        h.adapter.update_sun((0.4, 0, 1), (SUN, SUN, SUN))
        h.step(2)

        view = dict(size=(240, 240), fov=50)
        # fov 50 at 30 u altitude: half-extent 14 u over 120 px ->
        # 8.57 px/u; x=4996 is -4 u -> px 120 - 34 = 86.
        sx, sy = 86, 120
        tex = pipeline.render_snapshot((5000, 0, 30), (0, -90, 0),
                                       **view)
        lum_far = common.avg_lum(tex_to_img(tex), sx, sy, half=3)
        tex = pipeline.render_snapshot((5000, 0, 30), (0, -90, 0),
                                       shadow_center=(5000, 0, 0),
                                       **view)
        snap_sh = tex_to_img(tex)
        h.save_capture(snap_sh, 'shadow_recentred')
        lum_re = common.avg_lum(snap_sh, sx, sy, half=3)
        h.report.check('shadow_contract_documented',
                       lum_far > 0.3,
                       f'cluster at x=5000, extent centered at origin: '
                       f'ground under the caster reads LIT '
                       f'({lum_far:.3f}) — outside the frustum samples '
                       f'lit, the documented coupling')
        h.report.check('shadow_center_recentres',
                       lum_far - lum_re > 0.05,
                       f'shadow_center=(5000,0,0): ground under the '
                       f'caster {lum_far:.3f} -> {lum_re:.3f} (the '
                       f'one-frame recentre renders the shadow)')
        c = pipeline._shadow_center
        h.report.check('shadow_center_restored',
                       c.x == 0 and c.y == 0 and c.z == 0
                       and pipeline._shadow_extent == 50.0,
                       f'after the shot: center=({c.x}, {c.y}, {c.z}), '
                       f'extent={pipeline._shadow_extent} (restored '
                       f'exactly)')

    # --- 8. Repeat-shot latency (informational) -------------------------
    t0 = time.perf_counter()
    pipeline.render_snapshot((0, -90, 0), (0, 0, 0), size=(160, 120))
    dt = time.perf_counter() - t0
    h.report.info('repeat_shot_ms',
                  f'{dt * 1000:.1f} ms for a repeat shot on the '
                  f'persistent chain (one extra rendered frame — the '
                  f'AI-loop latency, vs ~30 s for a subprocess boot)')

    # --- 9. Follow cameras (Session AK, the far-field lane) -------------
    # A far scene in its OWN graph with its OWN trivial shader — the
    # horizon-ring recipe: never lit, never shadowed, never traversed by
    # the main camera; composited behind the world by a background
    # region on the pipeline's scene buffer.
    bg_root = p3d.NodePath('bg_far_scene')
    bright = scenes.make_emissive_quad(bg_root, h.use_330, 2.5, 80.0)
    bright.set_pos(0, 200, 0)                    # due north, faces -Y
    dim = scenes.make_emissive_quad(bg_root, h.use_330, 0.3, 80.0)
    dim.set_pos(200, 0, 0)
    dim.set_h(-90)                               # faces -X (the viewer)
    bg_lens = p3d.PerspectiveLens()
    bg_lens.set_near_far(0.5, 6000.0)            # the far-field frustum
    bg_cam = p3d.Camera('bg_cam')
    bg_cam.set_lens(bg_lens)
    bg_cam_np = bg_root.attach_new_node(bg_cam)
    reg = pipeline.register_scene_camera(bg_cam_np, sort=-50,
                                         clear_color=(0, 0, 0, 1),
                                         follow='pose')
    h.step(2)
    p_main = base.camera.get_pos(base.render)
    p_bg = bg_cam_np.get_pos()
    h.report.check('follow_live_sync',
                   (p_bg - p_main).length() < 1e-4,
                   f'aux cam {tuple(round(v, 3) for v in p_bg)} vs main '
                   f'{tuple(round(v, 3) for v in p_main)} — pipeline '
                   f'mirrors the main camera each frame')

    base.camera.set_pos(0, 40, 0)                # empty foreground
    base.camera.set_hpr(0, 0, 0)                 # looking north
    h.step(2)
    north_lum = common.avg_lum(h.capture(), h.win_w // 2, h.win_h // 2,
                               half=3)
    base.camera.set_hpr(-90, 0, 0)               # looking east
    h.step(2)
    east_lum = common.avg_lum(h.capture(), h.win_w // 2, h.win_h // 2,
                              half=3)
    h.report.check('background_composites',
                   north_lum > 0.6 and 0.02 < east_lum < north_lum - 0.2,
                   f'window centre north={north_lum:.3f} (bright far '
                   f'quad), east={east_lum:.3f} (dim far quad) — '
                   f'background pixels survive the main region and the '
                   f'follow camera tracks the view')

    base.camera.set_hpr(0, 0, 0)                 # player looks north...
    h.step(2)
    tex = pipeline.render_snapshot((0, 40, 0), (-90, 0, 0),
                                   size=(240, 180))
    snap_lum = common.avg_lum(tex_to_img(tex), 120, 90, half=3)
    h.report.check('snapshot_reaims_follow',
                   0.02 < snap_lum < north_lum - 0.2,
                   f'snapshot aimed east centre={snap_lum:.3f} (the DIM '
                   f'east quad) while the player looks north at the '
                   f'bright one — the shot re-aims follow cameras')
    p_bg = bg_cam_np.get_pos()
    hpr_bg = bg_cam_np.get_hpr()
    h.report.check('follow_restored_after_shot',
                   (p_bg - p3d.Vec3(0, 40, 0)).length() < 1e-4
                   and abs(hpr_bg[0]) < 1e-4,
                   f'aux cam after the shot: pos='
                   f'{tuple(round(v, 3) for v in p_bg)}, '
                   f'h={hpr_bg[0]:.4f} (pre-shot pose restored)')

    pipeline.unregister_scene_camera(reg)
    sky_cam_np = bg_root.attach_new_node(p3d.Camera('sky_cam'))
    reg2 = pipeline.register_scene_camera(sky_cam_np, sort=-40,
                                          follow='hpr')
    base.camera.set_pos(77, 33, 11)
    base.camera.set_hpr(123, 5, 0)
    h.step(1)
    h.report.check('follow_hpr_rotation_only',
                   sky_cam_np.get_pos().length() < 1e-6
                   and abs(sky_cam_np.get_hpr()[0] - 123.0) < 1e-3
                   and abs(sky_cam_np.get_hpr()[1] - 5.0) < 1e-3,
                   f'follow="hpr": pos stays '
                   f'{tuple(round(v, 3) for v in sky_cam_np.get_pos())} '
                   f'(origin-pinned dome), hpr tracks '
                   f'{tuple(round(v, 2) for v in sky_cam_np.get_hpr())}')

    pipeline.unregister_scene_camera(reg2)
    base.camera.set_pos(0, -30, 0)
    base.camera.set_hpr(0, 0, 0)
    h.step(2)
    subj_lum = common.avg_lum(h.capture(), h.win_w // 2, h.win_h // 2,
                              half=3)
    h.report.check('background_unregister_restores',
                   subj_lum > 0.4,
                   f'after the last background camera unregisters the '
                   f'main region clears are restored — subject centre '
                   f'reads {subj_lum:.3f} (lit white card, no stale '
                   f'background state)')

    h.report.finish()


if __name__ == '__main__':
    main()
