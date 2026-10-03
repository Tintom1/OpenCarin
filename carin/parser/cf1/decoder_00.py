from __future__ import annotations

from .core import *
from .core import _walk
from .constants import *
import struct

def _delta(ctx: Cf1Context, prev_val: int) -> int:
    """Codifica delta comune a dec_C / dec_D / dec_E (pbp 0x3b42 e gemelle)."""
    width = ctx.widths[1]
    if ctx.g(1):
        if ctx.g(1):
            return ctx.g(16)
        return (prev_val - ctx.g(width)) & 0xFFFF
    return (prev_val + ctx.g(width)) & 0xFFFF


def dec_a14(ctx: Cf1Context, idx: int) -> None:
    """Passata DB-REL 20 delle sezioni 0/1/2 (db_pub+0x2f30/0x30dc/0x3270).

    Per la sezione 0 i due campi condizionali vengono letti e **scartati**:
    il flusso li contiene ancora per i lettori piu' vecchi, ma i valori validi
    arrivano dalle passate 0x15/0x17.
    """
    pb = ctx.ptrbits
    rec = ctx.T(T_REC_S0)
    for cur, prev, _first in _walk(ctx, idx, rec):
        if ctx.g(1):
            v2, v4 = ctx.g(pb), ctx.g(pb - 1) << 1
            if idx != 0:
                ctx.w(cur + 2, v2)
                ctx.w(cur + 4, v4)
        elif idx != 0 and prev >= 0:
            ctx.w(cur + 2, ctx.rw(prev + 2))
            ctx.w(cur + 4, ctx.rw(prev + 4))
        ctx.w(cur + 0, ctx.g(pb))


def dec_a15_s0(ctx: Cf1Context) -> None:
    """Passata DB-REL 21 della sezione 0 (db_pub+0x3010)."""
    for cur, prev, _first in _walk(ctx, 0, ctx.T(T_REC_S0)):
        if ctx.g(1):
            ctx.w(cur + 2, ctx.g(16))
        elif prev >= 0:
            ctx.w(cur + 2, ctx.rw(prev + 2))


def dec_a17_s0(ctx: Cf1Context) -> None:
    """Passata DB-REL 23 della sezione 0 (db_pub+0x308c)."""
    for cur, _prev, _first in _walk(ctx, 0, ctx.T(T_REC_S0)):
        ctx.w(cur + 4, ctx.g(ctx.ptrbits - 1) << 1)


def dec_a17_s1(ctx: Cf1Context) -> None:
    """Passata DB-REL 23 della sezione 1 (db_pub+0x31dc): due offset assoluti."""
    pb = ctx.ptrbits
    for cur, _prev, _first in _walk(ctx, 1, ctx.T(T_REC_S0)):
        ctx.w(cur + 6, ctx.g(pb - 1) << 1)
        ctx.w(cur + 8, ctx.g(pb - 1) << 1)


def dec_a17_s2(ctx: Cf1Context) -> None:
    """Passata DB-REL 23 della sezione 2 (db_pub+0x3394): delta appiccicoso.

    Due accumulatori indipendenti: il flag a 1 aggiorna il passo, il flag a 0
    riusa l'ultimo passo letto.
    """
    pb = ctx.ptrbits
    step = [0, 0]
    acc = [0, 0]
    for cur, _prev, _first in _walk(ctx, 2, ctx.T(T_REC_S0)):
        for k, off in enumerate((6, 8)):
            if ctx.g(1):
                step[k] = (ctx.g(pb - 1) << 1) & 0xFFFF
            acc[k] = (step[k] + acc[k]) & 0xFFFF
            ctx.w(cur + off, acc[k])


def dec_b(ctx: Cf1Context, kind: int) -> None:
    """db_pub+0x348c — sezione 4, record T[0x08], campi di coda a T[0x09].

    ``kind`` seleziona il gruppo di campi: 0x14 sono quelli gia' presenti in
    DB-REL 20, 0x15 il campo ``+0x16`` aggiunto in DB-REL 21, che punta nella
    sezione 13, 0x1B il campo ``+0x18`` di DB-REL 27. Le passate 0x14 e 0x15
    leggono anche il record sentinella in coda (Mk3 +0x3a68/+0x3c50, RR
    sub_005594 +0x5be0/+0x5db8); la 0x1B no.
    """
    e4 = ctx.entry(4)
    e2, e7, e10, e11, e12, e13 = (ctx.entry(i) for i in (2, 7, 10, 11, 12, 13))
    rec, tail = ctx.T(T_REC_S4), ctx.T(T_TAIL_S4)
    pb, pbits = ctx.ptrbits, ctx.pb
    start, end = e4.off, e4.off + e4.count * rec
    cur, prev = start, -1

    def s13_ptr(at: int, prv: int) -> None:
        if ctx.g(1):
            ctx.w(at + 0x16, e13.off + ctx.g(pbits["s13"]) * ctx.T(T_REC_S13))
        elif prv >= 0:
            ctx.w(at + 0x16, ctx.rw(prv + 0x16))

    def ptr_group(at: int) -> None:
        ctx.w(at + 0x12, e10.off + ctx.g(pbits["s10"]) * ctx.T(T_REC_S10))
        ctx.w(at + 0x14, e12.off + ctx.g(pbits["s12"]) * ctx.T(T_REC_S12))
        ctx.w(at + tail + 4, e11.off + ctx.g(pbits["s11"]) * ctx.T(T_REC_S11))

    while cur < end:
        if kind == 0x14:
            if cur != start:
                ctx.dst[cur : cur + rec] = ctx.dst[prev : prev + rec]
            if ctx.g(1):
                ptr_group(cur)
            if ctx.g(1):
                ctx.b(cur + 0x0A, ctx.g(8))
                ctx.b(cur + 0x0B, ctx.g(8))
                ctx.b(cur + 0x10, ctx.g(8))
                ctx.b(cur + 0x11, ctx.g(8))
                ctx.w(cur + tail + 2, ctx.g(16))
            ctx.w(cur + 0x00, ctx.g(pb - 1) << 1)
            ctx.w(cur + 0x02, ctx.g(pb - 1) << 1)
            if ctx.g(1):
                ctx.cache_s7 = e7.off + ctx.g(pbits["s7"]) * ctx.T(T_REC_S7)
            ctx.w(cur + 0x04, ctx.cache_s7)
            for off in (0x06, 0x08):
                t = ctx.g(pbits["s4"])
                ctx.w(cur + off, 0 if t == e4.count else e4.off + t * rec)
            width = 16 if ctx.g(1) else ctx.widths[0]
            ctx.w(cur + 0x0C, ctx.g(width))
            ctx.b(cur + 0x0E, ctx.g(8))
            ctx.b(cur + 0x0F, ctx.g(8))
            if ctx.g(1):
                ctx.cache_s2 = e2.off + ctx.g(pbits["s2"]) * ctx.T(T_REC_S0)
            ctx.w(cur + tail + 0, ctx.cache_s2)
        elif kind == 0x15:
            s13_ptr(cur, prev)
        elif kind == 0x1B:
            # RR sub_005594 +0x5b5c: two bytes, or both copied from the
            # previous record (the firmware's first "previous" is address 0)
            if ctx.g(1):
                ctx.b(cur + 0x18, ctx.g(8))
                ctx.b(cur + 0x19, ctx.g(8))
            elif prev >= 0:
                ctx.b(cur + 0x18, ctx.dst[prev + 0x18])
                ctx.b(cur + 0x19, ctx.dst[prev + 0x19])
        prev, cur = cur, cur + rec

    if kind == 0x15:            # record sentinella (Mk3 +0x3c50, RR +0x5db8)
        s13_ptr(cur, prev)
    if kind != 0x14:
        return
    # record sentinella in coda (blueprint 9.5: la sezione ha count+1 record)
    if ctx.g(1):
        ptr_group(cur)
    elif prev >= 0:
        ctx.w(cur + 0x12, ctx.rw(prev + 0x12))
        ctx.w(cur + 0x14, ctx.rw(prev + 0x14))
        ctx.w(cur + tail + 4, ctx.rw(prev + tail + 4))
    if ctx.g(1):
        ctx.cache_s7 = e7.off + ctx.g(pbits["s7"]) * ctx.T(T_REC_S7)
    ctx.w(cur + 0x04, ctx.cache_s7)


def _dec_xy(ctx: Cf1Context, idx: int, recsize: int, extra) -> None:
    """Corpo comune di dec_C (0x3ad4) e dec_D (0x3bfa)."""
    e4 = ctx.entry(4)
    for cur, prev, first in _walk(ctx, idx, recsize):
        if ctx.g(1):
            ctx.b(cur + 6, ctx.g(8))
            ctx.b(cur + 7, ctx.g(3))
        elif prev >= 0:
            ctx.b(cur + 6, ctx.dst[prev + 6])
            ctx.b(cur + 7, ctx.dst[prev + 7])
        if first:
            ctx.w(cur + 0, ctx.g(16))
            ctx.w(cur + 2, ctx.g(16))
        else:
            ctx.w(cur + 0, _delta(ctx, ctx.rw(prev + 0)))
            ctx.w(cur + 2, _delta(ctx, ctx.rw(prev + 2)))
        ctx.w(cur + 4, e4.off + ctx.g(ctx.pb["s4"]) * ctx.T(T_REC_S4))
        if extra is not None:
            extra(ctx, cur)


def dec_c(ctx: Cf1Context) -> None:
    """pbp+0x3ad4 — sezione 5, record T[0x10]."""
    _dec_xy(ctx, 5, ctx.T(T_REC_S5), None)


def dec_d(ctx: Cf1Context) -> None:
    """pbp+0x3bfa — sezione 6, record T[0x06], con due campi in piu'."""
    off5 = ctx.T(T_REC_S5)

    def extra(c: Cf1Context, cur: int) -> None:
        c.l(cur + off5, c.g(32))
        # db_pub+0x4604: la larghezza del campo successivo dipende dalla
        # sotto-revisione del formato (LAYOUT[+2]), non dai dati
        c.w(cur + off5 + 4, c.g(16 if c.subrel >= 9 else 14))

    _dec_xy(ctx, 6, ctx.T(T_REC_S6), extra)


def dec_e(ctx: Cf1Context) -> None:
    """pbp+0x3d3e — sezione 7, record T[0x0c]."""
    for cur, prev, first in _walk(ctx, 7, ctx.T(T_REC_S7)):
        if first:
            ctx.w(cur + 0, ctx.g(16))
            ctx.w(cur + 2, ctx.g(16))
        else:
            ctx.w(cur + 0, _delta(ctx, ctx.rw(prev + 0)))
            ctx.w(cur + 2, _delta(ctx, ctx.rw(prev + 2)))
        ctx.b(cur + 4, ctx.g(3))


def dec_f(ctx: Cf1Context) -> None:
    """pbp+0x3e1c — sezione 11, record T[0x13]."""
    pb = ctx.ptrbits
    for cur, _prev, _first in _walk(ctx, 11, ctx.T(T_REC_S11)):
        ctx.w(cur + 0, ctx.g(pb))
        ctx.w(cur + 2, ctx.g(pb))
        ctx.w(cur + 4, ctx.g(1))


def dec_s13(ctx: Cf1Context) -> None:
    """db_pub+0x4a2c — sezione 13 (DB-REL 21), record T[0x4c]."""
    for cur, _prev, _first in _walk(ctx, 13, ctx.T(T_REC_S13)):
        ctx.l(cur + 0, ctx.g(32))
        ctx.w(cur + 4, ctx.g(ctx.ptrbits))
        ctx.b(cur + 6, ctx.g(8))
        ctx.b(cur + 7, ctx.g(8))


def dec_s14(ctx: Cf1Context) -> None:
    """db_pub+0x4b14 — sezione 14 (DB-REL 23), record T[0x59].

    Indice dei nomi: ``{u16 offset nel blob di testo, u8 lunghezza, u8 tipo}``,
    ogni campo con il proprio bit di ereditarieta' dal record precedente.
    """
    pb = ctx.ptrbits
    for cur, prev, _first in _walk(ctx, 14, ctx.T(T_REC_S14)):
        if ctx.g(1):
            ctx.w(cur + 0, ctx.g(pb))
        elif prev >= 0:
            ctx.w(cur + 0, ctx.rw(prev + 0))
        if ctx.g(1):
            ctx.b(cur + 2, ctx.g(8))
        elif prev >= 0:
            ctx.b(cur + 2, ctx.dst[prev + 2])
        if ctx.g(1):
            ctx.b(cur + 3, ctx.g(5))
        elif prev >= 0:
            ctx.b(cur + 3, ctx.dst[prev + 3])


_SECT_REC = {0: T_REC_S0, 1: T_REC_S0, 2: T_REC_S0, 3: T_REC_S3, 4: T_REC_S4,
             5: T_REC_S5, 6: T_REC_S6, 7: T_REC_S7, 9: T_REC_S9, 10: T_REC_S10,
             11: T_REC_S11, 12: T_REC_S12, 13: T_REC_S13}


def _sections_end(ctx: Cf1Context) -> int:
    """First byte past the numbered record sections 0..13.

    The name blob lives at or after this offset; everything below it is
    already-decoded record data that dec_text must never overwrite.
    """
    hi = 0
    for idx, key in _SECT_REC.items():
        e = ctx.entry(idx)
        if not e.count:
            continue
        try:
            rec = ctx.T(key)
        except Cf1Error:
            continue
        hi = max(hi, e.off + e.count * rec)
    return hi


def dec_text(ctx: Cf1Context, floor: "int | None" = None) -> None:
    """pbp+0x4862 — blob dei nomi, codice a prefisso + dizionario di blocco.

    `floor` is the first byte past the block's record sections; it defaults
    to the type 0x00 layout (`_sections_end`). Other block types pass theirs.

    The DB-REL >= 23 pass ends with two optional dec_text calls. Until
    2026-09-28 the port skipped the pass 0x15 sentinel record, so their flag
    bits were read misaligned and fired with garbage (start, end) ranges that
    overwrote decoded geometry (section 7 shape points turned into repeated
    "aa", 0x6161). With the stream aligned every range lands after the
    sections; writes below `floor` stay suppressed as a guard.
    """
    pb = ctx.ptrbits
    start = ctx.g(pb)
    end = ctx.g(pb)
    ctx.texts.append((start, end))
    if start == 0 and end == 0:
        return
    words = []
    for _ in range(6):
        n = ctx.g(5)
        words.append(bytes(ctx.g(7) for _ in range(n)))
    if floor is None:
        floor = _sections_end(ctx)
    ok = start <= end < len(ctx.dst) and start >= floor
    p = start
    while p <= end and p < len(ctx.dst):
        code = ctx.g(2)
        if code == 0:
            v = CHARMAP[ctx.g(1)]
        elif code == 1:
            v = CHARMAP[2 + ctx.g(2)]
        elif code == 2:
            v = CHARMAP[6 + ctx.g(3)]
        else:
            v = ctx.g(7)
            if v <= 0x26:
                if v > 0x1B:
                    w = words[v - 0x21]
                    if ok:
                        ctx.dst[p : p + len(w)] = w
                    p += len(w)
                    continue
                v = CHARMAP[14 + v]
        if ok:
            ctx.dst[p] = v
        p += 1


def text_end(dst: bytes, start: int) -> int:
    """Last byte of a name blob starting at `start`: the NUL closing its last string.

    The discs' blobs always end on that NUL (400/400 blocks sampled on CD-ID 2952).
    It must be written: the firmware's output buffer is not zeroed, and without it
    the last name runs on into whatever the buffer held (seen on a CNI1).
    Returns start - 1 for an empty blob.
    """
    last = len(dst.rstrip(b"\x00")) - 1
    if last < start:
        return start - 1
    return min(last + 1, len(dst) - 1)


def _char_bits(c: int) -> int | None:
    """Bits dec_text needs for one literal byte, or None if it has no code."""
    i = CHARMAP.find(bytes([c]))
    if 0 <= i < 2:
        return 3
    if 2 <= i < 6:
        return 4
    if 6 <= i < 14:
        return 5
    if 14 <= i < 14 + 0x1C or 0x26 < c < 0x80:
        return 9
    return None


def choose_words(blob: bytes, n: int = 6, maxlen: int = 31) -> list[bytes]:
    """Pick up to n dictionary words for a name blob, greedily by bits saved.

    A word is 7-bit bytes, at most 31 long; each use costs 9 bits instead of
    its letters, and each word costs 5 + 7 * len bits in the blob's header.
    Occurrences are counted without overlap, after the words already chosen.
    """
    cost = [_char_bits(c) or 9 for c in blob]
    work = list(blob)                       # chosen words are masked with -1
    words = []
    for _ in range(n):
        best, best_gain = None, 0
        for L in range(2, maxlen + 1):
            seen: dict[tuple, list] = {}
            for p in range(len(work) - L + 1):
                key = tuple(work[p:p + L])
                if -1 in key or any(x >= 0x80 for x in key):
                    continue
                st = seen.setdefault(key, [0, -L])
                if p >= st[1] + L:          # no overlap with the previous counted use
                    st[0] += 1
                    st[1] = p
            for key, (cnt, _last) in seen.items():
                if cnt < 2:
                    continue
                bits = sum(_char_bits(x) or 9 for x in key)
                gain = cnt * (bits - 9) - (5 + 7 * L)
                if gain > best_gain:
                    best, best_gain = bytes(key), gain
        if best is None:
            break
        words.append(best)
        p = 0
        while p <= len(work) - len(best):
            if tuple(work[p:p + len(best)]) == tuple(best):
                work[p:p + len(best)] = [-1] * len(best)
                p += len(best)
            else:
                p += 1
    return words


def enc_text(bw: BitWriter, dst: bytes, start: int, end: int, ptrbits: int,
             words: list[bytes] | None = None) -> None:
    """Inverse of dec_text: write dst[start..end] (end inclusive) as a name blob.

    `words` are the blob's dictionary (at most six 7-bit strings of up to 31
    bytes); None picks them with choose_words(), [] writes none. Uses are
    matched greedily, longest word first. The bits need not match the
    original encoder's, but they decode to the same bytes. An empty range
    (end < start) writes the (0, 0) "no blob" marker.
    """
    if end < start:
        bw.put(ptrbits, 0)
        bw.put(ptrbits, 0)
        return
    blob = bytes(dst[start:end + 1])
    if words is None:
        words = choose_words(blob)
    if len(words) > 6 or any(len(w) > 31 or any(x >= 0x80 for x in w) for w in words):
        raise Cf1Error("dictionary: at most six 7-bit words of up to 31 bytes")
    bw.put(ptrbits, start)
    bw.put(ptrbits, end)
    for k in range(6):
        w = words[k] if k < len(words) else b""
        bw.put(5, len(w))
        for x in w:
            bw.put(7, x)
    order = sorted((w for w in words if w), key=len, reverse=True)
    p = start
    while p <= end:
        w = next((w for w in order if dst[p:p + len(w)] == w and p + len(w) <= end + 1), None)
        if w is not None:
            bw.put(2, 3); bw.put(7, 0x21 + words.index(w))
            p += len(w)
            continue
        c = dst[p]
        i = CHARMAP.find(bytes([c]))
        if 0 <= i < 2:
            bw.put(2, 0); bw.put(1, i)
        elif 2 <= i < 6:
            bw.put(2, 1); bw.put(2, i - 2)
        elif 6 <= i < 14:
            bw.put(2, 2); bw.put(3, i - 6)
        elif 14 <= i < 14 + 0x1C:
            bw.put(2, 3); bw.put(7, i - 14)
        elif 0x26 < c < 0x80:
            bw.put(2, 3); bw.put(7, c)
        else:
            raise Cf1Error(f"name blob byte {c:#04x} at {p:#x} has no CF=1 text code")
        p += 1


def decode_type00(ctx: Cf1Context) -> None:
    """db_pub+0x3d04 — decoder del BLOCK_TYPE 0x00.

    Il flusso e' organizzato in passate: ogni passata percorre di nuovo le
    sezioni leggendo il gruppo di campi introdotto da una certa revisione del
    formato (0x14 = DB-REL 20, 0x15 = 21, 0x17 = 23, 0x1B = 27). Le passate
    oltre la DB-REL del disco non esistono nel flusso e vanno saltate.

    Portato dal Mk3 (0127), che si ferma alla 0x17; la passata 0x1B viene dal
    RoadRunner (bsw2 0101, db_pub sub_005e6c +0x6e70). Dopo di essa i blocchi
    DB-REL 34 hanno un solo bit a 1 e poi zeri, che nessun firmware legge.
    """
    ctx.copy_raw(0, ctx.T(T_PROLOG))
    ent = ctx.entry
    ctx.pb = {
        "s2": bits_needed(ent(2).count),
        "s4": bits_needed(ent(4).count + 1),
        "s7": bits_needed(ent(7).count + 1),
        "s10": bits_needed(ent(10).count + 1),
        "s11": bits_needed(ent(11).count + 1),
        "s12": bits_needed(ent(12).count + 1),
    }
    ctx.widths = ctx.copy_raw(-1, 2)
    ctx.copy_section(3, ctx.T(T_REC_S3), plus1=True)
    ctx.copy_section(9, ctx.T(T_REC_S9), plus1=False)
    ctx.copy_section(10, ctx.T(T_REC_S10), plus1=False)
    if ent(12).count:
        ctx.copy_section(12, ctx.T(T_REC_S12), plus1=False)
    ctx.bits_init()

    # --- passata 0x14 (DB-REL 20) -----------------------------------------
    for idx in (0, 1, 2):
        dec_a14(ctx, idx)
    dec_b(ctx, 0x14)
    dec_c(ctx)
    dec_d(ctx)
    dec_e(ctx)
    if ent(11).count:
        dec_f(ctx)
    dec_text(ctx)

    if ctx.dbrel < 0x15:
        return
    # --- passata 0x15 (DB-REL 21) -----------------------------------------
    ctx.pb["s13"] = bits_needed(ent(13).count + 1)
    dec_a15_s0(ctx)
    dec_b(ctx, 0x15)
    dec_s13(ctx)

    if ctx.dbrel < 0x17:
        return
    # --- passata 0x17 (DB-REL 23) -----------------------------------------
    dec_s14(ctx)
    dec_a17_s2(ctx)
    dec_a17_s1(ctx)
    dec_a17_s0(ctx)
    if ctx.g(1):
        dec_text(ctx)
    if ctx.g(1):
        dec_text(ctx)

    if ctx.dbrel < 0x1B:
        return
    # --- passata 0x1B (DB-REL 27), RR sub_005e6c +0x6e70 -------------------
    dec_b(ctx, 0x1B)


class _Enc00:
    """State for encode_type00: the target block, a shadow of what the decoder
    has written so far, and the bit writer. Every inherit flag is chosen by
    comparing the target with the shadow, so the decoder's copy-previous rules
    are followed exactly without special cases. The first record of a section
    always carries its values, as the discs' own encoder does."""

    def __init__(self, decoded: bytes, table: dict, dbrel: int, subrel: int):
        self.D = decoded
        self.T = table
        self.dbrel = dbrel
        self.subrel = subrel
        self.sh = bytearray(len(decoded))
        self.bw = BitWriter()
        self.pb = bits_needed(len(decoded))
        self.widths = decoded[6:8]
        self.cache_s7 = None             # never inherit into the first record:
        self.cache_s2 = None             # the firmware's buffer need not start zeroed

    # ---- primitives --------------------------------------------------------
    def entry(self, idx: int) -> Entry:
        off, count = struct.unpack_from(">HH", self.D, self.T[T_DESC_BASE] + 4 * idx)
        return Entry(off, count)

    def rw(self, off: int) -> int:
        return struct.unpack_from(">H", self.D, off)[0]

    def srw(self, off: int) -> int:
        return struct.unpack_from(">H", self.sh, off)[0]

    def w(self, off: int, val: int) -> None:
        struct.pack_into(">H", self.sh, off, val & 0xFFFF)

    def put(self, width: int, val: int, what: str) -> None:
        if val < 0 or (width < 32 and val >> width):
            raise Cf1Error(f"{what}: {val:#x} does not fit in {width} bits")
        self.bw.put(width, val)

    def same(self, *spans) -> bool:
        return all(self.D[o:o + n] == self.sh[o:o + n] for o, n in spans)

    def even(self, off: int, what: str) -> None:
        """A field read as g(pb - 1) << 1."""
        v = self.rw(off)
        if v & 1:
            raise Cf1Error(f"{what} at {off:#x}: odd value {v:#x}")
        self.put(self.pb - 1, v >> 1, what)
        self.w(off, v)

    def index(self, off: int, e: Entry, rec: int, bits: int, what: str) -> None:
        """A field read as e.off + g(bits) * rec."""
        v = self.rw(off)
        d = (v - e.off) & 0xFFFF
        if d % rec:
            raise Cf1Error(f"{what} at {off:#x}: {v:#x} is not a record of the section at {e.off:#x}")
        self.put(bits, d // rec, what)
        self.w(off, v)

    def delta(self, off: int, prev: int) -> None:
        """Inverse of _delta."""
        v, width = self.rw(off), self.widths[1]
        up, down = (v - prev) & 0xFFFF, (prev - v) & 0xFFFF
        if not up >> width:
            self.bw.put(1, 0); self.bw.put(width, up)
        elif not down >> width:
            self.bw.put(1, 1); self.bw.put(1, 0); self.bw.put(width, down)
        else:
            self.bw.put(1, 1); self.bw.put(1, 1); self.bw.put(16, v)
        self.w(off, v)

    def walk(self, idx: int, rec: int):
        e = self.entry(idx)
        cur, end, prev = e.off, e.off + e.count * rec, -1
        while cur < end:
            yield cur, prev, cur == e.off
            prev, cur = cur, cur + rec

    # ---- pass 0x14 ---------------------------------------------------------
    def a14(self, idx: int) -> None:
        for cur, prev, _first in self.walk(idx, self.T[T_REC_S0]):
            if idx == 0:                          # read and discarded by the decoder; the discs
                if prev < 0:                      # give the first record (0, 0), the rest inherit
                    self.bw.put(1, 1); self.bw.put(self.pb, 0); self.bw.put(self.pb - 1, 0)
                else:
                    self.bw.put(1, 0)
            else:
                if prev >= 0:                     # flag 0: copy the previous record's +2/+4
                    self.sh[cur + 2:cur + 6] = self.sh[prev + 2:prev + 6]
                if prev >= 0 and self.same((cur + 2, 4)):
                    self.bw.put(1, 0)
                else:
                    self.bw.put(1, 1)
                    self.put(self.pb, self.rw(cur + 2), f"S{idx} +2")
                    self.w(cur + 2, self.rw(cur + 2))
                    self.even(cur + 4, f"S{idx} +4")
            self.put(self.pb, self.rw(cur), f"S{idx} +0")
            self.w(cur, self.rw(cur))

    def b14(self) -> None:
        T, D, bw = self.T, self.D, self.bw
        e4 = self.entry(4)
        e2, e7, e10, e11, e12 = (self.entry(i) for i in (2, 7, 10, 11, 12))
        rec, tail = T[T_REC_S4], T[T_TAIL_S4]
        pbits = {"s2": bits_needed(e2.count), "s4": bits_needed(e4.count + 1),
                 "s7": bits_needed(e7.count + 1), "s10": bits_needed(e10.count + 1),
                 "s11": bits_needed(e11.count + 1), "s12": bits_needed(e12.count + 1)}
        self.pbits = pbits
        start, end = e4.off, e4.off + e4.count * rec
        ptr_spans = lambda at: ((at + 0x12, 2), (at + 0x14, 2), (at + tail + 4, 2))

        def ptr_group(at: int) -> None:
            self.index(at + 0x12, e10, T[T_REC_S10], pbits["s10"], "S4 +0x12")
            self.index(at + 0x14, e12, T[T_REC_S12], pbits["s12"], "S4 +0x14")
            self.index(at + tail + 4, e11, T[T_REC_S11], pbits["s11"], "S4 tail+4")

        def s7(at: int) -> None:
            v = self.rw(at + 4)
            if v == self.cache_s7:
                bw.put(1, 0)
            else:
                bw.put(1, 1)
                self.index(at + 4, e7, T[T_REC_S7], pbits["s7"], "S4 +4")
                self.cache_s7 = v
            self.w(at + 4, v)

        cur, prev = start, -1
        while cur < end:
            if cur != start:
                self.sh[cur:cur + rec] = self.sh[prev:prev + rec]
            if cur != start and self.same(*ptr_spans(cur)):
                bw.put(1, 0)
            else:
                bw.put(1, 1); ptr_group(cur)
            grp = ((cur + 0x0A, 2), (cur + 0x10, 2), (cur + tail + 2, 2))
            if cur != start and self.same(*grp):
                bw.put(1, 0)
            else:
                bw.put(1, 1)
                for o in (0x0A, 0x0B, 0x10, 0x11):
                    bw.put(8, D[cur + o]); self.sh[cur + o] = D[cur + o]
                bw.put(16, self.rw(cur + tail + 2)); self.w(cur + tail + 2, self.rw(cur + tail + 2))
            self.even(cur + 0, "S4 +0")
            self.even(cur + 2, "S4 +2")
            s7(cur)
            for o in (0x06, 0x08):
                v = self.rw(cur + o)
                if v == 0:
                    self.put(pbits["s4"], e4.count, "S4 link")
                    self.w(cur + o, 0)
                else:
                    self.index(cur + o, e4, rec, pbits["s4"], "S4 link")
            v = self.rw(cur + 0x0C)
            if v >> self.widths[0]:
                bw.put(1, 1); bw.put(16, v)
            else:
                bw.put(1, 0); bw.put(self.widths[0], v)
            self.w(cur + 0x0C, v)
            for o in (0x0E, 0x0F):
                bw.put(8, D[cur + o]); self.sh[cur + o] = D[cur + o]
            v = self.rw(cur + tail)
            if v == self.cache_s2:
                bw.put(1, 0)
            else:
                bw.put(1, 1)
                self.index(cur + tail, e2, T[T_REC_S0], pbits["s2"], "S4 tail+0")
                self.cache_s2 = v
            self.w(cur + tail, v)
            prev, cur = cur, cur + rec
        # sentinel record: not a copy of the previous one; flag 0 copies only the pointer group
        if prev >= 0:
            for o, n in ptr_spans(cur):
                self.sh[o:o + n] = self.sh[o - cur + prev:o - cur + prev + n]
        if prev >= 0 and self.same(*ptr_spans(cur)):
            bw.put(1, 0)
        else:
            bw.put(1, 1); ptr_group(cur)
        s7(cur)

    def xy(self, idx: int, rec: int, extra: bool) -> None:
        e4 = self.entry(4)
        for cur, prev, first in self.walk(idx, rec):
            if prev >= 0:
                self.sh[cur + 6:cur + 8] = self.sh[prev + 6:prev + 8]
            if prev >= 0 and self.same((cur + 6, 2)):
                self.bw.put(1, 0)
            else:
                self.bw.put(1, 1)
                self.put(8, self.D[cur + 6], f"S{idx} +6")
                self.put(3, self.D[cur + 7], f"S{idx} +7")
                self.sh[cur + 6:cur + 8] = self.D[cur + 6:cur + 8]
            self.coords(cur, prev, first)
            self.index(cur + 4, e4, self.T[T_REC_S4], self.pbits["s4"], f"S{idx} +4")
            if extra:
                o5 = self.T[T_REC_S5]
                self.bw.put(32, struct.unpack_from(">I", self.D, cur + o5)[0])
                self.sh[cur + o5:cur + o5 + 4] = self.D[cur + o5:cur + o5 + 4]
                self.put(16 if self.subrel >= 9 else 14, self.rw(cur + o5 + 4), f"S{idx} +{o5 + 4}")
                self.w(cur + o5 + 4, self.rw(cur + o5 + 4))

    def coords(self, cur: int, prev: int, first: bool) -> None:
        for o in (0, 2):
            if first:
                self.bw.put(16, self.rw(cur + o)); self.w(cur + o, self.rw(cur + o))
            else:
                self.delta(cur + o, self.rw(prev + o))

    def e7(self) -> None:
        for cur, prev, first in self.walk(7, self.T[T_REC_S7]):
            self.coords(cur, prev, first)
            self.put(3, self.D[cur + 4], "S7 +4")
            self.sh[cur + 4] = self.D[cur + 4]

    def f11(self) -> None:
        for cur, _prev, _first in self.walk(11, self.T[T_REC_S11]):
            for o in (0, 2):
                self.put(self.pb, self.rw(cur + o), f"S11 +{o}"); self.w(cur + o, self.rw(cur + o))
            self.put(1, self.rw(cur + 4), "S11 +4"); self.w(cur + 4, self.rw(cur + 4))

    def text(self) -> None:
        start = _layout_end(self.D, self.T, self.dbrel)
        end = text_end(self.D, start)
        enc_text(self.bw, self.D, start, end, self.pb)
        self.sh[start:end + 1] = self.D[start:end + 1]

    # ---- pass 0x15 ---------------------------------------------------------
    def a15_s0(self) -> None:
        for cur, prev, _first in self.walk(0, self.T[T_REC_S0]):
            if prev >= 0:
                self.sh[cur + 2:cur + 4] = self.sh[prev + 2:prev + 4]
            if prev >= 0 and self.same((cur + 2, 2)):
                self.bw.put(1, 0)
            else:
                self.bw.put(1, 1); self.bw.put(16, self.rw(cur + 2)); self.w(cur + 2, self.rw(cur + 2))

    def b15(self) -> None:
        """Section 4 +0x16, including the sentinel record (Mk3 +0x3c50)."""
        e4, e13 = self.entry(4), self.entry(13)
        bits = bits_needed(e13.count + 1)
        rec = self.T[T_REC_S4]
        cur, prev = e4.off, -1
        for cur, prev, _first in self.walk(4, rec):
            self.s13_ptr(cur, prev, e13, bits)
        cur, prev = (cur + rec, cur) if e4.count else (e4.off, -1)
        self.s13_ptr(cur, prev, e13, bits)

    def s13_ptr(self, cur: int, prev: int, e13: Entry, bits: int) -> None:
        if prev >= 0:
            self.sh[cur + 0x16:cur + 0x18] = self.sh[prev + 0x16:prev + 0x18]
        if prev >= 0 and self.same((cur + 0x16, 2)):
            self.bw.put(1, 0)
        else:
            self.bw.put(1, 1)
            self.index(cur + 0x16, e13, self.T[T_REC_S13], bits, "S4 +0x16")

    # ---- pass 0x1B ---------------------------------------------------------
    def b1b(self) -> None:
        """Section 4 +0x18/+0x19 (RR sub_005594 +0x5b5c); no sentinel."""
        for cur, prev, _first in self.walk(4, self.T[T_REC_S4]):
            if prev >= 0:
                self.sh[cur + 0x18:cur + 0x1A] = self.sh[prev + 0x18:prev + 0x1A]
            if prev >= 0 and self.same((cur + 0x18, 2)):
                self.bw.put(1, 0)
            else:
                self.bw.put(1, 1)
                self.bw.put(8, self.D[cur + 0x18]); self.bw.put(8, self.D[cur + 0x19])
                self.sh[cur + 0x18:cur + 0x1A] = self.D[cur + 0x18:cur + 0x1A]

    def s13(self) -> None:
        for cur, _prev, _first in self.walk(13, self.T[T_REC_S13]):
            self.bw.put(32, struct.unpack_from(">I", self.D, cur)[0])
            self.put(self.pb, self.rw(cur + 4), "S13 +4")
            self.bw.put(8, self.D[cur + 6]); self.bw.put(8, self.D[cur + 7])
            self.sh[cur:cur + 8] = self.D[cur:cur + 8]

    # ---- pass 0x17 ---------------------------------------------------------
    def s14(self) -> None:
        for cur, prev, _first in self.walk(14, self.T[T_REC_S14]):
            if prev >= 0:
                self.sh[cur:cur + 4] = self.sh[prev:prev + 4]
            for o, n, width in ((0, 2, self.pb), (2, 1, 8), (3, 1, 5)):
                if prev >= 0 and self.same((cur + o, n)):
                    self.bw.put(1, 0)
                else:
                    v = self.rw(cur) if n == 2 else self.D[cur + o]
                    self.bw.put(1, 1); self.put(width, v, f"S14 +{o}")
                    self.sh[cur + o:cur + o + n] = self.D[cur + o:cur + o + n]

    def a17_s2(self) -> None:
        step, acc = [0, 0], [0, 0]
        for cur, _prev, first in self.walk(2, self.T[T_REC_S0]):
            for k, off in enumerate((6, 8)):
                need = (self.rw(cur + off) - acc[k]) & 0xFFFF
                if need == step[k] and not first:
                    self.bw.put(1, 0)
                else:
                    if need & 1:
                        raise Cf1Error(f"S2 +{off} at {cur:#x}: odd step {need:#x}")
                    self.bw.put(1, 1); self.put(self.pb - 1, need >> 1, f"S2 +{off} step")
                    step[k] = need
                acc[k] = (step[k] + acc[k]) & 0xFFFF
                self.w(cur + off, acc[k])

    def a17(self, idx: int, offs) -> None:
        for cur, _prev, _first in self.walk(idx, self.T[T_REC_S0]):
            for o in offs:
                self.even(cur + o, f"S{idx} +{o}")


def _layout_end(decoded: bytes, table: dict, dbrel: int) -> int:
    """First byte past every record section of a decoded 0x00 block,
    counting the extra record of sections 3 and 4 (where the name blob starts)."""
    base = table[T_DESC_BASE]
    recs = dict(_SECT_REC)
    if dbrel >= 0x17:
        recs[14] = T_REC_S14
    hi = 0
    for idx, key in recs.items():
        off, count = struct.unpack_from(">HH", decoded, base + 4 * idx)
        if idx in (12, 13) and not count:
            continue
        if idx == 13 and dbrel < 0x15:
            continue
        n = count + (1 if idx in (3, 4) else 0)
        if n and key in table:
            hi = max(hi, off + n * table[key])
    return hi


def encode_type00(decoded: bytes, table: dict, dbrel: int, subrel: int = 9,
                  sector_size: int = SECTOR) -> bytes:
    """Re-encode a decoded 0x00 block (as returned by decode_block) to CF=1 raw bytes.

    Mirrors decode_type00 pass by pass. The bits need not match the original
    encoder's (no text dictionary, inherit flags chosen afresh), but
    decode_block(result) == decoded, bytes [4:]. Values the stream cannot
    carry raise Cf1Error.
    """
    if len(decoded) % sector_size:
        raise Cf1Error("decoded length is not a whole number of sectors")
    x = _Enc00(decoded, table, dbrel, subrel)
    T = table
    ent = x.entry
    prolog = bytearray(decoded[:T[T_PROLOG]])
    prolog[6] = 1
    prolog[7] = len(decoded) // sector_size
    head = bytes(prolog) + bytes(x.widths)
    for idx, key, plus1 in ((3, T_REC_S3, True), (9, T_REC_S9, False), (10, T_REC_S10, False),
                            (12, T_REC_S12, False)):
        e = ent(idx)
        if idx == 12 and not e.count:
            continue
        n = e.count * T[key] + (T[key] if plus1 else 0)
        head += decoded[e.off:e.off + n]
        x.sh[e.off:e.off + n] = decoded[e.off:e.off + n]
    x.sh[:len(prolog)] = decoded[:len(prolog)]

    for idx in (0, 1, 2):
        x.a14(idx)
    x.b14()
    x.xy(5, T[T_REC_S5], False)
    x.xy(6, T[T_REC_S6], True)
    x.e7()
    if ent(11).count:
        x.f11()
    x.text()
    if dbrel >= 0x15:
        x.a15_s0()
        x.b15()
        x.s13()
    if dbrel >= 0x17:
        x.s14()
        x.a17_s2()
        x.a17(1, (6, 8))
        x.a17(0, (4,))
        x.bw.put(1, 0)
        x.bw.put(1, 0)
    if dbrel >= 0x1B:
        x.b1b()
        x.bw.put(1, 1)          # DB-REL 34 streams end with one 1 bit that no firmware reads
    return head + x.bw.to_bytes()
