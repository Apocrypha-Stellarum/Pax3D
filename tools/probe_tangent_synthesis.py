"""Probe: does the loaded Geom carry tangents when the GLB file has no TANGENT?

ER-012 (sfb2 ship-intake lane, 2026-07-24; filed as ER-010) reported
158/246 fleet GLBs lacking TANGENT on normal-mapped primitives (Blender
refuses tangent export on n-gon meshes) and asked for load-time
synthesis. Answer: panda3d-gltf ALREADY synthesizes per-vertex tangents
at convert time for every primitive with UVs and no TANGENT
(gltf/_converter.py calculate_tangents — Lengyel UV-derivative
accumulation, normal-orthogonalized, handedness in w), and the result
is what the model cache stores. This probe measures both sides of that
boundary so in-file audits are never again read as at-render facts:

  (a) in-file: TANGENT attribute per primitive, from the glb JSON chunk
      (the same fact sfb2's pitbull_fleet_audit.py counts),
  (b) post-load: tangent column on each Geom's vdata after panda3d-gltf
      conversion (model cache disabled), plus degenerate-tangent counts
      (zero-magnitude tangents -> NaN in pax_pbr under USE_NORMAL_MAP
      if rasterized; pax_pbr has NO draw-time derivative fallback).

Usage (either env):
  C:/python/pax3d-env/Scripts/python.exe tools/probe_tangent_synthesis.py <model.glb> [...]

Reference numbers 2026-07-24 (panda3d-gltf 1.3.0, Session-X wheel):
  frigate_sr4_grey      file 4/5 no-TANGENT -> loaded 0/5 missing,  8/21725 zero
  destroyer_hermes_grey file 13/14          -> loaded 0/14 missing, 40/55226 zero
  frigate_storm_orange  file 24/24 (0 normal-mapped) -> 0/24 missing, 458/91092 zero
"""
import json
import math
import struct
import sys

from panda3d.core import load_prc_file_data

load_prc_file_data('', 'model-cache-dir\nwindow-type none\nnotify-level-gltf error')

from panda3d.core import GeomVertexReader, InternalName, NodePath
from gltf import load_model


def read_glb_json(path):
    with open(path, 'rb') as f:
        magic, _version, _length = struct.unpack('<III', f.read(12))
        assert magic == 0x46546C67, 'not a glb'
        chunk_len, chunk_type = struct.unpack('<II', f.read(8))
        assert chunk_type == 0x4E4F534A, 'first chunk not JSON'
        return json.loads(f.read(chunk_len))


def file_side(gltf_data):
    """Per-mesh primitive attribute facts straight from the glb JSON."""
    mats = gltf_data.get('materials', [])
    rows = []
    for mesh in gltf_data.get('meshes', []):
        for pi, prim in enumerate(mesh.get('primitives', [])):
            attrs = prim.get('attributes', {})
            mat = mats[prim['material']] if 'material' in prim else {}
            rows.append({
                'mesh': mesh.get('name', '?'),
                'prim': pi,
                'tangent': 'TANGENT' in attrs,
                'uv': 'TEXCOORD_0' in attrs,
                'normal_mapped': 'normalTexture' in mat,
            })
    return rows


def loaded_side(path):
    """Per-Geom tangent-column facts after panda3d-gltf conversion."""
    node = load_model(path)
    assert node is not None, f'load failed: {path}'
    np = NodePath(node)
    tan_name = InternalName.get_tangent()
    rows = []
    for gnp in np.find_all_matches('**/+GeomNode'):
        gn = gnp.node()
        for i in range(gn.get_num_geoms()):
            vdata = gn.get_geom(i).get_vertex_data()
            row = {'node': gn.get_name(), 'geom': i,
                   'verts': vdata.get_num_rows(),
                   'has_tangent': vdata.has_column(tan_name),
                   'zero': 0, 'nan': 0, 'bad_w': 0}
            if row['has_tangent']:
                r = GeomVertexReader(vdata, tan_name)
                while not r.is_at_end():
                    x, y, z, w = r.get_data4()
                    m = math.sqrt(x * x + y * y + z * z)
                    if any(v != v for v in (x, y, z, w)):
                        row['nan'] += 1
                    elif m < 1e-6:
                        row['zero'] += 1
                    if w not in (-1.0, 1.0):
                        row['bad_w'] += 1
            rows.append(row)
    return rows


def main():
    for path in sys.argv[1:]:
        print(f'\n=== {path} ===')
        frows = file_side(read_glb_json(path))
        n_no_tan = sum(1 for r in frows if not r['tangent'])
        n_nm_no_tan = sum(1 for r in frows
                          if r['normal_mapped'] and not r['tangent'])
        print(f'file: {len(frows)} primitives, {n_no_tan} without TANGENT '
              f'({n_nm_no_tan} of those normal-mapped)')
        for r in frows:
            if not r['tangent']:
                print(f"  no-TANGENT in file: {r['mesh']}[{r['prim']}] "
                      f"uv={r['uv']} normal_mapped={r['normal_mapped']}")
        lrows = loaded_side(path)
        missing = [r for r in lrows if not r['has_tangent']]
        degen = [r for r in lrows if r['zero'] or r['nan'] or r['bad_w']]
        total_zero = sum(r['zero'] for r in lrows)
        total_verts = sum(r['verts'] for r in lrows)
        print(f'loaded: {len(lrows)} geoms, {len(missing)} WITHOUT tangent '
              f'column, {total_zero}/{total_verts} zero-magnitude tangents')
        for r in missing:
            print(f"  loaded geom missing tangents: {r['node']}[{r['geom']}] "
                  f"verts={r['verts']}")
        for r in degen:
            print(f"  degenerate: {r['node']}[{r['geom']}] verts={r['verts']} "
                  f"zero={r['zero']} nan={r['nan']} bad_w={r['bad_w']}")


main()
