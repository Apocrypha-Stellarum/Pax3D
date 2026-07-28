"""Streaming frame capture — asynchronous framebuffer readback for video
recording and replay (2026-07-28, Session AM; the Animal Crossfire F9
recorder ask, filed as the "PBO round-robin readback" build-window item).

THE FINDING THAT MADE THIS PYTHON-ONLY: the engine already owns the PBO
round-robin. `GraphicsOutput::get_async_screenshot()` (upstream 1.11-dev,
inherited by the Window-1 catch-up merge — stock 1.10.16 does NOT have
it) binds a pixel-pack buffer from a size-keyed recycle pool, persistently
mapped where GL_ARB_buffer_storage allows, issues glReadPixels into it,
inserts a GL fence, and on fence completion maps and memcpys the pixels on
the two-thread `gl_texture_transfer` task chain. No stall, one small
fixed latency. What was missing was not the mechanism but the CONTRACT a
recorder needs on top of it, which is what this module is:

  - ORDERED delivery. A video encoder that ingests frames out of order
    produces scrambled output. Completions are emitted strictly in
    request order (a completed frame waits behind an incomplete
    predecessor). Measured in-gate as already in order at low load, but
    the chain has two worker threads and no cross-thread completion-order
    guarantee, so the queue enforces it rather than trusting it.
  - BOUNDED memory. Each in-flight request holds a full frame (5.8 MB at
    1600x900, 33 MB at 4K). An unbounded requester outruns the transfer
    chain: an unpaced test loop reached 120 in flight (~690 MB) in two
    seconds. `max_in_flight` caps it and counts what it skipped, so a
    recorder can account for dropped frames instead of swallowing GB.
  - An orderly shutdown. stop() retires what is still in flight and the
    pipeline stops every capture on cleanup(). This began as a crash
    guard: on wheels before 2026-07-28 a readback still in flight when
    the process exited segfaulted it — one was enough — because the
    GSG's fence deque holds CompletionTokens documented as "destroyed
    prematurely == complete(false)" and the screenshot fence callback
    ignored its success flag, running GL work against a GSG that was
    already going away. That is FIXED in the engine now (Session AM
    build window, `// PAX3D:` in glGraphicsStateGuardian_src.cxx;
    gated by test_capture's engine_survives_inflight_exit, which uses
    the raw API precisely so this wrapper cannot mask a regression).
    The drain stays: it is correct hygiene, it delivers the tail
    frames a recorder would otherwise lose to latency, and it keeps
    this module safe on older wheels.

Measured on this machine (RTX 4060 laptop, offscreen buffer, paced to
60 fps, cost over a no-readback baseline):

                      1600x900              3840x2160
    sync copy_ram     +3.92 ms p50          +13.29 ms p50
                      +9.91 ms p95          +22.86 ms p95
    async (this)      +0.19 ms p50          +0.56 ms p50
                      +0.13 ms p95          +2.26 ms p95

    latency           2 frames              2-3 frames

That closes the filing's headline number (a +4.7 ms/frame floor at 900p
on their box) and its projection that 4K put recording out of reach. In
the gate (1600x900, min-frame-time, the filing's own metric) the async
delta lands inside baseline noise: sync +2.19 ms, async -0.10 ms.
Delivered bytes are byte-identical to the synchronous RTM_copy_ram
path — 0 differing bytes of 5,760,000 in-gate.

Pixel layout is the framebuffer's, unchanged by this module: BGRA, 4
components, 8 bits each, BOTTOM-UP (Panda's RAM image convention — the
filing's encoder already passes `vflip`, and `bgra` is exactly the
pix_fmt x264 ingests without swizzle).

Usage — call poll() exactly once per rendered frame:

    cap = pipeline.begin_frame_capture(max_in_flight=3)
    ...
    for frame in cap.poll():          # per frame, after render
        encoder.write(frame.data)     # BGRA, bottom-up
    ...
    for frame in cap.drain():         # flush the in-flight tail
        encoder.write(frame.data)
    cap.stop()                        # REQUIRED before exit — see stop()

The capture reads the WINDOW, i.e. the final tonemapped, post-processed
image the player sees — not the scene HDR buffer.

One behaviour to know: on a real double-buffered window the delivered
frame is ONE behind the request, because the engine copies at the start
of the next frame's draw, after the flip. Offscreen buffers have no swap
and return the requested frame. The offset is constant either way
(measured 47/48 at exactly 1, never garbage), so `frame_number` names
the frame the request was made on, not necessarily the frame the pixels
came from.
"""

__all__ = ['CapturedFrame', 'FrameCapture', 'frame_capture_supported']


def _same_request(a, b):
    """Identity for two ScreenshotRequest wrappers.

    Panda hands out a fresh Python wrapper per lookup, so `id(a) ==
    id(b)` is false for the same C++ object and can FALSE-hit after a
    wrapper is collected (master plan fact #20). Compare `.this`.
    """
    a_this = getattr(a, 'this', None)
    if a_this is None:
        return a is b
    return a_this == getattr(b, 'this', None)


def frame_capture_supported():
    """True if the running engine exposes async framebuffer readback.

    False on stock Panda3D 1.10 (get_async_screenshot is 1.11-dev);
    games that must run on both can branch on this instead of catching
    the RuntimeError from begin_frame_capture().
    """
    try:
        import panda3d.core as p3d
    except ImportError:
        return False
    return hasattr(p3d.GraphicsOutput, 'get_async_screenshot')


class CapturedFrame(object):
    """One completed readback.

    data: buffer-protocol object over the pixels — BGRA, 8 bits per
        component, bottom-up, `width * height * num_components` bytes.
        Zero-copy; valid while this CapturedFrame is referenced (it
        holds the owning Texture). Use tobytes() for an owned copy.
    width, height, num_components: the framebuffer geometry (4 = BGRA).
    frame_number: the engine frame this capture was requested on, so a
        recorder can detect gaps without counting deliveries.
    """

    __slots__ = ('data', 'width', 'height', 'num_components',
                 'frame_number', 'texture')

    def __init__(self, texture, frame_number):
        self.texture = texture
        self.data = texture.get_ram_image()
        self.width = texture.get_x_size()
        self.height = texture.get_y_size()
        self.num_components = texture.get_num_components()
        self.frame_number = frame_number

    def tobytes(self):
        """An owned bytes copy of the pixels (data is a live view)."""
        return bytes(self.data)

    @property
    def nbytes(self):
        return self.width * self.height * self.num_components

    def __repr__(self):
        return ('CapturedFrame(%dx%d, %d comps, frame %d)'
                % (self.width, self.height, self.num_components,
                   self.frame_number))


class FrameCapture(object):
    """Ordered, bounded streaming readback of a GraphicsOutput.

    Built by `Pipeline.begin_frame_capture()`. Call poll() once per
    rendered frame: it retires whatever the transfer chain has finished
    (in request order) and queues the frame just rendered.
    """

    def __init__(self, output, max_in_flight=3, clock=None):
        if not frame_capture_supported():
            raise RuntimeError(
                'async framebuffer readback requires the Pax3D engine '
                '(GraphicsOutput.get_async_screenshot is absent — this '
                'is stock Panda3D 1.10); check '
                'pax3d_render.capture.frame_capture_supported()')
        if output is None:
            raise ValueError('FrameCapture needs a GraphicsOutput')
        if max_in_flight < 1:
            raise ValueError('max_in_flight must be >= 1')

        import panda3d.core as p3d

        self.output = output
        # For the shutdown drain in stop() — see its docstring for why
        # this is a crash guard rather than housekeeping.
        try:
            self._engine = output.get_engine()
        except Exception:
            self._engine = None
        self.max_in_flight = int(max_in_flight)
        self._clock = clock or p3d.ClockObject.get_global_clock()
        self._pending = []          # [(frame_number, ScreenshotRequest)]
        self._stopped = False

        # Accounting a recorder can report without keeping its own tally.
        self.requested = 0
        self.delivered = 0
        self.dropped = 0            # frames skipped because in-flight was full
        self.repeat_polls = 0       # polls with no new frame to request

    # ------------------------------------------------------------------
    # Per-frame driving
    # ------------------------------------------------------------------

    def poll(self):
        """Retire finished frames and request the one just rendered.

        Returns a list of CapturedFrame in capture order (usually 0 or
        1 entries once the pipe is primed; the first `latency` calls
        return nothing). Call exactly ONCE per rendered frame — the
        request queued here captures the frame the App stage last
        submitted.
        """
        if self._stopped:
            return []
        ready = self._retire()
        if len(self._pending) < self.max_in_flight:
            self._request()
        else:
            self.dropped += 1
        return ready

    def drain(self, timeout_frames=8, step=None):
        """Retire everything still in flight, in order.

        Renders up to `timeout_frames` extra frames waiting for the
        tail to land — the flush a recorder wants at stop() so the last
        frames are not lost to latency. `step` defaults to
        GraphicsEngine.render_frame (no app tasks run); pass
        `base.task_mgr.step` instead to keep game logic ticking while
        it flushes.
        """
        ready = self._retire()
        if step is None and self._engine is not None:
            step = self._engine.render_frame
        frames = 0
        while self._pending and frames < timeout_frames and step is not None:
            if not self.output.is_valid():
                break
            step()
            frames += 1
            ready.extend(self._retire())
        return ready

    @property
    def in_flight(self):
        return len(self._pending)

    # ------------------------------------------------------------------
    # Lifetime
    # ------------------------------------------------------------------

    def stop(self, drain_frames=8):
        """Finish outstanding readbacks, then stop tracking.

        Renders up to `drain_frames` engine frames
        (GraphicsEngine.render_frame — no app tasks run) to retire what
        is outstanding. One frame is normally enough. Pass
        drain_frames=0 only if you have already drained by hand.

        History worth keeping, because it dictates the default: on
        wheels before 2026-07-28 leaving even ONE readback in flight at
        process exit was an access violation. The GSG's fence deque
        holds CompletionTokens whose contract is "destroyed prematurely
        == complete(false)", and the screenshot fence callback ignored
        that flag, so on premature destruction it made GL calls
        (map_read_buffer, release_client_buffer) against a GSG already
        being destroyed. Measured on both a real window and an
        offscreen buffer; `cancel()` did not help (the fence lives in
        the GSG, not in the future) and neither did
        remove_all_windows() — only retiring the fences did. Fixed
        engine-side in the Session AM build window and gated by
        test_capture's engine_survives_inflight_exit, which drives the
        raw API so this drain cannot mask a regression. The drain stays
        on by default anyway: it recovers the tail frames a recorder
        would lose to latency, and it keeps callers safe on older
        wheels.
        """
        if drain_frames > 0:
            self._drain_engine(drain_frames)
        self._stopped = True
        self._pending = []

    def _drain_engine(self, max_frames):
        """Render frames until nothing is in flight (bounded).

        Rendering alone is not sufficient: a frame retires the GL fence,
        but the pixels are memcpy'd on the gl_texture_transfer chain, so
        `done()` flips on another thread a short time later. Yield
        between frames instead of spinning — at 4K the copy is 33 MB.
        """
        import time

        engine = self._engine
        if engine is None:
            return 0
        frames = 0
        while self._pending and frames < max_frames:
            if not self.output.is_valid():
                break
            try:
                engine.render_frame()
            except Exception:
                break
            frames += 1
            self._pending = [(n, r) for n, r in self._pending if not r.done()]
            if self._pending:
                time.sleep(0.002)
        return frames

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _request(self):
        req = self.output.get_async_screenshot()
        if self._pending and _same_request(self._pending[-1][1], req):
            # The engine caches ONE screenshot request per output and
            # clears it when the copy is issued at draw time. If the
            # window has not drawn since the last poll (poll() called
            # twice in a frame, a render_snapshot frame with the player
            # chain deactivated, a minimized window), it hands back the
            # SAME request object — tracking it twice would deliver one
            # captured frame twice, i.e. a duplicated video frame.
            self.repeat_polls += 1
            return
        self._pending.append((self._clock.get_frame_count(), req))
        self.requested += 1

    def _retire(self):
        """Pop completed requests from the HEAD only — ordered delivery."""
        ready = []
        while self._pending:
            frame_number, req = self._pending[0]
            if not req.done():
                # A later request may already be finished, but a video
                # stream must not reorder: hold it behind this one.
                break
            self._pending.pop(0)
            texture = req.result()
            if texture is None or not texture.has_ram_image():
                # Cancelled or a readback that produced nothing; count it
                # as dropped rather than emitting an empty frame.
                self.dropped += 1
                continue
            ready.append(CapturedFrame(texture, frame_number))
            self.delivered += 1
        return ready

    def __repr__(self):
        return ('FrameCapture(in_flight=%d/%d, requested=%d, delivered=%d, '
                'dropped=%d)' % (len(self._pending), self.max_in_flight,
                                 self.requested, self.delivered, self.dropped))
