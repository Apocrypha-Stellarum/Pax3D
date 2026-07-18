"""paxtest: the ER-003 data-texture contract (16-bit/float heightfields).

The Unity terrain-asset standard (game repo ER-003) makes single-channel
>=16-bit textures the terrain data interchange: heightfield stamps as
16-bit TIFF/PNG, float EXR; splat/weight maps as R16/R32F or RGBA8.
The 2025 FPS-loader terracing came from silent 8-bit/lossy conversions
in exactly this class, so the contract is: data textures are never
quantized, never sRGB-transfer-flagged, never auto-compressed. This test
turns that from observed behaviour into a gated guarantee, HOSTILE
CONFIG LIVE: the whole run executes under `compressed-textures 1`, the
prc that drives every CM_default texture into lossy block compression
(F_r16 -> RGTC1/BC4, F_luminance -> DXT1) at prepare time.

Checks:
  1. Wire-format precision: a 512-wide 16-bit PNG gradient loads as
     T_unsigned_short (16-bit TIFF checked opportunistically — write
     support varies; reads of the real packs are measured in ER-003).
  2. data_texture() stamp: format normalized to F_r16, compression
     CM_off, ATS_none; idempotent; unflags sRGB formats.
  3. THE ANTI-TERRACING ASSERTION: the gradient spans 1022 16-bit codes
     (< 4 8-bit codes); a probe shader amplifies it by 64 and the
     rendered card must show > 64 distinct output levels. An 8-bit
     negative control of the same gradient must band to <= 16 levels —
     proving the probe can fail (sample-geometry discipline, fact #12).
  4. GPU round-trip: extract_texture_data returns the stamped textures'
     texels byte-identical (R16 file route AND procedural
     set_ram_image float route), ram compression CM_off — while an
     UNSTAMPED F_rgb8 control texture comes back block-compressed,
     proving the hostile prc was actually live (not a vacuous pass).
  5. set_srgb_inputs(True) leaves a stamped data texture alone even in
     the worst case (riding an M_modulate texture stage).
  6. The texture-scale trap: with `texture-scale 0.25` live,
     Texture.read() DOES downscale (the trap is real) while
     load_data_texture() returns full size and byte-exact texels (the
     blessed file route is immune).

Only meaningful for pax3d_render (data_texture/load_data_texture +
set_srgb_inputs live there); run under both engines — identical results
is itself the usual signal.
"""
import argparse
import array
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

# Hostile config, set before ShowBase: every CM_default texture gets
# driver-compressed at prepare time. The contract must hold under it.
p3d.load_prc_file_data('paxtest_data_texture', 'compressed-textures 1')

import common

W, H = 512, 4       # gradient texture size
GAIN = 64.0         # probe amplification: 1022/65535 * 64 = 0.998 max
DATA_FY = 0.3       # film-y of the 16-bit card's center
CTRL_FY = -0.3      # film-y of the 8-bit control card's center


def build_gradient_image():
    """16-bit grayscale ramp: texel x holds 2*x/65535 (1022 codes total,
    i.e. under 4 8-bit codes — invisible to any 8-bit path)."""
    img = p3d.PNMImage(W, H, 1, 65535)
    for x in range(W):
        v = (x * 2) / 65535.0
        for y in range(H):
            img.set_gray(x, y, v)
    return img


def build_tiff16_bytes():
    """A minimal uncompressed little-endian 16-bit grayscale TIFF holding
    the same ramp as build_gradient_image() — hand-rolled because Panda's
    TIFF writer crashes on 16-bit output (see call site)."""
    import struct
    data = b''.join(struct.pack('<H', x * 2)
                    for y in range(H) for x in range(W))
    ifd_offset = 8 + len(data)
    entries = [
        (256, 4, W),            # ImageWidth
        (257, 4, H),            # ImageLength
        (258, 3, 16),           # BitsPerSample
        (259, 3, 1),            # Compression: none
        (262, 3, 1),            # Photometric: BlackIsZero
        (273, 4, 8),            # StripOffsets: data right after header
        (277, 3, 1),            # SamplesPerPixel
        (278, 4, H),            # RowsPerStrip
        (279, 4, len(data)),    # StripByteCounts
        (339, 3, 1),            # SampleFormat: unsigned integer
    ]
    ifd = struct.pack('<H', len(entries))
    for tag, typ, value in entries:
        ifd += struct.pack('<HHI', tag, typ, 1)
        ifd += struct.pack('<I', value) if typ == 4 \
            else struct.pack('<HH', value, 0)
    ifd += struct.pack('<I', 0)  # no next IFD
    return struct.pack('<2sHI', b'II', 42, ifd_offset) + data + ifd


def probe_shader(use_330):
    """Minimal pass-through: out = texture(data_tex, uv).r * u_gain."""
    if use_330:
        vert = """#version 330
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;
out vec2 v_uv;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_uv = p3d_MultiTexCoord0;
}
"""
        frag = """#version 330
uniform sampler2D data_tex;
uniform float u_gain;
in vec2 v_uv;
out vec4 o_color;
void main() {
    float v = texture(data_tex, v_uv).r * u_gain;
    o_color = vec4(v, v, v, 1.0);
}
"""
    else:
        vert = """#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
attribute vec4 p3d_Vertex;
attribute vec2 p3d_MultiTexCoord0;
varying vec2 v_uv;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_uv = p3d_MultiTexCoord0;
}
"""
        frag = """#version 120
uniform sampler2D data_tex;
uniform float u_gain;
varying vec2 v_uv;
void main() {
    float v = texture2D(data_tex, v_uv).r * u_gain;
    gl_FragColor = vec4(v, v, v, 1.0);
}
"""
    return p3d.Shader.make(p3d.Shader.SL_GLSL, vertex=vert, fragment=frag)


def set_nearest(tex):
    tex.set_minfilter(p3d.SamplerState.FT_nearest)
    tex.set_magfilter(p3d.SamplerState.FT_nearest)


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'data_texture')
    if args.pipeline != 'pax3d_render':
        h.report.skip('the data-texture contract API lives in pax3d_render '
                      '(data_texture / load_data_texture / set_srgb_inputs)')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = h.adapter.pipeline

    if common.PAX3D_ROOT not in sys.path:
        sys.path.insert(0, common.PAX3D_ROOT)
    from pax3d_render import data_texture, load_data_texture

    base = h.base
    h.set_ortho(film_h=2.0)
    shader = probe_shader(h.use_330)
    os.makedirs(common.OUTPUT_DIR, exist_ok=True)

    # --- 1. Wire-format precision (PNG16 core, TIFF16 opportunistic) ---
    src_img = build_gradient_image()
    png_path = os.path.join(common.OUTPUT_DIR, 'data_texture_grad16.png')
    src_img.write(p3d.Filename.from_os_specific(png_path))

    tex16 = p3d.Texture('grad16')
    ok = tex16.read(p3d.Filename.from_os_specific(png_path))
    h.report.check(
        'png16_precision',
        ok and tex16.get_component_type() == p3d.Texture.T_unsigned_short
        and tex16.get_num_components() == 1,
        f'16-bit PNG loads at native precision (type='
        f'{tex16.get_component_type()}, components='
        f'{tex16.get_num_components()}, format={tex16.get_format()})')

    # The stamp packs' wire format is 16-bit TIFF. Panda's TIFF WRITER
    # hard-crashes on maxval > 255 (native, no traceback — measured on
    # BOTH engines 2026-07-19, upstream behavior; intake must write
    # PNG16, never TIFF16, via Panda) — so the reader is gated with a
    # hand-rolled minimal TIFF instead.
    tif_path = os.path.join(common.OUTPUT_DIR, 'data_texture_grad16.tif')
    with open(tif_path, 'wb') as f:
        f.write(build_tiff16_bytes())
    ttif = p3d.Texture('grad16_tif')
    ok = ttif.read(p3d.Filename.from_os_specific(tif_path))
    h.report.check(
        'tiff16_precision',
        ok and ttif.get_component_type() == p3d.Texture.T_unsigned_short
        and ttif.get_num_components() == 1,
        f'16-bit grayscale TIFF (the stamp packs\' wire format) loads at '
        f'native precision (ok={ok}, type={ttif.get_component_type()}, '
        f'components={ttif.get_num_components()})')

    # --- 2. The stamp -------------------------------------------------
    data_texture(tex16)
    h.report.check(
        'stamp_contract',
        tex16.get_format() == p3d.Texture.F_r16
        and tex16.get_compression() == p3d.Texture.CM_off
        and tex16.get_auto_texture_scale() == p3d.ATS_none,
        f'data_texture(): F_r16 + CM_off + ATS_none '
        f'(format={tex16.get_format()})')
    orig16 = bytes(tex16.get_ram_image())

    state = (tex16.get_format(), tex16.get_compression(),
             tex16.get_auto_texture_scale(), orig16)
    data_texture(tex16)
    h.report.check(
        'stamp_idempotent',
        state == (tex16.get_format(), tex16.get_compression(),
                  tex16.get_auto_texture_scale(),
                  bytes(tex16.get_ram_image())),
        'second stamp is an exact no-op')

    tsrgb = p3d.Texture('flagged_srgb')
    tsrgb.setup_2d_texture(4, 4, p3d.Texture.T_unsigned_byte,
                           p3d.Texture.F_srgb)
    data_texture(tsrgb)
    h.report.check(
        'stamp_unflags_srgb',
        tsrgb.get_format() == p3d.Texture.F_rgb8,
        f'a pre-flagged F_srgb texture is unflagged to F_rgb8 '
        f'({tsrgb.get_format()})')

    # Procedural float route (the game's worker-thread splat/height path:
    # numpy/array -> set_ram_image)
    tex32 = p3d.Texture('grad32f')
    tex32.setup_2d_texture(W, 1, p3d.Texture.T_float, p3d.Texture.F_r32)
    buf32 = array.array('f', [(x * 2) / 65535.0 for x in range(W)])
    tex32.set_ram_image(buf32.tobytes())
    data_texture(tex32)
    orig32 = bytes(tex32.get_ram_image())

    # 8-bit negative control: the same ramp quantized to 8 bits — under
    # the same stamp and probe it MUST band (proves the probe can fail)
    tex8 = p3d.Texture('grad8')
    tex8.setup_2d_texture(W, 1, p3d.Texture.T_unsigned_byte,
                          p3d.Texture.F_red)
    tex8.set_ram_image(bytes(round((x * 2 / 65535.0) * 255)
                             for x in range(W)))
    data_texture(tex8)

    # Unstamped compression canary: CM_default F_rgb8, must come back
    # from the GPU block-compressed or the hostile prc wasn't live
    ctrl = p3d.Texture('comp_canary')
    ctrl.setup_2d_texture(64, 64, p3d.Texture.T_unsigned_byte,
                          p3d.Texture.F_rgb8)
    ctrl.set_ram_image(bytes((x * 7 + 13) % 256 for x in range(64 * 64 * 3)))

    # --- Scene: probe cards ------------------------------------------
    def probe_card(left, right, bottom, top, tex, gain, name):
        cm = p3d.CardMaker(name)
        cm.set_frame(left, right, bottom, top)
        np_ = base.render.attach_new_node(cm.generate())
        np_.set_two_sided(True)
        np_.set_shader(shader, 100)
        np_.set_shader_input('data_tex', tex)
        np_.set_shader_input('u_gain', gain)
        return np_

    for t in (tex16, tex8, tex32):
        set_nearest(t)
    probe_card(-1.0, 1.0, DATA_FY - 0.2, DATA_FY + 0.2, tex16, GAIN, 'data16')
    probe_card(-1.0, 1.0, CTRL_FY - 0.2, CTRL_FY + 0.2, tex8, GAIN, 'ctrl8')
    # Mini cards: just force the float texture and the canary to prepare
    probe_card(-1.0, -0.8, 0.55, 0.65, tex32, GAIN, 'float32')
    probe_card(-0.7, -0.5, 0.55, 0.65, ctrl, 1.0, 'canary')

    h.step(5)
    img = h.capture()
    h.save_capture(img, 'gradient')

    # --- 3. Anti-terracing: distinct rendered levels ------------------
    def distinct_levels(fy):
        py = int((0.5 - fy / 2.0) * h.win_h)
        vals = set()
        for x in range(h.win_w):
            vals.add(int(round(common.lum_at(img, x, py) * 255)))
        return len(vals)

    n16 = distinct_levels(DATA_FY)
    n8 = distinct_levels(CTRL_FY)
    h.report.check(
        'render_levels_16bit', n16 > 64,
        f'1022-code gradient renders {n16} distinct levels (>64 = the '
        f'sampled texture is genuinely >8-bit; terracing would band it)')
    h.report.check(
        'render_levels_8bit_control', n8 <= 16,
        f'8-bit control renders {n8} distinct levels (<=16 = the probe '
        f'can fail — sample geometry proven)')

    # --- 4. GPU round-trips under the hostile prc ---------------------
    gsg = base.win.get_gsg()

    def roundtrip(tex, orig, tag):
        ok = base.graphics_engine.extract_texture_data(tex, gsg)
        got = bytes(tex.get_ram_image()) if ok else b''
        comp = tex.get_ram_image_compression()
        h.report.check(
            tag, ok and comp == p3d.Texture.CM_off and got == orig,
            f'extract={ok} compression={comp} bytes '
            f'{"identical" if got == orig else "DIFFER"} '
            f'({len(orig)} bytes)')

    roundtrip(tex16, orig16, 'gpu_roundtrip_r16')
    roundtrip(tex32, orig32, 'gpu_roundtrip_r32f')

    ok = base.graphics_engine.extract_texture_data(ctrl, gsg)
    h.report.check(
        'compression_canary_live',
        ok and ctrl.get_ram_image_compression() != p3d.Texture.CM_off,
        f'unstamped F_rgb8 canary came back compression='
        f'{ctrl.get_ram_image_compression()} (!= CM_off proves '
        f'compressed-textures 1 was live, so the round-trips above '
        f'passed against a real threat)')

    # --- 5. set_srgb_inputs leaves data textures alone ----------------
    # Worst case: the data texture riding an M_modulate stage (shader-
    # input bindings are never even walked; a stage IS walked).
    cm = p3d.CardMaker('srgb_worst_case')
    cm.set_frame(3.0, 3.5, -0.2, 0.2)   # off-film; graph walk still sees it
    worst = base.render.attach_new_node(cm.generate())
    worst.set_texture(tex16, 1)
    n = pipeline.set_srgb_inputs(True)
    h.report.check(
        'srgb_walk_leaves_data',
        tex16.get_format() == p3d.Texture.F_r16,
        f'set_srgb_inputs(True) (converted {n}) left the stamped R16 '
        f'texture alone even on an M_modulate stage '
        f'({tex16.get_format()})')
    pipeline.set_srgb_inputs(False)

    # --- 6. The texture-scale trap and the immune file route ----------
    p3d.load_prc_file_data('paxtest_data_texture_scale', 'texture-scale 0.25')
    t_trap = p3d.Texture('trap')
    t_trap.read(p3d.Filename.from_os_specific(png_path))
    h.report.check(
        'texture_scale_trap_real',
        t_trap.get_x_size() == W // 4,
        f'Texture.read() under texture-scale 0.25: {W} -> '
        f'{t_trap.get_x_size()} texels (the read-time trap is real; '
        f'ATS/stamps cannot guard it)')
    t_safe = load_data_texture(png_path)
    h.report.check(
        'load_data_texture_immune',
        t_safe.get_x_size() == W
        and t_safe.get_format() == p3d.Texture.F_r16
        and bytes(t_safe.get_ram_image()) == orig16,
        f'load_data_texture() under the same prc: {t_safe.get_x_size()} '
        f'texels, format={t_safe.get_format()}, bytes '
        f'{"identical to" if bytes(t_safe.get_ram_image()) == orig16 else "DIFFER from"} '
        f'the direct-read original')
    p3d.load_prc_file_data('paxtest_data_texture_scale', 'texture-scale 1')

    h.report.finish()


if __name__ == '__main__':
    main()
