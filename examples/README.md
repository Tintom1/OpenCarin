# OpenCarin Examples

This directory contains practical examples and scripts that demonstrate how to use the reverse-engineered `carin-compiler` components to extract and process data from the CARINdb ISO.

## Available Examples

### `01_extract_country_network`
Demonstrates how to extract the full road network (graph) for a single country. Since the CARINdb does not partition the topological graph by country ID, this example uses a **spatial extraction method**:
1. Uses a standard WGS84 GeoJSON of the target country.
2. Projects the boundaries into CARIN's internal coordinate system.
3. Filters the spatial index of all 74,247 `0x0E` road parcels to find exact geometric intersections.
4. Outputs the specific list of `0x0E` virtual sectors containing the country's roads.

### `04_update_modugno_roundabout`
Updates a piece of the map from OpenStreetMap on a copy of the disc: a roundabout built at Modugno after the 2016 data replaces the old crossing in a street-level tile (delta against OSM, patch of the tile, re-encode, write in place, read back with the Python and the Rust decoder). Every change is logged in `CHANGES.md`.

## Setup
Before running the examples, ensure your environment is fully set up:
```bash
# Sync dependencies (including shapely for geospatial operations)
uv sync

# Ensure the spatial parcel index has been built (requires the ISO)
python scripts/routing/find_parcel.py
```
