# Plan: growable tiles, and a faithful roundabout at Modugno

Hand-off document for an agent that starts without any context. Read it top to bottom once, then work
through section 5 in order. Everything it claims is either verified (with the place to re-check it) or
marked **unknown**; do not turn an unknown into a fact without an experiment.

## 1. Goal and definition of done

OpenCarin's goal is to **update the map of a CARiN navigation disc from OpenStreetMap** so that the
original unit accepts it. This example is the smallest end-to-end test: at Modugno (Bari), around
41°05'16.1"N 16°47'22.6"E, a roundabout was built after the 2016 data of DVD `NAV_DB_21708`; the disc
still has a crossing there.

What exists: the crossing is replaced by a *simplified* roundabout (3 ring nodes, straight arms) by
re-using the 8 existing segment records, because our tile encoder cannot add records. The drawing is
therefore only approximate. See `CHANGES.md` and `dataset/before_after.html` (regenerate, see 2.3).

**Done means**, for the same area:
1. A tile editor that can **add** records (segments, nodes, shape points) to a street-level `0x00` tile and
   keep everything consistent, verified as in 5.3 (not just "it decodes").
2. The Modugno area redrawn from OSM with the real topology: 6 ring junctions, the 6 one-way links, arms
   with their real shape points, one-way directions, names; the old crossing gone.
3. The coarse levels (`0x01`-`0x03`) of the edited area consistent with it (5.7), or a documented
   experiment showing they need not be.
4. A validation battery (5.8) that passes on the patched copy, and a hand-off for the hardware test (5.9).
5. `CHANGES.md`, `docs/carindb/03-road-network.md` and the roadmap updated; work committed on a branch.

You can **not** test on a unit yourself. Acceptance by the unit is the user's step (5.9); until then say
"not run on a unit" in every report.

## 2. State of the repository

### 2.1 What to read first (in this order)
1. `CLAUDE.md` (project rules; graphify), `README.md` (status).
2. `examples/04_update_modugno_roundabout/README.md` and `CHANGES.md`: what was done and how.
3. `docs/carindb/03-road-network.md` §6.7 (segment record, nodes, "Writing road tiles", the paragraph
   "Node cycles, ordering and editing a tile in place", section 10).
4. `docs/carindb/04-cf1-codec.md` §9.11.4, 9.11.12 (the packed `0x00` block) and `carin/parser/cf1/decoder_00.py`
   (`decode_type00`, `_Enc00`, `encode_type00`, `_layout_end`).
5. `docs/carindb/06-objectives-roadmap.md` (what is known, what is open).
6. `examples/04_update_modugno_roundabout/04_patch_tile.py` (the in-place patch, with its checks).

### 2.2 Branches and commits
Work is on branch `example-modugno-roundabout` (commit `0c16aae`) cut from `main`; `example-address-lookup`
(PR #30) is a different, open line (house numbers and an address-lookup example). Do not push, merge or open
PRs unless the user asks. Commits: Conventional Commits, English, end with the attribution line the
harness gives you.

### 2.3 Running things (macOS, `uv`)
```bash
uv run --with numpy python examples/04_update_modugno_roundabout/01_extract_disc.py --tag before
uv run --with numpy python examples/04_update_modugno_roundabout/04_patch_tile.py           # dry run
uv run --with pytest --with numpy pytest -q                                               # 81 tests, must stay green
carindb-rs/target/release/carindb-rs --iso <iso> dump-block <sector>                     # one block, Rust decoder
(cd carindb-rs && cargo build --release && cargo test --release)
```
`dataset/` is git-ignored. `dataset/NAV_DB_21708.ISO` (repo root) is a symlink to the user's original 4.1 GB
image: **never write to it**. The working copy is `examples/04_update_modugno_roundabout/dataset/NAV_DB_21708_copy.ISO`,
made with `cp -c <original> <copy>` (APFS clone: instant, no extra space). `04_patch_tile.py` reads the tile
**from the copy**, so before a fresh run re-clone it (it holds the first patch now) and run step 01 with
`--tag before` first. OSM data: `02_fetch_osm.py` (Overpass; the main server is often busy, the script
retries and falls back to a mirror). `dataset/before_after.html` is built by hand from `before.svg` and
`after.svg` (written by `04_patch_tile.py`); `qlmanage -t -s 1000 -o <dir> file.svg` renders an SVG to PNG.

### 2.4 Tools you can use
- Python reader/decoder: `carin/parser/` (`iso.py` volume, `cf1/` codec, `geometry.py`, `spatial.py`,
  `house_numbers.py`). `CarinVolume(IsoImage(path))`, `vol.calibrate()`, `vol.block(sector).payload`.
- Rust (`carindb-rs`, an independent port of the decoders; **reverse-engineering tooling only**, no end-user
  features): `dump-block` (one block, 0.6 s), `xref <BLOCK_ID...>` (every byte-aligned occurrence of a
  BLOCK_ID in decoded blocks: one pass over the 4 GB disc; slow with many IDs, fine with one), `dump-type`
  and `stats` (whole-disc passes: avoid unless needed).
- `scripts/codec_cf1/oracle_00.py` (decoder oracle on CF=0/2 tiles), `scripts/geo/check_spatial_index.py`,
  `scripts/routing/check_house_number_sides.py`, `examples/03_address_lookup` (only on branch
  `example-address-lookup`).
- Not available: `timeout` (macOS), `matplotlib`, long `sleep` (use background commands and `Monitor`).

## 3. Facts about the tile you will edit

Tile `0x4c184f18`: sector 4,986,959 (`BLOCK_ID >> 8`), CF=1, **24 sectors on disc (12,288 B), encoded
size 12,125 B** (163 B of room), 25,600 B decoded (50 sectors of 512 B). Header (decoded) `4c184f18 0000 07 08`.
Frame: x0 259,915,776, y0 228,184,064, 98,304 square; local unit = 64 CARiN units (1.28 m N, 0.97 m E here).

Sections (offset, count, record size) of the decoded tile; the name blob starts right after S14
(`_layout_end`); S4 and S3 each have **one extra record** after `count` (sentinel):

| S | off | count | rec | what |
|---|---|---|---|---|
| 0, 1, 2 | 116, 148, 180 | 3, 3, 138 | -, -, 10 | S2: street names (text pointers in `+0`, `+2`) |
| 3 | 1560 | 7 | 4 (+1) | level groups: `u16` first S4 offset, `u16` first S5 offset (see below) |
| 4 | 1592 | 460 | 32 (+1) | segments (the road graph) |
| 5 | 16344 | 294 | 8 | nodes `u16 u, u16 v, u16 first segment, u16 flags` |
| 6 | 18696 | 64 | 16 | tile-edge nodes with twins in neighbour tiles |
| 7 | 19720 | 238 | 6 | shape points `u16 u, u16 v, u8 flag` |
| 9, 8, 10 | 21148, 21188 (empty), 21188 | 5, 0, 27 | 8 | S9 neighbour tiles; S10 forbidden turns |
| 11, 12, 13, 14 | 21404, 21556, 22104 (empty), 22104 | 25, 91, 0, 151 | | signposts, TMC, toll, name prefixes |

Verified rules (see `03-road-network.md` §6.7 for the evidence; the ones marked * were re-checked on this tile):
- *The start node of a segment is the end with the lower `(x, y)` (460 / 460). The S5 nodes are sorted by
  `(x, y)` inside each level group of S3. Both are **required** by the unit (breaking them crashed it).
- *The segments meeting at a node form a cycle: node `+4` is the first, `+0x06` (start) / `+0x08` (end) the
  next; clockwise by the bearing leaving the node, from the smallest (262 / 262).
- *S3 groups: `S4` records are ordered in level groups too (group starts at S4 offsets 0x638, 0x858, 0x858,
  0xd38, 0x1838, 0x3eb8, 0x3f78: the second group is empty; our crossing's records, 17-55, are the third). **Unknown**: whether the
  unit needs a new record to sit in the right group; a record appended after the last group would be in the
  wrong one.
- *S10 entries: `u32 BLOCK_ID` (own tile), `u16` offset of a target segment, `u16` flag; owner and target
  always share a node (27 / 27). `+0x12` of the segments is monotone.
- Segment record fields (offsets, one-way bits, junction type 6 = roundabout, class, length in metres,
  bearings in 1/256 turn): §6.7 table. Template ring records exist in this tile (records 177-180).
- `0x04` house numbers: one 10-byte record per S4 segment (count = S4 count, no sentinel).
- Every pointer field inside the packed tile is listed by the encoder `_Enc00` (`decoder_00.py`): each
  `index()`, `even()` and `put(self.pb, ...)` call is one. Sections 3, 9, 10 and 12 are copied raw
  (no pointer re-encoding) and still hold absolute offsets or tile IDs.

## 4. Constraints and conventions

- English in code, docs, commits. Match the surrounding style; no new abstractions without need.
- Evidence rules (`06-objectives-roadmap.md`): disc data decides; the CC-93 (m68k) firmware is a hint only;
  the RoadRunner (MIPS) firmware is the reader of these DVDs. A field is "known" only if it holds on every
  block checked and, where possible, matches OSM.
- Never write to the original ISO. Re-clone the copy when you need a clean start.
- Do not copy code from `lugovskovp/QGIS_VDO` (GPL-3.0; this project is MIT). Facts are fine.
- Every change to the disc copy goes into `CHANGES.md` (what, where, result). Say what you did not check.
- Prefer one-block tools and small areas; avoid whole-disc passes (4 GB). Bulk decoding of a type goes
  through `carindb-rs dump-type`, not Python.
- Report faithfully: "decodes", "re-reads identically" and "accepted by the unit" are three different claims.

## 5. Work items, in order

### 5.1 External reference census
Find **everything outside the tile that points into it**: `carindb-rs --iso <copy> xref 0x4c184f18`
(one pass). Classify each hit by the structure it sits in (type of block, field). Expected: spatial index
`0x09` S1, `0x0E` S2 links (BLOCK_ID + S4 offset + count), `0x04` `+0x0C`, `0x0C` city centre, neighbour
`0x00` S6 twins and S9, coarse tiles (links down, S8). **Unknown**: whether coarse tiles or others store
*node* offsets of this tile's S5 (they would break if S5 moves) and whether anything stores S6 offsets besides
the neighbour twins. Output: a table "who points where, with which offset kind" in `CHANGES.md`. This
decides everything in 5.4.

### 5.2 Pointer catalog and a semantic comparator
1. Derive the complete list of absolute-offset fields of a decoded `0x00` tile from `_Enc00` and the raw-copied
   sections (list in 3). For each: field, target section, whether it is an index or a byte offset.
2. Write `tile_graph(decoded) -> dict`: a **layout-independent** description of the tile (segments with their
   fields, nodes with coordinates and flags, shape points per segment, cycles, S10 turns as (segment, segment, flag),
   S11/S12/S13/S14 contents with text resolved, names resolved, S3 groups as segment/node ranges). Two tiles that
   differ only by where their sections sit must give equal dicts. This is your oracle for the rest.
3. Test the comparator on the original tile and on the patched tile (they must differ in exactly the 8 records).

### 5.3 Tile editor with section growth (the core)
Build `carin/parser/cf1/` (or a new module) `relayout`: take a decoded tile and a list of changes (add / remove
segment, add node, add shape points to a segment), produce a new decoded tile in the **canonical layout**
(sections contiguous in the original order, name blob after S14, padded to 512 B), rewriting every pointer from
the catalog of 5.2. Order of work:
1. **Null relayout**: rebuild the tile with no change; must equal the input byte for byte.
2. **Forced shift**: give S4 (or S5, S7) extra empty room and rebuild; `tile_graph` must equal the original's,
   the Python and the Rust decoders must read the re-encoded block identically, and `encode_type00` must
   accept it. Do this for each of S4, S5, S7 separately, then together.
3. **One added record**, then one added node (sorted into its level group), then added shape points.
4. Keep the S4 level groups in order (a new record goes into its group; S3 and all later S4 offsets change;
   then every external S4 offset found in 5.1 changes too: 5.4). If you find the unit does not need the group
   order, say so with evidence, not by assumption.
5. Keep the rules of section 3 (start node, S5 sort, cycles, S10 monotone and shared-node) as `check()`s
   (see `04_patch_tile.py`) that run on every produced tile.

Acceptance: items 1-3 pass on tile `0x4c184f18`, and on at least 20 other CF=1 tiles of different sizes
(sample them with the Rust `dump-block` or the Python reader: this is a test of the editor, not of the unit).

### 5.4 External fix-ups
For everything found in 5.1, rewrite what a growth changes:
- **Neighbour tiles' twins.** `S6 +8 u32 BLOCK_ID`, `+12 u16 offset` of the twin: if S6 of this tile moves, every
  neighbour that points at it must be re-encoded with the new offset (S9 lists the neighbours). Same for any
  other structure from 5.1 that stores an offset into a section that moved.
- **`0x0E` runs** (`s4_offset`, `s4_count`) if S4 records move (inserting inside a level group): `encode_type0E`
  exists (CF=1, oracle 10/10) and `decode_s2_links` reads the fields.
- **`0x04` block** of the tile: add one record per added segment (no numbers: `f0..f3 = 0x7FFF`, `f4 = 0`), at the
  same positions as the S4 records. The block is CF=0 or CF=2; keep it in place if it fits.
- **BLOCK_ID length.** The low byte of a BLOCK_ID is the block length in sectors and is stored in every
  reference. If the encoded tile needs more than 24 sectors it must move: 5.5.

### 5.5 Fitting on the disc
The encoded tile must fit its sectors (163 B of room now) or the block must move to free space. Moving was
done on a CD with success (`01-architecture.md` §4.4.1, "Moving a block": the file grew, the following ISO
structures were patched, every pointer rewritten). On this DVD: **unknown** where free space is (the ISO volume
has no slack inside `DB_0`/`DB_1`; check the file extents and what follows them, `iso.py`). Options, in order of
preference: keep the block within its extent by freeing room (a coarser shape elsewhere in the tile; **not** by
dropping data silently); use the zero padding of a neighbouring block only if the block order allows it and update
every BLOCK_ID reference (5.1); append at the end of `DB_1` and patch the ISO directory records and volume size
as in the CD case. Document the choice and what you rewrote.

### 5.6 Redraw the roundabout from OSM
Inputs: `dataset/osm_ways.json` (Overpass, `out geom tags`; 486 ways in 600 m; re-fetch if missing).
Ring: ways `1326505905`, `1383238947`, `1383238946` (20 vertices, about 29 m across, counter-clockwise). Six
junctions: links `80640277` (out), `80640279` (in), `1326505910` (in), `1331933266` (out) and Viale della
Repubblica `503040064` (out), `529215906` (in); Via Roma and SP1 arms join through those links.
1. Write the mapping OSM way -> record fields as a function with a table in `CHANGES.md`: class (`+0x10 & 0x0F`) from
   `highway` (use the disc's own statistics against OSM in `03-road-network.md` §6.7, not guesses), form (`+0x0B & 0x0F`),
   direction bits from `oneway` (and the start-node rule: reverse the shape when needed), junction type (6 for
   `junction=roundabout`), speed byte (copy from comparable disc segments of the same class), length in metres and
   bearings from the geometry, built-up bits like the neighbours.
2. Remove the old crossing's 8 records **without leaving holes the unit could read**: re-use the freed slots for
   new records first, delete the rest through the editor of 5.3 (which must then support removal and re-numbering).
3. Shape points: use the OSM vertices, simplified to the disc's resolution (1 grid unit). Keep the ring round (at least
   12 points on 29 m).
4. Names: keep Via Roma / Viale della Repubblica on the arms (S2), SP1 route numbers if the disc stores them (S11); give
   the ring and links no name. Add S10 turn restrictions only if OSM has them (it does not here).
5. Rebuild node cycles for every touched node (the rule in section 3) and recompute lengths and bearings.
Acceptance: `tile_graph` of the result equals the graph built from OSM for the area, modulo the generalisation you
define and document.

### 5.7 Coarse levels
Classes 0-2 appear in `0x03` (and higher) tiles. `03-road-network.md` §6.7 "How the coarse levels follow from the street
level" gives the rule (a coarse segment is the shortest same-class street path between its nodes; a node where three or
more segments meet is a coarse node; where two meet, only if class/speed/form/built-up/one-way changes; checked on
CDs, **not on the DVDs**). Steps: re-check the rule on the DVD in this area; find which coarse tiles hold the old
crossing (via 5.1 and `S8`); update them with the editor (the same machinery, on `0x01`-`0x03` tiles: check their
layout first, they are plain or packed, **unknown**). If you cannot, show by experiment on the unit (5.9) whether it matters.

### 5.8 Validation battery (all must pass before you report)
1. Structure: `check()` of 5.3 on every touched tile; `tile_graph` equality of unchanged tiles; unchanged blocks of the disc
   are byte-identical (`cmp -l` against the original: only the touched extents differ).
2. Decoders: Python re-read identical; Rust `dump-block` identical; `pytest` green; `cargo test --release` green.
3. Graph: build the routable graph of the area from the decoded tile and route across the ring in both directions with
   a small router that respects one-way bits, junction type 6 and S10; compare with an OSRM or a hand-checked set of
   10 origin / destination pairs (document them).
4. Lookups still work: spatial index (`carin.parser.spatial.tiles_at`), address lookup (example 03 on its branch), `0x0E` runs
   of the edited tile still land on records with the right names.
5. Picture: `before_after.svg` with every record drawn and OSM underneath; check by eye that the arms leave the ring where
   OSM's do.
6. Delta: `03_delta.py --tag after` shows the 12 OSM roundabout ways of the area as on the disc where you edited them.

### 5.9 Hand-off for the hardware test (blocked on the user)
Only the user can test on a unit. Prepare the request: which disc image, which scenario (search the address, route through
the roundabout from each arm, zoom in/out, the map drawing), what a pass and a fail look like, and what to send back (photos,
the crash symptom). Burning a DVD needs the DVD builder (roadmap D15, not implemented); on CD the CNI1 route from
`01-architecture.md` §4.4.1 and `docs/CARINDB_BLUEPRINT_EN.md` (CD-i Bridge, raw burn) exists but this disc is a DVD. State this
plainly and ask which unit and media the user has before building anything for it.

### 5.10 Documentation and commit
Update `CHANGES.md` (what you did, in order), `03-road-network.md` (new rules, with counts and the script that
reproduces them), the roadmap (D14/D15 status, what is now known). Put new checks in `scripts/` like the existing ones, with a
docstring of the claim they test. Commit on a branch; do not push.

## 6. Pitfalls learned (read before you edit)

- The first patch of this example broke two **required** rules (start node = lower `(x, y)`; S5 sorted inside its level
  group) because they were not in the first reading of the docs. Re-read §6.7 "Writing road tiles" before touching a tile.
- `01_extract_disc.py` once overwrote the "before" tile with the patched one (it reads the copy). Outputs are tagged
  `before` / `after` now; never run step 01 on a patched copy with `--tag before`.
- A coverage test (disc vs OSM within N metres) calls a roundabout "present" because its arcs lie near the old arms. Test
  small features by topology (junction type 6), not by geometry alone.
- `+0x0B` direction bits are relative to the **stored** direction; when a record is reversed to keep the start-node rule,
  swap them and reverse the shape.
- S10 entries must stay shared-node pairs. Removing a segment also removes the entries that name it.
- The encoder needs the decoded length to be a whole number of 512-byte sectors; header byte 7 of the packed block is that count.
- Overpass (`overpass-api.de`) is often busy; the data of the mirror may be months old (check `timestamp_osm_base`).
- The whole disc is 4 GB: a full pass in Python takes minutes; use the Rust tools.

## 7. Questions only an experiment can answer

1. Does the unit accept a tile whose S4 records are not in level-group order? (Prefer keeping the order.)
2. Does it need coarse tiles consistent with the street level for routing, or only for drawing?
3. What does a self-targeted S10 entry (used here to neutralise two turns) do? Better: remove the entries once the editor can.
4. Does the unit use `0x04` for anything but the address search?
5. Where is free space on this DVD for a block that outgrows its extent?
Each one is a hardware or disc-structure question; list the ones you could not settle in your final report.
