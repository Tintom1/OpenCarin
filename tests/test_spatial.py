import struct
from dataclasses import dataclass

import pytest

from carin.parser import spatial
from carin.parser.spatial import SpatialIndex, cell_index, parse_cell, tiles_at

ROOT = (0, 0, 1024, 1024)
GRID = (10 << 8) | 1          # first 0x08 block, sector 10
CELL = (20 << 8) | 1          # the only 0x09 block
TILE_A, TILE_B = 0x1000_0101, 0x1000_0201


@dataclass
class _Block:
    sector: int
    length: int
    type: int
    payload: bytes


class _Volume:
    db_rel = 34

    def __init__(self, blocks):
        self.blocks = blocks

    def block(self, sector):
        return self.blocks[sector]


def _dir07():
    data = bytearray(512)
    struct.pack_into(">I4i4H", data, 0x14, GRID, *ROOT, 6, 0, 1, 0)
    return bytes(data)


def _grid(entries, side=512):
    data = bytearray(512)
    struct.pack_into(">HHI", data, 8, 0x10, len(entries), side)
    struct.pack_into(f">{len(entries)}I", data, 0x10, *entries)
    return bytes(data)


def _cell(item_side, pointers_by_tile, q):
    """0x09 with S0 = q*q u16 pointers (column-major), S1 = the tiles in first-seen order."""
    tiles = []
    grid = [0] * (q * q)
    for (x, y), tile in pointers_by_tile.items():
        if tile not in tiles:
            tiles.append(tile)
        grid[x * q + y] = tile
    s1 = (0x14 + 2 * q * q + 3) & ~3
    ptrs = [s1 + 4 * tiles.index(t) if t else 0 for t in grid]
    data = bytearray(512)
    struct.pack_into(">HHHHI", data, 8, 0x14, q * q, s1, len(tiles), item_side)
    struct.pack_into(f">{q * q}H", data, 0x14, *ptrs)
    struct.pack_into(f">{len(tiles)}I", data, s1, *tiles)
    return bytes(data)


def _volume():
    # 2 x 2 grid split over two 0x08 blocks; only cell (1, 0) is populated.
    # Its 2 x 2 items: A covers column x = 0 (two items), B item (1, 0), item (1, 1) empty.
    cell = _cell(256, {(0, 0): TILE_A, (0, 1): TILE_A, (1, 0): TILE_B}, 2)
    return _Volume({
        3: _Block(3, 1, 0x07, _dir07()),
        10: _Block(10, 1, 0x08, _grid([0, 0])),
        11: _Block(11, 1, 0x08, _grid([CELL, 0])),
        20: _Block(20, 1, 0x09, cell),
    })


def test_cell_index_is_column_major_and_half_open():
    assert cell_index(0, 0, 0, 0, 512, 2) == 0
    assert cell_index(0, 512, 0, 0, 512, 2) == 1          # north neighbour: next entry
    assert cell_index(512, 0, 0, 0, 512, 2) == 2          # east neighbour: next column
    assert cell_index(1024, 0, 0, 0, 512, 2) is None
    assert cell_index(-1, 0, 0, 0, 512, 2) is None


def test_parse_cell_pointers_resolve_to_s1():
    node = parse_cell(_cell(256, {(0, 0): TILE_A, (1, 1): TILE_B}, 2))
    assert node.item_side == 256
    assert [node.tile(j) for j in range(4)] == [TILE_A, None, None, TILE_B]


def test_lookup_walks_directory_grid_and_cell():
    idx = SpatialIndex(_volume())
    # cell (1, 0) spans x 512..1024, y 0..512; items are 256 wide
    assert idx.tile_at_xy(0, 512, 0) == TILE_A
    assert idx.tile_at_xy(0, 767, 511) == TILE_A          # same column, upper item
    assert idx.tile_at_xy(0, 768, 0) == TILE_B
    assert idx.tile_at_xy(0, 768, 256) is None            # empty item
    assert idx.tile_at_xy(0, 100, 100) is None            # empty 0x08 cell
    assert idx.tile_at_xy(0, 2000, 0) is None             # outside the root square


def test_tiles_at_converts_wgs84(monkeypatch):
    vol = _volume()
    monkeypatch.setattr(spatial, "to_carin", lambda lon, lat: (int(lon), int(lat)))
    assert tiles_at(vol, 0, 800, 10) == [TILE_B]
    assert tiles_at(vol, 0, 800, 300) == []


def test_other_db_rel_is_refused():
    vol = _volume()
    vol.db_rel = 22
    with pytest.raises(ValueError):
        SpatialIndex(vol)
