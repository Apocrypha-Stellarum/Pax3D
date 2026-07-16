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
