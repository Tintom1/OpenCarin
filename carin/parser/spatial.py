"""Spatial index: 0x07 layer directory -> 0x08 grid -> 0x09 cell node -> tiles.

Answers "which tile of layer L covers the point (lon, lat)". Layout, as checked on
every block of DVDs 21708 and 21734 by scripts/geo/check_spatial_index.py
(docs/carindb/02-geo.md §7.3):

- 0x07 (sector 3), DB-REL 34: 12 records of 28 bytes at +0x14, one per layer:
  u32 BLOCK_ID of the layer's first 0x08 block, root square as 4 x i32
  (x0, y0, x1, y1), then 4 x u16 parameters (02-geo.md §7.3: param 0 = highest road
  class of a road layer, param 1 = lower scale bound, params 2-3 not read by the RR
  firmware). One record points at
  the 0x1B TMC position index instead of a 0x08 block, with an all-zero square.
- 0x08: S0 at +0x10 = u32 entries; +0x0C u32 = cell side in CARIN units. A layer's
  grid of N x N cells (N = root side / cell side) is split over physically
  consecutive 0x08 blocks, entries concatenated. Entry k is cell
  (x = k // N, y = k % N) from the root's south-west corner; 0 = empty cell,
  otherwise the BLOCK_ID of the cell's 0x09 block.
- 0x09: S0 at +0x14 = u16 pointers, S1 = u32 tile BLOCK_IDs; +0x10 u32 = item
  side. The cell is split into q x q items (q = cell side / item side), again
  column-major; a pointer is the absolute in-block offset of an S1 entry, 0 for
  an empty item. The items pointing at a tile tile its bounding box exactly.

Point-in-cell tests are half-open: a point on a shared edge belongs to the cell
east / north of it.
"""
from __future__ import annotations

import struct
import weakref
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .iso import CarinVolume, to_carin

TYPE_GRID = 0x08
TYPE_CELL = 0x09

DIR_OFFSET = 0x14         # 0x07: first layer record
DIR_RECORDS = 12
DIR_RECORD_SIZE = 28      # DB-REL 34; other releases are not checked
DIR_SECTOR = 3            # 0x07 block

GRID_SIDE = 0x0C          # 0x08: u32 cell side
CELL_SIDE = 0x10          # 0x09: u32 item side


def _bid_sector(bid: int) -> int:
    return bid >> 8


@dataclass(frozen=True)
class Layer:
    index: int                        # position in the 0x07 directory
    grid: int                         # BLOCK_ID of the first 0x08 block
    root: Tuple[int, int, int, int]   # x0, y0, x1, y1 (CARIN units)
    params: Tuple[int, int, int, int]  # see 02-geo.md §7.3 (param 0 ✅ roads, 1 🟡, 2-3 ❓)


def parse_layer_directory(p07: bytes) -> List[Layer]:
    """All 12 records of a DB-REL 34 0x07 block, including the non-grid one."""
    out = []
    for i in range(DIR_RECORDS):
        off = DIR_OFFSET + DIR_RECORD_SIZE * i
        bid, *root = struct.unpack_from(">I4i", p07, off)
        params = struct.unpack_from(">4H", p07, off + 20)
        out.append(Layer(i, bid, tuple(root), params))
    return out


def parse_grid_block(p08: bytes) -> Tuple[int, Tuple[int, ...]]:
    """0x08 block -> (cell side, its slice of the grid entries)."""
    off, cnt = struct.unpack_from(">HH", p08, 8)
    side = struct.unpack_from(">I", p08, GRID_SIDE)[0]
    return side, struct.unpack_from(f">{cnt}I", p08, off)


@dataclass(frozen=True)
class CellNode:
    item_side: int
    pointers: Tuple[int, ...]        # S0: absolute offsets into S1, 0 = empty
    tiles: Tuple[int, ...]           # S1: tile BLOCK_IDs
    s1: int                          # S1 offset

    def tile(self, j: int) -> Optional[int]:
        ptr = self.pointers[j]
        return self.tiles[(ptr - self.s1) // 4] if ptr else None


def parse_cell(p09: bytes) -> CellNode:
    (o0, c0), (o1, c1) = struct.unpack_from(">HH", p09, 8), struct.unpack_from(">HH", p09, 12)
    return CellNode(
        item_side=struct.unpack_from(">I", p09, CELL_SIDE)[0],
        pointers=struct.unpack_from(f">{c0}H", p09, o0),
        tiles=struct.unpack_from(f">{c1}I", p09, o1),
        s1=o1,
    )


def cell_index(x: int, y: int, x0: int, y0: int, side: int, n: int) -> Optional[int]:
    """Column-major index of the cell holding (x, y) in an n x n grid, None if outside."""
    cx, cy = (x - x0) // side, (y - y0) // side
    if not (0 <= cx < n and 0 <= cy < n):
        return None
    return cx * n + cy


class SpatialIndex:
    """Lookup over one volume. Blocks are read on demand and cached."""

    def __init__(self, vol: CarinVolume):
        if vol.db_rel != 34:
            raise ValueError(f"layer directory checked on DB-REL 34 only (disc has {vol.db_rel})")
        self.vol = vol
        self.layers = parse_layer_directory(vol.block(DIR_SECTOR).payload)
        self._grids: Dict[int, Tuple[int, int, list]] = {}
        self._cells: Dict[int, CellNode] = {}

    def grid_layers(self) -> List[Layer]:
        """Records that root a quadtree (their BLOCK_ID is a 0x08 block)."""
        return [l for l in self.layers if l.grid and
                self.vol.block(_bid_sector(l.grid)).type == TYPE_GRID]

    def _grid(self, layer: Layer) -> Tuple[int, int, list]:
        """(cell side, N, [(first entry index, sector, entries) per 0x08 block])."""
        if layer.index not in self._grids:
            vol = self.vol
            blk = vol.block(_bid_sector(layer.grid))
            if blk.type != TYPE_GRID:
                raise ValueError(f"layer {layer.index}: {layer.grid:#x} is not a 0x08 block")
            side, _ = parse_grid_block(blk.payload)
            n = (layer.root[2] - layer.root[0]) // side
            runs, total, sector = [], 0, blk.sector
            while total < n * n:
                b = vol.block(sector)
                if b.type != TYPE_GRID:
                    raise ValueError(f"layer {layer.index}: grid ends at sector {sector}")
                s, ents = parse_grid_block(b.payload)
                if s != side:
                    raise ValueError(f"layer {layer.index}: cell side {s} != {side}")
                runs.append((total, sector, ents))
                total += len(ents)
                sector += b.length
            self._grids[layer.index] = (side, n, runs)
        return self._grids[layer.index]

    def cell_entry(self, layer: Layer, x: int, y: int) -> Optional[Tuple[int, int, int, int]]:
        """(0x09 BLOCK_ID, cell x0, cell y0, cell side) at (x, y), None if empty/outside."""
        side, n, runs = self._grid(layer)
        k = cell_index(x, y, layer.root[0], layer.root[1], side, n)
        if k is None:
            return None
        for first, _, ents in reversed(runs):
            if k >= first:
                bid = ents[k - first]
                break
        if not bid:
            return None
        return bid, layer.root[0] + (k // n) * side, layer.root[1] + (k % n) * side, side

    def cell(self, bid: int) -> CellNode:
        if bid not in self._cells:
            self._cells[bid] = parse_cell(self.vol.block(_bid_sector(bid)).payload)
        return self._cells[bid]

    def tile_at_xy(self, layer: int, x: int, y: int) -> Optional[int]:
        """BLOCK_ID of the tile of directory record `layer` covering CARIN (x, y)."""
        entry = self.cell_entry(self.layers[layer], x, y)
        if entry is None:
            return None
        bid, cx0, cy0, side = entry
        node = self.cell(bid)
        q = side // node.item_side
        j = cell_index(x, y, cx0, cy0, node.item_side, q)
        return None if j is None else node.tile(j)


_INDEXES: "weakref.WeakKeyDictionary[CarinVolume, SpatialIndex]" = weakref.WeakKeyDictionary()


def tiles_at(vol: CarinVolume, layer: int, lon: float, lat: float) -> List[int]:
    """Tile BLOCK_IDs of layer `layer` (0x07 directory index) at (lon, lat).

    Tiles of one layer do not overlap, so the list holds at most one BLOCK_ID;
    it is empty for a point in an empty cell or outside the root square.
    """
    idx = _INDEXES.get(vol)
    if idx is None:
        idx = _INDEXES[vol] = SpatialIndex(vol)
    tile = idx.tile_at_xy(layer, *to_carin(lon, lat))
    return [] if tile is None else [tile]
