"""paxtest: per-node ambient scale (Session L — hull interiors).

The hemisphere/SH ambient (R5.2) models open sky, so inside a ship hull
it floods enclosed spaces as if they were outdoors.
`pipeline.set_ambient_scale(np, k)` damps the INDIRECT terms (SH/IBL +
flat AmbientLight) for a subtree via an inherited shader input, while
direct light (sun shafts, local lights) and emission stay untouched.
The scale folds into the shader's ambient-occlusion factor, which
multiplies exactly the indirect terms — glass variants included.

Scene: the ambient_sh recipe — white up-facing card under a two-tone
hemisphere ambient (sun black), camera straight above, every value
analytic per channel:

  ambient(ch) = KD*(avg + 2/3*delta) + AMB      (KD = 1-F0 at ndv=1)
  scaled      = k * ambient(ch)
  with sun on = S*(diff + spec) + k*ambient(ch) (sun on the view axis)

Checks:
  1. Untouched card matches ambient(ch) — the root default 1.0 is an
     exact no-op (IEEE x*1.0), and the analytics anchor.
  2. set_ambient_scale(np, 0.25) matches 0.25*ambient(ch) per channel.
  3. The scale survives a shader-recompile-class toggle (root default
     re-pushed by input preservation; node input untouched by design).
  4. With the sun on and the scale still 0.25, the card matches
     S*(diff+spec) + 0.25*ambient — direct light is NOT scaled.
  5. clear_ambient_scale() restores the baseline capture byte-identically
     (opt-out contract).

Only meaningful for pipelines exposing set_ambient_scale (pax3d_render
and the routed pax_pbr adapter).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common


SKY = (0.2, 0.4, 0.9)
GROUND = (0.6, 0.24, 0.12)
AMB = 0.02          # tiny AmbientLight (harness gotcha: none => white flood)
KD = 0.96           # (1 - F) at n_dot_v = 1: F = F0 = 0.04, metallic 0
ROUGH = 0.3         # perceptual roughness (known spec for the sun check)
SUN = 0.6
SCALE = 0.25
F0 = 0.04


def sun_terms():
    """Shader BRDF at n=l=v=h (all dots exactly 1) — see test_glass."""
    f = F0 + (1.0 - F0) * 2.0 ** (-5.55473 - 6.98316)
    spec = f * 0.25 * (1.0 / (math.pi * ROUGH ** 4))
    diff = (1.0 - F0) / math.pi
    return diff + spec


def expected_rgb(curve, scale, sun=0.0):
    out = []
    direct = sun * sun_terms()
    for i in range(3):
        avg = (SKY[i] + GROUND[i]) * 0.5
        delta = (SKY[i] - GROUND[i]) * 0.5
        ambient = KD * (avg + (2.0 / 3.0) * delta) + AMB
        out.append(curve(direct + scale * ambient))
    return tuple(out)


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


def make_up_card(parent, half):
    cm = p3d.CardMaker('paxtest_ascale')
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    np.set_p(-90)                      # face up (+Z normal)
    np.set_two_sided(True)

    mat = p3d.Material('paxtest_ascale')
    mat.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat.set_roughness(ROUGH)
    mat.set_metallic(0.0)
    np.set_material(mat, 1)

    white = p3d.Texture('paxtest_white')
    white.setup_2d_texture(1, 1, p3d.Texture.T_unsigned_byte,
                           p3d.Texture.F_rgb8)
    white.set_clear_color(p3d.LColor(1, 1, 1, 1))
    np.set_texture(white, 1)
    mr_stage = p3d.TextureStage('paxtest_mr')
    mr_stage.set_mode(p3d.TextureStage.M_selector)
    np.set_texture(mr_stage, white, 1)
    return np


def check_rgb(h, name, got, want, tol=0.05, extra=''):
    err = max(abs(g - w) for g, w in zip(got, want))
    h.report.check(name, err < tol,
                   f'rgb=({got[0]:.3f},{got[1]:.3f},{got[2]:.3f}) expected '
                   f'({want[0]:.3f},{want[1]:.3f},{want[2]:.3f}), max err '
                   f'{err:.3f}{extra}')


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'ambient_scale')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_ambient_scale'):
        h.report.skip('pipeline has no set_ambient_scale (Session L)')
    if not hasattr(pipeline, 'set_hemisphere_ambient'):
        h.report.skip('pipeline has no set_hemisphere_ambient (R5.2)')
    base = h.base
    curve = common.CURVES['hejl_dawson']

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, 0, 1), (0, 0, 0))     # sun black: ambient only
    pipeline.set_hemisphere_ambient(SKY, GROUND)

    card = make_up_card(base.render, half=30)
    base.camera.set_pos(0, 0, 40)
    base.camera.set_hpr(0, -90, 0)     # straight down at the up-face
    cx, cy = h.win_w // 2, h.win_h // 2

    # --- 1. Root default 1.0 is an exact no-op --------------------------
    h.step(5)
    img_base = h.capture()
    h.save_capture(img_base, 'baseline')
    check_rgb(h, 'default_scale_noop', avg_rgb(img_base, cx, cy),
              expected_rgb(curve, 1.0),
              extra=' (untouched card, full hemisphere ambient)')

    # --- 2. Scaled subtree: indirect damped to k ------------------------
    pipeline.set_ambient_scale(card, SCALE)
    h.step(5)
    img_scaled = h.capture()
    h.save_capture(img_scaled, 'scaled')
    check_rgb(h, 'scaled_analytic', avg_rgb(img_scaled, cx, cy),
              expected_rgb(curve, SCALE),
              extra=f' (interior at scale {SCALE})')

    # --- 3. Scale survives a shader-recompile-class toggle --------------
    pipeline.set_shadow_filter_size(3)
    h.step(5)
    img_recompiled = h.capture()
    pipeline.set_shadow_filter_size(1)
    h.step(2)
    rms = common.image_rms_diff(img_scaled, img_recompiled, step=1)
    h.report.check('scale_survives_recompile', rms == 0.0,
                   f'shader recompile with per-node scale set: rms='
                   f'{rms:.2e} (root default + node input both preserved)')

    # --- 4. Direct light is NOT scaled ----------------------------------
    h.adapter.update_sun((0, 0, 1), (SUN, SUN, SUN))
    h.step(5)
    img_sun = h.capture()
    h.save_capture(img_sun, 'sun_shaft')
    check_rgb(h, 'direct_light_unscaled', avg_rgb(img_sun, cx, cy),
              expected_rgb(curve, SCALE, sun=SUN),
              extra=' (full sun + damped ambient — the sun-shaft case)')

    # --- 5. clear_ambient_scale restores the baseline exactly -----------
    h.adapter.update_sun((0, 0, 1), (0, 0, 0))
    pipeline.clear_ambient_scale(card)
    h.step(5)
    img_cleared = h.capture()
    rms = common.image_rms_diff(img_base, img_cleared, step=1)
    h.report.check('clear_restores_baseline', rms == 0.0,
                   f'clear_ambient_scale(): rms vs baseline = {rms:.2e} '
                   f'(byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
