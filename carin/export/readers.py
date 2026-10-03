"""Read an exported GeoPackage back into a Graph (the inverse of writers.write_gpkg)."""
from __future__ import annotations

import sqlite3
import struct
from typing import List, Tuple

from .graph import Edge, Graph, Node, Restriction

_DIRECTIONS = {"both": 0, "forward": 1, "reverse": 2, "closed": 3}


def _decode_line(blob: bytes) -> List[Tuple[float, float]]:
    # GeoPackage header (8 bytes: "GP", version, flags, srs id) + little-endian WKB LineString
    n = struct.unpack_from("<I", blob, 8 + 5)[0]
    return [struct.unpack_from("<dd", blob, 8 + 9 + 16 * i) for i in range(n)]


def read_gpkg(path: str) -> Graph:
    db = sqlite3.connect(path)
    g = Graph()
    for fid, blob in db.execute("SELECT fid, geom FROM nodes ORDER BY fid"):
        x, y = struct.unpack_from("<dd", blob, 8 + 5)
        g.nodes.append(Node(fid, x, y))
    query = ("SELECT fid, geom, tile, seg_index, u, v, name, locality, road_class, subtype, form, "
             "oneway, toll, junction, junction_hi, speed_code, built_up, slip_role, length_m, "
             "geom_m FROM edges ORDER BY fid")
    for (fid, blob, tile, idx, u, v, name, loc, rc, st, form, ow, toll, junc, jh, sc, bu, slip,
         ln, gm) in db.execute(query):
        g.edges.append(Edge(fid, tile, idx, u, v, _decode_line(blob), name, loc, rc, st, form,
                            _DIRECTIONS[ow], bool(toll), junc, jh, sc, bool(bu), slip, ln, gm))
    for fe, te, via, flag, kind in db.execute(
            "SELECT from_edge, to_edge, via_node, flag, kind FROM restrictions"):
        g.restrictions.append(Restriction(fe, te, via, flag, kind))
    db.close()
    return g
