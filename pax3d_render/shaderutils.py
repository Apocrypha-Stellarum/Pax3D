"""pax3d_render shader utilities.

Loads GLSL shaders from the package's shaders/ directory, injects #define
directives, and compiles into Panda3D Shader objects.

Shader sources are written in GLSL 120 with a mechanical upgrade to GLSL 330
when a modern context is configured (gl-version 3 2). The legacy 120 path
exists only to keep rendering byte-identical with the game's previous
pipeline during the R1 transition — it is scheduled for removal once the
game runs on gl-version 3 2 (see PAX3D_MASTER_PLAN.md R1.4).
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

    shaderstr = _add_shader_defines(shaderstr, defines)

    use_330 = defines.get('USE_330', False)
    use_webgl = defines.get('IS_WEBGL', False)

    if use_330:
        if use_webgl:
            shaderstr = shaderstr.replace(
                '#version 120',
                '#version 300 es\nprecision highp float;\n'
            )
        shaderstr = shaderstr.replace('#version 120', '#version 330')
        if shaderpath.endswith('vert'):
            shaderstr = shaderstr.replace('varying ', 'out ')
            shaderstr = shaderstr.replace('attribute ', 'in ')
        else:
            shaderstr = shaderstr.replace('varying ', 'in ')
    elif use_webgl:
        shaderstr = shaderstr.replace(
            '#version 120',
            '#version 100\nprecision highp float;\n'
        )

    return shaderstr


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
