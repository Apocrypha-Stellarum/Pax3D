"""paxtest: hardware vs CPU skinning correctness + the per-node opt-out
API (openworld P1, 2026-07-17).

Openworld's second character pack exports full Blender Rigify control
rigs (94 joints incl. MCH-*/ORG-*/tweak_* bones, animated non-uniform
scale on DEF-spine bones). On the GPU skinning path these characters walk
with pogo-ing heads and accordion necks; the CPU path is correct. Pack 1
(64 joints, DEF-only, constant scale) is correct on both paths.

Three layers, each mechanical:

1. Machinery (no external assets): the egg-synthesized two-joint sheet,
   posed, rendered on the GPU path and again with the new per-node
   pipeline.set_hardware_skinning(np, False) opt-out. Images must match
   (the opted-out node CPU-skins the same pose, main AND shadow pass),
   and clear_hardware_skinning() must restore the GPU path.

2. Palette math (per character pack): simulate exactly what the GPU
   palette shader computes — per-vertex top-4 weighted sum of
   TransformBlend matrices applied to bind-pose vertices — in Python,
   and compare against GeomVertexData.animate_vertices() (the CPU truth).
   A mismatch here means the munge/blend data is lossy for this rig; a
   match pushes the defect into the GL binding/shader layer.

3. Rendered A/B (per pack): the actor rendered on the GPU path vs the
   same frame with the per-node opt-out — an in-process end-to-end
   comparison that catches whatever layer the math probe can't see.

Pack sections auto-skip (INFO) when panda3d-gltf or the asset packs are
absent. Only meaningful for pax3d_render (needs the per-node API).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes

PACKS = [
    ('pack1', r'C:\python\openworld\3D assets\Casual Characters\f_1.glb'),
    ('pack2', r'C:\python\openworld\3D assets\Casual Characters 2\f_1.glb'),
]


def pick_anim(actor):
    """Deterministic animation choice: 'Walk' (the openworld repro) if
    present, else first sorted name."""
    anims = sorted(actor.get_anim_names())
    if not anims:
        return None
    return 'Walk' if 'Walk' in anims else anims[0]


def soft_geoms(np):
    """Yield (GeomNode, geom_index, vdata) for soft-skinned geoms."""
    for geom_np in np.find_all_matches('**/+GeomNode'):
        gnode = geom_np.node()
        for i in range(gnode.get_num_geoms()):
            vdata = gnode.get_geom(i).get_vertex_data()
            if vdata.get_transform_blend_table() is not None:
                yield gnode, i, vdata


def simulate_gpu_palette(vdata):
    """Positions the GPU palette path SHOULD produce: per vertex, the
    weighted sum of the (at most 4, top-weight, renormalized) blend
    matrices applied to the bind-pose position — the exact math of
    geomVertexData.cxx's hardware conversion + pax_pbr.vert's skinning
    block. Returns (positions, max_simultaneous)."""
    table = vdata.get_transform_blend_table()
    reader_v = p3d.GeomVertexReader(vdata, 'vertex')
    reader_b = p3d.GeomVertexReader(vdata, 'transform_blend')
    out = []
    max_sim = 0
    while not reader_v.is_at_end():
        pos = p3d.LPoint3(reader_v.get_data3())
        bi = reader_b.get_data1i()
        blend = table.get_blend(bi)
        n = blend.get_num_transforms()
        max_sim = max(max_sim, n)
        entries = [(blend.get_weight(j), blend.get_transform(j))
                   for j in range(n)]
        if n > 4:
            entries.sort(key=lambda e: -e[0])
            entries = entries[:4]
            total = sum(w for w, _ in entries)
            if total > 0:
                entries = [(w / total, t) for w, t in entries]
        m = p3d.LMatrix4(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        for w, t in entries:
            tm = p3d.LMatrix4()
            t.get_matrix(tm)
            m += tm * w
        out.append(m.xform_point(pos))
    return out, max_sim


def cpu_truth(vdata):
    """Positions the CPU path produces (the openworld-verified-correct
    reference): animate_vertices()."""
    animated = vdata.animate_vertices(True, p3d.Thread.get_current_thread())
    reader_v = p3d.GeomVertexReader(animated, 'vertex')
    out = []
    while not reader_v.is_at_end():
        out.append(p3d.LPoint3(reader_v.get_data3()))
    return out


def image_changed_frac(a, b, thresh=0.05, step=1):
    """Fraction of pixels whose luminance moved more than thresh."""
    n = changed = 0
    for y in range(0, a.get_y_size(), step):
        for x in range(0, a.get_x_size(), step):
            n += 1
            if abs(common.lum_at(a, x, y) - common.lum_at(b, x, y)) > thresh:
                changed += 1
    return changed / max(n, 1)


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'skinning')
    if h.adapter.name != 'pax3d_render':
        h.report.skip('per-node skinning API is pax3d_render-only')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode='directional', shadows=True,
                    extra_pipeline_kwargs={'shadow_map_size': 1024})
    pipeline = h.adapter.pipeline
    pipeline.set_shadow_extent(12, 60)
    base = h.base

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(0.02, 0.02, 0.02, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    # ------------------------------------------------------------------
    # 1. Machinery + opt-out API on the synthetic sheet
    # ------------------------------------------------------------------
    h.set_ortho(film_h=6.0)
    h.adapter.update_sun((0, 0, 1), (3, 3, 3))

    ground = scenes.make_uv_sphere(48, 'game')
    scenes.apply_flat_pbr_surface(ground)
    ground.set_scale(2)
    ground.reparent_to(base.render)

    sheet = scenes.make_skinned_sheet(half=1.0, height=4.0, segments=8)
    scenes.apply_flat_pbr_surface(sheet)
    sheet.reparent_to(base.render)

    # Drag joint_tip +2x: the sheet's +x half stretches sideways, so the
    # sphere point at x=+1.4 is shadowed ONLY if the active skinning path
    # (whichever it is) renders the posed skin.
    char_np = sheet.find('**/+Character')
    bundle = char_np.node().get_bundle(0)
    ctrl = char_np.attach_new_node('tip_ctrl')
    posed_ok = bool(bundle.control_joint('joint_tip', ctrl.node()))
    ctrl.set_pos(2, 0, 0)

    scale = h.win_h / 6.0
    pose_pt = (h.win_w // 2 + int(round(1.4 * scale)),
               int(h.win_h * (0.5 - 1.43 / 6.0)))

    def snap(tag):
        h.step(4)
        img = h.capture()
        h.save_capture(img, tag)
        return img

    img_hw = snap('sheet_hw')
    hw_pose_lum = common.avg_lum(img_hw, pose_pt[0], pose_pt[1], half=3)

    pipeline.set_hardware_skinning(sheet, False)
    img_cpu = snap('sheet_optout')
    cpu_pose_lum = common.avg_lum(img_cpu, pose_pt[0], pose_pt[1], half=3)
    rms_cpu = common.image_rms_diff(img_hw, img_cpu)

    pipeline.clear_hardware_skinning(sheet)
    img_back = snap('sheet_cleared')
    rms_back = common.image_rms_diff(img_hw, img_back)

    h.report.check('sheet_rig_posed', posed_ok,
                   f'control_joint acquired={posed_ok}')
    h.report.check('optout_image_matches_hw', rms_cpu < 0.02,
                   f'image rms HW vs per-node-CPU = {rms_cpu:.4f} '
                   f'(same pose, both passes)')
    h.report.check('optout_shadow_follows_pose',
                   cpu_pose_lum < 0.5 * max(hw_pose_lum, 0.03) + 0.03
                   and cpu_pose_lum < 0.15,
                   f'x=+1.4 shadow lum: hw={hw_pose_lum:.3f} '
                   f'optout={cpu_pose_lum:.3f} (depth pass must follow the '
                   f'per-node CPU path — override 2 beats initial state)')
    h.report.check('optout_clear_restores', rms_back < 0.02,
                   f'image rms HW vs cleared = {rms_back:.4f}')

    # ------------------------------------------------------------------
    # 1b. Bone-palette ceiling (Session S): the declared table size is a
    # knob (max_skinning_bones) and must be INERT for small rigs — the
    # GL layer identity-pads short tables (engine fact #10). 200 bones
    # = 3200 of the typical 4096 vertex-uniform components, the spike
    # target for un-cut UE5-class rigs (the character pipeline's 352->81
    # cut exists because of the old hard [100]).
    # ------------------------------------------------------------------
    if hasattr(pipeline, 'set_max_skinning_bones'):
        pipeline.set_max_skinning_bones(200)
        img_200 = snap('sheet_bones200')
        rms_200 = common.image_rms_diff(img_back, img_200)
        pipeline.set_max_skinning_bones(100)
        img_100 = snap('sheet_bones100')
        rms_100 = common.image_rms_diff(img_back, img_100)
        h.report.check('bone_palette_200_inert', rms_200 == 0.0,
                       f'p3d_TransformTable[200] on the 2-joint rig: rms '
                       f'vs [100] = {rms_200:.2e} (identity padding — the '
                       f'ceiling is a knob, shadow pass included)')
        h.report.check('bone_palette_restore', rms_100 == 0.0,
                       f'back to 100: rms = {rms_100:.2e} (exact restore)')

    sheet.detach_node()
    ground.detach_node()

    # ------------------------------------------------------------------
    # 1c. A REAL >100-joint rig (Session S user directive: UE5/Unity
    # compatibility — no artificial cap). A 120-joint chain: under the
    # default [100] table the GPU CANNOT render its pose (the field
    # dev's "plausibly-exploded garbage" class, now measured), the
    # audit names the rig, and 'auto' resolves a covering palette that
    # matches the CPU truth pixel-for-pixel.
    # ------------------------------------------------------------------
    if hasattr(pipeline, 'refresh_skinning_budget'):
        chain = scenes.make_skinned_chain(joints=120)
        scenes.apply_flat_pbr_surface(chain)
        chain.reparent_to(base.render)
        chain_char = chain.find('**/+Character')
        cbundle = chain_char.node().get_bundle(0)
        cctrl = chain_char.attach_new_node('chain_tip_ctrl')
        cposed = bool(cbundle.control_joint('chain_119', cctrl.node()))
        cctrl.set_pos(0, 1.5, 0)          # swing the +x end sideways

        audit = pipeline.audit_skinning_budget(warn=True)
        flagged = [(n, j) for n, j, fits in audit if not fits]
        h.report.check(
            'audit_names_oversized_rig',
            cposed and any(j >= 120 for _, j in flagged),
            f'audit at table 100: flagged={flagged} (the missing '
            f'warning — a too-big rig now names itself)')

        # CPU truth for the pose (per-node opt-out renders it correctly)
        pipeline.set_hardware_skinning(chain, False)
        img_cpu_truth = snap('chain_cpu_truth')
        pipeline.clear_hardware_skinning(chain)

        img_gpu_100 = snap('chain_gpu_table100')
        rms_bad = common.image_rms_diff(img_cpu_truth, img_gpu_100)
        h.report.check(
            'oversized_rig_corrupts_at_100', rms_bad > 0.003,
            f'GPU@[100] vs CPU truth on the posed 120-joint chain: rms '
            f'{rms_bad:.4f} — the palette cannot hold the posed joint '
            f'(the measured justification for the audit warning)')

        pipeline.set_max_skinning_bones('auto')
        resolved = pipeline.max_skinning_bones
        img_gpu_auto = snap('chain_gpu_auto')
        rms_auto = common.image_rms_diff(img_cpu_truth, img_gpu_auto)
        h.report.check(
            'auto_palette_covers_rig',
            resolved >= 120 and rms_auto < 0.02,
            f"'auto' resolved the palette to {resolved} (>=120): GPU vs "
            f'CPU truth rms {rms_auto:.4f} — the cap follows the '
            f'content, not the other way around')

        chain.detach_node()
        pipeline.set_max_skinning_bones(100)
        h.step(2)

    # ------------------------------------------------------------------
    # 2 + 3. Character packs: palette math + rendered A/B
    # ------------------------------------------------------------------
    try:
        import gltf as gltf_mod
        if hasattr(gltf_mod, 'patch_loader'):
            gltf_mod.patch_loader(base.loader)
        from direct.actor.Actor import Actor
    except Exception as exc:
        h.report.info('gltf', f'panda3d-gltf unavailable: {exc}')
        h.report.finish()
        return

    # Neutral, front-lit look for the A/B renders
    h.adapter.update_sun((0.3, -0.7, 0.65), (2.5, 2.5, 2.5))
    alight.set_color(p3d.LColor(0.25, 0.25, 0.25, 1))

    for tag, glb in PACKS:
        if not os.path.exists(glb):
            h.report.info(f'{tag}', f'asset not present: {glb}')
            continue
        actor = Actor(p3d.Filename.from_os_specific(glb).get_fullpath())
        anim = pick_anim(actor)
        if anim:
            actor.pose(anim, 12)
        actor.reparent_to(base.render)
        h.step(2)   # let the character update to the posed frame

        # Frame the actor
        lo, hi = p3d.Point3(), p3d.Point3()
        actor.calc_tight_bounds(lo, hi, base.render)
        center = (lo + hi) * 0.5
        span = max(hi.x - lo.x, hi.z - lo.z) * 1.2
        base.camera.set_pos(center.x, center.y - 10, center.z)
        h.set_ortho(film_h=span)

        # --- Layer 2: palette math vs CPU truth ------------------------
        max_dev = 0.0
        max_sim_all = 0
        n_soft = 0
        has_sliders = False
        for gnode, i, vdata in soft_geoms(actor):
            n_soft += 1
            if vdata.get_slider_table() is not None:
                has_sliders = True
            gpu, max_sim = simulate_gpu_palette(vdata)
            cpu = cpu_truth(vdata)
            max_sim_all = max(max_sim_all, max_sim)
            for a, b in zip(gpu, cpu):
                d = (a - b).length()
                if d > max_dev:
                    max_dev = d
        table_info = []
        for _, _, vdata in soft_geoms(actor):
            t = vdata.get_transform_blend_table()
            table_info.append(f'{t.get_num_transforms()}tr')
            break
        h.report.check(f'{tag}_soft_rig', n_soft > 0,
                       f'{n_soft} soft geoms, anim={anim}, '
                       f'blends={",".join(table_info)}, '
                       f'max_simultaneous={max_sim_all}, '
                       f'sliders={has_sliders}')
        h.report.check(f'{tag}_palette_math_matches_cpu', max_dev < 0.005,
                       f'max |gpu_sim - cpu| = {max_dev:.4f} model units '
                       f'(>4-influence loss / stale palette would show '
                       f'here)')

        # --- Layer 3: rendered A/B via the per-node opt-out -------------
        img_hw = snap(f'{tag}_hw')
        pipeline.set_hardware_skinning(actor, False)
        img_cpu = snap(f'{tag}_cpu')
        pipeline.clear_hardware_skinning(actor)
        img_back = snap(f'{tag}_back')

        frac = image_changed_frac(img_hw, img_cpu, step=2)
        frac_back = image_changed_frac(img_hw, img_back, step=2)
        h.report.check(f'{tag}_hw_matches_cpu_render', frac < 0.01,
                       f'{frac * 100:.2f}% of pixels differ between GPU '
                       f'and CPU skinning (concertina shows as several %)')
        h.report.check(f'{tag}_optout_roundtrip', frac_back < 0.01,
                       f'{frac_back * 100:.2f}% differ after '
                       f'clear_hardware_skinning')

        actor.cleanup()
        actor.remove_node()

    h.report.finish()


if __name__ == '__main__':
    main()
