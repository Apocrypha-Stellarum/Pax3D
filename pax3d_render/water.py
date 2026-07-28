"""pax3d_render water surface — the shared game-water promoted into the
engine (voxel-lane ask, 2026-07-28; user-sanctioned direction: BOTH games
consume one module, so "tuning the engine for this water type" lands in
each).

Provenance: sfb2 terrain-demo water (sessions 449-453) -> planetside
world/water.py + shaders/water.{vert,frag} (Sea-of-Thieves shore pass) ->
paxcraft ocean.py port (2026-07-28).  The shader pair here is that recipe
with every game-specific deviation promoted to a uniform (defaults = the
planetside ocean), plus the port's two findings folded in for every
consumer:

 1. Distance haze is the ENGINE's analytic aerial perspective (the exact
    pax_pbr.frag block), not plain exp fog — sea, terrain and far-field
    haze as ONE system.  update() feeds it from pipeline.atmo_* each
    frame, so it tracks set_atmosphere_params automatically (density 0 /
    atmosphere disabled = exact no-op).
 2. HDR sun feeds get a luminance knee (water_sun): any game whose
    day-night cycle drives an HDR sun multiplier overdrives the
    body-colour recipe (tuned around a ~1.0 sun) without it.
    set_environment() applies it; params.sun_knee=0 disables.

What the engine owns: follow-grid geometry (dense near grid + optional
horizon annulus or rim fade), the shader pair, render state (transparent
bin, no depth write, omni bounds, shadow exclusion), uniform defaults,
the haze feed and the sun knee.

What the GAME owns (the provider contract):
 - Seafloor DEPTH: bake a player-following R32F height texture (absolute
   world z of the floor) however the world knows it — planetside bakes
   the analytic heightfield, paxcraft samples worldgen + resident-chunk
   overlay — and hand it over via set_seafloor(tex, origin_xy, size_m)
   whenever a bake lands (or bind u_seafloor/u_sf_origin_size on .root
   directly; the uniform names are the game copies' own).  Until then
   the surface renders per params.uncovered: 'deep' = open ocean
   everywhere (horizon-annulus games), 'dry' = nothing outside the
   window (windowed coastal games — far-field land lives out there).
 - Per-frame drive: call update(x, y, camera_pos) every frame and
   set_environment(...) whenever the day-night feed ticks.  **ORDER
   MATTERS: update() must run AFTER your day-night tick**, because it
   reads pipeline.atmo_* itself — call it before and the sea hazes with
   last frame's sky.  Game copies from before this promotion pushed
   haze from their own env update and were order-insensitive, so an
   adopter can inherit a wrong order silently (field report, voxel
   game, 2026-07-28).
 - Underwater eye effects, swimming, audio: not this module.

Typical use::

    from pax3d_render.water import WaterParams

    water = pipeline.build_water_surface(
        render, water_z=12.0,
        params=WaterParams(deep_color=(0.04, 0.10, 0.22)))
    # per frame:
    water.update(player_x, player_y, camera_pos)
    # on day-night tick:
    water.set_environment(sun_dir, sun_color, sky_horizon, sky_zenith)

Gate: tools/paxtest/test_water.py.
"""
import math
from dataclasses import dataclass

import panda3d.core as p3d

from . import shaderutils


# ---------------------------------------------------------------------------
# Parameters (defaults = the planetside ocean, field-tuned s690-s695b)
# ---------------------------------------------------------------------------

# Uncovered-seafloor policies: floor z relative to water z where the
# depth map has no data (bound window missed, or no map yet).
UNCOVERED_DZ = {'deep': -40.0, 'dry': 100.0}


@dataclass
class WaterParams:
    """Body optics + tuning for one water surface.  Every field maps to
    a uniform; all are safe to change live via the setters below."""
    # Body colours: deep body colour is the planet/world character;
    # shallow scatter tint derives from it unless given explicitly.
    deep_color: tuple = (0.04, 0.10, 0.22)
    shallow_color: tuple = None
    shallow_gain: float = 2.4
    shallow_bias: tuple = (0.02, 0.12, 0.10)
    # Per-channel Beer-Lambert extinction (1/m): red absorbed first —
    # the turquoise -> navy hue walk.
    absorb: tuple = (0.22, 0.072, 0.045)
    # View-through opacity rate (1/m): the shore melt.
    alpha_k: float = 0.32
    wave_amp: float = 1.0
    foam_gain: float = 1.0
    # Swell wavenumber multiplier: 1.0 = 57-120 m ocean swells; a voxel
    # coastal sea compresses them (~2x).
    swell_scale: float = 1.0
    # Camera-distance swell amplitude fade (full at .x, gone by .y).
    swell_fade: tuple = (1200.0, 2400.0)
    # Whitecaps: (patch noise scale, patch lo, patch hi, base gain) and
    # the cap-noise gate (lo, hi).
    whitecap: tuple = (0.006, 0.42, 0.78, 0.6)
    whitecap_gate: tuple = (0.62, 0.85)
    # Sun luminance knee coefficient (water_sun); 0 disables.
    sun_knee: float = 0.25
    # 'deep' | 'dry' | explicit float dz (floor z - water z).
    uncovered: str = 'deep'

    def uncovered_dz(self):
        if isinstance(self.uncovered, str):
            return UNCOVERED_DZ[self.uncovered]
        return float(self.uncovered)

    def derived_shallow(self, deep=None):
        """Shallow scatter tint: brightened deep colour + a cyan scatter
        bias — alien oceans stay coherent (green seas get bright green
        shallows) instead of forcing every world tropical-Earth."""
        if self.shallow_color is not None:
            return tuple(self.shallow_color)
        deep = deep if deep is not None else self.deep_color
        return tuple(min(1.0, c * self.shallow_gain + b)
                     for c, b in zip(deep, self.shallow_bias))


def water_sun(color, knee=0.25):
    """Soft luminance knee for the water shader's sun feed.

    Day-night suns are HDR multipliers (planetside noon 1.35+, paxcraft
    noon 3.3); the water recipe assumes a ~1.0 sun and blows the body
    colour to white-cyan under more (the paxcraft water_ocean_v1 noon
    probe).  s = 1/(1 + knee*max_c): 3.3 -> 1.81, 1.9 -> 1.29,
    0.95 -> 0.77 at knee 0.25 — daylight tamed, twilight character
    kept, hue preserved.  knee = 0 is the identity."""
    m = max(color[0], color[1], color[2])
    s = 1.0 / (1.0 + knee * m)
    return p3d.Vec3(color[0] * s, color[1] * s, color[2] * s)


# ---------------------------------------------------------------------------
# Follow geometry
# ---------------------------------------------------------------------------

def _grid_node(name, half_extent, resolution):
    """Flat square grid centred on the origin, vertices only."""
    fmt = p3d.GeomVertexFormat.get_v3()
    vdata = p3d.GeomVertexData(name, fmt, p3d.Geom.UH_static)
    vdata.set_num_rows((resolution + 1) ** 2)
    vw = p3d.GeomVertexWriter(vdata, 'vertex')
    step = 2.0 * half_extent / resolution
    for j in range(resolution + 1):
        y = -half_extent + j * step
        for i in range(resolution + 1):
            vw.add_data3(-half_extent + i * step, y, 0.0)
    tris = p3d.GeomTriangles(p3d.Geom.UH_static)
    stride = resolution + 1
    for j in range(resolution):
        for i in range(resolution):
            a = j * stride + i
            b = a + 1
            c = a + stride
            d = c + 1
            tris.add_vertices(a, b, c)
            tris.add_vertices(b, d, c)
    geom = p3d.Geom(vdata)
    geom.add_primitive(tris)
    node = p3d.GeomNode(name)
    node.add_geom(geom)
    return node


def _annulus_node(name, r_inner, r_outer, rings, segments):
    """Flat ring mesh (geometric ring spacing) centred on the origin."""
    fmt = p3d.GeomVertexFormat.get_v3()
    vdata = p3d.GeomVertexData(name, fmt, p3d.Geom.UH_static)
    vdata.set_num_rows((rings + 1) * (segments + 1))
    vw = p3d.GeomVertexWriter(vdata, 'vertex')
    growth = (r_outer / r_inner) ** (1.0 / rings)
    for ri in range(rings + 1):
        r = r_inner * growth ** ri
        for si in range(segments + 1):
            a = 2.0 * math.pi * si / segments
            vw.add_data3(r * math.cos(a), r * math.sin(a), 0.0)
    tris = p3d.GeomTriangles(p3d.Geom.UH_static)
    stride = segments + 1
    for ri in range(rings):
        for si in range(segments):
            a = ri * stride + si
            b = a + 1
            c = a + stride
            d = c + 1
            tris.add_vertices(a, b, c)
            tris.add_vertices(b, d, c)
    geom = p3d.Geom(vdata)
    geom.add_primitive(tris)
    node = p3d.GeomNode(name)
    node.add_geom(geom)
    return node


_shader = None


def _water_shader():
    global _shader
    if _shader is None:
        _shader = shaderutils.make_shader(
            'water_surface', 'water_surface.vert', 'water_surface.frag', {})
    return _shader


# ---------------------------------------------------------------------------
# The surface
# ---------------------------------------------------------------------------

class WaterSurface:
    """One animated water plane at world z = water_z, following the
    player in XY.  Build via pipeline.build_water_surface()."""

    def __init__(self, pipeline, parent_np, water_z, params=None,
                 near_half_extent=3200.0, near_resolution=280,
                 far_annulus=(3200.0, 45000.0, 24, 96),
                 rim_fade=False, bin_sort=10):
        """far_annulus: (inner, outer, rings, segments) horizon ring for
        ocean-to-the-horizon worlds, or None for a single windowed grid
        (pair that with rim_fade=True and params.uncovered='dry')."""
        self.pipeline = pipeline
        self.params = params if params is not None else WaterParams()
        self.water_z = float(water_z)
        self._absorb_base = tuple(self.params.absorb)
        self._deep = tuple(self.params.deep_color)

        self.root = parent_np.attach_new_node('pax3d_water')
        self.root.set_z(self.water_z)
        near = p3d.NodePath(_grid_node(
            'water_near', near_half_extent, near_resolution))
        near.reparent_to(self.root)
        meshes = [near]
        if far_annulus is not None:
            far = p3d.NodePath(_annulus_node('water_far', *far_annulus))
            far.reparent_to(self.root)
            meshes.append(far)

        self.root.set_shader(_water_shader(), 1)
        self.root.set_transparency(p3d.TransparencyAttrib.M_alpha)
        self.root.set_bin('transparent', bin_sort)
        self.root.set_depth_write(False)
        self.root.set_light_off(1)
        self.root.set_two_sided(True)
        # Vertex displacement moves geometry beyond CPU bounds, and the
        # meshes follow the camera anyway: never frustum-cull them.
        for np_ in meshes:
            np_.node().set_bounds(p3d.OmniBoundingVolume())
            np_.node().set_final(True)
        # Waves must not stripe the seafloor in the sun shadow pass.
        # (No caster mask configured = no shadow pass to stripe from.)
        try:
            pipeline.exclude_from_shadows(self.root)
        except (ValueError, AttributeError):
            pass

        p = self.params
        r = self.root
        r.set_shader_input('u_time', 0.0)
        r.set_shader_input('u_camera_pos', p3d.Vec3(0, 0, 0))
        r.set_shader_input('u_wave_amp', float(p.wave_amp))
        r.set_shader_input('u_swell_scale', float(p.swell_scale))
        r.set_shader_input('u_swell_fade', p3d.Vec2(*p.swell_fade))
        r.set_shader_input('u_rim_half',
                           float(near_half_extent) if rim_fade else 0.0)
        r.set_shader_input('u_shallow_color',
                           p3d.Vec3(*p.derived_shallow(self._deep)))
        r.set_shader_input('u_deep_color', p3d.Vec3(*self._deep))
        r.set_shader_input('u_absorb', p3d.Vec3(*self._absorb_base))
        r.set_shader_input('u_alpha_k', float(p.alpha_k))
        r.set_shader_input('u_foam_gain', float(p.foam_gain))
        r.set_shader_input('u_whitecap', p3d.Vec4(*p.whitecap))
        r.set_shader_input('u_capgate', p3d.Vec2(*p.whitecap_gate))
        r.set_shader_input('u_water_z', self.water_z)
        r.set_shader_input('u_uncovered_dz', p.uncovered_dz())
        # Seafloor: bound not-ready until the game's first bake lands
        # (the sampler must be bound either way for the shader to run).
        placeholder = p3d.Texture('seafloor')
        placeholder.setup_2d_texture(1, 1, p3d.Texture.T_float,
                                     p3d.Texture.F_r32)
        r.set_shader_input('u_seafloor', placeholder)
        r.set_shader_input('u_sf_origin_size', p3d.Vec3(0, 0, -1))
        r.set_shader_input('u_sun_dir_world', p3d.Vec3(0, 0, 1))
        r.set_shader_input('u_sun_color', p3d.Vec3(1, 1, 1))
        r.set_shader_input('u_sky_horizon', p3d.Vec3(0.12, 0.16, 0.22))
        r.set_shader_input('u_sky_zenith', p3d.Vec3(0.03, 0.06, 0.12))
        r.set_shader_input('u_haze_color', p3d.Vec3(0, 0, 0))
        r.set_shader_input('u_sun_haze_color', p3d.Vec3(0, 0, 0))
        r.set_shader_input('u_sun_power', 8.0)
        r.set_shader_input('u_density', 0.0)
        r.set_shader_input('u_inv_scale_h', 1.0 / 1200.0)
        r.set_shader_input('u_base_h', 0.0)

    # -- per-frame drive ------------------------------------------------
    def update(self, x, y, camera_pos, time=None):
        """Follow the player in XY, advance animation time, and refresh
        the aerial haze from the pipeline's live atmosphere state (all
        uniform-only, cheap).  camera_pos is the eye in the water's
        parent frame (world space for a render-parented surface).

        CALL THIS *AFTER* YOUR DAY-NIGHT TICK.  update() READS
        `pipeline.atmo_*` itself, so a frame task that updates the water
        before the sky pushes new atmosphere params hazes the sea with
        last frame's values.  Pre-promotion game copies pushed haze from
        their own env update and were order-insensitive, so an existing
        adopter can carry a wrong order in silently — reported from the
        field by the voxel game 2026-07-28 (Session AM), who hit exactly
        that on adoption and moved the call."""
        r = self.root
        r.set_pos(x, y, self.water_z)
        if time is None:
            time = p3d.ClockObject.get_global_clock().get_frame_time()
        r.set_shader_input('u_time', float(time))
        r.set_shader_input('u_camera_pos', camera_pos)
        # Haze rides set_atmosphere_params by construction: same values,
        # same frame as the terrain (atmosphere off = density 0 = no-op).
        pipe = self.pipeline
        if getattr(pipe, 'enable_atmosphere', False):
            haze = pipe.atmo_haze_color
            sun_haze = (pipe.atmo_sun_haze_color
                        if pipe.atmo_sun_haze_color is not None else haze)
            r.set_shader_input('u_haze_color', p3d.Vec3(*haze))
            r.set_shader_input('u_sun_haze_color', p3d.Vec3(*sun_haze))
            r.set_shader_input('u_sun_power', float(pipe.atmo_sun_power))
            r.set_shader_input('u_density', float(pipe.atmo_density))
            r.set_shader_input('u_inv_scale_h',
                               1.0 / float(pipe.atmo_scale_height))
            r.set_shader_input('u_base_h', float(pipe.atmo_base_height))
        else:
            r.set_shader_input('u_density', 0.0)

    def set_environment(self, sun_dir, sun_color, sky_horizon=None,
                        sky_zenith=None):
        """Day-night feed: the active light (sun by day, moon at night —
        the game's call) plus the sky reflection tints.  The sun colour
        passes through the luminance knee (params.sun_knee)."""
        r = self.root
        r.set_shader_input('u_sun_dir_world', p3d.Vec3(*sun_dir))
        r.set_shader_input('u_sun_color',
                           water_sun(sun_color, self.params.sun_knee))
        if sky_horizon is not None:
            r.set_shader_input('u_sky_horizon', p3d.Vec3(*sky_horizon))
        if sky_zenith is not None:
            r.set_shader_input('u_sky_zenith', p3d.Vec3(*sky_zenith))

    def set_seafloor(self, tex, origin_xy=None, size=None):
        """Bind the provider's seafloor height window: R32F texture of
        absolute world floor z, SW corner origin_xy, square size metres.
        origin_xy/size None marks the map not-ready (uncovered policy
        applies everywhere)."""
        self.root.set_shader_input('u_seafloor', tex)
        if origin_xy is None or size is None:
            self.root.set_shader_input('u_sf_origin_size',
                                       p3d.Vec3(0, 0, -1))
        else:
            self.root.set_shader_input(
                'u_sf_origin_size',
                p3d.Vec3(float(origin_xy[0]), float(origin_xy[1]),
                         float(size)))

    # -- live tuning (uniform-only, safe any frame) ---------------------
    def set_wave_amp(self, v):
        """Swell height multiplier (vertex displacement + whitecaps)."""
        self.root.set_shader_input('u_wave_amp', float(v))

    def set_alpha_k(self, v):
        """See-through opacity rate, 1/m — lower = clearer shallows."""
        self.root.set_shader_input('u_alpha_k', float(v))

    def set_absorb_scale(self, v):
        """Scales the Beer-Lambert extinction — lower = the colour walk
        to deep-navy happens over MORE metres of depth."""
        self.root.set_shader_input(
            'u_absorb', p3d.Vec3(*(c * float(v) for c in self._absorb_base)))

    def set_deep_color(self, rgb):
        """Deep body colour; the shallow scatter tint re-derives."""
        self._deep = tuple(float(c) for c in rgb)
        self.root.set_shader_input('u_deep_color', p3d.Vec3(*self._deep))
        self.root.set_shader_input(
            'u_shallow_color',
            p3d.Vec3(*self.params.derived_shallow(self._deep)))

    def set_shallow_gain(self, v):
        """Brightness of the shallow scatter tint over the deep colour."""
        self.params.shallow_gain = float(v)
        self.params.shallow_color = None
        self.root.set_shader_input(
            'u_shallow_color',
            p3d.Vec3(*self.params.derived_shallow(self._deep)))

    def set_foam_gain(self, v):
        """Master foam scale: whitecaps + contact + shore bands."""
        self.root.set_shader_input('u_foam_gain', float(v))

    def body_colours(self):
        """(deep, shallow) as currently tuned — underwater eye effects
        derive their column colour from these."""
        return self._deep, self.params.derived_shallow(self._deep)

    def cleanup(self):
        self.root.remove_node()
