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
faces the sun. Also documents whether a real DirectionalLight is consumed.
For pax3d_render, `--sun-mode directional` runs the same checks through the
real-DirectionalLight sun (R2) — the runner does both variants automatically.

**`test_bloom.py`** — black scene + one small HDR emissive quad, bloom on.
Asserts a halo exists and decays smoothly (max adjacent-pixel step, outward
brightness jumps, symmetry). Runs at 512x512 (divides evenly through the 1/32
mip chain) and 960x540 (doesn't) to localize truncation bugs.

**`test_rebuild.py`** — auxiliary background camera (the sky-camera pattern)
plus a bloom toggle, which rebuilds the FilterManager chain. Asserts the
auxiliary region still renders afterwards. Legacy pipelines attach the
sky_camera.py way and FAIL (that's F4); pax3d_render attaches through
`register_scene_camera()` and passes.

**`test_shadows.py`** — occluder sphere on the sun ray above a larger
sphere, `sun_light_mode='directional'` + `enable_shadows`. Asserts the
occluded pole darkens to ambient, restores on toggle-off, and re-darkens on
toggle-on (the toggle exercises the runtime shader-recompile path, which
once wiped all shader inputs — guarded here). Skips pipelines without the
directional sun mode.

## Goldens

`--golden` blesses the current captures into `goldens/`; `--check-golden`
adds an RMS-diff check against them on later runs. Analytic checks are the
primary mechanism — goldens are a safety net for refactors (R1).

## Results snapshot (post Session C, 2026-07-16)

Same results on stock 1.10.16 and Pax3D 1.11.0 — remaining defects are in
the Python/GLSL pipelines, not the engine:

| Test | none | simplepbr | pax_pbr | pax3d_render |
|---|---|---|---|---|
| gamma | PASS | PASS | PASS | PASS |
| lighting | PASS | PASS | PASS | PASS (both sun modes) |
| bloom | skip | skip | **FAIL (F3 blocky)** | **FAIL (F3 blocky)** |
| rebuild | skip | skip | FAIL (F4, by design of the old pattern) | **PASS** |
| shadows | skip | skip | skip | **PASS** |

Key established facts (full analysis:
`documents/PAXTEST_FINDINGS_SESSION_A.md` + master plan session updates):

- **No double gamma** — all tonemap operators match their analytic curves;
  the ACES wash-out is an input-linearization problem (textures sampled
  RAW, content tuned for Hejl-Dawson).
- **No DirectionalLight engine bug** — real lights work on every mesh type;
  pax3d_render's directional sun measures identically to the uniform sun,
  and its shadows are proven (lit 0.79 → shadowed 0.09).
- **Blocky bloom (F3)** is reproducible at any resolution — truncation
  ruled out; suspects are buffer filter state, the upsample design, and a
  half-texel Y offset (halo vertically asymmetric ~0.06). This is the R3
  target; `test_bloom` is its acceptance test.
