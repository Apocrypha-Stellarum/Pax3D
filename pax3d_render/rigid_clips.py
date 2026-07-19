"""Rigid node clips (ER-004, Session V): glTF animations targeting plain
nodes, as first-class queryable data — without the Character machinery.

Why this exists (measured, ER-004 + MINERVA_CENSUS.md): Unity ship packs
(Vattalus Phobos/Minerva) animate every interactive part — doors, ramps,
landing gear, drawers — as rigid TRS clips on plain nodes. panda3d-gltf
1.3.0 consumes glTF `animations` only inside build_character() (reached
from skins or morph meshes); channels targeting plain non-skinned nodes
are SILENTLY DROPPED. Re-deriving each part's motion from geometry cost a
full session per part (the Phobos ramp). This module reads those channels
directly from the .glb/.gltf file, so:

  1. Animated nodes stay ordinary PandaNodes (stable NodePaths — the
     game's find()-based rigging, collider parenting, and light registry
     all keep working; nothing is converted to a Character).
  2. Clips are a queryable store per model:
         clips = pipeline.get_model_clips(model_np)   # {name: RigidClip}
     (or load_rigid_clips(path) without a pipeline).
  3. A minimal player seeks a clip at t (seconds) or u in [0, 1] and
     writes local pos/quat/scale onto the target NodePaths. Forward,
     reverse, scrubbing — the GAME keeps owning interaction, sounds,
     easing and collision-mask gating; it just stops re-deriving hinge
     geometry from meshes.

The store does not care where a clip came from: RigidClip.from_delta()
synthesizes the second Vattalus clip source — prefab script-lerps whose
whole definition is a position delta + rotation delta + duration
(~40 parts on the Minerva) — as two-keyframe relative clips.

Axis conversion (PINNED — do not re-derive): panda3d-gltf converts EVERY
node's local transform as csxform_inv * gltf_mat * csxform
(gltf/_converter.py line ~224), i.e. a change of basis from glTF Y-up
right-handed to Panda Z-up right-handed — a proper rotation, so TRS
components convert independently:

    translation (x, y, z)      -> (x, -z, y)
    rotation    (x, y, z, w)   -> LQuaternion(w, x, -z, y)
    scale       (sx, sy, sz)   -> (sx, sz, sy)

Guarded end-to-end by paxtest test_rigid_clips: the loader's own rest
pose must equal the player's key-0 pose on the same file.

Channels targeting skin joints or morph weights are skipped — the loader's
Character machinery owns those (Actor clips); this store is complementary.
The channel `path` field is an open string: material-parameter channels
(ER-005 integration, "one runtime, two channel kinds") can land later as
new paths without restructuring — the player ignores unknown paths.
"""
import bisect
import json
import math
import os
import struct

import panda3d.core as p3d

from . import gltf_compat

__all__ = ['RigidClip', 'RigidChannel', 'RigidClipPlayer',
           'load_rigid_clips', 'get_model_clips']

# load_rigid_clips cache: os-path -> (mtime, size, clips dict)
_CLIP_CACHE = {}


# ----------------------------------------------------------------------
# Axis conversion (see module docstring — pinned to _converter.py ~224)
# ----------------------------------------------------------------------

def _cvt_pos(v):
    return (v[0], -v[2], v[1])


def _cvt_quat(q):
    """glTF (x, y, z, w) -> Panda (w, x, -z, y) component tuple."""
    return (q[3], q[0], -q[2], q[1])


def _cvt_scale(v):
    return (v[0], v[2], v[1])


_CONVERTERS = {'translation': _cvt_pos, 'rotation': _cvt_quat,
               'scale': _cvt_scale}


# ----------------------------------------------------------------------
# Interpolation helpers (glTF sampler semantics)
# ----------------------------------------------------------------------

def _lerp(a, b, u):
    return tuple(a[i] + (b[i] - a[i]) * u for i in range(len(a)))


def _slerp(q0, q1, u):
    """Shortest-path spherical lerp on (w, x, y, z) tuples (glTF LINEAR
    rotation semantic); falls back to nlerp for near-parallel quats."""
    d = sum(q0[i] * q1[i] for i in range(4))
    if d < 0.0:
        q1 = tuple(-c for c in q1)
        d = -d
    if d > 0.9995:
        q = _lerp(q0, q1, u)
        n = math.sqrt(sum(c * c for c in q)) or 1.0
        return tuple(c / n for c in q)
    theta = math.acos(min(1.0, d))
    s = math.sin(theta)
    w0 = math.sin((1.0 - u) * theta) / s
    w1 = math.sin(u * theta) / s
    return tuple(q0[i] * w0 + q1[i] * w1 for i in range(4))


def _hermite(v0, out0, v1, in1, u, td):
    """glTF CUBICSPLINE segment: cubic Hermite with scaled tangents."""
    u2 = u * u
    u3 = u2 * u
    h00 = 2.0 * u3 - 3.0 * u2 + 1.0
    h10 = u3 - 2.0 * u2 + u
    h01 = -2.0 * u3 + 3.0 * u2
    h11 = u3 - u2
    return tuple(h00 * v0[i] + h10 * td * out0[i]
                 + h01 * v1[i] + h11 * td * in1[i]
                 for i in range(len(v0)))


class RigidChannel:
    """One animation channel: key times + values for one target property.

    path: 'translation' | 'rotation' | 'scale' (open to new kinds).
    values are PANDA-SPACE tuples — pos/scale 3-tuples, rotation
    (w, x, y, z) quaternion tuples. For CUBICSPLINE, each key holds
    (in_tangent, value, out_tangent) — three tuples.
    """
    __slots__ = ('path', 'times', 'values', 'interpolation')

    def __init__(self, path, times, values, interpolation='LINEAR'):
        self.path = path
        self.times = list(times)
        self.values = list(values)
        self.interpolation = interpolation

    @property
    def end_time(self):
        return self.times[-1] if self.times else 0.0

    def _key_value(self, i):
        if self.interpolation == 'CUBICSPLINE':
            return self.values[i][1]
        return self.values[i]

    def value_at(self, t):
        """Sample the channel at t seconds (glTF semantics: clamp to the
        first/last key outside the keyed range)."""
        times = self.times
        if not times:
            return None
        if t <= times[0]:
            return self._key_value(0)
        if t >= times[-1]:
            return self._key_value(len(times) - 1)
        i = bisect.bisect_right(times, t) - 1
        t0, t1 = times[i], times[i + 1]
        td = t1 - t0
        u = (t - t0) / td if td > 0.0 else 1.0
        if self.interpolation == 'STEP':
            return self.values[i]
        if self.interpolation == 'CUBICSPLINE':
            _in0, v0, out0 = self.values[i]
            in1, v1, _out1 = self.values[i + 1]
            v = _hermite(v0, out0, v1, in1, u, td)
            if self.path == 'rotation':
                n = math.sqrt(sum(c * c for c in v)) or 1.0
                v = tuple(c / n for c in v)
            return v
        # LINEAR
        if self.path == 'rotation':
            return _slerp(self.values[i], self.values[i + 1], u)
        return _lerp(self.values[i], self.values[i + 1], u)


class RigidClip:
    """A named clip: {target node name: {path: RigidChannel}}.

    relative=False (glTF files): channel values are ABSOLUTE local TRS.
    relative=True (from_delta / prefab lerps): values COMPOSE onto the
    target's rest transform captured by the player —
        pos   = rest_pos + value
        quat  = value_quat * rest_quat   (delta in the node's LOCAL frame,
                the Unity localRotation * Euler(delta) convention)
        scale = rest_scale * value       (component-wise)
    """

    def __init__(self, name, relative=False):
        self.name = name
        self.relative = relative
        self.channels = {}   # node_name -> {path: RigidChannel}

    @property
    def duration(self):
        return max((ch.end_time
                    for paths in self.channels.values()
                    for ch in paths.values()), default=0.0)

    @property
    def target_names(self):
        return sorted(self.channels)

    def add_channel(self, node_name, path, times, values,
                    interpolation='LINEAR'):
        """Add a channel (PANDA-space values — no axis conversion applied;
        conversion happens only when parsing glTF files)."""
        ch = RigidChannel(path, times, values, interpolation)
        self.channels.setdefault(node_name, {})[path] = ch
        return ch

    @classmethod
    def from_delta(cls, name, node_name, duration, pos_delta=None,
                   hpr_delta=None, quat_delta=None, scale_end=None):
        """Synthesize a two-keyframe RELATIVE clip from a delta pose — the
        Vattalus prefab script-lerp shape (positionAnimation /
        rotationAnimation / animationDuration; linear curve).

        All values are PANDA-space and LOCAL to the target node: the game
        converts Unity prefab data before calling (validate the axis
        convention on one door first — the stated ER-004 game-side plan).
        hpr_delta is Panda HPR degrees (converted through LQuaternion);
        pass quat_delta as (w, x, y, z) to bypass HPR. scale_end is an
        absolute end multiplier, e.g. (1, 1, 0.5).

        Use add_delta() to put more parts on the same clip (multi-node
        interactables); returns the clip for chaining.
        """
        clip = cls(name, relative=True)
        clip.add_delta(node_name, duration, pos_delta, hpr_delta,
                       quat_delta, scale_end)
        return clip

    def add_delta(self, node_name, duration, pos_delta=None, hpr_delta=None,
                  quat_delta=None, scale_end=None):
        """Add another delta-lerped target to a relative clip."""
        if not self.relative:
            raise ValueError('add_delta needs a relative clip '
                             '(RigidClip.from_delta)')
        duration = max(1e-6, float(duration))
        times = [0.0, duration]
        if pos_delta is not None:
            self.add_channel(node_name, 'translation', times,
                             [(0.0, 0.0, 0.0), tuple(pos_delta)])
        if quat_delta is None and hpr_delta is not None:
            q = p3d.LQuaternion()
            q.set_hpr(p3d.LVecBase3(*hpr_delta))
            quat_delta = (q.get_r(), q.get_i(), q.get_j(), q.get_k())
        if quat_delta is not None:
            self.add_channel(node_name, 'rotation', times,
                             [(1.0, 0.0, 0.0, 0.0), tuple(quat_delta)])
        if scale_end is not None:
            self.add_channel(node_name, 'scale', times,
                             [(1.0, 1.0, 1.0), tuple(scale_end)])
        return self


# ----------------------------------------------------------------------
# glTF / GLB parsing (reuses gltf_compat's accessor machinery)
# ----------------------------------------------------------------------

_GLB_JSON = 0x4E4F534A   # 'JSON'
_GLB_BIN = 0x004E4942    # 'BIN\0'

_NORM_SCALE = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}


def _read_gltf_json(path):
    """The glTF JSON dict for a .glb or .gltf file, with any GLB BIN
    chunk attached under the loader's '_glb_bin' buffer convention (so
    gltf_compat._buffer_bytes reads it unchanged)."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] == b'glTF':
        json_data = None
        bin_data = None
        offset = 12
        while offset + 8 <= len(data):
            clen, ctype = struct.unpack_from('<II', data, offset)
            chunk = data[offset + 8:offset + 8 + clen]
            if ctype == _GLB_JSON:
                json_data = json.loads(chunk.decode('utf-8'))
            elif ctype == _GLB_BIN:
                bin_data = chunk
            offset += 8 + clen
        if json_data is None:
            raise ValueError(f'load_rigid_clips: no JSON chunk in {path}')
        if bin_data is not None:
            for buf in json_data.get('buffers', []):
                if 'uri' not in buf:
                    buf['uri'] = '_glb_bin'
                    buf['_glb_bin'] = bin_data
                    break
        return json_data
    return json.loads(data.decode('utf-8'))


def _read_accessor(gltf_data, idx, cache, filedir):
    """Accessor idx as a list of floats (SCALAR) or tuples."""
    acc = gltf_data['accessors'][idx]
    n_comp = gltf_compat._NUM_COMP[acc['type']]
    comp_type = acc['componentType']
    elem_size = n_comp * gltf_compat._COMP_SIZE[comp_type]
    dense = gltf_compat._dense_base(gltf_data, acc, elem_size, cache,
                                    filedir)
    fmt = '<' + str(acc['count'] * n_comp) + gltf_compat._COMP_FMT[comp_type]
    flat = struct.unpack(fmt, bytes(dense))
    if acc.get('normalized') and comp_type in _NORM_SCALE:
        s = _NORM_SCALE[comp_type]
        flat = tuple(max(v / s, -1.0) for v in flat)
    if n_comp == 1:
        return list(flat)
    return [tuple(flat[i * n_comp:(i + 1) * n_comp])
            for i in range(acc['count'])]


def parse_rigid_clips(gltf_data, filedir=None, axis_conversion=True):
    """Extract rigid clips from a parsed glTF JSON dict.

    Skips channels the loader's Character machinery already consumes
    (skin joints, morph 'weights'); everything else targeting a node
    becomes a RigidChannel in PANDA space (axis_conversion=False only for
    files loaded with panda3d-gltf's skip_axis_conversion setting).
    """
    # Densify sparse / bufferView-less accessors first (no-op on normal
    # files) so _dense_base sees only dense data — same pre-pass the
    # loader shim applies.
    gltf_compat.densify_sparse_accessors(gltf_data, filedir)

    joint_ids = set()
    for skin in gltf_data.get('skins', []):
        joint_ids.update(skin.get('joints', []))

    nodes = gltf_data.get('nodes', [])

    def node_name(nid):
        # panda3d-gltf's naming convention (_converter.py load_node)
        return nodes[nid].get('name', 'node' + str(nid))

    cache = {}
    clips = {}
    for anim_id, anim in enumerate(gltf_data.get('animations', [])):
        name = anim.get('name', 'anim' + str(anim_id))
        clip = RigidClip(name)
        samplers = anim.get('samplers', [])
        for channel in anim.get('channels', []):
            target = channel.get('target', {})
            path = target.get('path')
            nid = target.get('node')
            if nid is None or path == 'weights':
                continue        # morphs: the loader's Character owns them
            if nid in joint_ids:
                continue        # skin joints: Actor clips own them
            conv = _CONVERTERS.get(path)
            if conv is None:
                continue        # unknown target path — not TRS data
            sampler = samplers[channel['sampler']]
            times = _read_accessor(gltf_data, sampler['input'], cache,
                                   filedir)
            raw = _read_accessor(gltf_data, sampler['output'], cache,
                                 filedir)
            if not axis_conversion:
                conv = tuple
            interpolation = sampler.get('interpolation', 'LINEAR')
            if interpolation == 'CUBICSPLINE':
                # (in-tangent, value, out-tangent) triplets per key
                values = [tuple(conv(raw[3 * i + j]) for j in range(3))
                          for i in range(len(times))]
            else:
                values = [conv(v) for v in raw]
            clip.channels.setdefault(node_name(nid), {})[path] = \
                RigidChannel(path, times, values, interpolation)
        if clip.channels:
            clips[name] = clip
    return clips


def load_rigid_clips(path, axis_conversion=True):
    """Parse .glb/.gltf `path` and return {clip_name: RigidClip} for every
    animation with at least one plain-node TRS channel. Cached by
    (mtime, size); raises ValueError if the file cannot be read."""
    os_path = os.path.abspath(str(path))
    try:
        st = os.stat(os_path)
    except OSError as exc:
        raise ValueError(f'load_rigid_clips: cannot read {os_path}: {exc}')
    key = (st.st_mtime_ns, st.st_size)
    cached = _CLIP_CACHE.get(os_path)
    if cached is not None and cached[0] == key:
        return cached[1]
    gltf_data = _read_gltf_json(os_path)
    clips = parse_rigid_clips(gltf_data, os.path.dirname(os_path),
                              axis_conversion)
    _CLIP_CACHE[os_path] = (key, clips)
    return clips


def _find_model_file(model_np):
    """The source Filename recorded on the model's ModelRoot (searching
    the node itself, then ancestors, then descendants)."""
    candidates = [model_np]
    parent = model_np.get_parent()
    while not parent.is_empty():
        candidates.append(parent)
        parent = parent.get_parent()
    found = model_np.find('**/+ModelRoot')
    if not found.is_empty():
        candidates.append(found)
    for np_ in candidates:
        node = np_.node() if not np_.is_empty() else None
        if isinstance(node, p3d.ModelRoot):
            fn = node.get_fullpath()
            if fn and not fn.empty():
                return fn
    return None


def get_model_clips(model_np, path=None, axis_conversion=True):
    """{clip_name: RigidClip} for a LOADED model — resolves the source
    .glb/.gltf from the ModelRoot's recorded fullpath (pass `path`
    explicitly for models packed in multifiles or moved on disk).

    Also exposed as pipeline.get_model_clips() (the ER-004 sketch)."""
    if path is None:
        fn = _find_model_file(model_np)
        if fn is None:
            raise ValueError(
                'get_model_clips: no ModelRoot with a recorded source path '
                f'under/above {model_np}; pass path= explicitly')
        path = fn.to_os_specific()
    return load_rigid_clips(path, axis_conversion)


# ----------------------------------------------------------------------
# Player
# ----------------------------------------------------------------------

class RigidClipPlayer:
    """Applies one RigidClip onto the matching NodePaths under a model.

    Minimal by design (the ER-004 contract): the game owns tasks, easing,
    sounds, and collision gating — this just writes local TRS for a time.

        player = RigidClipPlayer(clips['DoorOpen'], ship_np)
        player.seek(0.0)          # closed  (u in [0, 1])
        player.seek(1.0)          # open
        player.apply(t_seconds)   # absolute clip time
        player.reset()            # restore the rest pose captured at init

    Reverse play is seek() with a decreasing u — evaluation is stateless.
    Targets are resolved by exact node NAME over the subtree (depth-first,
    first match wins — duplicate-named targets are reported in
    .duplicates); unresolved names land in .missing rather than raising
    (rigging problems should be visible, not fatal). Channels a clip does
    not key keep the node's current value (glTF semantic). Unknown channel
    paths are ignored (the ER-005 material-channel seam)."""

    def __init__(self, clip, model_np):
        self.clip = clip
        self.model_np = model_np
        self.targets = {}
        self.missing = []
        self.duplicates = []
        self.rest = {}
        wanted = set(clip.channels)
        found = {}
        stack = [model_np]
        while stack:
            np_ = stack.pop()
            name = np_.get_name()
            if name in wanted:
                if name in found:
                    if name not in self.duplicates:
                        self.duplicates.append(name)
                else:
                    found[name] = np_
            children = np_.get_children()
            for i in range(children.get_num_paths() - 1, -1, -1):
                stack.append(children.get_path(i))
        for name in clip.channels:
            np_ = found.get(name)
            if np_ is None:
                self.missing.append(name)
                continue
            self.targets[name] = np_
            self.rest[name] = (p3d.LPoint3(np_.get_pos()),
                               p3d.LQuaternion(np_.get_quat()),
                               p3d.LVecBase3(np_.get_scale()))

    @property
    def duration(self):
        return self.clip.duration

    def seek(self, u):
        """Pose the clip at normalized u in [0, 1]."""
        u = max(0.0, min(1.0, float(u)))
        self.apply(u * self.clip.duration)

    def apply(self, t):
        """Pose the clip at t seconds (clamped to the keyed range)."""
        relative = self.clip.relative
        for name, paths in self.clip.channels.items():
            np_ = self.targets.get(name)
            if np_ is None or np_.is_empty():
                continue
            rest = self.rest[name]
            ch = paths.get('translation')
            if ch is not None:
                v = ch.value_at(t)
                if relative:
                    v = (rest[0][0] + v[0], rest[0][1] + v[1],
                         rest[0][2] + v[2])
                np_.set_pos(v[0], v[1], v[2])
            ch = paths.get('rotation')
            if ch is not None:
                v = ch.value_at(t)
                q = p3d.LQuaternion(v[0], v[1], v[2], v[3])
                if relative:
                    # Delta in the node's LOCAL frame: with Panda's
                    # row-vector convention that composes delta first,
                    # then the rest rotation.
                    q = q * rest[1]
                np_.set_quat(q)
            ch = paths.get('scale')
            if ch is not None:
                v = ch.value_at(t)
                if relative:
                    v = (rest[2][0] * v[0], rest[2][1] * v[1],
                         rest[2][2] * v[2])
                np_.set_scale(v[0], v[1], v[2])

    def reset(self):
        """Restore every resolved target to its captured rest TRS."""
        for name, np_ in self.targets.items():
            if np_.is_empty():
                continue
            pos, quat, scale = self.rest[name]
            np_.set_pos(pos)
            np_.set_quat(quat)
            np_.set_scale(scale)
