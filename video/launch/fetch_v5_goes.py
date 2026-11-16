"""Fetch GOES-16 mesoscale visible frames of Hurricane Helene (NOAA, public domain).

`pipeline/.venv/bin/python video/launch/fetch_v5_goes.py <sector 1|2> <hour0> <hour1> <step_min>`
Band 2 (0.64 um, 0.5 km), day 270 of 2024 (September 26). Writes assets/v5/goes/<n>.jpg.
"""
import concurrent.futures as cf
import os
import re
import sys
import urllib.request

import numpy as np
import rasterio
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets", "v5", "goes")
TMP = os.path.join(HERE, "assets", "v5", "goes_nc")
BUCKET = "https://noaa-goes16.s3.amazonaws.com/"


def keys(sector: str, hour: int):
    u = f"{BUCKET}?list-type=2&prefix=ABI-L2-CMIPM/2024/270/{hour:02d}/OR_ABI-L2-CMIPM{sector}-M6C02&max-keys=70"
    return re.findall(r"<Key>([^<]+)</Key>", urllib.request.urlopen(u).read().decode())


def fetch(args):
    i, key = args
    path = os.path.join(TMP, f"{i}.nc")
    if not os.path.exists(os.path.join(OUT, f"{i:04d}.jpg")):
        with urllib.request.urlopen(BUCKET + key, timeout=60) as r, open(path, "wb") as fh:
            fh.write(r.read())
    return i


def convert(i: int) -> None:
    """GDAL runs in one thread only: decoding in the download pool hung."""
    nc = os.path.join(TMP, f"{i}.nc")
    if not os.path.exists(nc):
        return
    if os.path.exists(os.path.join(OUT, f"{i:04d}.jpg")):     # left by an interrupted run
        os.remove(nc)
        return
    with rasterio.open(f"netcdf:{nc}:CMI") as src:
        a = src.read(1).astype("float32")
        mask = a == src.nodata if src.nodata is not None else a < -1000
        s = src.scales[0]
        o = src.offsets[0]
    r = np.clip(a * s + o, 0, 1.1)
    r[mask] = 0
    g = np.power(np.clip(r, 0, 1), 0.62)             # the usual visible-band gamma
    Image.fromarray((g * 255).astype("uint8")).save(os.path.join(OUT, f"{i:04d}.jpg"), quality=90)
    os.remove(nc)


def main():
    sector, h0, h1, step = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    picks = []
    for h in range(h0, h1):
        picks += keys(sector, h)[::step]
    with cf.ThreadPoolExecutor(6) as ex:
        for i in ex.map(fetch, enumerate(picks)):
            convert(i)
    print(len(picks), "frames")


if __name__ == "__main__":
    main()
