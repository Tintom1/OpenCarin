import struct
import sys

import pytest

from carin.parser.carinet import UNIT, read_carinet

# event code -> (key bits, attribute word, tag): code 2 has quantifier 4 and update class 1
EVENTS = {1: (4, 0x029F, "A50"), 2: (4, 0x0294, "A2.A1D"), 5: (4, 0x2A1F, "C58")}
TEXTS = {1: {1: "traffic problem", 2: "queuing traffic (with average speeds Q)", 5: "service area closed"},
         2: {1: "Verkehrsbehinderung", 2: "stockender Verkehr", 5: "Rastplatz gesperrt"}}


def _blk(block_id, typ, off, nxt, prv, extra=0):
    b = bytearray(UNIT)
    struct.pack_into(">IHH", b, 0, block_id, typ, 0)
    struct.pack_into(">HH", b, 8, off, 0)
    struct.pack_into(">IIH", b, 0x0C, nxt, prv, extra)
    return b


def _strings(b, start, strs):
    offs = []
    for s in strs:
        offs.append(start)
        b[start:start + len(s) + 1] = s.encode("latin-1") + b"\0"
        start += len(s) + 1
    return offs


def _event_block(block_id, codes, nxt, prv):
    b = _blk(block_id, 0x64, 0x14, nxt, prv)
    struct.pack_into(">H", b, 10, len(codes))
    offs = _strings(b, 0x14 + 6 * len(codes), [EVENTS[c][2] for c in codes])
    for i, (c, o) in enumerate(zip(codes, offs)):
        struct.pack_into(">HHH", b, 0x14 + 6 * i, EVENTS[c][0] << 11 | c, EVENTS[c][1], o)
    return b


def _text_block(block_id, group, codes, nxt, prv):
    b = _blk(block_id, 0x65, 0x18, nxt, prv, group << 8)
    struct.pack_into(">H", b, 10, len(codes))
    offs = _strings(b, 0x18 + 4 * len(codes), [TEXTS[group][c] for c in codes])
    for i, (c, o) in enumerate(zip(codes, offs)):
        struct.pack_into(">HH", b, 0x18 + 4 * i, c, o)
    return b


def make_carinet(limit_error=False):
    """Root (2 sectors), 0x64 blocks at sectors 2 and 3, 0x65 blocks at sectors 4, 5 (set 1) and 6 (set 2)."""
    ev_a, ev_b = 0x201, 0x301
    t = [0x401, 0x501, 0x601]
    out = bytearray(2 * UNIT)
    struct.pack_into(">IH", out, 0, 2, 0x66)
    struct.pack_into(">HHHHHH", out, 8, 0x1C, 2, 0x34, 3, 0, 0)
    for i, (bid, limit) in enumerate([(ev_a, 2), (ev_b, 5), (0, 0x7FF)]):
        struct.pack_into(">IHH", out, 0x1C + 8 * i, bid, limit, 0)
    for i, (bid, limit, grp) in enumerate([(t[0], 2, 1), (t[1], 5, 1), (t[2], 5, 2)]):
        if limit_error and i == 0:
            limit = 3
        struct.pack_into(">IHBB", out, 0x34 + 8 * i, bid, limit, grp, 0)
    out += _event_block(ev_a, [1, 2], ev_b, 0) + _event_block(ev_b, [5], 0, ev_a)
    out += _text_block(t[0], 1, [1, 2], t[1], 0) + _text_block(t[1], 1, [5], t[2], t[0])
    out += _text_block(t[2], 2, [1, 2, 5], 0, t[1])
    return bytes(out)


def test_read_carinet_decodes_events_and_texts():
    c = read_carinet(make_carinet())
    assert [(b.block_id, b.limit, b.group) for b in c.blocks] == [(0x401, 2, 1), (0x501, 5, 1), (0x601, 5, 2)]
    assert sorted(c.events) == [1, 2, 5]
    ev = c.events[2]
    assert (ev.key_bits, ev.tag, ev.quantifier, ev.update_class) == (4, "A2.A1D", 4, 1)
    assert c.events[1].quantifier is None                    # low nibble 0xF
    assert c.events[5].update_class == 0x2A1F >> 9 & 0x3F
    # key bits 4 = one direction, event; attrs 0x0294 = quantifier 4, duration D (bits 4-6 = 1), urgency U
    assert (ev.nature, ev.directionality, ev.duration, ev.urgency) == ("event", 1, "D", "U")
    assert c.phrase(1, 2) == "queuing traffic (with average speeds Q)"
    assert c.phrase(2, 5) == "Rastplatz gesperrt" and c.phrase(3, 1) is None


def test_event_attribute_word_decodes_nature_duration_urgency():
    from carin.parser.carinet import Event
    # key bits 9 = both directions, forecast; attrs: quantifier 7, duration "(D)", urgency "U", update class 39
    e = Event(5, 9, 39 << 9 | 1 << 7 | 2 << 4 | 7, "T")
    assert (e.nature, e.directionality, e.quantifier, e.duration, e.urgency, e.update_class) == \
        ("forecast", 2, 7, "(D)", "U", 39)
    s = Event(7, 2, 1 << 9 | 0xF, "")              # key bits 2 = silent, no direction, no quantifier, no duration
    assert (s.nature, s.directionality, s.quantifier, s.duration) == ("silent", 0, None, None)


def test_read_carinet_rejects_a_foreign_file():
    with pytest.raises(ValueError):
        read_carinet(bytes(2048))


def test_check_accepts_a_consistent_file_and_flags_a_wrong_limit():
    from scripts.routing.check_carinet import check
    fail, rep = check(make_carinet())
    assert not any(fail.values()) and rep["events"] == 3 and sorted(rep["sets"]) == [1, 2]
    assert rep["sets"][2]["quantifier_without_Q"] == 1       # the German phrase has no Q
    fail, _ = check(make_carinet(limit_error=True))
    assert fail["0x65 last code != limit"] == 1


def test_main_prints_and_returns_the_failure_state(tmp_path, monkeypatch, capsys):
    import scripts.routing.check_carinet as chk
    path = tmp_path / "CARINET"
    path.write_bytes(make_carinet())
    monkeypatch.setattr(sys, "argv", ["check_carinet", str(path)])
    assert chk.main() == 0
    assert "failures: none" in capsys.readouterr().out
