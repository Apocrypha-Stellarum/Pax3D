# Handover — Session D: Bloom Fixed (R3.1) + Shadow Extent Centering (R2.4)

**Date:** 2026-07-17
**Repo state:** pax3d `01835c255a`, sfb2 `5acf839` (all work committed;
sfb2 `config/settings.json` intentionally left uncommitted — runtime-
rewritten local state, new keys have code defaults).
**Read first:** `../PAX3D_MASTER_PLAN.md` (Session D log entry),
`../PAX3D_RENDER_ARCHITECTURE.md` §2/§4/§5/§9, `CLAUDE.md`.

---

## What Session D delivered (all harness-proven)

1. **F3 blocky bloom is FIXED** — `test_bloom` green at 512×512 AND
   960×540, stock + Pax3D engines, GLSL 120 + 330. The root cause was
   **none of the three suspects in the plan**: the bloom intermediates
   were **8-bit FBOs**. `render_quad_into()` without `fbprops` creates a
   default 8-bit framebuffer and the texture bind silently rewrites the
   declared RGBA16F format. The extract's `*0.005` scale crushed the halo
   tail into a few 8-bit codes; tonemap amplified each code step into a
   band. **Diagnostic trap for posterity:** this quantization presents as
   texel-aligned flat plateaus with 1px cliffs — it perfectly mimics
   nearest-neighbor sampling and sent the investigation toward filter
   state first. It was cornered by RTM_copy_ram readback of the
   intermediates: every value was exactly n/255.
2. **Two secondary bloom defects fixed:** the 13-tap downsample kernel
   had `b`/`c` where the center sample `a` belongs (over-weighted the -y
   taps — this WAS the vertical halo asymmetry, now 0.0000-0.0004); and
   the 9-tap upsample tent filtered the same-res source while the coarser
   accumulator got one bilinear tap — now the tent filters the coarser
   accumulator per Jimenez (`texel_size` = accumulator texel). Plus
   explicit bilinear + clamp-to-edge on all bloom textures.
3. **Regression guards:** new `bloom_buffers_float` check in test_bloom
   (fails if any bloom FBO is non-float). Any NEW post pass carrying HDR
   data must pass float fbprops — this is now documented in the
   architecture doc §2.
4. **R2.4 mechanism closed:** `set_shadow_extent(radius, depth, center)`
   — center places the shadow frustum by positioning the light node.
   Lighting-neutral (DirectionalLight lights by orientation only), proven
   by three new test_shadows checks: `extent_miss_is_lit` (outside
   frustum = lit, not artifacts), `extent_recenter_shadows` (0.80→0.09 on
   an off-origin cluster), `recenter_keeps_lighting` (lit values
   identical to 3 decimals after set_pos). The old "never set_pos a
   directional light" wisdom is superseded — only the pipeline positions
   it, only update_sun rotates it.
5. **Game-side wiring (sfb2 `5acf839`):**
   `planetary_shuttle_rendering.sun_light_mode` settings key ('uniforms'
   default) passed through `plan_initialization_manager.py` (legacy
   pipeline ignores it — safe either way); `sun_position_manager.py`
   recenters the shadow frustum on the CAMERA every sun update when
   shadows are on (`shadow_extent_radius`/`shadow_extent_depth` keys,
   defaults 500/4000) — shadow resolution follows the player, no
   planet-sized extents needed. Testbed gained `--focus
   planet|station|ships|sun` (works with `--selftest`).
6. **Upstream remote fixed:** `git fetch upstream` now works (the remote
   was documented but never configured). **93 upstream commits pending**
   since the 2026-02-26 sync — still small; do the quarterly merge soon.

## How to verify the current state

```bash
C:/Python313/python.exe C:/python/pax3d/tools/paxtest/run.py
# Expect: ALL pax3d_render tests PASS (bloom now included, shadows 6/6).
# Legacy pax_pbr + pax3d_simplepbr still FAIL bloom (frozen A/B copies)
# and rebuild (F4 by design). Same results under
# C:/python/pax3d-env/Scripts/python.exe.
cd C:/python/sfb2 && python test3d_pax.py --pax3d --bloom --selftest
```

## Next work, in order

### 1. USER-GATED: the flag flips (everything else is ready)
- [ ] User flips `use_pax3d_render: true` → eyeball parity in the game.
- [ ] User flips `sun_light_mode: "directional"` → validate lit
      hemispheres at the four cardinals, then `enable_shadows: true` →
      validate terminator + ship shadows (extent auto-follows camera).
- [ ] Decide bloom-on defaults (`enable_bloom: true` + retune
      strength/intensity in the testbed with U/J/I/K — brightness rose
      now that the tail isn't quantized to zero; the per-mip tint list in
      pipeline.py reads inverted vs its comment labels — decide intent).

### 2. R3 remainder (content, after bloom-on decision)
- R3.2 physical-ish light units; R3.3 kill the game's magic compensation
  factors one per test run; R3.4 stretch: auto-exposure from the bloom
  downsample pyramid.

### 3. R1 leftovers (unchanged from Session C)
- sRGB input linearization experiment (testbed G key) → content retune plan.
- Drop GLSL-120 path once the game runs `gl-version 3 2` (full matrix
  under both baselines before/after).

### 4. R6 hygiene (cheap now)
- Quarterly upstream merge: `git fetch upstream && git merge
  upstream/master` (93 commits pending, engine C++ divergence is still
  one build-script fix — should be trivial). Rebuild + full paxtest under
  the venv wheel afterwards.

## Gotchas for the next dev

- All Session C gotchas still apply (paxtest before/after, ambient light
  in lighting tests, buffer appears after one frame, settings.json is
  runtime-rewritten, never edit the legacy pipelines).
- **New:** any post pass whose texture carries HDR data needs explicit
  float fbprops in `render_quad_into` — the silent 8-bit downgrade is
  the sneakiest failure mode in this codebase; `bloom_buffers_float`
  guards the bloom chain but a NEW chain needs its own check.
- **New:** 8-bit quantization banding looks exactly like nearest-neighbor
  filtering (flat texel-aligned plateaus, 1px cliffs). Before chasing
  sampler state, read back the intermediate texture and check whether
  values are n/255.
- `set_shadow_extent` is uniform-cost and per-frame safe; the game
  already drives it — don't add a second driver.
