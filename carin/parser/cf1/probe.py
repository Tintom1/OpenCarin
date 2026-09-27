"""Per-disc parameter detection for the CF=1 codec.

Two decode parameters are not stored anywhere we can read from the block
itself and vary between discs, even between discs with the same DB-REL:

- the sub-revision (``subrel``, LAYOUT[+2]): it only switches one section 6
  field between 14 and 16 bits (``subrel >= 9``), but a wrong choice
  desynchronises the stream for the rest of the block;
- the sector unit that ``usize`` is counted in (512 on the DB_0/DB_1 DVD
  layout, 2048 on single-file ``carindb`` CD discs).

Both can be recovered from the data with a structural check that a wrong
decode essentially never passes: in a type 0x00 block, each section 4 record
carries at offset 4 a pointer to its first section 7 shape point. In a correct
decode those pointers are non-decreasing, all land inside section 7, and step
in whole section 7 records.
"""
from __future__ import annotations

import struct
from typing import Iterable, Optional

from .constants import T_DESC_BASE, T_REC_S4, T_REC_S7
from .core import Cf1Error

SUBREL_CANDIDATES = (8, 9)   # the decoder only distinguishes subrel < 9 / >= 9


def shape_pointer_score(data: bytes, table: dict[int, int]) -> Optional[float]:
    """Fraction (0..1) of the section-4 -> section-7 invariants that hold.

    Returns None when the block has too few records to say anything.
    """
    desc = table.get(T_DESC_BASE, 8)
    rec4, rec7 = table.get(T_REC_S4), table.get(T_REC_S7, 6)
    if not rec4 or len(data) < desc + 32:
        return None
    s4, n4 = struct.unpack_from(">HH", data, desc + 4 * 4)
    s7, n7 = struct.unpack_from(">HH", data, desc + 7 * 4)
    if n4 < 3 or n7 < 3 or s4 + rec4 * n4 > len(data):
        return None
    ptr = [struct.unpack_from(">H", data, s4 + rec4 * i + 4)[0] for i in range(n4)]
    end7 = s7 + rec7 * n7
    mono = sum(a <= b for a, b in zip(ptr, ptr[1:])) / (n4 - 1)
    inside = sum(s7 <= p <= end7 for p in ptr) / n4
    steps = [b - a for a, b in zip(ptr, ptr[1:]) if b != a]
    whole = sum(s % rec7 == 0 for s in steps) / len(steps) if steps else 1.0
    return (mono + inside + whole) / 3


def detect_subrel(raws: Iterable[bytes], table: dict[int, int], dbrel: int,
                  sector_size: int, decode) -> int:
    """Pick the sub-revision under which CF=1 type 0x00 blocks decode cleanly.

    `raws` are on-disk blocks (header included) of type 0x00 with CF=1;
    `decode` is cf1.decode_block (passed in to avoid a circular import).
    """
    raws = list(raws)
    best, best_score = SUBREL_CANDIDATES[-1], -1.0
    for subrel in SUBREL_CANDIDATES:
        scores = []
        for raw in raws:
            try:
                data = decode(raw, table, dbrel, subrel=subrel, sector_size=sector_size)
            except (Cf1Error, IndexError, ValueError, struct.error):
                scores.append(0.0)
                continue
            s = shape_pointer_score(data, table)
            if s is not None:
                scores.append(s)
        if scores:
            score = sum(scores) / len(scores)
            if score > best_score:
                best, best_score = subrel, score
    return best
