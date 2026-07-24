# Pax3D — Modification Inventory, Effort Estimate and Costing

**Date:** 2026-07-19 · **Question asked:** what has been changed relative to
stock Panda3D, what would a conventional human development team need to
produce the same thing, how long would it take, and what would it cost?
· **Method:** direct measurement of the repository (git, line counts,
API extraction) plus a development-rate benchmark taken from upstream
Panda3D's own history.

All numbers below are measured, not estimated, unless explicitly labelled
as an estimate. Measurement commands are named so they can be re-run.

---

## 1. Measured divergence from upstream

Fork point: `3f5ea05d1c` (upstream master, 2026-07-14). Everything below is
`git diff <merge-base>..master`.

| Metric | Value |
|---|---|
| Fork commits | 86, single author (83 of them 2026-07-16 to 07-19; 3 in Feb 2026) |
| Files changed | 380 |
| Lines inserted | 31,236 |
| Lines deleted | 43,338 |
| **Net** | **−12,102. The fork is smaller than upstream** |
| New files added by the fork | 120 |
| Upstream files deleted | 217 |
| Upstream files modified | 43 (98 lines added across all of them) |
| New C++ engine behaviour | **34 lines, 1 file** (`glGraphicsStateGuardian_src.cxx`) |

The merge-base is upstream master's own tip, so this diff contains zero
upstream contamination. It is pure fork divergence.

The last row is the headline finding and it is easy to misread. The fork has
added almost no C++. Of the 43 modified upstream files, the churn is
concentrated in `makepanda/makepanda.py` (546 lines), `makepandacore.py`
(475), `direct/src/dist/commands.py` (376) and `makepackage.py` (189), which
is build-system and packaging scrubbing that fell out of the deletion
programme, not feature work. Exactly one `// PAX3D:` tag exists in the entire
engine tree.

The engineering value sits in three new first-party trees that stock Panda3D
does not have at all, and in the removal of 217 upstream files.

### New first-party code

| Tree | Files | Lines | What |
|---|---|---|---|
| `pax3d_render/` | 21 | 5,317 | The rendering pipeline (Python + GLSL) |
| `tools/paxtest/` | 46 | 10,410 | Offscreen analytic graphics test harness |
| `tools/gen_*.py` | 3 | ~600 | Content bake tools (BRDF LUT, GGX prefilter, equirect to cubemap) |
| `pax3d_simplepbr/` | 11 | 1,819 raw, **~500 original** | Retired intermediate fork. See caveat below |
| **Total** | **81** | **~16,800 (~16,100 original)** | |

Two counting caveats, both checked rather than assumed:

- **`pax3d_simplepbr` is mostly vendored.** It is a fork of Moguri's `simplepbr` 0.13.1. Diffed against the stock package, roughly 830 lines are byte-identical and a further ~430 unchanged; `shaders.py` reads as "+300 lines" only because upstream ships it minified to a single line and the fork reflowed it. Genuine fork authorship is ~400 to 600 lines. The package is retired in any case and is excluded from the effort estimate.
- **`tools/paxtest/` holds 469 files on disk but only 46 are tracked.** The other ~423 are generated PNG render captures in `output/`. A naive working-tree count overstates it by an order of magnitude.

### Documentation

34 maintained documents, 11,513 lines, **~89,000 words**, cited to source
file and line and trued up at the end of each session.

Counting all prose in the diff (`documents/`, `CLAUDE.md`,
`PAX3D_FEEDBACK.md`), documentation is **13,455 lines, or 43% of everything
the fork added**. It is costed as its own lane in section 3.

---

## 2. The modification inventory

### 2.1 A complete first-party renderer (`pax3d_render`, 5,317 lines)

Stock Panda3D ships a fixed-function path and an auto-shader; PBR comes from
the third-party `simplepbr`. This replaces all of it with one pipeline.
23 distinct capability areas:

| # | Modification | Notes |
|---|---|---|
| 1 | Unified pipeline, merging two previously divergent forks | Colour contract, byte-identity discipline against the legacy path |
| 2 | Rebuild-safe auxiliary camera registration (`register_scene_camera`) | Fixes FilterManager orphaning externally-attached cameras |
| 3 | Shader-input-preserving runtime recompile | Invariant; a naive recompile wipes every shader input |
| 4 | GLSL 120 / 330-core dual path with source transpilation | `shaderutils.py` define-injection layer |
| 5 | Dual sun model: legacy uniforms and real `DirectionalLight` | Selectable for A/B |
| 6 | Shadow mapping with world-space extent centring | Camera-driven sizing |
| 7 | World-unit shadow bias (`shadow_bias_world`) | Fixes the normalised-depth bias trap |
| 8 | 3x3 PCF filtering (`shadow_filter_size`) | |
| 9 | Slope-scaled / normal-offset bias (`shadow_normal_bias_world`) | Kills grazing-angle acne, error proportional to 1/tan(altitude) |
| 10 | Shadow texel snapping (`shadow_texel_snap`) | Camera-following frustum shimmer fix |
| 11 | Caster masking and per-node exclusion | `exclude_from_shadows` / `include_in_shadows` |
| 12 | Skinned shadow casters, hardware and CPU, with per-node opt-out | `set_hardware_skinning(np, bool)` |
| 13 | Bloom and HDR chain on float FBOs | Root-caused an 8-bit intermediate-FBO downgrade |
| 14 | Four tonemap operators plus exposure | Reinhard, ACES, Uncharted2, Hejl-Dawson |
| 15 | sRGB input linearisation (`set_srgb_inputs`) | The real cause of the "double gamma" myth |
| 16 | TAA resolve | |
| 17 | Logarithmic depth (`enable_log_depth`) | Solar-system scale range |
| 18 | SSAO, depth-only Alchemy/SAO plus blur | Flat-geometry byte-identity gated |
| 19 | Lens flare and lens dirt | Ghosts sourced analytically from the bloom bright extract |
| 20 | Aerial perspective / exponential height haze, plus per-node scale | `enable_atmosphere`, `set_atmosphere_scale` |
| 21 | Orbital atmospheric scattering | Per-planet analytic limb, halo, terminator, Rayleigh reddening |
| 22 | SH irradiance ambient: hemisphere, raw SH, and skybox-derived | `sh_from_cubemap`, face table pinned end to end |
| 23 | Specular IBL: env map, real split-sum BRDF LUT, GGX prefilter chain | Plus per-subtree environment binding |
| 24 | Specular-preserving glass (`set_glass`) | Premultiplied-alpha PBR variant |
| 25 | Double-sided lighting via `gl_FrontFacing` normal flip | |
| 26 | Model-authored light activation (`activate_model_lights`) | KHR_lights_punctual from Blender/glTF |
| 27 | Per-node ambient scale (`set_ambient_scale`) | Keeps sky ambient out of interiors |
| 28 | Terrain splatting (`set_terrain_splat`) | 4 layers via texture arrays, macro variation, analytic world TBN, detail-normal distance fade |
| 29 | Hardware instancing integration (`set_instanced`) | Over upstream `InstancedNode`, including instanced shadow casting |
| 30 | Data-texture contract (`data_texture`, `load_data_texture`) | Immunity to the `texture-scale` prc trap and to driver compression |
| 31 | Content-sized bone palette plus oversize audit | `max_skinning_bones` |
| 32 | glTF loader compatibility shim (`gltf_compat`) | Fixes three upstream `panda3d-gltf` defects |
| 33 | FTL radial motion blur and chromatic aberration | |

Public API surface: 57 documented pipeline methods plus 4 module-level
functions.

The glTF shim (#32) deserves separate note. It fixes three real defects in
`panda3d-gltf` 1.3.0: sparse accessors (Blender's default shape-key
encoding) crashing on an optional `bufferView`; animation channels ending
before the clip's global end crashing the time-index lookup; and
`get_lerp_factor` clamping with `max(t,1)` instead of `min(t,1)`, which
snaps every linear sample to the next key. All three are masked by dense
per-frame bakes, which is why they survive upstream. Finding these required
byte-patching known values into a GLB and comparing against a Blender
ground-truth manifest.

### 2.2 The test harness (`tools/paxtest`, 10,354 lines)

This has no upstream counterpart and is the least conventional part of the
programme.

- **27 test modules** (~5,100 lines), 6 forensic probe scripts (~1,900 lines), runner, scene library, shared infrastructure (~1,500 lines), plus 7 binary fixtures (glTF morph heads, QA reference renders)
- Renders offscreen, reads pixels back, and compares against **closed-form analytic expectations**, not golden images
- Matrix: 5 pipelines x 2 GL baselines, currently 134 rows, run in seconds
- Independent reference implementations where the shader maths is non-trivial (the orbital scattering test carries its own integrator and matches the render to <= 0.003)
- Cross-engine: identical results on stock Panda3D 1.10.16 and the Pax3D wheel is itself the signal that a defect is in Python/GLSL rather than C++

### 2.3 Engine surgery: 217 files, 43,338 lines removed

| Window | Commit | Files | Lines removed | Content |
|---|---|---|---|---|
| 2 | `d29183ce42` | 65 | 16,691 | DirectX 9 (`dxgsg9`, `pandadx9`, all references) |
| 3 | `3912762dd9` | 132 | 18,546 | GLES, GLES2, EGL, WebGL, Android, iPhone and macOS display backends, plus DX9 flag machinery |
| 4 | `c627e2d0bc` | 72 | 8,112 | Android/iPhone target glue, Android cross-compile, dist mobile deploy, DIRECTCAM |

Ten subsystems were removed outright:

| Subsystem | Lines | Files |
|---|---:|---:|
| DX9 renderer (`dxgsg9`, `pandadx9`, `FindDirect3D9`, `winDetectDx`) | 16,449 | 46 |
| Android (`panda/src/android`, `androiddisplay`, asset VFS, log stream) | 6,325 | 44 |
| OpenGL ES 1/2 (`glesgsg`, `gles2gsg`, `pandagles`, `pandagles2`) | 5,168 | 22 |
| macOS Cocoa display (`cocoadisplay`, `cocoagldisplay`) | 5,005 | 36 |
| EGL display (`egldisplay`, `FindEGL`) | 2,306 | 18 |
| iOS / iPhone (`iphone`, `iphonedisplay`) | 1,937 | 21 |
| WebGL / Emscripten (`webgldisplay`) | 1,727 | 12 |
| DirectShow webcam and microphone | 1,247 | 4 |
| tinydisplay macOS flavour | 592 | 6 |
| `direct.dist` mobile deploy, `deploy-stub` mobile | 503 | 8 |

Each window carried its own full build and validation gate. The result is a
tree that ships exactly one graphics reality: OpenGL 3.3+ core on Windows,
with X11/GLX held and the tinydisplay software rasteriser retained as
GPU-less insurance.

### 2.4 Build and C++ work

- Upstream catch-up merge (`eb685fd003`): 1,387 files, C++17 migration plus 93 commits absorbed, conflict-resolved and build-validated
- Build system brought up on VS Build Tools 2026 / MSVC 14.5, including the makepanda `oscmd` fix and toolchain-detection workarounds
- `STDFLOAT_DOUBLE` build variant brought up and verified to 0.000e+00 round-trip precision at Neptune-scale offsets. Upstream has never CI'd this configuration
- One new C++ engine behaviour: a core-profile combine-mode warning in `glgsg` (34 lines), which caught a real silently-flattened texture state in a downstream game on its first day

### 2.5 Engine research

`ENGINE_INTERNALS.md` records mechanisms dug out of the C++ and pinned by
tests: texture-pipeline format selection and silent-degradation paths,
ShaderAttrib composition and multi-pass state resolution, the full hardware
instancing chain, and instrument traps for test authors. Sixteen
programme-level facts are recorded with permanent test guards, several of
which overturned long-held beliefs about the engine.

### 2.6 What is genuinely new, versus what already existed

The §2.1 inventory lists what the pipeline *does*. It is not the same
question as what Pax3D brings that Panda3D did not have, because some of
those 33 areas re-implement capability that stock Panda3D or simplepbr
already shipped. Checked against the actual installed baselines
(Panda3D 1.10.16 and simplepbr 0.13.1 at `C:\Python313\Lib\site-packages`),
not from memory.

**What stock Panda3D already has** (`direct/filter/CommonFilters.py`):
`setBloom`, `setAmbientOcclusion`, `setHighDynamicRange(tonemap=ACES)`,
`setExposureAdjust`, `setSrgbEncode`, `setGammaAdjust`, `setBlurSharpen`,
`setVolumetricLighting`, `setMSAA`, plus `DirectionalLight.setShadowCaster`
and two terrain classes (`GeoMipTerrain`, `ShaderTerrainMesh`).

**What simplepbr already has:** the PBR shader itself, normal/emission/
occlusion maps, hardware skinning, fog, a shadow bias scalar, SDR LUTs,
**SH irradiance from a cubemap** (`get_sh_coeffs_from_cube_map`) and
**GGX-prefiltered environment maps**. Pax3D's prefilter tool borrows
simplepbr's sampling math, and says so.

With that subtracted, the honest list divides three ways.

#### Tier 1 — capability absent from both baselines

| # | Feature | Nearest prior art |
|---|---|---|
| 1 | Aerial perspective / exponential height haze, with per-node scale | None. `p3d_Fog` is linear/exponential distance fog only |
| 2 | Orbital atmospheric scattering, per-planet analytic limb, halo, terminator, Rayleigh reddening | None |
| 3 | Terrain **splatting**: 4 layers via texture arrays, macro variation, analytic world TBN, detail-normal distance fade | None. Panda3D ships terrain *geometry and LOD*, no material system |
| 4 | Logarithmic depth buffer | None |
| 5 | Lens flare and lens dirt | None |
| 6 | Specular-preserving glass (alpha attenuates transmission only) | None. Standard transparency kills the specular term |
| 7 | Double-sided lighting via `gl_FrontFacing` normal flip | None. `doubleSided` exists as a material flag, but backfaces stay lit from the wrong side |
| 8 | Temporal antialiasing resolve | None |
| 9 | **World-unit** shadow bias | Stock exposes **no bias control at all**; simplepbr has one normalised scalar whose world effect scales with frustum depth |
| 10 | Slope-scaled / normal-offset shadow bias | None |
| 11 | Shadow texel snapping | None |
| 12 | PCF filter-size control | None |
| 13 | Shadow extent centring and camera-driven sizing | None |
| 14 | Per-node and per-subtree override system: ambient scale, atmosphere scale, environment binding, skinning path, shadow exclusion | None. Nothing upstream is addressable per subtree |
| 15 | Data-texture contract: immunity to the `texture-scale` prc and to driver compression | None. Upstream silently degrades data textures |
| 16 | Rebuild-safe auxiliary camera registration | None. Upstream's FilterManager orphans externally-attached cameras on rebuild |
| 17 | glTF loader compatibility shim fixing three real `panda3d-gltf` defects | None; the defects are live upstream |
| 18 | Model-authored light activation (KHR_lights_punctual) | The lights are converted but never activated |
| 19 | Content-sized bone palette with oversize audit | Fixed cap |
| 20 | FTL radial blur and chromatic aberration | None |
| 21 | Core-profile combine-mode warning (the 34 lines of C++) | None; the state was silently flattened |

#### Tier 2 — existed, but was inadequate and was replaced with a verified version

The capability was reachable before. The claim here is quality and
correctness, not novelty, and each is now pinned by an analytic test.

| Feature | What changed |
|---|---|
| Bloom | Stock's is an LDR filter chain. Pax3D's runs on float FBOs, after root-causing a silent 8-bit intermediate-FBO downgrade that produced quantisation banding indistinguishable from bad filtering |
| SSAO | Stock's `setAmbientOcclusion` exists. Pax3D's is depth-only Alchemy/SAO applied in the tonemap pass, with flat geometry guaranteed to return AO exactly 1.0 and byte-identity gated |
| Tonemapping and exposure | Stock offers ACES. Pax3D ships four operators, each verified against its analytic curve, which is how the "double gamma" myth was disproven |
| sRGB input linearisation | Stock encodes output. Pax3D linearises *inputs*, which was the actual cause of the ACES wash-out |
| Shadows generally | `setShadowCaster` renders a shadow map and nothing more. Items 9 to 13 above are what makes it usable at mixed scale |
| SH ambient and specular IBL | **simplepbr already had both.** Pax3D adds a hemisphere-ambient constructor, per-subtree binding, a pinned cubemap face orientation, and a real split-sum BRDF LUT with the roughness ladder proven end to end |
| PBR shading itself | Descends from simplepbr. Not a Pax3D invention |

#### Tier 3 — integration of an upstream 1.11 feature, not a Pax3D invention

**Hardware instancing** (`set_instanced`). `InstancedNode` is upstream's,
absent from 1.10.16 but present in the 1.11 base. Pax3D added the
`INSTANCING` define to both the PBR and shadow vertex shaders and the
shadow-caster state invalidation. Worth stating plainly because the
measurement is counter-intuitive: without the call the traverser renders
every instance correctly anyway, one draw each. `set_instanced` is a
**performance switch, not a correctness fix**.

#### The two deliverables that are not features at all

Neither has any upstream counterpart, and on the evidence of this
programme's history they matter more than most of Tier 1:

- **The paxtest harness.** 27 analytic tests over 5 pipelines and 2 GL baselines. It is what disproved two founding myths, root-caused the bloom defect, and repeatedly showed that externally-reported "engine regressions" were contaminated worktrees or bad instruments.
- **One graphics reality.** 43,338 lines and 10 subsystems removed, so there is exactly one code path to reason about.

---

## 3. Effort estimate for a conventional human team

Estimates are engineer-weeks of net productive work by an experienced
engineer already familiar with real-time rendering, but new to this
codebase. They include research, implementation, GPU debugging, validation,
tuning and API documentation.

### 3.1 Bottom-up

| Workstream | Eng-weeks | Basis |
|---|---|---|
| Renderer foundation (pipeline merge, camera registration, colour contract, recompile invariant, GLSL dual path) | 5.5 | |
| Sun and shadows, including the correctness long tail | 11 | Shadow mapping works in a week; bias across scale, grazing angles, skinned casters and two GLSL baselines is the rest |
| Bloom, HDR, tonemapping, sRGB, TAA, log depth, FTL post | 8.5 | |
| SSAO and lens flare/dirt | 3 | |
| Atmosphere: aerial perspective, per-node scale, orbital scattering | 5.5 | |
| Ambient and IBL: SH, hemisphere, cubemap derivation, env maps, BRDF LUT, GGX prefilter, per-subtree binding | 7 | |
| Material features: glass, double-sided, model lights, ambient scale | 4 | |
| Terrain splatting, instancing, data-texture contract | 7.5 | |
| Skinning, bone palette, glTF compat shim | 3 | |
| **Renderer subtotal** | **55** | |
| Test harness: infrastructure, 27 analytic tests, 6 probes | 18 | The cost is deriving each analytic expectation, not writing the test |
| Build bring-up, catch-up merge, 3 surgery windows, doubles variant, C++ warning, internals archaeology | 14 | |
| Documentation (89,000 words, code-cited, maintained) | 10 | |
| Field integration and triage: 2 downstream games, 5 formal response rounds, joint design sessions, engine requests | 8 | |
| Architecture, planning, phase gates, policy | 5 | |
| **Total** | **110** | |

Bottom-up range: **95 to 130 engineer-weeks**, roughly **2.0 to 2.5
engineer-years**.

### 3.2 The discovery tax

That figure assumes the team arrives at the right answers. This programme's
own history says they will not, at least not first time.

The March 2026 attempt on this codebase was reverted almost entirely. It
built post-processing on an unlit, unverified pipeline while chasing two
defects that did not exist: a supposed Panda3D `DirectionalLight` bug and a
supposed double-gamma bug in the tonemap chain. Both were later disproven
mechanically in a single harness session. That is a measured failed
iteration in this very repository, and it is the normal failure mode for
graphics work without an instrument.

Add **15 to 25%** for wrong paths, false leads and rework.

**Realistic total: 115 to 160 engineer-weeks, or 2.2 to 3.1 engineer-years.**

### 3.3 Calendar time

Suggested team shape:

| Role | FTE |
|---|---|
| Principal / lead graphics engineer | 1.0 |
| Senior graphics engineer | 1.0 |
| Senior C++ engine and build engineer | 0.6 |
| Tools and test engineer | 0.6 |
| Engineering manager / producer | 0.2 |
| **Total** | **3.4** |

135 engineer-weeks divided by 3.4 FTE gives about 40 weeks of ideal work.
Three factors stretch that:

1. **Ramp-up.** Panda3D is a large, thinly-documented C++ engine with a bespoke Python build system. Expect 4 to 8 weeks per engineer before real productivity in `panda/src/`.
2. **Serialisation.** The phase structure is not arbitrary. The colour contract must be right before IBL means anything; lighting must be correct before shadows; shadows before bloom is worth tuning. Parallelism is limited by genuine dependencies.
3. **Coordination.** Roughly 20% overhead at this team size.

**Calendar estimate: 10 to 14 months, central case 12 months.**

The alternative shape is one exceptional senior graphics engineer working
alone for about 2.5 years. That produces a more coherent result and costs
less in total, at the price of a bus factor of 1. It is, as section 5 shows,
precisely upstream Panda3D's shape.

---

## 4. Skills required

Ordered by how hard the skill is to hire, hardest first.

| Skill | Level | Why it is needed here |
|---|---|---|
| **Real-time rendering theory and practice** | Senior to principal | PBR (Cook-Torrance, GGX, split-sum), shadow mapping and its bias pathologies, SH irradiance, analytic atmospheric scattering, SSAO, TAA, HDR and tonemapping. This is the scarce skill and the whole programme rests on it |
| **Graphics test engineering** | Senior, rare | Deriving closed-form expectations for rendered output and building offscreen analytic verification. Most studios do golden-image diffing at best; very few engineers have done this |
| **Numerical and applied mathematics** | Senior | SH projection, BRDF integration, reference integrators, float-versus-double precision analysis at astronomical scale |
| **GLSL, cross-version** | Senior | Including 120 versus 330-core portability and a define-driven ubershader |
| **Large C++ codebase archaeology** | Senior | Reading and safely deleting from a ~500k-line engine. The Window 4 over-cut fixups show the failure mode |
| **Build engineering** | Senior | MSVC toolchains, a bespoke Python build system, CMake, thirdparty dependency wrangling, wheel packaging. A notorious time sink |
| **Asset pipeline / glTF** | Mid to senior | Blender exports, sparse accessors, morph targets, skinning, and diagnosing loader defects against ground truth |
| **Python systems and API design** | Mid to senior | The pipeline's 57-method public surface is consumed by two downstream teams |
| **Technical writing** | Mid to senior | 89,000 words at this density cannot be delegated to a non-engineer |

The combination is the difficulty. Rendering engineers who can also build a
rigorous analytic test harness, and who will then write the documentation,
are uncommon in any market and particularly so in Australia.

---

## 5. Benchmark: upstream Panda3D's actual development rate

Measured from the upstream remote in this repository, corroborated against
public sources.

| Metric | Value |
|---|---|
| Commits per year, recent baseline | ~300 (2023-25 mean 301; trend downward) |
| Engine lines added per year (`panda/`, `dtool/`, `direct/`) | ~17,000 to 30,000 |
| Share of commits by the lead maintainer (rdb) | 82% to 94% every year since 2021 |
| Authors exceeding 10 commits in the 7.5-year 1.11 cycle | 9 |
| Authors exceeding 50 commits | 2 |
| Project funding | ~USD 7,000/year (Open Collective, USD 51,429 total since Feb 2019) |
| Paid staff | None full-time. The 2019 sponsors post describes a *part-time* maintainer |
| **Effective FTE on the whole engine** | **1.0 to 1.5** |
| 1.11 development period | Version bumped 2019-01-07. **No stable 1.11 release, 7 years 6 months later.** Described publicly as 70% complete in April 2025 |
| Release cadence | Collapsed from 5/year (2019) to 1/year (2025), 0 in 2023 and 0 so far in 2026 |
| Bus factor | 1 |

Two things follow.

**First, the estimate cross-checks.** Upstream adds roughly 20,000 engine
lines a year at 1 to 1.5 FTE, including all maintenance, release engineering,
issue triage and review. Pax3D's ~16,900 lines of new first-party code plus
89,000 words of documentation plus a validated 43,000-line deletion
programme is, at upstream's demonstrated rate, on the order of two to three
years of the entire project's capacity. That agrees with the bottom-up
figure of 2.2 to 3.1 engineer-years derived independently in section 3.

**Second, the comparison has a sharp edge.** 83 of the fork's 86 commits
landed across four calendar days, 2026-07-16 to 2026-07-19. The new-code
output of those four days is roughly 80% of what upstream Panda3D adds to
the entire engine in a typical year.

A caveat on reading the 7.5-year figure: it reflects calendar time at
approximately 1 FTE with no deadline, not the intrinsic size of the work. It
should not be read as "a funded team would need 7.5 years for 1.11."

---

## 6. Costing

### 6.1 Australia, employed team

Fully loaded means base plus 12% superannuation, payroll tax, on-costs and
overhead, at approximately 1.35x base. 2026 market rates.

| Role | Base AUD | Loaded AUD | FTE | Annual AUD |
|---|---|---|---|---|
| Principal graphics engineer | 200,000 | 270,000 | 1.0 | 270,000 |
| Senior graphics engineer | 165,000 | 223,000 | 1.0 | 223,000 |
| Senior C++ engine / build | 170,000 | 230,000 | 0.6 | 138,000 |
| Tools and test engineer | 140,000 | 189,000 | 0.6 | 113,000 |
| Engineering manager / producer | 190,000 | 257,000 | 0.2 | 51,000 |
| **Team** | | | **3.4** | **795,000/yr** |

| Duration | Salary cost AUD |
|---|---|
| 10 months (optimistic) | 663,000 |
| 12 months (central) | 795,000 |
| 14 months (pessimistic) | 928,000 |

One-off and additional costs:

| Item | AUD |
|---|---|
| Recruitment (3-4 specialist hires, agency at 15-18% of base) | 90,000 to 120,000 |
| Hardware, tooling, licences | 25,000 to 35,000 |
| Contingency at 15% | ~120,000 |

**All-in: AUD 950,000 to 1,250,000. Central case approximately AUD 1.05M.**

Recruitment is not merely a line item. Senior graphics engineers are among
the hardest hires in the Australian market, where the games industry is
small. A 3 to 6 month search before the team is even assembled is realistic,
and is not included in the 12-month delivery estimate above.

### 6.2 Alternative delivery models

| Model | Cost | Notes |
|---|---|---|
| **Specialist rendering consultancy** | AUD 1.2M to 1.5M | 675 billable days at AUD 1,400-1,900/day. They bill ramp-up too |
| **Single exceptional senior engineer** | AUD 700,000 to 800,000 over ~2.5 years | Cheapest and most coherent; bus factor 1; slowest to deliver |
| **Offshore team** | AUD 400,000 to 600,000 nominal | Not recommended. Graphics specialists at this level are scarce in low-cost markets too, and a research-heavy programme with daily measure-and-decide loops carries high coordination cost |
| **US equivalent** | USD 900,000 to 1.2M | Senior graphics engineers at USD 190,000-260,000 base, loaded at ~1.35x |

---

## 7. What this estimate does and does not include

Stated plainly, because several of these cut against the headline number.

**Understatements in the estimate:**

- The programme's *information* is treated as free. A human team pays for it in the discovery tax, and 15-25% may be light for research-heavy rendering work.
- Recruitment lead time (3-6 months) is excluded from the calendar figure.
- The harness's 18 engineer-weeks look optional. They are not fungible: omitting the harness does not save 18 weeks, it moves the time into a longer and far less predictable debugging tail. The reverted March 2026 attempt is the evidence.

**Overstatements in the estimate:**

- **"First slice" scoping.** Many features are deliberately minimal, opt-in and default-off. SSAO is depth-only. Specular IBL landed as a first slice. Orbital scattering is single-scatter analytic, not Bruneton multi-scatter. A team briefed with "add SSAO" would be expected to deliver more than what is here. The estimate prices *equivalent delivered scope*, not the feature names.
- **Deleted lines are cheap per line.** The 43,338 removed lines are priced at roughly 4 engineer-weeks, not proportionally.
- **The catch-up merge's 38,229 insertions are upstream's work**, not the fork's. Only absorbing, conflict-resolving and validating them is fork effort.
- **Documentation at this density is atypical.** A conventional team would write perhaps 10% of it and carry the rest in people's heads. That saves ~9 engineer-weeks up front and costs far more at the first handover.

**Excluded entirely:**

- Downstream game integration work in `sfb2` and `openworld`, which is a separate programme.
- Ongoing maintenance after delivery.

---

## 8. Summary

| Question | Answer |
|---|---|
| What was modified | A complete first-party renderer (33 capability areas, 5,317 lines), an analytic graphics test harness with no upstream counterpart (10,410 lines, 27 tests), 43,338 lines of engine surgery removing 10 subsystems across 217 files, an upstream catch-up merge, a doubles build variant, 89,000 words of documentation, and 34 lines of new C++ |
| Effort for a human team | 115 to 160 engineer-weeks, or 2.2 to 3.1 engineer-years |
| Calendar time | 10 to 14 months with a 3.4 FTE team, central case 12 months, plus 3 to 6 months to recruit |
| Skills | Senior real-time rendering above all, plus graphics test engineering, applied maths, cross-version GLSL, large-codebase C++ archaeology, build engineering, glTF asset pipeline, Python API design, technical writing |
| Cost | **AUD 950,000 to 1,250,000 all-in, central case ~AUD 1.05M** (USD 900,000 to 1.2M equivalent) |
| Upstream benchmark | Panda3D runs on 1.0 to 1.5 effective FTE and ~USD 7,000/year, has not shipped 1.11 in 7.5 years, and adds ~20,000 engine lines a year. This body of work is on the order of two to three years of that project's entire capacity |
| Actual elapsed time | 83 of 86 fork commits landed in four calendar days |
