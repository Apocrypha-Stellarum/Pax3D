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
| R0 harness | `tools/paxtest/` — 32 test files, 5 pipelines, analytic checks + instruments | **DONE**; gates everything (Session A; grown every session since). **Gate matrix redefined Session AC (R1.4, 2026-07-23): the standard gate is both engines × the ONE `game` baseline (= `gl-version 3 2`, mimicking the game); `modern` is a legacy alias; `compat` (no gl-version) is DIAGNOSTIC ONLY.** Canonical totals: **Pax3D 70/7/106 · stock 68/7/108** — identical to the historical @modern column (the bake-equivalence proof); FAIL set = the six documented rows + lighting/none. (Historical 2-baseline totals through Session AB: @game 71/6/106 · 69/6/108, @modern 70/7/106 · 68/7/108) |
| R1 unified renderer | `pax3d_render/` (pax_pbr ⊕ pax3d_simplepbr merge), color contract, `register_scene_camera()` | **Core done** (Sessions B, D — game flag flipped, boots clean). sRGB linearization experiment LANDED gated (Session R — `set_srgb_inputs`, test_srgb, ACES verdict on file). **sRGB flip USER-APPROVED 2026-07-23** (testbed A/B: toggle mechanically verified live — 1 eligible texture = the planet, rms 0.092 over 27.7% of pixels; ACES-vs-Hejl judged subtle-not-worse; parity implicitly signed off same session) and **WIRED game-side same day**: `srgb_inputs` settings key (ON) + init pass-through + boot re-walk after `_load_initial_planet` (set_srgb_inputs converts only current content — late spawns need the idempotent re-call; sfb2 edits uncommitted per convention). **Core flip LANDED same day** (census found plan.py booting COMPAT; `gl-version 3 2` now set in plan.py, main.py — covers launcher modes 2–7 — test3d.py, test3d_ftl.py, and test3d_pax.py where modern is now the DEFAULT with `--compat` escape; planetside already had it; PlanetApp offscreen boot smoke green). **"core signed off" received + R1.4 EXECUTED same day (Session AC): the GLSL-120 dual path is DELETED** — all 16 shader sources baked to native GLSL 330 (nesting-aware conditional resolver, legacy builtins renamed), the shaderutils 120→330 transform + dead IS_WEBGL machinery removed, pipeline emits 330 unconditionally (compat contexts warn loudly and still work — measured), paxtest gate redefined to ONE core baseline + `compat` diagnostic. Gate: **Pax3D 70/7/106 · stock 68/7/108 — identical to the historical @modern column, FAIL sets unchanged** (the bake-equivalence proof). One test fix: test_alpha_mask keyed its compat legs on the baseline NAME, not the context (`use_330`) — compat legs now run only under `--baseline compat`, where all four PASS bit-identical (rms 0.0) with the baked shaders. **R1 IS CLOSED — no remaining items** |
| R2 directional sun + shadows | Pipeline-owned DirectionalLight, HPR-driven; shadows with world-space extent center; **hardened Session E**: world-unit bias, 3×3 PCF, no-cast API, skinned casters proven; **hardened Session G**: glTF caster darkening is a hard assertion, glTF caster+receiver test (angled sun), per-node `set_hardware_skinning()` opt-out; **Session I**: slope-scaled bias (`shadow_normal_bias_world`, opt-in) kills grazing-angle acne (fact 14) | **DONE — USER SIGN-OFF 2026-07-23** ("directional signed off"; the game has run directional+shadows in settings since the planetside era; testbed N-toggle A/B + normal play validated). Harness: test_shadows 13+13, test_shadow_quality 9, test_shadows_gltf 6, test_shadow_grazing 6, test_skinning 12. WATCH ITEM (not blocking, user-flagged at sign-off): shadow STRIPES at certain angles previously reported in planetside, not reproducible in the testbed — when it recurs, capture sun az/el + camera pos; first levers are `shadow_normal_bias_world` (fact 14, grazing-angle acne) and the testbed shadow instruments (keys 10–16) |
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
| 19 | **The GPU morph path needs NO engine change and NO gl_VertexID — it runs on stock 1.10 too.** Morph deltas ride a per-vdata RGB32F data texture addressed by a plain float32 `morph_index` column — one mechanism on BOTH GLSL baselines. **Layout is VERTEX-MAJOR since Session AB** (width = 2×targets: position x=2t, normal x=2t+1; height = vertex rows) — byte-identical to the loader's own interleaved morph array (`[vertex.morph.s, normal.morph.s, …]` tightly packed per vertex, measured on production heads), so when a vdata's column order matches the character slider order the bake is a ZERO-COPY upload of the array's raw bytes (wren/juno: 5/7 vdatas ≈95% of rows; kade's pack orders non-canonically → numpy column gather, pure-Python fallback; all three variants byte-compared in-gate). Two conventions MEASURED before building (TexturePeeker probe): Texture ram row 0 = texcoord v=0, and `set_ram_image_as(data,'RGB')` preserves float component order. Panda ships normal deltas alongside positions (`normal.morph.<slider>` columns — the GPU path is lighting-correct, not position-only). Instrument trap the bench exposed: `apply_freeze_scalar` alone does NOT dirty the bundle — without `force_update()` (or a playing clip) the CPU path re-animates nothing and a perf A/B silently measures an idle scene (the +0.01 ms tell) | Session Z; probe_ram_order (scratchpad), test_morph_gltf `gpu_*` + `bake_fast_matches_reorder` (both engines × both baselines), probe_gpu_morph_bench.py |
| 20 | **Panda Python wrapper identity lies in both directions — key caches by `.this`, never `id()`.** Two lookups of the SAME C++ object return different wrapper objects (`id(a) != id(b)`, `a.this == b.this`, measured), so an `id()`-keyed cache never hits for shared objects — and worse, a collected wrapper's id can be REUSED by a different object (false hit → wrong data bound; the Session Z bake cache carried exactly this latent hazard, fixed Session AB). Same trap inverted: pointer-equality conclusions drawn from `id()` are wrong — Session Z's "copy_to clones share the vdata AND the delta textures" was HALF wrong: `copy_to` on a Character subtree pointer-shares RenderStates and their textures (delta textures ARE shared, `.this`-verified) but DEEP-COPIES the animated vdata (≈ the morph-column bytes per clone in RAM, ~18 MB on a production head). Corollary contract (Session AB): a clone of an enabled template arrives converted-but-puppeted (it inherits the template's `u_morphs` block) — `set_gpu_morphs(clone)` detects the variant states, skips the bake, and gives it its own face | Session AB; probe_identity (scratchpad), test_morph_gltf `copy_*` checks |
| 21 | **Cross-thread Geom destruction vs GVAD handle acquisition corrupts the heap on any wheel that runs mimalloc WITHOUT DeletedChain** — the first attributable native crashes of the fork (planetside chunk mesher, 2026-07-20 + 2026-07-23, both `libp3dtool.dll+0x15a30` in `write_stage_upstream`; the faulting thread is the VICTIM — a second constructor ran over its live object after a freelist double-issue). Single-threaded churn is clean at 97M iterations; stock 1.10.16 immune at 548k (it runs DeletedChain); `workers=1` does NOT mitigate (main-thread destruction is enough). Root regime change: `makepanda.py` set `USE_DELETED_CHAIN=UNDEF` when mimalloc is on, so our wheels were the first ever to run this churn on a general-purpose allocator; two latent upstream defects rode along (cycler stage guards demoted `#ifndef NDEBUG`→`#ifdef _DEBUG` = compiled out at opt-3, and `set_num_stages` freeing `&_single_data` instead of the old array). FIXED 2026-07-24 (GVAD stability window, `d6044b1d8a`): DeletedChain restored alongside mimalloc + guards restored + interior delete fixed; every crashing repro row survives (deep soak 6.9M builds) | GVAD window; `test_gvad_churn` (permanent, FAILed on the pre-fix wheel), `tools/repro_gvad_race/`, `CRASH_GVAD_HANDLE_RACE.md` |
| 22 | **`Thread::bind_thread`'s returned PT(Thread) was the ONLY reference to the bound ExternalThread while the impl kept a RAW pointer in TLS** — every measured consumer (paxcraft, sfb2 `planetside/world/chunks.py`, repro_min's own `_bind`) drops the return value, deleting the ExternalThread under `_current_thread`; heap reuse then poisons `get_pipeline_stage()` and release-mode cycler paths index `_data[garbage]` unchecked → null/junk CycleData → the GVAD-lookalike signature family (worker Geom-construction AV / stage asserts / `_pointer != nullptr`). Crashing is ALLOCATOR LUCK, not thread count — reproduced at workers=2 (the sfb2 envelope) from the paxcraft recipe; minidump: ref() on NULL CycleData (`fetch_add` on 0x8) under `GeomPrimitivePipelineReader` ← `close_primitive`; proof by intervention (keep the PT → full selftest passes; discard → AV in 3 s). Stock 1.10.16 carries the same upstream dangle (measured: AVs on the discard-shape render-churn row) — inherited, never patched by policy. FIXED 2026-07-26 (Session AH mini-window): `bind_thread` ref()s the bound thread — pinned for process lifetime (no portable foreign-thread exit hook; bounded deliberate leak). Corollary on record: the fork REQUIRES `bind_thread` on foreign threads (`thread != nullptr`, threadWin32Impl.cxx:71 — intentional, no auto-ExternalThread fallback like 1.10) | Session AH; `test_thread_bind` (permanent; bind_pinned FAILed rc=1 on the pre-fix wheel), `CRASH_BIND_THREAD_DANGLE.md` |
| 23 | **Per-geom shader variants, the override-2 skinning valve, and the override-1 shadow-camera initial state form an override ROCK-PAPER-SCISSORS no single override number can solve** — the valve must beat the depth camera (its flag must reach the depth pass: 2>1), a variant geom must beat the valve (or `RenderState` parent-override-wins ignores the child attrib WHOLESALE and the geom silently reverts to the base shader — the hero face going flat exactly in face range, gate-measured), and the depth camera must beat the variant (or the color-pass shader leaks into the shadow map — on this fork that's not subtle: the camera initial state drops the render root's ShaderAttrib with ALL its inputs, so a leaked pax_pbr variant ASSERTS `Shader input ... is not present` at draw; under LOG_DEPTH it would also write log-space gl_FragDepth into the linear shadow map). Resolution (ER-014): valve-covered variant geoms are re-stamped AT the valve override with the flag folded in (equal overrides merge — color pass gets both), and shadow casters carry a per-camera TAG STATE (`set_tag_state_key` + shadow attrib at override 3, composed onto the tagged valve node AFTER its own state, `cullTraverserData.cxx`) that re-asserts the depth shader above the stamp while letting the valve's flag ride through (the tag attrib is shader-only — an explicitly-set flag on it would stomp the valve's). Two residue traps closed with it: an EMPTY flag-cleared attrib left at override 2 still blankets everything below (clear_hardware_skinning now removes the attrib when it's trivially empty), and the empty tag-state key fully disables the per-node tag lookup (zero cost at rest) | Session AI; test_detail_maps (`valve_blanket_trap_measured`, `valve_shadow_intact` @directional @logdepth, tag lifecycle checks; rescue disabled → engine assert, proven) |

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
| Clustered/tiled lights (Godot-4-Forward+-class) | shaders (+ maybe C++ culling) | Post-R5; openworld's Megacity wants it (781 lamps vs ~6 forward lights). **Re-asked 2026-07-24 (user + ship lane, fleet-look consult) — direction recorded, still evidence-gated.** Trigger: a real scene wanting >16 real lights on the SAME geometry with measured visual loss (warden pop). Nav-light fleets do NOT qualify — emission blink + ER-013 halos carry them, and the ER-008 warden already buys clustering's cheap 80% (locality). Ingredients when it fires: light lists in data textures (ER-003 `data_texture` carrier, GLSL-330-compatible Doom-2016 style), froxel cull manager prototyped Python→C++ per canon, and shadow decoupling into an atlas (the per-light shadow varying array is the actual 22-light link ceiling) |
| `shaderAttrib.cxx:471` intermittent assert | engine | Needs a repro (fires when a shader reads an unbound input; the known recompile-wipe class is fixed) |
| Planet analytic tangents | sfb2 `planet_factory.py` | When normal-mapped planets arrive |
| GLSL-120 dual-path removal (R1.4) | pax3d_render | (1) ~~flip every entry point to `gl-version 3 2`~~ **DONE 2026-07-23** (plan.py, main.py all modes, test3d.py, test3d_ftl.py, test3d_pax.py modern-by-default with `--compat` escape; boot smoke green, combine warning fired once = the known look-change content); **DONE 2026-07-23 (Session AC)** — entry-point flip + "core signed off" + deletion all landed the same day; 16 shader sources baked native 330, transform + IS_WEBGL deleted, gate redefined to one core `game` baseline (+`compat` diagnostic), totals = the historical @modern column exactly (70/7/106 · 68/7/108, FAIL sets unchanged). R1 closed |
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

### 4.14 Session AB (2026-07-21) — GPU morph crowds: zero-copy bake, independent clone faces

Character-side session, driven by the lane's 2026-07-20 counts entry
(all consumed by Session Z same-day) and by what the shipped
three-hero roster exposed that a single-model bench could not. Probing
before building found two facts that reshaped the plan (fact #20):
`copy_to` does NOT share vdata (the Session Z claim was wrapper-id
artifact — textures ARE shared, vdata is deep-copied), and calling
`set_gpu_morphs` on a clone re-baked 1.17 s + 18.3 MB AND duplicated
the `morph_index` column. All pure Python/GLSL, runs on stock 1.10:

1. **Zero-copy bake (enable cost 1.17 s → 0.07–0.08 s per face,
   ~15×).** The loader stores all 104 morph columns in ONE
   interleaved, tightly-packed array per vdata — which is
   byte-identical to a VERTEX-MAJOR delta texture. The texture layout
   flipped (width = 2×targets, height = rows; shader axis swap), so a
   vdata whose column order matches the character slider order
   uploads its raw array bytes directly. Non-canonical orders (kade:
   5/6 prims) take a numpy column gather (numpy ships with
   panda3d-gltf, so it is present wherever glTF morphs are;
   pure-Python fallback stays). Measured per hero (8-face load):
   wren 0.07 s, kade 0.08 s, juno 0.08 s.
2. **Clone registration — the synchronized-face defect closed.**
   `set_gpu_morphs(clone)` on a `copy_to` clone of an enabled
   template now detects the variant states that came with the copy,
   reuses the pointer-shared delta textures (ZERO re-bake, ~0 s), and
   registers the clone's own CharacterSliders + uniform block —
   without the call, every clone in a plaza wears the template's
   face (they inherit its `u_morphs` block; pre-AB that was the ONLY
   behavior available). Clone opt-out parks a zeroed block (its
   as-copied geom states still carry the variant shader — clearing
   the input asserts at draw; the gate caught this) and never touches
   the template. Also fixed: the bake cache is keyed by `vdata.this`
   (the id() false-hit hazard, fact #20) and `_add_morph_index_column`
   is idempotent.
3. **Gate:** test_morph_gltf +5 checks (17 total per config) —
   `bake_fast_matches_reorder` (zero-copy vs numpy-gather vs
   pure-Python bakes byte-identical AND the fast path stays available
   on loader output — a loader layout change fails loudly),
   `copy_reuses_textures` (pointer-set equality, zero re-bake),
   `copy_drives_own_face`, `copy_ignores_template_sliders` (the
   synchronized-face defect, rms 0.000000), `copy_optout_isolated`.
   17/17 on Pax3D AND stock × both baselines. Full gate totals
   IDENTICAL to Sessions Y/Z/AA on all four configs (the row grew
   internally) — @game 71/6/106 Pax3D · 69/6/108 stock; @modern
   70/7/106 · 68/7/108; FAIL sets unchanged. Logs `gate_ab_*.log`.
4. **Three-hero validation (probe_gpu_morph_bench --hero, all
   measured):** kade 11,650×52 / 6 vdatas / 14.5 MB, wren 14,684×52 /
   7 / 18.3 MB, juno 14,561×52 / 7 / 18.2 MB — all load, bake,
   register, render. 8-face morph-attributable cost re-measured with
   an interleaved min-of-5 A/B (the machine was under variable load —
   single-run deltas drifted 0.4–0.8 ms): **0.19 ms** for 8 faces × 5
   sliders (bar ≤0.5 ms, more margin than Session Z's 0.3). 32-face
   stretch leg upgraded to the honest plaza: every clone registered
   AND independently driven — 4.3 ms (was 2.42 with 24 statues
   sharing one face). 24 clones copy+register in 0.25–0.49 s.

Remaining: character-lane adoption (crowd pattern is now
`enable template → copy_to → set_gpu_morphs(clone)` per clone; the
hero_closeup + PS_BENCH=300 GPU-path re-measure still stands). The
clone-RAM lever (strip morph columns from render vdata, ~18 MB/clone)
stays unbuilt pending evidence that clone RAM matters.

### 4.15 Session AC (2026-07-23) — R1 CLOSED: sign-offs, one graphics reality, GLSL-120 deletion

The program's oldest open phase closed in one day, in three user-gated
steps:

1. **Sign-offs.** "directional signed off" closed R2 (watch item on
   file: planetside shadow stripes at certain angles, not reproducible
   in the testbed — capture sun az/el on recurrence; levers =
   `shadow_normal_bias_world` + testbed instrument keys 10–16). "sRGB
   flip approved" closed R1.3 — the user's "G = no difference" was
   mechanically checked before recording: the testbed scene has exactly
   ONE sRGB-eligible texture (the planet; glTF base color is already
   loader-flagged, flat materials carry none) and it shifted 27.7% of
   pixels at rms 0.092 — real, subtle, approved. Wired game-side same
   day: `srgb_inputs` settings key + init pass-through + boot re-walk
   after `_load_initial_planet` (set_srgb_inputs converts only current
   content; late spawns need the idempotent re-call — game-lane item).
2. **One graphics reality.** Census: `plan.py` had NO gl-version — the
   main game booted COMPAT daily (the Session-R warnings fired in its
   boot). `gl-version 3 2` landed in every entry point: plan.py (covers
   launcher mode 1), main.py (modes 2–7), test3d.py, test3d_ftl.py,
   test3d_pax.py (modern now the DEFAULT; `--compat` escape hatch),
   planetside already had it. PlanetApp offscreen boot smoke: 30 frames
   green, no legacy warning, combine-mode warning fired exactly once
   (the known look-change content). User played a session under core:
   **"core signed off."**
3. **R1.4 deletion.** All 16 shader sources baked to native GLSL 330
   (nesting-aware `#ifdef USE_330` resolver keeps the modern branch;
   legacy builtins renamed texture2D/textureCube/textureCubeLod/
   texture2DArray→texture/textureLod; shadow2D→texture; the exact
   blind varying/attribute swaps the runtime transform performed, so
   compiled text is preprocessor-equivalent). shaderutils transform +
   dead IS_WEBGL machinery deleted; pipeline emits 330 unconditionally
   — a compat context warns loudly and still works (measured).
   **Gate redefined: both engines × ONE `game` baseline (= gl 3 2);
   `modern` = legacy alias; `compat` = diagnostic only.** Totals:
   **Pax3D 70/7/106 · stock 68/7/108 — identical to the historical
   @modern column, FAIL sets unchanged** (the bake-equivalence proof).
   One latent test defect surfaced and fixed: test_alpha_mask keyed its
   compat legs on the baseline NAME (`== 'modern'`) instead of the
   context (`h.use_330`) — first gate run failed those legs under the
   now-core game baseline; fixed, and under `--baseline compat` all
   four compat legs PASS bit-identical (rms 0.0) with the baked
   shaders, so the fixed-function archaeology remains live.

Also this session, before the sign-offs landed: the terrain lane's
state-less-parent repro run 4/4 PASS (their own run had only covered
the 120 fallback — closed, see ER-009), and the flatten consult
(B/C both zero engine changes). Renderer-convergence question from the
game side answered: only mode 1 + planetside run pax3d_render; capital
ship / FPS / diorama modes have NO PBR pipeline — convergence endorsed,
game-side adoption, do it before building new mode content.

Remaining R1 items: **none.** Program-wide: R3 content retune, R4
game-side items, R5 content adoption, R6 Vulkan watch, ER adoption
watches — all evidence- or game-side-gated.

### 4.16 Session AD (2026-07-23) — Effect sprites: baked explosion footage, spawn_effect

Panda3D never did explosions well (the stock particle system is dated,
and there is no volumetric path anywhere in the real-time world — even
UE only imports VDBs since 5.3). The sanctioned game technique is baked
footage on billboards, and the user bought the CGVision "Air and Space
Explosions" pack (28 ProRes 4444 MOVs, 2048×1500, alpha+beauty in one
`yuva444p12le` stream, `C:\python\asset_sources\Explosions\`). Intake
MEASURED the footage premultiplied (RGB ≤ alpha everywhere except a
deliberate additive spark tail; a==0 regions black to 1e-5) — bake
as-is, no unpremultiply, blend `M_premultiplied_alpha`.

**`pipeline.spawn_effect()` landed — a composition of already-gated
parts, zero new shader code:**

- `set_screen(albedo=False, metallic=1)`: black metallic base ⇒
  `diffuse_color` and `spec_color` both EXACTLY 0 in the frag — every
  lit term dies analytically, only emission survives (HDR-legal,
  `emission_scale` feeds bloom). Residuals on record: the f0=0 direct
  Fresnel grazing lobe and the IBL LUT bias term (env-bound scenes) —
  both bounded ≪ emission; field-watch, not blockers.
- `set_glass()`: the GLASS variant + premultiplied blending — emission
  adds at full strength (footage carries its own coverage), fog and
  atmosphere inscatter are coverage-weighted, so haze cannot paint the
  quad's transparent texels.
- `exclude_from_shadows()` when a caster mask is configured (fact #17:
  the depth pass never reads alpha — an un-excluded quad stamps its
  full silhouette).
- `play_flipbook()` + a new `_effects` registry: one-shots self-reap on
  completion through the public clears, so every registry returns to
  empty (byte-identical-when-unused held at rms 0.0 in-gate).
  `remove_effect()` for loops/cancel; game-removed nodes purge their
  dead registrations (the recompile-re-walk trap).

`tools/gen_flipbook.py` grew alpha: ffprobe-detected alpha sources
extract `-pix_fmt rgba`, scaling/assembly preserve the channel, RGB
sources produce the byte-identical 3-channel atlas as before (both
proven in-gate against synthetic frames). Sidecar gains `alpha`; the
paste-ready suggestion becomes `spawn_effect(meta=...)`. The tool's
"2013 ffmpeg" note was stale — the machine runs 8.0.1 (winget); ProRes
4444 alpha decodes clean.

**Gate: new test_effects (13 analytic checks/config: premult composite,
additive glow, opaque core, unlit-under-ambient-×4, billboard vs
rotated parent, one-shot self-cleanup, shadow-mask exclusion, tool
alpha/RGB exactness), runs @game + @directional, PASSES identically on
both engines. Totals now Pax3D 73/7/109 · stock 71/7/111 (+3 PASS +3
SKIP each = the 6 new effects jobs; FAIL sets unchanged, all
pre-existing).**

First adoption same-session (sfb2, uncommitted): `5_1.mov` baked to a
51-frame 12.5 fps 1792×1504 atlas (0.8 MB, `assets/effects/`), and
planetside's `WeaponEffects._begin_impact(fireball=True)` plays it on
NON-ground detonations (launcher/grenade airbursts + map-edge; ground
hits keep the corona+dust read; no pipeline / missing atlas ⇒ old
behavior). Offscreen smoke: bolt expires t=5.00, fireball spawns,
self-reaps t=9.10, registries clean. Structure hits should pass
`fireball=True` when structure collision lands (comment on file).

Retune levers on file: bake fps (12.5 → 25 doubles smoothness and
VRAM), cell size, `EXPLODE_FX_SIZE`/`_EMISSION` in effects.py, and
`depth_bias`/surface-normal offset for future wall impacts. Slice-2
candidates, evidence-gated: soft-particle depth fade, an EFFECT define
zeroing `glass_spec` if the env-ghost residual ever shows, multi-angle
bakes if slow orbiting explosions read flat.

The lane's field guide is `BAKED_EFFECTS_GUIDE.md` (intake facts, bake
levers, the spawn_effect contract, the planetside adoption pattern,
watch list) — hand THAT to a downstream dev, not this section.

### 4.17 Session AE (2026-07-24) — ER-010 wet-sand waterline: set_terrain_water

The terrain half of the Sea-of-Thieves shore look. The water dev's
Session-690 water (per-pixel depth, Beer-Lambert shallows, shore melt,
foam, Gerstner) made the missing piece visible at every beach: the sand
above AND below the contact line rendered identical dry albedo — "dry
beach with a blue film". ER-010 asked for a per-node water contract on
the splat shader; it landed same-day, exactly the suggested shape plus
the stretch goal:

```python
pipeline.set_terrain_water(chunk_np, water_z, band_m=1.0, dark=0.55,
                           rough_mult=0.35, sat=1.25,
                           anim_amp=0.0, anim_period=12.0,
                           anim_scale=6.0, anim_phase=None)
pipeline.clear_terrain_water(chunk_np)   # or water_z=None
```

- **TERRAIN_WATER rider on the splat variant** (6th cache key; the v2
  layer-weight seam untouched — water modifies the OUTPUTS after the
  weights). Wetness by WORLD Z only, all layers alike (wet rock darkens
  like wet sand — no layer coupling): `wet = 1 - smoothstep(water_z,
  water_z + band_m, world_z)`. **Submerged terrain is FULLY wet** — the
  seafloor under the depth-alpha shallows was the ER's headline.
- **Wet look:** albedo × `dark` + chroma expansion `sat` about Rec.709
  luminance (they commute exactly; applied after macro), roughness ×
  `rough_mult` (clamped, ahead of GSAA) — the sheen is a specular read,
  and under an env map the wet band mirrors the sky.
- **Breathing edge (the stretch goal):** `anim_amp` metres of edge
  offset `amp·sin(phase + 2π·noise(world_xy/anim_scale))` — static
  world-xy value noise phase-shifts a shared `anim_period` cycle, so
  the sheen line advances/retreats unevenly along shore. Phase pushed
  from `_update` (O(animated nodes), zero when none); `anim_phase`
  pins it (determinism valve, gate-used). amp=0 EXACT.
- **Contracts, all gated:** every consumer goes through `mix(dry, wet,
  w)` — wet==0 fragments compute the water-off arithmetic bit-exactly
  (dry-region rms 0.0 in-compile, <1e-4 cross-variant); unset nodes
  keep the water-free variant (byte-identical by construction);
  `set_terrain_splat` RE-calls PRESERVE water (chunk re-dressing must
  not silently dry the shore); water before splat raises ValueError;
  clears restore at rms 0.0.

**Gate: new test_terrain_water (17 checks/config: full-wet /
below-waterline / band-mid exact analytics against the wet transform,
dry-above arithmetic identity, re-dress preservation, white-env sheen
comparison 0.737→0.827, five breathing-edge checks, byte-identical
clears + opt-out), runs @game + @directional, identical on both
engines. Totals now Pax3D 75/7/113 · stock 73/7/115 (+2 PASS +4 SKIP
each = the 6 new terrain_water jobs; FAIL sets unchanged, all
pre-existing).**

Adoption is game-side and one call in `materials.py` next to
`set_terrain_splat` (feature-probed per the ER-009 pattern; sea level
already a single float `world.water.water_z`). Suggested start:
defaults + `anim_amp=0.35` on ocean worlds. Engine response filed in
the ER: `sfb2/documents/ENGINE_REQUESTS/ER-010_wet_sand_waterline.md`.

### 4.18 Session AE addendum (2026-07-24) — ER-012 glTF tangent synthesis: filed-as-answered

The ship-intake lane filed a second "ER-010" the same morning (renumbered
ER-012 by this desk; ER-011 = the mesher crash): synthesize tangents at
load time for the 158/246 fleet GLBs whose normal-mapped primitives ship
without TANGENT (Blender refuses tangent export on n-gon meshes; the
intake pipeline rightly refuses to triangulate early). **Answered same
day with a probe, zero engine work: the ask is already the shipped
behavior.** panda3d-gltf 1.3.0 synthesizes per-vertex tangents at convert
time for every UV'd primitive lacking TANGENT (`calculate_tangents`,
Lengyel accumulation + Gram-Schmidt + handedness w) and the model cache
stores the result. Measured on the ER's own meshes
(`tools/probe_tangent_synthesis.py`): SR4 4/5 primitives tangent-less
in-file → **0/5 geoms missing post-load**; Hermes 13/14 → 0/14; Storm
24/24 in-file (and 0 normal-mapped) → 0/24. Mechanism correction on
record in the ER: there is NO draw-time derivative fallback in pax_pbr —
truly missing tangents under USE_NORMAL_MAP render NaN-black, so the
watch item's diagnostic split is *black = tangents actually missing
(loader regression), shimmer/seams = tangent quality*. Genuinely
remaining, watch-gated LOW per the ER's own trigger: mikktspace
exactness and ~0.02–0.5% zero-magnitude tangents at degenerate-UV
vertices. If the trigger fires, the fix is a Python-only post-load pass
in `pax3d_render/`, gated against a reference-tangent GLB.

### 4.19 Session AF (2026-07-24) — the lights slice: ER-013 halos, visibility queries, spot penumbra

The three "now" items from the same-day fleet-look consult, all landed
+ gated in one slice, all Python/GLSL, all byte-identical when unused
(arch doc Session AF section has the mechanisms):

1. **`set_light_halo(np, color, size_m, min_px, intensity)` (ER-013)**
   — camera-facing additive halo quads with a minimum on-screen size;
   depth-tested (occlusion = the depth test, zero occluder
   bookkeeping), never depth-written, shadow-mask excluded, LOG_DEPTH
   composing (recompile-tracked shader); inherits `u_emission_factor`
   so halos flash with their `set_blink` circuit for free. ER-013
   status flipped to IMPLEMENTED + GATED same day it was filed.
2. **`add_visibility_query(np, radius_px, max_occluder_depth)`** (init
   flag `enable_visibility_query`, rebuild-class like SSAO) — the
   flare-occluder retirement: a K×1 depth-tap pass reports each
   target's visible fraction, ~2 frames latent via RTM_copy_ram with
   NO mid-frame stall (the query buffer sorts before the scene and
   reads last frame's depth). Kills the game's ray-sphere occluder
   lists AND fixes sun-flare-through-the-Phobos-hull (the case those
   lists cannot express). Sky-dome valve = `max_occluder_depth`.
3. **`enable_spot_exponent`** (+ runtime setter, recompile-class) —
   the flood-lamp gap from the consult: p3d_LightSource spotExponent
   with GL semantics. Opt-in BECAUSE Panda's Spotlight class default
   is exponent 50 (Light base reports 0 for non-spots) — flag-off is
   byte-identical, exponent-0 under the flag is an arithmetic no-op
   (both gated). Flood recipe: wide fov + exponent 1-4.

Gate: 3 NEW paxtests ×@game(+@directional / +@logdepth) — **totals now
Pax3D 81/7/125 · stock 79/7/127** (+6 PASS +12 SKIP each = the 18 new
jobs; FAIL sets unchanged, identical both engines; all three features
PASS identically on stock 1.10 — pure Python/GLSL). Game-facing
adoption notes: `sfb2/documents/ENGINE_UPDATE_2026-07-24_SESSION_AF_
LIGHTS.md` (halo per bulb = fleet-recipe step 6; flare adoption =
multiply by `q.visibility`, delete the occluder registrations, mind
the sky-dome valve; floods = set exponents deliberately before
enabling the flag). Remaining: game-side adoption only.

---

### 4.20 GVAD stability build window (2026-07-24) — the handle-race fix lands

The queued P0 from `CRASH_GVAD_HANDLE_RACE.md` (user go-ahead after the
2026-07-23 "report only" hold). Fifth C++ build window; first since
Session X part 2. Sequence executed: Session AD/AE/AF backlog committed
(`18a70ea964`, the wheel maps to a clean commit) → the three-site fix
committed (`d6044b1d8a`: `USE_DELETED_CHAIN='1'` alongside mimalloc in
makepanda.py; both cycler stage guards back to `#ifndef NDEBUG`
(live again at opt-3 = the 1.10.16-release regime); `set_num_stages`
frees the OLD array instead of `&_single_data`) → crash baseline
re-proven on the Session-X wheel (AV < 60 s) → `built_x64\` deleted
(dtool_config flag change = mandatory clean build) → full build 11 min
54 s at 20 threads → acceptance. **Acceptance, all green:** every
previously-crashing repro row survives 60 s (full 116k / no-prim 1.0M /
rows-only 3.0M / arraydata-rows 3.9M / handle-only 4.06M /
read-handle-only 4.08M / request-resident 3.96M / workers=1 3.96M
builds; handle-only deep soak 120 s = 6.9M); full gate both engines,
FAIL sets unchanged — **totals now Pax3D 82/7/129 · stock 80/7/131**
(+1 PASS +4 SKIP each = the NEW permanent `test_gvad_churn`, proven
three ways at introduction: FAIL on the pre-fix Session-X wheel — both
rows 0xC0000005 — PASS on stock, PASS on the fix); `test3d_pax
--selftest` + `test3d_ftl --selftest` green; `plan.py` boot smoke alive
at 75 s (only pre-existing content warnings). Wheel installed in
pax3d-env AND system Python (the machine-wide pin), archived
`wheels_gvad\`; rollback = `wheels_session_x\`. Fact #21 records the
mechanism. Game side: ER-011's main-thread-construction mitigation is
no longer load-bearing (relaxation is the game lane's call after field
soak); `ENGINE_UPDATE_2026-07-24_GVAD_STABILITY_WHEEL.md` filed. The
optional poison-on-free diagnostic wheel stays available if a stray
free ever needs naming.

---

### 4.21 Session AH (2026-07-26) — bind_thread dangling-ExternalThread pin (the paxcraft crash)

The paxcraft lane reported worker-thread Geom construction still AVing
on the GVAD wheel (5 bound workers vs a live render). Sixth C++ window,
smallest yet: ONE line. The report was real but mis-aimed — bisection
killed worker count (crashes at workers=2 = the sfb2 envelope), attach,
render state, and every per-frame subsystem; repro_min distillation
would NOT reproduce (allocator luck, the tell). Full-memory minidump
(freeze-filter workflow): ref() on a NULL CycleData under
`GeomPrimitivePipelineReader` ← `close_primitive`. Root cause = fact
#22: consumers drop `bind_thread`'s returned PT, deleting the
ExternalThread under the raw TLS pointer; heap reuse poisons
`get_pipeline_stage()`. Fix: `thread.cxx` pins the bound thread
(`ref()`, process lifetime). 1m32s incremental build. Acceptance:
bind-pin probe UNPINNED(rc=1)→PINNED(rc=2); the 3-second-AV paxcraft
discard shape completes its full selftest twice; `test_gvad_churn`
regression green (2.55M builds); full gate both engines (logs
`gate_bind_*`); NEW permanent `test_thread_bind` (pin contract + the
paxcraft envelope verbatim; SKIPs whole on stock — which AVs on the
discard shape, upstream-inherited, recorded not gated). Docs:
`CRASH_BIND_THREAD_DANGLE.md`, sibling pointer in the GVAD crash doc,
paxcraft `ENGINE_NOTES.md` response, sfb2
`ENGINE_UPDATE_2026-07-26_BIND_THREAD_PIN.md` + `chunks.py`
keep-the-PT one-liner. Wheel archived `wheels_bind_pin\`; rollback =
`wheels_gvad\`.

---

### 4.22 Session AI (2026-07-26) — ER-014 character detail maps (`set_detail_maps`)

The next HIGH in the game's request folder, pure Python/GLSL (no build
window). Characters ship full Normal + ORM sets the globally-off
USE_NORMAL_MAP/USE_OCCLUSION_MAP defines never sample (session-695
field diagnosis: heroes look better in the npc_viewer's
`use_normal_maps=True` preview buffer than in the world); the global
flip stays unsafe (tangentless procedural geometry NaN-blacks — ER-012)
and the user call is characters-only cost scoping.
`pipeline.set_detail_maps(model_np, enabled=True, normal=True,
occlusion=True)` — the ER proposal's name and signature verbatim, so
heroes.py's session-695 hasattr wiring lights up with zero game change
— composes the defines per geom on the apply_alpha_masks pattern:
NORMAL only where a normal-map stage (M_normal/M_normal_height, the
`p3d_TextureNormal` binding set) AND a tangent column exist; OCCLUSION
only where a metal-rough stage exists (M_selector = what the glTF
loader stamps on combined ORM; `.r` read as AO); geoms already
carrying a variant shader (ALPHA_MASK/GLASS/GPU_MORPHS) skipped;
byte-identical restore; lazy per-combo shader cache on the glass
discipline. **The hard half was the CPU-valve composition** — fact #23:
override rock-paper-scissors between valve (2), depth camera (1), and
geom variant, formally unsolvable by override choice alone. Landed
mechanism: `set_hardware_skinning`/`clear_hardware_skinning` now
maintain a valve registry and re-stamp covered detail geoms at the
valve override with the flag folded in; shadow casters get a
per-camera tag-state rescue (shadow attrib @3 on the tagged valve
node, shader-only so the valve flag rides through); empty tag key +
empty registries = byte-identical shipped pipeline, zero per-frame
cost. `clear_hardware_skinning` also stops leaving an empty override-2
attrib behind (a residue blanket that would have swallowed variants
forever). NEW `test_detail_maps` (18 checks default; +4 shadow
interplay @directional; @directional@logdepth = the depth-pass leak
detector), green both engines × all legs; the rescue was FALSIFIED
in-gate (disabled → engine assert `Shader input ... is not present` in
the depth pass — the leak is loud, not cosmetic). Stock-1.10 import
guard: the ORM mode constants getattr-degrade
(M_occlusion_metallic_roughness is 1.11-only). Gate totals move from
the bind-pin baseline 83/7/133 · 80/7/136 to **87/7/136 · 84/7/139**
(+4 PASS +3 SKIP each: the routed pax_pbr adapter runs the new test
too, plus the two directional legs; logs `gate_er014_*`), FAIL sets
unchanged — the same 7 known rows both engines. Rider committed with
it: the prior session's uncommitted `spawn_effect(fade_out=)` end-ramp
(pipeline + 3 test_effects checks, 13→16, green both engines) — found
as working-tree state, gate-proven, committed separately. Docs: ER-014 Engine notes
+ index row (game repo), `ENGINE_UPDATE_2026-07-26_SESSION_AI_DETAIL_MAPS.md`
(game repo), arch doc API row, fact #23. **ADOPTED GAME-SIDE same day
(game s737, `69c8554`, report in the ER's Game adoption section):**
boot counts kade 10 / wren 14 / juno 12 geoms with hair-cutout
ordering intact; juno A/B frames show the gap closed (leather folds,
zipper embossing, brow/nasolabial structure vs the old flat color
blocks) shot with the CPU face valve ON throughout — the valve
composition proven in-game, morphs alive, in-game disable/re-enable
round-tripped 12→12; PS_BENCH filed as unmeasurable (ON↔ON spread 2.0
ms exceeds any ON/OFF delta — scene-level term ≈ 0, per the ER
envelope; caveat on record: selftest camera has heroes mostly
off-frame). Game added a `PS_NO_DETAIL_MAPS=1` kill switch at the
apply site. Hair-under-valve boundary confirmed not applicable today
(morph parts and hair cards are siblings on all three heroes; the NPC
lane will flag us if a rig ever parents cards under a morph part).
ER-014 is TERMINAL; their next filing on its heels = the SSS-skin ER
(NPC_VISUAL_QUALITY Phase 2).

---

### 4.23 Session AJ (2026-07-27) — the voxel-lane trio: photo mode, loud visibility, streaming detail maps

The first session serving the SECOND game: Animal Crossfire (the
Minecraft-style voxel game at `C:\python\paxcraft`) filed three asks in
its `docs/ENGINE_NOTES.md`, and the session also formalized that
arrangement — the voxel game is a sanctioned secondary engine consumer
(user-ratified; CLAUDE.md "Games Served" table is the record, that
ENGINE_NOTES.md file is the standing two-way channel, replies inline).
Space sim first by policy; every item below serves planetside too
(concordance). All three landed same-day, pure Python, no build window.

**1. `render_snapshot` photo mode (their Phase-C AI-building loop; our
photo mode / kill-cam).** `pipeline.render_snapshot(pos, hpr, size,
fov=, near=, far=, shadow_center=, shadow_extent=, filename=)` → a
RAM-backed RGBA8 texture of ONE full-pipeline frame (PBR, shadows,
atmosphere, SSAO, bloom, flare, tonemap — mirroring current config)
from an arbitrary pose, without perturbing the player's view. New
`pax3d_render/snapshot.py`: a persistent offscreen mirror of the post
chain (scene HDR + SSAO pair + bloom extract/down/up + flare + tonemap
into an RTM_copy_ram buffer), inactive except during the shot — the
call deactivates the player chain (window + FilterManager + vis-query
buffers) for exactly one engine frame and restores everything.
Camera-coupled state swapped per shot (camera_world_position, orbital
quads, halo vp height, log-depth coefficient; lens defaults COPY the
main lens). The filing's flagged shadow coupling became a first-class
param: `shadow_center=`/`shadow_extent=` one-frame recentre with exact
restore — both their offered contracts honored. Measured: repeat shots
3–24 ms (their fallback was ~30 s subprocess boots); same-pose parity
vs the window capture rms 0.0; player view rms 0.0. Chain auto-releases
on every rebuild-class toggle (gated through a set_enable_bloom flip)
and on cleanup(). Known limits in the module header (aux-camera
transforms game-owned; viewmodel excluded; no TAA single-frame). NEW
`test_snapshot` (+@directional in run.py): 7 checks default + 10
directional (shadow contract both ways + exact restore + SSAO
flat-identity), green both engines, INCLUDING the routed pax_pbr row.

**2. Visibility queries fail LOUDLY (their Session-5 three-session
trap, promoted to contract).** `pipeline.visibility_query_valid`
property + per-query `.valid`: False whenever a post-main region
clears the scene depth (viewmodel depth_mode='clear', requested or
degraded-to) — while invalid every query reports visibility 0.0
fail-CLOSED with one loud print per transition, instead of confidently
reading the cleared buffer as "open sky everywhere" (flare through
mountains, the old behavior). `register_viewmodel_camera(...,
on_depth_degrade='raise')` makes a degraded 'range' request fatal at
registration; `set_enable_log_depth(True)` now degrades a live 'range'
viewmodel properly (region clear flipped on, loud) instead of leaving
gl_FragDepth clamping silently. +9 test_visibility_query checks
across default/@logdepth/stock legs (stock exercises the
no-set_depth_range degrade).

**3. `set_detail_maps` append-only registration (their streaming-chunk
profile; our streaming content too).** Registration of model N stamps
ONLY model N's geoms (`_stamp_detail_entry`); the old
always-global `_refresh_detail_valve_stamps` tail made per-attach
registration O(total registered) per call — their ~300-chunk terrain
measured gatling remesh 60→32 fps and shipped a 0.3 s/2 s
deferred-batch workaround, now retirable. No-valve removal is
O(entry). The global refresh remains on every path the valve registry
can touch (reconfigure-in-place, removal while valves exist, valve
flips, recompiles — character-lane events). +3 test_detail_maps
checks (stamp-count hook, no-restamp removal, bit-identical survivor),
all four legs green both engines.

Gate: **Pax3D 90/7/139 · stock 87/7/142** (from the ER-014 baseline
87/7/136 · 84/7/139: +3 PASS +3 SKIP each — the snapshot rows; FAIL
sets unchanged, the same 7 known rows both engines; logs
`gate_aj_*`). Docs: CLAUDE.md Games Served section + voxel-lane status
row, arch doc §6.1 note + §9 Session AJ, paxtest README rows, reply
filed inline in paxcraft ENGINE_NOTES.md, sfb2 USING_PAX3D_RENDER §8
quick-ref entries (committed game-side, `bc35e24`).

---

### 4.24 Session AK (2026-07-28) — the far-field consult: `follow=` scene cameras; readback ask queued

The voxel game's Builder Lane (the cliff-monastery dev) filed a
three-part report in ENGINE_NOTES.md: the far-field ask (megastructures
are invisible beyond the ~160 m chunk stream; they want a game-side
static horizon ring + build imposters and needed three engine answers
first), a fresh "+1" on the photo-mode aux camera, and an escalation of
the MSAA edge-on hairline seams. All three answered in-channel
same-day; one small engine feature landed to complete the recipe.

**The far-field answers (the headline — "three answers, not code," and
that is mostly what they got):**

1. **Depth: no problem exists.** The lane is `register_scene_camera`
   background regions on the HDR scene buffer — each region clears
   depth, so the ring camera carries its own lens (e.g. near 50 / far
   6000: 24-bit depth resolves ~1 cm at 3 km, Δz ≈ z²/(near·2²⁴))
   while the world keeps its short far plane. No log depth (their
   flare/viewmodel 'range' constraint untouched), no reversed-z (not
   wired, not needed), no camera-relative rendering. Composite order =
   ascending region sort; recommended layering sky (−100, 'hpr') →
   ring (−50, 'pose', clear_color=None) → world (0). Interaction
   documented, not discovered later: the ring never writes the main
   scene depth, so visibility queries can't see it — a ~20-line
   game-side horizon-altitude flare gate from their own `column_info`
   prescribed if they care.
2. **Cheap material lane: own graph + own ~20-line shader.** A
   separate scene root is never traversed by the main camera, gets no
   PBR inputs, and is never rasterized into the shadow cascade —
   zero cascade budget, no flags. (`exclude_from_shadows` remains the
   valve for under-render subtrees.) Their Session-7 ORM trap is
   structurally impossible on an own-shader ring.
3. **Haze: one system, two consumers.** `set_enable_atmosphere` once;
   `set_atmosphere_params(...)` per frame from their daynight keys
   (uniform-only). The ring shader reproduces the engine's analytic
   aerial-perspective form (quoted verbatim in the reply from
   pax_pbr.frag) with the same values — near-terrain haze and ring
   haze meet seamlessly at the stream boundary.

**Landed: `register_scene_camera(..., follow='pose'|'hpr')`** (the one
missing piece — camera tracking + photo-tour correctness). The
pipeline mirrors the main camera onto follow cameras each frame in
`_update` ('pose' = position+rotation for world-anchored far scenes,
'hpr' = rotation-only sky domes; copied transform applied LOCAL —
parent follow cameras at their scene root). `render_snapshot` re-aims
follow cameras to the snapshot pose for its one frame and restores
exactly — closes the Session-AJ "aux transforms are game-owned"
snapshot limit for follow cameras, and retires the voxel game's
apiserver sky-reparent hack once they migrate their sky off
`app.camera` (required anyway for the layering — their sky currently
draws in the MAIN region and would paint over the ring). Also fixed
while in there: `_update_main_region_clears` now saves and RESTORES
the main region's original clear state when the last background camera
unregisters (used to stay flipped forever). Gate: test_snapshot
section 9, +6 checks (live sync, composite-behind-world, snapshot
re-aim, exact restore, hpr mode, unregister-restores) — green both
engines, both legs; the test's far scene is itself the worked example
of the own-graph ring recipe.

**Photo-mode "+1": answered as already-shipped** (Session AJ landed it
the same day they filed; their own apiserver `/screenshot` already
runs on it). The reply maps their four workarounds (exec-head boot,
viewmodel hide, HUD hiding, selftest save-stomping) onto the shipped
API, plus the sky-hack retirement above.

**MSAA edge-on hairline seams: triaged with a prescription, no engine
work yet.** Mechanism hypothesis: adjacent chunks are separate meshes
under separate transforms → shared boundary corners reach clip space
through different float32 matrix paths → ulp-scale cracks, invisible
face-on, stacked into a full-height line when the shared 16×384 face
collapses edge-on to ~one column; MSAA resolves background through the
crack (their alpha≈232 measurement = minority-sample leak). Resolve-
side engine fixes can't help (can't invent coverage). Prescribed:
game-side A/B — mesh a 3×3 region with WORLD-space verts under one
identity root (voxel corners are integers, exact in float32; one
modelview ⇒ bit-identical clip results ⇒ watertight) and re-shoot the
monastery vantage. If a hairline survives THAT, it comes back here for
a rasterizer look in a build window. Photography workaround today:
render_snapshot at 2× + downscale (4× SSAA).

**Queued, not landed: PBO round-robin framebuffer readback** (their F9
H.264 recorder ask, filed mid-session; sync RTM_copy_ram readback
measured +4.7 ms/frame floor @1600×900). C++/GSG class → build-window
queue row (CLAUDE.md) with their contract (BGRA bytes view, 1–2-frame
latency) and field notes (`RTM_triggered_copy_ram` ~10 ms SLOWER than
continuous on this stack; 8 KB BufferedWriter pipe-write GIL convoy).
LOW priority, their words — batches into the next scheduled window.

Gate: full matrix re-run (`gate_ak_*`), totals unchanged vs Session AJ
(the +6 checks live inside the existing test_snapshot jobs) — Pax3D
90/7/139 · stock 87/7/142, FAIL sets unchanged. Docs: arch doc §6
(follow= + clear-restore), CLAUDE.md voxel-lane row + build-window
queue row, sfb2 USING_PAX3D_RENDER quick-ref (follow=), reply inline
in paxcraft ENGINE_NOTES.md.

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
