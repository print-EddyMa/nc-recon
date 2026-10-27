"""Search and assignment sectors on the US National Grid, plus logistics needs.

Sectors are 1 km USNG squares (FEMA's standard grid for land operations,
FEMA Directive 092-5). Each square carries what a planner assigns by: how
many buildings are likely Major or Destroyed, how many people were likely
inside at night, how many are cut off by road, and the share of buildings
still uncertain (sent to review). Squares are ranked by people in likely
Major or Destroyed buildings, then by those cut off.

Logistics needs use FEMA's generic planning factors for a 72-96 hour
requirement: 3 litres of water and 2 meals per person per day; shelter at 40
square feet per person (20 for an evacuation shelter); distribution points by
type: Type I about 20,000 people a day, Type II 10,000, Type III 5,000 (FEMA
distribution management guidance as reported in county training material).
"""
from __future__ import annotations

import math
from typing import Any

from . import AreaRun, occupants, p_severe

WATER_L, MEALS = 3.0, 2.0
SHELTER_FT2 = (40.0, 20.0)
POD = (("Type I", 20000), ("Type II", 10000), ("Type III", 5000))


def _cell(usng_1m: str | None) -> str | None:
    """'17S LV 73928 40073' -> '17S LV 73 40' (the 1 km square)."""
    if not usng_1m:
        return None
    parts = usng_1m.split()
    if len(parts) != 4:
        return None
    return f"{parts[0]} {parts[1]} {parts[2][:2]} {parts[3][:2]}"


def sectors(ar: AreaRun, per_building_access: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cells: dict[str, dict[str, Any]] = {}
    for f in ar.features:
        p = f["properties"]
        c = _cell(p.get("usng_1m"))
        if c is None:
            continue
        s = cells.setdefault(c, {"usng_1km": c, "buildings": 0, "major_or_destroyed_expected": 0.0,
                                 "people_in_severe_expected": 0.0, "people": 0.0, "cut_off_buildings": 0,
                                 "cut_off_people": 0.0, "needs_review": 0, "_x": [], "_y": []})
        ps = p_severe(p)
        occ = occupants(p)
        s["buildings"] += 1
        s["major_or_destroyed_expected"] += ps
        s["people_in_severe_expected"] += ps * occ
        s["people"] += occ
        s["needs_review"] += bool(p.get("needs_review"))
        acc = ((per_building_access or {}).get(p.get("ncr_id")) or {}).get("known_blocks") or {}
        if acc.get("access") == "isolated":
            s["cut_off_buildings"] += 1
            s["cut_off_people"] += occ
        s["_x"].append(p["centroid"][0])
        s["_y"].append(p["centroid"][1])
    out = []
    for s in cells.values():
        xs, ys = s.pop("_x"), s.pop("_y")
        s["center"] = [round(sum(xs) / len(xs), 6), round(sum(ys) / len(ys), 6)]
        for k in ("major_or_destroyed_expected", "people_in_severe_expected", "people", "cut_off_people"):
            s[k] = round(s[k], 1)
        s["review_share"] = round(s["needs_review"] / s["buildings"], 2)
        out.append(s)
    out.sort(key=lambda s: (-s["people_in_severe_expected"], -s["cut_off_people"], -s["major_or_destroyed_expected"]))
    for i, s in enumerate(out, 1):
        s["priority"] = i
    return out


def needs(people_displaced: float | None, people_cut_off: float) -> dict[str, Any]:
    """Daily commodities and shelter for people displaced plus people cut off."""
    served = (people_displaced or 0.0) + people_cut_off
    pods = []
    rem = served
    for name, cap in POD:
        if rem <= 0:
            break
        n = int(rem // cap)
        if name == POD[-1][0]:
            n = math.ceil(rem / cap)
        if n:
            pods.append({"type": name, "count": n, "people_per_day_each": cap})
            rem -= n * cap
    return {
        "people_served": round(served),
        "people_displaced_expected": None if people_displaced is None else round(people_displaced),
        "people_cut_off": round(people_cut_off),
        "water_litres_per_day": round(served * WATER_L),
        "meals_per_day": round(served * MEALS),
        "shelter_ft2_standard": round((people_displaced or 0.0) * SHELTER_FT2[0]),
        "shelter_ft2_evacuation": round((people_displaced or 0.0) * SHELTER_FT2[1]),
        "distribution_points": pods,
        "factors": {"water_litres_per_person_day": WATER_L, "meals_per_person_day": MEALS,
                    "shelter_ft2_per_person": {"standard": SHELTER_FT2[0], "evacuation": SHELTER_FT2[1]},
                    "planning_window_hours": "72-96"},
        "note": "Generic FEMA planning factors; adjust for medical needs, infants, pets and local supply.",
    }
