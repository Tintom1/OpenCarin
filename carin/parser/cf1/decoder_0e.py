from __future__ import annotations

from .core import *
from .core import _walk
from .constants import *
import struct

from .decoder_00 import dec_text, enc_text, text_end


def s2_offset_bits(subrel: int) -> int:
    """Width of the S2 `val1` field (SECTION_4 byte offset >> 1).

    13 bits on sub-revision < 9 (CC-93 hardcodes `moveq #$d`, pbp+0x4248;
    CD-IDs 2952 and 21594), 15 bits from sub-revision 9 (CD-IDs 21708 and
    21734, whose `0x00` tiles need offsets up to 33,364). Same +2-bit step as
    the section 6 field of type 0x00 (`db_pub+0x4604`). On the discs tested,
    sub-revision and sector unit change together, so the data alone cannot
    tell which of the two selects the width.
    """
    return 15 if subrel >= 9 else 13


def _dec_0e_s0(ctx: Cf1Context, e1: Entry, e2: Entry) -> None:
    """pbp+0x40b0 — sezione 0 del tipo 0x0E (nodi/segmenti).

    Verificato empiricamente su DB-REL 34 (0 S2-ptr errati su 1143 record S1):
      getbits(ptrbits)           -> A        [+0 u16]
      getbits(2)                 -> FLAGS lo [+2 bits 0-1]  (NB: annot. asm "$49e8=getbits(4)" errata)
      getbits(1) << 4            -> FLAGS hi [+2 bit 4]
      getbits(1)                 -> inherit bit
        if 1:  getbits(3) -> B [+3 u8],  getbits(ptrbits) -> C [+4 u16]
        if 0:  eredita B e C dal record precedente
      getbits(bits_needed(e1.count)) -> D_idx
             D = e1.off + D_idx * T[0x41]  [+6 u16]

    FLAGS semantics (firmware static analysis 2026-09-20 — FINAL):
      bit4=0: 0x00=67%, 0x01=5%, 0x02=1%
      bit4=1: 0x10=26%, 0x11=1%, 0x12=0.1%
      bits[1:0]: access category  0=normal, 1=restricted/ramp, 2=non-motorised or ferry
      B (3-bit, getbits(3)): functional class 1..6; distribution B=1(43%),4(19%),5(15%),3(14%)
    bit4 is NOT a one-way routing bit. Full rpmod.asm scan found no btst #4 on FLAGS byte
      (+2 of S0 record). can_traverse ($4360) reads block[D+0x10/+0x11] (always 0x00 for 0x0E),
      not FLAGS. $6eae cost = attribute_list_element[2]*0x3C00 (element[1]==5), not FLAGS.
      btst #4 in sub_0066de ($698a, $6a5a) tests OS-9 restriction-table outputs, not FLAGS.
      Best hypothesis: map-rendering category (road importance / cartographic class for pbp).
      One-way enforcement handled by OS-9 restriction tables via jsr -$7258(a6)/-$724c(a6).
    See docs/carindb/03-road-network.md §6.3 for full firmware evidence.
    """
    pb = ctx.ptrbits
    pb_s1 = bits_needed(e1.count)
    s1_rec = ctx.T(T_REC_S1_0E)

    for cur, prev, _first in _walk(ctx, 0, ctx.T(T_REC_S0_0E)):
        ctx.w(cur + 0, ctx.g(pb))                        # A
        flags_lo = ctx.g(2)
        flags_hi = ctx.g(1) << 4
        ctx.b(cur + 2, flags_lo | flags_hi)               # FLAGS
        if ctx.g(1):                                      # inherit=1: leggi B e C
            ctx.b(cur + 3, ctx.g(3))                      # B
            ctx.w(cur + 4, ctx.g(pb))                     # C
        elif prev >= 0:
            ctx.b(cur + 3, ctx.dst[prev + 3])             # eredita B
            ctx.w(cur + 4, ctx.rw(prev + 4))              # eredita C
        d_idx = ctx.g(pb_s1)
        ctx.w(cur + 6, e1.off + d_idx * s1_rec)           # D -> sezione 1


def _dec_0e_s2(ctx: Cf1Context, count_N: int, raw_12: bytes,
               M_hi: int, M_lo: int) -> None:
    """pbp+0x41c0 — sezione 2 del tipo 0x0E (geometria delta, T[0x42]=24 byte).

    Algoritmo bitstream (MSB-first, prosegue il bitstream di S0/S1):
      idx_N_bits = bits_needed(count_N)
      per ogni record:
        idx_N      = getbits(idx_N_bits)
        has_deltas = getbits(1)
        if has_deltas:
          per 4 campi: is_16=getbits(1); val=getbits(16 if is_16 else M_hi)
        else:
          4 x 0x7FFF  sentinella
        val1 = getbits(13 if subrel < 9 else 15) << 1
        val2 = getbits(M_lo)

    Output per record 24 byte (✅ VERIFIED 2026-09-19, oracle: pbp m68k write trace):
      +0   i32 x_anc        (anchor[idx_N] bytes 0-3, raw copy — memmove pbp+0x41d4)
      +4   i32 y_anc        (anchor[idx_N] bytes 4-7, raw copy — memmove pbp+0x41d4)
      +8   u16 raw_delta[0] (getbits(1)→is_16; getbits(16 if is_16 else M_hi))
      +10  u16 raw_delta[1]
      +12  u16 raw_delta[2]
      +14  u16 raw_delta[3]
      +16  i32 anchor_f2   (anchor[idx_N] bytes 8-11, raw copy — memmove pbp+0x41ee)
      +20  u16 val1 = getbits(s2_offset_bits(subrel)) << 1   (13 or 15 bits)
      +22  u16 val2 = getbits(M_lo)
    """
    e2 = ctx.entry(2)
    idx_N_bits = bits_needed(count_N)
    s2_rec = ctx.T(T_REC_S2_0E)

    for i in range(e2.count):
        base = e2.off + i * s2_rec
        idx_N = ctx.g(idx_N_bits)

        if idx_N < count_N:
            anc = idx_N * 12
            ctx.dst[base:base + 8] = raw_12[anc:anc + 8]
            ctx.dst[base + 16:base + 20] = raw_12[anc + 8:anc + 12]

        if ctx.g(1):  # has_deltas
            raw_d = []
            for _ in range(4):
                is_16 = ctx.g(1)
                w = 16 if is_16 else M_hi
                raw_d.append(ctx.g(w))
        else:
            raw_d = [0x7FFF] * 4

        struct.pack_into(">HHHH", ctx.dst, base + 8, *raw_d)

        val1 = ctx.g(s2_offset_bits(ctx.subrel)) << 1
        val2 = ctx.g(M_lo)
        struct.pack_into(">HH", ctx.dst, base + 20, val1 & 0xFFFF, val2 & 0xFFFF)


def _dec_0e_s1(ctx: Cf1Context, e2: Entry) -> None:
    """Sezione 1 del tipo 0x0E (archi/attributi) — da docs/carindb/03-road-network.md §6.3.1.

    Record 6 byte (T[0x41]):
      +0 u16: puntatore -> sezione 2  = e2.off + getbits(pb_s2) * T[0x42]
      +2 u8:  count     = getbits(1) ? getbits(pb_s2) + 2 : 1
      +3 u8:  flag      = getbits(1)
      +4-5:   sconosciuti, lasciati a 0
    """
    pb_s2 = bits_needed(e2.count)
    s1_rec = ctx.T(T_REC_S1_0E)
    s2_rec = ctx.T(T_REC_S2_0E)

    for cur, _prev, _first in _walk(ctx, 1, s1_rec):
        s2_idx = ctx.g(pb_s2)
        ctx.w(cur + 0, e2.off + s2_idx * s2_rec)          # ptr -> sezione 2
        cnt = ctx.g(pb_s2) + 2 if ctx.g(1) else 1
        ctx.b(cur + 2, cnt)                                # count
        ctx.b(cur + 3, ctx.g(1))                           # flag


def decode_type0E(ctx: Cf1Context) -> None:
    """db_pub+0x1e98 — decoder BLOCK_TYPE 0x0E (parcella stradale, CF=1).

    Pre-bitstream (raw, prima di bits_init — traccia da decode_modugno.py +
    m68k pbp+0x4320):
      T[0x2b]  byte di prologo   (header + descriptor + bbox + service = 48)
      u16      count_N           (numero di ancore da 12 byte per la sezione 2)
      count_N * 12  byte         (tabella ancore raw per la sezione 2)
      1 byte   M_hi              (larghezza delta per la sezione 2)
      1 byte   M_lo              (larghezza val2  per la sezione 2)

    Bitstream MSB-first (dopo bits_init):
      Sezione 0: nodi/segmenti     (_dec_0e_s0)
      Sezione 1: archi/attributi   (_dec_0e_s1)

    Sezione 2 (decode delta delle coordinate geometriche): _dec_0e_s2.

    The stream ends with the name blob (dec_text, as in type 0x00): without
    it the section 0 name and locality pointers point past the decoded data.
    It consumes the stream to within a byte of its end on both CDs.
    """
    ctx.copy_raw(0, ctx.T(T_PROLOG_0E))
    count_N = struct.unpack_from(">H", ctx.copy_raw(-1, 2))[0]
    raw_12 = ctx.copy_raw(-1, count_N * 12)
    mhi_mlo = ctx.copy_raw(-1, 2)
    M_hi, M_lo = mhi_mlo[0], mhi_mlo[1]
    ctx.m_hi = M_hi
    ctx.m_lo = M_lo

    e1 = ctx.entry(1)
    e2 = ctx.entry(2)

    ctx.bits_init()

    _dec_0e_s0(ctx, e1, e2)
    _dec_0e_s1(ctx, e2)
    _dec_0e_s2(ctx, count_N, raw_12, M_hi, M_lo)

    s2_rec = ctx.T(T_REC_S2_0E)
    dec_text(ctx, floor=e2.off + e2.count * s2_rec)


def encode_type0E(decoded: bytes, table: dict, dbrel: int, subrel: int = 9,
                  sector_size: int = SECTOR) -> bytes:
    """Re-encode a decoded 0x0E block to CF=1 raw bytes.

    Round-trip guarantee: decode_block(encode_type0E(decoded, table, dbrel),
                                       table, dbrel) == decoded  (bytes [4:]).
    """
    prolog_size = table[T_PROLOG_0E]    # 48
    s0_rec  = table[T_REC_S0_0E]       # 8
    s1_rec  = table[T_REC_S1_0E]       # 6
    s2_rec  = table[T_REC_S2_0E]       # 24
    base_d  = table[T_DESC_BASE]        # offset of section descriptor in decoded

    total   = len(decoded)
    usize   = total // sector_size
    ptrbits = bits_needed(total)

    e0_off, e0_cnt = struct.unpack_from(">HH", decoded, base_d + 0)
    e1_off, e1_cnt = struct.unpack_from(">HH", decoded, base_d + 4)
    e2_off, e2_cnt = struct.unpack_from(">HH", decoded, base_d + 8)

    # anchor table: unique 12-byte signatures in first-appearance order
    seen: dict[bytes, int] = {}
    anchors: list[bytes] = []
    for i in range(e2_cnt):
        b   = e2_off + i * s2_rec
        sig = bytes(decoded[b:b + 8]) + bytes(decoded[b + 16:b + 20])
        if sig not in seen:
            seen[sig] = len(anchors)
            anchors.append(sig)

    count_N    = len(anchors)
    raw_12     = b"".join(anchors)
    idx_N_bits = bits_needed(count_N) if count_N > 0 else 1

    # M_hi: min bits to cover all delta values in has_deltas=True records
    max_delta     = 0
    has_any_delta = False
    for i in range(e2_cnt):
        b      = e2_off + i * s2_rec
        deltas = struct.unpack_from(">HHHH", decoded, b + 8)
        if not all(d == 0x7FFF for d in deltas):
            has_any_delta = True
            for d in deltas:
                if d > max_delta:
                    max_delta = d
    # M_hi/M_lo: usa i valori del pre-header originale (decoded[7]/[6])
    # per preservare il round-trip; fallback al calcolo se byte è 0 (blocco non 0x0E).
    M_hi = decoded[7] if decoded[7] else (max(1, bits_needed(max_delta + 1)) if has_any_delta else 1)

    # M_lo: min bits to cover all val2 values
    max_val2 = 0
    for i in range(e2_cnt):
        b  = e2_off + i * s2_rec
        v2 = struct.unpack_from(">H", decoded, b + 22)[0]
        if v2 > max_val2:
            max_val2 = v2
    M_lo = decoded[6] if decoded[6] else max(1, bits_needed(max_val2 + 1))

    pb_s1 = bits_needed(e1_cnt)
    pb_s2 = bits_needed(e2_cnt)

    bw = BitWriter()

    # ── Section 0 (pbp+0x40b0 / 0x40fe) ─────────────────────────────────────
    prev_B: int = -1
    prev_C: int = -1
    for i in range(e0_cnt):
        b     = e0_off + i * s0_rec
        A     = struct.unpack_from(">H", decoded, b)[0]
        FLAGS = decoded[b + 2]
        B     = decoded[b + 3]
        C     = struct.unpack_from(">H", decoded, b + 4)[0]
        D     = struct.unpack_from(">H", decoded, b + 6)[0]
        d_idx = (D - e1_off) // s1_rec

        bw.put(ptrbits, A)
        bw.put(2, FLAGS & 0x03)
        bw.put(1, (FLAGS >> 4) & 1)

        # inherit=1 if B/C differ from prev (or first record with non-zero B/C)
        need_bc = (prev_B < 0 and (B != 0 or C != 0)) or \
                  (prev_B >= 0 and (B != prev_B or C != prev_C))
        bw.put(1, 1 if need_bc else 0)
        if need_bc:
            bw.put(3, B)
            bw.put(ptrbits, C)
        prev_B, prev_C = B, C

        bw.put(pb_s1, d_idx)

    # ── Section 1 (pbp+0x4168) ───────────────────────────────────────────────
    for i in range(e1_cnt):
        b      = e1_off + i * s1_rec
        ptr    = struct.unpack_from(">H", decoded, b)[0]
        span   = decoded[b + 2]
        flag   = decoded[b + 3]
        s2_idx = (ptr - e2_off) // s2_rec

        bw.put(pb_s2, s2_idx)
        if span > 1:
            bw.put(1, 1)
            bw.put(pb_s2, span - 2)
        else:
            bw.put(1, 0)
        bw.put(1, flag)

    # ── Section 2 (pbp+0x41c0) ───────────────────────────────────────────────
    for i in range(e2_cnt):
        b      = e2_off + i * s2_rec
        sig    = bytes(decoded[b:b + 8]) + bytes(decoded[b + 16:b + 20])
        idx_N  = seen[sig]
        deltas = struct.unpack_from(">HHHH", decoded, b + 8)
        val1   = struct.unpack_from(">H", decoded, b + 20)[0]
        val2   = struct.unpack_from(">H", decoded, b + 22)[0]

        bw.put(idx_N_bits, idx_N)

        has_deltas = not all(d == 0x7FFF for d in deltas)
        bw.put(1, 1 if has_deltas else 0)
        if has_deltas:
            thresh = (1 << M_hi) - 1
            for d in deltas:
                is_16 = 1 if d > thresh else 0
                bw.put(1, is_16)
                bw.put(16 if is_16 else M_hi, d)

        bw.put(s2_offset_bits(subrel), val1 >> 1)
        bw.put(M_lo, val2)

    # name blob (dec_text): from the end of section 2 to the NUL closing the last name
    text_start = e2_off + e2_cnt * s2_rec
    enc_text(bw, decoded, text_start, text_end(decoded, text_start), ptrbits)

    # ── assemble raw block ────────────────────────────────────────────────────
    prolog    = bytearray(decoded[:prolog_size])
    prolog[6] = 1       # CF=1
    prolog[7] = usize   # decompressed sectors

    pre_hdr   = struct.pack(">H", count_N) + raw_12 + bytes([M_hi, M_lo])
    bitstream = bw.to_bytes()

    payload = bytes(prolog) + pre_hdr + bitstream

    rem = len(payload) % sector_size
    if rem:
        payload += b"\x00" * (sector_size - rem)

    # fix block_id: preserve sector, update length-in-sectors
    old_bid = struct.unpack_from(">I", payload, 0)[0]
    sector  = old_bid >> 8
    n_secs  = len(payload) // sector_size
    return struct.pack(">I", (sector << 8) | (n_secs & 0xFF)) + payload[4:]


def decode_s2_coords(decoded: bytes, table: dict[int, int],
                     ) -> list[tuple[tuple[int, int], tuple[int, int]] | None]:
    """Ricostruisce le coordinate assolute CARIN per ogni record S2 di un blocco 0x0E.

    SUPERSEDED (2026-09-27, docs/carindb/03-road-network.md §6.3.1): S2 +8..+14
    are house-number ranges, not coordinate deltas, and +0/+4 is the centre of the
    linked 0x00 tile. Use decode_s2_links(). Kept for the historical oracle.

    Fonte firmware: il decoder pbp+0x41c0 memorizza i delta raw (unsigned) e
    l'ancora; il routing engine applica sign-extension e ancora+delta a query
    time. M_hi è letto da decoded[7] (impostato da decode_block dal pre-header);
    la larghezza per sign_extend è 16 se raw_delta[k] > (1<<M_hi)-1 (is_16),
    M_hi altrimenti. Layout delta: d[0]=dx1, d[1]=dy1, d[2]=dx2, d[3]=dy2.

    Ritorna una lista di lunghezza e2_cnt:
      - None  → sentinella (4 × 0x7FFF, nessuna geometria)
      - ((x1,y1),(x2,y2)) → due punti in coordinate CARIN assolute
    """
    base_d = table[T_DESC_BASE]
    s2_rec = table[T_REC_S2_0E]
    e2_off, e2_cnt = struct.unpack_from(">HH", decoded, base_d + 8)

    # M_hi dal pre-header, scritto a decoded[7] da decode_block per i blocchi 0x0E (CF=1)
    # in CF=2, decoded[6] = 2 (compression flag), decoded[7] = usize
    cf = decoded[6]
    M_hi = decoded[7] or 1
    thresh = (1 << M_hi) - 1

    def _sx(val: int, bits: int) -> int:
        if val & (1 << (bits - 1)):
            return val - (1 << bits)
        return val

    result: list[tuple[tuple[int, int], tuple[int, int]] | None] = []
    for i in range(e2_cnt):
        b = e2_off + i * s2_rec
        x_anc = struct.unpack_from(">i", decoded, b + 0)[0]
        y_anc = struct.unpack_from(">i", decoded, b + 4)[0]
        d_unsigned = struct.unpack_from(">HHHH", decoded, b + 8)

        if all(v == 0x7FFF for v in d_unsigned):
            result.append(None)
        else:
            if cf == 2:
                # CF=2 usa zlib: deltas sono interi 16-bit signed
                dx1, dy1, dx2, dy2 = struct.unpack_from(">hhhh", decoded, b + 8)
            else:
                w = [16 if v > thresh else M_hi for v in d_unsigned]
                dx1 = _sx(d_unsigned[0], w[0])
                dy1 = _sx(d_unsigned[1], w[1])
                dx2 = _sx(d_unsigned[2], w[2])
                dy2 = _sx(d_unsigned[3], w[3])
            result.append((
                (x_anc + dx1, y_anc + dy1),
                (x_anc + dx2, y_anc + dy2),
            ))
    return result


HOUSE_NUMBER_NONE = 0x7FFF


def decode_s2_links(decoded: bytes, table: dict[int, int]) -> list[dict]:
    """Section 2 records of a decoded 0x0E block (street-name directory).

    Each record links a street entry to a run of road segments in one type 0x00
    tile, with the house-number ranges of that run (03-road-network.md §6.3.1):

      +0  i32  x, +4 i32 y   centre of the linked 0x00 tile (CARIN units)
      +8  u16  even lo, +10 even hi, +12 odd lo, +14 odd hi   (0x7FFF pair = none)
      +16 u32  BLOCK_ID of the 0x00 tile
      +20 u16  byte offset of the first SECTION_4 record in that tile
      +22 u16  number of consecutive SECTION_4 records

    Works on CF=1 output (decode_block) and on CF=0/CF=2 payloads (header included).
    Returns one dict per record: {"tile_center", "tile_block_id", "tile_sector",
    "tile_length", "s4_offset", "s4_count", "even", "odd"}; "even"/"odd" are
    (lo, hi) or None.
    """
    base_d = table[T_DESC_BASE]
    s2_rec = table[T_REC_S2_0E]
    e2_off, e2_cnt = struct.unpack_from(">HH", decoded, base_d + 8)

    def _range(lo: int, hi: int):
        if lo == HOUSE_NUMBER_NONE and hi == HOUSE_NUMBER_NONE:
            return None
        return lo, hi

    out = []
    for i in range(e2_cnt):
        b = e2_off + i * s2_rec
        if b + 24 > len(decoded):
            break
        x, y = struct.unpack_from(">ii", decoded, b)
        ev_lo, ev_hi, od_lo, od_hi = struct.unpack_from(">4H", decoded, b + 8)
        bid, s4_off, s4_cnt = struct.unpack_from(">IHH", decoded, b + 16)
        out.append({
            "tile_center": (x, y),
            "tile_block_id": bid,
            "tile_sector": bid >> 8,
            "tile_length": bid & 0xFF,
            "s4_offset": s4_off,
            "s4_count": s4_cnt,
            "even": _range(ev_lo, ev_hi),
            "odd": _range(od_lo, od_hi),
        })
    return out
