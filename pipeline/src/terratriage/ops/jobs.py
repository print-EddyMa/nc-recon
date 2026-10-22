"""Operational assessment jobs: POST /ops/assess -> fetch -> assess -> impact -> brief.

One job runs at a time (the CNN and co-registration are CPU-heavy on a laptop
or small server); others wait in a FIFO queue. Each step runs as a subprocess
of `scripts/run.py` with a timeout, so a hung upstream cannot wedge the server,
and its log tail is kept for the UI.

Pre-event imagery is the NC Orthoimagery Program inside North Carolina and
USDA NAIP elsewhere, whichever covers the point and was flown before the
incident (`choose_pre_source`).

Post-event imagery is chosen automatically from the event's `post_sources`
(config / ops registry), first one that covers the point:
  nc_helene_2025  NC OneMap post-Helene orthos (leaf-off, same program as pre)
  eri             NOAA NGS Emergency Response Imagery for the event
  maxar           Maxar Open Data event (satellite)

Job records are written to data/jobs.json on every state change, so the list
survives a restart. The work itself does not: a job that was queued or running
when the server stopped comes back as "lost", and its half-registered area is
pruned (`prune_orphans`).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from . import DATA_DIR, PIPELINE_ROOT, RAW_DIR

RUN = os.path.join(PIPELINE_ROOT, "scripts", "run.py")
STEP_TIMEOUT = int(os.environ.get("NCR_STEP_TIMEOUT_S", "1800"))
MAX_QUEUE = 5
KEEP = 50                       # finished job records kept on disk
ACTIVE = ("queued", "running")
LOST_MSG = "The server restarted while this assessment was running. Run it again."


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class Cancelled(Exception):
    """Raised inside a job when a responder cancels it."""


def store_path() -> str:
    return os.environ.get("NCR_JOBS_FILE") or os.path.join(DATA_DIR, "jobs.json")


@dataclass
class Job:
    id: str
    area: str
    event: str
    name: str
    lon: float
    lat: float
    half_m: float
    kind: str = "assess"            # assess (new area) | reassess (same imagery, existing area)
    status: str = "queued"          # queued | running | done | failed | cancelled | lost
    step: str = ""
    post_source: str | None = None
    pre_source: str | None = None
    error: str | None = None
    warnings: list = field(default_factory=list)
    log: deque = field(default_factory=lambda: deque(maxlen=40))
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["log"] = list(self.log)[-15:]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Job":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d and k != "log"}
        job = cls(**known)
        job.log.extend(d.get("log") or [])
        return job


_lock = threading.Lock()
_io_lock = threading.Lock()
_jobs: dict[str, Job] = {}
_queue: deque[str] = deque()
_procs: dict[str, subprocess.Popen] = {}
_worker: threading.Thread | None = None


def _save() -> None:
    """Write the job list atomically. Never raises: losing the record of a job
    must not fail the job."""
    path = store_path()
    try:
        with _io_lock:
            rows = [j.to_dict() for j in sorted(_jobs.values(), key=lambda j: j.created)]
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f"{path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(rows, fh)
            os.replace(tmp, path)
    except OSError as ex:
        print(f"[jobs] could not write {path}: {ex}")


def _trim() -> None:
    """Keep every active job and the newest KEEP finished ones (caller holds _lock)."""
    done = sorted((j for j in _jobs.values() if j.status not in ACTIVE), key=lambda j: -j.created)
    for j in done[KEEP:]:
        _jobs.pop(j.id, None)


def restore() -> list[str]:
    """At startup: reload the job list. Anything that was queued or running is
    marked lost, because the worker that owned it is gone. Returns their ids."""
    path = store_path()
    lost: list[str] = []
    try:
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
    except (OSError, ValueError):
        return lost
    with _lock:
        for d in rows if isinstance(rows, list) else []:
            try:
                job = Job.from_dict(d)
            except TypeError:
                continue
            if job.id in _jobs:
                continue
            if job.status in ACTIVE:
                job.status, job.error, job.finished = "lost", LOST_MSG, time.time()
                job.log.append("LOST: server restarted")
                lost.append(job.id)
            _jobs[job.id] = job
        _trim()
    _save()
    return lost


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:30] or "area"
    return s


def choose_post_source(event, lon: float, lat: float) -> str:
    from .collect import nc_orthos
    from .collect.imagery_fetch import eri_covers

    for src in event.post_sources:
        if src in nc_orthos.SERVICES:
            try:
                if nc_orthos.covered(src, lon, lat):
                    return src
            except Exception:  # noqa: BLE001
                continue
        elif src == "eri" and event.eri_prefix:
            if eri_covers(lon, lat, event.eri_prefix):
                return "eri"
        elif src == "maxar" and event.maxar_event:
            try:
                from .. import download

                rows = download.fetch_catalog(event.maxar_event, os.path.join(PIPELINE_ROOT, "data", "cache"))
                download.choose_tile(rows, "probe", lat, lon, event.incident_begin)  # raises if none near
                return "maxar"
            except Exception:  # noqa: BLE001
                continue
    raise LookupError("no post-event imagery covers this point for this event "
                      f"(tried {', '.join(event.post_sources)})")


PRE_SOURCES = ("nc_2020_2023", "naip")


def choose_pre_source(event, lon: float, lat: float) -> str:
    """First pre-event source that covers the point with imagery flown inside
    the event's pre window. NAIP holds only each state's latest collection, so
    a collection flown after the incident is refused, never used as "before"."""
    from datetime import date

    from .collect import nc_orthos

    tried = []
    for src in PRE_SOURCES:
        try:
            if not nc_orthos.covered(src, lon, lat):
                tried.append(f"{src}: no coverage")
                continue
            lo, hi, _how = nc_orthos.tile_dates(src, [(lon, lat)])
        except Exception as ex:  # noqa: BLE001
            tried.append(f"{src}: {str(ex)[:80]}")
            continue
        if all(event.classify_image_date(date.fromisoformat(d)) == "pre" for d in (lo, hi)):
            return src
        tried.append(f"{src}: flown {hi}, outside the pre-event window")
    raise LookupError("no pre-event imagery covers this point before the incident ("
                      + "; ".join(tried) + ")")


def _step(job: Job, label: str) -> None:
    if job.cancel_requested:
        raise Cancelled()
    job.step = label
    job.log.append(f"== {label}")
    _save()


def _run(job: Job, label: str, args: list[str]) -> None:
    _step(job, label)
    # plain output: Python 3.13 colours tracebacks, and the escape codes would
    # end up in the job log and the error an analyst reads
    env = {**os.environ, "NO_COLOR": "1", "PYTHON_COLORS": "0"}
    p = subprocess.Popen([sys.executable, RUN, *args], cwd=PIPELINE_ROOT, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env=env)
    _procs[job.id] = p
    try:
        try:
            out, err = p.communicate(timeout=STEP_TIMEOUT)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            raise RuntimeError(f"{label} timed out after {STEP_TIMEOUT} s") from None
    finally:
        _procs.pop(job.id, None)
    if job.cancel_requested:
        raise Cancelled()
    out, err = _ANSI.sub("", out), _ANSI.sub("", err)
    for line in (out + err).splitlines()[-12:]:
        job.log.append(line[:300])
    if p.returncode != 0:
        tail = (err or out).strip().splitlines()[-1:] or ["failed"]
        raise RuntimeError(f"{label} failed: {tail[0][:300]}")


def _execute(job: Job) -> None:
    from .plan.events import add_ops_area, load_events

    if job.kind == "reassess":
        # the imagery is already on disk and the area registered: only the
        # analysis and what follows from it run again
        _run(job, "assessing structures", ["ops-assess", "--area", job.area])
        _secondary(job)
        return
    ev = load_events()[job.event]
    _step(job, "choosing imagery")
    src = choose_post_source(ev, job.lon, job.lat)
    job.post_source = src
    job.log.append(f"post-event imagery: {src}")
    if job.cancel_requested:
        raise Cancelled()
    if src != "maxar":
        job.pre_source = choose_pre_source(ev, job.lon, job.lat)
        job.log.append(f"pre-event imagery: {job.pre_source}")
        if job.cancel_requested:
            raise Cancelled()
    add_ops_area(job.area, job.event, job.name, job.lon, job.lat)
    if src == "maxar":
        _run(job, "fetching imagery", ["fetch", "--event", ev.maxar_event, "--area", job.area,
                                        "--lat", str(job.lat), "--lon", str(job.lon),
                                        "--event-date", ev.incident_begin.isoformat(), "--name", job.name])
    else:
        args = ["ops-fetch", "--area", job.area, "--lon", str(job.lon), "--lat", str(job.lat),
                "--half-m", str(job.half_m), "--pre", job.pre_source or "nc_2020_2023", "--post", src]
        if src == "eri":
            args += ["--eri-prefix", ev.eri_prefix]
        _run(job, "fetching imagery", args)
    _run(job, "assessing structures", ["ops-assess", "--area", job.area])
    _secondary(job)


def _secondary(job: Job) -> None:
    # the damage assessment is the product; a secondary source being down
    # (CDC SVI, Census, ...) must never throw it away
    for label, args in (("estimating people", ["ops-impact", "--area", job.area]),
                        ("writing brief", ["ops-brief", "--area", job.area])):
        try:
            _run(job, label, args)
        except Cancelled:
            raise
        except Exception as ex:  # noqa: BLE001
            job.warnings.append(f"{label}: {str(ex)[:200]}")
            job.log.append(f"WARNING: {label} failed; assessment kept")


def _loop() -> None:
    global _worker
    while True:
        with _lock:
            if not _queue:
                _worker = None
                return
            job = _jobs[_queue.popleft()]
            job.status, job.started = "running", time.time()
        run_job(job)


def run_job(job: Job) -> None:
    """Run one job to completion. Only a failed fetch or assess fails the job
    (and removes its partial outputs); later steps degrade to warnings."""
    try:
        _execute(job)
        job.status, job.step = "done", "done"
    except Cancelled:
        job.status, job.error = "cancelled", None
        job.log.append("CANCELLED by a responder")
        _cleanup(job)
    except Exception as ex:  # noqa: BLE001
        job.status, job.error = "failed", str(ex)[:500]
        job.log.append(f"FAILED: {job.error}")
        _cleanup(job)
    job.finished = time.time()
    _save()


def _cleanup(job: Job) -> None:
    if job.kind == "reassess":
        # the area existed before this job: its last complete assessment stays
        # (ops-assess only replaces the output once it has finished)
        job.log.append("previous assessment kept")
        return
    # never leave a half-finished assessment looking like a real one
    try:
        delete_area(job.area)
    except Exception as ex:  # noqa: BLE001
        job.log.append(f"cleanup failed: {ex}")


def cancel(job_id: str) -> Job | None:
    """Stop a queued or running job. A queued job just leaves the queue; a
    running one has its current step terminated and its partial outputs
    removed by the worker. Finished jobs are returned unchanged."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if job.status == "queued":
            try:
                _queue.remove(job_id)
            except ValueError:
                pass
            job.status, job.finished = "cancelled", time.time()
            job.log.append("CANCELLED by a responder")
        elif job.status == "running":
            job.cancel_requested = True
            proc = _procs.get(job_id)
            if proc is not None and proc.poll() is None:
                proc.terminate()
    _save()
    return job


def delete_area(area: str) -> list[str]:
    """Remove an OPS area's outputs, imagery and registry entry. Labels are
    kept (they are truth, and cheap) - they just stop matching anything."""
    import shutil

    from .plan.events import event_for_area, remove_ops_area

    found = event_for_area(area)
    if found and found[1].role != "OPS":
        raise PermissionError(f"{area} is a {found[1].role} area; edit config/events.yaml instead")
    from . import DATA_DIR, OPS_OUT

    data = DATA_DIR
    out = OPS_OUT
    removed = []
    for p in (os.path.join(out, f"{area}.geojson"), os.path.join(out, f"{area}.responder.json"),
              os.path.join(out, f"{area}.impact.json")):
        if os.path.exists(p):
            os.remove(p)
            removed.append(os.path.basename(p))
    from . import OPS_CACHE

    for d in (os.path.join(out, "exports", area), os.path.join(RAW_DIR, area),
              os.path.join(OPS_CACHE, "tiles", area)):
        # only ever delete inside the data, output or raw imagery directory
        inside = [r for r in (data, out, RAW_DIR) if os.path.realpath(d).startswith(os.path.realpath(r) + os.sep)]
        if inside and os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            removed.append(os.path.relpath(d, inside[0]))
    if remove_ops_area(area):
        removed.append("registry entry")
    return removed


def submit(event: str, name: str, lon: float, lat: float, half_m: float = 800.0) -> Job:
    from .geodesy import assert_lonlat_in_us
    from .plan.events import load_events

    global _worker
    assert_lonlat_in_us(lon, lat)
    if event not in load_events():
        raise ValueError(f"unknown event {event}")
    if not 200 <= half_m <= 1500:
        raise ValueError("half_m must be 200-1500 m")
    area = f"{slug(name)}_{uuid.uuid4().hex[:4]}"
    job = Job(id=uuid.uuid4().hex[:12], area=area, event=event, name=name.strip()[:60],
              lon=lon, lat=lat, half_m=half_m)
    with _lock:
        active = sum(1 for j in _jobs.values() if j.status in ACTIVE)
        if active >= MAX_QUEUE:
            raise OverflowError("assessment queue is full; try again when a job finishes")
        _jobs[job.id] = job
        _queue.append(job.id)
        _trim()
        if _worker is None:
            _worker = threading.Thread(target=_loop, daemon=True, name="ops-jobs")
            _worker.start()
    _save()
    return job


def submit_reassess(area: str) -> Job:
    """Assess an existing operational area again from the imagery it already
    has: after a calibration, a rule change or a software fix. Labels are
    keyed by structure id and carry over."""
    from .plan.events import area_name, event_for_area

    global _worker
    found = event_for_area(area)
    if not found:
        raise LookupError(f"no such area {area}")
    ev, aoi = found
    if aoi.role != "OPS":
        raise PermissionError(f"{area} is a {aoi.role} area: re-run it from the command line "
                              "(scripts/run.py ops-assess) so evaluation areas change deliberately")
    if not os.path.isdir(os.path.join(RAW_DIR, area)):
        raise ValueError("the imagery for this area is no longer stored; run a new assessment instead")
    lon, lat = aoi.center
    job = Job(id=uuid.uuid4().hex[:12], area=area, event=ev.id, name=area_name(area), lon=lon, lat=lat,
              half_m=0.0, kind="reassess")
    with _lock:
        if any(j.area == area and j.status in ACTIVE for j in _jobs.values()):
            raise ValueError("this area already has an assessment queued or running")
        if sum(1 for j in _jobs.values() if j.status in ACTIVE) >= MAX_QUEUE:
            raise OverflowError("assessment queue is full; try again when a job finishes")
        _jobs[job.id] = job
        _queue.append(job.id)
        _trim()
        if _worker is None:
            _worker = threading.Thread(target=_loop, daemon=True, name="ops-jobs")
            _worker.start()
    _save()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def recent(n: int = 20) -> list[Job]:
    return sorted(_jobs.values(), key=lambda j: -j.created)[:n]


def prune_orphans() -> list[str]:
    """At startup: drop OPS registry entries whose assessment never finished
    (e.g. the server restarted mid-job). Nothing runs at that point."""
    from . import OPS_OUT
    from .plan.events import load_events

    out = OPS_OUT
    removed = []
    try:
        evs = load_events()
    except Exception:  # noqa: BLE001
        return removed
    for ev in evs.values():
        for aid, a in list(ev.aois.items()):
            if a.role == "OPS" and not os.path.exists(os.path.join(out, f"{aid}.geojson")):
                try:
                    delete_area(aid)
                    removed.append(aid)
                except Exception:  # noqa: BLE001
                    pass
    return removed
