"""paxtest: glTF alphaMode MASK under the pipeline (field report 2026-07-19).

panda3d-gltf expresses MASK as a geom-level AlphaTestAttrib
(M_greater_equal, alphaCutoff). The GL backend implements that attrib
ONLY via fixed-function GL_ALPHA_TEST (glGraphicsStateGuardian:
do_issue_alpha_test lives behind has_fixed_function_pipeline()), so:

  @game (compat, GLSL 120):  MASK works — the fixed-function test acts
                             on the shader's output alpha.
  @modern (gl-version 3 2):  the attrib is SILENTLY IGNORED — every
                             MASK material renders opaque. A factor-only
                             mask (baseColorFactor alpha 0, no texture)
                             draws as a solid shell; cutout foliage
                             becomes solid cards. This is the character
                             dev's makeup-shell field report.

`pipeline.apply_alpha_masks(model_np)` composes an ALPHA_MASK compile of
the PBR shader (cutoff baked as a define) onto exactly the geoms
carrying the loader's attrib — in-shader discard, same predicate as the
fixed-function test, so both baselines agree afterwards.

Scene (authored GLB through the real loader, ortho camera, sun on the
view axis like test_doublesided): a white OPAQUE quad behind two MASK
quads — 'shell' (red factor, alpha 0, NO texture: must vanish entirely)
and 'cutout' (red factor, 8x8 alpha texture: left half kept, right half
discarded).

Checks:
  1. Loader premise: exactly the two MASK geoms carry AlphaTestAttrib.
  2. Baseline documented: BEFORE the API, compat already masks (the
     fixed-function path) and modern renders the shell solid (the
     defect, measured). If a future engine change flips the @modern
     expectation, this check fails and forces a true-up.
  3. apply_alpha_masks finds exactly the 2 masked geoms (never the
     opaque one) and is idempotent.
  4. THE field case: the alpha-0 textureless shell vanishes — the back
     quad's lit white shows through, matching the anchor capture.
  5. Textured cutout: kept half stays red-lit, discarded half shows the
     back quad. Both baselines, same predicate.
  6. Compat is BIT-identical before/after the API (the in-shader test
     double-applies the same predicate — cannot change a pixel).
  7. A recompile-class toggle (double_sided_lighting) keeps the masks
     (the glass discipline) and restores bit-identically after.
  8. Opt-out restores the pre-API capture byte-identically — including
     restoring the DEFECT on @modern (the contract is exact restore).

Only meaningful for pipelines exposing apply_alpha_masks (pax3d_render
and the routed pax_pbr adapter).
"""
import argparse
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common


ROUGH = 0.3         # perceptual roughness
SUN = 0.6           # sun intensity
AMB = 0.02          # tiny AmbientLight (harness gotcha: none => white flood)
F0 = 0.04


def analytic_lit(curve):
    """Shader BRDF at n=l=v=h (all dots exactly 1) — see test_glass."""
    f = F0 + (1.0 - F0) * 2.0 ** (-5.55473 - 6.98316)
    spec = f * 0.25 * (1.0 / (math.pi * ROUGH ** 4))
    diff = (1.0 - F0) / math.pi
    return curve(SUN * (diff + spec) + AMB)


# ----------------------------------------------------------------------
# Synthetic GLB: back quad (OPAQUE) + shell (factor-only MASK) + cutout
# (textured MASK). glTF axes: (x, y, z)_gltf -> (x, -z, y)_panda, so
# quads in the glTF XY plane face the -Y camera; glTF z=-2 sits BEHIND
# glTF z=0 for that camera.
# ----------------------------------------------------------------------

def build_alpha_png(path):
    """8x8 white RGBA: columns 0-3 alpha 1.0, columns 4-7 alpha 0.0."""
    img = p3d.PNMImage(8, 8)
    img.add_alpha()
    img.fill(1.0, 1.0, 1.0)
    for y in range(8):
        for x in range(8):
            img.set_alpha(x, y, 1.0 if x < 4 else 0.0)
    img.write(p3d.Filename.from_os_specific(path))
    with open(path, 'rb') as f:
        return f.read()


def build_glb(path, png_path):
    def f32(*vals):
        return struct.pack('<%df' % len(vals), *vals)

    def quad(x0, x1, y0, y1, z):
        pos = f32(x0, y0, z,  x1, y0, z,  x1, y1, z,  x0, y1, z)
        return pos

    nrm = f32(0.0, 0.0, 1.0) * 4
    idx = struct.pack('<6H', 0, 1, 2, 0, 2, 3)
    # u: 0 at the -x edge, 1 at the +x edge (v constant-alpha, any map)
    uv = f32(0.0, 1.0,  1.0, 1.0,  1.0, 0.0,  0.0, 0.0)
    png_bytes = build_alpha_png(png_path)

    blocks = [
        quad(-7.0, 7.0, -7.0, 7.0, -2.0),    # 0 back positions
        quad(-7.0, -0.5, -7.0, 7.0, 0.0),    # 1 shell positions
        quad(0.5, 7.0, -7.0, 7.0, 0.0),      # 2 cutout positions
        nrm,                                 # 3 shared normals
        idx,                                 # 4 shared indices
        uv,                                  # 5 cutout texcoords
        png_bytes,                           # 6 embedded PNG
    ]
    bin_data = b''
    views = []
    for block in blocks:
        offset = len(bin_data)
        views.append({'buffer': 0, 'byteOffset': offset,
                      'byteLength': len(block)})
        bin_data += block + b'\x00' * (-len(block) % 4)

    def pos_accessor(view, x0, x1, y0, y1, z):
        return {'bufferView': view, 'componentType': 5126, 'count': 4,
                'type': 'VEC3', 'min': [x0, y0, z], 'max': [x1, y1, z]}

    gltf = {
        'asset': {'version': '2.0', 'generator': 'paxtest_alpha_mask'},
        'scene': 0,
        'scenes': [{'nodes': [0, 1, 2]}],
        'nodes': [
            {'name': 'back', 'mesh': 0},
            {'name': 'shell', 'mesh': 1},
            {'name': 'cutout', 'mesh': 2},
        ],
        'meshes': [
            {'name': 'backMesh', 'primitives': [{
                'attributes': {'POSITION': 0, 'NORMAL': 3},
                'indices': 4, 'material': 0}]},
            {'name': 'shellMesh', 'primitives': [{
                'attributes': {'POSITION': 1, 'NORMAL': 3},
                'indices': 4, 'material': 1}]},
            {'name': 'cutoutMesh', 'primitives': [{
                'attributes': {'POSITION': 2, 'NORMAL': 3,
                               'TEXCOORD_0': 5},
                'indices': 4, 'material': 2}]},
        ],
        'materials': [
            {'name': 'backMat', 'pbrMetallicRoughness': {
                'baseColorFactor': [1.0, 1.0, 1.0, 1.0],
                'metallicFactor': 0.0, 'roughnessFactor': ROUGH}},
            # THE field case: MASK, factor alpha 0, NO texture.
            {'name': 'shellMat', 'alphaMode': 'MASK', 'alphaCutoff': 0.5,
             'pbrMetallicRoughness': {
                 'baseColorFactor': [1.0, 0.0, 0.0, 0.0],
                 'metallicFactor': 0.0, 'roughnessFactor': ROUGH}},
            # The foliage case: MASK, alpha from the texture.
            {'name': 'cutoutMat', 'alphaMode': 'MASK', 'alphaCutoff': 0.5,
             'pbrMetallicRoughness': {
                 'baseColorFactor': [1.0, 0.0, 0.0, 1.0],
                 'baseColorTexture': {'index': 0},
                 'metallicFactor': 0.0, 'roughnessFactor': ROUGH}},
        ],
        'textures': [{'source': 0, 'sampler': 0}],
        'samplers': [{'magFilter': 9728, 'minFilter': 9728,
                      'wrapS': 33071, 'wrapT': 33071}],
        'images': [{'bufferView': 6, 'mimeType': 'image/png'}],
        'buffers': [{'byteLength': len(bin_data)}],
        'bufferViews': views,
        'accessors': [
            pos_accessor(0, -7.0, 7.0, -7.0, 7.0, -2.0),
            pos_accessor(1, -7.0, -0.5, -7.0, 7.0, 0.0),
            pos_accessor(2, 0.5, 7.0, -7.0, 7.0, 0.0),
            {'bufferView': 3, 'componentType': 5126, 'count': 4,
             'type': 'VEC3'},
            {'bufferView': 4, 'componentType': 5123, 'count': 6,
             'type': 'SCALAR'},
            {'bufferView': 5, 'componentType': 5126, 'count': 4,
             'type': 'VEC2'},
        ],
    }

    json_bytes = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
    json_bytes += b' ' * (-len(json_bytes) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_data)
    with open(path, 'wb') as f:
        f.write(b'glTF' + struct.pack('<II', 2, total))
        f.write(struct.pack('<II', len(json_bytes), 0x4E4F534A))
        f.write(json_bytes)
        f.write(struct.pack('<II', len(bin_data), 0x004E4942))
        f.write(bin_data)
    return path


def avg_rgb(img, cx, cy, half=2):
    """Mean (r, g, b) of a small box (dodges dither noise)."""
    r = g = b = 0.0
    n = 0
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            c = img.get_xel(int(cx) + dx, int(cy) + dy)
            r += c[0]
            g += c[1]
            b += c[2]
            n += 1
    return r / n, g / n, b / n


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'alpha_mask')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'apply_alpha_masks'):
        h.report.skip('pipeline has no apply_alpha_masks')
    base = h.base
    curve = common.CURVES['hejl_dawson']
    modern = args.baseline == 'modern'

    try:
        import gltf  # noqa: F401  (loader self-registers on import)
    except Exception as exc:
        h.report.skip(f'panda3d-gltf unavailable: {exc}')
    p3d.BamCache.get_global_ptr().set_active(False)

    os.makedirs(common.OUTPUT_DIR, exist_ok=True)
    glb_path = build_glb(
        os.path.join(common.OUTPUT_DIR, 'alpha_mask_scene.glb'),
        os.path.join(common.OUTPUT_DIR, 'alpha_mask_tex.png'))
    model = base.loader.load_model(
        p3d.Filename.from_os_specific(glb_path).get_fullpath())
    model.reparent_to(base.render)

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(AMB, AMB, AMB, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    h.adapter.update_sun((0, -1, 0), (SUN, SUN, SUN))

    base.camera.set_pos(0, -30, 0)
    base.camera.set_hpr(0, 0, 0)
    h.set_ortho(film_w=16.0, film_h=16.0)

    # Ortho film 16x16 centered on the axis: world x -> px, world z -> py.
    def px(wx):
        return (0.5 + wx / 16.0) * h.win_w

    def py(wz):
        return (0.5 - wz / 16.0) * h.win_h

    # Sample geometry (fact #12 discipline — prove the sample points):
    # the ortho rays are parallel but v_view_position is not, so specular
    # falls off away from the view axis. The analytic check samples the
    # CENTER (v exactly on axis, through the 1-unit gap between the two
    # mask quads); every masked-region check compares against the anchor
    # capture AT THE SAME PIXEL, never across positions.
    P_CENTER = (px(0.0), py(0))     # the gap: back quad, v on axis
    P_SHELL = (px(-3.75), py(0))    # shell quad / back quad behind it
    P_KEPT = (px(2.1), py(0))       # cutout u~0.25 (texture alpha 1)
    P_CUT = (px(5.6), py(0))        # cutout u~0.78 (texture alpha 0)
    want_lit = analytic_lit(curve)

    # --- 1. Loader premise: the two MASK geoms carry the attrib ---------
    masked = pipeline._find_alpha_mask_geoms(model)
    h.report.check('loader_stamps_alpha_test', len(masked) == 2,
                   f'{len(masked)} geoms carry keep-if-greater '
                   f'AlphaTestAttrib (want 2: shell + cutout, never the '
                   f'opaque back quad)')

    # --- Anchor: the back quad alone (masks stashed) --------------------
    shell_np = model.find('**/shell')
    cutout_np = model.find('**/cutout')
    shell_np.stash()
    cutout_np.stash()
    h.step(5)
    img_anchor = h.capture()
    h.save_capture(img_anchor, 'anchor_back_only')
    anchor_center = avg_rgb(img_anchor, *P_CENTER)
    anchor_shell = avg_rgb(img_anchor, *P_SHELL)
    anchor_kept = avg_rgb(img_anchor, *P_KEPT)
    anchor_cut = avg_rgb(img_anchor, *P_CUT)
    h.report.check('anchor_back_lit',
                   abs(anchor_center[0] - want_lit) < 0.04
                   and abs(anchor_center[1] - want_lit) < 0.04,
                   f'back quad center rgb=({anchor_center[0]:.3f}, '
                   f'{anchor_center[1]:.3f}, {anchor_center[2]:.3f}), '
                   f'analytic {want_lit:.3f} (v on axis only here)')
    shell_np.unstash()
    cutout_np.unstash()

    # --- 2. Pre-API behavior: the baseline divergence, documented -------
    h.step(5)
    img_pre = h.capture()
    h.save_capture(img_pre, 'pre_api')
    pre_shell = avg_rgb(img_pre, *P_SHELL)
    pre_cut = avg_rgb(img_pre, *P_CUT)
    if modern:
        # The defect: attrib ignored, the red-diffuse quads draw solid.
        # Signature = the green channel collapses vs the same pixel of
        # the white anchor (specular stays gray, so full red-dominance
        # never happens — measured 2026-07-19).
        broken = (anchor_shell[1] - pre_shell[1] > 0.1
                  and anchor_cut[1] - pre_cut[1] > 0.1)
        h.report.check(
            'modern_prefix_defect_present', broken,
            f'gl 3 2 without the API: shell g={pre_shell[1]:.3f} / '
            f'cutout-alpha0 g={pre_cut[1]:.3f} vs anchor '
            f'{anchor_shell[1]:.3f}/{anchor_cut[1]:.3f} — MASK ignored, '
            f'renders solid (the field report). If this ever masks, the '
            f'engine grew core-profile alpha test: true up this test')
    else:
        # Compat already masks via GL_ALPHA_TEST on the output alpha.
        works = (abs(pre_shell[1] - anchor_shell[1]) < 0.02
                 and abs(pre_cut[1] - anchor_cut[1]) < 0.02)
        h.report.check(
            'compat_prefix_fixed_function_masks', works,
            f'compat without the API: shell g={pre_shell[1]:.3f} / '
            f'cutout-alpha0 g={pre_cut[1]:.3f} vs anchor '
            f'{anchor_shell[1]:.3f}/{anchor_cut[1]:.3f} (fixed-function '
            f'GL_ALPHA_TEST already discards)')

    # --- 3. The API scans exactly the masked geoms, idempotently --------
    n = pipeline.apply_alpha_masks(model)
    n2 = pipeline.apply_alpha_masks(model)
    h.report.check('api_finds_masked_geoms', n == 2 and n2 == 2,
                   f'apply_alpha_masks -> {n}, again -> {n2} (want 2, '
                   f'idempotent)')

    # --- 4/5. Post-API: both baselines mask identically -----------------
    h.step(5)
    img_post = h.capture()
    h.save_capture(img_post, 'post_api')
    post_shell = avg_rgb(img_post, *P_SHELL)
    post_kept = avg_rgb(img_post, *P_KEPT)
    post_cut = avg_rgb(img_post, *P_CUT)
    h.report.check('mask_alpha0_discards',
                   abs(post_shell[0] - anchor_shell[0]) < 0.02
                   and abs(post_shell[1] - anchor_shell[1]) < 0.02,
                   f'shell region rgb=({post_shell[0]:.3f}, '
                   f'{post_shell[1]:.3f}, {post_shell[2]:.3f}) vs anchor '
                   f'({anchor_shell[0]:.3f}, {anchor_shell[1]:.3f}, '
                   f'{anchor_shell[2]:.3f}) — the textureless alpha-0 '
                   f'shell vanishes (THE field case)')
    h.report.check('cutout_kept_half',
                   post_kept[0] - post_kept[1] > 0.08
                   and anchor_kept[1] - post_kept[1] > 0.08,
                   f'kept half rgb=({post_kept[0]:.3f}, '
                   f'{post_kept[1]:.3f}, {post_kept[2]:.3f}) — red-tinted '
                   f'(gray specular rides on top), g below anchor '
                   f'{anchor_kept[1]:.3f}: drawn, not discarded')
    h.report.check('cutout_discarded_half',
                   abs(post_cut[0] - anchor_cut[0]) < 0.02
                   and abs(post_cut[1] - anchor_cut[1]) < 0.02,
                   f'discarded half rgb=({post_cut[0]:.3f}, '
                   f'{post_cut[1]:.3f}, {post_cut[2]:.3f}) vs anchor '
                   f'({anchor_cut[0]:.3f}, {anchor_cut[1]:.3f}, '
                   f'{anchor_cut[2]:.3f}) — texture alpha 0 discards')

    # --- 6. Compat: the in-shader test cannot change a pixel ------------
    if not modern:
        rms = common.image_rms_diff(img_pre, img_post, step=1)
        h.report.check('compat_bit_identical', rms == 0.0,
                       f'compat pre vs post API: rms={rms:.2e} (same '
                       f'predicate, double-applied)')

    # --- 7. Recompile-class toggle keeps the masks ----------------------
    pipeline.set_double_sided_lighting(True)
    h.step(5)
    img_toggled = h.capture()
    tog_shell = avg_rgb(img_toggled, *P_SHELL)
    h.report.check('variant_tracks_recompile',
                   abs(tog_shell[1] - anchor_shell[1]) < 0.04,
                   f'shell region g={tog_shell[1]:.3f} vs anchor '
                   f'{anchor_shell[1]:.3f} after a recompile-class toggle '
                   f'(the glass discipline)')
    pipeline.set_double_sided_lighting(False)
    h.step(5)
    img_back = h.capture()
    rms = common.image_rms_diff(img_post, img_back, step=1)
    h.report.check('recompile_roundtrip_identical', rms == 0.0,
                   f'double_sided on->off vs post-API: rms={rms:.2e} '
                   f'(front-facing quads cannot change)')

    # --- 8. Opt-out restores the pre-API state byte-identically ---------
    n_off = pipeline.apply_alpha_masks(model, False)
    h.step(5)
    img_restored = h.capture()
    h.save_capture(img_restored, 'optout')
    rms = common.image_rms_diff(img_pre, img_restored, step=1)
    h.report.check('optout_restores_exactly',
                   n_off == 2 and rms == 0.0,
                   f'apply_alpha_masks(False) -> {n_off}, rms vs pre-API '
                   f'= {rms:.2e} (on @modern this restores the DEFECT — '
                   f'exact restore is the contract)')

    h.report.finish()


if __name__ == '__main__':
    main()
