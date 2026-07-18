"""probe_texturestage: where TextureStage combine modes actually run.

Answers the openworld round-4 P2 ask (PAX3D_FEEDBACK_2.md, 2026-07-18
retraction): under `gl-version 3 2` (core profile) the FFP-emulation path
silently drops CM_combine constants, rgb_scale, and CM_interpolate while
honoring set_color_scale — expected, or a fork regression?

Mechanism (verified in source, this probe verifies behavior):

- Core profile => `has_fixed_function_pipeline()` false. Any state WITHOUT
  an explicit shader is drawn by glgsg's built-in `_default_shader`
  (glGraphicsStateGuardian_src.cxx:189-303): ONE texture stage,
  `textureProj(tex0) * (vertexColor * colorScale) + texAlphaOnly`.
  No combine modes, no stage constants, no rgb_scale, no second stage.
  Color scale rides the shader => live and unclamped. This is upstream
  behavior, not fork surgery.
- The full ShaderGenerator (which DOES implement combine modes,
  shaderGenerator.cxx:1899+) only runs for states carrying
  `set_shader_auto()` (`auto_shader()`, graphicsStateGuardian.cxx:3998),
  and it emits Cg (`//Cg`, shaderGenerator.cxx:777). If the Cg shader
  cannot compile in the current context, do_issue_shader falls back to
  the same `_default_shader` (glGraphicsStateGuardian_src.cxx:8866).

Three quads, one decisive pixel each:

    left    M_combine: CM_modulate(texture, constant RED)
            works -> (0.5, 0, 0)      ignored -> gray 0.5
    center  M_combine: CM_replace(texture) with rgb_scale=2
            works -> (1.0, 1.0, 1.0)  ignored -> gray 0.5
    right   stage2 CM_interpolate(constant GREEN, previous, constant.a=0.5)
            works -> (0.25, 0.75, 0.25)  ignored -> gray 0.5

Modes:
    compat-plain  default context, no shader calls   (true FFP reference)
    compat-auto   default context, set_shader_auto() (Cg ShaderGenerator)
    core-plain    gl-version 3 2, no shader calls    (the game's dome path)
    core-auto     gl-version 3 2, set_shader_auto()

Run:  python tools/paxtest/probe_texturestage.py            # all modes
      python tools/paxtest/probe_texturestage.py core-plain # one mode
"""
import os
import subprocess
import sys

MODES = ('compat-plain', 'compat-auto', 'core-plain', 'core-auto')

TOL = 0.04  # 8-bit readback + driver wiggle


def run_mode(mode):
    import panda3d.core as p3d

    prc = ['window-type offscreen', 'win-size 256 256', 'sync-video 0',
           'audio-library-name null', 'notify-level-glgsg error']
    if mode.startswith('core'):
        prc.append('gl-version 3 2')
    for line in prc:
        p3d.load_prc_file_data('probe_texturestage', line)

    from direct.showbase.ShowBase import ShowBase
    base = ShowBase()

    # 8x8 mid-gray texture (129/255 ~ 0.506 keeps rounding honest).
    tex = p3d.Texture('gray')
    tex.setup_2d_texture(8, 8, p3d.Texture.T_unsigned_byte, p3d.Texture.F_rgba)
    tex.set_ram_image(bytes([129, 129, 129, 255]) * 64)

    cm = p3d.CardMaker('quad')
    cm.set_frame(-1, 1, -1, 1)

    def make_quad(x):
        np = base.render2d.attach_new_node(cm.generate())
        np.set_scale(1.0 / 3.0, 1, 1)
        np.set_pos(x, 0, 0)
        return np

    # LEFT: combine modulate(texture, constant RED)
    left = make_quad(-2.0 / 3.0)
    st = p3d.TextureStage('combine_const')
    st.set_combine_rgb(p3d.TextureStage.CM_modulate,
                       p3d.TextureStage.CS_texture, p3d.TextureStage.CO_src_color,
                       p3d.TextureStage.CS_constant, p3d.TextureStage.CO_src_color)
    st.set_color((1, 0, 0, 1))
    left.set_texture(st, tex)

    # CENTER: combine replace(texture) with rgb_scale 2
    center = make_quad(0)
    st2 = p3d.TextureStage('combine_scale')
    st2.set_combine_rgb(p3d.TextureStage.CM_replace,
                        p3d.TextureStage.CS_texture, p3d.TextureStage.CO_src_color)
    st2.set_rgb_scale(2)
    center.set_texture(st2, tex)

    # RIGHT: base replace(texture), then interpolate(GREEN, previous, a=0.5)
    right = make_quad(2.0 / 3.0)
    stb = p3d.TextureStage('base')
    stb.set_combine_rgb(p3d.TextureStage.CM_replace,
                        p3d.TextureStage.CS_texture, p3d.TextureStage.CO_src_color)
    stb.set_sort(0)
    stf = p3d.TextureStage('fade')
    stf.set_combine_rgb(p3d.TextureStage.CM_interpolate,
                        p3d.TextureStage.CS_constant, p3d.TextureStage.CO_src_color,
                        p3d.TextureStage.CS_previous, p3d.TextureStage.CO_src_color,
                        p3d.TextureStage.CS_constant, p3d.TextureStage.CO_src_alpha)
    stf.set_color((0, 1, 0, 0.5))
    stf.set_sort(1)
    right.set_texture(stb, tex)
    right.set_texture(stf, tex)

    if mode.endswith('auto'):
        for np in (left, center, right):
            np.set_shader_auto()

    for _ in range(3):
        base.graphicsEngine.render_frame()

    img = p3d.PNMImage()
    base.win.get_screenshot().store(img)
    w, h = img.get_x_size(), img.get_y_size()

    def sample(fx):
        x, y = int(fx * w), h // 2
        return tuple(round(v, 3) for v in
                     (img.get_red(x, y), img.get_green(x, y), img.get_blue(x, y)))

    g = 129.0 / 255.0
    checks = [
        ('combine_constant', sample(1.0 / 6.0), (g, 0.0, 0.0)),
        ('rgb_scale_2', sample(0.5), (min(1.0, 2 * g),) * 3),
        ('interpolate', sample(5.0 / 6.0), (0.5 * g, 0.5 + 0.5 * g, 0.5 * g)),
    ]
    for name, got, want in checks:
        live = all(abs(a - b) <= TOL for a, b in zip(got, want))
        inert = all(abs(a - g) <= TOL for a in got)
        verdict = 'WORKS' if live else ('IGNORED (base tex passthrough)' if inert
                                        else 'OTHER')
        print('%-14s %-16s got=%s want=%s' % (mode, name, got, want), verdict)
    base.destroy()


def main():
    if len(sys.argv) > 1:
        run_mode(sys.argv[1])
        return
    here = os.path.abspath(__file__)
    for mode in MODES:
        r = subprocess.run([sys.executable, here, mode],
                           capture_output=True, text=True, timeout=120)
        sys.stdout.write(r.stdout)
        err = r.stderr.strip()
        if err:
            sys.stdout.write('  [stderr] %s\n' % err.splitlines()[-1])
        if r.returncode != 0:
            print('%s: probe process FAILED (exit %d)' % (mode, r.returncode))
        print()


if __name__ == '__main__':
    main()
