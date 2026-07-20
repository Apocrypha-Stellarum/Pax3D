# Pax3D Master Plan v3 — The Sovereign Engine Program

**Project:** Pax3D — sovereign engine (forked from Panda3D, now independent) + its
first-party renderer `pax3d_render`, built for the Pax Abyssi space sim (`C:\python\sfb2`)
and proven by a second game (openworld, `C:\python\openworld`).
**Date:** 2026-07-17 · **Supersedes:** Master Plan v2 (2026-07-16 — this same file;
see git history) · **Session narratives:** `SESSION_LOG.md` · **Audience:** the next
AI dev working on this engine.

---

## 0. Orientation (five minutes)

Read order: `CLAUDE.md` → this file → `PAX3D_RENDER_ARCHITECTURE.md` (how the
renderer works) → `tools/paxtest/README.md` (how everything is verified). Game-side
usage guide: `sfb2/documents/PAX_3D_ENGINE_AND_GRAPHICS/USING_PAX3D_RENDER.md`.

**The superpower — protect it.** Rendering work here is Python
(`pax3d_render/pipeline.py`) + GLSL (`pax3d_render/shaders/`), verified by an
offscreen harness that runs in seconds (`tools/paxtest/`), with two downstream
games whose AI devs field-test features same-day. Edit → measure → hand over →
field report. No engine build is needed for any of it. This loop found and killed
every "mystery bug" in the program's history; every process rule below exists to
keep it fast and honest.

| Environment | Python | Engine | Use |
|---|---|---|---|
| System | `C:\Python313\python.exe` | stock Panda3D 1.10.16 | paxtest cross-checks |
| Pax3D venv | `C:\python\pax3d-env` | Pax3D wheel (1.11-line) | the games' engine; build testing |

Identical paxtest results on both engines = the defect is Python/GLSL, not C++.

---

## 1. Verified state

| Phase | What | Status (evidence) |
|---|---|---|
| R0 harness | `tools/paxtest/` — 32 test files, 5 pipelines, 2 GL baselines, analytic checks + instruments | **DONE**; gates everything (Session A; grown every session since — Session Y totals: @game 71 PASS / 6 documented FAIL / 106 SKIP Pax3D · 69/6/108 stock; @modern 70/7/106 · 68/7/108; the FAIL set is the same six documented rows everywhere, +lighting/none @modern) |
| R1 unified renderer | `pax3d_render/` (pax_pbr ⊕ pax3d_simplepbr merge), color contract, `register_scene_camera()` | **Core done** (Sessions B, D — game flag flipped, boots clean). sRGB linearization experiment LANDED gated (Session R — `set_srgb_inputs`, test_srgb, ACES verdict on file). Open: in-game parity eyeball (user), sRGB default flip (game retune + sign-off), GLSL-120 path removal (needs game `gl-version 3 2`) |
| R2 directional sun + shadows | Pipeline-owned DirectionalLight, HPR-driven; shadows with world-space extent center; **hardened Session E**: world-unit bias, 3×3 PCF, no-cast API, skinned casters proven; **hardened Session G**: glTF caster darkening is a hard assertion, glTF caster+receiver test (angled sun), per-node `set_hardware_skinning()` opt-out; **Session I**: slope-scaled bias (`shadow_normal_bias_world`, opt-in) kills grazing-angle acne (fact 14) | **Core done + hardened** (test_shadows 13+13, test_shadow_quality 9, test_shadows_gltf 6, test_shadow_grazing 6, test_skinning 12). Open: in-game validation — set `shadow_bias_world` (~0.5 IEU) first; openworld dev A/Bs `shadow_normal_bias_world` at az 240 low sun |
| R3 bloom + HDR | F3 root-caused (8-bit intermediate FBOs) and fixed; float fbprops everywhere | **Core done** (Session D; test_bloom green both sizes). Open: content retune, light units, auto-exposure stretch |
| R4 space scale | R4.0 acceptance tests; R4.1 log depth opt-in (`enable_log_depth`, @logdepth row green); R4.2 camera-relative DECIDED (game-side; parent-cancel trap measured); doubles wheel **built + verified 2026-07-17**: precision 0.000e+00 at Neptune offsets, `test3d_ftl --selftest` green, but stock simplepbr crashes on it (stays quarantined in `pax3d-double-env`) | **Engine side essentially done.** Open: game-side R4.2 implementation, frustum flip, then sky-camera retirement; doubles perf A/B + user flight |
| R5 atmosphere + signature look | Scattering, SH-from-skybox ambient, height fog, lens polish | **Planetside slice LANDED opt-in (Session J, user-directed):** R5.1 aerial perspective/height haze (`enable_atmosphere`, analytic exponential-height medium + sunward scatter tint), R5.2 env ambient via the existing SH path (`set_hemisphere_ambient`/`set_ambient_sh`, `sh_from_cubemap` experimental), plus backlog shadow texel snapping (`shadow_texel_snap`). All default-off = byte-identical; gated by test_atmosphere/test_ambient_sh/test_shadow_snap, green both engines × both baselines. **Session M: R5.3 specular IBL first slice landed** (`set_env_map` + real BRDF LUT, test_env_map analytics exact). **Session Q: R5.4 GGX prefilter tool landed** (`tools/gen_env_prefilter.py`, test_env_map end-to-end) + sh_from_cubemap face table pinned incl. file-loaded skyboxes (test_ambient_sh 6-8) — the skybox → ambient + reflections chain is now proven and correct end to end. Open: field tuning in openworld Mars colony (`PLANETSIDE_LOOK_GUIDE.md`), orbital scattering + lens polish |
| R6 engine surgery | DX9 + dead-backend deletion | **Windows 2+3 DONE 2026-07-17** (`d29183ce42`, `3912762dd9` — −35k lines, both fully gated). Window 4 (mobile-target extraction) queued — `ENGINE_SURGERY_PLAN.md` |

Engine changes to date: the makepanda oscmd fix, the Route A catch-up merge
(`eb685fd003` — **built and signed off 2026-07-17**), and the R6 surgery
deletions (Windows 2+3). Still zero new own-C++ features.

---

## 2. Policies in force (all user-ratified 2026-07-17)

1. **Sovereignty.** The upstream Panda3D relationship is SEVERED — no sync cadence,
   no compatibility goal; upstream is a read-only reference for hand cherry-picks.
   One-time Route A catch-up merge was taken first (C++17 + 93 commits,
   `eb685fd003`), putting our base at upstream's July-2026 state, adjacent to their
   vulkan/shaderpipeline branch. Details: CLAUDE.md "Upstream Relationship".
2. **Language Canon.** *Prototype in Python/GLSL; promote to C++ on evidence.*
   Never port on faith — a profile or harness number first. C++ lands only in
   user-scheduled **build windows** (full rebuild ≈ 25–40 min on the B computer;
   the queue lives in CLAUDE.md). Full canon: CLAUDE.md "Language Canon".
3. **The working method** (unchanged since v2, still non-negotiable): verify with
   paxtest, not by launching the game; rendering fixes land in `pax3d_render/`
   only; eyeball with the testbed (`sfb2/test3d_pax.py`); respect phase gates;
   behavior changes ship opt-in with defaults byte-identical until signed off.

---

## 3. Established facts — do not re-litigate without new evidence

Each was established mechanically; each has a permanent guard.

| # | Fact | Proven / guarded |
|---|---|---|
| 1 | No Panda3D DirectionalLight engine bug — real lights work on every mesh type | Session A; test_lighting |
| 2 | No double gamma — every tonemap operator matches its analytic curve; the ACES "wash-out" is INPUT linearization (sRGB textures sampled raw) | Session A; test_gamma |
| 3 | Blocky bloom = 8-bit intermediate FBOs (`render_quad_into` without float fbprops silently downgrades RGBA16F); the banding mimics nearest-neighbor filtering | Session D; `bloom_buffers_float` |
| 4 | FilterManager rebuilds orphan externally-attached cameras — aux cameras must go through `register_scene_camera()` | Session B; test_rebuild |
| 5 | Runtime shader recompiles must preserve the ShaderAttrib (else every shader input is wiped) | Session C; shadows toggle check |
| 6 | Z-fight probing must SWEEP (single frames tie-break uniformly); the off-origin precision defect needs a ROTATED camera; the parent-cancel rebasing shortcut quantizes before composition | Sessions D/D2; test_scale |
| 7 | Skinned meshes DO cast shadows — everywhere (egg + glTF/Actor, hw + CPU skinning, GLSL 120+330, posed joints). The openworld "P0" was the bias trap + a proxy-contaminated instrument | Session E; test_shadows `skinned_*`/`gltf_caster_*` |
| 8 | `shadow_bias` is normalized light-space depth: world offset = bias × extent depth (0.005 ⇒ 20 IEU at the game's 500/4000). Use `shadow_bias_world` | Session E; test_shadow_quality `bias_trap_at_scale` |
| 9 | Both sphere windings light correctly through pax3d_render (the old Formula B/C saga is closed); tangents matter only when normal maps arrive | Session A/C; test_lighting both variants |
| 10 | The GL layer pads absent/short transform tables with identity — a depth shader with `ENABLE_SKINNING` always on is safe for static meshes | Session E C++ recon (`glShaderContext update_transform_table`) |
| 11 | Field reports are only as good as the tree they measured. The 2026-07-17 openworld "lit shadows vanish" P0 was measured against a worktree contaminated with stale Session-D-era `pipeline.py`/`pax_pbr.frag` (forensics: SESSION_LOG.md); on a clean engine `gltf_caster_ground_lum` darkens 0.800→0.086. Check `git status` + reproduce on a pristine checkout before chasing external regressions | Session F forensics; Window 1–3 gate logs |
| 12 | A luminance check is only as good as its sample geometry — and pose sources must be pinned. The promoted glTF-caster assertion FAILED on a healthy engine because (a) `get_anim_names()` ordering is nondeterministic (historical 0.086 readings were pose luck) and (b) the "pole" sample pixel is the receiver sphere's FRONT surface (y=−0.76), outside a thin caster's shadow column. Verify the sample point lies inside the caster's depth-map footprint before trusting a NO-SHADOW result | Session G; test_shadows comments + deterministic pose |
| 13 | The 94-joint Rigify hardware-skinning concertina (openworld P1) does NOT reproduce on a clean engine: GPU palette math == `animate_vertices` exactly; rendered GPU/CPU A/B ≤0.25% (shading-level) across all 50 Walk frames (pack 1: 0.00%); the compensating-scale chains compose to net 1.000; the shader palette cap was [100] in every era. Awaiting field re-measurement; per-node `set_hardware_skinning()` exists as the safety valve | Session G; test_skinning (permanent gate coverage) |
| 14 | The openworld direction-gated "vanishing shadows" (P0 addendum) are **grazing-angle self-shadow acne**: at low sun one shadow-map texel spans a large receiver depth, so a CONSTANT bias sized for normal incidence self-shadows the open ground into terracing bands (error ∝ 1/tan(alt) — the exact western-low-sun signature); the acne drops ground luminance so real cast shadows lose contrast and read as "gone." Byte-identical on stock 1.10.16 and Pax3D (GLSL, not C++). Fix = **slope-scaled bias** (`shadow_normal_bias_world`, opt-in, 0=off): adds bias ∝ tan(θ) only where the receiver grazes, so it clears acne without peter-panning the large-gap real shadows a bigger constant bias would erase. Proven on the real village GLB at az 240 (terracing gone, building/tree shadows kept) | Session I; test_shadow_grazing + probe_openworld_scale `--normal-bias` |
| 15 | **Vertex morphs (egg Dxyz sliders) are silently dropped by the hardware-skinning render path** — the loader creates the CharacterSlider and the CPU path (`animate_vertices`) applies the morph exactly, but under GPU skinning the rendered vertices never move (identical stock + Pax3D = upstream behavior, not a fork artifact). **CLOSED OPT-IN Session Z (2026-07-20): `set_gpu_morphs(np)` renders sliders ON the hardware-skinning path** (delta texture + GPU_MORPHS variant, §4.12); the DEFAULT path still drops them (byte-identical shipped behavior, hw_drops_morphs stays the guard) and `set_hardware_skinning(np, False)` remains the no-flags fallback. The bone-palette ceiling is now a knob (`max_skinning_bones`, default 100; [200] measured inert for small rigs — identity padding) | Session S; probe_morph.py + test_skinning `bone_palette_*`; Session Z test_morph_gltf `gpu_*` |
| 16 | **panda3d-gltf (pip 1.3.0) cannot load a real Blender morph export — three loader defects, all fixed by `pax3d_render.gltf_compat.install()`**: (a) sparse accessors (Blender's DEFAULT shape-key encoding; `bufferView` is legally optional) crash with `KeyError: 'bufferView'` (upstream Moguri#103, open); (b) an anim channel whose keys end before the clip's global end (legal, normal) crashes `get_next_time_index`; (c) `get_lerp_factor` clamps with `max(t,1)` instead of `min(t,1)`, so every LINEAR sample between keys snaps to the NEXT key's value — joints and morphs alike. All three are masked by dense per-frame bakes, which is why upstream ships them. With the shim, glTF morph delivery is CORRECT end-to-end: sliders + slider tables + morph columns arrive, CPU truth matches the Blender ground-truth manifest to 4 decimals, and a real weights channel drives sliders exactly (proven by byte-patching known values into the GLB — LINEAR lerp analytic to 0.001, short-channel hold exact). Fact #15 extends to glTF and to JOINT-LESS meshes: the scene-wide `F_hardware_skinning` flag drops morphs on static geometry too (image rms 0.000000); the per-node CPU opt-out renders them (~+0.1 ms/frame per 2240-vert head). Instrument trap: cached bams bypass the loader entirely — disable `BamCache` when measuring loader behavior | Session T; probe_morph_gltf.py (SK_SFM_Head1 + manifest, 26 facts, identical both engines) |
| 17 | **glTF alphaMode MASK only works in the compat profile** — panda3d-gltf expresses MASK as a geom-level `AlphaTestAttrib`, and the GL backend implements that attrib solely via fixed-function `GL_ALPHA_TEST` (`do_issue_alpha_test` sits behind `has_fixed_function_pipeline()`); under `gl-version 3 2` it is silently ignored and ALL MASK content renders opaque (a factor-only mask = a solid shell — the character dev's field report; cutout foliage = solid cards). Identical on stock 1.10.16 — upstream behavior, not fork damage. Fix: `pipeline.apply_alpha_masks(model_np)` composes an ALPHA_MASK PBR variant onto exactly the stamped geoms (in-shader discard, same predicate ⇒ compat bit-identical, measured rms 0.0). **Extended Session AA (ER-009):** `TransparencyAttrib M_binary` is the SAME class of defect — cull composes `AlphaTestAttrib(GE, 0.5)` at max priority (`cullResult.cxx`), fixed-function-only, so M_binary foliage also renders solid @modern; detection now catches it (geom- or node-level), and `apply_alpha_masks(np, instanced=True)` keeps the mask variant paired with INSTANCING under set_instanced (the default variant collapses instances onto the origin — gate-measured). Depth-pass caveat: compat gets cutout shadows from the fixed-function test, modern casts the unmasked silhouette — `exclude_from_shadows()` is the valve; a cutout-shadow depth path lands only on field evidence | Session W; test_alpha_mask (both engines × both baselines); Session AA `binary_*`/`instanced_*` checks |
| 18 | **Every offscreen frame on the 1.11 fork raises one GL_INVALID_OPERATION — and it was never about characters.** The FPS-lane field attribution ("playing characters") measured wrong: an EMPTY offscreen scene errors identically (probe matrix: fork offscreen 1/frame both baselines; fork real window 0; stock 1.10.16 0 everywhere; the Window-1 wheel reproduces → predates all R6 surgery). Root cause: upstream `bd4dc8a379` (2024-10, a **DX9** wdxGraphicsBuffer copy fix, before our divergence point) commented out the single-buffered branch of `FrameBufferProperties::get_buffer_mask()`, so `prepare_display_region` issues `glDrawBuffer(GL_BACK)` on the single-buffered wgl pbuffer. Consequence: the once-per-second error sweep reaches `gl-max-errors` (default 20) after ~20 s of offscreen wall time and **panic-deactivates the GSG — frozen framebuffer, silently stale screenshots** (every paxtest process runs under this deadline; the runner never surfaced the stderr noise). Sibling defect: `gl-max-errors -1` (documented "no limit") deactivates on the FIRST error — bare `>=` at glGraphicsStateGuardian_src.cxx:4817 (`report_errors_loop` honors -1 correctly). One-line C++ fixes **LANDED (Session X part 2 mini-window, 2026-07-19)**: `PATCH_QUEUE_GL_OFFSCREEN.md` — probe now 0 errors/frame everywhere (was ~60/phase); the `gl-max-errors 1000000` workarounds can come out of game harnesses. Technique worth keeping: pin the global clock to dt>1 s so the 1/sec sweep runs every frame — per-frame GL-error attribution on a release build | Session X; probe_gl_errors.py + test_gl_clean (now the permanent zero-GL-errors guard, both engines) |
| 19 | **The GPU morph path needs NO engine change and NO gl_VertexID — it runs on stock 1.10 too.** Morph deltas ride a per-vdata RGB32F data texture (width = vertex rows, height = 2×targets: position row 2t, normal row 2t+1) addressed by a plain float32 `morph_index` column — one mechanism on BOTH GLSL baselines. Two conventions MEASURED before building (TexturePeeker probe): Texture ram row 0 = texcoord v=0, and `set_ram_image_as(data,'RGB')` preserves float component order. Panda ships normal deltas alongside positions (`normal.morph.<slider>` columns — the GPU path is lighting-correct, not position-only). Instrument trap the bench exposed: `apply_freeze_scalar` alone does NOT dirty the bundle — without `force_update()` (or a playing clip) the CPU path re-animates nothing and a perf A/B silently measures an idle scene (the +0.01 ms tell) | Session Z; probe_ram_order (scratchpad), test_morph_gltf `gpu_*` (12/12 both engines × both baselines), probe_gpu_morph_bench.py |

---

## 4. The road forward

Ordered by dependency, not excitement — the v2 lesson stands: *measure first,
light before glow, engine truth before content tuning.*

### 4.1 ~~In flight: Build Window 1~~ — COMPLETE (2026-07-17)

Both wheels built, the full gauntlet ran green, the merge is signed off, and
R6 surgery Windows 2+3 followed the same day (each with its own build + gate).
The program's engine base is now: upstream July-2026 + C++17, minus 35k lines
of dead backends, on a machine that rebuilds in 8 minutes. Details:
`BUILD_WINDOW_1_CATCHUP.md` (historical), `SESSION_LOG.md` (Session F).

### 4.2 Game-side adoption queue (needs the user / game dev, not this repo)

All engine work is done and waiting; these are eyeball-and-tune items in sfb2:

1. **Parity eyeball** (R1): `use_pax3d_render` is flipped and boots clean — compare
   look vs the legacy path, sign off.
2. **Shadows in the pilot seat** (R2): before judging anything, set
   `shadow_bias_world` (~0.5 IEU; the default normalized bias is ~20 IEU of offset
   at extent 500/4000 and will erase ship-scale shadows). Consider
   `shadow_filter_size=3` and `exclude_from_shadows()` for sky/FX geometry.
   Validate terminator + ship self-shadowing at the four cardinals.
3. **Bloom-on decision + retune** (R3): strength/intensity/tints (note the per-mip
   tint list reads inverted vs its comment labels), then the magic-number
   compensation factors go, one per test run.
4. **sRGB linearization ADOPTION** (R1): the experiment itself is DONE
   (Session R): `pipeline.set_srgb_inputs(True)` is the canonical flag,
   test_srgb gates the exact decoded analytics through all four tonemap
   curves, and the ACES prediction is VERIFIED in the testbed
   (`--tonemap aces --srgb`: wash-out gone, brightness drops). What
   remains is the game decision: retune sun/exposure around linear
   inputs and sign off the default flip (arch doc §8 has the verdict
   and the two adoption traps).

### 4.3 R4.2 — camera-relative rendering (game side, coordinated)

Decision made (2026-07-17): anchor-relative placement in the game's positioning
layer — sim state in Python doubles, `sim_pos − anchor` computed in doubles, only
small numbers to `set_pos`, anchor follows the player. The engine needs **zero
changes** (camera pos, log-depth coefficient, shadow center are all per-frame).
The trap is measured: don't parent-cancel (test_scale
`trap_parent_cancel_quantizes`). Integrate with the nested-space architecture
(deep-space mode already anchors at origin — generalize, don't rival; coordinate
with the game-space dev's `NESTED_SPACE_ARCHITECTURE.md`). Acceptance: jitter-free
orbit + fly-out at system scale; then the game flips the wide frustum +
`enable_log_depth`; sky shaders adopt the log-depth formula; **only then** does the
sky camera retire (never delete the workaround before its replacement is proven).
The doubles wheel, if Build 2 succeeds, is a complementary experiment — measured
against `handover_doubles_spike.md`'s checks, adopted only if it beats
camera-relative on evidence.

### 4.4 R5 — atmosphere & the signature look (planetside slice landed Session J)

The planetside half was pulled forward by user direction (2026-07-18 — the
openworld Mars colony proved the planetside use-case; spaceflight stays
first priority, so every feature is opt-in, default-off, byte-identical,
toggleable off for space scenes):

- ~~**Env-driven ambient** first~~ — **LANDED opt-in (Session J / R5.2):**
  `set_hemisphere_ambient(sky, ground)` (exact SH bands 0–1 — the two-tone
  sky/bounce ambient), raw `set_ambient_sh()`, `clear_ambient_sh()`, and
  `sh_from_cubemap()` for real skyboxes (shipped EXPERIMENTAL; orientation
  PINNED end-to-end in Session Q — no longer experimental). Zero shader
  changes — it feeds the sh_coeffs path that shipped zeroed since R1.
  Gated by test_ambient_sh (analytics exact). Both former open items are
  closed: orientation pinned (Session Q, checks 6-8), specular env maps
  landed (Session M, R5.3 below).
- ~~**Height fog / aerial perspective**~~ — **LANDED opt-in (Session J /
  R5.1):** `enable_atmosphere` — analytic exponential-height medium with
  sun-forward scatter tint (arch doc §9). Gated by test_atmosphere. Open:
  content tuning per planet type (Mars starting values in
  `PLANETSIDE_LOOK_GUIDE.md`).
- Also landed from the backlog: **shadow texel snapping**
  (`shadow_texel_snap`, arch doc §5.7, test_shadow_snap) — the planetside
  camera-following-frustum shimmer fix.
- ~~**Specular IBL env map**~~ — **LANDED first slice (Session M /
  R5.3):** `set_env_map(cubemap)` + the real split-sum BRDF LUT
  (`textures/brdf_lut.txo`, `tools/gen_brdf_lut.py` — the shipped 1×1
  white fallback would have corrupted the term the moment a real env
  bound; set_env_map refuses to run on it). Mip chain = roughness
  ladder (feed a GGX-prefiltered chain for correctness; box mips are
  the documented approximation). Gated by test_env_map (analytics
  exact vs LUT peek; ladder, orientation, glass composition).
  **Session Q closed the gap (R5.4): `tools/gen_env_prefilter.py`**
  bakes the correct complete GGX chain (reference sampling math
  borrowed from pip simplepbr; test_env_map checks 8-11 prove it end
  to end). Also Session Q: the sh_from_cubemap face table PINNED for
  file-loaded skyboxes (test_ambient_sh 6-8; up-face image top row =
  southern sky). Open: per-scene cubemap authoring.
- ~~**Atmospheric scattering** for orbital views~~ — **LANDED opt-in
  (Session R / R5.5):** `set_orbital_atmosphere(planet_np, ...)` —
  per-planet single-scattering analytic limb model (camera-facing quad
  pair: per-channel extinction + additive inscatter; soft terminator,
  Rayleigh-tint reddening; Earth-like defaults derived from radius).
  Gated by test_orbital (independent reference integrator matches the
  rendered limb to <=0.003; opt-out rms 0.0). Arch doc §9 has the full
  model + the R5.1 boundary (fly-down handoff = game-paced R4.2-era
  work). Bruneton LUTs remain the stretch goal if content demands
  multi-scatter. Open: per-planet-type content presets from the game's
  catalog (blackbody sun tint composes via update_sun already).
- ~~Lens flare/dirt polish on the bloom chain~~ — **LANDED opt-in
  (Session S): R5 IS NOW COMPLETE.** `enable_lens_flare` /
  `set_enable_lens_flare()` (rebuild-class; requires enable_bloom) —
  pseudo-flare ghosts sourced from the bloom bright extract at
  analytic center-scaled positions (occlusion implicit: a hidden sun's
  flare vanishes with its extract energy), `set_flare_strength`
  (0 = exact no-op), `set_lens_dirt(tex, strength)` screen-space dirt
  with exact clean restore. Gated by test_lens_flare (ghost positions
  analytic ±0.000 control; dark-scene/strength-0/dirt-clear/opt-out
  all rms 0.0), green both engines × both baselines. Remaining R5
  work everywhere is CONTENT ADOPTION only.

Gate: aesthetic sign-off per planet type; A/B against the old Fresnel
shader. Field consumer for the planetside slice: the openworld Mars
colony map (guide doc above).

### 4.5 R6 — engine surgery (Windows 2+3 DONE 2026-07-17)

`ENGINE_SURGERY_PLAN.md` is the authority. Window 2 (DX9, `d29183ce42`) and
Window 3 (mobile/GLES/WebGL/macOS backends + the DX9 flag machinery,
`3912762dd9`) both executed with their own builds and full gates — the
none/simplepbr canary rows never moved. x11/glx held, tinydisplay kept.
Window 4 queued: mobile-target extraction (android/iphone app glue, makepanda
Android machinery, deploy-tool logic, DIRECTCAM). Cg still deferred — it
falls out for free if the shaderpipeline port ever happens.

### 4.6 Watch: upstream `vulkan` / `shaderpipeline`

Active as of 2026-07-02/03 (shaderpipeline merged into the vulkan branch).
Post-merge, our base sits adjacent to it — a future hand-port is the plausible
next-gen graphics path (and would obsolete Cg + the GLSL-120 machinery wholesale).
Evaluate ONLY when it can run the paxtest suite. No cadence; check when curious.

### 4.7 Backlog (small, owned, waiting for their moment)

| Item | Home | Trigger |
|---|---|---|
| ~~Direction-gated lit-shadow failure (openworld P0 addendum)~~ | pipeline + paxtest | **ROOT-CAUSED + FIX LANDED Session I (fact 14):** it is grazing-angle self-shadow acne (∝ 1/tan(alt)), not a depth-path corruption. The toy sweep was clean because flat toy ground at alt 34 doesn't graze hard enough — the trigger is sun-altitude × terrain-slope. `shadow_normal_bias_world` (opt-in slope-scaled bias) clears it: proven on the real village GLB at az 240 (terracing gone, real shadows kept). Open: openworld dev A/Bs the value in-app and signs off |
| ~~paxtest hardening (openworld asks)~~ | tools/paxtest | **DONE Session G** — assertion promoted (after fixing two test-geometry traps it exposed, fact 12), `test_shadows_gltf.py` added; green both engines × both baselines |
| ~~Hardware skinning vs 94-joint Rigify rigs~~ | pipeline + shaders | **RESOLVED Session G (fact 13):** not reproducible on a clean engine — `test_skinning.py` guards it permanently; per-node `set_hardware_skinning()` opt-out landed anyway. Reopens ONLY if openworld's re-measurement on the clean wheel still concertinas in-app (then: their in-app repro + test_skinning on their machine first) |
| ~~Engine-side shadow texel snapping in `set_shadow_extent`~~ | pax3d_render (Python) | **DONE Session J** — `shadow_texel_snap` (opt-in, default off), snaps the frustum center to the texel grid along the light's film axes; gated by test_shadow_snap (sub-texel sweep leaves depth map + screen byte-identical; whole-texel steps still follow) |
| ~~Slope-scaled / receiver-plane shadow bias~~ | pax_pbr.frag | **DONE Session I** — slope-scaled depth bias (`shadow_normal_bias_world`), opt-in, gated by test_shadow_grazing; physics + API in arch doc §5.2 |
| ~~Runtime fog toggle~~ | pax3d_render | **Superseded by Session J R5.1** — `set_enable_atmosphere()` is the runtime toggle; the legacy `enable_fog`/p3d_Fog path stays as-is |
| ~~SSAO first slice~~ (game Tier-1 ask; walkable-interior contact shading) | pipeline + shaders | **DONE Session S** — `enable_ssao` (opt-in, rebuild-class): depth-only Alchemy/SAO obscurance + blur, applied in tonemap; flat geometry = AO exactly 1.0 (plane byte-identity gated); knobs ao_radius/ao_intensity/ao_bias uniform-only, ao_samples init. test_ssao green both engines × baselines × @logdepth × **@msaa4 (measured: the multisampled depth resolve works)**. Upgrade path documented: indirect-only AO via scene-pass sampling; depth+normals foundation now exists for TAA v2/SSR |
| CSM (cascades) | pipeline + shaders | Post-R5, if extent-following stops sufficing |
| Clustered/tiled lights | shaders (+ maybe C++ culling) | Post-R5; openworld's Megacity wants it (781 lamps vs ~6 forward lights) |
| `shaderAttrib.cxx:471` intermittent assert | engine | Needs a repro (fires when a shader reads an unbound input; the known recompile-wipe class is fixed) |
| Planet analytic tangents | sfb2 `planet_factory.py` | When normal-mapped planets arrive |
| GLSL-120 dual-path removal (R1.4) | pax3d_render | The game sets `gl-version 3 2` |
| R2.3 DirectionalLight C++ conveniences | engine | If ever — the pipeline owns orientation. Window-4 planning (2026-07-19) scoped it and found a DESIGN CONFLICT: the queued strip-translation `xform()` clashes with the pipeline's deliberate lighting-neutral `set_pos()` shadow-frustum centering (pipeline.py `_apply_shadow_center`, guarded by test_shadows `recenter_keeps_lighting`), and test_lighting's SunRig intentionally uses raw `set_direction()`. Needs its own design pass (DIRECTIONAL_LIGHTING_PLAN.md §4) before any window takes it |

### 4.8 Asset enablement — walkable ships (Session K+, user-directed)

Trigger (2026-07-18): the game is integrating the CGTrader Phobos
Starhopper (fully modelled interior, animated doors/ramp/gear, PBR
texture sets) as a walkable grounded ship. Scoping what imported assets
of this class need from the engine produced a four-item queue. Same
contract as the planetside package: opt-in, default-off, byte-identical
when off, paxtest-gated.

| Item | Status |
|---|---|
| ~~Specular-preserving glass~~ (`set_glass(np)`) — premultiplied-alpha PBR variant: alpha attenuates transmission terms only; specular (sun/local/IBL) and emission at full strength | **DONE Session K** — test_glass, analytics exact, green both engines × both baselines × both sun modes + the routed pax_pbr path; arch doc §9. Pair with `exclude_from_shadows()` on canopies (depth pass is opaque by design) |
| ~~`gl_FrontFacing` normal flip for doubleSided glTF materials~~ (backfaces were lit from the wrong side — thin panels, decals, seat fabric) | **DONE Session K** — `double_sided_lighting` init kwarg + `set_double_sided_lighting()` (recompile-class); test_doublesided (backface 0.108→0.705 analytic exact, front faces bit-identical under the flag, opt-out byte-identical), green both engines × baselines × sun modes. Opt-in because existing two-sided content (foliage cards, FX quads) WOULD change look — games eyeball then flip it on |
| ~~Per-node ambient scale~~ — keep the global SH sky ambient out of hull interiors | **DONE Session L** — `set_ambient_scale(np, k)`/`clear_ambient_scale(np)`: inherited `u_ambient_scale` input folded into the AO factor (scales SH/IBL + flat ambient ONLY; direct light and emission untouched — sun shafts still work). Root default 1.0 = exact no-op. test_ambient_scale (per-channel analytics exact ×3 states incl. the sun-shaft case), green both engines × baselines. Ship-dev-prioritized #1: "the interior is unlit without it" |
| ~~Specular IBL first slice~~ (`set_env_map()`) — canopy/hull reflections | **DONE Session M / R5.3** — see §4.4; test_env_map's mirror checks also prove the shader's cube-sampling orientation is GL-standard (evidence toward the Session J sh_from_cubemap question, sampling side; the loaded-skybox file-orientation half stays open) |
| ~~Blender/glTF-authored lights~~ (ships, stations — "simplepbr lights don't work") | **DONE Session P** — `activate_model_lights()`/`deactivate_model_lights()`: panda3d-gltf converts KHR_lights_punctual to real light nodes, they were just never activated; directional excluded by default (pipeline owns the sun), `scale` knob for the physical→scene units (I·4π/683, quadratic att). Gated by test_local_lights 7–9 (inert→analytic→byte-identical restore) |
| ~~Per-node atmosphere scale~~ (Phobos field ask 2026-07-18: aerial haze washes the cabin interior) | **DONE Session S** — `set_atmosphere_scale(np, k)`/`clear_atmosphere_scale(np)`: inherited `u_atmo_scale` input multiplying the R5.1 optical depth (root default 1.0 exact no-op; k=0 ⇒ tau exactly 0 = no haze on the subtree, windows still show hazed terrain). Gated by test_atmosphere `atmo_scale_*` (no-op/analytic/sibling/restore all exact), green both engines × both baselines |
| ~~Per-subtree environment binding~~ (Phobos consult ask 2026-07-18: cabin reflections/ambient vs sky) | **DONE Session S** — `set_env_map(tex, node=np)` + `set_ambient_sh`/`set_hemisphere_ambient(..., node=np)` + node-form clears: inherited-input overrides (env map + max_reflection_lod together, so the node chain's ladder addresses correctly). Gated by test_env_map `pernode_*` (node mid-roughness analytic exact through the NODE lod — a global-lod leak would miss by ~0.25; sibling 0.000; clear rms 0) and test_ambient_sh `pernode_sh_*`, green both engines × both baselines |
| **Interior collision / local walkable-mesh story** (registered 2026-07-18 from the ship dev: game walk mode is heightfield-only; a ship interior is a floor above terrain with walls and a ceiling — "walk around inside" is blocked on this) | **DESIGN AGREED Session N (2026-07-18)** — the ship dev accepted the position below and supplied their opening shape (`phobos_collision` subtree, CollisionSegment + pusher inside bounds, ramp-foot handoff); the joint design is written up in `WALKABLE_INTERIOR_COLLISION_DESIGN.md` with 10 engine facts MEASURED by `tools/paxtest/probe_walkmesh.py` (both engines, identical; facts 8-9 = Session S pusher-readback contract + chunk bounds-culling, doc §9) — two corrected en route: segment-vs-polygon is DOUBLE-SIDED (floor winding cannot break the ground query) and same-frame procedural joint reads need `Character.force_update()`. No engine code needed; implementation + field report are game-side |

Ship-dev priority ranking (2026-07-18, recorded): ambient scale →
double-sided → specular IBL ("pure polish"). The first two are landed;
IBL is the queue's remaining rendering item.

**Interior-collision design position (engine side, for the joint
design):** no new engine code expected for a first slice — Panda's C++
collision system already covers it. Recommended shape: (1) the ship
GLB conversion emits a dedicated LOW-POLY collision subtree (named
`collision_*` geoms: floors/ramps walkable, walls/ceiling blockers),
hidden from render — never ray-test the dense render mesh; (2) walk
mode, when the player is inside the ship's bounds volume, switches its
ground query from heightfield sample to a downward `CollisionSegment`
against that subtree via a scene-local `CollisionTraverser` (C++ cost),
with wall blocking from a `CollisionHandlerPusher` sphere active only
inside; hand off at the ramp/airlock by zone (or `max(floor_hit,
heightfield)` during the transition); (3) door/ramp collision nodes
ride the same animated joints as the visuals, so an open ramp is
automatically walkable. If the game uses its own character controller,
the contract reduces to "the ship provides a collision subtree; query
it with a traverser." Engine deliverables only if their profiling shows
traverser cost (unlikely — it is already C++); the design conversation
itself is the next step and belongs with the game dev.

Established while scoping (needs NO engine work): interior point/spot
lights (the p3d_LightSource loop is the known-correct path; lights scope
per-node), emissive cockpit screens (emission maps default-on, feed
bloom), animated doors/ramp/gear (node animations, no skinning). Config
only, game side: `use_normal_maps=True`, `use_occlusion_maps=True` for
this asset class; multi-layer glass stays separate geoms (per-geom
transparent-bin sorting).

### 4.9 Terrain lane — the Unity terrain-asset standard (ER-001/002/003, Session U+)

The game's eye-level terrain push, driven from
`C:\python\sfb2\documents\ENGINE_REQUESTS\` (one file per ask, statuses
maintained in place — engine notes written into each ER, 2026-07-19).
User direction: the Unity terrain-asset standard is the terrain data
interchange (120 owned Gaia/PW stamps + ~35 PBR layer sets + scatter
palettes become drop-in). Sequencing agreed with the terrain dev:
**003 → 001 → 002-interleaved**, all Python/GLSL, no build window.

1. **ER-003 — data-texture contract. IMPLEMENTED ENGINE-SIDE +
   GATED (Session U).** `pax3d_render.data_texture(tex)`: post-hoc,
   idempotent contract stamp (CM_off, ATS_none, sRGB unflag,
   single-channel ushort/float → F_r16/F_r32; multi-channel untouched —
   RGBA8 splat weights deliberately ride only the compression/sRGB
   clauses). `load_data_texture(path)`: PNMImage/PfmFile + `tex.load()`
   file route — immune to the `texture-scale` prc, which rescales INSIDE
   `Texture.read()` (name-glob-gated only; ATS does not exempt; measured).
   test_data_texture (13 checks) runs with `compressed-textures 1` LIVE:
   anti-terracing probe (1022-code gradient → 161 distinct levels vs 9 for
   the 8-bit negative control), byte-exact GPU round-trips (R16 file +
   R32F procedural) beside a DXT1-compressed canary, sRGB-walk
   non-interference, and the texture-scale trap + immunity pair.
   Identical both engines × both baselines. Upstream fact for intake
   tooling: Panda's 16-bit TIFF WRITER hard-crashes (native, both
   engines); reads are fine — intake writes PNG16.
2. **ER-001 — terrain splatting. IMPLEMENTED ENGINE-SIDE + GATED
   (Session U, same day).** `set_terrain_splat()`: TERRAIN_SPLAT
   per-subtree variant of pax_pbr (set_glass mechanism → sun/shadows/
   haze/IBL compose free), splat-map-driven, 4 layers via 2D texture
   arrays (sampler2DArray works on BOTH GLSL baselines — EXT_texture_
   array on 120, measured), per-layer uv_scale, splat-UV window
   transform, macro variation, detail-normal distance fade, analytic
   world TBN (chunks need no tangent column; u→+world_x, v→+world_y
   convention). The layer-weight function is the isolated v2 define
   seam (hex-tiling LANDED there Session Y — §4.11; height-blend
   sharpening LANDED Session AA — §4.13 — after the terrain dev
   delivered the height8-in-albedo.a source). Gate: test_terrain_splat
   — 12 EXACT analytic checks (quadrants, bilinear blend, renorm,
   macro, uv_scale, normal tilt+fade, byte-identical opt-out) + a
   directional-sun variant row; green both engines × both baselines.
   Remaining: game-side adoption (layer sets + per-chunk splat maps
   from their intake, in progress on their side).
3. **ER-002 — scatter. IMPLEMENTED ENGINE-SIDE + GATED (Session U,
   same day).** `set_instanced()` over upstream `InstancedNode`:
   INSTANCING define in pax_pbr.vert AND shadow.vert + F_hardware_
   instancing, shadow-caster initial states invalidated when the
   define flips. Zero C++ needed. Measured surprises (ENGINE_INTERNALS
   §3): WITHOUT the call the traverser renders every instance
   correctly (one draw each) — set_instanced is a PERFORMANCE switch,
   not correctness; per-instance frustum culling is upstream built-in;
   `clear_shader()` keeps attrib FLAGS (a hand-set flag without the
   INSTANCING shader collapses instances onto the origin — API keeps
   them paired, gate-guarded). Gate: test_instancing — fallback
   correctness, pairing trap, all-instances render, rms-0.0 vs plain
   copies (45° roll + 1.5× scale), instanced shadow casting 4/4,
   byte-identical opt-out; SKIPs on stock 1.10 (no InstancedNode).
   Remaining: game-side adoption; InstanceList bulk fill stays queued
   on profile evidence only (CLAUDE.md queue).

### 4.10 Walkable-ship animation + displays lane (ER-004/ER-005, Session V)

The Phobos/Minerva push continued: the ship dev's Session-632 census of
both Vattalus .unitypackages (`sfb2/documents/PLANETSIDE/
MINERVA_CENSUS.md` — NO .anim files, NO AnimatorControllers; motion is
FBX takes + prefab script-lerps + toggles; displays are six mp4 loops on
VideoPlayer→RenderTexture materials) rewrote both ERs with measured
evidence. Both implemented engine-side same-session (Session V,
2026-07-19), Python/GLSL only, no build window:

1. **ER-004 — rigid clips. IMPLEMENTED ENGINE-SIDE + GATED.**
   `pax3d_render/rigid_clips.py` + `pipeline.get_model_clips(np)`:
   panda3d-gltf consumes glTF animations only inside build_character()
   — plain-node TRS channels (every door/ramp/gear/drawer clip) are
   silently dropped (ENGINE_INTERNALS §5). The module parses them
   straight from the .glb into `RigidClip` stores (LINEAR/STEP/
   CUBICSPLINE, skin-joint + morph channels skipped — complementary to
   Actor), with the loader's own Y-up→Z-up conjugation applied
   per-component and PINNED against the loader's rest pose in-gate.
   Nodes stay ordinary PandaNodes (the ER's hard requirement).
   `RigidClipPlayer` seeks t∈[0,1]/seconds, stateless (reverse = 
   decreasing u), reset() restores rest; the game owns easing/sounds/
   collision gating. `RigidClip.from_delta()` synthesizes the prefab
   script-lerp source (~40 Minerva parts: pos delta + rot delta +
   duration) as relative two-key clips composing onto rest. Gate:
   test_rigid_clips (in-test-authored GLB, 10 checks: loader-drop
   premise, axis contract 0.0 err, analytic seeks/slerp/STEP/Hermite,
   delta compose, render A/B). **ADOPTED GAME-SIDE (session 637,
   2026-07-19): the Phobos console clip flows end-to-end through the
   store — contract held in the field (seek(0)==rest 0.0 err, travel
   to 1 mm, reset 1e-7); converter merges same-named NLA tracks into
   one multi-node clip each.** Remaining: the Minerva's ~40 prefab
   from_delta parts (validators: Bathroom door + one cupboard).
2. **ER-005 — powered displays. IMPLEMENTED ENGINE-SIDE + GATED.**
   The census's top ask (video-textured emissive surfaces) +the pokes:
   `set_screen(np, tex)` (albedo+emission binding at override, HDR
   emission, byte-identical restore; accepts ANY texture — flipbook
   atlas, dynamic set_ram_image, MovieTexture where decodable, static),
   `set_emission_scale/_color` (`u_emission_factor`, power states —
   0.0 = VA_ScreenOff with albedo still lit), `set_uv_transform` /
   `set_uv_scroll` (chase-light strips) / `play_flipbook` (atlas
   playback, `tools/gen_flipbook.py` converts videos at intake — the
   machine's ffmpeg CLI works, tested end-to-end). **Engine fact the
   lane rests on: the Pax3D wheel builds `--no-ffmpeg` — MP4 decode
   does not exist engine-side.** The flipbook is the sanctioned video
   path. Both uniforms are root-default exact no-ops; scroll/flipbook
   are pipeline-task-driven (O(active)/frame, zero idle). Gate:
   test_screen (15 analytic checks, every opt-out rms 0.0).
   **Questions RESOLVED (ship-lane Session 634 + user sign-off,
   2026-07-19): video carrier = TRIMMED flipbooks (long loops cut to
   10–20 s at intake; three of six run 1–2.8 min but are ambient FUI
   dressing) — the ffmpeg build-window question is CLOSED, the build
   stays `--no-ffmpeg`; converter splits per-screen nodes (49 screen
   bindings / 6 shared materials measured — set_emission_scale is
   per-node so materials stay shared); from_delta's local-frame
   compose VALIDATED against VattalusInteractable.cs source (line 248
   right-first multiply = our `delta * rest` exactly). Bonus census
   correction: pack easing is smoothstep (two-key zero-tangent
   AnimationCurve), not linear — game smoothsteps `u` (player is
   stateless by contract; a zero-tangent CUBICSPLINE channel is the
   in-store equivalent).** Remaining: game-side adoption (converter
   re-export + ClipPlayer wiring — their handover task 1 is the Phobos
   console clip on the landed store; atlas intake of the 6 loops;
   hologram stays deferred).
3. **Ship exterior/status lights (Session V part 3, user-directed off
   the Minerva screencaps). IMPLEMENTED + GATED same day.**
   `set_blink(np, period, pulses, phase, lights=)` / `clear_blink()`:
   pulse-train blinker on the emission factor (composes with the
   Session-V emission registry — setters re-base a blinking node, no
   one-frame pop) with optional real light nodes gated by the SAME
   envelope; edge-triggered pushes (~4/s per strobe); per-ship phase
   de-syncs fleets. Gate: test_screen 9b (envelope pinned; ON/OFF
   renders byte-identical to the emission-scale states; light sync +
   restore) — test_screen now 19 checks. Circuits model documented
   (737NG panel: position/beacon/strobe/floods as NAMED subtrees,
   each switch = 2–3 byte-identical-opt-out calls; airliner numbers
   in the ER addendum + set_blink docstring). **Light budget MEASURED
   (both baselines): with shadows, max_lights 16/20/22 link + light
   correctly, 24 FAILS to link (v_shadow_pos varying array vs the
   ~128-component budget) — recommend 16, ceiling 22.** NPC ships:
   emissive markers + bloom only (the packs' own convention); real
   lights for hero/parked ships. Interior look + shower-water recipes
   in the ER addendum (existing APIs — no engine work).

### 4.11 Session Y (2026-07-20) — ER-007 hex-tiling, ER-008 light policy, Round-5 env asks

The full outstanding game→engine queue cleared in one session — all
Python/GLSL, no build window, everything opt-in/default-exact-no-op:

1. **ER-007 — hex-tiling. IMPLEMENTED ENGINE-SIDE + GATED.**
   `set_terrain_splat(..., hex_tiling=True, hex_cell_size=4.0,
   hex_rotation=1.0 (per-layer capable), hex_contrast=6.0)` — the
   TERRAIN_HEX_TILING define at the ratified v2 seam. Mikkelsen-style
   3-tap stochastic tiling; per-cell constant transforms keep every
   tap's UV continuous wherever its weight is nonzero, so plain
   sampling mips correctly on BOTH GLSL baselines (no textureGrad —
   the 120 array path has none). Normals ride the same cells with
   back-rotated tangent xy; contrast = the cheap variance-preserving
   weight sharpen (histo-preserving on the books). Gate:
   test_terrain_splat +12 checks (uniform-layer invariance exact;
   shift-rms 0.0014→0.2296 periodicity break; mean preserved;
   anisotropy contract |dy|/|dx| 0.19 rot0 / 1.14 rot1; normal
   back-rotation live; byte-identical opt-out) — identical on all four
   engine × baseline configs. Height-blend rider NOT shipped: needs a
   height source; proposed carrier = albedo array alpha (terrain-unused)
   — question posed to the terrain dev in the ER.
2. **ER-008 — light selection policy. ANSWERED + ARMED + GATED.**
   The policy (from the C++, then measured): overflow uploads the
   priority-sorted head (`Light.set_priority` desc — fully dynamic),
   ties by class rank (spot > directional > point), equal ties
   ARBITRARY (measured differing between identical runs), excess
   silently dropped. Delivered: (a) **sun eviction guard, default-on**
   — the directional-mode sun competes in the same array and spots
   outrank directionals, so overflowing floods would have evicted the
   sun + shadows; `_create_sun_light` now pins priority 1<<20;
   (b) **`set_light_budget(root, lights, budget, anchor, radius,
   hysteresis)` / `clear_light_budget`** — the per-root nearest-N
   warden (the structural ask): scores luma over the light's own
   attenuation, binds top-N, rebinds only on membership change,
   blink-steady scoring, budgets LOCAL per hull; (c) Q3's priority
   field = `set_priority`, already existing, now documented + gated.
   Bonus fact on record: zero-light draws get a default WHITE slot-0
   light (GSG default-fill). Gate: NEW test_light_priority
   (+@directional variant) — 7+2 checks green on both engines × both
   baselines.
3. **Round-5 env asks (PAX3D_FEEDBACK_3.md §3). ALL THREE
   IMPLEMENTED + GATED.** `set_env_scale(np, s)`/`clear_env_scale`
   (per-node, ibl_spec only — ambient untouched), `set_env_intensity(s)`
   (global, composes multiplicatively), `set_env_map_rotation(deg)`
   (specular lookup yaw about +Z, skybox set_h sense, Rz(−θ)·r in-
   shader). Root-defaulted exact no-ops. Gate: test_env_map +5 checks
   (yaw −X→−Y mirror proof exact; 0.25×0.5=0.125 analytic; byte-
   identical restores). Response appended to PAX3D_FEEDBACK_3.md.

Remaining on all three: game-side adoption. ER statuses updated in
place (`sfb2/documents/ENGINE_REQUESTS/`), README index trued up.

### 4.12 Session Z (2026-07-20) — GPU morphs: fact #15 closed opt-in

The queued "GPU morph path" (the measured character-quality
bottleneck) landed as a pure Python/GLSL prototype per canon — no
build window, works unchanged on stock 1.10 (fact #19):

1. **`set_gpu_morphs(model_np)` / `(np, False)`** — morph sliders now
   render ON the hardware-skinning path. Mechanism: per-vdata RGB32F
   delta texture (ER-003 data-texture contract; position + normal
   deltas per target), a float32 `morph_index` vertex column for
   both-baseline addressing, and a GPU_MORPHS variant of the PBR
   shader composed per-geom at the alpha-mask seam. Slider values are
   read from the Character each frame and pushed as a compact 16-slot
   (row, weight) array — all 52 ARKit targets addressable, ≤16 live
   (the character lane's contract), overflow keeps the largest
   |weight| + warns once. Displacement applies pre-skinning; the
   loader ships no tangent deltas (measured), tangents keep base.
2. **Gate:** test_morph_gltf +5 checks — gpu_renders_morphs (the
   fact-#15 flip, opt-in), gpu_matches_cpu + sparse compose vs the
   CPU valve (rms 0.0000 measured, bar 0.02), byte-identical opt-out
   restore, convert count. 12/12 on Pax3D AND stock × both baselines;
   full gate totals UNCHANGED from Session Y (the row grew
   internally) — @game 71/6/106 Pax3D · 69/6/108 stock; @modern
   70/7/106 · 68/7/108.
3. **Perf (probe_gpu_morph_bench.py, hero_wren.glb = the worst-case
   14,684×52 production head, 8 faces driving 5 sliders each,
   offscreen 512²):** GPU path 1.27 ms/frame total scene (static
   floor 0.97 → **~0.3 ms morph-attributable, meets the 8-face
   ≤0.5 ms acceptance with margin**); CPU valve same scene 63.5
   ms/frame (~50× worse); 32-face stretch datapoint 2.42 ms. Python
   push 0.03 ms/frame for 8×52 sliders. Enable cost (one-time, load):
   1.17 s bake + 18.3 MB delta texture per face — pure-Python column
   slicing; optimize only on evidence (canon).
4. **Known limits (documented, field-evidence-gated):** shadow depth
   pass casts the UNMORPHED silhouette (the alpha-mask depth
   precedent); one PBR variant per geom (glass/mask/terrain do not
   stack with morphs on the same geom); requires the HW-skinning path
   (combining with the CPU valve would double-apply).

Remaining: character-lane adoption (their hero_closeup PS_BENCH=300
A/B re-measures the 185→133 datapoint on the GPU path); texture-
palette skinning + 8-influence option still queued separately (§2 of
the build-window queue) and unblocked by this in one direction —
the GPU morph shader is where a palette texture would also land.

### 4.13 Session AA (2026-07-21) — ER-007 height blend + hex world-anchor, ER-009 cutout alpha

Both arrivals the desk was watching for came in together (terrain dev,
sessions 651/652): the ER-007 height-source answer (height8 authored
into albedo.a library-wide, contract pinned) and a new HIGH ask,
ER-009 (cutout foliage renders solid in the main pass — the grass
understory is pulled from the palettes behind it). Both landed
same-day, pure Python/GLSL, everything opt-in/default-exact-no-op:

1. **ER-007 rider — height-blend sharpening. IMPLEMENTED + GATED.**
   `set_terrain_splat(..., height_blend=True, height_sharpness=8.0)`
   — TERRAIN_HEIGHT_BLEND at the ratified v2 seam. Splat weights are
   resharpened per fragment by a height softmax
   (`w_i · 2^(k · albedo_i.a)`, renormalized): the texel whose
   material stands taller wins the transition, so blend borders follow
   the height texture (grass interlocks with dirt) instead of
   crossfading. The FORM is the contract: equal heights cancel as a
   common factor, so the terrain dev's pinned requirement — an
   ALL-FLAT palette (Deep Desert ships no height maps) must be a
   visual no-op — holds by construction (measured rms 2.6e-06,
   one-hot texels exact); a flat-128 slice inside a height-rich
   palette (beach-sand) competes at its constant middle. Sharpened
   weights drive albedo, ORM AND detail normals (material coherence);
   on the hex path the per-layer taps ARE the blend taps (no extra
   samples), on the plain path it costs 4 extra array taps.
2. **ER-007 adoption follow-up — chunk-border motif seam. FIXED.**
   `set_terrain_splat(..., hex_offset=(u, v))` — per-chunk detail-UV
   offset in base-UV units added before the hex hash, exactly the fix
   shape the terrain dev proposed: cell ids become world-anchored, so
   the per-chunk hash reseam (their `dune_hex_after2.png` x=0 line)
   vanishes when each chunk passes its world offset. Gated by a UV-
   window equivalence check: mesh UVs shifted by δ with offset 0 ==
   mesh UVs 0..1 with offset δ (rms 0.0005).
3. **ER-009 — cutout alpha (grass understory). IMPLEMENTED + GATED.**
   Two engine-side gaps closed in `apply_alpha_masks` (the fact-#17
   seam — the main-pass discard was never missing, its NET was):
   (a) detection now also catches `TransparencyAttrib M_binary`
   (geom-level — the scatter `_proto` rewrite shape — or node-level
   anywhere in the subtree), at M_binary's own engine semantic
   a ≥ 0.5 (cull composes `AlphaTestAttrib(GE, 0.5)` at max priority,
   `cullResult.cxx get_binary_state` — read first, then measured);
   (b) `apply_alpha_masks(np, instanced=True)` compiles the mask
   variant WITH the INSTANCING path — the default variant on a
   set_instanced node hits the measured flag/shader pairing trap and
   collapses every instance onto the origin (now itself a gate
   check). Compat stays bit-identical (same predicate as the cull-
   composed test, rms 0.0). The ER's "shadow pass already discards"
   claim did NOT survive mechanism review: no discard exists in any
   depth path (engine or game shaders grepped), fact #17's depth-pass
   caveat stands (@modern casts the unmasked silhouette), and their
   scatter shadow-excludes everything but boulder tier anyway — the
   observation was likely made against compat content; corrected in
   the ER response rather than silently accepted.
4. **Gate:** test_terrain_splat +14 checks (RGBA-array carry, the
   all-flat contract, softmax analytics k=4 exact 0.9412/0.0588,
   sharpness-0 inert, flat-128-competes k=8 exact 0.9406/0.0594, hex
   compose, hex_offset reseed + world-anchor, opt-outs) — the 24
   pre-existing checks keep their exact pinned numbers (shift-rms
   0.2296, anisotropy 0.19/1.14: the new uniform is byte-neutral.)
   test_alpha_mask +10 checks (M_binary per-baseline split, geom- and
   node-level detection, both-baseline cutout, compat bit-identity,
   the instanced collapse trap measured 0/4→4/4, byte-exact
   opt-outs; instanced phase info-skips on stock 1.10). Full gate:
   totals IDENTICAL to Session Y/Z on all four configs (rows grew
   internally) — @game 71/6/106 Pax3D · 69/6/108 stock; @modern
   70/7/106 · 68/7/108; FAIL sets unchanged. Logs `gate_aa_*.log`.

Remaining: game-side adoption of both (terrain dev: height_blend +
hex_offset kwargs from `splat_dress_fns`, re-enable the pulled
understory classes in `scatter_palettes.json` with
`apply_alpha_masks(proto, instanced=True)` after the M_binary
rewrite). ER statuses updated in place; the "related observation"
(instanced nodes under a state-less parent) stays open pending their
game-side repro — not reproduced in the harness idiom, offer stands.

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| ~~Window 1 build fails~~ | RESOLVED — both builds green 2026-07-17; rollback wheel still sheltered in `wheels_float\` |
| In-game shadow validation disappoints at content scale | The Session E knobs (world bias, PCF, no-cast) + shadow_quality rows exist precisely for this; tune with the testbed, not the full game |
| R4.2 game-side rebasing introduces jitter/regressions | The trap is machine-measured (test_scale); acceptance criterion defined; nested-space dev owns the integration |
| Missing future upstream fixes (severance cost) | Accepted by policy; read-only remote for hand cherry-picks; watch log in CLAUDE.md |
| Doc drift across three repos (engine, sfb2, openworld) | This v3 refresh + `SESSION_LOG.md` + docs index; keep CLAUDE.md's status table current at session end |
| The plan stalls after the fun parts | Same guard as v2: phase gates + the harness; plus the adoption queue names its owners |
