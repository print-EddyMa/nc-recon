"""Groma's calls beside the Helene search-and-rescue field categories:
`run.py ops-sarcop --area X`.

During Helene, urban search-and-rescue teams logged a FEMA damage category
for each structure they passed (SARCOP waypoints, collected with QuickCapture
from 2024-09-27). Buncombe County published its extract as a public ArcGIS
layer (12,891 waypoints, FEMA levels including "unaffected"). That is the only
public structure-level Helene damage record with negatives found so far, so it
is the first thing a Groma area in Buncombe can be held up against.

What this is and is not:
* A comparison, not validation. SAR categories are windshield calls made
  under pressure in the first days; Groma reads imagery taken at a
  different time (for Swannanoa, NC OneMap's spring 2025 orthos, months
  later, after demolition and repair had begun). Disagreement is expected
  for both reasons, and the output says so.
* Kept out of `data/labels` and `evaluate.py`: the accuracy report stays
  "not yet validated" until analysts label under the protocol.
* TEST areas are refused unless explicitly allowed, so a hold-out area is
  never looked at through this lens by accident.
* Only the fields below are requested from the layer. The public layer also
  carries rescuers' names and e-mail addresses and residents' street
  addresses; none of that is fetched, cached or stored.
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Any

import numpy as np

from .. import DISCLAIMER, OPS_OUT
from ..collect.base import DiskCache, SchemaError, http_json
from ..provenance import utc_now
from .classes import FEMA, FEMA_LABEL

SARCOP = ("https://services6.arcgis.com/VLA0ImJ33zhtGEaP/arcgis/rest/services/"
          "SARCOP_v9_SIFS_NC_Damage/FeatureServer/0/query")
FIELDS = "OBJECTID,waypoint,waypoint_cat_cal,program_type,horizontalAccuracy,start_time,data_source"
SAR_TO_FEMA = {"unaffected": "no_damage", "affected": "affected", "minor": "minor",
               "major": "major", "destroyed": "destroyed"}
MATCH_M = 10.0           # SAR phones: median horizontal accuracy about 4.7 m
MASS = 0.8               # credible set: smallest set of levels holding 80% of the probability
SEVERE = ("major", "destroyed")
HOMES = ("single_family", "multi_family", "manufactured_home")   # SARCOP program_type values for dwellings
CAVEATS = [
    "SAR categories are rapid windshield calls by search teams, not engineering inspections or FEMA's PDA.",
    "The imagery Groma read may be months from the SAR visit; structures repaired or demolished in "
    "between disagree for that reason alone.",
    "SAR teams logged a subset of structures, weighted toward the visibly damaged, so this sample is not "
    "the area's damage distribution.",
    "This is not an accuracy figure: the accuracy report stays 'not yet validated' until analysts label "
    "under the protocol.",
]


def fetch_points(bbox: tuple[float, float, float, float], pad_deg: float = 0.0005,
                 cache_max_age_s: float = 7 * 86400) -> list[dict]:
    """SARCOP structure waypoints inside the area (no personal fields)."""
    w, s, e, n = bbox
    key = "{:.4f}_{:.4f}_{:.4f}_{:.4f}".format(w, s, e, n).replace("-", "m").replace(".", "p")
    cache = DiskCache("sarcop")
    hit = cache.get(key, cache_max_age_s)
    if hit is not None:
        return hit
    pts: list[dict] = []
    offset = 0
    while True:
        d = http_json(SARCOP, params={
            "where": "1=1", "outFields": FIELDS, "returnGeometry": "true", "outSR": "4326", "f": "json",
            "geometry": f"{w - pad_deg},{s - pad_deg},{e + pad_deg},{n + pad_deg}",
            "geometryType": "esriGeometryEnvelope", "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
            "resultOffset": offset, "resultRecordCount": 2000}, timeout=60)
        if not isinstance(d, dict) or not isinstance(d.get("features"), list):
            raise SchemaError("SARCOP layer: no features array")
        for f in d["features"]:
            a = f.get("attributes") or {}
            g = f.get("geometry") or {}
            if "x" not in g or "y" not in g:
                continue
            pts.append({"id": a.get("OBJECTID"), "lon": g["x"], "lat": g["y"],
                        "waypoint": a.get("waypoint"), "category": a.get("waypoint_cat_cal"),
                        "program_type": a.get("program_type"), "acc_m": a.get("horizontalAccuracy"),
                        "t": a.get("start_time"), "source": a.get("data_source")})
        if len(d["features"]) < 2000:
            break
        offset += 2000
    cache.put(key, pts)
    return pts


def _local_xy(lon0: float, lat0: float):
    kx = 111320.0 * math.cos(math.radians(lat0))
    return lambda lon, lat: ((lon - lon0) * kx, (lat - lat0) * 110540.0)


def credible_set(probs: dict[str, float], mass: float = MASS) -> list[str]:
    order = sorted(FEMA, key=lambda k: -(probs.get(k) or 0.0))
    out, tot = [], 0.0
    for k in order:
        out.append(k)
        tot += probs.get(k) or 0.0
        if tot >= mass - 1e-9:
            break
    return out


def kappa(cm: np.ndarray, weights: str | None = None) -> float | None:
    n = cm.sum()
    if n == 0:
        return None
    k = cm.shape[0]
    i, j = np.indices((k, k))
    w = np.abs(i - j) / (k - 1) if weights == "linear" else (i != j).astype(float)
    expected = np.outer(cm.sum(1), cm.sum(0)) / n
    denom = (w * expected).sum()
    return None if denom == 0 else float(1 - (w * cm).sum() / denom)


def match(points: list[dict], features: list[dict], match_m: float = MATCH_M) -> tuple[list[dict], dict[str, int]]:
    """One SAR category per assessed structure: point inside the footprint,
    else the nearest footprint within `match_m`. Where several waypoints land
    on one structure the latest visit wins (follow-up visits supersede)."""
    from shapely.geometry import Point, Polygon
    from shapely.strtree import STRtree

    polys, props = [], []
    lon0 = lat0 = None
    for f in features:
        g = f.get("geometry") or {}
        p = f.get("properties") or {}
        if g.get("type") != "Polygon" or not p.get("damage_level"):
            continue
        if lon0 is None:
            lon0, lat0 = g["coordinates"][0][0]
        polys.append(g["coordinates"][0])
        props.append(p)
    counts = {"waypoints": len(points), "not_structure": 0, "unmapped_category": 0, "unmatched": 0,
              "matched": 0, "superseded_visits": 0}
    if not polys:
        counts["unmatched"] = len(points)
        return [], counts
    xy = _local_xy(lon0, lat0)
    shapes = [Polygon([xy(x, y) for x, y in ring]) for ring in polys]
    tree = STRtree(shapes)
    best: dict[int, dict] = {}
    for pt in points:
        if str(pt.get("category") or "").strip().lower() != "structure":
            counts["not_structure"] += 1
            continue
        lvl = SAR_TO_FEMA.get(str(pt.get("waypoint") or "").strip().lower())
        if lvl is None:
            counts["unmapped_category"] += 1
            continue
        q = Point(*xy(pt["lon"], pt["lat"]))
        hit = None
        for i in tree.query(q):
            if shapes[i].contains(q):
                hit = (int(i), 0.0)
                break
        if hit is None:
            i = int(tree.nearest(q))
            dist = shapes[i].distance(q)
            if dist <= match_m:
                hit = (i, dist)
        if hit is None:
            counts["unmatched"] += 1
            continue
        i, dist = hit
        rec = {"ncr_id": props[i]["ncr_id"], "sar": lvl, "sar_time": pt.get("t"), "dist_m": round(dist, 1),
               "program_type": pt.get("program_type"), "ncr": props[i]["damage_level"],
               "probs": props[i].get("damage_probs") or {}, "needs_review": bool(props[i].get("needs_review"))}
        prev = best.get(i)
        if prev is not None:
            counts["superseded_visits"] += 1
            if (prev.get("sar_time") or 0) >= (rec.get("sar_time") or 0):
                continue
        best[i] = rec
    out = list(best.values())
    counts["matched"] = len(out)
    return out, counts


def summarise(pairs: list[dict]) -> dict[str, Any]:
    K = len(FEMA)
    cm = np.zeros((K, K), dtype=int)
    in_set = in_set_rev = n_rev = 0
    tp = fp = fn = 0
    exp_severe = 0.0
    for r in pairs:
        a, b = FEMA.index(r["sar"]), FEMA.index(r["ncr"])
        cm[a, b] += 1
        if r["sar"] in credible_set(r["probs"]):
            in_set += 1
            in_set_rev += r["needs_review"]
        n_rev += r["needs_review"]
        sar_sev, ncr_sev = r["sar"] in SEVERE, r["ncr"] in SEVERE
        tp += sar_sev and ncr_sev
        fp += (not sar_sev) and ncr_sev
        fn += sar_sev and (not ncr_sev)
        exp_severe += sum(r["probs"].get(k) or 0.0 for k in SEVERE)
    n = int(cm.sum())

    def rate(x, d):
        return None if d == 0 else round(x / d, 3)

    diag = int(np.trace(cm))
    within1 = int(sum(cm[i, j] for i in range(K) for j in range(K) if abs(i - j) <= 1))
    prec, rec = rate(tp, tp + fp), rate(tp, tp + fn)
    f1 = None if not prec or not rec else round(2 * prec * rec / (prec + rec), 3)
    by_review = {}
    for flag in (False, True):
        sub = [r for r in pairs if r["needs_review"] == flag]
        agree = sum(r["sar"] == r["ncr"] for r in sub)
        by_review["sent_to_review" if flag else "not_sent_to_review"] = {
            "n": len(sub), "same_level": rate(agree, len(sub)),
            "sar_level_in_80pct_set": rate(sum(r["sar"] in credible_set(r["probs"]) for r in sub), len(sub))}
    return {
        "n": n,
        "levels": [FEMA_LABEL[k] for k in FEMA],
        "confusion_rows_sar_cols_ncr": cm.tolist(),
        "same_level": rate(diag, n),
        "within_one_level": rate(within1, n),
        "kappa": None if kappa(cm) is None else round(kappa(cm), 3),
        "kappa_linear_weighted": None if kappa(cm, "linear") is None else round(kappa(cm, "linear"), 3),
        "sar_level_in_80pct_set": rate(in_set, n),
        "major_or_destroyed": {"both_count": tp, "sar_count": tp + fn, "ncr_most_likely_count": tp + fp,
                               "ncr_expected_count": round(exp_severe, 1),
                               "precision": prec, "recall": rec, "f1": f1},
        "by_review": by_review,
        "sar_counts": {FEMA_LABEL[k]: int(cm[FEMA.index(k)].sum()) for k in FEMA},
        "ncr_counts": {FEMA_LABEL[k]: int(cm[:, FEMA.index(k)].sum()) for k in FEMA},
    }


def _bbox(features: list[dict]) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for f in features:
        g = f.get("geometry") or {}
        if g.get("type") == "Polygon":
            for x, y in g["coordinates"][0]:
                xs.append(x)
                ys.append(y)
        elif g.get("type") == "Point":
            xs.append(g["coordinates"][0])
            ys.append(g["coordinates"][1])
    if not xs:
        raise ValueError("this assessment has no structures to compare")
    return min(xs), min(ys), max(xs), max(ys)


def compare_area(area: str, *, allow_test: bool = False, write: bool = True) -> dict[str, Any]:
    with open(os.path.join(OPS_OUT, f"{area}.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    run = fc.get("properties") or {}
    role = (run.get("aoi") or {}).get("role")
    if role == "TEST" and not allow_test:
        raise SystemExit(f"{area} is a TEST (hold-out) area; refusing to compare it unless --allow-test")
    county = (run.get("aoi") or {}).get("county")
    bbox = _bbox(fc["features"])
    t0 = time.time()
    points = fetch_points(bbox)
    pairs, counts = match(points, fc["features"])
    imagery = ((run.get("provenance") or {}).get("imagery") or {})
    out = {
        "area": area, "role": role, "county": county, "generated_utc": utc_now(),
        "run_id": run.get("run_id"), "disclaimer": DISCLAIMER,
        "reference": {"name": "Helene SARCOP structure waypoints (Buncombe County public extract)",
                      "url": SARCOP.rsplit("/query", 1)[0], "fields_used": FIELDS.split(","),
                      "note": "personal fields on the public layer are not fetched"},
        "ncr_imagery": imagery,
        "match_rule": f"waypoint inside a footprint, else nearest footprint within {MATCH_M:g} m; latest visit wins",
        "credible_set": f"smallest set of levels holding {int(MASS * 100)}% of Groma's probability",
        "counts": counts,
        "summary": summarise(pairs),
        # FEMA IA counts homes; the teams also logged shops, churches and the like
        "summary_homes": summarise([r for r in pairs if r.get("program_type") in HOMES]),
        "caveats": CAVEATS + ([] if role != "TUNE" else
                              ["This is a TUNE area: weights may be adjusted on it, so it is not a held-out result."]),
        "pairs": [{k: r[k] for k in ("ncr_id", "sar", "ncr", "needs_review", "dist_m", "program_type")}
                  for r in pairs],
        "runtime_sec": round(time.time() - t0, 1),
    }
    if not counts["waypoints"]:
        out["caveats"].insert(0, "No SARCOP waypoints fall in this area (the public extract covers Buncombe County).")
    if write:
        p = os.path.join(OPS_OUT, f"{area}.sarcop_reference.json")
        with open(p + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        os.replace(p + ".tmp", p)
    return out


def format_summary(r: dict[str, Any]) -> str:
    s, c = r["summary"], r["counts"]
    m = s["major_or_destroyed"]
    lines = [
        f"{r['area']} ({r['role']}, {r['county']} County) vs {r['reference']['name']}",
        f"  waypoints {c['waypoints']}, matched to an assessed structure {c['matched']}, unmatched {c['unmatched']}, "
        f"not a structure {c['not_structure']}, superseded visits {c['superseded_visits']}",
    ]
    if s["n"]:
        lines += [
            f"  same level {s['same_level']:.0%}, within one level {s['within_one_level']:.0%}, "
            f"kappa {s['kappa']}, linear-weighted kappa {s['kappa_linear_weighted']}",
            f"  SAR level inside Groma's 80% set {s['sar_level_in_80pct_set']:.0%}",
            f"  Major or Destroyed: SAR {m['sar_count']}, Groma most likely {m['ncr_most_likely_count']}, "
            f"expected {m['ncr_expected_count']}; precision {m['precision']}, recall {m['recall']}, F1 {m['f1']}",
            "  rows = SAR, columns = Groma: " + json.dumps(s["confusion_rows_sar_cols_ncr"]),
        ]
        h = r.get("summary_homes") or {}
        if h.get("n"):
            hm = h["major_or_destroyed"]
            lines.append(f"  homes only ({h['n']}): Major or Destroyed agreed {hm['both_count']} of "
                         f"{hm['ncr_most_likely_count']}, caught {hm['both_count']} of {hm['sar_count']}")
    lines += ["  caveats:"] + [f"   - {x}" for x in r["caveats"]]
    return "\n".join(lines)
