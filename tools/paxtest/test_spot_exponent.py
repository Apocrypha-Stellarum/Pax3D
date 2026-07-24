"""paxtest: per-light spot penumbra (Session AF — flood lamps).

enable_spot_exponent compiles the SPOT_EXPONENT read of
p3d_LightSource[i].spotExponent (GL_SPOT_EXPONENT semantics:
pow(cos angle-to-axis, exponent) inside the cone). The flag is OFF by
default because Panda's Spotlight CLASS default exponent is 50
(measured, spotlight.I:19) — an unconditional read would silently
retighten every existing spot cone. This test pins the whole contract:

Scene (the test_local_lights recipe): flat card facing the camera, sun
black, tiny flat ambient, a Spotlight at distance DIST on the view
axis with attenuation (1,0,0) — at the card center l = v = n = h, so
the BRDF value is the test_glass analytic. The spot is AIMED ALPHA
degrees off-axis (look_at a laterally offset point): the center
sample's spotcos is exactly cos(ALPHA) while every BRDF dot stays 1 —
the exponent factor is the ONLY new term:

    lin = S * brdf * smoothstep_edge * cos(ALPHA)^e + AMB

Checks:
  1. flag_off_ignores_exponent — default pipeline, exponent 50 on the
     light: the analytic WITHOUT the pow term (the shipped behavior).
  2. toggle_on_exponent0_noop — set_enable_spot_exponent(True) (the
     runtime recompile path) + set_exponent(0): byte-identical to the
     flag-off capture (pow(x>0, 0) == 1 exactly).
  3. exponent_2_analytic / exponent_8_analytic — cos^2 / cos^8 exact.
  4. spotlight_default_50_documented — an untouched Spotlight under
     the flag reads cos^50 (the reason the flag defaults OFF).
  5. point_light_immune — a PointLight scene renders identically with
     the flag on vs off (rms 0 — the cutoff guard).
  6. toggle_off_restores — set_enable_spot_exponent(False):
     byte-identical to the first capture.

Runs in both sun modes (run.py adds @directional: the sun occupies
slot 0 and the loop must still guard non-spots). Only meaningful for
pax3d_render (the flag lives there).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

AMB = 0.02
ROUGH = 0.3
S = 0.6
DIST = 4.0
ALPHA = 20.0        # aim offset, degrees — spotcos at the center sample
F0 = 0.04
FOV = 60.0          # cone half-angle 30 deg: cos(20) well inside cutoff


def brdf_terms():
    """diff + spec at n=l=v=h (all dots exactly 1) — see test_glass."""
    f = F0 + (1.0 - F0) * 2.0 ** (-5.55473 - 6.98316)
    spec = f * 0.25 * (1.0 / (math.pi * ROUGH ** 4))
    diff = (1.0 - F0) / math.pi
    return diff + spec


def make_card(parent, half):
    cm = p3d.CardMaker('paxtest_se')
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    mat = p3d.Material('paxtest_se')
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

    h = common.Harness(args, 'spot_exponent')
    if args.pipeline != 'pax3d_render':
        h.report.skip('enable_spot_exponent lives in pax3d_render '
                      '(Session AF)')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline,
                                       'set_enable_spot_exponent'):
        h.report.skip('pipeline has no set_enable_spot_exponent '
                      '(Session AF)')
    base = h.base
    curve = common.CURVES['hejl_dawson']
    tag = args.sun_mode or 'uniforms'

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))    # sun black
    card = make_card(base.render, half=6)
    base.camera.set_pos(0, -30, 0)
    base.camera.set_hpr(0, 0, 0)
    cx, cy = h.win_w // 2, h.win_h // 2
    cos_a = math.cos(math.radians(ALPHA))

    spot = p3d.Spotlight('flood_lamp')
    spot.set_color(p3d.LColor(S, S, S, 1))
    spot.set_attenuation(p3d.LVecBase3(1, 0, 0))
    lens = p3d.PerspectiveLens()
    lens.set_fov(FOV)
    spot.set_lens(lens)
    spot_np = base.render.attach_new_node(spot)
    spot_np.set_pos(0, -DIST, 0)
    # Aim ALPHA degrees off the light->card-center axis: the center
    # sample keeps every BRDF dot at 1, only spotcos changes.
    spot_np.look_at(DIST * math.tan(math.radians(ALPHA)), 0, 0)
    card.set_light(spot_np)

    def expected(factor):
        return curve(S * brdf_terms() * factor + AMB)

    def measure():
        h.step(5)
        img = h.capture()
        return img, common.avg_lum(img, cx, cy)

    # --- 1. Flag off (default): exponent is ignored ----------------------
    spot.set_exponent(50.0)                        # the class default
    img_off, lum = measure()
    h.save_capture(img_off, f'{tag}_flag_off')
    want = expected(1.0)
    h.report.check('flag_off_ignores_exponent', abs(lum - want) < 0.04,
                   f'exponent 50, flag off: lum={lum:.3f}, analytic '
                   f'{want:.3f} (shipped behavior — no pow term)')

    # --- 2. Flag on + exponent 0: arithmetic no-op -----------------------
    pipeline.set_enable_spot_exponent(True)
    spot.set_exponent(0.0)
    h.step(5)
    rms = common.image_rms_diff(img_off, h.capture(), step=1)
    h.report.check('toggle_on_exponent0_noop', rms < 1e-6,
                   f'flag ON, exponent 0 vs flag OFF: rms = {rms:.2e} '
                   f'(pow(x>0, 0) == 1 exactly; runtime recompile path)')

    # --- 3. The penumbra analytics ---------------------------------------
    for e in (2.0, 8.0):
        spot.set_exponent(e)
        _img, lum = measure()
        want = expected(cos_a ** e)
        h.report.check(f'exponent_{int(e)}_analytic',
                       abs(lum - want) < 0.04,
                       f'exponent {e:.0f}: lum={lum:.3f}, analytic '
                       f'{want:.3f} (= base * cos({ALPHA:.0f}deg)^'
                       f'{e:.0f})')

    # --- 4. The class-default trap, documented ---------------------------
    spot.set_exponent(50.0)
    _img, lum = measure()
    want = expected(cos_a ** 50.0)
    h.report.check('spotlight_default_50_documented',
                   abs(lum - want) < 0.04,
                   f'exponent 50 (Panda Spotlight default): lum={lum:.3f}, '
                   f'analytic {want:.3f} — why the flag defaults OFF')

    # --- 5. Point lights are immune --------------------------------------
    card.set_light_off(spot_np)
    spot_np.detach_node()
    lamp = p3d.PointLight('control_lamp')
    lamp.set_color(p3d.LColor(S, S, S, 1))
    lamp.set_attenuation(p3d.LVecBase3(1, 0, 0))
    lamp_np = base.render.attach_new_node(lamp)
    lamp_np.set_pos(0, -DIST, 0)
    card.set_light(lamp_np)
    h.step(5)
    img_point_on = h.capture()
    pipeline.set_enable_spot_exponent(False)
    h.step(5)
    img_point_off = h.capture()
    rms = common.image_rms_diff(img_point_on, img_point_off, step=1)
    h.report.check('point_light_immune', rms < 1e-6,
                   f'PointLight scene, flag on vs off: rms = {rms:.2e} '
                   f'(the cutoff guard never touches non-spots)')

    # --- 6. Toggle-off restores ------------------------------------------
    card.set_light_off(lamp_np)
    lamp_np.remove_node()
    spot_np.reparent_to(base.render)
    card.set_light(spot_np)
    h.step(5)
    rms = common.image_rms_diff(img_off, h.capture(), step=1)
    h.report.check('toggle_off_restores', rms < 1e-6,
                   f'flag off again (exponent 50 live on the light): '
                   f'rms vs the first capture = {rms:.2e}')

    h.report.finish()


if __name__ == '__main__':
    main()
