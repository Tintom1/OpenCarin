# OpenCarin (CarinCompiler)

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Format: CARINdb](https://img.shields.io/badge/format-CARiN%20%2F%20CarinDB-orange.svg)](#)
[![Buy Me A Coffee](https://img.shields.io/badge/Donate-Buy%20Me%20A%20Coffee-yellow.svg)](https://buymeacoffee.com/fdemusso)

**OpenCarin** is an open-source reverse-engineering and map compilation toolkit for the proprietary **Philips/VDO CARiN** navigation database format (`CARINdb`, `DB_0`, `DB_1`, `CARINET`).

These navigation databases were widely used in iconic late 1990s and 2000s automotive systems, including:
* **BMW Navigation Systems**: MK3 (CD, MIPS32) and MK4 (DVD, Hitachi SH-4) across BMW E46, E39, E38, X5 E53, Z4 E85
* **Renault / Nissan**: Carminat Navigation Informée 1 (CNI1)
* **VDO Dayton**: PC5000, PC5200, MS5000 series
* Systems across Opel/Vauxhall, Rover, Land Rover, and others

Official map updates ceased years ago (mostly frozen around 2015–2019). **The mission of this project is to reverse-engineer the CARiN binary format and build a compiler pipeline that converts modern OpenStreetMap (OSM) data into functional, bootable DVD/CD navigation discs for these classic cars.**

---

## 🧭 Project Status & Key Breakthroughs

We have made major progress on the binary format. Every technical finding below is byte-verified on real disc images (e.g. BMW High 2015 `NAV_DB_21708.ISO` and 2019 `NAV_DB_21734.bin`):

* ✅ **Addressing & Block Chaining Solved**: the addressing unit depends on the medium.
  * **DVD** (BMW MK4): the sector size is **512 bytes**, and the virtual address space spans `DB_0` (first 2 GiB) and `DB_1` via `virtual_sector = file_index * 0x400000 + local_sector`.
  * **CD** (e.g. Carminat CNI1): the database is a single `/carindb` file and the unit is **2048 bytes**.
  * The disc's `ABSTRACT` names the unit: `carinet16s512` on `NAV_DB_21708`, `carinet16s2048` on CD-ID 21594.
  * With the right unit, the block chain covers 100% of the file with no gaps (checked on DVD and on CD-IDs 2952 and 21594).
* ✅ **Coordinate System Cracked**: 
  $$X = (lon + 30.0) \times \frac{2 \times 10^9}{360}, \quad Y = (lat + 0.0) \times \frac{2 \times 10^9}{360}$$
  Origin is at $30^\circ\text{ W}$ on the Equator, linear in latitude (no Mercator projection). 1 unit $\approx 2\text{ cm}$ at the equator. Verified with 38 European city anchors (RMS error $2.0\text{ km}$, matching published city-center offsets).
* ✅ **Quadtree Grid & Bounding Boxes Mapped**: on the DVD, tile boundaries are fixed on multiples of 98,304 units ($3 \times 2^{15}$). CD discs use a different grid, so the 98,304 rule does not apply there:
  * CD-ID 21594: tile sides are powers of two, $2^{17}$ to $2^{21}$.
  * CD-ID 2952: tile sides are $46 \times 2^{16}$, halved per level.
  * On both, the 1:1 / 2:1 aspect and the ×64 local scale still hold.
* ✅ **POI Records Decoded (`0x06`)**: `T[0x32]`-byte records (28; 20 on DB-REL 22), exact local scale 64 ($1.2\text{ m}$ resolution), containing over 2 million POIs linked to street parcels and brand catalogs.
* ✅ **Feature Records Decoded (`0x16`, `0x14`, `0x1C`, `0x1D`, `0x1E`)**: 20-byte records with absolute coordinates and Latin-1 name strings.
* ✅ **`COMPRESSION_FLAG = 1` Cracked (September 2026)**:
  Covering 30% of all disc blocks (96,011 blocks), this was **not a dictionary compression codec** (all LZ/Huffman variants had failed). By reverse-engineering navigation unit firmware (`pbp` in m68k CC-93, `db_pub` in MIPS32 Mk3/RR), we discovered it is **structure-driven bit-packing** parameterized by the superblock's `RECORD_SIZE_TABLE`.
  * Fully decoded 1,200/1,200 type `0x00` blocks, verified against actual European road networks (El Hierro, Algarve, Alentejo).
  * Fully decoded type `0x0E` (road parcels, 74,247 blocks): S0/S1 verified 2026-09-18; Section 2 geometry layout verified 2026-09-19 via m68k firmware write trace (`pbp+0x41c0`). The 24-byte S2 record stores raw anchor coordinates + raw compressed deltas; the routing engine applies sign-extension at query time. 0/133 bad anchor indices on sector 2252227.
    * CD discs, both CD-IDs: the S0 → S1 → S2 structure holds on 100% of plain and decoded blocks.
    * The S1 record size is `T[0x41]`, which is 4 on DB-REL 22, not 6.
    * The S2 fields mean something other than first thought: S2 holds no geometry, but a link to a run of road segments in a `0x00` map tile plus that street's even/odd house-number ranges. Its anchor is the tile's centre. Checked on CD-IDs 2952, 21594, 21708 and 21734; see [`docs/carindb/03-road-network.md`](docs/carindb/03-road-network.md) §6.3.1.

---

## 🛠 Where Help is Desperately Needed ("The Heavy Lifting")

While the foundation is cracked, building a full compiler from OpenStreetMap requires tackling the remaining core reverse-engineering tasks. **We are looking for reverse engineers, embedded firmware hackers, and GIS enthusiasts to collaborate on:**

### 1. Road Network Parcel Semantics (`BLOCK_TYPE = 0x0E`) 🔴 Critical
* **74,247 blocks** (CD-ID 21708). From disc data they are a **street-name directory**, not the road graph:
  * `SECTION_0` (8 B, alphabetical) = street name pointer, `FLAGS`, `B`, locality pointer or 0, pointer to `SECTION_1` (stride `T[0x41]`: 6, or 4 on DB-REL 22).
  * `SECTION_2` (24 B) = a `0x00` tile (`BLOCK_ID` and centre), a run of that tile's road segments (`SECTION_4` offset + count), and even/odd house-number ranges.
  * Details and checks: [`docs/carindb/03-road-network.md`](docs/carindb/03-road-network.md) §6.3.1.
* **Still needed**: the meaning of `FLAGS` (`0x00, 0x01, 0x02, 0x10, 0x11`; bit 4 is common on word-reordered name variants) and `B`; and where the router actually gets its topology, since `0x0E` holds none.
* **Crucial Question**: Does the firmware route planner rely on **precomputed graph shortcuts / hierarchical boundaries** between parcels, or does it dynamically traverse the graph at runtime using topology and costs? (See [docs/PROMPT_SEMANTICA_STRADALE.md](docs/PROMPT_SEMANTICA_STRADALE.md) for full context).

### 2. Georeferencing Non-BBox Parcels (`0x0C`, `0x0E`, `0x10`) 🔴 Critical
* Unlike POI (`0x06`) and feature (`0x16`) blocks, road network parcels (`0x0E`) and street name parcels (`0x10`) have no explicit bounding box in their headers.
* They are indexed hierarchically through index blocks (`0x0D`, `0x0F`, `0x11`). We need to document the exact lookup chain from coordinate / region to parcel block.
* `0x0E` is now georeferenced indirectly: every `SECTION_2` record names a `0x00` tile, which has a bbox. `0x10` POI details carry absolute coordinates. `0x0C` is still open.

### 3. Decoder Ports for the Remaining Types 🟠 High
* Port the bit-packing decoder logic from MIPS firmware (`db_pub`) for the remaining block types into Python (`carin/parser/cf1/`).
  * Already ported: types `0x00`, `0x0E` and `0x14`–`0x16`.
  * On CD-ID 21594, the only `COMPRESSION_FLAG = 1` blocks without a decoder are types `0x1C`–`0x1E` (116 blocks).

### 4. OpenStreetMap to CARiN Serializer & ISO Compiler 🟡 Ongoing
* Pipeline to parse OSM PBF data (`osmium`), partition nodes/ways into 512-byte sector-aligned parcels, compute coordinate transforms, write CARiN block headers, and package a bootable ISO 9660 filesystem.

---

## 📚 Essential Documentation

Before diving into code, please read the technical blueprints:

* 📖 **[docs/CARINDB_BLUEPRINT_EN.md](docs/CARINDB_BLUEPRINT_EN.md)** 
  * The definitive specification of the format: byte maps, superblock layout, coordinate formulas, bit-packing primitives, and verification roadmap.
* 💻 **`docs/fw/`**: Disassembled and annotated assembly listings of the original firmware decoder routines (`mips_*.asm` for Mk3 MIPS32, `m68k_pbp_decoders.asm` for CC-93 m68k).

---

## 📂 Repository Structure

```
├── carin/
│   ├── parser/
│   │   ├── iso.py           # ISO reader & CarinVolume abstraction over DB_0 + DB_1
│   │   ├── cf1.py           # Bit-packing CF=1 decoder (from firmware reversing)
│   │   ├── calibration.py   # Geographic calibrator (WGS84 <-> CARiN coordinates)
│   │   ├── compression.py   # Compression analysis & oracle validation tools
│   │   └── header.py        # Block header structures
│   ├── osm/                 # OpenStreetMap ingestion tools (osmium pipeline)
│   ├── serializer/          # CARiN binary serialization & block packer
│   └── cli.py               # CLI interface
├── docs/
│   ├── CARINDB_BLUEPRINT_EN.md  # Complete English technical specification
│   ├── fw/                      # Disassembled firmware routines (MIPS & m68k)
│   └── agents/                  # Research notes and architecture papers
├── scripts/                     # Reverse engineering & analysis utilities
│   ├── cf1_sweep.py             # Mass-validation of CF=1 block decoding
│   ├── optimize_coords.py       # Levenberg-Marquardt coordinate calibrator
│   ├── extract_anchors.py       # Extracts city label anchor points from ISO
│   ├── extract_firmware.py      # Extracts firmware binaries from NAV_SW CD
│   ├── mips_dis.py / m68k_dis.py # Firmware disassemblers
│   └── ...
└── tests/                       # Test suite
```

---

## 🚀 Quick Start

### 1. Requirements

* Python 3.9+
* Capstone disassembly engine (with M68K and MIPS support enabled)
* Access to a CARiN disc dump (e.g. BMW High MK4 `NAV_DB_*.ISO`) in `dataset/`

### 2. Dataset (Navigation ISOs & Firmware)

Due to file sizes (multi-gigabyte disc dumps) and licensing restrictions, raw database dumps and firmware ISOs cannot be hosted directly in this GitHub repository.

The research dataset containing map disc dumps (e.g., `NAV_DB_21708.ISO`, `NAV_DB_21734.bin`) and navigation firmware (`NAV_SW(v32).iso`) can be downloaded here:

📁 **[Download Dataset (Google Drive)](https://drive.google.com/drive/folders/1KZH93y9ltZBkkjlIm-hBnoqKcCdnsqJa?usp=sharing)**

Place the downloaded files (or symlinks to them) into a `dataset/` directory at the project root:

```bash
mkdir -p dataset
# Place NAV_DB_21708.ISO, NAV_SW(v32).iso, etc. into dataset/
```

### 3. Setup

```bash
# Clone the repository
git clone https://github.com/fdemusso/OpenCarin.git
cd OpenCarin

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies in editable mode
pip install -e ".[dev]"
```

### 4. Inspecting Database Blocks

You can inspect and parse real CARiN blocks directly from Python:

```python
from carin.parser.iso import IsoImage, CarinVolume
from carin.parser.iso import to_wgs84

# Open ISO image (reads virtual sector space DB_0 + DB_1 without extracting)
vol = CarinVolume(IsoImage('dataset/NAV_DB_21708.ISO'))

# Inspect superblock
print("Volume Block Types:", vol.superblock.block_types)

# Read and decode a CF=1 bit-packed block (type 0x00, e.g. El Hierro)
blk = vol.block(3157624)
print(f"Block Sector: {blk.sector}, Type: {blk.type:#04x}, CF: {blk.comp}")
print(f"Decompressed Payload Length: {len(blk.payload)} bytes")

# Convert CARiN units to WGS84
lon, lat = to_wgs84(blk.bbox.x_min, blk.bbox.y_min)
print(f"Bounding Box SW Corner: {lat:.4f}° N, {lon:.4f}° E")
```

---

## 🤝 How to Contribute

Whether you have experience in:
- **Disassembling MIPS / m68k / SH-4 firmware** (Ghidra, IDA, Capstone)
- **Routing graph algorithms** (contraction hierarchies, A*, spatial partitioning)
- **OpenStreetMap data manipulation** (`osmium`, `shapely`, GeoJSON)
- **Automotive reverse engineering & retro tech**

...your help is warmly welcomed!

1. Check out the issues tab or open a discussion on road parcel semantics.
2. Read [docs/CARINDB_BLUEPRINT_EN.md](docs/CARINDB_BLUEPRINT_EN.md).
3. Grab a firmware dump or an ISO slice and explore with the tools in `scripts/`.
4. Submit PRs for decoders, serializers, documentation improvements, or tests.

---

## ☕ Support the Project

If you appreciate this reverse-engineering effort, find the findings useful, or simply want to support the journey of bringing modern maps to classic cars, you can buy me a coffee!

<a href="https://buymeacoffee.com/fdemusso" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>

Or visit: **[buymeacoffee.com/fdemusso](https://buymeacoffee.com/fdemusso)**

