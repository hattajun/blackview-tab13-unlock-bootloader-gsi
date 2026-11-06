#!/usr/bin/env python3
"""Extract logical partitions (system/vendor/product/...) from a `super` dump.

Minimal parser for the Android LP (dynamic partitions) metadata, linear extents
only. Tested with the Blackview Tab 13 `super` dump (LP metadata v10.0,
128-byte header, slot 0 metadata at 0x3000).

Usage: lp_extract.py super.bin outdir system vendor product
"""
import os
import struct
import sys


def main(super_path, outdir, wanted):
    f = open(super_path, "rb")

    f.seek(0x1000)  # geometry
    geo = f.read(52)
    assert struct.unpack("<I", geo[:4])[0] == 0x616C4467, "no LP geometry magic"

    f.seek(0x3000)  # primary metadata, slot 0
    h = f.read(256)
    assert struct.unpack("<I", h[:4])[0] == 0x414C5030, "no LP metadata magic"
    header_size = struct.unpack("<I", h[8:12])[0]
    tables_size = struct.unpack("<I", h[44:48])[0]
    poff, pnum, psz = struct.unpack("<III", h[80:92])    # partitions table
    eoff, enum, esz = struct.unpack("<III", h[92:104])   # extents table
    f.seek(0x3000 + header_size)
    tables = f.read(tables_size)

    parts = {}
    for i in range(pnum):
        e = tables[poff + i * psz: poff + (i + 1) * psz]
        name = e[:36].split(b"\0")[0].decode()
        _attrs, first, num, _group = struct.unpack("<IIII", e[36:52])
        parts[name] = (first, num)
    print("partitions:", list(parts))

    os.makedirs(outdir, exist_ok=True)
    for name in wanted:
        first, num = parts[name]
        out = os.path.join(outdir, name + ".img")
        total = 0
        with open(out, "wb") as o:
            for j in range(first, first + num):
                e = tables[eoff + j * esz: eoff + (j + 1) * esz]
                nsec, ttype, tdata = struct.unpack("<QIQ", e[:20])
                assert ttype == 0, "only linear extents are supported"
                f.seek(tdata * 512)
                left = nsec * 512
                total += left
                while left:
                    b = f.read(min(left, 1 << 24))
                    o.write(b)
                    left -= len(b)
        print(f"{name}: {num} extent(s), {total} bytes -> {out}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
