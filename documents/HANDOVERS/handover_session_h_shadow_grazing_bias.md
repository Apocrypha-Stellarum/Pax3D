# Handover — Session H (2026-07-18): grazing-angle shadow bias

**One focused piece for the next session: implement slope-scaled
(normal-offset) shadow bias, opt-in, paxtest-gated — but METRIC FIRST.**
Read `../PAX3D_MASTER_PLAN.md` and the openworld P0 addendum
(`C:\python\openworld\PAX3D_FEEDBACK.md`, the 2026-07-17 afternoon
section) before starting.

Engine is CLEAN and RESTORED — no build needed, everything is
Python/GLSL. The debug instruments + probe from this session are
committed (`bc1f6353b1`). No C++ was touched all session.

---

## First: a regression I caused and fixed (so you trust the tree)

Mid-session I added a `shadow_slope_bias()` GLSL function that referenced
an **undeclared** uniform `u_shadow_slope_bias`. That is a hard shader
compile error → the PBR program fell back → **shadows AND hardware
skinning both vanished in-game** (skinning shares the program). The game
live-loads `pax3d_render/` from `C:\python\pax3d`, so the uncommitted
edit hit the game with no rebuild. **Fixed and verified** (paxtest
shadows 13/13 + skinning 12/12 green, in-app village shows shadows +
posed NPCs). Lesson for you: any uniform a shader references MUST be
declared in the shader AND pushed by the pipeline before that shader
runs — do both in the same edit, then run `run.py --tests shadows` once
immediately.

---

## The diagnosis (single coherent hypothesis — verify before trusting)

**The direction-gated failure is very likely one root cause: insufficient
receiver depth-bias at grazing sun angles.** The evidence chain:

- Openworld's own signature: shadows fade/vanish in a **western low-sun
  cone** (alt ≤ ~40°, az ~240) with **fine terracing/acne bands on open
  ground**; the eastern mirror at the same altitude is clean. Error
  grows ~**1/tan(alt)**. That 1/tan(alt) is exactly the slope term of a
  receiver grazing the light.
- The terracing you can see yourself: user's Wild West capture
  (`C:\screencaps\capture_1784290543.png`) and this session's mode-14
  renders (`tools/paxtest/output/owscale_card_m14_*`) — the open ground
  is banded.
- **Why acne reads as "vanishing":** when self-shadow acne covers open
  ground at grazing angles, average ground luminance drops and a real
  cast shadow on top of half-shadowed ground **loses contrast** → "the
  shadow disappeared." Acne and vanishing are the same defect.
- **Why the azimuth asymmetry:** the village/desert terrain slopes are
  not symmetric (the village valley opens west — see
  `tools/paxtest/output/overhead_z240.png` vs `overhead_z120.png`). West
  sun grazes more terrain → more acne → more contrast loss. Same alt,
  mirrored az, different terrain interaction.

## What is ALREADY ruled out (don't repeat — evidence on file)

- **Not our C++ / not the R6 surgery:** failure is byte-identical on
  stock Panda 1.10.16 and Pax3D. (Run the probe under both:
  `C:/Python313/python.exe` vs `C:/python/pax3d-env/Scripts/python.exe`.)
- **Not the GPU driver:** user updated it mid-session; artifacts
  unchanged, probe m11frac identical (0.107/0.317), GL 0x502 errors
  persist. (Task #4.)
- **Not shadow-frustum coverage / caster missing from the map:** the box
  footprint is full-length in the extracted depth map at BOTH azimuths,
  and the skinned actor writes ~96 depth texels at both — the casters
  ARE captured. So it is a receiver-compare problem, not a
  map-population problem.
- **Not the receiver coordinate / varying interpolation:** debug mode 12
  (interpolated vs CPU-recomputed shadow coord) measured **0.000**
  across the frame; mode 13 (recomputed path) is pixel-identical to
  mode 11. The coordinate arriving at the compare is correct.
- **Not daynight alt/az→vector, follow-frustum, PCF 1v3, max_lights,
  NPCs, per-frame ordering, walking vs pinned pose** — all swept, no
  effect.

**Honest caveat:** the standalone probe's luminance-ratio metric produced
several FALSE "NO SHADOW" verdicts (sample-point geometry + perspective
foreshortening + a receiver card buried under terrain). The cleanest
trustworthy signal this session was the **overhead-orthographic village
render**. Do not trust the ratio column until you fix the metric (step 0).

---

## THE PLAN — do these in order

### Step 0 — build ONE trustworthy metric (do this FIRST)
The ratio-at-a-guessed-point approach failed. Replace it with an
**overhead orthographic** measurement:
- Main camera orthographic, looking straight down (`--ortho-cam` already
  exists in `probe_openworld_scale.py`).
- Known flat receiver + known caster at a known world position.
- Measure the **mode-11 black fraction inside a precomputed screen
  rectangle** where the umbra MUST fall (project the caster's base +
  `caster_height/tan(alt)` along the anti-sun horizontal; that rect is
  deterministic under ortho — no foreshortening, no guessing).
- Also measure **acne fraction on open ground** = fraction of a
  known-lit, caster-free ortho region whose mode-11 term < 0.9.
Acceptance instrument = (umbra_black_fraction, open_ground_acne_fraction).

### Step 1 — reproduce cleanly with that metric
Sweep sun altitude 60→30 at az 120 vs 240 over **real village terrain**
(the flat card is too clean — the terrain slopes are the trigger).
Expected: acne_fraction rises as alt drops, faster at az 240; umbra
contrast falls in lockstep. If this does NOT reproduce the asymmetry,
STOP — the hypothesis is wrong (see kill-switch below).

### Step 2 — implement slope-scaled bias (opt-in, world units)
GLSL (`pax3d_render/shaders/pax_pbr.frag`):
1. Inside `#ifdef ENABLE_SHADOWS`, declare
   `uniform float u_shadow_normal_bias;` (normalized-depth units, already
   divided by extent depth by the pipeline — mirror `global_shadow_bias`).
2. Split the bias back out (this session's `_biased` refactor was right;
   it just needs the uniform wired):
   `float shadow_caster_contrib_biased(sampler2DShadow m, vec4 p, float bias)`
   and keep `shadow_caster_contrib(m, p)` calling it with
   `global_shadow_bias` for back-compat.
3. At the call site (`pax_pbr.frag` ~line 355, inside the light loop):
   `n` (view normal) and `l` (view toward-light) are in scope, and
   `dot(n, l)` = NdotL. Compute
   `float ndl = clamp(dot(n, l), 0.0, 1.0);`
   `float slope = sqrt(max(1.0 - ndl*ndl, 0.0)) / max(ndl, 0.15);` // tan θ, clamped
   `float bias = global_shadow_bias + u_shadow_normal_bias * min(slope, 8.0);`
   then call `shadow_caster_contrib_biased(..., bias)`.
   (View-space NdotL == world-space NdotL; the angle is frame-invariant.)

Pipeline (`pax3d_render/pipeline.py`):
1. `__init__` kwarg `shadow_normal_bias_world=0.0` (default 0 = OFF =
   byte-identical legacy — honor the "opt-in until proven" rule).
2. In `_push_shadow_bias()` push
   `u_shadow_normal_bias = shadow_normal_bias_world / max(_shadow_depth, 1e-6)`
   (same world→normalized scaling as `shadow_bias_world`, so it stays
   physically constant across extent changes — this is the trap that
   already bit the plain bias).
3. Runtime setter `set_shadow_normal_bias(world_units)` +
   `_push_shadow_bias()`.

### Step 3 — gate it with a paxtest
New `tools/paxtest/test_shadow_grazing.py` (or extend `test_shadows.py`):
angled sun ~30° over a receiver plane **tilted away from the sun so it
grazes**, plus a caster. Assert:
- `normal_bias=0`: acne present on the lit grazing slope (the "before").
- `normal_bias` set: grazing slope clean AND a real caster still darkens
  the receiver (guards BOTH acne and peter-panning — a too-large normal
  bias would lift the real shadow off; the test must catch that).
Add to `ALL_TESTS` in `run.py`. Run on stock AND Pax3D.

### Step 4 — hand to the openworld dev
Ship `set_shadow_normal_bias(world_units)` + a recommended start value
(try ~0.5–1.0× texel_world / tan at their worst angle; tune with the
metric). Ask them to A/B at az 240 low sun. They have a live dev who can
test on request (`C:\python\openworld`, run per its `PAX3D_FEEDBACK.md`).

### KILL-SWITCH
If step 1's trustworthy metric does NOT show the az-asymmetric
acne/contrast pattern, the bias hypothesis is wrong. Fall back to: does
the umbra vanish because the **receiver** mis-compares (bias) or because
the light's ortho **near/far depth window** clips something at low sun?
Mode 14 (GPU-bound depth buckets) + depth-map extraction distinguishes
them; audit `set_shadow_extent` near/far placement along the light axis
(`pipeline.py` ~line 951) relative to `_shadow_center`.

---

## Operational notes
- **Debug modes now committed** (`bc1f6353b1`), behavior-neutral at
  `u_debug_lighting=0`. In-app: `OW_DEBUG_LIGHTING=11|12|13|14|15|16`.
  Modes: 11 = shadow term, 12 = interp-vs-recomputed coord (was 0.000),
  13 = recomputed-path term, 14 = 3-bucket GPU depth probe (R=−0.5m,
  G=ref, B=+0.5m), 15 = constant-uniform sample (flat = same bound map
  everywhere), 16 = coord distance from the uniform probe.
- **Probe:** `tools/paxtest/probe_openworld_scale.py`. Useful flags:
  `--ortho-cam` (step-0 view), `--actor --patch` (skinned caster + known
  receiver), `--no-village` (card control), `--village-shadow-only` /
  `--village-no-cast` (pass splitter), `--strip-broken`, `--mirror`,
  `--bias-world N`, `--map-size`, `--pcf`, `--baseline-game` (GLSL-120).
  Runs under both engines; `PROBE_GL_DEBUG=1` for verbose GL errors.
- Engine wheel: `wheels_window3\` in `pax3d-env`. No rebuild this
  session or next (Python/GLSL only).
- The GL 0x502 "required buffer is missing" spam in probe runs is
  pre-existing and benign here (offscreen FBO alpha-bits mismatch, see
  the `FrameBufferProperties available less than requested` warning); it
  is NOT the shadow bug — it fires identically in passing runs.

## Strategy reminder (unchanged, user-stated)
Space scenes first; planetary/character features land opt-in with zero
cost when disabled. `shadow_normal_bias_world` default 0.0 follows the
pattern. Keep behavior changes opt-in until proven (CLAUDE.md §5).
