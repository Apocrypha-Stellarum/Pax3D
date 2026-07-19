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
`master`, `02eb9c37`, `5ce5ef2911`, and `2499ecc~1` all reproduce, so it
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
