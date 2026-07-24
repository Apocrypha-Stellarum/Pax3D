"""Annotated hexdump of dump memory: symbolicate qword values (vtables,
code ptrs) and flag pointers into captured heap."""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

from minidump.minidumpfile import MinidumpFile

DUMP = sys.argv[1]
ADDR = int(sys.argv[2], 0)
BEFORE = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x100
AFTER = int(sys.argv[4], 0) if len(sys.argv) > 4 else 0x200
PDB_DIRS = r"C:\python\pax3d\built_x64\bin"

mf = MinidumpFile.parse(DUMP)
seglist = (mf.memory_segments_64.memory_segments
           if mf.memory_segments_64 else mf.memory_segments.memory_segments)

def read_mem(addr, size):
    for s in seglist:
        if s.start_virtual_address <= addr < s.start_virtual_address + s.size:
            mf.file_handle.seek(s.start_file_address
                                + (addr - s.start_virtual_address))
            n = min(size, s.start_virtual_address + s.size - addr)
            return mf.file_handle.read(n)
    return None

mods = [(m.baseaddress, m.size, m.name) for m in mf.modules.modules]
def mod_for(a):
    for b, s, n in mods:
        if b <= a < b + s:
            return b, n
    return None, None

dbghelp = ctypes.WinDLL("dbghelp")
kernel32 = ctypes.WinDLL("kernel32")
kernel32.GetCurrentProcess.restype = wt.HANDLE
dbghelp.SymInitializeW.argtypes = [wt.HANDLE, wt.LPCWSTR, wt.BOOL]
dbghelp.SymSetOptions(0x2)
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
def symbolize(a):
    b, name = mod_for(a)
    if b is None:
        return None
    if b not in _loaded:
        dbghelp.SymLoadModuleExW(hproc, None, name, None, b, 0, None, 0)
        _loaded.add(b)
    sym = SYMBOL_INFOW()
    sym.SizeOfStruct = 88
    sym.MaxNameLen = MAX_NAME - 1
    disp = ctypes.c_ulonglong(0)
    if not dbghelp.SymFromAddrW(hproc, a, ctypes.byref(disp),
                                ctypes.byref(sym)):
        return "%s+0x%x" % (name.split("\\")[-1], a - b)
    return "%s!%s+0x%x" % (name.split("\\")[-1], sym.Name, disp.value)

lo = ADDR - BEFORE
data = read_mem(lo, BEFORE + AFTER)
if data is None:
    sys.exit("memory not captured at 0x%X" % lo)
for i in range(0, len(data) - 7, 8):
    val = struct.unpack_from("<Q", data, i)[0]
    note = ""
    if val > 0x10000:
        s = symbolize(val)
        if s:
            note = "  -> " + s
        elif read_mem(val, 8) is not None:
            note = "  (heap ptr)"
    mark = "  <== ADDR" if lo + i == ADDR else ""
    print("0x%X: 0x%016X%s%s" % (lo + i, val, note, mark))
