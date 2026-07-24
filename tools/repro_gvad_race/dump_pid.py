"""Out-of-process minidump of a frozen crashed process, then kill it."""
import ctypes
import ctypes.wintypes as wt
import sys

pid = int(sys.argv[1])
out = sys.argv[2]

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
dbghelp = ctypes.WinDLL('dbghelp')
k32.OpenProcess.restype = wt.HANDLE
k32.CreateFileW.restype = wt.HANDLE
k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                            ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
dbghelp.MiniDumpWriteDump.restype = wt.BOOL
dbghelp.MiniDumpWriteDump.argtypes = [wt.HANDLE, wt.DWORD, wt.HANDLE,
                                      wt.DWORD, ctypes.c_void_p,
                                      ctypes.c_void_p, ctypes.c_void_p]

hp = k32.OpenProcess(0x1F0FFF, False, pid)
if not hp:
    sys.exit("OpenProcess failed: %d" % ctypes.get_last_error())
dump_type = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x40
hf = k32.CreateFileW(out, 0x40000000, 0, None, 2, 0x80, None)
ok = dbghelp.MiniDumpWriteDump(hp, pid, hf, dump_type, None, None, None)
k32.CloseHandle(hf)
print("dump ok:", bool(ok), "err:", ctypes.get_last_error())
k32.TerminateProcess(hp, 1)
k32.CloseHandle(hp)
