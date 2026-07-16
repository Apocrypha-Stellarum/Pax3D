# Building Pax3D from Source (Windows)

This guide is for AI developers building Pax3D. It documents every pitfall we hit so you don't have to rediscover them.

---

## Prerequisites

| Requirement | What We Have | Notes |
|-------------|-------------|-------|
| **Visual Studio 2022** | Community edition at `C:\Program Files\Microsoft Visual Studio\2022\Community\` | Need the "Desktop development with C++" workload. VS 2019 BuildTools also present but VS 2022 is used. |
| **Windows SDK 10** | 10.0.22621.0 at `C:\Program Files (x86)\Windows Kits\10\` | **CRITICAL: SDK 8.1 is also installed but is essentially empty — only has a `References` folder, no `windows.h`. You MUST specify `--windows-sdk 10` or the build will fail with `Cannot open include file: 'windows.h'`.** |
| **Python 3.13** | `C:\Python313\python.exe` | Must match the Python version Pax Abyssi uses. The thirdparty package includes its own Python but we invoke makepanda with the system Python. |
| **Thirdparty libraries** | `C:\python\pax3d\thirdparty\` | Pre-built dependencies. See "Thirdparty Setup" below. |

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

## The Build Command

```bash
cd C:/python/pax3d

C:/Python313/python.exe makepanda/makepanda.py \
    --everything \
    --no-dx9 \
    --no-fmod \
    --no-ffmpeg \
    --no-fftw \
    --no-opencv \
    --windows-sdk 10 \
    --threads 8 \
    --wheel
```

### Flags Explained

| Flag | Why |
|------|-----|
| `--everything` | Build all supported features (then subtract what we don't want) |
| `--no-dx9` | DirectX 9 removal is a Pax3D goal. We only target OpenGL. |
| `--no-fmod` | FMOD isn't in our thirdparty package (proprietary license). Pax Abyssi uses the default OpenAL audio backend. |
| `--no-ffmpeg` | Video playback not needed — we'd use PyQt6 for that. Also not in our thirdparty. |
| `--no-fftw` | FFT library — not in thirdparty, not needed. |
| `--no-opencv` | Computer vision — not in thirdparty, not needed. |
| `--windows-sdk 10` | **CRITICAL.** Without this, makepanda defaults to SDK 8.1 which is broken on this machine. See pitfalls below. |
| `--threads 8` | Parallel compilation. Adjust to your CPU core count. |
| `--wheel` | Produce a `.whl` pip package instead of an installer. |

### Build Time

- **Clean build:** ~25-40 minutes with 8 threads
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

### 1. Windows SDK 8.1 is broken — ALWAYS use `--windows-sdk 10`

SDK 8.1 is installed at `C:\Program Files (x86)\Windows Kits\8.1\` but only contains a `References` folder — no headers, no `windows.h`. Makepanda defaults to 8.1 if present and will fail with:

```
fatal error C1083: Cannot open include file: 'windows.h': No such file or directory
```

**Fix:** Always pass `--windows-sdk 10`.

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

```bash
# Incremental rebuild (only recompiles changed files)
cd C:/python/pax3d
C:/Python313/python.exe makepanda/makepanda.py \
    --everything --no-dx9 --no-fmod --no-ffmpeg --no-fftw --no-opencv \
    --windows-sdk 10 --threads 8 --wheel

# Install updated wheel
source C:/python/pax3d-env/Scripts/activate
pip install --force-reinstall panda3d-*.whl

# Test
cd C:/python/sfb2
python plan.py
```

### Build system changes we've made

| File | Change | Why |
|------|--------|-----|
| `makepanda/makepandacore.py:677-681` | `oscmd()` respects `ignoreError` for binary-not-found | `mt.exe` not in PATH caused hard crash on optional step |

---

## Quick Reference

```bash
# Full clean build
rm -rf C:/python/pax3d/built_x64
cd C:/python/pax3d
C:/Python313/python.exe makepanda/makepanda.py \
    --everything --no-dx9 --no-fmod --no-ffmpeg --no-fftw --no-opencv \
    --windows-sdk 10 --threads 8 --wheel

# Install into venv
source C:/python/pax3d-env/Scripts/activate
pip install --force-reinstall C:/python/pax3d/panda3d-*.whl

# Run game on Pax3D
cd C:/python/sfb2 && python plan.py

# Deactivate (back to stock Panda3D)
deactivate
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
| Game code | `C:\python\sfb2` |
| System Python | `C:\Python313\python.exe` |
| Visual Studio | `C:\Program Files\Microsoft Visual Studio\2022\Community\` |
| Windows SDK 10 | `C:\Program Files (x86)\Windows Kits\10\` |
| Windows SDK 8.1 | `C:\Program Files (x86)\Windows Kits\8.1\` (BROKEN — do not use) |
