# Handover — Session I (2026-07-18): grazing-angle shadow bias LANDED

**The Session-H plan executed and the fix is in.** The openworld P0
addendum ("shadows vanish in a western low-sun cone") is root-caused as
**grazing-angle self-shadow acne** and fixed with an opt-in **slope-scaled
bias**. Deterministically gated, byte-identical when off, proven on the
real village GLB. No engine build touched (Python/GLSL only).

Read `../PAX3D_MASTER_PLAN.md` fact #14 and arch doc §5.2 for the durable
record; `../OPENWORLD_FEEDBACK_RESPONSE_4.md` is the dev-facing writeup.

---

## What shipped

**GLSL** (`pax3d_render/shaders/pax_pbr.frag`):
- `uniform float u_shadow_normal_bias;` (declared inside `ENABLE_SHADOWS`).
- `shadow_slope_from_ndl(ndl)` = clamped `tan(θ)`; `slope_scaled_bias(ndl)`
  = `global_shadow_bias + u_shadow_normal_bias * min(tan θ, 8)`;
  `shadow_caster_contrib_biased(map, pos, bias)` split out of the old
  `shadow_caster_contrib` (which now just calls it with the constant bias).
- Light-loop call site passes `slope_scaled_bias(dot(n, l))`. Debug modes
  11 and 13 use the same bias so the instrument matches the lit pass.

**Pipeline** (`pax3d_render/pipeline.py`):
- `__init__(..., shadow_normal_bias_world=0.0)` (0 = OFF = byte-identical).
- `_push_shadow_bias()` uploads `u_shadow_normal_bias = world / extent_depth`
  (same rescaling as `shadow_bias_world` — declared AND pushed in the same
  change, per the Session-H regression lesson).
- `set_shadow_normal_bias(world_units)` runtime setter (uniform-only).

**Tests / tools:**
- `tools/paxtest/test_shadow_grazing.py` (new, in `ALL_TESTS`): 6 checks,
  green on stock **and** Pax3D, both GLSL baselines.
- `probe_openworld_scale.py` gained `--normal-bias` for real-terrain A/B.

## Evidence on file
- Mechanism (deterministic, both engines byte-identical): acne fraction
  0.000 at alt 30°, rising to 0.13 at alt 9° with the fix off; **0.000 at
  every altitude** with `normal_bias=0.10`, umbra kept at 1.000.
- test_shadow_grazing: acne 0.132→0.000, umbra 1.000 kept, over-bias
  erodes umbra 1.000→0.000 (the umbra check has teeth), opt-out exact.
- Real village GLB at az 240 / alt 34: terracing bands gone, building/tree
  shadows kept; mode-11 dark-fraction 0.133→0.097 as acne cleared.
- Full pax3d_render gate green (game baseline); shadow suite green on the
  modern baseline and on stock. The only red is `scale` default (the
  pre-existing R4 baseline documentation FAIL; `@logdepth` passes).

## What's ruled out / decided
- Not a `v_shadow_pos` corruption: mode 12 (interp vs recomputed coord)
  was 0.000 all along. The bisect landed on the receiver *compare*.
- The Session-H toy sweep stayed clean because flat toy ground at alt 34
  isn't grazing enough — the trigger is **sun altitude × terrain slope**.
  Emulated on flat ground with a low sun (alt ~12°); the real asymmetry is
  the village's west-facing slopes.
- Why constant bias can't fix it (their "no bias value works" finding): on
  varied terrain the value that clears grazing acne peter-pans real
  shadows elsewhere. Slope-scaling is the necessary lever.

---

## Next (in priority order)

1. **Openworld dev in-app A/B** (external, requested in RESPONSE_4):
   `shadow_normal_bias_world ≈ 0.25` start; confirm terracing clears AND
   NPC contact shadows survive; report the value they settle on. Fold their
   value into the guide once confirmed.
2. **IF contact shadows lift before terracing clears** at their content
   scale → promote to a true **normal-offset bias** (offset the receiver
   position along its normal before the shadow compare, not just the depth
   ref). More robust against peter-panning; more shader plumbing (needs the
   world normal into the shadow-coord recompute). The current slope-scaled
   *depth* bias is the simpler lever and it cleared the village in our
   probe — only escalate on evidence. Prototype in GLSL, gate with a new
   `test_shadow_grazing` variant (tilted receiver + short contact caster).
3. **Engine-side shadow texel snapping** in `set_shadow_extent` (backlog,
   still open): the openworld follow-frustum shimmers without it; reference
   impl is their `app.py:_follow_shadow_frustum`; gate with a shimmer test.
   Unrelated to this fix but the next shadow-quality item.

## Operational notes
- Engine wheel: `wheels_window3\` in `pax3d-env`. No rebuild this session
  or next (Python/GLSL only). The game live-loads `pax3d_render/` from this
  repo — a broken uncommitted shader edit hits the game with no rebuild
  (Session-H lesson: declare+push any new uniform in one edit, then run
  `run.py --tests shadows` immediately).
- Recommended-value physics: `N ≈ 0.5–1.0 × texel_world` clears flat-ground
  acne at any angle (the `tan θ` cancels); sloped terrain needs ~2–4×
  because the projected texel is larger. Tune with `OW_DEBUG_LIGHTING=11`.
