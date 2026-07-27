# Using pax3d_render — the Pax3D Rendering Pipeline in Pax Abyssi

> **Note (2026-07-28):** this guide is mirrored from the Pax Abyssi game
> repo, its original audience — the walkthrough is game-flavored, but the
> API it documents is the engine's `pax3d_render/` package and applies to
> any application on the Pax3D/Panda3D lineage. §8 is the quick API
> reference; start there if you just want the calls.

**Audience:** the AI/human dev working on the game (`C:\python\sfb2`).
**Engine repo:** `C:\python\pax3d` (package: `pax3d_render/`).
**Last updated:** 2026-07-18 (engine Sessions A–S; §8 is the quick
reference for everything added after Session C, §10 routes each
downstream dev — ship interior, weapons/viewmodel, terrain, NPC
characters — to exactly what they need).

`pax3d_render` is the successor to `graphics/pax_pbr/` — the same pipeline
(literally: merged from it, shaders identical), now maintained in the engine
repo with new capabilities the local copy will never get:

| Capability | graphics/pax_pbr (local, legacy) | pax3d_render |
|---|---|---|
| PBR + tonemap + bloom + TAA + debug modes | yes | yes (identical) |
| Sun as a **real DirectionalLight** | no (uniforms only) | yes — `sun_light_mode='directional'` |
| **Sun shadows** | no | yes, harness-proven |
| Sky camera survives bloom/TAA toggles | no (skybox dies) | yes — `register_scene_camera()` |
| Runtime shadow / sun-mode toggles | no | yes |
| sRGB input linearization helper | no | yes |
| Bloom fixed (F3), logarithmic depth | never | yes (Session D, opt-in) |
| Shadow quality suite (world-unit bias, slope bias, PCF, no-cast, texel snap) | never | yes (Sessions E–J, opt-in) |
| Planetside atmosphere + hemisphere ambient | never | yes (Session J, opt-in) |
| Specular IBL env maps + skybox ambient (incl. bake tools) | never | yes (Sessions M/Q/R, opt-in) |
| Orbital atmosphere (planet limb/halo from space) | never | yes (Session R, opt-in) |
| Future work (lens flare/dirt, SSAO) | never | lands here |

> **Correction to older docs** (`PAX_PBR_PIPELINE.md`, SCENE_LIGHTING.md):
> the "Panda3D DirectionalLight engine bug" that motivated the custom sun
> uniforms **does not exist**. The engine's test harness proved a real
> DirectionalLight lights every current mesh type correctly; the 2025
> symptoms were mesh winding + missing tangents + API confusion. The
> uniform sun still works and remains the default, but directional mode is
> the target — it's what enables shadows.

---

## 1. Switching the Game to pax3d_render

One flag in `config/settings.json`:

```json
"planetary_shuttle_rendering": {
    "use_pax3d_render": true,
    "pax3d_repo_path": "C:/python/pax3d",
    ...
}
```

`graphics/pax_pbr/__init__.py` then routes `from graphics.pax_pbr import
init` to the engine package — **no other game code changes**. All existing
call sites (`plan_initialization_manager.py`, `test3d.py`) work unchanged;
with default parameters the rendered output is identical (verified by the
engine's paxtest harness and the testbed).

Rollback = set the flag to `false`. Both paths accept the same kwargs
(unknown ones are ignored), so parameters like `sun_light_mode` are safe to
leave in the init call even when running the legacy pipeline.

---

## 2. The Sun

### Per-frame update (unchanged, both modes)

```python
# sun_dir_world: unit Vec3 TOWARD the sun, raw Panda Z-up world space
# sun_color:     linear RGB * intensity
pipeline.update_sun(sun_dir_world, sun_color)
```

`sun_position_manager.py` keeps working as-is in every mode. There is no
HPR formula anywhere in game code anymore — direction in, done.

### Directional mode (the upgrade)

```python
pipeline = pax_pbr_init(
    ...,
    sun_light_mode='directional',   # default: 'uniforms' (legacy)
)
```

In the real game this is wired to settings (Session D):
`planetary_shuttle_rendering.sun_light_mode` in `config/settings.json`
('uniforms' default; set 'directional' after parity sign-off) —
`plan_initialization_manager.py` passes it through. The legacy local
pipeline ignores the kwarg, so the key is safe with `use_pax3d_render`
either way.

What changes: the pipeline owns a real `DirectionalLight` ("pax3d_sun") and
the PBR shader lights from it — same BRDF, same look (harness-verified
identical), but now shadows are possible and any OTHER `DirectionalLight`
you attach to render is also honored (it no longer gets silently ignored).

Runtime switch (mainly for A/B): `pipeline.set_sun_light_mode('directional'
| 'uniforms')` — call `update_sun` afterwards if you switch mid-scene
(the testbed's N key does exactly this).

Rules that still apply to the sun in directional mode (the pipeline handles
them internally, but don't fight it): never `set_pos()` or `set_direction()`
on the sun light node yourself, never reparent it — game code goes through
`update_sun()` and `set_shadow_extent()` only (the pipeline positions the
node internally for shadow-frustum centering; that's its business).

### Sun shadows

```python
pipeline = pax_pbr_init(..., sun_light_mode='directional',
                        enable_shadows=True, shadow_map_size=2048)
pipeline.set_shadow_extent(radius, depth)   # size the shadowed region
```

- `set_shadow_extent(radius, depth, center)`: shadows exist inside a
  `2*radius`-wide box, `depth` deep, centered on `center` in world space
  (default: world origin), aligned to the sun. Objects OUTSIDE the extent
  render fully lit (no artifacts, just no shadows) — paxtest-proven.
  Uniform-cost, safe to call per frame.
- **The game already drives this** (Session D): `sun_position_manager`
  recenters the extent on the camera every sun update when shadows are
  on, using `planetary_shuttle_rendering.shadow_extent_radius` /
  `shadow_extent_depth` (defaults 500 / 4000). Shadow-map resolution
  follows the player; no planet-sized extents needed.
- Runtime toggle: `pipeline.set_enable_shadows(True/False)` — safe, causes
  one shader-recompile hitch.
- `shadow_bias` (default 0.005) if acne/peter-panning appears.

---

## 3. Sky Camera / Auxiliary Cameras

`graphics/sky_camera.py` already auto-detects the new API — when running on
pax3d_render, the sky display region is **owned by the pipeline and
survives bloom/TAA toggles** (the old "toggle bloom → skybox gone forever"
bug is dead). Nothing to do.

For any NEW overlay/background camera, use the same pattern — never search
for the FilterManager buffer yourself:

```python
reg = pipeline.register_scene_camera(
    my_cam_np,            # you own lens, camera mask, scene root, transform
    sort=-100,            # negative = renders before the main scene
    clear_color=(0, 0, 0, 1),
    clear_depth=True,
    name='my_overlay')
...
pipeline.unregister_scene_camera(reg)
```

Background cameras (sort < 0) automatically set the main scene region to
preserve their pixels (color-clear off, depth-clear on) — same contract the
sky camera always used.

---

## 4. Bloom, Tonemap, Exposure, TAA

Same parameters and setters as the legacy pipeline:

```python
pax_pbr_init(..., enable_bloom=True, bloom_strength=1.0,
             bloom_intensity=1.0, bloom_levels=5,
             tonemap_operator='hejl_dawson', exposure=0.0,
             enable_taa=False)

pipeline.set_bloom_strength(1.5)      # free, per-frame safe
pipeline.set_bloom_intensity(0.8)     # free
pipeline.set_tonemap_operator('aces') # free ('aces'|'reinhard'|'uncharted2'|'hejl_dawson')
pipeline.set_exposure(0.5)            # free, EV stops (2^x)
pipeline.set_enable_bloom(True)       # rebuild (frame hitch) — now SAFE, sky camera survives
pipeline.set_enable_taa(True)         # rebuild — now safe for the same reason
```

**Honest status:**
- **Bloom is FIXED (engine Session D, 2026-07-17)** — the old blocky,
  lopsided halos were root-caused (8-bit intermediate framebuffers
  silently quantizing the HDR chain, plus two kernel defects) and the
  fix is harness-gated at two resolutions on both engines. Bloom is
  safe to enable. What remains of R3 is CONTENT tuning: brightness rose
  because the halo tail is no longer quantized away, so retune
  `bloom_strength`/`bloom_intensity` (and the per-mip tints) in the
  testbed before shipping it on. Older advice to keep bloom off is
  obsolete — planetside already ships with it on.
- **Tonemap operators are mathematically correct** (harness-proven — no
  double gamma). If ACES looks washed out on game content, that is the
  input-linearization issue below, not a tonemap bug.

### Why ACES looks wrong today, and the fix path (sRGB linearization)

Game albedo textures are sRGB-encoded images sampled as if linear, so all
content enters the HDR pipeline "gamma-bright"; Hejl-Dawson looks right
only because the content was tuned against it. The canonical fix landed
in engine Session R (opt-in, gated by `test_srgb`):

```python
pipeline.set_srgb_inputs(True)     # or init kwarg srgb_inputs=True
```

This flags base-color AND emission stage textures under render as sRGB so
the GPU linearizes them on sampling — normal maps and metal-rough data
stay linear, as they must. Content loaded AFTER enabling needs a re-call
(the walk is idempotent). Two measured traps are handled inside the
implementation but worth knowing: already-prepared textures are released
so the format change actually reaches the GPU, and clear-color-only
placeholder textures cannot carry the decode (real image files can).
`set_srgb_inputs(False)` restores every format exactly.

**The verdict is on file** (engine arch doc §8): with linear inputs the
ACES wash-out is GONE — saturation and filmic contrast return — while
overall brightness drops because content was authored raw. Flipping the
default is therefore a CONTENT project: retune sun/exposure around linear
inputs, then sign off. Try it live in the testbed: `G` toggles the flag
scene-wide, `T` switches operators, `E` adjusts exposure; `--tonemap aces
--srgb` at boot for the A/B. (The older module-level
`make_base_color_textures_srgb(model_np)` still exists for
pipeline-less callers; the flag is the canonical path.)

---

## 5. Debug Visualization

`pipeline.set_debug_lighting(mode)` — modes are rendered instead of the
final shading (0 = off):

| Mode | Shows |
|---|---|
| 1 | World normals as RGB |
| 2 | Sun n·l grayscale (white = lit) |
| 3 | Sun direction as flat color (what the shader receives) |
| 4 | Position-derived normals (bypasses normal matrix) |
| 5 | n·l from position-derived normals |
| 6 | SIGNED n·l — green = lit, red = backlit (winding/inversion check) |
| 7 | Normal axis magnitudes (coordinate-system check) |
| 8 | Hardcoded-sun test (isolates uniform delivery) |
| 9 | Sun from float uniforms (isolates Vec3 conversion) |
| 10–16 | Shadow instruments (directional mode + shadows only): 10 shadow-map UV, 11 pure shadow term (the acne/bias tuning view), 12–16 coord/sampler probes — see engine arch doc §5 |

---

## 6. How to Verify Rendering Claims (do this instead of guessing)

**The testbed** — sun/planet/station/ships scene, starts in seconds, no
game systems:

```bash
cd C:/python/sfb2
python test3d_pax.py --pax3d --sun-mode directional --shadows
```

Hotkeys: mouse orbit; `1-4` focus; `W/A/S/D` move the sun; `T` tonemap;
`E` exposure; `B/U/J/I/K` bloom; `G` sRGB linearization; `N` sun mode;
`X` shadows; `L` TAA; `V` debug modes; `F9` screenshot; `H` help.
`--selftest` renders 30 frames offscreen and saves a screenshot (good for
scripted before/after comparisons). `--local` forces the legacy pipeline
for A/B.

**The engine harness** — programmatic checks (gamma curves, lit-hemisphere
per mesh type, shadow occlusion, rebuild survival):

```bash
C:/python/pax3d-env/Scripts/python.exe C:/python/pax3d/tools/paxtest/run.py
```

If you observe a rendering anomaly in the game: reproduce it in the testbed
first, then report it against the engine repo (ideally as a paxtest check).
That workflow is how the old "mystery bugs" (light formulas, washed-out
tonemaps, blocky bloom, skybox death) were all cracked.

---

## 7. Pitfalls (updated for pax3d_render)

- **`setShaderOff()` nodes still pass through tonemapping** (they render
  into the HDR buffer). Their brightness interacts with the operator —
  this is why legacy PBR compensation factors (0.45x sun etc.) exist.
  Don't remove those factors until bloom (R3) + linearization (R1) land.
- **Ambient**: if you ever remove ALL lights from render, PBR objects go
  full-bright (Panda reports pure-white `p3d_LightModel.ambient` when no
  lights are attached). Always keep the AmbientLight attached.
- **Don't create CommonFilters or a second FilterManager** alongside the
  pipeline — they fight over the window. Post-processing belongs in the
  engine pipeline.
- **Don't hand-position the sun light node** — `update_sun()` only.
- **`bloom_levels`, `msaa_samples` are init-time**; `enable_bloom`,
  `enable_taa`, shadows and sun mode are runtime-safe.
- `config/settings.json` is runtime-rewritten by the game and effectively
  not committed — treat flag flips there as local state, and record
  intended defaults in docs/handovers.

## 8. Newer Engine APIs — quick reference (Sessions D onward)

Everything below is **opt-in and byte-identical when unused** (the engine's
paxtest suite asserts exact opt-out restores). Full detail:
`pax3d/documents/PAX3D_RENDER_ARCHITECTURE.md`; planetside tuning guide:
`pax3d/documents/PLANETSIDE_LOOK_GUIDE.md`.

**Shadows (Sessions E–J — read arch doc §5.1 BEFORE sizing frustums):**

```python
pipeline.set_shadow_bias(0.5, world_units=True)   # ALWAYS set this first:
    # the 0.005 normalized default becomes ~20 IEU of offset at the game's
    # extent 500/4000 and silently erases every ship-scale shadow (§5.1)
pipeline.set_shadow_normal_bias(0.25)             # slope-scaled bias — THIS
    # CLOSES THE WEST-SUN / SUNSET SHADOW P0 (shadows "vanish" + terracing
    # at low sun): grazing-angle acne, root-caused Session I. Start at 0.25
    # world units, A/B at az 240 low sun. Full recipe:
    # pax3d/documents/OPENWORLD_FEEDBACK_RESPONSE_4.md (§5.2 in arch doc)
pipeline.set_shadow_filter_size(3)                # 3x3 PCF, softer edges
pipeline.exclude_from_shadows(np)                 # sky/FX/cloud geometry
    # (needs shadow_caster_mask=<free camera-mask bit> at init)
pipeline.set_shadow_texel_snap(True)              # Session J: stops shadow
    # edges shimmering when set_shadow_extent(center=...) follows the camera
pipeline.set_hardware_skinning(np, False)         # pin a problem rig to CPU
    # skinning (per-node; the rest of the scene stays on the GPU)
```

**Photo mode / kill-cam snapshots (Session AJ, 2026-07-27 — free for
planetside; built for the voxel game's AI-building loop, concordance
policy):**

```python
tex = pipeline.render_snapshot(pos, hpr, size=(1280, 720),
                               shadow_center=pos,   # recentre the sun
                               # frustum for the ONE frame (restored
                               # exactly) — planetside recentres extent
                               # on the player, so a far-away snapshot
                               # has no shadow coverage without this
                               filename='shot.png') # optional PNG write
    # ONE frame of the FULL pipeline (PBR/shadows/atmosphere/SSAO/
    # bloom/flare/tonemap) from any pose, into a RAM-backed texture,
    # WITHOUT perturbing the player's view (window keeps its last
    # frame; gated rms 0.0). Repeat shots 3-24 ms on a persistent
    # chain. fov/near/far default to copying the main lens. Limits:
    # the sky aux camera renders at its game-owned orientation (re-aim
    # it for off-pose shots); the viewmodel is excluded; no TAA.
    # Use cases here: photo mode, kill-cam, landing-site preview,
    # colony overhead shots. Gated by paxtest test_snapshot.
```

**Visibility-query validity (Session AJ — pairs with the Session AF
flare query):**

```python
pipeline.visibility_query_valid       # False = the depth source is
    # stomped (a viewmodel in depth_mode='clear'); every query then
    # fails CLOSED (visibility 0.0, q.valid False) instead of reading
    # "open sky everywhere". Gate flares on q.valid, and pass
    # on_depth_degrade='raise' to register_viewmodel_camera if your
    # systems require 'range' depth to actually hold.
```

**Character detail maps (Session AI, ER-014):**

```python
n = pipeline.set_detail_maps(actor)               # per-geom NORMAL/OCCLUSION
    # composition — renders the bakes' Normal + ORM sets without the unsafe
    # global define flip. Applies only where a normal-map stage AND tangent
    # column exist (normal) / an ORM stage exists (occlusion .r = AO);
    # skips ALPHA_MASK/GLASS/GPU_MORPHS geoms, so call it AFTER those.
    # Returns the geom count. Composes with set_hardware_skinning(np,
    # False) — the face-range CPU valve keeps its detail maps, shadows
    # stay correct (engine coordinates the two; flip order is free).
pipeline.set_detail_maps(actor, enabled=False)    # byte-identical restore
    # Session AJ: registration is APPEND-ONLY (new entries stamp only
    # their own geoms; no-valve removal is O(entry)) — safe to call
    # per-attach on streaming content (terrain chunks, spawned NPCs)
    # without O(total-registered) restamp storms.
```

**Logarithmic depth (Session D, R4.1):** `enable_log_depth=True` + widen
the lens (e.g. near 0.1 / far 1e9) — millimetre depth resolution at
planetary range. The game adopts this with the R4.2 camera-relative work.

**Planetside package (Session J — for planet-surface scenes; toggle all
three off for spaceflight):**

```python
pipeline.set_enable_atmosphere(True)              # aerial haze: distant
pipeline.set_atmosphere_params(                   # terrain fades into a
    haze_color=..., sun_haze_color=...,           # height-falloff haze with
    density=..., scale_height=...)                # a glow toward the sun
pipeline.set_hemisphere_ambient(sky, ground)      # two-tone ambient: sky
    # tint from above, ground bounce below — REPLACES the flat
    # AmbientLight level (keep a tiny one attached); clear_ambient_sh()
pipeline.set_shadow_texel_snap(True)              # (above — planetside win)
```

**Walkable-ship package (Sessions K–L — built for the Phobos Starhopper
class of asset: full interior, glass canopy, animated doors):**

```python
pipeline.set_glass(canopy_np)                     # transparency that KEEPS
    # its specular reflections (plain M_alpha scales the whole result by
    # alpha: a 0.15-alpha canopy loses 85% of its highlights). Apply to
    # the glass geoms only, and pair with:
pipeline.exclude_from_shadows(canopy_np)          # ...or the canopy casts
    # an opaque shadow and blacks out the cockpit
pipeline.set_double_sided_lighting(True)          # glTF doubleSided done
    # right: backfaces (interior walls, thin panels, decals) light from
    # the side actually facing the light. EYEBALL FIRST: two-sided
    # foliage/FX cards with visible backfaces will change look
pipeline.set_ambient_scale(interior_np, 0.15)     # damp the sky ambient
    # inside the hull (interiors otherwise glow like outdoors); direct
    # sun shafts, local lights, and emissive screens are untouched.
    # clear_ambient_scale(np) reverts
pipeline.set_atmosphere_scale(interior_np, 0.0)   # Session S: kill the
    # aerial-haze "cabin wash" on the interior subtree exactly — the
    # terrain seen through the windows keeps full haze.
    # clear_atmosphere_scale(np) reverts
pipeline.set_env_map(sky_cubemap)                 # Session M: specular IBL —
    # ADOPTED in planetside (2026-07-18): planetside/sky/envlight.py
    # binds every skybox's baked cubemap + SH automatically
    # (tools/bake_sky_ibl.py; PAX3D_FEEDBACK_3.md is the field report —
    # read it before tuning: E(up) anchoring + selective specular).
    # canopy glass and metallic hulls reflect the environment (roughness
    # picks the mip: sharp when smooth, blurry when rough). Feed a
    # GGX-prefiltered cubemap for correctness; plain cubemaps get auto
    # mips as an approximation. Pair the diffuse half from the same sky:
    # pipeline.set_ambient_sh(sh_from_cubemap(sky_cubemap))
    #
    # WORKED EXAMPLE (Session R — a real skybox end to end): the
    # openworld 006_Sunset HDRI is baked and shipped as
    # pax3d/tools/samples/sky006_sunset_ibl.txo. Recipe for ANY
    # equirect panorama (two commands, dev-time only):
    #   python pax3d/tools/gen_equirect_cubemap.py pano.hdr sky_cube.txo
    #   python pax3d/tools/gen_env_prefilter.py sky_cube.txo sky_ibl.txo
    #   tex = loader.load_texture('sky_ibl.txo')
    #   pipeline.set_env_map(tex)
    #   pipeline.set_ambient_sh(sh_from_cubemap(tex))
    # Orientation is settled — the tools follow the PINNED face table
    # (face 0=+x east ... a file-loaded up-face image's TOP row is the
    # SOUTHERN sky; arch doc 9 R5.2) — do not re-derive it. Content
    # caveat: check where a skybox's baked sun actually sits before
    # tuning ambient to it (006_Sunset's sun is SOUTH at the openworld
    # dome rotation, not west where the game's dusk sun is).
    # Eyeball: test3d_pax.py --pax3d --env full (M cycles off/spec/+SH).
pipeline.activate_model_lights(ship, scale=0.15)  # Session P: turn ON the
    # lights authored in Blender (KHR_lights_punctual) — they load as
    # real PointLight/Spotlight nodes but are inert until activated.
    # scale tames the physical units (I*4pi/683, inverse-square);
    # Blender sun lamps stay excluded (the pipeline owns the sun).
    # deactivate_model_lights(ship) restores exactly.
```

Config for this asset class: `use_normal_maps=True`,
`use_occlusion_maps=True` at init (both default False; the Starhopper
ships full normal + ORM sets). Interior lighting needs no new API —
point/spot lights scope per-room via `set_light()`, emission maps feed
bloom. Interior COLLISION (walk mode inside the hull):
`pax3d/documents/WALKABLE_INTERIOR_COLLISION_DESIGN.md` is the agreed
joint design with 10 measured engine facts — **§9 there answers the
wall-pusher questions**, including the one contract that will
otherwise bite: a directly-positioned walker must read the pusher's
corrected position back into sim state after traverse
(`sim_pos = walker_np.get_pos()`), or a held key walks through any
wall in ~7 frames.

**SSAO (Session S — interior/contact shading, the roadmap's Tier-1 ask):**

```python
pipeline = pax_pbr_init(..., enable_ssao=True, ao_radius=1.0,
                        ao_intensity=1.0)   # ao_samples=12 init-only
pipeline.set_enable_ssao(True)            # runtime toggle (rebuild-class)
pipeline.set_ao_radius(0.6)               # world units — ship-interior
    # scale wants roughly half a metre to a metre
pipeline.set_ao_intensity(1.5)            # strength; 0.0 = exact no-op
pipeline.set_ao_bias(0.02)                # raise if flat surfaces sparkle
```

Depth-only screen-space ambient obscurance: crevices, wall/floor
junctions, and clutter contact-darken. Measured guarantees: FLAT
geometry is byte-identical (AO is exactly 1.0 on planes — it can only
darken real concavities), opt-out and intensity-0 restore exactly, and
it works under msaa 4 and log depth (both gated). Honest scope: this
first slice darkens the full radiance (the classic SSAO compromise) —
eyeball under your harshest sun before shipping it on; the
indirect-only upgrade is on the engine roadmap.

**Lens flare/dirt (Session S — the R5 finale; needs bloom on):**

```python
pipeline = pax_pbr_init(..., enable_bloom=True, enable_lens_flare=True,
                        flare_strength=1.0)
pipeline.set_enable_lens_flare(True)      # runtime toggle (rebuild)
pipeline.set_flare_strength(0.6)          # 0.0 = exact no-op
pipeline.set_lens_dirt(loader.load_texture('dirt.png'), 0.5)
pipeline.set_lens_dirt(None)              # clean lens, exact restore
```

Ghosts source from the bloom bright extract, so occlusion is free (a
sun behind a hull stops flaring the moment its glow does) and ANY
bright emitter flares — twin suns and engine trails included. Tune
`flare_strength` low; flare is seasoning, not sauce.

**Orbital atmosphere (Session R, R5.5 — planets seen from space):**

```python
pipeline.set_orbital_atmosphere(planet_np,        # limb glow, halo beyond
    planet_radius=R)                              # the disk, blue haze over
    # the disk, soft reddened terminator. Earth-like defaults derive
    # from the radius alone; per-planet, unlimited planets, live-tunable
    # (re-call with any subset: scale_height, thickness, density,
    # scatter_tint, intensity). Mars dust: scatter_tint=(1.0,0.55,0.35).
    # planet_np's ORIGIN must be the planet center; radii in WORLD units
    # (node scale is NOT tracked — pass the scaled-up radius).
    # The halo follows the CURRENT update_sun() color, so blackbody sun
    # tints compose for free; the night side goes dark by itself.
pipeline.clear_orbital_atmosphere(planet_np)      # byte-identical restore
    # Boundary: ORBITAL view only — descending under the shell toward
    # terrain, hand off to the planetside enable_atmosphere at your
    # chosen altitude (look guide 6 has the rules of thumb).
    # Do NOT use camera-mask bit 30 for anything (pipeline-reserved).
```

Eyeball it: `python test3d_pax.py --pax3d --orbital` (O toggles,
Shift+O cycles earth/mars presets).

**Effect sprites (Session AD — baked explosion/impact footage; full
field guide: `pax3d/documents/BAKED_EFFECTS_GUIDE.md`):**

```python
meta  = json.load(open('assets/effects/explosion_5_1_flipbook.json'))
atlas = loader.load_texture('assets/effects/explosion_5_1_flipbook.png')
fx = pipeline.spawn_effect(atlas, meta=meta, pos=impact_pos,
                           size=9.0, emission_scale=2.0, fade_out=0.5)
    # ONE call plays a premultiplied flipbook atlas on a camera-facing
    # quad as pure emission: unlit by construction (sun/ambient/local
    # lights cannot tint it), HDR-legal (emission_scale > 1 feeds
    # bloom), coverage-weighted haze (fog can't paint the transparent
    # texels), shadow-excluded automatically. One-shots SELF-REAP when
    # playback ends — fire and forget. parent= makes it ride a ship;
    # billboard=False gives a static two-sided card.
    # fade_out=N (engine Session AI, game s731): coverage + emission
    # ramp to zero over the last N seconds — use it whenever the
    # footage's final frame is not fully transparent (baked smoke that
    # never dissolves holds a grey ghost card then pops off without it).
    # PACING TRAP: meta= wins over the fps kwarg. To change playback
    # speed, scale the meta dict once at load (meta['fps'] *= 2.0) —
    # passing fps= alongside meta= is silently ignored.
loop_fx = pipeline.spawn_effect(atlas, meta=meta, loop=True)
pipeline.remove_effect(loop_fx)   # loops and early cancels need this
```

Atlases come from `pax3d/tools/gen_flipbook.py` (alpha-aware — ProRes
4444 footage bakes with its alpha; the sidecar JSON is the `meta=`
dict). The CGVision explosion pack measured PREMULTIPLIED — bake
as-is. For impacts ON a surface spawn at `contact + normal * epsilon`,
or pass `depth_bias=`. Reference integration: planetside
`weapons/effects.py` — non-ground detonations play the fireball,
missing pipeline or atlas falls back to the corona, ~50 lines.

## 9. What's Coming (so you can plan game features around it)

Engine roadmap (see `pax3d/documents/PAX3D_MASTER_PLAN.md`): **R4.2**
camera-relative rendering is game-side work (anchor-relative positions in
Python doubles — after it, the wide frustum + log depth flip on and the
sky-camera dual-frustum architecture can retire); **R5** is now
essentially complete on the engine side — orbital scattering landed
Session R (§8 above), specular env maps / skybox ambient landed
Sessions M/Q; what remains is content adoption plus lens polish
(flare/dirt on the bloom chain, queued). **Landed in Session S** (the
walkable-ship interior package): `set_atmosphere_scale(np, k)` — the
per-node haze scale (the Phobos cabin-wash ask; 0.0 = no haze on the
interior subtree, windows still show hazed terrain), and per-node
`set_env_map(tex, node=np)` / `set_ambient_sh(coeffs, node=np)` /
`set_hemisphere_ambient(sky, ground, node=np)` binding (interior
reflections + ambient while the exterior keeps the sky) — all
paxtest-gated, byte-identical unless used. SSAO is the agreed next big
interior-look item. Each arrives harness-proven and opt-in, like the
features above.

## 10. Which Sections Are Yours (per-role routes)

**Ship interior dev (Phobos / Fenris):** §8 walkable-ship block is your
API surface; §10.1 below is the interior environment-lighting workflow;
collision + wall pusher: `pax3d/documents/
WALKABLE_INTERIOR_COLLISION_DESIGN.md` (§9 there = the pusher readback
contract + chunking recommendation, measured).

**Weapons / viewmodel dev:** §10.2 below — the "dark metal viewmodel"
problem has an engine answer now; the emissive-floor workaround can
retire once adopted.

**Terrain / planetside dev:** §8 planetside block for the APIs;
`pax3d/documents/PLANETSIDE_LOOK_GUIDE.md` is your tuning bible — §5
there is the expanded-terrain haze retune recipe (below-datum terrain
multiplies density fast; re-datum `base_height`, raise `scale_height`),
§7 the skybox→ambient+reflections recipe. Day-cycle rule from the
field: scale BOTH haze colors by the cycle luminance or distant hulls
paint bright against the night sky.

**NPC / character dev:** §10.3 below is the engine contract your baker
is built against — read it before changing bone counts, influences, or
material tricks.

### 10.1 Interior environment lighting (ship interiors — the current recipe)

The goal: the cabin reflects and is filled by a plausible INTERIOR
environment, not the sky. The mechanism (Session S): per-node
`set_env_map`/`set_ambient_sh` binding + `set_ambient_scale` +
`set_atmosphere_scale`. The workflow:

1. **Get an interior environment map.** Three sources, in order of
   effort: (a) any neutral interior HDRI (equirect panorama) — fastest,
   and plausible beats absent for interiors; (b) an offline Blender
   render of the actual cabin from its center saved as an equirect HDR
   (the ship .blend exists — one camera, cycles, low samples is fine
   for reflections); (c) in-engine capture via `base.win.makeCubeMap`
   with the rig parented to `render` (NOT the camera — measured trap),
   though exposure control makes offline easier.
2. **Bake it** (dev-time, two commands):
   ```
   python pax3d/tools/gen_equirect_cubemap.py cabin.hdr cabin_cube.txo
   python pax3d/tools/gen_env_prefilter.py cabin_cube.txo cabin_ibl.txo
   ```
3. **Bind it per subtree** (Session S — landed, paxtest-gated):
   ```python
   tex = loader.load_texture('cabin_ibl.txo')
   pipeline.set_env_map(tex, node=interior_np)
   pipeline.set_ambient_sh(pax3d_render.sh_from_cubemap(tex),
                           node=interior_np)
   ```
   The cabin reflects and is lit by its own environment while the
   exterior keeps the global sky map; `clear_env_map(node=np)` /
   `clear_ambient_sh(node=np)` revert to the inherited sky,
   byte-identical.
4. **Balance it.** `set_ambient_scale(interior_np, k)` still damps the
   result per-node (reflections are indirect light); with a real
   interior map you will likely RAISE k from the 0.15 sky-era value —
   the point of the interior map is that its ambient is already
   correct-ish for the space. And kill the cabin haze wash:
   `set_atmosphere_scale(interior_np, 0.0)` (Session S — exact no-haze
   on the subtree; the terrain through the windows keeps its aerial
   perspective).

### 10.2 Viewmodels (the "black metal pistol" fix)

The engine DOES have IBL (since Session M) — "the forward renderer has
no IBL" predates it. A dark full-metal viewmodel goes black because a
metal's diffuse term is zero: remove its light sources and only
specular remains, and with no env map bound there is nothing to
reflect. The fix is the same environment pair as §10.1: with
`set_env_map` + `set_ambient_sh` bound (sky outdoors, cabin indoors),
metallic surfaces always have something to reflect and the
`METAL_SCALE`/`ROUGH_FLOOR`/emissive-floor workarounds can retire.
Per-node trims if the weapon still reads dark against a hot sky:
`set_ambient_scale(weapon_np, k)` accepts k > 1.0 as a cheap fill
boost (it scales only indirect light — sun and lamps unaffected);
prefer fixing the environment first.

### 10.3 Character / skinned-asset engine contract (what the baker is built against)

- **Bone palette: sized by the content, not by us** (Session S;
  policy: UE5/Unity assets are the pipeline — no artificial caps).
  `max_skinning_bones='auto'` (init or
  `set_max_skinning_bones('auto')`) sizes `p3d_TransformTable` to the
  largest Character under render; **call
  `pipeline.refresh_skinning_budget()` after loading characters** —
  it re-resolves AND warns for any rig the active palette can't hold
  (the silent-exploded-skin failure now names itself; measured).
  Small rigs are unaffected at any size (identity padding, rms
  exactly 0). The hardware wall is ~240 joints (GPU uniform budget);
  your measured 151-bone `keyed` bake fits with room — re-bake and
  A/B whenever ready. Full-343 rigs verbatim await the queued
  texture-palette engine path.
- **4 bone influences per vertex** (`transform_weight`/`transform_index`
  vec4 — top-4 weighted blend). Exports already normalize to 4; more
  influences are silently truncated by the exporter, not the engine.
- **Hardware skinning is default-on and proven** (GPU == CPU to
  measurement, engine fact #13); shadows follow the posed skeleton
  (fact #7). If a specific rig ever misbehaves:
  `pipeline.set_hardware_skinning(actor_np, False)` pins that one
  character to CPU skinning (~per-character cost, scene stays GPU);
  report the rig to the engine with the repro.
- **Morph targets / blend shapes — MEASURED verdict (Session S,
  probe_morph.py, both engines identical):** under the default
  hardware skinning, slider-driven morphs are SILENTLY DROPPED (the
  slider exists, the CPU math applies it, the rendered vertices never
  move). The working path today:
  `pipeline.set_hardware_skinning(actor_np, False)` — that character
  renders morphs correctly on CPU skinning at per-character cost. So:
  sealed visors for crowds; a talking close-up character CAN morph if
  pinned to the CPU path. A GPU morph path is the engine upgrade if
  many simultaneous morphing characters ever land.
- **Character shadows**: set `shadow_bias_world` (~0.5) before judging
  — the normalized default erases person-height casters at game
  extents (§8; engine fact #8). Low-sun terracing/vanishing:
  `set_shadow_normal_bias(0.25)`.
- **Two-sided pieces** (hair cards, cloth flaps, decals): these light
  correctly only under `double_sided_lighting=True` (§8) — eyeball
  existing FX/foliage before flipping it on globally.
- **Emission masks**: the Blender exporter drops Principled
  "Emission Strength"-driven masks (bake-side limitation, not engine);
  route glow through emission COLOR (with an emission texture) and the
  engine's `use_emission_maps` path picks it up and feeds bloom.
- Measured-clip-speed sidecars (Walk 2.37 m/s etc.) and root-motion
  stripping are game-side pipeline patterns — the engine has no
  opinion, but foot-slide-free movement depends on them; keep them.
