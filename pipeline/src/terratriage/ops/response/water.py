"""Drinking water after the event: which systems serve the damage, who is on a well.

  systems        EPA community water system service areas that contain
                 assessed buildings: buildings inside, expected Major or
                 Destroyed inside, people served, and the system's own
                 treatment or wastewater facilities flagged nearby
  private wells  residential buildings inside no community system's service
                 area are likely on private wells. After a flood, wells and
                 septic systems need testing before use (more than 300,000
                 people near Helene's flooded areas in western NC used wells)

A system is "at risk" when assessed damage inside its area is high, a water
or wastewater facility serving the area is flagged, or the event floods.
This is where to call first, not a boil-water determination: only the
system and the state drinking water program can issue or lift a notice.
"""
from __future__ import annotations

from typing import Any

from shapely.geometry import Point
from shapely.strtree import STRtree

from . import AreaRun, occupants, p_severe

SEVERE_SHARE = 0.05       # share of assessed buildings likely Major or Destroyed


def assess(ar: AreaRun, systems: list[dict[str, Any]], facilities: list[dict[str, Any]] | None) -> dict[str, Any]:
    flood = any(h in ("riverine_flood", "flash_flood", "coastal_surge") for h in ar.event.hazards)
    geoms = [s["_geom"] for s in systems]
    tree = STRtree(geoms) if geoms else None
    per = [{"buildings": 0, "severe": 0.0, "people": 0.0} for _ in systems]
    wells = {"residential_buildings": 0, "people_est": 0.0, "major_or_destroyed_expected": 0.0}
    for f in ar.features:
        p = f["properties"]
        pt = Point(*p["centroid"])
        hit = []
        if tree is not None:
            hit = [int(i) for i in tree.query(pt) if geoms[int(i)].contains(pt)]
        for i in hit:
            per[i]["buildings"] += 1
            per[i]["severe"] += p_severe(p)
            per[i]["people"] += occupants(p)
        if not hit and (p.get("flags") or {}).get("residential"):
            wells["residential_buildings"] += 1
            wells["people_est"] += occupants(p)
            wells["major_or_destroyed_expected"] += p_severe(p)
    water_fac = [x for x in (facilities or [])
                 if x.get("kind") in ("water_treatment", "wastewater_treatment", "wastewater_discharger", "water_tower")]
    out = []
    for s, c in zip(systems, per):
        if not c["buildings"]:
            continue
        flagged = [x for x in water_fac if x.get("status") in ("disrupted", "at_risk")
                   and s["_geom"].buffer(0.01).contains(Point(x["lon"], x["lat"]))]
        share = c["severe"] / c["buildings"]
        reasons = []
        if share >= SEVERE_SHARE:
            reasons.append(f"{share:.0%} of assessed buildings inside likely Major or Destroyed (line breaks likely)")
        if flagged:
            reasons.append(f"{len(flagged)} water or wastewater facility flagged nearby")
        if flood:
            reasons.append("flood event: intakes, wells and treatment can be contaminated")
        out.append({"pwsid": s["pwsid"], "name": s["name"], "population_served": s["population_served"],
                    "boundary": (s.get("boundary") or "").strip() or "not verified",
                    "buildings_assessed_inside": c["buildings"],
                    "major_or_destroyed_expected": round(c["severe"], 1),
                    "people_in_assessed_buildings": round(c["people"]),
                    "status": "at_risk" if reasons else "no_evidence", "reasons": reasons,
                    "flagged_facilities": [{"name": x.get("name"), "kind": x["kind"], "status": x["status"]}
                                           for x in flagged][:10]})
    out.sort(key=lambda r: (r["status"] != "at_risk", -r["major_or_destroyed_expected"]))
    wells = {k: round(v, 1) if isinstance(v, float) else v for k, v in wells.items()}
    wells["advice"] = ("Likely on private wells: after a flood, test wells and septic systems before use; "
                       "the county health department runs well testing.") if flood else \
        "Likely on private wells (no community system's service area covers them)."
    return {"systems": out, "private_wells": wells,
            "note": "EPA service areas are partly modelled; only the system and the state drinking water "
                    "program issue or lift boil-water notices."}
