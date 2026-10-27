"""A basemap that works with no network: USGS The National Map topo tiles.

Source: `basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer`, a
US Government service (public domain; checked 2026-10-22), Web Mercator
256 px JPEG tiles addressed `/tile/{z}/{y}/{x}`. A pack carries the tiles that
cover its area: a wide context box at low zoom, the area plus a margin at high
zoom. Beyond the deepest zoom the map upsamples, and the assessment's own
imagery is the detail layer anyway.

Downloads are rate-limited (a few requests a second) and reuse any tile
already in BASEMAP_DIR, so building several packs does not hammer the
service.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import time
import urllib.request
from typing import Any, Iterator

from ..collect.base import USER_AGENT, SourceUnavailable

SOURCE = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer"
ATTRIBUTION = "USGS The National Map"
LICENSE = "US Government work (USGS); public domain"
CONTEXT_ZOOMS = (6, 12)          # inclusive
DETAIL_ZOOMS = (13, 16)
CONTEXT_MARGIN_KM = 25.0
DETAIL_MARGIN_KM = 3.0
REQUESTS_PER_S = 4.0
MAX_TILES = 4000                 # a pack that would need more is refused, not downloaded


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    lat = max(min(lat, 85.0511), -85.0511)
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def grow(bbox: tuple[float, float, float, float], km: float) -> tuple[float, float, float, float]:
    w, s, e, n = bbox
    dlat = km / 110.574
    dlon = km / (111.320 * math.cos(math.radians((s + n) / 2)))
    return w - dlon, s - dlat, e + dlon, n + dlat


def tiles_for(bbox: tuple[float, float, float, float]) -> Iterator[tuple[int, int, int]]:
    """Every (z, x, y) a pack for this area carries."""
    for (z0, z1), km in ((CONTEXT_ZOOMS, CONTEXT_MARGIN_KM), (DETAIL_ZOOMS, DETAIL_MARGIN_KM)):
        w, s, e, n = grow(bbox, km)
        for z in range(z0, z1 + 1):
            x0, y0 = lonlat_to_tile(w, n, z)
            x1, y1 = lonlat_to_tile(e, s, z)
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    yield z, x, y


def tile_path(root: str, z: int, x: int, y: int) -> str:
    return os.path.join(root, str(z), str(x), f"{y}.jpg")


def _get(url: str, retries: int = 3) -> bytes:
    last: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed https service
                body = r.read(2 * 1024 * 1024)
            if not body.startswith(b"\xff\xd8"):
                raise SourceUnavailable(f"basemap tile is not a JPEG ({body[:40]!r})")
            return body
        except Exception as ex:  # noqa: BLE001 - transient 5xx and resets
            last = ex
            time.sleep(1.5 * (i + 1))
    raise SourceUnavailable(f"USGS basemap tile failed after {retries} tries: {last}")


def extract(bbox: tuple[float, float, float, float], dest: str, reuse_from: str | None = None,
            fetch=_get) -> dict[str, Any]:
    """Write the area's tiles under `dest`; returns the basemap summary for the
    manifest. Tiles already in `reuse_from` (BASEMAP_DIR) are copied, not fetched."""
    wanted = list(tiles_for(bbox))
    if len(wanted) > MAX_TILES:
        raise ValueError(f"basemap extract would need {len(wanted)} tiles (cap {MAX_TILES})")
    fetched = reused = 0
    last = 0.0
    for z, x, y in wanted:
        out = tile_path(dest, z, x, y)
        if os.path.exists(out):
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        have = tile_path(reuse_from, z, x, y) if reuse_from else None
        if have and os.path.exists(have):
            shutil.copyfile(have, out)
            reused += 1
            continue
        wait = (1.0 / REQUESTS_PER_S - (time.monotonic() - last)) if fetch is _get else 0.0
        if wait > 0:
            time.sleep(wait)
        last = time.monotonic()
        body = fetch(f"{SOURCE}/tile/{z}/{y}/{x}")
        with open(out + ".tmp", "wb") as fh:
            fh.write(body)
        os.replace(out + ".tmp", out)
        fetched += 1
    w, s, e, n = grow(bbox, CONTEXT_MARGIN_KM)
    return {"source": SOURCE, "attribution": ATTRIBUTION, "license": LICENSE,
            "minzoom": CONTEXT_ZOOMS[0], "maxzoom": DETAIL_ZOOMS[1],
            "bounds": [round(v, 5) for v in (w, s, e, n)], "tiles": len(wanted),
            "fetched": fetched, "reused": reused}


INDEX = "index.json"


def read_index(root: str) -> dict[str, Any]:
    p = os.path.join(root, INDEX)
    if not os.path.exists(p):
        return {"areas": {}}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def merge_index(root: str, area: str, summary: dict[str, Any]) -> dict[str, Any]:
    idx = read_index(root)
    idx.setdefault("areas", {})[area] = summary
    os.makedirs(root, exist_ok=True)
    tmp = os.path.join(root, INDEX + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(idx, fh, indent=1)
    os.replace(tmp, os.path.join(root, INDEX))
    return idx


def coverage(root: str) -> dict[str, Any]:
    """Union of every imported area's basemap: zooms, bounds, tile count."""
    areas = read_index(root).get("areas") or {}
    if not areas:
        return {"available": False}
    bs = [a["bounds"] for a in areas.values()]
    return {"available": True, "attribution": ATTRIBUTION, "license": LICENSE,
            "minzoom": min(a["minzoom"] for a in areas.values()),
            "maxzoom": max(a["maxzoom"] for a in areas.values()),
            "bounds": [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)],
            "tiles": sum(a.get("tiles", 0) for a in areas.values()), "areas": sorted(areas)}


def style(tile_url: str, cov: dict[str, Any]) -> dict[str, Any]:
    """A MapLibre style with one raster source: no glyphs, sprites or fonts,
    so nothing in it reaches beyond this server."""
    src: dict[str, Any] = {"type": "raster", "tiles": [tile_url], "tileSize": 256,
                           "attribution": ATTRIBUTION}
    if cov.get("available"):
        src.update(minzoom=cov["minzoom"], maxzoom=cov["maxzoom"], bounds=cov["bounds"])
    return {"version": 8, "name": "Groma offline (USGS The National Map)",
            "sources": {"usgs-topo": src},
            "layers": [{"id": "background", "type": "background", "paint": {"background-color": "#e9e8e3"}},
                       {"id": "usgs-topo", "type": "raster", "source": "usgs-topo"}]}
