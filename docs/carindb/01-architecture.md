# Part 1 — Verified Architecture

> **Status: ✅ VERIFIED** (byte-for-byte against `dataset/NAV_DB_21708.ISO`).
> Big-Endian throughout. This is the solid ground layer: filesystem, generic
> block layout, the superblock/schema, system blocks, and text encoding.
> Build freely on anything here.
>
> Source: `../CARINDB_BLUEPRINT_EN.md` §1–§5. Related: coordinates & records →
> [`02-geo.md`](02-geo.md); road-network parcels → [`03-road-network.md`](03-road-network.md).

---

## 1. File System Architecture (ISO Volume)

Standard ISO 9660 image, **2048 bytes/logical sector** (`4385374208 / 2048 = 2141296` exact).
No Mode 2 Form 2 / subheader: extracted files are already pure "user data".

```
Volume ID       : NAV_DB_21708
Volume Set      : CARIN
System ID       : DVD9_21708_5001
Publisher       : MapScape B.V.
Data Preparer   : Digital Maps
Created         : 2015-08-04 16:09:55
```

| Path | Size (bytes) | Function |
|---|---|---|
| `/ABSTRACT` | 848 | ASCII. Tool 5001, CD number, Navteq build (`eur_hw_her_bmw_14q4_20150721a_w`), line `Event Texts: carinet16s512.20080318` |
| `/BIBLIOGR` | 38 | `CD-ID 21708DB-REL 34BSW-REL 10 11` — DB version and minimum SW |
| `/COPYRIGH` | 622 | Continental Automotive GmbH copyright |
| `/CARINET` | 750,592 | "Event Texts" catalog (UI strings / event codes). **Separate block space** from `DB/` (block type `0x0066`) |
| `/DB/DB_0` | 2,147,429,888 | CARINdb, virtual window 0 |
| `/DB/DB_1` | 1,175,287,296 | CARINdb, virtual window 1 |
| `/DVD9/PADDING` | 4,096 | Padding for DVD9 layer break |
| `/TPD/TPD3.DIC` | 51 | TPD dictionary |
| `/TPD/NCCBEUFNM_EUW_20150804/` | — | *Third Party Data*: `INFO.PSC`, `<LANG>.LSC`, `<LANG>_n.CPR`, `ICONS/*.GIF`, `<LANG>/DBPOI/*.HTM`. Marketing/POI, **not** required for routing |

> `carinet16s512` in ABSTRACT independently confirms the CARIN addressing unit is **512** bytes ("s512").

> **CD discs differ.** On CD (e.g. Carminat CNI1, CD-IDs 2952 and 21594):
> - the database is a single `/carindb` file;
> - there is no `DB_0`/`DB_1` split;
> - the addressing unit is **2048** bytes. CD-ID 21594's ABSTRACT reads `carinet16s2048`.
>
> `BLOCK_ID >> 8` counts 2048-byte sectors and `UNCOMPRESSED_SIZE` counts 2048-byte sectors too. With that unit, the block chain covers 100% of the file with no gaps on both CDs; with 512 it breaks after the first block.

### 1.1 Virtual Address Space `DB_0` + `DB_1`

`DB_0` and `DB_1` form **a single sector space**. Each file spans a window of
`0x400000` sectors (= 2 GiB):

```
virtual_sector      = file_index * 0x400000 + local_sector
byte_offset_in_file = local_sector * 512
```

| File | Virtual Sectors | Notes |
|---|---|---|
| `DB_0` | `0x000000` .. `0x3FFED6` (0..4,194,198) | |
| *(hole)* | `0x3FFED7` .. `0x3FFFFF` (105 sectors) | **does not exist on disc**: 2 GiB alignment padding |
| `DB_1` | `0x400000` .. `0x62FFFB` (4,194,304..6,489,787) | first block: `BLOCK_ID = 0x4000002B` |

Proof: first sector of `DB_1` declares `BLOCK_ID.sector = 0x400000`. All block
pointers (e.g. `0x6273EC01` in block 3) resolve correctly only under this rule.

### 1.2 Physical Layout by Block Type

The block chain covers **100%** of both files (315,095 blocks, no gaps),
ordered in contiguous regions by type:

| Type | Blocks | Total Sectors | Virtual Sector Range |
|---|---:|---:|---|
| `0x12` | 1 | 1 | 0 |
| `0x13` | 1 | 1 | 2 |
| `0x07` | 1 | 4 | 3 |
| `0x0B` | 2 | 2 | 7..8 |
| `0x0A` | 2 | 8 | 9..16 |
| `0x0D` | 10 | 390 | 17..406 |
| `0x0C` | 4,537 | 175,452 | 407..175,858 |
| `0x0F` | 1,661 | 59,896 | 175,859..235,754 |
| `0x0E` | 74,247 | 2,472,332 | 235,755..2,708,086 |
| `0x11` | 921 | 26,973 | 2,708,087..2,735,059 |
| `0x10` | 9,518 | 351,452 | 2,735,060..3,086,511 |
| `0x08` | 117 | 10,367 | 3,086,512..6,452,109 *(scattered)* |
| `0x09` | 13,348 | 13,813 | 3,088,561..6,452,110 *(scattered)* |
| `0x06` | 2,688 | 48,122 | 3,090,039..3,138,161 |
| `0x00` | 91,756 | 2,623,033 | 3,157,624..5,780,761 |
| `0x04` | 80,825 | 222,948 | 5,780,762..6,003,709 |
| `0x03` | 6,740 | 82,673 | 6,003,936..6,086,608 |
| `0x02` | 3,580 | 30,560 | 6,086,698..6,117,257 |
| `0x01` | 2,710 | 10,022 | 6,117,309..6,127,330 |
| `0x16` | 14,661 | 228,221 | 6,127,713..6,355,933 |
| `0x15` | 4,511 | 70,953 | 6,356,247..6,427,199 |
| `0x1C` | 1,461 | 19,935 | 6,427,316..6,447,250 |
| `0x14` | 358 | 2,897 | 6,447,258..6,450,154 |
| `0x1D` | 172 | 1,949 | 6,450,159..6,452,107 |
| `0x1E` | 53 | 94 | 6,452,110..6,452,203 |
| `0x18` | 13 | 19 | 6,452,204..6,452,222 |
| `0x17` | 920 | 34,279 | 6,452,223..6,486,501 |
| `0x1B` | 1 | 1 | 6,486,502 |
| `0x1A` | 1 | 5 | 6,486,503..6,486,507 |
| `0x19` | 279 | 3,279 | 6,486,508..6,489,786 |

> **Type `0x05` does not exist** in this DB — and the root block explicitly omits it
> from its own type list (§3.1). Cross-confirmation of the root block read.

---

## 2. Generic Block Structure

Each block starts on a 512-byte boundary:

```
+0x00  BLOCK_ID          u32   (sector << 8) | length_in_sectors
+0x04  BLOCK_TYPE        u16
+0x06  COMPRESSION_FLAG  u8
+0x07  UNCOMPRESSED_SIZE u8    decompressed size in 512 B sectors (header included)
+0x08  SECTION_DESCRIPTOR[N]   N * { u16 offset, u16 count }
 ...   SERVICE_DATA            (block-type specific, up to the first section offset)
 ...   SECTION_0 .. SECTION_N-1
```

**Golden rule for offsets:** every `offset` in the descriptor, and every internal
pointer within the block, is **relative to the start of the *decompressed* block,
8-byte header included**. Therefore `payload_index = offset - 8`.

### 2.1 `COMPRESSION_FLAG`

| Value | Codec | Blocks | Verification |
|---:|---|---:|---|
| `0` | no compression | 15,984 | payload used as-is |
| `1` | **structure-aware bit-packing** | 96,011 | resolved → [`04-cf1-codec.md`](04-cf1-codec.md). Not dictionary compression: bit-packed fields parameterized by the superblock's `RECORD_SIZE_TABLE`. Predominant in types `0x00`,`0x15`,`0x16`,`0x1C`,`0x14`,`0x1D` |
| `2` | **zlib / RFC 1950** (`78 DA`) | 203,100 | `zlib.decompress(raw[8:])` yields exactly `us*512 - 8` bytes |

For `cf==2` the zlib stream starts **immediately after the 8-byte header**; the
section descriptor is *inside* the compressed payload.

### 2.2 Compiler Write Constraint

`UNCOMPRESSED_SIZE` is 8-bit ⇒ a block cannot exceed **255 sectors (130,560 bytes)**
once decompressed. Maximum observed: 96 sectors (49,152 bytes) — the original
compiler limits blocks to ~48 KiB. `BLOCK_ID.length` is 8-bit ⇒ max 255 sectors on
disc; max observed 70.

### 2.3 Python Struct

```python
import struct, zlib
from dataclasses import dataclass

SECTOR = 512
WINDOW = 0x400000          # sectors per DB_n file (2 GiB)

BLOCK_HDR = ">IHBB"        # BLOCK_ID, BLOCK_TYPE, COMPRESSION_FLAG, UNCOMPRESSED_SIZE
BLOCK_HDR_SIZE = 8         # struct.calcsize(BLOCK_HDR) == 8

SECTION_DESC = ">HH"       # offset, count   (offset relative to block start, header included)

@dataclass
class CarinBlock:
    sector: int            # absolute virtual sector
    length: int            # length on disc, in 512 B sectors
    type: int              # BLOCK_TYPE
    comp: int              # 0 = raw, 1 = bit-packed (CF=1), 2 = zlib
    usize: int             # decompressed size in 512 B sectors
    data: bytes            # decompressed block, 8-byte header included

    @classmethod
    def parse(cls, raw: bytes, sector: int) -> "CarinBlock":
        bid, btype, cf, us = struct.unpack_from(BLOCK_HDR, raw)
        if (bid >> 8) != sector:
            raise ValueError(f"BLOCK_ID sector {bid >> 8:#x} != {sector:#x}")
        length = bid & 0xFF
        if cf == 2:
            body = zlib.decompress(raw[BLOCK_HDR_SIZE:length * SECTOR])
        elif cf == 0:
            body = raw[BLOCK_HDR_SIZE:length * SECTOR]
        else:
            body = cf1.decode_block(raw, layout_table, db_rel)[BLOCK_HDR_SIZE:]   # see 04-cf1-codec.md
        return cls(sector, length, btype, cf, us, raw[:BLOCK_HDR_SIZE] + body)

    def sections(self, n: int):
        """n = number of descriptor entries (depends on BLOCK_TYPE, see 03-road-network.md §6)."""
        out = []
        for i in range(n):
            off, cnt = struct.unpack_from(SECTION_DESC, self.data, BLOCK_HDR_SIZE + 4 * i)
            out.append((off, cnt))
        return out

    def section_bytes(self, off: int, end: int) -> bytes:
        return self.data[off:end]          # offsets are already absolute within the block

def pack_block_id(sector: int, length: int) -> int:
    assert 1 <= length <= 255
    return (sector << 8) | length
```

---

## 3. Superblock — Root Block (Sector 0, `BLOCK_TYPE = 0x12`)

Absolute offset `0x00000000`, 1 sector (512 bytes), uncompressed.
The root **does not** contain pointers to "Node/Edge/Name tables": it holds the
database *schema*.

### 3.1 Byte-by-byte Map

```
00000000: 0000 0001   BLOCK_ID          -> sector 0, length 1
00000004: 0012        BLOCK_TYPE        = 0x12
00000006: 00 00       COMPRESSION_FLAG=0, UNCOMPRESSED_SIZE=0
00000008: 0060 0001   SECTION_DESCRIPTOR[0] = { offset 0x0060, count 1 }

--- SERVICE_DATA 0x0C .. 0x5F (Array of 8-byte structs: `{u32 BLOCK_ID, u16 offset, u16 count}`) ---
0000000C: 0000 0801   BLOCK_ID  -> sector 8, 1 sector   (type 0x0B, alphabetical index)
00000010: 000C        offset (0x0C)
00000012: 0012        count  (18)
00000014: 0000 0201   BLOCK_ID  -> sector 2, 1 sector   (type 0x13, CD info)
00000018: 0001        offset (0x01)
0000001A: 0022        count  (34) -> **Hijacked by `rpmod` as `DB-REL`!**
0000001C: 0000 000C   BLOCK_ID  -> sector 0, length 12
00000020: 0001        offset (1)
00000022: 0060        count  (96)
00000024: 0068 001F   BLOCK_ID  -> sector 104, length 31
00000028: 00A6        offset (0xA6) -> **Hijacked by `rpmod` as RST Start Offset!**
0000002A: 005D        count  (0x5D) -> **Hijacked by `rpmod` as RST Entry Count!**
0000002C: 0200 0001   BLOCK_ID  -> sector 512, length 1
00000030: 0000        offset (0)
00000032: 0000        count  (0)
00000034: 0063 5FAC   BLOCK_ID  (identical to 0x50)
00000038: 0926        offset
0000003A: F69C        count 
0000003C: 36AF 692D   BLOCK_ID
00000040: 1756        offset
00000042: 9F41        count
00000044: 0000 0701   BLOCK_ID  -> sector 7, 1 sector   (type 0x0B, alphabetical index #2)
00000048: 000C        offset
0000004A: 0012        count
0000004C: 021C 0019   BLOCK_ID
00000050: 0063 5FAC   BLOCK_ID  (identical to 0x34)
00000054: 0926        offset
00000056: F69C        count
00000058: 102D 96F6   BLOCK_ID
0000005C: 1424        offset
0000005E: A443        count

> **FIRMWARE INSIGHT (0x12 ROOT BLOCK)**: 
> The `SERVICE_DATA` is actually an array of 8-byte structures (`{u32 BLOCK_ID, u16 offset, u16 count}`). This struct layout is defined by a C-struct `GlobalBlockHeader` shared with other directory blocks (like `0x08`).
> The routing engine (`rpmod.asm:01b122` and clones in `dbq`, `dbpa`, `pbp`) accesses this block **exclusively** to read the `DB-REL` and the Record Size Table (RST). It reads `DB-REL` via a hardcoded offset at `+0x1A`. It reads the RST offset/count at `+0x28` / `+0x2A`. 
> All other fields in this array (e.g. `+0x1C`, `+0x24`, `+0x2C..+0x5F`) are **DEAD DATA** (ignored compiler artifacts from the shared struct) and are never read by the query engine.
> Furthermore, `rpmod` adds the `+0x28` offset (`0x00A6`) directly to the base pointer, completely **bypassing** `SECTION_0` at `+0x60`. `SECTION_0` and the `BLOCK_TYPE_LIST` are not parsed by the routing engine's RST override logic.

--- SECTION_0 @ 0x0060 (1 record, variable length) ---
00000060: 0000 0304   BLOCK_ID  -> sector 3, 4 sectors    (type 0x07, Country Info)
00000064: 0001        UNKNOWN (u16)
00000066: 0000        UNKNOWN (u16)
00000068: 0000 0001 .. 001E   BLOCK_TYPE_LIST: 30 x u16, block types present in DB
                              (0x00..0x1E, with 0x05 ABSENT)  -> 0x0068..0x00A3
000000A4: 0000        terminator / padding (u16)
000000A6: [ u16 section_type, u16 record_size ] * 93   RECORD_SIZE_TABLE -> 0x00A6..0x0219
                              IDs 0x01..0x5A contiguous, then 0x8A, 0x97, 0x9D
0000021A: 0000 0000 0000 ...  UNKNOWN_PADDING up to 0x03FF (zeros)
```

The superblock **spans sectors 0 and 1** (1024 bytes) despite declaring `length = 1`.
Sector 1 (`0x200`) is the tail of `RECORD_SIZE_TABLE` and has no header of its own.
**This is the only observed exception to the chaining rule** — when reading the
root, pass ≥1024 bytes and do NOT truncate to `length*512`.

### 3.2 `RECORD_SIZE_TABLE` (verified extract)

Pairs `(section_type, record_size_bytes)` starting at `0x00A6`. **This table
parameterizes the CF=1 decoder** — see [`04-cf1-codec.md`](04-cf1-codec.md) §9.11.3.

```
01:0x0C  02:0x10  03:0x08  04:0x1C  05:0x08  06:0x10  07:0x08  08:0x20
09:0x1A  0A:0x06  0B:0x74  0C:0x06  0D:0x04  0E:0x30  0F:0x08  10:0x08
11:0x3C  12:0x04  13:0x06  14:0x08  15:0x06  16:0x06  17:0x0174 18:0x1C
19:0x0160 1A:0x0C 1B:0x60  1C:0x54  1D:0x04  1E:0x08  1F:0x18  20:0x38
21:0x10  22:0x04  23:0x04  24:0x04  25:0x14  26:0x04  27:0x08  28:0x0C
29:0x0C  2A:0x04  2B:0x30  2C:0x08  2D:0x08  2E:0x20  2F:0x28  30:0x0C
31:0x08  32:0x1C  33:0x20  34:0x10  35:0x08  36:0x10  37:0x0A  38:0x04
39:0x04  3A:0x14  3B:0x04  3C:0x10  3D:0x34  3E:0x14  3F:0x18  40:0x0A
41:0x06  42:0x18  43:0x1C  44:0x04  45:0x10  46:0x64  47:0x10  48:0x04
49:0x04  4A:0x08  4B:0x14  4C:0x08  4D:0x0C  4E:0x1C  4F:0x04  50:0x10
51:0x28  52:0x10  53:0x04  54:0x04  55:0x08  56:0x18  57:0x0C  58:0x04
59:0x04  5A:0x02  8A:0x01  97:0x10  9D:0x16
```

> **RESOLVED (Dual Module Architecture: `db_pub` vs `rpmod`)**:
> The `RECORD_SIZE_TABLE` is read and handled independently by the two major modules of the OS-9 navigation stack, each with its own private Global Data Area (GDA, register `a6`):
>
> 1. **Map-Rendering (`pbp` / `db_pub`)**:
>    - Copies the disc's `RECORD_SIZE_TABLE` into its private static area at base offset `-$71cc(a6)`.
>    - Reads entry `idx` via `-(0x71cc - 2*idx)(a6)`.
>    - Hardcodes which section indices to use for rendering blocks:
>      - `0x00`: `T[0x05]`, `T[0x06]`, `T[0x08]`, `T[0x09]`, `T[0x0B]`, `T[0x0C]`, `T[0x0F]`, `T[0x10]`, `T[0x12]`, `T[0x13]`, `T[0x14]`, `T[0x15]`, `T[0x40]`, `T[0x4C]`, `T[0x59]`.
>      - `0x0E`: `T[0x2B]`, `T[0x2D]`, `T[0x41]`, `T[0x42]`, etc.
>      - `0x14`–`0x16`, `0x1C`–`0x1E`: `T[0x05]`, `T[0x15]`, `T[0x3A]`, `T[0x3B]`, `T[0x3C]`, `T[0x3D]`, `T[0x3F]`, `T[0x59]`.
>    - **Non-rendering blocks (`0x10`, `0x12`, etc.)**: In the dispatcher at `0x3698`, blocks `> 0x0E` not handled by dedicated decoders branch to `0x36d2`. Here, `pbp` calculates `size = sectors * 2048`, sets `val = 0`, and calls `bsr.w $6a06` (`memset(dest, 0, size)`), simply zeroing the buffer because the map renderer does not draw them.
>
> 2. **Routing Engine (`rpmod`)**:
>    - Operates in its own distinct GDA where the table base is **`-$7ee8(a6)`** with cell offset `-$7ee8 + (ID * 2)`.
>    - **Factory Defaults**: Subroutine `01af8a` pre-loads 66 hardcoded default constants for IDs `0x01` to `0x42` (from `-$7ee6(a6)` to `-$7e64(a6)`).
>    - **Dynamic Disc Override**: Subroutine `01b122` parses the Superblock. It reads `DB-REL` at `+0x1A`. If `DB-REL >= 18` (`0x12`), it reads descriptor `+0x28` `{u16 offset, u16 count}` and dynamically **overrides** the table cells in RAM (`move.w $2(a1), (a0, d0.l * 2)`) with the values from the disc's `RECORD_SIZE_TABLE` for all entries with `ID <= 0x42` (66 decimal).
>    - The rest of `rpmod` relies on this table (over 100 read occurrences) for record stride multiplication, division to calculate element counts (`divs.l d0, d1`), and parcel navigation. Entries with `ID > 0x42` (e.g. `0x4C`, `0x59`) are ignored by `rpmod`.

See §3.2.1 below for the full `BLOCK_TYPE → section_type[]` mapping. Types not covered by the CF=1 codec
(0x06, 0x09, 0x0C, 0x10) are documented empirically in [`03-road-network.md`](03-road-network.md) §6.

### 3.2.1 `BLOCK_TYPE → section_type[]` (recovered from firmware)

**Verification rule**: every confirmed row requires ≥ 2 independent sources
(firmware T[] reference + RST cross-check + optional empirical). Unverified
entries are marked `[HYP]`.

#### BLOCK_TYPE `0x00` — map drawing (CF=1 / CF=0)

N = 15 descriptor entries (`e0..e14`) in DB-REL 34; 13 in CC-93 (`e0..e12`).
Bbox at offset `0x44`. Source: `docs/fw/mips_decode_type00.asm`,
`docs/fw/mips_dec_B.asm`, `carin/parser/cf1.py`.

| slot | section_type | record_size | sources |
|---|---:|---:|---|
| prologue (verbatim) | `0x0b` | 116 B | MIPS `T[0x0b]`, RST[0x0b]=116, empirical |
| S0 (`e0`) | `0x40` | 10 B | MIPS `T[0x40]`, RST[0x40]=10, CF=0 empirical |
| S1 (`e1`) | `0x40` | 10 B | `dbq/pbp_clean.c`: Bounding Box / Delta limits |
| S2 (`e2`) | `0x40` | 10 B | (same T-entry, shared section_type) |
| S3 (`e3`) | `0x12` | 4 B | MIPS `T[0x12]`, RST[0x12]=4, CF=0 empirical |
| S4 (`e4`) | `0x08` | 32 B | road segments: nodes, next-segment-at-node pointers, shape pointer, length, bearings, class, one-way (see `03-road-network.md` §6.7) |
| S5 (`e5`) | `0x10` | 8 B | MIPS `T[0x10]`, RST[0x10]=8, CF=0 empirical |
| S6 (`e6`) | `0x06` | 16 B | MIPS `T[0x06]`, RST[0x06]=16, CF=0 empirical |
| S7 (`e7`) | `0x0c` | 6 B | Turtle Graphics Geometry (X,Y,Pen Flags) |
| S8 (`e8`) | — | — | no firmware reference found |
| S9 (`e9`) | `0x0f` | 8 B | MIPS `T[0x0f]`, RST[0x0f]=8, CF=0 empirical |
| S10 (`e10`) | `0x14` | 8 B | MIPS `T[0x14]`, RST[0x14]=8, CF=0 empirical |
| S11 (`e11`) | `0x13` | 6 B | MIPS `T[0x13]`, RST[0x13]=6, CF=0 empirical |
| S12 (`e12`) | `0x15` | 6 B | MIPS `T[0x15]`, RST[0x15]=6, CF=0 empirical |
| S13 (`e13`) | `0x4c` | 8 B | MIPS `T[0x4c]`, RST[0x4c]=8; DB-REL ≥ 21 |
| S14 (`e14`) | `0x59` | 4 B | `cf1.py` `T_REC_S14=0x59`, RST[0x59]=4; DB-REL ≥ 23 |

Structural T-table entries used by the type `0x00` CF=1 decoder (not section
record sizes): `0x05`=8 (descriptor base offset), `0x09`=26 (S4 tail-field
offset), `0x11`=60 (internal width).

#### BLOCK_TYPE `0x0E` — road parcels (CF=1 / CF=2)

N = 4 descriptor entries (`e0..e3`). No bbox. Source: `docs/fw/pbp_0x0E_decoder.asm`,
`carin/parser/cf1.py`, `scripts/oracle_0e.py` (67/67 blocks validated).

| slot | section_type | record_size | sources |
|---|---:|---:|---|
| prologue (verbatim) | `0x2b` | 48 B (40 on DB-REL 22) | firmware `T[0x2b]`, RST[0x2b]=48 |
| S0 (`e0`) | `0x2d` | 8 B | firmware `T[0x2d]`, RST[0x2d]=8, CF=1 empirical |
| S1 (`e1`) | `0x41` | 6 B (4 on DB-REL 22) | firmware `T[0x41]`, RST[0x41]=6, CF=1 empirical; read it from the table |
| S2 (`e2`) | `0x42` | 24 B | firmware `T[0x42]`, RST[0x42]=24, CF=1 empirical |

S2 record layout: `+0` i32 X, `+4` i32 Y = centre of the linked `0x00` tile;
`+8..+14` 4×u16 = even low/high and odd low/high house numbers (`0x7FFF` = none);
`+16` u32 `BLOCK_ID` of the `0x00` tile; `+20` u16 byte offset into its SECTION_4;
`+22` u16 SECTION_4 record count. S0 `A` points to the street name and `C` (if
non-zero) to a locality. See `03-road-network.md` §6.3.1.

#### BLOCK_TYPE `0x14`–`0x16`, `0x1C`–`0x1E` — scale layers (CF=0 / CF=1 / CF=2)

N = 6 descriptor entries (`e0..e5`). Bbox at offset `0x20`. The RoadRunner CF=1
dispatcher sends all six types to one decoder (`db_pub` `sub_004b88`, see
[`04-cf1-codec.md`](04-cf1-codec.md) §9.11.11). Source: `carin/parser/cf1/decoder_14.py`;
oracle `scripts/routing/oracle_14_16.py` passes on every block of these types on
CD-IDs 21708 and 21734, whatever the `COMPRESSION_FLAG`.

| slot | table id | record | records | written by |
|---|---:|---:|---|---|
| prologue (verbatim) | `0x3d` | 52 B | — | header, descriptor, bbox `0x20`, `0x30` u16 S3 selector, `0x32` u16 S3 shift |
| S0 (`e0`) | `0x3b` | 4 B | count + 1 | category, draw flag, S1/S2 offset (`02-geo.md` §8.4) |
| S1 (`e1`) | `0x3a` | 20 B | count + 1 | areas: name, S3 offset, u32, X, Y, `+0x10` (0), `+0x12` e5 offset |
| S2 (`e2`) | `0x3c` | 16 B | count + 1 | lines: name, S3 offset, u32, `+8` e4 offset, `+0x0a` u16, `+0x0c` e5 offset, `+0x0e` u16 |
| S3 (`e3`) | — | 4 or 8 B | count | vertices: 4 B local `u16 x, y` (shift = u16 at `0x32`) when u16 at `T[0x05]+T[0x3f]+0x10` ≠ 0, else 8 B absolute `i32` |
| e4 | `0x15` | 6 B | count | 3 × u16 (DB-REL ≥ 20 pass) |
| e5 | `0x59` | 4 B | count | name offset, u8, u8 (5 bits) (DB-REL ≥ 23 pass) |
| text | — | — | — | NUL-terminated strings after the last section |

The last record of S0, S1 and S2 is a terminator: S0's points at the end of the
last of S1/S2, S1/S2's S3 offset is the end of S3, and its name and X/Y are 0. On
every CF=0 and CF=2 block of both DVDs (20,227 blocks) S3 records are
4 B (shift 6 for `0x16`, 7 `0x15`, 8 `0x1C`, 9 `0x14`, 10 `0x1D`, 11 `0x1E`), and
S1 `+8/+12` X/Y is a point on the disc but often outside the block's own bbox.
The value 4 in S1 `+0x12` / S2 `+0x0c` (below the prologue, so no section) means
"no e5 record".

#### Types with empirical record sizes only (no CF=1 decoder — `[HYP]`)

| BLOCK_TYPE | slot | section_type | record_size | notes |
|---|---|---|---:|---|
| `0x06` POI | S0 (`e0`) | 0x32 | 28 B (20 B on DB-REL 22) | `02-geo.md` §8.1; only `T[0x32]` of the 5 candidates is 20 on CD-ID 2952 |
| `0x0C` | S0 (`e0`) | *confirmed* | 8 B | CF=2; Array of Bounding Boxes (Xmin, Ymin, Xmax, Ymax) |
| `0x0C` | S1 (`e1`) | *confirmed* | 24 B | CF=2; Road parcels (16B metadata + 8B local BBox) |
| `0x0C` | S3 (`e3`) | *confirmed* | 12 B | CF=2; Topology/Relation references |
| `0x0C` | S5 (`e5`) | *confirmed* | text | CF=2; String Blob (Latin-1 null-terminated) referenced by byte offset |
| `0x10` | S0 (`e0`) | `[HYP]` many | 8 B | POI index: name, type, locality, detail ptr (`02-geo.md` §8.1.1) |
| `0x10` | S1 (`e1`) | 0x2f | 40 B | POI detail: absolute X/Y + address/phone ptrs; `T[0x51]` is 28 on CD-ID 2952 |
| `0x09` | S0 (`e0`) | `[HYP]` many | 4 B | CF=0 empirical |
| `0x09` | S1 (`e1`) | - | ~488 B | CF=0 empirical; no RST match (variable-length blob) |

#### Unassigned section_type IDs

Of the 93 RST entries, **24 are confirmed** (or confirmed-structural) above;
**69 have no block_type assignment** yet:

```
01(12) 02(16) 03(8)  04(28) 07(8)  0a(6)  0d(4)  0e(48)
11(60) 16(6)  17(372) 18(28) 19(352) 1a(12) 1b(96) 1c(84)
1d(4)  1e(8)  1f(24) 20(56) 21(16) 22(4)  23(4)  24(4)
25(20) 26(4)  27(8)  28(12) 29(12) 2a(4)  2c(8)  2e(32)
2f(40) 30(12) 31(8)  32(28) 33(32) 34(16) 35(8)  36(16)
37(10) 38(4)  39(4)  3e(20) 43(28) 44(4)  45(16) 46(100)
47(16) 48(4)  49(4)  4a(8)  4b(20) 4d(12) 4e(28) 4f(4)
50(16) 51(40) 52(16) 53(4)  54(4)  55(8)  56(24) 57(12)
58(4)  5a(2)  8a(1)  97(16) 9d(22)
```

Format: `ID(size_in_bytes)`. Likely block type candidates for some IDs are noted
in `03-road-network.md` §6 (road parcels) and `02-geo.md` §8 (geo records).

### 3.3 Python Struct — Superblock

```python
SUPERBLOCK_FMT = ">IHBB HH"        # BLOCK_ID, TYPE, CF, US, sec0_offset, sec0_count
ROOT_ENTRY_FMT = ">IHH"            # BLOCK_ID of a 1st-level index + its descriptor

@dataclass
class Superblock:
    block: CarinBlock
    country_info: int              # BLOCK_ID (sector 3, type 0x07)
    cd_info: int                   # BLOCK_ID (sector 2, type 0x13)
    name_index: tuple              # BLOCK_ID of the two type 0x0B blocks (sectors 8 and 7)
    block_types: list              # block types present in the DB
    record_sizes: dict             # section_type -> record size in bytes

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Superblock":
        # CAUTION: the root declares length=1 but spans 2 sectors (1024 bytes).
        blk = CarinBlock.parse(raw, 0)
        d = raw[:1024]
        sec0_off, sec0_cnt = struct.unpack_from(">HH", d, 8)          # 0x0060, 1
        idx_a = struct.unpack_from(">I", d, 0x0C)[0]                  # 0x00000801
        cd    = struct.unpack_from(">I", d, 0x14)[0]                  # 0x00000201
        idx_b = struct.unpack_from(">I", d, 0x44)[0]                  # 0x00000701
        ctry  = struct.unpack_from(">I", d, sec0_off)[0]              # 0x00000304

        p = sec0_off + 8
        types = []
        while True:
            v = struct.unpack_from(">H", d, p)[0]
            if types and v <= types[-1]:
                break
            types.append(v); p += 2
        p += 2                                                        # terminator 0x0000
        sizes = {}
        while p + 4 <= len(d):
            st, rs = struct.unpack_from(">HH", d, p)
            if st == 0:
                break
            sizes[st] = rs; p += 4
        return cls(blk, ctry, cd, (idx_a, idx_b), types, sizes)
```

---

## 4. System Blocks

### 4.1 `0x13` — CD Info (sector 2, zlib)

Decompressed to 1024 bytes. After the header: a 2-section descriptor
`{0x0010, 1}`, `{0x001C, 1}`, then a 12-byte record, then ASCII text delimited by `0x00`:

```
"no label\0no description\0"
"\n1.  name:      eur_hw_her_bmw_14q4_20150721a_w.\n"
"2.  content:    europe (europe)\n"
"3.  oem:        bmw\n"
"4.  supplier:   navteq\n" ...
```

### 4.2 `0x07` — Country Info (sector 3, 4 sectors, uncompressed)

```
+0x00 header (8)
+0x08 SECTION_DESCRIPTOR[3] = {0x0174, 40}, {0x0264, 13}, {0x0382, 43}
+0x14 SERVICE_DATA (0x14..0x173)
      0x0614: 2FE27160  UNKNOWN (u32)
      0x0618: F1198000 BC7A5000 51198000 1C7A5000   RESERVED (4x i32)
              NOT the geographic bbox of the data: incompatible with any lon/lat calibration.
      followed by 12 records of 24 bytes, each repeating the same quartet
+0x174 SECTION_0: 40 records of 6 bytes   -> ">HHH" (country_id, seq_id, 0)
                  seq_id = 0x0734..0x075B, consecutive
+0x264 SECTION_1: 13 records of 20 bytes  -> ">IHHHHHHHH"
                  field 0 = BLOCK_ID (e.g. 0x6273EC01 -> DB_1), field 5 = country_id
+0x382 SECTION_2: 43 records  (dimension UNKNOWN)
+0x750 approx: country names, lowercase ISO-8859-1, delimiter 0x00:
      "österreich\0schweiz\0deutschland\0ceska republika\0españa\0danmark\0
       italia\0united kingdom\0norge\0nederland\0france\0belgië\0sverige\0"
```

> **Update (2026-09-28):** the repeated quartet is the root square of the spatial
> quadtree, not the data's extent: on CD-ID 21708 it is lon −75.00..214.91, lat
> −203.91..86.00, side `3 · 2^29`, and `3 · 2^29 / 2^14` is the 98,304-unit tile grid. The
> 24-byte records around it form the **layer directory**: `u32 BLOCK_ID` of a layer's
> `0x08` grid, the root square, and the layer's parameters. See `02-geo.md` §7.3.

### 4.3 `0x0B` — Alphabetical Index (sectors 7 and 8, 1 sector each)

```
+0x08 SECTION_DESCRIPTOR[1] = {0x000C, 18}
+0x0C 18 records of 12 bytes:  ">IHHHH"
      BLOCK_ID(u32) | key(u16) | offset(u16) | count(u16) | flags(u16)
```
Observed `key`: `0x6101 0x6201 0x6301 0x6401 0x6501 0x6601 0x6701 0x6801 0x6901
0x6C01 0x6D01 0x6E01 0xF601 0x6F01 0x7001 0x7201 0x7301 0x7501`
→ high byte = **ISO-8859-1 initial** (`a b c d e f g h i l m n ö o p r s u`),
low byte = prefix length (1). `offset`/`count` index SECTION_0 of the referenced
`0x0A` block (stride 8, verified).

### 4.4 `0x0A` — Country Table

Checked on all four discs (CD-ID 2952, 21594, 21708, 21734); tool `local/tools/country0a.py`.

| Disc | Blocks | Countries | Record size |
|---|---|---|---|
| CD-ID 2952 (DB-REL 22) | 1 (sector 5, plain) | 19 (England, Scotland and Wales are separate entries, all with country ID `0xDF`) | 44 B |
| CD-ID 21594 (DB-REL 34) | 1 (sector 4, plain) | 2 (Ireland, United Kingdom) | 56 B |
| DVD 21708, DVD 21734 | 2 (sectors 9 and 13, zlib → 5120 B) | 44 + a pseudo-country `europe` (ID `0x400`, code `eu`) in the first block only; the `0x0D` counts differ between the two blocks (meaning unknown) | 56 B |

```
+0x08 SECTION_DESCRIPTOR[4] = {S0,n}, {S1,n}, {0,0}, {S3,m}      (DVD 21708: {0x30,44},{0x190,44},{0,0},{0xB30,128})
S0: n records of 8 bytes, alphabetical by name -> ">HHI"
    NAME_OFF  (u16)  offset of the country name (lowercase, NUL-terminated) in this block
    LANGUAGE  (u16)  1 Dutch, 2 English, 3 French, 4 German, 5 Italian, 6 Spanish, 7 Swedish,
                     10 Danish, 11 Catalan, 12 Finnish, 14 Norwegian, 15 Portuguese, 18 Polish,
                     19 Czech, 20 Slovak, 21 Russian, 23 Slovenian, 24 Lithuanian, 25 Bosnian,
                     26 Croatian, 27 Latvian, 255 none. (Andorra is 0 on CD-ID 2952, 11 on the DVDs.)
    REC_OFF   (u32)  offset of the country record in S1
S1: n country records (below)
S3: m records of 12 bytes -> ">IHHHH"
    BLOCK_ID (u32) of a 0x11 block | offset | count | POI category | text base
    The root of a per-country, per-category POI-name trie in 0x11 (see below). The category is
    a 0x06 POI category code; "text base" is always NAME_OFF of the first S0 entry.
```
The `0x0B` block indexes S0 by initial letter (§4.3).

**Country record** (DB-REL 34: 56 bytes; DB-REL 22: the first 44 bytes, ending after `+0x2A`):

```
 off  size  field
 0x00   4   CITY_TRIE     BLOCK_ID of a 0x0D block (upstream read 0x02 u32 as a NAME_PTR;
 0x04   2                 offset in that block       it is this BLOCK_ID, offset and count)
 0x06   2                 count: the root of the country's city-name trie (see below), one
                          entry per initial letter
 0x08  16   four u32: 11, 22, 33, 44 on DB-REL 34; 111,111,111 × 1..4 on CD-ID 2952.
            The same 16 bytes are in the 0x13 build-info block. A placeholder or format
            signature, not country data
 0x18   2   S3_OFFSET     offset of the country's first S3 record (0 = none)
 0x1A   2   S3_COUNT
 0x1C   8   4 × u16: 500, 300, 1000, 500 for every country on every disc, 0 for `europe`.
            The firmware multiplies each by 100 (as it does segment lengths); what they
            mean is not known. Upstream's "default speeds in 0.1 km/h" is unconfirmed
 0x24   2   LEFT_HAND     1 only for Ireland and the United Kingdom (England, Scotland, Wales
                          on CD-ID 2952). Gibraltar, which drives on the right, has 0
 0x26   2   UNKNOWN       1 for be, cz, de, gi, li, lu, me, nl, at, ch, sk, rs; else 0
 0x28   2   COUNTRY_ID    the country's position in the English-name order of ISO 3166
                          (al 0x02, ad 0x05, at 0x0E, … gb 0xDF, va 0xE5), with Serbia (0xF5)
                          and Montenegro (0xF6) appended at the end
 0x2A   2   FLAGS2        4 on most countries without S3 entries (eastern Europe, the Nordics),
                          2 on `europe`, else 0
 --- DB-REL 34 only ---
 0x2C   2   COVERAGE      3 full, 1 reduced (by, md, al; ua and gi on DVD 21708 only), 0 `europe`
 0x2E   2   ISO_CC        ISO 3166-1 alpha-2 ("de", "at", "ie", "gb", "me")
 0x30   2   0
 0x32   2   REGION        "eu" on the DVDs, "--" on CD-ID 21594
 0x34   4   0
```

**Firmware.** Mk3 0127 reads the record in two places with identical code, `rpmod+0x46ff0` (the
route planner, behind an RPC stub) and `dbq+0x213f0` (database queries). Both find the record
through S0 (`REC_OFF`) and fill a 20-byte struct: the four `+0x1C` values × 100 as u32, a byte
`+0x24 == 0` (drives on the right), a byte `+0x26 != 0`, and `COUNTRY_ID`, read only when a
version number the firmware keeps is at least `0x15` (so it is 0 on older data). In `rpmod` the
right-hand byte is read back by a caller that returns it (`rpmod+0x2761c`), and it defaults to 1
when the lookup fails. No reader of the other fields was found; they may be used through the RPC.

`ISO_CC` is not what the CNI1 displays: with CD-ID 21594 the unit shows the international
vehicle registration code "IRL" for Ireland, not "ie". The firmware maps the country to that
code itself, probably from `COUNTRY_ID`. CD-ID 2952 has no code field at all.

#### 4.4.1 `0x0D`, `0x0F` and `0x11`: name tries

Both are letter tries in the same 12-byte record format as `0x0B` (§4.3):
`u32 BLOCK_ID | u8 letter | u8 leaf | u16 offset | u16 count | u16 flags (0)`.
With `leaf` = 0 the record points to the next level (`count` records at `offset` in that
block, usually a `0x0D`/`0x11` block); with `leaf` = 1 it points to `count` consecutive name
records in the target block. The letter `@` (0x40) marks the end of a name: `ash@` is the leaf
for exactly "ash", while `ash` leads on to longer names. A range is split only while it is
large, so leaves sit at depths 1 to 18. This is how the unit offers only the letters that can
still follow.

| Trie | Root | Leaves point to | Check (`local/tools/trie0d.py`, `trie11.py`) |
|---|---|---|---|
| `0x0D` city names | `0x0A` record `+0x00` (one per country) | `0x0C` city records (8 B, name offset first) | every leaf name starts with its prefix: United Kingdom 35,168, Ireland 62,964 (CD-ID 21594); England 26,692, Scotland 2,921 (CD-ID 2952) |
| `0x11` POI names | `0x0A` section 3 (one per country and category) | `0x10` POI index records (8 B: name offset, type, locality, detail pointer) | 302 / 302 (CD-ID 21594), 187 / 187 (CD-ID 2952) |
| `0x0F` road names | `0x0C` city record `+0x00` (one per city, below) | `0x0E` section 0 street records (8 B, §6.3) | 18,848 / 18,861 names under their prefix on 200 cities (CD-ID 21594; the 13 are one Irish range where `i` and `í` sort together); 30,437 / 30,437 on 300 cities (CD-ID 2952) |

The `0x11` categories are the POIs you can search by name: 20 attractions (Guinness Storehouse,
Madame Tussauds), 32 museums, 35 stadiums, 37 landmarks (Big Ben, Newgrange), 38 theme parks,
39 national parks, 49 a museum (CD-ID 2952 only), 52 airports (with IATA codes such as `dub`
and `ork` as alias records, flag `0x0100`), 53 ferry terminals and the Channel Tunnel,
58 border crossings.

**`0x0C` city records** (`local/tools/city0c.py FILE SECTOR`). Section 0 holds 8-byte entries in
alphabetical order: `u16 name offset, u16 flags, u16 post-town offset (0 = none), u16 pointer
into section 1` (e.g. `abbas itchen` → `winchester`). Section 1 records are 24 bytes on
DB-REL 34 and 20 on DB-REL 22:

```
+0x00 u32 BLOCK_ID of a 0x0F block \
+0x04 u16 offset                     |  root of the city's road-name trie
+0x06 u16 count                     /
+0x08 u16 offset into section 3, +0x0A u16 count: the city's own 0x11 POI tries
      (12-byte records like 0x0A section 3; categories 48, 56, 57 seen)
+0x0C u32 BLOCK_ID of a 0x00 tile, +0x10 u16 offset in it: the city centre, used when a
      city is chosen without a road
```
Section 5 holds variable-length brand lists (`renault`, `bp`, `shell`, `tesco`) with `0x11`
pointers; not decoded.

A street can be listed under more than one city, as separate `0x0E` records reached from
separate tries. On CD-ID 2952 a street on the border of two towns sits in a packed `0x0E` block
under one town and in a plain one under the neighbouring larger town. Editing one copy leaves
the other list unchanged.

**Renaming a street (tested on a CNI1, CD-ID 2952).** A street's name is stored in every city
list that carries it (plain or packed `0x0E`), in its word-reordered alias (flag `0x1000`, e.g.
`lane …`) and in the text of its `0x00` tile. Renaming all of them, keeping the new name in the
same sort position (so no trie range changes), works on the unit: the new name is listed and
selectable. An earlier rename of one copy only, which also broke that list's sort order, showed
the old name in the other city's list and crashed the unit when it was selected. Packed blocks can
be edited without re-encoding by swapping letters whose text codes have the same total bit length
(`local/tools/textsplice.py`).

A rename that moves the street to another place in the list also works, once the list is re-sorted
and the city's `0x0F` leaves are rebuilt. The rule the disc's compiler used reproduces every
city's `0x0F` trie on both CDs (49,310 and 95,543 cities; `local/tools/triebuild.py`):

1. At each level, group the sorted names by their next letter, ignoring accents (`@` when the
   name ends there). The lists are sorted the same way.
2. A group whose records all sit in one target block becomes a leaf. A group spanning several
   blocks is split again on the following letter.
3. A group gets one trie record per letter that occurs in it, all pointing at the whole group.
   `ä`, `ö` and `ü` count as letters in their own right. Any other accented letter also brings
   its plain letter, which comes first (`á` alone gives `a`, `á`).

A made-up city also works. Renaming a city in place (keeping its sort position, so the country's
`0x0D` leaf still covers it), giving its street records new names, re-encoding the packed `0x0E`
block with `encode_type0E`, and writing the city's `0x0F` root from the rule alone gives a city
that can be selected, with the new street list, and a street that can be chosen as a destination.
The unit's destination line then shows the **old** street and city names ("street, locality"):
it doesn't take them from the list that was searched, but from another copy of the road's name.
That could be the post town's `0x0E` list (where `C` gives the locality) or the `0x00` tile text,
and neither was changed. The `0x0F` rule does not rebuild the `0x0D` city tries: these split some
groups that sit in one block (open).

The destination line comes from the map: re-encoding the `0x00` tiles with `encode_type00` and
changing the street name and locality that section 2 points to (`+0` street, `+2` locality) makes
the destination screen show the new names, with the post town's initial in front of the locality
(`T.-CUSTOM` for a place whose `0x0C` post town is Truro). The same names show when the road is
picked on the map. A name blob must end on the NUL that closes its last string, as every blob on
the discs does: the unit's decode buffer is not zeroed, and without that NUL the last name ran on
into leftover bytes (`HELLO WORLD ü $°%ú`).

Once a destination with a post town is set (the `T.` in `T.-CUSTOM`), the CNI1's street
selection lists the post town's streets (its whole `0x0E` list, e.g. Truro's 1,443 entries with
their localities: `a30, blackwater`), not those of the city that was picked; picking the city
again brings its own list back. This is the unit's normal behaviour (checked on an unedited
village), so a rename meant to be found this way must also be made in the post town's list.

**Moving a block (tested on a CNI1, CD-ID 2952).** A packed `0x00` tile was copied to the end of
`carindb` (the file grew by 3 sectors; the `CDI` directory and `CDI/PD` moved up behind it, with
the root directory, the `CDI` directory, both path tables and the PVD volume size patched), its
old sectors were zeroed, and every pointer to it was rewritten. The unit draws, searches and
routes the area as before, including routes that cross into the tile. So the firmware reaches
blocks only through their `BLOCK_ID`s, never by position in the chain, and `carindb` can grow.
A scan of every block on the disc (packed ones decoded) for that tile's `BLOCK_ID` found these
pointer kinds and nothing else (`local/tools/refs.py`):

| Holder | Field | Count for this tile |
|---|---|---|
| `0x0E` street directory | S2 `+16`, the street's segment run | 29 |
| Neighbouring `0x00` tiles | slot 6 `+8`, tile-edge twin | 34 |
| Neighbouring `0x00` tiles | slot 9, neighbour list | 5 |
| `0x0C` city record | S1 `+0x0C`, city centre | 2 |
| `0x10` POI details | section 4 (8 B records) `+0`, the POI's road | 3 |
| `0x09` spatial-index cell | tile list | 1 |
| `0x04` house numbers | header `+12` | 1 |
| The tile itself | header `+0`; slot 10 (and slot 13) own-tile entries | 1 + 12 |

`0x03` slot 8 can also point at a `0x00` tile (not for this one), and `0x10` section 1
(20 B records) `+8` does for a few tiles. A tile's header points outwards at `+80` (its `0x04`
block) and `+84` (its `0x03` parent); those don't change when the tile moves.

### 4.5 `CARINET` — Event Text Catalog (independent block space)

```
+0x00 BLOCK_ID 0x00000002  (sector 0, 2 sectors = 1024 bytes)
+0x04 BLOCK_TYPE 0x0066    CF=0  US=0
+0x08 SECTION_DESCRIPTOR[4] = {0x001C,2}, {0x0034,49}, {0x01C4,3}, {0x01CA,14}
+0x34 SECTION_1: 49 records of 8 bytes -> ">IHBB" reinterpreted as:
      first_id(u24) | count(u8) | limit(u16) | group(u8) | 0(u8)
```
`group` = 0,1,2,3,4,5,6,7,0x0A,0x0C,0x0F,0x11 → language / text family index.

### 4.6 `0x0C` — Administrative Parcel (CF=2 zlib)

The `0x0C` block contains administrative region geometry and localized toponyms, decompressed generically via zlib. It is actively requested and processed by the query engine (`dbc.asm:001c38` requests block type `0x0C` explicitly).

*   **S0 (8 bytes/record)**: Serves as a translation layer mapping the `C` field logical IDs (from `0x0E` S0 records) to metadata or node references.
*   **S1 (24 bytes/record)**: Hypothesis based on dimensions: represents the administrative hierarchy (e.g. Region -> City -> District). The 24-byte size suggests an OS-9 tree-node struct.
*   **S3 (12 bytes/record)**: Localized name mapping / metadata.
*   **Name Blob**: The final section of the block (likely S4 or S5) is hypothesized to hold the actual null-terminated string bytes, mirroring the structure used in `0x0E`.

---

## 5. Text Encoding (Name Table)

**Verified**: no character compression, no custom charset (for uncompressed text;
CF=1 blocks use a dedicated prefix encoder — see [`04-cf1-codec.md`](04-cf1-codec.md) §9.11.5).

* Encoding: **ISO-8859-1 / Latin-1**.
  `0xF6 = ö` ("österreich"), `0xEB = ë` ("belgië"), `0xF1 = ñ` ("españa"), `0xED = í`.
* All strings are **lowercase** (uppercase rendering is done by firmware).
* Terminator: `0x00`. Strings are packed into contiguous blobs at block end.
* Retrieval: records point to the blob with a `u16` offset relative to the current block
  (used in `0x0C`/`0x0E` parcels).

> **RESOLVED (2026-09-28, PR #13)**: there is no 32-bit `NAME_PTR` with a segment half. The
> country record in `0x0A` starts with a `u32 BLOCK_ID`, `u16 offset`, `u16 count`: the root of the
> country's `0x0D` city-name trie (§4.4, §4.4.1). Read at `+0x02`, those bytes look like
> "`high16` = low 16 bits of a `0x0D` `BLOCK_ID`, `low16` = offset", which is where the earlier
> "segments" (`6C2E 9A30 F931 CA2F 112E 12A6`) and the "16-bit truncation vulnerability" came
> from. Read at `+0x00` the `BLOCK_ID` is complete (87 / 87 roots are `0x0D` blocks on DVD 21708).

```python
def carin_str(buf: bytes, off: int) -> str:
    end = buf.index(b"\x00", off)
    return buf[off:end].decode("latin-1")

def encode_carin_str(s: str) -> bytes:
    return s.lower().encode("latin-1", errors="replace") + b"\x00"
```

### Where names live (index)

| Type | Textual content |
|---|---|
| `0x0C`, `0x0E` | toponyms / municipalities (≈3,600 distinct strings per sample) |
| `0x10`, `0x17`, `0x19` | odonyms (street names) |
| `0x15` | municipalities / hamlets |
| `0x16` | islands, lakes, watercourses, city labels |
| `0x14`, `0x1C`, `0x1D`, `0x1E` | seas, oceans, regions, major cities (multilingual) |
| `0x06` | POI brands |
| `0x07`, `0x0A` | country names |

## Note on 0x00 vs 0x0E Geometry
The database splits the road network into two distinct layers to save runtime memory:
1. **0x0E (street-name directory)**: Maps each street name (and locality) to runs of road segments in `0x00` tiles, with house-number ranges. It stores no geometry and no topology of its own (see `03-road-network.md` §6.3.1; the earlier "routing graph / bounding boxes" reading came from treating house numbers as coordinate deltas).
2. **0x00 (Map Drawing)**: Contains the high-resolution, continuous polylines for actual map rendering on the LCD. Loaded dynamically only for regions currently on screen.
