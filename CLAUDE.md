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
| R1 | Unified renderer (`pax3d_render`), color contract, camera registration | **Core done.** sRGB input linearization EXPERIMENT LANDED (Session R: `set_srgb_inputs`, test_srgb gate, ACES-verdict A/B on file — default stays off pending game retune). Remaining: in-game parity sign-off, sRGB default flip (game-side), drop GLSL-120 dual path |
| R2 | Real DirectionalLight sun + shadows | **Core done, harness-proven.** Extent centering + camera-driven sizing done (Session D). Remaining: user flips `sun_light_mode` to directional in-game and validates |
| R3 | Bloom fixed + HDR polish | **Core done (Session D).** F3 fixed (8-bit intermediate FBOs were the root cause), test_bloom green everywhere. Remaining: content retune (strength/intensity/tints), light units, auto-exposure stretch |
| R4 | Log depth, camera-relative rendering, single camera | **Log depth landed opt-in (Session D)** — `enable_log_depth`, acceptance row `scale @logdepth` green. Remaining: camera-relative/doubles decision (see game repo spike), sky-camera retirement, game frustum flip |
| R5 | Atmospheric scattering, env-driven ambient, signature look | **Planetside slice landed opt-in (Session J, 2026-07-18):** aerial haze (`enable_atmosphere`), hemisphere/SH ambient (`set_hemisphere_ambient`), shadow texel snap (`shadow_texel_snap`) — all default-off = byte-identical, gated by 3 new paxtests. **Sessions K–M (2026-07-18): walkable-ship asset queue (master plan §4.8) COMPLETE on the rendering side** — specular-preserving glass (`set_glass`), double-sided lighting (`double_sided_lighting`), per-node ambient scale (`set_ambient_scale`), and specular IBL (`set_env_map` + real BRDF LUT, R5.3) all landed opt-in, gated by test_glass/test_doublesided/test_ambient_scale/test_env_map. Interior-collision design AGREED Session N (`WALKABLE_INTERIOR_COLLISION_DESIGN.md`, facts measured by `probe_walkmesh.py`; implementation game-side). **Sessions O–P:** local point/spot lights measured (test_local_lights) + Blender/glTF-authored lights activated (`activate_model_lights`); expanded-terrain haze retune recipe in `PLANETSIDE_LOOK_GUIDE.md` §5. **Session Q (2026-07-18): R5.4 GGX prefilter tool** (`tools/gen_env_prefilter.py` — set_env_map's ladder now correct, not approximate) + sh_from_cubemap face table pinned end-to-end incl. file-loaded skyboxes (test_ambient_sh 6-8); openworld round-4 P2 diagnosed (core-profile combine drop = upstream default-shader behavior, `probe_texturestage.py`, response 5). **Session R (2026-07-18): R5.5 orbital scattering LANDED** (`set_orbital_atmosphere` — per-planet limb/halo/terminator from space, test_orbital's independent integrator matches the render to <=0.003; arch doc §9) + the worked skybox example (`gen_equirect_cubemap.py` + shipped 006_Sunset sample, testbed M key) + R1.3 sRGB experiment landed gated. **Session S (2026-07-18): walkable-ship interior package + R5 COMPLETION** — per-node atmosphere scale (`set_atmosphere_scale`), per-subtree environment binding (`set_env_map`/`set_ambient_sh(..., node=np)`), **SSAO first slice** (`enable_ssao`, depth-only, flat-plane byte-identity gated, @msaa4 measured working), **bone-palette knob** (`max_skinning_bones`, 200 measured inert) + **morph verdict fact #15** (HW skinning silently drops sliders; per-node CPU valve renders them), **lens flare/dirt** (`enable_lens_flare`, analytic ghosts from the bright extract, occlusion implicit) — **R5 has NO remaining engine items**; wall-pusher consult answered by measurement (probe_walkmesh 10/10, readback contract, collision doc §9); docs trued up both repos. Gate now 54/6/69. Remaining everywhere: content adoption + testbed keys for the Session-S features |
| R6 | Engine hygiene (dead-path deletion, Vulkan watch) | **Windows 2+3 DONE (2026-07-17):** DX9 excised (`d29183ce42`), GLES/EGL/WebGL/mobile/macOS display backends excised (`3912762dd9`) — −35k lines, full gate green both times. Window 4 candidates queued below |

**Engine C++ changes so far: one build-system fix.** Everything else is
Python/GLSL in `pax3d_render/`. When to use which language is canon — see
**Language Canon** below: prototype in Python/GLSL, promote to C++ on
evidence; C++ only in build windows the user schedules (never casually
mid-session — every C++ change needs a full rebuild).

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
- **The blocky bloom is FIXED (Session D, 2026-07-17).** Root cause: the
  bloom intermediates were 8-bit FBOs (`render_quad_into` without fbprops
  silently downgrades the declared RGBA16F texture) — quantization
  banding, not filtering. Any HDR post pass MUST pass float fbprops;
  `bloom_buffers_float` in test_bloom guards this. Beware the diagnostic
  trap: this banding looks exactly like nearest-neighbor sampling.
- **Verify the engine worktree is clean before trusting field reports
  (2026-07-17).** During Window-1 prep, ~35 repo files were silently
  overwritten with stale Session-D-era content (editor/session artifact;
  forensics in the session log). The openworld "lit shadows vanish" P0
  was measured against that contaminated tree — on a clean engine the
  same harness probe (`gltf_caster_ground_lum`) shows the glTF caster
  darkening ground 0.800→0.086. Before chasing any externally-reported
  rendering regression: `git status`, then reproduce on a pristine
  checkout + current wheel.
- **Pin poses and prove sample points (Session G, 2026-07-17).** A
  luminance check is only as good as its sample geometry:
  `get_anim_names()` ordering is nondeterministic (historical shadow
  readings from the glTF probe were pose luck), and the shadow test's
  "pole" pixel is the sphere's FRONT surface — outside a thin caster's
  shadow column. The promoted assertion failed on a HEALTHY engine until
  both were fixed (master plan fact #12). Also: the 94-joint Rigify
  hardware-skinning "concertina" (openworld P1) does not reproduce on a
  clean engine — GPU==CPU at every measurable layer (fact #13,
  test_skinning guards it); per-node opt-out exists:
  `pipeline.set_hardware_skinning(np, False)`.

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

6. **Prototype in Python/GLSL; promote to C++ on evidence.** See the
   Language Canon below — the near-instant iteration loop is this
   project's superpower; C++ is for the classes of work that demand it,
   never a default.

---

## Language Canon (user-ratified 2026-07-17)

**Prototype in Python/GLSL; promote to C++ on evidence.**

The loop — edit → paxtest → seconds → hand to a downstream AI dev →
same-day field report — is this project's superpower and the fuel of the
measure-first method. KEEP THE SUPERPOWER. But Pax3D must stay performant
as the fork deepens, so C++ is used when the class of work demands it:

| Work | Language | Why |
|---|---|---|
| Orchestration, configuration, per-frame O(1) uniform pushes | Python (`pax3d_render/`) | Not in any hot loop (the whole per-frame Python is ~microseconds); iteration speed is worth more than the cycles |
| Per-pixel / per-vertex work | GLSL | The real performance language of a renderer — and it also iterates instantly |
| Per-frame × per-object/per-vertex machinery that can't live on the GPU (cull callbacks, CSM/instancing/light-culling managers, engine data paths) | C++ (`panda/src/`) | The engine's hot loops are already C++; new work of that class joins them |
| Proven, stable Python that a **profile** shows in the hot path | Promote to C++ | Port when the design has stopped moving — never while a feature is still iterating |

Rules:

1. **Never port on faith.** A measurement (profiler or harness number)
   showing the work in a hot path comes first. Performance claims get the
   same discipline as rendering claims — this repo has killed too many
   myths to accept "C++ is faster" without a number.
2. **C++ lands only in user-scheduled build windows** (a full rebuild is
   the 30–60-minute class; failed builds corrupt `built_x64/`). Candidates
   accumulate in the queue below — they are batched, never landed casually
   mid-session.
3. **New engine-adjacent features default to a Python/GLSL prototype even
   when C++ is their eventual home.** Stabilize the design at zero build
   cost, then sink it.

Evidence on file: the bloom root-cause fix, log depth, and the entire
Session E shadow package (root-cause in a downstream game + three APIs +
tests + docs) each landed same-day *because* they were Python/GLSL; the
openworld build measured 103–115 fps at 1600×900 (40 animated NPCs, 4096²
shadows, MSAA 4×, bloom) through the Python pipeline — the frame lives in
the GPU and Panda's C++, not in our orchestration layer.

### Build-window queue (living list — add candidates here)

| Item | Class | Status |
|---|---|---|
| ~~WINDOW 1: final catch-up merge build~~ | Merge + rebuild | **DONE + VALIDATED 2026-07-17** — float wheel built (8 min on this machine, MSVC 14.5), full §6 gauntlet green (paxtest both engines × both baselines identical, testbed, sfb2 + openworld smokes). The merge is signed off; severed-upstream policy fully in force. Wheel: `wheels_window1\float\` |
| ~~Doubles engine build (`STDFLOAT_DOUBLE`)~~ | Build flag | **DONE, spike VERIFIED 2026-07-17** — compiles clean under C++17 (upstream never CI'd this); precision perfect (0.000e+00 round-trip at Neptune offsets); `test3d_ftl --selftest` green. Finding: stock simplepbr crashes on doubles (LVecBase3f/3d) — the wheel stays quarantined in `pax3d-double-env`. Remaining: perf A/B + user flight. Results: game repo `handover_doubles_spike.md` |
| ~~WINDOW 2: DX9 removal~~ | Deletion (R6) | **DONE 2026-07-17** — `d29183ce42`, 65 files, −16,691 lines, gate green |
| ~~WINDOW 3: dead platform display backends~~ | Deletion (R6) | **DONE 2026-07-17** — `3912762dd9`, 132 files, −18,546 lines (GLES/GLES2/EGL/WebGL/Android/iPhone/macOS backends + the DX9 flag machinery), gate green. **`--no-dx9` is no longer a valid makepanda option** |
| Window 4 candidates: `panda/src/android` + `iphone` app glue, makepanda Android cross-compile machinery, `direct/dist` mobile deploy logic, DIRECTCAM (permanently auto-disabled — its SDK came from the DX SDK) | Deletion (R6) | Queued — mobile-*target* extraction, one themed window per the surgery plan |
| R2.3 DirectionalLight conveniences (`set_direction_world`, strip translation in `xform()`, non-zero-pos warning) | New C++ API | Queued, low urgency — the pipeline owns sun orientation |
| **Texture-palette skinning** (joint matrices in a float texture / UBO instead of the uniform array) — removes the bone cap entirely; full 343-bone UE5 rigs verbatim, no reduction pass. User-ratified direction 2026-07-18: maximum UE5/Unity asset compatibility, no artificial caps. Until it lands, `max_skinning_bones='auto'` covers rigs to the ~240 uniform wall (Session S) | New C++ + GLSL | Queued, **deprioritized on field evidence 2026-07-19**: the 81-vs-151 re-bake A/B measured ≤0.33 mm deviation on the pack's demo clips (correctives rigid to parents) — no deformation win until richer anim packs key them; 'auto'+audit guards the gap. Pairs naturally with an 8-influence option |
| **GPU morph path** (morph deltas + slider uniforms in the skinning vertex shader — HW skinning and morphs coexist) — the measured character-quality bottleneck (fact #16: loader delivery proven; field: visors stay sealed because faces can't move; CPU valve is ~+0.1 ms/frame per head — fine for one hero, not crowds). Per canon: Python/GLSL prototype FIRST (morph columns + slider table already reach the vdata; per-character slider push is O(sliders)) — C++ only if a profile demands | GLSL + Python (C++ on evidence) | Queued behind the character dev's morph re-export A/B; shares the vertex shader with texture-palette — one window can land both |
| ~~Core-profile combine-mode warning~~ | New C++ warning | **DONE 2026-07-18 (Session R mini-window, user-authorized)** — `857b715086`, once-per-TextureAttrib glgsg warning in both default-shader paths; 1m22s incremental build, full gate identical both engines, wheel live in pax3d-env + archived `wheels_session_r\`. Day-one field value: the warning fired on a real silently-flattened combine state in sfb2's own boot |
| Vulkan-port evaluation (hand-port from read-only upstream reference) | Port | Only when it can run the paxtest suite. Watch log 2026-07-17: ACTIVE — upstream merged `shaderpipeline` (SPIR-V) into the `vulkan` branch 2026-07-02/03; nowhere near paxtest-ready. The catch-up merge moved our base next to it — a future port got much cheaper |
| Python→C++ promotions | Promotion | **None yet** — nothing Python has profiled hot |

---

## Repository Map

| Path | What | Status |
|---|---|---|
| `pax3d_render/` | **The unified rendering pipeline.** Pipeline class, camera registration, sun modes, shadows. | Active — all rendering work happens here |
| `pax3d_render/shaders/` | GLSL sources (PBR, bloom, tonemap, TAA, shadow) | Active |
| `tools/paxtest/` | Offscreen test harness: gamma, lighting, bloom, rebuild, shadows | Active — extend when adding features |
| `pax3d_simplepbr/` | March-2026 simplepbr fork | **Retired** — reference only, merged into pax3d_render |
| `panda/src/` | Engine C++ (`glstuff/`+`glgsg/` are the GL backend, `wgldisplay/`+`windisplay/` the Windows glue, `pgraphnodes/` has the light classes) | Upstream 1.11.0-dev July-2026 state (merge `eb685fd003`, C++17) **minus R6 surgery**: DX9 and all GLES/EGL/WebGL/mobile/macOS display backends deleted (Windows 2+3, −35k lines). Kept on purpose: `x11display/`+`glxdisplay/` (HOLD — plausible Linux CI future), `tinydisplay/` (software renderer — paxtest on GPU-less machines) |
| `makepanda/` | Build system | oscmd fix + R6 surgery scrubs. Ships one graphics reality: OpenGL core on Windows (+X11/tinydisplay). `--no-dx9`/`--directx-sdk` no longer exist |
| `documents/` | Planning docs, findings, guides — see `documents/README.md` | Mixed current/historical |
| `doc/` | Upstream Panda3D docs (CODING_STYLE, INSTALL) | Upstream |

---

## Building the Engine (only needed for C++ changes)

Python/GLSL work in `pax3d_render/` needs **no engine build** — it runs on
whatever `panda3d` is installed. Build only when touching `panda/src/`.

The canonical command on this machine (PowerShell; ~8 min at 20 threads):

```powershell
cd C:\python\pax3d
$env:VCINSTALLDIR = "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\"
C:\Python313\python.exe makepanda\makepanda.py --everything --no-fmod --no-ffmpeg `
    --no-fftw --no-opencv --windows-sdk 10 --msvc-version=14.5 --threads 20 --wheel

# Install into the Pax3D venv:
C:\python\pax3d-env\Scripts\python.exe -m pip install --force-reinstall --no-deps panda3d-1.11.0-cp313-cp313-win_amd64.whl
```

Critical pitfalls (full detail in `documents/BUILDING_PAX3D.md`):
1. **ALWAYS pass `--windows-sdk 10`** — never rely on the default SDK pick.
2. **This machine has VS Build Tools 2026, not full VS** — makepanda's
   vswhere query cannot see Build Tools editions and it defaults to MSVC
   14.3, hence BOTH `--msvc-version=14.5` AND the `VCINSTALLDIR` env var
   are required (detection falls through to that var).
3. **`--no-dx9` no longer exists** (removed with the DX9 surgery) — old
   docs/scripts that pass it will error out.
4. **Thirdparty libraries are not in the repo** — see the build doc.
5. **Use system Python, never `makepanda.bat`.**
6. **Delete `built_x64/` after failed builds AND between flag changes** —
   the dep cache corrupts/mis-builds silently.

## Environments

| Environment | Python | Engine | Use for |
|---|---|---|---|
| System Python | `C:\Python313\python.exe` | Stock Panda3D 1.10.16 | paxtest cross-checks, quick runs |
| Pax3D venv | `C:\python\pax3d-env\` | Pax3D 1.11.0 (Session-R wheel — Window-3 + combine-mode warning) + full game dep stack | **The game's default engine**; engine-build testing |
| Doubles venv | `C:\python\pax3d-double-env\` | Pax3D 1.11.0 `STDFLOAT_DOUBLE` wheel | The doubles experiment ONLY — never wire to launchers (stock simplepbr crashes on it) |

The game (`plan.py`) and testbed run under either; paxtest runs under both —
identical results on both is itself a useful signal (defect is in Python/GLSL,
not C++). See `documents/SWITCHING_ENGINES.md`.

**Machine context (since 2026-07-17):** THIS machine (20 cores, VS Build
Tools 2026) is the primary dev machine — sfb2 development moved here;
`C:\python\sfb2` is the canonical current game copy (`D:\python\sfb2` on
the external T7 is the master backup; `D:\python\pax3d` is the pre-transfer
engine backup). Wheels live in `wheels_window1\{float,double}\`,
`wheels_window2\`, `wheels_window3\`, `wheels_session_r\` (current);
`wheels_float\` holds the pre-merge rollback. Smoke-boot the game with `PYTHONUTF8=1` when stdout is
redirected (a game-side `→` print crashes under cp1252 otherwise).

---

## Conventions

- C++: follow upstream (`doc/CODING_STYLE.md`); tag every Pax3D change with
  a `// PAX3D:` comment and list it in this file's change table when it lands.
- Python: the pipeline is plain, dependency-light code — keep it that way
  (no game imports in `pax3d_render/`; debug via `PAX3D_RENDER_DEBUG` env
  var or `debug=True`).
- Don't break the game's API surface: `from graphics.pax_pbr import init`
  must keep working (it routes here via the settings flag). Add, don't rename.
- Focused diffs, no drive-by reformatting of engine code — for reviewability
  and `// PAX3D:` auditability, not for upstream's sake (see below).
- Commit style: one logical change per commit; note the phase (e.g.
  "Session C / R2") in the subject.

## Upstream Relationship — SEVERED (user decision, 2026-07-17)

**Pax3D is a sovereign engine. We do NOT maintain compatibility with future
Panda3D versions, and upstream sync is no longer a goal or a cost to weigh.**
Modify the engine however the game needs: change defaults, rename, delete
legacy paths, add engine-level features. The `// PAX3D:` change tags stay —
they exist so we know our code from inherited code, not to ease merges.

Upstream (`panda3d/panda3d`) remains a read-only *reference*: cherry-pick a
specific fix by hand if one ever matters. There is no sync cadence.

One-time exception, user-ratified (Route A, 2026-07-17): a **final
catch-up merge** of upstream master (`eb685fd003` — C++17 migration + 93
commits of fixes) was taken before the door closed, moving our divergence
point from 2026-02-26 to July 2026. **Built and fully validated
2026-07-17** (`documents/BUILD_WINDOW_1_CATCHUP.md`) — the door is now
closed for good. No further syncs — the policy above is otherwise
unchanged. Sovereignty has since been exercised: R6 surgery Windows 2+3
deleted 35k lines of never-shipped backends.

| | |
|---|---|
| Upstream (reference only) | `panda3d/panda3d` (GitHub) |
| Our engine | `Apocrypha-Stellarum/Pax3D` |
| Divergence point | 2026-02-26 (`2d2bdc9a`), upstream 1.11.0-dev |
| Sync cadence | **None — severed 2026-07-17** |

---

## History in One Paragraph

Forked Feb 2026 to fix "the DirectionalLight problem" and add bloom/HDR. The
March effort built post-processing on an unlit, unverified pipeline and was
reverted almost entirely (Session 459 in the game repo). July 2026 rebooted
the program with a test harness first: the harness disproved both founding
myths (engine light bug, double gamma), reproduced the real bloom defect,
and then R1/R2 landed in quick succession — one unified pipeline, a real
DirectionalLight sun with working shadows, all harness-proven. On
2026-07-17 the final upstream catch-up merge was built and signed off, the
doubles spike verified, and R6 surgery removed DX9 and every dead platform
backend — a sovereign, single-reality engine tree, every step gated by the
harness. The lesson that must survive: **measure first, then build.**
