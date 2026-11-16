"""OpenStreetMap via the Overpass API: response resources and the road network.

Keyless and worldwide, so it works for any event. OSM is community-mapped:
coverage of hospitals, fire stations and roads is good in the US; water works,
substations and towers are patchier. Every record keeps its OSM id so a
responder can check it, and nothing here is treated as authoritative status.
Licence: ODbL 1.0 (attribution; share-alike for derived databases).
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

from ..provenance import Provenance
from .base import USER_AGENT, DiskCache, SourceUnavailable

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
LICENSE = "OpenStreetMap contributors, ODbL 1.0"

# (lifeline, kind) for an OSM tag. Lifelines follow FEMA's Community Lifelines.
RESOURCE_TAGS: list[tuple[str, str, str, str]] = [
    # key, value, lifeline, kind
    ("amenity", "hospital", "health_medical", "hospital"),
    ("amenity", "clinic", "health_medical", "clinic"),
    ("healthcare", "dialysis", "health_medical", "dialysis"),
    ("amenity", "nursing_home", "health_medical", "nursing_home"),
    ("social_facility", "nursing_home", "health_medical", "nursing_home"),
    ("social_facility", "assisted_living", "health_medical", "nursing_home"),
    ("amenity", "pharmacy", "health_medical", "pharmacy"),
    ("amenity", "fire_station", "safety_security", "fire_station"),
    ("emergency", "ambulance_station", "safety_security", "ems_station"),
    ("amenity", "police", "safety_security", "police"),
    ("amenity", "school", "food_water_shelter", "school"),
    ("amenity", "community_centre", "food_water_shelter", "community_centre"),
    ("social_facility", "shelter", "food_water_shelter", "shelter"),
    ("shop", "supermarket", "food_water_shelter", "grocery"),
    ("power", "substation", "energy", "substation"),
    ("power", "plant", "energy", "power_plant"),
    ("amenity", "fuel", "energy", "fuel"),
    ("telecom", "exchange", "communications", "telecom_exchange"),
    ("tower:type", "communication", "communications", "comms_tower"),
    ("man_made", "water_works", "water_systems", "water_treatment"),
    ("man_made", "wastewater_plant", "water_systems", "wastewater_treatment"),
    ("man_made", "water_tower", "water_systems", "water_tower"),
    ("aeroway", "helipad", "transportation", "helipad"),
    ("aeroway", "aerodrome", "transportation", "airport"),
]
ROAD_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
                "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
                "living_street", "service", "track")


def overpass(query: str, cache_key: str, max_age_s: float = 3 * 86400, retries: int = 4) -> dict[str, Any]:
    cache = DiskCache("osm")
    hit = cache.get(cache_key, max_age_s)
    if hit is not None:
        return hit
    last: Exception | None = None
    for attempt in range(retries):
        ep = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(ep, data=urllib.parse.urlencode({"data": query}).encode(),
                                         headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=200) as r:  # noqa: S310
                data = json.loads(r.read())
            if "elements" not in data:
                raise ValueError("Overpass response has no elements")
            cache.put(cache_key, data)
            return data
        except Exception as ex:  # noqa: BLE001 - busy servers return 429/504
            last = ex
            time.sleep(4 + attempt * 6)
    raise SourceUnavailable(f"Overpass unreachable: {last}")


def _key(prefix: str, bbox) -> str:
    return prefix + "_" + "_".join(f"{v:.4f}" for v in bbox).replace("-", "m").replace(".", "p")


def provenance(what: str) -> Provenance:
    return Provenance(source=f"OpenStreetMap via Overpass API ({what})", source_url=ENDPOINTS[0],
                      license=LICENSE, crs="EPSG:4326", horizontal_datum="WGS 84")


def resources(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Response resources in the box, one record per facility."""
    w, s, e, n = bbox
    parts = "".join(f'nwr["{k}"="{v}"]({s},{w},{n},{e});' for k, v, _, _ in RESOURCE_TAGS)
    data = overpass(f"[out:json][timeout:180];({parts});out center tags;", _key("res", bbox))
    out, seen = [], set()
    for el in data["elements"]:
        tags = el.get("tags") or {}
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        if lon is None or lat is None:
            continue
        for k, v, lifeline, kind in RESOURCE_TAGS:
            if tags.get(k) == v:
                oid = f"{el['type']}/{el['id']}"
                if (oid, kind) in seen:
                    break
                seen.add((oid, kind))
                out.append({"id": oid, "kind": kind, "lifeline": lifeline, "name": tags.get("name"),
                            "lon": round(lon, 6), "lat": round(lat, 6),
                            "emergency": tags.get("emergency"), "beds": tags.get("beds"),
                            "operator": tags.get("operator")})
                break
    return out


def roads(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Drivable ways with geometry: id, class, name, bridge flag, coordinates."""
    w, s, e, n = bbox
    rx = "|".join(ROAD_CLASSES)
    data = overpass(f'[out:json][timeout:180];way["highway"~"^({rx})$"]({s},{w},{n},{e});out geom tags;',
                    _key("roads", bbox))
    out = []
    for el in data["elements"]:
        g = el.get("geometry") or []
        if len(g) < 2:
            continue
        t = el.get("tags") or {}
        out.append({"id": f"way/{el['id']}", "highway": t.get("highway"), "name": t.get("name") or t.get("ref"),
                    "bridge": t.get("bridge") not in (None, "no"), "oneway": t.get("oneway") == "yes",
                    "access": t.get("access"), "coords": [(p["lon"], p["lat"]) for p in g]})
    return out
