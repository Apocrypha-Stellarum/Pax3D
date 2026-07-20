"""probe_gpu_morph_bench — measured facts: the GPU morph path (Session
Z, set_gpu_morphs) at production scale, on the character lane's own
acceptance content (hero_{kade,wren,juno}.glb, 52 ARKit targets each,
11.6k-14.7k verts on the morphing mesh).

NOT a gate test (the gate rows live in test_morph_gltf). This probe
answers the character lane's perf questions from PAX3D_FEEDBACK.md
2026-07-20 with engine-side numbers:

  1. enable cost: set_gpu_morphs bake wall time + delta-texture bytes
     per hero (one-time, at load).
  2. per-frame Python cost: _step_gpu_morphs with N characters x 52
     sliders (the O(live) push).
  3. the 8-face datapoint: ms/frame with 8 production heads animating
     5 sliders each — GPU path vs the CPU valve (the 185->133 fps
     field measurement's engine-side sibling).
  4. the 32-face stretch datapoint (asked "measure once, not a gate"):
     baked copies at zero extra bake cost.

Run:  <python> tools/paxtest/probe_gpu_morph_bench.py --pipeline pax3d_render
      [--hero-dir DIR] [--hero hero_kade.glb] [--faces 8]

Session AB updates: the bake is the zero-copy vertex-major path (the
enable-cost fact re-measured), --hero selects any delivered head, and
the 32-face stretch leg registers every copy_to clone with its OWN
sliders (set_gpu_morphs(clone) — the crowd-independence contract) and
animates all 32 independently, which is what a real plaza does.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

HERO_DIR = r'C:\python\sfb2\assets\models\characters\heroes'
FALLBACK = os.path.join(common.HERE, 'assets', 'morph_head_skinned.glb')


def fact(name, value, detail=''):
    print(f'[fact] {name} = {value}   {detail}')


def find_char_sliders(model_np):
    """(char_np, [CharacterSlider]) for the first slider-carrying
    Character (bundle tree order)."""
    for char_np in model_np.find_all_matches('**/+Character'):
        bundle = char_np.node().get_bundle(0)
        out = []

        def walk(group):
            for i in range(group.get_num_children()):
                child = group.get_child(i)
                if isinstance(child, p3d.CharacterSlider):
                    out.append(child)
                walk(child)

        walk(bundle)
        if out:
            return char_np, out
    return None, []


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--hero-dir', default=HERO_DIR)
    parser.add_argument('--hero', default='hero_wren.glb')
    parser.add_argument('--faces', type=int, default=8)
    args = parser.parse_args()

    h = common.Harness(args, 'gpu_morph_bench')
    if h.adapter.name != 'pax3d_render':
        print('SKIP: needs pax3d_render')
        return
    p3d.BamCache.get_global_ptr().set_active(False)
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = h.adapter.pipeline
    base = h.base

    import gltf  # noqa: F401
    from pax3d_render import gltf_compat
    gltf_compat.install()

    hero = os.path.join(args.hero_dir, args.hero)
    if not os.path.exists(hero):
        print(f'hero content not found, falling back to {FALLBACK}')
        hero = FALLBACK

    alight = p3d.AmbientLight('ambient')
    alight.set_color(p3d.LColor(0.5, 0.5, 0.5, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -0.7, 0.7), (2.0, 2.0, 2.0))

    # --- load N faces, measure enable cost on each -------------------
    models = []
    t_loads = 0.0
    for i in range(args.faces):
        t0 = time.perf_counter()
        m = base.loader.load_model(p3d.Filename.from_os_specific(
            hero).get_fullpath(), noCache=True)
        t_loads += time.perf_counter() - t0
        m.reparent_to(base.render)
        m.set_x((i - args.faces / 2.0) * 0.5)
        models.append(m)
    fact('load_s_total', f'{t_loads:.2f}',
         f'{args.faces}x {os.path.basename(hero)}')

    bake_s = []
    n_geoms = 0
    for m in models:
        t0 = time.perf_counter()
        n_geoms = pipeline.set_gpu_morphs(m)
        bake_s.append(time.perf_counter() - t0)
    entry = pipeline._gpu_morph_entries[0]
    n_sliders = len(entry['sliders'])
    seen = {}
    for _g, _i, _s, t, _tx in entry['geoms']:
        seen[id(t)] = t
    tex_bytes = sum(t.get_ram_image_size() for t in seen.values())
    # vertex-major since Session AB: height = vertex rows
    verts = sum(t.get_y_size() for t in seen.values())
    fact('morph_mesh', f'{verts} verts x {n_sliders} targets',
         f'{n_geoms} morph geom(s) / {len(seen)} vdata(s) per face')
    fact('bake_s_per_face', f'{sum(bake_s) / len(bake_s):.2f}',
         f'first {bake_s[0]:.2f}, delta tex {tex_bytes / 1e6:.1f} MB '
         f'per face (one-time, at load)')

    chars = [find_char_sliders(m) for m in models]
    drive = [sl[:5] for _c, sl in chars]   # 5 live = today's repertoire

    # Frame the WHOLE row: Panda only updates Characters the cull
    # traversal reaches, so a head outside the frustum costs nothing
    # and poisons the comparison. Fit camera to the scene bounds.
    lo, hi = base.render.get_tight_bounds()
    center = (lo + hi) * 0.5
    extent = max(hi.x - lo.x, hi.z - lo.z)
    base.camera.set_pos(center.x, lo.y - extent * 1.6, center.z)
    base.camera.look_at(center)

    def animate(t):
        # freeze + force_update per character: a freeze alone does NOT
        # dirty the bundle (measured — the static/animate delta was
        # +0.01 ms without it), while in the real runtime playing clips
        # dirty it every frame. force_update models that for BOTH legs:
        # the CPU valve re-animates vertices, the GPU path re-poses
        # joints only.
        for face_i, ((char_np, _sl), sliders) in enumerate(
                zip(chars, drive)):
            for si, s in enumerate(sliders):
                v = 0.5 + 0.5 * ((t * (1.3 + 0.1 * si) + face_i) % 1.0)
                s.apply_freeze_scalar(v)
            char_np.node().force_update()

    def measure(frames=240, warmup=30):
        for f in range(warmup):
            animate(f / 60.0)
            h.step(1)
        t0 = time.perf_counter()
        for f in range(frames):
            animate((warmup + f) / 60.0)
            h.step(1)
        dt = time.perf_counter() - t0
        return 1000.0 * dt / frames

    # --- per-frame Python push cost, isolated ------------------------
    animate(0.35)
    t0 = time.perf_counter()
    reps = 1000
    for _ in range(reps):
        pipeline._step_gpu_morphs()
    step_ms = 1000.0 * (time.perf_counter() - t0) / reps
    fact('python_push_ms', f'{step_ms:.4f}',
         f'{args.faces} chars x {n_sliders} sliders, 5 live each '
         f'(_step_gpu_morphs, includes the no-change fast path miss)')

    # --- GPU path vs CPU valve, N faces ------------------------------
    ms_gpu = measure()
    fact(f'ms_frame_gpu_{args.faces}faces', f'{ms_gpu:.2f}',
         f'{1000.0 / ms_gpu:.0f} fps offscreen 512x512')

    for m in models:
        pipeline.set_gpu_morphs(m, False)
        pipeline.set_hardware_skinning(m, False)
    ms_cpu = measure()
    fact(f'ms_frame_cpuvalve_{args.faces}faces', f'{ms_cpu:.2f}',
         f'{1000.0 / ms_cpu:.0f} fps — the fact-#15 CPU fallback')

    # Cull sanity: the CPU valve only costs when sliders CHANGE and the
    # character is traversed. Static sliders must be measurably cheaper
    # or the animate legs above never exercised the morph path at all.
    for f in range(30):
        h.step(1)
    t0 = time.perf_counter()
    for f in range(240):
        h.step(1)
    ms_static = 1000.0 * (time.perf_counter() - t0) / 240
    fact('ms_frame_cpuvalve_static', f'{ms_static:.2f}',
         f'same scene, sliders frozen — the animate-leg delta '
         f'({ms_cpu - ms_static:+.2f} ms) is the CPU morph cost')

    for m in models:
        pipeline.clear_hardware_skinning(m)
        pipeline.set_gpu_morphs(m)

    # --- 32-face stretch datapoint: registered clones, all driven ----
    # Session AB: clones share the delta TEXTURES (pointer-shared by
    # the copied geom states; the vdata is deep-copied by the
    # Character — ~the morph-column bytes per clone in RAM) and each
    # gets its OWN face via set_gpu_morphs(clone): zero re-bake,
    # independent sliders. All 32 animate independently here — the
    # honest plaza scenario, not 24 statues wearing one face.
    copies = []
    extra = 32 - args.faces
    if extra > 0:
        t0 = time.perf_counter()
        for i in range(extra):
            c = models[i % len(models)].copy_to(base.render)
            c.set_x((i - extra / 2.0) * 0.5)
            c.set_y(1.0 + 0.5 * (i % 4))
            pipeline.set_gpu_morphs(c)
            copies.append(c)
        fact('copy_s_total', f'{time.perf_counter() - t0:.2f}',
             f'{extra} clones copied AND registered (delta textures '
             f'pointer-shared, zero re-bake, independent sliders)')
        chars.extend(find_char_sliders(c) for c in copies)
        drive.extend(sl[:5] for _c, sl in chars[len(drive):])
        ms_32 = measure()
        fact('ms_frame_gpu_32faces', f'{ms_32:.2f}',
             f'{1000.0 / ms_32:.0f} fps offscreen, all 32 driven '
             f'independently — stretch datapoint, not a gate')

    print('done')


if __name__ == '__main__':
    main()
