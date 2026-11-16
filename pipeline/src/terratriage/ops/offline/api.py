"""Routes for working with no network.

  GET /ops/offline                     is this server offline, is a local basemap
                                       here, which packs were imported
  GET /ops/basemap/style.json          MapLibre style for the local basemap
  GET /ops/basemap/{z}/{x}/{y}.jpg     one local basemap tile (204 if not packed)

Public: the basemap is a public-domain map, and the pack list names areas
and dates only (the area list is public already).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from .. import BASEMAP_DIR
from . import basemap, offline_mode
from .pack import LABELS_NOTE, OFFLINE_LIMITS

router = APIRouter(prefix="/ops")
STYLE_PATH = "/ops/basemap/style.json"
TILE_PATH = "/ops/basemap/{z}/{x}/{y}.jpg"


def _root() -> str:
    # read per request so a test or an import in another process is picked up
    return os.environ.get("NCR_BASEMAP_DIR") or BASEMAP_DIR


@router.get("/offline")
def offline_status():
    cov = basemap.coverage(_root())
    areas = (basemap.read_index(_root()).get("areas") or {})
    return {
        "offline": offline_mode(),
        "basemap": {**cov, "style_url": STYLE_PATH if cov.get("available") else None},
        "packs": [{"area": a, "event_id": v.get("event_id"), "pack_created_utc": v.get("pack_created_utc"),
                   "imported_utc": v.get("imported_utc")} for a, v in sorted(areas.items())],
        "unavailable_offline": OFFLINE_LIMITS if offline_mode() else [],
        "labels": LABELS_NOTE,
    }


@router.get("/basemap/style.json")
def basemap_style(request: Request):
    cov = basemap.coverage(_root())
    if not cov.get("available"):
        raise HTTPException(404, "no offline basemap on this server (import a pack)")
    base = str(request.base_url).rstrip("/")
    return JSONResponse(basemap.style(base + TILE_PATH, cov), headers={"Cache-Control": "no-cache"})


@router.get("/basemap/{z}/{x}/{y}.jpg")
def basemap_tile(z: int, x: int, y: int):
    if not (0 <= z <= 22 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise HTTPException(400, "bad tile")
    p = basemap.tile_path(_root(), z, x, y)
    if not os.path.isfile(p):
        return Response(status_code=204)          # MapLibre draws an empty tile, no console error
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})
