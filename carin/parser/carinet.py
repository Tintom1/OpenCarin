"""Reader for the `CARINET` file: the RDS-TMC (ALERT-C) event texts.

Layout and evidence: docs/carindb/01-architecture.md §4.5. Checked on a 2007 CD (DB-REL 34,
750,592 bytes): 49 text blocks in 11 text sets, 1,493 event codes, `limit` = last code in 49 / 49
blocks (`scripts/routing/check_carinet.py`). `CARINET` is a CARIN block space of its own: the
512-byte unit, BLOCK_ID = (sector << 8) | length in sectors, the same header as `carindb` blocks.

    0x66 root (sector 0, 2 sectors)   S0: index over the 0x64 chain; S1: the 0x65 blocks
    0x64 event table (a chain)        one record per event code: key, attribute word, short tag
    0x65 text blocks (one chain)      per text set (language): (event code, offset) -> phrase

The text sets are numbered like the `LANGUAGE` of the `0x0A` country records of `carindb`
(1 Dutch, 2 English, 3 French, 4 German, ...), which is how a country picks its phrases.
The attribute word and the key follow the columns of the published ALERT-C event list (checked, §4.5).
Fields that are not decoded are exposed raw.
"""
from __future__ import annotations

import struct
from typing import Dict, List, NamedTuple, Optional

UNIT = 512
ROOT_TYPE, EVENT_TYPE, TEXT_TYPE = 0x66, 0x64, 0x65
NO_QUANTIFIER = 0xF
NATURE = {0: "event", 1: "forecast", 2: "silent"}
DURATION = {1: "D", 2: "(D)", 3: "L", 4: "(L)"}
URGENCY = {0: "", 1: "U", 2: "X"}


class TextBlock(NamedTuple):
    """One S1 record of the root block."""
    block_id: int        # (sector << 8) | length in sectors
    limit: int           # the last (highest) event code in the block
    group: int           # text set: the LANGUAGE id of carindb's 0x0A, see the module docstring


class Event(NamedTuple):
    """One record of a 0x64 block."""
    code: int            # event code 1..0x7FF (ALERT-C event codes are 11 bits)
    key_bits: int        # key >> 11 = directionality << 2 | nature, see the properties
    attrs: int           # u16 attribute word, see the properties (bit 15 is never set)
    tag: str             # the event's phrase code in the published list ("A50", "A2.A1D"); empty for silent events

    @property
    def nature(self) -> str:
        """`key_bits & 3`: 0 event, 1 forecast, 2 silent (a cancellation)."""
        return NATURE.get(self.key_bits & 3, "?")

    @property
    def directionality(self) -> int:
        """`key_bits >> 2`: 1 one direction, 2 both directions, 0 for the silent events."""
        return self.key_bits >> 2

    @property
    def quantifier(self) -> Optional[int]:
        """Low nibble of `attrs`: the quantifier type 1..12, or None for 0xF (no quantifier, type 0 of the list)."""
        q = self.attrs & 0xF
        return None if q == NO_QUANTIFIER else q

    @property
    def duration(self) -> Optional[str]:
        """`attrs` bits 4-6: "D" dynamic, "(D)", "L" longer lasting, "(L)" (brackets as in the published list), None for 0."""
        return DURATION.get((self.attrs >> 4) & 7)

    @property
    def urgency(self) -> str:
        """`attrs` bits 7-8: "" none, "U" urgent, "X" extremely urgent."""
        return URGENCY.get((self.attrs >> 7) & 3, "?")

    @property
    def update_class(self) -> int:
        """`attrs` bits 9-14: the update class, 1..39."""
        return (self.attrs >> 9) & 0x3F


class Carinet(NamedTuple):
    blocks: List[TextBlock]
    events: Dict[int, Event]                 # by event code
    texts: Dict[int, Dict[int, str]]         # text set -> event code -> phrase

    def phrase(self, group: int, code: int) -> Optional[str]:
        return self.texts.get(group, {}).get(code)


def _block(data: bytes, block_id: int, expect_type: int) -> bytes:
    start, size = (block_id >> 8) * UNIT, (block_id & 0xFF) * UNIT
    blk = data[start:start + size]
    if len(blk) != size or struct.unpack_from(">IH", blk, 0) != (block_id, expect_type):
        raise ValueError("block %#x is not a %#x block" % (block_id, expect_type))
    return blk


def _string(blk: bytes, offset: int) -> str:
    end = blk.index(b"\0", offset)
    return blk[offset:end].decode("latin-1")


def parse_events(blk: bytes) -> List[Event]:
    """The records of one 0x64 block: `{u16 offset, u16 count}` at +0x08, then (key, attrs, string offset)."""
    off, cnt = struct.unpack_from(">HH", blk, 8)
    out = []
    for i in range(cnt):
        key, attrs, s = struct.unpack_from(">HHH", blk, off + 6 * i)
        out.append(Event(key & 0x7FF, key >> 11, attrs, _string(blk, s)))
    return out


def parse_texts(blk: bytes) -> Dict[int, str]:
    """The records of one 0x65 block: (event code, offset of the phrase in the block), ascending by code."""
    off, cnt = struct.unpack_from(">HH", blk, 8)
    out = {}
    for i in range(cnt):
        code, s = struct.unpack_from(">HH", blk, off + 4 * i)
        out[code] = _string(blk, s)
    return out


def read_carinet(data: bytes) -> Carinet:
    """Decode a whole CARINET file. Raises ValueError when the structure does not hold."""
    if struct.unpack_from(">IH", data, 0) != (2, ROOT_TYPE):
        raise ValueError("not a CARINET root block")
    (s0, n0), (s1, n1) = struct.unpack_from(">HH", data, 8), struct.unpack_from(">HH", data, 12)
    blocks = []
    for i in range(n1):
        block_id, limit, group, _ = struct.unpack_from(">IHBB", data, s1 + 8 * i)
        blocks.append(TextBlock(block_id, limit, group))

    events: Dict[int, Event] = {}
    block_id = struct.unpack_from(">I", data, s0)[0]        # S0[0]: the first 0x64 block
    while block_id:
        blk = _block(data, block_id, EVENT_TYPE)
        for ev in parse_events(blk):
            events[ev.code] = ev
        block_id = struct.unpack_from(">I", blk, 0x0C)[0]    # +0x0C: next block of the chain

    texts: Dict[int, Dict[int, str]] = {}
    for b in blocks:
        texts.setdefault(b.group, {}).update(parse_texts(_block(data, b.block_id, TEXT_TYPE)))
    return Carinet(blocks, events, texts)
