# RR `rpmod`: how the DVD route planner reads a road segment

> **Status: 🟡 PARTIAL (2026-09-28).** First pass over the RoadRunner route planner, the
> firmware of the unit that reads DB-REL 34 DVDs ([`03-firmware-provenance.md`](03-firmware-provenance.md)).
> Listing: [`rr_rpmod_edge_unpack.asm`](rr_rpmod_edge_unpack.asm). Field meanings on the
> data side: [`../carindb/03-road-network.md`](../carindb/03-road-network.md) §6.7.

## 1. Setup

- Module: `rpmod` in `/V_2/RR/0101/BMWC01S/app_sw/bsw2` at `0x110cf0` (MIPS32 BE, OS-9000),
  code `0x3000`–`0x8e008`, ~1,490 non-leaf functions.
- Listing: `python scripts/firmware/mips_listing.py build/fw/V_2_RR_0101_BMWC01S_app_sw_bsw2 rpmod build/rr_rpmod.asm`
  (extract `build/fw/` first with `scripts/firmware/extract_firmware.py`).
- Calls: `lui/addiu $at` + `addu $at, $at, $fp` + `jalr $at`, target = imm + `0x7FF0`
  (same as `db_pub`); the listing annotates them as `; -> sub_xxxxxx`.
- **DB descriptor** `gp[-0x6064]`: `+0x14` = DB-REL (`sub_07b390` returns it;
  `+0x14` = superblock `+0x1A`), and `RECORD_SIZE_TABLE` entry `T[i]` at `+0x1E + 2·i`.
  Checked against NAV_DB_21708: `+0x28` = `T[0x05]` = 8 (descriptor base), `+0x2E` =
  `T[0x08]` = 32 (S4 record), `+0x30` = `T[0x09]` = 26 (S4 tail), `+0x40` = `T[0x11]` = 60
  (tile frame after the 15 descriptors), `+0x46` = `T[0x14]` = 8 (S10 record),
  `+0x48` = `T[0x15]` (S12 record).

## 2. The segment unpacker `sub_01fd80` (and variant `sub_04e02c`)

Found by scanning every function for loads of `+0x10` and `+0x11` from one base register;
only these two also read `+0x02`, `+0x0A`, `+0x0B`, `+0x0C`, `+0x0E`, `+0x0F` and `+0x18`.
Arguments: `$a0` = edge struct (out), `$a1` = decoded block of type `0x00`–`0x03`
(header included); the S4 record offset is read from edge `+0x08`.

| S4 field | Firmware operation | Edge (`sub_01fd80`) | Data-side meaning (§6.7) |
|---|---|---|---|
| `+0x00` / `+0x02` | copied; `block + value` used as node pointer | `+0x22` / `+0x24` | start / end node ✔ |
| `+0x0B & 0x0F` | copied | `+0x16` | form of way ✔ |
| `+0x0B & 0x30 >> 4` | copied | `+0x15` | direction restriction ✔ |
| `+0x0B & 0x40` | `== 0x40` → 1 | `+0x1E` | toll road ✔ (first firmware confirmation) |
| `+0x0C` | copied as u32 | `+0x10` | length in metres ✔ |
| `+0x0E` / `+0x0F` | copied | `+0x26` / `+0x27` | bearing at start / end ✔ |
| `+0x10 & 0x0F` | copied | `+0x17` | road class ✔ |
| `+0x10 & 0x70 >> 4` | copied | `+0x19` | class 6 subtype ✔ |
| `+0x10 & 0x80` | → 1 if set | `+0x1D` | **new, meaning unknown** (bit 7 of the class byte) |
| `+0x11 & 0x0F` / `>> 4` | copied | `+0x14` / `+0x18` | junction type / high nibble ✔ |
| `+0x11` + class | `+0x1B` = 0 if class = 6, or if junction ∈ {3, 4} and high nibble ≠ 4; else 1 | `+0x1B` | "open to cars": same rule as CC-93 `can_traverse`; explains the DVD-only `0x13` (closed) vs `0x43` (open) |
| `+0x18 & 0x10` | only if DB-REL ≥ 27 | `+0x1F` | **the `0x10` value of `+0x18` is a routing flag** (meaning unknown) |
| `+0x0A & 0x80` / `+T[0x09]+2 & 0x80` | built-up flag: street level (`0x00`) reads `+0x0A` bit 7 on DB-REL ≥ 21, `+0x1D` bit 7 below; coarse levels read `+0x0A` bit 7 on DB-REL ≥ 21, else 0 | `+0x1A` | built-up area ✔ |
| `+T[0x09]+2 & 0x70 >> 4` | street level only | `+0x20` | **`+0x1D` bits 4–6: new, meaning unknown** |
| `+0x12` → S10 | via `sub_06322c`: first entry = `+0x12`, count = (next record's `+0x12` − this) / `T[0x14]` | lists at `+0x48` / `+0xA8` (≤ 8 × 12 B each), counts `+0x40` / `+0x44` | **forbidden turns**: entries are split by S10 `+6` bit 0 (start / end node). First firmware evidence for S10 |
| `+0x14` → S12 | same helper, stride `T[0x15]` | — | TMC references ✔ |

Other inputs:
- **Node records** (S5 / S6, pointed by `+0x00`/`+0x02`): converted to absolute coordinates by the
  function pointer `gp[-0x7ce4]` (args: tile frame at `block + T[0x05] + T[0x11]`, node, out →
  edge `+0x2C` / `+0x34`). Node `+6`: `& 7 == 1` → edge `+0x28` / `+0x29`; `3 − (bits 6–7)` →
  edge `+0x3C` / `+0x3D`. **Node `+6` flags are not documented on the data side yet.**
- **Block type table** `gp[-0x7A30 + 4·BLOCK_TYPE]` byte 3 → edge `+0x1C`: a per-level
  property; 0 selects the branch that also reads the S4 tail, so presumably 0 = street level (`0x00`). The table itself is not dumped yet.
- `sub_06322c` uses `T[0x08]` (32) as the record stride for `0x00` blocks and `T[0x09]` (26)
  for `0x01`–`0x03`, which suggests **coarse-level S4 records are 26 B** (no name tail).
  Not verified on data.

`sub_04e02c` builds a second, wider edge layout from the same fields (class at `+0x18`,
junction at `+0x14`, toll at `+0x20`, …). Its `+0x17` comes from `sub_0630cc`, the
**slip-road role**:
- DB-REL ≥ 27: `+0x18 & 3`;
- below: a jump table over `+0x0B & 0x0F`: 1, 8 → 1 (on-slip); 2, 9 → 2 (off-slip);
  3, 0xA → 3 (link); all other forms → 0.

This confirms from firmware both the slip roles of §6.7 and the meaning of `+0x18`
values 1–3. Note that for packed tiles `decoder_00.py` does not restore `+0x18` (§6.7,
"the `+0x18` pass"), so on DB-REL ≥ 27 discs the router would see slip role 0 and flag
`0x10` = 0 from our decoder. The RR `db_pub` has to write it; tracing that is open.

## 3. Checked on NAV_DB_21708 (DB-REL 34)

300 random `0x00` tiles (277 CF=1, 20 CF=2, 1 CF=0):
- `+0x12` monotone and on S10 record boundaries in 298 / 298 tiles; the ranges cover
  7,239 of 7,245 S10 entries (the rest belong to the last segment).
- `+0x14` the same for S12: 298 / 298 tiles, 36,895 / 36,895 entries.
- `+0x11` values: `0x20` 131,447; `0x29` 2,833; `0x26` 1,866; `0x25` 520; `0x22` 121;
  `0x14` 26; `0x13` 24; `0x11` 8; `0x43` 4; `0x44` 1.
- `+0x18` values: 0 on 136,369 segments, 4 on 417, 3 / 2 / 1 on 26 / 18 / 16, `0x10` on 4.

## 4. Open

1. The RR `db_pub` `0x00` decoder: does it read the `+0x18` pass? (Compare with Mk3 `decode_type00`.)
2. The cost function: which edge fields feed the route cost (speed `+0x0A` bits 0–4 is not read
   by either unpacker; look for readers of `+0x0A & 0x1F`).
3. Callers of `sub_01fd80` / `sub_04e02c`: which structure lists edges, and how the S6 twin and
   S8 level links are followed (tile crossing and level switching).
4. Meaning of `+0x10` bit 7, `+0x1D` bits 4–6, `+0x18 & 0x10` and node `+6`.
5. The `gp[-0x7A30]` per-block-type table (initialised data of `rpmod`).
