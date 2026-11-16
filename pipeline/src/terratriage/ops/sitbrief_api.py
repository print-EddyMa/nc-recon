"""Situation brief as a case file (ops/sitbrief.py).

  GET /ops/areas/{area}/sitbrief?ai=0|1
      {items, evidence, written_by, model, traced, total, untraced, dropped,
       ai_error, ai_available, generated_utc, disclaimer, ...}

ai=0 (default): written by fixed rules. ai=1: Claude writes it from the
evidence list alone when the server has ANTHROPIC_API_KEY and is not offline;
otherwise, or on any error, the rules brief comes back with `ai_error` saying
why. Responder-only: the evidence carries sector grid references.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request

from . import audit
from .api import _area, _responder
from . import sitbrief as sb

router = APIRouter(prefix="/ops")


@router.get("/areas/{area}/sitbrief")
def sitbrief(area: str, request: Request, ai: int = Query(default=0, ge=0, le=1),
             authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    _area(area)
    try:
        res = sb.ai_brief(area) if ai else sb.rule_brief(area)
    except FileNotFoundError:
        raise HTTPException(404, f"no ops assessment for {area}") from None
    audit.record("sitbrief_claude" if res["written_by"] == "claude" else "sitbrief", request, area)
    return res
