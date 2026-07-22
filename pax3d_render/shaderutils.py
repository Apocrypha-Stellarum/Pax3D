"""pax3d_render shader utilities.

Loads GLSL shaders from the package's shaders/ directory, injects #define
directives, and compiles into Panda3D Shader objects.

Shader sources are native GLSL 330 (R1.4, 2026-07-23: the GLSL-120 dual
path was removed after the game moved to `gl-version 3 2` everywhere;
sources were baked from the transformed 330 output, gate-verified).
"""
import os

import panda3d.core as p3d

# Shader directory: <package>/shaders/
_SHADER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'shaders')


def _add_shader_defines(shaderstr, defines):
    """Inject #define lines after the #version directive."""
    shaderlines = shaderstr.split('\n')

    version_line = None
    for line in shaderlines:
        if '#version' in line:
            version_line = line
            break

    if version_line is None:
        raise RuntimeError('Failed to find GLSL version string')

    shaderlines.remove(version_line)

    define_lines = [
        f'#define {define} {value if value is not True else ""}'
        for define, value in defines.items()
        if value
    ]

    return '\n'.join(
        [version_line]
        + define_lines
        + ['#line 1']
        + shaderlines
    )


def _load_shader_str(shaderpath, defines=None):
    """Load a shader source file from disk and inject defines."""
    filepath = os.path.join(_SHADER_DIR, shaderpath)
    with open(filepath, encoding='utf8') as f:
        shaderstr = f.read()

    if defines is None:
        defines = {}

    defines['p3d_TextureBaseColor'] = 'p3d_TextureModulate'
    defines['p3d_TextureMetalRoughness'] = 'p3d_TextureSelector'

    return _add_shader_defines(shaderstr, defines)


def make_shader(name, vertex, fragment, defines):
    """Load, preprocess, and compile a GLSL shader pair."""
    vertstr = _load_shader_str(vertex, defines)
    fragstr = _load_shader_str(fragment, defines)
    shader = p3d.Shader.make(
        p3d.Shader.SL_GLSL,
        vertstr,
        fragstr
    )
    shader.set_filename(p3d.Shader.ST_none, name)
    return shader
