"""Walk a WER minidump: exception context + return-address scan of the
faulting thread's stack, symbolicated against local PDBs via dbghelp."""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

from minidump.minidumpfile import MinidumpFile

DUMP = sys.argv[1]
PDB_DIRS = r"C:\python\pax3d\built_x64\bin"

mf = MinidumpFile.parse(DUMP)

# --- exception stream ---
exc = mf.exception
records = exc.exception_records if exc else []
NOEXC = not records
rec = records[0] if records else None
if NOEXC:
    tid = None
    class _R: pass
    rec = None
else:
    tid = rec.ThreadId
if rec is None:
    er = None
else:
    er = rec.ExceptionRecord
if er is not None:
    print("Exception %s at 0x%X, tid=0x%X" % (
        er.ExceptionCode, er.ExceptionAddress, tid))
    try:
        info = er.ExceptionInformation
        if info and len(info) >= 2:
            kind = {0: "READ", 1: "WRITE",
                    8: "DEP"}.get(info[0], str(info[0]))
            print("AV type: %s of address 0x%X" % (kind, info[1]))
    except Exception as e:
        print("(no AV detail: %s)" % e)
else:
    print("(no exception stream — frozen-process dump)")

# --- modules ---
mods = [(m.baseaddress, m.size, m.name) for m in mf.modules.modules]
def mod_for(addr):
    for b, s, n in mods:
        if b <= addr < b + s:
            return b, n
    return None, None

# --- thread context: pull RIP/RSP for the faulting thread ---
thread = None
for t in mf.threads.threads:
    if t.ThreadId == tid:
        thread = t
        break
if thread is None and not NOEXC:
    sys.exit("faulting thread not in dump")

# Context is a raw CONTEXT blob; x64 offsets: Rsp=0x98, Rip=0xF8,
# Rcx=0x80, Rax=0x78, Rdx=0x88, Rbx=0x90, R8=0xB8, R9=0xC0.
# Use the EXCEPTION stream's context (fault time), not the thread's
# (dump time).
buf = mf.file_handle
rip = rsp = 0
if not NOEXC:
    ctx_loc = rec.ThreadContext
    buf.seek(ctx_loc.Rva)
    ctx = buf.read(ctx_loc.DataSize)
    def reg(off):
        return struct.unpack_from("<Q", ctx, off)[0]
    rip, rsp = reg(0xF8), reg(0x98)
    print("RIP=0x%X RSP=0x%X" % (rip, rsp))
    print("RAX=0x%X RCX=0x%X RDX=0x%X RBX=0x%X" % (
        reg(0x78), reg(0x80), reg(0x88), reg(0x90)))
    print("R8 =0x%X R9 =0x%X" % (reg(0xB8), reg(0xC0)))

# --- read stack memory ---
seglist = (mf.memory_segments_64.memory_segments
           if mf.memory_segments_64 else mf.memory_segments.memory_segments)
stack = b""
if not NOEXC:
    seg = None
    for s in seglist:
        if (s.start_virtual_address <= rsp
                < s.start_virtual_address + s.size):
            seg = s
            break
    if seg is None:
        sys.exit("stack segment not captured (rsp=0x%X, %d segments)"
                 % (rsp, len(seglist)))
    buf.seek(seg.start_file_address + (rsp - seg.start_virtual_address))
    avail = seg.size - (rsp - seg.start_virtual_address)
    stack = buf.read(min(avail, 0x4000))

# --- dbghelp symbolication ---
dbghelp = ctypes.WinDLL("dbghelp")
kernel32 = ctypes.WinDLL("kernel32")
kernel32.GetCurrentProcess.restype = wt.HANDLE
dbghelp.SymInitializeW.argtypes = [wt.HANDLE, wt.LPCWSTR, wt.BOOL]
dbghelp.SymSetOptions(0x2 | 0x10)
hproc = kernel32.GetCurrentProcess()
dbghelp.SymInitializeW(hproc, PDB_DIRS, False)
dbghelp.SymLoadModuleExW.restype = ctypes.c_ulonglong
dbghelp.SymLoadModuleExW.argtypes = [wt.HANDLE, wt.HANDLE, wt.LPCWSTR,
                                     wt.LPCWSTR, ctypes.c_ulonglong,
                                     wt.DWORD, ctypes.c_void_p, wt.DWORD]
dbghelp.SymFromAddrW.argtypes = [wt.HANDLE, ctypes.c_ulonglong,
                                 ctypes.c_void_p, ctypes.c_void_p]
dbghelp.SymGetLineFromAddrW64.argtypes = [wt.HANDLE, ctypes.c_ulonglong,
                                          ctypes.c_void_p, ctypes.c_void_p]

MAX_NAME = 512
class SYMBOL_INFOW(ctypes.Structure):
    _fields_ = [("SizeOfStruct", wt.ULONG), ("TypeIndex", wt.ULONG),
                ("Reserved", ctypes.c_ulonglong * 2), ("Index", wt.ULONG),
                ("Size", wt.ULONG), ("ModBase", ctypes.c_ulonglong),
                ("Flags", wt.ULONG), ("Value", ctypes.c_ulonglong),
                ("Address", ctypes.c_ulonglong), ("Register", wt.ULONG),
                ("Scope", wt.ULONG), ("Tag", wt.ULONG),
                ("NameLen", wt.ULONG), ("MaxNameLen", wt.ULONG),
                ("Name", ctypes.c_wchar * MAX_NAME)]
class IMAGEHLP_LINEW64(ctypes.Structure):
    _fields_ = [("SizeOfStruct", wt.DWORD), ("Key", ctypes.c_void_p),
                ("LineNumber", wt.DWORD), ("FileName", wt.LPWSTR),
                ("Address", ctypes.c_ulonglong)]

loaded = {}
def load_mod(base, name):
    if base in loaded:
        return loaded[base]
    # dump module paths point at the installed env; PDBs sit in built_x64
    # (dbghelp matches by GUID, search path covers it) — pass the dump's
    # own DLL path so headers resolve.
    ok = dbghelp.SymLoadModuleExW(hproc, None, name, None, base, 0, None, 0)
    loaded[base] = ok
    return ok

def symbolize(addr):
    base, name = mod_for(addr)
    if base is None:
        return None
    load_mod(base, name)
    sym = SYMBOL_INFOW()
    sym.SizeOfStruct = 88
    sym.MaxNameLen = MAX_NAME - 1
    disp = ctypes.c_ulonglong(0)
    short = name.split("\\")[-1]
    if not dbghelp.SymFromAddrW(hproc, addr, ctypes.byref(disp),
                                ctypes.byref(sym)):
        return "%s+0x%x" % (short, addr - base)
    txt = "%s!%s+0x%x" % (short, sym.Name, disp.value)
    line = IMAGEHLP_LINEW64()
    line.SizeOfStruct = ctypes.sizeof(line)
    ld = wt.DWORD(0)
    if dbghelp.SymGetLineFromAddrW64(hproc, addr, ctypes.byref(ld),
                                     ctypes.byref(line)):
        txt += "  [%s:%d]" % (line.FileName.split("\\")[-1],
                              line.LineNumber)
    return txt

if not NOEXC:
    print("\nRIP: %s" % symbolize(rip))

def find_seg(addr):
    for s in seglist:
        if s.start_virtual_address <= addr < s.start_virtual_address + s.size:
            return s
    return None

def scan_thread(t, label, size=0x4000, panda_only=False):
    buf.seek(t.ThreadContext.Rva)
    tctx = buf.read(t.ThreadContext.DataSize)
    trsp = struct.unpack_from("<Q", tctx, 0x98)[0]
    trip = struct.unpack_from("<Q", tctx, 0xF8)[0]
    s = find_seg(trsp)
    print("\n--- %s tid=0x%X rip=%s ---" % (label, t.ThreadId,
                                           symbolize(trip)))
    if s is None:
        print("  (stack not captured)")
        return
    buf.seek(s.start_file_address + (trsp - s.start_virtual_address))
    data = buf.read(min(s.size - (trsp - s.start_virtual_address), size))
    for i in range(0, len(data) - 7, 8):
        val = struct.unpack_from("<Q", data, i)[0]
        b, name = mod_for(val)
        if b is None:
            continue
        short = (name or "?").split("\\")[-1].lower()
        if panda_only and not ("panda" in short or "p3d" in short
                               or "core.cp313" in short):
            continue
        sym = symbolize(val)
        if sym and "!" in sym:
            print("  rsp+0x%04X: %s" % (i, sym))

print("\n--- return-address scan of stack (rsp..rsp+0x4000) ---")
shown = 0
for i in range(0, len(stack) - 7, 8):
    val = struct.unpack_from("<Q", stack, i)[0]
    base, name = mod_for(val)
    if base is None:
        continue
    short = (name or "?").split("\\")[-1].lower()
    if short.startswith(("kernel32", "ntdll", "kernelbase", "ucrtbase",
                         "vcruntime")) and shown > 40:
        continue
    s = symbolize(val)
    if s and ("!" in s):
        print("rsp+0x%04X: %s" % (i, s))
        shown += 1
    if shown > 120:
        break

# Other threads (pass tids as extra args, or 'all' for every thread):
want = [w.lower() for w in sys.argv[2:]]
for t in mf.threads.threads:
    if t.ThreadId == tid or not want:
        continue
    if "all" not in want and ("0x%x" % t.ThreadId) not in want:
        continue
    scan_thread(t, "thread", panda_only=True)
