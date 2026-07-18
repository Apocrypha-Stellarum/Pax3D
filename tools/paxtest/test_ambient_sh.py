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
  6. FILE-loaded skybox face table (the Session P pin, closing the
     orientation question): six solid-color face images written to disk,
     loaded with loader.load_cube_map('..._#.png') — file N must land on
     GL face N with content intact (readback), matching the compass
     convention the openworld marker rig validated in-app 2026-07-18
     (PAX3D_FEEDBACK_2.md): file 0 = +x east, 1 = -x west, 2 = +y north,
     3 = -y south, 4 = +z up, 5 = -z down.
  7. The same skybox through sh_from_cubemap: irradiance evaluated with
     the shader's own basis names the correct marker color along every
     compass direction.
  8. In-face orientation of a file-loaded UP face: a top-red/bottom-blue
     face-4 image must tilt irradiance red toward SOUTH (-y) — i.e. the
     top row of the up-face image file is the southern sky.

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

    # --- 4b. Per-node SH override (Session S — cabin ambient) -----------
    # Global hemisphere on; a second up-facing card floats above the big
    # one with a node= override using SWAPPED colors — an up-facing card
    # under the swapped hemisphere must render exactly the down-face
    # analytic, while the global card underneath is untouched.
    if 'node' in pipeline.set_ambient_sh.__code__.co_varnames:
        pipeline.set_hemisphere_ambient(SKY, GROUND)
        card_b = make_h_card(base.render, 6, 'node_card', z=0.5,
                             face_up=True)
        card_b.set_x(8)
        ndc = p3d.Point2()
        base.camLens.project(base.camera.get_relative_point(
            base.render, card_b.get_pos(base.render)), ndc)
        bx = int((ndc.x * 0.5 + 0.5) * h.win_w)
        by = int((ndc.y * 0.5 + 0.5) * h.win_h)
        h.step(5)
        img_before = h.capture()
        pipeline.set_hemisphere_ambient(GROUND, SKY, node=card_b)
        h.step(5)
        img_node = h.capture()
        h.save_capture(img_node, 'pernode_sh')
        got_b = avg_rgb(img_node, bx, by)
        want_b = expected_rgb(curve, -1.0)    # swapped == down-face value
        err_b = max(abs(g - w) for g, w in zip(got_b, want_b))
        got_c = avg_rgb(img_node, cx, cy)
        want_c = expected_rgb(curve, +1.0)
        err_c = max(abs(g - w) for g, w in zip(got_c, want_c))
        h.report.check(
            'pernode_sh_override', err_b < 0.05 and err_c < 0.05,
            f'node card rgb=({got_b[0]:.3f},{got_b[1]:.3f},{got_b[2]:.3f})'
            f' expected swapped-hemisphere ({want_b[0]:.3f},'
            f'{want_b[1]:.3f},{want_b[2]:.3f}) err {err_b:.3f}; global '
            f'card beneath unaffected (err {err_c:.3f})')
        pipeline.clear_ambient_sh(node=card_b)
        h.step(5)
        rms = common.image_rms_diff(img_before, h.capture(), step=1)
        h.report.check('pernode_sh_clear_restores', rms == 0.0,
                       f'clear_ambient_sh(node=...): rms vs pre-override '
                       f'= {rms:.2e} (subtree reverts to the global set)')
        card_b.remove_node()
        pipeline.clear_ambient_sh()
        h.step(2)

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

    # --- 6-8. FILE-loaded skybox: face table + orientation pin ----------
    # Shader irradiance evaluation — deliberately DUPLICATED from
    # pax_pbr.frag irradiance_from_sh (same slot order and constants).
    def eval_irradiance(c, d):
        x, y, z = d
        w = (0.282095,
             0.488603 * x, 0.488603 * z, 0.488603 * y,
             1.092548 * x * z, 1.092548 * y * z, 1.092548 * y * x,
             0.946176 * z * z - 0.315392,
             0.546274 * (x * x - y * y))
        return tuple(sum(c[i][ch] * w[i] for i in range(9)) for ch in range(3))

    # The compass marker rig from the openworld validation: RED east,
    # GREEN north, BLUE west, YELLOW south; white up, dim down.
    face_colors = [(1, 0, 0), (0, 0, 1), (0, 1, 0),
                   (1, 1, 0), (1, 1, 1), (0.1, 0.1, 0.1)]
    out_dir = p3d.Filename.from_os_specific(common.OUTPUT_DIR).get_fullpath()
    fsize = 16
    for face, rgb in enumerate(face_colors):
        img = p3d.PNMImage(fsize, fsize, 3)
        img.fill(*rgb)
        img.write(p3d.Filename(f'{out_dir}/skyface_{face}.png'))
    sky_tex = base.loader.load_cube_map(f'{out_dir}/skyface_#.png')
    ok = sky_tex is not None
    worst = 0.0
    if ok:
        img = p3d.PNMImage()
        for face, rgb in enumerate(face_colors):
            if not sky_tex.store(img, face, 0):
                ok = False
                break
            got = img.get_xel(fsize // 2, fsize // 2)
            worst = max(worst, max(abs(got[i] - rgb[i]) for i in range(3)))
        ok = ok and worst < 0.02
    h.report.check('skybox_file_face_table', ok,
                   f'load_cube_map file N -> GL face N, content intact '
                   f'(worst center-texel err {worst:.4f})')

    comp = sh_from_cubemap(sky_tex)
    dirs = {'east_red': ((1, 0, 0), 0), 'west_blue': ((-1, 0, 0), 2),
            'north_green': ((0, 1, 0), 1)}
    all_ok = True
    detail = []
    for name, (d, ch) in dirs.items():
        e = eval_irradiance(comp, d)
        good = e[ch] == max(e) and e[ch] > 1.2 * min(e)
        all_ok = all_ok and good
        detail.append(f'{name}=({e[0]:.2f},{e[1]:.2f},{e[2]:.2f})')
    e_s = eval_irradiance(comp, (0, -1, 0))
    good_s = min(e_s[0], e_s[1]) > 1.2 * e_s[2]
    all_ok = all_ok and good_s
    detail.append(f'south_yellow=({e_s[0]:.2f},{e_s[1]:.2f},{e_s[2]:.2f})')
    h.report.check('skybox_file_sh_compass', all_ok,
                   'file skybox -> SH names every marker: ' + '; '.join(detail))

    # Up-face image: top half red, bottom half blue (fresh filenames — the
    # loader caches by path).
    for face, rgb in enumerate(face_colors[:4]):
        img = p3d.PNMImage(fsize, fsize, 3)
        img.fill(0.1, 0.1, 0.1)
        img.write(p3d.Filename(f'{out_dir}/skygrad_{face}.png'))
    img = p3d.PNMImage(fsize, fsize, 3)
    for py in range(fsize):
        rgb = (1, 0, 0) if py < fsize // 2 else (0, 0, 1)
        for px in range(fsize):
            img.set_xel(px, py, *rgb)
    img.write(p3d.Filename(f'{out_dir}/skygrad_4.png'))
    img = p3d.PNMImage(fsize, fsize, 3)
    img.fill(0.1, 0.1, 0.1)
    img.write(p3d.Filename(f'{out_dir}/skygrad_5.png'))
    grad_tex = base.loader.load_cube_map(f'{out_dir}/skygrad_#.png')
    gc = sh_from_cubemap(grad_tex)
    e_south = eval_irradiance(gc, (0, -1, 0))
    e_north = eval_irradiance(gc, (0, 1, 0))
    h.report.check('skybox_file_up_orientation',
                   e_south[0] > 1.2 * e_south[2] and
                   e_north[2] > 1.2 * e_north[0],
                   f'up-face image TOP row = SOUTHERN sky: E(south)='
                   f'({e_south[0]:.2f},{e_south[1]:.2f},{e_south[2]:.2f}) '
                   f'red-tilted, E(north)=({e_north[0]:.2f},{e_north[1]:.2f},'
                   f'{e_north[2]:.2f}) blue-tilted')

    h.report.finish()


if __name__ == '__main__':
    main()
