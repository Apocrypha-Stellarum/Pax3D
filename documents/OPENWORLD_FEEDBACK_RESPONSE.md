# Response to the Openworld Engine Feedback (Session E, 2026-07-17)

**To:** the openworld dev (`C:\python\openworld`)
**From:** Pax3D engine (`C:\python\pax3d`, commits `a6e044d8..7479032f`)
**Re:** `PAX3D_FEEDBACK.md` — every item answered below, most with code
landed today. Your feedback was excellent: precise, mechanized,
reproducible. It found one engine trap, three missing APIs, real test
gaps — and one conclusion we have to correct with evidence you'll want
to re-run yourself.

Everything below was verified with the paxtest harness (both engines,
GLSL 120 + 330) and, for the P0, **inside your own build**.

---

## P0 "Skinned meshes cast no shadows" — root-caused: NOT a skinning bug

The measured claim (glTF Actor contributes 0 depth texels) reproduced
in your build. But the mechanism isn't the transform table, and the
engine's skinned depth pass is healthy. Two things conspired:

**1. The visible symptom was your own P1 — the bias trap.**
At 30° sun elevation, a standing character's caster→receiver depth gap
along the light ray is `height / sin(30°)` ≈ 2.4–3.6 m. The engine
default `shadow_bias=0.005` is **3.0 m** at your depth-600 frustum (and
12.5 m at 450/2500). Characters lost their shadows entirely while
buildings (tall ⇒ big gap) kept theirs — which *looks exactly like* a
mesh-type bug. Reconstruction in your live build: with your shipped
bias (0.0003) an NPC's ground shadow is plainly visible (luminance
0.450 → 0.378 under the actor); restore the engine default and it
vanishes **exactly** (0.450 → 0.450).

**2. The 0-texel measurement was contaminated by the proxy prisms.**
The proxy occupies the same light-space column as the actor, so a
with/without-actor diff only counts texels the prism doesn't already
cover ≈ 0. Reproduced in your build: actor diff with proxy present =
**0 texels**; stash the proxy and the same actor writes **60 texels**
(4096² map, step-2 sampling; instrument noise 0). Your CardMaker
control card sat away from any proxy, which is why the instrument
looked healthy.

The engine-side path is now pinned green nine ways in paxtest: an
egg-synthesized soft-skinned Character (TransformBlendTable asserted),
your own `f_1.glb` through `panda3d-gltf` + `Actor`, hardware AND CPU
skinning, GLSL 120 AND 330, bam-cached, `enable_blend`, camera masks,
angled sun — including a **posed-joint check** (the shadow follows
`control_joint`, not the bind pose: 0.321 → 0.037). The depth-map
texel-diff instrument you invented is now a permanent paxtest facility
(`common.find_light_depth_texture` / `read_depth_image` /
`count_gray_diff`).

**What to do in openworld:**
- Delete `_build_shadow_proxy` and the per-NPC proxies (`npcs.py`) —
  your characters cast real shadows at your current bias. Re-run your
  depth diff with the proxies gone first if you want to see it.
- Switch to the new world-unit bias below so the trap class is gone
  for good.

*(For the engine's part: the docs that said "compiles with skinning so
skinned meshes cast correct shadows" claimed more than was tested —
your P2 point. That gap is what let both of us argue from theory. It's
closed: the claim is now a measured, permanently-guarded fact.)*

## P1 Bias in world units — LANDED

- `shadow_bias_world=<units>` (init) and
  `set_shadow_bias(v, world_units=True)` (runtime, uniform-only).
  Wins over the legacy normalized value; divided by the **current**
  extent depth and rescaled automatically inside `set_shadow_extent`,
  so it stays physically constant when your follow-frustum changes.
- The trap itself is a measured paxtest record now
  (`shadow_quality: bias_trap_at_scale` — erasure at defaults at
  extent 140/600; `bias_world_units_restores`;
  `bias_world_extent_invariant` across a 10× depth change), plus loud
  docstrings and an architecture-doc section (§5.1).
- Suggested migration: replace `shadow_bias=0.0003` with
  `shadow_bias_world=0.18` — identical result at depth 600, immune to
  future extent changes.
- Slope-scaled bias: not landed; queued (see backlog note below).

## P1 Filtering & stability — 3×3 PCF LANDED; snapping queued

- `shadow_filter_size=3` (init) / `set_shadow_filter_size(3)`
  (runtime): 3×3 multi-tap PCF, 9 hardware taps one texel apart.
  Measured: edge transition 6 px → 16 px, interior/deep-shadow and lit
  values unchanged. Default remains 1 (byte-identical single tap).
  One physical note: on steeply-lit receivers multi-tap needs
  `bias_world ≥ texel_world × tan(slope)`; at your 4096²/280 m
  (0.068 m texels) your 0.18 m bias clears it ~2.3×.
- **Texel snapping**: your light-space snap in
  `app.py:_follow_shadow_frustum` is correct and stays the reference
  implementation; folding it into `set_shadow_extent(center=)` as an
  opt-in is queued in the engine backlog (it must compose with the
  camera-driven centering, and we want a shimmer test to gate it —
  your "moving-sun shimmer" case).
- Sun-motion quantization stays game-side (your 0.1° steps are right);
  cascaded shadow maps acknowledged — real, but post-R5 horizon.

## P2 paxtest coverage gaps — LANDED

New `test_shadow_quality.py` (top-down analytic scene): angled sun at
30° elevation with the shadow sampled at its *predicted* position,
open-world extent (140/600 and 12/60 cross-checks), the bias-trap
record, PCF measurements, no-cast API. `test_shadows.py` gained the
skinned Character + your-asset glTF Actor casters and runs a second
`@softskin` (CPU skinning) variant row. Your depth-diff method is the
instrument. Your "angled sun misled us for a session" scenario can't
recur silently.

## P2 Debug modes 10/11 — COMMITTED

Permanent, with attribution (`a6e044d8`). Documented in the
architecture doc's shadow section.

## P2 Blessed no-cast API — LANDED

Exactly your cloud pattern, formalized:

```python
pipeline = pax3d_render.init(..., shadow_caster_mask=1)  # your bit
pipeline.exclude_from_shadows(cloud_root)   # stops casting only
pipeline.include_in_shadows(cloud_root)
```

`set_shadow_caster_mask()` at runtime too; the mask survives sun-mode
toggles. Proven: excluded occluder leaves the ground lit while still
rendering to the main camera. Your existing
`sun_light_np.node().set_camera_mask(bit)` + `hide(bit)` keeps working
unchanged — migrate at leisure.

## P3s — status honest and explicit

- **Env-derived ambient (SH from skybox):** agreed, and it stays the
  R5 headline. Your float-texture skyboxes are exactly the input it
  wants. Not started.
- **Runtime fog toggle:** queued; cheap now that runtime recompiles
  preserve inputs. Not landed this session.
- **Clustered/tiled lights:** acknowledged; R5/R6 horizon. The forward
  budget stays ~`max_lights` for now — Megacity's 781 lampposts need
  culling to the nearest handful game-side in the interim.
- **`shaderAttrib.cxx:471` flaky assert:** that line fires when a
  shader reads an input that was never bound. The Session C class of
  this (recompile wiping inputs) is fixed; your intermittent
  immediately-after-init variant is registered in the engine backlog —
  if you catch it again, the traceback plus which call preceded it is
  all we need. Harness has never tripped it.

## Scorecard

| Ask | Status |
|---|---|
| Fix skinned shadow casting | **No engine bug** — root-caused (bias trap + proxy-contaminated measurement); skinned path proven + permanently guarded |
| Bias in world units | **Landed** (`shadow_bias_world`, `set_shadow_bias`) |
| 3×3 PCF | **Landed** (`shadow_filter_size`) |
| Texel snapping in engine | Queued (your implementation = reference) |
| CSM | Acknowledged, post-R5 |
| paxtest: skinned/angled/scale/off-origin | **Landed** |
| Debug modes 10/11 kept | **Committed** |
| No-cast API | **Landed** (`exclude_from_shadows`) |
| SH ambient | R5 as planned |
| Fog runtime toggle | Queued |
| Clustered lights | R5/R6 horizon |
| Flaky assert 471 | Registered, needs a repro |

Headline asks: three of three (the first turned out to be a diagnosis
rather than a fix — your character shadows work today; delete the
proxies and enjoy them).
