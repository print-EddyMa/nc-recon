"""Build every response product for an assessed area.

`python -m terratriage.ops.response --area swannanoa [--skip landing]`

Writes data/output/ops/<area>.response.json (summary + per-product results)
and <area>.response.layers.json (map layers: roads by status, facilities, landing
zone candidates, sectors, cut-off clusters). Each product runs on its own: a
source being down costs that product, never the others.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from .. import DISCLAIMER
from ..provenance import utc_now
from . import OPS_OUT, AreaRun, load_area, pad_bbox

PRODUCTS = ("access", "resources", "landing", "money", "sectors")


def _hazard_geoms(ar: AreaRun, box) -> tuple[dict[str, Any], list, list[str]]:
    """Footprint geometries (lon/lat) for this event over the padded box."""
    from ..collect import hazard_footprints as hf

    geoms: dict[str, Any] = {}
    landslide_polys: list = []
    notes: list[str] = []
    ev = ar.event
    if "wildfire" in ev.hazards:
        try:
            fp = hf.fire_perimeters(box, ev.incident_begin)
            if fp is not None:
                geoms["wildfire"] = fp.geom
        except Exception as ex:  # noqa: BLE001
            notes.append(f"fire perimeters unavailable: {str(ex)[:120]}")
    storm = getattr(ev, "landslide_storm", None)
    if "landslide" in ev.hazards and storm:
        try:
            fp = hf.landslides_ncgs(box, storm)
            if fp is not None:
                geoms["landslide"] = fp.geom
                landslide_polys = [f["_geom"] for f in fp.features]
        except Exception as ex:  # noqa: BLE001
            notes.append(f"landslide inventory unavailable: {str(ex)[:120]}")
    return geoms, landslide_polys, notes


def _displaced(area: str) -> float | None:
    p = os.path.join(OPS_OUT, f"{area}.impact.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        d = json.load(fh)
    return (d.get("expected_displaced") or {}).get("median")


def build(area: str, *, skip: tuple[str, ...] = (), write: bool = True) -> dict[str, Any]:
    from ..collect import osm
    from . import access, landing, money, resources, sectors, sources, water

    t0 = time.time()
    ar = load_area(area)
    box = pad_bbox(ar.bbox, 6.0)
    errors: dict[str, str] = {}
    timings: dict[str, float] = {}
    hz_geoms, landslide_polys, notes = _hazard_geoms(ar, box)

    facilities: list[dict] = []
    try:
        facilities = osm.resources(box)
    except Exception as ex:  # noqa: BLE001
        errors["resources"] = f"OpenStreetMap unavailable: {str(ex)[:160]}"
    official, off_err = sources.facilities(box)
    for k, v in off_err.items():
        notes.append(f"{sources.SOURCES[k]['name']} unavailable: {v}")
    facilities = _merge(official, facilities)

    acc = None
    if "access" not in skip:
        t = time.time()
        try:
            acc = access.analyse(ar, landslide_polys_ll=landslide_polys, resources=facilities,
                                 points=[{"id": f["id"], "lon": f["lon"], "lat": f["lat"]} for f in facilities])
        except Exception as ex:  # noqa: BLE001
            errors["access"] = str(ex)[:200]
        timings["access"] = round(time.time() - t, 1)

    res = None
    if "resources" not in skip and facilities:
        res = resources.assess(ar, facilities, (acc or {}).get("per_point"), hz_geoms, acc)

    lz = None
    if "landing" not in skip:
        t = time.time()
        try:
            lz = landing.candidates(ar, targets=landing.targets_from(ar, acc))
        except Exception as ex:  # noqa: BLE001
            errors["landing"] = str(ex)[:200]
        timings["landing"] = round(time.time() - t, 1)

    wat = None
    try:
        wat = water.assess(ar, sources.water_systems(ar.bbox), (res or {}).get("facilities"))
        _water_lifeline(res, wat)
    except Exception as ex:  # noqa: BLE001
        errors["water"] = str(ex)[:200]
    try:
        power = sources.outages(box, ar.event.incident_begin)
    except Exception as ex:  # noqa: BLE001
        power = {"active": None, "note": f"ODIN unavailable: {str(ex)[:120]}"}

    cash = None
    if "money" not in skip:
        try:
            vals = {}
            try:
                vals = money.nsi_values(ar.bbox)
            except Exception as ex:  # noqa: BLE001
                notes.append(f"USACE NSI values unavailable: {str(ex)[:120]}")
            cash = money.estimate(ar, vals)
        except Exception as ex:  # noqa: BLE001
            errors["money"] = str(ex)[:200]

    sec = sectors.sectors(ar, (acc or {}).get("per_building"))
    cut_off = ((acc or {}).get("scenarios") or {}).get("known_blocks", {}).get("isolated_people_est", 0)
    need = sectors.needs(_displaced(area), float(cut_off or 0))

    assessed = len(ar.features)
    not_assessed = ar.not_assessed
    coverage = round(assessed / max(1, assessed + not_assessed), 3)
    flood = any(h in ("riverine_flood", "flash_flood", "coastal_surge") for h in ar.event.hazards)
    summary = {
        "area": area, "event": ar.event.id, "hazards": list(ar.event.hazards),
        "buildings_assessed": assessed,
        "buildings_not_assessed": not_assessed,
        "coverage": coverage,
        "reading_notes": (["Interior flood depth does not show from above: flood calls between Minor and Major "
                           "are candidates for field checks."] if flood else []) + [
            "Buildings not assessed are unknown (grey), never undamaged."],
        "major_or_destroyed_expected": round(sum(s["major_or_destroyed_expected"] for s in sec), 1),
        "people_in_severe_expected": round(sum(s["people_in_severe_expected"] for s in sec)),
        "cut_off": (acc or {}).get("scenarios"),
        "lifelines": [{"lifeline": x["lifeline"], "label": x["label"], "status": x["status"]}
                      for x in (res or {}).get("lifelines", [])],
        "landing_zone_candidates": len((lz or {}).get("candidates", [])),
        "water_systems_at_risk": sum(s["status"] == "at_risk" for s in (wat or {}).get("systems", [])),
        "private_well_homes": ((wat or {}).get("private_wells") or {}).get("residential_buildings"),
        "building_loss_usd": (cash or {}).get("building_loss_usd"),
        "debris_cy": (cash or {}).get("debris_cy"),
        "top_sectors": [{k: s[k] for k in ("priority", "usng_1km", "major_or_destroyed_expected",
                                           "people_in_severe_expected", "cut_off_people")} for s in sec[:5]],
    }
    out = {
        "schema": "groma.response/1", "area": area, "run_id": ar.run.get("run_id"),
        "generated_utc": utc_now(), "disclaimer": DISCLAIMER,
        "summary": summary,
        "access": {**{k: v for k, v in (acc or {}).items() if k not in ("per_building", "per_point", "layer_roads")},
                   "isolated_ids": _isolated_ids(acc)} if acc else None,
        "resources": {"lifelines": (res or {}).get("lifelines"), "status_rule": (res or {}).get("status_rule"),
                      "facilities": [{k: f[k] for k in ("id", "kind", "lifeline", "name", "lon", "lat", "status",
                                                        "reasons", "critical", "min_to_hospital")}
                                     for f in (res or {}).get("facilities", [])]} if res else None,
        "landing": lz, "money": cash, "sectors": sec, "needs": need, "water": wat, "power": power,
        "sources": {**sources.SOURCES, "osm": {"name": "OpenStreetMap via Overpass", "license": "ODbL 1.0"}},
        "notes": notes, "errors": errors, "timings_sec": {**timings, "total": round(time.time() - t0, 1)},
    }
    layers = _layers(acc, res, lz, sec)
    if write:
        _write(os.path.join(OPS_OUT, f"{area}.response.json"), out)
        _write(os.path.join(OPS_OUT, f"{area}.response.layers.json"), layers)
    return out


def _merge(official: list[dict], osm_items: list[dict], same_m: float = 150.0) -> list[dict]:
    """Official records first; an OSM record of the same kind within 150 m of
    one is the same place and is dropped."""
    import math

    out = list(official)
    for o in osm_items:
        dup = False
        for f in official:
            if f["kind"] != o["kind"]:
                continue
            dx = (f["lon"] - o["lon"]) * 111320 * math.cos(math.radians(o["lat"]))
            dy = (f["lat"] - o["lat"]) * 110540
            if math.hypot(dx, dy) <= same_m:
                dup = True
                break
        if not dup:
            out.append({**o, "source": "OpenStreetMap"})
    return out


def _water_lifeline(res: dict | None, wat: dict | None) -> None:
    """Water systems lifeline from the water product: yellow when a system
    serving damage is at risk or homes on private wells sit in a flood event."""
    if not res or not wat:
        return
    at_risk = [s for s in wat["systems"] if s["status"] == "at_risk"]
    for ll in res["lifelines"]:
        if ll["lifeline"] != "water_systems":
            continue
        if at_risk and ll["status"] in ("grey", "green"):
            ll["status"] = "yellow"
        ll["systems_at_risk"] = [s["name"] for s in at_risk][:5]
        ll["private_well_homes"] = wat["private_wells"]["residential_buildings"]


def _feature(geom, props):
    return {"type": "Feature", "geometry": geom, "properties": props}


def _isolated_ids(acc: dict[str, Any]) -> dict[str, list[str]]:
    """Per scenario, the buildings with no road out (for FEMA's count and list
    of inaccessible homes in the IDA packet)."""
    out: dict[str, list[str]] = {}
    for nid, rec in (acc.get("per_building") or {}).items():
        for scen, r in rec.items():
            if (r or {}).get("access") == "isolated":
                out.setdefault(scen, []).append(nid)
    return {k: sorted(v) for k, v in out.items()}


def _layers(acc, res, lz, sec) -> dict[str, Any]:
    feats = []
    for f in (acc or {}).get("layer_roads", []):
        if f["properties"]["status"] != "open":
            feats.append({**f, "properties": {**f["properties"], "layer": "road"}})
    for c in (acc or {}).get("isolated_clusters", []):
        feats.append(_feature({"type": "Point", "coordinates": c["center"]}, {**c, "layer": "cut_off_cluster"}))
    for f in (res or {}).get("facilities", []):
        feats.append(_feature({"type": "Point", "coordinates": [f["lon"], f["lat"]]},
                              {"layer": "facility", **{k: f[k] for k in ("id", "kind", "lifeline", "name", "status",
                                                                         "critical")}}))
    for c in (lz or {}).get("candidates", []):
        feats.append(_feature({"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                              {"layer": "landing_zone", **{k: v for k, v in c.items() if k not in ("lon", "lat")}}))
    for s in sec:
        feats.append(_feature({"type": "Point", "coordinates": s["center"]}, {"layer": "sector", **s}))
    return {"type": "FeatureCollection", "features": feats}


def _write(path: str, obj: Any) -> None:
    """Atomic: a reader during a rebuild sees the old file or the new one."""
    import tempfile

    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m terratriage.ops.response",
                                 description="Response products for an assessed area")
    ap.add_argument("--area", required=True)
    ap.add_argument("--skip", nargs="*", default=[], choices=PRODUCTS)
    a = ap.parse_args(argv)
    r = build(a.area, skip=tuple(a.skip))
    print(json.dumps(r["summary"], indent=1))
    if r["errors"]:
        print("errors:", json.dumps(r["errors"], indent=1))
