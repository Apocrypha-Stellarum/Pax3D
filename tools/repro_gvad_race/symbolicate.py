"""Symbolicate offsets in libp3dtool.dll against its PDB via dbghelp."""
import ctypes
import ctypes.wintypes as wt
import sys

DLL = r"C:\python\pax3d\built_x64\bin\libp3dtool.dll"
SEARCH = r"C:\python\pax3d\built_x64\bin"
OFFSETS = [int(a, 16) for a in sys.argv[1:]] or [0x15A30]

dbghelp = ctypes.WinDLL("dbghelp")
kernel32 = ctypes.WinDLL("kernel32")
kernel32.GetCurrentProcess.restype = wt.HANDLE
dbghelp.SymInitializeW.argtypes = [wt.HANDLE, wt.LPCWSTR, wt.BOOL]
dbghelp.SymFromAddrW.argtypes = [wt.HANDLE, ctypes.c_ulonglong,
                                 ctypes.c_void_p, ctypes.c_void_p]
dbghelp.SymGetLineFromAddrW64.argtypes = [wt.HANDLE, ctypes.c_ulonglong,
                                          ctypes.c_void_p, ctypes.c_void_p]

SYMOPT_UNDNAME = 0x2
SYMOPT_LOAD_LINES = 0x10
dbghelp.SymSetOptions(SYMOPT_UNDNAME | SYMOPT_LOAD_LINES)

hproc = kernel32.GetCurrentProcess()
if not dbghelp.SymInitializeW(hproc, ctypes.c_wchar_p(SEARCH), False):
    sys.exit("SymInitialize failed: %d" % kernel32.GetLastError())

dbghelp.SymLoadModuleExW.restype = ctypes.c_ulonglong
dbghelp.SymLoadModuleExW.argtypes = [wt.HANDLE, wt.HANDLE, wt.LPCWSTR,
                                     wt.LPCWSTR, ctypes.c_ulonglong,
                                     wt.DWORD, ctypes.c_void_p, wt.DWORD]
base = dbghelp.SymLoadModuleExW(hproc, None, DLL, None, 0x10000000, 0,
                                None, 0)
if not base:
    sys.exit("SymLoadModuleEx failed: %d" % kernel32.GetLastError())

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

ENUMCB = ctypes.WINFUNCTYPE(wt.BOOL, ctypes.POINTER(SYMBOL_INFOW),
                            wt.ULONG, ctypes.c_void_p)
fold_hits = []

def _cb(psym, size, ctx):
    s = psym.contents
    if abs(s.Address - _target[0]) <= 0:
        fold_hits.append((s.Address, s.Name))
    return True

_target = [0]

for off in OFFSETS:
    addr = base + off
    sym = SYMBOL_INFOW()
    sym.SizeOfStruct = 88  # offsetof(Name)
    sym.MaxNameLen = MAX_NAME - 1
    disp = ctypes.c_ulonglong(0)
    ok = dbghelp.SymFromAddrW(hproc, ctypes.c_ulonglong(addr),
                              ctypes.byref(disp), ctypes.byref(sym))
    if ok:
        print("0x%05X -> %s + 0x%x" % (off, sym.Name, disp.value))
    else:
        print("0x%05X -> SymFromAddr failed: %d"
              % (off, kernel32.GetLastError()))
        continue
    line = IMAGEHLP_LINEW64()
    line.SizeOfStruct = ctypes.sizeof(line)
    ldisp = wt.DWORD(0)
    if dbghelp.SymGetLineFromAddrW64(hproc, ctypes.c_ulonglong(addr),
                                     ctypes.byref(ldisp),
                                     ctypes.byref(line)):
        print("          %s:%d (+%d bytes)"
              % (line.FileName, line.LineNumber, ldisp.value))
    # Enumerate every symbol COMDAT-folded onto the same address.
    _target[0] = sym.Address
    fold_hits.clear()
    cb = ENUMCB(_cb)
    dbghelp.SymEnumSymbolsW.argtypes = [wt.HANDLE, ctypes.c_ulonglong,
                                        wt.LPCWSTR, cb.__class__,
                                        ctypes.c_void_p]
    dbghelp.SymEnumSymbolsW(hproc, ctypes.c_ulonglong(base), "*", cb, None)
    print("  fold set (%d):" % len(fold_hits))
    for a, n in sorted(set(fold_hits)):
        print("    %s" % n)
