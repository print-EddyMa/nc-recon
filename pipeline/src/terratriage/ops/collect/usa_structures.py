"""FEMA USA Structures (FEMA / ORNL / USGS) building footprints.

Footprints larger than 450 ft^2 with occupancy class, outbuilding flag, height,
address, a modeled population median + 95 % interval, and the date of the
imagery each footprint was digitised from (so its vintage is known per AOI).

Served as an ArcGIS FeatureServer (Esri Federal Data view). Addresses are
responder-mode only (see disseminate/exports.py `public` mode, which drops
them).
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..cachekey import cache_key
from ..provenance import Provenance
from .base import Connector, DiskCache, Layer, SchemaError, http_json

SERVICE = ("https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/"
           "USA_Structures_View/FeatureServer/0")
FIELDS = ("BUILD_ID,OCC_CLS,PRIM_OCC,SEC_OCC,PROP_ADDR,PROP_CITY,PROP_ZIP,OUTBLDG,HEIGHT,"
          "SQMETERS,PROD_DATE,SOURCE,IMAGE_DATE,VAL_METHOD,POP_MEDIAN,POP_CI95_LOWER,"
          "POP_CI95_UPPER,UUID,FIPS,CENSUSCODE")


def _ms_date(v) -> str | None:
    if v in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return str(v)


class USAStructures(Connector):
    name = "usa_structures"
    license = "US Government work (FEMA/ORNL); public"
    homepage = "https://gis-fema.hub.arcgis.com/pages/usa-structures"
    stale_after_s = 3 * 365 * 86400

    def __init__(self) -> None:
        self.cache = DiskCache("usa_structures")

    def fetch(self, bbox_lonlat: tuple[float, float, float, float]) -> Layer:
        key = cache_key("usa_structures", geometry=bbox_lonlat, dataset_version="view")
        feats = self.cache.get(key)
        if feats is None:
            w, s, e, n = bbox_lonlat
            feats, offset = [], 0
            while True:
                d = http_json(f"{SERVICE}/query", params={
                    "where": "1=1", "geometry": f"{w},{s},{e},{n}",
                    "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects", "outFields": FIELDS,
                    "returnGeometry": "true", "f": "geojson",
                    "resultOffset": offset, "resultRecordCount": 2000,
                }, timeout=120)
                page = d.get("features")
                if not isinstance(page, list):
                    raise SchemaError(f"USA Structures: no feature list ({str(d)[:200]})")
                feats.extend(page)
                offset += len(page)
                if not page or (not d.get("exceededTransferLimit") and not
                                (d.get("properties") or {}).get("exceededTransferLimit")):
                    if len(page) < 2000:
                        break
                if offset > 200_000:
                    break
            self.cache.put(key, feats)
        for f in feats[:5]:
            if "BUILD_ID" not in (f.get("properties") or {}):
                raise SchemaError("USA Structures feature missing BUILD_ID")
        for f in feats:
            p = f["properties"]
            p["PROD_DATE"] = _ms_date(p.get("PROD_DATE"))
            p["IMAGE_DATE"] = _ms_date(p.get("IMAGE_DATE"))
        dates = sorted(d for d in (f["properties"].get("IMAGE_DATE") for f in feats) if d)
        prov = Provenance(
            source="FEMA USA Structures", source_url=SERVICE, license=self.license,
            dataset_version=f"footprint imagery {dates[0]}..{dates[-1]}" if dates else None,
            crs="EPSG:4326", horizontal_datum="WGS 84 (as served)",
            units="SQMETERS m^2; HEIGHT m",
        )
        return Layer({"type": "FeatureCollection", "features": feats}, prov)

    def probe(self) -> float | None:
        d = http_json(f"{SERVICE}/query", params={
            "where": "1=1", "geometry": "-82.181,35.629,-82.179,35.631",
            "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "returnCountOnly": "true", "f": "json"}, timeout=30)
        if "count" not in d:
            raise SchemaError("USA Structures probe: no count")
        return None
