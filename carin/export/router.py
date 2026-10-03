"""Edge-based Dijkstra on an exported Graph (validation aid, not a product router).

State = (edge, direction). Direction flags, car access and `no_turn` / `no_u_turn` entries
are honoured. Cost = travel time at the stored speed category (floor 5 km/h). The
restriction direction (owner -> target at the via node) is the reading assumed in
docs/carindb/03-road-network.md §6.7; compare against OSRM to confirm it.
"""
from __future__ import annotations

import heapq
import math
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .cost import CostModel
from .graph import DIR_BOTH, DIR_FORWARD, DIR_REVERSE, Graph, haversine_m


class Router:
    def __init__(self, graph: Graph, respect_restrictions: bool = True,
                 model: CostModel | None = None) -> None:
        self.g = graph
        self.model = model or CostModel()
        degree: Dict[int, int] = defaultdict(int)
        for e in graph.edges:
            degree[e.u] += 1
            degree[e.v] += 1
        self.degree = degree
        self.edge_s = [self.model.edge_seconds(e) for e in graph.edges]
        self.out: Dict[int, List[Tuple[int, bool]]] = defaultdict(list)   # node -> (edge, forward)
        for e in graph.edges:
            if not e.car_ok:
                continue
            if e.direction in (DIR_BOTH, DIR_FORWARD):
                self.out[e.u].append((e.id, True))
            if e.direction in (DIR_BOTH, DIR_REVERSE):
                self.out[e.v].append((e.id, False))
        self.banned: Set[Tuple[int, int, int]] = set()
        if respect_restrictions:
            self.banned = {(r.from_edge, r.to_edge, r.via_node)
                           for r in graph.restrictions if r.kind in ("no_turn", "no_u_turn")}
        # coarse spatial hash for snapping
        self._cell = 0.01
        self._hash: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        used = {e.u for e in graph.edges if e.car_ok} | {e.v for e in graph.edges if e.car_ok}
        for nid in used:
            n = graph.nodes[nid]
            self._hash[(int(n.lon / self._cell), int(n.lat / self._cell))].append(nid)

    def snap(self, lon: float, lat: float, max_m: float = 2000.0) -> Optional[int]:
        cx, cy = int(lon / self._cell), int(lat / self._cell)
        best, best_d = None, max_m
        for r in range(0, 20):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    for nid in self._hash.get((cx + dx, cy + dy), ()):
                        n = self.g.nodes[nid]
                        d = haversine_m((lon, lat), (n.lon, n.lat))
                        if d < best_d:
                            best, best_d = nid, d
            if best is not None and r * self._cell * 80000 > best_d:
                break
        return best

    def route(self, src: int, dst: int) -> Optional[dict]:
        g = self.g
        dist: Dict[Tuple[int, bool], float] = {}
        prev: Dict[Tuple[int, bool], Optional[Tuple[int, bool]]] = {}
        heap: List[Tuple[float, int, bool]] = []
        for eid, fwd in self.out.get(src, ()):
            c = self.edge_s[eid]
            st = (eid, fwd)
            dist[st], prev[st] = c, None
            heapq.heappush(heap, (c, eid, fwd))
        goal = None
        while heap:
            c, eid, fwd = heapq.heappop(heap)
            if c > dist.get((eid, fwd), math.inf):
                continue
            e = g.edges[eid]
            at = e.v if fwd else e.u
            if at == dst:
                goal = (eid, fwd)
                break
            for nid, nfwd in self.out.get(at, ()):
                if (eid, nid, at) in self.banned:
                    continue
                nc = c + self.edge_s[nid] + (self.model.junction_s if self.degree[at] >= 3 else 0.0)
                st = (nid, nfwd)
                if nc < dist.get(st, math.inf):
                    dist[st], prev[st] = nc, (eid, fwd)
                    heapq.heappush(heap, (nc, nid, nfwd))
        if goal is None:
            return None
        path, st = [], goal
        while st is not None:
            path.append(st)
            st = prev[st]
        path.reverse()
        return {"time_s": dist[goal], "dist_m": sum(g.edges[i].length_m for i, _ in path),
                "edges": path}
