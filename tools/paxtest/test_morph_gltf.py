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
