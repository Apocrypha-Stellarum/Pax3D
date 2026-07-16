"""paxtest runner: executes each (test, pipeline) combination in its own
subprocess (Panda3D allows one ShowBase per process) and prints a summary.

    python tools/paxtest/run.py
    python tools/paxtest/run.py --tests gamma,bloom --pipelines pax_pbr
    python tools/paxtest/run.py --baseline modern

Exit code 0 = no failures (skips are fine), 1 = failures or errors.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(HERE, 'output')

ALL_TESTS = ['gamma', 'lighting', 'bloom', 'rebuild', 'shadows', 'ftl_blur',
             'scale']
ALL_PIPELINES = ['none', 'simplepbr', 'pax3d_simplepbr', 'pax_pbr',
                 'pax3d_render']

# Bloom runs twice: a size that divides evenly through the 1/32 mip chain,
# and a game-like size that does not (localizes truncation bugs).
BLOOM_WIN_SIZES = ['512x512', '960x540']

# Tests that are meaningless for a pipeline are skipped by the test itself
# (exit 77); the runner just reports what happened.


def run_one(test, pipeline, extra_args, timeout=180):
    script = os.path.join(HERE, f'test_{test}.py')
    cmd = [sys.executable, script, '--pipeline', pipeline] + extra_args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'test': test, 'pipeline': pipeline, 'status': 'ERROR',
                'reason': f'timeout after {timeout}s', 'checks': []}

    payload = None
    for line in proc.stdout.splitlines():
        if line.startswith('PAXTEST_JSON: '):
            try:
                payload = json.loads(line[len('PAXTEST_JSON: '):])
            except json.JSONDecodeError:
                pass
    if payload is None:
        tail = '\n'.join((proc.stdout + '\n' + proc.stderr)
                         .strip().splitlines()[-12:])
        payload = {'test': test, 'pipeline': pipeline, 'status': 'ERROR',
                   'reason': f'no result (exit {proc.returncode})',
                   'output_tail': tail, 'checks': []}
    for i, arg in enumerate(extra_args):
        if 'x' in arg and arg[0].isdigit():
            payload['win_size'] = arg
        if arg == '--sun-mode' and i + 1 < len(extra_args):
            payload['variant'] = extra_args[i + 1]
        if arg == '--log-depth':
            payload['variant'] = 'logdepth'
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tests', default=','.join(ALL_TESTS))
    parser.add_argument('--pipelines', default=','.join(ALL_PIPELINES))
    parser.add_argument('--baseline', default='game',
                        choices=['game', 'modern'])
    parser.add_argument('--golden', action='store_true')
    parser.add_argument('--check-golden', action='store_true')
    args = parser.parse_args()

    tests = [t.strip() for t in args.tests.split(',') if t.strip()]
    pipelines = [p.strip() for p in args.pipelines.split(',') if p.strip()]

    passthrough = ['--baseline', args.baseline]
    if args.golden:
        passthrough.append('--golden')
    if args.check_golden:
        passthrough.append('--check-golden')

    jobs = []
    for test in tests:
        for pipeline in pipelines:
            if test == 'bloom':
                for size in BLOOM_WIN_SIZES:
                    jobs.append((test, pipeline,
                                 passthrough + ['--win-size', size]))
            else:
                jobs.append((test, pipeline, list(passthrough)))
            if test == 'lighting' and pipeline == 'pax3d_render':
                # R2: also verify the real-DirectionalLight sun mode
                jobs.append((test, pipeline,
                             passthrough + ['--sun-mode', 'directional']))
            if test == 'scale' and pipeline == 'pax3d_render':
                # R4.1: the log-depth acceptance run (must PASS, unlike the
                # default run which documents the engine baseline)
                jobs.append((test, pipeline, passthrough + ['--log-depth']))

    results = []
    print(f'paxtest: {len(jobs)} jobs, python={sys.executable}, '
          f'baseline={args.baseline}\n')
    for test, pipeline, extra in jobs:
        size = ''
        if '--win-size' in extra:
            size = ' @' + extra[extra.index('--win-size') + 1]
        if '--sun-mode' in extra:
            size += ' @' + extra[extra.index('--sun-mode') + 1]
        if '--log-depth' in extra:
            size += ' @logdepth'
        label = f'{test}/{pipeline}{size}'
        print(f'--- {label} ---')
        result = run_one(test, pipeline, extra)
        results.append(result)
        status = result['status']
        if status == 'SKIP':
            print(f'  SKIP: {result.get("reason", "")}')
        elif status == 'ERROR':
            print(f'  ERROR: {result.get("reason", "")}')
            if result.get('output_tail'):
                for line in result['output_tail'].splitlines():
                    print(f'    | {line}')
        else:
            for c in result['checks']:
                mark = {'PASS': ' ok ', 'FAIL': 'FAIL',
                        'INFO': 'info'}[c['status']]
                print(f'  [{mark}] {c["name"]}  {c["detail"]}')
        print()

    # Summary matrix
    print('=' * 72)
    n_fail = n_err = 0
    for r in results:
        size = f' @{r.get("win_size", "")}' if r.get('win_size') else ''
        if r.get('variant'):
            size += f' @{r["variant"]}'
        counts = {'PASS': 0, 'FAIL': 0, 'INFO': 0}
        for c in r.get('checks', []):
            counts[c['status']] += 1
        status = r['status']
        if status == 'FAIL':
            n_fail += 1
        elif status == 'ERROR':
            n_err += 1
        print(f'{status:6} {r["test"]}/{r["pipeline"]}{size}   '
              f'({counts["PASS"]} pass, {counts["FAIL"]} fail)')
    print('=' * 72)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    report_path = os.path.join(OUTPUT_DIR, 'last_run.json')
    with open(report_path, 'w', encoding='utf8') as f:
        json.dump({'python': sys.executable, 'baseline': args.baseline,
                   'results': results}, f, indent=2)
    print(f'full report: {report_path}')
    print(f'captures:    {OUTPUT_DIR}')

    sys.exit(1 if (n_fail or n_err) else 0)


if __name__ == '__main__':
    main()
