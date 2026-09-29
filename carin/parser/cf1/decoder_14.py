"""CF=1 decoder for the scale-layer blocks 0x14, 0x15, 0x16, 0x1C, 0x1D, 0x1E.

Transcribed from the RoadRunner firmware that reads the DVDs: module `db_pub`
of `/V_2/RR/0101/BMWC01S/app_sw/bsw2` (offsets are inside the module). The
CF=1 dispatcher `sub_002a48` sends all six types to `sub_004b88`
(`scripts/firmware/rr_cf1_dispatch.py`), which calls the section decoder
`sub_004228(dst, entry, recsize, kind, pass)` once per section and pass.

The earlier port of CC-93 `pbp+0x46aa` stopped after the first pass and read
one record from sections whose count is 0; see docs/carindb/04-cf1-codec.md.
"""
from .core import *
from .constants import *
from .decoder_00 import dec_text
import struct

# sub_004228 `kind` argument: one per section layout
KIND_S0, KIND_S1, KIND_S2 = 0x80, 0x7F, 0x81
KIND_S3_ABS, KIND_S3_DELTA = 0xAE, 0xAC
KIND_E4, KIND_E5 = 0x17, 0x10
# sub_004228 `pass` argument, compared against DB-REL in sub_004b88
PASS_BASE, PASS_20, PASS_23 = 0x0E, 0x14, 0x17


class _State:
    """Values sub_004b88 keeps in the global data area for sub_004228."""

    def __init__(self, raw4: bytes, pb_s3: int, s3_rec: int):
        self.raw4 = raw4          # gp-0x6c04..-0x6c01, copied raw before the bitstream
        self.pb_s3 = pb_s3        # gp-0x6c08, bits_needed(e3.count + 1)
        self.s3_rec = s3_rec      # 0x18(sp) of sub_004228: 8 or 4
        self.w5 = b"\0" * 5       # gp-0x6c00..-0x6bfc, five getbits(8) (pass 0x14)


def s3_record_size(dst, table) -> int:
    """S3 record size: 8 if u16[T[0x05] + T[0x3f] + 0x10] == 0 else 4 (RR +0x42e0, +0x4cf0)."""
    off = table[T_DESC_BASE] + table[T_S3_DISP_141516] + 0x10
    return 8 if struct.unpack_from(">H", dst, off)[0] == 0 else 4


def _flag_or(ctx: Cf1Context, width: int) -> int:
    """getbits(1) ? getbits(16) : getbits(width) — used by passes 0x14 (RR +0x46ec, +0x4880)."""
    return ctx.g(16) if ctx.g(1) else ctx.g(width)


def _section(ctx: Cf1Context, idx: int, rec: int, kind: int, pas: int, st: _State) -> None:
    """sub_004228 — decode one pass over section `idx`.

    Sections 0, 1, 2 hold count + 1 records (the last is a terminator), the
    others count records (RR +0x4288..0x42dc). A section with count 0 is not
    read at all (RR +0x4280).
    """
    e = ctx.entry(idx)
    if e.count == 0:
        return
    last = (e.off + (e.count - 1) * rec) & 0xFFFF
    if kind in (KIND_S0, KIND_S1, KIND_S2):
        last = (last + rec) & 0xFFFF
    pb = ctx.ptrbits
    e3_off = ctx.entry(3).off
    prev_s3 = prev_e5 = None
    cur = e.off
    while cur <= last:
        if kind == KIND_S3_ABS:                       # +0x437c
            ctx.l(cur, ctx.g(32))
            ctx.l(cur + 4, ctx.g(32))
        elif kind == KIND_S3_DELTA:                   # +0x43b4
            if cur == e.off:
                ctx.w(cur, ctx.g(16))
                ctx.w(cur + 2, ctx.g(16))
            else:
                for f in (0, 2):
                    prev = ctx.rw(prev_s3 + f)
                    if ctx.g(1):
                        v = ctx.g(16) if ctx.g(1) else prev - ctx.g(st.raw4[2])
                    else:
                        v = prev + ctx.g(st.raw4[2])
                    ctx.w(cur + f, v)
            prev_s3 = cur
        elif kind == KIND_S0:                         # +0x4544
            ctx.b(cur, ctx.g(7))
            ctx.b(cur + 1, ctx.g(1))
            ctx.w(cur + 2, ctx.g(pb - 1) << 1)
        elif kind == KIND_S1:
            if pas == PASS_BASE:                      # +0x45a8
                ctx.w(cur, ctx.g(pb))
                ctx.w(cur + 2, e3_off + ctx.g(st.pb_s3) * st.s3_rec)
                ctx.l(cur + 4, ctx.g(32 if ctx.g(1) else st.raw4[1]))
                ctx.l(cur + 8, ctx.g(32))
                ctx.l(cur + 12, ctx.g(32))
            elif pas == PASS_20:                      # +0x46ac
                ctx.w(cur + 0x10, ctx.g(pb - 1) << 1)
                _flag_or(ctx, st.w5[0])               # read, not stored
            elif pas == PASS_23:                      # +0x4728
                ctx.w(cur + 0x12, ctx.g(pb - 1) << 1)
        elif kind == KIND_S2:
            if pas == PASS_BASE:                      # +0x4764
                ctx.w(cur, ctx.g(pb))
                ctx.w(cur + 2, e3_off + ctx.g(st.pb_s3) * st.s3_rec)
                ctx.l(cur + 4, ctx.g(32 if ctx.g(1) else st.raw4[0]))
            elif pas == PASS_20:                      # +0x483c
                ctx.w(cur + 8, ctx.g(pb - 1) << 1)
                ctx.w(cur + 0x0A, _flag_or(ctx, st.w5[1]))
            elif pas == PASS_23:                      # +0x48d8
                ctx.w(cur + 0x0C, ctx.g(pb - 1) << 1)
        elif kind == KIND_E4 and pas == PASS_20:      # +0x4914
            for f in range(3):
                ctx.w(cur + 2 * f, _flag_or(ctx, st.w5[2 + f]))
        elif kind == KIND_E5 and pas == PASS_23:      # +0x4a58
            # the firmware's "previous record" pointer starts at address 0
            # (+0x4284); a first record that inherits a field has no source.
            for off, width, size in ((0, pb, 2), (2, 8, 1), (3, 5, 1)):
                if ctx.g(1):
                    v = ctx.g(width)
                elif prev_e5 is None:
                    raise Cf1Error(f"e5 record at {cur}: first record inherits +{off}")
                else:
                    v = ctx.rw(prev_e5 + off) if size == 2 else ctx.dst[prev_e5 + off]
                (ctx.w if size == 2 else ctx.b)(cur + off, v)
            prev_e5 = cur
        cur = (cur + rec) & 0xFFFF


def _s2_tail(ctx: Cf1Context) -> None:
    """S2 +0x0e: the stream's last pass. NOT in the RR firmware; derived from the data.

    RR 0101 `sub_004b88` returns after the two text flags (+0x5024) and never
    writes S2 +0x0e, yet plain blocks carry a value there. On DB-REL 34 packed
    blocks, bits follow the last text flag exactly when S2 is non-empty, and
    reading, for each of the count + 1 S2 records, `getbits(1) ? getbits(16)
    : previous value` consumes every remaining set bit (oracle_14_16.py `pad`).
    The first record always carries its value; an explicit value never
    repeats the previous one, and the terminator ends at 0, as on plain blocks.
    """
    e = ctx.entry(2)
    if e.count == 0:
        return
    rec = ctx.T(T_REC_S2_141516)
    prev = None
    for k in range(e.count + 1):
        cur = e.off + k * rec
        if ctx.g(1):
            prev = ctx.g(16)
        elif prev is None:
            raise Cf1Error(f"S2 record at {cur}: first record inherits +0x0e")
        ctx.w(cur + 0x0E, prev)


def sections_end(ctx: Cf1Context) -> int:
    """First byte past the last non-empty record section (where the text starts)."""
    t = ctx.table
    recs = [t[T_REC_S0_141516], t[T_REC_S1_141516], t[T_REC_S2_141516],
            s3_record_size(ctx.dst, t), t[T_REC_E4_141516]]
    if ctx.dbrel >= 0x17:           # section 5 and T[0x59] exist from DB-REL 23 on
        recs.append(t[T_REC_E5_141516])
    hi = t[T_PROLOG_141516]
    for i, rec in enumerate(recs):
        e = ctx.entry(i)
        if e.count:
            hi = max(hi, e.off + (e.count + (1 if i < 3 else 0)) * rec)
    return hi


def decode_type14_16(ctx: Cf1Context) -> None:
    """RR db_pub sub_004b88 — BLOCK_TYPE 0x14, 0x15, 0x16, 0x1C, 0x1D, 0x1E (CF=1).

    Raw, before the bitstream:
      T[0x3d] bytes  prologue: header, six-entry descriptor, bbox, 0x30..0x33
      4 bytes        raw4: [0] S2 +4 width, [1] S1 +4 width, [2] S3 delta width
    Bitstream (MSB first):
      pass 0x0e      S0, S1, S2, S3; text
      DB-REL >= 20   5 x getbits(8) widths; e4; S1 +0x10; S2 +0x08/+0x0a
      DB-REL >= 23   e5; S1 +0x12; S2 +0x0c; if getbits(1): text; if getbits(1): text
      DB-REL > 23    S2 +0x0e (not in the firmware; see _s2_tail)

    Record layouts (bytes):
      S0 (T[0x3b]=4)  +0 u8 category (7 bits), +1 u8 draw flag, +2 u16 S1/S2 offset
      S1 (T[0x3a]=20) +0 name, +2 S3 offset, +4 u32, +8 i32 X, +12 i32 Y,
                      +0x10 u16 (always 0 on plain blocks), +0x12 e5 offset
      S2 (T[0x3c]=16) +0 name, +2 S3 offset, +4 u32, +8 e4 offset, +0x0a u16,
                      +0x0c e5 offset, +0x0e u16 (_s2_tail)
      S3              8 B absolute i32 X, Y, or 4 B u16 local x, y (delta coded)
      e4 (T[0x15]=6)  3 x u16
      e5 (T[0x59]=4)  +0 name, +2 u8, +3 u8 (5 bits)
    """
    t = ctx.table
    ctx.copy_raw(0, t[T_PROLOG_141516])                       # +0x4bac
    e3_count = struct.unpack_from(">H", ctx.dst, t[T_DESC_BASE] + 14)[0]
    st = _State(raw4=ctx.copy_raw(-1, 4),                     # +0x4c00
                pb_s3=bits_needed(e3_count + 1),              # +0x4bd4
                s3_rec=s3_record_size(ctx.dst, t))
    ctx.bits_init()                                           # +0x4c20
    floor = sections_end(ctx)

    _section(ctx, 0, t[T_REC_S0_141516], KIND_S0, PASS_BASE, st)
    _section(ctx, 1, t[T_REC_S1_141516], KIND_S1, PASS_BASE, st)
    _section(ctx, 2, t[T_REC_S2_141516], KIND_S2, PASS_BASE, st)
    _section(ctx, 3, st.s3_rec,
             KIND_S3_ABS if st.s3_rec == 8 else KIND_S3_DELTA, PASS_BASE, st)
    dec_text(ctx, floor)                                      # +0x4d64

    if ctx.dbrel < 0x14:                                      # +0x4d8c
        return
    st.w5 = bytes(ctx.g(8) for _ in range(5))                 # +0x4d98
    _section(ctx, 4, t[T_REC_E4_141516], KIND_E4, PASS_20, st)
    _section(ctx, 1, t[T_REC_S1_141516], KIND_S1, PASS_20, st)
    _section(ctx, 2, t[T_REC_S2_141516], KIND_S2, PASS_20, st)

    if ctx.dbrel < 0x17:                                      # +0x4f00
        return
    _section(ctx, 5, t[T_REC_E5_141516], KIND_E5, PASS_23, st)
    _section(ctx, 1, t[T_REC_S1_141516], KIND_S1, PASS_23, st)
    _section(ctx, 2, t[T_REC_S2_141516], KIND_S2, PASS_23, st)
    if ctx.g(1):                                              # +0x4fbc
        dec_text(ctx, floor)
    if ctx.g(1):                                              # +0x4ff0
        dec_text(ctx, floor)
    if ctx.dbrel > 0x17:        # seen on DB-REL 34; not read by RR 0101 (see _s2_tail)
        _s2_tail(ctx)
