"""NC Emergency Management's per-event peak-stage layer as a water-surface
source for E5 (flood depth).

After Helene, NCEM Risk Management published `Peak_Stage_Helene` on ArcGIS
Online: 222 gauges (NCEM, NCDOT, county and USGS) with the peak stage, the
gauge datum elevation, the peak time and whether the gauge stopped reporting
before the crest. A crest with a datum is a water-surface elevation on that
reach, which is exactly what `analyze.flood` needs and what no federal source
provided for any assessed town (STN high-water marks and NWPS crests all sit
on other reaches).

Rules that keep it honest:
* a gauge that stopped reporting is a lower bound, not a crest: skipped, and
  the run says so;
* the vertical datum is not stated in the layer, so a crest counts as
  NAVD88-verified only when FIMAN's gauge record carries a NAVD88 elevation
  that matches the layer's datum (USGS gauges do); anything else keeps a wide
  sigma and is labelled unverified in the output;
* a crest speaks for its own reach only: `MAX_DIST_M` and the per-km sigma in
  `WSESource` bound its reach, and structures above the water surface get
  "no damage" from the Monte Carlo, not a depth.

Checked 2026-10-07: 222 points, last edited 2024-12-04, no licence text
(NCEM AGOL item). Other events need their own layer here.
"""
from __future__ import annotations

import re
import time
from typing import Any

from ..heights import Elevation
from .base import Connector, DiskCache, SchemaError, http_json

PEAK_LAYERS = {
    # event id substrings -> NCEM layer
    "4827": "https://services1.arcgis.com/YBWrN5qiESVpqi92/arcgis/rest/services/Peak_Stage_Helene/FeatureServer/0/query",
    "helene": "https://services1.arcgis.com/YBWrN5qiESVpqi92/arcgis/rest/services/Peak_Stage_Helene/FeatureServer/0/query",
}
FIMAN_URL = "https://spartagis.ncem.org/arcgis/rest/services/FIMAN/GAGES_ALL/MapServer/0/query"

SIGMA_VERIFIED_M = 0.15      # NAVD88 datum confirmed against FIMAN's gauge record
SIGMA_UNVERIFIED_M = 0.60    # datum elevation stated by the operator only
MAX_DIST_M = 1500.0          # how far along its reach one crest is allowed to speak
PAD_DEG = 0.03               # gauges just outside the town still cover its edge
DATUM_TOL_FT = 0.1


def layer_for(event_id: str) -> str | None:
    e = (event_id or "").lower()
    for key, url in PEAK_LAYERS.items():
        if key in e:
            return url
    return None


def _norm(name: str) -> str:
    s = (name or "").lower().replace("@", " at ").replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _envelope(bbox: tuple[float, float, float, float], pad: float) -> dict[str, str]:
    w, s, e, n = bbox
    return {"geometry": f"{w - pad},{s - pad},{e + pad},{n + pad}", "geometryType": "esriGeometryEnvelope",
            "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"}


def peak_points(url: str, bbox: tuple[float, float, float, float]) -> list[dict]:
    d = http_json(url, params={"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326",
                               "f": "geojson", **_envelope(bbox, PAD_DEG)}, timeout=40)
    if not isinstance(d, dict) or not isinstance(d.get("features"), list):
        raise SchemaError("NCEM peak stage layer: no features array")
    return d["features"]


def fiman_rows(bbox: tuple[float, float, float, float]) -> list[dict]:
    d = http_json(FIMAN_URL, params={"where": "1=1", "returnGeometry": "false", "f": "json",
                                     "outFields": "SITE_ID,NAME,OWNER,GAGE_DATUM,NAVD88_ELEVATION,NGVD29_SITE_ELEVATION,NGVD29_TO_NAVD88",
                                     **_envelope(bbox, PAD_DEG + 0.02)}, timeout=40)
    if not isinstance(d, dict) or not isinstance(d.get("features"), list):
        raise SchemaError("FIMAN gauge layer: no features array")
    return [f.get("attributes") or {} for f in d["features"]]


def datum_check(datum_ft: float, fiman: dict | None) -> tuple[str, float, float]:
    """(status, offset_ft, sigma_m): how far the layer's datum can be trusted
    as NAVD88, from FIMAN's record of the same gauge."""
    if not fiman:
        return "unverified", 0.0, SIGMA_UNVERIFIED_M
    navd = _num(fiman.get("NAVD88_ELEVATION"))
    if navd and abs(navd - datum_ft) <= DATUM_TOL_FT:
        return "navd88_verified", 0.0, SIGMA_VERIFIED_M
    ngvd = _num(fiman.get("NGVD29_SITE_ELEVATION"))
    shift = _num(fiman.get("NGVD29_TO_NAVD88"))
    if ngvd and shift is not None and abs(ngvd - datum_ft) <= DATUM_TOL_FT:
        return "ngvd29_converted", shift, SIGMA_VERIFIED_M
    return "unverified", 0.0, SIGMA_UNVERIFIED_M


def wse_sources(event_id: str, bbox: tuple[float, float, float, float],
                incident_begin: str | None = None, incident_end: str | None = None,
                cache_max_age_s: float = 86400.0) -> tuple[list, list[str], list[dict]]:
    """(sources, warnings, provenance rows) for one town. Never raises on an
    upstream failure: the caller records the warning and E5 stays unavailable."""
    from ..analyze.flood import WSESource

    url = layer_for(event_id)
    warnings: list[str] = []
    if not url:
        return [], [f"no NCEM peak-stage layer is registered for event {event_id}: E5 unavailable"], []
    key = "{}_{:.3f}_{:.3f}_{:.3f}_{:.3f}".format(event_id, *bbox).replace("-", "m").replace(".", "p")
    cache = DiskCache("ncem_peak_stage")
    try:
        hit = cache.get(key, cache_max_age_s)
        if hit is None:
            hit = {"points": peak_points(url, bbox), "fiman": fiman_rows(bbox), "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            cache.put(key, hit)
    except Exception as ex:  # noqa: BLE001 - a secondary source must never cost the assessment
        return [], [f"NCEM peak stage unavailable ({type(ex).__name__}: {str(ex)[:120]}): E5 unavailable"], []

    fiman_by_name = {_norm(r.get("NAME", "")): r for r in hit["fiman"]}
    t0 = _ms(incident_begin)
    t1 = _ms(incident_end)
    sources, prov = [], []
    for f in hit["points"]:
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        c = g.get("coordinates") if g.get("type") == "Point" else None
        name = (p.get("Site_Name") or "").strip()
        peak = _num(p.get("Peak_Elevation"))
        datum = _num(p.get("DATUM"))
        if not c or peak is None or datum is None or not name:
            continue
        ref = f"NCEM peak stage: {name} ({p.get('Owner') or 'unknown owner'})"
        if str(p.get("Stopped_Reporting", "")).strip().lower() == "yes":
            warnings.append(f"{ref}: gauge stopped reporting before the crest; its reading is a lower bound and was not used")
            continue
        when = _num(p.get("Peak_Time"))
        if when is not None and ((t0 is not None and when < t0) or (t1 is not None and when > t1)):
            warnings.append(f"{ref}: peak time outside the incident window; not used")
            continue
        status, shift_ft, sigma = datum_check(datum, fiman_by_name.get(_norm(name)))
        wse_ft = peak + shift_ft
        sources.append(WSESource(kind="gauge_crest", ref=ref, lon=float(c[0]), lat=float(c[1]),
                                 wse=Elevation.of(wse_ft, "ft"), sigma_m=sigma, max_dist_m=MAX_DIST_M))
        prov.append({"ref": ref, "lon": c[0], "lat": c[1], "peak_elevation_ft": peak, "datum_ft": datum,
                     "datum_status": status, "sigma_m": sigma, "max_dist_m": MAX_DIST_M,
                     "peak_rating": p.get("Peak_Rating"), "return_period": p.get("Return_Period"),
                     "peak_time_ms": when, "layer": url.split("/rest/")[0] + "/.../Peak_Stage_Helene"})
        if status == "unverified":
            warnings.append(f"{ref}: vertical datum not verifiable against FIMAN; used with sigma {sigma} m")
    return sources, warnings, prov


def _ms(iso: str | None) -> float | None:
    if not iso:
        return None
    from datetime import datetime, timezone

    dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() * 1000.0


class NCEMPeakStage(Connector):
    name = "ncem_peak_stage"
    license = "NC Emergency Management (ArcGIS Online item; no licence text)"
    homepage = "https://services1.arcgis.com/YBWrN5qiESVpqi92/arcgis/rest/services/Peak_Stage_Helene/FeatureServer/0"
    stale_after_s = 400 * 86400  # a per-event product; staleness is not the question

    def probe(self):
        d = http_json(PEAK_LAYERS["helene"], params={"where": "1=1", "returnCountOnly": "true", "f": "json"}, timeout=30)
        if not isinstance(d, dict) or not d.get("count"):
            raise SchemaError("NCEM peak stage count query returned nothing")
        return None
