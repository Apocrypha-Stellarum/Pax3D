"""Auxiliary snapshot camera — one-shot full-pipeline renders from an
arbitrary pose (2026-07-27, the paxcraft "photo mode" ask; Session AJ).

`Pipeline.render_snapshot(pos, hpr, size)` renders ONE frame of the
scene — PBR, shadows, atmosphere, SSAO, bloom, lens flare, tonemap —
from any camera pose into an offscreen buffer at any resolution, and
returns the result as a RAM-backed Texture, WITHOUT perturbing the
player's view. The driving use case is the voxel game's AI-building
loop (an AI screenshots its own build and iterates — Phase C of their
prime directive); the same machinery is photo mode / kill-cam for
planetside, per the keep-the-apps-concordant policy.

How it works: this module owns a PERSISTENT mirror of the pipeline's
post chain (scene HDR buffer -> optional SSAO pair -> optional bloom
extract/down/up + flare -> tonemap into an 8-bit RTM_copy_ram buffer),
built lazily at the requested size and kept for repeat shots (the AI
loop takes many). All snapshot buffers stay INACTIVE except during
render(): the call deactivates the player chain (window + FilterManager
buffers + visibility-query buffer), activates the snapshot chain,
renders one engine frame, and restores everything. The player's window
simply keeps its last presented image for that frame — no flicker, no
temporal-state pollution (the snapshot chain has no TAA and its own
history-free buffers). Repeat-shot cost is one extra rendered frame.

The scene is shared, so scene-graph state renders as-is. Camera-coupled
state is handled per shot:

- `camera_world_position` (IBL reflections, atmosphere) is pushed for
  the snapshot pose and restored.
- Orbital-atmosphere quads are re-placed for the snapshot pose and
  restored.
- The light-halo viewport-height uniform tracks the snapshot size.
- Under log depth the shader coefficient tracks the snapshot far plane.

THE SHADOW EXTENT CONTRACT (the coupling the filing flagged): games
recentre the sun's shadow frustum on the main camera, so a snapshot far
from the player would see absent shadow coverage. Either recentre it
yourself before the call (set_shadow_extent, restore after), or pass
`shadow_center=` (usually the snapshot pos) / `shadow_extent=` and the
pipeline recentres for the one frame and restores exactly.

Known limits (documented, not defended by gates):
- Registered aux scene cameras (sky-background pattern) are replicated
  onto the snapshot buffer at their sorts. Cameras registered with
  follow='pose'/'hpr' (Session AK) are re-aimed to the SNAPSHOT pose
  for the one frame and restored — photo tours get the right
  background for free. Cameras WITHOUT follow keep their game-owned
  transforms: a hand-slaved sky camera renders the main view's sky
  orientation unless the game re-aims it for the shot.
- The viewmodel is excluded (photo mode does not show the player's
  hands from a third-person pose).
- App-owned buffers outside the pipeline chain stay active and render
  one extra frame during the snapshot.
"""

import math

import panda3d.core as p3d

from . import shaderutils

# Snapshot buffers sort far above the player chain (FilterManager
# buffers sit at -9.., the sun shadow buffer below them). Ordering only
# matters among simultaneously ACTIVE buffers: during a snapshot frame
# the player chain is off and the shadow buffer (negative sort) renders
# first, then the snapshot chain in this order.
_SORT_SCENE = 8000
_SORT_SSAO = 8010
_SORT_SSAO_BLUR = 8011
_SORT_EXTRACT = 8020
_SORT_DOWN = 8030       # + level index
_SORT_UP = 8050         # + level index
_SORT_FLARE = 8070
_SORT_TONEMAP = 8080

_MIP_TINTS = [
    p3d.LVecBase3(1.0, 1.0, 1.0),
    p3d.LVecBase3(1.0, 0.95, 0.9),
    p3d.LVecBase3(0.95, 0.95, 1.0),
    p3d.LVecBase3(1.0, 0.9, 0.85),
    p3d.LVecBase3(0.9, 0.95, 1.0),
]


def _clamp_size(size):
    w, h = int(size[0]), int(size[1])
    return max(8, min(8192, w)), max(8, min(8192, h))


class SnapshotRenderer:
    """Owns the pipeline's snapshot chain. Internal — use
    Pipeline.render_snapshot() / Pipeline.release_snapshot_resources().
    """

    def __init__(self, pipeline):
        self.pl = pipeline
        self._buffers = []      # every GraphicsOutput we created
        self._roots = []        # post-pass scene roots (kept referenced)
        self._signature = None
        self._scene_buf = None
        self._scene_tex = None
        self._depth_tex = None
        self._final_tex = None
        self._cam_np = None
        self._aux_regions = []
        self._ssao_quad = None
        self._ssao_blur_quad = None
        self._extract_quad = None
        self._flare_quad = None
        self._tonemap_quad = None

    # ------------------------------------------------------------------
    # Chain construction
    # ------------------------------------------------------------------

    def _config_signature(self, size):
        pl = self.pl
        flare = pl.enable_lens_flare and pl.enable_bloom
        return (size, pl.msaa_samples, pl.enable_bloom, pl.bloom_levels,
                flare, pl.enable_ssao, pl.ao_samples, pl.enable_log_depth)

    def _make_buffer(self, name, w, h, tex, sort, float_color=False,
                     to_ram=False, fbp=None):
        pl = self.pl
        if fbp is None and float_color:
            fbp = p3d.FrameBufferProperties()
            fbp.float_color = True
            fbp.set_rgba_bits(16, 16, 16, 16)
        buf = pl.window.make_texture_buffer(name, w, h, tex, to_ram, fbp)
        if buf is None:
            raise RuntimeError(f'[Pax3DRender] snapshot buffer '
                               f'"{name}" creation failed')
        buf.set_sort(sort)
        buf.set_active(False)
        self._buffers.append(buf)
        return buf

    def _float_tex(self, name):
        tex = p3d.Texture(name)
        tex.set_format(p3d.Texture.F_rgba16)
        tex.set_component_type(p3d.Texture.T_float)
        tex.set_wrap_u(p3d.SamplerState.WM_clamp)
        tex.set_wrap_v(p3d.SamplerState.WM_clamp)
        tex.set_minfilter(p3d.SamplerState.FT_linear)
        tex.set_magfilter(p3d.SamplerState.FT_linear)
        return tex

    def _make_post_pass(self, name, w, h, sort, shader,
                        float_color=False, to_ram=False):
        """A fullscreen-quad pass into its own buffer (the
        _build_vis_query_pass pattern — FilterManager is bound to the
        window, so the snapshot chain hand-rolls its quads)."""
        if float_color:
            tex = self._float_tex(name)
        else:
            tex = p3d.Texture(name)
            tex.set_wrap_u(p3d.SamplerState.WM_clamp)
            tex.set_wrap_v(p3d.SamplerState.WM_clamp)
        buf = self._make_buffer(name, w, h, tex, sort,
                                float_color=float_color, to_ram=to_ram)
        root = p3d.NodePath(name + '_root')
        cm = p3d.CardMaker(name + '_card')
        cm.set_frame(-1, 1, -1, 1)
        quad = root.attach_new_node(cm.generate())
        quad.set_two_sided(True)
        quad.set_depth_test(False)
        quad.set_depth_write(False)
        quad.set_shader(shader)
        cam = p3d.Camera(name + '_cam')
        lens = p3d.OrthographicLens()
        lens.set_film_size(2, 2)
        lens.set_near_far(-10, 10)
        cam.set_lens(lens)
        cam_np = root.attach_new_node(cam)
        cam_np.set_pos(0, -5, 0)
        dr = buf.make_display_region()
        dr.set_camera(cam_np)
        self._roots.append(root)
        return tex, quad, buf

    def _build_chain(self, size):
        self.release()
        pl = self.pl
        w, h = size
        self._signature = self._config_signature(size)

        # 1. Scene -> RGBA16F buffer (the main chain's recipe: float
        # fbprops are the fact-#3 discipline, msaa mirrors the pipeline)
        fbprops = p3d.FrameBufferProperties()
        fbprops.float_color = True
        fbprops.srgb_color = False
        fbprops.set_rgba_bits(16, 16, 16, 16)
        fbprops.set_depth_bits(24)
        fbprops.set_multisamples(pl.msaa_samples)
        scene_tex = self._float_tex('pax3d_snapshot_hdr')
        try:
            scene_buf = self._make_buffer('pax3d_snapshot_scene', w, h,
                                          scene_tex, _SORT_SCENE,
                                          fbp=fbprops)
        except RuntimeError:
            # Some drivers refuse multisampled texture buffers — retry
            # aliasing-only rather than failing the feature.
            fbprops.set_multisamples(0)
            scene_buf = self._make_buffer('pax3d_snapshot_scene', w, h,
                                          scene_tex, _SORT_SCENE,
                                          fbp=fbprops)
        depth_tex = None
        if pl.enable_ssao:
            depth_tex = p3d.Texture('pax3d_snapshot_depth')
            depth_tex.set_wrap_u(p3d.SamplerState.WM_clamp)
            depth_tex.set_wrap_v(p3d.SamplerState.WM_clamp)
            depth_tex.set_minfilter(p3d.SamplerState.FT_nearest)
            depth_tex.set_magfilter(p3d.SamplerState.FT_nearest)
            scene_buf.add_render_texture(
                depth_tex, p3d.GraphicsOutput.RTM_bind_or_copy,
                p3d.GraphicsOutput.RTP_depth)
        self._scene_buf = scene_buf
        self._scene_tex = scene_tex
        self._depth_tex = depth_tex

        # The snapshot camera (world pose set per shot). Sees what the
        # main camera sees minus the viewmodel bit (mask refreshed per
        # shot).
        cam = p3d.Camera('pax3d_snapshot_camera')
        cam.set_lens(p3d.PerspectiveLens())
        self._cam_np = pl.render_node.attach_new_node(cam)
        dr = scene_buf.make_display_region()
        dr.set_sort(0)
        dr.set_camera(self._cam_np)
        self._scene_dr = dr

        texel = p3d.LVecBase2(1.0 / max(1, w), 1.0 / max(1, h))

        # 2. SSAO pair (mirrors the main chain: 8-bit AO is deliberate)
        ao_result_tex = None
        self._ssao_quad = None
        self._ssao_blur_quad = None
        if pl.enable_ssao:
            ssao_defines = {
                'LOG_DEPTH': pl.enable_log_depth,
                'AO_SAMPLES': pl.ao_samples,
            }
            ao_raw_tex, ssao_quad, _b = self._make_post_pass(
                'pax3d_snapshot_ssao', w, h, _SORT_SSAO,
                shaderutils.make_shader('ssao', 'post.vert', 'ssao.frag',
                                        ssao_defines))
            ssao_quad.set_shader_input('depth_tex', depth_tex)
            ssao_quad.set_shader_input('u_texel', texel)
            self._ssao_quad = ssao_quad
            ao_tex, blur_quad, _b = self._make_post_pass(
                'pax3d_snapshot_ssao_blur', w, h, _SORT_SSAO_BLUR,
                shaderutils.make_shader('ssao_blur', 'post.vert',
                                        'ssao_blur.frag', {}))
            blur_quad.set_shader_input('ao_tex', ao_raw_tex)
            blur_quad.set_shader_input('u_texel', texel)
            self._ssao_blur_quad = blur_quad
            ao_result_tex = ao_tex

        # 3. Bloom chain + flare (structure mirrors _setup_tonemapping)
        bloom_result_tex = None
        flare_result_tex = None
        self._extract_quad = None
        self._flare_quad = None
        flare_active = pl.enable_lens_flare and pl.enable_bloom
        if pl.enable_bloom:
            num_levels = pl.bloom_levels
            extract_tex, extract_quad, _b = self._make_post_pass(
                'pax3d_snapshot_bloom_extract', w, h, _SORT_EXTRACT,
                shaderutils.make_shader('bloom_extract', 'post.vert',
                                        'bloom_extract.frag', {}),
                float_color=True)
            extract_quad.set_shader_input('scene_tex', scene_tex)
            self._extract_quad = extract_quad

            down_textures = [extract_tex]
            down_quads = []
            for i in range(num_levels):
                div = 2 ** (i + 1)
                tex, quad, _b = self._make_post_pass(
                    f'pax3d_snapshot_bloom_down_{i}',
                    max(1, w // div), max(1, h // div), _SORT_DOWN + i,
                    shaderutils.make_shader('bloom_down', 'post.vert',
                                            'bloom_downsample.frag', {}),
                    float_color=True)
                quad.set_shader_input('src_tex', down_textures[-1])
                src_w = max(1, w // (2 ** i))
                src_h = max(1, h // (2 ** i))
                quad.set_shader_input('texel_size', p3d.LVecBase2(
                    1.0 / src_w, 1.0 / src_h))
                down_textures.append(tex)
                down_quads.append(quad)

            up_tex = down_textures[-1]
            for i in range(num_levels):
                src_idx = len(down_textures) - 2 - i
                remaining = num_levels - 1 - i
                div = 2 ** remaining if remaining > 0 else 1
                tex, quad, _b = self._make_post_pass(
                    f'pax3d_snapshot_bloom_up_{i}',
                    max(1, w // div), max(1, h // div), _SORT_UP + i,
                    shaderutils.make_shader('bloom_up', 'post.vert',
                                            'bloom_upsample.frag', {}),
                    float_color=True)
                quad.set_shader_input('src_tex', down_textures[src_idx])
                quad.set_shader_input('bloom_accum_tex', up_tex)
                accum_w = max(1, w // (2 ** (src_idx + 1)))
                accum_h = max(1, h // (2 ** (src_idx + 1)))
                quad.set_shader_input('texel_size', p3d.LVecBase2(
                    1.0 / accum_w, 1.0 / accum_h))
                quad.set_shader_input(
                    'mip_tint', _MIP_TINTS[i % len(_MIP_TINTS)])
                up_tex = tex
            bloom_result_tex = up_tex

            if flare_active:
                src_idx = min(2, len(down_textures) - 1)
                flare_tex, flare_quad, _b = self._make_post_pass(
                    'pax3d_snapshot_flare',
                    max(1, w // 2), max(1, h // 2), _SORT_FLARE,
                    shaderutils.make_shader('lens_flare', 'post.vert',
                                            'lens_flare.frag', {}),
                    float_color=True)
                flare_quad.set_shader_input('src_tex',
                                            down_textures[src_idx])
                self._flare_quad = flare_quad
                flare_result_tex = flare_tex

        # 4. Tonemap into the readback buffer (8-bit + RTM_copy_ram)
        tonemap_defines = {
            'ENABLE_BLOOM': pl.enable_bloom,
            'ENABLE_SSAO': pl.enable_ssao,
            'ENABLE_LENS_FLARE': flare_active,
        }
        final_tex, tonemap_quad, _b = self._make_post_pass(
            'pax3d_snapshot_out', w, h, _SORT_TONEMAP,
            shaderutils.make_shader('tonemap', 'post.vert',
                                    'tonemap.frag', tonemap_defines),
            to_ram=True)
        tonemap_quad.set_shader_input('tex', scene_tex)
        if bloom_result_tex is not None:
            tonemap_quad.set_shader_input('bloom_tex', bloom_result_tex)
        if ao_result_tex is not None:
            tonemap_quad.set_shader_input('ao_tex', ao_result_tex)
        if flare_result_tex is not None:
            tonemap_quad.set_shader_input('flare_tex', flare_result_tex)
        self._tonemap_quad = tonemap_quad
        self._final_tex = final_tex

    # ------------------------------------------------------------------
    # Per-shot state
    # ------------------------------------------------------------------

    def _push_lens_inputs(self, quad, lens):
        """The SSAO position-reconstruction inputs, from the SNAPSHOT
        lens (the pipeline's own pusher reads the main camera lens)."""
        fov = lens.get_fov()
        quad.set_shader_input('u_proj_tan', p3d.LVecBase2(
            math.tan(math.radians(fov[0]) * 0.5),
            math.tan(math.radians(fov[1]) * 0.5)))
        quad.set_shader_input('u_near_far', p3d.LVecBase2(
            lens.get_near(), lens.get_far()))
        far = max(2.0, lens.get_far())
        quad.set_shader_input('u_log_depth_coef',
                              1.0 / math.log2(1.0 + far))

    def _push_shot_uniforms(self, lens):
        """Current pipeline parameter values onto the snapshot quads
        (they are runtime-settable pipeline-side, so push per shot)."""
        pl = self.pl
        if self._ssao_quad is not None:
            self._ssao_quad.set_shader_input('u_ao_radius', pl.ao_radius)
            self._ssao_quad.set_shader_input('u_ao_intensity',
                                             pl.ao_intensity)
            self._ssao_quad.set_shader_input('u_ao_bias', pl.ao_bias)
            self._push_lens_inputs(self._ssao_quad, lens)
        if self._extract_quad is not None:
            self._extract_quad.set_shader_input('bloom_strength',
                                                pl.bloom_strength)
        if self._flare_quad is not None:
            pl._apply_lens_dirt_inputs(self._flare_quad)
        quad = self._tonemap_quad
        quad.set_shader_input('exposure', 2 ** pl.exposure)
        from .pipeline import _TONEMAP_OPERATORS
        quad.set_shader_input('tonemap_operator',
                              _TONEMAP_OPERATORS.get(pl.tonemap_operator,
                                                     0))
        if pl.enable_bloom:
            quad.set_shader_input('bloom_intensity', pl.bloom_intensity)
        if self._flare_quad is not None:
            quad.set_shader_input('u_flare_strength', pl.flare_strength)
        pl._apply_warp_distortion_inputs(quad)

    def _sync_aux_regions(self):
        """Replicate registered aux scene cameras (the sky-background
        pattern) onto the snapshot scene buffer, mirroring
        _attach_scene_camera clears. Regions are rebuilt per shot (the
        registration list is tiny and can change any time). Viewmodels
        are excluded by design."""
        for dr in self._aux_regions:
            self._scene_buf.remove_display_region(dr)
        self._aux_regions = []
        has_background = False
        for reg in self.pl._scene_cameras:
            if getattr(reg, 'is_viewmodel', False):
                continue
            if reg.camera_np is None or reg.camera_np.is_empty():
                continue
            dr = self._scene_buf.make_display_region()
            dr.set_sort(reg.sort)
            dr.set_camera(reg.camera_np)
            if reg.clear_color is not None:
                dr.set_clear_color_active(True)
                dr.set_clear_color(p3d.LColor(*reg.clear_color))
            dr.set_clear_depth_active(reg.clear_depth)
            self._aux_regions.append(dr)
            if reg.sort < 0:
                has_background = True
        # Main-region clears mirror _update_main_region_clears
        self._scene_dr.set_clear_color_active(False)
        self._scene_dr.set_clear_depth_active(has_background)

    # ------------------------------------------------------------------
    # The shot
    # ------------------------------------------------------------------

    def render(self, pos, hpr, size=(1280, 720), fov=None, near=None,
               far=None, shadow_center=None, shadow_extent=None,
               filename=None):
        pl = self.pl
        size = _clamp_size(size)
        if self._signature != self._config_signature(size):
            self._build_chain(size)

        # Lens: defaults copy the main camera (so log-depth games get
        # their wide frustum without thinking about it)
        main_lens = pl.camera_node.node().get_lens()
        lens = self._cam_np.node().get_lens()
        lens.set_aspect_ratio(size[0] / float(size[1]))
        if fov is not None:
            lens.set_fov(float(fov))
        elif isinstance(main_lens, p3d.PerspectiveLens):
            lens.set_fov(main_lens.get_fov()[0])
        else:
            lens.set_fov(50.0)
        lens.set_near_far(
            near if near is not None else main_lens.get_near(),
            far if far is not None else main_lens.get_far())

        vm_bit = p3d.DrawMask.bit(pl.VIEWMODEL_BIT)
        self._cam_np.node().set_camera_mask(
            p3d.DrawMask(pl.camera_node.node().get_camera_mask())
            & ~vm_bit)
        self._cam_np.set_pos(p3d.Vec3(*pos))
        self._cam_np.set_hpr(p3d.VBase3(*hpr))

        self._sync_aux_regions()
        self._scene_buf.set_clear_color(pl.window.get_clear_color())
        self._push_shot_uniforms(lens)

        # Camera-coupled scene state -> snapshot pose (restored below)
        snap_pos = p3d.Vec3(*pos)
        main_cam_pos = pl.camera_node.get_pos(pl.render_node)
        pl.render_node.set_shader_input('camera_world_position', snap_pos)
        # Follow cameras (Session AK): aim the aux background cameras at
        # the snapshot pose for this one frame (restored in finally).
        saved_follow = []
        snap_hpr = p3d.VBase3(*hpr)
        for reg in pl._scene_cameras:
            if (getattr(reg, 'follow', None) is None
                    or getattr(reg, 'is_viewmodel', False)
                    or reg.camera_np is None or reg.camera_np.is_empty()):
                continue
            saved_follow.append((reg, p3d.Vec3(reg.camera_np.get_pos()),
                                 p3d.VBase3(reg.camera_np.get_hpr())))
            if reg.follow == 'pose':
                reg.camera_np.set_pos(snap_pos)
            reg.camera_np.set_hpr(snap_hpr)
        if pl._orbital_atmos:
            pl._update_orbital_atmos(snap_pos)
        if pl._halo_nodes:
            pl.render_node.set_shader_input('u_halo_vp_h',
                                            float(size[1]))
        if pl.enable_log_depth:
            snap_far = max(2.0, lens.get_far())
            pl.render_node.set_shader_input(
                'u_log_depth_coef', 1.0 / math.log2(1.0 + snap_far))

        # The shadow-extent contract: optional one-frame recentre
        saved_shadow = None
        if shadow_center is not None or shadow_extent is not None:
            saved_shadow = (pl._shadow_extent, pl._shadow_depth,
                            p3d.Vec3(pl._shadow_center))
            pl.set_shadow_extent(
                shadow_extent if shadow_extent is not None
                else pl._shadow_extent,
                center=shadow_center)

        # Swap active outputs: player chain off, snapshot chain on
        player_outputs = [pl.window]
        player_outputs.extend(getattr(pl._filtermgr, 'buffers', []))
        if pl._vis_buffer is not None:
            player_outputs.append(pl._vis_buffer)
        reactivate = []
        try:
            for out in player_outputs:
                if out.is_active():
                    out.set_active(False)
                    reactivate.append(out)
            for buf in self._buffers:
                buf.set_active(True)
            pl.window.get_engine().render_frame()
        finally:
            for buf in self._buffers:
                buf.set_active(False)
            for out in reactivate:
                out.set_active(True)
            if saved_shadow is not None:
                pl.set_shadow_extent(saved_shadow[0],
                                     depth=saved_shadow[1],
                                     center=saved_shadow[2])
            for reg, f_pos, f_hpr in saved_follow:
                if reg.camera_np is not None \
                        and not reg.camera_np.is_empty():
                    reg.camera_np.set_pos(f_pos)
                    reg.camera_np.set_hpr(f_hpr)
            pl.render_node.set_shader_input('camera_world_position',
                                            main_cam_pos)
            if pl._orbital_atmos:
                pl._update_orbital_atmos(main_cam_pos)
            if pl._halo_nodes:
                pl.render_node.set_shader_input(
                    'u_halo_vp_h',
                    float(max(1, pl.window.get_y_size())))
            if pl.enable_log_depth:
                main_far = max(2.0, main_lens.get_far())
                pl.render_node.set_shader_input(
                    'u_log_depth_coef', 1.0 / math.log2(1.0 + main_far))

        tex = self._final_tex
        if filename is not None:
            tex.write(p3d.Filename.from_os_specific(str(filename)))
        return tex

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def release(self):
        """Destroy every snapshot buffer/camera. Safe to call twice;
        the next render() lazily rebuilds."""
        engine = self.pl.window.get_engine()
        for buf in self._buffers:
            engine.remove_window(buf)
        self._buffers = []
        self._roots = []
        self._aux_regions = []
        if self._cam_np is not None and not self._cam_np.is_empty():
            self._cam_np.remove_node()
        self._cam_np = None
        self._scene_buf = None
        self._scene_tex = None
        self._depth_tex = None
        self._final_tex = None
        self._ssao_quad = None
        self._ssao_blur_quad = None
        self._extract_quad = None
        self._flare_quad = None
        self._tonemap_quad = None
        self._signature = None
