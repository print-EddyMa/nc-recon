"""Lidar ground-change plates for the launch film, from the real Swannanoa
rasters (collect/nc_lidar.py cache) and the area's ground_change sidecar.

  assets/lidar/relief.png   2025 bare-earth hillshade, footprints in hairline
  assets/lidar/change.png   the same with dz coloured (scour blue, deposit amber)
                            and the flagged buildings ringed

`python video/launch/lidar_plate.py` (pipeline venv: numpy, rasterio, pyproj, shapely, Pillow).
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "assets", "lidar")
CACHE = os.path.join(ROOT, "pipeline", "data", "cache", "ops", "nc_lidar")
AREA = "swannanoa"
FT_TO_M = 1200.0 / 3937.0
W, H = 1920, 1080


def hillshade(z: np.ndarray, az: float = 315.0, alt: float = 40.0) -> np.ndarray:
    gy, gx = np.gradient(z)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy) * 1.6)
    aspect = np.arctan2(-gx, gy)
    a, al = np.radians(az), np.radians(alt)
    hs = np.sin(al) * np.sin(slope) + np.cos(al) * np.cos(slope) * np.cos(a - aspect)
    return np.clip(hs, 0, 1)


def main() -> None:
    import rasterio
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as stf

    gc = json.load(open(os.path.join(ROOT, "pipeline", "data", "output", "ops", f"{AREA}.ground_change.json")))
    g = gc["grid"]
    key = next(f[:-9] for f in os.listdir(CACHE) if f.endswith("_post.tif")
               and rasterio.open(os.path.join(CACHE, f)).width == g["width"]
               and rasterio.open(os.path.join(CACHE, f)).height == g["height"])
    with rasterio.open(os.path.join(CACHE, f"{key}_post.tif")) as a, rasterio.open(os.path.join(CACHE, f"{key}_base.tif")) as b:
        post = a.read(1).astype("float64") * FT_TO_M
        base = b.read(1).astype("float64")
        tr = a.transform
    dz = post - base - gc["typical_change_m"]
    dz[(post < -1000) | (base < -1000)] = 0
    # 16:9 crop centred on the flagged buildings
    fc = json.load(open(os.path.join(ROOT, "pipeline", "data", "output", "ops", f"{AREA}.geojson")))
    to = Transformer.from_crs(4326, 32617, always_xy=True).transform
    flagged = {f["ncr_id"]: f["kind"] for f in gc["flagged"]}
    polys = {}
    for f in fc["features"]:
        p = f.get("properties") or {}
        if f.get("geometry") and f["geometry"]["type"] in ("Polygon", "MultiPolygon"):
            polys[p["ncr_id"]] = stf(to, shape(f["geometry"]))
    fx = [polys[k].centroid for k in flagged if k in polys]
    cx = float(np.median([p.x for p in fx]))
    cy = float(np.median([p.y for p in fx]))
    hgt, wid = post.shape
    cw = min(wid, int(hgt * 16 / 9))
    ch = int(cw * 9 / 16)
    c0 = int(np.clip((cx - tr.c) / tr.a - cw / 2, 0, wid - cw))
    r0 = int(np.clip((cy - tr.f) / tr.e - ch / 2, 0, hgt - ch))
    sub = (slice(r0, r0 + ch), slice(c0, c0 + cw))
    hs = hillshade(post)[sub]
    d = dz[sub]

    paper = np.array([18, 22, 24], float)
    lit = np.array([142, 148, 146], float)
    rgb = paper + (lit - paper) * (hs[..., None] ** 1.2)
    relief = rgb.copy()
    # dz colour: scour = verdigris-blue, deposit = bronze; alpha ramps 0.25 m .. 1.5 m
    scour = np.array([86, 168, 214], float)
    dep = np.array([224, 150, 64], float)
    amag = np.clip((np.abs(d) - 0.25) / 1.25, 0, 1)[..., None] * 0.92
    col = np.where((d < 0)[..., None], scour, dep)
    change = rgb * (1 - amag) + col * amag

    os.makedirs(OUT, exist_ok=True)

    def draw(arr: np.ndarray, rings: bool) -> Image.Image:
        im = Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).resize((W, H), Image.LANCZOS)
        sx, sy = W / cw, H / ch
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(ov)
        for nid, p in polys.items():
            geoms = getattr(p, "geoms", [p])
            for gpoly in geoms:
                pts = [(((x - tr.c) / tr.a - c0) * sx, ((y - tr.f) / tr.e - r0) * sy) for x, y in gpoly.exterior.coords]
                hot = rings and nid in flagged
                dr.line(pts, fill=(244, 241, 232, 235 if hot else 70), width=4 if hot else 1)
        out = Image.alpha_composite(im.convert("RGBA"), ov)
        return out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=40)).convert("RGB")

    draw(relief, False).save(os.path.join(OUT, "relief.png"))
    draw(change, True).save(os.path.join(OUT, "change.png"))
    json.dump({"area": AREA, "crop_px": [c0, r0, cw, ch], "res_m": g["res_m"], "flagged_in_view": sum(
        1 for k in flagged if k in polys and c0 <= (polys[k].centroid.x - tr.c) / tr.a <= c0 + cw
        and r0 <= (polys[k].centroid.y - tr.f) / tr.e <= r0 + ch)}, open(os.path.join(OUT, "meta.json"), "w"))
    print("lidar plates written", os.listdir(OUT))


if __name__ == "__main__":
    main()
