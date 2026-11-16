"""Civil Air Patrol photos beside a building, for Verify reviewers.

  GET /ops/photos/{area}/{ncr_id}          frames that probably show the building
  GET /ops/photos/{area}/thumb/{key}.jpg   a ~1600 px copy of one frame

Responder-only, like the image chips. Context for people judging a building,
never an input to the damage call (collect/cap_photos.py).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse

from . import audit
from .api import _load, _responder
from .collect import cap_photos

router = APIRouter(prefix="/ops")
_bbox: dict[str, tuple[float, tuple[float, float, float, float]]] = {}


def _area_points(area: str, fc: dict[str, Any]) -> tuple[list[dict], str | None]:
    from .plan.events import event_for_area

    found = event_for_area(area)
    if not found:
        return [], "this area is not registered to an event"
    ev, _ = found
    if not cap_photos.project_for(ev.id):
        return [], f"no Civil Air Patrol collection is registered for {ev.name}"
    xs = [f["properties"]["centroid"] for f in fc.get("features", []) if (f.get("properties") or {}).get("centroid")]
    if not xs:
        return [], "this assessment has no structures"
    bbox = (min(x for x, _ in xs), min(y for _, y in xs), max(x for x, _ in xs), max(y for _, y in xs))
    begin = ev.incident_begin if isinstance(ev.incident_begin, date) else None
    try:
        return cap_photos.points(ev.id, bbox, begin), None
    except Exception as ex:  # noqa: BLE001 - reviewer context; never fails the screen
        return [], f"Civil Air Patrol photo index unavailable ({type(ex).__name__})"


@router.get("/photos/{area}/{ncr_id}")
def photos(area: str, ncr_id: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    fc = _load(area)
    f = next((f for f in fc.get("features", []) if (f.get("properties") or {}).get("ncr_id") == ncr_id), None)
    if f is None:
        raise HTTPException(404, "no such structure in this area")
    audit.record("view_photos", request, area, ncr_id=ncr_id)
    pts, note = _area_points(area, fc)
    lon, lat = f["properties"]["centroid"]
    out = cap_photos.near(lon, lat, pts) if pts else []
    return {"area": area, "ncr_id": ncr_id, "photos": out, "note": note,
            "source": "Civil Air Patrol aerial photos (FEMA)",
            "caveat": "The building is not marked. Obliques were taken pointing toward it; it can still be outside the frame."}


@router.get("/photos/{area}/thumb/{key}.jpg")
def photo_thumb(area: str, key: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    fc = _load(area)
    try:
        cap_photos.thumb_path(key)
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from ex
    pts, _ = _area_points(area, fc)
    try:
        p = cap_photos.thumbnail(key, pts)
    except KeyError as ex:
        raise HTTPException(404, "no such photo for this area") from ex
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(502, f"could not fetch the photo ({type(ex).__name__})") from ex
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
