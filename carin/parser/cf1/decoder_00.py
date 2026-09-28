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


def enc_text(bw: BitWriter, dst: bytes, start: int, end: int, ptrbits: int) -> None:
    """Inverse of dec_text: write dst[start..end] (end inclusive) as a name blob.

    No dictionary words are used (all six are empty), so the output can be
    longer than the original encoder's but decodes to the same bytes. An empty
    range (end < start) writes the (0, 0) "no blob" marker.
    """
    if end < start:
        bw.put(ptrbits, 0)
        bw.put(ptrbits, 0)
        return
    bw.put(ptrbits, start)
    bw.put(ptrbits, end)
    for _ in range(6):
        bw.put(5, 0)
    for p in range(start, end + 1):
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
