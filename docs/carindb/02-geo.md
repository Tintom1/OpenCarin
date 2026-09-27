# Part 2 — Coordinate System & Georeferenced Records

> **Status: ✅ RESOLVED / VERIFIED.** The coordinate system is fully solved
> (0 free parameters, 2.0 km rms across 38 anchors, independently cross-checked).
> POI (`0x06`) and feature (`0x16`) record layouts are byte-verified.
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

Both grids, and the DVD's, come from the quadtree root stored in `0x07`; see below.

#### Spatial index: `0x07` → `0x08` → `0x09` → tiles (2026-09-28)

Every georeferenced tile sits in a quadtree whose root square is stored in `0x07`, and
the disc carries the index from a grid cell to its tiles:

- **`0x07` layer directory.** One record per map layer: `u32 BLOCK_ID` of the layer's
  first `0x08` grid block, the root square as `4 × i32` (`x0, y0, x1, y1`), then the
  layer's parameters (DB-REL 34: 4 × u16, record 28 B; DB-REL 22: 2 × u16, record 24 B).
  Parameters 1 and 2 look like the display-scale range the layer is drawn at.
- **`0x08` grid.** Section 0 is `4^k` `u32` entries, one per cell of a `2^k × 2^k` grid over
  the root square, split over consecutive `0x08` blocks (4,092 entries per 8-sector
  block). An entry is 0 for an empty cell, otherwise the `BLOCK_ID` of that cell's `0x09`.
- **`0x09` cell node.** Lists the `BLOCK_ID`s of the tiles of that layer in that cell
  (from a few samples: section 0 holds small records pointing into section 1, and section 1
  holds the `u32 BLOCK_ID`s).

Each layer holds one block type. On CD-ID 21594 (CD-ID 21708 has the same eleven layers, with finer grids, and they reference every block of those types too):

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

The number of `0x09` blocks equals the number of non-empty cells over all layers (1,153 on
CD-ID 21594). `0x0E`, `0x0C` and `0x10` are not in the spatial index: `0x10` is reached
from `0x06`, and `0x0E` links to `0x00` tiles itself (`03-road-network.md` §6.3.1).

**The tile grid follows from the root square.** Every tile is a cell of that quadtree:
its side is the root side divided by a power of two and its corners are on that grid.

| Disc | Root square (lon, lat of `x0, y0`) | Root side | Tiles on the root grid (`0x06`) |
|---|---|---|---|
| CD-ID 2952 | −11.81°, 33.33° | 46 · 2^22 | 730 / 730 |
| CD-ID 21594 | −36.30°, −10.64° | 2^29 | 1,652 / 1,652 |
| CD-ID 21708 | −75.00°, −203.91° | 3 · 2^29 | the 98,304-unit grid below is `3 · 2^29 / 2^14` |

The root square is not the data's extent (on CD-ID 21708 it reaches −203.9° latitude); it
is only the quadtree's frame. On CD-ID 2952 every `0x08` entry points to an empty `0x09`
(17,057 blocks with no records, 11% of that disc), so DB-REL 22 finds its tiles some
other way; how is not known.

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
| `0x0C`, `0x0E`, `0x10`, `0x0F`, `0x11`, `0x17`, `0x19` | — | **no bbox**: indirectly georeferenced (`0x0E`: each S2 record names a `0x00` tile, see `03-road-network.md` §6.3.1) |

> **Note for CF=1 work:** the bbox at `0x44` sits inside the plaintext prologue, so
> it is readable on `CF=1` blocks *without decompressing* — the basis of the
> cross-edition method in [`05-failed-attempts.md`](05-failed-attempts.md) §9.10.

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

### 8.1 Type `0x06` — POI Record, **28 bytes** (not 24)

```
 off  size  field
 0x00   4   BLOCK_ID of the 0x10 block (street/name parcel) containing the POI
 0x04   2   UNKNOWN (multiple of 8)
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
