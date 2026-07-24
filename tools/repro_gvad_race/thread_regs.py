"""Print per-thread saved registers from a minidump."""
import struct
import sys

from minidump.minidumpfile import MinidumpFile

mf = MinidumpFile.parse(sys.argv[1])
buf = mf.file_handle
for t in mf.threads.threads:
    buf.seek(t.ThreadContext.Rva)
    ctx = buf.read(t.ThreadContext.DataSize)
    def r(off):
        return struct.unpack_from("<Q", ctx, off)[0]
    print("tid=0x%05X rip=0x%012X rbx=0x%012X r14=0x%012X rsi=0x%012X "
          "rdi=0x%012X r12=0x%X r13=0x%X r15=0x%X"
          % (t.ThreadId, r(0xF8), r(0x90), r(0xE8), r(0xA8), r(0xB0),
             r(0xD8), r(0xE0), r(0xF0)))
