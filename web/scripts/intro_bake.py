#!/usr/bin/env python
"""Bake the intro sequence's own assets from the pipeline's outputs (no network).

    npm run intro:assets        (runs this with the pipeline's Python)

Writes web/public/intro/:
  structures.json   Old Fort, one row per structure: outline, FEMA level, review
                    flag. No ids, no addresses, no evidence: only what the
                    sequence draws. Old Fort is a TUNE area (never a hold-out).
  areas.json        every assessed area's public summary (the same numbers
                    GET /ops/areas serves), plus totals and Old Fort's figures
  oldfort_wide.jpg  the whole post-event Maxar tile the assessment read,
                    resampled to the structures' extent, for the pulled-back shots

Every figure the sequence shows comes out of these files; nothing is typed in.
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
PIPE = os.path.join(WEB, "..", "pipeline")
OPS = os.path.join(PIPE, "data", "output", "ops")
OUT = os.path.join(WEB, "public", "intro")
FEMA = ("no_damage", "affected", "minor", "major", "destroyed")
AREA = "old_fort"
WIDE_PX = 4096


def title(aid: str, name: str | None) -> str:
    import re

    return name or re.sub(r"_[0-9a-f]{4}$", "", aid).replace("_", " ").title()


def structures() -> dict:
    with open(os.path.join(OPS, f"{AREA}.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    rows, xs, ys = [], [], []
    for f in fc["features"]:
        p = f["properties"]
        lvl = FEMA.index(p["damage_level"]) if p.get("damage_level") else -1
        c = [round(p["centroid"][0], 6), round(p["centroid"][1], 6)]
        xs.append(c[0])
        ys.append(c[1])
        row = {"c": c, "l": lvl, "v": int(bool(p.get("needs_review")) and lvl >= 0)}
        if f["geometry"]["type"] == "Polygon":
            row["r"] = [[round(x, 6), round(y, 6)] for x, y in f["geometry"]["coordinates"][0]]
        rows.append(row)
    P = fc["properties"]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    out = {"area": AREA, "run_id": P["run_id"], "bbox": bbox, "structures": rows}
    with open(os.path.join(OUT, "structures.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print(f"structures.json  {len(rows)} structures, bbox {bbox}")
    return out


def areas() -> None:
    rows = []
    for p in sorted(glob.glob(os.path.join(OPS, "*.geojson"))):
        aid = os.path.basename(p)[:-8]
        with open(p, encoding="utf-8") as fh:
            fc = json.load(fh)
        P = fc["properties"]
        cs = [f["properties"]["centroid"] for f in fc["features"] if f["properties"].get("centroid")]
        if not cs:
            continue
        ec, rng = P["expected_counts"], P.get("expected_counts_80pct") or {}
        imp_p = p[:-8] + ".impact.json"
        displaced = None
        if os.path.exists(imp_p):
            with open(imp_p, encoding="utf-8") as fh:
                displaced = round(json.load(fh)["expected_displaced"]["median"])
        post = next((i for i in (P.get("provenance") or {}).get("imagery", []) if i.get("role") == "post"), {})
        pre = next((i for i in (P.get("provenance") or {}).get("imagery", []) if i.get("role") == "pre"), {})
        rows.append({
            "id": aid, "name": title(aid, (P.get("aoi") or {}).get("name")),
            "county": (P.get("aoi") or {}).get("county") or "",
            "center": [round(sum(c[0] for c in cs) / len(cs), 5), round(sum(c[1] for c in cs) / len(cs), 5)],
            "structures": P["n_structures"],
            "assessed": P["n_structures"] - P["not_assessed"]["total"],
            "severe": round(ec["major"] + ec["destroyed"]),
            "severe_lo": sum((rng.get(c) or [0, 0])[0] for c in ("major", "destroyed")),
            "severe_hi": sum((rng.get(c) or [0, 0])[1] for c in ("major", "destroyed")),
            "review": P["n_needs_review"],
            "displaced": displaced,
            "runtime_s": P.get("runtime_sec"),
            "expected": {c: round(ec[c]) for c in FEMA},
            "pre_date": (pre.get("acquired_utc") or "")[:10] or None,
            "post_date": (post.get("acquired_utc") or "")[:10] or None,
        })
    rows.sort(key=lambda r: -r["severe"])
    out = {
        "areas": rows,
        "total": {"areas": len(rows), "structures": sum(r["structures"] for r in rows),
                  "severe": sum(r["severe"] for r in rows), "review": sum(r["review"] for r in rows),
                  "max_runtime_s": max((r["runtime_s"] or 0) for r in rows)},
        "focus": next(r for r in rows if r["id"] == AREA),
    }
    with open(os.path.join(OUT, "areas.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(f"areas.json  {len(rows)} areas, totals {out['total']}")


def wide_image(bbox: list[float]) -> None:
    """The post-event image over the structures' extent, in a Web Mercator
    grid (what a deck.gl BitmapLayer stretches between its corner bounds)."""
    import numpy as np
    import rasterio
    from PIL import Image
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject, transform_bounds

    src_path = sorted(glob.glob(os.path.join(PIPE, "data", "raw", AREA, "post_*.tif")))
    if not src_path:
        print("oldfort_wide.jpg  SKIPPED: no post image on disk")
        return
    pad = 0.002
    with rasterio.open(src_path[0]) as ds:
        # no black margins: stay inside the image itself (its UTM rectangle is
        # slightly rotated against lon/lat, so come in a little from each edge)
        iw, isth, ie, inn = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
    inset_x, inset_y = (ie - iw) * 0.012, (inn - isth) * 0.012
    w, s = max(bbox[0] - pad, iw + inset_x), max(bbox[1] - pad, isth + inset_y)
    e, n = min(bbox[2] + pad, ie - inset_x), min(bbox[3] + pad, inn - inset_y)
    left, bottom, right, top = transform_bounds("EPSG:4326", "EPSG:3857", w, s, e, n)
    width = WIDE_PX
    height = int(round(width * (top - bottom) / (right - left)))
    dst = np.zeros((3, height, width), dtype="uint8")
    with rasterio.open(src_path[0]) as ds:
        # average on read first: the source is ~0.3 m and the target ~1.4 m
        dec = max(1, int(((right - left) / width) / abs(ds.transform.a) / 1.5))
        h, wd = ds.height // dec, ds.width // dec
        arr = ds.read(indexes=[1, 2, 3], out_shape=(3, h, wd), resampling=Resampling.average)
        t = ds.transform * ds.transform.scale(ds.width / wd, ds.height / h)
        reproject(arr, dst, src_transform=t, src_crs=ds.crs,
                  dst_transform=from_bounds(left, bottom, right, top, width, height),
                  dst_crs="EPSG:3857", resampling=Resampling.bilinear)
    # the satellite tile has a no-data strip (here its western fifth): crop to
    # the columns and rows that actually hold imagery, and move the bounds with it
    valid = dst.sum(axis=0) > 0
    cols = np.where(valid.mean(axis=0) > 0.97)[0]
    rows = np.where(valid[:, cols[0]:cols[-1] + 1].mean(axis=1) > 0.97)[0]
    c0, c1, r0, r1 = int(cols[0]), int(cols[-1]) + 1, int(rows[0]), int(rows[-1]) + 1
    dst = dst[:, r0:r1, c0:c1]
    mx = lambda c: left + (right - left) * c / width      # noqa: E731
    my = lambda r: top - (top - bottom) * r / height      # noqa: E731
    from rasterio.warp import transform_bounds as tb

    w, s, e, n = tb("EPSG:3857", "EPSG:4326", mx(c0), my(r1), mx(c1), my(r0))
    width, height = c1 - c0, r1 - r0
    Image.fromarray(np.transpose(dst, (1, 2, 0))).save(
        os.path.join(OUT, "oldfort_wide.jpg"), format="JPEG", quality=84, optimize=True)
    with open(os.path.join(OUT, "oldfort_wide.json"), "w", encoding="utf-8") as fh:
        json.dump({"bounds": [w, s, e, n], "width": width, "height": height,
                   "source": os.path.basename(src_path[0])}, fh)
    print(f"oldfort_wide.jpg  {width}x{height}, bounds {[round(v, 5) for v in (w, s, e, n)]}")


if __name__ == "__main__":
    if not os.path.isdir(OPS):
        sys.exit(f"no pipeline outputs at {OPS}: run an assessment first")
    os.makedirs(OUT, exist_ok=True)
    st = structures()
    areas()
    wide_image(st["bbox"])
