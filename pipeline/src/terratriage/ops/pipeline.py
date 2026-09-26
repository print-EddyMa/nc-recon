"""Ops-mode assessment of one AOI: `python scripts/run.py ops-assess --area old_fort`.

Output: data/output/ops/<area>.geojson (schema ops-1.0), one Feature per
structure with FEMA-class probabilities, confidence, review flag + reasons,
per-channel evidence, USNG, occupancy context and provenance; plus
runs/<run_id>/manifest.json recording everything needed to reproduce it.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import time
import uuid
from datetime import date
from typing import Any

import numpy as np
from shapely.ops import transform as shapely_transform

from . import DATA_DIR, DISCLAIMER, PIPELINE_ROOT
from .analyze import calibration, channels, flood
from .analyze.classes import FEMA, FEMA_DB_LEVEL, crosswalks
from .analyze.evidence import aoi_radiometry, measure
from .analyze.fusion import decide, rules
from .cachekey import code_version
from .collect.nsi import NSI
from .geodesy import transformer, usng
from .plan.events import check_image_pair, event_for_area
from .process import coreg, imagery
from .process.structures import RESIDENTIAL, conflate, unmatched_nsi
from .process.structures import ncr_id as ncr_id_fn
from .provenance import Provenance, utc_now

RAW = os.path.join(DATA_DIR, "raw")
CACHE = os.path.join(DATA_DIR, "cache")
OUT = os.path.join(DATA_DIR, "output", "ops")
RUNS = os.path.join(PIPELINE_ROOT, "runs")
MODEL_ID = "xview2_cmu_baseline"
WEIGHTS = os.path.join(PIPELINE_ROOT, "weights", "classification.hdf5")
SCHEMA = "ops-1.0"


def _cnn_logits(pre_path: str, post_path: str, polys, crs) -> tuple[np.ndarray | None, str | None]:
    from ..classify import _conda_python, _keras_logits, extract_crops

    if not os.path.exists(WEIGHTS):
        return None, "WEIGHTS_MISSING"
    if not _conda_python():
        return None, "TF_ENV_MISSING"
    crops = list(extract_crops(pre_path, post_path, polys, crs))
    try:
        return np.asarray(_keras_logits(crops, WEIGHTS), float), None
    except Exception as ex:  # noqa: BLE001
        print(f"[ops] CNN failed: {ex}")
        return None, "MODEL_ERROR"


def footprints(raster_path: str, area: str, warnings: list[str]) -> dict[str, Any]:
    """USA Structures as the primary footprint set, OSM filling gaps.

    OSM polygons are kept only where they do not overlap a USA Structures
    footprint (>= 30 % of the OSM polygon's area), so nothing is double
    counted. Both are clipped to the imagery and to a sane building size.
    """
    import rasterio
    from shapely.geometry import box, shape
    from shapely.strtree import STRtree

    from ..footprints import MAX_BUILDING_AREA, MIN_BUILDING_AREA, aoi_bounds_lonlat, fetch_osm_buildings_with_ids
    from .cachekey import cache_key
    from .collect.usa_structures import USAStructures

    with rasterio.open(raster_path) as ds:
        crs = ds.crs.to_wkt()
        rb = box(*ds.bounds)
    bbox = aoi_bounds_lonlat(raster_path)
    to_r = transformer("storage", crs).transform
    rb_ll = shapely_transform(transformer(crs, "storage").transform, rb)

    def _ok(p_ll) -> bool:
        a = shapely_transform(to_r, p_ll).area
        return p_ll.within(rb_ll) and MIN_BUILDING_AREA <= a <= MAX_BUILDING_AREA

    polys, srcs, ids, attrs = [], [], [], []
    try:
        usa = USAStructures().fetch(bbox)
        for f in usa.data["features"]:
            g = shape(f["geometry"])
            for part in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
                if part.is_valid and _ok(part):
                    polys.append(part)
                    srcs.append("usa_structures")
                    ids.append(str(f["properties"]["BUILD_ID"]))
                    attrs.append(f["properties"])
        vintage = usa.provenance.dataset_version
    except Exception as ex:  # noqa: BLE001
        warnings.append(f"USA Structures unavailable ({ex}); OSM only")
        vintage = None
    n_usa = len(polys)
    osm_cache = os.path.join(CACHE, f"osm_{cache_key('osm_buildings', geometry=bbox)[:16]}.json")
    osm = [(oid, p) for oid, p in fetch_osm_buildings_with_ids(bbox, cache_path=osm_cache)
           if p.is_valid and _ok(p)]
    tree = STRtree(polys) if polys else None
    added = 0
    for oid, p in osm:
        if tree is not None:
            hit = any(p.intersection(polys[int(k)]).area >= 0.3 * p.area for k in tree.query(p))
            if hit:
                continue
        polys.append(p)
        srcs.append("osm")
        ids.append(oid)
        attrs.append({})
        added += 1
    print(f"[ops] footprints: {n_usa} USA Structures + {added} OSM-only (of {len(osm)} OSM)")
    if vintage:
        warnings.append(f"USA Structures footprints digitised from {vintage}: newer buildings may be missing")
    return {"polys_ll": polys, "sources": srcs, "ids": ids, "attrs": attrs, "crs": crs,
            "counts": {"usa_structures": n_usa, "osm_only": added, "osm_total": len(osm)}}


def _occupants(nsi: dict | None, night: bool, attrs: dict | None = None) -> dict[str, Any] | None:
    usa = attrs or {}
    if not nsi and usa.get("POP_MEDIAN") is None:
        return None
    if not nsi:
        return {"usa_structures_median": usa.get("POP_MEDIAN"),
                "usa_structures_ci95": [usa.get("POP_CI95_LOWER"), usa.get("POP_CI95_UPPER")]}
    if night:
        n = (nsi.get("pop2amu65") or 0) + (nsi.get("pop2amo65") or 0)
    else:
        n = (nsi.get("pop2pmu65") or 0) + (nsi.get("pop2pmo65") or 0)
    o65 = nsi.get("pop2amo65") if night else nsi.get("pop2pmo65")
    return {"nsi_estimate": n, "over_65": o65, "period": "night" if night else "day",
            "usa_structures_median": usa.get("POP_MEDIAN"),
            "usa_structures_ci95": [usa.get("POP_CI95_LOWER"), usa.get("POP_CI95_UPPER")]}


def run_area(area: str, *, limit: int | None = None, night: bool = True,
             wse_sources: list[flood.WSESource] | None = None) -> dict[str, Any]:
    t0 = time.time()
    run_id = f"{area}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:6]}"
    timings: dict[str, float] = {}
    warnings: list[str] = []

    # ---- plan: event + windows (hard assertions) -------------------------- #
    found = event_for_area(area)
    if not found:
        raise SystemExit(f"{area} is not in config/events.yaml; register it with a TUNE/TEST role first")
    ev, aoi = found
    pre_info, post_info = imagery.pair_for_area(RAW, area, ev.maxar_event or "")
    # with date ranges the whole range must satisfy the rule: the latest
    # possible pre date before the incident, the earliest post date after it
    check_image_pair(pre_info.dmax, post_info.dmin, ev.incident_begin, area)
    for info, want in ((pre_info, "pre"), (post_info, "post")):
        for d_ in (info.dmin, info.dmax):
            if ev.classify_image_date(d_) != want:
                raise SystemExit(f"{area}: {want} image date {d_} falls outside the event's {want} window "
                                 f"({getattr(ev, want).start}..{getattr(ev, want).end})")
    pair = imagery.pair_context(pre_info, post_info, rules()["geometry_limit_deg"])
    lag_lo = (post_info.dmin - ev.incident_begin).days
    lag_hi = (post_info.dmax - ev.incident_begin).days
    pair["post_days_after_incident"] = lag_lo if lag_lo == lag_hi else [lag_lo, lag_hi]
    pair["reasons"].append(f"POST_IMAGE_{lag_lo}D_AFTER_INCIDENT" if lag_lo == lag_hi
                           else f"POST_IMAGE_{lag_lo}-{lag_hi}D_AFTER_INCIDENT")
    timings["plan"] = time.time() - t0

    # ---- collect: footprints + NSI --------------------------------------- #
    from ..footprints import aoi_bounds_lonlat

    t = time.time()
    fp = footprints(pre_info.path, area, warnings)
    polys_ll, srcs, ids, attrs, crs = fp["polys_ll"], fp["sources"], fp["ids"], fp["attrs"], fp["crs"]
    if limit:
        polys_ll, srcs, ids, attrs = polys_ll[:limit], srcs[:limit], ids[:limit], attrs[:limit]
    to_r = transformer("storage", crs).transform
    polys = [shapely_transform(to_r, p) for p in polys_ll]
    bbox = aoi_bounds_lonlat(pre_info.path)
    nsi_layer = NSI().fetch(bbox)
    structs = conflate(polys_ll, srcs, ids, nsi_layer.data["features"], attrs)
    missing = unmatched_nsi(structs, nsi_layer.data["features"])
    if missing:
        warnings.append(f"{len(missing)} NSI structure points have no footprint in any source "
                        "(not assessed from imagery; listed in the run manifest)")
    timings["collect"] = time.time() - t

    # ---- process: footprint-to-image alignment, per source, per image ---- #
    t = time.time()
    from shapely.affinity import translate

    from .process import align

    align_info: dict[str, Any] = {}
    polys_pre, polys_post = list(polys), list(polys)
    per_bldg = [{} for _ in polys]
    for src in sorted(set(srcs)):
        ix = [i for i, sname in enumerate(srcs) if sname == src]
        sub = [polys[i] for i in ix]
        for role, info in (("pre", pre_info), ("post", post_info)):
            base = align.consensus(info.path, sub)
            align_info[f"{src}:{role}"] = base.to_dict()
            for i, (dx, dy, gain, weak) in zip(ix, align.refine(info.path, sub, base)):
                moved = translate(polys[i], dx, dy)
                if role == "pre":
                    polys_pre[i] = moved
                else:
                    polys_post[i] = moved
                per_bldg[i][role] = {"dx_m": round(dx, 2), "dy_m": round(dy, 2),
                                     "gain": round(gain, 2), "weak": bool(weak)}
    timings["align"] = time.time() - t

    # ---- process: co-registration + radiometry --------------------------- #
    t = time.time()
    try:
        cr = coreg.estimate_shift(pre_info.path, post_info.path).to_dict()
    except Exception as ex:  # noqa: BLE001
        cr = {"error": str(ex)}
    gains, offs = aoi_radiometry(pre_info.path, post_info.path)
    timings["process"] = time.time() - t

    # ---- analyze: channels ------------------------------------------------ #
    t = time.time()
    ctx_rules = rules()
    evs = measure(pre_info.path, post_info.path, polys_pre, ctx_rules, gains, offs)
    for ev_b, al in zip(evs, per_bldg):
        ev_b.m["alignment"] = al
        if any(v.get("weak") for v in al.values()):
            ev_b.reasons.append("FOOTPRINT_ALIGNMENT_WEAK")
    timings["evidence"] = time.time() - t
    t = time.time()
    logits, cnn_err = _cnn_logits(pre_info.path, post_info.path, polys_post, crs)
    timings["cnn"] = time.time() - t
    cal = calibration.load(MODEL_ID)
    T = float(cal["temperature"]) if cal and "temperature" in cal else None
    fcal = calibration.load("fusion_v1")
    T_fusion = float(fcal["temperature"]) if fcal and "temperature" in fcal else None
    qhat = float(fcal["conformal_qhat"]) if fcal and "conformal_qhat" in fcal else None
    if T is None:
        warnings.append("CNN uncalibrated (no TUNE labels yet): E1 in label-only mode")

    t = time.time()
    e2_base = channels.e2_baseline(evs)
    feats = []
    for i, (st, ev_b) in enumerate(zip(structs, evs)):
        chs = [
            channels.e1(ev_b, None if logits is None else logits[i], T)
            if cnn_err is None else channels.Channel("E1", False, unavailable_reason=cnn_err),
            channels.e2(ev_b, pair["e2_geometry_weight"], e2_base),
            channels.e4(ev_b),
        ]
        cx, cy = st.footprint_ll.centroid.x, st.footprint_ll.centroid.y
        nsi = st.nsi or {}
        src = flood.pick_source(cx, cy, wse_sources or [])
        if src is None:
            chs.append(channels.e5_unavailable("NO_WSE_SOURCE_ON_REACH"))
        elif nsi.get("grnd_elv_m") is None or nsi.get("found_ht") is None:
            chs.append(channels.e5_unavailable("NO_GROUND_OR_FOUNDATION_HEIGHT"))
        else:
            from ..ops.heights import Depth, Elevation

            s, sig = src
            probs, depth = flood.class_probs(
                s.wse, sig, Elevation.of(nsi["grnd_elv_m"]), 0.5,
                Depth.of(nsi["found_ht"], "ft"), 0.3, st.flags["manufactured_home"], seed=i)
            chs.append(channels.e5(probs, depth, s.ref))
        v = decide(chs, T=T_fusion, qhat=qhat, extra_reasons=list(ev_b.reasons),
                   calibrated=T is not None and T_fusion is not None)
        ring = [[round(x, 7), round(y, 7)] for x, y in st.footprint_ll.exterior.coords]
        props = {
            "ncr_id": st.ncr_id,
            "source_ids": st.source_ids,
            "footprint_source": st.footprint_source,
            "area_m2": round(st.area_m2, 1),
            "centroid": [round(cx, 7), round(cy, 7)],
            "usng_1m": usng(cx, cy, 1),
            "usng_10m": usng(cx, cy, 10),
            **v.to_props(),
            "occupancy": st.occtype,
            "flags": st.flags,
            "nsi_match": {"method": st.match_method, "score": st.match_score},
            "stories": nsi.get("num_story"),
            "foundation_type": nsi.get("found_type"),
            "foundation_height_ft": nsi.get("found_ht"),
            "ground_elev_m_navd88": nsi.get("grnd_elv_m"),
            "flood_zone": nsi.get("firmzone"),
            "cbfips_2010": nsi.get("cbfips"),
            "occupants": _occupants(st.nsi, night, st.attrs),
            "primary_occupancy": st.attrs.get("PRIM_OCC"),
            "footprint_image_date": st.attrs.get("IMAGE_DATE"),
            "measurements": ev_b.m,
            # FEMA damage-database aligned fields (for export)
            "fema": {
                "DMG_LEVEL": FEMA_DB_LEVEL[FEMA[v.label]],
                "ASMT_TYPE": "Remote Sensing",
                # FEMA's field is a date: filled only when the capture date is
                # known exactly, never with an invented day
                "IMG_DATE": post_info.date if post_info.exact else None,
                "IMG_DATE_RANGE": f"{post_info.dmin}..{post_info.dmax}",
                "EVENT_NAME": ev.name,
                "EVENT_DATE": ev.incident_begin.isoformat(),
                "DIS_NUMBER": ",".join(d.fema_id for d in ev.declarations),
                "SOURCE": "NC Recon (decision support, unofficial)",
                "USNG": usng(cx, cy, 10),
            },
        }
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                      "properties": props})
    timings["fusion"] = time.time() - t

    # responder-only sidecar: addresses never go in the main (public-servable) file
    responder = {}
    for st in structs:
        addr = ", ".join(str(x) for x in (st.attrs.get("PROP_ADDR"), st.attrs.get("PROP_CITY"),
                                          st.attrs.get("PROP_ZIP")) if x)
        if addr:
            responder[st.ncr_id] = {"address": addr}

    # NSI structures no footprint covers: listed, never silently dropped
    for f in missing:
        np_ = f["properties"]
        x, y = f["geometry"]["coordinates"][:2]
        base = (np_.get("occtype") or "").split("-")[0]
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(x, 7), round(y, 7)]},
                      "properties": {
                          "ncr_id": ncr_id_fn("nsi", str(np_.get("fd_id"))),
                          "source_ids": {"nsi_fd_id": np_.get("fd_id")},
                          "footprint_source": None, "centroid": [round(x, 7), round(y, 7)],
                          "usng_1m": usng(x, y, 1), "usng_10m": usng(x, y, 10),
                          "damage_level": None, "damage_probs": None, "confidence": None,
                          "needs_review": True, "review_reasons": ["NOT_ASSESSED_NO_FOOTPRINT"],
                          "reason_codes": ["NOT_ASSESSED_NO_FOOTPRINT"], "evidence": [],
                          "evidence_unavailable": {"ALL": "NO_FOOTPRINT"},
                          "occupancy": np_.get("occtype"),
                          "flags": {"residential": base in RESIDENTIAL, "manufactured_home": base == "RES2",
                                    "outbuilding": False, "unmatched_source": False, "not_assessed": True},
                          "occupants": _occupants(np_, night),
                          "ground_elev_m_navd88": np_.get("grnd_elv_m"),
                          "foundation_height_ft": np_.get("found_ht"),
                          "cbfips_2010": np_.get("cbfips"),
                      }})

    counts = {c: 0 for c in FEMA}
    expected = np.zeros(len(FEMA))
    n_review = 0
    assessed_probs = []
    n_unassessed = {"total": 0, "residential": 0}
    for f in feats:
        p = f["properties"]
        if p["damage_level"] is None:
            n_unassessed["total"] += 1
            n_unassessed["residential"] += int(p["flags"]["residential"])
            continue
        counts[p["damage_level"]] += 1
        pr = np.array([p["damage_probs"][c] for c in FEMA])
        assessed_probs.append(pr)
        expected += pr
        n_review += int(p["needs_review"])
    interval = count_interval(np.array(assessed_probs)) if assessed_probs else {}

    provenance = {
        "imagery": [imagery.sidecar(RAW, area)[r]["provenance"] | {"role": r, "date_label": imagery.sidecar(RAW, area)[r]["date_label"]}
                    for r in ("pre", "post")] if imagery.sidecar(RAW, area) else [
            Provenance(
                source=f"Maxar Open Data ({i.platform})", source_url=i.url or "",
                license="CC BY-NC 4.0", acquired_utc=i.acquired_utc,
                dataset_version=i.catalog_id, crs="EPSG:32617 (Maxar ARD, WGS 84 UTM 17N)",
                horizontal_datum="WGS 84", units=f"RGB uint8, {i.gsd_m} m native GSD",
            ).to_dict() | {"role": i.role, "geometry": i.to_dict()}
            for i in (pre_info, post_info)
        ],
        "footprints": [
            {"source": "FEMA USA Structures", "license": "US Government work (FEMA/ORNL)",
             "source_url": "https://gis-fema.hub.arcgis.com/pages/usa-structures",
             "count": fp["counts"]["usa_structures"]},
            {"source": "OpenStreetMap (Overpass API), gap-fill only",
             "license": "ODbL 1.0 (attribution + share-alike for derived databases)",
             "source_url": "https://overpass-api.de/", "count": fp["counts"]["osm_only"]},
        ],
        "structures": nsi_layer.provenance.to_dict(),
        "declaration": ev.declarations[0].provenance.to_dict(),
        "model": {
            "id": MODEL_ID, "weights": os.path.basename(WEIGHTS),
            "sha256": "a1f0dff601c8f3582b686ac7ce695f116d339e7913d1928d9ff62ab740e703cd",
            "calibration": cal or "none",
            "input": "post-event 128x128 RGB chip only (the CNN never sees the pre image)",
        },
    }
    fc = {
        "type": "FeatureCollection",
        "properties": {
            "schema": SCHEMA, "run_id": run_id, "generated_utc": utc_now(),
            "disclaimer": DISCLAIMER,
            "event": {"id": ev.id, "name": ev.name,
                      "declarations": [d.fema_id for d in ev.declarations],
                      "incident_begin": ev.incident_begin.isoformat()},
            "aoi": {"id": area, "role": aoi.role, "county": aoi.county},
            "pair_context": pair, "coregistration": cr, "footprint_alignment": align_info,
            "e2_baseline": None if e2_base is None else {"median": round(e2_base[0], 3),
                                                         "scaled_mad": round(e2_base[1], 3)},
            "counts": counts,
            "expected_counts": {c: round(float(v), 1) for c, v in zip(FEMA, expected)},
            "expected_counts_80pct": interval,
            "argmax_counts_note": ("`counts` are argmax labels over broad probability "
                                   "distributions; headline totals should use expected_counts "
                                   "with their 80% interval"),
            "not_assessed": n_unassessed,
            "review_routing_note": ("review routing and all channel likelihoods come from "
                                    "provisional config until TUNE labels exist"),
            "n_structures": len(feats), "n_needs_review": n_review,
            "calibration": {"cnn": "none" if T is None else T, "fusion": "none" if T_fusion is None else T_fusion,
                            "conformal": "none" if qhat is None else qhat},
            "config_status": {"context_rules": ctx_rules.get("status"),
                              "crosswalk_xbd_to_fema": crosswalks()["xbd_to_fema"]["status"]},
            "warnings": warnings,
            "provenance": provenance,
            "runtime_sec": round(time.time() - t0, 1),
        },
        "features": feats,
    }
    os.makedirs(OUT, exist_ok=True)
    out_path = os.path.join(OUT, f"{area}.geojson")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(fc, fh)
    with open(os.path.join(OUT, f"{area}.responder.json"), "w", encoding="utf-8") as fh:
        json.dump({"run_id": run_id, "access": "responder-only (contains addresses)",
                   "structures": responder}, fh)
    _manifest(run_id, area, out_path, pre_info, post_info, timings, warnings, missing, ctx_rules)
    print(f"[ops] {area}: {len(feats)} structures, {n_review} need review, counts {counts} "
          f"in {fc['properties']['runtime_sec']}s -> {out_path}")
    return fc


def count_interval(probs: np.ndarray, n: int = 2000, seed: int = 0, q=(10, 90)) -> dict[str, list[int]]:
    """80 % interval on per-class structure counts, sampling each structure's
    class independently from its probabilities (a lower bound on the true
    spread, since neighbouring errors are correlated)."""
    rng = np.random.default_rng(seed)
    cum = np.cumsum(probs, axis=1)
    draws = np.zeros((n, probs.shape[1]), dtype=int)
    for k in range(n):
        u = rng.random((probs.shape[0], 1))
        cls = (u > cum).sum(axis=1)
        draws[k] = np.bincount(np.minimum(cls, probs.shape[1] - 1), minlength=probs.shape[1])
    lo, hi = np.percentile(draws, q, axis=0)
    return {c: [int(a), int(b)] for c, a, b in zip(FEMA, lo, hi)}


def _sha256(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest(run_id, area, out_path, pre, post, timings, warnings, missing, ctx_rules) -> None:
    import importlib.metadata as md

    d = os.path.join(RUNS, run_id)
    os.makedirs(d, exist_ok=True)
    libs = {}
    for lib in ("numpy", "rasterio", "shapely", "pyproj", "scikit-image", "scipy"):
        try:
            libs[lib] = md.version(lib)
        except md.PackageNotFoundError:
            pass
    man = {
        "run_id": run_id, "area": area, "git_sha": code_version(),
        "python": sys.version.split()[0], "platform": platform.platform(), "libraries": libs,
        "inputs": {"pre": {"path": pre.path, "sha256": _sha256(pre.path)},
                   "post": {"path": post.path, "sha256": _sha256(post.path)}},
        "config": {"context_rules_version": ctx_rules.get("version"),
                   "context_rules_status": ctx_rules.get("status")},
        "timings_sec": {k: round(v, 2) for k, v in timings.items()},
        "warnings": warnings,
        "nsi_structures_without_footprint": [
            {"fd_id": f["properties"].get("fd_id"), "occtype": f["properties"].get("occtype"),
             "lonlat": f["geometry"]["coordinates"]} for f in missing],
        "output": {"path": out_path, "sha256": _sha256(out_path)},
        "eecu_usage": None,
    }
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=2)
