"""Synthetic-tile tests for carin.export (no disc needed)."""
import sqlite3
import struct
import xml.etree.ElementTree as ET

from carin.export import build_graph, parse_tile
from carin.export.readers import read_gpkg
from carin.export.router import Router
from carin.export.writers import write_csv, write_gpkg, write_osm_xml
from carin.parser.iso import to_carin


TABLE = {0x05: 8, 0x06: 16, 0x08: 32, 0x09: 0x1C, 0x0C: 6, 0x10: 8, 0x14: 8, 0x40: 8}
S2, S4, S5, S6, S7, S10 = 200, 256, 400, 440, 520, 600


def make_tile(sector, x0, y0, side, segs, nodes, edge_nodes=(), s10=()):
    """segs: list of dict(a, b, shape[(u,v)], speed, form, length, cls, junc, s10=(lo,hi))."""
    data = bytearray(1024)
    secs = {2: (S2, 1), 4: (S4, len(segs)), 5: (S5, len(nodes)), 6: (S6, len(edge_nodes)),
            7: (S7, sum(len(s["shape"]) for s in segs)), 10: (S10, len(s10))}
    for i in range(15):
        struct.pack_into(">HH", data, 8 + 4 * i, *secs.get(i, (0, 0)))
    struct.pack_into(">4I", data, 8 + 60, x0, y0, x0 + side, y0 + side)
    struct.pack_into(">H", data, S2, 700)
    data[700:710] = b"main road\x00"
    for i, (u, v) in enumerate(nodes):
        struct.pack_into(">HHHH", data, S5 + 8 * i, u, v, 0, 0xC000)
    for i, (u, v, bid, off) in enumerate(edge_nodes):
        struct.pack_into(">HHHHIH", data, S6 + 16 * i, u, v, 0, 0xE000, bid, off)
    ptr, n_s10 = S7, 0
    for i, s in enumerate(segs):
        base = S4 + 32 * i
        struct.pack_into(">HHH", data, base, s["a"], s["b"], ptr)
        data[base + 0x0A] = s.get("speed", 11)
        data[base + 0x0B] = s.get("form", 0xC)
        struct.pack_into(">H", data, base + 0x0C, s["length"])
        data[base + 0x10] = s.get("cls", 4)
        data[base + 0x11] = s.get("junc", 0x20)
        lo = S10 + 8 * n_s10
        struct.pack_into(">H", data, base + 0x12, lo)
        n_s10 += s.get("n10", 0)
        struct.pack_into(">H", data, base + 0x1C, S2)
        for u, v in s["shape"]:
            struct.pack_into(">HH", data, ptr, u, v)
            ptr += 6
    for i, (bid, off, flag) in enumerate(s10):
        struct.pack_into(">IHH", data, S10 + 8 * i, bid, off, flag)
    return bytes(data)


def two_tiles():
    side = 64 * 1000
    x0, y0 = to_carin(5.0, 51.0)
    # tile A: A0 -(seg0)- A1 -(seg1)- E_A (edge node); tile B: E_B -(seg0)- B1
    na = S5, S5 + 8, S6
    A = make_tile(100, x0, y0, side,
                  [dict(a=na[0], b=na[1], shape=[(100, 100)], length=300, direction=0),
                   dict(a=na[1], b=na[2], shape=[(200, 100)], length=400, form=0x1C)],  # forward-only
                  nodes=[(50, 100), (150, 100)], edge_nodes=[(1000, 100, 200 << 8 | 1, S6)])
    B = make_tile(200, x0 + side, y0, side,
                  [dict(a=S6, b=S5, shape=[(500, 100)], length=500)],
                  nodes=[(900, 100)], edge_nodes=[(0, 100, 100 << 8 | 1, S6)])
    return A, B


def test_parse_and_join():
    A, B = two_tiles()
    ta, tb = parse_tile(100, A, TABLE), parse_tile(200, B, TABLE)
    assert ta and tb and len(ta.edges) == 2 and len(tb.edges) == 1
    assert ta.edges[0].name == "main road" and ta.edges[0].length_m == 300
    g = build_graph([ta, tb])
    # A's edge node and B's edge node are twins -> one node; total 2 (A) + 1 (shared) + 1 (B) = 4
    assert g.stats["nodes"] == 4 and g.stats["edges"] == 3
    assert g.edges[1].oneway == "forward" and g.edges[1].v == g.edges[2].u
    assert g.stats["twin_links"] == 2 and g.stats["twin_outside_window"] == 0
    assert g.stats["twin_position_mismatch"] == 0


def test_restriction_resolution():
    side = 64 * 1000
    x0, y0 = to_carin(5.0, 51.0)
    segs = [dict(a=S5, b=S5 + 8, shape=[(100, 100)], length=100, n10=1),
            dict(a=S5 + 8, b=S5 + 16, shape=[(200, 100)], length=100)]
    t = make_tile(100, x0, y0, side, segs, nodes=[(50, 100), (150, 100), (250, 100)],
                  s10=[(100 << 8 | 1, S4 + 32, 1)])         # seg0 -> seg1 at seg0's end node
    g = build_graph([parse_tile(100, t, TABLE)])
    assert len(g.restrictions) == 1
    r = g.restrictions[0]
    assert (r.from_edge, r.to_edge, r.kind) == (0, 1, "no_turn") and r.via_node == g.edges[0].v
    assert Router(g).route(g.edges[0].u, g.edges[1].v) is None      # banned turn, no alternative
    assert Router(g, respect_restrictions=False).route(g.edges[0].u, g.edges[1].v)


def test_writers_and_router(tmp_path):
    A, B = two_tiles()
    g = build_graph([parse_tile(100, A, TABLE), parse_tile(200, B, TABLE)])
    write_gpkg(g, str(tmp_path / "t.gpkg"))
    write_csv(g, str(tmp_path / "t"))
    write_osm_xml(g, str(tmp_path / "t.osm"))
    assert sqlite3.connect(tmp_path / "t.gpkg").execute("SELECT count(*) FROM edges").fetchone()[0] == 3
    g2 = read_gpkg(str(tmp_path / "t.gpkg"))
    assert len(g2.edges) == 3 and g2.edges[1].direction == 1
    root = ET.parse(tmp_path / "t.osm").getroot()
    assert len(root.findall("way")) == 3 and root.find("way/tag[@k='oneway']") is not None
    # forward route works across the tile edge; reverse is blocked by the one-way segment
    r = Router(g2)
    a_first, b_last = g2.edges[0].u, g2.edges[2].v
    assert r.route(a_first, b_last) is not None
    assert r.route(b_last, a_first) is None


def _graph_with(speed, cls=0, built=False):
    side = 64 * 1000
    x0, y0 = to_carin(5.0, 51.0)
    segs = [dict(a=S5, b=S5 + 8, shape=[(100, 100)], length=1000, speed=speed, cls=cls),
            dict(a=S5 + 8, b=S5 + 16, shape=[(200, 100)], length=1000, speed=speed, cls=cls)]
    if built:
        for s in segs:
            s["speed"] = speed | 0x80
    t = make_tile(100, x0, y0, side, segs, nodes=[(50, 100), (150, 100), (250, 100)])
    return build_graph([parse_tile(100, t, TABLE)])


def test_speed_category_zero_means_unknown_not_slow():
    from carin.export.cost import CostModel
    g = _graph_with(speed=0, cls=0)                         # a motorway without stored speed
    m = CostModel()
    assert g.edges[0].speed_code == 0
    assert m.speed_kmh(g.edges[0]) == m.unknown_kmh["motorway"] == 100.0
    g = _graph_with(speed=22, cls=1)                        # stored 22 * 4 = 88 km/h
    assert m.speed_kmh(g.edges[0]) == 88.0


def test_divisor_and_model_file_round_trip(tmp_path):
    from carin.export.cost import CostModel, bucket
    g = _graph_with(speed=11, cls=2, built=True)            # 44 km/h on a built-up main road
    e = g.edges[0]
    assert bucket(e) == "main_built" and e.built_up
    m = CostModel()
    m.divisor["main_built"] = 2.0
    m.junction_s = 7.5
    m.unknown_kmh["motorway"] = 90.0
    m.save(str(tmp_path / "m.json"))
    m2 = CostModel.load(str(tmp_path / "m.json"))
    assert m2.speed_kmh(e) == 22.0 and m2.junction_s == 7.5 and m2.unknown_kmh["motorway"] == 90.0


def test_junction_delay_is_charged_where_three_or_more_segments_meet():
    from carin.export.cost import CostModel
    side = 64 * 1000
    x0, y0 = to_carin(5.0, 51.0)
    # T junction: A - J - B in a line, C hanging off J
    segs = [dict(a=S5, b=S5 + 8, shape=[(100, 100)], length=1000, speed=11, cls=3),
            dict(a=S5 + 8, b=S5 + 16, shape=[(200, 100)], length=1000, speed=11, cls=3),
            dict(a=S5 + 8, b=S5 + 24, shape=[(150, 200)], length=1000, speed=11, cls=3)]
    t = make_tile(100, x0, y0, side, segs, nodes=[(50, 100), (150, 100), (250, 100), (150, 300)])
    g = build_graph([parse_tile(100, t, TABLE)])
    src, dst = g.edges[0].u, g.edges[1].v
    base = Router(g, model=CostModel()).route(src, dst)["time_s"]
    delayed = Router(g, model=CostModel(junction_s=30.0)).route(src, dst)["time_s"]
    assert abs((delayed - base) - 30.0) < 1e-6              # one junction node on the way

    # without the third segment J is an ordinary through node: no delay
    t2 = make_tile(100, x0, y0, side, segs[:2], nodes=[(50, 100), (150, 100), (250, 100)])
    g2 = build_graph([parse_tile(100, t2, TABLE)])
    assert Router(g2, model=CostModel(junction_s=30.0)).route(g2.edges[0].u, g2.edges[1].v)["time_s"] \
        == Router(g2, model=CostModel()).route(g2.edges[0].u, g2.edges[1].v)["time_s"]
