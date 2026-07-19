"""paxtest: offscreen frames must not generate GL errors (engine-level).

Field report (FPS lane, 2026-07-19): "one benign GL_INVALID_OPERATION
per frame for any PLAYING character in a bare offscreen window
deactivates the GSG after 20 [seconds]; screenshots go silently stale."
Measured truth (probe_gl_errors.py matrix): the character is irrelevant
— the 1.11 fork emits exactly one GL_INVALID_OPERATION per frame on an
EMPTY offscreen scene, both baselines; a real window is clean; stock
1.10.16 is clean everywhere. Root cause: upstream `bd4dc8a379` (a DX9
buffer-copy fix, pre-divergence) gutted the single-buffered branch of
FrameBufferProperties::get_buffer_mask(), so prepare_display_region
issues glDrawBuffer(GL_BACK) on the single-buffered wgl pbuffer every
frame. Fix queued: documents/PATCH_QUEUE_GL_OFFSCREEN.md.

This row asserts the CURRENT truth per engine, alpha-mask defect-row
style:
  * stock 1.10: zero error lines (the clean reference);
  * Pax3D 1.11 pre-patch: the defect fires at ~1/frame — asserted
    PRESENT so the queued patch fails this row "the good way";
    WHEN THE PATCH LANDS: flip `expect_defect` below to False and this
    row becomes the permanent zero-GL-errors guard for offscreen runs.

Engine-level test: runs on the 'none' pipeline only (no post stack —
the raw offscreen window is the subject).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

FRAMES = 30

# Flip to False when the PATCH_QUEUE_GL_OFFSCREEN.md window lands.
EXPECT_DEFECT_ON_1_11 = True

LOG = os.path.join(common.OUTPUT_DIR, 'gl_clean_notify.log')


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    if args.pipeline != 'none':
        # Engine-level check; the raw window is the subject
        print(f'[SKIP] gl_clean/{args.pipeline}: engine-level test, '
              f'runs on the none pipeline only')
        import json
        print('PAXTEST_JSON: ' + json.dumps({
            'test': 'gl_clean', 'pipeline': args.pipeline,
            'baseline': args.baseline, 'win_size': args.win_size,
            'status': 'SKIP',
            'reason': 'engine-level test, none pipeline only',
            'checks': []}))
        sys.exit(common.EXIT_SKIP)

    if args.show:
        print('[SKIP] gl_clean: offscreen is the subject (drop --show)')
        sys.exit(common.EXIT_SKIP)

    # The error sweep must never deactivate the GSG mid-measurement
    # (default gl-max-errors 20 would, ~20 frames into the fork run)
    p3d.load_prc_file_data('gl_clean', 'gl-max-errors 1000000')

    os.makedirs(common.OUTPUT_DIR, exist_ok=True)
    if os.path.exists(LOG):
        os.remove(LOG)
    ms = p3d.MultiplexStream()
    ms.add_file(p3d.Filename.from_os_specific(LOG))
    ms.add_standard_output()
    p3d.Notify.ptr().set_ostream_ptr(ms, False)

    h = common.Harness(args, 'gl_clean')
    h.init_pipeline()

    # dt > 1s: the engine's once-per-second glGetError sweep runs every
    # frame — per-frame error visibility in a release build
    clock = p3d.ClockObject.get_global_clock()
    clock.set_mode(p3d.ClockObject.M_non_real_time)
    clock.set_dt(1.1)

    h.step(FRAMES)
    ms.flush()

    lines = []
    if os.path.exists(LOG):
        lines = [ln for ln in
                 open(LOG, 'r', errors='replace').read().splitlines()
                 if 'GL error 0x' in ln]
    n = len(lines)

    major = p3d.PandaSystem.get_major_version()
    minor = p3d.PandaSystem.get_minor_version()
    is_fork = (major, minor) >= (1, 11)
    h.report.info('engine', f'{p3d.PandaSystem.get_version_string()} '
                            f'({n} GL error lines over {FRAMES} frames)')

    if is_fork and EXPECT_DEFECT_ON_1_11:
        h.report.check(
            'offscreen_glDrawBuffer_defect_present', n >= FRAMES - 5,
            f'{n} errors/{FRAMES} frames — KNOWN defect '
            f'(PATCH_QUEUE_GL_OFFSCREEN.md); when the patch lands this '
            f'fails the good way: flip EXPECT_DEFECT_ON_1_11 to False')
    else:
        h.report.check('offscreen_frames_gl_clean', n == 0,
                       f'{n} GL error lines over {FRAMES} frames')

    h.report.check('gsg_still_active',
                   h.base.win.get_gsg().is_active(), '')

    h.report.finish()


if __name__ == '__main__':
    main()
