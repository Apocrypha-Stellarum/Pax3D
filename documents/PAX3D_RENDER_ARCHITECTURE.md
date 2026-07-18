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
| `DOUBLE_SIDED_LIGHTING` | `double_sided_lighting` | **Session K**: backfaces shade with the inverted normal (glTF doubleSided semantic, §9) — front faces bit-identical |

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
| Uniform-only | free, per-frame safe | `set_exposure`, `set_tonemap_operator`, `set_bloom_strength`, `set_bloom_intensity`, `update_sun`, `set_debug_lighting`, `set_shadow_extent`, `set_shadow_bias`, `set_shadow_normal_bias` (slope-scaled, §5.2), `set_shadow_caster_mask`, `set_shadow_texel_snap` (§5.7), `exclude_from_shadows`/`include_in_shadows`, `set_hardware_skinning`/`clear_hardware_skinning` (per-node state change; no recompile), `set_atmosphere_params` (§9 R5.1), `set_ambient_sh`/`set_hemisphere_ambient`/`clear_ambient_sh` (§9 R5.2), `set_env_map`/`clear_env_map` (§9 R5.3), `set_glass` (§9 Session K; per-node state change — lazy one-time variant compile on first use, tracked across recompiles), `set_ambient_scale`/`clear_ambient_scale` (§9 Session L; per-node inherited input), `set_atmosphere_scale`/`clear_atmosphere_scale` (§9 Session S; per-node inherited input scaling the R5.1 optical depth — hull interiors), `activate_model_lights`/`deactivate_model_lights` (§9 Session P; scene-graph state only) |
| Shader recompile | one hitch; **must preserve inputs** (§3) | `set_sun_light_mode`, `set_enable_shadows`, `set_enable_log_depth`, `set_shadow_filter_size`, `set_enable_atmosphere`, `set_double_sided_lighting` (§9 Session K) |
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

**R1.3 input linearization: EXPERIMENT LANDED, gated (Session R).**
`pipeline.set_srgb_inputs(True)` (+ init kwarg `srgb_inputs`) flags
base-color (M_modulate) AND emission (M_emission) stage textures under
render as `F_srgb`/`F_srgb_alpha`; normal/metal-rough/data textures
stay linear. Disabling restores every format exactly. Content loaded
after enabling needs a re-call (idempotent walk). Two measured traps
baked into the implementation: prepared textures must be RELEASED on
format change or the GPU keeps sampling the old internal format
(`release_all()` — silently inert otherwise), and clear-color-only
textures (no RAM image) round-trip their value regardless of format —
they cannot carry the decode (real content always has RAM images).

Gate: `test_srgb` — metallic-1 cards collapse the ambient term to
`base * A`, so an 8-bit 128 texel must land on curve(0.2159) decoded vs
curve(0.5020) raw, exactly, through hejl/aces/reinhard/uncharted2;
opt-out rms exactly 0.0. Green both engines x both baselines.
**The Session A ACES prediction is VERIFIED in the testbed**
(`--tonemap aces --srgb` A/B): linear inputs kill the wash-out —
saturation and filmic contrast return — while overall brightness drops
(content was authored raw; adoption needs a sun/exposure retune).
DEFAULT STAYS OFF until the game signs off content-side; the
`gen_env_prefilter` raw-value note holds unchanged (this flag touches
stage textures at runtime, not baked artifacts).
The older module-level `make_base_color_textures_srgb(nodepath)`
remains for pipeline-less callers; the flag is the canonical path
(testbed: `G` toggles live, `--srgb` at boot).

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

**Per-node scale (Session S — the Phobos "cabin wash" ask):**
`set_atmosphere_scale(np, k)` / `clear_atmosphere_scale(np)` — the
hull-interior companion to `set_ambient_scale`, same mechanism: an
inherited shader input (`u_atmo_scale`, root default 1.0 = exact IEEE
no-op) that multiplies the OPTICAL DEPTH. `k=0` makes tau exactly 0 —
bit-identical to `density=0` for those fragments, so an interior mesh
group carries no haze at all while terrain seen through the windows
keeps full aerial perspective; intermediate values behave as
proportionally thinner air (tau scales linearly, so analytics stay
closed-form). Composes with glass (the coverage-weighted inscatter
uses the same tau). Measured record: `test_atmosphere`
`atmo_scale_*` checks (scale-1.0 rms 0; scale-0.5 analytic exact with
the sibling unaffected; scale-0.0 == density-0 at rms 0; clear
restores byte-identically) — green both engines × both baselines.

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
- `sh_from_cubemap(tex)` (module-level) — CPU projection of a loaded
  cubemap to those 9 coefficients (call once at scene setup). Face
  table PINNED (Session Q): file/face 0 = +x east, 1 = -x west,
  2 = +y north, 3 = -y south, 4 = +z up, 5 = -z down; a file-loaded
  up-face image's TOP row is the SOUTHERN sky. Proven on all three
  legs — shader sampling (test_env_map mirror proof), win.makeCubeMap
  captures (openworld marker rig, 2026-07-18; parent the capture rig
  to render, not the camera), and loader.load_cube_map image files
  (test_ambient_sh checks 6-8).

The custom coefficients survive shader recompiles
(`_set_env_map_uniforms` re-pushes the CURRENT set — the §3 invariant
extended). Specular IBL landed as R5.3 below (Session M).
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

### Session K — Double-sided lighting: `double_sided_lighting` (LANDED, opt-in)

Second slice of the walkable-ship queue (master plan §4.8). The shader
historically shaded backfaces with the FRONT face's normal, so glTF
`doubleSided` materials (thin panels, decals, seat fabric, interior
walls) seen from behind lit from the wrong side — ambient-only black
under direct sun (test_doublesided measures 0.108 vs the correct
0.705 at the analytic scene).

`double_sided_lighting=True` (init kwarg) / `set_double_sided_lighting()`
(runtime, recompile-class) compiles in the Khronos sample-viewer
semantic: `if (!gl_FrontFacing) { n = -n; world_normal = -world_normal; }`
right after normal derivation, so every consumer — both sun paths, the
light loop, IBL, the slope-scaled shadow bias — sees the flipped
normal. Front faces take the no-op path and are BIT-identical to the
flag-off compile (asserted), so single-sided content cannot change;
default off is byte-identical for everything, because existing
two-sided content with visible backfaces (foliage cards, FX quads)
WOULD change appearance — the games opt in after eyeballing. Glass
variants inherit the define automatically (shared `_get_pbr_defines`).

Measured record: `test_doublesided` (front/back analytics exact both
flag states; flag-on front vs flag-off front rms 0; opt-out rms 0;
@directional variant covers the view-space flip in the light loop).

### Session L — Per-node ambient scale: `set_ambient_scale(np, k)` (LANDED)

Third slice of the walkable-ship queue (§4.8), prioritized first by the
ship's integrating dev: the hemisphere/SH ambient models open sky, so a
hull interior floods with sky light as if outdoors — "the interior is
unlit without it" (dark where it should be dark, so its real lights can
read).

`set_ambient_scale(np, k)` sets the inherited shader input
`u_ambient_scale` on the subtree (root default 1.0 — an EXACT no-op,
IEEE `x*1.0 == x`, asserted). The shader folds it into the
ambient-occlusion factor, which multiplies precisely the indirect
terms — SH/IBL and the flat AmbientLight ambient, including their
GLASS-variant splits — and nothing else: direct sun through a canopy
still lights the deck, local point/spots work normally, emissive
screens still glow. `clear_ambient_scale(np)` reverts to the inherited
default, byte-identical. Uniform-cost, no recompile, composes with
`set_glass` and `use_occlusion_maps`. Typical interior values: 0.1–0.2
on the interior mesh group (the Starhopper splits
exterior/interior/cockpit meshes, so the group is directly taggable).

Measured record: `test_ambient_scale` (per-channel analytics exact at
scale 1.0, 0.25, and 0.25+full sun — the sun-shaft case proving direct
light is unscaled; recompile survival rms 0; opt-out rms 0).

### R5.3 — Specular IBL env map: `set_env_map(cubemap)` (first slice LANDED, Session M)

Closes the walkable-ship queue's last rendering item (glass canopies
finally have something to reflect) and the R5 "specular env maps"
remainder. Two pieces:

**The real BRDF LUT.** `pax3d_render/textures/brdf_lut.txo` (128²,
generated by `tools/gen_brdf_lut.py` via pip simplepbr's reference
split-sum integrator — the library this shader forked from). The old
1×1 WHITE fallback made `env_brdf = (1,1)`, which was harmless only
while the env map was black; with a real cubemap it would ADD the whole
env color as a bias. Defaults stay byte-identical (black env × any LUT
= 0), and `set_env_map` REFUSES to run on the fallback LUT.

**The binding.** `set_env_map(cubemap, max_lod=None)` feeds the
shader's until-now-black `filtered_env_map`/`max_reflection_lod` path:
`ibl_spec = textureCubeLod(env, reflect_dir, perceptual_roughness *
max_lod) * (F * lut.x + lut.y)`. CONTRACT: the cubemap's own mip
chain IS the roughness ladder — bake the correct chain with
`tools/gen_env_prefilter.py` (R5.4 below); an ordinary cubemap gets
mipmap filtering enforced and auto box mips as an approximation
(fine for blurry metal). `max_lod` defaults to the full
chain. Pair the diffuse half from the same source:
`set_ambient_sh(sh_from_cubemap(cubemap))`. Uniform-cost; survives
recompiles; reflections ride at FULL strength on `set_glass` nodes
(the canopy case) and are damped per-node by `set_ambient_scale`
(reflections are indirect light). `clear_env_map()` is a
byte-identical restore.

Measured record: `test_env_map` — per-channel analytics exact (max err
0.000) with (A,B) peeked from the pipeline's own LUT: constant-env,
the LOD ladder (hand-loaded per-mip colors: roughness 0 reads mip 0,
roughness 1 the top mip), mirror ORIENTATION (normal incidence
reflects the -Y face, a 45°-pitched mirror the +Z face — the shader's
cube sampling is GL-standard; evidence toward the Session J
sh_from_cubemap orientation question, sampling side), glass
composition (env term unattenuated through alpha 0.15), recompile
survival and opt-out both rms 0.

### R5.4 — The GGX prefilter tool: `tools/gen_env_prefilter.py` (LANDED, Session Q)

Promotes `set_env_map` from documented approximation to correct: bakes
any cubemap (six-file `#` pattern or cube-map .txo/.dds) into a COMPLETE
GGX-prefiltered mip chain — mip i carries perceptual roughness
i/(levels-1), the exact convention `textureCubeLod(env, r,
perceptual_roughness * max_lod)` samples, so the default `max_lod`
addresses it with no argument. Same borrow-and-verify shape as the BRDF
LUT: the per-texel sampling math is pip simplepbr 0.13.1's own
`filter_sample`/`calc_vector` (Karis split-sum, GGX importance
sampling, NdotL weighting), borrowed verbatim; only the mip LOOP is
ours, because the reference's `filter_env_map` cannot reach the 1×1
level (its `calc_vector` divides by `dim - 1` — ZeroDivisionError;
upstream's 4-level default never hits it). Inherited reference quirks
documented in the tool docstring (the -z-pole tangent degeneracy, the
corner-stretched texel directions). Values filtered RAW — consistent
with the pipeline's current color contract. Dev-time dependency on pip
simplepbr only; runtime loads the committed/shipped .txo. Measured
2.6 s at the default 64px/32-sample bake.

Adoption: `tex = loader.load_texture('sky_ibl.txo')` →
`set_env_map(tex)` + `set_ambient_sh(sh_from_cubemap(tex))` — one
skybox feeds both halves of the environment.

Measured record: `test_env_map` checks 8-11 (the tool runs as a real
subprocess): complete chain with mip 0 an exact identity, uniform env
exactly preserved at every level (weight normalization), monotone blur
across the ladder (+X red 0.700 → 0.450), and the .txo driving the
shader end to end (mirror reads mip 0, roughness 1 reads the tool's
top-mip texel — max err 0.000 both).

### Session P — Model-authored lights: `activate_model_lights(np)` (LANDED)

The classic simplepbr annoyance closed: Blender lights export via
KHR_lights_punctual and panda3d-gltf converts them into REAL
PointLight/Spotlight nodes — which illuminate nothing, because a light
node is inert until something calls `set_light()` with it.
`activate_model_lights(model_np, root=None, scale=1.0,
include_directional=False)` finds and activates every point/spot light
under a loaded model on `root` (default: the model — a ship's lights
light the ship); `deactivate_model_lights(model_np)` restores colors
and scopes byte-identically.

Units: panda3d-gltf converts Blender intensity through physical units
(`color * I * 4π/683`, attenuation `(1,0,1)` inverse-square) — bright
in our unitless linear-HDR scene; `scale` ~0.05–0.3 is the tuning
knob. DirectionalLights are excluded by default (the pipeline owns the
sun — a stray Blender sun lamp would double-light directional mode).
glTF `range` is not consumed (quadratic falloff only). Keep per-root
counts within `max_lights`.

Measured record: `test_local_lights` checks 7–9 — a synthesized
KHR_lights_punctual asset loads inert (rms 0 vs no-asset), activates
to the exact analytic through the converter's unit chain
(lum 0.219 vs 0.220), the authored directional stays excluded, and
deactivation restores the inert capture at rms 0.

### R5.5 — Orbital scattering: `set_orbital_atmosphere(planet_np, ...)` (LANDED, Session R)

**The spaceflight half of the R5 signature look**: planet limb glow, an
atmosphere halo beyond the disk, aerial haze over the disk, and a soft
reddened terminator, seen from orbit/space. Per-planet registration
(the GLASS-family shape — no global flag, no PBR recompile, unlimited
planets); `clear_orbital_atmosphere(planet_np)` restores the scene
graph byte-identically, and `density=0` is an exact framebuffer no-op.

**Mechanism** (the "where it renders" decision): NOT a planet-material
variant (it could never draw the halo beyond the limb) and NOT a shell
mesh (tessellation would polygonalize the limb — the signature pixel).
Each planet gets a camera-facing quad pair the pipeline places every
frame at the shell's near surface: an extinction pass (blend
`dst *= src.rgb` — per-channel transmittance over whatever is behind,
planet or space) then an additive inscatter pass. Depth-tested but not
depth-written, `fixed`-bin after the opaque scene; own shader
(`orbital_atmo.vert/frag`) whose USE_330/LOG_DEPTH defines track
pipeline recompiles under the glass rule, including log-space
`gl_FragDepth`. Quads ride reserved draw-mask bit 30
(`ORBITAL_HIDE_BIT`) which the sun shadow camera always clears — a
billboard between sun and planet must never rasterize into the depth
map. Don't reuse bit 30 as `shadow_caster_mask`.

**Model** (documented in the .frag header; the paxtest replicates it
independently): exponential shell `rho(h) = exp(-h/H)` between R and
R_top; per-channel extinction `beta = density * scatter_tint`;
transmittance from a fixed-step trapezoid over the ray's in-shell
segment; single-scatter inscatter
`L = sun_color * intensity * phase(mu) * T_sun(P*) * (1 - T_view)` —
exact given albedo-1 scattering and the ONE stated approximation: sun
transmittance evaluated at P*, the segment's closest approach to the
planet center (the density-weighted heart of the ray). Terminator =
smoothstep of the sun ray's grazing altitude over 2H, plus per-channel
`T_sun` reddening (Rayleigh tint). `phase = 0.75*(1+mu^2)` — the
Rayleigh lobe normalized to sphere-average exactly 1, so `intensity`
scales mean halo brightness directly.

**Defaults derive Earth-like optics from the radius alone**:
`H = 0.02*R` (stylized ~15x Earth-true so the limb reads at game
distances), `thickness = 6H`, `density = 4/sqrt(2*pi*R*H)` (tangent-ray
optical depth ~4*tint per channel), `scatter_tint = (0.175, 0.41, 1.0)`
(Rayleigh lambda^-4). Mars-ish dust: `(1.0, 0.55, 0.35)`. All radii are
WORLD units and the node's origin must be the planet center (node scale
is not tracked — pass scaled-up values).

**Boundary with R5.1** (documented, not solved — the handover's
instruction): this is the orbital side only. Objects INSIDE the shell
(low-orbit stations, descending ships) get full-path haze drawn over
them since the quad sits at the shell's near surface; the camera
descending into the shell degrades gracefully (the quad clamps in
front of the near plane) but the planetside `enable_atmosphere` is the
right system once terrain exists. The fly-down handoff altitude and
cross-fade are game-paced R4.2-era work.

Measured record: `test_orbital` (12 checks) — the shader's limb profile
matches an independent 2048-step reference integrator to <=0.003
display-space at every measured impact parameter (on-disk, near-limb,
high-shell, outside-shell), through the tonemap; halo matches at 0.000;
terminator dark side lum 0.000 with >5x day/night asymmetry;
registration with density=0 AND full opt-out both rms exactly 0.0.
Green both engines x both baselines x `@logdepth`. Eyeball rig:
`test3d_pax.py --pax3d --orbital` (O toggles, Shift+O cycles
earth/mars presets).

---

## 10. Testing Contract

- Every feature has (at least) one paxtest: gamma, lighting (×sun-modes),
  bloom, rebuild, the shadow suite (shadows/gltf/quality/grazing/snap),
  skinning, ftl_blur, scale (+@logdepth), atmosphere, ambient_sh, glass
  (×sun-modes), doublesided (×sun-modes), ambient_scale, env_map,
  local_lights (×sun-modes), orbital (+@logdepth). Run
  `tools/paxtest/run.py` before and after.
- Add a test WITH the feature, not after. Analytic checks > goldens;
  goldens (`--golden` / `--check-golden`) are a refactor safety net.
- The testbed (`sfb2/test3d_pax.py`) is the eyeball companion — its
  `--selftest` mode (offscreen, 30 frames, screenshot) is scriptable.
- Harness gotchas encoded in the tests (keep them in mind for new ones):
  attach a small `AmbientLight` in lighting tests (with NO lights attached,
  `p3d_LightModel.ambient` is pure white and floods PBR output); render a
  frame before any manual buffer discovery; sample bar/halo centers to
  dodge the tonemap dither.
