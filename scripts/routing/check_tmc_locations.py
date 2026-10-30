"""
Check the TMC location records (0x17) and their section 12 references against the disc.

Claims tested (01-architecture.md §4.7, 03-road-network.md §6.7):
  1. The 0x17 chain, the 0x18 index and the record area: S0 = 100-byte records, then the strings.
  2. Every string pointer (+0x06, +0x08, +0x0A, +0x0C) lands in the string area of its block;
     every link (+0x0E, +0x10, +0x12, +0x14, +0x18, +0x1A) is a location code of the same table;
     +0x12 / +0x14 are symmetric (next.prev == this); every point lies in the European range
     (lon -35..65, lat 20..75, which includes the Canary Islands).
  3. (--s12) The section 12 triple of a road-tile segment is (direction, code, flags) with
     flags & 0x3FF = the table id of 0x18: it names a record, and the segment lies near that
     record. Tested against the distance to a random point of the same table.
Table ids that the road tiles use but the disc has no 0x17 table for are counted, not failed
(the 2007 CD references the UK, LTN 7 and 10, and carries no UK table).

Usage:
    python scripts/routing/check_tmc_locations.py PATH [--sector-size 512] [--s12] [--stride 10]

PATH is an ISO image or a bare carindb file. --stride N samples every N-th 0x00 tile for --s12.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser.cf1.tile00 import Tile00
from carin.parser.iso import CarinVolume, open_image
from carin.parser.tmc import Location, decode_s12, parse_0x17, parse_0x18

LINKS = ("parent", "road", "prev", "next", "first", "last")
EUROPE = (-35.0, 65.0, 20.0, 75.0)          # lon min, lon max, lat min, lat max; includes the Canaries
MAX_MEDIAN_KM = 10.0                        # a real link is near; a random one is ~100s of km


def km(a, b) -> float:
    return math.hypot((a[0] - b[0]) * math.cos(math.radians(a[1])), a[1] - b[1]) * 111.195


def check_records(locs: Iterable[Location], fail: Counter) -> None:
    """Link, symmetry and coordinate checks over all records."""
    by_table: Dict[int, Dict[int, Location]] = defaultdict(dict)
    for loc in locs:
        by_table[loc.table][loc.code] = loc
    for table, codes in by_table.items():
        for loc in codes.values():
            for name in LINKS:
                v = getattr(loc, name)
                fail["link %s not in table" % name] += bool(v) and v not in codes
            if loc.next and loc.next in codes:
                fail["next.prev != this"] += codes[loc.next].prev != loc.code
            for p in loc.points:
                if p:
                    fail["point outside the European range"] += not (
                        EUROPE[0] < p[0] < EUROPE[1] and EUROPE[2] < p[1] < EUROPE[3])


def check_link_distances(dists: List[float], baseline: List[float], fail: Counter) -> None:
    dists, baseline = sorted(dists), sorted(baseline)
    if not dists:
        fail["no section 12 point links found"] += 1
        return
    fail["median link distance too large"] += dists[len(dists) // 2] > MAX_MEDIAN_KM
    fail["link no nearer than random"] += (
        bool(baseline) and dists[len(dists) // 2] * 10 > baseline[len(baseline) // 2])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--sector-size", type=int, default=None)
    ap.add_argument("--s12", action="store_true",
                    help="also test the section 12 references of the 0x00 tiles (slow)")
    ap.add_argument("--stride", type=int, default=10, help="with --s12: every N-th 0x00 tile")
    args = ap.parse_args()

    vol = CarinVolume(open_image(args.path), sector_size=args.sector_size)
    vol.calibrate()
    fail: Counter = Counter()

    p17, p18, tiles = {}, {}, []
    for b in vol.walk():
        bid = (b.sector << 8) | b.length
        if b.type == 0x17:
            p17[bid] = vol.block(b.sector).payload
        elif b.type == 0x18:
            p18[bid] = vol.block(b.sector).payload
        elif b.type == 0x00:
            tiles.append(b.sector)
    print(f"blocks: 0x17 {len(p17)}, 0x18 {len(p18)}, 0x00 {len(tiles)}")

    # 1. chain and 0x18
    parsed = {bid: parse_0x17(p) for bid, p in p17.items()}
    heads = [b for b, (h, _) in parsed.items() if h.prev_block == 0]
    fail["0x17 chain heads != 1"] += len(heads) != 1
    order, cur = [], heads[0] if heads else 0
    while cur in parsed and cur not in order:
        order.append(cur)
        cur = parsed[cur][0].next_block
    fail["0x17 chain does not cover all blocks"] += len(order) != len(parsed)
    for bid, (h, recs) in parsed.items():
        codes = [r.code for r in recs]
        fail["0x17 codes not first..last ascending"] += (
            not recs or codes[0] != h.first_code or codes[-1] != h.last_code or codes != sorted(codes))
    tables = {}
    for bid, p in p18.items():
        table, runs = parse_0x18(p)
        in_table = [b for b in order if parsed[b][0].table == table]
        fail["0x18 run != 0x17 blocks of the table"] += [b for b, _ in runs] != in_table
        tables[table] = len(runs)
    fail["0x17 tables without 0x18"] += len({h.table for h, _ in parsed.values()} - set(tables))
    locs = [r for b in order for r in parsed[b][1]]
    print(f"0x18: {len(tables)} tables over {sum(tables.values())} blocks; {len(locs)} location records")
    for t, n in sorted(tables.items()):
        print(f"  table {t:#05x} (LTN {t >> 4}, CC {t & 0xF:X}): {n} blocks")

    # 2. records
    kinds = Counter(r.kind for r in locs)
    print("kinds:", dict(kinds), "; without a name:", sum(r.name is None for r in locs))
    check_records(locs, fail)

    # 3. section 12
    if args.s12:
        points = {(r.table, r.code): r for r in locs if r.kind == "point" and r.points[0]}
        pts_by_table = defaultdict(list)
        for r in points.values():
            pts_by_table[r.table].append(r)
        have = {r.table for r in locs}
        known = {(r.table, r.code): r for r in locs}
        rnd = random.Random(1)
        n: Counter = Counter()
        dists: List[float] = []
        base: List[float] = []
        unknown: Counter = Counter()
        directions: Counter = Counter()
        for s in tiles[::args.stride]:
            try:
                t = Tile00.parse(vol.block(s).data, vol.layout)
            except Exception:  # noqa: BLE001
                n["tiles not parsed"] += 1
                continue
            for sg in t.segs:
                if not sg.tmc:
                    continue
                poly = t.polyline(sg)
                for e in sg.tmc:
                    ref = decode_s12(e)
                    n["triples"] += 1
                    if ref.table not in have:
                        n["table without 0x17"] += 1
                        unknown[ref.table] += 1
                        continue
                    loc = known.get((ref.table, ref.code))
                    if loc is None:
                        n["code not in table"] += 1
                        continue
                    n["resolved"] += 1
                    directions[(ref.direction, loc.kind)] += 1
                    if (ref.table, ref.code) in points:
                        dists.append(min(km(v, q) for v in poly for q in loc.points if q))
                        other = rnd.choice(pts_by_table[ref.table])
                        base.append(min(km(v, q) for v in poly for q in other.points if q))
        print("section 12:", dict(n))
        print("  direction x kind:", dict(sorted(directions.items())))
        print("  tables used but not on the disc:",
              {f"{t:#05x} (LTN {t >> 4}, CC {t & 0xF:X})": c for t, c in unknown.most_common()})
        fail["code not in table (> 1 %)"] += n["code not in table"] > 0.01 * max(n["triples"], 1)
        if dists:
            dists.sort()
            base.sort()
            print(f"  {len(dists)} point links: distance segment vertex -> record point, km: "
                  f"p50 {dists[len(dists) // 2]:.2f}, p90 {dists[int(len(dists) * .9)]:.2f}; "
                  f"random point of the same table: p50 {base[len(base) // 2]:.0f}")
        check_link_distances(dists, base, fail)

    bad = {k: v for k, v in fail.items() if v}
    print("failures:", bad or "none")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
