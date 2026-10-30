import struct
import sys

import pytest

from carin.parser.iso import to_carin
from carin.parser.tmc import (RECORD_SIZE, decode_s12, parse_0x17, parse_0x18, split_table_id,
                              table_id)


def _block(records, table=0x11E, strings=b"\0A1\0Diemen\0A9\0", nxt=0, prv=0):
    """A 0x17 payload: header, descriptor, `records` (dicts) and the string blob."""
    off = 0x1C
    end = off + RECORD_SIZE * len(records)
    data = bytearray(end) + strings
    struct.pack_into(">HH", data, 8, off, len(records))
    struct.pack_into(">IIHHH", data, 0x0C, nxt, prv, table, records[0]["code"], records[-1]["code"])
    for i, rec in enumerate(records):
        r = off + RECORD_SIZE * i
        struct.pack_into(">HB", data, r, rec["code"], rec.get("bits", 2))
        data[r + 5] = rec.get("b5", 0)
        for o, key in ((0x06, "num"), (0x08, "road"), (0x0A, "name"), (0x0C, "name2")):
            if key in rec:                                  # string offset into the blob
                struct.pack_into(">H", data, r + o, end + rec[key])
        struct.pack_into(">4H", data, r + 0x0E, rec.get("parent", 0), rec.get("road_code", 0),
                         rec.get("prev", 0), rec.get("next", 0))
        struct.pack_into(">2H", data, r + 0x18, rec.get("first", 0), rec.get("last", 0))
        for o, (lon, lat) in zip((0x20, 0x38, 0x44, 0x4C, 0x54, 0x5C), rec.get("pts", ())):
            struct.pack_into(">II", data, r + o, *to_carin(lon, lat))
    return bytes(data)


def test_table_id_round_trip():
    assert table_id(1, 0xD) == 0x1D and split_table_id(0x11E) == (17, 0xE)
    assert split_table_id(0x0AC) == (10, 0xC)           # the UK table of the DVDs
    assert split_table_id(0x07C) == (7, 0xC)             # the published UK table


def test_parse_0x17_fields():
    payload = _block([
        {"code": 37003, "bits": 2, "num": 1, "name": 4, "name2": 11, "parent": 32427,
         "road_code": 33000, "prev": 37000, "next": 37004, "pts": [(4.9763, 52.3459)]},
        {"code": 40000, "bits": 1, "name": 4, "first": 37000, "last": 37004},
        {"code": 40001, "bits": 0, "name": 4},
    ], nxt=0xAB00, prv=0)
    hdr, locs = parse_0x17(payload)
    assert (hdr.next_block, hdr.prev_block, hdr.table, hdr.first_code, hdr.last_code) == (0xAB00, 0, 0x11E, 37003, 40001)
    p, line, area = locs
    assert (p.kind, line.kind, area.kind) == ("point", "line", "area")
    assert (p.road_number, p.road_name, p.name, p.name2) == ("A1", None, "Diemen", "A9")
    assert (p.parent, p.road, p.prev, p.next) == (32427, 33000, 37000, 37004)
    assert (line.first, line.last) == (37000, 37004)
    lon, lat = p.points[0]
    assert abs(lon - 4.9763) < 1e-4 and abs(lat - 52.3459) < 1e-4
    assert p.points[1:] == (None,) * 5 and p.table == 0x11E


def test_string_pointer_outside_the_string_area_is_an_error():
    payload = bytearray(_block([{"code": 1, "name": 4}]))
    struct.pack_into(">H", payload, 0x1C + 0x0A, 0x20)   # points into the record area
    with pytest.raises(ValueError):
        parse_0x17(bytes(payload))


def test_parse_0x18_drops_the_terminator():
    data = bytearray(0x40)
    struct.pack_into(">HHH", data, 8, 0x10, 3, 0x11E)
    for i, (b, first) in enumerate([(0xB7A530C, 1), (0xB7A5A0D, 5000), (0, 9001)]):
        struct.pack_into(">IHH", data, 0x10 + 8 * i, b, first, 0)
    assert parse_0x18(bytes(data)) == (0x11E, [(0xB7A530C, 1), (0xB7A5A0D, 5000)])


def test_decode_s12_splits_table_and_flag_bits():
    # 0x91E = Spanish table 0x11E with flag bit 1 set (tile 292280, Canary Islands)
    ref = decode_s12(struct.pack(">HHH", 6, 32553, 0x91E))
    assert (ref.direction, ref.code, ref.table, ref.flag_bits) == (6, 32553, 0x11E, 2)
    assert decode_s12(struct.pack(">HHH", 7, 4459, 0x1C7C)).table == 0x07C   # UK, LTN 7


def _loc(code, **kw):
    from carin.parser.tmc import Location
    f = dict(table=0x11E, code=code, kind="point", type_bits=2, unknown_05=0, road_number=None,
             road_name=None, name="x", name2=None, parent=0, road=0, prev=0, next=0, first=0, last=0,
             points=(None,) * 6)
    f.update(kw)
    return Location(**f)


def test_check_records_flags_broken_links_and_points():
    from collections import Counter
    from scripts.routing.check_tmc_locations import check_records
    good = [_loc(1, next=2), _loc(2, prev=1, parent=1)]
    fail = Counter()
    check_records(good, fail)
    assert not any(fail.values())
    bad = [_loc(1, next=2, parent=99), _loc(2, prev=7, points=((0.0, 0.0),) + (None,) * 5)]
    fail = Counter()
    check_records(bad, fail)
    assert fail["link parent not in table"] == 1
    assert fail["next.prev != this"] == 1
    assert fail["point outside the European range"] == 1


def test_check_link_distances_separates_a_real_link_from_a_random_one():
    from collections import Counter
    from scripts.routing.check_tmc_locations import check_link_distances
    fail = Counter()
    check_link_distances([0.5, 1.2, 1.5, 3.0, 9.0], [150.0, 260.0, 300.0, 640.0], fail)
    assert not any(fail.values())
    fail = Counter()
    check_link_distances([200.0, 260.0, 310.0], [150.0, 260.0, 300.0], fail)   # no nearer than random
    assert fail["median link distance too large"] and fail["link no nearer than random"]


class _FakeVolume:
    """Just enough of CarinVolume for check_tmc_locations.main (no 0x00 tiles)."""

    layout = {}

    def __init__(self, *_a, **_k):
        a = _block([{"code": 1, "name": 1, "next": 5}, {"code": 5, "name": 1, "prev": 1}], table=0x11E, nxt=0x200)
        b = _block([{"code": 9, "name": 1}], table=0x11E, prv=0x100)
        idx = bytearray(0x30)
        struct.pack_into(">HHH", idx, 8, 0x10, 3, 0x11E)
        for i, (blk, first) in enumerate([(0x100, 1), (0x200, 9), (0, 10)]):
            struct.pack_into(">IHH", idx, 0x10 + 8 * i, blk, first, 0)
        self.blocks = {0x100: (0x17, a), 0x200: (0x17, b), 0x300: (0x18, bytes(idx))}

    def calibrate(self):
        pass

    def walk(self):
        from types import SimpleNamespace
        return [SimpleNamespace(sector=bid >> 8, length=bid & 0xFF, type=t)
                for bid, (t, _) in self.blocks.items()]

    def block(self, sector):
        from types import SimpleNamespace
        return SimpleNamespace(payload=self.blocks[sector << 8][1])


def test_check_script_passes_a_consistent_disc_and_fails_a_broken_chain(monkeypatch, capsys):
    import scripts.routing.check_tmc_locations as chk
    monkeypatch.setattr(chk, "CarinVolume", _FakeVolume)
    monkeypatch.setattr(chk, "open_image", lambda p: None)
    monkeypatch.setattr(sys, "argv", ["check_tmc_locations", "disc"])
    assert chk.main() == 0
    assert "failures: none" in capsys.readouterr().out

    orig = _FakeVolume.__init__

    def broken(self, *a, **k):
        orig(self, *a, **k)
        t, blk = self.blocks[0x100]
        data = bytearray(blk)
        struct.pack_into(">I", data, 0x0C, 0)        # cut the chain after the first block
        self.blocks[0x100] = (t, bytes(data))
    monkeypatch.setattr(_FakeVolume, "__init__", broken)
    assert chk.main() == 1
    assert "0x17 chain does not cover all blocks" in capsys.readouterr().out
