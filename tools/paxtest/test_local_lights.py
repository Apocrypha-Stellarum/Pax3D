"""paxtest: local point/spot lights (Session O — ship interior lighting).

The p3d_LightSource loop (point + spot lights) is the pipeline's ONLY
never-measured lighting path — inherited from simplepbr as the "correct
path", used by nothing until ship interiors needed lamps. This gives it
the same analytic treatment as the sun paths, and measures the exact
ship-interior recipe (Session L ambient scale + a cabin lamp).

Scene: flat card facing the camera (test_glass geometry), sun BLACK, a
PointLight/Spotlight ON the view axis between camera and card — at the
card center the light/view/normal/half vectors all coincide, so the
BRDF terms are the same analytic values as test_glass:

  lin = att * S * (diff + spec) + ambient_terms
  att = 1 / (c + l*d + q*d*d)         (shader's attenuation form)

Checks:
  1. PointLight, attenuation (1,0,0): exact analytic at the center.
  2. Quadratic attenuation (1,0,q) at distance d: exact 1/(1+q*d^2)
     falloff — the knob cabin lights live and die by. (Panda's default
     attenuation is (1,0,0) = NO falloff; docstring warns.)
  3. Scoping: a second card WITHOUT set_light stays ambient-only —
     per-room lighting works, and light cost is per-subtree.
  4. Spotlight: exact analytic inside the cone; a sample outside the
     cone half-angle reads ambient-only (the smoothstep cutoff).
  5. The ship-interior recipe: hemisphere sky ambient + ambient scale
     0.1 + the lamp — lamp term at FULL strength, ambient damped to
     0.1 (direct light is not indirect; measured composition).

Runs in both sun modes (run.py adds @directional): the loop must
behave with the sun occupying light slot 0 (directional mode) and
with the slot-skipping uniforms mode.

Only meaningful for pax_pbr-family pipelines (update_sun + material
conventions); skips otherwise.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common


AMB = 0.02          # tiny AmbientLight (harness gotcha: none => white flood)
ROUGH = 0.3
S = 0.6             # lamp intensity (linear HDR)
DIST = 4.0          # lamp distance from the card
QUAD = 0.25         # quadratic attenuation coefficient
SKY = (0.2, 0.4, 0.9)
GROUND = (0.6, 0.24, 0.12)
KD = 0.96
SCALE = 0.1         # interior ambient scale (the ship recipe)
F0 = 0.04


def brdf_terms():
    """diff + spec at n=l=v=h (all dots exactly 1) — see test_glass."""
    f = F0 + (1.0 - F0) * 2.0 ** (-5.55473 - 6.98316)
    spec = f * 0.25 * (1.0 / (math.pi * ROUGH ** 4))
    diff = (1.0 - F0) / math.pi
    return diff + spec


def expected(curve, att=1.0, ambient=AMB):
    return curve(att * S * brdf_terms() + ambient)


def hemi_ambient(ch):
    """Hemisphere-SH irradiance for THIS card's HORIZONTAL normal
    (faces the camera, nz = 0): the sky/ground delta term vanishes,
    leaving KD * avg per channel."""
    avg = (SKY[ch] + GROUND[ch]) * 0.5
    return KD * avg


def make_card(parent, half, name='paxtest_ll'):
    cm = p3d.CardMaker(name)
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    mat = p3d.Material(name)
    mat.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat.set_roughness(ROUGH)
    mat.set_metallic(0.0)
    np.set_material(mat, 1)
    white = p3d.Texture('paxtest_white')
    white.setup_2d_texture(1, 1, p3d.Texture.T_unsigned_byte,
                           p3d.Texture.F_rgb8)
    white.set_clear_color(p3d.LColor(1, 1, 1, 1))
    np.set_texture(white, 1)
    mr = p3d.TextureStage('paxtest_mr')
    mr.set_mode(p3d.TextureStage.M_selector)
    np.set_texture(mr, white, 1)
    return np


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default=None,
                        choices=['uniforms', 'directional'])
    args = parser.parse_args()

    h = common.Harness(args, 'local_lights')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'update_sun'):
        h.report.skip('needs a pax_pbr-family pipeline')
    base = h.base
    curve = common.CURVES['hejl_dawson']
    tag = args.sun_mode or 'uniforms'

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))    # sun BLACK: lamps only

    card = make_card(base.render, half=6)
    base.camera.set_pos(0, -30, 0)
    base.camera.set_hpr(0, 0, 0)
    cx, cy = h.win_w // 2, h.win_h // 2

    # --- 1. PointLight, no attenuation: exact analytic ------------------
    lamp = p3d.PointLight('cabin_lamp')
    lamp.set_color(p3d.LColor(S, S, S, 1))
    lamp.set_attenuation(p3d.LVecBase3(1, 0, 0))
    lamp_np = base.render.attach_new_node(lamp)
    lamp_np.set_pos(0, -DIST, 0)                   # on-axis, in front
    card.set_light(lamp_np)
    h.step(5)
    img = h.capture()
    h.save_capture(img, f'{tag}_point')
    lum = common.avg_lum(img, cx, cy)
    want = expected(curve, att=1.0)
    h.report.check('point_light_analytic', abs(lum - want) < 0.04,
                   f'PointLight on-axis, att (1,0,0): lum={lum:.3f}, '
                   f'analytic {want:.3f}')

    # --- 2. Quadratic attenuation: exact 1/(1+q d^2) --------------------
    lamp.set_attenuation(p3d.LVecBase3(1, 0, QUAD))
    h.step(5)
    lum = common.avg_lum(h.capture(), cx, cy)
    att = 1.0 / (1.0 + QUAD * DIST * DIST)
    want = expected(curve, att=att)
    h.report.check('quadratic_attenuation', abs(lum - want) < 0.04,
                   f'att (1,0,{QUAD}) at d={DIST}: lum={lum:.3f}, '
                   f'analytic {want:.3f} (falloff x{att:.3f})')

    # --- 3. Scoping: an unlit sibling card stays ambient-only -----------
    card.hide()
    other = make_card(base.render, half=6, name='paxtest_unlit')
    h.step(5)
    lum = common.avg_lum(h.capture(), cx, cy)
    want = curve(AMB)
    h.report.check('light_scoping', abs(lum - want) < 0.04,
                   f'card WITHOUT set_light: lum={lum:.3f}, ambient-only '
                   f'{want:.3f} (per-room scoping works)')
    other.remove_node()
    card.show()

    # --- 4. Spotlight: analytic in-cone, dark outside the cone ----------
    card.set_light_off(lamp_np)
    spot = p3d.Spotlight('cone_lamp')
    spot.set_color(p3d.LColor(S, S, S, 1))
    spot.set_attenuation(p3d.LVecBase3(1, 0, 0))
    lens = p3d.PerspectiveLens()
    lens.set_fov(40)                               # half-angle 20 deg
    spot.set_lens(lens)
    spot_np = base.render.attach_new_node(spot)
    spot_np.set_pos(0, -DIST, 0)
    spot_np.look_at(0, 0, 0)                       # aimed at card center
    card.set_light(spot_np)
    h.step(5)
    img = h.capture()
    h.save_capture(img, f'{tag}_spot')
    lum_in = common.avg_lum(img, cx, cy)
    want_in = expected(curve, att=1.0)
    h.report.check('spot_in_cone_analytic', abs(lum_in - want_in) < 0.04,
                   f'in-cone center: lum={lum_in:.3f}, analytic '
                   f'{want_in:.3f}')
    # card corner at (5,0,0): 51 deg off the spot axis, well outside 20
    px = cx + int(5.0 / (30 * math.tan(math.radians(
        base.camLens.get_hfov() / 2))) * (h.win_w // 2))
    lum_out = common.avg_lum(img, px, cy)
    want_out = curve(AMB)
    h.report.check('spot_outside_cone_dark',
                   abs(lum_out - want_out) < 0.04,
                   f'51 deg off-axis: lum={lum_out:.3f}, ambient-only '
                   f'{want_out:.3f} (cone cutoff)')
    card.set_light_off(spot_np)
    spot_np.remove_node()

    # --- 5. The ship-interior recipe: damped sky ambient + full lamp ----
    if hasattr(pipeline, 'set_ambient_scale') and hasattr(
            pipeline, 'set_hemisphere_ambient'):
        pipeline.set_hemisphere_ambient(SKY, GROUND)
        pipeline.set_ambient_scale(card, SCALE)
        card.set_light(lamp_np)                    # quadratic att still set
        h.step(5)
        img = h.capture()
        h.save_capture(img, f'{tag}_interior_recipe')
        got = [0.0, 0.0, 0.0]
        n = 0
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                c = img.get_xel(cx + dx, cy + dy)
                got = [g + c[i] for i, g in enumerate(got)]
                n += 1
        got = [g / n for g in got]
        lamp_lin = att * S * brdf_terms()
        want_rgb = [curve(lamp_lin + SCALE * (hemi_ambient(i) + AMB))
                    for i in range(3)]
        err = max(abs(g - w) for g, w in zip(got, want_rgb))
        h.report.check('interior_recipe_composes', err < 0.04,
                       f'lamp + hemisphere ambient x{SCALE}: rgb='
                       f'({got[0]:.3f},{got[1]:.3f},{got[2]:.3f}) expected '
                       f'({want_rgb[0]:.3f},{want_rgb[1]:.3f},'
                       f'{want_rgb[2]:.3f}), max err {err:.3f} '
                       f'(lamp full strength, sky damped)')
        pipeline.clear_ambient_sh()
        pipeline.clear_ambient_scale(card)
    else:
        h.report.info('interior_recipe_composes',
                      'pipeline lacks ambient_scale/hemisphere APIs')

    h.report.finish()


if __name__ == '__main__':
    main()
