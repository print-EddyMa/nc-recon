"""Real material for the Groma launch film: `python video/launch/fetch_assets.py`.

Everything here is public, keyless, and read from the same sources the
product uses. Nothing is generated or stock.

  plates/<name>_pre.jpg, _post.jpg   NC OneMap orthoimagery before (2023) and
                                     after (spring 2025) Helene, 16:9
  cap/<key>.jpg                      Civil Air Patrol frames, 2024-09-28/29
                                     (full resolution originals)

Writes under video/launch/assets/ (git-ignored).
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "assets")
NC = "https://services.nconemap.gov/secure/rest/services/Imagery"
UA = "Groma/2.0 (launch film asset fetch; +https://github.com/print-EddyMa/nc-recon)"

# name: (lon, lat, width in metres)
PLATES = {
    "swannanoa_home": (-82.4072571, 35.6028075, 300.0),
    "swannanoa_wide": (-82.4000, 35.6020, 1400.0),
    "swannanoa_corridor": (-82.3955, 35.6050, 700.0),
}
PX = (1920, 1080)


def merc(lon: float, lat: float) -> tuple[float, float]:
    x = lon * 20037508.34 / 180
    y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180) * 20037508.34 / 180
    return x, y


def export(service: str, lon: float, lat: float, width_m: float, path: str) -> None:
    if os.path.exists(path):
        return
    x, y = merc(lon, lat)
    k = 1 / math.cos(math.radians(lat))           # web mercator stretch
    hw = width_m * k / 2
    hh = hw * PX[1] / PX[0]
    q = {"bbox": f"{x - hw},{y - hh},{x + hw},{y + hh}", "bboxSR": 3857, "imageSR": 3857,
         "size": f"{PX[0]},{PX[1]}", "format": "jpg", "bandIds": "0,1,2", "f": "image",
         "interpolation": "RSP_BilinearInterpolation", "compressionQuality": 92}
    req = urllib.request.Request(f"{NC}/{service}/ImageServer/exportImage?{urllib.parse.urlencode(q)}",
                                 headers={"User-Agent": UA})
    import time

    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                body = r.read()
            break
        except Exception as ex:  # noqa: BLE001 - the analysis service 504s under load
            print(f"  {service}: {ex}; retrying")
            time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f"{service}: gave up")
    if body[:2] not in (b"\xff\xd8", b"\x89P"):
        raise RuntimeError(f"{service}: not an image: {body[:120]!r}")
    with open(path, "wb") as fh:
        fh.write(body)


def cap_frames(keys: list[str]) -> None:
    sys.path.insert(0, os.path.join(ROOT, "pipeline", "src"))
    from datetime import date

    from terratriage.ops.collect import cap_photos as cp

    fc = json.load(open(os.path.join(ROOT, "pipeline", "data", "output", "ops", "swannanoa.geojson")))
    xs = [f["properties"]["centroid"] for f in fc["features"]]
    bbox = (min(x for x, _ in xs), min(y for _, y in xs), max(x for x, _ in xs), max(y for _, y in xs))
    pts = cp.points("helene-2024-nc", bbox, date(2024, 9, 25))
    by = {p["key"]: p for p in pts}
    os.makedirs(os.path.join(OUT, "cap"), exist_ok=True)
    meta = {}
    for k in keys:
        p = by.get(k)
        if not p:
            print("missing", k)
            continue
        dst = os.path.join(OUT, "cap", f"{k}.jpg")
        if not os.path.exists(dst):
            req = urllib.request.Request(p["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=300) as r:
                open(dst, "wb").write(r.read())
        meta[k] = {"url": p["url"], "date": p["date"], "kind": p["kind"], "mission": p["mission"]}
    json.dump(meta, open(os.path.join(OUT, "cap", "meta.json"), "w"), indent=1)


def main() -> None:
    os.makedirs(os.path.join(OUT, "plates"), exist_ok=True)
    for name, (lon, lat, w) in PLATES.items():
        export("Orthoimagery_2020_2023_4band_analysis", lon, lat, w, os.path.join(OUT, "plates", f"{name}_pre.jpg"))
        export("Orthoimagery_Helene_2025", lon, lat, w, os.path.join(OUT, "plates", f"{name}_post.jpg"))
        print("plate", name)
    if len(sys.argv) > 1:
        cap_frames(sys.argv[1:])


if __name__ == "__main__":
    main()
