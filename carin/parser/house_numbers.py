"""House numbers per road segment, from BLOCK_TYPE 0x04 blocks.

A type 0x04 block (CF=0 or CF=2, never CF=1 on the DVDs) belongs to one type
0x00 tile and holds one record per SECTION_4 segment of that tile, in the same
order (03-road-network.md §6.4):

    +0x08  SECTION_DESCRIPTOR[1] = {0x0010, N}   N = tile e4 count
    +0x0C  u32 BLOCK_ID of the linked 0x00 tile
    +0x10  N records of 10 bytes: u16 f0 f1 f2 f3 f4

(f0, f2) is one side of the segment, (f1, f3) the other; 0x7FFF = no number.
f4 is the numbering scheme: 0 none, 1 mixed (a side runs through both
parities), 2 odd/even split (each side one parity).

The even/odd ranges of a 0x0E S2 link (decode_s2_links) are the envelope of
these ranges over the linked SECTION_4 run: run_envelope() reproduces them for
98.8% of 29,496 links on CD-ID 21708
(scripts/routing/check_04_house_numbers.py).

Not known yet: which side is left or right of the segment direction, and
whether f0/f1 are the numbers at the start node.
"""
from __future__ import annotations

import struct
from typing import List, Optional, Sequence, Tuple

NONE = 0x7FFF
REC_SIZE = 10          # CC-93 rpmod uses 8 (four fields); DB-REL 34 discs have five

SCHEME_NONE = 0
SCHEME_MIXED = 1
SCHEME_ODD_EVEN = 2

Range = Optional[Tuple[int, int]]


def _side(a: int, b: int) -> Range:
    if a == NONE and b == NONE:
        return None
    # one missing end defaults to the other (CC-93 rpmod fill-in, 0x014134)
    return (b if a == NONE else a, a if b == NONE else b)


def tile_block_id(data: bytes) -> int:
    """BLOCK_ID of the type 0x00 tile a decoded 0x04 block belongs to."""
    return struct.unpack_from(">I", data, 0x0C)[0]


def segment_house_numbers(data: bytes) -> List[dict]:
    """Records of a decoded type 0x04 block, one per SECTION_4 segment.

    Returns dicts {"index", "side_a", "side_b", "scheme"}; a side is
    (first, second) in stored order, or None. "index" is the segment's
    position in the tile's SECTION_4.
    """
    off, cnt = struct.unpack_from(">HH", data, 8)
    out = []
    for i in range(cnt):
        p = off + REC_SIZE * i
        if p + REC_SIZE > len(data):
            break
        f0, f1, f2, f3, f4 = struct.unpack_from(">5H", data, p)
        out.append({
            "index": i,
            "side_a": _side(f0, f2),
            "side_b": _side(f1, f3),
            "scheme": f4,
        })
    return out


def run_envelope(records: Sequence[dict], start: int, count: int) -> Tuple[Range, Range]:
    """(even, odd) house-number ranges of segments start..start+count-1.

    Same summary as the 0x0E S2 +8..+14 fields. A mixed-scheme side
    contributes both parities of its interval.
    """
    ev: List[int] = []
    od: List[int] = []
    for r in records[start:start + count]:
        for side in (r["side_a"], r["side_b"]):
            if side is None:
                continue
            lo, hi = min(side), max(side)
            if r["scheme"] == SCHEME_MIXED:
                e_lo, e_hi = lo + lo % 2, hi - hi % 2
                o_lo, o_hi = lo + 1 - lo % 2, hi - 1 + hi % 2
                if e_lo <= e_hi:
                    ev += [e_lo, e_hi]
                if o_lo <= o_hi:
                    od += [o_lo, o_hi]
            else:
                (ev if lo % 2 == 0 else od).extend([lo, hi])
    return ((min(ev), max(ev)) if ev else None,
            (min(od), max(od)) if od else None)
