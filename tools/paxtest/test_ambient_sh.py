"""paxtest: environment-driven ambient via irradiance SH (Session J, R5.2).

Feeds the shader's ALREADY-EXISTING sh_coeffs diffuse-IBL path (shipped
zeroed since R1) through the new pipeline APIs:

  * set_hemisphere_ambient(sky, ground) — exact SH bands 0-1 for a
    two-tone sky/ground-bounce environment (the planetside ambient),
  * set_ambient_sh(coeffs) — raw 9-coefficient API,
  * clear_ambient_sh() — back to zeros,
  * sh_from_cubemap(tex) — EXPERIMENTAL cubemap projection (math checked
    here against the analytic hemisphere, no rendering involved).

Checks:
  1. Baseline (zero SH) — the shipped look.
  2. Hemisphere ambient: an up-facing white card matches the analytic
     base * kd * (avg + 2/3*delta) per channel through the tonemap curve;
     a down-facing card matches (avg - 2/3*delta); sky/ground tints
     dominate the correct faces.
  3. The coefficients survive a shader-recompile-class toggle (the §3
     input-preservation invariant, extended to _set_env_map_uniforms).
  4. clear_ambient_sh() restores the baseline capture exactly.
  5. sh_from_cubemap of a synthetic L = avg + delta*dir_z cubemap
     reproduces the analytic hemisphere coefficients (bands 0-1) with
     near-zero band 2.

Only meaningful for pipelines exposing set_hemisphere_ambient
(pax3d_render).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


SKY = (0.2, 0.4, 0.9)
GROUND = (0.6, 0.24, 0.12)
AMB = 0.02          # tiny AmbientLight (harness gotcha: none => white flood)
KD = 0.96           # (1 - F) at n_dot_v = 1: F = F0 = 0.04, metallic 0


def make_h_card(parent, half, name, z, face_up=True):
    cm = p3d.CardMaker(name)
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    np.set_p(-90 if face_up else 90)
    np.set_z(z)
    np.set_two_sided(True)
    scenes.apply_flat_pbr_surface(np, rgb=(1, 1, 1))
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


def expected_rgb(curve, nz):
    """Analytic screen color of the white card with hemisphere ambient:
    kd * (avg + 2/3 * delta * nz) + ambient-light term, per channel."""
    out = []
    for i in range(3):
        avg = (SKY[i] + GROUND[i]) * 0.5
        delta = (SKY[i] - GROUND[i]) * 0.5
        lin = KD * (avg + (2.0 / 3.0) * delta * nz) + AMB
        out.append(curve(lin))
    return tuple(out)


# GL cube-map face table — deliberately DUPLICATED from
# pax3d_render.pipeline.sh_from_cubemap so an accidental edit there breaks
# this test instead of silently agreeing with itself.
def face_dir(face, a, b):
    if face == 0:
        return (1.0, -b, -a)
    if face == 1:
        return (-1.0, -b, a)
    if face == 2:
        return (a, 1.0, b)
    if face == 3:
        return (a, -1.0, -b)
    if face == 4:
        return (a, -b, 1.0)
    return (-a, -b, -1.0)


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'ambient_sh')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_hemisphere_ambient'):
        h.report.skip('pipeline has no set_hemisphere_ambient (R5.2)')
    base = h.base
    curve = common.CURVES['hejl_dawson']

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, 0, 1), (0, 0, 0))   # sun black: ambient only

    up_card = make_h_card(base.render, 30, 'up_card', z=0, face_up=True)
    down_card = make_h_card(base.render, 30, 'down_card', z=0, face_up=False)
    down_card.hide()
    cx, cy = h.win_w // 2, h.win_h // 2

    base.camera.set_pos(0, 0, 40)
    base.camera.set_hpr(0, -90, 0)     # straight down at the up-face

    # --- 1. Baseline: zero SH (shipped behavior) ------------------------
    h.step(5)
    img0 = h.capture()
    h.save_capture(img0, 'baseline')
    lum0 = common.avg_lum(img0, cx, cy)
    want0 = curve(AMB)
    h.report.check('baseline_flat_ambient', abs(lum0 - want0) < 0.05,
                   f'zero SH: card lum={lum0:.3f}, analytic ambient-only '
                   f'{want0:.3f}')

    # --- 2. Hemisphere ambient: up- and down-facing analytics -----------
    pipeline.set_hemisphere_ambient(SKY, GROUND)
    h.step(5)
    img_up = h.capture()
    h.save_capture(img_up, 'hemisphere_up')
    got_up = avg_rgb(img_up, cx, cy)
    want_up = expected_rgb(curve, +1.0)
    err_up = max(abs(g - w) for g, w in zip(got_up, want_up))
    h.report.check('up_face_analytic', err_up < 0.05,
                   f'up-facing card rgb=({got_up[0]:.3f},{got_up[1]:.3f},'
                   f'{got_up[2]:.3f}) expected ({want_up[0]:.3f},'
                   f'{want_up[1]:.3f},{want_up[2]:.3f}), max err {err_up:.3f}')
    h.report.check('up_face_sky_tinted', got_up[2] > got_up[0],
                   f'up face is sky-tinted: blue {got_up[2]:.3f} > red '
                   f'{got_up[0]:.3f}')

    up_card.hide()
    down_card.show()
    base.camera.set_pos(0, 0, -40)
    base.camera.set_hpr(0, 90, 0)      # straight up at the down-face
    h.step(5)
    img_down = h.capture()
    h.save_capture(img_down, 'hemisphere_down')
    got_down = avg_rgb(img_down, cx, cy)
    want_down = expected_rgb(curve, -1.0)
    err_down = max(abs(g - w) for g, w in zip(got_down, want_down))
    h.report.check('down_face_analytic', err_down < 0.05,
                   f'down-facing card rgb=({got_down[0]:.3f},'
                   f'{got_down[1]:.3f},{got_down[2]:.3f}) expected '
                   f'({want_down[0]:.3f},{want_down[1]:.3f},'
                   f'{want_down[2]:.3f}), max err {err_down:.3f}')
    h.report.check('down_face_ground_tinted', got_down[0] > got_down[2],
                   f'down face is ground-tinted: red {got_down[0]:.3f} > '
                   f'blue {got_down[2]:.3f}')

    # --- 3. Coefficients survive a recompile-class toggle ---------------
    # set_shadow_filter_size recompiles the PBR shader; with shadows off it
    # cannot change output, so any pixel drift means the SH inputs were
    # wiped or reset by _recompile_pbr/_set_env_map_uniforms.
    pipeline.set_shadow_filter_size(3)
    h.step(5)
    img_recompiled = h.capture()
    pipeline.set_shadow_filter_size(1)
    rms = common.image_rms_diff(img_down, img_recompiled, step=1)
    h.report.check('sh_survives_recompile', rms == 0.0,
                   f'shader recompile with hemisphere SH set: rms='
                   f'{rms:.2e} (inputs preserved, custom SH re-pushed)')

    # --- 4. clear_ambient_sh restores the baseline exactly --------------
    down_card.hide()
    up_card.show()
    base.camera.set_pos(0, 0, 40)
    base.camera.set_hpr(0, -90, 0)
    pipeline.clear_ambient_sh()
    h.step(5)
    img_cleared = h.capture()
    rms = common.image_rms_diff(img0, img_cleared, step=1)
    h.report.check('clear_restores_baseline', rms == 0.0,
                   f'clear_ambient_sh(): rms vs baseline = {rms:.2e} '
                   f'(byte-identical opt-out)')

    # --- 5. sh_from_cubemap math vs the analytic hemisphere -------------
    from pax3d_render.pipeline import sh_from_cubemap
    size = 32
    tex = p3d.Texture('paxtest_env')
    tex.setup_cube_map(size, p3d.Texture.T_float, p3d.Texture.F_rgb32)
    avg, delta = 0.5, 0.4              # L(dir) = 0.5 + 0.4 * dir_z
    for face in range(6):
        img = p3d.PNMImage(size, size, 3, 65535)
        for py in range(size):
            t = 1.0 - (py + 0.5) / size
            b = 2.0 * t - 1.0
            for px in range(size):
                s = (px + 0.5) / size
                a = 2.0 * s - 1.0
                d = face_dir(face, a, b)
                inv = (d[0] ** 2 + d[1] ** 2 + d[2] ** 2) ** -0.5
                v = avg + delta * d[2] * inv
                img.set_xel(px, py, v, v, v)
        tex.load(img, face, 0)
    coeffs = sh_from_cubemap(tex)
    want_c0 = math.pi * avg / 0.282095
    want_c2 = (2.0 * math.pi / 3.0) / 0.488603 * delta
    err_c0 = abs(coeffs[0][0] - want_c0) / want_c0
    err_c2 = abs(coeffs[2][0] - want_c2) / want_c2
    stray = max(abs(coeffs[i][0]) for i in (1, 3, 4, 5, 6, 7, 8))
    h.report.check('cubemap_sh_dc', err_c0 < 0.03,
                   f'DC coeff {coeffs[0][0]:.3f} vs analytic {want_c0:.3f} '
                   f'({err_c0 * 100:.1f}%)')
    h.report.check('cubemap_sh_linear_z', err_c2 < 0.03,
                   f'z-linear coeff {coeffs[2][0]:.3f} vs analytic '
                   f'{want_c2:.3f} ({err_c2 * 100:.1f}%)')
    h.report.check('cubemap_sh_stray_bands', stray < 0.05 * want_c0,
                   f'non-z bands stay ~zero for a pure z-gradient env '
                   f'(max stray {stray:.4f})')

    h.report.finish()


if __name__ == '__main__':
    main()
