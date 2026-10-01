# OpenCarin (CarinCompiler)

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Rust 2024](https://img.shields.io/badge/rust-2024-orange.svg)](carindb-rs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Format: CARINdb](https://img.shields.io/badge/format-CARiN%20%2F%20CarinDB-orange.svg)](#)
[![Tests: 37 passing](https://img.shields.io/badge/tests-37%20passing-brightgreen.svg)](tests/)
[![Buy Me A Coffee](https://img.shields.io/badge/Donate-Buy%20Me%20A%20Coffee-yellow.svg)](https://buymeacoffee.com/fdemusso)

**OpenCarin** is an open-source reverse-engineering and map compilation toolkit for the proprietary **Philips/VDO CARiN** navigation database format (`CARINdb`, `DB_0`, `DB_1`, `CARINET`).

These navigation databases were widely used in iconic late 1990s and 2000s automotive systems, including:
* **BMW Navigation Systems**: MK3 (CD, MIPS32) and MK4 (DVD, Hitachi SH-4) across BMW E46, E39, E38, X5 E53, Z4 E85
  *(On the BMW update CD `NAV_SW(v32).iso` the DVD database reader and route planner are MIPS32 — the VDO Dayton "RoadRunner" software; see [docs/fw/03-firmware-provenance.md](docs/fw/03-firmware-provenance.md).)*
* **Renault / Nissan**: Carminat Navigation Informée 1 (CNI1)
* **VDO Dayton**: PC5000, PC5200, MS5000 series
* Systems across Opel/Vauxhall, Rover, Land Rover, Volkswagen/Audi and others

Official map updates ceased years ago (mostly frozen around 2015–2019). **The mission of this project is to reverse-engineer the CARiN binary format and build a compiler pipeline that converts modern OpenStreetMap (OSM) data into functional, bootable DVD/CD navigation discs for these classic cars.**

---

## 🧭 Current Project Status & Key Breakthroughs

We have achieved major breakthroughs across the entire format specification. Every technical finding below is byte-verified on real disc images (e.g. BMW High 2015 `NAV_DB_21708.ISO`, 2019 `NAV_DB_21734.bin`, and CD-IDs 2952 / 21594):

* ✅ **Addressing & Block Chaining Solved (100% File Coverage)**:
  * **DVD** (BMW MK4): The sector size is **512 bytes**, and the virtual address space spans `DB_0` (first 2 GiB) and `DB_1` via `virtual_sector = file_index * 0x400000 + local_sector`.
  * **CD** (e.g. Carminat CNI1): The database is a single `/carindb` file and the unit is **2048 bytes**.
  * The disc's `ABSTRACT` names the unit: `carinet16s512` on `NAV_DB_21708`, `carinet16s2048` on CD-ID 21594.
  * The block chain covers **100% of the volume with zero gaps** (315,095 blocks on DVD 21708).
  * `/CARINET` identified as the RDS-TMC ALERT-C event and weather phrase catalog across 8–9 European languages.
* ✅ **Coordinate System Cracked**:
  $$X = (lon + 30.0) \times \frac{2 \times 10^9}{360}, \quad Y = (lat + 0.0) \times \frac{2 \times 10^9}{360}$$
  Origin is at $30^\circ\text{ W}$ on the Equator, linear in latitude (no Mercator projection). 1 unit $\approx 2\text{ cm}$ at the equator. Verified with 38 European city anchors (RMS error $2.0\text{ km}$, matching published city-center offsets).
* ✅ **Hierarchical Spatial Index Fully Cracked (`0x07` → `0x08` → `0x09`)**:
  * Block `0x07` contains the 12-layer directory and quadtree root bounding box.
  * Layer parameters decoded via RoadRunner firmware (`dbq 0x21270`, `rpmod 0x7490c`): parameter 0 defines the highest allowed road class for road layers `0x00`–`0x03`.
  * Quadtree grid partitioned into consecutive `0x08` blocks.
  * Column-major cell matrix in `0x09` points directly to map and feature tile blocks.
  * Implemented in [`carin/parser/spatial.py`](carin/parser/spatial.py) (`tiles_at`), reaching **100% of all tiles** on both DVD 21708 (128,690/128,690) and DVD 21734 (144,143 tiles).
* ✅ **100% of CF=1 Bit-Packed Blocks Decoded Across Entire Discs**:
  Covering 30% of all disc blocks (96,011 blocks), this was **not a dictionary compression codec** but **structure-driven bit-packing** parameterized by the superblock's `RECORD_SIZE_TABLE`. Decoders recovered from RoadRunner MIPS32 (`db_pub`) and CC-93 m68k (`pbp`) firmware:
  * **Map tiles (`0x00`)**: **100% decoded without error** (86,107/86,107 on DVD 21708, and 91,651/91,651 on DVD 21734). Solved by identifying the pass `0x15` sentinel and pass `0x1B` (`+0x18`) from RoadRunner `db_pub` (`sub_005e6c`).
  * **Background feature layers (`0x14`–`0x16`, `0x1C`–`0x1E`)**: Sea, forest, built-up areas, rivers, rail across all zoom levels decoded via RoadRunner `sub_004b88`. Oracle qualified on 20,227 plain blocks and passes 100% of CF=1 blocks on both DVDs, including legacy DB-REL < 23 discs.
  * **Street-name directory (`0x0E`)**: Packed name blobs fully decoded and re-encoded byte-perfect (`enc_text`).
* ✅ **Road Network Graph Architecture Cracked (Major Paradigm Shift)**:
  * **`0x0E` is the Street-Name Directory, NOT the routing graph**: It maps street names, alternative names, languages, and localities to runs of segments in `0x00`, providing the envelope of house-number ranges.
  * **The True Routing Graph is in `0x00`–`0x03` (Section 4)**: Contains topological start/end nodes, next-segment adjacency lists (falsifying the older "BSP tree" hypothesis), inter-tile boundary crossings (Section 6 twins), level transitions (Section 8), road class hierarchy (0–7), speed codes, one-way flags, length, bearings, signposts, and turn restrictions (Section 10; U-turn bans are entries whose target is the owner segment itself). Confirmed by RoadRunner route planner (`sub_01fd80`).
* ✅ **Per-Segment House Numbers Decoded (`0x04` & `0x0E` S2)**:
  * Block `0x04` stores 10-byte records defining left/right house number ranges per S4 road segment (implemented in [`carin/parser/house_numbers.py`](carin/parser/house_numbers.py)).
  * `0x0E` S2 holds street-level envelope ranges, cross-checked with a **98.9% match against OpenStreetMap addresses**.
* ✅ **Administrative Search Tries & Physical Hardware Verification (`0x0A`, `0x0C`, `0x0D`, `0x0F`, `0x11`)**:
  * Country table (`0x0A`), city records (`0x0C` with exact city-center coordinates), and prefix radix tries for cities (`0x0D`), roads (`0x0F`), and POIs (`0x11`).
  * **Live vehicle verification**: Modified street names and a custom created city were injected into disc images and successfully booted and recognized on a physical Renault Carminat CNI1 nav computer!
* ✅ **TMC Traffic Message Channel Indices Decoded (`0x17`–`0x1B`)**:
  * TMC location tables (`0x17`), table index (`0x18`), TMC position records (`0x19`), and spherical coordinate spatial index (`0x1B` → `0x1A`).
* ✅ **High-Performance Rust Toolchain (`carindb-rs`)**:
  * Fast native CLI tool with memory-mapped ISO access, ultra-fast CF=2 zlib and full CF=1 bit-packing decoders, supporting `dump-type`, `stats`, and disc-wide `xref` cross-referencing.

---

## 🛠 Current Roadmap & Focus Areas ("The Heavy Lifting")

With the reading and decoding of the binary format solved, our focus is shifted towards routing semantics, export tools, and the OpenStreetMap compiler pipeline:

### 1. RoadRunner Firmware Route Planner & Cost Functions 🔴 Critical
* Reverse-engineer the routing engine in RoadRunner MIPS firmware (`bsw2` / `sub_01fd80`, `sub_04e02c`).
* Decode speed code lookup tables (`+0x0A & 0x1F`), turn restriction weights (Section 10), and routing cost traversal heuristics.
* Trace inter-tile crossing logic (Section 6 twins) and hierarchical layer transitions (Section 8).

### 2. Routable Export Pipeline (GeoPackage / OSRM / Valhalla) 🟠 High
* Build an export pipeline converting decoded `0x00`–`0x03` road segments, nodes, geometry, one-way restrictions, turn penalties, and street names into standard GIS / routing formats (GeoPackage, GeoJSON, OSRM/Valhalla graph).
* Validate routing accuracy by computing test routes and comparing against OSM/OSRM.

### 3. OpenStreetMap to CARiN Serializer & ISO Compiler 🟡 Ongoing
* **Block Serializers**: Generate uncompressed (CF=0) `0x00`–`0x03` road network tiles from OSM ways and nodes (CF=1 is not required for writing custom discs).
* **Spatial Index Builder**: Generate quadtree directory `0x07` → grid `0x08` → cell matrix `0x09`.
* **Administrative Hierarchy & Tries**: Compile country table `0x0A`, city directory `0x0C`, and search tries `0x0D` / `0x0F` / `0x11`.
* **Disc Masterer**: Package 512-byte sector-aligned `DB_0` / `DB_1` files and generate bootable dual-layer ISO 9660 filesystem images.

### 4. Residual Decoders & Legacy Formats 🟢 Minor
* Determine left/right orientation and start/end node assignments of `0x04` house numbers.
* Investigate residual trailer fields in `0x07` (`+0x164`) and legacy variations on DB-REL < 34 discs.

---

## 📚 Essential Documentation

Before diving into code, consult the modular technical documentation:

* 📖 **[docs/CARINDB_BLUEPRINT_EN.md](docs/CARINDB_BLUEPRINT_EN.md)**: The authoritative, comprehensive reference specification.
* 📂 **[docs/carindb/](docs/carindb/README.md)**: Agent-oriented modular documentation:
  * [`01-architecture.md`](docs/carindb/01-architecture.md): Filesystem, superblock schema, system blocks, text encoding, TMC.
  * [`02-geo.md`](docs/carindb/02-geo.md): Coordinate system, quadtree, spatial index `0x07`–`0x09`, POI & background layers.
  * [`03-road-network.md`](docs/carindb/03-road-network.md): Routing graph in `0x00`–`0x03`, street directory `0x0E`, house numbers `0x04`.
  * [`04-cf1-codec.md`](docs/carindb/04-cf1-codec.md): Bit-packing specifications, pass definitions, and firmware decoders.
  * [`05-failed-attempts.md`](docs/carindb/05-failed-attempts.md): Falsified hypotheses & lessons learned.
  * [`06-objectives-roadmap.md`](docs/carindb/06-objectives-roadmap.md): Current prioritized engineering roadmap.
  * [`07-toolchain.md`](docs/carindb/07-toolchain.md): Python & Rust tooling, oracles, and test scripts.
  * [`08-qgis-vdo-handoff.md`](docs/carindb/08-qgis-vdo-handoff.md): Comparative analysis with prior reverse-engineering projects.
* 💻 **[docs/fw/](docs/fw/)**: Disassembled and annotated firmware routines (MIPS32 RoadRunner, m68k CC-93) and firmware provenance notes.

---

## 📂 Repository Structure

```
├── carin/
│   ├── parser/
│   │   ├── iso.py           # ISO reader & CarinVolume abstraction over DB_0 + DB_1
│   │   ├── spatial.py       # Spatial index: 0x07 directory -> 0x08 grid -> 0x09 cells
│   │   ├── house_numbers.py # Per-segment house number parser (0x04)
│   │   ├── geometry.py      # CARiN coordinate transforms & polyline reconstruction
│   │   ├── header.py        # Superblock and block header definitions
│   │   └── cf1/             # Structure-driven bit-packing CF=1 decoders
│   │       ├── decoder_00.py # Map tiles (0x00-0x03)
│   │       ├── decoder_0e.py # Street directory (0x0E) + name blobs
│   │       └── decoder_14.py # Background feature layers (0x14-0x16, 0x1C-0x1E)
│   ├── osm/                 # OpenStreetMap ingestion tools (osmium pipeline)
│   ├── serializer/          # CARiN binary serialization & block packer
│   └── cli.py               # Python CLI interface
├── carindb-rs/              # High-performance Rust CLI toolkit
│   ├── src/
│   │   ├── iso.rs           # Memory-mapped ISO volume reader
│   │   ├── cf1.rs           # Native CF=1 bit-packing decoders
│   │   ├── codec.rs         # CF=2 zlib codec & payload handling
│   │   ├── tools.rs         # dump-type, stats, and xref implementations
│   │   └── main.rs          # CLI entry point
│   └── Cargo.toml
├── docs/
│   ├── CARINDB_BLUEPRINT_EN.md  # Monolithic format blueprint
│   ├── carindb/             # Modular documentation parts 0-8
│   └── fw/                  # Annotated firmware listings & provenance
├── scripts/
│   ├── codec_cf1/           # Decoders and oracle validation scripts
│   ├── geo/                 # Spatial index checks and coordinate optimizers
│   ├── routing/             # Graph analysis, TMC checks, and house number tools
│   └── firmware/            # Firmware extractors and disassemblers
└── tests/                   # Pytest test suite (37 unit tests)
```

---

## 🚀 Quick Start

### 1. Requirements

* Python 3.9+
* Rust toolchain (optional, for `carindb-rs` high-performance tools)
* Access to a CARiN disc dump (e.g. BMW High MK4 `NAV_DB_*.ISO`) in `dataset/`

### 2. Dataset (Navigation ISOs & Firmware)

Due to file sizes and licensing restrictions, disc dumps cannot be hosted directly in this repository. Research map disc dumps (e.g. `NAV_DB_21708.ISO`, `NAV_DB_21734.bin`) and firmware images (`NAV_SW(v32).iso`) can be downloaded here:

📁 **[Download Dataset (Google Drive)](https://drive.google.com/drive/folders/1KZH93y9ltZBkkjlIm-hBnoqKcCdnsqJa?usp=sharing)**

Place them (or symlinks) in the `dataset/` folder at project root:
```bash
mkdir -p dataset
# Place NAV_DB_21708.ISO into dataset/
```

### 3. Python Environment Setup

```bash
# Clone the repository
git clone https://github.com/fdemusso/OpenCarin.git
cd OpenCarin

# Using uv (recommended)
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Or using standard python venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 4. Inspecting Database Blocks & Spatial Lookup

```python
from carin.parser.iso import IsoImage, CarinVolume, to_wgs84
from carin.parser.spatial import tiles_at
from carin.parser.house_numbers import segment_house_numbers

# Open ISO image (virtual sector space DB_0 + DB_1)
vol = CarinVolume(IsoImage('dataset/NAV_DB_21708.ISO'))

# Query spatial index: which street tile covers a coordinate? (e.g. Milan: 9.19° E, 45.46° N)
tiles = tiles_at(vol, layer=0, lon=9.1900, lat=45.4600)
print(f"Tiles covering location: {[hex(b) for b in tiles]}")

# Read and decode a tile block
if tiles:
    blk = vol.block(tiles[0] >> 8)
    print(f"Block Sector: {blk.sector}, Type: {blk.type:#04x}, CF: {blk.comp}")
    print(f"Decompressed Payload Length: {len(blk.payload)} bytes")
    
    lon, lat = to_wgs84(blk.bbox.x_min, blk.bbox.y_min)
    print(f"Bounding Box SW Corner: {lat:.4f}° N, {lon:.4f}° E")
```

### 5. High-Performance Rust CLI (`carindb-rs`)

For fast exploration across multi-gigabyte ISOs:

```bash
cd carindb-rs

# Mass-dump all decoded blocks of a specific type (e.g. 0x18 TMC index)
cargo run --release -- --iso ../dataset/NAV_DB_21708.ISO dump-type 0x18 --out ./dump_0x18

# Compute cross-instance byte statistics for a block type
cargo run --release -- --iso ../dataset/NAV_DB_21708.ISO stats 0x0A

# Search for all occurrences of a BLOCK_ID across all decoded blocks in one pass
cargo run --release -- --iso ../dataset/NAV_DB_21708.ISO xref 0x00000304
```

### 6. Running Tests

```bash
# Run Python test suite
uv run --with pytest pytest

# Run Rust test suite
cargo test --manifest-path carindb-rs/Cargo.toml
```

---

## 🤝 How to Contribute

Whether you have experience in:
- **Disassembling MIPS / m68k / SH-4 firmware** (Ghidra, IDA, Capstone)
- **Routing graph algorithms** (contraction hierarchies, A*, spatial partitioning, OSRM/Valhalla)
- **OpenStreetMap data manipulation** (`osmium`, `shapely`, GeoJSON)
- **Automotive reverse engineering & retro tech**

...your help is warmly welcomed!

1. Check out the issues tab or open a discussion on road routing semantics.
2. Read [docs/carindb/06-objectives-roadmap.md](docs/carindb/06-objectives-roadmap.md) and [docs/CARINDB_BLUEPRINT_EN.md](docs/CARINDB_BLUEPRINT_EN.md).
3. Submit PRs for decoders, serializers, documentation improvements, or tests.

---

## ☕ Support the Project

If you appreciate this reverse-engineering effort, find the findings useful, or simply want to support the journey of bringing modern maps to classic cars, you can buy me a coffee!

<a href="https://buymeacoffee.com/fdemusso" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

Or visit: **[buymeacoffee.com/fdemusso](https://buymeacoffee.com/fdemusso)**
