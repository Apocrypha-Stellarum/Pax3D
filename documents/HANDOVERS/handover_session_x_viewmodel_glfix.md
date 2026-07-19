# Handover: Session X — viewmodel display region + the offscreen GL window (2026-07-19)

**State: everything this session opened is CLOSED.** Two engine items
were pulled from the field the same afternoon they appeared game-side,
both landed gated, and the C++ half went through a user-authorized
mini build window the same evening. Adoption of the first item is
already confirmed game-side. No open engine asks from any lane.

## What landed (engine repo)

| Commit | What |
|---|---|
| `877d2dc112` | `register_viewmodel_camera`/`unregister_viewmodel_camera` + `test_viewmodel` (15 checks / 17 @directional) — the FPS lane's near-plane answer. Arch doc §6.1 |
| `fd963b6a9a` | Offscreen GL_INVALID_OPERATION root-caused → fact #18; `probe_gl_errors.py`, `test_gl_clean` (defect-asserted), `PATCH_QUEUE_GL_OFFSCREEN.md` |
| `795e87d7f2` | Session X docs: fact #18, arch §6.1, FPS-lane feedback response, gate totals |
| (this session, part 2) | The two fact-#18 C++ one-liners BUILT + LANDED (mini window, 1-min incremental): `get_buffer_mask` single-buffered branch restored, `gl-max-errors -1` honored. `test_gl_clean` flipped to permanent zero-GL-errors form. Wheel live in pax3d-env, archived `wheels_session_x\` |

**Gate (Session X canonical): @game 69/6/102 Pax3D · 67/6/104 stock;
@modern 68/7/102 · 66/7/104.** FAIL sets unchanged (the six documented
rows + lighting/none @modern). Part-2 re-gate on the new wheel:
verify `gate_x_*.log` if you need the receipts.

## Field/adoption state

- **Viewmodel ADOPTED same day** (sfb2 `be4072b`, session 643d; field
  report `openworld/PAX3D_FEEDBACK_3.md` addendum 3): scale fallback
  deleted, scene-switch register/unregister cycling green, pixels
  byte-identical to approved shots. Shipped near 0.02 / far 8.0 /
  fov=None (world copy 80°) / depth_mode 'clear' (no SSAO yet). Their
  M2: sway/recoil on `reg.camera_np` + the 55–65° fov taste test.
  Nothing owed from us.
- **GL workaround retirement announced** (feedback doc, Session X
  part 2 section): FPS dev deletes `gl-max-errors 1000000` from
  `test_weapon_system.py` at their convenience.
- ER-004/005/006 all adopted or filed-as-answered; terrain ER-001/002/003
  still awaiting game-side adoption (unchanged).

## WATCH ITEMS for the next session (read these first)

1. **The engine-pinning sweep RESOLVED (game commit `ee861db`, 643c) —
   new machine topology, learn it before running anything:**
   `C:\Python313` (system python, `py`, double-click) now carries the
   **FORK** — it is no longer the stock reference and never will be
   again. The stock testbed is **`C:\python\stock-panda-env`**
   (1.10.16 + panda3d-gltf 1.3.0 + simplepbr 0.13.1, engine-dev-only;
   verified working, gltf loader files byte-identical to the old
   install). All canonical commands in CLAUDE.md/paxtest README are
   repointed. The mid-sweep gate run that used C:\Python313 as "stock"
   was fork-vs-fork — its logs were overwritten by the corrected
   re-run. One open hatch the terrain dev offered: a pip.ini
   find-links pin so `pip install panda3d` in fresh venvs resolves to
   the local fork wheel — engine lane has no objection (stock-panda-env
   already exists; a deliberate `panda3d==1.10.16` install would still
   work); user decides.
2. **Stale user eyeball feedback.** The user had been launching
   planetside via a command that resolved to system Python = stock
   1.10. Any pre-2026-07-19 visual impressions from those runs were
   measured on the wrong engine. Expect "it looks different now"
   reports when their launcher moves to pax3d-env — those are baseline
   corrections, not regressions. Fact-#11 discipline now extends to
   the INTERPRETER: when triaging a field report, confirm which
   python/wheel produced it before reproducing.
3. **Parallel game-repo sessions are hot** (three lanes committed to
   sfb2 today; session numbers collided twice — game lanes took 643c/
   643d/644). Tree-check before any sfb2 edit.

## Open engine queue (unchanged priorities)

- **GPU morph prototype** — the top strategic candidate when a session
  has idle capacity: Python/GLSL first per canon (no build window
  needed for the prototype), queued behind the character dev's
  re-export A/B; the +2 ms production-head datapoint sharpened it.
- Texture-palette skinning (deprioritized on 0.33 mm evidence; shares
  a vertex shader with GPU morph — one window can land both).
- R2.3 DirectionalLight conveniences (low urgency), InstanceList bulk
  fill (profile-gated), Vulkan watch (no action).
- Depth-pass cutout shadows @modern — waits on field evidence.
- Game-side flips we watch, not drive: R1 sRGB default + GLSL-120 drop,
  R2 directional in-game, R3 retune, terrain ER adoption, doubles A/B.

## Instrument lesson from the window (fact-#12 class)

The GL fix made offscreen frames measurably faster and
`uv_scroll_animates` (test_screen) promptly failed rms 0.00000 under
gate load @modern: the scroll advances by WALL-CLOCK seconds (the
game-facing contract) and 30 fast frames moved the UV sub-pixel.
Fixed by pinning the global clock (`M_non_real_time`, dt=1/30) at
test start — rms now 0.14060, identical on all four engine×baseline
configs. **Any future check that asserts "it moved over N frames"
must pin the clock**; the FPS harness and probe_gl_errors already do.

## First moves next session

1. `git status` both repos (fact #11) + confirm the machine topology
   (watch item 1: system python = fork, stock-panda-env = stock).
2. Sweep `ENGINE_REQUESTS/`, `PAX3D_FEEDBACK.md`,
   `openworld/PAX3D_FEEDBACK_3.md`, and the newest sfb2 handovers for
   overnight addenda.
3. If quiet: start the GPU morph GLSL prototype.
