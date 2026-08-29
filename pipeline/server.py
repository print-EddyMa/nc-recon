"""Optional lightweight API for the Phase A output.

The web app reads GeoJSON + tiles as static files and needs no backend, but this
serves the same paths for setups that want an API (and adds permissive CORS for
cross-origin dev).

    ./.venv/bin/pip install "fastapi" "uvicorn[standard]"
    ./.venv/bin/python server.py            # http://127.0.0.1:8000
    #   GET /areas
    #   GET /areas/{id}            -> the contract GeoJSON
    #   GET /areas/{id}/summary    -> counts + headline stats
    #   GET /tiles/{id}/{kind}/{z}/{x}/{y}.jpg
"""
from __future__ import annotations

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "output")
TILES = os.path.join(ROOT, "..", "web", "public", "tiles")

app = FastAPI(title="TerraTriage", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"]
)


def _load(area: str) -> dict:
    path = os.path.join(OUT, f"{area}.geojson")
    if not os.path.exists(path):
        raise HTTPException(404, f"no output for area {area!r}")
    with open(path) as fh:
        return json.load(fh)


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
