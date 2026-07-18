# Handover — Session Q (2026-07-18): field service done; next, the two-front field + R5 spaceflight

**From Session Q** (one session, field-response focus). Everything below
is written to be executed SEQUENTIALLY, in phases — Phase 1 is
non-negotiable before any building; Phases 2–4 are the build work in
priority order; Phase 5 is standing watches. Read `SESSION_LOG.md`
(Session Q entry) and `OPENWORLD_FEEDBACK_RESPONSE_5.md` for what just
happened; the K–P handover (now historical) for the walkable-ship
program background.

**State of the world:** engine commits `726aa2a93f` (probe),
`239b4a717c` (sh face-table pin), `b6325a727b` (GGX prefilter tool),
`206fd2b636` (docs/Response 5); sfb2 doc commit `97be3a2` (west-sun P0
pointer). None pushed. Full 19-test matrix green on both engines after
every commit: 43 PASS / 6 documented FAILs / 57 SKIP, identical stock
vs Pax3D. The R5 planetside half AND the whole skybox → ambient +
reflections chain are now proven end to end (prefilter tool + pinned
face table). The engine side of the walkable-ship program remains
complete; adoption is the game's move.

---

## Phase 0 — Orient (15 minutes, do not skip)

1. `git -C C:\python\pax3d log --oneline -8` and `git status` — verify
   the tree is clean and matches the commits above (fact #11: never
   trust a field report measured against a dirty tree).
2. Check for NEW field material — all three places, newest first:
   - `C:\python\openworld\PAX3D_FEEDBACK_2.md` (and a possible `_3`) —
     the openworld dossier chain;
   - `C:\python\sfb2\documents\HANDOVERS\` and
     `documents/PLANETSIDE/` — the planetside unification thread
     (Phase 3 procedural surround is IN FLIGHT there; Session 614
     bench spike passed: 25 CPU-meshed chunks at 311 fps under
     pax3d_render);
   - `git -C C:\python\sfb2 log --oneline --since="2026-07-18"`.
3. If anything rendering-related is reported, Phase 1 starts now. If
   the field is quiet, skim Phase 1's "what to expect" anyway (so you
   recognize reports when they land mid-session), then go to Phase 2.

## Phase 1 — Field triage (FIRST, always; two streams now)

The standing rule: triage against the measured records before touching
the engine. Reproduce on a clean checkout + current wheel. If a claim
matters, write a paxtest check for it. Do not build game-side
workarounds for engine problems or engine features for game problems.

### Stream A — walkable ship / Mars colony (adoption reports due)

Everything they need is landed and documented; expect reports of five
kinds, with the records to triage each against:

1. **West-sun P0 A/B** — they now know the fix exists (Session Q wired
   it into `USING_PAX3D_RENDER.md` and their handover):
   `set_shadow_normal_bias(0.25)`. If their A/B is unsatisfying:
   sweep 0.15–0.5 before concluding anything; remember their config
   (`shadow_bias_world=0.18`, extent radius 140 / depth 600, 4096²,
   PCF 3) and that too-large values erode real umbras —
   `test_shadow_grazing` has the teeth check; the varied-terrain proof
   is `probe_openworld_scale.py --normal-bias`. Records:
   `OPENWORLD_FEEDBACK_RESPONSE_4.md`, fact #14.
2. **Ship feature adoption** (glass / double-sided / ambient scale /
   env map / authored lights) — recipes are in `USING_PAX3D_RENDER.md`
   and arch doc §9. The traps that will actually get hit:
   `set_glass` without `exclude_from_shadows(canopy)` (opaque depth
   pass by design); ambient scale on the WHOLE ship instead of the
   interior mesh group; `activate_model_lights` without `scale`
   (physical units are bright — 0.05–0.3); `set_env_map` on a raw
   cubemap (works, box-mip approximation) vs the correct
   `gen_env_prefilter.py` bake.
3. **Collision wiring** (fall-through / ramp / walls) — ALL measured,
   NO engine work: `WALKABLE_INTERIOR_COLLISION_DESIGN.md` §7
   (checklist: conversion actually run; name drift `COLL_floor` vs
   `phobos_collision`; `hide()` never `stash()` — stashed nodes are
   invisible to the traverser) and §8 (ramp has NO collision piece;
   wall blockers don't exist in the GLB — author low-poly `block_*`
   quads, 2.3 ms/frame measured against the 27k-poly shell).
4. **Haze retune choice** — they pick a preset from
   `PLANETSIDE_LOOK_GUIDE.md` §5; the valley fix (scale_height +
   base_height re-datum) is non-negotiable, density is aesthetic.
   Remember their lesson already in the guide: scale both haze colors
   by day-cycle luminance.
5. **TextureStage follow-up** — if they ask for help with the explicit
   GLSL dome shader (their planned fix), support it; the diagnosis is
   closed (`OPENWORLD_FEEDBACK_RESPONSE_5.md` §1,
   `probe_texturestage.py`). Do NOT reopen the engine question; the
   C++ warning is queued for Window 4, not for now.

### Stream B — Phase 3 procedural surround terrain (NEW ask source)

They are meshing 4 km terrain chunks as plain Geoms with PBR materials
under pax3d_render, streaming around the player, blending procedural
surround into hero heightfields. Their engine-dev-on-call banner is up.
Likely ask classes and first responses:

- **Chunk-edge seams / normal margins** — their own
  `PROCEDURAL_TERRAIN_SYSTEM/PITFALLS.md` #18/#20 covers this
  game-side (generate normals with a margin row); only if a seam
  survives correct margins does it become an engine question.
- **Culling / OmniBoundingVolume** (#9) and **mesh-res faceting**
  (#17) — game-side pitfalls, pre-answered in their doc.
- **Terrain material APIs** — v1 is tinted albedo + detail textures
  through standard materials; if they ask for splat/layer blending,
  that is a REAL engine feature discussion — scope it, don't improvise
  it mid-session (a per-node shader variant like GLASS is the likely
  shape; remember load-bearing decision: variants must track
  recompiles via the `_reapply_glass_shaders` pattern).
- **Perf** — the bench says 311 fps at 25 chunks; treat any perf
  report against that baseline, and remember the Language Canon:
  no C++ promotion without a profile showing Python hot.

### Also possible from either stream
- A skybox/env map adoption question → Phase 3 below IS the answer;
  pull it forward if asked.
- Anything about flying the ship far → Phase 5's R4.2 trigger; consult
  from the decided plan, engine half is ready.

**Exit criteria for Phase 1:** every open report answered or reproduced
+ root-caused, response doc updated (`OPENWORLD_FEEDBACK_RESPONSE_*` /
game-repo docs), gates still green. Only then build.

## Phase 2 — Orbital scattering (R5.5): the main build item

The last big unclaimed R5 piece — the spaceflight half of the
signature look. Planet limb glow, atmospheric halo, terminator tinting
seen from orbit/space. Master plan scope: **single-scattering analytic
limb model per planet type** (Bruneton LUTs explicitly a stretch goal,
NOT the first slice).

Design constraints (from the R5 pattern that worked):

1. **Opt-in, default-off, byte-identical** — new
   `enable_orbital_scattering` (or an explicit mode on the atmosphere
   system; decide early and document which). Every prior feature's
   opt-out asserts rms exactly 0.0 — same bar.
2. **Decide the boundary with the planetside haze FIRST.** The
   in-atmosphere system (R5.1) is camera-relative exponential-height
   haze on scene geometry. The orbital view is a different regime:
   the atmosphere seen as a shell around a sphere from outside. First
   slice should be the ORBITAL side only (limb on/around the planet
   geometry), with the handoff altitude documented, not solved —
   a continuous fly-down is R4.2-era work, don't gold-plate it now.
3. **Analytic and testable:** for an exponential atmosphere over a
   sphere, per-ray optical depth has closed-form/Chapman
   approximations; whatever form the shader uses, the paxtest computes
   the same integral independently (numerically is fine) and asserts
   the rendered limb profile matches — the test_atmosphere shape
   (three-distance transmittance analytics) adapted to limb geometry.
4. **Per-planet params as uniforms** (live-tunable, uniform-only):
   scatter tint (Rayleigh-ish RGB), density/scale height, planet
   radius, atmosphere thickness, sun direction (already have),
   intensity. Blackbody sun tint composes from the game's context
   (their Phase 2 derives it — don't duplicate).
5. **Where it renders:** decide early — on the planet sphere's
   material (a variant compile, GLASS-pattern) vs a billboard/shell
   pass. Prototype the cheapest correct thing; the testbed
   (`test3d_pax.py` — sun/planet/station scene) is the eyeball rig.
6. **Gates:** new `test_orbital` (or `test_atmosphere` extension):
   limb transmittance analytics, sunward vs anti-sunward asymmetry,
   opt-out rms 0, both engines × both baselines. Doc: arch doc §9
   subsection + master plan R5 row + look guide sibling section for
   space ("ORBITAL_LOOK" section or extend the planetside guide).

Lens polish (flare/dirt on the bloom chain) stays queued BEHIND
scattering — do not start it in the same session unless scattering
lands early and green.

## Phase 3 — Worked skybox → environment example (small, high leverage)

The chain is proven but unused: nobody has pushed a REAL skybox
through `gen_env_prefilter.py` + `set_env_map` + 
`set_ambient_sh(sh_from_cubemap(tex))` yet. Close that:

1. Pick a real asset — the openworld village skyboxes
   (e.g. `006_Sunset.hdr`-derived) or the game's space skybox. NOTE:
   if the source is an EQUIRECT panorama (not six faces), conversion
   is out of the tool's scope by design — pip simplepbr's `hdr2env` is
   the reference to borrow if this becomes the session's small tool
   extension (same borrow-and-verify shape; budget an hour, not a
   day).
2. Bake, wire it in `test3d_pax.py` behind a hotkey, screenshot A/B
   (off / env-only / env+SH). 64px/32-sample bake is 2.6 s; a
   committed sample .txo is ~400 KB — fine to ship as a testbed asset.
3. Write the recipe where adopters look: `USING_PAX3D_RENDER.md` ship
   package section + look guide. One paragraph each, pointing at the
   pinned face table (up-face image top row = SOUTHERN sky) so nobody
   re-derives orientation.
4. Known content caveat to carry into the recipe (from the game's own
   validation): 006_Sunset's baked sun sits SOUTH at their dome
   rotation — check a skybox's sun azimuth before tuning SH ambient
   to the sunset pool.

## Phase 4 — sRGB input linearization EXPERIMENT (only if time / field quiet)

The oldest R1 leftover, and it now gates more than it used to: the
ACES wash-out (fact from Session A: inputs sampled raw, NOT a tonemap
bug), the R3 content retune, and physically-honest env maps all trace
here. Experiment shape, strictly opt-in:

- A pipeline flag (e.g. `srgb_inputs=True`) that flips BASE COLOR (and
  emission) textures to sRGB texture formats so hardware linearizes at
  sample time. Normal / metal-rough / AO / LUT stay linear. Nothing
  else changes — tonemap output side is already display-referred.
- Gate first: paxtest check — an 0.5-sRGB-encoded texture card must
  render at the analytic linearized value through each tonemap curve;
  opt-out rms 0. Then testbed A/B screenshots, INCLUDING an ACES pair
  (the prediction on record: ACES stops looking washed out when inputs
  are linear — verify or kill that claim).
- **Blast radius warning:** all game content is tuned around raw
  sampling + Hejl-Dawson. This session produces the flag, the gate,
  and the A/B evidence — the DEFAULT never flips without game-side
  sign-off, and the prefilter tool's raw-value note
  (`gen_env_prefilter.py` docstring) must be updated in the same
  commit if the contract ever changes.

## Phase 5 — Standing watches (no proactive work)

| Watch | Trigger | Prepared state |
|---|---|---|
| **R6 Window 4 build day** | USER schedules it (never mid-session) | Queue in CLAUDE.md: mobile app glue deletion, the core-profile combine-mode warning (Session Q, response 5 §1), R2.3 DirectionalLight conveniences |
| **R4.2 ship-as-anchor** | The Starhopper actually flies far | Decided plan: scene-graph parenting for the camera lock (never per-frame copying), ship-as-anchor rebasing; engine half ready (log depth, test_scale traps); engine CONSULTS, game leads |
| **Clustered/tiled lighting (§4.7)** | Field reports pressing per-state `max_lights` (ship lights + street lights) | Backlogged deliberately; do not build early |
| **GLSL-120 dual-path removal** | Game flips to `gl-version 3 2` | Session Q's core-profile findings ARE the migration checklist: FFP-emulation content (combine-mode sky domes etc.) silently changes under core — game needs explicit shaders on those first. Game-paced |
| **Vulkan** | Upstream `vulkan` branch becomes paxtest-runnable | Watch only |

## Operational notes (the ones that keep biting)

- No rebuild for ANY of this — Python/GLSL only; both games live-load
  `pax3d_render/`. C++ (the warning, R2.3) waits for Window 4.
- Gate = `run.py` on BOTH pythons sequentially (shared output dir).
  Expected FAILs are exactly the six documented baselines
  (retired-pipeline bloom ×2, rebuild ×2, scale R4 default rows ×2) —
  a seventh FAIL is real, a fifth PASS-that-was-FAIL means check the
  baselines.
- `gen_env_prefilter.py` / `gen_brdf_lut.py` need pip simplepbr
  (dev-time only; both envs have it). test_env_map's tool checks
  INFO-skip without it — INFO is not a failure.
- Asset paths: live planetside app = `C:\python\sfb2\planetside`;
  frozen openworld checkout (dossiers, repro commands, asset packs) =
  `C:\python\openworld`. Their repro commands run FROM the openworld
  checkout.
- `PYTHONUTF8=1` when redirecting game smoke-test output (cp1252
  crash on `→` prints); paxtest check strings are ASCII-safe as of
  Session Q — keep new ones that way.
- sfb2 tree carries heavy concurrent-session churn — stage ONLY your
  files, verify each diff hunk is yours before committing (Session Q
  precedent).
- `hide()` vs `stash()`: stashed nodes are skipped by the collision
  traverser — still the silent killer in collision wiring reports.
