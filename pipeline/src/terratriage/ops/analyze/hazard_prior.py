"""Hazard footprint evidence (channel H): where the hazard reached, how hard.

For each hazard of the event that has a built footprint source
(config/hazards.yaml), collect the footprint for the area once, then measure
each building against it:

  wildfire    inside the fire perimeter, or how far outside (metres)
  earthquake  ShakeMap MMI at the building
  landslide   inside a mapped source / transport / deposit zone of the storm

A missing footprint (no fire there, no quake, source down) is recorded and the
channel is simply unavailable; the damage call never depends on it alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import transform as shp_transform

from .. import hazards as hz
from ..collect import hazard_footprints as hf
from .classes import FEMA
from .fusion import Channel, rules


@dataclass
class HazardContext:
    footprints: dict[str, hf.Footprint] = field(default_factory=dict)
    projected: dict[str, Any] = field(default_factory=dict)     # hazard -> geometry in metres
    unavailable: dict[str, str] = field(default_factory=dict)  # hazard -> reason

    def to_dict(self) -> dict[str, Any]:
        return {"footprints": {k: v.to_dict() for k, v in self.footprints.items()},
                "unavailable": dict(self.unavailable)}


def build_context(event, bbox_lonlat: tuple[float, float, float, float],
                  to_metric: Callable[[float, float], tuple[float, float]]) -> HazardContext:
    """Collect the footprints that apply to this event over this area."""
    ctx = HazardContext()
    applicable = [h for h in event.hazards if "H" in (hz.profiles()["hazards"].get(h) or {}).get("channels", [])]
    for h in applicable:
        try:
            if h == "wildfire":
                fp = hf.fire_perimeters(bbox_lonlat, event.incident_begin)
            elif h == "earthquake":
                fp = hf.shakemap(bbox_lonlat, event.incident_begin)
            elif h == "landslide":
                storm = getattr(event, "landslide_storm", None)
                if not storm:
                    ctx.unavailable[h] = "NO_LANDSLIDE_INVENTORY_FOR_EVENT"
                    continue
                fp = hf.landslides_ncgs(bbox_lonlat, storm)
            else:
                ctx.unavailable[h] = "NO_FOOTPRINT_SOURCE"
                continue
        except Exception as ex:  # noqa: BLE001 - context, never fatal
            ctx.unavailable[h] = f"SOURCE_UNAVAILABLE: {str(ex)[:120]}"
            continue
        if fp is None:
            ctx.unavailable[h] = "NO_FOOTPRINT_IN_AREA"
            continue
        ctx.footprints[h] = fp
        if fp.geom is not None:
            ctx.projected[h] = shp_transform(to_metric, fp.geom)
    return ctx


def measure(ctx: HazardContext, footprint_m: Polygon, centroid_ll: tuple[float, float]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "wildfire" in ctx.projected:
        g = ctx.projected["wildfire"]
        inside = g.intersects(footprint_m)
        out["wildfire"] = {"inside": bool(inside),
                           "dist_m": 0.0 if inside else round(float(g.distance(footprint_m)), 1)}
    if "landslide" in ctx.projected:
        g = ctx.projected["landslide"]
        out["landslide"] = {"inside": bool(g.intersects(footprint_m))}
    if "earthquake" in ctx.footprints and ctx.footprints["earthquake"].grid is not None:
        v = ctx.footprints["earthquake"].grid.at(*centroid_ll)
        if v is not None:
            out["earthquake"] = {"mmi": round(v, 2)}
    return out


def channel(ctx: HazardContext | None, m: dict[str, Any] | None) -> Channel:
    """One H channel per building: the product of the per-hazard likelihoods
    (each raised to its weight), so two footprints that agree reinforce."""
    if ctx is None:
        return Channel("H", False, unavailable_reason="NOT_APPLICABLE_FOR_HAZARD")
    if not m:
        reason = "; ".join(f"{k}: {v}" for k, v in ctx.unavailable.items()) or "NO_FOOTPRINT_IN_AREA"
        return Channel("H", False, unavailable_reason=reason[:200])
    cfg = rules()["channels"]["H"]
    logL = np.zeros(len(FEMA))
    reasons: list[str] = []
    used = False
    if "wildfire" in m:
        c, d = cfg["wildfire"], m["wildfire"]
        if d["inside"]:
            logL += c["weight"] * np.log(np.asarray(c["inside"], float))
            reasons.append("H_INSIDE_FIRE_PERIMETER")
            used = True
        elif d["dist_m"] >= c["outside_beyond_m"]:
            logL += c["weight"] * np.log(np.asarray(c["outside"], float))
            reasons.append(f"H_OUTSIDE_FIRE_PERIMETER_{d['dist_m']:.0f}M")
            used = True
        else:
            reasons.append(f"H_NEAR_FIRE_PERIMETER_{d['dist_m']:.0f}M")
    if "earthquake" in m:
        c, mmi = cfg["earthquake"], m["earthquake"]["mmi"]
        b = int(np.searchsorted(c["mmi_bins"], mmi, side="right"))
        logL += c["weight"] * np.log(np.asarray(c["likelihood"][b], float))
        reasons.append(f"H_SHAKEMAP_MMI_{mmi:.1f}")
        used = True
    if m.get("landslide", {}).get("inside"):
        c = cfg["landslide"]
        logL += c["weight"] * np.log(np.asarray(c["inside"], float))
        reasons.append("H_IN_MAPPED_LANDSLIDE")
        used = True
    if not used:
        return Channel("H", True, np.ones(len(FEMA)) / len(FEMA), 0.0, "provisional", reasons, detail=m)
    L = np.exp(logL - logL.max())
    return Channel("H", True, L / L.sum(), 1.0, "provisional", reasons, detail=m)


def centroid_ll(poly: Polygon) -> tuple[float, float]:
    p: Point = poly.centroid
    return p.x, p.y
