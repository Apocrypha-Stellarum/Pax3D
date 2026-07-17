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
