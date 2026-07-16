"""paxtest: auxiliary display-region survival across pipeline rebuilds.

Reproduces failure F4 ("toggling bloom kills the skybox"): an auxiliary
background camera — attached the way the game's sky_camera.py does it, by
finding the FilterManager buffer once at init — dies when the pipeline
rebuilds its buffers (bloom toggle).

For pipelines with a camera-registration API (pax3d_render), the camera is
attached through pipeline.register_scene_camera() and must survive.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes

RED_X = -0.6      # world x of the red background card (screen-left)
RED_HALF = 0.15


def make_background_rig(h):
    """A separate scene root with a red card, rendered by its own camera."""
    sky_root = p3d.NodePath('paxtest_sky_root')

    cm = p3d.CardMaker('paxtest_red_card')
    cm.set_frame(RED_X - RED_HALF, RED_X + RED_HALF, -RED_HALF, RED_HALF)
    card = sky_root.attach_new_node(cm.generate())
    card.set_color(1, 0, 0, 1)
    card.set_light_off(1)
    card.set_two_sided(True)

    lens = p3d.OrthographicLens()
    lens.set_film_size(2.0 * h.win_w / h.win_h, 2.0)
    lens.set_near_far(-50, 50)
    cam_node = p3d.Camera('paxtest_sky_camera')
    cam_node.set_lens(lens)
    cam_node.set_scene(sky_root)
    cam_np = sky_root.attach_new_node(cam_node)
    cam_np.set_pos(0, -10, 0)
    return sky_root, cam_np


def attach_manually(base, cam_np):
    """The game's sky_camera.py pattern: find the buffer once, make a DR."""
    target_cam = base.cam
    ge = base.graphics_engine
    for i in range(ge.get_num_windows()):
        output = ge.get_window(i)
        for j in range(output.get_num_display_regions()):
            dr = output.get_display_region(j)
            if dr.get_camera() == target_cam:
                sky_dr = output.make_display_region()
                sky_dr.set_sort(-100)
                sky_dr.set_clear_color_active(True)
                sky_dr.set_clear_color(p3d.LColor(0, 0, 0, 1))
                sky_dr.set_clear_depth_active(True)
                sky_dr.set_camera(cam_np)
                dr.set_clear_color_active(False)
                dr.set_clear_depth_active(True)
                return sky_dr
    raise RuntimeError('main camera display region not found')


def red_card_visible(h, img):
    """Is the red card present in the final output?"""
    fw = 2.0 * h.win_w / h.win_h
    px = int((RED_X / (fw / 2.0) * 0.5 + 0.5) * (h.win_w - 1))
    py = h.win_h // 2
    total_r = total_g = 0.0
    n = 0
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            c = img.get_xel(min(max(px + dx, 0), h.win_w - 1),
                            min(max(py + dy, 0), h.win_h - 1))
            total_r += c[0]
            total_g += c[1]
            n += 1
    r, g = total_r / n, total_g / n
    return (r > 0.3 and r > g + 0.15), r


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'rebuild')
    if not h.adapter.supports_bloom:
        h.report.skip('pipeline has no bloom toggle — nothing rebuilds')

    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson', bloom=None)
    h.set_ortho(film_h=2.0)

    # Something in the main scene so the main region isn't empty
    scenes.make_emissive_quad(h.base.render, h.use_330, 2.0, 0.08)

    # The FilterManager buffer only appears in the GraphicsEngine window
    # list after a frame renders (in-game, sky setup happens much later).
    h.step(2)

    sky_root, cam_np = make_background_rig(h)
    if h.adapter.supports_camera_registration:
        h.adapter.pipeline.register_scene_camera(cam_np, sort=-100)
        mode = 'register_scene_camera API'
    else:
        attach_manually(h.base, cam_np)
        mode = 'manual buffer-discovery (sky_camera.py pattern)'
    h.report.info('attach_mode', mode)

    h.step(4)
    img = h.capture()
    h.save_capture(img, 'before_toggle')
    visible, r = red_card_visible(h, img)
    h.report.check('aux_visible_initial', visible, f'red={r:.2f}')

    if visible:
        h.adapter.set_bloom_enabled(True)   # triggers rebuild
        h.step(4)
        img = h.capture()
        h.save_capture(img, 'after_bloom_on')
        visible, r = red_card_visible(h, img)
        h.report.check('aux_survives_bloom_on', visible, f'red={r:.2f}')

        h.adapter.set_bloom_enabled(False)  # second rebuild
        h.step(4)
        img = h.capture()
        h.save_capture(img, 'after_bloom_off')
        visible, r = red_card_visible(h, img)
        h.report.check('aux_survives_bloom_off', visible, f'red={r:.2f}')

    h.report.finish()


if __name__ == '__main__':
    main()
