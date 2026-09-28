# CarinDB Blueprint — Agent Knowledge Base

Reverse-engineering knowledge base for the **CarinDB** binary map format
(BMW MK4 / CARiN navigation). Split from the monolithic
[`../CARINDB_BLUEPRINT_EN.md`](../CARINDB_BLUEPRINT_EN.md) into task-scoped parts
so an AI agent can load only the part relevant to its current task.

> **Analyzed media**: `dataset/NAV_DB_21708.ISO` — BMW MK4 / CARiN, CD-ID 21708,
> compile date 2015-08-04. All multi-byte values are **Big-Endian**.
> Dataset disc images and firmware dumps are on
> [Google Drive](https://drive.google.com/drive/folders/1KZH93y9ltZBkkjlIm-hBnoqKcCdnsqJa?usp=sharing).

## How to read these docs (agent guide)

Every statement in these files is tagged by confidence:
- **VERIFIED** — checked byte-for-byte against the dump. Trust and build on it.
- **RESOLVED** — a previously open problem now fully understood.
- **PARTIAL** — structure known, field *semantics* not. Do **not** assume meaning.
- **UNKNOWN / RESERVED** — explicitly not determined. Do not guess silently.
- **NEGATIVE KNOWLEDGE** — hypotheses proven *false*. Do not re-attempt.

Load order for a cold agent: start here, then jump to the part matching your task.

## Parts

| # | File | Scope | Status |
|---|---|---|---|
| 0 | this README | Index, dataset, forum-note corrections | — |
| 1 | [`01-architecture.md`](01-architecture.md) | Filesystem, generic block layout, superblock/schema, system blocks, text encoding | ✅ VERIFIED |
| 2 | [`02-geo.md`](02-geo.md) | Coordinate system, bounding boxes, POI/feature georeferenced records | ✅ VERIFIED / RESOLVED |
| 3 | [`03-road-network.md`](03-road-network.md) | Road graph `0x00`–`0x03` (§6.7), street-name directory `0x0E`, address indexes, house numbers | ✅ mostly RESOLVED (open items in part 6) |
| 4 | [`04-cf1-codec.md`](04-cf1-codec.md) | `COMPRESSION_FLAG=1` decoder, found in original firmware | ✅ RESOLVED (`0x00`, `0x0E`, `0x14`–`0x16`, `0x1C`–`0x1E`) |
| 5 | [`05-failed-attempts.md`](05-failed-attempts.md) | Every codec hypothesis that was falsified | ⛔ NEGATIVE KNOWLEDGE |
| 6 | [`06-objectives-roadmap.md`](06-objectives-roadmap.md) | Status per block type, corrected conclusions, prioritized roadmap | 🎯 OPEN (rewritten 2026-09-28) |
| 7 | [`07-toolchain.md`](07-toolchain.md) | Parser library + scripts reference | 🔧 REFERENCE |

## One-paragraph orientation

CarinDB is an ISO 9660 image whose real payload is a single virtual sector space
(`DB_0` + `DB_1`, 512-byte sectors) covered 100% by a chain of typed **blocks**.
The root/superblock holds the *schema* (a `RECORD_SIZE_TABLE`), not table pointers.
The road network is not global tables but **parcels** with block-local 16-bit
pointers. Coordinates are a linear (non-Mercator) lon/lat grid, **RESOLVED**.
30% of blocks use `COMPRESSION_FLAG=1`, which is **not compression** but
structure-driven bit-packing; its decoder was recovered from the navigation-unit
firmware and is **RESOLVED for `0x00`, `0x0E`, `0x14`–`0x16` and `0x1C`–`0x1E`** (parts 4 & 5).
Firmware evidence comes from two BMW platforms — the CC-93 (m68k, CD) and the
RoadRunner (MIPS, DVD) that reads these discs; see [`../fw/03-firmware-provenance.md`](../fw/03-firmware-provenance.md).

## §0 — Corrections to forum notes (`dataset/context.md`)

Prior community notes contained errors; corrected against the dump:

| Forum claim | Dump verification | Outcome |
|---|---|---|
| "1 sector = 2048 bytes" | `BLOCK_ID.sector * 512 == offset` for 315,095/315,095 blocks | ❌ on the DVD the CARINdb sector is **512 B** (2048 is the *ISO* sector). ⚠️ CD discs with a single `/carindb` do use 2048 (`carinet16s2048` in `ABSTRACT`) |
| "block from 1 to 8 sectors" | observed lengths 1..70 | ❌ length field = 1 byte, max observed 70 sectors (35 KiB) |
| "BLOCK_ID = 0x01030000 → block #3" | `0x00000304` = sector 3, 4 sectors | ⚠️ forum example was little-endian; rule `sector<<8 \| len` is correct |
| "UNCOMPRESSED_SIZE (1 byte)" | `us*512 == len(payload)+8` on all compressed blocks | ✅ expressed **in 512-B sectors**, not bytes |
| "Sector 0 = character set" | sector 0 = block type `0x12` (root) | ❌ it is the **root/superblock** |
| "Sector 1 = CD info" | CD-info block is at **sector 2**, type `0x13`, zlib | ⚠️ off-by-one |
