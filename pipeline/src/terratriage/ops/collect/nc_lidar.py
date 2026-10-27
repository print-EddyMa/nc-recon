"""Ground elevation change from lidar: NC's 2025 post-Helene QL1 survey
against the USGS 3DEP baseline.

After Helene, North Carolina re-flew quality-level-1 lidar over the hardest
hit counties and NC OneMap serves the bare-earth result as countywide 3 ft
rasters in `Elevation/DEM03` (`<County>_QL1_2025_03ft_CountywideRaster`, feet,
NAVD88, NC State Plane). USGS 3DEP serves the earlier bare-earth surface
(western NC: the 2017 statewide collection, 1 m, metres, NAVD88). Both are
keyless ArcGIS ImageServers, so both are requested on one grid (UTM 17N, 1 m)
and differenced: dz = DEM03 (ft -> m) - 3DEP.

What dz can show: debris and sediment piled around a building (dz > 0),
ground scoured or slid out from under it (dz < 0). What it cannot: anything
about the building itself (bare earth has buildings removed), and anything
built, graded or paved between 2017 and 2025 shows up as change too, which is
why analyze/ground_change.py works on a ring of ground around each footprint
and against the area's own spread.

Checked 2026-10-22: DEM03 keyless (HTTP 200 without a token despite the
`/secure/` path), 2025 rasters for Ashe, Avery, Buncombe, Burke, Haywood,
Henderson, Jackson, McDowell, Mitchell, Rutherford, Watauga, Yancey (Madison
has only its older raster). No licence text (NC OneMap / NC 911 Board).
Flight dates are not published in the service; the county rasters are named
2025 and the collection post-dates the storm. 3DEP: public domain.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from .. import OPS_CACHE
from .base import USER_AGENT, Connector, SchemaError, SourceUnavailable, http_json

DEM03 = "https://services.nconemap.gov/secure/rest/services/Elevation/DEM03/ImageServer"
DEP3 = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"
FT_TO_M = 1200.0 / 3937.0      # US survey foot (NC State Plane rasters)
UTM17N = 32617
RES_M = 1.0
MAX_PX = 16000                 # beyond this the grid coarsens to 2 m
RETRIES = 3
TILE_PX = 2500                 # per-request tile: NC OneMap returns an HTML error page above ~2,500 px
NODATA = -9999.0


def county_raster(county: str) -> tuple[int, str] | None:
    """(objectid, name) of the county's 2025 QL1 raster, or None."""
    c = (county or "").strip().replace(" County", "")
    # the name goes into an ArcGIS where-clause: county names are letters,
    # spaces, dots and hyphens; anything else (quotes, LIKE wildcards) is dropped
    c = re.sub(r"[^A-Za-z .\-]", "", c).strip()
    if not c:
        return None
    d = http_json(f"{DEM03}/query", params={
        "where": f"name like '{c}%' and name like '%2025%'", "outFields": "objectid,name",
        "returnGeometry": "false", "f": "json"}, timeout=30)
    if not isinstance(d, dict) or not isinstance(d.get("features"), list):
        raise SchemaError("DEM03 catalog query: no features array")
    rows = [f.get("attributes") or {} for f in d["features"]]
    rows = [r for r in rows if "QL1" in str(r.get("name")) and "2025" in str(r.get("name"))]
    return (int(rows[0]["objectid"]), str(rows[0]["name"])) if rows else None


def _grid(bbox_utm: tuple[float, float, float, float]) -> tuple[tuple[float, float, float, float], int, int, float]:
    x0, y0, x1, y1 = bbox_utm
    res = RES_M
    while max(x1 - x0, y1 - y0) / res > MAX_PX:
        res *= 2
    w, h = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
    return (x0, y0, x0 + w * res, y0 + h * res), w, h, res


def _fetch_tile(url: str, bbox: tuple[float, float, float, float], w: int, h: int, mosaic: dict | None) -> bytes:
    q = {"bbox": ",".join(f"{v:.2f}" for v in bbox), "bboxSR": UTM17N, "imageSR": UTM17N, "size": f"{w},{h}",
         "format": "tiff", "pixelType": "F32", "noData": NODATA, "noDataInterpretation": "esriNoDataMatchAny",
         "interpolation": "RSP_BilinearInterpolation", "f": "image"}
    if mosaic:
        q["mosaicRule"] = json.dumps(mosaic)
    req = urllib.request.Request(f"{url}/exportImage?{urllib.parse.urlencode(q)}", headers={"User-Agent": USER_AGENT})
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310 - fixed https services
                body = r.read()
            break
        except Exception as ex:  # noqa: BLE001 - 502/504 from the image servers are usually transient
            last = ex
            time.sleep(2.0 * (attempt + 1))
    else:
        raise SourceUnavailable(f"{url.split('/rest/')[0]} exportImage failed after {RETRIES} tries: {last}") from last
    if not body.startswith((b"II*\x00", b"MM\x00*")):
        raise SchemaError(f"{url.split('/rest/')[0]} did not return a GeoTIFF ({body[:80]!r})")
    return body


def _export(url: str, bbox: tuple[float, float, float, float], w: int, h: int, mosaic: dict | None, path: str) -> None:
    """One GeoTIFF for the whole grid, requested in tiles of at most TILE_PX
    (the services cap total pixels per request well below their stated width)."""
    import numpy as np
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    x0, y0, x1, y1 = bbox
    res = (x1 - x0) / w
    arr = np.full((h, w), NODATA, dtype="float32")
    for r0 in range(0, h, TILE_PX):
        for c0 in range(0, w, TILE_PX):
            tw, th = min(TILE_PX, w - c0), min(TILE_PX, h - r0)
            tb = (x0 + c0 * res, y1 - (r0 + th) * res, x0 + (c0 + tw) * res, y1 - r0 * res)
            with MemoryFile(_fetch_tile(url, tb, tw, th, mosaic)) as mf, mf.open() as d:
                tile = d.read(1)
            arr[r0:r0 + th, c0:c0 + tw] = tile[:th, :tw]
    with rasterio.open(path + ".tmp", "w", driver="GTiff", width=w, height=h, count=1, dtype="float32",
                       crs=f"EPSG:{UTM17N}", transform=from_origin(x0, y1, res, res), nodata=NODATA,
                       compress="deflate") as d:
        d.write(arr, 1)
    os.replace(path + ".tmp", path)


def surfaces(county: str, bbox_utm: tuple[float, float, float, float]) -> dict[str, Any]:
    """Fetch (or reuse) the post and baseline surfaces for a UTM 17N box.
    Returns paths, the grid, and provenance. Raises SourceUnavailable when the
    county has no 2025 survey."""
    ras = county_raster(county)
    if ras is None:
        raise SourceUnavailable(f"no 2025 QL1 lidar raster for {county} County in NC OneMap DEM03")
    oid, name = ras
    bbox, w, h, res = _grid(bbox_utm)
    key = hashlib.sha1(json.dumps([oid, [round(v, 1) for v in bbox], w, h]).encode()).hexdigest()[:16]
    d = os.path.join(OPS_CACHE, "nc_lidar")
    os.makedirs(d, exist_ok=True)
    post, base = os.path.join(d, f"{key}_post.tif"), os.path.join(d, f"{key}_base.tif")
    if not os.path.exists(post):
        _export(DEM03, bbox, w, h, {"mosaicMethod": "esriMosaicLockRaster", "lockRasterIds": [oid]}, post)
    if not os.path.exists(base):
        _export(DEP3, bbox, w, h, None, base)
    return {"post": post, "base": base, "bbox_utm": bbox, "width": w, "height": h, "res_m": res, "crs": f"EPSG:{UTM17N}",
            "provenance": {"post": {"service": DEM03, "raster": name, "objectid": oid, "units": "US survey ft, NAVD88"},
                           "base": {"service": DEP3, "units": "m, NAVD88", "note": "best available 3DEP (WNC: 2017)"}}}


def dz(paths: dict[str, Any]):
    """(dz array in metres with NaN for no data, rasterio transform)."""
    import numpy as np
    import rasterio

    with rasterio.open(paths["post"]) as a, rasterio.open(paths["base"]) as b:
        post = a.read(1).astype("float64")
        base = b.read(1).astype("float64")
        tr = a.transform
    bad = (post <= NODATA + 1) | (base <= NODATA + 1) | ~np.isfinite(post) | ~np.isfinite(base)
    out = post * FT_TO_M - base
    out[bad] = np.nan
    return out, tr


class NCLidar(Connector):
    name = "nc_lidar_2025"
    license = "NC OneMap DEM03 (no licence text) / USGS 3DEP (public domain)"
    homepage = DEM03
    stale_after_s = 400 * 86400

    def probe(self):
        if county_raster("Buncombe") is None:
            raise SchemaError("DEM03 no longer lists Buncombe_QL1_2025")
        return None
