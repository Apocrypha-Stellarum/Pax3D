"""Compatibility shims for panda3d-gltf (the glTF loader is a
third-party pip package, not part of the Pax3D engine tree). All three
defects below were measured on the SK_SFM_Head1 morph asset
(tools/paxtest/probe_morph_gltf.py, 2026-07-19); each is masked by
dense per-frame Blender bakes, which is why upstream ships them.

1. SPARSE ACCESSORS (crash): glTF 2.0 makes accessor.bufferView
   optional — absent means "zero-initialized", and a `sparse` block
   overlays deltas on that base. Blender writes shape keys (morph
   targets) this way BY DEFAULT, so every Blender-default morph export
   crashes stock panda3d-gltf <= 1.3.0 with KeyError: 'bufferView'
   (upstream Moguri/panda3d-gltf#103, open). Fix: a Converter.update
   pre-pass densifies every sparse / bufferView-less accessor at the
   JSON level and appends the dense bytes as base64 data: URI buffers
   (a branch load_buffer already supports). Files without sparse
   accessors are byte-identical no-ops.

2. SHORT ANIMATION CHANNELS (crash): a channel whose last keyframe
   ends before the clip's global end (legal and normal — each glTF
   channel carries its own key times; short channels hold their last
   value) sends _converter.get_next_time_index past the end of its
   time buffer -> IndexError. Fix: clamp the scan to the last index.

3. KEYFRAME INTERPOLATION (silent wrongness): _converter's
   get_lerp_factor returns max(t, 1) where the intent is plainly
   min(t, 1) — every LINEAR sample between two keys snaps to the NEXT
   key's full value (joints and morphs alike). Invisible when every
   frame is a key; badly wrong on sparse keyframes. Fix: clamp the
   factor to [0, 1].

install() applies all three. Call once, after `import gltf`, before
loading models (patch_loader no longer exists in 1.3.0 — the loader
self-registers; just install the shims):

    from pax3d_render import gltf_compat
    gltf_compat.install()
"""
import base64
import os
import struct

_COMP_SIZE = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
_COMP_FMT = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H',
             5125: 'I', 5126: 'f'}
_NUM_COMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4,
             'MAT2': 4, 'MAT3': 9, 'MAT4': 16}


def _buffer_bytes(gltf_data, idx, cache, filedir):
    """Raw bytes of buffer idx (mirrors Converter.load_buffer's URI
    handling; read-only)."""
    if idx in cache:
        return cache[idx]
    buf = gltf_data['buffers'][idx]
    uri = buf.get('uri')
    if uri == '_glb_bin':
        data = buf['_glb_bin']
    elif uri is not None and uri.startswith('data:'):
        data = base64.b64decode(uri.split(',', 1)[1])
    elif uri is not None:
        with open(os.path.join(filedir or '', uri), 'rb') as f:
            data = f.read(buf['byteLength'])
    else:
        data = bytes(buf['byteLength'])
    cache[idx] = data
    return data


def _view_slice(gltf_data, view_id, byte_offset, length, cache, filedir):
    view = gltf_data['bufferViews'][view_id]
    data = _buffer_bytes(gltf_data, view['buffer'], cache, filedir)
    start = view.get('byteOffset', 0) + byte_offset
    return data[start:start + length]


def _dense_base(gltf_data, acc, elem_size, cache, filedir):
    """The accessor's base data, tightly packed (zeros when it has no
    bufferView, de-strided otherwise)."""
    count = acc['count']
    if 'bufferView' not in acc:
        return bytearray(count * elem_size)
    view = gltf_data['bufferViews'][acc['bufferView']]
    stride = view.get('byteStride') or elem_size
    raw = _view_slice(gltf_data, acc['bufferView'],
                      acc.get('byteOffset', 0),
                      stride * (count - 1) + elem_size, cache, filedir)
    if stride == elem_size:
        return bytearray(raw)
    out = bytearray(count * elem_size)
    for i in range(count):
        out[i * elem_size:(i + 1) * elem_size] = \
            raw[i * stride:i * stride + elem_size]
    return out


def densify_sparse_accessors(gltf_data, filedir=None):
    """Rewrite sparse / bufferView-less accessors as dense ones backed
    by appended data: URI buffers. Returns the number rewritten."""
    cache = {}
    rewritten = 0
    for acc in gltf_data.get('accessors', []):
        sparse = acc.get('sparse')
        if sparse is None and 'bufferView' in acc:
            continue
        elem_size = (_COMP_SIZE[acc['componentType']]
                     * _NUM_COMP[acc['type']])
        dense = _dense_base(gltf_data, acc, elem_size, cache, filedir)
        if sparse is not None:
            n = sparse['count']
            idx_spec = sparse['indices']
            idx_fmt = '<' + str(n) + _COMP_FMT[idx_spec['componentType']]
            idx_raw = _view_slice(
                gltf_data, idx_spec['bufferView'],
                idx_spec.get('byteOffset', 0),
                n * _COMP_SIZE[idx_spec['componentType']], cache, filedir)
            indices = struct.unpack(idx_fmt, idx_raw)
            val_raw = _view_slice(
                gltf_data, sparse['values']['bufferView'],
                sparse['values'].get('byteOffset', 0),
                n * elem_size, cache, filedir)
            for i, vi in enumerate(indices):
                dense[vi * elem_size:(vi + 1) * elem_size] = \
                    val_raw[i * elem_size:(i + 1) * elem_size]
        buffers = gltf_data.setdefault('buffers', [])
        views = gltf_data.setdefault('bufferViews', [])
        buf_idx = len(buffers)
        buffers.append({
            'uri': ('data:application/octet-stream;base64,'
                    + base64.b64encode(bytes(dense)).decode('ascii')),
            'byteLength': len(dense),
        })
        views.append({'buffer': buf_idx, 'byteOffset': 0,
                      'byteLength': len(dense)})
        acc['bufferView'] = len(views) - 1
        acc.pop('byteOffset', None)
        acc.pop('sparse', None)
        rewritten += 1
    return rewritten


def _fixed_next_time_index(currtime, time_buffer):
    """Upstream get_next_time_index without the off-the-end walk (fix 2).
    Semantics preserved otherwise, including the currtime <= first-key
    case returning 1."""
    nextidx = 1
    last = len(time_buffer) - 1
    while currtime > time_buffer[nextidx] and nextidx < last:
        nextidx += 1
    return nextidx


def _fixed_lerp_factor(currtime, lasttime, nexttime):
    """Upstream get_lerp_factor with the max->min clamp corrected and
    both ends bounded (fix 3)."""
    if nexttime <= lasttime:
        return 1.0
    return max(0.0, min((currtime - lasttime) / (nexttime - lasttime), 1.0))


def install():
    """Idempotent: apply all shims to gltf._converter. Returns True if
    newly installed."""
    from gltf import _converter
    if getattr(_converter.Converter.update, '_pax3d_gltf_shims', False):
        return False
    orig = _converter.Converter.update

    def update(self, gltf_data):
        try:
            filedir = self.filedir.to_os_specific()
        except Exception:
            filedir = None
        densify_sparse_accessors(gltf_data, filedir)
        return orig(self, gltf_data)

    update._pax3d_gltf_shims = True
    _converter.Converter.update = update
    _converter.get_next_time_index = _fixed_next_time_index
    _converter.get_lerp_factor = _fixed_lerp_factor
    return True
