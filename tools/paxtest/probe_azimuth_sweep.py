"""Azimuth-asymmetry probe (openworld P0 addendum, 2026-07-17 afternoon).

Their claim: lit-pass shadows die inside a western low-sun cone
(alt <= ~40 deg, az ~240) while the eastern mirror at the same altitude
is perfect — a depth error scaling like 1/tan(alt) with an azimuth-sign
asymmetry. Our angled tests only ever used sun-from-+X.

This probe: glTF box over glTF textured ground (the test_shadows_gltf
scene), sun swept over 4 azimuths (+X, +Y, -X, -Y) x altitudes
(34, 45, 60), measuring the box-shadow darkening ratio at the
analytically expected shadow position each time.

RESULT AT TOY SCALE (2026-07-17, Session G postscript): all 12
directions cast perfect shadows (ratio 0.11-0.12), identical on stock
1.10.16 and Pax3D 1.11.0 — the asymmetry does NOT reproduce at extent
12/60 with a static sun at the origin. Next step (Session H): re-run at
openworld scale (set_shadow_extent(450, 600), 4096 map, scene spanning
hundreds of units, off-origin camera, shadow_bias_world=0.18) and with
the EXACT sun vectors produced by openworld's game/daynight.py alt/az
mapping — their OW_SUN_OVERRIDE evidence cannot distinguish an engine
defect from a defect in their alt/az->vector conversion; this probe can.
Promote the working matrix into test_shadow_quality when done.
"""
import math
import os
import sys

PAXTEST = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PAXTEST)

import argparse
import panda3d.core as p3d
import common
import test_shadows_gltf as tsg


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args(['--pipeline', 'pax3d_render'])
    h = common.Harness(args, 'azprobe')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode='directional', shadows=True,
                    extra_pipeline_kwargs={'shadow_map_size': 1024})
    pipeline = h.adapter.pipeline
    pipeline.set_shadow_extent(12, 60)
    base = h.base

    import gltf as gltf_mod
    if hasattr(gltf_mod, 'patch_loader'):
        gltf_mod.patch_loader(base.loader)

    alight = p3d.AmbientLight('amb')
    alight.set_color(p3d.LColor(0.02, 0.02, 0.02, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    os.makedirs(common.OUTPUT_DIR, exist_ok=True)
    tex_path = os.path.join(common.OUTPUT_DIR, tsg.GLTF_TEX_NAME)
    gltf_path = os.path.join(common.OUTPUT_DIR, tsg.GLTF_SCENE_NAME)
    tsg._write_white_png(tex_path)
    tsg._build_gltf_scene(gltf_path, tsg.GLTF_TEX_NAME)
    scene_np = base.loader.load_model(p3d.Filename.from_os_specific(gltf_path))
    scene_np.reparent_to(base.render)
    box_np = scene_np.find('**/box')
    box_np.set_pos(base.render, 0, 0, 3.0)

    base.camera.set_pos(0, 0, 30)
    base.camera.set_hpr(0, -90, 0)
    film = 16.0
    h.set_ortho(film_h=film)
    scale = h.win_h / film

    def to_px(wx, wy):
        return (int(h.win_w / 2 + wx * scale),
                int(h.win_h / 2 - wy * scale))

    print(f'engine: {p3d.PandaSystem.get_version_string()}')
    print(f'{"alt":>4} {"az(dir)":>8} | {"off":>6} {"on":>6} {"ratio":>6} | verdict')

    for alt in (34, 45, 60):
        for az_name, (dx, dy) in [('+X', (1, 0)), ('+Y', (0, 1)),
                                  ('-X', (-1, 0)), ('-Y', (0, -1))]:
            el = math.radians(alt)
            toward = (math.cos(el) * dx, math.cos(el) * dy, math.sin(el))
            h.adapter.update_sun(toward, (3, 3, 3))
            # box center (0,0,3): its shadow center lands at
            # -horizontal_dir * 3/tan(alt)
            off = 3.0 / math.tan(el)
            spx = to_px(-dx * off, -dy * off)

            h.step(4)
            img = h.capture()
            on = common.avg_lum(img, spx[0], spx[1], half=3)
            pipeline.set_enable_shadows(False)
            h.step(4)
            img2 = h.capture()
            offl = common.avg_lum(img2, spx[0], spx[1], half=3)
            pipeline.set_enable_shadows(True)

            ratio = on / max(offl, 1e-4)
            verdict = 'SHADOW' if ratio < 0.5 else '*** NO SHADOW ***'
            print(f'{alt:>4} {az_name:>8} | {offl:6.3f} {on:6.3f} '
                  f'{ratio:6.2f} | {verdict}')


if __name__ == '__main__':
    main()
