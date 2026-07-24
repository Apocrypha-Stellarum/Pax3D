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
                         "request-resident", "mark-used-only"])
ap.add_argument("--workers", type=int, default=2)
ap.add_argument("--seconds", type=float, default=90.0)
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
loadPrcFileData("", "window-type none\naudio-library-name null\n")

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData,
                          GeomVertexFormat, PandaNode,
                          Thread as PandaThread)

RES_CHOICES = [96, 128, 128, 128, 256]
LIVE_TARGET = 25
_payload = {}
_indices = {}


def payload(res):
    if res not in _payload:
        _payload[res] = bytes(res * res * 32)
    return _payload[res]


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
    PandaThread.bind_thread('repro_worker', 'repro_sync')


def build(seedv):
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
    vdata = GeomVertexData(vname,
                           GeomVertexFormat.get_v3n3t2(), Geom.UH_static)
    if args.level == "empty-vdata":
        return vdata
    n = res * res
    vdata.unclean_set_num_rows(n)
    if args.level == "rows-only":
        return vdata
    vdata.modify_array(0).modify_handle().copy_data_from(payload(res))
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


pool = ThreadPoolExecutor(max_workers=args.workers, initializer=_bind)
results = queue.Queue()
live = []
seed = [0]
built = [0]
t0 = time.time()


def submit_one():
    s = seed[0]
    seed[0] += 1
    fut = pool.submit(build, s)
    fut.add_done_callback(lambda f: results.put(f))


for _ in range(8):
    submit_one()

_lrus = []
if args.validate_lru:
    from panda3d.core import GeomVertexArrayData as _GVAD
    _lrus = [_GVAD.get_independent_lru(), _GVAD.get_small_lru()]

while time.time() - t0 < args.seconds:
    try:
        fut = results.get(timeout=0.01)
    except queue.Empty:
        continue
    obj = fut.result()
    if args.check_alias:
        t = obj.this
        others = set(o.this for o in live)
        if t in others:
            print("ALIAS! two live objects share this=0x%X after %d builds"
                  % (t, built[0]), flush=True)
            raise SystemExit(3)
    live.append(obj)
    built[0] += 1
    submit_one()
    while len(live) > LIVE_TARGET:
        live.pop(0)                     # main-thread destruction
    if _lrus and built[0] % 50 == 0:
        for lru in _lrus:
            if not lru.validate():
                print("LRU CORRUPT after %d builds: %s"
                      % (built[0], lru), flush=True)
                raise SystemExit(2)

print("SURVIVED %.0f s, %d builds" % (time.time() - t0, built[0]),
      flush=True)
pool.shutdown(wait=False, cancel_futures=True)
