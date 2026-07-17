# Handover — Session G (2026-07-17 evening): paxtest hardening, skinning verdict, per-node API

**State: both openworld asks landed and gated; the P1 is measured and
returned to sender; a new per-node skinning API is live.** Read
`../PAX3D_MASTER_PLAN.md` (v3, facts #12/#13 added) first; Session G
narrative in `../SESSION_LOG.md`.

## What happened (all Python/GLSL/tests/docs — zero C++ touched)

| Item | Where | Result |
|---|---|---|
| `gltf_caster_darkens_ground` assertion (ask #1) | `test_shadows.py` | Promoted from `[info]`; deterministic (sorted anims + pinned pose + y-shifted actor); 0.800→0.086 both engines |
| glTF caster+receiver lit-shadow test (ask #2) | `test_shadows_gltf.py` (NEW) | Synthesized textured-glTF scene, 45° angled sun, optional pack-1 character caster; 6 checks green everywhere |
| Skinning correctness + opt-out test | `test_skinning.py` (NEW) | 12 checks green; carries the pack-1/pack-2 probes permanently |
| Per-node skinning opt-out (P1 ask) | `pax3d_render/pipeline.py` | `set_hardware_skinning(np, enabled)` + `clear_hardware_skinning(np)`; arch doc §5.5 |
| P1 root-cause verdict | probes (scratchpad) + test_skinning | **Not reproducible on the clean engine** — see below |
| Feedback response | `OPENWORLD_FEEDBACK_RESPONSE_3.md` (+ copy at openworld root) | Re-measurement requested |

Gate: 58 jobs × stock/Pax3D × game/modern — green in the documented
pattern (documented-FAIL rows unchanged: retired pax3d_simplepbr,
rebuild/pax_pbr F4-by-design, scale R4 baseline with @logdepth PASS.
`lighting/none @modern` fails identically on stock — pre-existing
control-pipeline artifact under gl 3 2, not ours).

## The two findings worth internalizing (facts #12, #13)

1. **Fact #12 — sample geometry + pose determinism.** The promoted
   assertion FAILED on a healthy engine first: `get_anim_names()` order
   is nondeterministic (historical 0.086 readings were pose luck), and
   the "pole" sample pixel is the sphere's FRONT surface (y=−0.76),
   which a thin A-posed caster does not shadow. The depth maps were
   IDENTICAL between stock and Pax3D (1/2803 texels) — the engine was
   never wrong. Before trusting any NO-SHADOW reading: pin the pose, and
   verify the sample point sits inside the caster's depth-map footprint.
2. **Fact #13 — the Rigify P1 doesn't exist on the clean wheel.**
   GPU palette math == CPU truth exactly (pure-Python simulation);
   rendered A/B ≤0.25% shading-level across all 50 Walk frames (pack 1:
   0.00%); net compensating-scale = 1.000 on every spine joint; palette
   cap [100] in every era. Same epistemic shape as the P0.

## Next session — priorities in order

1. **Openworld round-3 follow-up** (when their re-measurement arrives):
   if pack 2 still concertinas in-app on a clean tree + current wheel,
   first step is `test_skinning.py` on THEIR machine, then their in-app
   two-command-style repro. If it's clean: close the P1 for good.
2. **Game-side adoption queue** (master plan §4.2 — needs the user):
   parity eyeball, shadows-in-the-pilot-seat (`shadow_bias_world` ~0.5
   IEU first!), bloom retune, sRGB linearization experiment.
3. **R4.2 camera-relative** (game side, §4.3) — the engine is ready;
   coordinate with the nested-space dev.
4. Smaller backlog: engine-side shadow texel snapping (shimmer test),
   runtime fog toggle (R5-adjacent), the two sfb2 bugs (cp1252 `→`
   print; mixed-slash music path).

## Operational notes

- Worktree was verified clean at session start (fact #11 habit) and the
  wheel is `wheels_window3\` in `pax3d-env`. No engine build needed or
  performed this session.
- `run.py` ALL_TESTS now has 10 entries ('shadows_gltf', 'skinning'
  added). Both new tests self-skip on pipelines without what they need
  (directional sun / the per-node API / panda3d-gltf).
- The openworld asset packs are load-bearing for the pack probes
  (`C:\python\openworld\3D assets\Casual Characters{,\ 2}\f_1.glb`) —
  the tests degrade to INFO when absent, so the suite stays green on
  machines without them.
- The per-node opt-out rides on ShaderAttrib per-bit flag composition +
  override 2 (> the shadow pass's override-1 initial state). If anyone
  adds another override-carrying attrib to the shadow initial state,
  keep it below 2 or the opt-out's shadow-pass behavior breaks (guarded
  by `optout_shadow_follows_pose`).

## Strategy reminder (unchanged, user-stated 2026-07-17)

**Space scenes are the first priority, always.** Planetary/character
features land opt-in with zero cost when disabled — `set_hardware_skinning`
follows the pattern (no-op unless called).
