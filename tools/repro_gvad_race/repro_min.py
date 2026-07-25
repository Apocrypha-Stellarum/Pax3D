"""Minimal, numpy-free bisection repro for the cross-thread free/alloc AV.

Levels (--level):
  full        vdata + arrays + prim + geom + node   (known-crashing shape)
  no-prim     vdata + copy only, no GeomTriangles/Geom/GeomNode
  empty-vdata vdata ctor/dtor churn only (no rows, no copy)
  plain-nodes PandaNode ctor/dtor churn only (no gobj at all)
Main thread destroys; N workers build.  Stdlib only.
"""
import argparse
import faulthandler
import os
import queue
import time
from concurrent.futures import ThreadPoolExecutor

faulthandler.enable()

ap = argparse.ArgumentParser()
ap.add_argument("--level", default="full",
                choices=["full", "no-prim", "empty-vdata", "plain-nodes",
                         "pta-array", "rows-only", "arraydata-rows",
                         "arraydata-empty", "mixed-traffic",
                         "handle-only", "read-handle-only",
                         "request-resident", "mark-used-only",
                         "bind-pin"])
ap.add_argument("--workers", type=int, default=2)
ap.add_argument("--seconds", type=float, default=90.0)
ap.add_argument("--render", action="store_true",
                help="live offscreen render loop on the main thread "
                     "(paxcraft envelope, 2026-07-25 report)")
ap.add_argument("--attach", action="store_true",
                help="with --render: attach worker-built GeomNodes to the "
                     "rendered scene graph (implies level full shapes)")
ap.add_argument("--no-bind", action="store_true",
                help="skip Thread.bind_thread in workers")
ap.add_argument("--main-churn", action="store_true",
                help="also construct one build() per main-loop iteration "
                     "on the main thread (paxcraft: HUD text/particles "
                     "rebuild vertex data every frame)")
ap.add_argument("--pipeline", action="store_true",
                help="with --render: boot pax3d_render with the paxcraft "
                     "field config (directional sun + shadows, bloom, "
                     "atmosphere, lens flare, srgb/aces, msaa4)")
ap.add_argument("--custom-format", action="store_true",
                help="build vdatas with a fresh v3n3c4t2 format registered "
                     "LAZILY from the first worker(s) to mesh — the "
                     "paxcraft mesher shape (module-global cache, no lock)")
ap.add_argument("--numpy-load", action="store_true",
                help="every other worker job is ~10 ms of pure numpy "
                     "(GIL fully released — the gen jobs sharing the pool)")
ap.add_argument("--numpy-inline", action="store_true",
                help="each build job runs ~10 ms of numpy BEFORE "
                     "constructing (the mesh_chunk-then-build shape)")
ap.add_argument("--multi-node", action="store_true",
                help="each build job constructs THREE GeomNodes "
                     "(opaque/cutout/water shape)")
ap.add_argument("--inflight", type=int, default=8,
                help="jobs kept in flight (paxcraft: 24)")
ap.add_argument("--dump", default=None,
                help="write a minidump here on unhandled exception")
ap.add_argument("--same-name", action="store_true",
                help="reuse one vdata name (PStat collector cache hits)")
ap.add_argument("--validate-lru", action="store_true",
                help="validate the global vertex-data LRUs from main")
ap.add_argument("--check-alias", action="store_true",
                help="assert no two live objects share a C++ this pointer")
args = ap.parse_args()
print("pid", os.getpid(), "level:", args.level, "workers:", args.workers,
      flush=True)

_filter_ref = None
if args.dump:
    import ctypes
    import ctypes.wintypes as wt
    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _dbghelp = ctypes.WinDLL('dbghelp')

    class _MEI(ctypes.Structure):
        _fields_ = [("ThreadId", wt.DWORD),
                    ("ExceptionPointers", ctypes.c_void_p),
                    ("ClientPointers", wt.BOOL)]

    _FILTER = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)
    _k32.CreateFileW.restype = wt.HANDLE
    _k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                                 ctypes.c_void_p, wt.DWORD, wt.DWORD,
                                 wt.HANDLE]
    _k32.GetCurrentProcess.restype = wt.HANDLE
    _dbghelp.MiniDumpWriteDump.restype = wt.BOOL
    _dbghelp.MiniDumpWriteDump.argtypes = [wt.HANDLE, wt.DWORD, wt.HANDLE,
                                           wt.DWORD, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p]

    def _write_dump(ptrs):
        # Freeze here so an external dumper can snapshot the crashed
        # process (in-process MiniDumpWriteDump is unreliable).
        with open(args.dump + ".marker", "w") as f:
            f.write("%d %d %d" % (_k32.GetCurrentProcessId(),
                                  _k32.GetCurrentThreadId(), ptrs or 0))
        _k32.Sleep(600000)
        return 1  # EXCEPTION_EXECUTE_HANDLER

    _filter_ref = _FILTER(_write_dump)
    _k32.SetUnhandledExceptionFilter(_filter_ref)

from panda3d.core import loadPrcFileData
if args.render:
    loadPrcFileData("", "window-type offscreen\ngl-version 3 2\n"
                        "sync-video 0\naudio-library-name null\n")
else:
    loadPrcFileData("", "window-type none\naudio-library-name null\n")

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData,
                          GeomVertexFormat, PandaNode,
                          Thread as PandaThread)

RES_CHOICES = [96, 128, 128, 128, 256]
LIVE_TARGET = 25
_payload = {}
_indices = {}


def payload(res, rowbytes=32):
    key = (res, rowbytes)
    if key not in _payload:
        _payload[key] = bytes(res * res * rowbytes)
    return _payload[key]


def indices(res):
    if res not in _indices:
        import array
        tris = array.array('I')
        for j in range(res - 1):
            base0 = j * res
            for i in range(res - 1):
                a = base0 + i
                b = a + 1
                c = a + res
                d = c + 1
                tris.extend((a, b, c, c, b, d))
        _indices[res] = tris.tobytes()
    return _indices[res]


def _bind():
    if not args.no_bind:
        # DELIBERATELY discards the returned PT(Thread) — the universal
        # consumer mistake (CRASH_BIND_THREAD_DANGLE.md).  The engine's
        # bind pin must make this safe; keeping the discard makes every
        # churn row here adversarial on that contract (stock 1.10, which
        # has no pin, AVs on the render-churn shape for exactly this
        # reason).
        PandaThread.bind_thread('repro_worker', 'repro_sync')


if args.level == "bind-pin":
    # The 2026-07-26 dangling-ExternalThread contract: bind_thread must PIN
    # the bound thread (process-lifetime ref) so the TLS _current_thread
    # raw pointer can never dangle when the caller drops the returned
    # PT(Thread) -- which every measured consumer does (sfb2 planetside,
    # paxcraft, this tool's own _bind above).  On an unpinned wheel the
    # ref count is 1 (wrapper only) and we exit UNPINNED *without* touching
    # the dangle (doing so would be use-after-free).  On a pinned wheel we
    # additionally prove the dangle-survival: drop the wrapper, gc, churn
    # allocations, and get_current_thread() must still name the bound
    # thread.
    import gc

    def _pin_probe():
        t = PandaThread.bind_thread('pin_probe', 'pin_probe_sync')
        rc = t.get_ref_count()
        if rc < 2:
            return rc, None
        del t
        gc.collect()
        junk = [bytes(56) for _ in range(100000)]   # heap-reuse pressure
        del junk
        return rc, PandaThread.get_current_thread().get_name()

    with ThreadPoolExecutor(max_workers=1) as _ex:
        _rc, _name = _ex.submit(_pin_probe).result()
    print("bind_thread ref count:", _rc,
          "| current thread after drop+gc:", _name, flush=True)
    if _rc >= 2 and _name == 'pin_probe':
        print("PINNED", flush=True)
        raise SystemExit(0)
    print("UNPINNED", flush=True)
    raise SystemExit(4)


_cfmt = []


def custom_format():
    # Deliberately racy lazy init: N workers can hit register_format
    # concurrently on their first mesh, exactly like paxcraft's
    # mesher.vertex_format() module-global cache.
    if not _cfmt:
        from panda3d.core import GeomVertexArrayFormat
        arr = GeomVertexArrayFormat()
        arr.add_column('vertex', 3, Geom.NT_float32, Geom.C_point)
        arr.add_column('normal', 3, Geom.NT_float32, Geom.C_normal)
        arr.add_column('color', 4, Geom.NT_float32, Geom.C_color)
        arr.add_column('texcoord', 2, Geom.NT_float32, Geom.C_texcoord)
        _cfmt.append(GeomVertexFormat.register_format(GeomVertexFormat(arr)))
    return _cfmt[0]


def numpy_load():
    import numpy as _np
    a = _np.random.default_rng(1).random((256, 256))
    for _ in range(6):
        a = a @ a.T
        a /= (_np.abs(a).max() + 1.0)
    return None


def build(seedv):
    if args.numpy_inline:
        numpy_load()
    if args.multi_node and args.level == "full":
        return [build_one(seedv * 3 + k) for k in range(3)]
    return build_one(seedv)


def build_one(seedv):
    res = RES_CHOICES[seedv % len(RES_CHOICES)]
    if args.level == "plain-nodes":
        return PandaNode('n_%d' % seedv)
    if args.level == "pta-array":
        from panda3d.core import PTAUchar
        return PTAUchar.empty_array(res * res * 32)
    if args.level == "mixed-traffic":
        from panda3d.core import GeomVertexArrayData, PTAUchar
        afmt = GeomVertexFormat.get_v3n3t2().get_array(0)
        ad = GeomVertexArrayData(afmt, Geom.UH_static)
        big = PTAUchar.empty_array(res * res * 32)
        return (ad, big)
    if args.level in ("arraydata-rows", "arraydata-empty", "handle-only",
                      "read-handle-only", "request-resident",
                      "mark-used-only"):
        from panda3d.core import GeomVertexArrayData
        afmt = GeomVertexFormat.get_v3n3t2().get_array(0)
        ad = GeomVertexArrayData(afmt, Geom.UH_static)
        if args.level == "arraydata-rows":
            ad.modify_handle().unclean_set_num_rows(res * res)
        elif args.level == "handle-only":
            h = ad.modify_handle()
            del h
        elif args.level == "read-handle-only":
            h = ad.get_handle()
            del h
        elif args.level == "request-resident":
            ad.request_resident()
        elif args.level == "mark-used-only":
            ad.mark_used_lru()
        return ad

    vname = 'chunk' if args.same_name else 'c_%d' % seedv
    if args.custom_format:
        fmt, rowbytes = custom_format(), 48
    else:
        fmt, rowbytes = GeomVertexFormat.get_v3n3t2(), 32
    vdata = GeomVertexData(vname, fmt, Geom.UH_static)
    if args.level == "empty-vdata":
        return vdata
    n = res * res
    vdata.unclean_set_num_rows(n)
    if args.level == "rows-only":
        return vdata
    vdata.modify_array(0).modify_handle().copy_data_from(
        payload(res, rowbytes))
    if args.level == "no-prim":
        return vdata

    idx = indices(res)
    prim = GeomTriangles(Geom.UH_static)
    prim.set_index_type(Geom.NT_uint32)
    iarr = prim.modify_vertices()
    iarr.unclean_set_num_rows(len(idx) // 4)
    iarr.modify_handle().copy_data_from(idx)
    prim.close_primitive()
    geom = Geom(vdata)
    geom.add_primitive(prim)
    node = GeomNode('c_%d' % seedv)
    node.add_geom(geom)
    return node


base = None
pipeline = None
if args.render:
    from direct.showbase.ShowBase import ShowBase
    base = ShowBase()
    base.disable_mouse()
    base.cam.set_pos(0, -10, 3)
    base.cam.look_at(0, 0, 0)
    if args.pipeline:
        import sys
        sys.path.insert(0, os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            os.pardir, os.pardir)))
        import pax3d_render
        pipeline = pax3d_render.init(
            msaa_samples=4, max_lights=12, enable_shadows=True,
            sun_light_mode='directional', shadow_map_size=4096,
            shadow_caster_mask=15, enable_bloom=True, bloom_strength=0.55,
            bloom_intensity=0.75, bloom_levels=5, tonemap_operator='aces',
            srgb_inputs=True, enable_atmosphere=True, atmo_scale_height=55.0,
            atmo_base_height=36.0, enable_lens_flare=True,
            flare_strength=0.30, use_emission_maps=True)
        pipeline.set_shadow_bias(0.35, world_units=True)
        pipeline.set_shadow_normal_bias(0.30)
        pipeline.set_shadow_filter_size(3)
        pipeline.set_shadow_texel_snap(True)
        pipeline.set_shadow_extent(110.0, 500.0)

pool = ThreadPoolExecutor(max_workers=args.workers, initializer=_bind)
results = queue.Queue()
live = []
seed = [0]
built = [0]
frames = [0]
t0 = time.time()


def submit_one():
    s = seed[0]
    seed[0] += 1
    job = numpy_load if (args.numpy_load and s % 2) else build
    fut = pool.submit(job, s) if job is build else pool.submit(job)
    fut.add_done_callback(lambda f: results.put(f))


for _ in range(args.inflight):
    submit_one()

_lrus = []
if args.validate_lru:
    from panda3d.core import GeomVertexArrayData as _GVAD
    _lrus = [_GVAD.get_independent_lru(), _GVAD.get_small_lru()]

def take_one(fut):
    obj = fut.result()
    if obj is None:            # numpy-load filler job
        submit_one()
        return
    if args.check_alias:
        t = obj.this
        others = set((o.this if not hasattr(o, 'node') else o.node().this)
                     for o in live)
        if t in others:
            print("ALIAS! two live objects share this=0x%X after %d builds"
                  % (t, built[0]), flush=True)
            raise SystemExit(3)
    if args.attach and base is not None:
        if isinstance(obj, list):
            group = base.render.attach_new_node('multi_%d' % built[0])
            for node in obj:
                group.attach_new_node(node)
            obj = group
        elif hasattr(obj, 'add_geom'):
            obj = base.render.attach_new_node(obj)   # rendered next frame
    live.append(obj)
    built[0] += 1
    submit_one()
    while len(live) > LIVE_TARGET:
        old = live.pop(0)                # main-thread destruction
        if hasattr(old, 'remove_node'):
            old.remove_node()


main_live = []

while time.time() - t0 < args.seconds:
    if args.main_churn:
        s = seed[0]
        seed[0] += 1
        main_live.append(build(s))       # main-thread construction
        while len(main_live) > 8:
            main_live.pop(0)             # and destruction
    if base is not None:
        # drain without blocking, then render one frame (the paxcraft
        # shape: main thread inside __igLoop while workers construct)
        while True:
            try:
                fut = results.get_nowait()
            except queue.Empty:
                break
            take_one(fut)
        base.task_mgr.step()
        frames[0] += 1
    else:
        try:
            fut = results.get(timeout=0.01)
        except queue.Empty:
            continue
        take_one(fut)
    if _lrus and built[0] % 50 == 0:
        for lru in _lrus:
            if not lru.validate():
                print("LRU CORRUPT after %d builds: %s"
                      % (built[0], lru), flush=True)
                raise SystemExit(2)

print("SURVIVED %.0f s, %d builds, %d frames"
      % (time.time() - t0, built[0], frames[0]), flush=True)
pool.shutdown(wait=False, cancel_futures=True)
