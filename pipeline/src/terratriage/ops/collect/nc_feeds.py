"""Server-side versions of the Conditions-map feeds that browsers cannot read
directly (no CORS) or that need shaping: NCDOT DriveNC closures/incidents and
cameras, NHC active Atlantic storms, NC FIMAN gauges, Duke Energy outages by
county and FEMA open shelters. Output matches the web's NCPointFC / NCGeomFC
shapes and the committed snapshots written by
web/scripts/refresh_nc_snapshots.mjs, so the browser can use either. Fixed
upstream URLs only (no user-supplied URLs).
"""
from __future__ import annotations

import time

from ..geodesy import NC_BBOX
from .base import SchemaError, http_json

DRIVENC = "https://www.drivenc.gov/map/mapIcons/{kind}"
NHC = "https://www.nhc.noaa.gov/CurrentStorms.json"
# NC Emergency Management's FIMAN gauge layer (NCEM, NCDOT, county and USGS
# gauges with FIMAN flood categories). Public ArcGIS service, no documented
# terms: checked 2026-10-07, 882 records, 791 in service. The description
# literally reads "Test Gages NC FIMAN"; the operator is fimanhelp@ncdps.gov.
FIMAN = "https://spartagis.ncem.org/arcgis/rest/services/FIMAN/GAGES_ALL/MapServer/0/query"
FIMAN_CONDITION = {0: "Normal", 1: "Near flooding", 2: "Minor flooding", 3: "Moderate flooding", 4: "Major flooding"}
# Duke Energy "Distribution Outages for public use": county polygons with
# customers served / out, refreshed about every 20 minutes. Duke Energy
# Carolinas and Progress territory only (no co-ops, municipals or Dominion).
DUKE = "https://services3.arcgis.com/oX5r75R7mapdoI2F/ArcGIS/rest/services/Outages/FeatureServer/1/query"
# FEMA ESF6 open shelters (synchronised daily with the American Red Cross
# shelter database, incremental checks every 20 minutes).
SHELTERS = "https://gis.fema.gov/arcgis/rest/services/NSS/OpenShelters/FeatureServer/0/query"
NHC_CLASS = {"TD": "Tropical Depression", "TS": "Tropical Storm", "HU": "Hurricane",
             "STD": "Subtropical Depression", "STS": "Subtropical Storm",
             "PTC": "Post-tropical Cyclone", "PC": "Potential Tropical Cyclone"}


def _in_nc(lon: float, lat: float) -> bool:
    w, s, e, n = NC_BBOX
    return w - 0.3 <= lon <= e + 0.3 and s - 0.3 <= lat <= n + 0.3


def _icons(kind: str) -> list[dict]:
    d = http_json(DRIVENC.format(kind=kind), headers={"X-Requested-With": "XMLHttpRequest"}, timeout=30)
    items = d.get("item2") if isinstance(d, dict) else None
    if not isinstance(items, list):
        raise SchemaError(f"DriveNC {kind}: unexpected response")
    return items


def _icons_fc(items: list[dict], layer: str, prefix: str, seen: set[str]) -> list[dict]:
    feats = []
    for it in items:
        loc = it.get("location")
        if not isinstance(loc, list) or len(loc) < 2:
            continue
        lat, lon = loc[0], loc[1]
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)) or not _in_nc(lon, lat):
            continue
        fid = f"{layer}-{it.get('itemId')}"
        if fid in seen:
            continue
        seen.add(fid)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                      "properties": {"id": fid, "layer": layer,
                                     "title": (it.get("title") or "").strip() or f"{prefix} {it.get('itemId')}",
                                     "severity": 3 if layer == "closure" else 0, "category": prefix,
                                     "url": f"https://www.drivenc.gov/?type={layer}&id={it.get('itemId')}"}})
    return feats


def drivenc_closures() -> dict:
    seen: set[str] = set()
    feats = _icons_fc(_icons("Closures"), "closure", "Road closure", seen)
    try:
        feats += _icons_fc(_icons("Incidents"), "closure", "Incident", seen)
    except Exception:  # noqa: BLE001 - closures alone are still useful
        pass
    return {"type": "FeatureCollection", "generated": int(time.time() * 1000), "features": feats}


def drivenc_cameras() -> dict:
    feats = _icons_fc(_icons("Cameras"), "camera", "Camera", set())
    return {"type": "FeatureCollection", "generated": int(time.time() * 1000), "features": feats}


def nhc_storms() -> dict:
    d = http_json(NHC, timeout=30)
    feats = []
    for s in d.get("activeStorms") or []:
        if not str(s.get("id", "")).lower().startswith("al"):
            continue
        try:
            lon, lat = float(s["longitudeNumeric"]), float(s["latitudeNumeric"])
        except (KeyError, TypeError, ValueError):
            continue
        cls = NHC_CLASS.get(s.get("classification"), s.get("classification") or "Cyclone")
        try:
            kt = float(s.get("intensity") or 0)
        except (TypeError, ValueError):
            kt = 0.0
        sev = 3 if kt >= 64 else 2 if kt >= 34 else 1
        adv = (s.get("publicAdvisory") or {})
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                      "properties": {"id": f"nhc-{s.get('id')}", "layer": "storm",
                                     "title": f"{cls} {s.get('name')}",
                                     "detail": f"{int(kt) or '?'} kt · {s.get('pressure') or '?'} mb · "
                                               f"moving {s.get('movementDir', '?')}° at {s.get('movementSpeed', '?')} kt · "
                                               f"adv {adv.get('advNum', '?')}",
                                     "severity": sev, "category": cls, "value": f"{int(kt) or '?'} kt",
                                     "url": adv.get("url") or "https://www.nhc.noaa.gov/"}})
    return {"type": "FeatureCollection", "generated": int(time.time() * 1000), "features": feats}


# --------------------------------------------------------------------------- #
# ArcGIS feature services (FIMAN gauges, Duke outages, FEMA shelters)
# --------------------------------------------------------------------------- #
def _arcgis_features(url: str, params: dict, page: int = 1000) -> list[dict]:
    """All features of an ArcGIS query as GeoJSON, following resultOffset
    pagination (services cap a page at 1,000 or 2,000 records)."""
    feats: list[dict] = []
    offset = 0
    while True:
        d = http_json(url, params={**params, "f": "geojson", "resultOffset": offset, "resultRecordCount": page}, timeout=40)
        if not isinstance(d, dict) or not isinstance(d.get("features"), list):
            raise SchemaError(f"ArcGIS query to {url.split('/rest/')[0]}: no features array")
        feats.extend(d["features"])
        if len(d["features"]) < page or offset >= 20000:
            break
        offset += page
    return feats


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _fc(feats: list[dict]) -> dict:
    return {"type": "FeatureCollection", "generated": int(time.time() * 1000), "features": feats}


def _fiman_severity(cond) -> int:
    """FIMAN categories 0 Normal, 1 Near flooding, 2 Minor, 3 Moderate, 4 Major
    onto the Conditions ramp -1 offline, 0 normal, 1 watch, 2 elevated, 3 severe."""
    if cond is None:
        return -1
    c = int(cond)
    return 0 if c <= 0 else 1 if c == 1 else 2 if c == 2 else 3


def fiman_gauges() -> dict:
    """Every in-service FIMAN gauge as a point with its flood category, the
    forecast peak when one exists, 24-hour rain and the roads it floods."""
    rows = _arcgis_features(FIMAN, {
        "where": "IN_SERVICE=1",
        "outFields": "SITE_ID,NAME,OWNER,COUNTY,River_Basin,CONDITION,TREND,HYDRO_ALL_STAGE,HYDRO_ALL_DATE,"
                     "MINOR,MODERATE,MAJOR,FORECAST_PEAK_STAGE,NWMFORECAST_PEAK_STAGE,"
                     "RAIN_24HR,NC_Miles,Local_Miles,AfBridgeCount,LINK",
        "returnGeometry": "true", "outSR": "4326"})
    feats = []
    for f in rows:
        g = f.get("geometry") or {}
        c = g.get("coordinates") if g.get("type") == "Point" else None
        p = f.get("properties") or {}
        if not c or not _in_nc(c[0], c[1]) or not p.get("SITE_ID"):
            continue
        cond = _num(p.get("CONDITION"))
        category = FIMAN_CONDITION.get(int(cond), "No reading") if cond is not None else "No reading"
        stage = _num(p.get("HYDRO_ALL_STAGE"))
        fc_stage = _num(p.get("FORECAST_PEAK_STAGE"))
        nwm_stage = _num(p.get("NWMFORECAST_PEAK_STAGE"))
        rain24 = _num(p.get("RAIN_24HR"))
        bits = [category.lower() if cond is not None else "no reading"]
        if stage is not None:
            bits.append(f"stage {stage:g} ft" + (f", {str(p.get('TREND')).lower()}" if p.get("TREND") else ""))
        if fc_stage is not None and fc_stage > 0:
            bits.append(f"NWS forecast peak {fc_stage:g} ft")
        elif nwm_stage is not None and nwm_stage > 0:
            bits.append(f"NWM forecast peak {nwm_stage:g} ft")
        if rain24 is not None:
            bits.append(f"{rain24:g} in rain in 24 h")
        miles = (_num(p.get("NC_Miles")) or 0) + (_num(p.get("Local_Miles")) or 0)
        if miles:
            bits.append(f"{miles:g} road miles flooded")
        if _num(p.get("AfBridgeCount")):
            bits.append(f"{int(p['AfBridgeCount'])} bridges affected")
        owner = p.get("OWNER") or "unknown owner"
        thresholds = ", ".join(f"{k.lower()} {v:g} ft" for k, v in (("MINOR", _num(p.get("MINOR"))), ("MODERATE", _num(p.get("MODERATE"))), ("MAJOR", _num(p.get("MAJOR")))) if v is not None)
        detail = " · ".join(bits) + (f" · thresholds {thresholds}" if thresholds else "") + f" · {owner} gauge, {p.get('COUNTY') or '?'} County"
        link = p.get("LINK")
        if not (isinstance(link, str) and link.startswith("http") and "water.weather.gov" not in link):
            link = "https://fiman.nc.gov/"  # legacy AHPS links no longer resolve
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [c[0], c[1]]},
                      "properties": {"id": f"fiman-{p['SITE_ID']}", "layer": "fiman",
                                     "title": (p.get("NAME") or p["SITE_ID"]).strip(),
                                     "detail": detail, "severity": _fiman_severity(cond), "category": category,
                                     "value": f"{stage:g} ft" if stage is not None else "",
                                     "owner": owner, "county": p.get("COUNTY"), "basin": p.get("River_Basin"),
                                     "observed": _num(p.get("HYDRO_ALL_DATE")), "url": link}})
    feats.sort(key=lambda f: -f["properties"]["severity"])
    return _fc(feats)


def duke_outages() -> dict:
    """Counties in Duke Energy territory with customers out of power, as
    polygons coloured by the share of customers out. Counties with nobody out
    are left out so a calm day is an empty map, not a grey one."""
    rows = _arcgis_features(DUKE, {
        "where": "1=1",
        "outFields": "county_name,state_name,customer_served,customer_out,customer_with_power,percent_out,etr,last_edited_date",
        "returnGeometry": "true", "outSR": "4326", "geometryPrecision": 4,
        "geometryType": "esriGeometryEnvelope", "geometry": ",".join(str(v) for v in NC_BBOX),
        "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"})
    feats = []
    served_total = out_total = 0
    for f in rows:
        p = f.get("properties") or {}
        g = f.get("geometry")
        out = int(_num(p.get("customer_out")) or 0)
        served = int(_num(p.get("customer_served")) or 0)
        served_total += served
        out_total += out
        if out <= 0 or not g:
            continue
        pct = _num(p.get("percent_out"))
        if pct is None:
            pct = round(100.0 * out / served, 1) if served else 0.0
        sev = 3 if pct >= 50 else 2 if pct >= 20 else 1 if pct >= 5 else 0
        name = str(p.get("county_name") or "").title()
        etr = p.get("etr")
        feats.append({"type": "Feature", "geometry": g,
                      "properties": {"id": f"duke-{name.lower().replace(' ', '_')}", "layer": "power",
                                     "title": f"{name} County: {out:,} customers out",
                                     "detail": f"{pct:g}% of {served:,} Duke Energy customers"
                                               + (f" · estimated restoration {etr}" if etr else "")
                                               + " · updated about every 20 minutes · Duke territory only, co-ops and municipals not shown",
                                     "severity": sev, "category": "Power outage", "value": f"{pct:g}% out",
                                     "customers_out": out, "customers_served": served, "percent_out": pct,
                                     "url": "https://outagemap.duke-energy.com/"}})
    feats.sort(key=lambda f: -f["properties"]["customers_out"])
    fc = _fc(feats)
    fc["totals"] = {"customers_out": out_total, "customers_served": served_total, "counties_out": len(feats)}
    return fc


def fema_shelters() -> dict:
    """Open shelters in North Carolina from FEMA's ESF6 feed, with capacity
    and population where the operator entered them."""
    rows = _arcgis_features(SHELTERS, {
        "where": "state='NC'",
        "outFields": "shelter_id,shelter_name,address,city,state,zip,shelter_status,evacuation_capacity,post_impact_capacity,"
                     "total_population,org_name,ada_compliant,wheelchair_accessible,pet_accommodations_code",
        "returnGeometry": "true", "outSR": "4326"})
    feats = []
    for f in rows:
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        c = g.get("coordinates") if g.get("type") == "Point" else None
        if not c or not _in_nc(c[0], c[1]):
            continue
        pop = _num(p.get("total_population"))
        cap = _num(p.get("post_impact_capacity")) or _num(p.get("evacuation_capacity"))
        bits = [str(p.get("shelter_status") or "open").lower()]
        if pop is not None:
            bits.append(f"{int(pop):,} sheltered")
        if cap:
            bits.append(f"capacity {int(cap):,}")
        if p.get("ada_compliant") in ("Y", "Yes", 1, True):
            bits.append("ADA")
        if p.get("pet_accommodations_code") in ("Y", "Yes", 1, True):
            bits.append("pets")
        addr = ", ".join(str(x) for x in (p.get("address"), p.get("city")) if x)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [c[0], c[1]]},
                      "properties": {"id": f"shelter-{p.get('shelter_id') or len(feats)}", "layer": "shelter",
                                     "title": (p.get("shelter_name") or "Shelter").strip(),
                                     "detail": " · ".join(bits) + (f" · {addr}" if addr else "")
                                               + (f" · run by {p['org_name']}" if p.get("org_name") else "")
                                               + " · FEMA ESF6 shelter list, synced daily with the Red Cross",
                                     "severity": 0, "category": "Open shelter",
                                     "value": f"{int(pop):,} sheltered" if pop is not None else "",
                                     "population": pop, "capacity": cap,
                                     "url": "https://www.redcross.org/get-help/disaster-relief-and-recovery-services/find-an-open-shelter.html"}})
    return _fc(feats)
