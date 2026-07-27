"""paxtest: engine water surface (pax3d_render/water.py, voxel-lane ask
2026-07-28 — the planetside/paxcraft shared water promoted engine-side).

The module owns the Gerstner follow-grid + shader pair; the GAME owns
seafloor depth (provider contract: R32F world-z texture + window via
set_seafloor, uncovered policy 'deep'|'dry'), the per-frame drive and
the day-night feed.  Two port findings are folded in for every
consumer: the ENGINE-analytic aerial haze (exact pax_pbr.frag block —
water and terrain haze as one system) and the HDR-sun luminance knee
(water_sun).

Analytic strategy: the fragment stage is full of non-periodic noise
(normals, foam) — instead of reimplementing the noise, the checks
choose configurations where the noise terms CANCEL:
 - sun black + sky known -> body colour is Beer-Lambert exact (noise
   only wiggles the 3%-weight Fresnel mix, inside tolerance);
 - sun black + sky black -> the surface contributes NOTHING and a
   pixel IS the analytic haze inscatter (test_orbital's independent-
   evaluation pattern, per-pixel ray extrusion in Python);
 - the alpha chain's final melt multiplier makes dry/rim regions
   EXACTLY zero alpha -> byte-identical composites.

Checks, in order:
  1.  defaults_match_planetside: WaterParams defaults == the planetside
      field-tuned constants (migration honesty — adopting the engine
      module with default params must be the planetside ocean).
  2.  knee_curve: water_sun matches the filed probe points (3.3 -> 1.81,
      1.9 -> 1.29, 0.95 -> 0.77); knee=0 is the identity.
  3.  shallow_derivation: derived shallow = min(1, deep*gain + bias);
      explicit shallow_color wins.
  4.  card_sanity: the backdrop card renders its analytic colour.
  5.  dry_uncovered_exact: uncovered='dry' with no seafloor bound
      composites BYTE-IDENTICALLY over the scene (alpha exactly 0 —
      windowed coastal games render nothing outside their window).
  6.  deep_uncovered_covers: uncovered='deep' renders the analytic
      40 m open-ocean body colour (horizon-annulus games).
  7.  melt_mid_analytic: a bound seafloor at depth 1.5 m gives the
      exact Beer-Lambert body colour AND the exact 1-exp(-k d) melt
      alpha (the provider window mapping is load-bearing here).
  8.  melt_shallow_clear: depth 0.05 m melts to the backdrop (the
      waterline dissolves instead of hard-edging).
  9.  update_follow: update(x, y) re-centres the follow root.
  10. sun_knee_applied: set_environment pushes water_sun(sun_color)
      (uniform readback) — every consumer gets the knee for free.
  11. rim_fade_edge: rim_fade=True melts the outer grid rim into the
      backdrop (vertex-interpolated v_edge -> ~1e-4 alpha at the outer
      rows) while the centre stays covered.
  12. haze_analytic_side_sun: sun abeam — three pixel rows at different
      depths match insc*(1-trans) evaluated independently in Python
      (ray extrusion; exponential-height medium, the falloff term live).
  13. haze_analytic_sun_lobe: sun dead ahead — the forward-scattering
      pow(mu, sun_power) lobe matches the independent evaluation.
  14. haze_tracks_params: set_atmosphere_params changes ride the next
      update() (water haze follows the terrain's atmosphere feed).
  15. cleanup_restores: cleanup() returns the bare scene, rms == 0.

The directional-sun variant run (run.py) re-runs everything with
sun_light_mode='directional' — the game's shipping sun mode (the water
shader is self-lit; the variant proves no interference either way).

Only meaningful for pax3d_render (the water module lives there).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

AMBIENT = 0.6
C_CARD = (0.8, 0.6, 0.4)
CURVE = common.CURVES['hejl_dawson']

# The planetside ocean constants (world/water.py, field-tuned s690-s695b)
PS_DEEP = (0.04, 0.10, 0.22)
PS_ABSORB = (0.22, 0.072, 0.045)
PS_ALPHA_K = 0.32
PS_SHALLOW_GAIN = 2.4
PS_SHALLOW_BIAS = (0.02, 0.12, 0.10)


def const_floor_tex(name, floor_z):
    """1x1 R32F seafloor texture reading a constant world floor z."""
    import struct
    tex = p3d.Texture(name)
    tex.setup_2d_texture(1, 1, p3d.Texture.T_float, p3d.Texture.F_r32)
    tex.set_ram_image(struct.pack('<f', float(floor_z)))
    tex.set_wrap_u(p3d.SamplerState.WM_clamp)
    tex.set_wrap_v(p3d.SamplerState.WM_clamp)
    return tex


def mixv(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t[i] for i in range(3))


def expected_water_pixel(depth, shallow, zen, hor, card_lin, fresnel=0.03):
    """Sun-black analytic: body colour + 3% sky Fresnel, melt alpha,
    composited over the LINEAR card colour (alpha blending happens in
    the HDR buffer, before the tonemap).  Tonemapped mean luminance."""
    transmit = tuple(math.exp(-a * depth) for a in PS_ABSORB)
    body = tuple(z * 0.8 for z in zen)
    water_col = tuple(c * b for c, b in zip(mixv(PS_DEEP, shallow, transmit),
                                            body))
    sky_ref = zen  # top-down: skyH ~ 1 -> the zenith endpoint
    color = tuple(w * (1.0 - fresnel) + s * fresnel
                  for w, s in zip(water_col, sky_ref))
    alpha = 1.0 - math.exp(-depth * PS_ALPHA_K)
    alpha = alpha * (1.0 - fresnel) + 0.98 * fresnel
    t = max(0.0, min(1.0, (depth - 0.02) / 0.48))
    alpha *= t * t * (3.0 - 2.0 * t)
    out = tuple(c * alpha + k * (1.0 - alpha)
                for c, k in zip(color, card_lin))
    return sum(CURVE(c) for c in out) / 3.0


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default='uniforms')
    args = parser.parse_args()

    h = common.Harness(args, 'water')
    if args.pipeline != 'pax3d_render':
        h.report.skip('the water module lives in pax3d_render')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode,
                    extra_pipeline_kwargs={'enable_atmosphere': True})
    pipeline = h.adapter.pipeline
    if not hasattr(pipeline, 'build_water_surface'):
        h.report.skip('pipeline has no build_water_surface')
    if common.PAX3D_ROOT not in sys.path:
        sys.path.insert(0, common.PAX3D_ROOT)
    from pax3d_render.water import WaterParams, water_sun

    base = h.base
    # Ortho phases run hazeless; the haze phase sets real params later.
    pipeline.set_atmosphere_params(density=0.0)
    h.adapter.update_sun((1, 0, 0), (0, 0, 0))  # pipeline sun black

    # --- Pure-python contracts -----------------------------------------
    p = WaterParams()
    ok = (p.deep_color == PS_DEEP and p.absorb == PS_ABSORB
          and p.alpha_k == PS_ALPHA_K and p.shallow_gain == PS_SHALLOW_GAIN
          and p.shallow_bias == PS_SHALLOW_BIAS
          and p.swell_fade == (1200.0, 2400.0)
          and p.whitecap == (0.006, 0.42, 0.78, 0.6)
          and p.whitecap_gate == (0.62, 0.85)
          and p.swell_scale == 1.0 and p.sun_knee == 0.25
          and p.uncovered == 'deep' and p.uncovered_dz() == -40.0)
    h.report.check('defaults_match_planetside', ok,
                   'WaterParams() IS the planetside ocean')

    probes = [(3.3, 1.8082), (1.9, 1.2881), (0.95, 0.7677)]
    ok = all(abs(water_sun((v, v, v))[0] - want) < 0.001
             for v, want in probes)
    ident = water_sun((3.3, 1.0, 0.5), knee=0.0)
    ok = ok and abs(ident[0] - 3.3) < 1e-6 and abs(ident[2] - 0.5) < 1e-6
    h.report.check('knee_curve', ok,
                   f'{"; ".join(f"{v}->{water_sun((v, v, v))[0]:.3f}" for v, _ in probes)}'
                   f' (filed: 3.3->1.81, 1.9->1.29, 0.95->0.77); knee=0 identity')

    shallow = p.derived_shallow()
    want = tuple(min(1.0, c * PS_SHALLOW_GAIN + b)
                 for c, b in zip(PS_DEEP, PS_SHALLOW_BIAS))
    explicit = WaterParams(shallow_color=(0.9, 0.1, 0.2)).derived_shallow()
    ok = (all(abs(a - b) < 1e-9 for a, b in zip(shallow, want))
          and explicit == (0.9, 0.1, 0.2))
    h.report.check('shallow_derivation', ok,
                   f'derived {tuple(round(c, 3) for c in shallow)}; '
                   f'explicit shallow_color wins')

    # --- Scene: top-down ortho over a metallic backdrop card ------------
    h.set_ortho(film_h=2.0)
    base.cam.set_pos(0, 0, 20)
    base.cam.set_hpr(0, -90, 0)

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMBIENT, AMBIENT, AMBIENT, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    cm = p3d.CardMaker('backdrop')
    cm.set_frame(-50, 50, -50, 50)
    card = base.render.attach_new_node(cm.generate())
    card.set_p(-90)
    card.set_z(-10)
    card.set_two_sided(True)
    mat = p3d.Material('metal1')
    mat.set_base_color(p3d.LColor(*C_CARD, 1))
    mat.set_metallic(1.0)
    mat.set_roughness(1.0)
    card.set_material(mat, 1)

    def px(wx, wy):
        return (int((wx / 2.0 + 0.5) * h.win_w),
                int((0.5 - wy / 2.0) * h.win_h))

    cx, cy = px(0.0, 0.0)
    card_lum = sum(CURVE(c * AMBIENT) for c in C_CARD) / 3.0
    card_lin = tuple(c * AMBIENT for c in C_CARD)

    h.step(5)
    img_card = h.capture()
    got = common.avg_lum(img_card, cx, cy)
    h.report.check('card_sanity', abs(got - card_lum) < 0.02,
                   f'lum={got:.3f} expected {card_lum:.3f} (metallic card)')

    campos = p3d.Vec3(0, 0, 20)
    ZEN = (0.5, 0.5, 0.5)
    HOR = (0.2, 0.2, 0.2)

    # --- Phase 1: 'dry' uncovered = render NOTHING, byte-exact ----------
    water = pipeline.build_water_surface(
        base.render, 0.0,
        params=WaterParams(uncovered='dry', wave_amp=0.0),
        near_half_extent=100.0, near_resolution=8, far_annulus=None)
    water.set_environment((0, 0, 1), (0, 0, 0), HOR, ZEN)
    water.update(0, 0, campos)
    h.step(5)
    img = h.capture()
    rms = common.image_rms_diff(img_card, img, step=1)
    h.report.check('dry_uncovered_exact', rms == 0.0,
                   f'no seafloor bound, uncovered=dry: rms vs bare card = '
                   f'{rms:.2e} (alpha exactly 0)')
    water.cleanup()

    # --- Phase 2: 'deep' uncovered = the open ocean ----------------------
    water = pipeline.build_water_surface(
        base.render, 0.0, params=WaterParams(wave_amp=0.0),
        near_half_extent=100.0, near_resolution=8, far_annulus=None)
    water.set_environment((0, 0, 1), (0, 0, 0), HOR, ZEN)
    water.update(0, 0, campos)
    h.step(5)
    img = h.capture()
    h.save_capture(img, 'deep_ocean')
    got = common.avg_lum(img, cx, cy)
    want = expected_water_pixel(40.0, water.body_colours()[1],
                                ZEN, HOR, card_lin)
    h.report.check('deep_uncovered_covers', abs(got - want) < 0.03,
                   f'lum={got:.3f} expected {want:.3f} '
                   f'(40 m Beer-Lambert body, sun black)')

    # --- Phase 3: provider depth window — the melt -----------------------
    water.set_seafloor(const_floor_tex('floor_mid', -1.5), (-64, -64), 128)
    h.step(5)
    img = h.capture()
    got = common.avg_lum(img, cx, cy)
    want = expected_water_pixel(1.5, water.body_colours()[1],
                                ZEN, HOR, card_lin)
    h.report.check('melt_mid_analytic', abs(got - want) < 0.03,
                   f'depth 1.5 m: lum={got:.3f} expected {want:.3f} '
                   f'(1-exp(-kd) alpha + Beer-Lambert body)')

    water.set_seafloor(const_floor_tex('floor_shallow', -0.05),
                       (-64, -64), 128)
    h.step(5)
    img = h.capture()
    got = common.avg_lum(img, cx, cy)
    want = expected_water_pixel(0.05, water.body_colours()[1],
                                ZEN, HOR, card_lin)
    ok = abs(got - want) < 0.02 and abs(got - card_lum) < 0.03
    h.report.check('melt_shallow_clear', ok,
                   f'depth 0.05 m: lum={got:.3f} expected {want:.3f} '
                   f'~ card {card_lum:.3f} (the waterline melts)')

    # --- Phase 4: API contracts ------------------------------------------
    water.update(123.0, -45.0, campos)
    pos = water.root.get_pos()
    ok = (abs(pos[0] - 123.0) < 1e-6 and abs(pos[1] + 45.0) < 1e-6
          and abs(pos[2] - 0.0) < 1e-6)
    h.report.check('update_follow', ok,
                   f'root at {tuple(round(v, 3) for v in pos)} '
                   f'(follows in XY, pinned at water_z)')
    water.update(0, 0, campos)

    water.set_environment((0, 0, 1), (3.3, 3.3, 3.3), HOR, ZEN)
    got_sun = water.root.get_shader_input('u_sun_color').get_vector()
    ok = abs(got_sun[0] - 1.8082) < 0.001
    water.params.sun_knee = 0.0
    water.set_environment((0, 0, 1), (3.3, 3.3, 3.3), HOR, ZEN)
    got_raw = water.root.get_shader_input('u_sun_color').get_vector()
    ok = ok and abs(got_raw[0] - 3.3) < 1e-5
    h.report.check('sun_knee_applied', ok,
                   f'set_environment(3.3) -> u_sun_color {got_sun[0]:.3f} '
                   f'(knee); {got_raw[0]:.2f} with sun_knee=0')
    water.cleanup()

    # --- Phase 5: rim fade ------------------------------------------------
    # v_edge is vertex-interpolated, so the grid must SAMPLE the fade
    # zone (rim 0.80-0.97): resolution 64 puts ~11 vertex rows in it;
    # by the outermost rows the interpolated edge is ~1e-4 — visually
    # (and usually byte-) identical to the backdrop.
    water = pipeline.build_water_surface(
        base.render, 0.0, params=WaterParams(wave_amp=0.0),
        near_half_extent=1.0, near_resolution=64, far_annulus=None,
        rim_fade=True)
    water.set_environment((0, 0, 1), (0, 0, 0), HOR, ZEN)
    water.update(0, 0, campos)
    h.step(5)
    img = h.capture()
    ex, ey = px(0.995, 0.0)
    edge_diff = abs(common.lum_at(img, ex, ey)
                    - common.lum_at(img_card, ex, ey))
    centre_diff = abs(common.avg_lum(img, cx, cy) - card_lum)
    ok = edge_diff < 1e-3 and centre_diff > 0.03
    h.report.check('rim_fade_edge', ok,
                   f'rim pixel diff={edge_diff:.2e} (melts into the '
                   f'backdrop), centre covered (diff {centre_diff:.3f})')
    water.cleanup()

    # --- Phase 6: the analytic haze (sun+sky black -> pixel IS insc) -----
    card.stash()
    lens = p3d.PerspectiveLens()
    lens.set_fov(60)
    lens.set_near_far(0.5, 60000)
    base.cam.node().set_lens(lens)
    base.cam.set_pos(0, 0, 5)
    base.cam.set_hpr(0, 0, 0)

    HAZE = (0.4, 0.5, 0.6)
    SUN_HAZE = (0.9, 0.6, 0.3)
    DENS, SCALE_H, BASE_H, SUN_POW = 0.01, 50.0, 0.0, 8.0
    pipeline.set_atmosphere_params(
        haze_color=HAZE, sun_haze_color=SUN_HAZE, sun_power=SUN_POW,
        density=DENS, scale_height=SCALE_H, base_height=BASE_H)

    water = pipeline.build_water_surface(
        base.render, 0.0, params=WaterParams(wave_amp=0.0))
    campos = p3d.Vec3(0, 0, 5)

    def haze_expected(py, sun_dir, haze, sun_haze):
        """Independent evaluation of the engine's aerial-perspective
        block for the water-plane fragment under pixel column cx."""
        fx = (cx + 0.5) / h.win_w * 2.0 - 1.0
        fy = 1.0 - (py + 0.5) / h.win_h * 2.0
        near_p, far_p = p3d.LPoint3(), p3d.LPoint3()
        lens.extrude(p3d.LPoint2(fx, fy), near_p, far_p)
        d = far_p - near_p
        d.normalize()
        t = -campos.z / d.z
        dist = t
        pz = 0.0
        a = (campos.z - BASE_H) / SCALE_H
        u = (pz - campos.z) / SCALE_H
        falloff = ((1.0 - math.exp(-max(-30.0, min(30.0, u)))) / u
                   if abs(u) > 1e-4 else 1.0)
        tau = DENS * dist * math.exp(-max(-30.0, min(30.0, a))) * falloff
        trans = math.exp(-min(60.0, max(0.0, tau)))
        L = p3d.Vec3(*sun_dir)
        L.normalize()
        mu = max(0.0, min(1.0, d.dot(L)))
        insc = mixv(haze, sun_haze, (mu ** SUN_POW,) * 3)
        out = tuple(c * (1.0 - trans) for c in insc)
        return sum(CURVE(c) for c in out) / 3.0, trans

    ROWS = (300, 280, 264)

    def haze_check(name, sun_dir, haze, sun_haze):
        water.set_environment(sun_dir, (0, 0, 0), (0, 0, 0), (0, 0, 0))
        water.update(0, 0, campos)
        h.step(5)
        img = h.capture()
        worst, detail = 0.0, []
        for py in ROWS:
            want, trans = haze_expected(py, sun_dir, haze, sun_haze)
            got = common.lum_at(img, cx, py)
            worst = max(worst, abs(got - want))
            detail.append(f'row {py}: {got:.3f}/{want:.3f} (T={trans:.2f})')
        h.report.check(name, worst < 0.025,
                       f'{"; ".join(detail)} — worst err {worst:.3f}')
        return img

    haze_check('haze_analytic_side_sun', (1, 0, 0), HAZE, SUN_HAZE)
    haze_check('haze_analytic_sun_lobe', (0, 1, 0), HAZE, SUN_HAZE)

    HAZE2 = (0.1, 0.45, 0.12)
    pipeline.set_atmosphere_params(haze_color=HAZE2)
    img = haze_check('haze_tracks_params', (0, 1, 0), HAZE2, SUN_HAZE)
    h.save_capture(img, 'haze')

    # --- Phase 7: cleanup restores ---------------------------------------
    water.root.stash()
    h.step(5)
    img_bare = h.capture()
    water.root.unstash()
    h.step(2)
    water.cleanup()
    h.step(5)
    img = h.capture()
    rms = common.image_rms_diff(img_bare, img, step=1)
    h.report.check('cleanup_restores', rms == 0.0,
                   f'cleanup(): rms vs bare scene = {rms:.2e}')

    h.report.finish()


if __name__ == '__main__':
    main()
