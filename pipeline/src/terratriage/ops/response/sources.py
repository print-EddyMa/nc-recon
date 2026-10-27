"""Official, keyless, nationwide layers for response products (checked 2026-10-22).

HIFLD Open shut down on 26 Aug 2025; its public layers now live with the
original agencies or in FEMA's own ArcGIS copies, which is where these come
from. Only the fields named are requested: addresses and phone numbers are
never fetched.

  water_systems   EPA community water system service areas (many boundaries
                  are modelled, see Verification_Status)
  hospitals       FEMA Hospitals (RAPT): beds, trauma level, helipad
  dams            USACE National Inventory of Dams: hazard potential, condition,
                  emergency action plan
  hazmat          EPA facility points: Superfund (SEMS), Toxics Release
                  Inventory, NPDES wastewater dischargers
  heliports       FAA facilities via the National Transportation Atlas
  outages         DOE/ORNL ODIN county outages (about 50 utilities report;
                  live only, so used only while an event is current)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from shapely.geometry import shape

from ..collect.base import DiskCache, SchemaError, http_json

EPA_WATER = ("https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/"
             "Water_System_Boundaries/FeatureServer/0")
HOSPITALS = "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/Hospitals_RAPT/FeatureServer/6"
NID = ("https://geospatial.sec.usace.army.mil/dls/rest/services/NID/"
       "National_Inventory_of_Dams_Public_Service/FeatureServer/0")
EMEF = "https://geopub.epa.gov/arcgis/rest/services/EMEF/efpoints/MapServer"
EMEF_LAYERS = {0: "superfund_site", 1: "toxics_release_facility", 2: "wastewater_discharger"}
AVIATION = ("https://services.arcgis.com/xOi1kZaI0eWDREZv/ArcGIS/rest/services/"
            "NTAD_Aviation_Facilities/FeatureServer/0")
ODIN = ("https://ornl.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
        "odin-real-time-outages-county/records")

SOURCES = {
    "water_systems": {"name": "EPA community water system service area boundaries", "url": EPA_WATER,
                      "license": "US Government (EPA); public domain"},
    "hospitals": {"name": "FEMA Hospitals (RAPT)", "url": HOSPITALS, "license": "US Government (FEMA)"},
    "dams": {"name": "USACE National Inventory of Dams", "url": NID, "license": "US Government (USACE)"},
    "hazmat": {"name": "EPA EMEF facility points (SEMS, TRI, NPDES)", "url": EMEF,
               "license": "US Government (EPA); public domain"},
    "heliports": {"name": "FAA aviation facilities (BTS National Transportation Atlas)", "url": AVIATION,
                  "license": "US Government (FAA/BTS)"},
    "outages": {"name": "DOE/ORNL ODIN county outages", "url": ODIN, "license": "no licence text published"},
}


def _query(url: str, bbox, fields: str, where: str = "1=1", geometry: bool = False,
           page: int = 1000, max_pages: int = 20) -> list[dict[str, Any]]:
    w, s, e, n = bbox
    cache = DiskCache("response_sources")
    key = (url.split("/services/")[-1] + f"_{where}_{fields}_{geometry}_" + "_".join(f"{v:.4f}" for v in bbox))
    key = "".join(ch if ch.isalnum() else "_" for ch in key)[-180:]
    hit = cache.get(key, 7 * 86400)
    if hit is not None:
        return hit
    out: list[dict[str, Any]] = []
    for k in range(max_pages):
        d = http_json(url + "/query", params={
            "where": where, "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": fields,
            "returnGeometry": "true" if geometry else "false", "f": "geojson" if geometry else "json",
            "resultOffset": k * page, "resultRecordCount": page}, timeout=90)
        if not isinstance(d, dict) or "features" not in d:
            raise SchemaError(f"{url}: no features ({str(d)[:120]})")
        out += d["features"]
        if len(d["features"]) < page:
            break
    cache.put(key, out)
    return out


def water_systems(bbox) -> list[dict[str, Any]]:
    feats = _query(EPA_WATER, bbox, "PWSID,PWS_Name,Population_Served_Count,Service_Connections_Count,"
                                    "Verification_Status,Service_Area_Type", geometry=True, page=200)
    out = []
    for f in feats:
        p = f.get("properties") or {}
        if not f.get("geometry"):
            continue
        out.append({"pwsid": p.get("PWSID"), "name": p.get("PWS_Name"),
                    "population_served": p.get("Population_Served_Count"),
                    "connections": p.get("Service_Connections_Count"),
                    "boundary": p.get("Verification_Status"), "_geom": shape(f["geometry"])})
    return out


def _pt(a: dict, lon_k: str, lat_k: str) -> tuple[float, float] | None:
    try:
        return float(a[lon_k]), float(a[lat_k])
    except (KeyError, TypeError, ValueError):
        return None


def hospitals(bbox) -> list[dict[str, Any]]:
    out = []
    for f in _query(HOSPITALS, bbox, "ID,NAME,TYPE,STATUS,BEDS,TRAUMA,HELIPAD,LATITUDE,LONGITUDE"):
        a = f.get("attributes") or {}
        p = _pt(a, "LONGITUDE", "LATITUDE")
        if p and str(a.get("STATUS") or "").upper() != "CLOSED":
            out.append({"id": f"hospital/{a.get('ID')}", "kind": "hospital", "lifeline": "health_medical",
                        "name": a.get("NAME"), "lon": p[0], "lat": p[1], "beds": a.get("BEDS"),
                        "trauma": a.get("TRAUMA"), "helipad": a.get("HELIPAD"), "source": "FEMA Hospitals (RAPT)"})
    return out


def dams(bbox) -> list[dict[str, Any]]:
    out = []
    for f in _query(NID, bbox, "NIDID,NAME,HAZARD_POTENTIAL,CONDITION_ASSESSMENT,EAP_PREPARED,"
                               "LAST_INSPECTION_DATE,RIVER_OR_STREAM,NID_STORAGE,LATITUDE,LONGITUDE"):
        a = f.get("attributes") or {}
        p = _pt(a, "LONGITUDE", "LATITUDE")
        if p:
            out.append({"id": f"dam/{a.get('NIDID')}", "kind": "dam", "lifeline": "water_systems",
                        "name": a.get("NAME"), "lon": p[0], "lat": p[1],
                        "hazard_potential": a.get("HAZARD_POTENTIAL"), "condition": a.get("CONDITION_ASSESSMENT"),
                        "emergency_action_plan": a.get("EAP_PREPARED"), "river": a.get("RIVER_OR_STREAM"),
                        "storage_acre_ft": a.get("NID_STORAGE"), "source": "USACE NID"})
    return out


def hazmat(bbox) -> list[dict[str, Any]]:
    out = []
    for layer, kind in EMEF_LAYERS.items():
        for f in _query(f"{EMEF}/{layer}", bbox, "registry_id,primary_name,latitude,longitude,pgm_sys_acrnm"):
            a = f.get("attributes") or {}
            p = _pt(a, "longitude", "latitude")
            if p:
                out.append({"id": f"frs/{a.get('registry_id')}/{layer}", "kind": kind,
                            "lifeline": "hazardous_materials" if layer != 2 else "water_systems",
                            "name": a.get("primary_name"), "lon": p[0], "lat": p[1],
                            "program": a.get("pgm_sys_acrnm"), "source": "EPA EMEF"})
    return out


def heliports(bbox) -> list[dict[str, Any]]:
    out = []
    for f in _query(AVIATION, bbox, "ARPT_ID,ARPT_NAME,SITE_TYPE_CODE,FACILITY_USE_CODE,ARPT_STATUS,"
                                    "LAT_DECIMAL,LONG_DECIMAL"):
        a = f.get("attributes") or {}
        p = _pt(a, "LONG_DECIMAL", "LAT_DECIMAL")
        if p and a.get("SITE_TYPE_CODE") in ("H", "A"):
            out.append({"id": f"faa/{a.get('ARPT_ID')}", "kind": "helipad" if a["SITE_TYPE_CODE"] == "H" else "airport",
                        "lifeline": "transportation", "name": a.get("ARPT_NAME"), "lon": p[0], "lat": p[1],
                        "use": a.get("FACILITY_USE_CODE"), "status": a.get("ARPT_STATUS"), "source": "FAA"})
    return out


def outages(bbox, incident: date, active_days: int = 21) -> dict[str, Any]:
    """County outages from ODIN, only while the event is current: outside
    that window today's outages say nothing about this event."""
    age = (datetime.now(timezone.utc).date() - incident).days
    if age > active_days or age < -3:
        return {"active": False, "note": f"event began {age} days ago; live outage feeds are not used for it"}
    w, s, e, n = bbox
    poly = f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"
    d = http_json(ODIN, params={"where": f"intersects(geom, geom'{poly}')", "limit": 100}, timeout=60)
    rows = d.get("results") or []
    return {"active": True, "counties": [{"utility": r.get("name"), "county": r.get("county"),
                                          "state": r.get("state"), "meters_out": r.get("metersaffected"),
                                          "estimated_restoration": r.get("estimatedrestorationtime")} for r in rows],
            "note": "About 50 utilities report to ODIN; a county with no row is not necessarily powered."}


def facilities(bbox) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Every official facility layer; a layer that fails is reported, not fatal."""
    out: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for name, fn in (("hospitals", hospitals), ("dams", dams), ("hazmat", hazmat), ("heliports", heliports)):
        try:
            out += fn(bbox)
        except Exception as ex:  # noqa: BLE001
            errors[name] = str(ex)[:160]
    return out, errors


_ = json
