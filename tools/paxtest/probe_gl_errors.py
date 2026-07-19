"""probe: per-frame GL errors for PLAYING characters in offscreen windows.

Field report (FPS lane, 2026-07-19, sfb2 test_weapon_system.py): one
"benign" GL_INVALID_OPERATION per frame for any playing character in a
bare offscreen ShowBase (no pipeline, FFP or shader, software or
hardware skinning); the engine's error sweep then hits gl-max-errors
(default 20) and panic-deactivates the GSG — frozen framebuffer,
silently stale screenshots. Their workaround: gl-max-errors 1000000
(-1 is broken: the >= at glGraphicsStateGuardian_src.cxx:4817 fires
instantly on -1 — separate bug, fix queued).

This probe measures WHERE the errors come from:

  * The engine only sweeps glGetError once per second in release builds
    (per-call checks compile out). Trick: pin the global clock to
    dt=1.1 s so the sweep runs EVERY frame — per-frame attribution
    without a debug build.
  * Phases: empty scene / character loaded static / character PLAYING /
    stopped again — the error count delta names the trigger.
  * --gl-debug turns on the KHR_debug callback (driver-level messages,
    exact failing call) where the context supports it.

Run on BOTH engines and BOTH baselines (the field claim is fork-only —
verify): every combination of
    C:/Python313/python.exe | C:/python/pax3d-env/Scripts/python.exe
    [--baseline modern] [--gl-debug] [--show]
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAX3D_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, PAX3D_ROOT)

import panda3d.core as p3d

ASSET = os.path.join(HERE, 'assets', 'morph_head_skinned_anim.glb')
LOG = os.path.join(HERE, 'output', 'probe_gl_errors_notify.log')

FRAMES = 30


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', default='game',
                        choices=['game', 'modern'])
    parser.add_argument('--gl-debug', action='store_true')
    parser.add_argument('--show', action='store_true')
    parser.add_argument('--hw-skinning', action='store_true',
                        help='basic-shaders-only #f + a Shader.load-less '
                             'auto-shader so the skinning path is GPU')
    parser.add_argument('--empty-only', action='store_true',
                        help='just the empty-scene phase (wheel bisection: '
                             'no gltf/pax3d_render imports needed)')
    args = parser.parse_args()

    prc = [
        'win-size 256 256',
        'audio-library-name null',
        'sync-video 0',
        'gl-max-errors 1000000',
    ]
    if not args.show:
        prc.append('window-type offscreen')
    if args.baseline == 'modern':
        prc.append('gl-version 3 2')
    if args.gl_debug:
        prc.append('gl-debug 1')
        prc.append('notify-level-glgsg debug')
    for line in prc:
        p3d.load_prc_file_data('probe', line)

    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if os.path.exists(LOG):
        os.remove(LOG)
    ms = p3d.MultiplexStream()
    ms.add_file(p3d.Filename.from_os_specific(LOG))
    ms.add_standard_output()
    p3d.Notify.ptr().set_ostream_ptr(ms, False)

    from direct.showbase.ShowBase import ShowBase

    base = ShowBase()
    base.disable_mouse()

    # dt > 1s: the engine's once-per-second glGetError sweep runs every
    # frame -> per-frame error attribution in a release build.
    clock = p3d.ClockObject.get_global_clock()
    clock.set_mode(p3d.ClockObject.M_non_real_time)
    clock.set_dt(1.1)

    def errors_so_far():
        ms.flush()
        if not os.path.exists(LOG):
            return 0, []
        text = open(LOG, 'r', errors='replace').read()
        lines = [ln for ln in text.splitlines()
                 if 'GL error' in ln or 'invalid operation' in ln.lower()
                 or 'GL_INVALID' in ln]
        return len(lines), lines

    def phase(name, frames=FRAMES):
        n0, _ = errors_so_far()
        for _ in range(frames):
            base.task_mgr.step()
        n1, lines = errors_so_far()
        print(f'PROBE {name}: +{n1 - n0} error lines over {frames} frames')
        return n1 - n0, lines

    print(f'PROBE engine={p3d.PandaSystem.get_version_string()} '
          f'baseline={args.baseline} show={args.show} '
          f'gl_debug={args.gl_debug}')

    phase('empty_scene')
    if args.empty_only:
        return

    from direct.actor.Actor import Actor
    from pax3d_render import gltf_compat
    gltf_compat.install()
    actor = Actor(p3d.Filename.from_os_specific(ASSET).get_fullpath())
    actor.reparent_to(base.render)
    actor.set_pos(0, 5, 0)
    if args.hw_skinning:
        actor.set_shader_auto()
    phase('actor_static')

    names = actor.get_anim_names()
    print(f'PROBE clips: {names}')
    actor.loop(names[0])
    d_play, lines = phase('actor_PLAYING')

    actor.stop()
    phase('actor_stopped')

    actor.pose(names[0], 0)
    phase('actor_posed_frame0')

    # Force per-frame pose churn WITHOUT playback (isolates "animating"
    # from "playing"): pose to alternating frames each step.
    n0, _ = errors_so_far()
    for i in range(FRAMES):
        actor.pose(names[0], i % 30)
        base.task_mgr.step()
    n1, _ = errors_so_far()
    print(f'PROBE actor_pose_churn: +{n1 - n0} error lines '
          f'over {FRAMES} frames')

    if lines:
        print('PROBE sample error lines (playing phase):')
        for ln in lines[-6:]:
            print('   | ' + ln)

    tail = [ln for ln in open(LOG, 'r', errors='replace').read().splitlines()
            if re.search(r'error|invalid|deactivat', ln, re.I)][-12:]
    print('PROBE notify tail (error-ish lines):')
    for ln in tail:
        print('   | ' + ln)


if __name__ == '__main__':
    main()
