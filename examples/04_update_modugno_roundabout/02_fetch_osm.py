"""Step 2: OpenStreetMap highways around the test point -> dataset/osm_ways.json + osm_ways.csv.

Overpass API, one request, kept on disk so the later steps do not need the network.

    uv run python examples/04_update_modugno_roundabout/02_fetch_osm.py
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CENTER, DATA, RADIUS_M, length_m, wkt

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
QUERY = f'[out:json][timeout:90];way["highway"](around:{RADIUS_M + 100:.0f},{CENTER[1]},{CENTER[0]});out geom tags;'


def main() -> None:
    out = DATA / "osm_ways.json"
    els = None
    for attempt in range(3):
        for url in ENDPOINTS:
            subprocess.run(["curl", "-s", "-m", "120", "-A", "opencarin-research/0.1 (github fdemusso)",
                            "--data-urlencode", f"data={QUERY}", url, "-o", str(out)], check=True)
            try:
                els = json.load(open(out))
                break
            except ValueError:
                print(f"{url}: busy or error, trying the next")
        if els:
            break
        time.sleep(10)
    if els is None:
        raise SystemExit("Overpass did not answer; rerun later")
    stamp = els.get("osm3s", {}).get("timestamp_osm_base", "?")
    rows = []
    for el in els["elements"]:
        coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
        t = el["tags"]
        rows.append({"id": el["id"], "highway": t["highway"], "name": t.get("name", ""),
                     "junction": t.get("junction", ""), "oneway": t.get("oneway", ""),
                     "length_m": round(length_m(coords), 1), "wkt": wkt(coords)})
    with open(DATA / "osm_ways.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} ways, OSM data of {stamp} -> dataset/osm_ways.csv")


if __name__ == "__main__":
    main()
