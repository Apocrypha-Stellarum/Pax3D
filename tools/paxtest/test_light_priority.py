"""paxtest: forward-light selection policy + local light budgets (ER-008).

THE ANSWER ER-008 ASKED FOR, pinned mechanically: when a node's active
lights exceed max_lights (the shader array size), the engine uploads
the highest-`Light.set_priority()` lights and SILENTLY DROPS the rest.
Ties break by class rank (spot > directional > point — light.h
ClassPriority); within equal priority+class the order is effectively
arbitrary. So with all-default priorities a nearby cabin lamp can lose
its slot to a distant flood — the ER's exact fear. Priority is fully
dynamic: set_priority bumps a global sort seq and every LightAttrib
re-sorts lazily.

Checks (uniforms sun mode — the sun occupies no array slot):
  1. Overflow drops silently: 3 co-axial point lights (pure R/G/B) on
     a max_lights=2 pipeline -> exactly 2 of 3 channels render.
  2. Priority selects the bound set: priorities C>A>B -> R+B present,
     G absent.
  3. Priority re-sort is LIVE: raising B above A mid-session flips the
     bound set without rebinding anything.
  4. set_light_budget (the ER-008 structural ask): a per-root warden
     binds the top-N candidates scored by luma over the light's own
     attenuation at its distance -> nearest two bound, far one not.
  5. The warden rebinds on motion: moving the far light nearest swaps
     the bound set within a frame.
  6. clear_light_budget unbinds everything it bound (dark card).

Directional-variant run (--sun-mode directional, from run.py):
  7. THE SUN SURVIVES OVERFLOW: two flood spotlights + the pipeline
     sun on a max_lights=2 pipeline. Spots outrank directionals at
     equal priority, so without the pipeline's sun-priority guard
     (_create_sun_light pins priority 1<<20) the floods would evict
     the sun — and its shadows — from every draw. Gate: the card
     center (outside both spot cones) is still sun-lit, and exactly
     one spot won the remaining slot.

Only meaningful for pax3d_render (max_lights kwarg + the warden live
there).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common


def avg_rgb(img, cx, cy, half=2):
    r = g = b = 0.0
    n = 0
    for y in range(cy - half, cy + half + 1):
        for x in range(cx - half, cx + half + 1):
            c = img.get_xel(x, y)
            r += c[0]
            g += c[1]
            b += c[2]
            n += 1
    return r / n, g / n, b / n


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--sun-mode', default='uniforms')
    args = parser.parse_args()

    h = common.Harness(args, 'light_priority')
    if args.pipeline != 'pax3d_render':
        h.report.skip('max_lights/set_light_budget live in pax3d_render '
                      '(ER-008)')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    sun_mode=args.sun_mode,
                    extra_pipeline_kwargs={'max_lights': 2})
    pipeline = h.adapter.pipeline

    base = h.base
    h.set_ortho(film_h=2.0)

    cm = p3d.CardMaker('light_card')
    cm.set_frame(-1, 1, -1, 1)
    card = base.render.attach_new_node(cm.generate())
    card.set_two_sided(True)
    mat = p3d.Material('white_diffuse')
    mat.set_base_color(p3d.LColor(1, 1, 1, 1))
    mat.set_metallic(0.0)
    mat.set_roughness(1.0)
    card.set_material(mat, 1)

    def px(fx, fy):
        return (int((fx / 2.0 + 0.5) * h.win_w),
                int((0.5 - fy / 2.0) * h.win_h))

    cx, cy = px(0.0, 0.0)
    HI, LO = 0.10, 0.03

    if args.sun_mode == 'directional':
        # --- Phase 7: the sun survives spot overflow --------------------
        h.adapter.update_sun((0, -1, 0), (2.0, 2.0, 2.0))
        spots = {}
        for tag, sx, aim, color in (
                ('green', -1.5, (-0.9, 0.0, 0.0), (0, 5, 0)),
                ('blue', 1.5, (0.9, 0.0, 0.0), (0, 0, 5))):
            sl = p3d.Spotlight(f'flood_{tag}')
            sl.set_color(p3d.LColor(color[0], color[1], color[2], 1))
            sl.set_attenuation(p3d.LVecBase3(1, 0, 0))
            snp = base.render.attach_new_node(sl)
            snp.set_pos(sx, -2.0, 0.0)
            snp.look_at(p3d.LPoint3(*aim))
            base.render.set_light(snp)
            spots[tag] = snp
        h.step(5)
        img = h.capture()
        h.save_capture(img, 'sun_overflow')
        r, g, b = avg_rgb(img, cx, cy)
        center_lum = (r + g + b) / 3.0
        h.report.check(
            'sun_survives_spot_overflow', center_lum > 0.3,
            f'center (outside both spot cones) lum={center_lum:.3f} — '
            f'sun priority guard holds against 2 floods on a 2-slot '
            f'array')
        # Exactly one spot should hold the remaining slot: measure each
        # spot's channel EXCESS over the sun-lit center.
        exl, eyl = px(-0.9, 0.0)
        exr, eyr = px(0.9, 0.0)
        g_excess = avg_rgb(img, exl, eyl)[1] - g
        b_excess = avg_rgb(img, exr, eyr)[2] - b
        n_spots = int(g_excess > 0.08) + int(b_excess > 0.08)
        h.report.check(
            'overflow_still_drops_one_spot', n_spots == 1,
            f'green excess {g_excess:.3f}, blue excess {b_excess:.3f} '
            f'-> {n_spots} spots bound (1 slot left beside the sun)')
        h.report.finish()
        return

    # --- Uniforms mode: the sun occupies no array slot ------------------
    h.adapter.update_sun((1, 0, 0), (0, 0, 0))

    # Zero-light baseline for the opt-out check. NOTE (part of the
    # ER-008 answer): a draw with NO active lights is not black — the
    # GSG fills empty array slots with defaults and slot 0's default is
    # WHITE (graphicsStateGuardian.cxx SMO_light_source_i), with
    # degenerate position/attenuation. Invisible in practice (the
    # pipeline always binds sun/ambient), but it is the no-light
    # ground truth this scene restores to.
    h.step(5)
    img_nolight = h.capture()

    lights = {}
    for tag, color, dist in (('red', (2, 0, 0), 1.0),
                             ('green', (0, 2, 0), 2.0),
                             ('blue', (0, 0, 2), 3.0)):
        pl = p3d.PointLight(f'pl_{tag}')
        pl.set_color(p3d.LColor(color[0], color[1], color[2], 1))
        pl.set_attenuation(p3d.LVecBase3(1, 0, 0))
        lnp = base.render.attach_new_node(pl)
        lnp.set_pos(0.0, -dist, 0.0)
        lights[tag] = lnp

    # --- Phase 1: overflow drops silently -------------------------------
    for lnp in lights.values():
        base.render.set_light(lnp)
    h.step(5)
    img = h.capture()
    rgb = avg_rgb(img, cx, cy)
    present = [c > HI for c in rgb]
    h.report.check(
        'overflow_binds_exactly_array_size', sum(present) == 2,
        f'3 lights on a 2-slot array: rgb=({rgb[0]:.3f}, {rgb[1]:.3f}, '
        f'{rgb[2]:.3f}) -> {sum(present)} bound (excess silently '
        f'dropped)')
    h.report.info(
        'tie_order_observed',
        f'all priorities 0: bound set = '
        f'{[t for t, p in zip(("red", "green", "blue"), present) if p]} '
        f'(arbitrary — do not rely on it)')

    # --- Phase 2: priority selects the bound set ------------------------
    lights['red'].node().set_priority(1)
    lights['green'].node().set_priority(0)
    lights['blue'].node().set_priority(2)
    h.step(5)
    rgb = avg_rgb(h.capture(), cx, cy)
    h.report.check(
        'priority_selects_bound_set',
        rgb[0] > HI and rgb[2] > HI and rgb[1] < LO,
        f'priorities R=1 G=0 B=2: rgb=({rgb[0]:.3f}, {rgb[1]:.3f}, '
        f'{rgb[2]:.3f}) — top-2 priorities bound, green dropped')

    # --- Phase 3: priority re-sort is live ------------------------------
    lights['green'].node().set_priority(3)
    h.step(5)
    rgb = avg_rgb(h.capture(), cx, cy)
    h.report.check(
        'priority_resort_is_live',
        rgb[1] > HI and rgb[2] > HI and rgb[0] < LO,
        f'green raised to 3 mid-session: rgb=({rgb[0]:.3f}, '
        f'{rgb[1]:.3f}, {rgb[2]:.3f}) — bound set flipped without '
        f'rebinding')

    # --- Phase 4: the warden binds the top-scoring set ------------------
    for lnp in lights.values():
        base.render.clear_light(lnp)
        lnp.node().set_priority(0)
    # Equal-luma colors + quadratic attenuation -> score is purely a
    # distance ranking; intensities keep every bound light readable.
    for tag, color in (('red', (13.6, 0, 0)), ('green', (0, 4.0, 0)),
                       ('blue', (0, 0, 39.9))):
        lights[tag].node().set_color(p3d.LColor(*color, 1))
        lights[tag].node().set_attenuation(p3d.LVecBase3(1, 0, 1))
    pipeline.set_light_budget(card, list(lights.values()), budget=2)
    h.step(5)
    rgb = avg_rgb(h.capture(), cx, cy)
    h.report.check(
        'warden_binds_top_scoring',
        rgb[0] > HI and rgb[1] > HI and rgb[2] < LO,
        f'd=1,2,3 @ budget 2: rgb=({rgb[0]:.3f}, {rgb[1]:.3f}, '
        f'{rgb[2]:.3f}) — nearest two bound, far one not')

    # --- Phase 5: the warden rebinds on motion --------------------------
    lights['blue'].set_pos(0.0, -0.5, 0.0)
    h.step(5)
    rgb = avg_rgb(h.capture(), cx, cy)
    h.report.check(
        'warden_rebinds_on_motion',
        rgb[2] > HI and rgb[0] > HI and rgb[1] < LO,
        f'blue moved nearest: rgb=({rgb[0]:.3f}, {rgb[1]:.3f}, '
        f'{rgb[2]:.3f}) — bound set follows the scores')

    # --- Phase 6: opt-out restores the zero-light baseline --------------
    pipeline.clear_light_budget(card)
    h.step(5)
    rms = common.image_rms_diff(img_nolight, h.capture(), step=1)
    h.report.check(
        'warden_optout_unbinds', rms == 0.0,
        f'clear_light_budget: rms vs zero-light baseline = {rms:.2e} '
        f'(every warden-bound light cleared; byte-identical restore)')

    h.report.finish()


if __name__ == '__main__':
    main()
