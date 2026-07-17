"""paxtest: double-sided lighting via gl_FrontFacing (Session K).

The PBR shader historically shaded backfaces with the FRONT face's
normal, so two-sided geometry seen from behind (glTF `doubleSided`
materials: thin panels, decals, seat fabric, interior walls) lit from
the wrong side — near-black under direct sun. `double_sided_lighting`
(init kwarg / `set_double_sided_lighting()`, recompile-class) compiles
in the Khronos sample-viewer semantic: `if (!gl_FrontFacing) n = -n`.

Scene: an opaque white two-sided card, sun exactly on the view axis
(every BRDF dot product 1 on the face toward the camera), analytics as
in test_glass:

  lit  = S*(diff + spec) + amb          (facing normal toward camera)
  dark = amb                            (unflipped backface: n_dot_l = 0)

Checks:
  1. Front face matches the lit analytic (anchor; both flag states).
  2. Default backface renders ambient-only — the defect, measured.
  3. With the flag on, the backface matches the lit analytic and the
     front-face luminance.
  4. Front faces are BIT-identical with the flag on vs off (the flip is
     a not-front-facing branch; single-sided content cannot change).
  5. Toggling off restores the default backface capture byte-identically
     (opt-out contract; exercises the recompile path both ways).

Runs in both sun modes (run.py adds @directional): 'uniforms' flips
`world_normal` in the world-space sun block, 'directional' flips the
view-space `n` consumed by the p3d_LightSource loop.

Only meaningful for pipelines exposing set_double_sided_lighting
(pax3d_render and the routed pax_pbr adapter).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common


ROUGH = 0.3         # perceptual roughness
SUN = 0.6           # sun intensity
AMB = 0.02          # tiny AmbientLight (harness gotcha: none => white flood)
F0 = 0.04


def analytic_lit(curve):
    """Shader BRDF at n=l=v=h (all dots exactly 1) — see test_glass."""
    f = F0 + (1.0 - F0) * 2.0 ** (-5.55473 - 6.98316)
    spec = f * 0.25 * (1.0 / (math.pi * ROUGH ** 4))
    diff = (1.0 - F0) / math.pi
    # ambient adds (diffuse_color + spec_color) * AMB = 1.0 * AMB
    return curve(SUN * (diff + spec) + AMB)


def analytic_dark(curve):
    """Unflipped backface: n_dot_l clamps to 0, ambient has no direction."""
    return curve(AMB)


def make_two_sided_card(parent, half):
    cm = p3d.CardMaker('paxtest_ds')
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    np.set_two_sided(True)

    mat = p3d.Material('paxtest_ds')
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


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default=None,
                        choices=['uniforms', 'directional'])
    args = parser.parse_args()

    h = common.Harness(args, 'doublesided')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_double_sided_lighting'):
        h.report.skip('pipeline has no set_double_sided_lighting (Session K)')
    base = h.base
    curve = common.CURVES['hejl_dawson']
    tag = args.sun_mode or 'uniforms'

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (SUN, SUN, SUN))

    card = make_two_sided_card(base.render, half=6)
    base.camera.set_pos(0, -30, 0)
    base.camera.set_hpr(0, 0, 0)
    cx, cy = h.win_w // 2, h.win_h // 2
    want_lit = analytic_lit(curve)
    want_dark = analytic_dark(curve)

    # --- 1. Anchor: front face, flag off --------------------------------
    h.step(5)
    img_front_off = h.capture()
    h.save_capture(img_front_off, f'{tag}_front_off')
    lum_front_off = common.avg_lum(img_front_off, cx, cy)
    h.report.check('front_analytic', abs(lum_front_off - want_lit) < 0.04,
                   f'front face lum={lum_front_off:.3f}, analytic '
                   f'{want_lit:.3f}')

    # --- 2. Default backface: lit from the wrong side -------------------
    card.set_h(180)                    # show the camera its BACK face
    h.step(5)
    img_back_off = h.capture()
    h.save_capture(img_back_off, f'{tag}_back_off')
    lum_back_off = common.avg_lum(img_back_off, cx, cy)
    h.report.check('default_backface_dark',
                   abs(lum_back_off - want_dark) < 0.04,
                   f'backface lum={lum_back_off:.3f}, ambient-only analytic '
                   f'{want_dark:.3f} — the defect, measured')

    # --- 3. Flag on: backface lights like a front face ------------------
    pipeline.set_double_sided_lighting(True)
    h.step(5)
    img_back_on = h.capture()
    h.save_capture(img_back_on, f'{tag}_back_on')
    lum_back_on = common.avg_lum(img_back_on, cx, cy)
    h.report.check('flip_lights_backface',
                   abs(lum_back_on - want_lit) < 0.04,
                   f'flipped backface lum={lum_back_on:.3f}, analytic '
                   f'{want_lit:.3f}')
    h.report.check('backface_matches_front',
                   abs(lum_back_on - lum_front_off) < 0.01,
                   f'backface {lum_back_on:.3f} vs front '
                   f'{lum_front_off:.3f} (same surface, same light)')

    # --- 4. Front faces are bit-identical under the flag ----------------
    card.set_h(0)
    h.step(5)
    img_front_on = h.capture()
    rms = common.image_rms_diff(img_front_off, img_front_on, step=1)
    h.report.check('front_unchanged_by_flag', rms == 0.0,
                   f'front face, flag on vs off: rms={rms:.2e} '
                   f'(the flip is a !gl_FrontFacing branch)')

    # --- 5. Toggle off restores the default backface exactly ------------
    pipeline.set_double_sided_lighting(False)
    card.set_h(180)
    h.step(5)
    img_back_restored = h.capture()
    rms = common.image_rms_diff(img_back_off, img_back_restored, step=1)
    h.report.check('optout_restores_default', rms == 0.0,
                   f'set_double_sided_lighting(False): rms vs default '
                   f'backface = {rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
