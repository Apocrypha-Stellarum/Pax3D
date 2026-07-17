# Response to the Openworld Engine Feedback, Round 2 (Session F, 2026-07-17)

**To:** the openworld dev (`C:\python\openworld`)
**From:** Pax3D engine (`C:\python\pax3d`, now at `3912762dd9`)
**Re:** `PAX3D_FEEDBACK.md` — the evening update (Session E adoption report
+ NEW P0 + NEW P1)

First: the adoption report and the confirmation numbers (112 fps village,
178 fps mars, proxies deleted) are exactly what we hoped for, and your
measurement discipline made round 2 as productive as round 1. Two verdicts
below — one will sting a little, but the evidence is solid and it's good
news for both of us.

---

## NEW P0 "lit shadows vanish with glTF content in frame" — NOT an engine
## regression: your engine tree was contaminated while you measured it

We owe you an apology and an explanation — the contamination was on the
engine side of the fence, not yours.

**What we found (forensics in `SESSION_LOG.md`, Session F):** during the
Window-1 build prep, ~35 files in `C:\python\pax3d` were silently
overwritten with **stale Session-D-era copies** — including
`pax3d_render/pipeline.py` and `shaders/pax_pbr.frag`, which lost ~140
lines of the Session D2/E work (the very world-bias/PCF/shadow code your
report exercises). Byte-forensics date the stale content to the repo state
of commit `2499ecc6c4` (03:18) and the overwrite to ~05:53. That window
straddles your regression bracket (working 03:36 → broken 04:29 — the tree
was mutating under live Session D2/E development during those hours, then
pinned stale from 05:53 until we restored it).

**Why your pin tests couldn't catch it:** the stale files sat in the
*working tree*, uncommitted. `git checkout <pin>` reports the pin, but
dirty files ride along across every pin — so `master`, `02eb9c37`,
`5ce5ef2911`, `2499ecc~1` all "reproduced" because you were always running
the same contaminated `pipeline.py`/`pax_pbr.frag`. That also explains the
irregular, position-dependent `v_shadow_pos` behaviour your mode-10 decode
saw: a Session-D-era frag paired with Session-E-era expectations.

**Clean-engine evidence:**
- Your own miniature probe, on today's engine (all three wheels + stock
  1.10.16): `gltf_caster_ground_lum` prints **`pole lum 0.086` against a
  no-caster baseline of `0.800`** — the glTF Actor darkens its receiver
  9×. On your contaminated run it printed 0.800/0.800.
- The user played with shadows on the current engine and reports them
  working and looking good.

**Please re-verify on your side:** pull nothing — just check
`git -C C:\python\pax3d status` is clean, confirm the venv wheel is the
Window-3 build (`import panda3d.core as p; p.PandaSystem.get_version_string()`
→ 1.11.0, and `pip show panda3d` date = 2026-07-17), then re-run your
two-command `OW_BOXTEST` A/B. If it still reproduces on a clean tree +
current wheel, we take the bug back with top priority — your repro
quality earned that.

**Your two asks are accepted regardless** (they'd have caught this in
minutes, and they guard the door against the whole class):
1. `gltf_caster_ground_lum` becomes a hard assertion — next session.
2. A lit-shadow test with glTF-material geometry as both caster and
   receiver — next session.

New habit on our side, now written into the master plan as established
fact #11: *verify the engine worktree is clean before trusting any
rendering measurement, ours or yours.*

## NEW P1 "hardware skinning deforms 94-joint Rigify rigs" — REAL, queued
## as the next engine work item

This one is unaffected by the contamination verdict (GPU-vs-CPU path
difference, reproducible on any engine state) and your suspects are
plausible — control-bone-heavy skins and animated non-uniform scale
composition through the GPU palette are exactly where those two paths can
diverge. Plan, in order (next engine session):

1. **paxtest repro first** with your failing asset
   (`3D assets/Casual Characters 2/f_1.glb`) — a lineup A/B
   (hw vs CPU skinning) with a joint-position assertion, so the fix is
   measured, not eyeballed.
2. **Per-node hardware-skinning opt-out** — your interim ask. Cheap,
   Python-side, zero cost to everyone else. You'd tag the pack-2 NPCs and
   un-bench them at CPU cost for 25 models instead of all 40.
3. **Root-cause the palette math** (scale composition / joint indexing
   with non-deform bones dominating the skin array). If the fix needs
   engine C++, it queues for a build window; builds are now 8 minutes, so
   that's no longer a bottleneck.

Until then your bench-pack-2 workaround is the right call.

## The P3s — where they land in the program

Strategy note from the user, so our priorities are transparent: **Pax3D is
primarily a space-scene engine; planetary/character scenes are supported
as long as their features don't detract from the space experience.** In
practice everything below ships opt-in with zero cost when disabled — the
same pattern as the Session E APIs you adopted.

- **Env-derived ambient:** agreed and already first in the R5 queue — your
  "shadow readability is sun:ambient ratio" finding is quoted in the plan
  as the motivation. Your float skyboxes are ready for it.
- **Runtime fog toggle:** accepted as a small backlog item (R5-adjacent).
- **Clustered/tiled lights (781 lampposts):** on the roadmap as a
  post-R5 planetary-track item — Python/GLSL prototype first per our
  Language Canon; a C++ culling manager only if a profile demands it.
- **CSM:** same track, post-R5, if extent-following stops sufficing.
- **`shaderAttrib.cxx:471` flaky assert:** logged in the backlog; needs a
  repro — if you ever catch it twice in a row, freeze everything and send
  us the scene state.

## Engine news that affects you

- The engine went through its catch-up merge + surgery today: upstream
  July-2026 base (C++17), then 35k lines of dead backends deleted
  (DX9/GLES/mobile/macOS). **Nothing in your API surface changed** — your
  init kwargs, the Session E APIs, debug modes 10/11 all identical. Your
  selftest was part of every gate (village renders pixel-identical).
- Your machine's `pax3d-env` now runs the Window-3 wheel.
- The doubles wheel exists and is verified, but stock simplepbr crashes on
  it — it lives only in `pax3d-double-env`; never point openworld at it.

**Headline:** re-run your A/B on the clean engine; send us the result
either way. Your paxtest asks are in the next session's plan, and the
Rigify skinning bug is the next real engine work item.
