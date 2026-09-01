"""Authoritative building footprints for an AOI, as polygons in the raster CRS.

Sources:
  osm        OpenStreetMap via the Overpass API (live, ODbL). Default, works
             anywhere.
  nc_onemap  A statewide NC building-footprint ArcGIS FeatureServer, set via
             TERRATRIAGE_NC_FOOTPRINTS_URL (e.g. an NC OneMap / NCDOT layer).
             Falls back to OSM if unset or unreachable.
  auto       nc_onemap when the AOI centre is in North Carolina, else osm.

Footprints replace a learned localisation model: they are exact, current, and
free of framework baggage.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

import rasterio
from pyproj import Transformer
from shapely.geometry import Polygon, box, shape
from shapely.ops import transform as shapely_transform

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# NC bbox [w, s, e, n], keep in sync with lib/nc.ts and server.ALLOWED_BBOX
NC_BBOX = (-84.55, 33.75, -75.4, 36.7)
NC_FOOTPRINTS_URL = os.environ.get("TERRATRIAGE_NC_FOOTPRINTS_URL", "").strip()

# a polygon under this many m^2 is classified off a handful of pixels; one over
# the max, in the small-town AOIs this tool assesses, is almost always bad OSM
# data (a rail yard, a whole block, a parking lot tagged `building`)
MIN_BUILDING_AREA = float(os.environ.get("TERRATRIAGE_MIN_BUILDING_AREA", "8"))
MAX_BUILDING_AREA = float(os.environ.get("TERRATRIAGE_MAX_BUILDING_AREA", "15000"))


def _in_nc(lon: float, lat: float) -> bool:
    w, s, e, n = NC_BBOX
    return w <= lon <= e and s <= lat <= n


def fetch_arcgis_buildings(bounds_lonlat, service_url: str, page: int = 2000):
    """Building polygons (lon/lat) from an ArcGIS FeatureServer/MapServer layer.

    `service_url` points at a layer, e.g.
      https://host/arcgis/rest/services/<name>/FeatureServer/0
    """
    w, s, e, n = bounds_lonlat
    polys: list[Polygon] = []
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "geometry": f"{w},{s},{e},{n}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "outSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "returnGeometry": "true",
            "f": "geojson",
            "resultOffset": str(offset),
            "resultRecordCount": str(page),
        }
        url = service_url.rstrip("/") + "/query?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "TerraTriage/1.2"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            fc = json.loads(resp.read())
        feats = fc.get("features", [])
        for f in feats:
            geom = f.get("geometry")
            if not geom:
                continue
            try:
                g = shape(geom)
            except Exception:  # noqa: BLE001
                continue
            if g.geom_type == "Polygon" and g.is_valid and g.area > 0:
                polys.append(g)
            elif g.geom_type == "MultiPolygon":
                polys.extend(p for p in g.geoms if p.is_valid and p.area > 0)
        # advance by what we actually got — servers often cap the page below the
        # requested size. Stop on an empty page, or when the server says there is
        # no more, or at the safety valve.
        if not feats:
            break
        offset += len(feats)
        if not fc.get("exceededTransferLimit", False) and len(feats) < page:
            break
        if offset > 300_000:
            break
    return polys


def aoi_bounds_lonlat(raster_path: str) -> tuple[float, float, float, float]:
    with rasterio.open(raster_path) as ds:
        tr = Transformer.from_crs(ds.crs, 4326, always_xy=True)
        l, b = tr.transform(ds.bounds.left, ds.bounds.bottom)
        r, t = tr.transform(ds.bounds.right, ds.bounds.top)
    return (min(l, r), min(b, t), max(l, r), max(t, b))


def _overpass_query(s: float, w: float, n: float, e: float) -> str:
    return (
        "[out:json][timeout:120];"
        f'(way["building"]({s},{w},{n},{e});'
        f' relation["building"]({s},{w},{n},{e}););'
        "out geom;"
    )


def fetch_osm_buildings(bounds_lonlat, cache_path: str | None = None, retries: int = 3):
    """Return a list of shapely polygons (lon/lat) for buildings in the bbox."""
    if cache_path and os.path.exists(cache_path):
        with open(cache_path) as fh:
            data = json.load(fh)
    else:
        w, s, e, n = bounds_lonlat
        q = _overpass_query(s, w, n, e)
        data = None
        for attempt in range(retries):
            ep = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
            try:
                req = urllib.request.Request(
                    ep, data=urllib.parse.urlencode({"data": q}).encode(),
                    headers={"User-Agent": "TerraTriage/1.0 (disaster damage demo)"},
                )
                with urllib.request.urlopen(req, timeout=150) as resp:
                    data = json.loads(resp.read())
                break
            except Exception as ex:  # noqa: BLE001
                print(f"[footprints] Overpass {ep} failed ({ex}); retrying...")
                time.sleep(3 + attempt * 5)
        if data is None:
            raise RuntimeError("Overpass API unreachable after retries")
        if cache_path:
            os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
            with open(cache_path, "w") as fh:
                json.dump(data, fh)

    polys: list[Polygon] = []
    for el in data.get("elements", []):
        if el["type"] == "way" and "geometry" in el:
            ring = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if len(ring) >= 4:
                p = Polygon(ring)
                if p.is_valid and p.area > 0:
                    polys.append(p)
        elif el["type"] == "relation":
            for m in el.get("members", []):
                if m.get("role") == "outer" and "geometry" in m:
                    ring = [(p["lon"], p["lat"]) for p in m["geometry"]]
                    if len(ring) >= 4:
                        p = Polygon(ring)
                        if p.is_valid and p.area > 0:
                            polys.append(p)
    return polys


def to_raster_crs(polys_lonlat, dst_crs):
    fwd = Transformer.from_crs(4326, dst_crs, always_xy=True).transform
    return [shapely_transform(fwd, p) for p in polys_lonlat]


def load_for_area(pre_path: str, cache_dir: str, area: str, source: str = "osm"):
    """Footprints for an AOI, clipped to the raster footprint, in raster CRS.

    Returns (polys, dst_crs, source_used). `source_used` is what actually
    produced the polygons ("osm" or "nc_onemap") so the contract can record it.
    """
    with rasterio.open(pre_path) as ds:
        dst_crs = ds.crs
        rb = box(*ds.bounds)
    bounds = aoi_bounds_lonlat(pre_path)
    cx, cy = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2

    resolved = source
    if source == "auto":
        resolved = "nc_onemap" if _in_nc(cx, cy) else "osm"

    polys_ll: list[Polygon] = []
    source_used = "osm"
    if resolved == "nc_onemap" and NC_FOOTPRINTS_URL:
        try:
            polys_ll = fetch_arcgis_buildings(bounds, NC_FOOTPRINTS_URL)
            source_used = "nc_onemap"
            print(f"[footprints] {area}: {len(polys_ll)} NC OneMap polygons")
        except Exception as ex:  # noqa: BLE001
            print(f"[footprints] NC OneMap fetch failed ({ex}); falling back to OSM")
            polys_ll = []
    elif resolved == "nc_onemap":
        print("[footprints] source=nc_onemap but TERRATRIAGE_NC_FOOTPRINTS_URL "
              "is unset — using OSM")

    if not polys_ll:
        cache = os.path.join(cache_dir, f"{area}_osm.json")
        polys_ll = fetch_osm_buildings(bounds, cache_path=cache)
        source_used = "osm"

    polys = [p for p in to_raster_crs(polys_ll, dst_crs) if p.intersects(rb)]
    polys = [p.intersection(rb) for p in polys]
    polys = [p for p in polys if p.geom_type == "Polygon"]
    kept = [p for p in polys if MIN_BUILDING_AREA <= p.area <= MAX_BUILDING_AREA]
    dropped = len(polys) - len(kept)
    if dropped:
        print(
            f"[footprints] {area}: dropped {dropped} polygon(s) outside "
            f"{MIN_BUILDING_AREA:.0f}-{MAX_BUILDING_AREA:.0f} m^2 (likely not single buildings)"
        )
    print(f"[footprints] {area}: {len(kept)} building polygons in AOI ({source_used})")
    return kept, dst_crs, source_used


def load_osm_polys(pre_path: str, cache_dir: str, area: str):
    """Just the OSM footprints for an AOI, in the raster CRS — for use as a
    filter over a *separate* set of model-predicted polygons (Phase D1)."""
    polys, dst_crs, _src = load_for_area(pre_path, cache_dir, area, source="osm")
    return polys, dst_crs


def filter_by_osm(pred_polys, osm_polys, min_iou: float = 0.1):
    """Split model-predicted polygons by whether they overlap a real OSM
    building. Returns (kept, dropped) index lists + a per-poly bool.

    Used by the segmentation pipeline, where the model invents its own
    footprints and can mistake terrain / shadow / vegetation for a structure.
    The primary footprints pipeline starts from OSM so every building already
    passes this by construction.
    """
    from shapely.strtree import STRtree

    if not osm_polys:
        return list(range(len(pred_polys))), [], [True] * len(pred_polys)
    tree = STRtree(osm_polys)
    verified = []
    for p in pred_polys:
        ok = False
        for j in tree.query(p):
            o = osm_polys[int(j)]
            inter = p.intersection(o).area
            if inter <= 0:
                continue
            union = p.area + o.area - inter
            if union > 0 and inter / union >= min_iou:
                ok = True
                break
        verified.append(ok)
    kept = [i for i, v in enumerate(verified) if v]
    dropped = [i for i, v in enumerate(verified) if not v]
    return kept, dropped, verified
