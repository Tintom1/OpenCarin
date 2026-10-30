"""TMC location records: block types 0x17 (locations) and 0x18 (table index), and the section 12
reference of the road tiles.

Layout and evidence: docs/carindb/01-architecture.md §4.7 and 03-road-network.md §6.7. Checked on
a 2007 CD (DB-REL 34): 189,973 records in 14 tables, 0 pointer or link failures
(`scripts/routing/check_tmc_locations.py`). Fields that are still open are exposed raw.

A `0x17` payload (header included) is: the 8-byte block header, `+0x0C` u32 next and `+0x10` u32
previous BLOCK_ID of the chain, `+0x14` u16 table id, `+0x16` / `+0x18` u16 first / last location
code, a section descriptor `{u16 offset, u16 count}` at `+0x08`, then `count` records of 100 bytes
and, after them, the NUL-terminated Latin-1 strings the records point to.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Dict, Iterator, List, NamedTuple, Optional, Tuple

from .iso import to_wgs84

RECORD_SIZE = 100
_POINT_OFFSETS = (0x20, 0x38, 0x44, 0x4C, 0x54, 0x5C)
_KINDS = {0: "area", 1: "line"}


def table_id(ltn: int, cc: int) -> int:
    """The id used by 0x18 and by the section 12 flags: (location table number << 4) | RDS country code."""
    return (ltn << 4) | cc


def split_table_id(table: int) -> Tuple[int, int]:
    return table >> 4, table & 0xF


@dataclass
class Location:
    table: int
    code: int
    kind: str                        # "area", "line" or "point" (from `type_bits`)
    type_bits: int                   # +0x02, raw: 0 area, 1 line, others point; the bits are not decoded
    unknown_05: int                  # +0x05, 0..6, not decoded
    road_number: Optional[str]       # +0x06 -> string
    road_name: Optional[str]         # +0x08 -> string
    name: Optional[str]              # +0x0A -> string, always set
    name2: Optional[str]             # +0x0C -> string: point: crossing road; line: end name
    parent: int                      # +0x0E: code of the enclosing area, 0 at the roots
    road: int                        # +0x10: code shared by the points of one road
    prev: int                        # +0x12: previous point on the road (0 at the end)
    next: int                        # +0x14: next point on the road
    first: int                       # +0x18: line only: first point code
    last: int                        # +0x1A: line only: last point code
    points: Tuple[Optional[Tuple[float, float]], ...]   # six (lon, lat) at _POINT_OFFSETS; None = (0, 0)


class BlockHeader(NamedTuple):
    next_block: int
    prev_block: int
    table: int
    first_code: int
    last_code: int


class S12Ref(NamedTuple):
    """One section 12 entry of a road-tile segment: u16 (direction, location code, flags)."""
    direction: int       # 6, 7 or 8; 8 only names line locations
    code: int
    table: int           # flags & 0x3FF
    flag_bits: int       # flags >> 10, not decoded


def decode_s12(entry: bytes) -> S12Ref:
    direction, code, flags = struct.unpack(">HHH", entry)
    return S12Ref(direction, code, flags & 0x3FF, flags >> 10)


def _string(payload: bytes, offset: int, lo: int) -> Optional[str]:
    if offset == 0:
        return None
    if offset < lo or offset >= len(payload):
        raise ValueError("string pointer %#x outside the string area" % offset)
    end = payload.index(b"\0", offset)
    return payload[offset:end].decode("latin-1")


def parse_0x17(payload: bytes) -> Tuple[BlockHeader, List[Location]]:
    """Decode one 0x17 block payload. Raises ValueError on a pointer that leaves the string area."""
    nxt, prv, table, first, last = struct.unpack_from(">IIHHH", payload, 0x0C)
    off, cnt = struct.unpack_from(">HH", payload, 8)
    end = off + RECORD_SIZE * cnt
    locs = []
    for i in range(cnt):
        r = off + RECORD_SIZE * i
        code, bits = struct.unpack_from(">HB", payload, r)
        ptr = struct.unpack_from(">4H", payload, r + 0x06)
        pts = []
        for o in _POINT_OFFSETS:
            x, y = struct.unpack_from(">II", payload, r + o)
            pts.append(to_wgs84(x, y) if (x or y) else None)
        locs.append(Location(
            table, code, _KINDS.get(bits, "point"), bits, payload[r + 5],
            _string(payload, ptr[0], end), _string(payload, ptr[1], end),
            _string(payload, ptr[2], end), _string(payload, ptr[3], end),
            *struct.unpack_from(">4H", payload, r + 0x0E),
            *struct.unpack_from(">2H", payload, r + 0x18), tuple(pts)))
    return BlockHeader(nxt, prv, table, first, last), locs


def parse_0x18(payload: bytes) -> Tuple[int, List[Tuple[int, int]]]:
    """Decode a 0x18 block: (table id, [(0x17 BLOCK_ID, first location code)] in chain order).

    The terminator record `{0, last code + 1, 0}` is dropped.
    """
    off, cnt, table = struct.unpack_from(">HHH", payload, 8)
    recs = [struct.unpack_from(">IHH", payload, off + 8 * i) for i in range(cnt)]
    return table, [(b, first) for b, first, _ in recs if b]


def iter_locations(vol) -> Iterator[Location]:
    """Every location record of a CarinVolume, in chain order of its 0x17 blocks."""
    for b in vol.walk():
        if b.type == 0x17:
            yield from parse_0x17(vol.block(b.sector).payload)[1]


def read_locations(vol) -> Dict[Tuple[int, int], Location]:
    """{(table id, location code): Location} for a whole disc."""
    return {(loc.table, loc.code): loc for loc in iter_locations(vol)}
