"""Authoritative building footprints for an AOI, as polygons in the raster CRS.

Primary source: OpenStreetMap via the Overpass API (live, ODbL). Optional
augmentation: Microsoft's GlobalMLBuildingFootprints (per-quadkey, only the tiles
covering the AOI are fetched). Footprints replace a learned localisation model:
they are exact, current, and free of framework baggage.
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


def load_for_area(pre_path: str, cache_dir: str, area: str):
    """Convenience: OSM footprints clipped to the raster footprint, in raster CRS."""
    with rasterio.open(pre_path) as ds:
        dst_crs = ds.crs
        rb = box(*ds.bounds)
    bounds = aoi_bounds_lonlat(pre_path)
    cache = os.path.join(cache_dir, f"{area}_osm.json")
    polys_ll = fetch_osm_buildings(bounds, cache_path=cache)
    polys = [p for p in to_raster_crs(polys_ll, dst_crs) if p.intersects(rb)]
    polys = [p.intersection(rb) for p in polys]
    polys = [p for p in polys if p.geom_type == "Polygon" and p.area >= 8.0]
    print(f"[footprints] {area}: {len(polys)} OSM building polygons in AOI")
    return polys, dst_crs
