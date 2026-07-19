"""paxtest: hardware instancing under the pipeline (ER-002,
pipeline.set_instanced).

The scatter render path: an InstancedNode's InstanceList drawn in ONE
draw per Geom, each instance transformed in-vertex-shader by
p3d_InstanceMatrix (divisor-1 attrib munged from the list by
CullableObject when F_hardware_instancing is set). This gate measures
the whole contract on the REAL pipeline shader:

  1. THE FALLBACK: an InstancedNode WITHOUT set_instanced still renders
     every instance CORRECTLY — the cull traverser draws one object per
     instance (correct output, no perf win). set_instanced is a
     performance switch, not a correctness switch (measured; better
     than the ER-002 prediction).
  1b. THE FLAG/SHADER PAIRING TRAP: F_hardware_instancing hand-set on a
     node whose shader lacks p3d_InstanceMatrix collapses every
     instance onto the node origin (the flag engages the munge path;
     the shader gets identity). This doubles as PROOF the flagged path
     really is hardware instancing — the fallback disappears.
  2. set_instanced(): every instance renders at its list transform
     (positions + rotation + scale), nothing at the origin.
  3. Equivalence: the instanced render matches a reference scene of N
     plain copies at the same transforms (small rms tolerance — the
     instance transform is applied in-shader, the reference's on the
     CPU; same math, different rounding).
  4. Shadows (directional variant): instanced casters darken a ground
     card under EACH instance — the depth pass carries the same
     instancing path (identity-fallback safe for other casters).
  5. Opt-out: set_instanced(np, False) restores the single-at-origin
     render byte-identically.

Ambient-only analytics (test_srgb pattern): metallic-1/roughness-1
white cards under a flat AmbientLight render curve(A) exactly, so
presence/absence probes are deterministic.

Only meaningful for pax3d_render on a Pax3D 1.11 engine — stock 1.10
has no InstancedNode (the SKIP itself documents the version gap).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

AMBIENT = 0.6
# Instance placements: (film_x, film_z, roll_deg, scale)
INSTANCES = [
    (-0.6, 0.5, 0.0, 1.0),
    (0.6, 0.5, 45.0, 1.0),
    (-0.6, -0.3, 0.0, 1.5),
    (0.6, -0.3, 0.0, 1.0),
]
SUN_DIR = (0, -0.7071, 0.7071)   # toward-sun; light falls +y and -z


def make_patch_mesh(name):
    cm = p3d.CardMaker(name)
    cm.set_frame(-0.15, 0.15, -0.15, 0.15)
    node = cm.generate()
    return node


def metal_material(name):
    mat = p3d.Material(name)
    mat.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat.set_metallic(1.0)
    mat.set_roughness(1.0)
    return mat


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default='uniforms')
    args = parser.parse_args()

    h = common.Harness(args, 'instancing')
    if args.pipeline != 'pax3d_render':
        h.report.skip('set_instanced lives in pax3d_render (ER-002)')
    if not hasattr(p3d, 'InstancedNode'):
        h.report.skip('engine has no InstancedNode (needs Pax3D 1.11; '
                      'stock 1.10 predates it)')
    directional = args.sun_mode == 'directional'
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode, shadows=directional)
    pipeline = h.adapter.pipeline

    base = h.base
    h.set_ortho(film_h=2.0)

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMBIENT, AMBIENT, AMBIENT, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun(SUN_DIR, (0, 0, 0))

    def px(fx, fz):
        return (int((fx / 2.0 + 0.5) * h.win_w),
                int((0.5 - fz / 2.0) * h.win_h))

    # --- Scene: an InstancedNode holding one small card ------------------
    inode = p3d.InstancedNode('paxtest_instances')
    inp = base.render.attach_new_node(inode)
    inp.attach_new_node(make_patch_mesh('patch'))
    inp.set_two_sided(True)
    inp.set_material(metal_material('m1'), 1)

    # Python surface: InstancedNode.instances (the modify_instances
    # property — mutations write back), append(pos, hpr, scale) /
    # append(TransformState), reserve. get_num_instances is not
    # published; use len(node.instances).
    ilist = inode.instances
    ilist.reserve(len(INSTANCES))
    for fx, fz, roll, scale in INSTANCES:
        ilist.append(p3d.LPoint3(fx, 0, fz), p3d.LVecBase3(0, 0, roll),
                     p3d.LVecBase3(scale, scale, scale))
    h.report.info('instance_api',
                  f'InstanceList: reserve + append(pos,hpr,scale) x'
                  f'{len(ilist)} ok; node re-reads '
                  f'{len(inode.instances)} instances')

    lit = common.CURVES['hejl_dawson'](AMBIENT)

    def probe(img, fx, fz):
        x, y = px(fx, fz)
        return common.avg_lum(img, x, y)

    # --- 1. Without the flag: per-instance fallback, correct output ------
    h.step(5)
    img_unflagged = h.capture()
    got_origin = probe(img_unflagged, 0.0, 0.0)
    corners_lit = sum(1 for fx, fz, _r, _s in INSTANCES
                      if abs(probe(img_unflagged, fx, fz) - lit) < 0.02)
    h.report.check(
        'unflagged_fallback_correct',
        corners_lit == 4 and got_origin < 0.05,
        f'no set_instanced: {corners_lit}/4 instances render (origin '
        f'lum={got_origin:.3f}) — the traverser falls back to one draw '
        f'per instance; set_instanced is a PERF switch, not correctness')

    # --- 1b. Flag without the shader: the pairing trap (and the proof
    # the flag really flips the engine into hardware-instanced draws:
    # the per-instance fallback vanishes, identity matrices collapse
    # every instance onto the node transform) ----------------------------
    prev = inp.get_attrib(p3d.ShaderAttrib) or p3d.ShaderAttrib.make()
    inp.set_attrib(prev.set_flag(
        p3d.ShaderAttrib.F_hardware_instancing, True))
    h.step(5)
    img_trap = h.capture()
    got_origin = probe(img_trap, 0.0, 0.0)
    corners_lit = sum(1 for fx, fz, _r, _s in INSTANCES
                      if probe(img_trap, fx, fz) > 0.1)
    h.report.check(
        'flag_without_shader_collapses',
        abs(got_origin - lit) < 0.02 and corners_lit == 0,
        f'flag + non-INSTANCING shader: origin lum={got_origin:.3f} '
        f'(expected {lit:.3f}), {corners_lit}/4 positions lit — HW '
        f'path engaged, identity matrices collapse instances (keep '
        f'flag and shader paired via set_instanced)')
    inp.set_attrib(inp.get_attrib(p3d.ShaderAttrib).clear_flag(
        p3d.ShaderAttrib.F_hardware_instancing))

    # --- 2. set_instanced: every instance renders -------------------------
    pipeline.set_instanced(inp)
    h.step(5)
    img_inst = h.capture()
    h.save_capture(img_inst, 'instanced')
    corners_lit = sum(1 for fx, fz, _r, _s in INSTANCES
                      if abs(probe(img_inst, fx, fz) - lit) < 0.02)
    got_origin = probe(img_inst, 0.0, 0.0)
    h.report.check(
        'instanced_draws_all',
        corners_lit == 4 and got_origin < 0.05,
        f'{corners_lit}/4 instance positions at ambient-exact lum, '
        f'origin lum={got_origin:.3f} (no stray copy)')

    # --- 3. Matches N plain copies ----------------------------------------
    inp.stash()
    ref_root = base.render.attach_new_node('reference')
    ref_root.set_two_sided(True)
    ref_root.set_material(metal_material('m2'), 1)
    for fx, fz, roll, scale in INSTANCES:
        copy = ref_root.attach_new_node(make_patch_mesh('ref'))
        copy.set_pos(fx, 0, fz)
        copy.set_hpr(0, 0, roll)
        copy.set_scale(scale)
    h.step(5)
    img_ref = h.capture()
    h.save_capture(img_ref, 'reference')
    rms = common.image_rms_diff(img_inst, img_ref, step=1)
    h.report.check(
        'matches_plain_copies', rms < 0.005,
        f'instanced render vs {len(INSTANCES)} plain copies (pos + '
        f'45-deg roll + 1.5x scale): rms={rms:.5f}')
    ref_root.stash()
    inp.unstash()

    # --- 4. Shadows: each instance casts (directional variant only) ------
    if directional:
        pipeline.set_shadow_extent(3.0, 10.0)
        alight.set_color(p3d.LColor(0.15, 0.15, 0.15, 1))
        h.adapter.update_sun(SUN_DIR, (2.0, 2.0, 2.0))
        cm = p3d.CardMaker('ground')
        cm.set_frame(-1, 1, -1, 1)
        ground = base.render.attach_new_node(cm.generate())
        ground.set_y(0.5)
        ground.set_two_sided(True)
        gmat = p3d.Material('ground_mat')
        gmat.set_base_color(p3d.LColor(1, 1, 1, 1))
        gmat.set_metallic(0.0)
        gmat.set_roughness(1.0)
        ground.set_material(gmat, 1)
        h.step(5)
        img_sh = h.capture()
        h.save_capture(img_sh, 'shadows')
        clear_lum = probe(img_sh, 0.0, 0.9)
        # Light falls (0, +y, -z) at 45 deg: instance (x, 0, z) shadows
        # the ground plane (y=+0.5) at (x, z-0.5).
        n_shadowed = 0
        details = []
        for fx, fz, _r, _s in INSTANCES:
            slum = probe(img_sh, fx, fz - 0.5)
            details.append(f'({fx},{fz - 0.5:.1f})={slum:.2f}')
            if slum < clear_lum * 0.7:
                n_shadowed += 1
        h.report.check(
            'instanced_casters_shadow', n_shadowed == len(INSTANCES),
            f'{n_shadowed}/{len(INSTANCES)} shadow spots dark vs clear '
            f'ground {clear_lum:.2f} ({", ".join(details)}) — the depth '
            f'pass applies per-instance transforms')
        ground.remove_node()
        alight.set_color(p3d.LColor(AMBIENT, AMBIENT, AMBIENT, 1))
        h.adapter.update_sun(SUN_DIR, (0, 0, 0))

    # --- 5. Opt-out: back to the single-at-origin render ------------------
    pipeline.set_instanced(inp, False)
    h.step(5)
    img_off = h.capture()
    rms = common.image_rms_diff(img_unflagged, img_off, step=1)
    h.report.check(
        'opt_out_restores', rms == 0.0,
        f'set_instanced(np, False): rms vs the unflagged baseline = '
        f'{rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
