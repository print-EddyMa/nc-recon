"""Impact and need: from structure damage probabilities to people.

`run.py ops-impact --area X` -> data/output/ops/<area>.impact.json

Per structure (residential, assessed):
  occupants   NSI night (or day) estimate; USA Structures median as fallback.
              Always reported as a range across the independent estimates.
  p_occupied  1 - (vacant share) from ACS 5-year tract tables B25002/B25004
              when a Census API key is configured (NCR_CENSUS_API_KEY; the
              API stopped serving keyless requests in 2026). WNC has many
              seasonal / second homes, so without it displacement is an upper
              bound and is labelled "occupancy unadjusted".

  E[displaced] = sum_b occupants_b * p_occupied_b *
                 (P_b(destroyed) + P_b(major) + w_minor * P_b(minor))

Per 2020 census tract (spatial join, so NSI's 2010 block ids never need a
crosswalk):
  need = E[displaced] * (1 + alpha * SVI_percentile)

The isolation (beta) and power-outage (gamma) terms of the Phase J need index
are NOT computed: those channels (E8) are not built yet, and the output says
so rather than silently dropping them. The need index ranks where to look
first; it is not an eligibility determination.
"""
from __future__ import annotations

import json
import os
from typing import Any

import numpy as np

from .. import DATA_DIR
from ..collect.base import DiskCache, http_json
from ..cachekey import cache_key

OPS_OUT = os.path.join(DATA_DIR, "output", "ops")
SVI = ("https://services3.arcgis.com/ZvidGQkLaDJxRSJ2/arcgis/rest/services/"
       "CDC_ATSDR_Social_Vulnerability_Index_2022_USA/FeatureServer/2")
PARAMS = {"w_minor": 0.10, "w_minor_sensitivity": [0.0, 0.25], "alpha": 1.0}


def svi_tracts(bbox) -> list[dict[str, Any]]:
    cache = DiskCache("svi")
    key = cache_key("cdc_svi_2022_tract", geometry=bbox, dataset_version="2022")
    hit = cache.get(key)
    if hit is not None:
        return hit
    w, s, e, n = bbox
    d = http_json(f"{SVI}/query", params={
        "where": "1=1", "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
        "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FIPS,LOCATION,RPL_THEMES,E_TOTPOP,E_HU", "returnGeometry": "true", "f": "geojson"},
        timeout=120)
    feats = d.get("features") or []
    cache.put(key, feats)
    return feats


def acs_occupancy(tract_fips: list[str]) -> dict[str, float] | None:
    """tract FIPS -> share of housing units occupied (ACS 2022 5-yr), or None."""
    key = os.environ.get("NCR_CENSUS_API_KEY", "").strip()
    if not key:
        return None
    out: dict[str, float] = {}
    by_county: dict[tuple[str, str], list[str]] = {}
    for f in tract_fips:
        by_county.setdefault((f[:2], f[2:5]), []).append(f)
    for (st, co), _ in by_county.items():
        rows = http_json("https://api.census.gov/data/2022/acs/acs5", params={
            "get": "B25002_001E,B25002_002E,B25004_006E", "for": "tract:*",
            "in": f"state:{st} county:{co}", "key": key}, timeout=60)
        hdr = rows[0]
        for r in rows[1:]:
            d = dict(zip(hdr, r))
            fips = d["state"] + d["county"] + d["tract"]
            tot = float(d["B25002_001E"] or 0)
            if tot > 0:
                out[fips] = float(d["B25002_002E"]) / tot
    return out


def run(area: str, seed: int = 0, n_mc: int = 2000) -> dict[str, Any]:
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    with open(os.path.join(OPS_OUT, f"{area}.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    feats = [f["properties"] for f in fc["features"]]
    lons = [p["centroid"][0] for p in feats]
    lats = [p["centroid"][1] for p in feats]
    bbox = (min(lons), min(lats), max(lons), max(lats))
    svi_status = "ok"
    try:
        tracts = svi_tracts(bbox)
    except Exception as ex:  # noqa: BLE001 - displacement does not need SVI
        tracts, svi_status = [], f"unavailable ({str(ex)[:120]})"
    tgeoms = [shape(t["geometry"]) for t in tracts]
    tree = STRtree(tgeoms) if tgeoms else None
    try:
        occ_share = acs_occupancy([t["properties"]["FIPS"] for t in tracts])
    except Exception as ex:  # noqa: BLE001
        print(f"[impact] ACS unavailable: {ex}")
        occ_share = None

    rows = []
    unassessed = {"residential_structures": 0, "occupants_nsi": 0.0}
    for p in feats:
        if not (p.get("flags") or {}).get("residential"):
            continue
        if not p.get("damage_probs"):
            # residential inventory point with no footprint: never assessed,
            # but its people exist - counted separately, never silently dropped
            unassessed["residential_structures"] += 1
            unassessed["occupants_nsi"] += float((p.get("occupants") or {}).get("nsi_estimate") or 0)
            continue
        o = p.get("occupants") or {}
        ests = [v for v in (o.get("nsi_estimate"), o.get("usa_structures_median")) if v is not None]
        if not ests:
            continue
        tract = None
        if tree is not None:
            pt = Point(p["centroid"])
            for j in tree.query(pt, predicate="within"):
                tract = tracts[int(j)]["properties"]
                break
        rows.append({
            "ncr_id": p["ncr_id"],
            "probs": [p["damage_probs"][c] for c in ("no_damage", "affected", "minor", "major", "destroyed")],
            "occ_lo": float(min(ests)), "occ_hi": float(max(ests)), "occ_mid": float(np.median(ests)),
            "tract": tract["FIPS"] if tract else None,
        })
    if not rows:
        return {"area": area, "status": "NO_RESIDENTIAL_STRUCTURES"}

    rng = np.random.default_rng(seed)
    P = np.array([r["probs"] for r in rows])
    lo = np.array([r["occ_lo"] for r in rows])
    hi = np.array([r["occ_hi"] for r in rows])
    p_occ = np.array([(occ_share or {}).get(r["tract"], 1.0) for r in rows])

    def displaced(w_minor: float) -> np.ndarray:
        """Monte Carlo totals: class drawn per structure, occupants uniform in
        [lo, hi], occupancy Bernoulli(p_occ)."""
        cum = np.cumsum(P, axis=1)
        out = np.zeros(n_mc)
        for k in range(n_mc):
            cls = (rng.random((len(rows), 1)) > cum).sum(axis=1)
            occ = lo + rng.random(len(rows)) * (hi - lo)
            here = rng.random(len(rows)) < p_occ
            disp = (cls >= 3) | ((cls == 2) & (rng.random(len(rows)) < w_minor))
            out[k] = float((occ * here * disp).sum())
        return out

    main = displaced(PARAMS["w_minor"])
    sens = {str(w): [float(np.percentile(displaced(w), q)) for q in (10, 50, 90)]
            for w in PARAMS["w_minor_sensitivity"]}
    expected_each = (P[:, 3] + P[:, 4] + PARAMS["w_minor"] * P[:, 2]) * (lo + hi) / 2 * p_occ

    by_tract: dict[str, dict[str, Any]] = {}
    svi_by = {t["properties"]["FIPS"]: t["properties"] for t in tracts}
    for r, e in zip(rows, expected_each):
        k = r["tract"] or "unknown"
        d = by_tract.setdefault(k, {"tract": k, "structures": 0, "expected_displaced": 0.0})
        d["structures"] += 1
        d["expected_displaced"] += float(e)
    for k, d in by_tract.items():
        s = svi_by.get(k, {})
        svi = s.get("RPL_THEMES")
        svi = None if svi is None or svi < 0 else float(svi)   # CDC uses -999 for no data
        d["location"] = s.get("LOCATION")
        d["svi_percentile"] = svi
        d["need_index"] = None if svi is None else d["expected_displaced"] * (1 + PARAMS["alpha"] * svi)
        d["expected_displaced"] = round(d["expected_displaced"], 1)
        if d["need_index"] is not None:
            d["need_index"] = round(d["need_index"], 1)
    ranked = sorted(by_tract.values(), key=lambda d: -(d["need_index"] or 0))
    out = {
        "area": area, "run_id": fc["properties"]["run_id"],
        "residential_structures_assessed": len(rows),
        "occupancy_adjustment": "ACS 2022 5-yr tract occupied share" if occ_share
        else "UNADJUSTED (no NCR_CENSUS_API_KEY): seasonal / vacant homes counted as occupied",
        "bias_note": (
            "Neither a lower nor an upper bound: biased HIGH where seasonal / vacant homes are counted "
            "as occupied" + ("" if occ_share else " (no occupancy adjustment applied)") + ", biased LOW by "
            f"{unassessed['residential_structures']} residential structures with no footprint "
            f"(~{round(unassessed['occupants_nsi'])} people by NSI) that were not assessed, and "
            "conditional on uncalibrated damage probabilities."),
        "unassessed_residential": {"structures": unassessed["residential_structures"],
                                   "occupants_nsi": round(unassessed["occupants_nsi"], 1)},
        "expected_displaced": {"p10": float(np.percentile(main, 10)), "median": float(np.median(main)),
                               "p90": float(np.percentile(main, 90))},
        "sensitivity_w_minor": sens,
        "params": PARAMS,
        "svi_status": svi_status,
        "need_index_terms_missing": ["beta * isolated_persons (E8 road isolation not built)",
                                     "gamma * outage_person_days (E8 Black Marble not built)"],
        "tracts": ranked,
        "note": "Prioritization aid, not an eligibility determination. Class probabilities are "
                "uncalibrated until TUNE labels exist.",
    }
    with open(os.path.join(OPS_OUT, f"{area}.impact.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    return out
