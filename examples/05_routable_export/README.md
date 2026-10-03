# Example 5: Export a region as a routable network and route on it

Exports the street-level road graph (`0x00` tiles) of a bounding box to GeoPackage, CSV and
OSM XML, builds an [OSRM](https://project-osrm.org) graph from the OSM XML and routes on it.
Works on an ISO image or on a bare `carindb` file. No disc data is included here.

What is exported (see `docs/carindb/03-road-network.md` §6.7 for the fields):

| Table / layer | Content |
|---|---|
| `nodes` | one point per junction; tile-edge nodes are merged through their S6 twin |
| `edges` | one line per segment: name, locality, road class (+ class 6 subtype), form of way, one-way direction, toll, junction type (roundabout), speed category, built-up flag, stored length, polyline length, `car_ok`, an approximate OSM `highway` value |
| `restrictions` | forbidden turns (S10): `from_edge` (the street you come from) → `to_edge` (the one you may not enter) at `via_node`; flags 2 and 3 are kept as `other` and are not turn bans |

## 1. Export a region

```bash
# --sector-size is the unit BLOCK_ID counts in: 2048 for most CDs, 512 for DVDs and for CDs whose
# ABSTRACT reads "carinet16s512". Without it a single /carindb is read in 2048-byte sectors.
python3 scripts/routing/export_routable.py /path/to/carindb --sector-size 512 \
    --bbox 5.4 51.35 5.6 51.5 --out build/region 2>&1 | tee export.txt
```

`--bbox LON0 LAT0 LON1 LAT1` picks the tiles whose header bounds overlap the box; every other
tile is skipped without decoding it. A few hundred tiles take seconds; memory grows with the
number of segments (about 300 per tile), so export large areas in several boxes.
The printout shows the tile, node, edge and restriction counts, how many S6 twin links were
found and how many of them are further than 2 m apart (should be 0), the connected components,
and the ratio of stored length (`+0x0C`) to polyline length (about 1.00).

Outputs: `build/region.gpkg`, `build/region_{nodes,edges,restrictions}.csv`, `build/region.osm`.

## 2. Route with OSRM

```bash
P=$(ls -d /opt/homebrew/Cellar/osrm-backend/*/share/osrm/profiles | head -1)   # or your profile dir
osrm-extract -p $P/car.lua build/region.osm
osrm-partition build/region
osrm-customize build/region
osrm-routed --algorithm mld build/region.osrm
curl "http://127.0.0.1:5000/route/v1/driving/5.49,51.45;5.52,51.42?overview=false"
```

For Valhalla, convert first: `osmium cat build/region.osm -o build/region.osm.pbf`.

## 3. Travel times

`maxspeed` in the OSM file and `model_kmh` in the CSV come from `carin.export.cost.CostModel`.
Its defaults are the raw stored speeds. Two things need care:

* **Speed category 0 means "no speed stored".** Edges with it (most motorways) get a default
  per road type (`UNKNOWN_KMH`), not 0 km/h.
* The stored speeds are free-flow limits. A divisor per road type and a junction delay bring
  travel times close to a reference engine. They can be fitted against OSRM durations on routes
  where both take the same path, and loaded with `--speed-model model.json`:

```json
{"divisor": {"motorway": 1.0, "main_open": 1.28, "main_built": 1.02, "minor_open": 0.88, "minor_built": 0.70},
 "unknown_kmh": {"motorway": 87, "main_open": 71, "main_built": 40, "minor_open": 40, "minor_built": 30},
 "junction_s": 3.6}
```

These example values are what a fit on 112–119 routes around Deurne (NL) against the public OSRM
demo gave; they describe Dutch roads as OSRM models them and must be refitted elsewhere.

## Limits

* Street level only; `0x01`–`0x03`, signposts, toll points and house numbers are not exported.
* Region-based: a whole disc does not fit in a few GB.
* The disc is as old as it is: new roads are missing and some one-ways have changed.
