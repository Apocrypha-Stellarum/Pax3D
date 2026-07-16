"""paxtest: sun shadow mapping via the real DirectionalLight (R2.4).

Occluder sphere directly on the sun ray above a larger sphere: the occluded
pole region must darken to ambient when shadows are on, restore when toggled
off, and darken again when re-enabled (exercises the runtime recompile path,
which once wiped all shader inputs — a bug this test now guards).

Only meaningful for pipelines with sun_light_mode='directional'
(pax3d_render); others skip.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'shadows')
    if not getattr(h.adapter, 'supports_sun_modes', False):
        h.report.skip('pipeline has no directional sun mode')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode='directional', shadows=True)
    pipeline = h.adapter.pipeline
    pipeline.set_shadow_extent(12, 60)

    h.set_ortho(film_h=6.0)  # 1 world unit = win_h/6 px
    base = h.base

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(0.02, 0.02, 0.02, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    ground = scenes.make_uv_sphere(48, 'game')
    scenes.apply_flat_pbr_surface(ground)
    ground.set_scale(2)
    ground.reparent_to(base.render)

    occluder = scenes.make_uv_sphere(24, 'game')
    scenes.apply_flat_pbr_surface(occluder)
    occluder.set_scale(1.0)
    occluder.set_pos(0, 0, 4)   # directly on the sun ray
    occluder.reparent_to(base.render)

    h.adapter.update_sun((0, 0, 1), (3, 3, 3))  # sun overhead

    # Sample point: z ~ 1.85 on the r=2 sphere — inside the shadow column
    px = h.win_w // 2
    py = int(h.win_h * (0.5 - 1.85 / 6.0))

    def pole_lum(tag):
        h.step(4)
        img = h.capture()
        h.save_capture(img, tag)
        return common.avg_lum(img, px, py, half=4)

    shadowed = pole_lum('on')
    pipeline.set_enable_shadows(False)
    unshadowed = pole_lum('off')
    pipeline.set_enable_shadows(True)
    reshadowed = pole_lum('on_again')

    h.report.check('unshadowed_bright', unshadowed > 0.4,
                   f'lum={unshadowed:.3f} with shadows off')
    ratio = unshadowed / max(shadowed, 1e-4)
    h.report.check('shadow_darkens', shadowed < 0.5 * unshadowed,
                   f'shadowed={shadowed:.3f} unshadowed={unshadowed:.3f} '
                   f'ratio={ratio:.1f}')
    h.report.check('shadow_toggle_returns', reshadowed < 0.5 * unshadowed,
                   f'reshadowed={reshadowed:.3f} (runtime recompile path)')

    h.report.finish()


if __name__ == '__main__':
    main()
