"""
Check the type 0x04 house-number layout against the disc and against 0x0E S2.

Claims tested (03-road-network.md §6.4):
  1. +0x0C of every 0x04 block is the BLOCK_ID of a type 0x00 tile, and each tile has
     at most one 0x04 block.
  2. 0x04 SECTION_0 holds one 10-byte record per SECTION_4 segment of that tile
     (record count == tile e4 count).
  3. Record = [f0 f1 f2 f3 f4]: (f0, f2) and (f1, f3) are the two sides of the segment;
     f4 = numbering scheme (0 none, 1 mixed parity, 2 odd/even split).
  4. The even/odd ranges of a 0x0E S2 link (tile, S4 run) are the envelope of the 0x04
     ranges of the segments in that run.

Usage:
    python scripts/routing/check_04_house_numbers.py [--iso PATH] [--links 60] [--seed 5]
"""

from __future__ import annotations

import argparse
import random
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser.cf1 import decode_s2_links
from carin.parser.house_numbers import (NONE, run_envelope, segment_house_numbers,
                                        tile_block_id)
from carin.parser.iso import CarinVolume, IsoImage

ISO = "dataset/NAV_DB_21708.ISO"


def _payload_head(vol: CarinVolume, bid: int) -> bytes:
    """Header + descriptors of a block without running the CF=1 decoder
    (CF=1 copies the prologue verbatim)."""
    sec, ln = bid >> 8, bid & 0xFF
    head = vol.read_sectors(sec, 1)
    if head[6] == 2:
        raw = vol.read_sectors(sec, ln)
        return raw[:8] + zlib.decompress(raw[8:])
    return head


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default=ISO)
    ap.add_argument("--links", type=int, default=60, help="0x0E blocks to sample")
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args()

    vol = CarinVolume(IsoImage(args.iso))
    vol.calibrate()
    lay = vol.layout
    s4_rec = lay[0x08]

    heads = list(vol.walk())
    tiles = {(b.sector << 8) | b.length for b in heads if b.type == 0x00}
    by04: dict[int, list] = {}
    layout = Counter()
    fields = Counter()
    for b in heads:
        if b.type != 0x04:
            continue
        p = vol.block(b.sector).payload
        tile = tile_block_id(p)
        layout["service = 0x00 tile" if tile in tiles else "service not a tile"] += 1
        layout["duplicate tile"] += tile in by04
        by04[tile] = segment_house_numbers(p)
        off, cnt = struct.unpack_from(">HH", p, 8)
        for r in (struct.unpack_from(">5H", p, off + 10 * i) for i in range(cnt)):
            has = any(v != NONE for v in r[:4])
            mixed = any(a != NONE and c != NONE and a % 2 != c % 2
                        for a, c in ((r[0], r[2]), (r[1], r[3])))
            fields[(r[4], "mixed" if mixed else ("numbers" if has else "empty"))] += 1
    print("0x04 blocks:", sum(1 for b in heads if b.type == 0x04), dict(layout))
    print("f4 x content:", sorted(fields.items()))

    rng = random.Random(args.seed)
    count_ok = Counter()
    for tile in rng.sample(sorted(by04), 200):
        e4 = struct.unpack_from(">HH", _payload_head(vol, tile), 8 + 16)[1]
        count_ok[len(by04[tile]) == e4] += 1
    print("record count == tile S4 count:", dict(count_ok))

    res = Counter()
    e4off: dict[int, int] = {}
    b0e = [b.sector for b in heads if b.type == 0x0E]
    for s in rng.sample(b0e, args.links):
        blk = vol.block(s)
        if blk.data is None:
            res["0x0E undecoded"] += 1
            continue
        for link in decode_s2_links(blk.payload, lay):
            tile = link["tile_block_id"]
            if link["even"] is None and link["odd"] is None:
                res["link without numbers"] += 1
                continue
            if tile not in by04:
                res["tile without 0x04"] += 1
                continue
            if tile not in e4off:
                e4off[tile] = struct.unpack_from(">H", _payload_head(vol, tile), 8 + 16)[0]
            i0 = (link["s4_offset"] - e4off[tile]) // s4_rec
            got = run_envelope(by04[tile], i0, link["s4_count"])
            res["match" if got == (link["even"], link["odd"]) else "differ"] += 1
    print("0x0E S2 ranges vs 0x04 envelope:", dict(res))
    n = res["match"] + res["differ"]
    print(f"agreement: {res['match']}/{n} = {res['match'] / max(n, 1):.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
