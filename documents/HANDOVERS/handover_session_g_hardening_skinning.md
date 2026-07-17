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

## LATE-BREAKING (same day, after the sections above): the P0 is back,
## and it is DIRECTION-GATED

Openworld updated `PAX3D_FEEDBACK.md` with an afternoon **P0 addendum**
that supersedes their "shadows vanish everywhere" characterization AND
weakens Session F's contamination verdict:

- **Cast shadows work at high/eastern sun and die only inside a western
  low-sun cone.** Their `OW_SUN_OVERRIDE=alt,az` matrix (deterministic,
  clock-independent): alt 34/az 120 east = perfect; noon = perfect;
  az 240 west at alt 60/45 = good, 42 = fading, 40 = nearly gone +
  ground banding, ≤38 = gone. Natural clock: works ≤15:36, broken
  ≥15:42; the 08:00 morning mirror (same 34° altitude, eastern azimuth)
  is FINE.
- **Signature:** shadow pools fade and vanish inside the cone; fine
  terracing/acne on open ground; large-offset self-shadowing survives;
  mode-10 UV gradient stays smooth across the boundary → looks like a
  **depth error growing ~1/tan(alt) with an azimuth-sign asymmetry**,
  not a UV/matrix flip. Eliminated: follow-frustum (`OW_NO_FOLLOW`),
  PCF 1v3, NPCs, all hour-driven inputs.
- **Their reinterpretation, which we should take seriously:** the
  03:36/04:29 "regression window" probably changed their sun-arc
  mapping, moving hour-16's *direction* across an always-present fault
  boundary — i.e. possibly NOT the contamination after all. Our own
  fact #12 (the forensic 0.800→0.086 was pose luck) already removed the
  strongest clean-engine counter-evidence. Treat the direction-gated
  failure as a LIVE bug candidate of unknown location (engine C++ /
  pipeline Python-GLSL / their daynight mapping).
- **Session G postscript probe** (`tools/paxtest/probe_azimuth_sweep.py`):
  at TOY scale (extent 12/60, origin, static sun, glTF caster+receiver)
  all 4 azimuths × alt 34/45/60 cast perfect shadows (ratio 0.11–0.12),
  **identical on stock and Pax3D**. So the trigger needs their scale
  and/or their exact sun vectors — the toy matrix is exonerated on all
  axes, both engines.
- Also in the addendum: NPC casters darken ground 0.604× at noon
  in-game (Session E follow-up delivered) — skinned shadow casting is
  fully confirmed in the field.

## Next session — priorities in order

1. **THE direction-gated shadow bug (new P0).** Method, in order:
   (a) re-run `probe_azimuth_sweep.py` at openworld scale —
   `set_shadow_extent(450, 600)`, `shadow_map_size=4096`, scene
   spanning hundreds of units, camera + content off-origin,
   `shadow_bias_world=0.18`, per-frame `update_sun` — sweep the
   az×alt boundary (30–60°); (b) read openworld's `game/daynight.py`
   alt/az→vector mapping and feed the harness its EXACT vectors for
   (34,240) vs (34,120) — their evidence cannot distinguish an engine
   defect from a mapping defect, the harness can; (c) read our
   `set_shadow_extent`/`_configure_sun_shadows` for how the depth
   window is placed along the light axis relative to `center` — a
   placement error is the natural candidate for a depth offset that
   grows as the sun drops and could carry a sign asymmetry; (d) once
   reproduced, mode-10/11 decode at a failing direction; fix in
   Python/GLSL if it's ours; (e) if it will NOT reproduce at scale
   with their exact vectors, ship them a parameterized in-app probe
   (Session-E style) and take their two-command repro. Run everything
   on BOTH engines — stock-vs-Pax3D identity is the C++-vs-Python
   discriminator.
2. **Openworld P1 re-measurement follow-up** (their file did NOT
   retract the concertina claim): if pack 2 still deforms in-app on a
   clean tree + current wheel, run `test_skinning.py` on THEIR machine
   first, then take their in-app repro. If clean: close the P1.
3. **Game-side adoption queue** (master plan §4.2 — needs the user):
   parity eyeball, shadows-in-the-pilot-seat (`shadow_bias_world` ~0.5
   IEU first!), bloom retune, sRGB linearization experiment.
4. **R4.2 camera-relative** (game side, §4.3) — the engine is ready;
   coordinate with the nested-space dev.
5. Smaller backlog: engine-side shadow texel snapping (shimmer test),
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
