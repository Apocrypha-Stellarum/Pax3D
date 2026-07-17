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
| R0 harness | `tools/paxtest/` — 8 test files, 5 pipelines, 2 GL baselines, analytic checks + instruments | **DONE**; gates everything (Session A) |
| R1 unified renderer | `pax3d_render/` (pax_pbr ⊕ pax3d_simplepbr merge), color contract, `register_scene_camera()` | **Core done** (Sessions B, D — game flag flipped, boots clean). Open: in-game parity eyeball (user), sRGB linearization experiment, GLSL-120 path removal (needs game `gl-version 3 2`) |
| R2 directional sun + shadows | Pipeline-owned DirectionalLight, HPR-driven; shadows with world-space extent center; **hardened Session E**: world-unit bias, 3×3 PCF, no-cast API, skinned casters proven | **Core done + hardened** (test_shadows 12+12 checks, test_shadow_quality 9). Open: in-game validation — set `shadow_bias_world` (~0.5 IEU) first |
| R3 bloom + HDR | F3 root-caused (8-bit intermediate FBOs) and fixed; float fbprops everywhere | **Core done** (Session D; test_bloom green both sizes). Open: content retune, light units, auto-exposure stretch |
| R4 space scale | R4.0 acceptance tests; R4.1 log depth opt-in (`enable_log_depth`, @logdepth row green); R4.2 camera-relative DECIDED (game-side; parent-cancel trap measured); doubles wheel = Window 1 Build 2 (experiment) | **Engine side essentially done.** Open: game-side R4.2 implementation, frustum flip, then sky-camera retirement |
| R5 atmosphere + signature look | Scattering, SH-from-skybox ambient, height fog, lens polish | **Not started** — next feature phase after in-game sign-offs |
| R6 engine surgery | DX9 + dead-backend deletion | **ELEVATED** — `ENGINE_SURGERY_PLAN.md`, Windows 2+ |

Engine C++ changes to date: **one build-system fix** (makepanda oscmd) — plus the
Route A catch-up merge of upstream code (`eb685fd003`, awaiting its build window).

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

---

## 4. The road forward

Ordered by dependency, not excitement — the v2 lesson stands: *measure first,
light before glow, engine truth before content tuning.*

### 4.1 In flight: Build Window 1 (B computer)

The Route A catch-up merge build. Float wheel (required) validates the merge;
doubles wheel (optional Build 2) resumes the R4.2-adjacent experiment. Procedure,
prerequisites, rollback: `BUILD_WINDOW_1_CATCHUP.md`. Until the float wheel passes
the full gauntlet, no surgery and no new C++.

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
4. **sRGB linearization experiment** (R1): testbed G key; decides the input half of
   the color contract, unlocks ACES for real.

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

### 4.4 R5 — atmosphere & the signature look (next engine feature phase)

Unblocked once 4.2's sign-offs land. Content unchanged from v2, priority order:

- **SH-from-skybox ambient** first — highest value per line: both games run flat
  hand-tuned AmbientLights today, and shadow readability is dominated by the
  sun:ambient ratio (openworld's finding). The skyboxes are already float
  textures; simplepbr's IBL machinery (SH irradiance) is in the codebase.
- **Atmospheric scattering** for orbital views (single-scattering analytic limb
  model per planet type; Bruneton LUTs as stretch).
- **Height fog / volumetric media** (~65 lines GLSL, tobspr catalogue) for gas
  giants and nebulae; fold the runtime fog toggle in here.
- Lens flare/dirt polish on the bloom chain.

Gate: aesthetic sign-off per planet type; A/B against the old Fresnel shader.

### 4.5 R6 — engine surgery (ELEVATED; the user wants this soon)

`ENGINE_SURGERY_PLAN.md` is the authority. Window 2 = DX9 removal (588 KB,
19 makepanda refs, zero runtime risk — it never builds). Window 3 = dead
platform backends (mobile/GLES/WebGL/macOS delete; x11/glx hold; tinydisplay
KEEP as the GPU-less CI insurance). Cg deferred — it falls out for free if the
shaderpipeline port ever happens. Deletions only, one themed set per window,
full paxtest gate each time.

### 4.6 Watch: upstream `vulkan` / `shaderpipeline`

Active as of 2026-07-02/03 (shaderpipeline merged into the vulkan branch).
Post-merge, our base sits adjacent to it — a future hand-port is the plausible
next-gen graphics path (and would obsolete Cg + the GLSL-120 machinery wholesale).
Evaluate ONLY when it can run the paxtest suite. No cadence; check when curious.

### 4.7 Backlog (small, owned, waiting for their moment)

| Item | Home | Trigger |
|---|---|---|
| Engine-side shadow texel snapping in `set_shadow_extent` | pax3d_render (Python) | Next shadow session; reference impl = openworld `app.py:_follow_shadow_frustum`; gate with a shimmer test |
| Slope-scaled / receiver-plane shadow bias | pax_pbr.frag | If PCF acne appears at real content scales (physics + margins documented in arch doc §5.2) |
| Runtime fog toggle | pax3d_render | R5 fog work |
| CSM (cascades) | pipeline + shaders | Post-R5, if extent-following stops sufficing |
| Clustered/tiled lights | shaders (+ maybe C++ culling) | Post-R5; openworld's Megacity wants it (781 lamps vs ~6 forward lights) |
| `shaderAttrib.cxx:471` intermittent assert | engine | Needs a repro (fires when a shader reads an unbound input; the known recompile-wipe class is fixed) |
| Planet analytic tangents | sfb2 `planet_factory.py` | When normal-mapped planets arrive |
| GLSL-120 dual-path removal (R1.4) | pax3d_render | The game sets `gl-version 3 2` |
| R2.3 DirectionalLight C++ conveniences | engine | Window 4+, if ever — the pipeline owns orientation |

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| Window 1 build fails on B (first C++17 build; doubles×C++17 never CI-built upstream) | Logs come home; float and doubles fail independently; rollback = sheltered pre-merge wheel + `pre-catchup-merge` tag |
| In-game shadow validation disappoints at content scale | The Session E knobs (world bias, PCF, no-cast) + shadow_quality rows exist precisely for this; tune with the testbed, not the full game |
| R4.2 game-side rebasing introduces jitter/regressions | The trap is machine-measured (test_scale); acceptance criterion defined; nested-space dev owns the integration |
| Missing future upstream fixes (severance cost) | Accepted by policy; read-only remote for hand cherry-picks; watch log in CLAUDE.md |
| Doc drift across three repos (engine, sfb2, openworld) | This v3 refresh + `SESSION_LOG.md` + docs index; keep CLAUDE.md's status table current at session end |
| The plan stalls after the fun parts | Same guard as v2: phase gates + the harness; plus the adoption queue names its owners |
