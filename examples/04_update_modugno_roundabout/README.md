# 04 — Update a piece of the map from OSM: the Modugno roundabout

Test of the project's goal on a small area. Around 41°05'16.1"N 16°47'22.6"E (Modugno, Bari) a
roundabout was built after the 2016 data of DVD `NAV_DB_21708`; the disc still has a crossing
there. We compare the disc with today's OpenStreetMap, measure what would have to be updated, and
patch a **copy** of the disc.

Nothing here touches the original disc: all work is on `dataset/NAV_DB_21708_copy.ISO`, a
copy-on-write clone (`cp -c`, instant, no extra disk space). `dataset/` is git-ignored and holds
the copy and every intermediate table. Every change we make is logged in [`CHANGES.md`](CHANGES.md); what is left to do is in [`PLAN.md`](PLAN.md).

## Steps

| Script | Does | Writes (`dataset/`) |
|---|---|---|
| `01_extract_disc.py [--tag before\|after]` | street-level (`0x00`) tiles of the area, decoded; their segments | `disc_segments_<tag>.csv`, `tile_<BLOCK_ID>_<tag>.bin` |
| `02_fetch_osm.py` | OSM highways of the area (Overpass; kept on disk) | `osm_ways.json`, `osm_ways.csv` |
| `03_delta.py [--tag before\|after]` | disc vs OSM: present / removed (disc only) / new (OSM only); roundabouts by junction type | `delta_<tag>.csv` |
| `04_patch_tile.py [--write]` | replaces the old crossing by the OSM roundabout in tile `0x4c184f18` of the copy; checks, re-encodes (CF=1) and writes it in place | `tile_0x4c184f18_patched.bin`, `before_after.svg`, `before.svg`, `after.svg` |

```bash
uv run python examples/04_update_modugno_roundabout/01_extract_disc.py
uv run python examples/04_update_modugno_roundabout/02_fetch_osm.py
uv run python examples/04_update_modugno_roundabout/03_delta.py --tol 15 --cover 0.7
uv run python examples/04_update_modugno_roundabout/04_patch_tile.py            # dry run: checks, nothing written
uv run python examples/04_update_modugno_roundabout/04_patch_tile.py --write    # writes the block into the copy
uv run python examples/04_update_modugno_roundabout/01_extract_disc.py --tag after
uv run python examples/04_update_modugno_roundabout/03_delta.py --tag after
# independent check of the written block with the Rust decoder (one block, no disc scan):
carindb-rs/target/release/carindb-rs --iso examples/04_update_modugno_roundabout/dataset/NAV_DB_21708_copy.ISO dump-block 4986959
```

To start over, replace the copy by a fresh clone of the original
(`cp -c <original> dataset/NAV_DB_21708_copy.ISO`) and run step 01 with `--tag before` first: the patch
script reads the tile from the copy, so it must be a pristine one.

Each step takes seconds: the area is three tiles, and the delta is a flat-earth match of 8 m
samples (`common.py`). The Rust tools `dump-type` and `xref` are whole-disc passes and are not
needed here; `dump-block` (added for this test) decodes one block with the independent Rust decoder.

## Reading the result

- A disc segment is **present** if at least `--cover` of its samples lie within `--tol` metres of a
  drivable OSM way, otherwise **removed**; an OSM way is **present** if the same holds against the
  disc, otherwise **new**.
- Small features need a second test: a roundabout's arcs pass within the tolerance of the old crossing's
  arms, so coverage calls it present. `03_delta.py` therefore also checks each OSM roundabout way against the
  disc segments of junction type 6 (S4 `+0x11 & 0x0F`) within 6 m.
- Footways, paths, cycleways and the like are counted apart: the disc is a car map.
- Names are compared case-folded; the tolerance and cover are parameters, so the numbers depend on
  them (see `CHANGES.md` for the values used).
