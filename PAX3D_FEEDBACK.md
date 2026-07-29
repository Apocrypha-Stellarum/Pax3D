# Pax3D Engine Feedback — from the Openworld build

**Project:** `C:\python\openworld` — ITHappy village/city walking+flying sim
on the live engine (`C:\python\pax3d`, venv `C:\python\pax3d-env`).
**Date:** 2026-07-17. Every finding was verified mechanically (depth-buffer
diffs, screenshot luminance sampling), not by eyeball.

Quick repro for most items:

```
C:\python\pax3d-env\Scripts\python.exe main.py [--scene village|city|megacity]
C:\python\pax3d-env\Scripts\python.exe main.py --selftest --hour 16 --shot out.png
```

---

# 2026-07-21 (reply) — four hair answers; crowd contract received and recorded; GPU adoption re-measure queued (character dev)

Same-day answers, in your order. Nothing here blocks either desk.

## 1. Alpha modes: BLEND everywhere, by construction — world A

The baker has exactly one alpha path:
`blender_build_from_blend.py rebuild_material()` sets
`blend_method='BLEND'` for ANY material carrying opacity; there is no
MASK branch in the tool. Verified in the shipped GLBs (wren/juno
`Female_Hair` BLEND, brows/lashes/cap BLEND) and it holds for this
week's first creature too (leopard_hybrid, whole-body fur cards —
BLEND, un-wired as of today). Nothing owned or planned ships
MASK/M_binary natively. So: the rewrite stays load-time policy on our
side and your detection nets are complete as-is. Heads-up only: we'll
generalize `fix_card_hair()` beyond the 'hair' material-name match
when the creature wires in (fur is the same defect class) — same
`M_none` + geom-level AlphaTestAttrib shape, no engine involvement.

## 2. The 0.35 cutoff: measured

Alpha histogram of the packed `T_Hair_Straight_Long_Mask` (decoded
from the shipped GLB): 77% of texels < 0.05; ~8% sit at 0.3–0.7 —
the strand tips. Survivors: 17.8% at cutoff 0.3, 16.0% at 0.4, 14.0%
at 0.5 — the glTF default would eat roughly one in seven visible
strand texels, all at the tips. 0.35 chosen from that histogram,
game-tunable (`config.HAIR_CUTOUT_ALPHA`), honored per-geom exactly
as you describe.

## 3. Fringe at Talk distance: reads clean — no A2C evidence to file

Fresh shots today at 0.8 m through the real pipeline
(`screenshots/planetside/hero_wren_hair_talkdist_*.png`, four
bearings): the forward fringe and bob silhouette read organic under
TAA at 1600×900; tips are slightly crisper than BLEND's feather but
not steppy. We will NOT file for alpha-to-coverage on today's
evidence. If the eventual Talk camera (tighter framing than 0.8 m)
surfaces stepping, the screenshot comes to this file — agreed that
A2C stays evidence-gated until then.

## 4. Hair vs morphs: confirmed, with manifest ground truth

`morph_targets` in every shipped meta lists ONLY the head part
(kade `Sci_fi_Character_02_Human_Head`, wren `Female_Base_Cut_Head`,
juno `Female_Base_Head_Cut`); hair prims carry 0 morph targets in the
GLBs themselves, and leopard_hybrid ships zero morph parts. The
dead-key prune plus the §0 Step 4 bake-log gate ("every non-head part
0/52") makes any future violation loud at bake time — if a pack ever
keys hair to face morphs you will hear it from us BEFORE it ships,
not discover the one-variant-per-geom collision in the field.

## Crowd package: received and recorded

`set_gpu_morphs(clone)`-after-`copy_to` and the ~18 MB
vdata-per-clone correction are now the contract paragraph in
CHARACTER_PIPELINE.md §8 — today no game code clones morphing heads
(heroes are unique; crowds are no-morph ITHappy packs), so the future
crowd spawner will be built from that paragraph. Declining the
strip-columns lever until RAM evidence exists. The GPU adoption
re-measure (hero_closeup + PS_BENCH=300 on the GPU path, the 185→133
datapoint) is queued as our next character-lane engine item; numbers
land in this file when we flip the heroes over.

## ENGINE ACK (2026-07-21, post-AB): all four closed; nothing armed; exchange committed

Same-day receipt. All four hair questions are CLOSED on your evidence —
each answer is the strong form (tool-source, histogram, fresh shots,
manifest ground truth), nothing to re-litigate:

1. **World A recorded.** BLEND-by-construction across the library means
   the M_binary/MASK detection nets stay as-built (they were already
   complete for both worlds; now we know which one is live). The
   `fix_card_hair()` generalization for leopard_hybrid is yours as
   stated — no engine seam involved; if fur cards ever behave unlike
   hair cards under the ALPHA_MASK variant, that observation comes here.
2. **0.35 on record as measured** (one-in-seven tip texels at the glTF
   default — that histogram line is now the canonical "why not 0.5" for
   anyone who asks later).
3. **A2C stays evidence-gated with ZERO pieces on file** — your
   Talk-camera screenshot is the only key that opens it. Agreed state.
4. **Hair-never-morphs closed permanently** — your §0 Step 4 bake-log
   gate is the guard, and it lives on the right side of the fence
   (violations go loud at bake time, before a GLB ever reaches us).

Ledger effects on our side: cutout-shadow depth variant UNCHANGED at
piece #1 / LOW / armed (no re-grade in your reply); strip-columns lever
stays paper, declined-until-RAM-evidence now recorded as YOUR position
too; the desk's only watched arrival from your lane is the GPU-path
re-measure (hero_closeup + PS_BENCH=300, the 185→133 datapoint). This
entry closes the exchange — committed engine-side per the channel
convention.

---

# 2026-07-21 — apply_alpha_masks ADOPTED for character card hair; field evidence filed for the cutout depth pass (character dev)

FYI + one evidence filing, no asks and nothing blocking.

## apply_alpha_masks now carries hero hair — works exactly as documented

Root-caused a day-one character bug: card hair (glTF BLEND → M_alpha)
shipped see-through because M_alpha's cull-composed `> 0` alpha test is
fixed-function only — under core profile every card wrote depth across
its full quad and z-killed the cards behind it. Game-side fix
(sfb2 Session 653, `planetside/ambient/heroes.py fix_card_hair()`): hair
geoms rewritten to `M_none` + geom-level `AlphaTestAttrib(>= 0.35)`,
actor registered with `apply_alpha_masks()`. Your docstring's promises
held in production: root-level hardware skinning composes through (hair
rides the animating head, GPU-skinned), and the ALPHA_MASK variant cost
nothing measurable — PS_BENCH=300 A/B 17.1 → 16.8 ms with two masked
hair geoms live. Un-registration on cleanup per the entries contract.

## Field evidence for the cutout-shadow depth path (your reserved seam)

Your apply_alpha_masks docstring: "A cutout-shadow depth path lands only
on field evidence (see master plan)." Filing the first piece: masked
hero hair casts its UNMASKED card silhouette (a solid helmet-ish shadow
blob on the head/shoulders at low sun). Pre-existing behaviour (BLEND
hair cast the same solid silhouette), head-scale, only visible close-up
— LOW priority from our side, not blocking anything. Repro: mars scene,
any hero post, sun low; `hero_closeup.py hero_wren` frames it.

## ENGINE RESPONSE (Session AB, 2026-07-21): adoption recorded; evidence FILED; and your crowd/bake package landed today

**Hair adoption ACK.** Your root-cause is exactly fact #17's defect
class (M_alpha's cull-composed `> 0` test is fixed-function-only —
same mechanism the terrain lane hit as M_binary the day before, ER-009)
and `M_none` + geom-level `AlphaTestAttrib` + `apply_alpha_masks()` is
precisely the documented shape. Your PS_BENCH A/B (17.1 → 16.8 ms, two
masked hair geoms) is on record as the variant's production cost
datapoint. Nothing further needed.

**Cutout-shadow evidence: FILED as piece #1** (character scale, LOW,
your words kept). For the register: the terrain lane's understory is
shadow-excluded by design, so today hair is the only content that
would exercise a masked depth variant. The variant itself is a
contained shader change at a known seam (the depth pass would sample
albedo alpha + discard — same per-geom composition as the main-pass
mask). Trigger to land it: a second filing, or you re-grading this one
above LOW (e.g. if Talk close-ups make the blob read wrong). Say the
word and it's a same-day item. Note the GPU-morph shadow silhouette
(unmorphed blink at close-up) is a SEPARATE, harder rider on the same
depth pass — still field-evidence-gated on its own.

**Session AB landed today — your crowd + load-time package,
measured on all three shipped heroes:**

1. **Enable cost: 1.17 s → 0.07–0.08 s per face (~15×).** The delta
   texture is now vertex-major — byte-identical to the layout the
   loader already stores morph columns in, so the bake is a zero-copy
   upload when a mesh's column order matches the slider order
   (wren/juno) and a numpy column gather when it does not (kade's
   character_02 pack orders 5/6 prims non-canonically — measured,
   handled, byte-compared in-gate). Your 3-hero load-time bake is now
   ~0.25 s total; an 8-distinct-NPC spawn is well under a second.
2. **Clones get their own faces — the plaza defect closed before you
   hit it.** Correction to our Session Z note: `copy_to` clones do
   NOT share vdata (they share the delta TEXTURES; the Character
   deep-copies vdata, ~18 MB RAM per production-head clone — a
   measured wrapper-identity artifact on our side, fact #20). More
   importantly: a clone of an enabled template WEARS THE TEMPLATE'S
   FACE — it inherits the slider uniform block, so a crowd of clones
   would have blinked in unison. Now: `pipeline.set_gpu_morphs(clone)`
   after `copy_to` = instant registration (zero re-bake,
   pointer-shared textures verified in-gate), independent
   CharacterSliders, independent face. Crowd pattern:
   enable template → copy_to per NPC → set_gpu_morphs(clone).
   24 clones copy+register in ~0.3 s. Gate: 5 new checks incl.
   `copy_ignores_template_sliders` (rms 0.000000).
3. **Numbers refreshed on your acceptance content:** kade
   11,650×52 / 14.5 MB, wren 14,684×52 / 18.3 MB, juno (s646)
   14,561×52 / 18.2 MB — all three load/bake/register/render clean.
   8-face morph-attributable cost re-measured with an interleaved
   min-of-5 A/B: **0.19 ms** (your ≤0.5 ms bar; the Session Z 0.3 was
   honest but single-run). 32-face stretch re-measured the honest
   way — every clone independently driven: **4.3 ms** (the old
   2.42 ms had 24 statues sharing one face). The wall is still
   nowhere near a plaza.

Your hero_closeup + PS_BENCH=300 GPU-path re-measure stands as the
adoption closer — with today's numbers the enable hitch objection is
gone before it was filed.

**Four questions on hair, since you're in that code this week** (none
blocking; answers shape what we build next, not whether your current
path works):

1. **Alpha modes across the hair library:** is card hair BLEND
   everywhere (converted by `fix_card_hair()` to M_none +
   AlphaTestAttrib), or do any owned/planned packs author MASK or
   M_binary natively? If BLEND-authored is universal, your rewrite
   stays per-pack policy and our detection nets are already complete;
   if anything ships MASK/M_binary, `apply_alpha_masks` catches it
   with NO rewrite — worth knowing which world we're in.
2. **The 0.35 cutoff:** eyeballed or measured against the pack's
   alpha histograms? (Engine detail: geom-level AlphaTestAttrib keeps
   YOUR threshold per geom — 0.35 is honored, we're just curious
   whether it was chosen or defaulted.)
3. **Fringe quality:** at Talk-distance close-ups, does hard cutout
   read acceptably on fine strands, or are you seeing steppy edges
   where BLEND used to feather? If the latter, alpha-to-coverage
   under MSAA is the engine lever we'd evaluate (order-independent,
   no sorting, plays with the deferred-ish HDR chain) — we will NOT
   build it speculatively, but a screenshot of steppy fringe would be
   its field evidence.
4. **Hair vs morphs:** confirm hair parts never carry shape keys
   (your dead-key prune should structurally guarantee the hairline is
   bone-driven, not morph-driven) — if any pack ever keys hair to
   follow brow/jaw morphs, the one-variant-per-geom limit (morphs vs
   alpha-mask on the SAME geom) becomes real and we'd need a combined
   variant. One line in your bake log ("hair kept 0/52 keys") is a
   sufficient answer, forever.

---

# 2026-07-20 — GPU morph prototype inputs: re-export was DELIVERED yesterday; counts, pruning, perf gate (character dev)

Answering the engine desk's four questions, in their order. Short
version: the re-export question is already closed in this file, and
since it closed the acceptance content tripled — three production
heroes ship value-verified 52-key living faces today.

## 1. Re-export status: DELIVERED 2026-07-19, value-verified, gate-promoted

Not blocked — done yesterday. See "Re-export DELIVERED; all three asks
done" (2026-07-19, below) and the ENGINE ACK under it that promoted
`test_morph_gltf` to a permanent gate row (55/6/73 totals). Our
`verify_morph_glb` value-checks per-target weight peaks (1.000 at your
manifest's authored keys) on every delivery since. The A/B harness is
standing by for the prototype: the CPU-valve datapoint on file
(185→133 fps) came from `hero_closeup.py` + `PS_BENCH=300` selftests —
re-measuring on the GPU path is one run the day it lands.

## 2. Real counts, measured from the shipped GLBs (2026-07-20)

| character | morphing mesh | verts | targets |
|---|---|---|---|
| hero_kade | Sci_fi_Character_02_Human_Head | 11,650 | 52 |
| hero_wren | Female_Base_Cut_Head | 14,684 | 52 |
| hero_juno (new, s646) | Female_Base_Head_Cut | 14,561 | 52 |

- **Max targets per mesh: 52 confirmed** — the vendor authors exactly
  the ARKit set on every pack we own (character_02/03/04 alike);
  nothing bought or planned exceeds it. Size the slider table to 52.
- **Exactly ONE morphing mesh per character, structurally
  guaranteed:** the baker's dead-key prune deletes the whole key set
  from any part whose keys don't move it, so a body part can never
  carry targets into a GLB. Your per-character cost model can assume
  one morph mesh, ~11.7–14.7k verts.
- **Simultaneously driven today: ≤5** — blink L+R, one eye-glance
  pair, browInnerUp; that is FacePuppet's whole rest repertoire.
  **Design ceiling: ~16** — when Talk grows visemes, ARKit's jaw+mouth
  block runs ~10–14 concurrent on top of blink/brow. All 52 must stay
  addressable (writes are sparse, most sliders sit at 0), so if the
  table needs packing, pack for ≤16 live.
- Worst case the prototype should carry: **14,684 verts × 52 delta
  columns** (wren). Footnote on the 10,965 figure on file: that was
  kade's head-skin prim alone; his full morphing mesh, eyes/teeth/
  lashes prims included, is 11,650 — the numbers above are the whole
  mesh, which is what the GPU path allocates for.

## 3. Pruning: keep it — confirmed, and it already guards you

`strip_dead_shape_keys(threshold=1e-5)` measures every key's max
|delta| vs Basis in metres (after the metre bake) and drops the dead
ones; a part with zero live keys loses its key set entirely. On this
bundle: heads keep ~52/52, every other part exports 0. It stays — and
it's gated, not aspirational: the bake log prints `kept N/52 shape
keys` per part and §0 Step 4 reads those lines before shipping.

## 4. Perf acceptance: gate on 8 close-up faces; measure 32 once

- **Primary gate: 8 simultaneously animated close-up faces** at
  production scale (14.7k verts × 52 targets each) with per-face cost
  that is genuinely slider-push + vertex math — anything under
  ~0.5 ms total for all 8 and close faces stop being a budget item.
  That is the real design target: the player's crew plus a
  conversation circle inside the 30 m face LOD.
- **Stretch datapoint, not a gate: 32** — a full plaza moment with
  every face in LOD range. Measure it once so we know where the wall
  is before we design toward it.
- The 30 m face LOD stays either way (rested faces beyond it); the
  GPU path turns it from a budget valve into a polish choice.

Acceptance content, ready now:
`C:\python\sfb2\assets\models\characters\heroes\hero_{kade,wren,juno}.glb`
(+ `.meta.json` manifests naming the morph part and clip set).
`hero_closeup.py <name> --scene mars` produces the blink-proof shot
pair; `PS_BENCH=300` selftest is the fps harness. Any extra test
variant you want baked (stripped head, textured/untextured, other
vert counts) is one characters.json entry away — same-day turnaround.

## ENGINE RESPONSE (Session Z, 2026-07-20): the GPU morph path is LANDED — same day, gated, measured on YOUR content

Everything above went straight into the design; the prototype landed
today, pure Python/GLSL (no wheel change — the Session-X wheel you run
is already enough; it even works unchanged on stock 1.10).

**Adoption is one call per character, after load:**

```python
pipeline.set_gpu_morphs(hero_np)      # returns morph geom count
# ... drive the same CharacterSliders you drive today (FacePuppet
#     unchanged — values are read from the Character each frame) ...
pipeline.set_gpu_morphs(hero_np, False)   # exact restore, if ever
```

Remove the `set_hardware_skinning(np, False)` CPU valve where you had
it — sliders now render ON the HW-skinning path. (Do NOT combine the
two on one node: the valve CPU-applies morphs into the vertex data and
the shader would add them again.)

**Your numbers, answered with measurements (probe_gpu_morph_bench.py,
hero_wren.glb = your worst case, 14,684 × 52, 7 morph vdatas/face):**

- **The 8-face gate: MET with margin.** 8 faces driving 5 sliders each
  ≈ **0.3 ms/frame morph-attributable** (1.27 ms total scene minus the
  0.97 ms static floor), offscreen 512². Your bar was ≤0.5 ms.
- **CPU valve, same scene: 63.5 ms/frame** — the GPU path is ~50×
  cheaper at 8 faces. (Engine-side sibling of your 185→133; please
  re-run `hero_closeup.py` + `PS_BENCH=300` on the GPU path and file
  the number here — that closes your A/B.)
- **32-face stretch datapoint (measured once, as asked): 2.42 ms
  total.** The wall is nowhere near a plaza moment. Bonus mechanism
  for crowds: enable on a template FIRST, then `copy_to` — copies
  share the vdata AND the delta textures (24 copies cost 0.24 s, no
  re-bake; sliders shared with their template).
- **Slider push: 0.03 ms/frame for 8 chars × 52 sliders.** All 52
  addressable, ≤16 live (your ceiling; overflow keeps the largest
  |weight| and warns once).
- **Enable cost, one-time at load: 1.17 s + 18.3 MB delta texture per
  face** (position AND normal deltas — lighting morphs correctly, not
  just silhouettes). For 3 heroes that is ~3.5 s at load; if that ever
  hurts, say so — the bake loop is pure Python and is the first thing
  we'd optimize on evidence.

**Gate:** test_morph_gltf grew 5 checks (GPU renders sliders on the HW
path; GPU-vs-CPU-valve image rms 0.0000 single AND sparse-composed;
byte-identical opt-out) — 12/12 on both engines × both baselines; full
gate totals unchanged. Fact #15 is closed opt-in; the default pipeline
without the call is byte-identical, per canon.

**Known limits, so you're not surprised in the field:** (1) the shadow
depth pass casts the UNMORPHED silhouette (a blink's shadow at
close-up; lands on field evidence if it ever reads wrong); (2) one PBR
variant per geom — if you ever mark the morphing eye prims `set_glass`,
tell us, glass+morph would need a combined variant; (3) your per-part
key pruning stays load-bearing — pruned keys are texture rows we never
bake.

---

# 2026-07-19 (Session X part 2) — BUILD WINDOW LANDED: offscreen GL is clean; drop the workaround. + viewmodel adoption ACK + one machine-environment ask (ALL LANES)

## The GL build window landed — announcement the FPS lane was waiting for

Both fact-#18 fixes are BUILT and LIVE (user-authorized mini window,
1-min incremental build; wheel in pax3d-env, archived
`wheels_session_x\`). Measured on the new wheel: **zero GL errors per
frame in every probe phase, both baselines** (was ~60/phase);
`test_gl_clean` is now the permanent zero-GL-errors guard on BOTH
engines; full gate green. `gl-max-errors -1` now honors its
documented "no limit" (validated by code symmetry with
`report_errors_loop` — there is no longer any offscreen error source
to exercise the limit path, which is the point).

**TASK (FPS dev):** the `gl-max-errors 1000000` line in
`test_weapon_system.py` can come out whenever convenient — offscreen
harnesses no longer live under the ~20 s deactivation deadline.

## Viewmodel adoption ACK (your addendum 3, sfb2 `be4072b` / 643d)

Recorded engine-side — the register→unregister→register scene-switch
cycling, deleted scale machinery, byte-identical harness pixels, and
your field numbers (near 0.02 / far 8.0 / fov world-copy / 'clear')
are exactly the designed shape. Nothing further needed from you;
layering M2 recoil/sway on `reg.camera_np` is precisely what that
node exists for, and the 55–65° fov taste test deferred to M2 is
sensible. When you flip planetside's SSAO on someday, remember the
one-line change here is `depth_mode='range'` (Pax3D wheel only).

## Machine-environment coordination — RESOLVED same evening (game `ee861db`/643c)

**Post-script:** the sweep landed mid-gate and did it right — system
Python now carries the fork machine-wide, and the terrain dev built
`C:\python\stock-panda-env` (1.10.16 + gltf 1.3.0 + simplepbr 0.13.1)
as the engine-dev stock testbed. Engine lane verified it and repointed
every canonical paxtest command (CLAUDE.md + README); the corrected
full gate ran against it. Nothing further needed from any lane — just
never "fix" stock-panda-env to the fork. On the offered pip.ini
find-links hatch: no engine-lane objection; a deliberate
`pip install panda3d==1.10.16` still resolves stock if we ever need a
rebuild of the testbed. The section below is kept as written for the
record.

## (superseded) Machine-environment coordination (terrain dev's engine-pinning sweep — read before converting interpreters)

The "nothing runs stock Panda3D by accident" goal is right for every
game app — with ONE engine-lane constraint: **the paxtest gate
requires a deliberately-stock environment to exist.** Every "identical
on stock = upstream behavior, not fork damage" fact (#13, #16, #17,
#18) and every cross-engine gate row is measured against stock
1.10.16, which today lives in **system Python `C:\Python313`** (plus
panda3d-gltf + simplepbr there).

- Pin every game launcher/app to `C:\python\pax3d-env\` by absolute
  path — that alone makes accidental-stock impossible for games.
- Do NOT install the fork into `C:\Python313` without telling the
  engine lane. If the sweep wants system Python converted anyway,
  say so and we will move the stock reference into a dedicated venv
  (e.g. `C:\python\stock-panda-env`) and update the canonical paxtest
  commands in CLAUDE.md/README in the same change.
- Context for everyone: the user had been launching planetside via a
  direct command that resolved to system Python = **stock 1.10** —
  eyeball impressions from those runs predate the fork's feature set
  (and, until today, the fork-only offscreen GL defect). Engine facts
  are unaffected (everything is gated on both engines), but visual
  feedback given from those sessions should be re-checked on
  pax3d-env before anyone chases it.

---

# 2026-07-19 (Session X) — ENGINE RESPONSE to the FPS weapons lane: the §5 near-plane question answered before it was filed + the GL-error report root-caused

**To the FPS dev.** We read `FPS_WEAPONS_KIT.md` §5 ("engine ask
drafted, not sent") and the `gl-max-errors` comment in
`test_weapon_system.py`. Both are answered engine-side, same day —
nothing was waiting on you filing the ask.

## 1. Viewmodel display region: YES — it is now a first-class API

Your option 1 (own camera/near-far, drawn after the world) is the
right call, and it landed today, gated:

```python
vm_root = base.cam.attach_new_node('vm_root')   # hands/weapons under this
reg = pipeline.register_viewmodel_camera(vm_root, near=0.02, far=8.0)
# reg.camera_np = the created viewmodel camera, parented under the main
# camera at identity — animate IT for sway/ADS. fov=None copies the
# world FOV; pass your own (viewmodels usually run a touch narrower).
pipeline.unregister_viewmodel_camera(reg)       # exact restore
```

Everything you asked about is measured (`test_viewmodel`, 15 checks,
17 under directional+shadows, green both engines × both baselines):

- **The post chain is NOT broken — it applies to your hands.** The
  region draws after the world into the SAME HDR scene buffer, so
  tonemap analytics hold on viewmodel pixels, a hot emissive viewmodel
  feeds bloom, TAA resolves over it. PBR lighting reaches the subtree
  (luminance parity 0.848 == 0.848 against an identical world card lit
  by the same sun) — keep `vm_root` under render; under the camera is
  the blessed spot (free view tracking).
- **The mask folklore is pipeline-owned.** Draw bit 29 is reserved
  (sibling of the orbital bit 30): hands invisible to the main camera
  AND to the sun shadow camera — zero texels in the sun depth map,
  gated — so no giant hand shadows and no mask dance in game code.
  Keep bits 29/30 out of any camera masks you hand-roll.
- **Rebuild-proof**: the region + its depth state survive every
  FilterManager rebuild (bloom/SSAO toggles), same contract as the sky
  camera.
- **`depth_mode` matters the day you adopt SSAO (the Q key):**
  `'clear'` (default) clears region depth — always wins, but the scene
  depth texture is stomped full-screen and world AO reads garbage
  (measured, documented-limitation gate row). `'range'` compresses the
  viewmodel into glDepthRange [0, 0.05] — no clear, world depth
  byte-preserved (SSAO-friendly). `'range'` needs the Pax3D wheel
  (stock 1.10 has no `DisplayRegion.set_depth_range`; auto-falls back
  to 'clear' with a warning) and is incompatible with
  `enable_log_depth` (gl_FragDepth is clamped, not rescaled, to the
  region range; auto-falls back and says so).
- Nuances measured so you don't have to: TAA jitters only the world
  lens (viewmodel unjittered — no ghosting, marginally less temporal
  AA on hands); in 'range' mode world geometry inside ~0.32 m of the
  camera still wins depth (a ~2 cm shell past the world near plane) —
  the standard walls-clip-hands FPS behavior, invisible in practice.

Your §5 option 2 (uniform scale about the camera) can be deleted once
this is wired; `min_cam_dist_m` in your metas stays useful for
choosing per-weapon `near` if you ever want tighter than 0.02.

**TASK (FPS dev):** wire the WeaponSystem viewmodel root through
`register_viewmodel_camera`, delete the scale fallback, and report
field numbers (FOV taste, far plane, sway feel on `reg.camera_np`).
API details: `PAX3D_RENDER_ARCHITECTURE.md` §6.1.

## 2. Your GL-error report: root-caused — it was never about characters

Filing the line number was gold
(`glGraphicsStateGuardian_src.cxx:4817` is exactly the `-1` bug). But
the attribution measured wrong, in an interesting way — probe matrix
(`tools/paxtest/probe_gl_errors.py`):

| Config | GL_INVALID_OPERATION |
|---|---|
| Pax3D, offscreen, EMPTY scene (both baselines) | **1 per frame** |
| Pax3D, offscreen, character static / playing / posed | 1 per frame (unchanged) |
| Pax3D, real window | 0 |
| stock 1.10.16, offscreen | 0 |

The character is irrelevant — every offscreen frame errors, and it has
since the fork began (the Window-1 pre-surgery wheel reproduces).
Root cause: an upstream 2024 commit (`bd4dc8a379` — ironically a
**DX9** buffer fix; we deleted DX9 entirely) gutted the
single-buffered branch of `FrameBufferProperties::get_buffer_mask()`,
so the engine calls `glDrawBuffer(GL_BACK)` on the single-buffered wgl
pbuffer every display-region prep. The once-per-second error sweep
then reaches `gl-max-errors` (20) and panic-deactivates the GSG.
One correction to your comment: it deactivates after ~20 **seconds of
wall time** (the sweep is 1/s), not 20 frames — same trap, different
clock. And your `-1` read was exactly right: the sweep's bare `>=`
makes -1 deactivate on the FIRST error while `report_errors_loop`
honors it as unlimited.

Both fixes are one-line C++, queued for a user-authorized mini build
window (`documents/PATCH_QUEUE_GL_OFFSCREEN.md`); `test_gl_clean`
asserts today's defect per-engine and flips "the good way" when the
patch lands. Master plan fact #18.

**TASK (FPS dev):** keep the `gl-max-errors 1000000` workaround until
we announce the window landed — anything offscreen running >20 s needs
it. After the window: `-1` works as documented, and your workaround
comment can shrink to a pointer at fact #18. Worth truing up the
"playing character" attribution in `FPS_WEAPONS_KIT.md` §7 when you
next touch it. One technique from your report worth stealing
game-side: pin the global clock to dt>1 s and the engine's 1/s error
sweep becomes per-frame — free GL-error attribution on release builds.

---

# 2026-07-19 (evening) — First visor-off hero SHIPPED on the CPU valve; two field notes (character dev)

The morph lane paid off same-day: a hero NPC from a second CGTrader
pack (UE4 mannequin, 52 authored ARKit blendshapes on an 11k-vert head
module) is posted in the Mars colony — blink/eye-dart/brow ambience
driven straight through CharacterSliders (apply_freeze_scalar), head on
`set_hardware_skinning(np, False)`, body hardware-skinned. Verified
in-pipeline by screenshot (eyes close, jaw opens), scene-switch green.

Two field notes, neither urgent:

1. **CPU-valve cost datapoint for the GPU-morph-path decision:** your
   ~+0.1 ms was the 2,240-vert test head; our production head module
   (10,965 verts + eyes/teeth/lashes) measures **~+2 ms** (185→133 fps
   at the selftest camera). Fine for one hero — we toggle the valve
   with a 30 m face LOD so it's only paid up close — but it scales the
   "crowd of faces" argument: ~5 close-up morphing characters would eat
   10 ms on CPU. Sharpens the case for the queued GPU morph route.
2. **Textureless alphaMode-MASK renders opaque white** under the
   pipeline: a MASK material with baseColorFactor alpha 0 and NO
   texture (the pack's makeup-shell overlay) drew as a solid white
   shell over the hero's eyes. glTF says MASK + alpha 0 ⇒ discarded.
   We route around it (delete the faces at bake — shipping invisible
   geometry was wrong anyway), so no ask; noting it since other glTF
   content with factor-only MASK alpha would hit the same thing.

## ENGINE RESPONSE (Session W, 2026-07-19) — MASK root-caused + fixed; datapoint recorded

**Note 2 was a real engine-lane defect and it is now fixed, gated, and
bigger than your case.** Root cause (read from the GL backend source,
then measured): panda3d-gltf expresses `alphaMode MASK` as a geom-level
`AlphaTestAttrib`, and the engine implements that attrib ONLY via
fixed-function `GL_ALPHA_TEST` — a compat-profile feature. Your build
runs `gl-version 3 2`, where the attrib is **silently ignored**, so
EVERY Mask material renders opaque there — not just factor-only ones:
textured cutout foliage becomes solid cards too. (Identical on stock
1.10.16 — upstream behavior, the core-profile combine drop's sibling.
Master plan fact #17.)

The fix is one opt-in call after loading any model with MASK materials:

    n = pipeline.apply_alpha_masks(model_np)   # -> masked geom count

It composes an ALPHA_MASK compile of the PBR shader onto exactly the
geoms carrying the loader's attrib (cutoff baked in; in-shader discard,
same keep-if-greater predicate as the fixed-function test — measured
BIT-identical on compat, so it is safe to call unconditionally under
either baseline). `apply_alpha_masks(np, False)` restores byte-
identically. Gate: `test_alpha_mask`, green both engines × both
baselines, including your exact case (factor alpha 0, no texture).

Your bake-side deletion stays the right call for permanently-invisible
geometry (don't ship faces you never draw) — use the API for content
where the mask is the point (foliage, grilles, decals).

One caveat to know before you meet it: the shadow depth pass has no
per-geom alpha knowledge, so under gl 3 2 a masked caster still casts
its UNMASKED silhouette (compat gets cutouts from the fixed-function
test). For invisible shells use `exclude_from_shadows()`; if cutout
foliage shadows ever matter to a shot, report it — the depth-pass
variant is queued on field evidence.

**Note 1 (the ~+2 ms production-head datapoint) is recorded** in the
GPU-morph queue row (CLAUDE.md + master plan) with your numbers
(10,965-vert head, 185→133 fps, ~5 close faces ≈ 10 ms). It sharpens
the evidence but doesn't change the trigger: the GPU morph path lands
behind field-driven demand for close-up morphing crowds, and your
30 m face LOD is exactly the right bridge until then.

---

# 2026-07-19 (later) — Re-export DELIVERED; all three asks done (character dev)

Response to ENGINE RESPONSE 2. The gate row is unblocked — all three
asks landed the same day:

**1. The re-export is in `tools/paxtest/assets/` (all files
refreshed).** Root cause of the empty weights channel: Blender 5
slotted actions don't resolve a shape-key action's slot through an NLA
strip — the exporter finds the track and silently samples zeros. The
anim variant now exports via ACTIVE_ACTIONS (both actions named
`FaceTest`; the exporter merges them under its default name
`Animation` — find the clip by structure, not name). The 24-vs-30 fps
defect: FBX import restamps the scene fps; the baker now re-asserts
30 before every export. A terminal key at frame 90 pins the weights
channel to the declared clip length. Both traps are in the game-side
playbook now.

**2. Your `max(weights) > 0` ask, exceeded:** verify_morph_glb now
decodes the BIN chunk and value-checks every animation sampler —
per-target weight peaks (must reach ~1.0), weights-channel duration vs
manifest fps, and rotation-actually-varies. Run against the OLD
delivery it reproduces your diagnosis exactly (max weight 0.000 over
2 keys, 3.292s vs 2.967s); against the re-export it's ALL CHECKS PASS
(90 keys × 3 targets, per-target peaks 1.000, 2.967s exact).

**3. `gltf_compat.install()` wired unconditionally at every game-side
loader boot:** `planetside/bootstrap.py::add_engine_path()` (launcher +
all test suites), `graphics/pax_pbr/__init__.py` (plan.py / test3d
apps under use_pax3d_render), and both character tools. Verified
no-op on existing content: 4/4 character verify, Mars selftest 179 fps
with the palette log intact, scene-switch suite green. End-to-end
proof through the shimmed loader game-side: all three sliders arrive
as CharacterSliders and the clip loads at 3.0s — the same file that
crashes the stock loader.

Fact #16 noted in the playbook: the hero-NPC valve applies to any
morphing node including joint-less heads; ~+0.1 ms/frame is a price
we'll happily pay for the first visor-off face. When you promote
test_morph_gltf to a gate row, we're ready to supply any variant it
still needs (textured head remains one config line away).

## ENGINE ACK (2026-07-19) — gate row PROMOTED; morph lane is closed end-to-end

Re-export verified and **test_morph_gltf is a permanent gate row as of
this session** (in run.py's ALL_TESTS; new expected totals 55 PASS /
6 documented FAIL / 73 SKIP per engine). The authored clip measures
perfect through Actor on BOTH engines: per-slider peaks 1.00 at frames
10/38/68 — exactly your manifest's authored keys — zeros at frame 0,
peak order correct, structural clip pick handling the 'Animation'
merge (good trap note; it's in the test's docstring). The row also
permanently guards the shim, delivery on skinned + joint-less meshes,
CPU truth vs your manifest, and the fact-#16 render split (with an
explicit note that hw_drops_morphs "failing the good way" means the
GPU morph path landed). Your slotted-action/NLA root cause + fps
restamp trap are exactly the class of export defect the value-checking
verifier will now catch on your side before it ever reaches ours —
the two instruments now cover both halves of the pipeline. Nothing
further needed from you; the GPU morph route is now queued as a named
build-window candidate with a complete measurement basis.

---

# 2026-07-19 — Morph paxtest asset DELIVERED (character dev)

The SK_SFM_Head1 asset you accepted is in `tools/paxtest/assets/`,
baked by `sfb2/tools/character_pipeline/blender_build_morph_head.py`:

| File | What it is |
|---|---|
| `morph_head_static.glb` | the bare head (2,240 Blender verts) + 3 shape keys (`blink`, `jaw_open`, `brow_raise`), NO armature |
| `morph_head_skinned.glb` | same mesh skinned to a 9-bone spine chain — deliberately tiny so the default 100-bone palette is never the variable under test |
| `morph_head_skinned_anim.glb` | skinned + ONE clip `FaceTest` (90f/30fps) with glTF `weights` channels AND a head-yaw bone channel in the same animation — channel coexistence is testable in a single clip |
| `morph_head_manifest.json` | ground truth: per-key moved-vert counts, max deltas, full-mesh AABBs at weight 0/1, max-delta point positions — in Z-up metres as panda3d-gltf re-loads them. Assert against these, not vertex indices (GLB export reindexes). |
| `qa/*.png` | front-view renders of each key at 1.0 — what "working" looks like (the blink shelf is unmissable) |

The shape keys are analytic region displacements (1–2.2 cm), sized for
unambiguous measurement, not beauty. File-side integrity is already
proven game-side (`verify_morph_glb.py`: targets + names + delta bounds
+ skin joints + channel classes, all green on all three GLBs) — so
whatever the loader fails to deliver is a loader fact, not export loss.
This unblocks your (a)/(b)/(c) measurement plan from the 2026-07-18
section. If a textured variant would help eyeball work, it's one config
line — say the word.

## 151-bone re-bake SHIPPED + the 81-vs-151 A/B you asked for — measured, surprising

All four military characters re-baked `keyed`/151 (one-line
`bone_budget` 100→200), 4/4 verify green, and the game now runs
`max_skinning_bones='auto'` + `refresh_skinning_budget()` after every
scene build (planetside/app.py + lifecycle.py). Field confirmation of
your Session-S work, all live: palette resolves 160 on Mars (151-bone
rigs), 128 in the village (64-bone rigs), scene-switch suite green
across the resolve boundary, in-game skin verified whole by screenshot
under hardware skinning, 185 fps selftest (no regression).

**The A/B verdict: the deformation win does not exist for this pack's
demo clips.** Measured pose-matched at Idle/Walk×2/Run poses
(`sfb2/tools/character_pipeline/ab_bone_compare.py`, CPU-animated
vertex truth, your probe_morph technique): max vertex deviation
81-core vs 151-keyed = **0.33 mm** on a 1.8 m character (officer:
0.00 mm), pixel diff 0.0% at 512². The correctives these demo clips
"key" are effectively rigid to their parents — the 81-bone weight
merge was already lossless *for these clips*. Your "merging loses
nothing for these clips" caveat is now a measured fact, and it extends
to the 81↔151 gap, not just 151↔343.

Implications as we read them: (1) we ship 151 anyway — zero measured
cost, and it keeps the whole >100-bone path exercised in production
before a real animation pack needs it; (2) the texture-palette C++
item loses more urgency — even the mid-band correctives buy nothing
until richer clip sets arrive, so it can comfortably wait for a
convenient build window; (3) by elimination, the morph lane is now
unambiguously the character-quality bottleneck — the head asset above
is the gate.

## ENGINE RESPONSE 2 (2026-07-19) — our reports crossed: the morph verdict is already IN

Your "next engine session measures the morph head" happened the same
day the asset landed — the full verdict is in the ENGINE RESPONSE
inside the 2026-07-18 entry below. Short version, plus what only you
can do next:

**Morphs work; the wall was the loader, and it's shimmed.** Stock
panda3d-gltf 1.3.0 can't load ANY Blender-default morph export (sparse
accessors, upstream Moguri#103) and has two more bugs behind that
crash (short-channel IndexError; a max-for-min lerp clamp that snaps
LINEAR samples to the next key — joints too). All three are fixed by
`pax3d_render.gltf_compat.install()` — **add it to the baker/pipeline
boot unconditionally**: it is a no-op on your existing morph-less
bakes and required for every morph-bearing GLB from now on. With the
shim, your morph geometry measured perfect: all sliders delivered,
CPU truth matched your manifest to 4 decimals on both variants, and
the manifest's numbers-not-indices design worked exactly as intended.

**Your "loader fact, not export loss" claim held for everything except
one value your verifier can't see:** the FaceTest weights channel in
`morph_head_skinned_anim.glb` is all-zero in the file (2 keys, nothing
between), and the timeline exported at 24 fps against the declared 30.
The shape-key action never reached the exporter — container presence
green, values empty. We proved the loader side works anyway by
byte-patching a nonzero ramp into your GLB (sliders track it
analytically), so the **re-export is the single remaining blocker**;
when it lands we promote the probe to a permanent gate row
(test_morph_gltf) with the real clip. Please also add a
`max(weights) > 0` check to verify_morph_glb so the next empty export
names itself game-side.

**Lane 2 ratified, one caveat kept alive.** The 0.33 mm A/B is a
model measurement (and ab_bone_compare adopting the probe technique is
the cross-pollination working as designed) — we've annotated the
texture-palette queue item as deprioritized-until-richer-clips on your
evidence. The caveat: purchased Manny-compatible animation packs may
key correctives your demo clips don't — nothing to do now; the audit
will name the first rig/clip combination that outgrows the palette,
and 'auto' resolving 160/128 live in your scenes is exactly the
designed behavior. Shipping 151 to keep the >100 path hot in
production is the right call.

**On the hero NPC today: yes, with one nuance from fact #16.** The
scene-wide hardware-skinning flag drops morphs even on JOINT-LESS
meshes — so a static talking head needs the valve too, not just
skinned characters: `set_hardware_skinning(np, False)` on the morphing
node, measured at ~+0.1 ms/frame for the 2,240-vert head. One
visor-off face is effectively free; the crowd path stays gated on the
GPU morph route, which your re-export A/B now decides the build-window
shape for (it shares the skinning vertex shader with texture-palette,
so one window can still land both when the user schedules it).

---

# 2026-07-18 — Characters, bones & animations (from the sfb2 character-pipeline build, Session 618)

**Context:** first realistic rigged humanoids shipped in planetside — the
CGTrader "Sci-fi Military" pack (UE5 Manny skeleton) baked to GLB by
`sfb2/tools/character_pipeline/` and posted in the Mars colony. Everything
below was measured on that pack; playbook in
`sfb2/documents/PLANETSIDE/CHARACTER_PIPELINE.md`.

## Response to your bone-palette note — measured numbers for sizing the spike

The pack's skeleton, as our baker sees it:

| Set | Bones | What it is |
|---|---|---|
| Full rig | 352 (343 sans IK/utility) | every deform bone incl. the detailed-hand corrective set |
| **Clip-animated** | **151** | union of bones the pack's own demo clips key, + ancestor closure — nothing outside this set ever moves in these clips |
| Hand-authored core | 81 | what we ship today under `p3d_TransformTable[100]` |

So the concrete target: **a 192 table covers every animated bone with
margin; 256 gives headroom for richer clip sets.** The bones between 151
and 343 are finger-corrective helpers that the clips never key — merging
their weights loses nothing *for these clips*, so chasing 343 buys
nothing today.

The pipeline is already parameterized for the day you raise it: baker
strategies `core` (81) / `keyed` (151) / `all` select automatically
against a `bone_budget` config. We test-baked the 151-bone `keyed`
variant and round-trip-validated it (corrective drivers like
`thigh_fwd_l` animate correctly) — the moment the table is ≥192 behind
the harness, we re-bake all characters with a one-line config change and
you get a real A/B (81-core vs 151-keyed elbows/shoulders) to measure
the deformation win on.

One request with the spike: bump BOTH vertex shaders together (main +
shadow) in engine and confirm the identity-padding fact (#10) holds at
the new size, so short rigs (our 81s, the ITHappy villagers) keep
working unchanged.

## Morph targets — paxtest asset offer

Agreed it's a measure-first unknown. We can supply the test asset from
this pack: the bare-head module (`SK_SFM_Head1`, 2,240 verts) with
authored shape keys (blink/jaw/brow) exported both ways — morphs on a
skinned mesh and morphs on a static mesh — so the paxtest can establish:
(a) does panda3d-gltf deliver sliders at all, (b) what happens under
`F_hardware_skinning` (silently ignored? CPU path? garbage?), (c) cost
of the CPU fallback per character. Say the word and we'll bake it to
`paxtest/assets/`.

Near-term game-side need is honest-but-mild: dialogue close-ups are on
the roadmap (textad portraits exist; 3D talking heads are not scheduled
yet). Right now every posted character except one wears a sealed visor
partly BECAUSE faces can't move — so the cap is already shaping content
choices, but nothing ships broken.

## ENGINE RESPONSE (2026-07-19) — SK_SFM_Head1 measured: morphs WORK, one re-export needed

Your asset is measurement-grade — the manifest's assert-numbers-not-
indices rule and the 9-bone skeleton isolation both paid off. Full run:
`probe_morph_gltf.py`, 26 facts, **identical on stock 1.10.16 and
Pax3D** (so everything below is loader-layer truth, not engine-specific).

**The headline: panda3d-gltf 1.3.0 cannot load your GLBs at all** —
`KeyError: 'bufferView'` — and it's not your export. Blender writes
shape keys as SPARSE accessors (bufferView legally absent), which is
spec-valid and upstream-broken (Moguri/panda3d-gltf#103). Two more
loader bugs sit behind it: a crash on any anim channel that ends before
the clip's global end (yours do — weights end 3.33s, joints 3.75s), and
a `max()`-for-`min()` clamp that snaps every LINEAR interpolation to
the next keyframe (affects JOINTS too; dense per-frame bakes mask it,
sparse keys like yours don't). All three are fixed in the engine repo:

```python
from pax3d_render import gltf_compat
gltf_compat.install()   # once, before loading; no-op on clean files
```

Add that to the baker/pipeline boot and your GLBs load. With it
installed, everything you shipped measures correct: all three sliders
delivered, CPU truth matches your Blender ground truth to 4 decimals
(max-delta vertices exact on both variants), and the weights→slider
animation path works end-to-end — we proved it by byte-patching a
nonzero ramp into your GLB and watching the sliders track it
analytically.

**One thing needs a re-export: the FaceTest weights channel in
`morph_head_skinned_anim.glb` is empty.** The file contains 2 keyframes
of all-zero weights — the shape-key action didn't reach the exporter
(the classic gotcha: the action must be on the MESH's shape-key
animation data, active or stashed per your exporter's animation mode,
not only on the armature). Also the timeline exported at 24 fps (joint
keys end at 3.75s = frame 90 @ 24) while the manifest declares 30 —
set the scene fps or fix the manifest so the slider_keys frame numbers
mean what they say. The joint yaw channel exported fine.

**Render-path verdict for your content planning (fact #15 extended):**
hardware skinning drops glTF morphs exactly as it drops egg sliders —
and the scene-wide flag drops them on JOINT-LESS meshes too, so even a
static talking head needs the valve: `set_hardware_skinning(np, False)`
per morphing node. Cost measured at ~+0.1 ms/frame for the 2240-vert
head — one dialogue close-up is nothing; a crowd of morphing NPCs is
not this path (the GPU morph route is queued engine-side behind your
re-export A/B). Sealed visors can start coming off.

Yes to the textured variant when convenient — not needed for the
measurement (done), but it will serve the testbed eyeball rig when
dialogue-face tuning starts. One note on your verifier: it checks
channel PRESENCE, which passed while the weights VALUES were all zero —
worth adding a `max(weights) > 0` check so the next empty export names
itself game-side.


- 81-bone GLBs skin correctly under the pipeline: correct shadows, no
  concertina, Megacity + Mars verified by offscreen screenshot.
- 4-influence cap is fine at NPC camera distances — agreed, no ask.
- SSS/skin shading — agreed, queue behind a real close-up feature.
- Per-node `set_hardware_skinning(np, False)` remains our safety valve;
  unused so far.
- A warning would have saved us an hour: a >100-bone skin renders
  *plausibly-exploded* garbage with no log line. If the skinning path
  can cheaply detect `joints > table_size` and print ONE warning, future
  character work debugs itself. (Low priority; our verifier now gates
  this game-side.)

## Owned game-side (not asks)

Emission-mask glTF loss — FIXED in the baker (rewire to Emission Color;
glow accents now arrive as glTF emissive textures). Per-GLB texture
duplication (~45 MB each, skins share atlases) — baker backlog, we'll
dedup when character count justifies it. Emote clips, FPS-hands bake,
weapon-in-hand via the kept `weapon_l/r` sockets — game-side roadmap.

---

# 2026-07-17 evening — Session E adoption + one NEW P0, one NEW P1

## Adoption report (your Session E handoff — all four items done)

1. **Proxies deleted** — `_build_shadow_proxy()` and the per-NPC attach are
   gone from `game/npcs.py`. Your root-cause held up: our depth-map diff was
   contaminated by the proxy in the same light-space column, and your nine-way
   green matrix (incl. our own `f_1.glb`) settles the skinning path.
2. **World-unit bias** — `SHADOW_BIAS_WORLD = 0.18` in `game/config.py`,
   `shadow_bias_world=` in init. Verified identical at depth 600.
3. **3×3 PCF** — `shadow_filter_size=3` (env `OW_PCF` to switch). Visibly
   softer edges in the world-hidden A/B (see below); no acne at 0.18m bias.
4. **Blessed no-cast API** — `shadow_caster_mask=1` in init; the manual
   `sun_light_np.node().set_camera_mask(...)` line is deleted;
   sky dome + cloud root now use `pipeline.exclude_from_shadows()`.

**Confirmation numbers** (1600×900 offscreen, OW_BENCH=300):
village 40 NPCs **112 fps** (103 with proxies yesterday), mars 30 NPCs
**178 fps**. CPU-skinning datapoint for context: `OW_NO_HWSKIN=1` drops the
village to **8 fps** — hardware skinning is load-bearing at our NPC counts.
The NPC shadow on/off luminance you asked for is **blocked by the new P0
below** — in-game lit shadows are currently absent entirely. It's queued as
the first measurement once the P0 is fixed.

## NEW P0 — Lit-pass shadows vanish when glTF scene content is in frame

**Symptom:** in every scene, no geometry receives cast shadows (buildings,
trees, NPCs, test boxes — nothing), even though the shadow map itself is
correct. Regression window on this machine: working screenshot at 03:36
(`screenshots/rebalanced_16.png`), broken by 04:29. Engine pins at
`master`, `a43cfba7`, `dbbf63ba13`, and `474cd57~1` all reproduce, so it
predates Session E part 2 — but 03:36 worked, so *something* in that window
(engine or a runtime ingredient we can't reconstruct — openworld has no VCS)
flipped it. Either way it reproduces mechanically today:

**Two-command repro (the whole bug in one A/B):**
```
OW_BOXTEST=1 python main.py --scene village --selftest --hour 16 --shot a.png
OW_BOXTEST=3 python main.py --scene village --selftest --hour 16 --shot b.png
```
Variant 1 hides the world and drops a flat-colour card box + plane at the
camera: **perfect soft shadow** (your PCF, bias, follow-frustum all work).
Variant 3 keeps the village visible and puts the same box on the road:
**no shadow, anywhere, including the box**. The only variable is whether
the glTF world participates in the frame.

**What we measured (all scripts reproducible on request):**
- The 4096² `pax3d_sun` depth map is **content-correct and lens-consistent**:
  extracted stored depths equal lens-projected expected refs to 4 decimals
  on open ground; occluders (trees, houses) present at plausible depths.
  Exactly one shadow buffer exists (sort −10, first), one GSG for all
  buffers.
- **Bias sweep:** at bias 0 the scene shows broad smooth acne bands (so the
  GPU compare works and receivers roughly self-compare); at 0.00005–0.0003
  acne fades directly to *nothing*. There is **no bias value at which real
  occluder shadows appear** — occluders 3–30m deep in the verified map never
  darken their receivers.
- **Mode-10 decode:** inverting the hejl-dawson tonemap on your debug mode
  10 output (bloom off) shows the shader's sampled (u,v,ref) deviating from
  lens truth **irregularly and position-dependently** — near-zero error at
  some ground points, +10..20m at others. A best-fit constant offset
  (−12.3m, −9.8m in film space) explains only 83% of observed shadow terms
  (64% at zero offset) — i.e. it is NOT a clean matrix translation/scale;
  it behaves like per-vertex corruption of `v_shadow_pos` interpolation for
  glTF-material geometry.
- **Eliminated by experiment:** night lights, weather/fog/clouds, NPCs, HUD,
  sky dome, bucket flattening, bam-cache vs fresh parse, our prc set, camera
  lens/fov/mask, sun camera mask, caster-mask kwarg vs manual, PCF 1 vs 3,
  normalized vs world bias, max_lights 10 vs 4, camera/world position
  magnitude, per-frame update_sun, per-frame follow recentre. A standalone
  pax3d_render scene with all our init kwargs + the village GLB loaded fresh
  does NOT reproduce — the trigger needs the full app scene graph, which is
  why the two-command in-app repro above matters.
- **Your own harness already shows it in miniature:**
  `gltf_caster_ground_lum` prints `pole lum 0.800 under the actor
  (no-caster baseline 0.800)` — a glTF Actor that verifiably wrote 2804
  depth texels darkens the ground by exactly nothing, and the line is
  `[info]` so it can't fail. **Ask #1: promote that to an assertion.**
  **Ask #2: add a lit-shadow test where glTF-material geometry is both
  caster and receiver** (e.g. f_1.glb + a card over a textured glTF plane,
  assert ground darkening) — flat-colour scenes demonstrably cannot catch
  this class of bug.

Debug hooks we added game-side that you can reuse: `OW_DEBUG_LIGHTING=10|11`
(your modes), `OW_BIAS=<v>`, `OW_PCF=1|3`, `OW_MAX_LIGHTS=n`, `OW_NO_BLOOM`,
`OW_NO_LIGHTS`, `OW_NO_WEATHER_SYS`, `OW_NO_NPCS`, `OW_NO_HUD`,
`OW_BOXTEST=1|2|3`.

## NEW P1 — Hardware skinning deforms 94-joint Rigify rigs (concertina necks)

Our second character pack (`Casual Characters 2`, 25 models) exports the
full Blender Rigify control rig into the glTF skin: **94 joints** including
`MCH-*`, `ORG-*`, `tweak_*`, `*_fk` control bones, plus **animated scale
channels** on the `DEF-spine.*` deform bones (ranges up to ±21% per axis).
On the **hardware skinning path** these characters walk with pogo-ing heads
and accordion necks; on the **CPU path they render perfectly**
(`screenshots/lineup_hw_a.png` vs `lineup_cpu_a.png` — pack-1 and pack-2
models side by side, same frame). Pack 1 (64 joints, DEF bones only,
constant scale) is correct on both paths. Both packs use a single
JOINTS_0/WEIGHTS_0 set (4 influences), both under your 100-joint cap.

- Repro: `Actor('3D assets/Casual Characters 2/f_1.glb')`, `loop('Walk')`,
  compare `enable_hardware_skinning` True/False.
- Suspects worth a look: palette indexing when the skin's joint array is
  dominated by non-deform control bones; composition of animated non-uniform
  scale through the GPU palette (Blender "inherit scale: off" semantics
  can't survive glTF; the CPU path evidently composes what the exporter
  baked, the GPU path doesn't).
- **Ask:** fix, or give us a per-node hardware-skinning opt-out (global CPU
  is 112→8 fps at our NPC counts). Interim game-side: pack 2 is benched from
  the NPC pool (one commented line in `config.py` restores it).

---

## P0 — Skinned meshes cast no shadows (bug) — **RESOLVED 2026-07-17 (Session E: not an engine bug; bias trap + contaminated measurement. Proxies deleted.)**

Any glTF character (panda3d-gltf `Character` node) contributes **zero
texels** to the sun shadow depth map. Plain geometry at the same spot casts
fine. Same result with `enable_hardware_skinning=True` and `False`.

- Evidence: freeze the sun, extract the `pax3d_sun` buffer texture, diff
  with/without an Actor — 0 changed texels; a `CardMaker` card changes 32+.
- Suspected mechanism: the depth pass applies `shadow.vert/frag` via the
  shadow camera's *initial state* (`pipeline.py` `_update` caster loop →
  `_create_shadow_shader_attrib`). In that path `p3d_TransformTable` never
  gets bound, so `skin_matrix` sums to zero and skinned vertices collapse
  to a point. `pax_pbr.vert` uses the identical skinning block and works in
  the main pass.
- The pipeline docs say the shadow pass "compiles with skinning so skinned
  meshes cast correct shadows" — it compiles, but paxtest has no skinned
  caster, so it was never exercised.
- **Game workaround (delete when fixed):** `game/npcs.py`
  `_build_shadow_proxy()` — invisible low-poly prism per NPC, hidden from
  the main camera, visible to the shadow camera.
- **Ask:** bind the transform table in the depth pass (or force CPU skinning
  there); add a paxtest case: one animated Actor over a plane, assert its
  texels appear in the depth map.

## P1 — `shadow_bias` is in normalized-depth units

`light_space_coords.z -= global_shadow_bias` means world-space offset =
`bias × frustum_depth`. The 0.005 default = 0.3m in paxtest's 60-unit
frustum but **12.5m** at open-world `set_shadow_extent(450, 2500)` — every
shadow silently vanishes with no artifact hinting why. Single most
expensive debugging trap of this project.

- **Ask:** accept bias in world units (divide by `_shadow_depth`
  internally), or a prominent docstring + a paxtest check at non-toy scale.
  Slope-scaled bias would be a bonus.
- We ship `shadow_bias=0.0003` with depth 600 (= 0.18m).

## P1 — Shadow filtering & stability

Single hardware-PCF tap → hard, crawling edges. We mitigated game-side;
the engine could own all three:

1. **Multi-tap PCF** (3×3 in `shadow_caster_contrib`) — biggest visual win
   per line of code.
2. **Texel snapping** inside `set_shadow_extent(center=)` — see
   `game/app.py:_follow_shadow_frustum` for the light-space snap; without
   it every recenter shimmers all shadow edges.
3. **Sun-motion quantization guidance or cascades** — a creeping
   time-of-day sun sub-texel-shifts every shadow each frame. We quantize
   the sun direction to 0.1° steps (`game/daynight.py`). Long-term: CSM.

Session D's world-space `center=` parameter is exactly right — adopted the
day it landed; on-foot texel density went from 22cm to 7cm.

## P2 — paxtest coverage gaps

How the above survived "harness-proven": `test_shadows.py` only tests a sun
at exactly (0,0,1), toy scale, camera at origin, no skinned geometry. Its
shadowed sample point is only valid overhead — an angled-sun variant
reports NO SHADOW even on a healthy pipeline because the occluder's shadow
misses the r=2 sphere entirely (this misled us for a session).

- Suggested cases: angled sun ~30° elevation with an occluder-over-plane,
  40× scale, camera far from origin, skinned caster, moving-sun shimmer.
- Depth-map diff tests must freeze the sun first — any frame stepping with
  live game time shifts the whole map when the sun crosses a quantum.
- **Debug modes 10/11** (shadow UV / shadow term) were added to
  `pax_pbr.frag` in both repos, guarded by `#ifdef ENABLE_SHADOWS` — they
  were decisive in every diagnosis here; please keep/upstream.

## P2 — Blessed "don't cast shadows" API

Drifting cloud meshes crossing the sun ray blanket the whole play area in
one giant moving shadow (this was most of the reported "flickering
shadows"). Fixed via `sun_light_np.node().set_camera_mask(bit)` +
`node.hide(bit)` (`game/app.py`, `game/weather.py`) — works, but it's
undocumented folklore. A `pipeline.set_shadow_camera_mask()` or per-node
opt-out would make it discoverable.

## P3 — Nice-to-haves

- **Env-derived ambient (planned R5):** shadow readability is dominated by
  the sun:ambient ratio; our hand-tuned flat AmbientLight initially washed
  16:00 shadows to an invisible 11% delta ("gamma too high" feel).
  SH-from-skybox ambient solves this class automatically; our skyboxes are
  already float textures.
- **Runtime fog toggle:** `enable_fog` is an init-time define; density-0
  works as "off" but a true toggle would be cleaner.
- **Clustered/tiled lights someday:** Megacity ships 781 lampposts; the
  forward budget is ~6 point lights + sun.
- **Flaky assertion:** intermittent abort at `shaderAttrib.cxx:471` when
  `set_debug_lighting` is called immediately after pipeline init
  (offscreen; seen twice, not on-demand reproducible).

## Confirmed working — data points, no asks

- Session D bloom fix verified in-game; we run `enable_bloom=True`.
- panda3d-gltf + Actor + hardware skinning through the PBR pipeline: first
  real exercise of this path (chars are 64–94 joints, under the 100 cap);
  only the shadow pass is broken.
- Model cache: 60MB village GLB = ~20s first parse, 0.3s thereafter.
- Native Radiance `.hdr` float textures (whole sky pipeline rests on it).
- `update_sun` / `set_exposure` / `set_shadow_extent` per-frame: as
  documented.
- Performance: ~103–115fps offscreen @1600×900 with 40 animated NPCs,
  4096² shadows, MSAA 4×, bloom on. Game-side we flatten the 1,250-node
  village GLB into 44 spatial buckets.

**Headline asks:** fix skinned shadow casting, make bias world-unit, add
3×3 PCF — those three turn shadows from "needs workarounds" into "just
works" for character games on this engine.
