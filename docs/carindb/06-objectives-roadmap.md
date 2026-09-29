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
| `0x01`–`0x03` | coarser levels of the same graph; S8 links a tile to the next level down, header `+84` up; node flag bits 15–14 = highest level reached; which roads and nodes reach each level | ✅ · written by us and drawn on a CNI1 (CD-ID 2952) · ❓ the ~4% of runs left out, shape simplification, node codes 2 and 4 | `03-road-network.md` §6.7 |
| `0x04` | per-segment house numbers of the linked `0x00` tile (one 10-byte record per S4 segment); `0x0E` S2 ranges are their envelope | ✅ · ❓ left/right and start/end orientation | `03-road-network.md` §6.4 |
| `0x06` | POI spatial index → `0x10`: position, category, brand, POI ID; sorted by X | ✅ · written by us on a CNI1 | `02-geo.md` §8.1 |
| `0x07` → `0x08` → `0x09` | country info (§4.2) + spatial index: layer directory (12 × 28 B), quadtree grid split over consecutive `0x08` blocks, cell node = column-major grid of `u16` item pointers into a `u32` tile list | ✅ every field of `0x08`/`0x09` and the lookup `carin.parser.spatial.tiles_at` (both DVDs, `scripts/geo/check_spatial_index.py`; 21708: 128,690 / 128,690 tiles; 21734: 144,143 reached from `0x07` + 3,129 `0x06` only through an unreferenced 512² grid) · layer parameters, RR reader `dbq` `0x21270`: param 0 ✅ highest road class of road layers `0x00`–`0x03` (`rpmod` `0x7490c`, checked on every segment of both DVDs), param 1 🟡 lower scale bound (`dbq` `0x5508`, unit ❓), params 2–3 ❓ (not read) · `0x07` `+0x164` trailer: RR read offsets ✅, meaning ❓ | `02-geo.md` §7.3 |
| `0x0A` | country table: `0x0D` city-trie root, language, left-hand traffic, `COUNTRY_ID`, ISO code, per-category `0x11` POI-trie roots | ✅ · ❓ `+0x1C` (500/300/1000/500 everywhere), `+0x26` | `01-architecture.md` §4.4 (PR #13) |
| `0x0B` | alphabetical index | 🟡 | `01-architecture.md` §4.3 |
| `0x13` | CD info (zlib) | 🟡 | `01-architecture.md` §4.1 |
| `0x0C` | city records: name, post town, `0x0F` road-trie root, POI index by category (S3) and brand (S5), city-centre `0x00` segment | ✅ S0, S1, S3, S5 (issue #21) · written by us on a CNI1 | `01-architecture.md` §4.4.1 (PR #13), §4.4.2, `03-road-network.md` §6.6 |
| `0x0D` / `0x0F` / `0x11` | letter tries (city / road / POI names) → `0x0C` / `0x0E` / `0x10`; build rule for `0x0F` known; `0x11` is a first-letter index (almost always one level) | ✅ (checked on DVD 21708 too) · ❓ `0x0D` split rule | `03-road-network.md` §6.3.2, `01-architecture.md` §4.4.1 |
| `0x0E` | **street-name directory**: name, kind, language, locality → runs of `0x00` segments + house-number ranges | ✅ | `03-road-network.md` §6.3.1 |
| `0x10` | POI records (name, locality, brand, address, phone, POI ID, road link); branded POIs in a category copy and a brand copy | ✅ · written by us on a CNI1 | `02-geo.md` §8.1.1, `01-architecture.md` §4.4.2 |
| `0x14`–`0x16`, `0x1C`–`0x1E` | background layers (sea, forest, built-up, rivers, rail) per zoom | ✅ categories | `02-geo.md` §8.4 |
| `0x17`, `0x19` | TMC locations: `0x17` the location tables of 13 countries (100 B records by location code), `0x19` ~92,000 records in Germany sorted by position, linked to a `0x00` S4 segment and to other `0x19` records; both one linked block chain | ✅ chains, keys, `0x19` tile/segment links (both DVDs) · ❓ other record fields | `03-road-network.md` §6.7 (S12), `01-architecture.md` §4.7 |
| `0x12` | root / superblock (schema, `RECORD_SIZE_TABLE`, DB-REL) | ✅ | `01-architecture.md` |
| `0x18` | TMC location-table index: one block per table (`TABLE = LTN << 4 \| CC`), 0x17 `BLOCK_ID` + first location code; reached from `0x07` S1 | ✅ (both DVDs; CC/LTN match the published TMC list, UK LTN 10 not listed) · ❓ `0x07` S1 `+0x0A` bytes | `01-architecture.md` §4.7 |
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
   values 4 and `0x10`; DB-REL < 34 discs.
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
   (98.8%, `scripts/routing/check_04_house_numbers.py`). Left open: which side is left/right
   and whether `f0`/`f1` are the start-node numbers (needs segment geometry).

### B. RoadRunner firmware (`bsw2`)
6. **Route cost**: find the readers of speed (`+0x0A & 0x1F`) and the edge fields from
   `sub_01fd80`; recover the cost function and how turn restrictions (S10) apply.
7. **Graph traversal**: callers of `sub_01fd80` / `sub_04e02c`, tile crossing via S6 twins,
   level switching via S8.
8. **Unknown fields the firmware reads**: `+0x10` bit 7, `+0x1D` bits 4–6, `+0x18 & 0x10`,
   node `+6` flags, S10 flags 2/3, the per-block-type table `gp[-0x7A30]`.
9. **Issue #6**: where `subrel` (LAYOUT `+2`) comes from; trace the RR `db_pub` setup.
10. **RR vs Mk3 `db_pub`**: diff the CF=1 decoders (the listings in `docs/fw/` are Mk3).
    Done for `0x00` (§9.11.12) and `0x14`–`0x1E` (§9.11.11); `0x0E` and `0x29` remain.

### C. Library and export
11. **Typed records per block type** (`carin` API) instead of per-type scripts.
12. **Routable export**: nodes/edges with length, class, speed, one-way, toll, turn
    restrictions, names, house numbers → GeoPackage + a routing format; check routes against
    OSM/OSRM in a test area.
13. ~~**Unknown blocks** `0x18`, `0x1A`, `0x1B`~~ Done 2026-09-29 (`01-architecture.md` §4.7,
    `scripts/routing/check_tmc_index.py --geometry`, issue #17; DVDs 21708 and 21734): TMC
    indexes over `0x17` and `0x19`. Left open: the remaining `0x17` and `0x19` record fields;
    `0x1A`/`0x1B` `0x0104`, `0x1000`; `0x07` S1 `+0x0A`; the firmware reader (none found; the
    `hdltmc +0x2f620` switch is not one).

### D. Writer / compiler
14. Encoders: plain (CF=0) `0x00`–`0x03` tiles first; then `0x0E`, `0x0D`/`0x0F`/`0x11`,
    `0x06`/`0x10`, `0x14`–`0x16`, the spatial index `0x07`–`0x09`, superblock and
    `RECORD_SIZE_TABLE`. CF=1 is not needed to generate a valid DB (only `encode_type0E` exists;
    it now keeps the names). Evidence the approach works: renamed streets and a made-up city
    run on a CNI1 (PR #13, `01-architecture.md` §4.4.1); the destination label still showed the
    old names, so find which copy it reads before generating whole regions.
    Done on a CNI1 with CD-ID 2952 (2026-09-28/29): plain `0x00` tiles from our own records
    (drawn, routed, turn-by-turn guidance, also in a country of empty tiles), their `0x03`,
    `0x02` and `0x01` parents, and a city's whole POI index (`0x06`, `0x10`, `0x11`, `0x0C`
    sections 3 and 5; `03-road-network.md` §6.7, `01-architecture.md` §4.4.2). Next: a POI index
    and coarse tiles for a disc of our own roads only, then a writer in the library.
15. Disc image builder (DVD split `DB_0`/`DB_1`, 512-byte unit) and a round-trip test:
    re-encode a region of 21708 and read it back with our reader.

### E. Housekeeping
16. Refresh the graphify graph (`graphify update .`); it still points at the old `carin/parser/cf1.py`.
17. `02-dbq-engine-mechanics.md`: handler addresses after `bsr.w` were lost to shell escaping; recover them from `dbq/dbd.asm`.

## Constraints / non-goals

- `/TPD/*` third-party data (POI marketing, HTML) is not needed for routing.
- CF=1 is needed only to read original discs, not to generate one (CF=0 + CF=2 suffice).
- No block checksum exists.
