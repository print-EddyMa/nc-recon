"""Response products built on an assessment: what responders do with damage.

  resources   lifeline facilities around the area and their likely status
  access      road network, blocked and uncertain segments, isolated
              buildings and people, travel time to hospitals, access routes
  landing     helicopter landing-zone candidates near isolated or hard-hit places
  money       expected building losses, debris volume, FEMA threshold context
  sectors     US National Grid 1 km cells ranked for search and assignment

Every product is decision support from open data, labelled with its sources
and assumptions, and written beside the assessment as
data/output/ops/<area>.response.json (+ <area>.response.layers.json layers).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any

from .. import OPS_OUT



@dataclass
class AreaRun:
    area: str
    features: list[dict[str, Any]]          # assessed structures (GeoJSON features)
    run: dict[str, Any]                     # FeatureCollection properties
    event: Any
    bbox: tuple[float, float, float, float]  # assessed structures' extent, lon/lat
    not_assessed: int = 0                     # inventory points with no footprint (unknown, never undamaged)

    @property
    def center(self) -> tuple[float, float]:
        w, s, e, n = self.bbox
        return (w + e) / 2, (s + n) / 2


def load_area(area: str) -> AreaRun:
    from ..plan.events import event_for_area

    with open(os.path.join(OPS_OUT, f"{area}.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    found = event_for_area(area)
    if not found:
        raise SystemExit(f"{area} is not a registered area")
    feats = [f for f in fc["features"] if (f.get("properties") or {}).get("damage_level")]
    xs, ys = [], []
    for f in feats:
        c = (f.get("properties") or {}).get("centroid")
        if c:
            xs.append(c[0])
            ys.append(c[1])
    if not xs:
        raise SystemExit(f"{area}: assessment has no structures")
    return AreaRun(area, feats, fc.get("properties") or {}, found[0],
                   (min(xs), min(ys), max(xs), max(ys)), len(fc["features"]) - len(feats))


def pad_bbox(bbox, km: float) -> tuple[float, float, float, float]:
    w, s, e, n = bbox
    dlat = km / 110.54
    dlon = km / (111.32 * math.cos(math.radians((s + n) / 2)))
    return w - dlon, s - dlat, e + dlon, n + dlat


def local_xy(lon0: float, lat0: float):
    """Equirectangular metres around a point: fine at town scale (< 30 km)."""
    kx = 111320.0 * math.cos(math.radians(lat0))
    return lambda lon, lat: ((lon - lon0) * kx, (lat - lat0) * 110540.0)


def p_severe(props: dict[str, Any]) -> float:
    p = props.get("damage_probs") or {}
    return float((p.get("major") or 0.0) + (p.get("destroyed") or 0.0))


def occupants(props: dict[str, Any]) -> float:
    o = props.get("occupants") or {}
    for k in ("nsi_estimate", "usa_structures_median"):
        v = o.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0
