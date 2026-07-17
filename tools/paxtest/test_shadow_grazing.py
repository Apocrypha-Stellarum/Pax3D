"""paxtest: grazing-angle shadow acne + slope-scaled bias (Session I, R2.5).

The openworld build's signature P0: at low western sun, open ground develops
fine terracing/acne bands and cast shadows lose contrast / "vanish". Root
cause (measured, not asserted): at a grazing sun angle one shadow-map texel
spans a large receiver depth, so a CONSTANT depth bias sized for normal
incidence self-shadows the open ground into acne. Error grows ~1/tan(alt) --
exactly the openworld report.

This test emulates the mechanism deterministically. A horizontal ground card
under a LOW sun grazes purely by altitude (NdotL = sin(alt), tan(theta) =
cot(alt)); no sloped terrain asset needed. It measures the PURE shadow term
via debug mode 11 (decoupled from the dim grazing lighting -- the trap that
produced false luminance verdicts in Session H), as a black-fraction:

  * OPEN ground (no caster): fraction shadowed = the acne fraction.
  * UMBRA under a real caster: fraction shadowed = the real shadow's health.

Acceptance (the fix is opt-in; 0 = byte-identical constant-bias path):
  1. normal_bias = 0     -> open-ground acne PRESENT, real umbra present.
  2. normal_bias = REC   -> acne CLEARED, real umbra RETAINED (no peter-pan).
  3. normal_bias = HUGE  -> real umbra ERODES (proves the umbra check has
                            teeth: a too-large normal bias lifts real
                            shadows off, and this test catches it).

Slope-scaled bias adds bias only where the receiver grazes, so it clears the
open-ground acne without touching the real (large depth-gap) shadow. On this
flat scene a constant bias in the same window also works; the discriminator --
varied terrain where no constant bias threads acne vs real shadow -- is the
openworld probe (probe_openworld_scale.py), not this mechanism gate.

Only meaningful for pipelines with a directional sun mode (pax3d_render).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


ALT = 12.0                          # sun altitude (deg): flat ground grazes
ELEV = math.radians(ALT)
SUN = (math.cos(ELEV), 0.0, math.sin(ELEV))   # toward sun, from +x
COT = math.cos(ELEV) / math.sin(ELEV)         # 4.70: shadow runs -x
CASTER_H = 1.0                      # caster height above ground
CASTER_HALF = 2.0                   # 4x4 card
UMBRA_X = -CASTER_H * COT           # umbra center on the ground (x)

MAP = 512                           # coarse texel -> clear, robust acne
EXTENT, DEPTH = 60.0, 600.0
TEXEL_WORLD = 2 * EXTENT / MAP      # 0.234
CONST_BIAS = 0.05                   # world; fine at normal incidence
# N ~ 0.5-1.0 x texel_world clears acne at any angle (the tan cancels).
REC_BIAS = 0.15                     # world; ~0.64 x texel
HUGE_BIAS = 1.5                     # world; slope term > umbra gap -> erodes


def make_flat_card(parent, half, name, z=0.0, rgb=(0.8, 0.8, 0.8)):
    cm = p3d.CardMaker(name)
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    np.set_p(-90)                   # XZ card -> XY plane, faces +z
    np.set_z(z)
    np.set_two_sided(True)
    scenes.apply_flat_pbr_surface(np, rgb=rgb)
    return np


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'shadow_grazing')
    if not getattr(h.adapter, 'supports_sun_modes', False):
        h.report.skip('pipeline has no directional sun mode')

    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode='directional', shadows=True,
                    extra_pipeline_kwargs={'shadow_map_size': MAP})
    pipeline = h.adapter.pipeline
    if not hasattr(pipeline, 'set_shadow_normal_bias'):
        h.report.skip('pipeline has no set_shadow_normal_bias (slope bias)')
    base = h.base
    pipeline.set_shadow_bias(CONST_BIAS, world_units=True)
    pipeline.set_shadow_extent(EXTENT, DEPTH)

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(0.02, 0.02, 0.02, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    make_flat_card(base.render, 200, 'ground', z=0.0)
    make_flat_card(base.render, CASTER_HALF, 'caster', z=CASTER_H,
                   rgb=(0.9, 0.15, 0.15))

    # Top-down camera. set_ortho() clips at view-distance +-50, so keep the
    # ground (z=0) within 50 of the camera.
    base.camera.set_pos(0, 0, 40)
    base.camera.set_hpr(0, -90, 0)
    film_h = 80.0
    h.set_ortho(film_h=film_h)
    scale = h.win_h / film_h

    def to_px(x, y):
        return (h.win_w // 2 + int(round(x * scale)),
                h.win_h // 2 - int(round(y * scale)))

    def shadow_fraction(img, x0, y0, x1, y1, thr=0.5):
        """Fraction of mode-11 pixels in world-rect [x0,x1]x[y0,y1] that are
        shadowed (gray < thr). Open ground -> acne fraction; umbra -> health."""
        px0, py0 = to_px(x0, y1)
        px1, py1 = to_px(x1, y0)
        n = shad = 0
        for py in range(min(py0, py1), max(py0, py1) + 1):
            for px in range(min(px0, px1), max(px0, px1) + 1):
                if common.lum_at(img, px, py) < thr:
                    shad += 1
                n += 1
        return shad / max(n, 1)

    def measure(tag):
        pipeline.set_debug_lighting(11)
        h.step(5)
        img = h.capture()
        h.save_capture(img, tag)
        pipeline.set_debug_lighting(0)
        # open ground: sun side of the caster, clear of its umbra & footprint
        acne = shadow_fraction(img, 6.0, -10.0, 26.0, 10.0)
        # umbra: caster shadow lands at x = -CASTER_H*cot(alt)
        umbra = shadow_fraction(img, UMBRA_X - 1.5, -1.5, UMBRA_X + 1.5, 1.5)
        return acne, umbra

    h.adapter.update_sun(SUN, (3, 3, 3))

    # --- 1. Before: constant bias only (normal_bias = 0) ----------------
    pipeline.set_shadow_normal_bias(0.0)
    acne0, umbra0 = measure('normal_bias_off')
    h.report.check('grazing_acne_present', acne0 > 0.04,
                   f'open-ground acne fraction={acne0:.3f} at sun alt '
                   f'{ALT:.0f} deg (tan(theta)={COT:.2f}), constant bias '
                   f'{CONST_BIAS} world / texel {TEXEL_WORLD:.3f} -- the '
                   f'grazing self-shadow defect reproduces')
    h.report.check('real_umbra_present', umbra0 > 0.9,
                   f'caster umbra fraction={umbra0:.3f} (a real shadow '
                   f'exists to protect; gap={CASTER_H/math.sin(ELEV):.1f} '
                   f'world units)')

    # --- 2. Fix: recommended slope-scaled bias --------------------------
    pipeline.set_shadow_normal_bias(REC_BIAS)
    acne1, umbra1 = measure('normal_bias_rec')
    h.report.check('grazing_acne_cleared', acne1 < 0.01,
                   f'open-ground acne fraction {acne0:.3f} -> {acne1:.3f} '
                   f'with set_shadow_normal_bias({REC_BIAS}) -- slope term '
                   f'{REC_BIAS*COT:.2f} > acne offset '
                   f'{0.5*TEXEL_WORLD*COT:.2f}')
    h.report.check('real_umbra_retained', umbra1 > 0.9,
                   f'caster umbra fraction {umbra0:.3f} -> {umbra1:.3f}: the '
                   f'real shadow survives (slope term {REC_BIAS*COT:.2f} << '
                   f'gap {CASTER_H/math.sin(ELEV):.1f}) -- no peter-panning')

    # --- 3. Teeth: a too-large normal bias must erode the real shadow ---
    # Proves 'real_umbra_retained' is a meaningful constraint: without this,
    # an absurd normal bias could pass check 2 unnoticed.
    pipeline.set_shadow_normal_bias(HUGE_BIAS)
    acne2, umbra2 = measure('normal_bias_huge')
    h.report.check('over_bias_erodes_shadow', umbra2 < 0.5,
                   f'caster umbra fraction {umbra1:.3f} -> {umbra2:.3f} at '
                   f'set_shadow_normal_bias({HUGE_BIAS}) (slope term '
                   f'{HUGE_BIAS*COT:.2f} > gap '
                   f'{CASTER_H/math.sin(ELEV):.1f}) -- the umbra check has '
                   f'teeth: over-biasing lifts real shadows and is caught')

    # --- 4. Off again: opt-out is byte-identical to before --------------
    pipeline.set_shadow_normal_bias(0.0)
    acne3, umbra3 = measure('normal_bias_off_again')
    h.report.check('opt_out_restores',
                   abs(acne3 - acne0) < 1e-6 and abs(umbra3 - umbra0) < 1e-6,
                   f'normal_bias 0 reproduces the before state exactly '
                   f'(acne {acne0:.3f}->{acne3:.3f}, umbra '
                   f'{umbra0:.3f}->{umbra3:.3f})')

    h.report.finish()


if __name__ == '__main__':
    main()
