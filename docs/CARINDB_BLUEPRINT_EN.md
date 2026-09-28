# CarinDB Binary Blueprint

> **📂 Agent-oriented split:** this monolith is also available as task-scoped parts
> under [`docs/carindb/`](carindb/README.md) — architecture, geo, road network,
> the CF=1 codec, falsified hypotheses, roadmap, and toolchain. Load the relevant
> part instead of the whole file when working on a specific task. This document
> remains the authoritative single source.

> Analyzed media: `dataset/NAV_DB_21708.ISO` — BMW MK4 / CARiN, CD-ID 21708, compile date 2015-08-04.
> All values are **Big-Endian**. Every statement in this document has been verified
> against the dump; what has not been verified is marked `UNKNOWN` / `RESERVED`.
> Dataset disc images and firmware dumps are available on [Google Drive](https://drive.google.com/drive/folders/1KZH93y9ltZBkkjlIm-hBnoqKcCdnsqJa?usp=sharing).

---

## ⚑ `COMPRESSION_FLAG = 1` — **RESOLVED** (2026-09-15)

The codec covering 96,011 blocks (30% of the disc) that had resisted six
algorithm families and over 650 parameter variants **is not a compression codec**.
It is **structure-driven bit-packing tailored to the block structure**:
each section has its own decoder that reconstructs fixed-size records
by reading minimal-width fields from an MSB-first bitstream, and converts
record indices into absolute offsets. Record sizes come from the
superblock's `RECORD_SIZE_TABLE` (§3.2), which previously appeared inert.

The decoder was found in the navigation unit's original firmware: module `pbp`
of the CARIN CC-93 (m68k/OS-9) and module `db_pub` of Mk3/RR (MIPS32/OS-9000).

**Verification**: 1,200 `CF=1` blocks of type `0x00` decoded, 1,200 with a readable
name blob consistent with the block's bounding box — El Hierro, Algarve,
Alentejo, with their respective actual street names and real road codes.

→ **§9.11** for the complete format, primitives, listings, and tools.
Implementation in `carin/parser/cf1.py`.

## 0. Corrections to Forum Notes (`dataset/context.md`)

| Forum Claim | Dump Verification | Outcome |
|---|---|---|
| "1 sector = 2048 bytes" | `BLOCK_ID.sector * 512 == offset` for **315,095** blocks out of 315,095 | ❌ **The CARINdb sector is 512 bytes**, not 2048. 2048 is the *ISO* sector, not the DB sector |
| "block from 1 to 8 sectors" | observed lengths 1..70 | ❌ length field = 1 byte, maximum observed 70 sectors (35 KiB) |
| "BLOCK_ID = 0x01030000 → block #3" | `0x00000304` = sector 3, 4 sectors | ⚠️ forum example inverted (little-endian); the rule `sector<<8 \| len` is correct |
| "UNCOMPRESSED_SIZE" (1 byte) | `us*512 == len(payload)+8` across all compressed blocks | ✅ expressed **in 512 B sectors**, not in bytes |
| "Sector 0 = character set" | sector 0 = block type `0x12` (root) | ❌ it is the **root/superblock** |
| "Sector 1 = CD info" | CD-info block is at **sector 2**, type `0x13`, zlib | ⚠️ off-by-one |

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
| `/ABSTRACT` | 848 | ASCII text. Tool 5001, CD number, Navteq build name (`eur_hw_her_bmw_14q4_20150721a_w`), line **`Event Texts: carinet16s512.20080318`** |
| `/BIBLIOGR` | 38 | `CD-ID 21708DB-REL 34BSW-REL 10 11` — DB version and minimum SW |
| `/COPYRIGH` | 622 | Continental Automotive GmbH copyright |
| `/CARINET` | 750,592 | "Event Texts" catalog (UI strings / event codes). **Separate block space** from `DB/` (block type `0x0066`) |
| `/DB/DB_0` | 2,147,429,888 | CARINdb, virtual window 0 |
| `/DB/DB_1` | 1,175,287,296 | CARINdb, virtual window 1 |
| `/DVD9/PADDING` | 4,096 | Padding for DVD9 layer break |
| `/TPD/TPD3.DIC` | 51 | TPD dictionary |
| `/TPD/NCCBEUFNM_EUW_20150804/` | — | *Third Party Data*: `INFO.PSC`, `<LANG>.LSC`, `<LANG>_n.CPR`, `ICONS/*.GIF`, `<LANG>/DBPOI/*.HTM`. Marketing/POI contents, **not** required for routing |

> `carinet16s512` in the ABSTRACT file is independent confirmation that the CARIN
> addressing unit is **512** bytes ("s512").

### 1.1 Virtual Address Space `DB_0` + `DB_1`

`DB_0` and `DB_1` form **a single sector space**. Each file spans a window of
`0x400000` sectors (= 2 GiB):

```
virtual_sector = file_index * 0x400000 + local_sector
byte_offset_in_file = local_sector * 512
```

| File | Virtual Sectors | Notes |
|---|---|---|
| `DB_0` | `0x000000` .. `0x3FFED6` (0..4,194,198) | |
| *(hole)* | `0x3FFED7` .. `0x3FFFFF` (105 sectors) | **does not exist on disc**: 2 GiB alignment padding |
| `DB_1` | `0x400000` .. `0x62FFFB` (4,194,304..6,489,787) | first block: `BLOCK_ID = 0x4000002B` |

Proof: the first sector of `DB_1` declares `BLOCK_ID.sector = 0x400000`, not 0 and not 4,194,199.
All block pointers (e.g. `0x6273EC01` in block 3) resolve correctly only under
this rule.

### 1.2 Physical Layout by Block Type

The block chain covers **100%** of both files (315,095 blocks, no gaps).
The DB is ordered in contiguous regions by type:

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

**Golden rule for offsets:** every `offset` in the descriptor, and every internal pointer
within the block, is **relative to the start of the *decompressed* block, 8-byte header included**.
Therefore `payload_index = offset - 8`.

### 2.1 `COMPRESSION_FLAG`

| Value | Codec | Blocks | Verification |
|---:|---|---:|---|
| `0` | no compression | 15,984 | payload used as-is |
| `1` | **structure-aware bit-packing** | 96,011 | **resolved, §9.11**: not dictionary compression but bit-packed fields, parameterized by the superblock's `RECORD_SIZE_TABLE`. Decoder in `carin/parser/cf1.py`. Predominant in types `0x00`,`0x15`,`0x16`,`0x1C`,`0x14`,`0x1D` |
| `2` | **zlib / RFC 1950** (`78 DA`) | 203,100 | `zlib.decompress(raw[8:])` yields exactly `us*512 - 8` bytes |

For `cf==2` the zlib stream starts **immediately after the 8-byte header**; the section descriptor
is *inside* the compressed payload.

### 2.2 Compiler Write Constraint

`UNCOMPRESSED_SIZE` is 8-bit ⇒ a block cannot exceed **255 sectors (130,560 bytes)**
once decompressed. Maximum observed: 96 sectors (49,152 bytes) — in practice the
original compiler limits blocks to 48 KiB.
`BLOCK_ID.length` is 8-bit ⇒ maximum 255 sectors on disc; maximum observed 70.

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
            body = cf1.decode_block(raw, layout_table, db_rel)[BLOCK_HDR_SIZE:]   # §9.11
        return cls(sector, length, btype, cf, us, raw[:BLOCK_HDR_SIZE] + body)

    def sections(self, n: int):
        """n = number of descriptor entries (depends on BLOCK_TYPE, see §6)."""
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
The root **does not** contain pointers to "Node/Edge/Name tables": it contains the database *schema*.

### 3.1 Byte-by-byte Map

```
00000000: 0000 0001   BLOCK_ID          -> sector 0, length 1
00000004: 0012        BLOCK_TYPE        = 0x12
00000006: 00 00       COMPRESSION_FLAG=0, UNCOMPRESSED_SIZE=0
00000008: 0060 0001   SECTION_DESCRIPTOR[0] = { offset 0x0060, count 1 }

--- SERVICE_DATA 0x0C .. 0x5F : list of first-level index blocks ---
0000000C: 0000 0801   BLOCK_ID  -> sector 8,  1 sector   (type 0x0B, alphabetical index)
00000010: 000C 0012   copy of that block's SECTION_DESCRIPTOR { 0x000C, 18 }
00000014: 0000 0201   BLOCK_ID  -> sector 2,  1 sector   (type 0x13, CD info)
00000018: 0001 0022   RESERVED (4 bytes)
0000001C: 0000 000C   RESERVED (4 bytes)
00000020: 0001 0060   RESERVED (4 bytes)
00000024: 0068 001F   RESERVED (4 bytes)
00000028: 00A6 005D   RESERVED (4 bytes)
0000002C: 0200 0001   RESERVED (4 bytes)
00000030: 0000 0000   RESERVED (4 bytes)
00000034: 0063 5FAC   RESERVED (4 bytes)   \  identical to field at 0x50
00000038: 0926 F69C   RESERVED (4 bytes)   /
0000003C: 36AF 692D   RESERVED (4 bytes)
00000040: 1756 9F41   RESERVED (4 bytes)
00000044: 0000 0701   BLOCK_ID  -> sector 7,  1 sector   (type 0x0B, alphabetical index #2)
00000048: 000C 0012   copy of SECTION_DESCRIPTOR { 0x000C, 18 }
0000004C: 021C 0019   RESERVED (4 bytes)
00000050: 0063 5FAC   RESERVED (4 bytes)   \  identical to field at 0x34
00000054: 0926 F69C   RESERVED (4 bytes)   /
00000058: 102D 96F6   RESERVED (4 bytes)
0000005C: 1424 A443   RESERVED (4 bytes)

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

File `DB_0` then contains the CD-info block at sector 2 (`0x400`) and the Country-Info
block at sector 3 (`0x600`): **the superblock spans sectors 0 and 1**, i.e. 1024 bytes,
despite declaring `length = 1`. Sector 1 (`0x200`) is the tail of the `RECORD_SIZE_TABLE`
and has no header of its own. This is the only observed exception to the chaining rule.

### 3.2 `RECORD_SIZE_TABLE` (verified extract)

Pairs `(section_type, record_size_bytes)` starting at `0x00A6`:

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

> **UNKNOWN**: the mapping `BLOCK_TYPE → list of section_types` was not found
> in any block. The firmware likely hardcodes it. Actual record sizes were
> instead derived empirically (§6) and should be used as the primary reference.

### 3.3 Python Struct — Superblock

```python
SUPERBLOCK_FMT = ">IHBB HH"        # BLOCK_ID, TYPE, CF, US, sec0_offset, sec0_count
# struct.calcsize(SUPERBLOCK_FMT) == 12

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
        # Pass at least 1024 bytes and DO NOT truncate to length*512 (see §3.1).
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

Decompressed to 1024 bytes. Following the header: a 2-section descriptor
`{0x0010, 1}`, `{0x001C, 1}`, then a 12-byte record, then **ASCII text
delimited by `0x00`**:

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
              NOT the geographic bbox of the data (see §7): values are
              incompatible with any lon/lat calibration found.
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

### 4.3 `0x0B` — Alphabetical Index (sectors 7 and 8, 1 sector each)

```
+0x08 SECTION_DESCRIPTOR[1] = {0x000C, 18}
+0x0C 18 records of 12 bytes:  ">IHHHH"
      BLOCK_ID(u32) | key(u16) | offset(u16) | count(u16) | flags(u16)
```
Observed `key`: `0x6101 0x6201 0x6301 0x6401 0x6501 0x6601 0x6701 0x6801 0x6901
0x6C01 0x6D01 0x6E01 0xF601 0x6F01 0x7001 0x7201 0x7301 0x7501`
→ high byte = **ISO-8859-1 initial** (`a b c d e f g h i l m n ö o p r s u`),
low byte = prefix length (1).
`offset`/`count` index SECTION_0 of the referenced `0x0A` block
(stride 8, verified: `0x30 +1*8 = 0x38`, `0x38 +4*8 = 0x58`, …).

### 4.4 `0x0A` — Country Table (sectors 9 and 13, 4 sectors, zlib → 5120 bytes)

```
+0x08 SECTION_DESCRIPTOR[4] = {0x0030,44}, {0x0190,44}, {0x0000,0}, {0x0B30,128}
+0x30  SECTION_0: 44 records of  8 bytes -> ">HHI"  (key, count, ptr-to-SECTION_1)
+0x190 SECTION_1: 44 records of 56 bytes -> country record (below)
+0xB30 SECTION_3: 128 records of 12 bytes -> ">IHHHH" block references
                  BLOCK_ID | offset | count | subtype | group
```

**Country record (56 bytes), verified across all 44:**

```
 off  size  field
 0x00   2   UNKNOWN (always 0x0000)
 0x02   4   NAME_PTR      (u32) — high16 = name segment, low16 = offset. 6 distinct
                          segments observed: 6C2E 9A30 F931 CA2F 112E 12A6
 0x06   2   UNKNOWN (u16) — 0x0006..0x0037
 0x08   4   0x0000000B    constant across all records
 0x0C   4   0x00000016    constant
 0x10   4   0x00000021    constant
 0x14   4   0x0000002C    constant (= 44 = number of countries)
 0x18   2   SEC3_OFFSET   offset in SECTION_3 (0 = no entry)
 0x1A   2   SEC3_COUNT    number of 12-byte records
 0x1C   2   0x01F4 (500)  \
 0x1E   2   0x012C (300)   |  DEFAULT_SPEED[4] — constants in this DB
 0x20   2   0x03E8 (1000)  |  (unit: presumably 0.1 km/h; UNKNOWN)
 0x22   2   0x01F4 (500)  /
 0x24   4   FLAGS         0x00000000 / 0x00000001 / 0x00010000
                          **0x00010000 only for `ie` and `gb`** -> left-hand traffic
 0x28   2   COUNTRY_ID    id used throughout the DB (at=0x0E, be=0x15, cz=0x38,
                          de=0x51, dk=0x39, es=0xC4, fr=0x49, gb=0xDF, it=0x69,
                          nl=0x96, no=0xA0, ch=0xCD, se=0xCC, …)
 0x2A   2   FLAGS2        0x0000 or 0x0004
 0x2C   2   COVERAGE      3 = full coverage, 1 = reduced coverage
                          (1 for by, md, al, ua, gi, mc… )
 0x2E   2   ISO_CC        2 chars ISO-3166-1 alpha-2 ASCII: "ad","be","de",…
 0x30   2   UNKNOWN (0x0000)
 0x32   2   REGION        "eu"
 0x34   4   UNKNOWN (0x00000000)
```

Consistency check of `SEC3_OFFSET/COUNT`:
`ad` 0x0B30+2·12 = 0x0B48 = `be`; `be` 0x0B48+8·12 = 0x0BA8 = `cz`;
`cz` 0x0BA8+8·12 = 0x0C08 = `dk`; `de` 0x0C68+9·12 = 0x0CD4 = `es`. ✅

```python
COUNTRY_FMT = ">H I H 4I HH 4H I H H H 2s H 2s I"
# better to use explicit offsets:
COUNTRY_RECORD_SIZE = 56
def parse_country(d, off):
    name_ptr  = struct.unpack_from(">I", d, off + 0x02)[0]
    sec3_off, sec3_cnt = struct.unpack_from(">HH", d, off + 0x18)
    speeds    = struct.unpack_from(">4H", d, off + 0x1C)
    flags     = struct.unpack_from(">I",  d, off + 0x24)[0]
    cid       = struct.unpack_from(">H",  d, off + 0x28)[0]
    coverage  = struct.unpack_from(">H",  d, off + 0x2C)[0]
    iso_cc    = d[off + 0x2E: off + 0x30].decode("latin-1")
    region    = d[off + 0x32: off + 0x34].decode("latin-1")
    return dict(name_ptr=name_ptr, sec3=(sec3_off, sec3_cnt), speeds=speeds,
                left_hand_traffic=bool(flags & 0x00010000), country_id=cid,
                coverage=coverage, iso_cc=iso_cc, region=region)
```

### 4.5 `CARINET` — Event Text Catalog (independent block space)

```
+0x00 BLOCK_ID 0x00000002  (sector 0, 2 sectors = 1024 bytes)
+0x04 BLOCK_TYPE 0x0066    CF=0  US=0
+0x08 SECTION_DESCRIPTOR[4] = {0x001C,2}, {0x0034,49}, {0x01C4,3}, {0x01CA,14}
+0x34 SECTION_1: 49 records of 8 bytes -> ">IHBB" reinterpreted as:
      first_id(u24) | count(u8) | limit(u16) | group(u8) | 0(u8)
```
Chain verified: `0x25+0x20=0x45`, `0x45+0x20=0x65`, … `0xA5+0x1A=0xBF`, … ✅
`group` = 0,1,2,3,4,5,6,7,0x0A,0x0C,0x0F,0x11 → language / text family index.

---

## 5. Text Encoding (Name Table)

**Verified**: no character compression, no custom charset.

* Encoding: **ISO-8859-1 / Latin-1**.
  `0xF6 = ö` ("österreich"), `0xEB = ë` ("belgië"), `0xF1 = ñ` ("españa"), `0xED = í`.
* All strings in the DB are **lowercase** (uppercase rendering is performed by the firmware).
* Terminator: `0x00`. Strings are packed into contiguous blobs at the end of the block.
* Retrieval: records point to the blob with a 32-bit `NAME_PTR`
  (`high16` = segment, `low16` = offset within segment) or with a `u16` relative
  to the current block (used in `0x0C`/`0x0E` parcels, see §6.3).

> **UNKNOWN**: the resolution of the `high16` of `NAME_PTR` (the 6 segments `6C2E 9A30 F931
> CA2F 112E 12A6`) has not been determined. It does not correspond to a `BLOCK_ID`.

```python
def carin_str(buf: bytes, off: int) -> str:
    end = buf.index(b"\x00", off)
    return buf[off:end].decode("latin-1")

def encode_carin_str(s: str) -> bytes:
    return s.lower().encode("latin-1", errors="replace") + b"\x00"
```
---

## 6. Node / Edge / Parcel — Road Network Tables

CARINdb **does not have** global Node and Edge tables at fixed offsets.
The network is partitioned into *parcels* (blocks `0x0C`, `0x0E`, `0x10`, `0x0F`, `0x11`),
each with its own local sections and 16-bit internal pointers within the block.

### 6.1 Descriptor Arity and Record Sizes (empirically derived)

Sampled 40 blocks per type; `~n` = average approximate size (section with
variable records or padding).

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

> `0x11`, `0x14`, `0x15`, `0x16`, `0x1C`, `0x1D`, `0x1E` are not in the table: the
> majority of their blocks use `COMPRESSION_FLAG = 1` (decodable, §9.11).

### 6.2 Types `0x00`–`0x03`: Same Schema (15–16 sections)

They occupy **2.9 GB out of 3.3 GB** of the database. The identical schema of `0x00`, `0x01`,
`0x02`, `0x03` with separate blocks per region (see §1.2) suggests **different levels of detail
of the same structure** (`0x00` = finest level, 91,756 blocks; `0x01` = coarser,
2,710 blocks). Recurring sections of 10, 8, 16, 6, and 4 bytes are compatible with
lists of nodes/edges/geometries, but **field semantics have not been verified**
and must not be assumed.

### 6.3 Type `0x0E` (74,247 blocks) — Main Parcel

```
+0x08 SECTION_DESCRIPTOR[3 used out of 10] e.g. {0x0030, 1169}, {0x24B8, 531}, {0x312C, 772}
+0x14 UNKNOWN_PADDING (20 bytes, zeros)
+0x28 SERVICE_DATA (8 bytes)
+0x30 SECTION_0: 8-byte records  ">HBBHH"
      A(u16)  FLAGS(u8)  B(u8)  C(u16)  D(u16)
```
Verified on sample:
* `D` is a **pointer to SECTION_1** and advances in steps of 6 (= record size S1): the first
  record has `D = 0x24B8` = exactly the offset of SECTION_1.
* `A` (0x798C, 0x799A, 0x79B1, …) is **not** a pointer into SECTION_2: it points to the
  record's **street name**, a NUL-terminated Latin-1 string in the text that follows
  SECTION_2 (it is monotonic because records are alphabetical). See §6.3.2.
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
* `FLAGS` takes values `0x00, 0x01, 0x02, 0x10, 0x11` → independent bit 4 and bit 0/1
  (candidates: one-way / digitization direction). **UNCONFIRMED**.
* `B` is `0xFF` in the vast majority of records (sentinel "absent"),
  otherwise small values (`0x05, 0x07, 0x0A, 0x13, 0x15`).
* `C` is usually `0x0000` in `0x0E` blocks; when non-zero it points to a **locality**
  string (e.g. `haddington road` → `dublin 4`), see §6.3.2. In `0x0C` blocks it is an internal pointer
  (e.g. `0x989F`, `0x98C6`) to the blob at offset `0x9884` indicated in SERVICE_DATA.

```python
PARCEL_S0_FMT = ">HBBHH"        # 8 bytes
# A, FLAGS, B, C(name/aux ptr or 0), D(ptr to SECTION_1, stride 6)
```


### 6.3.1 Type `0x0E` CF=1 Decoder & Semantics

**Routing Architecture**: The routing engine (`rpmod`) and database query engine (`dbq`) ONLY request `BLOCK_TYPE` `0x0E` (parcels), `0x10` (street names), and `0x12` (root). They **never** read types `0x00`-`0x03` (which are handled strictly by `pbp` for map drawing) nor `0x04` (matrices). Thus, **the routing is NOT precalculated**: the firmware reconstructs the entire network hierarchy, valid paths, and turn costs at runtime starting from the base `0x0E` topology.

**Layout**: 
- **Prologue**: `T[0x2b]` (48 bytes).
- **Bitstream Pre-header** (raw bytes, copied before `bits_init` — ✅ VERIFIED 2026-09-18):
  - 2 bytes: Count $N$ (number of 12-byte anchor structs)
  - $N \times 12$ bytes: anchor table (reference points for Section 2 delta decode; NOT output to dst)
  - 1 byte: `M_hi` — delta field width for Section 2
  - 1 byte: `M_lo` — val2 field width for Section 2
- **Section 0** (Nodes/Segments, `T[0x2d]` = 8 bytes — ✅ VERIFIED 2026-09-18):
  - `+0 (u16)` `A`: `getbits(ptrbits)` → Section 2 byte offset.
  - `+2 (u8)` `FLAGS`: `getbits(2)` bits 0–1; `getbits(1)<<4` bit 4. (**NB**: original m68k annotation "getbits(4)" is wrong for DB-REL 34.)
  - `+3 (u8)` `B`: If `getbits(1)`==1 → `getbits(3)`, else inherit from previous record. (**NB**: original annotation "getbits(8)" is wrong for DB-REL 34.)
  - `+4 (u16)` `C`: If same `getbits(1)`==1 → `getbits(ptrbits)`, else inherit.
  - `+6 (u16)` `D`: Pointer to Section 1. `getbits(bits_needed(S1_count)) × T[0x41] + S1_offset`.
- **Section 1** (Edges/Attributes, `T[0x41]` = 6 bytes — ✅ VERIFIED 2026-09-18):
  - `+0 (u16)`: Pointer to Section 2. `getbits(bits_needed(S2_count)) × T[0x42] + S2_offset`.
  - `+2 (u8)`: If `getbits(1)`==1 → `getbits(bits_needed(S2_count)) + 2`, else `1`.
  - `+3 (u8)`: flag. `getbits(1)`. **1 = the entry has house numbers** (at least one of its
    S2 records has a non-`0x7FFF` range): 2,510 / 2,510, and 0 for all 4,363 others (CD-ID 21594).
  - `+4–5`: zero (not decoded); 0 in all 6,873 records sampled on CD-ID 21594.
- **Section 2** (street → map link, `T[0x42]` = 24 bytes; earlier read as geometry. Bitstream layout ✅ VERIFIED 2026-09-19, oracle: pbp m68k write trace `pbp+0x41c0`):
  - `idx_N = getbits(bits_needed(count_N))` → selects 12-byte anchor
  - `has_deltas = getbits(1)`
  - if `has_deltas`: for each of 4 fields: `is_16=getbits(1)`; `val=getbits(16 if is_16 else M_hi)`
  - else: 4 × sentinel `0x7FFF`
  - `val1 = getbits(13 if subrel < 9 else 15) << 1`; `val2 = getbits(M_lo)`
  - **Output byte layout**:

    | offset | size | content |
    |--------|------|---------|
    | `+0`   | i32  | `x_anc` — anchor bytes 0-3 (raw copy) |
    | `+4`   | i32  | `y_anc` — anchor bytes 4-7 (raw copy) |
    | `+8`   | u16  | `raw_delta[0]` — unsigned, width = `is_16?16:M_hi` |
    | `+10`  | u16  | `raw_delta[1]` |
    | `+12`  | u16  | `raw_delta[2]` |
    | `+14`  | u16  | `raw_delta[3]` |
    | `+16`  | i32  | `anchor_f2` — anchor bytes 8-11 (raw copy) |
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

### 6.3.2 Type `0x0E` Field Meaning from Disc Data

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

### 6.4 Type `0x04` (80,825 blocks) — 160-Entry Table

```
+0x08 SECTION_DESCRIPTOR[1] = {0x0010, 160}
+0x0C SERVICE_DATA (4 bytes)
+0x10 SECTION_0: 160 records of 10 bytes = 5 x u16
      sentinel value "undefined" = 0x7FFF
```
The first sampled block has 22 records all set to `7FFF 7FFF 7FFF 7FFF 0000` followed by
small values (`000B 000E 000D 0010 0002`). Size and sentinel are verified;
**the meaning of the 5 fields is UNKNOWN** (candidates: turn cost matrix / road
classes, unconfirmed).

### 6.5 Type `0x06` (2,688 blocks) — POI

```
+0x08 SECTION_DESCRIPTOR[1..6], the first is {0x0020, N}
+0x0C UNKNOWN (4 bytes)
+0x10 BOUNDING_BOX: 4 x i32 big-endian = X_min, Y_min, X_max, Y_max   ✅ VERIFIED
+0x20 SECTION_0: N records of 24 bytes
      ">IHHHHIII" e.g. 2C48F11D | 0E10 | 8512 | B3A8 | 0023 | 00000000 | 419CC638 | 00000000
```
POI names are at the end of the block, ISO-8859-1, `0x00`-terminated
(e.g. `la caixa`, `cepsa`, `deutsche bank`, `caja rural de canarias`).
`X_max - X_min == Y_max - Y_min` always, and always `98304 * 2^k` → **quadtree grid**.
Observed values: 98,304 / 196,608 / 393,216 / 786,432 / 1,572,864 / 3,145,728.

---

## 7. Coordinate System — **RESOLVED**

```
X = (lon + 30.0) * 2_000_000_000 / 360        lon = X / K - 30.0
Y = (lat +  0.0) * 2_000_000_000 / 360        lat = Y / K
K = 2e9 / 360 = 5_555_555.5555…  units / degree
```

A full turn of 360° equals exactly **2,000,000,000 units**: fits into a signed
`int32` (max 2,147,483,647) with margin. 1 unit = **0.18 µ°** ≈ 2 cm
at the equator. The origin is at the **equator at 30° West**; the X axis increases eastward,
the Y axis northward, the relationship is **linear in latitude** (no
Mercator projection).

### 7.1 How It Was Determined

Blocks of type `0x16` contain 20-byte records with absolute 32-bit
coordinates and a pointer to the name (§6.6). From there, label points
of 38 European cities were extracted (`scripts/extract_anchors.py`) and compared
with published WGS84 city centers (`scripts/optimize_coords.py`).

| Fit | K | Cx | Cy | rms | max |
|---|---|---|---|---|---|
| free (3 parameters, Levenberg-Marquardt) | 5,556,973 | 29.9891 | −0.0102 | 2.00 km | 4.07 km |
| hypothesis `K = 2e9/360`, `Cx = 30`, `Cy = 0` (0 parameters) | 5,555,556 | 30.0000 | 0.0000 | **2.00 km** | 4.09 km |

The free fit converges to `Cx = 29.989` and `Cy = −0.010` — i.e. 30 and 0 within
noise — and the **zero free parameter hypothesis yields the same rms as the three-parameter
fit**. The 2 km residual is the offset between the city label point in the
database and the reference city center, not a modeling error.
The deviation between free K and `2e9/360` is **+0.0255 %**, within 1σ.

Residuals for the best anchors: Toulouse 0.17 km · Bordeaux 0.28 km · Köln 0.37 km ·
Praha 0.47 km · Amsterdam 0.47 km · Zaragoza 0.47 km · Helsinki 0.66 km.

### 7.2 Independent Verifications

None of these cities were used in the fit:

| Block / tile | decoding | reality |
|---|---|---|
| Westernmost POI tile | lon −29.13…−28.57 · lat 38.44…39.00 | Faial/Pico, Azores (−28.7 · 38.58) ✅ |
| Southernmost POI tile | lon −18.38…−17.81 · lat 27.68…28.24 | El Hierro / Southern La Palma ✅ |
| Northernmost POI tile with strings | lon −1.39…−0.82 · lat 59.95…60.52 | Shetland, Lerwick (−1.15 · 60.15) ✅ |
| Easternmost POI tile with strings | lon 18.4…19.0 | Ostrava (CZ) / Otranto (IT) ✅ |
| Canary POI cluster (5 groups) | −17.85 / −17.22 / −16.50 / −15.50 / −13.78 | La Palma · La Gomera · Tenerife · Gran Canaria · Fuerteventura+Lanzarote ✅ |
| bbox block `0x01` sector 6117309 | −5.92…−5.35 · 35.61…36.17 | Strait of Gibraltar ✅ |

The POI tiles reaching `X = 920,223,744` (lon ≈ 135° E) are **empty cells of the
global quadtree** (`COMPRESSION_FLAG=0`, zero records, zero strings): structure,
not coverage.

### 7.3 Quadtree Grid

All tile boundaries are exact multiples of **98,304 units** (= 3 · 2^15 =
0.0176896°), with origin at `(0, 0)`, i.e. 30° W on the equator. Observed sides
are `98304 · 2^k` for k = 0…5, with aspect ratios 1:1, 1:2, or 2:1.

### 7.4 Bounding Box by Block Type

The bbox (`4 × int32` = `X_min, Y_min, X_max, Y_max`) immediately follows the
section descriptor. **The number of descriptor entries varies from block to block**,
so the bbox must be located with a grid constraint (`carin.parser.iso.find_bbox`):
sides as multiples of 98,304 and aspect ratio 1:1 / 1:2 / 2:1.

| Type | bbox offset | locator coverage |
|---|---|---|
| `0x00`–`0x03` | `0x44` | 60/60 |
| `0x06` | `0x10` | 60/60 |
| `0x14`, `0x15`, `0x16`, `0x1C` | `0x20` | 60/60 |
| `0x1D`, `0x1E` | `0x20` | 43/60, 20/39 |
| `0x0C`, `0x0E`, `0x10`, `0x0F`, `0x11`, `0x17`, `0x19` | — | **no bbox**: indirectly georeferenced (`0x0E`: each S2 record names a `0x00` tile, §6.3.2) |

### 7.5 Python Struct

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

Verified across 2,395 blocks: for each observed tile size,
`max(LOCAL_X) = (X_max − X_min)/64 − 1` exactly.

| tile side (units) | 98304 | 196608 | 393216 | 786432 | 1572864 | 3145728 |
|---|---|---|---|---|---|---|
| measured `max(LOCAL_X)` | 1535 | 3071 | 6143 | 12287 | 24575 | 49151 |
| expected `side/64 − 1` | 1535 | 3071 | 6143 | 12287 | 24575 | 49151 |

POI resolution: 64 units = 1.15e−5° ≈ **1.2 m**.
The name blob (Latin-1, `\0`-terminated) follows the records; it contains **173
distinct names across the entire DB**, all brands/chains (banks, fuels, hotels) —
no toponyms, no airports.

Extracted from the image: **2,048,403 POIs**.

### 8.2 Type `0x16` — Feature Record, **20 bytes**

Layer of named features (islands, lakes, rivers, fjords, city labels).
It is the source of geographic anchors for the database.

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

The records reside in the section indicated by **entry 1** of the descriptor
(`struct.unpack_from(">HH", payload, 12)`), with a sentinel record at the tail.

```python
FEATURE_REC = ">HHIiiHH"     # 20 bytes
```

Verified example (sector 6326923, Göteborg bbox):
`landvettersjön` → X=234411946 Y=320448230 → **12.196° E · 57.681° N**
(actual Landvettersjön: 12.32 E · 57.68 N).

The same 20-byte layout with absolute coordinates applies to types `0x14`,
`0x1C`, `0x1D`, `0x1E` (labels of seas, regions, major cities).

### 8.3 Where Names Are Located

| Type | Textual content |
|---|---|
| `0x0C`, `0x0E` | toponyms / municipalities (≈3,600 distinct strings per sample) |
| `0x10`, `0x17`, `0x19` | odonyms (street names) |
| `0x15` | municipalities / hamlets |
| `0x16` | islands, lakes, watercourses, city labels |
| `0x14`, `0x1C`, `0x1D`, `0x1E` | seas, oceans, regions, major cities (multilingual) |
| `0x06` | POI brands |
| `0x07`, `0x0A` | country names |
---

## 9. `COMPRESSION_FLAG = 1` — Analysis Status

96,011 blocks out of 315,095 (30%) use this codec. **It is not required for the
compiler**: a generated database can use only `CF=0` and `CF=2`. It is only
needed to fully read the original disc.

### 9.1 Block Structure

The prologue is **in plaintext**, identical to a `CF=0` block: 8-byte header,
section descriptor, bbox, service data. Section offsets in the descriptor are
expressed in **decompressed** space and are consistent with `UNCOMPRESSED_SIZE*512`.
The compressed stream begins after the service data.

```
type 0x1E, sector 6452121, len=4 (2048 B) us=6 (3072 B)
0000: 62 73 99 04  00 1e  01 06        header: sec. 0x627399, 4 sec., type 0x1E, CF=1, US=6
0008: 0034 0004 0048 0010 019c 0003 01dc 010d 0000 0000 0610 005a   descriptor
0020: 03198000 107a5000 09198000 167a5000                            bbox
0030: 0001 000b 1300 0a00                                            service (plaintext)
0038: 02 04 81 41 a8 40 3a 67 ...                                    <- compressed stream
```

### 9.2 Measurements

| Quantity | Value |
|---|---|
| compression ratio | 1.33 – 2.65 (median ≈ 1.6) |
| stream entropy | **7.17 – 7.84 bits/byte** |
| trailing zero padding | 0 – 500 bytes |
| plaintext prologue | 48 B (type `0x0E`) · 56 B (`0x14`…`0x1E`) · 116 B (`0x00`…`0x03`) |

### 9.3 Experimentally Excluded Codecs

* **zlib / raw deflate**: exhaustive scan of *every byte offset and every
  bit phase* (left and right shifts, `wbits` −15/15) across the entire block →
  no valid stream. `scripts/analyze_codec.py`.
* **LZ4 raw block**: output ≤ 1 byte.
* **LZW** 9→12/13/14 bits, MSB and LSB first, with and without early change: no
  plausible output (oracle score ≤ 0.80).
* **Byte-aligned LZSS/LZ77**: grid of 384 combinations (literal bit 0/1,
  LSB/MSB order, window 1024/2048/4096/8192, 10/11/12/13-bit offset, three
  packings of the back-reference pair, initial fill `0x00`/`0x20`).
  No combination produces either the expected length or readable text.

### 9.4 The Result Pointing the Way

Comparison of shared 8-grams between pairs of blocks of the **same type**:

| Set | Blocks | Average Length | Shared 8-grams per pair |
|---|---|---|---|
| type `0x16`, `CF=1` | 12 | 14,988 B | **13.0** |
| type `0x16`, `CF=2` (zlib) | 12 | 23,638 B | **0.0** |
| type `0x15`, `CF=1` | 12 | 7,055 B | **3.0** |
| type `0x15`, `CF=2` (zlib) | 12 | 16,594 B | **0.0** |
| type `0x1E`, `CF=1` | 12 | 1,672 B | **4.0** |
| random control | 12 | 2,000 B | **0.0** |

Larger zlib blocks share **no** 8-grams, because the dynamic Huffman tree
destroys byte alignment. `CF=1` blocks regularly share them. Consequences:

1. The codec is **deterministic and stateless across blocks** — not per-block
   key/IV encryption.
2. The code is **byte-aligned** or uses a **shared static table**: identical
   input sequences produce identical output bytes.
3. Therefore it is vulnerable to frequency analysis / cross-block pattern
   matching, without having to guess the format a priori.

### 9.5 Verified Layout of Type `0x1E` (sections, offset by offset)

Derived by comparing 3 `CF=0` blocks with different schemas (`6452125`: 2 sectors,
6-entry descriptor; `6452128`: 1 sector; `6452121` cited in §9.1) and verifying
that all formulas hold exactly across all three together:

```
+0x00  header (8 B)
+0x08  SECTION_DESCRIPTOR[6]  { off, count } x 6   (always 6 entries for 0x14..0x1E)
+0x20  BBOX  4 x int32                              (16 B, fixed)
+0x30  SERVICE_DATA  4 B  (observed: 00 01 00 0b constant across samples)
+0x34  SECTION_0  @ entry0.off, entry0.count records — variable record size
       (record = (entry1.off - entry0.off) / entry0.count; 6 B in samples)
       SECTION_1  @ entry1.off, **(entry1.count + 1) records of 20 B**
       — the +1 is a sentinel record at the tail, verified across 3 independent
         blocks: entry3.off - entry1.off == (entry1.count+1)*20 exactly
         in all three (6452121: 0x19c-0x48=0x154=17*20; 6452127: 0x90-0x40=
         0x50=4*20; 6452128: 0x64-0x3c=0x28=2*20). Record layout = FEATURE_REC
         (§8.2): NAME_PTR u16, u16, u32, X i32, Y i32, u16, u16.
       SECTION_3  @ entry3.off, entry3.count records of **4 B** (verified:
         6452128 (0x74-0x64)/4=4 exact)
       SECTION_5  @ entry5.off, entry5.count records of **4 B** (verified:
         6452125 (0x178-0x114)/25=4 exact; 6452128 (0xa4-0x74)/12=4 exact)
         — almost certainly { u16 offset_in_blob, u16 lang_id }, i.e. the
         name→language lookup table preceding the string blob
+text  blob of Latin-1 \0-terminated strings, as many as entry5.count
```

`entry2` and `entry4` are always `{0,0}` in 0x1E samples — sections unused
by this type. This map **does not crack the codec**, but firmly establishes
the expected structure of the decompressed output: useful as a much stricter
oracle than `score_output` for any future attempt (exact section lengths, not
just readable text).

### 9.6 Additional Attempts in This Session — All Failed, with Measurements

1. **Search for identical bbox pairs between `CF=1` and `CF=0`/`CF=2`** (the most
   direct idea to obtain an actual plaintext/ciphertext pair, not a hypothesis).
   Scanned all `CF=0`/`CF=1` blocks of types with known bbox
   (`0x14,0x15,0x16,0x1C,0x1D,0x1E`, 18,481 blocks), extracted the bbox from
   the plaintext prologue (works on `CF=1` as well, because the prologue is not
   compressed), grouped by `(type, bbox)`. **Result: 18,406 groups across
   18,481 blocks, zero groups with mixed CF.** Each quadtree tile exists only
   once with a single compression level: **no plaintext/ciphertext pair of the
   same content exists in the database.** The script is `scripts/find_pairs.py`
   (moved from scratchpad if needed to re-run).
2. **Global static Huffman, order 0.** Built a canonical Huffman tree from the
   aggregate byte frequency across 4,000 `CF=0` blocks (trimming trailing
   zero-padding). The sample is dominated by low-entropy numeric types (byte
   `0x00` = 93% even after trimming), so the model does not represent the textual
   content of `0x1E`: it predicts a compression ratio of 5.3x versus the
   1.33–2.65x observed. Decoding block `6452127` with this table (MSB and LSB bit
   orders): wrong output length and no readable text in either bit order. **Inconclusive**:
   only rules out a global order-0 Huffman built from an unrepresentative sample,
   not the hypothesis itself — the true table would be needed, which is not in
   the prologue of any block.
3. **Search for leaked plaintext in the "compressed" stream.** Grep for runs of
   4+ lowercase Latin-1 characters across the 14 `CF=1` blocks of type `0x1E`:
   ~40 matches found, all 4-5 bytes long, at the frequency expected by chance
   (~(27/256)^4 per position, consistent with random matches across ~5,000 total
   bytes). Only one match is pure readable ASCII (`coth` in `6452200`, offset
   `0x65`) but corresponds to no plausible word for a sea/ocean name and does
   not repeat in any other block at the same relative position. **Conclusion: no
   plaintext leakage into the compressed stream**, ruling out a mixed
   literal+compressed hypothesis at the byte level.
4. **Entropy invariance to bit shifts** (0–7 bits, rotating the entire stream).
   Tested on 5 `CF=1` blocks of type `0x1E` (from 374 to 4,105 B). Result: nearly
   constant entropy (variation < 0.2 bits across all shifts, on both short and
   long samples). **Non-discriminating**: an already high entropy (7.0–7.8 bits/byte)
   leaves little margin to detect bit misalignment; the test does not contradict
   the byte-aligned conclusion of §9.4 (based on shared 8-grams, a stronger signal),
   nor does it independently confirm it.
5. **Comparison with `/TPD/*.CPR`** (phase 3 of the plan). Extracted the 3 files
   `ENG_1.CPR`, `FRE_4.CPR`, `GER_2.CPR` (same "Tool 5001", same content in 3
   languages). Byte 0 identical (`0x03`) on all; byte 1 diverges immediately
   (probable per-file length/ID field); **bytes 2–7 identical across all three**
   (`00 09 87 25 52 aa`), followed by total divergence from byte 8 onward. CPR
   entropy: **6.636–6.638 bits/byte**, markedly lower than `CF=1` blocks (7.17–7.84).
   The common 6-byte prefix is consistent with a simple magic/format version (too
   short to be a dictionary), and the lower entropy can be explained simply by the
   higher redundancy of natural text compared to CARINdb binary data — **neither
   proves nor rules out the same codec**. Not investigated further due to time
   constraints: would require cracking the CPR format from scratch, which is a
   sub-project on its own (no known UNCOMPRESSED_SIZE to validate an attempt,
   unlike CARINdb blocks).

### 9.7 Next Steps (Updated)

1. **The most important dead end of this session**: no plaintext/ciphertext
   pair of the same content exists on the disc (§9.6.1). Any known-plaintext
   attack must therefore rely on content *reconstructed by similarity* (`CF=0`
   block of an adjacent tile / same type), not an exact duplicate — weaker, but
   the only avenue remaining on the disc.
2. The section map of §9.5 makes it possible to construct a validation oracle
   much stricter than `score_output`: exact length of *each* section declared
   by the descriptor (not just total block length). Should be integrated into
   `compression.py` prior to any new decoding attempt on type `0x1E`.
3. If one wishes to pursue the Huffman / static table hypothesis: one would need
   to derive true per-type frequencies (not a mixed global sample as in §9.6.2)
   and attempt to *break* the code blindly (Cichelli's algorithm or golfed tree
   search starting from most probable code lengths), or search for the table among
   root/`0x0D`/`0x18` data not yet inspected byte-by-byte in this session
   (`0x1B`/`0x1A` were inspected: `0x1B` is almost all zeros with a single pointer
   to `0x1A`; `0x1A` is a sequential table of ~430 `BLOCK_ID`s with 4 extra bytes
   each, appearing to be a block index rather than an encoding table — both
   *ruled out* as static table candidates).
4. Alternatively, deciphering `/TPD/*.CPR` as an independent corpus (§9.6.5) remains
   the most promising unexplored lead, but requires reconstructing the CPR format
   from scratch (no expected length documentation).

### 9.8 Attempts in Session 2026-09-15 — Also Failed

Starting from the hypothesis "the most frequent bytes are powers of two ⇒ 1-bit
LZSS control bytes" (motivation of the session): **the hypothesis had already
been tested and ruled out in §9.3** (the grid of 384 combinations covers both bit
orders of a single power-of-two control byte). Additional verification performed
here: the dominance of powers of two in byte frequency **is not a signal specific
to the codec** — it persists identically if looking only at the tail of the stream
beyond the entropy boundary (`0xC0` in the analyzed type `0x00` block), with
counts 4–16× uniform expectation (`0x00`≈16×, `0x10`≈5×, `0x80`≈4×), BUT all 256
byte values still appear in the stream (no evidence of a restricted codebook).
Not decisive either way: consistent both with a real control byte and with an
accumulation of small field-level integers/flags surviving mild compression.

New attempts, both pursued to completion:

1. **aPLib / aP_depack** (byte-by-byte interleaved bitstream with gamma-coded
   lengths, not a separate control byte with 8 fixed tokens — hence not covered
   by the grid of §9.3). Faithfully ported from `https://github.com/snemes/aplib`
   (direct adaptation of Jørgen Ibsen's official library). Tested on type `0x00`
   block (sector 3157624, expected 10,636 B after 116 B prologue) and type `0x1E`
   (sector 6452121, expected 3,016 B after 56 B prologue): **fails within 3–13
   bytes**, almost immediately hitting aPLib's end-of-stream marker (`offs==0`
   in the short match branch). Sweep of starting point (0–250 B) on type `0x00`
   block: maximum reached is **59 bytes out of 10,636 expected** (offset 95) —
   no trigger point produces a valid stream. **Ruled out.**
2. **Varint / gamma-coding at field level** (hypothesis: not dictionary compression
   but numerical field-by-field delta coding, given the low compression ratio —
   1.33–2.65× — and already near-maximum entropy, atypical for LZ but typical of
   packed integers). Preliminary verification (LEB128 on the raw stream) not
   discriminating alone; not taken to a full decoder due to lack of a field-level
   validation oracle (would first require solving the target type record
   semantics). **Inconclusive — remains the most promising lead not yet
   exhaustively tested**, to be paired with the section oracle of §9.5.
3. **Search for a static table in `0x0D`/`0x18`** (flagged for inspection in §9.7.3).
   `0x18` (sector 6452204): confirmed index of `BLOCK_ID` + 4 extra bytes (no
   256-entry structure). `0x0D` (sector 17, zlib, 49,152 B decompressed): variable
   records `{u32 segment-constant, u16 id, u16 flag, u16 offset, u16 count, u16 pad}`,
   clearly a range index (alphabetical/regional type), not a table of 256 code
   lengths. **Ruled out as well.**

**Summary Balance**: with this session, 6 codec families have been experimentally
excluded (zlib, LZ4, LZW, byte-aligned LZSS with 384 variants, global order-0
Huffman, aPLib), plus the search for static tables in system blocks. No concrete
new leads emerged: the codec remains unidentified. The actual block is not on the
compiler's critical path (§9, opening) — it affects only full reading of the
original disc, not generation.

### 9.9 Targeted Test of User Hypothesis (189 B prologue, custom LZSS) — Falsified with Structural Oracle

Re-examination of the hypothesis with specific parameters suggested by the user
(plaintext prologue 189 B = `0xBD`, window 4096, zero-init, MSB-first control bit,
0=literal/1=backref, 2-byte token with high nibble = length−2, low 12 bits = offset).
Tested with an oracle **far stronger** than output length alone:

1. **Exact length is not a valid oracle.** On type `0x00` block sector 3157624
   (expected 10,752 B), *every* prologue value from 0 to 421 yields an output
   of the exact expected length — the loop halts as soon as it hits the target,
   so hitting the length proves nothing about parameters.
2. **Actual structural oracle**: found a `CF=2` block (zlib, hence known ground
   truth) of the same type `0x00` (sector 3247755) with the *same* initial
   descriptor layout (offsets 116/148/180) and the same section record sizes
   (`S4=32 B`, `S5=8 B`, `S6=16 B`, confirmed also on a second zlib sample, sector
   3249459). Real `S4` records display nearly constant columns and slowly growing
   IDs (e.g. bytes 19–22 = `4688000000` fixed across *all* records, byte 17
   increments by 1 from record to record). Reference score: average entropy per
   column `S4=2.43`, `S5=3.28` bits (on an alphabet of 0-255, thus far below 8 =
   structured data).
3. **Test on user parameters** (prologue 189, absolute off, little-endian token
   as suggested): exact length reached on 6/8 sample blocks, but **section content
   is unstructured** (no constant column, no monotonic ID) — falsified by direct
   inspection, not merely by the oracle.
4. **Grid search guided by the structural oracle** (literal bit 0/1, bit order
   MSB/LSB, token endianness LE/BE, length split 4/5/6 bits, bias 2/3, offset as
   absolute position vs backward distance — 96 combinations at exact length):
   the combination closest to the target (`lit_bit=0`, `MSB`, **big-endian token**
   — not little as hypothesized —, length=high nibble+3, **offset as backward distance**
   from `pos` not absolute position) matches the target within 0.001 on the sum
   (`S4=2.44`, `S5=3.27` vs real `2.43`/`3.28`) — yet **byte-by-byte inspection
   still reveals noise**, not the actual constant/monotonic fields. Proximity in
   mean column entropy is therefore a **statistical coincidence** (likely due to
   identical zero density), not a signal of correctness: aggregate mean entropy
   oracle is insufficient; a per-column test on mode/variance, not merely mean
   entropy, would be required.
5. **Shared 8-grams also on type `0x00`** (not yet verified in §9.4, which covered
   only `0x14`–`0x1E`): confirmed — average 9.0 shared 8-grams per pair across 66
   pairs of `CF=1` type `0x00` blocks (up to 38 on a single pair), well above noise.
   Also discovered a **non-trivial** 14-byte fragment, all 14 distinct (no internal
   repetition, hence not explainable by padding or obvious patterns), byte-for-byte
   identical between sector 3157667 (offset 15625 in stream) and sector 3157861
   (offset 15774): `04 81 10 32 08 42 c8 61 0e 21 e4 4c 89 31`. Confirms that the
   codec is **byte-aligned and deterministic for type `0x00` as well** (consistent
   with §9.4) — probability of random coincidence on 14 all-different bytes is
   negligible. It is the best candidate for a future differential known-plaintext
   attack (not yet attempted: would require aligning the two decompressed streams
   and deducing token structure from match position), but was insufficient in this
   session to determine exact parameters.

**Conclusion**: the single-bit control-byte hypothesis (across any of the >480
variants tested between both sessions: 384 + 96) is **in all likelihood wrong in
its entirety**, not merely in details of bit order or endianness. The byte-aligned /
deterministic signal (shared 8-grams, 14-byte fragment) remains valid and should
be leveraged via a different method — differential analysis on shared fragments,
not grid search over fixed-model parameters.

### 9.10 Cross-Edition Comparison (CD-ID 21708 vs 21734) — New Methodology, Same Negative Outcome

A second image of the same format was made available: `NAV_DB_21734`
("High_2019_WE_SC_SL.bin", build 2018-05-09, DB-REL 34 / BSW-REL 10 11 —
**same binary schema** as 21708 from 2015-08-04, thus byte-comparable).
Contrary to what was hypothesized in §9.7.1, this does *not* provide an exact
plaintext/ciphertext pair (content changes between editions even for the same
tile), but nonetheless provides concrete leverage:

1. **Method**: the bbox of type `0x00` is located at decompressed offset `0x44`,
   **inside the plaintext prologue** (~0xBD) — hence readable on `CF=1` blocks
   without decompressing. Scanned all type `0x00` blocks in both images (36,452
   in 21708, 28,008 in 21734), indexed by exact bbox: **21,751 bboxes in common**.
   Distribution `(cf_old, cf_new)`: `{(1,1): 21363, (0,0): 328, (1,0): 31, (0,1): 29}`
   — **60 tiles with differing compression between editions for the same
   geographic tile**, as close as possible to a real plaintext/ciphertext pair
   obtainable from this material.
2. **No pair is byte-identical**: 0 of the 60 cases with identical `UNCOMPRESSED_SIZE`
   have identical zlib/raw content — the tile was almost always updated between
   2015 and 2018 (roads/POIs added), even when size does not change.
3. **Filtering for likely stable content**: the `SECTION_DESCRIPTOR` (8 pairs of
   `offset,count`) is readable in plaintext **regardless of CF**. Filtering the
   60 pairs for identical descriptors across all 8 entries between editions → 12
   pairs with probable nearly unchanged content (same record count per section,
   same offsets).
4. **Test**: for each of the 12 "stable" pairs, decompressed the `CF=1` side
   using the parameter grid of §9.9 (literal bit, order, token endianness, length/offset
   split, distance vs absolute position) and compared with `difflib.SequenceMatcher`
   against the real content of the other edition (`CF=0`), **excluding** both the
   plaintext prologue (`< 0xBD` on both sides) and low-variety match blocks
   (`len(set(bytes)) < 3`, i.e. runs of zeros) to avoid the false signal
   uncovered in §9.9.4. Best combination: **32–70 non-trivial matching bytes
   across ~1,024–1,200 bytes per block** (total 590 out of 14,336, ~4%) — **at
   the level of noise**: discrepancies are scattered fragments of 4–14 bytes of
   low information (`0000000000...` with 1-2 differing bytes), not the long,
   high-variety matches expected from true decompression (such as the 14-byte
   all-distinct fragment of §9.8.5).
5. **Conclusion**: even with a far stronger ground-truth oracle (nearly unchanged
   tile content between two editions, rather than synthetic statistics), **no
   combination from the control-byte LZSS family reproduces real content**.
   While this does not prove the codec is not LZSS in a broader sense, it rules
   out with highest confidence yet the entire "1-bit control byte + 2-byte token"
   family tested from §9.3 to here (>650 combinations), regardless of bit/endianness/offset
   assignments.
6. **Value for the future**: the methodology itself (indexing type `0x00`/`0x06`/`0x16`
   bboxes between different editions, filtering by identical descriptor, using
   `difflib` excluding low-variety runs as an oracle) remains valid and reusable
   for **any** new codec hypothesis — not just LZSS. If a third edition is obtained,
   or if scanning is extended to `0x06`/`0x16`/`0x1E` (bboxes also in plaintext,
   §7.4), the probability of finding a differing-CF pair with *truly* unchanged
   content increases. Reference script saved in `build/cross_iso_type0.pkl`
   (bbox→(sector,length,cf) map for both images, type `0x00`).
---

### 9.11 — **CODEC IDENTIFIED** from Original Firmware (2026-09-15)

`CF=1` **is not a dictionary codec**. It is not LZ, not Huffman, not
entropic. It is **structure-driven bit-packing guided by block structure**:
each section has its own decoder that reconstructs fixed-size records
by reading minimal-width fields from an MSB-first bitstream, and converts
**record indices into absolute offsets** within the decompressed block.

This explains all previous seemingly contradictory observations:

| Observation | Explanation |
|---|---|
| 1.33–2.65× ratio only | only high bits of fields are omitted, no dictionary |
| entropy 7.17–7.84 bits/byte | bit-packed fields, no residual redundancy |
| shared 8-grams across blocks | identical field patterns at the same bit phase |
| zero plaintext leakage | names use a dedicated prefix encoder |
| every LZ/Huffman family falsified | all of them were the wrong hypothesis |

#### 9.11.1 Where the Decoder Resides

| Firmware | Path in ISO | Module | CPU | DB-REL |
|---|---|---|---|---|
| CARIN CC-93 0560 | `/CC93_/0560/nav_sw_load` | `pbp` @ `0x58ed0` | m68k (OS-9/68K) | 14–17 |
| Mk2C / Mk2M | `/Mk2C/0211/BMW/app_sw/bsw_load` | `pbp` @ `0x34130` | m68k (OS-9/68K) | 14–22 |
| Mk3 | `/Mk3/0127/BMWC01S/app_sw/bsw_load` | `db_pub` @ `0x7d488` | **MIPS32 BE** (OS-9000) | ≥ 34 |
| RR / V_2 | `/V_2/RR/0101/BMWC01S/app_sw/bsw2` | `db_pub` @ `0x917c8` | MIPS32 BE | ≥ 34 |

The decoder **is not** in `dbd`, `dbq`, or `dbc` (those are daemon, query,
and cache). `Mk3`/`RR` modules labeled `usw_load` are the MMI side and
do not contain the codec.

**Unique codec signature** — the character table of the text decoder,
42 bytes, identical across all firmwares:

```
61 65 | 73 74 72 00 | 20 64 67 68 69 6c 6e 6f | e0 e1 … fd ac
 a  e |  s  t  r NUL |  SP d  g  h  i  l  n  o | à á … ý ¬
```

A frequency-tailored code designed for European street names: `a`/`e` in
1 bit, `s t r NUL` in 2, `SP d g h i l n o` in 3, accented Latin-1 in 7.
Searching for these 42 bytes is the fastest way to locate the codec in
any other firmware (`scripts/fw_hunt_charmap.py`).

#### 9.11.2 Primitives (offsets in CC-93 `pbp` module)

```
0x3660  uncompressed_sectors(hdr)   bit 0 of hdr[6] -> hdr[7] otherwise blockid&0xff
0x3698  dispatch: if hdr[6]&1 -> init + switch on BLOCK_TYPE, otherwise memcpy
0x4798  init(src)        PTRBITS = bits_needed(usize * SECTOR)   [CC-93: SECTOR=2048]
0x47da  copy_raw(dst,n)  memcpy from raw cursor, cursor += n
0x4800  copy_section(base, entry, recsize, plus1)
0x49a8  bits_init()      base = current cursor, bitpos = 0
0x49bc  getbits(n)       BFEXTU (a0){bitpos:n}  -> MSB-first
0x4a68  bits_needed(n)   bits to represent 0..n-1, 16-bit arithmetic
```

`getbits` uses **68020 bitfield instructions** (`BFEXTU`, opcode `E9D0`).
This explains why earlier sessions missed it: capstone in `CS_MODE_M68K_000`
mode renders them as `.dc.w`. **`CS_MODE_M68K_040` is required.**

`PTRBITS` is the bit width of an internal block pointer:
`ceil(log2(UNCOMPRESSED_SIZE * 512))`. For a 10,752 B block it is 14 —
compared to the 16 bits of the decompressed field. Hence the compression.

#### 9.11.3 Superblock `RECORD_SIZE_TABLE` Parameterizes the Decoder

`pbp+0x3582` reads the superblock: descriptor at `+0x28` = `{u16 offset, u16 count}`,
then `count` pairs `{u16 id, u16 value}` that **override** hardcoded defaults
(`pbp+0x33ea`, extractable via `scripts/cf1_defaults.py`). This is exactly the
`RECORD_SIZE_TABLE` of §3.2. In the MIPS firmware the same table is pointed to by
`-0x7900($gp)` with `field(X) = T[(X-8)/2]`.

Entries used by the type `0x00` decoder (CC-93 default → DB-REL 34 actual value):

| id | role | CC-93 | DB-REL 34 |
|---|---|---:|---:|
| `0x05` | offset of `SECTION_DESCRIPTOR` in block | 8 | 8 |
| `0x06` | section 6 record | 16 | 16 |
| `0x08` | section 4 record | 28 | **32** |
| `0x09` | offset of tail fields in section 4 record | 22 | **26** |
| `0x0b` | plaintext prologue length | 108 | **116** |
| `0x0c` | section 7 record | 6 | 6 |
| `0x0f` | section 9 record (copied verbatim) | 8 | 8 |
| `0x10` | section 5 record | 8 | 8 |
| `0x12` | section 3 record (verbatim, +1 record) | 4 | 4 |
| `0x13` | section 11 record | 6 | 6 |
| `0x14` | section 10 record (verbatim) | 8 | 8 |
| `0x15` | section 12 record (verbatim) | 4 | **6** |
| `0x40` | sections 0,1,2 record | 6 | **10** |

Verified against a real `CF=0` block (sector 3169061, DB-REL 34): all section
lengths match **exactly** with these values, including the sentinel record
(`e3` = `(count+1)·4`, `e4` = `(count+1)·32`).

#### 9.11.4 `decode_type00` — Structure

```
copy_raw(dst, T[0x0b])                       # plaintext prologue (header+descr+bbox+service)
PB_s2  = bits_needed(e2.count)               # descriptor[D+0x0a]
PB_s4  = bits_needed(e4.count  + 1)          # [D+0x12]
PB_s7  = bits_needed(e7.count  + 1)          # [D+0x1e]
PB_s10 = bits_needed(e10.count + 1)          # [D+0x2a]
PB_s11 = bits_needed(e11.count + 1)          # [D+0x2e]
PB_s12 = bits_needed(e12.count + 1)          # [D+0x32]
widths = copy_raw(2)                         # two adaptive widths per block
copy_section(e3,  T[0x12], plus1=True)       # sections copied verbatim
copy_section(e9,  T[0x0f])
copy_section(e10, T[0x14])
if e12.count: copy_section(e12, T[0x15])
bits_init()                                  # bitstream from here on
dec_A(e0); dec_A(e1); dec_A(e2)
dec_B(e4)                                    # + sentinel record at tail
dec_C(e5); dec_D(e6); dec_E(e7)
if e11.count: dec_F(e11)
dec_text()
```

`dec_B` confirms the sentinel record of §9.5: the loop covers `count` records
and then writes only select fields of record `count`.

Recurring field encodings:

* **internal pointer**: `target_section_off + getbits(PB_target) * recsize`
  (record index, not offset) — with `index == count` used as `NULL`;
* **even offset**: `getbits(PTRBITS-1) << 1`;
* **inheritance**: 1-bit flag; if 0 the field is copied from the preceding record
  (in `dec_B` the entire record starts as a copy of the previous one);
* **coordinates** (`dec_C`/`dec_D`/`dec_E`): first record absolute 16-bit, then
  `1 bit` → absolute/delta, `1 bit` → sign, `getbits(widths[1])` for magnitude;
* **block cache**: two values (pointer to `e7` and to `e2`) initialized to 1
  and re-emitted until a flag updates them.

#### 9.11.5 Text Decoder (`pbp+0x4862`)

```
start = getbits(PTRBITS);  end = getbits(PTRBITS)
if start == 0 and end == 0: return
dictionary = [ bytes(getbits(7) for _ in range(getbits(5))) for _ in range(6) ]
p = start
while p <= end:
    code = getbits(2)
    00 -> CHARMAP[getbits(1)]            # a e
    01 -> CHARMAP[2 + getbits(2)]        # s t r NUL
    10 -> CHARMAP[6 + getbits(3)]        # SP d g h i l n o
    11 -> v = getbits(7)
          v > 0x26  -> literal character
          v > 0x1b  -> block-local dictionary entry (v-0x21)
          otherwise -> CHARMAP[14 + v]   # accented
```

The decoded name blob is the **strongest validation oracle available**:
it sits at the end of the bitstream, so if readable text emerges, everything
preceding it was decoded correctly.

#### 9.11.6 DB-REL 34 Differences and Port Status

The m68k decoder (CC-93 / Mk2C) **is insufficient** for DB-REL 34 discs:
records grew (`T[0x08]` 28→32, `T[0x40]` 6→10) and extra fields are not
written. The correct decoder is the **MIPS one in `db_pub`** (Mk3/RR), which
shares the same structure but is organized into **multiple passes**: each section
is traversed multiple times with a `kind` argument (`0x14`, `0x15`, `0x17`)
selecting the group of fields to read. Sequence of `decode_type00`
(`db_pub+0x3d04`, Mk3 0127):

```
kind 0x14: dec_e0, dec_e1, dec_e2, dec_B, [dec_C/dec_D/dec_E inlined]
kind 0x15: dec_e0, dec_B, ...
kind 0x17: dec_e2, dec_e1, dec_e0
if getbits(1): dec_text()      # two text blobs, not one
```

The descriptor of type `0x00` has **15 entries** in DB-REL 34 (`e0..e14`), versus
the 13 used by CC-93; `e13` and `e14` are the new sections.

**Sections 0/1/2** — three distinct functions (`db_pub+0x2f30`, `+0x30dc`,
`+0x3270`), 10 B records, `PTRBITS` is a byte at `-0x6635($gp)`:

```
e0  kind 0x14 : if getbits(1) { getbits(PTRBITS); getbits(PTRBITS-1) }   # bits consumed, not stored
                rec[0] = getbits(PTRBITS)
    kind 0x15 : if getbits(1) rec[2] = getbits(16)
    kind 0x17 : rec[4] = getbits(PTRBITS-1) << 1

e1  kind 0x14 : if getbits(1) { rec[2] = getbits(PTRBITS)
                                rec[4] = getbits(PTRBITS-1) << 1 }
                else          { rec[2] = prev[2]; rec[4] = prev[4] }
                rec[0] = getbits(PTRBITS)
    kind 0x17 : rec[6] = getbits(PTRBITS-1) << 1
                rec[8] = getbits(PTRBITS-1) << 1

e2  kind 0x14 : like e1
    kind 0x17 : "sticky" delta on rec[6] and rec[8] (see below)
```

In `kind 0x14` of `e0` the two fields are read and **discarded**: the stream still
contains them (a DB-REL ≤ 22 reader would use them for `rec[2]`/`rec[4]`) but the
new reader overwrites them in passes `0x15`/`0x17`. This is backwards compatibility
of the format, not a read bug.

**Sticky Delta** (`e2`, `kind 0x17`) — two independent accumulators:

```
delta = 0 ; acc = 0
per record:  if getbits(1): delta = (getbits(PTRBITS-1) << 1) & 0xffff
             rec[k] = acc = (delta + acc) & 0xffff
```

A flag of 1 updates the step, a flag of 0 reuses the last step. **Verified against
real `CF=0` block**: `e2.rec[6]` is `0, 0x2ec, 0x2f0, 0x2f4, 0x2f8, 0x2fc`
→ steps `0, 0x2ec, 4, 4(reuse), 4(reuse), 4(reuse)`; `e2.rec[8]` is
`0, 4, 4, 4, 4, 4` → steps `0, 4, 0, 0(reuse), 0(reuse), 0(reuse)`. Both
series reproduce exactly, and steps are always even as dictated by `<< 1`.

**Section 4** (`db_pub+0x348c`), 32 B records: identical to CC-93 for
`+0x00..+0x15` and for tail fields `T[0x09]+0/+2/+4` (= `+0x1a/+0x1c/+0x1e`).
The new field `+0x16` is written in the `kind 0x15` pass:

```
if getbits(1): rec[0x16] = e13.off + getbits(PB_s13) * T[0x4c]
else:          rec[0x16] = prev[0x16]
PB_s13 = bits_needed(e13.count + 1)        # byte at -0x65dd($gp)
```

Consistent with the real block, where `+0x16` equals `e13.off` across all records
(`e13` empty, hence index 0).

**Effective bitstream order** in `db_pub+0x3d04`:

```
kind 0x14 : dec(e0), dec(e1), dec(e2), dec_B(e4),
            inline dec_C(e5), dec_D(e6), dec_E(e7), dec_F(e11),
            if getbits(1): dec_text()
PB_s13 = bits_needed(e13.count + 1)
kind 0x15 : dec(e0), dec_B(e4), inline e13 (record T[0x4c]=8: u32, ptr, 2 bytes), ...
kind 0x17 : dec(e2), dec(e1), dec(e0)
if getbits(1): dec_text()
if getbits(1): dec_text()
```

Disassembled and annotated listings are in `docs/fw/` (`mips_*.asm` for the
DB-REL 34 decoder, `m68k_pbp_decoders.asm` for CC-93), so transcription can
resume without redoing the analysis.

#### 9.11.7 Sub-revision Dependent Widths

The layout structure has an 8-byte header before the array indexed by `id`:
`LAYOUT[+0]` is DB-REL (`db_pub+0x1150`), `LAYOUT[+2]` a sub-revision
(`db_pub+0x1164`). **Certain field widths depend on the latter, not on data.**
In section 6 (`db_pub+0x4604`):

```
rec[T[0x10]]     = getbits(32)
rec[T[0x10] + 4] = getbits(14 if subrel < 9 else 16)
```

CC-93 hardcoded 14 because its sub-revision was always < 9. On `NAV_DB_21708`
(DB-REL 34) the correct value is **16**: with 14 the stream desynchronizes
halfway through section 6 and the remainder of the block turns to noise. This
was the single difference separating correct decoding from failure in 80% of
blocks.

The sub-revision is a property of the individual disc, not of the DB-REL. Another
disc whose superblock DB-REL (`+0x1A`, also shown in `BIBLIOGR`) is 34 (CD-ID
21594), and one whose DB-REL is 22 (CD-ID 2952), both need
**14 bits**. Without the `dec_text` guard, only 108/200 and 117/200 sampled blocks
passed the structural check with 16 bits; with 14, all of them do (1,200/1,200 and
600/600, with the guard applied). `cf1.probe.detect_subrel` / `CarinVolume.calibrate()`
recover it from the data by decoding a sample of type `0x00` blocks under both
widths and keeping the one that scores best on two checks: the section 4 →
section 7 shape pointers must be structurally consistent, and the section 2 name
pointers must land on real strings in the decoded text.

The shape-pointer check on its own cannot tell the widths apart once the
`dec_text` guard is in place: section 4 is decoded before the section 6 field,
so it scores 1.0 under both widths on all four discs tested, and the tie used to
resolve to 14 bits, which is wrong for CD-ID 21708. The name check separates
them because the text is decoded last:

| Disc | names hit, 14 bits | names hit, 16 bits | detected |
|---|---|---|---|
| CD-ID 2952 (DB-REL 22) | 1.00 | 0.04 | 14 bits (subrel 8) |
| CD-ID 21594 (DB-REL 34) | 1.00 | 0.19 | 14 bits (subrel 8) |
| CD-ID 21708 (DB-REL 34) | 0.02 | 1.00 | 16 bits (subrel 9) |
| CD-ID 21734 (DB-REL 34) | 0.00 | 1.00 | 16 bits (subrel 9) |

The type `0x0E` decoder has a second sub-revision dependent width: the S2 `val1`
field (a SECTION_4 byte offset in the linked `0x00` tile, stored `>> 1`) is
`getbits(13)` below sub-revision 9 and `getbits(15)` from 9. CC-93 hardcodes 13
(`moveq #$d`, `pbp+0x4248`). On CD-ID 21708 the `0x00` tiles need offsets up to
33,364, which 13 bits cannot hold: with 13 bits the `CF=1` `0x0E` blocks lose sync
at S2 (76% valid tile links, 16% valid house-number pairs over 15 blocks); with 15,
both are 100% on CD-IDs 21708 and 21734 (40 blocks each), while the CDs stay at
100% with 13. On these four discs sub-revision and sector unit always change
together, so the data alone does not say which of the two selects the width; the
decoder ties it to the sub-revision, like the section 6 field.

CD images also use a different sector unit: the database is a single `/carindb`
file and `BLOCK_ID`, length and `usize` count **2048-byte** sectors rather than
512. `CarinVolume` detects the layout from the image.

#### 9.11.8 Results

`scripts/cf1_sweep.py` decodes **1,200 `CF=1` blocks of type `0x00`** in
`NAV_DB_21708.ISO`: **1,200 produce a readable name blob geographically
consistent with the block's bbox**. Real examples:

```
sector 3157624  bbox lon -18.09..-17.81  lat 27.40..27.68   (El Hierro)
  españa · el pinar de el hierro · avenida marítima · calle dos la restinga
  calle juan gutiérrez monteverde
sector 3178407  (Algarve)
  portugal · lagoa · silves · cabeços · n125 · m1154 · faro
sector 3183947  (Alentejo)
  portugal · sines · a261 · bairro quinta dos passarinhos · n120
```

The oracle is not output length (§9.9.1 disproved it) but **content**:
the name blob sits at the end of the first pass, so real text implies that
prologue, verbatim sections, and bit-packed decoding of sections 0, 1, 2, 4, 5, 6,
7, and 11 are byte-for-byte exact. Cross-verification with bbox (§7)
rules out any coincidence: names correspond to the geographic tile of the block.

**Status**: types `0x00` and `0x0E` **resolved**. Type `0x0E` S2 layout verified
2026-09-19 via m68k write trace (`pbp+0x41c0`); see `docs/carindb/03-road-network.md`
§6.3.1. Remaining to be ported are types `0x14`/`0x15`/`0x16` (`db_pub+0x2a7c`),
which share the same structure but with a different set of sections. Implementation in
`carin/parser/cf1.py`, tools in `scripts/`:

| Script | Function |
|---|---|
| `os9_modules.py` | enumerates OS-9/OS-9000 modules (`4AFC` and `4DAD` sync) |
| `m68k_dis.py` | disassembles m68k **in 68040 mode** (required for `BFEXTU`) |
| `fw_xref.py` | xref of PC-relative constant strings |
| `os9_data.py` | static data area and resolution of `a6` references |
| `cf1_defaults.py` | extracts default layout table from firmware |
| `cf1_super.py` | extracts `RECORD_SIZE_TABLE` from disc superblock |
| `cf1_charmap.py` | extracts text decoder character table |
| `extract_firmware.py` | re-extracts firmwares containing the codec from `NAV_SW(v32).iso` |
| `fw_hunt_charmap.py` | searches for the codec across all files in a firmware ISO |
| `fw_arch_detect.py` | detects module CPU architecture |
| `mips_dis.py`, `mips_graph.py`, `mips_func.py` | disassembler, call graph, and annotated dump for MIPS modules |
| `cf1_layout_probe.py` | inspects real `CF=0` blocks to infer layout |
| `cf1_try.py` | decodes a single block and prints descriptor |
| `cf1_validate.py` | structural + text oracles on selected blocks |
| `cf1_sweep.py` | batch decodes and reports success rate |

#### 9.11.9 Hypotheses Not to Revisit

`docs/agents/agente_pdf.md` claims that `CF=1` is LZSS with a 4096 window
and 16-bit tokens, and that `CF=2` is handled by zlib in m68k firmware.
**This is false on both counts**: CC-93 firmware contains no zlib (no `inflate`
tables present) and never compares `COMPRESSION_FLAG` against 0/1/2 — it tests
`btst #0`. Its sole proof is "length matches", already refuted in §9.9.1.

---

## 10. Toolchain

| File | Function |
|---|---|
| `carin/parser/iso.py` | ISO 9660 reader (no mount needed), `CarinVolume` over `DB_0+DB_1` space, `CarinBlock`, `find_bbox`, `to_wgs84` / `to_carin` |
| `carin/parser/calibration.py` | `GeographicCalibrator` (Levenberg-Marquardt + grid search) |
| `carin/parser/compression.py` | `CompressionAnalyzer`, `LzssSweep`, `sweep_lzss`, `decode_lzw`, `decode_lz4_block`, `entropy`, `plain_prefix`, `score_output` |
| `scripts/extract_anchors.py` | extracts `(name, X, Y)` from `0x16` blocks |
| `scripts/optimize_coords.py` | calibration and residual verification |
| `scripts/analyze_codec.py` | analysis of `CF=1` codec on real ISO blocks |
| `scripts/find_pairs.py` | scans DB for plaintext/ciphertext pairs (identical bbox, differing CF) — outcome: none found, §9.6.1 |

```bash
python3 scripts/extract_anchors.py --out build/cities.pkl --names paris london roma
python3 scripts/optimize_coords.py
python3 scripts/analyze_codec.py --type 0x1E --count 1
```

---

## 11. Verification Roadmap

| # | Block / Topic | Status | Priority |
|---|---|---|---|
| 1 | Coordinate system | ✅ **RESOLVED** — `K = 2e9/360`, origin 30° W on the equator, rms 2.0 km across 38 anchors | — |
| 2 | POI `0x06` and feature `0x16` records | ✅ **RESOLVED** — 28 and 20 bytes, local scale 64 | — |
| 3 | Bounding box per block | ✅ **RESOLVED** — `find_bbox`, 60/60 on georeferenced types | — |
| 4 | `COMPRESSION_FLAG = 1` | ✅ **RESOLVED** — structure-driven bit-packing parameterized by superblock `RECORD_SIZE_TABLE`; decoder verified for `0x00`, `0x0E`, `0x14`–`0x16`. 1,200/1,200 `CF=1` type `0x00`; oracle 10/10 `0x16` CF=1 (1958 geo records); oracle 10/10 `0x0E` CF=1 S0/S1/S2. Firmware listing: `docs/fw/pbp_0x0E_decoder.asm`. | — |
| 5 | Field semantics in `0x0E` SECTION_0/1/2 | ✅ **RESOLVED (revised 2026-09-27)** — street-name directory: A=ptr→street name, C=0 or ptr→locality, D=ptr→S1; S2 = `0x00` tile (`BLOCK_ID`, centre X/Y) + SECTION_4 segment run + even/odd house-number ranges. Checked on CD-IDs 2952, 21594, 21708, 21734. FLAGS = kind of name, B = language code, S1 +3 = has house numbers (§6.3). See §6.3.2. | — |
| 6 | Georeferencing of parcels `0x0C`/`0x0E`/`0x10` (via `0x0D`/`0x0F`/`0x11`) | ✅ **RESOLVED** — `find_parcel(vol, X, Y) → sector` oracle 10/10 PASS 2026-09-19. Spatial index built from S2 `x_anc`/`y_anc`; cached in `dataset/parcel_index.npz`. **Key**: `0x0D`/`0x0F`/`0x11` are TEXT address-lookup indices (ASCII street/country codes → parcel record ranges), NOT geographic R-trees. See `scripts/find_parcel.py`. | — |
| 7 | Mapping `BLOCK_TYPE → section_type[]` | not present in data | 🟠 high |
| 8 | Resolution of `NAME_PTR` high16 (country table) | 6 unidentified segments | 🟡 medium |
| 9 | Order/role of the 5 `u16` in type `0x04` | UNKNOWN | 🟡 medium |
| 10 | Block checksum / CRC | **none found** | 🟢 no risk |
