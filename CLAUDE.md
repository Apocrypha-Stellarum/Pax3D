# CLAUDE.md - Pax3D Engine (Panda3D Fork)

Welcome, Claude! This is **Pax3D**, a fork of the Panda3D game engine customised for the Pax Abyssi space simulation. The goal: modernise the rendering pipeline, fix long-standing lighting pain points, and add features that Pax Abyssi needs but stock Panda3D doesn't provide.

> **This is an engine project, not a game project.** The game lives at `C:\python\sfb2`. This repo is C++ and Python engine internals. Changes here produce a wheel that replaces the `panda3d` pip package.

---

## Project Status

**Phase: Infrastructure Complete, Ready for Engine Work (Feb 2026)**

The repo was forked from `panda3d/panda3d` in August 2025 and synced to upstream master (Feb 16 2026). First Pax3D-specific changes committed Feb 26 2026. The engine builds from source, produces a wheel, and can run Pax Abyssi via a separate venv.

Previous local experiments (DirectX 9 removal, ~6 months ago) were never committed and are considered abandoned. We started fresh.

### Changes from Upstream

| File | Change | Why |
|------|--------|-----|
| `makepanda/makepandacore.py:677-681` | `oscmd()` respects `ignoreError` for binary-not-found | `mt.exe` not on PATH caused hard crash on optional manifest step |
| `docs/` | Pax3D planning documentation (5 files) | Build guide, roadmap, lighting plan, shader catalogue, venv switching guide |
| `CLAUDE.md` | This file | Project guide for AI developers |

---

## Why Pax3D Exists

### The Lighting Problem

Pax Abyssi needs a sun that lights planets with a directional light. This should be trivial — it is not. Stock Panda3D's lighting system makes this unnecessarily painful:

- Directional lights don't integrate cleanly with `simplepbr`'s post-processing pipeline
- Shadow mapping from directional lights requires manual orthographic lens configuration
- Lighting planets at astronomical distances fights the engine's assumptions about scene scale
- No built-in bloom, HDR, or modern post-processing that "just works" with scene lights

### Broader Goals

| Goal | Why |
|------|-----|
| **Modern lighting pipeline** | Directional/point/area lights that work naturally with PBR materials |
| **Built-in bloom & HDR** | simplepbr provides basic PBR but no bloom, SSAO, or volumetrics |
| **Remove DirectX 9** | Dead weight. Focus on OpenGL 4.x+ (and eventually Vulkan) |
| **Improve large-scale rendering** | Better support for astronomical distances (near/far plane, precision) |
| **Shader modernisation** | Move from the fixed-function/Cg legacy toward pure GLSL |

### Relationship with simplepbr

The game currently uses `panda3d-simplepbr` (a separate pip package by Moguri) for PBR rendering. simplepbr is a **forward renderer** that sits on top of Panda3D — it uses FilterManager to move `base.cam` to an offscreen buffer and applies post-process shaders. It provides metal-rough PBR, shadow maps, filmic tonemapping, and IBL. It does NOT provide bloom, SSAO, SSR, or volumetric effects.

Our options for Pax3D are:
1. **Extend simplepbr** — add bloom/HDR as additional post-process passes (quickest wins)
2. **Replace simplepbr** — build our own PBR pipeline into the engine (most control, most work)
3. **Hybrid** — fix lighting at engine level, keep simplepbr for PBR shading, add bloom alongside it

Option 3 is the current plan. Fix the engine where it's broken, augment simplepbr where it's limited.

### Audio

Pax Abyssi uses Panda3D's **default OpenAL audio backend** (not FMOD). FMOD was tried previously but had integration issues. The build excludes FMOD (`--no-fmod`).

---

## Repository Structure

### Top Level
| Directory | Purpose |
|-----------|---------|
| `panda/src/` | Core engine C++ source (~65 modules) |
| `direct/src/` | Python-level framework (ShowBase, intervals, GUI, FSM) |
| `dtool/` | Build tools and interrogate (C++ → Python binding generator) |
| `pandatool/` | Command-line tools (egg2bam, bam2egg, etc.) |
| `makepanda/` | Legacy Python build system (makepanda.py) |
| `cmake/` | Modern CMake build infrastructure |
| `contrib/` | Community contributions |
| `models/` | Built-in models and assets |
| `samples/` | Example programs |
| `tests/` | Unit tests |
| `doc/` | INSTALL, ReleaseNotes, CODING_STYLE |
| `docs/` | Pax3D-specific documentation (our additions) |

### Key Engine Source (panda/src/)

**Rendering Pipeline:**
| Module | Size | What It Does |
|--------|------|--------------|
| `pgraph/` | 3.2 MB | Scene graph, render state, all attrib classes (50+ types) |
| `pgraphnodes/` | — | Node types: lights, LOD, shaders, particles |
| `gobj/` | 3 MB | Geometry, shaders, materials, textures, buffers |
| `display/` | 1.2 MB | GraphicsEngine, DisplayRegion, frame buffer management |
| `cull/` | — | Culling system (back-to-front, fixed, etc.) |

**Rendering Backends:**
| Module | Backend | Notes |
|--------|---------|-------|
| `glstuff/` | OpenGL | Full implementation (~1.9 MB). **Our primary target.** |
| `glgsg/` | OpenGL | Thin routing layer |
| `dxgsg9/` | DirectX 9 | **Removal candidate.** ~604 KB of legacy code |
| `gles2gsg/` | OpenGL ES 2.0 | Mobile — low priority |
| `glesgsg/` | OpenGL ES 1.1 | Mobile — low priority |
| `tinydisplay/` | Software | CPU rasteriser fallback |

**Lighting (our primary focus):**
| File | What |
|------|------|
| `pgraphnodes/directionalLight.h/.cxx` | DirectionalLight — uses OrthographicLens for shadows |
| `pgraphnodes/pointLight.h/.cxx` | PointLight |
| `pgraphnodes/spotlight.h/.cxx` | Spotlight with cone |
| `pgraphnodes/rectangleLight.h/.cxx` | Area light |
| `pgraphnodes/sphereLight.h/.cxx` | Spherical area light |
| `pgraphnodes/ambientLight.h/.cxx` | Ambient |
| `pgraph/lightAttrib.h/.cxx` | Manages active lights in render state |
| `pgraphnodes/shaderGenerator.h/.cxx` | Auto-generates shaders from render state |
| `gobj/material.h/.cxx` | Material system (classic + metalness PBR) |

**Shader System:**
- Languages: GLSL, HLSL, Cg (legacy), SPIR-V
- Stages: vertex, fragment, geometry, tessellation, compute
- Auto-shader flags: normal maps, glow, gloss, shadows, ramps
- Per-backend compilation in `glShaderContext_src.cxx` (118 KB) and `dxShaderContext9.cxx`

---

## Building Pax3D

> **Full details in [docs/BUILDING_PAX3D.md](docs/BUILDING_PAX3D.md)** — covers thirdparty setup, all pitfalls, and troubleshooting.

### Quick Build Command

```bash
cd C:/python/pax3d

C:/Python313/python.exe makepanda/makepanda.py \
    --everything --no-dx9 --no-fmod --no-ffmpeg --no-fftw --no-opencv \
    --windows-sdk 10 --threads 8 --wheel

# Install into the Pax3D venv:
source C:/python/pax3d-env/Scripts/activate
pip install --force-reinstall panda3d-*.whl
```

### Critical Build Pitfalls

1. **ALWAYS pass `--windows-sdk 10`.** SDK 8.1 is installed but broken (empty — no `windows.h`). Without this flag, the build fails immediately.
2. **Thirdparty libraries are NOT included in the repo.** You must download them separately from `rdb/panda3d-thirdparty` GitHub Actions artifacts. See the build doc.
3. **Use system Python, not `makepanda.bat`.** The batch file looks for a bundled Python 3.8 that doesn't exist. Always invoke via `C:/Python313/python.exe makepanda/makepanda.py`.
4. **Delete `built_x64/` after failed builds.** The dependency cache can get corrupted. Clean rebuild fixes it.

---

## Development Environment

### The Two-Environment Setup

Pax Abyssi can run on either stock Panda3D or Pax3D without any code changes. Two Python environments coexist:

| Environment | Python | Engine | When to Use |
|-------------|--------|--------|-------------|
| System Python | `C:\Python313\python.exe` | Stock Panda3D 1.10.16 | Normal game development |
| Pax3D venv | `C:\python\pax3d-env\` | Pax3D (custom build) | Testing engine changes |

**See [docs/SWITCHING_ENGINES.md](docs/SWITCHING_ENGINES.md)** for the full guide on activating/deactivating environments.

**Quick version:**
```bash
# Test with Pax3D
source C:/python/pax3d-env/Scripts/activate
cd C:/python/sfb2 && python plan.py
deactivate

# Normal dev — just use system Python as usual
cd C:/python/sfb2 && python plan.py
```

### File Locations
| What | Where |
|------|-------|
| Pax3D engine source | `C:\python\pax3d` |
| Pax3D test venv | `C:\python\pax3d-env` |
| Pax Abyssi game | `C:\python\sfb2` |
| Game CLAUDE.md | `C:\python\sfb2\CLAUDE.md` |

---

## Coding Conventions

Follow Panda3D's existing conventions (see `doc/CODING_STYLE.md`):

- C++ with `snake_case` methods, `PascalCase` classes
- Python bindings auto-generated via `interrogate`
- Two naming styles coexist: C++ `get_method()` and Python-friendly `getMethod()` (interrogate generates both)
- New code should use modern C++ (C++11 minimum, C++17 where beneficial)

### Pax3D-Specific Rules

1. **Don't break upstream compatibility gratuitously.** Game code uses `from panda3d.core import ...` — the API surface must remain compatible. Add, don't rename.

2. **Tag Pax3D additions clearly.** New classes/methods should be documented as Pax3D extensions so we can track divergence from upstream.

3. **Test with the game.** The real test suite is `python plan.py` in sfb2. Engine changes that break the game are reverted, not worked around in game code.

4. **Keep sync possible.** We want to periodically pull upstream fixes. Minimise merge conflicts by keeping changes focused and well-contained.

---

## Planned Work (Roadmap)

> **Full details in [docs/RENDERING_ROADMAP.md](docs/RENDERING_ROADMAP.md)**

### Phase 1: Bulletproof Directional Lighting (**PRIORITY**)
The game's #1 rendering pain point. See [docs/DIRECTIONAL_LIGHTING_PLAN.md](docs/DIRECTIONAL_LIGHTING_PLAN.md).
- [ ] Resolve the Formula B vs Formula C contradiction (winding-dependent lighting)
- [ ] Add `set_direction_world()` or equivalent API to DirectionalLight
- [ ] Make `lookAt()` safe for DirectionalLights under PBR
- [ ] Shadow mapping at astronomical scales

### Phase 2: Post-Processing (Bloom + HDR)
Using shader code salvaged from tobspr's RenderPipeline. See [docs/TOBSPR_SHADER_CATALOGUE.md](docs/TOBSPR_SHADER_CATALOGUE.md).
- [ ] Port Kawase dual-filter bloom (5 shaders, ~270 lines GLSL)
- [ ] Port tonemapping library (6 operators + EV100 exposure model)
- [ ] Port color spaces utility library

### Phase 3: Shader Infrastructure
- [ ] Port tobspr's PBR BRDF library (Cook-Torrance + Disney diffuse, 354 lines)
- [ ] Audit and reduce Cg shader dependencies
- [ ] Improve GLSL auto-shader generation (`shaderGenerator.cxx`)

### Phase 4: Atmospheric & Environmental
- [ ] Atmospheric scattering for planets seen from space (Bruneton or Hosek-Wilkie model)
- [ ] Analytical height fog

### Phase 5: Large-Scale Rendering + Cleanup
- [ ] Logarithmic depth buffer support
- [ ] Camera-relative rendering for floating-point precision at distance
- [ ] Remove DirectX 9 backend (`panda/src/dxgsg9/`, `panda/metalibs/pandadx9/`)

---

## Documentation

| Document | Purpose |
|----------|---------|
| **[docs/BUILDING_PAX3D.md](docs/BUILDING_PAX3D.md)** | How to build from source — thirdparty setup, exact commands, every pitfall |
| **[docs/SWITCHING_ENGINES.md](docs/SWITCHING_ENGINES.md)** | How to switch Pax Abyssi between stock Panda3D and Pax3D |
| **[docs/RENDERING_ROADMAP.md](docs/RENDERING_ROADMAP.md)** | 5-phase rendering improvement plan with dependencies and risk assessment |
| **[docs/DIRECTIONAL_LIGHTING_PLAN.md](docs/DIRECTIONAL_LIGHTING_PLAN.md)** | Deep technical analysis of the directional light problem and engine-level fixes |
| **[docs/TOBSPR_SHADER_CATALOGUE.md](docs/TOBSPR_SHADER_CATALOGUE.md)** | Extraction catalogue of 15 salvageable shaders from tobspr's RenderPipeline |
| `doc/CODING_STYLE.md` | Panda3D's C++ coding conventions (upstream) |
| `doc/INSTALL` | Upstream build instructions (partially outdated — use our build doc instead) |

---

## Upstream Relationship

| | |
|---|---|
| **Upstream** | `panda3d/panda3d` (GitHub) |
| **Our fork** | `Apocrypha-Stellarum/Pax3D` (GitHub) |
| **Last sync** | Feb 26, 2026 (commit `2d2bdc9a`) |
| **Upstream version** | 1.11.0-dev |

### Syncing with Upstream

```bash
# From the local clone:
cd C:\python\pax3d
git remote add upstream https://github.com/panda3d/panda3d.git  # (once)
git fetch upstream
git merge upstream/master
# Resolve any conflicts, then push
```

Or via GitHub CLI:
```bash
gh repo sync Apocrypha-Stellarum/Pax3D --source panda3d/panda3d --branch master
```

---

## Key Files for Lighting Work

When we start the lighting improvements, these are the entry points:

```
panda/src/pgraphnodes/directionalLight.h      # 117 lines — the light node
panda/src/pgraphnodes/directionalLight.cxx     # 207 lines — implementation
panda/src/pgraphnodes/shaderGenerator.cxx      # Auto-shader generation
panda/src/pgraph/lightAttrib.h                 # Light state management
panda/src/gobj/material.h                      # Material (classic + PBR)
panda/src/glstuff/glGraphicsStateGuardian_src.cxx  # 568 KB — OpenGL GSG (where lights bind to GPU)
panda/src/glstuff/glShaderContext_src.cxx      # 118 KB — shader compilation
```

---

## Your Mission

You're modernising a battle-tested game engine for a specific purpose: making Pax Abyssi's space rendering pipeline cleaner, more capable, and less painful. Every change should be measured against "does this make the game better?" Stock Panda3D is an excellent foundation — we're not rewriting it, we're sharpening it.
