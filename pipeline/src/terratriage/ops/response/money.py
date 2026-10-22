"""Money questions after the event: losses, debris, and FEMA's thresholds.

Building losses (planning ranges, not appraisals)
  value      USACE National Structure Inventory structure and contents values
             (val_struct, val_cont) where the assessment matched one
  ratio      the damage share each level stands for, as CAL FIRE's damage
             inspection defines the levels: Affected 1-10%, Minor 10-25%,
             Major 25-50%, Destroyed over 50% (taken as 50-100%)
  expected   sum over buildings of P(level) x value x ratio, at the low and
             high end of each range

Debris (FEMA 329, Debris Estimating Field Guide)
  destroyed home      length x width (ft) x stories x 0.20 x vegetation
                      multiplier (1.1 light to 1.5 heavy) cubic yards
  manufactured home   290 CY single-wide, 415 CY double-wide (by footprint size)
  flood, Major        25-30 CY of household debris put to the curb (slab
                      house; 45-50 with a basement)
  FEMA gives no coefficient for other levels, so none is invented here.

Public Assistance threshold
  countywide per-capita indicator x county population (Census Vintage 2024
  estimates); FY2025 $4.72 (statewide $1.89), FY2026 $4.86 (statewide $1.94),
  by the fiscal year the incident began in. The PA threshold counts public
  costs (debris removal, roads, utilities, public buildings); building losses
  here are mostly private, so the threshold is context for the debris line,
  not a comparison with the loss figure.
"""
from __future__ import annotations

import csv
import io
import urllib.request
from datetime import date
from typing import Any

from ..collect.base import USER_AGENT, DiskCache
from . import AreaRun

RATIO = {"no_damage": (0.0, 0.0), "affected": (0.01, 0.10), "minor": (0.10, 0.25),
         "major": (0.25, 0.50), "destroyed": (0.50, 1.00)}
SQFT_PER_M2 = 10.7639
VM = (1.1, 1.5)
FLOOD_MAJOR_CY = (25.0, 30.0)
MH_SINGLE_CY, MH_DOUBLE_CY = 290.0, 415.0
MH_DOUBLE_MIN_M2 = 100.0     # footprints this large are taken as double-wide
# FEMA PA per-capita indicators, by federal fiscal year of the incident start
PA_INDICATOR = {2025: {"statewide": 1.89, "countywide": 4.72},
                2026: {"statewide": 1.94, "countywide": 4.86}}
PA_SOURCE = "https://www.fema.gov/assistance/public/applicants/per-capita-impact-indicator"
CENSUS = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/counties/totals/co-est2024-alldata.csv"


def fiscal_year(d: date) -> int:
    return d.year + 1 if d.month >= 10 else d.year


def county_population(state_name: str, county: str) -> int | None:
    cache = DiskCache("census")
    table = cache.get("co_est2024", 90 * 86400)
    if table is None:
        req = urllib.request.Request(CENSUS, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
            text = r.read().decode("latin-1")
        table = {}
        for row in csv.DictReader(io.StringIO(text)):
            if row["SUMLEV"] == "050":
                table[f"{row['STNAME']}|{row['CTYNAME']}".lower()] = int(row["POPESTIMATE2024"])
        cache.put("co_est2024", table)
    name = county if county.lower().endswith(("county", "parish", "borough")) else f"{county} County"
    return table.get(f"{state_name}|{name}".lower())


def _probs(p: dict[str, Any]) -> dict[str, float]:
    pr = p.get("damage_probs") or {}
    if pr:
        return {k: float(pr.get(k) or 0.0) for k in RATIO}
    lvl = p.get("damage_level")
    return {k: float(k == lvl) for k in RATIO}


def nsi_values(bbox) -> dict[int, tuple[float, float]]:
    """fd_id -> (structure value, contents value) from USACE NSI (cached)."""
    from ..collect.nsi import NSI

    layer = NSI().fetch(bbox)
    out = {}
    for f in layer.data["features"]:
        p = f.get("properties") or {}
        if p.get("fd_id") is not None and p.get("val_struct") is not None:
            out[int(p["fd_id"])] = (float(p["val_struct"]), float(p.get("val_cont") or 0.0))
    return out


def estimate(ar: AreaRun, values: dict[int, tuple[float, float]] | None = None) -> dict[str, Any]:
    flood = any(h in ("riverine_flood", "flash_flood", "coastal_surge") for h in ar.event.hazards)
    lo = hi = 0.0
    valued = unvalued = 0
    debris_lo = debris_hi = 0.0
    exp_destroyed = exp_major_homes = 0.0
    per_level_value = {k: 0.0 for k in RATIO}
    for f in ar.features:
        p = f["properties"]
        pr = _probs(p)
        fd = (p.get("source_ids") or {}).get("nsi_fd_id")
        vs, vc = (values or {}).get(int(fd), (None, None)) if fd is not None else (None, None)
        if vs is None:
            unvalued += 1
        else:
            valued += 1
            v = float(vs) + float(vc or 0.0)
            for k, (a, b) in RATIO.items():
                lo += pr[k] * v * a
                hi += pr[k] * v * b
                per_level_value[k] += pr[k] * v
        # debris
        area_ft2 = float(p.get("area_m2") or 0.0) * SQFT_PER_M2
        stories = float(p.get("stories") or 1.0)
        manufactured = bool((p.get("flags") or {}).get("manufactured_home"))
        residential = bool((p.get("flags") or {}).get("residential"))
        if manufactured:
            cy = MH_DOUBLE_CY if float(p.get("area_m2") or 0) >= MH_DOUBLE_MIN_M2 else MH_SINGLE_CY
            d_lo = d_hi = cy
        else:
            d_lo, d_hi = area_ft2 * stories * 0.20 * VM[0], area_ft2 * stories * 0.20 * VM[1]
        debris_lo += pr["destroyed"] * d_lo
        debris_hi += pr["destroyed"] * d_hi
        exp_destroyed += pr["destroyed"]
        if flood and residential:
            debris_lo += pr["major"] * FLOOD_MAJOR_CY[0]
            debris_hi += pr["major"] * FLOOD_MAJOR_CY[1]
        if residential or manufactured:
            exp_major_homes += pr["major"] + pr["destroyed"]

    fy = fiscal_year(ar.event.incident_begin)
    ind = PA_INDICATOR.get(fy)
    county = (ar.run.get("aoi") or {}).get("county") or ""
    from ..plan.bootstrap import STATES

    pop = None
    try:
        pop = county_population(STATES.get(ar.event.state, ""), county) if county else None
    except Exception:  # noqa: BLE001 - threshold context is optional
        pop = None
    threshold = None
    if ind and pop:
        threshold = {"fiscal_year": fy, "county": county, "county_population_2024": pop,
                     "countywide_per_capita": ind["countywide"],
                     "county_threshold_usd": round(pop * ind["countywide"]),
                     "statewide_per_capita": ind["statewide"], "source": PA_SOURCE}
    return {
        "building_loss_usd": {"low": round(lo, -3), "high": round(hi, -3),
                              "buildings_valued": valued, "buildings_without_value": unvalued,
                              "note": "Structure plus contents value from USACE NSI where matched; buildings "
                                      "without a matched value are left out, so the range is low by their share."},
        "homes_major_or_destroyed_expected": round(exp_major_homes, 1),
        "debris_cy": {"low": round(debris_lo, -1), "high": round(debris_hi, -1),
                      "destroyed_expected": round(exp_destroyed, 1),
                      "method": "FEMA 329: destroyed homes L x W x stories x 0.20 x VM (1.1-1.5); manufactured "
                                "homes 290 or 415 CY; flood events add 25-30 CY per home at Major. No FEMA "
                                "coefficient exists for other levels, so they add nothing."},
        "public_assistance_threshold": threshold or {
            "fiscal_year": fy, "note": "per-capita indicator for this fiscal year or county population not "
                                       "available here; see " + PA_SOURCE},
        "ratios": {k: list(v) for k, v in RATIO.items()},
        "ratio_source": "CAL FIRE damage inspection level definitions (Affected 1-10%, Minor 10-25%, "
                        "Major 25-50%, Destroyed over 50%)",
    }
