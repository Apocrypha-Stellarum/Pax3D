"""paxtest: bloom quality on an isolated HDR point source.

Black scene + one small bright emissive quad, bloom enabled. Checks that
a glow halo exists and decays smoothly (failure F3 in PAX3D_MASTER_PLAN.md:
"blocky artifacts"). Run at both 512x512 (divides evenly through the 1/32
mip chain) and a game-like size such as 960x540 (does not divide evenly) —
comparing the two localizes resolution-truncation bugs.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import scenes

QUAD_VALUE = 1000.0    # HDR emissive value (firefly clamp in extract is 25000)
QUAD_HALF = 0.03       # world units; film_h=2 -> ~15 px at 512


def profile(img, cx, cy, dx, dy, r_start, r_end):
    """Luminance along a ray from (cx,cy), 1px steps."""
    out = []
    for r in range(int(r_start), int(r_end)):
        x = cx + dx * r
        y = cy + dy * r
        out.append(common.lum_at(img, x, y))
    return out


def smoothness_stats(vals):
    """Max adjacent-step and count of outward brightness jumps."""
    max_step = 0.0
    max_step_at = 0
    inversions = 0
    for i in range(len(vals) - 1):
        step = abs(vals[i + 1] - vals[i])
        if step > max_step:
            max_step = step
            max_step_at = i
        if vals[i + 1] > vals[i] + 0.015:  # brightness must decay outward
            inversions += 1
    return max_step, max_step_at, inversions


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--quad-value', type=float, default=QUAD_VALUE)
    args = parser.parse_args()

    h = common.Harness(args, 'bloom')
    if not h.adapter.supports_bloom:
        h.report.skip('pipeline has no bloom support')

    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    bloom={'strength': 1.0, 'intensity': 1.0, 'levels': 5})
    h.set_ortho(film_h=2.0)

    scenes.make_emissive_quad(h.base.render, h.use_330,
                              args.quad_value, QUAD_HALF)
    h.step(6)
    img = h.capture()
    h.save_capture(img, f'halo_{h.win_w}x{h.win_h}')

    cx, cy = h.win_w // 2, h.win_h // 2
    qh_px = QUAD_HALF * (h.win_h / 2.0)   # quad half-extent in pixels

    # 1. The source itself is visible
    core = common.avg_lum(img, cx, cy, half=2)
    h.report.check('core_visible', core > 0.05, f'core_lum={core:.3f}')

    # 2. A halo exists outside the quad
    r_halo = qh_px * 3
    halo_samples = [
        common.avg_lum(img, cx + r_halo, cy, half=1),
        common.avg_lum(img, cx - r_halo, cy, half=1),
        common.avg_lum(img, cx, cy + r_halo, half=1),
        common.avg_lum(img, cx, cy - r_halo, half=1),
    ]
    halo_mean = sum(halo_samples) / 4
    h.report.check('halo_present', halo_mean > 0.008,
                   f'mean_lum at r={r_halo:.0f}px: {halo_mean:.4f}')

    # 3. Halo decays smoothly (blockiness detector)
    r_start = qh_px + 6
    r_end = min(h.win_w, h.win_h) // 2 - 4
    diag = 1.0 / math.sqrt(2.0)
    for ray_name, dx, dy in [('+x', 1, 0), ('-x', -1, 0),
                             ('diag', diag, diag)]:
        vals = profile(img, cx, cy, dx, dy, r_start, r_end)
        max_step, at, inversions = smoothness_stats(vals)
        ok = max_step < 0.04 and inversions <= 2
        h.report.check(
            f'halo_smooth:{ray_name}', ok,
            f'max_adjacent_step={max_step:.3f} at r={r_start + at:.0f}px, '
            f'outward_jumps={inversions}')

    # 4. Rough radial symmetry (informational)
    lr_delta = abs(halo_samples[0] - halo_samples[1])
    ud_delta = abs(halo_samples[2] - halo_samples[3])
    h.report.info('halo_symmetry',
                  f'left/right delta={lr_delta:.4f}, '
                  f'up/down delta={ud_delta:.4f}')

    h.report.finish()


if __name__ == '__main__':
    main()
