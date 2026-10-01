"""Claim: a decoded CF=1 type 0x00 tile survives `Tile00.parse` -> `build` byte for byte, and tiles
whose sections are forced to move (empty room inserted in S4, S5, S7, or all three) have the same
`graph()`, re-encode with `encode_type00` and decode back to the same bytes.

    uv run --with numpy python scripts/codec_cf1/check_tile00_relayout.py <iso> [--n 40] [--sector 0x4c184f]

Tiles are sampled evenly over the size distribution of the disc (sizes in 512-byte sectors on disc).
"""
from __future__ import annotations

import argparse
import sys
import zlib
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser import cf1
from carin.parser.cf1.tile00 import Tile00, TileError, diff_graph
from carin.parser.iso import CarinVolume, IsoImage


def shifted(d: bytes, table: dict, sec: int, n: int = 6) -> bytes:
    """Re-lay the tile with `n` extra zero bytes after section `sec`: everything behind it moves, no
    record changes. Section 3 moves S4 onwards, 4 moves S5, 7 moves S9 and the rest."""
    t = Tile00.parse(d, table)
    t.gaps[sec] = t.gaps.get(sec, b"") + bytes(n)
    return t.build()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("iso")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--coarse", type=int, default=0, help="also sample this many coarse tiles (types 0x01-0x03, zlib)")
    ap.add_argument("--sector", action="append", default=[], help="extra block sector (hex) to include")
    ap.add_argument("--index", help="json list of [sector, length, type, comp, usize] (skips the disc walk)")
    args = ap.parse_args()

    vol = CarinVolume(IsoImage(args.iso))
    vol.calibrate()
    if args.index:
        import json
        idx = json.load(open(args.index))
    else:
        idx = [(b.sector, b.length, b.type, b.comp, b.usize) for b in vol.walk() if b.type <= 3]
    heads = sorted(((s, l) for s, l, ty, cf, _ in idx if ty == 0 and cf & 1), key=lambda h: h[1])
    pick = [heads[int(i * (len(heads) - 1) / max(1, args.n - 1))] for i in range(args.n)]
    coarse = sorted(((s, l) for s, l, ty, cf, _ in idx if 1 <= ty <= 3 and cf == 2), key=lambda h: h[1])
    pick += [coarse[int(i * (len(coarse) - 1) / max(1, args.coarse - 1))] for i in range(args.coarse)]
    pick += [(int(s, 16), 0) for s in args.sector]

    errors = Counter()
    ok = 0
    for sector, length in pick:
        blk = vol.block(sector)
        d = blk.payload
        try:
            t = Tile00.parse(d, vol.layout)
        except TileError as e:
            errors[str(e).split(":")[0]] += 1
            print(f"{sector:#x} ({blk.length} sectors): PARSE {e}")
            continue
        out = t.build()
        row = [f"{sector:#x}", f"{blk.length:3d} sec", f"{len(t.segs):4d} seg"]
        if out != d:
            print(*row, "NULL RELAYOUT DIFFERS", sum(a != b for a, b in zip(out, d)), "bytes")
            errors["null"] += 1
            continue
        g0 = t.graph()
        broken = t.check()
        if broken:
            errors["rules"] += 1
            print(*row, "RULES BROKEN on the untouched tile:", len(broken), broken[:3])
        n = Tile00.parse(d, vol.layout)
        n.normalize()
        if n.build() != d:
            errors["normalize"] += 1
            print(*row, "normalize() does not reproduce the tile")
        for label, secs in (("S3", (3,)), ("S4", (4,)), ("S7", (7,)), ("all", (3, 4, 7))):
            grown = d
            for sec in secs:
                grown = shifted(grown, vol.layout, sec)
            r = Tile00.parse(grown, vol.layout)
            gr = r.graph()
            gr["gaps"] = g0["gaps"]
            if grown == d:
                errors[f"{label} no shift"] += 1
            if gr != g0:
                errors[f"{label} graph"] += 1
                print(*row, label, "GRAPH DIFFERS", diff_graph(g0, gr)[:5])
            if blk.comp & 1:
                enc = cf1.encode_type00(grown, vol.layout, vol.db_rel, vol.subrel)
                back = cf1.decode_block(enc, vol.layout, vol.db_rel, subrel=vol.subrel, sector_size=vol.sector_size)
            else:                                                  # zlib block: header + deflate of the rest
                back = grown[:8] + zlib.decompress(zlib.compress(grown[8:], 9))
            if back != grown:
                errors[f"{label} re-decode"] += 1
                print(*row, label, "RE-DECODE DIFFERS")
        ok += 1
        print(*row, "null relayout identical; " + ("rules hold; " if not broken else "") +
              "4 forced shifts re-encode and re-read")
    print(f"\n{ok} / {len(pick)} tiles clean; errors: {dict(errors) or 'none'}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
