"""Repro/probe: exit the process with async screenshot readbacks IN FLIGHT.

Session AM found that a readback still outstanding when the process
exits AVs it — ONE is enough, on both a real window and an offscreen
buffer. Mechanism: the GL GSG's `_fences` deque holds
Fence{GLsync, CompletionToken}; CompletionToken's contract is that a
token destroyed before it completes calls its callback with
success=false so cleanup can run (completionToken.I). The screenshot
fence callback ignored that flag and ran its normal body anyway —
map_read_buffer() (a GL call) plus GSG member access — against a GSG
that is already being destroyed.

Fixed engine-side by honoring the flag (glGraphicsStateGuardian_src.cxx,
`// PAX3D:` tag): on abandonment do no GL, touch no GSG state, cancel
the future.

This probe deliberately uses the RAW engine API, NOT
pax3d_render.capture.FrameCapture — the wrapper drains on stop(), which
is the Python-side mitigation and would hide an engine regression. Run
by test_capture as a subprocess; the ENGINE verdict is the exit code.

  exit 0   = clean shutdown with readbacks in flight (fixed)
  exit 139 / 0xC0000005 = the AV (regressed)

Usage: probe_async_shutdown.py [--requests N] [--show]
"""
import sys

import panda3d.core as p3d

REQUESTS = 8
for i, a in enumerate(sys.argv):
    if a == '--requests':
        REQUESTS = int(sys.argv[i + 1])
SHOW = '--show' in sys.argv

lines = ['win-size 640 360', 'window-title probe-async-shutdown',
         'audio-library-name null', 'sync-video 0',
         'show-frame-rate-meter 0', 'textures-power-2 none',
         'color-bits 8 8 8', 'depth-bits 24', 'multisamples 0',
         'gl-version 3 2']
if not SHOW:
    lines.append('window-type offscreen')
for line in lines:
    p3d.load_prc_file_data('probe', line)

if not hasattr(p3d.GraphicsOutput, 'get_async_screenshot'):
    print('SKIP: no get_async_screenshot on this engine')
    sys.exit(77)

from direct.showbase.ShowBase import ShowBase

base = ShowBase()
base.disable_mouse()
win = base.win
step = base.task_mgr.step

cm = p3d.CardMaker('card')
cm.set_frame(-1, 1, -1, 1)
card = base.render.attach_new_node(cm.generate())
card.set_pos(0, 10, 0)
card.set_color(0.4, 0.6, 0.8, 1)

for _ in range(10):
    step()

# Issue readbacks and step just enough that they are queued but NOT
# retired. Deliberately no drain, no stop, no wait.
pending = []
for i in range(REQUESTS):
    pending.append(win.get_async_screenshot())
    step()

live = sum(1 for r in pending if not r.done())
print(f'IN_FLIGHT {live} of {REQUESTS} at exit')
if live == 0:
    # Nothing outstanding means the probe proved nothing; say so loudly
    # rather than passing vacuously.
    print('INCONCLUSIVE: everything retired before exit')
    sys.stdout.flush()
    sys.exit(70)
print('EXITING with readbacks in flight')
sys.stdout.flush()
