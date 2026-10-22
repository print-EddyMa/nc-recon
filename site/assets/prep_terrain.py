"""Bake the website's terrain explorer assets from real, public, keyless data.

Run with the pipeline venv:  pipeline/.venv/bin/python site/assets/prep_terrain.py

Writes site/assets/terrain/:
  dem.png        16-bit grayscale elevation (USGS 3DEP, public domain), metres*10
  post.jpg       NC OneMap post-Helene orthoimagery, spring 2025 (NC Collaboratory)
  pre.jpg        NC OneMap 2020-2023 orthoimagery (NC CGIA, NC 911 Board)
  heat.png       damage density: expected Major + Destroyed per building, smoothed
                 (Gaussian, 70 m) so no single building can be read off the map
  ground.png     lidar ground change (NC 2025 QL1 minus 3DEP 2017), deposit / scour
  layers.json    grid, published response layers (roads, landing-zone candidates,
                 USNG 1 km sectors), rivers (OpenStreetMap), totals, anatomy record
  anatomy_*     the one showcase structure: change (jpg), ground change (png)
Public-safety rule: no per-building geometry, id or address leaves this script
except the single showcase record the site already publishes.
"""
from __future__ import annotations

import io
import json
import math
import os
import sys
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "terrain")
OPS = os.path.join(REPO, "pipeline", "data", "output", "ops")
sys.path.insert(0, os.path.join(REPO, "pipeline", "src"))

AREA = "swannanoa"
SHOWCASE = "e874056f"
# UTM 17N window: the Swannanoa valley, 7.2 x 5.0 km around the assessed town
X0, X1, Y0, Y1 = 369_500.0, 376_700.0, 3_937_700.0, 3_942_700.0
DEM_W, DEM_H = 432, 300          # ~16.7 m
IMG_W, IMG_H = 2048, 1422        # ~3.5 m
HEAT_W, HEAT_H = 720, 500        # 10 m
UA = {"User-Agent": "Groma/2.0 (website asset build)"}
NCO = "https://services.nconemap.gov/secure/rest/services/Imagery"
DEP3 = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer"


def get(url: str, params: dict, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed public services
        return r.read()


def export(url: str, w: int, h: int, fmt: str, **extra) -> bytes:
    return get(f"{url}/exportImage", {"bbox": f"{X0},{Y0},{X1},{Y1}", "bboxSR": 32617, "imageSR": 32617,
                                      "size": f"{w},{h}", "format": fmt, "f": "image", **extra})


def utm(lon: float, lat: float):
    from pyproj import Transformer

    if not hasattr(utm, "t"):
        utm.t = Transformer.from_crs(4326, 32617, always_xy=True)
    return utm.t.transform(lon, lat)


def ll(x: float, y: float) -> list[float]:
    from pyproj import Transformer

    if not hasattr(ll, "t"):
        ll.t = Transformer.from_crs(32617, 4326, always_xy=True)
    lon, lat = ll.t.transform(x, y)
    return [round(lon, 6), round(lat, 6)]


def uv(x: float, y: float) -> list[float]:
    """UTM -> 0..1 texture coordinates (u east, v south)."""
    return [round((x - X0) / (X1 - X0), 5), round((Y1 - y) / (Y1 - Y0), 5)]


def dem() -> dict:
    raw = export(DEP3, DEM_W, DEM_H, "tiff", pixelType="F32", noData=-9999,
                 interpolation="RSP_BilinearInterpolation")
    import rasterio
    from rasterio.io import MemoryFile

    with MemoryFile(raw) as mf, mf.open() as d:
        z = d.read(1).astype("float64")
    z[z < -1000] = np.nan
    z = np.where(np.isnan(z), np.nanmin(z), z)
    lo, hi = float(z.min()), float(z.max())
    Image.fromarray(np.round(z * 10).astype(np.uint16)).save(os.path.join(OUT, "dem.png"), optimize=True)
    del rasterio
    return {"min_m": round(lo, 1), "max_m": round(hi, 1), "w": DEM_W, "h": DEM_H}


def ortho(path: str, name: str) -> None:
    raw = export(f"{NCO}/{path}/ImageServer", IMG_W, IMG_H, "jpg", bandIds="0,1,2",
                 interpolation="RSP_BilinearInterpolation", compressionQuality=82)
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.save(os.path.join(OUT, name), "JPEG", quality=78, optimize=True, progressive=True)


def ramp(t: np.ndarray, stops: list[tuple[float, tuple[int, int, int, int]]]) -> np.ndarray:
    out = np.zeros(t.shape + (4,), dtype="float64")
    for c in range(4):
        out[..., c] = np.interp(t, [s for s, _ in stops], [col[c] for _, col in stops])
    return out.astype(np.uint8)


def heat(features: list[dict]) -> dict:
    from scipy.ndimage import gaussian_filter

    g = np.zeros((HEAT_H, HEAT_W))
    total = 0.0
    for f in features:
        p = f["properties"]
        probs = p.get("damage_probs") or {}
        w = (probs.get("major") or 0) + (probs.get("destroyed") or 0)
        if not p.get("centroid") or w <= 0:
            continue
        x, y = utm(*p["centroid"])
        c, r = int((x - X0) / (X1 - X0) * HEAT_W), int((Y1 - y) / (Y1 - Y0) * HEAT_H)
        if 0 <= c < HEAT_W and 0 <= r < HEAT_H:
            g[r, c] += w
            total += w
    px = (X1 - X0) / HEAT_W
    g = gaussian_filter(g, sigma=70 / px)
    t = np.clip(g / np.quantile(g[g > 0], 0.995), 0, 1)
    rgba = ramp(t, [(0.0, (240, 190, 70, 0)), (0.08, (240, 190, 70, 0)), (0.25, (243, 156, 52, 150)),
                    (0.6, (222, 76, 38, 210)), (1.0, (160, 20, 40, 235))])
    Image.fromarray(rgba, "RGBA").save(os.path.join(OUT, "heat.png"), optimize=True)
    return {"expected_major_or_destroyed": round(total, 1), "sigma_m": 70}


def ground(meta: dict) -> dict:
    """Lidar dz resampled onto the heat grid, inside the measured box only."""
    import rasterio
    from rasterio.warp import Resampling, reproject

    from terratriage.ops.collect import nc_lidar

    cache = os.path.join(REPO, "pipeline", "data", "cache", "ops", "nc_lidar")
    pick = None
    for f in os.listdir(cache):
        if f.endswith("_post.tif"):
            with rasterio.open(os.path.join(cache, f)) as d:
                b = d.bounds
            if b.left < 373_000 < b.right and b.bottom < 3_940_300 < b.top:
                pick = f[:-9]
    if not pick:
        raise SystemExit("no cached Swannanoa lidar surfaces; run ground_change for swannanoa first")
    paths = {"post": os.path.join(cache, pick + "_post.tif"), "base": os.path.join(cache, pick + "_base.tif")}
    dz, tr = nc_lidar.dz(paths)
    gc = json.load(open(os.path.join(OPS, f"{AREA}.ground_change.json")))
    typ = gc.get("typical_change_m") or 0.0
    dst = np.full((HEAT_H, HEAT_W), np.nan)
    from rasterio.transform import from_bounds

    reproject(dz - typ, dst, src_transform=tr, src_crs="EPSG:32617",
              dst_transform=from_bounds(X0, Y0, X1, Y1, HEAT_W, HEAT_H), dst_crs="EPSG:32617",
              resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    v = np.nan_to_num(dst, nan=0.0)
    a = np.clip((np.abs(v) - 0.4) / 1.6, 0, 1)
    rgba = np.zeros((HEAT_H, HEAT_W, 4), dtype=np.uint8)
    up, down = v > 0, v < 0
    rgba[up] = (214, 128, 46, 0)
    rgba[down] = (52, 120, 196, 0)
    rgba[..., 3] = (a * 225).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(os.path.join(OUT, "ground.png"), optimize=True)
    return {"typical_m": typ, "deposit_flags": gc["flag_counts"].get("deposit"),
            "scour_flags": gc["flag_counts"].get("scour"), "measured": gc["measured"],
            "box_utm": [round(v_) for v_ in (tr.c, tr.f + tr.e * dz.shape[0], tr.c + tr.a * dz.shape[1], tr.f)],
            "paths": paths}


def response_layers() -> dict:
    lay = json.load(open(os.path.join(OPS, f"{AREA}.response.layers.json")))
    roads, lzs, sectors = [], [], []
    for f in lay["features"]:
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        kind = p.get("layer")
        if kind == "road" and g.get("type") in ("LineString", "MultiLineString"):
            parts = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
            for part in parts:
                roads.append({"s": p.get("status"), "p": [uv(*utm(*c)) for c in part],
                              "ll": [[round(c[0], 6), round(c[1], 6)] for c in part]})
        elif kind == "landing_zone" and g.get("type") == "Point":
            lzs.append({"p": uv(*utm(*g["coordinates"])), "d": p.get("clear_diameter_m"),
                        "ll": [round(g["coordinates"][0], 6), round(g["coordinates"][1], 6)], "usng": p.get("usng"),
                        "fits": p.get("fits"), "slope": p.get("slope_deg")})
        elif kind == "sector" and g.get("type") == "Point":
            # a USNG 1 km cell is the UTM 1000 m square around its centre
            cx, cy = utm(*g["coordinates"])
            x0, y0 = math.floor(cx / 1000) * 1000, math.floor(cy / 1000) * 1000
            sectors.append({"usng": p.get("usng_1km"), "priority": p.get("priority"),
                            "severe": p.get("major_or_destroyed_expected"),
                            "people_severe": p.get("people_in_severe_expected"), "buildings": p.get("buildings"),
                            "p": [uv(x0, y0), uv(x0 + 1000, y0), uv(x0 + 1000, y0 + 1000), uv(x0, y0 + 1000)],
                            "ll": [ll(x0, y0), ll(x0 + 1000, y0), ll(x0 + 1000, y0 + 1000), ll(x0, y0 + 1000)]})
    return {"roads": roads, "lz": lzs, "sectors": sectors}


def rivers() -> list[dict]:
    """Named waterways from OpenStreetMap (ODbL). Optional: [] if Overpass is slow."""
    from pyproj import Transformer

    t = Transformer.from_crs(32617, 4326, always_xy=True)
    w, s = t.transform(X0, Y0)
    e, n = t.transform(X1, Y1)
    q = f'[out:json][timeout:40];way["waterway"~"river|stream"]["name"]({s},{w},{n},{e});out geom;'
    try:
        req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                     data=urllib.parse.urlencode({"data": q}).encode(), headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
            d = json.load(r)
    except Exception as ex:  # noqa: BLE001
        print("rivers skipped:", ex)
        return []
    out = []
    for el in d.get("elements", []):
        pts = [uv(*utm(g["lon"], g["lat"])) for g in el.get("geometry", [])]
        if len(pts) > 1:
            out.append({"name": el.get("tags", {}).get("name"), "river": el["tags"].get("waterway") == "river", "p": pts})
    return out


def anatomy(features: list[dict], gmeta: dict) -> dict:
    chips = json.load(open(os.path.join(REPO, "site", "assets", "chips.json")))[SHOWCASE]
    import base64

    def img(uri):
        return Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGB")

    pre, post = np.asarray(img(chips["pre"]), float), np.asarray(img(chips["post"]), float)
    lum = lambda a: a @ [0.299, 0.587, 0.114]  # noqa: E731
    d = np.abs(lum(post) - lum(pre))
    t = np.clip(d / 90.0, 0, 1)
    Image.fromarray(ramp(t, [(0, (20, 28, 34, 255)), (0.35, (60, 96, 120, 255)), (0.7, (236, 160, 60, 255)),
                             (1, (250, 236, 200, 255))])[..., :3]).save(os.path.join(OUT, "anatomy_change.jpg"),
                                                                            quality=80)
    f = next(f for f in features if f["properties"]["ncr_id"].startswith(SHOWCASE))
    p = f["properties"]
    # ground change around the showcase building, same 47.2 m window as the chips
    import rasterio
    from rasterio.warp import Resampling, reproject
    from rasterio.transform import from_bounds

    from terratriage.ops.collect import nc_lidar

    dz, tr = nc_lidar.dz(gmeta["paths"])
    cx, cy = utm(*p["centroid"])
    half = chips["width_m"] / 2
    dst = np.full((96, 96), np.nan)
    reproject(dz - gmeta["typical_m"], dst, src_transform=tr, src_crs="EPSG:32617",
              dst_transform=from_bounds(cx - half, cy - half, cx + half, cy + half, 96, 96), dst_crs="EPSG:32617",
              resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
    v = np.nan_to_num(dst, nan=0.0)
    tt = np.clip((v + 2) / 4, 0, 1)
    rgb = ramp(tt, [(0, (52, 120, 196, 255)), (0.4, (40, 46, 52, 255)), (0.6, (40, 46, 52, 255)),
                    (1, (214, 128, 46, 255))])[..., :3]
    Image.fromarray(rgb).resize((480, 480), Image.NEAREST).save(os.path.join(OUT, "anatomy_ground.png"), optimize=True)
    del rasterio
    ev = {e["id"]: {k: e.get(k) for k in ("available", "weight", "likelihood", "status", "reasons", "detail",
                                          "unavailable_reason")} for e in p["evidence"]}
    for e in ev.values():
        d_ = e.get("detail") or {}
        e["detail"] = {k: d_[k] for k in ("z", "score", "xbd_label", "tarp_frac_new") if k in d_}
    sarcop = json.load(open(os.path.join(OPS, f"{AREA}.sarcop_reference.json")))
    sar = next((r for r in sarcop["pairs"] if r["ncr_id"].startswith(SHOWCASE)), None)
    return {"usng": p["usng_10m"], "probs": p["damage_probs"], "level": p["damage_level"],
            "needs_review": p["needs_review"], "evidence": ev, "dz_ring_max_m": round(float(np.nanmax(np.abs(v))), 2),
            "field": sar and {"level": sar["sar"], "program_type": sar["program_type"]}, "uv": uv(cx, cy),
            "width_m": chips["width_m"]}


def poster() -> None:
    """Still frame for no-WebGL and reduced-motion viewers, and the elevation as raw
    little-endian uint16 decimetres (a PNG decoded through canvas loses 16-bit)."""
    from scipy.ndimage import zoom

    z = np.asarray(Image.open(os.path.join(OUT, "dem.png")), dtype="float64") / 10.0
    z.astype("<f4")
    np.round(z * 10).astype("<u2").tofile(os.path.join(OUT, "dem.u16"))
    zz = zoom(z, (IMG_H / z.shape[0], IMG_W / z.shape[1]), order=1)
    gy, gx = np.gradient(zz, (Y1 - Y0) / IMG_H, (X1 - X0) / IMG_W)
    az, alt = math.radians(315), math.radians(45)
    slope = np.arctan(np.hypot(gx, gy) * 1.6)
    aspect = np.arctan2(-gx, gy)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    shade = np.clip(0.55 + 0.6 * (shade - shade.mean()), 0.25, 1.25)
    base = np.asarray(Image.open(os.path.join(OUT, "post.jpg")).convert("RGB"), dtype="float64")
    img = np.clip(base * shade[..., None], 0, 255).astype(np.uint8)
    out = Image.fromarray(img).convert("RGBA")
    out = Image.alpha_composite(out, Image.open(os.path.join(OUT, "heat.png")).resize(out.size))
    out.convert("RGB").resize((1600, 1111)).save(os.path.join(OUT, "poster.jpg"), quality=76, optimize=True,
                                                 progressive=True)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    fc = json.load(open(os.path.join(OPS, f"{AREA}.geojson")))
    feats = fc["features"]
    meta = {"area": AREA, "utm_zone": 17, "bbox_utm": [X0, Y0, X1, Y1],
            "size_m": [X1 - X0, Y1 - Y0], "counts": fc["properties"].get("counts"),
            "expected": fc["properties"].get("expected_counts"), "structures": len(feats),
            "aoi_uv": None}
    xs = [utm(*f["properties"]["centroid"]) for f in feats]
    meta["aoi_uv"] = [uv(min(x for x, _ in xs), max(y for _, y in xs)), uv(max(x for x, _ in xs), min(y for _, y in xs))]
    print("dem", meta.setdefault("dem", dem()))
    ortho("Orthoimagery_Helene_2025", "post.jpg")
    ortho("Orthoimagery_2020_2023_4band_analysis", "pre.jpg")
    meta["heat"] = heat(feats)
    g = ground(meta)
    meta["ground"] = {k: v for k, v in g.items() if k != "paths"}
    meta["ground"]["box_uv"] = [uv(g["box_utm"][0], g["box_utm"][3]), uv(g["box_utm"][2], g["box_utm"][1])]
    meta.update(response_layers())
    meta["rivers"] = rivers()
    meta["anatomy"] = anatomy(feats, g)
    resp = json.load(open(os.path.join(OPS, f"{AREA}.response.json")))
    s = resp.get("summary") or {}
    meta["response_summary"] = {k: s.get(k) for k in ("cut_off", "landing_zone_candidates", "debris_cy",
                                                       "building_loss_usd", "coverage", "major_or_destroyed_expected")}
    poster()
    with open(os.path.join(OUT, "layers.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, separators=(",", ":"))
    for f in sorted(os.listdir(OUT)):
        print(f"{os.path.getsize(os.path.join(OUT, f)) // 1024:6d} KB  {f}")


if __name__ == "__main__":
    main()
