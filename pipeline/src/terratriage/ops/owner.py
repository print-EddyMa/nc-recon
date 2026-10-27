"""Owner evidence record and the public "is my house OK?" check.

Two answers, deliberately unequal:

* **Owner record.** One building's call, its probability, the imagery dates,
  the evidence in plain words and whether people have confirmed it. Only
  through a signed, expiring link that an operator issues to a verified owner
  or occupant (legal aid intake, a county call centre, a FEMA registration
  match: the verification happens outside Groma, by a partner who can do it).
  The link is the credential, so it travels in the URL fragment (`#/record/<t>`)
  and is posted in a request body, never in a query string a server log keeps.

* **Public check.** Anyone may ask about a place and gets a coarse answer for
  the buildings around it: banded shares, never a count small enough to
  single out one home, never the building's own call. After the January 2025
  fires, burglaries in the Altadena burn area rose by more than 400% and
  undamaged homes were targeted: a public per-building map is a looting map.

Secrets: `NCR_OWNER_SECRET` signs links. Without it, links are refused unless
the server runs in local development mode (`NCR_DEV_OPEN=1`), which uses a
per-process secret so dev links die with the process. Revoked link ids are
kept in `NCR_OWNER_REVOKED` (default data/owner_revoked.json).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
from typing import Any

from . import DATA_DIR, DISCLAIMER, OPS_OUT
from .analyze.classes import FEMA, FEMA_LABEL

MAX_DAYS = 90
BLOCK_RADIUS_M = 250.0
BLOCK_MIN = 8            # fewer buildings than this nearby: no answer at all
_dev_secret = secrets.token_bytes(32)
_lock = threading.Lock()
_B64 = re.compile(r"^[A-Za-z0-9_-]{8,400}$")

CHANNEL = {
    "E1": "General image model", "E2": "Pixel change inside the outline", "E4": "Blue tarps on the roof",
    "E5": "Flood depth against the first floor", "E6": "Lidar ground change", "H": "Hazard footprint",
    "M1": "Groma wildfire model",
}
UNAVAILABLE = {
    "NO_WSE_SOURCE_ON_REACH": "no published river level for this stretch of river",
}


class LinkError(Exception):
    """A link that is malformed, forged, expired or revoked."""


def _secret() -> bytes:
    s = os.environ.get("NCR_OWNER_SECRET", "").strip()
    if s:
        return hashlib.sha256(s.encode()).digest()
    from .auth import dev_open

    if dev_open():
        return _dev_secret
    raise LinkError("owner links are not configured on this server (set NCR_OWNER_SECRET)")


def _revoked_path() -> str:
    return os.environ.get("NCR_OWNER_REVOKED") or os.path.join(DATA_DIR, "owner_revoked.json")


def _revoked() -> set[str]:
    p = _revoked_path()
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8") as fh:
        return set(json.load(fh).get("revoked") or [])


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue(area: str, ncr_id: str, days: int = 30, now: float | None = None) -> dict[str, Any]:
    days = max(1, min(int(days), MAX_DAYS))
    now = time.time() if now is None else now
    claims = {"a": area, "b": ncr_id, "x": int(now + days * 86400), "j": secrets.token_hex(8)}
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest()[:24])
    return {"token": f"{body}.{sig}", "id": claims["j"], "expires_utc": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(claims["x"])), "days": days}


def verify(token: str, now: float | None = None) -> dict[str, Any]:
    if not isinstance(token, str) or token.count(".") != 1:
        raise LinkError("this link is not valid")
    body, sig = token.split(".")
    if not (_B64.match(body) and _B64.match(sig)):
        raise LinkError("this link is not valid")
    good = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest()[:24])
    if not hmac.compare_digest(good, sig):
        raise LinkError("this link is not valid")
    try:
        claims = json.loads(_unb64(body))
    except ValueError as ex:
        raise LinkError("this link is not valid") from ex
    if (time.time() if now is None else now) > claims.get("x", 0):
        raise LinkError("this link has expired: ask whoever sent it for a new one")
    if claims.get("j") in _revoked():
        raise LinkError("this link was withdrawn: ask whoever sent it for a new one")
    return claims


def revoke(link_id: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{16}", link_id or ""):
        raise ValueError("bad link id")
    with _lock:
        ids = _revoked() | {link_id}
        p = _revoked_path()
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"revoked": sorted(ids)}, fh)
        os.replace(tmp, p)


# --------------------------------------------------------------------------- #
# the owner's record
# --------------------------------------------------------------------------- #
def _lean(lik: list[float] | None) -> str | None:
    if not lik or len(lik) != len(FEMA) or max(lik) - min(lik) < 0.05:
        return None
    return FEMA_LABEL[FEMA[max(range(len(FEMA)), key=lambda i: lik[i])]]


def evidence_lines(p: dict[str, Any]) -> list[dict[str, Any]]:
    """Each evidence channel in plain words: what it saw, or why it is missing."""
    out = []
    for e in p.get("evidence") or []:
        name = CHANNEL.get(e.get("id"), e.get("id"))
        if not e.get("available"):
            why = e.get("unavailable_reason") or ""
            out.append({"channel": name, "says": "Not available: " + UNAVAILABLE.get(why, why.replace("_", " ").lower()),
                        "used": False})
            continue
        if not e.get("weight"):
            continue
        lean = _lean(e.get("likelihood"))
        det = e.get("detail") or {}
        if e.get("id") == "E2" and det.get("z") is not None:
            says = (f"The ground inside the outline changed {det['z']:+.1f} standard deviations from the area's "
                    "typical change" + (f"; on its own this points to {lean}" if lean else ""))
        elif e.get("id") == "E4":
            says = "A blue tarp was seen" if (det.get("tarp_frac_new") or 0) > 0.05 else "No blue tarp seen"
        else:
            says = f"Leans {lean}" if lean else "No clear lean"
        out.append({"channel": name, "says": says, "used": True, "weight": e.get("weight")})
    return out


def _img_label(run: dict[str, Any], role: str) -> str | None:
    """The imagery's date as its source states it (a date, or a program cycle)."""
    for im in ((run.get("provenance") or {}).get("imagery") or []):
        if im.get("role") == role:
            return (im.get("acquired_utc") or "")[:10] or im.get("date_label") or im.get("dataset_version")
    return None


def _fc(area: str) -> dict[str, Any]:
    with open(os.path.join(OPS_OUT, f"{area}.geojson"), encoding="utf-8") as fh:
        return json.load(fh)


def record(area: str, ncr_id: str) -> dict[str, Any]:
    from .disseminate.ida import validation_note
    from .disseminate.exports import state_name
    from . import truth

    fc = _fc(area)
    feat = next((f for f in fc["features"] if f["properties"]["ncr_id"] == ncr_id), None)
    if feat is None:
        raise LookupError("this building is not in the assessment any more")
    p = feat["properties"]
    run = fc["properties"]
    ev, aoi = run.get("event") or {}, run.get("aoi") or {}
    fema = p.get("fema") or {}
    rsp_path = os.path.join(OPS_OUT, f"{area}.responder.json")
    addr = None
    if os.path.exists(rsp_path):
        with open(rsp_path, encoding="utf-8") as fh:
            addr = ((json.load(fh).get("structures") or {}).get(ncr_id) or {}).get("address")
    hazards: list[str] = []
    rp = os.path.join(OPS_OUT, f"{area}.response.json")
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as fh:
            hazards = ((json.load(fh).get("summary") or {}).get("hazards")) or []
    lvl = p.get("damage_level")
    probs = p.get("damage_probs") or {}
    people = truth.consensus(area).get(ncr_id) or {}
    confirmed = people.get("status") == "verified"
    return {
        "area": area, "ncr_id": ncr_id, "address": addr, "usng_10m": p.get("usng_10m"),
        "lon": p["centroid"][0], "lat": p["centroid"][1],
        "event": ev.get("name"), "declarations": ev.get("declarations") or [],
        "county": aoi.get("county"), "state": state_name(fc),
        "level": lvl, "level_label": FEMA_LABEL.get(lvl, "Not assessed") if lvl else "Not assessed",
        "probability": round(probs.get(lvl) or 0, 3) if lvl else None,
        "probs": {FEMA_LABEL[c]: round(probs.get(c) or 0, 3) for c in FEMA} if probs else {},
        "needs_review": bool(p.get("needs_review")),
        "people_checked": {"status": people.get("status") or "not yet", "label": FEMA_LABEL.get(people.get("label"))
                           if people.get("label") else None, "judgments": people.get("n", 0)},
        "field_confirmed": False,
        "confirmed_by_people": confirmed,
        "imagery": {"before": _img_label(run, "pre"),
                    "after": fema.get("IMG_DATE") or fema.get("IMG_DATE_RANGE") or _img_label(run, "post")},
        "evidence": evidence_lines(p),
        "validation": validation_note(hazards, "owner"),
        "run_id": run.get("run_id"), "assessed_utc": run.get("generated_utc"),
        "uses": [
            "FEMA Individual Assistance: if you were denied for insufficient damage, attach this record and your "
            "own photos to the appeal, and ask for a new inspection.",
            "Insurance: give this record to your adjuster or public adjuster with your own photos and receipts. "
            "It is an independent, dated before-and-after, not an inspection.",
            "Keep this record yourself. If your adjuster changes, you do not have to start over.",
        ],
        "disclaimer": DISCLAIMER + " This is a remote assessment from imagery: it has not been confirmed by "
                                   "anyone at the building.",
    }


# --------------------------------------------------------------------------- #
# the public answer: nearby buildings, banded
# --------------------------------------------------------------------------- #
def _band(share: float) -> str:
    if share < 0.10:
        return "few"
    if share < 0.34:
        return "some"
    if share < 0.67:
        return "many"
    return "most"


def _norm(addr: str) -> str:
    a = re.sub(r"[^a-z0-9 ]", " ", (addr or "").lower())
    for long, short in ((" road", " rd"), (" street", " st"), (" drive", " dr"), (" avenue", " ave"),
                        (" lane", " ln"), (" court", " ct"), (" circle", " cir"), (" highway", " hwy")):
        a = re.sub(rf"{long}\b", short, a)
    return re.sub(r"\s+", " ", a).strip()


def find_address(area: str, q: str) -> tuple[float, float] | None:
    """Locate a typed street address among the area's structures (the
    responder sidecar). Returns only a point: the caller never learns which
    building matched or what was called there."""
    want = _norm(q)
    if len(want) < 5 or not re.match(r"^\d+ \S", want):
        return None
    rsp_path = os.path.join(OPS_OUT, f"{area}.responder.json")
    if not os.path.exists(rsp_path):
        return None
    with open(rsp_path, encoding="utf-8") as fh:
        rs = json.load(fh).get("structures") or {}
    hit = None
    for nid, r in rs.items():
        street = _norm((r.get("address") or "").split(",")[0])
        if street and (street == want or want.startswith(street + " ")):
            hit = nid
            break
    if hit is None:
        return None
    for f in _fc(area)["features"]:
        if f["properties"]["ncr_id"] == hit:
            return tuple(f["properties"]["centroid"])  # type: ignore[return-value]
    return None


def nearby(area: str, lon: float, lat: float) -> dict[str, Any]:
    fc = _fc(area)
    kx = 111320.0 * math.cos(math.radians(lat))
    near = []
    for f in fc["features"]:
        x, y = f["properties"]["centroid"]
        if math.hypot((x - lon) * kx, (y - lat) * 110540.0) <= BLOCK_RADIUS_M:
            near.append(f["properties"])
    run = fc["properties"]
    base = {"area": area, "radius_m": int(BLOCK_RADIUS_M), "event": (run.get("event") or {}).get("name"),
            "assessed_utc": run.get("generated_utc"), "disclaimer": DISCLAIMER}
    assessed = [p for p in near if p.get("damage_probs")]
    if len(assessed) < BLOCK_MIN:
        return {**base, "answer": "too_few",
                "text": "Too few buildings near this place to answer without pointing at one home. "
                        "Ask your county emergency management office, or a legal aid group that can send you "
                        "a private record for your own home."}
    n = len(assessed)
    severe = sum((p["damage_probs"].get("major") or 0) + (p["damage_probs"].get("destroyed") or 0) for p in assessed) / n
    anyd = sum(1 - (p["damage_probs"].get("no_damage") or 0) for p in assessed) / n
    sb, ab = _band(severe), _band(anyd)
    if sb in ("many", "most"):
        text = f"{sb.capitalize()} buildings within about {int(BLOCK_RADIUS_M)} m look badly damaged or destroyed."
    elif sb == "some":
        text = f"Some buildings within about {int(BLOCK_RADIUS_M)} m look badly damaged or destroyed."
    elif ab in ("many", "most", "some"):
        text = (f"{ab.capitalize()} buildings within about {int(BLOCK_RADIUS_M)} m show some damage, "
                "few look badly damaged.")
    else:
        text = f"Few buildings within about {int(BLOCK_RADIUS_M)} m show damage from above."
    return {**base, "answer": "banded", "severe_band": sb, "any_damage_band": ab, "buildings_band":
            "8 to 20" if n <= 20 else ("21 to 60" if n <= 60 else "more than 60"), "text": text,
            "note": "From imagery, for the buildings around this place, not for any one home. It cannot tell you "
                    "about your own home: for that, ask for a private record."}
