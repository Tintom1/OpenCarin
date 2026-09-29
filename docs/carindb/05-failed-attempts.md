# Part 5 — Falsified Hypotheses (Negative Knowledge)

> **Status: ⛔ NEGATIVE KNOWLEDGE.** Everything here was *proven wrong* while the
> `CF=1` codec was still open. It is kept so no agent burns time re-running these.
> The codec was ultimately solved as bit-packing, not compression — see
> [`04-cf1-codec.md`](04-cf1-codec.md). **Read this file before proposing any new
> codec attack.**
>
> Source: `../CARINDB_BLUEPRINT_EN.md` §9.1–§9.10.

---

## TL;DR — what is definitively ruled out

Over two sessions, **6 codec families + >650 parameter combinations** were
experimentally falsified for `CF=1`:

1. zlib / raw deflate (every byte offset & bit phase, wbits ±15) — **no valid stream**
2. LZ4 raw block — output ≤ 1 byte
3. LZW 9→12/13/14 bits, MSB/LSB, ±early change — no plausible output
4. Byte-aligned LZSS/LZ77 — grid of 384 combinations — none produce length or text
5. Global order-0 static Huffman — wrong length, no text (unrepresentative sample)
6. aPLib / aP_depack — fails within 3–13 bytes
7. Static-table search in system blocks (`0x0D`,`0x18`,`0x1A`,`0x1B`) — none is a table
8. The entire "1-bit control byte + 2-byte token" LZSS family (§9.9–§9.10, >650 combos)
   — falsified with a structural oracle **and** cross-edition ground truth

**Why they all failed**: the format is not compression at all. It is structure-driven
bit-packing (record fields packed to minimal width), so no dictionary/entropy model
can reproduce it. The real solution came from the firmware, not from cryptanalysis.

---

## Background measurements (still valid facts)

### 9.1 CF=1 block structure
Prologue is **plaintext**, identical to a CF=0 block: 8-byte header, descriptor,
bbox, service data. Descriptor offsets are in **decompressed** space, consistent
with `UNCOMPRESSED_SIZE*512`. Compressed stream begins after the service data.

```
type 0x1E, sector 6452121, len=4 (2048 B) us=6 (3072 B)
0000: 62 73 99 04  00 1e  01 06        header
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
| plaintext prologue | 48 B (`0x0E`) · 56 B (`0x14`…`0x1E`) · 116 B (`0x00`…`0x03`) |

### 9.4 The result that pointed the way (still valid)
Shared 8-grams between blocks of the **same type**:

| Set | Blocks | Avg length | Shared 8-grams/pair |
|---|---|---|---|
| `0x16` CF=1 | 12 | 14,988 B | **13.0** |
| `0x16` CF=2 (zlib) | 12 | 23,638 B | **0.0** |
| `0x15` CF=1 | 12 | 7,055 B | **3.0** |
| `0x1E` CF=1 | 12 | 1,672 B | **4.0** |
| random control | 12 | 2,000 B | **0.0** |

Consequences (all confirmed by the final solution): the codec is **deterministic
and stateless across blocks** (not per-block encryption), **byte-aligned or shared
static table** (identical input → identical output bytes). This is what made the
firmware approach the right one.

### 9.5 Verified decompressed-output layout of type `0x1E`
Derived by comparing 3 CF=0 blocks with different schemas. Establishes exact section
lengths of the *decompressed* output — a strict structural oracle. (Details in the
monolith §9.5; superseded operationally by the resolved decoder.)

---

## The falsified attempts (do not repeat)

### 9.3 First-round exclusions
zlib/deflate, LZ4, LZW, byte-aligned LZSS (384-combo grid: literal bit 0/1, LSB/MSB,
window 1024–8192, 10–13-bit offset, 3 back-ref packings, fill 0x00/0x20). All fail.

### 9.6 Session 1 additional dead ends
1. **No plaintext/ciphertext pair on the disc.** Scanned 18,481 blocks of bbox-known
   types, grouped by `(type, bbox)`: 18,406 groups, **zero with mixed CF**. Each
   quadtree tile exists once at a single compression level. *(This was the single
   most important dead end: no exact known-plaintext exists on the disc.)*
2. **Global order-0 Huffman** from 4,000 CF=0 blocks: sample dominated by `0x00`
   (93%), predicts 5.3× vs observed 1.33–2.65×; wrong length, no text.
3. **Plaintext leakage search**: ~40 chance matches of 4–5 bytes, one ASCII (`coth`)
   with no meaning — no leakage, rules out literal+compressed byte mix.
4. **Entropy invariance to bit shift**: non-discriminating (entropy already 7.0–7.8).
5. **`/TPD/*.CPR` comparison**: common 6-byte prefix (`00 09 87 25 52 aa`), entropy
   6.636–6.638 (lower than CF=1). Neither proves nor rules out same codec.

### 9.8 Session 2 (2026-09-15) — also failed
"Powers-of-two bytes ⇒ 1-bit LZSS control byte" — already covered by §9.3 grid.
New: **all 256 byte values appear** (no restricted codebook).
1. **aPLib / aP_depack** — faithful port of Ibsen's lib. Fails within 3–13 bytes;
   best sweep reached 59 of 10,636 expected bytes. **Ruled out.**
2. **Varint / gamma field-level** — non-discriminating alone; no field oracle at the
   time. Inconclusive — was flagged as the most promising remaining lead (and indeed
   the truth was field-level bit-packing).
3. **Static table in `0x0D`/`0x18`** — `0x18` is a BLOCK_ID index; `0x0D` is a range
   index. Neither is a 256-entry code-length table. **Ruled out.**

### 9.9 User hypothesis: 189 B prologue custom LZSS — falsified with structural oracle
1. **Exact length is not a valid oracle**: every prologue 0–421 yields exact length
   (loop halts at target). Proves nothing.
2. Used a real CF=2 block of the same type/layout as ground truth (column entropy
   `S4=2.43`, `S5=3.28` bits — structured).
3. User params: exact length on 6/8 blocks but **content unstructured** — falsified
   by direct inspection.
4. 96-combo grid guided by the oracle: closest match within 0.001 on mean entropy but
   byte inspection still noise → **statistical coincidence**, mean-entropy oracle
   insufficient.
5. **Shared 8-grams on type `0x00` confirmed** (avg 9.0/pair over 66 pairs). Found a
   **non-trivial 14-byte all-distinct fragment** byte-identical between sector
   3157667 (off 15625) and 3157861 (off 15774):
   `04 81 10 32 08 42 c8 61 0e 21 e4 4c 89 31`. Confirms byte-aligned & deterministic.

**Conclusion**: the single-bit control-byte hypothesis (>480 variants across both
sessions) is wrong in its entirety, not in details.

### 9.10 Cross-edition comparison (CD-ID 21708 vs 21734) — same negative outcome, reusable method
Second image `NAV_DB_21734` (build 2018-05-09, **same binary schema**).
1. **Method**: type `0x00` bbox at decompressed off `0x44` is inside the plaintext
   prologue → readable on CF=1 without decompressing. Indexed all `0x00` blocks in
   both images by bbox: **21,751 common bboxes**. CF distribution:
   `{(1,1):21363, (0,0):328, (1,0):31, (0,1):29}` → **60 tiles with differing CF**.
2. **No pair byte-identical** (tile updated between 2015 and 2018).
3. Filter by identical `SECTION_DESCRIPTOR` across all 8 entries → 12 "stable" pairs.
4. Decoded the CF=1 side with the §9.9 grid, compared with `difflib` against the
   other edition's CF=0 (excluding prologue and low-variety runs). Best: 32–70
   matching bytes / ~1,200 (~4%) — **noise level**.
5. **Conclusion**: no control-byte-LZSS combination reproduces real content (>650
   combos total).
6. **Reusable value**: the methodology (index bboxes across editions, filter by
   identical descriptor, `difflib` excluding low-variety runs as oracle) is valid for
   **any** future hypothesis. Reference map in `build/cross_iso_type0.pkl`.

### 9.12 Spatial index `0x07`–`0x09` (issue #20, 2026-09-29) — not a codec attempt
1. **"All DVD tile edges are multiples of 98,304 from `(0, 0)`" — falsified** on every tile of
   both DVDs (`scripts/geo/check_spatial_index.py`): 0 of 128,690 (21708) and 0 of 147,272
   (21734) tiles have their corner on that grid, and 2,837 / 3,887 have a side that is not a
   multiple of 98,304 (sides 24,576 and 49,152 exist). The rule that holds is root side /
   `2^k` (`02-geo.md` §7.3). `find_bbox`, built on the old rule, is marked superseded.
2. **Firmware reader of the `0x07` layer parameters — not found.** Searched the 17 modules of
   RR `V_2_RR_0101_BMWC01S_app_sw_bsw2` (all code, capstone, not Ghidra) for two shapes:
   - a 28-byte record read: `lw` at `+0/+4/+8/+0xC/+0x10` and `lh`/`lhu` at `+0x14/+0x16` on one
     base register within 80 instructions (base offset 0 or `0x14`). One hit, `mm +0x304e0`:
     it copies byte fields at `+0`, `+2`, `+3`, `+0x2B` and a word at `+0x34` of its source into
     a map-matching object. A `0x07` record has a `u32 BLOCK_ID` at `+0` and nothing at
     `+0x2B`: not the reader.
   - a cell/item side used as divisor: a `lw` from `+0x0C` or `+0x10` that is the divisor of
     two or more `div`/`divu` within 60 instructions. One hit, `db_bh_read +0x6524`: it
     divides a handle's `+0x18` by its `+0x10` and compares the quotient with `+0x14` − 1,
     on the handle passed in `$a0` (a buffer position), not on a `0x08`/`0x09` block.

   Why this is not conclusive: the reader may copy the directory into another structure
   first, divide by a value loaded elsewhere, or use code my windows split. Not tried: Ghidra
   cross-references from the `0x07` read, other RR builds, Mk3. The parameters stay ❓, and
   QGIS_VDO's names `zoom_from`/`zoom_to` are not evidence.

   **Superseded (2026-09-29): reader found** by following the superblock S0 `BLOCK_ID`
   (`db_bh_read` `0x17cc`, `dbq` `0x2081c`) — see `02-geo.md` §7.3. Why both shapes missed it:
   the reader (`dbq` `0x21270`) addresses a record as `block + T[5] + T[0x1A] + k · T[0x18]`
   with `k` from a switch on the tile type, and copies it as six `lw`/`sw` pairs (`+0` … `+0x14`),
   so there are no `lh` loads at `+0x14`/`+0x16` and no fixed stride `0x1C`; the parameters are
   then read from the stack copy (`lhu 0x1c/0x1e($sp)`). The grid readers (`0x2af6c`,
   `0x2b92c`) divide the root width by the cell side once, not twice.
3. **Who else points at the unreferenced `0x08` grid on 21734.** `carindb-rs xref 0x32f1e060`
   (its first block): 0 hits on the whole disc. The same scan for its 1,476 `0x09` and 3,129
   `0x06` `BLOCK_ID`s was stopped: with 4,605 IDs it had covered about 3% of the disc after
   several minutes. So "nothing points at those `0x09` / `0x06` blocks" is **not** established;
   only "no grid reached from `0x07` lists them" is (check script).

---

## What survived as *positive* signal

The byte-aligned / deterministic evidence (shared 8-grams, the 14-byte fragment) was
**correct** and pointed at a static, structural encoding — which is exactly what the
firmware revealed: per-field bit-packing driven by `RECORD_SIZE_TABLE`, not
compression. Any future codec question should start from
[`04-cf1-codec.md`](04-cf1-codec.md), not from this list.
