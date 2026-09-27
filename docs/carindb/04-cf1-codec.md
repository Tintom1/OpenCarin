# Part 4 — `COMPRESSION_FLAG = 1` Codec — RESOLVED

> **Status: ✅ RESOLVED — decoder and serializer complete** (2026-09-19).
> Block types `0x00`, `0x0E`, `0x14`/`0x15`/`0x16` decoded; `0x0E` CF=1 serializer
> (`encode_type0E`) oracle 10/10 PASS. No remaining ports needed for routing.
> For the exhaustive list of *falsified* codec hypotheses (do not re-attempt),
> read [`05-failed-attempts.md`](05-failed-attempts.md) **before** trying anything here.
>
> Source: `../CARINDB_BLUEPRINT_EN.md` §9.11. Firmware listings: `docs/fw/`.
> Implementation: `carin/parser/cf1.py`.

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

**Effective bitstream order** (`db_pub+0x3d04`):

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
with 16, only 108/200 and 117/200 sampled blocks pass the structural check
described next; with 14, all of them do (1,200/1,200 and 600/600, with the
`dec_text` guard applied). Since the value is not read from the block,
`cf1.probe.detect_subrel` (and `CarinVolume.calibrate()`) picks it from the data:
it decodes a sample of type `0x00` blocks both ways and keeps the one whose
section 4 → section 7 shape pointers are monotone, stay inside section 7 and step
in whole records.

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
- `0x0E` (road parcels): decoder + **encoder** (`encode_type0E`) — round-trip oracle 10/10 PASS 2026-09-19.
- `0x14`/`0x15`/`0x16` (geo labels): decoder verified 2026-09-19, 1,958/1,958 records with X/Y in European range.

Type `0x0E` oracle (2026-09-18): 67/67 CF=1 blocks pass structural validation
(bad_D=0, bad_S2ptr=0) across usize 7–96. Key finding: m68k asm subroutines at
`$49e8`/`$49fc` were annotated as getbits(4)/getbits(8) but DB-REL 34 uses
**2 bits** (FLAGS_lo) and **3 bits** (B). See `docs/carindb/03-road-network.md` §6.3.1.

Type `0x0E` Section 2 oracle (2026-09-19): ground-truth write trace from m68k firmware
(`pbp+0x41c0`). The 24-byte record stores **raw anchor + raw deltas** — not pre-computed
coordinates. Layout: `+0` i32 x_anc; `+4` i32 y_anc; `+8..+14` 4×u16 raw_delta[0..3]
(width = `is_16?16:M_hi`, `is_16` consumed from bitstream but NOT stored); `+16` i32
anchor_f2 (anchor bytes 8–11, previously missing); `+20` u16 val1 = `getbits(13)<<1`;
`+22` u16 val2 = `getbits(M_lo)`. End-to-end check sector 2252227: 0/133 bad anchor
indices, 556/556 non-zero val1/val2. See `docs/carindb/03-road-network.md` §6.3.1 for
full verified layout table and `docs/fw/pbp_0x0E_decoder.asm` for write trace.

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
