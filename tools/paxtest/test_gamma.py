"""paxtest: color-transfer (gamma / tonemap) correctness.

Renders bars of known scene-linear values through the pipeline and compares
the framebuffer output against the analytically expected tonemap curve.
Detects double-gamma, missing gamma, and wrong-operator bugs mechanically
(failure F2 in PAX3D_MASTER_PLAN.md).

Also reports (informational) whether 8-bit texture values are sRGB-decoded
on sampling or passed through raw — the input half of the color contract.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import scenes

NUM_BARS = 16
ROW_MAX_BOTTOM = 1.0   # LDR sweep
ROW_MAX_TOP = 4.0      # HDR sweep (exercises the tonemap shoulder)


def srgb_encode(v):
    return common._clamp01(v) ** (1.0 / 2.2)


def srgb_decode(v):
    return common._clamp01(v) ** 2.2


def bar_values(row_max):
    return [(i / (NUM_BARS - 1)) * row_max for i in range(NUM_BARS)]


def measure_bars(harness, img, film_w, film_h):
    """Return ([ldr measurements], [hdr measurements]) at bar centers."""
    w, h = harness.win_w, harness.win_h

    def to_px(xw, yw):
        px = (xw / (film_w / 2.0) * 0.5 + 0.5) * (w - 1)
        py = (1.0 - (yw / (film_h / 2.0) * 0.5 + 0.5)) * (h - 1)
        return int(px), int(py)

    rows = []
    for yw in (-0.5, 0.5):  # bottom row (LDR), top row (HDR)
        vals = []
        for i in range(NUM_BARS):
            u = (i + 0.5) / NUM_BARS
            xw = -1.0 + 2.0 * u
            px, py = to_px(xw, yw)
            vals.append(common.avg_lum(img, px, py, half=3))
        rows.append(vals)
    return rows[0], rows[1]


def classify(op, inputs, measured, exposure_ev):
    """Best-fit hypothesis for a failed transfer curve."""
    curve = common.CURVES[op]

    def rms(fn):
        errs = [(fn(v) - m) ** 2 for v, m in zip(inputs, measured)]
        return math.sqrt(sum(errs) / len(errs))

    scale = 2.0 ** exposure_ev
    hypotheses = {
        'expected': lambda v: curve(v * scale),
        'extra_srgb_gamma (double-gamma)':
            lambda v: srgb_encode(curve(v * scale)),
        'gamma_removed (linear out)':
            lambda v: srgb_decode(curve(v * scale)),
        'no_tonemap (raw clamp)': lambda v: common._clamp01(v * scale),
    }
    scored = sorted((rms(fn), name) for name, fn in hypotheses.items())
    return scored[0], scored


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'gamma')
    h.init_pipeline(exposure=0.0, tonemap=h.adapter.operators[0])
    film_w, film_h = h.set_ortho(film_h=2.0)

    bars = scenes.make_bar_card(h.base.render, h.use_330, NUM_BARS,
                                ROW_MAX_BOTTOM, ROW_MAX_TOP)
    ldr_in = bar_values(ROW_MAX_BOTTOM)
    hdr_in = bar_values(ROW_MAX_TOP)

    tolerance = 0.03

    for op in h.adapter.operators:
        h.adapter.set_tonemap(op)
        h.step(4)
        img = h.capture()
        h.save_capture(img, f'ramp_{op}')

        ldr_meas, hdr_meas = measure_bars(h, img, film_w, film_h)
        inputs = ldr_in + hdr_in
        measured = ldr_meas + hdr_meas
        expected = [common.expected_output(op, v, 0.0) for v in inputs]
        errs = [abs(e - m) for e, m in zip(expected, measured)]
        max_err = max(errs)
        worst = errs.index(max_err)

        ok = max_err < tolerance
        detail = (f'max_err={max_err:.3f} at in={inputs[worst]:.3f} '
                  f'(expected {expected[worst]:.3f}, got {measured[worst]:.3f})')
        if not ok:
            (best_rms, best_name), _ = classify(op, inputs, measured, 0.0)
            detail += f' | best-fit: {best_name} (rms={best_rms:.3f})'
        h.report.check(f'transfer:{op}', ok, detail)

    # Exposure check (pipelines only — 'none' has no exposure control)
    if args.pipeline != 'none':
        op = h.adapter.operators[-1]
        h.adapter.set_tonemap(op)
        try:
            h.adapter.set_exposure(1.0)
            h.step(4)
            img = h.capture()
            ldr_meas, _ = measure_bars(h, img, film_w, film_h)
            expected = [common.expected_output(op, v, 1.0) for v in ldr_in]
            max_err = max(abs(e - m) for e, m in zip(expected, ldr_meas))
            h.report.check(f'exposure_ev1:{op}', max_err < 0.035,
                           f'max_err={max_err:.3f}')
            h.adapter.set_exposure(0.0)
        except Exception as exc:  # runtime exposure not supported everywhere
            h.report.info('exposure_ev1', f'not testable: {exc}')

    # Texture linearization (informational): is an 8-bit texture value
    # sRGB-decoded when sampled, or passed through raw?
    bars.hide()
    tex_val = 128 / 255.0
    texcard = scenes.make_texture_card(h.base.render, h.use_330,
                                       tex_value_8bit=128)
    op = h.adapter.operators[0]
    h.adapter.set_tonemap(op)
    h.step(4)
    img = h.capture()
    center = common.avg_lum(img, h.win_w // 2, h.win_h // 2, half=3)
    out_if_raw = common.expected_output(op, tex_val, 0.0)
    out_if_decoded = common.expected_output(op, srgb_decode(tex_val), 0.0)
    d_raw = abs(center - out_if_raw)
    d_dec = abs(center - out_if_decoded)
    verdict = 'RAW (not linearized)' if d_raw < d_dec else 'sRGB-DECODED'
    h.report.info(
        'texture_srgb_decode',
        f'{verdict}: measured={center:.3f}, raw-pred={out_if_raw:.3f}, '
        f'decoded-pred={out_if_decoded:.3f}')
    texcard.remove_node()

    h.report.finish()


if __name__ == '__main__':
    main()
