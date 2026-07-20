# Handover: Session AB — GPU morph crowds: zero-copy bake + independent clone faces (2026-07-21)

**State: the character lane's crowd scenario works end-to-end and the
enable-cost objection is dead before it was filed.** No API additions —
`set_gpu_morphs` got ~15× cheaper to enable and clone-aware. Pure
Python/GLSL per canon; no wheel change (Session-X wheel stays current);
runs unchanged on stock 1.10.

## What landed (one commit: pipeline + shader + gate + probe + docs + feedback response)

| Piece | Delivery |
|---|---|
| Zero-copy bake | Delta texture flipped VERTEX-MAJOR (W=2×targets, H=rows) = byte-identical to the loader's own interleaved morph array ⇒ raw-bytes upload when column order matches slider order (wren/juno 5/7 vdatas ≈95% of rows); numpy column gather otherwise (numpy ships with panda3d-gltf; kade's pack is non-canonical on 5/6 prims); pure-Python per-row floor kept. `pax_pbr.vert` GPU_MORPHS block: axis swap. `morph_index` fill is bulk (`array('f')` → `handle.set_data`) |
| Clone registration | `set_gpu_morphs(clone)` on a copy_to clone of an enabled template: detects per-geom `u_morph_tex` in the as-copied states, skips the bake (ZERO new textures), registers the clone's own sliders + PTA. Without the call a clone WEARS THE TEMPLATE'S FACE (inherited uniform block — the synchronized-blink defect). Clone opt-out parks a zeroed block (clearing asserts at draw — the gate caught it); template untouched |
| Correctness fixes | Bake cache keyed by `vdata.this` (id() is wrapper-unstable and can false-hit after collection — fact #20); `_add_morph_index_column` idempotent (double-convert used to duplicate the column) |
| Gate | test_morph_gltf +5 → **17 checks/config**: `bake_fast_matches_reorder` (3-way byte compare + fast-path-availability pin on loader output), `copy_reuses_textures` (pointer-set equality), `copy_drives_own_face`, `copy_ignores_template_sliders` (rms 0.000000), `copy_optout_isolated` |
| Probe | probe_gpu_morph_bench: `--hero` arg; 32-face leg now registers + independently drives every clone (the honest plaza); copy-leg wording corrected |

## Gate (Session AB canonical — totals UNCHANGED, the morph row grew)

**@game 71/6/106 Pax3D · 69/6/108 stock; @modern 70/7/106 · 68/7/108**
— identical to Sessions Y/Z/AA; FAIL sets unchanged (the six documented
rows + lighting/none @modern). morph_gltf/pax3d_render 17/17 on all
four configs. Logs: `gate_ab_*.log` + `.json` (bash redirect, UTF-8).

## The numbers (all three shipped heroes, this machine)

- Enable/bake per face: **wren 0.07 s, kade 0.08 s, juno 0.08 s**
  (was 1.17 s); textures 18.3 / 14.5 / 18.2 MB (unchanged size).
- 8-face morph-attributable: **0.19 ms** (interleaved min-of-5 —
  cross-run deltas drifted 0.4–0.8 ms under background load; see the
  new ENGINE_INTERNALS §6 trap entry).
- 32 faces ALL independently driven: **4.3 ms** total (the old
  2.42 ms had 24 statues wearing one face). 24 clones copy+register
  0.25–0.49 s, zero re-bake.
- Clone RAM: vdata is DEEP-copied by the Character (~18 MB per
  production head); delta textures are pointer-shared. A
  strip-morph-columns lever exists on paper, unbuilt pending evidence.

## Facts worth carrying (new this session)

1. **Fact #20 (register):** Panda wrapper `id()` lies both ways —
   same object ⇒ different wrappers; collected wrapper's id reusable.
   Key caches / compare identity by `.this`. Session Z's "clones share
   vdata" was this artifact (textures shared, vdata copied).
2. The loader stores ALL morph columns in ONE tight interleaved array
   per vdata `[v.morph.s, n.morph.s, …]` — that layout IS a
   vertex-major delta texture. Vendor packs differ in column ORDER
   (character_02 non-canonical, character_03/juno canonical) — hence
   the 3-rung bake ladder, byte-compared in-gate.
3. Sub-ms perf attribution needs an INTERLEAVED in-process A/B
   (min per leg), not cross-run comparisons (ENGINE_INTERNALS §6).

## Field traffic this session (PAX3D_FEEDBACK.md 2026-07-21 + response)

- Character dev ADOPTED apply_alpha_masks for card hair (sfb2 653,
  `fix_card_hair()`): M_alpha's fixed-function-only cull test =
  fact #17's class; PS_BENCH 17.1→16.8 ms. ACKed.
- **Cutout-shadow depth path: field evidence piece #1 FILED** (hair
  casts unmasked card silhouette; LOW, their grading). Trigger to
  build: a second filing or a re-grade. It's a contained depth-pass
  variant at a known seam; the GPU-morph unmorphed-silhouette rider
  stays separately gated.
- Four hair questions posed in the response (alpha modes across the
  library, 0.35 cutoff provenance, fringe quality vs alpha-to-coverage
  evidence, hair-never-morphs confirmation).

## What the character lane owes (we watch, not drive)

- The hero_closeup + PS_BENCH=300 GPU-path re-measure (185→133
  datapoint) — still the adoption closer, now with no enable hitch.
- Crowd adoption when a plaza scene lands: enable template → copy_to
  → `set_gpu_morphs(clone)` per clone.
- Answers to the four hair questions (none blocking).

## Open engine queue (updated)

- Cutout-shadow depth variant: evidence piece #1 on file (LOW) —
  armed, waiting for piece #2 or a re-grade.
- Texture-palette skinning: unchanged (queued, deprioritized on field
  evidence; shares the GPU_MORPHS vertex-shader region).
- Strip-morph-columns clone-RAM lever: paper only, evidence-gated.
- Unchanged: R2.3 conveniences, InstanceList bulk fill
  (profile-gated), Vulkan watch.

## First moves next session

1. `git status` both repos + machine topology (fact #11: stock ONLY
   via `C:\python\stock-panda-env`; system Python = fork).
2. Sweep PAX3D_FEEDBACK.md / ENGINE_REQUESTS / newest sfb2 handovers —
   likely arrivals: character lane's GPU-path re-measure + hair
   answers, terrain dev's adoption A/Bs (height_blend/hex_offset/
   understory re-enable), anything from the ships lane on ER-005
   adoption.
3. If quiet: the desk is EMPTY of committed work again.
