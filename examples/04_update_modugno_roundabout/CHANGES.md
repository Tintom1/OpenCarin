# Changes log — Modugno roundabout test

Everything is done on `dataset/NAV_DB_21708_copy.ISO`, a copy-on-write clone of the original disc
(`cp -c`, 2026-10-01). The original is never written. One entry per change, newest last.

## 2026-10-01 — setup and delta (no change to the disc yet)

| What | Where | Result |
|---|---|---|
| Clone of the disc | `dataset/NAV_DB_21708_copy.ISO` | identical bytes, no extra disk space |
| Area | centre 41.087806 N, 16.789611 E (41°05'16.1"N 16°47'22.6"E), radius 500 m | 3 street-level tiles: `0x4c18252a`, `0x4c184f18` (CF=1), `0x4c187112` |
| Disc segments | `dataset/disc_segments_before.csv`, `tile_<BLOCK_ID>_before.bin` (decoded tiles) | 265 segments, 21,178 m |
| OSM highways | `dataset/osm_ways.json`, `osm_ways.csv` (Overpass; mirror data of 2026-05-31) | 486 ways; 210 not for cars (footway, cycleway, pedestrian) |
| Delta, tolerance 15 m, cover 0.7 | `dataset/delta_before.csv` | disc: 263 present, 2 removed. OSM: 162 present, 114 new (20,891 m) |
| Same at tolerance 6 m | (not saved) | disc: 201 present, 64 removed. OSM: 113 present, 163 new |

### What the delta says

- The count of new and removed ways depends strongly on the tolerance: 15 m calls most of the
  disc present; 6 m moves 62 more disc segments to "removed". The disc's geometry is generalised
  (2 to 7 points per segment), so a tight tolerance mostly measures drawing differences, not new
  roads. Use the new / removed lists by name and type, not the totals.
- Large OSM-only ways in the area are real changes since the disc: the A14 ring-road ramps,
  Strada Provinciale 1 Bari - Modugno, Via Vigili del Fuoco Caduti in Servizio, plus many
  `service` ways (car parks, hotel).
- **The roundabout.** On the disc the junction at the centre is a 4-arm crossing: Via Roma
  (segments 38, 41) across Viale della Repubblica (43, 44, 45, 46), which is a dual carriageway
  (S4 `+0x0B` = `0x14` / `0x24`: opposite one-way directions), joined by two junction connectors
  (17, 18; junction type 9). The hub node is at 41.08800 N, 16.78962 E, 23 m north of the ring's
  centre. OSM now has the ring as three ways (`1326505905`, `1383238946`, `1383238947`; about
  20 m across, centre 41.08779 N, 16.78971 E).
- A plain coverage test calls the ring "present" (its arcs pass within 15 m of the old arms), so
  `03_delta.py` also checks roundabouts by junction type: none of the 12 OSM roundabout ways of the
  area is on a disc segment of junction type 6 (S4 `+0x11 & 0x0F`). Type 6 does occur on these
  tiles (4 / 7 / 10 segments elsewhere in them), so the disc encodes roundabouts this way, but not
  within 500 m of the centre.

## 2026-10-01 — tile `0x4c184f18` patched in the copy (`04_patch_tile.py --write`)

The old crossing is replaced by the OSM roundabout. **Nothing else on the disc changes**: the block is
rewritten in place (12,125 bytes of CF=1 in its 24 sectors, 12,288 B; zero padding); the copy differs
from the original only inside that extent. No section changes size, so no offset moves and every
pointer into the tile (`0x0E` runs, `0x04`, `0x0C`, the spatial index) stays valid.

The eight records of the old crossing are reused (the plan and the logical directions are in the
script's docstring). 93 decoded bytes change:

| Record | Was | Now |
|---|---|---|
| 43 | H -> C, Viale della Repubblica, 51 m | ring Rw -> Rse, junction 6, 29 m, no name |
| 17 | C -> A, connector (junction 9), 68 m | ring Rse -> Rne, junction 6, 28 m, stored reversed, no name |
| 44 | H -> D, Viale della Repubblica, 51 m | ring Rne -> Rw, junction 6, 32 m, stored reversed, no name |
| 41 | B -> H, Via Roma, 63 m | B -> Rw, 52 m, two-way |
| 38 | H -> A, 52 m | Rne -> A, 42 m, two-way |
| 45 | C -> E, inbound, 49 m | E -> Rse inbound, 60 m |
| 46 | D -> F, outbound, 72 m | Rse -> F outbound, 85 m |
| 18 | B -> D, connector (junction 9), 79 m | B -> Rse slip lane south of the ring (junction 0), 74 m |

- **Nodes.** The three internal nodes of the crossing (S5 offsets 16528, 16536, 16544) move onto the OSM
  ring (vertices 12, 4 and 18 of its 20) as Rw (west), Rne (north-east) and Rse (south-east).
  The roles go to the slots in (x, y) order so the S5 nodes stay sorted inside their level group.
  The outer nodes A, B, E, F do not move.
- **Ring shape.** The ring's own vertices, resampled onto the 2 / 3 / 1 shape points the three records
  already had: a 9-gon: on a ring about 29 m across the chords stay under 1 m from the circle. Lengths (`+0x0C`) and bearings
  (`+0x0E`, `+0x0F`) of the eight records are recomputed from the new geometry.
- **Ordering rules kept** (03-road-network.md §6.7): the start node is the end with the lower (x, y), so
  records 17 and 44 are stored reversed (shape reversed, one-way bits swapped to "against"); S5 nodes
  sorted per level group. Both rules were first checked on the untouched tile (460 / 460 records, and every level group of S3).
- **Node cycles.** The segment lists at the seven nodes (`+0x06` / `+0x08`, node `+4`) are rebuilt:
  clockwise by bearing, starting from the smallest. The rule reproduces all 294 cycles of the original
  tile before it is used.
- **Forbidden turns (S10).** Two entries would now forbid a ring exit (17 -> 38 and 43 -> 38, now both
  at Rne): their target is set to the owning segment itself. (A U-turn onto itself; the effect on the
  unit is not known.) Entry 41 -> 18 at B is unchanged and still valid.
- **Not touched, on purpose.** Street names (S2) and house numbers (`0x04`): the ring records had none, and
  41 keeps its number 108. Class 2 roads in the coarse tiles `0x03`/`0x02`/`0x01` (they still hold the
  old crossing). Node flags. Speed byte. The other 9 OSM roundabout ways of the area.

### Checks

| Check | Result |
|---|---|
| Our decoder re-reads the written block | identical to the patched tile |
| Independent Rust decoder (`carindb-rs dump-block`, new) reads it | identical, 25,600 B, 0.6 s |
| Node cycles, start-node rule, S5 order, S10 shared node (`check()`, before and after) | pass on the original; pass on the patched tile |
| Original disc | untouched (cmp against the clone: only the block's extent differs) |
| Address lookup on the copy (Via Roma 114, example 03) | same result as on the original |
| `03_delta.py --tag after`, roundabouts by junction type | 3 of 12 OSM roundabout ways are on the disc (the 3 of this ring); 0 of 12 before |
| `before_after.svg` | the ring replaces the crossing; arms attach at three ring nodes |

## Open

- **Coarse levels.** `0x03`, `0x02`, `0x01` tiles that hold these class 2 roads still have the old crossing
  and its nodes (every node of a coarse tile lies on a `0x00` node). A coarse segment's geometry is not
  updated; whether the unit needs them consistent for routing or only for the zoomed-out map is not known.
- **Fidelity to OSM.** The real roundabout has six junctions and curved arms; this has three ring nodes,
  straight arms, one slip lane. Adding records needs a tile that grows (the sections after S4 move), which
  our encoder does not do yet.
- **On the unit.** Nothing has been run on a unit. The next test is a burned disc (the DVD builder, roadmap
  D15, does not exist yet) or, on the CD platform, a CNI1 disc made the same way.
- **Delta.** The other 9 OSM roundabout ways (small ones, some 2 to 15 m) are not on the disc: whether they
  are new, or encoded differently, was not looked at. The OSM data of the mirror is dated 2026-05-31.
