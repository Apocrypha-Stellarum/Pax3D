"""Test geometry and shaders for paxtest.

Everything here is deliberately minimal GLSL 120 (matching the game's
current baseline) with a mechanical 120->330 conversion for the modern
baseline, mirroring what sfb2's graphics/pax_pbr/shaderutils.py does.
"""
import math

import panda3d.core as p3d


# ----------------------------------------------------------------------
# Shader helpers
# ----------------------------------------------------------------------

_VERT_120 = """#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
attribute vec4 p3d_Vertex;
attribute vec2 p3d_MultiTexCoord0;
varying vec2 v_uv;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_uv = p3d_MultiTexCoord0;
}
"""

# Fragment shaders write to FRAG_OUT which is #defined per GLSL version.
_FRAG_BARS_120 = """#version 120
varying vec2 v_uv;
uniform float u_num_bars;
uniform float u_row_max_bottom;
uniform float u_row_max_top;
void main() {
    float maxv = (v_uv.y > 0.5) ? u_row_max_top : u_row_max_bottom;
    float bar = min(floor(v_uv.x * u_num_bars), u_num_bars - 1.0);
    float v = (bar / (u_num_bars - 1.0)) * maxv;
    FRAG_OUT = vec4(v, v, v, 1.0);
}
"""

_FRAG_CONST_120 = """#version 120
varying vec2 v_uv;
uniform float u_value;
void main() {
    FRAG_OUT = vec4(u_value, u_value, u_value, 1.0);
}
"""

_FRAG_TEXPASS_120 = """#version 120
varying vec2 v_uv;
uniform sampler2D u_tex;
void main() {
    FRAG_OUT = vec4(texture2D(u_tex, v_uv).rgb, 1.0);
}
"""


def _convert_120_to_330(src, is_vertex):
    """Mechanical GLSL 120 -> 330 core conversion (mirrors game shaderutils)."""
    src = src.replace('#version 120', '#version 330')
    if is_vertex:
        src = src.replace('varying ', 'out ')
        src = src.replace('attribute ', 'in ')
    else:
        src = src.replace('varying ', 'in ')
        src = src.replace('texture2D(', 'texture(')
    return src


def _prep_frag(src, use_330):
    """Resolve the FRAG_OUT macro for the target GLSL version."""
    if use_330:
        src = _convert_120_to_330(src, is_vertex=False)
        # Declare an explicit output after the #version line
        src = src.replace(
            '#version 330',
            '#version 330\nout vec4 o_color;\n#define FRAG_OUT o_color'
        )
    else:
        src = src.replace(
            '#version 120',
            '#version 120\n#define FRAG_OUT gl_FragColor'
        )
    return src


def make_shader(frag_src_120, use_330):
    vert = _convert_120_to_330(_VERT_120, is_vertex=True) if use_330 else _VERT_120
    frag = _prep_frag(frag_src_120, use_330)
    shader = p3d.Shader.make(p3d.Shader.SL_GLSL, vert, frag)
    if shader is None:
        raise RuntimeError('paxtest shader failed to compile')
    return shader


# ----------------------------------------------------------------------
# Cards
# ----------------------------------------------------------------------

def _make_card(parent, half_w, half_h, name):
    cm = p3d.CardMaker(name)
    cm.set_frame(-half_w, half_w, -half_h, half_h)
    cm.set_uv_range((0, 0), (1, 1))
    np = parent.attach_new_node(cm.generate())
    # CardMaker generates in the XZ plane, visible from the default camera
    # (at -Y looking +Y): frame-left = screen-left, uv (0,0) = bottom-left.
    np.set_two_sided(True)
    return np


def make_bar_card(parent, use_330, num_bars=16, row_max_bottom=1.0,
                  row_max_top=4.0, half_size=1.0):
    """Fullscreen (with ortho film 2x2) card of `num_bars` vertical gray bars.

    Bottom half of the card sweeps 0..row_max_bottom, top half 0..row_max_top.
    Values are written raw (linear) into whatever buffer the scene renders to.
    """
    np = _make_card(parent, half_size, half_size, 'paxtest_bars')
    np.set_shader(make_shader(_FRAG_BARS_120, use_330))
    np.set_shader_input('u_num_bars', float(num_bars))
    np.set_shader_input('u_row_max_bottom', float(row_max_bottom))
    np.set_shader_input('u_row_max_top', float(row_max_top))
    np.set_light_off(1)
    return np


def make_emissive_quad(parent, use_330, value, half_size):
    """Small constant-value HDR quad (bloom source)."""
    np = _make_card(parent, half_size, half_size, 'paxtest_emissive')
    np.set_shader(make_shader(_FRAG_CONST_120, use_330))
    np.set_shader_input('u_value', float(value))
    np.set_light_off(1)
    return np


def make_texture_card(parent, use_330, tex_value_8bit=128, half_size=1.0):
    """Card showing an 8-bit texture through a passthrough shader.

    Used to detect whether texture values are sRGB-decoded on sampling
    (linearized) or passed through raw.
    """
    tex = p3d.Texture('paxtest_gray')
    tex.setup_2d_texture(4, 4, p3d.Texture.T_unsigned_byte, p3d.Texture.F_rgb8)
    v = tex_value_8bit / 255.0
    tex.set_clear_color(p3d.LColor(v, v, v, 1))
    tex.set_minfilter(p3d.SamplerState.FT_nearest)
    tex.set_magfilter(p3d.SamplerState.FT_nearest)

    np = _make_card(parent, half_size, half_size, 'paxtest_texcard')
    np.set_shader(make_shader(_FRAG_TEXPASS_120, use_330))
    np.set_shader_input('u_tex', tex)
    np.set_light_off(1)
    return np


# ----------------------------------------------------------------------
# Spheres
# ----------------------------------------------------------------------

def make_uv_sphere(resolution=48, winding='game'):
    """Procedural UV sphere replicating sfb2 planet_factory conventions.

    winding='game'     — exact copy of the current planet_factory triangle
                         order (post-Session-424 "corrected" order).
    winding='reversed' — the opposite order (the pre-424 order that the
                         directional-lighting docs call "session 417 winding").

    Vertex format is V3n3t2 (position/normal/texcoord, NO tangents), matching
    the game exactly. Normals point outward in both variants; only the
    triangle winding differs.
    """
    fmt = p3d.GeomVertexFormat.get_v3n3t2()
    vdata = p3d.GeomVertexData('paxtest_sphere', fmt, p3d.Geom.UH_static)

    vertex = p3d.GeomVertexWriter(vdata, 'vertex')
    normal = p3d.GeomVertexWriter(vdata, 'normal')
    texcoord = p3d.GeomVertexWriter(vdata, 'texcoord')

    for i in range(resolution + 1):
        v = i / resolution
        phi = v * math.pi
        for j in range(resolution + 1):
            u = j / resolution
            theta = u * 2 * math.pi
            x = math.sin(phi) * math.cos(theta)
            y = math.sin(phi) * math.sin(theta)
            z = math.cos(phi)
            vertex.add_data3(x, y, z)
            normal.add_data3(x, y, z)
            texcoord.add_data2(u, v)

    tris = p3d.GeomTriangles(p3d.Geom.UH_static)
    for i in range(resolution):
        for j in range(resolution):
            bottom_left = i * (resolution + 1) + j
            bottom_right = i * (resolution + 1) + j + 1
            top_left = (i + 1) * (resolution + 1) + j
            top_right = (i + 1) * (resolution + 1) + j + 1
            if winding == 'game':
                if i != 0:
                    tris.add_vertices(bottom_left, top_left, bottom_right)
                    tris.close_primitive()
                if i != resolution - 1:
                    tris.add_vertices(bottom_right, top_left, top_right)
                    tris.close_primitive()
            else:  # reversed
                if i != 0:
                    tris.add_vertices(bottom_left, bottom_right, top_left)
                    tris.close_primitive()
                if i != resolution - 1:
                    tris.add_vertices(bottom_right, top_right, top_left)
                    tris.close_primitive()

    geom = p3d.Geom(vdata)
    geom.add_primitive(tris)
    node = p3d.GeomNode(f'paxtest_sphere_{winding}')
    node.add_geom(geom)
    np = p3d.NodePath(node)
    np.set_two_sided(False)
    return np


# ----------------------------------------------------------------------
# Skinned geometry (shadow-caster coverage — openworld P0)
# ----------------------------------------------------------------------

def make_skinned_sheet(half=1.0, height=4.0, segments=8):
    """A horizontal soft-skinned sheet: a Character with two joints.

    Built via in-memory egg synthesis so it exercises the exact machinery
    real characters use (egg/gltf loaders both produce a Character with a
    TransformBlendTable). The sheet lies in the XY plane at z=height,
    x/y in [-half, half]; skin weights ramp along +x from joint_root
    (x=-half, weight 1) to joint_tip (x=+half, weight 1), so most vertices
    have BLENDED weights — the loader cannot rigidify them.

    Returns the loaded NodePath (contains '**/+Character').
    Translating joint_tip by +dx stretches the sheet's +x half sideways
    (linear weight ramp: a vertex at bind-pose x lands at x + t*dx with
    t=(x+half)/(2*half), so the footprint [-1,1] becomes [-1, 1+dx]),
    which the shadow tests use to prove the depth pass renders the POSED
    skin, not the bind pose.
    """
    from panda3d import egg as pegg

    data = pegg.EggData()
    data.set_coordinate_system(p3d.CS_zup_right)

    dart = pegg.EggGroup('skinned_sheet')
    dart.set_dart_type(pegg.EggGroup.DT_default)
    data.add_child(dart)

    pool = pegg.EggVertexPool('vp')
    dart.add_child(pool)

    j_root = pegg.EggGroup('joint_root')
    j_root.set_group_type(pegg.EggGroup.GT_joint)
    dart.add_child(j_root)
    j_tip = pegg.EggGroup('joint_tip')
    j_tip.set_group_type(pegg.EggGroup.GT_joint)
    j_root.add_child(j_tip)

    verts = {}
    for iy in range(segments + 1):
        for ix in range(segments + 1):
            x = -half + 2.0 * half * ix / segments
            y = -half + 2.0 * half * iy / segments
            v = pegg.EggVertex()
            v.set_pos(p3d.LPoint3d(x, y, height))
            v.set_normal(p3d.LVector3d(0, 0, 1))
            v = pool.add_vertex(v)
            t = ix / segments  # 0 at -x edge -> root, 1 at +x edge -> tip
            if t < 1.0:
                j_root.ref_vertex(v, 1.0 - t)
            if t > 0.0:
                j_tip.ref_vertex(v, t)
            verts[(ix, iy)] = v

    for iy in range(segments):
        for ix in range(segments):
            poly = pegg.EggPolygon()
            # CCW seen from +z (normal side)
            poly.add_vertex(verts[(ix, iy)])
            poly.add_vertex(verts[(ix + 1, iy)])
            poly.add_vertex(verts[(ix + 1, iy + 1)])
            poly.add_vertex(verts[(ix, iy + 1)])
            dart.add_child(poly)

    node = pegg.load_egg_data(data)
    if node is None:
        raise RuntimeError('skinned sheet egg failed to load')
    np = p3d.NodePath(node)
    np.set_two_sided(True)
    return np


def make_skinned_chain(joints=120, length=6.0, half_w=0.25, height=4.0):
    """A horizontal strip soft-skinned along a FLAT chain of `joints`
    joints — the >100-joint palette test rig (Session S). Strip lies in
    the XY plane at z=height, x in [-length/2, length/2]; vertex column
    i blends joints (i-1, i) at 0.5/0.5 (ends at full membership), so
    the geometry cannot be rigidified and the palette must hold every
    joint. Translating the LAST joint (chain_<joints-1>) moves the +x
    end of the strip — rendered correctly ONLY if the palette actually
    covers that joint's row."""
    from panda3d import egg as pegg

    data = pegg.EggData()
    data.set_coordinate_system(p3d.CS_zup_right)
    dart = pegg.EggGroup('skinned_chain')
    dart.set_dart_type(pegg.EggGroup.DT_default)
    data.add_child(dart)
    pool = pegg.EggVertexPool('vp')
    dart.add_child(pool)

    jgroups = []
    for i in range(joints):
        g = pegg.EggGroup(f'chain_{i}')
        g.set_group_type(pegg.EggGroup.GT_joint)
        dart.add_child(g)
        jgroups.append(g)

    cols = []
    for i in range(joints + 1):
        x = -length / 2.0 + length * i / joints
        col = []
        for y in (-half_w, half_w):
            v = pegg.EggVertex()
            v.set_pos(p3d.LPoint3d(x, y, height))
            v.set_normal(p3d.LVector3d(0, 0, 1))
            v = pool.add_vertex(v)
            lo, hi = max(0, i - 1), min(i, joints - 1)
            if lo == hi:
                jgroups[lo].ref_vertex(v, 1.0)
            else:
                jgroups[lo].ref_vertex(v, 0.5)
                jgroups[hi].ref_vertex(v, 0.5)
            col.append(v)
        cols.append(col)

    for i in range(joints):
        poly = pegg.EggPolygon()
        poly.add_vertex(cols[i][0])
        poly.add_vertex(cols[i + 1][0])
        poly.add_vertex(cols[i + 1][1])
        poly.add_vertex(cols[i][1])
        dart.add_child(poly)

    node = pegg.load_egg_data(data)
    if node is None:
        raise RuntimeError('skinned chain egg failed to load')
    np = p3d.NodePath(node)
    np.set_two_sided(True)
    return np


def character_blend_info(np):
    """(has_character, has_blend_table) for a loaded model — used by tests
    to assert the caster really is soft-skinned (guards against the egg
    loader silently rigidifying the geometry)."""
    char = np.find('**/+Character')
    has_char = not char.is_empty()
    has_blend = False
    for geom_np in np.find_all_matches('**/+GeomNode'):
        gnode = geom_np.node()
        for i in range(gnode.get_num_geoms()):
            vdata = gnode.get_geom(i).get_vertex_data()
            if vdata.get_transform_blend_table() is not None:
                has_blend = True
    return has_char, has_blend


def apply_flat_pbr_surface(np, rgb=(0.8, 0.8, 0.8)):
    """Give a mesh a neutral PBR surface: gray base-color material,
    white modulate texture (so shaders that sample a base-color texture
    get 1.0), full roughness to keep shading mostly diffuse."""
    mat = p3d.Material('paxtest_gray')
    mat.set_base_color(p3d.LColor(rgb[0], rgb[1], rgb[2], 1))
    if hasattr(mat, 'set_roughness'):
        mat.set_roughness(0.9)
        mat.set_metallic(0.0)
    np.set_material(mat, 1)

    tex = p3d.Texture('paxtest_white')
    tex.setup_2d_texture(1, 1, p3d.Texture.T_unsigned_byte, p3d.Texture.F_rgb8)
    tex.set_clear_color(p3d.LColor(1, 1, 1, 1))
    np.set_texture(tex, 1)
    return np
