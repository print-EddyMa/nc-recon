"""USGS Water Data OGC APIs (api.waterdata.usgs.gov) - replaces legacy NWIS.

Legacy WaterServices (waterservices.usgs.gov) is scheduled for decommission in
Q1 2027 with planned degradation from Aug 2026; on 2026-09-26 it was already
answering 503. This connector uses the OGC API collections instead:

  monitoring-locations   site metadata (state 37 = NC, site type ST = stream),
                         incl. gauge altitude + vertical datum when published
  latest-continuous      newest instantaneous value per time series
                         (00060 discharge ft^3/s, 00065 gage height ft)

The latest-continuous items carry no state field, so we pull by NC bbox and
join to the NC stream-site list (cached 24 h). A series whose newest value is
older than FRESH_HOURS counts as not reporting. Free API keys (env
NCR_USGS_API_KEY) raise rate limits; keyless works for this volume.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from ..geodesy import NC_BBOX
from ..provenance import Provenance
from .base import Connector, DiskCache, Layer, SchemaError, http_json, parse_utc

BASE = "https://api.waterdata.usgs.gov/ogcapi/v1"
PARAMS = {"00060": ("discharge", "ft^3/s"), "00065": ("gage_height", "ft")}
FRESH_HOURS = 48


class USGSWater(Connector):
    name = "usgs_water"
    license = "US Government work (public domain); credit USGS"
    homepage = "https://api.waterdata.usgs.gov/"
    stale_after_s = 3 * 3600

    def __init__(self) -> None:
        self.cache = DiskCache("usgs_water")

    # -- site list ---------------------------------------------------------- #
    def sites(self, max_age_s: float = 24 * 3600) -> dict[str, dict]:
        hit = self.cache.get("nc_stream_sites", max_age_s=max_age_s)
        if hit is not None:
            return hit
        fc = http_json(
            f"{BASE}/collections/monitoring-locations/items",
            params={
                "f": "json", "limit": 10000, "state_code": "37", "site_type_code": "ST",
                "properties": "monitoring_location_name,county_name,altitude,"
                              "vertical_datum,altitude_accuracy,drainage_area",
            },
            timeout=60,
        )
        feats = fc.get("features")
        if not isinstance(feats, list) or not feats:
            raise SchemaError("monitoring-locations returned no features for NC")
        out: dict[str, dict] = {}
        for f in feats:
            p = f.get("properties") or {}
            g = (f.get("geometry") or {}).get("coordinates")
            if not f.get("id") or not g:
                continue
            out[f["id"]] = {
                "name": p.get("monitoring_location_name"),
                "county": p.get("county_name"),
                "lon": g[0], "lat": g[1],
                "gauge_altitude": p.get("altitude"),
                "gauge_vertical_datum": p.get("vertical_datum"),
                "drainage_area_mi2": p.get("drainage_area"),
            }
        self.cache.put("nc_stream_sites", out)
        return out

    def _latest(self, param: str) -> list[dict]:
        w, s, e, n = NC_BBOX
        fc = http_json(
            f"{BASE}/collections/latest-continuous/items",
            params={"f": "json", "limit": 10000, "bbox": f"{w},{s},{e},{n}", "parameter_code": param},
            timeout=60,
        )
        feats = fc.get("features")
        if not isinstance(feats, list):
            raise SchemaError(f"latest-continuous {param}: no feature list")
        for f in feats[:5]:
            p = f.get("properties") or {}
            for k in ("monitoring_location_id", "time", "value", "unit_of_measure"):
                if k not in p:
                    raise SchemaError(f"latest-continuous {param}: missing {k}")
        return feats

    # -- public ------------------------------------------------------------- #
    def fetch(self, fresh_hours: float = FRESH_HOURS) -> Layer:
        """NC stream gauges with their newest discharge / gage height (GeoJSON)."""
        sites = self.sites()
        now = datetime.now(timezone.utc)
        by_site: dict[str, dict] = {}
        warnings: list[str] = []
        for code, (key, unit) in PARAMS.items():
            for f in self._latest(code):
                p = f["properties"]
                sid = p["monitoring_location_id"]
                if sid not in sites:
                    continue  # bbox catches SC/VA/GA/TN sites
                t = parse_utc(p["time"])
                if t is None or (now - t).total_seconds() > fresh_hours * 3600:
                    continue
                try:
                    v = float(p["value"])
                except (TypeError, ValueError):
                    continue
                rec = by_site.setdefault(sid, {"time": t})
                rec[key] = v
                rec[f"{key}_unit"] = p.get("unit_of_measure") or unit
                rec[f"{key}_approval"] = p.get("approval_status")
                rec["time"] = max(rec["time"], t)
        feats = []
        for sid, rec in sorted(by_site.items()):
            s = sites[sid]
            code = sid.split("-", 1)[-1]
            feats.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
                "properties": {
                    "id": sid,
                    "site_no": code,
                    "name": s["name"],
                    "county": s["county"],
                    "discharge_cfs": rec.get("discharge"),
                    "gage_height_ft": rec.get("gage_height"),
                    "gage_height_is": "stage above the gauge's local datum (not NAVD88)",
                    "gauge_altitude": s.get("gauge_altitude"),
                    "gauge_vertical_datum": s.get("gauge_vertical_datum"),
                    "approval": rec.get("discharge_approval") or rec.get("gage_height_approval"),
                    "observed_utc": rec["time"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "url": f"https://waterdata.usgs.gov/monitoring-location/{sid}/",
                },
            })
        if not feats:
            raise SchemaError("no NC stream gauges reported in the freshness window")
        if len(feats) < 150:
            warnings.append(f"only {len(feats)} NC gauges reporting (expected ~290)")
        newest = max(parse_utc(f["properties"]["observed_utc"]) for f in feats)
        prov = Provenance(
            source="USGS Water Data OGC API (latest-continuous + monitoring-locations)",
            source_url=BASE,
            license=self.license,
            acquired_utc=newest.strftime("%Y-%m-%dT%H:%M:%SZ"),
            crs="EPSG:4326", horizontal_datum="WGS 84 (as served)",
            units="discharge ft^3/s; gage height ft above local gauge datum",
            processing_chain=(f"joined to NC (state 37) stream sites; dropped series older than {fresh_hours} h",),
        )
        return Layer({"type": "FeatureCollection", "features": feats}, prov, warnings)

    def probe(self) -> float | None:
        fc = http_json(
            f"{BASE}/collections/latest-continuous/items",
            params={"f": "json", "limit": 1, "bbox": "-82.6,35.5,-82.4,35.7", "parameter_code": "00065"},
            timeout=20,
        )
        feats = fc.get("features") or []
        if not feats:
            raise SchemaError("probe returned no features")
        t = parse_utc(feats[0]["properties"]["time"])
        return time.time() - t.timestamp() if t else None
