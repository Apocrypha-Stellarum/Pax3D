"""Pax3D Render Pipeline (Phase R1 of PAX3D_MASTER_PLAN.md).

The unified first-party renderer for Pax3D — the merge of:
  - sfb2/graphics/pax_pbr (the game's battle-tested fork of simplepbr 0.13.1:
    custom sun uniforms, debug modes, Kawase bloom, multi-operator tonemap,
    TAA), and
  - pax3d_simplepbr (this repo's earlier fork — now retired).

Behavior is intentionally byte-identical to the game's pax_pbr as of
July 2026, plus the following R1 additions:

  * register_scene_camera() / unregister_scene_camera() — auxiliary display
    regions (e.g. the sky camera) are owned by the pipeline and re-created
    automatically on every internal rebuild (bloom/TAA toggles). This
    replaces the fragile pattern of external code searching for the
    FilterManager buffer once at init (fixes failure F4).
  * Legacy-GL warning — GLSL 120 mode still works but is deprecated;
    the target baseline is `gl-version 3 2` (GLSL 330).
  * debug output controlled by PAX3D_RENDER_DEBUG env var or debug=True.

Phase R2 (sun_light_mode): the sun can now be a REAL DirectionalLight.

  * sun_light_mode='uniforms' (default) — legacy custom u_sun_dir_world /
    u_sun_color uniforms, byte-identical to the game's pax_pbr. No sun
    shadows.
  * sun_light_mode='directional' — the pipeline owns a DirectionalLight
    node ('pax3d_sun'); the PBR shader processes it through the standard
    p3d_LightSource loop (define SUN_FROM_LIGHTSOURCE), which also enables
    the simplepbr shadow-map path for the sun. update_sun() keeps the same
    signature and drives the node (orienting via HPR so the shadow camera
    and the lighting direction always agree — never set_direction(), which
    the shadow camera ignores).

Switch at runtime with set_sun_light_mode(); toggle sun shadows with
set_enable_shadows(); size the shadow frustum with set_shadow_extent().
"""
import builtins
import math
import os

import panda3d.core as p3d
from direct.filter.FilterManager import FilterManager

from . import shaderutils

_ENV_DEBUG = bool(os.environ.get('PAX3D_RENDER_DEBUG'))


# Tonemap operator name -> uniform int mapping
_TONEMAP_OPERATORS = {
    'aces': 0,
    'reinhard': 1,
    'uncharted2': 2,
    'hejl_dawson': 3,
}

# Per-mip bloom tints — warm/cool fringe for artistic bloom character
_MIP_TINTS = [
    p3d.LVecBase3(0.214, 0.429, 0.497),  # fine detail, cool
    p3d.LVecBase3(0.964, 0.947, 0.991),  # near-white
    p3d.LVecBase3(0.982, 0.542, 0.542),  # warm
    p3d.LVecBase3(0.301, 0.493, 1.000),  # blue halo
    p3d.LVecBase3(0.456, 0.209, 0.167),  # deep warm outer
]


def _set_bloom_filtering(tex):
    """Bilinear + clamp-to-edge on a bloom intermediate texture.

    The tent/box kernels sample between mismatched resolutions and assume
    this state; Panda's default wrap is repeat, which bleeds the halo
    across screen edges (part of F3).
    """
    tex.set_minfilter(p3d.SamplerState.FT_linear)
    tex.set_magfilter(p3d.SamplerState.FT_linear)
    tex.set_wrap_u(p3d.SamplerState.WM_clamp)
    tex.set_wrap_v(p3d.SamplerState.WM_clamp)


def _load_brdf_lut(debug=False):
    """Load the BRDF LUT texture for IBL specular.

    Looks for <package>/textures/brdf_lut.txo; falls back to a 1x1 white
    texture (matching the game's current behavior — the LUT only affects
    IBL specular, and env maps are not used yet).
    """
    lut_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'textures', 'brdf_lut.txo')
    if os.path.exists(lut_path):
        panda_path = p3d.Filename.from_os_specific(lut_path)
        tex = p3d.TexturePool.load_texture(panda_path)
        if tex:
            tex.wrap_u = p3d.SamplerState.WM_clamp
            tex.wrap_v = p3d.SamplerState.WM_clamp
            tex.minfilter = p3d.SamplerState.FT_linear
            tex.magfilter = p3d.SamplerState.FT_linear
            return tex

    if debug:
        print('[Pax3DRender] No brdf_lut.txo — using white fallback')
    tex = p3d.Texture('brdf_lut_fallback')
    tex.setup_2d_texture(1, 1, p3d.Texture.T_unsigned_byte, p3d.Texture.F_rgb8)
    tex.set_clear_color(p3d.LColor(1, 1, 1, 1))
    tex.wrap_u = p3d.SamplerState.WM_clamp
    tex.wrap_v = p3d.SamplerState.WM_clamp
    return tex


def sh_from_cubemap(tex, band_factors=(math.pi, 2.0 * math.pi / 3.0,
                                       math.pi / 4.0)):
    """Project a cube-map Texture to 9 irradiance-SH coefficients for
    Pipeline.set_ambient_sh() — the R5 "ambient from the skybox" path.

    EXPERIMENTAL (Session J): the face-direction table follows the standard
    GL cube-map convention with Panda's Z-up lookup vectors (face 4 = +z =
    up, face 5 = -z = down). The up/down axis and the DC term are exact;
    validate the horizontal orientation against your actual skybox before
    shipping content tuned to it. Runs on the CPU from the texture's RAM
    image (loaded skyboxes have one) — call once at scene setup, not per
    frame; cost scales with face area (a 64px cubemap is plenty for
    irradiance).

    Returns a list of 9 (r, g, b) tuples, or raises RuntimeError if a face
    cannot be read back.
    """
    size = tex.get_x_size()
    if tex.get_texture_type() != p3d.Texture.TT_cube_map or size == 0:
        raise RuntimeError('sh_from_cubemap needs a loaded cube map texture')

    # Shader basis constants, slot order [1, x, z, y, xz, yz, xy,
    # 3z^2-ish, x^2-y^2] (matches pax_pbr.frag irradiance_from_sh).
    def basis(d):
        x, y, z = d
        return (0.282095,
                0.488603 * x, 0.488603 * z, 0.488603 * y,
                1.092548 * x * z, 1.092548 * y * z, 1.092548 * y * x,
                0.946176 * z * z - 0.315392,
                0.546274 * (x * x - y * y))

    # Per-slot cosine-convolution factors (Ramamoorthi): band 0, 1, 2.
    slot_factor = (band_factors[0],) + (band_factors[1],) * 3 \
        + (band_factors[2],) * 5

    coeffs = [[0.0, 0.0, 0.0] for _ in range(9)]
    img = p3d.PNMImage()
    for face in range(6):
        if not tex.store(img, face, 0):
            raise RuntimeError(f'sh_from_cubemap: cannot read face {face}')
        n = img.get_x_size()
        for py in range(n):
            # PNM y runs down from the top; GL face t runs up.
            t = 1.0 - (py + 0.5) / n
            b = 2.0 * t - 1.0
            for px in range(n):
                s = (px + 0.5) / n
                a = 2.0 * s - 1.0
                if face == 0:
                    d = (1.0, -b, -a)      # +x
                elif face == 1:
                    d = (-1.0, -b, a)      # -x
                elif face == 2:
                    d = (a, 1.0, b)        # +y
                elif face == 3:
                    d = (a, -1.0, -b)      # -y
                elif face == 4:
                    d = (a, -b, 1.0)       # +z (up)
                else:
                    d = (-a, -b, -1.0)     # -z (down)
                r2 = a * a + b * b + 1.0
                inv_len = r2 ** -0.5
                dn = (d[0] * inv_len, d[1] * inv_len, d[2] * inv_len)
                # Texel solid angle: dA / r^3, with dA = (2/n)^2 on the
                # unit-distance cube face and r = sqrt(a^2 + b^2 + 1).
                dw = (2.0 / n) ** 2 / (r2 * r2 ** 0.5)
                c = img.get_xel(px, py)
                y_vals = basis(dn)
                for i in range(9):
                    w = y_vals[i] * dw
                    coeffs[i][0] += c[0] * w
                    coeffs[i][1] += c[1] * w
                    coeffs[i][2] += c[2] * w
    return [(coeffs[i][0] * slot_factor[i],
             coeffs[i][1] * slot_factor[i],
             coeffs[i][2] * slot_factor[i]) for i in range(9)]


class _SceneCameraRegistration:
    """Internal record of an auxiliary camera attached to the scene buffer."""

    def __init__(self, camera_np, sort, clear_color, clear_depth, name):
        self.camera_np = camera_np
        self.sort = sort
        self.clear_color = clear_color
        self.clear_depth = clear_depth
        self.name = name
        self.display_region = None
        self.buffer = None


class Pipeline:
    """Pax3D rendering pipeline.

    Drop-in replacement for sfb2's graphics.pax_pbr.Pipeline (same
    constructor signature and runtime API) with pipeline-owned auxiliary
    cameras.
    """

    def __init__(self, render_node=None, window=None, camera_node=None,
                 taskmgr=None, msaa_samples=4, max_lights=8,
                 enable_shadows=False, use_normal_maps=False,
                 use_emission_maps=True, use_occlusion_maps=False,
                 enable_fog=False, exposure=0.0, shadow_bias=0.005,
                 shadow_bias_world=None, shadow_normal_bias_world=0.0,
                 shadow_filter_size=1,
                 shadow_caster_mask=None,
                 enable_hardware_skinning=True, calculate_normalmap_blue=True,
                 enable_bloom=False, bloom_strength=1.0, bloom_intensity=1.0,
                 bloom_levels=5, tonemap_operator='aces',
                 enable_taa=False, debug=False,
                 sun_light_mode='uniforms', shadow_map_size=2048,
                 enable_log_depth=False,
                 shadow_texel_snap=False,
                 double_sided_lighting=False,
                 enable_atmosphere=False,
                 atmo_haze_color=(0.60, 0.71, 0.85),
                 atmo_sun_haze_color=None,
                 atmo_sun_power=8.0,
                 atmo_density=0.002,
                 atmo_scale_height=60.0,
                 atmo_base_height=0.0,
                 radial_blur_strength=0.0,
                 chromatic_aberration_strength=0.0,
                 radial_blur_center=(0.5, 0.5),
                 **_kwargs):
        base = builtins.base

        self.render_node = render_node or base.render
        self.window = window or base.win
        self.camera_node = camera_node or base.cam
        self.taskmgr = taskmgr or base.task_mgr
        self._debug = debug or _ENV_DEBUG

        self.msaa_samples = msaa_samples
        self.max_lights = max_lights
        self.enable_shadows = enable_shadows
        self.use_normal_maps = use_normal_maps
        self.use_emission_maps = use_emission_maps
        self.use_occlusion_maps = use_occlusion_maps
        self.enable_fog = enable_fog
        self.exposure = exposure
        # BEWARE the bias trap: shadow_bias is consumed in NORMALIZED
        # light-space depth, so its world-space size is bias * extent
        # depth. The 0.005 default is 0.3 units deep in the 60-unit test
        # frustum but 12.5 at an open-world set_shadow_extent depth of
        # 2500 (or 20 IEU at the space game's 4000) — enough to silently
        # erase every shadow shorter than a building, with no artifact
        # hinting why. Prefer shadow_bias_world (world units; wins when
        # set; rescaled automatically when the extent depth changes).
        self.shadow_bias = shadow_bias
        self.shadow_bias_world = shadow_bias_world
        # Slope-scaled (grazing-angle) bias, in WORLD units, same rescaling
        # discipline as shadow_bias_world (divided by the extent depth before
        # upload so it stays physically constant across extent changes). 0.0
        # = OFF = byte-identical to the constant-bias-only path (opt-in until
        # proven — the openworld dev A/Bs it at az 240 low sun). It adds
        # bias only where the receiver grazes the sun, so it clears open-
        # ground acne without peter-panning normal-incidence shadows.
        self.shadow_normal_bias_world = float(shadow_normal_bias_world)
        if shadow_filter_size not in (1, 3):
            print(f'[Pax3DRender] Unsupported shadow_filter_size '
                  f'{shadow_filter_size!r}, falling back to 1')
            shadow_filter_size = 1
        self.shadow_filter_size = shadow_filter_size
        self.shadow_caster_mask = self._normalize_caster_mask(
            shadow_caster_mask)
        self.enable_hardware_skinning = enable_hardware_skinning
        self.calculate_normalmap_blue = calculate_normalmap_blue
        # Double-sided lighting (Session K, asset enablement): shade
        # backfaces with the inverted normal (the glTF doubleSided /
        # Khronos sample-viewer semantic). Default off = byte-identical:
        # existing two-sided content (foliage cards, FX quads) keeps its
        # shipped look until the game opts in and signs off.
        self.double_sided_lighting = bool(double_sided_lighting)

        # Bloom and tonemapping parameters
        self.enable_bloom = enable_bloom
        self.bloom_strength = bloom_strength
        self.bloom_intensity = bloom_intensity
        self.bloom_levels = max(2, min(8, bloom_levels))
        if tonemap_operator not in _TONEMAP_OPERATORS:
            print(f'[Pax3DRender] Unknown tonemap operator '
                  f'"{tonemap_operator}", falling back to "aces"')
            tonemap_operator = 'aces'
        self.tonemap_operator = tonemap_operator
        self.enable_taa = enable_taa

        # FTL warp distortion (radial motion blur + chromatic aberration).
        # Uniform-only: 0.0 strengths = passthrough, no rebuild ever needed.
        self.radial_blur_strength = max(0.0, min(
            float(radial_blur_strength), 1.0))
        self.chromatic_aberration_strength = max(0.0, min(
            float(chromatic_aberration_strength), 1.0))
        self.radial_blur_center = (float(radial_blur_center[0]),
                                   float(radial_blur_center[1]))

        # Logarithmic depth (R4.1) — opt-in until the game adopts the wide
        # frustum. With it on, set the camera lens near/far to the real
        # scene span (e.g. 0.1 / 1e9); the pipeline tracks the lens far
        # every frame for the shader coefficient.
        self.enable_log_depth = enable_log_depth

        # Planetside package (Session J / R5.1-R5.3) — ALL opt-in; with the
        # defaults every one of these is byte-identical to the previous
        # pipeline (guarded by test_atmosphere / test_ambient_sh /
        # test_shadow_snap opt-out checks). Spaceflight scenes simply never
        # enable them.
        #
        # Shadow texel snapping: quantize the shadow-frustum center to the
        # shadow-map texel grid in the light's film plane, so a frustum that
        # follows the camera (planetside pattern) stops re-rasterizing the
        # depth map every sub-texel step — the source of edge shimmer while
        # walking. Off by default (center used exactly as given).
        self.shadow_texel_snap = bool(shadow_texel_snap)
        # Aerial perspective / height haze: exponential-height medium
        # evaluated analytically in the PBR shader (define
        # ENABLE_ATMOSPHERE, recompile-class). Parameters are uniform-only.
        self.enable_atmosphere = bool(enable_atmosphere)
        self.atmo_haze_color = tuple(atmo_haze_color)
        self.atmo_sun_haze_color = (tuple(atmo_sun_haze_color)
                                    if atmo_sun_haze_color is not None
                                    else None)
        self.atmo_sun_power = float(atmo_sun_power)
        self.atmo_density = max(0.0, float(atmo_density))
        self.atmo_scale_height = max(1e-6, float(atmo_scale_height))
        self.atmo_base_height = float(atmo_base_height)
        # Environment-driven ambient (R5): irradiance SH coefficients fed to
        # the shader's existing sh_coeffs path (zeros = off = the shipped
        # behavior). Set via set_hemisphere_ambient()/set_ambient_sh().
        self._ambient_sh = None

        # Glass nodes (set_glass): premultiplied-alpha PBR variant so
        # specular reflections survive low alpha. Entries are
        # (nodepath, saved node-local TransparencyAttrib or None, override)
        # so opt-out restores the node's prior blend state exactly.
        self._glass_nodes = []
        self._glass_shader = None

        # Sun light mode (R2)
        if sun_light_mode not in ('uniforms', 'directional'):
            print(f'[Pax3DRender] Unknown sun_light_mode "{sun_light_mode}", '
                  f'falling back to "uniforms"')
            sun_light_mode = 'uniforms'
        self.sun_light_mode = sun_light_mode
        self.shadow_map_size = shadow_map_size
        self.sun_light_np = None
        self._last_sun_dir = p3d.Vec3(0, 1, 0)
        self._last_sun_color = p3d.Vec3(1.2, 1.15, 1.0)
        self._shadow_extent = 800.0
        self._shadow_depth = 4000.0
        self._shadow_center = p3d.Vec3(0, 0, 0)

        self._is_webgl = 'WebGL' in self.window.type.name

        # Detect GLSL 330 capability
        cvar = p3d.ConfigVariableInt('gl-version')
        gl_version = [cvar.get_word(i) for i in range(cvar.get_num_words())]
        self._use_330 = (
            len(gl_version) >= 2
            and gl_version[0] >= 3
            and gl_version[1] >= 2
        )
        if not self._use_330:
            print('[Pax3DRender] WARNING: running legacy GLSL 120 path '
                  '(gl-version not set to 3 2+). This path is deprecated — '
                  'see PAX3D_MASTER_PLAN.md R1.4.')

        # Load BRDF LUT for IBL
        self._brdf_lut = _load_brdf_lut(self._debug)

        # Empty SH coefficients (no env map by default)
        self._empty_sh = p3d.PTA_LVecBase3f()
        for _ in range(9):
            self._empty_sh.push_back(p3d.LVecBase3f(0, 0, 0))

        # Empty cubemap for filtered_env_map
        self._empty_cubemap = p3d.Texture('empty_env')
        self._empty_cubemap.setup_cube_map(1, p3d.Texture.T_unsigned_byte,
                                           p3d.Texture.F_rgb8)

        # Auxiliary scene cameras (survive rebuilds) — R1 addition
        self._scene_cameras = []

        # FilterManager for tonemapping
        self._filtermgr = FilterManager(self.window, self.camera_node)
        if self._filtermgr.nextsort == -1000:
            self._filtermgr.nextsort = -9

        # Don't force power-of-two textures
        p3d.Texture.set_textures_power_2(p3d.ATS_none)

        # AA
        self.render_node.set_antialias(p3d.AntialiasAttrib.M_auto)

        # Default/fallback material
        fallback_material = p3d.Material('pax3d-render-fallback')
        self.render_node.set_material(fallback_material)

        # Create the sun DirectionalLight if requested (R2)
        if self.sun_light_mode == 'directional':
            self._create_sun_light()

        # Compile and apply PBR shader
        self._recompile_pbr()

        # Tonemapping + bloom post-process
        self._post_process_quad = None
        self._bloom_extract_quad = None
        self._bloom_down_quads = []
        self._bloom_up_quads = []
        self._setup_tonemapping()

        # Set initial sun state (safe defaults — +Y world direction).
        # Drives the uniforms and, in directional mode, the light node.
        self.update_sun(self._last_sun_dir, self._last_sun_color)

        # Limb darkening (0=off, only close sun renderer sets nonzero)
        self.render_node.set_shader_input('u_limb_darkening', 0.0)

        # Debug lighting mode (0=normal, 1=normals, 2=n_dot_l, 3=light dir)
        self.render_node.set_shader_input('u_debug_lighting', 0.0)

        # World -> light-0 shadow-UV matrix for debug modes 12/13
        # (fragment-recomputed shadow coords). Identity until a
        # directional sun exists; refreshed by update_sun and
        # set_shadow_extent.
        self.render_node.set_shader_input('u_probe_shadow_world_mat',
                                          p3d.LMatrix4.ident_mat())
        # Fixed (u, v, ref) sample point for debug mode 15.
        self.render_node.set_shader_input('u_probe_uvref',
                                          p3d.Vec3(0.5, 0.5, 0.5))

        # Coordinate system conversion for custom shader inputs
        self._init_cs_conversion()

        # Per-frame update task
        self.taskmgr.add(self._update, 'pax3d_render_update', sort=49)

        if self._debug:
            bloom_str = (f"bloom=ON strength={self.bloom_strength} "
                         f"intensity={self.bloom_intensity} "
                         f"levels={self.bloom_levels}"
                         if self.enable_bloom else "bloom=OFF")
            print(f"[Pax3DRender] Pipeline initialized ({bloom_str}, "
                  f"tonemap={self.tonemap_operator}, "
                  f"glsl={'330' if self._use_330 else '120'})")

    def _get_pbr_defines(self):
        """Build the #define dict for the PBR shader."""
        return {
            'MAX_LIGHTS': self.max_lights,
            'USE_NORMAL_MAP': self.use_normal_maps,
            'USE_EMISSION_MAP': self.use_emission_maps,
            'ENABLE_SHADOWS': self.enable_shadows,
            'ENABLE_FOG': self.enable_fog,
            'USE_OCCLUSION_MAP': self.use_occlusion_maps,
            'USE_330': self._use_330,
            'IS_WEBGL': self._is_webgl,
            'ENABLE_SKINNING': self.enable_hardware_skinning,
            'CALC_NORMAL_Z': self.calculate_normalmap_blue,
            'SUN_FROM_LIGHTSOURCE': self.sun_light_mode == 'directional',
            'LOG_DEPTH': self.enable_log_depth,
            'SHADOW_FILTER_SIZE': self.shadow_filter_size,
            'ENABLE_ATMOSPHERE': self.enable_atmosphere,
            'DOUBLE_SIDED_LIGHTING': self.double_sided_lighting,
        }

    def _recompile_pbr(self):
        """Compile and apply the PBR shader to the render node.

        Called at init AND at runtime (sun mode / shadow toggles). Must
        preserve the existing ShaderAttrib's shader INPUTS — building a
        fresh attrib would wipe every set_shader_input() made on the render
        node (sun uniforms, debug mode, camera position, ...).
        """
        defines = self._get_pbr_defines()
        pbr_shader = shaderutils.make_shader(
            'pax_pbr', 'pax_pbr.vert', 'pax_pbr.frag', defines
        )
        prev = self.render_node.get_attrib(p3d.ShaderAttrib)
        if prev is not None:
            attr = prev.set_shader(pbr_shader)  # keeps existing inputs
        else:
            attr = p3d.ShaderAttrib.make(pbr_shader)
        if self.enable_hardware_skinning:
            attr = attr.set_flag(p3d.ShaderAttrib.F_hardware_skinning, True)
        self.render_node.set_attrib(attr)
        self._push_shadow_bias()
        self._set_env_map_uniforms()
        self._push_atmosphere_uniforms()
        # Glass nodes carry a per-node variant of the PBR shader — it must
        # track every recompile (same defines + GLASS) or a runtime toggle
        # would leave glass rendering with stale defines.
        self._glass_shader = None
        self._reapply_glass_shaders()

    def _set_env_map_uniforms(self):
        """Set IBL-related shader inputs.

        sh_coeffs carries the environment-driven ambient when one is set
        (set_hemisphere_ambient / set_ambient_sh) — it must survive shader
        recompiles like every other input, so this re-pushes the CURRENT
        coefficients, not unconditionally the empty set.
        """
        sh = self._ambient_sh if self._ambient_sh is not None else self._empty_sh
        self.render_node.set_shader_input('sh_coeffs', sh)
        self.render_node.set_shader_input('brdf_lut', self._brdf_lut)
        self.render_node.set_shader_input('filtered_env_map', self._empty_cubemap)
        self.render_node.set_shader_input('max_reflection_lod', 0)

    # ------------------------------------------------------------------
    # Auxiliary scene cameras (R1 addition — replaces sky_camera's
    # find-the-buffer-once pattern)
    # ------------------------------------------------------------------

    def register_scene_camera(self, camera_np, sort=-100,
                              clear_color=(0, 0, 0, 1), clear_depth=True,
                              name='aux_scene_camera'):
        """Attach an auxiliary camera to the pipeline's scene buffer.

        The display region is owned by the pipeline and is automatically
        re-created whenever the internal FilterManager chain is rebuilt
        (bloom toggle, bloom_levels/TAA change, etc.) — external code never
        needs to locate the offscreen buffer itself.

        Args:
            camera_np: NodePath of a Camera node (caller owns lens, masks,
                       scene root, and transform).
            sort: display-region sort. Negative renders BEFORE the main
                  scene (background, e.g. a sky camera).
            clear_color: RGBA tuple to clear this region to, or None to
                         not clear color.
            clear_depth: whether this region clears depth before drawing.

        For any background camera (sort < 0), the main scene region is set
        to preserve background pixels: color clear off, depth clear on.

        Returns an opaque registration handle for unregister_scene_camera().
        """
        reg = _SceneCameraRegistration(camera_np, sort, clear_color,
                                       clear_depth, name)
        self._scene_cameras.append(reg)
        self._attach_scene_camera(reg)
        return reg

    def unregister_scene_camera(self, reg):
        """Detach an auxiliary camera previously registered."""
        if reg in self._scene_cameras:
            self._scene_cameras.remove(reg)
        if reg.display_region is not None and reg.buffer is not None:
            reg.buffer.remove_display_region(reg.display_region)
        reg.display_region = None
        reg.buffer = None
        self._update_main_region_clears()

    def _scene_buffer(self):
        buffers = getattr(self._filtermgr, 'buffers', None)
        return buffers[0] if buffers else None

    def _find_main_display_region(self):
        """The display region where the main camera renders on the buffer."""
        buf = self._scene_buffer()
        if buf is None:
            return None
        for i in range(buf.get_num_display_regions()):
            dr = buf.get_display_region(i)
            if dr.get_camera() == self.camera_node:
                return dr
        return None

    def _attach_scene_camera(self, reg):
        buf = self._scene_buffer()
        if buf is None:
            print(f'[Pax3DRender] WARNING: no scene buffer for aux camera '
                  f'"{reg.name}"')
            return
        dr = buf.make_display_region()
        dr.set_sort(reg.sort)
        dr.set_camera(reg.camera_np)
        if reg.clear_color is not None:
            dr.set_clear_color_active(True)
            dr.set_clear_color(p3d.LColor(*reg.clear_color))
        dr.set_clear_depth_active(reg.clear_depth)
        reg.display_region = dr
        reg.buffer = buf
        self._update_main_region_clears()
        if self._debug:
            print(f'[Pax3DRender] aux camera "{reg.name}" attached '
                  f'(sort={reg.sort})')

    def _update_main_region_clears(self):
        """With a background camera present, the main region must preserve
        the background's color output but still clear depth."""
        main_dr = self._find_main_display_region()
        if main_dr is None:
            return
        has_background = any(r.sort < 0 for r in self._scene_cameras)
        if has_background:
            main_dr.set_clear_color_active(False)
            main_dr.set_clear_depth_active(True)

    def _reattach_scene_cameras(self):
        """Called after every _setup_tonemapping(): old buffer (and its
        display regions) are gone; re-create them on the new buffer."""
        for reg in self._scene_cameras:
            reg.display_region = None
            reg.buffer = None
            self._attach_scene_camera(reg)

    # ------------------------------------------------------------------
    # Coordinate system conversion
    # ------------------------------------------------------------------

    def _init_cs_conversion(self):
        """Determine if custom shader inputs need coordinate system conversion.

        Panda3D internally uses Z-up right-handed coordinates. The GSG
        (OpenGL) uses Y-up right-handed. Built-in shader matrices like
        p3d_ModelMatrix include this CS conversion, so normals/positions
        in the shader are in GL Y-up space. Custom shader inputs (via
        set_shader_input) are passed RAW in P3D Z-up space.
        """
        self._cs_mat4 = None  # None = no conversion needed
        self._cs_diag_done = False

        try:
            gsg = self.window.get_gsg() if self.window else None
            if not gsg:
                return

            default_cs = p3d.get_default_coordinate_system()
            gsg_cs = gsg.get_coordinate_system()

            if default_cs != gsg_cs:
                self._cs_mat4 = p3d.LMatrix4f.convert_mat(default_cs, gsg_cs)
                if self._debug:
                    print('[Pax3DRender] CS conversion ACTIVE '
                          '(P3D -> shader world space)')
        except Exception as exc:
            print(f'[Pax3DRender] CS detection failed ({exc}) — '
                  f'no conversion applied')

    def _convert_dir(self, v):
        """Convert a Panda3D direction Vec3 to shader world space."""
        if self._cs_mat4 is None:
            return v
        m = self._cs_mat4
        x = v.x * m.get_cell(0, 0) + v.y * m.get_cell(1, 0) + v.z * m.get_cell(2, 0)
        y = v.x * m.get_cell(0, 1) + v.y * m.get_cell(1, 1) + v.z * m.get_cell(2, 1)
        z = v.x * m.get_cell(0, 2) + v.y * m.get_cell(1, 2) + v.z * m.get_cell(2, 2)
        return p3d.Vec3(x, y, z)

    def _convert_point(self, v):
        return self._convert_dir(v)

    # ------------------------------------------------------------------
    # Post-processing chain
    # ------------------------------------------------------------------

    def _setup_tonemapping(self):
        """Set up tonemapping and optional bloom chain.

        Pipeline:
        1. Scene renders to RGBA16F buffer (HDR)
        2. If bloom enabled: extract -> N downsample -> N upsample passes
        3. Tonemap pass composites bloom (if any) and maps HDR -> sRGB
        """
        # Reset bloom state
        self._bloom_extract_quad = None
        self._bloom_down_quads = []
        self._bloom_up_quads = []

        # 1. Scene -> RGBA16F buffer
        fbprops = p3d.FrameBufferProperties()
        fbprops.float_color = True
        fbprops.srgb_color = False
        fbprops.set_rgba_bits(16, 16, 16, 16)
        fbprops.set_depth_bits(24)
        fbprops.set_multisamples(self.msaa_samples)

        scene_tex = p3d.Texture('scene_hdr')
        scene_tex.set_format(p3d.Texture.F_rgba16)
        scene_tex.set_component_type(p3d.Texture.T_float)
        # Clamp + bilinear: the radial-blur taps in tonemap.frag sample
        # off the pixel grid near the screen edge — Panda's default
        # repeat wrap would bleed the opposite edge in
        scene_tex.set_wrap_u(p3d.SamplerState.WM_clamp)
        scene_tex.set_wrap_v(p3d.SamplerState.WM_clamp)
        scene_tex.set_minfilter(p3d.SamplerState.FT_linear)
        scene_tex.set_magfilter(p3d.SamplerState.FT_linear)

        postquad = self._filtermgr.render_scene_into(
            colortex=scene_tex, fbprops=fbprops
        )

        if postquad is None:
            raise RuntimeError('[Pax3DRender] Failed to setup FilterManager')

        defines = {
            'USE_330': self._use_330,
            'IS_WEBGL': self._is_webgl,
            'ENABLE_BLOOM': self.enable_bloom,
        }

        bloom_result_tex = None

        if self.enable_bloom:
            win_x = self.window.get_x_size()
            win_y = self.window.get_y_size()
            num_levels = self.bloom_levels

            bloom_defines = {
                'USE_330': self._use_330,
                'IS_WEBGL': self._is_webgl,
            }

            # Bloom buffers must be REAL float FBOs. Without explicit
            # fbprops, render_quad_into creates a default 8-bit framebuffer
            # and the texture bind silently rewrites the declared RGBA16F
            # format to match it — the extract's 0.005 scale then collapses
            # the halo tail into a handful of 8-bit codes, which the tonemap
            # amplifies into visible banding (defect F3).
            bloom_fbprops = p3d.FrameBufferProperties()
            bloom_fbprops.float_color = True
            bloom_fbprops.set_rgba_bits(16, 16, 16, 16)

            # 2. Bloom extract pass (full resolution)
            bloom_extract_tex = p3d.Texture('bloom_extract')
            bloom_extract_tex.set_format(p3d.Texture.F_rgba16)
            bloom_extract_tex.set_component_type(p3d.Texture.T_float)
            _set_bloom_filtering(bloom_extract_tex)
            extract_quad = self._filtermgr.render_quad_into(
                colortex=bloom_extract_tex, fbprops=bloom_fbprops)
            extract_quad.set_shader(shaderutils.make_shader(
                'bloom_extract', 'post.vert', 'bloom_extract.frag',
                bloom_defines
            ))
            extract_quad.set_shader_input('scene_tex', scene_tex)
            extract_quad.set_shader_input('bloom_strength',
                                          self.bloom_strength)
            self._bloom_extract_quad = extract_quad

            # 3. Downsample chain (num_levels levels, each half the previous)
            down_textures = [bloom_extract_tex]
            for i in range(num_levels):
                div = 2 ** (i + 1)
                tex = p3d.Texture(f'bloom_down_{i}')
                tex.set_format(p3d.Texture.F_rgba16)
                tex.set_component_type(p3d.Texture.T_float)
                _set_bloom_filtering(tex)
                quad = self._filtermgr.render_quad_into(
                    colortex=tex, div=div, fbprops=bloom_fbprops)
                quad.set_shader(shaderutils.make_shader(
                    'bloom_down', 'post.vert', 'bloom_downsample.frag',
                    bloom_defines
                ))
                quad.set_shader_input('src_tex', down_textures[-1])
                # Texel size of the SOURCE texture we're reading from
                src_w = max(1, win_x // (2 ** i))
                src_h = max(1, win_y // (2 ** i))
                quad.set_shader_input('texel_size', p3d.LVecBase2(
                    1.0 / src_w, 1.0 / src_h
                ))
                down_textures.append(tex)
                self._bloom_down_quads.append(quad)

            # 4. Upsample chain (from smallest back to full resolution)
            up_tex = down_textures[-1]  # start from smallest mip
            for i in range(num_levels):
                src_idx = len(down_textures) - 2 - i
                remaining = num_levels - 1 - i
                div = 2 ** remaining if remaining > 0 else 1

                tex = p3d.Texture(f'bloom_up_{i}')
                tex.set_format(p3d.Texture.F_rgba16)
                tex.set_component_type(p3d.Texture.T_float)
                _set_bloom_filtering(tex)
                if div > 1:
                    quad = self._filtermgr.render_quad_into(
                        colortex=tex, div=div, fbprops=bloom_fbprops)
                else:
                    quad = self._filtermgr.render_quad_into(
                        colortex=tex, fbprops=bloom_fbprops)
                quad.set_shader(shaderutils.make_shader(
                    'bloom_up', 'post.vert', 'bloom_upsample.frag',
                    bloom_defines
                ))
                quad.set_shader_input('src_tex', down_textures[src_idx])
                quad.set_shader_input('bloom_accum_tex', up_tex)
                # Texel size of the COARSER accumulator — that's what the
                # tent filter reads (matches FilterManager's win//div sizing)
                accum_w = max(1, win_x // (2 ** (src_idx + 1)))
                accum_h = max(1, win_y // (2 ** (src_idx + 1)))
                quad.set_shader_input('texel_size', p3d.LVecBase2(
                    1.0 / accum_w, 1.0 / accum_h
                ))
                # Per-mip tint (cycle if more levels than tints)
                tint = _MIP_TINTS[i % len(_MIP_TINTS)]
                quad.set_shader_input('mip_tint', tint)
                up_tex = tex
                self._bloom_up_quads.append(quad)

            bloom_result_tex = up_tex

        # 5. Final tonemap + composite pass
        tonemap_shader = shaderutils.make_shader(
            'tonemap', 'post.vert', 'tonemap.frag', defines
        )

        # TAA state (reset on every rebuild)
        self._tonemap_quad = None
        self._taa_resolve_quad = None
        # Start at -1: first _update() increments to 0, so the first rendered
        # frame sees u_taa_frame=0 -> blend=1.0 (100% current, no black flash).
        self._taa_frame = -1
        self._taa_jitter_index = 0

        if self.enable_taa:
            # --- TAA pipeline: tonemap -> resolve -> history copy -> display

            # Tonemap to intermediate texture (LDR)
            tonemap_tex = p3d.Texture('tonemap_output')
            tonemap_tex.set_format(p3d.Texture.F_rgba8)
            tonemap_quad = self._filtermgr.render_quad_into(
                colortex=tonemap_tex)
            tonemap_quad.set_shader(tonemap_shader)
            tonemap_quad.set_shader_input('tex', scene_tex)
            tonemap_quad.set_shader_input('exposure', 2 ** self.exposure)
            tonemap_quad.set_shader_input(
                'tonemap_operator',
                _TONEMAP_OPERATORS.get(self.tonemap_operator, 0))
            if bloom_result_tex is not None:
                tonemap_quad.set_shader_input('bloom_tex', bloom_result_tex)
                tonemap_quad.set_shader_input('bloom_intensity',
                                              self.bloom_intensity)
            self._apply_warp_distortion_inputs(tonemap_quad)
            self._tonemap_quad = tonemap_quad

            # Resolved and history textures
            resolved_tex = p3d.Texture('taa_resolved')
            resolved_tex.set_format(p3d.Texture.F_rgba8)
            resolved_tex.set_wrap_u(p3d.SamplerState.WM_clamp)
            resolved_tex.set_wrap_v(p3d.SamplerState.WM_clamp)
            resolved_tex.set_minfilter(p3d.SamplerState.FT_linear)
            resolved_tex.set_magfilter(p3d.SamplerState.FT_linear)

            history_tex = p3d.Texture('taa_history')
            history_tex.set_format(p3d.Texture.F_rgba8)
            history_tex.set_wrap_u(p3d.SamplerState.WM_clamp)
            history_tex.set_wrap_v(p3d.SamplerState.WM_clamp)
            history_tex.set_minfilter(p3d.SamplerState.FT_linear)
            history_tex.set_magfilter(p3d.SamplerState.FT_linear)

            taa_defines = {
                'USE_330': self._use_330,
                'IS_WEBGL': self._is_webgl,
            }

            # TAA resolve pass
            winx = self.window.get_x_size()
            winy = self.window.get_y_size()
            taa_resolve_quad = self._filtermgr.render_quad_into(
                colortex=resolved_tex)
            taa_resolve_quad.set_shader(shaderutils.make_shader(
                'taa_resolve', 'post.vert', 'taa_resolve.frag', taa_defines
            ))
            taa_resolve_quad.set_shader_input('current_frame', tonemap_tex)
            taa_resolve_quad.set_shader_input('history', history_tex)
            taa_resolve_quad.set_shader_input(
                'u_resolution', p3d.Vec2(winx, winy))
            taa_resolve_quad.set_shader_input('u_taa_frame', 0.0)
            taa_resolve_quad.set_shader_input('u_debug_taa', 0.0)
            self._taa_resolve_quad = taa_resolve_quad

            # History copy pass (resolved -> history for next frame)
            history_copy_quad = self._filtermgr.render_quad_into(
                colortex=history_tex)
            history_copy_quad.set_shader(shaderutils.make_shader(
                'passthrough_copy', 'post.vert', 'passthrough.frag',
                taa_defines
            ))
            history_copy_quad.set_shader_input('tex', resolved_tex)

            # Final display (postquad -> window)
            display_shader = shaderutils.make_shader(
                'passthrough_display', 'post.vert', 'passthrough.frag',
                taa_defines
            )
            postquad.set_shader(display_shader)
            postquad.set_shader_input('tex', resolved_tex)

        else:
            # Original: tonemap directly on postquad (no TAA overhead)
            postquad.set_shader(tonemap_shader)
            postquad.set_shader_input('tex', scene_tex)
            postquad.set_shader_input('exposure', 2 ** self.exposure)
            postquad.set_shader_input(
                'tonemap_operator',
                _TONEMAP_OPERATORS.get(self.tonemap_operator, 0))
            if bloom_result_tex is not None:
                postquad.set_shader_input('bloom_tex', bloom_result_tex)
                postquad.set_shader_input('bloom_intensity',
                                          self.bloom_intensity)
            self._apply_warp_distortion_inputs(postquad)

        self._post_process_quad = postquad

        # R1: auxiliary cameras survive the rebuild
        self._reattach_scene_cameras()

    # ------------------------------------------------------------------
    # Runtime parameter updates
    # ------------------------------------------------------------------

    def _rebuild_tonemapping(self):
        """Tear down and recreate the tonemap + bloom chain.

        Needed when structural parameters change (enable_bloom, bloom_levels,
        enable_taa). Registered scene cameras are re-attached automatically.
        """
        self._filtermgr.cleanup()
        self._filtermgr = FilterManager(self.window, self.camera_node)
        if self._filtermgr.nextsort == -1000:
            self._filtermgr.nextsort = -9
        # Clear any residual TAA jitter before rebuilding
        lens = self.camera_node.node().get_lens()
        lens.set_film_offset(0, 0)
        self._setup_tonemapping()

    def set_bloom_strength(self, value):
        """Update bloom extract strength (uniform-only, no rebuild)."""
        self.bloom_strength = value
        if self._bloom_extract_quad is not None:
            self._bloom_extract_quad.set_shader_input(
                'bloom_strength', self.bloom_strength)

    def set_bloom_intensity(self, value):
        """Update bloom composite intensity (uniform-only, no rebuild)."""
        self.bloom_intensity = value
        if self.enable_bloom:
            target = self._tonemap_quad or self._post_process_quad
            if target:
                target.set_shader_input('bloom_intensity',
                                        self.bloom_intensity)

    def set_tonemap_operator(self, name):
        """Switch tonemap operator at runtime (uniform-only, no rebuild)."""
        if name not in _TONEMAP_OPERATORS:
            print(f'[Pax3DRender] Unknown tonemap operator "{name}", ignoring')
            return
        self.tonemap_operator = name
        target = self._tonemap_quad or self._post_process_quad
        if target:
            target.set_shader_input(
                'tonemap_operator', _TONEMAP_OPERATORS[name])

    def set_exposure(self, value):
        """Update exposure (uniform-only, no rebuild)."""
        self.exposure = value
        target = self._tonemap_quad or self._post_process_quad
        if target:
            target.set_shader_input('exposure', 2 ** self.exposure)

    def _apply_warp_distortion_inputs(self, quad):
        """Push the FTL warp-distortion uniforms to a tonemap quad.

        Called for both the TAA and non-TAA tonemap quads during
        (re)builds so the values survive bloom/TAA toggles.
        """
        quad.set_shader_input('radial_blur_strength',
                              self.radial_blur_strength)
        quad.set_shader_input('chroma_strength',
                              self.chromatic_aberration_strength)
        quad.set_shader_input('radial_blur_center',
                              p3d.Vec2(*self.radial_blur_center))

    def set_radial_blur(self, value):
        """Radial motion-blur strength 0-1 (uniform-only, no rebuild).

        0.0 disables the multi-tap loop entirely.  The blur is zero at
        radial_blur_center and grows outward — the vanishing point of
        motion stays sharp (FTL high-warp effect).
        """
        self.radial_blur_strength = max(0.0, min(float(value), 1.0))
        target = self._tonemap_quad or self._post_process_quad
        if target:
            target.set_shader_input('radial_blur_strength',
                                    self.radial_blur_strength)

    def set_chromatic_aberration(self, value):
        """Radial chromatic-aberration strength 0-1 (uniform-only)."""
        self.chromatic_aberration_strength = max(0.0, min(float(value), 1.0))
        target = self._tonemap_quad or self._post_process_quad
        if target:
            target.set_shader_input('chroma_strength',
                                    self.chromatic_aberration_strength)

    def set_radial_blur_center(self, x, y):
        """Move the radial-blur center (texture UV space, default 0.5, 0.5)."""
        self.radial_blur_center = (float(x), float(y))
        target = self._tonemap_quad or self._post_process_quad
        if target:
            target.set_shader_input('radial_blur_center',
                                    p3d.Vec2(*self.radial_blur_center))

    def set_enable_bloom(self, enabled):
        """Enable or disable bloom (requires buffer rebuild)."""
        if enabled == self.enable_bloom:
            return
        self.enable_bloom = enabled
        self._rebuild_tonemapping()

    def set_enable_taa(self, enabled):
        """Enable or disable Temporal Anti-Aliasing (requires rebuild)."""
        if enabled == self.enable_taa:
            return
        self.enable_taa = enabled
        if not enabled:
            lens = self.camera_node.node().get_lens()
            lens.set_film_offset(0, 0)
        self._rebuild_tonemapping()

    @staticmethod
    def _halton(index, base):
        """Halton low-discrepancy sequence for sub-pixel jitter."""
        result = 0.0
        f = 1.0
        i = index
        while i > 0:
            f /= base
            result += f * (i % base)
            i //= base
        return result

    # ------------------------------------------------------------------
    # Sun light (R2): real DirectionalLight vs legacy uniforms
    # ------------------------------------------------------------------

    def _create_sun_light(self):
        """Create the pipeline-owned sun DirectionalLight."""
        if self.sun_light_np is not None:
            return
        dlight = p3d.DirectionalLight('pax3d_sun')
        c = self._last_sun_color
        dlight.set_color(p3d.LColor(c[0], c[1], c[2], 1))
        self.sun_light_np = self.render_node.attach_new_node(dlight)
        self.render_node.set_light(self.sun_light_np)
        self._apply_shadow_caster_mask()
        if self.enable_shadows:
            self._configure_sun_shadows(True)

    def _destroy_sun_light(self):
        if self.sun_light_np is None:
            return
        self.render_node.clear_light(self.sun_light_np)
        self.sun_light_np.remove_node()
        self.sun_light_np = None

    def _configure_sun_shadows(self, enabled):
        dlight = self.sun_light_np.node()
        if enabled:
            dlight.set_shadow_caster(True, self.shadow_map_size,
                                     self.shadow_map_size)
            self.set_shadow_extent(self._shadow_extent, self._shadow_depth)
        else:
            dlight.set_shadow_caster(False)

    def set_shadow_extent(self, radius, depth=None, center=None):
        """Size and place the sun's shadow frustum: the ortho lens covers
        a (2*radius x 2*radius) area, depth units deep, centered on
        `center` in world space (default: keeps the current center,
        initially the world origin). Call with the radius and center of
        the region that should receive shadows (e.g. the current
        planet/station cluster).

        Centering works by positioning the light NODE: a DirectionalLight
        lights by orientation only, so this is lighting-neutral (proven by
        paxtest test_shadows `recenter_keeps_lighting`) while the shadow
        camera, which follows the node transform, moves with it.
        update_sun() only touches HPR, so the center survives sun
        movement. Uniform-cost — safe to call per-frame."""
        self._shadow_extent = radius
        if depth is not None:
            self._shadow_depth = depth
        if center is not None:
            self._shadow_center = p3d.Vec3(*center)
        # The bias uniform is normalized against the extent DEPTH — keep
        # a world-unit bias physically constant across extent changes.
        self._push_shadow_bias()
        if self.sun_light_np is None:
            return
        self._apply_shadow_center()
        lens = self.sun_light_np.node().get_lens()
        lens.set_film_size(2 * radius, 2 * radius)
        lens.set_near_far(-self._shadow_depth / 2, self._shadow_depth / 2)
        self._push_shadow_probe_matrix()

    def _apply_shadow_center(self):
        """Position the sun node on the requested shadow center, texel-
        snapped when shadow_texel_snap is on.

        Snapping quantizes the center to multiples of the shadow-map texel's
        world size (2*extent / map_size) along the light's film axes (the
        node's right and up vectors), leaving the along-ray component
        untouched. A frustum that follows the camera then re-rasterizes the
        depth map only on whole-texel steps, so shadow edges stop shimmering
        as the viewer walks (the openworld `_follow_shadow_frustum` pattern,
        engine-side). Always snapped FROM the stored ideal center — repeated
        calls cannot drift. With the flag off this is set_pos(center),
        byte-identical to the pre-snap pipeline.
        """
        if self.sun_light_np is None:
            return
        center = p3d.Vec3(self._shadow_center)
        if self.shadow_texel_snap and self.shadow_map_size > 0:
            texel = 2.0 * self._shadow_extent / self.shadow_map_size
            if texel > 0.0:
                quat = self.sun_light_np.get_quat(self.render_node)
                for axis in (quat.get_right(), quat.get_up()):
                    offs = center.dot(axis)
                    center += axis * (round(offs / texel) * texel - offs)
        self.sun_light_np.set_pos(center)

    def set_shadow_texel_snap(self, enabled):
        """Toggle shadow-frustum texel snapping at runtime (uniform-cost,
        no rebuild). See _apply_shadow_center. The requested center from
        set_shadow_extent is preserved: toggling off restores it exactly."""
        self.shadow_texel_snap = bool(enabled)
        self._apply_shadow_center()
        self._push_shadow_probe_matrix()

    def _push_shadow_probe_matrix(self):
        """Refresh the world -> light-0 shadow-UV matrix consumed by debug
        modes 12/13 (fragment-recomputed shadow coords). Mirrors the
        engine's shadowViewMatrix chain (graphicsStateGuardian.cxx) from
        world space: world -> light node -> light clip -> [0,1]^3."""
        if self.sun_light_np is None:
            return
        world_to_light = p3d.LMatrix4(
            self.sun_light_np.get_net_transform().get_mat())
        world_to_light.invert_in_place()
        bias = p3d.LMatrix4(0.5, 0, 0, 0,
                            0, 0.5, 0, 0,
                            0, 0, 0.5, 0,
                            0.5, 0.5, 0.5, 1)
        lens = self.sun_light_np.node().get_lens()
        mat = world_to_light * lens.get_projection_mat() * bias
        self.render_node.set_shader_input('u_probe_shadow_world_mat', mat)

    def _push_shadow_bias(self):
        """Push the shadow depth-bias and texel-size shader inputs.

        `global_shadow_bias` is consumed in NORMALIZED light-space depth:
        world-space offset = bias * extent depth. When shadow_bias_world
        is set it wins, divided by the CURRENT extent depth here so the
        offset stays a fixed world size no matter how the frustum is
        driven (this is what prevents the classic trap where the 0.005
        default quietly becomes metres of offset at open-world or
        planetary extents and erases every low caster's shadow).
        """
        if self.shadow_bias_world is not None:
            bias = self.shadow_bias_world / max(self._shadow_depth, 1e-6)
        else:
            bias = self.shadow_bias
        self.render_node.set_shader_input('global_shadow_bias', bias)
        # Slope-scaled bias: same world->normalized rescaling so the world
        # offset stays constant as the extent depth changes. 0.0 => the
        # slope term contributes nothing (byte-identical opt-out).
        self.render_node.set_shader_input(
            'u_shadow_normal_bias',
            self.shadow_normal_bias_world / max(self._shadow_depth, 1e-6))
        self.render_node.set_shader_input(
            'u_shadow_texel', 1.0 / max(self.shadow_map_size, 1))

    def set_shadow_bias(self, value, world_units=False):
        """Set the shadow depth bias at runtime (uniform-only, no rebuild).

        world_units=True: `value` is in world units and stays physically
        constant when set_shadow_extent changes the frustum depth — this
        is almost always what you want (e.g. 0.2 for metre-scale scenes,
        ~0.5 IEU for ship scale). world_units=False restores the legacy
        normalized interpretation (world offset = value * extent depth;
        see _push_shadow_bias for why that scaling is a trap).
        """
        if world_units:
            self.shadow_bias_world = float(value)
        else:
            self.shadow_bias = float(value)
            self.shadow_bias_world = None
        self._push_shadow_bias()

    def set_shadow_normal_bias(self, world_units):
        """Set the slope-scaled (grazing-angle) shadow bias at runtime, in
        WORLD units (uniform-only, no rebuild).

        The value is the extra depth bias applied per unit tan(theta) of the
        angle between a receiver and the sun, so it targets exactly the
        grazing surfaces that self-shadow into acne bands at low sun while
        leaving normal-incidence shadows untouched (unlike a bigger constant
        bias, which peter-pans everything). Stays physically constant across
        set_shadow_extent changes. 0.0 disables the slope term (byte-
        identical to the constant-bias-only path).

        Start around 0.5-1.0x the shadow texel's world size at the worst
        grazing angle and tune with the mode-11 acne fraction; see
        tools/paxtest/test_shadow_grazing.py.
        """
        self.shadow_normal_bias_world = float(world_units)
        self._push_shadow_bias()

    def set_shadow_filter_size(self, size):
        """Switch shadow filtering at runtime: 1 = single hardware-PCF
        tap (default, byte-identical to the original pipeline), 3 = 3x3
        multi-tap PCF (9 hardware taps averaged — visibly softer, more
        stable edges for open-world/character scenes). Recompiles the
        PBR shader."""
        if size not in (1, 3):
            print(f'[Pax3DRender] Unsupported shadow filter size {size!r}, '
                  f'ignoring')
            return
        if size == self.shadow_filter_size:
            return
        self.shadow_filter_size = size
        self._recompile_pbr()

    @staticmethod
    def _normalize_caster_mask(mask):
        """None | int bit index | BitMask32 -> BitMask32 or None."""
        if mask is None:
            return None
        if isinstance(mask, int):
            return p3d.BitMask32.bit(mask)
        return p3d.BitMask32(mask)

    def _apply_shadow_caster_mask(self):
        if self.sun_light_np is not None and self.shadow_caster_mask is not None:
            self.sun_light_np.node().set_camera_mask(self.shadow_caster_mask)

    def set_shadow_caster_mask(self, mask):
        """Restrict the sun's shadow camera to a dedicated camera-mask bit
        (BitMask32 or an int bit index) so scene nodes can opt out of
        shadow casting. Assigning a mask changes nothing by itself —
        every node is visible on every bit by default; it only enables
        exclude_from_shadows(). Pick a bit no other camera uses (the
        openworld build uses bit 1; check your game's camera masks)."""
        self.shadow_caster_mask = self._normalize_caster_mask(mask)
        self._apply_shadow_caster_mask()

    def exclude_from_shadows(self, nodepath):
        """Stop `nodepath` (and its subtree) casting sun shadows, while
        every other camera still renders it. The blessed API for clouds,
        sky geometry, FX quads — anything whose depth-map footprint would
        blanket the scene. Requires shadow_caster_mask to be configured
        (init kwarg or set_shadow_caster_mask)."""
        if self.shadow_caster_mask is None:
            raise ValueError(
                'exclude_from_shadows needs a shadow_caster_mask: pass '
                'shadow_caster_mask=<free bit index> to init() or call '
                'set_shadow_caster_mask() first')
        nodepath.hide(self.shadow_caster_mask)

    def include_in_shadows(self, nodepath):
        """Undo exclude_from_shadows()."""
        if self.shadow_caster_mask is None:
            raise ValueError('shadow_caster_mask is not configured')
        nodepath.show(self.shadow_caster_mask)

    # ------------------------------------------------------------------
    # Glass (specular-preserving transparency)
    # ------------------------------------------------------------------

    def _get_glass_shader(self):
        """The GLASS-defined PBR variant for the CURRENT pipeline defines
        (compiled lazily, invalidated by _recompile_pbr)."""
        if self._glass_shader is None:
            defines = self._get_pbr_defines()
            defines['GLASS'] = True
            self._glass_shader = shaderutils.make_shader(
                'pax_pbr_glass', 'pax_pbr.vert', 'pax_pbr.frag', defines)
        return self._glass_shader

    def _apply_glass_shader(self, nodepath):
        """Compose the glass shader onto the node WITHOUT wiping its other
        shader state (same discipline as _recompile_pbr): flags and inputs
        on the node's existing attrib survive, and root-level flags/inputs
        keep composing through. No override — the shadow camera's
        initial-state attrib (override 1) still wins for the depth pass,
        so glass renders into the shadow map exactly as before."""
        prev = nodepath.get_attrib(p3d.ShaderAttrib)
        if prev is None:
            prev = p3d.ShaderAttrib.make()
        nodepath.set_attrib(prev.set_shader(self._get_glass_shader()))

    def _reapply_glass_shaders(self):
        """Re-push the (freshly invalidated) glass variant onto every
        registered glass node after a pipeline shader recompile."""
        self._glass_nodes = [entry for entry in self._glass_nodes
                             if not entry[0].is_empty()]
        for entry in self._glass_nodes:
            self._apply_glass_shader(entry[0])

    def set_glass(self, nodepath, enabled=True):
        """Mark `nodepath` (and its subtree) as glass: transparency that
        keeps its specular reflections.

        The standard M_alpha path multiplies the ENTIRE shaded result by
        alpha at the blend stage, so a canopy at alpha 0.1 loses 90% of
        the highlights and reflections that make glass read as glass.
        This switches the subtree to a premultiplied-alpha PBR variant:
        alpha attenuates only the transmission-class terms (diffuse,
        ambient); specular — sun, local lights, IBL — and emission add at
        full strength, which is the glTF/PBR-viewer semantic for BLEND
        materials.

        Mechanism: a GLASS-defined compile of the same PBR shader is
        composed onto the node, plus TransparencyAttrib
        M_premultiplied_alpha at override 1 (outranks the geom-level
        M_alpha that panda3d-gltf stamps on BLEND materials). Tracks
        pipeline shader recompiles automatically. `enabled=False` undoes
        everything, restoring the node's previous blend state exactly
        (byte-identical opt-out — paxtest test_glass).

        Apply it to the glass geometry only (e.g. the canopy GeomNode),
        not a parent it shares with opaque meshes. You almost always want
        `exclude_from_shadows(nodepath)` too — the depth pass is opaque,
        so un-excluded glass casts a solid shadow. Multi-layer glass
        should be separate geoms so the transparent bin can sort them.
        """
        idx = next((i for i, entry in enumerate(self._glass_nodes)
                    if entry[0] == nodepath), None)
        if enabled:
            if idx is None:
                node = nodepath.node()
                prev_trans = node.get_attrib(p3d.TransparencyAttrib)
                prev_override = (
                    node.get_state().get_override(p3d.TransparencyAttrib)
                    if prev_trans is not None else 0)
                self._glass_nodes.append((nodepath, prev_trans,
                                          prev_override))
            self._apply_glass_shader(nodepath)
            nodepath.set_transparency(
                p3d.TransparencyAttrib.M_premultiplied_alpha, 1)
        else:
            if idx is None:
                return
            _np, prev_trans, prev_override = self._glass_nodes.pop(idx)
            nodepath.clear_shader()
            if prev_trans is not None:
                nodepath.set_attrib(prev_trans, prev_override)
            else:
                nodepath.clear_transparency()

    def set_hardware_skinning(self, nodepath, enabled):
        """Per-node override of the pipeline-wide enable_hardware_skinning
        flag: pin a problem rig to the CPU-skinning path (or force a node
        back to the GPU path) while the rest of the scene is unaffected.

        The blessed interim for rigs the GPU palette mis-skins (openworld
        P1: 94-joint Rigify exports) — global CPU skinning costs 112->8 fps
        at their NPC counts; per-node costs only the affected characters.

        Mechanism: a flag-only ShaderAttrib is composed onto the node. The
        shader itself is inherited unchanged (ShaderAttrib flags compose
        per-bit), only F_hardware_skinning flips, and the attrib rides at
        override 2 so it also outranks the shadow camera's initial-state
        attrib (override 1) — the depth pass follows the same skinning
        path and shadows keep matching the visible pose. The PBR/shadow
        shaders' skinning block degrades to identity for CPU-skinned
        vertex data (no transform_index/weight columns, identity palette),
        so one shader serves both paths.
        """
        prev = nodepath.get_attrib(p3d.ShaderAttrib)
        if prev is None:
            prev = p3d.ShaderAttrib.make()
        attr = prev.set_flag(p3d.ShaderAttrib.F_hardware_skinning,
                             bool(enabled))
        nodepath.set_attrib(attr, 2)

    def clear_hardware_skinning(self, nodepath):
        """Undo set_hardware_skinning(): the node reverts to the
        pipeline-wide enable_hardware_skinning flag. Other shader state on
        the node (e.g. its shader inputs) is preserved."""
        prev = nodepath.get_attrib(p3d.ShaderAttrib)
        if prev is not None:
            nodepath.set_attrib(
                prev.clear_flag(p3d.ShaderAttrib.F_hardware_skinning), 2)

    def set_sun_light_mode(self, mode):
        """Switch between 'uniforms' (legacy) and 'directional' (real
        DirectionalLight) at runtime. Recompiles the PBR shader."""
        if mode not in ('uniforms', 'directional'):
            print(f'[Pax3DRender] Unknown sun_light_mode "{mode}", ignoring')
            return
        if mode == self.sun_light_mode:
            return
        self.sun_light_mode = mode
        if mode == 'directional':
            self._create_sun_light()
        else:
            self._destroy_sun_light()
        self._recompile_pbr()
        self.update_sun(self._last_sun_dir, self._last_sun_color)

    def set_enable_shadows(self, enabled):
        """Toggle sun shadow mapping at runtime (directional mode only —
        the legacy uniform sun has no light node to cast from)."""
        if enabled == self.enable_shadows:
            return
        self.enable_shadows = enabled
        self._recompile_pbr()
        if self.sun_light_np is not None:
            self._configure_sun_shadows(enabled)

    def set_enable_log_depth(self, enabled):
        """Toggle logarithmic depth at runtime (R4.1). Recompiles the PBR
        shader. The caller owns the lens: widen near/far (e.g. 0.1 / 1e9)
        when enabling, restore when disabling."""
        if enabled == self.enable_log_depth:
            return
        self.enable_log_depth = enabled
        self._recompile_pbr()

    def set_double_sided_lighting(self, enabled):
        """Toggle double-sided lighting at runtime (Session K).
        Recompiles the PBR shader (glass variants track it too).

        When on, backfaces of two-sided geometry are shaded with the
        inverted normal — the glTF `doubleSided` semantic — so a thin
        panel, decal, or interior wall seen from behind lights from the
        side actually facing the sun instead of rendering near-black.
        Front faces are untouched (the flip is a per-triangle-facing
        branch), so single-sided content cannot change. Off (default)
        is byte-identical to the shipped shader."""
        enabled = bool(enabled)
        if enabled == self.double_sided_lighting:
            return
        self.double_sided_lighting = enabled
        self._recompile_pbr()

    def update_sun(self, sun_dir_world, sun_color):
        """Update the sun. Same signature in both modes.

        Args:
            sun_dir_world: Vec3, world-space direction toward the sun
                           (normalized). Passed raw in Panda3D Z-up space.
            sun_color: Vec3, linear RGB color * intensity
        """
        self._last_sun_dir = p3d.Vec3(sun_dir_world)
        self._last_sun_color = p3d.Vec3(sun_color)

        if self.sun_light_mode == 'directional' and self.sun_light_np is not None:
            # Orient the NODE so its +Y forward is the photon travel
            # direction. The engine derives the shader's toward-light vector
            # from (default _direction) x (node transform), and the shadow
            # camera looks along the node's forward — so both stay in
            # agreement. (set_direction() would move the lighting but NOT
            # the shadow camera; never use it here.)
            travel = -p3d.Vec3(sun_dir_world)
            if travel.length_squared() > 0:
                travel.normalize()
                heading = math.degrees(math.atan2(-travel.x, travel.y))
                horiz = math.sqrt(travel.x * travel.x + travel.y * travel.y)
                pitch = math.degrees(math.atan2(travel.z, horiz))
                self.sun_light_np.set_hpr(heading, pitch, 0)
            self.sun_light_np.node().set_color(
                p3d.LColor(sun_color[0], sun_color[1], sun_color[2], 1))
            # The texel-snap grid rotates with the light's film axes — with
            # snapping on, re-derive the snapped center from the stored
            # ideal one (no-op set_pos when snapping is off).
            if self.shadow_texel_snap:
                self._apply_shadow_center()
            self._push_shadow_probe_matrix()

        # Uniforms are always updated: the legacy sun block reads them, and
        # the shader debug modes (V key) visualize them in both modes.
        self.render_node.set_shader_input('u_sun_dir_world', sun_dir_world)
        self.render_node.set_shader_input('u_sun_color', sun_color)

        # Float components (for debug mode 9) — also raw Z-up
        self.render_node.set_shader_input('u_sun_dir_x', float(sun_dir_world[0]))
        self.render_node.set_shader_input('u_sun_dir_y', float(sun_dir_world[1]))
        self.render_node.set_shader_input('u_sun_dir_z', float(sun_dir_world[2]))

    def set_debug_lighting(self, mode):
        """Set shader debug visualization mode (see pax_pbr.frag)."""
        self.render_node.set_shader_input('u_debug_lighting', float(mode))

    # ------------------------------------------------------------------
    # Planetside atmosphere (Session J / R5.1) — aerial perspective
    # ------------------------------------------------------------------

    def _push_atmosphere_uniforms(self):
        """Push the aerial-perspective uniforms.

        Always pushed (whether or not ENABLE_ATMOSPHERE is compiled in):
        unused inputs are free, whereas a compiled-in shader with a missing
        input is the known crash class (arch doc §3).
        """
        haze = self.atmo_haze_color
        sun_haze = (self.atmo_sun_haze_color
                    if self.atmo_sun_haze_color is not None else haze)
        rn = self.render_node
        rn.set_shader_input('u_atmo_haze_color', p3d.Vec3(*haze))
        rn.set_shader_input('u_atmo_sun_haze_color', p3d.Vec3(*sun_haze))
        rn.set_shader_input('u_atmo_sun_power', self.atmo_sun_power)
        rn.set_shader_input('u_atmo_density', self.atmo_density)
        rn.set_shader_input('u_atmo_inv_scale_height',
                            1.0 / self.atmo_scale_height)
        rn.set_shader_input('u_atmo_base_height', self.atmo_base_height)

    def set_enable_atmosphere(self, enabled):
        """Toggle aerial perspective / height haze (recompile-class).

        PLANETSIDE feature — leave off for space scenes (off is the
        default and is byte-identical to the pre-atmosphere pipeline).
        With it on, distant geometry fades into u_atmo_haze_color with an
        exponential-height falloff, tinted toward u_atmo_sun_haze_color
        when looking sunward. Tune with set_atmosphere_params().
        """
        enabled = bool(enabled)
        if enabled == self.enable_atmosphere:
            return
        self.enable_atmosphere = enabled
        self._recompile_pbr()

    def set_atmosphere_params(self, haze_color=None, sun_haze_color=None,
                              sun_power=None, density=None,
                              scale_height=None, base_height=None):
        """Update aerial-perspective parameters (uniform-only, no rebuild).

        haze_color:     linear-HDR inscatter color at the horizon. Match it
                        to the horizon of the scene's skybox.
        sun_haze_color: inscatter when looking straight at the sun (the
                        forward-scattering glow); None = follow haze_color.
        sun_power:      tightness of that sunward lobe (pow exponent).
        density:        extinction per world unit at base_height. The
                        distance to ~63% haze is 1/density world units.
        scale_height:   world-unit e-folding height of the medium — haze
                        thins with altitude (mountaintops stay clear).
        base_height:    world z of the density datum (ground level).
        """
        if haze_color is not None:
            self.atmo_haze_color = tuple(haze_color)
        if sun_haze_color is not None:
            self.atmo_sun_haze_color = tuple(sun_haze_color)
        if sun_power is not None:
            self.atmo_sun_power = float(sun_power)
        if density is not None:
            self.atmo_density = max(0.0, float(density))
        if scale_height is not None:
            self.atmo_scale_height = max(1e-6, float(scale_height))
        if base_height is not None:
            self.atmo_base_height = float(base_height)
        self._push_atmosphere_uniforms()

    # ------------------------------------------------------------------
    # Environment-driven ambient (Session J / R5.2) — irradiance SH
    # ------------------------------------------------------------------

    def set_ambient_sh(self, coeffs):
        """Feed 9 irradiance-convolved SH coefficients (RGB triples) to the
        shader's existing sh_coeffs diffuse-IBL path (uniform-only).

        The shader evaluates E(n) = sum(coeffs[i] * Y_i(n)) and applies it
        as base_color * E(n) / pi, energy-conserving against metallic/
        Fresnel (arch doc §9 R5 hooks). Basis slot order (world frame,
        Panda Z-up): [const, x, z, y, xz, yz, xy, 3z^2-1, x^2-y^2] with
        simplepbr's normalization constants. Survives shader recompiles.
        """
        pta = p3d.PTA_LVecBase3f()
        for c in coeffs:
            pta.push_back(p3d.LVecBase3f(c[0], c[1], c[2]))
        if len(pta) != 9:
            raise ValueError(f'set_ambient_sh needs 9 coefficients, '
                             f'got {len(pta)}')
        self._ambient_sh = pta
        self.render_node.set_shader_input('sh_coeffs', pta)

    def set_hemisphere_ambient(self, sky_color, ground_color, up=(0, 0, 1)):
        """Two-tone environment ambient: sky_color lights up-facing
        surfaces, ground_color down-facing, smoothly blended by the world
        normal (uniform-only, exact SH bands 0-1).

        THE cheap planetside-look win: shadowed sides of objects pick up
        sky tint instead of a flat gray, and undersides get ground bounce.
        Both colors are linear; a surface facing straight up receives
        base_color * (avg + 2/3 * delta) where avg/delta are the mean and
        half-difference of the two colors. Replaces (don't stack with) the
        flat AmbientLight the scene would otherwise use — keep any
        AmbientLight small. up is the world up axis in Panda Z-up space.
        clear_ambient_sh() restores the exact pre-call output.
        """
        sky = p3d.Vec3(sky_color[0], sky_color[1], sky_color[2])
        ground = p3d.Vec3(ground_color[0], ground_color[1], ground_color[2])
        upv = p3d.Vec3(up[0], up[1], up[2])
        if upv.length_squared() > 0:
            upv.normalize()
        avg = (sky + ground) * 0.5
        half = (sky - ground) * 0.5
        # Irradiance of L(w) = avg + half*(w.up): E(n) = pi*avg
        # + (2pi/3)*half*(n.up). Divide by the shader's basis constants so
        # sum(c_i * Y_i(n)) reproduces E(n) exactly (bands 0-1 are exact
        # for a linear-gradient environment; higher bands are zero).
        c0 = avg * (math.pi / 0.282095)
        lin = half * ((2.0 * math.pi / 3.0) / 0.488603)
        zero = (0.0, 0.0, 0.0)
        self.set_ambient_sh([
            tuple(c0),
            tuple(lin * upv.x),   # slot 1: basis normal.x
            tuple(lin * upv.z),   # slot 2: basis normal.z
            tuple(lin * upv.y),   # slot 3: basis normal.y
            zero, zero, zero, zero, zero,
        ])

    def clear_ambient_sh(self):
        """Remove the environment ambient: sh_coeffs back to zeros —
        byte-identical to the pipeline before any set_*_ambient call."""
        self._ambient_sh = None
        self.render_node.set_shader_input('sh_coeffs', self._empty_sh)

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def _update(self, task):
        """Per-frame maintenance: shadow shaders, camera position, clear color."""
        # Handle shadow casters (same as simplepbr)
        if self.enable_shadows:
            for caster in self._get_all_casters():
                if isinstance(caster, p3d.PointLight):
                    caster.set_shadow_caster(False)
                    continue
                state = caster.get_initial_state()
                if not state.has_attrib(p3d.ShaderAttrib):
                    attr = self._create_shadow_shader_attrib()
                    state = state.add_attrib(attr, 1)
                    state = state.remove_attrib(p3d.CullFaceAttrib)
                    caster.set_initial_state(state)

        # Copy background color to offscreen buffer
        if self._filtermgr.buffers:
            self._filtermgr.buffers[0].set_clear_color(
                self.window.get_clear_color())

        # Camera world position for IBL reflections — raw Z-up, no CS conversion
        cam_pos = self.camera_node.get_pos(self.render_node)
        self.render_node.set_shader_input('camera_world_position', cam_pos)

        # Log-depth coefficient tracks the camera lens far plane (R4.1) —
        # the game may change near/far at runtime (regime switches)
        if self.enable_log_depth:
            far = max(2.0, self.camera_node.node().get_lens().get_far())
            self.render_node.set_shader_input(
                'u_log_depth_coef', 1.0 / math.log2(1.0 + far))

        # TAA per-frame jitter
        if self.enable_taa and self._taa_resolve_quad is not None:
            self._taa_jitter_index += 1
            lens = self.camera_node.node().get_lens()
            jx = self._halton(self._taa_jitter_index, 2) - 0.5
            jy = self._halton(self._taa_jitter_index, 3) - 0.5
            win_x = max(1, self.window.get_x_size())
            win_y = max(1, self.window.get_y_size())
            film_size = lens.get_film_size()
            lens.set_film_offset(
                jx * film_size.x / win_x,
                jy * film_size.y / win_y
            )
            self._taa_frame += 1
            self._taa_resolve_quad.set_shader_input(
                'u_taa_frame', float(self._taa_frame))

        return task.DS_cont

    def _get_all_casters(self):
        """Find all shadow-casting lights in the scene."""
        engine = p3d.GraphicsEngine.get_global_ptr()
        cameras = [
            dr.camera
            for win in engine.windows
            for dr in win.active_display_regions
        ]

        result = []
        for cam_np in cameras:
            if cam_np.is_empty():
                continue
            node = cam_np.node()
            if hasattr(node, 'is_shadow_caster') and node.is_shadow_caster():
                result.append(node)
        return result

    def _create_shadow_shader_attrib(self):
        """Create a shader attrib for shadow-casting geometry."""
        defines = {
            'USE_330': self._use_330,
            'IS_WEBGL': self._is_webgl,
            'ENABLE_SKINNING': self.enable_hardware_skinning,
        }
        shader = shaderutils.make_shader(
            'shadow', 'shadow.vert', 'shadow.frag', defines
        )
        attr = p3d.ShaderAttrib.make(shader)
        if self.enable_hardware_skinning:
            attr = attr.set_flag(p3d.ShaderAttrib.F_hardware_skinning, True)
        return attr

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        """Remove the pipeline task, sun light, aux cameras, FilterManager."""
        self.taskmgr.remove('pax3d_render_update')
        self._destroy_sun_light()
        for reg in list(self._scene_cameras):
            self.unregister_scene_camera(reg)
        if self.enable_taa:
            lens = self.camera_node.node().get_lens()
            lens.set_film_offset(0, 0)
        if self._filtermgr:
            self._filtermgr.cleanup()
