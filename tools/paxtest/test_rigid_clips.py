"""paxtest: rigid node clips (ER-004 — walkable-ship doors/ramps/gear).

panda3d-gltf 1.3.0 consumes glTF animations only inside
build_character() (skins/morphs); channels targeting PLAIN nodes are
silently dropped — which is every Unity ship-pack door, ramp, drawer
and landing-gear clip (Blender exports object-level actions as exactly
such channels). pax3d_render.rigid_clips reads them straight from the
.glb and plays them onto the loaded nodes, which stay ordinary
PandaNodes.

This test authors a minimal GLB from scratch (known analytic content —
no Blender in the loop), loads it through the real loader, and pins:

  1. The premise: the loader creates plain nodes (no Character) and
     drops the animation — our store is the only motion source.
  2. Axis conversion: the player's key-0 pose equals the LOADER's own
     rest pose for the same nodes (the csxform conjugation contract,
     gltf/_converter.py ~224) — translation, rotation, and scale.
  3. Analytic seeks: end pose, LINEAR midpoint (lerp + slerp via a
     rotated probe child), STEP hold, CUBICSPLINE midpoint (data
     level), reverse scrub, reset().
  4. RigidClip.from_delta — the prefab script-lerp synthesizer
     (Minerva: ~40 parts defined by pos delta + rot delta + duration)
     — composes onto the captured rest pose.
  5. End-to-end: seeking the clip visibly moves the rendered mesh.

Runs under any pipeline exposing get_model_clips (pax3d_render; the
store itself is loader-level, so stock vs Pax3D engines must agree).
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

S45 = math.sin(math.radians(45.0))
C45 = math.cos(math.radians(45.0))


# ----------------------------------------------------------------------
# Synthetic GLB (fixed indices, one buffer)
# ----------------------------------------------------------------------

def build_glb(path):
    def f32(*vals):
        return struct.pack('<%df' % len(vals), *vals)

    quad_pos = f32(-0.5, -0.5, 0.0,  0.5, -0.5, 0.0,
                   0.5, 0.5, 0.0,  -0.5, 0.5, 0.0)
    quad_nrm = f32(0.0, 0.0, 1.0) * 4
    quad_idx = struct.pack('<6H', 0, 1, 2, 0, 2, 3)
    times = f32(0.0, 2.0)
    door_trans = f32(1.0, 2.0, 3.0,  1.0, 4.0, 3.0)
    hatch_rot = f32(0.0, 0.0, 0.0, 1.0,  0.0, S45, 0.0, C45)
    step_scale = f32(1.0, 1.0, 1.0,  2.0, 3.0, 4.0)

    blocks = [quad_pos, quad_nrm, quad_idx, times, door_trans,
              hatch_rot, step_scale]
    bin_data = b''
    views = []
    for block in blocks:
        offset = len(bin_data)
        views.append({'buffer': 0, 'byteOffset': offset,
                      'byteLength': len(block)})
        bin_data += block + b'\x00' * (-len(block) % 4)

    gltf = {
        'asset': {'version': '2.0', 'generator': 'paxtest_rigid_clips'},
        'scene': 0,
        'scenes': [{'nodes': [0]}],
        'nodes': [
            {'name': 'ShipRoot', 'children': [1, 2, 4]},
            {'name': 'DoorPivot', 'translation': [1.0, 2.0, 3.0],
             'mesh': 0},
            {'name': 'Hatch', 'translation': [-2.0, 0.0, 0.0],
             'children': [3]},
            {'name': 'HatchProbe', 'translation': [1.0, 0.0, 0.0]},
            {'name': 'StepNode'},
        ],
        'meshes': [{'name': 'DoorMesh', 'primitives': [{
            'attributes': {'POSITION': 0, 'NORMAL': 1},
            'indices': 2, 'material': 0}]}],
        'materials': [{'name': 'DoorMat', 'pbrMetallicRoughness': {
            'baseColorFactor': [1.0, 1.0, 1.0, 1.0],
            'metallicFactor': 0.0, 'roughnessFactor': 0.9}}],
        'buffers': [{'byteLength': len(bin_data)}],
        'bufferViews': views,
        'accessors': [
            {'bufferView': 0, 'componentType': 5126, 'count': 4,
             'type': 'VEC3', 'min': [-0.5, -0.5, 0.0],
             'max': [0.5, 0.5, 0.0]},
            {'bufferView': 1, 'componentType': 5126, 'count': 4,
             'type': 'VEC3'},
            {'bufferView': 2, 'componentType': 5123, 'count': 6,
             'type': 'SCALAR'},
            {'bufferView': 3, 'componentType': 5126, 'count': 2,
             'type': 'SCALAR', 'min': [0.0], 'max': [2.0]},
            {'bufferView': 4, 'componentType': 5126, 'count': 2,
             'type': 'VEC3'},
            {'bufferView': 5, 'componentType': 5126, 'count': 2,
             'type': 'VEC4'},
            {'bufferView': 6, 'componentType': 5126, 'count': 2,
             'type': 'VEC3'},
        ],
        'animations': [{
            'name': 'DoorOpen',
            'samplers': [
                {'input': 3, 'output': 4, 'interpolation': 'LINEAR'},
                {'input': 3, 'output': 5, 'interpolation': 'LINEAR'},
                {'input': 3, 'output': 6, 'interpolation': 'STEP'},
            ],
            'channels': [
                {'sampler': 0, 'target': {'node': 1,
                                          'path': 'translation'}},
                {'sampler': 1, 'target': {'node': 2, 'path': 'rotation'}},
                {'sampler': 2, 'target': {'node': 4, 'path': 'scale'}},
            ],
        }],
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


def vec_err(got, want):
    return max(abs(got[i] - want[i]) for i in range(len(want)))


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'rigid_clips')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'get_model_clips'):
        h.report.skip('pipeline has no get_model_clips (ER-004)')
    base = h.base
    TOL = 1e-4

    try:
        import gltf  # noqa: F401  (loader self-registers on import)
    except Exception as exc:
        h.report.skip(f'panda3d-gltf unavailable: {exc}')
    p3d.BamCache.get_global_ptr().set_active(False)

    os.makedirs(common.OUTPUT_DIR, exist_ok=True)
    glb_path = build_glb(os.path.join(common.OUTPUT_DIR,
                                      'rigid_clips_ship.glb'))
    model = base.loader.load_model(
        p3d.Filename.from_os_specific(glb_path).get_fullpath())
    model.reparent_to(base.render)

    door = model.find('**/DoorPivot')
    hatch = model.find('**/Hatch')
    probe = model.find('**/HatchProbe')
    stepn = model.find('**/StepNode')

    # --- 1. Premise: plain nodes, no Character, clip dropped ------------
    plain = (not door.is_empty() and not hatch.is_empty()
             and not probe.is_empty() and not stepn.is_empty()
             and model.find('**/+Character').is_empty())
    h.report.check('loader_keeps_plain_nodes', plain,
                   f'door/hatch/probe/step found='
                   f'{[not n.is_empty() for n in (door, hatch, probe, stepn)]}, '
                   f'Character absent='
                   f'{model.find("**/+Character").is_empty()}')
    if not plain:
        h.report.finish()

    # --- 2. The store parses the file the loader just consumed ---------
    clips = pipeline.get_model_clips(model)
    ok = ('DoorOpen' in clips
          and sorted(clips['DoorOpen'].target_names)
          == ['DoorPivot', 'Hatch', 'StepNode']
          and abs(clips['DoorOpen'].duration - 2.0) < TOL)
    h.report.check('clips_parsed', ok,
                   f'clips={sorted(clips)}, targets='
                   f'{sorted(clips["DoorOpen"].target_names) if "DoorOpen" in clips else None}, '
                   f'duration={clips["DoorOpen"].duration if "DoorOpen" in clips else None}')
    if not ok:
        h.report.finish()
    clip = clips['DoorOpen']

    from pax3d_render.rigid_clips import RigidClip, RigidClipPlayer

    rest_door_pos = p3d.LPoint3(door.get_pos())
    rest_hatch_quat = p3d.LQuaternion(hatch.get_quat())
    player = RigidClipPlayer(clip, model)
    h.report.check('targets_resolved',
                   not player.missing and not player.duplicates,
                   f'missing={player.missing}, '
                   f'duplicates={player.duplicates}')

    # --- 3. Key-0 pose == loader rest pose (axis-conversion contract) --
    player.seek(0.0)
    e_pos = vec_err(door.get_pos(), rest_door_pos)
    q = hatch.get_quat()
    e_rot = 1.0 - abs(sum(q[i] * rest_hatch_quat[i] for i in range(4)))
    exp_door = (1.0, -3.0, 2.0)   # glTF (1,2,3) conjugated to Z-up
    e_abs = vec_err(door.get_pos(), exp_door)
    h.report.check('key0_matches_loader_rest',
                   e_pos < TOL and e_rot < TOL and e_abs < TOL,
                   f'door pos err vs loader {e_pos:.2e}, vs analytic '
                   f'{exp_door}: {e_abs:.2e}; hatch quat err {e_rot:.2e}')

    # --- 4. End pose: translation + rotated probe ----------------------
    player.seek(1.0)
    e1 = vec_err(door.get_pos(), (1.0, -3.0, 4.0))
    probe_w = probe.get_pos(model)   # hatch(-2,0,0) + X rotated 90 deg
    e2 = vec_err(probe_w, (-2.0, 1.0, 0.0))
    e3 = vec_err(stepn.get_scale(), (2.0, 4.0, 3.0))
    h.report.check('seek_end_analytic', e1 < TOL and e2 < TOL and e3 < TOL,
                   f'door {e1:.2e}, probe world {tuple(probe_w)} err '
                   f'{e2:.2e}, step scale err {e3:.2e}')

    # --- 5. LINEAR midpoint: lerp + slerp; STEP holds ------------------
    player.seek(0.5)
    e1 = vec_err(door.get_pos(), (1.0, -3.0, 3.0))
    probe_w = probe.get_pos(model)   # 45 deg about +Z
    e2 = vec_err(probe_w, (-2.0 + C45, S45, 0.0))
    e3 = vec_err(stepn.get_scale(), (1.0, 1.0, 1.0))
    h.report.check('seek_mid_lerp_slerp_step',
                   e1 < TOL and e2 < TOL and e3 < TOL,
                   f'door lerp {e1:.2e}, probe slerp {e2:.2e}, '
                   f'step holds {e3:.2e}')

    # --- 6. Reverse scrub is stateless; reset restores -----------------
    player.seek(0.0)
    e1 = vec_err(door.get_pos(), rest_door_pos)
    player.seek(0.7)
    player.reset()
    e2 = vec_err(door.get_pos(), rest_door_pos)
    q = hatch.get_quat()
    e3 = 1.0 - abs(sum(q[i] * rest_hatch_quat[i] for i in range(4)))
    h.report.check('reverse_and_reset', e1 < TOL and e2 < TOL and e3 < TOL,
                   f'scrub-back err {e1:.2e}, reset pos {e2:.2e} '
                   f'quat {e3:.2e}')

    # --- 7. CUBICSPLINE evaluation (data level) ------------------------
    from pax3d_render.rigid_clips import RigidChannel
    ch = RigidChannel('translation', [0.0, 1.0],
                      [((0.0,) * 3, (0.0,) * 3, (0.0,) * 3),
                       ((0.0,) * 3, (1.0, 0.0, 0.0), (0.0,) * 3)],
                      'CUBICSPLINE')
    v = ch.value_at(0.5)
    h.report.check('cubicspline_midpoint', vec_err(v, (0.5, 0.0, 0.0)) < TOL,
                   f'hermite(0.5) with zero tangents = {v}')

    # --- 8. from_delta: the prefab script-lerp shape -------------------
    delta = RigidClip.from_delta('CupboardOpen', 'Hatch', 1.5,
                                 pos_delta=(0.0, 0.5, 0.0),
                                 hpr_delta=(90.0, 0.0, 0.0))
    dplayer = RigidClipPlayer(delta, model)
    dplayer.seek(1.0)
    e1 = vec_err(hatch.get_pos(), (-2.0, 0.5, 0.0))
    probe_w = probe.get_pos(model)   # H+90 spins probe +X -> +Y
    e2 = vec_err(probe_w, (-2.0, 0.5 + 1.0, 0.0))
    dplayer.seek(0.0)
    e3 = vec_err(hatch.get_pos(), (-2.0, 0.0, 0.0))
    h.report.check('delta_clip_composes_on_rest',
                   e1 < TOL and e2 < TOL and e3 < TOL,
                   f'end pos err {e1:.2e}, rotated probe err {e2:.2e}, '
                   f'back-to-rest err {e3:.2e}')

    # --- 9. End-to-end: seeking visibly moves the rendered mesh --------
    h.adapter.update_sun((0, -1, 0), (2.0, 2.0, 2.0))
    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(0.05, 0.05, 0.05, 1))
    base.render.set_light(base.render.attach_new_node(alight))
    base.camera.set_pos(1, -10, 3)
    base.camera.look_at(1, 0, 3)
    player.seek(0.0)
    h.step(5)
    img_closed = h.capture()
    h.save_capture(img_closed, 'closed')
    player.seek(1.0)
    h.step(3)
    img_open = h.capture()
    h.save_capture(img_open, 'open')
    rms = common.image_rms_diff(img_closed, img_open, step=1)
    h.report.check('render_moves', rms > 0.005,
                   f'seek 0 vs 1 rms {rms:.4f} (the quad rides its '
                   f'clip-driven node)')

    h.report.finish()


if __name__ == '__main__':
    main()
