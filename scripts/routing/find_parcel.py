"""
Builds and queries a spatial index from S2 anchors.

Allows O(1) geographic lookups to map an arbitrary lon/lat coordinate to the exact 0x0E road parcel sector.

Note (2026-09-28): the S2 "anchors" are the centres of the 0x00 tiles each 0x0E
record links to, so this index finds 0x0E blocks that reference tiles near a point.
The disc's own spatial index is 0x07 -> 0x08 -> 0x09 (docs/carindb/02-geo.md §7.3),
which does not cover 0x0E. See roadmap item A3.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Optional

import numpy as np

from carin.parser.iso import CarinVolume
from carin.parser import cf1

T_DESC_BASE  = cf1.T_DESC_BASE   # 0x05
T_REC_S2_0E  = cf1.T_REC_S2_0E  # 0x42 → 24

_CACHE = Path("dataset/parcel_index.npz")

# ---------------------------------------------------------------------------
# bbox helpers
# ---------------------------------------------------------------------------

def _bbox_from_data(data: bytes, table: dict) -> Optional[tuple]:
    """Return (x_min, y_min, x_max, y_max, cx, cy) from a decoded 0x0E block."""
    base_d = table[T_DESC_BASE]
    e2_off, e2_cnt = struct.unpack_from(">HH", data, base_d + 8)  # section 2
    s2_rec = table[T_REC_S2_0E]

    xs: list[int] = []
    ys: list[int] = []
    for j in range(e2_cnt):
        off = e2_off + j * s2_rec
        if off + 8 > len(data):
            break
        x_anc, y_anc = struct.unpack_from(">ii", data, off)
        if x_anc != 0 or y_anc != 0:
            xs.append(x_anc)
            ys.append(y_anc)

    if not xs:
        return None
    cx = sum(xs) // len(xs)
    cy = sum(ys) // len(ys)
    return (min(xs), min(ys), max(xs), max(ys), cx, cy)


def _bbox_from_raw(raw: bytes, table: dict, comp: int, dbrel: int) -> Optional[tuple]:
    """Decode a raw 0x0E block and return its bbox tuple."""
    try:
        if comp == 2:
            data = raw[:8] + zlib.decompress(raw[8:])
        elif comp == 1:
            data = cf1.decode_block(raw, table, dbrel)
        else:
            data = raw
    except Exception:
        return None
    return _bbox_from_data(data, table)


# ---------------------------------------------------------------------------
# index builder
# ---------------------------------------------------------------------------

def build_index(vol: CarinVolume) -> np.ndarray:
    """Scan every 0x0E block and build the spatial index array.

    Returns an int64 array with columns:
      [sector, x_min, y_min, x_max, y_max, cx, cy]
    """
    table = vol.layout
    dbrel  = vol.db_rel
    rows: list[tuple] = []

    for blk in vol.walk():
        if blk.type != 0x0E:
            continue
        raw = vol.read_sectors(blk.sector, blk.length)
        result = _bbox_from_raw(raw, table, blk.comp, dbrel)
        if result is not None:
            x0, y0, x1, y1, cx, cy = result
            rows.append((blk.sector, x0, y0, x1, y1, cx, cy))

    return np.array(rows, dtype=np.int64)


def _get_index(vol: CarinVolume) -> np.ndarray:
    """Load from cache or build and cache the spatial index."""
    if _CACHE.exists():
        return np.load(_CACHE)["index"]

    print("Building parcel spatial index (scanning 74,247 blocks — ~30 s) …")
    idx = build_index(vol)
    np.savez_compressed(str(_CACHE), index=idx)
    print(f"Index saved to {_CACHE}  ({len(idx)} entries).")
    return idx


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def find_parcel(vol: CarinVolume, x: int, y: int) -> Optional[int]:
    """Return the virtual sector of the 0x0E block that covers (x, y).

    Parameters
    ----------
    vol : CarinVolume
    x, y : int
        CARiN coordinates (X = (lon+30)*K, Y = lat*K).

    Returns
    -------
    int | None
        Virtual sector, or None if the index is empty.
    """
    idx = _get_index(vol)
    if len(idx) == 0:
        return None

    secs = idx[:, 0]
    x0s  = idx[:, 1];  y0s = idx[:, 2]
    x1s  = idx[:, 3];  y1s = idx[:, 4]
    cxs  = idx[:, 5];  cys = idx[:, 6]

    # blocks whose anchor bbox contains the query point
    mask = (x0s <= x) & (x <= x1s) & (y0s <= y) & (y <= y1s)

    if mask.any():
        ii     = np.where(mask)[0]
        dist2  = (cxs[ii] - x) ** 2 + (cys[ii] - y) ** 2
        best   = ii[int(dist2.argmin())]
    else:
        # fallback: nearest centroid in the whole index
        dist2  = (cxs - x) ** 2 + (cys - y) ** 2
        best   = int(dist2.argmin())

    return int(secs[best])
