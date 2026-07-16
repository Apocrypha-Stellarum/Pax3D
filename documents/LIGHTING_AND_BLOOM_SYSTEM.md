> **HISTORICAL (Mar 2026).** Describes `pax3d_simplepbr`, which is now
> RETIRED — its features were merged into `pax3d_render/` (July 2026),
> which the game consumes via the `use_pax3d_render` flag. The bloom
> implementation described here shipped with a blocky-halo defect (fix is
> phase R3). Current docs: `PAX3D_RENDER_ARCHITECTURE.md` and the game
> repo's `USING_PAX3D_RENDER.md`.

# Pax3D Lighting and Bloom System

**Project:** Pax3D (fork of Panda3D 1.11.0-dev)
**Repository:** github.com/Apocrypha-Stellarum/Pax3D
**Game:** Pax Abyssi Space Simulation
**Date:** 2026-03-03

---

## 1. Overview

Pax3D is a fork of the Panda3D game engine, created specifically for the Pax Abyssi space simulation. The fork was motivated by two categories of rendering problems that stock Panda3D + simplepbr did not solve:

1. **Directional lighting confusion.** Panda3D's `DirectionalLight` has two independent direction representations (`_direction` CycleData field and NodePath HPR) that are not kept in sync. Combined with mesh winding differences, this caused months of debugging to find a working light orientation formula.

2. **No bloom or HDR tonemapping control.** simplepbr 0.13.1 provides PBR shading and a basic Hejl-Dawson tonemap, but no bloom, no exposure control beyond a single uniform, and no choice of tonemap operator. For a space simulation with extreme dynamic range (stars, engines, weapons, deep space), this forced the game to use fragile per-effect magic numbers to manually compensate.

Pax3D resolves both problems. Phase 1 (directional lighting) was resolved through investigation -- the root cause was planet mesh winding, not an engine bug. Phase 2 (bloom + HDR tonemapping) was implemented by forking simplepbr into the engine repository and extending its post-processing pipeline with a full Kawase bloom chain and selectable tonemap operators.

### What Changed from Upstream

| Component | Change | Files |
|-----------|--------|-------|
| simplepbr fork | Forked simplepbr 0.13.1 into `pax3d_simplepbr/` with bloom chain and ACES tonemapping | 11 files in `pax3d_simplepbr/` |
| makepanda | `oscmd()` respects `ignoreError` for binary-not-found | `makepanda/makepandacore.py:677-681` |
| Engine C++ | No changes yet -- lighting issue was resolved without engine modification | -- |

---

## 2. Phase 1: Directional Lighting (Resolved)

### 2.1 The Problem

Pax Abyssi uses one directional light (the local star) to illuminate planets, moons, ships, and stations. After months of investigation, the lit hemisphere of planets faced the wrong direction depending on which HPR formula was used. Four different formulas were tested live. Three produced visually wrong results.

The working formula (Formula B) contradicted the algebraic derivation that predicted the opposite formula (Formula C) should be correct. The same simplepbr shader, applied to two different sphere meshes, produced opposite lighting results.

### 2.2 Root Cause Analysis

Five interacting factors were identified:

| Factor | Description |
|--------|-------------|
| **Two disconnected direction representations** | `DirectionalLight._direction` (CycleData field, default = `LVector3::forward()`) and the NodePath HPR transform are independent. `setHpr()` does NOT update `_direction`. The shader pipeline reads `-(get_direction() * light_mat)` where `light_mat` comes from the NodePath transform. They interact only through matrix multiplication. |
| **HPR formula confusion** | Formula B (`heading = atan2(-sun_dir.x, sun_dir.y)`) maps `forward = sun_dir` and works in-game. Formula C (`heading = atan2(sun_dir.x, -sun_dir.y)`) maps `forward = -sun_dir` and works for a clean test sphere. Same engine, same simplepbr, opposite results. |
| **Winding-dependent lighting inversion** | The game's procedural planet sphere (built in `planet_factory.py`) has different triangle winding from a standard UV sphere. simplepbr's fragment shader behavior with `gl_FrontFacing` causes the effective normal to flip for back-wound geometry, inverting which hemisphere is lit. |
| **lookAt() / setPos() corruption** | `lookAt()` sets both position and rotation on a NodePath. For a DirectionalLight (infinitely distant), the position component is meaningless but contaminates the transform that the shader pipeline reads when simplepbr's FilterManager is active. |
| **_direction not updated by setHpr()** | `setHpr()` does not call `set_direction()`. The system works because the default `_direction = (0, 1, 0)` is rotated by `light_mat` derived from HPR. But any call to `set_direction()` with a non-identity vector breaks this implicit relationship. |

### 2.3 Resolution

The root cause turned out to be **planet mesh winding**, not an engine bug. The procedural sphere in `planet_factory.py` uses winding that produces inward-facing front-face normals (or equivalently, simplepbr flips normals via `gl_FrontFacing` for back-wound geometry). This inverts the effective lighting convention.

**Formula B is correct for the game's mesh geometry.** The algebraically-derived Formula C is correct for standard-wound meshes. The discrepancy is a mesh-level issue, not an engine defect.

The resolution was:

1. **Hard-code Formula B** in `sun_position_manager.py` -- the canonical formula for the game's planet mesh winding.
2. **Remove the formula toggle** (Shift+F9 debug cycling through four formulas).
3. **Document the safe API pattern**: use `setHpr()` only on DirectionalLight NodePaths. Never call `setPos()`, `setFluidPos()`, or `lookAt()`.
4. **Accept the winding discrepancy** as a known characteristic of the game's procedural sphere mesh.

### 2.4 Safe DirectionalLight API Pattern

The correct pattern for orienting a DirectionalLight under simplepbr:

```python
# sun_dir = unit vector from planet toward sun (direction photons travel FROM)
heading = math.degrees(math.atan2(-sun_dir.x, sun_dir.y))
horiz_len = math.sqrt(sun_dir.x ** 2 + sun_dir.y ** 2)
pitch = math.degrees(math.atan2(sun_dir.z, horiz_len))
sun_light_np.setHpr(heading, pitch, 0)
```

This derives from the Panda3D HPR-to-forward mapping:
```
forward = (-sin(H)*cos(P),  cos(H)*cos(P),  sin(P))
```
Solving for `forward = sun_dir` gives `H = atan2(-d.x, d.y)`, `P = atan2(d.z, sqrt(d.x^2 + d.y^2))`.

### 2.5 Proposed (Not Yet Implemented) Engine Fixes

These engine-level improvements were documented in the analysis but have not been implemented, because the game-side resolution (Formula B hard-code) was sufficient:

- **`set_direction_world(LVector3)`** -- A convenience method on DirectionalLight that takes a world-space travel direction and configures HPR automatically, eliminating manual atan2 in game code.
- **`xform()` override** -- Strip translation from the transform matrix in `DirectionalLight::xform()` to prevent `setPos()` / `lookAt()` corruption.
- **Debug assertion** -- Warn when a DirectionalLight has non-zero position, which has no rendering effect but may corrupt shadow maps.

These remain candidates for future Pax3D engine work if the lighting formula needs to be changed or generalized.

---

## 3. Phase 2: Bloom + HDR Tonemapping (Implemented)

### 3.1 Motivation

Pax Abyssi is a space simulation with extreme dynamic range. Scenes range from near-black interstellar space to blinding close-approach stars, with engine exhaust, weapon fire, and planet-scale illumination in between.

Without bloom, the game compensated with fragile per-effect magic numbers:

| Effect | Compensation | Purpose |
|--------|-------------|---------|
| Sun glow | 0.45x RGB reduction | Prevent oversaturation at close approach |
| Weapon bolts | 0.25x RGB reduction | Prevent flat white-out on bright projectiles |
| Corona billboard | 1.8x scale factor | Fake bloom halo around stars |

Without proper tonemapping, the HDR-to-display mapping was uncontrolled. simplepbr's stock Hejl-Dawson tonemap has no scene-adaptive control and no operator selection. The baked-in sRGB gamma in Hejl-Dawson also prevented clean compositing with other tonemap curves.

### 3.2 Architecture

The bloom system is implemented as a fork of simplepbr 0.13.1 into `pax3d_simplepbr/`, extending the post-processing chain with additional FilterManager passes.

**Stock simplepbr pipeline:**

```
Scene (PBR shader) --> RGBA16F buffer --> Tonemap (Hejl-Dawson) --> Window
```

**Pax3D pipeline with bloom enabled:**

```
Scene (PBR shader) --> RGBA16F buffer -+-> Bloom Extract (full res)
                                       |       |
                                       |       v
                                       |   Downsample x5 (1/2, 1/4, 1/8, 1/16, 1/32)
                                       |       |
                                       |       v
                                       |   Upsample x5 (tent filter + mip tints + accumulation)
                                       |       |
                                       v       v
                                   Tonemap + Composite (ACES/Reinhard/Uncharted2/Hejl-Dawson)
                                       |
                                       v
                                     Window
```

Total passes with bloom enabled: **1 scene render + 1 extract + 5 downsample + 5 upsample + 1 tonemap = 13 passes.** The 11 intermediate bloom passes (extract + downsample + upsample) are rendered via `FilterManager.render_quad_into()`, with downsample and upsample passes at progressively reduced resolution. The tonemap pass composites bloom additively before applying the tone curve.

Without bloom (`enable_bloom=False`), the pipeline collapses to the original 2-pass simplepbr flow: scene render to RGBA16F, then tonemap to window. The tonemap shader is still the modified version with selectable operators, but the `ENABLE_BLOOM` define is not set and the bloom sampling code is compiled out.

All intermediate textures use `F_rgba16` format with `T_float` component type (16-bit half-float per channel), matching the scene HDR buffer format.

### 3.3 New Shaders

Three new fragment shaders were added to `pax3d_simplepbr/shaders.py`. All use the existing `post.vert` vertex shader (a simple fullscreen quad passthrough).

#### 3.3.1 bloom_extract.frag -- Luminance Scaling with Firefly Clamp

Reads the HDR scene texture and scales pixel values into the bloom input. Uses a **no-threshold** approach: every pixel blooms proportionally to its brightness. This is physically correct -- dim objects produce negligible bloom, bright objects bloom strongly. No threshold popping or hard cutoffs.

```glsl
vec3 color = texture2D(scene_tex, v_texcoord).rgb;
color *= bloom_strength * 0.005;
color = clamp(color, vec3(0.0), vec3(25000.0));  // firefly clamp
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `scene_tex` | `sampler2D` | HDR scene render (RGBA16F) |
| `bloom_strength` | `float` | Extract multiplier. Controls how much scene luminance feeds into the bloom chain. Default: 1.0. Runtime-adjustable via uniform. |

The `0.005` scale factor normalizes bloom input so that `bloom_strength = 1.0` produces visually appropriate bloom for typical scene luminance values. The firefly clamp at 25000.0 prevents single extremely bright pixels (e.g., sun center at close approach) from dominating the entire bloom field after blurring.

#### 3.3.2 bloom_downsample.frag -- 13-Tap Kawase Dual-Filter

Implements the Jimenez 2014 (Call of Duty: Advanced Warfare) progressive downsample. Uses 5 overlapping 2x2 box sub-kernels arranged in a cross pattern, totaling 13 texture samples.

**Kernel layout:**

```
f . g . h          Positions relative to center 'a':
. b . c .          f,g,h,i,j,k,l,m = outer ring (2 texels offset)
g b a c j          b,c,d,e = inner ring (1 texel offset)
. d . e .          a = center
k . l . m
```

**Weights:**

| Samples | Weight per sample | Box total | Description |
|---------|------------------|-----------|-------------|
| `a` (center) | 0.125 | 0.125 | Center point |
| `b, c, d, e` (inner) | 0.125 each | 0.500 | Inner 2x2 box |
| `f, g, b, i` (top-left box) | 0.03125 each | 0.125 | Corner box |
| `g, h, c, j` (top-right box) | 0.03125 each | 0.125 | Corner box |
| `i, b, k, l` (bottom-left box) | 0.03125 each | 0.125 | Corner box |
| `c, j, l, m` (bottom-right box) | 0.03125 each | 0.125 | Corner box |
| **Total** | | **1.000** | Energy-preserving before compensation |

Note: samples `b`, `c`, `g`, `i`, `j`, `l` appear in multiple sub-kernels (shared edges/corners), which is the key insight of the Jimenez approach -- overlapping boxes provide better filtering quality with fewer unique sample positions.

After weighted summation, a **1.3x energy compensation** factor is applied to counteract the energy loss inherent in resolution halving:

```glsl
result *= 1.3;
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `src_tex` | `sampler2D` | Source texture from previous level (extract output or previous downsample) |
| `texel_size` | `vec2` | `(1.0 / src_width, 1.0 / src_height)` of the source texture being read |

#### 3.3.3 bloom_upsample.frag -- 9-Tap Tent Filter with Per-Mip Tinting

Upsamples the bloom chain back to full resolution using a 3x3 tent filter, with per-mip color tinting for artistic warm-cool bloom fringe.

**Tent filter weights:**

```
1  2  1       Weights: corners = 1, edges = 2, center = 4
2  4  2       Total = 16, normalize by dividing by 16
1  2  1
```

After filtering, the result is **tinted** by a per-mip color vector and **accumulated** additively with the result from the previous upsample level:

```glsl
s /= 16.0;
s *= mip_tint;
vec3 result = s + texture2D(bloom_accum_tex, uv).rgb;
```

This accumulation means each mip level contributes its own tinted glow, building up from the smallest (broadest blur) to the largest (finest detail). The tint colors create a subtle warm-to-cool spectral separation that gives the bloom a more natural, less digitally uniform character.

| Parameter | Type | Description |
|-----------|------|-------------|
| `src_tex` | `sampler2D` | Downsample chain texture at the current resolution level |
| `bloom_accum_tex` | `sampler2D` | Accumulated bloom from the previous (coarser) upsample level |
| `texel_size` | `vec2` | `(1.0 / src_width, 1.0 / src_height)` of `src_tex` |
| `mip_tint` | `vec3` | Per-mip RGB color tint (see Section 5.2) |

### 3.4 Modified Tonemap Shader

The stock simplepbr `tonemap.frag` was replaced with a new version that adds bloom compositing and selectable tonemap operators.

#### Bloom Compositing

When `ENABLE_BLOOM` is defined (compile-time), the shader samples the bloom result texture and adds it to the scene color **before** tonemapping. This is physically correct: bloom represents scattered light that should be tonemapped along with the scene, producing natural rolloff in highlights rather than the washed-out appearance of post-tonemap bloom addition.

```glsl
#ifdef ENABLE_BLOOM
    vec3 bloom = texture2D(bloom_tex, v_texcoord).rgb;
    color += bloom * bloom_intensity;
#endif
```

#### Tonemap Operators

Four tonemap operators are available, selectable at runtime via the `tonemap_operator` uniform integer:

| Index | Name | Description | sRGB Gamma |
|-------|------|-------------|------------|
| 0 | **ACES** (default) | Stephen Hill's fitted approximation of the Academy Color Encoding System filmic curve. Industry standard for games. Provides good highlight rolloff, moderate contrast, and saturated midtones. | Explicit `pow(1.0/2.2)` |
| 1 | **Reinhard** | Simple `x / (x + 1)` mapping. Preserves detail in highlights at the cost of lower contrast. Useful for debugging or scenes where highlight detail matters more than filmic look. | Explicit `pow(1.0/2.2)` |
| 2 | **Uncharted 2** | John Hable's piecewise filmic curve from Uncharted 2. Higher contrast than Reinhard, with configurable shoulder, toe, and linear white point (W=11.2). | Explicit `pow(1.0/2.2)` |
| 3 | **Hejl-Dawson** (legacy) | The original simplepbr default. Bakes sRGB gamma into the curve itself, so no additional gamma correction is needed. Retained for backward compatibility and comparison. | Baked in |

**ACES function (Stephen Hill fit):**
```glsl
vec3 aces_tonemap(vec3 x) {
    float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}
```

**Uncharted 2 function (Hable):**
```glsl
vec3 uncharted2_partial(vec3 x) {
    float A = 0.15;  // shoulder strength
    float B = 0.50;  // linear strength
    float C = 0.10;  // linear angle
    float D = 0.20;  // toe strength
    float E = 0.02;  // toe numerator
    float F = 0.30;  // toe denominator
    return ((x * (A * x + C * B) + D * E) / (x * (A * x + B) + D * F)) - E / F;
}

vec3 uncharted2_tonemap(vec3 x) {
    float W = 11.2;  // linear white point
    vec3 curr = uncharted2_partial(x * 2.0);
    vec3 white_scale = vec3(1.0) / uncharted2_partial(vec3(W));
    return curr * white_scale;
}
```

All operators except Hejl-Dawson output linear color and require an explicit `pow(color, vec3(1.0 / 2.2))` gamma correction step for sRGB display output.

### 3.5 Python API

The bloom and tonemapping system is controlled through the `Pipeline` dataclass in `pax3d_simplepbr/__init__.py`. All parameters are available at construction time and can be modified at runtime.

#### Construction Parameters

```python
import pax3d_simplepbr

pipeline = pax3d_simplepbr.Pipeline(
    # Bloom parameters (Pax3D additions)
    enable_bloom=True,          # Enable/disable the bloom chain
    bloom_strength=1.0,         # Extract multiplier (how much scene feeds bloom)
    bloom_intensity=1.0,        # Composite multiplier (overall bloom brightness)
    bloom_levels=5,             # Mip chain depth (clamped to 2-8)

    # Tonemapping (Pax3D addition)
    tonemap_operator='aces',    # 'aces', 'reinhard', 'uncharted2', 'hejl_dawson'

    # Existing simplepbr parameters (unchanged)
    msaa_samples=4,
    max_lights=8,
    enable_shadows=True,
    exposure=0.0,               # Power-of-2 exposure: shader receives 2^exposure
    # ... etc.
)
```

#### Runtime Parameter Updates

Parameters fall into two categories based on how they update:

**Uniform-only updates** (instant, no buffer rebuild):

| Parameter | Uniform | Effect |
|-----------|---------|--------|
| `bloom_strength` | `bloom_strength` on extract quad | Changes how much scene luminance feeds into bloom |
| `bloom_intensity` | `bloom_intensity` on tonemap quad | Changes overall bloom brightness in final composite |
| `tonemap_operator` | `tonemap_operator` on tonemap quad | Switches tonemap curve (integer index) |
| `exposure` | `exposure` on tonemap quad | Scales scene brightness (power-of-2) |

**Buffer rebuild** (destroys and recreates the full FilterManager chain):

| Parameter | Rebuild Scope | Effect |
|-----------|--------------|--------|
| `enable_bloom` | Full tonemap + bloom chain | Adds or removes all 11 bloom passes |
| `bloom_levels` | Full tonemap + bloom chain | Changes the depth of the downsample/upsample mip chain |
| `msaa_samples` | Full tonemap + bloom chain | Changes MSAA sample count on the scene render |
| `window` | Full tonemap + bloom chain | Retargets to a different graphics output |
| `camera_node` | Full tonemap + bloom chain | Retargets to a different camera |

The `__setattr__` override in `Pipeline` handles all of these automatically. Game code simply assigns to the property:

```python
pipeline.bloom_strength = 2.0      # Instant uniform update
pipeline.enable_bloom = False       # Triggers full rebuild
pipeline.tonemap_operator = 'reinhard'  # Instant uniform update
```

#### Tonemap Operator Mapping

The string-to-integer mapping used by the `tonemap_operator` parameter:

| String | Integer | Shader Constant |
|--------|---------|-----------------|
| `'aces'` | 0 | Default branch |
| `'reinhard'` | 1 | `if (tonemap_operator == 1)` |
| `'uncharted2'` | 2 | `if (tonemap_operator == 2)` |
| `'hejl_dawson'` | 3 | `if (tonemap_operator == 3)` |

Invalid operator names are caught at both construction time and runtime, logging a warning and falling back to `'aces'`.

### 3.6 Game Integration

The game (`C:\python\sfb2`) switches from stock simplepbr to pax3d_simplepbr with minimal changes:

1. **Import change:** `import pax3d_simplepbr as simplepbr` (or conditional import for dual-engine support)
2. **Init change:** `simplepbr.init(enable_bloom=True, bloom_strength=1.0, bloom_intensity=1.0, tonemap_operator='aces')`
3. **Remove magic numbers:** Delete the per-effect RGB reduction factors (0.45x sun, 0.25x weapons, 1.8x corona scale) that compensated for the lack of bloom
4. **Keep setShaderOff():** Additive-blended nodes (sun glow, weapon bolts, nebula billboards) still opt out of PBR shading. Bloom naturally captures their bright fragments from the HDR scene buffer.

### 3.7 File Listing

All files in `pax3d_simplepbr/` and their purpose:

| File | Size | Status | Purpose |
|------|------|--------|---------|
| `__init__.py` | 22 KB | **Modified** | Pipeline class. Bloom chain creation in `_setup_tonemapping()`, bloom parameter handling in `__setattr__`, tonemap operator validation and uniform mapping. |
| `shaders.py` | 25 KB | **Modified** | All embedded GLSL shaders. Added `bloom_extract.frag`, `bloom_downsample.frag`, `bloom_upsample.frag`. Replaced `tonemap.frag` with ACES + bloom composite + selectable operators. |
| `_shaderutils.py` | 3 KB | Unchanged | Shader compilation helper. Reads from the `shaders` dict, applies `#define` preprocessing, creates `p3d.Shader` objects. |
| `envmap.py` | 7 KB | Unchanged | Environment map loading and processing for IBL (image-based lighting). |
| `envpool.py` | 2 KB | Unchanged | Environment map pool/cache manager. |
| `hdr2env.py` | 1 KB | Unchanged | HDR-to-environment-map conversion utility. |
| `_ibl_funcs_cpu.py` | 10 KB | Unchanged | CPU-side IBL spherical harmonics computation. |
| `logging.py` | 500 B | Unchanged | Simple logging wrapper for simplepbr messages. |
| `textures.py` | 4.9 MB | Unchanged | Embedded texture data (BRDF LUT as serialized `.txo`). |
| `utils.py` | 4 KB | Unchanged | Utility functions (texture loading, PRC helpers). |
| `textures/` | (dir) | Unchanged | Directory containing `brdf_lut.txo` texture file. |

Files marked **Modified** contain Pax3D-specific changes. All other files are unmodified copies of simplepbr 0.13.1.

---

## 4. Remaining Roadmap

The following phases from the original rendering roadmap have not yet been started. They are additive quality improvements that build on the now-functional lighting and bloom foundation.

### Phase 3: Shader Infrastructure

| Task | Description | Effort |
|------|-------------|--------|
| Port tobspr PBR BRDF library | Cook-Torrance specular + Disney diffuse (354 lines GLSL) from RenderPipeline. Would replace simplepbr's built-in BRDF with more accurate energy-conserving functions. | Medium |
| Audit Cg shader dependencies | Identify remaining Cg-language shaders in the engine and plan migration to GLSL. | Low |
| Improve GLSL auto-shader generation | `shaderGenerator.cxx` generates shaders from render state attributes. Modernize its GLSL output. | Medium-High |
| Port tobspr color spaces library | sRGB, linear, ACEScg conversions. Useful for future HDR pipeline work. | Low |

### Phase 4: Atmospheric and Environmental

| Task | Description | Effort |
|------|-------------|--------|
| Atmospheric scattering | Bruneton or Hosek-Wilkie model for planets seen from space. Replaces the current custom additive Fresnel atmosphere shader. | High |
| Analytical height fog | Distance-based fog with exponential falloff, compatible with the PBR pipeline. | Medium |

### Phase 5: Large-Scale Rendering and Cleanup

| Task | Description | Effort |
|------|-------------|--------|
| Logarithmic depth buffer | `gl_FragDepth = log2(w) / log2(far)` for scenes spanning AU-scale distances. Eliminates Z-fighting without the current sky camera workaround. | High |
| Camera-relative rendering | Transform vertices relative to camera position (not world origin) to avoid floating-point precision loss at large distances. | High |
| Remove DirectX 9 backend | Delete `panda/src/dxgsg9/` (~604 KB) and `panda/metalibs/pandadx9/`. Dead weight -- focus on OpenGL 4.x+. | Low |

### Dependencies

```
Phase 1 (Lighting) -----> COMPLETE
Phase 2 (Bloom/HDR) ----> COMPLETE
Phase 3 (Shaders) ------> Phase 4 (Atmospheric) requires BRDF library
Phase 5 (Large-Scale) --> Independent, can proceed in parallel with Phase 3-4
```

---

## 5. Technical Reference

### 5.1 Key Constants

| Constant | Value | Location | Purpose |
|----------|-------|----------|---------|
| Bloom extract scale | `bloom_strength * 0.005` | `bloom_extract.frag` | Normalizes scene luminance into bloom-appropriate range |
| Firefly clamp | `25000.0` per channel | `bloom_extract.frag` | Prevents single bright pixels from dominating after blur |
| Downsample energy compensation | `1.3x` | `bloom_downsample.frag` | Counteracts energy loss from resolution halving |
| Tent filter normalization | `1/16` | `bloom_upsample.frag` | Sum of tent kernel weights: 4+2+2+2+2+1+1+1+1 = 16 |
| Default bloom levels | `5` | `Pipeline.__init__` | Produces mip chain: full, 1/2, 1/4, 1/8, 1/16, 1/32 |
| Bloom levels range | `[2, 8]` | `Pipeline.__init__` | Clamped at construction and on rebuild |
| HDR buffer format | `RGBA16F` (F_rgba16 / T_float) | `_setup_tonemapping()` | 16-bit half-float, sufficient for HDR bloom chain |
| Depth buffer | 24-bit | `_setup_tonemapping()` | Scene render depth buffer precision |
| Default MSAA | 4x | `Pipeline.msaa_samples` | Applied to the scene render buffer |
| Default exposure | `0.0` (shader receives `2^0 = 1.0`) | `Pipeline.exposure` | Power-of-2 exposure control |
| ACES coefficients | a=2.51, b=0.03, c=2.43, d=0.59, e=0.14 | `tonemap.frag` | Stephen Hill's fitted ACES approximation |
| Uncharted 2 white point | W=11.2 | `tonemap.frag` | Hable's linear white point |
| sRGB gamma | `pow(1.0/2.2)` | `tonemap.frag` | Applied after ACES, Reinhard, and Uncharted2 (not Hejl-Dawson) |

### 5.2 Per-Mip Bloom Tint Values

These tints are applied during the upsample chain. Each mip level (from finest/smallest blur to coarsest/largest blur) gets a distinct color that blends into the accumulated bloom result. The tints create a subtle spectral fringe -- warm inner glow, cool outer halo -- that gives bloom a more natural appearance than uniform white blurring.

| Mip Level | Index | RGB Tint | Visual Character |
|-----------|-------|----------|-----------------|
| 0 (finest detail) | 0 | `(0.214, 0.429, 0.497)` | Cool blue-green. Fine detail bloom has a cool tone. |
| 1 | 1 | `(0.964, 0.947, 0.991)` | Near-white with slight cool bias. The bulk of visible bloom. |
| 2 | 2 | `(0.982, 0.542, 0.542)` | Warm red-orange. Mid-range glow has warmth. |
| 3 | 3 | `(0.301, 0.493, 1.000)` | Strong blue. Creates a blue halo at medium spread. |
| 4 (coarsest) | 4 | `(0.456, 0.209, 0.167)` | Deep warm brown-red. The widest bloom spread has a warm tone. |

When `bloom_levels > 5`, the tints cycle modulo 5 (`_MIP_TINTS[i % len(_MIP_TINTS)]`).

The tints are defined in `pax3d_simplepbr/__init__.py` as the `_MIP_TINTS` module-level constant:

```python
_MIP_TINTS = [
    p3d.LVecBase3(0.214, 0.429, 0.497),  # fine detail, cool
    p3d.LVecBase3(0.964, 0.947, 0.991),  # near-white
    p3d.LVecBase3(0.982, 0.542, 0.542),  # warm
    p3d.LVecBase3(0.301, 0.493, 1.000),  # blue halo
    p3d.LVecBase3(0.456, 0.209, 0.167),  # deep warm outer
]
```

### 5.3 Downsample Kernel Weight Derivation

The 13-tap Jimenez kernel decomposes the sampling area into 5 overlapping 2x2 boxes:

```
Box 0 (center):   b, c, d, e  (inner ring, 1 texel offset)        weight: 0.500
Box 1 (top-left): f, g, b, i  (top-left 2x2 of outer ring)       weight: 0.125
Box 2 (top-right): g, h, c, j  (top-right 2x2)                   weight: 0.125
Box 3 (bottom-left): i, b, k, l  (bottom-left 2x2)               weight: 0.125
Box 4 (bottom-right): c, j, l, m  (bottom-right 2x2)             weight: 0.125
```

Center sample `a` is weighted at 0.125 (half of a center box share). Each inner sample (b,c,d,e) receives 0.125 from the center box. Each outer sample in a corner box receives 0.03125 (= 0.125 / 4). Samples shared between boxes (b, c, g, i, j, l) accumulate weights from all boxes they belong to.

Total weight before energy compensation: 1.0. After 1.3x compensation: 1.3.

### 5.4 Upsample Tent Kernel Derivation

The 9-tap tent (bilinear hat function) weights are:

```
1/16  2/16  1/16
2/16  4/16  2/16
1/16  2/16  1/16
```

This is the outer product of a 1D tent `[1, 2, 1]` with itself, normalized by the total weight 16. It provides smooth bilinear interpolation during upsampling, avoiding the blocky artifacts of nearest-neighbor or box-filter upsampling.

### 5.5 Bloom Pipeline Buffer Sizes

For a default 5-level bloom chain at 1920x1080 window resolution:

| Pass | Buffer Name | Resolution | Div | Format |
|------|------------|------------|-----|--------|
| Scene render | `scene_hdr` | 1920 x 1080 | 1 | RGBA16F + D24 + MSAA4x |
| Bloom extract | `bloom_extract` | 1920 x 1080 | 1 | RGBA16F |
| Downsample 0 | `bloom_down_0` | 960 x 540 | 2 | RGBA16F |
| Downsample 1 | `bloom_down_1` | 480 x 270 | 4 | RGBA16F |
| Downsample 2 | `bloom_down_2` | 240 x 135 | 8 | RGBA16F |
| Downsample 3 | `bloom_down_3` | 120 x 67 | 16 | RGBA16F |
| Downsample 4 | `bloom_down_4` | 60 x 33 | 32 | RGBA16F |
| Upsample 0 | `bloom_up_0` | 120 x 67 | 16 | RGBA16F |
| Upsample 1 | `bloom_up_1` | 240 x 135 | 8 | RGBA16F |
| Upsample 2 | `bloom_up_2` | 480 x 270 | 4 | RGBA16F |
| Upsample 3 | `bloom_up_3` | 960 x 540 | 2 | RGBA16F |
| Upsample 4 | `bloom_up_4` | 1920 x 1080 | 1 | RGBA16F |
| Tonemap composite | (postquad) | 1920 x 1080 | 1 | Window framebuffer |

Total additional VRAM for bloom (approximate, at 1920x1080, 8 bytes/pixel for RGBA16F):

- Full-res textures (extract + up_4): 2 x 1920 x 1080 x 8 = ~33 MB
- Half-res textures (down_0 + up_3): 2 x 960 x 540 x 8 = ~8.3 MB
- Quarter and smaller: diminishing, ~4 MB total
- **Total bloom VRAM overhead: approximately 45 MB at 1080p**

### 5.6 Shader Compatibility

All shaders target GLSL version 120 for maximum compatibility, with `#ifdef USE_330` blocks for OpenGL 3.3+ paths. The USE_330 define switches between:

| Feature | GLSL 120 | GLSL 330+ |
|---------|----------|-----------|
| Texture sampling | `texture2D()` | `texture()` |
| Fragment output | `gl_FragColor` | `out vec4 o_color` |
| 3D texture sampling | `texture3D()` | `texture()` |

The `IS_WEBGL` define is carried forward from simplepbr for WebGL compatibility but is not tested or relevant for Pax Abyssi.

---

## Appendix A: Upstream Relationship

| Property | Value |
|----------|-------|
| Upstream | `panda3d/panda3d` (GitHub) |
| Fork | `Apocrypha-Stellarum/Pax3D` (GitHub) |
| Last upstream sync | Feb 26, 2026 (commit `2d2bdc9a`) |
| Upstream version | 1.11.0-dev |
| simplepbr fork base | simplepbr 0.13.1 (Moguri) |

The `pax3d_simplepbr/` directory is a first-party module in the Pax3D repository. It is NOT installed from PyPI. The game imports it directly when running under the Pax3D venv. The original `simplepbr` pip package remains available for the stock Panda3D environment.

## Appendix B: Key Source File Locations

| File | Purpose |
|------|---------|
| `C:\python\pax3d\pax3d_simplepbr\__init__.py` | Pipeline class -- bloom chain, tonemap setup, all parameter handling |
| `C:\python\pax3d\pax3d_simplepbr\shaders.py` | All GLSL shaders (3 new bloom + modified tonemap + unchanged PBR/shadow/post) |
| `C:\python\pax3d\pax3d_simplepbr\_shaderutils.py` | Shader compilation with `#define` preprocessing |
| `C:\python\pax3d\CLAUDE.md` | Project context and build instructions |
| `C:\python\pax3d\documents\DIRECTIONAL_LIGHTING_PLAN.md` | Original deep analysis of the directional lighting problem (Phase 1) |
| `C:\python\pax3d\documents\RENDERING_ROADMAP.md` | Full 5-phase rendering roadmap |
| `C:\python\pax3d\documents\TOBSPR_SHADER_CATALOGUE.md` | Catalogue of salvageable shaders from tobspr's RenderPipeline |
| `C:\python\pax3d\documents\BUILDING_PAX3D.md` | Build instructions for the engine |
| `C:\python\pax3d\documents\SWITCHING_ENGINES.md` | Guide for switching between stock Panda3D and Pax3D venvs |
| `C:\python\pax3d\panda\src\pgraphnodes\directionalLight.h` | Engine DirectionalLight class (not modified) |
| `C:\python\pax3d\panda\src\display\graphicsStateGuardian.cxx` | Engine light binding to GLSL (not modified) |
