# Crash Report: GeomVertexArrayData handle churn × cross-thread destruction

**Status: FIXED + VALIDATED (GVAD stability build window, 2026-07-24,
user go-ahead). The §6 stability-wheel plan landed exactly as written —
commit `d6044b1d8a`, wheel `wheels_gvad\`. Acceptance measured: every
crashing §3 row survives (full/no-prim/rows-only/arraydata-rows/
handle-only/read-handle-only/request-resident + workers=1, 60 s each,
0.1–4.1M builds; handle-only deep soak 120 s / 6.9M builds), full
paxtest gate green both engines with FAIL sets unchanged
(Pax3D 82/7/129 · stock 80/7/131), and the permanent gate
`test_gvad_churn` FAILs on the pre-fix Session-X wheel / PASSes on the
fixed wheel and stock. Repro + dump tooling: `tools/repro_gvad_race/`.**

Field incidents: planetside access violations 2026-07-20 06:36 (pid 32784)
and 2026-07-23 14:39 (pid 94520), both `libp3dtool.dll+0x15a30`
(exception 0xc0000005), both with two chunk-mesher workers inside
`build_chunk_geomnode`. First attributable native crashes of the fork
(the Session-643 telemetry did its job).

---

## 1. The defect in one paragraph

Any thread that takes a `GeomVertexArrayDataHandle` (reader OR writer —
`get_handle()`, `modify_handle()`, or anything built on them:
`unclean_set_num_rows`, `copy_data_from`, even `request_resident()`)
while any other thread is freeing Geom-class objects can corrupt the
heap: a block is eventually handed to two threads at once, and the
second thread's constructor runs over the first thread's live object.
The visible crash is `PipelineCyclerTrueImpl::write_stage_upstream`
(pipelineCyclerTrueImpl.cxx:209) reading a NULL or garbage
`_single_data._cdata` out of a microseconds-old object — but that
thread is the victim, not the culprit. Single-threaded churn is clean
at 97M iterations; stock Panda 1.10.16 is immune at 548k. This is a
latent upstream race unmasked by the 1.11 line's build/layout changes.

## 2. Reproduction

`C:/python/pax3d-env/Scripts/python.exe tools/repro_gvad_race/repro_min.py
--level handle-only --seconds 120` — AV in under 60 s on the Session-X
wheel, every run. `--dump <path>` freezes the crashed process for
external dumping via `dump_pid.py` (git-bash swallows WER dumps;
`--dump` + `dump_pid.py <pid> <out> 0x2` gives a full-memory dump; the
`analyze_full.py` / `find_ctx.py` / `annotate_mem.py` scripts do the
rest against `built_x64\bin` PDBs).

## 3. The measured variant matrix

| Variant (2 bound workers unless noted) | Result |
|---|---|
| full chunk build / no-prim / rows-only / arraydata-rows | **crash < 60 s** |
| handle-only (`modify_handle()`, dropped immediately, no rows) | **crash** |
| read-handle-only (`get_handle()`) | **crash** (cycler write lock exonerated) |
| request-resident (no handle object, no `MemoryUsage::update_type`) | **crash** |
| workers=1 + main destroying | **crash** (⇒ `workers=1` is NOT a mitigation) |
| destroy-in-worker (each worker frees its own; main idle) | **crash** |
| no-destroy (nothing ever freed) | survives (12k builds) |
| empty-vdata / plain-nodes ctor-dtor churn | survives 4.5M / 4.2M |
| arraydata-empty (ctor enqueues on LRU too) | survives 7.2M |
| pta-array (same sizes through TypeHandle::allocate_array) | survives 550k |
| mixed-traffic (pta + empty arraydata, same alloc pattern) | survives 530k (allocator traffic alone exonerated) |
| mark-used-only (`mark_used_lru()` churn) | survives 7.1M (LRU exonerated) |
| single thread doing everything | survives **97M** |
| stock Panda 1.10.16, crashing recipe | survives 548k |
| MIMALLOC_PURGE_* knobs, same-name (PStats quiet) | still crash (purge + PStats exonerated) |

Crashing core beyond plain churn = exactly the handle trio:
`cdata->ref(); cdata->_rw_lock acquire/release; unref_delete((CycleData*)cdata)`
executed concurrently with frees on any other thread.

## 4. Dump forensics (full-memory dumps, both fault CONTEXTs recovered)

- Fault: AV READ at `old_data+8` (`get_ref_count()` — the ICF-folded
  `std::atomic<uint>::load` at libp3dtool+0x15a30) with
  `old_data = _single_data._cdata` = NULL (repro) / 0xC800FD0000
  garbage (game).
- The faulting thread legitimately holds its own CyclerMutex
  (CRITICAL_SECTION decoded from the dump: DebugInfo −1,
  LockCount/Recursion packed, OwningThread = faulting tid, SpinCount
  0xFA0).
- The object later shows a fully re-constructed state — a second
  constructor ran over the live block (ctor member order: `_single_data`
  nulled → `_lock` re-initialised → body stores CData; the fault reads
  the NULL window).
- Both workers can fault simultaneously, each on its own object, each
  in fresh pages of its own mimalloc segment ⇒ freelist-level
  double-issue, cascading from an unidentified stray/double free.

## 5. Why 1.11 and not 1.10 (two independent audits)

The entire handle/refcount path (`geomVertexArrayData.I`,
`copyOnWriteObject.*`, `nodePointerTo*`, `cycleData.h`) is
**byte-identical to v1.10.16**, and the refcount contract was verified
balanced (object +1/−1; CData 1→2→1→0 with both delete sites keyed on
one atomic). What changed underneath:

1. **`f02a3156ca` (upstream, Nov 2022):** `_single_data` + the
   CyclerMutex moved **inside** the owning object (1.10 kept the
   CycleDataNode array in a detached heap block) and the object grew
   8 bytes (size-class shift). This is why the corruption presents as
   "same GVAD constructed twice" — structurally impossible in 1.10 —
   and it created new latent surfaces: any `pipeline_stage ≥ 1` access
   with num_stages==1 now reads/writes the cycler's own `_data`/`_lock`
   (bound workers measured stage 0, so not our trigger).
2. **Bounds guards compiled out:** the cycler's stage guards were
   demoted `#ifndef NDEBUG` → `#ifdef _DEBUG`; opt-3 wheels define
   neither, so 1.10.16 wheels ran them and ours do not.
3. **`makepanda.py:2327`: `USE_DELETED_CHAIN = UNDEF` when mimalloc is
   enabled.** Every stable Panda release ran this churn through
   DeletedChain (never-freed same-size arenas + double-delete
   canaries) — a regime that *masks* exactly this race class. Our
   wheels are the first to run it on a general-purpose allocator
   (mimalloc 2.1.6, statically linked in libp3dtool), where a stray
   free cascades into double-issued blocks.
4. patomic port of refcounts: audited correct on x86; noted only that
   `node_unref_delete` lacks the acquire fence `unref_delete` has.

Latent defects found on the way (fix in any window, none is our
trigger): `set_num_stages` does `delete[] &_single_data` on the
multi→1 transition (pipelineCyclerTrueImpl.cxx:334-341 — frees an
interior pointer of a live object); `release_write` resolves the
pipeline stage from the *destroying* thread rather than the handle's;
the two demoted guards.

## 6. Fix plan (LANDED 2026-07-24 — the stability wheel below, verbatim)

**Stability wheel (recommended first):** restore `USE_DELETED_CHAIN=1`
alongside mimalloc (one-line makepanda change), restore both cycler
guards to `#ifndef NDEBUG`, fix the `set_num_stages` interior delete.
Acceptance: `repro_min.py` matrix — every crashing row must survive a
soak; full paxtest gate both engines unchanged.

**Diagnostic wheel (optional, for the exact racing line):**
env-var-gated poison-on-free (memset 0xDD) in
`MemoryHook::heap_free_single/array` — makes the first stray free
crash at the culprit's stack instead of two recycles later.

**Permanent gate:** promote the crashing recipe into paxtest as a
threaded-churn test once the fix lands (it must FAIL on the Session-X
wheel and PASS on the fixed wheel).

## 7. Game-side guidance (until the fix ships)

`workers=1` does **not** fix this (measured). The safe mitigation is
moving the four Panda construction calls of `build_chunk_geomnode`
onto the main thread; apron generation + conform (the heavy numpy
work) stay on workers. Filed game-side as ER-011.

**Post-fix (2026-07-24): the fix ships in every installed engine**
(pax3d-env + system Python both carry the stability wheel). The ER-011
mitigation is no longer load-bearing — worker-thread Geom construction
is safe again. Keeping the mitigation is harmless; relaxing it is the
game lane's call after the wheel has soaked in the field.
