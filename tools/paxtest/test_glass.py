"""paxtest: specular-preserving glass transparency (Session K).

The standard M_alpha path multiplies the ENTIRE shaded result by alpha at
the blend stage — a canopy at alpha 0.15 keeps only 15% of the specular
highlight that makes glass read as glass. `pipeline.set_glass(np)` switches
the node to a GLASS-defined compile of the same PBR shader plus
M_premultiplied_alpha: alpha attenuates only the transmission-class terms
(diffuse, ambient), while specular and emission add at full strength.

Scene: a flat white card facing the camera, sun exactly along the view
axis (n = l = v = h, every BRDF dot product = 1), so both paths are
analytically computable to the pixel:

  spec  = F(1) * V(1) * D(1)   (Schlick-SG, Smith-GGX, GGX — see shader)
  diff  = base * (1 - F0) / pi
  legacy_linear = a * (S*(diff+spec) + amb*(diff_color+F0))
  glass_linear  = a * (S*diff + amb*diff_color) + S*spec + amb*F0

Checks:
  1. Legacy M_alpha matches legacy_linear through the tonemap curve —
     the defect, measured (specular scaled by alpha).
  2. set_glass() matches glass_linear — specular survives alpha.
  3. Glass is decisively brighter at the highlight than legacy (the
     defect statement, independent of curve tolerances).
  4. A known-value emissive background behind the glass transmits at
     exactly (1 - a) — premultiplied blending composes correctly.
  5. The glass look survives a shader-recompile-class toggle (the §3
     input-preservation invariant extended to per-node glass variants).
  6. set_glass(np, False) restores the M_alpha capture byte-identically
     (opt-out contract).

Runs in both sun modes (run.py adds @directional): 'uniforms' exercises
the world-space sun block's GLASS split, 'directional' the p3d_LightSource
loop's. The expected numbers are identical by R2's established fact.

Only meaningful for pipelines exposing set_glass (pax3d_render and the
routed pax_pbr adapter).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


ALPHA = 0.15        # canopy-class base-color alpha
ROUGH = 0.3         # perceptual roughness (broad, off-axis-tolerant lobe)
SUN = 0.6           # sun intensity (keeps both paths mid-curve)
AMB = 0.02          # tiny AmbientLight (harness gotcha: none => white flood)
BG = 0.35           # emissive background linear value (transmission check)
F0 = 0.04


def analytic_terms():
    """Mirror the shader's BRDF at n=l=v=h (all dots exactly 1)."""
    # specular_reflection: Schlick with Spherical-Gaussian exponent
    f = F0 + (1.0 - F0) * 2.0 ** (-5.55473 - 6.98316)
    # visibility_occlusion: ggxv = ggxl = 1 -> 0.5 / 2
    v = 0.25
    # microfacet_distribution: alpha_roughness = rough^2, roughness2 =
    # alpha_roughness^2, f_term = roughness2 -> D = 1/(pi * rough^4)
    d = 1.0 / (math.pi * ROUGH ** 4)
    spec = f * v * d
    diff_color = 1.0 * (1.0 - F0)          # white base, metallic 0
    diff = diff_color / math.pi
    return spec, diff, diff_color


def expected_legacy(curve):
    spec, diff, diff_color = analytic_terms()
    lit = SUN * (diff + spec) + AMB * (diff_color + F0)
    return curve(ALPHA * lit)


def expected_glass(curve, background=0.0):
    spec, diff, diff_color = analytic_terms()
    transmission = ALPHA * (SUN * diff + AMB * diff_color)
    reflection = SUN * spec + AMB * F0
    return curve(transmission + reflection + background * (1.0 - ALPHA))


def make_glass_card(parent, half):
    """White card with material alpha + explicit white metal-rough texture
    (the selector stage), so the shader's roughness/metallic multipliers
    are exactly the material values — no reliance on unbound-sampler
    defaults."""
    cm = p3d.CardMaker('paxtest_glass')
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())

    mat = p3d.Material('paxtest_glass')
    mat.set_base_color(p3d.LColor(1, 1, 1, ALPHA))
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


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default=None,
                        choices=['uniforms', 'directional'])
    args = parser.parse_args()

    h = common.Harness(args, 'glass')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_glass'):
        h.report.skip('pipeline has no set_glass (Session K)')
    base = h.base
    curve = common.CURVES['hejl_dawson']
    tag = args.sun_mode or 'uniforms'

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (SUN, SUN, SUN))

    card = make_glass_card(base.render, half=6)
    base.camera.set_pos(0, -30, 0)
    base.camera.set_hpr(0, 0, 0)       # looking +Y, straight at the card
    cx, cy = h.win_w // 2, h.win_h // 2

    # --- 1. Legacy M_alpha: the whole result fades with alpha -----------
    card.set_transparency(p3d.TransparencyAttrib.M_alpha)
    h.step(5)
    img_legacy = h.capture()
    h.save_capture(img_legacy, f'{tag}_legacy')
    lum_legacy = common.avg_lum(img_legacy, cx, cy)
    want_legacy = expected_legacy(curve)
    h.report.check('legacy_alpha_fades_spec',
                   abs(lum_legacy - want_legacy) < 0.04,
                   f'M_alpha highlight lum={lum_legacy:.3f}, analytic '
                   f'(spec*alpha) {want_legacy:.3f} — the defect, measured')

    # --- 2. set_glass: specular survives alpha --------------------------
    pipeline.set_glass(card)
    h.step(5)
    img_glass = h.capture()
    h.save_capture(img_glass, f'{tag}_glass')
    lum_glass = common.avg_lum(img_glass, cx, cy)
    want_glass = expected_glass(curve)
    h.report.check('glass_spec_preserved',
                   abs(lum_glass - want_glass) < 0.04,
                   f'glass highlight lum={lum_glass:.3f}, analytic '
                   f'(spec unattenuated) {want_glass:.3f}')
    h.report.check('glass_vs_legacy_ratio',
                   lum_glass > lum_legacy * 1.5,
                   f'highlight {lum_legacy:.3f} -> {lum_glass:.3f} '
                   f'({lum_glass / max(lum_legacy, 1e-6):.2f}x)')

    # --- 3. Transmission: background composes at exactly (1 - a) --------
    bg_quad = scenes.make_emissive_quad(base.render, h.use_330,
                                        value=BG, half_size=12)
    bg_quad.set_y(10)                  # behind the glass card
    h.step(5)
    img_bg = h.capture()
    h.save_capture(img_bg, f'{tag}_background')
    lum_bg = common.avg_lum(img_bg, cx, cy)
    want_bg = expected_glass(curve, background=BG)
    h.report.check('glass_transmits_background',
                   abs(lum_bg - want_bg) < 0.04,
                   f'glass over emissive {BG}: lum={lum_bg:.3f}, analytic '
                   f'{want_bg:.3f} (bg * (1-a) + glass)')
    bg_quad.hide()

    # --- 4. Glass variant survives a shader-recompile-class toggle ------
    pipeline.set_shadow_filter_size(3)
    h.step(5)
    img_recompiled = h.capture()
    pipeline.set_shadow_filter_size(1)
    h.step(2)
    rms = common.image_rms_diff(img_glass, img_recompiled, step=1)
    h.report.check('glass_survives_recompile', rms == 0.0,
                   f'shader recompile with glass applied: rms={rms:.2e} '
                   f'(variant re-pushed by _reapply_glass_shaders)')

    # --- 5. Opt-out restores the legacy capture byte-identically --------
    pipeline.set_glass(card, False)
    h.step(5)
    img_off = h.capture()
    h.save_capture(img_off, f'{tag}_optout')
    rms = common.image_rms_diff(img_legacy, img_off, step=1)
    h.report.check('optout_restores_legacy', rms == 0.0,
                   f'set_glass(np, False): rms vs M_alpha baseline = '
                   f'{rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
