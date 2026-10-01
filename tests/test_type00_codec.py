import random
import struct

import pytest

from carin.parser import cf1
from carin.parser.cf1.constants import *
from carin.parser.cf1.decoder_00 import _layout_end

# RECORD_SIZE_TABLE entries used by the 0x00 codec, as on CD-ID 2952 (DB-REL 22)
# and CD-ID 21594 (DB-REL 34)
TABLES = {
    22: {T_DESC_BASE: 8, T_REC_S6: 16, T_REC_S4: 30, T_TAIL_S4: 24, T_PROLOG: 112, T_REC_S7: 6,
         T_REC_S9: 8, T_REC_S5: 8, T_REC_S3: 4, T_REC_S11: 6, T_REC_S10: 8, T_REC_S12: 6,
         T_REC_S0: 6, T_REC_S13: 8},
    34: {T_DESC_BASE: 8, T_REC_S6: 16, T_REC_S4: 32, T_TAIL_S4: 26, T_PROLOG: 116, T_REC_S7: 6,
         T_REC_S9: 8, T_REC_S5: 8, T_REC_S3: 4, T_REC_S11: 6, T_REC_S10: 8, T_REC_S12: 6,
         T_REC_S0: 10, T_REC_S13: 8, T_REC_S14: 4},
}
REC = {0: T_REC_S0, 1: T_REC_S0, 2: T_REC_S0, 3: T_REC_S3, 4: T_REC_S4, 5: T_REC_S5, 6: T_REC_S6,
       7: T_REC_S7, 9: T_REC_S9, 10: T_REC_S10, 11: T_REC_S11, 12: T_REC_S12, 13: T_REC_S13,
       14: T_REC_S14}
SECTOR_SIZE = 2048


def _tile(dbrel: int, seed: int) -> bytes:
    """A decoded tile the decoder itself produced: a made-up section layout and random bits,
    with the name text replaced by known strings."""
    T = TABLES[dbrel]
    rnd = random.Random(seed)
    prolog = bytearray(T[T_PROLOG])
    struct.pack_into(">IHBB", prolog, 0, 0x1234503, 0x00, 1, 3)
    at = len(prolog)
    for idx in range(15):
        if idx == 8 or idx not in REC or REC[idx] not in T:
            continue
        n = rnd.randint(1, 12)
        struct.pack_into(">HH", prolog, T[T_DESC_BASE] + 4 * idx, at, n)
        at += (n + (1 if idx in (3, 4) else 0)) * T[REC[idx]]
    widths = bytes([rnd.randint(2, 9), rnd.randint(2, 9)])
    raw = bytes(prolog) + widths
    for idx in (3, 9, 10, 12):
        off, n = struct.unpack_from(">HH", prolog, T[T_DESC_BASE] + 4 * idx)
        raw += rnd.randbytes((n + (idx == 3)) * T[REC[idx]])
    raw += rnd.randbytes(3 * SECTOR_SIZE - len(raw))
    dec = bytearray(cf1.decode_block(raw, T, dbrel, subrel=8, sector_size=SECTOR_SIZE))
    # Random bits can leave a first record's pointers unwritten (0), which no disc does and the
    # encoder refuses (it always writes first records): give every section 4 pointer a real target.
    ent = lambda i: struct.unpack_from(">HH", dec, T[T_DESC_BASE] + 4 * i)
    s4_off, s4_n = ent(4)
    rec, tail = T[T_REC_S4], T[T_TAIL_S4]
    targets = [(0x04, 7, T_REC_S7, 1), (0x12, 10, T_REC_S10, 1), (0x14, 12, T_REC_S12, 1),
               (tail + 4, 11, T_REC_S11, 1), (tail, 2, T_REC_S0, 0), (0x16, 13, T_REC_S13, 1)]
    for r in range(s4_n + 1):
        for fld, idx, key, plus in targets:
            if r == s4_n and fld == tail:
                continue                          # the sentinel has no s2 pointer
            off, n = ent(idx)
            struct.pack_into(">H", dec, s4_off + r * rec + fld, off + rnd.randrange(n + plus) * T[key])
    start = _layout_end(bytes(dec), T, dbrel)
    blob = "high street\0the green\0ch\xe2teau\0m62\0".encode("latin-1")
    dec[start:] = blob + bytes(len(dec) - start - len(blob))
    return bytes(dec)


@pytest.mark.parametrize("dbrel", [22, 34])
@pytest.mark.parametrize("seed", range(20))
def test_type00_roundtrip(dbrel, seed):
    T = TABLES[dbrel]
    dec = _tile(dbrel, seed)
    raw = cf1.encode_type00(dec, T, dbrel, subrel=8, sector_size=SECTOR_SIZE)
    assert len(raw) <= len(dec)
    assert cf1.decode_block(raw, T, dbrel, subrel=8, sector_size=SECTOR_SIZE)[4:] == dec[4:]


def test_type00_rejects_odd_even_field():
    T = TABLES[22]
    dec = bytearray(_tile(22, 0))
    e4_off = struct.unpack_from(">H", dec, T[T_DESC_BASE] + 16)[0]
    dec[e4_off + 1] |= 1                  # S4 +0 is carried as g(pb - 1) << 1
    with pytest.raises(cf1.Cf1Error):
        cf1.encode_type00(bytes(dec), T, 22, subrel=8, sector_size=SECTOR_SIZE)


@pytest.mark.parametrize("dbrel", [22, 34])
def test_type00_blob_ends_on_the_closing_nul(dbrel):
    # the firmware's buffer is not zeroed: the last name's NUL must be in the stream
    T = TABLES[dbrel]
    dec = _tile(dbrel, 1)
    raw = cf1.encode_type00(dec, T, dbrel, subrel=8, sector_size=SECTOR_SIZE)
    ctx = cf1.decode_ctx(raw, T, dbrel, subrel=8, sector_size=SECTOR_SIZE)
    assert ctx.texts[0][1] == len(dec.rstrip(b"\0"))
