"""Ops-mode HTTP API (mounted by server.py under /ops).

Public (no building-level PII; the ops GeoJSON never carries addresses):
  GET  /ops/areas                       summaries of every ops assessment
  GET  /ops/areas/{area}                ops GeoJSON (schema ops-1.0)
  GET  /ops/areas/{area}/chip/{ncr_id}/{pre|post}.png
                                        pre/post image chip with the footprint
  GET  /ops/health                      collection board (refreshed <= 10 min)
  GET  /ops/report                      latest ACCURACY_REPORT.json
  GET  /ops/meta                        disclaimer, class vocab, colours

Responder (bearer token; with no token configured, loopback clients only):
  GET  /ops/areas/{area}/responder      ncr_id -> address sidecar
  POST /ops/labels                      append a truth label (TUNE/TEST aware)
  GET  /ops/areas/{area}/export.zip     GeoJSON/CSV/KML/GPKG/FileGDB/Survey123 bundle
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
import time
import zipfile
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from . import DATA_DIR, DISCLAIMER, PIPELINE_ROOT
from .analyze.classes import FEMA, FEMA_LABEL

OPS_OUT = os.path.join(DATA_DIR, "output", "ops")
LABELS = os.path.join(DATA_DIR, "labels")
RAW = os.path.join(DATA_DIR, "raw")
REPORT = os.path.join(PIPELINE_ROOT, "..", "reports", "ACCURACY_REPORT.json")
_AREA = re.compile(r"[a-z0-9_]{1,40}")
_UUID = re.compile(r"[0-9a-f-]{36}")
PROTOCOL = "ncr-label-v1"
LABEL_CHOICES = (*FEMA, "cannot_tell")

router = APIRouter(prefix="/ops")
_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _area(area: str) -> str:
    if not _AREA.fullmatch(area):
        raise HTTPException(400, "bad area id")
    return area


def _responder(request: Request, authorization: str | None) -> None:
    token = os.environ.get("TERRATRIAGE_TOKEN", "").strip()
    if token:
        if authorization != f"Bearer {token}":
            raise HTTPException(401, "responder token required")
        return
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(403, "responder data needs TERRATRIAGE_TOKEN when served beyond localhost")


def _load(area: str) -> dict[str, Any]:
    p = os.path.join(OPS_OUT, f"{_area(area)}.geojson")
    if not os.path.exists(p):
        raise HTTPException(404, f"no ops assessment for {area}")
    mt = os.path.getmtime(p)
    hit = _cache.get(p)
    if hit and hit[0] == mt:
        return hit[1]
    with open(p, encoding="utf-8") as fh:
        fc = json.load(fh)
    _cache[p] = (mt, fc)
    return fc


@router.get("/meta")
def meta():
    from .disseminate.exports import COLORS

    return {"disclaimer": DISCLAIMER, "classes": list(FEMA),
            "labels": {c: FEMA_LABEL[c] for c in FEMA}, "colors": {k or "not_assessed": v for k, v in COLORS.items()},
            "label_choices": list(LABEL_CHOICES), "protocol": PROTOCOL}


@router.get("/areas")
def areas():
    out = []
    if os.path.isdir(OPS_OUT):
        for f in sorted(os.listdir(OPS_OUT)):
            if not f.endswith(".geojson"):
                continue
            fc = _load(f[:-8])
            p = fc["properties"]
            out.append({k: p.get(k) for k in (
                "run_id", "generated_utc", "event", "aoi", "counts", "expected_counts",
                "expected_counts_80pct", "n_structures", "n_needs_review", "not_assessed",
                "calibration", "warnings", "pair_context")} | {"id": f[:-8]})
    return out


@router.get("/areas/{area}")
def area(area: str):
    return JSONResponse(_load(area), headers={"Cache-Control": "no-cache"})


@router.get("/areas/{area}/chip/{ncr_id}/{kind}.png")
def chip(area: str, ncr_id: str, kind: str, size: int = 256, pad_m: float = 12.0):
    import numpy as np
    import rasterio
    from PIL import Image, ImageDraw
    from rasterio.windows import from_bounds
    from shapely.geometry import shape
    from shapely.ops import transform as st

    from .geodesy import transformer
    from .process import imagery

    if kind not in ("pre", "post") or not _UUID.fullmatch(ncr_id):
        raise HTTPException(400, "bad chip request")
    fc = _load(area)
    feat = next((f for f in fc["features"] if f["properties"]["ncr_id"] == ncr_id), None)
    if feat is None:
        raise HTTPException(404, "no such structure")
    pre, post = imagery.pair_for_area(RAW, area, (fc["properties"].get("event") or {}).get("maxar") or "HurricaneHelene-Oct24")
    path = pre.path if kind == "pre" else post.path
    size = max(64, min(size, 512))
    al = ((feat["properties"].get("measurements") or {}).get("alignment") or {}).get(kind) or {}
    with rasterio.open(path) as ds:
        g = st(transformer("storage", ds.crs.to_wkt()).transform, shape(feat["geometry"]))
        if al:
            from shapely.affinity import translate

            g = translate(g, al.get("dx_m", 0.0), al.get("dy_m", 0.0))
        minx, miny, maxx, maxy = g.bounds
        half = max(maxx - minx, maxy - miny) / 2 + pad_m
        cx, cy = g.centroid.x, g.centroid.y
        win = from_bounds(cx - half, cy - half, cx + half, cy + half, ds.transform)
        arr = ds.read(indexes=[1, 2, 3], window=win, boundless=True, fill_value=0,
                      out_shape=(3, size, size))
    img = Image.fromarray(np.transpose(arr, (1, 2, 0)).astype("uint8"))
    draw = ImageDraw.Draw(img)
    geoms = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
    for poly in geoms:
        pts = [((x - (cx - half)) / (2 * half) * size, ((cy + half) - y) / (2 * half) * size)
               for x, y in poly.exterior.coords]
        if len(pts) > 2:
            draw.line(pts + [pts[0]], fill=(74, 128, 246), width=2)
    if g.geom_type == "Point":
        r = size * 0.03
        draw.ellipse([size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r], outline=(74, 128, 246), width=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600",
                             "Cross-Origin-Resource-Policy": "cross-origin"})


@router.get("/areas/{area}/impact")
def impact(area: str):
    p = os.path.join(OPS_OUT, f"{_area(area)}.impact.json")
    if not os.path.exists(p):
        raise HTTPException(404, "no impact run for this area")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


@router.get("/areas/{area}/public.geojson")
def public_tracts(area: str):
    from .disseminate.aggregate import aggregate

    _load(area)
    with open(aggregate(area), encoding="utf-8") as fh:
        return JSONResponse(json.load(fh))


@router.get("/areas/{area}/brief.html")
def brief_html(area: str):
    from fastapi.responses import HTMLResponse

    from .disseminate.brief import brief

    _load(area)
    with open(brief(area), encoding="utf-8") as fh:
        return HTMLResponse(fh.read())


@router.get("/areas/{area}/responder")
def responder(area: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    p = os.path.join(OPS_OUT, f"{_area(area)}.responder.json")
    if not os.path.exists(p):
        raise HTTPException(404, "no responder sidecar")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


@router.get("/health")
def health():
    from .collect import health as h

    p = os.path.join(OPS_OUT, "health.json")
    if not os.path.exists(p) or time.time() - os.path.getmtime(p) > 600:
        with _lock:
            if not os.path.exists(p) or time.time() - os.path.getmtime(p) > 600:
                h.run(write=True)
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


@router.get("/report")
def report():
    if not os.path.exists(REPORT):
        return {"status": "NO_REPORT"}
    with open(REPORT, encoding="utf-8") as fh:
        return json.load(fh)


class LabelReq(BaseModel):
    area: str = Field(max_length=40)
    ncr_id: str = Field(max_length=36)
    label: str
    labeler: str = Field(min_length=1, max_length=40)
    notes: str = Field(default="", max_length=300)

    @field_validator("label")
    @classmethod
    def _lab(cls, v: str) -> str:
        if v not in LABEL_CHOICES:
            raise ValueError(f"label must be one of {LABEL_CHOICES}")
        return v

    @field_validator("labeler")
    @classmethod
    def _who(cls, v: str) -> str:
        v = re.sub(r"[^\w .-]", "", v).strip()
        if not v:
            raise ValueError("labeler required")
        return v


@router.post("/labels")
def add_label(req: LabelReq, request: Request, authorization: str | None = Header(default=None)):
    from .plan.events import event_for_area

    _responder(request, authorization)
    _area(req.area)
    if not _UUID.fullmatch(req.ncr_id):
        raise HTTPException(400, "bad ncr_id")
    fc = _load(req.area)
    if not any(f["properties"]["ncr_id"] == req.ncr_id for f in fc["features"]):
        raise HTTPException(404, "structure not in this assessment")
    found = event_for_area(req.area)
    role = found[1].role if found else "UNREGISTERED"
    post = next((i for i in (fc["properties"].get("provenance") or {}).get("imagery", []) if i.get("role") == "post"), {})
    os.makedirs(LABELS, exist_ok=True)
    path = os.path.join(LABELS, f"{req.area}.csv")
    new = not os.path.exists(path)
    with _lock, open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["ncr_id", "label", "labeler", "protocol", "imagery_date", "aoi_role", "labeled_utc", "notes"])
        w.writerow([req.ncr_id, req.label, req.labeler, PROTOCOL,
                    post.get("acquired_utc") or post.get("date_label") or post.get("dataset_version") or "",
                    role, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), req.notes])
    return {"ok": True, "aoi_role": role, "file": os.path.basename(path)}


@router.get("/labels/{area}")
def get_labels(area: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    path = os.path.join(LABELS, f"{_area(area)}.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@router.get("/areas/{area}/export.zip")
def export_zip(area: str, request: Request, authorization: str | None = Header(default=None)):
    from .disseminate.exports import export_area

    _responder(request, authorization)
    _load(area)
    d = os.path.join(OPS_OUT, "exports", area)
    export_area(area, mode="responder", out_dir=d)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(d):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, d))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="nc-recon-{area}-responder.zip"'})
