# Switching Between Stock Panda3D and Pax3D

This guide explains how to run Pax Abyssi with either the standard Panda3D engine or the custom Pax3D engine. **The game code never changes** — only the engine underneath does.

## Quick Reference (TL;DR)

| What | Command |
|------|---------|
| **Activate Pax3D venv** | `C:\python\pax3d-env\Scripts\activate` (cmd) or `. C:\python\pax3d-env\Scripts\Activate.ps1` (PowerShell) |
| **Deactivate venv** | `deactivate` |
| **Check current engine** | `python -c "import panda3d; print(panda3d.__file__)"` |
| **Run with stock Panda3D** | From C:\python\sfb2: `python plan.py` |
| **Run with Pax3D** | Activate venv first, then from C:\python\sfb2: `python plan.py` |

---

## Setup Overview

You have three Python environments:

1. **Stock Panda3D (Default)**
   - Python: `C:\Python313\python.exe`
   - Panda3D: User site-packages (system Python)
   - Used by: `python plan.py` without venv activation

2. **Pax3D venv**
   - Virtual environment: `C:\python\pax3d-env`
   - Python: 3.13.7 (isolated)
   - Panda3D: Currently 1.10.16 (will be replaced with custom Pax3D builds)
   - Used by: `python plan.py` with venv activated

3. **Pax3D source (development)**
   - Location: `C:\python\pax3d`
   - What it is: Engine source code (GitHub fork: Apocrypha-Stellarum/Pax3D)
   - Purpose: Building custom wheel files to install into the venv

---

## Activating the Pax3D Virtual Environment

### Windows Command Prompt (cmd.exe)

```cmd
C:\python\pax3d-env\Scripts\activate
```

After running this, your prompt should show `(pax3d-env)` at the start.

### Windows PowerShell

```powershell
. C:\python\pax3d-env\Scripts\Activate.ps1
```

If you get a permission error about execution policy, try:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
. C:\python\pax3d-env\Scripts\Activate.ps1
```

### Git Bash / WSL / Unix shells

```bash
source C:\python\pax3d-env\Scripts\activate
```

---

## Deactivating the Virtual Environment

From any shell (cmd, PowerShell, bash):

```
deactivate
```

The `(pax3d-env)` indicator will disappear from your prompt.

---

## Checking Which Engine is Active

Run this one-liner to see which Panda3D you're using:

```python
python -c "import panda3d; print(panda3d.__file__)"
```

**Stock Panda3D output** (without venv):
```
C:\Users\<username>\AppData\Roaming\Python\Python313\site-packages\panda3d
```

**Pax3D venv output** (with venv activated):
```
C:\python\pax3d-env\lib\site-packages\panda3d
```

---

## Running Pax Abyssi with Each Engine

### With Stock Panda3D (Default)

Simply run from the game directory with no venv:

```bash
cd C:\python\sfb2
python plan.py
```

**Verify:** The game window will start using the system Python and stock Panda3D 1.10.16.

### With Pax3D

Activate the venv first, then run the game:

```bash
# Activate the venv (cmd or PowerShell example)
C:\python\pax3d-env\Scripts\activate

# Navigate to game directory
cd C:\python\sfb2

# Run the game
python plan.py
```

**Verify:** The game window will start using the venv's Python and the custom Pax3D build.

---

## Installing a New Pax3D Build

When you build a new Pax3D wheel from source at `C:\python\pax3d`, follow these steps:

### Step 1: Build the wheel (from pax3d source directory)

```bash
cd C:\python\pax3d
python -m pip install -e .
# or build a wheel directly (consult Pax3D build docs)
```

### Step 2: Activate the venv

```cmd
C:\python\pax3d-env\Scripts\activate
```

### Step 3: Uninstall the old Panda3D

```bash
pip uninstall panda3d -y
```

### Step 4: Install the new wheel

If you have a `.whl` file (e.g., `panda3d-custom-1.10.16.whl`):

```bash
pip install C:\path\to\panda3d-custom-1.10.16.whl
```

If building from source with `pip install -e .`:

```bash
cd C:\python\pax3d
pip install -e .
```

### Step 5: Verify installation

```python
python -c "import panda3d; print(panda3d.__file__)"
```

You should see the venv path. If it still shows the system path, the venv may not be activated.

---

## Troubleshooting

### Problem: Game runs the wrong engine

**Symptom:** You activated the venv but the game still uses stock Panda3D.

**Solution:**
1. Verify the venv is active: Look for `(pax3d-env)` in your prompt
2. Check which Python is running: `python --version` and `python -c "import sys; print(sys.prefix)"`
3. If the venv is active but `sys.prefix` shows the system directory, the venv activation failed
4. Try deactivating and re-activating: `deactivate` then `C:\python\pax3d-env\Scripts\activate`

### Problem: "ModuleNotFoundError: No module named 'panda3d'"

**Symptom:** Game crashes with panda3d import error.

**Solution:**
1. Check if you activated the venv: `(pax3d-env)` should be in your prompt
2. Verify packages are installed: `pip list | grep panda3d`
3. If missing, reinstall dependencies:
   ```bash
   cd C:\python\pax3d-env
   pip install panda3d panda3d-gltf panda3d-simplepbr numpy pillow PyQt6
   ```

### Problem: venv activation doesn't work on PowerShell

**Symptom:** `Cannot be loaded because running scripts is disabled` or similar.

**Solution:** Allow script execution for your user:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then try activating again.

### Problem: "Permission denied" when running Python scripts

**Symptom:** Game won't start, permission error.

**Solution:**
1. Try running in a new prompt window (close and reopen)
2. Make sure you're in the correct directory: `cd C:\python\sfb2`
3. Check file permissions on the venv and game directory (usually just a Windows path issue)

---

## How the Game Code Stays Unchanged

The game is completely **engine-agnostic**. Whether you run `python plan.py` with stock Panda3D or custom Pax3D:

- All game scripts in `C:\python\sfb2` work identically
- The `import panda3d` lines point to whichever engine is installed
- No game code needs to change

This is why switching engines is just about **which Python environment** you activate — the game code itself never needs modification.

---

## File Locations Reference

| Item | Location |
|------|----------|
| Stock Python | `C:\Python313\python.exe` |
| Pax3D venv root | `C:\python\pax3d-env` |
| Pax3D source | `C:\python\pax3d` |
| Game code | `C:\python\sfb2` |
| This guide | `C:\python\pax3d\docs\SWITCHING_ENGINES.md` |

---

## Questions?

- **For game issues:** Check `C:\python\sfb2\CLAUDE.md` and the game documentation
- **For Pax3D build/engine issues:** Check `C:\python\pax3d` README or Pax3D GitHub fork
- **For venv/Python issues:** See troubleshooting section above
