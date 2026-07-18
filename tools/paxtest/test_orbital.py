"""paxtest: orbital scattering — planet limb/halo from space (Session R, R5.5).

The spaceflight half of the R5 signature look: single scattering through an
exponential shell around a sphere, rendered by pipeline-owned billboard
quads (extinction pass then additive inscatter pass). Opt-in per planet via
set_orbital_atmosphere(); unregistered scenes are byte-identical.

The reference model here is computed INDEPENDENTLY of the shader (same
documented math, high-resolution quadrature vs the shader's fixed-step
trapezoid — see orbital_atmo.frag header; any model change must land in
both places). Scene radiances are fully known: the planet sphere and the
backdrop card render constant emissive values through their own shaders,
so every expected pixel is analytic:

    pixel = curve( source_radiance * T_rgb(ray) + L_rgb(ray) )

Checks, in order:
  1. Baseline captures (no orbital atmosphere): planet disk and backdrop
     land on their analytic tonemap values.
  2. Registration with density=0 is byte-identical to baseline (T=1, L=0
     are exact framebuffer no-ops through the blend pipeline).
  3. Transmittance profile (sun black): on-disk and off-disk in-shell
     pixels match backdrop/planet * T_rgb from the reference integrator at
     three impact parameters, plus one outside the shell (untouched), plus
     monotonicity across the limb.
  4. Inscatter (sun +x, backdrop hidden -> halo against space): sunward
     limb and on-disk pixels match the reference L_rgb; the anti-sunward
     limb is terminator-occluded (dark), giving the day/night asymmetry.
  5. Full opt-out: clear_orbital_atmosphere() restores the baseline
     capture exactly.

Only meaningful for pipelines exposing set_orbital_atmosphere
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


# Geometry / model parameters (world units)
PLANET_R = 100.0
H = 6.0
THICK = 36.0                 # shell top 6H above the surface
R_TOP = PLANET_R + THICK
DENSITY = 0.05               # extinction per unit at the surface
TINT = (0.3, 0.6, 1.0)
INTENSITY = 1.0
SUN_RGB = (1.2, 1.1, 1.0)
BETA = tuple(DENSITY * t for t in TINT)

PV = 0.35                    # planet constant emissive radiance
BG = 0.55                    # backdrop constant emissive radiance
CAM_POS = (0.0, -700.0, 0.0)

# Sample columns are found ADAPTIVELY at runtime: for each target impact
# parameter b (perpendicular ray-to-center distance, world units) the test
# scans pixel columns, reconstructs each ray through the lens, and picks
# the column whose b is closest — no assumptions about fov/film math.
B_DISK_DAY = 45.0            # on-disk, +x (day side in the sun phase)
B_SHELL_IN = PLANET_R + 0.5 * H    # in-shell, near the limb
B_SHELL_OUT = PLANET_R + 4.0 * H   # in-shell, high altitude
B_SPACE = R_TOP + 15.0       # outside the shell entirely


# ----------------------------------------------------------------------
# Reference integrator (pure Python doubles, high-res trapezoid)
# ----------------------------------------------------------------------

def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _madd(o, d, t):
    return (o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t)


def _ray_sphere(o, d, c, r):
    """(t_enter, t_exit) of a unit ray against a sphere, or None."""
    oc = _sub(o, c)
    b = _dot(oc, d)
    cc = _dot(oc, oc) - r * r
    disc = b * b - cc
    if disc <= 0.0:
        return None
    sq = math.sqrt(disc)
    return (-b - sq, -b + sq)


def _rho(p, center):
    h = max(math.dist(p, center) - PLANET_R, 0.0)
    return math.exp(-min(h / H, 60.0))


def _integrate_rho(o, d, t0, t1, center, n=2048):
    if t1 <= t0:
        return 0.0
    dt = (t1 - t0) / n
    total = 0.5 * (_rho(_madd(o, d, t0), center)
                   + _rho(_madd(o, d, t1), center))
    for i in range(1, n):
        total += _rho(_madd(o, d, t0 + dt * i), center)
    return total * dt


def reference_model(o, d, center, sun_dir, sun_color):
    """(T_rgb, L_rgb) for one ray — the documented R5.5 model."""
    hit = _ray_sphere(o, d, center, R_TOP)
    if hit is None:
        return (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)
    t0 = max(hit[0], 0.0)
    t1 = hit[1]
    planet_hit = _ray_sphere(o, d, center, PLANET_R)
    if planet_hit is not None and planet_hit[0] > 0.0:
        t1 = min(t1, planet_hit[0])
    if t1 <= t0:
        return (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)

    d_view = _integrate_rho(o, d, t0, t1, center)
    trans = tuple(math.exp(-min(b * d_view, 60.0)) for b in BETA)

    # Sun transmittance at the segment's closest approach to the center
    t_ca = -_dot(_sub(o, center), d)
    t_star = min(max(t_ca, t0), t1)
    pstar = _madd(o, d, t_star)
    pc = _sub(pstar, center)

    m = -_dot(pc, sun_dir)
    occl = 1.0
    if m > 0.0:
        closest = _madd(pc, sun_dir, m)
        b_alt = math.sqrt(_dot(closest, closest)) - PLANET_R
        x = min(max(b_alt / (2.0 * H), 0.0), 1.0)
        occl = x * x * (3.0 - 2.0 * x)

    sb = _dot(pc, sun_dir)
    sc = _dot(pc, pc) - R_TOP * R_TOP
    sdisc = sb * sb - sc
    u_exit = max(-sb + math.sqrt(sdisc), 0.0) if sdisc > 0.0 else 0.0
    d_sun = _integrate_rho(pstar, sun_dir, 0.0, u_exit, center)
    t_sun = tuple(math.exp(-min(b * d_sun, 60.0)) * occl for b in BETA)

    mu = _dot(d, sun_dir)
    phase = 0.75 * (1.0 + mu * mu)
    inscatter = tuple(sun_color[i] * INTENSITY * phase * t_sun[i]
                      * (1.0 - trans[i]) for i in range(3))
    return trans, inscatter


# ----------------------------------------------------------------------
# Harness plumbing
# ----------------------------------------------------------------------

def pixel_ray(base, px, py, win_w, win_h):
    """World-space (origin, unit direction) of the ray through pixel
    center (px, py) — py in PNMImage coords (down from top)."""
    lens = base.cam.node().get_lens()
    fx = 2.0 * (px + 0.5) / win_w - 1.0
    fy = 1.0 - 2.0 * (py + 0.5) / win_h
    near_p = p3d.Point3()
    far_p = p3d.Point3()
    if not lens.extrude(p3d.Point2(fx, fy), near_p, far_p):
        raise RuntimeError('lens.extrude failed')
    mat = base.cam.get_mat(base.render)
    near_w = mat.xform_point(near_p)
    far_w = mat.xform_point(far_p)
    o = base.cam.get_pos(base.render)
    dvec = far_w - near_w
    dvec.normalize()
    return (o[0], o[1], o[2]), (dvec[0], dvec[1], dvec[2])


def rgb_at(img, x, y):
    c = img.get_xel(int(x), int(y))
    return (c[0], c[1], c[2])


def max_err(got, want):
    return max(abs(g - w) for g, w in zip(got, want))


def fmt3(v):
    return f'({v[0]:.3f},{v[1]:.3f},{v[2]:.3f})'


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--log-depth', action='store_true',
                        help='run with enable_log_depth (R4.1) — the quads '
                             'must depth-test correctly against log-depth '
                             'scene geometry')
    args = parser.parse_args()

    h = common.Harness(args, 'orbital')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    log_depth=args.log_depth)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_orbital_atmosphere'):
        h.report.skip('pipeline has no set_orbital_atmosphere (R5.5)')
    base = h.base
    curve = common.CURVES['hejl_dawson']

    base.camLens.set_near_far(0.5, 5000.0)
    base.camera.set_pos(*CAM_POS)
    base.camera.set_hpr(0, 0, 0)          # looking +y

    # Planet: constant-emissive sphere (radiance known exactly — the PBR
    # shader never touches these pixels)
    planet = scenes.make_uv_sphere(resolution=96)
    planet.reparent_to(base.render)
    planet.set_scale(PLANET_R)
    planet.set_shader(scenes.make_shader(scenes._FRAG_CONST_120, h.use_330))
    planet.set_shader_input('u_value', PV)

    # Backdrop: constant-emissive card behind the shell (transmittance
    # target for off-disk rays)
    backdrop = scenes.make_emissive_quad(base.render, h.use_330, BG, 800.0)
    backdrop.set_pos(0, 1500, 0)

    # Sun black until the inscatter phase (L = 0 exactly)
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))

    cx, cy = h.win_w // 2, h.win_h // 2

    def ray_for_offset(off):
        return pixel_ray(base, cx + off, cy, h.win_w, h.win_h)

    def impact_param(off):
        """(b, hits_planet) for the ray through column cx+off."""
        o, d = ray_for_offset(off)
        oc = o  # planet center is the origin
        along = _dot(oc, d)
        b = math.sqrt(max(_dot(oc, oc) - along * along, 0.0))
        hit = _ray_sphere(o, d, (0, 0, 0), PLANET_R)
        return b, (hit is not None and hit[1] > 0.0)

    def find_offset(target_b, want_disk):
        """Pixel column whose ray has impact parameter closest to
        target_b, restricted to on-disk / off-disk rays."""
        best_off, best_err = None, None
        for off in range(0, cx - 2):
            b, on_disk = impact_param(off)
            if on_disk != want_disk:
                continue
            err = abs(b - target_b)
            if best_err is None or err < best_err:
                best_off, best_err = off, err
        if best_off is None:
            raise RuntimeError(f'no pixel column with b~{target_b}')
        return best_off

    off_disk_day = find_offset(B_DISK_DAY, want_disk=True)
    off_shell_in = find_offset(B_SHELL_IN, want_disk=False)
    off_shell_out = find_offset(B_SHELL_OUT, want_disk=False)
    off_space = find_offset(B_SPACE, want_disk=False)
    h.report.info(
        'sample_columns',
        f'disk_day px+{off_disk_day} (b={impact_param(off_disk_day)[0]:.1f})'
        f', shell_in px+{off_shell_in} '
        f'(b={impact_param(off_shell_in)[0]:.1f}), shell_out '
        f'px+{off_shell_out} (b={impact_param(off_shell_out)[0]:.1f}), '
        f'space px+{off_space} (b={impact_param(off_space)[0]:.1f})')

    # --- 1. Baseline: no orbital atmosphere ----------------------------
    h.step(5)
    img_off = h.capture()
    h.save_capture(img_off, 'off')
    disk = rgb_at(img_off, cx, cy)
    h.report.check('baseline_disk', abs(disk[1] - curve(PV)) < 0.03,
                   f'planet disk renders its emissive value: g={disk[1]:.3f}'
                   f' expected {curve(PV):.3f}')
    bgpix = rgb_at(img_off, cx + off_space, cy)
    h.report.check('baseline_backdrop', abs(bgpix[1] - curve(BG)) < 0.03,
                   f'backdrop g={bgpix[1]:.3f} expected {curve(BG):.3f}')

    # --- 2. Registered with density=0 == baseline, byte-identical ------
    pipeline.set_orbital_atmosphere(
        planet, planet_radius=PLANET_R, scale_height=H, thickness=THICK,
        density=0.0, scatter_tint=TINT, intensity=INTENSITY)
    h.step(5)
    img_d0 = h.capture()
    rms = common.image_rms_diff(img_off, img_d0, step=1)
    h.report.check('density_zero_identical', rms == 0.0,
                   f'quads present, density=0: rms vs off = {rms:.2e} '
                   f'(dst*1.0 and dst+0.0 are exact blend no-ops)')

    # --- 3. Transmittance profile (sun black, L=0) ---------------------
    pipeline.set_orbital_atmosphere(planet, density=DENSITY)
    h.step(5)
    img_t = h.capture()
    h.save_capture(img_t, 'transmittance')
    lums = []
    for off, source, tag in ((0, PV, 'disk_center'),
                             (off_shell_in, BG, 'shell_inner'),
                             (off_shell_out, BG, 'shell_outer'),
                             (off_space, BG, 'space')):
        o, d = ray_for_offset(off)
        trans, _ = reference_model(o, d, (0, 0, 0), (1, 0, 0), (0, 0, 0))
        want = tuple(curve(source * t) for t in trans)
        got = rgb_at(img_t, cx + off, cy)
        err = max_err(got, want)
        lums.append(sum(got) / 3.0)
        h.report.check(
            f'trans_{tag}', err < 0.05,
            f'px+{off}: rgb={fmt3(got)} expected {fmt3(want)} '
            f'[T={fmt3(trans)}], max channel err {err:.3f}')
    h.report.check('trans_profile_monotonic',
                   lums[1] < lums[2] < lums[3],
                   f'extinction fades outward across the limb: '
                   f'{lums[1]:.3f} < {lums[2]:.3f} < {lums[3]:.3f}')

    # --- 4. Inscatter: sun +x, halo against space ----------------------
    backdrop.hide()
    h.adapter.update_sun((1, 0, 0), SUN_RGB)
    h.step(5)
    img_l = h.capture()
    h.save_capture(img_l, 'inscatter')
    sun_dir = (1.0, 0.0, 0.0)
    for off, source, tag in ((off_shell_in, 0.0, 'halo_sunward'),
                             (off_disk_day, PV, 'disk_day')):
        o, d = ray_for_offset(off)
        trans, ins = reference_model(o, d, (0, 0, 0), sun_dir, SUN_RGB)
        want = tuple(curve(source * trans[i] + ins[i]) for i in range(3))
        got = rgb_at(img_l, cx + off, cy)
        err = max_err(got, want)
        h.report.check(
            f'inscatter_{tag}', err < 0.05,
            f'px+{off}: rgb={fmt3(got)} expected {fmt3(want)} '
            f'[L={fmt3(ins)}], max channel err {err:.3f}')
    lum_sun = common.avg_lum(img_l, cx + off_shell_in, cy, half=1)
    lum_anti = common.avg_lum(img_l, cx - off_shell_in, cy, half=1)
    h.report.check('terminator_dark', lum_anti < 0.05,
                   f'anti-sunward limb is terminator-occluded: '
                   f'lum={lum_anti:.3f}')
    h.report.check('limb_asymmetry', lum_sun > 5.0 * max(lum_anti, 1e-3),
                   f'sunward halo {lum_sun:.3f} vs anti-sunward '
                   f'{lum_anti:.3f} — day/night asymmetry')

    # --- 5. Opt-out restores the baseline exactly ----------------------
    backdrop.show()
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))
    pipeline.clear_orbital_atmosphere(planet)
    h.step(5)
    img_restored = h.capture()
    rms = common.image_rms_diff(img_off, img_restored, step=1)
    h.report.check('opt_out_restores', rms == 0.0,
                   f'clear_orbital_atmosphere(): rms vs the pre-enable '
                   f'baseline = {rms:.2e} (byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
