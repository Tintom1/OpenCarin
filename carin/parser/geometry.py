"""Georeferenced road geometry from decoded BLOCK_TYPE 0x00 blocks.

A type 0x00 block (after CF=1 decoding, or as-is when CF=0) carries:

- section 4: road segments, record T[0x08]. Per record:
    +0x00  start node   -> section 5 (node inside the tile) or section 6
    +0x02  end node        (node shared with a neighbouring tile)
    +0x04  first shape point -> section 7; the segment's shape points run up
           to the next record's pointer (or the end of section 7)
    +0x10  display class byte
    +T[0x09]  pointer -> section 2 record (name reference)
- section 2: record T[0x40]; its first word is an in-block byte offset of a
  NUL-terminated road name.
- sections 5 and 6: nodes, (u16 x, u16 y) first. Section 6 nodes sit on the
  tile edge and are what joins roads across tiles; both are in this tile's
  own frame.
- section 7: shape points, (u16 x, u16 y) first, record T[0x0c].

Local coordinates are tile-relative, in units of 64 CARIN units (x east,
y north). The tile frame follows the section descriptor (T[0x05] + 15*4) and
comes in two forms:

- four u32 (x0, y0, x1, y1): a full box, X = longitude. Seen on CD-ID 21594.
- three u32 (y0, x1, y1): latitude extent plus the EAST longitude edge; the
  longitude extent is not stored and is either equal to the latitude extent
  or twice it (tiles are square or 2:1). Seen on CD-ID 2952.

The form is recognised from the fields themselves (a valid 1:1 / 2:1 box or
not), not inferred from the DB-REL.

Verified on two CD discs (CD-ID 2952 and CD-ID 21594) against OpenStreetMap:
on CD-ID 21594, 88.7% of OSM road vertices in a test area have a
decoded segment within 40 m; named streets land within tens of metres of
their OSM position.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .cf1.constants import (T_DESC_BASE, T_REC_S0, T_REC_S4, T_REC_S5,
                            T_REC_S6, T_REC_S7, T_TAIL_S4)
from .iso import to_wgs84

VERTEX_SHIFT = 6          # local coordinate unit = 64 CARIN units
N_SECTIONS = 15


@dataclass(frozen=True)
class TileFrame:
    x0: int               # west edge, CARIN units
    y0: int               # south edge, CARIN units
    width: int            # longitude extent, CARIN units
    height: int           # latitude extent, CARIN units

    def to_wgs84(self, u: int, v: int) -> Tuple[float, float]:
        return to_wgs84(self.x0 + (u << VERTEX_SHIFT), self.y0 + (v << VERTEX_SHIFT))

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        lon0, lat0 = to_wgs84(self.x0, self.y0)
        lon1, lat1 = to_wgs84(self.x0 + self.width, self.y0 + self.height)
        return lon0, lat0, lon1, lat1


def _sections(data: bytes, table: dict) -> List[Tuple[int, int]]:
    desc = table.get(T_DESC_BASE, 8)
    return [struct.unpack_from(">HH", data, desc + 4 * i) for i in range(N_SECTIONS)]


def _bbox_fields(data: bytes, table: dict) -> Tuple[int, int, int, int]:
    return struct.unpack_from(">4I", data, table.get(T_DESC_BASE, 8) + 4 * N_SECTIONS)


def _is_full_box(x0: int, y0: int, x1: int, y1: int) -> bool:
    w, h = x1 - x0, y1 - y0
    return w > 0 and h > 0 and (w == h or w == 2 * h or h == 2 * w)


def _max_local(data: bytes, table: dict) -> Tuple[int, int]:
    s7, n7 = _sections(data, table)[7]
    rec7 = table.get(T_REC_S7, 6)
    mx = my = 0
    for i in range(n7):
        p = s7 + rec7 * i
        if p + 4 > len(data):
            break
        x, y = struct.unpack_from(">HH", data, p)
        mx, my = max(mx, x), max(my, y)
    return mx, my


def header_bounds(data: bytes, table: dict) -> Optional[Tuple[float, float, float, float]]:
    """Conservative WGS84 bounds from the plaintext prologue alone.

    Works on raw (still packed) blocks too, since the prologue is copied
    verbatim. For the three-field form the west edge is not known without the
    geometry, so the box is widened to the largest possible (2:1) extent.
    """
    f0, f1, f2, f3 = _bbox_fields(data, table)
    if _is_full_box(f0, f1, f2, f3):
        lon0, lat0 = to_wgs84(f0, f1)
        lon1, lat1 = to_wgs84(f2, f3)
        return lon0, lat0, lon1, lat1
    h = f2 - f0
    if h <= 0:
        return None
    lon0, lat0 = to_wgs84(f1 - 2 * h, f0)
    lon1, lat1 = to_wgs84(f1, f2)
    return lon0, lat0, lon1, lat1


def tile_frame(data: bytes, table: dict) -> Optional[TileFrame]:
    """Resolve the tile's frame, deriving the unstored extent if needed."""
    f0, f1, f2, f3 = _bbox_fields(data, table)
    if _is_full_box(f0, f1, f2, f3):
        return TileFrame(f0, f1, f2 - f0, f3 - f1)
    # three-field form: (y0, east x1, y1)
    span = f2 - f0
    if span <= 0:
        return None
    mx, my = _max_local(data, table)
    width = span if (mx << VERTEX_SHIFT) <= span else 2 * span
    height = span if (my << VERTEX_SHIFT) <= span else 2 * span
    if (mx << VERTEX_SHIFT) > width or (my << VERTEX_SHIFT) > height:
        return None                     # beyond 2:1: not a tile shape
    return TileFrame(f1 - width, f0, width, height)


def _name(data: bytes, table: dict, rec_off: int, sec2: Tuple[int, int]) -> Optional[str]:
    tail = table.get(T_TAIL_S4)
    rec2 = table.get(T_REC_S0)
    if tail is None or not rec2:
        return None
    s2, n2 = sec2
    ref = struct.unpack_from(">H", data, rec_off + tail)[0]
    if not (s2 <= ref < s2 + rec2 * n2 and (ref - s2) % rec2 == 0):
        return None
    ptr = struct.unpack_from(">H", data, ref)[0]
    if not 0 < ptr < len(data):
        return None
    end = data.find(b"\x00", ptr, ptr + 64)
    if end <= ptr:
        return None
    text = data[ptr:end].decode("latin-1")
    return text if any(c.isalpha() for c in text) else None


def road_segments(data: bytes, table: dict) -> List[dict]:
    """Road segments of a decoded type 0x00 block, in WGS84.

    Returns dicts: {"index", "name", "display_class", "coords": [(lon, lat), ...]}.
    Segments whose points fall outside the tile are dropped (misparse guard).
    """
    frame = tile_frame(data, table)
    if frame is None:
        return []
    secs = _sections(data, table)
    (s4, n4), (s5, n5), (s6, n6), (s7, n7) = secs[4], secs[5], secs[6], secs[7]
    rec4, rec7 = table.get(T_REC_S4), table.get(T_REC_S7, 6)
    if not rec4 or s4 + rec4 * n4 > len(data):
        return []
    end7 = s7 + rec7 * n7
    if end7 > len(data):
        return []
    lim_u, lim_v = frame.width >> VERTEX_SHIFT, frame.height >> VERTEX_SHIFT

    nodes = {}
    for off, n, rec in ((s5, n5, table.get(T_REC_S5, 8)), (s6, n6, table.get(T_REC_S6, 16))):
        for i in range(n):
            p = off + rec * i
            if p + 4 <= len(data):
                nodes[p] = struct.unpack_from(">HH", data, p)

    ptrs = [struct.unpack_from(">H", data, s4 + rec4 * i + 4)[0] for i in range(n4)]
    out = []
    for i in range(n4):
        base = s4 + rec4 * i
        a, b = struct.unpack_from(">HH", data, base)
        p0 = ptrs[i]
        p1 = ptrs[i + 1] if i + 1 < n4 else end7
        if not (s7 <= p0 <= p1 <= end7):
            continue
        pts = []
        if a in nodes:
            pts.append(nodes[a])
        pts += [struct.unpack_from(">HH", data, q) for q in range(p0, p1 - 3, rec7)]
        if b in nodes:
            pts.append(nodes[b])
        if len(pts) < 2 or any(not (0 <= u <= lim_u and 0 <= v <= lim_v) for u, v in pts):
            continue
        out.append({
            "index": i,
            "name": _name(data, table, base, secs[2]),
            "display_class": data[base + 0x10],
            "coords": [frame.to_wgs84(u, v) for u, v in pts],
        })
    return out
