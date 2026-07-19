"""paxtest: powered displays (ER-005 — walkable-ship screens).

The Unity ship packs' dominant display mechanism (MINERVA_CENSUS §3) is
a texture bound as BOTH albedo and emission on a Standard material —
pax3d_render reproduces it with set_screen() plus per-node emission
factor (set_emission_scale/_color) and per-node UV transform
(set_uv_transform / set_uv_scroll / play_flipbook — the flipbook is the
sanctioned video path on the no-ffmpeg Pax3D wheel).

Scene: ortho camera, a card filling the window, sun BLACK, tiny flat
AmbientLight AMB — every check is analytic per channel:

    albedo screen:  lin = e[ch]*t + AMB*(0.96*t + 0.04)
    emissive-only:  lin = e[ch]*t + AMB*0.04
    (t = quadrant texel value, e = material emission * emission factor,
     0.96 = 1-F0 diffuse, 0.04 = F0 spec under flat ambient)

The screen texture is a 2x2 quadrant color map (nearest filter), so
every UV-transform state maps to exact expected colors at the four
quadrant-center pixels.

Checks: baseline anchor, screen binding analytics, power-off
(scale 0 keeps albedo lit), HDR color/scale, byte-identical
clear_emission, UV window (flipbook building block) + restore,
recompile survival, flipbook frame mapping + frame-0 render +
restore, UV scroll animates + restore, emissive-only rebind
(albedo=False), and clear_screen back to the baseline byte-identically.

Only meaningful for pipelines exposing set_screen (pax3d_render).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

AMB = 0.02
F0 = 0.04
KD = 1.0 - F0
GRAY = 0.5

# Quadrant colors: keys are (u_half, v_half) with v up (0 = bottom).
QUAD = {
    (0, 1): (0.0, 0.0, 1.0),   # top-left     blue
    (1, 1): (1.0, 1.0, 0.0),   # top-right    yellow
    (0, 0): (1.0, 0.0, 0.0),   # bottom-left  red
    (1, 0): (0.0, 1.0, 0.0),   # bottom-right green
}


def make_quad_tex():
    img = p3d.PNMImage(2, 2)
    img.set_xel(0, 0, *QUAD[(0, 1)])   # PNM row 0 = top
    img.set_xel(1, 0, *QUAD[(1, 1)])
    img.set_xel(0, 1, *QUAD[(0, 0)])
    img.set_xel(1, 1, *QUAD[(1, 0)])
    tex = p3d.Texture('paxtest_screen_quads')
    tex.load(img)
    tex.set_minfilter(p3d.SamplerState.FT_nearest)
    tex.set_magfilter(p3d.SamplerState.FT_nearest)
    tex.set_wrap_u(p3d.SamplerState.WM_repeat)
    tex.set_wrap_v(p3d.SamplerState.WM_repeat)
    return tex


def make_card(parent):
    cm = p3d.CardMaker('paxtest_screen_card')
    cm.set_frame(-1, 1, -1, 1)
    cm.set_uv_range((0, 0), (1, 1))
    np = parent.attach_new_node(cm.generate())
    np.set_pos(0, 5, 0)                # facing the default -Y camera

    mat = p3d.Material('paxtest_screen_base')
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


def expected(curve, t_rgb, e_rgb, albedo=True):
    out = []
    for ch in range(3):
        t = t_rgb[ch]
        if albedo:
            lin = e_rgb[ch] * t + AMB * (KD * t + F0)
        else:
            lin = e_rgb[ch] * t + AMB * F0
        out.append(curve(lin))
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


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'screen')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_screen'):
        h.report.skip('pipeline has no set_screen (ER-005)')
    base = h.base
    curve = common.CURVES['hejl_dawson']

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))    # sun black
    h.set_ortho(film_h=2.0)

    card = make_card(base.render)
    quad_tex = make_quad_tex()

    # Quadrant-center sample pixels (PNM y down; v up).
    def qpix(u_half, v_half):
        cx = (0.25 + 0.5 * u_half) * h.win_w
        cy = (1.0 - (0.25 + 0.5 * v_half)) * h.win_h
        return cx, cy

    def check_quads(name, img, e_rgb, albedo=True, uniform_color=None,
                    tol=0.03, extra=''):
        worst = 0.0
        details = []
        for key, t_rgb in QUAD.items():
            want_t = uniform_color if uniform_color is not None else t_rgb
            want = expected(curve, want_t, e_rgb, albedo)
            got = avg_rgb(img, *qpix(*key))
            err = max(abs(g - w) for g, w in zip(got, want))
            worst = max(worst, err)
            if err >= tol:
                details.append(f'{key}: got ({got[0]:.3f},{got[1]:.3f},'
                               f'{got[2]:.3f}) want ({want[0]:.3f},'
                               f'{want[1]:.3f},{want[2]:.3f})')
        h.report.check(name, worst < tol,
                       f'worst quadrant err {worst:.3f}{extra}'
                       + ('; ' + '; '.join(details) if details else ''))

    # --- 1. Baseline anchor (gray albedo card, ambient only) ------------
    h.step(5)
    img_base = h.capture()
    h.save_capture(img_base, 'baseline')
    want = curve(AMB * (KD * GRAY + F0))
    got = avg_rgb(img_base, h.win_w * 0.5, h.win_h * 0.5)
    err = max(abs(g - want) for g in got)
    h.report.check('baseline_analytic', err < 0.03,
                   f'gray card rgb ({got[0]:.3f},{got[1]:.3f},{got[2]:.3f}) '
                   f'expected {want:.3f}, err {err:.3f}')

    # --- 2. set_screen binds albedo+emission ----------------------------
    pipeline.set_screen(card, quad_tex)
    h.step(5)
    img_screen = h.capture()
    h.save_capture(img_screen, 'screen_on')
    check_quads('screen_binds_analytic', img_screen, (1.0, 1.0, 1.0),
                extra=' (texture as albedo+emission, e=1)')

    # --- 3. Power off: emission dies, albedo stays lit ------------------
    pipeline.set_emission_scale(card, 0.0)
    h.step(5)
    img_off = h.capture()
    h.save_capture(img_off, 'screen_off')
    check_quads('screen_off_albedo_lit', img_off, (0.0, 0.0, 0.0),
                extra=' (scale 0 = the VA_ScreenOff state; quadrants '
                      'still faintly visible under room light)')

    # --- 4. HDR scale + color tint --------------------------------------
    pipeline.set_emission_scale(card, 2.0)
    pipeline.set_emission_color(card, (1.0, 0.5, 0.25))
    h.step(5)
    img_tint = h.capture()
    check_quads('emission_scale_color', img_tint, (2.0, 1.0, 0.5),
                extra=' (scale 2.0 * color (1,.5,.25))')

    # --- 5. clear_emission restores the e=1 state byte-identically ------
    pipeline.clear_emission(card)
    h.step(5)
    rms = common.image_rms_diff(img_screen, h.capture(), step=1)
    h.report.check('clear_emission_restores', rms == 0.0,
                   f'rms vs screen_on = {rms:.2e}')

    # --- 6. UV window (the flipbook building block) ---------------------
    pipeline.set_uv_transform(card, offset=(0.5, 0.5), scale=(0.5, 0.5))
    h.step(5)
    img_win = h.capture()
    h.save_capture(img_win, 'uv_window')
    check_quads('uv_window_selects_quadrant', img_win, (1.0, 1.0, 1.0),
                uniform_color=QUAD[(1, 1)],
                extra=' (uv*0.5+0.5 windows the top-right cell '
                      'everywhere)')
    pipeline.clear_uv_transform(card)
    h.step(5)
    rms = common.image_rms_diff(img_screen, h.capture(), step=1)
    h.report.check('clear_uv_transform_restores', rms == 0.0,
                   f'rms vs screen_on = {rms:.2e}')

    # --- 7. Screen state survives a shader-recompile-class toggle -------
    pipeline.set_shadow_filter_size(3)
    h.step(5)
    img_recompiled = h.capture()
    pipeline.set_shadow_filter_size(1)
    h.step(2)
    rms = common.image_rms_diff(img_screen, img_recompiled, step=1)
    h.report.check('screen_survives_recompile', rms == 0.0,
                   f'rms vs screen_on across recompile = {rms:.2e}')

    # --- 8. Flipbook: frame->window mapping + frame-0 render ------------
    fb = pipeline._flipbook_transform
    mapping_ok = (fb(2, 2, 0) == (0.0, 0.5, 0.5, 0.5)
                  and fb(2, 2, 1) == (0.5, 0.5, 0.5, 0.5)
                  and fb(2, 2, 2) == (0.0, 0.0, 0.5, 0.5)
                  and fb(2, 2, 3) == (0.5, 0.0, 0.5, 0.5))
    h.report.check('flipbook_frame_mapping', mapping_ok,
                   f'2x2 frames 0-3 -> {[fb(2, 2, i) for i in range(4)]} '
                   f'(row-major from TOP-LEFT)')
    pipeline.play_flipbook(card, 2, 2, fps=1e-3)   # frame 0 holds
    h.step(5)
    img_fb = h.capture()
    check_quads('flipbook_frame0_renders', img_fb, (1.0, 1.0, 1.0),
                uniform_color=QUAD[(0, 1)],
                extra=' (frame 0 = top-left cell)')
    pipeline.stop_flipbook(card)
    h.step(5)
    rms = common.image_rms_diff(img_screen, h.capture(), step=1)
    h.report.check('stop_flipbook_restores', rms == 0.0,
                   f'rms vs screen_on = {rms:.2e}')

    # --- 9. UV scroll animates ------------------------------------------
    pipeline.set_uv_scroll(card, 0.25, 0.0)
    h.step(5)
    img_a = h.capture()
    h.step(30)
    img_b = h.capture()
    rms_moved = common.image_rms_diff(img_a, img_b, step=1)
    h.report.check('uv_scroll_animates', rms_moved > 1e-5,
                   f'captures 30 frames apart rms {rms_moved:.5f}')
    pipeline.clear_uv_scroll(card)
    h.step(5)
    rms = common.image_rms_diff(img_screen, h.capture(), step=1)
    h.report.check('clear_uv_scroll_restores', rms == 0.0,
                   f'rms vs screen_on = {rms:.2e}')

    # --- 9b. Blinker (ship nav/strobe/beacon driver) --------------------
    # Envelope math is a pinned pure function; the render checks force a
    # known envelope state via phase (period >> test duration).
    env = pipeline._blink_envelope
    env_ok = (env(0.02, 1.0, ((0.0, 0.05), (0.15, 0.05))) == 1.0
              and env(0.10, 1.0, ((0.0, 0.05), (0.15, 0.05))) == 0.0
              and env(0.17, 1.0, ((0.0, 0.05), (0.15, 0.05))) == 1.0
              and env(1.02, 1.0, ((0.0, 0.05),)) == 1.0      # wraps
              and env(0.5, 1.0, ((0.0, 0.05),), phase=0.5) == 1.0
              and env(0.0, 1.33, ((0.0, 0.20),), phase=0.3) == 0.0)
    h.report.check('blink_envelope_math', env_ok,
                   'double-flash windows, wrap, and phase all exact')

    lamp = p3d.PointLight('paxtest_blink_lamp')
    lamp.set_color(p3d.LColor(0.8, 0.4, 0.2, 1))
    lamp_np = base.render.attach_new_node(lamp)   # never set_light: the
    # sync contract is measured on the node color, no render impact
    now = p3d.ClockObject.get_global_clock().get_frame_time()
    pipeline.set_blink(card, period=1000.0, pulses=((0.0, 500.0),),
                       phase=-(now % 1000.0), lights=[lamp_np])
    h.step(5)
    rms_on = common.image_rms_diff(img_screen, h.capture(), step=1)
    lamp_on = tuple(lamp.get_color())
    pipeline.set_blink(card, period=1000.0, pulses=((0.0, 500.0),),
                       phase=-(now % 1000.0) + 600.0, lights=[lamp_np])
    h.step(5)
    rms_off = common.image_rms_diff(img_off, h.capture(), step=1)
    lamp_off = tuple(lamp.get_color())
    h.report.check('blink_on_off_states', rms_on == 0.0 and rms_off == 0.0,
                   f'pulse-ON == screen_on rms {rms_on:.2e}; gap-OFF == '
                   f'emission-0 rms {rms_off:.2e}')
    LAMP = (0.8, 0.4, 0.2, 1.0)

    def color_close(got, want):
        return max(abs(g - w) for g, w in zip(got, want)) < 1e-6

    h.report.check('blink_syncs_light',
                   color_close(lamp_on, LAMP)
                   and lamp_off == (0.0, 0.0, 0.0, 1.0),
                   f'lamp color ON {tuple(round(c, 3) for c in lamp_on)} '
                   f'/ OFF {lamp_off} (gated with the same envelope)')
    pipeline.clear_blink(card)
    h.step(5)
    rms = common.image_rms_diff(img_screen, h.capture(), step=1)
    lamp_restored = tuple(lamp.get_color())
    h.report.check('clear_blink_restores',
                   rms == 0.0 and color_close(lamp_restored, LAMP),
                   f'rms vs screen_on = {rms:.2e}, lamp color restored '
                   f'{tuple(round(c, 3) for c in lamp_restored)}')

    # --- 10. Emissive-only rebind (albedo=False, in-place re-call) ------
    pipeline.set_screen(card, quad_tex, albedo=False)
    h.step(5)
    img_em = h.capture()
    h.save_capture(img_em, 'emissive_only')
    check_quads('emissive_only_analytic', img_em, (1.0, 1.0, 1.0),
                albedo=False,
                extra=' (albedo=False: black base, pure glow)')

    # --- 11. clear_screen restores the baseline byte-identically --------
    pipeline.clear_screen(card)
    h.step(5)
    rms = common.image_rms_diff(img_base, h.capture(), step=1)
    h.report.check('clear_screen_restores', rms == 0.0,
                   f'rms vs baseline = {rms:.2e} (texture + material '
                   f'state both restored)')

    h.report.finish()


if __name__ == '__main__':
    main()
