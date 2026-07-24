"""paxtest: wet-sand waterline (ER-010, pipeline.set_terrain_water).

The TERRAIN_WATER rider on the terrain-splat variant renders fragments
below `water_z` + band WET: darker, more saturated albedo and much
lower roughness (the retreating-wave sheen is a specular read).
Wetness is by WORLD Z only — all splat layers alike — and applies
below the waterline too (the game's depth-alpha shallows make the
seafloor visible; it must not read bone-dry). Every consumer applies
its change through mix(dry, wet, w), so wet == 0 fragments compute the
water-off arithmetic exactly; unset nodes keep the water-free shader
variant — byte-identical to today by construction.

Analytic setup (the test_terrain_splat pattern): an ortho camera over
a card spanning world z in [-1, 1]; metallic=1/roughness=1 material
collapses the ambient term to base_color * A exactly (diffuse=0,
spec=base_color, IBL zero, sun black) — a pixel at height z IS
curve(wet_mix(sand, wet(z)) * A). The camera is pulled back to
y = -10 so n_dot_v ~ 1 for the env-BRDF sheen phase (on the card
plane it would be ~0 — the LUT corner).

Checks, in order:
  1.  dry_sanity: the splat-only card renders curve(sand * A).
  2.  wet_full_analytic: water_z above the whole card -> every pixel
      is the exact wet transform (dark multiplier + chroma expansion
      about Rec.709 luminance, then mix by wet=1).
  3.  wet_below_waterline: THE seafloor contract — z = -0.5 under a
      water_z=0 line renders fully wet (not bone-dry).
  4.  band_mid_analytic: at z = band/2 the smoothstep gives wet=0.5
      exactly -> the half-mixed analytic color.
  5.  band_dry_above: the region above water_z + band matches the
      water-OFF render to rms < 1e-4 (wet==0 arithmetic identity,
      across shader variants).
  6.  redress_preserves_water: re-calling set_terrain_splat on the
      node keeps the water contract byte-identically (chunk
      re-dressing must not silently dry the shore).
  7.  wet_sheen_brighter: under a constant white env cube (specular
      IBL), rough_mult 0.12 renders the submerged region brighter
      than rough_mult 1.0 — the roughness lever reaches the specular
      read (env-BRDF rises as roughness falls at n_dot_v ~ 1).
  8.  sheen_dry_region_exact: those two configs differ ONLY in a
      uniform; above the band they are byte-identical (wet==0 makes
      the uniform unreachable).
  9.  anim_amp0_exact: anim_amp=0 with a nonzero pinned phase is
      byte-identical to the static band (edge + 0.0*noise == edge).
  10. anim_phase_live: pinned phase 0 vs pi move the breathing edge
      (images differ in the band).
  11. anim_above_reach_exact: above water_z + band + amp both phases
      are byte-identical to the static band (wet==0 everywhere the
      edge can reach).
  12. anim_deep_below_exact: below water_z - amp likewise (wet==1
      saturates — the deep seafloor never flickers).
  13. anim_shore_variation: at the waterline the breathing edge
      varies ALONG the shore (world-xy value noise phase-shifts the
      cycle) — per-column luminance spread at z=0.
  14. water_none_clears: set_terrain_water(np, None) restores the
      water-free render byte-identically.
  15. water_clear_restores: clear_terrain_water() ditto.
  16. water_requires_splat: calling set_terrain_water on a node with
      no splat config raises ValueError (API contract).
  17. opt_out_restores: clear_terrain_splat() restores the untouched
      card byte-identically (rms == 0).

The directional-sun variant run (run.py) re-runs everything with
sun_light_mode='directional' — the game's shipping sun mode.

Only meaningful for pax3d_render (set_terrain_water lives there).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

AMBIENT = 0.6
C_SAND = (0.8, 0.6, 0.4)     # exact byte values (204/153/102)
DARK = 0.55
SAT = 1.25
BAND = 0.5
CURVE = common.CURVES['hejl_dawson']


def solid_image(size, rgb):
    img = p3d.PNMImage(size, size, 3)
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


def make_splat_l0(name):
    """Uniform layer-0 splat (2x2, all-red texels)."""
    img = p3d.PNMImage(2, 2, 4)
    for x, y in ((0, 0), (1, 0), (0, 1), (1, 1)):
        img.set_xel_val(x, y, 255, 0, 0)
        img.set_alpha_val(x, y, 0)
    tex = p3d.Texture(name)
    tex.load(img)
    tex.set_wrap_u(p3d.SamplerState.WM_clamp)
    tex.set_wrap_v(p3d.SamplerState.WM_clamp)
    return tex


def make_white_cube(size=4):
    """Constant white float cubemap (every face, single mip chain)."""
    tex = p3d.Texture('paxtest_water_env')
    tex.setup_cube_map(size, p3d.Texture.T_float, p3d.Texture.F_rgb32)
    for n in range(int(math.log2(size)) + 1):
        msize = size >> n
        img = p3d.PNMImage(msize, msize, 3)
        img.fill(1.0, 1.0, 1.0)
        for face in range(6):
            tex.load(img, face, n)
    tex.set_minfilter(p3d.SamplerState.FT_linear_mipmap_linear)
    tex.set_magfilter(p3d.SamplerState.FT_linear)
    return tex


def wet_mix(rgb, wet, dark=DARK, sat=SAT):
    """The shader's wet-albedo transform, exactly: dark multiplier,
    chroma expansion about Rec.709 luminance (clamped at 0), then
    mix(dry, wet_rgb, wet)."""
    wr = [c * dark for c in rgb]
    wl = 0.2126 * wr[0] + 0.7152 * wr[1] + 0.0722 * wr[2]
    wr = [max(0.0, wl + (c - wl) * sat) for c in wr]
    return [rgb[i] + (wr[i] - rgb[i]) * wet for i in range(3)]


def expected_lum(rgb, ambient=AMBIENT):
    return sum(CURVE(c * ambient) for c in rgb) / 3.0


def region_rms(a, b, y0, y1, step=2):
    """rms luminance diff restricted to pixel rows [y0, y1)."""
    total, n = 0.0, 0
    for yy in range(y0, y1, step):
        for xx in range(0, a.get_x_size(), step):
            d = common.lum_at(a, xx, yy) - common.lum_at(b, xx, yy)
            total += d * d
            n += 1
    return (total / n) ** 0.5 if n else 0.0


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default='uniforms')
    args = parser.parse_args()

    h = common.Harness(args, 'terrain_water')
    if args.pipeline != 'pax3d_render':
        h.report.skip('set_terrain_water lives in pax3d_render (ER-010)')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode)
    pipeline = h.adapter.pipeline
    if not hasattr(pipeline, 'set_terrain_water'):
        h.report.skip('pipeline has no set_terrain_water (ER-010)')
    if common.PAX3D_ROOT not in sys.path:
        sys.path.insert(0, common.PAX3D_ROOT)
    from pax3d_render import data_texture

    base = h.base
    h.set_ortho(film_h=2.0)
    # Pull the camera off the card plane: n_dot_v ~ 1 (0.995) for the
    # env-BRDF sheen phase. Ambient analytics are view-independent.
    base.cam.set_pos(0, -10, 0)

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMBIENT, AMBIENT, AMBIENT, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((1, 0, 0), (0, 0, 0))  # sun black throughout

    cm = p3d.CardMaker('shore_card')
    cm.set_frame(-1, 1, -1, 1)          # world z spans [-1, 1]
    card = base.render.attach_new_node(cm.generate())
    card.set_two_sided(True)
    mat_metal = p3d.Material('metal1')
    mat_metal.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat_metal.set_metallic(1.0)
    mat_metal.set_roughness(1.0)
    card.set_material(mat_metal, 1)

    def px(fx, fy):
        return (int((fx / 2.0 + 0.5) * h.win_w),
                int((0.5 - fy / 2.0) * h.win_h))

    def y_of(fz):
        return int((0.5 - fz / 2.0) * h.win_h)

    cx, cy = px(0.0, 0.0)

    # --- Phase 0: untouched baseline for the opt-out check --------------
    h.step(5)
    img_bare = h.capture()

    # --- Phase 1: splat only (the dry shore) ----------------------------
    albedo = make_albedo_array([C_SAND, (0, 0, 0), (0, 0, 0), (0, 0, 0)],
                               'albedo_sand')
    splat_l0 = data_texture(make_splat_l0('splat_l0'))
    pipeline.set_terrain_splat(card, albedo, splat_l0)
    h.step(5)
    img_dry = h.capture()
    got = common.avg_lum(img_dry, cx, cy)
    want = expected_lum(C_SAND)
    h.report.check('dry_sanity', abs(got - want) < 0.02,
                   f'lum={got:.3f} expected {want:.3f} (dry sand)')

    # --- Phase 2: fully submerged (water above the whole card) ----------
    pipeline.set_terrain_water(card, 2.0, band_m=BAND)
    h.step(5)
    img = h.capture()
    got = common.avg_lum(img, cx, cy)
    want = expected_lum(wet_mix(C_SAND, 1.0))
    h.report.check('wet_full_analytic', abs(got - want) < 0.02,
                   f'lum={got:.3f} expected {want:.3f} '
                   f'(dark {DARK} + sat {SAT}, wet=1)')

    # --- Phase 3: the shore band (water_z = 0) --------------------------
    pipeline.set_terrain_water(card, 0.0, band_m=BAND)
    h.step(5)
    img_band = h.capture()
    h.save_capture(img_band, 'shore_band')

    x, y = px(0.0, -0.5)
    got = common.avg_lum(img_band, x, y)
    want = expected_lum(wet_mix(C_SAND, 1.0))
    h.report.check('wet_below_waterline', abs(got - want) < 0.02,
                   f'z=-0.5 under water_z=0: lum={got:.3f} expected '
                   f'{want:.3f} (the seafloor reads WET, not dry)')

    x, y = px(0.0, BAND / 2.0)
    got = common.avg_lum(img_band, x, y)
    want = expected_lum(wet_mix(C_SAND, 0.5))
    h.report.check('band_mid_analytic', abs(got - want) < 0.02,
                   f'z=band/2: lum={got:.3f} expected {want:.3f} '
                   f'(smoothstep midpoint, wet=0.5)')

    rms = region_rms(img_band, img_dry, 0, y_of(BAND + 0.1))
    h.report.check('band_dry_above', rms < 1e-4,
                   f'region z>{BAND + 0.1}: rms vs water-off = {rms:.2e} '
                   f'(wet==0 computes the dry arithmetic)')

    # --- Phase 4: chunk re-dress preserves the contract -----------------
    pipeline.set_terrain_splat(card, albedo, splat_l0)
    h.step(5)
    img = h.capture()
    rms = common.image_rms_diff(img_band, img, step=1)
    h.report.check('redress_preserves_water', rms == 0.0,
                   f'set_terrain_splat re-call: rms vs shore band = '
                   f'{rms:.2e} (re-dressing keeps the water)')

    # --- Phase 5: the sheen — rough_mult reaches the specular read ------
    # Constant white env cube: ibl_spec = white * (F*brdf.x + brdf.y) at
    # n_dot_v ~ 1; as wet roughness falls the env-BRDF rises steeply, so
    # the submerged half brightens. dark/sat pinned at 1.0 in BOTH
    # configs — the roughness uniform is the only difference.
    env = make_white_cube()
    pipeline.set_env_map(env)
    lums = {}
    imgs = {}
    for rough_mult, tag in ((1.0, 'r100'), (0.12, 'r012')):
        pipeline.set_terrain_water(card, 0.0, band_m=BAND, dark=1.0,
                                   rough_mult=rough_mult, sat=1.0)
        h.step(5)
        imgs[tag] = h.capture()
        x, y = px(0.0, -0.5)
        lums[tag] = common.avg_lum(imgs[tag], x, y)
    h.save_capture(imgs['r012'], 'sheen')
    h.report.check('wet_sheen_brighter',
                   lums['r012'] > lums['r100'] + 0.05,
                   f'white env, z=-0.5: rough_mult 0.12 lum='
                   f'{lums["r012"]:.3f} vs 1.0 lum={lums["r100"]:.3f} '
                   f'(the sheen is a specular read)')
    rms = region_rms(imgs['r100'], imgs['r012'], 0, y_of(BAND + 0.1))
    h.report.check('sheen_dry_region_exact', rms == 0.0,
                   f'same compile, only the uniform differs: dry-region '
                   f'rms = {rms:.2e} (wet==0 never reads it)')
    pipeline.clear_env_map()

    # --- Phase 6: the breathing edge (pinned-phase determinism) ---------
    AMP = 0.3
    pipeline.set_terrain_water(card, 0.0, band_m=BAND, anim_amp=0.0,
                               anim_phase=1.234)
    h.step(5)
    img = h.capture()
    rms = common.image_rms_diff(img_band, img, step=1)
    h.report.check('anim_amp0_exact', rms == 0.0,
                   f'amp=0, phase pinned nonzero: rms vs static band = '
                   f'{rms:.2e} (edge + 0.0*noise == edge)')

    for phase, tag in ((0.0, 'p0'), (math.pi, 'ppi')):
        pipeline.set_terrain_water(card, 0.0, band_m=BAND, anim_amp=AMP,
                                   anim_scale=0.5, anim_phase=phase)
        h.step(5)
        imgs[tag] = h.capture()
    h.save_capture(imgs['p0'], 'breathing')
    rms = common.image_rms_diff(imgs['p0'], imgs['ppi'], step=1)
    h.report.check('anim_phase_live', rms > 0.01,
                   f'phase 0 vs pi: rms={rms:.4f} (the edge breathes)')

    top = y_of(BAND + AMP + 0.1)
    rms = max(region_rms(imgs['p0'], img_band, 0, top),
              region_rms(imgs['ppi'], img_band, 0, top))
    h.report.check('anim_above_reach_exact', rms == 0.0,
                   f'region z>{BAND + AMP + 0.1}: worst rms vs static = '
                   f'{rms:.2e} (beyond the edge reach, wet==0 exact)')

    deep = y_of(-(AMP + 0.1))
    rms = max(region_rms(imgs['p0'], img_band, deep, h.win_h),
              region_rms(imgs['ppi'], img_band, deep, h.win_h))
    h.report.check('anim_deep_below_exact', rms == 0.0,
                   f'region z<-{AMP + 0.1}: worst rms vs static = '
                   f'{rms:.2e} (the deep seafloor never flickers)')

    yrow = y_of(0.0)
    cols = [common.avg_lum(imgs['p0'], xx, yrow, half=1)
            for xx in range(24, h.win_w - 24, 32)]
    spread = max(cols) - min(cols)
    h.report.check('anim_shore_variation', spread > 0.02,
                   f'z=0 per-column lum spread={spread:.3f} '
                   f'(the edge varies ALONG the shore)')

    # --- Phase 7: opt-outs and the API contract -------------------------
    pipeline.set_terrain_water(card, None)
    h.step(5)
    img = h.capture()
    rms = common.image_rms_diff(img_dry, img, step=1)
    h.report.check('water_none_clears', rms == 0.0,
                   f'water_z=None: rms vs dry = {rms:.2e} '
                   f'(byte-identical clear)')

    pipeline.set_terrain_water(card, 0.0, band_m=BAND)
    h.step(5)
    pipeline.clear_terrain_water(card)
    h.step(5)
    img = h.capture()
    rms = common.image_rms_diff(img_dry, img, step=1)
    h.report.check('water_clear_restores', rms == 0.0,
                   f'clear_terrain_water(): rms vs dry = {rms:.2e} '
                   f'(byte-identical clear)')

    bare_np = base.render.attach_new_node('no_splat')
    raised = False
    try:
        pipeline.set_terrain_water(bare_np, 0.0)
    except ValueError:
        raised = True
    bare_np.remove_node()
    h.report.check('water_requires_splat', raised,
                   'set_terrain_water without set_terrain_splat raises '
                   'ValueError (API contract)')

    pipeline.clear_terrain_splat(card)
    h.step(5)
    img_restored = h.capture()
    rms = common.image_rms_diff(img_bare, img_restored, step=1)
    h.report.check('opt_out_restores', rms == 0.0,
                   f'clear_terrain_splat(): rms vs untouched baseline = '
                   f'{rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
