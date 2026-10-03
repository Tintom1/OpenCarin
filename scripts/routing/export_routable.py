"""Export the street-level road graph (BLOCK_TYPE 0x00) of a CARiN disc as a routable network.

    python3 scripts/routing/export_routable.py /path/to/carindb --sector-size 512 \
        --bbox 5.0 51.0 6.0 51.6 --out build/limburg --formats gpkg,csv,osm

`--bbox LON0 LAT0 LON1 LAT1` selects tiles by their header bounds (no decoding of other tiles).
Outputs: <out>.gpkg (nodes, edges, restrictions), <out>_{nodes,edges,restrictions}.csv,
<out>.osm (OSM XML for osrm-extract; for Valhalla run `osmium cat`), and a stats printout.
Reads ISO images and bare `carindb` files; stdlib only.
"""
from __future__ import annotations

import argparse
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from carin.export import build_graph, parse_tile                      # noqa: E402
from carin.export.cost import CostModel                                  # noqa: E402
from carin.export.graph import components                              # noqa: E402
from carin.export.writers import write_csv, write_gpkg, write_osm_xml  # noqa: E402
from carin.parser.geometry import header_bounds                       # noqa: E402
from carin.parser.iso import BLOCK_HDR_SIZE, CarinVolume, IsoFile, IsoImage  # noqa: E402


class RawImage:
    def __init__(self, path: str):
        self._f = open(path, "rb")
        self._f.seek(0, 2)
        self.files = {"/carindb": IsoFile("/carindb", 0, self._f.tell())}

    def read(self, iso_file, offset, length):
        if offset >= iso_file.size:
            return b""
        self._f.seek(iso_file.offset + offset)
        return self._f.read(min(length, iso_file.size - offset))


def open_volume(path: str, sector_size) -> CarinVolume:
    try:
        img = IsoImage(path)
    except ValueError:
        img = RawImage(path)
    return CarinVolume(img, sector_size=sector_size)


def prefilter(vol: CarinVolume, b, bbox) -> bool:
    """Cheap tile-bounds test without CF=1 decoding (the prologue is plain in CF=0/1)."""
    raw = vol.read_sectors(b.sector, b.length)
    data = raw[:BLOCK_HDR_SIZE] + zlib.decompress(raw[BLOCK_HDR_SIZE:]) if b.comp == 2 else raw
    hb = header_bounds(data, vol.layout)
    if hb is None:
        return False
    lon0, lat0, lon1, lat1 = hb
    return not (lon1 < bbox[0] or lon0 > bbox[2] or lat1 < bbox[1] or lat0 > bbox[3])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--sector-size", type=int, default=None)
    ap.add_argument("--bbox", type=float, nargs=4, metavar=("LON0", "LAT0", "LON1", "LAT1"),
                    required=True)
    ap.add_argument("--out", required=True, help="output prefix")
    ap.add_argument("--formats", default="gpkg,csv,osm")
    ap.add_argument("--speed-model", default=None,
                    help="cost-model JSON (carin.export.cost.CostModel): effective speeds for maxspeed / model_kmh")
    ap.add_argument("--max-tiles", type=int, default=0, help="stop after N tiles (0 = all)")
    a = ap.parse_args()

    vol = open_volume(a.path, a.sector_size)
    vol.calibrate()
    print(f"DB-REL={vol.db_rel} subrel={vol.subrel} sector_size={vol.sector_size}", flush=True)

    t0 = time.time()
    tiles, seen, failed = [], 0, 0
    for b in vol.walk():
        if b.type != 0x00:
            continue
        seen += 1
        if not prefilter(vol, b, a.bbox):
            continue
        try:
            blk = vol.block(b.sector)
            td = parse_tile(b.sector, blk.payload, vol.layout)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  tile {b.sector}: {e!r}", flush=True)
            continue
        if td is None:
            failed += 1
            continue
        tiles.append(td)
        if len(tiles) % 50 == 0:
            print(f"  {len(tiles)} tiles parsed ({seen} 0x00 blocks scanned, {time.time()-t0:.0f}s)",
                  flush=True)
        if a.max_tiles and len(tiles) >= a.max_tiles:
            break
    print(f"tiles selected: {len(tiles)}  failed: {failed}  scanned: {seen}", flush=True)

    g = build_graph(tiles)
    for k, v in g.stats.items():
        print(f"  {k}: {v}")
    ratios = [e.length_m / e.geom_m for e in g.edges if e.geom_m > 1]
    if ratios:
        ratios.sort()
        print(f"  stored/geometry length ratio: median {ratios[len(ratios)//2]:.3f} "
              f"(p5 {ratios[len(ratios)//20]:.3f}, p95 {ratios[-len(ratios)//20-1]:.3f})")

    comps = components(g)
    if comps:
        print(f"  components: {len(comps)}, largest {len(comps[0])} nodes "
              f"({100*len(comps[0])/len(g.nodes):.1f}%), singletons "
              f"{sum(1 for c in comps if len(c) == 1)}")
    cars = [e for e in g.edges if e.car_ok]
    print(f"  car-passable edges: {len(cars)} ({100*len(cars)/max(1,len(g.edges)):.1f}%), "
          f"one-way: {sum(1 for e in cars if e.direction in (1, 2))}, "
          f"roundabout: {sum(1 for e in cars if e.roundabout)}, toll: {sum(1 for e in cars if e.toll)}")

    model = CostModel.load(a.speed_model) if a.speed_model else CostModel()
    fmts = set(a.formats.split(","))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    if "gpkg" in fmts:
        write_gpkg(g, a.out + ".gpkg")
    if "csv" in fmts:
        write_csv(g, a.out, model)
    if "osm" in fmts:
        write_osm_xml(g, a.out + ".osm", model)
    print("written:", ", ".join(sorted(fmts)), "->", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
