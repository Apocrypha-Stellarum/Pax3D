# Handover: Session Z — GPU morphs landed (2026-07-20)

**State: fact #15 is closed, opt-in.** `set_gpu_morphs(model_np)`
renders morph sliders ON the hardware-skinning path — the measured
character-quality bottleneck (sealed visors, CPU valve that couldn't
scale) is gone. Pure Python/GLSL per canon: no build window, no wheel
change (Session-X wheel stays current), and the whole feature runs
unchanged on stock 1.10 (fact #19) — it is built entirely from
upstream primitives (data texture + vertex column + shader variant).

## What landed (one commit: pipeline + shader + gate + probe + docs)

| Piece | Delivery |
|---|---|
| API | `set_gpu_morphs(model_np, enabled=True)` → morph geom count; opt-out restores geom states byte-identically. Sits next to `set_hardware_skinning` in pipeline.py |
| Data path | Per-vdata RGB32F delta texture (width = rows, height = 2×targets; pos row 2t, NORMAL delta row 2t+1 — loader ships `normal.morph.*`, so lighting is correct), ER-003 `data_texture()` contract, baked by raw array-byte slicing; float32 `morph_index` column = both-baseline vertex addressing (GLSL 120 has no gl_VertexID) |
| Shader | GPU_MORPHS variant of pax_pbr (alpha-mask per-geom seam), MORPH_LIVE=16 compact (row, weight) slots, break at first zero weight, displacement PRE-skinning |
| Per-frame | `_step_gpu_morphs` in `_update`: reads CharacterSliders, refills the PTA only on live-set change; 52 addressable / ≤16 live (character-lane contract), overflow keeps largest \|w\| + warns once |
| Gate | test_morph_gltf +5 checks — gpu_renders_morphs (fact-#15 flip), gpu_matches_cpu rms 0.0000 (bar 0.02), sparse compose (first+last rows), byte-identical restore, convert count. 12/12 on Pax3D AND stock × both baselines |
| Perf probe | `tools/paxtest/probe_gpu_morph_bench.py` (repo probe, not a gate) on hero_wren.glb |

## Gate (Session Z canonical — UNCHANGED totals, the morph row grew)

**@game 71/6/106 Pax3D · 69/6/108 stock; @modern 70/7/106 · 68/7/108**
— identical to Session Y; FAIL sets unchanged (the six documented
rows + lighting/none @modern). Logs: `gate_z_*.log` (UTF-8, bash
redirect this time).

## The numbers (probe_gpu_morph_bench, worst-case production head)

- 8 faces × 5 live sliders: **~0.3 ms/frame morph-attributable**
  (1.27 total − 0.97 static floor) — the character lane's ≤0.5 ms
  acceptance bar is MET with margin.
- CPU valve, same scene: **63.5 ms/frame** (~50× worse).
- 32-face stretch (measured once, as asked): **2.42 ms** total.
- Slider push: 0.03 ms / 8 chars; enable: 1.17 s + 18.3 MB per face
  (one-time; pure-Python bake loop — optimize only on evidence).
- Crowd pattern: enable template → `copy_to` shares vdata + delta
  textures (24 copies = 0.24 s, zero re-bake).

## Facts worth carrying (new this session)

1. **Fact #19 (register):** GPU morphs need no engine change and no
   gl_VertexID; ram row 0 = v=0 and `set_ram_image_as('RGB')` keeps
   float order (MEASURED via TexturePeeker before building — both
   conventions re-proven end-to-end by the gate's rms 0.0000).
2. **Bench trap:** `apply_freeze_scalar` alone does NOT dirty the
   bundle — without `force_update()` (or a playing clip) a slider
   -driving perf loop measures an idle scene. The tell: +0.01 ms
   animate/static delta; with force_update it was +62.5 ms.
   (ENGINE_INTERNALS §6.)
3. Panda ships **normal deltas** with morph targets; NO tangent
   deltas (measured — tangents keep base values, invisible for faces).

## Known limits (documented in arch doc + API docstring, field-gated)

- Shadow depth pass casts the UNMORPHED silhouette (alpha-mask depth
  precedent — a valve exists: exclude_from_shadows; a morphing depth
  variant lands on field evidence).
- One PBR variant per geom: glass/alpha-mask/terrain don't stack with
  GPU_MORPHS on the same geom (if the lane ever glasses morphing eye
  prims, a combined variant is a small follow-up).
- Requires the HW-skinning path on the node — combining with the CPU
  valve double-applies (both docstrings say so).

## Repo state

- Engine repo: 1 commit this session (code + gate + probe + docs +
  feedback response). No sfb2 changes (their adoption is one call;
  the ER-less character lane communicates via PAX3D_FEEDBACK.md —
  engine response appended under their 2026-07-20 entry).
- No wheel change. Machine topology unchanged (system Python = fork;
  stock ONLY via `C:\python\stock-panda-env`).

## What the character lane owes (we watch, not drive)

- Adopt: `set_gpu_morphs(hero_np)` per hero, drop the CPU valve,
  re-run `hero_closeup.py` + `PS_BENCH=300` — the 185→133 datapoint
  re-measured on the GPU path, filed back into PAX3D_FEEDBACK.md.
- Tell us if 3×1.17 s load-time bake hurts (then: bake optimization
  on evidence) or if glass-on-eyes is ever wanted (combined variant).

## Open engine queue (updated)

- ~~GPU morph prototype~~ **DONE** (this session).
- Texture-palette skinning: still queued, still deprioritized on
  field evidence; if it ever lands it shares the same vertex shader
  region as GPU_MORPHS (one window can do both).
- Unchanged: R2.3 conveniences (design conflict noted §4.7),
  InstanceList bulk fill (profile-gated), Vulkan watch, depth-pass
  cutout shadows @modern (field-gated), height-blend rider (waiting
  on the terrain dev's albedo-alpha answer in ER-007).

## First moves next session

1. `git status` both repos + confirm machine topology (fact #11).
2. Sweep PAX3D_FEEDBACK.md / ENGINE_REQUESTS / newest sfb2 handovers —
   most likely early arrivals: the character lane's GPU-path PS_BENCH
   re-measurement, the terrain dev's height-source answer (unblocks
   the height-blend define), adoption reports on Session-Y items.
3. If quiet: the engine desk is EMPTY of committed work — idle
   capacity goes to watch items or whatever the field files next.
