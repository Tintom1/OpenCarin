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

All tile boundaries are exact multiples of **98,304 units** (= 3·2^15 = 0.0176896°),
origin at `(0, 0)` = 30° W on the equator. Observed sides are `98304 · 2^k` for
k = 0…5, aspect ratios 1:1, 1:2, or 2:1.

**This grid is DVD-specific.** On the CD discs, no `0x06` tile has its edges on the 98,304 grid (0/730 on CD-ID 2952, 0/1,652 on CD-ID 21594). Their tiles also aren't aligned to a multiple of their own side.

| disc | observed sides |
|---|---|
| CD-ID 21594 | powers of two, `2^17 … 2^21` |
| CD-ID 2952 | `46 · 2^16 / 2^k` (3,014,656 halving down) |

The 1:1 / 2:1 aspect ratio and the ×64 local scale (`max(LOCAL_X) = side/64 − 1`) hold on both. `find_bbox` below relies on the 98,304 rule, so it does not find the bbox on these discs; use the per-type offsets in §7.4 directly.

### 7.4 Bounding box by block type

The bbox (`4 × int32` = `X_min, Y_min, X_max, Y_max`) immediately follows the
section descriptor. The number of descriptor entries varies per block, so locate
the bbox with a grid constraint (`carin.parser.iso.find_bbox`): sides multiple of
98,304 and aspect ratio 1:1 / 1:2 / 2:1.

| Type | bbox offset | locator coverage |
|---|---|---|
| `0x00`–`0x03` | `0x44` | 60/60 |
| `0x06` | `0x10` | 60/60 |
| `0x14`, `0x15`, `0x16`, `0x1C` | `0x20` | 60/60 |
| `0x1D`, `0x1E` | `0x20` | 43/60, 20/39 |
| `0x0C`, `0x0E`, `0x10`, `0x0F`, `0x11`, `0x17`, `0x19` | — | **no bbox**: indirectly georeferenced |

> **Note for CF=1 work:** the bbox at `0x44` sits inside the plaintext prologue, so
> it is readable on `CF=1` blocks *without decompressing* — the basis of the
> cross-edition method in [`05-failed-attempts.md`](05-failed-attempts.md) §9.10.

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
QUADTREE_UNIT = 98_304

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
 0x0A   2   CATEGORY   (0x0016, 0x0017, 0x001F, 0x0023, 0x0030, …)
 0x0C   4   0x00000000
 0x10   4   BRAND_REF  global reference to chain (recurring across blocks)
 0x14   4   0x00000000
 0x18   4   0x00000000
```

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
follows the records: **173 distinct names across the whole DB**, all brands/chains
(banks, fuels, hotels) — no toponyms, no airports. **2,048,403 POIs** extracted.

**Record size is `T[0x32]`, not a constant.** On CD-ID 2952 (DB-REL 22) the record is
**20 bytes**: the same fields up to `CATEGORY`, then `u32 0`, `u32 BRAND_REF`, with
the trailing 8 bytes of the 28-byte form absent. Of the five `RECORD_SIZE_TABLE`
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

#### 8.1.1 Type `0x10` — POI parcel (name, address, phone, absolute position)

All `0x10` blocks on both CD discs are CF=0. The section descriptor at `0x08` has the
shape `[(o0, n0), (o1, n1), (0,0), (0,0), (o4, n4), (0,0)]`; `o0` is 40 on DB-REL 22
and 48 on DB-REL 34, so read it from the descriptor. **Every string pointer below is a
plain byte offset from the start of the block** (header included) to a Latin-1,
`\0`-terminated string; `0` means absent.

S0 — `n0` index records, 8 bytes:

```
 off  size  field
 0x00   2   NAME_PTR
 0x02   2   TYPE          (2 in 94% of records on DB-REL 22, >99% on DB-REL 34)
 0x04   2   LOCALITY_PTR  or 0
 0x06   2   DETAIL_PTR    byte offset of an S1 record
```

`n0 >= n1`: several index records can share one detail record (alternate names).

S1 — `n1` detail records, 40 bytes (`T[0x2f]`; the other candidate, `T[0x51]`, is 28
on DB-REL 22):

```
 off  size  field
 0x00   4   X             absolute, same frame as §7
 0x04   4   Y
 0x0E   2   STREET_PTR
 0x1A   2   HOUSE_NO_PTR
 0x20   2   PHONE_PTR
 0x22   2   POSTCODE_PTR  (outward code + first inward digit, e.g. "sw7 2"; 0 on DB-REL 22)
 other      UNKNOWN
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
blocks.

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
