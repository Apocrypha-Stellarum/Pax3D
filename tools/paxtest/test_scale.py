"""paxtest: space-scale rendering defects (Phase R4 acceptance tests).

Reproduces the two scale problems the game hits with one camera and large
world coordinates. These checks are EXPECTED TO FAIL until R4 lands
(logarithmic depth + camera-relative rendering) — they are the mechanical
bug reports R4 is built against, exactly as test_bloom was for F3:

1. zfight_at_range — two surfaces 1.0 IEU apart at 2500 IEU from the
   camera, game-baseline perspective frustum (near 0.1, far 5000, 24-bit
   depth). Theoretical depth resolution at that range is ~1.9 IEU, so the
   pair cannot be resolved: the rear (green) surface bleeds through the
   front (red) one in quantization bands.
   zfight_near_control — the same rig at 50 IEU resolves trivially and
   must stay green forever (guards that log depth doesn't break the near
   field).

2. precision_off_origin — an identical unlit scene rendered at the world
   origin and at 1e6 / 1e7 IEU from it (camera moved with the scene, so
   the images should be pixel-identical). The camera is ROTATED (look_at)
   and the offsets are non-representable in float32: the view-matrix
   composition then multiplies the huge translation through the rotation
   basis and rounds — vertices displace. Axis-aligned identity-rotation
   rigs cancel exactly and do NOT reproduce the defect (verified).
   origin_control (origin vs origin) must always be identical.

Runs for 'none' (isolates the engine, no custom shaders in the pipeline)
and 'pax3d_render' (the real target). Other pipelines skip.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes

# Unlit flat-color card/mesh shader (pipeline-independent color identity)
_FRAG_RGB_120 = """#version 120
uniform vec3 u_rgb;
void main() {
    FRAG_OUT = vec4(u_rgb, 1.0);
}
"""

NEAR, FAR = 0.1, 5000.0          # sfb2 plan.py camera baseline
RANGE_FAR = 2500.0               # test distance (mid-frustum, in-game regime)
RANGE_NEAR = 50.0                # control distance
SEPARATION = 1.0                 # IEU between the two surfaces
# Off-origin translation distances — deliberately NOT representable in
# float32 (round offsets like exactly 1e6 cancel without error and hide
# the defect)
OFFSETS = [1234567.89, 12345678.9]
CAM_ARM = p3d.Vec3(5.3, -27.7, 6.1)   # camera offset from the subject


def make_color_card(parent, use_330, rgb, half, name):
    np = scenes._make_card(parent, half, half, name)
    np.set_shader(scenes.make_shader(_FRAG_RGB_120, use_330))
    np.set_shader_input('u_rgb', p3d.LVecBase3(*rgb))
    np.set_light_off(1)
    return np


def classify_fractions(img, cx, cy, half):
    """Fractions of red-dominant / green-dominant pixels in a box."""
    n = red = green = 0
    for dy in range(-half, half + 1, 2):
        for dx in range(-half, half + 1, 2):
            c = img.get_xel(cx + dx, cy + dy)
            n += 1
            if c[0] > 0.1 and c[0] > 2.0 * c[1]:
                red += 1
            elif c[1] > 0.1 and c[1] > 2.0 * c[0]:
                green += 1
    return red / n, green / n


def diff_fraction(img_a, img_b, threshold=0.1):
    """Fraction of pixels whose luminance differs by more than threshold."""
    w, h = img_a.get_x_size(), img_a.get_y_size()
    n = diff = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            n += 1
            if abs(common.lum_at(img_a, x, y)
                   - common.lum_at(img_b, x, y)) > threshold:
                diff += 1
    return diff / n


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'scale')
    if args.pipeline not in ('none', 'pax3d_render'):
        h.report.skip('scale defects are engine-level; '
                      'run under none + pax3d_render only')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    base = h.base

    # ------------------------------------------------------------------
    # 1. Depth precision: perspective camera, game near/far
    # ------------------------------------------------------------------
    lens = p3d.PerspectiveLens()
    lens.set_fov(40)
    lens.set_near_far(NEAR, FAR)
    base.cam.node().set_lens(lens)
    base.camera.set_pos(0, 0, 0)
    base.camera.set_hpr(0, 0, 0)

    cx, cy = h.win_w // 2, h.win_h // 2

    def zfight_rig(distance, tag):
        # Green (rear) attached FIRST, red (front) second: with the default
        # M_less depth test, a quantized depth TIE makes the later-drawn red
        # fragment lose — so any green inside the overlap means the buffer
        # could not order two surfaces SEPARATION apart. Both cards are
        # pitched so interpolated depth sweeps across quantization steps
        # (the classic banding pattern).
        root = base.render.attach_new_node(f'zfight_{tag}')
        scale = distance / RANGE_FAR
        green = make_color_card(root, h.use_330, (0, 1, 0),
                                500.0 * scale, 'rear_green')
        green.set_pos(0, distance + SEPARATION, 0)
        green.set_p(30)
        red = make_color_card(root, h.use_330, (1, 0, 0),
                              400.0 * scale, 'front_red')
        red.set_pos(0, distance, 0)
        red.set_p(30)

        h.step(3)
        img = h.capture()
        h.save_capture(img, tag)
        red_f, green_f = classify_fractions(img, cx, cy, half=60)
        root.remove_node()
        return red_f, green_f

    red_f, green_f = zfight_rig(RANGE_FAR, 'zfight_at_range')
    h.report.check(
        'zfight_at_range', red_f > 0.5 and green_f < 0.02,
        f'overlap at {RANGE_FAR:.0f} IEU (sep {SEPARATION}): '
        f'red={red_f:.2f} green={green_f:.2f} '
        f'(R4 acceptance — expected FAIL until log depth)')

    red_f, green_f = zfight_rig(RANGE_NEAR, 'zfight_near_control')
    h.report.check(
        'zfight_near_control', red_f > 0.5 and green_f < 0.02,
        f'overlap at {RANGE_NEAR:.0f} IEU: red={red_f:.2f} '
        f'green={green_f:.2f} (must stay green forever)')

    # ------------------------------------------------------------------
    # 2. Transform precision far from the origin
    # ------------------------------------------------------------------
    h.set_ortho(film_h=6.0)

    sphere = scenes.make_uv_sphere(48, 'game')
    sphere.set_shader(scenes.make_shader(_FRAG_RGB_120, h.use_330))
    sphere.set_shader_input('u_rgb', p3d.LVecBase3(0.8, 0.8, 0.8))
    sphere.set_light_off(1)
    sphere.set_scale(2)
    sphere.set_hpr(33.3, 12.2, 5.5)   # rotated model, like a real ship
    sphere.reparent_to(base.render)

    def capture_at(offset_x, tag):
        subject = p3d.Vec3(offset_x, 0, 0)
        sphere.set_pos(subject)
        base.camera.set_pos(subject + CAM_ARM)
        base.camera.look_at(subject)   # rotated view — the real-game case
        h.step(3)
        img = h.capture()
        h.save_capture(img, tag)
        return img

    img_origin = capture_at(0.0, 'precision_origin')
    img_origin2 = capture_at(0.0, 'precision_origin_repeat')
    control = diff_fraction(img_origin, img_origin2)
    h.report.check('origin_control', control < 0.001,
                   f'origin vs origin diff_fraction={control:.5f} '
                   f'(determinism guard)')

    for off in OFFSETS:
        img_off = capture_at(off, f'precision_{off:.0e}')
        frac = diff_fraction(img_origin, img_off)
        h.report.check(
            f'precision_off_origin:{off:.0e}', frac < 0.001,
            f'origin vs {off:.0e} IEU diff_fraction={frac:.5f} '
            f'(R4 acceptance — expected FAIL until camera-relative)')

    h.report.finish()


if __name__ == '__main__':
    main()
