# paxtest — Pax3D graphics test harness

Standalone, seconds-fast graphics tests for the Pax3D rendering program
(Phase R0 of `documents/PAX3D_MASTER_PLAN.md`). Tests real pipelines against
analytic expectations by rendering offscreen and reading pixels back — no
need to launch Pax Abyssi and eyeball the result.

## Quick start

```bash
# Full matrix (any Python that has panda3d):
C:/Python313/python.exe tools/paxtest/run.py              # stock engine
C:/python/pax3d-env/Scripts/python.exe tools/paxtest/run.py   # Pax3D engine

# One test, one pipeline:
C:/Python313/python.exe tools/paxtest/test_bloom.py --pipeline pax_pbr

# Subset / options:
python tools/paxtest/run.py --tests gamma,bloom --pipelines pax_pbr
python tools/paxtest/run.py --baseline modern     # adds gl-version 3 2
```

Exit codes: 0 pass, 1 fail, 77 skip. Each test prints per-check lines and a
machine-readable `PAXTEST_JSON:` line; the runner aggregates into
`output/last_run.json`. Captures land in `output/*.png` — always look at the
pictures when a check fails.

## Pipelines under test

| Name | What it is |
|---|---|
| `none` | Raw Panda3D, no post-processing. Control — validates the harness itself. |
| `simplepbr` | Stock pip simplepbr. Known-good reference for PBR conventions. |
| `pax3d_simplepbr` | The old fork in this repo. Retired — superseded by pax3d_render. |
| `pax_pbr` | The game's local pipeline, imported from `C:/python/sfb2`. |
| `pax3d_render` | **The unified R1 pipeline in this repo** — the successor both of the above merge into. |

`--baseline game` (default) mimics sfb2/plan.py PRC (no `gl-version` →
GLSL 120). `--baseline modern` sets `gl-version 3 2` — the R1 target.

## Tests

**`test_gamma.py`** — renders bars of known scene-linear values (LDR 0–1 and
HDR 0–4 rows) through the pipeline, compares the framebuffer against the
analytic tonemap curve for every operator. On failure, reports the best-fit
hypothesis (double-gamma / missing gamma / no tonemap). Also reports whether
8-bit textures are sRGB-decoded on sampling (the input half of the color
contract).

**`test_lighting.py`** — game-winding sphere, reversed-winding sphere, and a
GLTF ship from sfb2, lit from each cardinal direction through the pipeline's
native sun mechanism (`update_sun()` uniforms for pax_pbr, a real
`DirectionalLight` + `set_direction()` elsewhere). Asserts the lit hemisphere
faces the sun. For pax_pbr, additionally documents whether a real
DirectionalLight is consumed at all.

**`test_bloom.py`** — black scene + one small HDR emissive quad, bloom on.
Asserts a halo exists and decays smoothly (max adjacent-pixel step, outward
brightness jumps, symmetry). Runs at 512x512 (divides evenly through the 1/32
mip chain) and 960x540 (doesn't) to localize truncation bugs.

**`test_rebuild.py`** — auxiliary background camera (the sky-camera pattern)
plus a bloom toggle, which rebuilds the FilterManager chain. Asserts the
auxiliary region still renders afterwards. Legacy pipelines attach the
sky_camera.py way and FAIL (that's F4); pax3d_render attaches through
`register_scene_camera()` and passes.

## Goldens

`--golden` blesses the current captures into `goldens/`; `--check-golden`
adds an RMS-diff check against them on later runs. Analytic checks are the
primary mechanism — goldens are a safety net for refactors (R1).

## Findings snapshot (Session A, 2026-07-16)

Same results on stock 1.10.16 and Pax3D 1.11.0 — the defects are in the
Python/GLSL pipelines, not the engine:

- `gamma`: **PASS everywhere.** ACES/Reinhard/Uncharted2/Hejl-Dawson all match
  their analytic curves exactly on pax_pbr and pax3d_simplepbr. The
  Session-459 "double gamma" hypothesis is disproven; the ACES wash-out is an
  *input* problem (textures sampled RAW, content tuned for Hejl-Dawson).
- `lighting`: game-winding sphere and GLTF ship light **correctly** under a
  real DirectionalLight on simplepbr — the R2 restoration is viable today.
  Reversed winding inverts lighting (PBR) or culls to black (fixed-function).
  pax_pbr confirmed to IGNORE real DirectionalLights.
- `bloom`: blocky halo (F3) reproduced in isolation on both pipelines at both
  resolutions — not a resolution-truncation bug; suspect filtering/upsample
  design in the mip chain. Halo is also vertically asymmetric (~0.05–0.07
  up/down luminance delta at equal radius).

See `documents/PAXTEST_FINDINGS_SESSION_A.md` for the full analysis.
