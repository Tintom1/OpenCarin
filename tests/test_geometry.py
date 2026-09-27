import struct

import pytest

from carin.parser.geometry import header_bounds, road_segments, tile_frame
from carin.parser.iso import to_wgs84

TABLE = {0x05: 8, 0x06: 16, 0x08: 30, 0x09: 24, 0x0C: 6, 0x10: 8, 0x40: 6}
UNIT = 64


def _block(bbox, shape=((10, 20), (30, 40)), nodes=((0, 0), (100, 100))):
    """Minimal decoded type 0x00 block: one named segment, two nodes."""
    data = bytearray(1024)
    sec = {2: (200, 1), 4: (240, 1), 5: (300, len(nodes)), 7: (340, len(shape))}
    for i in range(15):
        struct.pack_into(">HH", data, 8 + 4 * i, *sec.get(i, (0, 0)))
    struct.pack_into(">4I", data, 0x44, *bbox)
    struct.pack_into(">HHH", data, 240, 300, 308, 340)      # start/end node, shape ptr
    data[240 + 0x10] = 3                                    # display class
    struct.pack_into(">H", data, 240 + 24, 200)             # -> section 2 record
    struct.pack_into(">H", data, 200, 400)                  # -> name text
    data[400:410] = b"test road\x00"
    for i, (x, y) in enumerate(nodes):
        struct.pack_into(">HH", data, 300 + 8 * i, x, y)
    for i, (x, y) in enumerate(shape):
        struct.pack_into(">HH", data, 340 + 6 * i, x, y)
    return bytes(data)


def test_full_box_frame_and_segment():
    x0, y0 = 150_000_000, 280_000_000
    side = 100 * UNIT
    data = _block((x0, y0, x0 + side, y0 + side))
    frame = tile_frame(data, TABLE)
    assert (frame.x0, frame.y0, frame.width, frame.height) == (x0, y0, side, side)
    [seg] = road_segments(data, TABLE)
    assert seg["name"] == "test road" and seg["display_class"] == 3
    expected = [(0, 0), (10, 20), (30, 40), (100, 100)]
    assert seg["coords"] == [to_wgs84(x0 + u * UNIT, y0 + v * UNIT) for u, v in expected]


def test_three_field_frame_uses_east_edge_and_derives_width():
    y0, x_east = 280_000_000, 150_000_000
    span = 100 * UNIT
    # a shape point beyond the latitude span in x makes the tile 2:1
    data = _block((y0, x_east, y0 + span, 0), shape=((150, 20), (30, 40)))
    frame = tile_frame(data, TABLE)
    assert frame.width == 2 * span and frame.height == span
    assert frame.x0 == x_east - 2 * span and frame.y0 == y0
    assert len(road_segments(data, TABLE)) == 1


def test_header_bounds_three_field_is_conservative():
    y0, x_east, span = 280_000_000, 150_000_000, 100 * UNIT
    lon0, lat0, lon1, lat1 = header_bounds(_block((y0, x_east, y0 + span, 0)), TABLE)
    assert (lon0, lat0) == pytest.approx(to_wgs84(x_east - 2 * span, y0))
    assert (lon1, lat1) == pytest.approx(to_wgs84(x_east, y0 + span))


def test_points_outside_tile_are_dropped():
    x0, y0, side = 150_000_000, 280_000_000, 100 * UNIT
    data = _block((x0, y0, x0 + side, y0 + side), shape=((10, 20), (500, 40)))
    assert road_segments(data, TABLE) == []
