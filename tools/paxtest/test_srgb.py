"""paxtest: sRGB input linearization experiment (Session R, R1.3).

The input half of the R1 color contract. Session A pinned the output
half (every tonemap curve matches its analytic exactly) and identified
the real ACES problem: INPUTS are sampled raw — 8-bit sRGB-encoded
texels enter the lighting math as display-space numbers. The experiment:
`set_srgb_inputs(True)` flags base-color (M_modulate) and emission
(M_emission) stage textures as sRGB formats so the GPU decodes to
linear at sample time. Data textures (M_normal, M_selector, ...) stay
linear. Off by default — the shipped contract is raw sampling and all
game content is tuned around it; the default never flips without
game-side sign-off.

Analytic setup: cards under the REAL pipeline shader, arranged so every
term is exact. Cards are metallic=1 / roughness=1, so the ambient term
collapses to base_color * ambient (diffuse=0, spec_color=base_color) —
linear in the sampled texel; the emission card is black-based with a
white emission material, so its pixel IS the sampled emission texel.
One AmbientLight (A) is the only light; sun black; IBL zeroed.

    8-bit 128 texel: raw = 128/255 = 0.50196
                     sRGB-decoded = ((0.50196+0.055)/1.055)^2.4 = 0.21586

Checks, in order:
  1. Raw baselines: modulate card = curve(0.50196*A), emission card =
     curve(0.50196), white card = curve(A) — the shipped contract.
  2. set_srgb_inputs(True): both cards land on the DECODED analytic
     through the hejl curve; formats flipped structurally; the M_normal
     stage texture is untouched.
  3. Tonemap sweep — the decoded value through aces / reinhard /
     uncharted2 analytics (the ACES-input-fix claim, measured).
  4. set_srgb_inputs(False): byte-identical restore (rms exactly 0).

Only meaningful for pipelines exposing set_srgb_inputs (pax3d_render).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common


AMBIENT = 0.6
TEX_8BIT = 128
RAW = TEX_8BIT / 255.0
DECODED = ((RAW + 0.055) / 1.055) ** 2.4
SWEEP_OPS = ['aces', 'reinhard', 'uncharted2']


def make_gray_texture(value_8bit, name):
    # A real RAM image, not set_clear_color: clear-color-only textures
    # round-trip their value through sRGB formats unchanged (driver
    # clears encode; measured Session R), so they cannot carry this
    # test — and real game content always has RAM images anyway.
    tex = p3d.Texture(name)
    tex.setup_2d_texture(4, 4, p3d.Texture.T_unsigned_byte,
                         p3d.Texture.F_rgb8)
    img = p3d.PNMImage(4, 4)
    v = value_8bit / 255.0
    img.fill(v, v, v)
    tex.load(img)
    tex.set_format(p3d.Texture.F_rgb8)
    tex.set_minfilter(p3d.SamplerState.FT_nearest)
    tex.set_magfilter(p3d.SamplerState.FT_nearest)
    return tex


def make_card(parent, x, name):
    cm = p3d.CardMaker(name)
    cm.set_frame(-0.25, 0.25, -0.25, 0.25)
    np = parent.attach_new_node(cm.generate())
    np.set_pos(x, 0, 0)
    np.set_two_sided(True)
    return np


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'srgb')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_srgb_inputs'):
        h.report.skip('pipeline has no set_srgb_inputs (R1.3)')
    base = h.base
    curve = common.CURVES['hejl_dawson']

    h.set_ortho(film_h=2.0)

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMBIENT, AMBIENT, AMBIENT, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))

    # Modulate card: metallic-1 white material + gray base-color texture
    # -> pixel = curve(texel * A), plus an M_normal data texture that
    # must NOT be converted
    card_mod = make_card(base.render, -0.6, 'card_mod')
    mat = p3d.Material('mod_mat')
    mat.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat.set_metallic(1.0)
    mat.set_roughness(1.0)
    card_mod.set_material(mat, 1)
    tex_mod = make_gray_texture(TEX_8BIT, 'gray_modulate')
    card_mod.set_texture(tex_mod, 1)
    tex_norm = make_gray_texture(TEX_8BIT, 'gray_normalmap')
    norm_stage = p3d.TextureStage('paxtest_normal')
    norm_stage.set_mode(p3d.TextureStage.M_normal)
    card_mod.set_texture(norm_stage, tex_norm, 1)

    # Emission card: black base, white emission material, gray emission
    # texture -> pixel = curve(texel)
    card_emis = make_card(base.render, 0.0, 'card_emis')
    mat = p3d.Material('emis_mat')
    mat.set_base_color(p3d.LColor(0, 0, 0, 1))
    mat.set_emission(p3d.LColor(1, 1, 1, 1))
    mat.set_metallic(1.0)
    mat.set_roughness(1.0)
    card_emis.set_material(mat, 1)
    tex_emis = make_gray_texture(TEX_8BIT, 'gray_emission')
    emis_stage = p3d.TextureStage('paxtest_emission')
    emis_stage.set_mode(p3d.TextureStage.M_emission)
    card_emis.set_texture(emis_stage, tex_emis, 1)

    # White card: calibration — pixel = curve(A) regardless of the flag
    card_white = make_card(base.render, 0.6, 'card_white')
    mat = p3d.Material('white_mat')
    mat.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat.set_metallic(1.0)
    mat.set_roughness(1.0)
    card_white.set_material(mat, 1)
    card_white.set_texture(make_gray_texture(255, 'white_modulate'), 1)

    film_w = 2.0 * h.win_w / h.win_h
    px = {name: int((x / film_w + 0.5) * h.win_w)
          for name, x in (('mod', -0.6), ('emis', 0.0), ('white', 0.6))}
    cy = h.win_h // 2

    def check_value(img, which, want_linear, op, tag, tol=0.02):
        got = common.avg_lum(img, px[which], cy, half=1)
        want = common.CURVES[op](want_linear)
        h.report.check(
            tag, abs(got - want) < tol,
            f'{which} card via {op}: lum={got:.3f} expected '
            f'{want:.3f} (linear {want_linear:.4f})')

    # --- 1. Raw baselines (the shipped contract) ------------------------
    h.step(5)
    img_off = h.capture()
    h.save_capture(img_off, 'raw')
    check_value(img_off, 'mod', RAW * AMBIENT, 'hejl_dawson',
                'baseline_mod_raw')
    check_value(img_off, 'emis', RAW, 'hejl_dawson', 'baseline_emis_raw')
    check_value(img_off, 'white', AMBIENT, 'hejl_dawson',
                'calibration_white')

    # --- 2. Linearized inputs ------------------------------------------
    n = pipeline.set_srgb_inputs(True)
    h.report.info('converted', f'{n} textures flipped to sRGB formats')
    h.step(5)
    img_on = h.capture()
    h.save_capture(img_on, 'srgb')
    check_value(img_on, 'mod', DECODED * AMBIENT, 'hejl_dawson',
                'srgb_mod_decoded')
    check_value(img_on, 'emis', DECODED, 'hejl_dawson',
                'srgb_emis_decoded')
    check_value(img_on, 'white', AMBIENT, 'hejl_dawson',
                'srgb_white_unchanged')
    h.report.check(
        'modulate_format_flipped',
        tex_mod.get_format() == p3d.Texture.F_srgb,
        f'base-color texture format is now F_srgb '
        f'({tex_mod.get_format()})')
    h.report.check(
        'normal_stage_untouched',
        tex_norm.get_format() == p3d.Texture.F_rgb8,
        f'M_normal stage texture stays linear ({tex_norm.get_format()})')

    # --- 3. Decoded value through every tonemap curve -------------------
    for op in SWEEP_OPS:
        h.adapter.set_tonemap(op)
        h.step(5)
        img = h.capture()
        if op == 'aces':
            h.save_capture(img, 'srgb_aces')
        check_value(img, 'emis', DECODED, op, f'{op}_emis_decoded')
        check_value(img, 'mod', DECODED * AMBIENT, op, f'{op}_mod_decoded')
    h.adapter.set_tonemap('hejl_dawson')

    # --- 4. Opt-out restores the baseline exactly -----------------------
    pipeline.set_srgb_inputs(False)
    h.step(5)
    img_restored = h.capture()
    rms = common.image_rms_diff(img_off, img_restored, step=1)
    h.report.check('opt_out_restores', rms == 0.0,
                   f'set_srgb_inputs(False): rms vs the raw baseline = '
                   f'{rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
