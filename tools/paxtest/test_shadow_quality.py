"""paxtest: shadow quality + configuration hardening (Session E).

Everything the openworld build hit, measured mechanically, top-down over a
ground plane so an ANGLED sun's shadow positions are analytic:

  * angled sun (30 deg elevation) — shadow lands exactly where projected
    geometry says (the old zenith-only coverage let this class hide);
  * the bias trap — the legacy normalized bias (world offset = bias x
    extent depth) ERASES a low caster's shadow at open-world extents;
    documented as a measured record, like test_scale does for z-fights;
  * shadow_bias_world — the world-unit bias restores the shadow and stays
    physically constant across extent changes;
  * 3x3 PCF (shadow_filter_size) — edge transition measurably widens,
    interior/lit luminance unchanged;
  * exclude_from_shadows() — the blessed no-cast API: node stops casting
    but stays visible to the main camera.

Geometry: ground card at z=0; occluder card 2x2 at z=1.2. Sun toward
(+cos30, 0, +sin30): every caster point (x,y,1.2) shadows (x-2.078, y).
The occluder never overlaps its own shadow on screen (top view), so all
samples are clean. Light-ray depth gap caster->receiver = 2.4 world units:
bias 0.005x600 = 3.0 erases it; 0.2 world units keeps it.

Only meaningful for pipelines with a directional sun mode (pax3d_render).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common
import scenes


ELEV = math.radians(30)
SUN = (math.cos(ELEV), 0.0, math.sin(ELEV))
OCC_H = 1.2
DISP = OCC_H * SUN[0] / SUN[2]          # 2.078 toward -x
SHADOW_C = (-DISP, 0.0)                 # shadow center of the occluder
MIRROR_C = (+DISP, 0.0)                 # same distance, sun side: lit
EDGE_X = -1.0 - DISP                    # shadow's -x edge (from card x=-1)


def make_flat_card(parent, half, name, z=0.0, rgb=(0.8, 0.8, 0.8)):
    cm = p3d.CardMaker(name)
    cm.set_frame(-half, half, -half, half)
    np = parent.attach_new_node(cm.generate())
    np.set_p(-90)                        # XZ card -> XY plane, faces +z
    np.set_z(z)
    np.set_two_sided(True)
    scenes.apply_flat_pbr_surface(np, rgb=rgb)
    return np


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'shadow_quality')
    if not getattr(h.adapter, 'supports_sun_modes', False):
        h.report.skip('pipeline has no directional sun mode')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode='directional', shadows=True,
                    extra_pipeline_kwargs={'shadow_map_size': 1024,
                                           'shadow_caster_mask': 21})
    pipeline = h.adapter.pipeline
    base = h.base

    alight = p3d.AmbientLight('paxtest_ambient')
    alight.set_color(p3d.LColor(0.02, 0.02, 0.02, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    ground = make_flat_card(base.render, 30, 'ground', z=0.0)
    occluder = make_flat_card(base.render, 1, 'occluder', z=OCC_H,
                              rgb=(0.9, 0.15, 0.15))   # red: visibility check

    # Top-down camera: world x -> +px, world y -> -py, both * scale
    base.camera.set_pos(0, 0, 30)
    base.camera.set_hpr(0, -90, 0)
    film_h = 10.0
    h.set_ortho(film_h=film_h)
    scale = h.win_h / film_h

    def to_px(x, y):
        return (h.win_w // 2 + int(round(x * scale)),
                h.win_h // 2 - int(round(y * scale)))

    h.adapter.update_sun(SUN, (3, 3, 3))

    def snap(tag):
        h.step(4)
        img = h.capture()
        h.save_capture(img, tag)
        return img

    def lum(img, wx, wy, half=3):
        px, py = to_px(wx, wy)
        return common.avg_lum(img, px, py, half=half)

    # --- A. The bias trap, at open-world extent, engine defaults --------
    pipeline.set_shadow_extent(140, 600)   # legacy bias 0.005 -> 3.0 world
    img = snap('bias_trap')
    trap_shadow = lum(img, *SHADOW_C)
    trap_lit = lum(img, *MIRROR_C)
    h.report.check('bias_trap_at_scale',
                   abs(trap_shadow - trap_lit) < 0.05,
                   f'under-occluder lum={trap_shadow:.3f} vs open ground '
                   f'{trap_lit:.3f}: default bias 0.005 x depth 600 = 3.0 '
                   f'world units ERASES the 1.2-high caster (gap 2.4) — '
                   f'the trap is real and measured')

    # --- B. World-unit bias restores; angled sun lands where predicted --
    pipeline.set_shadow_bias(0.2, world_units=True)
    img = snap('bias_world')
    b_shadow = lum(img, *SHADOW_C)
    b_lit = lum(img, *MIRROR_C)
    h.report.check('bias_world_units_restores', b_shadow < 0.5 * b_lit,
                   f'shadow lum={b_shadow:.3f} lit={b_lit:.3f} with '
                   f'set_shadow_bias(0.2, world_units=True)')
    h.report.check('angled_sun_shadow_where_predicted',
                   b_shadow < 0.5 * b_lit and b_lit > 0.3,
                   f'sun 30 deg elevation: dark at predicted '
                   f'({SHADOW_C[0]:.2f},0), lit at mirror '
                   f'({MIRROR_C[0]:.2f},0)')

    # --- C. World bias is extent-invariant ------------------------------
    pipeline.set_shadow_extent(12, 60)
    img = snap('bias_world_small_extent')
    c_shadow = lum(img, *SHADOW_C)
    c_lit = lum(img, *MIRROR_C)
    h.report.check('bias_world_extent_invariant', c_shadow < 0.5 * c_lit,
                   f'same 0.2 world bias at extent 12/60: shadow '
                   f'lum={c_shadow:.3f} lit={c_lit:.3f} (normalized bias '
                   f'would have changed by 10x)')

    # --- D. 3x3 PCF: edge widens, interior/lit unchanged ----------------
    # Extent 40/600: shadow texel = 80/1024 = 0.078 world = 4 px here.
    # Receiver-slope depth per tap (tan 60 deg x texel = 0.135) stays
    # under the 0.2 world bias, so open ground cannot self-shadow.
    pipeline.set_shadow_extent(40, 600)

    def edge_width(img, dark, lit):
        lo, hi = dark + 0.06, lit - 0.06
        y_px = h.win_h // 2
        n = 0
        for x_px in range(*sorted((to_px(EDGE_X - 0.8, 0)[0],
                                   to_px(EDGE_X + 0.8, 0)[0]))):
            v = common.avg_lum(img, x_px, y_px, half=0)
            if lo < v < hi:
                n += 1
        return n

    img = snap('pcf_1tap')
    d1_shadow = lum(img, *SHADOW_C)
    d1_lit = lum(img, *MIRROR_C)
    w1 = edge_width(img, d1_shadow, d1_lit)

    pipeline.set_shadow_filter_size(3)
    img = snap('pcf_3tap')
    d3_shadow = lum(img, *SHADOW_C)
    d3_lit = lum(img, *MIRROR_C)
    w3 = edge_width(img, d3_shadow, d3_lit)
    pipeline.set_shadow_filter_size(1)

    h.report.check('pcf_edge_softens', w3 >= w1 + 3,
                   f'edge transition {w1}px (1 tap) -> {w3}px (3x3); '
                   f'texel = 4px, expect ~+2 texels')
    h.report.check('pcf_interior_unchanged',
                   abs(d3_shadow - d1_shadow) < 0.03
                   and abs(d3_lit - d1_lit) < 0.03,
                   f'interior {d1_shadow:.3f}->{d3_shadow:.3f}, '
                   f'lit {d1_lit:.3f}->{d3_lit:.3f} across filter switch')

    # --- E. Blessed no-cast API -----------------------------------------
    pipeline.exclude_from_shadows(occluder)
    img = snap('nocast_excluded')
    e_shadow = lum(img, *SHADOW_C)
    occ_px = to_px(0, 0)
    occ_c = img.get_xel(occ_px[0], occ_px[1])
    h.report.check('nocast_excluded_ground_lit', e_shadow > 0.5 * d1_lit,
                   f'ground under excluded occluder lum={e_shadow:.3f} '
                   f'(lit ref {d1_lit:.3f})')
    h.report.check('nocast_still_visible_to_camera',
                   occ_c[0] > 0.25 and occ_c[0] > 1.5 * occ_c[1],
                   f'occluder pixel rgb=({occ_c[0]:.2f},{occ_c[1]:.2f},'
                   f'{occ_c[2]:.2f}) — red card still renders in the '
                   f'main view')

    pipeline.include_in_shadows(occluder)
    img = snap('nocast_included_again')
    f_shadow = lum(img, *SHADOW_C)
    h.report.check('nocast_include_restores', f_shadow < 0.5 * d1_lit,
                   f'shadow back after include_in_shadows '
                   f'(lum={f_shadow:.3f})')

    h.report.finish()


if __name__ == '__main__':
    main()
