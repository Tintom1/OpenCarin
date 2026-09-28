from __future__ import annotations
import struct
from dataclasses import dataclass, field
from .constants import *

class Cf1Error(RuntimeError):
    pass


def bits_needed(n: int) -> int:
    """pbp+0x4a68 — numero di bit per rappresentare 0..n-1, aritmetica a 16 bit."""
    v = n & 0xFFFF
    if v == 1:
        return 1
    v = (v - 1) & 0xFFFF
    out = 0
    while v:
        v >>= 1
        out += 1
    return out


class BitReader:
    """Lettore MSB-first equivalente a ``BFEXTU (aN){offset:width}``."""

    def __init__(self, data: bytes, base: int):
        self.data = data
        self.base = base
        self.pos = 0

    def get(self, width: int) -> int:
        if width <= 0:
            return 0
        start = self.pos
        self.pos += width
        out = 0
        for i in range(start, start + width):
            byte = self.base + (i >> 3)
            bit = 0
            if byte < len(self.data):
                bit = (self.data[byte] >> (7 - (i & 7))) & 1
            out = (out << 1) | bit
        return out

    @property
    def byte_pos(self) -> int:
        return self.base + (self.pos + 7) // 8


@dataclass
class Entry:
    off: int
    count: int


@dataclass
class Cf1Context:
    table: dict[int, int]
    src: bytes
    dst: bytearray
    cursor: int = 0                 # pbp: -0x7108(a6), posizione di lettura raw
    ptrbits: int = 0                # pbp: -0x710c(a6)
    widths: bytes = b"\x00\x00"     # pbp: -0x7142(a6), due byte letti in chiaro
    bits: BitReader | None = None
    pb: dict[str, int] = field(default_factory=dict)
    dbrel: int = 34
    subrel: int = 9                 # LAYOUT[+2], sceglie larghezze di campo
    cache_s7: int = 1               # pbp: -0x7146(a6)
    cache_s2: int = 1               # pbp: -0x7144(a6)
    m_hi: int = 0                   # 0x0E: M_hi dal pre-header (→ decoded[7])
    m_lo: int = 0                   # 0x0E: M_lo dal pre-header (→ decoded[6])
    texts: list = field(default_factory=list)  # (start, end) di ogni dec_text, per gli oracle

    # ---- primitive ---------------------------------------------------------
    def T(self, idx: int) -> int:
        try:
            return self.table[idx]
        except KeyError as exc:  # pragma: no cover - diagnostica
            raise Cf1Error(f"RECORD_SIZE_TABLE priva della voce {idx:#x}") from exc

    def copy_raw(self, dst_off: int, n: int) -> bytes:
        chunk = self.src[self.cursor : self.cursor + n]
        if len(chunk) < n:
            raise Cf1Error(f"stream troncato: servono {n} byte a {self.cursor}")
        if dst_off >= 0:
            self.dst[dst_off : dst_off + n] = chunk
        self.cursor += n
        return chunk

    def entry(self, idx: int) -> Entry:
        base = self.T(T_DESC_BASE) + 4 * idx
        off, count = struct.unpack_from(">HH", self.dst, base)
        return Entry(off, count)

    def copy_section(self, idx: int, recsize: int, plus1: bool) -> None:
        e = self.entry(idx)
        n = e.count * recsize + (recsize if plus1 else 0)
        self.copy_raw(e.off, n)

    def bits_init(self) -> None:
        self.bits = BitReader(self.src, self.cursor)

    def g(self, width: int) -> int:
        assert self.bits is not None
        return self.bits.get(width)

    # ---- accesso ai record -------------------------------------------------
    def w(self, off: int, val: int) -> None:
        struct.pack_into(">H", self.dst, off, val & 0xFFFF)

    def rw(self, off: int) -> int:
        return struct.unpack_from(">H", self.dst, off)[0]

    def b(self, off: int, val: int) -> None:
        self.dst[off] = val & 0xFF

    def l(self, off: int, val: int) -> None:  # noqa: E743
        struct.pack_into(">I", self.dst, off, val & 0xFFFFFFFF)


class BitWriter:
    """MSB-first bit writer — inverse of BitReader (pbp+0x49bc BFEXTU convention)."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._pos = 0

    def put(self, width: int, value: int) -> None:
        if width <= 0:
            return
        for shift in range(width - 1, -1, -1):
            bit = (value >> shift) & 1
            byte_idx = self._pos >> 3
            bit_off  = 7 - (self._pos & 7)
            if byte_idx >= len(self._buf):
                self._buf.append(0)
            if bit:
                self._buf[byte_idx] |= 1 << bit_off
            self._pos += 1

    def to_bytes(self) -> bytes:
        return bytes(self._buf)


def _walk(ctx: Cf1Context, idx: int, recsize: int):
    """Itera (cur, prev, first) sui record di una sezione."""
    e = ctx.entry(idx)
    cur, end, prev = e.off, e.off + e.count * recsize, -1
    while cur < end:
        yield cur, prev, cur == e.off
        prev, cur = cur, cur + recsize


