# Baked Effects Guide — flipbook explosions, impacts, and fireballs

**Status: CURRENT** (Session AD, 2026-07-23). The field guide for the
VFX lane: how baked effect footage travels from a vendor pack to a
detonation in-game. Engine mechanism detail:
`PAX3D_RENDER_ARCHITECTURE.md` §9 (Session AD entry); program record:
`PAX3D_MASTER_PLAN.md` §4.16; gate: `tools/paxtest/test_effects.py`.

---

## 1. Why baked footage (and why not anything else)

Panda3D never did explosions well: the stock particle system is dated,
and no real-time engine has a volumetric fire path (UE only *imports*
baked VDBs since 5.3). The industry technique for cinematic
explosions/fire/smoke at game cost is **baked fluid-sim footage on
camera-facing quads** — that is this lane.

Two closed decisions shape the workflow (do not re-litigate without
new evidence):

- **The Pax3D wheel builds `--no-ffmpeg`** — there is NO video decode
  engine-side. The sanctioned carrier is the flipbook atlas
  (`tools/gen_flipbook.py` → `play_flipbook`), VRAM-resident, zero
  per-frame uploads, identical on stock and Pax3D. The "trimmed
  flipbooks, no ffmpeg build window" decision was closed in Session V
  (ship-lane 634 + user sign-off).
- **`spawn_effect()` is a composition of already-gated parts** — zero
  new shader code (§4 below). Any future effect feature should try
  composition first for the same reason: every piece arrives
  pre-proven.

## 2. The source pack — intake facts (measured Session AD)

| | |
|---|---|
| Pack | CGVision "Air and Space Explosions" |
| Location | `C:\python\asset_sources\Explosions\` (28 MOVs) |
| Format | ProRes 4444, 2048×1500, alpha+beauty in ONE `yuva444p12le` stream, 25 fps |
| Alpha semantics | **PREMULTIPLIED — measured, not assumed**: RGB ≤ alpha everywhere except a deliberate additive spark/glow tail; `a == 0` regions are black to 1e-5 |
| Consequence | **Bake as-is. No unpremultiply, no conversion** — premultiplied is exactly what `spawn_effect`'s blend composites (straight-alpha footage from another vendor WOULD need conversion at intake; measure first: check `max(RGB) ≤ a` over sample frames) |
| Decoder | winget ffmpeg **8.0.1** on this machine decodes ProRes 4444 alpha cleanly (an old "2013 ffmpeg" note in the tool was stale — fixed) |

First bake shipped: `5_1.mov` → 51 frames @ 12.5 fps, 1792×1504 atlas,
0.8 MB PNG → `C:\python\sfb2\assets\effects\explosion_5_1_flipbook.{png,json}`.
The clip reads: flash → fireball → smoke dissolve, ~4 s.

## 3. Baking — `tools/gen_flipbook.py`

```bash
# explosion footage: decimate 25 fps -> 12.5 and downscale
python tools/gen_flipbook.py 5_1.mov --fps 12.5 --cell 256x188

# from an already-exported frame directory (alphabetical order):
python tools/gen_flipbook.py frames_dir/ --fps 12.5
```

Output: `<name>_flipbook.png` + `<name>_flipbook.json` sidecar
(`{cols, rows, frames, fps, cell_w, cell_h, alpha, source}`) and a
paste-ready `spawn_effect(...)` call (alpha atlases) or
`set_screen`/`play_flipbook` call (RGB atlases).

Alpha handling is automatic: ffprobe detects alpha-carrying pixel
formats, extraction pins `-pix_fmt rgba`, scaling and assembly
preserve the channel, unused trailing atlas cells stay fully
transparent. **Alpha-free sources produce the byte-identical 3-channel
atlas the tool always made** — screens are unaffected (both directions
proven in-gate by test_effects).

Levers, in taste order:

- **`--fps`** — THE smoothness lever. 12.5 (every 2nd source frame) is
  the shipped intake taste; 25 doubles smoothness AND atlas
  size/VRAM. Flipbook playback holds frames (no cross-fade), so low
  fps reads as stutter on slow-evolving smoke before it does on fast
  flashes.
- **`--cell WxH`** — per-frame resolution. Keep the source aspect
  (2048×1500 → e.g. 256×188). The quad is emission-only and usually
  fills a modest screen area; 256-wide cells hold up well at
  gameplay range.
- **`--cols` / `--max-frames`** — force grid shape / trim the tail.
  Trailing near-invisible smoke frames are the first thing to cut
  when an atlas crowds the 8192 px GPU limit (the tool warns; 4096 to
  be safe on older cards).
- Loops read best when fps divides the source duration evenly
  (seamless wrap) — mostly relevant for screens, not one-shot
  explosions.

sRGB note: atlases are gamma-2.2 content. Under the (now-approved)
`srgb_inputs` contract the game's format walk flags them sRGB like any
authored emission map — nothing to do at bake time.

## 4. Playing — `pipeline.spawn_effect()`

```python
import json
meta  = json.load(open('assets/effects/explosion_5_1_flipbook.json'))
atlas = loader.load_texture('assets/effects/explosion_5_1_flipbook.png')

fx = pipeline.spawn_effect(atlas, meta=meta, pos=impact_pos,
                           size=9.0, emission_scale=2.0)
# one-shot: the pipeline reaps the quad itself when playback ends.

loop_fx = pipeline.spawn_effect(atlas, meta=meta, loop=True)
pipeline.remove_effect(loop_fx)      # loops (and early cancels) need this
```

| Parameter | Meaning |
|---|---|
| `texture` | RGBA atlas from gen_flipbook |
| `meta=` | the sidecar dict — cols/rows/frames/fps read from it (or pass `cols`/`rows`/`num_frames`/`fps` explicitly) |
| `parent`, `pos` | where it lives — parent to a ship node and the explosion rides the ship; default parent is the scene root |
| `size` | world-space quad WIDTH; height follows the cell aspect |
| `emission_scale`, `emission_color` | intensity/tint; scale > 1 pushes the core into bloom (HDR-legal) |
| `billboard` | default True (`set_billboard_point_eye`); False = static two-sided card |
| `loop` | False = self-reaping one-shot; True = plays until `remove_effect()` |
| `depth_bias` | int, `set_depth_offset` units — win the depth test near a contact surface |

Returns the effect NodePath — reparent/move it freely while it plays.
If the game removes the node itself, the pipeline purges the dead
registrations on the next reap (recompile-safe).

**What the composition guarantees** (each part separately gated):

- **Analytically unlit**: `set_screen(albedo=False, metallic=1)` —
  black metallic base makes `diffuse_color` and `spec_color` EXACTLY 0
  in the frag; sun, ambient, and local lights cannot tint the footage
  (test_effects sweeps ambient ×4 and the effect does not move).
- **Premultiplied compositing**: `set_glass()` — emission adds at full
  strength (the footage carries its own coverage), background shows
  through `1 − a`, `a = 0` texels are pure additive glow that occludes
  nothing.
- **Haze-proof**: fog/atmosphere inscatter is coverage-weighted — haze
  cannot paint the quad's transparent texels.
- **Shadow-proof**: `exclude_from_shadows()` applies automatically when
  a caster mask is configured — otherwise the depth pass would stamp
  the quad's FULL silhouette (fact #17: no depth path reads alpha).
- **Depth**: the quad depth-TESTS (hull geometry occludes it) but never
  depth-writes (overlapping effects compose in the transparent bin).
- **Byte-identical when unused**: empty registries = zero per-frame
  cost and rms 0.0 vs a pipeline that never spawned an effect (gated).

For impacts ON a surface: spawn at `contact + normal * epsilon`
(game-side) or pass `depth_bias`. Soft-particle depth fade (the quad
fading where it nears geometry) is the evidence-gated slice-2 item —
file footage of quad-intersection artifacts before asking for it.

## 5. Worked adoption — planetside detonations (sfb2, Session AD)

`planetside/player/weapons/effects.py` is the reference integration
(~50 lines at adoption; game session 717 extended it to both
detonation paths):

- **Optional wiring**: `getattr(app, 'pipeline', None)` then
  `getattr(pipeline, 'spawn_effect', None)`; atlases + sidecars loaded
  from `assets/effects/` in a try/except per path. Missing pipeline
  (stock A/B) or a missing atlas ⇒ the old corona-only detonation for
  that path, untouched.
- **Where it fires** (s716): `_begin_impact` plays footage on EVERY
  detonation from a two-take dict (`EXPLODE_ATLASES`): ground contact
  → a low-fireball/rising-plume take, billboard lifted just under
  half the card height so the plume roots on the terrain, with
  `depth_bias=` for the contact seam (the §4 surface recipe, used for
  real); airburst (dedicated `EffectSpec.fuse` expiry, map-edge — and
  structure hits when those land) → a spherical take.
- **Composition with the existing kit**: the 0.45 s light pulse reads
  as the flash; the ~3.5-5 s footage carries the fireball + smoke
  aftermath. Constants: `EXPLODE_FX_SIZE = 9.0` air /
  `EXPLODE_FX_SIZE_GROUND = 8.0` (metres), `EXPLODE_FX_EMISSION =
  2.0` (core into bloom), `EXPLODE_FX_BIAS = 2`.
- **Verified offscreen**: bolt expires → fireball spawns → self-reaps
  ~4 s later, all pipeline registries empty after (and the game's
  scene-switch leak test stays green).

## 6. Retune levers and the watch list

Taste levers, cheapest first: `EXPLODE_FX_SIZE` / `EXPLODE_FX_EMISSION`
game-side; bake fps 12.5 → 25 (smoothness ×2, VRAM ×2); cell size;
bake more of the 28 clips (variety — the pack has air, space, and
directional variants).

Watch items (field-evidence-gated, none blocking):

- **glass_spec env ghost**: two bounded residuals survive the
  metallic-1-black zeroing — the f0=0 direct-Fresnel grazing lobe and
  the IBL BRDF-LUT bias term when an env map is bound. Both measured
  far below working emission levels. If a faint quad-shaped
  reflection ever shows on an env-mapped scene, the fix shape is an
  EFFECT define zeroing `glass_spec` — file the sighting first.
- **Soft-particle depth fade** (slice 2): wanted only when effects
  visibly slice through terrain/hulls in real gameplay footage.
- **Multi-angle bakes** (slice 2): a billboard fireball orbited slowly
  reads flat; only matters for slow fly-bys of large explosions.
- **Testbed hotkey**: not yet wired (`test3d_pax.py`) — worth adding
  with the next testbed pass.

## 7. Verifying changes

```bash
C:/python/pax3d-env/Scripts/python.exe tools/paxtest/run.py --tests effects
C:/python/stock-panda-env/Scripts/python.exe tools/paxtest/run.py --tests effects
```

test_effects (13 analytic checks, ×@game/@directional, both engines):
premultiplied composite, additive glow, opaque core,
unlit-under-ambient ×4, billboard vs rotated parent, one-shot
self-cleanup (registries back to empty), shadow-mask exclusion, and
gen_flipbook exactness (RGBA assembly exact / RGB output byte-identical
to the pre-alpha tool). Touch `spawn_effect`, `set_screen`,
`set_glass`, `play_flipbook`, or the tool — run it before and after.
