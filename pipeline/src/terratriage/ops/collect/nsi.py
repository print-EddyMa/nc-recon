"""USACE National Structure Inventory (NSI 2022 base) - structure points.

Per structure: Hazus occupancy (RES1 single-family, RES2 manufactured home, ...),
stories, foundation type + height, ground elevation, FEMA flood zone, value,
and day/night population split by age (<65 / >=65).

Caveats recorded in provenance and docs/ops/DATA_SOURCES.md:
  * points, not footprints - matched to footprints in process/structures.py
  * `cbfips` are 2010 census blocks (crosswalk before joining 2020 data)
  * `found_ht` is feet above ground; `grnd_elv_m` is metres, from USGS 3DEP
    (NAVD88); `ground_elv` is the same value in feet
  * -9999 is a "no value" sentinel (e.g. `static_bfe`) -> converted to None
  * population fields are modeled estimates, not a census of occupants
"""
from __future__ import annotations

import time

from ..cachekey import cache_key
from ..provenance import Provenance
from .base import Connector, DiskCache, Layer, SchemaError, http_json

API = "https://nsi.sec.usace.army.mil/nsiapi/structures"
REQUIRED = ("fd_id", "occtype", "x", "y", "found_ht", "grnd_elv_m", "num_story")
SENTINELS = (-9999, -9999.0, "-9999")


def _clean(p: dict) -> dict:
    return {k: (None if v in SENTINELS else v) for k, v in p.items()}


class NSI(Connector):
    name = "nsi"
    license = "US Government work (USACE); public"
    homepage = "https://nsi.sec.usace.army.mil/"
    stale_after_s = 365 * 86400  # a static inventory; age is the release, not the fetch

    def __init__(self) -> None:
        self.cache = DiskCache("nsi")

    def fetch(self, bbox_lonlat: tuple[float, float, float, float]) -> Layer:
        w, s, e, n = bbox_lonlat
        key = cache_key("nsi_structures", geometry=bbox_lonlat, dataset_version="2022")
        data = self.cache.get(key)
        if data is None:
            ring = f"{w},{s},{e},{s},{e},{n},{w},{n},{w},{s}"
            data = http_json(API, params={"bbox": ring, "fmt": "fc"}, timeout=120)
            self.cache.put(key, data)
        feats = data.get("features")
        if not isinstance(feats, list):
            raise SchemaError("NSI response has no feature list")
        out = []
        for f in feats:
            p = f.get("properties") or {}
            miss = [k for k in REQUIRED if k not in p]
            if miss:
                raise SchemaError(f"NSI feature missing {miss}")
            out.append({"type": "Feature", "geometry": f["geometry"], "properties": _clean(p)})
        prov = Provenance(
            source="USACE National Structure Inventory",
            source_url=API,
            license=self.license,
            dataset_version="NSI 2022 base",
            crs="EPSG:4326", horizontal_datum="WGS 84 (as served)",
            vertical_datum="NAVD88 (grnd_elv_m, from USGS 3DEP)",
            units="found_ht ft above ground; grnd_elv_m m; sqft ft^2; values USD",
            processing_chain=("-9999 sentinels -> null",),
        )
        return Layer({"type": "FeatureCollection", "features": out}, prov)

    def probe(self) -> float | None:
        ring = "-82.181,35.629,-82.179,35.629,-82.179,35.631,-82.181,35.631,-82.181,35.629"
        t0 = time.time()
        d = http_json(API, params={"bbox": ring, "fmt": "fc"}, timeout=30)
        if not isinstance(d.get("features"), list):
            raise SchemaError("NSI probe: no feature list")
        _ = t0
        return None
