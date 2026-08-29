"""The Phase A -> Phase B contract.

Phase A (this package) emits a single GeoJSON FeatureCollection. Phase B (the web
app) consumes it and never needs to know how it was produced. Everything about
that file's shape lives here so both sides can import the same source of truth.

FeatureCollection
-----------------
{
  "type": "FeatureCollection",
  "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
  "properties": {                      # collection-level metadata (see RunMeta)
    "event": "HurricaneHelene-Oct24",
    "area": "old_fort",
    "generated": "2026-08-29T12:00:00Z",
    "model": "xview2_1st_place:res34+se50 (loc+cls ensemble)",
    "pre_image":  {"date": "2022-01-07", "source": "Maxar Open Data", "catalog_id": "..."},
    "post_image": {"date": "2024-10-05", "source": "Maxar Open Data", "catalog_id": "..."},
    "counts": {"0": 812, "1": 96, "2": 141, "3": 77},
    "n_buildings": 1126
  },
  "features": [Feature, ...]
}

Feature (one building)
----------------------
{
  "type": "Feature",
  "geometry": {"type": "Polygon", "coordinates": [[[lon, lat], ...]]},   # EPSG:4326, lon/lat
  "properties": {
    "id": "old_fort-000042",
    "damage_class": 2,              # 0..3, integer, see DAMAGE_CLASSES
    "damage_label": "major-damage",
    "confidence": 0.71,            # mean per-pixel softmax prob for the winning class, 0..1
    "area_m2": 143.6,             # footprint area in square metres (UTM)
    "centroid": [lon, lat]
  }
}

Damage scale
------------
The xView2 / xBD four-class scale, re-based to 0..3 (xView2 masks use 1..4 with 0
meaning "no building"; we drop the background class since every Feature *is* a
building).

  0  no-damage      structure intact
  1  minor-damage   roofline / envelope partially compromised, surrounding damage
  2  major-damage   partial collapse, significant structural failure, burn-through
  3  destroyed      structure no longer standing / scoured away
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"
CRS84 = {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}

# index -> (machine label, human label, hex). The hex ramp is the damage-severity
# scale the web app keys off; it is deliberately the one saturated thing in the
# palette. Sequential yellow -> deep red, colour-blind-safe, dark-bg legible.
DAMAGE_CLASSES: list[tuple[str, str, str]] = [
    ("no-damage", "No damage", "#f5d76e"),
    ("minor-damage", "Minor damage", "#e8894a"),
    ("major-damage", "Major damage", "#d1495b"),
    ("destroyed", "Destroyed", "#8b1e3f"),
]
LABELS = [c[0] for c in DAMAGE_CLASSES]
COLORS = {i: c[2] for i, c in enumerate(DAMAGE_CLASSES)}

# xView2 mask value (1..4) -> our class index (0..3)
XVIEW2_MASK_TO_CLASS = {1: 0, 2: 1, 3: 2, 4: 3}


@dataclass
class ImageMeta:
    date: str
    source: str = "Maxar Open Data"
    catalog_id: str | None = None
    gsd: float | None = None
    url: str | None = None


@dataclass
class RunMeta:
    event: str
    area: str
    model: str
    pre_image: ImageMeta
    post_image: ImageMeta
    generated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    schema_version: str = SCHEMA_VERSION
    tile_size: int = 1024
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def feature(
    fid: str,
    polygon_lonlat: list[list[tuple[float, float]]],
    damage_class: int,
    confidence: float,
    area_m2: float,
    centroid_lonlat: tuple[float, float],
) -> dict[str, Any]:
    """Build one contract-compliant Feature."""
    if damage_class not in (0, 1, 2, 3):
        raise ValueError(f"damage_class must be 0..3, got {damage_class!r}")
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": polygon_lonlat},
        "properties": {
            "id": fid,
            "damage_class": int(damage_class),
            "damage_label": LABELS[damage_class],
            "confidence": round(float(confidence), 4),
            "area_m2": round(float(area_m2), 2),
            "centroid": [round(centroid_lonlat[0], 6), round(centroid_lonlat[1], 6)],
        },
    }


def collection(features: list[dict[str, Any]], meta: RunMeta) -> dict[str, Any]:
    counts = {str(i): 0 for i in range(4)}
    for f in features:
        counts[str(f["properties"]["damage_class"])] += 1
    props = meta.to_dict()
    props["counts"] = counts
    props["n_buildings"] = len(features)
    return {
        "type": "FeatureCollection",
        "crs": CRS84,
        "properties": props,
        "features": features,
    }


def validate(fc: dict[str, Any]) -> list[str]:
    """Cheap structural check. Returns a list of problems ([] == valid)."""
    problems: list[str] = []
    if fc.get("type") != "FeatureCollection":
        problems.append("top-level type is not FeatureCollection")
    for i, f in enumerate(fc.get("features", [])):
        p = f.get("properties", {})
        if f.get("geometry", {}).get("type") != "Polygon":
            problems.append(f"feature {i}: geometry is not a Polygon")
        if p.get("damage_class") not in (0, 1, 2, 3):
            problems.append(f"feature {i}: bad damage_class {p.get('damage_class')!r}")
        ring = f.get("geometry", {}).get("coordinates", [[]])[0]
        if len(ring) < 4:
            problems.append(f"feature {i}: polygon ring has < 4 vertices")
        else:
            for lon, lat in ring:
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    problems.append(f"feature {i}: coordinate out of range ({lon},{lat})")
                    break
    return problems
