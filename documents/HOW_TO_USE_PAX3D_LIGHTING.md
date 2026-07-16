> **HISTORICAL (Mar 2026) — DO NOT FOLLOW.** This guide targets the retired
> `pax3d_simplepbr` package and an integration path the game never adopted
> (the game runs its own `graphics/pax_pbr`, now superseded by
> `pax3d_render` behind the `use_pax3d_render` settings flag). The current
> usage guide is in the game repo:
> `sfb2/documents/PAX_3D_ENGINE_AND_GRAPHICS/USING_PAX3D_RENDER.md`.

# How to Use Pax3D Bloom and Tonemapping in Pax Abyssi

**Project:** Pax3D (fork of Panda3D 1.11.0-dev)
**Game:** Pax Abyssi (`C:\python\sfb2`)
**Date:** 2026-03-03

This is a practical integration guide. For deep technical details on the bloom pipeline internals, see the companion document `LIGHTING_AND_BLOOM_SYSTEM.md`.

---

## 1. Quick Start

Getting bloom working requires exactly two changes in the game's PBR initialization code.

### Step 1: Change the Import

In `C:\python\sfb2\modules\plan_initialization_manager.py`, the game currently initializes PBR rendering through `graphics.pax_pbr`. To use the Pax3D bloom pipeline instead, change the import and init call in `_initialize_pax_pbr()`:

**Before (current code, line ~283):**
```python
from graphics.pax_pbr import init as pax_pbr_init
self.app.pax_pbr = pax_pbr_init(
    enable_shadows=self.app.enable_shadows,
    msaa_samples=4,
    max_lights=10
)
```

**After (Pax3D bloom):**
```python
import pax3d_simplepbr as simplepbr
self.app.pax_pbr = simplepbr.init(
    enable_shadows=self.app.enable_shadows,
    msaa_samples=4,
    max_lights=10,
    enable_bloom=True,
    tonemap_operator='aces',
)
```

That is the minimal change. The Pax3D simplepbr fork is API-compatible with stock simplepbr -- it accepts all the same parameters plus the new bloom/tonemap ones.

### Step 2: Verify It Works

Activate the Pax3D venv, run the game, and look for bloom halos around the sun, engine exhaust, and weapon fire:

```bash
source C:/python/pax3d-env/Scripts/activate
cd C:/python/sfb2
python plan.py
```

If you see soft glow around bright objects and the overall color balance has shifted slightly (ACES tonemapping is warmer than the old Hejl-Dawson), it is working.

---

## 2. Switching Between Engines

The dual-environment setup lets Pax Abyssi run on either stock Panda3D or Pax3D without changing game code.

### The Two Environments

| Environment | Python | Engine | simplepbr | Bloom |
|-------------|--------|--------|-----------|-------|
| System Python (`C:\Python313`) | 3.13 | Stock Panda3D 1.10.16 | Stock simplepbr (pip) | No |
| Pax3D venv (`C:\python\pax3d-env`) | 3.13 (isolated) | Pax3D custom build | pax3d_simplepbr (in-repo) | Yes |

### Activating the Pax3D venv

```bash
# Git Bash / Unix shell
source C:/python/pax3d-env/Scripts/activate

# Windows cmd.exe
C:\python\pax3d-env\Scripts\activate

# PowerShell
. C:\python\pax3d-env\Scripts\Activate.ps1
```

Your prompt will show `(pax3d-env)` when the venv is active. Deactivate with `deactivate`.

### Making Imports Work on Both Engines

If the game needs to work on both stock simplepbr and pax3d_simplepbr without manual code edits, use a conditional import:

```python
try:
    import pax3d_simplepbr as simplepbr
    _PAX3D_BLOOM_AVAILABLE = True
except ImportError:
    import simplepbr
    _PAX3D_BLOOM_AVAILABLE = False
```

Then at init time:

```python
if _PAX3D_BLOOM_AVAILABLE:
    pipeline = simplepbr.init(
        enable_shadows=True,
        msaa_samples=4,
        max_lights=10,
        enable_bloom=True,
        tonemap_operator='aces',
    )
else:
    pipeline = simplepbr.init(
        enable_shadows=True,
        msaa_samples=4,
        max_lights=10,
    )
```

This way the game runs cleanly under both engines -- with bloom on Pax3D, without on stock.

### Checking Which Engine is Active

```bash
python -c "import panda3d; print(panda3d.__file__)"
```

Stock: `C:\Users\<user>\AppData\Roaming\Python\Python313\site-packages\panda3d`
Pax3D: `C:\python\pax3d-env\lib\site-packages\panda3d`

To check if pax3d_simplepbr is available:

```bash
python -c "import pax3d_simplepbr; print('Pax3D bloom available')"
```

---

## 3. API Reference

All parameters below are passed to `pax3d_simplepbr.Pipeline()` (aliased as `pax3d_simplepbr.init()`).

### Bloom and Tonemap Parameters (Pax3D additions)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_bloom` | `bool` | `False` | Enable the full bloom chain (extract + 5 downsample + 5 upsample passes). |
| `bloom_strength` | `float` | `1.0` | Extract multiplier. Controls how much scene luminance feeds into the bloom chain. Higher = more glow on everything. |
| `bloom_intensity` | `float` | `1.0` | Final composite multiplier. Scales the bloom texture when it is added to the scene before tonemapping. 0.0 = no visible bloom. |
| `bloom_levels` | `int` | `5` | Mip chain depth (clamped to 2-8). More levels = wider bloom spread. |
| `tonemap_operator` | `str` | `'aces'` | Tonemap curve. One of: `'aces'`, `'reinhard'`, `'uncharted2'`, `'hejl_dawson'`. |

### Inherited simplepbr Parameters (unchanged)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `msaa_samples` | `int` | `4` | MSAA sample count (0, 2, 4, 8, 16). |
| `max_lights` | `int` | `8` | Maximum simultaneous lights in the PBR shader. |
| `enable_shadows` | `bool` | `True` | Enable shadow mapping. |
| `shadow_bias` | `float` | `0.005` | Shadow map depth bias. |
| `exposure` | `float` | `0.0` | EV stops (power of 2). Shader receives `2^exposure`. |
| `use_normal_maps` | `bool` | `False` | Enable normal map sampling. |
| `use_emission_maps` | `bool` | `True` | Enable emission map sampling. |
| `use_occlusion_maps` | `bool` | `False` | Enable ambient occlusion map sampling. |
| `enable_fog` | `bool` | `False` | Enable exponential fog. |

### Runtime Update Categories

Parameters can be changed at runtime by assigning to the Pipeline instance. The `__setattr__` override handles the update automatically. The cost depends on the parameter:

**Uniform-only updates (instant, no buffer rebuild):**

| Parameter | What Happens |
|-----------|--------------|
| `bloom_strength` | Updates the `bloom_strength` uniform on the extract quad. |
| `bloom_intensity` | Updates the `bloom_intensity` uniform on the tonemap quad. |
| `tonemap_operator` | Updates the `tonemap_operator` uniform on the tonemap quad (integer index). Invalid names fall back to `'aces'` with a warning. |
| `exposure` | Updates the `exposure` uniform on the tonemap quad (converted to `2^value`). |
| `sdr_lut_factor` | Updates the SDR LUT blend factor uniform. |

These are free to call every frame if needed (e.g., from a debug console slider).

**Buffer rebuild (destroys and recreates the entire FilterManager chain):**

| Parameter | What Happens |
|-----------|--------------|
| `enable_bloom` | Adds or removes all 11 bloom passes. |
| `bloom_levels` | Changes the mip chain depth (2-8). |
| `msaa_samples` | Changes MSAA on the scene render buffer. |
| `window` | Retargets to a different GraphicsOutput. |
| `camera_node` | Retargets to a different camera. |

Buffer rebuilds are expensive (causes a frame hitch). Do not change these every frame.

### Runtime Example

```python
# Assuming 'pipeline' is the Pipeline instance returned from init()

# Instant updates (uniform-only):
pipeline.bloom_strength = 2.0          # More scene luminance feeds bloom
pipeline.bloom_intensity = 0.5         # Reduce final bloom brightness
pipeline.tonemap_operator = 'reinhard' # Switch to Reinhard curve
pipeline.exposure = 1.0                # Brighten scene by 1 EV stop

# Buffer rebuild (avoid doing this frequently):
pipeline.enable_bloom = False          # Disable bloom entirely
pipeline.bloom_levels = 3              # Fewer levels = narrower bloom + fewer passes
```

---

## 4. Removing Legacy Compensations

The game currently uses several magic numbers to compensate for the lack of bloom. With the Pax3D bloom pipeline active, these should be removed or adjusted because bloom now handles bright-object glow naturally.

### 4.1 The 0.45x Sun Glow RGB Reduction

**Files:**
- `C:\python\sfb2\graphics\draw_distant_sun.py` (lines 423-424, 482-483, 543-544)
- `C:\python\sfb2\graphics\lens_flare_sun_model.py` (line 36, used at line 186)

**What it does:** Multiplies the brightness of all additive sun glow billboard cards and sun rays by 0.45 when `_pbr_mode` is True. This is the `PBR_BRIGHTNESS_COMPENSATION` constant.

**Why it exists:** Without bloom, additive-blended glow cards rendered with `setShaderOff()` bypass simplepbr's tonemapping. They appear in the final framebuffer as raw additive color, which looks over-bright and flat compared to the tonemapped scene. The 0.45x reduction was a manual correction to bring the glow brightness into a visually acceptable range.

**Why bloom makes it unnecessary:** With bloom enabled, the HDR scene buffer captures the full brightness of additive glow layers. The bloom extract pass picks up these bright fragments and produces natural glow halos. The tonemap pass then compresses the combined scene + bloom into display range. The result is physically correct -- bright glow that rolls off smoothly instead of clipping to white.

**What to change:** Remove or guard the 0.45x multiplication. In `draw_distant_sun.py`, the three locations are:

```python
# Line ~424 in _create_additive_sun_glow():
if self._pbr_mode:
    base_brightness *= 0.45  # <-- Remove or set to 1.0

# Line ~483 in _create_km_outer_glow():
if self._pbr_mode:
    base_brightness *= 0.45  # <-- Remove or set to 1.0

# Line ~544 in _create_additive_sun_rays():
if self._pbr_mode:
    ray_brightness *= 0.45  # <-- Remove or set to 1.0
```

In `lens_flare_sun_model.py`:
```python
# Line 36:
PBR_BRIGHTNESS_COMPENSATION = 0.45  # <-- Change to 1.0
```

**Note:** You may find that removing the compensation makes the sun glow slightly too bright with bloom. If so, tune `bloom_strength` down slightly rather than re-adding the compensation. The goal is to let bloom handle the brightness management rather than manual per-effect scaling.

### 4.2 The 0.25x Weapon RGB Reduction

**File:** `C:\python\sfb2\graphics\shuttle_weapon_effects.py` (line 138)

**What it does:** Sets `_pbr_intensity = 0.25` when `_pbr_mode` is True. This multiplier is applied to all weapon bolt core colors, corona colors, muzzle flash colors, and trail segment colors throughout the file.

**Why it exists:** Same reason as the sun glow -- additive-blended weapon bolts with `setShaderOff()` appear too bright without tonemapping. The 0.25x factor was tuned to make plasma bolts look like glowing projectiles rather than flat white rectangles.

**Why bloom makes it unnecessary:** Bloom picks up the bright weapon fragments from the HDR buffer and wraps them in a natural glow halo. The ACES tonemap compresses the peak brightness smoothly. Weapon bolts will look like they are actually emitting light rather than just being bright colored cards.

**What to change:**

```python
# Line ~138 in __init__():
self._pbr_intensity = 0.25 if self._pbr_mode else 1.0
# Change to:
self._pbr_intensity = 1.0  # Bloom handles bright additive effects

# Line ~139:
self._pbr_corona_scale = 0.6 if self._pbr_mode else 1.0
# Change to:
self._pbr_corona_scale = 1.0  # Bloom provides natural glow spread
```

The same `_pbr_intensity` is also passed to the impact manager (`shuttle_weapon_impacts.py` line 157). Changing it in `shuttle_weapon_effects.py` will propagate automatically.

### 4.3 The 1.8x Corona/Bell Scale

**File:** `C:\python\sfb2\graphics\engine_exhaust_manager.py` (line 135)

**What it does:** Uses `1.8` as the default `ftl_bell_scale` for FTL engine exhaust bell geometry. This oversizes the engine glow to fake a bloom-like halo around the exhaust.

**Why it exists:** Without bloom, engine exhaust had no glow spread. Oversizing the geometry was the only way to make it look like the exhaust was emitting light.

**Why bloom makes it unnecessary:** The bloom pipeline naturally captures bright exhaust fragments and spreads them into a soft halo. The exhaust geometry can be sized to match its physical extent, and bloom provides the visual glow for free.

**What to change:** Reduce `ftl_bell_scale` toward 1.0 and let bloom handle the glow effect. The exact value will need visual tuning -- start with 1.2 and adjust.

### 4.4 What to Keep

**Keep `setShaderOff()` on additive-blended nodes.** Sun glow cards, weapon bolts, engine exhaust, and nebula billboards all use `setShaderOff()` to bypass the PBR shader. This is still correct -- these nodes use additive blending and have no PBR materials. They do not need to be lit by the PBR pipeline.

With bloom, `setShaderOff()` nodes still write their bright fragments to the HDR scene buffer. The bloom extract pass reads this buffer and picks up those fragments. So bloom captures bright additive effects regardless of whether they go through the PBR shader.

**Keep `setLightOff()` on additive-blended nodes.** Same reasoning -- these nodes are self-illuminating effects that should not respond to scene lights.

---

## 5. Tuning Guide

### 5.1 Start with Defaults

The default settings are designed to work well for typical Pax Abyssi scenes:

```python
pipeline = simplepbr.init(
    enable_bloom=True,
    bloom_strength=1.0,
    bloom_intensity=1.0,
    exposure=0.0,
    tonemap_operator='aces',
)
```

### 5.2 Parameter Tuning

**`bloom_strength`** (default: 1.0) -- Controls how much scene luminance feeds into the bloom chain. This is the extract multiplier. The shader applies `color * bloom_strength * 0.005`, so at 1.0 only genuinely bright pixels produce visible bloom.

- Increase (1.5-3.0): Everything glows more. Creates a dreamier, more atmospheric look. Good for establishing shots or close solar approach.
- Decrease (0.3-0.7): Only the very brightest pixels bloom. Subtler, more restrained. Good for tactical/combat scenes.
- 0.0: Effectively no bloom (but the passes still run -- use `enable_bloom=False` to actually disable).

**`bloom_intensity`** (default: 1.0) -- Scales the final bloom composite that gets added to the scene before tonemapping.

- 0.0: Bloom is computed but not visible (useful for fade-in effects).
- 0.5: Half-strength bloom. Good as a subtle glow.
- 1.0: Full bloom effect.
- Above 1.0: Exaggerated bloom. Can look washed out if overdone.

The difference from `bloom_strength`: strength controls how much goes INTO the bloom chain (affects which pixels bloom and how much), while intensity controls how much of the RESULT appears in the final image. Use strength to control bloom selectivity, intensity to control overall bloom visibility.

**`exposure`** (default: 0.0) -- EV stops, applied as a power of 2. The shader receives `2^exposure` as a multiplier on the scene color after bloom composite but before tonemapping.

- 0.0: Neutral (multiplier = 1.0).
- +1.0: Scene is 2x brighter. Good for dark scenes.
- -1.0: Scene is 0.5x as bright. Good for very bright scenes (close solar approach).
- Range is unbounded, but useful values are typically -3.0 to +3.0.

**`tonemap_operator`** (default: `'aces'`) -- Controls the HDR-to-display mapping curve.

| Operator | Character | Best For |
|----------|-----------|----------|
| `'aces'` | Filmic. Warm midtones, saturated highlights, good rolloff. Industry standard. | General use. Recommended default. |
| `'reinhard'` | Soft. Preserves highlight detail at the cost of contrast. | Debug, or scenes where you need to see detail in very bright areas. |
| `'uncharted2'` | Contrasty. Strong shoulder and toe. Dramatic look. | Cinematic sequences, dramatic lighting setups. |
| `'hejl_dawson'` | Legacy simplepbr look. Built-in sRGB gamma. Lower saturation than ACES. | Backward compatibility testing. If colors look "wrong" compared to stock simplepbr, try this. |

### 5.3 Per-Scene Recommendations

**Deep space (interstellar, far from any star):**
```python
pipeline.exposure = 0.5       # Slight brightness boost for dark scenes
pipeline.bloom_strength = 1.0 # Default -- stars and distant objects bloom naturally
```

**Planetary approach (orbit, moderate stellar distance):**
```python
pipeline.exposure = 0.0       # Neutral
pipeline.bloom_strength = 1.0 # Default
```

**Close solar approach (near star, intense light):**
```python
pipeline.exposure = -1.0      # Dim scene to prevent wash-out
pipeline.bloom_strength = 1.5 # Increase bloom for dramatic solar glow
# The sun glow billboards will bloom intensely through the chain
```

**Weapon fire / combat:**
```python
pipeline.bloom_strength = 1.0 # Default -- bolts bloom naturally from their additive brightness
# With the 0.25x compensation removed, weapon bolts will bloom strongly.
# If too much, reduce bloom_strength to 0.7 during combat.
```

**Cinematic / beauty shots:**
```python
pipeline.tonemap_operator = 'uncharted2'  # Dramatic contrast
pipeline.bloom_strength = 1.5             # Lush bloom
pipeline.exposure = 0.3                   # Slight brightness lift
```

### 5.4 Performance

The bloom chain adds 11 FilterManager passes on top of the stock simplepbr pipeline:

| Pass Type | Count | Resolution |
|-----------|-------|------------|
| Bloom extract | 1 | Full resolution |
| Downsample | 5 | 1/2, 1/4, 1/8, 1/16, 1/32 |
| Upsample | 5 | 1/32 back up to full |

Total additional passes: 11 (most at reduced resolution). The downsample and upsample passes are progressively cheaper because they operate on smaller textures.

Typical overhead: less than 2ms on a modern discrete GPU at 1080p. On integrated graphics or at 4K, the overhead may be higher.

To reduce cost:
- Set `bloom_levels=3` for fewer passes (7 extra instead of 11) with narrower bloom spread.
- Set `enable_bloom=False` to eliminate all bloom passes entirely.

---

## 6. Troubleshooting

### "Bloom looks too strong / everything is washed out"

Reduce `bloom_strength` (controls input) or `bloom_intensity` (controls output). Try `bloom_strength=0.5` first. If the sun glow compensations (0.45x) have not been removed yet, there may be a conflict -- the compensations dim the glow cards while bloom is trying to amplify them. Remove the compensations first, then tune bloom parameters.

### "Bloom looks too weak / I can barely see it"

Increase `bloom_strength` to 2.0 or 3.0. Make sure `bloom_intensity` is at 1.0. Check that `enable_bloom=True` was actually passed (the default is False). Check the console for any FilterManager setup errors.

### "Scene is too dark"

Increase `exposure`. Try `pipeline.exposure = 1.0` (doubles scene brightness). The ACES tonemap curve compresses highlights more aggressively than Hejl-Dawson, which can make overall brightness feel lower. A small positive exposure compensates.

### "Scene is too bright"

Decrease `exposure`. Try `pipeline.exposure = -0.5`. Also check whether the legacy PBR compensations (0.45x, 0.25x) have been removed -- if they have, additive effects are brighter than before and the scene may need a slight negative exposure adjustment.

### "Colors look different from stock simplepbr"

That is the ACES tonemap operator. ACES has warmer midtones, more saturated highlights, and a different contrast curve compared to Hejl-Dawson (the stock simplepbr default). To get the legacy look back, set `tonemap_operator='hejl_dawson'`. But consider keeping ACES -- it generally produces more visually pleasing results for space scenes.

### "ImportError: No module named pax3d_simplepbr"

The `pax3d_simplepbr` package lives in the Pax3D repo at `C:\python\pax3d\pax3d_simplepbr\`. It needs to be importable. Options:

1. **Pax3D venv is active** and `C:\python\pax3d` is on `sys.path` (add it to `PYTHONPATH` or add a `.pth` file in the venv's site-packages).
2. **Install it** as a package in the venv: `pip install -e C:\python\pax3d` (if a setup.py/pyproject.toml exists) or create a symlink.
3. **Add to sys.path** at game startup:
   ```python
   import sys
   sys.path.insert(0, r'C:\python\pax3d')
   ```

### "Performance regression / frame rate drop"

The bloom chain adds approximately 11 FilterManager passes. If the frame rate drop is unacceptable:

1. Reduce bloom levels: `pipeline.bloom_levels = 3` (7 extra passes instead of 11, narrower bloom).
2. Disable bloom entirely: `pipeline.enable_bloom = False` (restores stock simplepbr performance).
3. Check your GPU. Integrated graphics may struggle with the additional RGBA16F render targets.

### "Bloom does not affect additive-blended nodes"

Bloom DOES capture bright fragments from additive-blended nodes (sun glow, weapon bolts, engine exhaust) because they write into the shared HDR scene buffer that the bloom extract pass reads. If you do not see bloom around these effects:

1. Check that the effects are actually bright. With the 0.45x / 0.25x compensations still in place, the effects may be too dim to produce visible bloom.
2. Check that `enable_bloom=True` is set.
3. Check that `bloom_strength` is at least 1.0.

### "FilterManager error on startup"

The Pax3D simplepbr fork uses FilterManager to manage all post-processing buffers. If the game also creates its own CommonFilters or FilterManager instance (the current code in `plan_initialization_manager.py` has a lazy CommonFilters for billboard bloom), there may be a conflict. Disable the game's CommonFilters-based bloom when using pax3d_simplepbr's built-in bloom -- they are redundant and may fight over framebuffer attachments.
