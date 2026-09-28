# Part 3 — Road Network Tables (Parcels)

> **Status: ✅ VERIFIED (STEP 2 & 3 complete, 2026-09-19).** Block/section structure
> AND field semantics for `0x0E` are fully verified from firmware traces (S0 `A`/`C` and
> the S2 fields were reinterpreted from disc data on 2026-09-27: §6.3.1). Spatial
> lookup via `find_parcel(vol, X, Y)` oracle 10/10 PASS. `0x0D`/`0x0F`/`0x11` = TEXT
> address-lookup index (not spatial). Type `0x00` field semantics are now KNOWN (map drawing). Types `0x01`–`0x03` are assumed identical.
>
> Source: `../CARINDB_BLUEPRINT_EN.md` §6. Related: CF=1 decoding for these types →
> [`04-cf1-codec.md`](04-cf1-codec.md); open goals → [`06-objectives-roadmap.md`](06-objectives-roadmap.md).

---

## 6. Node / Edge / Parcel

CARINdb **has no** global Node/Edge/Name tables at fixed offsets. The network is
partitioned into *parcels* (blocks `0x0C`, `0x0E`, `0x10`, `0x0F`, `0x11`), each
with its own local sections and **16-bit internal pointers within the block**.

### 6.1 Descriptor arity and record sizes (empirically derived)

Sampled 40 blocks per type; `~n` = average approximate size (variable/padded section).

| Type | N sections | S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S9 | S10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `0x00` | 5–8 (up to 16) | ~10 | 10 | ~10 | ~4 | ~32 | 8 | 16 | ~6 | | 8 | |
| `0x01` | 15–16 | 10 | 10 | 10 | ~4 | ~26 | 8 | 16 | 6 | 4 | 8 | 8 |
| `0x02` | 15–16 | 10 | 10 | 10 | ~4 | ~26 | 8 | 16 | 6 | 4 | 8 | 8 |
| `0x03` | 15–16 | 10 | 10 | 10 | ~4 | ~26 | 8 | 16 | 6 | 4 | 8 | 8 |
| `0x04` | 1 | ~10 | | | | | | | | | | |
| `0x06` | 6 (sometimes 2) | 24 | | | | | | | | | | |
| `0x08` | 2 | var | | | | | | | | | | |
| `0x09` | 3 | 4 | 488 | | | | | | | | | |
| `0x0A` | 10 | 8 | 56 | | 12 | | | | | | | |
| `0x0C` | 10 | 8 | 24 | | ~12 | | ~47 | | | var | var | |
| `0x0E` | 10 | 8 | 6 | var | | | | | | var | var | |
| `0x10` | 10 | 8 | ~8 | | | ~25 | | | | var | var | |
| `0x19` | 1 | ~49 | | | | | | | | | | |
| `0x1B` | 1 | 500 | | | | | | | | | | |

> `0x11`, `0x14`, `0x15`, `0x16`, `0x1C`, `0x1D`, `0x1E` are not in the table:
> most of their blocks use `COMPRESSION_FLAG = 1` (decode → [`04-cf1-codec.md`](04-cf1-codec.md)).

### 6.2 Types `0x00`–`0x03`: same schema (15–16 sections)

They occupy **2.9 GB of 3.3 GB** of the DB. Identical schema across `0x00`–`0x03`
with separate blocks per region (§1.2) suggests **different levels of detail of the
same structure** (`0x00` = finest, 91,756 blocks; `0x01` = coarser, 2,710 blocks).
Recurring 10/8/16/6/4-byte sections are compatible with node/edge/geometry lists,
but **field semantics are NOT verified** and must not be assumed.

### 6.3 Type `0x0E` (74,247 blocks) — main parcel

```
+0x08 SECTION_DESCRIPTOR[3 used of 10] e.g. {0x0030, 1169}, {0x24B8, 531}, {0x312C, 772}
+0x14 UNKNOWN_PADDING (20 bytes, zeros)
+0x28 SERVICE_DATA (8 bytes)
+0x30 SECTION_0: 8-byte records  ">HBBHH"
      A(u16)  FLAGS(u8)  B(u8)  C(u16)  D(u16)
```
Verified on sample:
* `D` is a **pointer to SECTION_1**, advances in steps of 6 (= S1 record size).
* `A` (0x798C, 0x799A, 0x79B1, …) is **not** a pointer into SECTION_2: it points to the
  record's **street name**, a NUL-terminated Latin-1 string in the text that follows
  SECTION_2 (it is monotonic because records are alphabetical). See §6.3.1,
  "`0x0E` is the street-name directory".
* **Name metadata, from disc data (2026-09-28)**: `FLAGS` and `B` describe the *name*, not
  the road. Checked on CD-ID 21594 (6,873 S0 records in 25 blocks, each compared with the
  names of the road segments its S2 records link to) and CD-ID 21708 (300 `CF=2` blocks):

  | Field | Value | Meaning | Evidence (CD-ID 21594) |
  |---|---|---|---|
  | `FLAGS` bits 0–1 | 0 | the linked segments' own name | 4,707 / 4,707 exact match |
  | | 1 | an alternative name for the road (e.g. `muckross road` → segment `n71`, `jellicoe court` → `atlantic wharf`) | 368 + 230, all differ from the segment name |
  | | 2 | the name in a second language (e.g. `heol y groes` → `cross street`, `an baile beag` → `ballybeg`) | 106 + 127, all differ |
  | `FLAGS` bit 4 | 1 | a word-reordered form of the name, for search (`east rathcahill` → `rathcahill east`) | 1,335 / 1,335 reordered |
  | `B` | code | the **language** of the name | see below |

  `B` codes seen on CD-ID 21708: 1 Dutch, 2 English, 3 French, 4 German, 5 Italian,
  6 Spanish, 7 Swedish, 10 Danish, 11 Catalan, 15 Portuguese, 19 Czech, 21 Russian
  (transliterated), 255 other (Welsh, Irish, Ukrainian, Basque, Galician). On CD-ID 21594,
  English names carry 2 and Welsh/Irish names 255. In `CF=1` blocks `B` is read as 3 bits;
  on the discs tested, packed blocks only carry codes 1–6.

  This supersedes the "access category" reading of bits 0–1 and the "functional class"
  reading of `B` below; the firmware notes that follow found no routing use of `FLAGS`,
  which is consistent with it being name metadata.
* `FLAGS` ∈ `{0x00,0x01,0x02,0x10,0x11,0x12}` (3 active bits: lo=bits[1:0] via `getbits(2)`, hi=bit4 via `getbits(1)<<4`).
  Global distribution across 563 CF=1 blocks (218 k records): 0x00=67.1 %, 0x10=26.4 %, 0x01=4.5 %, 0x11=1.3 %, 0x02=0.6 %, 0x12=0.1 %.
  **Hypothesis "bit4 = one-way": FALSIFIED by full firmware static analysis (2026-09-20).**
  - bit4 = 0 → bidirectional; bit4 = 1 → one-way: **NOT CONFIRMED**. Spatial correlation with
    ZTL/city-centre roads is consistent with "high-restriction category" but does not prove direction.
  - bits[1:0] = **access category**: 0x0=normal (93.5 %), 0x1=restricted/ramp (5.8 %),
    0x2=non-motorised or ferry (0.7 %, correlated 94 % with B=3). Still unconfirmed but plausible.
  **Firmware evidence — complete static analysis of rpmod (2026-09-20):**
  - `can_traverse` (`rpmod+$4360`): reads `block[D+0x10]` / `block[D+0x11]`, always `0x00` for
    `0x0E` CF=1 blocks → always returns 1 (traversable). FLAGS NOT READ.
  - `rpmod+$6eae` (cost function for `0x0E`): calls `jsr -$7240(a6)` to retrieve an attribute list,
    searches for `element[1]==5`, returns `element[2] × 0x3C00`. FLAGS NOT READ. (The earlier note
    "arc value × 0x3C00" incorrectly attributed the multiplied value to FLAGS; it is `element[2]`
    from an OS-9 attribute list — identity of `element` TBD.)
  - `rpmod+$66de` (neighbour expansion): two `btst #4` tests found ($698a, $6a5a), but both operate
    on NODE DESCRIPTOR fields — one on output of `jsr -$7258(a6)` (OS-9 restriction-table query),
    one on a propagated routing-state bit. No `btst #4` on the S0 FLAGS byte (offset +2) found
    anywhere in rpmod.asm.
  **Result: FLAGS bit4 has NO confirmed routing effect in the analyzed firmware.**
  Direction enforcement (one-way restriction) is NOT implemented via FLAGS bit4. It likely comes
  from OS-9 restriction/turn tables queried via `jsr -$7258(a6)` / `jsr -$724c(a6)`, not from the
  arc FLAGS field. FLAGS bit4 may be a map-rendering category (road importance/direction for pbp)
  rather than a routing control bit. OSM visual overlay may clarify its cartographic meaning.
  **Twin-arc test (2026-09-20, `scripts/test_twin_arcs.py`, 50 blocks / 1915 arcs):**
  Cross-block global twin rate: 0x00 = 21.5 %, 0x10 = 22.1 %, delta = −0.7 %.
  **Result: SMENTITO (paired-arc model).** Arcs stored once per segment regardless of FLAGS value.
  The "direction = topology" model is false. FLAGS bit4 constraint is NOT expressed through paired
  arc storage and NOT through any btst #4 in routing code — semantics remain OPEN (best hypothesis:
  map-rendering / road-category flag, not a routing direction bit).
* `B` ∈ `{1,2,3,4,5,6}` in CF=1 blocks (3-bit field, `getbits(3)`, inherited across records).
  Distribution: B=1 43 %, B=4 19 %, B=5 15 %, B=3 14 %, B=2 6 %, B=6 3 %.
  Functional class (road category); CF=0 blocks may also carry the sentinel value `0xFF` ("absent").
* `C` is usually `0x0000`; when non-zero it points to a **locality** string in the same
  text area, used to tell apart streets with the same name (e.g. `haddington road` →
  `dublin 4`). In `0x0C` blocks it is an internal pointer to the name blob.

```python
PARCEL_S0_FMT = ">HBBHH"        # 8 bytes: A, FLAGS, B, C(name/aux ptr or 0), D(ptr to S1, stride 6)
```

### 6.3.1 Type `0x0E` CF=1 decoder & semantics

**Routing architecture** (from firmware): the routing engine (`rpmod`) and query
engine (`dbq`) request ONLY `BLOCK_TYPE` `0x0E` (parcels), `0x10` (street names),
and `0x12` (root). They **never** read `0x00`–`0x03` (those are `pbp` map-drawing)
nor `0x04` (house-number index). Thus **routing is NOT precalculated**: the firmware
reconstructs the network hierarchy, valid paths, and turn costs at runtime from the
base `0x0E` topology.

**Layout of the CF=1 `0x0E` block** (S0/S1 structure ✅ VERIFIED 2026-09-18, oracle 67/67 blocks; S2 ✅ VERIFIED 2026-09-19, oracle: pbp m68k write trace `pbp+0x41c0`):
- **Prologue**: `T[0x2b]` (48 bytes).
- **Bitstream pre-header** (raw bytes, copied before `bits_init`):
  - 2 bytes: Count *N* (number of 12-byte anchor structs)
  - *N* × 12 bytes: anchor table (reference points for Section 2 delta decode; NOT output to dst)
  - 1 byte: `M_hi` — delta field width for Section 2
  - 1 byte: `M_lo` — val2 field width for Section 2
- **Section 0** (Nodes/Segments, `T[0x2d]` = 8 bytes):
  - `+0 (u16) A`: internal pointer, `getbits(ptrbits)` → Section 2 byte offset.
  - `+2 (u8) FLAGS`: `getbits(2)` bits 0–1, `getbits(1)<<4` bit 4. (**NB**: m68k asm annotation "getbits(4)" is wrong for DB-REL 34.)
  - `+3 (u8) B`: If `getbits(1)`==1 → `getbits(3)`, else inherit from previous record. (**NB**: m68k annotation "getbits(8)" is wrong for DB-REL 34.)
  - `+4 (u16) C`: If same `getbits(1)`==1 → `getbits(ptrbits)`, else inherit.
  - `+6 (u16) D`: pointer to Section 1. `getbits(bits_needed(S1_count)) * T[0x41] + S1_offset`.
- **Section 1** (Edges/Attributes, `T[0x41]` = 6 bytes):
  - `+0 (u16)`: pointer to Section 2. `getbits(bits_needed(S2_count)) * T[0x42] + S2_offset`.
  - `+2 (u8)`: span count. If `getbits(1)`==1 → `getbits(bits_needed(S2_count)) + 2`, else `1`.
  - `+3 (u8)`: flag. `getbits(1)`. **1 = the entry has house numbers** (at least one of its
    S2 records has a non-`0x7FFF` range): 2,510 / 2,510, and 0 for all 4,363 others (CD-ID 21594).
  - `+4–5`: zero (not decoded); 0 in all 6,873 records sampled on CD-ID 21594.
- **Section 2** (street → map link, `T[0x42]` = 24 bytes; earlier read as geometry):
  unpacked from the bitstream using the anchor table. Algorithm (✅ VERIFIED 2026-09-19, oracle: pbp m68k write trace — `pbp+0x41c0`):
  - `idx_N = getbits(bits_needed(count_N))` → selects 12-byte anchor
  - `has_deltas = getbits(1)`
  - if `has_deltas`: for each of 4 fields: `is_16=getbits(1)`; `val=getbits(16 if is_16 else M_hi)`
  - else: 4 × sentinel `0x7FFF` — no geometry
  - `val1 = getbits(13 if subrel < 9 else 15) << 1`; `val2 = getbits(M_lo)`
  - **Output byte layout** (✅ VERIFIED 2026-09-19, oracle: pbp m68k write trace):

    | offset | size | content |
    |--------|------|---------|
    | `+0`   | i32  | `x_anc` — anchor bytes 0-3 (raw copy, `memmove pbp+0x41d4`) |
    | `+4`   | i32  | `y_anc` — anchor bytes 4-7 (raw copy) |
    | `+8`   | u16  | `raw_delta[0]` — unsigned, width = `is_16?16:M_hi` |
    | `+10`  | u16  | `raw_delta[1]` |
    | `+12`  | u16  | `raw_delta[2]` |
    | `+14`  | u16  | `raw_delta[3]` |
    | `+16`  | i32  | `anchor_f2` — anchor bytes 8-11 (raw copy, `memmove pbp+0x41ee`) |
    | `+20`  | u16  | `val1 = getbits(13 or 15) << 1` (15 from sub-revision 9) |
    | `+22`  | u16  | `val2 = getbits(M_lo)` |

  - **Field meaning** (2026-09-27, see "`0x0E` is the street-name directory" below):

    | offset | size | content |
    |--------|------|---------|
    | `+0`   | i32  | X of the **centre of the target `0x00` tile** (anchor bytes 0-3) |
    | `+4`   | i32  | Y of the centre of the target tile (anchor bytes 4-7) |
    | `+8`   | u16  | **even house numbers, low** (`0x7FFF` pair = none) |
    | `+10`  | u16  | even house numbers, high |
    | `+12`  | u16  | **odd house numbers, low** (`0x7FFF` pair = none) |
    | `+14`  | u16  | odd house numbers, high |
    | `+16`  | u32  | **`BLOCK_ID` of a type `0x00` map tile** (anchor bytes 8-11) |
    | `+20`  | u16  | `val1`: byte offset of a record in that tile's **SECTION_4** (road segments) |
    | `+22`  | u16  | `val2`: number of consecutive SECTION_4 records |

    The four "deltas" are **not coordinates**: they are unsigned house-number ranges, and
    there is no sign extension to apply. The anchor table in the pre-header is a per-block
    list of the `0x00` tiles the block links to: `(centre X, centre Y, BLOCK_ID)`.
  - The `is_16` flag is consumed from the bitstream but not stored in the record.

#### `0x0E` is the street-name directory (2026-09-27)

Checked on CD-IDs 2952, 21594, 21708 and 21734 (`CF=0`, `CF=1` and `CF=2`; `CF=1` on the DVDs with the 15-bit `val1`, see below):

| Check | Result |
|---|---|
| S0 `A` points to a NUL-terminated street name in the text after SECTION_2 | 122,743 / 122,743 records (CD-ID 21708, 150 `CF=2` blocks); same on both CDs |
| S0 records are in alphabetical order of that name | 97% (CD-ID 21708); accented names account for the rest |
| S0 `C`, when non-zero, points to a locality string (e.g. `haddington road` → `dublin 4`) | 24,137 / 24,137 (CD-ID 21708) |
| S2 `+16` is the `BLOCK_ID` of a type `0x00` block with that exact length | 100%: 455,974 records (CD-ID 21594, plain), 6,942 (CD-ID 2952), 23,451 (CD-ID 21708, `CF=2`), 23,724 (CD-ID 21734, `CF=2`) |
| S2 `+20` lands in that tile's SECTION_4 on a record boundary (stride `T[0x08]`: 32, or 30 on DB-REL 22) | 100% on all four discs; the `+22` run also stays inside SECTION_4 on CD-IDs 21708 and 21734 (checked there) |
| S2 `+8..+14` are two ranges, `lo ≤ hi`, first pair both even, second pair both odd | 100% on all four discs (e.g. 134,648 even and 135,855 odd ranges on CD-ID 21594) |
| S2 `+8..+14` match real house numbers (OSM `addr:housenumber` within 80 m of the linked segments, CD-ID 21734, 22 streets) | 98.9% of 1,355 addresses fall in a range of their street with the right parity; 85.5% in the range of their nearest segment (43.9% with the ranges shuffled between the street's segments) |
| S2 `+0/+4` is the centre of the target tile's bbox | 100% on CD-IDs 21708 and 21734 |
| The linked SECTION_4 segments carry the same name (segment name via SECTION_4 `+T[0x09]` → SECTION_2 `+0`) | exact / word-reordered / other name / unnamed: CD-ID 2952 55% / 16% / 19% / 11% (2,839 links); CD-ID 21594 64% / 18% / 18% / 0% (9,791); CD-ID 21708 37% / 37% / 26% / 0.1% (12,932); CD-ID 21734 35% / 47% / 18% / 0% (15,229). On the DVDs, "word-reordered" includes names that add `, locality` (`clavé anselm, roquetes` → `anselm clavé`). "Other name" is the road's other name, often a route number (`shanwar` → `n26`, `wirtenbacher strasse` → `l38`) |

So a `0x0E` entry is: street name → locality → one or more `(0x00 tile, run of road
segments, house-number ranges)`. This is the data the Destination → Street → House
number flow needs. The block holds no road geometry, and no topology (node or neighbour
references) has been found in its decoded fields; `S2`
plotted as `anchor + delta` produces the "disconnected dashes" noted below because the
anchor is a tile centre and the "deltas" are house numbers. Where the router gets its
topology from is **not** settled by this: the only road topology found so far is in
`0x00` (SECTION_4 end nodes, SECTION_6 boundary nodes), which contradicts the firmware
reading above that the router never requests `0x00`.

**`val1` width**: `val1` is `getbits(13)` below sub-revision 9 and `getbits(15)` from 9
(see `04-cf1-codec.md` §9.11.7). Read as 13 bits, the `CF=1` `0x0E` blocks of CD-ID 21708
lose sync at S2 (78% valid tile links, 15% valid house-number pairs); with 15 bits they
check out 100% on CD-IDs 21708 and 21734, and the CDs stay at 100% with 13.
`decode_s2_coords` should not be used as geometry.

**S2 coordinate reconstruction** (superseded 2026-09-27: `+8..+14` are house numbers, so
`anchor + delta` is not a position; kept for reference):
`decode_block` stores `M_hi` at `decoded[7]` and `M_lo` at `decoded[6]` after decoding a
0x0E block (bytes normally zeroed for CF). `decode_s2_coords(decoded, table)` reads M_hi
from `decoded[7]` and reconstructs absolute coordinates:

```python
M_hi   = decoded[7]          # from block pre-header
thresh = (1 << M_hi) - 1
for each S2 record i:
    x_anc, y_anc = S2[i]+0, S2[i]+4   # i32 anchor
    d[0..3]      = S2[i]+8             # 4 × u16 raw delta (unsigned)
    for k in 0..3:
        w_k = 16 if d[k] > thresh else M_hi
        signed_k = sign_extend(d[k], w_k)   # two's complement
    pt1 = (x_anc + signed_0, y_anc + signed_1)   # d[0]=dx1, d[1]=dy1
    pt2 = (x_anc + signed_2, y_anc + signed_3)   # d[2]=dx2, d[3]=dy2
```

Oracle: for each non-sentinel record with anchor in block's anchor bbox,
`|pt.coord − anchor| ≤ max_magnitude_k` (32767 for is_16, `1<<(M_hi−1)` otherwise).

> Implementation: `carin/parser/cf1.py` — `decode_type0E` + `_dec_0e_s0/s1/s2` (decoder);
> `encode_type0E` + `BitWriter` (serializer, ✅ STEP 4, oracle 10/10 PASS 2026-09-19);
> `decode_s2_coords` (coord reconstruction, ✅ STEP 5, oracle 10/10 PASS 2026-09-19).
> Firmware listing: `docs/fw/pbp_0x0E_decoder.asm`. Decoder entry `pbp+0x4320`
> (= `db_pub+0x1e98`); common section loop `pbp+0x40b0`; S2 handler `pbp+0x41c0`; `$694e` = memmove.

### 6.3.2 Types `0x0D` / `0x0F` / `0x11` — TEXT address-lookup index (NOT spatial)

**Discovery 2026-09-19** (STEP 3): these blocks were initially suspected to be a geographic
R-tree for parcel lookup. They are in fact an **alphabetical address index**.

Each block holds an array of **12-byte records** with identical layout:

```
  Offset  Size  Field  Content
  +0x00   u32   A      BLOCK_ID of target block (0x0C / 0x0E / 0x10 depending on type)
  +0x04   u8    B_hi   ASCII code — country / street-type code (e.g. 0x61='a'=Albania)
  +0x05   u8    B_lo   always 0x01
  +0x06   u16   C      byte offset into target block's S0 section
  +0x08   u16   D      record count in that range
  +0x0A   u16   E      always 0x0000 (padding)
```

Hierarchy and block counts:

| Type | Blocks | Target type | Semantics |
|------|--------|-------------|-----------|
| `0x0D` | 10 | `0x0C` | Country/language codes → record ranges in `0x0C` S0 |
| `0x0F` | 1,661 | `0x0E` | Street-name codes → record ranges in `0x0E` S0 |
| `0x11` | 921 | `0x10` | Street-name codes → record ranges in `0x10` S1 |

The `B_hi` code is an ASCII initial: the first `0x0E` block referenced (sector 235755)
is in Albania because 'a' is the first letter alphabetically. **This is address-lookup by
street name, not geographic proximity**. Do NOT use `0x0D`/`0x0F`/`0x11` for spatial
parcel lookup — use `scripts/find_parcel.py` instead (index from S2 `x_anc`/`y_anc`).

> **NAME_PTR Connection & 16-bit Truncation**:
> The 44 country records in block `0x0A` (Section 1) store a 32-bit `NAME_PTR` pointing into these `0x0D` blocks:
> - `high16` = `BLOCK_ID & 0xFFFF` of a `0x0D` block (`((sector & 0xFF) << 8) | length`).
> - `low16` = byte offset into the uncompressed `0x0D` block.
> - **Truncation Vulnerability**: For sectors > 255 (4 out of 10 `0x0D` blocks in `NAV_DB_21708.ISO`), the upper byte of the sector is discarded. Resolving `NAME_PTR` without a pre-scanned lookup table of `0x0D` blocks is impossible.
> - The record pointed to in `0x0D` links to an administrative `0x0C` parcel node. For UI display, human-readable country names are directly cached in `0x0A`.

### 6.4 Type `0x04` (80,825 blocks) — House Number Range Index ✅ RESOLVED 2026-09-21

```
+0x08 SECTION_DESCRIPTOR[1] = {0x0010, N}    ; N = record count (varies per block)
+0x0C SERVICE_DATA = BLOCK_ID of associated 0x00 map tile (4 bytes)
+0x10 SECTION_0: N records of 8 bytes = 4 × u16
      [f0 f1 f2 f3]  sentinel = 0x7FFF ("no houses on this side")
```

**Field semantics** (verified from rpmod.asm subroutine `0x014134`):

| Field | Meaning |
|---|---|
| `f0` | House number range start, Street Side A |
| `f2` | House number range end, Street Side A |
| `f1` | House number range start, Street Side B |
| `f3` | House number range end, Street Side B |

- Side A and Side B correspond to the two sides of the street segment.
- `f0` and `f2` always share the same parity (both odd, or both even); same for `f1`/`f3`.
- `btst #$0` on the query house number selects which parity side to search.
- Fill-in rule: if `f0 = 0x7FFF` → `f0 := f2`; if `f2 = 0x7FFF` → `f2 := f0` (symmetric default); same for `f1`/`f3`.
- Range check: `min(f0,f2) ≤ query ≤ max(f0,f2)` → returns byte offset of the matched street segment record in the associated `0x00` primary block.

**Firmware evidence:**
- `rpmod.asm` factory-default subroutine `0x01af8a`, line 31577: `move.w #$8, -$7e7a(a6)` — record size = 8 bytes.
- Subroutine `0x014134` (lines 22792–22952): full range-lookup implementation; parity check at `0x014226`; fill-in at lines 22840–22859; min/max at 22882–22895; range test at 22937–22952.
- Wrapper `0x013272` (line 21640): copies house-number query from `$42(a7)` → local struct offset `$1e` (`0x01329c`), then calls `0x01456c` → `0x014658` → `bsr $14134`.
- Empirical check: all high-range field values sampled from sector 5781092 (95, 103, 105, 109, 111, 113) are ODD integers — consistent with one side of an odd-numbered street.

**Linkage**: each `0x04` block is linked to its parent `0x00` map-tile block via `SERVICE_DATA` at `+0x0C`. The routing engine (`rpmod`) uses this block to resolve a house-number query to the byte offset of the street segment record inside the map tile.

### 6.5 Type `0x06` (2,688 blocks) — POI

```
+0x08 SECTION_DESCRIPTOR[1..6], first is {0x0020, N}
+0x0C UNKNOWN (4 bytes)
+0x10 BOUNDING_BOX: 4 x i32 big-endian = X_min, Y_min, X_max, Y_max   ✅ VERIFIED
+0x20 SECTION_0: N records of 24 bytes (see georef layout in 02-geo.md §8.1)
```
`X_max − X_min == Y_max − Y_min` always, and always `98304 · 2^k` → **quadtree grid**.
Observed sides: 98,304 / 196,608 / 393,216 / 786,432 / 1,572,864 / 3,145,728.
Full POI record layout → [`02-geo.md`](02-geo.md) §8.1.

## Discovery: Dual-Graph Architecture (Routing vs Display)
> **Update (2026-09-27):** the "dashes" are explained: S2 has no geometry at all. Its
> anchor is the centre of a linked `0x00` tile and its four "deltas" are house-number
> ranges (§6.3.1). The `0x0E` → `0x00` link is S2 `+16/+20/+22`.
>
> **CRITICAL NOTE (2026-09-22):** Section 2 of 0x0E blocks DOES NOT contain high-resolution map drawing geometry (polylines).
> Instead, it contains simplified routing heuristic segments or local bounding boxes used exclusively by the A* routing engine.
> Plotting S2 points yields millions of disconnected diagonal 'dashes' corresponding to the spatial extents of edges.
> The actual beautiful, high-resolution curved road polylines are stored entirely separately in 0x00 (map drawing) blocks, which are processed only for rendering.

### 6.6 Type `0x00` (91,756 blocks) — High-Resolution Map Geometry ✅ RESOLVED 2026-09-22

The `0x00` block holds the precise geometries for rendering the map, but it does NOT store them as a flat array of contiguous polylines.

**Coordinate Scaling:**\nJust like `0x06` POI blocks, `0x00` blocks use a fixed scale multiplier of `64.0`. (Previous theories about dynamic scaling via `ctx.widths` were incorrect; those bytes dictate bitstream extraction widths, not geometric scale).\n
**Section 4 (Spatial Tree):**
S4 is a **BSP/QuadTree**, not a flat line array. Traversing it sequentially creates massive zigzag artifacts.
- `+0x04` (u16): Pointer/index into Section 7 (starts a coordinate sequence).
- `+0x06` (u16): Pointer/index to the Left Child S4 record.
- `+0x08` (u16): Pointer/index to the Right Child S4 record.

**Section 7 (Coordinate Points):**
S7 is a sequence of 6-byte records.
- `+0x00` (u16): Delta X
- `+0x02` (u16): Delta Y
- `+0x04` (u8): **Topology Flag** (3 active bits). 
The firmware evaluates this flag to determine if the turtle graphics cursor should move (Pen-Up, e.g. starting a new line) or draw (Pen-Down, continuing the polyline). This flag breaks the sequence into individual street curves and correctly manages line continuity.

**Section 1 (Bounding Box / Geometry Limits):**
S1 (e1) is an array of 24-byte structs. Firmware C decompilation (dbq/pbp_clean.c) proves it parses identical to  x0E S2 records:
- Reads a flag: if  , populates four int16 fields with  x7FFF (sentinel for no geometry).
- If 1, it reads four int16 bounds (likely Delta X/Y bbox limits).
- Then it reads a uint16 (shifted left by 1) and a second uint16, mirroring exactly the al1 and al2 fields of  x0E S2.
This acts as spatial filtering to cull BSP branches without iterating S7 points.

**Firmware Dispatcher Architecture (The "Magic Numbers" Myth):**
Values previously thought to be internal section IDs (like  x24,  x28,  x2A,  x2C) are actually **direct byte offsets into the  x00 block header**.
- The  x00 block has an 8-byte header, followed by the SECTION_DESCRIPTOR array (offset, count).
- E.g.,  x28 is 8 + 8 * 4 = 40, which is the exact byte offset of the e8 descriptor's offset field.  x2A is the count field.
- The C firmware explicitly does *(ushort *)(in_D0 + 0x28) to read the array pointer, meaning the layout of  x00 is rigidly hardcoded, relying on these structural header offsets rather than runtime switch-cases.

