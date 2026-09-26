"""Server-side versions of the Conditions-map feeds that browsers cannot read
directly (no CORS): NCDOT DriveNC closures/incidents and cameras, and NHC
active Atlantic storms. Output matches the web's NCPointFC shape and the
committed snapshots written by web/scripts/refresh_nc_snapshots.mjs, so the
browser can use either. Fixed upstream URLs only (no user-supplied URLs).
"""
from __future__ import annotations

import time

from ..geodesy import NC_BBOX
from .base import SchemaError, http_json

DRIVENC = "https://www.drivenc.gov/map/mapIcons/{kind}"
NHC = "https://www.nhc.noaa.gov/CurrentStorms.json"
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
