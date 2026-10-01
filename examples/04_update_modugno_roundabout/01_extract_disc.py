"""Step 1: the disc's street-level segments around the test point -> dataset/disc_segments.csv.

Reads the working copy of the disc (dataset/NAV_DB_21708_copy.ISO), finds the 0x00 tiles that
cover the area with the spatial index, decodes them and keeps the segments with a vertex within
RADIUS_M of the centre. Also saves each tile's decoded bytes (dataset/tile_<BLOCK_ID>.bin) for the
later patching steps.

    uv run python examples/04_update_modugno_roundabout/01_extract_disc.py [--tag before|after]

The tag names the outputs, so the state before the patch (04_patch_tile.py) is kept next to the
state after it: disc_segments_<tag>.csv and tile_<BLOCK_ID>_<tag>.bin.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from carin.parser.cf1.constants import T_REC_S4
from carin.parser.geometry import _sections, road_segments
from carin.parser.iso import CarinVolume, IsoImage
from carin.parser.spatial import tiles_at
from common import CENTER, DATA, ISO_COPY, M_LAT, M_LON, RADIUS_M, length_m, to_m, wkt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="before")
    tag = ap.parse_args().tag
    vol = CarinVolume(IsoImage(str(ISO_COPY)))
    vol.calibrate()

    tiles, step = set(), 0.002
    dlon, dlat = RADIUS_M / M_LON, RADIUS_M / M_LAT
    lon = CENTER[0] - dlon
    while lon <= CENTER[0] + dlon:
        lat = CENTER[1] - dlat
        while lat <= CENTER[1] + dlat:
            tiles.update(tiles_at(vol, 0, lon, lat))
            lat += step
        lon += step
    print(f"{len(tiles)} street-level tiles: {', '.join(hex(t) for t in sorted(tiles))}")

    rows = []
    for tile in sorted(tiles):
        blk = vol.block(tile >> 8)
        (DATA / f"tile_{tile:#x}_{tag}.bin").write_bytes(blk.payload)
        s4_off = _sections(blk.payload, vol.layout)[4][0]
        rec4 = vol.layout[T_REC_S4]
        for s in road_segments(blk.payload, vol.layout):
            if min((x * x + y * y) ** 0.5 for x, y in map(lambda c: to_m(*c), s["coords"])) > RADIUS_M:
                continue
            rows.append({
                "tile": f"{tile:#x}", "cf": blk.comp, "index": s["index"], "name": s["name"] or "",
                "class": s["display_class"],
                # S4 +0x11 low nibble: 0 ordinary, 6 roundabout, 9 connector inside a junction;
                # +0x0B: form, direction (bits 4-5) and toll (03-road-network.md §6.7)
                "junction": blk.payload[s4_off + rec4 * s["index"] + 0x11] & 0x0F,
                "b0b": f"{blk.payload[s4_off + rec4 * s['index'] + 0x0B]:#04x}",
                "points": len(s["coords"]),
                "length_m": round(length_m(s["coords"]), 1), "wkt": wkt(s["coords"]),
            })
    with open(DATA / f"disc_segments_{tag}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} segments -> dataset/disc_segments_{tag}.csv")


if __name__ == "__main__":
    main()
