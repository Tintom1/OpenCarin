# Part 3 — Road Network Tables (Parcels)

> **Status: ✅ VERIFIED (STEP 2 & 3 complete, 2026-09-19).** Block/section structure
> AND field semantics for `0x0E` are fully verified from firmware traces (S0 `A`/`C` and
> the S2 fields were reinterpreted from disc data on 2026-09-27: §6.3.1). Spatial
> lookup via `find_parcel(vol, X, Y)` oracle 10/10 PASS. `0x0D`/`0x0F`/`0x11` = name
> tries for letter-by-letter search (not spatial, §6.3.2). Type `0x00` field semantics are now KNOWN (map drawing). Types `0x01`–`0x03` are assumed identical.
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
    (**Correction 2026-09-28:** `+0x10`/`+0x11` are read from the segment record whose offset is the arc's `+6`, i.e. a `0x00`-style segment, not a `0x0E` record: it rejects road class 6. See §6.7.)
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
    The ranges are the envelope of the per-segment numbers in type `0x04` over the linked
    run (§6.4).
  - The `is_16` flag is consumed from the bitstream but not stored in the record.

#### `0x0E` is the street-name directory (2026-09-27)

Checked on CD-IDs 2952, 21594, 21708 and 21734 (`CF=0`, `CF=1` and `CF=2`; `CF=1` on the DVDs with the 15-bit `val1`, see below):

| Check | Result |
|---|---|
| S0 `A` points to a NUL-terminated street name in the text after SECTION_2 | 122,743 / 122,743 records (CD-ID 21708, 150 `CF=2` blocks); same on both CDs |
| Packed (`CF=1`) blocks: the text is a `dec_text` name blob after S2, as in `0x00` (PR #14; before, the decoder never read it and every name came out empty) | S0 name/locality pointers on text: 259,454 / 259,454 over all 563 `CF=1` blocks of CD-ID 21708; every stream ends within a byte of the data end; decode → `encode_type0E` → decode identical from byte 8 in 150 / 150 |
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
`decode_s2_coords` should not be used as geometry; read S2 with `decode_s2_links` (`carin.parser.cf1`).

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

### 6.3.2 Types `0x0D` / `0x0F` / `0x11` — name tries (letter-by-letter search, NOT spatial)

Letter tries behind the destination entry, in the 12-byte record format of `0x0B`. Full
description (roots, leaf targets, `0x0C` city record, the rule the original compiler used to
build `0x0F`, rename tests on a CNI1): [`01-architecture.md`](01-architecture.md) §4.4.1 (PR #13).

```
  +0x00   u32   BLOCK_ID of the next level (leaf = 0) or of the target block (leaf = 1)
  +0x04   u8    letter   '@' (0x40) = the name ends here
  +0x05   u8    leaf     0 = inner node, 1 = leaf
  +0x06   u16   offset   of `count` records in that block (trie records, or target records)
  +0x08   u16   count
  +0x0A   u16   flags    0 (0x0100 on 0x11 alias records, e.g. IATA codes)
```

| Trie | Blocks (21708) | Root | Leaves point to |
|------|--------|------|-----------------|
| `0x0D` city names | 10 | `0x0A` country record `+0x00` (u32 `BLOCK_ID`, u16 offset, u16 count) | `0x0C` city records |
| `0x0F` road names | 1,661 | `0x0C` city record section 1 `+0x00` | `0x0E` S0 street records |
| `0x11` POI names | 921 | `0x0A` section 3 / `0x0C` section 3 (per category) | `0x10` POI records |

The whole Destination chain is therefore: country (`0x0A`) → `0x0D` → city (`0x0C`) → `0x0F` →
street (`0x0E` S0) → S2 link → segment run in a `0x00` tile (§6.3.1) → house number per
segment (`0x04`, §6.4).

**Checked on DVD 21708 (2026-09-28)** by walking the tries from both `0x0A` blocks (PR #13 checked
the CDs): 87 / 87 country roots are `0x0D` blocks; 424 / 424 sampled city leaves point to `0x0C`;
24,944 / 25,114 city names start with their leaf's prefix (the rest are Danish `ø`/`æ`, which the
check's accent folding does not map to `o`/`ae`); 423 / 424 cities root a `0x0F` trie; 2,006 /
2,006 road leaves point to `0x0E`; 15,761 / 15,763 street names (packed blocks decoded with
the name blob, see §6.3.1) start with their prefix.

**Superseded readings.** "`B_hi` = ASCII country/street-type code, `B_lo` always `0x01`" is the
letter and the leaf flag. The "32-bit `NAME_PTR`" in `0x0A` with its "16-bit truncation
vulnerability" came from reading the country record at `+0x02` instead of `+0x00`: `+0x02` u32 is
the low half of the `BLOCK_ID` followed by the offset. Read at `+0x00`, the `BLOCK_ID` is complete
and nothing is truncated. These tries are still not a spatial index (spatial lookup: `0x07`–`0x09`,
`02-geo.md` §7.3).

### 6.4 Type `0x04` (80,825 blocks) — per-segment house numbers ✅ VERIFIED on disc 2026-09-28

```
+0x08 SECTION_DESCRIPTOR[1] = {0x0010, N}   ; N = SECTION_4 count of the linked tile
+0x0C BLOCK_ID of the linked type 0x00 tile
+0x10 SECTION_0: N records of 10 bytes = 5 × u16
      [f0 f1 f2 f3 f4]   sentinel 0x7FFF = no number
```

Checked on CD-ID 21708 (all 80,114 `CF=2` and 711 `CF=0` blocks; `scripts/routing/check_04_house_numbers.py`):

| Check | Result |
|---|---|
| `+0x0C` is the `BLOCK_ID` (sector and length) of a type `0x00` tile | 80,825 / 80,825; no tile has two `0x04` blocks. The other 10,931 `0x00` tiles have none |
| Record `i` belongs to SECTION_4 segment `i` of that tile | record count = tile e4 count, 200 / 200 tiles sampled |
| `(f0, f2)` and `(f1, f3)` are the two sides of the segment | a side is either both `0x7FFF` or both set; same parity within a side 94%, opposite parity between the sides 84% (`f4` = 2 accounts for the exceptions below) |
| `f4` = numbering scheme | 0: no numbers (22,793,560 records, all empty); 2: odd/even split, one parity per side (15,059,361 with numbers, 99.8% single parity per side); 1: mixed, a side runs through both parities (1,440,795 of 2,097,923 have mixed parity within a side) |
| `0x0E` S2 even/odd ranges (§6.3.1) = envelope of the `0x04` ranges of the linked SECTION_4 run | 29,140 / 29,496 links (98.8%, 60 `0x0E` blocks); a scheme-1 side contributes both parities of its interval. The rest differ at one end of a mixed-scheme run |

So `0x04` is the fine-grained data (numbers at each end of each side of each segment) and `0x0E`
S2 is a per-link summary of it, used to pick the street run from the address search.

**Side and end (2026-10-01, `scripts/routing/check_house_number_sides.py`, DVD 21708 against OSM
addresses, Bari and Modugno).** Each OSM `addr:housenumber` with `addr:street` was given to the
nearest same-named segment (at most 25 m), placed on its polyline (`t` from the start node, left
or right of the start → end direction of the S4 record's polyline), and compared with the
stored numbers:

| Question | Result (Bari bbox 16.74–16.95 E, 40.98–41.20 N; 2,589 addresses on 53 `0x04` blocks) |
|---|---|
| `f0`/`f1` are the numbers at the **start** node and `f2`/`f3` at the **end** node | 205 / 210 sides (97.6%): the fitted slope of the OSM number against `t` has the sign of `f2 − f0` (`f3 − f1`). Modugno alone: 15 / 16 |
| `(f0, f2)` is the **left** side and `(f1, f3)` the **right** side of the start → end direction (scheme `f4` = 2) | side A on the left in 311 of 341 segments (91%), side B on the right in 298 of 315 (95%), counted per segment by majority of its addresses; Modugno alone: 22 / 27 and 16 / 18 |

The exceptions are not tied to the end test: of the segments testable on both, those with side A
on the right (5) all have `f2` at the end, and the two with `f2` at the start have A on the left.
Not examined: why about 9% of the segments disagree (OSM errors, one-way streets or a rule in
the record), the mixed scheme (`f4` = 1), and other countries (Italy, DB-REL 34 only).

**CC-93 firmware (hint, not the DVD reader).** `rpmod` sets the record size with
`move.w #$8, -$7e7a(a6)` (factory-default subroutine `0x01af8a`, line 31577), i.e. 8-byte
records with four fields: the DVD format has a fifth field. Its lookup, subroutine
`0x014134` (lines 22792–22952), matches the side pairing above: `btst #$0` on the query
number picks a side (`0x014226`); fill-in `f0 := f2` if `f0 = 0x7FFF` and vice versa, same for
`f1`/`f3` (lines 22840–22859); range test `min ≤ query ≤ max` (lines 22882–22952), returning
the offset of the matching segment in the linked `0x00` tile. Caller chain: `0x013272`
(line 21640) copies the query from `$42(a7)` to local `$1e`, then `0x01456c` → `0x014658` →
`bsr $14134`. The earlier reading of this block as "160 records of 10 bytes, meaning unknown"
(blueprint §6.4) had the right size; 160 was one block's count.

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
> **Correction (2026-09-28):** `+0x06` / `+0x08` are not tree children but the next segment at the start / end node, and section 4 is the road graph; see §6.7.

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
S1 (e1) is an array of 24-byte structs. Firmware C decompilation (dbq/pbp_clean.c) proves it parses identical to 0x0E S2 records:
- Reads a flag: if 0, populates four int16 fields with 0x7FFF (sentinel for no geometry).
- If 1, it reads four int16 bounds (likely Delta X/Y bbox limits).
- Then it reads a uint16 (shifted left by 1) and a second uint16, mirroring exactly the val1 and val2 fields of 0x0E S2.
This acts as spatial filtering to cull BSP branches without iterating S7 points.

**Firmware Dispatcher Architecture (The "Magic Numbers" Myth):**
Values previously thought to be internal section IDs (like 0x24, 0x28, 0x2A, 0x2C) are actually **direct byte offsets into the 0x00 block header**.
- The 0x00 block has an 8-byte header, followed by the SECTION_DESCRIPTOR array (offset, count).
- E.g., 0x28 is 8 + 8 * 4 = 40, which is the exact byte offset of the e8 descriptor's offset field. 0x2A is the count field.
- The C firmware explicitly does *(ushort *)(in_D0 + 0x28) to read the array pointer, meaning the layout of 0x00 is rigidly hardcoded, relying on these structural header offsets rather than runtime switch-cases.

### 6.7 Types `0x00`–`0x03` — Road Graph (routing) (2026-09-28)

Types `0x00`–`0x03` form a routable road graph. `0x00` is the street level and `0x01`–`0x03` are coarser levels of the same network. Everything below was checked on disc data from CD-IDs 2952, 21594, 21708 and 21734 (sample sizes given per row). Rows marked **FW** are also confirmed in the Philips CARIN CC-93 firmware (`dbq/rpmod.asm`, `(c) PHILIPS,Eindhoven CARIN CC-93 system`, 1993, OS-9/68K, taken from a BMW update disc), where the route planner reads these fields from segment records at the same offsets. The CC-93 is a sibling of the units that read these discs, not their own firmware (e.g. the Renault CNI1's firmware is not in the repo), so **FW** means "an older CARiN route planner reads the field this way".

> **RR firmware (2026-09-28).** The route planner of the unit that actually reads the DVDs (VDO Dayton RoadRunner, `bsw2` `rpmod`, MIPS) unpacks this record in `sub_01fd80`. It confirms `+0x00`/`+0x02`, `+0x0B` (form, direction, **toll**), `+0x0C`, `+0x0E`/`+0x0F`, `+0x10` (class, subtype), `+0x11` (the same car-access rule as `can_traverse`), the slip role (`+0x18 & 3` on DB-REL ≥ 27, else from `+0x0B`; `+0x18` of packed tiles comes from pass `0x1B`, `04-cf1-codec.md` §9.11.12), and reads **section 10 via `+0x12`** and section 12 via `+0x14`. It also reads fields not explained here: `+0x10` bit 7, `+0x1D` bits 4–6 and `+0x18 & 0x10` (DB-REL ≥ 27). See [`../fw/04-rr-rpmod-edge-record.md`](../fw/04-rr-rpmod-edge-record.md).

**Segment record (section 4, record `T[0x08]`: 32 B on DB-REL 34, 30 B on DB-REL 22):**

| Offset | Field | Evidence |
|---|---|---|
| `+0x00` / `+0x02` | start / end node: in-block offset of a section 5 node or a section 6 edge node | 100% on all four discs (e.g. 19,054 / 19,054 ends on CD-ID 21594). **FW**: `rpmod:007d18` picks `+0x00` or `+0x02` from the arc's direction flag |
| `+0x04` | first shape point in section 7 | geometry vs OSM (`02-geo.md`) |
| `+0x06` / `+0x08` | **next segment at the start / end node** (0 = none), not BSP children | the target always shares the node (12,850 pointers, CD-ID 21594). Following them visits every segment at that node: 11,611 / 11,622 (CD-ID 21594), 9,411 / 9,414 (2952), 5,733 / 5,734 (21708), 5,701 / 5,704 (21734) |
| `+0x0A` bits 0–4 | **speed category**, roughly km/h ÷ 4 | vs OSM `maxspeed`, name/position-matched (CD-ID 21594, Dublin + Leeds, 45,080 segments; 3 rural areas, 1,236): 20 mph → 5, 30 mph / 50 km/h → 11, 40 mph / 60 km/h → 16, 80 km/h → 22, 60 mph / 100 km/h → 26, 70 mph → 31; footways and pedestrian streets 2, minor/service roads 5. Bits 5–6 are always 0. **0 means no speed is stored**, not 0 km/h: on a CD (DB-REL 34) around Deurne it is on 520 of 623 motorway edges (106.7 of 123 km) and on 48 class 1 edges, while other classes carry values (class 4: 6 and 11, class 6: 3). Treat it as unknown and use a default per road type. Not found in the firmware yet |
| `+0x0A` bit 7 | **built-up area** | same value as `+0x1D` bit 7 on all 63,922 segments sampled. Its share falls from 1.00 on the smallest (densest) tiles to 0.12 on large rural tiles; in rural areas 81% of 30 mph roads have it set and ~90% of 60 mph roads have it clear |
| `+0x0B & 0x0F` | **form of way**: 0 motorway; 1 on-slip, 2 off-slip, 3 motorway-to-motorway link; 4 dual carriageway (non-motorway); 8, 9, 0xA the same three slip roles at non-motorway junctions; 0xB, 0xC single carriageway (0xB mostly on main roads) | Slip roles from the graph (CD-ID 21594, 1,510 one-way slip segments in 236 tiles): form 1 never starts at a motorway and is the only one that ends at one from a road; form 2 starts at the motorway and ends on a road; form 3 runs slip → slip or joins two motorways. vs OSM (Dublin + Leeds): motorway 0 (88%) / 1 (8%); `motorway_link` 1 (57%), 0, 2; one-way trunk 4 (77%), one-way primary 4 (69%); residential 0xC (99%). **FW**: `rpmod:0043ca` returns false for exactly 1, 2, 3, 8, 9, 0xA (slip roads); `0056c0` stores that as a flag used when choosing which segment to snap a position to. Also copied to edge `+0x28` |
| `+0x0B` bits 4–5 | **direction restriction**: 0 two-way, 1 (bit 4) passable only along the stored direction, 2 (bit 5) only against it, 3 closed to vehicles | vs OSM `oneway`, name/position-matched, rate the bits agree with OSM: 91 / 76 / 82% (CD-ID 21594, Dublin, 2,263 segments), 91 / 75 / 81% (CD-ID 21708), 94 / 50 / 55% (CD-ID 2952, York, 27 years older). Both bits = pedestrian streets (Grafton St, Henry St). **FW**: `rpmod:011ad6` does `(+0x0B & 0x30) >> 4` and switches on it exactly so; `011b42` tests `== 3` |
| `+0x0B` bit 6 | **toll road** | set on 89% of OSM `toll=yes` segments and 0% of the rest (44 segments: M50, M1) |
| `+0x0C` | **length in metres** (u16) | correlation 1.000 with the shape length, median 0.999 m per unit (5,952 segments). **FW**: `rpmod:007d88` multiplies it by 100 into the edge record |
| `+0x0E` / `+0x0F` | **compass bearing** leaving the start node / leaving the end node back into the segment, in 1/256 turn (0 = north, clockwise) | median error 1.1°, 95–96% within 10° (4,512 segments). **FW**: `rpmod:007dd0` picks one by direction and scales by `0x8CA0 >> 8` (36,000 / 256, i.e. hundredths of a degree) |
| `+0x10 & 0x0F` | **road class**, 0 (motorway/trunk) … 4–5 (residential) … 6 (pedestrian, service, private) | vs OSM `highway` (Dublin). **FW**: copied into the edge record at `007d9e`; `can_traverse` (`rpmod:004360`) rejects class 6 |
| `+0x10` bits 4–6 | **class 6 subtype**, 0 on every other class: 1 restricted road (most private/service/estate roads), 3 private or permissive, 5 pedestrian street or footway, 6 pedestrian street closed to vehicles (`access=no`); 2 and 4 rare | vs OSM `highway`/`access` on 1,418 class 6 segments (Dublin + Leeds). **FW** compares it with 5 (not traced further) |
| `+0x11 & 0x0F` | **junction type**: 0 ordinary; 6 roundabout; 9 short connector inside a junction (median 27 m, on every road type, including slip lanes); 2 and 5 rare; 3 appears only on the DVD (see **FW**) | 6: 91–100% of OSM roundabout segments on residential/trunk roads; 9: 1,398 segments. **FW**: `can_traverse` (`004360`) rejects 3 and 4 unless the high nibble is 4; `004432` groups 0, 2 and 9 against 5 and 6; `0056c0` prefers segments ≥ 20 m with value 0 when snapping a position |
| `+0x11 >> 4` | 2 on every CD segment; 1 and 4 occur with low nibble 3 on the DVD (`0x13`, `0x43`) | unexplained; `0x43` is the case `can_traverse` lets through |
| `+0x12` → section 10 | start of this segment's **forbidden turns** (see below) | monotone in 108 / 108 tiles |
| `+0x14` → section 12 | TMC location references (DVD only, see below) | |
| `+0x16` → section 13 | **toll points** (DB-REL 34; see below) | every segment of a tile holds the same offset when the section is empty |
| `+0x18` / `+0x19` | two bytes; `+0x19` is 0 on every segment of every tile checked. `+0x18`: 1, 2, 3 = the segment's slip role, repeating `+0x0B` form 1/8, 2/9, 3/0xA; 4 almost only on class 3–6 (plain DVD tiles: 5 of 393,203 on classes 0–2; mostly class 5 and class 6 subtypes 1, 3, 4, 5; on CD-ID 21594 about a third of class 6 subtype 1, mostly tracks, service roads and farm lanes in OSM; meaning unclear); 5–7 rare; `0x10` rare, on main roads, sometimes combined with a slip role (`0x11`–`0x13`, one `0x14`). Plain tiles store it in the record; packed tiles in pass `0x1B`, see "Packed tiles: pass `0x1B`" below. **RR**: `rpmod sub_0630cc` takes the slip role from `+0x18 & 3` on DB-REL ≥ 27, `sub_01fd80` also reads `+0x18 & 0x10` | Plain, CD-ID 21594 (1,114 tiles): 236 / 236 tiles with slip roads mark every slip segment. Plain DVD tiles (`pass18_baseline.py`): non-zero on 185,496 / 2,643,784 segments (21708) and 298,577 / 3,791,013 (21734); every segment with a slip form in `+0x0B` has the same role in `+0x18 & 3`; the reverse fails on 2,855 and 9,290 segments (role only in `+0x18`; `& 3` = 3 on 2,727 and 8,909 of them). Packed (all CF=1 tiles): 39,740,445 / 39,760,087 and 42,257,406 / 42,299,606 agree, same one-way exceptions |
| `+T[0x09]` → section 2 | road name and locality | `03-road-network.md` §6.3.1 |
| `+T[0x09]+2` hi (`+0x1C`) | bit 4 always set; **bit 3 = bridge**; bits 1–2 (value `0x16`) on stretches of motorway/trunk/main roads; bit 0 on a few tunnels (`0x1D`) | bit 3: 80% of OSM `bridge` segments vs 1% of the rest. `0x16`: 41% of motorway segments (M621, M50, Leeds Inner Ring Road, M1), 6% of trunk; meaning unknown |
| `+T[0x09]+3` (`+0x1D`) | bit 7 = built-up area (same as `+0x0A` bit 7); bits 1–2 ≈ **width / lane category**: 0 one-lane one-way, 1 ordinary road, 2 wide one-way (motorway carriageway), 3 wide two-way (4+ lanes); bit 0 unexplained (mostly set on residential streets) | vs OSM `lanes`: one-way 1 lane → 0 (63%); two-way 1–2 lanes → 1 (92–94%); motorway → 2 (89%); two-way 5 lanes → 3 (61%). Coarse, not a lane count |
| `+T[0x09]+4` → section 11 | **signposts** (see below) | |

**Packed tiles: pass `0x1B` (DB-REL ≥ 27).** In `CF=1` tiles `+0x18` comes from a fourth pass over section 4 that the RoadRunner reads after pass `0x17` and its two text flags (`db_pub` `sub_005e6c +0x6e70` → `sub_005594` kind `0x1B`, `+0x5b5c`): per segment, no sentinel, a flag bit, then `+0x18` and `+0x19` as two `getbits(8)`, or both copied from the previous segment. The Mk3 builds (0103–0127), from which `decoder_00.py` was ported, have no such pass; RR 0101, 0102 and 0103 all do. After it the stream holds one 1 bit and zeros; no firmware reads that bit. Every `CF=1` `0x00` tile of CD-IDs 21708 and 21734 passes `scripts/codec_cf1/oracle_00.py` with the pass decoded (86,107 / 86,107 and 91,651 / 91,651). The first segment always carries a value and an explicit value never repeats the previous one (300 tiles per disc); segments repeating the previous value: 95.3% / 95.0% packed, 94.7% / 94.5% plain. The "head" of unknown content described here before (median 18 bits on CD-ID 21594, found by search) was not part of the format: the port skipped the pass `0x15` sentinel record, so pass `0x17` and the two text flags were read shifted. In the aligned stream the gap is the two flags, plus a text blob of exonyms when the second is set. Details: `04-cf1-codec.md` §9.11.12. CD-ID 2952 (DB-REL 22) has no `+0x18` and no pass after `0x15`; DB-REL 34 CD-ID 21594 was not rerun here.

On DB-REL 22 (30 B records) there is no `+0x16` section 13 pointer: `+0x14` is the last section pointer, `+0x16` is the always-zero u16, `T[0x09]` = `0x18`, and the flags u16 is at `+0x1A`. On CD-ID 2952 (100 tiles, 15,186 segments) the same fields show the same patterns: class 6 subtypes, `+0x11` 0/5/6/9, the `+0x1A` hi byte 0x10/0x18/0x90, low byte 0x80–0x87. The speed values differ slightly (mostly 13, 17, 22, 31 and 2 instead of 11, 16, 22, 31 and 2). These were not matched to OSM on that disc. Tools: `local/tools/seg4.py` (per-class survey), `seg4osm.py` (OSM matching), `seg4study.py` and `seg4bits.py` (cross-tabs).

**Nodes and tiles:**
- Section 5 (`T[0x10]` = 8 B): nodes inside the tile, `(u, v, …)` in the tile frame.
- Section 6 (`T[0x06]` = 16 B): **tile-edge nodes**. `(u, v)`, then `+8 u32 BLOCK_ID` of the neighbouring tile of the same type and `+12 u16` byte offset of its twin record. The twin points back and sits at the same absolute position: 1,574 / 1,574 (`0x00`), 755 (`0x03`), 619 (`0x02`), 373 (`0x01`) on CD-ID 21594; 778 / 778 and 818 / 818 on CD-IDs 21708 / 21734; 919 / 937 on CD-ID 2952.
- Section 9 (`T[0x0F]` = 8 B): the neighbouring tiles.

**Levels.** Every node of `0x01`, `0x02` and `0x03` lies exactly on a `0x00` node (100% on CD-ID 21594). Coarse segments pass through street junctions without stopping (32% of `0x03`, 37% of `0x02`, 46% of `0x01` segments), so each coarser level is the main-road network with minor junctions merged. **Section 8** of a coarse tile links it to the next level down (`0x01` → `0x02` → `0x03` → `0x00`; empty in `0x00`). It holds `gw × gh` `u32` `BLOCK_ID`s, one per cell of a grid over the tile, numbered column-major (`cx · gh + cy`), with the grid aspect equal to the tile aspect. A coarse node is found one level down by position: its cell gives the tile, and the node with identical coordinates is its twin. This resolved every node with a twin (CD-ID 21594: 869, 1,428 and 569 nodes; CD-ID 2952: 1,101, 964 and 668, with 55 nodes lacking a twin).

**Levels on CD-ID 2952** (plain tiles, `local/tools/build_attempt21.py`):
- A tile's header `+84` is its parent one level up: `0x00` → `0x03` → `0x02` → `0x01`.
- `0x03` holds road classes 0–2, `0x02` classes 0–1 and `0x01` class 0 (15,000 segments sampled).
- Coarse segment records are 24 B: the 30 B layout up to `+0x15`, then `+0x16` = 0 (no name).
  Coarse tiles store their sections in the order 0–7, 9, 8, 10–12 (4,424 / 4,424); their section 2
  is the null name record alone.
- Every plain road tile ends section 4 with a **sentinel record**: zero except `+0x04` (the end
  of section 7) and `+0x12` / `+0x14` (and `+0x1C` in `0x00`), which hold the end of the sections
  they point into (5,934 / 5,934 tiles).
- A node record (sections 5 and 6) is `u, v`, `+4` the first segment at the node, `+6` flags.
  **Flag bits 15–14 give the highest level the node reaches**: 3 street level only, 2 up to
  `0x03`, 1 up to `0x02`, 0 up to `0x01` (31,700 / 32,400 nodes sampled; the rest have their twin
  across a tile edge); edge nodes have `0x2000` set as well. A coarse node carries exactly its
  street twin's flags (9,935 / 10,015). Bit 12 is set. Bits 8–11 follow the node's degree: 1 at
  one segment, 5 at two, 0 at three or more (1,957 / 2,001 nodes in 300 tiles); 2 also occurs at
  junctions involving slip roads and 4 at some street-level-only nodes with two segments (meaning
  open). The low byte is 0, or 1 / 2 on the two nodes of a crossing (below).

**How the coarse levels follow from the street level** (CD-ID 2952, 60 random tiles per level in
Great Britain; `local/tools/coarse_study.py`). A coarse tile's street tiles are the tiles whose
header `+84` points at it (read down level by level) together with its section 8 grid; some `0x03`
grids are empty.
- A level keeps the street roads of its classes (≤ 2, ≤ 1, 0). About 4% of the runs between
  junctions are left out: 211 / 5,107 on `0x03`, 225 / 5,628 on `0x02`, 57 / 1,671 on `0x01`.
  Almost all are one-way, none are dead ends, and most have no same-direction alternative through
  the kept roads; which ones are left out is not understood.
- Each coarse segment is the shortest street path of its own class between its two nodes. Its
  length is the sum of the street lengths (within 1 m: 6,532 / 6,554, 7,119 / 7,148,
  2,436 / 2,440); class, speed and form are the same all along it (6,553 / 6,554 and similar);
  `+0x0E` / `+0x0F` are the bearings of the first and last street segment. The shape keeps a
  subset of the street shape's points (median ½ on `0x03` and `0x02`, ⅓ on `0x01`); how points are
  chosen is not known.
- **Coarse nodes**, counted on the kept roads: a node where three or more kept roads meet is always
  a coarse node (3,188 / 3,188 on `0x03`). Where two meet, it is a coarse node exactly when class,
  speed, form of way, built-up (`+0x0A` bit 7) or the one-way direction changes there; a change of
  name or junction type (`+0x11`) doesn't count. Two kept roads without such a change: the coarse
  segment passes through 12,817 times (13 exceptions) on `0x03`, 17,201 (11) on `0x02` and
  10,880 (4) on `0x01`. Street tile edges are passed through; coarse tile edges end a segment.
- **Crossings without a junction** (bridges) are two nodes at the same coordinates, with node flag
  low byte 1 and 2 (2,638 and 2,640 in 3,000 tiles). Each has its own two segments and its own
  next-segment ring, so the roads don't connect. A graph keyed on coordinates alone would join
  them; key it on coordinates and that byte.

**Writing road tiles (tested on a CNI1, CD-ID 2952, 2026-09-28/29).** Plain tiles written from our
own records, on burned discs:
1. The map is drawn from the node `(u, v)` and section 7 through `+0x04` alone. Moving nodes and
   shape points, with the same records, counts and topology, redraws the roads (text in road
   shapes worked), joined to the neighbouring tile at the edge nodes.
2. Two ordering rules are **required**; breaking them crashed the unit whenever the map loaded. A
   segment's start node is the end with the lower `(x, y)` (43,757 / 43,809 segments on the disc;
   reverse the shape and swap the one-way bits to match), and the section 5 nodes are
   `(x, y)`-sorted within each level of section 3 (2,800 / 2,800 groups). A node's level is the
   lowest class among its segments (100%), and section 2 is sorted by name.
3. A tile without edge nodes (section 6 empty) works, and so does a disc whose road tiles are all
   emptied (sections 0, 1, 8, 9 and the strings kept; section 2 the null record; the rest empty).
4. With our own records throughout (next-segment rings in clockwise bearing order, levels, flags,
   lengths, bearings) the unit routes along our roads and gives turn-by-turn guidance (arrows,
   speech, distance), also in a country of empty tiles. Guidance starts once the car is on a road
   line of the map; before that the unit only shows a direction arrow.
5. **Choosing a POI needs the level links near the car**; choosing a street does not. On a disc
   where the four `0x03` nodes whose section 8 cell is the car's `0x00` tile had lost their twins
   (the tile's nodes were moved), no POI showed the Guidance button; giving those four nodes back
   their positions fixed it. Our own `0x03`, `0x02` and `0x01` tiles, written from a street tile
   (its segments unmerged, every coarse node on a street node, flags as above), draw when zoomed
   out. Whether they carry POI routing was not tested apart from other changes.
6. On a map of empty tiles, the town, sea and road-number labels that remain come from the name
   blobs of the area and line layers `0x14`–`0x16` (`02-geo.md` §8.4); emptying the blobs removes
   them.

**Node cycles, ordering and editing a tile in place (DVD 21708, tile `0x4c184f18`, 2026-10-01).** A section 5
node is `u16 u, u16 v, u16 first segment, u16 flags`. The segments that meet at a node form a cycle: the node
holds the offset of the first one and each segment's `+0x06` (if the node is its start) or `+0x08` (if its end)
the next. On this tile the stored cycles equal the segments found by node in 358 / 358 nodes, and a cycle with
at least two members is ordered **clockwise by the bearing leaving the node** (`+0x0E` at a start node, `+0x0F`
at an end node) **starting from the smallest bearing**: 262 / 262 cycles (234 / 234 of three or more members run
clockwise, none counter-clockwise). The two ordering rules above hold on the whole tile: the start node has the
lower `(x, y)` in 460 / 460 records and the S5 nodes are sorted inside each level group of section 3
(`+2` of a section 3 record is the group's first node). Section 10 entries (27 / 27) name a segment that shares
a node with their owner. With these rules a tile can be edited without moving a byte of any section (same
record counts): node positions, shape points, segment ends, lengths and bearings, junction type, one-way bits,
node cycles. `examples/04_update_modugno_roundabout` does this to replace a crossing by a roundabout; the
re-encoded tile (12,125 B in the original 24 sectors) reads back identically with the Python and the Rust
decoder. Not yet run on a unit.

**Editing a tile that grows, and what points into it (DVD 21708, tiles `0x4c184f18` and `0x5c58a51c`, 2026-10-01).**
Records can be added and removed if every pointer is rewritten. `carin/parser/cf1/tile00.py` parses a decoded `0x00`
tile into objects that refer to each other and builds it again; its docstring is the pointer catalog (every absolute
in-tile offset: S4 `+0x00 +0x02 +0x04 +0x06 +0x08 +0x12 +0x14 +0x16`, street record, signposts; S5 / S6 `+4`; S3; S10 / S13 `+4`;
S11 text; S0 / S1 / S2 / S14 links). The sections follow each other in the order 0 1 2 3 4 5 6 7 9 8 10 11 12 13 14 (name blob last); S11 and S12
are followed by two zero bytes (S4 `+0x1E` / `+0x14` of the sentinel point at the end of the section, before them). The ranges
`+0x04` (S7), `+0x12` (S10), `+0x14` (S12), `+0x16` (S13) and `+0x1E` (S11) are monotone covers: a segment owns the entries up to the next
segment's pointer (460 / 460 here). Checked on 62 tiles of the disc (40 street CF=1 tiles over the size range, 20 coarse, the two of this test; `scripts/codec_cf1/check_tile00_relayout.py`):
parse and build give the tile byte for byte, and a tile whose sections are shifted by extra bytes has the same graph and re-encodes (`encode_type00`) to the same decoded bytes.
Facts found on the way:
- **Level group k of S3 holds the class-k segments and the S5 nodes whose lowest class is k** (7 groups for classes 0 to 6; 460 / 460 segments and 294 / 294 nodes
  here, 7 groups). A new record goes into the group of its class; a class change moves it.
- A node with one segment holds that segment as its first and each segment's next at that node is itself (32 / 32 here); at an S6 edge node a lone segment's next is 0 (64 / 64).
- The cycle and ordering rules of the paragraph above hold on 43 of 62 sampled tiles untouched; the exceptions are 10 cycles at nodes on the tile edge and 36 S10 entries
  whose target shares no node with the owner (19 tiles). The tile of this test has none.
- A zlib block's header `+7` is its decoded length in 512-byte sectors (330 / 330 blocks checked); it must be rewritten when a coarse tile grows by a sector.
- **Coarse tiles** (`0x01`-`0x03`, zlib on this DVD) have 26-byte S4 records: the 32-byte layout up to `+0x19`, without the street record, flags and signpost pointer.
  A coarse segment of a three-way node is its street record (same fields, shape, bearings): found by the absolute coordinates of its end nodes, 6 / 6 here. An empty S14 may be written with offset 0.
- Words 24-26 of the 116-byte header of a street tile (`0x726 0x726 0x724` here) vary and match no count, length or class sum tried; an edit leaves them as they are. Unknown.

*What points into a street tile* (`carindb-rs xref`, 39 s over 315,095 blocks; `carin/parser/refs.py`): the tile `0x4c184f18` appears in 1,080 places.
`0x0E`: S2 `+16` BLOCK_ID, `+20` S4 offset, `+22` count (934 runs in 320 blocks). `0x10`: its section 4 holds 8-byte entries u32 BLOCK_ID, u16 S4 offset, u16 flag, one segment per street and tile (24 here, 2 blocks).
`0x17` (TMC locations): x, y, idA, idB (u32), offA, offB (u16) (4 hits). `0x04`: header `+0x0C`, one record per S4 record. `0x00` neighbours: S6 `+8` / `+12` twin offset in the edited tile's S6 (64
in 5 tiles). Only BLOCK_ID, no offset: `0x03` S8, `0x09` cell, the `+0x58` header word of 32 street tiles (the parent coarse tile), S9. Nothing was found that stores an S5 node offset of the tile.
A coarse tile is referenced by its four coarse neighbours (S6 twins) and the same BLOCK_ID-only places. Inserting records shifts every S4 offset after the insertion (918 of 934 `0x0E` runs here);
**an edit that keeps the tile in its sectors changes no BLOCK_ID** (its low byte is the length in sectors). Every block rewritten this way kept its extent (a zlib block with at least 142 spare bytes).
Where a record is removed, an entry that names it is redirected to the nearest record of the same street (`0x10`, `0x17`) and a run shrinks to its surviving, still consecutive records (`0x0E`),
whose house-number ranges are recomputed from the new `0x04` records (the envelope rule above).
`examples/04_update_modugno_roundabout` (steps 5 to 7) uses all of it: roundabout of 6 ring records, 4 links and 2 arms of Viale della Repubblica in 24 sectors (12,208 of 12,288 B). Not run on a unit.

**Section 10 (`T[0x14]` = 8 B): forbidden turns.** A segment's entries run from its `+0x12` to the next segment's. Each entry is `u32 BLOCK_ID` (own tile), `u16` offset of a target segment and `u16` flag:
- flag 0: the target meets the owner at its start node (548 / 562);
- flag 1: at its end node (514 / 542);
- flags 0 and 1 also occur with the owner itself as the target (CD-ID 2952, 6,000 sampled tiles: 106 with flag 0, 97 with flag 1): a ban on turning back into the same segment at its start or end node, i.e. a **U-turn ban**, stored like any other entry. This is read from the data alone; not yet checked against OSM `no_u_turn` or on a unit;
- flags 2 and 3 are not turn bans. On CD-ID 2952 (same sample) they come in pairs on the same segment, both pointing at the segment itself (1,055 with flag 2, 1,033 with flag 3), plus 727 flag-2 entries into another segment at the owner's start node and 713 flag-3 entries at its end node. The owners have form of way 7 (`+0x0B & 0xF`, a value not otherwise explained) and usually a dead end at one node, which suggests an access rule such as "no through traffic" rather than a turn ban. Not understood further.

In central Dublin (CD-ID 21594), 55% of these junctions lie within 15 m of an OSM turn restriction, against 10% for random junctions, and 57% of OSM restriction vias have an entry within 20 m. Using the bearings to classify each entry's turn: at OSM `no_right_turn` junctions 33 of 38 entries are right turns; at `only_straight_on` junctions all listed turns are left or right; at `only_right_turn` junctions they are left turns. Found in the RR firmware (2026-09-28): `rpmod` `sub_06322c` reads the range from `+0x12` and `sub_01fd80` splits the entries by flag bit 0 into start-node and end-node lists (≤ 8 each).

**Routable export check (2026-10-03).** A 2007 Master CD (DB-REL 34, 512-byte unit), tiles in `5.4–5.6° E, 51.35–51.5° N` (118 `0x00` tiles, 26,330 nodes, 34,215 segments), exported with `scripts/routing/export_routable.py` and compared with OpenStreetMap data of 2026 (the disc is 19 years older, so new roads and rebuilt junctions show up as differences). The scripts used for the checks below are not part of the export PR.
- **Graph:** 38 connected components, the largest has 99.3% of the nodes, no singletons; 91.7% of the segments are car-passable (not class 6, not closed), 7,288 one-way, 353 roundabout segments. Stored length `+0x0C` against the polyline: median 1.003 (p5 0.971, p95 1.041).
- **Tile joins:** 4,802 section 6 twin links, 4,376 of them inside the exported window; none of those lies more than 2 m from its twin. The other 426 point to tiles outside the window.
- **vs OSRM (public demo, OSM 2026), 40 random routes of 3–25 km:** the distance ratio CARiN / OSRM has median 0.996 (p10 0.859, p90 1.097). Replaying the OSRM geometries on the CARiN segments (sample every 50 m, 25 m tolerance): 96.9% of 18,666 samples have a CARiN segment nearby (misses cluster in a few new areas); for the 18,090 matched samples, a car-passable segment that allows OSRM's direction of travel is within 25 m in all but 52 (0.29%: car-passable segments exist but all one-way against OSRM, mostly the rebuilt A2 / A58 interchange) and 42 (0.23%: only class 6 segments nearby).
- **Turn bans (S10) against 332 OSM `restriction` relations** in the same area, matched by position and by the bearings of the two ways at the via node: 13 `no_*` restrictions agree with owner = `from` way, target = `to` way and 1 with the reverse; 12 `no_u_turn` relations agree; of the `only_*` relations 30 have bans from their `from` way to other ways and none bans the mandatory turn. So **an S10 entry bans the turn from the owner segment into the target segment.** 184 OSM restrictions have no ban within 25 m of their via node (newer than the disc, or not stored).
- **Routing engines:** `osrm-extract` (car profile) reads the OSM XML as is; it takes all 1,601 bans (761 flag 0, 840 flag 1, no entry targets its own owner), rejects 17 as invalid and routes with them: of 748 drivable bans 746 are honoured (or leave no route), while on a control graph without restrictions 747 are driven through.
- **Route choice and travel time:** read as 5 km/h, the category 0 edges make motorways unattractive: the worst distance ratio CARiN / OSRM over 40 routes was 0.705 and no route used a motorway; with the fitted model below (87 km/h on motorway edges without a stored speed, plus divisors and a junction delay) it is 0.844 and the median time ratio is 0.99. The stored speeds with those defaults alone give a median 74% of OSRM's travel time on routes where both take the same path (mean error 26%). A divisor per road type and 3.6 s per junction, fitted on 112–119 same-path routes, lowers the error on the held-out half to 6.6% (median ratio 0.98). The fitted values describe Dutch roads as OSRM models them and need a refit elsewhere. Written as `maxspeed`, they change little in OSRM itself (time ratio 0.93 with or without), which adds its own penalties.

**Section 11 (`T[0x13]` = 6 B): signposts.** Pointed to by `+T[0x09]+4`. Each entry is `u16` destination text, `u16` route-number text or 0, and a `u16` flag 0/1. 984 of 985 destination pointers resolve to strings, e.g. `norwich` / `a11`, `bury st. edmunds((a14))`, `london stansted airport`, `((m11))`. Used by 10–11% of class 0–1 segments, ~0% of residential ones (CD-ID 21594).

**Section 12 (DVD only): TMC.** Pointed to by `+0x14`: whole triples of u16 `(direction 6/7/8, location code, flags)`. Used by 95% of class 0 and 85% of class 1 segments. The codes are consecutive IDs, not pointers, and occur in the DVD-only blocks `0x17` and `0x19`. `0x19` holds TMC location names (`autobahndreieck treptow`, `schönefelder kreuz`). Empty on both CDs.

**Section 13 (DB-REL 34, `+0x16`): toll points.** Entries are 8 B, like section 10: `u32 BLOCK_ID` (always the tile's own), `u16` offset of a segment record, `u16` flag `0x1200` or `0x3200`. They come in pairs, one per flag, on consecutive class 0–2 segments of one road. On CD-ID 21594 they sit in 16 / 247 `0x01`, 23 / 426 `0x02` and 27 / 1,476 `0x03` tiles, and in 1 of 1,114 plain `0x00` tiles (2 of 60 sampled on DVD 21708). Every pair checked lies on a toll point: the Limerick Tunnel, M8 Fermoy, N25 Waterford bridge, M6 Ballinasloe, M7 Portlaoise, M4 Enfield, M3 Dunshaughlin and the Dublin East Link. The two flags are probably the two directions; not verified.

**Section 14 (DB-REL ≥ 23):** `{u16 text offset, u8 length, u8 type}`. Type 0 entries are two-letter name prefixes (`st`, `ki`, `ch`, …), i.e. a name search index.

**Not found:** lane counts or lane arrows. `+0x1D` bits 1–2 give only a coarse width category. The per-segment speed is `+0x0A` bits 0–4; how the route planner turns it into a cost is not traced (upstream's cost function `rpmod:6eae` is the candidate).
