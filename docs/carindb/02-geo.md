# Part 2 — Coordinate System & Georeferenced Records

> **Status: ✅ RESOLVED / VERIFIED.** The coordinate system is fully solved
> (0 free parameters, 2.0 km rms across 38 anchors, independently cross-checked).
> POI (`0x06`, `0x10`) and feature (`0x16`) record layouts are byte-verified.
>
> Source: `../CARINDB_BLUEPRINT_EN.md` §7–§8. Related: block layout →
> [`01-architecture.md`](01-architecture.md).

---

## 7. Coordinate System — RESOLVED

```
X = (lon + 30.0) * 2_000_000_000 / 360        lon = X / K - 30.0
Y = (lat +  0.0) * 2_000_000_000 / 360        lat = Y / K
K = 2e9 / 360 = 5_555_555.5555…  units / degree
```

A full turn of 360° equals exactly **2,000,000,000 units**: fits into a signed
`int32` (max 2,147,483,647) with margin. 1 unit = **0.18 µ°** ≈ 2 cm at the
equator. Origin is at the **equator at 30° West**; X increases eastward, Y
northward; the relationship is **linear in latitude** (no Mercator projection).

### 7.1 How it was determined

Type `0x16` blocks contain 20-byte records with absolute 32-bit coordinates and a
name pointer (§8.2). Label points of 38 European cities were extracted
(`scripts/extract_anchors.py`) and compared with published WGS84 city centers
(`scripts/optimize_coords.py`).

| Fit | K | Cx | Cy | rms | max |
|---|---|---|---|---|---|
| free (3 params, Levenberg-Marquardt) | 5,556,973 | 29.9891 | −0.0102 | 2.00 km | 4.07 km |
| hypothesis `K = 2e9/360`, `Cx = 30`, `Cy = 0` (0 params) | 5,555,556 | 30.0000 | 0.0000 | **2.00 km** | 4.09 km |

The zero-free-parameter hypothesis yields the same rms as the three-parameter fit.
The 2 km residual is the offset between the DB label point and the reference city
center, not a modeling error. Deviation between free K and `2e9/360` is +0.0255 %,
within 1σ. Best anchors: Toulouse 0.17 km · Bordeaux 0.28 km · Köln 0.37 km ·
Praha 0.47 km · Amsterdam 0.47 km · Zaragoza 0.47 km · Helsinki 0.66 km.

### 7.2 Independent verifications (none used in the fit)

| Block / tile | decoding | reality |
|---|---|---|
| Westernmost POI tile | lon −29.13…−28.57 · lat 38.44…39.00 | Faial/Pico, Azores ✅ |
| Southernmost POI tile | lon −18.38…−17.81 · lat 27.68…28.24 | El Hierro / S. La Palma ✅ |
| Northernmost POI tile w/ strings | lon −1.39…−0.82 · lat 59.95…60.52 | Shetland, Lerwick ✅ |
| Easternmost POI tile w/ strings | lon 18.4…19.0 | Ostrava (CZ) / Otranto (IT) ✅ |
| Canary POI cluster (5 groups) | −17.85/−17.22/−16.50/−15.50/−13.78 | La Palma·La Gomera·Tenerife·Gran Canaria·Fuerteventura+Lanzarote ✅ |
| bbox block `0x01` sector 6117309 | −5.92…−5.35 · 35.61…36.17 | Strait of Gibraltar ✅ |

POI tiles reaching `X = 920,223,744` (lon ≈ 135° E) are **empty cells of the global
quadtree** (CF=0, zero records, zero strings): structure, not coverage.

### 7.3 Quadtree grid

> **Status (2026-09-29, issue #20): ✅ layout of `0x07` records, `0x08` and `0x09`, and the
> lookup, on every block of DVDs 21708 and 21734** (`scripts/geo/check_spatial_index.py`,
> 0 failures on both). Layer parameters (RR firmware reader found, 2026-09-29): param 0 ✅
> on road layers, param 1 🟡, params 2–3 ❓ (not read by the RR code found).

Tile edges follow the quadtree of the `0x07` root square, not a fixed grid. On both DVDs
every tile side is the root side divided by `2^k` (k = 4…16, i.e. 100,663,296 down to
24,576 units), the tile is 1:1 or 2:1, and its south-west corner is a multiple of its own
width (x) and height (y) from the root corner: 128,690 / 128,690 tiles on 21708,
147,272 / 147,272 on 21734.

**Corrected:** the earlier rule "all tile boundaries are multiples of 98,304 units, origin
at `(0, 0)`" is false on the DVDs too. No tile has its corner on that grid (0 / 128,690 on
21708, 0 / 147,272 on 21734), and 2,837 (21708) and 3,887 (21734) tiles have a side that
is not a multiple of 98,304 (sides 24,576 and 49,152 exist). 98,304 = root side / 2^14 is
one tile size among thirteen (the short side of 17,676 tiles on 21708).

On the CD discs, no `0x06` tile has its edges on the 98,304 grid either (0/730 on CD-ID
2952, 0/1,652 on CD-ID 21594).

| disc | observed sides |
|---|---|
| CD-ID 21594 | powers of two, `2^17 … 2^21` |
| CD-ID 2952 | `46 · 2^16 / 2^k` (3,014,656 halving down) |

The 1:1 / 2:1 aspect ratio and the ×64 local scale (`max(LOCAL_X) = side/64 − 1`) hold on both. `find_bbox` (§7.4) relies on the 98,304 rule; it is superseded by the per-type offsets in §7.4 and the lookup below.

#### Spatial index: `0x07` → `0x08` → `0x09` → tiles

Every georeferenced tile sits in a quadtree whose root square is stored in `0x07`, and
the disc carries the index from a grid cell to its tiles. Library: `carin.parser.spatial`
(`tiles_at(vol, layer, lon, lat)`). Every row marked ✅ is a rule of
`scripts/geo/check_spatial_index.py` that holds on every block of both DVDs.

**`0x07` layer directory** (sector 3, DB-REL 34):

| Offset | Field | Status |
|---|---|---|
| `+0x14 + 28·i`, i = 0…11 | 12 records of 28 bytes, inside the service data (before S0 at `+0x174`) | ✅ |
| record `+0x00` | `u32 BLOCK_ID` of the layer's first `0x08` block; one record (i = 8) points at the `0x1B` TMC position index instead | ✅ |
| record `+0x04` | root square `4 × i32` (`x0, y0, x1, y1`); the same square for all 11 `0x08` records, all-zero for the `0x1B` one | ✅ |
| record `+0x14` | `u16` param 0: highest road class (`S4 +0x10 & 0x0F`) stored in the layer, for the road layers `0x00`–`0x03`; compared with a road class by the RR (`rpmod` `0x7490c`, `0x29da0`; `dbq` `0x8e98`) | ✅ roads · 🟡 other layers |
| record `+0x16` | `u16` param 1: lower scale bound; RR `dbq` uses the area layer whose `50 · param1 ≤` requested scale (`0x5478`, `0x5508`) | 🟡 (unit ❓, not read for road layers) |
| record `+0x18`, `+0x1A` | `u16` params 2, 3: not read by the RR code found (its reader copies only 24 bytes of the record) | ❓ |
| `+0x164` | 16-byte trailer after the 12 records: `99555696 00000000 a6a62a9a 07d60000` (21708), `99555596 …` (21734). RR reads bit fields of `+0x164` and `+0x16C`, the `u32` at `+0x168`, and at `+0x170` a `u16` in-block offset (`0x7D6`) of a string it copies (≤ 0x4C B; here `"\x01qxs"`) | layout of reads ✅ · meaning ❓ |

The root square is `3 · 2^29` wide on both DVDs, lon −75.00..214.91, lat −203.91..86.00;
it is the quadtree's frame, not the data's extent.

**`0x08` grid** (CF=0 on both DVDs):

| Offset | Field | Status |
|---|---|---|
| `+0x08` | one descriptor `{0x0010, count}` | ✅ |
| `+0x0C` | `u32` cell side, in CARIN units (divides the root side exactly) | ✅ |
| `+0x10` | S0: `count × u32` grid entries; the rest of the block is zero | ✅ |

A layer's grid has `N × N` cells, `N = root side / cell side`. The entries are split over the
run of **physically consecutive** `0x08` blocks that starts at the directory's `BLOCK_ID`
(each with its own descriptor and the same cell side); concatenated, they number exactly
`N²` (up to 171 blocks per layer on 21734). Entry `k` is cell `(x = k div N, y = k mod N)`
counted east and north from the root corner (column-major). An entry is 0 for an empty cell,
otherwise the `BLOCK_ID` of a `0x09` block; no `0x09` block appears in two entries. ✅

**`0x09` cell node** (CF=0 or CF=2: 11,537 + 1,811 on 21708, 27,885 + 2,024 on 21734;
never CF=1):

| Offset | Field | Status |
|---|---|---|
| `+0x08` | descriptor S0 = `{0x0014, q²}` | ✅ |
| `+0x0C` | descriptor S1 = `{(0x14 + 2·q² + 3) & ~3, n}` (S1 starts at the next 4-byte boundary) | ✅ |
| `+0x10` | `u32` item side `s`; it divides the cell side, `q = cell side / s` | ✅ |
| `+0x14` | S0: `q²` `u16` item pointers, column-major like `0x08`. A pointer is 0 (empty item) or the absolute in-block offset of an S1 entry | ✅ |
| S1 | `n` `u32` tile `BLOCK_ID`s, no duplicates, each pointed at by at least one item, in the order they are first met scanning S0 | ✅ |
| gap after S0, bytes after S1 | zero | ✅ |

The item side is the smallest side of (tile bbox ∩ cell) over the cell's tiles, and equals the
gcd of those sides and of their offsets from the cell corner: the coarsest grid that puts
every tile edge in the cell on an item boundary (13,348 / 13,348 blocks on 21708,
29,909 / 29,909 on 21734). The two `u16` at `+0x10` seen in samples (`0000 c000`,
`0001 8000`) are this one `u32` (49,152 and 98,304). ✅

**Items and tiles.** The items that point at a tile, collected over every `0x09` block of
its layer, are disjoint and their union is exactly the tile's bounding box (§7.4), both in
extent and in area: 128,690 / 128,690 tiles on 21708, 147,272 / 147,272 on 21734. On
21734, 3,753 `0x06` tiles are listed in more than one `0x09` block: they span several
layer-1 cells, and each cell's items cover the tile clipped to that cell (on 21708 every tile
is listed in exactly one `0x09`). Tiles of one layer therefore do
not overlap, and a point selects at most one tile per layer. ✅

**Lookup** (`carin.parser.spatial`): cell `(⌊(X−x0)/cell⌋, ⌊(Y−y0)/cell⌋)` → entry of the
concatenated `0x08` run → `0x09` → item `(⌊(X−cx0)/s⌋, ⌊(Y−cy0)/s⌋)` → pointer → S1. Queried
at the centre of every tile's bbox it returns that tile: 128,690 / 128,690 on 21708,
144,143 / 144,143 tiles reached from `0x07` on 21734. ✅

**Layers on the DVDs** (each layer holds exactly one tile type; parameters as stored):

| # | Parameters | Tiles | 21708: grid, non-empty cells, tiles | 21734: grid, non-empty cells, tiles |
|---|---|---|---|---|
| 0 | `(6, 0, 1, 0)` | `0x00` | 1024², 11,040, 91,756 | 1024², 11,291, 99,355 |
| 1 | `(0, 0, 0, 0)` | `0x06` | 512², 1,477, 2,688 | 1024², 15,488, 8,113 |
| 2 | `(0, 1200, 3000, 0)` | `0x01` | 16², 16, 2,710 | 16², 18, 2,830 |
| 3 | `(1, 120, 1200, 0)` | `0x02` | 32², 44, 3,580 | 32², 49, 3,709 |
| 4 | `(2, 1, 120, 0)` | `0x03` | 64², 134, 6,740 | 64², 145, 7,137 |
| 5 | `(0, 320, 1200, 0)` | `0x14` | 2², 2, 358 | 2², 2, 397 |
| 6 | `(2, 40, 120, 0)` | `0x15` | 64², 265, 4,511 | 64², 289, 4,885 |
| 7 | `(2, 1, 40, 0)` | `0x16` | 64², 265, 14,661 | 128², 1,040, 15,872 |
| 8 | `(0, 0, 0, 0)` | — (`0x1B` TMC index, `01-architecture.md` §4.7) | — | — |
| 9 | `(1, 120, 320, 0)` | `0x1C` | 32², 102, 1,461 | 32², 108, 1,605 |
| 10 | `(0, 1200, 3000, 0)` | `0x1D` | 2², 2, 172 | 2², 2, 187 |
| 11 | `(65535, 3000, 65535, 0)` | `0x1E` | 1, 1, 53 | 1, 1, 53 |

On 21708 the 117 `0x08` blocks, 13,348 `0x09` blocks and 128,690 tile blocks on the disc are
all reached from `0x07`.

**21734: an unreferenced grid.** 22 consecutive `0x08` blocks starting at `0x32F1E060` are in
no layer's run: a complete 512² grid (cell side 3,145,728, the same as layer 1 on 21708)
over the same root, pointing at 1,476 `0x09` blocks and through them at 3,129 `0x06` tiles.
It passes every rule above, but nothing points at it (`carindb-rs xref 0x32f1e060`: 0 hits
on the whole disc), and its 1,476 `0x09` blocks and 3,129 `0x06` tiles are in no grid that
`0x07` reaches. So on 21734 the lookup reaches 28,433 of 29,909 `0x09` blocks and 144,143 of
147,272 tiles; the rest are exactly those of this grid. Whether the firmware ever reads it ❓.

**Layer parameters: the RoadRunner reader** (2026-09-29, RR `V_2_RR_0101_BMWC01S`
`bsw2`; addresses are module offsets; Ghidra programs `RR_0101_bsw2_dbq.bin`,
`RR_0101_bsw2_rpmod.bin`, `RR_0101_bsw2_db_bh_read.bin`).

*How the firmware finds `0x07`* ✅. The superblock S0 (`+0x08` = offset `0x60`, `+0x0A` = count)
is a list of 8-byte records (`T[0x1E]` = 8); the first `u32` of record `n − 1` is a
`BLOCK_ID`. `db_bh_read` `0x17cc` (at `0x256c`) and `dbq` `0x2081c` (`n = 1`) read record 0 =
`0x304` and load that block. Records are then addressed as
`block + T[0x05] + T[0x1A] + k · T[0x18]` (RECORD_SIZE_TABLE, descriptor `+0x28`, `+0x52`,
`+0x4E`; 8 + 12 + 28·k = `0x14 + 28·k` on DB-REL 34) and the trailer as `k = 12`: the record
count is hard-coded, and `T[0x19]` = `0x160` = 12 × 28 + 16 covers records plus trailer
(`T[0x17]` = `0x174` = S0).

*Reader* ✅. `dbq` `0x21270` (twins: `rpmod` `0x65b98`, `dbpa` `0x1cf98`) maps a tile type to a
record — `0x00`→0, `0x06`→1, `0x01`→2, `0x02`→3, `0x03`→4, `0x14`→5, `0x15`→6, `0x16`→7,
`0x1C`→9, `0x1D`→10, `0x1E`→11 — and copies **24 bytes**: `BLOCK_ID`, root square, param 0,
param 1. `0x21074` reads record 8's `BLOCK_ID` (the `0x1B` index); `0x2af6c` / `0x2b92c` read
the grid (cell side at `0x08 +0x0C`, `N = (x1 − x0) / cell side`).

*Param 0* — observed in code ✅:
- `rpmod` `0x7490c` returns its low byte; when the record is missing it falls back to
  **6, 0, 1, 2 for types `0x00`, `0x01`, `0x02`, `0x03`** — the values stored on both DVDs.
- `rpmod` `0x50aa0` stores it per level (`gp[0x6650 + i]`); the route search `0x29da0`
  (`0x29fb8`, `0x2ab80`) moves an edge to level `i + 1` only if that level's value ≥ the edge's
  road class (edge `+0x18` = `S4 +0x10 & 0x0F`, written by `0x4e02c`).
- `dbq` `0x8e98` rejects a layer when `(s16) param0 <` the largest requested class (class
  bytes must be < 7, `0x8f58`); `0xFFFF` of `0x1E` reads as −1 there.

Meaning on the road layers ✅: the **highest road class stored in the layer**. On every
segment of every `0x00`–`0x03` tile of both DVDs (S4 record 32 B for `0x00`, 26 B = `T[0x09]`
for `0x01`–`0x03`), class ≤ param 0 and the maximum is reached: `0x00` 0…6, `0x03` 0…2,
`0x02` 0…1, `0x01` 0 only. On the other layers the firmware does the same comparison, but
what a "class" is for area tiles is ❓.

*Param 1* — observed in code ✅: `dbq` `0x5478` / `0x8e98` test `2 · scale ≥ 100 · param1`;
`0x5508` / `0x8f58` try `0x1E`, `0x1D`, `0x14`, `0x1C`, `0x15` in that fixed order and fall
back to `0x16` — the order of decreasing param 1 (3000, 1200, 320, 120, 40, 1) — so they pick
the coarsest area layer whose `50 · param1` does not exceed the requested scale. RPC handlers
`0x21940` / `0x219d4` return `50 · param1` (min/max, and per layer with param 0) for the six
area layers. Meaning 🟡: lower scale bound of the layer. The scale's unit is ❓ (request
`+0x2C`, a power of two in `0x8f58`), and no code reading param 1 for the road layers was found.

*Params 2, 3* ❓: never copied by the reader, and no other code addresses the records through
`T[0x18]` in the 17 `bsw2` modules or the 18 `navboot` application modules scanned (code that
hard-codes the offsets would not be caught). On the
data, param 2 of each layer equals param 1 of the next coarser one in both chains (roads
0 → 1 → 120 → 1200 → 3000; areas 1 → 40 → 120 → 320 → 1200 → 3000 → 65535): an upper bound, as
QGIS_VDO's `zoom_to` suggests, but not confirmed by firmware. Param 3 is 0 on every record.
The 24-byte copy also fits the 24-byte DB-REL 22 records.

**Relation to QGIS_VDO** (`lugovskovp/QGIS_VDO`, GPL-3.0, commit `91c516e`; read, not
copied). Confirmed by the rules above:

- `vdo/blocks/block_0x09.py` L14–16: `+0x08` list of items, `+0x0C` list of `BLADDR`s,
  `+0x10` `item_side` (u32). L125: an item pointer is an in-block offset to a u32 `BLADDR`.
- `block_0x09.py` L94–97, L135 and `block_0x08.py` L99–108, L146: index `y + x · qty_y`
  (column-major), in both block types.
- `block_0x09.py` L46–47: `qty = (max − origin) // item_side`, with origin/max the parent
  `0x08` cell; on the DVDs cells are square, so `qty_x = qty_y = cell side / item side`.
- `block_0x09.py` L109–123: cells with the same pointer merged into one tile (RLE on x and y).
  Stronger on the DVDs: they always form one full rectangle equal to the tile's bbox (except
  tiles clipped at a `0x08` cell edge, see above).
- `block_0x08.py` L33–34, L58: `+0x0C` `item_side` (u32) = our cell side.
- `block_0x07.py` L41, L44–53, L252–254: 12 records of `0x1C` bytes at `+0x14` on DB-REL 34
  (`BLADDR`, two `COORD`s, `value_a`, `zoom_from`, `zoom_to`).

Not in QGIS_VDO: its `block_0x08` reads the entries of one block (`block_0x08.py` L57, L113);
on the DVDs most grids span several consecutive `0x08` blocks. Its names `zoom_from`/`zoom_to`
are not evidence for the parameter meaning. The handoff `08-qgis-vdo-handoff.md` §3 summarises
these files; each point used here was checked against the files themselves.

**CD discs** (tested by a contributor, 2026-09-28; not re-checked here). On DB-REL 22 the
directory records are 24 bytes (`2 × u16` parameters). On CD-ID 21594
(CD-ID 21708 has the same eleven layers, with finer grids, and they reference every block of those types too):

| Layer parameters | Grid | Tiles | Referenced / on disc (CD-ID 21594) |
|---|---|---|---|
| `(6, 0, 1)` | 256² | `0x00` | 25,974 / 25,974 |
| `(0, 0, 0)` | 256² | `0x06` | 1,652 / 1,652 |
| `(2, 1, 120)` | 64² | `0x03` | 1,476 / 1,476 |
| `(1, 120, 1200)` | 16² | `0x02` | 426 / 426 |
| `(0, 1200, 3000)` | 8² | `0x01` | 247 / 247 |
| `(2, 1, 40)` | 64² | `0x16` | 1,996 / 1,996 |
| `(2, 40, 120)` | 32² | `0x15` | 599 / 599 |
| `(0, 320, 1200)` | 2² | `0x14` | 79 / 79 |
| `(1, 120, 320)` | 4² | `0x1C` | 164 / 164 |
| `(0, 1200, 3000)` | 1 | `0x1D` | 108 / 108 |
| `(65535, 3000, 65535)` | 1 | `0x1E` | 42 / 42 |

`0x19` is indexed through the `0x1B` record by a sorted position key instead
(`01-architecture.md` §4.7).

The number of `0x09` blocks equals the number of non-empty cells over all layers (1,153 on
CD-ID 21594; on 21708 13,348; on 21734 28,433 plus the 1,476 of the unreferenced grid).
`0x0E`, `0x0C` and `0x10` are not in the spatial index: `0x10` is reached
from `0x06`, and `0x0E` links to `0x00` tiles itself (`03-road-network.md` §6.3.1).

**The tile grid follows from the root square.** Every tile is a cell of that quadtree:
its side is the root side divided by a power of two and its corners are on that grid.

| Disc | Root square (lon, lat of `x0, y0`) | Root side | Tiles on the root grid (`0x06`) |
|---|---|---|---|
| CD-ID 2952 | −11.81°, 33.33° | 46 · 2^22 | 730 / 730 |
| CD-ID 21594 | −36.30°, −10.64° | 2^29 | 1,652 / 1,652 |
| CD-ID 21708 | −75.00°, −203.91° | 3 · 2^29 | 2,688 / 2,688 (all tiles: 128,690 / 128,690) |
| CD-ID 21734 | −75.00°, −203.91° | 3 · 2^29 | 11,242 / 11,242 (all tiles: 147,272 / 147,272) |

The root square is not the data's extent (on CD-ID 21708 it reaches −203.9° latitude); it
is only the quadtree's frame.

CD-ID 2952 (DB-REL 22) uses the same scheme with eight layers (no `0x1C`–`0x1E`), and its
`0x09` nodes reach every tile: all 22,594 `0x00`, 730 `0x06`, 900 `0x01`, 1,269 `0x02`,
2,255 `0x03` and all `0x14`–`0x16` blocks. It differs in one detail: an empty cell is not
0 in the grid but points to an empty `0x09` block (13,528 of its 17,057 `0x09` blocks,
most of the 11% of the disc that `0x09` takes up there).

### 7.4 Bounding box by block type

The bbox (`4 × int32` = `X_min, Y_min, X_max, Y_max`) immediately follows the
section descriptor, at a fixed offset per block type (table). On DVDs 21708 and 21734 the
offsets hold for every tile block of every type below: each bbox read there equals the union
of the `0x09` items that point at the tile (§7.3, `scripts/geo/check_spatial_index.py`).
`carin.parser.iso.find_bbox` (a scan for a box with sides multiple of 98,304) is superseded:
2,837 tiles on 21708 and 3,887 on 21734 break its side rule.

| Type | bbox offset | `find_bbox` coverage (old sample) |
|---|---|---|
| `0x00`–`0x03` | `0x44` | 60/60 |
| `0x06` | `0x10` | 60/60 |
| `0x14`, `0x15`, `0x16`, `0x1C` | `0x20` | 60/60 |
| `0x1D`, `0x1E` | `0x20` | 43/60, 20/39 |
| `0x0C`, `0x0E`, `0x10`, `0x0F`, `0x11`, `0x17`, `0x19` | — | **no bbox**: indirectly georeferenced (`0x0E`: each S2 record names a `0x00` tile, see `03-road-network.md` §6.3.1) |

> **Note for CF=1 work:** the bbox at `0x44` sits inside the plaintext prologue, so
> it is readable on `CF=1` blocks *without decompressing* — the basis of the
> cross-edition method in [`05-failed-attempts.md`](05-failed-attempts.md) §9.10.
> Checked on every CF=1 tile of both DVDs (`check_spatial_index.py --cf1-rust`): the bbox
> decoded by `carindb-rs` equals the prologue bytes for all `0x00` (86,107 / 91,651) and
> `0x14`–`0x16`, `0x1C`–`0x1E` blocks (9,763 / 14,225) on 21708 / 21734; both decoders
> copy the prologue (`T[0x0B]` = 0x74, `T[0x3D]` = 0x34 bytes) verbatim.

#### 7.4.1 Type `0x00` frames on CD-era discs

Two single-file `carindb` CD discs store the `0x00` frame at `0x44` differently
from the DVD layout above, and neither matches the 98,304 grid, so
`find_bbox` finds nothing on them:

| disc | fields at `0x44` | tile sides |
|---|---|---|
| DB-REL 34 (CD-ID 21594) | `X_min, Y_min, X_max, Y_max` (full box) | powers of two (2^19, 2^21 …), 1:1 or 2:1 |
| DB-REL 22 (CD-ID 2952) | `Y_min, X_max, Y_max` — **east** edge, latitude extent only | 1:1 or 2:1; the X extent is not stored |

On the three-field form the X extent is either equal to the Y extent or twice
it, and is resolved from the geometry (it must contain every section 7 point);
the west edge is `X_max − width`. Reading that field as the west edge shifts
every tile east by its own width, which is why tiles of different sizes then
fail to join. `carin.parser.geometry.tile_frame` handles both forms.

### 7.5 Python struct

```python
CARIN_UNITS_PER_TURN = 2_000_000_000
K = CARIN_UNITS_PER_TURN / 360.0      # 5_555_555.5555...
LON_ORIGIN, LAT_ORIGIN = -30.0, 0.0
QUADTREE_UNIT = 98_304                # find_bbox only; not a grid rule (§7.3)

BBOX_FMT = ">4i"                      # X_min, Y_min, X_max, Y_max

def to_wgs84(x, y):
    return (x / K + LON_ORIGIN, y / K + LAT_ORIGIN)

def to_carin(lon, lat):
    return (round((lon - LON_ORIGIN) * K), round((lat - LAT_ORIGIN) * K))
```

---

## 8. Georeferenced Record Formats

### 8.1 Type `0x06` — POI Record, **`T[0x32]` bytes** (28 on DB-REL 34, 20 on DB-REL 22)

```
 off  size  field
 0x00   4   BLOCK_ID of the 0x10 block (POI parcel, §8.1.1) holding this POI's details
 0x04   2   byte offset, within that 0x10 block, of this POI's S0 index record (§8.1.1)
 0x06   2   LOCAL_X    position in tile, step 64        <- sorted ascending
 0x08   2   LOCAL_Y    position in tile, step 64
 0x0A   2   CATEGORY   (12 petrol, 21 hotels, 37 landmarks, 48 towns, …; 01-architecture.md §4.4.1)
 0x0C   2   BRAND      offset of the POI's brand in this block's name blob, 0 = no brand
 0x0E   2   0, or 1 on a few ports and airports (187 records on CD-ID 2952, 240 on CD-ID 21594)
 0x10   4   POI_ID     the 0x10 detail record's +0x1C (§8.1.1); read before as a "brand reference"
 0x14   8   0          DB-REL 34 only: the 20-byte form (DB-REL 22) ends at 0x14
```

Checked on every record: the brand matches the `0x10` detail's brand (64,433 / 64,433 on CD-ID
2952, 466,310 / 466,310 on CD-ID 21594), and so does the POI ID. Every block is sorted by
`LOCAL_X` (730 / 730, 1,652 / 1,652).

**Exact local scale = 64:**

```
X_abs = X_min + LOCAL_X * 64
Y_abs = Y_min + LOCAL_Y * 64
```

Verified across 2,395 blocks: for each tile size, `max(LOCAL_X) = (X_max−X_min)/64 − 1`.

| tile side (units) | 98304 | 196608 | 393216 | 786432 | 1572864 | 3145728 |
|---|---|---|---|---|---|---|
| measured `max(LOCAL_X)` | 1535 | 3071 | 6143 | 12287 | 24575 | 49151 |
| expected `side/64 − 1` | 1535 | 3071 | 6143 | 12287 | 24575 | 49151 |

POI resolution: 64 units = 1.15e−5° ≈ **1.2 m**. Name blob (Latin-1, `\0`-terminated)
follows the records: the brands used in the block (`BRAND`), **173 distinct names across the
whole DB**, all chains (banks, fuels, hotels). **2,048,403 POIs** extracted.

**Record size is `T[0x32]`, not a constant.** On CD-ID 2952 (DB-REL 22) the record is
**20 bytes**: the same fields up to `POI_ID`, without the trailing 8 zero bytes of the
28-byte form. Of the five `RECORD_SIZE_TABLE`
candidates for 28 bytes listed in `01-architecture.md` (`0x04`, `0x18`, `0x32`,
`0x43`, `0x4e`), `T[0x32]` is the only one that equals 20 on that disc (28 on
CD-ID 21594, DB-REL 34).

Every `0x06` record points at exactly one POI in a `0x10` block, and its tile
position equals that POI's stored absolute coordinate (§8.1.1) to the unit:

| disc | `0x06` blocks | records | tile position == 0x10 coordinate |
|---|---|---|---|
| CD-ID 2952 (DB-REL 22) | 730 | 64,433 | 64,433 |
| CD-ID 21594 (DB-REL 34) | 1,652 | 466,310 | 466,310 |

The `0x06` blocks are therefore a **spatial index over the `0x10` POI parcels**:
finding the POIs near a position is a bbox lookup plus one read per tile, with no
geometry involved.

A branded POI is stored twice in `0x10`, in a category copy and a brand copy (`01-architecture.md`
§4.4.2). On CD-ID 2952 the `0x06` record points at the brand copy for every branded POI
(11,643 / 11,643) and at the category copy for the rest; on CD-ID 21594 it points at the
category copy for all of them.

On a CNI1 (CD-ID 2952), with every `0x06` block's record count set to 0 (and the cities' POI
roots cut, §4.4.2 of `01-architecture.md`) the unit runs normally but draws no POI icons, and its
POI category menus come up empty. A block rewritten with our own records (sorted by `LOCAL_X`,
brands in its name blob) draws and lists them.

#### 8.1.1 Type `0x10` — POI parcel (name, address, phone, absolute position)

All `0x10` blocks on both CD discs are CF=0. The section descriptor at `0x08` has the
shape `[(o0, n0), (o1, n1), (0,0), (0,0), (o4, n4), (0,0)]`; `o0` is 40 on DB-REL 22
and 48 on DB-REL 34, so read it from the descriptor. On DB-REL 22 the header ends with two
`u32 BLOCK_ID`s at `+0x20` / `+0x24`: the next and the previous `0x10` block (620 / 620 chain
back). Measured over CD-ID 2952 (92,774 detail records) unless noted. S4 holds one
8-byte road link per detail record: `u32 BLOCK_ID` of a `0x00` tile, `u16` offset of the
segment record (in the decoded tile if it is packed), `u16` 0 or 1 (unknown; perhaps the side
of the road). On CD-ID 2952 the linked segment's name is the detail's street (445 / 445 sampled).
The strings follow S4. **Every string pointer below is a
plain byte offset from the start of the block** (header included) to a Latin-1,
`\0`-terminated string; `0` means absent.

S0 — `n0` index records, 8 bytes:

```
 off  size  field
 0x00   2   NAME_PTR
 0x02   2   TYPE          (2 in 94% of records on DB-REL 22, >99% on DB-REL 34)
 0x04   2   LOCALITY_PTR  or 0; shown after the post-town initial ("S.-LOCALITY")
 0x06   2   DETAIL_PTR    byte offset of an S1 record
```

`n0 >= n1`: several index records can share one detail record (alternate names).

S1 — `n1` detail records, 40 bytes (`T[0x2f]`; the other candidate, `T[0x51]`, is 28
on DB-REL 22):

```
 off  size  field
 0x00   4   X             absolute, same frame as §7
 0x04   4   Y
 0x08   2   LINK_PTR      byte offset of an S4 road link (the record's own in 77,711 / 92,774)
 0x0A   2   1             (92,305 / 92,774 on CD-ID 2952)
 0x0C   2   BRAND_PTR     or 0
 0x0E   2   STREET_PTR
 0x10   2   CITY_PTR
 0x12   2   COUNTY_PTR
 0x14   2   COUNTRY_PTR   (`england`, `scotland`, `wales`, `france`, …)
 0x16   4   0             (92,308 / 92,774)
 0x1A   2   HOUSE_NO_PTR
 0x1C   4   POI_ID        u16 prefix (0x0113, 0x0114, 0x0115, … on CD-ID 2952) + u16 serial;
                          the same in every copy of the POI and in its 0x06 records
 0x20   2   PHONE_PTR
 0x22   2   POSTCODE_PTR  (outward code + first inward digit, e.g. "sw7 2"; 0 on DB-REL 22)
 0x24   4   0             (all)
```

Measured over every `0x10` block:

| | CD-ID 2952 (DB-REL 22) | CD-ID 21594 (DB-REL 34) |
|---|---|---|
| blocks / S0 records | 620 / 119,006 | 4,787 / 844,749 |
| `DETAIL_PTR` lands on an S1 record boundary | 119,006 | 844,749 |
| `NAME_PTR` resolves to a string | 117,920 | 840,706 |
| (X, Y) inside Europe | 119,006 | 844,749 |
| `STREET_PTR` non-zero / resolves | 92,144 / 92,142 | 781,916 / 781,898 |
| `PHONE_PTR` non-zero / resolves | 33,992 / 33,992 | 688,901 / 688,901 |
| `POSTCODE_PTR` non-zero / resolves | 0 | 764,848 / 764,848 |

Example (CD-ID 21594, block at 2048-byte sector 54542, S0 record at `0x480`):
`royal albert hall` → street `kensington road`, phone `+442075898212`, postcode
`sw7 2`, X/Y → **51.50153 N, 0.17716 W**. The same POI is repeated in several `0x10`
blocks: a branded POI has a category copy and a brand copy (`01-architecture.md` §4.4.2).

On a CNI1 (CD-ID 2952) the POI lists show the brand in front of the name. Moving a POI (detail
X/Y and its `0x06` record) or pointing its road link at another road keeps it routable; renaming
it does too, as long as the name stays in order in its letter's `0x11` leaf
(`01-architecture.md` §4.4.2).

Positions agree with OpenStreetMap to within tens of metres for distinctive names
(median 52 m over the 28 name matches in one CD-ID 21594 parcel, a figure that
still includes common names such as chain pubs matched to an unrelated venue). CD-ID 2952 is
more coarsely geocoded: distinct POIs at one address can share a coordinate.

### 8.2 Type `0x16` — Feature Record, **20 bytes**

Layer of named features (islands, lakes, rivers, fjords, city labels). This is the
**source of the geographic anchors** used to solve §7.

```
 off  size  field
 0x00   2   NAME_PTR   offset of the name within the block itself, Latin-1, \0-terminated
 0x02   2   UNKNOWN (internal pointer)
 0x04   4   UNKNOWN
 0x08   4   X          absolute int32
 0x0C   4   Y          absolute int32
 0x10   2   UNKNOWN
 0x12   2   offset of another section of the block
```

Records reside in the section indicated by **entry 1** of the descriptor
(`struct.unpack_from(">HH", payload, 12)`), with a sentinel record at the tail.

```python
FEATURE_REC = ">HHIiiHH"     # 20 bytes
```

Verified example (sector 6326923, Göteborg bbox):
`landvettersjön` → X=234411946 Y=320448230 → **12.196° E · 57.681° N**
(actual Landvettersjön: 12.32 E · 57.68 N).

The same 20-byte layout with absolute coordinates applies to types `0x14`, `0x1C`,
`0x1D`, `0x1E` (labels of seas, regions, major cities).

### 8.3 Type `0x00` — Road Segments (section 4)

Street-level geometry. Field offsets are the ones `decode_type00` writes
(`carin/parser/cf1/decoder_00.py`, `dec_b`); record size and the tail offset
come from the `RECORD_SIZE_TABLE`.

```
section 4, record T[0x08] (30 B on CD-ID 2952, 32 B on CD-ID 21594)
 +0x00      start node   -> section 5 (in-tile node) or section 6 (tile-edge node)
 +0x02      end node        same
 +0x04      first shape point -> section 7; the segment runs to the next
            record's pointer (or the end of section 7)
 +0x10      display class byte
 +T[0x09]   -> section 2 record (24 on CD-ID 2952, 26 on CD-ID 21594)

section 2, record T[0x40]:  +0x00  in-block offset of the NUL-terminated name
sections 5 / 6 / 7:         +0x00  u16 x, +0x02 u16 y (tile-local)
```

Local coordinates are in units of 64 CARIN units from the tile's south-west
corner (§7.4.1). Section 6 nodes carry coordinates in *this* tile's frame and
sit on its edge: they are the cross-tile joins, so both sections 5 and 6 must
be resolved for segment endpoints, or boundary roads stop short of the edge.

`carin.parser.geometry.road_segments` returns each segment as WGS84 points with
its name and display class; `scripts/geo/extract_00_geometry.py` exports them
as GeoJSON by sector or by WGS84 window. On CD-ID 21594, 88.7% of
OpenStreetMap road vertices in a test area have a decoded segment within 40 m.

### 8.4 Area and Line Categories — Types `0x14`–`0x16`, `0x1C`–`0x1E`, Section 0

The background layer (sea, lakes, forest, built-up areas, rivers, railways) lives
in the scale-layer block types, not in the street-level `0x00` tiles. Section 0
of a decoded block is a category list:

```
section 0, record T[0x3B] (4 bytes on both CD discs checked):
 +0x00  u8   category code (7 bits used)
 +0x01  u8   draw flag (0 = polygon, 1 = polyline)
 +0x02  u16  offset of the category's first record in section 1 or section 2
count + 1 records; the last is a terminator that supplies the end bound
```

A category owns the records from its pointer up to the next category's pointer.
**Decide polygon vs polyline by which section the pointer lands in** (section 1:
areas, section 2: lines), not by the draw flag: the terminator carries
`draw = 0` while pointing at the end of section 2. Treating it as an area makes
the last area category — usually water — compute an out-of-range end and
disappear, which looks like "the format only stores open sea".

Codes, checked on two CD discs (CD-ID 2952 and CD-ID 21594). Section 0 records decoded by
`decode_type14_16` are identical to an independent decoder's on 375/375 sampled
packed blocks.

On the DVDs (CD-ID 21708, 21734) the rule above holds on every block of the six
types, plain, zlib or packed: every S0 offset lands on an S1 or S2 record boundary
and the offsets never decrease (`scripts/routing/oracle_14_16.py`, check `s0_ptr`,
46,215 blocks; decoder: `04-cf1-codec.md` §9.11.11). The same category codes occur
in packed and plain blocks of each type (`scripts/routing/layer_stats.py`). Full
record layout: `01-architecture.md`, scale layers.

| code | meaning | evidence |
|---|---|---|
| `0x00` | land | background fill under islands and coast |
| `0x01` | water / sea | renders the coastline, sea lochs and estuaries of both discs' coverage; over tiles wholly at sea vs wholly inland (CD-ID 21594): 3.51 deg² sea, 0.00 deg² land |
| `0x03` | forest / green space | national parks, large forests |
| `0x05` | built-up area | matches urban geography; land-only |
| `0x06` | industrial | sparse, next to built-up areas; land-only |
| `0x08` | island | Hebrides, Orkney, Shetland |
| `0x61` | canal | line |
| `0x62` | river | line, dendritic drainage pattern |
| `0x65` | major river | line; road-proximity 1.05× a random-shift null (not a road) |
| `0x66` | railway | line; road-proximity 1.29× null |
| `0x67` | border | line |
| `0x68`–`0x6A` | coarse-scale road classes (strongly indicated) | lines within 40 m of decoded `0x00` roads at 1.69×, 2.05×, 1.98× a random-shift null; national renders form a three-tier hierarchy |

`0x02` (sea/ocean), `0x04` (national park), `0x07` (airport), `0x09` (amusement),
`0x0A` (golf), `0x0F` (sports) follow the QGIS_VDO naming and were not
independently verified here.

**Scale layers are alternatives, not layers to composite.** `0x14`, `0x15`,
`0x16`, `0x1C`, `0x1D`, `0x1E` are the same ground generalised for different
zooms. Render one layer for a view (the finest that covers it), as the unit
does. Compositing lets a coarse layer's generalised polygon show wherever the
fine layer draws nothing: with all layers painted coarsest-first, 364 water
polygons on CD-ID 21594 cover street-level land tiles, against 26 (all
ordinary coastal tiles) when only `0x16` is drawn. Sorting by tile span is not a
substitute for layer order — a coarse layer's tile can be smaller than a fine
layer's.

Some tiles store the same polygon two or three times, in distinct consecutive
vertex ranges. This is in the data, not a decode error.
