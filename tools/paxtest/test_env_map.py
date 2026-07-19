"""paxtest: specular IBL env map (Session M / R5.3 first slice).

`pipeline.set_env_map(cubemap)` feeds the shader's until-now-black
`filtered_env_map` + `max_reflection_lod` path:

  ibl_spec = textureCubeLod(env, reflect(-view, normal),
                            perceptual_roughness * max_lod)
             * (F * brdf_lut.x + brdf_lut.y)

The slice also ships the REAL split-sum BRDF LUT
(pax3d_render/textures/brdf_lut.txo, tools/gen_brdf_lut.py) — the old
1x1 white fallback made lut.y = 1, which would ADD the whole env color
the moment a real cubemap bound (harmless only while env was black).

Scene: flat card facing the camera (test_glass geometry), sun BLACK —
everything measured is IBL + the tiny flat ambient. Expected values
peek (A, B) from the same LUT texture the pipeline loaded, at the
texel centers the shader's clamped bilinear fetch resolves to; the
material roughness is chosen ON a texel center so the fetch is exact.

Checks:
  1. The real LUT is loaded (not the white fallback) and its mirror
     corner integrates to (A~1, B~0).
  2. Baseline (no env map): card shows only the flat ambient.
  3. Constant-color cubemap: per-channel analytic C*(F*A+B) + amb
     (metallic 1: F = 1) — catches channel swaps and LUT misuse.
  4. Survives a shader-recompile-class toggle (rms 0).
  5. Hand-loaded per-mip colors: roughness 0 reads mip 0, roughness 1
     reads the top mip — proves the LOD ladder actually addresses the
     chain (mip colors chosen red-ish vs blue-ish for dominance).
  6. Face-colored cubemap, mirror card: normal incidence reflects the
     -Y face; pitched 45 degrees it reflects the +Z face — sampling
     ORIENTATION is correct (the Session J sh_from_cubemap soft spot,
     shader-sampling side).
  6b. Env yaw (Round-5 ask): set_env_map_rotation(90) brings the -X
     face content to -Y (the skybox set_h sense); yaw 0 restores the
     pre-yaw capture byte-identically.
  6c. Env scale/intensity (Round-5 asks): per-node set_env_scale and
     global set_env_intensity multiply ONLY the env term (flat
     ambient intact), compose multiplicatively, and restore to an
     exact full-strength default.
  7. Glass composition: on a set_glass node the reflection term rides
     at FULL strength through alpha 0.15 (the canopy case).
  8-11. The GGX prefilter tool (Session Q / R5.4, tools/
     gen_env_prefilter.py, run here as a real subprocess — requires pip
     simplepbr, else reported as INFO and skipped):
       8. face-colored input -> .txo: complete mip chain, mip 0 an exact
          identity (roughness 0 preserves the env);
       9. uniform input -> every level stays exactly that color (GGX
          weight normalization = energy preservation);
      10. the ladder actually blurs: face-center color walks
          monotonically from its own face color toward the blend;
      11. the .txo drives the SHADER: mirror card reflects mip 0, a
          roughness-1 card reads the top of the tool's ladder
          (disk -> GPU -> textureCubeLod, end to end).
  12. clear_env_map() restores the baseline byte-identically.

Only meaningful for pipelines exposing set_env_map (pax3d_render and
the routed pax_pbr adapter).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common


AMB = 0.02          # tiny AmbientLight (harness gotcha: none => white flood)
ALPHA = 0.15        # glass-check alpha
F0 = 0.04
C_ENV = (0.5, 0.3, 0.15)                 # constant-cubemap color
MIP_COLORS = [(0.6, 0.1, 0.1), (0.3, 0.3, 0.1),
              (0.1, 0.5, 0.1), (0.1, 0.1, 0.6)]   # mips 0..3 (8,4,2,1)
FACE_COLORS = [(0.7, 0.1, 0.1), (0.1, 0.7, 0.1),  # +X, -X
               (0.7, 0.7, 0.1), (0.7, 0.1, 0.7),  # +Y, -Y (magenta)
               (0.1, 0.1, 0.7), (0.1, 0.7, 0.7)]  # +Z (blue), -Z


def lut_ab(lut, ndv, rough):
    """(A, B) as the shader's clamped bilinear fetch resolves them,
    peeked at the nearest texel center of the pipeline's own LUT."""
    n = lut.get_x_size()
    peek = lut.peek()
    c = p3d.LColor()
    u = (min(int(ndv * n), n - 1) + 0.5) / n
    v = (min(int(rough * n), n - 1) + 0.5) / n
    peek.lookup(c, u, v)
    return c[0], c[1]


def make_float_cube(size, mip_colors=None, face_colors=None, const=None):
    """Cubemap with: one constant color (auto mips), per-mip colors
    (explicit chain), or per-face colors (auto mips)."""
    tex = p3d.Texture('paxtest_env')
    tex.setup_cube_map(size, p3d.Texture.T_float, p3d.Texture.F_rgb32)
    levels = ([(0, size)] if mip_colors is None else
              [(n, size >> n) for n in range(int(math.log2(size)) + 1)])
    for mip, msize in levels:
        for face in range(6):
            rgb = (const if const is not None else
                   mip_colors[mip] if mip_colors is not None else
                   face_colors[face])
            img = p3d.PNMImage(msize, msize, 3, 65535)
            img.fill(*rgb)
            tex.load(img, face, mip)
    return tex


def make_card(parent, half, roughness, metallic, alpha=1.0):
    cm = p3d.CardMaker('paxtest_env_card')
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    apply_surface(np, roughness, metallic, alpha)

    white = p3d.Texture('paxtest_white')
    white.setup_2d_texture(1, 1, p3d.Texture.T_unsigned_byte,
                           p3d.Texture.F_rgb8)
    white.set_clear_color(p3d.LColor(1, 1, 1, 1))
    np.set_texture(white, 1)
    mr_stage = p3d.TextureStage('paxtest_mr')
    mr_stage.set_mode(p3d.TextureStage.M_selector)
    np.set_texture(mr_stage, white, 1)
    return np


def apply_surface(np, roughness, metallic, alpha=1.0):
    mat = p3d.Material('paxtest_env_mat')
    mat.set_base_color(p3d.LColor(1, 1, 1, alpha))
    mat.set_roughness(roughness)
    mat.set_metallic(metallic)
    np.set_material(mat, 1)


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


def check_rgb(h, name, got, want, tol=0.05, extra=''):
    err = max(abs(g - w) for g, w in zip(got, want))
    h.report.check(name, err < tol,
                   f'rgb=({got[0]:.3f},{got[1]:.3f},{got[2]:.3f}) expected '
                   f'({want[0]:.3f},{want[1]:.3f},{want[2]:.3f}), max err '
                   f'{err:.3f}{extra}')


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'env_map')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_env_map'):
        h.report.skip('pipeline has no set_env_map (Session M / R5.3)')
    base = h.base
    curve = common.CURVES['hejl_dawson']

    lut = pipeline._brdf_lut
    # Material roughness ON a LUT texel center -> the shader's clamped
    # bilinear fetch lands exactly on the peeked texel.
    n_lut = max(lut.get_x_size(), 1)
    rough_tc = (int(0.4 * n_lut) + 0.5) / n_lut

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (0, 0, 0))    # sun BLACK: IBL only

    card = make_card(base.render, 6, roughness=rough_tc, metallic=1.0)
    base.camera.set_pos(0, -30, 0)
    base.camera.set_hpr(0, 0, 0)
    cx, cy = h.win_w // 2, h.win_h // 2

    # --- 1. Real LUT loaded, mirror corner sane -------------------------
    a0, b0 = lut_ab(lut, 1.0, 0.0)
    h.report.check('real_brdf_lut',
                   lut.get_x_size() > 1 and abs(a0 - 1.0) < 0.05
                   and abs(b0) < 0.05,
                   f'{lut.get_x_size()}x{lut.get_y_size()} LUT; mirror '
                   f'corner (A,B)=({a0:.3f},{b0:.3f}) ~ (1, 0)')

    # --- 2. Baseline: no env map -> flat ambient only -------------------
    h.step(5)
    img_base = h.capture()
    h.save_capture(img_base, 'baseline')
    # metallic 1: diffuse_color = 0, flat amb = spec_color * AMB = AMB
    check_rgb(h, 'baseline_no_env', avg_rgb(img_base, cx, cy),
              (curve(AMB),) * 3, extra=' (shipped behavior: ibl_spec 0)')

    # --- 3. Constant cubemap: per-channel analytic ----------------------
    env_const = make_float_cube(8, const=C_ENV)
    pipeline.set_env_map(env_const)
    a, b = lut_ab(lut, 1.0, rough_tc)
    h.step(5)
    img_env = h.capture()
    h.save_capture(img_env, 'constant_env')
    want = tuple(curve(c * (a + b) + AMB) for c in C_ENV)   # F = 1
    check_rgb(h, 'constant_env_analytic', avg_rgb(img_env, cx, cy), want,
              extra=f' (A={a:.3f} B={b:.3f} @ ndv=1, rough={rough_tc:.3f})')

    # --- 4. Survives a recompile-class toggle ---------------------------
    pipeline.set_shadow_filter_size(3)
    h.step(5)
    img_recompiled = h.capture()
    pipeline.set_shadow_filter_size(1)
    h.step(2)
    rms = common.image_rms_diff(img_env, img_recompiled, step=1)
    h.report.check('env_survives_recompile', rms == 0.0,
                   f'shader recompile with env map bound: rms={rms:.2e}')

    # --- 5. LOD ladder: roughness picks the mip -------------------------
    env_mips = make_float_cube(8, mip_colors=MIP_COLORS)
    pipeline.set_env_map(env_mips)          # max_lod = 3 (8->1 chain)
    apply_surface(card, 0.0, 1.0)
    a, b = lut_ab(lut, 1.0, 0.0)
    h.step(5)
    got0 = avg_rgb(h.capture(), cx, cy)
    want0 = tuple(curve(c * (a + b) + AMB) for c in MIP_COLORS[0])
    check_rgb(h, 'lod_zero_reads_base', got0, want0,
              extra=' (roughness 0 -> mip 0, red)')
    apply_surface(card, 1.0, 1.0)
    a, b = lut_ab(lut, 1.0, 1.0)
    h.step(5)
    got3 = avg_rgb(h.capture(), cx, cy)
    want3 = tuple(curve(c * (a + b) + AMB) for c in MIP_COLORS[3])
    check_rgb(h, 'lod_max_reads_top', got3, want3,
              extra=' (roughness 1 -> top mip, blue)')

    # --- 6. Mirror orientation: which face does the world see? ----------
    env_faces = make_float_cube(8, face_colors=FACE_COLORS)
    pipeline.set_env_map(env_faces)
    apply_surface(card, 0.0, 1.0)
    a, b = lut_ab(lut, 1.0, 0.0)
    h.step(5)
    img_mirror = h.capture()
    h.save_capture(img_mirror, 'mirror_neg_y')
    want_my = tuple(curve(c * (a + b) + AMB) for c in FACE_COLORS[3])
    check_rgb(h, 'mirror_reflects_neg_y', avg_rgb(img_mirror, cx, cy),
              want_my, extra=' (normal incidence -> -Y face, magenta)')
    card.set_p(-45)                          # normal -> (0,-.707,+.707)
    a, b = lut_ab(lut, math.sqrt(0.5), 0.0)
    h.step(5)
    img_tilt = h.capture()
    h.save_capture(img_tilt, 'mirror_pos_z')
    got = avg_rgb(img_tilt, cx, cy)
    want_pz = tuple(curve(c * (a + b) + AMB) for c in FACE_COLORS[4])
    check_rgb(h, 'mirror_reflects_pos_z', got, want_pz, tol=0.06,
              extra=' (45-degree pitch -> +Z face, blue)')
    card.set_p(0)

    # --- 6b. Env yaw (Round-5 ask): set_env_map_rotation ----------------
    # Environment rotated +90 in the skybox set_h sense: content that
    # sat at -X (green) arrives at -Y, so the normal-incidence mirror
    # now reflects green. Yaw 0 restores the pre-yaw capture exactly.
    if hasattr(pipeline, 'set_env_map_rotation'):
        a, b = lut_ab(lut, 1.0, 0.0)
        pipeline.set_env_map_rotation(90.0)
        h.step(5)
        img_yaw = h.capture()
        h.save_capture(img_yaw, 'mirror_yaw90')
        want_yaw = tuple(curve(c * (a + b) + AMB) for c in FACE_COLORS[1])
        check_rgb(h, 'env_yaw_rotates_lookup', avg_rgb(img_yaw, cx, cy),
                  want_yaw, extra=' (+90 yaw: -X green arrives at -Y — '
                  'the skybox set_h sense)')
        pipeline.set_env_map_rotation(0.0)
        h.step(5)
        rms = common.image_rms_diff(img_mirror, h.capture(), step=1)
        h.report.check('env_yaw_zero_restores', rms == 0.0,
                       f'yaw back to 0: rms vs pre-yaw mirror = '
                       f'{rms:.2e} (exact no-op default)')

    # --- 6c. Env scale + intensity (Round-5 asks) -----------------------
    # Constant cubemap, metallic 1: pixel = curve(C*(A+B)*s*k + AMB) —
    # per-node scale s and global intensity k multiply the env term
    # ONLY (the flat ambient stays untouched) and compose.
    if hasattr(pipeline, 'set_env_scale'):
        pipeline.set_env_map(env_const)
        apply_surface(card, rough_tc, 1.0)
        a, b = lut_ab(lut, 1.0, rough_tc)
        pipeline.set_env_scale(card, 0.25)
        h.step(5)
        want_s = tuple(curve(c * (a + b) * 0.25 + AMB) for c in C_ENV)
        check_rgb(h, 'env_scale_scales_env_only',
                  avg_rgb(h.capture(), cx, cy), want_s,
                  extra=' (per-node 0.25: sheen trace, ambient intact)')
        pipeline.set_env_intensity(0.5)
        h.step(5)
        want_sk = tuple(curve(c * (a + b) * 0.125 + AMB) for c in C_ENV)
        check_rgb(h, 'env_intensity_composes',
                  avg_rgb(h.capture(), cx, cy), want_sk,
                  extra=' (global 0.5 x node 0.25 = 0.125 multiply)')
        pipeline.clear_env_scale(card)
        pipeline.set_env_intensity(1.0)
        h.step(5)
        want_1 = tuple(curve(c * (a + b) + AMB) for c in C_ENV)
        check_rgb(h, 'env_controls_restore',
                  avg_rgb(h.capture(), cx, cy), want_1,
                  extra=' (defaults back: exact full-strength env)')

    # --- 7. Glass composition: reflections survive alpha ----------------
    pipeline.set_env_map(env_const)
    apply_surface(card, rough_tc, 0.0, alpha=ALPHA)
    pipeline.set_glass(card)
    a, b = lut_ab(lut, 1.0, rough_tc)
    h.step(5)
    img_glass = h.capture()
    h.save_capture(img_glass, 'glass_env')
    # metallic 0 glass: ibl_f = F0; spec bucket unattenuated, ambient
    # split diffuse*alpha + F0-part unattenuated (see pax_pbr GLASS)
    want_g = tuple(curve(ALPHA * ((1 - F0) * AMB) + c * (F0 * a + b)
                         + F0 * AMB) for c in C_ENV)
    check_rgb(h, 'glass_reflections_full', avg_rgb(img_glass, cx, cy),
              want_g, extra=f' (alpha {ALPHA}: env term NOT scaled)')
    pipeline.set_glass(card, False)

    # --- 7b. Per-node env override (Session S — cabin vs sky) -----------
    # A second, smaller card beside the first: the "interior" node. The
    # global map stays the sky (C_ENV); the node gets its own 4-size
    # mip-colored chain, so BOTH overrides are proven: the map itself,
    # and max_reflection_lod (if the global lod 3 leaked onto the node's
    # 2-lod chain, mid-roughness would blend the wrong mips and miss by
    # ~0.25 — far outside tolerance).
    if 'node' in pipeline.set_env_map.__code__.co_varnames:
        apply_surface(card, rough_tc, 1.0)      # restore from glass alpha
        pipeline.set_env_map(env_const)         # the global "sky"
        card2 = make_card(base.render, 2.0, roughness=rough_tc,
                          metallic=1.0)
        # x=5 keeps the projected center well inside the fov-30 frame
        # (x=8 lands at px ~511 — off the sampling window); y=-0.5 puts
        # card2 in FRONT of the big card it partially overlaps.
        card2.set_pos(5.0, -0.5, 0.0)
        ndc = p3d.Point2()
        base.camLens.project(base.camera.get_relative_point(
            base.render, card2.get_pos(base.render)), ndc)
        c2x = int((ndc.x * 0.5 + 0.5) * h.win_w)
        c2y = int((ndc.y * 0.5 + 0.5) * h.win_h)
        # Off-axis view: ndv < 1 on card2 (normal -Y, camera at (0,-30,0))
        view = p3d.Vec3(0.0 - 5.0, -30.0 - (-0.5), 0.0)
        view.normalize()
        ndv2 = -view.y                          # dot((0,-1,0), -view)
        a, b = lut_ab(lut, ndv2, rough_tc)
        h.step(5)
        img_two = h.capture()
        h.save_capture(img_two, 'pernode_before')
        want_sky = tuple(curve(c * (a + b) + AMB) for c in C_ENV)
        check_rgb(h, 'pernode_baseline_both_sky',
                  avg_rgb(img_two, c2x, c2y), want_sky,
                  extra=f' (both cards on the global map; ndv={ndv2:.3f})')

        mips4 = [(0.6, 0.1, 0.1), (0.3, 0.3, 0.1), (0.1, 0.1, 0.6)]
        env_cabin = make_float_cube(4, mip_colors=mips4)
        r_mid = (int(0.5 * n_lut) + 0.5) / n_lut   # LUT texel center ~0.5
        apply_surface(card2, r_mid, 1.0)
        pipeline.set_env_map(env_cabin, node=card2)
        a2, b2 = lut_ab(lut, ndv2, r_mid)
        h.step(5)
        img_override = h.capture()
        h.save_capture(img_override, 'pernode_override')
        # node lod = 2: lod = r*2 ~ 1.008 -> essentially mip 1 exactly
        want_cabin = tuple(curve(c * (a2 + b2) + AMB) for c in mips4[1])
        check_rgb(h, 'pernode_override_analytic',
                  avg_rgb(img_override, c2x, c2y), want_cabin,
                  extra=' (node map mip 1 via the NODE max_lod=2)')
        a, b = lut_ab(lut, 1.0, rough_tc)
        want_center = tuple(curve(c * (a + b) + AMB) for c in C_ENV)
        check_rgb(h, 'pernode_sibling_keeps_sky',
                  avg_rgb(img_override, cx, cy), want_center,
                  extra=' (center card still on the global map)')

        pipeline.clear_env_map(node=card2)
        apply_surface(card2, rough_tc, 1.0)
        h.step(5)
        rms = common.image_rms_diff(img_two, h.capture(), step=1)
        h.report.check('pernode_clear_restores', rms == 0.0,
                       f'clear_env_map(node=...): rms vs pre-override = '
                       f'{rms:.2e} (subtree reverts to the inherited map)')
        card2.remove_node()

    # --- 8-11. The GGX prefilter tool (gen_env_prefilter.py) ------------
    try:
        import simplepbr  # noqa: F401
        have_simplepbr = True
    except ImportError:
        have_simplepbr = False
        h.report.info('prefilter_tool',
                      'pip simplepbr unavailable in this env - tool checks '
                      'not run (dev-time dependency)')
    if have_simplepbr:
        import subprocess
        tool = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'gen_env_prefilter.py')
        out_dir = common.OUTPUT_DIR
        pf_dir = p3d.Filename.from_os_specific(out_dir).get_fullpath()
        psize = 16
        levels = int(math.log2(psize)) + 1
        for face, rgb in enumerate(FACE_COLORS):
            img = p3d.PNMImage(psize, psize, 3, 65535)
            img.fill(*rgb)
            img.write(p3d.Filename(f'{pf_dir}/pfface_{face}.png'))
        txo = os.path.join(out_dir, 'pf_faces.txo')
        r = subprocess.run(
            [sys.executable, tool, os.path.join(out_dir, 'pfface_#.png'),
             txo, '--size', str(psize), '--samples', '16'],
            capture_output=True, text=True, timeout=300)
        pf_tex = p3d.TexturePool.load_texture(
            p3d.Filename.from_os_specific(txo)) if r.returncode == 0 else None

        # 8. Complete chain; mip 0 is the identity.
        img = p3d.PNMImage()
        ok = (pf_tex is not None
              and pf_tex.get_num_ram_mipmap_images() == levels)
        worst = 1.0
        if ok:
            worst = 0.0
            for face, rgb in enumerate(FACE_COLORS):
                pf_tex.store(img, face, 0)
                got = img.get_xel(psize // 2, psize // 2)
                worst = max(worst,
                            max(abs(got[i] - rgb[i]) for i in range(3)))
            ok = worst < 0.01
        h.report.check(
            'prefilter_chain_identity', ok,
            f'tool .txo: {levels}-level chain, mip 0 face centers exact '
            f'(worst err {worst:.4f})'
            + ('' if r.returncode == 0 else
               f' — TOOL FAILED: {r.stderr.strip()[-200:]}'))

        # 9. Uniform input -> uniform at every level (energy preserved).
        for face in range(6):
            img = p3d.PNMImage(psize, psize, 3, 65535)
            img.fill(*C_ENV)
            img.write(p3d.Filename(f'{pf_dir}/pfuni_{face}.png'))
        txo_u = os.path.join(out_dir, 'pf_uniform.txo')
        r2 = subprocess.run(
            [sys.executable, tool, os.path.join(out_dir, 'pfuni_#.png'),
             txo_u, '--size', str(psize), '--samples', '16'],
            capture_output=True, text=True, timeout=300)
        worst_u = 1.0
        if r2.returncode == 0:
            uni = p3d.TexturePool.load_texture(
                p3d.Filename.from_os_specific(txo_u))
            worst_u = 0.0
            for mip in range(levels):
                for face in range(6):
                    uni.store(img, face, mip)
                    got = img.get_xel(img.get_x_size() // 2,
                                      img.get_y_size() // 2)
                    worst_u = max(worst_u, max(
                        abs(got[i] - C_ENV[i]) for i in range(3)))
        h.report.check('prefilter_uniform_energy', worst_u < 0.005,
                       f'uniform env: every mip level of every face stays '
                       f'({C_ENV[0]},{C_ENV[1]},{C_ENV[2]}) - worst err '
                       f'{worst_u:.4f} (GGX weights normalize)')

        # 10. The ladder blurs monotonically (+X face, red channel).
        reds = []
        if pf_tex is not None:
            for mip in range(levels):
                pf_tex.store(img, 0, mip)
                reds.append(img.get_xel(img.get_x_size() // 2,
                                        img.get_y_size() // 2)[0])
        mono = (len(reds) == levels
                and all(reds[i + 1] <= reds[i] + 0.005
                        for i in range(levels - 1))
                and reds[0] - reds[-1] > 0.05)
        h.report.check(
            'prefilter_monotonic_blur', mono,
            '+X face-center red across the ladder: ['
            + ', '.join(f'{v:.3f}' for v in reds)
            + '] - monotone toward the blend')

        # 11. The .txo drives the shader end to end.
        pipeline.set_env_map(pf_tex)     # default max_lod == full chain
        apply_surface(card, 0.0, 1.0)
        a, b = lut_ab(lut, 1.0, 0.0)
        h.step(5)
        img_pf = h.capture()
        h.save_capture(img_pf, 'prefiltered_mirror')
        want_m = tuple(curve(c * (a + b) + AMB) for c in FACE_COLORS[3])
        got_m = avg_rgb(img_pf, cx, cy)
        err_m = max(abs(g - w) for g, w in zip(got_m, want_m))
        apply_surface(card, 1.0, 1.0)
        a, b = lut_ab(lut, 1.0, 1.0)
        pf_tex.store(img, 3, levels - 1)     # tool's own top-mip -Y texel
        top = img.get_xel(0, 0)
        h.step(5)
        got_r = avg_rgb(h.capture(), cx, cy)
        want_r = tuple(curve(top[i] * (a + b) + AMB) for i in range(3))
        err_r = max(abs(g - w) for g, w in zip(got_r, want_r))
        h.report.check(
            'prefilter_drives_shader', err_m < 0.05 and err_r < 0.06,
            f'mirror reflects tool mip 0 (-Y magenta, err {err_m:.3f}); '
            f'roughness 1 reads the tool top mip '
            f'({top[0]:.3f},{top[1]:.3f},{top[2]:.3f}) through '
            f'textureCubeLod (err {err_r:.3f})')

    # --- 12. clear_env_map restores the baseline exactly ----------------
    apply_surface(card, rough_tc, 1.0)
    pipeline.clear_env_map()
    h.step(5)
    img_cleared = h.capture()
    rms = common.image_rms_diff(img_base, img_cleared, step=1)
    h.report.check('clear_restores_baseline', rms == 0.0,
                   f'clear_env_map(): rms vs baseline = {rms:.2e} '
                   f'(byte-identical opt-out)')

    h.report.finish()


if __name__ == '__main__':
    main()
