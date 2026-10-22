"""Public-mode product: tract-level expected counts, no building-level data.

`run.py ops-aggregate --area X` -> exports/<area>/<area>_public_tracts.geojson

Per 2020 census tract (CDC SVI 2022 geometry): expected structures by FEMA
class (sum of probabilities), residential share, needs-review count, expected
displaced people and the need index from impact.json. Any count below
SUPPRESS is published as null with `suppressed: true`, so a single damaged
home cannot be singled out.
"""
from __future__ import annotations

import json
import os

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from .. import DISCLAIMER, OPS_OUT
from ..analyze.classes import FEMA
from ..analyze.impact import svi_tracts

SUPPRESS = 5


def aggregate(area: str) -> str:
    with open(os.path.join(OPS_OUT, f"{area}.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    imp_p = os.path.join(OPS_OUT, f"{area}.impact.json")
    impact = json.load(open(imp_p, encoding="utf-8")) if os.path.exists(imp_p) else {}
    by_imp = {t["tract"]: t for t in impact.get("tracts", [])}
    feats = [f["properties"] for f in fc["features"]]
    lons = [p["centroid"][0] for p in feats]
    lats = [p["centroid"][1] for p in feats]
    # an area with no structures publishes an empty (but valid) product
    tracts = svi_tracts((min(lons), min(lats), max(lons), max(lats))) if feats else []
    geoms = [shape(t["geometry"]) for t in tracts]
    tree = STRtree(geoms)
    acc: dict[str, dict] = {}
    for p in feats:
        hit = [int(j) for j in tree.query(Point(p["centroid"]), predicate="within")]
        if not hit:
            continue
        fips = tracts[hit[0]]["properties"]["FIPS"]
        a = acc.setdefault(fips, {c: 0.0 for c in FEMA} | {"structures": 0, "not_assessed": 0, "needs_review": 0})
        a["structures"] += 1
        if p.get("damage_probs"):
            for c in FEMA:
                a[c] += p["damage_probs"][c]
            a["needs_review"] += int(p["needs_review"])
        else:
            a["not_assessed"] += 1
    out = []
    for t, g in zip(tracts, geoms):
        fips = t["properties"]["FIPS"]
        if fips not in acc:
            continue
        a = acc[fips]
        props = {"tract": fips, "location": t["properties"].get("LOCATION"), "suppressed_fields": []}
        for k, v in a.items():
            val = round(v, 1) if isinstance(v, float) else v
            if val < SUPPRESS and val != 0:
                props[k] = None
                props["suppressed_fields"].append(k)
            else:
                props[k] = val
        imp = by_imp.get(fips, {})
        # the people figures come from the same few homes: when the structure
        # count is withheld (or the tract has under SUPPRESS assessed homes)
        # they are withheld too, or a single household could be read off them
        few = a["structures"] < SUPPRESS or (imp.get("structures") or 0) < SUPPRESS
        for k in ("expected_displaced", "need_index"):
            v = imp.get(k)
            if few and v is not None:
                props[k] = None
                props["suppressed_fields"].append(k)
            else:
                props[k] = v
        props["svi_percentile"] = imp.get("svi_percentile")
        props["disclaimer"] = DISCLAIMER
        out.append({"type": "Feature", "geometry": t["geometry"], "properties": props})
    d = os.path.join(OPS_OUT, "exports", area)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{area}_public_tracts.geojson")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "properties": {
            "area": area, "run_id": fc["properties"]["run_id"], "suppression_threshold": SUPPRESS,
            "note": "Tract-level expected counts (sum of per-structure probabilities). "
                    "Counts below the threshold are withheld.", "disclaimer": DISCLAIMER},
            "features": out}, fh)
    return path
