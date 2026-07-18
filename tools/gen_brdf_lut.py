"""Generate pax3d_render/textures/brdf_lut.txo (Session M / R5.3).

The split-sum BRDF integration LUT for IBL specular:
`pax_pbr.frag` samples `brdf_lut` at (n_dot_v, perceptual_roughness) and
computes `ibl_spec = env_color * (F * lut.x + lut.y)`. Until Session M
the pipeline fell back to a 1x1 WHITE texture — harmless while the env
map was the 1x1 black default (ibl_spec = 0 regardless), but wrong the
moment `set_env_map()` binds a real cubemap (lut.y = 1 adds the whole
env color as a bias).

This runs the REFERENCE integrator from pip simplepbr — the library
pax3d_render's shader forked from (0.13.1), so the committed artifact
is exactly the Karis split-sum convention the shader's IBL path was
written against.

Dev-time only; runtime just loads the committed .txo:

    C:/Python313/python.exe tools/gen_brdf_lut.py [--size 128]
        [--samples 1024]
"""
import argparse
import os
import sys
import time

import panda3d.core as p3d

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'pax3d_render', 'textures', 'brdf_lut.txo')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--size', type=int, default=128)
    parser.add_argument('--samples', type=int, default=1024)
    args = parser.parse_args()

    try:
        from simplepbr._ibl_funcs_cpu import gen_brdf_lut
    except ImportError as exc:
        sys.exit(f'needs pip simplepbr (the reference integrator): {exc}')

    t0 = time.time()
    lut = gen_brdf_lut(args.size, num_samples=args.samples)
    print(f'integrated {args.size}x{args.size} @ {args.samples} samples '
          f'in {time.time() - t0:.1f}s')

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if not lut.write(p3d.Filename.from_os_specific(OUT)):
        sys.exit(f'failed to write {OUT}')
    print(f'wrote {OUT}')

    # Sanity: reload and peek the mirror corner (A ~ 1, B ~ 0).
    tex = p3d.TexturePool.load_texture(p3d.Filename.from_os_specific(OUT))
    peek = tex.peek()
    c = p3d.LColor()
    n = tex.get_x_size()
    peek.lookup(c, (n - 0.5) / n, 0.5 / n)
    print(f'reloaded {tex.get_x_size()}x{tex.get_y_size()}; '
          f'A,B at (ndv=1, rough~0) = ({c[0]:.4f}, {c[1]:.4f})')


if __name__ == '__main__':
    main()
