"""Scan all captured memory for fault CONTEXT records (Rip == fault addr)
and print their register sets."""
import struct
import sys

from minidump.minidumpfile import MinidumpFile

DUMP = sys.argv[1]
FAULT_RIP = int(sys.argv[2], 0)

mf = MinidumpFile.parse(DUMP)
seglist = (mf.memory_segments_64.memory_segments
           if mf.memory_segments_64 else mf.memory_segments.memory_segments)
buf = mf.file_handle
needle = struct.pack("<Q", FAULT_RIP)

for s in seglist:
    if s.size > 0x10000000:
        continue
    buf.seek(s.start_file_address)
    data = buf.read(s.size)
    pos = 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            break
        # If this is CONTEXT.Rip (offset 0xF8), registers precede it.
        base = pos - 0xF8
        if base >= 0:
            def r(off):
                return struct.unpack_from("<Q", data, base + off)[0]
            rcx, rsp, rbx = r(0x80), r(0x98), r(0x90)
            # heuristics: AV read of tiny addr, plausible stack ptr
            if rcx < 0x10000 and rsp > 0x10000:
                print("CONTEXT @0x%X: RIP=0x%X RCX=0x%X RSP=0x%X "
                      "RBX=0x%X RAX=0x%X R14=0x%X"
                      % (s.start_virtual_address + base, FAULT_RIP, rcx,
                         rsp, rbx, r(0x78), r(0xE8)))
        pos += 8
