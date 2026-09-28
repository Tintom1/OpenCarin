# Part 4 — `COMPRESSION_FLAG = 1` Codec — RESOLVED

> **Status: ✅ RESOLVED — decoder and serializer complete** (2026-09-19).
> Block types `0x00`, `0x0E`, `0x14`–`0x16` and `0x1C`–`0x1E` decoded (the last six
> re-transcribed from the RoadRunner firmware on 2026-09-28, §9.11.11; `0x00` completed from it
> the same day: pass `0x15` sentinel and pass `0x1B`, §9.11.12); `0x0E` CF=1 serializer
> (`encode_type0E`) oracle 10/10 PASS. No remaining ports needed for routing.
> For the exhaustive list of *falsified* codec hypotheses (do not re-attempt),
> read [`05-failed-attempts.md`](05-failed-attempts.md) **before** trying anything here.
>
> Source: `../CARINDB_BLUEPRINT_EN.md` §9.11. Firmware listings: `docs/fw/`.
> Implementation: `carin/parser/cf1/`.

---

## The one-line answer

`CF=1` (96,011 blocks, 30% of the disc) that resisted six algorithm families and
650+ parameter variants **is not a compression codec**. It is **structure-driven
bit-packing tailored to the block structure**: each section has its own decoder
that reconstructs fixed-size records by reading minimal-width fields from an
**MSB-first bitstream**, converting record *indices* into absolute offsets. Record
sizes come from the superblock's `RECORD_SIZE_TABLE` (see [`01-architecture.md`](01-architecture.md) §3.2).

The decoder was found in the navigation unit's original firmware: module `pbp`
(CARIN CC-93, m68k/OS-9) and `db_pub` (Mk3/RR, MIPS32/OS-9000).

**Verification**: 1,200 `CF=1` blocks of type `0x00` decoded → 1,200 with a
readable name blob consistent with the block's bbox (El Hierro, Algarve, Alentejo,
with real street names and road codes).

### Why every previous hypothesis was wrong (and now consistent)

| Observation | Explanation under bit-packing |
|---|---|
| 1.33–2.65× ratio only | only high bits of fields are omitted, no dictionary |
| entropy 7.17–7.84 bits/byte | bit-packed fields, no residual redundancy |
| shared 8-grams across blocks | identical field patterns at the same bit phase |
| zero plaintext leakage | names use a dedicated prefix encoder |
| every LZ/Huffman family falsified | all were the wrong hypothesis |

---

## 9.11.1 Where the decoder resides

| Firmware | Path in ISO | Module | CPU | DB-REL |
|---|---|---|---|---|
| CARIN CC-93 0560 | `/CC93_/0560/nav_sw_load` | `pbp` @ `0x58ed0` | m68k (OS-9/68K) | 14–17 |
| Mk2C / Mk2M | `/Mk2C/0211/BMW/app_sw/bsw_load` | `pbp` @ `0x34130` | m68k (OS-9/68K) | 14–22 |
| Mk3 | `/Mk3/0127/BMWC01S/app_sw/bsw_load` | `db_pub` @ `0x7d488` | **MIPS32 BE** (OS-9000) | ≥ 34 |
| RR / V_2 | `/V_2/RR/0101/BMWC01S/app_sw/bsw2` | `db_pub` @ `0x917c8` | MIPS32 BE | ≥ 34 |

The decoder is **not** in `dbd`, `dbq`, `dbc` (daemon, query, cache). `Mk3`/`RR`
`usw_load` modules are the MMI side and do not contain the codec.

**Unique codec signature** — the text decoder's 42-byte character table, identical
across all firmwares:

```
61 65 | 73 74 72 00 | 20 64 67 68 69 6c 6e 6f | e0 e1 … fd ac
 a  e |  s  t  r NUL |  SP d  g  h  i  l  n  o | à á … ý ¬
```

A frequency-tailored code for European street names: `a`/`e` in 1 bit, `s t r NUL`
in 2, `SP d g h i l n o` in 3, accented Latin-1 in 7. Searching for these 42 bytes
is the fastest way to locate the codec in any firmware (`scripts/fw_hunt_charmap.py`).

## 9.11.2 Primitives (offsets in CC-93 `pbp`)

```
0x3660  uncompressed_sectors(hdr)   bit 0 of hdr[6] -> hdr[7] otherwise blockid&0xff
0x3698  dispatch: if hdr[6]&1 -> init + switch on BLOCK_TYPE:
        - 0x00:                 branch 0x36b4 -> bsr 0x3ea0 (decode_type00)
        - 0x0E:                 branch 0x36be -> bsr 0x4320 (decode_type0E)
        - 0x14, 0x15, 0x16:     branch 0x36c8 -> bsr 0x46aa
        - others > 0x0E (0x10, 0x12, etc.): branch 0x36d2 -> pass length*2048, bsr 0x6a06 (memset 0 — buffer zeroed because non-rendered)
        otherwise (CF=0): branch 0x3726 (memcpy raw sectors)
0x4798  init(src)        PTRBITS = bits_needed(usize * SECTOR)   [CC-93: SECTOR=2048]
0x47da  copy_raw(dst,n)  memcpy from raw cursor, cursor += n
0x4800  copy_section(base, entry, recsize, plus1)
0x49a8  bits_init()      base = current cursor, bitpos = 0
0x49bc  getbits(n)       BFEXTU (a0){bitpos:n}  -> MSB-first
0x4a68  bits_needed(n)   bits to represent 0..n-1, 16-bit arithmetic
```

`getbits` uses **68020 bitfield instructions** (`BFEXTU`, opcode `E9D0`). This is
why earlier sessions missed it: capstone in `CS_MODE_M68K_000` renders them as
`.dc.w`. **`CS_MODE_M68K_040` is required.**

`PTRBITS` = bit width of an internal block pointer = `ceil(log2(UNCOMPRESSED_SIZE * 512))`.
For a 10,752 B block it is 14 (vs 16 bits of the decompressed field) — hence the compression.

## 9.11.3 Superblock `RECORD_SIZE_TABLE` parameterizes the decoder

`pbp+0x3582` reads the superblock: descriptor at `+0x28` = `{u16 offset, u16 count}`,
then `count` pairs `{u16 id, u16 value}` that **override** hardcoded defaults
(`pbp+0x33ea`, extract via `scripts/cf1_defaults.py`). This is the `RECORD_SIZE_TABLE`
of [`01-architecture.md`](01-architecture.md) §3.2.
- In **m68k firmware** (`pbp` / `db_pub`), the table is copied into the module's Global Data Area at `-$71cc(a6)` and accessed as `-(0x71cc - 2*idx)(a6)`.
- In **MIPS firmware**, the table is pointed to by `-0x7900($gp)` with `field(X) = T[(X-8)/2]`.

Entries used by the type `0x00` decoder (CC-93 default → DB-REL 34 actual):

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
lengths match exactly, including the sentinel record (`e3 = (count+1)·4`, `e4 = (count+1)·32`).

## 9.11.4 `decode_type00` — structure

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

Recurring field encodings:
* **internal pointer**: `target_section_off + getbits(PB_target) * recsize` (record
  index, not offset) — with `index == count` used as `NULL`;
* **even offset**: `getbits(PTRBITS-1) << 1`;
* **inheritance**: 1-bit flag; if 0 the field is copied from the preceding record
  (in `dec_B` the whole record starts as a copy of the previous one);
* **coordinates** (`dec_C`/`dec_D`/`dec_E`): first record absolute 16-bit, then
  `1 bit`→absolute/delta, `1 bit`→sign, `getbits(widths[1])` magnitude;
* **block cache**: two values (pointers to `e7` and `e2`) initialized to 1 and
  re-emitted until a flag updates them.

## 9.11.5 Text decoder (`pbp+0x4862`) — the strongest oracle

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

The name blob sits at the **end** of the bitstream, so if readable text emerges,
everything before it decoded correctly. This is the primary validation oracle
(output length is NOT a valid oracle — see [`05-failed-attempts.md`](05-failed-attempts.md) §9.9.1).

## 9.11.6 DB-REL 34 differences and port status

The m68k decoder (CC-93/Mk2C) is **insufficient** for DB-REL 34 discs: records grew
(`T[0x08]` 28→32, `T[0x40]` 6→10) and extra fields are unwritten. The correct
decoder is the **MIPS one in `db_pub`** (Mk3/RR), same structure but **multiple
passes**: each section is traversed several times with a `kind` arg (`0x14`,`0x15`,`0x17`)
selecting which field group to read. Sequence (`db_pub+0x3d04`, Mk3 0127):

```
kind 0x14: dec_e0, dec_e1, dec_e2, dec_B, [dec_C/dec_D/dec_E inlined]
kind 0x15: dec_e0, dec_B, ...
kind 0x17: dec_e2, dec_e1, dec_e0
if getbits(1): dec_text()      # two text blobs, not one
```

Type `0x00` descriptor has **15 entries** in DB-REL 34 (`e0..e14`), vs 13 in CC-93;
`e13`/`e14` are the new sections.

**Sections 0/1/2** — three functions (`db_pub+0x2f30/+0x30dc/+0x3270`), 10 B records,
`PTRBITS` a byte at `-0x6635($gp)`:

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

In `kind 0x14` of `e0` the two fields are read and **discarded** — the stream still
contains them (a DB-REL ≤ 22 reader would use them) but the new reader overwrites
them in passes `0x15`/`0x17`. Backward compatibility, not a bug.

**Sticky delta** (`e2`, `kind 0x17`) — two independent accumulators:

```
delta = 0 ; acc = 0
per record:  if getbits(1): delta = (getbits(PTRBITS-1) << 1) & 0xffff
             rec[k] = acc = (delta + acc) & 0xffff
```

Verified vs real `CF=0` block: `e2.rec[6]` = `0,0x2ec,0x2f0,0x2f4,0x2f8,0x2fc`
→ steps `0,0x2ec,4,4,4,4`; `e2.rec[8]` = `0,4,4,4,4,4`. Steps always even (`<<1`).

**Section 4** (`db_pub+0x348c`), 32 B records: identical to CC-93 for `+0x00..+0x15`
and tail fields `T[0x09]+0/+2/+4` (= `+0x1a/+0x1c/+0x1e`). New field `+0x16` written
in the `kind 0x15` pass:

```
if getbits(1): rec[0x16] = e13.off + getbits(PB_s13) * T[0x4c]
else:          rec[0x16] = prev[0x16]
PB_s13 = bits_needed(e13.count + 1)        # byte at -0x65dd($gp)
```

**Effective bitstream order** (Mk3 `db_pub+0x3d04`; RR `sub_005e6c`, §9.11.12):

```
kind 0x14 : dec(e0), dec(e1), dec(e2), dec_B(e4) + sentinel record,
            inline dec_C(e5), dec_D(e6), dec_E(e7), dec_F(e11) if e11.count,
            dec_text()                                   # no flag (RR +0x6a94)
PB_s13 = bits_needed(e13.count + 1)
kind 0x15 : dec(e0), dec_B(e4) + sentinel record,        # Mk3 +0x3c50, RR +0x5db8
            inline e13 (record T[0x4c]=8: u32, ptr, 2 bytes)
kind 0x17 : inline e14, dec(e2), dec(e1), dec(e0)
if getbits(1): dec_text()
if getbits(1): dec_text()
kind 0x1B : dec_B(e4), no sentinel                       # RR only, DB-REL >= 27
# DB-REL 34: one 1 bit, then zeros to the end of the block (read by no firmware)
```

Annotated listings in `docs/fw/` (`mips_*.asm` for DB-REL 34, `m68k_pbp_decoders.asm`
for CC-93) so transcription can resume without redoing analysis.

## 9.11.7 Sub-revision dependent widths (the 80%-of-blocks bug)

The layout structure has an 8-byte header before the id-indexed array:
`LAYOUT[+0]` = DB-REL (`db_pub+0x1150`), `LAYOUT[+2]` = sub-revision (`db_pub+0x1164`).
**Certain field widths depend on the sub-revision, not on data.** In section 6
(`db_pub+0x4604`):

```
rec[T[0x10]]     = getbits(32)
rec[T[0x10] + 4] = getbits(14 if subrel < 9 else 16)
```

CC-93 hardcoded 14 (its subrel was always < 9). On `NAV_DB_21708` (DB-REL 34) the
correct value is **16**: with 14 the stream desyncs halfway through section 6 and
the rest of the block becomes noise. **This single difference separated correct
decoding from failure in 80% of blocks.**

The sub-revision is **per disc, not per DB-REL**. Another disc whose superblock
DB-REL (`+0x1A`, also shown in `BIBLIOGR`) is 34 (CD-ID 21594), and one whose
DB-REL is 22 (CD-ID 2952), both need **14 bits** (subrel < 9):
without the `dec_text` guard, only 108/200 and 117/200 sampled blocks passed the
shape-pointer check with 16 bits; with 14, all of them do (1,200/1,200 and 600/600,
with the guard applied). Since the value is not read from the block,
`cf1.probe.detect_subrel` (and `CarinVolume.calibrate()`) picks it from the data:
it decodes a sample of type `0x00` blocks both ways and keeps the one that scores
best on two checks: section 4 → section 7 shape pointers that are monotone, stay
inside section 7 and step in whole records; and section 2 name pointers that land
on real strings in the decoded text.

With the guard in place the shape-pointer check alone scores 1.0 under both
widths on all four discs tested, because section 4 is decoded before the section 6
field, and the tie used to resolve to 14 bits, which is wrong for CD-ID 21708. The
text is decoded last, so the name check separates them:

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

The same discs also differ in the sector unit: CD images keep the database in a
single `/carindb` file and count `BLOCK_ID`, length and `usize` in **2048-byte**
sectors, not 512. `CarinVolume` detects this from the image layout; decoding a
CD block with `sector_size=512` fails outright (output buffer too small).

## 9.11.8 Results

`scripts/cf1_sweep.py` decodes **1,200 `CF=1` blocks of type `0x00`** in
`NAV_DB_21708.ISO`: **1,200 produce a readable name blob geographically consistent
with the block's bbox**. Examples:

```
sector 3157624  bbox lon -18.09..-17.81  lat 27.40..27.68   (El Hierro)
  españa · el pinar de el hierro · avenida marítima · calle dos la restinga
  calle juan gutiérrez monteverde
sector 3178407  (Algarve)
  portugal · lagoa · silves · cabeços · n125 · m1154 · faro
sector 3183947  (Alentejo)
  portugal · sines · a261 · bairro quinta dos passarinhos · n120
```

The oracle is **content**, not length: real text implies prologue, verbatim
sections, and bit-packed decoding of sections 0,1,2,4,5,6,7,11 are byte-exact.
Cross-check with bbox rules out coincidence.

**Status**: all routing-relevant block types **resolved**.
- `0x00` (map drawing): decoder verified on 1,200 blocks (1,200/1,200 readable names).
  That check only covers pass `0x14`: passes `0x15`/`0x17` were misaligned until 2026-09-28;
  now every CF=1 `0x00` block of 21708 and 21734 passes `oracle_00.py` (§9.11.12).
- `0x0E` (road parcels): decoder + **encoder** (`encode_type0E`) — round-trip oracle 10/10 PASS 2026-09-19.
- `0x14`–`0x16`, `0x1C`–`0x1E` (scale layers): every block of both DVDs passes the
  structural oracle (§9.11.11). The 2026-09-19 claim "1,958/1,958 records with X/Y in
  European range" was withdrawn: that check fails on plain blocks too, and the decoder
  then in use was incomplete.

Type `0x0E` oracle (2026-09-18): 67/67 CF=1 blocks pass structural validation
(bad_D=0, bad_S2ptr=0) across usize 7–96. Key finding: m68k asm subroutines at
`$49e8`/`$49fc` were annotated as getbits(4)/getbits(8) but DB-REL 34 uses
**2 bits** (FLAGS_lo) and **3 bits** (B). See `docs/carindb/03-road-network.md` §6.3.1.

Type `0x0E` Section 2 oracle (2026-09-19): ground-truth write trace from m68k firmware
(`pbp+0x41c0`). The 24-byte record stores **raw anchor + raw deltas** — not pre-computed
coordinates. Layout: `+0` i32 x_anc; `+4` i32 y_anc; `+8..+14` 4×u16 raw_delta[0..3]
(width = `is_16?16:M_hi`, `is_16` consumed from bitstream but NOT stored); `+16` i32
anchor_f2 (anchor bytes 8–11, previously missing); `+20` u16 val1 = `getbits(13)<<1` (15 bits from sub-revision 9);
`+22` u16 val2 = `getbits(M_lo)`. End-to-end check sector 2252227: 0/133 bad anchor
indices, 556/556 non-zero val1/val2. See `docs/carindb/03-road-network.md` §6.3.1 for
full verified layout table and `docs/fw/pbp_0x0E_decoder.asm` for write trace.
The bitstream layout stands; the field *meaning* was revised on 2026-09-27: `raw_delta`
are house-number ranges, `anchor_f2` is a `0x00` `BLOCK_ID`, `val1`/`val2` are a
SECTION_4 offset and count. `val1` is 15 bits from sub-revision 9 (§9.11.7); with
that, the `CF=1` S2 decode is 100% consistent on all four discs tested.

## 9.11.9 `encode_type0E` — CF=1 serializer (STEP 4, ✅ 2026-09-19)

`carin/parser/cf1.py` — `encode_type0E(decoded, table, dbrel) → bytes`.

**Algorithm** (inverse of `decode_type0E`):

1. Read section entries `e0/e1/e2` from `decoded[table[T_DESC_BASE]…]`.
2. **Anchor table**: scan all S2 records, collect unique 12-byte signatures
   (`decoded[base:base+8] + decoded[base+16:base+20]`) in first-appearance order
   → `count_N` anchors → `raw_12`.
3. **M_hi**: `max(1, bits_needed(max_non_sentinel_delta + 1))` across all
   `has_deltas=True` S2 records. Sentinel detection: all 4 deltas == `0x7FFF`.
4. **M_lo**: `max(1, bits_needed(max_val2 + 1))` across all S2 records.
5. `BitWriter` (MSB-first, inverse of `BitReader`): encode S0, S1, S2 bitstream.
6. Assemble: `prolog` (CF restored to 1, usize from `len(decoded)//512`) +
   `pre_hdr` (count_N u16 + raw_12 + M_hi + M_lo) + bitstream + padding to
   sector boundary. Fix `block_id` sector field; update length-in-sectors.

**Round-trip guarantee**: `decode_block(encode_type0E(dec, t, r), t, r)[4:] == dec[4:]`
(bytes 0–3 = block_id legitimately differ if encoded size changes; bytes 4–7 =
btype/cf/usize are identical after decode_block zeroes cf and usize).

**Oracle**: `scripts/oracle_encode_0e.py` — 10/10 CF=1 `0x0E` blocks, PASS.
Re-encoded blocks are 30–40% smaller than originals because M_hi/M_lo are derived
from the actual data distribution, whereas the original encoder used conservative
fixed widths.

## 9.11.10 Hypotheses NOT to revisit

`docs/agents/agente_pdf.md` claims `CF=1` is LZSS (4096 window, 16-bit tokens) and
`CF=2` is zlib handled in m68k firmware. **False on both counts**: CC-93 firmware
contains no zlib (no `inflate` tables) and never compares `COMPRESSION_FLAG` against
0/1/2 — it tests `btst #0`. Its only proof was "length matches", refuted in
[`05-failed-attempts.md`](05-failed-attempts.md) §9.9.1.

## 9.11.11 Scale layers `0x14`–`0x16`, `0x1C`–`0x1E` — RoadRunner decoder (2026-09-28)

**Dispatch.** `scripts/firmware/rr_cf1_dispatch.py` decodes the CF=1 jump table of
RR `db_pub` (`bsw2` 0101, module at `0x917c8`): `sub_002a48` tests `hdr[6..7] & 0xf00`
(`== 0x100` → table, `== 0x200` → zlib `sub_006ee8`), then `sltiu $ra, type, 0x2a`
at `+0x2aa4`, table at `+0x2acc`:

| types | case | decoder |
|---|---|---|
| `0x00` | `+0x2b74` | `sub_005e6c` |
| `0x0E` | `+0x2b84` | `sub_003c9c` or `sub_003a3c` (byte `L+0x193`) |
| `0x14`, `0x15`, `0x16`, `0x1C`, `0x1D`, `0x1E` | `+0x2bc8` | `sub_004b88` |
| `0x29` | `+0x2bb8` | `sub_003e18` |
| others < `0x2a` | `+0x2be4` | buffer cleared (`sub_00c198`) |

Identical in `bsw2` 0101 BMWC01S, 0101 BMWM01S and 0103 BMWOCN (same `db_pub` bytes);
0102 BMWOCN is an older `db_pub` (31 cases, no `0x29`) with the same grouping
(`sub_004558`). The layout table seen by RR is `L = gp[-0x7f24]`, `L+0x14` DB-REL
(`sub_002930`), `L+0x16` sub-revision (`sub_002980`), `T[id]` at `L + 0x1e + 2·id`
(checked against the superblock: `L+0x98` = `T[0x3d]` = 52, `L+0x94/0x92/0x96` =
`T[0x3b/0x3a/0x3c]` = 4/20/16, `L+0x9c` = `T[0x3f]` = 24).

**`sub_004b88`**, with `sub_004228(dst, entry, recsize, kind, pass)` per section:

```
copy_raw(T[0x3d])                           prologue; pb_s3 = bits_needed(e3.count + 1)
raw4 = copy_raw(4)                          [0] S2 +4 width, [1] S1 +4 width, [2] S3 delta width
bits_init()
S0 kind 0x80, S1 kind 0x7f, S2 kind 0x81    pass 0x0e
S3 kind 0xae (8 B abs) | 0xac (4 B delta)   selector u16 at T[0x05]+T[0x3f]+0x10
dec_text                                    sub_002ec8, same code as pbp+0x4862
if DB-REL >= 0x14: w5 = 5 x getbits(8); e4 kind 0x17 (T[0x15]); S1, S2 pass 0x14
if DB-REL >= 0x17: e5 kind 0x10 (T[0x59]); S1, S2 pass 0x17;
                   if getbits(1): dec_text; if getbits(1): dec_text
```

`sub_004228` returns at once when `count == 0` (`+0x4280`) and runs count + 1 records
for kinds `0x7f/0x80/0x81` (`+0x42a8..0x42dc`), count for the others. Fields per pass
are in `carin/parser/cf1/decoder_14.py`; pass 0x14 on S1 reads `getbits(1) ?
getbits(16) : getbits(w5[0])` and stores nothing (`+0x46ec..0x4720`).

**What the CC-93 port got wrong** (`pbp+0x46aa`, the decoder used until 2026-09-28):
it stopped after the first pass, so e4, e5, S1 `+0x10/+0x12` and S2 `+0x08..+0x0c`
were never decoded; and it decoded one record of an empty S0/S1/S2 at the entry's
offset 0, overwriting header and descriptor (sector 6449842 on 21708: `e1 = (0, 0)`,
the S1 record written at 0 turns `e0` into `off = 17068`). With it, 0 of 25,988
CF=1 blocks passed the oracle below.

**One pass the firmware does not read.** After the last text flag, bits remain
exactly in the blocks whose S2 is non-empty (17,775 of 25,988 CF=1 blocks on the two
DVDs; none of the others). Plain blocks carry a S2 `+0x0e` u16 that no pass above
writes. Reading, for each of the count + 1 S2 records, `getbits(1) ? getbits(16) :
previous value` consumes every remaining set bit in all 17,775 blocks. Checks:
the first record always carries a value (8,544/8,544 and 9,231/9,231); an explicit
value never equals the previous one (28,634 and 29,109, none equal); the terminator
ends at 0 (as on all plain blocks); plain blocks keep the previous value on 96.7%
of records, packed ones on 96.9%. Example: sector 6128051 (21708, `0x16`, one S2
record) ends `1 0000000011000100 1 0000000000000000`: `+0x0e` = 196, then 0. This is
derived from the data, not from firmware (`decoder_14._s2_tail`); no available RR
build reads it. Its meaning is unknown.

**Oracle** — `scripts/routing/oracle_14_16.py`, independent of the decoder (layout from
the descriptor and `vol.layout`). Checks and their source are listed in its
docstring: sections contiguous from the prologue; S0 → S1/S2 on record boundaries
(02-geo.md §8.4); S1/S2 → S3 on boundaries, non-decreasing, first/last = S3 start/end;
S3 local points inside the bbox (`x << u16[0x32]`); S1 X/Y inside the disc range (union
of the six types' bboxes); names at string starts; S2 `+8` on e4 boundaries; S1 `+0x12`,
S2 `+0x0c` on e5 boundaries or 4; S1 `+0x10` = 0; S2 `+0x0e` terminator 0 and never
changing to 0; for CF=1 also text ranges after the sections and zero padding after the
last bit read.

| disc | type | CF=0 | CF=2 | CF=1 |
|---|---|---|---|---|
| 21708 | `0x14` | 145/145 | 27/27 | 186/186 |
| 21708 | `0x15` | 1,608/1,608 | 1,457/1,457 | 1,446/1,446 |
| 21708 | `0x16` | 6,276/6,276 | 666/666 | 7,719/7,719 |
| 21708 | `0x1C` | 579/579 | 564/564 | 318/318 |
| 21708 | `0x1D` | 72/72 | 20/20 | 80/80 |
| 21708 | `0x1E` | 38/38 | 1/1 | 14/14 |
| 21734 | `0x14` | 96/96 | 51/51 | 250/250 |
| 21734 | `0x15` | 992/992 | 1,628/1,628 | 2,265/2,265 |
| 21734 | `0x16` | 3,840/3,840 | 983/983 | 11,049/11,049 |
| 21734 | `0x1C` | 418/418 | 643/643 | 544/544 |
| 21734 | `0x1D` | 40/40 | 44/44 | 103/103 |
| 21734 | `0x1E` | 38/38 | 1/1 | 14/14 |

The old check (S1 X/Y inside 20° W–50° E, 25–75° N, `--legacy-eu`) fails on 4,499 of
10,116 plain `0x16` blocks (CF=0 2,530/6,276 on 21708, 1,969/3,840 on 21734): S1 X/Y
are points of the whole disc (up to 196° E, 86° N), not of Europe. It was the ~17%
CF=1 "anomaly" (1,002/7,719 and 2,295/11,049 with the new decoder, which passes
everything else). `scripts/routing/layer_stats.py` compares CF=1 with CF=0/2 per type
(category codes, records per section, S3 record size, named records).

Not covered: 8-byte S3 records never occur on these discs (all 46,215 blocks use 4 B),
so the absolute branch (`kind 0xae`) is transcribed but untested; DB-REL < 34 discs
(CD-ID 2952, 21594) were not run here.

## 9.11.12 Type `0x00` on the RoadRunner: pass `0x15` sentinel and pass `0x1B` (2026-09-28)

`decode_type00` was ported from the **Mk3** (`db_pub+0x3d04`, 0127). The RR decoder of
`0x00` is `sub_005e6c` (`bsw2` 0101, dispatch case `+0x2b74`,
`scripts/firmware/rr_cf1_dispatch.py`); section helpers `sub_005038` (S0), `sub_0051e4`
(S1), `sub_005378` (S2), `sub_005594` (S4, `kind` in `$a2`). Listing:
`python scripts/firmware/mips_listing.py build/fw/V_2_RR_0101_BMWC01S_app_sw_bsw2 db_pub out.asm`.

Pass by pass, the RR matches the port (prologue `T[0x0b]`, `PB_*` from `e2.count`,
`e4/e7/e10/e11/e12.count + 1`, two raw widths, verbatim S3 (+1 record), S9, S10, S12 if
`e12.count`; S0/S1/S2/S4 pass `0x14`; inline S5 `+0x6228`, S6 `+0x64e0` (14/16 bits by
`subrel`, `+0x676c`), S7 `+0x6800`, S11 `+0x69e4` if `e11.count`; `dec_text` with **no**
flag `+0x6a94`; if DB-REL ≥ `0x15`: `PB_s13`, S0 and S4 pass `0x15`, inline S13 `+0x6b68`;
if DB-REL ≥ `0x17`: inline S14 `+0x6c40`, S2, S1, S0 pass `0x17`, two flagged `dec_text`
`+0x6e08`/`+0x6e3c`), except for two points:

1. **Pass `0x15` reads the sentinel record.** After the record loop, `sub_005594` reads the
   sentinel's `+0x16` for `kind == 0x15` too (`+0x5db8..0x5e3c`: flag, then
   `e13.off + getbits(PB_s13) · T[0x4c]`, else the previous record's). The Mk3 does the same
   (`+0x3c50..0x3cd4`); the port stopped one record short. `docs/fw/mips_dec_B.asm` ends
   before that code.
2. **Pass `0x1B`.** `sub_005e6c +0x6e70`: if DB-REL ≥ `0x1B`, `sub_005594(dst, e4, 0x1b)`.
   Per section 4 record, no sentinel (`+0x5b5c..0x5bc8`):
   ```
   if getbits(1): rec[0x18] = getbits(8); rec[0x19] = getbits(8)
   else:          rec[0x18] = prev[0x18]; rec[0x19] = prev[0x19]
   ```
   The firmware's "previous" pointer starts at 0 (`+0x563c`), so a first record without the
   flag would copy from address 0x18; on the discs the first flag is always set. The pass is
   in RR 0101 BMWC01S/BMWM01S and 0103 (`+0x6e80`) and 0102 (`+0x6850`), in no Mk3 build
   (0103, 0107, 0116, 0127: no `slti …, 0x1b` in `db_pub`).

**Effect of point 1.** Without the sentinel bit(s) every later read is shifted: S13, pass
`0x17` (S14 name index, S0/S1/S2 offsets) and the two text flags come out wrong. With the
port as it was, **0 of 86,107 (21708) and 0 of 91,651 (21734)** CF=1 tiles passed the oracle
below; every one failed `s4_ptr` (sentinel `+0x16` = 0) and `names` (S14). The misread flags
started `dec_text` with garbage ranges, which is what the `floor` guard in `dec_text` had been
added against (the "~8% of blocks" overwrite). On the invariant sample (300 CF=1 tiles per
disc, seed 1) `name_pointer_score` was 0.549 on sector 4072845 (21734): a spurious second
`dec_text` (41043, 42240) wrote into the real name blob (40940, 43732); now 1.0.

**After pass `0x1B`** every CF=1 tile of both discs holds exactly one 1 bit, then zeros to the
end of the block. No firmware reads it. It is not an encoded sentinel record for pass `0x1B`:
in the 300-tile samples the first segment is explicit in 300/300, an explicit value never
equals the previous one (0 of 7,003 and 7,211), yet the 1 bit follows in the 240 and 226 tiles
whose last segment is 0, where a sentinel `0x0000` would have been an explicit repeat.

**The "head".** The earlier description of the packed `+0x18` pass (a head of unknown content,
median 18 bits on CD-ID 21594, before the flag + u16 records) measured from the end of the
misaligned pass `0x17`. Measured the same way with the old port on the 300-tile samples it is
2–1,165 bits, median 23 (21708) and 24 (21734). In the aligned stream the gap is the two
`dec_text` flags, plus a text blob when the second one is set (31/300 and 43/300 tiles; the
first flag was never set). Those blobs hold exonyms: sector 3522859 (21734) `seviglia`,
`sevil'ya`, `sevilha`, `seville`, `sewilla`; sector 5766936 (21708) `norrbotten` in six
languages.

**Oracle** — `scripts/codec_cf1/oracle_00.py`, independent of the decoder (layout from the
descriptor and `vol.layout`; checks in its docstring): sections in index order from
`T[0x0b]`, 4-byte aligned, S3/S4 with count + 1 records; S4 → S5/S6 nodes, → S7 (non-decreasing,
sentinel = S7 end), → S4 next segments, → S10/S12/S13/S11 (non-decreasing, sentinel = end);
S4 → S2; S5/S6 → S4; names at string starts (S2, S14); pass `0x17` S1 `+6/+8` on S14 boundaries
and S0 `+4`, S2 `+6/+8` non-decreasing; `+0x18` low byte 0 and sentinel 0; for CF=1, text
ranges after the sections and, after the last bit read, one 1 bit and zeros.

| disc | CF=0 | CF=2 | CF=1 (before) | CF=1 (now) |
|---|---|---|---|---|
| 21708 | 858/858 | 4,791/4,791 | 0/86,107 | 86,107/86,107 |
| 21734 | 809/809 | 6,895/6,895 | 0/91,651 | 91,651/91,651 |

**`+0x18` against the plain tiles** (`scripts/codec_cf1/pass18_baseline.py`, plain by default,
`--cf 1` for the decoder's output; 21708 / 21734):

| | plain (CF=0/2) | packed (CF=1) |
|---|---|---|
| segments | 2,643,784 / 3,791,013 | 39,760,087 / 42,299,606 |
| values (high byte) | 1–7, `0x10`–`0x13` (+ `0x14` ×2 on 21734) | 1–7, `0x10`–`0x14` |
| `+0x19` (low byte) | always 0 | always 0 |
| `+0x18 & 3` = role from `+0x0B` | 99.89% / 99.75% | 99.95% / 99.90% |
| exceptions | only role 0 with `& 3` ≠ 0 | same, only that direction |
| repeats previous segment | 94.7% / 94.5% | 95.3% / 95.0% |
| first segment non-zero | 4.5% / 3.9% | 1.9% / 2.0% |

Two differences are not explained: `0x0400` is more frequent on class 5 (plain 12.3%, packed
36.2% on 21708; 13.6% / 40.9% on 21734), and packed tiles carry `0x0400` on classes 0–2
(137 and 2,079 segments; plain 0 and 5). In a 10,000-tile sample the latter sit in few tiles
(5 on 21708, 14 on 21734) near the end of the `0x00` sector range (21734: sectors
6,284,872–6,285,447), mostly class 0 with `+0x0B` 0xB, `+0x11` `0x20`.
