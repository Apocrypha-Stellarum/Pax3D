"""Openworld-scale direction-gated shadow probe (Session H).

The in-app repro is now LOCAL and deterministic: openworld's village at
alt 34 / az 120 (east) has perfect shadows; alt 34 / az 240 (west) has
none (plus terrain banding), on the current engine tree. The toy-scale
probe (probe_azimuth_sweep.py) is green on all azimuths, so the trigger
needs scale and/or their exact ingredients. This probe rebuilds the
openworld configuration faithfully OUTSIDE the app:

  - their prc reality (gl 3 2, textures-power-2 none)
  - their pipeline kwargs (4096 map, bias_world 0.18, PCF3, caster mask,
    max_lights 10, fog on, hejl_dawson, directional sun)
  - the village GLB, camera at the spawn pose
  - set_shadow_extent(140, 600, center=camera) like the follow-frustum
  - the EXACT game/daynight.py alt/az->vector mapping (incl. 0.1 deg
    quantization), hour-12 sun color/exposure/ambient

plus a known flat-card + cube caster (their OW_BOXTEST geometry) so the
shadow test has an analytic sample point over known-albedo ground.

Per direction it reports: box-shadow luminance ratio (shadows on/off)
and the mode-11 shadowed-pixel fraction, and saves a lit screenshot.

Bisect knobs: --radius --depth --map-size --center --no-village --pcf
--bias-world --max-lights --alts --azs.

Run under BOTH engines (identity = defect is in Python/GLSL, not C++):
  C:/python/pax3d-env/Scripts/python.exe tools/paxtest/probe_openworld_scale.py
  C:/Python313/python.exe tools/paxtest/probe_openworld_scale.py
"""
import argparse
import math
import os
import sys

PAXTEST = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PAXTEST)

import panda3d.core as p3d

VILLAGE_GLB = r'C:\python\openworld\3D assets\Village\uploads_files_3912680_Village_2.glb'
SPAWN_POS = (95.0, 50.0, 15.0)
SPAWN_HPR = (150.0, -20.0, 0.0)


def daynight_sun_dir(alt_deg, az_deg):
    """EXACT copy of openworld game/daynight.py apply() mapping."""
    alt_deg = round(alt_deg / 0.1) * 0.1
    az_deg = round(az_deg / 0.1) * 0.1
    alt = math.radians(alt_deg)
    az = math.radians(az_deg)
    return p3d.Vec3(math.sin(az) * math.cos(alt),
                    math.cos(az) * math.cos(alt),
                    math.sin(alt))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--radius', type=float, default=140.0)
    ap.add_argument('--depth', type=float, default=600.0)
    ap.add_argument('--map-size', type=int, default=4096)
    ap.add_argument('--center', default='camera', choices=['camera', 'origin'])
    ap.add_argument('--no-village', action='store_true')
    ap.add_argument('--pcf', type=int, default=3)
    ap.add_argument('--bias-world', type=float, default=0.18)
    ap.add_argument('--max-lights', type=int, default=10)
    ap.add_argument('--alts', default='34')
    ap.add_argument('--azs', default='120,240')
    ap.add_argument('--shots', action='store_true', default=True)
    ap.add_argument('--grid', type=int, default=0,
                    help='tessellate the ground card into NxN tiles '
                         '(0 = single 600m card, the failing case)')
    ap.add_argument('--pillars', action='store_true',
                    help='row of thin pillars along the az axis; measure '
                         'each shadow displacement from analytic truth')
    ap.add_argument('--ortho-cam', action='store_true',
                    help='overhead orthographic main camera instead of the '
                         'perspective spawn camera (w=1: no perspective '
                         'interpolation of varyings)')
    ap.add_argument('--actor', action='store_true',
                    help='add a skinned glTF Actor (openworld f_1.glb) and '
                         'diff its depth-map texels per direction')
    ap.add_argument('--walk', action='store_true',
                    help='loop the Walk animation instead of pinning a pose')
    ap.add_argument('--follow', action='store_true',
                    help='per-frame follow-frustum recentre (their snap '
                         'math) + per-frame update_sun, in app order')
    ap.add_argument('--patch', action='store_true',
                    help='known flat receiver patch at the actor feet '
                         '(controlled receiver inside the village scene)')
    ap.add_argument('--village-shadow-only', action='store_true',
                    help='village invisible to the main camera but still '
                         'renders into the depth map')
    ap.add_argument('--village-no-cast', action='store_true',
                    help='village visible but excluded from the depth map')
    ap.add_argument('--baseline-game', action='store_true',
                    help='GLSL-120 game baseline instead of gl 3 2 / 330')
    ap.add_argument('--strip-broken', action='store_true',
                    help='remove the three malformed no-material meshes '
                         'the loader warns about (Mesh.385/9098/9147)')
    ap.add_argument('--mirror', action='store_true',
                    help='mirror the village in X (geography control: if '
                         'the failing azimuth flips with the terrain, the '
                         'engine has no direction dependence)')
    args_probe = ap.parse_args()

    # prc that must precede ShowBase: openworld's texture + cache reality.
    p3d.load_prc_file_data('', 'textures-power-2 none')
    if os.environ.get('PROBE_GL_DEBUG'):
        p3d.load_prc_file_data('', 'gl-debug #t')
    cache_dir = os.path.join(PAXTEST, 'output', 'owcache')
    os.makedirs(cache_dir, exist_ok=True)
    p3d.load_prc_file_data(
        '', 'model-cache-dir ' + p3d.Filename.from_os_specific(cache_dir).get_fullpath())

    import common
    parser = common.add_common_args(argparse.ArgumentParser())
    h_args = parser.parse_args(['--pipeline', 'pax3d_render',
                                '--baseline',
                                'game' if args_probe.baseline_game
                                else 'modern',
                                '--win-size', '960x540'])
    h = common.Harness(h_args, 'owscale')
    h.init_pipeline(
        exposure=math.log2(1.35), tonemap='hejl_dawson',
        sun_mode='directional', shadows=True, bloom=False,
        extra_pipeline_kwargs={
            'shadow_map_size': args_probe.map_size,
            'shadow_bias_world': args_probe.bias_world,
            'shadow_filter_size': args_probe.pcf,
            'shadow_caster_mask': 1,
            'max_lights': args_probe.max_lights,
            'enable_fog': True,
        })
    pipeline = h.adapter.pipeline
    base = h.base

    import gltf as gltf_mod
    if hasattr(gltf_mod, 'patch_loader'):
        gltf_mod.patch_loader(base.loader)

    # hour-12 ambient from daynight AMBIENT_KEYFRAMES
    alight = p3d.AmbientLight('amb')
    alight.set_color(p3d.LColor(0.30, 0.32, 0.36, 1))
    base.render.set_light(base.render.attach_new_node(alight))

    # camera: spawn pose, their lens (or overhead ortho for the
    # perspective-interpolation discriminator)
    if args_probe.ortho_cam:
        lens = p3d.OrthographicLens()
        lens.set_film_size(400, 400 * h.win_h / h.win_w)
        lens.set_near_far(1, 800)
        base.cam.node().set_lens(lens)
        base.camera.set_pos(SPAWN_POS[0], SPAWN_POS[1], 415)
        base.camera.set_hpr(0, -90, 0)
    else:
        base.camLens.set_near_far(0.3, 8000.0)
        base.camLens.set_fov(80)
        base.camera.set_pos(*SPAWN_POS)
        base.camera.set_hpr(*SPAWN_HPR)
    cam = p3d.Vec3(*SPAWN_POS)

    if not args_probe.no_village:
        scene_np = base.loader.load_model(
            p3d.Filename.from_os_specific(VILLAGE_GLB))
        scene_np.reparent_to(base.render)
        if args_probe.mirror:
            # mirror about the camera's x so the local geography flips
            scene_np.set_pos(2 * SPAWN_POS[0], 0, 0)
            scene_np.set_scale(-1, 1, 1)
            scene_np.set_two_sided(True)   # neutralize flipped winding
        if args_probe.strip_broken:
            stripped = 0
            for name in ('Mesh.385', 'Mesh.9098', 'Mesh.9147'):
                for np_ in scene_np.find_all_matches('**/' + name):
                    np_.remove_node()
                    stripped += 1
                for np_ in scene_np.find_all_matches('**/' + name + '*'):
                    np_.remove_node()
                    stripped += 1
            print(f'[probe] stripped {stripped} malformed mesh nodes')
        if args_probe.village_shadow_only:
            # invisible to every camera except the shadow camera (which
            # runs with camera-mask bit 1, the caster mask)
            scene_np.hide()
            scene_np.show_through(p3d.BitMask32.bit(1))
        elif args_probe.village_no_cast:
            pipeline.exclude_from_shadows(scene_np)

    # OW_BOXTEST-style reference geometry: flat card at cam.z-3 + 8m cube
    # 25m ahead along the camera heading, resting on the card.
    card_z = cam.z - 3.0
    if args_probe.grid > 0:
        n = args_probe.grid
        tile = 600.0 / n
        groot = base.render.attach_new_node('ground_grid')
        for iy in range(n):
            for ix in range(n):
                cmt = p3d.CardMaker(f'tile_{ix}_{iy}')
                x0 = -300 + ix * tile
                y0 = -300 + iy * tile
                cmt.set_frame(x0, x0 + tile, y0, y0 + tile)
                groot.attach_new_node(cmt.generate())
        groot.set_p(-90)
        groot.set_pos(cam.x, cam.y, card_z + 0.05)
        groot.set_color(0.5, 0.7, 0.35, 1)
        groot.flatten_strong()
    else:
        cm = p3d.CardMaker('ground')
        cm.set_frame(-300, 300, -300, 300)
        g = base.render.attach_new_node(cm.generate())
        g.set_p(-90)
        g.set_pos(cam.x, cam.y, card_z + 0.05)
        g.set_color(0.5, 0.7, 0.35, 1)
    hrad = math.radians(SPAWN_HPR[0])
    fwd = p3d.Vec3(-math.sin(hrad), math.cos(hrad), 0)
    box_center = p3d.Vec3(cam.x + fwd.x * 25, cam.y + fwd.y * 25, card_z + 4.0)
    box = base.render.attach_new_node('box')
    for hpr, pos in [((0, 0, 0), (0, -4, 0)), ((180, 0, 0), (0, 4, 0)),
                     ((90, 0, 0), (-4, 0, 0)), ((-90, 0, 0), (4, 0, 0)),
                     ((0, -90, 0), (0, 0, 4)), ((0, 90, 0), (0, 0, -4))]:
        cmf = p3d.CardMaker('face')
        cmf.set_frame(-4, 4, -4, 4)
        f = box.attach_new_node(cmf.generate())
        f.set_hpr(*hpr)
        f.set_pos(*pos)
    box.set_pos(box_center)
    box.set_color(0.8, 0.4, 0.3, 1)
    # Cards are single-sided; force two-sided so the depth pass writes the
    # full silhouette regardless of per-face winding (a hollow footprint
    # here corrupts the umbra and masquerades as the engine bug).
    box.set_two_sided(True)
    g_all = base.render.find('**/ground')
    if not g_all.is_empty():
        g_all.set_two_sided(True)

    actor_np = None
    if args_probe.actor:
        from direct.actor.Actor import Actor
        actor_np = Actor(p3d.Filename.from_os_specific(
            r'C:\python\openworld\3D assets\Casual Characters\f_1.glb'
        ).get_fullpath())
        actor_np.reparent_to(base.render)
        actor_z = card_z + 0.1 if args_probe.no_village else 13.5
        apos = p3d.Vec3(cam.x + fwd.x * 12, cam.y + fwd.y * 12, actor_z)
        actor_np.set_pos(apos)
        anims = sorted(actor_np.get_anim_names())
        if args_probe.walk and 'Walk' in actor_np.get_anim_names():
            actor_np.loop('Walk')
        elif anims:
            actor_np.pose(anims[0], 0)   # pinned pose (fact #12)

    if args_probe.patch and actor_np is not None:
        # TWO patches in the same frame: untextured (left/near half) and
        # textured (right/far half). If the shadow term differs between
        # them, the shadow sampler's texture binding depends on the
        # geom's texture layout — the smoking gun.
        cmp_ = p3d.CardMaker('patch')
        cmp_.set_frame(-10, 0, -10, 10)     # west half: untextured
        pnp = base.render.attach_new_node(cmp_.generate())
        pnp.set_p(-90)
        pnp.set_pos(apos.x, apos.y, apos.z - 0.01)
        pnp.set_color(0.75, 0.75, 0.5, 1)
        pnp.set_two_sided(True)
        teximg = p3d.PNMImage(64, 64)
        teximg.fill(0.75, 0.75, 0.5)
        ptex = p3d.Texture('patchtex')
        ptex.load(teximg)
        cmp2 = p3d.CardMaker('patch_tex')
        cmp2.set_frame(0, 10, -10, 10)      # east half: textured
        pnp2 = base.render.attach_new_node(cmp2.generate())
        pnp2.set_p(-90)
        pnp2.set_pos(apos.x, apos.y, apos.z - 0.01)
        pnp2.set_texture(ptex)
        pnp2.set_two_sided(True)

    center = cam if args_probe.center == 'camera' else p3d.Vec3(0, 0, 0)
    pipeline.set_shadow_extent(args_probe.radius, args_probe.depth,
                               center=center)

    os.makedirs(common.OUTPUT_DIR, exist_ok=True)
    tag = ('g%d' % args_probe.grid if args_probe.grid else 'card')
    tag += '_oc' if args_probe.ortho_cam else ''
    tag += '_nv' if args_probe.no_village else ''

    def world_to_px(p):
        rel = base.cam.get_relative_point(base.render, p)
        ndc = p3d.Point2()
        if not base.camLens.project(p3d.Point3(rel), ndc):
            return None
        return (int((ndc.x * 0.5 + 0.5) * h.win_w),
                int((0.5 - ndc.y * 0.5) * h.win_h))

    def shadow_fraction(img, thresh=0.4):
        n_shadow, n = 0, 0
        for y in range(0, h.win_h, 4):
            for x in range(0, h.win_w, 4):
                c = img.get_xel(x, y)
                if (c[0] + c[1] + c[2]) / 3.0 < thresh:
                    n_shadow += 1
                n += 1
        return n_shadow / max(n, 1)

    sun_color = p3d.Vec3(1.00 * 1.35, 0.97 * 1.35, 0.90 * 1.35)
    print(f'engine: {p3d.PandaSystem.get_version_string()}  '
          f'radius={args_probe.radius} depth={args_probe.depth} '
          f'map={args_probe.map_size} center={args_probe.center} '
          f'village={not args_probe.no_village}')
    print(f'{"alt":>5} {"az":>5} | {"off":>6} {"on":>6} {"ratio":>6} '
          f'| {"m11frac":>7} | verdict')

    alts = [float(v) for v in args_probe.alts.split(',')]
    azs = [float(v) for v in args_probe.azs.split(',')]
    def app_frame(sun_dir, n_frames):
        """Replicate the app's per-frame order: follow recentre (using the
        PREVIOUS frame's sun quat, like _follow_shadow_frustum), then
        update_sun, then render one frame."""
        for _ in range(n_frames):
            sun_np = pipeline.sun_light_np
            texel = 2.0 * args_probe.radius / args_probe.map_size
            quat = sun_np.get_quat()
            right, upv = quat.get_right(), quat.get_up()
            r = round(cam.dot(right) / texel) * texel
            u = round(cam.dot(upv) / texel) * texel
            snapped = cam + right * (r - cam.dot(right)) \
                + upv * (u - cam.dot(upv))
            pipeline.set_shadow_extent(args_probe.radius, args_probe.depth,
                                       center=snapped)
            h.adapter.update_sun(sun_dir, sun_color)
            h.step(1)

    for alt in alts:
        for az in azs:
            sun_dir = daynight_sun_dir(alt, az)
            if args_probe.follow:
                step_fn = lambda k, sd=sun_dir: app_frame(sd, k)
            else:
                step_fn = h.step
            h.adapter.update_sun(sun_dir, sun_color)
            # expected box-shadow point: box center projected to the card
            # along the sun ray
            horiz = p3d.Vec3(sun_dir.x, sun_dir.y, 0)
            drop = (box_center.z - card_z) / max(math.tan(math.radians(alt)), 1e-3)
            hn = p3d.Vec3(horiz)
            hn.normalize()
            spt = p3d.Vec3(box_center.x - hn.x * drop,
                           box_center.y - hn.y * drop, card_z + 0.05)
            spx = world_to_px(spt)

            step_fn(6)
            img = h.capture()
            on = common.avg_lum(img, spx[0], spx[1], half=3) if spx else -1
            if args_probe.shots:
                img.write(p3d.Filename.from_os_specific(os.path.join(
                    common.OUTPUT_DIR,
                    f'owscale_{tag}_a{alt:.0f}_z{az:.0f}.png')))

            pipeline.set_debug_lighting(11)
            step_fn(2)
            m11 = h.capture()
            if actor_np is not None:
                hnm = p3d.Vec3(sun_dir.x, sun_dir.y, 0)
                hnm.normalize()
                for label, sgn in (('anti-sun', -1.0), ('sunward', +1.0)):
                    row = []
                    for tt in [0.5 * i for i in range(1, 9)]:
                        wp = p3d.Point3(apos.x + sgn * hnm.x * tt,
                                        apos.y + sgn * hnm.y * tt, apos.z)
                        ppx = world_to_px(wp)
                        if ppx is None:
                            row.append('?')
                        else:
                            lv = common.avg_lum(m11, ppx[0], ppx[1], half=1)
                            row.append('X' if lv < 0.4 else '.')
                    print(f'    [m11-line {label}] ' + ''.join(row)
                          + '  (0.5m steps from feet)')
            frac = shadow_fraction(m11)
            m11.write(p3d.Filename.from_os_specific(os.path.join(
                common.OUTPUT_DIR,
                f'owscale_{tag}_m11_a{alt:.0f}_z{az:.0f}.png')))
            # mode-15 sweep: sample the GPU compare at points along the
            # BOX's umbra line (uniform-supplied coords — no receiver
            # geometry involved). Print GPU verdict vs CPU verdict.
            sun_np_s = pipeline.sun_light_np
            w2l_s = p3d.LMatrix4(sun_np_s.get_net_transform().get_mat())
            w2l_s.invert_in_place()
            biasm_s = p3d.LMatrix4(0.5, 0, 0, 0, 0, 0.5, 0, 0,
                                   0, 0, 0.5, 0, 0.5, 0.5, 0.5, 1)
            m_s = w2l_s * sun_np_s.node().get_lens().get_projection_mat() \
                * biasm_s
            hns = p3d.Vec3(sun_dir.x, sun_dir.y, 0)
            hns.normalize()
            dtex_s = common.find_light_depth_texture(pipeline.sun_light_np)
            dimg_s = common.read_depth_image(base, dtex_s)
            ns = dimg_s.get_x_size() if dimg_s else 0
            pipeline.set_debug_lighting(15)
            print('    [m15-sweep t(m), gap(m along ray), CPU, GPU]')
            for tt in (2.0, 5.0, 8.0, 11.0, 14.0, 18.0):
                sp = p3d.Point3(box_center.x - hns.x * tt,
                                box_center.y - hns.y * tt, card_z + 0.05)
                su = m_s.xform_point(sp)
                base.render.set_shader_input(
                    'u_probe_uvref', p3d.Vec3(su.x, su.y, su.z))
                h.step(2)
                cap = h.capture()
                gpu_term = common.avg_lum(cap, h.win_w // 2, h.win_h // 2,
                                          half=4)
                cpu = '?'
                gap = 0.0
                if dimg_s is not None and ns:
                    sx_ = int(su.x * ns)
                    sy_ = int((1.0 - su.y) * ns)
                    if 0 <= sx_ < ns and 0 <= sy_ < ns:
                        st_s = dimg_s.get_gray(sx_, sy_)
                        gap = (su.z - st_s) * args_probe.depth
                        cpu = 'SHADOW' if gap > 0.18 else 'lit'
                gpu = 'SHADOW' if gpu_term < 0.4 else 'lit'
                mark = '' if cpu == gpu or cpu == '?' else '   <<< DISAGREE'
                print(f'    [m15-sweep] t={tt:5.1f} gap={gap:+7.2f} '
                      f'CPU={cpu:6s} GPU={gpu:6s} (term {gpu_term:.2f})'
                      f'{mark}')
            pipeline.set_debug_lighting(0)
            h.step(1)
            # mode 15's fixed sample: the t=1.5m umbra point (must read
            # SHADOW = black frame if every draw samples the true map)
            sun_np_ = pipeline.sun_light_np
            w2l_ = p3d.LMatrix4(sun_np_.get_net_transform().get_mat())
            w2l_.invert_in_place()
            biasm_ = p3d.LMatrix4(0.5, 0, 0, 0, 0, 0.5, 0, 0,
                                  0, 0, 0.5, 0, 0.5, 0.5, 0.5, 1)
            m_ = w2l_ * sun_np_.node().get_lens().get_projection_mat() * biasm_
            if actor_np is not None:
                hn_ = p3d.Vec3(sun_dir.x, sun_dir.y, 0)
                hn_.normalize()
                up_ = m_.xform_point(p3d.Point3(
                    apos.x - hn_.x * 1.5, apos.y - hn_.y * 1.5, apos.z))
                base.render.set_shader_input(
                    'u_probe_uvref', p3d.Vec3(up_.x, up_.y, up_.z))
            for mode in (12, 13, 14, 15, 16):
                pipeline.set_debug_lighting(mode)
                step_fn(2)
                mimg = h.capture()
                mimg.write(p3d.Filename.from_os_specific(os.path.join(
                    common.OUTPUT_DIR,
                    f'owscale_{tag}_m{mode}_a{alt:.0f}_z{az:.0f}.png')))
                if mode == 14:
                    # consecutive-frame pair: does the sampled-map state
                    # alternate frame to frame?
                    h.step(1)
                    mb = h.capture()
                    mb.write(p3d.Filename.from_os_specific(os.path.join(
                        common.OUTPUT_DIR,
                        f'owscale_{tag}_m14b_a{alt:.0f}_z{az:.0f}.png')))
                    ndiff = 0
                    for yy in range(0, h.win_h, 3):
                        for xx in range(0, h.win_w, 3):
                            c1 = mimg.get_xel(xx, yy)
                            c2 = mb.get_xel(xx, yy)
                            if (abs(c1[0] - c2[0]) + abs(c1[1] - c2[1])
                                    + abs(c1[2] - c2[2])) > 0.3:
                                ndiff += 1
                    print(f'    [m14-pair] {ndiff} of '
                          f'{(h.win_h // 3) * (h.win_w // 3)} sampled px '
                          f'changed between consecutive frames')
            pipeline.set_debug_lighting(0)

            depth_tex = common.find_light_depth_texture(pipeline.sun_light_np)
            if depth_tex is not None:
                dimg = common.read_depth_image(base, depth_tex)
                if dimg is not None:
                    dimg.write(p3d.Filename.from_os_specific(os.path.join(
                        common.OUTPUT_DIR,
                        f'owscale_{tag}_depth_a{alt:.0f}_z{az:.0f}.png')))
                    # Map-check: project the KNOWN box top through the same
                    # world->UV matrix the receiver uses (proven exact by
                    # mode 12) and compare against where the box actually
                    # landed in the extracted map.
                    sun_np = pipeline.sun_light_np
                    w2l = p3d.LMatrix4(sun_np.get_net_transform().get_mat())
                    w2l.invert_in_place()
                    biasm = p3d.LMatrix4(0.5, 0, 0, 0, 0, 0.5, 0, 0,
                                         0, 0, 0.5, 0, 0.5, 0.5, 0.5, 1)
                    m = w2l * sun_np.node().get_lens().get_projection_mat() \
                        * biasm
                    top = p3d.Point3(box_center.x, box_center.y,
                                     box_center.z + 4.0)
                    uvw = m.xform_point(top)
                    n = dimg.get_x_size()
                    tx, ty = int(uvw.x * n), int((1.0 - uvw.y) * n)
                    if 0 <= tx < n and 0 <= ty < n:
                        stored = dimg.get_gray(tx, ty)
                        # brute search: darkest 5x5 mean in a +-400 window
                        best, bx, by = 1e9, -1, -1
                        for yy in range(max(2, ty - 400), min(n - 3, ty + 400), 3):
                            for xx in range(max(2, tx - 400), min(n - 3, tx + 400), 3):
                                s = 0.0
                                for dy2 in (-2, 0, 2):
                                    for dx2 in (-2, 0, 2):
                                        s += dimg.get_gray(xx + dx2, yy + dy2)
                                if s < best:
                                    best, bx, by = s, xx, yy
                        texel_m = 2.0 * args_probe.radius / n
                        print(f'    [map-check] box-top ref={uvw.z:.4f} '
                              f'stored@pred={stored:.4f} '
                              f'(diff {(stored - uvw.z) * args_probe.depth:+.2f} m along ray)')
                        print(f'    [map-check] darkest blob offset '
                              f'({(bx - tx) * texel_m:+.1f}, {(by - ty) * texel_m:+.1f}) m '
                              f'(texels {bx - tx:+d},{by - ty:+d}), '
                              f'depth {best / 9.0:.4f}')
                    else:
                        print(f'    [map-check] box-top UV out of map: '
                              f'({uvw.x:.3f}, {uvw.y:.3f})')
                    # footprint-length: stored depth along the anti-sun
                    # line THROUGH THE BOX, relative to the card-plane ref
                    # at each point. Strongly negative = caster footprint;
                    # ~0 = ground. Analytic footprint length =
                    # 8m (box) + 8m/tan(alt) beyond the far base edge.
                    hnf = p3d.Vec3(sun_dir.x, sun_dir.y, 0)
                    hnf.normalize()
                    frow = []
                    for step in range(-6, 50):
                        tt = step * 0.5
                        fp = p3d.Point3(box_center.x - hnf.x * tt,
                                        box_center.y - hnf.y * tt,
                                        card_z + 0.05)
                        fu = m.xform_point(fp)
                        fx = int(fu.x * n)
                        fy = int((1.0 - fu.y) * n)
                        if 0 <= fx < n and 0 <= fy < n:
                            dv = (dimg.get_gray(fx, fy) - fu.z) \
                                * args_probe.depth
                            frow.append('#' if dv < -2.0
                                        else ('x' if dv < -0.5 else '.'))
                        else:
                            frow.append('?')
                    print(f'    [box-footprint anti-sun, 0.5m steps from '
                          f'-3m] {"".join(frow)}')
                    print(f'    [box-footprint] analytic: # from -3m to '
                          f'+{4 + 8 / math.tan(math.radians(alt)):.1f}m')
                    if actor_np is not None:
                        # cross-profile: stored depth at t=1.5 m sampled
                        # ACROSS the umbra column (perpendicular offsets).
                        # A healthy body column is ~5 texels (~0.35 m) of
                        # shallow (caster) depth; a 1-texel line means the
                        # map footprint itself is emaciated.
                        hnp = p3d.Vec3(-sun_dir.y, sun_dir.x, 0)
                        hnp.normalize()
                        hnc = p3d.Vec3(sun_dir.x, sun_dir.y, 0)
                        hnc.normalize()
                        base_pt = p3d.Point3(apos.x - hnc.x * 1.5,
                                             apos.y - hnc.y * 1.5, apos.z)
                        prof = []
                        for k in range(-8, 9):
                            off = k * 0.07
                            pp = p3d.Point3(base_pt.x + hnp.x * off,
                                            base_pt.y + hnp.y * off,
                                            base_pt.z)
                            pu = m.xform_point(pp)
                            px_ = int(pu.x * n)
                            py_ = int((1.0 - pu.y) * n)
                            if 0 <= px_ < n and 0 <= py_ < n:
                                st_ = dimg.get_gray(px_, py_)
                                prof.append(
                                    'X' if pu.z - 0.0003 > st_ else '.')
                            else:
                                prof.append('?')
                        print(f'    [cross-profile t=1.5m, 7cm steps] '
                              + ''.join(prof)
                              + '  (X=shadowed texel, .=lit)')
                        # numeric compare along the expected umbra: sample
                        # stored-vs-ref at points 0.5..3.0 m from the feet
                        # along the anti-sun direction (torso shadow), at
                        # ground level.
                        hnn = p3d.Vec3(sun_dir.x, sun_dir.y, 0)
                        hnn.normalize()
                        print('    [umbra] t(m)  ref     stored  '
                              '(stored-ref)*depth_m  verdict(bias 0.18)')
                        for t in (0.5, 1.0, 1.5, 2.0, 3.0):
                            gp = p3d.Point3(apos.x - hnn.x * t,
                                            apos.y - hnn.y * t, apos.z)
                            guv = m.xform_point(gp)
                            gx = int(guv.x * n)
                            gy = int((1.0 - guv.y) * n)
                            if 0 <= gx < n and 0 <= gy < n:
                                st = dimg.get_gray(gx, gy)
                                d_m = (st - guv.z) * args_probe.depth
                                verdict = ('SHADOW' if guv.z - 0.0003 > st
                                           else 'lit')
                                print(f'    [umbra] {t:4.1f}  {guv.z:.4f}  '
                                      f'{st:.4f}  {d_m:+8.2f}  {verdict}')
                        actor_np.detach_node()
                        step_fn(3)
                        map0 = common.read_depth_image(base, depth_tex)
                        actor_np.reparent_to(base.render)
                        step_fn(3)
                        map1 = common.read_depth_image(base, depth_tex)
                        texels = common.count_gray_diff(map0, map1)
                        auv = m.xform_point(
                            p3d.Point3(apos.x, apos.y, apos.z + 0.9))
                        # centroid of changed texels
                        cx = cy = cnt = 0
                        for yy in range(0, n, 2):
                            for xx in range(0, n, 2):
                                if abs(map0.get_gray(xx, yy)
                                       - map1.get_gray(xx, yy)) > 0.001:
                                    cx += xx
                                    cy += yy
                                    cnt += 1
                        if cnt:
                            cx, cy = cx / cnt, cy / cnt
                            pu, pv = auv.x * n, (1.0 - auv.y) * n
                            texel_m = 2.0 * args_probe.radius / n
                            print(f'    [actor] {texels} depth texels; '
                                  f'centroid offset from predicted '
                                  f'({(cx - pu) * texel_m:+.1f}, '
                                  f'{(cy - pv) * texel_m:+.1f}) m')
                        else:
                            print(f'    [actor] {texels} depth texels '
                                  f'(NO CHANGED TEXELS FOUND)')

            pipeline.set_enable_shadows(False)
            h.step(4)
            img2 = h.capture()
            offl = common.avg_lum(img2, spx[0], spx[1], half=3) if spx else -1
            pipeline.set_enable_shadows(True)
            h.step(2)

            ratio = on / max(offl, 1e-4)
            verdict = 'SHADOW' if ratio < 0.6 else '*** NO SHADOW ***'
            print(f'{alt:>5.0f} {az:>5.0f} | {offl:6.3f} {on:6.3f} '
                  f'{ratio:6.2f} | {frac:7.3f} | {verdict}')


if __name__ == '__main__':
    main()
