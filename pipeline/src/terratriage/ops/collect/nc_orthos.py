"""NC OneMap orthoimagery (NC Orthoimagery Program + post-Helene collection).

Services (ArcGIS ImageServer, public, exportImage):
  nc_2020_2023   Imagery/Orthoimagery_2020_2023_4band_analysis
                 6 in, RGB+NIR, RMSE 1.0 ft, leaf-off; the "analysis" service
                 uses compression that "minimizes the alteration of individual
                 pixel values" (unlike the display services), so it is fit for
                 radiometric change detection. Pre-event for Helene.
  nc_helene_2025 Imagery/Orthoimagery_Helene_2025
                 6 in, 13 WNC counties (Alexander, Ashe, Watauga, Avery,
                 Mitchell, Burke, Yancey, McDowell, Rutherford, Buncombe,
                 Henderson, Haywood, Jackson), spring 2025, leaf-off. NC
                 Collaboratory / UNC. Seamline editing focused on major roads;
                 elsewhere "may exhibit seamline displacement ... smears".

Native CRS EPSG:6543 (NAD83(2011) / NC State Plane, US survey foot). We ask
the server to resample onto our analysis grid (NAD83(2011) UTM 17N/18N) so
pre and post land on the identical pixel grid.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request

import numpy as np

from ..provenance import Provenance
from .base import Connector, SchemaError, SourceUnavailable, USER_AGENT, http_json

ROOT = "https://services.nconemap.gov/secure/rest/services/Imagery"
SERVICES = {
    "nc_2020_2023": {
        "path": "Orthoimagery_2020_2023_4band_analysis", "bands": [1, 2, 3], "nir_band": 4,
        "date_label": "NC Orthoimagery Program 2020-2023 cycle (leaf-off)",
        # acquisition date is encoded in each full-resolution tile name
        # (OF6i0_37_000_<tile>_<YYYYMMDD>_...); the catalog `date` field is a
        # year placeholder, so it is not used
        "range_if_undated": ["2020-01-01", "2023-12-31"], "season": "leaf-off",
        "license": "NC OneMap / NC CGIA / NC 911 Board; public",
        "radiometric": True,
    },
    "nc_helene_2025": {
        "path": "Orthoimagery_Helene_2025", "bands": [1, 2, 3], "nir_band": None,
        "date_label": "spring 2025 (leaf-off), NC Collaboratory post-Helene collection",
        # tile names carry no date and the service publishes only "spring
        # 2025"; Jan 1 - May 31 2025 is the widest range that statement allows
        "range_if_undated": ["2025-01-01", "2025-05-31"], "season": "leaf-off",
        "license": "NC Collaboratory at UNC Chapel Hill; public via NC OneMap",
        "radiometric": True,
    },
}
MAX_PX = 2000  # 4000 px requests return an HTML error page; 2500 works


def export_window(service: str, bounds_xy: tuple[float, float, float, float], epsg: int,
                  res_m: float) -> np.ndarray:
    """(bands, H, W) uint8 for `bounds_xy` in `epsg`, tiled under the server limit."""
    import rasterio
    from rasterio.io import MemoryFile

    spec = SERVICES[service]
    x0, y0, x1, y1 = bounds_xy
    W = int(round((x1 - x0) / res_m))
    H = int(round((y1 - y0) / res_m))
    nb = len(spec["bands"])
    out = np.zeros((nb, H, W), dtype="uint8")
    for r0 in range(0, H, MAX_PX):
        for c0 in range(0, W, MAX_PX):
            h, w = min(MAX_PX, H - r0), min(MAX_PX, W - c0)
            bx = (x0 + c0 * res_m, y1 - (r0 + h) * res_m, x0 + (c0 + w) * res_m, y1 - r0 * res_m)
            q = {
                "bbox": ",".join(f"{v:.3f}" for v in bx), "bboxSR": epsg, "imageSR": epsg,
                "size": f"{w},{h}", "format": "tiff", "pixelType": "U8",
                "bandIds": ",".join(str(b - 1) for b in spec["bands"]),
                "interpolation": "RSP_BilinearInterpolation", "f": "image",
            }
            url = f"{ROOT}/{spec['path']}/ImageServer/exportImage?" + urllib.parse.urlencode(q)
            data = None
            for i in range(4):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310
                        data = r.read()
                        ctype = r.headers.get("Content-Type", "")
                    if "tiff" not in ctype:
                        raise SchemaError(f"{service}: exportImage returned {ctype}: {data[:120]!r}")
                    break
                except Exception as ex:  # noqa: BLE001 - incl. transient HTML error pages
                    if i == 3:
                        raise SourceUnavailable(f"{service} exportImage failed: {ex}") from ex
                    time.sleep(2 ** (i + 1))
            with MemoryFile(data) as mf, mf.open() as ds:
                arr = ds.read()
                if arr.shape[1:] != (h, w):
                    arr = ds.read(out_shape=(ds.count, h, w))
            out[:, r0:r0 + h, c0:c0 + w] = arr[:nb]
    _ = rasterio
    return out


_TILE_DATE = re.compile(r"_(20\d{2})(\d{2})(\d{2})_")


def tile_dates(service: str, points_lonlat: list[tuple[float, float]]) -> tuple[str, str, str]:
    """(date_min, date_max, how) for the full-resolution tiles under the points.

    Dates come from tile names where the service encodes them; otherwise the
    documented collection range, labelled as a range, never a single made-up day.
    """
    spec = SERVICES[service]
    found: set[str] = set()
    for lon, lat in points_lonlat:
        try:
            d = http_json(f"{ROOT}/{spec['path']}/ImageServer/identify", params={
                "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
                "geometryType": "esriGeometryPoint", "returnGeometry": "false",
                "returnCatalogItems": "true", "f": "json"}, timeout=60)
        except Exception:  # noqa: BLE001
            continue
        for f in ((d.get("catalogItems") or {}).get("features") or []):
            a = f.get("attributes") or {}
            if a.get("minps") not in (0, 0.0):
                continue  # overview levels, not the source tile
            m = _TILE_DATE.search(a.get("name") or "")
            if m:
                found.add(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    if found:
        return min(found), max(found), "tile names"
    lo, hi = spec["range_if_undated"]
    return lo, hi, "service description (tiles undated)"


def covered(service: str, lon: float, lat: float) -> bool:
    """Does the service have imagery at this point? (catalog footprint query)"""
    spec = SERVICES[service]
    # the geometry must carry its spatialReference: a bare "x,y" with sr=4326 is
    # silently read in the service's own CRS (NC State Plane ftUS) -> NoData
    d = http_json(f"{ROOT}/{spec['path']}/ImageServer/identify", params={
        "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "returnGeometry": "false", "returnCatalogItems": "false", "f": "json"}, timeout=60)
    v = str(d.get("value", "NoData"))
    return v not in ("NoData", "", "None")


def provenance(service: str) -> Provenance:
    spec = SERVICES[service]
    return Provenance(
        source=f"NC OneMap {spec['path']}", source_url=f"{ROOT}/{spec['path']}/ImageServer",
        license=spec["license"], dataset_version=spec["date_label"],
        crs="EPSG:6543 native (served resampled)", horizontal_datum="NAD83(2011)", epoch=2010.0,
        units="RGB uint8, 6 in (0.1524 m) native GSD",
    )


class NCOrthos(Connector):
    name = "nc_orthos"
    license = "NC OneMap; public"
    homepage = "https://www.nconemap.gov/"
    stale_after_s = 10 * 365 * 86400

    def fetch(self, **kw):  # pragma: no cover - use export_window
        raise NotImplementedError

    def probe(self) -> float | None:
        for s in SERVICES:
            d = http_json(f"{ROOT}/{SERVICES[s]['path']}/ImageServer", params={"f": "json"}, timeout=30)
            if "bandCount" not in d:
                raise SchemaError(f"{s}: ImageServer metadata missing bandCount")
        return None


_ = os
