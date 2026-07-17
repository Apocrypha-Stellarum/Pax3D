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
once wiped all shader inputs — guarded here). Session D adds the off-origin
extent checks: geometry outside the frustum samples LIT,
`set_shadow_extent(center=...)` recenters onto a far cluster, and
positioning the light node leaves lighting bit-identical. Session E adds
the skinned casters (egg-synthesized sheet: depth texels, ground darkening,
shadow-follows-pose), and a real panda3d-gltf Actor as caster — whose
ground-darkening line was promoted from `[info]` to the hard assertion
`gltf_caster_darkens_ground` in Session G (openworld ask #1). Two traps
are encoded there: `get_anim_names()` ordering is nondeterministic (the
anim is now sorted and the pose pinned), and the "pole" sample pixel is
the sphere's FRONT surface (world y=-0.76), which a thin standing caster
does not shadow — the actor is y-shifted to put its trunk's shadow column
over the sampled point. The `--soft-skin` variant reruns everything on the
CPU-skinning path. Skips pipelines without the directional sun mode.

**`test_shadows_gltf.py`** (Session G, openworld ask #2) — lit-pass
shadows with glTF-material geometry as BOTH caster and receiver, under a
45-degree ANGLED sun. Synthesizes a .gltf scene in-code (textured ground
plane + box, real `baseColorTexture` sampling through panda3d-gltf — the
flat-color scenes demonstrably cannot catch this class), asserts the box
darkens the textured ground, and repeats with the pack-1 openworld
character as caster when the asset is present. Guards
`receiver_is_gltf_material` so the test can't silently degrade to the
flat-color path.

**`test_shadow_quality.py`** (Session E) — angled-sun analytic shadow
placement, the normalized-bias trap (measured record), `shadow_bias_world`,
3×3 PCF widening, and `exclude_from_shadows()` — top-down over a ground
plane so every expected shadow position is computable.

**`test_shadow_grazing.py`** (Session I, openworld P0 addendum) —
grazing-angle self-shadow acne and the slope-scaled bias fix
(`shadow_normal_bias_world`). Low sun over flat ground so grazing is set
purely by altitude; measures the pure shadow term (mode 11) as a
black-fraction. Asserts acne present at `normal_bias=0`, cleared when set,
a real caster's umbra retained (no peter-pan), and — with teeth — that a
too-large value erodes the real umbra. The mechanism gate; the varied-
terrain proof is `probe_openworld_scale.py --normal-bias`.

**`test_skinning.py`** (Session G, openworld P1) — hardware vs CPU
skinning correctness plus the per-node opt-out API. Three layers: the
egg sheet posed and rendered GPU vs `set_hardware_skinning(np, False)`
(images must match, the depth pass must follow the per-node path,
`clear_hardware_skinning()` must restore); a pure-Python simulation of
the GPU palette math (top-4 weighted blend-matrix sum on bind-pose
vertices) against `animate_vertices()` (the CPU truth); and a rendered
GPU/CPU A/B per openworld character pack (the 94-joint Rigify pack 2
included). Session G verdict: the reported concertina does NOT reproduce
on a clean engine — pack 1 pixel-exact across all 50 Walk frames, pack 2
≤0.25% (shading-level), palette math exact, net Rigify compensating-scale
chains compose to 1.000.

**`test_ftl_blur.py`** — the FTL warp distortion pass (radial blur +
chromatic aberration in tonemap); asserts zero-strength passthrough and
effect behavior (added alongside the feature, post-Session-D).

**`test_scale.py`** — R4 acceptance tests: `zfight_at_range` (1 IEU
separation at 2500 IEU under the game frustum 0.1/5000 — swept through a
full depth-quantization cell in 6 sub-resolution steps; the rear surface
bleeds through at some step, worst ~89%), and `precision_off_origin`
(identical rotated-camera scene at origin vs 1.2e6/1.2e7 IEU differs by
0.24%/22% of pixels). Near-field depth and origin-determinism controls
must stay green forever. The default runs document the engine baseline
and FAIL by design until R4 completes; the **`--log-depth` variant
(`scale/pax3d_render @logdepth`) must PASS** — it runs the depth checks
with `enable_log_depth=True` under a 0.1/1e9 frustum (R4.1, landed).
Two findings encoded here: the precision defect requires a ROTATED
camera (axis-aligned rigs cancel exactly in float32 and hide it), and
z-fight probing must SWEEP — a single frame can tie-break uniformly in
the correct surface's favor and mimic a working depth buffer.

## Goldens

`--golden` blesses the current captures into `goldens/`; `--check-golden`
adds an RMS-diff check against them on later runs. Analytic checks are the
primary mechanism — goldens are a safety net for refactors (R1).

## Results snapshot (post Session G, 2026-07-17)

Same results on stock 1.10.16 and Pax3D 1.11.0 (Window-3 wheel), both
baselines — 58 jobs per matrix, 4 matrices. Note: with the game's
`use_pax3d_render` flag flipped (Session D), the `pax_pbr` adapter routes
to pax3d_render — its column now mirrors pax3d_render except for `rebuild`
(the test exercises the old attach pattern, which fails by design).

| Test | none | simplepbr | pax_pbr (routed) | pax3d_render |
|---|---|---|---|---|
| gamma | PASS | PASS | PASS | PASS |
| lighting | PASS (game); FAIL @modern (fixed-function control under gl 3 2 — identical both engines, pre-existing) | PASS | PASS | PASS (both sun modes) |
| bloom | skip | skip | PASS | **PASS (F3 fixed, Session D)** |
| rebuild | skip | skip | FAIL (F4, by design of the old pattern) | **PASS** |
| shadows | skip | skip | skip | **PASS (incl. off-origin extent, skinned + glTF casters, @softskin)** |
| shadows_gltf | skip | skip | skip | **PASS (glTF caster AND receiver, 45° sun)** |
| shadow_quality | skip | skip | skip | **PASS** |
| shadow_grazing | skip | skip | skip | **PASS (grazing acne cleared by slope-scaled bias, umbra kept)** |
| ftl_blur | skip | skip | PASS | PASS |
| scale | **FAIL (R4 baseline)** | skip | skip | **FAIL (R4 baseline)**; **@logdepth PASS (R4.1)** |
| skinning | skip | skip | skip | **PASS (opt-out API + both openworld packs)** |

`pax3d_simplepbr` (retired) keeps its historical bloom/rebuild failures.
`scale` failing is the DOCUMENTED baseline until R4 lands — see its entry
above.

Key established facts (full analysis:
`documents/PAXTEST_FINDINGS_SESSION_A.md` + master plan session updates):

- **No double gamma** — all tonemap operators match their analytic curves;
  the ACES wash-out is an input-linearization problem (textures sampled
  RAW, content tuned for Hejl-Dawson).
- **No DirectionalLight engine bug** — real lights work on every mesh type;
  pax3d_render's directional sun measures identically to the uniform sun,
  and its shadows are proven (lit 0.79 → shadowed 0.09).
- **Blocky bloom (F3) is FIXED (Session D)** — the root cause was 8-bit
  intermediate FBOs (`render_quad_into` without float fbprops), NOT
  filtering; the banding mimics nearest-neighbor sampling. Guarded by
  `bloom_buffers_float`.
- **Scale defects (R4) are reproduced** — depth resolution ~1.9 IEU at
  2500 IEU under the game frustum; float32 view-matrix precision loss
  needs a rotated camera to manifest.
- **A luminance check is only as good as its sample geometry (Session G)**
  — the glTF-caster assertion initially FAILED on a healthy engine because
  the sampled "pole" pixel is the sphere's front surface, outside a thin
  caster's shadow column, and because the nondeterministic anim pick had
  been silently choosing wide poses. Pin poses; verify the sample point is
  inside the caster's shadow volume (the depth-map diff bbox tells you).
- **The 94-joint Rigify concertina (openworld P1) does not reproduce on a
  clean engine (Session G)** — GPU palette == CPU truth at every layer
  measured (math sim exact, renders ≤0.25% shading-level across the full
  Walk, net compensating-scale chains = 1.000). Guarded permanently by
  test_skinning; field re-verification requested.
