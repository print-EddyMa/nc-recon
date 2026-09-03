"""Assessment service for NC Recon.

The web app reads GeoJSON + tiles + the event registry as static files and needs
no backend. This service adds on-demand assessment of a North Carolina area:

  GET  /events                     -> web/public/data/events.json (assessed areas)
  GET  /catalog                    -> every Maxar Open Data event + coverage
  GET  /events/match?radius_km=200 -> live USGS/GDACS hazards paired with a
                                      Maxar event that covers them
  POST /assess  {event, lat, lon, name, subtitle}
                                   -> fetch -> infer -> make_tiles -> registry,
                                      in a background thread. NC AOIs only.
  GET  /assess/{job_id}            -> {status, step, area, log_tail}
  DELETE /areas/{area}             -> remove an assessed area (token-gated)
  GET  /areas, /areas/{id}, /areas/{id}/summary, /tiles/...

Configuration (all optional, via environment):

  TERRATRIAGE_TOKEN   if set, POST /assess and DELETE require
                      `Authorization: Bearer <token>`
  CORS_ORIGINS        comma-separated allowed origins
                      (default: http://localhost:5173,http://127.0.0.1:5173)
  ALLOWED_BBOX        "w,s,e,n" AOI gate (default: North Carolina)
  MAX_ACTIVE_JOBS     concurrent assessments (default: 2)
  MAX_ASSESS_PER_HOUR per-client rate limit (default: 6)
  MAX_DATA_GB         refuse new jobs when data/ exceeds this (default: 20)
  HOST                bind address (default: 127.0.0.1; containers set 0.0.0.0)
  PORT                listen port (default: 8000)

    ./.venv/bin/pip install "fastapi" "uvicorn[standard]"
    ./.venv/bin/python server.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from collections import deque

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
OUT = os.path.join(ROOT, "data", "output")
RAW = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(ROOT, "data", "cache")
DATA = os.path.join(ROOT, "data")
# these mirror scripts/run.py + scripts/make_tiles.py so a container deploy
# (where ../web is not on disk) can point all three at a writable volume.
TILES = os.environ.get("TERRATRIAGE_TILES_DIR") or os.path.join(
    ROOT, "..", "web", "public", "tiles"
)
WEB_DATA = os.environ.get("TERRATRIAGE_WEB_DATA_DIR") or os.path.join(
    ROOT, "..", "web", "public", "data"
)
os.makedirs(WEB_DATA, exist_ok=True)
EVENTS_JSON = os.path.join(WEB_DATA, "events.json")

# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #
TOKEN = os.environ.get("TERRATRIAGE_TOKEN", "").strip()
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]
_bbox_env = os.environ.get("ALLOWED_BBOX", "-84.55,33.75,-75.4,36.7")
try:
    ALLOWED_BBOX = tuple(float(v) for v in _bbox_env.split(","))
    assert len(ALLOWED_BBOX) == 4
except Exception:  # noqa: BLE001
    ALLOWED_BBOX = (-84.55, 33.75, -75.4, 36.7)
MAX_ACTIVE_JOBS = int(os.environ.get("MAX_ACTIVE_JOBS", "2"))
MAX_ASSESS_PER_HOUR = int(os.environ.get("MAX_ASSESS_PER_HOUR", "6"))
MAX_DATA_GB = float(os.environ.get("MAX_DATA_GB", "20"))
MAX_TOTAL_JOBS = 500

_AREA_RE = re.compile(r"[a-z0-9_]{1,40}")
_EVENT_RE = re.compile(r"[A-Za-z0-9._-]{1,80}")
_NAME_STRIP_RE = re.compile(r"[^\w \-.,]", re.UNICODE)

app = FastAPI(title="NC Recon", version="1.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["http://localhost:5173"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["authorization", "content-type"],
)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"


def _safe_area(area: str) -> str:
    """Reject anything that isn't a bare pipeline area slug (blocks traversal)."""
    if not _AREA_RE.fullmatch(area or ""):
        raise HTTPException(400, "bad area id")
    return area


def _require_token(authorization: str | None) -> None:
    if not TOKEN:
        return
    expected = f"Bearer {TOKEN}"
    if not authorization or authorization != expected:
        raise HTTPException(401, "missing or invalid bearer token")


def _clean_name(s: str | None, limit: int = 80) -> str | None:
    if not s:
        return None
    s = _NAME_STRIP_RE.sub("", s).strip()[:limit]
    return s or None


def _dir_bytes(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _load(area: str) -> dict:
    _safe_area(area)
    path = os.path.join(OUT, f"{area}.geojson")
    if not os.path.realpath(path).startswith(os.path.realpath(OUT) + os.sep):
        raise HTTPException(400, "bad area id")
    if not os.path.exists(path):
        raise HTTPException(404, f"no output for area {area!r}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _catalog_or_503():
    """The Maxar catalogue, or a clean 503 if it can't be built (GitHub down /
    rate-limited on a cold cache)."""
    from terratriage import events as ev

    try:
        return ev.catalog(CACHE)
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(503, f"Maxar catalogue unavailable: {ex}") from ex


# --------------------------------------------------------------------------- #
# static registries
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    """Fast liveness probe — the web app's `serverUp()` hits this, not /catalog
    (which can be slow on a cold catalogue cache)."""
    return {"ok": True, "version": app.version}


# --------------------------------------------------------------------------- #
# cached pass-through for the keyless NC feeds whose upstreams either omit CORS
# headers on error, rate-limit aggressively, or want a real User-Agent. The
# browser keeps its committed-snapshot fallback either way; this just keeps the
# happy path clean and polite to the source.
# --------------------------------------------------------------------------- #
_FEEDS: dict[str, tuple[str, int]] = {
    "nwps": (
        "https://api.water.noaa.gov/nwps/v1/gauges"
        "?bbox.xmin=-84.55&bbox.ymin=33.75&bbox.xmax=-75.4&bbox.ymax=36.7&srid=EPSG_4326",
        300,
    ),
    "nws": ("https://api.weather.gov/alerts/active?area=NC", 180),
    "nwis": (
        "https://waterservices.usgs.gov/nwis/iv/?format=json&stateCd=nc"
        "&parameterCd=00060,00065&siteType=ST&siteStatus=active",
        300,
    ),
}
_FEED_CACHE: dict[str, tuple[float, bytes, str]] = {}
_FEED_UA = "NCRecon/1.0 (Congressional App Challenge; +https://github.com/)"


@app.get("/feed/{name}")
def feed(name: str):
    spec = _FEEDS.get(name)
    if not spec:
        raise HTTPException(404, "unknown feed")
    url, ttl = spec
    hit = _FEED_CACHE.get(name)
    if hit and time.time() - hit[0] < ttl:
        return Response(content=hit[1], media_type=hit[2])
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": _FEED_UA, "Accept": "application/geo+json, application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (fixed whitelist)
            body = r.read()
            ctype = r.headers.get("Content-Type", "application/json")
        _FEED_CACHE[name] = (time.time(), body, ctype)
        return Response(content=body, media_type=ctype)
    except Exception as ex:  # noqa: BLE001
        if hit:  # serve the last good copy rather than fail
            return Response(content=hit[1], media_type=hit[2], headers={"X-Stale": "1"})
        # nothing cached yet: hand back an empty-but-valid body (200) so the
        # browser stays quiet and falls through to its committed snapshot
        print(f"[server] feed {name} upstream failed, no cache: {ex}")
        return Response(content=b"{}", media_type="application/json", headers={"X-Stale": "miss"})


@app.get("/events")
def events_registry():
    if not os.path.exists(EVENTS_JSON):
        return JSONResponse([])
    with open(EVENTS_JSON, encoding="utf-8") as fh:
        return JSONResponse(json.load(fh))


@app.get("/catalog")
def catalog():
    return JSONResponse(_catalog_or_503())


@app.get("/events/{event}/coverage")
def event_coverage(event: str):
    if not _EVENT_RE.fullmatch(event or ""):
        raise HTTPException(400, "bad event id")
    from terratriage import events as ev

    try:
        return JSONResponse(ev.coverage(event, CACHE))
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(404, f"no coverage for {event!r}: {ex}") from ex


_HAZARD_CACHE: dict[str, object] = {"at": 0.0, "data": None}


def _live_hazards() -> dict:
    # cache for 60 s so /events/match doesn't do two 20 s blocking fetches per call
    if _HAZARD_CACHE["data"] is not None and time.time() - float(_HAZARD_CACHE["at"]) < 60:
        return _HAZARD_CACHE["data"]  # type: ignore[return-value]
    feats = []
    try:
        with urllib.request.urlopen(USGS_URL, timeout=20) as r:
            for f in json.load(r).get("features", []):
                if (f.get("geometry") or {}).get("type") == "Point":
                    p = f.get("properties", {})
                    feats.append({"type": "Feature", "geometry": f["geometry"], "properties": {
                        "hazard_type": "earthquake", "title": p.get("place"),
                        "mag": p.get("mag"), "source": "usgs",
                    }})
    except Exception as ex:  # noqa: BLE001
        print(f"[server] USGS failed: {ex}")
    try:
        with urllib.request.urlopen(GDACS_URL, timeout=20) as r:
            for f in json.load(r).get("features", []):
                if (f.get("geometry") or {}).get("type") == "Point":
                    p = f.get("properties", {})
                    feats.append({"type": "Feature", "geometry": f["geometry"], "properties": {
                        "hazard_type": (p.get("eventtype") or "").lower() or None,
                        "title": p.get("name") or p.get("htmldescription"),
                        "alertlevel": p.get("alertlevel"), "source": "gdacs",
                    }})
    except Exception as ex:  # noqa: BLE001
        print(f"[server] GDACS failed: {ex}")
    out = {"type": "FeatureCollection", "features": feats}
    _HAZARD_CACHE["data"] = out
    _HAZARD_CACHE["at"] = time.time()
    return out


@app.get("/events/match")
def events_match(radius_km: float = 200.0):
    from terratriage import events as ev

    radius_km = max(1.0, min(2000.0, radius_km))
    cat = _catalog_or_503()
    ingested = set()
    if os.path.exists(EVENTS_JSON):
        with open(EVENTS_JSON, encoding="utf-8") as fh:
            ingested = {e["id"] for e in json.load(fh)}
    matches = ev.match_hazards(cat, _live_hazards(), radius_km=radius_km)
    by_id = {c["id"]: c for c in cat}
    for m in matches:
        c = by_id.get(m["event"], {})
        m["ingested"] = m["event"] in ingested
        m["center"] = c.get("center")
        m["hazard_kind"] = c.get("hazard")
        m["capture_dates"] = c.get("capture_dates")
        m["name"] = c.get("name")
    return matches


# --------------------------------------------------------------------------- #
# on-demand assessment
# --------------------------------------------------------------------------- #
class AssessReq(BaseModel):
    event: str = Field(max_length=80)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    name: str | None = Field(default=None, max_length=200)
    subtitle: str | None = Field(default=None, max_length=200)
    event_date: str | None = Field(default=None, max_length=10)

    @field_validator("event")
    @classmethod
    def _event_shape(cls, v: str) -> str:
        if not _EVENT_RE.fullmatch(v or ""):
            raise ValueError("bad event id")
        return v

    @field_validator("event_date")
    @classmethod
    def _date_shape(cls, v: str | None) -> str | None:
        if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("event_date must be YYYY-MM-DD")
        return v


JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_RATE: dict[str, deque] = {}


def _rate_check(client: str) -> bool:
    """True if the client is under the hourly quota. Does NOT consume a slot —
    call _rate_consume once the job is actually created."""
    now = time.time()
    dq = _RATE.setdefault(client, deque())
    while dq and now - dq[0] > 3600:
        dq.popleft()
    return len(dq) < MAX_ASSESS_PER_HOUR


def _rate_consume(client: str) -> None:
    _RATE.setdefault(client, deque()).append(time.time())


# per-step ceilings (a hung fetch surfaces as a real error, and frees its
# MAX_ACTIVE_JOBS slot, well before the client's ~12-min poll gives up). The
# job-level JOB_DEADLINE_SEC below is what actually bounds the whole run.
STEP_TIMEOUT: dict[str, int] = {
    "fetch imagery": 360,
    "run damage model": 420,
    "cut map tiles": 240,
    "update registry": 120,
}
_STUCK_JOB_SEC = 15 * 60


def _reap_jobs(ttl_sec: int = 1800) -> None:
    with _JOBS_LOCK:
        now = time.time()
        # a job still "running"/"queued" well past any plausible runtime is wedged
        # (e.g. the worker thread died) — fail it so the slot is reusable
        for v in JOBS.values():
            if v["status"] in ("queued", "running") and now - v.get("started", now) > _STUCK_JOB_SEC:
                v["status"] = "error"
                v["error"] = "assessment exceeded the time budget"
                v["finished"] = now
        cutoff = now - ttl_sec
        for jid in [
            k for k, v in JOBS.items()
            if v["status"] in ("done", "error") and v.get("finished", v.get("started", 0)) < cutoff
        ]:
            JOBS.pop(jid, None)
        if len(JOBS) > MAX_TOTAL_JOBS:
            for jid in sorted(JOBS, key=lambda k: JOBS[k].get("started", 0))[: len(JOBS) - MAX_TOTAL_JOBS]:
                JOBS.pop(jid, None)


# hard ceiling on a whole assessment, independent of the per-step caps — keeps a
# run from creeping past the browser's ~12-min poll window if several steps each
# run long. Comfortably above the ~90s a real NC AOI takes.
JOB_DEADLINE_SEC = 600


def _run_step(job: dict, label: str, args: list[str], deadline: float | None = None) -> None:
    job["step"] = label
    budget = STEP_TIMEOUT.get(label, 900)
    if deadline is not None:
        budget = max(1, min(budget, int(deadline - time.time())))
    p = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", *args[:1]), *args[1:]],
        capture_output=True, text=True, cwd=ROOT, timeout=budget,
    )
    job["log"] = (job.get("log", "") + f"\n$ {' '.join(args)}\n" + p.stdout + p.stderr)[-8000:]
    if p.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {p.returncode})")


def _assess_worker(job_id: str, req: AssessReq, area: str, event_date: str | None) -> None:
    job = JOBS[job_id]
    deadline = time.time() + JOB_DEADLINE_SEC
    try:
        job["status"] = "running"
        common = ["--event", req.event, "--area", area]
        fetch = ["run.py", "fetch", *common, "--lat", str(req.lat), "--lon", str(req.lon)]
        if req.name:
            fetch += ["--name", req.name]
        if req.subtitle:
            fetch += ["--subtitle", req.subtitle]
        if event_date:
            fetch += ["--event-date", event_date]
        _run_step(job, "fetch imagery", fetch, deadline)
        # the service only assesses NC AOIs, so always use NC footprints + priors
        _run_step(
            job, "run damage model",
            ["run.py", "infer", "--area", area, "--source", "auto", "--nc-context"],
            deadline,
        )
        _run_step(job, "cut map tiles", ["make_tiles.py", "--area", area], deadline)
        src = os.path.join(OUT, f"{area}.geojson")
        if os.path.exists(src):
            os.makedirs(WEB_DATA, exist_ok=True)
            shutil.copy2(src, os.path.join(WEB_DATA, f"{area}.geojson"))
        _run_step(job, "update registry", ["run.py", "events", "registry"], deadline)
        job["status"] = "done"
        job["step"] = "done"
        job["area"] = area
    except Exception as ex:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(ex)
    finally:
        job["finished"] = time.time()


@app.post("/assess")
def assess(req: AssessReq, request: Request, authorization: str | None = Header(default=None)):
    _require_token(authorization)
    _reap_jobs()

    w, s, e, n = ALLOWED_BBOX
    if not (w <= req.lon <= e and s <= req.lat <= n):
        raise HTTPException(400, "AOI is outside the allowed area (North Carolina)")

    client = request.client.host if request.client else "unknown"
    if not _rate_check(client):
        raise HTTPException(429, f"rate limit: max {MAX_ASSESS_PER_HOUR} assessments per hour")
    if _dir_bytes(DATA) > MAX_DATA_GB * 1e9:
        raise HTTPException(507, "assessment storage is full on this service")

    cat = {c["id"]: c for c in _catalog_or_503()}
    if req.event not in cat:
        raise HTTPException(400, f"{req.event!r} is not in the Maxar Open Data catalogue")
    event_date = req.event_date or cat[req.event].get("suggested_event_date")

    req.name = _clean_name(req.name)
    req.subtitle = _clean_name(req.subtitle)
    area = re.sub(r"[^a-z0-9_]+", "_", (req.name or req.event).lower()).strip("_")[:40] or "aoi"

    if os.path.exists(os.path.join(OUT, f"{area}.geojson")):
        return {"job_id": None, "status": "done", "area": area, "note": "already assessed"}

    # capacity + dedup + creation are one atomic section so concurrent requests
    # cannot both slip past the MAX_ACTIVE_JOBS gate
    with _JOBS_LOCK:
        for jid, j in JOBS.items():
            if j.get("area") == area and j["status"] in ("queued", "running"):
                return {"job_id": jid, "status": j["status"], "area": area, "note": "already running"}
        active = sum(1 for j in JOBS.values() if j["status"] in ("queued", "running"))
        if active >= MAX_ACTIVE_JOBS:
            raise HTTPException(
                429, f"{MAX_ACTIVE_JOBS} assessments already running — try again shortly"
            )
        job_id = uuid.uuid4().hex[:12]
        JOBS[job_id] = {"status": "queued", "step": "queued", "started": time.time(), "area": area}
        _rate_consume(client)
    threading.Thread(
        target=_assess_worker, args=(job_id, req, area, event_date), daemon=True
    ).start()
    return {"job_id": job_id, "status": "queued", "area": area}


@app.get("/assess/{job_id}")
def assess_status(job_id: str, authorization: str | None = Header(default=None)):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    # the raw subprocess log can carry filesystem paths / stack traces — only
    # expose it when auth is not configured, or a valid token is presented
    show_log = not TOKEN or authorization == f"Bearer {TOKEN}"
    return {
        "status": job["status"],
        "step": job.get("step"),
        "area": job.get("area"),
        "error": job.get("error"),
        "log_tail": (job.get("log", "") or "")[-1200:] if show_log else None,
    }


# --------------------------------------------------------------------------- #
@app.get("/areas")
def areas():
    if not os.path.isdir(OUT):
        return []
    return [
        f[:-8]
        for f in sorted(os.listdir(OUT))
        if f.endswith(".geojson") and not f.endswith("_seg.geojson")
    ]


@app.get("/areas/{area}")
def area(area: str):
    return JSONResponse(_load(area))


@app.get("/areas/{area}/summary")
def summary(area: str):
    fc = _load(area)
    p = fc["properties"]
    c = {int(k): v for k, v in p["counts"].items()}
    total = p["n_buildings"] or 1
    severe = c.get(2, 0) + c.get(3, 0)
    return {
        "area": area,
        "model": p["model"],
        "n_buildings": p["n_buildings"],
        "counts": c,
        "severe": severe,
        "severe_pct": round(100 * severe / total, 1),
        "review": p.get("review"),
        "pre_image": p["pre_image"],
        "post_image": p["post_image"],
    }


@app.delete("/areas/{area}")
def delete_area(area: str, authorization: str | None = Header(default=None)):
    _require_token(authorization)
    _safe_area(area)
    removed = []
    for path in (
        os.path.join(OUT, f"{area}.geojson"),
        os.path.join(OUT, f"{area}_seg.geojson"),
        os.path.join(WEB_DATA, f"{area}.geojson"),
        os.path.join(RAW, area),
        os.path.join(TILES, area),
    ):
        rp = os.path.realpath(path)
        # only ever delete inside our own data / tiles roots
        if not (
            rp.startswith(os.path.realpath(OUT) + os.sep)
            or rp.startswith(os.path.realpath(RAW) + os.sep)
            or rp.startswith(os.path.realpath(TILES) + os.sep)
            or rp.startswith(os.path.realpath(WEB_DATA) + os.sep)
        ):
            continue
        if os.path.isdir(rp):
            shutil.rmtree(rp, ignore_errors=True)
            removed.append(path)
        elif os.path.exists(rp):
            os.remove(rp)
            removed.append(path)
    try:
        subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "run.py"), "events", "registry"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
    except Exception as ex:  # noqa: BLE001
        print(f"[server] registry rewrite after delete failed: {ex}")
    return {"area": area, "removed": removed}


# 1x1 transparent PNG — handed back for missing basemap tiles at an AOI's edge
# so MapLibre's viewport grid doesn't spew 404s to the console
_BLANK_TILE = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c626001000000050001a5f645400000000049454e44ae426082"
)


@app.get("/tiles/{area}/{kind}/{z}/{x}/{y}.jpg")
def tile(area: str, kind: str, z: int, x: int, y: int, empty: int = 0):
    _safe_area(area)
    if kind not in ("pre", "post"):
        raise HTTPException(400, "kind must be pre or post")
    path = os.path.join(TILES, area, kind, str(z), str(x), f"{y}.jpg")
    if not os.path.realpath(path).startswith(os.path.realpath(TILES) + os.sep):
        raise HTTPException(400, "bad path")
    if not os.path.exists(path):
        # `?empty=1` (the slippy-map basemap): a blank tile keeps the console
        # clean. Without it (the review-queue crop <img>): a real 404 so the
        # crop can retry one zoom out.
        if empty:
            return Response(
                content=_BLANK_TILE,
                media_type="image/png",
                headers={
                    "Cross-Origin-Resource-Policy": "cross-origin",
                    "Cache-Control": "public, max-age=86400",
                },
            )
        raise HTTPException(404, "tile not found")
    # CORP so a cross-origin <img> (the review queue) can embed the tile without
    # tripping the browser's Opaque-Response-Blocking heuristic
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={
            "Cross-Origin-Resource-Policy": "cross-origin",
            "Cache-Control": "public, max-age=86400",
        },
    )


if __name__ == "__main__":
    import uvicorn

    # 127.0.0.1 for local dev; containers/hosts set HOST=0.0.0.0
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )
