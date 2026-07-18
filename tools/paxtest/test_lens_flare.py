"""paxtest: lens flare/dirt (Session S — the R5 lens-polish finale).

`enable_lens_flare` — pseudo-flare ghosts sourced from the bloom
bright extract (lens_flare.frag). Because the source is the extract,
occlusion is implicit (no bright pixels -> no flare) and every bright
emitter flares consistently. Ghost positions are ANALYTIC: a source at
uv p produces ghost k at

    x_k = 0.5 + (p - 0.5) / c_k,   c in (-2.0, -3.5, 1.7, 3.0)

(the shader's pinned constants). The test places the emissive quad
OFF-CENTER HORIZONTALLY so every prediction sits on the center row —
independent of the screenshot row-order convention.

Checks:
  1. Baselines: bloom-on flare-off, bright quad shown + hidden.
  2. ghosts_at_predicted_positions — flare-on minus flare-off
     luminance rises at all four predicted ghost centers.
  3. control_off_axis_unchanged — an off-axis point gains nothing.
  4. dark_scene_no_flare — with the source hidden, flare-on renders
     byte-identical to flare-off (occlusion is implicit).
  5. flare_strength_zero — exact no-op (adds exactly 0).
  6. dirt_modulates — a left-black/right-white dirt texture kills the
     left-half ghosts and keeps the right-half ones;
     set_lens_dirt(None) restores byte-identically.
  7. opt_out_restores — set_enable_lens_flare(False) restores the
     bloom-only capture exactly.

Only meaningful for pipelines exposing set_enable_lens_flare
(pax3d_render and the routed pax_pbr adapter).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


QUAD_VALUE = 1000.0
QUAD_HALF = 0.03
SRC_X = 0.44            # world x (ortho film 2x2) -> uv 0.72, center row
GHOST_SCALES = (-2.0, -3.5, 1.7, 3.0)


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'lens_flare')
    if not h.adapter.supports_bloom:
        h.report.skip('pipeline has no bloom support')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    bloom={'strength': 1.0, 'intensity': 1.0, 'levels': 5})
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_enable_lens_flare'):
        h.report.skip('pipeline has no set_enable_lens_flare (Session S)')
    h.set_ortho(film_h=2.0)

    quad = scenes.make_emissive_quad(h.base.render, h.use_330,
                                     QUAD_VALUE, QUAD_HALF)
    quad.set_x(SRC_X)

    src_u = (SRC_X + 1.0) / 2.0
    cx, cy = h.win_w // 2, h.win_h // 2
    ghost_px = [int((0.5 + (src_u - 0.5) / c) * h.win_w)
                for c in GHOST_SCALES]
    control = (cx, cy + h.win_h // 4)      # off the ghost line entirely

    def snap(tag=None):
        h.step(6)
        img = h.capture()
        if tag:
            h.save_capture(img, tag)
        return img

    def lums(img):
        pts = [common.avg_lum(img, px, cy, half=3) for px in ghost_px]
        pts.append(common.avg_lum(img, control[0], control[1], half=3))
        return pts

    # --- 1. Baselines: flare off ---------------------------------------
    img_base = snap('bloom_only')
    base_l = lums(img_base)
    quad.hide()
    img_base_dark = snap('bloom_only_dark')
    quad.show()

    # --- 2/3. Flare on: ghosts at the predicted positions ---------------
    pipeline.set_enable_lens_flare(True)
    img_flare = snap('flare_on')
    fl = lums(img_flare)
    deltas = [f - b for f, b in zip(fl, base_l)]
    detail = ', '.join(f'c={c}: +{d:.3f}@px{p}' for c, d, p in
                       zip(GHOST_SCALES, deltas[:4], ghost_px))
    h.report.check('ghosts_at_predicted_positions',
                   all(d > 0.008 for d in deltas[:4]),
                   f'flare-on minus flare-off at the four analytic ghost '
                   f'centers: {detail}')
    h.report.check('control_off_axis_unchanged', abs(deltas[4]) < 0.005,
                   f'off-axis control point delta {deltas[4]:+.4f} '
                   f'(ghosts land only where the formula says)')

    # --- 4. Occlusion is implicit: dark scene, no flare ------------------
    quad.hide()
    img_dark = snap('flare_on_dark')
    rms = common.image_rms_diff(img_base_dark, img_dark, step=1)
    h.report.check('dark_scene_no_flare', rms == 0.0,
                   f'source hidden: flare-on vs flare-off rms = {rms:.2e} '
                   f'(no extract energy -> no flare, occlusion for free)')
    quad.show()

    # --- 5. Strength 0 is an exact no-op ---------------------------------
    pipeline.set_flare_strength(0.0)
    img_zero = snap()
    rms = common.image_rms_diff(img_base, img_zero, step=1)
    h.report.check('flare_strength_zero', rms == 0.0,
                   f'flare_strength 0.0: rms vs bloom-only = {rms:.2e} '
                   f'(adds exactly zero)')
    pipeline.set_flare_strength(1.0)

    # --- 6. Dirt modulates in screen space -------------------------------
    dirt_img = p3d.PNMImage(64, 64, 3)
    for y in range(64):
        for x in range(64):
            v = 1.0 if x >= 32 else 0.0
            dirt_img.set_xel(x, y, v, v, v)
    dirt_tex = p3d.Texture('paxtest_dirt')
    dirt_tex.load(dirt_img)
    pipeline.set_lens_dirt(dirt_tex, 1.0)
    img_dirt = snap('flare_dirt')
    dl = lums(img_dirt)
    d_deltas = [f - b for f, b in zip(dl, base_l)]
    # ghosts 0/1 (c negative) land LEFT of center (u < 0.5, black dirt);
    # ghosts 2/3 land RIGHT (white dirt)
    h.report.check(
        'dirt_modulates',
        d_deltas[0] < 0.005 and d_deltas[1] < 0.005
        and d_deltas[2] > 0.008 and d_deltas[3] > 0.008,
        f'left-black/right-white dirt: left ghosts +{d_deltas[0]:.3f}/'
        f'+{d_deltas[1]:.3f} (killed), right ghosts +{d_deltas[2]:.3f}/'
        f'+{d_deltas[3]:.3f} (kept)')
    pipeline.set_lens_dirt(None)
    img_clean = snap()
    rms = common.image_rms_diff(img_flare, img_clean, step=1)
    h.report.check('dirt_clear_restores', rms == 0.0,
                   f'set_lens_dirt(None): rms vs clean flare = {rms:.2e}')

    # --- 7. Opt-out restores ---------------------------------------------
    pipeline.set_enable_lens_flare(False)
    img_restored = snap()
    rms = common.image_rms_diff(img_base, img_restored, step=1)
    h.report.check('opt_out_restores', rms == 0.0,
                   f'set_enable_lens_flare(False): rms vs bloom-only = '
                   f'{rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
