"""
Check the layout of the TMC index blocks 0x18, 0x1A and 0x1B against the disc.

Claims tested (01-architecture.md §4.7):
  1. 0x17 blocks form one doubly linked chain (+0x0C next, +0x10 prev BLOCK_ID); each holds
     one TMC table (+0x14) and the location codes +0x16 .. +0x18 of its 100-byte records.
  2. One 0x18 block per TMC table: +0x0C = table, S0 = {u32 BLOCK_ID of a 0x17 block,
     u16 first location code, u16 0} for every 0x17 block of that table in chain order,
     then a terminator {0, last code + 1, 0} counted in S0.
  3. 0x07 SECTION_1 (20-byte records) holds, per table, the 0x18 BLOCK_ID, the table, the
     first code, the offset of the country name in 0x07, the 0x0A COUNTRY_ID and an
     {offset, count} list of COUNTRY_IDs; the table's low nibble is the RDS country code.
  4. 0x19 blocks form one chain of 40-byte records sorted by the key (u16 x, u16 y); +0x14 /
     +0x18 hold the first / last key. Records link to other records by (BLOCK_ID +0x08,
     offset +0x16) and (BLOCK_ID +0x0C, offset +0x18).
  5. 0x1A: S0 = {u32 BLOCK_ID of a 0x19 block, i16 x, i16 y} = every 0x19 block in chain
     order with its first key, then a terminator {0, last key} not counted in S0.
  6. 0x1B: one 22-byte record {BLOCK_ID of 0x1A, first key, i32 X0, i32 Y0, u16, u16,
     u16 COUNTRY_ID}; 0x07 lists it in the layer directory.
  7. (--geometry) 0x19 +0x04 is the BLOCK_ID of a 0x00 tile and +0x14 the byte offset of a
     SECTION_4 segment in it; the key is that place in 100 m steps on a sphere:
     y = R * (lat - lat0), x = R * (lon - lon0) * cos(lat), in radians, R ~ 6371 km,
     rounded to nearest. Fitted against the midpoints of the linked segments; the bias must
     not follow the sign of the key (truncation would give -0.5 / +0.5).

Usage:
    python scripts/routing/check_tmc_index.py [--iso PATH] [--geometry]
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser.geometry import VERTEX_SHIFT, _sections, tile_frame
from carin.parser.iso import CarinVolume, IsoImage

ISO = "dataset/NAV_DB_21708.ISO"
K = 2_000_000_000 / 360
STEP = 100.0                     # metres per key step
R_EARTH = 6_371_000.0

# RDS/TMC country code (PI high nibble) by ISO 3166 code
RDS_CC = {"at": 0xA, "ch": 0x4, "de": 0xD, "cz": 0x2, "es": 0xE, "dk": 0x9, "it": 0x5,
          "gb": 0xC, "no": 0xF, "nl": 0x8, "fr": 0xF, "be": 0x6, "se": 0xE}


def bid(b) -> int:
    return (b.sector << 8) | b.length


def chain(heads: dict[int, tuple]) -> list[int]:
    """heads: BLOCK_ID -> (next, prev, ...). Returns the chain from its only head."""
    first = [b for b, h in heads.items() if h[1] == 0]
    assert len(first) == 1, f"{len(first)} chain heads"
    out, cur = [], first[0]
    while cur:
        out.append(cur)
        cur = heads[cur][0]
    assert len(out) == len(heads), f"chain covers {len(out)} of {len(heads)}"
    return out


def countries(vol: CarinVolume) -> dict[int, str]:
    """COUNTRY_ID -> ISO code, from the 0x0A country tables (§4.4)."""
    out = {}
    for sector in (9, 13):
        p = vol.block(sector).payload
        off, cnt = struct.unpack_from(">HH", p, 0x0C)
        for i in range(cnt):
            r = off + 56 * i
            cid = struct.unpack_from(">H", p, r + 0x28)[0]
            out[cid] = p[r + 0x2E:r + 0x30].decode("latin-1")
    return out


def fit(pairs: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Least squares key = a * feature + b with 4-sigma trimming. Returns (a, b, sd)."""
    keep = pairs
    for _ in range(3):
        n = len(keep)
        mf = sum(f for f, _ in keep) / n
        mk = sum(k for _, k in keep) / n
        a = (sum((f - mf) * (k - mk) for f, k in keep) /
             sum((f - mf) ** 2 for f, _ in keep))
        b = mk - a * mf
        sd = math.sqrt(sum((k - a * f - b) ** 2 for f, k in keep) / n)
        keep = [(f, k) for f, k in pairs if abs(k - a * f - b) < 4 * sd]
    return a, b, sd


def check_geometry(vol: CarinVolume, b19: dict[int, bytes], x0: int, y0: int,
                   fail: Counter) -> None:
    table = vol.layout
    rec4 = table[0x08]
    lat0, lon0 = math.radians(y0 / K), math.radians(x0 / K)
    tiles: dict[int, tuple | None] = {}
    fx, fy, no_tile = [], [], 0
    for p in b19.values():
        off, cnt = struct.unpack_from(">HH", p, 8)
        for i in range(cnt):
            r = off + 40 * i
            kx, ky, tile = struct.unpack_from(">hhI", p, r)
            s4off = struct.unpack_from(">H", p, r + 0x14)[0]
            if not tile:
                no_tile += 1
                continue
            if tile not in tiles:
                blk = vol.block(tile >> 8)
                d = blk.data
                tiles[tile] = (d, tile_frame(d, table), _sections(d, table)[4]) \
                    if blk.type == 0x00 and d else None
            if tiles[tile] is None:
                fail["0x19 +0x04 not a decodable 0x00 tile"] += 1
                continue
            d, frame, (s4, n4) = tiles[tile]
            if (s4off - s4) % rec4 or not s4 <= s4off < s4 + n4 * rec4:
                fail["0x19 +0x14 not a SECTION_4 record"] += 1
                continue
            a, b = struct.unpack_from(">HH", d, s4off)
            (u, v), (u2, v2) = struct.unpack_from(">HH", d, a), struct.unpack_from(">HH", d, b)
            lon = math.radians((frame.x0 + ((u + u2) << VERTEX_SHIFT) / 2) / K)
            lat = math.radians((frame.y0 + ((v + v2) << VERTEX_SHIFT) / 2) / K)
            fx.append(((lon - lon0) * math.cos(lat) / STEP, kx))
            fy.append(((lat - lat0) / STEP, ky))
    print(f"geometry: {len(fy)} records linked to {len(tiles)} tiles, {no_tile} without tile")
    for name, pairs in (("y", fy), ("x", fx)):
        a, b, sd = fit(pairs)
        print(f"  {name}: R = {a:,.0f} m, intercept {b:+.3f}, residual sd {sd:.2f} steps")
        fail[f"geometry {name}: R not ~6371 km"] += abs(a - R_EARTH) > 1000
        fail[f"geometry {name}: biased or loose"] += abs(b) > 0.25 or sd > 2.5
        for sign in (-1, 1):
            r = [k - a * f - b for f, k in pairs if sign * f * a > 1 and abs(k - a * f - b) < 5]
            bias = sum(r) / len(r)
            print(f"    {name} {'<0' if sign < 0 else '>0'}: mean residual {bias:+.3f} (n {len(r)})")
            fail[f"geometry {name}: bias follows sign (truncation)"] += abs(bias) > 0.25


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default=ISO)
    ap.add_argument("--geometry", action="store_true",
                    help="also check 0x19 -> 0x00 links and the key projection (slow)")
    args = ap.parse_args()

    vol = CarinVolume(IsoImage(args.iso))
    vol.calibrate()
    by_type: dict[int, dict[int, bytes]] = {t: {} for t in (0x17, 0x18, 0x19, 0x1A, 0x1B)}
    for b in vol.walk():
        if b.type in by_type:
            by_type[b.type][bid(b)] = vol.block(b.sector).payload
    print("blocks:", {f"{t:#04x}": len(v) for t, v in by_type.items()})
    fail = Counter()

    # 1. 0x17 chain
    h17 = {b: struct.unpack_from(">IIHHH", p, 0x0C) for b, p in by_type[0x17].items()}
    order17 = chain(h17)
    for b, p in by_type[0x17].items():
        off, cnt = struct.unpack_from(">HH", p, 8)
        codes = [struct.unpack_from(">H", p, off + 100 * i)[0] for i in range(cnt)]
        fail["0x17 codes not first..last ascending"] += (
            codes[0] != h17[b][3] or codes[-1] != h17[b][4] or codes != sorted(codes))

    # 2. 0x18 -> 0x17
    tables = {}
    for b, p in by_type[0x18].items():
        off, cnt, table = struct.unpack_from(">HHH", p, 8)
        recs = [struct.unpack_from(">IHH", p, off + 8 * i) for i in range(cnt)]
        body, term = recs[:-1], recs[-1]
        run = [r[0] for r in body]
        i = order17.index(run[0])
        fail["0x18 run != 0x17 chain slice"] += run != order17[i:i + len(run)]
        fail["0x18 run mixes tables / key mismatch"] += any(
            h17[r[0]][2] != table or h17[r[0]][3] != r[1] or r[2] for r in body)
        fail["0x18 run not the whole table"] += sum(h[2] == table for h in h17.values()) != len(run)
        fail["0x18 terminator != {0, last+1, 0}"] += term != (0, h17[run[-1]][4] + 1, 0)
        tables[table] = (b, body[0][1])
    covered = sum(struct.unpack_from(">H", p, 10)[0] - 1 for p in by_type[0x18].values())
    print(f"0x18: {len(tables)} tables cover {covered} / {len(h17)} 0x17 blocks")

    # 3. 0x07 SECTION_1
    p07 = vol.block(3).payload
    off, cnt = struct.unpack_from(">HH", p07, 8 + 4)
    cmap = countries(vol)
    for i in range(cnt):
        b18, table, first, name, _, flag, cid, zero, loff, lcnt = struct.unpack_from(
            ">IHHHBBHHHH", p07, off + 20 * i)
        iso = cmap.get(cid, "?")
        fail["0x07 S1 != 0x18 (BLOCK_ID, table, first code)"] += tables.get(table) != (b18, first)
        fail["0x07 S1 table low nibble != RDS CC"] += RDS_CC.get(iso) != table & 0xF
        ids = [struct.unpack_from(">H", p07, loff + 2 * j)[0] for j in range(lcnt)]
        fail["0x07 S1 country list != [COUNTRY_ID]"] += ids != [cid] or zero != 0
        text = p07[name:p07.index(b"\0", name)].decode("latin-1")
        print(f"  table {table:#05x} (LTN {table >> 4:2}, CC {table & 0xF:X}) "
              f"country {cid:#04x} {iso} '{text}' flag {flag}  first code {first}")

    # 4. 0x19 chain, sorted keys, record links
    h19 = {b: struct.unpack_from(">II4h", p, 0x0C) for b, p in by_type[0x19].items()}
    order19 = chain(h19)
    keys, starts = [], set()
    for b in order19:
        p = by_type[0x19][b]
        off, cnt = struct.unpack_from(">HH", p, 8)
        ks = [struct.unpack_from(">hh", p, off + 40 * i) for i in range(cnt)]
        fail["0x19 +0x14/+0x18 != first/last key"] += (ks[0] != h19[b][2:4] or
                                                        ks[-1] != h19[b][4:6])
        keys += ks
        starts |= {(b, off + 40 * i) for i in range(cnt)}
    u = [(x & 0xFFFF, y & 0xFFFF) for x, y in keys]
    fail["0x19 keys not sorted (unsigned)"] += u != sorted(u)
    links = 0
    for b, off in starts:
        p = by_type[0x19][b]
        b1, b2 = struct.unpack_from(">II", p, off + 8)
        o1, o2 = struct.unpack_from(">HH", p, off + 0x16)
        for lb, lo in ((b1, o1), (b2, o2)):
            if lb:
                links += 1
                fail["0x19 link not a record start"] += (lb, lo) not in starts
            else:
                fail["0x19 null link with offset"] += lo != 0
    print(f"0x19: {len(keys)} records, {links} record links")

    # 5. 0x1A -> 0x19
    (b1a, p1a), = by_type[0x1A].items()
    off, cnt = struct.unpack_from(">HH", p1a, 8)
    recs = [struct.unpack_from(">Ihh", p1a, off + 8 * i) for i in range(cnt + 1)]
    fail["0x1A != 0x19 chain"] += [r[0] for r in recs[:-1]] != order19
    fail["0x1A key != first key"] += any(h19[r[0]][2:4] != r[1:] for r in recs[:-1])
    fail["0x1A terminator != {0, last key}"] += recs[-1] != (0, *h19[order19[-1]][4:6])
    print(f"0x1A: {cnt} entries, 0x19 chain {len(order19)} blocks")

    # 6. 0x1B
    (b1b, p1b), = by_type[0x1B].items()
    off, cnt = struct.unpack_from(">HH", p1b, 8)
    root, kx, ky, x0, y0, u0, u1, cid = struct.unpack_from(">Ihhii3H", p1b, off)
    fail["0x1B root != 0x1A"] += root != b1a or cnt != 1
    fail["0x1B key != first key"] += (kx, ky) != keys[0]
    fail["0x1B not in 0x07 layer directory"] += struct.pack(">I", b1b) not in p07[0x14:0x174]
    print(f"0x1B: origin {x0 / K - 30:.4f} E, {y0 / K:.4f} N, u16 {u0:#x} {u1:#x}, "
          f"country {cid:#04x} {cmap.get(cid, '?')}")

    # 7. key projection
    if args.geometry:
        check_geometry(vol, by_type[0x19], x0, y0, fail)

    bad = {k: v for k, v in fail.items() if v}
    print("failures:", bad or "none")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
