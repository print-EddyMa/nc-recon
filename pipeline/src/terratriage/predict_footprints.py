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
from .fusion import retier_with_priors


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
    footprint_source: str = "osm",
    nc_context: bool = False,
) -> dict:
    t0 = time.time()
    polys, dst_crs, source_used = load_for_area(
        pre_path, cache_dir, area, source=footprint_source
    )
    if limit:
        polys = polys[:limit]
    if not polys:
        raise RuntimeError(f"{area}: no footprints found")

    scores = score_buildings(
        pre_path, post_path, polys, dst_crs, backend=backend, weights_path=cls_weights
    )
    fused = bool(scores) and len(scores[0]) == 4

    to_wgs = Transformer.from_crs(dst_crs, 4326, always_xy=True).transform

    # NC context priors, computed once at the AOI centroid
    priors = None
    if nc_context and fused:
        try:
            from .context import nc_priors
            from .footprints import aoi_bounds_lonlat

            w, s, e, n = aoi_bounds_lonlat(pre_path)
            priors = nc_priors((w + e) / 2, (s + n) / 2)
        except Exception as ex:  # noqa: BLE001
            print(f"[predict_fp] nc-context priors unavailable ({ex})")

    features = []
    for i, (poly, score) in enumerate(zip(polys, scores)):
        if fused:
            cls, conf, tier, srcs = score
            if priors:
                tier, srcs = retier_with_priors(
                    cls, float(srcs.get("margin", 0.0)), tier, srcs, priors
                )
        else:
            cls, conf = score
            tier, srcs = None, None
        poly_s = poly.simplify(0.4, preserve_topology=True) or poly
        pw = shapely_transform(to_wgs, poly_s if not poly_s.is_empty else poly)
        ring = [[float(x), float(y)] for x, y in pw.exterior.coords]
        cen = pw.centroid
        features.append(
            contract.feature(
                f"{area}-{i:06d}", [ring], cls, conf, poly.area, (cen.x, cen.y),
                tier=tier, sources=srcs, footprint_source=source_used,
            )
        )

    fp_label = "NC OneMap footprints" if source_used == "nc_onemap" else "OSM footprints"
    if fused:
        model_name = f"fusion:cmu-classifier + change-detection ({fp_label})"
    elif backend == "keras":
        model_name = f"xview2_baseline:cmu-classifier (ResNet50+CNN, {fp_label})"
    else:
        model_name = f"heuristic:change-detection ({fp_label})"
    if fused:
        notes = (
            "Damage class from the xView2 CMU baseline classifier (ResNet50-v1 + CNN "
            "head, trained on xBD). A per-building confidence tier is fused from "
            "agreement with an independent change-detection pass: buildings where the "
            "two disagree by two or more damage levels (or whose footprint is too "
            "small to classify) are routed to the human review queue. Footprints are "
            "OpenStreetMap."
        )
    elif backend == "keras":
        notes = (
            "Damage from the xView2 CMU baseline classifier (ResNet50-v1 + CNN head), "
            "trained on xBD; a per-building post-image classifier, not the 1st-place "
            "ensemble. Footprints are OpenStreetMap."
        )
    else:
        notes = "Damage from a change-detection heuristic, not a trained CNN. Footprints are OSM."
    if source_used == "nc_onemap":
        notes = notes.replace("Footprints are OpenStreetMap.", "Footprints are NC OneMap.") \
                     .replace("Footprints are OSM.", "Footprints are NC OneMap.")
    if priors:
        notes += (
            f" NC context priors applied (flood_stage={priors.get('flood_stage')}, "
            f"fema_declaration={priors.get('in_fema_decl')}, "
            f"slope_deg={priors.get('slope_deg')}) - they only move borderline "
            "confidence tiers, never the damage class."
        )
    meta = contract.RunMeta(
        event=event, area=area, model=model_name,
        pre_image=contract.ImageMeta(**(pre_meta or {"date": "unknown"})),
        post_image=contract.ImageMeta(**(post_meta or {"date": "unknown"})),
        notes=notes,
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
