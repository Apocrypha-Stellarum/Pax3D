# CLAUDE.md — Pax3D Engine (Panda3D Fork + Rendering Stack)

Welcome, Claude! This is **Pax3D**: a fork of the Panda3D game engine plus a
first-party rendering stack, built for the Pax Abyssi space simulation.

> **This is an engine project, not a game project.** The game lives at
> `C:\python\sfb2` (it has its own CLAUDE.md). This repo contains:
> 1. The Panda3D C++ engine source (buildable to a wheel),
> 2. **`pax3d_render/`** — the unified Python/GLSL rendering pipeline (the
>    center of gravity of current work),
> 3. **`tools/paxtest/`** — the offscreen graphics test harness that gates
>    all rendering changes.

---

## Read These First

| Priority | Document | What it gives you |
|---|---|---|
| 1 | `documents/PAX3D_MASTER_PLAN.md` | The phased program (R0–R6), root-cause register, session log. **The current plan.** |
| 2 | `documents/PAX3D_RENDER_ARCHITECTURE.md` | How pax3d_render works: passes, sun modes, shadows, invariants, API. |
| 3 | `tools/paxtest/README.md` | How to run and extend the test harness. |
| 4 | `documents/README.md` | Index of all docs with current/historical status. |

For using the pipeline from the game side, the guide lives in the game repo:
`C:\python\sfb2\documents\PAX_3D_ENGINE_AND_GRAPHICS\USING_PAX3D_RENDER.md`.

---

## Project Status (July 2026)

The rendering program runs in gated phases (see the master plan):

| Phase | Content | Status |
|---|---|---|
| R0 | paxtest harness | **DONE** — gates everything below |
| R1 | Unified renderer (`pax3d_render`), color contract, camera registration | **Core done.** Remaining: in-game parity sign-off, sRGB input linearization rollout, drop GLSL-120 dual path |
| R2 | Real DirectionalLight sun + shadows | **Core done, harness-proven.** Remaining: game switches to directional mode; shadow extent at planetary scale |
| R3 | Bloom fixed + HDR polish | **NEXT.** Blocky-bloom defect reproduced and cornered (see F3 in the plan) |
| R4 | Log depth, camera-relative rendering, single camera | Not started |
| R5 | Atmospheric scattering, env-driven ambient, signature look | Not started |
| R6 | Engine hygiene (DX9 removal, upstream sync, Vulkan watch) | Ongoing, low priority |

**Engine C++ changes so far: one build-system fix.** Everything else is
Python/GLSL in `pax3d_render/`. The C++ fork earns its keep in R4 (log
depth) and targeted conveniences; do not start engine C++ work casually —
each change costs upstream-sync friction.

### Hard-won facts (do not re-litigate without new evidence)

These were established mechanically by the harness (Session A, 2026-07-16;
full analysis in `documents/PAXTEST_FINDINGS_SESSION_A.md`):

- **There is no Panda3D DirectionalLight engine bug.** A real
  DirectionalLight lights every current mesh type correctly. The 2025-era
  "bug" was mesh winding + NaN tangents + API confusion. Older docs (both
  repos) that say otherwise are wrong.
- **There is no double-gamma bug in the tonemap chain.** All operators match
  their analytic curves exactly. ACES looks washed out because *inputs* are
  not linearized (sRGB textures sampled raw) and content was tuned around
  Hejl-Dawson.
- **The blocky bloom is real and reproducible** at any resolution —
  truncation is ruled out; suspects are buffer filter state, the
  upsample-pass design, and a half-texel Y offset.

---

## The Working Method (non-negotiable)

1. **Verify with the harness, not by launching the game.**
   ```bash
   C:/Python313/python.exe tools/paxtest/run.py                 # stock engine
   C:/python/pax3d-env/Scripts/python.exe tools/paxtest/run.py  # Pax3D engine
   ```
   Run the relevant tests before AND after any rendering change. If a claim
   about rendering behavior matters, write a paxtest check for it — that is
   how every "mystery bug" here has been killed.

2. **Rendering fixes land in `pax3d_render/` and only there.** The game's
   `graphics/pax_pbr/` is the legacy copy kept for A/B; `pax3d_simplepbr/`
   is retired. Never fork the pipeline again — divergent copies caused the
   failed March 2026 effort.

3. **Eyeball with the testbed, not the full game.**
   `C:\python\sfb2\test3d_pax.py` gives a sun/planet/station/ships scene in
   seconds with hotkeys for every feature (`--pax3d --sun-mode directional
   --shadows`, `--selftest` for automated screenshots).

4. **Respect the phase gates.** Bloom work (R3) was blocked until lighting
   (R2) passed for a reason. Check the master plan before starting work
   that belongs to a later phase.

5. **Keep behavior changes opt-in until proven.** The game adopts new
   pipeline behavior via flags (`use_pax3d_render`, `sun_light_mode`), with
   the old path selectable for A/B until the new one is signed off.

---

## Repository Map

| Path | What | Status |
|---|---|---|
| `pax3d_render/` | **The unified rendering pipeline.** Pipeline class, camera registration, sun modes, shadows. | Active — all rendering work happens here |
| `pax3d_render/shaders/` | GLSL sources (PBR, bloom, tonemap, TAA, shadow) | Active |
| `tools/paxtest/` | Offscreen test harness: gamma, lighting, bloom, rebuild, shadows | Active — extend when adding features |
| `pax3d_simplepbr/` | March-2026 simplepbr fork | **Retired** — reference only, merged into pax3d_render |
| `panda/src/` | Engine C++ (~65 modules; `glstuff/` is the GL backend, `pgraphnodes/` has the light classes) | Unmodified upstream 1.11.0-dev |
| `makepanda/` | Build system | One committed fix (`oscmd` ignoreError) |
| `documents/` | Planning docs, findings, guides — see `documents/README.md` | Mixed current/historical |
| `doc/` | Upstream Panda3D docs (CODING_STYLE, INSTALL) | Upstream |

---

## Building the Engine (only needed for C++ changes)

Python/GLSL work in `pax3d_render/` needs **no engine build** — it runs on
whatever `panda3d` is installed. Build only when touching `panda/src/`.

```bash
cd C:/python/pax3d
C:/Python313/python.exe makepanda/makepanda.py \
    --everything --no-dx9 --no-fmod --no-ffmpeg --no-fftw --no-opencv \
    --windows-sdk 10 --threads 8 --wheel

# Install into the Pax3D venv:
source C:/python/pax3d-env/Scripts/activate
pip install --force-reinstall panda3d-*.whl
```

Critical pitfalls (full detail in `documents/BUILDING_PAX3D.md`):
1. **ALWAYS pass `--windows-sdk 10`** — SDK 8.1 is present but broken.
2. **Thirdparty libraries are not in the repo** — see the build doc.
3. **Use system Python, never `makepanda.bat`.**
4. **Delete `built_x64/` after failed builds** — the dep cache corrupts.

## Environments

| Environment | Python | Engine | Use for |
|---|---|---|---|
| System Python | `C:\Python313\python.exe` | Stock Panda3D 1.10.16 | paxtest cross-checks, quick runs |
| Pax3D venv | `C:\python\pax3d-env\` | Pax3D 1.11.0 custom wheel | **The game's default engine**; engine-build testing |

The game (`plan.py`) and testbed run under either; paxtest runs under both —
identical results on both is itself a useful signal (defect is in Python/GLSL,
not C++). See `documents/SWITCHING_ENGINES.md`.

---

## Conventions

- C++: follow upstream (`doc/CODING_STYLE.md`); tag every Pax3D change with
  a `// PAX3D:` comment and list it in this file's change table when it lands.
- Python: the pipeline is plain, dependency-light code — keep it that way
  (no game imports in `pax3d_render/`; debug via `PAX3D_RENDER_DEBUG` env
  var or `debug=True`).
- Don't break the game's API surface: `from graphics.pax_pbr import init`
  must keep working (it routes here via the settings flag). Add, don't rename.
- Keep upstream sync possible: focused diffs, no drive-by reformatting of
  engine code.
- Commit style: one logical change per commit; note the phase (e.g.
  "Session C / R2") in the subject.

## Upstream Relationship

| | |
|---|---|
| Upstream | `panda3d/panda3d` (GitHub) |
| Our fork | `Apocrypha-Stellarum/Pax3D` |
| Last sync | 2026-02-26 (`2d2bdc9a`), upstream 1.11.0-dev |
| Sync cadence | Quarterly while C++ divergence is small (R6) |

```bash
git fetch upstream && git merge upstream/master
```

---

## History in One Paragraph

Forked Feb 2026 to fix "the DirectionalLight problem" and add bloom/HDR. The
March effort built post-processing on an unlit, unverified pipeline and was
reverted almost entirely (Session 459 in the game repo). July 2026 rebooted
the program with a test harness first: the harness disproved both founding
myths (engine light bug, double gamma), reproduced the real bloom defect,
and then R1/R2 landed in quick succession — one unified pipeline, a real
DirectionalLight sun with working shadows, all harness-proven. The lesson
that must survive: **measure first, then build.**
