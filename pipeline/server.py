"""Optional API for the Phase A output + on-demand assessment.

The web app reads GeoJSON + tiles + the event registries as static files and
needs no backend. This server adds:

  GET  /events                     -> web/public/data/events.json (ingested)
  GET  /catalog                    -> every Maxar Open Data event + coverage
  GET  /events/match?radius_km=200 -> live USGS/GDACS hazards paired with a
                                      Maxar event that covers them
  POST /assess  {event, lat, lon, name, subtitle}
                                   -> kicks off fetch -> infer -> make_tiles ->
                                      events registry in a background thread
  GET  /assess/{job_id}            -> {status, step, area, log_tail}
  GET  /areas, /areas/{id}, /areas/{id}/summary, /tiles/...

    ./.venv/bin/pip install "fastapi" "uvicorn[standard]"
    ./.venv/bin/python server.py            # http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)
OUT = os.path.join(ROOT, "data", "output")
RAW = os.path.join(ROOT, "data", "raw")
CACHE = os.path.join(ROOT, "data", "cache")
TILES = os.path.join(ROOT, "..", "web", "public", "tiles")
WEB_DATA = os.path.join(ROOT, "..", "web", "public", "data")
EVENTS_JSON = os.path.join(WEB_DATA, "events.json")

app = FastAPI(title="TerraTriage", version="1.1")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"


def _load(area: str) -> dict:
    path = os.path.join(OUT, f"{area}.geojson")
    if not os.path.exists(path):
        raise HTTPException(404, f"no output for area {area!r}")
    with open(path) as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# static registries
# --------------------------------------------------------------------------- #
@app.get("/events")
def events_registry():
    if not os.path.exists(EVENTS_JSON):
        raise HTTPException(404, "events.json not built — run `run.py events registry`")
    with open(EVENTS_JSON) as fh:
        return JSONResponse(json.load(fh))


@app.get("/catalog")
def catalog():
    from terratriage import events as ev

    return JSONResponse(ev.catalog(CACHE))


def _live_hazards() -> dict:
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
    return {"type": "FeatureCollection", "features": feats}


@app.get("/events/match")
def events_match(radius_km: float = 200.0):
    from terratriage import events as ev

    cat = ev.catalog(CACHE)
    ingested = set()
    if os.path.exists(EVENTS_JSON):
        with open(EVENTS_JSON) as fh:
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
    event: str
    lat: float
    lon: float
    name: str | None = None
    subtitle: str | None = None
    event_date: str | None = None


JOBS: dict[str, dict] = {}


def _run_step(job: dict, label: str, args: list[str]) -> None:
    job["step"] = label
    p = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", *args[:1]), *args[1:]],
        capture_output=True, text=True, cwd=ROOT,
    )
    job["log"] = (job.get("log", "") + f"\n$ {' '.join(args)}\n" + p.stdout + p.stderr)[-8000:]
    if p.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {p.returncode})")


def _assess_worker(job_id: str, req: AssessReq, area: str, event_date: str | None) -> None:
    job = JOBS[job_id]
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
        _run_step(job, "fetch imagery", fetch)
        _run_step(job, "run damage model", ["run.py", "infer", "--area", area])
        _run_step(job, "cut map tiles", ["make_tiles.py", "--area", area])
        # the contract GeoJSON lands in pipeline/data/output; the web app reads
        # from web/public/data — copy it so the new event is loadable
        import shutil

        src = os.path.join(OUT, f"{area}.geojson")
        if os.path.exists(src):
            os.makedirs(WEB_DATA, exist_ok=True)
            shutil.copy2(src, os.path.join(WEB_DATA, f"{area}.geojson"))
        _run_step(job, "update registry", ["run.py", "events", "registry"])
        job["status"] = "done"
        job["step"] = "done"
        job["area"] = area
    except Exception as ex:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(ex)


@app.post("/assess")
def assess(req: AssessReq):
    from terratriage import events as ev

    cat = {c["id"]: c for c in ev.catalog(CACHE)}
    if req.event not in cat:
        raise HTTPException(400, f"{req.event!r} is not in the Maxar Open Data catalogue")
    event_date = req.event_date or cat[req.event].get("suggested_event_date")
    area = re.sub(r"[^a-z0-9_]+", "_", (req.name or req.event).lower()).strip("_")[:40] or "aoi"
    if os.path.exists(os.path.join(OUT, f"{area}.geojson")):
        return {"job_id": None, "status": "done", "area": area, "note": "already assessed"}
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "queued", "step": "queued", "started": time.time(), "area": area}
    threading.Thread(
        target=_assess_worker, args=(job_id, req, area, event_date), daemon=True
    ).start()
    return {"job_id": job_id, "status": "queued", "area": area}


@app.get("/assess/{job_id}")
def assess_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return {
        "status": job["status"],
        "step": job.get("step"),
        "area": job.get("area"),
        "error": job.get("error"),
        "log_tail": (job.get("log", "") or "")[-1200:],
    }


# --------------------------------------------------------------------------- #
@app.get("/areas")
def areas():
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


@app.get("/tiles/{area}/{kind}/{z}/{x}/{y}.jpg")
def tile(area: str, kind: str, z: int, x: int, y: int):
    if kind not in ("pre", "post"):
        raise HTTPException(400, "kind must be pre or post")
    path = os.path.join(TILES, area, kind, str(z), str(x), f"{y}.jpg")
    if not os.path.exists(path):
        raise HTTPException(404, "tile not found")
    return FileResponse(path, media_type="image/jpeg")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
