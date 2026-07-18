"""Convert an equirectangular panorama (.hdr etc.) to a Panda cubemap .txo.

The missing front end of the R5 environment chain: skybox sources are
usually equirect panoramas (the openworld village HDRIs, most HDRI
libraries), while `gen_env_prefilter.py`, `set_env_map`, and
`sh_from_cubemap` all consume CUBE maps. pip simplepbr 0.13.1's hdr2env
has no equirect support either (its `from_file_path` just calls
`load_cube_map`), so this tool is ours — but the face/texel direction
convention is BORROWED VERBATIM from simplepbr's `calc_vector`, i.e. the
exact convention the prefilter tool, the SH projector, and the shader
sampling path were all verified against (the PINNED face table: face 0
= +x east, 1 = -x west, 2 = +y north, 3 = -y south, 4 = +z up,
5 = -z down; arch doc S9 R5.2).

Equirect convention (documented, checked by --selftest):
  - columns: azimuth. Image CENTER column faces +y NORTH; azimuth
    increases eastward (+x east at 3/4 across). Skyboxes are rotated by
    content anyway — if your dome shader anchors differently, spin the
    result or the dome, not this tool.
  - rows: elevation. Image TOP row is the ZENITH (+z), bottom the nadir.
  - Sampling: bilinear, azimuth wraps, elevation clamps;
    `--supersample N` averages NxN sub-texel taps (default 2 — keeps a
    small HDR sun from aliasing away at cube resolutions).

Measured fact baked into the code: `TexturePeeker.fetch_pixel` row 0 is
the image's BOTTOM row (Panda RAM images are bottom-up; probed
2026-07-18 on stock and Pax3D engines).

Values pass through RAW (no sRGB decode, float in float out) —
consistent with the pipeline color contract and gen_env_prefilter.

Usage (dev-time; runtime loads the .txo):

    python tools/gen_equirect_cubemap.py pano.hdr sky_cube.txo [--size 256]
    python tools/gen_equirect_cubemap.py --selftest

Then feed the result to the rest of the chain:

    python tools/gen_env_prefilter.py sky_cube.txo sky_ibl.txo
    # pipeline.set_env_map(loader.load_texture('sky_ibl.txo'))
    # pipeline.set_ambient_sh(sh_from_cubemap(tex))
"""
import argparse
import math
import os
import struct
import sys
import tempfile

import panda3d.core as p3d


def calc_vector(dim, face_idx, xloc, yloc):
    """simplepbr._ibl_funcs_cpu.calc_vector, verbatim (float-friendly).

    RAM texel (x, y) of a cube face -> world direction, corner-stretched
    (index/(dim-1)) exactly like the reference, so this tool's output is
    orientation-consistent with the prefilter/SH consumers.
    """
    maxidx = dim - 1
    xcoord = xloc / maxidx * 2 - 1
    ycoord = (maxidx - yloc) / maxidx * 2 - 1
    unitlength = 1.00001
    if face_idx == 0:
        return (unitlength, ycoord, -xcoord)
    if face_idx == 1:
        return (-unitlength, ycoord, xcoord)
    if face_idx == 2:
        return (xcoord, unitlength, -ycoord)
    if face_idx == 3:
        return (xcoord, -unitlength, ycoord)
    if face_idx == 4:
        return (xcoord, ycoord, unitlength)
    return (-xcoord, ycoord, -unitlength)


class EquirectSampler:
    """Bilinear sampler over a 2D texture's RAM image via TexturePeeker."""

    def __init__(self, tex):
        self.peeker = tex.peek()
        if self.peeker is None:
            sys.exit('cannot peek input texture (no RAM image?)')
        self.w = tex.get_x_size()
        self.h = tex.get_y_size()
        self._c = p3d.LColor()

    def _fetch(self, x, y):
        self.peeker.fetch_pixel(self._c, x % self.w,
                                min(max(y, 0), self.h - 1))
        return (self._c[0], self._c[1], self._c[2])

    def sample_direction(self, d):
        """Bilinear equirect sample for unit direction d (Panda Z-up)."""
        azimuth = math.atan2(d[0], d[1])          # 0 north, + east
        elevation = math.asin(min(max(d[2], -1.0), 1.0))
        # peeker rows are bottom-up: row 0 = image bottom = nadir
        fx = (0.5 + azimuth / (2.0 * math.pi)) * self.w - 0.5
        fy = (0.5 + elevation / math.pi) * self.h - 0.5
        x0, y0 = math.floor(fx), math.floor(fy)
        tx, ty = fx - x0, fy - y0
        c00 = self._fetch(x0, y0)
        c10 = self._fetch(x0 + 1, y0)
        c01 = self._fetch(x0, y0 + 1)
        c11 = self._fetch(x0 + 1, y0 + 1)
        return tuple(
            (c00[i] * (1 - tx) + c10[i] * tx) * (1 - ty)
            + (c01[i] * (1 - tx) + c11[i] * tx) * ty
            for i in range(3))


def convert(tex, size, supersample):
    """Equirect texture -> float cube map of `size`, simplepbr layout."""
    sampler = EquirectSampler(tex)
    out = p3d.Texture('equirect_cube')
    out.setup_cube_map(size, p3d.Texture.T_float, p3d.Texture.F_rgb32)
    out.wrap_u = p3d.SamplerState.WM_clamp
    out.wrap_v = p3d.SamplerState.WM_clamp
    out.wrap_w = p3d.SamplerState.WM_clamp
    out.minfilter = p3d.SamplerState.FT_linear_mipmap_linear
    out.magfilter = p3d.SamplerState.FT_linear

    pixelsize = out.component_width * out.num_components
    texdata = p3d.PTA_uchar.empty_array(size * size * 6 * pixelsize)
    n = max(1, supersample)
    subs = [(i + 0.5) / n - 0.5 for i in range(n)]
    for face in range(6):
        for y in range(size):
            for x in range(size):
                r = g = b = 0.0
                for dy in subs:
                    for dx in subs:
                        v = calc_vector(size, face, x + dx, y + dy)
                        ln = math.sqrt(v[0] * v[0] + v[1] * v[1]
                                       + v[2] * v[2])
                        c = sampler.sample_direction(
                            (v[0] / ln, v[1] / ln, v[2] / ln))
                        r += c[0]
                        g += c[1]
                        b += c[2]
                k = 1.0 / (n * n)
                offset = ((face * size + y) * size + x) * pixelsize
                struct.pack_into('fff', texdata, offset,
                                 b * k, g * k, r * k)
    out.set_ram_image(texdata)
    return out


def selftest():
    """Compass-panorama round trip against the pinned face table."""
    north, east, south, west = ((0, 1, 0), (1, 0, 0),
                                (1, 1, 0), (0, 0, 1))
    zenith, nadir = (1, 1, 1), (0, 0, 0)
    img = p3d.PNMImage(128, 64)
    for y in range(64):
        # image rows top-down: y=0 zenith
        elevation = math.degrees((0.5 - (y + 0.5) / 64) * math.pi)
        for x in range(128):
            if elevation > 60:
                c = zenith
            elif elevation < -60:
                c = nadir
            else:
                azimuth = ((x + 0.5) / 128 - 0.5) * 360  # 0 north, + east
                if -45 <= azimuth < 45:
                    c = north
                elif 45 <= azimuth < 135:
                    c = east
                elif azimuth >= 135 or azimuth < -135:
                    c = south
                else:
                    c = west
            img.set_xel(x, y, *c)
    path = os.path.join(tempfile.gettempdir(), 'equirect_selftest.png')
    img.write(p3d.Filename.from_os_specific(path))
    tex = p3d.TexturePool.load_texture(p3d.Filename.from_os_specific(path))
    cube = convert(tex, 16, 2)

    peeker = cube.peek()
    c = p3d.LColor()
    failures = []

    def check(name, got, want):
        err = max(abs(got[i] - want[i]) for i in range(3))
        ok = err < 0.1
        print(f'  [{"ok" if ok else "FAIL"}] {name}: '
              f'got ({got[0]:.2f},{got[1]:.2f},{got[2]:.2f}) '
              f'want {want}')
        if not ok:
            failures.append(name)

    for name, d, want in (('east  +x', (1, 0, 0), east),
                          ('west  -x', (-1, 0, 0), west),
                          ('north +y', (0, 1, 0), north),
                          ('south -y', (0, -1, 0), south),
                          ('up    +z', (0, 0, 1), zenith),
                          ('down  -z', (0, 0, -1), nadir)):
        peeker.lookup(c, *d)
        check(name, (c[0], c[1], c[2]), want)
    # Face-table orientation: up-face RAM row 0 leans NORTH (the
    # file-loaded flip side of "up-face image top row = southern sky")
    peeker.fetch_pixel(c, 8, 0, 4)
    check('up-face RAM row 0 = north sky', (c[0], c[1], c[2]), north)
    peeker.fetch_pixel(c, 8, 15, 4)
    check('up-face RAM row 15 = south sky', (c[0], c[1], c[2]), south)

    if failures:
        sys.exit(f'SELFTEST FAILED: {failures}')
    print('SELFTEST OK — equirect conversion matches the pinned face table')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', nargs='?', help='equirect panorama '
                        '(.hdr/.png/... — anything Panda loads)')
    parser.add_argument('output', nargs='?', help='output cubemap .txo')
    parser.add_argument('--size', type=int, default=256,
                        help='cube face resolution (default 256)')
    parser.add_argument('--supersample', type=int, default=2,
                        help='NxN sub-texel taps per output texel '
                             '(default 2)')
    parser.add_argument('--selftest', action='store_true',
                        help='verify the face table on a synthetic '
                             'compass panorama and exit')
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return
    if not args.input or not args.output:
        parser.error('input and output are required (or --selftest)')

    tex = p3d.TexturePool.load_texture(
        p3d.Filename.from_os_specific(args.input))
    if tex is None:
        sys.exit(f'cannot load {args.input}')
    if not tex.has_ram_image():
        sys.exit(f'{args.input} has no readable RAM image')
    print(f'converting {tex.get_x_size()}x{tex.get_y_size()} equirect -> '
          f'{args.size}px cube faces ({args.supersample}x{args.supersample} '
          f'taps/texel)')
    import time
    t0 = time.time()
    cube = convert(tex, args.size, args.supersample)
    print(f'converted in {time.time() - t0:.1f}s')
    out = p3d.Filename.from_os_specific(os.path.abspath(args.output))
    if not cube.write(out):
        sys.exit(f'failed to write {args.output}')
    reloaded = p3d.TexturePool.load_texture(out)
    ok = (reloaded is not None
          and reloaded.get_texture_type() == p3d.Texture.TT_cube_map
          and reloaded.get_x_size() == args.size)
    if not ok:
        sys.exit('round-trip sanity FAILED')
    print(f'wrote {args.output} ({args.size}px cube). Next: '
          f'tools/gen_env_prefilter.py {args.output} <name>_ibl.txo')


if __name__ == '__main__':
    main()
