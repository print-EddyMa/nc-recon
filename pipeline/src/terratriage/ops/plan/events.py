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
from typing import Any

import yaml

from .. import CONFIG_DIR
from ..collect.base import DiskCache, SchemaError, http_json
from ..provenance import Provenance

OPENFEMA = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"
ROLES = ("TUNE", "TEST", "OPS")  # OPS = operational area, never used for evaluation


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
    manual_begin: date | None = None       # provisional event, no declaration yet
    eri_prefix: str | None = None          # NOAA ERI folder for this event
    post_sources: tuple[str, ...] = ("eri", "maxar")
    provisional: bool = False

    @property
    def incident_begin(self) -> date:
        if self.declarations:
            return min(d.incident_begin for d in self.declarations)
        if self.manual_begin is None:
            raise WindowError(f"{self.id}: no declaration and no manual incident_begin")
        return self.manual_begin

    def to_summary(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "state": self.state,
                "declarations": [d.fema_id for d in self.declarations],
                "incident_begin": self.incident_begin.isoformat(), "provisional": self.provisional,
                "pre_window": [self.pre.start.isoformat(), self.pre.end.isoformat()],
                "post_window": [self.post.start.isoformat(), self.post.end.isoformat()],
                "post_sources": list(self.post_sources),
                "aois": [{"id": a.id, "role": a.role, "county": a.county, "center": list(a.center)}
                         for a in self.aois.values()]}

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
    if declarations:
        begin = min(d.incident_begin for d in declarations)
    elif spec.get("incident_begin"):
        begin = date.fromisoformat(str(spec["incident_begin"]))
    else:
        raise ValueError(f"{eid}: needs disaster_numbers or a provisional incident_begin")
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
        manual_begin=None if declarations else begin,
        eri_prefix=spec.get("eri_prefix"),
        post_sources=tuple(spec.get("post_sources") or ("eri", "maxar")),
        provisional=not declarations,
    )
    seen: dict[str, str] = {}
    for aid, a in (spec.get("aois") or {}).items():
        role = str(a["role"]).upper()
        if role not in ROLES:
            raise ValueError(f"{eid}/{aid}: role must be one of {ROLES}, got {role}")
        if aid in seen:
            raise ValueError(f"{eid}/{aid}: AOI listed twice")
        seen[aid] = role
        ev.aois[aid] = AOI(aid, role, a.get("county", ""), tuple(a["center"]), a.get("status", "active"))
    ev.assert_windows()
    return ev


def registry_path() -> str:
    """Writable registry of operational events + areas (lives in the data volume;
    config/events.yaml is baked into the image and holds TUNE/TEST areas)."""
    from .. import DATA_DIR

    return os.environ.get("NCR_OPS_REGISTRY") or os.path.join(DATA_DIR, "ops_registry.yaml")


def _read_yaml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


_CACHE: dict[str, Any] = {"key": None, "events": None}


def load_events(offline_ok: bool = True) -> dict[str, Event]:
    """Config events merged with the operational registry. Re-read whenever
    either file changes (the server adds areas at runtime)."""
    paths = [_config_path(), registry_path()]
    key = tuple((p, os.path.getmtime(p)) if os.path.exists(p) else (p, None) for p in paths)
    if _CACHE["key"] == key and _CACHE["events"] is not None:
        return _CACHE["events"]
    cfg = _read_yaml(paths[0])
    reg = _read_yaml(paths[1])
    specs: dict[str, dict] = {k: dict(v) for k, v in (cfg.get("events") or {}).items()}
    for eid, spec in (reg.get("events") or {}).items():
        if eid in specs:
            raise ValueError(f"event {eid} is defined in both config and the ops registry")
        specs[eid] = dict(spec)
    for aid, a in (reg.get("aois") or {}).items():
        ev = specs.get(a.get("event"))
        if ev is None:
            continue
        ev.setdefault("aois", {})
        ev["aois"] = dict(ev["aois"] or {})
        if aid in ev["aois"]:
            raise ValueError(f"area {aid} is defined in both config and the ops registry")
        ev["aois"][aid] = {**a, "role": "OPS"}
    out: dict[str, Event] = {}
    for eid, spec in specs.items():
        decls = [fetch_declaration(int(n)) for n in (spec.get("disaster_numbers") or [])]
        out[eid] = build_event(eid, spec, decls)
    _CACHE.update(key=key, events=out)
    return out


def add_ops_area(area_id: str, event_id: str, name: str, lon: float, lat: float, county: str = "") -> AOI:
    """Register an operational area (role OPS) in the writable registry."""
    import fcntl
    from datetime import datetime, timezone

    evs = load_events()
    if event_id not in evs:
        raise ValueError(f"unknown event {event_id}")
    for ev in evs.values():
        if area_id in ev.aois:
            raise ValueError(f"area id {area_id} already exists")
    path = registry_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        reg = _read_yaml(path)
        reg.setdefault("aois", {})[area_id] = {
            "event": event_id, "name": name, "county": county, "center": [lon, lat],
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.safe_dump(reg, fh, sort_keys=False)
        os.replace(tmp, path)
    return load_events()[event_id].aois[area_id]


def add_provisional_event(event_id: str, name: str, incident_begin: str, *, state: str = "NC",
                          hazards: list[str] | None = None, eri_prefix: str | None = None,
                          post_sources: list[str] | None = None, pre_days=(-1500, -1),
                          post_days=(0, 120), disaster_numbers: list[int] | None = None) -> Event:
    """T-72 h step: register an event before (or after) its declaration."""
    import fcntl

    path = registry_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        reg = _read_yaml(path)
        if event_id in (reg.get("events") or {}) or event_id in (_read_yaml(_config_path()).get("events") or {}):
            raise ValueError(f"event {event_id} already exists")
        spec: dict[str, Any] = {"name": name, "state": state, "hazards": hazards or [],
                                "windows": {"pre_days": list(pre_days), "post_days": list(post_days)},
                                "post_sources": post_sources or ["eri", "maxar"]}
        if disaster_numbers:
            spec["disaster_numbers"] = [int(n) for n in disaster_numbers]
        else:
            spec["incident_begin"] = incident_begin
        if eri_prefix:
            spec["eri_prefix"] = eri_prefix
        build_event(event_id, spec, [fetch_declaration(int(n)) for n in (disaster_numbers or [])])
        reg.setdefault("events", {})[event_id] = spec
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.safe_dump(reg, fh, sort_keys=False)
        os.replace(tmp, path)
    return load_events()[event_id]


def event_for_area(area_id: str) -> tuple[Event, AOI] | None:
    for ev in load_events().values():
        if area_id in ev.aois:
            return ev, ev.aois[area_id]
    return None
