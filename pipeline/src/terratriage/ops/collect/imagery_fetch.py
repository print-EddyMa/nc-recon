"""Build a co-gridded pre/post image pair for any US point (ops mode).

`run.py ops-fetch --area chimney_rock --lon -82.249 --lat 35.432`

Sources:
  pre   nc_2020_2023   NC Orthoimagery Program, leaf-off, 6 in (analysis service)
        naip           USDA NAIP, latest statewide collection, leaf-on, 0.3-0.6 m
                       (every other state; must predate the incident)
  post  nc_helene_2025 NC Collaboratory post-Helene, spring 2025, leaf-off, 6 in
        eri            NOAA ERI Oct 2024 aerials, ~15 cm (mosaicked from tiles)

Both are resampled to one analysis grid: NAD83(2011) UTM (17N west of 78 W),
0.3 m pixels - the GSD band the xView2 CNN was trained on - snapped to a 0.3 m
lattice so repeat fetches are identical. Output mirrors the Maxar path
(`data/raw/<area>/pre_<date>.tif`, `post_<date>.tif`) plus `imagery.json`,
which `process/imagery.py` reads for acquisition metadata.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

import numpy as np
import rasterio
from rasterio.transform import from_origin

from .. import RAW_DIR
from ..geodesy import transformer, utm_for
from ..provenance import utc_now
from . import nc_orthos
from .eri import ERI

RAW = RAW_DIR
RES = 0.3


def grid_for(lon: float, lat: float, half_m: float) -> tuple[int, tuple[float, float, float, float]]:
    epsg = utm_for(lon, lat)
    x, y = transformer("storage", epsg).transform(lon, lat)
    x0 = math.floor((x - half_m) / RES) * RES
    y1 = math.ceil((y + half_m) / RES) * RES
    n = int(round(2 * half_m / RES))
    return epsg, (x0, y1 - n * RES, x0 + n * RES, y1)


def _eri_mosaic(bounds_xy, epsg: int, eri_prefix: str) -> tuple[np.ndarray, dict]:
    from rasterio.vrt import WarpedVRT
    from rasterio.warp import transform_bounds
    from rasterio.enums import Resampling

    x0, y0, x1, y1 = bounds_xy
    w, s, e, n = transform_bounds(epsg, 4326, x0, y0, x1, y1)
    pad = 0.01
    tiles = [t for t in ERI().index(eri_prefix) if w - pad <= t["lon"] <= e + pad and s - pad <= t["lat"] <= n + pad]
    if not tiles:
        raise LookupError("no ERI tiles cover this AOI")
    # most recent flight last so it paints over earlier ones
    tiles.sort(key=lambda t: t["flight"])
    W = int(round((x1 - x0) / RES))
    H = int(round((y1 - y0) / RES))
    out = np.zeros((3, H, W), dtype="uint8")
    tr = from_origin(x0, y1, RES, RES)
    used = []
    env = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
               GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES")
    with rasterio.Env(**env):
        for t in tiles:
            with rasterio.open("/vsicurl/" + t["url"]) as src0:
                tb = src0.bounds
                if tb.right < w or tb.left > e or tb.top < s or tb.bottom > n:
                    continue
                level = _overview_level(src0, RES)
            # read the coarsest internal overview that is still finer than the
            # analysis grid: newer ERI tiles are ~7.5 cm and 1.5 GB each, and
            # warping from full resolution moves ~16x the bytes the grid needs
            with rasterio.open("/vsicurl/" + t["url"], **({} if level is None else {"overview_level": level})) as src:
                with WarpedVRT(src, crs=f"EPSG:{epsg}", transform=tr, width=W, height=H,
                               resampling=Resampling.average) as vrt:
                    arr = vrt.read(indexes=[1, 2, 3])
                    alpha = vrt.read(4) if src.count >= 4 else (arr.max(axis=0) > 0).astype("uint8") * 255
                m = alpha > 0
                if m.any():
                    out[:, m] = arr[:, m]
                    used.append(t)
    if not used:
        raise LookupError("ERI tiles listed but none intersect the AOI")
    dates = sorted({t["flight_date"] for t in used})
    return out, {"flights": sorted({t["flight"] for t in used}), "dates": dates,
                 "tiles": [t["key"] for t in used]}


def _overview_level(src, res_m: float) -> int | None:
    """Index of the coarsest overview whose pixel is no larger than `res_m`
    (None: read full resolution)."""
    px = abs(src.res[0])
    if src.crs and src.crs.is_geographic:
        px *= 111320.0 * math.cos(math.radians((src.bounds.top + src.bounds.bottom) / 2))
    best = None
    for i, f in enumerate(src.overviews(1)):
        if px * f <= res_m * 1.01:
            best = i
    return best


def _span(lo: str, hi: str) -> str:
    return lo if lo == hi else f"{lo}_{hi}"


def _probe_points(bounds_xy, epsg: int) -> list[tuple[float, float]]:
    """Centre + four inset corners, lon/lat, for catalog date lookups."""
    x0, y0, x1, y1 = bounds_xy
    tr = transformer(epsg, "storage")
    fx = [(0.5, 0.5), (0.15, 0.15), (0.85, 0.15), (0.15, 0.85), (0.85, 0.85)]
    return [tr.transform(x0 + a * (x1 - x0), y0 + b * (y1 - y0)) for a, b in fx]


def _write(path: str, arr: np.ndarray, epsg: int, bounds_xy) -> None:
    x0, _, _, y1 = bounds_xy
    prof = {"driver": "GTiff", "height": arr.shape[1], "width": arr.shape[2], "count": 3,
            "dtype": "uint8", "crs": f"EPSG:{epsg}", "transform": from_origin(x0, y1, RES, RES),
            "tiled": True, "blockxsize": 512, "blockysize": 512, "compress": "DEFLATE",
            "predictor": 2, "nodata": None}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(arr[:3])


def fetch_pair(area: str, lon: float, lat: float, *, half_m: float = 800.0,
               pre: str = "nc_2020_2023", post: str = "nc_helene_2025",
               eri_prefix: str = "2024_Hurricane_Helene") -> dict[str, Any]:
    epsg, b = grid_for(lon, lat, half_m)
    d = os.path.join(RAW, area)
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if f.startswith(("pre_", "post_")) and f.endswith(".tif"):
            os.remove(os.path.join(d, f))
    meta: dict[str, Any] = {"area": area, "center": [lon, lat], "grid": {"epsg": epsg, "bounds": b, "res_m": RES},
                            "fetched_utc": utc_now()}
    pre_arr = nc_orthos.export_window(pre, b, epsg, RES)
    if pre_arr.max() == 0:
        raise LookupError(f"{pre} has no imagery at {lon},{lat}")
    spec = nc_orthos.SERVICES[pre]
    probe = _probe_points(b, epsg)
    lo, hi, how = nc_orthos.tile_dates(pre, probe)
    pre_path = os.path.join(d, f"pre_{_span(lo, hi)}.tif")
    _write(pre_path, pre_arr, epsg, b)
    meta["pre"] = {"source": pre, "date": lo if lo == hi else None, "date_min": lo, "date_max": hi,
                   "date_source": how, "date_label": spec["date_label"],
                   "season": spec["season"], "provenance": nc_orthos.provenance(pre).to_dict(), "path": pre_path}

    if post == "eri":
        post_arr, info = _eri_mosaic(b, epsg, eri_prefix)
        plo, phi = info["dates"][0], info["dates"][-1]
        meta["post"] = {"source": "eri", "date": plo if plo == phi else None, "date_min": plo, "date_max": phi,
                        "date_source": "ERI flight ids", "date_label": f"ERI flights {', '.join(info['flights'])}",
                        "season": "transition", "eri": info,
                        "provenance": {"source": "NOAA NGS Emergency Response Imagery",
                                       "source_url": f"https://noaa-eri-pds.s3.amazonaws.com/{eri_prefix}/",
                                       "license": "US Government work (NOAA NGS)", "crs": "EPSG:4326 tiles",
                                       "horizontal_datum": "per NOAA ERI metadata"}}
    else:
        post_arr = nc_orthos.export_window(post, b, epsg, RES)
        s2 = nc_orthos.SERVICES[post]
        plo, phi, how = nc_orthos.tile_dates(post, _probe_points(b, epsg))
        meta["post"] = {"source": post, "date": plo if plo == phi else None, "date_min": plo, "date_max": phi,
                        "date_source": how, "date_label": s2["date_label"], "season": s2["season"],
                        "provenance": nc_orthos.provenance(post).to_dict()}
    if post_arr.max() == 0:
        raise LookupError(f"{post} has no imagery at {lon},{lat}")
    post_path = os.path.join(d, f"post_{_span(plo, phi)}.tif")
    _write(post_path, post_arr, epsg, b)
    meta["post"]["path"] = post_path
    valid = float(((pre_arr.max(axis=0) > 0) & (post_arr.max(axis=0) > 0)).mean())
    meta["valid_overlap_frac"] = round(valid, 3)
    with open(os.path.join(d, "imagery.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    # the demo registry reads meta.json; keep it minimal and truthful
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"event": "ops", "area": area, "name": area.replace("_", " ").title(),
                   "center": [lon, lat], "zoom": 15.2, "pre_date": meta["pre"]["date"],
                   "post_date": _span(plo, phi), "imagery_source": f"{pre} -> {post}"}, fh, indent=2)
    print(f"[ops-fetch] {area}: {pre} -> {post}, grid EPSG:{epsg} {post_arr.shape[2]}x{post_arr.shape[1]} "
          f"@ {RES} m, valid overlap {valid:.0%}")
    return meta


def eri_covers(lon: float, lat: float, eri_prefix: str, radius_deg: float = 0.012) -> bool:
    try:
        return any(abs(t["lon"] - lon) < radius_deg and abs(t["lat"] - lat) < radius_deg
                   for t in ERI().index(eri_prefix))
    except Exception:  # noqa: BLE001
        return False
