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
  8. Hex-tiling uniform invariant (ER-007): solid-color layers render
     the SAME quadrant analytics with hex_tiling=True — any blend of
     identical samples with weights summing to 1 is that color (pins
     hex weight normalization exactly).
  9. Hex breaks periodicity: a patterned layer tiled plain is exactly
     self-similar under a one-period pixel shift; hex-tiled it is not.
     Mean luminance is preserved (stochastic resampling of the same
     tile).
 10. Hex rotation semantics: vertical stripes with per-layer
     rotation=0 keep gradients x-dominant (anisotropy preserved for
     directional sets); rotation=1 mixes gradient directions.
 11. Hex normals: a uniform tilted normal map with rotation=0 renders
     identically to hex-off (offset-only taps of a uniform map are the
     map); rotation=1 changes the render (per-cell back-rotation of
     the sampled tangent-space normal is live).
 12. Hex opt-out: clear_terrain_splat() after hex restores the
     untouched capture byte-identically.
 13. RGBA albedo array carry (the height8-in-albedo.a intake,
     2026-07-21): WITHOUT height_blend, alpha in the array changes
     nothing — the quadrant analytics reproduce exactly (the terrain
     dev's selftest result, engine-gated).
 14. THE all-flat contract (ER-007 height rider): every slice at flat
     alpha 128 + height_blend=True renders the plain splat weights —
     equal heights cancel as a common factor of the softmax renorm, so
     an all-flat palette (Deep Desert) is a visual no-op by
     construction, not by tuning.
 15. Softmax analytics: two layers at 50/50 splat with h=1.0 vs h=0.0
     at k=4 render exactly the 2^4:1 reweighted blend; sharpness=0 is
     inert (plain 50/50); a flat-128 slice against h=1.0 at k=8
     competes at its constant middle height (the beach-sand case).
 16. Height blend composes with hex tiling: solid slices with distinct
     constant alphas reproduce the same softmax analytic through the
     3-tap hex path (terrain_layer_sample's hex branch).
 17. hex_offset world-anchor (the chunk-border motif seam): a nonzero
     offset reseeds the lattice (image changes), and shifting the MESH
     UV window by delta equals shifting hex_offset by delta — cell ids
     depend only on base_uv + hex_offset, so chunks passing their
     world offset get a border-seamless motif.
 18. Height/offset opt-out: clear_terrain_splat() restores the
     untouched capture byte-identically (the new uniforms clear).

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


def make_rgba_array(layer_colors, alphas, name):
    """RGBA8 array: solid color slices with per-layer constant alpha
    (the height8-in-albedo.a intake shape; alpha bytes stay exact)."""
    tex = p3d.Texture(name)
    tex.setup_2d_texture_array(4, 4, len(layer_colors),
                               p3d.Texture.T_unsigned_byte,
                               p3d.Texture.F_rgba8)
    for z, (rgb, a) in enumerate(zip(layer_colors, alphas)):
        img = p3d.PNMImage(4, 4, 4)
        img.fill(*rgb)
        img.alpha_fill(a)
        tex.load(img, z, 0)
    tex.set_minfilter(p3d.SamplerState.FT_nearest)
    tex.set_magfilter(p3d.SamplerState.FT_nearest)
    return tex


def softmax_pair(w0, w1, h0, h1, k):
    """The shader's height softmax for a two-layer blend: w_i * 2^(k*h_i),
    renormalized."""
    f0 = w0 * 2.0 ** (k * h0)
    f1 = w1 * 2.0 ** (k * h1)
    return f0 / (f0 + f1), f1 / (f0 + f1)


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

    # ==== ER-007: hex-tiling phases =====================================

    def shift_rms(img, dx, x0=64, x1=416, y0=64, y1=448, step=4):
        """rms of lum(x, y) vs lum(x+dx, y) over the central region —
        ~0 for an image that is exactly dx-periodic in x."""
        total, count = 0.0, 0
        for yy in range(y0, y1, step):
            for xx in range(x0, x1, step):
                d = common.lum_at(img, xx, yy) - common.lum_at(
                    img, xx + dx, yy)
                total += d * d
                count += 1
        return (total / count) ** 0.5

    def grad_aniso(img, x0=64, x1=448, y0=64, y1=448, step=2):
        """(sum |dL/dy|) / (sum |dL/dx|) over the central region."""
        sx, sy = 0.0, 0.0
        for yy in range(y0, y1, step):
            for xx in range(x0, x1, step):
                l0 = common.lum_at(img, xx, yy)
                sx += abs(common.lum_at(img, xx + 1, yy) - l0)
                sy += abs(common.lum_at(img, xx, yy + 1) - l0)
        return sy / max(sx, 1e-9)

    def mean_lum(img, x0=64, x1=448, y0=64, y1=448, step=4):
        total, count = 0.0, 0
        for yy in range(y0, y1, step):
            for xx in range(x0, x1, step):
                total += common.lum_at(img, xx, yy)
                count += 1
        return total / count

    # --- Phase 8: hex uniform invariant ---------------------------------
    # Solid-color layers: every hex tap reads the same texel, so the
    # blend must reproduce phase 1's analytics exactly — this pins the
    # sharpened weights renormalizing to 1 through the whole hex path.
    pipeline.set_terrain_splat(card, albedo, splat_quad,
                               hex_tiling=True, hex_cell_size=2.0)
    h.step(5)
    img = h.capture()
    for tag, ((fx, fy), rgb) in QUADS.items():
        x, y = px(fx, fy)
        got = common.avg_lum(img, x, y)
        want = expected_lum(rgb)
        h.report.check(f'hex_{tag}', abs(got - want) < 0.02,
                       f'lum={got:.3f} expected {want:.3f} '
                       f'(uniform layers: hex == plain)')

    # --- Phase 9: hex breaks periodicity, preserves the mean ------------
    # Asymmetric 4x4 gray tile on layer 0, uv_scale 16 -> the plain
    # render repeats every 32 px exactly (nearest filter, ortho 1:1).
    pat_img = p3d.PNMImage(4, 4, 3)
    pat_vals = (0.9, 0.6, 0.15, 0.75, 0.3, 0.85, 0.5, 0.05,
                0.7, 0.2, 0.95, 0.4, 0.1, 0.55, 0.25, 0.8)
    for i, v in enumerate(pat_vals):
        pat_img.set_xel(i % 4, i // 4, v, v, v)
    pat_array = p3d.Texture('albedo_pattern')
    pat_array.setup_2d_texture_array(4, 4, 4, p3d.Texture.T_unsigned_byte,
                                     p3d.Texture.F_rgb8)
    pat_array.load(pat_img, 0, 0)
    for z in range(1, 4):
        pat_array.load(solid_image(4, (0, 0, 0)), z, 0)
    pat_array.set_minfilter(p3d.SamplerState.FT_nearest)
    pat_array.set_magfilter(p3d.SamplerState.FT_nearest)

    pipeline.set_terrain_splat(card, pat_array, splat_l0,
                               uv_scales=(16, 1, 1, 1))
    h.step(5)
    img_plain = h.capture()
    pipeline.set_terrain_splat(card, pat_array, splat_l0,
                               uv_scales=(16, 1, 1, 1),
                               hex_tiling=True, hex_cell_size=2.0)
    h.step(5)
    img_hex = h.capture()
    h.save_capture(img_hex, 'hex_pattern')

    srms_plain = shift_rms(img_plain, 32)
    srms_hex = shift_rms(img_hex, 32)
    h.report.check('hex_plain_is_periodic', srms_plain < 0.005,
                   f'plain tiling one-period shift rms={srms_plain:.4f} '
                   f'(exactly self-similar)')
    h.report.check('hex_breaks_periodicity',
                   srms_hex > max(0.05, 10.0 * srms_plain),
                   f'hex one-period shift rms={srms_hex:.4f} vs plain '
                   f'{srms_plain:.4f} (motif repetition broken)')
    m_plain = mean_lum(img_plain)
    m_hex = mean_lum(img_hex)
    h.report.check('hex_preserves_mean', abs(m_hex - m_plain) < 0.03,
                   f'mean lum hex={m_hex:.3f} plain={m_plain:.3f} '
                   f'(stochastic resample of the same tile)')

    # --- Phase 10: rotation semantics (per-layer contract) --------------
    # Vertical stripes: 2 bright / 2 dark columns -> 16-px bands.
    stripe_img = p3d.PNMImage(4, 4, 3)
    for xx in range(4):
        v = 0.8 if xx < 2 else 0.0
        for yy in range(4):
            stripe_img.set_xel(xx, yy, v, v, v)
    stripe_array = p3d.Texture('albedo_stripes')
    stripe_array.setup_2d_texture_array(4, 4, 4,
                                        p3d.Texture.T_unsigned_byte,
                                        p3d.Texture.F_rgb8)
    stripe_array.load(stripe_img, 0, 0)
    for z in range(1, 4):
        stripe_array.load(solid_image(4, (0, 0, 0)), z, 0)
    stripe_array.set_minfilter(p3d.SamplerState.FT_nearest)
    stripe_array.set_magfilter(p3d.SamplerState.FT_nearest)

    ratios = {}
    for rot, tag in ((0.0, 'rot0'), (1.0, 'rot1')):
        pipeline.set_terrain_splat(card, stripe_array, splat_l0,
                                   uv_scales=(16, 1, 1, 1),
                                   hex_tiling=True, hex_cell_size=2.0,
                                   hex_rotation=rot)
        h.step(5)
        ratios[tag] = grad_aniso(h.capture())
    h.report.check('hex_rotation_off_keeps_anisotropy',
                   ratios['rot0'] < 0.4,
                   f'rotation=0: |dy|/|dx|={ratios["rot0"]:.3f} '
                   f'(stripes stay axis-aligned; offsets only)')
    h.report.check('hex_rotation_mixes_directions',
                   ratios['rot1'] > max(0.6, 2.0 * ratios['rot0']),
                   f'rotation=1: |dy|/|dx|={ratios["rot1"]:.3f} vs rot0 '
                   f'{ratios["rot0"]:.3f} (random rotation live)')

    # --- Phase 11: hex normals (back-rotation contract) -----------------
    card.set_material(mat_diel, 1)
    h.adapter.update_sun((1, 0, 0), (2.0, 2.0, 2.0))
    imgs = {}
    for tag, kwargs in (
            ('off', {}),
            ('hex_r0', {'hex_tiling': True, 'hex_cell_size': 2.0,
                        'hex_rotation': 0.0}),
            ('hex_r1', {'hex_tiling': True, 'hex_cell_size': 2.0,
                        'hex_rotation': 1.0})):
        pipeline.set_terrain_splat(card, white_array, splat_l0,
                                   normal_array=norm_array,
                                   normal_fade=(1e6, 2e6), **kwargs)
        h.step(5)
        imgs[tag] = h.capture()
    lum_off = common.avg_lum(imgs['off'], cx, cy)
    lum_r0 = common.avg_lum(imgs['hex_r0'], cx, cy)
    h.report.check('hex_normals_r0_matches_plain',
                   abs(lum_r0 - lum_off) < 0.01,
                   f'uniform tilted normal, rotation=0: lum={lum_r0:.3f} '
                   f'vs plain {lum_off:.3f} (offset taps of a uniform '
                   f'map are the map)')
    rms_rot = common.image_rms_diff(imgs['hex_r0'], imgs['hex_r1'],
                                    step=1)
    h.report.check('hex_normals_backrotation_live', rms_rot > 0.02,
                   f'rotation=1 vs rotation=0 rms={rms_rot:.4f} '
                   f'(sampled normals rotate with the motif)')

    # --- Phase 12: hex opt-out ------------------------------------------
    pipeline.clear_terrain_splat(card)
    card.set_material(mat_metal, 1)
    h.adapter.update_sun((1, 0, 0), (0, 0, 0))
    h.step(5)
    img_restored = h.capture()
    rms = common.image_rms_diff(img_bare, img_restored, step=1)
    h.report.check('hex_opt_out_restores', rms == 0.0,
                   f'clear after hex: rms vs untouched baseline = '
                   f'{rms:.2e} (byte-identical opt-out)')

    # ==== ER-007 rider: height-blend sharpening + hex_offset ============
    FLAT128 = 128.0 / 255.0

    # --- Phase 13: RGBA array carry (no kwarg = alpha inert) ------------
    # Distinct per-layer alphas, height_blend OFF: the render must
    # reproduce phase 1's quadrant analytics exactly — alpha is carried
    # by the array without disturbing RGB (the intake's F_srgb_alpha
    # upload contract measured engine-side).
    rgba_varied = make_rgba_array(
        LAYERS, (1.0, 0.0, FLAT128, 1.0), 'albedo_rgba_varied')
    pipeline.set_terrain_splat(card, rgba_varied, splat_quad)
    h.step(5)
    img = h.capture()
    for tag, ((fx, fy), rgb) in QUADS.items():
        x, y = px(fx, fy)
        got = common.avg_lum(img, x, y)
        want = expected_lum(rgb)
        h.report.check(f'rgba_{tag}', abs(got - want) < 0.02,
                       f'lum={got:.3f} expected {want:.3f} '
                       f'(RGBA array, height_blend off: alpha inert)')

    # --- Phase 14: THE all-flat contract --------------------------------
    # Every slice flat 128 (the Deep Desert census): height_blend=True
    # must be a visual no-op — the softmax factors are a COMMON FACTOR
    # of the renormalization. One-hot splat texels cancel exactly
    # (w*f/f == w in IEEE); blend zones can wiggle by an 8-bit LSB at
    # most, so the whole-image rms is pinned tiny.
    rgba_flat = make_rgba_array(
        LAYERS, (FLAT128,) * 4, 'albedo_rgba_flat')
    pipeline.set_terrain_splat(card, rgba_flat, splat_quad)
    h.step(5)
    img_flat_off = h.capture()
    pipeline.set_terrain_splat(card, rgba_flat, splat_quad,
                               height_blend=True, height_sharpness=8.0)
    h.step(5)
    img_flat_on = h.capture()
    rms = common.image_rms_diff(img_flat_off, img_flat_on, step=1)
    h.report.check('height_allflat_noop', rms < 1e-3,
                   f'all-flat palette, k=8 on vs off: rms={rms:.2e} '
                   f'(equal heights cancel — dune cannot shift)')
    x, y = px(-0.5, 0.5)
    d_quad = abs(common.avg_lum(img_flat_on, x, y)
                 - common.avg_lum(img_flat_off, x, y))
    h.report.check('height_allflat_onehot_exact', d_quad < 0.005,
                   f'one-hot quadrant delta={d_quad:.4f} '
                   f'(w*f/f == w exactly)')

    # --- Phase 15: softmax analytics ------------------------------------
    # Layer 0 h=1.0 vs layer 1 h=0.0 at a 50/50 splat (the renorm
    # texture): k=4 reweights 2^4:1 -> (0.9412, 0.0588).
    rgba_steep = make_rgba_array(
        LAYERS, (1.0, 0.0, 0.0, 0.0), 'albedo_rgba_steep')
    k = 4.0
    w0p, w1p = softmax_pair(0.5, 0.5, 1.0, 0.0, k)
    pipeline.set_terrain_splat(card, rgba_steep, splat_dim,
                               height_blend=True, height_sharpness=k)
    h.step(5)
    img = h.capture()
    h.save_capture(img, 'height_softmax')
    got = common.avg_lum(img, cx, cy)
    mix_rgb = [w0p * C0[i] + w1p * C1[i] for i in range(3)]
    want = expected_lum(mix_rgb)
    h.report.check('height_softmax_analytic', abs(got - want) < 0.02,
                   f'k={k:g}, h=1 vs h=0 at 50/50: lum={got:.3f} '
                   f'expected {want:.3f} (weights {w0p:.4f}/{w1p:.4f})')

    pipeline.set_terrain_splat(card, rgba_steep, splat_dim,
                               height_blend=True, height_sharpness=0.0)
    h.step(5)
    got = common.avg_lum(h.capture(), cx, cy)
    half_rgb = [(C0[i] + C1[i]) / 2.0 for i in range(3)]
    want = expected_lum(half_rgb)
    h.report.check('height_sharp0_inert', abs(got - want) < 0.02,
                   f'sharpness=0: lum={got:.3f} expected {want:.3f} '
                   f'(kwarg live, softmax inert)')

    # The beach-sand case: flat-128 slice against a real h=1.0 layer at
    # k=8 — the flat slice competes at its constant 0.5, it does not
    # vanish (h=0 would give weight 1/257; 0.5 gives ~1/17).
    rgba_beach = make_rgba_array(
        LAYERS, (1.0, FLAT128, 0.0, 0.0), 'albedo_rgba_beach')
    kb = 8.0
    w0b, w1b = softmax_pair(0.5, 0.5, 1.0, FLAT128, kb)
    pipeline.set_terrain_splat(card, rgba_beach, splat_dim,
                               height_blend=True, height_sharpness=kb)
    h.step(5)
    got = common.avg_lum(h.capture(), cx, cy)
    mix_rgb = [w0b * C0[i] + w1b * C1[i] for i in range(3)]
    want = expected_lum(mix_rgb)
    h.report.check('height_flat128_competes', abs(got - want) < 0.02,
                   f'k={kb:g}, h=1 vs flat-128 at 50/50: lum={got:.3f} '
                   f'expected {want:.3f} (weights {w0b:.4f}/{w1b:.4f})')

    # --- Phase 16: height blend through the hex path --------------------
    # Solid slices: every hex tap reads the same texel, so the 3-tap
    # per-layer sample (terrain_layer_sample's hex branch) must land on
    # the same softmax analytic as the plain path.
    pipeline.set_terrain_splat(card, rgba_steep, splat_dim,
                               hex_tiling=True, hex_cell_size=2.0,
                               height_blend=True, height_sharpness=k)
    h.step(5)
    got = common.avg_lum(h.capture(), cx, cy)
    mix_rgb = [w0p * C0[i] + w1p * C1[i] for i in range(3)]
    want = expected_lum(mix_rgb)
    h.report.check('height_hex_uniform_analytic', abs(got - want) < 0.02,
                   f'hex + height, k={k:g}: lum={got:.3f} expected '
                   f'{want:.3f} (uniform slices: hex == plain)')

    # --- Phase 17: hex_offset (chunk-border world anchor) ---------------
    # (a) A nonzero offset reseeds the cell hash: the motif changes.
    pipeline.set_terrain_splat(card, pat_array, splat_l0,
                               uv_scales=(16, 1, 1, 1),
                               hex_tiling=True, hex_cell_size=2.0)
    h.step(5)
    img_off0 = h.capture()
    pipeline.set_terrain_splat(card, pat_array, splat_l0,
                               uv_scales=(16, 1, 1, 1),
                               hex_tiling=True, hex_cell_size=2.0,
                               hex_offset=(5.0, 3.0))
    h.step(5)
    img_off53 = h.capture()
    rms = common.image_rms_diff(img_off0, img_off53, step=1)
    h.report.check('hexoff_reseeds_lattice', rms > 0.02,
                   f'hex_offset (5,3) vs (0,0): rms={rms:.4f} '
                   f'(hash input moved — the seam mechanism is live)')
    m0, m53 = mean_lum(img_off0), mean_lum(img_off53)
    h.report.check('hexoff_preserves_mean', abs(m0 - m53) < 0.03,
                   f'mean lum {m0:.3f} vs {m53:.3f} (same stochastic '
                   f'resample statistics)')

    # (b) THE anchor contract: shifting the MESH UV window by delta ==
    # shifting hex_offset by delta. Card B carries base UVs 1.37..2.37
    # with offset (0,0); card A carries 0..1 with offset (1.37, 0) —
    # identical images up to varying-interpolation ulps (nearest-filter
    # texel flips on isolated pixels), so a chunk grid passing its
    # world offset renders one continuous world-anchored motif.
    DELTA = 1.37
    pipeline.set_terrain_splat(card, pat_array, splat_l0,
                               uv_scales=(16, 1, 1, 1),
                               hex_tiling=True, hex_cell_size=2.0,
                               hex_offset=(DELTA, 0.0))
    h.step(5)
    img_a = h.capture()
    pipeline.clear_terrain_splat(card)
    card.stash()
    cmb = p3d.CardMaker('terrain_card_b')
    cmb.set_frame(-1, 1, -1, 1)
    cmb.set_uv_range(p3d.LTexCoord(DELTA, 0.0),
                     p3d.LTexCoord(DELTA + 1.0, 1.0))
    card_b = base.render.attach_new_node(cmb.generate())
    card_b.set_two_sided(True)
    card_b.set_material(mat_metal, 1)
    pipeline.set_terrain_splat(card_b, pat_array, splat_l0,
                               uv_scales=(16, 1, 1, 1),
                               hex_tiling=True, hex_cell_size=2.0)
    h.step(5)
    img_b = h.capture()
    h.save_capture(img_b, 'hexoff_anchor')
    rms = common.image_rms_diff(img_a, img_b, step=1)
    h.report.check('hexoff_world_anchor', rms < 0.01,
                   f'UV window +{DELTA} w/ offset 0 vs UV 0..1 w/ '
                   f'offset {DELTA}: rms={rms:.4f} (cell ids anchor to '
                   f'base_uv + hex_offset — chunk borders seamless)')
    pipeline.clear_terrain_splat(card_b)
    card_b.remove_node()
    card.unstash()

    # --- Phase 18: height/offset opt-out --------------------------------
    pipeline.clear_terrain_splat(card)
    h.step(5)
    img_restored = h.capture()
    rms = common.image_rms_diff(img_bare, img_restored, step=1)
    h.report.check('height_opt_out_restores', rms == 0.0,
                   f'clear after height+hex_offset: rms vs untouched '
                   f'baseline = {rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
