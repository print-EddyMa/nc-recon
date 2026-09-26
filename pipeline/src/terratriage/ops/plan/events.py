"""Ops event registry: incident periods from OpenFEMA, AOIs + windows from config.

Bug class guarded here: v2 mis-dated Helene (a "widest imagery gap" heuristic
put the event in 2021) and compared two *pre*-event images. In ops mode an
event's incident period comes from the federal declaration record, never from
imagery gaps or a hand table, and every imagery window is asserted against it:

    pre.end < incident.begin <= post.start
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import yaml

from .. import CONFIG_DIR
from ..collect.base import DiskCache, SchemaError, http_json
from ..provenance import Provenance

OPENFEMA = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
ROLES = ("TUNE", "TEST")


class WindowError(ValueError):
    pass


@dataclass(frozen=True)
class Declaration:
    disaster_number: int
    fema_id: str
    title: str
    incident_type: str
    incident_begin: date
    incident_end: date | None
    declared: date
    designated_areas: tuple[str, ...]
    ia_areas: tuple[str, ...]
    provenance: Provenance


@dataclass(frozen=True)
class Window:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise WindowError(f"window end {self.end} before start {self.start}")

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end


@dataclass(frozen=True)
class AOI:
    id: str
    role: str
    county: str
    center: tuple[float, float]
    status: str = "active"


@dataclass
class Event:
    id: str
    name: str
    state: str
    hazards: tuple[str, ...]
    declarations: tuple[Declaration, ...]
    pre: Window
    post: Window
    aois: dict[str, AOI] = field(default_factory=dict)
    maxar_event: str | None = None

    @property
    def incident_begin(self) -> date:
        return min(d.incident_begin for d in self.declarations)

    def assert_windows(self) -> None:
        check_windows(self.pre, self.post, self.incident_begin, self.id)

    def classify_image_date(self, d: date) -> str:
        """'pre' | 'post' | 'outside' - the only way ops code labels an image."""
        if self.pre.contains(d):
            return "pre"
        if self.post.contains(d):
            return "post"
        return "outside"

    def tune_aois(self) -> list[AOI]:
        return [a for a in self.aois.values() if a.role == "TUNE"]

    def test_aois(self) -> list[AOI]:
        return [a for a in self.aois.values() if a.role == "TEST"]


def check_windows(pre: Window, post: Window, incident_begin: date, label: str = "") -> None:
    if not pre.end < incident_begin:
        raise WindowError(
            f"{label}: pre window ends {pre.end}, not before incident begin {incident_begin}"
        )
    if not post.start >= incident_begin:
        raise WindowError(
            f"{label}: post window starts {post.start}, before incident begin {incident_begin}"
        )


def check_image_pair(pre_date: date, post_date: date, incident_begin: date, label: str = "") -> None:
    """Assert an actual pre/post image pair straddles the incident."""
    if not pre_date < incident_begin:
        raise WindowError(f"{label}: 'pre' image {pre_date} is not before incident {incident_begin}")
    if not post_date >= incident_begin:
        raise WindowError(f"{label}: 'post' image {post_date} is before incident {incident_begin}")


# --------------------------------------------------------------------------- #
# OpenFEMA
# --------------------------------------------------------------------------- #
def _d(s: str | None) -> date | None:
    return date.fromisoformat(s[:10]) if s else None


def parse_declaration(rows: list[dict[str, Any]], retrieved_url: str) -> Declaration:
    if not rows:
        raise SchemaError("no OpenFEMA rows for this disaster number")
    for k in ("disasterNumber", "incidentBeginDate", "declarationDate", "designatedArea"):
        if k not in rows[0]:
            raise SchemaError(f"OpenFEMA row missing {k}")
    r0 = rows[0]
    begin = _d(r0["incidentBeginDate"])
    if any(_d(r["incidentBeginDate"]) != begin for r in rows):
        raise SchemaError("designated areas disagree on incidentBeginDate")
    areas = tuple(sorted({r["designatedArea"] for r in rows}))
    # IA-era declarations set iaProgramDeclared; IHP-era ones (incl. DR-4827)
    # set ihProgramDeclared instead - either means individual assistance
    ia = tuple(sorted({r["designatedArea"] for r in rows
                       if r.get("iaProgramDeclared") or r.get("ihProgramDeclared")}))
    return Declaration(
        disaster_number=int(r0["disasterNumber"]),
        fema_id=r0.get("femaDeclarationString") or f"DR-{r0['disasterNumber']}",
        title=r0.get("declarationTitle", ""),
        incident_type=r0.get("incidentType", ""),
        incident_begin=begin,
        incident_end=_d(r0.get("incidentEndDate")),
        declared=_d(r0["declarationDate"]),
        designated_areas=areas,
        ia_areas=ia,
        provenance=Provenance(
            source="OpenFEMA DisasterDeclarationsSummaries v2",
            source_url=retrieved_url,
            license="US Government work; FEMA OpenFEMA terms (no endorsement)",
            crs="n/a", horizontal_datum="n/a",
        ),
    )


def fetch_declaration(number: int, *, max_age_s: float = 7 * 86400) -> Declaration:
    cache = DiskCache("openfema")
    key = f"dr_{number}"
    rows = cache.get(key, max_age_s=max_age_s)
    url = f"{OPENFEMA}?$filter=disasterNumber eq {number}"
    if rows is None:
        try:
            data = http_json(OPENFEMA, params={"$filter": f"disasterNumber eq {number}", "$top": 1000})
            rows = data.get("DisasterDeclarationsSummaries")
            if not isinstance(rows, list):
                raise SchemaError("OpenFEMA response has no DisasterDeclarationsSummaries list")
            cache.put(key, rows)
        except Exception:
            rows = cache.get(key)  # any age beats nothing - but say so
            if rows is None:
                raise
            print(f"[events] OpenFEMA unreachable; using cached DR-{number} (stale)")
    return parse_declaration(rows, url)


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
def _config_path() -> str:
    return os.environ.get("NCR_EVENTS_CONFIG") or os.path.join(CONFIG_DIR, "events.yaml")


def build_event(eid: str, spec: dict[str, Any], declarations: list[Declaration]) -> Event:
    begin = min(d.incident_begin for d in declarations)
    pre_lo, pre_hi = spec["windows"]["pre_days"]
    post_lo, post_hi = spec["windows"]["post_days"]
    ev = Event(
        id=eid,
        name=spec["name"],
        state=spec.get("state", "NC"),
        hazards=tuple(spec.get("hazards", [])),
        declarations=tuple(declarations),
        pre=Window(begin + timedelta(days=pre_lo), begin + timedelta(days=pre_hi)),
        post=Window(begin + timedelta(days=post_lo), begin + timedelta(days=post_hi)),
        maxar_event=spec.get("maxar_event"),
    )
    seen: dict[str, str] = {}
    for aid, a in (spec.get("aois") or {}).items():
        role = str(a["role"]).upper()
        if role not in ROLES:
            raise ValueError(f"{eid}/{aid}: role must be TUNE or TEST, got {role}")
        if aid in seen:
            raise ValueError(f"{eid}/{aid}: AOI listed twice")
        seen[aid] = role
        ev.aois[aid] = AOI(aid, role, a.get("county", ""), tuple(a["center"]), a.get("status", "active"))
    ev.assert_windows()
    return ev


@lru_cache(maxsize=1)
def load_events(offline_ok: bool = True) -> dict[str, Event]:
    with open(_config_path(), encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    out: dict[str, Event] = {}
    for eid, spec in (cfg.get("events") or {}).items():
        decls = [fetch_declaration(int(n)) for n in spec["disaster_numbers"]]
        out[eid] = build_event(eid, spec, decls)
    return out


def event_for_area(area_id: str) -> tuple[Event, AOI] | None:
    for ev in load_events().values():
        if area_id in ev.aois:
            return ev, ev.aois[area_id]
    return None
