# Part 7 — Toolchain Reference

> **Status: 🔧 REFERENCE.** The parser library and scripts that produced/verify
> everything in these docs. Paths are relative to the repo root.
>
> Source: `../CARINDB_BLUEPRINT_EN.md` §10 + §9.11.8.

---

## Library (`carin/`)

| File | Function |
|---|---|
| `carin/parser/iso.py` | ISO 9660 reader (no mount), `CarinVolume` over `DB_0+DB_1` (DVD, 512-byte unit) or a single `/carindb` (CD, 2048-byte unit), `calibrate()` (detects `subrel`), `CarinBlock`, `find_bbox` (98,304 grid: DVD only), `to_wgs84`/`to_carin` |
| `carin/parser/calibration.py` | `GeographicCalibrator` (Levenberg-Marquardt + grid search) |
| `carin/parser/compression.py` | `CompressionAnalyzer`, `LzssSweep`, `sweep_lzss`, `decode_lzw`, `decode_lz4_block`, `entropy`, `plain_prefix`, `score_output` |
| `carin/parser/cf1/` | **CF=1 bit-packing codec** — `decode_block(raw, table, dbrel, subrel, sector_size)` for `0x00`, `0x0E`, `0x14`–`0x16`; `encode_type0E`; `probe.py` (per-disc `subrel` detection); parameterized by `RECORD_SIZE_TABLE` — see [`04-cf1-codec.md`](04-cf1-codec.md) |
| `carin/parser/geometry.py` | `road_segments(data, table)`: WGS84 road segments of a decoded `0x00` tile with name, locality, display class; `tile_frame`, `header_bounds` — see [`02-geo.md`](02-geo.md) §8.3 |

## Analysis & extraction scripts (`scripts/`)

### Geo / records
| Script | Function |
|---|---|
| `extract_anchors.py` | extracts `(name, X, Y)` from `0x16` blocks |
| `optimize_coords.py` | calibration and residual verification |

### CF=1 codec — firmware recovery
| Script | Function |
|---|---|
| `os9_modules.py` | enumerates OS-9/OS-9000 modules (`4AFC`/`4DAD` sync) |
| `m68k_dis.py` | disassembles m68k **in 68040 mode** (required for `BFEXTU`) |
| `mips_dis.py`, `mips_graph.py`, `mips_func.py` | MIPS disassembler, call graph, annotated dump (default firmware: Mk3 `bsw_load`, override with `CARIN_FW2`) |
| `mips_listing.py` | full listing of one MIPS module with functions split and `$fp` call targets resolved (used for RR `rpmod`) |
| `fw_xref.py` | xref of PC-relative constant strings |
| `os9_data.py` | static data area, resolves `a6` references |
| `fw_arch_detect.py` | detects module CPU architecture |
| `extract_firmware.py` | re-extracts codec-bearing firmwares from `NAV_SW(v32).iso` |
| `fw_hunt_charmap.py` | searches for the 42-byte codec charmap across a firmware ISO |
| `cf1_defaults.py` | extracts default layout table from firmware |
| `cf1_super.py` | extracts `RECORD_SIZE_TABLE` from disc superblock |
| `cf1_charmap.py` | extracts text-decoder character table |

### CF=1 codec — decode & validate
| Script | Function |
|---|---|
| `cf1_layout_probe.py` | inspects real CF=0 blocks to infer layout |
| `cf1_try.py` | decodes a single block, prints descriptor |
| `cf1_validate.py` | structural + text oracles on selected blocks |
| `cf1_sweep.py` | batch decodes, reports success rate (1,200/1,200 on type `0x00`) |

### Road-network oracles (STEP 2, 3 & 4)
| Script | Function |
|---|---|
| `oracle_0e.py` | STEP 2 oracle — S0/S1/S2 structural invariants on `0x0E` CF=1 blocks; 10/10 PASS |
| `oracle_0e_s0.py` | STEP 2 oracle — S0 field statistics (A monotone, B block-constant, D pointer validity) |
| `oracle_14_16.py` | STEP 1 oracle — X/Y geographic range on `0x16` CF=1 blocks; 1958/1958 PASS |
| `find_parcel.py` | **STEP 3** — `find_parcel(vol, X, Y) → sector`; builds/loads spatial index from S2 anchors (superseded in meaning: S2 anchors are linked `0x00` tile centres; the disc's own index is `0x07`–`0x09`, roadmap A3) |
| `oracle_find_parcel.py` | STEP 3 oracle — 10/10 PASS 2026-09-19; samples blocks Albania→Austria |
| `oracle_encode_0e.py` | **STEP 4** oracle — `encode_type0E` round-trip: raw→decode→encode→decode, compare `[4:]`; 10/10 PASS 2026-09-19 |

### Codec analysis (historical — negative results, see [`05-failed-attempts.md`](05-failed-attempts.md))
| Script | Function |
|---|---|
| `analyze_codec.py` | analysis of CF=1 codec on real ISO blocks |
| `find_pairs.py` | scans DB for plaintext/ciphertext pairs (identical bbox, differing CF) — outcome: none |

## Firmware listings (`docs/fw/`)

Disassembled, annotated decoders so transcription can resume without redoing the RE:

| File | Content |
|---|---|
| `m68k_pbp_decoders.asm` | CC-93 `pbp` decoders (m68k, DB-REL ≤ 22) |
| `mips_decode_type00.asm` | DB-REL 34 `decode_type00` (`db_pub`, MIPS) |
| `mips_primitives.asm` | `getbits`/`bits_init`/`copy_*` primitives |
| `mips_dec_A.asm`, `mips_dec_B.asm` | section decoders |
| `mips_dec_text.asm` | text decoder |
| `pbp_0x0E_decoder.asm` | type `0x0E` parcel decoder — S0/S1/S2 write traces complete (✅ 2026-09-19) |
| `rr_rpmod_edge_unpack.asm` | **RR** (DVD unit) `rpmod`: S4 segment → edge record, S10/S12 range helper, DB-REL getter — see [`../fw/04-rr-rpmod-edge-record.md`](../fw/04-rr-rpmod-edge-record.md) |

The `mips_*` decoder listings were traced on Mk3; the m68k ones (and `dbq/`, `rpmod/`) are CC-93. Which platform reads which disc: [`../fw/03-firmware-provenance.md`](../fw/03-firmware-provenance.md).

## Example invocations

```bash
python3 scripts/extract_anchors.py --out build/cities.pkl --names paris london roma
python3 scripts/optimize_coords.py
python3 scripts/analyze_codec.py --type 0x1E --count 1

# CF=1 pipeline
python3 scripts/cf1_super.py      dataset/NAV_DB_21708.ISO   # RECORD_SIZE_TABLE
python3 scripts/cf1_charmap.py    <firmware>                 # 42-byte charmap
python3 scripts/cf1_sweep.py      --type 0x00 --count 1200   # batch decode + validate

# road geometry as GeoJSON (by sector or WGS84 window)
python3 scripts/geo/extract_00_geometry.py dataset/NAV_DB_21708.ISO build/roads.geojson --window LON0 LAT0 LON1 LAT1

# RoadRunner route planner listing
python3 scripts/firmware/extract_firmware.py
python3 scripts/firmware/mips_listing.py build/fw/V_2_RR_0101_BMWC01S_app_sw_bsw2 rpmod build/rr_rpmod.asm
```

## Build artifacts

| File | Content |
|---|---|
| `build/cities.pkl` | extracted city anchors for calibration |
| `build/cross_iso_type0.pkl` | bbox → (sector, length, cf) map for both editions (cross-edition method, [`05-failed-attempts.md`](05-failed-attempts.md) §9.10) |
| `dataset/parcel_index.npz` | spatial index of all 74,247 `0x0E` parcels — int64 array `[sector, x_min, y_min, x_max, y_max, cx, cy]`; auto-generated by `find_parcel.py` on first call (~150 s build time) |
