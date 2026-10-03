"""Writers for an exported Graph: GeoPackage, CSV and OSM XML (stdlib only).

OSM XML feeds `osrm-extract` directly; for Valhalla convert it first
(`osmium cat graph.osm -o graph.osm.pbf`). The highway mapping from the CARiN road class
is approximate (03-road-network.md §6.7 lists class 0 motorway/trunk, 4-5 residential,
6 pedestrian/service) and meant for validation, not for display.
"""
from __future__ import annotations

import csv
import os
import sqlite3
import struct
from datetime import datetime, timezone
from xml.sax.saxutils import quoteattr

from .cost import CostModel
from .graph import DIR_CLOSED, DIR_FORWARD, DIR_REVERSE, Edge, Graph

GPKG_APP_ID = 0x47504B47
WGS84_WKT = ('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
             'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]')


def highway_tag(e: Edge) -> str:
    c = e.road_class
    base = {0: "trunk", 1: "primary", 2: "secondary", 3: "tertiary", 4: "residential",
            5: "residential"}
    if c == 6:
        return "pedestrian" if e.subtype in (5, 6) else "service"
    if c == 0 and e.form == 0:
        return "motorway"
    if c == 0 and e.form == 3:
        return "motorway_link"
    if e.slip_role or e.form in (1, 2, 8, 9, 10):
        return "motorway_link" if c == 0 else (base.get(c, "unclassified") + "_link"
                                              if c in (1, 2, 3) else "residential")
    return base.get(c, "unclassified")


def _wkb_line(coords) -> bytes:
    return struct.pack("<BII", 1, 2, len(coords)) + b"".join(struct.pack("<dd", x, y) for x, y in coords)


def _wkb_point(x, y) -> bytes:
    return struct.pack("<BIdd", 1, 1, x, y)


def _gpkg_geom(wkb: bytes) -> bytes:
    return b"GP" + bytes([0, 0x01]) + struct.pack("<i", 4326) + wkb


def write_gpkg(g: Graph, path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    db.execute(f"PRAGMA application_id = {GPKG_APP_ID}")
    db.execute("PRAGMA user_version = 10300")
    db.executescript("""
    CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY,
        organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
        definition TEXT NOT NULL, description TEXT);
    CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY, data_type TEXT NOT NULL,
        identifier TEXT UNIQUE, description TEXT DEFAULT '',
        last_change DATETIME NOT NULL, min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
        srs_id INTEGER);
    CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL,
        geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL, z TINYINT NOT NULL,
        m TINYINT NOT NULL, PRIMARY KEY (table_name, column_name));
    CREATE TABLE nodes (fid INTEGER PRIMARY KEY, geom BLOB);
    CREATE TABLE edges (fid INTEGER PRIMARY KEY, geom BLOB, tile INTEGER, seg_index INTEGER,
        u INTEGER, v INTEGER, name TEXT, locality TEXT, road_class INTEGER, subtype INTEGER,
        form INTEGER, oneway TEXT, toll INTEGER, junction INTEGER, junction_hi INTEGER, roundabout INTEGER,
        speed_code INTEGER, speed_kmh INTEGER, built_up INTEGER, slip_role INTEGER,
        length_m REAL, geom_m REAL, car_ok INTEGER, highway TEXT);
    CREATE TABLE restrictions (fid INTEGER PRIMARY KEY, from_edge INTEGER, to_edge INTEGER,
        via_node INTEGER, flag INTEGER, kind TEXT);
    """)
    db.executemany("INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)", [
        ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
        ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
        ("WGS 84", 4326, "EPSG", 4326, WGS84_WKT, None)])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    if g.nodes:
        bx = [(min(n.lon for n in g.nodes), min(n.lat for n in g.nodes),
               max(n.lon for n in g.nodes), max(n.lat for n in g.nodes))][0]
    else:
        bx = (0, 0, 0, 0)
    db.executemany("INSERT INTO gpkg_contents VALUES (?,?,?,?,?,?,?,?,?,?)", [
        ("nodes", "features", "nodes", "", now, *bx, 4326),
        ("edges", "features", "edges", "", now, *bx, 4326),
        ("restrictions", "attributes", "restrictions", "", now, None, None, None, None, None)])
    db.executemany("INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)", [
        ("nodes", "geom", "POINT", 4326, 0, 0), ("edges", "geom", "LINESTRING", 4326, 0, 0)])
    db.executemany("INSERT INTO nodes VALUES (?,?)",
                   ((n.id, _gpkg_geom(_wkb_point(n.lon, n.lat))) for n in g.nodes))
    db.executemany("INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        (e.id, _gpkg_geom(_wkb_line(e.coords)), e.tile, e.index, e.u, e.v, e.name, e.locality,
         e.road_class, e.subtype, e.form, e.oneway, int(e.toll), e.junction, e.junction_hi, int(e.roundabout),
         e.speed_code, e.speed_kmh, int(e.built_up), e.slip_role, e.length_m, e.geom_m,
         int(e.car_ok), highway_tag(e)) for e in g.edges))
    db.executemany("INSERT INTO restrictions VALUES (?,?,?,?,?,?)", (
        (i, r.from_edge, r.to_edge, r.via_node, r.flag, r.kind) for i, r in enumerate(g.restrictions)))
    db.commit()
    db.close()


def write_csv(g: Graph, prefix: str, model: CostModel | None = None) -> None:
    model = model or CostModel()
    with open(prefix + "_nodes.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "lon", "lat"])
        w.writerows((n.id, f"{n.lon:.7f}", f"{n.lat:.7f}") for n in g.nodes)
    with open(prefix + "_edges.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "u", "v", "oneway", "road_class", "speed_kmh", "length_m", "name",
                    "highway", "toll", "roundabout", "car_ok", "model_kmh"])
        w.writerows((e.id, e.u, e.v, e.oneway, e.road_class, e.speed_kmh, f"{e.length_m:.1f}",
                     e.name or "", highway_tag(e), int(e.toll), int(e.roundabout), int(e.car_ok),
                     f"{model.speed_kmh(e):.1f}")
                    for e in g.edges)
    with open(prefix + "_restrictions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["from_edge", "to_edge", "via_node", "flag", "kind"])
        w.writerows((r.from_edge, r.to_edge, r.via_node, r.flag, r.kind) for r in g.restrictions)


def write_osm_xml(g: Graph, path: str, model: CostModel | None = None) -> None:
    """One OSM way per segment, junction nodes shared, turn bans as restriction relations.

    `maxspeed` is the cost model's effective speed (the raw stored speed with the default model).
    """
    model = model or CostModel()
    q = quoteattr
    next_id = len(g.nodes) + 1
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="OpenCarin">\n')
        for n in g.nodes:
            f.write(f'<node id="{n.id + 1}" version="1" lat="{n.lat:.7f}" lon="{n.lon:.7f}"/>\n')
        way_refs = {}
        for e in g.edges:
            refs = [e.u + 1]
            for lon, lat in e.coords[1:-1]:
                f.write(f'<node id="{next_id}" version="1" lat="{lat:.7f}" lon="{lon:.7f}"/>\n')
                refs.append(next_id)
                next_id += 1
            refs.append(e.v + 1)
            way_refs[e.id] = refs
        for e in g.edges:
            f.write(f'<way id="{e.id + 1}" version="1">\n')
            for r in way_refs[e.id]:
                f.write(f'  <nd ref="{r}"/>\n')
            tags = {"highway": highway_tag(e), "maxspeed": str(max(5, round(model.speed_kmh(e))))}
            if e.name:
                tags["name"] = e.name
            if e.direction == DIR_FORWARD:
                tags["oneway"] = "yes"
            elif e.direction == DIR_REVERSE:
                tags["oneway"] = "-1"
            elif e.direction == DIR_CLOSED:
                tags["access"] = "no"
            if e.roundabout:
                tags["junction"] = "roundabout"
            if e.toll:
                tags["toll"] = "yes"
            if not e.car_ok and e.direction != DIR_CLOSED:
                tags["motor_vehicle"] = "no"
            for k, v in tags.items():
                f.write(f'  <tag k={q(k)} v={q(v)}/>\n')
            f.write("</way>\n")
        rid = 1
        for r in g.restrictions:
            if r.kind == "other":
                continue
            rtype = "no_u_turn" if r.kind == "no_u_turn" else "no_turn"
            f.write(f'<relation id="{rid}" version="1">\n'
                    f'  <member type="way" ref="{r.from_edge + 1}" role="from"/>\n'
                    f'  <member type="node" ref="{r.via_node + 1}" role="via"/>\n'
                    f'  <member type="way" ref="{r.to_edge + 1}" role="to"/>\n'
                    f'  <tag k="type" v="restriction"/>\n  <tag k="restriction" v={q(rtype)}/>\n'
                    "</relation>\n")
            rid += 1
        f.write("</osm>\n")
