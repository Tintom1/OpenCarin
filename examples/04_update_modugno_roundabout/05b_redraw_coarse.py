"""Step 5b: the same change in the coarse tile (type 0x03) that holds the old crossing.

A coarse level keeps the street roads of its classes (0x03: classes 0-2). Every node where three or
more of them meet is a coarse node and a coarse segment is a street segment (or several, merged through
two-segment nodes; docs/carindb/03-road-network.md section 6.7, "How the coarse levels follow from the street
level"). Here all ends of the changed records are three-way nodes, so the coarse tile holds copies of the
street records: this step finds them by the absolute CARIN coordinates of their end nodes, drops the ones
the street edit removed and adds / adopts the new ones, with the same fields and shape points.

    uv run --with numpy python examples/04_update_modugno_roundabout/05b_redraw_coarse.py

Needs dataset/tile_0x4c184f18_redrawn.bin and dataset/redraw.json (step 5). Dry run: writes
dataset/tile_0x5c58a51c_redrawn.bin and dataset/redraw_coarse.json (the offset map of the coarse tile).
"""
from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carin.parser.cf1.tile00 import Node, Seg, Tile00
from carin.parser.geometry import VERTEX_SHIFT
from carin.parser.iso import CarinVolume, IsoImage
from carin.parser.refs import OffsetMap
from common import DATA

STREET, COARSE = 0x4C184F18, 0x5C58A51C
ORIGINAL = Path(__file__).resolve().parents[2] / "dataset" / "NAV_DB_21708.ISO"
CLASS = 2


def absxy(t: Tile00, u: int, v: int) -> tuple[int, int]:
    return (t.frame.x0 + (u << VERTEX_SHIFT), t.frame.y0 + (v << VERTEX_SHIFT))


def main() -> None:
    log = print
    vol = CarinVolume(IsoImage(str(ORIGINAL)))
    vol.calibrate()
    sb = Tile00.parse(vol.block(STREET >> 8).payload, vol.layout)               # street tile before
    sa = Tile00.parse((DATA / f"tile_{STREET:#x}_redrawn.bin").read_bytes(), vol.layout)   # and after
    info = json.load(open(DATA / "redraw.json"))
    smap = OffsetMap.from_json(info["offsets"])
    blk = vol.block(COARSE >> 8)
    tc = Tile00.parse(blk.payload, vol.layout)
    assert tc.coarse and tc.build() == blk.payload
    omap = OffsetMap.capture(tc)
    sb_segs, n5_before = list(tc.segs), len(tc.nodes5)

    ends = lambda t, s: (absxy(t, *s.a.xy), absxy(t, *s.b.xy))
    # coarse records and nodes by absolute end coordinates
    cseg = {}
    for s in tc.segs:
        cseg.setdefault(ends(tc, s), []).append(s)
    cnode = {absxy(tc, *n.xy): n for n in tc.nodes5 + tc.nodes6}

    removed_before = [sb.segs[(o - smap.seg_base) // 32] for o, n in smap.seg_new.items() if n is None]
    # street records that exist in both tiles keep their identity in the model only through the offset map:
    # find the survivors that changed (same old offset) by their coordinates
    survivors = {o: sb.segs[(o - smap.seg_base) // 32] for o, n in smap.seg_new.items() if n is not None}
    after_by_new = {smap.new_seg_base + 32 * i: s for i, s in enumerate(sa.segs)}

    def find(s_street_before):
        hit = cseg.get(ends(sb, s_street_before), [])
        assert len(hit) == 1, f"coarse record for street ends {ends(sb, s_street_before)}: {len(hit)} matches"
        return hit[0]

    # 1. remove the coarse copies of the removed street records
    gone = [find(s) for s in removed_before]
    for c in gone:
        tc.remove_seg(c)
    log(f"removed {len(gone)} coarse records (copies of the removed street records)")

    # 2. nodes: the old inner nodes (the ends that only removed records used) go, the moved node follows
    used_after = {absxy(sa, *n.xy) for n in sa.nodes5}
    old_nodes = {absxy(sb, *n.xy): n for n in sb.nodes5}
    drop = [p for p in old_nodes if p not in used_after and p in cnode]
    for p in drop:
        tc.remove_node(cnode.pop(p))
    log(f"removed {len(drop)} coarse nodes that have no street node any more")
    node_at = dict(cnode)
    new_nodes = [n for n in sa.nodes5 if absxy(sa, *n.xy) not in old_nodes]       # six ring nodes and the moved node
    for n in new_nodes:
        cn = Node(5, 0, 0, n.flags)
        cn.u, cn.v = ((absxy(sa, *n.xy)[0] - tc.frame.x0) >> VERTEX_SHIFT, (absxy(sa, *n.xy)[1] - tc.frame.y0) >> VERTEX_SHIFT)
        node_at[absxy(sa, *n.xy)] = cn
        tc.insert_node(cn, CLASS)
    log(f"added {len(new_nodes)} coarse nodes")

    def coarse_of(street_tile, n: Node) -> Node:
        return node_at[absxy(street_tile, *n.xy)]

    def adopt(c: Seg, s: Seg) -> None:
        """Make coarse record c a copy of street record s (fields up to +0x19, shape, end nodes)."""
        c.raw[:26] = s.raw[:26]
        for o in Seg.PTR:
            c.raw[o:o + 2] = b"\0\0"
        c.a, c.b = coarse_of(sa, s.a), coarse_of(sa, s.b)
        du = (sa.frame.x0 - tc.frame.x0) >> VERTEX_SHIFT
        dv = (sa.frame.y0 - tc.frame.y0) >> VERTEX_SHIFT
        c.shape = [struct.pack(">HHBB", struct.unpack_from(">H", e, 0)[0] + du, struct.unpack_from(">H", e, 2)[0] + dv,
                               e[4], e[5]) for e in s.shape]

    # 3. survivors whose ends or shape changed: the street records that were reoriented, and those at the moved node
    changed = 0
    for o, s_before in survivors.items():
        s_after = after_by_new[smap.seg_new[o]]
        if (ends(sb, s_before), [bytes(e) for e in s_before.shape]) != (ends(sa, s_after), [bytes(e) for e in s_after.shape]):
            hit = cseg.get(ends(sb, s_before), [])
            if len(hit) == 1:
                adopt(hit[0], s_after)
                changed += 1
    log(f"adopted the new geometry of {changed} surviving coarse records")

    # 4. the new street records
    fresh_street = [s for i, s in enumerate(sa.segs) if smap.new_order[i] is None]
    for k, s in enumerate(fresh_street):
        c = Seg(bytes(26), None)
        adopt(c, s)
        tc.insert_seg(c, CLASS, k)
    log(f"added {len(fresh_street)} coarse records")
    tc.normalize()
    bad = tc.check()
    assert not bad, bad
    new = tc.build()
    omap.finish(tc)
    (DATA / f"tile_{COARSE:#x}_redrawn.bin").write_bytes(new)
    room = blk.length * vol.sector_size
    enc = new[:8] + zlib.compress(new[8:], 9)
    assert zlib.decompress(enc[8:]) == new[8:]
    json.dump({"tile": COARSE, "fits": len(enc) <= room, "encoded": len(enc), "room": room, "offsets": omap.to_json()},
              open(DATA / "redraw_coarse.json", "w"))
    log(f"coarse tile: S4 {len(sb_segs)} -> {len(tc.segs)} records, S5 {n5_before} -> {len(tc.nodes5)} nodes; "
        f"zlib {len(enc)} bytes in {room}")
    log("wrote dataset/tile_0x5c58a51c_redrawn.bin, dataset/redraw_coarse.json")


if __name__ == "__main__":
    main()
