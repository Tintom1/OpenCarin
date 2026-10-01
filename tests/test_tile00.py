"""Tile00: parse / build / edit of a decoded type 0x00 tile, and the offset map used to fix references to it.

The tile is made up (DB-REL 34 layout): three level groups, a few nodes and segments, no text, so the tests
need no disc.
"""
import struct

import pytest

from carin.parser import cf1
from carin.parser.cf1.constants import *
from carin.parser.cf1.tile00 import Node, Seg, Tile00, TileError, diff_graph
from carin.parser.refs import OffsetMap, patch_04

TABLE = {T_DESC_BASE: 8, T_REC_S6: 16, T_REC_S4: 32, T_TAIL_S4: 26, T_PROLOG: 116, T_REC_S7: 6,
         T_REC_S9: 8, T_REC_S5: 8, T_REC_S3: 4, T_REC_S11: 6, T_REC_S10: 8, T_REC_S12: 6,
         T_REC_S0: 10, T_REC_S13: 8, T_REC_S14: 4}
REC = {0: 10, 1: 10, 2: 10, 3: 4, 4: 32, 5: 8, 6: 16, 7: 6, 8: 4, 9: 8, 10: 8, 11: 6, 12: 6, 13: 8, 14: 4}


def made_up() -> bytes:
    """A small tile that follows the editing rules: classes 0 and 1, six nodes, five segments."""
    t = Tile00()
    t.table, t.tile_id, t.coarse, t.zero_empty = TABLE, 0x01234503, False, set()
    t.rec4, t.tail, t._rec = 32, 26, dict(REC)
    prolog = bytearray(116)
    struct.pack_into(">IHBB", prolog, 0, t.tile_id, 0, 7, 8)
    struct.pack_into(">4I", prolog, 68, 259_915_776, 228_184_064, 259_915_776 + 98_304, 228_184_064 + 98_304)
    t.prolog = bytes(prolog)
    t.passive = {0: [[0] * 5], 1: [[0] * 5], 2: [[0] * 5, [0] * 5], 14: []}
    t.raw_sections = {8: [], 9: [struct.pack(">IHH", 0x01234603, 0, 64)]}
    t.gaps = {11: b"\0\0", 12: b"\0\0"}
    t.blob, t.extra_sectors, t.s4_sentinel = b"abc\0", 0, bytes(32)
    n = [Node(5, u, v, 0x9000) for u, v in ((10, 10), (20, 10), (20, 20), (40, 40), (50, 40))]
    t.nodes5, t.nodes6, t.groups = n, [], [[3, 3], [2, 2]]

    def seg(a, b, cls, length):
        s = Seg(bytes(32), 26)
        s.raw[0x10], s.raw[0x0A] = cls, 0x0B
        s.set16(0x0C, length)
        s.a, s.b, s.name = n[a], n[b], 1
        s.shape = [struct.pack(">HHBB", n[a].u + 1, n[a].v + 1, 0, 0)]
        return s

    t.segs = [seg(0, 1, 0, 10), seg(1, 2, 0, 10), seg(0, 2, 0, 14), seg(2, 3, 1, 28), seg(3, 4, 1, 10)]
    t.segs[0].signs = [[0, None, 1]]
    t.segs[1].tmc = [struct.pack(">3H", 6, 7, 8)]
    t.rebuild_cycles()
    return t.build()


def test_null_relayout_is_identical_and_rules_hold():
    d = made_up()
    t = Tile00.parse(d, TABLE)
    assert t.build() == d
    t2 = Tile00.parse(d, TABLE)
    t2.normalize()
    assert t2.build() == d


def test_forced_shift_keeps_the_graph():
    d = made_up()
    t = Tile00.parse(d, TABLE)
    g0 = t.graph()
    for sec in (3, 4, 7):
        t.gaps[sec] = t.gaps.get(sec, b"") + bytes(6)
    grown = t.build()
    assert grown != d and len(grown) >= len(d)
    g1 = Tile00.parse(grown, TABLE).graph()
    assert diff_graph(g0, g1) == ["gaps"]


def test_add_and_remove_records_rewrites_every_pointer():
    d = made_up()
    t = Tile00.parse(d, TABLE)
    omap = OffsetMap.capture(t)
    first = t.segs[0]
    new_node = Node(5, 15, 30, 0x9000)
    t.insert_node(new_node, 1)
    s = Seg(first.raw, 26)
    s.raw[0x10], s.name = 1, 1
    s.a, s.b = new_node, t.segs[3].b
    s.shape = [struct.pack(">HHBB", 16, 31, 0, 0)] * 3
    t.insert_seg(s, 1, 0)
    t.remove_seg(first)
    t.normalize()
    t.finalize(s)                                                     # bearings first, then the cycles that depend on them
    t.rebuild_cycles()
    assert t.check() == []
    omap.finish(t)
    out = t.build()
    back = Tile00.parse(out, TABLE)
    assert back.check() == [] and back.graph() == t.graph()
    assert len(back.segs) == 5 and back.groups == [[2, 3], [3, 3]]
    # the removed record is gone from the map, the others moved with their position
    assert omap.seg_new[omap.seg_order[0]] is None and omap.seg_new[omap.seg_order[1]] is not None
    # encoder: the grown tile must still go through the CF=1 packer
    padded = out + bytes((-len(out)) % 512)
    enc = cf1.encode_type00(padded, TABLE, 34, 9, 512)
    assert cf1.decode_block(enc, TABLE, 34, subrel=9, sector_size=512) == padded


def test_check_reports_broken_rules():
    t = Tile00.parse(made_up(), TABLE)
    t.segs[0].a, t.segs[0].b = t.segs[0].b, t.segs[0].a              # start node no longer the lower (x, y)
    assert any("lower (x, y)" in m for m in t.check())
    t = Tile00.parse(made_up(), TABLE)
    t.nodes5[0], t.nodes5[1] = t.nodes5[1], t.nodes5[0]
    assert any("sorted" in m for m in t.check())
    t = Tile00.parse(made_up(), TABLE)
    t.segs[3].raw[0x10] = 0                                           # class 0 record in the class 1 group
    assert any("level group" in m for m in t.check())


def test_parse_refuses_a_tile_that_is_not_canonical():
    d = bytearray(made_up())
    struct.pack_into(">H", d, 8 + 4 * 5, 20000)                       # S5 starts somewhere else
    with pytest.raises(TileError):
        Tile00.parse(bytes(d), TABLE)


def test_offset_map_runs_and_redirects():
    t = Tile00.parse(made_up(), TABLE)
    omap = OffsetMap.capture(t)
    t.remove_seg(t.segs[1])
    t.normalize()
    omap.finish(t)
    b = omap.seg_base
    assert omap.run(b, 3) == (b, 2)                                   # records 0..2 lose the middle one: 0 and 2 -> 0, 1 (consecutive)
    assert omap.target(b + 32) in (b, b + 32 * 1)                     # removed record: nearest of the same street
    assert omap.run(b + 32, 1) is None


def test_patch_04_reorders_house_number_records():
    t = Tile00.parse(made_up(), TABLE)
    omap = OffsetMap.capture(t)
    t.remove_seg(t.segs[0])
    s = Seg(t.segs[0].raw, 26)
    s.a, s.b, s.name = t.segs[0].a, t.segs[0].b, 1
    t.insert_seg(s, 1)
    omap.finish(t)
    recs = [struct.pack(">5H", 10 * i + 1, 0x7FFF, 10 * i + 3, 0x7FFF, 2) for i in range(5)]
    payload = bytearray(8 + 8 + 10 * 5 + 64)
    struct.pack_into(">HH", payload, 8, 0x10, 5)
    payload[0x10:0x10 + 50] = b"".join(recs)
    out, notes = patch_04(bytes(payload), omap)
    assert len(out) == len(payload) and "5 -> 5 records" in notes[0]
    got = [out[0x10 + 10 * i: 0x10 + 10 * i + 10] for i in range(5)]
    empty = struct.pack(">5H", 0x7FFF, 0x7FFF, 0x7FFF, 0x7FFF, 0)
    assert recs[0] not in got and empty in got
    assert [r for r in got if r != empty] == recs[1:]
