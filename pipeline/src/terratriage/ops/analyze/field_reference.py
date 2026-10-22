"""Groma's calls beside published building-level damage records, any hazard:
`run.py ops-field-reference --area X [--source dins|fema_hgda|sarcop]`.

Reference sources (keyless public ArcGIS layers, checked 2026-10-22):

  dins       CAL FIRE Damage Inspection (DINS) master layer: every structure
             inspectors visited after California wildfires since 2013, with a
             FEMA-style damage level (No Damage, Affected, Minor, Major,
             Destroyed) and structure type.
  fema_hgda  FEMA Historical Geospatial Damage Assessment database: 19
             hurricanes, floods, tornadoes and earthquakes 2011-2020. Only
             imagery-observed records (ASMT_TYPE 'RS') are used; most of the
             database is modelled from depth grids and would be circular.
  nemac      Buncombe County "Helene Visual Damage Assessment" points (UNCA
             NEMAC): damaged and destroyed buildings by cause (flood,
             landslide, tree on house). Positives only, so the summary is
             recall-style: how many of them Groma also called damaged.
  sarcop     Buncombe County's Helene search-and-rescue extract
             (analyze/sarcop_reference.py, unchanged).

Same rules as the SARCOP comparison: it is a comparison, not validation; it
never writes to data/labels; TEST areas need an explicit allow; and only the
fields listed are requested (the DINS layer also holds street addresses,
parcel numbers and assessed values, none of which are fetched).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .. import DATA_DIR, DISCLAIMER
from ..collect.base import DiskCache, SchemaError, http_json
from ..provenance import utc_now
from . import sarcop_reference as sr

OPS_OUT = os.path.join(DATA_DIR, "output", "ops")

DINS = ("https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/"
        "POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0/query")
DINS_FIELDS = "OBJECTID,DAMAGE,STRUCTURETYPE,INCIDENTNAME,INCIDENTSTARTDATE"
DINS_LEVEL = {"no damage": "unaffected", "affected": "affected", "minor": "minor", "major": "major",
              "destroyed": "destroyed"}

HGDA = ("https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/"
        "FEMA_Historical_Geospatial_Damage_Assessment_Database/FeatureServer/0/query")
HGDA_FIELDS = "OBJECTID,DMG_LEVEL,DMG_TYPE,ASMT_TYPE,IMG_DATE,EVENT_NAME,DIS_NUMBER"
HGDA_LEVEL = {"NOD": "unaffected", "AFF": "affected", "MIN": "minor", "MAJ": "major", "DES": "destroyed"}

NEMAC = ("https://services1.arcgis.com/PwLrOgCfU0cYShcG/arcgis/rest/services/"
         "Damage_Points_(Public_View)/FeatureServer/0/query")
NEMAC_FIELDS = "OBJECTID,DamageType"
# building classes only (roads, bridges and debris fields are left out); the
# "Sructure" spelling is the source's own
NEMAC_CLASSES = {
    "sructure destroyed (flood)": ("destroyed", "flood"), "structure destroyed (flood)": ("destroyed", "flood"),
    "sructure destroyed (landslide)": ("destroyed", "landslide"),
    "structure destroyed (landslide)": ("destroyed", "landslide"),
    "structure damage (flood)": ("damaged", "flood"), "structure damage (landslide)": ("damaged", "landslide"),
    "tree on house": ("damaged", "tree"),
}


def _page(url: str, params: dict[str, Any]) -> list[dict]:
    out, offset = [], 0
    while True:
        d = http_json(url, params={**params, "returnGeometry": "true", "outSR": "4326", "f": "json",
                                   "geometryType": "esriGeometryEnvelope", "inSR": "4326",
                                   "spatialRel": "esriSpatialRelIntersects",
                                   "resultOffset": offset, "resultRecordCount": 2000}, timeout=90)
        if not isinstance(d, dict) or not isinstance(d.get("features"), list):
            raise SchemaError(f"reference layer: no features array ({str(d)[:120]})")
        out += d["features"]
        if len(d["features"]) < 2000 or not d.get("exceededTransferLimit", len(d["features"]) == 2000):
            break
        offset += 2000
    return out


def _home(structure_type: str) -> str | None:
    t = (structure_type or "").lower()
    if "single family" in t:
        return "single_family"
    if "multi family" in t or "mixed commercial/residential" in t:
        return "multi_family"
    if "mobile home" in t or "motor home" in t:
        return "manufactured_home"
    return None


def fetch_dins(bbox, event) -> list[dict]:
    """DINS inspections in the area for fires that started within a week of
    the incident (as SARCOP-shaped points)."""
    w, s, e, n = bbox
    lo = int(datetime.combine(event.incident_begin, datetime.min.time(), timezone.utc).timestamp() * 1000)
    hi = lo + 8 * 86400 * 1000
    lo -= 3 * 86400 * 1000
    feats = _page(DINS, {"where": "1=1", "outFields": DINS_FIELDS, "geometry": f"{w},{s},{e},{n}"})
    pts = []
    for f in feats:
        a, g = f.get("attributes") or {}, f.get("geometry") or {}
        start = a.get("INCIDENTSTARTDATE")
        if "x" not in g or start is None or not lo <= start <= hi:
            continue
        dmg = str(a.get("DAMAGE") or "").lower()
        lvl = next((v for k, v in DINS_LEVEL.items() if dmg.startswith(k)), None)
        pts.append({"id": a.get("OBJECTID"), "lon": g["x"], "lat": g["y"], "category": "structure",
                    "waypoint": lvl or dmg, "program_type": _home(a.get("STRUCTURETYPE")),
                    "structure_type": a.get("STRUCTURETYPE"), "incident": a.get("INCIDENTNAME"), "t": start})
    return pts


def fetch_hgda(bbox, event) -> list[dict]:
    """FEMA's imagery-observed damage points for this event's declarations."""
    nums = [d.disaster_number for d in event.declarations]
    if not nums:
        return []
    w, s, e, n = bbox
    where = "ASMT_TYPE='RS' AND (" + " OR ".join(f"DIS_NUMBER LIKE '%{x}%'" for x in nums) + ")"
    feats = _page(HGDA, {"where": where, "outFields": HGDA_FIELDS, "geometry": f"{w},{s},{e},{n}"})
    pts = []
    for f in feats:
        a, g = f.get("attributes") or {}, f.get("geometry") or {}
        if "x" not in g:
            continue
        pts.append({"id": a.get("OBJECTID"), "lon": g["x"], "lat": g["y"], "category": "structure",
                    "waypoint": HGDA_LEVEL.get(str(a.get("DMG_LEVEL") or "").upper(), a.get("DMG_LEVEL")),
                    "program_type": None, "dmg_type": a.get("DMG_TYPE"), "t": a.get("IMG_DATE")})
    return pts


def fetch_nemac(bbox, event) -> list[dict]:
    """NEMAC building damage points (Helene, Buncombe County only). 'Damaged'
    has no level, so it is carried as 'affected' for matching and summarised
    as 'Groma called any damage'."""
    if "helene" not in event.id:
        return []
    w, s, e, n = bbox
    feats = _page(NEMAC, {"where": "1=1", "outFields": NEMAC_FIELDS, "geometry": f"{w},{s},{e},{n}"})
    pts = []
    for f in feats:
        a, g = f.get("attributes") or {}, f.get("geometry") or {}
        cls = NEMAC_CLASSES.get(str(a.get("DamageType") or "").strip().lower())
        if "x" not in g or cls is None:
            continue
        pts.append({"id": a.get("OBJECTID"), "lon": g["x"], "lat": g["y"], "category": "structure",
                    "waypoint": "destroyed" if cls[0] == "destroyed" else "affected",
                    "program_type": cls[1], "t": 0})
    return pts


def summarise_positives(pairs: list[dict]) -> dict[str, Any]:
    """For a reference that lists only damaged buildings: how often Groma
    agrees there is damage. No precision or kappa: there are no negatives."""
    def rate(x, d):
        return None if d == 0 else round(x / d, 3)

    des = [r for r in pairs if r["sar"] == "destroyed"]
    dam = [r for r in pairs if r["sar"] != "destroyed"]
    by_cause = {}
    for cause in sorted({r.get("program_type") or "other" for r in pairs}):
        sub = [r for r in pairs if (r.get("program_type") or "other") == cause]
        by_cause[cause] = {"n": len(sub), "ncr_any_damage": rate(sum(r["ncr"] != "no_damage" for r in sub), len(sub)),
                           "ncr_major_or_destroyed": rate(sum(r["ncr"] in sr.SEVERE for r in sub), len(sub))}
    return {
        "n": len(pairs),
        "destroyed_points": len(des),
        "ncr_major_or_destroyed_at_destroyed": rate(sum(r["ncr"] in sr.SEVERE for r in des), len(des)),
        "damaged_points": len(dam),
        "ncr_any_damage_at_damaged": rate(sum(r["ncr"] != "no_damage" for r in dam), len(dam)),
        "ncr_minor_or_worse_at_damaged": rate(sum(r["ncr"] in ("minor", *sr.SEVERE) for r in dam), len(dam)),
        "by_cause": by_cause,
    }


SOURCES: dict[str, dict[str, Any]] = {
    "dins": {
        "name": "CAL FIRE Damage Inspection (DINS) master layer", "url": DINS.rsplit("/query", 1)[0],
        "fields": DINS_FIELDS, "fetch": fetch_dins, "match_m": 15.0,
        "caveats": [
            "DINS inspectors record a damage level from the ground; Groma reads imagery. The two can differ "
            "on the same building (interior or partial damage, debris clearance before the flight).",
            "DINS points sit on the structure or near it; a point more than 15 m from any footprint is not "
            "matched.",
            "Outbuildings (sheds, detached garages) are in DINS as 'Utility Misc Structure'; the homes-only "
            "summary leaves them out.",
        ]},
    "fema_hgda": {
        "name": "FEMA Historical Geospatial Damage Assessment (imagery-observed records)",
        "url": HGDA.rsplit("/query", 1)[0], "fields": HGDA_FIELDS, "fetch": fetch_hgda, "match_m": 15.0,
        "caveats": [
            "FEMA's records are imagery interpretations too, made by analysts at a different time and "
            "resolution; agreement is between two remote reads, not with the ground.",
            "Only ASMT_TYPE 'RS' records are used: modelled records come from depth grids, not observation.",
        ]},
    "nemac": {
        "name": "Buncombe County Helene Visual Damage Assessment points (UNCA NEMAC)",
        "url": NEMAC.rsplit("/query", 1)[0], "fields": NEMAC_FIELDS, "fetch": fetch_nemac, "match_m": 15.0,
        "positives_only": True,
        "caveats": [
            "The layer lists damaged and destroyed buildings only, so these are recall-style figures: there are "
            "no undamaged buildings to measure false alarms against.",
            "The analysts most likely read the same spring 2025 post-event imagery Groma reads, so agreement is "
            "between two reads of one picture, not an independent check.",
            "'Damaged' carries no level; it is counted as agreement when Groma calls any damage.",
        ]},
}


def pick_source(event) -> str:
    if "wildfire" in event.hazards and event.state == "CA":
        return "dins"
    if event.declarations and max(d.incident_begin.year for d in event.declarations) <= 2020:
        return "fema_hgda"
    return "sarcop"


def compare_area(area: str, source: str | None = None, *, allow_test: bool = False,
                 write: bool = True, fetch: Callable | None = None) -> dict[str, Any]:
    from ..plan.events import event_for_area

    found = event_for_area(area)
    if not found:
        raise SystemExit(f"{area} is not a registered area")
    event = found[0]
    source = source or pick_source(event)
    if source == "sarcop":
        return sr.compare_area(area, allow_test=allow_test, write=write)
    if source not in SOURCES:
        raise SystemExit(f"unknown reference source {source}; one of {', '.join(['sarcop', *SOURCES])}")
    spec = SOURCES[source]
    with open(os.path.join(OPS_OUT, f"{area}.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    run = fc.get("properties") or {}
    role = (run.get("aoi") or {}).get("role")
    if role == "TEST" and not allow_test:
        raise SystemExit(f"{area} is a TEST (hold-out) area; refusing to compare it unless --allow-test")
    bbox = sr._bbox(fc["features"])
    t0 = time.time()
    cache = DiskCache(f"ref_{source}")
    key = f"{event.id}_" + "_".join(f"{v:.4f}" for v in bbox).replace("-", "m").replace(".", "p")
    points = cache.get(key, 7 * 86400)
    if points is None:
        points = (fetch or spec["fetch"])(bbox, event)
        cache.put(key, points)
    pairs, counts = sr.match(points, fc["features"], match_m=spec["match_m"])
    out = {
        "area": area, "role": role, "county": (run.get("aoi") or {}).get("county"), "source": source,
        "generated_utc": utc_now(), "run_id": run.get("run_id"), "disclaimer": DISCLAIMER,
        "reference": {"name": spec["name"], "url": spec["url"], "fields_used": spec["fields"].split(","),
                      "note": "only the fields listed are requested; addresses and personal fields are not"},
        "ncr_imagery": (run.get("provenance") or {}).get("imagery"),
        "match_rule": f"point inside a footprint, else nearest footprint within {spec['match_m']:g} m; "
                      "latest record wins",
        "credible_set": f"smallest set of levels holding {int(sr.MASS * 100)}% of Groma's probability",
        "counts": counts,
        "summary": summarise_positives(pairs) if spec.get("positives_only") else sr.summarise(pairs),
        "summary_homes": None if spec.get("positives_only") else
        sr.summarise([r for r in pairs if r.get("program_type") in sr.HOMES]),
        "caveats": spec["caveats"] + [
            "This is not an accuracy figure: the accuracy report stays 'not yet validated' until analysts "
            "label under the protocol."] + (
            ["This is a TUNE area: weights may be adjusted on it, so it is not a held-out result."]
            if role == "TUNE" else
            ["This is a TEST (hold-out) area: nothing was tuned on it."] if role == "TEST" else []),
        "pairs": [{k: r[k] for k in ("ncr_id", "sar", "ncr", "needs_review", "dist_m", "program_type")}
                  for r in pairs],
        "runtime_sec": round(time.time() - t0, 1),
    }
    if not points:
        out["caveats"].insert(0, f"No {spec['name']} records fall in this area.")
    if write:
        p = os.path.join(OPS_OUT, f"{area}.field_reference.json")
        with open(p + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        os.replace(p + ".tmp", p)
    return out


def format_summary(r: dict[str, Any]) -> str:
    s = r["summary"]
    if "destroyed_points" in s:
        c = r["counts"]
        lines = [f"{r['area']} ({r['role']}) vs {r['reference']['name']}",
                 f"  points {c['waypoints']}, matched {c['matched']}, unmatched {c['unmatched']}",
                 f"  destroyed points {s['destroyed_points']}: Groma Major or Destroyed "
                 f"{s['ncr_major_or_destroyed_at_destroyed']}",
                 f"  damaged points {s['damaged_points']}: Groma any damage {s['ncr_any_damage_at_damaged']}, "
                 f"Minor or worse {s['ncr_minor_or_worse_at_damaged']}",
                 "  by cause: " + json.dumps(s["by_cause"])]
        return "\n".join(lines + ["  caveats:"] + [f"   - {x}" for x in r["caveats"]])
    return sr.format_summary(r).replace(" SAR ", " reference ").replace("SAR level", "reference level") \
        .replace("rows = SAR", "rows = reference").replace("Major or Destroyed: SAR", "Major or Destroyed: reference")
