"""Self-check report for an assessed area (ops/selfcheck.py).

  GET /ops/areas/{area}/checks     verdict, every check with its margin, landing-zone margins

Responder-only, like the response products: the landing-zone rows locate
places near cut-off people. Computed on request from the stored outputs;
nothing is written. Checks label an assessment; they never gate an export.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from . import api as _api
from . import audit
from .api import _area, _load, _responder
from .selfcheck import run_checks

router = APIRouter(prefix="/ops")


@router.get("/areas/{area}/checks")
def area_checks(area: str, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    fc = _load(area)                      # 400 on a bad id, 404 when not assessed
    try:
        report = run_checks(_area(area), out_dir=_api.OPS_OUT, fc=fc)   # the same directory _load read
    except FileNotFoundError as ex:
        raise HTTPException(404, f"no ops assessment for {area}") from ex
    audit.record("view_checks", request, area)
    return JSONResponse(report, headers={"Cache-Control": "no-cache, private"})
