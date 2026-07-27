# Pax3D Changelog

A curated record of what has landed, newest first. Every entry below shipped
with paxtest coverage — the full evidence trail lives in
`documents/PAX3D_MASTER_PLAN.md` (session log) and the commit history.

## 2026-07-27

- **Photo mode:** `render_snapshot()` — one-shot full-pipeline renders
  (PBR/shadows/atmosphere/SSAO/bloom/flare/tonemap) from any pose into a
  RAM-backed texture without perturbing the player's view; repeat shots in
  milliseconds. Optional one-frame shadow recentring (`shadow_center=`).
- **Visibility queries now fail loudly:** `visibility_query_valid`, per-query
  `.valid`, fail-closed when a depth-format degrade would poison results.
- **`set_detail_maps` registration is append-only** — O(entry) instead of
  O(everything registered); fixes a measured 60→32 fps regression on
  300-chunk voxel terrain.

## 2026-07-26

- **`bind_thread` lifetime pin (C++):** binding a foreign thread now holds a
  reference for process lifetime — fixes a use-after-free crash class when
  callers drop the returned handle (reproduced from a field report; gated by
  `test_thread_bind`).
- **Character detail maps:** `set_detail_maps()` — per-geom normal-map and
  occlusion composition with NaN-tangent guards; composes with the
  hardware-skinning valve and shadow casters.
- **`spawn_effect(fade_out=)`** — end-of-life coverage/emission ramp for
  baked effects.

## 2026-07-24

- **Cross-thread geometry stability window (C++):** restored deleted-chain
  allocation alongside mimalloc, cycler stage guards, and a
  `set_num_stages` interior-delete fix — kills a reproducible heap
  corruption under threaded mesh churn (6.9M-build soak green; permanent
  `test_gvad_churn` gate).
- **Wet-sand waterline:** `set_terrain_water()` — world-Z wetness band with
  darkened/saturated albedo, reduced roughness sheen, animated breathing
  edge; bit-exact when off.
- **Lights slice:** `set_light_halo()` (distance-visible nav-light sprites,
  depth-tested occlusion), stall-free depth-tap visibility queries,
  `enable_spot_exponent()` for flood lamps.

## 2026-07-23

- **The GLSL-120 dual path is deleted** — all 16 shader sources are native
  GLSL 330; compat contexts are diagnostic-only. Phases R1 (unified
  renderer, color contract) and R2 (directional sun + shadows) closed with
  sign-off.
- **sRGB input linearization** approved and wired (A/B verified).
- **Baked explosion effects:** `spawn_effect()` — premultiplied flipbook
  quads, analytically unlit, one-shot self-reaping; alpha-aware
  `gen_flipbook.py`.

## 2026-07-21

- **Terrain height-aware blending** (`height_blend=`) — softmax reweight by
  packed height; provably a no-op on flat palettes. `hex_offset=` world-
  anchors hex-tiling across chunk borders.
- **Cutout alpha for binary transparency** (`TransparencyAttrib M_binary`)
  including instanced foliage; fixes core-profile content rendering opaque.
- **Morph crowds:** zero-copy morph bakes (1.17 s → 0.08 s per face); clones
  share delta textures but wear their own faces.

## 2026-07-20

- **Hex-tiling for terrain** (`hex_tiling=`) — 3-tap stochastic tiling kills
  texture repetition without `textureGrad`; per-layer rotation, contrast
  control.
- **Light-budget policy:** priority-sorted overflow with the sun pinned
  (floods can no longer evict sun shadows), `set_light_budget()` per-root
  nearest-N warden.
- **GPU morph targets:** `set_gpu_morphs()` — morphs and hardware skinning
  finally coexist; 52 addressable targets, runs on stock Panda3D 1.10 too.
- Environment controls: `set_env_scale/intensity/rotation`.

## 2026-07-19

- **Terrain lane:** guaranteed-format data textures, splat-driven 4-layer
  texture arrays with macro variation and normal mapping, GPU instancing
  over InstancedNode with instanced shadows.
- **Ships lane:** rigid-clip extraction from glTF (doors/ramps/gear —
  channels the loader silently drops), powered display screens
  (`set_screen`, flipbooks, UV scroll), `set_blink()` nav-light circuits.
- **glTF MASK fix:** `apply_alpha_masks()` — alpha-tested content renders
  correctly on core profiles (upstream renders it opaque).
- **Offscreen GL fixes (C++):** every offscreen frame had raised
  GL_INVALID_OPERATION since an inherited upstream regression — fixed;
  `test_gl_clean` now enforces zero GL errors permanently.
- **R6 surgery, window 4:** mobile-target machinery removed (−8.1k lines).
  First-person viewmodel camera API.

## 2026-07-18

- **R5 complete — the look of the game, in one day-per-slice increments:**
  aerial haze, hemisphere/SH ambient, shadow texel snap; specular-preserving
  glass; double-sided lighting; per-node ambient scale; specular IBL with a
  real BRDF LUT and correctly prefiltered GGX ladder
  (`tools/gen_env_prefilter.py`); local point/spot lights; Blender-authored
  lights; **orbital atmospheric scattering** (limb/halo/terminator from
  space, matched to an independent integrator to ≤0.003); SSAO; lens
  flare/dirt; per-node atmosphere/environment binding; skinning bone-budget
  knob. Worked skybox example + shipped sample.

## 2026-07-17

- **Final upstream catch-up merge** (Panda3D master, C++17 migration) —
  built, validated, and the door closed: Pax3D is sovereign from here.
- **R6 surgery, windows 2+3:** DirectX 9 excised (−16.7k lines); dead
  platform display backends excised — GLES/GLES2/EGL/WebGL/Android/
  iPhone/macOS (−18.5k lines). One graphics reality: OpenGL core.
- **Double-precision build** (`STDFLOAT_DOUBLE`) compiles clean and
  round-trips exactly at Neptune-scale offsets.
- **Bloom root cause found and fixed:** 8-bit intermediate FBOs were
  quantizing the blur chain (looked exactly like bad filtering — it wasn't).
  Float fbprops now gated. Opt-in logarithmic depth landed.
- Language canon ratified: prototype in Python/GLSL, promote to C++ on
  profile evidence only.

## 2026-07-16

- **The verification harness (`tools/paxtest/`) is born** — offscreen render
  jobs with analytic checks, run identically against Pax3D and stock
  Panda3D. Its first act: disproving both founding myths. There was no
  DirectionalLight engine bug and no double-gamma bug — the 2025-era
  evidence was mesh winding, NaN tangents, and non-linearized inputs.
  **Measure first, then build** became the project's law.

## 2026-02-26

- **Forked from panda3d/panda3d** at 1.11.0-dev to fix "the DirectionalLight
  problem" and add HDR rendering for the Pax Abyssi space simulation. (The
  March 2026 rendering effort was later reverted wholesale — it built on an
  unverified pipeline. The July reboot above started with the harness
  instead. The lesson is the changelog's oldest entry on purpose.)
