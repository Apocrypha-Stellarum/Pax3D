# pax3d_render — Architecture & Maintainer's Guide

**Audience:** the AI/human dev working on the Pax3D engine repo.
**Package:** `C:\python\pax3d\pax3d_render\`
**Status:** Active — this is where ALL rendering work lands (see CLAUDE.md
working method). Game-side usage is documented separately in
`sfb2/documents/PAX_3D_ENGINE_AND_GRAPHICS/USING_PAX3D_RENDER.md`.
**Last updated:** 2026-07-18 (post Session J / planetside package)

---

## 1. Lineage and Design Intent

```
simplepbr 0.13.1 (Moguri, pip)
   └── graphics/pax_pbr (game repo, ~Feb-Mar 2026)
   │      custom sun uniforms, debug modes, bloom port, TAA, dither,
   │      geometric specular AA, disk-loaded shaders
   └── pax3d_simplepbr (this repo, Mar 2026) — bloom + tonemap operators
          │
          └──> pax3d_render (July 2026) = MERGE of both + R1/R2 additions
```

Design intent:
- **One pipeline, engine-owned.** The game consumes it via an opt-in flag;
  fixes land here exactly once.
- **Byte-compatible by default.** Every new behavior is opt-in
  (`sun_light_mode`, sRGB helpers); with defaults, output is identical to
  the game's legacy `graphics/pax_pbr`.
- **No game imports.** The package depends only on panda3d. Debug prints
  gate on `PAX3D_RENDER_DEBUG` env var or `debug=True`.

Files:

| File | Purpose |
|---|---|
| `__init__.py` | Exports (`init = Pipeline`), `configure_prc()`, `make_base_color_textures_srgb()` |
| `pipeline.py` | The Pipeline class — everything below |
| `shaderutils.py` | Loads `shaders/*` from disk, injects `#define`s, mechanical GLSL 120→330 upgrade |
| `shaders/pax_pbr.vert/.frag` | The PBR scene shader (metal-rough, IBL hooks, debug modes) |
| `shaders/tonemap.frag` | 4 operators + bloom composite + dither |
| `shaders/bloom_extract/downsample/upsample.frag` | Jimenez-style bloom chain (F3 fixed Session D — §9) |
| `shaders/taa_resolve.frag`, `passthrough.frag` | TAA resolve + copies |
| `shaders/shadow.vert/.frag` | Shadow-caster depth pass |
| `textures/` | Optional `brdf_lut.txo` (absent → 1×1 white fallback; only matters once env maps are used) |

---

## 2. Frame Anatomy

Default (no bloom, no TAA) — 2 passes:

```
render (PBR shader, HDR linear) ──> scene_hdr  RGBA16F + D24 [+MSAA]
                                        │
                                 tonemap.frag (operator + dither) ──> window
```

With bloom (`enable_bloom=True`) — 13 passes:

```
scene_hdr ──> bloom_extract (full res) ──> down×N (1/2 … 1/2^N)
                                              └──> up×N (tent + per-mip tint,
                                                          accumulating)
scene_hdr + bloom_result ──> tonemap (composite BEFORE tone curve) ──> window
```

With TAA (`enable_taa=True`), tonemap goes to an intermediate LDR texture,
then: `taa_resolve` (history blend + neighborhood clamp) → history copy →
passthrough to window. Camera gets per-frame Halton sub-pixel jitter from
the `_update` task.

All intermediate textures are RGBA16F — and since Session D this is true
of the actual framebuffers, not just the texture declarations: every bloom
`render_quad_into` passes explicit float fbprops. **Without fbprops,
FilterManager creates a default 8-bit FBO and the texture bind silently
rewrites the declared format to match** — that was the F3 root cause (§9).
Any new post pass that carries HDR data MUST pass float fbprops; the
paxtest `bloom_buffers_float` check guards the bloom chain. The scene
buffer is explicitly **linear** (`srgb_color=False`); sRGB encoding happens
exactly once, in `tonemap.frag` (explicit `pow(1/2.2)` for
ACES/Reinhard/Uncharted2; Hejl-Dawson bakes its own curve). **paxtest
`test_gamma` proves this chain matches the analytic curves — keep it that
way.**

Everything is orchestrated through Panda3D's `FilterManager`
(`render_scene_into` for the scene buffer, `render_quad_into` for each
post pass). A structural change (`enable_bloom`, `bloom_levels`,
`enable_taa`) destroys and rebuilds the whole FilterManager chain
(`_rebuild_tonemapping()`).

---

## 3. The Scene Shader and Its Defines

`_recompile_pbr()` compiles `pax_pbr.vert/.frag` with defines from
`_get_pbr_defines()` and applies the ShaderAttrib to `render`:

| Define | Driven by | Effect |
|---|---|---|
| `MAX_LIGHTS` | `max_lights` | Size of `p3d_LightSource[]` |
| `USE_NORMAL_MAP` | `use_normal_maps` | TBN normal mapping (needs tangents!) |
| `USE_EMISSION_MAP` | `use_emission_maps` | Emission texture sampling |
| `ENABLE_SHADOWS` | `enable_shadows` | Shadow-map sampling + per-light `v_shadow_pos` |
| `ENABLE_FOG` | `enable_fog` | Exponential fog |
| `USE_OCCLUSION_MAP` | `use_occlusion_maps` | AO from metal-rough texture R channel |
| `USE_330` | gl-version ≥ 3.2 | Mechanical 120→330 shader upgrade |
| `ENABLE_SKINNING` | `enable_hardware_skinning` | GPU skinning |
| `CALC_NORMAL_Z` | `calculate_normalmap_blue` | Reconstruct normal-map Z |
| `SUN_FROM_LIGHTSOURCE` | `sun_light_mode == 'directional'` | **R2**: sun via `p3d_LightSource` loop (§4) |
| `LOG_DEPTH` | `enable_log_depth` | **R4.1**: fragment-level logarithmic depth (§9) |
| `ENABLE_ATMOSPHERE` | `enable_atmosphere` | **R5.1**: aerial perspective / height haze (§9) — planetside, off for space |
| `GLASS` | `set_glass(np)` — per-NODE variant, never in the render-root compile | **Session K**: specular-preserving glass (§9) — alpha attenuates transmission terms only, premultiplied output |

Notable shader features already present (inherited from the game's fork):
geometric specular anti-aliasing (Kaplanyan-Hill), Eddington limb darkening
for stellar surfaces (`u_limb_darkening`), tangentless fallback (uses
`v_world_normal` when `USE_NORMAL_MAP` is off — procedural spheres have no
tangents), and 9 debug visualization modes on `u_debug_lighting` (world
normals, n·l, light dir, position-derived normals, signed n·l,
axis-magnitudes, hardcoded-sun test, float-uniform test).

### CRITICAL invariant: `_recompile_pbr()` preserves shader inputs

Shader inputs (`set_shader_input`) live inside the node's ShaderAttrib.
Runtime recompiles (`set_sun_light_mode`, `set_enable_shadows`) must
`prev.set_shader(new_shader)` on the EXISTING attrib — building a fresh
`ShaderAttrib.make(shader)` silently wipes every input on `render`
(u_sun_*, u_debug_lighting, camera_world_position, ...) and crashes the
next frame with "Shader input X is not present". This bug shipped once;
`test_shadows.py`'s toggle check guards it now.

---

## 4. Sun Lighting — the Two Modes (R2)

`sun_light_mode` selects how the sun reaches the shader. **The game-facing
API is identical in both modes:** `pipeline.update_sun(toward_sun_vec,
color_vec)` every frame.

### 'uniforms' (default — legacy, byte-identical to graphics/pax_pbr)

`update_sun` writes `u_sun_dir_world` / `u_sun_color`; the shader has a
dedicated world-space sun block. Directional lights in `p3d_LightSource[]`
are explicitly skipped. **No sun shadows possible** (no light node).

### 'directional' (R2 — the target mode)

The pipeline owns a `DirectionalLight('pax3d_sun')` attached to render.
The shader compiles with `SUN_FROM_LIGHTSOURCE`: the standard light loop
processes directional entries too (`position.w == 0` → the
`position.xyz - v_view_position * w` trick yields the view-space
toward-light vector; attenuation resolves to 1; spot terms self-disable).
Same BRDF, and the simplepbr shadow path works (§5).

`update_sun` in this mode orients the node and sets its color. The uniforms
are STILL updated every frame (debug modes visualize them; cheap).

### THE trap: node transform vs `_direction` (do not regress this)

`DirectionalLight` has two direction representations:
- the `_direction` field (`set_direction()`) — what the *lighting* math
  transforms by the node matrix;
- the node transform — what the *shadow camera* looks along.

`set_direction()` moves the light but NOT the shadow camera. Therefore the
pipeline NEVER calls `set_direction()`; it leaves `_direction` at its
default (+Y forward) and orients the NODE:

```python
travel = -toward_sun          # photon travel direction
H = atan2(-travel.x, travel.y)
P = atan2(travel.z, hypot(travel.x, travel.y))
sun_light_np.set_hpr(deg(H), deg(P), 0)
```

This maps node-forward exactly onto `travel`, so shader lighting
(`-(_direction · node_mat)` = toward-sun) and the shadow camera agree by
construction. This resolves the 2025-2026 "Formula B vs C" saga — the full
history is in `DIRECTIONAL_LIGHTING_PLAN.md` (historical).

Node position: the pipeline DOES position the sun node — that is how
`set_shadow_extent(center=...)` places the shadow frustum (Session D). A
DirectionalLight lights by orientation only, so position is
lighting-neutral (proven by paxtest `recenter_keeps_lighting`: lit values
identical after `set_pos`). Keep the node parented to render; only
`set_shadow_extent` writes its position, only `update_sun` writes its HPR.

---

## 5. Sun Shadows (R2)

Only in `'directional'` mode. Machinery is simplepbr's, inherited intact:

1. `dlight.set_shadow_caster(True, size, size)` creates the shadow buffer
   (`shadow_map_size`, default 2048).
2. The ortho lens is sized and placed by `set_shadow_extent(radius,
   depth, center)`: film `2r×2r`, near/far `±depth/2`, centered on
   `center` in world space (default world origin; centering = positioning
   the light node, lighting-neutral — see §4). **The caller must size AND
   place this** — e.g. the game should drive it from the current
   planet/station cluster each frame (uniform-cost, per-frame safe).
3. The `_update` task assigns the shadow depth shader
   (`shadow.vert/.frag`) to every shadow-casting light camera via
   camera initial-state override.
4. The vertex shader computes `v_shadow_pos[i] = shadowViewMatrix ×
   view_position` for every light; the fragment shader does the
   `sampler2DShadow` lookup with `global_shadow_bias` (param
   `shadow_bias`, default 0.005).

Runtime toggles: `set_enable_shadows(bool)` (recompiles the PBR shader +
configures the caster) — proven by `paxtest test_shadows` (lit 0.79 →
shadowed 0.09 → restored → re-shadowed).

Geometry outside the shadow frustum samples as LIT — undersized or
mis-centered extents produce shadow-free zones, not artifacts (proven by
paxtest `extent_miss_is_lit`). At planetary scales the game must drive
radius AND center from scene context (R2.4).

### 5.1 THE BIAS TRAP (read before sizing any shadow frustum)

`shadow_bias` is consumed in **normalized light-space depth**: its
world-space size is `bias × extent depth`. The 0.005 default is 0.3
units deep in paxtest's 60-unit frustum — but 12.5 m at an open-world
`set_shadow_extent(450, 2500)` and **20 IEU at the game's 500/4000**.
Any caster whose light-ray depth gap to its receiver is smaller than
that offset casts **no shadow at all, with no artifact hinting why**
(a standing character at 30° sun elevation has a ~2.4–3.6 m gap; a
building survives). This erased every character shadow in the openworld
build and was misdiagnosed there as a skinned-mesh engine bug
(Session E root-cause; see `OPENWORLD_FEEDBACK_RESPONSE.md`).

**Use world units instead:** `shadow_bias_world=<units>` (init) or
`set_shadow_bias(v, world_units=True)` (runtime, uniform-only). The
pipeline divides by the *current* extent depth and rescales on every
`set_shadow_extent`, so the offset stays physical. Measured record:
paxtest `shadow_quality` `bias_trap_at_scale` (erasure at defaults) /
`bias_world_units_restores` / `bias_world_extent_invariant`.

### 5.2 Grazing-angle acne & slope-scaled bias (`shadow_normal_bias_world`)

**The problem.** A *constant* depth bias (§5.1) is right for a receiver
facing the sun but wrong for one grazing it. On a receiver at angle θ to
the light, one shadow-map texel spans a receiver depth of
`texel_world × tan(θ)`, so a fragment can sit that far below the stored
depth and **self-shadow**. As the sun drops, `tan(θ)` grows — the open
ground breaks into fine terracing/acne bands whose severity scales like
**1/tan(alt)**. Because the acne darkens open ground, real cast shadows
lose contrast and read as *vanishing* — the exact openworld western-low-
sun signature (P0 addendum), reproduced byte-identically on stock 1.10.16
and Pax3D (so: GLSL, not C++). A bigger *constant* bias can't rescue it:
the value needed to clear the grazing acne is large enough to lift real
shadows off their casters everywhere else (peter-panning) — on varied
terrain no constant bias threads both.

**The fix.** `shadow_normal_bias_world=<units>` (init) or
`set_shadow_normal_bias(units)` (runtime, uniform-only) adds a bias term
proportional to `tan(θ)` — from `dot(n, l)` at the light-loop call site —
so it grows exactly where the receiver grazes and contributes ~nothing at
normal incidence. World-unit, rescaled by extent depth like
`shadow_bias_world`. **Default 0.0 = OFF = byte-identical** to the
constant-only path (opt-in; view-space NdotL == world-space NdotL, so the
angle is frame-invariant). The shader clamps `tan(θ)` at 8 so a near-
perpendicular receiver can't blow the bias up.

**Sizing.** To clear acne the slope term must exceed the half-texel
offset: `N × tan(θ) > 0.5 × texel_world × tan(θ)` — the `tan(θ)` cancels,
so **`N ≈ 0.5–1.0 × texel_world` clears acne at any angle**, while a real
shadow's depth gap (`caster_height / sin(alt)`, metres) is far larger and
survives. On sloped terrain the projected texel is larger than the flat
`texel_world`, so start at ~2–4× texel and tune up until the terracing is
gone, backing off if short/contact shadows start lifting. Measured record:
paxtest `shadow_grazing` (acne 0.13 → 0.00 with the real umbra kept, and
`over_bias_erodes_shadow` proves the umbra check has teeth); real-terrain
proof: `probe_openworld_scale.py --normal-bias` over the village GLB at
az 240 (terracing gone, building/tree shadows kept).

### 5.3 Filtering: `shadow_filter_size` (1 | 3)

Default 1 = the original single hardware-PCF tap (byte-identical).
3 = 3×3 multi-tap PCF (9 hardware taps one texel apart via
`u_shadow_texel`), visibly softer and more stable edges — measured:
edge transition 6 px → 16 px with interior/lit luminance unchanged
(`pcf_edge_softens` / `pcf_interior_unchanged`). Runtime:
`set_shadow_filter_size(n)` (recompile-class). Interaction to know:
multi-tap sampling on a sloped receiver needs
`bias_world ≥ texel_world × tan(slope-vs-light)` or open surfaces can
self-shadow. At real map densities a large constant bias "clears" this
only by erasing real shadows — the correct lever at grazing angles is the
slope-scaled bias (§5.2), not a bigger constant one.

### 5.4 Opting out of casting: `exclude_from_shadows(np)`

Configure a dedicated camera-mask bit for the sun's shadow camera
(`shadow_caster_mask=<bit index or BitMask32>`, or
`set_shadow_caster_mask()`), then `pipeline.exclude_from_shadows(np)` /
`include_in_shadows(np)`. The node stops writing the sun depth map but
stays visible to every other camera (Panda visibility is
camera-mask ∩ node-show-mask). Use for clouds, sky geometry, FX quads —
anything whose depth footprint would blanket the scene (a drifting
cloud crossing the sun ray shadows the whole map). Assigning the mask
alone changes nothing; nodes cast by default. Proven by
`nocast_excluded_ground_lit` / `nocast_still_visible_to_camera`.

### 5.5 Skinned casters — proven working (Session E)

The depth pass renders skinned Characters correctly: hardware AND CPU
skinning, egg- and glTF-loaded (`panda3d-gltf` + `Actor`), GLSL 120 and
330, including posed joints (the shadow follows `control_joint`, not
the bind pose). `StandardMunger` converts blend tables to the hardware
path per-state (the shadow attrib carries `F_hardware_skinning`), and
the GL layer pads short/missing transform tables with identity — so the
always-on `ENABLE_SKINNING` depth shader is safe for static meshes too.
Guarded permanently by test_shadows `skinned_*` + `gltf_caster_*`
checks (depth-map texel-diff instrument in `common.py`). Any report of
"skinned meshes don't cast" should first rule out §5.1 (the bias trap
erases short casters — characters — while sparing tall ones) and
measurement contamination by co-located proxy geometry.

Shader debug modes for shadow work: `set_debug_lighting(10)` = light-0
shadow-map UV + depth ref, `11` = shadow term (openworld contribution,
permanent) — now sampled with the same slope-scaled bias as the lit pass,
so grazing acne shows at `shadow_normal_bias_world=0` and clears as it is
raised. Modes 12–16 are the Session H probe instruments.

### 5.6 Per-node skinning path: `set_hardware_skinning(np, enabled)` (Session G)

`pipeline.set_hardware_skinning(np, False)` pins a subtree to the
CPU-skinning path while the rest of the scene stays on the GPU;
`clear_hardware_skinning(np)` reverts to the pipeline-wide flag. Built as
the openworld P1 safety valve (global CPU skinning cost them 112→8 fps;
per-node costs only the affected characters).

Mechanism (all engine-native, zero cost when unused): a **flag-only**
`ShaderAttrib` is composed onto the node — `ShaderAttrib` flags compose
per-bit (`_has_flags` masking), so the shader and its inputs are inherited
unchanged and only `F_hardware_skinning` flips. `StandardMunger` reads the
flag from the NET composed state per Geom, so the opted-out node's
vertices are CPU-animated while its neighbors keep the GPU palette. The
attrib rides at **override 2**, outranking the shadow camera's
initial-state attrib (override 1) — the depth pass follows the same
per-node path, so shadows keep matching the visible pose. The always-on
`ENABLE_SKINNING` shader block degrades to identity for CPU-skinned data
(no transform_index/weight columns → GL default attribs + identity
palette), so one compiled shader serves both paths. Proven by
test_skinning: pixel-exact vs the GPU path on the same pose, shadow
follows pose while opted out, round-trip restores exactly.

### 5.7 Texel snapping: `shadow_texel_snap` (Session J — planetside)

A shadow frustum that follows the camera (the planetside pattern —
openworld drives `set_shadow_extent(center=cam)` per frame) re-rasterizes
the depth map on every sub-texel center move, making every shadow edge
crawl while the viewer walks. With `shadow_texel_snap=True` (init) or
`set_shadow_texel_snap(True)` (runtime, uniform-cost) the pipeline
quantizes the frustum center to multiples of the texel's world size
(`2*extent / shadow_map_size`) along the light's film axes before
positioning the node, so the map only re-rasterizes on whole-texel steps.
Snapping is always FROM the caller's stored ideal center (no drift), the
grid re-derives when `update_sun` rotates the light, and geometry coverage
is unaffected (the center moves by at most half a texel — size extents
with a half-texel margin as you already should). Default OFF =
byte-identical. Measured record: `test_shadow_snap` (0.3-texel move flips
24 depth texels unsnapped, 0 across a snapped sub-texel sweep, 152 on a
2-texel step — the frustum follows, it is not frozen).

---

## 6. Auxiliary Scene Cameras (R1 — the skybox-death fix)

External code must never hunt for the FilterManager buffer (the game's old
sky camera found it once at init and died on every rebuild — failure F4).
Instead the pipeline owns auxiliary display regions:

```python
reg = pipeline.register_scene_camera(cam_np, sort=-100,
                                     clear_color=(0,0,0,1),
                                     clear_depth=True, name='sky_camera')
pipeline.unregister_scene_camera(reg)
```

Internals: `_attach_scene_camera` makes a DR on `_filtermgr.buffers[0]`
with the given sort/clears; for any background camera (sort < 0) the MAIN
scene DR is set to color-clear OFF / depth-clear ON (preserves background
pixels, standard sky-camera contract). `_setup_tonemapping()` ends with
`_reattach_scene_cameras()`, so every rebuild (bloom/TAA toggles) re-creates
all registered DRs on the new buffer. Proven by `paxtest test_rebuild`
(manual-discovery pattern dies, registration survives).

Caller keeps ownership of the camera node: lens, camera masks, scene root,
transform sync are the caller's business (the game's `sky_camera.py` shows
the pattern and auto-uses this API when available).

Gotcha for tests/tools: the FilterManager buffer appears in
`GraphicsEngine`'s window list only after a frame renders — anything doing
manual discovery must render ≥1 frame first (the registration API is
immune; it holds the buffer object directly).

---

## 7. Runtime Parameter Model

Three cost classes — keep new parameters within this taxonomy:

| Class | Cost | Parameters / methods |
|---|---|---|
| Uniform-only | free, per-frame safe | `set_exposure`, `set_tonemap_operator`, `set_bloom_strength`, `set_bloom_intensity`, `update_sun`, `set_debug_lighting`, `set_shadow_extent`, `set_shadow_bias`, `set_shadow_normal_bias` (slope-scaled, §5.2), `set_shadow_caster_mask`, `set_shadow_texel_snap` (§5.7), `exclude_from_shadows`/`include_in_shadows`, `set_hardware_skinning`/`clear_hardware_skinning` (per-node state change; no recompile), `set_atmosphere_params` (§9 R5.1), `set_ambient_sh`/`set_hemisphere_ambient`/`clear_ambient_sh` (§9 R5.2), `set_glass` (§9 Session K; per-node state change — lazy one-time variant compile on first use, tracked across recompiles) |
| Shader recompile | one hitch; **must preserve inputs** (§3) | `set_sun_light_mode`, `set_enable_shadows`, `set_enable_log_depth`, `set_shadow_filter_size`, `set_enable_atmosphere` |
| FilterManager rebuild | frame hitch; aux cameras auto-reattach | `set_enable_bloom`, `set_enable_taa`, (`bloom_levels`, `msaa_samples` at init) |

Constructor parameters (all keyword): `render_node, window, camera_node,
taskmgr, msaa_samples=4, max_lights=8, enable_shadows=False,
use_normal_maps=False, use_emission_maps=True, use_occlusion_maps=False,
enable_fog=False, exposure=0.0, shadow_bias=0.005,
shadow_bias_world=None, shadow_normal_bias_world=0.0,
shadow_filter_size=1, shadow_caster_mask=None,
enable_hardware_skinning=True, calculate_normalmap_blue=True,
enable_bloom=False, bloom_strength=1.0, bloom_intensity=1.0,
bloom_levels=5, tonemap_operator='aces', enable_taa=False, debug=False,
sun_light_mode='uniforms', shadow_map_size=2048, enable_log_depth=False,
shadow_texel_snap=False, enable_atmosphere=False,
atmo_haze_color=(0.60, 0.71, 0.85), atmo_sun_haze_color=None,
atmo_sun_power=8.0, atmo_density=0.002, atmo_scale_height=60.0,
atmo_base_height=0.0` — unknown kwargs are swallowed (`**_kwargs`) for
forward/backward compatibility with the game's call sites.

---

## 8. Color Pipeline — Verified State and Remaining Work

Verified by `paxtest test_gamma` (both engines, both GL baselines):

- Post chain is analytically correct for ALL operators (ACES, Reinhard,
  Uncharted2, Hejl-Dawson) and the EV exposure path. There is NO
  double-gamma. Do not "fix" the tonemap shaders.
- **Inputs are NOT linearized**: 8-bit textures are sampled raw. Game
  content is sRGB-encoded and hand-tuned around Hejl-Dawson, which is why
  correct operators look washed out on it.

Remaining R1 work: roll out input linearization —
`make_base_color_textures_srgb(nodepath)` flags modulate-stage textures as
`F_srgb`/`F_srgb_alpha` (normal/metal-rough stay linear!), then retune
sun/ambient/exposure. This is a content-facing change; keep it opt-in and
A/B it in the testbed (`G` key toggles it live).

GLSL: sources are 120 with a mechanical 330 upgrade in `shaderutils`
(`--baseline modern` / `gl-version 3 2`). R1.4 plans to delete the 120 path
once the game runs on gl-version 3 2 — do it in one sweep, verified by the
full paxtest matrix under both baselines before/after.

---

## 9. Known Defects / Where the Next Phases Land

### F3 — Blocky bloom — FIXED (Session D, 2026-07-17)

`test_bloom` is green at both resolutions, both engines, both GL
baselines. The fix was three defects, in order of importance:

1. **Root cause — 8-bit intermediate FBOs.** The bloom `render_quad_into`
   calls passed no fbprops, so FilterManager created default 8-bit
   framebuffers and the texture bind silently rewrote the declared RGBA16F
   format to match. The extract's `*0.005` scale then crushed the halo
   tail into a handful of 8-bit codes; the tonemap amplified each 1-code
   step into a visible band. Diagnostic trap for posterity: the banding
   shows up as *texel-aligned flat plateaus with 1px cliffs*, which
   perfectly mimics nearest-neighbor sampling and misdirects toward
   filter state. It was cornered by reading back the intermediates
   (`RTM_copy_ram`) and noticing every value was exactly n/255. Fixed by
   passing explicit float fbprops (`bloom_fbprops`) to every bloom pass;
   guarded by the `bloom_buffers_float` check in test_bloom.
2. **Downsample kernel typo** (`bloom_downsample.frag`): the four corner
   boxes of the 13-tap Jimenez kernel must each include the center sample
   `a`; the code had `b`/`c` in its place, over-weighting the two -y inner
   taps (kernel summed to 1.125, vertically lopsided). This was the
   up/down halo asymmetry (~0.05–0.07 delta, left/right ~0). Now sums to
   exactly 1.0 and is symmetric.
3. **Upsample tent on the wrong input** (`bloom_upsample.frag`): the
   9-tap tent was applied to the same-res downsample (near no-op) while
   the coarser accumulator — the texture actually being magnified — got a
   single bilinear tap. Now the tent filters the coarser accumulator
   (Jimenez-style progressive upsample; `texel_size` = accumulator texel)
   and the same-res source gets one exact tap, keeping the per-mip tint
   on the source contribution as before.

Also hardened: all bloom textures get explicit bilinear + clamp-to-edge
(`_set_bloom_filtering`) — the Panda default wrap is repeat, which bled
the halo across screen edges.

Remaining R3 (content, not correctness): retune strength/intensity/tints
in the testbed (`--bloom`, U/J/I/K) — brightness rose because the tail is
no longer quantized to zero and HDR extract values survive; the per-mip
tint indexing also reads inverted vs its comment labels (finest mip gets
the "deep warm outer" tint) — decide intent when retuning.

### R4.1 — Logarithmic depth (LANDED, opt-in — Session D addendum)

`enable_log_depth=True` (constructor or `set_enable_log_depth()`, a
shader-recompile-class toggle). The PBR shader then writes fragment-level
logarithmic depth:

- vertex: `v_log_depth_w = 1.0 + gl_Position.w`
- fragment: `gl_FragDepth = log2(max(v_log_depth_w, 1e-6)) *
  u_log_depth_coef` where `u_log_depth_coef = 1 / log2(1 + far)`.

The pipeline reads the camera lens' far plane EVERY FRAME for the
coefficient — the caller owns the lens and should widen it when enabling
(the point of log depth is a huge frustum, e.g. near 0.1 / far 1e9;
depth resolution at 2500 IEU goes from ~1.9 IEU linear to ~0.003 IEU).
Acceptance: `paxtest test_scale --log-depth` (the runner's
`scale/pax3d_render @logdepth` row) — a 6-step sub-resolution sweep that
must order two surfaces 1 IEU apart at 2500 IEU at every step. Verified
under GLSL 120 + 330, stock + Pax3D engines.

Notes:
- Fragment-level (not vertex-level) so long triangles interpolate
  correctly; costs early-Z for pax_pbr-shaded geometry — acceptable in
  sparse space scenes.
- The SHADOW pass deliberately does NOT use log depth: the sun shadow
  camera is an orthographic lens, whose linear depth is already uniform —
  applying the formula there (w≡1) would be wrong.
- Sky-object shaders (game-side) don't compile with LOG_DEPTH; they render
  in separate-DR passes today. They adopt the formula when the sky camera
  retires (later R4).
- Z-fight probing is sweep-based for a reason: a single frame can tie-break
  uniformly in the correct surface's favor and mimic a working depth
  buffer (observed in the harness).

### R4.2 — Camera-relative rendering (the chosen path, 2026-07-17)

`test_scale`'s `precision_off_origin` checks (0.24% pixel drift at 1.2e6
IEU, 22% at 1.2e7, rotated camera required) document the engine baseline.
The doubles engine build is shelved (compile cost); camera-relative
placement is the path, and it is GAME-side work — the pipeline needs
nothing new:

- **The contract:** node positions handed to Panda must be
  `sim_pos - anchor` computed in PYTHON DOUBLES, anchor near the camera.
  Never store sim-scale coordinates in node transforms expecting a parent
  at -anchor to cancel them: float32 storage quantizes locals BEFORE
  composition (~1 IEU spacing at 1.2e7) — machine-proven by
  `trap_parent_cancel_quantizes` in test_scale (8.5% pixel displacement
  for a ship 1.5 IEU from its anchor).
- **The pipeline is already rebase-safe:** camera_world_position, the
  log-depth coefficient, and the shadow-extent center are all recomputed
  per frame; the sun is direction-only. Rebasing the scene between frames
  requires no pipeline calls.
- Game integration goes through the nested-space architecture (deep-space
  mode already anchors the ship at origin — generalize that), owned in
  the game repo.

### R5.1 — Aerial perspective / height haze (LANDED opt-in, Session J)

**Planetside feature — off by default and byte-identical when off; space
scenes never enable it.** `enable_atmosphere=True` (init) or
`set_enable_atmosphere()` (recompile-class) compiles `ENABLE_ATMOSPHERE`
into the PBR shader: an exponential-height medium
(`density(z) = density * exp(-(z - base_height) / scale_height)`) whose
optical depth along the camera→fragment ray is integrated analytically —
no ray marching, a handful of ALU per fragment. Distant geometry fades
into `haze_color`, blended toward `sun_haze_color` by a
`pow(cos_angle_to_sun, sun_power)` forward-scattering lobe, so the haze
glows around the sun direction. Applied in linear HDR after emission
(extinction affects emitters too), before the tonemap; alpha untouched;
debug modes override it (instruments stay pure). If the legacy
`ENABLE_FOG` is also compiled in, fog applies first.

Parameters are uniform-only via `set_atmosphere_params(haze_color,
sun_haze_color, sun_power, density, scale_height, base_height)`. Rules of
thumb: 1/density is the distance to ~63% haze; match `haze_color` to the
skybox horizon (the shader has no sky — background matching is content
work); `scale_height` sets how far above the ground the haze dies.
`density=0` is an exact no-op even when compiled in. Heights are world-z
(the shader's world frame is Panda Z-up — same frame as
`u_sun_dir_world`). Measured record: `test_atmosphere` (transmittance
matches `curve(haze*(1-exp(-density*d)))` to 3 decimals at three
distances, height falloff analytic, sunward tint, byte-identical opt-out).

### R5.2 — Environment-driven ambient via irradiance SH (LANDED, Session J)

The IBL plumbing that shipped zeroed since R1 (`sh_coeffs[9]`) is now
fed by three uniform-only APIs — **zero shader changes**, and zeros (the
default) remain byte-identical to the pre-R5 pipeline:

- `set_hemisphere_ambient(sky_color, ground_color, up=(0,0,1))` — exact
  SH bands 0–1 for a two-tone environment: up-facing surfaces receive
  `base * (avg + 2/3*delta)`, down-facing the ground-bounce complement,
  smoothly blended by the world normal. THE cheap planetside win: shadow
  sides pick up sky tint, undersides get bounce. Replaces (don't stack
  with) the flat AmbientLight — keep any AmbientLight small.
- `set_ambient_sh(coeffs)` — raw 9×RGB irradiance-convolved
  coefficients, shader slot order `[1, x, z, y, xz, yz, xy, 3z²-1,
  x²-y²]` (simplepbr constants).
- `clear_ambient_sh()` — back to zeros, byte-identical restore.
- `sh_from_cubemap(tex)` (module-level, EXPERIMENTAL) — CPU projection of
  a loaded cubemap to those 9 coefficients (call once at scene setup).
  The up/down axis and DC term are validated; confirm horizontal
  orientation against a real skybox before tuning content to it.

The custom coefficients survive shader recompiles
(`_set_env_map_uniforms` re-pushes the CURRENT set — the §3 invariant
extended). Specular IBL (filtered env cubemap) remains future R5 work.
Measured record: `test_ambient_sh` (per-channel analytics exact through
the tonemap curve; recompile survival; cubemap projection matches the
analytic hemisphere at 0.0%).

### Session K — Specular-preserving glass: `set_glass(np)` (LANDED, opt-in)

First slice of the walkable-ship asset-enablement queue (master plan
§4.8; motivating asset: the Phobos Starhopper cockpit canopy). The
defect, measured: standard `M_alpha` blending multiplies the ENTIRE
shaded result by alpha, so a canopy at alpha 0.15 keeps 15% of the
specular highlight that makes glass read as glass (test_glass: 2.07×
luminance loss at the analytic highlight).

`pipeline.set_glass(np)` switches the subtree to:

- a `GLASS`-defined compile of the SAME PBR shader — the render-root
  compile is textually unchanged, so default rendering is byte-identical
  by construction. In the variant, alpha attenuates only
  transmission-class terms (diffuse, flat + SH ambient; fog and
  atmosphere inscatter are coverage-weighted); specular — sun, local
  lights, IBL — and emission add at full strength (the glTF-viewer
  semantic for BLEND materials). Output is premultiplied.
- `TransparencyAttrib.M_premultiplied_alpha` at override 1, outranking
  the geom-level `M_alpha` that panda3d-gltf stamps on BLEND materials.

Mechanics worth knowing: the variant is compiled lazily (one hitch on
first `set_glass`) and re-pushed after every recompile-class toggle
(`_reapply_glass_shaders` — the §3 invariant extended to per-node
variants); the node's prior TransparencyAttrib (+override) is saved so
`set_glass(np, False)` is a byte-identical restore; the shadow camera's
override-1 initial state outranks the node-level shader, so the depth
pass is untouched — glass still casts an OPAQUE shadow unless you pair
with `exclude_from_shadows(np)` (you almost always should, or the
canopy blacks out the cockpit). Apply to the glass geoms only, never a
parent shared with opaque meshes; keep multi-layer glass as separate
geoms so the transparent bin can sort them.

Measured record: `test_glass` (both-path analytics exact through the
tonemap curve — legacy 0.289/0.290, glass 0.599/0.599, transmission
through to a known background 0.753/0.753; recompile survival rms 0;
opt-out rms 0; @directional variant covers the light-loop split).

---

## 10. Testing Contract

- Every feature has (at least) one paxtest: gamma, lighting (×sun-modes),
  bloom, rebuild, the shadow suite (shadows/gltf/quality/grazing/snap),
  skinning, ftl_blur, scale (+@logdepth), atmosphere, ambient_sh, glass
  (×sun-modes). Run `tools/paxtest/run.py` before and after.
- Add a test WITH the feature, not after. Analytic checks > goldens;
  goldens (`--golden` / `--check-golden`) are a refactor safety net.
- The testbed (`sfb2/test3d_pax.py`) is the eyeball companion — its
  `--selftest` mode (offscreen, 30 frames, screenshot) is scriptable.
- Harness gotchas encoded in the tests (keep them in mind for new ones):
  attach a small `AmbientLight` in lighting tests (with NO lights attached,
  `p3d_LightModel.ambient` is pure white and floods PBR output); render a
  frame before any manual buffer discovery; sample bar/halo centers to
  dodge the tonemap dither.
