# CRASH: bind_thread dangling ExternalThread (FIXED + VALIDATED)

**Status:** FIXED engine-side 2026-07-26 (`thread.cxx` bind pin) — gated by
`paxtest/test_thread_bind.py`.
**Field reports:** paxcraft `docs/ENGINE_NOTES.md` 2026-07-25 (5 workers,
live render, AV in 10–60 s); reproduced same-day at **workers=2 — the sfb2
shipping envelope** (`planetside/world/chunks.py` has the identical usage).
**Distinct from** the 2026-07-24 GVAD handle-race
(`CRASH_GVAD_HANDLE_RACE.md`) — overlapping signature, different bug; the
GVAD window's three fixes all stand.

## Signature (all one bug)

- 0xC0000005 in worker-side Geom construction (`unclean_set_num_rows`,
  `copy_data_from`, `close_primitive`) while the main thread renders.
- `Assertion failed: pipeline_stage >= 0 && pipeline_stage <
  get_num_stages()` (pipelineCyclerTrueImpl.cxx) in guard-compiled paths.
- `_pointer != nullptr` (cycleDataWriter.I:48).
- Minidump (2026-07-26, full-memory, frozen-filter workflow):
  `fetch_add` **WRITE to address 0x8** — `ref()` on a **null CycleData** —
  under `GeomPrimitivePipelineReader` ctor ← `GeomPrimitive::
  get_num_vertices` ← `close_primitive` on the worker's own freshly built
  primitive.

## Root cause

`Thread::bind_thread()` creates an `ExternalThread` whose **only**
reference is the returned `PT(Thread)`. `ThreadWin32Impl::bind_thread`
stores a **raw pointer** in the `thread_local Thread *_current_thread`
slot. The upstream doc comment makes lifetime "the caller's
responsibility" — and every measured consumer drops the return value:

```python
def _bind_worker():                      # paxcraft, sfb2, repro_min alike
    Thread.bind_thread('worker', 'sync')   # PT dropped -> deleted NOW
```

From that moment the worker runs on a dangling `_current_thread`. Freed
memory usually still reads `_pipeline_stage == 0`, so everything works —
until the allocator reuses the block (mimalloc per-thread heap; `Thread`
has no DeletedChain, so ANY small same-size-class allocation on that
worker can take it). Then `get_pipeline_stage()` returns garbage and the
release-mode cycler paths index `_data[garbage]` **unchecked**
(`read_unlocked` guards with `#ifdef _DEBUG` only) → junk/null CycleData
→ `ref()` on null → AV at offset 0x8. Guarded paths (`#ifndef NDEBUG`)
fire the stage assert instead. Whether a given app crashes is pure
allocator luck — which is why sfb2 (2 workers) and `repro_min` never
crashed while paxcraft died in seconds, and why worker count seemed to
matter when it does not.

## Proof (paxcraft worktree @ 509488c, GVAD wheel, 2026-07-26)

| Variant | Result |
|---|---|
| Baseline (5 bound workers, worker-side Geom build, live render) | AV in 3–5 s, every run |
| workers=2 (the sfb2 envelope) | AV in 3 s |
| No attach (worker nodes never enter the scene graph), plain state, all per-frame subsystems gated off | still AVs — nothing downstream of construction is required |
| unbound workers (`--no-bind` analogue) | `thread != nullptr` assert, threadWin32Impl.cxx:71 (this fork requires binding; stock 1.10 falls back to the global ExternalThread) |
| **Keep the returned `PT(Thread)` alive** | **full selftest passes, twice, 269 chunks, clean exit** |
| Discard again (control) | AV in 3 s |

Distillation attempts that did NOT reproduce (all survived 60–90 s on the
pre-fix wheel — allocator luck, kept for the record): repro_min
`--render --attach` (±`--pipeline` with the full paxcraft init, ±
`--custom-format`, ±`--numpy-load/--numpy-inline`, ±`--main-churn`, ±
`--multi-node`, `--inflight 24`, workers 2/5). The deterministic gate is
therefore the **ref-count contract**, not a stochastic soak.

## The fix

`thread.cxx` `Thread::bind_thread`: when the fresh ExternalThread becomes
the bound thread, `thread->ref()` — pinned for process lifetime. A
deliberate, bounded leak (one ~200-byte object per bound thread); foreign
threads have no portable exit hook, so releasing the pin safely is
impossible and keeping it is correct.

## Gate (`test_thread_bind.py`)

- `bind_pinned` — `bind_thread` ref count ≥ 2 AND the dangle survives
  drop + gc + heap churn with `get_current_thread()` still naming the
  bound thread. **Deterministic**: measured UNPINNED (rc=1, exit 4) on
  the pre-fix GVAD wheel; Pax3D-only (stock 1.10 has no pin contract).
- `bound_churn_render` — the paxcraft envelope (5 bound workers building
  Geoms against a live offscreen render, 30 s), both engines.

`repro_min.py` grew the field-shape knobs used in the hunt: `--render`,
`--attach`, `--pipeline`, `--custom-format`, `--numpy-load`,
`--numpy-inline`, `--multi-node`, `--inflight`, `--no-bind`,
`--main-churn`, and the `bind-pin` level.

## Consumer guidance (until/independent of the fixed wheel)

Keep the returned Thread alive for the worker's lifetime — correct on
every wheel, and mandatory on pre-fix wheels:

```python
_BOUND = []
def _bind_worker():
    _BOUND.append(Thread.bind_thread('worker', 'sync'))
```

sfb2: `planetside/world/chunks.py:44` needs this one-liner (filed with
the release note). paxcraft: their numpy-only-workers workaround is safe
either way; worker-side GeomNode construction is legal again on the
fixed wheel.

## Forensics workflow (reusable)

Freeze-filter + out-of-process dump, as in the GVAD window: inject the
`SetUnhandledExceptionFilter` marker+Sleep block (see repro_min
`--dump`), poll for the `.marker`, `dump_pid.py <pid> out.dmp 0x2`
(full memory), `analyze_full.py out.dmp <exception_pointers>` under
system Python (has `minidump`), symbols from `built_x64\bin` PDBs.
