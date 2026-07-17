# Building Pax3D from Source (Windows)

This guide is for AI developers building Pax3D. It documents every pitfall we hit so you don't have to rediscover them.

> **Policy note (2026-07-17):** builds run only in **user-scheduled build
> windows** (see CLAUDE.md "Language Canon"). Windows 1–3 all completed
> 2026-07-17 on the current primary machine (20 cores, ~8-minute builds).
> Post-catch-up-merge (`eb685fd003`) facts: the tree compiles as **C++17**,
> and makepanda **pip-installs `panda3d-interrogate==0.11.2` from PyPI at
> build time** — the build machine needs internet, or pre-seed
> `built_x64/tmp/interrogate` with `pip install -t <that dir>
> panda3d-interrogate==0.11.2` beforehand. Convention: segregate wheels
> into per-window folders (`wheels_window1/float/`, `wheels_window2/`, …) —
> all builds emit the SAME filename.
> **R6 surgery note:** DX9 and the GLES/EGL/WebGL/mobile/macOS backends
> are deleted from the tree; **`--no-dx9` and `--directx-sdk` are no
> longer valid makepanda options.**

---

## Prerequisites

| Requirement | What We Have (primary machine, 2026-07-17) | Notes |
|-------------|-------------|-------|
| **Visual Studio C++ toolchain** | **VS Build Tools 2026** (v18.2, MSVC 14.50) at `C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\` | "Desktop development with C++" workload. **Build Tools editions are invisible to makepanda's vswhere query** — you MUST pass `--msvc-version=14.5` AND set `VCINSTALLDIR` (see pitfall 0). Full VS 2022+ works without the env var. |
| **Windows SDK 10** | 10.0.26100.0 at `C:\Program Files (x86)\Windows Kits\10\` | Always pass `--windows-sdk 10` regardless of machine — never trust the default pick. |
| **Python 3.13** | `C:\Python313\python.exe` (3.13.11 x64, also `py -3.13`) | Must be 3.13 x64 — the wheel is tagged `cp313` to match `pax3d-env`. |
| **Thirdparty libraries** | `C:\python\pax3d\thirdparty\` (777 MB, 24 packages) | Pre-built dependencies, NOT in git. See "Thirdparty Setup" below. |

---

## Thirdparty Setup (One-Time)

The Panda3D source on GitHub does NOT include third-party libraries. You need to download them separately.

### Download prebuilt thirdparty (recommended)

The fastest approach — download pre-built binaries from the `rdb/panda3d-thirdparty` GitHub Actions:

```bash
# Find the latest successful build
gh api repos/rdb/panda3d-thirdparty/actions/runs?branch=main'&'status=success'&'event=push'&'per_page=1 \
  --jq '.workflow_runs[0].id'

# Download the Windows x64 artifact (use the run ID from above)
gh run download <RUN_ID> -R rdb/panda3d-thirdparty -n win-libs-vc14-x64 -D C:/python/pax3d/thirdparty

# Extract (the zip contains a thirdparty/ subdirectory)
cd C:/python/pax3d
python -c "
import zipfile
with zipfile.ZipFile('thirdparty/thirdparty-win64.zip', 'r') as z:
    z.extractall('.')
"

# Clean up the zip
rm thirdparty/thirdparty-win64.zip
```

After extraction, `thirdparty/` should contain:
```
win-libs-vc14-x64/     ← The actual libraries (OpenGL, zlib, OpenSSL, etc.)
win-python3.13-x64/    ← Bundled Python (makepanda uses this for some steps)
win-python3.12-x64/    ← Other Python versions (ignored)
win-nsis/              ← NSIS installer tools
win-util/              ← Build utilities
```

### Build thirdparty from source (alternative)

Only if the prebuilt artifacts have expired (GitHub Actions artifacts expire after 90 days):

```bash
git clone https://github.com/rdb/panda3d-thirdparty.git
cd panda3d-thirdparty
mkdir build && cd build
cmake -G"Visual Studio 17 2022" -A x64 ..
cmake --build . --config Release
```

This takes a long time. Use the prebuilt route if at all possible.

---

## The Build Command (canonical, primary machine)

```powershell
cd C:\python\pax3d
$env:VCINSTALLDIR = "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\"

C:\Python313\python.exe makepanda\makepanda.py `
    --everything `
    --no-fmod --no-ffmpeg --no-fftw --no-opencv `
    --windows-sdk 10 --msvc-version=14.5 `
    --threads 20 --wheel
```

### Flags Explained

| Flag | Why |
|------|-----|
| `--everything` | Build all supported features (then subtract what we don't want) |
| `--no-fmod` | FMOD isn't in our thirdparty package (proprietary license). Pax Abyssi uses the default OpenAL audio backend. |
| `--no-ffmpeg` | Video playback not needed — we'd use PyQt6 for that. Also not in our thirdparty. |
| `--no-fftw` | FFT library — not in thirdparty, not needed. |
| `--no-opencv` | Computer vision — not in thirdparty, not needed. |
| `--windows-sdk 10` | **CRITICAL.** Never trust the default SDK pick. |
| `--msvc-version=14.5` | **CRITICAL on this machine.** makepanda defaults to 14.3 (VS 2022); we have MSVC 14.5 (VS 2026 Build Tools). Pairs with the `VCINSTALLDIR` env var above. |
| `--threads 20` | Parallel compilation. Set to your core count. |
| `--wheel` | Produce a `.whl` pip package instead of an installer. |

(`--no-dx9` is gone — DX9 was deleted from the tree in R6 Window 2; the
flag no longer parses.)

### Build Time

- **Clean build:** ~8 minutes at 20 threads on the primary machine
  (25–40 min at 8 threads on older hardware)
- **Incremental rebuild** (after code changes): Much faster — only recompiles changed files

### Build Output

The build output lands in `built_x64/`. The `--wheel` flag should produce a wheel in the repo root, but if it doesn't (which can happen), see the manual wheel step below.

### Manual Wheel Generation (if `--wheel` doesn't produce one)

If the build succeeds but no `.whl` file appears, run `makewheel.py` separately:

```bash
# IMPORTANT: dumpbin.exe must be in PATH for makewheel to work
# Add the VS MSVC tools directory (adjust version number as needed):
export PATH="$PATH:/c/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.38.33130/bin/Hostx64/x64"

# Generate the wheel
cd C:/python/pax3d
C:/Python313/python.exe makepanda/makewheel.py --outputdir built_x64
```

The `--outputdir built_x64` flag tells makewheel where the compiled build output lives. Without it, makewheel won't find the DLLs.

The resulting wheel lands in the repo root:
```
C:\python\pax3d\panda3d-1.11.0-cp313-cp313-win_amd64.whl
```

---

## Installing the Build

```bash
# Activate the Pax3D venv
source C:/python/pax3d-env/Scripts/activate

# Install the wheel (force-reinstall replaces whatever was there)
pip install --force-reinstall C:/python/pax3d/panda3d-1.11.0-cp313-cp313-win_amd64.whl

# Verify
python -c "import panda3d.core; print('Version:', panda3d.core.PandaSystem.getVersionString())"
# Should print: Version: 1.11.0

# Test the game
cd C:/python/sfb2
python plan.py
```

---

## Known Pitfalls

### 0. VS Build Tools editions are invisible to makepanda (this machine)

makepanda finds Visual Studio via `vswhere.exe` — but its query lacks
`-products *`, so **Build Tools** editions (like this machine's VS 2026
Build Tools) are never found, and the VS7 registry fallback doesn't exist
for them either. The surviving detection path is the `VCINSTALLDIR`
environment variable:

```powershell
$env:VCINSTALLDIR = "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\"
```

Combined with `--msvc-version=14.5` (makepanda defaults to 14.3 = VS 2022),
this makes detection work end-to-end. Symptom if you forget either:
`Couldn't find Visual Studio 2022/2026`.

### 1. Never trust the default Windows SDK pick — ALWAYS use `--windows-sdk 10`

On the old A computer, a broken SDK 8.1 shell made makepanda's default fail
with `Cannot open include file: 'windows.h'`. Pass `--windows-sdk 10` on
every machine, always.

### 2. `mt.exe` not found — patched in Pax3D

The Windows Manifest Tool (`mt.exe`) lives in `C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\` and is NOT on the default PATH. Stock Panda3D's `oscmd()` function in `makepandacore.py` would hard-crash when `mt.exe` wasn't found, even though the call was flagged as `ignoreError=True`.

**Pax3D fix:** We patched `makepandacore.py:677-681` so that `oscmd()` respects `ignoreError` on binary-not-found — it prints a warning and continues instead of calling `exit()`. The `mt` step is optional (embeds a Windows SxS manifest into the Python executable copy, which modern Python doesn't need).

If you see `WARNING: Cannot find mt on search path, skipping` — that's expected and harmless.

### 3. Don't modify PATH in the bash shell

Adding Windows SDK or VS directories to the bash PATH can break other tools (`tail`, `head`, etc.) because Windows executables shadow Unix ones. Makepanda handles compiler discovery internally — it finds Visual Studio and the SDK without needing them in PATH.

If you need VS tools for other purposes, use the VS Developer Command Prompt or `vcvarsall.bat` in a separate `cmd.exe` session.

### 4. Corrupted dependency cache after failed builds

If a build fails partway through and you change build flags or environment, the dependency cache in `built_x64/` can get confused, causing subsequent builds to skip setup steps or compile with wrong settings.

**Fix:** Delete `built_x64/` and rebuild clean:
```bash
rm -rf C:/python/pax3d/built_x64
```

### 5. `makepanda.bat` won't work — use `python makepanda.py` directly

The batch file (`makepanda/makepanda.bat`) looks for a bundled Python in `thirdparty/win-python3.8-x64/` which doesn't exist in our thirdparty package (we have 3.10+). Always invoke makepanda via the system Python directly:

```bash
C:/Python313/python.exe makepanda/makepanda.py [flags]
```

### 6. Run from the repo root

Makepanda must be run from `C:\python\pax3d\` (the repo root), not from inside the `makepanda/` directory. It checks for this and exits with "Current directory is not the root of the panda tree" if wrong.

### 7. Missing thirdparty packages produce warnings, not errors

If a thirdparty package isn't found, makepanda prints a warning and excludes that feature:
```
WARNING: Could not locate thirdparty package fmodex, excluding from build
```

This is usually fine. The packages we explicitly exclude with `--no-xxx` flags won't even warn. Unexpected warnings about packages we DO want (e.g., OpenGL, OpenSSL, zlib) indicate a broken thirdparty setup — redownload.

---

## Pax3D-Specific Engine Changes

Any C++ changes to the engine source are in the `panda/src/` and `dtool/` directories. After making changes:

```powershell
# Incremental rebuild (only recompiles changed files)
cd C:\python\pax3d
$env:VCINSTALLDIR = "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\"
C:\Python313\python.exe makepanda\makepanda.py `
    --everything --no-fmod --no-ffmpeg --no-fftw --no-opencv `
    --windows-sdk 10 --msvc-version=14.5 --threads 20 --wheel

# Install updated wheel
C:\python\pax3d-env\Scripts\python.exe -m pip install --force-reinstall --no-deps panda3d-*.whl

# Gate it (never skip): paxtest both engines, then testbed/smokes
C:\Python313\python.exe tools\paxtest\run.py
C:\python\pax3d-env\Scripts\python.exe tools\paxtest\run.py
```

### Build system changes we've made

| File | Change | Why |
|------|--------|-----|
| `makepanda/makepandacore.py` | `oscmd()` respects `ignoreError` for binary-not-found | `mt.exe` not in PATH caused hard crash on optional step |
| `makepanda/*` (Window 2, `d29183ce42`) | DX9 build rules, SDK locator, `HAVE_DX9`/`HAVE_CGDX9`, installer refs removed | R6 surgery: DX9 deleted from the tree |
| `makepanda/*` (Window 3, `3912762dd9`) | GLES/GLES2/EGL/COCOA packages, build sections, config.in display lines, DX9 flag machinery removed | R6 surgery: dead platform backends deleted; `--no-dx9`/`--directx-sdk` no longer parse |

---

## Quick Reference

```powershell
# Full clean build
Remove-Item C:\python\pax3d\built_x64 -Recurse -Force
cd C:\python\pax3d
$env:VCINSTALLDIR = "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\"
C:\Python313\python.exe makepanda\makepanda.py `
    --everything --no-fmod --no-ffmpeg --no-fftw --no-opencv `
    --windows-sdk 10 --msvc-version=14.5 --threads 20 --wheel

# Segregate the wheel (all builds emit the same filename), then install
Move-Item panda3d-*.whl wheels_windowN\
C:\python\pax3d-env\Scripts\python.exe -m pip install --force-reinstall --no-deps wheels_windowN\panda3d-1.11.0-cp313-cp313-win_amd64.whl

# Run game on Pax3D (PYTHONUTF8=1 if redirecting output)
cd C:\python\sfb2; C:\python\pax3d-env\Scripts\python.exe plan.py
```

---

## File Locations

| What | Where |
|------|-------|
| Pax3D source | `C:\python\pax3d` |
| Thirdparty libs | `C:\python\pax3d\thirdparty\win-libs-vc14-x64\` |
| Build output | `C:\python\pax3d\built_x64\` |
| Wheel file | `C:\python\pax3d\panda3d-*.whl` |
| Pax3D venv | `C:\python\pax3d-env` |
| Doubles venv (experiment only) | `C:\python\pax3d-double-env` |
| Game code (canonical) | `C:\python\sfb2` (master backup: `D:\python\sfb2`) |
| System Python | `C:\Python313\python.exe` |
| VS Build Tools 2026 | `C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\` |
| Windows SDK 10 | `C:\Program Files (x86)\Windows Kits\10\` (10.0.26100) |
| Wheels | `wheels_window1\{float,double}\`, `wheels_window2\`, `wheels_window3\` (current), `wheels_float\` (pre-merge rollback) |
