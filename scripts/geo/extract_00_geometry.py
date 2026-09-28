"""Export georeferenced road geometry from BLOCK_TYPE 0x00 blocks as GeoJSON.

Usage:
    extract_00_geometry.py ISO OUT --sector N [N ...]
    extract_00_geometry.py ISO OUT --window LON0 LAT0 LON1 LAT1

Each road segment becomes a WGS84 LineString with its name (when the block
carries one) and display class. See carin/parser/geometry.py.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.parser.iso import IsoImage, CarinVolume
from carin.parser.geometry import header_bounds, road_segments


def _overlaps(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("iso", help="Path to ISO")
    parser.add_argument("out", help="Output GeoJSON")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sector", type=int, nargs="+", help="Sector(s) of 0x00 blocks")
    group.add_argument("--window", type=float, nargs=4,
                       metavar=("LON0", "LAT0", "LON1", "LAT1"),
                       help="Export every 0x00 block overlapping this WGS84 box")
    args = parser.parse_args()

    vol = CarinVolume(IsoImage(args.iso))
    vol.calibrate()
    table = vol.layout

    if args.sector:
        sectors = args.sector
    else:
        sectors = []
        for head in vol.walk():
            if head.type != 0x00:
                continue
            raw = vol.read_sectors(head.sector, 1)
            box = header_bounds(raw, table)
            if box and _overlaps(box, args.window):
                sectors.append(head.sector)

    features = []
    for sector in sectors:
        blk = vol.block(sector)
        if blk.type != 0x00 or not blk.data:
            print(f"sector {sector}: not a decodable 0x00 block, skipped")
            continue
        for seg in road_segments(blk.data, table):
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": seg["coords"]},
                "properties": {
                    "sector": sector,
                    "index": seg["index"],
                    "name": seg["name"],
                    "display_class": seg["display_class"],
                },
            })

    with open(args.out, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    print(f"Exported {len(features)} road segments from {len(sectors)} blocks to {args.out}")


if __name__ == "__main__":
    main()
