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
| `shaderutils.py` | Loads `shaders/*` from disk, injects `#define`s (sources are native GLSL 330 since R1.4, 2026-07-23 — the 120→330 transform is deleted) |
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
| `USE_NORMAL_MAP` | `use_normal_maps` — or per-GEOM via `set_detail_maps` (below) | TBN normal mapping (needs tangents!) |
| `USE_EMISSION_MAP` | `use_emission_maps` | Emission texture sampling |
| `ENABLE_SHADOWS` | `enable_shadows` | Shadow-map sampling + per-light `v_shadow_pos` |
| `ENABLE_FOG` | `enable_fog` | Exponential fog |
| `USE_OCCLUSION_MAP` | `use_occlusion_maps` — or per-GEOM via `set_detail_maps` (below) | AO from metal-rough texture R channel |
| ~~`USE_330`~~ | — | REMOVED (R1.4, 2026-07-23): sources are native GLSL 330; a compat context warns and still works (diagnostic only) |
| `ENABLE_SKINNING` | `enable_hardware_skinning` | GPU skinning |
| `MAX_SKINNING_BONES` | `max_skinning_bones` | **Session S**: joint-palette size (`p3d_TransformTable[N]`, scene + shadow pass; default 100 — the ceiling that forced the character pipeline's 352→81 cuts, now a knob) |
| `CALC_NORMAL_Z` | `calculate_normalmap_blue` | Reconstruct normal-map Z |
| `SUN_FROM_LIGHTSOURCE` | `sun_light_mode == 'directional'` | **R2**: sun via `p3d_LightSource` loop (§4) |
| `LOG_DEPTH` | `enable_log_depth` | **R4.1**: fragment-level logarithmic depth (§9) |
| `ENABLE_ATMOSPHERE` | `enable_atmosphere` | **R5.1**: aerial perspective / height haze (§9) — planetside, off for space |
| `GLASS` | `set_glass(np)` — per-NODE variant, never in the render-root compile | **Session K**: specular-preserving glass (§9) — alpha attenuates transmission terms only, premultiplied output |
| `DOUBLE_SIDED_LIGHTING` | `double_sided_lighting` | **Session K**: backfaces shade with the inverted normal (glTF doubleSided semantic, §9) — front faces bit-identical |
| `ALPHA_MASK` (+`ALPHA_MASK_CUTOFF`) | `apply_alpha_masks(model_np, instanced=)` — per-GEOM variant, never in the render-root compile | **Session W**: glTF alphaMode MASK in-shader discard (§9) — core profile ignores the loader's AlphaTestAttrib (fact #17); cutoff baked per distinct value. **Session AA (ER-009)**: also detects TransparencyAttrib M_binary (cutoff 0.5, the cull semantic); `instanced=True` composes INSTANCING into the variant (shaders cached per (cutoff, instanced)) |
| `USE_NORMAL_MAP` / `USE_OCCLUSION_MAP` (per-geom) | `set_detail_maps(model_np, enabled=, normal=, occlusion=)` — per-GEOM variant, never in the render-root compile | **Session AI (ER-014)**: character detail maps. NORMAL only where a normal-map stage AND a tangent column exist (NaN-black guard); OCCLUSION only where a metal-rough/ORM stage exists (`.r` = AO); geoms already carrying a variant shader skipped (call AFTER apply_alpha_masks / set_gpu_morphs / set_glass). Composes with `set_hardware_skinning(np, False)`: valve-covered geoms re-stamp at the valve override with the flag folded in, and shadow casters carry a tag-state rescue (shadow attrib @3) so the depth pass keeps the shadow shader — fact #23's override rock-paper-scissors, gate-proven (test_detail_maps incl. @directional @logdepth) |

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
skinning, egg- and glTF-loaded (`panda3d-gltf` + `Actor`) — verified on
both GLSL baselines while the 120 path existed (native 330 only since
R1.4) — including posed joints (the shadow follows `control_joint`, not
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

Since Session AI (ER-014) the valve coordinates with per-geom detail
variants: the override-2 attrib would otherwise BLANKET a variant geom
below it (parent-override-wins ignores the child attrib wholesale —
fact #23), so `set_hardware_skinning`/`clear_hardware_skinning`
maintain a valve registry, re-stamp covered `set_detail_maps` geoms at
the valve override with the flag folded in, and manage the shadow
casters' tag-state rescue. `clear_hardware_skinning` also removes the
node attrib entirely when the flag was its only content — a leftover
EMPTY override-2 attrib is still a blanket.

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

### 5.8 Bone palette + the morph verdict (Session S — NPC characters)

**Policy (user-ratified 2026-07-18): the palette is a compatibility
shim, not a design cap.** UE5/Unity assets are the game's content
pipeline; the engine's job is to swallow their rigs as authored. The
ladder: (1) `max_skinning_bones` sizes the table; (2) `'auto'` makes
the CONTENT size it; (3) the uniform-budget wall (~240 mat4) is the
hardware's cap, not ours — beyond it, the queued **texture-palette
C++ path** (palette in a float texture, no uniform limit, full
343-bone UE5 rigs verbatim; CLAUDE.md build queue) is the answer.

**`max_skinning_bones`** (init) / `set_max_skinning_bones(n | 'auto')`
(recompile-class — PBR AND shadow depth shader, caster initial states
invalidated): the `p3d_TransformTable[N]` declaration, default 100.
`'auto'` resolves to the largest Character skeleton under render
(bucketed to 32, floor 100, clamp 240) — call
`refresh_skinning_budget()` after loading characters so it
re-resolves. The GL layer identity-pads short tables (fact #10), so
bigger tables are inert for small rigs — measured: rms exactly 0.0 at
[200] vs [100] (test_skinning `bone_palette_*`).

**The audit + warning** (field ask, 2026-07-18):
`audit_skinning_budget()` / `refresh_skinning_budget()` name every
Character whose skeleton exceeds the active palette — because the
failure mode is otherwise silent "plausibly-exploded" skin with no
log line. Measured on a synthetic 120-joint chain (test_skinning
`audit_names_oversized_rig` / `oversized_rig_corrupts_at_100` /
`auto_palette_covers_rig`): at [100] the GPU cannot render the posed
chain (rms 0.1045 vs CPU truth), the audit flags it, and `'auto'`
resolves 128 and matches CPU truth at rms 0.0000 — the cap follows
the content.

**Vertex morphs (egg `<Dxyz>` sliders) — measured verdict
(`probe_morph.py`, both engines identical = upstream behavior):** the
egg loader DOES create the `CharacterSlider`, and `animate_vertices`
(the CPU path) applies the morph exactly — but the hardware-skinning
render path **silently drops sliders** (the morphed vertices never
move on screen). The working morphs path today is the per-node valve:
`set_hardware_skinning(actor_np, False)` renders morphs correctly
(measured 0.000→0.763 at the probe's sample point) at that one
character's CPU-skinning cost. A GPU morph path (slider deltas as
vertex columns scaled in the vert shader) is the upgrade if content
ever needs many morphing characters at once.

---

## 6. Auxiliary Scene Cameras (R1 — the skybox-death fix)

External code must never hunt for the FilterManager buffer (the game's old
sky camera found it once at init and died on every rebuild — failure F4).
Instead the pipeline owns auxiliary display regions:

```python
reg = pipeline.register_scene_camera(cam_np, sort=-100,
                                     clear_color=(0,0,0,1),
                                     clear_depth=True, name='sky_camera',
                                     follow=None)   # None | 'pose' | 'hpr'
pipeline.unregister_scene_camera(reg)
```

Internals: `_attach_scene_camera` makes a DR on `_filtermgr.buffers[0]`
with the given sort/clears; for any background camera (sort < 0) the MAIN
scene DR is set to color-clear OFF / depth-clear ON (preserves background
pixels, standard sky-camera contract; since Session AK the original clear
state is saved and RESTORED when the last background camera unregisters).
`_setup_tonemapping()` ends with `_reattach_scene_cameras()`, so every
rebuild (bloom/TAA toggles) re-creates all registered DRs on the new
buffer. Proven by `paxtest test_rebuild` (manual-discovery pattern dies,
registration survives).

Caller keeps ownership of the camera node: lens, camera masks, and scene
root. Transform sync is the caller's business ONLY when `follow=None`
(the game's `sky_camera.py` shows the hand-slaved pattern): with
`follow='pose'` the pipeline mirrors the main camera's render-relative
position AND rotation onto the camera every frame (world-anchored far
scenes — horizon rings, build-massing imposters — parallax correctly),
with `follow='hpr'` rotation only (origin-pinned sky domes). The copied
transform is applied as the camera's LOCAL transform — parent follow
cameras at their scene root. `render_snapshot` re-aims follow cameras to
the snapshot pose for its one frame and restores them (the Session-AJ
"aux transforms are game-owned" snapshot limit now applies only to
`follow=None` cameras). The far-field layering this serves (voxel-lane
Session AK consult): sky at sort −100 `follow='hpr'`, horizon ring at
sort −50 `follow='pose'` with `clear_color=None`, world at sort 0 — each
region clears depth, so a 2–6 km ring lens coexists with a short world
far plane with no log depth and no precision interaction. Gated:
test_snapshot section 9 (six checks, both engines).

Gotcha for tests/tools: the FilterManager buffer appears in
`GraphicsEngine`'s window list only after a frame renders — anything doing
manual discovery must render ≥1 frame first (the registration API is
immune; it holds the buffer object directly).

### 6.1 Foreground viewmodel camera (Session X — the FPS near-plane answer)

`register_scene_camera` covers backgrounds (sort < 0, sky). The
foreground mirror is a first-class API — the standard FPS solution for
hands/weapons closer than the world near plane (planetside: hands at
~0.04 m, world near 0.3 m):

```python
vm_root = base.cam.attach_new_node('vm_root')   # under the camera: free tracking
# ...parent hands/weapon Actors under vm_root...
reg = pipeline.register_viewmodel_camera(vm_root, near=0.02, far=8.0,
                                         fov=None, depth_mode='clear')
# reg.camera_np = the created viewmodel camera (animate it for sway)
pipeline.unregister_viewmodel_camera(reg)       # exact restore; vm_root left hidden
```

What it owns (measured, test_viewmodel — 15 checks, 17 @directional):

- **A second display region on the HDR scene buffer, sort +100** — drawn
  after the world, BEFORE post: tonemap analytics hold on viewmodel
  pixels, a hot emissive viewmodel feeds bloom, TAA applies. PBR
  lighting reaches the subtree (vm_root must live under the pipeline's
  render node — the API warns if not); measured luminance parity with
  an identical world surface.
- **Draw-bit isolation, pipeline-reserved bit 29** (sibling of the
  orbital bit 30): world hidden from the viewmodel camera, viewmodel
  hidden from the main camera (mask restored exactly on unregister) and
  from the sun shadow camera (bit 29 is always cleared from its mask —
  zero texels in the depth map, gated @directional). Games hand-rolling
  camera masks must leave bits 29/30 alone.
- **Rebuild survival**: region, clears, and depth-range state re-attach
  across every FilterManager rebuild (bloom/SSAO toggles) — same
  contract as the sky camera.
- **Two depth modes.** `'clear'` (default): region clears depth —
  always wins, but the scene buffer's depth texture is stomped
  full-screen, so **SSAO reads garbage world depth** (measured;
  documented-limitation row). `'range'`: glDepthRange-compresses the
  viewmodel into window depth [0, 0.05] — no clear, world depth
  byte-preserved outside the viewmodel silhouette (SSAO-friendly;
  hands get a near-field AO halo on their own pixels only). `'range'`
  needs the fork's `DisplayRegion.set_depth_range` (falls back to
  'clear' on stock 1.10 with a warning) and is incompatible with
  `enable_log_depth` (the PBR shader writes gl_FragDepth, which GL
  CLAMPS — not rescales — to the region's depth range; the API falls
  back to 'clear' and says so). **Session AJ:** pass
  `on_depth_degrade='raise'` to make that fallback fatal at
  registration instead — and either way the degrade flips
  `pipeline.visibility_query_valid` False and visibility queries fail
  closed (see the Session AJ section), never silently confident.
- Caveats: TAA jitters only the main lens (viewmodel unjittered — no
  ghosting, marginally less temporal AA on hands); one viewmodel
  registration at a time is the supported shape.

---

## 7. Runtime Parameter Model

Three cost classes — keep new parameters within this taxonomy:

| Class | Cost | Parameters / methods |
|---|---|---|
| Uniform-only | free, per-frame safe | `set_exposure`, `set_tonemap_operator`, `set_bloom_strength`, `set_bloom_intensity`, `set_ao_radius`/`set_ao_intensity`/`set_ao_bias` (§9 Session S), `set_flare_strength`/`set_lens_dirt` (§9 Session S), `update_sun`, `set_debug_lighting`, `set_shadow_extent`, `set_shadow_bias`, `set_shadow_normal_bias` (slope-scaled, §5.2), `set_shadow_caster_mask`, `set_shadow_texel_snap` (§5.7), `exclude_from_shadows`/`include_in_shadows`, `set_hardware_skinning`/`clear_hardware_skinning` (per-node state change; no recompile), `set_atmosphere_params` (§9 R5.1), `set_ambient_sh`/`set_hemisphere_ambient`/`clear_ambient_sh` (§9 R5.2), `set_env_map`/`clear_env_map` (§9 R5.3), `set_glass` (§9 Session K; per-node state change — lazy one-time variant compile on first use, tracked across recompiles), `apply_alpha_masks` (§9 Session W; per-GEOM state change — lazy per-cutoff variant compile, tracked across recompiles), `set_ambient_scale`/`clear_ambient_scale` (§9 Session L; per-node inherited input), `set_atmosphere_scale`/`clear_atmosphere_scale` (§9 Session S; per-node inherited input scaling the R5.1 optical depth — hull interiors), `activate_model_lights`/`deactivate_model_lights` (§9 Session P; scene-graph state only) |
| Shader recompile | one hitch; **must preserve inputs** (§3) | `set_sun_light_mode`, `set_enable_shadows`, `set_enable_log_depth`, `set_shadow_filter_size`, `set_enable_atmosphere`, `set_double_sided_lighting` (§9 Session K), `set_max_skinning_bones` (§5.8 Session S; also invalidates shadow-caster states) |
| FilterManager rebuild | frame hitch; aux cameras auto-reattach | `set_enable_bloom`, `set_enable_taa`, `set_enable_ssao`, `set_enable_lens_flare` (§9 Session S; needs bloom), (`bloom_levels`, `msaa_samples`, `ao_samples` at init). `register_viewmodel_camera`/`unregister_viewmodel_camera` (§6.1 Session X) are scene-graph + display-region state — no rebuild, and they survive rebuilds |

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
under both GLSL baselines while the 120 path existed (native 330 only
since R1.4), stock + Pax3D engines.

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

**Per-subtree binding (Session S):** `set_ambient_sh(coeffs, node=np)`
and `set_hemisphere_ambient(sky, ground, node=np)` bind to a SUBTREE —
a plain inherited shader-input override, so a hull interior gets
cabin-derived ambient while the exterior keeps the sky's. Node-level
inputs live on the node's own state, so they survive recompiles with
no pipeline tracking; `clear_ambient_sh(node=np)` reverts to the
inherited global set byte-identically. Measured record:
`test_ambient_sh` `pernode_sh_*` (swapped-hemisphere override exact
with the global card unaffected; clear rms 0).

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

**Per-subtree binding (Session S):** `set_env_map(cubemap, node=np)` /
`clear_env_map(node=np)` — the walkable-ship pattern: the interior
subtree reflects a cabin-derived map while the exterior keeps the sky.
Inherited shader-input override of BOTH `filtered_env_map` and
`max_reflection_lod` (the node's own chain ladder is addressed
correctly even when its mip count differs from the global map's);
same validation as the global path (cube-map type, real BRDF LUT,
mipmap filter). Pair with `set_ambient_sh(..., node=np)` from the same
cubemap. Measured record: `test_env_map` `pernode_*` (node-map
mid-roughness analytic exact through the NODE max_lod — a leaked
global lod would miss by ~0.25; sibling untouched at 0.000; node
clear reverts to the inherited map at rms 0).

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
(`orbital_atmo.vert/frag`) whose LOG_DEPTH define tracks
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

### Session S — SSAO first slice: `enable_ssao` (LANDED, opt-in)

The first true post-R5 PaxPBR-native feature (nothing in the simplepbr
lineage): screen-space ambient obscurance for interior/contact
shading — the walkable-ship "corners are flat" fix and the game
roadmap's Tier-1 ask.

**Architecture (first slice, deliberately depth-only):** when enabled,
the scene buffer gains a depth target (`render_scene_into(depthtex=…)`
— requested ONLY when on, so the default chain is structurally
untouched); an `ssao.frag` pass reconstructs view-space positions from
depth (normals from `dFdx/dFdy` — zero scene-shader changes) and
evaluates Alchemy/SAO-style obscurance over a rotated spiral kernel,
radius-normalized so AO is scene-scale-invariant; a 3×3 tent
(`ssao_blur.frag`) suppresses the rotation noise; tonemap multiplies
the scene HDR color by AO BEFORE the bloom add and tone curve. The AO
buffers are DELIBERATELY 8-bit (a [0,1] scalar — unlike the bloom
chain, where fact #3 demands float fbprops).

**The defining measured property:** flat geometry produces AO exactly
1.0 (every tap lies in the tangent plane; the depth-proportional bias
absorbs quantization), so on planes the multiply is an exact no-op —
SSAO can only darken real concavities. `ao_intensity=0` is likewise an
exact no-op. Honest scope note: at tonemap time the AO multiplies the
COMPLETE radiance (direct included) — the classic screen-space AO
compromise; the principled indirect-only variant (AO map sampled in
the scene pass, folded into the §Session-L ambient/occlusion factor)
needs a depth prepass and is the documented upgrade path.

Knobs: `enable_ssao` (init) / `set_enable_ssao()` (rebuild-class);
`ao_radius` (world units), `ao_intensity`, `ao_bias`
(uniform-only setters); `ao_samples` (init-only compile define,
default 12). The lens (fov/near/far) is re-pushed every frame; under
LOG_DEPTH the pass inverts the log formula instead of the standard
linearization.

Measured record: `test_ssao` — plane byte-identity (rms 0.00e+00 with
the feature ON over constant-depth geometry), both creases of a
wall/floor/ceiling slot darken while the wall center 3 units away is
unchanged, intensity monotonic, intensity-0 and full opt-out both rms
0.00e+00. Green both engines × both baselines × `@logdepth` ×
`@msaa4` — the msaa4 row is itself a measurement: **the multisampled
depth resolve works** (the game's default msaa_samples=4 needs no
special-casing). Rig lesson encoded: the MSAA resolve can shift a
crease line sub-pixel — crease samples scan ±3 rows for the minimum
(fact-#12 discipline).

### Session S — Lens flare/dirt: `enable_lens_flare` (LANDED, opt-in — R5 COMPLETE)

The R5 lens-polish finale. Pseudo-flare ghosts sourced from the BLOOM
BRIGHT EXTRACT (`lens_flare.frag`, a half-res float pass over a
blurred down level — fact-#3 fbprops discipline): each of four ghosts
samples the source at a center-scaled UV, so a bright source at uv p
produces ghosts at the ANALYTIC positions `x_k = 0.5 + (p-0.5)/c_k`,
`c ∈ (-2.0, -3.5, 1.7, 3.0)` (pinned constants — change only together
with test_lens_flare). Sourcing from the extract buys two properties
for free: **occlusion is implicit** (a sun hidden behind a hull
contributes no extract energy — its flare vanishes with it) and every
bright emitter (twin suns, engine trails) flares consistently. The
composite adds in HDR next to bloom; `flare_strength=0` adds exactly
zero.

**Requires `enable_bloom`** — flare with bloom off is inert with a
one-time warning (the ghosts have no source without the extract).
Knobs: `enable_lens_flare` (init) / `set_enable_lens_flare()`
(rebuild-class); `set_flare_strength(v)` (uniform);
`set_lens_dirt(tex, strength)` (uniform) — a screen-space dirt texture
modulating the flare, `None` restores the clean lens exactly (a 1×1
white always binds under the strict-uniform rule; no-dirt forces
strength 0 so `mix()` is an exact identity).

Measured record: `test_lens_flare` — all four ghosts appear at the
predicted pixels (deltas +0.92/+0.81/+0.32/+0.48) with an off-axis
control at +0.0000; hidden source ⇒ flare-on byte-identical to
flare-off (occlusion); strength-0, dirt-clear, and opt-out all rms
0.00e+00; a left-black/right-white dirt kills exactly the left-half
ghosts. Green both engines × both baselines.

### Session U — Terrain lane: data textures, splatting, instancing (LANDED)

The three game ERs (`sfb2/documents/ENGINE_REQUESTS/`), all engine-side
same-session; deep mechanisms in `ENGINE_INTERNALS.md`.

**ER-003 — `data_texture(tex)` / `load_data_texture(path)`** (module
functions, not Pipeline methods): the 16-bit/float heightfield contract —
compression pinned off (the `compressed-textures` prc would BC4/DXT1 data
textures), ATS_none, sRGB unflagged, 1-channel ushort/float normalized to
F_r16/F_r32. `load_data_texture` decodes via PNMImage/PfmFile + `load()`
because `Texture.read()` applies the `texture-scale` prc DURING the read.
Gate: test_data_texture (runs under a hostile `compressed-textures 1`).

**ER-001 — `set_terrain_splat(np, albedo_array, splat_map, ...)`**: a
TERRAIN_SPLAT compile of pax_pbr composed per-subtree (glass mechanism;
tracked via `_reapply_terrain_splat` on every recompile; variants cached
per optional-feature combo — normals/ORM/macro). Replaces only the
material inputs: 4 layers from 2D texture arrays weighted by an RGBA
splat map (renormalized in-shader), per-layer uv_scale, splat-UV window,
macro brightness variation, detail-normal distance fade, analytic world
TBN (u→+world_x, v→+world_y — chunks carry no tangents). The layer-weight
function is the ratified v2 seam (hex-tiling LANDED there Session Y,
height-blend sharpening + hex world-anchor Session AA —
TERRAIN_HEX_TILING, see the Session Y section; height-blend sharpening
still slots in the same way; the ER-010 wet-sand waterline rider —
TERRAIN_WATER, `set_terrain_water`, Session AE — modifies the OUTPUTS
(albedo/roughness) after the weights, not the seam). sampler2DArray
works on the 120 path via GL_EXT_texture_array (measured). Gate:
test_terrain_splat — 12 exact analytics + 12 hex checks + directional
variant; test_terrain_water for the water rider.

**ER-002 — `set_instanced(np)`**: hardware instancing over upstream
`InstancedNode` — INSTANCING compile of pax_pbr + F_hardware_instancing
composed on the node; the GLOBAL shadow shader gains the same define
while any instanced node is registered (identity fallback keeps other
casters behavior-identical; caster initial states invalidated on flip).
Measured contract: unflagged InstancedNodes render correctly via the
traverser's per-instance fallback (set_instanced = the draw-call
collapse, not correctness); instanced casters shadow correctly; the
opt-out clears the FLAG explicitly (`clear_shader()` keeps attrib flags
— the collapse trap, gate-guarded). Gate: test_instancing (SKIPs on
stock 1.10 — no InstancedNode there).

### Session V — Walkable-ship lane: rigid clips (ER-004) + powered displays (ER-005)

The Vattalus Phobos/Minerva compatibility pair
(`sfb2/documents/ENGINE_REQUESTS/`, evidence in the game repo's
`documents/PLANETSIDE/MINERVA_CENSUS.md`), both engine-side same-session.

**ER-004 — `pax3d_render/rigid_clips.py`** (module + thin
`pipeline.get_model_clips(model_np)`): panda3d-gltf consumes glTF
animations only inside `build_character()` — channels targeting PLAIN
nodes (every Unity door/ramp/gear/drawer clip) are silently dropped. The
module parses them straight from the .glb/.gltf (GLB container + accessor
decode reusing `gltf_compat`'s machinery; sparse accessors densified via
the same pre-pass) into `RigidClip` stores:

- Nodes stay ordinary PandaNodes — nothing converts to Character; the
  parser SKIPS channels targeting skin joints or morph weights (the
  loader's Character/Actor path owns those; the two stores are
  complementary by construction).
- Axis conversion is the loader's own conjugation (`_converter.py` ~224,
  csxform_inv · M · csxform — a proper Y-up→Z-up rotation), applied
  per-component: pos (x,y,z)→(x,−z,y), quat (x,y,z,w)→LQuaternion(w,x,−z,y),
  scale (sx,sy,sz)→(sx,sz,sy). Pinned by the gate's
  `key0_matches_loader_rest` check (player key-0 pose == loader rest pose,
  0.0 err on file).
- Sampler semantics: LINEAR (slerp for rotation), STEP, CUBICSPLINE
  (Hermite, normalized for rotation); values clamp outside the keyed range.
- `RigidClipPlayer(clip, model_np)`: name-resolved targets (full-subtree
  walk, `.missing`/`.duplicates` surfaced, rest TRS captured), `seek(u)`
  / `apply(t_seconds)` / `reset()` — stateless evaluation, so reverse =
  decreasing u. The GAME owns tasks/easing/sounds/collision gating
  (ER-004 contract).
- `RigidClip.from_delta(...)` / `add_delta(...)`: the second Vattalus
  clip source — prefab script-lerps (pos delta + rot delta + duration,
  ~40 Minerva parts) — as two-keyframe RELATIVE clips composing onto the
  captured rest pose (delta quat premultiplies: local-frame delta, the
  Unity `localRotation * Euler(delta)` convention). Values are
  PANDA-space; the game converts Unity axes and validates on one door.
- The channel `path` is an open string — ER-005 material channels can
  join later ("one runtime, two channel kinds") without restructuring.

Gate: test_rigid_clips (authors a GLB from scratch in-test; loader-drop
premise, axis contract, analytic seeks, delta compose, render A/B).

**ER-005 — powered displays** (the census verdict: the packs' dominant
display mechanism is a texture bound as albedo+emission on a Standard
material — VIDEO-textured; plus material-swap power states, UV-scroll
strips):

- `set_screen(np, tex, albedo=True, emission_scale=, emission_color=,
  roughness=, metallic=)`: node-level TextureAttrib (modulate+emission
  stages sharing `tex`, white selector, flat normal when the pipeline
  compiles normal maps) + MaterialAttrib (HDR emission) at override 1 —
  beats the loader's geom-level states (set_glass discipline; the node's
  own texture state is cleared first because set_texture MERGES stages).
  `clear_screen(np)` restores the saved attribs byte-identically.
  `tex` is ANY Texture: static image, flipbook atlas, dynamic
  `set_ram_image` target, or MovieTexture — but NOTE: **the Pax3D wheel
  builds `--no-ffmpeg`; MP4 decode does not exist engine-side.** The
  sanctioned video path is a flipbook atlas (`tools/gen_flipbook.py`
  converts videos/frame-dirs at intake; the dev machine's ffmpeg CLI
  works) played by `play_flipbook()`. Re-adding ffmpeg would be a
  user-scheduled build-window decision.
- `set_emission_scale(np, s)` / `set_emission_color(np, rgb)` /
  `clear_emission(np)`: new `u_emission_factor` uniform (root default
  (1,1,1) = exact no-op) multiplying ONLY the emission term — screen
  power states (0.0 = the VA_ScreenOff state with albedo still lit),
  blink/pulse, HDR boost. Composes with whatever the material/texture
  emission is; works on any authored emissive material, not just screens.
- `set_uv_transform(np, offset, scale)` + animated drivers
  `set_uv_scroll(np, du_dt, dv_dt)` (chase-light strips) and
  `play_flipbook(np, cols, rows, num_frames, fps, loop)`: new
  `u_uv_transform` uniform (root default (0,0,1,1) = exact no-op),
  `mat_uv = v_texcoord * zw + xy` applied to the STANDARD material
  samples (base/metal-rough/normal/emission) — not the terrain-splat
  sample set. Scroll/flipbook are stepped by the pipeline's per-frame
  task: O(active) uniform pushes, zero when idle, no TexMatrix state
  churn, atlas resident on the GPU (zero per-frame uploads). Flipbook
  atlas convention: row-major from the TOP-LEFT (contact-sheet order),
  `Pipeline._flipbook_transform` is the pinned mapping.

Both uniforms ride every pax_pbr variant (glass/terrain/instanced share
the source) and survive recompiles via the input-preservation invariant
(§3). Gate: test_screen — 19 checks, all analytic (quadrant-color map),
every opt-out byte-identical (rms == 0.0).

**Ship exterior lights (Session V part 3 — the Minerva gold-standard
look; every NPC and player ship):**

- `set_blink(np, period, pulses, phase, lights=None, off_scale=0.0)` /
  `clear_blink(np)`: a pulse-train blinker for nav strobes / beacons /
  hazard flashers. The envelope (`_blink_envelope`, pure + pinned:
  1.0 inside any `(start_s, duration_s)` window of the period, cycle
  shifted by `phase`) multiplies the node's REGISTERED emission
  scale/color — it composes with `set_emission_scale/_color` (the
  registry hands the blinker its base; setters on a blinking node
  re-base instead of pushing, so there is no one-frame pop), and
  `clear_blink` restores through the same registry. `lights` gates
  real light-node colors with the SAME envelope so a marker and the
  light it casts never drift; originals restored on clear. Pushes are
  EDGE-triggered (a strobe ≈ 4 pushes/s/node — a parked fleet is a
  handful of comparisons per frame). Airliner recipe in the docstring:
  steady position lights (no blinker), beacon ≈ period 1.33 s / pulse
  0.20 s, strobes ≈ 1 Hz double-flash (0.00/0.05 + 0.15/0.05);
  per-ship `phase` de-syncs a fleet.
- **Circuits, not bulbs (the 737NG-panel model — game owns the
  switches/power bus):** author each circuit as a NAMED subtree
  (`lights_position`, `lights_beacon`, `lights_strobe`,
  `lights_floods`); a panel switch is then 2–3 pipeline calls on that
  subtree — floods: `activate_/deactivate_model_lights(circuit_np)`
  (+ emissive fixture via `set_emission_scale` 1/0); position:
  `set_emission_scale` 1/0 (markers are emissive-only; add small real
  lights on hero ships); beacon/strobe: `set_blink`/`clear_blink` +
  `set_emission_scale 0` for off. All opt-outs are byte-identical
  (gated), so power-bus wiring is pure composition.
- **Light budget (MEASURED, this GPU, both baselines):** with
  `enable_shadows` the binding constraint is the
  `v_shadow_pos[MAX_LIGHTS]` varying array against the ~128-component
  varying budget — `max_lights=16` and 20 and 22 link and light
  correctly; **24 FAILS to link** (silent-looking GLSL link error).
  Recommend 16 for walkable-ship scenes (9 exterior + interior
  fixtures fits), 22 = the measured ceiling. Without shadows the
  varying array is absent and the ceiling is far higher. NPC ships at
  range: NO real lights — emissive markers + bloom (the packs' own
  small lights are glow-texture-only); real lights are for hero/parked
  ships.

Gate: test_screen 9b (envelope math pinned; pulse-ON/gap-OFF renders
byte-identical to the emission-scale states; light-node sync + restore).

### Session W — glTF alphaMode MASK: `apply_alpha_masks(model_np)` (LANDED)

Field-driven (character dev: a factor-only MASK material — baseColor
alpha 0, no texture — drew as a solid white shell under `gl-version
3 2`). The mechanism gap is engine-wide (master plan **fact #17**):
panda3d-gltf expresses MASK as a geom-level `AlphaTestAttrib`, and the
GL backend implements that attrib ONLY via fixed-function
`GL_ALPHA_TEST` — core profile silently ignores it, so ALL MASK
content (cutout foliage included) renders opaque there. Identical on
stock 1.10.16: upstream behavior, not fork damage.

`pipeline.apply_alpha_masks(model_np)` scans the subtree's Geom states
for keep-if-greater alpha tests (exactly what the loader stamps — one
per MASK primitive) and composes an `ALPHA_MASK` compile of the PBR
shader onto those geoms, cutoff baked as `ALPHA_MASK_CUTOFF` (variants
cached per distinct cutoff — content is overwhelmingly the glTF
default 0.5). Returns the masked-geom count (0 = nothing to do).
Mechanics worth knowing:

- The geom-level ShaderAttrib composes: root shader inputs and flags
  (`F_hardware_skinning`) pass through (`ShaderAttrib::compose_impl`
  only overrides explicitly-set child flags), and the shadow camera's
  override-1 attrib still wins the depth pass.
- On compat the fixed-function test stays active alongside — same
  predicate on the same output alpha, so compat is BIT-identical
  (measured rms 0.0). Safe to call unconditionally under either
  baseline.
- `apply_alpha_masks(np, False)` restores the saved geom states
  byte-identically; recompile-class toggles re-push fresh variants
  (the glass discipline).
- **Depth-pass caveat:** the shadow shader has no per-geom alpha
  knowledge — under gl 3 2 masked casters cast their UNMASKED
  silhouette (compat gets cutouts from the fixed-function test).
  Invisible shells: `exclude_from_shadows()`. A cutout-shadow depth
  path lands only on field evidence.

Gate: test_alpha_mask (in-test GLB through the real loader: factor-only
shell + textured cutout; pre-API defect asserted per-baseline so an
engine change forces a true-up; compat bit-identity; byte-identical
opt-out).

### Session Y — ER-007 hex-tiling, ER-008 light policy, env controls (LANDED)

**ER-007 — hex-tiling (`set_terrain_splat(..., hex_tiling=True,
hex_cell_size=4.0, hex_rotation=1.0, hex_contrast=6.0)`):** the
TERRAIN_HEX_TILING define lands at the ratified v2 seam. Mikkelsen-
style stochastic tiling on the dual triangle lattice: per fragment the
3 nearest hex cells' samples blend, each cell hashed (fract-mix, no
sin — well-distributed into tens of thousands of repeats) to a random
phase offset + rotation about its center. KEY DESIGN FACT: per-cell
transforms are constant, so every tap's UV is continuous wherever its
weight is nonzero (the tap whose cell changes at a blend boundary has
weight ~0 there) — plain sampling mips correctly on BOTH GLSL
baselines, no textureGrad (which the 120 array path lacks). Normals
ride the same cells/weights and each sampled tangent-space xy is
back-rotated with its motif; ORM likewise; 3x taps on the hex path.
`hex_rotation` is per-layer (scalar or 4-seq — 0 keeps anisotropic
sets axis-aligned); `hex_contrast` is the cheap variance-preserving
weight-sharpen (histogram-preserving needs per-texture LUTs; on the
books if the field shows washout). Gate: test_terrain_splat phases
8-12 (12 checks): uniform-layer invariance, shift-rms 0.0014→0.2296
periodicity break, mean preserved, |dy|/|dx| 0.19 rot0 vs 1.14 rot1,
normal back-rotation live, byte-identical opt-out.

**ER-008 — the light drop policy, answered + armed:** overflow beyond
MAX_LIGHTS uploads the LightAttrib's priority-sorted head and silently
drops the rest — `Light.set_priority()` descending (fully dynamic: a
global sort-seq bump re-sorts every attrib lazily), ties by class rank
(spot > directional > point), equal ties effectively ARBITRARY
(measured differing between identical runs). Three consequences
engineered this session:
- **Sun eviction guard (default-on):** in directional mode the sun
  competes in the same array and spots outrank directionals — floods
  on an overflowing hull would have evicted the sun + its shadows.
  `_create_sun_light` pins priority 1<<20.
- **`set_light_budget(root, lights, budget=None, anchor=None,
  radius=0.0, hysteresis=1.25)` / `clear_light_budget`:** per-root
  nearest-N warden (the ER's structural ask) — per frame each
  candidate scores luma/(kc+kl·d+kq·d²) via its OWN attenuation at
  d = |light−anchor|−radius; top-N bound, rest unbound, rebinds only
  on membership change; incumbents get the hysteresis multiplier;
  blinking lights score by STEADY color (the set_blink registry).
  Budget defaults to max_lights−1 in directional sun mode. Refuses
  directional/ambient candidates. Python-canon orchestration
  (microseconds; no per-frame state churn).
- **Zero-light quirk on record:** a draw with NO active lights gets a
  default WHITE light in slot 0 (GSG default-fill, degenerate params)
  — invisible in practice, but it is the no-light ground truth.
Gate: test_light_priority (+@directional): overflow binds exactly
array-size, priority selects/re-sorts live, warden binds/rebinds/
restores, sun survives spot overflow; tie order reported as INFO only.

**Env controls (Round-5 asks):** `set_env_scale(np, s)` /
`clear_env_scale` (per-node, ibl_spec ONLY — SH diffuse + flat ambient
untouched, unlike set_ambient_scale), `set_env_intensity(s)` (global,
multiplies with per-node scale), `set_env_map_rotation(deg)` (yaws the
specular lookup about world +Z in the skybox set_h sense: the shader
samples at Rz(−θ)·r; pair with the game-side SH yaw). All three are
root-defaulted shader inputs with exact no-op defaults (u_env_scale /
u_env_intensity 1.0, u_env_yaw (1,0)). Gate: test_env_map 6b/6c — +90°
yaw maps −X→−Y mirror exactly, 0.25 node × 0.5 global = 0.125 analytic,
defaults restore byte-identically.

### Session Z — GPU morphs: `set_gpu_morphs(model_np)` (LANDED, opt-in)

Fact #15's missing half: morph sliders render ON the hardware-skinning
path — no CPU valve, faces animate at crowd scale. Pure Python/GLSL;
runs unchanged on stock 1.10 (fact #19).

**Data path.** At enable, every Geom whose vertex data carries a
slider table gets: (1) a per-vdata RGB32F **delta texture** —
VERTEX-MAJOR since Session AB: width = 2×targets (position delta at
x=2t, NORMAL delta at x=2t+1 — the loader ships
`normal.morph.<slider>` columns; lighting morphs correctly, not just
silhouettes), height = vertex rows, stamped with the ER-003
`data_texture()` contract, nearest-filtered. Vertex-major is the
loader's OWN byte layout (one interleaved tight array per vdata), so
the bake is zero-copy when column order matches the slider order —
see the Session AB section for the bake ladder; (2) a float32
`morph_index` column (its own array) carrying each vertex's row id —
the ONE addressing mechanism that works on both GLSL baselines (120
has no gl_VertexID); (3) a GPU_MORPHS compile of the PBR shader
composed onto its geom state exactly like the alpha-mask seam (root
inputs + flags still compose through; per-geom inputs: u_morph_tex,
u_morph_texel). Ram conventions were measured before building:
row 0 = v=0, set_ram_image_as('RGB') keeps float order.

**Per-frame path.** `_step_gpu_morphs` (in `_update`) reads each
registered Character's slider values and refills a compact 16-slot
(row, weight) PTA only when the live set changes — uploaded by
reference, no set_shader_input churn. All 52 ARKit targets stay
addressable; ≤16 live is the character-lane contract; overflow keeps
the largest |weight| and warns once. The shader loop breaks at the
first zero weight (slots are compact by contract) and adds
w·Δpos/w·Δnormal BEFORE the skin matrix — glTF semantics, matching
`animate_vertices` exactly (gate: GPU-vs-CPU-valve image rms 0.0000).

**Invariants.** Not enabled = byte-identical shipped pipeline (the
default HW path still drops morphs — hw_drops_morphs guards that);
`set_gpu_morphs(np, False)` restores saved geom states exactly (the
inert morph_index column stays — nothing reads it without the
variant). Requires the HW-skinning path: combining with
`set_hardware_skinning(np, False)` would double-apply deltas. One PBR
variant per geom (no stacking with glass/mask/terrain). Shadow depth
pass casts the UNMORPHED silhouette (alpha-mask depth precedent;
lands on field evidence).

**Measured (probe_gpu_morph_bench.py, hero_wren = worst-case
14,684 verts × 52 targets, 512² offscreen):** 8 faces × 5 live
sliders ≈ 0.3 ms/frame morph-attributable (acceptance bar ≤0.5 ms;
re-measured 0.19 ms Session AB, interleaved min-of-5); CPU valve same
scene 63.5 ms; 32 faces 2.42 ms total (superseded by the Session AB
all-driven leg: 4.3 ms with every clone independent); Python push
0.03 ms; enable cost 1.17 s + 18.3 MB per face at Session Z —
**bake now 0.07–0.08 s (Session AB zero-copy path)**, texture size
unchanged. Bench trap on record: `apply_freeze_scalar` without
`force_update()` dirties nothing — an A/B without a playing clip
silently measures an idle scene.

### Session AA — ER-007 height blend + hex anchor, ER-009 cutout alpha (LANDED)

**Height-blend sharpening (`set_terrain_splat(..., height_blend=True,
height_sharpness=8.0)`):** the ER-007 rider, unblocked by the terrain
dev's height8-in-albedo.a intake (albedo.a == height16 >> 8, linear —
the game binds F_srgb_alpha so sRGB touches RGB only; heightless
layers ship flat 128). TERRAIN_HEIGHT_BLEND resharpens the splat
weights per fragment by a height softmax — `w_i · 2^(k · h_i)`,
renormalized — so the taller material's texels win the transition and
blend borders follow the height texture instead of crossfading. The
FORM is the contract: equal heights cancel as a common factor, so an
all-flat palette (Deep Desert) degenerates to plain splat weights BY
CONSTRUCTION (gate: rms 2.6e-06, one-hot texels exact) and a flat-128
slice competes at its constant middle (beach-sand; k=8 vs h=1.0 →
0.9406/0.0594, analytic-exact in-gate). Sharpened weights feed albedo,
ORM and detail normals — material coherence. Sampling: per-layer
albedo is pulled up front through `terrain_layer_sample` (the hex
3-tap when TERRAIN_HEX_TILING is on, plain wrap tap otherwise — the
height stays coherent with the rendered motif); plain path costs 4
extra array taps, hex path reuses its taps. `height_sharpness` 0 is
an exact no-op; useful range ~4–16 (at k=8 a 0.25 height advantage
outweighs a 4× splat-weight deficit).

**Hex world-anchor (`hex_offset=(u, v)`):** the Session-647 adoption
observation — chunk-local base UVs restart per chunk, so the hex cell
HASH reseeds along borders (whole-repeat uv_scales keep the texture
PHASE continuous; the hash input is what jumps). `u_terrain_hex_off`
is added to base UV before the per-layer uv_scales in the hex path
only: chunks passing their world offset (in base-UV units) get
world-anchored cell ids and a border-seamless motif. Default (0,0) is
an exact no-op (x+0.0); the pinned hex numbers did not move. Gate:
UV-window equivalence — mesh UVs shifted by δ with offset 0 == mesh
UVs 0..1 with offset δ (rms 0.0005) — plus reseed-live and
mean-preservation checks.

**ER-009 — cutout alpha (`apply_alpha_masks` widened):** the grass-
understory ask. Two gaps, not a missing discard:
- **Detection:** `TransparencyAttrib M_binary` (the scatter `_proto`
  BLEND→binary rewrite) is cull-implemented as
  `AlphaTestAttrib(M_greater_equal, 0.5)` at max priority
  (`cullResult.cxx get_binary_state`) — fixed-function-only, so
  @modern it is silently ignored exactly like the loader's MASK
  attrib (fact #17's class). `_find_alpha_mask_geoms` now scans the
  subtree-COMPOSED state (geom-level or node-level M_binary both
  count) and applies M_binary's own predicate a ≥ 0.5, so compat's
  live fixed-function test and the in-shader discard cannot disagree
  (bit-identity gated).
- **Instancing:** the mask shader is a GEOM-level ShaderAttrib — on a
  `set_instanced` node it replaces the INSTANCING variant and the
  inherited F_hardware_instancing flag collapses every instance onto
  the origin (the measured pairing trap). `apply_alpha_masks(np,
  instanced=True)` compiles the mask variant WITH the instancing
  path; re-calling with a different flag reconfigures in place.
  Shaders cache per (cutoff, instanced).
Depth pass: unchanged — fact #17's caveat stands (@modern casts the
unmasked silhouette; compat cuts via the fixed-function test on the
depth pass's output alpha). The ER's "shadow.frag already discards"
premise was reviewed and corrected: no discard exists in any depth
path; planetside's scatter shadow-excludes all but boulder tier, so
nothing rides on it. Gate: test_alpha_mask `binary_*` (per-baseline
split, both detection shapes, compat bit-identity rms 0.0) +
`instanced_*` (trap 0/4 → fix 4/4, byte-exact opt-outs; info-skip on
stock 1.10).

### Session AB — GPU morph crowds: zero-copy bake, independent clone faces (LANDED)

Two upgrades to the Session Z path, driven by the shipped three-hero
roster (kade/wren/juno) and the crowd scenario. No API additions —
`set_gpu_morphs` just got cheaper and clone-aware.

**Bake ladder (enable cost 1.17 s → 0.07–0.08 s per production
face).** The delta texture is vertex-major (see the amended Session Z
data path) — the loader's own interleaved morph array IS the texture
when a vdata's column order matches the character slider order:
1. **Zero-copy** (order matches, tight, one array): raw array bytes →
   `set_ram_image_as`. wren/juno: 5/7 vdatas, ~95% of rows.
2. **numpy column gather** (any order/spread; numpy ships with
   panda3d-gltf so it is present wherever glTF morphs are): ~104
   C-speed column moves. kade's pack orders 5/6 prims
   non-canonically — 0.34 s pure-Python → 0.08 s.
3. **Pure-Python per-row loop** (no numpy): the Session Z path,
   correctness floor.
All three produce byte-identical textures — gate check
`bake_fast_matches_reorder` compares them AND asserts the fast path
stays available on loader output, so a future loader layout change
fails loudly instead of silently regressing enable cost. Class flags
`_MORPH_FAST_BAKE` / `_MORPH_NUMPY_REORDER` are test hooks, not user
knobs. `morph_index` fill is bulk (`array('f')` → handle.set_data).

**Clone contract (the synchronized-face defect).** `copy_to` on a
Character pointer-shares RenderStates + textures but DEEP-COPIES the
vdata (fact #20 — Session Z's "copies share vdata" was a wrapper-id
artifact). A clone of an enabled template therefore arrives
converted-but-puppeted: variant states + shared delta textures came
with the copy, and it renders the TEMPLATE's face through the
inherited `u_morphs` block. `set_gpu_morphs(clone)` detects the
per-geom `u_morph_tex` input, skips the bake entirely (zero new
textures — pointer-verified in-gate), and registers the clone's own
CharacterSliders + PTA (the clone root's input overrides the
inherited one). Clone opt-out parks a ZEROED block instead of
clearing — the as-copied geom states still carry the variant shader,
and a missing declared input asserts at draw (the gate caught this) —
and never touches the template. The bake cache inside one enable call
is keyed by `vdata.this` (id() is unstable across wrapper lookups and
can false-hit after collection — fact #20).

**Measured (three heroes + crowd):** bake wren 0.07 / kade 0.08 /
juno 0.08 s per face; 24 clones copy+register 0.25–0.49 s, zero
re-bake; 8-face morph-attributable 0.19 ms (interleaved min-of-5 —
single-run deltas drifted 0.4–0.8 ms under background load, so
cross-run A/Bs are not trusted for sub-ms attribution); 32 faces ALL
independently driven 4.3 ms. Clone RAM: ~the morph-column bytes per
clone (deep-copied vdata, ~18 MB on a production head) — a
strip-columns lever exists on paper, unbuilt pending evidence.

---

### Session AD — Effect sprites: `spawn_effect(atlas, ...)` (LANDED)

Baked-footage explosions/impacts (the CGVision air/space pack class) as
one call — a composition of already-gated parts, no new shader:

```python
meta = json.load(open('explosion_5_1_flipbook.json'))
atlas = loader.load_texture('explosion_5_1_flipbook.png')
fx = pipeline.spawn_effect(atlas, meta=meta, pos=impact_pos, size=9.0,
                           emission_scale=2.0)      # self-reaps at end
loop_fx = pipeline.spawn_effect(atlas, meta=meta, loop=True)
pipeline.remove_effect(loop_fx)                     # loops need this
```

- **Atlas contract:** PREMULTIPLIED RGBA flipbook from
  `tools/gen_flipbook.py` (alpha-aware since this session; the CGVision
  MOVs measured premultiplied — bake as-is). `meta=` takes the sidecar
  dict; explicit cols/rows/num_frames/fps also accepted. Gamma-2.2
  content — under `srgb_inputs` the game's format walk flags it sRGB
  like any emission map.
- **Mechanism:** CardMaker quad (world-width `size`, height follows the
  cell aspect), `set_billboard_point_eye()` (`billboard=False` = static
  two-sided card), depth-test-no-write, `set_screen(albedo=False,
  metallic=1)` — black metallic base zeroes diffuse_color AND
  spec_color exactly, leaving pure emission — plus `set_glass()` for
  premultiplied blending with coverage-weighted fog/atmo inscatter, and
  `exclude_from_shadows()` when a caster mask is configured (fact #17).
- **Lifecycle:** one-shots register in `_effects` and self-reap in
  `_update` via the public clears — every registry back to empty,
  byte-identical-when-unused (gated at rms 0.0). The returned NodePath
  may be reparented/moved while playing; if the game removes the node
  itself, dead registrations purge on the next reap (recompile-safe).
- **Residuals on record (field-watch, not blockers):** direct-spec
  grazing lobe at f0=0 (F90 white lobe) and the IBL BRDF-LUT bias term
  when an env map is bound — both bounded far below working
  emission_scale values. If an env ghost ever shows, the fix is an
  EFFECT define zeroing glass_spec.
- **Impacts on surfaces:** spawn at contact + surface-normal epsilon
  (game-side) or pass `depth_bias` (set_depth_offset units).
  Soft-particle depth fade is the slice-2 candidate, evidence-gated.

Gated by test_effects (13 analytic checks ×@game/@directional, both
engines identical): premultiplied composite, additive glow (a=0 adds,
occludes nothing), opaque core, unlit under ambient ×4, billboard vs
rotated parent, one-shot self-cleanup, shadow-mask exclusion, and
gen_flipbook RGBA-exact / RGB-unchanged assembly. Field guide (intake,
baking, adoption): `documents/BAKED_EFFECTS_GUIDE.md`.

### Session AE — ER-010 wet-sand waterline: `set_terrain_water` (LANDED)

The terrain half of the Sea-of-Thieves shore look (the water half —
depth-alpha shallows, foam, Gerstner — landed game-side Session 690).
One call next to `set_terrain_splat`:

```python
pipeline.set_terrain_water(chunk_np, world.water.water_z,
                           band_m=1.0,       # wet reach above sea level
                           dark=0.55,        # wet albedo multiplier
                           rough_mult=0.35,  # wet roughness multiplier
                           sat=1.25,         # wet chroma expansion
                           anim_amp=0.0)     # breathing edge, off by default
pipeline.clear_terrain_water(chunk_np)       # or water_z=None
```

- **Mechanism:** TERRAIN_WATER rider on the splat variant (a 6th key in
  the variant cache). Wetness is by WORLD Z only — all layers alike, no
  layer-semantics coupling: `wet = 1 - smoothstep(water_z, water_z +
  band_m, world_z)`, so submerged terrain is FULLY wet (the seafloor
  visible through the game's depth-alpha shallows must not read
  bone-dry — the ER's headline). Wet albedo = dark multiplier + chroma
  expansion about Rec.709 luminance (the transforms commute exactly),
  applied after macro variation; wet roughness = `clamp(pr *
  rough_mult, 0, 1)` ahead of GSAA. Everything lands through
  `mix(dry, wet_value, wet)` — a wet==0 fragment computes the
  water-off arithmetic bit-exactly (gated: dry-region rms 0.0 within a
  compile, < 1e-4 across variants).
- **Breathing edge (the ER-010 stretch):** `anim_amp` (m) offsets the
  edge by `amp · sin(phase + 2π · noise(world_xy / anim_scale))` —
  static value noise phase-shifts a shared `anim_period` cycle, so the
  sheen line advances/retreats unevenly along shore. The pipeline's
  `_update` pushes the phase per frame (O(animated nodes), zero when
  none); `anim_phase=<float>` pins it (the determinism valve the gate
  uses). amp=0 is EXACT (`edge + 0.0·noise == edge`).
- **Contracts:** unset nodes keep the water-free variant — byte-
  identical by construction; `set_terrain_splat` RE-calls preserve the
  node's water config (chunk re-dressing must not silently dry the
  shore); `set_terrain_water` before `set_terrain_splat` raises
  ValueError; clears restore byte-identically (rms 0.0 gated).
- **The sheen is a specular read:** under a bound env map the wet band
  mirrors the sky — the gate pins rough_mult reaching the specular
  term via a white env cube (env-BRDF at n·v≈1 rises as roughness
  falls; submerged region brightens 0.737→0.827 at rough_mult 0.12).

Gated by test_terrain_water (17 checks ×@game/@directional, both
engines identical): full-wet/below-waterline/band-mid exact analytics,
wet==0 arithmetic identity, re-dress preservation, sheen, 5 breathing-
edge checks (amp-0 exactness, phase-live, reach bounds, along-shore
variation), byte-identical clears + opt-out.

### Session AF — the lights slice: halos (ER-013), visibility queries, spot penumbra (LANDED)

Three small opt-in features from the 2026-07-24 fleet-look consult —
all Python/GLSL, all byte-identical when unused.

**1. Light halo billboards — `set_light_halo` (ER-013).**

```python
quad = pipeline.set_light_halo(bulb_np, color=(1, .2, .2),
                               size_m=0.4,   # world diameter close up
                               min_px=6.0,   # never smaller on screen
                               intensity=1.0)  # HDR-legal (feeds bloom)
pipeline.clear_light_halo(bulb_np)
```

A camera-facing quad (`halo.vert/frag`) expanded in VIEW space around
the node origin: `size = max(size_m, min_px / px_per_world)` with
`px_per_world = proj[1][1] * vp_h / (2 * clip_w)` — exact for both
perspective and orthographic lenses. Soft falloff `(1-r²)²` (center
exactly 1.0, zero slope — the analytic anchor), additive blend
(one, one) into the HDR scene buffer, **depth-TESTED but never
depth-written**: occlusion by hulls/terrain/ships is the depth test,
no occluder lists. The quad culls by OmniBoundingVolume (the shader
resizes it), is excluded from the shadow caster mask when one is
configured, and under LOG_DEPTH writes the same log-encoded
gl_FragDepth as pax_pbr so its depth test composes (shader tracked by
the recompile discipline). **Composition contract:** the fragment
multiplies by `u_emission_factor` — the set_blink/set_emission_scale
registry input — so a halo parented under a circuit node flashes in
sync with its bulbs with zero extra wiring.

**2. Depth-tap visibility queries — `add_visibility_query`.**

```python
pipe = init(enable_visibility_query=True)   # rebuild-class, like SSAO
q = pipe.add_visibility_query(sun_marker_np, radius_px=8.0,
                              max_occluder_depth=None)
# per frame: flare_sprite.set_alpha_scale(q.visibility)
pipe.remove_visibility_query(q)
```

The general replacement for hand-built analytic flare occluders. A
`max_visibility_queries × 1` buffer (`vis_query.frag`) samples the
scene depth in a 16-tap spiral disc around each target's projected
position and writes the visible fraction; `RTM_copy_ram` brings it to
RAM and `_update` reads it — `q.visibility` ∈ [0, 1], ~2 frames
latent. **The stall dodge:** the query buffer sorts BEFORE every
FilterManager buffer, reading LAST frame's depth texture, so the
readpixels waits on nothing but the 16×1 quad itself. Any
depth-writing geometry occludes (hull walls from inside — the case
ray-sphere occluders cannot express); partial coverage fades smoothly;
cleared depth counts open sky; `max_occluder_depth` (default
0.999·far) treats depth beyond it as open — set it just below a sky
dome's radius. Targets behind the camera or off-frustum read 0.0.
Enabling requests the scene depth target (shared with SSAO); the
visible chain is untouched (gated: rms 0.0 with queries active).

**3. Per-light spot penumbra — `enable_spot_exponent`.**

`init(enable_spot_exponent=True)` or
`set_enable_spot_exponent(True)` (recompile-class) compiles the
SPOT_EXPONENT read of `p3d_LightSource[i].spotExponent` —
GL_SPOT_EXPONENT semantics, `pow(cos angle-to-axis, exponent)` inside
the cone, on top of the existing SPOTSMOOTH edge. **Why opt-in:
Panda's Spotlight class default exponent is 50** (Light base reports 0
for non-spots) — an unconditional read would silently retighten every
existing spot. Exponent 0 = the flag-off flat cone exactly
(`pow(x>0, 0) == 1`, gated at rms 0). The flood-lamp recipe: a wide
Spotlight (fov 90–120°), `set_exponent(1–4)` for the soft
center-weighted wash, optional shadows — landing pads, hangar bays,
hull floods. Point/directional lights are never affected.

Gated by test_light_halo (10 checks + @directional shadow-mask row),
test_visibility_query (7 checks + latency INFO, +@logdepth), and
test_spot_exponent (7 checks, +@directional) — identical on both
engines.

### Session AJ — the voxel-lane trio: photo mode, loud visibility, streaming detail maps (LANDED)

Three Animal Crossfire asks (`C:\python\paxcraft\docs\ENGINE_NOTES.md`,
2026-07-27), all pure Python, all serving planetside too (concordance).

**1. Photo-mode snapshots — `render_snapshot` (`snapshot.py`).**

```python
tex = pipe.render_snapshot((x, y, z), (h, p, r), size=(1280, 720),
                           fov=None, near=None, far=None,      # copy main lens
                           shadow_center=None, shadow_extent=None,
                           filename='shot.png')                # optional write
pipe.release_snapshot_resources()                              # optional; auto on rebuilds
```

One frame of the FULL pipeline (PBR, shadows, atmosphere, SSAO, bloom,
flare, tonemap — mirroring the pipeline's current config) from an
arbitrary pose into a RAM-backed RGBA8 texture, WITHOUT perturbing the
player's view. `SnapshotRenderer` keeps a persistent offscreen mirror
of the post chain (scene HDR buffer → SSAO pair → bloom
extract/down/up + flare → tonemap into an `RTM_copy_ram` buffer), all
buffers inactive except during a shot: the call deactivates the player
chain (window + FilterManager buffers + vis-query buffer), renders one
engine frame, restores everything — the window keeps its last
presented image (gated rms 0.0), and a same-pose snapshot matches the
window capture at rms 0.0 (full-pipeline parity, gated). Repeat shots
measured 3–24 ms — the AI-building feedback loop this was filed for
runs interactively (the pre-API fallback was ~30 s subprocess boots).
Camera-coupled state is swapped per shot: `camera_world_position`,
orbital-atmosphere quad placement, halo viewport height, the log-depth
coefficient (snapshot lens defaults COPY the main lens, so log-depth
games keep their wide frustum for free). **The shadow-extent
contract:** games recentre the sun shadow frustum on the main camera,
so a far-away snapshot sees absent coverage — pass
`shadow_center=`(usually the pose)/`shadow_extent=` for a one-frame
recentre with exact restore (gated both ways), or recentre yourself
around the call. Known limits (header of `snapshot.py`): aux scene
cameras render with their game-owned transforms (re-aim the sky camera
yourself for off-pose shots); the viewmodel is excluded; no TAA on
single frames. Chain releases on every rebuild-class toggle and
rebuilds lazily at the next shot (gated through a set_enable_bloom
flip).

**2. Visibility queries fail LOUDLY — `visibility_query_valid`.**

The Session-AF query read the scene depth texture; a viewmodel region
in `depth_mode='clear'` stomps that texture full-screen, and the
queries then confidently reported "open sky everywhere" (flare through
mountains — a downstream game lost three sessions to it). Now:
`pipe.visibility_query_valid` is False whenever a post-main region
clears depth; while invalid every query reports `visibility 0.0` with
`.valid False` (fail CLOSED, one loud print per transition, restored
automatically on unregister). `register_viewmodel_camera(...,
on_depth_degrade='raise')` makes a degraded 'range' request fatal at
registration (log depth on, or stock 1.10), and
`set_enable_log_depth(True)` degrades a live 'range' viewmodel
properly (region clear flipped on) and loudly, instead of leaving it
silently broken. +9 test_visibility_query checks across the legs.

**3. `set_detail_maps` append-only registration.**

Registering model N now stamps ONLY model N's geoms
(`_stamp_detail_entry`); the old path ended every call in the global
valve refresh — O(total registered geoms) per call, which made
per-attach registration on a ~300-chunk streaming terrain a
full-registry restamp per weapon-fire remesh (measured game-side:
60→32 fps). Removal with no skinning valves anywhere is O(entry).
The global refresh still runs where the valve registry can interact
(reconfigure-in-place, removal while valves exist, valve flips,
recompiles — character-lane events, never the chunk-attach path).
+3 test_detail_maps checks (stamp counting, no-restamp removal,
bit-identical survivor).

Gated by NEW test_snapshot (8 checks + 3 @directional shadow-contract
rows + SSAO flat-identity) and the extended visibility/detail tests —
identical on both engines.

### Session AK — follow= scene cameras: the far-field lane (LANDED)

The voxel game's builder lane asked how to render a 2–6 km horizon
ring (baked worldgen heightfield + build-massing imposters) behind a
~160 m streamed world, with log depth unavailable (their viewmodel
runs depth_mode='range'). The answer is §6's background regions plus
one new flag — `register_scene_camera(..., follow='pose'|'hpr')` (§6
has the full semantics): the pipeline mirrors the main camera onto
follow cameras each frame in `_update`, and `render_snapshot` re-aims
them to the snapshot pose for its one frame with exact restore. Depth
story: each region clears depth, so the ring camera's own lens (e.g.
near 50 / far 6000 — 24-bit depth resolves ~1 cm at 3 km) coexists
with any world far plane; no log depth, no reversed-z. Recommended
layering: sky (sort −100, 'hpr') → ring (sort −50, 'pose',
clear_color=None, own graph + own ~20-line shader — no PBR inputs, no
shadow-cascade traversal by construction) → world (sort 0). Documented
interaction: background regions never write the main scene depth, so
visibility queries cannot see the ring (games gate sun flares from
their own horizon data if they care). Also fixed here: the main
region's clears are saved/restored when the last background camera
unregisters. Gate: test_snapshot section 9 (+6 checks — live sync,
composite, snapshot re-aim + restore, 'hpr' mode, clear restoration),
green both engines; full matrix totals unchanged from Session AJ.

### Session AL — the water surface: `build_water_surface()` (LANDED)

The shared game-water (planetside `world/water.py` → paxcraft
`ocean.py` near-verbatim port) promoted into the engine on the water
lane's ask — both games consume ONE module now.
`pipeline.build_water_surface(parent_np, water_z,
params=WaterParams(...), **geometry)` returns a
`water.WaterSurface`: a Gerstner-swell follow grid (dense near grid +
optional horizon annulus, or a single windowed grid with
`rim_fade=True`) at world z = water_z, shaded by
`shaders/water_surface.{vert,frag}` — the field-proven recipe
(noise-not-sine fragment normals, restrained Fresnel, Beer-Lambert
body colour over real seafloor depth, depth-keyed shore melt,
slope-gated contact foam + marching bands, crest-pinch whitecaps) with
every game-specific deviation promoted to a `WaterParams` uniform
(defaults = the planetside ocean, pinned in-gate).

The GAME is the depth PROVIDER: it bakes an R32F world-z seafloor
window however its world knows it and hands it over via
`set_seafloor(tex, origin_xy, size_m)` (or binds
`u_seafloor`/`u_sf_origin_size` on `.root` — the uniform names match
the pre-promotion game copies on purpose). `params.uncovered` sets
the no-data policy: `'deep'` = open ocean (horizon games), `'dry'` =
alpha exactly 0 (windowed coastal games — far-field land beyond the
window). Per frame the game calls `update(x, y, camera_pos)` — which
also feeds the fragment stage's aerial haze from `pipeline.atmo_*`
(the EXACT pax_pbr.frag analytic block, so sea and terrain haze as
one system; atmosphere off = exact no-op) — and
`set_environment(sun_dir, sun_color, sky_horizon, sky_zenith)` on
day-night ticks, which applies the `water_sun` HDR luminance knee
(s = 1/(1+knee·max_c), default 0.25) before the push. Surface is
transparent-bin, depth-write off, omni-bounds (follow meshes are
never frustum-culled), and shadow-excluded when a caster mask is
configured. Underwater eye effects, swimming and audio stay
game-side. Gate: test_water (15 checks ×@game/@directional, both
engines) — the analytic-haze rows match an independent Python
ray-evaluation to ≤0.002.

## 10. Testing Contract

- Every feature has (at least) one paxtest: gamma, lighting (×sun-modes),
  bloom, rebuild, the shadow suite (shadows/gltf/quality/grazing/snap),
  skinning, ftl_blur, scale (+@logdepth), atmosphere, ambient_sh, glass
  (×sun-modes), doublesided (×sun-modes), ambient_scale, env_map,
  local_lights (×sun-modes), orbital (+@logdepth), srgb, ssao
  (+@logdepth/@msaa4), lens_flare, morph_gltf, data_texture,
  terrain_splat (×sun-modes), terrain_water (×sun-modes), instancing
  (×sun-modes), rigid_clips, screen, alpha_mask, effects (×sun-modes),
  light_halo (×sun-modes), visibility_query (+@logdepth),
  spot_exponent (×sun-modes).
  Run `tools/paxtest/run.py` before and after.
- Add a test WITH the feature, not after. Analytic checks > goldens;
  goldens (`--golden` / `--check-golden`) are a refactor safety net.
- The testbed (`sfb2/test3d_pax.py`) is the eyeball companion — its
  `--selftest` mode (offscreen, 30 frames, screenshot) is scriptable.
- Harness gotchas encoded in the tests (keep them in mind for new ones):
  attach a small `AmbientLight` in lighting tests (with NO lights attached,
  `p3d_LightModel.ambient` is pure white and floods PBR output); render a
  frame before any manual buffer discovery; sample bar/halo centers to
  dodge the tonemap dither.
