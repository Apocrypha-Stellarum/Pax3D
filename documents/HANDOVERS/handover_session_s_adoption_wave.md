# Handover — Session S (2026-07-18): R5 COMPLETE; the engine is ahead of its content

**From Session S** (one session, two user directives: "docs first, make
things easy for the four downstream devs" then "proceed on the proposed
queue"). Read `SESSION_LOG.md` (Session S entry) for the narrative.

**State of the world:** engine commits `eaceab7c0c` (doc true-up),
`af86281580` (pusher consult, probe 10/10), `aceed4ac71` (per-node
atmosphere scale), `72c015aa7e` (per-subtree env binding), `c6fee5d1e3`
(first close-out), `6658480d8f` (SSAO), `e074a6d10a` (bone palette +
morph verdict), `11c0ad2cd6` (lens flare — **R5 COMPLETE**). sfb2 doc
commits `b7923b2`, `6563b80`. None pushed. No C++ this session — the
Session-R wheel stays current.

**Gate totals moved twice:** 48/6/63 → (Session S features) →
**54 PASS / 6 documented FAILs / 69 SKIP** per engine, identical stock
vs Pax3D (test_ssao adds 4 PASS+3 SKIP incl. @logdepth + @msaa4 rows;
test_lens_flare adds 2 PASS+3 SKIP). The six FAILs remain the
documented set.

---

## What landed (all opt-in, byte-identical off, gated)

1. **Per-node atmosphere scale** — `set_atmosphere_scale(np, k)`
   (Phobos cabin-wash ask; k=0 ⇒ tau exactly 0).
2. **Per-subtree environment binding** — `set_env_map(tex, node=np)` +
   `set_ambient_sh`/`set_hemisphere_ambient(..., node=np)` (cabin
   reflections/ambient vs sky; node lod override proven).
3. **SSAO first slice** — `enable_ssao`, depth-only obscurance;
   flat-plane byte-identity is the defining gate; **@msaa4 measured:
   the multisampled depth resolve works**. Upgrade path documented
   (indirect-only via scene-pass sampling; the depth foundation also
   serves TAA v2/SSR).
4. **Bone-palette knob** — `max_skinning_bones` (default 100; [200]
   measured inert for small rigs). The 352→81 UE5-Manny cut no longer
   has to merge corrective bones away.
5. **Morph verdict (fact #15)** — hardware skinning SILENTLY DROPS
   egg `<Dxyz>` sliders (upstream behavior, both engines);
   `set_hardware_skinning(np, False)` renders them correctly — the
   working morphs path today. `probe_morph.py` is the record.
6. **Lens flare/dirt** — `enable_lens_flare` (needs bloom), ghosts at
   analytic positions from the bright extract (occlusion implicit),
   `set_flare_strength`, `set_lens_dirt`. **R5 has no remaining
   engine items.**
7. **Wall-pusher consult answered by measurement** (probe_walkmesh
   10/10, collision doc §9): the READBACK CONTRACT (sim_pos =
   walker.get_pos() after traverse — else a held key escapes in ~7
   frames past contact), chunk bounds-culling 6.3–6.7×, converter
   `block_room_*` groups recommended for the Fenris.
8. **Docs trued up both repos** — game-side USING_PAX3D_RENDER §10
   routes each dev (ship interior / weapons / terrain / NPC);
   PAX3D_PITFALLS +6 traps; GRAPHICS_ROADMAP status banner.

## Phase 0 — Orient

Standard: `git log --oneline -10`, `git status` (fact #11), field sweep
(`C:\python\openworld\PAX3D_FEEDBACK_2.md`, sfb2 handovers/planetside,
`git -C C:\python\sfb2 log --oneline` since this morning).

## Phase 1 — Field triage (FIRST, always)

**Already in hand (arrived mid-Session-S close-out —
`PAX3D_FEEDBACK.md` 2026-07-18 character entry, unanswered):** the
character dev measured the pack's bone sets (full 352 / clip-animated
151 / shipped core 81) and asked for a ≥192 table with both shaders
bumped together + identity padding confirmed — **all already satisfied
by the landed `max_skinning_bones` knob** (test_skinning
`bone_palette_200_inert`, both shaders share the define, padding rms
0.0). Their 151-bone `keyed` re-bake A/B is UNBLOCKED — tell them to
run it (`set_max_skinning_bones(200)` or init kwarg). Two new items
from the same entry: (1) they OFFER a real glTF morph test asset
(SK_SFM_Head1, blink/jaw/brow shape keys, skinned + static variants)
— ACCEPT it: probe_morph answered the egg-slider mechanics (fact #15)
but whether panda3d-gltf DELIVERS morph targets at all is unmeasured;
(2) their warning ask is **ALREADY RESOLVED in-session** (user
directive: no artificial caps, maximum UE5/Unity compatibility):
`max_skinning_bones='auto'` sizes the palette to the content, and
`refresh_skinning_budget()` / `audit_skinning_budget()` name any rig
the palette can't hold — measured on a synthetic 120-joint chain
(corrupts at [100] rms 0.1045 vs CPU truth; 'auto' resolves 128,
matches at 0.0000). Tell them: call `refresh_skinning_budget()` after
character loads. The TRUE uncap (full 343-bone rigs verbatim) is the
new **texture-palette skinning** C++ build-queue item (CLAUDE.md).

Expected report classes:

1. **Wall pusher goes in game-side** — the readback contract is the
   trap they were told about (collision doc §9.1); if walls still leak,
   check teleport-class moves and the add_collider target node first.
2. **Interior look adoption** — per-node env binding + atmosphere
   scale + SSAO are all new this session; the §10.1 workflow in
   USING_PAX3D_RENDER is the recipe. SSAO eyeball caveat: this slice
   darkens full radiance — check under harsh sun before shipping on.
3. **Character lane** — the baker may retarget to ~150–200-bone rigs
   (keep correctives); morphing close-up characters must pin to
   `set_hardware_skinning(np, False)`.
4. **Lens flare adoption** — testbed wiring for eyeballing is NOT yet
   done (see Phase 2).

## Phase 2 — Engine-side follow-ups (queued, none urgent)

- **Testbed keys for the Session-S features** (game repo,
  `test3d_pax.py`): SSAO toggle + radius/intensity, lens flare toggle
  + strength, per-node env A/B. The features are harness-proven but
  have no eyeball rig yet — do this before content tuning starts.
- **SSAO quality ladder** (when content asks): depth-aware bilateral
  blur, half-res + upsample, indirect-only application via scene-pass
  AO sampling (the principled variant), GTAO estimator.
- **GPU morph path** (only if content needs many simultaneous
  morphing characters — fact #15 has the per-node CPU valve until
  then).
- **Lens flare halo/streak variants** (content-driven polish).

## Phase 3 — Standing watches (unchanged)

R6 Window 4 (mobile-glue deletion — USER schedules), R4.2
ship-as-anchor (Fenris walkable-in-flight makes this nearer), clustered
lighting (Megacity), GLSL-120 removal (game flips gl-version 3 2),
Vulkan (watch only).

## Operational notes

- Gate = `run.py` both pythons SEQUENTIALLY (concurrent runs share the
  output dir); expected totals now **54 / 6 / 69** per engine.
- test_ssao has @logdepth AND @msaa4 variant rows (the runner's --msaa
  labeling landed with it); test_lens_flare runs plain.
- The known startup `GL error 0x502` noise (openworld report, response
  5) also prints on this machine in bloom-bearing tests — still
  noise-class (all checks byte-exact), still undiagnosed.
- probe_morph.py is a measurement probe (not a gate row) — rerun it
  after any skinning/munger-adjacent change.

---

## Session T addendum (2026-07-19) — morph measurement DONE

The accepted SK_SFM_Head1 measurement ran (probe_morph_gltf.py, 26
facts, identical both engines). Result: **fact #16** — panda3d-gltf
1.3.0 has three loader defects (sparse-accessor crash = upstream #103,
short-channel IndexError, max-vs-min lerp clamp) all fixed by the new
`pax3d_render.gltf_compat.install()`; with the shim, morph delivery is
correct end-to-end (CPU truth matches the Blender manifest to 4
decimals; a byte-patched weights ramp drives sliders analytically).
Fact #15 extends to glTF and joint-less meshes — ANY morphing node
needs `set_hardware_skinning(np, False)` (~+0.1 ms/frame per head).
Engine response is in PAX3D_FEEDBACK.md. Field ball: the dev re-exports
`morph_head_skinned_anim.glb` (its weights channel is all-zero — the
shape-key action never reached the exporter; also 24 fps timeline vs
the manifest's declared 30) and adds `gltf_compat.install()` to the
baker boot. When the re-export lands, promote probe facts to a gate row
(test_morph_gltf) with the real clip. GPU morph path: still queued,
now with a measured cost basis for the decision.
