"""paxtest: sun shadow mapping via the real DirectionalLight (R2.4).

Occluder sphere directly on the sun ray above a larger sphere: the occluded
pole region must darken to ambient when shadows are on, restore when toggled
off, and darken again when re-enabled (exercises the runtime recompile path,
which once wiped all shader inputs — a bug this test now guards).

Only meaningful for pipelines with sun_light_mode='directional'
(pax3d_render); others skip.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--soft-skin', action='store_true',
                        help='run with enable_hardware_skinning=False '
                             '(CPU skinning path)')
    args = parser.parse_args()

    h = common.Harness(args, 'shadows')
    if not getattr(h.adapter, 'supports_sun_modes', False):
        h.report.skip('pipeline has no directional sun mode')
    extra = {'shadow_map_size': 1024}  # fast depth-map readback
    if args.soft_skin:
        extra['enable_hardware_skinning'] = False
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode='directional', shadows=True,
                    extra_pipeline_kwargs=extra)
    pipeline = h.adapter.pipeline
    pipeline.set_shadow_extent(12, 60)

    h.set_ortho(film_h=6.0)  # 1 world unit = win_h/6 px
    base = h.base

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(0.02, 0.02, 0.02, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    ground = scenes.make_uv_sphere(48, 'game')
    scenes.apply_flat_pbr_surface(ground)
    ground.set_scale(2)
    ground.reparent_to(base.render)

    occluder = scenes.make_uv_sphere(24, 'game')
    scenes.apply_flat_pbr_surface(occluder)
    occluder.set_scale(1.0)
    occluder.set_pos(0, 0, 4)   # directly on the sun ray
    occluder.reparent_to(base.render)

    h.adapter.update_sun((0, 0, 1), (3, 3, 3))  # sun overhead

    # Sample point: z ~ 1.85 on the r=2 sphere — inside the shadow column
    px = h.win_w // 2
    py = int(h.win_h * (0.5 - 1.85 / 6.0))

    def pole_lum(tag):
        h.step(4)
        img = h.capture()
        h.save_capture(img, tag)
        return common.avg_lum(img, px, py, half=4)

    shadowed = pole_lum('on')
    pipeline.set_enable_shadows(False)
    unshadowed = pole_lum('off')
    pipeline.set_enable_shadows(True)
    reshadowed = pole_lum('on_again')

    h.report.check('unshadowed_bright', unshadowed > 0.4,
                   f'lum={unshadowed:.3f} with shadows off')
    ratio = unshadowed / max(shadowed, 1e-4)
    h.report.check('shadow_darkens', shadowed < 0.5 * unshadowed,
                   f'shadowed={shadowed:.3f} unshadowed={unshadowed:.3f} '
                   f'ratio={ratio:.1f}')
    h.report.check('shadow_toggle_returns', reshadowed < 0.5 * unshadowed,
                   f'reshadowed={reshadowed:.3f} (runtime recompile path)')

    # --- Off-origin cluster (R2.4 dynamic extent) ----------------------
    # An extent frustum centered on the world origin misses a cluster at
    # (40,0,0): outside-extent geometry must sample LIT (not artifacts).
    # Recentring via set_shadow_extent(center=...) restores the shadow,
    # and positioning the light node must NOT change the lighting itself
    # (a DirectionalLight lights by orientation only).
    cluster = p3d.Vec3(40, 0, 0)
    ground.set_pos(cluster)
    occluder.set_pos(cluster + p3d.Vec3(0, 0, 4))
    base.camera.set_pos(cluster)  # keep the same relative view

    scale = h.win_h / 6.0  # world units -> pixels (film_h=6)
    lit_px = h.win_w // 2 - int(round(1.2 * scale))   # outside the shadow
    lit_py = int(h.win_h * (0.5 - 1.6 / 6.0))         # column, sunlit slope

    def snap(tag):
        h.step(4)
        img = h.capture()
        h.save_capture(img, tag)
        return img

    img = snap('off_origin_missed')
    miss_pole = common.avg_lum(img, px, py, half=4)
    lit_before = common.avg_lum(img, lit_px, lit_py, half=3)
    h.report.check('extent_miss_is_lit', miss_pole > 0.4,
                   f'pole lum={miss_pole:.3f} outside origin-centered '
                   f'extent (outside frustum must be lit, not artifacts)')

    pipeline.set_shadow_extent(12, 60, center=cluster)
    img = snap('off_origin_centered')
    centered_pole = common.avg_lum(img, px, py, half=4)
    lit_after = common.avg_lum(img, lit_px, lit_py, half=3)
    h.report.check('extent_recenter_shadows',
                   centered_pole < 0.5 * max(miss_pole, 1e-4),
                   f'pole lum={centered_pole:.3f} after centering the '
                   f'extent on the cluster')
    h.report.check('recenter_keeps_lighting',
                   abs(lit_after - lit_before) < 0.02,
                   f'lit-point lum {lit_before:.3f} -> {lit_after:.3f} '
                   f'(light-node set_pos must not change lighting)')

    # --- Skinned caster (openworld P0) ---------------------------------
    # A soft-skinned Character sheet (two joints, blended weights) hangs
    # over the ground sphere where the occluder was. It must (a) write
    # texels into the sun's depth map — the exact instrument the openworld
    # dev used (glTF Actor: 0 texels; plain card: 32+) — and (b) darken
    # the ground, and (c) the shadow must follow a POSED joint, not the
    # bind pose. Scene stays at the off-origin cluster: skinning must
    # survive the recentered extent too.
    sheet = scenes.make_skinned_sheet(half=1.0, height=4.0, segments=8)
    has_char, has_blend = scenes.character_blend_info(sheet)
    h.report.check('skinned_rig_soft', has_char and has_blend,
                   f'Character={has_char} TransformBlendTable={has_blend} '
                   f'(guards against rigidified test geometry)')
    scenes.apply_flat_pbr_surface(sheet)
    sheet.set_pos(cluster)  # sheet plane sits at cluster + (0,0,4)

    depth_tex = common.find_light_depth_texture(pipeline.sun_light_np)

    def depth_map():
        return common.read_depth_image(base, depth_tex)

    occluder.detach_node()
    h.step(4)
    map_empty = depth_map()
    img = snap('skinned_none')
    lit_pole = common.avg_lum(img, px, py, half=4)   # nothing overhead

    occluder.reparent_to(base.render)                # static control
    h.step(4)
    map_static = depth_map()
    occluder.detach_node()

    sheet.reparent_to(base.render)
    h.step(4)
    map_skinned = depth_map()

    static_texels = common.count_gray_diff(map_empty, map_static)
    skinned_texels = common.count_gray_diff(map_empty, map_skinned)
    if static_texels >= 0 and skinned_texels >= 0:
        h.report.check('depth_instrument_sees_static', static_texels > 200,
                       f'{static_texels} texels from the static occluder '
                       f'(instrument sanity)')
        h.report.check('skinned_writes_depth', skinned_texels > 200,
                       f'{skinned_texels} texels from the skinned sheet '
                       f'(static control: {static_texels})')
    else:
        h.report.info('depth_readback',
                      'depth-map readback unavailable — luminance only')

    img = snap('skinned_on')
    pole_skinned = common.avg_lum(img, px, py, half=4)
    pose_pt = (h.win_w // 2 + int(round(1.4 * scale)),
               int(h.win_h * (0.5 - 1.43 / 6.0)))   # x=+1.4 on the sphere
    pose_before = common.avg_lum(img, pose_pt[0], pose_pt[1], half=3)
    h.report.check('skinned_casts_shadow',
                   pole_skinned < 0.5 * max(lit_pole, 1e-4),
                   f'pole lum {lit_pole:.3f} (no caster) -> '
                   f'{pole_skinned:.3f} (skinned sheet overhead)')

    # Pose: drag joint_tip +2x. The sheet's +x half stretches sideways
    # (bind footprint x in [-1,1] -> posed [-1,3]) so the point at x=+1.4
    # goes lit -> shadowed only if the depth pass renders the POSED skin.
    char_np = sheet.find('**/+Character')
    posed_ok = False
    if not char_np.is_empty():
        bundle = char_np.node().get_bundle(0)
        ctrl = char_np.attach_new_node('tip_ctrl')
        posed_ok = bool(bundle.control_joint('joint_tip', ctrl.node()))
        ctrl.set_pos(2, 0, 0)
    img = snap('skinned_posed')
    pose_after = common.avg_lum(img, pose_pt[0], pose_pt[1], half=3)
    pole_posed = common.avg_lum(img, px, py, half=4)
    h.report.check('skinned_shadow_follows_pose',
                   posed_ok and pose_after < 0.5 * max(pose_before, 1e-4),
                   f'x=+1.4 lum {pose_before:.3f} -> {pose_after:.3f} '
                   f'(joint_tip dragged +2x; control_joint={posed_ok})')
    h.report.info('skinned_pole_posed',
                  f'pole lum {pole_posed:.3f} (stretched sheet still '
                  f'covers x=0)')

    # --- glTF character caster (openworld P0, exact reported path) -----
    # The egg-synthesized Character above proves the engine machinery; this
    # loads a real panda3d-gltf character through direct.actor.Actor —
    # the precise combination openworld reported as casting zero texels.
    # Auto-skips (INFO) when panda3d-gltf or the asset pack is absent.
    sheet.detach_node()
    glb = r'C:\python\openworld\3D assets\Casual Characters\f_1.glb'
    actor = None
    try:
        import gltf as gltf_mod
        if hasattr(gltf_mod, 'patch_loader'):
            gltf_mod.patch_loader(base.loader)
        if os.path.exists(glb):
            from direct.actor.Actor import Actor
            actor = Actor(p3d.Filename.from_os_specific(glb).get_fullpath())
    except Exception as exc:
        h.report.info('gltf_caster', f'unavailable: {exc}')
        actor = None

    if actor is not None:
        anims = actor.get_anim_names()
        if anims:
            actor.loop(anims[0])
        actor.set_scale(3)                       # ~5m tall: a fat blob
        actor.set_pos(cluster + p3d.Vec3(0, 0, 2))   # feet on the pole
        actor.reparent_to(base.render)
        h.step(6)
        map_gltf = depth_map()
        gltf_texels = common.count_gray_diff(map_empty, map_gltf)
        img = snap('gltf_caster')
        gltf_pole = common.avg_lum(img, px, py, half=4)
        if gltf_texels >= 0:
            h.report.check('gltf_caster_writes_depth', gltf_texels > 200,
                           f'{gltf_texels} depth texels from a panda3d-gltf '
                           f'Actor ({os.path.basename(glb)}, '
                           f'anims={anims[:1]})')
        h.report.info('gltf_caster_ground_lum',
                      f'pole lum {gltf_pole:.3f} under the actor '
                      f'(no-caster baseline {lit_pole:.3f})')
        actor.detach_node()

    h.report.finish()


if __name__ == '__main__':
    main()
