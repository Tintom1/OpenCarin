"""The OSM side of the Modugno test: ways of the roundabout, junctions and arms, in lon/lat.

Everything is read from `dataset/osm_ways.json` (Overpass `out geom tags`, step 2). The six ring
junctions are the places where a link or an arm of Viale della Repubblica meets the ring: OSM shares
the node, so the coordinates are equal.
"""
from __future__ import annotations

import json
from math import hypot

from common import DATA, dist_point_polyline, to_m

RING_WAYS = (1326505905, 1383238947, 1383238946)
# way -> (role of its first vertex, role of its last vertex); R1..R6 are ring junctions, counter-clockwise
LINKS = {
    80640277: ("R2", "NE"),        # secondary_link, one-way, ring -> NE arm
    1326505910: ("NE", "R3"),      # secondary_link, one-way, NE arm -> ring
    1331933266: ("R4", "W"),       # secondary_link, one-way, ring -> Via Roma west
    80640279: ("W", "R5"),         # secondary_link, one-way, Via Roma west -> ring
    503040064: ("R6", None),       # Viale della Repubblica, one-way, ring -> south-east
    529215906: (None, "R1"),       # Viale della Repubblica, one-way, south-east -> ring
}


def ways() -> dict:
    return {e["id"]: e for e in json.load(open(DATA / "osm_ways.json"))["elements"]}


def geom(w: dict, wid: int) -> list[tuple[float, float]]:
    return [(p["lon"], p["lat"]) for p in w[wid]["geometry"]]


def ring_polygon(w: dict) -> list[tuple[float, float]]:
    """The roundabout as one closed counter-clockwise ring of (lon, lat), first vertex not repeated."""
    pts: list = []
    for wid in RING_WAYS:
        g = geom(w, wid)
        pts += g if not pts or pts[-1] != g[0] else g[1:]
    if pts[0] == pts[-1]:
        pts.pop()
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    return pts if area > 0 else pts[::-1]


def junctions(w: dict) -> dict[str, tuple[float, float]]:
    """R1..R6 (ring), NE and W (where the two links of an arm meet Via Roma / the SP1)."""
    out = {}
    for wid, (first, last) in LINKS.items():
        g = geom(w, wid)
        if first:
            out[first] = g[0]
        if last:
            out[last] = g[-1]
    return out


def project(poly, p) -> float:
    """Distance along a lon/lat polyline (metres) of the point nearest to metre-point p."""
    pts = [to_m(*c) for c in poly]
    best, s_best, acc = float("inf"), 0.0, 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        ln = dx * dx + dy * dy
        f = 0.0 if ln == 0 else max(0.0, min(1.0, ((p[0] - x0) * dx + (p[1] - y0) * dy) / ln))
        d = hypot(p[0] - (x0 + f * dx), p[1] - (y0 + f * dy))
        if d < best:
            best, s_best = d, acc + f * hypot(dx, dy)
        acc += hypot(dx, dy)
    return s_best


def interior(poly, s0: float, s1: float):
    """Vertices of a polyline strictly between arc distances s0 and s1 (metres)."""
    pts = [to_m(*c) for c in poly]
    out, acc = [], 0.0
    for k, c in enumerate(poly):
        if k:
            acc += hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1])
        if s0 + 0.3 < acc < s1 - 0.3:
            out.append(c)
    return out
