import struct

import pytest

from carin.parser import cf1
from carin.parser.cf1.core import BitWriter

TABLE = {0x05: 8, 0x3D: 52, 0x3A: 20, 0x3B: 4, 0x3C: 16, 0x3F: 24, 0x15: 6, 0x59: 4}
TYPES = (0x14, 0x15, 0x16, 0x1C, 0x1D, 0x1E)


def test_dispatch_matches_rr_db_pub():
    # RR bsw2 db_pub sub_002a48: all six types share the case at +0x2bc8 -> sub_004b88
    for t in TYPES:
        assert cf1.DECODERS[t] is cf1.decode_type14_16


def _prologue(btype, entries):
    p = bytearray(52)
    struct.pack_into(">IHBB", p, 0, (1000 << 8) | 1, btype, 1, 1)   # usize 1 -> PTRBITS 9
    for i, (off, cnt) in enumerate(entries):
        struct.pack_into(">HH", p, 8 + 4 * i, off, cnt)
    struct.pack_into(">4i", p, 0x20, 0, 0, 1 << 20, 1 << 20)
    struct.pack_into(">HH", p, 0x30, 1, 6)                         # 4-byte S3, shift 6
    return p


def _block(btype=0x1C):
    """S0 2 recs @52, S1 2 recs @60, S3 2 recs @100, e5 1 rec @108, text @112."""
    head = _prologue(btype, [(52, 1), (60, 1), (0, 0), (100, 2), (0, 0), (108, 1)])
    raw4 = bytes([8, 8, 4, 0])
    w = BitWriter()
    # pass 0x0e -- S0: code 7, draw 1, offset (PTRBITS-1) >> 1
    for code, draw, ptr in ((1, 0, 60), (0, 0, 100)):
        w.put(7, code); w.put(1, draw); w.put(8, ptr >> 1)
    # S1: name 9, S3 index 2 bits, flag + u32, X 32, Y 32
    w.put(9, 112); w.put(2, 0); w.put(1, 0); w.put(8, 5); w.put(32, 1000); w.put(32, 2000)
    w.put(9, 0); w.put(2, 2); w.put(1, 1); w.put(32, 0); w.put(32, 0); w.put(32, 0)
    # S3 delta: first absolute, then x +3 (flag 0), y -5 (flags 1,0), width raw4[2]
    w.put(16, 10); w.put(16, 20)
    w.put(1, 0); w.put(4, 3)
    w.put(1, 1); w.put(1, 0); w.put(4, 5)
    # text "ae\0" at 112..114
    w.put(9, 112); w.put(9, 114)
    for _ in range(6):
        w.put(5, 0)
    w.put(2, 0); w.put(1, 0)          # a
    w.put(2, 0); w.put(1, 1)          # e
    w.put(2, 1); w.put(2, 3)          # NUL
    # DB-REL >= 20: five widths, S1 +0x10 and a discarded field
    for width in (3, 4, 5, 6, 7):
        w.put(8, width)
    for _ in range(2):
        w.put(8, 0); w.put(1, 0); w.put(3, 1)
    # DB-REL >= 23: e5 (name, u8, 5 bits), S1 +0x12, two text flags
    w.put(1, 1); w.put(9, 112); w.put(1, 1); w.put(8, 7); w.put(1, 1); w.put(5, 3)
    w.put(8, 108 >> 1); w.put(8, 112 >> 1)
    w.put(1, 0); w.put(1, 0)
    raw = bytes(head) + raw4 + w.to_bytes()
    return raw + bytes(512 - len(raw))


def test_synthetic_block_all_passes():
    ctx = cf1.decode_ctx(_block(), TABLE, dbrel=34, decoder=cf1.decode_type14_16)
    d = ctx.dst
    assert list(d[52:60]) == [1, 0, 0, 60, 0, 0, 0, 100]
    s1 = struct.unpack_from(">HHIiiHH", d, 60)
    assert s1 == (112, 100, 5, 1000, 2000, 0, 108)
    assert struct.unpack_from(">HHIiiHH", d, 80) == (0, 108, 0, 0, 0, 0, 112)
    assert struct.unpack_from(">4H", d, 100) == (10, 20, 13, 15)
    assert struct.unpack_from(">HBB", d, 108) == (112, 7, 3)
    assert bytes(d[112:115]) == b"ae\0"
    assert ctx.texts == [(112, 114)]
    tail = ctx.bits.pos
    assert not any(ctx.src[ctx.bits.base + tail // 8 + 1:])


def test_passes_follow_db_rel():
    ctx = cf1.decode_ctx(_block(), TABLE, dbrel=22, decoder=cf1.decode_type14_16)
    assert struct.unpack_from(">H", ctx.dst, 60 + 0x12)[0] == 0      # pass 0x17 not run
    assert struct.unpack_from(">H", ctx.dst, 108)[0] == 0


def test_empty_section_is_not_read():
    # count 0: RR sub_004228 returns at +0x4280; the CC-93 port still decoded
    # one record at the entry's offset 0, over the header and descriptor
    head = _prologue(0x16, [(0, 0)] * 6)
    raw = bytes(head) + bytes(512 - len(head))
    ctx = cf1.decode_ctx(raw, TABLE, dbrel=34, decoder=cf1.decode_type14_16)
    assert bytes(ctx.dst[:52]) == bytes(head)
    assert ctx.texts == [(0, 0)]


def test_first_e5_record_cannot_inherit():
    raw = bytearray(_block())
    # e5 is the only section: its first flag bit (0) asks for a previous record
    for i in range(5):
        struct.pack_into(">HH", raw, 8 + 4 * i, 0, 0)
    struct.pack_into(">HH", raw, 8 + 20, 52, 1)
    raw[56:] = bytes(5) + bytes([0]) + bytes(len(raw) - 62)   # empty text, widths 0, flag 0
    with pytest.raises(cf1.Cf1Error):
        cf1.decode_ctx(bytes(raw), TABLE, dbrel=34, decoder=cf1.decode_type14_16)


def _tail_ctx(bits):
    from carin.parser.cf1.core import BitReader, Cf1Context
    dst = bytearray(52 + 3 * 16)
    struct.pack_into(">HH", dst, 8 + 8, 52, 2)          # S2: 2 records + terminator
    w = BitWriter()
    for width, value in bits:
        w.put(width, value)
    ctx = Cf1Context(table=TABLE, src=w.to_bytes() + bytes(4), dst=dst)
    ctx.bits = BitReader(ctx.src, 0)
    return ctx


def test_s2_tail_inherits_previous_value():
    from carin.parser.cf1.decoder_14 import _s2_tail
    ctx = _tail_ctx([(1, 1), (16, 196), (1, 0), (1, 1), (16, 0)])
    _s2_tail(ctx)
    assert [struct.unpack_from(">H", ctx.dst, 52 + 16 * k + 0x0E)[0] for k in range(3)] == [196, 196, 0]


def test_s2_tail_first_record_needs_a_value():
    from carin.parser.cf1.decoder_14 import _s2_tail
    with pytest.raises(cf1.Cf1Error):
        _s2_tail(_tail_ctx([(1, 0)]))
