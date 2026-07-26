"""paxtest: per-geom character detail maps (ER-014, set_detail_maps).

The pipeline ships USE_NORMAL_MAP / USE_OCCLUSION_MAP globally OFF:
flipping them globally is unsafe (the TBN rotation NaN-blacks any
tangentless procedural geometry — ER-012 established there is no
draw-time derivative fallback) and the cost scoping is characters-only.
Character GLBs ship full Normal + ORM sets that were never sampled
in-world (session 695 field diagnosis: heroes look better in the
npc_viewer preview, which runs its own use_normal_maps=True pipeline,
than in the world).

`pipeline.set_detail_maps(model_np)` composes the NORMAL/OCCLUSION
defines per geom, following the apply_alpha_masks discipline: only
where a normal-map texture stage AND a tangent column exist (normal) /
a metal-rough ORM stage exists (occlusion, .r channel), skipping geoms
that already carry a variant shader (ALPHA_MASK hair cards, GLASS,
GPU_MORPHS).

Scene (authored GLB through the real loader, ortho camera, sun on the
view axis): four quads — 'norm' (tilted-constant normal map + explicit
TANGENT), 'occ' (ORM texture, occlusion .r = 0.25), 'mask' (alphaMode
MASK + normal map + TANGENT: the hair-card analog), 'plain' (no
textures) — plus a procedural CardMaker card carrying a hand-bound
M_normal stage but NO tangent column (the NaN-black guard case).

Checks:
  1. Selection: exactly norm + occ take the variant (mask skipped —
     already ALPHA_MASK'd; plain has nothing); idempotent.
  2. Tangentless guard: the procedural card binds a normal-map stage
     but has no tangent column -> set_detail_maps refuses it (0).
  3. Normal map renders: the norm quad's shading changes measurably
     (tilted normal, darker on-axis) after the API.
  4. Occlusion renders: the occ quad's ambient term drops to .r of the
     ORM texture — analytic-exact against the BRDF + hejl curve.
  5. Recompile-class toggle (double_sided_lighting) keeps the variants
     and round-trips bit-identically (the glass discipline).
  6. Reconfigure in place: normal=True, occlusion=False drops the occ
     quad back to baseline; re-calling with both restores bit-exactly.
  7. THE ER-014 composition contract: set_hardware_skinning(np, False)
     (the hero face-range CPU valve) must NOT blanket the variant.
     The raw-attrib trap is measured first (a flag-only override-2
     attrib reverts the geom to the base shader — why the pipeline
     coordinates the two APIs), then the API path: bit-identical
     render with the valve on, valve node tagged for the depth-pass
     rescue, bit-identical restore + no attrib residue after
     clear_hardware_skinning.
  8. Opt-out restores the pre-API capture byte-identically.

Directional-variant run (--sun-mode directional, from run.py) adds the
shadow interplay: with shadows enabled, flipping the valve on a
detail-mapped caster must not change a pixel — the shadow-camera tag
state (override 3) keeps the depth pass on the shadow shader while the
override-2 geom stamp wins the color pass. The --log-depth directional
run is the leak detector: a color-pass variant leaking into the depth
pass would write log-space gl_FragDepth into the (linear) shadow map
and visibly corrupt the shadow.

Only meaningful for pipelines exposing set_detail_maps (pax3d_render).
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


ROUGH = 0.3         # material roughness where no ORM texture exists
SUN = 0.6           # sun intensity
AMB = 0.25          # ambient — large enough to measure the AO cut
F0 = 0.04

# ORM texture channels (8-bit quantized values used in the analytics)
OCC_R = 64 / 255.0      # occlusion 0.251
OCC_G = 77 / 255.0      # roughness 0.302
OCC_B = 0               # metallic 0

# Normal-map constant color: nx = 217/255*2-1 = 0.702 (tilted in +x)
NORM_R = 217


def analytic_lit(curve, rough, ao):
    """Shader output at n=l=v=h (all dots exactly 1) for a white
    non-metal quad: SUN*(diffuse+specular BRDF) + AMB*ao*(diffuse_color
    + spec_color) where diffuse_color+spec_color = 1.0 (white albedo,
    metallic 0). BRDF terms as proven in test_glass/test_alpha_mask."""
    f = F0 + (1.0 - F0) * 2.0 ** (-5.55473 - 6.98316)
    spec = f * 0.25 * (1.0 / (math.pi * rough ** 4))
    diff = (1.0 - F0) / math.pi
    return curve(SUN * (diff + spec) + AMB * ao)


# ----------------------------------------------------------------------
# Synthetic GLB: norm / occ / mask / plain quads. glTF axes:
# (x, y, z)_gltf -> (x, -z, y)_panda, so quads in the glTF XY plane face
# the -Y camera.
# ----------------------------------------------------------------------

def build_normal_png(path):
    """8x8 constant tilted normal: RGB (217, 128, 255)."""
    img = p3d.PNMImage(8, 8)
    img.fill(NORM_R / 255.0, 128 / 255.0, 1.0)
    img.write(p3d.Filename.from_os_specific(path))
    with open(path, 'rb') as f:
        return f.read()


def build_orm_png(path):
    """8x8 constant ORM: R=64 (occlusion .25), G=77 (rough .30), B=0."""
    img = p3d.PNMImage(8, 8)
    img.fill(64 / 255.0, 77 / 255.0, 0.0)
    img.write(p3d.Filename.from_os_specific(path))
    with open(path, 'rb') as f:
        return f.read()


def build_glb(path, norm_png_path, orm_png_path):
    def f32(*vals):
        return struct.pack('<%df' % len(vals), *vals)

    def quad(x0, x1):
        return f32(x0, -3.0, 0.0,  x1, -3.0, 0.0,
                   x1, 3.0, 0.0,  x0, 3.0, 0.0)

    nrm = f32(0.0, 0.0, 1.0) * 4
    tan = f32(1.0, 0.0, 0.0, 1.0) * 4
    idx = struct.pack('<6H', 0, 1, 2, 0, 2, 3)
    uv = f32(0.0, 1.0,  1.0, 1.0,  1.0, 0.0,  0.0, 0.0)
    norm_png = build_normal_png(norm_png_path)
    orm_png = build_orm_png(orm_png_path)

    blocks = [
        quad(-7.0, -4.0),   # 0 norm positions
        quad(-1.5, 1.5),    # 1 occ positions (ON the view axis: its
                            #   checks are analytic, and ortho specular
                            #   droops off-axis — fact #12 discipline)
        quad(2.5, 5.0),     # 2 mask positions
        quad(5.5, 7.5),     # 3 plain positions
        nrm,                # 4 shared normals
        tan,                # 5 shared tangents (norm + mask)
        idx,                # 6 shared indices
        uv,                 # 7 shared texcoords
        norm_png,           # 8 normal-map PNG
        orm_png,            # 9 ORM PNG
    ]
    bin_data = b''
    views = []
    for block in blocks:
        offset = len(bin_data)
        views.append({'buffer': 0, 'byteOffset': offset,
                      'byteLength': len(block)})
        bin_data += block + b'\x00' * (-len(block) % 4)

    def pos_accessor(view, x0, x1):
        return {'bufferView': view, 'componentType': 5126, 'count': 4,
                'type': 'VEC3', 'min': [x0, -3.0, 0.0],
                'max': [x1, 3.0, 0.0]}

    gltf = {
        'asset': {'version': '2.0', 'generator': 'paxtest_detail_maps'},
        'scene': 0,
        'scenes': [{'nodes': [0, 1, 2, 3]}],
        'nodes': [
            {'name': 'norm', 'mesh': 0},
            {'name': 'occ', 'mesh': 1},
            {'name': 'mask', 'mesh': 2},
            {'name': 'plain', 'mesh': 3},
        ],
        'meshes': [
            {'name': 'normMesh', 'primitives': [{
                'attributes': {'POSITION': 0, 'NORMAL': 4, 'TANGENT': 5,
                               'TEXCOORD_0': 7},
                'indices': 6, 'material': 0}]},
            {'name': 'occMesh', 'primitives': [{
                'attributes': {'POSITION': 1, 'NORMAL': 4,
                               'TEXCOORD_0': 7},
                'indices': 6, 'material': 1}]},
            {'name': 'maskMesh', 'primitives': [{
                'attributes': {'POSITION': 2, 'NORMAL': 4, 'TANGENT': 5,
                               'TEXCOORD_0': 7},
                'indices': 6, 'material': 2}]},
            {'name': 'plainMesh', 'primitives': [{
                'attributes': {'POSITION': 3, 'NORMAL': 4},
                'indices': 6, 'material': 3}]},
        ],
        'materials': [
            # Tilted-constant normal map; roughness from the factor.
            {'name': 'normMat', 'normalTexture': {'index': 0},
             'pbrMetallicRoughness': {
                 'baseColorFactor': [1.0, 1.0, 1.0, 1.0],
                 'metallicFactor': 0.0, 'roughnessFactor': ROUGH}},
            # Combined ORM texture; factors 1 so the texture channels
            # carry rough/metal (the glTF multiply convention).
            {'name': 'occMat', 'pbrMetallicRoughness': {
                'baseColorFactor': [1.0, 1.0, 1.0, 1.0],
                'metallicRoughnessTexture': {'index': 1},
                'metallicFactor': 1.0, 'roughnessFactor': 1.0}},
            # The hair-card analog: MASK material carrying a normal
            # map — apply_alpha_masks claims the geom first and
            # set_detail_maps must then skip it.
            {'name': 'maskMat', 'alphaMode': 'MASK', 'alphaCutoff': 0.5,
             'normalTexture': {'index': 0},
             'pbrMetallicRoughness': {
                 'baseColorFactor': [1.0, 1.0, 1.0, 1.0],
                 'metallicFactor': 0.0, 'roughnessFactor': ROUGH}},
            {'name': 'plainMat', 'pbrMetallicRoughness': {
                'baseColorFactor': [1.0, 1.0, 1.0, 1.0],
                'metallicFactor': 0.0, 'roughnessFactor': ROUGH}},
        ],
        'textures': [{'source': 0, 'sampler': 0},
                     {'source': 1, 'sampler': 0}],
        'samplers': [{'magFilter': 9728, 'minFilter': 9728,
                      'wrapS': 33071, 'wrapT': 33071}],
        'images': [{'bufferView': 8, 'mimeType': 'image/png'},
                   {'bufferView': 9, 'mimeType': 'image/png'}],
        'buffers': [{'byteLength': len(bin_data)}],
        'bufferViews': views,
        'accessors': [
            pos_accessor(0, -7.0, -4.0),
            pos_accessor(1, -1.5, 1.5),
            pos_accessor(2, 2.5, 5.0),
            pos_accessor(3, 5.5, 7.5),
            {'bufferView': 4, 'componentType': 5126, 'count': 4,
             'type': 'VEC3'},
            {'bufferView': 5, 'componentType': 5126, 'count': 4,
             'type': 'VEC4'},
            {'bufferView': 6, 'componentType': 5123, 'count': 6,
             'type': 'SCALAR'},
            {'bufferView': 7, 'componentType': 5126, 'count': 4,
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
    parser.add_argument('--sun-mode', default=None,
                        choices=['uniforms', 'directional'])
    parser.add_argument('--log-depth', action='store_true')
    args = parser.parse_args()

    directional = args.sun_mode == 'directional'
    h = common.Harness(args, 'detail_maps')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode, shadows=directional,
                    log_depth=args.log_depth)
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'set_detail_maps'):
        h.report.skip('pipeline has no set_detail_maps')
    base = h.base
    curve = common.CURVES['hejl_dawson']

    try:
        import gltf  # noqa: F401  (loader self-registers on import)
    except Exception as exc:
        h.report.skip(f'panda3d-gltf unavailable: {exc}')
    p3d.BamCache.get_global_ptr().set_active(False)

    os.makedirs(common.OUTPUT_DIR, exist_ok=True)
    glb_path = build_glb(
        os.path.join(common.OUTPUT_DIR, 'detail_maps_scene.glb'),
        os.path.join(common.OUTPUT_DIR, 'detail_maps_norm.png'),
        os.path.join(common.OUTPUT_DIR, 'detail_maps_orm.png'))
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

    def px(wx):
        return (0.5 + wx / 16.0) * h.win_w

    def py(wz):
        return (0.5 - wz / 16.0) * h.win_h

    P_NORM = (px(-5.5), py(0))
    P_OCC = (px(0.0), py(0))    # exactly on the view axis (analytic)
    P_MASK = (px(3.75), py(0))
    P_PLAIN = (px(6.5), py(0))
    P_CARD = (px(-5.5), py(-4.75))

    # The procedural tangentless card: a hand-bound M_normal stage on
    # CardMaker geometry (no tangent column) — the class of geometry
    # that made the global flip unsafe.
    norm_tex = base.loader.load_texture(p3d.Filename.from_os_specific(
        os.path.join(common.OUTPUT_DIR, 'detail_maps_norm.png')))
    card_cm = p3d.CardMaker('proc_card')
    card_cm.set_frame(-7.0, -4.0, -6.0, -3.5)
    card = base.render.attach_new_node(card_cm.generate())
    card_mat = p3d.Material('card_mat')
    card_mat.set_base_color(p3d.LColor(1, 1, 1, 1))
    card_mat.set_metallic(0.0)
    card_mat.set_roughness(ROUGH)
    card.set_material(card_mat, 1)
    norm_stage = p3d.TextureStage('card_normal')
    norm_stage.set_mode(p3d.TextureStage.M_normal)
    card.set_texture(norm_stage, norm_tex)

    # --- Anchors: everything flat-lit, before any API -------------------
    h.step(5)
    img_pre = h.capture()
    h.save_capture(img_pre, 'pre_api')
    pre_norm = avg_rgb(img_pre, *P_NORM)
    pre_occ = avg_rgb(img_pre, *P_OCC)
    pre_mask = avg_rgb(img_pre, *P_MASK)
    pre_plain = avg_rgb(img_pre, *P_PLAIN)
    want_flat = analytic_lit(curve, ROUGH, 1.0)
    want_occ_pre = analytic_lit(curve, OCC_G, 1.0)
    # Sample geometry (fact #12 discipline): only the occ quad sits ON
    # the view axis, so only its checks are analytic-exact — ortho rays
    # are parallel but v_view_position is not, and specular droops
    # off-axis (~0.06 at |x|=6, measured). Off-axis quads get a droop
    # tolerance here and RELATIVE checks (same pixel, before vs after)
    # everywhere else.
    h.report.check('anchor_flat_lit',
                   abs(pre_plain[1] - want_flat) < 0.1
                   and abs(pre_norm[1] - want_flat) < 0.1,
                   f'plain g={pre_plain[1]:.3f} / norm g={pre_norm[1]:.3f}'
                   f' vs analytic {want_flat:.3f} (defines off: normal '
                   f'map and tangents ignored; off-axis droop tolerated)')
    h.report.check('anchor_orm_rough_read',
                   abs(pre_occ[1] - want_occ_pre) < 0.04,
                   f'occ quad g={pre_occ[1]:.3f} vs analytic '
                   f'{want_occ_pre:.3f} (on-axis; metal_rough .g already '
                   f'read pre-variant; .r ignored)')

    # --- Hair-card analog claimed by apply_alpha_masks first ------------
    n_mask = pipeline.apply_alpha_masks(model)
    h.report.check('mask_premise', n_mask == 1,
                   f'apply_alpha_masks -> {n_mask} (want 1: the MASK '
                   f'quad, the hair-card analog)')

    # --- 1/2. Selection ---------------------------------------------------
    n = pipeline.set_detail_maps(model)
    n2 = pipeline.set_detail_maps(model)
    h.report.check('api_selects_exactly', n == 2 and n2 == 2,
                   f'set_detail_maps -> {n}, again -> {n2} (want 2: '
                   f'norm + occ; mask carries the ALPHA_MASK variant, '
                   f'plain has no maps; idempotent)')
    n_card = pipeline.set_detail_maps(card)
    h.report.check('tangentless_guard', n_card == 0,
                   f'set_detail_maps(card) -> {n_card} (M_normal stage '
                   f'bound but no tangent column: refused — the '
                   f'NaN-black class the global flip would hit)')

    # --- 3/4. The maps render --------------------------------------------
    h.step(5)
    img_post = h.capture()
    h.save_capture(img_post, 'post_api')
    post_norm = avg_rgb(img_post, *P_NORM)
    post_occ = avg_rgb(img_post, *P_OCC)
    post_mask = avg_rgb(img_post, *P_MASK)
    post_card = avg_rgb(img_post, *P_CARD)
    pre_card = avg_rgb(img_pre, *P_CARD)
    h.report.check('normal_map_renders',
                   pre_norm[1] - post_norm[1] > 0.05,
                   f'norm quad g {pre_norm[1]:.3f} -> {post_norm[1]:.3f} '
                   f'(constant normal tilted nx=0.702 turns the surface '
                   f'away from the on-axis sun: darker)')
    want_occ_post = analytic_lit(curve, OCC_G, OCC_R)
    h.report.check('occlusion_renders',
                   abs(post_occ[1] - want_occ_post) < 0.04,
                   f'occ quad g={post_occ[1]:.3f} vs analytic '
                   f'{want_occ_post:.3f} (ambient term x ORM .r '
                   f'{OCC_R:.3f}; was {pre_occ[1]:.3f})')
    h.report.check('masked_geom_untouched',
                   abs(post_mask[1] - pre_mask[1]) < 0.02,
                   f'mask quad g {pre_mask[1]:.3f} -> {post_mask[1]:.3f} '
                   f'(ALPHA_MASK variant kept; its normal map stays '
                   f'unsampled — variant stacking is a documented limit)')
    h.report.check('card_untouched',
                   abs(post_card[1] - pre_card[1]) < 0.02,
                   f'card g {pre_card[1]:.3f} -> {post_card[1]:.3f} '
                   f'(refused geom renders exactly as before)')

    # --- 5. Recompile-class toggle keeps the variants ---------------------
    pipeline.set_double_sided_lighting(True)
    h.step(5)
    img_tog = h.capture()
    tog_norm = avg_rgb(img_tog, *P_NORM)
    h.report.check('variant_tracks_recompile',
                   pre_norm[1] - tog_norm[1] > 0.05,
                   f'norm quad g={tog_norm[1]:.3f} still detail-shaded '
                   f'after a recompile-class toggle (the glass '
                   f'discipline)')
    pipeline.set_double_sided_lighting(False)
    h.step(5)
    rms = common.image_rms_diff(img_post, h.capture(), step=1)
    h.report.check('recompile_roundtrip_identical', rms == 0.0,
                   f'double_sided on->off vs post-API: rms={rms:.2e}')

    # --- 6. Reconfigure in place ------------------------------------------
    n_r = pipeline.set_detail_maps(model, normal=True, occlusion=False)
    h.step(5)
    img_reconf = h.capture()
    rec_occ = avg_rgb(img_reconf, *P_OCC)
    rec_norm = avg_rgb(img_reconf, *P_NORM)
    h.report.check('reconfigure_in_place',
                   n_r == 1
                   and abs(rec_occ[1] - pre_occ[1]) < 0.02
                   and pre_norm[1] - rec_norm[1] > 0.05,
                   f'normal-only -> {n_r} geom(s); occ back to baseline '
                   f'(g={rec_occ[1]:.3f} vs {pre_occ[1]:.3f}), norm still '
                   f'detail-shaded')
    n_r2 = pipeline.set_detail_maps(model)
    h.step(5)
    rms = common.image_rms_diff(img_post, h.capture(), step=1)
    h.report.check('reconfigure_roundtrip', n_r2 == 2 and rms == 0.0,
                   f'both maps back -> {n_r2}, rms vs post-API '
                   f'= {rms:.2e}')

    # --- 7. The valve composition contract (ER-014's hard requirement) ----
    norm_np = model.find('**/norm')
    F_skin = p3d.ShaderAttrib.F_hardware_skinning

    # The measured trap: a RAW flag-only attrib at the valve override
    # blankets the geom variant (RenderState parent-override-wins
    # ignores the child attrib wholesale) — the face would go flat
    # exactly in face range. This is why set_hardware_skinning
    # coordinates with the detail registry.
    norm_np.set_attrib(
        p3d.ShaderAttrib.make().set_flag(F_skin, False), 2)
    h.step(5)
    img_trap = h.capture()
    trap_norm = avg_rgb(img_trap, *P_NORM)
    h.report.check('valve_blanket_trap_measured',
                   abs(trap_norm[1] - pre_norm[1]) < 0.02,
                   f'raw override-2 flag attrib: norm quad g='
                   f'{trap_norm[1]:.3f} reverts to flat anchor '
                   f'{pre_norm[1]:.3f} — the blanket, measured (why the '
                   f'valve API re-stamps)')
    norm_np.clear_attrib(p3d.ShaderAttrib)

    # The API path: variant survives, bit-identically (static mesh, so
    # CPU-vs-GPU skinning cannot differ; only the composition could).
    pipeline.set_hardware_skinning(norm_np, False)
    h.step(5)
    img_valve = h.capture()
    h.save_capture(img_valve, 'valve_on')
    rms = common.image_rms_diff(img_post, img_valve, step=1)
    h.report.check('valve_composes_variant', rms == 0.0,
                   f'set_hardware_skinning(np, False) with detail maps '
                   f'on: rms vs post-API = {rms:.2e} (variant + flag '
                   f'both survive the color pass)')
    h.report.check('valve_tags_for_depth_rescue',
                   norm_np.get_tag('pax3d_shadow') == 'shadow',
                   f'valve node tag pax3d_shadow='
                   f'{norm_np.get_tag("pax3d_shadow")!r} (the shadow '
                   f'cameras re-assert the depth shader above the '
                   f'override-2 stamp through this tag)')

    if directional:
        # Shadow interplay: a tilted sun makes the norm quad cast onto
        # a backdrop strip; flipping the valve must not change a pixel.
        # On the --log-depth run this is the leak detector: a
        # color-pass variant in the depth pass writes log-space
        # gl_FragDepth into the linear shadow map and visibly corrupts
        # the shadow. The strip deliberately overlaps NO quad on
        # screen: under log depth the ortho camera writes constant
        # gl_FragDepth (w==1), so overlapping opaque geometry would
        # composite by draw order — which the valve's state change can
        # reorder — not by depth.
        back_cm = p3d.CardMaker('shadow_back')
        back_cm.set_frame(-3.9, -3.1, -8.0, 8.0)
        back = base.render.attach_new_node(back_cm.generate())
        back.set_y(2.0)
        back_mat = p3d.Material('back_mat')
        back_mat.set_base_color(p3d.LColor(1, 1, 1, 1))
        back_mat.set_metallic(0.0)
        back_mat.set_roughness(ROUGH)
        back.set_material(back_mat, 1)
        if hasattr(pipeline, 'set_shadow_extent'):
            pipeline.set_shadow_extent(20.0, depth=40.0)
        h.adapter.update_sun((-0.35, -1, 0), (SUN, SUN, SUN))
        P_SHADOW = (px(-3.6), py(0))    # norm quad's shadow, offset +x

        model.stash()
        h.step(5)
        no_caster = avg_rgb(h.capture(), *P_SHADOW)
        model.unstash()
        h.step(5)
        img_shadow = h.capture()
        h.save_capture(img_shadow, 'shadow_valve')
        with_caster = avg_rgb(img_shadow, *P_SHADOW)
        h.report.check('shadow_premise',
                       no_caster[1] - with_caster[1] > 0.05,
                       f'backdrop g {no_caster[1]:.3f} -> '
                       f'{with_caster[1]:.3f} with the detail-mapped '
                       f'caster unstashed (its shadow lands on the '
                       f'sample)')

        # Valve off/on around the SAME scene: bit-identical or the
        # depth pass leaked.
        pipeline.clear_hardware_skinning(norm_np)
        h.step(5)
        img_novalve = h.capture()
        pipeline.set_hardware_skinning(norm_np, False)
        h.step(5)
        img_revalve = h.capture()
        rms = common.image_rms_diff(img_novalve, img_revalve, step=1)
        h.report.check('valve_shadow_intact', rms == 0.0,
                       f'valve off vs on under shadows'
                       f'{" + log depth" if args.log_depth else ""}: '
                       f'rms={rms:.2e} (tag-state rescue keeps the '
                       f'depth pass on the shadow shader)')
        casters = pipeline._get_all_casters()
        tagged = [c for c in casters
                  if c.get_tag_state_key() == 'pax3d_shadow'
                  and c.has_tag_state('shadow')]
        h.report.check('caster_tag_state_installed',
                       len(casters) > 0 and len(tagged) == len(casters),
                       f'{len(tagged)}/{len(casters)} shadow casters '
                       f'carry the pax3d_shadow tag-state rescue while '
                       f'the valve holds a detail geom')

    # Clearing the valve restores the plain variant stamp, exactly, and
    # leaves NO attrib residue (a left-over empty override-2 attrib
    # would blanket the variant forever).
    pipeline.clear_hardware_skinning(norm_np)
    h.step(5)
    if directional:
        rms = common.image_rms_diff(img_novalve, h.capture(), step=1)
    else:
        rms = common.image_rms_diff(img_post, h.capture(), step=1)
    residue = norm_np.get_attrib(p3d.ShaderAttrib)
    h.report.check('valve_clear_restores',
                   rms == 0.0 and residue is None
                   and not norm_np.has_tag('pax3d_shadow'),
                   f'clear_hardware_skinning: rms={rms:.2e}, node '
                   f'attrib={residue}, tag cleared')
    if directional:
        casters = pipeline._get_all_casters()
        stale = [c for c in casters if c.get_tag_state_key() != '']
        h.report.check('caster_tag_state_removed', not stale,
                       f'{len(stale)}/{len(casters)} casters still keyed '
                       f'after the last valve cleared (want 0 — the '
                       f'per-node tag lookup must cost nothing at rest)')
        # Back to the axis sun + no backdrop for the final restore rms.
        back.remove_node()
        h.adapter.update_sun((0, -1, 0), (SUN, SUN, SUN))

    # --- 8. Opt-out restores the pre-API state byte-identically -----------
    n_off = pipeline.set_detail_maps(model, enabled=False)
    pipeline.apply_alpha_masks(model, False)
    h.step(5)
    img_restored = h.capture()
    h.save_capture(img_restored, 'optout')
    rms = common.image_rms_diff(img_pre, img_restored, step=1)
    h.report.check('optout_restores_exactly', n_off == 2 and rms == 0.0,
                   f'set_detail_maps(False) -> {n_off}, rms vs pre-API '
                   f'= {rms:.2e} (the baked detail goes back to being '
                   f'unsampled — exact restore is the contract)')

    h.report.finish()


if __name__ == '__main__':
    main()
