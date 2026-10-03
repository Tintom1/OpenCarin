"""Parse one decoded `0x00` street tile into nodes, segments and forbidden turns.

Field meanings are the ones in docs/carindb/03-road-network.md §6.7 (segment record
section 4, nodes sections 5/6, forbidden turns section 10). This module only reads; it
does not decide how the pieces join across tiles (see graph.py).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..parser.cf1.constants import T_REC_S4, T_REC_S5, T_REC_S6, T_REC_S7, T_REC_S10
from ..parser.geometry import VERTEX_SHIFT, _names, _sections, tile_frame

NodeKey = Tuple[int, int]          # (tile sector, in-block byte offset)


@dataclass
class RawNode:
    key: NodeKey
    lon: float
    lat: float
    flags: int                      # +6: bits 15-14 = highest level reached (3 = street only)
    twin: Optional[NodeKey] = None  # section 6 only: node of the neighbouring tile


@dataclass
class RawRestriction:
    target_index: Optional[int]     # segment index in the same tile, None if unresolved
    flag: int                       # 0 = at owner's start node, 1 = at end node, 2/3 = other
    via: NodeKey                    # owner's start (flag 0) or end node (flag 1)


@dataclass
class RawEdge:
    sector: int
    index: int
    start: NodeKey
    end: NodeKey
    coords: List[Tuple[float, float]]
    name: Optional[str]
    locality: Optional[str]
    speed_byte: int                 # +0x0A
    form_byte: int                  # +0x0B
    length_m: int                   # +0x0C
    bearing_start: int              # +0x0E, 1/256 turn
    bearing_end: int                # +0x0F
    class_byte: int                 # +0x10
    junction_byte: int              # +0x11
    slip_byte: int                  # +0x18 (0 when the record has no such byte)
    restrictions: List[RawRestriction] = field(default_factory=list)


@dataclass
class TileData:
    sector: int
    nodes: Dict[NodeKey, RawNode]
    edges: List[RawEdge]
    skipped: int = 0                # segment records dropped by the sanity guards


def parse_tile(sector: int, data: bytes, table: dict) -> Optional[TileData]:
    """Return the tile's graph pieces, or None if the frame / sections are not usable."""
    frame = tile_frame(data, table)
    if frame is None:
        return None
    secs = _sections(data, table)
    (s4, n4), (s5, n5), (s6, n6), (s7, n7) = secs[4], secs[5], secs[6], secs[7]
    s10, n10 = secs[10]
    rec4, rec7 = table.get(T_REC_S4), table.get(T_REC_S7, 6)
    rec5, rec6, rec10 = table.get(T_REC_S5, 8), table.get(T_REC_S6, 16), table.get(T_REC_S10, 8)
    if not rec4 or rec4 < 0x14 or s4 + rec4 * n4 > len(data):
        return None
    end7 = s7 + rec7 * n7
    end10 = s10 + rec10 * n10
    if end7 > len(data) or end10 > len(data):
        return None
    lim_u, lim_v = frame.width >> VERTEX_SHIFT, frame.height >> VERTEX_SHIFT

    nodes: Dict[NodeKey, RawNode] = {}
    for off, n, rec, is_edge in ((s5, n5, rec5, False), (s6, n6, rec6, True)):
        for i in range(n):
            p = off + rec * i
            if p + 8 > len(data):
                continue
            u, v, _first, flags = struct.unpack_from(">HHHH", data, p)
            lon, lat = frame.to_wgs84(u, v)
            twin = None
            if is_edge and rec >= 14:
                bid, toff = struct.unpack_from(">IH", data, p + 8)
                if bid:
                    twin = (bid >> 8, toff)
            nodes[(sector, p)] = RawNode((sector, p), lon, lat, flags, twin)

    ptr7 = [struct.unpack_from(">H", data, s4 + rec4 * i + 4)[0] for i in range(n4)]
    ptr10 = [struct.unpack_from(">H", data, s4 + rec4 * i + 0x12)[0] for i in range(n4)]
    edges: List[RawEdge] = []
    skipped = 0
    for i in range(n4):
        base = s4 + rec4 * i
        a, b = struct.unpack_from(">HH", data, base)
        p0 = ptr7[i]
        p1 = ptr7[i + 1] if i + 1 < n4 else end7
        if (sector, a) not in nodes or (sector, b) not in nodes or not (s7 <= p0 <= p1 <= end7):
            skipped += 1                       # also catches the sentinel record
            continue
        uv = [(nodes[(sector, a)].lon, nodes[(sector, a)].lat)]
        bad = False
        for q in range(p0, p1 - 3, rec7):
            u, v = struct.unpack_from(">HH", data, q)
            if not (0 <= u <= lim_u and 0 <= v <= lim_v):
                bad = True
                break
            uv.append(frame.to_wgs84(u, v))
        if bad:
            skipped += 1
            continue
        uv.append((nodes[(sector, b)].lon, nodes[(sector, b)].lat))
        name, locality = _names(data, table, base, secs[2])
        spd, form, length, bs, be, cls, junc = struct.unpack_from(">BBHBBBB", data, base + 0x0A)
        slip = data[base + 0x18] if rec4 > 0x18 else 0
        edge = RawEdge(sector, i, (sector, a), (sector, b), uv, name, locality,
                       spd, form, length, bs, be, cls, junc, slip)
        q0 = ptr10[i]
        q1 = ptr10[i + 1] if i + 1 < n4 else end10
        if s10 <= q0 <= q1 <= end10:
            for q in range(q0, q1 - rec10 + 1, rec10):
                bid, toff, flag = struct.unpack_from(">IHH", data, q)
                tidx = None
                if bid >> 8 == sector and toff >= s4 and (toff - s4) % rec4 == 0:
                    t = (toff - s4) // rec4
                    tidx = t if t < n4 else None
                via = edge.start if flag == 0 else edge.end
                edge.restrictions.append(RawRestriction(tidx, flag, via))
        edges.append(edge)
    return TileData(sector, nodes, edges, skipped)
