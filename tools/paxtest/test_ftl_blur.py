"""paxtest: FTL radial motion blur + chromatic aberration (tonemap pass).

One small bright emissive quad placed OFF-CENTER (+x of the blur
center).  Checks, via runtime setters only (that is how the game drives
the effect):

1. passthrough    — strengths 0.0: image identical to baseline
2. radial smear   — blur 1.0 smears the quad along the radial axis
                    (bright inboard of the quad), NOT tangentially
3. center control — moving radial_blur_center onto the quad kills the
                    smear there (blur amount is proportional to the
                    distance from the center)
4. chroma fringe  — chromatic aberration displaces R outward and B
                    inward at the quad's radial edges

Skips on pipelines without the radial-blur API (pre-Session-E
pax3d_render, legacy pax_pbr, simplepbr family).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import scenes

QUAD_VALUE = 4.0       # HDR emissive value (bright but not clipping smear)
QUAD_HALF = 0.03       # world units; film_h=2 -> ~7.7 px at 512
QUAD_WORLD_X = 0.55    # off-center along +x


def channel_at(img, x, y, ch):
    x = max(0, min(img.get_x_size() - 1, int(x)))
    y = max(0, min(img.get_y_size() - 1, int(y)))
    return img.get_xel(x, y)[ch]


def band_channel_mean(img, x0, x1, cy, ch, rows=2):
    total, n = 0.0, 0
    for x in range(int(x0), int(x1) + 1):
        for dy in range(-rows, rows + 1):
            total += channel_at(img, x, cy + dy, ch)
            n += 1
    return total / max(n, 1)


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'ftl_blur')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')

    pipe = getattr(h.adapter, 'pipeline', None)
    if pipe is None or not hasattr(pipe, 'set_radial_blur'):
        h.report.skip('pipeline has no radial-blur API')

    h.set_ortho(film_h=2.0)
    quad = scenes.make_emissive_quad(h.base.render, h.use_330,
                                     QUAD_VALUE, QUAD_HALF)
    quad.set_x(QUAD_WORLD_X)

    cx, cy = h.win_w // 2, h.win_h // 2
    film_half_w = (2.0 * h.win_w / h.win_h) / 2.0
    qx = cx + int(QUAD_WORLD_X / film_half_w * (h.win_w / 2.0))
    qh_px = QUAD_HALF / 1.0 * (h.win_h / 2.0)
    in_px = qx - int(qh_px + 9)      # radially inboard of the quad
    tan_py = cy - int(qh_px + 9)     # tangentially offset (above)

    # --- Baseline (strengths default 0) ------------------------------
    h.step(4)
    base_img = h.capture()
    h.save_capture(base_img, 'baseline')
    base_core = common.avg_lum(base_img, qx, cy, half=2)
    base_in = common.avg_lum(base_img, in_px, cy, half=1)
    base_tan = common.avg_lum(base_img, qx, tan_py, half=1)
    h.report.check('quad_visible', base_core > 0.3,
                   f'core_lum={base_core:.3f}')
    h.report.check('baseline_dark_inboard', base_in < 0.05,
                   f'lum={base_in:.4f}')

    # --- 2. Radial smear ---------------------------------------------
    pipe.set_radial_blur(1.0)
    h.step(2)
    blur_img = h.capture()
    h.save_capture(blur_img, 'blur')
    blur_in = common.avg_lum(blur_img, in_px, cy, half=1)
    blur_tan = common.avg_lum(blur_img, qx, tan_py, half=1)
    h.report.check('smear_radial_inboard', blur_in > base_in + 0.05,
                   f'baseline={base_in:.4f} blurred={blur_in:.4f}')
    h.report.check('smear_not_tangential',
                   blur_tan < base_tan + 0.03,
                   f'baseline={base_tan:.4f} blurred={blur_tan:.4f}')

    # --- 3. Center control -------------------------------------------
    quad_u = qx / float(h.win_w)
    pipe.set_radial_blur_center(quad_u, 0.5)
    h.step(2)
    centered_img = h.capture()
    centered_in = common.avg_lum(centered_img, in_px, cy, half=1)
    h.report.check('center_moves_with_uniform',
                   centered_in < base_in + 0.03,
                   f'smear at old inboard point: {centered_in:.4f} '
                   f'(baseline {base_in:.4f})')
    pipe.set_radial_blur_center(0.5, 0.5)
    pipe.set_radial_blur(0.0)

    # --- 4. Chromatic fringe ------------------------------------------
    pipe.set_chromatic_aberration(1.0)
    h.step(2)
    ca_img = h.capture()
    h.save_capture(ca_img, 'chroma')
    # Outer radial edge: red image shifts outward -> r > b just outside
    outer0, outer1 = qx + qh_px, qx + qh_px + 3
    r_out = band_channel_mean(ca_img, outer0, outer1, cy, 0)
    b_out = band_channel_mean(ca_img, outer0, outer1, cy, 2)
    # Inner radial edge: blue image shifts inward -> b > r just inside
    inner0, inner1 = qx - qh_px - 3, qx - qh_px
    r_in = band_channel_mean(ca_img, inner0, inner1, cy, 0)
    b_in = band_channel_mean(ca_img, inner0, inner1, cy, 2)
    h.report.check('chroma_red_outward', r_out > b_out + 0.01,
                   f'outer band r={r_out:.4f} b={b_out:.4f}')
    h.report.check('chroma_blue_inward', b_in > r_in + 0.01,
                   f'inner band r={r_in:.4f} b={b_in:.4f}')
    pipe.set_chromatic_aberration(0.0)

    # --- 1. Passthrough (checked last so setters returned to 0) -------
    h.step(2)
    off_img = h.capture()
    max_diff = 0.0
    for sx in range(8, h.win_w - 8, max(h.win_w // 16, 8)):
        for sy in range(8, h.win_h - 8, max(h.win_h // 16, 8)):
            d = abs(common.lum_at(off_img, sx, sy)
                    - common.lum_at(base_img, sx, sy))
            max_diff = max(max_diff, d)
    h.report.check('passthrough_identical', max_diff < 0.02,
                   f'max_point_diff={max_diff:.4f}')

    h.report.finish()


if __name__ == '__main__':
    main()
