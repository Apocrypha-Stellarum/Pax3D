"""paxtest: directional lighting correctness per mesh type.

For each mesh (game-winding sphere, reversed-winding sphere, optional GLTF
ship) and each light direction, verifies that the lit side of the object
faces the light. Uses the pipeline's native sun mechanism:

  - pax_pbr:            pipeline.update_sun() custom uniforms
  - simplepbr family:   a real DirectionalLight (node at identity HPR,
                        set_direction(travel) — the unambiguous API)
  - none:               a real DirectionalLight via fixed-function

For pax_pbr, additionally documents whether a real DirectionalLight is
consumed at all (failure F1 in PAX3D_MASTER_PLAN.md — expected: ignored).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes

DEFAULT_GLTF = 'C:/python/sfb2/assets/models/frigate_storm_grey_v4.glb'

# toward_sun vector -> which half of the screen should be brighter.
# Camera at (0,-10,0) looking +Y; screen right = +X, screen up = +Z.
# PNM y grows DOWNWARD, so half_y=-1 means upper half of the image.
CARDINALS = [
    ('east',  (1, 0, 0),  dict(half_x=1),  dict(half_x=-1)),
    ('west',  (-1, 0, 0), dict(half_x=-1), dict(half_x=1)),
    ('up',    (0, 0, 1),  dict(half_y=-1), dict(half_y=1)),
    ('down',  (0, 0, -1), dict(half_y=1),  dict(half_y=-1)),
]
SUN_COLOR = (3.0, 3.0, 3.0)


class SunRig:
    """Drives the sun through whichever mechanism the pipeline uses."""

    AMBIENT = 0.02

    def __init__(self, harness):
        self.h = harness
        self.adapter = harness.adapter
        self.dlight_np = None

        # Always attach a small AmbientLight (mirrors the game's setup).
        # Critical: with NO lights attached, Panda3D reports
        # p3d_LightModel.ambient as pure white, which floods PBR shaders
        # with a flat ambient term that swamps any directional signal.
        alight = p3d.AmbientLight('paxtest_ambient')
        alight.set_color(p3d.LColor(self.AMBIENT, self.AMBIENT,
                                    self.AMBIENT, 1))
        self.ambient_np = harness.base.render.attach_new_node(alight)
        harness.base.render.set_light(self.ambient_np)

        if self.adapter.consumes_directional_light:
            dlight = p3d.DirectionalLight('paxtest_sun')
            dlight.set_color(p3d.LColor(*SUN_COLOR, 1))
            self.dlight_np = harness.base.render.attach_new_node(dlight)
            harness.base.render.set_light(self.dlight_np)

    def set_toward_sun(self, toward):
        toward = p3d.Vec3(*toward)
        toward.normalize()
        if self.adapter.supports_sun_uniforms:
            self.adapter.update_sun(toward, SUN_COLOR)
        if self.dlight_np is not None:
            travel = -toward  # direction the photons travel
            self.dlight_np.node().set_direction(travel)


def measure_halves(h, img, radius, lit_kw, dark_kw):
    cx, cy = h.win_w / 2.0, h.win_h / 2.0
    lit = common.mean_lum_disc(img, cx, cy, radius, exclude_band=8, **lit_kw)
    dark = common.mean_lum_disc(img, cx, cy, radius, exclude_band=8, **dark_kw)
    return lit, dark


def run_mesh(h, rig, mesh_np, mesh_name, radius_px, informational=False):
    """Cardinal + front/back checks for one mesh.

    informational=True turns pass/fail into INFO records — used for the
    reversed-winding probe sphere, whose inverted/culled behaviour is the
    documented winding characterization (F8), not a pipeline defect.
    """
    def record(name, ok, detail):
        if informational:
            h.report.info(name, ('ok — ' if ok else 'ANOMALY — ') + detail)
        else:
            h.report.check(name, ok, detail)

    # Visibility precheck: sun toward the camera -> visible face fully lit
    rig.set_toward_sun((0, -1, 0))
    h.step(3)
    img = h.capture()
    cx, cy = h.win_w / 2.0, h.win_h / 2.0
    full_lum = common.mean_lum_disc(img, cx, cy, radius_px)
    visible = full_lum > 0.02
    record(f'{mesh_name}:visible', visible,
           f'mean_lum={full_lum:.3f} with sun behind camera'
           + ('' if visible else ' — mesh dark/culled, skipping'))
    h.save_capture(img, f'{mesh_name}_frontlit')
    if not visible:
        return

    # Sun behind the object -> visible face dark
    rig.set_toward_sun((0, 1, 0))
    h.step(3)
    img = h.capture()
    back_lum = common.mean_lum_disc(img, cx, cy, radius_px)
    ratio = full_lum / max(back_lum, 1e-4)
    record(f'{mesh_name}:front_vs_back', ratio > 4.0,
           f'frontlit={full_lum:.3f} backlit={back_lum:.3f} '
           f'ratio={ratio:.1f}'
           + (' — INVERTED' if ratio < 0.5 else ''))

    # Cardinals: correct hemisphere lit
    for name, toward, lit_kw, dark_kw in CARDINALS:
        rig.set_toward_sun(toward)
        h.step(3)
        img = h.capture()
        lit, dark = measure_halves(h, img, radius_px, lit_kw, dark_kw)
        ratio = lit / max(dark, 1e-4)
        ok = lit > dark and ratio > 2.0
        record(f'{mesh_name}:{name}', ok,
               f'lit_half={lit:.3f} dark_half={dark:.3f} '
               f'ratio={ratio:.1f}'
               + ('' if lit >= dark else ' — WRONG SIDE LIT'))
        if name == 'east':
            h.save_capture(img, f'{mesh_name}_east')


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--gltf', default=DEFAULT_GLTF,
                        help='GLTF model to test (blank to skip)')
    args = parser.parse_args()

    h = common.Harness(args, 'lighting')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    h.set_ortho(film_h=4.0)  # 1 world unit = win_h/4 px
    radius_px = 0.7 * (h.win_h / 4.0)  # sample disc inside the r=1 sphere

    rig = SunRig(h)

    meshes = []
    for winding in ('game', 'reversed'):
        sphere = scenes.make_uv_sphere(48, winding)
        scenes.apply_flat_pbr_surface(sphere)
        sphere.reparent_to(h.base.render)
        sphere.hide()
        meshes.append((f'sphere_{winding}', sphere, radius_px))

    if args.gltf and os.path.exists(args.gltf):
        try:
            ship = h.base.loader.load_model(
                p3d.Filename.from_os_specific(args.gltf))
            # Normalize: center at origin, fit inside ~1.6 world units
            bounds = ship.get_tight_bounds()
            if bounds:
                lo, hi = bounds
                center = (lo + hi) * 0.5
                size = max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
                ship.set_scale(1.6 / max(size, 1e-6))
                ship.set_pos(-center * (1.6 / max(size, 1e-6)))
            ship.reparent_to(h.base.render)
            ship.hide()
            meshes.append(('gltf_ship', ship, radius_px))
        except Exception as exc:
            h.report.info('gltf_ship', f'load failed, skipping: {exc}')
    else:
        h.report.info('gltf_ship', 'no model available, skipping')

    for mesh_name, mesh_np, r in meshes:
        mesh_np.show()
        if mesh_name == 'gltf_ship':
            # Irregular silhouette: only the coarse front/back check is
            # meaningful. It answers: does this mesh receive the sun at all?
            rig.set_toward_sun((0, -1, 0))
            h.step(3)
            img = h.capture()
            cx, cy = h.win_w / 2.0, h.win_h / 2.0
            front = common.mean_lum_disc(img, cx, cy, r)
            h.save_capture(img, 'gltf_ship_frontlit')
            rig.set_toward_sun((0, 1, 0))
            h.step(3)
            img = h.capture()
            back = common.mean_lum_disc(img, cx, cy, r)
            ratio = front / max(back, 1e-4)
            h.report.check('gltf_ship:receives_directional',
                           front > 0.02 and ratio > 2.0,
                           f'frontlit={front:.3f} backlit={back:.3f} '
                           f'ratio={ratio:.1f}')
        else:
            run_mesh(h, rig, mesh_np, mesh_name, r,
                     informational=(mesh_name == 'sphere_reversed'))
        mesh_np.hide()

    # F1 documentation for pax_pbr: is a real DirectionalLight consumed?
    if (h.adapter.supports_sun_uniforms
            and not h.adapter.consumes_directional_light):
        sphere = meshes[0][1]
        sphere.show()
        cx, cy = h.win_w / 2.0, h.win_h / 2.0
        h.adapter.update_sun((0, -1, 0), (0.0, 0.0, 0.0))  # kill uniform sun
        h.step(3)
        baseline = common.mean_lum_disc(h.capture(), cx, cy, radius_px)
        dlight = p3d.DirectionalLight('paxtest_real_dlight')
        dlight.set_color(p3d.LColor(*SUN_COLOR, 1))
        dlight_np = h.base.render.attach_new_node(dlight)
        dlight.set_direction(p3d.Vec3(0, 1, 0))  # photons toward the mesh
        h.base.render.set_light(dlight_np)
        h.step(3)
        lum = common.mean_lum_disc(h.capture(), cx, cy, radius_px)
        consumed = lum > baseline + 0.05
        h.report.info(
            'real_directional_light',
            ('CONSUMED' if consumed else 'IGNORED')
            + f' by this pipeline (ambient-only={baseline:.3f}, '
            f'with DirectionalLight={lum:.3f})')
        h.base.render.clear_light(dlight_np)
        sphere.hide()

    h.report.finish()


if __name__ == '__main__':
    main()
