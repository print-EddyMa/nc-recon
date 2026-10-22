"""Civil Air Patrol aerial photos near a building, for Verify reviewers.

After Helene, Civil Air Patrol crews flew western North Carolina and FEMA
published every frame as a point (camera position, heading, time, a direct
link to the JPEG): `Image_Points_view`, 159,819 obliques and 704,948 nadir
frames nationally. Over Swannanoa the obliques were shot on 2024-09-28, two
days after the crest, months before the spring-2025 orthos Groma reads.

What this module does and does not do:
* It finds the frames that probably show a building: an oblique whose camera
  was 150 m to 2.5 km away and pointing at it (bearing inside the lens's
  horizontal field of view), or a nadir frame taken almost overhead. The
  building is not marked in the photo; for obliques the expected direction is
  returned as a fraction of the frame width, from the bearing and the lens.
* It is reviewer context, not an evidence channel: nothing here reaches the
  damage call. Reviewers see the photo beside the before and after chips.
* Only the CAP image host is ever fetched, and a thumbnail is fetched by key
  from the cached point list, never from a URL the client supplies.

Checked 2026-10-22: keyless ArcGIS FeatureServer (layers 1 oblique, 3 nadir),
no licence text (FEMA / Civil Air Patrol). The nadir cameras write a bogus
EXIF date (year 2000); the capture date is then read from the folder name
(`.../20241004T014015Z/...`).
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import tempfile
import threading
import time
import urllib.request
from datetime import date, datetime, timezone
from typing import Any

from .. import OPS_CACHE
from .base import USER_AGENT, Connector, DiskCache, SchemaError, http_json

BASE = "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/Image_Points_view/FeatureServer"
LAYERS = {"oblique": 1, "nadir": 3}
FIELDS = "longitude,latitude,altitude,heading,exif_photo_date,exif_focal_length,exif_camera_maker,url,mission"
HOST = "https://fema-cap-imagery.s3.amazonaws.com/"
# CAP project name per event (event id substrings, as in ncem_peak_stage)
PROJECTS = {"4827": "CAP - H-TS Helene 2024", "helene": "CAP - H-TS Helene 2024"}
PAD_DEG = {"oblique": 0.03, "nadir": 0.004}
OBLIQUE_M = (150.0, 2500.0)       # camera to building, along the ground
NADIR_M = 150.0                   # nadir frames: camera almost overhead
SENSOR_W_MM = 36.0                # full-frame bodies (the oblique cameras are Nikon DSLRs)
DEFAULT_HFOV_DEG = 30.0
BURST_S = 20.0                    # frames of one burst are near-duplicates
THUMB_PX = 1600
MAX_BYTES = 40 * 1024 * 1024
MAX_PIXELS = 80_000_000           # the DSLR frames are ~24 MP; refuse anything absurd before decoding
# each fetch holds up to MAX_BYTES in memory: at most this many at once
_FETCHES = threading.BoundedSemaphore(2)
_FOLDER_DATE = re.compile(r"/(\d{8})T\d{6}Z/")


def project_for(event_id: str) -> str | None:
    e = (event_id or "").lower()
    for k, v in PROJECTS.items():
        if k in e:
            return v
    return None


def key_of(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def capture_date(exif_ms: Any, url: str) -> date | None:
    """EXIF date when plausible, else the date in the folder name."""
    if isinstance(exif_ms, (int, float)) and not isinstance(exif_ms, bool):
        d = datetime.fromtimestamp(exif_ms / 1000.0, tz=timezone.utc).date()
        if d.year >= 2010:
            return d
    m = _FOLDER_DATE.search(url or "")
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            return None
    return None


def _query(layer: int, project: str, bbox: tuple[float, float, float, float]) -> list[dict]:
    w, s, e, n = bbox
    out: list[dict] = []
    offset = 0
    while True:
        d = http_json(f"{BASE}/{layer}/query", params={
            "where": f"project='{project}'", "outFields": FIELDS, "returnGeometry": "false", "f": "json",
            "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects", "resultOffset": offset, "resultRecordCount": 2000}, timeout=60)
        if not isinstance(d, dict) or not isinstance(d.get("features"), list):
            raise SchemaError("CAP image points: no features array")
        out += [f.get("attributes") or {} for f in d["features"]]
        if len(d["features"]) < 2000:
            return out
        offset += 2000


def points(event_id: str, bbox: tuple[float, float, float, float], incident_begin: date | None = None,
           cache_max_age_s: float = 30 * 86400) -> list[dict]:
    """CAP frames that could show something inside `bbox` (lon/lat), with a
    usable capture date on or after the incident. [] when the event has no
    registered CAP collection."""
    project = project_for(event_id)
    if not project:
        return []
    key = "{}_{:.4f}_{:.4f}_{:.4f}_{:.4f}".format(event_id, *bbox).replace("-", "m").replace(".", "p")
    cache = DiskCache("cap_photos")
    raw = cache.get(key, cache_max_age_s)
    if raw is None:
        w, s, e, n = bbox
        raw = {}
        for kind, layer in LAYERS.items():
            p = PAD_DEG[kind]
            raw[kind] = _query(layer, project, (w - p, s - p, e + p, n + p))
        cache.put(key, raw)
    out = []
    for kind, rows in raw.items():
        for a in rows:
            url = str(a.get("url") or "")
            lon, lat = a.get("longitude"), a.get("latitude")
            if not url.startswith(HOST) or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
                continue
            d = capture_date(a.get("exif_photo_date"), url)
            if d is None or (incident_begin is not None and d < incident_begin):
                continue
            out.append({"kind": kind, "lon": float(lon), "lat": float(lat), "url": url, "date": d.isoformat(),
                        "heading": a.get("heading"), "focal_mm": a.get("exif_focal_length"),
                        "maker": a.get("exif_camera_maker"), "mission": a.get("mission"),
                        "t": a.get("exif_photo_date"), "key": key_of(url)})
    return out


def _hfov(focal_mm: Any) -> float:
    if isinstance(focal_mm, (int, float)) and focal_mm > 5:
        return math.degrees(2 * math.atan(SENSOR_W_MM / (2 * focal_mm)))
    return DEFAULT_HFOV_DEG


def near(lon: float, lat: float, pts: list[dict], max_oblique: int = 3, max_nadir: int = 1) -> list[dict]:
    """The frames most likely to show the building at (lon, lat), nearest first."""
    kx = 111320.0 * math.cos(math.radians(lat))
    ky = 110540.0
    obl, nad = [], []
    for p in pts:
        dx, dy = (lon - p["lon"]) * kx, (lat - p["lat"]) * ky
        dist = math.hypot(dx, dy)
        if p["kind"] == "nadir":
            if dist <= NADIR_M:
                nad.append((dist, p, None))
            continue
        h = p.get("heading")
        if not isinstance(h, (int, float)) or h < 0 or not (OBLIQUE_M[0] <= dist <= OBLIQUE_M[1]):
            continue
        bearing = math.degrees(math.atan2(dx, dy)) % 360
        off = (bearing - h + 540) % 360 - 180
        half = _hfov(p.get("focal_mm")) / 2
        if abs(off) > 0.9 * half:
            continue
        x = 0.5 + math.tan(math.radians(off)) / (2 * math.tan(math.radians(half)))
        obl.append((dist, p, round(x, 3)))
    picked: list[dict] = []
    for pool, k in ((sorted(obl, key=lambda r: r[0]), max_oblique), (sorted(nad, key=lambda r: r[0]), max_nadir)):
        n = 0
        for dist, p, x in pool:
            if n >= k:
                break
            dup = any(q["mission"] == p["mission"] and q["kind"] == p["kind"]
                      and isinstance(q.get("_t"), (int, float)) and isinstance(p.get("t"), (int, float))
                      and abs(q["_t"] - p["t"]) <= BURST_S * 1000 for q in picked)
            if dup:
                continue
            picked.append({"key": p["key"], "kind": p["kind"], "date": p["date"], "dist_m": round(dist),
                           "x_frac": x, "url": p["url"], "mission": p["mission"], "_t": p.get("t")})
            n += 1
    for q in picked:
        q.pop("_t", None)
    return picked


def thumb_path(key: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{16}", key or ""):
        raise ValueError("bad photo key")
    d = os.path.join(OPS_CACHE, "cap_photos", "thumbs")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{key}.jpg")


def thumbnail(key: str, pts: list[dict]) -> str:
    """Path to a cached ~1600 px JPEG of the frame `key` (which must be one of
    `pts`). The originals are 15 to 20 MB; this is what reviewers load."""
    p = thumb_path(key)
    if os.path.exists(p):
        return p
    url = next((q["url"] for q in pts if q["key"] == key), None)
    if not url or not url.startswith(HOST):
        raise KeyError(key)
    from io import BytesIO

    from PIL import Image

    with _FETCHES:
        if os.path.exists(p):          # another request made it while this one waited
            return p
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - HOST is a fixed https origin
            final = r.geturl() if hasattr(r, "geturl") else url   # urllib follows redirects
            if not final.startswith(HOST):
                raise ValueError("photo request was redirected off the CAP image host")
            body = r.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("photo larger than the size cap")
        im = Image.open(BytesIO(body))
        if im.width * im.height > MAX_PIXELS:
            raise ValueError("photo has more pixels than the cap")
        im.draft("RGB", (THUMB_PX, THUMB_PX))
        im = im.convert("RGB")
        im.thumbnail((THUMB_PX, THUMB_PX))
        # a unique temp name: two requests for one key must not share a file
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                im.save(fh, "JPEG", quality=80, optimize=True)
            os.replace(tmp, p)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
    return p


class CAPPhotos(Connector):
    name = "cap_photos"
    license = "FEMA / Civil Air Patrol (ArcGIS Online item; no licence text)"
    homepage = BASE
    stale_after_s = 400 * 86400  # a per-event archive

    def probe(self):
        t0 = time.time()
        d = http_json(f"{BASE}/{LAYERS['oblique']}/query",
                      params={"where": f"project='{PROJECTS['helene']}'", "returnCountOnly": "true", "f": "json"},
                      timeout=30)
        if not isinstance(d, dict) or not d.get("count"):
            raise SchemaError(f"CAP image points count query returned nothing ({time.time() - t0:.1f}s)")
        return None
