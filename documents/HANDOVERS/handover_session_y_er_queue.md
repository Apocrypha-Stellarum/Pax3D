# Handover: Session Y — the game-request queue cleared (2026-07-20)

**State: every outstanding game→engine ask is CLOSED engine-side.**
ER-007 (hex-tiling, HIGH), ER-008 (light selection policy, MED), and
the three carried-over Round-5 env asks all landed this session —
Python/GLSL only, no build window, everything opt-in with exact no-op
defaults, all gated. The engine desk is EMPTY: nothing is owed to any
lane until new field reports arrive.

## What landed (all in this session's two commits)

| Item | Delivery |
|---|---|
| ER-007 hex-tiling | `set_terrain_splat(..., hex_tiling=True, hex_cell_size=4.0, hex_rotation=1.0, hex_contrast=6.0)` — TERRAIN_HEX_TILING define at the ratified v2 seam. 3-tap Mikkelsen stochastic tiling; per-cell constant transforms ⇒ no textureGrad needed ⇒ works on BOTH GLSL baselines (the design fact that made this a same-day landing). Per-layer rotation control (anisotropic sets). +12 test_terrain_splat checks |
| ER-008 answer | Overflow policy pinned from the C++ then gated: priority-sorted head uploaded (`Light.set_priority`, fully dynamic), ties by class rank spot > directional > point, equal ties ARBITRARY (measured varying run-to-run), excess silently dropped. Same on stock 1.10 — upstream behavior |
| ER-008 sun guard | **Default-on behavior change (deliberate):** `_create_sun_light` pins the pipeline sun at priority 1<<20 — without it, flood SPOTLIGHTS on an overflowing hull evict the directional sun AND ITS SHADOWS (class rank). Gated: sun survives 2 floods on a 2-slot array |
| ER-008 warden | `set_light_budget(root, lights, budget=None, anchor=None, radius=0.0, hysteresis=1.25)` / `clear_light_budget` — per-root nearest-N binding; scores luma/(kc+kl·d+kq·d²) via each light's own attenuation; blink-steady scoring; rebinds only on membership change. Budgets are now LOCAL per hull |
| Env asks (Round 5 §3) | `set_env_scale(np, s)`/`clear_env_scale` (per-node, ibl_spec ONLY), `set_env_intensity(s)` (global, multiplies with node scale), `set_env_map_rotation(deg)` (specular yaw about +Z, skybox set_h sense — shader samples Rz(−θ)·r). +5 test_env_map checks, all max-err 0.000 |

## Gate (Session Y canonical)

**@game 71/6/106 Pax3D · 69/6/108 stock; @modern 70/7/106 · 68/7/108**
(183 jobs; +test_light_priority incl. @directional variant = +2 PASS
/ +4 SKIP per config vs Session X; FAIL sets UNCHANGED — the six
documented rows + lighting/none @modern). Logs: `gate_y_*.log`
(UTF-16, PowerShell redirect).

## Facts worth carrying (new this session)

1. **Zero-light draws are not black.** With no active lights, the GSG
   fills empty `p3d_LightSource` slots with defaults and slot 0's
   default is WHITE (degenerate params → uniform gray ghost-lighting).
   Never visible in practice (something always binds sun/ambient), but
   it IS the no-light ground truth — test_light_priority's opt-out
   check compares against it, not against black.
2. **Light tie-order is genuinely nondeterministic** — the bound pair
   differed between two identical runs. Reported as INFO in-gate,
   deliberately not gated. Anyone triaging "my lamp works sometimes"
   now has the mechanism on paper.
3. **Hex-tiling needs no textureGrad** — per-cell transforms are
   constant, so each tap's UV is continuous wherever its weight > 0
   (the discontinuous tap always has weight ~0 at the boundary). This
   is why the legacy GLSL-120 path (no array-grad sampling) could ship
   the full feature.

## Adoption state / what the lanes owe (we watch, not drive)

- **ER-007**: terrain lane passes the kwargs from
  `materials.splat_dress_fns`, A/B screenshots, retunes the ±24% macro
  swing DOWN. Height-blend rider: question posed in the ER — can they
  author height into the albedo array's ALPHA at intake? If yes it
  lands as the next define at the same seam.
- **ER-008**: ship lane can replace/shrink `SpaceTraffic._light_warden`
  with `set_light_budget` per hull + coarse `set_priority` ranks on
  colony lights. Their `max_lights=16` stops being a global
  correctness ceiling.
- **Env asks**: planetside drives `set_env_intensity` from the sky
  segment ramps, `set_env_scale(terrain, ~0.15)`, yaw from the same
  value as their SH yaw. Response appended to
  `openworld/PAX3D_FEEDBACK_3.md` (engine response section, 2026-07-20).
- Older queue unchanged: ER-005 adoption + Minerva conversion
  (ship lane), terrain ER-001/002/003 adoption, R1 sRGB flip, R2
  directional flip, R3 retune (game side).

## Repo state

- Engine repo: 2 commits this session (code, docs). sfb2:
  ENGINE_REQUESTS ER-007/ER-008/README updated in place (committed
  separately, only those files — game-lane churn left untouched).
  openworld PAX3D_FEEDBACK_3.md: response appended (repo frozen-ish —
  check whether the game dev wants it committed there).
- No wheel change: this session is pure Python/GLSL; the Session-X
  wheel remains current in pax3d-env and system Python.
- Machine topology unchanged (Session X watch item 1): system Python =
  FORK; stock ONLY via `C:\python\stock-panda-env`.

## Open engine queue (unchanged priorities)

- **GPU morph prototype** — still the top idle-capacity item
  (Python/GLSL per canon; queued behind the character dev's re-export
  A/B).
- Texture-palette skinning (deprioritized), R2.3 conveniences,
  InstanceList bulk fill (profile-gated), Vulkan watch,
  depth-pass cutout shadows @modern (field-evidence-gated).
- Height-blend sharpening (NEW, small): unblocks the moment the
  terrain dev answers the albedo-alpha question in ER-007.

## First moves next session

1. `git status` both repos (fact #11) + confirm machine topology.
2. Sweep `ENGINE_REQUESTS/`, `PAX3D_FEEDBACK*.md`, newest sfb2
   handovers for adoption reports on this session's three deliveries —
   field feedback on hex contrast/cell defaults is the most likely
   early arrival.
3. If quiet: the GPU morph GLSL prototype.
