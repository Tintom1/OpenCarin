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

## 2026-10-01 — first attempt: tile `0x4c184f18` patched in place (`04_patch_tile.py --write`), superseded by steps 5 to 7 below

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

## 2026-10-01 — tile editor, the roundabout as OSM has it, every reference (steps 5, 5b, 6, 7)

Supersedes the in-place patch above: step 6 starts from a **fresh clone** of the original (`--fresh`), so the
copy now holds only what steps 5 to 6 write. The first attempt could not add records; the editor
(`carin/parser/cf1/tile00.py`) can, and rewrites every pointer in the tile. Pipeline, from a fresh clone:

```bash
carindb-rs/target/release/carindb-rs --iso dataset/NAV_DB_21708.ISO xref 0x4c184f18 > examples/04_update_modugno_roundabout/dataset/xref_4c184f18.txt   # 40 s, once
carindb-rs/target/release/carindb-rs --iso dataset/NAV_DB_21708.ISO xref 0x5c58a51c > examples/04_update_modugno_roundabout/dataset/xref_5c58a51c.txt   # the coarse tile
uv run --with numpy python examples/04_update_modugno_roundabout/05_redraw_roundabout.py     # street tile, dry run
uv run --with numpy python examples/04_update_modugno_roundabout/05b_redraw_coarse.py        # coarse tile, dry run
uv run --with numpy python examples/04_update_modugno_roundabout/06_patch_references.py --fresh   # writes the copy
uv run --with numpy python examples/04_update_modugno_roundabout/07_validate.py
```

### Who points into the tile (step 5.1, `carindb-rs xref` on the original, 315,095 blocks, 39 s)

1,080 hits of the BLOCK_ID `0x4c184f18`, classified by the structure they sit in (`carin/parser/refs.py`):

| Block type | Hits | Field | What it holds | Changes with an edit? |
|---|---:|---|---|---|
| `0x0E` (street directory) | 934 in 320 blocks (319 zlib, 1 CF=1) | S2 `+16` BLOCK_ID, `+20` u16 S4 offset, `+22` u16 count | a run of consecutive S4 records of one street, with the house-number ranges of the run | **yes**: every offset after an insertion (918 of 934 here) |
| `0x10` (street directory, zlib) | 24 in 2 blocks | section 4, 8 B: u32 BLOCK_ID, u16 S4 offset, u16 flag | one segment per street and tile | **yes**: offset; a removed record needs a replacement of the same street |
| `0x17` (TMC locations, zlib) | 4 in 3 blocks | x, y (u32), idA, idB (u32), offA, offB (u16) | segments at the two ends of a location | **yes**: offset (2 of 4 here) |
| `0x04` (house numbers) | 1 | header `+0x0C` BLOCK_ID, one 10 B record per S4 record | numbers per segment | **yes**: one record per S4 record, same order |
| `0x00` neighbours | 64 in 5 tiles (S6 `+8`), 5 (S9), 27 (own S10) | S6 `+8` BLOCK_ID, `+12` u16 offset of the twin **in this tile's S6** | tile-edge twin | **yes**: S6 moves when S4 / S5 grow |
| `0x03` | 4 | S8 level link | BLOCK_ID only | no |
| `0x09` | 1 | spatial cell | BLOCK_ID only | no |
| `0x16` | 1 | odd offset `0x2b2b` | byte coincidence | no |
| `0x00` far away | 13 | S4 `+6` / `+0` / S2 `+6` | byte coincidences (two `u16` that happen to read `0x4c18 0x4f18`) | no |

Not found: anything storing a **node** (S5) offset of this tile, a type `0x0C` reference, or an S4 offset of
this tile without its BLOCK_ID next to it. The coarse tile `0x5c58a51c` is referenced by 32 street tiles (header
`+0x58`, BLOCK_ID only), a `0x02` S8 link, a `0x09` cell, and four `0x03` neighbours (25 S6 twins + S9).

### The tile model

`Tile00.parse` -> objects (a segment holds its node objects, next-segment links, shape points, turns, signposts) ->
`build()` lays the sections out again and writes every pointer of the catalog (docstring of `tile00.py`).

| Test (`scripts/codec_cf1/check_tile00_relayout.py`, 62 tiles: 40 street CF=1 over the size range 1 to 56 sectors, 20 coarse zlib, the two tiles of this test) | Result |
|---|---|
| null relayout (parse, build) | byte for byte identical: 62 / 62 |
| forced shift of S3 / S4 / S7 / all (extra bytes after the section, so everything behind moves) | same graph (`tile_graph` equality), `encode_type00` accepts it and our decoder reads it back identically: 62 / 62 |
| the rules hold on the untouched tile (start node, S5 order, level groups, node cycles, S10 shared node) | 43 / 62 tiles. The rest: 10 node cycles at tile-edge nodes and 36 S10 entries whose target shares no node with the owner (19 tiles). Not on the two tiles of this test |
| `normalize()` (sort S5, rebuild cycles) on a tile that follows the rules | reproduces it byte for byte |

New facts found on the way (`03-road-network.md` §6.7): the level group k of S3 holds the class-k segments and the S5
nodes whose lowest class is k (7 groups for classes 0 to 6; 460 / 460 segments, 294 / 294 nodes here); a node alone
on a segment holds that segment itself as next; a lone segment at an S6 node has none; the zlib blocks'
header `+7` is the decoded length in sectors (330 / 330 blocks of the kinds this test touches); coarse tiles have 26-byte S4 records (the 32-byte
layout without the street record, flags and signpost pointer) and are zlib, not packed.

### Step 5: what the street tile becomes (`05_redraw_roundabout.py`)

OSM way -> record, the mapping written once in `05_redraw_roundabout.py` (`place_seg`, `reorient`):

| OSM | Record | Fields |
|---|---|---|
| ring `1326505905`, `1383238946`, `1383238947` (`junction=roundabout`, secondary) | 6 new records, one per arc between ring junctions, counter-clockwise R1 R2 R3 R4 R5 R6 | class 2 (the disc has secondary and tertiary roads of this tile in class 2: records 43-46 and 38-42); junction type 6; form single carriageway `0xC`; one-way along or against the stored direction (`+0x0B` bits 4-5); speed `0x0B`, not built-up, `+0x1C` = `0x1000` (the class-2 neighbours); no street name (S2 record 1); length and both bearings from the geometry; shape = the ring's own vertices (14 inner points, 20 with the nodes) |
| links `80640277`, `1326505910`, `1331933266`, `80640279` (`secondary_link`, one-way) | 4 new records | as the ring but junction type 9, the type of the old connectors 17 and 18; shape = OSM vertices (14 inner points) |
| Viale della Repubblica `503040064` (out), `529215906` (in) | records 46 and 45 kept (name, class, speed, flags), re-attached to R6 / R1, new shape (7 + 4 points) | the arms end where the disc's nodes F and E already are (0.8 m and 0.6 m from the OSM lines) |

- **Old crossing removed.** Records 17, 18, 38, 41, 43, 44 and the nodes H, D, C. 45 and 46 stay. Node B moves 8.7 m along Via Roma
  to the junction of the two west links (the disc had it beyond), so record 40 is recomputed. Node A stays (2 m from the OSM junction).
- **Ordered insertion.** The ten new records open class group 2, in front of the surviving unnamed record 19; the six ring nodes
  join the group's S5 nodes in (x, y) order. S4 460 -> 464 records, S5 294 -> 297, S7 238 -> 266 shape points.
- **Data that sat on the removed records.** Signposts (S11) follow the traffic they were on: "modugno centro" -> 45, "carbonara / bitritto /
  bitetto" -> 46, "pescara-napoli (a14)" -> the link to the north-east. **Dropped, not moved:** 3 forbidden turns that only existed
  inside the old crossing (S10: 17 -> 38, 41 -> 18, 43 -> 38), 6 TMC triples (S12) of the two Via Roma arms (39, 40, 42 keep theirs), the house
  numbers of record 41 (Via Roma, the arm that OSM now draws as two unnamed links).
- **Fit.** Re-encoded CF=1: 12,208 bytes in the original 24 sectors (12,288 B): 80 B left, no block moves. The decoded tile stays 25,600 B.

### Step 5b: the coarse tile (`05b_redraw_coarse.py`)

Tile `0x5c58a51c` (type `0x03`, classes 0-2, 28 sectors, zlib) holds copies of the crossing's records (found by the absolute coordinates of their
end nodes, 6 of 6). Every end of the changed records is a three-way node, so every coarse record is the street record: the six removed ones go, three
(45, 46 and 40) take the new geometry, the ten new ones are added with the street record's fields and shape (572 -> 576 records, 392 -> 395
nodes, flags copied from the street twin). Zlib 14,253 B in 14,336. **Not tested:** that the coarse tile *needs* to follow the street tile.

### Step 6: everything that points into the two tiles (`06_patch_references.py`)

331 blocks rewritten in place, none moved; each re-encoded (CF=1 / zlib level 9, header `+7` = decoded sectors) and checked to fit its extent
(`carin/parser/volume_edit.py`); every block reads back from the copy to what was written:

| Blocks | Change |
|---|---|
| the street tile, the coarse tile | the redrawn tiles |
| 5 street neighbours, 4 coarse neighbours | S6 twin offsets (64 + 25 entries), the S6 of the edited tiles moved by +152 / +128 bytes |
| 315 of 320 `0x0E` | 918 run offsets (+128, four records) and 6 house-number ranges (the runs that lost record 41; recomputed as the envelope of the new `0x04` records, as before) |
| 2 `0x10`, 2 of 3 `0x17` | 24 street entries (record 41 -> a Via Roma record next to it), 2 TMC offsets |
| `0x04` | 460 -> 464 records: the six removed ones dropped, ten empty ones (`0x7FFF`, scheme 0) |

### Step 7: validation (`07_validate.py`, `pytest`, `cargo test`; **not run on a unit**)

| Check | Result |
|---|---|
| Rules on the edited street and coarse tile | hold (start node, S5 order, level groups, cycles, S10) |
| Image against the original | 6,113 sectors differ, all inside the 331 rewritten blocks; no byte of the ISO structures changed; same size |
| S6 twins of both edited tiles | 64 / 64 and 25 / 25 point back at the same absolute position |
| Router on the ring, 4 links, 2 Viale arms (one-way bits, ten pairs, vs the OSM ways and a hand-written list) | 10 / 10: same node sequence (e.g. W -> NE = W R5 R6 R1 R2 NE), lengths within 3 m / 8 % (132 vs 134 m, 224 vs 224 m, ...) |
| Spatial index `check_spatial_index.py` on the copy (all 128,690 tiles) | no failures; `tiles_at` at the centre gives the street and the coarse tile |
| 928 `0x0E` street runs | every run lands on records with the same street names; ranges unchanged unless the run lost a record |
| 24 `0x10` entries, `0x04` | same street; 464 records, survivors keep their numbers; 0x04 envelope = 0x0E ranges still true for 928 / 928 runs |
| Independent Rust decoder, `dump-block` on 8 edited blocks (street, coarse, a street and a coarse neighbour, `0x0E`, `0x10`, `0x04`, `0x17`) | identical to our decoder |
| `pytest` | 88 passed (7 new, `tests/test_tile00.py`). `cargo test --release`: 3 passed |
| `03_delta.py --tag after` | the 3 OSM ring ways are on the disc as junction type 6 (3 of 12; the other 9 are other roundabouts of the 500 m area, not edited) |
| Picture | `dataset/before_after.html`: the arms leave the ring where OSM's do |

## Open and not checked

- **Free space on the DVD: none.** Blocks tile `DB_0` (4,194,198 of 4,194,199 sectors; one single sector gap after block 0) and `DB_1` (2,295,483 of 2,295,483) completely, so a block that outgrows its
  sectors cannot be moved into slack. This test needed none (80 B left in the street tile, 83 B in the coarse one); a bigger edit would have to grow `DB_1` and patch the ISO directory records and
  volume size, as in the CD case (`01-architecture.md` §4.4.1), and rewrite the BLOCK_ID (its low byte is the length in sectors) in every reference of the census table.
- **Nothing was run on a unit.** See [`HARDWARE_TEST.md`](HARDWARE_TEST.md): which media and unit, what to look at. A burned DVD needs the DVD builder (roadmap D15).
- **Prolog words.** Words 24 to 26 of the 116-byte header of a street tile (`0x726 0x726 0x724` here) vary from tile to tile and match no count, length or
  class sum we tried; the editor keeps them as they were. If the unit checks them against the content, the edited tile is wrong there.
- **Unit questions** (hardware only): does it need S4 level-group order (kept) and the coarse tile to agree with the street tile (done); does a missing
  record in a `0x0E` run matter (the runs were shrunk, not split); what does the S7 shape-point flag byte (0, 1, 2; we write 0) do.
- **Not taken from the disc:** shape-point flag values, junction-type 9 for the links (copied from the old connectors), form `0xC` for the links
  (OSM `secondary_link` could be a slip role; slip forms 8-0xA were not used).
- **House numbers** of record 41 are gone. Names of the arms (Via Roma, Viale della Repubblica) stay on the records OSM names.
- **Coarse levels 0x02 / 0x01** hold no class-2 road, so they are untouched. Coarse levels were not re-derived by the rule of §6.7, only copied from the street records.
- **Rule exceptions on other tiles** (10 tile-edge node cycles, 36 S10 entries) mean the editor's `check()` is a statement about this tile and its
  neighbours, not about every tile of the disc.
