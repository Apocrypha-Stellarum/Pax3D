# paxtest Session A — Harness Built, First Findings

**Date:** 2026-07-16
**Deliverable:** `tools/paxtest/` (Phase R0 of `PAX3D_MASTER_PLAN.md`)
**Verified on:** stock Panda3D 1.10.16 (system Python) and Pax3D 1.11.0
(pax3d-env) — results identical on both engines.

## What was built

A standalone offscreen test harness (`tools/paxtest/`) that renders known
scenes through each of the four pipelines (`none`, stock `simplepbr`,
`pax3d_simplepbr`, the game's `pax_pbr`) and checks the output
*programmatically* — analytic tonemap curves, lit-hemisphere measurement,
halo-smoothness metrics. Full matrix runs in ~3 minutes; a single test in
~10 seconds. See `tools/paxtest/README.md` for usage.

Control checks validate the harness itself: the `none` pipeline shows a
perfect identity transfer (max error 0.000) and correct raw texture readback.

## Results matrix (both engines)

| Test | none | simplepbr | pax3d_simplepbr | pax_pbr (game) |
|---|---|---|---|---|
| gamma | PASS | PASS | **PASS (all 4 operators)** | **PASS (all 4 operators)** |
| lighting | PASS* | PASS* | PASS* | PASS* |
| bloom 512x512 | skip | skip | **FAIL (blocky)** | **FAIL (blocky)** |
| bloom 960x540 | skip | skip | **FAIL (blocky)** | **FAIL (blocky)** |

\* the only lighting failure on every pipeline is the deliberately
reversed-winding sphere (see Finding 3).

## Finding 1 — The "double gamma" hypothesis is DISPROVEN (F2 revised)

`test_gamma` pushes known linear values (0–1 and 0–4 HDR) through the full
post chain and compares against the analytic curves. On the game's pax_pbr
pipeline **every operator matches exactly** (max error ≤ 0.001, tolerance
0.03): ACES, Reinhard, Uncharted2, Hejl-Dawson, and the EV+1 exposure path.
Same for pax3d_simplepbr.

**The post-processing chain is mathematically correct.** Session 459's
suspicion ("GLSL 120 / framebuffer may already be doing sRGB conversion,
causing double-gamma") is wrong.

So why did ACES look washed out in-game? The harness's texture check gives
the answer's first half: **8-bit texture values are sampled RAW — not
sRGB-decoded** (measured 0.502 for a 128/255 texel through the `none`
pipeline; the game pipeline transfer confirms the same raw value). Game
albedo textures are sRGB-encoded images being treated as linear light. All
scene content therefore enters the HDR buffer ~gamma-bright. Hejl-Dawson
(whose curve the content was hand-tuned against for hundreds of sessions)
looks "right"; any *correct* operator applied to gamma-bright inputs looks
washed out.

**Consequence for R1:** the color-contract work is not about fixing the
tonemap shaders (they're fine) — it is about **linearizing inputs**: flag
albedo/emissive textures as sRGB so hardware decodes them, then retune
sun/ambient intensities. Expect the scene to look darker/contrastier at
first; that's the correct starting point for ACES.

## Finding 2 — A real DirectionalLight works TODAY on every mesh type (R2 de-risked)

Under stock simplepbr with a real `DirectionalLight` (node at identity HPR,
`set_direction(travel_dir)` — no HPR formulas at all):

- the **game-winding sphere** (exact copy of `planet_factory.py` post-Session-424
  geometry) lights correctly at all four cardinals (lit/dark ratio ~6.5),
- the **GLTF ship** (`frigate_storm_grey_v4.glb`) receives correct
  directional light,
- front/back behaviour is correct.

The Formula B/C/HPR confusion documented in `DIRECTIONAL_LIGHTING_PLAN.md`
does not reproduce with current meshes and the `set_direction()` API. The
R2 restoration path ("real DirectionalLight + shader reads
`p3d_LightSource[0]`") is confirmed mechanically viable.

Also confirmed: **pax_pbr ignores real DirectionalLights entirely**
(ambient-only 0.086 → 0.086 with a DirectionalLight added), and the
uniform-driven sun (`update_sun`) lights spheres AND the GLTF ship correctly
in isolation (ship lit/unlit ratio 108). The in-game "flat ships" problem is
therefore **not** a pipeline defect — it's scene-level (sun intensity
vs. ambient, per-model materials, or the sun update not reaching ship
scenes). Needs a targeted in-game measurement in R2.

## Finding 3 — Winding inversion confirmed and quantified (F8)

The reversed-winding sphere:
- under fixed-function (`none`): backface-culled → renders black,
- under all three PBR pipelines: visible but lit **inverted** (frontlit 0.086
  vs backlit 0.786 — exactly mirrored vs the correct sphere).

One scene-wide winding convention (R2.2) remains the right call, but note the
*current* planet geometry already follows the standard convention — the fix
is about preventing regressions, not repairing today's planets.

## Finding 4 — Blocky bloom reproduced in isolation; truncation ruled out (F3 narrowed)

A single small HDR quad on black produces a visibly blocky, stair-stepped
halo (see `tools/paxtest/output/bloom_*_halo_*.png`) with max adjacent-pixel
luminance steps of ~0.05 (a smooth halo measures <0.01). Identical on
pax3d_simplepbr and pax_pbr, at **both** 512x512 (divides evenly through the
1/32 mip chain) and 960x540 (doesn't).

Ruled out: resolution truncation / `div=` rounding (512 divides cleanly and
still fails). Additional signature: the halo is **vertically asymmetric**
(up/down luminance delta 0.05–0.07 at equal radius; left/right ~0.000),
suggesting a half-texel or Y-flip offset somewhere in the chain.

Prime suspects for R3 (in test order):
1. Sampling filter state on the intermediate bloom textures (tent/bilinear
   assumptions require linear filtering + clamp-to-edge on every buffer).
2. The upsample pass design: the tent filter samples the *same-resolution*
   downsample texture while the coarser accumulator gets a single bilinear
   tap — so each mip is effectively upsampled by raw bilinear alone, which
   produces exactly this blocky-diamond look.
3. Half-texel offset conventions (the vertical asymmetry).

## Gate status (R0)

- Harness green on control paths (`none` pipeline, gamma + lighting): **yes**
- Reproduces a current-pipeline failure mechanically: **yes** (bloom, on both
  pipelines, both engines, both resolutions)
- F2 caught as designed: **better** — the test is sensitive (control
  validated) and *disproved* the hypothesis, redirecting R1 to input
  linearization.

**R0 gate: PASSED.** Next per the master plan: Session B (R1 — unified
`pax3d_render` package; color contract = sRGB-flag the input textures;
GLSL 330; camera-registration API), now with a harness that can verify each
step.
