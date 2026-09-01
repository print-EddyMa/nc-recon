"""North Carolina context priors for the damage-fusion step.

The damage model looks only at the pre/post image crop. These priors add cheap,
independent signal about whether damage at a location is *plausible*:

  flood_stage   nearest NWPS gauge's worst (observed/forecast) flood category,
                0 none .. 3 major, or None
  in_fema_decl  is the AOI inside an NC county with an active/recent federal
                disaster declaration
  slope_deg     terrain slope at the AOI, from USGS point-elevation queries

All three are network calls; every one degrades to None/False on any failure, so
the caller can always run. Used only when `run.py infer --nc-context` is set.
"""
from __future__ import annotations

import concurrent.futures
import json
import math
import urllib.parse
import urllib.request
from typing import Any

_UA = {"User-Agent": "TerraTriage/1.2 (nc context priors)"}
_FLOOD_SEV = {"major": 3, "moderate": 2, "minor": 1, "action": 1, "no_flooding": 0}


def _get(url: str, timeout: int = 15) -> Any:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def nearest_flood_stage(lon: float, lat: float, pad_deg: float = 0.4) -> int | None:
    """Worst flood category among NWPS gauges within ~pad_deg of the point."""
    try:
        url = (
            "https://api.water.noaa.gov/nwps/v1/gauges?"
            f"bbox.xmin={lon - pad_deg}&bbox.ymin={lat - pad_deg}"
            f"&bbox.xmax={lon + pad_deg}&bbox.ymax={lat + pad_deg}&srid=EPSG_4326"
        )
        data = _get(url)
    except Exception as ex:  # noqa: BLE001
        print(f"[context] NWPS lookup failed: {ex}")
        return None
    worst = -1
    for g in data.get("gauges", []):
        st = g.get("status") or {}
        for part in ("observed", "forecast"):
            cat = ((st.get(part) or {}).get("floodCategory") or "").lower()
            if cat in _FLOOD_SEV:
                worst = max(worst, _FLOOD_SEV[cat])
    return worst if worst >= 0 else None


def in_fema_declaration(lat: float, lon: float, months_back: int = 18) -> bool:
    """True if an NC federal disaster declaration's incident period is recent."""
    import datetime as dt

    cutoff = (dt.date.today() - dt.timedelta(days=30 * months_back)).isoformat()
    try:
        flt = urllib.parse.quote(
            f"state eq 'NC' and incidentBeginDate ge '{cutoff}'", safe=""
        )
        url = (
            "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries?"
            f"$filter={flt}&$select=disasterNumber,incidentType&$top=200"
        )
        data = _get(url)
    except Exception as ex:  # noqa: BLE001
        print(f"[context] OpenFEMA lookup failed: {ex}")
        return False
    return len(data.get("DisasterDeclarationsSummaries", [])) > 0


def _elev(x: float, y: float) -> float | None:
    try:
        url = (
            "https://epqs.nationalmap.gov/v1/json?"
            f"x={x}&y={y}&units=Meters&wkid=4326&includeDate=false"
        )
        d = _get(url, timeout=8)
        v = float(d["value"])
        return v if v > -1e5 else None
    except Exception:  # noqa: BLE001
        return None


def terrain_slope_deg(lon: float, lat: float, step_m: float = 90.0) -> float | None:
    """Slope from four USGS point-elevation samples around the AOI centroid.

    EPQS is slow and flaky, so the four probes run in parallel; any failure
    returns None (the caller treats a missing slope as "no signal").
    """
    dlat = step_m / 111_320.0
    dlon = step_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    pts = [(lon, lat + dlat), (lon, lat - dlat), (lon + dlon, lat), (lon - dlon, lat)]
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            n, s, e, w = list(ex.map(lambda p: _elev(*p), pts, timeout=12))
    except Exception:  # noqa: BLE001
        return None
    if None in (n, s, e, w):
        return None
    dz_dy = (n - s) / (2 * step_m)
    dz_dx = (e - w) / (2 * step_m)
    return round(math.degrees(math.atan(math.hypot(dz_dx, dz_dy))), 1)


def nc_priors(lon: float, lat: float, *, with_slope: bool = True) -> dict[str, Any]:
    """All three priors for an AOI centroid, fetched concurrently. Safe: every
    field is None/False on error, so the caller can always proceed."""
    jobs: dict[str, concurrent.futures.Future] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        jobs["flood_stage"] = ex.submit(nearest_flood_stage, lon, lat)
        jobs["in_fema_decl"] = ex.submit(in_fema_declaration, lat, lon)
        if with_slope:
            jobs["slope_deg"] = ex.submit(terrain_slope_deg, lon, lat)

    def _safe(key: str, default: Any) -> Any:
        f = jobs.get(key)
        if f is None:
            return default
        try:
            return f.result(timeout=30)
        except Exception as ex:  # noqa: BLE001
            print(f"[context] {key} failed: {ex}")
            return default

    priors = {
        "flood_stage": _safe("flood_stage", None),
        "in_fema_decl": bool(_safe("in_fema_decl", False)),
        "slope_deg": _safe("slope_deg", None),
    }
    print(f"[context] NC priors @ {lat:.4f},{lon:.4f}: {priors}")
    return priors
