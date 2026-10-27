"""Helicopter landing-zone candidates near cut-off or hard-hit places.

On a 10 m grid around the area:
  terrain    USGS 3DEP elevation (ImageServer, keyless) -> slope
  cover      ESA WorldCover 2021 10 m (COG on AWS, keyless, CC BY 4.0):
             grass, cropland and bare ground are open; shrubland and built-up
             are marginal (a parking lot or a ball field, or a roof)
  buildings  assessed footprints, kept clear by a margin

A candidate is the centre of a circle of open, gentle ground at least the
required diameter across. Candidates are ranked by how close they are to
people cut off by road (response/access.py) and to buildings likely Major or
Destroyed.

These are map candidates for planning a reconnaissance, never approved landing
zones: wires, poles, tree edges, soft ground and debris do not show in 10 m
data. Every one needs eyes on it (a crew or a ground team) before use.
"""
from __future__ import annotations

import math
import urllib.parse
import urllib.request
from typing import Any

import numpy as np
from scipy import ndimage

from ..collect.base import USER_AGENT, SourceUnavailable
from ..geodesy import transformer, usng, utm_for
from . import AreaRun, p_severe, pad_bbox

DEM = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
WORLDCOVER = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
RES = 10.0
OPEN = {30: "grassland", 40: "cropland", 60: "bare ground"}
MARGINAL = {20: "shrubland", 50: "built-up (paved or roofed)"}
# Single-ship landing point: 50 m cleared diameter for a UH-60, 80 m for a
# CH-47; up to 7 degrees of slope every aircraft can land on (Army air assault
# handbook citing FM 3-21.38, pathfinder operations). The aviation unit's own
# standard governs; these are planning defaults.
PARAMS = {"min_diameter_m": 50.0, "ch47_diameter_m": 80.0, "max_slope_deg": 7.0, "building_clear_m": 20.0,
          "max_candidates": 30, "min_separation_m": 300.0}


def _dem(bounds_xy, epsg: int, W: int, H: int) -> np.ndarray:
    from rasterio.io import MemoryFile

    q = {"bbox": ",".join(f"{v:.2f}" for v in bounds_xy), "bboxSR": epsg, "imageSR": epsg,
         "size": f"{W},{H}", "format": "tiff", "pixelType": "F32",
         "interpolation": "RSP_BilinearInterpolation", "f": "image"}
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(DEM + "?" + urllib.parse.urlencode(q), headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310
                data, ctype = r.read(), r.headers.get("Content-Type", "")
            if "tiff" not in ctype:
                raise SourceUnavailable(f"3DEP returned {ctype}")
            with MemoryFile(data) as mf, mf.open() as ds:
                return ds.read(1, out_shape=(H, W)).astype("float32")
        except Exception as ex:  # noqa: BLE001
            last = ex
    raise SourceUnavailable(f"3DEP elevation: {last}")


def _tile(lon: float, lat: float) -> str:
    la = int(math.floor(lat / 3.0) * 3)
    lo = int(math.floor(lon / 3.0) * 3)
    return f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"


def _cover(bounds_xy, epsg: int, W: int, H: int, center_ll) -> np.ndarray:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT

    x0, _y0, _x1, y1 = bounds_xy
    url = "/vsicurl/" + WORLDCOVER.format(tile=_tile(*center_ll))
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"), rasterio.open(url) as src, \
                WarpedVRT(src, crs=f"EPSG:{epsg}", transform=from_origin(x0, y1, RES, RES), width=W, height=H,
                          resampling=Resampling.nearest) as vrt:
            return vrt.read(1)
    except Exception as ex:  # noqa: BLE001
        raise SourceUnavailable(f"ESA WorldCover: {ex}") from ex


def _rasterize_buildings(ar: AreaRun, to_xy, bounds_xy, W: int, H: int) -> np.ndarray:
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from shapely.geometry import shape
    from shapely.ops import transform as st

    x0, _y0, _x1, y1 = bounds_xy
    geoms = [st(to_xy, shape(f["geometry"])) for f in ar.features if f.get("geometry")]
    if not geoms:
        return np.zeros((H, W), bool)
    return rasterize(((g, 1) for g in geoms), out_shape=(H, W), transform=from_origin(x0, y1, RES, RES),
                     fill=0, dtype="uint8").astype(bool)


def candidates(ar: AreaRun, *, pad_km: float = 4.0, targets: list[dict] | None = None,
               params: dict[str, float] | None = None) -> dict[str, Any]:
    """`targets`: places that need air access, each {lon, lat, weight, label}
    (isolated clusters, severe-damage concentrations)."""
    P = {**PARAMS, **(params or {})}
    box = pad_bbox(ar.bbox, pad_km)
    lon0, lat0 = ar.center
    epsg = utm_for(lon0, lat0)
    to_xy = transformer("storage", epsg).transform
    to_ll = transformer(epsg, "storage").transform
    xs, ys = zip(*[to_xy(x, y) for x, y in ((box[0], box[1]), (box[2], box[3]), (box[0], box[3]), (box[2], box[1]))])
    x0, y0 = math.floor(min(xs) / RES) * RES, math.floor(min(ys) / RES) * RES
    x1, y1 = math.ceil(max(xs) / RES) * RES, math.ceil(max(ys) / RES) * RES
    W, H = int((x1 - x0) / RES), int((y1 - y0) / RES)
    bounds = (x0, y0, x1, y1)

    dem = _dem(bounds, epsg, W, H)
    cover = _cover(bounds, epsg, W, H, (lon0, lat0))
    gy, gx = np.gradient(dem, RES)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    bld = _rasterize_buildings(ar, to_xy, bounds, W, H)
    near_bld = ndimage.binary_dilation(bld, iterations=max(1, int(P["building_clear_m"] / RES)))
    open_ = np.isin(cover, list(OPEN)) & (slope <= P["max_slope_deg"]) & ~near_bld
    marg = np.isin(cover, list(MARGINAL)) & (slope <= P["max_slope_deg"]) & ~near_bld
    usable = open_ | marg
    clear = ndimage.distance_transform_edt(usable) * RES          # metres to the nearest unusable cell
    need = P["min_diameter_m"] / 2
    cand = clear >= need
    if not cand.any():
        return {"candidates": [], "params": P, "note": "no open, gentle ground of the required size in the box"}

    # spread candidates out: best clear radius first, then suppress neighbours
    tgt = targets or []
    t_xy = [(to_xy(t["lon"], t["lat"]), t) for t in tgt]
    rr, cc = np.nonzero(cand)
    order = np.argsort(-clear[rr, cc])
    picked: list[dict[str, Any]] = []
    sep = P["min_separation_m"]
    for k in order:
        r, c = int(rr[k]), int(cc[k])
        x, y = x0 + (c + 0.5) * RES, y1 - (r + 0.5) * RES
        if any(math.hypot(x - p["_x"], y - p["_y"]) < sep for p in picked):
            continue
        lon, lat = to_ll(x, y)
        win = (slice(max(0, r - 3), r + 4), slice(max(0, c - 3), c + 4))
        nearest = None
        if t_xy:
            d, t = min(((math.hypot(x - tx, y - ty), t) for (tx, ty), t in t_xy), key=lambda z: z[0])
            nearest = {"label": t.get("label"), "distance_m": round(d), "weight": t.get("weight", 1.0)}
        lc = int(cover[r, c])
        picked.append({
            "_x": x, "_y": y, "lon": round(lon, 6), "lat": round(lat, 6), "usng": usng(lon, lat, 10),
            "clear_diameter_m": round(2 * float(clear[r, c])), "slope_deg": round(float(np.nanmean(slope[win])), 1),
            "elevation_m": round(float(dem[r, c]), 1),
            "cover": OPEN.get(lc) or MARGINAL.get(lc) or str(lc), "marginal": lc in MARGINAL,
            "fits": ["UH-60"] + (["CH-47"] if 2 * float(clear[r, c]) >= P["ch47_diameter_m"] else []),
            "nearest_need": nearest})
        if len(picked) >= 400:
            break

    def score(p):
        s = p["clear_diameter_m"] / P["min_diameter_m"]
        if p["nearest_need"]:
            s += 6.0 * p["nearest_need"]["weight"] / (1 + p["nearest_need"]["distance_m"] / 1000)
        return s - (1.5 if p["marginal"] else 0)

    picked.sort(key=score, reverse=True)
    out = []
    for p in picked[: int(P["max_candidates"])]:
        p.pop("_x"), p.pop("_y")
        p["score"] = round(score(p), 2)
        out.append(p)
    return {
        "candidates": out, "params": P, "grid": {"epsg": epsg, "res_m": RES, "width": W, "height": H},
        "open_fraction": round(float(open_.mean()), 3),
        "sources": [{"source": "USGS 3DEP elevation (ImageServer)", "url": DEM.rsplit("/", 1)[0],
                     "license": "US Government (USGS); public domain"},
                    {"source": "ESA WorldCover 2021 v200 (10 m)", "url": WORLDCOVER.split("/v200")[0],
                     "license": "CC BY 4.0, (c) ESA WorldCover project / Copernicus Sentinel data 2021"}],
        "caveat": "Map candidates for reconnaissance, not approved landing zones: wires, poles, tree edges, "
                  "soft ground and debris are not in 10 m data. Size and slope limits are defaults; use the "
                  "aviation unit's own standard.",
    }


def targets_from(ar: AreaRun, access_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Places needing air access: worst-case isolated clusters, then the
    buildings most likely Major or Destroyed."""
    out = []
    for c in (access_result or {}).get("isolated_clusters", [])[:20]:
        out.append({"lon": c["center"][0], "lat": c["center"][1], "label": f"cut off: {c['people_est']} people",
                    "weight": 1.0 + min(2.0, c["people_est"] / 100)})
    sev = sorted(ar.features, key=lambda f: -p_severe(f["properties"]))[:30]
    for f in sev:
        if p_severe(f["properties"]) >= 0.5:
            c = f["properties"]["centroid"]
            out.append({"lon": c[0], "lat": c[1], "label": "likely Major or Destroyed", "weight": 0.6})
    return out
