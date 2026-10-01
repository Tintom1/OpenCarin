"""Look up a street address in a CARiN DVD and print where it is.

    uv run python examples/03_address_lookup/lookup_address.py \
        --country italia --city modugno --street "via roma" --number 114

The path an address search takes through the database, all of it read with the
code in `carin/parser` (docs/carindb/01-architecture.md §4.4, 03-road-network.md §6.3-6.4):

  0x0A  country table             country name  -> root of its city trie
  0x0D  city trie (letter trie)   city name     -> 0x0C city record
  0x0C  city record               city          -> root of its road-name trie (0x0F)
  0x0F  road trie                 street name   -> 0x0E street record
  0x0E  street-name directory     S0 -> S1 -> S2 link: tile (0x00) + run of S4 segments
                                  + the even / odd house-number envelope
  0x00  street-level tile         the segments' geometry (WGS84 polyline)
  0x04  house numbers             one record per S4 segment: the numbers on its two sides

Position of the number: linear along the segment polyline between the numbers stored for it,
first number at the start node, then moved --offset metres to the side of the number: side A of
the record is the left and side B the right of the start -> end direction (checked against OSM,
03-road-network.md §6.4). The point on the centre line and the segment's end points are printed too.
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser.geometry import road_segments
from carin.parser.house_numbers import NONE, SCHEME_MIXED, segment_house_numbers, tile_block_id
from carin.parser.iso import CarinVolume, IsoImage

TYPE_TILE, TYPE_HOUSE_NUMBERS = 0x00, 0x04
ALIAS = 0x1000                       # flag of a word-reordered alias record of a street


def cstr(d: bytes, off: int) -> str:
    return d[off:d.index(0, off)].decode("latin-1")


def trie_leaf(vol: CarinVolume, root: tuple, name: str):
    """Walk a 0x0D / 0x0F letter trie (01-architecture.md §4.4.1) to the leaf of `name`.

    Records are `u32 BLOCK_ID | u8 letter | u8 leaf | u16 offset | u16 count | u16 flags`.
    Returns (BLOCK_ID, offset, count) of the leaf's name records, or None.
    """
    bid, off, cnt = root
    name = name.lower()
    depth = 0
    while True:
        d = vol.block(bid >> 8).payload
        want = ord(name[depth]) if depth < len(name) else ord("@")
        for i in range(cnt):
            tb, letter, leaf, o2, c2, _ = struct.unpack_from(">IBBHHH", d, off + 12 * i)
            if letter == want:
                break
        else:
            return None
        if leaf:
            return tb, o2, c2
        bid, off, cnt = tb, o2, c2
        depth += 1


def find_city(vol: CarinVolume, country: str, city: str):
    """(0x0C block payload, city S1 offset) for `country` / `city`, over every 0x0A block."""
    for sector in (b.sector for b in vol.walk() if b.type == 0x0A):
        blk = vol.block(sector)
        d = blk.payload
        (o0, n0), (o1, _n1) = blk.sections(2)
        for i in range(n0):
            name_off, _lang, rec_off = struct.unpack_from(">HHI", d, o0 + 8 * i)
            if cstr(d, name_off) != country.lower():
                continue
            root = struct.unpack_from(">IHH", d, rec_off)
            leaf = trie_leaf(vol, root, city)
            if leaf is None:
                continue
            tb, o2, c2 = leaf
            cd = vol.block(tb >> 8).payload
            for k in range(c2):
                n_off, _flags, town_off, s1 = struct.unpack_from(">HHHH", cd, o2 + 8 * k)
                if cstr(cd, n_off) == city.lower():
                    town = cstr(cd, town_off) if town_off else None
                    return cd, s1, town
    return None


def find_street(vol: CarinVolume, road_root: tuple, street: str):
    """Yield (0x0E payload, S1 record offset) of every record named `street`."""
    leaf = trie_leaf(vol, road_root, street)
    if leaf is None:
        return
    tb, o2, c2 = leaf
    d = vol.block(tb >> 8).payload
    for i in range(c2):
        name_off, flags, _loc, s1 = struct.unpack_from(">HHHH", d, o2 + 8 * i)
        if cstr(d, name_off) == street.lower() and not flags & ALIAS:
            yield d, s1


def s2_links(d: bytes, s1: int):
    """S1 record -> its S2 links (03-road-network.md §6.3.1): one per tile run."""
    s2_off, span = struct.unpack_from(">HB", d, s1)
    for k in range(span):
        b = s2_off + 24 * k
        ev = struct.unpack_from(">2H", d, b + 8)
        od = struct.unpack_from(">2H", d, b + 12)
        bid, s4_off, s4_cnt = struct.unpack_from(">IHH", d, b + 16)
        yield {"even": None if ev == (NONE, NONE) else ev,
               "odd": None if od == (NONE, NONE) else od,
               "tile": bid, "s4_off": s4_off, "s4_cnt": s4_cnt}


def find_house_number_block(vol: CarinVolume, tile: int):
    """Payload of the 0x04 block of a tile (one per tile, +0x0C names it): a scan of the 0x04 blocks."""
    for b in vol.walk():
        if b.type != TYPE_HOUSE_NUMBERS:
            continue
        head = vol.read_sectors(b.sector, 1)
        if head[6] == 0:
            if tile_block_id(head) == tile:
                return vol.block(b.sector).payload
        else:                                     # zlib: decompress to read +0x0C
            raw = vol.read_sectors(b.sector, b.length)
            if tile_block_id(raw[:8] + zlib.decompress(raw[8:])) == tile:
                return vol.block(b.sector).payload
    return None


def covers(side, number: int, mixed: bool) -> bool:
    if side is None:
        return False
    lo, hi = min(side), max(side)
    return lo <= number <= hi and (mixed or number % 2 == lo % 2)


def along(coords, t: float):
    """(lon, lat, east, north) at fraction t (0..1) of the polyline's length, flat-earth distances.

    (east, north) is the unit direction of the polyline there, in metres.
    """
    from math import cos, hypot, radians
    k = cos(radians(coords[0][1]))
    dist = [0.0]
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        dist.append(dist[-1] + hypot((x1 - x0) * k, y1 - y0))
    target = t * dist[-1]
    for i in range(1, len(coords)):
        if target <= dist[i] or i == len(coords) - 1:
            f = 0 if dist[i] == dist[i - 1] else (target - dist[i - 1]) / (dist[i] - dist[i - 1])
            (x0, y0), (x1, y1) = coords[i - 1], coords[i]
            dx, dy = (x1 - x0) * k, y1 - y0
            n = hypot(dx, dy) or 1.0
            return x0 + f * (x1 - x0), y0 + f * (y1 - y0), dx / n, dy / n


def offset(lon: float, lat: float, east: float, north: float, side: int, metres: float):
    """Move a point `metres` to the left (side +1) or right (-1) of the direction (east, north)."""
    from math import cos, radians
    m_lat = 111_320.0
    return (lon + side * (-north) * metres / (m_lat * cos(radians(lat))),
            lat + side * east * metres / m_lat)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iso", default="dataset/NAV_DB_21708.ISO")
    ap.add_argument("--country", default="italia")
    ap.add_argument("--city", default="modugno")
    ap.add_argument("--street", default="via roma")
    ap.add_argument("--number", type=int, default=114)
    ap.add_argument("--offset", type=float, default=12.0,
                    help="metres from the road centre line to the side of the number")
    args = ap.parse_args()

    vol = CarinVolume(IsoImage(args.iso))
    vol.calibrate()

    found = find_city(vol, args.country, args.city)
    if found is None:
        print(f"city {args.city!r} not found in {args.country!r}")
        return 1
    cd, s1, town = found
    print(f"city      : {args.city} (post town: {town})   [0x0A -> 0x0D -> 0x0C]")
    road_root = struct.unpack_from(">IHH", cd, s1)          # 0x0C S1 +0x00: root of the 0x0F trie

    hits = 0
    for d, s1_rec in find_street(vol, road_root, args.street):
        for link in s2_links(d, s1_rec):
            ev, od = link["even"], link["odd"]
            print(f"street    : {args.street}   [0x0F -> 0x0E]  numbers even {ev}  odd {od}  "
                  f"tile {link['tile']:#x}, {link['s4_cnt']} segments")
            if not (covers(ev, args.number, False) or covers(od, args.number, False)):
                print(f"            {args.number} is outside this run's numbers")
                continue
            tile = vol.block(link["tile"] >> 8)
            data = tile.payload
            e4_off = struct.unpack_from(">H", data, 8 + 16)[0]
            first = (link["s4_off"] - e4_off) // vol.layout[0x08]
            segs = {s["index"]: s for s in road_segments(data, vol.layout)}

            hn = find_house_number_block(vol, link["tile"])
            if hn is None:
                print("            no 0x04 block for the tile")
                continue
            recs = segment_house_numbers(hn)
            for r in recs[first:first + link["s4_cnt"]]:
                seg = segs.get(r["index"])
                if seg is None:
                    continue
                mixed = r["scheme"] == SCHEME_MIXED
                for label, side, left in (("A, left", r["side_a"], 1), ("B, right", r["side_b"], -1)):
                    if not covers(side, args.number, mixed):
                        continue
                    lo, hi = side
                    t = 0.5 if lo == hi else (args.number - lo) / (hi - lo)
                    lon, lat, east, north = along(seg["coords"], min(max(t, 0.0), 1.0))
                    olon, olat = offset(lon, lat, east, north, left, args.offset)
                    a, z = seg["coords"][0], seg["coords"][-1]
                    hits += 1
                    print(f"\nRESULT    : n. {args.number} on segment {r['index']} of tile {link['tile']:#x}, "
                          f"numbers {lo}..{hi} (scheme {r['scheme']}, side {label} of the start -> end direction)")
                    print(f"  on road : {lat:.6f}, {lon:.6f}")
                    print(f"  position: {olat:.6f}, {olon:.6f}   ({args.offset:g} m to the {label.split(', ')[1]})")
                    print(f"  segment : {a[1]:.6f}, {a[0]:.6f}  ->  {z[1]:.6f}, {z[0]:.6f}"
                          f"  ({len(seg['coords'])} points, class {seg['display_class']})")
                    print(f"  map     : https://www.openstreetmap.org/?mlat={olat:.6f}&mlon={olon:.6f}#map=19/{olat:.6f}/{olon:.6f}")
    if not hits:
        print("no segment found for that number")
    return 0 if hits else 2


if __name__ == "__main__":
    raise SystemExit(main())
