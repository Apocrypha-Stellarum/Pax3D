"""paxtest: effect sprites (Session AD — explosion/impact flipbooks).

pipeline.spawn_effect() plays a PREMULTIPLIED-alpha atlas (baked
explosion footage — tools/gen_flipbook.py) on a camera-facing quad as
pure emission: set_screen(albedo=False, metallic=1) zeroes every lit
term (diffuse_color and spec_color are both exactly 0 at metallic-1
black base), set_glass() gives M_premultiplied_alpha blending with
coverage-weighted fog/atmosphere, play_flipbook() steps the UV window,
and the pipeline reaps the quad when playback completes.

Scene: ortho camera, sun BLACK, flat AmbientLight AMB, a gray albedo
card filling the window as the composite background. The effect atlas
is a synthetic 2x2-cell (1px cells, nearest) premultiplied sprite, so
every check is analytic per channel:

    background:  B = AMB*(KD*0.5 + F0)
    effect over: lin[ch] = e[ch]*cell[ch] + B*(1 - cell.a)
    (e = emission_scale * emission_color, premultiplied compositing)

Cells: f0 premult smoke (0.25,0.10,0.05|a .5), f1 pure additive glow
(0.20 gray|a 0 — background must survive untouched), f2 opaque core
(1,.3,.1|a 1), f3 fully transparent.

Checks: baseline anchor, premultiplied composite, additive glow,
opaque core, unlit-ness (ambient x4 cannot move an effect pixel),
remove_effect byte-identical restore, HDR emission scale*tint,
billboard vs rotated parent (+ static quad control), one-shot
completion self-cleanup (node gone, registries empty, byte-identical),
shadow-mask exclusion, and gen_flipbook atlas assembly (RGBA exact,
RGB path unchanged).

Runs in both sun modes (run.py adds @directional): the unlit contract
must hold whether the sun is the world-space uniform block or a real
DirectionalLight in the p3d_LightSource loop.

Only meaningful for pipelines exposing spawn_effect (pax3d_render).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..'))

import panda3d.core as p3d

import common

AMB = 0.02
F0 = 0.04
KD = 1.0 - F0
GRAY = 0.5

# Atlas cells, row-major from the TOP-LEFT (contact-sheet order):
# (r, g, b, a) — premultiplied (rgb <= a except the deliberate
# additive-glow cell, the pattern the CGVision footage measured).
CELLS = [
    (0.25, 0.10, 0.05, 0.5),   # f0 translucent fireball smoke
    (0.20, 0.20, 0.20, 0.0),   # f1 pure additive glow
    (1.00, 0.30, 0.10, 1.0),   # f2 opaque core
    (0.00, 0.00, 0.00, 0.0),   # f3 fully transparent (end state)
]


def make_effect_atlas():
    img = p3d.PNMImage(2, 2, 4)
    for i, (r, g, b, a) in enumerate(CELLS):
        x, y = i % 2, i // 2               # PNM row 0 = atlas TOP row
        img.set_xel(x, y, r, g, b)
        img.set_alpha(x, y, a)
    tex = p3d.Texture('paxtest_effect_atlas')
    tex.load(img)
    tex.set_minfilter(p3d.SamplerState.FT_nearest)
    tex.set_magfilter(p3d.SamplerState.FT_nearest)
    return tex


def make_background(parent):
    cm = p3d.CardMaker('paxtest_effect_bg')
    cm.set_frame(-4, 4, -3, 3)
    np = parent.attach_new_node(cm.generate())
    np.set_pos(0, 10, 0)                   # behind the effect quad

    mat = p3d.Material('paxtest_effect_bg_mat')
    mat.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat.set_roughness(0.5)
    mat.set_metallic(0.0)
    np.set_material(mat, 1)

    gray = p3d.Texture('paxtest_gray')
    gray_img = p3d.PNMImage(1, 1)
    gray_img.set_xel(0, 0, GRAY, GRAY, GRAY)
    gray.load(gray_img)
    np.set_texture(gray, 1)
    mr_stage = p3d.TextureStage('paxtest_mr')
    mr_stage.set_mode(p3d.TextureStage.M_selector)
    white = p3d.Texture('paxtest_white')
    white_img = p3d.PNMImage(1, 1)
    white_img.set_xel(0, 0, 1, 1, 1)
    white.load(white_img)
    np.set_texture(mr_stage, white, 1)
    return np


def avg_rgb(img, cx, cy, half=2):
    r = g = b = 0.0
    n = 0
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            c = img.get_xel(int(cx + dx), int(cy + dy))
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

    h = common.Harness(args, 'effects')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'spawn_effect'):
        h.report.skip('pipeline has no spawn_effect (Session AD)')
    base = h.base
    curve = common.CURVES['hejl_dawson']

    # Pin the clock (the Session-X lesson): flipbook/lifecycle advance by
    # frame time, so 30 deterministic steps = 1.0 s regardless of load.
    clock = p3d.ClockObject.get_global_clock()
    clock.set_mode(p3d.ClockObject.M_non_real_time)
    clock.set_dt(1.0 / 30.0)

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))    # sun black
    h.set_ortho(film_h=2.0)

    make_background(base.render)
    atlas = make_effect_atlas()

    B = AMB * (KD * GRAY + F0)                     # background, linear
    center = (h.win_w * 0.5, h.win_h * 0.5)
    corner = (h.win_w * 0.08, h.win_h * 0.5)       # outside the quad

    def expected(cell, scale=1.0, color=(1.0, 1.0, 1.0)):
        return tuple(curve(scale * color[ch] * cell[ch]
                           + B * (1.0 - cell[3])) for ch in range(3))

    def check_px(name, img, want, at=None, tol=0.03, extra=''):
        got = avg_rgb(img, *(at or center))
        err = max(abs(g - w) for g, w in zip(got, want))
        h.report.check(name, err < tol,
                       f'got ({got[0]:.3f},{got[1]:.3f},{got[2]:.3f}) '
                       f'want ({want[0]:.3f},{want[1]:.3f},{want[2]:.3f}) '
                       f'err {err:.3f}{extra}')

    def force_frame(np_, f):
        off_u, off_v, su, sv = pipeline._flipbook_transform(2, 2, f)
        pipeline.set_uv_transform(np_, offset=(off_u, off_v),
                                  scale=(su, sv))

    def registries_empty():
        return (not pipeline._effects and not pipeline._flipbooks
                and not pipeline._screen_nodes
                and not pipeline._glass_nodes
                and not pipeline._emission_overrides)

    # --- 1. Baseline anchor (gray background, ambient only) -------------
    h.step(5)
    img_base = h.capture()
    h.save_capture(img_base, 'baseline')
    check_px('baseline_analytic', img_base, (curve(B),) * 3,
             extra=' (gray card under flat ambient)')

    # --- 2. Premultiplied composite (translucent fireball cell) ---------
    fx = pipeline.spawn_effect(atlas, cols=2, rows=2, num_frames=4,
                               fps=1e-3, pos=(0, 5, 0), size=1.0,
                               loop=True)
    h.step(5)
    img_fx = h.capture()
    h.save_capture(img_fx, 'premult')
    check_px('premult_composite_analytic', img_fx, expected(CELLS[0]),
             extra=' (emission + B*(1-a), the premultiplied contract)')

    # --- 3. Additive glow: a=0 leaves the background fully lit ----------
    force_frame(fx, 1)
    h.step(5)
    img_add = h.capture()
    h.save_capture(img_add, 'additive')
    check_px('additive_glow_analytic', img_add, expected(CELLS[1]),
             extra=' (rgb>0 at a=0 adds light, occludes nothing)')

    # --- 4. Opaque core: background fully replaced ----------------------
    force_frame(fx, 2)
    h.step(5)
    img_core = h.capture()
    check_px('opaque_core_analytic', img_core, expected(CELLS[2]),
             extra=' (a=1: emission only, B*(1-1)=0)')

    # --- 5. Unlit-ness: scene light cannot move an effect pixel ---------
    # metallic-1 black base: diffuse_color and spec_color are both
    # exactly 0, so quadrupling the ambient may only move the BACKGROUND.
    alight.set_color(p3d.LColor(4 * AMB, 4 * AMB, 4 * AMB, 1))
    h.step(5)
    img_bright = h.capture()
    fx_moved = max(abs(a - b) for a, b in
                   zip(avg_rgb(img_core, *center),
                       avg_rgb(img_bright, *center)))
    bg_moved = max(abs(a - b) for a, b in
                   zip(avg_rgb(img_core, *corner),
                       avg_rgb(img_bright, *corner)))
    h.report.check('effect_unlit', fx_moved < 0.005 and bg_moved > 0.01,
                   f'ambient x4: effect pixel moved {fx_moved:.4f} '
                   f'(must not), background moved {bg_moved:.4f} (must)')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))

    # --- 6. remove_effect: byte-identical restore + empty registries ----
    pipeline.remove_effect(fx)
    h.step(5)
    rms = common.image_rms_diff(img_base, h.capture(), step=1)
    h.report.check('remove_effect_restores',
                   rms == 0.0 and registries_empty(),
                   f'rms vs baseline = {rms:.2e}, registries empty = '
                   f'{registries_empty()}')

    # --- 7. HDR emission scale * tint ------------------------------------
    fx = pipeline.spawn_effect(atlas, cols=2, rows=2, num_frames=4,
                               fps=1e-3, pos=(0, 5, 0), size=1.0,
                               loop=True, emission_scale=2.0,
                               emission_color=(1.0, 0.5, 0.25))
    h.step(5)
    check_px('emission_scale_tint', h.capture(),
             expected(CELLS[0], scale=2.0, color=(1.0, 0.5, 0.25)),
             extra=' (scale 2 * tint (1,.5,.25), HDR-legal)')
    pipeline.remove_effect(fx)

    # --- 8. Billboard faces the camera through a rotated parent ---------
    rot = base.render.attach_new_node('paxtest_effect_rot')
    rot.set_pos(0, 5, 0)
    rot.set_h(90)                       # a static quad here is edge-on
    fx = pipeline.spawn_effect(atlas, cols=2, rows=2, num_frames=4,
                               fps=1e-3, pos=(0, 0, 0), size=1.0,
                               loop=True)
    fx.reparent_to(rot)
    h.step(5)
    check_px('billboard_faces_camera', h.capture(), expected(CELLS[0]),
             extra=' (parent H=90: billboard still faces the eye)')
    pipeline.remove_effect(fx)

    fx = pipeline.spawn_effect(atlas, cols=2, rows=2, num_frames=4,
                               fps=1e-3, pos=(0, 0, 0), size=1.0,
                               loop=True, billboard=False, parent=rot)
    h.step(5)
    rms = common.image_rms_diff(img_base, h.capture(), step=1)
    h.report.check('static_quad_edge_on', rms == 0.0,
                   f'billboard=False inherits H=90 (edge-on, invisible): '
                   f'rms vs baseline = {rms:.2e}')
    pipeline.remove_effect(fx)
    rot.remove_node()

    # --- 9. One-shot lifecycle: plays, completes, cleans up itself ------
    fx = pipeline.spawn_effect(atlas, cols=2, rows=2, num_frames=4,
                               fps=30.0, pos=(0, 5, 0), size=1.0,
                               loop=False)          # 4 frames @ 30 fps
    h.step(2)
    visible = common.image_rms_diff(img_base, h.capture(), step=1)
    h.step(10)                          # 10/30 s >> 4/30 s duration
    img_after = h.capture()
    rms = common.image_rms_diff(img_base, img_after, step=1)
    h.report.check('one_shot_completes_cleans',
                   visible > 1e-5 and fx.is_empty()
                   and registries_empty() and rms == 0.0,
                   f'played (rms {visible:.5f}) then self-reaped: node '
                   f'empty = {fx.is_empty()}, registries empty = '
                   f'{registries_empty()}, rms vs baseline = {rms:.2e}')

    # --- 10. Shadow-mask exclusion --------------------------------------
    pipeline.set_shadow_caster_mask(4)
    fx = pipeline.spawn_effect(atlas, cols=2, rows=2, num_frames=4,
                               fps=1e-3, pos=(0, 5, 0), size=1.0,
                               loop=True)
    hidden = fx.is_hidden(pipeline.shadow_caster_mask)
    h.report.check('effect_excluded_from_shadows', hidden,
                   f'quad hidden from the shadow caster mask = {hidden} '
                   f'(the depth pass never reads alpha — fact #17)')
    pipeline.remove_effect(fx)

    # --- 11. gen_flipbook atlas assembly (alpha + RGB regression) -------
    import gen_flipbook

    def cell_img(r, g, b, a=None):
        img = p3d.PNMImage(2, 1, 4 if a is not None else 3)
        for x in range(2):
            img.set_xel(x, 0, r, g, b)
            if a is not None:
                img.set_alpha(x, 0, a)
        return img

    rgba_frames = [cell_img(1.0, 0.5, 0.25, 0.5),
                   cell_img(0.25, 0.5, 1.0, 0.0),
                   cell_img(0.0, 1.0, 0.0, 1.0)]
    atlas_a, cols_a, rows_a = gen_flipbook.assemble_atlas(rgba_frames)
    ok = atlas_a.get_num_channels() == 4
    worst = 0.0
    for i, src in enumerate(rgba_frames):
        cx, cy = (i % cols_a) * 2, (i // cols_a) * 1
        for x in range(2):
            got = atlas_a.get_xel(cx + x, cy)
            want = src.get_xel(x, 0)
            worst = max(worst, max(abs(g - w) for g, w in
                                   zip(got, want)),
                        abs(atlas_a.get_alpha(cx + x, cy)
                            - src.get_alpha(x, 0)))
    # Unused trailing cell must be fully transparent black.
    n_cells = cols_a * rows_a
    if n_cells > len(rgba_frames):
        i = len(rgba_frames)
        cx, cy = (i % cols_a) * 2, (i // cols_a) * 1
        worst = max(worst, atlas_a.get_alpha(cx, cy),
                    max(atlas_a.get_xel(cx, cy)))
    h.report.check('atlas_tool_alpha_exact', ok and worst < 1e-6,
                   f'{cols_a}x{rows_a} RGBA atlas, worst texel err '
                   f'{worst:.2e} (alpha survives assembly; trailing '
                   f'cell transparent)')

    rgb_frames = [cell_img(1.0, 0.5, 0.25), cell_img(0.25, 0.5, 1.0)]
    atlas_r, cols_r, _rows_r = gen_flipbook.assemble_atlas(rgb_frames)
    worst = 0.0
    for i, src in enumerate(rgb_frames):
        cx, cy = (i % cols_r) * 2, (i // cols_r) * 1
        for x in range(2):
            got = atlas_r.get_xel(cx + x, cy)
            want = src.get_xel(x, 0)
            worst = max(worst, max(abs(g - w) for g, w in
                                   zip(got, want)))
    h.report.check('atlas_tool_rgb_unchanged',
                   atlas_r.get_num_channels() == 3 and worst < 1e-6,
                   f'alpha-free sources still produce a 3-channel atlas '
                   f'(worst texel err {worst:.2e}) — screens unchanged')

    h.report.finish()


if __name__ == '__main__':
    main()
