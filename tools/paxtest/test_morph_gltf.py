"""paxtest: glTF morph delivery end-to-end (fact #16 gate).

Promoted from probe_morph_gltf.py (Session T) once the character dev's
re-exported SK_SFM_Head1 anim variant landed (2026-07-19, second
delivery — real weights values, 90 keys x 3 targets, terminal key).

What this row guards, permanently:

  1. pax3d_render.gltf_compat.install() keeps making Blender-default
     morph exports loadable (sparse accessors, short channels, lerp
     clamp — upstream panda3d-gltf 1.3.0 fails all three).
  2. The loader delivers sliders + slider tables on skinned AND
     joint-less meshes, and the CPU path reproduces the Blender
     ground-truth manifest exactly.
  3. Fact #15/#16 render behavior: the DEFAULT hardware-skinning path
     drops morphs (silently) — that stays true and hw_drops_morphs
     stays its guard, because the GPU morph path (Session Z,
     set_gpu_morphs) landed OPT-IN: enabling it is the fix, not
     enabling it is byte-identical to the shipped pipeline.
  4. The GPU morph path itself: set_gpu_morphs makes sliders render
     on the HW-skinning path (delta texture + morph_index column +
     GPU_MORPHS variant), matches the CPU-valve ground truth within
     the fact-#13 image bar, composes sparse multi-slider sets, and
     restores byte-identically on opt-out.
  5. A real exporter-authored weights animation drives the sliders
     through Actor (structural clip pick — Blender 5 ACTIVE_ACTIONS
     merges under the exporter-default name 'Animation').
  6. Session AB crowd/bake contract: the zero-copy fast bake and the
     per-column reorder bake produce byte-identical delta textures
     (and the loader still ships the interleaved-in-slider-order
     array that makes the fast path available); a copy_to clone
     registers with ZERO new textures, drives its OWN face, ignores
     the template's sliders, and detaches cleanly on opt-out.

Only meaningful for pax3d_render (needs the per-node skinning API).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
from probe_morph_gltf import (ASSETS, MANIFEST, SLIDERS, POS_TOL,
                              find_sliders, frame_head, read_positions,
                              set_slider, vec_close)


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'morph_gltf')
    if h.adapter.name != 'pax3d_render':
        h.report.skip('glTF morph gate is pax3d_render-only '
                      '(needs set_hardware_skinning)')
    p3d.BamCache.get_global_ptr().set_active(False)
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = h.adapter.pipeline
    base = h.base

    try:
        import gltf  # noqa: F401  (loader self-registers on import)
        from direct.actor.Actor import Actor
    except Exception as exc:
        h.report.skip(f'panda3d-gltf unavailable: {exc}')
    if not os.path.exists(MANIFEST):
        h.report.skip('morph_head assets not present')

    import json
    with open(MANIFEST, encoding='utf-8') as f:
        manifest = json.load(f)
    truth = manifest['ground_truth']

    from pax3d_render import gltf_compat
    installed = gltf_compat.install()
    h.report.check('shim_installs', installed or True,
                   f'gltf_compat.install() -> {installed} (sparse '
                   f'densify + short-channel + lerp fixes active)')

    alight = p3d.AmbientLight('ambient')
    alight.set_color(p3d.LColor(0.5, 0.5, 0.5, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -0.7, 0.7), (2.0, 2.0, 2.0))

    def load(name):
        return base.loader.load_model(p3d.Filename.from_os_specific(
            os.path.join(ASSETS, name)).get_fullpath())

    def delivery(tag, model_np):
        char_np = model_np.find('**/+Character')
        if char_np.is_empty():
            h.report.check(f'{tag}_delivery', False, 'no Character node')
            return None, None
        _, sliders = find_sliders(char_np)
        got = sorted(n for n, s in sliders.items() if s is not None)
        table = any(
            g.node().get_geom(i).get_vertex_data().get_slider_table()
            is not None
            for g in model_np.find_all_matches('**/+GeomNode')
            for i in range(g.node().get_num_geoms()))
        ok = got == sorted(SLIDERS) and table
        h.report.check(f'{tag}_delivery', ok,
                       f'sliders={got}, slider_table={table}')
        return (char_np, sliders) if ok else (char_np, None)

    # --- skinned variant: delivery + CPU truth + render paths --------
    skinned = load('morph_head_skinned.glb')
    char_np, sliders = delivery('skinned', skinned)
    skinned.reparent_to(base.render)

    if sliders:
        worst = 0.0
        pos_ok = True
        for name in SLIDERS:
            set_slider(char_np, sliders[name], 0.0)
            p0 = read_positions(skinned)
            set_slider(char_np, sliders[name], 1.0)
            p1 = read_positions(skinned)
            set_slider(char_np, sliders[name], 0.0)
            best_d, best_i = 0.0, -1
            for i, (a, b) in enumerate(zip(p0, p1)):
                d = (b - a).length()
                if d > best_d:
                    best_d, best_i = d, i
            worst = max(worst, abs(best_d - truth[name]['max_delta_m']))
            if not (vec_close(p0[best_i],
                              truth[name]['max_delta_vertex_at_0'])
                    and vec_close(p1[best_i],
                                  truth[name]['max_delta_vertex_at_1'])):
                pos_ok = False
        h.report.check('cpu_truth_matches_manifest',
                       worst <= POS_TOL and pos_ok,
                       f'3 sliders: worst |max_delta - truth| = '
                       f'{worst:.5f} m, argmax positions match={pos_ok}')

        frame_head(h, base)

        def rms_ab(slider):
            set_slider(char_np, slider, 0.0)
            h.step(4)
            a = h.capture()
            set_slider(char_np, slider, 1.0)
            h.step(4)
            b = h.capture()
            set_slider(char_np, slider, 0.0)
            return common.image_rms_diff(a, b, step=1)

        rms_hw = rms_ab(sliders['jaw_open'])
        h.report.check('hw_drops_morphs', rms_hw < 1e-6,
                       f'jaw_open 0->1 rms {rms_hw:.6f} on the DEFAULT '
                       f'HW path (fact #16; the opt-in fix is '
                       f'set_gpu_morphs — gpu_renders_morphs below)')
        pipeline.set_hardware_skinning(skinned, False)
        rms_cpu = rms_ab(sliders['jaw_open'])
        h.report.check('cpu_optout_renders_morphs', rms_cpu > 0.002,
                       f'same A/B on set_hardware_skinning(np, False): '
                       f'rms {rms_cpu:.5f}')
        pipeline.clear_hardware_skinning(skinned)

        # --- GPU morph path (Session Z: set_gpu_morphs) --------------
        def capture_at(values):
            """Capture with the named sliders held at the given values
            (all back to 0 afterwards)."""
            for name, v in values.items():
                set_slider(char_np, sliders[name], v)
            h.step(4)
            img = h.capture()
            for name in values:
                set_slider(char_np, sliders[name], 0.0)
            h.step(1)
            return img

        img_before = capture_at({})
        n_geoms = pipeline.set_gpu_morphs(skinned)
        h.report.check('gpu_morphs_convert', n_geoms == 1,
                       f'set_gpu_morphs converted {n_geoms} morph '
                       f'geom(s) (expected 1)')

        rms_gpu = rms_ab(sliders['jaw_open'])
        h.report.check('gpu_renders_morphs', rms_gpu > 0.002,
                       f'jaw_open 0->1 rms {rms_gpu:.5f} on the HW '
                       f'path WITH set_gpu_morphs — sliders render '
                       f'without the CPU valve (fact #15 closed, '
                       f'opt-in)')

        img_gpu_jaw = capture_at({'jaw_open': 1.0})
        # Sparse compose: first and LAST texture rows together proves
        # row addressing + the compact live-slot fill, not just "moves".
        img_gpu_two = capture_at({'blink': 0.6, 'brow_raise': 1.0})

        pipeline.set_gpu_morphs(skinned, False)
        img_after = capture_at({})
        rms_restore = common.image_rms_diff(img_before, img_after,
                                            step=1)
        h.report.check('gpu_optout_restores', rms_restore < 1e-6,
                       f'set_gpu_morphs(np, False): rms vs pre-enable '
                       f'{rms_restore:.6f} (geom states restored '
                       f'exactly)')

        pipeline.set_hardware_skinning(skinned, False)
        img_cpu_jaw = capture_at({'jaw_open': 1.0})
        img_cpu_two = capture_at({'blink': 0.6, 'brow_raise': 1.0})
        pipeline.clear_hardware_skinning(skinned)

        rms_jaw = common.image_rms_diff(img_gpu_jaw, img_cpu_jaw,
                                        step=1)
        h.report.check('gpu_matches_cpu', rms_jaw < 0.02,
                       f'jaw_open=1 image, GPU morphs vs CPU valve: '
                       f'rms {rms_jaw:.4f} (fact-#13 bar 0.02; both '
                       f'paths apply position AND normal deltas)')
        rms_two = common.image_rms_diff(img_gpu_two, img_cpu_two,
                                        step=1)
        h.report.check('gpu_sparse_compose_matches_cpu', rms_two < 0.02,
                       f'blink=0.6 + brow_raise=1 image, GPU vs CPU: '
                       f'rms {rms_two:.4f}')

        # --- Session AB: fast bake == reorder bake, byte-level -------
        def bake_blobs():
            entry = next(e for e in pipeline._gpu_morph_entries
                         if e['np'] == skinned)
            seen = {}
            for _g, _i, _s, t, _tx in entry['geoms']:
                seen[t.this] = t
            return sorted(bytes(t.get_ram_image())
                          for t in seen.values())

        # the fast path must be AVAILABLE on loader output (the
        # interleaved-in-slider-order array is what makes production
        # bakes zero-copy — a loader layout change should fail loudly
        # here, not silently fall back to the slow path)
        snames = [n for _r, n, _s
                  in pipeline._character_sliders(skinned)]
        want = []
        for n in snames:
            want += ['vertex.morph.' + n, 'normal.morph.' + n]
        fast_avail = False
        for g in skinned.find_all_matches('**/+GeomNode'):
            for i in range(g.node().get_num_geoms()):
                vd = g.node().get_geom(i).get_vertex_data()
                if vd.get_slider_table() is None:
                    continue
                fmt = vd.get_format()
                for ai in range(fmt.get_num_arrays()):
                    arrf = fmt.get_array(ai)
                    if (arrf.get_num_columns() == len(want)
                            and arrf.get_stride() == 12 * len(want)
                            and [str(arrf.get_column(ci).get_name())
                                 for ci in range(len(want))] == want):
                        fast_avail = True

        pipeline.set_gpu_morphs(skinned)
        blobs_fast = bake_blobs()
        pipeline.set_gpu_morphs(skinned, False)
        pcls = type(pipeline)
        try:
            import numpy  # noqa: F401
            have_numpy = True
        except ImportError:
            have_numpy = False
        try:
            pcls._MORPH_FAST_BAKE = False
            pipeline.set_gpu_morphs(skinned)
            blobs_np = bake_blobs()      # numpy gather (if importable)
            pipeline.set_gpu_morphs(skinned, False)
            pcls._MORPH_NUMPY_REORDER = False
            pipeline.set_gpu_morphs(skinned)
            blobs_py = bake_blobs()      # pure-Python fallback
            pipeline.set_gpu_morphs(skinned, False)
        finally:
            pcls._MORPH_FAST_BAKE = True
            pcls._MORPH_NUMPY_REORDER = True
        same = blobs_fast == blobs_np == blobs_py
        h.report.check('bake_fast_matches_reorder',
                       fast_avail and same,
                       f'fast path available on loader output='
                       f'{fast_avail}; zero-copy vs reorder(numpy='
                       f'{have_numpy}) vs reorder(pure-py) texture '
                       f'bytes identical={same} ({len(blobs_fast)} '
                       f'texture(s), '
                       f'{sum(len(b) for b in blobs_fast)} bytes)')

        # --- Session AB: copy_to clone = independent face, no bake ---
        pipeline.set_gpu_morphs(skinned)
        entry_t = next(e for e in pipeline._gpu_morph_entries
                       if e['np'] == skinned)
        ptrs_t = {t.this for _g, _i, _s, t, _tx in entry_t['geoms']}
        tmpl_jaw = capture_at({'jaw_open': 1.0})

        clone = skinned.copy_to(base.render)
        skinned.detach_node()   # clone sits at the same transform
        n_clone = pipeline.set_gpu_morphs(clone)
        entry_c = next(e for e in pipeline._gpu_morph_entries
                       if e['np'] == clone)
        ptrs_c = {t.this for _g, _i, _s, t, _tx in entry_c['geoms']}
        h.report.check('copy_reuses_textures',
                       n_clone == 1 and ptrs_c == ptrs_t,
                       f'set_gpu_morphs(clone): {n_clone} geom(s), '
                       f'delta textures pointer-shared with template='
                       f'{ptrs_c == ptrs_t} (zero re-bake)')

        cchar_np = clone.find('**/+Character')
        _, csliders = find_sliders(cchar_np)

        def capture_clone(values):
            for name, v in values.items():
                set_slider(cchar_np, csliders[name], v)
            h.step(4)
            img = h.capture()
            for name in values:
                set_slider(cchar_np, csliders[name], 0.0)
            h.step(1)
            return img

        img_c_rest = capture_clone({})
        img_c_jaw = capture_clone({'jaw_open': 1.0})
        rms_moves = common.image_rms_diff(img_c_jaw, img_c_rest,
                                          step=1)
        rms_same = common.image_rms_diff(img_c_jaw, tmpl_jaw, step=1)
        h.report.check('copy_drives_own_face',
                       rms_moves > 0.002 and rms_same < 0.02,
                       f'clone jaw_open=1 via the CLONE\'s sliders: '
                       f'moves (rms {rms_moves:.5f} vs rest), matches '
                       f'the template\'s own jaw image (rms '
                       f'{rms_same:.4f})')

        # the synchronized-face defect: the template's sliders must
        # NOT reach a registered clone (pre-AB, the inherited uniform
        # block made every clone wear the template's face)
        set_slider(char_np, sliders['jaw_open'], 1.0)
        h.step(4)
        img_c_follow = h.capture()
        set_slider(char_np, sliders['jaw_open'], 0.0)
        h.step(1)
        rms_follow = common.image_rms_diff(img_c_follow, img_c_rest,
                                           step=1)
        h.report.check('copy_ignores_template_sliders',
                       rms_follow < 1e-6,
                       f'template jaw_open=1 while clone rests: clone '
                       f'image rms vs rest {rms_follow:.6f}')

        # opt-out on the clone stops driving it; template unaffected
        pipeline.set_gpu_morphs(clone, False)
        img_c_dead = capture_clone({'jaw_open': 1.0})
        rms_dead = common.image_rms_diff(img_c_dead, img_c_rest,
                                         step=1)
        clone.remove_node()
        skinned.reparent_to(base.render)
        img_t_again = capture_at({'jaw_open': 1.0})
        rms_t_again = common.image_rms_diff(img_t_again, tmpl_jaw,
                                            step=1)
        h.report.check('copy_optout_isolated',
                       rms_dead < 1e-6 and rms_t_again < 1e-6,
                       f'disabled clone ignores its sliders (rms '
                       f'{rms_dead:.6f}); template still drives (rms '
                       f'{rms_t_again:.6f} vs its earlier jaw image)')
        pipeline.set_gpu_morphs(skinned, False)
    skinned.detach_node()

    # --- static (joint-less) variant: delivery only (render behavior
    # is the same class, measured by the probe) ----------------------
    static = load('morph_head_static.glb')
    delivery('static', static)

    # --- real clip drives the sliders through Actor ------------------
    actor = Actor(p3d.Filename.from_os_specific(os.path.join(
        ASSETS, 'morph_head_skinned_anim.glb')).get_fullpath())
    actor.reparent_to(base.render)
    names = sorted(actor.get_anim_names())
    clip = 'FaceTest' if 'FaceTest' in names else (
        names[0] if len(names) == 1 else None)
    achar = actor.find('**/+Character')
    _, asliders = find_sliders(achar)
    if clip and all(asliders.values()):
        actor.pose(clip, 0)
        nf = actor.get_num_frames(clip)
        peaks = {n: (0.0, -1) for n in SLIDERS}
        at_zero = {}
        for frame in range(nf):
            actor.pose(clip, frame)
            achar.node().force_update()
            for n, s in asliders.items():
                v = s.get_value()
                if frame == 0:
                    at_zero[n] = v
                if v > peaks[n][0]:
                    peaks[n] = (v, frame)
        peak_ok = all(v >= 0.98 for v, _ in peaks.values())
        zero_ok = all(abs(v) <= 0.02 for v in at_zero.values())
        order_ok = (peaks['blink'][1] < peaks['jaw_open'][1]
                    < peaks['brow_raise'][1])
        h.report.check(
            'clip_drives_sliders', peak_ok and zero_ok and order_ok,
            f'clip {clip!r} ({nf}f): peaks '
            + ', '.join(f'{n}={v:.2f}@f{fr}'
                        for n, (v, fr) in peaks.items())
            + f'; frame0 zeros={zero_ok}, order={order_ok}')
    else:
        h.report.check('clip_drives_sliders', False,
                       f'clip={clip!r}, sliders='
                       f'{sorted(n for n, s in asliders.items() if s)}')
    actor.cleanup()

    h.report.finish()


if __name__ == '__main__':
    main()
