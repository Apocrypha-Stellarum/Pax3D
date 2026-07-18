"""probe_morph_gltf — measured facts: glTF morph targets end-to-end
(SK_SFM_Head1 asset, delivered per the PAX3D_FEEDBACK.md 2026-07-18
offer; ground truth in assets/morph_head_manifest.json).

NOT a gate test. probe_morph.py answered the egg <Dxyz> mechanics
(fact #15: hardware skinning silently drops sliders; the per-node CPU
opt-out renders them). This probe answers the OTHER half for the real
character pipeline:

  1. does panda3d-gltf DELIVER morph targets at all (Character +
     CharacterSlider + slider table on the vertex data), for both a
     skinned mesh and a static (joint-less) mesh?
  2. does the CPU path reproduce the Blender-authored ground truth
     (max-delta vertex positions / magnitudes from the manifest)?
  3. does the RENDER follow a slider under the pipeline default
     (F_hardware_skinning scene-wide) and under the per-node CPU
     opt-out — for each variant?
  4. does the FaceTest clip drive the sliders (glTF weights-channel
     animation -> Panda slider animation)?
  5. rough cost of the CPU fallback (ms/frame, HW vs opt-out, one head).

Assertions follow the manifest's own rule: compare NUMBERS (positions,
magnitudes), never vertex indices — GLB export reindexes and may split
vertices, so moved-vertex counts are reported as facts, not asserted.

Run:  <python> tools/paxtest/probe_morph_gltf.py --pipeline pax3d_render
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

ASSETS = os.path.join(common.HERE, 'assets')
MANIFEST = os.path.join(ASSETS, 'morph_head_manifest.json')

SLIDERS = ['blink', 'jaw_open', 'brow_raise']
POS_TOL = 1.5e-3    # manifest rounds to 4 decimals; loader is float32
MOVE_EPS = 1e-5     # a vertex "moved" if |delta| exceeds this (metres)

PASS_ = []


def fact(name, value, detail):
    PASS_.append(name)
    print(f'[fact] {name} = {value}   {detail}')


def load_glb(base, name):
    path = os.path.join(ASSETS, name)
    if not os.path.exists(path):
        return None
    return base.loader.load_model(
        p3d.Filename.from_os_specific(path).get_fullpath())


def find_sliders(char_np):
    """(bundle, {name: CharacterSlider-or-None}) for the manifest names."""
    bundle = char_np.node().get_bundle(0)
    return bundle, {n: bundle.find_child(n) for n in SLIDERS}


def set_slider(char_np, slider, v):
    slider.apply_freeze_scalar(v)
    char_np.node().force_update()


def read_positions(model_np):
    """CPU-truth vertex positions (animate_vertices) across every geom,
    in the model root's space (geom-local positions transformed by the
    geom node's mat relative to the model root — identity for this
    asset, but cheap insurance)."""
    out = []
    for geom_np in model_np.find_all_matches('**/+GeomNode'):
        mat = geom_np.get_mat(model_np)
        use_mat = not mat.is_identity()
        gnode = geom_np.node()
        for i in range(gnode.get_num_geoms()):
            vdata = gnode.get_geom(i).get_vertex_data().animate_vertices(
                True, p3d.Thread.get_current_thread())
            reader = p3d.GeomVertexReader(vdata, 'vertex')
            while not reader.is_at_end():
                pos = p3d.LPoint3(reader.get_data3())
                out.append(mat.xform_point(pos) if use_mat else pos)
    return out


def vec_close(a, b, tol=POS_TOL):
    return all(abs(a[i] - b[i]) <= tol for i in range(3))


def fmt(v):
    return f'({v[0]:.4f}, {v[1]:.4f}, {v[2]:.4f})'


def measure_slider_cpu(tag, model_np, char_np, slider_name, slider, truth):
    """CPU path vs manifest ground truth for one slider."""
    set_slider(char_np, slider, 0.0)
    p0 = read_positions(model_np)
    set_slider(char_np, slider, 1.0)
    p1 = read_positions(model_np)
    set_slider(char_np, slider, 0.0)

    moved = 0
    best_d = 0.0
    best_i = -1
    for i, (a, b) in enumerate(zip(p0, p1)):
        d = (b - a).length()
        if d > MOVE_EPS:
            moved += 1
        if d > best_d:
            best_d = d
            best_i = i

    ok_mag = abs(best_d - truth['max_delta_m']) <= POS_TOL
    ok_pos = (best_i >= 0
              and vec_close(p0[best_i], truth['max_delta_vertex_at_0'])
              and vec_close(p1[best_i], truth['max_delta_vertex_at_1']))
    at0 = fmt(p0[best_i]) if best_i >= 0 else 'n/a'
    at1 = fmt(p1[best_i]) if best_i >= 0 else 'n/a'
    fact(f'{tag}_cpu_{slider_name}_matches_manifest', ok_mag and ok_pos,
         f'max delta {best_d:.4f}m (truth {truth["max_delta_m"]:.4f}), '
         f'argmax {at0} -> {at1} (truth '
         f'{fmt(truth["max_delta_vertex_at_0"])} -> '
         f'{fmt(truth["max_delta_vertex_at_1"])}); moved {moved} verts '
         f'(blender counted {truth["moved_verts"]} of 2240 pre-split)')
    return ok_mag and ok_pos


def delivery_facts(tag, model_np):
    """Character/slider/slider-table delivery. Returns (char_np, sliders)
    with sliders=None when nothing usable arrived."""
    char_np = model_np.find('**/+Character')
    fact(f'{tag}_character_created', not char_np.is_empty(),
         'panda3d-gltf wrapped the mesh in a Character')
    if char_np.is_empty():
        return None, None
    bundle, sliders = find_sliders(char_np)
    got = sorted(n for n, s in sliders.items() if s is not None)
    fact(f'{tag}_sliders_delivered', got == sorted(SLIDERS),
         f'bundle.find_child: {got or "none"} of {SLIDERS}')

    has_table = False
    has_morph_cols = False
    anim_types = set()
    for geom_np in model_np.find_all_matches('**/+GeomNode'):
        gnode = geom_np.node()
        for i in range(gnode.get_num_geoms()):
            vdata = gnode.get_geom(i).get_vertex_data()
            if vdata.get_slider_table() is not None:
                has_table = True
            fmt_ = vdata.get_format()
            anim_types.add(fmt_.get_animation().get_animation_type())
            for c in range(fmt_.get_num_columns()):
                if 'morph' in str(fmt_.get_column(c).get_name()):
                    has_morph_cols = True
    fact(f'{tag}_vertex_morph_data', has_table and has_morph_cols,
         f'slider_table={has_table}, morph columns={has_morph_cols}, '
         f'animation spec={sorted(anim_types)}')
    if got != sorted(SLIDERS) or not has_table:
        return char_np, None
    return char_np, sliders


def frame_head(h, base):
    """Front ortho close-up: face points -y, head z 1.53..1.80."""
    base.camera.set_pos(0, -1.5, 1.663)
    base.camera.set_hpr(0, 0, 0)
    h.set_ortho(film_h=0.35)


def render_ab(h, tag, char_np, slider):
    """Image rms between slider 0 and slider 1 renders (jaw_open is the
    caller's pick: the largest authored delta, 2.28cm on a 27cm head)."""
    set_slider(char_np, slider, 0.0)
    h.step(4)
    img0 = h.capture()
    h.save_capture(img0, f'{tag}_s0')
    set_slider(char_np, slider, 1.0)
    h.step(4)
    img1 = h.capture()
    h.save_capture(img1, f'{tag}_s1')
    set_slider(char_np, slider, 0.0)
    return common.image_rms_diff(img0, img1, step=1)


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'probe_morph_gltf')
    # Measure the LOADER, not the model cache: a prior successful run
    # writes cached bams that would make the stock-crash check below
    # silently pass (and bypass the shim path entirely).
    p3d.BamCache.get_global_ptr().set_active(False)
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None:
        h.report.skip('probe needs a pax_pbr-family pipeline')
    base = h.base

    try:
        import gltf as gltf_mod
        if hasattr(gltf_mod, 'patch_loader'):
            gltf_mod.patch_loader(base.loader)
        from direct.actor.Actor import Actor
    except Exception as exc:
        print(f'[fact] gltf_available = False   ({exc})')
        sys.exit(1)
    fact('gltf_available', True,
         f'panda3d-gltf {getattr(gltf_mod, "__version__", "?")}')

    # Stock loader first: Blender exports shape keys as SPARSE accessors
    # (bufferView legally absent); panda3d-gltf <=1.3.0 crashes on them
    # (upstream Moguri/panda3d-gltf#103).
    stock_ok = True
    try:
        base.loader.load_model(p3d.Filename.from_os_specific(
            os.path.join(ASSETS, 'morph_head_static.glb')).get_fullpath())
    except Exception as exc:
        stock_ok = False
        stock_detail = str(exc).splitlines()[0]
    fact('stock_loader_loads_sparse_morph_glb', stock_ok,
         'stock panda3d-gltf on a Blender-default morph export'
         + ('' if stock_ok else
            f' — crashed (upstream #103): {stock_detail}'))

    from pax3d_render import gltf_compat
    fact('sparse_shim_installed', gltf_compat.install(),
         'pax3d_render.gltf_compat densifies sparse accessors before '
         'Converter.update; everything below measures loader+shim')

    if not os.path.exists(MANIFEST):
        print('[fact] manifest_present = False')
        sys.exit(1)
    with open(MANIFEST, encoding='utf-8') as f:
        manifest = json.load(f)
    truth = manifest['ground_truth']

    alight = p3d.AmbientLight('probe_ambient')
    alight.set_color(p3d.LColor(0.5, 0.5, 0.5, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -0.7, 0.7), (2.0, 2.0, 2.0))

    # ------------------------------------------------------------------
    # 1. static variant: morphs on a joint-less mesh
    # ------------------------------------------------------------------
    static = load_glb(base, 'morph_head_static.glb')
    fact('static_loads', static is not None, 'morph_head_static.glb')
    if static is not None:
        static.reparent_to(base.render)
        char_np, sliders = delivery_facts('static', static)
        if sliders:
            for name in SLIDERS:
                measure_slider_cpu('static', static, char_np, name,
                                   sliders[name], truth[name])
            frame_head(h, base)
            rms_hw = render_ab(h, 'static_hw', char_np,
                               sliders['jaw_open'])
            fact('static_render_hw_drops_morph', rms_hw < 1e-6,
                 f'jaw_open 0->1 image rms {rms_hw:.6f} under the '
                 f'pipeline default — the scene-wide F_hardware_skinning '
                 f'flag drops morphs even on this JOINT-LESS mesh')
            pipeline.set_hardware_skinning(static, False)
            rms_cpu = render_ab(h, 'static_cpu', char_np,
                                sliders['jaw_open'])
            fact('static_render_cpu_optout_applies_morph',
                 rms_cpu > 0.002,
                 f'same A/B on the per-node CPU opt-out: rms '
                 f'{rms_cpu:.5f}')
            pipeline.clear_hardware_skinning(static)
        static.detach_node()

    # ------------------------------------------------------------------
    # 2. skinned variant: morphs + 9-bone spine chain
    # ------------------------------------------------------------------
    skinned = load_glb(base, 'morph_head_skinned.glb')
    fact('skinned_loads', skinned is not None, 'morph_head_skinned.glb')
    if skinned is not None:
        skinned.reparent_to(base.render)
        char_np, sliders = delivery_facts('skinned', skinned)
        if sliders:
            for name in SLIDERS:
                measure_slider_cpu('skinned', skinned, char_np, name,
                                   sliders[name], truth[name])
            frame_head(h, base)
            rms_hw = render_ab(h, 'skinned_hw', char_np,
                               sliders['jaw_open'])
            fact('skinned_render_hw_drops_morph', rms_hw < 1e-6,
                 f'jaw_open 0->1 image rms {rms_hw:.6f} with hardware '
                 f'skinning ON (fact #15 predicted 0.0 — silently '
                 f'dropped)')
            pipeline.set_hardware_skinning(skinned, False)
            rms_cpu = render_ab(h, 'skinned_cpu', char_np,
                                sliders['jaw_open'])
            fact('skinned_render_cpu_optout_applies_morph',
                 rms_cpu > 0.002,
                 f'same A/B on the per-node CPU opt-out: rms '
                 f'{rms_cpu:.5f}')
            pipeline.clear_hardware_skinning(skinned)
        skinned.detach_node()

    # ------------------------------------------------------------------
    # 3. anim variant: does a glTF weights channel drive the sliders?
    #
    # Two layers, because the SHIPPED asset's weights channel is empty
    # (export defect, measured below) while the LOADER path is fine:
    #   a. file truth — decode the weights sampler straight from the
    #      GLB JSON/BIN and report what the exporter actually wrote;
    #   b. engine truth — byte-patch a temp copy with known nonzero
    #      weights (0,0,0 -> 1.0/0.5/0.25 LINEAR ramp) and assert the
    #      Actor's sliders follow them.
    # ------------------------------------------------------------------
    anim_path = os.path.join(ASSETS, 'morph_head_skinned_anim.glb')
    fact('anim_loads', os.path.exists(anim_path),
         'morph_head_skinned_anim.glb')
    actor = None
    if os.path.exists(anim_path):
        import shutil
        import struct
        import tempfile
        with open(anim_path, 'rb') as f:
            raw = f.read()
        jlen = struct.unpack('<I', raw[12:16])[0]
        gj = json.loads(raw[20:20 + jlen])
        anim0 = gj['animations'][0]
        wchan = [c for c in anim0['channels']
                 if c['target']['path'] == 'weights'][0]
        sampler = anim0['samplers'][wchan['sampler']]
        out_acc = gj['accessors'][sampler['output']]
        in_acc = gj['accessors'][sampler['input']]
        bv = gj['bufferViews'][out_acc['bufferView']]
        w_off = (20 + jlen + 8 + bv.get('byteOffset', 0)
                 + out_acc.get('byteOffset', 0))
        w_vals = struct.unpack(f'<{out_acc["count"]}f',
                               raw[w_off:w_off + 4 * out_acc['count']])
        fact('anim_file_weights_authored', max(w_vals) > 0.0,
             f'weights sampler in the FILE: {out_acc["count"]} values, '
             f'{in_acc["count"]} keys ending {in_acc["max"][0]:.3f}s, '
             f'min {min(w_vals):.2f} max {max(w_vals):.2f} (False = '
             f'the shape-key action did not reach the exporter — '
             f'asset-side export defect, not a loader gap; the '
             f'2026-07-19 first delivery failed exactly this way)')

        actor = Actor(p3d.Filename.from_os_specific(
            anim_path).get_fullpath())
        actor.reparent_to(base.render)
        names = sorted(actor.get_anim_names())
        # Structural pick, not name: Blender 5 ACTIVE_ACTIONS export
        # merges the clip under the exporter default 'Animation'
        # (field note 2026-07-19) — one clip is the contract.
        clip = 'FaceTest' if 'FaceTest' in names else (
            names[0] if len(names) == 1 else None)
        fact('anim_clip_delivered', clip is not None,
             f'actor.get_anim_names() = {names} -> using {clip!r}')

        # b. engine truth on a byte-patched copy.
        tmpdir = tempfile.mkdtemp(prefix='paxtest_morph_')
        patched = os.path.join(tmpdir, 'morph_head_patched.glb')
        shutil.copy(anim_path, patched)
        with open(patched, 'r+b') as f:
            buf = bytearray(raw)
            n_keys = in_acc['count']
            targets_per_key = out_acc['count'] // n_keys
            vals = [0.0] * out_acc['count']
            # Write the ramp target into the LAST TWO keys: the panda
            # frame range ends at t=(num_frames-1)/fps, which can land
            # exactly ON the penultimate key (dense-key clips) — one
            # patched key would then never be sampled.
            ramp = [1.0, 0.5, 0.25][:targets_per_key]
            vals[-targets_per_key:] = ramp
            if n_keys >= 2:
                vals[-2 * targets_per_key:-targets_per_key] = ramp
            buf[w_off:w_off + 4 * out_acc['count']] = struct.pack(
                f'<{out_acc["count"]}f', *vals)
            f.write(buf)
        pactor = Actor(p3d.Filename.from_os_specific(
            patched).get_fullpath())
        pactor.reparent_to(base.render)
        pchar = pactor.find('**/+Character')
        _, psliders = find_sliders(pchar)
        pnames = pactor.get_anim_names()
        pclip = 'FaceTest' if 'FaceTest' in pnames else (
            pnames[0] if len(pnames) == 1 else None)
        if all(psliders.values()) and pclip:
            pactor.pose(pclip, 0)   # bind before frame queries
            nf = pactor.get_num_frames(pclip)
            readings = {}
            for frame in (0, nf - 1):
                pactor.pose(pclip, frame)
                h.step(2)
                pchar.node().force_update()
                readings[frame] = {n: s.get_value()
                                   for n, s in psliders.items()}
            want_end = dict(zip(SLIDERS, [1.0, 0.5, 0.25]))
            start = readings[0]
            end = readings[nf - 1]
            ok = (all(abs(v) < 0.02 for v in start.values())
                  and all(abs(end[n] - want_end[n]) < 0.02
                          for n in SLIDERS))
            fact('anim_weights_channel_drives_sliders', ok,
                 f'byte-patched ramp to (1.0, 0.5, 0.25): frame 0 '
                 f'{ {n: round(v, 3) for n, v in start.items()} } -> '
                 f'frame {nf - 1} '
                 f'{ {n: round(v, 3) for n, v in end.items()} } '
                 f'(needs the gltf_compat short-channel + lerp fixes)')
        else:
            fact('anim_weights_channel_drives_sliders', False,
                 'patched copy did not deliver sliders/clip')
        pactor.cleanup()

    # ------------------------------------------------------------------
    # 4. cost datapoint: one head, FaceTest looping, HW vs CPU opt-out
    # ------------------------------------------------------------------
    if actor is not None and clip:
        frame_head(h, base)
        actor.loop(clip)
        h.step(10)  # warm up

        def time_steps(n=120):
            t0 = time.perf_counter()
            h.step(n)
            return (time.perf_counter() - t0) * 1000.0 / n

        ms_hw = time_steps()
        pipeline.set_hardware_skinning(actor, False)
        h.step(10)
        ms_cpu = time_steps()
        pipeline.clear_hardware_skinning(actor)
        fact('cpu_fallback_cost_one_head', True,
             f'{h.win_w}x{h.win_h} offscreen, 2240-vert head, FaceTest '
             f'looping: HW {ms_hw:.2f} ms/frame, CPU opt-out '
             f'{ms_cpu:.2f} ms/frame (delta {ms_cpu - ms_hw:+.2f})')
        actor.cleanup()

    print(f'\nprobe_morph_gltf: {len(PASS_)} facts measured')


if __name__ == '__main__':
    main()
