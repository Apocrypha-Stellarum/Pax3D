"""paxtest: terrain layer splatting (ER-001, pipeline.set_terrain_splat).

The TERRAIN_SPLAT variant blends up to 4 material layers (2D texture
arrays) per-fragment, weighted by an RGBA splat map, replacing only the
MATERIAL INPUTS of the standard PBR shader — so sun/shadows/fog/IBL
compose untouched. This gate pins the blend math analytically.

Analytic setup (the test_srgb pattern): cards under the REAL pipeline
shader with metallic=1 / roughness=1 materials collapse the ambient
term to base_color * A exactly (diffuse=0, spec=base_color, IBL zero,
sun black) — so a splat quadrant's pixel IS curve(layer_color * A).

Checks, in order:
  1. Quadrant purity: 2x2 splat (R/G/B/A texels) over 4 solid-color
     layers -> each quadrant renders exactly curve(c_i * A).
  2. Bilinear 4-way blend at the splat center: curve(mean(c_i) * A).
  3. Weight renormalization: a (0.2, 0.2, 0, 0) splat texel renders
     exactly like (0.5, 0.5, 0, 0) — the in-shader renorm contract.
  4. Macro variation: albedo modulated by mix(1, 2*macro, strength),
     analytic against the decoded macro texel.
  5. Per-layer uv_scale: a half-bright/half-dark layer slice sampled at
     scale 0.5 vs 1.0 flips a known pixel bright/dark.
  6. Normal array + distance fade (comparative): a 45-degree-tilted
     tangent normal lights up under a horizontal sun where the faded
     (forced-flat) config shows ambient only; forcing the fade
     reproduces flat exactly. Uses the analytic terrain TBN — the card
     carries NO tangent column, like real chunk meshes.
  7. Opt-out: clear_terrain_splat() restores the untouched-card capture
     byte-identically (rms == 0).

The directional-sun variant run (run.py) re-runs the quadrant checks
with sun_light_mode='directional' — proving the variant compiles and
behaves under SUN_FROM_LIGHTSOURCE.

Only meaningful for pax3d_render (set_terrain_splat lives there).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

AMBIENT = 0.6
C0 = (0.8, 0.0, 0.0)   # layer colors, exact byte values (204/255)
C1 = (0.0, 0.8, 0.0)
C2 = (0.0, 0.0, 0.8)
C3 = (0.8, 0.8, 0.0)
LAYERS = [C0, C1, C2, C3]
MACRO_BYTE = 191       # macro texel; factor = 2 * (191/255) at strength 1
CURVE = common.CURVES['hejl_dawson']


def solid_image(size, rgb, maxch=3):
    img = p3d.PNMImage(size, size, maxch)
    img.fill(*rgb)
    return img


def make_albedo_array(layer_colors, name):
    tex = p3d.Texture(name)
    tex.setup_2d_texture_array(4, 4, len(layer_colors),
                               p3d.Texture.T_unsigned_byte,
                               p3d.Texture.F_rgb8)
    for z, rgb in enumerate(layer_colors):
        tex.load(solid_image(4, rgb), z, 0)
    tex.set_minfilter(p3d.SamplerState.FT_nearest)
    tex.set_magfilter(p3d.SamplerState.FT_nearest)
    return tex


def make_splat(texels, name, filt=p3d.SamplerState.FT_linear):
    """2x2 RGBA splat: texels = ((r,g,b,a) top-left, top-right,
    bottom-left, bottom-right) in 0..255 bytes."""
    img = p3d.PNMImage(2, 2, 4)
    for i, (x, y) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
        r, g, b, a = texels[i]
        img.set_xel_val(x, y, r, g, b)
        img.set_alpha_val(x, y, a)
    tex = p3d.Texture(name)
    tex.load(img)
    tex.set_minfilter(filt)
    tex.set_magfilter(filt)
    tex.set_wrap_u(p3d.SamplerState.WM_clamp)
    tex.set_wrap_v(p3d.SamplerState.WM_clamp)
    return tex


def expected_lum(rgb, scale=1.0, ambient=AMBIENT):
    return sum(CURVE(c * scale * ambient) for c in rgb) / 3.0


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default='uniforms')
    args = parser.parse_args()

    h = common.Harness(args, 'terrain_splat')
    if args.pipeline != 'pax3d_render':
        h.report.skip('set_terrain_splat lives in pax3d_render (ER-001)')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode)
    pipeline = h.adapter.pipeline
    if common.PAX3D_ROOT not in sys.path:
        sys.path.insert(0, common.PAX3D_ROOT)
    from pax3d_render import data_texture

    base = h.base
    h.set_ortho(film_h=2.0)

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMBIENT, AMBIENT, AMBIENT, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((1, 0, 0), (0, 0, 0))  # sun black for phases 1-5

    cm = p3d.CardMaker('terrain_card')
    cm.set_frame(-1, 1, -1, 1)
    card = base.render.attach_new_node(cm.generate())
    card.set_two_sided(True)
    mat_metal = p3d.Material('metal1')
    mat_metal.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat_metal.set_metallic(1.0)
    mat_metal.set_roughness(1.0)
    card.set_material(mat_metal, 1)

    # Pixel positions: film 2x2 maps 1:1 onto the window
    def px(fx, fy):
        return (int((fx / 2.0 + 0.5) * h.win_w),
                int((0.5 - fy / 2.0) * h.win_h))

    QUADS = {  # quadrant film centers -> expected layer (splat texels below)
        'q_topleft': ((-0.5, 0.5), C0),
        'q_topright': ((0.5, 0.5), C1),
        'q_botleft': ((-0.5, -0.5), C2),
        'q_botright': ((0.5, -0.5), C3),
    }

    # --- Phase 0: untouched baseline for the opt-out check --------------
    h.step(5)
    img_bare = h.capture()

    # --- Phase 1+2: quadrant purity + center blend ----------------------
    albedo = make_albedo_array(LAYERS, 'albedo4')
    splat_quad = data_texture(make_splat(
        ((255, 0, 0, 0), (0, 255, 0, 0), (0, 0, 255, 0), (0, 0, 0, 255)),
        'splat_quad'))
    pipeline.set_terrain_splat(card, albedo, splat_quad)
    h.step(5)
    img = h.capture()
    h.save_capture(img, 'quadrants')
    for tag, ((fx, fy), rgb) in QUADS.items():
        x, y = px(fx, fy)
        got = common.avg_lum(img, x, y)
        want = expected_lum(rgb)
        h.report.check(tag, abs(got - want) < 0.02,
                       f'lum={got:.3f} expected {want:.3f} '
                       f'(layer {rgb})')
    cx, cy = px(0.0, 0.0)
    got = common.avg_lum(img, cx, cy)
    center_rgb = [sum(c[i] for c in LAYERS) / 4.0 for i in range(3)]
    want = expected_lum(center_rgb)
    h.report.check('center_4way_blend', abs(got - want) < 0.02,
                   f'lum={got:.3f} expected {want:.3f} '
                   f'(bilinear mid = mean of 4 layers)')

    # --- Phase 3: weight renormalization --------------------------------
    splat_dim = data_texture(make_splat(
        ((51, 51, 0, 0),) * 4, 'splat_dim'))
    pipeline.set_terrain_splat(card, albedo, splat_dim)
    h.step(5)
    img = h.capture()
    got = common.avg_lum(img, cx, cy)
    half_rgb = [(C0[i] + C1[i]) / 2.0 for i in range(3)]
    want = expected_lum(half_rgb)
    h.report.check('weights_renormalized', abs(got - want) < 0.02,
                   f'(0.2,0.2,0,0) splat: lum={got:.3f} expected '
                   f'{want:.3f} (== normalized 0.5/0.5 blend)')

    # --- Phase 4: macro variation ---------------------------------------
    macro_img = p3d.PNMImage(2, 2, 1)
    macro_img.fill_val(MACRO_BYTE)
    macro_tex = p3d.Texture('macro')
    macro_tex.load(macro_img)
    pipeline.set_terrain_splat(card, albedo, splat_quad,
                               macro_map=macro_tex, macro_uv_scale=1.0,
                               macro_strength=1.0)
    h.step(5)
    img = h.capture()
    factor = 2.0 * (MACRO_BYTE / 255.0)
    x, y = px(-0.5, 0.5)
    got = common.avg_lum(img, x, y)
    want = expected_lum(C0, scale=factor)
    h.report.check('macro_modulation', abs(got - want) < 0.02,
                   f'macro {MACRO_BYTE}/255 @ strength 1: lum={got:.3f} '
                   f'expected {want:.3f} (factor {factor:.3f})')

    # --- Phase 5: per-layer uv_scale ------------------------------------
    # Layer 0 slice: left half 0.8-bright, right half black; uniform
    # layer-0 splat. At uv_scale 0.5 the right-quadrant sample (u=0.75
    # -> u'=0.375) lands in the bright half; at 1.0 (u'=0.75) the dark.
    half_img = p3d.PNMImage(4, 4, 3)
    for xx in range(4):
        v = 0.8 if xx < 2 else 0.0
        for yy in range(4):
            half_img.set_xel(xx, yy, v, v, v)
    uv_array = p3d.Texture('albedo_halves')
    uv_array.setup_2d_texture_array(4, 4, 4, p3d.Texture.T_unsigned_byte,
                                    p3d.Texture.F_rgb8)
    uv_array.load(half_img, 0, 0)
    for z in range(1, 4):
        uv_array.load(solid_image(4, (0, 0, 0)), z, 0)
    uv_array.set_minfilter(p3d.SamplerState.FT_nearest)
    uv_array.set_magfilter(p3d.SamplerState.FT_nearest)
    splat_l0 = data_texture(make_splat(((255, 0, 0, 0),) * 4, 'splat_l0'))
    x, y = px(0.5, 0.0)
    bright = (0.8, 0.8, 0.8)
    for scale, want_rgb, tag in ((0.5, bright, 'uv_scale_half'),
                                 (1.0, (0, 0, 0), 'uv_scale_full')):
        pipeline.set_terrain_splat(card, uv_array, splat_l0,
                                   uv_scales=(scale, 1, 1, 1))
        h.step(5)
        img = h.capture()
        got = common.avg_lum(img, x, y)
        want = expected_lum(want_rgb)
        h.report.check(tag, abs(got - want) < 0.02,
                       f'scale {scale}: lum={got:.3f} expected {want:.3f}')

    # --- Phase 6: normal array + distance fade (comparative) ------------
    # 45-degree tilt toward tangent-u; horizontal sun along +x. The
    # geometric normal is perpendicular to the sun (ndl=0), so ONLY the
    # normal map lights the card. Fade forced -> flat -> ambient only.
    mat_diel = p3d.Material('diel')
    mat_diel.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat_diel.set_metallic(0.0)
    mat_diel.set_roughness(1.0)
    card.set_material(mat_diel, 1)
    h.adapter.update_sun((1, 0, 0), (2.0, 2.0, 2.0))

    tilt_img = p3d.PNMImage(4, 4, 3)
    tilt_img.fill_val(218, 127, 218)      # n_ts ~ (0.707, 0, 0.707)
    norm_array = p3d.Texture('normals_tilt')
    norm_array.setup_2d_texture_array(4, 4, 4, p3d.Texture.T_unsigned_byte,
                                      p3d.Texture.F_rgb8)
    for z in range(4):
        norm_array.load(tilt_img, z, 0)

    white_array = make_albedo_array([(0.8, 0.8, 0.8)] * 4, 'albedo_white')
    # 'near': fade edges far beyond the card -> nf=0, tilt active.
    # 'faded': edges BELOW the card's ~0 view distance -> nf=1, flat.
    # (The ortho camera sits ON the card plane: view distance ~0, so
    # (0.0, 0.1) would give smoothstep(...)=0 — measured trap.)
    lums = {}
    for tag, fade in (('near', (1e6, 2e6)), ('faded', (-2.0, -1.0))):
        pipeline.set_terrain_splat(card, white_array, splat_l0,
                                   normal_array=norm_array,
                                   normal_fade=fade)
        h.step(5)
        img = h.capture()
        lums[tag] = common.avg_lum(img, cx, cy)
        if tag == 'near':
            h.save_capture(img, 'normals')
    h.report.check(
        'normal_tilt_lights', lums['near'] > lums['faded'] + 0.05,
        f'tilted normal under horizontal sun: lum={lums["near"]:.3f} vs '
        f'faded-flat {lums["faded"]:.3f} (map normals light the surface)')
    ambient_only = expected_lum((0.8 * 0.96 + 0.04,) * 3)
    h.report.check(
        'normal_fade_flattens', abs(lums['faded'] - ambient_only) < 0.03,
        f'forced fade renders ambient-only {lums["faded"]:.3f} expected '
        f'{ambient_only:.3f} (detail normals gone past fade_end)')

    # --- Phase 7: opt-out restores the untouched card -------------------
    pipeline.clear_terrain_splat(card)
    card.set_material(mat_metal, 1)
    h.adapter.update_sun((1, 0, 0), (0, 0, 0))
    h.step(5)
    img_restored = h.capture()
    rms = common.image_rms_diff(img_bare, img_restored, step=1)
    h.report.check('opt_out_restores', rms == 0.0,
                   f'clear_terrain_splat(): rms vs untouched baseline = '
                   f'{rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
