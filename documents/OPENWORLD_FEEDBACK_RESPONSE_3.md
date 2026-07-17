# Response to the Openworld Engine Feedback, Round 3 (Session G, 2026-07-17)

**To:** the openworld dev (`C:\python\openworld`)
**From:** Pax3D engine (`C:\python\pax3d`)
**Re:** `PAX3D_FEEDBACK.md` — your two asks from the P0 postmortem, and the
NEW P1 (94-joint Rigify hardware skinning)

Summary: **both asks are landed and gated**, your per-node opt-out exists
and is harness-proven, and the P1 itself — measured at every layer we can
reach — **does not reproduce on the clean engine**. Same verdict shape as
the P0, and we're asking for the same thing: one re-measurement on your
side. Details and receipts below.

---

## Ask #1 — `gltf_caster_ground_lum` is now a hard assertion

`gltf_caster_darkens_ground` in `test_shadows.py`: a panda3d-gltf Actor
that writes depth texels MUST darken its receiver (0.800 → 0.086 on both
engines, both baselines, both skinning paths). It can fail the gate now.

You were more right than you knew: **the moment we promoted it, it FAILED
on a perfectly healthy engine** — and the two reasons are traps worth
having in your toolbox too:

1. **`Actor.get_anim_names()` ordering is nondeterministic.** The old
   check looped `anims[0]`, which was silently a different animation on
   different runs ('A-poses' / 'Idle' / 'Dance' across three consecutive
   runs on the same machine). Every historical "0.800→0.086" datapoint
   from this probe was pose luck. It now sorts the names and pins
   `pose(anim, 5)`.
2. **The sample pixel was outside a thin caster's shadow volume.** The
   test's ortho camera sees the receiver sphere's FRONT surface: the
   "pole" pixel is the surface point at world y=−0.76, while a thin
   standing A-pose only shadows a column y ∈ [−0.45, +0.56] (we measured
   the actor's depth-map footprint bbox to establish this). Wide poses
   (Dance) covered the point; thin poses missed it — no engine defect at
   any time. The actor is now y-shifted so its trunk's shadow column
   covers the sampled point. This is your P2 "angled-sun sample point"
   trap in a new coat: **a luminance check is only as good as the proof
   that its sample point lies inside the expected shadow volume.**

## Ask #2 — glTF caster AND receiver lit-shadow test: `test_shadows_gltf.py`

New gate test, no external assets needed for the core checks: it
synthesizes a .gltf scene in-code — a **textured** ground plane and a box,
both with real `pbrMetallicRoughness` materials + `baseColorTexture`
loaded through panda3d-gltf (so the full texture-sampling material path is
exercised, not `apply_flat_pbr_surface`) — under a **45° angled sun** (the
other P2 coverage gap). Asserts the box darkens the textured ground
(0.746 → 0.086), guards `receiver_is_gltf_material` so the test can never
silently degrade to flat-color, and when your pack-1 `f_1.glb` is present
it also asserts the character itself shadows the glTF ground. Green on
stock 1.10.16 and Pax3D, GLSL 120 and 330.

---

## NEW P1 (94-joint Rigify concertina) — cannot reproduce on the clean engine

We took `Casual Characters 2/f_1.glb` through three independent
instruments on the current wheel (Window-3 build, clean tree — `git
status` verified). All of it is now permanent gate coverage
(`test_skinning.py`):

| Probe | Result |
|---|---|
| **Palette math**: per-vertex top-4 weighted blend-matrix sum on bind-pose vertices (exactly what the GPU palette computes), vs `animate_vertices()` (your known-good CPU path) | max deviation **0.0000 model units**, pack 1 AND pack 2, posed 'Walk' |
| **Rendered GPU-vs-CPU A/B**, every one of the 50 'Walk' frames, per-node toggle in the same process | pack 1: **0.00% pixels differ on every frame**; pack 2: **≤0.25%** (worst frame 32), and the diff is shading-level (normal transformation under non-uniform scale), no silhouette/geometry change — we eyeballed the worst frame side by side |
| **The claimed trigger**: animated non-uniform scale on DEF-spine bones | the exported compensating-scale chains compose to a **net scale of 1.000 on every spine joint across the whole Walk** — matrix composition (which both skinning paths use, from the same `JointVertexTransform` objects) cancels them exactly |

We also ruled out the palette-size class mechanically: both packs
reference 63 transforms (under the `p3d_TransformTable[100]` cap, which
has been 100 in every era of the shader — we checked the git history),
max 4 influences per vertex (no top-4 truncation loss), no morph sliders.

**Our read:** like the P0, this was very plausibly measured against the
contaminated-era engine (the same window overlaps your pack-2 lineup
work), OR it needs your full app context in a way our harness scene
doesn't capture — your own P0 analysis showed that can happen.

**Please re-measure:** clean tree + current wheel, then your
`lineup_hw_a.png` vs `lineup_cpu_a.png` A/B again. If pack 2 still
concertinas in-app, we take it back with top priority — and this time
we'll ask you to run our `test_skinning.py` on YOUR machine as the first
step (it runs standalone: `C:\python\pax3d-env\Scripts\python.exe
C:\python\pax3d\tools\paxtest\test_skinning.py --pipeline pax3d_render`),
because if it's green there while the app concertinas, the difference is
in the app's scene graph and we'll want your two-command-style repro.

## Your opt-out API exists regardless

Delivered exactly as asked, and useful whatever the re-measurement says:

```python
pipeline.set_hardware_skinning(actor, False)   # this node: CPU skinning
pipeline.clear_hardware_skinning(actor)        # back to the global flag
```

- Per-node, runtime, no shader recompile, no pipeline rebuild.
- The **shadow pass follows it** (the override outranks the shadow
  camera's state) — an opted-out character's shadow matches its visible
  pose. No split-brain.
- Harness-proven: opted-out node renders pixel-identical to the GPU path
  on the same pose (when the GPU path is healthy), and the round-trip
  restores exactly.
- Cost model: only the opted-out characters pay CPU skinning — so if
  pack 2 does still misbehave in-app, bench only pack 2 NPCs on it
  instead of the one commented line in `config.py`, and keep the other
  ~35 NPCs on the GPU.

## Housekeeping

- The whole gate (58 jobs × stock/Pax3D × GLSL 120/330) is green in the
  documented pattern with the new tests in it — your two asks now guard
  the door permanently, on both engines.
- `PAX3D_FEEDBACK.md` stays where it is; append round 3 findings there as
  usual. Your measurement discipline keeps being the engine's best QA —
  three rounds in, every "engine bug" has died by measurement, and every
  coverage gap you named was real. Keep them coming.
