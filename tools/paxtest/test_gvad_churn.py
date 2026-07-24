"""paxtest: threaded GeomVertexData churn must not corrupt the heap
(engine-level).

Field crashes 2026-07-20 + 2026-07-23 (planetside chunk mesher, two
worker threads inside build_chunk_geomnode): any cross-thread
GeomVertexArrayData handle acquisition (get_handle / modify_handle /
anything built on them) concurrent with Geom-class destruction on
another thread corrupts the heap — AV in under 60 s on the Session-X
wheel, every run. Full root-cause analysis in
documents/CRASH_GVAD_HANDLE_RACE.md; repro + dump forensics in
tools/repro_gvad_race/. Fixed by the GVAD stability window
(USE_DELETED_CHAIN restored alongside mimalloc + both cycler stage
guards back to #ifndef NDEBUG + the set_num_stages interior delete).

This row runs the canonical repro recipe as subprocesses and asserts
survival. It must FAIL on any pre-fix 1.11 wheel (the repro AVs, the
child exits nonzero) and PASS on the fixed wheel and on stock 1.10.16
(measured immune at 548k builds).

Engine-level test: runs on the 'none' pipeline only; no window needed.
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

# (level, soak seconds). handle-only is the sharpest distilled trigger
# (AV < 60 s every run on a broken wheel); full is the field workload
# class (the chunk-mesher recipe). Budget stays inside the runner's
# 180 s job timeout.
ROWS = [('handle-only', 60), ('full', 30)]


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    report = common.TestReport('gvad_churn', args)
    if args.pipeline != 'none':
        report.skip('engine-level test, none pipeline only')

    for level, seconds in ROWS:
        cmd = [sys.executable, REPRO, '--level', level,
               '--seconds', str(seconds)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=seconds + 90)
        except subprocess.TimeoutExpired:
            report.check(f'churn_{level}_survives', False,
                         f'repro hung past {seconds + 90}s '
                         f'(deadlock class, not the AV class)')
            continue
        survived = (proc.returncode == 0 and 'SURVIVED' in proc.stdout)
        tail = (proc.stdout + '\n' + proc.stderr).strip().splitlines()
        detail = tail[-1].strip() if tail else ''
        report.check(f'churn_{level}_survives', survived,
                     f'exit {proc.returncode}: {detail}')

    report.finish()


if __name__ == '__main__':
    main()
