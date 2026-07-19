# Handover — Session V (2026-07-19): the walkable-ship engine surface is COMPLETE

**From Session V** (one session, three waves: ER-004 rigid clips +
ER-005 powered displays off the ship dev's Minerva census; the
same-day question resolutions; then ship exterior/status lights off
the user's gold-standard screencaps). Read `SESSION_LOG.md` (Session V
entries, three parts) for the narrative.

**State of the world:** engine commits `18d4228aea` (ER-004+ER-005
code + gates), `cafa3bfe33` (docs true-up), `faee71ffb6` (ship-lane
634 resolutions — ffmpeg question CLOSED), `0b3e0483ed` (blinker +
light-budget measurement). None pushed. **No C++, no build — the
Window-4 wheel stays current.** sfb2 ER-004/ER-005 files carry the
engine responses/resolutions/lights-addendum but are **deliberately
NOT committed** (the ship dev's active lane — verify they survived
before relying on them; fact #11 discipline).

**Gate totals (new canonical):** @game **64 PASS / 6 FAIL / 91 SKIP**
Pax3D · 62/6/93 stock; @modern 63/7/91 · 61/7/93. FAIL sets are the
documented pre-existing six (+lighting/none @modern); the stock delta
is the known instancing SKIP pair. test_rigid_clips (10 checks) and
test_screen (19 checks) are the two new rows, green on both engines ×
both baselines including the routed `graphics.pax_pbr` path.

---

## What landed (all opt-in, byte-identical off, gated)

1. **ER-004 — rigid clips** (`pax3d_render/rigid_clips.py` +
   `pipeline.get_model_clips(np)`): parses the plain-node TRS channels
   panda3d-gltf silently drops (every Unity door/ramp/gear/drawer
   clip). Nodes stay PandaNodes; skin/morph channels skipped
   (complementary to Actor). Axis contract = the loader's own csxform
   conjugation, pinned in-gate at 0.0 err vs the loader's rest pose.
   `RigidClipPlayer` (stateless seek(u)/apply(t)/reset; game owns
   easing/sounds/gating). `RigidClip.from_delta()`/`add_delta()` for
   the ~40 Minerva prefab script-lerps — compose convention VALIDATED
   against `VattalusInteractable.cs` source (line 248; no change).
2. **ER-005 — powered displays**: `set_screen()` (albedo+emission
   bind at override 1, node texture state cleared first — set_texture
   MERGES stages; byte-identical restore), `set_emission_scale/_color`
   (`u_emission_factor` uniform; 0.0 = VA_ScreenOff with albedo lit),
   `set_uv_transform`/`set_uv_scroll`/`play_flipbook`
   (`u_uv_transform` uniform; pipeline-task-driven, O(active)/frame),
   `tools/gen_flipbook.py` (video/frames → atlas; works with this
   machine's 2013-era ffmpeg CLI — no `-hide_banner`).
3. **THE video fact + decision:** the Pax3D wheel builds `--no-ffmpeg`
   — MP4 decode does not exist engine-side. **DECISION CLOSED (634 +
   user sign-off): trimmed flipbooks** (long loops cut to 10–20 s at
   intake; 3 of 6 Minerva loops run 1–2.8 min but are ambient FUI
   dressing). If long-form video ever becomes content: game-side
   `set_ram_image` decoder FIRST; ffmpeg-in-the-build only after,
   with evidence.
4. **Ship lights (part 3)**: `set_blink(np, period, pulses, phase,
   lights=)` / `clear_blink()` — pulse-train envelope on the emission
   factor (composes with the emission registry, no one-frame pop),
   optional real light nodes gated by the SAME envelope,
   edge-triggered pushes, per-ship phase de-syncs fleets. Airliner
   recipe in the docstring; 737NG circuits model documented (named
   subtrees `lights_position/beacon/strobe/floods`; each switch =
   2–3 byte-identical-opt-out calls).
5. **Light budget MEASURED** (probe, both baselines): with shadows,
   `max_lights` 16/20/22 link + light correctly, **24 FAILS to link**
   (`v_shadow_pos[MAX_LIGHTS]` varying array vs the ~128-component
   budget). Recommend 16 for walkable-ship scenes; ceiling 22. NPC
   ships: emissive markers + bloom, NO real lights (the packs' own
   convention).
6. **Loader mechanisms recorded** — `ENGINE_INTERNALS.md` §5
   (animations only via build_character; per-node csxform conjugation;
   naming; ModelRoot fullpath) + §2 TextureAttrib stage-merge/override
   entry. Census corrections recorded: 49 screens / 6 shared
   materials; pack easing is SMOOTHSTEP not linear.

## Phase 0 — Orient

Standard: `git log --oneline -10`, `git status` (fact #11 — verify the
tree AND the sfb2 ER files' uncommitted edits survived), field sweep
(sfb2 handovers + `git -C C:\python\sfb2 log --oneline` since
2026-07-19, planetside lane).

## Phase 1 — Field triage (FIRST, always)

The whole lane is now game-side adoption; expected report classes:

1. **Phobos console clip flow** (their stated handover task 1): the
   converter re-exports with `export_animations=True` + named takes,
   then `get_model_clips` → `RigidClipPlayer`. Traps they were told
   about: BamCache OFF when measuring loader behavior; clip/target
   names follow panda3d-gltf conventions (`name` else `node%d`);
   `player.missing`/`.duplicates` are the rigging diagnostics. The
   exported GLB renders byte-identically before the ClipPlayer
   migration — safe to re-export early.
2. **Prefab delta batch-convert**: their in-scene validators are the
   Bathroom sliding door (pure translation) + one cupboard (pure
   rotation). If a delta rotates the wrong way, suspect THEIR
   Unity→Panda axis conversion of the delta VALUES (the compose
   convention itself is source-validated) — multi-axis eulers must be
   built with Unity's ZXY order and passed as `quat_delta`.
3. **Screens**: converter splits per-screen nodes (their plan is
   sound); atlas intake of the 6 loops via `gen_flipbook.py`. If a
   screen renders black under `use_emission_maps=False` configs, the
   set_screen warning names it. Emission scale ≈1.72 matches the
   packs' HDR level.
4. **Lights**: circuit wiring per the ER-005 addendum table. If a
   ship scene silently loses lights, check `max_lights` first — 24+
   with shadows is a LINK FAILURE (measured); recommend 16, ceiling
   22. Blink phase: give each ship a distinct phase.

## Phase 2 — Engine-side follow-ups (queued, none urgent)

- **Testbed keys for the Session-V features** (game repo,
  `test3d_pax.py`): a screen quad with flipbook playback, a blink
  strobe/beacon pair, a clip-driven door on a hotkey. Harness-proven
  but no eyeball rig yet — do this before content tuning starts (the
  Session-S precedent).
- **Material channels in RigidClip** ("one runtime, two channel
  kinds") — the channel `path` field is the open seam; land only when
  the game asks for synchronized motion+material sequences.
- **Hologram treatment** (ER-005 #4, deferred): a per-node shader
  variant (set_glass mechanism — additive scanline + glitch). Needs
  their look targets first.
- **Blink easing/soft-rise** (beacon glow ramps): only if the binary
  envelope reads harsh in the field; trivial to add to
  `_blink_envelope`.
- **Flipbook cross-fade / non-uniform fps**: only on field evidence.

## Phase 3 — Standing watches (unchanged)

R4.2 ship-as-anchor (walkable-in-flight makes it nearer), GLSL-120
removal (game flips gl-version 3 2), texture-palette skinning + GPU
morph path (build-window queue, evidence-gated), InstanceList bulk
fill (profile evidence only), Vulkan (watch only).

## Operational notes

- Gates: 4 combos SEQUENTIALLY, detached (`Start-Process` — inline
  background tasks die at ~10 min). This session's runner script:
  scratchpad `run_gates.ps1` pattern; logs `gate_v_*.log` (+ `.json`
  copies of last_run.json per combo) in the repo root, untracked.
- Expected totals: see header. `screen/pax_pbr` PASSES — the game's
  routed path picks up new pipeline APIs automatically.
- `tools/gen_flipbook.py` needs the ffmpeg CLI only for video input
  (frame dirs work without); the machine's ffmpeg is a 2013 build —
  don't add modern flags.
- test_screen's blink checks force envelope state via `phase` against
  the global clock (period 1000 s) — deterministic; don't "fix" them
  to real-time patterns.
- The Minerva gold-standard screencaps live at
  `C:\python\sfb2\screencaps\minerva\` (look targets for lights /
  interior / screens).
