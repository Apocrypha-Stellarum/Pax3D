# Pax3D Master Plan v2 — The Rendering Program, Rebooted

**Project:** Pax3D (Panda3D 1.11.0-dev fork) + Pax Abyssi (`C:\python\sfb2`)
**Date:** 2026-07-16
**Supersedes:** `RENDERING_ROADMAP.md` (2026-02-26), `LIGHTING_CHANGE_PLAN.md` (Session 459)
**Status of predecessors:** kept as reference; their analysis is still valid, their sequencing is not.

---

## 1. Why the Previous Plan Didn't Deliver

An honest audit (July 2026) of both repos shows the March effort stalled, and *why* it stalled
is the most important input to this plan.

### 1.1 What the state actually is

| Claim in old docs | Reality (verified 2026-07-16) |
|---|---|
| "Phase 2 (Bloom + HDR) implemented" | Bloom code exists in `sfb2/graphics/pax_pbr/pipeline.py` but is **disabled** (`enable_bloom: false`). When enabled it produced blocky artifacts and no useful glow. |
| "ACES tonemapping" | Reverted. `tonemap_operator: "hejl_dawson"` — the *stock simplepbr curve we started with*. ACES/Reinhard/Uncharted2 all looked wrong (suspected double-gamma, never diagnosed). |
| "Game uses pax3d_simplepbr" | The game **never adopted it**. It uses its own fork-of-a-fork, `sfb2/graphics/pax_pbr/`, with the bloom code copy-pasted in. `pax3d_simplepbr/` sits unused in the engine repo. |
| "Phase 1 (directional lighting) resolved" | The *formula* was resolved. But the scene has **no DirectionalLight at all** — the sun is driven by custom `u_sun_dir_world`/`u_sun_color` uniforms in a custom shader. Ships get no directional light and no sun specular. Shadows are off. |
| "Pax3D engine fork" | **Zero engine C++ changes exist.** The only committed change is a build-system fix. |

Rendering work stopped at Session 459 (2026-03-03). Sessions 460–595 were all gameplay systems.
The DirectionalLight restoration that Session 459's handover called "next session" never happened.

### 1.2 Root-cause register

Every observed failure from the March effort, its actual cause, and where this plan fixes it:

| # | Observed failure | Root cause | Fixed in |
|---|---|---|---|
| F1 | Ships look flat; bloom "does nothing useful" | No DirectionalLight → no specular highlights → nothing bright for bloom to amplify. Post-processing was built on an unlit scene. | Phase R2 |
| F2 | ACES/Reinhard/Uncharted2 washed out | ~~Suspected double-gamma~~ **DISPROVEN by paxtest (Session A):** the post chain matches the analytic curves exactly. Real cause: **inputs are not linearized** — sRGB textures sampled raw, content hand-tuned against Hejl-Dawson. R1 = flag textures sRGB + retune intensities. | Phase R1 |
| F3 | Bloom produces blocky artifacts | **FIXED (Session D).** Root cause: bloom intermediates were 8-bit FBOs (`render_quad_into` without fbprops; the bind silently rewrites the declared RGBA16F texture format) → dim halo tail quantized into bands. Secondary: downsample kernel typo (vertical asymmetry), upsample tented the wrong input. Guarded by `test_bloom` incl. `bloom_buffers_float`. | Phase R3 — done |
| F4 | Toggling bloom kills the skybox permanently | `_rebuild_tonemapping()` destroys the FilterManager; the sky camera found its display region by *searching* for it once at init and can't recover. Architectural: the pipeline doesn't own its auxiliary cameras. | Phase R1 |
| F5 | Tuning was guesswork; regressions couldn't be attributed | Many variables changed at once (bloom + tonemap + compensation removal in one session), tested only by launching the full game and eyeballing. | Phase R0 |
| F6 | Planet spheres forced the custom-uniform workaround | `V3n3t2` format — no tangents → NaN TBN in the stock shader. Worked around instead of fixed. | Phase R2 |
| F7 | Two divergent renderer forks | `pax3d_simplepbr` (engine repo) and `graphics/pax_pbr` (game repo) implement the same pipeline differently. Fixes land in one and not the other; neither is authoritative. | Phase R1 |
| F8 | Winding-dependent lighting (Formula B vs C) | Planet sphere winding is non-standard; GLTF assets follow spec CCW. Two conventions in one scene. | Phase R2 |

> **Session A update (2026-07-16):** Phase R0 is complete — `tools/paxtest/`
> exists and its first run revised this register: F2's double-gamma
> hypothesis is disproven (real cause: input linearization), F3 is reproduced
> in isolation, F8 is confirmed, and a real DirectionalLight is proven to
> work on all current mesh types (de-risking R2). Full analysis in
> `PAXTEST_FINDINGS_SESSION_A.md`.
>
> **Session B update (2026-07-16):** R1 core landed — `pax3d_render/` is the
> unified pipeline (merge of the game's pax_pbr + pax3d_simplepbr), verified
> behavior-identical to pax_pbr by the harness (gamma/lighting match; bloom
> shows the same known F3 defect), on both engines and both GL baselines.
> New `register_scene_camera()` API fixes F4: paxtest `rebuild` shows the
> old sky-camera pattern dying on bloom toggle in both legacy pipelines
> while pax3d_render survives. Game side: opt-in
> `planetary_shuttle_rendering.use_pax3d_render` flag (default false) routes
> `graphics.pax_pbr` to the new package; sky_camera.py auto-uses the
> registration API when available. Remaining R1: flip the flag in-game and
> eyeball parity; sRGB texture linearization experiment
> (`make_base_color_textures_srgb()` helper is ready); drop the GLSL 120
> dual-path once the game sets gl-version 3 2.
>
> **Session C update (2026-07-16):** R2 core landed — pax3d_render gains
> `sun_light_mode='directional'`: a pipeline-owned real DirectionalLight
> processed by the standard p3d_LightSource loop (SUN_FROM_LIGHTSOURCE
> define), oriented via HPR so lighting and the shadow camera always agree.
> `update_sun()` keeps its signature in both modes; paxtest lighting is
> green in directional mode with measurements identical to uniforms mode,
> and external DirectionalLights are now CONSUMED. **Sun shadows work**:
> new `test_shadows.py` proves occlusion (0.79 lit → 0.09 shadowed),
> runtime toggles via `set_sun_light_mode()` / `set_enable_shadows()` /
> `set_shadow_extent()`. Fixed a real bug the harness caught: runtime
> `_recompile_pbr()` wiped all shader inputs (now preserves the attrib).
> Testbed: `--sun-mode/--shadows` flags, N/X hotkeys. Remaining R2:
> game-side switch to directional mode + shadow-extent driving from planet
> data (R2.4 at scale), planet tangents (only needed for normal maps),
> engine C++ conveniences (set_direction_world — optional now that the
> pipeline owns orientation).

> **Session D update (2026-07-17):** R3.1 done — **F3 (blocky bloom) is
> root-caused and fixed**; `test_bloom` is green at both resolutions, both
> engines, both GL baselines. The real cause was none of the three
> suspects: the bloom intermediates were **8-bit framebuffers**.
> `render_quad_into()` without `fbprops` creates a default 8-bit FBO and
> the texture bind silently rewrites the declared RGBA16F format to match,
> so the extract's `*0.005` scale crushed the halo tail into a handful of
> 8-bit codes — the tonemap then amplified each 1-code step into a visible
> band (texel-aligned plateaus that mimic nearest-neighbor sampling; this
> misdirected the investigation toward filter state). Fix: explicit float
> fbprops on every bloom `render_quad_into` (pipeline.py), plus two real
> but secondary defects found on the way: the 13-tap downsample kernel
> used `b`/`c` where the center sample `a` belongs (over-weighted the -y
> taps — this was the vertical halo asymmetry), and the 9-tap upsample
> tent was applied to the same-res source while the coarser accumulator
> got one bilinear tap (Jimenez tents the coarser mip). Also explicit
> bilinear+clamp on all bloom textures (was default repeat → edge bleed).
> New paxtest check `bloom_buffers_float` guards the root cause. Legacy
> pax_pbr/pax3d_simplepbr still fail test_bloom by design (frozen A/B
> copies). Remaining R3: content retune (R3.2/R3.3 — strength/intensity/
> tints; note the per-mip tint list reads inverted vs its comment labels),
> auto-exposure stretch (R3.4), and the game-side bloom-on decision after
> the R1/R2 flag flips.
>
> Session D also closed the R2.4 mechanism: `set_shadow_extent` gained a
> world-space `center` (light-node positioning, lighting-neutral — three
> new paxtest checks in test_shadows prove outside-extent-is-lit,
> recenter-shadows, and lighting-unchanged), and the game now recenters
> the shadow frustum on the camera every sun update
> (`sun_position_manager.py`) with a new
> `planetary_shuttle_rendering.sun_light_mode` settings key passed through
> `plan_initialization_manager.py`. What's left of R1/R2 needs the user:
> flip `use_pax3d_render` → parity eyeball → flip `sun_light_mode` to
> 'directional' → validate shadows in-game.

> **Session D addendum (2026-07-17, cont.):** Flags FLIPPED on user order
> (`use_pax3d_render`, `sun_light_mode=directional`, `enable_shadows`) —
> game smoke-boots clean on pax3d_render, zero shader errors; visual
> parity eyeball still pending. **R4.0 done:** `test_scale.py` reproduces
> both scale defects deterministically (Z-fight sweep at 2500 IEU;
> off-origin precision loss — which requires a ROTATED camera to
> manifest; axis-aligned rigs cancel exactly). **R4.1 core done:**
> opt-in `enable_log_depth` in pax3d_render — fragment-level log depth,
> `scale/pax3d_render @logdepth` GREEN under both GLSL baselines and both
> engines; testbed Z hotkey / `--log-depth`; planet approach clean through
> a 0.1/1e9 frustum. Sweep-based z-fight probing was required: single
> frames can tie-break uniformly and mimic correct rendering. Parallel
> sessions the same day: FTL warp distortion in the tonemap pass (with
> test_ftl_blur, green) and the game repo's doubles-build spike (candidate
> for the R4.2 precision half).

> **Session E update (2026-07-17):** R2 shadow hardening, driven by the
> openworld build's engine feedback (`PAX3D_FEEDBACK.md` in that repo;
> our reply: `OPENWORLD_FEEDBACK_RESPONSE.md`). Their P0 — "skinned
> meshes cast no shadows" — was **root-caused as NOT an engine bug**:
> (1) the visible symptom was the shadow-bias trap (normalized bias ×
> extent depth: the 0.005 default = 3.0 m at their 600-deep frustum ≈ a
> standing character's entire light-ray depth gap at a 30° sun, so
> characters lost shadows while buildings kept them — reconstructed
> exactly in their live build, 0.450→0.450 vs 0.450→0.378); (2) their
> 0-texel depth-map evidence was contaminated by their own proxy-prism
> workaround occupying the same light-space column (proven in their
> build: 0 texels with proxy, 60 without). The skinned depth path is
> proven green nine ways in paxtest (egg + their glb via Actor, hw+sw
> skinning, GLSL 120+330, bam-cache, blend, masks, angled sun, posed
> joints 0.321→0.037) — new permanent coverage in test_shadows incl. a
> `@softskin` matrix row and a depth-map texel-diff instrument.
> **Landed in pax3d_render (opt-in, defaults byte-identical):**
> `shadow_bias_world` / `set_shadow_bias(v, world_units=True)` (rescales
> with extent depth — kills the trap class), `shadow_filter_size=3`
> (3×3 multi-tap PCF, edge 6→16 px, interior unchanged),
> `shadow_caster_mask` + `exclude_from_shadows()`/`include_in_shadows()`
> (blessed no-cast API), openworld's shadow debug modes 10/11 committed.
> New `test_shadow_quality.py`: angled-sun-at-predicted-position,
> bias-trap measured record, PCF, no-cast — 9/9 both engines, both GL
> baselines. **Space-game exposure:** sfb2 runs extent 500/4000 with the
> default bias ⇒ ~20 IEU effective offset — ship-on-station/ship
> shadows are likely being erased in-game today; when validating R2,
> set a world-unit bias (start ~0.5 IEU). Backlog added: engine-side
> texel snapping in `set_shadow_extent` (openworld's game-side snap is
> the reference impl), slope-scaled bias, runtime fog toggle,
> intermittent `shaderAttrib.cxx:471` assert (needs repro), CSM +
> clustered lights (post-R5).

### 1.3 The lesson

The March plan ordered work by *visual payoff* (bloom first, because it's exciting). The correct
order is by *dependency*: *test harness → color correctness → lighting → post-processing → scale →
atmosphere*. Bloom amplifies whatever the lighting produces; when the lighting produces nothing,
bloom amplifies nothing — this was learned empirically at the cost of a month.

---

## 2. Strategy

### 2.1 Five principles

1. **Fix the light before the glow.** No post-processing work until a real DirectionalLight
   produces correct diffuse + specular on every mesh type in the scene.

2. **One renderer, owned by the engine repo.** Merge `graphics/pax_pbr` (game) and
   `pax3d_simplepbr` (engine) into a single first-party package in the Pax3D repo. The game
   becomes a consumer with a thin adapter. Every rendering fix lands in exactly one place.

3. **Verify in a harness, not by launching the game.** A standalone test kit in the engine repo
   renders known scenes offscreen and checks the output programmatically. Gamma correctness is
   checked with a ramp image, not by opinion. Lighting direction is checked by sampling pixels
   on a sphere, not by squinting. This is the single highest-leverage item in the whole plan.

4. **GLSL 330 core, minimum.** Set `gl-version 3 2` and delete the GLSL 120 dual-path. The
   hardware target is OpenGL 4.x-class GPUs; carrying 2008-era shader syntax doubles every
   shader's surface area for bugs (and is entangled with the sRGB confusion).

5. **Prototype in Python/GLSL; promote to C++ on evidence.** *(v2, user-ratified 2026-07-17 —
   supersedes "C++ only where Python can't reach", whose upstream-sync rationale died with the
   severed-upstream policy.)* The near-instant Python/GLSL loop — edit → paxtest → seconds →
   downstream AI dev feedback same-day — is the program's superpower and the default for ALL
   new work, even features whose eventual home is C++. C++ is used when the class of work
   demands it: per-frame × per-object/per-vertex machinery that can't live on the GPU, and
   stable, proven Python that a profile shows in the hot path. Never port on faith; C++
   batches into user-scheduled build windows. Full canon + the living build-window queue:
   CLAUDE.md "Language Canon".

### 2.2 Graphics API decision (the "modern DirectX" question)

Recommendation: **OpenGL 4.x core profile now; hand-ported Vulkan later, if ever; no DirectX.**
*(Updated 2026-07-17 for the severed-upstream policy — "sync it in" is no longer a mechanism;
anything we take from upstream is a deliberate hand cherry-pick from the read-only reference.)*

- Panda3D's only DirectX backend is **DirectX 9** (`dxgsg9/`) — a 2004-era API already scheduled
  for removal in our own roadmap. There is nothing modern to build on there.
- Writing a D3D12 backend from scratch is a multi-man-year project and Windows-only. It delivers
  nothing the game needs that GL 4.x doesn't.
- OpenGL 4.6 *is* a modern API on Windows: compute shaders, HDR framebuffers, everything in
  Phases R1–R5 runs on it. It is what tobspr's RenderPipeline (our shader donor) targets.
- Upstream Panda3D has an experimental **Vulkan** backend in a development branch. If it ever
  matures, porting it BY HAND into our tree (a scheduled-build-window project, evaluated only
  when it can run the paxtest suite) is the realistic next-gen path — and everything in this
  plan (GLSL 330+, no fixed-function, engine-owned pipeline) moves *toward* such a port,
  not away from it.

If "modern DirectX framework" meant "modern rendering feature set" (PBR, HDR, bloom,
physically-based atmospherics), that is exactly what Phases R1–R5 deliver, on GL.

---

## 3. The Program

Six phases. Each has a hard acceptance gate; no phase starts until the previous gate passes.
R0 is deliberately small — do it first, in one or two sessions.

```
R0 Harness ──> R1 Unified renderer + color correctness ──> R2 Real lighting ──> R3 HDR/bloom
                                                                     │
                                                                     ├──> R4 Space-scale rendering
                                                                     └──> R5 Atmosphere & signature look
R6 Engine hygiene (DX9 removal, dead-path deletion) — parallel, low priority
```

---

### Phase R0 — Test Harness & Ground Truth (small; 1–2 sessions)

**Goal:** Never again tune a renderer by restarting the game and guessing.

Build `tools/paxtest/` in the Pax3D repo — standalone Panda3D scripts that run in seconds
against whichever engine is in the active venv:

| Test | Scene | Programmatic check |
|---|---|---|
| `test_gamma.py` | Fullscreen quad of known linear values (0.0–1.0 ramp) through the full pipeline | Read back pixels; assert output matches sRGB curve within tolerance. **Detects double-gamma (F2) mechanically.** |
| `test_lighting.py` | UV sphere (standard winding), UV sphere (game winding), GLTF ship, all with one DirectionalLight at each cardinal | Sample lit/unlit hemisphere pixels; assert lit side faces the light. Resolves Formula B/C per mesh type once and for all (F8). |
| `test_bloom.py` | Black scene + single small emissive quad | Render with bloom; assert radially smooth falloff (no blockiness), assert energy roughly conserved. **Reproduces F3 in isolation.** |
| `test_rebuild.py` | Pipeline + registered auxiliary camera; toggle bloom/levels at runtime | Assert auxiliary camera still renders after rebuild (F4). |
| `test_scale.py` | **Implemented (Session D addendum).** Tilted near-coplanar cards at 2500 IEU (game frustum 0.1/5000) + identical rotated-camera scene at origin vs 1.2e6/1.2e7 IEU | R4 acceptance: zfight_at_range FAILS today (green bleed 0.54); precision_off_origin FAILS today (diff 0.0024 @1e6, 0.22 @1e7). Controls (near-field depth, origin determinism) green. NOTE: the precision defect needs a ROTATED camera — axis-aligned rigs cancel exactly. |

Plus: `paxtest run --golden` captures reference screenshots; `paxtest run --check` diffs against
them. Keep it crude — image RMS diff is enough.

**Also in R0:** establish the PRC baseline the whole program assumes:
`gl-version 3 2`, `textures-power-2 none`, explicit framebuffer bits. Document it in one place.

**Gate:** the harness runs green on stock behaviour, and `test_gamma.py` + `test_bloom.py`
demonstrably *fail* against the current pipeline (proving they can catch F2/F3).

---

### Phase R1 — One Renderer, Correct Color (medium; 3–5 sessions)

**Goal:** A single engine-owned render package with a verified linear-light pipeline.

**R1.1 — Merge the forks (F7).**
Create `pax3d_render/` in the Pax3D repo (evolving `pax3d_simplepbr/`, absorbing the good parts
of the game's `graphics/pax_pbr`: sun debug modes, dithering, runtime tuning hooks). The game's
`graphics/pax_pbr/` becomes a thin adapter (`from pax3d_render import ...`) and its 600-line
pipeline.py is deleted. `pax3d_simplepbr/` is retired.

**R1.2 — Pipeline owns its cameras (F4).**
First-class API for auxiliary display regions:

```python
pipeline = pax3d_render.init(...)
pipeline.register_scene_camera(sky_cam, sort=-100, clear_color=True)   # sky camera
```

The pipeline creates the DR on its internal buffer and **re-creates it on every rebuild**.
`sky_camera.py`'s `_find_render_target()` spelunking is deleted. Toggling bloom, changing
levels, resizing — nothing can orphan the skybox again.

**R1.3 — Explicit color-space contract (F2).**
One contract, enforced by `test_gamma.py`:

- Scene renders in **linear** light into RGBA16F (`srgb_color=False` — already true).
- All albedo/emissive textures flagged sRGB on load (hardware decode → linear in shader).
- Linear → sRGB conversion happens **exactly once**, in the final present pass —
  and pick one mechanism: in-shader `pow(1/2.2)` **or** sRGB-enabled window framebuffer, never both.
- With this verified, ACES/Reinhard/Uncharted2 become usable; Hejl-Dawson survives only as a
  legacy toggle (its baked-in gamma violates the contract).

**R1.4 — GLSL 330 core only.**
Delete the 120/330 dual-path from every shader. `gl-version 3 2` becomes required
(set by `pax3d_render.init()` if not already configured).

**Gate:** game renders via `pax3d_render` visually identical to today (bloom off, Hejl-Dawson);
`test_gamma.py` passes with ACES; `test_rebuild.py` passes.

---

### Phase R2 — Real Directional Lighting (medium; 3–5 sessions) ★ the payoff phase

**Goal:** A real `DirectionalLight` lights every mesh in the scene — diffuse, specular, shadows.
This is the fix for "ships look flat" and the prerequisite for bloom being worth anything.

**R2.1 — Restore the DirectionalLight node (F1).**
`planetary_lighting.py` creates a real `DirectionalLight` again. The PBR shader's sun block
reads `p3d_LightSource[0]` (the `w == 0` branch it currently *skips*) instead of
`u_sun_dir_world`. Panda3D handles the direction transform; `sun_position_manager.py` shrinks
to one canonical call. Keep `u_sun_color`-style intensity control as a multiplier if useful.

*Why read the light node rather than keep uniforms:* shadows, the shader generator, `p3d_LightSource`
consumers (GLTF viewer paths, future point lights) and any engine-level lighting work all key off
the node. The uniforms were a detour; going back now costs one shader block.

**R2.2 — Fix the geometry, not the formula (F6, F8).**
- `planet_factory.py`: emit **standard CCW winding** and **analytic tangents** (trivial for a UV
  sphere: `tangent = normalize(∂P/∂u)`). This makes planets follow the same convention as every
  GLTF asset, makes Formula C / `lookAt()` semantics correct, and un-blocks normal-mapped planets.
- Keep the shader's tangentless fallback as a safety net for any other procedural geometry.
- `test_lighting.py` proves both sphere variants and the GLTF ship agree before the game is touched.

**R2.3 — Engine C++ (the fork's first real changes).**
Small, surgical, `// PAX3D:`-tagged — from `DIRECTIONAL_LIGHTING_PLAN.md`:
- `DirectionalLight::set_direction_world(const LVector3&)` — takes the photon-travel direction,
  no atan2 in game code ever again.
- Strip translation in `DirectionalLight::xform()` so `setPos()`/`lookAt()` cannot corrupt it.
- Debug warning when a DirectionalLight has a non-zero position.

**R2.4 — Shadows at planet scale.** **Mechanism DONE (Session D).**
`set_shadow_extent(radius, depth, center)` now takes a world-space center
(implemented by positioning the light node — lighting-neutral, proven by
paxtest `recenter_keeps_lighting`), and the game recenters the frustum on
the CAMERA every sun update (`sun_position_manager`, settings keys
`shadow_extent_radius`/`shadow_extent_depth`, defaults 500/4000) — shadow
resolution follows the player instead of planet-sized extents. Remaining:
in-game validation of terminator + ship self-shadowing at the four
cardinals once the user flips directional mode. **Session E addendum:**
that validation MUST set a world-unit bias first — at 500/4000 the
default normalized bias is ~20 IEU of depth offset, which erases most
ship-scale shadows (`set_shadow_bias(0.5, world_units=True)` or
`shadow_bias_world` in settings; see the bias trap, architecture doc
§5.1). Shadow quality knobs now available for the eyeball pass:
`shadow_filter_size=3` (3×3 PCF), `exclude_from_shadows()` for FX/sky
geometry.

**Gate:** in-game — ships show sun specular that moves correctly as the camera orbits; lit
hemispheres correct at all four cardinals (debug overlay reads OK); shadows toggle cleanly;
`test_lighting.py` green for all mesh types.

---

### Phase R3 — HDR & Bloom, Second Attempt (medium; 2–4 sessions)

**Goal:** The March feature set, working, on top of a scene that now has real light.

**R3.1 — Diagnose blockiness in the harness (F3).** **DONE (Session D,
2026-07-17).** Root cause was 8-bit intermediate FBOs, not any of the listed
suspects — see the Session D update in §1.2 and the F3 register row.
`test_bloom` green at 512×512 and 960×540, both engines, both GL baselines;
new `bloom_buffers_float` check prevents regression.

**R3.2 — Physical-ish light units.**
Sun intensity, emissives, and exposure defined in consistent relative units with exposure in EV
stops (already there) — so "close solar approach" vs "deep space" is an exposure change, not a
per-effect retune.

**R3.3 — Kill the magic numbers, one at a time.**
The 0.45×/0.7×/0.25×/0.35× compensation factors go, *one per test run*, tuning
`bloom_strength`/exposure after each — the discipline that F5 says March lacked. Now that
additive glows sit in a verified-linear HDR buffer with working bloom, they should finally be
removable for real.

**R3.4 — Stretch: auto-exposure.**
Average-luminance readback from the existing downsample chain (it's already a luminance
pyramid) driving EV with smooth adaptation. Deep space and solar approach stop needing manual
exposure presets. Cheap to try once R3.1 works.

**Gate:** bloom on by default in the game; no blocky artifacts; sun/engines/weapons glow
naturally with zero per-effect compensation factors; `test_bloom.py` golden green; toggling
bloom at runtime is safe (R1.2 already guarantees it).

---

### Phase R4 — Space-Scale Rendering (high effort; engine-heavy)

**Goal:** One camera, near 0.1 to far 10⁹, no Z-fighting, no sky-camera architecture.

**R4.0 — Acceptance tests (DONE, Session D addendum 2026-07-17).**
`test_scale.py` reproduces both defects mechanically against the current
stack (identical under stock and Pax3D engines, 'none' and pax3d_render —
engine-level, pipeline-independent):
- `zfight_at_range`: 1.0 IEU separation at 2500 IEU under the game frustum
  (0.1/5000, 24-bit depth) cannot be resolved — the rear surface bleeds
  through in bands (green fraction 0.54; theoretical depth resolution at
  that range ≈ 1.9 IEU). Near-field control (50 IEU) resolves cleanly and
  must stay green after log depth lands.
- `precision_off_origin`: the same rotated-camera scene at the origin vs
  1.2e6 / 1.2e7 IEU differs by 0.24% / 22% of pixels (float32 view-matrix
  composition). **Finding:** the defect requires camera ROTATION — with an
  identity-rotation axis-aligned rig the large translations cancel exactly
  and everything looks fine; this is why the game degrades when orbiting
  at range, not when flying straight out.
These rows are EXPECTED FAILs in the matrix until R4 lands — they are the
definition of done for log depth (zfight) and camera-relative rendering
(precision).

- **Logarithmic depth** — **CORE LANDED, opt-in (Session D addendum).**
  `enable_log_depth` in pax3d_render: fragment-level log depth in the PBR
  shader, coefficient tracks the lens far every frame. Acceptance row
  `scale/pax3d_render @logdepth` is GREEN: two surfaces 1 IEU apart at
  2500 IEU order correctly at every step of a sub-resolution sweep under a
  0.1/1e9 frustum (linear buffer: 89% bleed-through at the worst step).
  Verified GLSL 120+330, both engines; testbed `--log-depth` / Z hotkey;
  planet approach renders clean through the wide frustum. Deliberately NOT
  applied to the ortho shadow pass (linear depth is already uniform
  there). Remaining: sky-object shaders adopt the formula when the sky
  camera retires; game flips the frustum + flag after fly-out testing.
- **Camera-relative rendering — THE CHOSEN R4.2 PATH (decision
  2026-07-17).** The doubles engine build (STDFLOAT_DOUBLE spike, game
  repo) is SHELVED for now — the compile cost can't be afforded on this
  machine today; revisit at the next break (its handover doc preserves
  the full procedure, and it would complement rather than replace this).
  Camera-relative = anchor-relative placement in the GAME's positioning
  layer: sim state stays in Python doubles; every node position is
  `sim_pos - anchor` computed in doubles BEFORE set_pos, anchor follows
  the player. **The contract is machine-proven in test_scale:** the
  parent-cancel shortcut (huge coords in node transforms + parent at
  -anchor) fails — local positions quantize (~1 IEU at 1.2e7) before
  composition (`trap_parent_cancel_quantizes`: 8.5% pixel displacement
  for a ship 1.5 IEU from anchor). Acceptance:
  `test_scale precision_off_origin` stays the engine-baseline record;
  the game-side criterion is a jitter-free orbit + fly-out at system
  scale. Integrate WITH the nested-space architecture (deep-space mode
  already locks the ship at origin — R4.2 generalizes that pattern;
  coordinate with the game-space dev's NESTED_SPACE_ARCHITECTURE.md).
- **Retire the sky camera** only after `test_scale.py` and a full fly-out test pass with log
  depth stable. The old roadmap's warning stands: never remove the workaround before its
  replacement is proven.

**Gate:** continuous planet-surface-to-deep-space fly-out with zero Z-fighting on a single
camera; `sky_camera.py` deleted.

---

### Phase R5 — Atmosphere & the Signature Look (high effort; the "wow" phase)

With correct lighting, verified color, working bloom, and single-camera depth, the showpiece
features become tractable:

- **Atmospheric scattering for orbital views.** Start with a single-scattering analytic limb
  model (per-planet-type parameters: rocky/ocean/gas/airless); Bruneton LUTs as a stretch goal
  once compute-shader precompute is worth the effort. Replaces the additive Fresnel shader.
- **Height fog / volumetric media** (~65 lines GLSL, tobspr) for gas giant depth and nebula
  volumes.
- **Environment-driven ambient:** derive ambient light from the skybox/nebula (spherical
  harmonics from the sky texture) instead of a flat constant — ships in a red nebula pick up
  red fill light. Distinctive, cheap (simplepbr's IBL machinery already exists in the fork),
  and uniquely fitting for this game.
- Lens flare/dirt polish on top of the bloom chain.

**Gate:** aesthetic sign-off per planet type; `Alt+A` comparisons against the old Fresnel shader.

---

### Phase R6 — Engine Hygiene (parallel, low priority)

- Remove `dxgsg9/` + `pandadx9/` (~600 KB dead code) once nothing references DX9.
- Cg dependency audit; shader-generator GLSL modernisation as needed by R4.
- ~~Quarterly upstream sync~~ **CANCELLED (2026-07-17): upstream severed by user decision —
  Pax3D is sovereign.** Upstream (`panda3d/panda3d`) is a read-only reference; specific fixes
  are hand cherry-picked if one ever matters. No cadence, no merge, no compatibility goal.
  Engine changes may now freely change defaults, rename, and delete inherited paths
  (`// PAX3D:` tags stay, for auditability not mergeability). See CLAUDE.md.
- Watch upstream's Vulkan branch as a *porting source*; evaluate only when it can run the
  paxtest suite (hand-port, scheduled build window — see §2.2).

---

## 4. What Changes vs. the Old Plan

| Old plan | This plan | Why |
|---|---|---|
| Bloom/HDR (Phase 2) before real lighting | Lighting (R2) strictly before bloom (R3) | F1 — bloom on an unlit scene does nothing |
| No test infrastructure | R0 harness is the first deliverable | F2/F3/F5 all survived because nothing could catch them |
| Extend simplepbr *and* game keeps pax_pbr | One `pax3d_render` package, game is a consumer | F7 — divergent forks meant fixes never landed where they ran |
| GLSL 120 with 330 ifdefs | GLSL 330 core minimum | Half the shader surface area, ends the sRGB ambiguity |
| Winding accepted, Formula B canonical | Fix sphere winding + tangents to match GLTF convention | One convention scene-wide; unlocks lookAt(), normal maps, spec sanity |
| Engine changes deferred indefinitely | Small targeted C++ in R2; big C++ (log depth) in R4 | The fork should earn its existence, incrementally |
| DirectX direction ambiguous | Explicit: GL 4.x now, hand-ported Vulkan later if ever, no D3D | §2.2 |

## 5. Suggested First Three Sessions

1. **Session A (R0):** Build `tools/paxtest/` with `test_gamma.py` + `test_lighting.py` +
   `test_bloom.py`. Run them against the current stack; record which fail and why. This turns
   F2 and F3 from mysteries into bug reports.
2. **Session B (R1 start):** Create `pax3d_render` from `pax3d_simplepbr` + game pax_pbr merge;
   GLSL 330; color contract; camera registration API. Game adapter behind a settings flag.
3. **Session C (R2 start):** Winding + tangents in `planet_factory.py` (validated by harness),
   then restore the DirectionalLight and switch the sun block to `p3d_LightSource[0]`.

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| Switching sun to `p3d_LightSource[0]` regresses planet look | Harness compares before/after per mesh type; keep `u_sun_*` path behind a define for one release |
| GLSL 330 breaks on some in-use shader | paxtest smoke-loads every shader in the package; the game's other custom shaders (atmosphere, terrain) are ported in R1 or explicitly left on their own path |
| Winding fix breaks atmosphere Fresnel / moon renderer | Old roadmap's regression list still applies — test atmosphere limb, moons, distant sprites after the mesh change |
| Log depth inconsistencies across shaders | Single `#include`-style snippet injected by `_shaderutils`; R4 gate requires the full fly-out test |
| ~~Fork drift from upstream~~ Divergence is now POLICY (severed 2026-07-17); residual risk: missing future upstream bug/security/driver fixes | Upstream remote kept read-only for hand cherry-picks; all C++ changes tagged `// PAX3D:` and listed in CLAUDE.md so our code stays identifiable |
| This plan also stalls after the fun parts | The gates are the guard: bloom (R3) is *blocked* until lighting (R2) passes its gate — enforced by the plan, checked by the harness |
