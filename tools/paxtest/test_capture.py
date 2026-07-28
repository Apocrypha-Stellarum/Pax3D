"""paxtest: streaming asynchronous framebuffer readback (Session AM,
2026-07-28 — the Animal Crossfire F9-recorder ask).

`pipeline.begin_frame_capture()` hands out a FrameCapture that reads the
window off the render thread: the engine's own PBO round-robin
(`GraphicsOutput::get_async_screenshot` — PBO recycle pool, GL fence,
memcpy on the gl_texture_transfer chain) wrapped in the contract a video
encoder actually needs — ordered delivery, bounded in-flight, drop
accounting. The filing's headline was a +4.7 ms/frame floor from the
synchronous RTM_copy_ram tap, and a projection that 4K put recording out
of reach; this measures both against the async path.

Scene: a full-window card whose colour is restamped every frame, so a
delivered frame's own pixels identify WHICH frame it is — that single
trick gates ordering and frame correspondence together, with no reliance
on timing.

Rows:
  1. builds                 -- frame_capture_supported() + a live capture
  2. format_contract        -- window geometry, 4 components (BGRA),
                               nbytes == w*h*4, data length agrees
  3. frame_correspondence   -- each delivered frame carries the pixels of
                               the frame it was requested on, and they
                               arrive in capture order (0 inversions)
  4. byte_identical_to_sync -- async pixels == synchronous RTM_copy_ram
                               pixels for the same frame, byte for byte
  5. post_processed_view    -- the capture is the tonemapped window image
                               (matches get_screenshot), not the HDR
                               scene buffer
  6. latency_bounded        -- frames from request to delivery
  7. ordering_holds_head    -- a completed request behind an incomplete
                               one is HELD (the guarantee the two-thread
                               transfer chain does not itself make)
  8. in_flight_bounded      -- max_in_flight is a hard cap and the
                               skipped frames are counted, not swallowed
  9. repeat_poll_no_duplicate -- the engine caches ONE request per
                               output and clears it at draw time, so
                               polling twice before a draw hands back
                               the SAME object; enqueued twice it would
                               deliver one frame twice
 10. drain_flushes_tail     -- drain() recovers the in-flight tail
 11. stop_releases/stop_drains_in_flight -- stop() empties the queue AND
                               retires what is still outstanding
 12. engine_survives_inflight_exit -- THE C++ FIX: a subprocess using the
                               RAW get_async_screenshot() API exits with
                               readbacks in flight and must not AV (the
                               wrapper's drain would mask a regression)
 13. cost_beats_sync        -- THE ASK: min-frame-time delta over a
                               no-readback baseline, async vs sync

Pax3D only: stock Panda3D 1.10.16 has no get_async_screenshot (the API
is upstream 1.11-dev, inherited by the Window-1 catch-up merge), so the
whole test skips there rather than adding a permanent red.
"""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import panda3d.core as p3d

import common

TARGET_DT = 1.0 / 60.0
PERF_FRAMES = 90
PERF_WARM = 20


def stamp_color(card, i):
    """Frame i gets a distinct red — the delivered pixels name the frame.

    Spread wide enough that consecutive frames stay distinguishable
    after the tonemap compresses them.
    """
    card.set_color(0.02 + i * 0.02, 0.25, 0.5, 1)


def ram_pixel(frame, x, y):
    """(r, g, b) 0-255 at window pixel (x, y) from a BGRA bottom-up RAM
    image (Panda's convention — the encoder side passes vflip)."""
    row = frame.height - 1 - y
    off = (row * frame.width + x) * frame.num_components
    d = frame.data
    return d[off + 2], d[off + 1], d[off + 0]


class _StubRequest(object):
    """Deterministic stand-in for a ScreenshotRequest (row 7)."""

    def __init__(self, is_done, texture=None):
        self._done = is_done
        self._texture = texture

    def done(self):
        return self._done

    def result(self):
        return self._texture


def make_paced_step(step):
    """A step() paced to 60 fps.

    EVERY functional row uses this. An unpaced harness loop renders at
    ~2000 fps, which outruns the two-thread transfer chain by 30x and
    turns both latency and queue depth into measurement artifacts (the
    first cut of this test read 34-frame latency and 19/60 delivery for
    exactly that reason). Games render paced; measure paced.
    """
    def paced():
        t0 = time.perf_counter()
        step()
        slack = TARGET_DT - (time.perf_counter() - t0)
        if slack > 0:
            time.sleep(slack)
    return paced


def make_stub_texture(w=4, h=4):
    """A tiny RAM-backed texture for the ordering row, so it does not
    depend on a real capture having landed first."""
    tex = p3d.Texture('paxtest_stub')
    tex.setup_2d_texture(w, h, p3d.Texture.T_unsigned_byte,
                         p3d.Texture.F_rgba)
    tex.make_ram_image()
    return tex


def paced_min_frame_ms(step, frames, per_frame=None):
    """Min frame time over a loop paced to 60 fps.

    Min, not mean: the filing used min-frame-time precisely because
    means on a shared box are contention noise.
    """
    for _ in range(PERF_WARM):
        step()
        if per_frame:
            per_frame()
        time.sleep(0.001)
    best = None
    for _ in range(frames):
        t0 = time.perf_counter()
        step()
        if per_frame:
            per_frame()
        dt = time.perf_counter() - t0
        if best is None or dt < best:
            best = dt
        slack = TARGET_DT - dt
        if slack > 0:
            time.sleep(slack)
    return best * 1000.0


def main():
    parser = common.add_common_args(argparse.ArgumentParser())
    args = parser.parse_args()

    h = common.Harness(args, 'capture')
    h.init_pipeline(exposure=0.0, tonemap='hejl_dawson')
    pipeline = getattr(h.adapter, 'pipeline', None)
    if pipeline is None or not hasattr(pipeline, 'begin_frame_capture'):
        h.report.skip('pipeline has no begin_frame_capture (Session AM)')

    from panda3d.core import PandaSystem
    if PandaSystem.get_version_string().startswith('1.10'):
        h.report.skip('stock 1.10: no GraphicsOutput.get_async_screenshot '
                      '(upstream 1.11-dev API, inherited by the Window-1 '
                      'catch-up merge)')

    from pax3d_render import capture as capture_mod

    base = h.base
    win = base.win
    raw_step = base.task_mgr.step
    step = make_paced_step(raw_step)

    # Unlit full-window card: the colour reaches the framebuffer through
    # the real post chain, so row 5 is a genuine end-to-end read.
    h.set_ortho()
    cm = p3d.CardMaker('stamp')
    cm.set_frame(-100, 100, -100, 100)
    card = base.render.attach_new_node(cm.generate())
    card.set_pos(0, 10, 0)
    card.set_light_off(1)
    card.set_shader_off(1)
    stamp_color(card, 0)
    h.step(5)

    # --- 1. builds ----------------------------------------------------
    supported = capture_mod.frame_capture_supported()
    cap = pipeline.begin_frame_capture(max_in_flight=3)
    h.report.check('builds',
                   supported and isinstance(cap, capture_mod.FrameCapture)
                   and cap.in_flight == 0 and cap.requested == 0,
                   f'frame_capture_supported()={supported}, {cap!r}')

    # --- 2/3. correspondence + order ----------------------------------
    # The stamp colour reaches the framebuffer through the tonemap, so
    # the request index is NOT recoverable from the pixels directly.
    # Ground-truth each frame with a synchronous window screenshot taken
    # the same frame, and require the async delivery to reproduce it —
    # a stronger statement than any index arithmetic: frame i's async
    # bytes ARE frame i's window image.
    N = 40
    truth = {}              # frame index -> centre red 0-255, sync screenshot
    req_index = []          # delivery order -> the frame it was requested on
    delivered = []          # (requested_on, matched_content_frame, err)
    latency_first = None
    for i in range(N):
        stamp_color(card, i)
        step()
        truth[i] = round(h.capture().get_xel(h.win_w // 2, h.win_h // 2)[0]
                         * 255)
        before = cap.requested
        frames = cap.poll()
        if cap.requested > before:
            req_index.append(i)
        for f in frames:
            k = len(delivered)
            src_i = req_index[k] if k < len(req_index) else -1
            red = ram_pixel(f, f.width // 2, f.height // 2)[0]
            # Which frame's ground truth do these pixels actually match?
            match = min(truth, key=lambda t: abs(truth[t] - red))
            delivered.append((src_i, match, abs(truth[match] - red),
                              f.frame_number))
            if latency_first is None:
                latency_first = i - src_i

    # --- 2. format contract -------------------------------------------
    probe = None
    stamp_color(card, 77)
    for _ in range(8):
        step()
        got = cap.poll()
        if got:
            probe = got[-1]
    if probe is None:
        h.report.check('format_contract', False, 'no frame delivered')
    else:
        ok = (probe.width == h.win_w and probe.height == h.win_h
              and probe.num_components == 4
              and probe.nbytes == h.win_w * h.win_h * 4
              and len(probe.data) == probe.nbytes)
        h.report.check('format_contract', ok,
                       f'{probe.width}x{probe.height}, '
                       f'{probe.num_components} comps (BGRA), '
                       f'{probe.nbytes} bytes, data len {len(probe.data)} '
                       f'— bottom-up, the pix_fmt x264 ingests unswizzled')

    # --- 3. frame correspondence + ordering ---------------------------
    # Drop the first delivery: its content may predate the truth table.
    body = delivered[1:]
    inexact = [d for d in body if d[2] > 2]
    offsets = [src - match for src, match, _, _ in body]
    fnums = [fn for _, _, _, fn in body]
    inversions = sum(1 for a, b in zip(fnums, fnums[1:]) if b < a)
    offset_set = sorted(set(offsets))
    h.report.check('frame_correspondence',
                   len(delivered) >= N - 6 and not inexact
                   and inversions == 0 and len(offset_set) == 1,
                   f'{len(delivered)}/{len(req_index)} requested frames '
                   f'delivered; every one matches a synchronous ground-truth '
                   f'screenshot EXACTLY ({len(inexact)} over 2/255) at a '
                   f'CONSTANT offset {offset_set} frame(s) behind its request, '
                   f'in capture order ({inversions} inversions). Offset 0 '
                   f'offscreen, 1 on a real double-buffered window (the '
                   f'engine copies after the flip) — constant either way, '
                   f'which is what a recorder needs')

    # --- 6. latency ----------------------------------------------------
    h.report.check('latency_bounded',
                   latency_first is not None and 1 <= latency_first <= 5,
                   f'first delivery {latency_first} frames after its '
                   f'request (the fence + transfer-chain latency; the '
                   f'filing accepts 1-2)')

    # --- 4. byte identity vs the synchronous path ----------------------
    stamp_color(card, 123)
    sync_tex = p3d.Texture('paxtest_sync')
    win.add_render_texture(sync_tex, p3d.GraphicsOutput.RTM_copy_ram)
    h.step(4)
    async_frame = None
    for _ in range(10):
        step()
        got = cap.poll()
        if got:
            async_frame = got[-1]
    sync_bytes = bytes(sync_tex.get_ram_image())
    win.clear_render_textures()
    h.step(2)

    if async_frame is None:
        h.report.check('byte_identical_to_sync', False, 'no async frame')
    else:
        async_bytes = async_frame.tobytes()
        same_len = len(async_bytes) == len(sync_bytes)
        diff = (sum(1 for x, y in zip(async_bytes, sync_bytes) if x != y)
                if same_len else -1)
        h.report.check('byte_identical_to_sync',
                       same_len and diff == 0,
                       f'{len(async_bytes)} bytes, {diff} differing vs the '
                       f'synchronous RTM_copy_ram tap of the same frozen '
                       f'frame — the async path changes cost, not pixels')

    # --- 5. the POST-PROCESSED window image ----------------------------
    stamp_color(card, 180)
    h.step(3)
    img = h.capture()                     # PNMImage, top-down, 0..1
    got = None
    for _ in range(10):
        step()
        frames = cap.poll()
        if frames:
            got = frames[-1]
    if got is None:
        h.report.check('post_processed_view', False, 'no frame delivered')
    else:
        cx, cy = h.win_w // 2, h.win_h // 2
        pr, pg, pb = ram_pixel(got, cx, cy)
        xel = img.get_xel(cx, cy)
        d = max(abs(pr / 255.0 - xel[0]), abs(pg / 255.0 - xel[1]),
                abs(pb / 255.0 - xel[2]))
        h.report.check('post_processed_view', d <= 2.0 / 255.0,
                       f'capture centre ({pr},{pg},{pb}) matches the window '
                       f'screenshot ({xel[0]*255:.0f},{xel[1]*255:.0f},'
                       f'{xel[2]*255:.0f}) to {d*255:.2f}/255 — the tonemapped '
                       f'player view, not the HDR scene buffer')

    # --- 7. ordering holds the head ------------------------------------
    # max_in_flight=2 so poll() cannot append a real request behind the
    # stubs and perturb the count.
    order_cap = pipeline.begin_frame_capture(max_in_flight=2)
    stub_tex = make_stub_texture()
    order_cap._pending = [(1, _StubRequest(False)),
                          (2, _StubRequest(True, stub_tex))]
    held = order_cap.poll()
    blocked_ok = (held == [] and order_cap.in_flight == 2)
    order_cap._pending[0] = (1, _StubRequest(True, stub_tex))
    released = order_cap.poll()
    order_cap.stop()
    h.report.check('ordering_holds_head',
                   blocked_ok and len(released) == 2
                   and [f.frame_number for f in released] == [1, 2],
                   f'a finished request behind an unfinished one is HELD '
                   f'(poll returned {len(held)}), then both release in '
                   f'order ({[f.frame_number for f in released]}) — the '
                   f'2-thread transfer chain makes no completion-order '
                   f'guarantee, so the queue does')

    # --- 8. in-flight bound + drop accounting --------------------------
    cap2 = pipeline.begin_frame_capture(max_in_flight=2)
    peak = 0
    for i in range(40):
        stamp_color(card, i)
        step()
        cap2.poll()
        peak = max(peak, cap2.in_flight)
    h.report.check('in_flight_bounded',
                   peak <= 2 and (cap2.requested + cap2.dropped) == 40,
                   f'peak in-flight {peak} <= cap 2; 40 frames accounted '
                   f'as {cap2.requested} requested + {cap2.dropped} dropped '
                   f'(each in-flight readback holds a whole frame — '
                   f'{h.win_w * h.win_h * 4 / 1e6:.2f} MB here, 33 MB at 4K)')

    # --- 8b. double poll in one frame must not duplicate a frame -------
    # The engine caches ONE screenshot request per output and clears it
    # at draw time, so a second get_async_screenshot() before the next
    # draw returns the SAME object. Tracked twice, it would deliver one
    # captured frame twice — a duplicated video frame, intermittently.
    dup_cap = pipeline.begin_frame_capture(max_in_flight=6)
    stamp_color(card, 90)
    step()
    dup_cap.poll()
    dup_cap.poll()              # same frame, no draw in between
    dup_cap.poll()
    tracked = dup_cap.requested
    repeats = dup_cap.repeat_polls
    got_frames = []
    for _ in range(8):
        step()
        got_frames.extend(dup_cap.poll())
    fnums = [f.frame_number for f in got_frames]
    dup_cap.stop()
    h.report.check('repeat_poll_no_duplicate',
                   tracked == 1 and repeats == 2
                   and len(fnums) == len(set(fnums)),
                   f'3 polls with one draw tracked {tracked} request '
                   f'({repeats} repeats skipped); delivered frame numbers '
                   f'{fnums} are unique — the per-output cached request '
                   f'cannot be enqueued twice (identity by .this, fact #20)')

    # --- 9. drain flushes the tail -------------------------------------
    before_inflight = cap2.in_flight
    tail = cap2.drain(timeout_frames=8, step=step)
    h.report.check('drain_flushes_tail',
                   cap2.in_flight == 0 and len(tail) == before_inflight,
                   f'drain recovered the {len(tail)}-frame tail that was '
                   f'still in flight ({before_inflight} pending), leaving '
                   f'{cap2.in_flight}')

    # --- 10. stop ------------------------------------------------------
    cap2.stop()
    step()
    after = cap2.poll()
    h.report.check('stop_releases',
                   after == [] and cap2.in_flight == 0,
                   'stop() empties the queue and poll() is inert')

    # --- 10b. stop() DRAINS — the shutdown crash guard ------------------
    # On pre-2026-07-28 wheels a readback still in flight at process
    # exit segfaulted it (GSG fence deque -> CompletionToken "destroyed
    # prematurely == complete(false)" -> the screenshot callback ignored
    # the flag and called GL on a dying GSG). ONE was enough; cancel()
    # and remove_all_windows() did not help. Fixed engine-side in the
    # Session AM build window and gated below by
    # engine_survives_inflight_exit; the drain stays because it also
    # recovers the tail and keeps older wheels safe.
    drain_cap = pipeline.begin_frame_capture(max_in_flight=4)
    for _ in range(4):
        step()
        drain_cap.poll()
    watched = [r for _, r in drain_cap._pending]
    live_before = sum(1 for r in watched if not r.done())
    drain_cap.stop()
    live_after = sum(1 for r in watched if not r.done())
    h.report.check('stop_drains_in_flight',
                   live_before > 0 and live_after == 0
                   and drain_cap.in_flight == 0,
                   f'{live_before} readback(s) in flight at stop(); '
                   f'{live_after} still outstanding afterwards — stop() '
                   f'renders engine frames until the GSG fences retire '
                   f'(leaving even one in flight AVs the process at exit; '
                   f'C++ fix queued)')
    h.report.info('shutdown_exit_code',
                  'this process exits AFTER a capture has run — a nonzero '
                  'exit here (139/0xC0000005) is a regression signal, and '
                  'run.py now cross-checks the child exit code against the '
                  'reported status')

    # --- 10c. THE ENGINE FIX, gated independently of the wrapper -------
    # FrameCapture.stop() drains, so it would MASK a regression of the
    # C++ fix. This subprocess uses the RAW get_async_screenshot() API
    # and exits with readbacks deliberately in flight: its exit code is
    # the engine verdict. Measured 139 on the pre-fix wheel, 0 after
    # (glGraphicsStateGuardian_src.cxx honors the CompletionToken
    # abandonment flag instead of doing GL on a dying GSG).
    probe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'probe_async_shutdown.py')
    try:
        proc = subprocess.run([sys.executable, probe_path],
                              capture_output=True, text=True, timeout=120)
        out = (proc.stdout or '') + (proc.stderr or '')
        in_flight = 0
        for line in out.splitlines():
            if line.startswith('IN_FLIGHT'):
                try:
                    in_flight = int(line.split()[1])
                except (IndexError, ValueError):
                    pass
        h.report.check('engine_survives_inflight_exit',
                       proc.returncode == 0 and in_flight > 0,
                       f'raw get_async_screenshot(), {in_flight} readback(s) '
                       f'still in flight at process exit: child exited '
                       f'{proc.returncode} (139/0xC0000005 = the AV this '
                       f'gates; measured on the pre-fix wheel). Uses the raw '
                       f'API on purpose — FrameCapture.stop() drains and '
                       f'would hide an engine regression')
    except subprocess.TimeoutExpired:
        h.report.check('engine_survives_inflight_exit', False,
                       'probe_async_shutdown hung past 120s')

    # --- 11. THE ASK: cost vs the synchronous tap ----------------------
    cap.stop()
    h.step(3)
    # paced_min_frame_ms does its OWN pacing — hand it the raw step so
    # the sleep is not counted inside the measured interval.
    base_ms = paced_min_frame_ms(raw_step, PERF_FRAMES)

    sync_tex2 = p3d.Texture('paxtest_sync_perf')
    win.add_render_texture(sync_tex2, p3d.GraphicsOutput.RTM_copy_ram)

    def sync_grab():
        img_ = sync_tex2.get_ram_image()
        if img_:
            _ = bytes(img_)

    sync_ms = paced_min_frame_ms(raw_step, PERF_FRAMES, sync_grab)
    win.clear_render_textures()
    h.step(2)

    cap3 = pipeline.begin_frame_capture(max_in_flight=3)

    def async_grab():
        for f in cap3.poll():
            _ = f.data[0]          # touch the mapped pixels

    async_ms = paced_min_frame_ms(raw_step, PERF_FRAMES, async_grab)
    cap3.stop()

    sync_delta = sync_ms - base_ms
    async_delta = async_ms - base_ms
    h.report.check('cost_beats_sync',
                   sync_delta > 0.5 and async_delta < sync_delta * 0.5,
                   f'min-frame-time over a no-readback baseline '
                   f'({base_ms:.3f} ms): sync +{sync_delta:.3f} ms, '
                   f'async +{async_delta:.3f} ms at {h.win_w}x{h.win_h} '
                   f'— the readback stall the filing measured is off the '
                   f'render thread')
    h.report.info('cost_numbers',
                  f'baseline {base_ms:.3f} ms | sync {sync_ms:.3f} ms | '
                  f'async {async_ms:.3f} ms (min of {PERF_FRAMES} frames '
                  f'paced to 60 fps)')

    h.report.finish()


if __name__ == '__main__':
    main()
