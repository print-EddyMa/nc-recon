"""Footprints pipeline: OSM building polygons + per-building damage classifier
-> contract GeoJSON. This is the primary Phase A path (no learned localisation).
"""
from __future__ import annotations

import json
import os
import time

from pyproj import Transformer
from shapely.ops import transform as shapely_transform

from . import contract
from .footprints import load_for_area
from .classify import score_buildings


def run(
    pre_path: str,
    post_path: str,
    out_path: str,
    *,
    event: str,
    area: str,
    cache_dir: str,
    backend: str = "heuristic",
    cls_weights: str | None = None,
    pre_meta: dict | None = None,
    post_meta: dict | None = None,
    limit: int | None = None,
) -> dict:
    t0 = time.time()
    polys, dst_crs = load_for_area(pre_path, cache_dir, area)
    if limit:
        polys = polys[:limit]
    if not polys:
        raise RuntimeError(f"{area}: no footprints found")

    scores = score_buildings(
        pre_path, post_path, polys, dst_crs, backend=backend, weights_path=cls_weights
    )

    to_wgs = Transformer.from_crs(dst_crs, 4326, always_xy=True).transform
    features = []
    for i, (poly, (cls, conf)) in enumerate(zip(polys, scores)):
        poly_s = poly.simplify(0.4, preserve_topology=True) or poly
        pw = shapely_transform(to_wgs, poly_s if not poly_s.is_empty else poly)
        ring = [[float(x), float(y)] for x, y in pw.exterior.coords]
        cen = pw.centroid
        features.append(
            contract.feature(f"{area}-{i:06d}", [ring], cls, conf, poly.area, (cen.x, cen.y))
        )

    model_name = (
        "xview2_baseline:cmu-classifier (ResNet50+CNN, OSM footprints)"
        if backend == "keras" else
        "heuristic:change-detection (OSM footprints)"
    )
    meta = contract.RunMeta(
        event=event, area=area, model=model_name,
        pre_image=contract.ImageMeta(**(pre_meta or {"date": "unknown"})),
        post_image=contract.ImageMeta(**(post_meta or {"date": "unknown"})),
        notes=None if backend == "keras" else
        "Damage from a change-detection heuristic, not a trained CNN. Footprints are OSM.",
    )
    fc = contract.collection(features, meta)
    fc["properties"]["runtime_sec"] = round(time.time() - t0, 1)

    problems = contract.validate(fc)
    if problems:
        print(f"[predict_fp] WARNING {len(problems)} contract issue(s): {problems[:3]}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(fc, fh)
    print(f"[predict_fp] {out_path}: {len(features)} buildings {fc['properties']['counts']} "
          f"in {fc['properties']['runtime_sec']}s")
    return fc
