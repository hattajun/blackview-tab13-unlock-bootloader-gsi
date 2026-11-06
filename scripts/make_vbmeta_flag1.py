#!/usr/bin/env python3
"""Create a vbmeta image with only AVB_VBMETA_IMAGE_FLAGS_HASHTREE_DISABLED (1).

On the Blackview Tab 13, `fastboot --disable-verity --disable-verification`
(flags = 3) on vbmeta, vbmeta_system and vbmeta_vendor made the device fail to
boot (recovery reason `init_user0_failed`). Flags = 1 on the MAIN vbmeta only
(the two chained vbmetas left stock) booted both stock and the GSI.

The flags field is a big-endian u32 at offset 120 of the AVB vbmeta header.

Usage: make_vbmeta_flag1.py stock_vbmeta.bin vbmeta_flag1.bin
"""
import struct
import sys

src, dst = sys.argv[1], sys.argv[2]
d = bytearray(open(src, "rb").read())
assert d[:4] == b"AVB0", "not an AVB vbmeta image"
print("original flags:", struct.unpack(">I", d[120:124])[0])
struct.pack_into(">I", d, 120, 1)
open(dst, "wb").write(bytes(d))
print("new flags:     ", struct.unpack(">I", d[120:124])[0], "->", dst)
