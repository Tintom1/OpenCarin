import struct

from carin.parser.house_numbers import (NONE, run_envelope, segment_house_numbers,
                                        tile_block_id)


def _block(tile, records):
    """Minimal decoded type 0x04 block: descriptor at +8, tile at +0x0C, records at +0x10."""
    data = bytearray(0x10 + 10 * len(records))
    struct.pack_into(">HHI", data, 8, 0x10, len(records), tile)
    for i, r in enumerate(records):
        struct.pack_into(">5H", data, 0x10 + 10 * i, *r)
    return bytes(data)


def test_records_and_tile():
    data = _block((1234 << 8) | 7, [(NONE, NONE, NONE, NONE, 0), (1, 2, 9, 20, 2)])
    assert tile_block_id(data) == (1234 << 8) | 7
    assert segment_house_numbers(data) == [
        {"index": 0, "side_a": None, "side_b": None, "scheme": 0},
        {"index": 1, "side_a": (1, 9), "side_b": (2, 20), "scheme": 2},
    ]


def test_missing_end_takes_the_other():
    rec = segment_house_numbers(_block(0, [(NONE, 21, NONE, 21, 2), (7, NONE, NONE, NONE, 2)]))
    assert rec[0]["side_a"] is None and rec[0]["side_b"] == (21, 21)
    assert rec[1]["side_a"] == (7, 7) and rec[1]["side_b"] is None


def test_envelope_odd_even_and_mixed():
    rec = segment_house_numbers(_block(0, [
        (NONE, NONE, NONE, NONE, 0),
        (31, NONE, 31, NONE, 2),        # odd side only
        (111, 110, 82, 110, 1),         # mixed: side A 82..111, side B 110
        (1, 2, 9, 20, 2),
    ]))
    assert run_envelope(rec, 0, 3) == ((82, 110), (31, 111))
    assert run_envelope(rec, 3, 1) == ((2, 20), (1, 9))
    assert run_envelope(rec, 0, 1) == (None, None)
