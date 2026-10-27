"""The Groma Index: one public, preliminary damage summary per assessed area.

`GET /ops/index` lists every area; `GET /ops/index/<area>` is one area's record
(schema `groma.index/1`). Built for apps, newsrooms, aid groups and AI agents
that need a number within days of a declaration: counts by FEMA level with an
80% range, roads cut, people cut off, debris and building loss, the imagery
dates and what has been validated. Nothing building-level: no addresses, no
coordinates finer than the area, no count below the public suppression
threshold. TEST areas are left out (they are held out for evaluation).
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

from .. import DISCLAIMER, OPS_OUT
from ..analyze.classes import FEMA, FEMA_LABEL
from .aggregate import SUPPRESS

SCHEMA = "groma.index/1"
Z80 = 1.2816


def _load(name: str) -> Any:
    p = os.path.join(OPS_OUT, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _img(run: dict[str, Any], role: str) -> str | None:
    for im in ((run.get("provenance") or {}).get("imagery") or []):
        if im.get("role") == role:
            return (im.get("acquired_utc") or "")[:10] or im.get("date_label") or im.get("dataset_version")
    return None


def _role(area: str, fc: dict[str, Any]) -> str:
    from ..truth import area_role

    return area_role(area, fc)


def _range(ps: list[float]) -> tuple[float, list[int]]:
    """Expected count and an 80% range for a sum of independent Bernoullis
    (normal approximation to the Poisson-binomial)."""
    mu = sum(ps)
    sd = math.sqrt(sum(p * (1 - p) for p in ps))
    return round(mu, 1), [max(0, math.floor(mu - Z80 * sd)), math.ceil(mu + Z80 * sd)]


def _suppress(v: Any) -> Any:
    return None if isinstance(v, (int, float)) and 0 < v < SUPPRESS else v


def record(area: str) -> dict[str, Any] | None:
    from .exports import state_name
    from .ida import _hazards, validation_note

    fc = _load(f"{area}.geojson")
    if fc is None:
        return None
    run = fc["properties"]
    role = _role(area, fc)
    if role == "TEST":
        return None
    rsp = _load(f"{area}.response.json") or {}
    summ = rsp.get("summary") or {}
    probs = [f["properties"].get("damage_probs") or {} for f in fc["features"]]
    probs = [p for p in probs if p]
    # the run's own expected counts and 80% ranges, so the public figure is the
    # one the operators see; recomputed only for runs that did not record them
    dmg: dict[str, Any] = {}
    exp_run = run.get("expected_counts") or {}
    rng = run.get("expected_counts_80pct") or {}
    for c in FEMA:
        exp, r80 = _range([p.get(c) or 0.0 for p in probs])
        dmg[c] = {"label": FEMA_LABEL[c], "expected": round(exp_run.get(c, exp), 1), "range_80": rng.get(c) or r80,
                  "most_likely": _suppress((run.get("counts") or {}).get(c))}
    if rng.get("major") and rng.get("destroyed"):
        sev_exp = round(dmg["major"]["expected"] + dmg["destroyed"]["expected"], 1)
        sev_r = [rng["major"][0] + rng["destroyed"][0], rng["major"][1] + rng["destroyed"][1]]
    else:
        sev_exp, sev_r = _range([(p.get("major") or 0) + (p.get("destroyed") or 0) for p in probs])
    acc = rsp.get("access") or {}
    roads = acc.get("roads") or {}
    cut = summ.get("cut_off") or {}
    ev = run.get("event") or {}
    aoi = run.get("aoi") or {}
    hazards = _hazards(fc, rsp)
    na = run.get("not_assessed") or {}
    return {
        "schema": SCHEMA, "area": area, "name": aoi.get("name") or area.replace("_", " ").title(),
        "status": "preliminary", "role": role,
        "event": {"id": ev.get("id"), "name": ev.get("name"), "declarations": ev.get("declarations") or [],
                  "incident_begin": ev.get("incident_begin")},
        "state": state_name(fc), "county": aoi.get("county"), "hazards": hazards,
        "assessed_utc": run.get("generated_utc"), "run_id": run.get("run_id"),
        "imagery": {"before": _img(run, "pre"), "after": _img(run, "post")},
        "buildings": {"assessed": len(probs), "not_assessed": na.get("total") if isinstance(na, dict) else na,
                      "needs_review": run.get("n_needs_review")},
        "damage": dmg,
        "major_or_destroyed": {"expected": sev_exp, "range_80": sev_r},
        "access": {"road_segments_blocked": roads.get("blocked"), "road_segments_debris_possible": roads.get("debris"),
                   "bridges_unverified": roads.get("bridge"),
                   "people_cut_off": {"known_blocks": _suppress((cut.get("known_blocks") or {}).get("isolated_people_est")),
                                      "if_debris_blocks_roads": _suppress(
                                          (cut.get("plus_debris") or {}).get("isolated_people_est"))}}
        if acc else None,
        "debris_cubic_yards": {k: (summ.get("debris_cy") or {}).get(k) for k in ("low", "high")}
        if summ.get("debris_cy") else None,
        "building_loss_usd": {k: (summ.get("building_loss_usd") or {}).get(k) for k in ("low", "high")}
        if summ.get("building_loss_usd") else None,
        "validation": validation_note(hazards, "public"),
        "method": "Per-building probabilities of FEMA's five damage levels from public before and after imagery, "
                  "building footprints and lidar; expected counts are sums of probabilities with an 80% range. "
                  "Roads from OpenStreetMap. Preliminary until verified on the ground.",
        "public_tracts": f"/ops/areas/{area}/public.geojson",
        "disclaimer": DISCLAIMER,
    }


def listing() -> dict[str, Any]:
    out = []
    if os.path.isdir(OPS_OUT):
        for f in sorted(os.listdir(OPS_OUT)):
            stem = f[:-8]
            if not f.endswith(".geojson") or "." in stem:
                continue
            r = record(stem)
            if r:
                out.append({k: r[k] for k in ("area", "name", "status", "event", "state", "county", "hazards",
                                              "assessed_utc", "buildings", "major_or_destroyed")})
    return {"schema": SCHEMA, "areas": out, "disclaimer": DISCLAIMER}
