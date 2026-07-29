# Handover — Session R (2026-07-18): R5 engine-complete; next, adoption support + lens polish

**From Session R** (one session, executed the full Session Q handover:
field triage -> R5.5 orbital scattering -> worked skybox example -> sRGB
experiment -> C++ mini-window). Read `SESSION_LOG.md` (Session R entries)
for what happened; `OPENWORLD_FEEDBACK_RESPONSE_5.md` for the last field
exchange.

**State of the world:** engine commits `05cde87ba5` (R5.5 core),
`bb6cfd01fe` (R5.5 docs), `6439779a86` (equirect tool), `cdc55d1a68`
(skybox sample + look guide), `eaebcd7ef0` (sRGB experiment),
`e21bfc6ea7` (C++ combine warning). sfb2 commits `2dff312`, `907c501`,
`b442c96` (testbed + docs). None pushed. **The installed engine is now
the Session-R wheel** (Window-3 + combine warning; archived
`wheels_session_r\`). Full 21-test matrix green on both engines after
every commit: **48 PASS / 6 documented FAILs / 63 SKIP, identical stock
vs Pax3D** — a seventh FAIL is real; the six are still bloom x2 /
rebuild x2 / scale x2.

**R5 is engine-complete except lens polish.** Everything in the
signature look now exists, harness-proven, opt-in: planetside haze,
SH/hemisphere ambient, specular IBL + GGX prefilter + equirect front
end, orbital scattering, texel snap. What remains everywhere is
ADOPTION (game-side tuning + sign-offs), then lens flare/dirt.

---

## Phase 0 — Orient (15 minutes, do not skip)

1. `git -C C:\python\pax3d log --oneline -8`, `git status` — clean tree,
   commits above (fact #11).
2. Field sweep, newest first: `C:\python\openworld\PAX3D_FEEDBACK_2.md`
   (a `_3` may start), `C:\python\sfb2\documents\HANDOVERS\
   handover_planetside_unification.md`, `documents/PLANETSIDE/`,
   `git -C C:\python\sfb2 log --oneline --since="2026-07-18T13:00"`.
3. **Session 617 landed "Phobos walkable" mid-Session-R** (ground apron,
   ramp, interior floors/lights) — the walkable-ship adoption wave is
   LIVE. Expect the Stream-A report classes from the Session Q handover
   (glass/ambient-scale/collision/authored-lights traps — that
   handover's Phase 1 list still applies verbatim).

## Phase 1 — Field triage (FIRST, always)

Same standing rule: triage against measured records, reproduce on a
clean checkout + the Session-R wheel, paxtest anything that matters.

New Session-R-specific report classes on top of the Session Q list:

1. **The combine-mode warning fires in sfb2's own boot** (found during
   the Session R smoke): some game state has a combine/scale/multi-stage
   TextureAttrib silently flattened under core profile. If the game team
   asks: the warning is the diagnosis (once per TextureAttrib); the fix
   is an explicit GLSL shader on that geometry (same as the openworld
   dome — their worked fix is in PAX3D_FEEDBACK_2.md). Help them locate
   it if asked (the warning prints at first render of the state; a
   binary-search hide() session finds the node fast).
2. **Orbital scattering adoption** (sfb2 planets/planetside space
   views): recipes in USING_PAX3D_RENDER 8 + look guide 6. Likely
   traps: node origin not at planet center; node-scale radii (API takes
   WORLD units); expecting the haze handoff to be automatic (it is
   documented-not-solved — R4.2-era); bit-30 caster-mask collision.
3. **Skybox env adoption**: the two-command bake + set_env_map +
   set_ambient_sh(sh_from_cubemap(tex)). Traps: equirect azimuth anchor
   (content rotation, never the face table — look guide 7), baked sun
   azimuth (006_Sunset's sun sits SOUTH), clear-color placeholder
   textures cannot carry sRGB decode (real files can).
4. **sRGB flip request**: the experiment is DONE and the ACES verdict is
   on file (arch doc 8). If the game wants the default flipped: that is
   a CONTENT project (sun/exposure retune) — support with A/B evidence,
   do not flip the default engine-side.

## Phase 2 — Lens polish (R5 finale) IF the field is quiet

The last R5 item: lens flare/dirt on the bloom chain. Shape it like
every R5 feature: opt-in post-pass on the existing bloom buffers
(they are float — fact #3 discipline), analytic paxtest gate (flare
position from sun screen-space projection is analytically checkable),
byte-identical off. Do NOT start it with open field reports.

## Phase 3 — Standing watches (unchanged triggers)

| Watch | Trigger | Prepared state |
|---|---|---|
| **R6 Window 4: mobile-glue deletion** | USER schedules (the Session R user authorization was consumed by the combine-warning mini-window; the themed deletion window deserves its own fresh session) | Queue in CLAUDE.md: android/iphone app glue, makepanda Android machinery, deploy-tool logic, DIRECTCAM. R2.3 conveniences also still queued |
| **R4.2 ship-as-anchor** | Starhopper flies far (Session 617 is building the walkable ship NOW — this trigger is getting closer) | Engine half ready; consult from the decided plan |
| **Clustered lighting** | max_lights pressure in reports | Backlogged |
| **GLSL-120 removal** | Game flips `gl-version 3 2` | Session Q core-profile findings are the checklist; the new combine warning helps the game FIND its FFP stragglers first |
| **Vulkan** | Upstream branch runs paxtest | Watch only |

## Operational notes

- Gate = `run.py` both pythons sequentially; expected totals now
  **48 / 6 / 63** per engine (test_orbital + test_srgb added; both also
  PASS on the pax_pbr shim rows because the game routes to
  pax3d_render).
- test_orbital has a `@logdepth` variant row; test_srgb runs plain.
- `gen_equirect_cubemap.py --selftest` is the converter's own gate
  (8 checks); it needs no simplepbr. The prefilter still needs pip
  simplepbr (dev-time only).
- The testbed grew: O/Shift+O (orbital), M (env cycle), `--orbital`,
  `--env spec|full`, `--tonemap`, `--srgb` — all selftest-composable
  for scripted A/B screenshots.
- sfb2 tree still carries concurrent-session churn (Session 617+) —
  stage ONLY your files, verify each hunk.
- `PYTHONUTF8=1` for redirected game output; paxtest strings stay
  ASCII-safe.
- Two new measured traps for texture work: prepared textures need
  `release_all()` after format changes, and clear-color-only textures
  round-trip sRGB formats undecoded.
