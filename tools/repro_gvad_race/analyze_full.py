"""Autopsy a full-memory frozen-crash dump.

argv: dump_path exception_pointers_addr
Reads EXCEPTION_POINTERS from dump memory, symbolicates the fault,
hex-dumps and identifies the object around the AV target via vtable
symbolication.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

from minidump.minidumpfile import MinidumpFile

DUMP = sys.argv[1]
PPTR = int(sys.argv[2], 0)
PDB_DIRS = r"C:\python\pax3d\built_x64\bin"

mf = MinidumpFile.parse(DUMP)
reader = mf.get_reader()

def read_mem(addr, size):
    try:
        return reader.read(addr, size) if hasattr(reader, 'read') else None
    except Exception:
        pass
    seglist = (mf.memory_segments_64.memory_segments
               if mf.memory_segments_64
               else mf.memory_segments.memory_segments)
    for s in seglist:
        if s.start_virtual_address <= addr < s.start_virtual_address + s.size:
            mf.file_handle.seek(s.start_file_address
                                + (addr - s.start_virtual_address))
            n = min(size, s.start_virtual_address + s.size - addr)
            return mf.file_handle.read(n)
    return None

def q(addr):
    d = read_mem(addr, 8)
    return struct.unpack("<Q", d)[0] if d and len(d) == 8 else None

# EXCEPTION_POINTERS -> (EXCEPTION_RECORD*, CONTEXT*)
prec = q(PPTR)
pctx = q(PPTR + 8)
print("EXCEPTION_RECORD @0x%X, CONTEXT @0x%X" % (prec, pctx))

rec = read_mem(prec, 0x98)
code, flags = struct.unpack_from("<II", rec, 0)
exc_addr = struct.unpack_from("<Q", rec, 16)[0]
nparams = struct.unpack_from("<I", rec, 24)[0]
info = struct.unpack_from("<%dQ" % max(nparams, 2), rec, 32)
print("code=0x%08X addr=0x%X av_kind=%d av_target=0x%X"
      % (code, exc_addr, info[0], info[1]))

ctx = read_mem(pctx, 0x4D0)
def reg(off):
    return struct.unpack_from("<Q", ctx, off)[0]
print("RIP=0x%X RSP=0x%X" % (reg(0xF8), reg(0x98)))
print("RAX=0x%X RBX=0x%X RCX=0x%X RDX=0x%X" % (reg(0x78), reg(0x90),
                                               reg(0x80), reg(0x88)))
print("RSI=0x%X RDI=0x%X R8=0x%X R9=0x%X R10=0x%X R11=0x%X"
      % (reg(0xA8), reg(0xB0), reg(0xB8), reg(0xC0), reg(0xC8), reg(0xD0)))
print("R12=0x%X R13=0x%X R14=0x%X R15=0x%X"
      % (reg(0xD8), reg(0xE0), reg(0xE8), reg(0xF0)))

# --- symbolication setup ---
mods = [(m.baseaddress, m.size, m.name) for m in mf.modules.modules]
def mod_for(addr):
    for b, s, n in mods:
        if b <= addr < b + s:
            return b, n
    return None, None

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
_loaded = set()
def symbolize(addr):
    b, name = mod_for(addr)
    if b is None:
        return None
    if b not in _loaded:
        dbghelp.SymLoadModuleExW(hproc, None, name, None, b, 0, None, 0)
        _loaded.add(b)
    sym = SYMBOL_INFOW()
    sym.SizeOfStruct = 88
    sym.MaxNameLen = MAX_NAME - 1
    disp = ctypes.c_ulonglong(0)
    if not dbghelp.SymFromAddrW(hproc, addr, ctypes.byref(disp),
                                ctypes.byref(sym)):
        return "%s+0x%x" % (name.split("\\")[-1], addr - b)
    return "%s!%s+0x%x" % (name.split("\\")[-1], sym.Name, disp.value)

print("\nfault RIP:", symbolize(reg(0xF8)))

# --- hex dump around the AV target and annotate qwords ---
target = info[1]
base = target & ~0xF
lo = base - 0x80
print("\n--- memory around AV target 0x%X ---" % target)
data = read_mem(lo, 0x140)
if data:
    for i in range(0, len(data) - 7, 8):
        val = struct.unpack_from("<Q", data, i)[0]
        note = ""
        s = symbolize(val) if val > 0x10000 else None
        if s:
            note = "  -> " + s
        mark = " <== AV target" if lo + i == target else ""
        print("0x%X: 0x%016X%s%s" % (lo + i, val, note, mark))
else:
    print("target memory not captured")

# Also annotate the faulting thread stack top (RSP) qwords for frames.
print("\n--- fault-time stack (from CONTEXT RSP) ---")
rsp = reg(0x98)
sdata = read_mem(rsp, 0x300)
if sdata:
    for i in range(0, len(sdata) - 7, 8):
        val = struct.unpack_from("<Q", sdata, i)[0]
        s = symbolize(val)
        if s and "!" in s:
            print("rsp+0x%03X: %s" % (i, s))
