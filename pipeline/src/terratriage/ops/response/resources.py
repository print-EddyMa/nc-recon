"""Lifeline facilities around the area and their likely status.

Facilities come from OpenStreetMap (collect/osm.py), grouped by FEMA's
Community Lifelines. Each facility is checked against what the assessment
and the hazard data say about its location:

  damage     the nearest assessed building within 60 m and its damage level
             (the facility itself, or the block it sits in)
  hazard     inside the event's hazard footprint (fire perimeter, mapped
             landslide of this storm)
  access     reachable by road with known blocks, and with debris as well
             (response/access.py); the all-bridges worst case is reported for
             the area, not used to flag single facilities

Facility status (estimated, never confirmed):
  disrupted   severe damage at the location, inside a landslide, or cut off
              by known road blocks
  at_risk     inside a fire perimeter, beside damage, or cut off only in the
              worst-case road scenario
  no_evidence nothing in the open data says it is affected
  not_assessed outside the assessed buildings and no hazard data covers it

Lifeline status follows FEMA's colours as an estimate: red when a critical
facility is disrupted, yellow when any facility is disrupted or at risk, green when facilities were found and none is flagged, grey
when nothing was found or nothing could be checked. Confirm with owners and
utilities: this is where to look first, not a status report.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import Point

from . import AreaRun, local_xy, p_severe

LIFELINES = {
    "safety_security": "Safety and security",
    "food_water_shelter": "Food, hydration, shelter",
    "health_medical": "Health and medical",
    "energy": "Energy",
    "communications": "Communications",
    "transportation": "Transportation",
    "hazardous_materials": "Hazardous materials",
    "water_systems": "Water systems",
}
CRITICAL = {"hospital", "dialysis", "nursing_home", "fire_station", "ems_station", "police",
            "substation", "power_plant", "water_treatment", "wastewater_treatment", "telecom_exchange",
            "shelter", "superfund_site", "toxics_release_facility"}
NEAR_M = 60.0


def _transportation(acc: dict[str, Any] | None) -> dict[str, Any] | None:
    """The roads themselves: red when known blocks cut buildings off, yellow
    when segments are blocked or debris could cut buildings off, else green."""
    if not acc:
        return None
    sc, rd = acc.get("scenarios") or {}, acc.get("roads") or {}
    kb = (sc.get("known_blocks") or {}).get("isolated_buildings", 0)
    pdb = (sc.get("plus_debris") or {}).get("isolated_buildings", 0)
    if kb:
        colour, why = "red", f"{kb} buildings cut off by known road blocks"
    elif rd.get("blocked") or pdb:
        colour, why = "yellow", (f"{rd.get('blocked', 0)} road segments blocked; "
                                 f"{pdb} buildings cut off if debris blocks nearby roads")
    else:
        colour, why = "green", "no road blocks found in the open data"
    return {"status": colour, "roads_note": why, "bridges_unverified": rd.get("bridge", 0)}


def assess(ar: AreaRun, facilities: list[dict[str, Any]], access_points: dict[str, Any] | None,
           hazard_geoms: dict[str, Any] | None, access_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    flood = any(h in ("riverine_flood", "flash_flood", "coastal_surge") for h in ar.event.hazards)
    lon0, lat0 = ar.center
    xy = local_xy(lon0, lat0)
    pts = np.array([xy(*f["properties"]["centroid"]) for f in ar.features])
    tree = cKDTree(pts) if len(pts) else None
    w, s, e, n = ar.bbox
    margin = 0.001
    out = []
    for fac in facilities:
        fx, fy = xy(fac["lon"], fac["lat"])
        rec = dict(fac)
        flags: list[str] = []
        assessed = (w - margin) <= fac["lon"] <= (e + margin) and (s - margin) <= fac["lat"] <= (n + margin)
        dmg = None
        if tree is not None and assessed:
            d, i = tree.query((fx, fy))
            if d <= NEAR_M:
                p = ar.features[int(i)]["properties"]
                dmg = {"level": p.get("damage_level"), "p_major_or_destroyed": round(p_severe(p), 2),
                       "distance_m": round(float(d), 1), "ncr_id": p.get("ncr_id")}
        rec["damage_nearby"] = dmg
        hz_in = []
        for h, g in (hazard_geoms or {}).items():
            if g is not None and g.contains(Point(fac["lon"], fac["lat"])):
                hz_in.append(h)
        rec["inside_hazard"] = hz_in
        acc = (access_points or {}).get(fac["id"]) or {}
        rec["access"] = {k: v.get("access") for k, v in acc.items()}
        rec["min_to_hospital"] = (acc.get("known_blocks") or {}).get("min_to_hospital")

        if dmg and dmg["p_major_or_destroyed"] >= 0.5:
            flags.append("severe damage at the location")
        if "landslide" in hz_in:
            flags.append("inside a mapped landslide")
        if rec["access"].get("known_blocks") == "isolated":
            flags.append("cut off by known road blocks")
        risk: list[str] = []
        if "wildfire" in hz_in:
            risk.append("inside the fire perimeter")
        if dmg and 0.2 <= dmg["p_major_or_destroyed"] < 0.5:
            risk.append("damage likely nearby")
        if fac["kind"] == "dam" and flood and str(fac.get("hazard_potential") or "").lower() == "high":
            risk.append("high-hazard dam in a flood event: confirm it has been inspected")
        if rec["access"].get("plus_debris") == "isolated" and rec["access"].get("known_blocks") != "isolated":
            risk.append("cut off if debris blocks the roads beside destroyed buildings")
        if flags:
            rec["status"] = "disrupted"
        elif risk:
            rec["status"] = "at_risk"
        elif assessed or hz_in or acc or fac["kind"] == "dam":
            rec["status"] = "no_evidence"
        else:
            rec["status"] = "not_assessed"
        rec["reasons"] = flags + risk
        rec["critical"] = fac["kind"] in CRITICAL or (
            fac["kind"] == "dam" and str(fac.get("hazard_potential") or "").lower() == "high")
        out.append(rec)

    lifelines = []
    for key, label in LIFELINES.items():
        fs = [f for f in out if f["lifeline"] == key]
        crit_dis = [f for f in fs if f["critical"] and f["status"] == "disrupted"]
        any_dis = [f for f in fs if f["status"] == "disrupted"]
        any_risk = [f for f in fs if f["status"] == "at_risk"]
        checked = [f for f in fs if f["status"] != "not_assessed"]
        if not fs or not checked:
            colour = "grey"
        elif crit_dis:
            colour = "red"
        elif any_dis or any_risk:
            colour = "yellow"
        else:
            colour = "green"
        lifelines.append({
            "lifeline": key, "label": label, "status": colour, "facilities": len(fs),
            "disrupted": len(any_dis), "at_risk": sum(f["status"] == "at_risk" for f in fs),
            "not_assessed": len(fs) - len(checked),
            "first_look": [{"name": f["name"] or f["kind"].replace("_", " "), "kind": f["kind"],
                            "status": f["status"], "reasons": f["reasons"], "lon": f["lon"], "lat": f["lat"]}
                           for f in sorted(fs, key=lambda f: (f["status"] != "disrupted", not f["critical"],
                                                               f["status"] != "at_risk"))[:5]
                           if f["status"] in ("disrupted", "at_risk")],
        })
    tr = _transportation(access_summary)
    if tr:
        for ll in lifelines:
            if ll["lifeline"] == "transportation":
                ll.update(tr)
    if not any(f["lifeline"] == "hazardous_materials" for f in out):
        for ll in lifelines:
            if ll["lifeline"] == "hazardous_materials":
                ll["note"] = "No hazardous-materials facility found in EPA's registries for this box."
    return {"facilities": out, "lifelines": lifelines,
            "status_rule": "red: a critical facility disrupted; yellow: any facility disrupted or at risk; green: facilities found, none flagged; grey: none found or none checked. "
                           "Estimated from open data: confirm with owners and utilities."}
