# tobspr RenderPipeline — Shader Extraction Catalogue

**For Pax3D (Panda3D space simulation engine fork)**
**Source:** https://github.com/tobspr/RenderPipeline (abandoned ~2020, final commit Jan 2021)
**Purpose:** Identify, document, and grade every shader worth salvaging for a space simulation renderer.

---

## Quick-Reference Summary Table

| # | Shader | Tier | Lines | Extract Difficulty | Space Sim Value |
|---|--------|------|-------|--------------------|-----------------|
| 1 | Bloom (Kawase dual-filter) | 1 | ~270 | Low | Essential — star glare, engine glow |
| 2 | Tonemapping + HDR (6 operators) | 1 | ~150 | Very Low | Essential — HDR space luminance |
| 3 | PBR BRDF Library | 1 | ~354 | Low | Essential — physically correct ship/hull lighting |
| 4 | Color Spaces Library | 1 | ~200 | Very Low | Core dependency for all above |
| 5 | Directional Sun Lighting (PSSM) | 1 | ~350 | Medium | High — star-as-directional-light |
| 6 | Atmospheric Scattering — Hosek-Wilkie | 2 | ~100 | Medium | High — planet atmosphere skydomes |
| 7 | Atmospheric Scattering — Bruneton | 2 | ~700 | High | High — physically accurate atmosphere LUTs |
| 8 | Screen-Space Reflections | 2 | ~350 | Medium | Medium — cockpit glass, metallic hull panels |
| 9 | SMAA Anti-aliasing | 2 | ~52KB | Very Low | High — clean geometry edges in space |
| 10 | FXAA 3.11 | 2 | ~51KB | Very Low | Medium — lightweight fallback AA |
| 11 | Color Correction + Post-FX | 3 | ~200 | Low | Medium — film grain, chromatic aberration |
| 12 | Volumetric Fog | 3 | ~80 | Very Low | Medium — nebula density fog |
| 13 | Motion Blur | 3 | ~250 | Medium | Low-Medium — fast ship maneuvers |
| 14 | Normal Packing | 3 | ~20 | Very Low | Low — G-buffer utility |
| 15 | Importance Sampling | 3 | ~80 | Very Low | Core dependency for SSR/PBR |

**Skip entirely:** VXGI, DOF (WIP/broken), volumetric clouds, skin SSS, Sky AO, most AO variants.

---

## Extraction Procedure (Universal — Apply to Every Shader)

Before reading individual entries, understand the mechanical steps to port any tobspr shader:

### Step 1 — Remove Base Include
```glsl
// REMOVE this line:
#pragma include "render_pipeline_base.inc.glsl"

// REPLACE with explicit uniform declarations as needed, e.g.:
uniform sampler2D SomeTexture;
uniform vec2 screen_size;
```

### Step 2 — Flatten MainSceneData References
```glsl
// tobspr pattern:
float near = MainSceneData.camera_near;
vec3 ws_pos = MainSceneData.camera_pos;

// Pax3D replacement:
uniform float camera_near;
uniform vec3 camera_pos;
```

### Step 3 — Inline GET_SETTING
```glsl
// tobspr pattern:
float strength = GET_SETTING(bloom, bloom_strength);

// Pax3D replacement (choose one):
uniform float bloom_strength;         // dynamic at runtime
// OR:
#define bloom_strength 1.0            // baked constant
```

### Step 4 — Resolve HAVE_PLUGIN Guards
```glsl
// tobspr pattern:
#if HAVE_PLUGIN(pssm)
    shadow_factor = sample_shadow(...);
#endif

// Pax3D replacement:
#define HAVE_PLUGIN_pssm 1    // enable
// OR:
#define HAVE_PLUGIN_pssm 0    // disable
```

### Step 5 — Replace get_texcoord()
```glsl
// tobspr pattern:
vec2 tc = get_texcoord();

// Pax3D replacement:
vec2 tc = gl_FragCoord.xy / screen_size;
// OR with explicit uniforms:
vec2 tc = gl_FragCoord.xy / vec2(float(screen_width), float(screen_height));
```

### Step 6 — Add Missing Utility Macros
```glsl
// Add at top of any ported shader that uses these:
#define saturate(v)     clamp((v), 0.0, 1.0)
#define square(v)       ((v) * (v))
#define lerp(a,b,t)     mix((a), (b), (t))
```

### Step 7 — Strip Driver Hints
```glsl
// REMOVE all lines like:
#pragma optionNV(unroll all)
#pragma optionNV(fastmath on)
// These are Nvidia-specific and ignored by Mesa/AMD; they may cause errors.
```

### Step 8 — Unroll Sequence Macros (AO shaders only)
```glsl
// tobspr pattern (AO):
START_ITERATE_SEQUENCE(ao, poisson_disk, sample_offset)
    vec2 offset = sample_offset;
    // ... use offset
END_ITERATE_SEQUENCE()

// Pax3D replacement:
const vec2 poisson_disk[16] = vec2[](
    vec2(-0.94201624, -0.39906216),
    // ... fill in the actual sample array
);
for (int i = 0; i < 16; i++) {
    vec2 offset = poisson_disk[i];
    // ... use offset
}
```

---

## Tier 1 — Priority Extractions (Space Sim Essential)

These four shaders form the non-negotiable rendering foundation for a convincing space simulation. Without them, HDR star fields, engine glows, and physically correct metal/glass surfaces cannot work.

---

### 1. Bloom — Kawase Dual-Filter

**Purpose:** Physically-based bloom that responds to scene luminance rather than a hard threshold. Essential for star glare, engine exhaust glow, and thruster plumes at high energy levels.

**Source files:**

| File | Approx Lines | Role |
|------|--------------|------|
| `rpplugins/bloom/shader/extract_bright_spots.frag.glsl` | ~40 | Downsample + luminance scale |
| `rpplugins/bloom/shader/bloom_downsample.frag.glsl` | ~90 | 13-tap Kawase downsample to mip chain |
| `rpplugins/bloom/shader/bloom_upsample.frag.glsl` | ~60 | 9-tap tent upsample with tinting |
| `rpplugins/bloom/shader/apply_bloom.frag.glsl` | ~50 | Final composite into HDR scene |
| `rpplugins/bloom/shader/bloom_common.inc.glsl` | ~30 | Shared tap weight constants |

**Total GLSL lines:** ~270

**Technical Implementation:**

The algorithm is a dual Kawase filter based on Siggraph 2015 "Bandwidth-Efficient Rendering" (ARM/Marius Bjorge). It builds a mip pyramid by alternating asymmetric sample kernels on downsample and upsample passes, achieving a much wider blur radius than a single Gaussian pass of equivalent cost.

_Extract pass_ (`extract_bright_spots.frag.glsl`):
- Reads linear HDR scene color
- Multiplies by `bloom_strength * 0.005` — no hard luminance threshold (physically correct; stars and hot metal contribute continuously)
- Clamps at 25000 to prevent NaN propagation from saturation artifacts
- Optional firefly removal via local neighborhood median comparison

_Downsample pass_ (`bloom_downsample.frag.glsl`):
- 13-tap Kawase filter decomposed into 5 overlapping 2x2 bilinear sub-kernels
- Writes results into successive mip levels via `imageStore()` — requires OpenGL 4.2+ image load/store
- Applies 1.3x amplification factor per level to compensate for energy loss
- Sample offsets are half-pixel-aligned to maximize bilinear hardware utilization

_Upsample pass_ (`bloom_upsample.frag.glsl`):
- 9-tap tent filter (3x3 with center weight 4, edge weight 2, corner weight 1)
- Per-mip tinting with hardcoded color vectors (`vec3(1.0, 0.95, 0.85)` etc.) to produce a natural warm-cool bloom fringe
- Adds current mip to the accumulated result from finer mips

_Apply pass_ (`apply_bloom.frag.glsl`):
- Blends accumulated bloom mip-0 into HDR scene color: `scene + bloom * strength`
- Optional lens dirt texture modulates bloom shape (for sensor smear effects)

**Pipeline Stages:**

```
Scene HDR Buffer
     |
     v
[Extract] -- bright spots mip-0
     |
     v
[Downsample x N] -- builds mip 1..N
     |
     v
[Upsample x N] -- collapses back to mip-0 (accumulated)
     |
     v
[Apply] -- adds to HDR scene
     |
     v
Tonemapper input
```

**Inputs Required:**

| Uniform | Type | Description |
|---------|------|-------------|
| `scene_color` | `sampler2D` | Linear HDR scene color |
| `bloom_tex` | `image2D[]` | Mip chain (image2D array, OpenGL 4.2+) |
| `bloom_strength` | `float` | Overall intensity multiplier |
| `num_mipmaps` | `int` | Mip chain depth (2–10, default 8) |
| `remove_fireflies` | `int` | 0/1 flag |
| `lens_dirt_factor` | `float` | Optional dirt texture strength |
| `lens_dirt_tex` | `sampler2D` | Optional lens dirt mask |
| `screen_size` | `vec2` | Pixel dimensions for texcoord computation |

**Outputs Produced:**

- Mip chain image stores during downsample/upsample (intermediate)
- Final: additive contribution written into HDR scene color buffer

**RP-Specific Dependencies:**

| Dependency | Where Used | Replacement |
|------------|------------|-------------|
| `render_pipeline_base.inc.glsl` | All files | Remove; add `uniform vec2 screen_size;` |
| `get_texcoord()` | All files | `gl_FragCoord.xy / screen_size` |
| `GET_SETTING(bloom, ...)` | All files | `uniform float bloom_strength;` etc. |
| `color_spaces.inc.glsl` | Extract | Port alongside (Tier 1, item 4) |
| `get_luminance()` | Extract, firefly check | Inline: `dot(color.rgb, vec3(0.2126, 0.7152, 0.0722))` |
| `imageStore()` | Downsample | Requires Pax3D to expose GL 4.2 image units — verify context |

**Extraction Difficulty:** Low

The logic is self-contained and algorithmic. The main work is replacing macros (15–20 substitutions across 5 files) and ensuring the Panda3D shader program can bind image2D arrays for the mip chain. If image2D bindings are inconvenient, the mip chain can be replaced with explicit render-to-texture passes using framebuffer attachments (slightly less efficient but fully equivalent).

**Space Sim Relevance:**

Critical. Space contains extreme dynamic range: stars range from faint pinpoints to blinding nearfield suns, engines pulse through visible spectrum into UV. Threshold-based bloom (old approach) produces ugly halos that pop in and out. The tobspr physically-based approach scales continuously — a dim star barely blooms, Sol at close range saturates the sensor realistically.

**Integration Target:** Pax3D post-process pipeline, runs after main scene render, before tonemapping.

---

### 2. Tonemapping + HDR Exposure

**Purpose:** Map linear HDR floating-point scene color to display-range [0,1] with physically motivated exposure control. Six selectable operators plus Frostbite's EV100 model.

**Source file:** `rpcore/shader/includes/tonemapping.inc.glsl`

**Total GLSL lines:** ~150

**Technical Implementation:**

This is a pure include library — no full-screen pass logic, just functions. It provides six tone mapping operators and a complete Frostbite EV100 exposure pipeline.

_Tonemap operators:_

```glsl
// 1. Linear (raw HDR, just exposure)
vec3 tonemap_none(vec3 color, float exposure) {
    return color * exposure;
}

// 2. Haarm-Peter Duiker (fast filmic, no white point)
vec3 tonemap_optimized(vec3 color, float exposure) { ... }

// 3. Reinhard — 4 variants:
//    a. Simple:  c / (c + 1)
//    b. Luminance-based reinhard
//    c. Extended reinhard with white point
//    d. Luminance extended
vec3 tonemap_reinhard(vec3 color, float exposure) { ... }

// 4. Uncharted 2 / Hable — full 6-parameter filmic curve
//    Parameters: A=shoulder, B=linear_strength, C=linear_angle,
//                D=toe_strength, E=toe_numerator, F=toe_denominator
vec3 tonemap_uncharted2(vec3 color, float exposure) { ... }

// 5. Exponential:  1 - exp(-color * exposure)
// 6. Exponential squared:  1 - exp(-color^2 * exposure)
```

_Frostbite EV100 exposure model:_

```glsl
// Compute EV100 from camera parameters:
float computeEV100(float aperture, float shutterTime, float ISO) {
    return log2(square(aperture) / shutterTime * 100.0 / ISO);
}

// Compute EV100 from average scene luminance:
float computeEV100FromAvgLuminance(float avgLuminance) {
    return log2(avgLuminance * 100.0 / 12.5);
}

// Convert EV100 to linear exposure multiplier:
float convertEV100ToExposure(float EV100) {
    float maxLuminance = 1.2 * pow(2.0, EV100);
    return 1.0 / maxLuminance;
}
```

**Inputs Required:**

| Uniform | Type | Description |
|---------|------|-------------|
| `scene_color` | `vec3` | Linear HDR color (inline, not a sampler) |
| `current_exposure` | `float` | EV100-derived multiplier, typically driven by auto-exposure |
| `tonemap_operator` | `int` | Selector 0–5 |
| `tonemap_*` | `float` | Per-operator tuning params (optional) |

**Outputs Produced:** `vec3` display-range color, passed to LUT color grading or written directly to swapchain.

**RP-Specific Dependencies:**

| Dependency | Replacement |
|------------|-------------|
| `saturate()` macro | `#define saturate(v) clamp(v, 0.0, 1.0)` |
| `square()` macro | `#define square(v) ((v)*(v))` |
| No other dependencies | — |

**Extraction Difficulty:** Very Low

Zero structural RP coupling. Copy the file, add two macro defines, done. The EV100 model is self-contained math.

**Space Sim Relevance:**

Essential. The dynamic range of a space scene spans 10+ stops — from deep space background (near-zero) to the facing surface of a nearby star (extreme). Reinhard and Uncharted 2 both have distinct character for this range; Uncharted 2 is typically better for preserving color saturation in bright highlights. EV100 auto-exposure is needed for seamless transitions from open space to planetary shadow to station interiors.

**Integration Target:** Engine-level post-process, called at the end of every frame's final composite pass.

---

### 3. PBR BRDF Library

**Purpose:** Complete physically-based rendering BRDF implementation covering Cook-Torrance specular (GGX/Schlick/Smith), Lambert and Disney Burley diffuse, and a ready-made `apply_light()` assembly function.

**Source file:** `rpcore/shader/includes/brdf.inc.glsl`

**Total GLSL lines:** 354

**Technical Implementation:**

The file is organized as a layered include library. Each component function is individually switchable via commented-out alternatives, making it easy to swap algorithms without restructuring calling code.

_Specular Distribution (NDF):_
```glsl
// Active: Trowbridge-Reitz GGX (Walter et al. 2007)
float distribution_ggx(float NdotH, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float denom = NdotH * NdotH * (a2 - 1.0) + 1.0;
    return a2 / (M_PI * denom * denom);
}

// Available (commented): Blinn-Phong, Beckmann
```

_Geometric Shadowing:_
```glsl
// Active: Implicit (NdotV * NdotL) — fast, no artifact at grazing
float geometric_implicit(float NdotV, float NdotL) {
    return NdotV * NdotL;
}

// Available (commented): Smith-GGX, Schlick-GGX, Schlick-Beckmann
// (Smith-GGX is more accurate but 4x more expensive; use for cinematic passes)
```

_Fresnel:_
```glsl
// Active: Schlick with Epic's approximation (Karis 2013)
vec3 fresnel_schlick(float HdotV, vec3 F0) {
    return F0 + (1.0 - F0) * pow(1.0 - HdotV, 5.0);
    // Epic fast variant: replaces pow() with Exp2 trick for performance
}
```

_Diffuse:_
```glsl
// Lambert:
vec3 diffuse_lambert(vec3 diffuse_color) {
    return diffuse_color / M_PI;
}

// Disney Burley (physically plausible, retroreflection at grazing):
vec3 diffuse_burley(vec3 diffuse_color, float roughness,
                    float NdotV, float NdotL, float HdotV) {
    float FD90 = 0.5 + 2.0 * HdotV * HdotV * roughness;
    float FdV = 1.0 + (FD90 - 1.0) * pow(1.0 - NdotV, 5.0);
    float FdL = 1.0 + (FD90 - 1.0) * pow(1.0 - NdotL, 5.0);
    return diffuse_color * (1.0 / M_PI) * FdV * FdL;
}
```

_Assembly function:_
```glsl
// apply_light() — ~60 lines, takes all BRDF inputs, returns radiance contribution
vec3 apply_light(MaterialData m, vec3 N, vec3 V, vec3 L,
                 vec3 light_color, float attenuation) {
    vec3 H = normalize(V + L);
    float NdotV = max(dot(N, V), 1e-4);
    float NdotL = max(dot(N, L), 0.0);
    float NdotH = max(dot(N, H), 0.0);
    float HdotV = max(dot(H, V), 0.0);

    vec3 F0 = mix(vec3(0.04), m.base_color, m.metallic);
    float D = distribution_ggx(NdotH, m.roughness);
    float G = geometric_implicit(NdotV, NdotL);
    vec3  F = fresnel_schlick(HdotV, F0);

    vec3 kS = F;
    vec3 kD = (1.0 - kS) * (1.0 - m.metallic);
    vec3 specular = (D * G * F) / (4.0 * NdotV * NdotL + 1e-4);
    vec3 diffuse = kD * diffuse_burley(m.base_color, m.roughness, NdotV, NdotL, HdotV);

    return (diffuse + specular) * light_color * attenuation * NdotL;
}
```

**Inputs Required:** Inline math only — no texture samplers. Caller provides `MaterialData` struct (base_color, metallic, roughness, normal) plus per-light vectors.

**Outputs Produced:** `vec3` radiance per light call, accumulated by the caller.

**RP-Specific Dependencies:**

| Dependency | Replacement |
|------------|-------------|
| `saturate()`, `square()` | Add macros |
| `M_PI` | `#define M_PI 3.14159265358979` |
| `MaterialData` struct | Port struct definition or adapt to Pax3D's material layout |
| No other RP coupling | — |

**Extraction Difficulty:** Low

Pure math, no texture bindings, no RP infrastructure. The only work is adapting `MaterialData` struct field names to Pax3D's material representation and deciding which geometric shadowing term to enable. Burley diffuse and GGX specular are considered industry standard (used by Frostbite, UE4, Unity HDRP).

**Space Sim Relevance:**

Essential. Ship hulls, station panels, and cockpit glass are predominantly metallic and dielectric surfaces. Without GGX specular, metal looks plasticky. Without Disney diffuse, matte surfaces lose their edge-darkening at grazing angles that gives geometric depth cues in space where ambient occlusion is weak.

**Integration Target:** Engine-level material library, included by all surface shaders.

---

### 4. Color Spaces Library

**Purpose:** Comprehensive color space conversion library. Foundation dependency for bloom (luminance), tonemapping (exposure), and scattering (sky color). Zero RP coupling.

**Source file:** `rpcore/shader/includes/color_spaces.inc.glsl`

**Total GLSL lines:** ~200

**Technical Implementation:**

Provides conversion matrices and functions for the following color spaces:

| Conversion | Function |
|------------|----------|
| Linear RGB → XYZ (D65) | `rgb_to_xyz(vec3)` |
| XYZ → Linear RGB | `xyz_to_rgb(vec3)` |
| XYZ → xyY | `xyz_to_xyY(vec3)` |
| xyY → XYZ | `xyY_to_xyz(vec3)` |
| Linear RGB → sRGB | `linear_to_srgb(vec3)` |
| sRGB → Linear RGB | `srgb_to_linear(vec3)` |
| Linear RGB → HSL | `rgb_to_hsl(vec3)` |
| HSL → Linear RGB | `hsl_to_rgb(vec3)` |
| Luminance (photometric) | `get_luminance(vec3)` → `dot(c, vec3(0.2126, 0.7152, 0.0722))` |
| Perceived lightness (CIE L*) | `get_perceived_brightness(vec3)` |

The sRGB piecewise gamma is correctly implemented (linear region + gamma region at the 0.0031308 threshold), not the common approximate `pow(x, 1/2.2)`.

**Inputs Required:** Inline math only.

**RP-Specific Dependencies:** None. Only `saturate()` macro needed.

**Extraction Difficulty:** Very Low

Copy file, add `#define saturate(v) clamp(v, 0.0, 1.0)`. Done.

**Space Sim Relevance:**

Core dependency. Every other shader in Tier 1 depends on this. Additionally, star color rendering (blackbody temperature to linear RGB) benefits from accurate XYZ conversions. Planet atmosphere color grading requires HSL operations.

**Integration Target:** Engine-level include, available to all shaders via `#include`.

---

### 5. Directional Sun Lighting — PSSM Shadows

**Purpose:** Physically-based sun shading using Frostbite "representative point" area light model (to simulate the sun's 0.54-degree angular diameter) plus Parallel Split Shadow Maps (PSSM) with PCF and Exponential Shadow Maps (ESM) filtering.

**Source files:**

| File | Approx Lines | Role |
|------|--------------|------|
| `rpplugins/pssm/shader/apply_sun_shading.frag.glsl` | ~85 | Sun BRDF with representative point |
| `rpplugins/pssm/shader/filter_pssm.inc.glsl` | ~120 | PCF + ESM shadow filter, slope bias |
| `rpplugins/pssm/shader/convert_to_esm.frag.glsl` | ~40 | Builds ESM depth buffer |
| `rpplugins/pssm/shader/blur_esm.frag.glsl` | ~50 | Gaussian blur for ESM anti-aliasing |
| `rpplugins/pssm/shader/pssm_common.inc.glsl` | ~55 | Split frustum math, cascade selection |

**Total GLSL lines:** ~350

**Technical Implementation:**

_Representative point sun (`apply_sun_shading.frag.glsl`):_

Based on Frostbite PBR paper (Lagarde & de Rousiers, Siggraph 2014). The sun is not treated as an infinitely distant point light but as a visible disk with angular radius 0.54 degrees. This shifts the specular highlight from a mathematical point to a physically correct disk of finite solid angle.

```glsl
// Representative point for sun disk (Frostbite 2014):
float sun_angular_radius = 0.00942;  // 0.54 degrees in radians
vec3 D = sun_direction;              // Normalized sun vector
vec3 r = reflect(-view_dir, normal); // Mirror reflection direction
vec3 L = D;
float DdotR = dot(D, r);
// Clamp ray to cone of sun disk:
L = DdotR < cos(sun_angular_radius)
    ? normalize(r - normalize(r - DdotR * D) * sin(sun_angular_radius))
    : r;
// L is now the representative point direction
```

Also includes optional foliage backscatter (irrelevant for space sim — skip via `#define FOLIAGE_ENABLED 0`).

_PSSM cascade selection (`pssm_common.inc.glsl`):_

Splits the view frustum into N cascades (tobspr default 5) at logarithmic distances. Each cascade has its own orthographic shadow map. Fragment selects cascade by comparing view-space depth to split distances.

_Shadow filtering (`filter_pssm.inc.glsl`):_

Uses ESM (Exponential Shadow Maps) with PCF fallback. ESM encodes depth as `exp(c * depth)` which allows hardware bilinear filtering to produce soft penumbrae. Slope-scaled bias (per-cascade) prevents shadow acne on angled surfaces. Each cascade adds a small bias increment to account for increasing texel size at distance.

```glsl
// ESM comparison (avoids PCF sampling overhead):
float esm_compare(sampler2D esm_map, vec2 uv, float receiver_depth, float c) {
    float occluder = texture(esm_map, uv).r;
    return saturate(occluder * exp(-c * receiver_depth));
}
```

**Pipeline Stages:**

```
Per-frame shadow pass:
  [Depth render to PSSM cascades] (N cascade shadow cameras)
  [convert_to_esm]: depth -> exp(c * depth) for each cascade
  [blur_esm]: 2-pass Gaussian blur on ESM maps

Lighting pass:
  [filter_pssm]: sample shadow + ESM, select cascade, compute shadow factor
  [apply_sun_shading]: representative-point BRDF + shadow factor -> sun radiance
```

**Inputs Required:**

| Uniform | Type | Description |
|---------|------|-------------|
| `pssm_shadow_maps` | `sampler2DArray` | Depth maps for all N cascades |
| `pssm_esm_maps` | `sampler2DArray` | ESM filtered maps |
| `pssm_mvps` | `mat4[N]` | Shadow VP matrices per cascade |
| `pssm_splits` | `float[N]` | View-space split distances |
| `sun_direction` | `vec3` | Normalized world-space sun direction |
| `sun_color` | `vec3` | Linear HDR sun color |
| `sun_angular_radius` | `float` | 0.00942 (0.54 degrees) |
| `pssm_esm_factor` | `float` | ESM exponent c (typically 80–200) |
| `pssm_slope_bias` | `float` | Slope-scaled depth bias |

**Outputs Produced:** Per-fragment `vec3` sun radiance contribution, accumulated with other lights.

**RP-Specific Dependencies:**

| Dependency | Where Used | Replacement |
|------------|------------|-------------|
| `render_pipeline_base.inc.glsl` | All | Remove |
| `brdf.inc.glsl` | apply_sun_shading | Port alongside (Tier 1, item 3) |
| `GET_SETTING(pssm, ...)` | All | Uniforms or defines |
| `HAVE_PLUGIN(pssm)` | apply_sun_shading | `#define HAVE_PLUGIN_pssm 1` |
| Foliage backscatter block | apply_sun_shading | Remove or `#define FOLIAGE_ENABLED 0` |
| `GBuffer` sampling | apply_sun_shading | Replace with Pax3D G-buffer layout |

**Extraction Difficulty:** Medium

The math is clean and portable. The challenge is wiring the PSSM shadow camera setup into Panda3D (creating N auxiliary cameras, binding the shadow map array) — this is engine integration work, not shader complexity. The GLSL itself extracts cleanly once the G-buffer and uniform layout is decided.

**Space Sim Relevance:**

High. In a space sim, "the sun" is always exactly one directional light source. The representative point model correctly simulates why specular highlights on polished metal aren't infinitesimally small — they have a disk shape matching the star's angular diameter. PSSM shadows are needed for close planetary passes and station docking where surface detail matters.

**Integration Target:** Pax3D lighting pipeline — the primary direct illumination pass for all scene geometry when within a stellar system.

---

## Tier 2 — High Value Extractions

---

### 6. Atmospheric Scattering — Hosek-Wilkie (Lightweight)

**Purpose:** Analytic sky color model using precomputed Hosek-Wilkie spectral coefficients stored in a 3D LUT, combined with a 6-step height-layer raymarcher and exponential height fog. Suitable for real-time planet atmosphere rendering.

**Source files:**

| File | Approx Lines | Role |
|------|--------------|------|
| `rpplugins/scattering/shader/hosek_wilkie/compute_scattering.inc.glsl` | ~100 | Sky color LUT lookup + fog |
| `rpplugins/scattering/shader/hosek_wilkie/hosek_wilkie_coeff.inc.glsl` | ~200 | Precomputed coefficient tables |

**Total GLSL lines:** ~300

**Technical Implementation:**

Hosek-Wilkie (Siggraph 2012 "An Analytic Model for Full Spectral Sky-Dome Radiance") fits 9 polynomial coefficients per sky color channel to measured sky data. These coefficients are tabulated against turbidity and solar elevation, then baked into a 3D texture.

_LUT indexing:_
```glsl
// LUT dimensions: [gamma_norm, elevation_norm, sun_elevation_slice]
float gamma_norm       = gamma / (2.0 * M_PI);          // angle between view and sun
float elevation_norm   = 1.0 - (elevation / (M_PI / 2.0)); // flipped: 0=zenith, 1=horizon
float sun_elev_slice   = sun_elevation / (M_PI / 2.0);  // which precomputed sun slice

vec3 sky_color = texture(scattering_lut, vec3(gamma_norm, elevation_norm, sun_elev_slice)).rgb;
```

_6-step height raymarcher:_
```glsl
// Integrate through 6 atmosphere height layers:
float layer_heights[6] = float[](0.0, 1000.0, 5000.0, 15000.0, 50000.0, 100000.0);
for (int i = 0; i < 6; i++) {
    // Sample LUT at this height, weight by layer thickness and density
    sky_color += sample_lut_at_height(view_dir, sun_dir, layer_heights[i]) * layer_weights[i];
}
```

_Exponential height fog:_
```glsl
// Analytic integration of exp(-height * fog_density):
float fog_factor = fog_density * exp(-camera_height * fog_falloff)
                 * (1.0 - exp(-ray_length * ray_dir.z * fog_falloff)) / ray_dir.z;
```

_Sun disk:_
```glsl
// Limb-darkening approximated by steep power function:
float sun_disk = pow(saturate(dot(view_dir, sun_direction) + 0.000069), 23.0 * 1e5);
```

**Inputs Required:**

| Uniform | Type | Description |
|---------|------|-------------|
| `scattering_lut` | `sampler3D` | Precomputed Hosek-Wilkie LUT |
| `sun_direction` | `vec3` | Normalized world-space sun direction |
| `camera_pos` | `vec3` | World position (for height fog) |
| `fog_density` | `float` | Exponential fog scale |
| `fog_falloff` | `float` | Height falloff coefficient |
| `turbidity` | `float` | Atmospheric haziness (1–10) |

**Outputs Produced:** `vec3` sky radiance for a given view direction. Used for skybox rendering and atmospheric haze on scene geometry.

**RP-Specific Dependencies:**

| Dependency | Replacement |
|------------|-------------|
| `scattering_setting_*` macros | Uniforms or defines |
| `MainSceneData.camera_pos` | `uniform vec3 camera_pos` |
| `render_pipeline_base.inc.glsl` | Remove |

**Extraction Difficulty:** Medium

The LUT generation must be ported (Python script in the RP generates the 3D texture). The GLSL runtime code itself is straightforward. The LUT generator (in `rpplugins/scattering/hosek_wilkie_lut_generator.py`) runs on CPU and produces a DDS/PNG that must be loaded into Panda3D as a 3D texture.

**Space Sim Relevance:**

High. Every habitable planet needs an atmosphere rendered from orbit and from near-surface flight. Hosek-Wilkie gives physically plausible sky colors across dawn-to-dusk cycle without full path tracing. For non-Earth atmospheres, turbidity and fog parameters can shift the color balance to simulate reducing, oxidizing, or hazy atmospheres.

**Integration Target:** Planet atmosphere renderer — skybox/skydome pass for near-planet flight modes.

---

### 7. Atmospheric Scattering — Bruneton (Physically Accurate)

**Purpose:** Full precomputed atmospheric scattering with 4D LUTs encoding transmittance, in-scattering, and irradiance. Physically correct for any planet atmosphere parameters. Heavier than Hosek-Wilkie but renders correctly from any altitude including orbit-to-surface transitions.

**Source files:**

| File | Approx Lines | Role |
|------|--------------|------|
| `rpplugins/scattering/shader/eric_bruneton/transmittance.glsl` | ~60 | Transmittance LUT precompute |
| `rpplugins/scattering/shader/eric_bruneton/inscatter1.glsl` | ~80 | Single scattering LUT pass 1 |
| `rpplugins/scattering/shader/eric_bruneton/inscatter1delta.glsl` | ~60 | Single scattering delta |
| `rpplugins/scattering/shader/eric_bruneton/inscatterN.glsl` | ~70 | Multiple scattering iterations |
| `rpplugins/scattering/shader/eric_bruneton/irradiance1.glsl` | ~40 | Irradiance LUT |
| `rpplugins/scattering/shader/eric_bruneton/irradianceN.glsl` | ~40 | Multiple scattering irradiance |
| `rpplugins/scattering/shader/eric_bruneton/copyIrradiance.glsl` | ~25 | Accumulation pass |
| `rpplugins/scattering/shader/eric_bruneton/copyInscatter1.glsl` | ~25 | Accumulation pass |
| `rpplugins/scattering/shader/eric_bruneton/render_sky.inc.glsl` | ~150 | Runtime rendering |
| `rpplugins/scattering/shader/eric_bruneton/definitions.glsl` | ~50 | Constants and LUT dimensions |

**Total GLSL lines:** ~700

**Technical Implementation:**

Based on Bruneton & Neyret (2008) "Precomputed Atmospheric Scattering" with Hillaire (2016) improvements for multiple scattering. The core insight is to precompute all light transport into a set of texture lookups, enabling real-time rendering of accurate Rayleigh + Mie scattering.

_LUT dimensions (from `definitions.glsl`):_

| LUT | Dimensions | Encoding |
|-----|-----------|----------|
| Transmittance | 256×64 (2D) | [cos(view_zenith), altitude_norm] → optical depth |
| Inscatter | 32×128×32×8 (4D packed) | [R, mu, mu_s, nu] → in-scattered radiance |
| Irradiance | 64×16 (2D) | [mu_s, altitude_norm] → ground irradiance |

_Physical constants (Rayleigh + Mie):_
```glsl
// Rayleigh scattering coefficients (RGB, m^-1):
const vec3 betaR = vec3(5.8e-3, 1.35e-2, 3.31e-2);
// Mie scattering coefficient (grey, m^-1):
const float betaMSca = 4e-3;
// Height scales (m):
const float HR = 8000.0;    // Rayleigh scale height
const float HM = 1200.0;    // Mie scale height
// Phase:
const float mieG = 0.8;     // Mie asymmetry factor
```

_Runtime rendering (`render_sky.inc.glsl`):_
```glsl
// Top-level entry point:
vec3 DoScattering(vec3 camera_pos, vec3 view_dir, vec3 sun_dir) {
    vec2 ray = intersect_atmosphere(camera_pos, view_dir);
    vec3 inscatter = get_inscattered_light(camera_pos, view_dir, sun_dir, ray);
    vec3 transmittance = get_transmittance(camera_pos, view_dir, ray);
    return inscatter;   // transmittance applied to scene color by caller
}

// Ray-sphere atmosphere intersection:
vec2 intersect_atmosphere(vec3 origin, vec3 direction) {
    // Intersect against outer atmosphere sphere (Rg=6360km, Rt=6420km):
    float Rg = 6360000.0;  // ground radius
    float Rt = 6420000.0;  // top atmosphere radius
    // ... standard ray-sphere math
}
```

**Settings (configurable per planet type):**

| Setting | Default (Earth) | Notes |
|---------|-----------------|-------|
| `rayleigh_height_scale` | 8000 m | Controls blue sky depth |
| `mie_height_scale` | 1200 m | Controls haze near horizon |
| `beta_mie_scattering` | 4e-3 | Aerosol density |
| `mie_phase_factor` | 0.8 | Mie lobe asymmetry (0=isotropic) |
| `ground_reflectance` | 0.1 | Albedo of surface |

**Inputs Required:**

| Uniform | Type | Description |
|---------|------|-------------|
| `transmittance_tex` | `sampler2D` | Precomputed 256×64 transmittance LUT |
| `inscatter_tex` | `sampler3D` | Precomputed 4D inscatter (packed as 3D) |
| `irradiance_tex` | `sampler2D` | Precomputed 64×16 irradiance LUT |
| `sun_direction` | `vec3` | Normalized sun direction |
| `camera_pos` | `vec3` | World position |
| `camera_far` | `float` | Far plane for depth reconstruction |

**Outputs Produced:** `vec3` physically accurate sky radiance for any camera position/altitude.

**RP-Specific Dependencies:**

| Dependency | Replacement |
|------------|-------------|
| `scattering_setting_*` | Uniforms |
| `GET_SETTING` macros | Uniforms or defines |
| Precomputation Python code | Must run separately to generate LUTs |
| `render_pipeline_base.inc.glsl` | Remove |

**Extraction Difficulty:** High

The GLSL itself is clean. The challenge is the multi-pass LUT precomputation (5–8 sequential GPU passes with specific framebuffer ping-pong). tobspr runs these on startup. In Pax3D, LUTs could be precomputed offline and saved as textures, or computed once per planet type. The 4D LUT packing into a 3D texture (slicing the nu dimension) requires careful understanding of the texture coordinate mapping documented in `definitions.glsl`.

**Space Sim Relevance:**

High. Bruneton correctly handles the camera at any altitude — viewing atmosphere from orbit, from 10km altitude, and from the surface — all with the same shader. This is critical for a space sim that transitions between space and near-planet flight. Hosek-Wilkie only works from a single altitude. Bruneton also correctly renders the limb of a planet from orbit, which is essential visual feedback for the player.

**Integration Target:** Planet atmosphere system — used for planet skydomes on planetary surfaces and as a compositing overlay for orbit-altitude views.

---

### 8. Screen-Space Reflections (SSR)

**Purpose:** Half-resolution, importance-sampled GGX screen-space ray marching for specular reflections on metallic and glossy surfaces (cockpit glass, polished hull panels, space station windows).

**Source files:**

| File | Approx Lines | Role |
|------|--------------|------|
| `rpplugins/ssr/shader/generate_ssr.frag.glsl` | ~120 | Ray march + hit detection |
| `rpplugins/ssr/shader/resolve_ssr.frag.glsl` | ~80 | Temporal reprojection |
| `rpplugins/ssr/shader/upscale_ssr.frag.glsl` | ~60 | Bilateral upscale to full resolution |
| `rpplugins/ssr/shader/ssr_common.inc.glsl` | ~50 | GGX importance sampling helper |
| `rpplugins/ssr/shader/apply_ssr.frag.glsl` | ~40 | BRDF-weighted blend into scene |

**Total GLSL lines:** ~350

**Technical Implementation:**

_Ray generation (`generate_ssr.frag.glsl`):_

Unlike naive mirror-reflection SSR, this uses importance-sampled GGX to trace rays distributed around the specular lobe, weighted by the GGX distribution. This produces correct glossy (not just mirror) reflections with roughness-dependent softness.

```glsl
// GGX importance sample (from ssr_common.inc.glsl):
vec3 importance_sample_ggx(vec2 Xi, float roughness, vec3 N) {
    float a = roughness * roughness;
    float phi = 2.0 * M_PI * Xi.x;
    float cos_theta = sqrt((1.0 - Xi.y) / (1.0 + (a*a - 1.0) * Xi.y));
    float sin_theta = sqrt(1.0 - cos_theta * cos_theta);
    vec3 H = vec3(sin_theta * cos(phi), sin_theta * sin(phi), cos_theta);
    // Transform H from tangent space to world space
    return H;
}
```

Ray is marched in screen space using linear depth comparison. Three retries with different offsets if first ray misses geometry. Jittered ray start (per-frame noise texture) to distribute artifacts for temporal smoothing.

_Discard conditions:_
- Skip pixels with `roughness > roughness_fade` (falls back to environment cubemap)
- Skip pixels with world distance `> 3000` units (too far for SS validity)
- Skip rays that march off screen

_Temporal reprojection (`resolve_ssr.frag.glsl`):_

Previous frame's SSR result is reprojected using the velocity buffer. Blend ratio controlled by reprojection confidence (how well screen position matches history).

_Bilateral upscale (`upscale_ssr.frag.glsl`):_

Half-resolution SSR result is upscaled to full resolution using depth-weighted bilateral filter to prevent reflection bleeding across depth discontinuities.

**Inputs Required:**

| Uniform | Type | Description |
|---------|------|-------------|
| `scene_depth` | `sampler2D` | Hardware depth buffer (or linear depth) |
| `scene_normals` | `sampler2D` | World-space normals G-buffer |
| `scene_roughness` | `sampler2D` | Roughness G-buffer |
| `scene_color` | `sampler2D` | Previous frame HDR color |
| `velocity_buffer` | `sampler2D` | Screen-space velocity (for reprojection) |
| `noise_tex` | `sampler2D` | Per-frame jitter noise |
| `camera_mvp` | `mat4` | Current frame MVP |
| `prev_mvp` | `mat4` | Previous frame MVP (for reprojection) |
| `roughness_fade` | `float` | Roughness above which SSR is skipped |
| `max_march_steps` | `int` | Ray march step count (default 32) |

**Outputs Produced:** Half-resolution SSR color buffer, upscaled to full resolution and blended into scene.

**RP-Specific Dependencies:**

| Dependency | Where Used | Replacement |
|------------|------------|-------------|
| G-buffer layout macros | All | Adapt to Pax3D G-buffer |
| `MainSceneData.camera_*` | All | Uniforms |
| `GET_SETTING(ssr, ...)` | All | Uniforms |
| `importance_sampling.inc.glsl` | generate_ssr | Port alongside (Tier 3, item 15) |

**Extraction Difficulty:** Medium

The algorithm is well-contained. Integration work is non-trivial because SSR requires a velocity buffer and a previous-frame color buffer — these must be explicitly wired into Pax3D's render pipeline. G-buffer layout must match what the RP expects. The GGX importance sampling is the most complex math but is straightforward once `importance_sampling.inc.glsl` is ported.

**Space Sim Relevance:**

Medium-High. Cockpit glass, polished instrument panels, and metallic station corridors all benefit significantly. Open space surfaces (hull exterior, asteroids) benefit less because there is no nearby scene content to reflect. Worth including for interior and close-up rendering passes.

**Integration Target:** Pax3D post-process pipeline — runs after G-buffer fill, result blended into lighting pass.

---

### 9. SMAA Anti-aliasing

**Purpose:** Subpixel Morphological Anti-aliasing — high quality temporal-stable edge anti-aliasing. The canonical implementation from Jimenez et al. 2013.

**Source files:**

| File | Approx Lines | Role |
|------|--------------|------|
| `rpplugins/smaa/shader/SMAA.inc.glsl` | ~1300 | Full canonical SMAA library |
| `rpplugins/smaa/shader/edge_detection.frag.glsl` | ~30 | Luma/color edge detection wrapper |
| `rpplugins/smaa/shader/blend_weights.frag.glsl` | ~30 | Blend weight computation wrapper |
| `rpplugins/smaa/shader/blend_neighbors.frag.glsl` | ~30 | Final neighborhood blend wrapper |

**Total GLSL lines:** ~1400 (library is canonical third-party code)

**Technical Implementation:**

SMAA operates in three passes:
1. **Edge detection** — identifies aliased edges using luma or color contrast
2. **Blend weight computation** — calculates how much to blend adjacent pixels using the SMAA pattern search
3. **Neighborhood blending** — applies accumulated blend weights

The tobspr wrappers are minimal (20–30 lines each) around the canonical SMAA.inc.glsl library which is unchanged from the reference implementation.

**Extraction Difficulty:** Very Low

The SMAA library is third-party open source (MIT license). The RP wrappers add only `get_texcoord()` substitution (3–4 lines per file). Drop the canonical SMAA.inc.glsl in, fix the texcoord macro, done.

**Space Sim Relevance:**

High. Space scenes have hard geometric edges (ship hull silhouettes against black space) that alias severely without AA. SMAA provides clean edges without the ghosting artifacts of TAA on high-contrast moving geometry.

**Integration Target:** Pax3D post-process pipeline — final pass before output, or before tonemapping.

---

### 10. FXAA 3.11

**Purpose:** Fast Approximate Anti-aliasing — single-pass edge smoothing. Lighter and faster than SMAA, useful as a quality-tier fallback.

**Source files:**

| File | Approx Lines | Role |
|------|--------------|------|
| `rpplugins/smaa/shader/FXAA.inc.glsl` | ~1200 | Canonical FXAA 3.11 library (Lottes/Nvidia) |
| `rpplugins/smaa/shader/apply_fxaa.frag.glsl` | ~25 | Thin RP wrapper |

**Extraction Difficulty:** Very Low. Same as SMAA — canonical library with a thin wrapper.

**Space Sim Relevance:** Medium. Good for lower-end hardware target. SMAA preferred when available.

**Integration Target:** Same as SMAA — post-process pipeline, quality-tier selection.

---

## Tier 3 — Nice to Have

---

### 11. Color Correction + Post-FX

**Purpose:** 64³ 3D LUT color grading, vignette, film grain, and chromatic aberration. Also includes histogram-based auto-exposure.

**Source files:**

| File | Approx Lines | Role |
|------|--------------|------|
| `rpplugins/color_correction/shader/apply_tonemap.frag.glsl` | ~60 | Tonemap + 3D LUT color grading |
| `rpplugins/color_correction/shader/post_fx.frag.glsl` | ~80 | Vignette, film grain, chromatic aberration |
| `rpplugins/color_correction/shader/generate_luminance.frag.glsl` | ~30 | Histogram bin generation |
| `rpplugins/color_correction/shader/downscale_luminance.frag.glsl` | ~25 | Downsample for average luma |
| `rpplugins/color_correction/shader/analyze_brightness.frag.glsl` | ~40 | Extract target exposure from histogram |
| `rpplugins/color_correction/shader/color_correction_common.inc.glsl` | ~20 | Shared LUT sampling helper |

**Total GLSL lines:** ~255

**Technical Implementation:**

_3D LUT color grading (`apply_tonemap.frag.glsl`):_
```glsl
// After tonemapping, apply 64^3 color LUT:
vec3 lut_uv = saturate(color.rgb) * (64.0 - 1.0) / 64.0 + 0.5 / 64.0;
vec3 graded = texture(color_lut, lut_uv).rgb;
```

_Post-FX (`post_fx.frag.glsl`):_
```glsl
// Vignette:
float vignette = 1.0 - vignette_strength * pow(length(tc - 0.5) * 2.0, vignette_power);
color *= vignette;

// Film grain (value noise, animated):
float grain = fract(sin(dot(tc, vec2(12.9898, 78.233)) + time) * 43758.5453);
color += (grain - 0.5) * grain_strength;

// Chromatic aberration (radial lens fringe):
float aberration = length(tc - 0.5) * chromatic_aberration;
color.r = texture(scene_color, tc + vec2(aberration, 0)).r;
color.b = texture(scene_color, tc - vec2(aberration, 0)).b;
```

_Auto-exposure (3-pass):_
1. `generate_luminance` — downsample scene to 64×64, compute log-luminance per pixel into histogram
2. `downscale_luminance` — reduce histogram to single average luma value
3. `analyze_brightness` — compute target EV100 from average, smooth toward target using `mix(current, target, dt * adaption_speed)`

**Extraction Difficulty:** Low

The post-FX pass is completely self-contained. The auto-exposure histogram requires 3 sequential passes but no RP-specific infrastructure beyond a ping-pong float texture. LUT color grading requires generating a 3D LUT texture (can be identity LUT initially, then artist-authored for scene mood).

**Space Sim Relevance:**

Medium. Film grain gives footage a cinematic sensor-noise quality appropriate for a space sim's cameras. Chromatic aberration on extreme HDR sources (sun glare) looks authentic. Vignette subtly reinforces the viewport-as-sensor metaphor. 3D LUT grading allows per-scene mood control (cold deep space vs warm orange atmosphere). Auto-exposure is critical if the bloom system doesn't already handle this.

**Integration Target:** Pax3D post-process pipeline — very last pass before display output.

---

### 12. Volumetric Fog (Analytic)

**Purpose:** Analytic exponential height fog. NOT voxel-grid volumetrics — this is a closed-form integral of an exponential density function, trivially fast and easily ported.

**Source files:**

| File | Approx Lines | Role |
|------|--------------|------|
| `rpplugins/volumetrics/shader/apply_volumetrics.frag.glsl` | ~50 | Fog color + density application |
| `rpplugins/volumetrics/shader/volumetrics_common.inc.glsl` | ~30 | Fog integral function |

**Total GLSL lines:** ~80

**Technical Implementation:**

```glsl
// Analytic integral of exp(-density * height * falloff) along a ray:
float compute_fog_integral(vec3 camera_pos, vec3 ray_dir, float ray_length,
                           float fog_density, float fog_falloff) {
    float c = fog_density * exp(-camera_pos.z * fog_falloff);
    float b = fog_falloff;

    if (abs(ray_dir.z) < 0.0001) {
        // Horizontal ray: simple exponential attenuation
        return c * ray_length;
    } else {
        // Angled ray: integrated closed form
        return c * (1.0 - exp(-ray_length * ray_dir.z * b)) / (ray_dir.z * b);
    }
}

// Usage:
float fog_amount = compute_fog_integral(camera_pos, view_dir, scene_depth, density, falloff);
vec3 fog_color = sun_color * 0.5 + ambient_color * 0.5;
color = mix(color, fog_color, saturate(fog_amount));
```

Optional: volumetric shadow texture from PSSM can modulate fog color to create shafts of light — but this is not required for the base analytic fog.

**Extraction Difficulty:** Very Low

Pure math, 80 lines total, no RP infrastructure needed.

**Space Sim Relevance:**

Medium. Primarily useful for nebula regions where particle/gas density should attenuate distant objects. Also useful for planetary atmosphere haze at low altitude when Bruneton/Hosek-Wilkie handle only the sky dome, not scene geometry attenuation. Can also simulate dust in asteroid fields or gas torus regions near giant planets.

**Integration Target:** Pax3D post-process pipeline — applied per-fragment during scene compositing.

---

### 13. Motion Blur (McGuire 2012)

**Purpose:** Reconstruction-filter motion blur using tile-based dominant velocity, per-sample depth and velocity weighting. Perceptually correct — fast-moving objects blur, stationary objects do not.

**Source files:**

| File | Approx Lines | Role |
|------|--------------|------|
| `rpplugins/motion_blur/shader/tiles_minmax.frag.glsl` | ~40 | Build velocity tile buffer |
| `rpplugins/motion_blur/shader/tiles_neighbor.frag.glsl` | ~35 | Neighbor tile max velocity |
| `rpplugins/motion_blur/shader/generate_motion_blur.frag.glsl` | ~100 | McGuire reconstruction filter |
| `rpplugins/motion_blur/shader/pack_velocity.frag.glsl` | ~30 | Velocity buffer preparation |
| `rpplugins/motion_blur/shader/motion_blur_common.inc.glsl` | ~45 | Cone/cylinder weight functions |

**Total GLSL lines:** ~250

**Technical Implementation:**

Based on McGuire et al. 2012 "A Reconstruction Filter for Plausible Motion Blur". The key insight is to avoid blurring all pixels along velocity — instead, use tile-based dominant velocity to reconstruct what a real camera sensor would record.

```glsl
// McGuire cone weight (foreground contribution):
float cone_weight(float distance, float velocity_mag) {
    return saturate(1.0 - abs(distance) / velocity_mag);
}

// McGuire cylinder weight (background contribution from fast objects):
float cylinder_weight(float distance, float velocity_mag) {
    return 1.0 - smoothstep(0.95 * velocity_mag, 1.05 * velocity_mag, abs(distance));
}

// Main reconstruction loop:
for (int i = 0; i < num_samples; i++) {
    float t = mix(-1.0, 1.0, (i + jitter) / float(num_samples));
    vec2 sample_pos = texcoord + velocity_dominant * t;
    float depth_diff = sample_depth - texture(depth_buf, sample_pos).r;

    float w  = cone_weight(t, velocity_dominant_mag)
             * cylinder_weight(t * depth_diff, velocity_dominant_mag)
             * depth_weight(depth_diff);
    color_sum += texture(scene_color, sample_pos).rgb * w;
    weight_sum += w;
}
result = color_sum / max(weight_sum, 0.0001);
```

**Extraction Difficulty:** Medium

Requires a velocity buffer (screen-space per-pixel velocity from current/previous MVP transforms). The velocity buffer must be filled during the geometry pass, which requires Pax3D to render with dual MVP matrices. The blur shader itself is well-contained.

**Space Sim Relevance:**

Low-Medium. Useful for fast ship maneuvers and FTL entry/exit effects. Less critical in open space where the camera often tracks slowly. Could be applied selectively only during high-speed passes.

**Integration Target:** Pax3D post-process pipeline — applied before SMAA/FXAA to avoid blurring AA result.

---

### 14. Normal Packing (Octahedral)

**Purpose:** Compact 2-component normal encoding for G-buffer storage. Better quality than sphere-map encoding, used for normals in any deferred pipeline.

**Source file:** `rpcore/shader/includes/normal_packing.inc.glsl`

**Total GLSL lines:** ~20

**Technical Implementation:**

```glsl
// Octahedral encoding — maps hemisphere to [-1,1]^2
vec2 octahedron_encode(vec3 n) {
    n /= abs(n.x) + abs(n.y) + abs(n.z);
    if (n.z < 0.0) {
        vec2 tmp = n.xy;
        n.xy = (1.0 - abs(n.yx)) * sign(tmp);
    }
    return n.xy;
}

// Decode:
vec3 octahedron_decode(vec2 e) {
    vec3 n = vec3(e, 1.0 - abs(e.x) - abs(e.y));
    if (n.z < 0.0) n.xy = (1.0 - abs(n.yx)) * sign(n.xy);
    return normalize(n);
}
```

Octahedral encoding preserves the full sphere (unlike sphere-map which loses back-facing normals), is uniform in quality across the sphere, and uses only 2 components.

**Extraction Difficulty:** Very Low. 20 lines, zero dependencies.

**Space Sim Relevance:** Low — primarily a G-buffer utility. Include in engine-level shader library for completeness.

**Integration Target:** Engine-level include — G-buffer write/read wherever normals are stored.

---

### 15. Importance Sampling (GGX + Cosine Hemisphere)

**Purpose:** Quasi-random GGX importance sampling for IBL and SSR. Hammersley low-discrepancy sequence + GGX distribution warping.

**Source file:** `rpcore/shader/includes/importance_sampling.inc.glsl`

**Total GLSL lines:** ~80

**Technical Implementation:**

```glsl
// Hammersley point set (low-discrepancy 2D sequence):
vec2 hammersley(uint i, uint N) {
    uint bits = i;
    bits = (bits << 16u) | (bits >> 16u);
    bits = ((bits & 0x55555555u) << 1u) | ((bits & 0xAAAAAAAAu) >> 1u);
    bits = ((bits & 0x33333333u) << 2u) | ((bits & 0xCCCCCCCCu) >> 2u);
    bits = ((bits & 0x0F0F0F0Fu) << 4u) | ((bits & 0xF0F0F0F0u) >> 4u);
    bits = ((bits & 0x00FF00FFu) << 8u) | ((bits & 0xFF00FF00u) >> 8u);
    float vdc = float(bits) * 2.3283064365386963e-10;
    return vec2(float(i) / float(N), vdc);
}

// GGX importance sample:
vec3 importance_sample_ggx(vec2 Xi, float roughness, vec3 N) {
    float a = roughness * roughness;
    float phi = 2.0 * M_PI * Xi.x;
    float cos_theta = sqrt((1.0 - Xi.y) / (1.0 + (a*a - 1.0) * Xi.y));
    float sin_theta = sqrt(1.0 - cos_theta * cos_theta);
    vec3 H = vec3(sin_theta * cos(phi), sin_theta * sin(phi), cos_theta);
    // TBN basis construction omitted for brevity
    return H_world;
}

// Cosine hemisphere sample:
vec3 importance_sample_cosine(vec2 Xi, vec3 N) {
    float phi = 2.0 * M_PI * Xi.x;
    float cos_theta = sqrt(1.0 - Xi.y);
    float sin_theta = sqrt(Xi.y);
    // ... TBN transform
}
```

**Extraction Difficulty:** Very Low. Standalone math, no RP coupling. Required by SSR and any IBL convolution.

**Space Sim Relevance:** Core dependency for SSR (Tier 2). Directly useful for offline IBL cubemap convolution for environment lighting of ship hulls.

**Integration Target:** Engine-level include, alongside brdf.inc.glsl.

---

## Tier 4 — Skip for Space Sim

| Shader | Location | Reason to Skip |
|--------|----------|----------------|
| VXGI (Voxel Cone Tracing GI) | `rpplugins/vxgi/` | Indoor/scene GI technique, irrelevant in open space |
| Depth of Field | `rpplugins/dof/` | tobspr documented it as WIP and incomplete; not production-ready |
| Volumetric Clouds | `rpplugins/clouds/` | No planetary surface cloud rendering needed for space orbit |
| Skin Shading (SSS) | `rpplugins/skin_shading/` | No close-up character rendering |
| Sky AO (SSAO variant) | `rpplugins/sky_ao/` | Sky AO adds upward occlusion using skylight — irrelevant in space |
| Full AO Suite (5 variants) | `rpplugins/ao/` | All 5 variants (SSAO, SAO, HBAO, HBIL, ALCHEMY) — possibly relevant for ship interiors later but not a space sim priority |
| Bloom lens flare | `rpplugins/bloom/` (partial) | The lens flare component of bloom (lens_dirt_factor) can be skipped; the core bloom is Tier 1 |
| Temporal AA (TAA) | `rpplugins/temporal_aa/` | tobspr TAA has known ghosting on high-contrast space geometry; SMAA preferred |

---

## Dependency Graph

```
color_spaces.inc.glsl (4)          ← No dependencies
  └─ used by: bloom (1), tonemapping (2), scattering (6,7)

tonemapping.inc.glsl (2)           ← color_spaces
  └─ used by: color_correction (11)

brdf.inc.glsl (3)                  ← color_spaces, M_PI
  └─ used by: pssm sun (5), ssr resolve (8), any lit surface

importance_sampling.inc.glsl (15)  ← No RP dependencies
  └─ used by: ssr (8)

normal_packing.inc.glsl (14)       ← No dependencies
  └─ used by: G-buffer write/read

bloom (1)                          ← color_spaces (4)
pssm/sun (5)                       ← brdf (3), color_spaces (4)
ssr (8)                            ← importance_sampling (15), brdf (3)
scattering hosek (6)               ← color_spaces (4)
scattering bruneton (7)            ← color_spaces (4)
color_correction (11)              ← tonemapping (2), color_spaces (4)
volumetric_fog (12)                ← No RP dependencies
motion_blur (13)                   ← No RP dependencies (needs velocity buffer)
smaa/fxaa (9,10)                   ← No RP dependencies
```

**Recommended extraction order:**
1. color_spaces (foundation, no dependencies)
2. tonemapping (depends on color_spaces)
3. brdf (depends on color_spaces)
4. importance_sampling (standalone)
5. normal_packing (standalone)
6. bloom (depends on color_spaces)
7. pssm/sun (depends on brdf, color_spaces)
8. smaa + fxaa (standalone)
9. ssr (depends on importance_sampling, brdf)
10. scattering (depends on color_spaces)
11. color_correction + post_fx (depends on tonemapping)
12. volumetric_fog (standalone)
13. motion_blur (standalone, needs velocity buffer infrastructure)

---

## Notes on RenderPipeline Architecture

Understanding what the RP wraps around these shaders helps estimate extraction cost.

**What `render_pipeline_base.inc.glsl` provides:**
- `get_texcoord()` — fragment texture coordinate
- `SCREEN_SIZE` — vec2 pixel dimensions
- `MainSceneData` uniform block — camera matrices, position, near/far
- `IS_FIRST_FRAME` — frame counter flag
- Utility macros: `saturate`, `square`, `lerp`
- `START/END_ITERATE_SEQUENCE` — AO sample unrolling macros

**What G-buffer macros provide:**
- `GBuffer_SampleAlbedo(tc)`, `GBuffer_SampleNormal(tc)`, etc.
- These must be replaced with direct texture2D lookups into Pax3D's own G-buffer layout

**What `GET_SETTING(plugin, name)` provides:**
- Integer, float, or boolean uniform named `plugin_name`
- Direct replacement: `uniform float plugin_name;`

**What `HAVE_PLUGIN(x)` provides:**
- Conditional compilation based on which RP plugins are loaded
- Replace with `#define HAVE_PLUGIN_x 0` or `1` at build time

---

*Document generated for Pax3D development reference.*
*Source repository: https://github.com/tobspr/RenderPipeline*
*Last known repository activity: January 2021*
