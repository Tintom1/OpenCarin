"""
Check the spatial index 0x07 -> 0x08 -> 0x09 -> tiles against every block of a disc.

Claims tested (02-geo.md §7.3):
  1. 0x07: 12 records of 28 bytes at +0x14 = {u32 BLOCK_ID, 4 x i32 root square, 4 x u16}.
     Every record points at a 0x08 block, except one that points at the 0x1B block with an
     all-zero square and parameters. All 0x08 records carry the same square root.
  2. 0x08: one section at +0x10 of u32 entries, +0x0C u32 = cell side; the rest of the block
     is zero. A layer's grid is the run of physically consecutive 0x08 blocks starting at its
     directory BLOCK_ID, all with the same cell side, whose entries add up to N^2
     (N = root side / cell side, exact). Entries are 0 or the BLOCK_ID of a 0x09 block; no
     0x09 appears twice. 0x08 blocks outside every layer's run are reported (and must form
     complete grids over the same root that satisfy every rule below).
  3. 0x09: S0 at +0x14 (u16 pointers), S1 at the next 4-aligned offset (u32 BLOCK_IDs),
     +0x10 u32 = item side; the gap after S0 and everything after S1 are zero.
     count(S0) = (cell side / item side)^2, exact. Every non-zero pointer is the absolute
     offset of an S1 entry; every S1 entry is pointed at; S1 has no duplicate and is in the
     order its entries are first met scanning S0.
  4. Grid order: entry k of a grid of n x n is cell (k // n, k % n) (x east, y north), in
     0x08 and in 0x09 alike. Test: the items pointing at a tile, over all 0x09 blocks, are
     disjoint and their union is exactly the tile's bounding box (area and extent).
  5. Item side = the smallest side of (tile bbox ∩ cell) over the cell's tiles, and the gcd of
     those sides and of their offsets from the cell corner.
  6. Each layer holds one tile block type; every tile block on the disc is reached.
  7. carin.parser.spatial.tiles_at at the centre of every reached tile's bbox returns it.
  8. Every tile's sides are root side / 2^k, 1:1 or 2:1, and its corner is a multiple of its
     own width (x) and height (y) from the root corner. (This replaces the old "multiples of
     98,304 from (0, 0)" rule; the script counts the tiles that break it.)
  9. How the RR firmware finds the directory (dbq 0x2081c / 0x21270, db_bh_read 0x17cc): the
     superblock S0 (8-byte records, RECORD_SIZE_TABLE T[0x1E]) starts with the BLOCK_ID of
     0x07; T[0x05] + T[0x1A] = directory offset, T[0x18] = record size,
     T[0x19] = 12 records + 16-byte trailer, T[0x17] = the 0x07 S0 offset.
 10. Parameter 0 of each road layer (tiles 0x00-0x03) = the highest road class
     (S4 +0x10 & 0x0F; S4 record T[0x08] for 0x00, T[0x09] for 0x01-0x03) over its tiles, and
     no segment has a higher class (rpmod 0x7490c). 0x01-0x03 always; 0x00 (CF=1) only with
     --cf1-rust.

Tile bounding boxes are read at +0x44 (0x00-0x03), +0x10 (0x06), +0x20 (0x14-0x16,
0x1C-0x1E) (02-geo.md §7.4). CF=1 blocks are read from their plaintext prologue, which both
decoders copy verbatim (carin/parser/cf1: copy_raw(0, T_PROLOG...)); the script checks the
prologue covers the bbox. --cf1-rust also decodes every CF=1 tile with carindb-rs dump-type
and checks the decoded bbox equals the prologue one (slow: a few GB of temporary files).

Usage:
    python scripts/geo/check_spatial_index.py [--iso PATH] [--cf1-rust]
"""

from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from collections import Counter, defaultdict
from math import gcd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser.cf1.constants import T_PROLOG, T_PROLOG_141516
from carin.parser.iso import CarinVolume, IsoImage, to_wgs84
from carin.parser.spatial import (DIR_OFFSET, DIR_RECORD_SIZE, DIR_RECORDS, parse_cell,
                                  parse_grid_block, parse_layer_directory, tiles_at)

ISO = "dataset/NAV_DB_21708.ISO"
RUST = Path(__file__).resolve().parents[2] / "carindb-rs/target/release/carindb-rs"
BBOX_AT = {0x00: 0x44, 0x01: 0x44, 0x02: 0x44, 0x03: 0x44, 0x06: 0x10,
           0x14: 0x20, 0x15: 0x20, 0x16: 0x20, 0x1C: 0x20, 0x1D: 0x20, 0x1E: 0x20}
PROLOG = {0x00: T_PROLOG, 0x14: T_PROLOG_141516, 0x15: T_PROLOG_141516,
          0x16: T_PROLOG_141516, 0x1C: T_PROLOG_141516, 0x1D: T_PROLOG_141516,
          0x1E: T_PROLOG_141516}


ROAD_TYPES = (0x00, 0x01, 0x02, 0x03)


def bid(b) -> int:
    return (b.sector << 8) | b.length


def max_road_class(p: bytes, btype: int, layout: dict) -> int:
    """Highest road class (S4 +0x10 & 0x0F) of a decoded 0x00-0x03 tile; -1 if S4 is empty."""
    s4, n4 = struct.unpack_from(">HH", p, 8 + 4 * 4)
    rec = layout[0x08] if btype == 0x00 else layout[0x09]
    return max((p[s4 + rec * i + 0x10] & 0x0F for i in range(n4)), default=-1)


def collect(vol: CarinVolume, fail: Counter):
    heads, p08, p09, bbox = {}, {}, {}, {}
    for b in vol.walk():
        heads[bid(b)] = b
        if b.type == 0x08:
            p08[bid(b)] = vol.block(b.sector).payload
        elif b.type == 0x09:
            p09[bid(b)] = vol.block(b.sector).payload
        elif b.type in BBOX_AT:
            at = BBOX_AT[b.type]
            if b.comp == 2:
                raw = vol.read_sectors(b.sector, b.length)
                head = raw[:8] + zlib.decompressobj().decompress(raw[8:], at + 16)
            else:
                if b.comp == 1 and (b.type not in PROLOG or vol.layout[PROLOG[b.type]] < at + 16):
                    fail["tile CF=1 bbox outside the plaintext prologue"] += 1
                    continue
                head = vol.read_sectors(b.sector, 1)
            bbox[bid(b)] = (b.type, struct.unpack_from(">4i", head, at))
    return heads, p08, p09, bbox


def check_cf1_rust(iso: str, heads: dict, bbox: dict, fail: Counter, layout: dict) -> dict:
    """Decoded (carindb-rs) bbox == plaintext-prologue bbox on every CF=1 tile.

    Returns {tile BLOCK_ID: highest road class} for every dumped 0x00 tile (claim 10)."""
    classes = {}
    by_sector = {k >> 8: k for k in heads}
    for t in sorted(PROLOG):
        want = {k >> 8: v[1] for k, v in bbox.items() if v[0] == t and heads[k].comp == 1}
        if not want:
            continue
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([str(RUST), "dump-type", f"{t:#04x}", "--iso", iso, "--out", d],
                           check=True, capture_output=True)
            seen = bad = 0
            for f in os.listdir(d):
                sector = int(f[7:15], 16)
                if t == 0x00 and sector in by_sector and not f.endswith(".cf1raw.bin"):
                    with open(os.path.join(d, f), "rb") as fh:
                        classes[by_sector[sector]] = max_road_class(fh.read(), t, layout)
                if sector not in want:
                    continue
                with open(os.path.join(d, f), "rb") as fh:
                    head = fh.read(BBOX_AT[t] + 16)
                seen += 1
                bad += struct.unpack_from(">4i", head, BBOX_AT[t]) != want[sector]
        fail["CF=1 tile not decoded by carindb-rs"] += len(want) - seen
        fail["CF=1 decoded bbox != prologue bbox"] += bad
        print(f"  CF=1 {t:#04x}: {seen} / {len(want)} decoded, {bad} bbox mismatches")
    return classes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", default=ISO)
    ap.add_argument("--cf1-rust", action="store_true",
                    help="cross-check CF=1 tile bboxes against carindb-rs decoding (slow)")
    args = ap.parse_args()

    vol = CarinVolume(IsoImage(args.iso))
    fail = Counter()
    heads, p08, p09, bbox = collect(vol, fail)
    by_sector = {k >> 8: k for k in heads}
    def cf(blocks):
        return dict(sorted(Counter(heads[k].comp for k in blocks).items()))

    print(f"blocks (by CF): 0x08 {len(p08)} {cf(p08)}, 0x09 {len(p09)} {cf(p09)}, "
          f"tiles {len(bbox)}")

    # 1. 0x07 layer directory
    p07 = vol.block(3).payload
    fail["0x07 not DB-REL 34"] += vol.db_rel != 34
    layers = parse_layer_directory(p07)
    fail["0x07 directory overruns S0"] += DIR_OFFSET + DIR_RECORDS * DIR_RECORD_SIZE > \
        struct.unpack_from(">H", p07, 8)[0]
    roots = set()
    grid_layers = []
    for l in layers:
        t = heads[l.grid].type if l.grid in heads else None
        if t == 0x08:
            grid_layers.append(l)
            roots.add(l.root)
        elif t == 0x1B:
            fail["0x07 0x1B record has a square or parameters"] += any(l.root) or any(l.params)
        else:
            fail["0x07 record points at neither 0x08 nor 0x1B"] += 1
    # 9. the firmware's route to the directory
    T = vol.layout
    sb = vol.read_sectors(0, 1)
    s0_off, s0_cnt = struct.unpack_from(">HH", sb, 8)
    b07 = struct.unpack_from(">I", sb, s0_off)[0] if s0_cnt else None
    fail["superblock S0[0] is not the 0x07 block"] += not (
        b07 in heads and heads[b07].type == 0x07 and heads[b07].sector == 3)
    fail["T[0x1E] != 8 (superblock S0 record)"] += T.get(0x1E) != 8
    fail["T[0x05] + T[0x1A] != directory offset"] += T.get(0x05, 0) + T.get(0x1A, 0) != DIR_OFFSET
    fail["T[0x18] != directory record size"] += T.get(0x18) != DIR_RECORD_SIZE
    fail["T[0x19] != 12 records + 16-byte trailer"] += \
        T.get(0x19) != DIR_RECORDS * DIR_RECORD_SIZE + 16
    fail["T[0x17] != 0x07 S0 offset"] += T.get(0x17) != struct.unpack_from(">H", p07, 8)[0]
    fail["0x07 roots differ"] += len(roots) != 1
    fail["0x07 root not square"] += any(r[2] - r[0] != r[3] - r[1] for r in roots)
    fail["0x07 != 1 record pointing at 0x1B"] += len(layers) - len(grid_layers) != 1

    # 2. 0x08 grids
    def next_bid(sector):
        return by_sector.get(sector)

    grids = []                    # (name, layer, side, n, entries)
    runs = {}
    in_run = set()
    for l in grid_layers:
        side, n, ents, run = _grid(l.root, l.grid, p08, next_bid, fail)
        grids.append((f"L{l.index}", l, side, n, ents))
        runs[f"L{l.index}"] = len(run)
        in_run |= set(run)
    orphans = sorted(set(p08) - in_run)
    root = next(iter(roots))
    while orphans:                # unreferenced runs: must be complete grids themselves
        side, n, ents, run = _grid(root, orphans[0], p08, next_bid, fail)
        print(f"  0x08 run not in the directory: {orphans[0]:#x}, {len(run)} blocks, "
              f"{n}x{n} cells of {side}")
        grids.append((f"orphan {orphans[0]:#x}", None, side, n, ents))
        runs[f"orphan {orphans[0]:#x}"] = len(run)
        orphans = [b for b in orphans if b not in run]
    seen9 = Counter(e for *_, ents in grids for e in ents if e)
    fail["0x08 entry not a 0x09 block"] += sum(e not in p09 for e in seen9)
    fail["0x09 in two 0x08 entries"] += sum(c > 1 for c in seen9.values())
    fail["0x09 block not in any grid"] += len(set(p09) - set(seen9))
    live9 = {e for name, _, _, _, ents in grids if name.startswith("L") for e in ents if e}
    print(f"0x09: {len(live9)} reached from 0x07, {len(seen9) - len(live9)} only from an "
          f"unreferenced grid, {len(p09)} on disc")

    # 3.-6. 0x09 layout, grid order, bboxes
    cover = defaultdict(list)     # (grid, tile) -> [(x, y, side)] items
    nodes = defaultdict(set)      # (grid, tile) -> 0x09 blocks listing it
    tile_grid = {}
    layer_tiles = {}              # name -> (layer, tile type, tiles)
    for name, layer, side, n, ents in grids:
        tiles = set()
        cells = 0
        for k, e in enumerate(ents):
            if not e or e not in p09:
                continue
            cells += 1
            p = p09[e]
            ox, oy = root[0] + (k // n) * side, root[1] + (k % n) * side
            (o0, c0), (o1, c1) = struct.unpack_from(">HH", p, 8), struct.unpack_from(">HH", p, 12)
            node = parse_cell(p)
            s = node.item_side
            q, rem = divmod(side, s) if s else (0, 1)
            fail["0x09 S0 not at +0x14"] += o0 != 0x14
            fail["0x09 S1 not 4-aligned after S0"] += o1 != (o0 + 2 * c0 + 3) & ~3
            fail["0x09 gap after S0 not zero"] += any(p[o0 + 2 * c0:o1])
            fail["0x09 bytes after S1 not zero"] += any(p[o1 + 4 * c1:])
            fail["0x09 item side does not divide cell side"] += bool(rem)
            fail["0x09 count(S0) != (cell/item)^2"] += c0 != q * q
            nz = [v for v in node.pointers if v]
            fail["0x09 pointer not an S1 entry"] += any(
                not (o1 <= v < o1 + 4 * c1) or (v - o1) % 4 for v in nz)
            fail["0x09 S1 entry not pointed at"] += set(nz) != {o1 + 4 * i for i in range(c1)}
            fail["0x09 S1 duplicate"] += len(set(node.tiles)) != c1
            fail["0x09 S1 not in first-seen order"] += list(dict.fromkeys(nz)) != sorted(set(nz))
            g, smallest = 0, side
            for t in node.tiles:
                if t not in bbox:
                    fail["0x09 S1 entry not a tile block"] += 1
                    continue
                tiles.add(t)
                nodes[(name, t)].add(e)
                tile_grid.setdefault(t, set()).add(name)
                x0, y0, x1, y1 = bbox[t][1]
                w, h = min(x1, ox + side) - max(x0, ox), min(y1, oy + side) - max(y0, oy)
                g = gcd(gcd(g, gcd(w, h)), gcd(max(x0, ox) - ox, max(y0, oy) - oy))
                smallest = min(smallest, w, h)
            fail["0x09 item side != min clipped tile side"] += s != smallest
            fail["0x09 item side != gcd of clipped tile edges"] += s != g
            for j in range(c0):
                t = node.tile(j)
                if t is not None:
                    cover[(name, t)].append((ox + (j // q) * s, oy + (j % q) * s, s))
        types = Counter(bbox[t][0] for t in tiles)
        fail[f"{name}: more than one tile type"] += len(types) > 1
        if layer and len(types) == 1:
            layer_tiles[name] = (layer, next(iter(types)), tiles)
        print(f"  {name}: params {layer.params if layer else '-'}, {runs[name]} 0x08 blocks, "
              f"{n}x{n} cells of {side}, "
              f"{cells} non-empty, tiles {', '.join(f'{t:#04x} x {c}' for t, c in types.items())}")

    exact = 0
    for (name, t), items in cover.items():
        x0, y0, x1, y1 = bbox[t][1]
        ext = (min(i[0] for i in items), min(i[1] for i in items),
               max(i[0] + i[2] for i in items), max(i[1] + i[2] for i in items))
        disjoint = len({i[:2] for i in items}) == len(items)
        area = sum(i[2] * i[2] for i in items)
        ok = ext == (x0, y0, x1, y1) and disjoint and area == (x1 - x0) * (y1 - y0)
        fail["items of a tile != its bbox"] += not ok
        exact += ok
    live = {t for (name, t) in cover if name.startswith("L")}
    split = sum(len(v) > 1 for v in nodes.values())
    sides = {(root[2] - root[0]) >> k: k for k in range(32)}
    ks, side98, off98 = Counter(), 0, 0
    for t, (_, (x0, y0, x1, y1)) in bbox.items():
        w, h = x1 - x0, y1 - y0
        fail["tile side not root / 2^k"] += w not in sides or h not in sides
        fail["tile not 1:1 or 2:1"] += w not in (h, 2 * h) and h != 2 * w
        fail["tile corner not on its own grid from the root"] += bool(
            (x0 - root[0]) % w or (y0 - root[1]) % h)
        ks[sides.get(min(w, h))] += 1
        side98 += bool(w % 98_304 or h % 98_304)
        off98 += bool(w % 98_304 or h % 98_304 or x0 % 98_304 or y0 % 98_304)
    print(f"tile short side = root / 2^k: {dict(sorted(ks.items()))}; "
          f"side not a multiple of 98,304: {side98}; off the 98,304 grid from (0, 0): "
          f"{off98} / {len(bbox)}")
    fail["tile in two grids"] += sum(len(v) > 1 for v in tile_grid.values())
    fail["tile block not reached by any grid"] += len(set(bbox) - set(tile_grid))
    print(f"tiles: {len(bbox)} on disc, {len(live)} reached from 0x07, "
          f"{len(tile_grid) - len(live)} only from an unreferenced grid, "
          f"{exact} item sets == bbox, {split} listed in more than one 0x09")

    # 7. library lookup at every live tile's centre
    layer_of = {t: int(name[1:]) for (name, t) in cover if name.startswith("L")}
    miss = 0
    for t, L in layer_of.items():
        x0, y0, x1, y1 = bbox[t][1]
        lon, lat = to_wgs84((x0 + x1) // 2, (y0 + y1) // 2)
        miss += tiles_at(vol, L, lon, lat) != [t]
    fail["tiles_at(centre) != tile"] += miss
    print(f"lookup: {len(layer_of) - miss} / {len(layer_of)} tiles found at their centre")

    classes = {}
    if args.cf1_rust:
        classes = check_cf1_rust(args.iso, heads, bbox, fail, T)

    # 10. parameter 0 of the road layers = highest road class of their tiles
    for name, (layer, t, tiles) in sorted(layer_tiles.items()):
        if t not in ROAD_TYPES:
            continue
        if t == 0x00 and not args.cf1_rust:
            print(f"  {name} ({t:#04x}): road class check needs --cf1-rust, skipped")
            continue
        got = Counter()
        for k in tiles:
            if k not in classes and heads[k].comp != 1:
                classes[k] = max_road_class(vol.block(heads[k].sector).payload, t, T)
            if k in classes:
                got[classes[k]] += 1
            else:
                fail["road tile not decoded (class check)"] += 1
        top = max(got, default=-1)
        fail["road layer param 0 != highest road class of its tiles"] += top != layer.params[0]
        print(f"  {name} ({t:#04x}): param 0 = {layer.params[0]}, highest class per tile "
              f"{dict(sorted(got.items()))}")

    bad = {k: v for k, v in fail.items() if v}
    print("failures:", bad or "none")
    return 1 if bad else 0


def _grid(root, first, p08, next_bid, fail):
    """Claim 2 for the 0x08 run starting at `first`. Returns (cell side, N, entries, run)."""
    side, _ = parse_grid_block(p08[first])
    n, rem = divmod(root[2] - root[0], side)
    fail["0x08 cell side does not divide the root side"] += bool(rem)
    ents, run, cur = [], [], first
    while True:
        p = p08.get(cur)
        if p is None:
            fail["0x08 run broken (next block not 0x08)"] += 1
            break
        s, part = parse_grid_block(p)
        off, cnt = struct.unpack_from(">HH", p, 8)
        fail["0x08 S0 not at +0x10"] += off != 0x10
        fail["0x08 cell side differs within a run"] += s != side
        fail["0x08 bytes after S0 not zero"] += any(p[off + 4 * cnt:])
        ents += part
        run.append(cur)
        if len(ents) >= n * n:
            break
        cur = next_bid((cur >> 8) + (cur & 0xFF))
    fail["0x08 run entries != N^2"] += len(ents) != n * n
    return side, n, ents, run


if __name__ == "__main__":
    raise SystemExit(main())
