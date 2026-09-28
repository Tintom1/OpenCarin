import struct

from carin.parser.cf1 import decode_s2_links

TABLE = {0x05: 8, 0x42: 24}


def _block(records):
    """Minimal decoded type 0x0E block with section 2 at offset 64."""
    data = bytearray(64 + 24 * len(records))
    struct.pack_into(">HH", data, 8 + 2 * 4, 64, len(records))
    for i, (xy, houses, bid, off, cnt) in enumerate(records):
        b = 64 + 24 * i
        struct.pack_into(">ii4HIHH", data, b, *xy, *houses, bid, off, cnt)
    return bytes(data)


def test_links_and_house_numbers():
    rec = decode_s2_links(_block([((100, -200), (2, 40, 1, 39), (1234 << 8) | 7, 96, 3)]), TABLE)
    assert rec == [{
        "tile_center": (100, -200),
        "tile_block_id": (1234 << 8) | 7,
        "tile_sector": 1234,
        "tile_length": 7,
        "s4_offset": 96,
        "s4_count": 3,
        "even": (2, 40),
        "odd": (1, 39),
    }]


def test_missing_house_numbers_are_none():
    none = 0x7FFF
    rec = decode_s2_links(_block([((0, 0), (none, none, 5, 9), 0x100, 64, 1)]), TABLE)
    assert rec[0]["even"] is None and rec[0]["odd"] == (5, 9)
