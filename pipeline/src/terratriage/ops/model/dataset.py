"""Chip pairs around labelled buildings, from any pre/post raster pair.

Labels: CAL FIRE DINS inspection points (only damage level, structure type,
incident name and start date are requested; the layer's addresses, parcel
numbers and values are not). Each chip is CHIP_M metres square around the
point, resampled to CHIP_PX pixels from whatever resolution the rasters have,
so training mosaics (0.5 m) and assessment imagery (0.3 m) read the same way.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np

from ..collect.base import DiskCache, http_json
from . import LEVELS

DINS = ("https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/"
        "POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0/query")
DINS_LEVEL = {"no damage": "no_damage", "affected": "affected", "minor": "minor", "major": "major",
              "destroyed": "destroyed"}
CHIP_M, CHIP_PX = 48.0, 96
BLOCK_M = 300.0           # spatial split unit: chips in one block stay together


def dins_points(bbox, incident: str) -> list[dict[str, Any]]:
    w, s, e, n = bbox
    cache = DiskCache("model_dins")
    key = f"{incident}_" + "_".join(f"{v:.4f}" for v in bbox).replace("-", "m").replace(".", "p")
    hit = cache.get(key, 30 * 86400)
    if hit is not None:
        return hit
    out, off = [], 0
    while True:
        d = http_json(DINS, params={
            "where": f"INCIDENTNAME='{incident}'", "outFields": "OBJECTID,DAMAGE,STRUCTURETYPE",
            "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outSR": 4326, "returnGeometry": "true", "f": "json",
            "resultOffset": off, "resultRecordCount": 2000}, timeout=90)
        feats = d.get("features") or []
        for f in feats:
            a, g = f.get("attributes") or {}, f.get("geometry") or {}
            dmg = str(a.get("DAMAGE") or "").lower()
            lvl = next((v for k, v in DINS_LEVEL.items() if dmg.startswith(k)), None)
            if lvl is None or "x" not in g:
                continue      # Inaccessible: no level
            out.append({"id": f"dins/{a['OBJECTID']}", "lon": g["x"], "lat": g["y"], "level": lvl,
                        "structure_type": a.get("STRUCTURETYPE")})
        if len(feats) < 2000:
            break
        off += 2000
    cache.put(key, out)
    return out


def read_chips(pre_path: str, post_path: str, points: list[dict[str, Any]], *,
               chip_m: float = CHIP_M, px: int = CHIP_PX, max_nodata: float = 0.2):
    """(pre, post, kept_points): uint8 arrays (N, 3, px, px)."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds

    from ..geodesy import transformer

    pres, posts, kept = [], [], []
    with rasterio.open(pre_path) as a, rasterio.open(post_path) as b:
        tr = transformer("storage", a.crs.to_epsg()).transform
        for p in points:
            x, y = tr(p["lon"], p["lat"])
            h = chip_m / 2
            chips = []
            for ds in (a, b):
                win = from_bounds(x - h, y - h, x + h, y + h, ds.transform)
                arr = ds.read([1, 2, 3], window=win, out_shape=(3, px, px), boundless=True, fill_value=0,
                              resampling=Resampling.bilinear)
                chips.append(arr)
            nod = max(float((c.max(axis=0) == 0).mean()) for c in chips)
            if nod > max_nodata:
                continue
            pres.append(chips[0])
            posts.append(chips[1])
            kept.append(p)
    if not kept:
        return np.zeros((0, 3, px, px), "uint8"), np.zeros((0, 3, px, px), "uint8"), []
    return np.stack(pres), np.stack(posts), kept


def block_of(lon: float, lat: float) -> str:
    kx = 111320 * math.cos(math.radians(lat))
    return f"{int(lon * kx // BLOCK_M)}_{int(lat * 110540 // BLOCK_M)}"


def is_val(lon: float, lat: float, k: int = 5) -> bool:
    """One block in k goes to validation (deterministic, spatial)."""
    return int(hashlib.sha1(block_of(lon, lat).encode()).hexdigest(), 16) % k == 0


def labels(points: list[dict[str, Any]]) -> np.ndarray:
    return np.array([LEVELS.index(p["level"]) for p in points], dtype="int64")
