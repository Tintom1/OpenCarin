"""Shared constants and flat-earth geometry for the Modugno roundabout test."""
from __future__ import annotations

from math import cos, hypot, radians
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "dataset"
ISO_COPY = DATA / "NAV_DB_21708_copy.ISO"      # working copy of the disc, never the original

# 41°05'16.1"N 16°47'22.6"E: the roundabout that did not exist in the 2016 data
CENTER = (16.789611, 41.087806)                # lon, lat
RADIUS_M = 500.0                               # area of the test
M_LAT = 111_320.0
M_LON = M_LAT * cos(radians(CENTER[1]))


def to_m(lon: float, lat: float):
    """Metres east / north of CENTER (flat earth, good to < 1 m over 1 km)."""
    return (lon - CENTER[0]) * M_LON, (lat - CENTER[1]) * M_LAT


def length_m(coords) -> float:
    pts = [to_m(*c) for c in coords]
    return sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def dist_point_polyline(p, coords) -> float:
    """Distance in metres from metre-point p to a lon/lat polyline."""
    pts = [to_m(*c) for c in coords]
    best = float("inf")
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        ln = dx * dx + dy * dy
        f = 0.0 if ln == 0 else max(0.0, min(1.0, ((p[0] - x0) * dx + (p[1] - y0) * dy) / ln))
        best = min(best, hypot(p[0] - (x0 + f * dx), p[1] - (y0 + f * dy)))
    if len(pts) == 1:
        best = hypot(p[0] - pts[0][0], p[1] - pts[0][1])
    return best


def samples(coords, step_m: float = 8.0):
    """Points every ~step_m along a lon/lat polyline, as metre-points (ends included)."""
    pts = [to_m(*c) for c in coords]
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(hypot(x1 - x0, y1 - y0) // step_m))
        out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(1, n + 1)]
    return out


def wkt(coords) -> str:
    return "LINESTRING(" + ", ".join(f"{x:.6f} {y:.6f}" for x, y in coords) + ")"
