"""Step 5: redraw the Modugno roundabout in tile 0x4c184f18 with its real topology (tile editor, section growth).

Replaces the eight records and three inner nodes of the 2016 crossing by what OSM has there
(osm_area.py): the ring split at its six junctions into six one-way segments (junction type 6), four
one-way links (two to the north-east arm, two to Via Roma west) and the two one-way carriageways of
Viale della Repubblica, with the real shape points. The tile is edited as a model (carin.parser.cf1.tile00),
so records and nodes are added and removed and every pointer in it is rewritten.

    uv run --with numpy python examples/04_update_modugno_roundabout/05_redraw_roundabout.py [--src copy|original] [--out FILE]

Dry run: nothing is written to a disc image. The result is dataset/tile_0x4c184f18_redrawn.bin (decoded),
dataset/redraw.json (old record -> new record map, used by step 6 for the references outside the tile)
and dataset/redraw.svg.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from math import hypot
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carin.parser import cf1
from carin.parser.cf1.tile00 import Node, Seg, Tile00, diff_graph
from carin.parser.iso import CarinVolume, IsoImage
from carin.parser.refs import OffsetMap
from common import DATA, ISO_COPY, to_m
from osm_area import geom, interior, junctions, project, ring_polygon, ways

TILE = 0x4C184F18
ORIGINAL = Path(__file__).resolve().parents[2] / "dataset" / "NAV_DB_21708.ISO"
OLD = {"B": 22, "H": 23, "D": 24, "C": 25, "A": 26, "F": 27, "E": 28}      # S5 nodes of the old crossing
OLD_SEGS = (17, 18, 38, 41, 43, 44, 45, 46)                                  # its eight records
CLASS = 2                                                                    # secondary / tertiary / links
NAME_NONE = 1                                                                # S2 record without a street name


def place_seg(t: Tile00, tmpl: Seg, frm: Node, to: Node, pts, *, ring: bool) -> Seg:
    """A new one-way segment travelling frm -> to through `pts` (local (u, v), in travel order).

    The stored start is the end with the lower (x, y): when travel runs the other way the shape is
    reversed and the one-way bit says "against the stored direction".
    """
    s = Seg(tmpl.raw, tmpl.tail)
    s.raw[0x10] = CLASS
    s.raw[0x11] = (tmpl.raw[0x11] & 0xF0) | (0x06 if ring else 0x09)       # 6 roundabout, 9 connector
    s.raw[0x0A] = 0x0B
    s.raw[0x1C], s.raw[0x1D] = 0x10, 0x00                                    # one lane, one-way, not built up
    fwd = frm.xy < to.xy
    s.a, s.b = (frm, to) if fwd else (to, frm)
    seq = list(pts) if fwd else list(pts)[::-1]
    s.shape = [struct.pack(">HHBB", u, v, 0, 0) for u, v in seq]
    s.raw[0x0B] = (tmpl.raw[0x0B] & 0xC0) | 0x0C | (0x10 if fwd else 0x20)
    s.name = NAME_NONE
    return s


def reorient(t: Tile00, s: Seg, frm: Node, to: Node, pts) -> None:
    """Re-point an existing one-way segment at new end nodes and a new shape (travel frm -> to)."""
    one = (s.raw[0x0B] >> 4) & 3
    assert one in (1, 2), "only one-way records are reoriented"
    fwd = frm.xy < to.xy
    s.a, s.b = (frm, to) if fwd else (to, frm)
    seq = list(pts) if fwd else list(pts)[::-1]
    s.shape = [struct.pack(">HHBB", u, v, 0, 0) for u, v in seq]
    s.raw[0x0B] = (s.raw[0x0B] & 0xCF) | (0x10 if fwd else 0x20)


def dedupe(pts, ends):
    """Drop shape points that fall on the grid point of the previous point or of an end node."""
    out, prev = [], ends[0]
    for p in pts:
        if p != prev and p != ends[1]:
            out.append(p)
            prev = p
    return out


def redraw(t: Tile00, log) -> dict:
    w = ways()
    jn = junctions(w)
    ring = ring_polygon(w)
    L = lambda c: t.local(*c)
    segs0 = list(t.segs)
    nodes0 = list(t.nodes5)
    old = {k: nodes0[i] for k, i in OLD.items()}
    names = [t.text(t.passive[2][segs0[i].name][0][1]) if t.passive[2][segs0[i].name][0] else None for i in OLD_SEGS]
    log(f"old crossing records {OLD_SEGS}: street names {names}")
    assert names == [None, None, "via roma", "via roma", "viale della repubblica", "viale della repubblica",
                     "viale della repubblica", "viale della repubblica"], "this is not the expected tile"

    tmpl_ring, tmpl_link = segs0[177].clone(), segs0[17].clone()
    signs = {  # signposts of the old records go to the new record that carries the same traffic
        "modugno centro": segs0[43].signs, "carbonara": segs0[44].signs, "pescara-napoli": segs0[17].signs}
    seg45, seg46 = segs0[45], segs0[46]
    tmc_lost = sum(len(segs0[i].tmc) for i in (38, 41))
    turns_lost = sum(len(segs0[i].turns) for i in OLD_SEGS)

    # remove the old crossing: six records (45 and 46 are reused), its three inner nodes
    for i in (17, 18, 38, 41, 43, 44):
        t.remove_seg(segs0[i])
    for k in ("H", "D", "C"):
        t.remove_node(old[k])
    for s in (seg45, seg46):
        s.turns = []
    log(f"removed 6 records + 3 inner nodes; dropped {turns_lost} forbidden turn(s) and {tmc_lost} TMC triple(s) that sat on them")

    # nodes: six ring nodes; B moves to the junction of the two west links
    R = {}
    for k in ("R1", "R2", "R3", "R4", "R5", "R6"):
        u, v = L(jn[k])
        R[k] = Node(5, u, v, old["H"].flags)
        t.insert_node(R[k], CLASS)
    bu, bv = L(jn["W"])
    log(f"B moves {old['B'].xy} -> {(bu, bv)} (junction of the west links; {hypot(*(a - b for a, b in zip(to_m(*t.lonlat(*old['B'].xy)), to_m(*jn['W'])))):.1f} m along Via Roma)")
    old["B"].u, old["B"].v = bu, bv
    assert len({n.xy for n in R.values()} | {old["B"].xy, old["A"].xy}) == 8, "two nodes on one grid point"

    # ring: counter-clockwise R1 -> R2 -> ... -> R6 -> R1
    at = {k: min(range(len(ring)), key=lambda i: hypot(*(a - b for a, b in zip(to_m(*ring[i]), to_m(*jn[k])))))
          for k in R}
    order = [(at[k] - at["R1"]) % len(ring) for k in R]
    assert order == sorted(order) and len(set(order)) == 6, f"ring junctions out of order: {order}"
    new_ring = []
    names6 = list(R)
    for a, b in zip(names6, names6[1:] + names6[:1]):
        i, j, arc = at[a], at[b], []
        k = i
        while k != j:
            k = (k + 1) % len(ring)
            arc.append(ring[k])
        pts = dedupe([L(c) for c in arc[:-1]], (R[a].xy, R[b].xy))
        new_ring.append(place_seg(t, tmpl_ring, R[a], R[b], pts, ring=True))
    # links (one-way, no name): ends are ring junctions and the existing nodes A (north-east) and B (west)
    A, B = old["A"], old["B"]
    link_ends = {80640277: (R["R2"], A), 1326505910: (A, R["R3"]), 1331933266: (R["R4"], B), 80640279: (B, R["R5"])}
    new_links = {}
    for wid, (f, to) in link_ends.items():
        g = geom(w, wid)
        pts = dedupe([L(c) for c in g[1:-1]], (f.xy, to.xy))
        new_links[wid] = place_seg(t, tmpl_link, f, to, pts, ring=False)
    # Viale della Repubblica: records 45 (inbound, from E) and 46 (outbound, to F) keep their names
    g_in, g_out = geom(w, 529215906), geom(w, 503040064)
    s_e = project(g_in, to_m(*t.lonlat(*old["E"].xy)))
    s_f = project(g_out, to_m(*t.lonlat(*old["F"].xy)))
    total_in = sum(hypot(*(a - b for a, b in zip(to_m(*p), to_m(*q)))) for p, q in zip(g_in, g_in[1:]))
    pts_in = dedupe([L(c) for c in interior(g_in, s_e, total_in)], (old["E"].xy, R["R1"].xy))
    pts_out = dedupe([L(c) for c in interior(g_out, 0.0, s_f)], (R["R6"].xy, old["F"].xy))
    reorient(t, seg45, old["E"], R["R1"], pts_in)
    reorient(t, seg46, R["R6"], old["F"], pts_out)

    # signposts follow the traffic they were on
    seg45.signs += signs["modugno centro"]
    seg46.signs += signs["carbonara"]
    new_links[80640277].signs += signs["pescara-napoli"]

    # the new unnamed records open the class group, in front of the surviving unnamed record
    fresh = new_ring + list(new_links.values())
    for k, s in enumerate(fresh):
        t.insert_seg(s, CLASS, k)
    t.normalize()
    touched = fresh + [seg45, seg46] + [s for s in t.segs if old["B"] in (s.a, s.b)]
    for s in touched:
        t.finalize(s)
    t.rebuild_cycles()
    bad = t.check()
    assert not bad, bad
    log(f"new: {len(new_ring)} ring records (junction 6), {len(new_links)} links; shape points: "
        f"ring {sum(len(s.shape) for s in new_ring)}, links {sum(len(s.shape) for s in new_links.values())}, "
        f"Viale della Repubblica {len(pts_in)} + {len(pts_out)}")
    return {"fresh": fresh, "seg45": seg45, "seg46": seg46, "nodes": R, "old_segs": [segs0[i] for i in OLD_SEGS],
            "segs0": segs0, "links": new_links, "ring": new_ring}


def svg(t0: Tile00, t1: Tile00, osm, path: Path) -> None:
    scale, half = 5.0, 70
    pt = lambda ll: f"{(to_m(*ll)[0] + half) * scale:.1f},{(half - to_m(*ll)[1]) * scale:.1f}"
    panels = []
    for k, (t, title) in enumerate(((t0, "disc 2016 (before)"), (t1, "redrawn (after)"))):
        g = [f'<text x="6" y="16" font-size="13" font-family="sans-serif">{title}</text>']
        for o in osm:
            g.append(f'<polyline fill="none" stroke="#9bb7ff" stroke-width="5" points="{" ".join(map(pt, o))}"/>')
        for s in t.segs:
            p = t.polyline(s)
            if min(hypot(*to_m(*c)) for c in p) > 2 * half:
                continue
            ringseg = (s.raw[0x11] & 15) == 6
            g.append(f'<polyline fill="none" stroke="{"#d62728" if ringseg else "#555"}" stroke-width="2" '
                     f'points="{" ".join(map(pt, p))}"/>')
            for u, v in ([s.a.xy, s.b.xy]):
                x, y = pt(t.lonlat(u, v)).split(",")
                g.append(f'<circle cx="{x}" cy="{y}" r="2.5" fill="#000"/>')
        panels.append(f'<g transform="translate(0,{k * (2 * half * scale + 20)})"><rect width="{2 * half * scale}" '
                      f'height="{2 * half * scale}" fill="#fafafa" stroke="#ccc"/>{"".join(g)}</g>')
    h = 2 * (2 * half * scale) + 20
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{2 * half * scale}" height="{h}">{"".join(panels)}</svg>')
    for name, panel in (("before", panels[0]), ("after", panels[1])):      # one file per panel too
        body = panel.split(">", 1)[1].rsplit("</g>", 1)[0]
        path.with_name(f"{path.stem}_{name}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{2 * half * scale}" height="{2 * half * scale}">{body}</svg>')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", choices=("original", "copy"), default="original",
                    help="where the untouched tile is read from (default: the original image, read only)")
    args = ap.parse_args()
    report = []
    log = lambda m: (print(m), report.append(m))

    iso = ORIGINAL if args.src == "original" else ISO_COPY
    vol = CarinVolume(IsoImage(str(iso)))
    vol.calibrate()
    blk = vol.block(TILE >> 8)
    orig = bytes(blk.payload)
    t0 = Tile00.parse(orig, vol.layout)
    assert t0.build() == orig and not t0.check()
    t = Tile00.parse(orig, vol.layout)
    omap = OffsetMap.capture(t)
    ctx = redraw(t, log)
    omap.finish(t)
    new = t.build()
    g0, g1 = t0.graph(), t.graph()
    log(f"S4 {len(t0.segs)} -> {len(t.segs)} records, S5 {len(t0.nodes5)} -> {len(t.nodes5)} nodes, "
        f"S7 {sum(len(s.shape) for s in t0.segs)} -> {sum(len(s.shape) for s in t.segs)} shape points, "
        f"decoded {len(orig)} -> {len(new)} bytes")

    enc = cf1.encode_type00(new, vol.layout, vol.db_rel, vol.subrel)
    back = cf1.decode_block(enc, vol.layout, vol.db_rel, subrel=vol.subrel, sector_size=vol.sector_size)
    assert back == new
    room = blk.length * vol.sector_size
    log(f"re-encoded CF=1: {len(enc)} bytes in {room} (original {len(blk.raw)} raw; room left {room - len(enc)})")
    (DATA / f"tile_{TILE:#x}_redrawn.bin").write_bytes(new)
    osm = [[(p["lon"], p["lat"]) for p in e["geometry"]] for e in ways().values()
           if e["tags"]["highway"] not in ("footway", "cycleway", "pedestrian", "path", "steps", "service")]
    svg(t0, t, osm, DATA / "redraw.svg")
    json.dump({"tile": TILE, "fits": len(enc) <= room, "encoded": len(enc), "room": room, "offsets": omap.to_json()},
              open(DATA / "redraw.json", "w"))
    removed = [o for o, n in omap.seg_new.items() if n is None]
    log(f"S4 records removed: {[(o - omap.seg_base) // 32 for o in removed]}; "
        f"S6 nodes moved {next(iter(omap.s6_new.items()))} ... (+{next(iter(omap.s6_new.values())) - next(iter(omap.s6_new))})")
    log("wrote dataset/tile_0x4c184f18_redrawn.bin, dataset/redraw.svg")


if __name__ == "__main__":
    main()
