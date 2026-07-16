# Handover — Session D part 2: Flags Flipped, R4.0/R4.1 Done, R4.2 Teed Up

**Date:** 2026-07-17 (same-day continuation of Session D — see
`handover_session_d_bloom_fix.md` for the bloom fix + shadow extent work)
**Repo state:** pax3d `e16a24e1ae`, sfb2 `c3f25a3` committed.
**In-flight (not mine, do not clobber):** uncommitted shadow debug modes
10/11 in `pax3d_render/shaders/pax_pbr.frag` (another session's working
tree); the FTL warp distortion pass landed at `3f1c9c90f9` with its own
paxtest (`ftl_blur`, green); the game repo has an active nested-space /
FTL dev — coordinate before touching arena/coordinate systems.
**Read first:** `../PAX3D_MASTER_PLAN.md` (Session D log + R4 section),
`../PAX3D_RENDER_ARCHITECTURE.md` §9 (R4.1 landed / R4.2 contract).

---

## What this session delivered

1. **Game flags FLIPPED (user-ordered):** `use_pax3d_render: true`,
   `sun_light_mode: "directional"`, `enable_shadows: true` in sfb2
   settings.json (runtime-rewritten file; keys survive the game's
   rewrite). Game smoke-boots clean on pax3d_render — zero shader
   errors, planet scene loads, clean exit. `bloom` stays false pending
   retune. **Visual parity/shadow eyeball by the user still pending** —
   with the flag on, the paxtest `pax_pbr` column routes to pax3d_render
   (that's why bloom/pax_pbr now passes).
2. **R4.0 — scale defects mechanized** (`test_scale.py`, runs under
   'none' + pax3d_render): Z-fighting at 2500 IEU under the game frustum
   (0.1/5000: ~1.9 IEU depth resolution), and off-origin float32
   precision loss (0.24% pixels @1.2e6, 22% @1.2e7). Baseline rows FAIL
   BY DESIGN until R4 completes.
3. **R4.1 — logarithmic depth LANDED, opt-in** (`enable_log_depth` /
   `set_enable_log_depth()`): fragment-level
   `gl_FragDepth = log2(1+w)/log2(1+far)` in the PBR shader; coefficient
   tracks the camera lens far EVERY frame (caller owns the lens — widen
   to 0.1/1e9 when enabling). Acceptance row
   `scale/pax3d_render @logdepth` is GREEN: 1 IEU separation at 2500 IEU
   orders correctly at every step of a 6-step sub-resolution sweep,
   GLSL 120+330, stock + Pax3D engines. Ortho SHADOW pass deliberately
   stays linear (log-of-w is wrong for w≡1). Testbed: `--log-depth`,
   Z hotkey, HUD line; planet approach renders clean through the wide
   frustum.
4. **R4.2 groundwork + decision:** camera-relative rendering is the
   chosen path; the doubles engine build is SHELVED for CPU cost (user
   decision — revisit at the next break; the game repo's
   `handover_doubles_spike.md` preserves the full procedure). The
   implementation trap is machine-proven (`trap_parent_cancel_quantizes`
   INFO line): parent-at-minus-anchor does NOT cancel sim-scale
   coordinates stored in node transforms — they quantize first (8.5%
   pixel displacement for a ship 1.5 IEU from anchor at 1.2e7).

## Test-design lessons encoded this session (respect them in new tests)

- **Z-fight probes must SWEEP** a full depth-quantization cell: a single
  frame can tie-break uniformly in the correct surface's favor and mimic
  a working depth buffer (observed flake before the sweep landed).
- **Float32 precision loss needs a ROTATED camera** to manifest —
  axis-aligned rigs cancel exactly and hide the defect.
- Route defect rigs through the pipeline's real scene shader (the zfight
  cards use PBR materials under pipelines), or you test the wrong path.

## How to verify current state

```bash
C:/Python313/python.exe C:/python/pax3d/tools/paxtest/run.py
# Expect: all pax3d_render rows PASS incl. scale @logdepth and ftl_blur;
# scale/none + scale/pax3d_render (default) FAIL = documented R4 baseline;
# legacy pax3d_simplepbr bloom/rebuild FAIL by design; rebuild/pax_pbr
# FAIL by design (old attach pattern).
cd C:/python/sfb2 && python test3d_pax.py --pax3d --log-depth --focus planet --selftest
```

## Next session: R4.2 — camera-relative rendering (game-side)

The pipeline needs NOTHING new — it is already rebase-safe
(camera_world_position, log-depth coef, shadow-extent center are all
per-frame; the sun is direction-only). The work is the game's
positioning layer:

1. **Read the other dev's domain docs first:**
   `sfb2/documents/.../NESTED_SPACE_ARCHITECTURE.md` (Quick Reference
   table: arena state, display-scale ownership, camera/DR layering
   contract). Deep-space mode ALREADY locks the ship at origin — R4.2
   generalizes that pattern rather than inventing a parallel one.
   **Coordinate with that dev** — same files, active work.
2. **The contract (machine-proven):** every node position handed to
   Panda = `sim_pos - anchor` computed in PYTHON DOUBLES; the anchor
   follows the player/camera (rebase when |camera-anchor| exceeds a few
   thousand IEU, between frames). Never put sim-scale numbers in node
   transforms — see the trap INFO line in test_scale.
3. **Audit who writes large world coordinates today:** the known writers
   are `sun_position_manager.py` (sun visual at ~3700 IEU — fine),
   planet placement (~2600 IEU — fine), and the system/multi-star scale
   paths (1e5+ — the actual problem regime, currently fenced off by
   deep-space mode). `calculate_planets_and_sun_from_player: true` in
   settings means the game is already largely player-centric.
4. **Acceptance:** engine-side, `precision_off_origin` stays red (it
   measures the raw engine, by design). Game-side: an orbit + fly-out at
   system-scale offsets with zero jitter — consider a testbed/selftest
   variant that places the whole scene at 1.2e7 sim coords through the
   anchor layer and diffs against the origin render (the pattern gives
   bit-identical output when done right).
5. **After R4.2:** game flips the wide frustum + `enable_log_depth`
   (fly-out test), sky-object shaders adopt the log-depth formula, and
   ONLY THEN retire the sky camera (the plan's standing warning: never
   remove the workaround before its replacement is proven).

## Also queued (unchanged)

- User eyeball: parity + shadows in the pilot seat; bloom-on retune
  decision (strength/intensity/tints — tint list indexing reads inverted
  vs its comment labels).
- R1 leftovers: sRGB linearization experiment (testbed G key); GLSL-120
  path removal once the game runs `gl-version 3 2`.
- ~~R6: upstream merge — `git fetch upstream && git merge upstream/master`
  (93 commits pending, remote now configured); rebuild + full paxtest
  after.~~ **CANCELLED 2026-07-17: upstream severed by user decision —
  Pax3D is sovereign, no sync ever; upstream is a read-only reference
  for hand cherry-picks (see CLAUDE.md "Upstream Relationship —
  SEVERED").** *Same-day revision: user ratified ONE final catch-up
  merge (Route A) before closing the door — performed as `eb685fd003`,
  awaiting its build window (`BUILD_WINDOW_1_CATCHUP.md`). Still no
  syncs after.* Doubles-build spike: resume when CPU allows — now
  bundled into that same window as optional Build 2.
