#!/usr/bin/env python3
"""Create a `misc` image whose bootloader message (BCB) makes the device boot
into fastbootd on the next start.

Use it when the device is stuck in the stock recovery ("Can't load Android
system") and you cannot reach fastboot with the hardware keys:

    mtk w misc misc_fastboot.bin     # then power the tablet on

BCB layout (struct bootloader_message): command[32], status[32], recovery[768].

Usage: make_misc_fastboot.py stock_misc.bin misc_fastboot.bin
"""
import sys

src, dst = sys.argv[1], sys.argv[2]
d = bytearray(open(src, "rb").read())
d[0:32] = b"boot-recovery".ljust(32, b"\0")
d[32:64] = b"\0" * 32
d[64:832] = b"recovery\n--fastboot\n".ljust(768, b"\0")
open(dst, "wb").write(bytes(d))
print("wrote", dst, len(d), "bytes")
