# Build Window 1 — Final Catch-Up Merge (+ optional doubles wheel)

**Date opened:** 2026-07-17 · **Merge commit:** `eb685fd003`
**What this window builds:** the one-time Route A catch-up merge of
upstream `panda3d/panda3d` master (93 commits: C++17 migration,
robustness/bugfix cluster, test suite) into our tree. After this window
validates, the severed-upstream policy applies forever — no future syncs.
**Optional second build:** the double-precision engine wheel
(`STDFLOAT_DOUBLE=1`) — the shelved spike, resumed because the B computer
removes the compile-cost objection. Full doubles context:
`C:\python\sfb2\documents\handover_doubles_spike.md`.

The A-computer state is ready: merge committed, zero conflicts, our only
local build change (`makepandacore.py` oscmd fix) intact, paxtest green
on the pre-merge wheels (Python/GLSL side provably undisturbed).

---

## 1. What to copy to the external drive

Copy the **whole `C:\python\pax3d\` folder** — it self-contains everything
including `thirdparty\` (834 MB of prebuilt libs; the part NOT in git) and
`.git\` (keep it: provenance + lets B commit fixes if needed).

Then **DELETE from the copy** (stale artifacts that will poison the build):

| Delete from the copy | Why |
|---|---|
| `built_x64\` | Pre-merge dependency cache — pitfall #4, guaranteed wrong after a 1,387-file merge |
| `wheels_float\` | Pre-merge wheel from the old doubles spike |
| `panda3d-*.whl` (repo root, if any) | Pre-merge artifacts |
| `.claude\` | Session-local, not needed |
| `tools\paxtest\output\` | Screenshots/reports, junk weight |

Expect roughly 1.5–2 GB total.

## 2. B-computer prerequisites

| Requirement | Detail |
|---|---|
| Visual Studio 2022 | "Desktop development with C++" workload. (Newer VS also fine — the merge added MSVC 14.5/2026 support.) |
| Windows 10/11 SDK | Any complete SDK 10.x. Pass `--windows-sdk 10` regardless — never rely on the default (an empty SDK 8.1 shell, if present, breaks it). |
| **Python 3.13 x64** | MUST be 3.13 — the wheel is tagged `cp313` to match `pax3d-env` and `C:\Python313` on the A computer. Invoke makepanda with it explicitly. |
| **Internet at build time** | makepanda pip-installs `panda3d-interrogate==0.11.2` into `built_x64\tmp\interrogate`. If B is offline, pre-seed on A first: `C:/Python313/python.exe -m pip install --force-reinstall -t <copy>/built_x64/tmp/interrogate panda3d-interrogate==0.11.2` (create just that folder — nothing else in built_x64). |

## 3. Build 1 — the standard (float) wheel  [REQUIRED]

From the repo root of the copy (makepanda refuses to run elsewhere), in
plain `cmd`/PowerShell or Git Bash:

```bash
cd <drive>/pax3d
py -3.13 makepanda/makepanda.py \
    --everything --no-dx9 --no-fmod --no-ffmpeg --no-fftw --no-opencv \
    --windows-sdk 10 --threads 8 --wheel 2>&1 | tee build_float.log
```

(`--threads`: set to B's core count. Use the real python path if `py -3.13`
isn't wired.)

- Clean build: ~25–40 min at 8 threads (first C++17 build — expect the
  full compile, no shortcuts).
- Success = `panda3d-1.11.0-cp313-cp313-win_amd64.whl` in the repo root.
- If the build succeeds but no wheel appears, run makewheel manually —
  `dumpbin.exe` must be on PATH for it:
  ```bash
  export PATH="$PATH:/c/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/<version>/bin/Hostx64/x64"
  py -3.13 makepanda/makewheel.py --outputdir built_x64
  ```
- Segregate immediately (both builds produce the SAME filename):
  ```bash
  mkdir -p wheels_window1/float && mv panda3d-*.whl wheels_window1/float/
  ```

## 4. Build 2 — the doubles wheel  [OPTIONAL, recommended]

**Delete `built_x64\` first — mandatory.** A flag change over a stale
dep cache mis-builds silently (pitfall #4):

```bash
rm -rf built_x64
py -3.13 makepanda/makepanda.py \
    --everything --no-dx9 --no-fmod --no-ffmpeg --no-fftw --no-opencv \
    --windows-sdk 10 --threads 8 --wheel \
    --override "STDFLOAT_DOUBLE=1" 2>&1 | tee build_double.log
mkdir -p wheels_window1/double && mv panda3d-*.whl wheels_window1/double/
```

Sanity marker: the log must show
`Overriding value of key "STDFLOAT_DOUBLE" with value "1"`.
Note: this is upstream's supported flag but their C++17 sweep was never
CI-built with it — if Build 2 fails, that is a FINDING, not a blocker:
bring the log home and Build 1 still completes the window.

## 5. Bring back to the A computer

- `wheels_window1\float\panda3d-1.11.0-cp313-cp313-win_amd64.whl`
- `wheels_window1\double\panda3d-1.11.0-cp313-cp313-win_amd64.whl` (if built)
- `build_float.log` + `build_double.log` (always — even on success)

## 6. Validation back home (A computer — Claude runs this)

Sequential, one variable at a time:

1. **Float wheel** → `pip install --force-reinstall` into `pax3d-env` →
   version check → **full paxtest suite on BOTH engines, both baselines**
   → `test3d_pax.py --selftest` testbed eyeball → sfb2 smoke boot →
   openworld smoke (`main.py --selftest`). Green = the merge is signed
   off; the severed-upstream policy is now fully in force.
   **Rollback if red:** the pre-merge wheel is sheltered on the A
   computer at `wheels_float\panda3d-1.11.0-cp313-cp313-win_amd64.whl`
   (KEEP it there — delete it only from the B-computer copy);
   `pip install --force-reinstall` that file restores today's engine.
   The pre-merge source state is tagged `pre-catchup-merge`.
2. **Doubles wheel** → separate env per
   `sfb2/documents/handover_doubles_spike.md` steps 2–3 (NEVER into
   `pax3d-env`) → `doubles_spike_check.py` → record precision numbers
   against the R4.2 camera-relative decision. The doubles wheel remains
   an experiment — no launcher switches.

## 7. Troubleshooting quick table

| Symptom | Meaning / fix |
|---|---|
| `Cannot open include file: 'windows.h'` | You forgot `--windows-sdk 10` |
| `WARNING: Cannot find mt on search path, skipping` | Expected, harmless (our oscmd patch) |
| Build fails mid-way, flags changed since | `rm -rf built_x64`, rebuild clean |
| `Current directory is not the root of the panda tree` | Run from the repo-copy root |
| `makepanda.bat` errors about win-python3.8 | Never use the .bat — invoke with system Python |
| Warnings about fmod/ffmpeg/fftw/opencv missing | Expected (we exclude them). Warnings about zlib/OpenSSL/OpenGL = broken thirdparty copy — recopy `thirdparty\` |
| pip error fetching panda3d-interrogate | B is offline — pre-seed per §2 |
