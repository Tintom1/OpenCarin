"""Step 7: the validation battery on the patched copy (docs: PLAN 5.8). Not a test on a unit.

    uv run --with numpy python examples/04_update_modugno_roundabout/07_validate.py [--skip-diff]

1. structure   the rules hold on the edited street and coarse tile; only the expected blocks differ from the
               original image (byte compare of the whole image, mapped to blocks)
2. twins       every S6 node of the edited tiles and of their neighbours still has a twin that points back
3. routing     ten origin / destination pairs on the ring, its four links and Viale della Repubblica, routed
               on the disc tile (one-way bits) and on the OSM ways of the same area, compared
4. lookups     spatial index, every 0x0E street run, 0x10 entries, 0x04 records
Exit status 1 if any check fails.
"""
from __future__ import annotations

import argparse
import heapq
import json
import struct
import sys
from math import hypot
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carin.parser.cf1.decoder_0e import decode_s2_links
from carin.parser.house_numbers import run_envelope, segment_house_numbers
from carin.parser.cf1.tile00 import Node, Seg, Tile00
from carin.parser.iso import CARIN_WINDOW, CarinVolume, IsoImage
from carin.parser.refs import OffsetMap
from carin.parser.spatial import SpatialIndex, tiles_at
from common import CENTER, DATA, ISO_COPY, to_m
from osm_area import LINKS, geom, junctions, ring_polygon, ways

STREET, COARSE = 0x4C184F18, 0x5C58A51C
ORIGINAL = Path(__file__).resolve().parents[2] / "dataset" / "NAV_DB_21708.ISO"
FAILS: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        FAILS.append(msg)


def openvol(path) -> CarinVolume:
    v = CarinVolume(IsoImage(str(path)))
    v.calibrate()
    return v


# ---------------------------------------------------------------------------------------------- 1
def image_diff(vol: CarinVolume, blocks) -> None:
    """Every differing 512-byte sector of the image lies in a block step 6 rewrote (and in DB_0 / DB_1)."""
    parts = [(p.offset, p.size) for p in vol.parts]
    extents = sorted((s * 512 + vol.parts[s // CARIN_WINDOW].offset - (s // CARIN_WINDOW) * CARIN_WINDOW * 512, l * 512)
                     for s, l, *_ in blocks)
    chunk = 1 << 24
    diff_sectors = []
    with open(ORIGINAL.resolve(), "rb") as a, open(ISO_COPY, "rb") as b:
        pos = 0
        while True:
            x, y = a.read(chunk), b.read(chunk)
            if not x and not y:
                break
            if x != y:
                for k in range(0, len(x), 512):
                    if x[k:k + 512] != y[k:k + 512]:
                        diff_sectors.append(pos + k)
            pos += len(x)
    inside = lambda off: any(lo <= off < lo + n for lo, n in extents)
    stray = [o for o in diff_sectors if not inside(o)]
    check(pos == ORIGINAL.resolve().stat().st_size == ISO_COPY.stat().st_size, f"image sizes equal ({pos} bytes)")
    check(not stray, f"{len(diff_sectors)} sectors differ from the original, all inside the {len(extents)} rewritten blocks"
                     + (f"; OUTSIDE: {[hex(o) for o in stray[:5]]}" if stray else ""))
    outside_db = [o for o in diff_sectors if not any(lo <= o < lo + n for lo, n in parts)]
    check(not outside_db, "no byte of the ISO structures (directories, volume descriptors) changed")


# ---------------------------------------------------------------------------------------------- 2
def twins(tile: Tile00, tile_id: int, vol: CarinVolume, label: str) -> None:
    """S6 node k of this tile -> neighbour S6 node at ext offset; it must hold this tile's id and offset, same absolute point."""
    _, _, n6 = tile.offsets()
    off = {id(n): o for n, o in zip(tile.nodes6, [n6[id(n)] for n in tile.nodes6])}
    bad = total = 0
    cache = {}
    for n in tile.nodes6:
        nid, toff, _ = n.ext
        if not nid:
            continue
        total += 1
        if nid not in cache:
            blk = vol.block(nid >> 8)
            nb = Tile00.parse(blk.payload, vol.layout)
            cache[nid] = (nb, {o: nd for nd, o in zip(nb.nodes6, [nb.offsets()[2][id(x)] for x in nb.nodes6])})
        nb, by_off = cache[nid]
        twin = by_off.get(toff)
        ok = twin is not None and twin.ext[0] == tile_id and twin.ext[1] == off[id(n)]
        if ok:
            ax = (tile.frame.x0 + (n.u << 6), tile.frame.y0 + (n.v << 6))
            bx = (nb.frame.x0 + (twin.u << 6), nb.frame.y0 + (twin.v << 6))
            ok = ax == bx
        bad += not ok
    check(bad == 0, f"{label}: {total - bad} / {total} S6 twins point back at the same absolute position")


# ---------------------------------------------------------------------------------------------- 3
def travel(seg: Seg):
    """Directions a record can be driven: [(from node, to node)]."""
    d = (seg.raw[0x0B] >> 4) & 3
    return {0: [(seg.a, seg.b), (seg.b, seg.a)], 1: [(seg.a, seg.b)], 2: [(seg.b, seg.a)], 3: []}[d]


def dijkstra(edges: dict, src, dst):
    """edges: node -> [(node, metres, label)]. Returns (metres, [nodes]) or None."""
    best, prev, heap = {src: 0.0}, {}, [(0.0, 0, src)]
    cnt = 0
    while heap:
        d, _, u = heapq.heappop(heap)
        if u == dst:
            path = [u]
            while path[-1] != src:
                path.append(prev[path[-1]])
            return d, path[::-1]
        if d > best.get(u, 1e18):
            continue
        for v, w, _lab in edges.get(u, []):
            if d + w < best.get(v, 1e18):
                best[v] = d + w
                prev[v] = u
                cnt += 1
                heapq.heappush(heap, (d + w, cnt, v))
    return None


PAIRS = [("W", "NE"), ("W", "F"), ("NE", "W"), ("NE", "F"), ("E", "W"), ("E", "NE"), ("E", "F"),
         ("R3", "R2"), ("R2", "R3"), ("NE", "E")]
EXPECT = {                                      # hand-checked on the OSM ways (ring runs counter-clockwise R1 R2 R3 R4 R5 R6)
    ("W", "NE"): "W R5 R6 R1 R2 NE", ("W", "F"): "W R5 R6 F", ("NE", "W"): "NE R3 R4 W",
    ("NE", "F"): "NE R3 R4 R5 R6 F", ("E", "W"): "E R1 R2 R3 R4 W", ("E", "NE"): "E R1 R2 NE",
    ("E", "F"): "E R1 R2 R3 R4 R5 R6 F", ("R3", "R2"): "R3 R4 R5 R6 R1 R2", ("R2", "R3"): "R2 R3",
    ("NE", "E"): None}


def routing(t: Tile00) -> None:
    w = ways()
    jn = junctions(w)
    to_xy = lambda ll: to_m(*ll)
    # roles of the disc nodes: by position (metres from the centre)
    role = {}
    for k, ll in jn.items():
        u, v = t.local(*ll)
        for n in t.nodes5:
            if hypot(*(a - b for a, b in zip(to_xy(t.lonlat(n.u, n.v)), to_xy(ll)))) < 2.5:
                role[id(n)] = k
    ring = [s for s in t.segs if (s.raw[0x11] & 15) == 6 and not (s.raw[0x10] & 15 != 2)]
    ring_nodes = {id(x) for s in ring for x in (s.a, s.b)}
    # E and F: the far ends of the two Viale della Repubblica records at R1 / R6
    r1 = next(n for n in t.nodes5 if role.get(id(n)) == "R1")
    r6 = next(n for n in t.nodes5 if role.get(id(n)) == "R6")
    seg_in = next(s for s in t.segs if r1 in (s.a, s.b) and (s.raw[0x11] & 15) != 6 and (s.raw[0x0B] >> 4) & 3 and
                  t.passive[2][s.name][0] and t.text(t.passive[2][s.name][0][1]) == "viale della repubblica")
    seg_out = next(s for s in t.segs if r6 in (s.a, s.b) and (s.raw[0x11] & 15) != 6 and (s.raw[0x0B] >> 4) & 3 and
                   t.passive[2][s.name][0] and t.text(t.passive[2][s.name][0][1]) == "viale della repubblica")
    role[id(seg_in.b if seg_in.a is r1 else seg_in.a)] = "E"
    role[id(seg_out.b if seg_out.a is r6 else seg_out.a)] = "F"
    names = {v: k for k, v in role.items()}
    check(len(role) == 10 and set(role.values()) == {"R1", "R2", "R3", "R4", "R5", "R6", "NE", "W", "E", "F"},
          f"disc nodes found for the ten roles: {sorted(role.values())}")
    local = [s for s in t.segs if id(s.a) in role and id(s.b) in role]
    check(len(local) == 12, f"{len(local)} records join the ten nodes (6 ring + 4 links + 2 Viale della Repubblica)")
    check(all(not s.turns for s in local), "no forbidden turn (S10) on the local records")
    ringlen = sum(len(s.shape) + 1 for s in local if (s.raw[0x11] & 15) == 6)
    check(ringlen >= 12, f"ring drawn with {ringlen} points on ~29 m")
    check(sum((s.raw[0x11] & 15) == 6 for s in local) == 6, "six ring segments have junction type 6")
    disc = {}
    pos = {id(n): to_xy(t.lonlat(n.u, n.v)) for s in local for n in (s.a, s.b)}
    for s in local:
        for f, to in travel(s):
            pts = t.polyline(s) if f is s.a else t.polyline(s)[::-1]
            m = sum(hypot(*(a - b for a, b in zip(to_xy(p), to_xy(q)))) for p, q in zip(pts, pts[1:]))
            disc.setdefault(role[id(f)], []).append((role[id(to)], m, None))
    # the OSM side
    osm = {}
    rp = ring_polygon(w)
    at = {k: min(range(len(rp)), key=lambda i: hypot(*(a - b for a, b in zip(to_xy(rp[i]), to_xy(jn[k]))))) for k in jn if k.startswith("R")}
    order = ["R1", "R2", "R3", "R4", "R5", "R6"]
    plen = lambda pts: sum(hypot(*(a - b for a, b in zip(to_xy(p), to_xy(q)))) for p, q in zip(pts, pts[1:]))
    for a, b in zip(order, order[1:] + order[:1]):
        i, j, arc, k = at[a], at[b], [rp[at[a]]], at[a]
        while k != j:
            k = (k + 1) % len(rp)
            arc.append(rp[k])
        osm.setdefault(a, []).append((b, plen(arc), None))
    e_ll, f_ll = t.lonlat(*next(n for n in t.nodes5 if role.get(id(n)) == "E").xy), t.lonlat(*next(n for n in t.nodes5 if role.get(id(n)) == "F").xy)
    from osm_area import project
    for wid, (fr, to) in LINKS.items():
        g = geom(w, wid)
        if fr and to:
            osm.setdefault(fr, []).append((to, plen(g), None))
        elif to:                                                                  # inbound Viale della Repubblica: from E
            s_e = project(g, to_xy(e_ll))
            osm.setdefault("E", []).append((to, plen(g) - s_e, None))
        else:                                                                     # outbound: to F
            s_f = project(g, to_xy(f_ll))
            osm.setdefault(fr, []).append(("F", s_f, None))
    bad = 0
    print("  pair          disc route                      m     OSM route                       m")
    for a, b in PAIRS:
        rd, ro = dijkstra(disc, a, b), dijkstra(osm, a, b)
        sd = " ".join(rd[1]) if rd else None
        so = " ".join(ro[1]) if ro else None
        ok = sd == so == EXPECT[(a, b)] and (rd is None or abs(rd[0] - ro[0]) <= max(3.0, 0.08 * ro[0]))
        bad += not ok
        print(f"  {a:>3} -> {b:<3}  {str(sd):<30} {rd[0] if rd else 0:5.0f}   {str(so):<30} {ro[0] if ro else 0:5.0f}  {'ok' if ok else 'DIFFERS'}")
    check(bad == 0, f"{len(PAIRS) - bad} / {len(PAIRS)} pairs: same route as OSM and as the hand-checked list, lengths within 8%")


# ---------------------------------------------------------------------------------------------- 4
def lookups(vol_new: CarinVolume, vol_old: CarinVolume, tnew: Tile00, told: Tile00) -> None:
    got = {ly.index: tiles_at(vol_new, ly.index, *CENTER) for ly in SpatialIndex(vol_new).grid_layers()}
    flat = {x for v in got.values() for x in v}
    check(STREET in flat and COARSE in flat, f"spatial index: layers at the roundabout give the street and the coarse tile ({sorted(hex(x) for x in flat)[:6]} ...)")
    smap = OffsetMap.from_json(json.load(open(DATA / "redraw.json"))["offsets"])
    name = lambda t, s: (t.text(t.passive[2][s.name][0][1]) if t.passive[2][s.name][0] else None)
    # 0x0E runs
    runs = json.load(open(DATA / "runs_before.json")) if (DATA / "runs_before.json").exists() else None
    blocks = {b[0] for b in json.load(open(DATA / "patched_blocks.json")) if b[2] == 14}
    nruns = bad = 0
    for sec in sorted(blocks):
        old = decode_s2_links(vol_old.block(sec).payload, vol_old.layout)
        new = decode_s2_links(vol_new.block(sec).payload, vol_new.layout)
        for lo, ln in zip(old, new):
            if lo["tile_block_id"] != STREET:
                assert ln == lo
                continue
            nruns += 1
            i = (lo["s4_offset"] - smap.seg_base) // 32
            names_old = [name(told, told.segs[k]) for k in range(i, i + lo["s4_count"]) if smap.seg_new[smap.seg_order[k]] is not None]
            j = (ln["s4_offset"] - smap.new_seg_base) // 32
            names_new = [name(tnew, tnew.segs[k]) for k in range(j, j + ln["s4_count"])]
            same_run = ln["s4_count"] == lo["s4_count"]
            bad += names_old != names_new or (same_run and (ln["even"] != lo["even"] or ln["odd"] != lo["odd"]))
    check(bad == 0, f"{nruns} street runs of {len(blocks)} 0x0E blocks land on records with the same street names (ranges unchanged where the run kept all its records)")
    # 0x10 entries
    b10 = [b[0] for b in json.load(open(DATA / "patched_blocks.json")) if b[2] == 16]
    bad = n = 0
    for sec in b10:
        po, pn = vol_old.block(sec).payload, vol_new.block(sec).payload
        s4, n4 = struct.unpack_from(">HH", po, 8 + 16)
        for k in range(n4):
            o = s4 + 8 * k
            bo, bn = struct.unpack_from(">IHH", po, o), struct.unpack_from(">IHH", pn, o)
            if bo[0] == STREET:
                n += 1
                bad += not (bo[0] == bn[0] and bo[2] == bn[2] and
                            name(told, told.segs[(bo[1] - smap.seg_base) // 32]) == name(tnew, tnew.segs[(bn[1] - smap.new_seg_base) // 32]))
    check(bad == 0, f"{n} street-directory entries (0x10) name a record of the same street")
    # 0x04
    sec04 = [b[0] for b in json.load(open(DATA / "patched_blocks.json")) if b[2] == 4][0]
    po, pn = vol_old.block(sec04).payload, vol_new.block(sec04).payload
    off, n_old = struct.unpack_from(">HH", po, 8)
    _, n_new = struct.unpack_from(">HH", pn, 8)
    ro = [po[off + 10 * i: off + 10 * i + 10] for i in range(n_old)]
    rn = [pn[off + 10 * i: off + 10 * i + 10] for i in range(n_new)]
    keep = [i for i, o in enumerate(smap.seg_order) if smap.seg_new[o] is not None]
    same = all(rn[smap.index_new(smap.seg_new[smap.seg_order[i]])] == ro[i] for i in keep) if hasattr(smap, "index_new") else \
        all(rn[(smap.seg_new[smap.seg_order[i]] - smap.new_seg_base) // 32] == ro[i] for i in keep)
    check(n_new == len(tnew.segs) and same, f"0x04: {n_new} records = the tile's S4 count; every surviving record keeps its house numbers")


def envelopes(vol_new: CarinVolume, vol_old: CarinVolume) -> None:
    """The 0x0E house-number ranges of a run are the envelope of its 0x04 records (98.8% on the disc): the edit must not break a run that held."""
    smap = OffsetMap.from_json(json.load(open(DATA / "redraw.json"))["offsets"])
    sec04 = [b[0] for b in json.load(open(DATA / "patched_blocks.json")) if b[2] == 4][0]
    h_old, h_new = segment_house_numbers(vol_old.block(sec04).payload), segment_house_numbers(vol_new.block(sec04).payload)
    broke, held = [], 0
    for sec in sorted(b[0] for b in json.load(open(DATA / "patched_blocks.json")) if b[2] == 14):
        old = decode_s2_links(vol_old.block(sec).payload, vol_old.layout)
        new = decode_s2_links(vol_new.block(sec).payload, vol_new.layout)
        for lo, ln in zip(old, new):
            if lo["tile_block_id"] != STREET:
                continue
            i = (lo["s4_offset"] - smap.seg_base) // 32
            j = (ln["s4_offset"] - smap.new_seg_base) // 32
            was = run_envelope(h_old, i, lo["s4_count"]) == (lo["even"], lo["odd"])
            now = run_envelope(h_new, j, ln["s4_count"]) == (ln["even"], ln["odd"])
            held += was and now
            if was and not now:
                broke.append((hex(sec), lo["s4_offset"], lo["s4_count"]))
    removed = [i for i, o in enumerate(smap.seg_order) if smap.seg_new[o] is None]
    numbered = [i for i in removed if h_old[i]["side_a"] or h_old[i]["side_b"]]
    check(not broke, f"0x04 envelope == 0x0E ranges still holds for the {held} runs where it held before"
                     + (f"; BROKEN for {len(broke)} (first {broke[:3]})" if broke else "")
                     + f" (removed records {removed}; with house numbers: {numbered})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-diff", action="store_true", help="skip the whole-image byte compare (about a minute)")
    args = ap.parse_args()
    new, old = openvol(ISO_COPY), openvol(ORIGINAL)
    tn = Tile00.parse(new.block(STREET >> 8).payload, new.layout)
    to = Tile00.parse(old.block(STREET >> 8).payload, old.layout)
    cn = Tile00.parse(new.block(COARSE >> 8).payload, new.layout)
    print("1. structure")
    check(tn.check() == [], "street tile: start node, S5 order, level groups, node cycles, turns all hold")
    check(cn.check() == [], "coarse tile: the same rules hold")
    check(Tile00.parse(tn.build(), new.layout).graph() == tn.graph(), "street tile: build -> parse gives the same graph")
    if not args.skip_diff:
        image_diff(new, json.load(open(DATA / "patched_blocks.json")))
    print("2. twins")
    twins(tn, STREET, new, "street tile")
    twins(cn, COARSE, new, "coarse tile")
    print("3. routing")
    routing(tn)
    print("4. lookups")
    lookups(new, old, tn, to)
    envelopes(new, old)
    print(f"\n{'FAILED: ' + str(len(FAILS)) + ' check(s)' if FAILS else 'all checks passed'} (not run on a unit)")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
