"""Step 3: what changed between the disc and OSM in the area -> dataset/delta.csv.

Both sides are sampled every 8 m along their polylines. A disc segment is `present` if at least
--cover of its samples lie within --tol metres of a drivable OSM way, else `removed` (on the
disc, not in OSM). An OSM way is `present` if at least --cover of its samples lie within --tol of
a disc segment, else `new`. Pedestrian and cycle ways (footway, path, steps, cycleway, ...) are
counted apart: the disc is a car map.

    uv run python examples/04_update_modugno_roundabout/03_delta.py [--tol 15] [--cover 0.7] [--tag before|after]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, RADIUS_M, dist_point_polyline, samples, to_m

NOT_FOR_CARS = {"footway", "path", "steps", "cycleway", "pedestrian", "bridleway", "corridor",
                "track", "proposed", "construction", "platform"}


def parse(wkt: str):
    return [tuple(map(float, p.split())) for p in re.findall(r"\(([^)]*)\)", wkt)[0].split(",")]


def covered(coords, others, tol: float) -> float:
    """Fraction of coords' samples within tol metres of some polyline in `others`."""
    pts = samples(coords)
    ok = sum(1 for p in pts if any(dist_point_polyline(p, o) <= tol for o in others))
    return ok / len(pts)


def fold(s: str) -> str:
    return re.sub(r"\s+", " ", s.casefold()).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=15.0)
    ap.add_argument("--cover", type=float, default=0.7)
    ap.add_argument("--tag", default="before", help="which disc state: before or after the patch")
    args = ap.parse_args()

    disc = list(csv.DictReader(open(DATA / f"disc_segments_{args.tag}.csv")))
    osm = list(csv.DictReader(open(DATA / "osm_ways.csv")))
    for r in disc:
        r["c"] = parse(r["wkt"])
    for r in osm:
        r["c"] = parse(r["wkt"])
    car_osm = [r for r in osm if r["highway"] not in NOT_FOR_CARS]
    near = lambda r: min(abs(x) + abs(y) for x, y in map(lambda c: to_m(*c), r["c"])) < 2 * RADIUS_M

    out, stat = [], Counter()
    for r in disc:
        f = covered(r["c"], [o["c"] for o in car_osm], args.tol)
        kind = "present" if f >= args.cover else "removed"
        stat[f"disc segments {kind}"] += 1
        stat[f"disc length {kind} (m)"] += float(r["length_m"])
        out.append({"kind": kind, "source": "disc", "id": f"{r['tile']}/{r['index']}", "name": r["name"],
                    "type": f"class {r['class']}", "length_m": r["length_m"], "covered": round(f, 2),
                    "name_in_osm": "", "wkt": r["wkt"]})
    osm_names = {fold(o["name"]) for o in car_osm if o["name"]}
    disc_names = {fold(r["name"]) for r in disc if r["name"]}
    for o in osm:
        if o["highway"] in NOT_FOR_CARS:
            stat[f"osm not for cars ({o['highway']})"] += 1
            continue
        f = covered(o["c"], [r["c"] for r in disc], args.tol)
        kind = "present" if f >= args.cover else "new"
        stat[f"osm ways {kind}"] += 1
        stat[f"osm length {kind} (m)"] += float(o["length_m"])
        out.append({"kind": kind, "source": "osm", "id": o["id"], "name": o["name"],
                    "type": o["highway"] + (f" ({o['junction']})" if o["junction"] else ""),
                    "length_m": o["length_m"], "covered": round(f, 2),
                    "name_in_osm": "", "wkt": o["wkt"]})
    for r in out:
        if r["kind"] != "present" and r["name"]:
            r["name_in_osm" if r["source"] == "disc" else "name_in_osm"] = (
                "yes" if fold(r["name"]) in (osm_names if r["source"] == "disc" else disc_names) else "no")
    out.sort(key=lambda r: (r["kind"], -float(r["length_m"])))
    with open(DATA / f"delta_{args.tag}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)

    print(f"tolerance {args.tol:g} m, cover {args.cover:g}")
    for k in sorted(stat):
        v = stat[k]
        print(f"  {k:40s} {v:8.0f}" if isinstance(v, float) else f"  {k:40s} {v:8d}")
    print("\nnew or removed, longest first:")
    for r in out:
        if r["kind"] != "present" and float(r["length_m"]) >= 30:
            print(f"  {r['kind']:8s} {r['source']:5s} {r['id']:>16s} {r['type']:28s} {r['length_m']:>7s} m  "
                  f"cov {r['covered']:.2f}  {r['name']}")

    # Roundabouts need a topological test: a ring lies within a few metres of the old crossing's arms,
    # so a plain coverage test calls it present. On the disc a roundabout is a run of segments with
    # junction type 6 (S4 +0x11 & 0x0F); an OSM roundabout is on the disc if such segments lie on it.
    disc_ring = [r["c"] for r in disc if r["junction"] == "6"]
    print(f"\nroundabouts: {len(disc_ring)} disc segments of junction type 6 in the area")
    rows = []
    for o in osm:
        if o["junction"] != "roundabout":
            continue
        f = covered(o["c"], disc_ring, 6.0) if disc_ring else 0.0
        rows.append((o["id"], o["length_m"], f))
        print(f"  osm {o['id']:>12s} {o['length_m']:>6s} m  on a disc junction-6 segment: {f:.2f}  "
              f"{'ON THE DISC' if f >= args.cover else 'NOT ON THE DISC'}")
    stat_rings = sum(1 for _, _, f in rows if f >= args.cover)
    print(f"  {stat_rings} of {len(rows)} OSM roundabout ways are on the disc")
    near_old = [r for r in disc if r["junction"] in ("0", "9") and min(
        (x * x + y * y) ** 0.5 for x, y in map(lambda c: to_m(*c), r["c"])) < 45]
    print(f"  disc segments within 45 m of the centre (the old crossing): {len(near_old)}")


if __name__ == "__main__":
    main()
