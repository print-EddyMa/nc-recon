"""Routes for the owner evidence record and the public check (see owner.py).

  POST /ops/owner/links          responder: issue a link for one building
  POST /ops/owner/links/revoke   responder: withdraw a link by its id
  POST /ops/owner/record         link holder: the building's record
  POST /ops/owner/chip           link holder: before / after image
  POST /ops/lookup               anyone: banded answer around an address or point (POST so a
                                 survivor's address never sits in a URL an access log keeps)
  GET  /ops/index                anyone: the Groma Index, every area (disseminate/index.py)
  GET  /ops/index/{area}         anyone: one area's preliminary damage summary

TEST areas are refused everywhere here: their building calls stay unseen
until the area is retired as a hold-out.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import audit, owner
from .api import _UUID, _area, _load, _responder, chip_png

router = APIRouter(prefix="/ops")


def _not_test(area: str) -> None:
    from .truth import area_role

    if area_role(area, _load(area)) == "TEST":
        raise HTTPException(409, "this area is held out for testing: retire it as a test area before sharing "
                                 "building-level answers from it")


class LinkReq(BaseModel):
    area: str = Field(max_length=40)
    ncr_id: str = Field(max_length=36)
    days: int = Field(default=30, ge=1, le=owner.MAX_DAYS)


class RevokeReq(BaseModel):
    id: str = Field(max_length=16)


class LookupReq(BaseModel):
    area: str = Field(max_length=40)
    q: str | None = Field(default=None, max_length=120)
    lon: float | None = Field(default=None, ge=-180, le=180)
    lat: float | None = Field(default=None, ge=-90, le=90)


class TokenReq(BaseModel):
    token: str = Field(max_length=600)
    kind: str | None = Field(default=None, max_length=4)


def _claims(token: str) -> dict:
    try:
        c = owner.verify(token)
    except owner.LinkError as ex:
        raise HTTPException(403, str(ex)) from ex
    _area(c["a"])
    if not _UUID.fullmatch(c["b"]):
        raise HTTPException(403, "this link is not valid")
    return c


@router.post("/owner/links")
def issue_link(req: LinkReq, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    area = _area(req.area)
    if not _UUID.fullmatch(req.ncr_id):
        raise HTTPException(400, "bad building id")
    _not_test(area)
    if not any(f["properties"]["ncr_id"] == req.ncr_id for f in _load(area)["features"]):
        raise HTTPException(404, "no such building in this assessment")
    try:
        out = owner.issue(area, req.ncr_id, req.days)
    except owner.LinkError as ex:
        raise HTTPException(503, str(ex)) from ex
    # the audit keeps who issued which link id for which building, never the token
    audit.record("owner_link_issued", request, area, ncr_id=req.ncr_id, link_id=out["id"], days=out["days"])
    return {**out, "path": f"#/record/{out['token']}"}


@router.post("/owner/links/revoke")
def revoke_link(req: RevokeReq, request: Request, authorization: str | None = Header(default=None)):
    _responder(request, authorization)
    try:
        owner.revoke(req.id)
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from ex
    audit.record("owner_link_revoked", request, None, link_id=req.id)
    return {"revoked": req.id}


@router.post("/owner/record")
def owner_record(req: TokenReq, request: Request):
    c = _claims(req.token)
    _not_test(c["a"])
    try:
        rec = owner.record(c["a"], c["b"])
    except LookupError as ex:
        raise HTTPException(404, str(ex)) from ex
    audit.record("owner_record_view", request, c["a"], link_id=c["j"])
    return {**rec, "expires_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(c["x"]))}


@router.post("/owner/chip")
def owner_chip(req: TokenReq, request: Request):
    c = _claims(req.token)
    _not_test(c["a"])
    if req.kind not in ("pre", "post"):
        raise HTTPException(400, "kind must be pre or post")
    return Response(chip_png(c["a"], c["b"], req.kind, 384, 18.0), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.post("/lookup")
def lookup(req: LookupReq, request: Request):
    area = _area(req.area)
    _not_test(area)
    lon, lat = req.lon, req.lat
    if req.q:
        pt = owner.find_address(area, req.q)
        if pt is None:
            return {"area": area, "answer": "not_found",
                    "text": "That address is not in this assessment. Check the house number and street, "
                            "or pick the place on the map."}
        lon, lat = pt
    if lon is None or lat is None:
        raise HTTPException(400, "give an address (q) or a point (lon, lat)")
    out = owner.nearby(area, lon, lat)
    # a rounded centre (about 100 m) so the map can show the place asked about, not the building
    out["center"] = [round(lon, 3), round(lat, 3)]
    audit.record("public_lookup", request, area)
    return out


@router.get("/index")
def index_all():
    from .disseminate import index

    return index.listing()


@router.get("/index/{area}")
def index_one(area: str):
    from .disseminate import index

    r = index.record(_area(area))
    if r is None:
        raise HTTPException(404, "no public index for this area")
    return r
