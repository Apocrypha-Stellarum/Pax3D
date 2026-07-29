# Handover — Sessions K–P (2026-07-18): the walkable-ship program

**One conversation, six logged sessions**, all driven by the game
integrating the CGTrader Phobos Starhopper (fully modelled interior)
as a walkable, eventually flyable ship — plus the expanded Mars map's
field reports. Everything landed is opt-in with byte-identical
defaults (every test asserts rms exactly 0.0 on opt-out), pure
Python/GLSL — no engine build touched, runs on stock 1.10.16
identically. The paxtest suite grew **14 → 19 test files** and the
full matrix is green on both engines after every commit below.

Engine commits (none pushed): `c6cb35c3fe` glass, `75ab574468`
double-sided, `7466cf93c4` ambient scale, `a8b0993f6a` anim-pin flake
fix, `86e26c5989` specular IBL + BRDF LUT, `2d8a7b7845` +
`caafe88388` + `fdc28288ea` collision design + field triage,
`30187b4b79` local lights, `c272afb270` authored lights + haze guide.
Game-repo (sfb2) doc commits: `a2ddbea`, `c223303`, `f709d43`
(USING_PAX3D_RENDER quick-reference for everything below).

Durable records: master plan §1 (R0/R5 rows) + **§4.8** (the
walkable-ship queue, all rendering rows struck), arch doc §3/§7/§9
(one section per feature), `../WALKABLE_INTERIOR_COLLISION_DESIGN.md`,
`../PLANETSIDE_LOOK_GUIDE.md` §5, SESSION_LOG.md entries K–P.

---

## What shipped

**Session K — glass + double-sided (`c6cb35c3fe`, `75ab574468`):**
- `set_glass(np)` — specular-preserving transparency: a per-node
  `GLASS`-defined compile of the same PBR shader (render-root compile
  textually unchanged = byte-identical by construction) +
  `M_premultiplied_alpha` at override 1 (beats the loader's geom-level
  M_alpha). Alpha attenuates transmission terms only; specular
  (sun/local/IBL) and emission ride full strength. Variant tracks
  recompiles (`_reapply_glass_shaders`); opt-out restores the saved
  TransparencyAttrib exactly. Measured defect: M_alpha loses 2.07× at
  alpha 0.15. PAIR WITH `exclude_from_shadows(canopy)` — the depth
  pass is opaque by design.
- `double_sided_lighting` (init) / `set_double_sided_lighting()`
  (recompile-class) — `!gl_FrontFacing` normal flip after normal
  derivation; covers both sun paths, the light loop, IBL, slope bias;
  glass variants inherit. Front faces BIT-identical under the flag
  (asserted). Opt-in because existing two-sided content (foliage/FX
  cards) WOULD change look — games eyeball first.
- Tests: `test_glass` (6), `test_doublesided` (6), both ×sun-modes.

**Session L — ambient scale (`7466cf93c4`):**
- `set_ambient_scale(np, k)` / `clear_ambient_scale(np)` — inherited
  `u_ambient_scale` input (root default 1.0 = exact no-op) folded into
  the AO factor, which multiplies exactly the indirect terms (SH/IBL +
  flat ambient, glass splits included). Direct light and emission
  untouched — sun shafts and screens still work in a dark hull.
  Interior recipe: ~0.1–0.2 on the interior mesh group.
- Test: `test_ambient_scale` (5; the sun-shaft case measured).
- Also: `test_shadows_gltf` anim pick sorted (`a8b0993f6a`) — the
  fact-#12 residue; the unsorted pick flaked one gate (pose wandered
  0.239/0.415 around the 0.373 threshold); 5/5 at exactly 0.254 since.

**Session M — specular IBL first slice, R5.3 (`86e26c5989`):**
- The REAL split-sum BRDF LUT now ships:
  `pax3d_render/textures/brdf_lut.txo` (128², `tools/gen_brdf_lut.py`
  via pip simplepbr's reference integrator). The old 1×1 WHITE
  fallback made `env_brdf=(1,1)` — harmless only while the env map was
  black; `set_env_map` REFUSES to run on the fallback.
- `set_env_map(cubemap, max_lod=None)` / `clear_env_map()` — feeds the
  until-now-black `filtered_env_map`/`max_reflection_lod` path.
  FIRST-SLICE CONTRACT: the cubemap's mip chain IS the roughness
  ladder (GGX-prefiltered input = correct; enforced mipmap filtering +
  auto box mips = documented approximation). Pair diffuse:
  `set_ambient_sh(sh_from_cubemap(tex))`. Reflections ride full
  strength on glass; damp under ambient scale.
- Test: `test_env_map` (10, max err 0.000 vs the pipeline's own LUT
  peeked at texel centers) — includes the LOD-ladder proof
  (hand-loaded per-mip colors) and the mirror ORIENTATION proof
  (cube sampling is GL-standard: −Y and +Z faces reflect correctly).

**Session N — interior collision design (`2d8a7b7845` + addenda):**
- `../WALKABLE_INTERIOR_COLLISION_DESIGN.md` — AGREED with the ship
  dev. Contract: ship provides a hidden low-poly collision subtree;
  walk mode queries it with a traverser inside ship bounds; ground =
  `max(walkmesh, heightfield)` (automatic ramp handoff); door/ramp
  collision rides the animated part nodes. NO engine code needed.
- `tools/paxtest/probe_walkmesh.py` (7/7 both engines) — doubles as
  the reference implementation (`geom_np_to_collision` + query/pusher
  rigs). Two corrected assumptions: segment-vs-polygon is
  DOUBLE-SIDED (floor winding cannot break the ground query; winding
  only sets pusher direction), and same-frame procedural joint reads
  need `Character.force_update()`.
- Field triage on the shipped `phobos_starhopper.glb` (doc §7–8):
  `COLL_floor` converts fine (1366 polys, correct deck hits) — the
  fall-through is loader/walk wiring (checklist in §7: conversion not
  run / name drift `COLL_floor` vs the agreed `phobos_collision`;
  `hide()` never `stash()`); the RAMP has no collision piece
  (boarding-threshold fall); wall blockers DON'T EXIST in the GLB yet
  — pusher proven against the real Int_Walls shell but author low-poly
  `block_*` quads (2.3 ms/frame vs the 27k-poly shell, slivers,
  thin-wall escape — all measured, §8).

**Session O — local lights measured (`30187b4b79`):**
- No engine change: the p3d_LightSource point/spot loop was the LAST
  never-measured lighting path. `test_local_lights` (6→9): point
  analytics exact, quadratic attenuation exact, per-room `set_light`
  scoping, spot cone, and the interior recipe (lamp full + damped sky)
  composing to 0.002. Gotchas: Panda default attenuation `(1,0,0)` =
  NO falloff; `max_lights` per state (planetside runs 10); no
  local-light shadows (point shadows explicitly disabled); emissive
  strips glow but don't illuminate.

**Session P — authored lights + haze root-cause (`c272afb270`):**
- `activate_model_lights(model, root=None, scale=1.0,
  include_directional=False)` / `deactivate_model_lights(model)` —
  closes "Blender lights don't work": panda3d-gltf converts
  KHR_lights_punctual into REAL light nodes (units: color·I·4π/683,
  attenuation (1,0,1)); they were simply never `set_light`-ed.
  Directional excluded by default (the pipeline owns the sun); `scale`
  ~0.05–0.3 tames physical units; deactivation restores colors/scopes
  byte-identically. Tests: `test_local_lights` 7–9 (synthesized KHR
  asset: inert rms 0 → analytic 0.219/0.220 → restore rms 0).
- Expanded-map field reports root-caused (NO engine defect — both haze
  systems are camera-relative by construction): "haze centered on the
  map middle" = the exponential height medium amplifying density
  e^{158/50} ≈ 24× in the −158 m valleys below the `base_height=0`
  datum, on top of `density=0.0018` eating 99% at 2 km by original
  design. Retune recipe + three presets:
  `../PLANETSIDE_LOOK_GUIDE.md` §5 (raise `scale_height` to ~3× the
  terrain span, re-datum `base_height` to mid-terrain, density by
  target visibility; all live-tunable). The "hard wall" is the game's
  own `half_extent` clamp (by design; raising it extends the
  heightfield rasterizer with it).

**Also established (flight prep, no code):** camera lock aboard a
flying ship = scene-graph parenting (player+camera+collision under the
ship node; never per-frame transform copying — that's the one-frame-
lag jitter class). Long-range flight is the already-decided R4.2
anchor-relative work with the SHIP as anchor; log depth + the measured
traps in test_scale are the engine half, already landed.

---

## Load-bearing decisions (keep these)

1. **The byte-identical opt-out contract held for every feature** —
   via textually-unchanged default compiles (glass), exact-noop
   uniforms (ambient scale ×1.0), refused-degenerate states
   (set_env_map vs the fallback LUT), and saved-state restores. It is
   the bar for all future work.
2. **Per-node variants must track recompiles** — `_reapply_glass_
   shaders` extends the §3 input-preservation invariant; any future
   per-node shader variant needs the same hook.
3. **The depth pass is deliberately untouched by glass** (shadow
   camera's override-1 initial state outranks node shaders) —
   `exclude_from_shadows` is the intended pairing, not a bug.
4. **DirectionalLights from assets stay inert by default** — the
   pipeline owns the sun in both modes.
5. **The env-map mip chain IS the roughness ladder** until the GGX
   prefilter tool exists — approximation documented, not hidden.
6. **Collision is game-side by design** — the engine contributes the
   measured contract + reference recipe, no new code. Panda facts on
   file: double-sided segment tests, pusher one-sidedness,
   force_update.

## Priority queue for the next session

1. **Field follow-ups first (blocked on the ship/planetside devs, not
   us — chase reports):** fall-through wiring checklist (design doc
   §7) + ramp/wall blocker emission (§8); haze retune choice (look
   guide §5 presets) + `half_extent` raise; adoption of set_glass /
   double-sided eyeball / ambient scale / env map / activate_model_
   lights on the actual ship. Expect new field reports — triage
   against the measured records before touching the engine (fact #11).
2. **GGX prefilter tool** — the one honest gap in the reflections
   story (box mips → correct prefiltered chain; pip simplepbr's
   EnvMap/prefilter machinery is the reference to borrow, same as the
   BRDF LUT). Promotes `set_env_map` from approximation to correct.
3. **sh_from_cubemap file-orientation check** — half-settled (shader
   sampling proven GL-standard in test_env_map); the open half is how
   Panda orients faces when loading skybox IMAGE FILES. One synthetic
   skybox-file test closes it.
4. **R5 spaceflight remainder** — orbital scattering (analytic limb
   model per planet type), lens polish. Unblocked, unclaimed.
5. **R4.2 support when the ship flies far** — game-side per the
   decided plan (ship-as-anchor rebasing); engine consults + the
   test_scale traps are ready. Likely triggered the moment the ship
   dev wires flight.
6. **Watch the light budget** — activated ship lights + street lights
   will eventually press against per-state `max_lights`; that's the
   trigger for the backlogged clustered/tiled lighting (§4.7), not
   before.
7. Unchanged long-tail: R6 Window 4 (user-scheduled build window),
   GLSL-120 removal (needs game `gl-version 3 2`), sRGB input
   linearization experiment, R3 content retune.

## Operational notes (the ones that keep biting)

- No rebuild needed for ANY of this; both games live-load
  `pax3d_render/` — uncommitted shader edits hit them instantly.
- `tools/gen_brdf_lut.py` needs pip simplepbr (dev-time only; the .txo
  artifact is committed).
- The games' live copy of openworld is now `C:\python\sfb2\planetside`
  (sfb2 Session 610); asset packs paxtest reads are still at
  `C:\python\openworld\3D assets\`.
- Full-matrix gate: `run.py` on BOTH pythons, sequentially (shared
  output dir). The only expected FAILs are the six documented
  baselines (retired-pipeline bloom/rebuild, rebuild/pax_pbr F4,
  scale R4 default rows).
- `hide()` vs `stash()`: stashed nodes are skipped by the collision
  traverser — the silent killer in collision wiring.
