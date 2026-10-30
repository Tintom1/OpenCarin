# Part 6 — Objectives, Status & Roadmap

> **Status: 🎯 OPEN — rewritten 2026-09-28** after merging the community findings
> (PRs #3–#12) and the first pass over the RoadRunner firmware. This is the worklist:
> what is known, what is not, and what "done" means for each open item.

---

## Project goal

1. **Read** CARINdb completely: every block of a DB-REL 34 DVD (`NAV_DB_21708`,
   `NAV_DB_21734`) decoded to typed records with known meaning, exported as a routable
   road network with geometry, names, house numbers, POIs and background layers.
2. **Write** it: compile OpenStreetMap data into a disc the original units accept.

Discs used for evidence: DVD 21708 and 21734 (DB-REL 34, in `dataset/`); CD 21594
(DB-REL 34) and CD 2952 (DB-REL 22), tested by a contributor. Firmware: see
[`../fw/03-firmware-provenance.md`](../fw/03-firmware-provenance.md).

## Evidence rules

- **Disc data decides.** A field is ✅ when it holds on every block of at least one DVD and,
  where possible, matches OpenStreetMap or a second disc.
- **RoadRunner (RR, MIPS) firmware** is the reader of our DVDs: use it to confirm and to find fields.
- **CC-93 (m68k, `dbq/`, `rpmod/`)** is an older CD-only platform: a hint, never proof on its own.
  Three CC-93-only conclusions were overturned by data (see "Corrected" below).

---

## 1. Byte-level decoding (NAV_DB_21708)

Every block is readable except one group:

| Encoding | Types | Status |
|---|---|---|
| CF=0 (plain) | all | ✅ |
| CF=2 (zlib) | all | ✅ |
| CF=1 (bit-packed) | `0x00`, `0x0E` | ✅ `carin/parser/cf1/`; `subrel` detected per disc (`CarinVolume.calibrate`), CD layout supported, `dec_text` overwrite fixed (was corrupting ~8% of `0x00` blocks; cause: the missing pass `0x15` sentinel, fixed 2026-09-28); packed `0x0E` name blob decoded and re-encoded (`enc_text`, PR #14: all 563 blocks of 21708 end on the data end) |
| CF=1 | `0x14`–`0x16`, `0x1C`–`0x1E` | ✅ one decoder, transcribed from RR `db_pub` `sub_004b88` (2026-09-28). Oracle `oracle_14_16.py` qualified on all 20,227 CF=0/CF=2 blocks, then passes all CF=1 blocks: 21708 186/1,446/7,719/318/80/14, 21734 250/2,265/11,049/544/103/14 (`0x14`/`0x15`/`0x16`/`0x1C`/`0x1D`/`0x1E`). The CC-93 port it replaces passed 0 (missing passes, empty-section overwrite). S2 `+0x0e` comes from a last pass no RR build reads (data-derived) |
| CF=1 `0x00`, DB-REL 34 | passes `0x15`/`0x17` and the `+0x18` pass | ✅ 2026-09-28: pass `0x15` sentinel record (Mk3 and RR read it, the port did not) and pass `0x1B` (`+0x18`, RR `sub_005e6c +0x6e70`). Oracle `oracle_00.py` qualified on all 13,353 CF=0/CF=2 tiles, then passes all CF=1 tiles: 86,107/86,107 (21708), 91,651/91,651 (21734); before, 0 of each. Last bit after pass `0x1B`: a single 1 no firmware reads (`04-cf1-codec.md` §9.11.12) |

## 2. Block types and their meaning

| Type | Role | Status | Where |
|---|---|---|---|
| `0x00` | street-level tile: geometry + routable graph + names | ✅ S2, S4 (incl. `+0x18`), S5, S6, S7, S9–S14 · ❓ S0, S1, S3 | `02-geo.md` §8.3, `03-road-network.md` §6.6–6.7 |
| `0x01`–`0x03` | coarser levels of the same graph; S8 links a tile to the next level down, header `+84` up (`+88` on DB-REL 34: 2007 CD, PR #36, and DVD 21708); node flag bits 15–14 = highest level reached; which roads and nodes reach each level | ✅ · written by us and drawn on a CNI1 (CD-ID 2952) · ❓ the ~4% of runs left out, shape simplification, node codes 2 and 4 | `03-road-network.md` §6.7 |
| `0x04` | per-segment house numbers of the linked `0x00` tile (one 10-byte record per S4 segment); `0x0E` S2 ranges are their envelope | ✅ · ❓ left/right and start/end orientation | `03-road-network.md` §6.4 |
| `0x06` | POI spatial index → `0x10`: position, category, brand, POI ID; sorted by X | ✅ · written by us on a CNI1 | `02-geo.md` §8.1 |
| `0x07` → `0x08` → `0x09` | country info (§4.2: S0 = POI category list, issue #24) + spatial index: layer directory (12 × 28 B), quadtree grid split over consecutive `0x08` blocks, cell node = column-major grid of `u16` item pointers into a `u32` tile list | ✅ every field of `0x08`/`0x09` and the lookup `carin.parser.spatial.tiles_at` (both DVDs, `scripts/geo/check_spatial_index.py`; 21708: 128,690 / 128,690 tiles; 21734: 144,143 reached from `0x07` + 3,129 `0x06` only through an unreferenced 512² grid) · layer parameters, RR reader `dbq` `0x21270`: param 0 ✅ highest road class of road layers `0x00`–`0x03` (`rpmod` `0x7490c`, checked on every segment of both DVDs), param 1 🟡 lower scale bound (`dbq` `0x5508`, unit ❓), params 2–3 ❓ (not read) · `0x07` `+0x164` trailer: RR read offsets ✅, meaning ❓ | `02-geo.md` §7.3 |
| `0x0A` | country table: `0x0D` city-trie root, language, left-hand traffic, `COUNTRY_ID`, ISO code, per-category `0x11` POI-trie roots | ✅ · ❓ `+0x1C` (500/300/1000/500 everywhere), `+0x26` | `01-architecture.md` §4.4 (PR #13) |
| `0x0B` | alphabetical index: one-level letter index over the `0x0A` countries | ✅ · record layout and leaf → type − 1 rule checked on both DVDs (issue #18) | `01-architecture.md` §4.3 |
| `0x13` | CD info (zlib): two one-record sections (DB-REL, string offsets/lengths) + build-info text | ✅ layout (2007 CD, both DVDs; issue #19) · ❓ the 16 bytes 111,111,111 × 1..4 (placeholder or box 10° W..30° E, 40..80° N), the leading `1` fields | `01-architecture.md` §4.1 |
| `0x0C` | city records: name, post town, `0x0F` road-trie root, POI index by category (S3) and brand (S5), city-centre `0x00` segment | ✅ S0, S1, S3, S5 (issue #21) · written by us on a CNI1 | `01-architecture.md` §4.4.1 (PR #13), §4.4.2, `03-road-network.md` §6.6 |
| `0x0D` / `0x0F` / `0x11` | letter tries (city / road / POI names) → `0x0C` / `0x0E` / `0x10`; build rule for `0x0F` known; `0x11` is a first-letter index (almost always one level) | ✅ (checked on DVD 21708 too) · ❓ `0x0D` split rule | `03-road-network.md` §6.3.2, `01-architecture.md` §4.4.1 |
| `0x0E` | **street-name directory**: name, kind, language, locality → runs of `0x00` segments + house-number ranges | ✅ | `03-road-network.md` §6.3.1 |
| `0x10` | POI records (name, locality, brand, address, phone, POI ID, road link); branded POIs in a category copy and a brand copy | ✅ · written by us on a CNI1 | `02-geo.md` §8.1.1, `01-architecture.md` §4.4.2 |
| `0x14`–`0x16`, `0x1C`–`0x1E` | background layers (sea, forest, built-up, rivers, rail) per zoom | ✅ categories | `02-geo.md` §8.4 |
| `0x17`, `0x19` | TMC locations: `0x17` the location tables of 13 countries on the DVDs, 14 on the 2007 CD (100 B records by location code: names, parent, road, previous / next point, six coordinate pairs), `0x19` (DVD only) ~92,000 records in Germany sorted by position, linked to a `0x00` S4 segment and to other `0x19` records; both one linked block chain | ✅ chains, keys, `0x19` tile/segment links (both DVDs); `0x17` record layout, section 12 link `(direction, code, flags & 0x3FF = table id)` (2007 CD, `check_tmc_locations.py`) · ❓ bits of `+0x02`, `+0x05` and `flags >> 10`, which of the six points is which, `+0x1C`/`+0x1E` | `03-road-network.md` §6.7 (S12), `01-architecture.md` §4.7 |
| `0x12` | root / superblock (schema, `RECORD_SIZE_TABLE`, DB-REL, two coverage boxes, `BLOCK_MAP` of first / last block per type) | ✅ · ❓ what the coverage boxes are used for | `01-architecture.md` §3 (PR #37) |
| `0x18` | TMC location-table index: one block per table (`TABLE = LTN << 4 \| CC`), 0x17 `BLOCK_ID` + first location code; reached from `0x07` S1 | ✅ (both DVDs and the 2007 CD, 14 tables; CC/LTN match the published TMC list; UK: the DVD table has LTN 10 and the published list 7, the CD's road tiles use both, `01-architecture.md` §4.7) · ❓ `0x07` S1 `+0x0A` bytes; `0x07` S1 not checked on the CD | `01-architecture.md` §4.7 |
| `0x1B` → `0x1A` | position index over `0x19`: root (key origin 13.5° E 52.5° N, COUNTRY_ID) → one `0x19` `BLOCK_ID` + first key per block; `0x1B` is in the `0x07` layer directory | ✅ (both DVDs): key = 100 m steps on a 6,371 km sphere, `x` scaled by `cos φ`, rounded · ❓ `0x0104`, `0x1000`; no firmware reader found | `01-architecture.md` §4.7 |

## 3. Corrected conclusions (do not rely on the old text)

| Old claim | Now | Source |
|---|---|---|
| `0x0E` is the routing graph; cost formula from `0x0E` S1 | `0x0E` is the street-name directory; the graph is S4 of `0x00`–`0x03` | PR #10, #12 |
| `0x0E` S2 `+8..+14` are coordinate deltas (`decode_s2_coords`) | even/odd house-number ranges | PR #10 |
| `0x00` S4 is a BSP tree, `+0x06`/`+0x08` children | next segment at start / end node | PR #12 |
| `can_traverse` always returns 1; `rpmod` never reads `0x00` records | rejects class 6 and junction 3/4 unless high nibble 4; reads S4 records | PR #12, RR `sub_01fd80` |
| `subrel >= 9` follows from DB-REL 34 | per disc (CD 21594 needs 8) | PR #4, issue #6 |
| 98,304 tile grid is universal | follows from the `0x07` root square; DVD-specific value | PR #11 |
| On the DVDs all tile edges are multiples of 98,304 from `(0, 0)` | no tile corner is (0 of 128,690 / 147,272); tile sides are root / `2^k`, k = 4…16, down to 24,576; 2,837 / 3,887 tiles have a side not a multiple of 98,304 | `check_spatial_index.py`, issue #20 |
| `find_parcel` indexes `0x0E` by S2 anchors | S2 `+0/+4` are the centres of linked `0x00` tiles; the real spatial index is `0x07`–`0x09` | PR #10, #11 |
| Packed `0x00` tiles carry a `+0x18` pass no firmware reads, behind a head of unknown content | RR reads it as pass `0x1B`; the head came from the port skipping the pass `0x15` sentinel | RR `sub_005e6c`, `04-cf1-codec.md` §9.11.12 |
| `0x0A` holds a 32-bit `NAME_PTR` whose high half is a truncated `0x0D` block ID | `+0x00` is a full `BLOCK_ID` + offset + count (city-trie root); the "truncation" came from reading at `+0x02` | PR #13 |
| `0x0D`/`0x0F`/`0x11` records carry an ASCII country/street-type code `B_hi`, `B_lo` = 1 | letter + leaf flag of a name trie | PR #13 |
| `0x11` is a POI-name trie refined letter by letter | a first-letter index: all 85,313 records are leaves on CD-ID 2952, 143 of 437,838 are not on CD-ID 21594 | `01-architecture.md` §4.4.1 |
| `0x0C` S1 `+0x08` roots the city's own POI tries (categories 48, 56, 57) | one section 3 range per POI category of the city; section 5 holds the brand ranges | `01-architecture.md` §4.4.2, issue #21 |
| `0x06` `+0x10` is a brand reference | the POI ID (`0x10` detail `+0x1C`); the brand is `+0x0C` | `02-geo.md` §8.1 |
| `0x04` has 8-byte records (CC-93 `rpmod`) | 10 bytes on the DVD: two sides + numbering scheme, one per S4 segment | `03-road-network.md` §6.4 |

---

## 4. Open work, by priority

### A. Complete and correct the reader
1. ~~**`0x1C`–`0x1E` CF=1.**~~ Done 2026-09-28 (`04-cf1-codec.md` §9.11.11). Left open: the
   meaning of S2 `+0x0e` (read by no available firmware) and of S1/S2 `+4`, `+0x0a`, e4;
   the 8-byte S3 branch (no block uses it); DB-REL < 34 discs.
2. ~~**`+0x18` pass in packed `0x00` tiles.**~~ Done 2026-09-28 (`04-cf1-codec.md`
   §9.11.12): the RR reads it as pass `0x1B`; the "head" was the port's misalignment (missing
   pass `0x15` sentinel). Left open: the single 1 bit after pass `0x1B`; the meaning of `+0x18`
   value `0x10` (value 4: a hint for unpaved tracks, 2026-10-01); DB-REL < 34 discs.
3. ~~**Spatial lookup on `0x07`–`0x09`.**~~ Done 2026-09-29 (`02-geo.md` §7.3, issue #20):
   `carin.parser.spatial.tiles_at(vol, layer, lon, lat)`, checked at the centre of every
   reached tile on both DVDs. `find_bbox` marked superseded (per-type bbox offsets, §7.4);
   `find_parcel` kept for `0x0E`, which the disc index does not cover. Layer parameters
   (2026-09-29): RR reader found (`dbq` `0x21270`, `rpmod` `0x7490c`); param 0 = highest road
   class on the road layers ✅. Left open: param 0 on area layers, the unit of the param-1
   scale, params 2–3 (not read by the RR code found), the meaning of the `0x07 +0x164`
   trailer fields, whether the firmware reads the unreferenced `0x08` grid on 21734, DB-REL < 34.
4. **Retire superseded code**: `decode_s2_links` (tile link, segment run, house numbers) replaces
   `decode_s2_coords` (kept, marked superseded); remove it with `oracle_s2_coords.py` and any
   script that treats `0x0E` as geometry.
5. ~~**`0x04` vs `0x0E` S2 house numbers**~~ Done 2026-09-28 (`03-road-network.md` §6.4):
   `0x04` holds the numbers per segment and side, `0x0E` S2 their envelope per linked run
   (98.8%, `scripts/routing/check_04_house_numbers.py`). Side and end done 2026-10-01 against OSM
   addresses (`scripts/routing/check_house_number_sides.py`, §6.4): `f0`/`f1` at the start node
   (97.6%), `(f0, f2)` on the left and `(f1, f3)` on the right of the start → end direction
   (91% / 95%, Bari). Left open: the ~9% of segments that disagree, scheme 1 (mixed), a check
   outside Italy, and the RR firmware reader of `0x04` (not yet found).

### B. RoadRunner firmware (`bsw2`)
6. **Route cost**: find the readers of speed (`+0x0A & 0x1F`) and the edge fields from
   `sub_01fd80`; recover the cost function and how turn restrictions (S10) apply. **2026-10-09
   (`fw/04` §19, negative result):** exhaustively verified that no instruction in `rpmod` masks S4
   `+0x0A` with `0x1F` (only two `& 0x1F` sites exist in the whole module, both unrelated bitfield
   packers), and that neither of `sub_01fd80`'s two known callers is the route search — both are
   map-matching / position-tracking routines. **2026-10-09, same day, follow-up (`fw/04` §20):** the
   same `+0x0A` search extended to all seven sibling RR modules, also zero hits everywhere — speed is
   never read via literal-immediate `+0x0A` addressing anywhere in the RR firmware. The **turn-restriction
   half is now found**: `sub_04e02c` (the sibling unpacker)'s own caller chain (`sub_04e56c`, reached
   from a 5-function cluster distinct from `sub_01fd80`'s two callers) feeds a turn-feasibility gate
   (`sub_04757c`/`sub_0476f4`) that checks, in order, junction-type compatibility between two decoded
   edges, a now-decoded one-way field (`+0x15`: 0 = two-way, 1/2 = one-way per direction, 3 = closed),
   and exact-match membership against the per-edge S10 forbidden-turn list (`sub_047990`). The
   **cost-function half is still unfound**: no `mult`/`div` or running-total/priority-queue pattern
   occurs anywhere in that gate or in `sub_04e56c` itself — these decide whether a transition is legal,
   not how much it costs. Whether the numeric cost lives in a different RR module remains open. Not yet
   cross-checked against real S10/`+0x15` disc data (firmware-code reading only so far). Still open.
7. **Graph traversal**: callers of `sub_01fd80` / `sub_04e02c`, tile crossing via S6 twins,
   level switching via S8. **2026-10-09 (`fw/04` §20.1-§20.2):** found a concrete candidate for the
   tile-crossing mechanism — `sub_04e56c`, `sub_04e02c`'s sole in-module caller — which follows S4's
   `+0x06`/`+0x08` next-segment links across tile boundaries via a block-resolution helper
   (`sub_04ffb0`) and the DB descriptor table. Not yet confirmed to touch a documented S6 record, and
   S8 level switching was not investigated this session. Still open.
8. **Unknown fields the firmware reads**: `+0x10` bit 7 (**UAG, unattributed geometry**, 2026-10-01: firmware `rs_dump -u` + data placeholder class), `+0x18 & 0x10`
   (**tunnel flag**, chain record `+0x1B`, `fw/04` §7), `+0x1D` bits 4–6 (3-bit category: groups the segments of one complex junction in guidance, `gd_bjl` `sub_00a810`; also used by `rpmod` costs; `fw/04` §8–9), node `+6` flags (`fw/04` §12: bits 5-4 == 2 = edge node, `& 7` 4 and 5 alike, `& 7 == 2` = fork / merge node, `BIF_SYM_2` / `BIF_SYM_3` in guidance (§13), bit 3 unused; why some S6 nodes have bit 12 is open),
   S10 flags 2/3 (data: not dead ends, not restrictions; see `examples/06_osm_vs_disc_modugno/CHANGES.md`); `examples/07_firmware_emulator` runs the `dbq` descriptor builder in an emulator and maps every descriptor byte to its S4 input bits (`fw/04` §14; the `dbq` stream, `gd_bjl` items and junction passes, `fw/04` §17), the per-block-type table `gp[-0x7A30]`.
9. **Issue #6**: where `subrel` (LAYOUT `+2`) comes from; trace the RR `db_pub` setup.
10. **RR vs Mk3 `db_pub`**: diff the CF=1 decoders (the listings in `docs/fw/` are Mk3).
    Done for `0x00` (§9.11.12) and `0x14`–`0x1E` (§9.11.11); `0x0E` and `0x29` remain.

### C. Library and export
11. **Typed records per block type** (`carin` API) instead of per-type scripts.
12. **Routable export**: nodes/edges with length, class, speed, one-way, toll, turn
    restrictions, names, house numbers → GeoPackage + a routing format; check routes against
    OSM/OSRM in a test area. Street level (`0x00`) done 2026-10-03: `carin/export/` and
    `scripts/routing/export_routable.py` write GeoPackage (nodes, edges, restrictions), CSV and
    OSM XML (read by `osrm-extract` as is); checked on a CD, 118 tiles, 34,215 segments, against OSM
    and OSRM (`03-road-network.md` §6.7, "Routable export check"). Region-based: pick tiles by
    `--bbox`. The coarse levels `0x01`–`0x03`, signposts (S11), section 13 marks and the `0x04` house
    numbers are export layers since 2026-10-05 (`--layers`, tiles decoded by all cores; `03-road-network.md`
    §6.7). Left open: what the section 13 marks are on a CD without tolls, S10 flags 2 and 3, the
    layers checked on a DVD, Valhalla, a whole-disc export (memory).
13. ~~**Unknown blocks** `0x18`, `0x1A`, `0x1B`~~ Done 2026-09-29 (`01-architecture.md` §4.7,
    `scripts/routing/check_tmc_index.py --geometry`, issue #17; DVDs 21708 and 21734): TMC
    indexes over `0x17` and `0x19`. 2026-10-09 (2007 Master CD, issue #22): `0x17` and `0x18`
    are on a CD too (1,164 / 14 blocks, 14 tables); the 100-byte `0x17` record is decoded (names,
    links, six coordinate pairs) and section 12 is populated there, `flags & 0x3FF` = table id
    (`01-architecture.md` §4.7, `03-road-network.md` §6.7, `carin/parser/tmc.py`,
    `scripts/routing/check_tmc_locations.py`). Left open: the bits of `+0x02`, `+0x05` and
    `flags >> 10`, which of the six points is which, `+0x1C`/`+0x1E`; the remaining `0x19` record
    fields; `0x1A`/`0x1B` `0x0104`, `0x1000`; `0x07` S1 `+0x0A`; the firmware reader (none found;
    the `hdltmc +0x2f620` switch is not one).

### D0. Which value to write for an OSM way (study of 2026-10-01)

`examples/06_osm_vs_disc_modugno/CHANGES.md` compares both DVDs with today's OSM, field by field. Known now: `+0x1D` bit 0 = has house numbers;
speed category = default per (class, form, built-up), not `maxspeed`; node flags follow degree, level and section; S10 flag 0 / 1 entries match OSM
restrictions; `+0x1C` 0x18 = bridge, S7 flag 2 with it. `+0x10` bit 7 = not fully attributed / UAG (write 0; firmware `FULLY_ATTRIB`, `fw/04` §10), `+0x18 & 0x10` = tunnel flag (`fw/04` §7). Hints: `+0x1D` bits 4-6 = category chaining the segments of one junction (write 0), `+0x18` = 4 (unpaved track), junction 3
(pedestrian areas), signposts on ramps from `destination`. Not known: form 7 (write 11 / 12), S10 flags 2 / 3, the values of the `+0x1D` bits 4–6 category, node nibble 4 and 2,
TMC (location table). Not done: the 2015 OSM snapshot (Overpass attic did not answer), nothing run on a unit.

### D. Writer / compiler
14. Encoders: plain (CF=0) `0x00`–`0x03` tiles first; then `0x0E`, `0x0D`/`0x0F`/`0x11`,
    `0x06`/`0x10`, `0x14`–`0x16`, the spatial index `0x07`–`0x09`, superblock and
    `RECORD_SIZE_TABLE`. The units read plain (CF=0) blocks, but a **CD needs CF=1 to fit in
    ~700 MB**: with every block plain, `carindb` would grow from 322 to ~509 MB on CD-ID 2952 and
    from 437 to ~640 MB on CD-ID 21594 (packed `0x00` tiles decode to 1.84× / 1.95× their size,
    `0x0E` to 2.27× / 2.05×, `0x14`–`0x16` to ~1.4×; 300 blocks sampled per type), and an OSM
    region is larger still. Encoders: `encode_type00` (bit-identical to the discs outside the
    text blob, tested on a CNI1) and `encode_type0E` exist; `0x14`–`0x16` / `0x1C`–`0x1E` have
    none yet. A DVD has room for plain blocks. Evidence the approach works: renamed streets and a made-up city
    run on a CNI1 (PR #13, `01-architecture.md` §4.4.1); the destination label still showed the
    old names, so find which copy it reads before generating whole regions.
    Done on a CNI1 with CD-ID 2952 (2026-09-28/29): plain `0x00` tiles from our own records
    (drawn, routed, turn-by-turn guidance, also in a country of empty tiles), their `0x03`,
    `0x02` and `0x01` parents, and a city's whole POI index (`0x06`, `0x10`, `0x11`, `0x0C`
    sections 3 and 5; `03-road-network.md` §6.7, `01-architecture.md` §4.4.2). Next: a POI index
    and coarse tiles for a disc of our own roads only, then a writer in the library.
    Editing a street tile of a DVD so that it **grows** (2026-10-01, DVD 21708): `carin/parser/cf1/tile00.py`
    (parse to a model, build with every pointer rewritten; null relayout identical and forced shifts keep the graph on 62
    tiles), `carin/parser/refs.py` (what points into a tile: `0x0E`, `0x10`, `0x17`, `0x04`, S6 twins) and `volume_edit.py`
    (re-encode and write a block in its extent). `examples/04_update_modugno_roundabout` redraws a roundabout from OSM with it,
    in the street and the coarse tile, 331 blocks rewritten in place. Done on a disc image only; **not run on a unit**
    (`examples/04_update_modugno_roundabout/HARDWARE_TEST.md`). Not done: moving a block that outgrows its sectors
    (no free room on DVD 21708: blocks tile `DB_0` (4,194,198 of 4,194,199 sectors, one single gap after block 0) and `DB_1` (2,295,483 of 2,295,483) completely; a block that outgrows its sectors would mean growing `DB_1` and patching the ISO structures, as in the CD case, `01-architecture.md` §4.4.1),
    BLOCK_ID rewrites if a block changes length, other block types.
15. Disc image builder (DVD split `DB_0`/`DB_1`, 512-byte unit) and a round-trip test:
    re-encode a region of 21708 and read it back with our reader. Partly: `volume_edit.write_block` and `examples/04_update_modugno_roundabout/06_patch_references.py`
    patch blocks of a copy in place and read them back; building and burning a new volume is not done.

### E. Housekeeping
16. Refresh the graphify graph (`graphify update .`); it still points at the old `carin/parser/cf1.py`.
17. `02-dbq-engine-mechanics.md`: handler addresses after `bsr.w` were lost to shell escaping; recover them from `dbq/dbd.asm`.

## Constraints / non-goals

- `/TPD/*` third-party data (POI marketing, HTML) is not needed for routing.
- CF=1 is needed to read original discs. To generate a DVD it is not needed (CF=0 + CF=2 suffice; the units read plain blocks and a DVD has room). To generate a CD it is needed for size: with every block plain, `carindb` outgrows ~700 MB (D14).
- No block checksum exists.
