"""Exports an EM analyst can open anywhere: `run.py ops-export --area X`.

Formats (all in data/output/ops/exports/<area>/):
  <area>.geojson      RFC 7946 (WGS 84 lon/lat, CCW exterior rings)
  <area>.csv          one row per structure: lon/lat, USNG 1 m + 10 m, ncr_id
  <area>.kml          styled by damage level
  <area>.gpkg         GeoPackage (QGIS / ArcGIS Pro)
  <area>.gdb          File Geodatabase (GDAL OpenFileGDB writer)
  <area>_survey123.csv  field-verification sheet + choices
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

from .. import DATA_DIR, DISCLAIMER
from ..analyze.classes import FEMA, FEMA_LABEL
from ..provenance import utc_now

OPS_OUT = os.path.join(DATA_DIR, "output", "ops")
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


def _ring_ccw(ring: list[list[float]]) -> list[list[float]]:
    a = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))
    return ring if a > 0 else list(reversed(ring))


def _flat(p: dict[str, Any], responder: dict[str, Any] | None) -> dict[str, Any]:
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
    for k in ("DMG_LEVEL", "ASMT_TYPE", "IMG_DATE", "EVENT_NAME", "EVENT_DATE", "DIS_NUMBER", "USNG", "SOURCE"):
        row[k] = fema.get(k)
    if not lvl:
        row["DMG_LEVEL"] = "Not Assessed"
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
    d = out_dir or os.path.join(OPS_OUT, "exports", area)
    os.makedirs(d, exist_ok=True)
    rows, geoms = [], []
    feats_out = []
    for f in fc["features"]:
        row = _flat(f["properties"], responder)
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
        w.writerows(rows)
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

    prov = {"generated_utc": utc_now(), "run_id": run_props.get("run_id"), "mode": mode,
            "disclaimer": DISCLAIMER, "event": run_props.get("event"), "aoi": run_props.get("aoi"),
            "provenance": run_props.get("provenance"), "calibration": run_props.get("calibration"),
            "config_status": run_props.get("config_status"), "warnings": run_props.get("warnings"),
            "coordinate_reference": "EPSG:4326 (WGS 84) lon/lat; USNG strings computed from NAD83(2011)-"
                                    "equivalent lon/lat (the ~1 m realization gap is below 1 m USNG precision "
                                    "reliability)",
            "files": {k: os.path.basename(v) for k, v in paths.items()}}
    p = os.path.join(d, f"{area}.provenance.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, indent=2)
    paths["provenance"] = p
    with open(os.path.join(d, "README.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"NC Recon export: {area}\n\n{DISCLAIMER}\n\n"
                 "Contains street addresses (responder mode). Do not post publicly.\n\n"
                 f"{LICENSE_TEXT}\nSee {area}.provenance.json for sources, dates and processing.\n")
    print(f"[export] {area}: {len(rows)} rows -> {d}")
    return paths


def _kml(area, rows, geoms, path) -> str:
    from xml.sax.saxutils import escape

    def kcol(hexc: str, a: str = "b0") -> str:
        h = hexc.lstrip("#")
        return f"{a}{h[4:6]}{h[2:4]}{h[0:2]}"

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           f"<name>NC Recon {escape(area)}</name><description>{escape(DISCLAIMER)}</description>"]
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
            w.writerow([r["ncr_id"], r["usng_10m"], r["lat"], r["lon"], r.get("address") or "",
                        r["damage_level"], r["confidence"], r["needs_review"], "", "", "", "", ""])
    with open(os.path.join(d, "survey123_choices.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["list_name", "name", "label"])
        for n in ("unaffected", "affected", "minor", "moderate", "major", "destroyed", "inaccessible"):
            w.writerow(["field_damage_category", n, n.title()])
        for n in ("autonomous", "sbas", "dgps", "rtk_float", "rtk_fixed", "ppk", "manual_pin"):
            w.writerow(["gnss_fix_type", n, n.replace("_", " ").upper()])
    return path
