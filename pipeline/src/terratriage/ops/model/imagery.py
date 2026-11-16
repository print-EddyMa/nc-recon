"""Co-gridded pre/post mosaics from public-domain imagery, for training boxes.

  pre   NAIP via Microsoft Planetary Computer STAC (all collection years as
        COGs; asset reads are anonymous). The newest collection that ends
        before the incident is used, so "before" is always before.
  post  NOAA ERI tiles for the event, read through their overviews.

Both are warped onto one UTM grid at RES metres (0.5 m: between NAIP's
0.6 m and ERI's ~0.07-0.3 m, and in the band xBD-style models train on).
"""
from __future__ import annotations

import json
import math
import os
import urllib.request
from datetime import date
from typing import Any

import numpy as np

from ..collect.base import USER_AGENT
from ..geodesy import transformer, utm_for

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
RES = 0.5


def grid(bbox_ll, res: float = RES) -> tuple[int, tuple[float, float, float, float], int, int]:
    w, s, e, n = bbox_ll
    epsg = utm_for((w + e) / 2, (s + n) / 2)
    tr = transformer("storage", epsg)
    xs, ys = zip(*[tr.transform(x, y) for x, y in ((w, s), (e, n), (w, n), (e, s))])
    x0, y0 = math.floor(min(xs) / res) * res, math.floor(min(ys) / res) * res
    x1, y1 = math.ceil(max(xs) / res) * res, math.ceil(max(ys) / res) * res
    return epsg, (x0, y0, x1, y1), int(round((x1 - x0) / res)), int(round((y1 - y0) / res))


def naip_items(bbox_ll, before: date) -> list[dict[str, Any]]:
    body = json.dumps({"collections": ["naip"], "bbox": list(bbox_ll),
                       "datetime": f"2010-01-01/{before.isoformat()}", "limit": 200}).encode()
    req = urllib.request.Request(PC_STAC, data=body, headers={"Content-Type": "application/json",
                                                               "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as r:  # noqa: S310
        feats = json.load(r)["features"]
    # newest year first; within the newest year every quarter-quad covering the box
    feats.sort(key=lambda f: f["properties"]["datetime"], reverse=True)
    if not feats:
        return []
    year = feats[0]["properties"]["datetime"][:4]
    return [f for f in feats if f["properties"]["datetime"][:4] == year]


def _overview(url: str, res: float) -> dict:
    """Open option for the coarsest overview still finer than `res`: the ERI
    tiles are ~7 cm, and warping from full resolution reads ~1.5 GB a tile."""
    import rasterio

    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"), rasterio.open("/vsicurl/" + url) as src:
        native = abs(src.res[0])
        if src.crs.is_geographic:
            native *= 111320.0
        best = None
        for i, f in enumerate(src.overviews(1)):
            if native * f <= res:
                best = i
    return {} if best is None else {"OVERVIEW_LEVEL": best}


def _paint(out: np.ndarray, urls: list[str], epsg: int, bounds, res: float, bands=(1, 2, 3)) -> None:
    """Warp each source onto the grid, reading only the window it covers."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import transform_bounds

    x0, _y0, _x1, y1 = bounds
    H, W = out.shape[1:]
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4",
                      GDAL_HTTP_RETRY_DELAY="2"):
        for u in urls:
            with rasterio.open("/vsicurl/" + u, **_overview(u, res)) as src:
                l, b, r, t = transform_bounds(src.crs, f"EPSG:{epsg}", *src.bounds)
                c0 = max(0, int((l - x0) / res))
                c1 = min(W, int(math.ceil((r - x0) / res)))
                r0 = max(0, int((y1 - t) / res))
                r1 = min(H, int(math.ceil((y1 - b) / res)))
                if c1 <= c0 or r1 <= r0:
                    continue
                with WarpedVRT(src, crs=f"EPSG:{epsg}", transform=from_origin(x0 + c0 * res, y1 - r0 * res, res, res),
                               width=c1 - c0, height=r1 - r0, resampling=Resampling.average,
                               src_nodata=0, nodata=0) as vrt:
                    arr = vrt.read(list(bands))
            sub = out[:, r0:r1, c0:c1]
            m = arr.max(axis=0) > 0
            sub[:, m] = arr[:, m]


def build_pair(name: str, bbox_ll, incident: date, eri_prefix: str, out_dir: str) -> dict[str, Any]:
    """Write <out_dir>/<name>/{pre,post}.tif and meta.json; returns meta."""
    import rasterio
    from rasterio.transform import from_origin

    from ..collect.eri import ERI

    epsg, bounds, W, H = grid(bbox_ll)
    d = os.path.join(out_dir, name)
    os.makedirs(d, exist_ok=True)
    items = naip_items(bbox_ll, incident)
    if not items:
        raise LookupError("no NAIP collection before the incident covers this box")
    pre = np.zeros((3, H, W), "uint8")
    _paint(pre, [f["assets"]["image"]["href"] for f in items], epsg, bounds, RES)
    w, s, e, n = bbox_ll
    pad = 0.006
    tiles = [t for t in ERI().index(eri_prefix) if w - pad <= t["lon"] <= e + pad and s - pad <= t["lat"] <= n + pad]
    tiles.sort(key=lambda t: t["flight"])
    post = np.zeros((3, H, W), "uint8")
    _paint(post, [t["url"] for t in tiles], epsg, bounds, RES)
    prof = {"driver": "GTiff", "height": H, "width": W, "count": 3, "dtype": "uint8", "crs": f"EPSG:{epsg}",
            "transform": from_origin(bounds[0], bounds[3], RES, RES), "tiled": True, "blockxsize": 512,
            "blockysize": 512, "compress": "DEFLATE", "predictor": 2}
    for nm, arr in (("pre", pre), ("post", post)):
        with rasterio.open(os.path.join(d, f"{nm}.tif"), "w", **prof) as dst:
            dst.write(arr)
    meta = {"name": name, "bbox": list(bbox_ll), "epsg": epsg, "bounds": bounds, "res_m": RES,
            "incident": incident.isoformat(),
            "pre": {"source": "USDA NAIP via Planetary Computer", "items": [f["id"] for f in items],
                    "dates": sorted({f["properties"]["datetime"][:10] for f in items}),
                    "license": "public domain (USDA FSA)"},
            "post": {"source": "NOAA NGS Emergency Response Imagery", "prefix": eri_prefix,
                     "flights": sorted({t["flight"] for t in tiles}), "tiles": len(tiles),
                     "license": "US Government work (NOAA NGS)"},
            "valid_frac": float(((pre.max(0) > 0) & (post.max(0) > 0)).mean())}
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return meta
