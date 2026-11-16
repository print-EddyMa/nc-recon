"""Draft an event for any US disaster from its FEMA declaration.

`run.py ops-event-from-fema --disaster 4856 [--write]`

From one disaster number this fills in everything config/events.yaml would
need: the incident date and designated areas (OpenFEMA), the hazards
(config/hazards.yaml, from the incident type), the post-event imagery window
(widest default across those hazards) and which NOAA Emergency Response
Imagery folder and Maxar Open Data event match the disaster. Imagery matches
are suggestions scored by name and year; coverage at a point is still checked
when an area is assessed (`jobs.choose_post_source`).
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from .. import hazards as hz
from ..collect.base import DiskCache, http_json
from .events import Declaration, Event, add_provisional_event, fetch_declaration

ERI_BUCKET = "https://noaa-eri-pds.s3.amazonaws.com"
MAXAR_CATALOG = "https://maxar-opendata.s3.amazonaws.com/events/catalog.json"

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico", "VI": "Virgin Islands", "GU": "Guam", "DC": "District of Columbia",
}
# words that say nothing about which event a folder is
_STOP = {"pre", "event", "the", "and", "of", "update", "rgb"}
# hazard words in folder names, matched to our hazard ids
_HAZARD_WORDS = {
    "hurricane": {"wind", "coastal_surge", "riverine_flood"}, "tropical": {"wind", "riverine_flood"},
    "typhoon": {"wind"}, "cyclone": {"wind"}, "storm": {"wind", "flash_flood"},
    "flood": {"riverine_flood", "flash_flood", "coastal_surge"}, "flooding": {"riverine_flood", "flash_flood"},
    "fire": {"wildfire"}, "fires": {"wildfire"}, "wildfire": {"wildfire"}, "wildfires": {"wildfire"},
    "tornado": {"tornado"}, "tornadoes": {"tornado"}, "earthquake": {"earthquake"},
    "landslide": {"landslide"}, "volcano": {"volcanic"}, "noreaster": {"coastal_surge", "wind"},
}


@dataclass
class Draft:
    event_id: str
    name: str
    state: str
    hazards: list[str]
    disaster_number: int
    incident_begin: str
    designated_areas: list[str]
    post_days: list[int]
    eri_prefix: str | None
    maxar_event: str | None
    candidates: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t and t not in _STOP]


def eri_events(max_age_s: float = 86400) -> list[str]:
    cache = DiskCache("eri")
    hit = cache.get("events", max_age_s=max_age_s)
    if hit is not None:
        return hit
    from ..collect.eri import _get

    body = _get(f"{ERI_BUCKET}/?" + urllib.parse.urlencode({"list-type": "2", "delimiter": "/"}))
    out = [p.rstrip("/") for p in re.findall(r"<Prefix>([^<]+)</Prefix>", body)]
    cache.put("events", out)
    return out


def maxar_events(max_age_s: float = 86400) -> list[str]:
    cache = DiskCache("maxar")
    hit = cache.get("events", max_age_s=max_age_s)
    if hit is not None:
        return hit
    d = http_json(MAXAR_CATALOG, timeout=30)
    out = [ln["href"].split("/")[1] for ln in d.get("links", []) if ln.get("rel") == "child"]
    cache.put("events", out)
    return out


def score_folder(folder: str, decl: Declaration, hazards: list[str]) -> tuple[float, list[str]]:
    """Name/year match between an imagery folder and a declaration. Returns
    (score, reasons). A folder for another year scores 0."""
    toks = _tokens(folder)
    yr = decl.incident_begin.year
    years = {int(t) for t in toks if re.fullmatch(r"(19|20)\d\d", t)}
    years |= {2000 + int(t[-2:]) for t in toks if re.fullmatch(r"[a-z]*\d\d", t) and not t.isdigit()}
    if "pre" in folder.lower().split("_"):
        return 0.0, ["pre-event folder"]
    if years and yr not in years and not (decl.incident_begin.month == 12 and yr + 1 in years):
        return 0.0, [f"year {sorted(years)} is not {yr}"]
    areas = " ".join(decl.designated_areas)
    title = f"{decl.title} {STATES.get(decl.state, '')} {decl.incident_type} {areas} {areas.replace(' ', '')}".lower()
    score, why = 0.0, []
    if years:
        score += 1.0
        why.append(f"year {yr}")
    for t in toks:
        if t.isdigit():
            continue
        stem = t.rstrip("s")
        if len(stem) >= 4 and stem in title:
            score += 2.0
            why.append(f"'{t}' in title or state")
        elif set(hazards) & _HAZARD_WORDS.get(t, set()):
            score += 1.0
            why.append(f"'{t}' matches hazard")
    return score, why


def _rank(folders: list[str], decl: Declaration, hazards: list[str]) -> list[dict[str, Any]]:
    out = []
    for f in folders:
        s, why = score_folder(f, decl, hazards)
        if s >= 2.0:
            out.append({"folder": f, "score": s, "why": why})
    return sorted(out, key=lambda r: -r["score"])


def _pick(ranked: list[dict[str, Any]], min_score: float) -> str | None:
    """Best folder only when it clears the bar and is not tied with the next."""
    if not ranked or ranked[0]["score"] < min_score:
        return None
    if len(ranked) > 1 and ranked[1]["score"] == ranked[0]["score"]:
        return None
    return ranked[0]["folder"]


def event_id_for(decl: Declaration, hazards: list[str]) -> str:
    kind = (hazards[0] if hazards else "event").replace("_", "-")
    return f"{kind}-{decl.incident_begin.year}-{(decl.state or 'us').lower()}-dr{decl.disaster_number}"[:40]


def draft_from_declaration(number: int) -> Draft:
    decl = fetch_declaration(number)
    hazards = hz.hazards_for_incident(decl.incident_type)
    notes: list[str] = []
    cands: dict[str, list[dict[str, Any]]] = {}
    try:
        cands["eri"] = _rank(eri_events(), decl, hazards)
    except Exception as ex:  # noqa: BLE001 - imagery match is a suggestion
        notes.append(f"NOAA ERI listing unavailable: {str(ex)[:120]}")
        cands["eri"] = []
    try:
        cands["maxar"] = _rank(maxar_events(), decl, hazards)
    except Exception as ex:  # noqa: BLE001
        notes.append(f"Maxar Open Data catalog unavailable: {str(ex)[:120]}")
        cands["maxar"] = []
    eri, maxar = _pick(cands["eri"], 3.0), _pick(cands["maxar"], 4.0)
    if not eri and not maxar:
        notes.append("no open post-event imagery matched by name; add one by hand or wait for a "
                     "NOAA Emergency Response Imagery flight")
    if maxar:
        notes.append("Maxar Open Data is CC BY-NC: decision support only, never in paid products")
    title = decl.title.strip()
    if title.isupper():   # OpenFEMA titles are upper case; keep proper nouns readable
        title = re.sub(r"\b(And|Of|The|In)\b", lambda m: m.group(1).lower(), title.title())
    return Draft(
        event_id=event_id_for(decl, hazards),
        name=f"{title} ({decl.state}, {decl.fema_id})"[:80],
        state=decl.state or "US", hazards=hazards, disaster_number=decl.disaster_number,
        incident_begin=decl.incident_begin.isoformat(),
        designated_areas=list(decl.designated_areas), post_days=hz.post_days(hazards),
        eri_prefix=eri, maxar_event=maxar, candidates=cands, notes=notes,
    )


def create_from_declaration(number: int, event_id: str | None = None) -> tuple[Event, Draft]:
    d = draft_from_declaration(number)
    sources = [s for s, ok in (("eri", d.eri_prefix), ("maxar", d.maxar_event)) if ok]
    ev = add_provisional_event(
        event_id or d.event_id, d.name, d.incident_begin, state=d.state, hazards=d.hazards,
        eri_prefix=d.eri_prefix, post_sources=sources or ["eri", "maxar"],
        post_days=tuple(d.post_days), disaster_numbers=[d.disaster_number],
        maxar_event=d.maxar_event)
    return ev, d
