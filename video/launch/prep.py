"""Prepare composition inputs from the real assets: `python video/launch/prep.py`.

  assets/cap_3200/<key>.jpg      CAP originals reduced to 3200 px (push-ins stay sharp at 1080p)
  assets/overlays/<plate>.json   Groma footprints projected onto a plate, with the
                                 model's most likely level (from the real assessment)
  assets/export_rows.json        FEMA damage survey columns and a few real rows
                                 (no addresses: those are responder-only)
"""
from __future__ import annotations

import json
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
A = os.path.join(HERE, "assets")
sys.path.insert(0, HERE)
from fetch_assets import PLATES, PX, merc  # noqa: E402

AREA = "swannanoa"


def cap() -> None:
    src, dst = os.path.join(A, "cap"), os.path.join(A, "cap_3200")
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        if f.endswith(".jpg") and not os.path.exists(os.path.join(dst, f)):
            im = Image.open(os.path.join(src, f))
            im.draft("RGB", (3200, 3200))
            im = im.convert("RGB")
            im.thumbnail((3200, 3200), Image.LANCZOS)
            im.save(os.path.join(dst, f), quality=90)


def overlays(fc: dict) -> None:
    os.makedirs(os.path.join(A, "overlays"), exist_ok=True)
    for name, (lon, lat, wm) in PLATES.items():
        x0, y0 = merc(lon, lat)
        k = 1 / math.cos(math.radians(lat))
        hw = wm * k / 2
        hh = hw * PX[1] / PX[0]
        sx, sy = PX[0] / (2 * hw), PX[1] / (2 * hh)
        out = []
        for f in fc["features"]:
            g, p = f.get("geometry") or {}, f.get("properties") or {}
            if g.get("type") != "Polygon":
                continue
            pts = []
            for lo, la in g["coordinates"][0]:
                mx, my = merc(lo, la)
                pts.append((round((mx - (x0 - hw)) * sx, 1), round(((y0 + hh) - my) * sy, 1)))
            if not any(0 <= x <= PX[0] and 0 <= y <= PX[1] for x, y in pts):
                continue
            out.append({"id": p["ncr_id"][:8], "level": p.get("damage_level"), "review": bool(p.get("needs_review")),
                        "pts": pts})
        json.dump(out, open(os.path.join(A, "overlays", f"{name}.json"), "w"))
        print(name, len(out), "footprints")


def export_rows(fc: dict) -> None:
    from collections import Counter

    sys.path.insert(0, os.path.join(ROOT, "pipeline", "src"))
    from terratriage.ops.disseminate.exports import FEMA_IA_FIELDS

    lv = {"no_damage": "unaffected", "affected": "affected", "minor": "minor", "major": "major", "destroyed": "destroyed"}
    feats = [f["properties"] for f in fc["features"] if (f.get("properties") or {}).get("damage_level")]
    feats.sort(key=lambda p: -max((p.get("damage_probs") or {}).values() or [0]))
    rows = []
    for p in feats:
        if p["damage_level"] in ("major", "destroyed") and len(rows) < 3 or p["damage_level"] == "minor" and len(rows) < 4 \
                or p["damage_level"] == "no_damage" and len(rows) < 5:
            rows.append({"incident_id_number": "DR-4827-NC", "county": "Buncombe",
                         "level_of_damage_assessed": lv[p["damage_level"]],
                         "ncr_usng_10m": p.get("usng_10m"),
                         "ncr_probability": round(max(p["damage_probs"].values()), 2),
                         "street_address": "(responder only)"})
    json.dump({"columns": list(FEMA_IA_FIELDS), "rows": rows,
               "counts": Counter(p["damage_level"] for p in feats), "n": len(fc["features"])},
              open(os.path.join(A, "export_rows.json"), "w"), indent=1)


def main() -> None:
    fc = json.load(open(os.path.join(ROOT, "pipeline", "data", "output", "ops", f"{AREA}.geojson")))
    cap()
    overlays(fc)
    export_rows(fc)


if __name__ == "__main__":
    main()
