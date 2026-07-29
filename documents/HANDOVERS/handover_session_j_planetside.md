# Handover — Session J (2026-07-18): planetside package LANDED

**R5's planetside slice, pulled forward by user direction** after the
openworld Mars colony map proved the planetside use-case. Spaceflight
remains the first priority, so the whole package is opt-in: every feature
defaults OFF and off is **byte-identical** (the tests assert rms exactly
0.0 on opt-out). Python/GLSL only — no engine build was touched, the
features run on stock 1.10.16 too. Committed as `980e96b286` (not
pushed).

Durable records: master plan §1 R5 row + §4.4, arch doc §5.7 / §9
R5.1–R5.2, `../PLANETSIDE_LOOK_GUIDE.md` (the dev-facing writeup).

---

## What shipped

**R5.1 — aerial perspective / height haze** (`pax_pbr.frag` +
`pipeline.py`):
- `ENABLE_ATMOSPHERE` define (recompile-class, `enable_atmosphere` /
  `set_enable_atmosphere()`): analytic exponential-height optical depth
  along the camera→fragment ray (no ray march; degenerate horizontal-ray
  case handled with the `(1-exp(-u))/u → 1` limit), sun-forward scatter
  tint `pow(mu, sun_power)`, applied in linear HDR after emission,
  before debug modes; alpha untouched; legacy `ENABLE_FOG` unchanged
  (applies first if both on).
- `set_atmosphere_params(haze_color, sun_haze_color, sun_power, density,
  scale_height, base_height)` — uniform-only, per-frame safe (weather).
- Uniforms are pushed even when the define is off (missing-input crash
  class, arch doc §3) — keep it that way.

**R5.2 — environment-driven ambient** (`pipeline.py` only — zero shader
changes; it feeds the `sh_coeffs` path that shipped zeroed since R1):
- `set_hemisphere_ambient(sky, ground, up=(0,0,1))` — exact SH bands 0–1
  for a two-tone sky/bounce environment (up face gets
  `avg + 2/3·delta`).
- `set_ambient_sh(coeffs)` raw 9×RGB, `clear_ambient_sh()` exact restore.
- `sh_from_cubemap(tex)` module-level, **EXPERIMENTAL** (see Next #2).
- `_set_env_map_uniforms` now re-pushes the CURRENT coefficients on
  recompile (the §3 input-preservation invariant extended — guarded by
  `sh_survives_recompile`).

**Shadow texel snapping** (backlog item, `pipeline.py`):
- `shadow_texel_snap` (init) / `set_shadow_texel_snap()` (runtime,
  uniform-cost): `_apply_shadow_center()` quantizes the frustum center to
  the texel grid (`2·extent/map_size`) along the light's **film axes**
  (quat right/up), always from the caller's stored ideal center (no
  drift); re-derived in `update_sun` when the grid rotates. Off =
  `set_pos(center)` exactly as before.

**Tests** (all in `ALL_TESTS`; green both engines × both GLSL baselines,
also through the game-routed `pax_pbr` adapter):
- `test_atmosphere.py` (11): analytic transmittance to 3 decimals at
  three distances, height falloff, sunward tint, `density=0` exact no-op
  with the define compiled in, opt-out rms 0.0.
- `test_ambient_sh.py` (10): per-channel hemisphere analytics exact
  (kd=0.96 at n·v=1), recompile survival, clear restores rms 0.0,
  cubemap→SH matches the analytic hemisphere at 0.0%.
- `test_shadow_snap.py` (6): 0.3-texel move flips 24 depth texels
  unsnapped (the shimmer, measured) → 0 texels + rms-0.0 screens across
  a snapped sub-texel sweep → 152 texels on a 2-texel step (follows, not
  frozen).

**Docs:** arch doc (§3 defines, §5.7, §7 param model + constructor, §9
R5.1/R5.2), master plan (R0/R5 rows, §4.4, backlog: texel-snap DONE,
fog-toggle superseded), SESSION_LOG, paxtest README (+3 tests, snapshot
table), CLAUDE.md R5 row, docs index, `PLANETSIDE_LOOK_GUIDE.md` (new,
dev-facing: APIs, Mars starting values, tuning loops, adoption order).

## Evidence on file
- Full gate: both engines (stock `C:\Python313`, `pax3d-env` Window-3
  wheel) × game baseline — failure pattern byte-identical to the
  pre-session baseline (the six documented legacy/R4 rows only); modern
  baseline all-pax3d_render sweep green except the documented `scale`
  default row. Logs were in the session scratchpad; the durable record is
  the paxtest README snapshot table.
- Analytics landed EXACT on first run (max channel err 0.000 in both
  atmosphere and ambient tests) — the shader math and the SH derivation
  (E(n) = π·avg + 2π/3·delta·(n·up), divided by the shader basis
  constants) are confirmed against the GPU, not just each other.

## Decided / notable
- **The opt-out contract is load-bearing:** every planetside feature must
  keep an exact byte-identical off-state (spaceflight first). New R5 work
  inherits this bar.
- Hemisphere ambient **replaces** the flat AmbientLight level (keep a tiny
  one attached — the no-lights white-flood harness gotcha is real in
  games too); it does not stack.
- Atmosphere heights are world-z (shader world frame is Panda Z-up — same
  frame as `u_sun_dir_world`; empirically proven by the sun path).
- CSM, clustered lights: NOT pulled forward (post-R5 per plan; CSM is
  C++-class). Vegetation wind sway: considered, deferred (content-
  dependent, needs a define + per-node inputs; note in master plan if
  requested again).

---

## Next (in priority order)

1. **Openworld field tuning** (external): the dev adopts per
   `PLANETSIDE_LOOK_GUIDE.md` §4 order (snap → ambient → haze) and
   reports settled Mars values; fold them back into the guide as presets.
   The Session-I ask (A/B `shadow_normal_bias_world` ≈ 0.25 at az-240 low
   sun) is STILL OPEN and pairs naturally with this pass.
2. **`sh_from_cubemap` horizontal orientation**: up/down axis + DC are
   validated; the in-face u/v orientation of the ±x/±y faces is NOT (the
   harness fixture is self-consistent by construction). Have a real
   skybox loaded, check the sunset side tints the correct flank; if
   flipped, fix the face table in `pipeline.py` and extend
   `test_ambient_sh` with an asymmetric-horizontal fixture that would
   have caught it.
3. **R5 remainder** (engine): orbital atmospheric scattering (analytic
   single-scatter limb model per planet type — the spaceflight half),
   specular env maps for the IBL path, lens flare/dirt on the bloom
   chain. Same opt-in bar.
4. **Unchanged queues:** game-side adoption (master plan §4.2 — parity
   eyeball, pilot-seat shadows with `shadow_bias_world`, bloom retune,
   sRGB experiment) and R4.2 camera-relative (game-side, §4.3). The
   normal-offset-bias contingency (Session I #2) stays dormant unless
   openworld's contact shadows lift.

## Operational notes
- No rebuild needed this session or next (Python/GLSL only). Wheel:
  `wheels_window3\` in `pax3d-env`.
- The games live-load `pax3d_render/` from this repo — an uncommitted
  broken shader edit hits them with no rebuild. Declare AND push any new
  uniform in one edit, then run the relevant test immediately
  (Session-H lesson; held this session).
- `set_atmosphere_params` before `set_enable_atmosphere(True)` is safe in
  either order (uniforms always pushed).
- The three new tests skip on pipelines without the APIs (hasattr), so
  the matrix stays clean; `pax_pbr` rows now PASS atmosphere/ambient_sh
  because the game's `use_pax3d_render` flag routes that adapter here —
  expected, not a leak.
