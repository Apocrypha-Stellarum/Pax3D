# Engine Surgery Plan — Deletions, Windows 2+

**Date:** 2026-07-17 · **Status:** Windows 2+3 EXECUTED 2026-07-17;
**Window 4 EXECUTED 2026-07-19** (see Sequencing) · **Policy basis:** Pax3D is
sovereign (no upstream sync — see CLAUDE.md); deletions no longer carry
merge-friction cost. **Audience:** the AI dev running a build window.

Pax3D ships one graphics reality: **OpenGL 3.3+ core on Windows**, custom
GLSL via `pax3d_render`. Everything in the engine tree that serves another
reality is candidate dead weight. The payoff of surgery is mostly
*cognitive and hygienic* — a smaller tree for AI devs to grep, read, and
reason about, faster builds, no accidental references — not runtime speed
(dead backends already compile out). Price accordingly: surgery is cheap
but never urgent; it rides build windows, it never justifies one alone.

---

## Ground rules

1. **Window 1 first.** No surgery until the catch-up-merge wheel (float)
   has passed the full validation gauntlet. Never stack an unvalidated
   merge and a mass deletion in one build.
2. **Deletions only, per window.** Surgery windows delete; they do not
   add or refactor. (New C++ like the R2.3 conveniences goes in its own
   window under the Language Canon.)
3. **The gate is the usual one:** clean build on B, full paxtest matrix
   both engines + both baselines, testbed `--selftest`, sfb2 + openworld
   smoke. paxtest's `none`/`simplepbr` reference pipelines exercise the
   auto-shader and fixed-function paths — they are the canary for
   over-deletion.
4. **Method per item:** `grep` the symbol/dir across `makepanda/`,
   `panda/`, `direct/`, PRC defaults (`dtool/src/prc/`), docs → delete →
   build → gate. Tag the commit `// PAX3D:`-style in the message
   ("Surgery: remove X").

---

## Inventory and verdicts

### Window 2 — DirectX 9 (the ratified R6 goal)

| Target | Size | Notes |
|---|---|---|
| `panda/src/dxgsg9/` | 588 KB | The DX9 GSG. Never built since the fork (`--no-dx9`). |
| `panda/metalibs/pandadx9/` | 3 KB | Its metalib shell. |
| makepanda references | 19 hits in `makepanda.py` | `--no-dx9` flag handling, package lists, sdk checks. Keep accepting the flag as a no-op for one window (our build scripts pass it), then drop. |
| PRC / loader references | `load-display pandadx9` fallbacks, `aux-display` lists in `dtool/src/prc` defaults and docs | grep `pandadx9` + `dx9`. |

Risk: **build-system only** (nothing links it today); any breakage
surfaces at compile time on B, not at runtime. This is the ideal first
surgery — big cognitive win, near-zero risk.

### Window 3 — non-Windows / non-GL display backends (decide per row)

We target Windows + OpenGL. These serve platforms we will never ship:

| Target | Verdict | Rationale |
|---|---|---|
| `androiddisplay/`, `iphonedisplay/` | DELETE | Mobile. Dead certainty. |
| `glesgsg/`, `gles2gsg/`, `egldisplay/`, `webgldisplay/` | DELETE | GLES/WebGL stacks. The `IS_WEBGL` branches in pax3d_render shaders are unrelated (they're our GLSL-level switches) and unaffected. |
| `cocoadisplay/`, `cocoagldisplay/` | DELETE (after a beat) | macOS. Only pause: the B computer and any future machine are Windows — confirm no one dreams of a Mac build, then cut. |
| `x11display/`, `glxdisplay/` | HOLD | Linux. Cheap to keep; a headless Linux CI box someday is the one plausible future. Revisit at Window 4. |
| `tinydisplay/` | **KEEP** | Software renderer — the only way to run paxtest on a GPU-less machine (CI, cloud). Costs little; insurance worth holding. |
| `wgldisplay/`, `windisplay/`, `glgsg/`, `glstuff/`, `display/`, `gsgbase/` | KEEP | This is the engine. |

### Deferred indefinitely — entangled, wrong time

| Target | Verdict | Rationale |
|---|---|---|
| Cg shader support (`glCgShaderContext_src.*`, `HAVE_CG` paths through `gobj`/`glstuff`) | DEFER | Entangled with the `Shader` class internals, and upstream's `shaderpipeline` branch replaces that entire stack. If we ever hand-port shaderpipeline (see watch item), Cg falls out for free; hand-extracting it now buys the smallest win in the inventory at the highest risk. |
| Fixed-function / ShaderGenerator paths | KEEP | paxtest's `none` + `simplepbr` reference pipelines run on them — they are our control group. They stay as long as the harness method stays. |
| Audio backends beyond OpenAL, bullet, etc. | KEEP (excluded at build) | `--no-fmod` etc. already handle it; source presence costs nothing and openworld uses OpenAL. |

---

## Sequencing — status 2026-07-17 evening

```
Window 1  DONE     Catch-up merge + doubles wheel — built, FULL gauntlet
                   green, merge signed off (see BUILD_WINDOW_1_CATCHUP.md)
Window 2  DONE     DX9 removal — commit cd37d67b93, 65 files,
                   −16,691 lines, own build + full gate green
Window 3  DONE     Mobile/GLES/WebGL/macOS backend removal + DX9 flag
                   machinery drop — commit 8366907b14, 132 files,
                   −18,546 lines, own build + full gate green.
                   x11/glx HOLD confirmed kept; tinydisplay kept
                   (its macOS tinyCocoa* flavor removed with the theme)
Window 4  DONE     Mobile-TARGET extraction — commit baf541388a
                   (2026-07-19), 72 files, −8,112 lines: panda/src/android
                   + panda/src/iphone, express Android asset mount, prc
                   androidLogStream, deploy-stub android glue, dist
                   _android.py/_proto/ + android branches in commands/
                   installers/FreezeTool, makepanda Android cross-compile
                   machinery (SdkLocateAndroid, SetTarget mapping,
                   CompileJava/CompileDalvik), DIRECTCAM (gated sources +
                   plumbing). Two fixup commits (c6a5f502f3, ecf01ea976)
                   restored Cxx-cache globals over-cut beside the Java
                   block — LESSON: when excising a block between two
                   anchors, audit ALL top-level names removed vs still
                   referenced (the audit script pattern is in the session
                   log). Own build (10m54s clean) + full gate green:
                   134-row paxtest matrix identical stock vs Pax3D on
                   BOTH baselines (@game 55/6/73 — the post-morph-gate
                   totals; @modern 54/7/73, the extra FAIL being
                   lighting/none — fixed-function control vs core
                   profile, pre-existing on stock), testbed selftest,
                   openworld selftest, sfb2 30s boot smoke clean.
                   x11/glx HOLD revisited and MAINTAINED (plausible
                   Linux CI future); tinydisplay KEEP. Inert #ifdef
                   ANDROID/BUILD_IPHONE guards in core dtool files
                   survive by design (out-of-scope rule). Wheel:
                   wheels_window4\
Window 5+          Any Language-Canon promotions that have profiled hot;
                   R2.3 DirectionalLight conveniences ONLY after its own
                   design pass (Window-4 planning found the queued
                   strip-translation xform() conflicts with the
                   pipeline's set_pos() shadow centering — see the
                   master plan §4.7 queue row)
Unscheduled        Cg — only via a shaderpipeline port decision
```

Each window: one themed change-set, one build, one full gate. Windows 2,
3 and 4 each got their own build + gate (paxtest both baselines identical
incl. the none/simplepbr canaries, testbed + openworld selftests, sfb2
boot). Post-surgery the tree is ~43k lines lighter and ships exactly one
graphics reality: OpenGL core on Windows, with X11/GLX held and
tinydisplay as GPU-less insurance. No mobile target machinery remains
anywhere in the tree.

Note for Window 4: `--no-dx9` / `--directx-sdk` already ceased to exist
in Window 3 — any script still passing them fails fast.

## What surgery does NOT cover

- GLSL-120 dual-path removal in `pax3d_render/shaderutils.py` + shaders —
  that's Python/GLSL (R1.4), gated on the GAME setting `gl-version 3 2`,
  no build window needed.
- Anything performance-motivated — that goes through the Language Canon
  (profile first), not the deletion plan.
