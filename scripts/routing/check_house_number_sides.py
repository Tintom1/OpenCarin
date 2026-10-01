"""Which side and which end of a segment do the 0x04 house numbers belong to? (roadmap A5)

A 0x04 record holds (f0, f2) for one side and (f1, f3) for the other (house_numbers.py).
Two things are not known from the disc alone:

  ORIENTATION  is f0 (f1) the number at the segment's start node and f2 (f3) at its end node?
  SIDE         is (f0, f2) on the left or the right of the start -> end direction?

Test against OpenStreetMap addresses (nodes and areas with addr:street + addr:housenumber):
each OSM address is matched to the CARiN segments of the same street name (accent- and
case-folded) whose number range holds its number on a side of that parity, projected on the
segment's polyline (at most --max-dist metres away), which gives

  t     position along the segment, 0 = start node, 1 = end node
  side  +1 left / -1 right of the start -> end direction

ORIENTATION: for a side (a, b) with a != b the stored numbers predict n(t) = a + (b - a) t. The
script reports, over every (segment, side) with at least --min-points matched addresses and a
spread of t of at least 0.3, whether the fitted slope of n against t has the sign of (b - a).
SIDE: for segments with the odd/even scheme (f4 = 2) the side is fixed by the parity: it
counts how many addresses of side A (f0, f2) and of side B (f1, f3) fall on the left / right.

Usage:
    python scripts/routing/check_house_number_sides.py --osm osm_modugno.json \
        --bbox 16.74 41.06 16.83 41.12

OSM data: Overpass `[out:json];nwr["addr:housenumber"]["addr:street"](S,W,N,E);out center tags;`
(the file holds the response; `elements[].center` or `lat`/`lon` give the position).
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import unicodedata
import zlib
from collections import Counter, defaultdict
from math import cos, radians
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser.geometry import road_segments
from carin.parser.house_numbers import NONE, SCHEME_MIXED, segment_house_numbers, tile_block_id
from carin.parser.iso import CarinVolume, IsoImage
from carin.parser.spatial import tiles_at

ISO = "dataset/NAV_DB_21708.ISO"
M_LAT = 111_320.0


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.casefold().replace("’", "'"))
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


def number_of(tag: str):
    """Leading integer of an OSM housenumber, None for ranges, lists and plain text."""
    m = re.fullmatch(r"(\d{1,4})\s*[a-zA-Z]?", tag.strip())
    return int(m.group(1)) if m else None


def load_osm(path: str):
    out = defaultdict(list)
    for el in json.load(open(path))["elements"]:
        t = el.get("tags", {})
        n = number_of(t.get("addr:housenumber", ""))
        pos = el.get("center") or el
        if n is None or "lat" not in pos:
            continue
        out[fold(t["addr:street"])].append((n, pos["lon"], pos["lat"]))
    return out


def project(coords, lon, lat):
    """(distance m, t along the polyline 0..1, side +1 left / -1 right) of a point."""
    k = cos(radians(lat))
    px, py = lon * k * M_LAT, lat * M_LAT
    pts = [(x * k * M_LAT, y * M_LAT) for x, y in coords]
    lens = [((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 for (x0, y0), (x1, y1) in zip(pts, pts[1:])]
    total = sum(lens)
    if total == 0:
        return None
    best, run = None, 0.0
    for (x0, y0), (x1, y1), ln in zip(pts, pts[1:], lens):
        if ln == 0:
            continue
        f = max(0.0, min(1.0, ((px - x0) * (x1 - x0) + (py - y0) * (y1 - y0)) / (ln * ln)))
        qx, qy = x0 + f * (x1 - x0), y0 + f * (y1 - y0)
        d = ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5
        if best is None or d < best[0]:
            cross = (x1 - x0) * (py - y0) - (y1 - y0) * (px - x0)
            best = (d, (run + f * ln) / total, 1 if cross > 0 else -1)
        run += ln
    return best


def slope(points):
    """Least-squares slope of n against t, and the spread of t."""
    ts = [t for t, _ in points]
    ns = [n for _, n in points]
    mt, mn = sum(ts) / len(ts), sum(ns) / len(ns)
    var = sum((t - mt) ** 2 for t in ts)
    if var == 0:
        return None, 0.0
    return sum((t - mt) * (n - mn) for t, n in points) / var, max(ts) - min(ts)


def covers(side, n: int, mixed: bool) -> bool:
    if side is None:
        return False
    lo, hi = min(side), max(side)
    return lo <= n <= hi and (mixed or n % 2 == lo % 2)


def road_layer(vol: CarinVolume, lon: float, lat: float) -> int:
    """Index of the directory layer whose tiles are 0x00 street-level tiles."""
    for layer in range(12):
        try:
            tiles = tiles_at(vol, layer, lon, lat)
        except Exception:
            continue
        if tiles and vol.block(tiles[0] >> 8).type == 0x00:
            return layer
    raise SystemExit("no 0x00 layer at the bbox centre")


def house_number_blocks(vol: CarinVolume, wanted: set):
    """{tile BLOCK_ID: decoded 0x04 payload} for the wanted tiles (one scan of the 0x04 blocks)."""
    found = {}
    for b in vol.walk():
        if b.type != 0x04:
            continue
        head = vol.read_sectors(b.sector, 1)
        if head[6] == 0:
            tile = tile_block_id(head)
        elif head[6] == 2:
            raw = vol.read_sectors(b.sector, b.length)
            tile = tile_block_id(raw[:8] + zlib.decompress(raw[8:]))
        else:
            continue
        if tile in wanted:
            found[tile] = vol.block(b.sector).payload
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iso", default=ISO)
    ap.add_argument("--osm", required=True)
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("W", "S", "E", "N"))
    ap.add_argument("--max-dist", type=float, default=25.0, help="metres from address to segment")
    ap.add_argument("--min-points", type=int, default=3)
    args = ap.parse_args()

    vol = CarinVolume(IsoImage(args.iso))
    vol.calibrate()
    w, s, e, n = args.bbox
    layer = road_layer(vol, (w + e) / 2, (s + n) / 2)

    tiles = set()
    step = 0.002
    lon = w
    while lon <= e:
        lat = s
        while lat <= n:
            tiles.update(tiles_at(vol, layer, lon, lat))
            lat += step
        lon += step
    print(f"layer {layer}: {len(tiles)} tiles over the bbox")
    hn = house_number_blocks(vol, tiles)
    osm = load_osm(args.osm)
    print(f"0x04 blocks: {len(hn)}   OSM streets with numbers: {len(osm)}")

    # every numbered segment of the bbox, by street name
    by_name = defaultdict(list)
    stat = Counter()
    for tile in sorted(tiles):
        if tile not in hn:
            stat["tile without 0x04"] += 1
            continue
        data = vol.block(tile >> 8).payload
        recs = segment_house_numbers(hn[tile])
        for seg in road_segments(data, vol.layout):
            r = recs[seg["index"]] if seg["index"] < len(recs) else None
            if r is None or not seg["name"] or r["scheme"] == 0:
                continue
            by_name[fold(seg["name"])].append((tile, seg, r))

    # each OSM address goes to the NEAREST segment of its street, if within --max-dist
    matched = defaultdict(list)             # (tile, segment index) -> [(t, n, side)]
    for name, adds in osm.items():
        segs = by_name.get(name)
        if not segs:
            stat["street not on the disc"] += len(adds)
            continue
        for num, alon, alat in adds:
            best = None
            for tile, seg, r in segs:
                pr = project(seg["coords"], alon, alat)
                if pr and (best is None or pr[0] < best[0][0]):
                    best = (pr, tile, seg, r)
            if best is None or best[0][0] > args.max_dist:
                stat["address too far from its street"] += 1
                continue
            (d, t, side), tile, seg, r = best
            matched[(tile, seg["index"])].append((t, num, side, r))

    cross = Counter()                       # side A: (majority side, orientation) per segment
    side_tally = Counter()                  # per segment: side A / B -> majority left / right
    orient = Counter()
    examples = []
    for (tile, idx), pts in matched.items():
        r = pts[0][3]
        mixed = r["scheme"] == SCHEME_MIXED
        for name, rng in (("A", r["side_a"]), ("B", r["side_b"])):
            sel = [(t, num, side) for t, num, side, _ in pts if covers(rng, num, mixed)]
            if not sel:
                continue
            stat["address on a side's range"] += len(sel)
            maj = None
            if r["scheme"] == 2:
                left = sum(1 for _, _, sd in sel if sd > 0)
                right = len(sel) - left
                if left != right:
                    maj = "left" if left > right else "right"
                    side_tally[(name, "left" if left > right else "right",
                                "clean" if min(left, right) == 0 else "mixed")] += 1
            if len(sel) >= args.min_points and rng[0] != rng[1]:
                sl, spread = slope([(t, num) for t, num, _ in sel])
                if sl is None or spread < 0.3:
                    stat["side too short to test"] += 1
                    continue
                ok = (sl > 0) == (rng[1] > rng[0])
                orient["second at the end" if ok else "second at the start"] += 1
                if maj and name == "A":
                    cross[(maj, "second at the end" if ok else "second at the start")] += 1
                if len(examples) < 8:
                    examples.append((tile, idx, name, rng, len(sel), round(sl, 1)))
    print("\nstats:", dict(stat))
    print("\nORIENTATION (side tuple (first, second) = (f0, f2) or (f1, f3)):")
    print("  ", dict(orient))
    print("\nSIDE (odd/even scheme, per segment: where the majority of the side's addresses lie):")
    for k in sorted(side_tally):
        print("  ", k, side_tally[k])
    print("\nside A: majority side x orientation (segments testable on both):")
    for k in sorted(cross):
        print("  ", k, cross[k])
    print("\nexamples (tile, segment, side, stored range, points, fitted dn/dt):")
    for x in examples:
        print("  ", x)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
