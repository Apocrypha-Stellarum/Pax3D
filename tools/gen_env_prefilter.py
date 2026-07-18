"""GGX-prefilter a cubemap into a set_env_map roughness ladder (R5.4).

Closes the Session M "first slice" gap: `set_env_map` samples
`textureCubeLod(env, r, perceptual_roughness * max_lod)`, so the cubemap's
mip chain IS the roughness ladder. Auto-generated box mips were the
documented approximation; this tool bakes the CORRECT chain — mip i is the
Karis split-sum GGX prefilter at perceptual roughness i/(levels-1), the
exact convention the shader's IBL path (and the committed BRDF LUT) was
written against.

Like tools/gen_brdf_lut.py this runs the REFERENCE sampling math from pip
simplepbr 0.13.1 (`_ibl_funcs_cpu.filter_sample` / `calc_vector` — the
Karis prefilter with GGX importance sampling) — borrowed verbatim, so the
artifact matches the library pax3d_render's shader came from. The mip
LOOP is ours: the reference's `filter_env_map` cannot address a complete
chain (its `calc_vector` divides by `dim - 1`, a ZeroDivisionError at the
1x1 level; upstream's 4-level default never reaches it), so we drive
their per-texel sampler ourselves and special-case dim=1 (texel direction
= the face axis). Inherited reference quirks, documented not hidden:
(a) the tangent basis degenerates at the exact -z pole
(`abs(normal.z < 0.999)` operates on a bool), leaving the down-face
CENTER texel unblurred at all roughness levels — one texel, invisible in
practice; (b) texel directions are corner-stretched (index/(dim-1), not
the (i+0.5)/dim center convention) — a sub-texel direction skew,
symmetric across the face.

Values are filtered RAW (no sRGB decode) — consistent with the pipeline's
current color contract (inputs are sampled raw; R1 linearization is a
separate program). The OUTPUT chain is written complete (down to 1x1), so
`set_env_map(tex)` with the default max_lod addresses it correctly —
no max_lod argument needed.

Usage (dev-time only; runtime just loads the .txo):

    C:/Python313/python.exe tools/gen_env_prefilter.py sky_#.png sky_ibl.txo
    C:/Python313/python.exe tools/gen_env_prefilter.py sky.txo sky_ibl.txo
        [--size 64] [--samples 32]

    # adoption:
    tex = loader.load_texture('sky_ibl.txo')
    pipeline.set_env_map(tex)
    pipeline.set_ambient_sh(sh_from_cubemap(tex))   # matching diffuse half

--size is the output base resolution (64 is plenty for reflections);
--samples the GGX importance samples per texel (quality knob — 32 default,
crank for hero skyboxes). Cost is CPU-side Python, roughly
size^2 * 6 * samples * 1.4 lookups; measured 2.6 s at 64/32 on the dev
machine (~40 s for a 128/64 hero bake).
"""
import argparse
import math
import os
import struct
import sys
import time

import panda3d.core as p3d


def prefilter_complete_chain(src, filtered, size, samples):
    """The reference's filter_env_map loop, extended to a COMPLETE chain.

    Per-texel work is simplepbr's own `filter_sample` (Karis split-sum,
    GGX importance sampling, NdotL weighting) with directions from its
    `calc_vector`; only the loop plumbing is ours (see module docstring).
    Mip i carries perceptual roughness i/(levels-1); the 1x1 level's
    texel direction is the face axis (what calc_vector cannot express).
    """
    from simplepbr._ibl_funcs_cpu import calc_vector, filter_sample

    peeker = src.peek()
    levels = int(math.log2(size)) + 1

    filtered.setup_cube_map(size, p3d.Texture.T_float, p3d.Texture.F_rgb32)
    filtered.magfilter = p3d.SamplerState.FT_linear
    filtered.minfilter = p3d.SamplerState.FT_linear_mipmap_linear

    pixelsize = filtered.component_width * filtered.num_components
    face_axes = [(1, 0, 0), (-1, 0, 0), (0, 1, 0),
                 (0, -1, 0), (0, 0, 1), (0, 0, -1)]

    for i in range(levels):
        mipsize = size >> i
        roughness = i / (levels - 1)
        texdata = p3d.PTA_uchar.empty_array(mipsize * mipsize * 6 * pixelsize)
        for face in range(6):
            for x in range(mipsize):
                for y in range(mipsize):
                    offset = ((face * mipsize + y) * mipsize + x) * pixelsize
                    vec = (face_axes[face] if mipsize == 1 else
                           calc_vector(mipsize, face, x, y))
                    pos = p3d.LVector3(*vec)
                    c = filter_sample(pos, peeker, roughness, samples)
                    struct.pack_into('fff', texdata, offset, c[2], c[1], c[0])
        filtered.set_ram_mipmap_image(i, texdata)
    return levels


def load_input(path):
    if '#' in path:
        tex = p3d.TexturePool.load_cube_map(
            p3d.Filename.from_os_specific(path))
    else:
        tex = p3d.TexturePool.load_texture(
            p3d.Filename.from_os_specific(path))
    if tex is None:
        sys.exit(f'cannot load {path}')
    if tex.get_texture_type() != p3d.Texture.TT_cube_map:
        sys.exit(f'{path} is not a cube map (use a six-file "#" pattern '
                 f'or a cube-map .txo/.dds)')
    if not tex.has_ram_image():
        sys.exit(f'{path} has no readable RAM image')
    return tex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='cubemap: six-file "#" pattern or file')
    parser.add_argument('output', help='output .txo path')
    parser.add_argument('--size', type=int, default=64,
                        help='output base resolution (default 64)')
    parser.add_argument('--samples', type=int, default=32,
                        help='GGX samples per texel (default 32)')
    args = parser.parse_args()

    try:
        import simplepbr._ibl_funcs_cpu  # noqa: F401 -- fail early, clearly
    except ImportError as exc:
        sys.exit(f'needs pip simplepbr (the reference prefilter): {exc}')

    src = load_input(args.input)
    levels = int(math.log2(args.size)) + 1
    print(f'prefiltering {src.get_name()} ({src.get_x_size()}px) -> '
          f'{args.size}px, {levels} mip levels (roughness ladder 0..1), '
          f'{args.samples} samples/texel')

    filtered = p3d.Texture(os.path.splitext(os.path.basename(args.output))[0])
    t0 = time.time()
    prefilter_complete_chain(src, filtered, args.size, args.samples)
    print(f'filtered in {time.time() - t0:.1f}s')

    out = p3d.Filename.from_os_specific(os.path.abspath(args.output))
    if not filtered.write(out):
        sys.exit(f'failed to write {args.output}')
    print(f'wrote {args.output}')

    # Sanity: reload, confirm the complete chain survived the round trip.
    tex = p3d.TexturePool.load_texture(out)
    n_mips = tex.get_num_ram_mipmap_images()
    img = p3d.PNMImage()
    tex.store(img, 3, 0)
    c0 = img.get_xel(img.get_x_size() // 2, img.get_y_size() // 2)
    tex.store(img, 3, n_mips - 1)
    ct = img.get_xel(0, 0)
    ok = (tex.get_texture_type() == p3d.Texture.TT_cube_map
          and tex.get_x_size() == args.size and n_mips == levels)
    print(f'reloaded: {tex.get_x_size()}px cube, {n_mips}/{levels} mip '
          f'levels; -Y face mip0 center=({c0[0]:.3f},{c0[1]:.3f},{c0[2]:.3f})'
          f' top=({ct[0]:.3f},{ct[1]:.3f},{ct[2]:.3f})')
    if not ok:
        sys.exit('round-trip sanity FAILED')
    print(f"adopt with: pipeline.set_env_map(loader.load_texture("
          f"'{args.output}'))  # default max_lod == full chain")


if __name__ == '__main__':
    main()
