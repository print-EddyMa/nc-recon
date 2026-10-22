"""Ops-mode HTTP API (mounted by server.py under /ops).

Public (aggregates only, nothing at building level):
  GET  /ops/areas                       area summaries (counts, ranges, caveats)
  GET  /ops/areas/{area}/public.geojson tract-level product, small counts withheld
  GET  /ops/areas/{area}/impact         tract-level people / need
  GET  /ops/health                      collection board (refreshed <= 10 min)
  GET  /ops/report                      latest ACCURACY_REPORT.json
  GET  /ops/meta                        disclaimer, class vocab, colours

Responder (bearer token; refused when no token is configured, unless the
operator runs with NCR_DEV_OPEN=1 for local development - see ops/auth.py):
  GET  /ops/areas/{area}                ops GeoJSON (building level; no addresses)
  GET  /ops/areas/{area}/chip/{ncr_id}/{pre|post}.png
  GET  /ops/areas/{area}/tiles/{pre|post}/{z}/{x}/{y}   map tiles of the assessed imagery
  GET  /ops/areas/{area}/brief.html     situation brief (its map shows structures)
  GET  /ops/areas/{area}/responder      ncr_id -> address sidecar
  GET  /ops/areas/{area}/fema-assistance  FEMA assistance by ZIP beside the assessment
  GET  /ops/areas/{area}/field-reference  Helene SAR field categories beside the calls (Buncombe)
  GET  /ops/truth/next?area=&worker=&role=   NC Recon Verify: next blind verification task
  POST /ops/truth/judgments                  one blind judgment
  GET  /ops/truth/areas/{area}               verification progress for an area
  GET  /ops/truth/metrics                    verified structures, verifiers, reliability
  GET  /ops/truth/export.zip                 versioned dataset of verified labels + datasheet
  POST /ops/labels                      append a truth label (TUNE/TEST aware)
  GET  /ops/areas/{area}/export.zip     GeoJSON/CSV/KML/GPKG/FileGDB/Survey123 bundle
  POST /ops/assess                      queue an assessment; GET /ops/assess/{id}, GET /ops/jobs
  DELETE /ops/assess/{id}               cancel a queued or running assessment
  POST /ops/areas/{area}/reassess       run an operational area again on its stored imagery
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

from . import DATA_DIR, DISCLAIMER, PIPELINE_ROOT, audit
from .analyze.classes import FEMA, FEMA_LABEL

OPS_OUT = os.path.join(DATA_DIR, "output", "ops")
LABELS = os.environ.get("NCR_LABELS_DIR") or os.path.join(DATA_DIR, "labels")
RAW = os.path.join(DATA_DIR, "raw")
REPORT = os.path.join(os.environ.get("NCR_REPORTS_DIR") or os.path.join(PIPELINE_ROOT, "..", "reports"),
                      "ACCURACY_REPORT.json")
_AREA = re.compile(r"[a-z0-9_]{1,40}")
_UUID = re.compile(r"[0-9a-f-]{36}")
PROTOCOL = "ncr-label-v1"
LABEL_CHOICES = (*FEMA, "cannot_tell")

router = APIRouter(prefix="/ops")
_label_lock = threading.Lock()      # serialises appends to the label CSVs
_health_lock = threading.Lock()     # one health refresh at a time
_health_busy = threading.Event()
_cache: dict[str, tuple[float, Any]] = {}
_bbox_cache: dict[str, tuple[float, list[float] | None]] = {}
HEALTH_TTL_S = 600
HEALTH_MIN_RECHECK_S = 60


def _area(area: str) -> str:
    if not _AREA.fullmatch(area):
        raise HTTPException(400, "bad area id")
    return area


def _responder(request: Request, authorization: str | None) -> None:
    from . import auth

    auth.check(authorization)


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
    aoi = fc["properties"].setdefault("aoi", {})
    if not aoi.get("name"):
        from .plan.events import area_name

        aoi["name"] = area_name(area)
    if not aoi.get("county"):
        # assessed before operational areas recorded their county: read it off
        # the structures' census blocks
        from .counties import county_of

        aoi["county"] = county_of(f["properties"].get("cbfips_2010") for f in fc["features"])
    _cache[p] = (mt, fc)
    return fc


def _bbox(area: str) -> list[float] | None:
    """[west, south, east, north] of an area's structures, for the public
    overview map. Coarse on purpose: snapped outward to 0.001 degree (about
    100 m), and withheld when the area has fewer structures than the public
    suppression threshold, so the box never pins down a home."""
    import math

    from .disseminate.aggregate import SUPPRESS

    p = os.path.join(OPS_OUT, f"{area}.geojson")
    fc = _load(area)
    mt = _cache[p][0]
    hit = _bbox_cache.get(p)
    if hit and hit[0] == mt:
        return hit[1]
    pts = [f["properties"].get("centroid") for f in fc["features"]]
    pts = [c for c in pts if c]
    box = None
    if len(pts) >= SUPPRESS:
        xs, ys = [c[0] for c in pts], [c[1] for c in pts]
        box = [math.floor(min(xs) * 1000) / 1000, math.floor(min(ys) * 1000) / 1000,
               math.ceil(max(xs) * 1000) / 1000, math.ceil(max(ys) * 1000) / 1000]
    _bbox_cache[p] = (mt, box)
    return box


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
                "calibration", "warnings", "pair_context")} | {"id": f[:-8], "bbox": _bbox(f[:-8])})
    return out


@router.get("/areas/{area}")
def area(area: str, request: Request, authorization: str | None = Header(default=None)):
    # building-level (centroids ~ addresses): responder only
    _responder(request, authorization)
    fc = _load(area)
    audit.record("view_area", request, area)
    return JSONResponse(fc, headers={"Cache-Control": "no-cache, private"})


@router.get("/areas/{area}/chip/{ncr_id}/{kind}.png")
def chip(area: str, ncr_id: str, kind: str, request: Request, size: int = 256, pad_m: float = 12.0,
         authorization: str | None = Header(default=None)):
    import numpy as np
    import rasterio
    from PIL import Image, ImageDraw
    from rasterio.windows import from_bounds
    from shapely.geometry import shape
    from shapely.ops import transform as st

    from .geodesy import transformer
    from .process import imagery

    _responder(request, authorization)
    if kind not in ("pre", "post") or not _UUID.fullmatch(ncr_id):
        raise HTTPException(400, "bad chip request")
    fc = _load(area)
    feat = next((f for f in fc["features"] if f["properties"]["ncr_id"] == ncr_id), None)
    if feat is None:
        raise HTTPException(404, "no such structure")
    from .plan.events import event_for_area

    found = event_for_area(area)
    pre, post = imagery.pair_for_area(RAW, area, (found[0].maxar_event if found else None) or "")
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
                    headers={"Cache-Control": "private, max-age=3600",
                             "Cross-Origin-Resource-Policy": "cross-origin"})


# 1x1 transparent PNG: "no imagery here" without a console-spamming 404
_BLANK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d49444154789c626001000000050001a5f645400000000049454e44ae426082")


@router.get("/areas/{area}/tiles/{kind}/{z}/{x}/{y}")
def image_tile(area: str, kind: str, z: int, x: int, y: int, request: Request,
               authorization: str | None = Header(default=None)):
    """Map tile of the before / after imagery this assessment read."""
    from .disseminate import tiles
    from .plan.events import event_for_area
    from .process import imagery

    _responder(request, authorization)
    if kind not in ("pre", "post") or not tiles.MIN_ZOOM <= z <= tiles.MAX_ZOOM or not (
            0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise HTTPException(400, "bad tile request")
    _load(area)
    found = event_for_area(area)
    try:
        pre, post = imagery.pair_for_area(RAW, area, (found[0].maxar_event if found else None) or "")
    except FileNotFoundError as ex:
        raise HTTPException(404, "the imagery for this assessment is no longer stored") from ex
    out = tiles.get(area, kind, pre.path if kind == "pre" else post.path, z, x, y)
    body, media = out if out else (_BLANK_PNG, "image/png")
    return Response(body, media_type=media, headers={"Cache-Control": "private, max-age=86400",
                                                     "Cross-Origin-Resource-Policy": "cross-origin"})


@router.get("/areas/{area}/impact")
def impact(area: str, authorization: str | None = Header(default=None)):
    """People / need by tract. Responders get it whole; the public gets the same
    small-count suppression as the public tract product."""
    from . import auth
    from .disseminate.aggregate import SUPPRESS

    p = os.path.join(OPS_OUT, f"{_area(area)}.impact.json")
    if not os.path.exists(p):
        raise HTTPException(404, "no impact run for this area")
    with open(p, encoding="utf-8") as fh:
        d = json.load(fh)
    try:
        auth.check(authorization)
        return d
    except HTTPException:
        pass
    for t in d.get("tracts", []):
        if (t.get("structures") or 0) < SUPPRESS:
            t.update(structures=None, expected_displaced=None, need_index=None, suppressed=True)
    ua = d.get("unassessed_residential") or {}
    if ua and (ua.get("structures") or 0) < SUPPRESS:
        d["unassessed_residential"] = {"structures": None, "occupants_nsi": None, "suppressed": True}
    return d


@router.get("/areas/{area}/public.geojson")
def public_tracts(area: str):
    from .disseminate.aggregate import aggregate

    from .collect.base import SourceUnavailable

    _load(area)
    try:
        path = aggregate(area)
    except SourceUnavailable as ex:
        # tract boundaries come from the CDC SVI service; nothing is cached yet
        raise HTTPException(503, "census tract boundaries (CDC SVI) are unreachable; try again later") from ex
    with open(path, encoding="utf-8") as fh:
        return JSONResponse(json.load(fh))


@router.get("/areas/{area}/fema-assistance")
def fema_assistance(area: str, request: Request, authorization: str | None = Header(default=None)):
    """FEMA Individual Assistance by ZIP code, beside this assessment's own
    numbers for the same ZIPs. Responder-only: the ZIPs come from addresses."""
    from .analyze import fema_reference

    _responder(request, authorization)
    _load(area)
    return fema_reference.run(area)


@router.get("/areas/{area}/field-reference")
def field_reference(area: str, request: Request, authorization: str | None = Header(default=None)):
    """NC Recon's calls beside the Helene search-and-rescue field categories
    for the same structures (Buncombe's public SARCOP extract). Responder-only:
    the per-structure pairs locate damage calls. Read from the stored
    comparison (`run.py ops-sarcop`); never computed on request, and never for
    a TEST area."""
    _responder(request, authorization)
    _load(area)
    p = os.path.join(OPS_OUT, f"{_area(area)}.sarcop_reference.json")
    if not os.path.exists(p):
        raise HTTPException(404, "no field comparison for this area (only Buncombe County areas have one)")
    with open(p, encoding="utf-8") as fh:
        d = json.load(fh)
    d.pop("pairs", None)
    return JSONResponse(d)


class JudgmentReq(BaseModel):
    area: str = Field(max_length=40)
    ncr_id: str = Field(max_length=36)
    label: str
    worker: str = Field(min_length=1, max_length=40)
    role: str = "verifier"
    kind: str = "remote"
    blind: bool = True
    seconds: float | None = Field(default=None, ge=0, le=36000)


@router.get("/truth/next")
def truth_next(area: str, worker: str, request: Request, role: str = "verifier",
               authorization: str | None = Header(default=None)):
    """The next blind verification task: a building and its imagery dates,
    never the model's call."""
    from . import truth

    _responder(request, authorization)
    _load(area)
    try:
        t = truth.next_task(area, worker, role)
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from ex
    return t or {"area": area, "ncr_id": None, "done": True}


@router.post("/truth/judgments")
def truth_judge(req: JudgmentReq, request: Request, authorization: str | None = Header(default=None)):
    from . import truth

    _responder(request, authorization)
    _area(req.area)
    if not _UUID.fullmatch(req.ncr_id):
        raise HTTPException(400, "bad ncr_id")
    _load(req.area)
    try:
        j = truth.submit(req.area, req.ncr_id, req.label, req.worker, role=req.role, kind=req.kind,
                         blind=req.blind, seconds=req.seconds)
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from ex
    except LookupError as ex:
        raise HTTPException(404, str(ex)) from ex
    except PermissionError as ex:
        raise HTTPException(409, str(ex)) from ex
    audit.record("verify", request, req.area, ncr_id=req.ncr_id, label=req.label, worker=j["worker"])
    return {"ok": True, "status": truth.consensus(req.area).get(req.ncr_id)}


@router.get("/truth/areas/{area}")
def truth_area(area: str, request: Request, authorization: str | None = Header(default=None)):
    from . import truth

    _responder(request, authorization)
    _load(area)
    return truth.area_status(_area(area))


@router.get("/truth/metrics")
def truth_metrics(request: Request, authorization: str | None = Header(default=None)):
    from . import truth

    _responder(request, authorization)
    return truth.metrics()


@router.get("/truth/export.zip")
def truth_export(request: Request, area: str | None = None, authorization: str | None = Header(default=None)):
    from . import truth

    _responder(request, authorization)
    data, sheet = truth.export([_area(area)] if area else None)
    audit.record("verify_export", request, area, records=sheet["records"])
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="ncrecon-verify-dataset.zip"'})


@router.get("/areas/{area}/brief.html")
def brief_html(area: str, request: Request, authorization: str | None = Header(default=None)):
    from fastapi.responses import HTMLResponse

    from .disseminate.brief import brief

    _responder(request, authorization)  # its map plots every structure
    _load(area)
    audit.record("brief", request, area)
    with open(brief(area), encoding="utf-8") as fh:
        return HTMLResponse(fh.read())


@router.get("/areas/{area}/responder")
def responder(area: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    audit.record("view_addresses", request, area)
    p = os.path.join(OPS_OUT, f"{_area(area)}.responder.json")
    if not os.path.exists(p):
        raise HTTPException(404, "no responder sidecar")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _refresh_health() -> None:
    from .collect import health as h

    try:
        with _health_lock:
            h.run(write=True)
    except Exception as ex:  # noqa: BLE001 - a failed refresh keeps the last board
        print(f"[ops] health refresh failed: {ex}")
    finally:
        _health_busy.clear()


@router.get("/health")
def health(recheck: bool = False):
    """The collection board. Serves the last written board straight away and
    refreshes it in the background when it is older than 10 minutes, so a slow
    upstream never holds up the page (or anything else). `recheck=1` asks for
    a refresh now; honoured at most once a minute."""
    from .collect import health as h

    p = os.path.join(OPS_OUT, "health.json")
    if not os.path.exists(p):
        # first ever call: nothing to show yet, so this one waits
        with _health_lock:
            if not os.path.exists(p):
                h.run(write=True)
    else:
        age = time.time() - os.path.getmtime(p)
        if (age > HEALTH_TTL_S or (recheck and age > HEALTH_MIN_RECHECK_S)) and not _health_busy.is_set():
            _health_busy.set()
            threading.Thread(target=_refresh_health, daemon=True, name="ops-health").start()
    if not os.path.exists(p):
        raise HTTPException(503, "data-source status is not available yet")
    with open(p, encoding="utf-8") as fh:
        d = json.load(fh)
    d["refreshing"] = _health_busy.is_set()
    return d


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
    with _label_lock, open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["ncr_id", "label", "labeler", "protocol", "imagery_date", "aoi_role", "labeled_utc", "notes"])
        w.writerow([req.ncr_id, req.label, req.labeler, PROTOCOL,
                    post.get("acquired_utc") or post.get("date_label") or post.get("dataset_version") or "",
                    role, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), req.notes])
    audit.record("label", request, req.area, ncr_id=req.ncr_id, label=req.label, labeler=req.labeler)
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
    audit.record("export", request, area)
    d = os.path.join(OPS_OUT, "exports", area)
    try:
        export_area(area, mode="responder", out_dir=d)
    except ValueError as ex:
        raise HTTPException(409, str(ex)) from ex
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(d):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, d))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="nc-recon-{area}-responder.zip"'})


# --------------------------------------------------------------------------- #
# events + operational assessments
# --------------------------------------------------------------------------- #
@router.get("/events")
def events():
    from .plan.events import load_events

    return [ev.to_summary() for ev in load_events().values()]


class EventReq(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,40}$")
    name: str = Field(min_length=3, max_length=80)
    incident_begin: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    disaster_numbers: list[int] = Field(default_factory=list, max_length=4)
    eri_prefix: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{3,60}$")
    hazards: list[str] = Field(default_factory=list, max_length=6)


@router.post("/events")
def create_event(req: EventReq, request: Request, authorization: str | None = Header(default=None)):
    from .plan.events import add_provisional_event

    _responder(request, authorization)
    try:
        ev = add_provisional_event(req.id, req.name, req.incident_begin, hazards=req.hazards,
                                   eri_prefix=req.eri_prefix, disaster_numbers=req.disaster_numbers or None)
    except (ValueError, LookupError) as ex:
        raise HTTPException(400, str(ex)) from ex
    audit.record("create_event", request, None, event=req.id)
    return ev.to_summary()


@router.get("/coverage")
def coverage(event: str, lon: float, lat: float):
    """Which post-event imagery would be used at this point (no data returned)."""
    from .geodesy import in_nc
    from .jobs import choose_post_source
    from .plan.events import load_events

    evs = load_events()
    if event not in evs:
        raise HTTPException(404, "unknown event")
    if not in_nc(lon, lat, pad=0.1):
        return {"covered": False, "reason": "outside North Carolina"}
    try:
        return {"covered": True, "post_source": choose_post_source(evs[event], lon, lat)}
    except LookupError as ex:
        return {"covered": False, "reason": str(ex)}


class AssessReq(BaseModel):
    event: str = Field(max_length=40)
    name: str = Field(min_length=2, max_length=60)
    lon: float = Field(ge=-85, le=-75)
    lat: float = Field(ge=33, le=37)
    half_m: float = Field(default=800, ge=200, le=1500)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = re.sub(r"[^\w .,'-]", "", v).strip()
        if len(v) < 2:
            raise ValueError("name required")
        return v


@router.post("/assess")
def assess(req: AssessReq, request: Request, authorization: str | None = Header(default=None)):
    from . import jobs

    _responder(request, authorization)
    try:
        job = jobs.submit(req.event, req.name, req.lon, req.lat, req.half_m)
    except OverflowError as ex:
        raise HTTPException(429, str(ex)) from ex
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from ex
    audit.record("assess", request, job.area, event=req.event, lon=req.lon, lat=req.lat)
    return job.to_dict()


@router.post("/areas/{area}/reassess")
def reassess(area: str, request: Request, authorization: str | None = Header(default=None)):
    """Assess an operational area again from the imagery it already has."""
    from . import jobs

    _responder(request, authorization)
    _area(area)
    try:
        job = jobs.submit_reassess(area)
    except LookupError as ex:
        raise HTTPException(404, str(ex)) from ex
    except PermissionError as ex:
        raise HTTPException(403, str(ex)) from ex
    except OverflowError as ex:
        raise HTTPException(429, str(ex)) from ex
    except ValueError as ex:
        raise HTTPException(409, str(ex)) from ex
    audit.record("reassess", request, area, job=job.id)
    return job.to_dict()


@router.get("/assess/{job_id}")
def assess_status(job_id: str, request: Request, authorization: str | None = Header(default=None)):
    from . import jobs

    _responder(request, authorization)
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return job.to_dict()


@router.delete("/assess/{job_id}")
def assess_cancel(job_id: str, request: Request, authorization: str | None = Header(default=None)):
    from . import jobs

    _responder(request, authorization)
    job = jobs.cancel(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    audit.record("cancel_assess", request, job.area, job=job_id)
    return job.to_dict()


@router.get("/jobs")
def job_list(request: Request, authorization: str | None = Header(default=None)):
    from . import jobs

    _responder(request, authorization)
    return [j.to_dict() for j in jobs.recent()]


@router.delete("/areas/{area}")
def delete_area(area: str, request: Request, authorization: str | None = Header(default=None)):
    from . import jobs

    _responder(request, authorization)
    _area(area)
    try:
        removed = jobs.delete_area(area)
    except PermissionError as ex:
        raise HTTPException(403, str(ex)) from ex
    if not removed:
        raise HTTPException(404, "no such operational area")
    audit.record("delete_area", request, area)
    _cache.pop(os.path.join(OPS_OUT, f"{area}.geojson"), None)
    return {"area": area, "removed": removed}
