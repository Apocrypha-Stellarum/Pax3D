# Handover — Session F (2026-07-17): Build Windows 1–3, machine migration

**State: engine base transformed and fully validated.** If you read one
thing first, read `../PAX3D_MASTER_PLAN.md` (v3) — this handover covers
what changed today and what to do next.

## What happened (all of it gated, all of it committed)

| Commit | What |
|---|---|
| `8c15a5fa87` (prior) | Window-1 prep from the A computer |
| `d29183ce42` | **Window 2:** DX9 excised — dxgsg9/, pandadx9/, winDetectDx9, displaySearchParameters, all refs. −16,691 lines |
| `3912762dd9` | **Window 3:** GLES/GLES2/EGL/WebGL/Android/iPhone/macOS display backends + DX9 flag machinery excised. −18,546 lines. **`--no-dx9` and `--directx-sdk` no longer parse** |
| `237e8e4ec5` | Doc-modernization inherited from the A computer, committed here |
| (this session) | Docs refreshed post-surgery + this handover + feedback response 2 |

- **Window 1 (catch-up merge) is SIGNED OFF.** Float wheel + doubles wheel
  built; paxtest both engines × both baselines 48/48 identical; testbed,
  sfb2 boot, openworld selftest all green. Severed-upstream policy is now
  fully in force, permanently.
- **Doubles spike verified** — see game repo
  `documents/handover_doubles_spike.md` Results: precision perfect at
  Neptune offsets; stock simplepbr crashes on doubles (keep the wheel in
  `pax3d-double-env`, NEVER in launcher envs). Open: perf A/B, user flight.
- **Live engine = Window-3 wheel** in `C:\python\pax3d-env`
  (`wheels_window3\`). Rollbacks: `wheels_window2\`, `wheels_window1\float\`,
  pre-merge `wheels_float\`.

## The machine (this is the primary dev machine now)

20 cores, VS **Build Tools** 2026 → builds need `--msvc-version=14.5` +
`$env:VCINSTALLDIR` (BUILDING_PAX3D.md pitfall 0). ~8-minute builds: the
build-window cost objection is dead. Canonical game at `C:\python\sfb2`
(master backup on the T7: `D:\python\sfb2`; engine backup `D:\python\pax3d`).
`pax3d-env` carries the full game dep stack (pandas/scipy/trimesh/pygame/
PyQt6…), version-matched to the old machine.

## Incident report (read before trusting any field report)

The first Window-1 build failed because ~35 files in the engine repo had
been silently overwritten with **stale Session-D-era content** before the
machine transfer (full forensics: `../SESSION_LOG.md` Session F). Fixed by
`git restore`. Consequence: the openworld dev's evening "P0 — lit shadows
vanish" was **measured against that contaminated engine** — the same probe
on a clean engine shows correct shadow darkening (0.800→0.086), and the
user confirms shadows look good in-game. Established fact #11. Habit:
`git -C C:\python\pax3d status` before ANY engine debugging session.

## Next session — priorities in order

1. **paxtest hardening** (openworld asks — cheap, do first):
   - Promote `gltf_caster_ground_lum` from `[info]` to a real assertion.
   - New lit-shadow test: glTF-material geometry as BOTH caster and
     receiver (their two-command A/B showed flat-color scenes can't catch
     this class). This also guards the contamination failure mode.
2. **The REAL openworld P1 — hardware skinning vs Rigify rigs**
   (`../../PAX3D_FEEDBACK.md`, "NEW P1"): 94-joint skins with control
   bones + animated non-uniform scale on DEF-spine bones → concertina
   necks on the GPU path; CPU path renders perfectly; 64-joint DEF-only
   pack fine on both. Plan: (a) paxtest repro (asset:
   `openworld/3D assets/Casual Characters 2/f_1.glb`), (b) per-node
   hardware-skinning opt-out API — cheap interim, global CPU is 112→8 fps
   for them, (c) root-cause the GPU palette's composition of animated
   scale. Python/GLSL first per the Language Canon.
3. **Game-side adoption queue** (master plan §4.2 — needs the user):
   parity eyeball, shadows-in-the-pilot-seat (set `shadow_bias_world`
   first!), bloom retune, sRGB linearization experiment.
4. Smaller: runtime fog toggle (R5-adjacent, cheap); the two sfb2 bugs
   (cp1252 `→` print crash — smoke with `PYTHONUTF8=1` meanwhile; mixed-
   slash music path).

## Strategy reminder (user-stated 2026-07-17)

**Space scenes are the first priority, always.** Planetary/character
scenes (openworld's domain) are supported and welcome, but engine
optimisations for them must not detract from the space experience —
planetary features land opt-in with zero cost when disabled (the pattern
every Session E API already follows). Clustered lights / CSM remain
post-R5 planetary-track items on that basis.
