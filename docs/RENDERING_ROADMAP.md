# Pax3D Rendering Roadmap
**Repository:** github.com/Apocrypha-Stellarum/Pax3D
**Game:** Pax Abyssi Space Simulation
**Engine base:** Panda3D 1.10.16 fork
**Current renderer:** panda3d-simplepbr 0.13.1
**Document created:** 2026-02-26

---

## 1. Executive Summary

Pax3D is a fork of Panda3D being customised specifically for the Pax Abyssi space simulation. The game is a 3D space sim with real astronomical data (119,000+ HYG catalog stars), orbital mechanics, planetary rendering, and starship combat. Its scenes are simple in structure — one dominant star illuminating planets, moons, and ships — but extreme in scale, spanning distances from metres to thousands of astronomical units.

The current rendering stack (stock Panda3D 1.10.16 + panda3d-simplepbr 0.13.1) works but has a long tail of friction:

- **DirectionalLight orientation is unintuitive and mesh-winding-dependent.** Two debugging sessions (416-417) were needed to find a working formula, and the correct formula contradicts what algebra predicts. This is the single highest-priority problem.
- **No bloom.** The game compensates manually with oversized coronas and RGB reduction factors — a fragile, effect-specific workaround.
- **No HDR tonemapping control.** simplepbr's built-in tonemapping cannot be tuned per-scene, which matters when switching from interstellar space (nearly black) to close planetary approach.
- **No atmospheric scattering.** Planets seen from space have a manually-tuned additive Fresnel atmosphere shader — scientifically incorrect and visually limited.
- **No logarithmic depth buffer.** Scenes spanning AU-scale distances require careful near/far management to avoid Z-fighting. The current workaround (sky camera at sort -100 with a separate DR) is a symptom of this.
- **simplepbr's FilterManager architecture causes interaction problems.** Any additional camera display regions must be created on simplepbr's offscreen buffer, not the window. This has caused multiple bugs.

The roadmap below structures improvements into five phases, from highest-impact fixes to longer-term architectural improvements. Phase 1 is the only blocking item — everything else is additive quality improvement.

---

## 2. Current State Assessment

### 2.1 What Works

- **simplepbr PBR rendering:** GLTF models (ships, stations) render with correct metallic-roughness, normal maps, emissive maps. Lighting looks physically plausible.
- **Two-light system:** One DirectionalLight (sun) + one AmbientLight. Simple and sufficient for space scenes.
- **MSAA 4x:** Anti-aliasing active via simplepbr.
- **Shadow mapping:** Implemented but disabled by default. Orthographic lens, 2048x2048 shadow map. Not yet validated at game scales.
- **Formula B directional lighting:** After Sessions 416-417, a working HPR formula for the DirectionalLight has been found empirically. It is hardcoded in `sun_position_manager.py`. Confirmed correct at the EAST cardinal position; remaining three cardinals need validation.
- **setShaderOff() compensation pattern:** All additive-blended effects (sun glow, weapon bolts, nebula billboards, atmosphere) correctly opt out of simplepbr with documented RGB reduction and corona scale factors.
- **Sky camera system:** Separate DR on simplepbr's offscreen buffer at sort -100 for distant objects that need independent frustum culling. Functional with OmniBoundingVolume on all sky-tagged nodes.
- **PRC configuration:** Correct Panda3D PRC settings documented and enforced (no texture compression, no FXAA, hardware framebuffer).

### 2.2 What Is Broken or Incomplete

| Issue | Severity | Current Workaround |
|-------|----------|--------------------|
| Directional lighting formula is empirically derived, not understood | High | Formula B works at 1 cardinal position. Needs full validation. |
| No bloom | High | Manual RGB reduction + 1.8x corona scale on every effect |
| No HDR/exposure control | Medium | simplepbr `exposure` parameter, but no scene-adaptive control |
| No atmospheric scattering | Medium | Custom additive Fresnel shader, scientifically wrong |
| No logarithmic depth buffer | Medium | Sky camera + OmniBoundingVolume workaround |
| simplepbr FilterManager interaction | Medium | Sky camera DR must target offscreen buffer, not window |
| setPos() corrupts DirectionalLight under simplepbr | Medium | Documented pitfall, avoided in code |
| lookAt() corrupts DirectionalLight under simplepbr | Medium | Documented pitfall, avoided in code |
| Bloom compensations are per-effect magic numbers | Low | 0.45x sun, 0.25x weapons, 1.8x corona — all fragile |
| Winding-dependent lighting (planet mesh vs clean UV sphere) | Low | Accepted — Formula B works for game's mesh |
| Formula cycle debug code still in sun_position_manager.py | Low | Temporary — see Phase 1 cleanup tasks |

### 2.3 The Directional Lighting Problem in Detail

This is covered fully in `documents/3D_SPACEFLIGHT_MODULE/SCENE_LIGHTING.md`. Summary:

Panda3D's `setHpr(H, P, R)` maps the node's +Y axis to a world-space forward vector via:
```
forward = (-sin(H)*cos(P),  cos(H)*cos(P),  sin(P))
```

For a clean simplepbr scene with a standard UV sphere, the lit hemisphere faces **-forward** (light travels in the -forward direction). This is the algebraically expected behaviour: `forward = -sun_dir`, producing Formula C (`atan2(sun_dir.x, -sun_dir.y)`).

However, the game's planet mesh (built in `planet_factory.py:_create_procedural_sphere()`) uses the opposite winding order, causing the lit hemisphere to face **+forward**. The working formula is therefore Formula B: `atan2(-sun_dir.x, sun_dir.y)`, which maps `forward = sun_dir`.

The root cause is almost certainly simplepbr's fragment shader using `gl_FrontFacing` to flip surface normals, which inverts the effective lighting direction for back-wound geometry. This is an engine-level issue that should be resolved definitively in Pax3D.

---

## 3. Phased Roadmap

| Phase | Title | Priority | Effort | Status |
|-------|-------|----------|--------|--------|
| 1 | Bulletproof Directional Lighting | Critical | Low-Medium | In progress |
| 2 | Post-Processing Pipeline (Bloom + HDR) | High | Medium | Not started |
| 3 | Shader Infrastructure | Medium | Medium-High | Not started |
| 4 | Atmospheric and Environmental | Medium | High | Not started |
| 5 | Large-Scale Rendering | Low | High | Not started |

---

## 4. Phase 1: Bulletproof Directional Lighting

**Goal:** Eliminate all ambiguity about DirectionalLight orientation under simplepbr. One correct API, zero winding-dependent behaviour, correct behaviour with `lookAt()` and `setDirection()`, shadows that work at astronomical scales.

**Why this is Phase 1:** Every other rendering improvement depends on correct base lighting. If the sun illuminates the wrong hemisphere, bloom, atmospheric scattering, and PBR improvements all build on a broken foundation.

### 4.1 Immediate Game-Side Fixes (No Engine Changes)

These fixes can be applied to `C:\python\sfb2` with the current stock Panda3D, independently of any Pax3D build.

#### 4.1.1 Validate Formula B at All Four Cardinal Positions

**Status:** Confirmed correct at EAST (sun at +X). Three positions remain untested.

**Procedure:**
1. Launch `plan.py`, navigate to a planet with Formula B active (default)
2. Press `Ctrl+L` to enable the lighting debug overlay
3. Press `Ctrl+Right` to cycle through cardinal positions: SOUTH, WEST, NORTH, EAST
4. At each position, confirm the lit hemisphere of the planet faces the sun billboard (YELLOW line in debug overlay matches GREEN line)
5. If any position fails, note the sun_dir, HPR, and forward vector from the OSD dump

**Pass criterion:** `dot(forward, sun_visual_dir) >= 0.99` at all four cardinals.

#### 4.1.2 Fix the Debug Tool

**File:** `C:\python\sfb2\modules\planetary_debug_tools.py`

Two known bugs introduced during session 417:

1. **Angle check uses wrong sign** (line ~197): `toward_light = Vec3(-fwd)` is correct for Formula C (lit=-forward) but wrong for Formula B (lit=+forward). Change to `toward_light = Vec3(fwd)`.

2. **Debug line legend is inverted**: The legend docstring and OSD text describe GREEN as opposing YELLOW, but with Formula B they should overlap. Update all legend text.

3. **Ctrl+Left/Right not working**: Verify the key binding guard (`if not self.active: return`) is not blocking. Check for binding conflicts with other systems. The 3-tuple to 4-tuple conversion for cardinal entries (done in session 417) may have unpacking bugs at all call sites.

#### 4.1.3 Clean Up Temporary Debug Code

Once Formula B is validated at all cardinals, remove the development scaffolding from `sun_position_manager.py`:

- Remove `_light_formula` attribute (line ~22)
- Remove `_FORMULA_NAMES` class variable (line ~33)
- Remove `_cycle_light_formula()` method
- Remove `app.accept("shift-f9", ...)` binding
- Remove the four-formula switch block in `update_from_orbit()` (lines ~197-218)
- Hard-code Formula B:

```python
heading = math.degrees(math.atan2(-sun_dir.x, sun_dir.y))
horiz_len = math.sqrt(sun_dir.x ** 2 + sun_dir.y ** 2)
pitch = math.degrees(math.atan2(sun_dir.z, horiz_len))
app.lighting.sun_light_np.setHpr(heading, pitch, 0)
app.lighting.set_sun_direction(sun_dir)
```

Update `debug_modules/directional_light_test.md` header to mark Formula B as the confirmed answer.

#### 4.1.4 Update SCENE_LIGHTING.md

Current document (rewritten session 417) still has "Validation status: Confirmed at EAST cardinal position." After full validation, update to "Confirmed at all cardinal positions" and remove the "Temporary Development Tools" section at the bottom.

### 4.2 Engine-Level Fix (Pax3D Change)

**Goal:** Make `DirectionalLight.setDirection(vec3)` and `DirectionalLight.lookAt(target)` work correctly and intuitively under simplepbr's PBR shader, regardless of mesh triangle winding.

#### 4.2.1 Understand the Root Cause

The problem has two layers:

**Layer 1 — HPR formula confusion.** `setHpr()` on a node maps +Y to a world vector via the formula above. The relationship between HPR angles, +Y forward, and light direction is non-obvious. A dedicated `setDirection(world_vec)` method that takes the sun-to-scene vector directly would eliminate this entirely.

**Layer 2 — Winding-dependent lighting.** simplepbr's fragment shader likely contains something like:
```glsl
vec3 N = normalize(v_normal);
// Possibly:
if (!gl_FrontFacing) { N = -N; }
```
This flips the surface normal for back-facing fragments, which means a sphere with inverted winding order sees inverted normals, and therefore inverted lighting direction. The game's planet mesh has the opposite winding from a standard UV sphere, producing the `forward = sun_dir` instead of `forward = -sun_dir` behaviour.

**Confirm the root cause** by reading simplepbr's fragment shader source. With panda3d-simplepbr installed at `C:\python\pax3d-env\Lib\site-packages\simplepbr\`, the shader files are `.glsl` fragments inside the package. Find and read the main fragment shader and check for `gl_FrontFacing`.

```bash
# Find simplepbr shaders
find C:/python/pax3d-env -name "*.glsl" -path "*/simplepbr/*"
```

#### 4.2.2 Option A: Add `setDirection()` Method to DirectionalLight

**Files to modify:**
- `C:\python\pax3d\panda\src\pgraphnodes\directionalLight.h`
- `C:\python\pax3d\panda\src\pgraphnodes\directionalLight.cxx`

**What to add:** A `setDirection(const LVector3 &dir)` method that sets the node's orientation such that the correct hemisphere is lit, regardless of simplepbr's winding convention.

The implementation depends on confirming which convention simplepbr uses (lit=+forward or lit=-forward). Once confirmed:

```cpp
// If simplepbr lights the hemisphere in the +Y direction (forward):
void DirectionalLight::setDirection(const LVector3 &light_to_target) {
  // Compute HPR such that forward (+Y after rotation) = normalize(light_to_target)
  // light_to_target is the direction FROM sun TO scene
  LVector3 d = normalize(light_to_target);
  PN_stdfloat h = atan2f(-d[0], d[1]) * (180.0f / MathNumbers::pi_f);
  PN_stdfloat horiz = sqrtf(d[0]*d[0] + d[1]*d[1]);
  PN_stdfloat p = atan2f(d[2], horiz) * (180.0f / MathNumbers::pi_f);
  set_hpr(h, p, 0);
}
```

Also expose this in Python via the `.pyi` stub or `.i` interrogate file so it's callable as `light_np.node().setDirection(vec)`.

This is the minimal viable fix — the game can then replace the HPR formula in `sun_position_manager.py` with:
```python
sun_to_scene = -sun_dir  # sun_dir is planet-to-sun; negate for sun-to-planet
light_node.setDirection(sun_to_scene)
```

#### 4.2.3 Option B: Fix Winding Handling in simplepbr

Alternatively, rather than working around the problem in the engine, fix the game's planet mesh winding to match the standard UV sphere convention that simplepbr expects. This is a game-side change, not an engine change.

In `C:\python\sfb2\modules\planet_factory.py`, find `_create_procedural_sphere()` (around lines 416-423) and swap the vertex order to match standard counter-clockwise winding when viewed from outside:

```python
# Current (session 417 identified this winding):
tris.addVertices(bottom_left, bottom_right, top_left)
tris.addVertices(bottom_right, top_right, top_left)

# Standard CCW winding (what simplepbr expects):
tris.addVertices(bottom_left, top_left, bottom_right)
tris.addVertices(bottom_right, top_left, top_right)
```

If this change makes Formula C (the algebraically correct formula) work, it would be the cleanest resolution: the planet mesh matches simplepbr's convention, `lookAt(-sun_dir)` works as expected, no custom `setDirection()` method needed.

**Risk:** Changing planet mesh winding may affect other things (atmosphere Fresnel shader, normal maps if any are added later, collision geometry). Test carefully. If it works, also update SCENE_LIGHTING.md's "Confirmed Working Formula" section to replace Formula B with Formula C / lookAt().

#### 4.2.4 Option C: Add `lookAt()` Override That Works Under simplepbr

The problem with Panda3D's standard `lookAt()` on a DirectionalLight is that it also sets `setPos()`, which corrupts the transform under simplepbr's FilterManager (which moves `base.cam` to an offscreen buffer, changing what "position" means for lights attached to render).

A Pax3D-specific override could strip the position component:

```cpp
void LightLensNode::lookAtLighting(const LPoint3 &point, const LVector3 &up) {
  // Standard lookAt orientation only, no position
  NodePath::look_at(point, up);
  // Force position back to origin (clear any position corruption)
  set_pos(0, 0, 0);
}
```

This is a workaround rather than a proper fix, but it would allow the game code to use the readable `light_np.lookAtLighting(-sun_dir)` pattern.

#### 4.2.5 Recommended Approach

1. **First:** Confirm whether the winding fix (Option B) alone resolves the issue. This is the cheapest change and produces the most "correct" code.
2. **If winding fix works:** Use Formula C / `lookAt()` convention throughout. No engine changes needed.
3. **If winding fix causes other problems:** Add `setDirection()` to DirectionalLight (Option A). This is engine-level but clean and well-scoped.
4. **Do not implement Option C** — it is a workaround on top of a workaround and does not address the root cause.

### 4.3 Shadow Mapping at Astronomical Scales

**Current status:** Shadows implemented but disabled. When enabled, the OrthographicLens is configured as:
```python
lens.setNearFar(1, 1000)
lens.setFilmSize(400, 400)  # 400x400 IEU coverage
```

**Problem:** At typical planet viewing distances (500-5000 IEU), a 400x400 IEU film size covers only a fraction of a planet's shadow. The shadow map near/far needs to span the planet diameter (~12 IEU for Earth, ~140 IEU for a gas giant).

**Engine change needed:** Panda3D's DirectionalLight shadow lens (`OrthographicLens`) currently uses static near/far/filmSize. For space scenes, we need these to be automatically computed based on the scene's bounding volume or configurable per-frame.

**Game-side workaround (no engine change):** Set shadow lens parameters dynamically in `planetary_lighting.py` based on the current planet's diameter (available from `planet.diameter_km`):

```python
def update_shadow_for_planet(self, planet_diameter_ieu):
    lens = self.sun_light.node().getLens()
    margin = planet_diameter_ieu * 1.5
    lens.setFilmSize(margin * 2, margin * 2)
    lens.setNearFar(-margin, margin)
```

### 4.4 Phase 1 Deliverables

- [ ] Formula B validated at all four cardinal positions (game-side)
- [ ] Debug tool angle check and legend corrected (game-side)
- [ ] Ctrl+Left/Right cardinal cycling fixed (game-side)
- [ ] Temporary formula-toggle code removed from `sun_position_manager.py` (game-side)
- [ ] SCENE_LIGHTING.md updated with full validation status (game-side)
- [ ] Root cause of winding-dependent lighting confirmed (inspect simplepbr fragment shader for `gl_FrontFacing`)
- [ ] Either: planet mesh winding fixed (game-side) OR `DirectionalLight.setDirection()` added (engine-side)
- [ ] `lookAt()` / `setPos()` corruption under simplepbr documented formally in engine comments
- [ ] Shadow lens dynamic sizing implemented (game-side)

---

## 5. Phase 2: Post-Processing Pipeline

**Goal:** Bloom + HDR tonemapping as first-class engine features, removing the need for manual RGB reduction and oversized corona hacks.

**Prerequisites:** Phase 1 complete. Bloom is only useful if the base lighting is correct.

### 5.1 Architecture Decision: simplepbr Extension vs. Replacement

simplepbr uses Panda3D's `FilterManager` to move `base.cam` to an offscreen buffer and apply post-process shaders. The post-process chain is:

```
Scene render → Offscreen buffer → Post-process quad → Window
```

**Option A: Extend simplepbr** — Add bloom and improved tonemapping as additional passes in simplepbr's existing FilterManager chain. This keeps compatibility with the existing `simplepbr.init()` API.

**Option B: Replace simplepbr with Pax3D's own forward PBR pipeline** — Write a replacement that provides the same PBR shading plus the additional features. Higher effort but full control.

**Recommendation:** Option A for Phase 2. Option B is a Phase 3 goal.

### 5.2 Bloom: Kawase Dual-Filter

**Source:** tobspr/RenderPipeline — `RenderPipeline/rpplugins/bloom/`

The tobspr bloom pipeline uses a Kawase dual-filter (not Gaussian) which is faster and produces a nicer spread:

1. Bright-pass: threshold + knee curve to extract luminance above threshold
2. Downsample x4 passes (half resolution each time, Kawase filter)
3. Upsample x4 passes with per-mip tinting for artistic control
4. Composite: add to main scene with configurable intensity
5. Optional lens dirt: multiply the bloom contribution by a dirt texture

**Files to port (5 shaders, ~270 lines GLSL total):**
- `bloom_filter.frag.glsl` — bright-pass extract
- `bloom_downscale.frag.glsl` — Kawase downsample
- `bloom_upscale.frag.glsl` — Kawase upsample
- `bloom_apply.frag.glsl` — composite
- `bloom_lens_dirt.frag.glsl` — optional lens dirt multiply

**Extraction procedure:**
1. Replace `#pragma include "render_pipeline_base.inc.glsl"` with explicit uniform declarations
2. Replace `GET_SETTING(bloom, threshold)` with `uniform float bloom_threshold;` etc.
3. Replace `get_texcoord()` with `gl_FragCoord.xy / vec2(screen_width, screen_height)`
4. Remove `#pragma optionNV` lines (NVIDIA-specific optimisation hints, not needed)
5. Replace `HAVE_PLUGIN(x)` guards with `#define HAVE_PLUGIN_x 0` constants

**Integration in Pax3D:**
- Add bloom pass to simplepbr's FilterManager chain after the main PBR pass
- Expose parameters via `simplepbr.init()` keyword args: `enable_bloom=False, bloom_threshold=0.8, bloom_intensity=1.0, bloom_radius=1.0`
- Or as a post-init configuration: `simplepbr_pipeline.set_bloom(threshold=0.8, intensity=1.0)`

**Impact on existing game code:**
- Remove per-effect RGB reduction factors (0.45x sun, 0.25x weapons)
- Remove 1.8x corona scale hack on weapon bolts
- Keep `setShaderOff()` on additive-blended nodes (bloom will naturally capture them if they're bright enough)
- The PBR compensation pattern in `SIMPLEPBR_RENDERING.md` becomes obsolete and can be simplified

### 5.3 HDR Tonemapping

**Source:** tobspr/RenderPipeline — `RenderPipeline/rpcore/stages/apply_colors_stage.py` and `tonemapping.inc.glsl`

tobspr provides 6 operators:
1. Uncharted 2 (Filmic)
2. Reinhard
3. Optimised Filmic (John Hable)
4. ACES
5. Drago
6. Exponential

Plus an EV100 exposure model: `exposure = pow(2.0, ev100) / 1.2`

**Current simplepbr tonemapping:** simplepbr uses a fixed Reinhard-based tonemapping in its fragment shader, controlled only by the `exposure` parameter at init time.

**What we need:** Per-scene tunable tonemapping with scene-adaptive exposure. Space scenes have extreme luminance range — directly facing a star vs. deep-space looking away from any star spans many stops of exposure.

**Extraction procedure for `tonemapping.inc.glsl`:**
1. It is self-contained with no external dependencies — nearly drop-in
2. Replace any `GET_SETTING` macros with uniform declarations
3. Include as a utility header in Pax3D's PBR fragment shader

**Integration:**
- Add `tonemap_operator` uniform (0-5) and `ev100` uniform to the PBR shader
- Expose via Python API: `simplepbr_pipeline.set_tonemap(operator='aces', ev100=0.0)`
- Or auto-compute EV100 from scene luminance average (requires luminance histogram pass — scope this for Phase 3)

**Minimal viable change:** Just replace simplepbr's Reinhard with ACES (widely considered the best for games), with a configurable `exposure` multiplier. This is a one-line GLSL change in simplepbr's fragment shader.

### 5.4 Color Correction (Optional, Phase 2)

**Source:** tobspr — `color_spaces.inc.glsl` and post-process passes

Available from tobspr with low extraction cost:
- **Vignette:** 10-line GLSL, darkens screen edges, configurable strength and falloff
- **Film grain:** procedural noise overlay, frame-counter seeded for temporal variation
- **Chromatic aberration:** RGB channel offset at screen edges, ~15 lines GLSL

These are purely cosmetic and can be wired as toggles: `enable_vignette=False, enable_film_grain=False`.

For a space sim, vignette (subtle) is appropriate. Film grain and chromatic aberration are optional taste items.

### 5.5 Phase 2 Deliverables

- [ ] tobspr bloom shaders extracted and adapted (5 files, ~270 GLSL lines)
- [ ] Bloom pass integrated into Pax3D's simplepbr fork
- [ ] `simplepbr.init()` accepts `enable_bloom`, `bloom_threshold`, `bloom_intensity` parameters
- [ ] Game-side PBR compensation magic numbers removed from sun, weapon, nebula systems
- [ ] `SIMPLEPBR_RENDERING.md` PBR Compensation Pattern section updated/simplified
- [ ] tobspr tonemapping.inc.glsl extracted
- [ ] ACES tonemapping replaces Reinhard in simplepbr fragment shader
- [ ] `exposure` is runtime-configurable from Python
- [ ] (Optional) Vignette pass added with configurable strength
- [ ] Test scene: star at various distances, weapon fire, planet surface — verify bloom and tonemap look correct

---

## 6. Phase 3: Shader Infrastructure

**Goal:** Port tobspr's PBR BRDF library and utility headers into Pax3D, establishing the foundation for a potential full simplepbr replacement.

**Prerequisites:** Phase 2 complete. Bloom and tonemapping should be working before re-doing the PBR pipeline.

### 6.1 BRDF Library Port

**Source:** `tobspr/RenderPipeline/rpcore/render_pipeline/rpcore/pluginbase/brdf.inc.glsl` — 354 lines

**Contents:**
- GGX microfacet distribution `D_GGX(N, H, roughness)`
- Smith-GGX geometry function `G_SmithGGX(N, V, L, roughness)`
- Fresnel-Schlick approximation `F_Schlick(cosTheta, F0)`
- Full Cook-Torrance specular BRDF
- Disney diffuse (Burley's normalized diffuse)
- Multiscatter GGX energy compensation

**Extraction procedure:**
1. Self-contained — no external dependencies beyond standard GLSL math
2. Strip the `#pragma include` header
3. Replace any `GET_SETTING` calls (check for these — most BRDF code has none)
4. Place as `pax3d_brdf.inc.glsl` in Pax3D's shader utility directory

**Why this matters:** simplepbr's current BRDF is functional but its Cook-Torrance implementation differs from tobspr's. tobspr's version handles multiscatter energy compensation (prevents energy loss at high roughness) which makes metallic surfaces look more physically correct.

### 6.2 Utility GLSL Libraries

**Source:** Various tobspr include files

**`color_spaces.inc.glsl`** — low extraction cost, self-contained:
- `sRGB_to_linear()` / `linear_to_sRGB()`
- `RGB_to_HSL()` / `HSL_to_RGB()`
- `RGB_to_XYZ()` / XYZ_to_xyY()
- `xyY_to_XYZ()`
Useful for any shader that needs to work in linear space and convert back.

**`normal_packing.inc.glsl`** — octahedral encode/decode:
- Encodes 3-component normal to 2 components (useful for GBuffer if deferred rendering is ever considered)
- Currently not needed for forward rendering but adds no cost to include

**`math_functions.inc.glsl`** — various helper functions (saturate, pow2, lerp variations, etc.)

### 6.3 Option: Full simplepbr Replacement

This is a longer-term option. Rather than extending simplepbr, write `Pax3DPipeline` as a replacement:

- Same `render`-to-offscreen-buffer FilterManager setup
- Pax3D's own PBR fragment shader using the BRDF library above
- Native bloom, tonemapping, and vignette (from Phase 2)
- Native `setDirection()` for directional lights (from Phase 1)
- Eliminates the `simplepbr` Python package dependency

**Benefit:** Full control over the shader. No constraints from simplepbr's design decisions.
**Cost:** Significant effort. All existing simplepbr API calls in game code must be updated.
**Risk:** Regression — simplepbr has been battle-tested in the game for hundreds of sessions. A replacement needs extensive validation.

**Recommendation:** Do not implement a full replacement in Phase 3. Port the BRDF and utility libraries first, and improve the existing simplepbr rather than replacing it. A full replacement is a Phase 4/5 consideration.

### 6.4 SMAA / FXAA Anti-Aliasing

**Source:** tobspr — canonical library integrations

simplepbr's MSAA 4x works but is applied before tonemapping, meaning it antialiases in linear space. SMAA (subpixel morphological antialiasing) and FXAA work on the final tonemapped image and often produce better results at lower cost.

**Extraction:** SMAA is a canonical library (Jimenez et al.) and can be integrated directly from the reference implementation. tobspr's integration shows how to wire it as a FilterManager pass.

**For Pax3D:** Add `aa_mode` parameter to `simplepbr.init()`: `'msaa'` (current), `'smaa'`, `'fxaa'`, `'none'`.

FXAA is already available in Panda3D via PRC config (`framebuffer-fxaa`), but conflicts with simplepbr's MSAA. A post-process FXAA pass in the FilterManager chain would avoid this conflict.

### 6.5 Phase 3 Deliverables

- [ ] `pax3d_brdf.inc.glsl` ported from tobspr (354 lines, Cook-Torrance + Disney diffuse)
- [ ] `pax3d_tonemapping.inc.glsl` ported (6 operators + EV100)
- [ ] `pax3d_color_spaces.inc.glsl` ported
- [ ] simplepbr fragment shader updated to use `pax3d_brdf.inc.glsl`
- [ ] SMAA post-process pass available as alternative to MSAA
- [ ] `aa_mode` parameter added to `simplepbr.init()`

---

## 7. Phase 4: Atmospheric and Environmental

**Goal:** Physically-based atmospheric scattering for planets seen from space, and volumetric height fog as a general atmospheric effect.

**Prerequisites:** Phase 3 BRDF infrastructure. Atmospheric scattering needs the tonemapping pipeline to be correct first.

### 7.1 Atmospheric Scattering

**Current state:** The game has a custom additive Fresnel atmosphere shader (`graphics/atmosphere_shader.py` or similar) that uses `setShaderOff()` to opt out of simplepbr and applies a Fresnel glow around planets. Toggle: `Alt+A`. This is visually acceptable but not physically based.

**Two options:**

#### 7.1.1 Hosek-Wilkie Analytic Sky

**Source:** tobspr — `RenderPipeline/rpplugins/scattering/scattering.frag.glsl`

Hosek-Wilkie is a fitted analytic model for sky appearance. It is NOT a full scattering simulation — it models the integrated sky color seen from the surface. For a space game where we need the appearance of an atmosphere from above/outside, this is a reasonable approximation.

**Pros:** Analytic (no precomputation), ~50 lines GLSL, produces correct limb darkening and horizon glow colors for different stellar types.

**Cons:** Designed for surface-level sky, not top-down atmosphere rendering. May need adaptation for orbital viewing angles.

**Extractability:** Medium. tobspr's implementation is tied to its sky rendering context. The core math functions can be extracted but the integration layer needs rewriting.

#### 7.1.2 Bruneton Model (Precomputed LUTs)

**Source:** tobspr — 12 compute passes building 4D transmittance/scattering LUTs

This is the Bruneton & Neyret 2008 model, a full single-scattering precomputed simulation. It produces the most physically accurate results — correct ozone absorption, Mie scattering, ground-level and space-level views are all consistent.

**Pros:** Correct limb brightening, correct sunset colors, correct color shifts with altitude.

**Cons:** 12 compute passes for precomputation (done once per planet type), complex shader code (~500 lines runtime), requires Panda3D compute shader support.

**Extractability:** Low. The precomputation pipeline is deeply integrated into tobspr's render pipeline. Standalone extraction would require rewriting the compute pass framework.

**Recommendation:** Implement Hosek-Wilkie as a Phase 4 deliverable. Bruneton as a long-term Phase 4/5 stretch goal if the analytic model proves insufficient.

**Note:** The current additive Fresnel atmosphere already does something reasonable. Do not remove it until a replacement is ready and tested.

### 7.2 Height Fog

**Source:** tobspr — `RenderPipeline/rpplugins/volumetrics/`

An analytical height fog model — ~65 lines of GLSL:

```glsl
float fog_factor = exp(-height * fog_density) * exp(-depth * fog_extinction);
vec3 fog_color = sun_color * sun_inscatter + ambient_color * ambient_inscatter;
result = mix(fog_color, scene_color, saturate(1.0 - fog_factor));
```

For a space game, height fog is mainly useful for:
- Planets with thick atmospheres (surface not visible from above some altitude)
- Gas giant "surface" (no hard surface, fade to opaque)
- Nebula volumes (uniform volumetric fog, not height-based, but same math)

**Extractability:** Very high — self-contained analytical formula. No GBuffer dependency.

**Integration:** As a post-process pass or as part of the PBR fragment shader. Parameters: `fog_density`, `fog_height_falloff`, `fog_color`, `fog_start_distance`.

### 7.3 Phase 4 Deliverables

- [ ] Hosek-Wilkie sky model extracted and adapted for orbital viewing
- [ ] Atmosphere shader replaces current additive Fresnel for close-orbit planet views
- [ ] Planet type → atmosphere scattering parameters mapping (rocky, gas giant, waterworld, airless)
- [ ] Height fog GLSL extracted and integrated as optional effect
- [ ] Nebula/gas cloud rendering uses height fog model
- [ ] `Alt+A` toggle still works, switches between new physics atmosphere and off

---

## 8. Phase 5: Large-Scale Rendering

**Goal:** Eliminate Z-fighting and precision artifacts at astronomical distances. Enable single-pass rendering without the sky camera workaround.

**Prerequisites:** Phases 1-3 complete. This is an engine-level architectural change.

### 8.1 Logarithmic Depth Buffer

**Problem:** Standard depth buffers have linear (or perspective-linear) precision distribution. For a scene spanning 1m to 1,000,000m (typical space game range), the depth buffer allocates ~50% of its precision to the first 1000m, leaving almost nothing for the rest. This causes Z-fighting (flickering) when two distant objects are close relative to the total depth range.

**Current workaround:** The sky camera system (sort -100 DR on simplepbr's offscreen buffer, OmniBoundingVolume on distant objects) effectively splits the scene into two depth ranges. This works but is fragile and complex.

**Solution:** Logarithmic depth buffer — `gl_FragDepth` is replaced with `log2(Ccoef * gl_Position.w + 1.0) * FC` where `FC = 2 / log2(far + 1)`. This distributes depth precision logarithmically, giving equal resolution at 1m and at 1,000,000m.

**Engine changes needed:**
- `glGraphicsStateGuardian_src.cxx` — detect when log depth is enabled, set the `FC` uniform
- PBR fragment shader — override `gl_FragDepth` with log depth formula
- All other fragment shaders that write depth (shadow, etc.) need the same override

**Panda3D note:** Log depth is not natively supported in Panda3D 1.10.16. It requires shader-level implementation. The main complexity is ensuring ALL shaders (including those in simplepbr and the sky) use the same log depth formula — mixing log and linear depth causes rendering artifacts where shaders interact.

**Reference implementation:** `tobspr/RenderPipeline` has log depth as an optional compile-time switch. The relevant code is in `render_pipeline_base.inc.glsl` (the fragment depth override) and the pipeline setup code.

### 8.2 Camera-Relative Rendering

**Problem:** At large distances (>10,000 IEU ≈ 20 million km), floating-point position coordinates begin to lose precision. A ship at position (100000.1, 0, 0) and a bullet at (100000.2, 0, 0) may be indistinguishable at 32-bit float precision.

**Solution:** Camera-relative rendering — translate all world-space positions by subtracting the camera position before the vertex shader sees them. The camera is always at (0,0,0) in this space. This is standard in modern game engines (Unreal, Unity large world coordinates).

**Engine changes needed:**
- Vertex shader: subtract `camera_world_position` from vertex position before model-view transform
- All position-dependent effects (depth fog, atmospheric scattering, distance-based LOD) use the relative position
- `camera_world_position` is already passed to the PBR shader as a uniform (`render.setShaderInput("camera_world_position", ...)`) — this is already in place

**Panda3D note:** Panda3D uses double-precision for scene graph transforms internally (`LPoint3d`), which helps. But shader inputs are 32-bit floats. Camera-relative rendering must happen at the shader level.

**Priority for Pax Abyssi:** The game's IEU unit system (1 IEU = 2000 km) means positions in the hundreds of thousands of IEU for outer-system objects. At `float32`, precision drops below 1 IEU at around ±16,777,216 — roughly 82,000 IEU from origin. Outer planets in large systems (e.g., Proxima-scale companions at thousands of AU) can exceed this. Low priority today, needed before supporting multi-star systems with widely separated stars.

### 8.3 Near/Far Plane Management

**Current settings:** No explicit near/far in game PRC config — Panda3D defaults to near=0.1, far=10000. The sky camera has its own lens: near=100, far=10M IEU.

**Problem:** With the default far=10000, any object beyond 10000 IEU is clipped. Outer planets, distant stars, and the milky way background all rely on the sky camera to render beyond this range.

**With log depth:** A single camera with near=0.1, far=1e9 (1 billion IEU) is feasible because log depth distributes precision well across this range. This eliminates the need for the sky camera architecture entirely.

**Dependency:** Phase 5.1 (log depth buffer) must be complete before removing the sky camera system. Do not remove the sky camera workaround until log depth is proven stable.

### 8.4 Phase 5 Deliverables

- [ ] Logarithmic depth buffer implemented in Pax3D's PBR fragment shader
- [ ] Log depth applied consistently to all shaders (sky, shadow, post-process)
- [ ] Single camera with near=0.1, far=1e9 — sky camera system can be removed
- [ ] Camera-relative rendering in vertex shader
- [ ] Near/far management simplified from 2-camera system to single configurable values
- [ ] `SWITCHING_ENGINES.md` updated with Phase 5 architecture notes

---

## 9. Dependencies Between Phases

```
Phase 1 (Directional Lighting)
    └── Required by ALL other phases (lighting must be correct before visual improvements)

Phase 2 (Bloom + HDR)
    └── Requires Phase 1 (bloom on incorrect lighting = wrong)
    └── Enables removal of per-effect RGB compensation hacks

Phase 3 (Shader Infrastructure)
    └── Requires Phase 2 (tonemapping must be correct before improving BRDF)
    └── Provides foundation for Phase 4 atmospheric shaders

Phase 4 (Atmospheric / Environmental)
    └── Requires Phase 3 (correct BRDF + tonemapping needed for atmospheric scattering)
    └── Independent of Phase 5

Phase 5 (Large-Scale Rendering)
    └── Requires Phase 3 (log depth is shader-level, needs PBR shader control)
    └── Removes sky camera workaround (sky camera was Phase 1/2 workaround)
    └── Independent of Phase 4
```

**Critical path:** Phase 1 → Phase 2 → Phase 3 → Phase 4 or Phase 5 (parallel).

---

## 10. Risk Assessment

### Phase 1 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Formula B fails at other cardinal positions | Low | High | Formula toggle (Shift+F9) still in place for rapid A/B testing |
| Winding fix breaks atmosphere shader normals | Medium | Medium | Test atmosphere rendering after mesh winding change |
| Engine `setDirection()` method not exposed in Python interrogate | Medium | Low | Use `setHpr()` wrapper in Python as fallback |
| lookAt() corruption is FilterManager-specific to simplepbr | High (known) | Medium | Document as permanent limitation, do not try to fix in engine |

### Phase 2 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Bloom passes interact with sky camera's separate DR | Medium | Medium | Test with sky camera active; may need bloom to apply per-DR |
| tobspr shaders use macros that are hard to replace | Low | Low | Extraction procedure above handles all known macros |
| ACES tonemapping changes star/planet colors noticeably | Medium | Low | A/B test with existing Reinhard; expose as configurable parameter |
| Removing RGB compensation factors makes sun/weapons too bright | High | Medium | Remove compensation factors gradually, tune per-effect |

### Phase 3 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| tobspr BRDF produces different results from simplepbr's current BRDF | Medium | Low | Visible only on metallic surfaces; adjust base colors if needed |
| SMAA requires post-process pass that conflicts with sky camera | Medium | Medium | Same issue as Phase 2 bloom; resolve at same time |

### Phase 4 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Hosek-Wilkie is not designed for orbital views | High | Medium | May need custom adaptation; keep existing Fresnel shader as fallback |
| Bruneton precomputation requires Panda3D compute shader support | High | High | Bruneton is stretch goal; Hosek-Wilkie is primary target |
| Atmosphere shader conflicts with existing setShaderOff() pattern | Medium | Medium | Test thoroughly; may need to restructure opt-out list |

### Phase 5 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Log depth requires ALL shaders to be consistent | High | High | Any shader that doesn't write log depth will cause visual artifacts |
| Removing sky camera before log depth is stable causes regression | High | High | Never remove sky camera until log depth is confirmed stable in all scenes |
| Camera-relative rendering breaks particle systems / billboard effects | Medium | Medium | All positional effects must subtract camera position; audit each system |

---

## 11. Testing Strategy

### Phase 1 Testing

**Automated test:** The existing `tools/lighttest.py` standalone test validates formula correctness mathematically. Run after any HPR formula change.

**Manual test procedure (cardinal validation):**
1. Launch `plan.py` with debug enabled (`Ctrl+L`)
2. Navigate to a planet (not position 100)
3. Cycle through all four cardinal positions with `Ctrl+Right`
4. At each position, dump to `debug_modules/lighting_debug.md` and verify:
   - `ANGLE` field shows `OK: < 5 deg` (not MISMATCH)
   - Green line on screen overlaps yellow line
5. Test with the star at different orbital positions (move to planets with different orbital coordinates, not just the debug cardinal positions)

**Regression test:** After winding fix, verify:
- Atmosphere Fresnel shader still shows correct limb glow (not inside-out)
- Moon rendering still correct (moon renderer uses same planet factory sphere)
- Distant planet sprites still visible (different code path, should be unaffected)

### Phase 2 Testing

**Bloom test scene:**
1. Engine exhaust glow from ship at night-side of planet
2. Sun corona at various distances (1000 IEU, 10000 IEU, interstellar)
3. Weapon fire in deep space (no competing light sources)
4. Compare before/after with screenshots at same scene positions

**Tonemapping test:**
- Directly facing the sun (extreme bright scene) — verify no blown-out whites
- Deep space pointing away from all stars (dark scene) — verify star visibility
- Planet in shadow vs. lit hemisphere — verify correct exposure in both

### Phase 3 Testing

**BRDF comparison:**
- Same scene rendered with old BRDF and new BRDF
- Focus on metallic ship surfaces (hull panels, engine nozzles)
- Check for energy conservation artifacts at high roughness (surfaces should not get darker at grazing angles with old non-compensated BRDF)

### Phase 4 Testing

**Atmosphere test:**
- View each major planet type (rocky, gas giant, ocean, airless) from orbit
- Verify correct limb color (blue for water, red/orange for dusty, white for cloudy, none for airless)
- Verify atmosphere fades correctly with altitude
- Verify `Alt+A` toggle works

### Phase 5 Testing

**Log depth test:**
- Fly from planetary surface altitude (~50 IEU) to deep space transit (~100000 IEU) in one continuous fly-out
- Verify no Z-fighting artifacts at any point
- Verify stars remain visible at all altitudes
- Compare with screenshot at same positions using old camera system

---

## 12. The Directional Lighting Fix in Detail

This section documents the complete current state of the directional lighting system, for any developer picking up Phase 1.

### 12.1 How the System Works

The game's sun illuminates the scene via a `DirectionalLight` node attached to `render`. Every frame, `sun_position_manager.py:update_from_orbit()` computes where the sun is relative to the player's current position and calls `app.lighting.sun_light_np.setHpr(heading, pitch, 0)`.

The HPR maps the light node's +Y axis (forward vector) to a world-space direction. simplepbr's PBR shader reads the light's direction and illuminates surfaces accordingly.

### 12.2 The Four Formulas That Were Tested

| Formula | Code | Forward Result | Works? |
|---------|------|----------------|--------|
| A (original) | `atan2(sun_dir.x, sun_dir.y)` | `(-sun_dir.x, sun_dir.y, sun_dir.z)` | Partially — only when sun_dir.x ≈ 0 |
| B (current, empirical) | `atan2(-sun_dir.x, sun_dir.y)` | `(sun_dir.x, sun_dir.y, sun_dir.z) = sun_dir` | YES (confirmed at EAST) |
| C (algebraic derivation) | `atan2(sun_dir.x, -sun_dir.y)`, pitch negated | `-sun_dir` | Works in isolated test, WRONG in game |
| D (lookAt) | `lookAt(-sun_dir)` | `-sun_dir` (same as C) | Wrong in game, CORRUPTS transform |

**The contradiction:** Formula C is algebraically correct for a standard simplepbr scene where `lit = -forward`. An isolated test with a clean UV sphere confirms this. But the game's planet mesh produces `lit = +forward`, making Formula B the empirical winner.

**Probable explanation:** The game's `_create_procedural_sphere()` uses a different triangle winding order from the test's `make_uv_sphere()`. simplepbr's fragment shader uses `gl_FrontFacing` to flip surface normals on back-facing triangles. An inverted winding sphere is rendered "inside-out" from the GPU's perspective — every fragment is back-facing, so the normals are flipped, effectively inverting the lighting direction.

**Why `lookAt(-sun_dir)` also fails:** `lookAt()` sets both position AND rotation on the NodePath. Under simplepbr, `base.cam` is moved to an offscreen buffer by FilterManager. Setting a position on a light attached to `render` corrupts the transform matrix in this configuration. The position component interferes with how Panda3D computes the light direction in eye space before passing it to the shader.

**Why `setPos()` also fails:** Same reason as lookAt() — sets position on a node that should be purely orientational, corrupting the matrix under simplepbr's offscreen buffer architecture.

### 12.3 The Confirmed Working Code

This is the correct implementation, live in `modules/sun_position_manager.py`:

```python
sun_dir = Vec3(new_sun_pos)   # planet-to-sun vector (not negated)
length = sun_dir.length()
if length > 0:
    sun_dir /= length
    heading = math.degrees(math.atan2(-sun_dir.x, sun_dir.y))
    horiz_len = math.sqrt(sun_dir.x ** 2 + sun_dir.y ** 2)
    pitch = math.degrees(math.atan2(sun_dir.z, horiz_len))
    app.lighting.sun_light_np.setHpr(heading, pitch, 0)
    app.lighting.set_sun_direction(sun_dir)   # stores as planet-to-sun
```

**Critical invariants:**
- `sun_dir` is `planet → sun`, NOT negated. The formula negates only the x component in `atan2(-sun_dir.x, ...)`.
- `set_sun_direction()` stores the `planet → sun` vector (not the `sun → planet` light travel direction).
- Never call `setPos()` on `sun_light_np`. Never call `lookAt()` on `sun_light_np`.
- `sun_light_np` must be parented to `render`, never to camera or another node.

### 12.4 Debug Tools Available

| Tool | Activation | Purpose |
|------|-----------|---------|
| Lighting OSD | `Ctrl+L` | Live overlay: formula, sun_dir, HPR, forward, angle check |
| Cardinal cycler | `Ctrl+Right/Left` (requires Ctrl+L active) | Snap ship to N/S/E/W at 180 IEU for systematic testing |
| Formula toggle | `Shift+F9` | Cycle A/B/C/D formulas live |
| 3D direction lines | (with Ctrl+L) | YELLOW=toward sun, GREEN=light forward, RED=-forward |
| Debug dump | Auto-written | `debug_modules/lighting_debug.md` every ~2 seconds while Ctrl+L active |
| Isolated test | `python tools/lighttest.py` | Standalone simplepbr test, clean UV sphere, HPR presets |

### 12.5 What the Pax3D Engine Change Should Do

The ideal engine-side fix eliminates all of the above complexity for future developers. The ideal API:

```python
# Pax3D target API — direction FROM sun TO scene (light travel direction)
sun_to_scene = Vec3(-orbital_x, -orbital_y, -orbital_z).normalized()
app.lighting.sun_light_np.node().setDirection(sun_to_scene)
```

Where `setDirection(vec)` internally computes the correct HPR (accounting for the mesh winding convention and simplepbr's `gl_FrontFacing` behaviour) so the caller never has to think about it.

The second-best option is fixing the planet mesh winding so that Formula C (the algebraically correct derivation) and `lookAt()` work as expected. This requires no engine changes but does require careful validation that the fix does not break the atmosphere shader, moon renderer, or any other system that uses the planet mesh.

---

## 13. File Reference

### Game Files (C:\python\sfb2)

| File | Relevance |
|------|-----------|
| `modules/sun_position_manager.py` | HPR formula (Formula B), debug OSD integration, formula toggle |
| `modules/planetary_debug_tools.py` | Ctrl+L overlay, cardinal cycling, 3D direction lines |
| `modules/planetary_lighting.py` | DirectionalLight + AmbientLight creation, intensity controls |
| `modules/plan_initialization_manager.py` | `simplepbr.init()` call, PRC config |
| `modules/planet_factory.py` | `_create_procedural_sphere()` — the winding-order suspect |
| `graphics/draw_distant_sun.py` | Sun glow, 0.45x PBR compensation |
| `graphics/shuttle_weapon_effects.py` | Weapon bolt, 0.25x PBR compensation, 1.8x corona scale |
| `graphics/sky_camera.py` | Sky camera architecture (workaround for near/far limits) |
| `documents/3D_SPACEFLIGHT_MODULE/SCENE_LIGHTING.md` | Lighting architecture doc (rewritten session 417) |
| `documents/3D_SPACEFLIGHT_MODULE/SIMPLEPBR_RENDERING.md` | PBR compensation pattern, node opt-out list |
| `debug_modules/directional_light_test.md` | 8-case formula test results table |
| `debug_modules/lighting_debug.md` | Last live dump from debug OSD |
| `debug_modules/lt_h*.png` | Screenshots from isolated simplepbr test |
| `tools/lighttest.py` | Standalone simplepbr DirectionalLight test |

### Engine Files (C:\python\pax3d)

| File | Relevance |
|------|-----------|
| `panda/src/pgraphnodes/directionalLight.h/.cxx` | DirectionalLight node — add `setDirection()` here |
| `panda/src/pgraphnodes/shaderGenerator.cxx` | Auto-shader generation from render state |
| `panda/src/pgraph/lightAttrib.h` | Active lights in render state |
| `panda/src/gobj/material.h` | Material system (classic + metalness PBR) |
| `panda/src/glstuff/glGraphicsStateGuardian_src.cxx` | OpenGL GSG — `bind_light(DirectionalLight*, ...)` at line ~9654 |
| `panda/src/glstuff/glShaderContext_src.cxx` | Shader compilation |
| `docs/SWITCHING_ENGINES.md` | Environment setup (venv, stock Panda3D vs Pax3D) |

### tobspr Source (Reference Only)

These are not in the repository but are referenced above. All are in `tobspr/RenderPipeline` on GitHub.

| File | Phase | Lines | Notes |
|------|-------|-------|-------|
| `rpcore/render_pipeline/rpcore/pluginbase/brdf.inc.glsl` | 3 | 354 | Cook-Torrance + Disney diffuse |
| `rpcore/stages/apply_colors/tonemapping.inc.glsl` | 2,3 | ~150 | 6 operators + EV100 |
| `rpcore/stages/apply_colors/color_spaces.inc.glsl` | 3 | ~100 | RGB/XYZ/HSL conversions |
| `rpplugins/bloom/*.frag.glsl` (5 files) | 2 | ~270 | Kawase dual-filter bloom |
| `rpplugins/scattering/hosek_wilkie.inc.glsl` | 4 | ~200 | Analytic sky model |
| `rpplugins/volumetrics/volumetrics.frag.glsl` | 4 | ~65 | Height fog formula |
| `rpcore/stages/gbuffer/depth_log.inc.glsl` | 5 | ~20 | Logarithmic depth buffer |

---

## 14. Session History

| Session | Date | Work Done |
|---------|------|-----------|
| 416 | 2026-02-26 | Lighting debug tool (Ctrl+L), cardinal cycling, identified X-flip theory (false), formula A→B |
| 417 | 2026-02-26 | Proved X-flip theory false, isolated test, confirmed Formula B empirically, Shift+F9 toggle, rewrote SCENE_LIGHTING.md |
| Future | — | Phase 1: validate Formula B at all cardinals, clean up debug code, confirm winding root cause |
