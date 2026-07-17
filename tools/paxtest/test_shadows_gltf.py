"""paxtest: lit-pass shadows with glTF-material geometry as BOTH caster
and receiver (openworld ask #2, 2026-07-17).

The evening "P0 shadows vanish" report proved flat-color scenes cannot
catch a class of defect where glTF-material geometry stops receiving
shadows even though the depth map is correct (root cause there was a
contaminated tree, but the coverage gap was real). This test closes it:

- The receiver is a TEXTURED glTF ground plane loaded through
  panda3d-gltf (real baseColorTexture sampling path, not
  apply_flat_pbr_surface).
- The casters are (a) a glTF box from the same file and (b) a real
  panda3d-gltf character (when the asset pack is present).
- The sun is at 45 degrees elevation — the angled-sun case the original
  test_shadows never exercised (its occluder trick only worked overhead).

The scene .gltf is synthesized in-code (no external asset needed for the
core checks) and written to the output dir. Only meaningful for pipelines
with sun_light_mode='directional'; others skip. Skips if panda3d-gltf is
not importable in this environment.
"""
import argparse
import base64
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


GLTF_SCENE_NAME = 'paxtest_gltf_shadow_scene.gltf'
GLTF_TEX_NAME = 'paxtest_gltf_white.png'
GROUND_HALF = 10.0
BOX_Z = 3.0          # box center height (Panda Z-up world units)
SUN_ELEV_DEG = 45.0  # angled sun: shadow of a point at height h lands h away


def _write_white_png(path):
    img = p3d.PNMImage(2, 2)
    img.fill(1.0, 1.0, 1.0)
    if not img.write(p3d.Filename.from_os_specific(path)):
        raise RuntimeError('could not write test texture')


def _build_gltf_scene(gltf_path, tex_name):
    """Synthesize a two-node glTF: 'ground' (textured plane, +Y normal in
    glTF space -> +Z in Panda) and 'box' (unit cube at the glTF origin).
    Both use pbrMetallicRoughness materials WITH a baseColorTexture so the
    full glTF material path (texture sampling included) is exercised."""
    s = GROUND_HALF
    # Ground: glTF X-Z plane at y=0 (Panda: X-Y plane at z=0), CCW from +Y.
    g_pos = [(-s, 0.0, -s), (s, 0.0, -s), (s, 0.0, s), (-s, 0.0, s)]
    g_nrm = [(0.0, 1.0, 0.0)] * 4
    g_uv = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    g_idx = [0, 2, 1, 0, 3, 2]

    # Unit cube centered at the glTF origin, per-face normals, CCW outward.
    b_pos, b_nrm, b_uv, b_idx = [], [], [], []
    h = 0.5
    faces = [
        ((0, 0, 1), [(-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h)]),
        ((0, 0, -1), [(h, -h, -h), (-h, -h, -h), (-h, h, -h), (h, h, -h)]),
        ((1, 0, 0), [(h, -h, h), (h, -h, -h), (h, h, -h), (h, h, h)]),
        ((-1, 0, 0), [(-h, -h, -h), (-h, -h, h), (-h, h, h), (-h, h, -h)]),
        ((0, 1, 0), [(-h, h, h), (h, h, h), (h, h, -h), (-h, h, -h)]),
        ((0, -1, 0), [(-h, -h, -h), (h, -h, -h), (h, -h, h), (-h, -h, h)]),
    ]
    for normal, quad in faces:
        start = len(b_pos)
        b_pos.extend(quad)
        b_nrm.extend([normal] * 4)
        b_uv.extend([(0, 0), (1, 0), (1, 1), (0, 1)])
        b_idx.extend([start, start + 1, start + 2,
                      start, start + 2, start + 3])

    def floats(seq):
        return b''.join(struct.pack('<' + 'f' * len(v), *v) for v in seq)

    def shorts(seq):
        return b''.join(struct.pack('<H', i) for i in seq)

    blobs = [floats(g_pos), floats(g_nrm), floats(g_uv), shorts(g_idx),
             floats(b_pos), floats(b_nrm), floats(b_uv), shorts(b_idx)]
    buffer_views = []
    accessors = []
    data = b''
    for i, blob in enumerate(blobs):
        while len(data) % 4:
            data += b'\x00'
        is_index = i in (3, 7)
        buffer_views.append({
            'buffer': 0, 'byteOffset': len(data), 'byteLength': len(blob),
            'target': 34963 if is_index else 34962,
        })
        data += blob

    def add_accessor(view, count, ctype, comp, vmin=None, vmax=None):
        acc = {'bufferView': view, 'componentType': comp,
               'count': count, 'type': ctype}
        if vmin is not None:
            acc['min'] = vmin
            acc['max'] = vmax
        accessors.append(acc)
        return len(accessors) - 1

    def bounds(seq):
        lo = [min(v[i] for v in seq) for i in range(3)]
        hi = [max(v[i] for v in seq) for i in range(3)]
        return lo, hi

    g_lo, g_hi = bounds(g_pos)
    b_lo, b_hi = bounds(b_pos)
    acc = {
        'g_pos': add_accessor(0, len(g_pos), 'VEC3', 5126, g_lo, g_hi),
        'g_nrm': add_accessor(1, len(g_nrm), 'VEC3', 5126),
        'g_uv': add_accessor(2, len(g_uv), 'VEC2', 5126),
        'g_idx': add_accessor(3, len(g_idx), 'SCALAR', 5123),
        'b_pos': add_accessor(4, len(b_pos), 'VEC3', 5126, b_lo, b_hi),
        'b_nrm': add_accessor(5, len(b_nrm), 'VEC3', 5126),
        'b_uv': add_accessor(6, len(b_uv), 'VEC2', 5126),
        'b_idx': add_accessor(7, len(b_idx), 'SCALAR', 5123),
    }

    def material(name, gray):
        return {
            'name': name,
            'pbrMetallicRoughness': {
                'baseColorFactor': [gray, gray, gray, 1.0],
                'baseColorTexture': {'index': 0},
                'metallicFactor': 0.0,
                'roughnessFactor': 0.9,
            },
        }

    doc = {
        'asset': {'version': '2.0', 'generator': 'paxtest'},
        'scene': 0,
        'scenes': [{'nodes': [0, 1]}],
        'nodes': [
            {'name': 'ground', 'mesh': 0},
            {'name': 'box', 'mesh': 1},
        ],
        'meshes': [
            {'name': 'ground_mesh', 'primitives': [{
                'attributes': {'POSITION': acc['g_pos'],
                               'NORMAL': acc['g_nrm'],
                               'TEXCOORD_0': acc['g_uv']},
                'indices': acc['g_idx'], 'material': 0}]},
            {'name': 'box_mesh', 'primitives': [{
                'attributes': {'POSITION': acc['b_pos'],
                               'NORMAL': acc['b_nrm'],
                               'TEXCOORD_0': acc['b_uv']},
                'indices': acc['b_idx'], 'material': 1}]},
        ],
        'materials': [material('ground_mat', 0.8), material('box_mat', 0.6)],
        'textures': [{'source': 0, 'sampler': 0}],
        'samplers': [{'magFilter': 9728, 'minFilter': 9728}],
        'images': [{'uri': tex_name}],
        'buffers': [{
            'byteLength': len(data),
            'uri': 'data:application/octet-stream;base64,'
                   + base64.b64encode(data).decode('ascii'),
        }],
        'bufferViews': buffer_views,
        'accessors': accessors,
    }
    with open(gltf_path, 'w', encoding='utf8') as f:
        json.dump(doc, f)


def _has_texture_and_material(np):
    """True if some Geom under np carries BOTH a TextureAttrib and a
    MaterialAttrib — i.e. it really is texture-mapped glTF-material
    geometry, not silently degraded flat-color. panda3d-gltf puts the
    material on the per-Geom state inside the GeomNode, so compose that
    with the net state before checking."""
    for geom_np in np.find_all_matches('**/+GeomNode'):
        net = geom_np.get_net_state()
        gnode = geom_np.node()
        for i in range(gnode.get_num_geoms()):
            state = net.compose(gnode.get_geom_state(i))
            if not (state.has_attrib(p3d.TextureAttrib)
                    and state.has_attrib(p3d.MaterialAttrib)):
                continue
            tex_attrib = state.get_attrib(p3d.TextureAttrib)
            if tex_attrib.get_num_on_stages() > 0:
                return True
    return False


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'shadows_gltf')
    if not getattr(h.adapter, 'supports_sun_modes', False):
        h.report.skip('pipeline has no directional sun mode')
    try:
        import gltf as gltf_mod
    except ImportError as exc:
        h.report.skip(f'panda3d-gltf not importable: {exc}')

    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode='directional', shadows=True,
                    extra_pipeline_kwargs={'shadow_map_size': 1024})
    pipeline = h.adapter.pipeline
    pipeline.set_shadow_extent(12, 60)

    base = h.base
    if hasattr(gltf_mod, 'patch_loader'):
        gltf_mod.patch_loader(base.loader)

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(0.02, 0.02, 0.02, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    # Synthesize + load the glTF scene (textured ground plane + box).
    os.makedirs(common.OUTPUT_DIR, exist_ok=True)
    tex_path = os.path.join(common.OUTPUT_DIR, GLTF_TEX_NAME)
    gltf_path = os.path.join(common.OUTPUT_DIR, GLTF_SCENE_NAME)
    _write_white_png(tex_path)
    _build_gltf_scene(gltf_path, GLTF_TEX_NAME)
    scene_np = base.loader.load_model(
        p3d.Filename.from_os_specific(gltf_path))
    scene_np.reparent_to(base.render)

    ground_np = scene_np.find('**/ground')
    box_np = scene_np.find('**/box')
    h.report.check('gltf_scene_loaded',
                   not ground_np.is_empty() and not box_np.is_empty(),
                   f'ground={not ground_np.is_empty()} '
                   f'box={not box_np.is_empty()}')
    h.report.check('receiver_is_gltf_material',
                   _has_texture_and_material(ground_np),
                   'ground carries TextureAttrib + MaterialAttrib '
                   '(texture-sampling glTF path, not flat color)')
    h.report.check('caster_is_gltf_material',
                   _has_texture_and_material(box_np),
                   'box carries TextureAttrib + MaterialAttrib')

    box_np.set_pos(base.render, 0, 0, BOX_Z)

    # Top-down ortho view: world (x, y) -> pixel, 1 unit = win_h/16 px.
    base.camera.set_pos(0, 0, 30)
    base.camera.set_hpr(0, -90, 0)
    film = 16.0
    h.set_ortho(film_h=film)
    scale = h.win_h / film

    def to_px(wx, wy):
        return (int(h.win_w / 2 + wx * scale),
                int(h.win_h / 2 - wy * scale))

    # Sun at 45 degrees elevation from +X: a caster at height z shadows
    # the ground at (-z, 0) — the angled case test_shadows never covered.
    elev = math.radians(SUN_ELEV_DEG)
    h.adapter.update_sun((math.cos(elev), 0, math.sin(elev)), (3, 3, 3))

    shadow_px = to_px(-BOX_Z, 0)     # box shadow center
    lit_px = to_px(0, 5)             # open ground, away from all shadows

    def snap(tag):
        h.step(4)
        img = h.capture()
        h.save_capture(img, tag)
        return img

    img = snap('on')
    lit_on = common.avg_lum(img, lit_px[0], lit_px[1], half=3)
    shadow_on = common.avg_lum(img, shadow_px[0], shadow_px[1], half=3)

    pipeline.set_enable_shadows(False)
    img = snap('off')
    shadow_off = common.avg_lum(img, shadow_px[0], shadow_px[1], half=3)
    pipeline.set_enable_shadows(True)

    h.report.check('gltf_ground_lit_bright', lit_on > 0.3,
                   f'open-ground lum={lit_on:.3f} with shadows on '
                   f'(textured glTF receiver renders lit)')
    h.report.check('gltf_box_shadows_gltf_ground',
                   shadow_on < 0.5 * max(shadow_off, 1e-4),
                   f'shadow-point lum {shadow_off:.3f} (shadows off) -> '
                   f'{shadow_on:.3f} (on); 45-degree sun, glTF caster '
                   f'AND receiver')

    # --- Real character as caster over the glTF ground ------------------
    # f_1.glb (pack 1, the Session-E-settled asset) posed at a fixed frame,
    # feet on the plane; its shadow must darken the textured glTF ground.
    glb = r'C:\python\openworld\3D assets\Casual Characters\f_1.glb'
    if os.path.exists(glb):
        from direct.actor.Actor import Actor
        actor = Actor(p3d.Filename.from_os_specific(glb).get_fullpath())
        anims = actor.get_anim_names()
        if anims:
            actor.pose(anims[0], 10)   # frozen pose: comparable captures
        actor.reparent_to(base.render)
        lo, hi = p3d.Point3(), p3d.Point3()
        actor.calc_tight_bounds(lo, hi)
        height = hi.z - lo.z
        actor.set_pos(base.render, 4, 0, actor.get_z() - lo.z)
        h.step(2)

        # 45-degree sun: shadow band stretches from the feet to one body
        # height in -x. Sample mid-band.
        actor_shadow_px = to_px(4 - 0.5 * height, 0)
        img = snap('actor_on')
        act_on = common.avg_lum(img, actor_shadow_px[0],
                                actor_shadow_px[1], half=3)
        pipeline.set_enable_shadows(False)
        img = snap('actor_off')
        act_off = common.avg_lum(img, actor_shadow_px[0],
                                 actor_shadow_px[1], half=3)
        pipeline.set_enable_shadows(True)
        h.report.check('gltf_actor_shadows_gltf_ground',
                       act_on < 0.5 * max(act_off, 1e-4),
                       f'actor-shadow lum {act_off:.3f} (off) -> '
                       f'{act_on:.3f} (on); height={height:.2f}, '
                       f'{os.path.basename(glb)}')
    else:
        h.report.info('gltf_actor_caster',
                      f'asset pack not present ({glb}) — box-only run')

    h.report.finish()


if __name__ == '__main__':
    main()
