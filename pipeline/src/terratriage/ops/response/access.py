"""Road access after the event: what is cut off, who is inside, how far to care.

The road network comes from OpenStreetMap. Each segment is marked:

  blocked    evidence the road is gone or buried: a mapped landslide of this
             storm on the road (NCGS inventory), or a reported closure
  debris     a road beside a building called Destroyed (debris likely)
  bridge     a bridge in an event with flooding (Helene took out hundreds):
             unconfirmed until inspected
  open       no evidence either way

Three scenarios: known blocks only; plus debris; plus every bridge (the worst
case a planner should prepare for). For each,
buildings whose road node cannot reach the edge of the analysis box are
isolated; their occupants are counted from the assessment (USACE NSI night
population where matched). Travel time to the nearest hospital uses typical
speeds per road class, on the network as it stands in each scenario.

Planning estimates from open data: confirm closures with the DOT and roads
crews before routing anyone.
"""
from __future__ import annotations

import heapq
import math
from typing import Any

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from ..collect import osm
from ..geodesy import usng
from . import AreaRun, local_xy, occupants, pad_bbox

SPEED_KMH = {"motorway": 90, "trunk": 80, "primary": 70, "secondary": 60, "tertiary": 50,
             "unclassified": 40, "residential": 35, "living_street": 15, "service": 15, "track": 10}
EXIT_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential"}
SNAP_M = 250.0            # a building further than this from any road is "no road access mapped"
DEBRIS_M = 20.0           # road within this of a Destroyed building: debris likely
OUTSIDE_KMH = 50.0        # beyond the analysis box: straight line to the hospital at this speed,
OUTSIDE_DETOUR = 1.4      # times a road-detour factor


def _speed(hw: str | None) -> float:
    base = (hw or "").replace("_link", "")
    return SPEED_KMH.get(base, 30)


class RoadGraph:
    def __init__(self, ways: list[dict[str, Any]], xy):
        self.xy = xy
        self.node_ix: dict[tuple[float, float], int] = {}
        self.nodes_ll: list[tuple[float, float]] = []
        self.edges: list[dict[str, Any]] = []        # u, v, way index, metres, minutes, status
        self.ways = ways
        for wi, w in enumerate(ways):
            pts = [self._node(c) for c in w["coords"]]
            for a, b in zip(pts, pts[1:]):
                if a == b:
                    continue
                (x0, y0), (x1, y1) = (xy(*self.nodes_ll[a]), xy(*self.nodes_ll[b]))
                m = math.hypot(x1 - x0, y1 - y0)
                self.edges.append({"u": a, "v": b, "way": wi, "m": m,
                                   "min": m / 1000 / _speed(w["highway"]) * 60, "status": "open", "why": []})
        self.nodes_xy = np.array([xy(*p) for p in self.nodes_ll]) if self.nodes_ll else np.zeros((0, 2))
        self.tree = cKDTree(self.nodes_xy) if len(self.nodes_xy) else None

    def _node(self, c) -> int:
        k = (round(c[0], 7), round(c[1], 7))
        if k not in self.node_ix:
            self.node_ix[k] = len(self.nodes_ll)
            self.nodes_ll.append(k)
        return self.node_ix[k]

    def segment_geoms(self) -> list[LineString]:
        return [LineString([self.nodes_xy[e["u"]], self.nodes_xy[e["v"]]]) for e in self.edges]

    def adjacency(self, exclude: set[str]) -> list[list[tuple[int, float]]]:
        adj: list[list[tuple[int, float]]] = [[] for _ in self.nodes_ll]
        for e in self.edges:
            if e["status"] in exclude:
                continue
            adj[e["u"]].append((e["v"], e["min"]))
            adj[e["v"]].append((e["u"], e["min"]))
        return adj

    def snap(self, lon: float, lat: float) -> tuple[int | None, float]:
        if self.tree is None:
            return None, math.inf
        d, i = self.tree.query(self.xy(lon, lat))
        return (int(i), float(d)) if d <= SNAP_M else (None, float(d))


def dijkstra(adj, sources: list[int] | dict[int, float]) -> np.ndarray:
    """Multi-source shortest times; `sources` may carry a starting time each."""
    dist = np.full(len(adj), np.inf)
    h = []
    init = sources if isinstance(sources, dict) else {s: 0.0 for s in sources}
    for s, t0 in init.items():
        if t0 < dist[s]:
            dist[s] = t0
            h.append((t0, s))
    heapq.heapify(h)
    while h:
        d, u = heapq.heappop(h)
        if d > dist[u]:
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(h, (nd, v))
    return dist


def _exit_nodes(g: RoadGraph, box, edge_m: float = 200.0) -> list[int]:
    """Nodes of through roads near the analysis box edge: the way out."""
    w, s, e, n = box
    xy = g.xy
    x0, y0 = xy(w, s)
    x1, y1 = xy(e, n)
    keep = set()
    for ed in g.edges:
        if (g.ways[ed["way"]]["highway"] or "").replace("_link", "") not in EXIT_CLASSES:
            continue
        for k in (ed["u"], ed["v"]):
            x, y = g.nodes_xy[k]
            if min(x - x0, x1 - x, y - y0, y1 - y) <= edge_m:
                keep.add(k)
    return sorted(keep)


def mark(g: RoadGraph, blocks: list[tuple[Any, str]], flood_event: bool,
         destroyed_xy: list[tuple[float, float]]) -> dict[str, int]:
    """Set each segment's status from the evidence. `blocks` are (shapely
    geometry in local metres, reason) pairs."""
    segs = g.segment_geoms()
    tree = STRtree(segs) if segs else None
    counts = {"blocked": 0, "debris": 0, "bridge": 0}
    if tree is not None:
        for geom, why in blocks:
            for i in tree.query(geom):
                if segs[int(i)].intersects(geom):
                    e = g.edges[int(i)]
                    e["status"] = "blocked"
                    if why not in e["why"]:
                        e["why"].append(why)
        if destroyed_xy:
            pts = [Point(p).buffer(DEBRIS_M) for p in destroyed_xy]
            for p in pts:
                for i in tree.query(p):
                    e = g.edges[int(i)]
                    if e["status"] == "open" and segs[int(i)].intersects(p):
                        e["status"] = "debris"
                        e["why"].append("beside a building called Destroyed (debris likely)")
    if flood_event:
        for e in g.edges:
            if e["status"] == "open" and g.ways[e["way"]]["bridge"]:
                e["status"] = "bridge"
                e["why"].append("bridge in a flood event (inspect before use)")
    for e in g.edges:
        if e["status"] in counts:
            counts[e["status"]] += 1
    return counts


def analyse(ar: AreaRun, *, pad_km: float = 6.0, hospital_km: float = 40.0,
            landslide_polys_ll: list | None = None, closures_ll: list | None = None,
            resources: list[dict] | None = None, points: list[dict] | None = None) -> dict[str, Any]:
    box = pad_bbox(ar.bbox, pad_km)
    lon0, lat0 = ar.center
    xy = local_xy(lon0, lat0)
    ways = osm.roads(box)
    g = RoadGraph(ways, xy)

    from shapely.ops import transform as st

    blocks: list[tuple[Any, str]] = []
    for p in landslide_polys_ll or []:
        blocks.append((st(xy, p).buffer(3.0), "mapped landslide of this storm on the road"))
    for c in closures_ll or []:
        blocks.append((st(xy, c["geom"]).buffer(10.0), f"reported closure: {c.get('why', 'closed')}"))
    destroyed = [xy(*f["properties"]["centroid"]) for f in ar.features
                 if (f.get("properties") or {}).get("damage_level") == "destroyed"]
    flood_event = any(h in ("riverine_flood", "flash_flood", "coastal_surge") for h in ar.event.hazards)
    counts = mark(g, blocks, flood_event, destroyed)

    exits = _exit_nodes(g, box)
    # hospitals: OSM within a wider box; fall back to the resources passed in
    hosp = [r for r in (resources or []) if r["kind"] == "hospital"]
    try:
        hosp_wide = [r for r in osm.resources(pad_bbox(ar.bbox, hospital_km)) if r["kind"] == "hospital"]
        hosp = hosp_wide or hosp
    except Exception:  # noqa: BLE001 - travel time is optional
        pass

    scen = {"known_blocks": {"blocked"}, "plus_debris": {"blocked", "debris"},
            "worst_case": {"blocked", "debris", "bridge"}}
    snapped = [g.snap(*f["properties"]["centroid"]) for f in ar.features]
    pts = points or []
    pt_snap = [g.snap(p["lon"], p["lat"]) for p in pts]
    per_point: dict[str, dict[str, Any]] = {p["id"]: {} for p in pts}
    out_scen: dict[str, Any] = {}
    per_building: dict[str, dict[str, Any]] = {f["properties"]["ncr_id"]: {} for f in ar.features}
    for name, excl in scen.items():
        adj = g.adjacency(excl)
        to_exit = dijkstra(adj, exits) if exits else np.full(len(adj), np.inf)
        # hospitals inside the box route on the graph; outside it, the trip
        # continues past an exit (time to exit + straight-line at 50 km/h)
        seeds: dict[int, float] = {}
        for h in hosp:
            i, _d = g.snap(h["lon"], h["lat"])
            if i is not None:
                seeds[i] = 0.0
        if hosp:
            for k in exits:
                ex, ey = g.nodes_xy[k]
                t = min(math.hypot(*(np.array(xy(h["lon"], h["lat"])) - (ex, ey))) for h in hosp)
                seeds[k] = min(seeds.get(k, math.inf), t * OUTSIDE_DETOUR / 1000 / OUTSIDE_KMH * 60)
        to_h = dijkstra(adj, seeds) if seeds else np.full(len(adj), np.inf)
        iso_n = iso_people = 0
        iso_severe = 0
        for f, (node, dm) in zip(ar.features, snapped):
            p = f["properties"]
            rec = per_building[p["ncr_id"]]
            if node is None:
                rec[name] = {"access": "no_mapped_road", "road_m": round(dm)}
                continue
            reach = bool(np.isfinite(to_exit[node]))
            t_h = float(to_h[node]) if np.isfinite(to_h[node]) else None
            rec[name] = {"access": "connected" if reach else "isolated",
                         "min_to_exit": None if not reach else round(float(to_exit[node]), 1),
                         "min_to_hospital": None if t_h is None else round(t_h, 1)}
            if not reach:
                iso_n += 1
                iso_people += occupants(p)
                iso_severe += p.get("damage_level") in ("major", "destroyed")
        for p, (node, dm) in zip(pts, pt_snap):
            if node is None:
                per_point[p["id"]][name] = {"access": "no_mapped_road", "road_m": round(dm)}
            else:
                per_point[p["id"]][name] = {
                    "access": "connected" if np.isfinite(to_exit[node]) else "isolated",
                    "min_to_hospital": round(float(to_h[node]), 1) if np.isfinite(to_h[node]) else None}
        out_scen[name] = {"isolated_buildings": iso_n, "isolated_people_est": round(iso_people),
                          "isolated_major_or_destroyed": iso_severe}

    # isolated clusters (worst case): group isolated buildings by road component
    clusters = _clusters(ar, per_building, snapped, g, "worst_case")
    layer = []
    for e in g.edges:
        if e["status"] == "open" and g.ways[e["way"]]["highway"] in ("service", "track"):
            continue  # keep the layer light: driveways only when they matter
        a, b = g.nodes_ll[e["u"]], g.nodes_ll[e["v"]]
        layer.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [list(a), list(b)]},
                      "properties": {"status": e["status"], "why": e["why"], "way": g.ways[e["way"]]["id"],
                                     "highway": g.ways[e["way"]]["highway"], "name": g.ways[e["way"]]["name"]}})
    return {
        "box": [round(v, 5) for v in box],
        "roads": {"ways": len(ways), "segments": len(g.edges), **counts, "exits": len(exits)},
        "hospitals": [{"name": h["name"], "id": h["id"], "lon": h["lon"], "lat": h["lat"]} for h in hosp][:20],
        "scenarios": out_scen,
        "isolated_clusters": clusters,
        "per_building": per_building,
        "per_point": per_point,
        "layer_roads": layer,
        "method": ("OpenStreetMap roads; blocked = mapped landslide of this storm or a reported closure; "
                   "debris = road beside a Destroyed building; bridge = any bridge in a flood event; isolated = no "
                   "path to the edge of a box padded " f"{pad_km:g} km around the area; speeds by road class; "
                   "hospitals beyond the box at a straight line x1.4 at 50 km/h from the exit"),
        "provenance": osm.provenance("roads").to_dict(),
    }


def _clusters(ar: AreaRun, per_building, snapped, g: RoadGraph, scen: str) -> list[dict[str, Any]]:
    adj = g.adjacency({"blocked", "debris", "bridge"})
    comp = np.full(len(adj), -1)
    cid = 0
    groups: dict[int, list[dict]] = {}
    for f, (node, _d) in zip(ar.features, snapped):
        rec = per_building[f["properties"]["ncr_id"]].get(scen) or {}
        if rec.get("access") != "isolated" or node is None:
            continue
        if comp[node] < 0:
            stack = [node]
            comp[node] = cid
            while stack:
                u = stack.pop()
                for v, _w in adj[u]:
                    if comp[v] < 0:
                        comp[v] = cid
                        stack.append(v)
            cid += 1
        groups.setdefault(int(comp[node]), []).append(f["properties"])
    out = []
    for k, ps in groups.items():
        xs = [p["centroid"][0] for p in ps]
        ys = [p["centroid"][1] for p in ps]
        cx, cy = float(np.mean(xs)), float(np.mean(ys))
        out.append({"cluster": k, "buildings": len(ps), "people_est": round(sum(occupants(p) for p in ps)),
                    "major_or_destroyed": sum(p.get("damage_level") in ("major", "destroyed") for p in ps),
                    "center": [round(cx, 6), round(cy, 6)], "usng": usng(cx, cy, 100)})
    return sorted(out, key=lambda c: (-c["people_est"], -c["buildings"]))
