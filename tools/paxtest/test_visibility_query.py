"""paxtest: depth-tap visibility queries (Session AF — the lens-flare
occluder retirement).

pipeline.add_visibility_query(np, radius_px) reports, per frame, the
fraction of a tap disc around np's projected screen position where the
SCENE DEPTH does not occlude it — the general replacement for the
game's hand-built analytic flare occluders (ray-sphere lists cannot
express "the camera is inside a hull"; the depth buffer can). The pass
renders BEFORE the scene (reads last frame's depth), so the tiny
RTM_copy_ram readback stalls on nothing; results are ~2 frames latent.

Scene: perspective camera at the origin looking +Y. A wall card
spanning x in [-8, 0] at y=10 covers EXACTLY the left half of the
screen at every depth (the x=0 edge plane contains the camera, so it
projects to the vertical center line) — visibility analytics are
therefore exact by construction:

  1. open_sky_full — target in the open right half: 1.0 (taps read
     cleared depth).
  2. blocked_zero — target behind the wall half: 0.0.
  3. half_covered — target projecting exactly ON the wall edge: ~0.5
     (the tap disc splits down the middle).
  4. behind_geometry_visible — a card BEHIND the target does not
     occlude (scene depth > target depth = visible).
  5. sky_dome_default_blocks / sky_dome_horizon_opens — a full-screen
     dome card in front of a beyond-it target occludes by default;
     max_occluder_depth below the dome distance re-opens it (the
     documented sky-dome knob).
  6. query_pass_invisible — registering queries leaves the RENDERED
     frame byte-identical (the query buffer never touches the visible
     chain).
  7. latency INFO — frames from a scene change to the value flip.
  8. LOUD FAILURE on depth-source degrade (2026-07-27, the paxcraft
     Session-5 trap promoted to contract): a viewmodel region in
     depth_mode='clear' stomps the scene depth full-screen, so the
     query taps would confidently read "open sky everywhere" (flare
     through mountains). Now: pipeline.visibility_query_valid flips
     False, every query fails CLOSED (visibility 0.0, .valid False),
     and unregistering restores validity + real readings. A 'range'
     request that degrades ('clear' fallback under log depth or on
     stock 1.10) invalidates the same way, and
     on_depth_degrade='raise' makes the degrade fatal at
     registration. Where 'range' is honored (Pax3D 1.11, linear
     depth), queries stay valid THROUGH a registered viewmodel — and
     flipping enable_log_depth on mid-session degrades it live,
     loudly.

The @logdepth variant (run.py) reruns the row with enable_log_depth
(the linear_depth decode's other branch). Only meaningful for
pax3d_render (add_visibility_query lives there).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common


def make_card(parent, x0, x1, z0, z1, y, name):
    cm = p3d.CardMaker(name)
    cm.set_frame(x0, x1, z0, z1)
    np = parent.attach_new_node(cm.generate())
    np.set_pos(0, y, 0)
    return np


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    parser.add_argument('--log-depth', action='store_true')
    args = parser.parse_args()

    h = common.Harness(args, 'visibility_query')
    if args.pipeline != 'pax3d_render':
        h.report.skip('add_visibility_query lives in pax3d_render '
                      '(Session AF)')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson',
                    log_depth=args.log_depth,
                    extra_pipeline_kwargs={
                        'enable_visibility_query': True})
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'add_visibility_query'):
        h.report.skip('pipeline has no add_visibility_query (Session AF)')
    base = h.base

    h.adapter.update_sun((0, -1, 0), (0, 0, 0))
    base.camera.set_pos(0, 0, 0)
    base.camera.set_hpr(0, 0, 0)
    if args.log_depth:
        base.camLens.set_near_far(0.1, 1e6)
    else:
        base.camLens.set_near_far(1.0, 1000.0)

    # The wall: x in [-8, 0] at y=10 — its x=0 edge plane contains the
    # camera, so it covers exactly the left half of the screen at any
    # depth. z span generous (full vertical coverage).
    wall = make_card(base.render, -8, 0, -8, 8, 10, 'paxtest_vis_wall')

    open_np = base.render.attach_new_node('paxtest_vis_open')
    open_np.set_pos(2.0, 50, 0)                    # right half: open sky
    blocked_np = base.render.attach_new_node('paxtest_vis_blocked')
    blocked_np.set_pos(-2.0, 50, 0)                # left half: walled
    edge_np = base.render.attach_new_node('paxtest_vis_edge')
    edge_np.set_pos(0.0, 50, 0)                    # exactly on the edge

    q_open = pipeline.add_visibility_query(open_np, radius_px=6.0)
    q_blocked = pipeline.add_visibility_query(blocked_np, radius_px=6.0)
    q_edge = pipeline.add_visibility_query(edge_np, radius_px=6.0)

    img_with_queries = None

    h.step(6)                                      # flush the latency
    h.report.check('open_sky_full', q_open.visibility > 0.95,
                   f'open target: visibility {q_open.visibility:.3f} '
                   f'(cleared depth counts as open sky)')
    h.report.check('blocked_zero', q_blocked.visibility < 0.05,
                   f'walled target: visibility {q_blocked.visibility:.3f}')
    h.report.check('half_covered',
                   abs(q_edge.visibility - 0.5) < 0.2,
                   f'edge target: visibility {q_edge.visibility:.3f} '
                   f'(tap disc split by the wall edge — smooth partial '
                   f'occlusion)')

    # --- 4. Geometry BEHIND the target does not occlude -----------------
    backdrop = make_card(base.render, 0, 8, -8, 8, 200,
                         'paxtest_vis_backdrop')
    h.step(6)
    h.report.check('behind_geometry_visible', q_open.visibility > 0.95,
                   f'backdrop at y=200 behind the y=50 target: '
                   f'visibility {q_open.visibility:.3f}')
    backdrop.remove_node()

    # --- 5. The sky-dome knob -------------------------------------------
    # A "dome" covering the whole view at y=80; the "sun" beyond it.
    dome = make_card(base.render, -30, 30, -30, 30, 80,
                     'paxtest_vis_dome')
    sun_np = base.render.attach_new_node('paxtest_vis_sun')
    sun_np.set_pos(2.0, 200, 0)
    q_sun = pipeline.add_visibility_query(sun_np, radius_px=6.0)
    h.step(6)
    h.report.check('sky_dome_default_blocks', q_sun.visibility < 0.05,
                   f'dome at y=80 in front of the y=200 sun: visibility '
                   f'{q_sun.visibility:.3f} (default: any closer depth '
                   f'occludes)')
    pipeline.remove_visibility_query(q_sun)
    q_sun = pipeline.add_visibility_query(sun_np, radius_px=6.0,
                                          max_occluder_depth=70.0)
    h.step(6)
    h.report.check('sky_dome_horizon_opens', q_sun.visibility > 0.95,
                   f'max_occluder_depth=70 (below the dome distance): '
                   f'visibility {q_sun.visibility:.3f} — the sky-dome '
                   f'valve')
    pipeline.remove_visibility_query(q_sun)
    sun_np.remove_node()
    dome.remove_node()
    h.step(3)
    img_with_queries = h.capture()

    # --- 6. The query pass never touches the visible frame --------------
    pipeline.remove_visibility_query(q_open)
    pipeline.remove_visibility_query(q_blocked)
    pipeline.remove_visibility_query(q_edge)
    h.step(3)
    rms = common.image_rms_diff(img_with_queries, h.capture(), step=1)
    h.report.check('query_pass_invisible', rms == 0.0,
                   f'3 active queries vs none: rendered frame rms = '
                   f'{rms:.2e} (the query buffer is outside the visible '
                   f'chain)')

    # --- 7. Latency (informational) -------------------------------------
    q = pipeline.add_visibility_query(open_np, radius_px=6.0)
    h.step(6)
    before = q.visibility
    open_np.set_pos(-2.0, 50, 0)                   # jump behind the wall
    frames = 0
    for _ in range(8):
        h.step(1)
        frames += 1
        if q.visibility < 0.05:
            break
    h.report.info('latency_frames',
                  f'value flipped {before:.2f} -> '
                  f'{q.visibility:.2f} in {frames} frames after the '
                  f'target moved (contract: ~2, depth is one frame old)')

    # --- 8. Loud failure when the depth source degrades ------------------
    # (2026-07-27, paxcraft ask — the Session-5 three-session trap.)
    open_np.set_pos(2.0, 50, 0)                    # back to open sky
    h.step(6)
    h.report.check('healthy_state_valid',
                   pipeline.visibility_query_valid and q.valid
                   and q.visibility > 0.95,
                   f'no depth stomper: visibility_query_valid='
                   f'{pipeline.visibility_query_valid}, q.valid='
                   f'{q.valid}, visibility {q.visibility:.3f}')

    # A 'clear'-mode viewmodel stomps the scene depth: the OLD behavior
    # was a confident 1.0 everywhere; the contract is now fail-closed.
    vm_root = base.render.attach_new_node('paxtest_vis_vm_root')
    reg = pipeline.register_viewmodel_camera(vm_root, depth_mode='clear')
    h.step(6)
    h.report.check('clear_viewmodel_invalidates',
                   not pipeline.visibility_query_valid
                   and not q.valid and q.visibility == 0.0,
                   f'viewmodel depth_mode="clear" registered: '
                   f'visibility_query_valid='
                   f'{pipeline.visibility_query_valid}, q.valid='
                   f'{q.valid}, visibility {q.visibility:.3f} '
                   f'(fail closed — NOT the garbage open-sky read)')
    pipeline.unregister_viewmodel_camera(reg)
    h.step(6)
    h.report.check('unregister_restores_valid',
                   pipeline.visibility_query_valid and q.valid
                   and q.visibility > 0.95,
                   f'viewmodel unregistered: visibility_query_valid='
                   f'{pipeline.visibility_query_valid}, q.valid='
                   f'{q.valid}, visibility {q.visibility:.3f}')

    has_range = hasattr(p3d.DisplayRegion, 'set_depth_range')
    range_degrades = args.log_depth or not has_range
    if range_degrades:
        # The trap case: 'range' requested but not honorable (log depth
        # on, or stock 1.10). Must invalidate — and 'raise' must be
        # fatal at registration.
        raised = False
        try:
            pipeline.register_viewmodel_camera(
                vm_root, depth_mode='range', on_depth_degrade='raise')
        except RuntimeError:
            raised = True
        h.report.check('range_degrade_raises', raised,
                       'on_depth_degrade="raise": degraded "range" '
                       'request raised RuntimeError at registration')
        reg = pipeline.register_viewmodel_camera(vm_root,
                                                 depth_mode='range')
        h.step(3)
        h.report.check('range_degrade_invalidates',
                       not pipeline.visibility_query_valid
                       and q.visibility == 0.0,
                       f'degraded "range" viewmodel: '
                       f'visibility_query_valid='
                       f'{pipeline.visibility_query_valid}, visibility '
                       f'{q.visibility:.3f} (fail closed)')
        pipeline.unregister_viewmodel_camera(reg)
        h.step(3)
    else:
        # 'range' honored: world depth survives outside the viewmodel
        # silhouette — queries stay VALID through a live viewmodel.
        reg = pipeline.register_viewmodel_camera(vm_root,
                                                 depth_mode='range')
        h.step(6)
        h.report.check('range_mode_stays_valid',
                       pipeline.visibility_query_valid and q.valid
                       and q.visibility > 0.95,
                       f'honored "range" viewmodel: '
                       f'visibility_query_valid='
                       f'{pipeline.visibility_query_valid}, visibility '
                       f'{q.visibility:.3f}')
        # The exact Session-5 shape: log depth flips ON with the
        # 'range' viewmodel live — must degrade loudly, not silently.
        pipeline.set_enable_log_depth(True)
        base.camLens.set_near_far(0.1, 1e6)
        h.step(3)
        h.report.check('logdepth_flip_degrades_live',
                       not pipeline.visibility_query_valid
                       and q.visibility == 0.0,
                       f'enable_log_depth flipped on under a live '
                       f'"range" viewmodel: visibility_query_valid='
                       f'{pipeline.visibility_query_valid}, visibility '
                       f'{q.visibility:.3f} (degraded to "clear", '
                       f'fail closed)')
        pipeline.unregister_viewmodel_camera(reg)

    h.report.finish()


if __name__ == '__main__':
    main()
