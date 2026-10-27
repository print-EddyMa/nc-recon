"""Exports an EM analyst can open anywhere: `run.py ops-export --area X`.

Formats (all in data/output/ops/exports/<area>/):
  <area>.geojson      RFC 7946 (WGS 84 lon/lat, CCW exterior rings)
  <area>.csv          one row per structure: lon/lat, USNG 1 m + 10 m, ncr_id
  <area>.kml          styled by damage level
  <area>.gpkg         GeoPackage (QGIS / ArcGIS Pro)
  <area>.gdb          File Geodatabase (GDAL OpenFileGDB writer)
  <area>_survey123.csv  field-verification sheet + choices
  <area>_fema_ia.csv / .geojson  residential structures in the field layout of
                      FEMA's Individual Assistance damage assessment survey, so
                      a county can append them to its Survey123 layer
  <area>.provenance.json, README.txt  (sources, licenses, disclaimer)

Field names follow the FEMA damage-assessment database where one exists
(DMG_LEVEL, ASMT_TYPE, IMG_DATE, EVENT_NAME, EVENT_DATE, DIS_NUMBER, USNG,
SOURCE). ASMT_TYPE is always "Remote Sensing" (or "Modeled" for flood-only
calls); only field reports may say "Field Assessed".

Modes:
  public     no addresses, no building-level export at all unless the caller
             asks for an aggregate (see aggregate.py)
  responder  building level + addresses (from the responder sidecar)
"""
from __future__ import annotations

import csv
import json
import os
from typing import Any

from .. import DISCLAIMER, OPS_OUT
from ..analyze.classes import FEMA, FEMA_LABEL
from ..guard import csv_cell
from ..provenance import utc_now

# ColorBrewer YlOrRd (colour-blind + print safe); no-damage = neutral grey
COLORS = {"no_damage": "#9e9e9e", "affected": "#fecc5c", "minor": "#fd8d3c",
          "major": "#f03b20", "destroyed": "#bd0026", None: "#555555"}

LICENSE_TEXT = """\
License obligations for this export
-----------------------------------
* Building footprints from OpenStreetMap (footprint_source = "osm") are
  (c) OpenStreetMap contributors, ODbL 1.0. A derived database that includes
  them must be shared under ODbL with attribution.
* FEMA USA Structures and USACE NSI attributes: US Government works.
* Maxar Open Data imagery (when used): CC BY-NC 4.0 - non-commercial use only,
  with attribution. Products derived from it inherit the NC restriction.
* NC OneMap orthoimagery and NOAA ERI: public; credit NC OneMap / NC
  Collaboratory and NOAA NGS.
* Damage model: xView2 baseline classifier trained on xBD (xView2 challenge
  terms: non-commercial).
"""


FEMA_IA_LEVELS = ("unaffected", "affected", "minor", "major", "destroyed", "inaccessible")
# Groma level -> FEMA IA survey choice (code values as the survey stores them)
IA_LEVEL = {"no_damage": "unaffected", "affected": "affected", "minor": "minor",
            "major": "major", "destroyed": "destroyed"}
# Field names exactly as a deployed FEMA "Damage Assessment form V2.7 for
# Individual Assistance" Survey123 layer stores them (Survey123 truncates long
# question names to 31 characters). Read from a public deployment on
# 2026-10-09; FEMA's own v4.1.0 template page was not reachable, so confirm
# against NCEM's authoritative IA survey before appending.
FEMA_IA_FIELDS = (
    "incident_id_number", "incident_begin_date", "collection_date", "event_name",
    "street_address", "stateterritory", "county", "zipcode",
    "what_event_type_caused_the_dama", "owner_or_renter", "is_there_insurance",
    "level_of_damage_assessed", "choose_the_type_of_dwelling",
    "is_this_home_occupied_at_least_", "are_the_utilities_functional",
    "additional_narrative", "date_and_time_of_assessment",
)
FEMA_IA_NOTE = """FEMA IA layout (<area>_fema_ia.csv / .geojson)
---------------------------------------------
Residential structures only, one point each, with the question names of FEMA's
Individual Assistance damage assessment survey as deployed in Survey123
(form V2.7), plus Groma columns prefixed ncr_. Every row is a remote call:
"level_of_damage_assessed" is the most likely level from imagery, never a
field observation; owner/renter, insurance, occupancy and utilities are
"unknown" because imagery cannot see them. Rows marked ncr_needs_review = yes
are uncertain or severe and should be verified on the ground first.
The field list was read from a public deployment of the FEMA form; confirm it
against NCEM's authoritative IA survey before appending to a state layer.
"""


def _event_type(name: str) -> str:
    n = (name or "").lower()
    for key, label in (("hurricane", "Hurricane"), ("tropical storm", "Tropical Storm"), ("tornado", "Tornado"),
                       ("flood", "Flood"), ("winter", "Winter Storm"), ("fire", "Fire"), ("storm", "Severe Storm")):
        if key in n:
            return label
    return "Other"


def _dwelling(p: dict[str, Any]) -> str | None:
    """FEMA IA dwelling type; "" for a home of unknown type; None for a
    structure that is not a home (left out of the IA layer)."""
    flags = p.get("flags") or {}
    occ = (p.get("occupancy") or "").upper()
    prim = (p.get("primary_occupancy") or "").lower()
    if flags.get("outbuilding"):
        return None
    if flags.get("manufactured_home") or occ.startswith("RES2") or "manufactured" in prim:
        return "manufactured_home"
    if occ.startswith(("RES3", "RES4", "RES5", "RES6")) or "multi" in prim:
        return "multi_family"
    if occ.startswith("RES1") or "single family" in prim:
        return "single_family"
    if flags.get("residential"):
        return ""  # a home, but nothing says which kind: leave it for the field team
    return None


def state_name(fc: dict[str, Any]) -> str:
    """The event's state, from its declaration ("DR-4827-NC" -> "North Carolina")
    or the area's own state field; "" when neither says."""
    from ..plan.bootstrap import STATES

    run = fc.get("properties") or {}
    for d in (run.get("event") or {}).get("declarations") or []:
        code = str(d).rsplit("-", 1)[-1].upper()
        if code in STATES:
            return STATES[code]
    st = str((run.get("aoi") or {}).get("state") or "").strip()
    return STATES.get(st.upper(), st)


def fema_ia_rows(fc: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[list[dict], list[dict], int]:
    """Residential rows in FEMA's IA survey layout (see FEMA_IA_NOTE), verify-first
    then most severe, with matching point features; plus how many non-homes were left out."""
    from ..analyze.fema_reference import zip_of

    run = fc["properties"]
    state = state_name(fc)
    ev = run.get("event") or {}
    aoi = run.get("aoi") or {}
    generated = run.get("generated_utc") or utc_now()
    event_type = _event_type(ev.get("name") or "")
    out_rows, feats, skipped = [], [], 0
    for f, row in zip(fc["features"], rows):
        p = f["properties"]
        dwelling = _dwelling(p)
        if dwelling is None:
            skipped += 1
            continue
        lvl = p.get("damage_level")
        fema = p.get("fema") or {}
        probs = p.get("damage_probs") or {}
        reasons = [r.replace("_", " ").lower() for r in (p.get("review_reasons") or [])]
        if lvl:
            narrative = (f"Remote assessment by Groma from imagery dated "
                         f"{fema.get('IMG_DATE') or fema.get('IMG_DATE_RANGE') or 'unknown'}; "
                         f"P({FEMA_LABEL.get(lvl, lvl)}) = {round(100 * (probs.get(lvl) or 0))}%"
                         + (f"; verify first: {', '.join(reasons)}" if p.get("needs_review") else "")
                         + ". Not field verified.")
        else:
            narrative = "In the structure inventory but not assessed (no footprint seen in the imagery). Not field verified."
        addr = row.get("address") or ""
        out = {
            "incident_id_number": fema.get("DIS_NUMBER") or (ev.get("declarations") or [""])[0],
            "incident_begin_date": ev.get("incident_begin") or fema.get("EVENT_DATE"),
            "collection_date": fema.get("IMG_DATE") or "",
            "event_name": ev.get("name") or fema.get("EVENT_NAME"),
            "street_address": addr.split(",")[0].strip() if addr else "",
            "stateterritory": state,
            "county": aoi.get("county") or "",
            "zipcode": zip_of(addr) or "",
            "what_event_type_caused_the_dama": event_type,
            "owner_or_renter": "unknown",
            "is_there_insurance": "unknown",
            # an inventory point with no footprint in the imagery is not "inaccessible"
            # in FEMA's sense (blocked access); leave it blank for the field team
            "level_of_damage_assessed": IA_LEVEL.get(lvl, "") if lvl else "",
            "choose_the_type_of_dwelling": dwelling,
            "is_this_home_occupied_at_least_": "unknown",
            "are_the_utilities_functional": "unknown",
            "additional_narrative": narrative,
            "date_and_time_of_assessment": generated,
            "ncr_id": p["ncr_id"],
            "ncr_assessment_type": fema.get("ASMT_TYPE") or ("Remote Sensing" if lvl else "Unknown"),
            "ncr_probability": round(probs.get(lvl) or 0, 3) if lvl else None,
            "ncr_needs_review": "yes" if p.get("needs_review") else "no",
            "ncr_usng_10m": p.get("usng_10m"),
            "ncr_lat": row["lat"], "ncr_lon": row["lon"],
        }
        out_rows.append(out)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
                      "properties": out})
    # verify-first rows first, then most severe, so a field team can work down the list
    order = {"destroyed": 0, "major": 1, "minor": 2, "affected": 3, "unaffected": 4, "": 5}
    idx = sorted(range(len(out_rows)), key=lambda i: (out_rows[i]["ncr_needs_review"] != "yes",
                                                      order.get(out_rows[i]["level_of_damage_assessed"], 5)))
    return [out_rows[i] for i in idx], [feats[i] for i in idx], skipped


def _fema_ia(area: str, fc: dict[str, Any], rows: list[dict[str, Any]], d: str) -> tuple[str, str, int]:
    out_rows, feats, skipped = fema_ia_rows(fc, rows)
    cols = list(FEMA_IA_FIELDS) + ["ncr_id", "ncr_assessment_type", "ncr_probability", "ncr_needs_review",
                                   "ncr_usng_10m", "ncr_lat", "ncr_lon"]
    csv_path = os.path.join(d, f"{area}_fema_ia.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows({k: csv_cell(v) for k, v in r.items()} for r in out_rows)
    gj_path = os.path.join(d, f"{area}_fema_ia.geojson")
    with open(gj_path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh)
    return csv_path, gj_path, skipped


def _ring_ccw(ring: list[list[float]]) -> list[list[float]]:
    a = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))
    return ring if a > 0 else list(reversed(ring))


def _flat(p: dict[str, Any], responder: dict[str, Any] | None,
          fema_defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    lvl = p.get("damage_level")
    probs = p.get("damage_probs") or {}
    occ = p.get("occupants") or {}
    row = {
        "ncr_id": p["ncr_id"],
        "lon": p["centroid"][0], "lat": p["centroid"][1],
        "usng_1m": p.get("usng_1m"), "usng_10m": p.get("usng_10m"),
        "damage_level": FEMA_LABEL.get(lvl, "Not assessed") if lvl else "Not assessed",
        "confidence": p.get("confidence"),
        "needs_review": p.get("needs_review"),
        "review_reasons": ";".join(p.get("review_reasons") or []),
        "p_no_damage": probs.get("no_damage"), "p_affected": probs.get("affected"),
        "p_minor": probs.get("minor"), "p_major": probs.get("major"),
        "p_destroyed": probs.get("destroyed"),
        "prediction_set": ";".join(p.get("prediction_set") or []),
        "reason_codes": ";".join(p.get("reason_codes") or [])[:1000],
        "evidence_unavailable": ";".join(f"{k}:{v}" for k, v in (p.get("evidence_unavailable") or {}).items()),
        "occupancy": p.get("occupancy"), "primary_occupancy": p.get("primary_occupancy"),
        "residential": (p.get("flags") or {}).get("residential"),
        "manufactured_home": (p.get("flags") or {}).get("manufactured_home"),
        "outbuilding": (p.get("flags") or {}).get("outbuilding"),
        "occupants_nsi": occ.get("nsi_estimate"), "occupants_usa_median": occ.get("usa_structures_median"),
        "stories": p.get("stories"), "foundation_height_ft": p.get("foundation_height_ft"),
        "ground_elev_m_navd88": p.get("ground_elev_m_navd88"), "flood_zone": p.get("flood_zone"),
        "footprint_source": p.get("footprint_source"),
        "source_ids": json.dumps(p.get("source_ids") or {}),
    }
    fema = p.get("fema") or {}
    for k in ("DMG_LEVEL", "ASMT_TYPE", "IMG_DATE", "IMG_DATE_RANGE", "EVENT_NAME", "EVENT_DATE",
              "DIS_NUMBER", "USNG", "SOURCE"):
        row[k] = fema.get(k)
    if not lvl:
        # inventory structure with no footprint: event fields from the run,
        # FEMA's own "Unknown" assessment type, no damage level
        for k in ("EVENT_NAME", "EVENT_DATE", "DIS_NUMBER", "SOURCE"):
            row[k] = (fema_defaults or {}).get(k)
        row["DMG_LEVEL"] = "Not Assessed"
        row["ASMT_TYPE"] = "Unknown"
        row["IMG_DATE"] = None
        row["USNG"] = p.get("usng_10m")
    if responder is not None:
        row["address"] = (responder.get(p["ncr_id"]) or {}).get("address")
    row["disclaimer"] = DISCLAIMER
    return row


def export_area(area: str, mode: str = "responder", out_dir: str | None = None) -> dict[str, str]:
    import geopandas as gpd
    from shapely.geometry import shape

    if mode not in ("responder", "public"):
        raise ValueError("mode must be responder or public")
    if mode == "public":
        raise PermissionError("public mode exports aggregates only: use `run.py ops-aggregate`")
    with open(os.path.join(OPS_OUT, f"{area}.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    rsp_path = os.path.join(OPS_OUT, f"{area}.responder.json")
    responder = {}
    if os.path.exists(rsp_path):
        with open(rsp_path, encoding="utf-8") as fh:
            responder = json.load(fh)["structures"]
    if not fc["features"]:
        raise ValueError("this assessment found no structures, so there is nothing to export")
    d = out_dir or os.path.join(OPS_OUT, "exports", area)
    os.makedirs(d, exist_ok=True)
    rows, geoms = [], []
    feats_out = []
    defaults = next((f["properties"]["fema"] for f in fc["features"] if f["properties"].get("fema")), {})
    for f in fc["features"]:
        row = _flat(f["properties"], responder, defaults)
        g = f["geometry"]
        if g["type"] == "Polygon":
            g = {"type": "Polygon", "coordinates": [_ring_ccw(g["coordinates"][0])]}
        rows.append(row)
        geoms.append(shape(g))
        feats_out.append({"type": "Feature", "geometry": g, "properties": row})
    paths: dict[str, str] = {}
    run_props = fc["properties"]

    # GeoJSON (RFC 7946: no crs member, lon/lat WGS 84)
    p = os.path.join(d, f"{area}.geojson")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": feats_out}, fh)
    paths["geojson"] = p

    # CSV
    p = os.path.join(d, f"{area}.csv")
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows({k: csv_cell(v) for k, v in r.items()} for r in rows)
    paths["csv"] = p

    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
    for col in gdf.columns:
        if gdf[col].dtype == object and col != "geometry":
            gdf[col] = gdf[col].astype("string")
    polys = gdf[gdf.geometry.geom_type == "Polygon"]
    pts = gdf[gdf.geometry.geom_type == "Point"]
    p = os.path.join(d, f"{area}.gpkg")
    if os.path.exists(p):
        os.remove(p)
    polys.to_file(p, layer="structures", driver="GPKG")
    if len(pts):
        pts.to_file(p, layer="not_assessed_points", driver="GPKG")
    paths["gpkg"] = p
    p = os.path.join(d, f"{area}.gdb")
    import shutil

    if os.path.exists(p):
        shutil.rmtree(p)
    polys.to_file(p, layer="structures", driver="OpenFileGDB")
    if len(pts):
        pts.to_file(p, layer="not_assessed_points", driver="OpenFileGDB")
    paths["filegdb"] = p

    paths["kml"] = _kml(area, rows, geoms, os.path.join(d, f"{area}.kml"))
    paths["survey123"] = _survey123(area, rows, d)
    ia_csv, ia_geojson, ia_skipped = _fema_ia(area, fc, rows, d)
    paths["fema_ia_csv"], paths["fema_ia_geojson"] = ia_csv, ia_geojson

    prov = {"generated_utc": utc_now(), "run_id": run_props.get("run_id"), "mode": mode,
            "disclaimer": DISCLAIMER, "event": run_props.get("event"), "aoi": run_props.get("aoi"),
            "provenance": run_props.get("provenance"), "calibration": run_props.get("calibration"),
            "config_status": run_props.get("config_status"), "warnings": run_props.get("warnings"),
            "coordinate_reference": "EPSG:4326 (WGS 84) lon/lat; USNG strings computed from NAD83(2011)-"
                                    "equivalent lon/lat (the ~1 m realization gap is below 1 m USNG precision "
                                    "reliability)",
            "fema_ia_excluded_non_residential": ia_skipped,
            "files": {k: os.path.basename(v) for k, v in paths.items()}}
    p = os.path.join(d, f"{area}.provenance.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, indent=2)
    paths["provenance"] = p
    with open(os.path.join(d, "README.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"Groma export: {area}\n\n{DISCLAIMER}\n\n"
                 "Contains street addresses (responder mode). Do not post publicly.\n\n"
                 f"{LICENSE_TEXT}\n{FEMA_IA_NOTE}\nSee {area}.provenance.json for sources, dates and processing.\n")
    print(f"[export] {area}: {len(rows)} rows -> {d}")
    return paths


def _kml(area, rows, geoms, path) -> str:
    from xml.sax.saxutils import escape

    def kcol(hexc: str, a: str = "b0") -> str:
        h = hexc.lstrip("#")
        return f"{a}{h[4:6]}{h[2:4]}{h[0:2]}"

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           f"<name>Groma {escape(area)}</name><description>{escape(DISCLAIMER)}</description>"]
    for lvl, hexc in COLORS.items():
        sid = lvl or "not_assessed"
        out.append(f'<Style id="{sid}"><LineStyle><color>{kcol(hexc, "ff")}</color><width>1.5</width></LineStyle>'
                   f'<PolyStyle><color>{kcol(hexc)}</color></PolyStyle>'
                   f'<IconStyle><color>{kcol(hexc, "ff")}</color></IconStyle></Style>')
    inv = {FEMA_LABEL[c]: c for c in FEMA}
    for r, g in zip(rows, geoms):
        lvl = inv.get(r["damage_level"])
        desc = (f"Damage: {r['damage_level']} (confidence {r['confidence']})<br/>"
                f"Needs review: {r['needs_review']} {r['review_reasons']}<br/>USNG: {r['usng_10m']}<br/>"
                f"{DISCLAIMER}")
        if g.geom_type == "Polygon":
            coords = " ".join(f"{x:.7f},{y:.7f}" for x, y in g.exterior.coords)
            geom = f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon>"
        else:
            geom = f"<Point><coordinates>{g.x:.7f},{g.y:.7f}</coordinates></Point>"
        out.append(f"<Placemark><name>{escape(r['usng_10m'] or r['ncr_id'])}</name>"
                   f"<description><![CDATA[{desc}]]></description><styleUrl>#{lvl or 'not_assessed'}</styleUrl>{geom}</Placemark>")
    out.append("</Document></kml>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    return path


def _survey123(area, rows, d) -> str:
    """Field-verification sheet: review-first ordering, NC field categories."""
    path = os.path.join(d, f"{area}_survey123.csv")
    ordered = sorted(rows, key=lambda r: (not r["needs_review"], -(r.get("p_destroyed") or 0) - (r.get("p_major") or 0)))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ncr_id", "usng_10m", "lat", "lon", "address", "remote_damage_level", "remote_confidence",
                    "needs_review", "field_damage_category", "field_notes", "accessible", "gnss_fix_type",
                    "gnss_accuracy_m"])
        for r in ordered:
            w.writerow([csv_cell(x) for x in [r["ncr_id"], r["usng_10m"], r["lat"], r["lon"], r.get("address") or "",
                                              r["damage_level"], r["confidence"], r["needs_review"], "", "", "", "", ""]])
    with open(os.path.join(d, "survey123_choices.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["list_name", "name", "label"])
        # FEMA's IA degrees of damage (2025 PDA Guide) plus the two states a
        # field team needs: unaffected, and inaccessible (cannot be seen)
        for n in FEMA_IA_LEVELS:
            w.writerow(["field_damage_category", n, n.title()])
        for n in ("autonomous", "sbas", "dgps", "rtk_float", "rtk_fixed", "ppk", "manual_pin"):
            w.writerow(["gnss_fix_type", n, n.replace("_", " ").upper()])
    return path
