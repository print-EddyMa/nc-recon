"""Shared helpers: read a pre/post chip for one Old Fort structure, with the
outline's pixel coordinates (aligned and as-delivered)."""
import glob, io, json, base64, sys
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from shapely.geometry import shape
from shapely.ops import transform as st
from shapely.affinity import translate
from PIL import Image
sys.path.insert(0, "src")
from terratriage.ops.geodesy import transformer

AREA = "old_fort"
FC = json.load(open(f"data/output/ops/{AREA}.geojson"))
PATH = {"pre": sorted(glob.glob(f"data/raw/{AREA}/pre_*.tif"))[0], "post": sorted(glob.glob(f"data/raw/{AREA}/post_*.tif"))[0]}

def chip(feat, kind, size=200, pad_m=9.0):
    p = feat["properties"]
    al = ((p.get("measurements") or {}).get("alignment") or {}).get(kind) or {}
    with rasterio.open(PATH[kind]) as ds:
        raw = st(transformer("storage", ds.crs.to_wkt()).transform, shape(feat["geometry"]))
        g = translate(raw, al.get("dx_m", 0.0), al.get("dy_m", 0.0))
        minx, miny, maxx, maxy = g.bounds
        half = max(maxx - minx, maxy - miny) / 2 + pad_m
        cx, cy = g.centroid.x, g.centroid.y
        win = from_bounds(cx - half, cy - half, cx + half, cy + half, ds.transform)
        arr = ds.read(indexes=[1, 2, 3], window=win, boundless=True, fill_value=0, out_shape=(3, size, size))
    img = Image.fromarray(np.transpose(arr, (1, 2, 0)).astype("uint8"))
    def ring(poly):
        return [[round((x - (cx - half)) / (2 * half), 4), round(((cy + half) - y) / (2 * half), 4)] for x, y in poly.exterior.coords]
    return img, ring(g), ring(raw), round(2 * half, 1)

def b64(img, q=74):
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
