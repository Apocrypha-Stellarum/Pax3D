"""paxtest: Thread.bind_thread must pin bound external threads
(engine-level).

Field crashes 2026-07-25/26 (paxcraft chunk streamer; reproduced at
workers=2 = the sfb2 shipping envelope): Thread.bind_thread() returns a
fresh ExternalThread whose ONLY reference is the returned PT(Thread);
the impl stores a raw pointer in TLS.  Every measured consumer drops the
return value (sfb2 planetside chunks.py, paxcraft, repro_min's own
_bind), deleting the ExternalThread under the TLS pointer -- once the
freed block is reused, get_pipeline_stage() reads garbage, the
release-mode cycler paths index _data[garbage] unchecked, and Geom
construction on that worker AVs (2026-07-26 minidump: ref() on a null
CycleData inside GeomPrimitivePipelineReader under close_primitive).
Root cause + forensics: documents/CRASH_BIND_THREAD_DANGLE.md.

Fixed by pinning the bound thread engine-side (thread.cxx bind_thread
ref(); a deliberate bounded leak, one small object per bound thread).

Rows:
  bind_pinned        -- bind_thread ref count >= 2 AND the dangle
                        survives drop+gc+churn (Pax3D only: stock 1.10
                        auto-falls-back to the global ExternalThread for
                        foreign threads and has no pin contract)
  bound_churn_render -- the paxcraft envelope: 5 bound workers building
                        Geoms against a live offscreen render loop,
                        30 s survival (both engines)

Engine-level test: runs on the 'none' pipeline only; the repro
subprocesses open their own offscreen contexts as needed.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

HERE = os.path.dirname(os.path.abspath(__file__))
REPRO = os.path.normpath(os.path.join(HERE, os.pardir, 'repro_gvad_race',
                                      'repro_min.py'))


def run_repro(extra, timeout):
    cmd = [sys.executable, REPRO] + extra
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout)


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    report = common.TestReport('thread_bind', args)
    if args.pipeline != 'none':
        report.skip('engine-level test, none pipeline only')

    from panda3d.core import PandaSystem
    is_stock = PandaSystem.get_version_string().startswith('1.10')
    if is_stock:
        # Stock inherits the same raw-TLS "caller's responsibility"
        # contract and has no pin: measured 2026-07-26, the discard-shape
        # bound_churn_render row AVs (0xC0000005) on stock 1.10.16 —
        # upstream-inherited bug class, not a Pax3D regression.  Stock is
        # a read-only reference (never patched by policy), so the whole
        # test skips rather than adding a permanent red to its FAIL set.
        report.skip('stock 1.10: no bind-pin contract; discard-shape '
                    'churn AVs upstream too (CRASH_BIND_THREAD_DANGLE.md)')

    if not is_stock:
        try:
            proc = run_repro(['--level', 'bind-pin'], 60)
            pinned = (proc.returncode == 0 and 'PINNED' in proc.stdout
                      and 'UNPINNED' not in proc.stdout)
            tail = (proc.stdout + '\n' + proc.stderr).strip().splitlines()
            detail = '; '.join(t.strip() for t in tail[-2:]) if tail else ''
            report.check('bind_pinned', pinned,
                         f'exit {proc.returncode}: {detail}')
        except subprocess.TimeoutExpired:
            report.check('bind_pinned', False, 'probe hung past 60s')

    try:
        proc = run_repro(['--level', 'full', '--workers', '5',
                          '--seconds', '30', '--render', '--attach'], 150)
        survived = (proc.returncode == 0 and 'SURVIVED' in proc.stdout)
        tail = (proc.stdout + '\n' + proc.stderr).strip().splitlines()
        detail = tail[-1].strip() if tail else ''
        report.check('bound_churn_render', survived,
                     f'exit {proc.returncode}: {detail}')
    except subprocess.TimeoutExpired:
        report.check('bound_churn_render', False,
                     'repro hung past 150s (deadlock class, not AV class)')

    report.finish()


if __name__ == '__main__':
    main()
