"""Response products for an assessed area (ops/response/).

  GET  /ops/areas/{area}/response               summary + every product (stored JSON)
  GET  /ops/areas/{area}/response/layers        map layers (GeoJSON FeatureCollection)
  GET  /ops/areas/{area}/response/plan.kml      sectors, landing-zone candidates, cut-off
                                                clusters and flagged facilities as KML
                                                (opens in Google Earth, ATAK/WinTAK, ArcGIS)
  POST /ops/areas/{area}/response               (re)build in the background; one at a time
  GET  /ops/areas/{area}/response/status        building | idle, last error

Responder-only: the products locate damage, people and cut-off places.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from . import audit
from .api import _area, _load, _responder
from .response import OPS_OUT

router = APIRouter(prefix="/ops")
_lock = threading.Lock()
_state: dict[str, dict[str, Any]] = {}


def _read(area: str, suffix: str) -> dict[str, Any]:
    p = os.path.join(OPS_OUT, f"{_area(area)}.{suffix}")
    if not os.path.exists(p):
        raise HTTPException(404, "no response products for this area yet (POST to build them)")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


@router.get("/areas/{area}/response")
def response(area: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    _load(area)
    d = _read(area, "response.json")
    audit.record("view_response", request, area)
    return JSONResponse(d)


@router.get("/areas/{area}/response/layers")
def response_layers(area: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    _load(area)
    d = _read(area, "response.layers.json")
    audit.record("view_response_layers", request, area)
    return JSONResponse(d, media_type="application/geo+json")


@router.get("/areas/{area}/response/status")
def response_status(area: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    st = _state.get(_area(area)) or {}
    return {"area": area, "status": st.get("status", "idle"), "started_utc": st.get("started_utc"),
            "error": st.get("error"),
            "built": os.path.exists(os.path.join(OPS_OUT, f"{area}.response.json"))}


@router.post("/areas/{area}/response", status_code=202)
def response_build(area: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    _load(area)
    area = _area(area)
    def run():
        from .response.build import build

        try:
            build(area)
            _state[area] = {**_state[area], "status": "idle", "error": None}
        except Exception as ex:  # noqa: BLE001
            _state[area] = {**_state[area], "status": "idle", "error": str(ex)[:300]}

    with _lock:
        if any(st.get("status") == "building" for st in _state.values()):
            raise HTTPException(409, "another area's response products are being built; try again shortly")
        _state[area] = {"status": "building", "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "error": None}
        audit.record("build_response", request, area)
        threading.Thread(target=run, daemon=True, name=f"response-{area}").start()
    return {"area": area, "status": "building"}


def _placemark(name: str, lon: float, lat: float, desc: str, style: str) -> str:
    return (f"<Placemark><name>{escape(name)}</name><styleUrl>#{style}</styleUrl>"
            f"<description>{escape(desc)}</description>"
            f"<Point><coordinates>{lon:.6f},{lat:.6f},0</coordinates></Point></Placemark>")


def plan_kml(d: dict[str, Any]) -> str:
    area = d.get("area", "")
    parts = []
    secs = d.get("sectors") or []
    parts.append("<Folder><name>Sectors (USNG 1 km, by priority)</name>" + "".join(
        _placemark(f"{s['priority']}. {s['usng_1km']}", *s["center"],
                   f"Likely Major or Destroyed: {s['major_or_destroyed_expected']}; people in them (night): "
                   f"{s['people_in_severe_expected']}; cut off: {s['cut_off_people']}; "
                   f"buildings: {s['buildings']}; sent to review: {int(s['review_share'] * 100)}%", "sector")
        for s in secs[:40]) + "</Folder>")
    lz = (d.get("landing") or {}).get("candidates") or []
    parts.append("<Folder><name>Landing zone candidates (reconnoitre before use)</name>" + "".join(
        _placemark(f"LZ {i} {c['usng']}", c["lon"], c["lat"],
                   f"Clear about {c['clear_diameter_m']} m across, slope {c['slope_deg']} deg, {c['cover']}; "
                   f"fits {', '.join(c.get('fits') or ['UH-60'])}. Map candidate only: wires, poles and debris "
                   f"are not in the data.", "lz")
        for i, c in enumerate(lz, 1)) + "</Folder>")
    cl = ((d.get("access") or {}).get("isolated_clusters")) or []
    parts.append("<Folder><name>Cut off by road (worst case)</name>" + "".join(
        _placemark(f"Cut off {c['usng']}", *c["center"],
                   f"{c['buildings']} buildings, about {c['people_est']} people, "
                   f"{c['major_or_destroyed']} likely Major or Destroyed", "cutoff")
        for c in cl[:40]) + "</Folder>")
    fac = [f for f in ((d.get("resources") or {}).get("facilities") or []) if f["status"] in ("disrupted", "at_risk")]
    parts.append("<Folder><name>Facilities flagged</name>" + "".join(
        _placemark(f"{(f['name'] or f['kind'].replace('_', ' '))} ({f['status'].replace('_', ' ')})", f["lon"],
                   f["lat"], "; ".join(f["reasons"]), "facility") for f in fac) + "</Folder>")
    styles = "".join(
        f'<Style id="{k}"><IconStyle><color>{c}</color><Icon><href>'
        f"https://maps.google.com/mapfiles/kml/shapes/{icon}.png</href></Icon></IconStyle></Style>"
        for k, c, icon in (("sector", "ff00a5ff", "placemark_square"), ("lz", "ff00ff00", "heliport"),
                           ("cutoff", "ff0000ff", "caution"), ("facility", "ff00ffff", "triangle")))
    return ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            f"<name>Groma response plan: {escape(area)}</name>"
            f"<description>{escape(d.get('disclaimer', ''))}</description>{styles}{''.join(parts)}"
            "</Document></kml>")


@router.get("/areas/{area}/response/plan.kml")
def response_kml(area: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    _load(area)
    kml = plan_kml(_read(area, "response.json"))
    audit.record("export_response_kml", request, area)
    return Response(kml, media_type="application/vnd.google-earth.kml+xml",
                    headers={"Content-Disposition": f'attachment; filename="groma-{area}-response.kml"'})
