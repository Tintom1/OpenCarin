"""Step 4: replace the old crossing by the OSM roundabout in tile 0x4c184f18 of the disc copy.

The edit keeps every section size, so no offset moves and nothing that points into the tile
(`0x0E` runs, `0x04`, `0x0C`, the spatial index) changes. The eight records of the old crossing are
reused (03-road-network.md §6.7). Logical travel directions of the new layout (a ring node is
`Rw` west, `Rne` north-east, `Rse` south-east; the ring runs counter-clockwise, as for right-hand traffic):

    41  B   <-> Rw     Via Roma, W arm, two-way        43  Rw  ->  Rse   ring
    38  Rne <-> A      NE arm, two-way                 17  Rse ->  Rne   ring
    45  E   ->  Rse    Viale della Repubblica, inbound 44  Rne ->  Rw    ring
    46  Rse ->  F      Viale della Repubblica, outbound 18  B   ->  Rse   slip lane south of the ring

The three internal nodes of the old crossing (S5 slots H, D, C) become the three ring nodes and move
onto the OSM ring. The two ordering rules the unit needs are kept (§6.7, "Writing road tiles"): the
S5 nodes stay (x, y)-sorted inside their level group, so the roles are assigned to the slots in
(x, y) order; and a segment's start node is the end with the lower (x, y), so a record whose travel
direction runs the other way is stored reversed (shape reversed, one-way bits swapped).
Ring segments get junction type 6, no street name and the shape points of the ring between their
nodes. Lengths and bearings of the eight records are recomputed, the node cycles (clockwise by
bearing, from the smallest) are rebuilt for the seven nodes, and the two forbidden turns (S10)
that would now close a ring exit are neutralised.

    uv run python examples/04_update_modugno_roundabout/04_patch_tile.py [--write]

Without --write nothing is written to the disc copy. Everything is checked before and after.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import defaultdict
from math import atan2, cos, hypot, pi, radians
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carin.parser import cf1
from carin.parser.cf1.constants import T_REC_S10, T_REC_S3, T_REC_S4, T_TAIL_S4
from carin.parser.geometry import VERTEX_SHIFT, _sections, road_segments, tile_frame
from carin.parser.iso import CarinVolume, IsoImage, to_carin, to_wgs84
from common import CENTER, DATA, ISO_COPY, M_LAT, length_m, to_m

TILE = 0x4C184F18
RING_WAYS = (1326505905, 1383238947, 1383238946)         # OSM ways of the roundabout
SLOTS = {"H": 16528, "D": 16536, "C": 16544}               # S5 slots of the old crossing's internal nodes
OUTER = {"A": 16552, "B": 16520, "E": 16568, "F": 16560}    # outer ends: unchanged
# record -> (travel from, travel to, one-way?): ring nodes by role Rw / Rne / Rse
TRAVEL = {41: ("B", "Rw", False), 38: ("Rne", "A", False), 43: ("Rw", "Rse", True),
          17: ("Rse", "Rne", True), 44: ("Rne", "Rw", True), 45: ("E", "Rse", True),
          46: ("Rse", "F", True), 18: ("B", "Rse", True)}
RING_RECS = (43, 17, 44)
NEW_ENDS = {}                                               # filled by patch(): record -> (start, end) node offsets
REPORT = []


def log(msg: str) -> None:
    print(msg)
    REPORT.append(msg)


class Tile:
    """Field access on the decoded bytes of one 0x00 tile."""

    def __init__(self, data: bytes, layout: dict):
        self.d = bytearray(data)
        self.layout = layout
        secs = _sections(self.d, layout)
        self.s4, self.n4 = secs[4]
        self.s5, self.n5 = secs[5]
        self.s7, self.n7 = secs[7]
        self.s10, self.n10 = secs[10]
        self.rec = layout[T_REC_S4]
        self.tail = layout[T_TAIL_S4]
        self.frame = tile_frame(bytes(self.d), layout)

    def u16(self, o): return struct.unpack_from(">H", self.d, o)[0]
    def put16(self, o, v): struct.pack_into(">H", self.d, o, v & 0xFFFF)
    def r(self, i): return self.s4 + self.rec * i

    def local(self, lon, lat):
        x, y = to_carin(lon, lat)
        return (round((x - self.frame.x0) / (1 << VERTEX_SHIFT)),
                round((y - self.frame.y0) / (1 << VERTEX_SHIFT)))

    def lonlat(self, u, v): return self.frame.to_wgs84(u, v)
    def node_xy(self, node): return struct.unpack_from(">HH", self.d, node)
    def node_ll(self, node): return self.lonlat(*self.node_xy(node))

    def s7_ptrs(self):
        return [self.u16(self.r(i) + 4) for i in range(self.n4)] + [self.s7 + 6 * self.n7]

    def poly(self, i):
        """lon/lat polyline of record i: start node, S7 points, end node."""
        p = self.s7_ptrs()
        pts = [self.node_ll(self.u16(self.r(i)))]
        pts += [self.lonlat(*struct.unpack_from(">HH", self.d, q)) for q in range(p[i], p[i + 1], 6)]
        pts.append(self.node_ll(self.u16(self.r(i) + 2)))
        return pts


def bearing(a, b) -> int:
    """Compass bearing from a to b (lon, lat) in 1/256 turn, 0 = north, clockwise."""
    east, north = (b[0] - a[0]) * cos(radians(a[1])), b[1] - a[1]
    return round(atan2(east, north) / (2 * pi) * 256) % 256


def cycles_for(t: Tile, node: int):
    """Members (record, 's'|'e') at a node, clockwise by bearing, starting at the smallest."""
    mem = []
    for i in range(t.n4):
        if t.u16(t.r(i)) == node:
            mem.append((t.d[t.r(i) + 0x0E], i, "s"))
        if t.u16(t.r(i) + 2) == node:
            mem.append((t.d[t.r(i) + 0x0F], i, "e"))
    return [(i, s) for _, i, s in sorted(mem)]


def write_cycle(t: Tile, node: int) -> None:
    cyc = cycles_for(t, node)
    if not cyc:
        return
    t.put16(node + 4, t.r(cyc[0][0]))
    for k, (i, side) in enumerate(cyc):
        nxt = cyc[(k + 1) % len(cyc)]
        t.put16(t.r(i) + (6 if side == "s" else 8), t.r(nxt[0]))


def check_cycles(t: Tile, nodes, label: str) -> int:
    """Stored node cycles == rebuilt ones, for the given nodes; returns the number of mismatches."""
    bad = 0
    for node in nodes:
        cyc = cycles_for(t, node)
        first = t.u16(node + 4)
        got, cur = [], first
        for _ in range(len(cyc) + 1):
            i = (cur - t.s4) // t.rec
            side = "s" if t.u16(t.r(i)) == node else "e"
            got.append((i, side))
            cur = t.u16(t.r(i) + (6 if side == "s" else 8))
            if cur == first:
                break
        if got != cyc:
            bad += 1
            log(f"  {label}: node {node} stored {got} != rebuilt {cyc}")
    return bad


def ring_polygon():
    """The OSM roundabout as one closed counter-clockwise ring of (lon, lat)."""
    ways = {e["id"]: e for e in json.load(open(DATA / "osm_ways.json"))["elements"]}
    pts = []
    for wid in RING_WAYS:
        g = [(p["lon"], p["lat"]) for p in ways[wid]["geometry"]]
        pts += g if not pts or pts[-1] != g[0] else g[1:]
    if pts[0] == pts[-1]:
        pts.pop()
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    return pts if area > 0 else pts[::-1]


def arc(ring, i, j):
    """Ring vertices from index i to j (counter-clockwise, both included)."""
    out, k = [ring[i]], i
    while k != j:
        k = (k + 1) % len(ring)
        out.append(ring[k])
    return out


def resample(poly, k):
    """k interior points at equal arc-length fractions of a lon/lat polyline."""
    pts = [to_m(*p) for p in poly]
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + hypot(b[0] - a[0], b[1] - a[1]))
    out = []
    for n in range(1, k + 1):
        target = cum[-1] * n / (k + 1)
        j = max(x for x in range(len(cum)) if cum[x] <= target)
        j = min(j, len(poly) - 2)
        f = (target - cum[j]) / ((cum[j + 1] - cum[j]) or 1)
        out.append((poly[j][0] + f * (poly[j + 1][0] - poly[j][0]),
                    poly[j][1] + f * (poly[j + 1][1] - poly[j][1])))
    return out


def seg_length(poly) -> int:
    return round(length_m(poly))


def patch(t: Tile) -> dict:
    ring = ring_polygon()
    nearest = lambda p: min(range(len(ring)), key=lambda i: hypot(*(a - b for a, b in zip(to_m(*ring[i]), to_m(*p)))))
    old_ll = {n: t.node_ll(o) for n, o in {**SLOTS, **OUTER}.items()}
    mid_ef = ((old_ll["E"][0] + old_ll["F"][0]) / 2, (old_ll["E"][1] + old_ll["F"][1]) / 2)
    idx = {"Rw": nearest(old_ll["B"]), "Rne": nearest(old_ll["A"]), "Rse": nearest(mid_ef)}
    order = [(idx[r] - idx["Rw"]) % len(ring) for r in ("Rw", "Rse", "Rne")]      # counter-clockwise Rw -> Rse -> Rne
    assert order == sorted(order) and len(set(order)) == 3, f"ring nodes out of order: {order}"
    log(f"ring: {len(ring)} OSM vertices; Rw = vertex {idx['Rw']}, Rse = {idx['Rse']}, Rne = {idx['Rne']}")

    # roles -> S5 slots, in (x, y) order, so the nodes stay sorted inside their level group
    local = {r: t.local(*ring[i]) for r, i in idx.items()}
    assert len(set(local.values())) == 3, "two ring nodes fall on the same grid point"
    slot = dict(zip(sorted(local, key=lambda r: local[r]), sorted(SLOTS.values())))
    node = {**{r: slot[r] for r in slot}, **OUTER}
    for r, off in slot.items():
        struct.pack_into(">HH", t.d, off, *local[r])
        log(f"{r}: S5 slot {off} {tuple(round(c, 6) for c in old_ll[[k for k, v in SLOTS.items() if v == off][0]])} "
            f"-> {tuple(round(c, 6) for c in t.node_ll(off))}")
    ptrs = t.s7_ptrs()
    key = lambda off: t.node_xy(off)

    for i, (a, b, oneway) in TRAVEL.items():
        na, nb = node[a], node[b]
        fwd = key(na) < key(nb)                                      # travel a -> b is the stored direction
        start, end = (na, nb) if fwd else (nb, na)
        assert key(start) != key(end)
        NEW_ENDS[i] = (start, end)
        t.put16(t.r(i), start)
        t.put16(t.r(i) + 2, end)
        b0b = t.d[t.r(i) + 0x0B]
        if i in RING_RECS:
            k = (ptrs[i + 1] - ptrs[i]) // 6
            ra, rb = {"Rw": "Rw", "Rse": "Rse", "Rne": "Rne"}[a], {"Rw": "Rw", "Rse": "Rse", "Rne": "Rne"}[b]
            pts = resample(arc(ring, idx[ra], idx[rb]), k)
            if not fwd:
                pts = pts[::-1]                                      # shape runs from the stored start
            for n, p in enumerate(pts):
                u, v = t.local(*p)
                struct.pack_into(">HHB", t.d, ptrs[i] + 6 * n, u, v, 0)
            # junction 6 (keep the high nibble), class 2, form single carriageway, no street name
            t.d[t.r(i) + 0x11] = (t.d[t.r(i) + 0x11] & 0xF0) | 0x06
            t.d[t.r(i) + 0x10] = 0x02
            b0b = (b0b & 0xC0) | 0x0C
            t.put16(t.r(i) + t.tail, t.u16(t.r(17) + t.tail))
        if i == 18:
            t.d[t.r(18) + 0x11] &= 0xF0                              # an ordinary slip lane now, no junction connector
        # direction restriction bits 4-5: 0 two-way, 1 along the stored direction, 2 against it
        t.d[t.r(i) + 0x0B] = (b0b & 0xCF) | ((0x10 if fwd else 0x20) if oneway else 0)

    # the slip lane runs south of the ring: two shape points between B and Rse
    (u0, v0), (u1, v1) = t.node_xy(node["B"]), t.node_xy(node["Rse"])
    for n, f in enumerate((0.35, 0.7)):
        struct.pack_into(">HHB", t.d, ptrs[18] + 6 * n, round(u0 + (u1 - u0) * f),
                         round(v0 + (v1 - v0) * f - 8 * (1 - abs(2 * f - 1))), 0)

    # lengths and bearings of the eight records
    for i in TRAVEL:
        p = t.poly(i)
        t.put16(t.r(i) + 0x0C, seg_length(p))
        t.d[t.r(i) + 0x0E] = bearing(p[0], p[1])
        t.d[t.r(i) + 0x0F] = bearing(p[-1], p[-2])
    for n in node.values():
        write_cycle(t, n)
    # forbidden turns (S10) that would close a ring exit: aim them at the segment itself
    p10 = [t.u16(t.r(i) + 0x12) for i in range(t.n4)] + [t.s10 + t.n10 * t.layout[T_REC_S10]]
    neut = []
    for src, tgt in ((17, 38), (43, 38)):
        for x in range(p10[src], p10[src + 1], t.layout[T_REC_S10]):
            if struct.unpack_from(">IH", t.d, x) == (TILE, t.r(tgt)):
                struct.pack_into(">H", t.d, x + 4, t.r(src))
                neut.append((src, tgt, x))
    log(f"S10 entries neutralised: {neut}")
    return {"ring": ring}


def check(t: Tile, label: str):
    """Structural checks on a tile: the two ordering rules, the node cycles, the forbidden turns."""
    problems = 0
    nodes = [t.s5 + 8 * k for k in range(t.n5)]
    problems += check_cycles(t, [n for n in nodes if cycles_for(t, n)], label)
    for i in range(t.n4):                                           # rule: the start node has the lower (x, y)
        a, b = t.u16(t.r(i)), t.u16(t.r(i) + 2)
        if not t.node_xy(a) < t.node_xy(b):
            problems += 1
            log(f"  {label}: record {i} starts at {t.node_xy(a)}, ends at {t.node_xy(b)}")
    s3, n3 = _sections(bytes(t.d), t.layout)[3]
    rec3 = t.layout[T_REC_S3]
    firsts = [struct.unpack_from(">HH", t.d, s3 + rec3 * k)[1] for k in range(n3)] + [t.s5 + 8 * t.n5]
    for lo, hi in zip(firsts, firsts[1:]):                          # rule: S5 sorted by (x, y) inside each level group
        xy = [t.node_xy(o) for o in range(lo, hi, 8)]
        if xy != sorted(xy):
            problems += 1
            log(f"  {label}: S5 nodes {lo}..{hi} are not (x, y)-sorted")
    for i in range(t.n4):                                           # every S10 entry names a segment sharing a node
        a = t.u16(t.r(i) + 0x12)
        b = t.u16(t.r(i + 1) + 0x12) if i + 1 < t.n4 else t.s10 + t.n10 * t.layout[T_REC_S10]
        for x in range(a, b, t.layout[T_REC_S10]):
            tid, off = struct.unpack_from(">IH", t.d, x)
            if tid == TILE:
                j = (off - t.s4) // t.rec
                if not {t.u16(t.r(i)), t.u16(t.r(i) + 2)} & {t.u16(t.r(j)), t.u16(t.r(j) + 2)}:
                    problems += 1
                    log(f"  {label}: S10 entry of {i} targets {j}, no shared node")
    return problems


def write_block(vol: CarinVolume, sector: int, raw: bytes) -> None:
    idx, local = divmod(sector, 0x400000)
    off = vol.parts[idx].offset + local * vol.sector_size
    with open(ISO_COPY, "r+b") as f:
        f.seek(off)
        f.write(raw)


def svg(t_before: Tile, t_after: Tile, osm_polys, path: Path) -> None:
    scale, half = 4.0, 75
    def pt(ll):
        x, y = to_m(*ll)
        return f"{(x + half) * scale:.1f},{(half - y) * scale:.1f}"
    panels = []
    for k, (t, title) in enumerate(((t_before, "disc 2016 (before)"), (t_after, "disc patched (after)"))):
        g = [f'<text x="6" y="16" font-size="13" font-family="sans-serif">{title}</text>']
        for o in osm_polys:
            g.append(f'<polyline fill="none" stroke="#9bb7ff" stroke-width="5" points="{" ".join(map(pt, o))}"/>')
        for i in range(t.n4):
            p = t.poly(i)
            if min(hypot(*to_m(*c)) for c in p) > 2 * half:
                continue
            ring = (t.d[t.r(i) + 0x11] & 0x0F) == 6
            col = "#d62728" if ring else ("#333" if i in NEW_ENDS else "#888")
            g.append(f'<polyline fill="none" stroke="{col}" stroke-width="{3 if i in NEW_ENDS else 2}" '
                     f'points="{" ".join(map(pt, p))}"/>')
            if i in NEW_ENDS:
                mx, my = pt(p[len(p) // 2]).split(",")
                g.append(f'<text x="{mx}" y="{my}" font-size="10" font-family="sans-serif" fill="#000">{i}</text>')
        panels.append(f'<g transform="translate(0,{k * (2 * half * scale + 20)})"><rect width="{2 * half * scale}" '
                      f'height="{2 * half * scale}" fill="#fafafa" stroke="#ccc"/>{"".join(g)}</g>')
    h = 2 * (2 * half * scale) + 20
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{2 * half * scale}" height="{h}">{"".join(panels)}'
                    f'</svg>')
    for name, panel in (("before", panels[0]), ("after", panels[1])):      # one file per panel too
        body = panel.split(">", 1)[1].rsplit("</g>", 1)[0]
        path.with_name(f"{name}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{2 * half * scale}" height="{2 * half * scale}">{body}</svg>')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write the patched block into the disc copy")
    args = ap.parse_args()

    vol = CarinVolume(IsoImage(str(ISO_COPY)))
    vol.calibrate()
    blk = vol.block(TILE >> 8)
    orig = bytes(blk.payload)
    before = Tile(orig, vol.layout)
    log(f"tile {TILE:#x}: block {blk.sector}, {blk.length} sectors on disc, decoded {len(orig)} bytes")

    # sanity of the editing rules on the untouched tile
    nodes = [before.s5 + 8 * k for k in range(before.n5)]
    assert check(before, "original") == 0, "the rules do not hold on the untouched tile"
    log("rule check on the untouched tile: node cycles rebuilt identically, every start node has the lower "
        "(x, y), S5 sorted inside each level group, every S10 entry shares a node")

    t = Tile(orig, vol.layout)
    ctx = patch(t)
    assert check(t, "patched") == 0
    changed = [x for x in range(len(orig)) if orig[x] != t.d[x]]
    log(f"bytes changed in the decoded tile: {len(changed)} (sections untouched in size: {len(t.d) == len(orig)})")

    for i, (a, b, oneway) in TRAVEL.items():
        pa, pb = before.poly(i), t.poly(i)
        log(f"  rec {i:3d}: {seg_length(pa):3d} m -> {seg_length(pb):3d} m, {len(pa)} -> {len(pb)} points, "
            f"junction {before.d[before.r(i) + 0x11] & 15} -> {t.d[t.r(i) + 0x11] & 15}, "
            f"travel {a} -> {b}, restriction: "
            f"{('two-way', 'along', 'against', 'closed')[(t.d[t.r(i) + 0x0B] >> 4) & 3]}")

    enc = cf1.encode_type00(bytes(t.d), vol.layout, vol.db_rel, vol.subrel)
    assert cf1.decode_block(enc, vol.layout, vol.db_rel, subrel=vol.subrel, sector_size=vol.sector_size) == bytes(t.d)
    room = blk.length * vol.sector_size
    log(f"re-encoded CF=1: {len(enc)} bytes, room in place: {room} (original raw {len(blk.raw)})")
    assert len(enc) <= room, "the patched block no longer fits in its sectors"

    osm = [[(p["lon"], p["lat"]) for p in e["geometry"]]
           for e in json.load(open(DATA / "osm_ways.json"))["elements"]
           if e["tags"]["highway"] not in ("footway", "cycleway", "pedestrian", "path", "steps", "service")]
    (DATA / f"tile_{TILE:#x}_patched.bin").write_bytes(bytes(t.d))
    svg(before, t, osm, DATA / "before_after.svg")
    log("wrote dataset/tile_0x4c184f18_patched.bin and dataset/before_after.svg")

    if args.write:
        write_block(vol, blk.sector, enc + bytes(room - len(enc)))
        vol2 = CarinVolume(IsoImage(str(ISO_COPY)))
        vol2.calibrate()
        back = vol2.block(TILE >> 8)
        assert back.payload == bytes(t.d), "read-back differs"
        segs = {s["index"]: s for s in road_segments(back.payload, vol2.layout)}
        log(f"WRITTEN to the disc copy and read back identical; ring segments (junction 6) now: "
            f"{[i for i in NEW_ENDS if (back.payload[before.r(i) + 0x11] & 15) == 6]}")
        log("old crossing records now: " + ", ".join(
            f"{i}={segs[i]['name'] or '-'}/{len(segs[i]['coords'])}pt" for i in sorted(NEW_ENDS)))
    else:
        log("dry run: nothing written (use --write)")


if __name__ == "__main__":
    main()
