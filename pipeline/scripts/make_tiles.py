#!/usr/bin/env python
"""Slice the pre/post Maxar COGs into XYZ PNG tiles for the web map.

    python scripts/make_tiles.py --area old_fort --minzoom 13 --maxzoom 18

Writes  web/public/tiles/<area>/<pre|post>/<z>/<x>/<y>.png  (EPSG:3857, 256 px).
Small AOIs -> a few hundred tiles per layer, committed with the app.
"""
import argparse
import glob
import math
import os

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Override for container deploys where ../web is not on disk; the service then
# serves tiles from here via GET /tiles/...
WEB_TILES = os.environ.get("TERRATRIAGE_TILES_DIR") or os.path.join(
    ROOT, "..", "web", "public", "tiles"
)
R = 6378137.0
ORIGIN = math.pi * R


def deg2num(lon, lat, z):
    n = 2**z
    x = (lon + 180.0) / 360.0 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def tile_bounds_3857(x, y, z):
    n = 2**z
    span = 2 * ORIGIN / n
    minx = -ORIGIN + x * span
    maxy = ORIGIN - y * span
    return minx, maxy - span, minx + span, maxy


def tiles_for(src_path, kind, area, minz, maxz):
    out_root = os.path.join(WEB_TILES, area, kind)
    with rasterio.open(src_path) as src:
        with WarpedVRT(src, crs="EPSG:3857", resampling=Resampling.bilinear) as vrt:
            l, b, r, t = vrt.bounds
            # lon/lat bounds for tile enumeration
            import pyproj

            to_ll = pyproj.Transformer.from_crs(3857, 4326, always_xy=True)
            lon0, lat1 = to_ll.transform(l, t)
            lon1, lat0 = to_ll.transform(r, b)
            written = 0
            for z in range(minz, maxz + 1):
                x0f, y0f = deg2num(lon0, lat1, z)
                x1f, y1f = deg2num(lon1, lat0, z)
                full = rasterio.windows.Window(0, 0, vrt.width, vrt.height)
                for tx in range(int(x0f), int(x1f) + 1):
                    for ty in range(int(y0f), int(y1f) + 1):
                        bx0, by0, bx1, by1 = tile_bounds_3857(tx, ty, z)
                        win = from_bounds(bx0, by0, bx1, by1, vrt.transform)
                        inter = win.intersection(full) if rasterio.windows.intersect(win, full) else None
                        if inter is None or inter.width < 1 or inter.height < 1:
                            continue
                        # sub-pixel box of the intersection within the 256px tile
                        px = 256.0 / win.width
                        py = 256.0 / win.height
                        ox = int(round((inter.col_off - win.col_off) * px))
                        oy = int(round((inter.row_off - win.row_off) * py))
                        ow = max(1, int(round(inter.width * px)))
                        oh = max(1, int(round(inter.height * py)))
                        sub = vrt.read(
                            indexes=[1, 2, 3], window=inter,
                            out_shape=(3, oh, ow), resampling=Resampling.bilinear,
                        )
                        if sub.max() == 0:
                            continue
                        canvas = np.zeros((3, 256, 256), "uint8")
                        oy = min(oy, 256 - oh)
                        ox = min(ox, 256 - ow)
                        canvas[:, oy:oy + oh, ox:ox + ow] = sub
                        rgb = np.transpose(canvas, (1, 2, 0)).astype("uint8")
                        img = Image.fromarray(rgb, "RGB")
                        d = os.path.join(out_root, str(z), str(tx))
                        os.makedirs(d, exist_ok=True)
                        img.save(os.path.join(d, f"{ty}.jpg"), quality=80, optimize=True)
                        written += 1
            print(f"  {kind}: {written} tiles  z{minz}-{maxz}  -> {out_root}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True)
    ap.add_argument("--minzoom", type=int, default=13)
    ap.add_argument("--maxzoom", type=int, default=17)
    a = ap.parse_args()

    raw = os.path.join(ROOT, "data", "raw", a.area)
    pre = sorted(glob.glob(os.path.join(raw, "pre_*.tif")))
    post = sorted(glob.glob(os.path.join(raw, "post_*.tif")))
    if not pre or not post:
        raise SystemExit(f"no pre/post tif in {raw}")
    print(f"[tiles] {a.area}")
    tiles_for(pre[0], "pre", a.area, a.minzoom, a.maxzoom)
    tiles_for(post[0], "post", a.area, a.minzoom, a.maxzoom)


if __name__ == "__main__":
    main()
