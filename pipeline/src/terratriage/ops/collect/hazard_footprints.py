"""Where the hazard reached, and how hard: per-building context for any event.

Keyless public sources (checked 2026-10-22):
  wildfire    NIFC WFIGS interagency fire perimeters (ArcGIS FeatureServer),
              perimeters discovered within the event's first days
  earthquake  USGS ComCat + ShakeMap grid.xml (MMI on a ~1.8 km grid)
  landslide   NC Geological Survey landslide inventory (ArcGIS FeatureServer),
              source / transport / deposit polygons tagged with the storm

Each collector returns a `Footprint` for one area, or None when the source has
nothing there; a source being down raises SourceUnavailable so the caller can
record it and carry on (the hazard prior is context, never the whole call).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
from shapely.geometry import shape
from shapely.ops import unary_union

from ..provenance import Provenance
from .base import DiskCache, SchemaError, SourceUnavailable, http_json

WFIGS = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
         "WFIGS_Interagency_Perimeters/FeatureServer/0/query")
COMCAT = "https://earthquake.usgs.gov/fdsnws/event/1/query"
NCGS_LS = ("https://services2.arcgis.com/kCu40SDxsCGcuUWO/arcgis/rest/services/"
           "NC_Landslide_Inventory/FeatureServer/2/query")


@dataclass
class Footprint:
    hazard: str
    provenance: Provenance
    geom: Any = None                      # shapely (multi)polygon, lon/lat
    grid: "ShakeGrid | None" = None
    features: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"hazard": self.hazard, "summary": self.summary, "provenance": self.provenance.to_dict()}


def _arcgis_geojson(url: str, params: dict[str, Any], page: int = 1000, max_pages: int = 50) -> list[dict[str, Any]]:
    """All features, paged: services cap a response at their maxRecordCount
    (2,000 for the NCGS inventory) and a silent cap would drop blocks."""
    out: list[dict[str, Any]] = []
    for k in range(max_pages):
        d = http_json(url, params={**params, "f": "geojson", "outSR": 4326, "inSR": 4326,
                                   "geometryType": "esriGeometryEnvelope", "spatialRel": "esriSpatialRelIntersects",
                                   "returnGeometry": "true", "resultOffset": k * page, "resultRecordCount": page,
                                   "orderByFields": "OBJECTID"}, timeout=90)
        if not isinstance(d, dict) or "features" not in d:
            raise SchemaError(f"unexpected ArcGIS response: {str(d)[:160]}")
        out += d["features"]
        more = d.get("exceededTransferLimit") or (d.get("properties") or {}).get("exceededTransferLimit")
        if len(d["features"]) < page and not more:
            break
    return out


# --------------------------------------------------------------------------- #
# wildfire
# --------------------------------------------------------------------------- #
def fire_perimeters(bbox: tuple[float, float, float, float], incident_begin: date,
                    days: int = 30) -> Footprint | None:
    """Final (or latest) perimeters of fires discovered from 3 days before the
    incident to `days` after, intersecting the area."""
    lo = (incident_begin - timedelta(days=3)).isoformat()
    hi = (incident_begin + timedelta(days=days)).isoformat()
    w, s, e, n = bbox
    try:
        feats = _arcgis_geojson(WFIGS, {
            "where": f"attr_FireDiscoveryDateTime >= TIMESTAMP '{lo} 00:00:00' "
                     f"AND attr_FireDiscoveryDateTime <= TIMESTAMP '{hi} 00:00:00'",
            "geometry": f"{w},{s},{e},{n}",
            "outFields": "poly_IncidentName,attr_UniqueFireIdentifier,poly_GISAcres,"
                         "attr_FireDiscoveryDateTime,poly_FeatureCategory,poly_DateCurrent",
            "geometryPrecision": 6})
    except SchemaError:
        raise
    except Exception as ex:  # noqa: BLE001
        raise SourceUnavailable(f"NIFC WFIGS perimeters: {ex}") from ex
    polys = [shape(f["geometry"]) for f in feats if f.get("geometry")]
    if not polys:
        return None
    fires = sorted({(f["properties"].get("poly_IncidentName"), f["properties"].get("attr_UniqueFireIdentifier"))
                    for f in feats})
    return Footprint(
        "wildfire",
        Provenance(source="NIFC WFIGS Interagency Fire Perimeters", source_url=WFIGS.rsplit("/", 1)[0],
                   license="US Government (NIFC); public", crs="EPSG:4326", horizontal_datum="WGS 84",
                   dataset_version=f"fires discovered {lo}..{hi}"),
        geom=unary_union(polys), features=[f["properties"] for f in feats],
        summary={"fires": [{"name": a, "id": b} for a, b in fires]})


# --------------------------------------------------------------------------- #
# earthquake
# --------------------------------------------------------------------------- #
class ShakeGrid:
    """ShakeMap grid.xml: regular lon/lat grid of MMI (and PGA etc.)."""

    def __init__(self, lon0: float, lat0: float, dlon: float, dlat: float, mmi: np.ndarray):
        self.lon0, self.lat0, self.dlon, self.dlat, self.mmi = lon0, lat0, dlon, dlat, mmi

    @classmethod
    def parse(cls, text: str) -> "ShakeGrid":
        root = ET.fromstring(text)
        ns = {"s": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
        q = (lambda t: f"s:{t}") if ns else (lambda t: t)
        spec = root.find(q("grid_specification"), ns)
        if spec is None:
            raise SchemaError("ShakeMap grid.xml has no grid_specification")
        nlon, nlat = int(spec.get("nlon")), int(spec.get("nlat"))
        fields = {f.get("name"): int(f.get("index")) - 1 for f in root.findall(q("grid_field"), ns)}
        if "MMI" not in fields:
            raise SchemaError("ShakeMap grid.xml has no MMI field")
        data = np.array(root.find(q("grid_data"), ns).text.split(), dtype=float).reshape(-1, len(fields))
        if data.shape[0] != nlon * nlat:
            raise SchemaError("ShakeMap grid.xml size mismatch")
        lon, lat = data[:, fields["LON"]], data[:, fields["LAT"]]
        mmi = data[:, fields["MMI"]].reshape(nlat, nlon)       # rows north to south
        return cls(float(lon.min()), float(lat.max()), float(spec.get("nominal_lon_spacing")),
                   float(spec.get("nominal_lat_spacing")), mmi)

    def at(self, lon: float, lat: float) -> float | None:
        c = (lon - self.lon0) / self.dlon
        r = (self.lat0 - lat) / self.dlat
        if not (0 <= c <= self.mmi.shape[1] - 1 and 0 <= r <= self.mmi.shape[0] - 1):
            return None
        c0, r0 = int(min(c, self.mmi.shape[1] - 2)), int(min(r, self.mmi.shape[0] - 2))
        fc, fr = c - c0, r - r0
        m = self.mmi
        return float((m[r0, c0] * (1 - fc) + m[r0, c0 + 1] * fc) * (1 - fr)
                     + (m[r0 + 1, c0] * (1 - fc) + m[r0 + 1, c0 + 1] * fc) * fr)


def _download_text(url: str, retries: int = 4) -> str:
    """Large text file (ShakeMap grid.xml is several MB) with retries: the
    USGS CDN sometimes closes the connection part-way."""
    import time
    import urllib.request

    from .base import USER_AGENT

    last: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310
                return r.read().decode()
        except Exception as ex:  # noqa: BLE001 - IncompleteRead, resets
            last = ex
            time.sleep(2 ** i)
    raise SourceUnavailable(f"download failed after {retries} tries: {last}")


def shakemap(bbox: tuple[float, float, float, float], incident_begin: date,
             min_magnitude: float = 4.5) -> Footprint | None:
    """Strongest ShakeMap event within 2 days of the incident whose epicentre
    is within ~1 degree of the area."""
    w, s, e, n = bbox
    cache = DiskCache("shakemap")
    try:
        d = http_json(COMCAT, params={
            "format": "geojson", "producttype": "shakemap", "minmagnitude": min_magnitude,
            "starttime": (incident_begin - timedelta(days=1)).isoformat(),
            "endtime": (incident_begin + timedelta(days=2)).isoformat(),
            "minlatitude": s - 1, "maxlatitude": n + 1, "minlongitude": w - 1, "maxlongitude": e + 1},
            timeout=60)
    except Exception as ex:  # noqa: BLE001
        raise SourceUnavailable(f"USGS ComCat: {ex}") from ex
    evs = sorted(d.get("features") or [], key=lambda f: -(f["properties"].get("mag") or 0))
    if not evs:
        return None
    ev = evs[0]
    key = f"grid_{ev['id']}"
    hit = cache.get(key)
    if hit is not None:
        grid = ShakeGrid(hit["lon0"], hit["lat0"], hit["dlon"], hit["dlat"], np.asarray(hit["mmi"], float))
    else:
        try:
            det = http_json(ev["properties"]["detail"], timeout=60)
            url = det["properties"]["products"]["shakemap"][0]["contents"]["download/grid.xml"]["url"]
        except (KeyError, IndexError) as ex:
            raise SchemaError(f"ShakeMap product missing grid.xml for {ev['id']}") from ex
        except Exception as ex:  # noqa: BLE001
            raise SourceUnavailable(f"ShakeMap detail for {ev['id']}: {ex}") from ex
        grid = ShakeGrid.parse(_download_text(url))
        cache.put(key, {"lon0": grid.lon0, "lat0": grid.lat0, "dlon": grid.dlon, "dlat": grid.dlat,
                        "mmi": np.round(grid.mmi, 2).tolist()})
    p = ev["properties"]
    return Footprint(
        "earthquake",
        Provenance(source="USGS ShakeMap", source_url=p.get("url") or COMCAT,
                   license="US Government (USGS); public domain", crs="EPSG:4326", horizontal_datum="WGS 84",
                   dataset_version=f"{ev['id']} M{p.get('mag')}"),
        grid=grid, summary={"event_id": ev["id"], "magnitude": p.get("mag"), "place": p.get("place")})


# --------------------------------------------------------------------------- #
# landslide
# --------------------------------------------------------------------------- #
def landslides_ncgs(bbox: tuple[float, float, float, float], storm: str) -> Footprint | None:
    """NCGS landslide source, transport and deposit polygons tagged with this
    storm (AssociatedStorm, e.g. '2024/09/27 Helene'). Prehistoric deposits and
    outlines of older slides are left out."""
    w, s, e, n = bbox
    storm = "".join(ch for ch in storm if ch.isalnum() or ch in " -")
    try:
        feats = _arcgis_geojson(NCGS_LS, {
            "where": f"AssociatedStorm LIKE '%{storm}%' AND FeatureType IN "
                     "('Source Area','Transport Zone','Deposit','Source Area (Reactivated)')",
            "geometry": f"{w},{s},{e},{n}",
            "outFields": "FeatureType,LandslideType,ExistenceConfidence,LocationConfidence,AssociatedStorm",
            "geometryPrecision": 6})
    except SchemaError:
        raise
    except Exception as ex:  # noqa: BLE001
        raise SourceUnavailable(f"NCGS landslide inventory: {ex}") from ex
    feats = [f for f in feats if f.get("geometry")]
    if not feats:
        return None
    return Footprint(
        "landslide",
        Provenance(source="NC Geological Survey landslide inventory", source_url=NCGS_LS.rsplit("/", 2)[0],
                   license="NC DEQ / NCGS public service (no licence text)", crs="EPSG:4326",
                   horizontal_datum="WGS 84", dataset_version=f"AssociatedStorm ~ {storm}"),
        geom=unary_union([shape(f["geometry"]) for f in feats]),
        features=[{**f["properties"], "_geom": shape(f["geometry"])} for f in feats],
        summary={"polygons": len(feats), "storm": storm})
