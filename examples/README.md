# OpenCarin Examples

This directory contains practical examples and scripts that demonstrate how to use the reverse-engineered `carin-compiler` components to extract and process data from the CARINdb ISO.

## Available Examples

### `01_extract_country_network`
Demonstrates how to extract the full road network (graph) for a single country. Since the CARINdb does not partition the topological graph by country ID, this example uses a **spatial extraction method**:
1. Uses a standard WGS84 GeoJSON of the target country.
2. Projects the boundaries into CARIN's internal coordinate system.
3. Filters the spatial index of all 74,247 `0x0E` road parcels to find exact geometric intersections.
4. Outputs the specific list of `0x0E` virtual sectors containing the country's roads.

### `03_address_lookup`
Looks up a street address (country, city, street, number) through the disc's own search structures (`0x0A` → `0x0D` → `0x0C` → `0x0F` → `0x0E` → `0x00` / `0x04`) and prints its position, with an OpenStreetMap link to check it.

### `04_update_modugno_roundabout`
Updates a piece of the map from OpenStreetMap on a copy of the disc: a roundabout built at Modugno after the 2016 data replaces the old crossing in a street-level tile and its coarse tile, with every reference into them rewritten (delta against OSM, tile editor, validation, read back with the Python and the Rust decoder). Every change is logged in `CHANGES.md`; not run on a unit (`HARDWARE_TEST.md`).

## Setup
Before running the examples, ensure your environment is fully set up:
```bash
# Sync dependencies (including shapely for geospatial operations)
uv sync

# Ensure the spatial parcel index has been built (requires the ISO)
python scripts/routing/find_parcel.py
```
