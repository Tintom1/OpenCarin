"""Travel-time model for exported edges.

The disc stores a speed category per segment (`+0x0A & 0x1F`, roughly km/h / 4). Two things make
it unusable at face value:

  * category 0 means "no speed stored", not "very slow": it is on 520 of 623 motorway edges and
    106.7 of 123 motorway km around Deurne (48 more on class 1 roads). Those edges get a default
    speed per road bucket (`unknown_kmh`).
  * the stored speeds are free-flow limits; real town driving is slower. A divisor per road
    bucket and a delay at junctions correct that. They can be fitted against the travel times of a
    reference routing engine; a JSON file with the fitted values is read by `CostModel.load`.

The default model uses the raw stored speeds and the unknown-speed defaults below, no divisors
and no junction delay.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict

BUCKETS = ("motorway", "main_open", "main_built", "minor_open", "minor_built")
UNKNOWN_KMH = {"motorway": 100.0, "main_open": 60.0, "main_built": 40.0,
               "minor_open": 40.0, "minor_built": 30.0}


def bucket(edge) -> str:
    if edge.road_class == 0:
        return "motorway"
    main = edge.road_class <= 2
    if edge.built_up:
        return "main_built" if main else "minor_built"
    return "main_open" if main else "minor_open"


@dataclass
class CostModel:
    divisor: Dict[str, float] = field(default_factory=lambda: {b: 1.0 for b in BUCKETS})
    unknown_kmh: Dict[str, float] = field(default_factory=lambda: dict(UNKNOWN_KMH))
    junction_s: float = 0.0
    min_kmh: float = 5.0

    def speed_kmh(self, edge) -> float:
        b = bucket(edge)
        if edge.speed_code == 0:
            return self.unknown_kmh[b]
        return max(edge.speed_kmh, self.min_kmh) / self.divisor[b]

    def edge_seconds(self, edge) -> float:
        return edge.length_m / (self.speed_kmh(edge) / 3.6)

    @classmethod
    def load(cls, path: str) -> "CostModel":
        d = json.load(open(path))
        m = cls()
        m.divisor.update(d.get("divisor", {}))
        m.unknown_kmh.update(d.get("unknown_kmh", {}))
        m.junction_s = d.get("junction_s", 0.0)
        return m

    def save(self, path: str) -> None:
        json.dump({"divisor": self.divisor, "unknown_kmh": self.unknown_kmh,
                   "junction_s": self.junction_s}, open(path, "w"), indent=2)
