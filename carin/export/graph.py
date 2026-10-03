"""Join parsed tiles into one routable graph.

Nodes of different tiles are the same crossing when a section 6 node names its twin
(`+8` BLOCK_ID, `+12` offset of the twin record). Nodes are identified by (tile, offset),
never by coordinates, so two crossing roads on a bridge (same position, separate nodes)
stay apart (03-road-network.md §6.7, "Crossings without a junction").
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .tiles import NodeKey, TileData

# direction restriction, +0x0B bits 4-5
DIR_BOTH, DIR_FORWARD, DIR_REVERSE, DIR_CLOSED = 0, 1, 2, 3
ONEWAY_NAMES = {DIR_BOTH: "both", DIR_FORWARD: "forward", DIR_REVERSE: "reverse", DIR_CLOSED: "closed"}


def haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 12742000.0 * math.asin(min(1.0, math.sqrt(h)))


def polyline_m(coords: List[Tuple[float, float]]) -> float:
    return sum(haversine_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


@dataclass
class Node:
    id: int
    lon: float
    lat: float


@dataclass
class Edge:
    id: int
    tile: int                       # tile sector
    index: int                      # S4 record index in that tile
    u: int                          # start node id
    v: int                          # end node id
    coords: List[Tuple[float, float]]
    name: Optional[str]
    locality: Optional[str]
    road_class: int                 # +0x10 & 0x0F, 0 motorway .. 6 pedestrian/service
    subtype: int                    # +0x10 >> 4 (class 6 subtype)
    form: int                       # +0x0B & 0x0F
    direction: int                  # DIR_*
    toll: bool
    junction: int                   # +0x11 & 0x0F, 6 = roundabout
    junction_hi: int                # +0x11 >> 4
    speed_code: int                 # +0x0A & 0x1F, roughly km/h / 4
    built_up: bool
    slip_role: int                  # +0x18 & 3
    length_m: float                 # stored length (+0x0C), falls back to geometry
    geom_m: float                   # length of the decoded polyline

    @property
    def speed_kmh(self) -> int:
        return self.speed_code * 4

    @property
    def roundabout(self) -> bool:
        return self.junction == 6

    @property
    def oneway(self) -> str:
        return ONEWAY_NAMES[self.direction]

    @property
    def car_ok(self) -> bool:
        """Mirror of the firmware's can_traverse (rpmod:004360): class 6 and junction 3/4
        are rejected, junction 3/4 only when the high nibble is not 4."""
        if self.road_class == 6 or self.direction == DIR_CLOSED:
            return False
        if self.junction in (3, 4) and self.junction_hi != 4:
            return False
        return True


@dataclass
class Restriction:
    from_edge: int
    to_edge: int
    via_node: int
    flag: int
    kind: str                       # "no_u_turn" | "no_turn" | "other"


@dataclass
class Graph:
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    restrictions: List[Restriction] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)


class _UnionFind:
    def __init__(self) -> None:
        self.parent: Dict[NodeKey, NodeKey] = {}

    def add(self, k: NodeKey) -> None:
        self.parent.setdefault(k, k)

    def find(self, k: NodeKey) -> NodeKey:
        root = k
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[k] != root:
            self.parent[k], k = root, self.parent[k]
        return root

    def union(self, a: NodeKey, b: NodeKey) -> None:
        self.add(a)
        self.add(b)
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)      # deterministic root


def build_graph(tiles: Iterable[TileData], twin_tolerance_m: float = 2.0) -> Graph:
    tiles = list(tiles)
    uf = _UnionFind()
    pos: Dict[NodeKey, Tuple[float, float]] = {}
    for t in tiles:
        for k, n in t.nodes.items():
            uf.add(k)
            pos[k] = (n.lon, n.lat)
    twins = twin_missing = twin_far = 0
    for t in tiles:
        for k, n in t.nodes.items():
            if n.twin is None:
                continue
            twins += 1
            if n.twin not in pos:
                twin_missing += 1                # neighbour outside the exported window
                continue
            uf.union(k, n.twin)
            if haversine_m(pos[k], pos[n.twin]) > twin_tolerance_m:
                twin_far += 1

    ids: Dict[NodeKey, int] = {}
    g = Graph()

    def node_id(key: NodeKey) -> int:
        root = uf.find(key)
        if root not in ids:
            ids[root] = len(g.nodes)
            lon, lat = pos[root]
            g.nodes.append(Node(ids[root], lon, lat))
        return ids[root]

    edge_of: Dict[Tuple[int, int], int] = {}
    pending = []
    for t in tiles:
        for e in t.edges:
            geom = polyline_m(e.coords)
            length = float(e.length_m) if e.length_m else geom
            eid = len(g.edges)
            edge_of[(e.sector, e.index)] = eid
            g.edges.append(Edge(
                id=eid, tile=e.sector, index=e.index,
                u=node_id(e.start), v=node_id(e.end), coords=e.coords,
                name=e.name, locality=e.locality,
                road_class=e.class_byte & 0x0F, subtype=(e.class_byte >> 4) & 0x07,
                form=e.form_byte & 0x0F, direction=(e.form_byte >> 4) & 3,
                toll=bool(e.form_byte & 0x40), junction=e.junction_byte & 0x0F,
                junction_hi=e.junction_byte >> 4, speed_code=e.speed_byte & 0x1F,
                built_up=bool(e.speed_byte & 0x80), slip_role=e.slip_byte & 3,
                length_m=length, geom_m=geom))
            if e.restrictions:
                pending.append(e)

    unresolved = 0
    for e in pending:
        eid = edge_of[(e.sector, e.index)]
        for r in e.restrictions:
            tid = edge_of.get((e.sector, r.target_index)) if r.target_index is not None else None
            if tid is None:
                unresolved += 1
                continue
            if r.flag in (0, 1):
                kind = "no_u_turn" if tid == eid else "no_turn"
            else:
                kind = "other"
            g.restrictions.append(Restriction(eid, tid, node_id(r.via), r.flag, kind))

    g.stats = {
        "tiles": len(tiles), "nodes": len(g.nodes), "edges": len(g.edges),
        "restrictions": len(g.restrictions), "restrictions_unresolved": unresolved,
        "segments_skipped": sum(t.skipped for t in tiles),
        "twin_links": twins, "twin_outside_window": twin_missing, "twin_position_mismatch": twin_far,
    }
    return g


def components(graph: Graph) -> List[List[int]]:
    """Weakly connected components of the node set, largest first (all edges, any direction)."""
    parent = list(range(len(graph.nodes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in graph.edges:
        ra, rb = find(e.u), find(e.v)
        if ra != rb:
            parent[ra] = rb
    groups: Dict[int, List[int]] = {}
    for n in range(len(graph.nodes)):
        groups.setdefault(find(n), []).append(n)
    return sorted(groups.values(), key=len, reverse=True)
