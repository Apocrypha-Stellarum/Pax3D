# Queued C++ patch: offscreen GL_INVALID_OPERATION + gl-max-errors -1

**Status: LANDED — window executed Session X part 2 (2026-07-19,
user-authorized).** Build 1 min 0 sec incremental, exit 0; wheel
installed into pax3d-env and archived `wheels_session_x\`. Verified:
probe_gl_errors 0 errors/frame in EVERY phase both baselines (was
~60/phase); `test_gl_clean` flipped to its permanent zero-GL-errors
form — now the same clean assertion on both engines; full gate green.
The `-1` fix is validated by code symmetry with `report_errors_loop`
(no error source remains offscreen to exercise the limit path
end-to-end — which is the point). The rest of this file is the
historical record of the defect and the patch as applied.

## Defect 1: one GL_INVALID_OPERATION per frame in EVERY offscreen run

Field report (sfb2 FPS lane): "1 benign GL_INVALID_OPERATION per frame
for any PLAYING character in a bare offscreen window deactivates the
GSG after 20 frames." Measured truth (probe matrix): the character is
irrelevant — the fork emits 1 error/frame on an EMPTY offscreen scene,
both baselines; a real window is clean; stock 1.10.16 is clean
everywhere. Present in the Window-1 wheel → predates all R6 surgery;
upstream commit `bd4dc8a379` (2024-10-10, before our divergence point)
commented out the single-buffered branch of
`FrameBufferProperties::get_buffer_mask()` to fix a **DX9** buffer
copy. The mask now always contains `T_back`, so `prepare_display_region`
issues `glDrawBuffer(GL_BACK)` on the single-buffered wgl pbuffer —
GL_INVALID_OPERATION, once per frame, until the once-per-second error
sweep reaches `gl-max-errors` (default 20) and panic-deactivates the
GSG: frozen framebuffer, silently stale screenshots. DX9 no longer
exists in this engine (R6 Window 2), so the accommodation is moot.

**Consequences today:** any offscreen consumer (game harnesses, and
paxtest itself) running >~20 s of wall time in one process silently
freezes its framebuffer unless it sets a huge `gl-max-errors`.

### Fix — `panda/src/display/frameBufferProperties.cxx` `get_buffer_mask()`

Replace the commented-out block:

```cxx
  int mask = 0;

  // PAX3D: restore the 1.10 semantics — a single-buffered target has no
  // GL_BACK, and glDrawBuffer(GL_BACK) on it raises GL_INVALID_OPERATION
  // in every prepare_display_region (= once per frame on wgl pbuffers =
  // every offscreen harness; the GSG panic-deactivates at gl-max-errors).
  // Upstream bd4dc8a379 commented this conditional out for a DX9
  // buffer-copy fix; DX9 was excised in R6 Window 2, so the
  // accommodation is moot here.
  if (_property[FBP_back_buffers] > 0) {
    mask = RenderBuffer::T_front | RenderBuffer::T_back;
  } else {
    mask = RenderBuffer::T_front;
  }
```

(Behavior after fix: `get_draw_buffer_type() & mask` drops the color
bits for single-buffered pbuffers → `set_draw_buffer` issues no
`glDrawBuffer` at all → context default `GL_FRONT` — exactly the 1.10
behavior, which stock measures clean.)

## Defect 2: `gl-max-errors -1` deactivates on the FIRST error

The variable is documented "-1 for no limit" (`glmisc_src.cxx:134`)
and `report_errors_loop` honors that (`gl_max_errors < 0 ||` at
glGraphicsStateGuardian_src.cxx:9922) — but the once-per-second sweep
does a bare `>=` at :4817, so `-1` means instant `panic_deactivate()`.
Found by the field dev (their harness comment names the line).

### Fix — `panda/src/glstuff/glGraphicsStateGuardian_src.cxx` (~:4817)

```cxx
        _error_count += error_count;
        // PAX3D: honor the documented "-1 = no limit" (report_errors_loop
        // already does; a bare >= made -1 panic-deactivate on the FIRST
        // error instead).
        if (gl_max_errors >= 0 && _error_count >= gl_max_errors) {
          panic_deactivate();
        }
```

## Window checklist

1. Apply both edits (they are NOT in the tree — this file is the only
   copy, keeping the tree clean per fact #11).
2. Incremental build (canonical command, CLAUDE.md), reinstall into
   pax3d-env, archive the wheel.
3. `test_gl_clean` flips: true up its fork expectation to zero errors
   (the test says exactly what to change).
4. Full gate both engines × both baselines; totals true-up.
5. Tell the FPS lane: `gl-max-errors 1000000` workaround can come out
   of test_weapon_system.py (and -1 now works as documented).
