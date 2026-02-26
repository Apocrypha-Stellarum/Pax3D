# CLAUDE.md - Pax3D Engine (Panda3D Fork)

Welcome, Claude! This is **Pax3D**, a fork of the Panda3D game engine customised for the Pax Abyssi space simulation. The goal: modernise the rendering pipeline, fix long-standing lighting pain points, and add features that Pax Abyssi needs but stock Panda3D doesn't provide.

> **This is an engine project, not a game project.** The game lives at `C:\python\sfb2`. This repo is C++ and Python engine internals. Changes here produce a wheel that replaces the `panda3d` pip package.

---

## Project Status

**Phase: Fresh Start (Feb 2026)**

The repo was forked from `panda3d/panda3d` in August 2025 and synced to upstream master (commit `2d2bdc9a`, Feb 16 2026). All three branches (`master`, `main`, `dev`) are currently identical to upstream. No Pax3D-specific changes have been pushed yet.

Previous local experiments (DirectX 9 removal, ~6 months ago) were never committed to this repo and are considered abandoned. We are starting fresh.

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
| **Built-in bloom & HDR** | Currently hacked via simplepbr — should be engine-native |
| **Remove DirectX 9** | Dead weight. Focus on OpenGL 4.x+ (and eventually Vulkan) |
| **Improve large-scale rendering** | Better support for astronomical distances (near/far plane, precision) |
| **Shader modernisation** | Move from the fixed-function/Cg legacy toward pure GLSL |

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

## Build System

Panda3D has two build systems. We will use **makepanda** (the legacy one) initially as it's what produces pip-installable wheels:

### Building a Wheel (Windows)

```bash
cd C:\python\pax3d

# Full build with OpenGL, no DirectX 9 (our target configuration)
python makepanda/makepanda.py --everything --no-dx9 --threads=8 --wheel

# The wheel lands in the pax3d root directory
# Install into the Pax3D venv:
C:\python\pax3d-env\Scripts\pip.exe install --force-reinstall panda3d-*.whl
```

### Build Requirements (Windows)
- **Visual Studio 2019 or 2022** with C++ Desktop workload
- **Windows SDK** (for platform headers)
- **Python 3.13** (matching the game's Python)
- Third-party libs are bundled or auto-downloaded by makepanda

### CMake Alternative
```bash
mkdir build && cd build
cmake .. -DBUILD_TESTS=ON
cmake --build . --config Release
```

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

### Phase 1: DirectX 9 Removal
- [ ] Remove `panda/src/dxgsg9/` (~35 files, ~604 KB)
- [ ] Remove `panda/metalibs/pandadx9/`
- [ ] Clean build system references (makepanda + CMake)
- [ ] Verify clean build with `--no-dx9` flag (should already work)

### Phase 2: Lighting Pipeline Improvements
- [ ] Audit `DirectionalLight` → understand shadow mapping lens setup
- [ ] Investigate simplepbr integration points (where engine ends and simplepbr begins)
- [ ] Design improved directional light workflow for astronomical-scale scenes
- [ ] Prototype bloom as engine-native post-process

### Phase 3: Shader Modernisation
- [ ] Audit Cg shader dependencies — can they be removed?
- [ ] Improve GLSL auto-shader generation (`shaderGenerator.cxx`)
- [ ] Better PBR defaults in the material system

### Phase 4: Large-Scale Rendering
- [ ] Logarithmic depth buffer support
- [ ] Improved near/far plane management for space scenes
- [ ] Double-precision vertex positions (or camera-relative rendering)

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
