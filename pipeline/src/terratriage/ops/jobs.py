"""Operational assessment jobs: POST /ops/assess -> fetch -> assess -> impact -> brief.

One job runs at a time (the CNN and co-registration are CPU-heavy on a laptop
or small server); others wait in a FIFO queue. Each step runs as a subprocess
of `scripts/run.py` with a timeout, so a hung upstream cannot wedge the server,
and its log tail is kept for the UI.

Post-event imagery is chosen automatically from the event's `post_sources`
(config / ops registry), first one that covers the point:
  nc_helene_2025  NC OneMap post-Helene orthos (leaf-off, same program as pre)
  eri             NOAA NGS Emergency Response Imagery for the event
  maxar           Maxar Open Data event (satellite)
"""
from __future__ import annotations

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

from . import PIPELINE_ROOT

RUN = os.path.join(PIPELINE_ROOT, "scripts", "run.py")
STEP_TIMEOUT = int(os.environ.get("NCR_STEP_TIMEOUT_S", "1800"))
MAX_QUEUE = 5


@dataclass
class Job:
    id: str
    area: str
    event: str
    name: str
    lon: float
    lat: float
    half_m: float
    status: str = "queued"          # queued | running | done | failed
    step: str = ""
    post_source: str | None = None
    error: str | None = None
    log: deque = field(default_factory=lambda: deque(maxlen=40))
    created: float = field(default_factory=time.time)
    finished: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["log"] = list(self.log)[-15:]
        return d


_lock = threading.Lock()
_jobs: dict[str, Job] = {}
_queue: deque[str] = deque()
_worker: threading.Thread | None = None


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


def _run(job: Job, label: str, args: list[str]) -> None:
    job.step = label
    job.log.append(f"== {label}")
    p = subprocess.run([sys.executable, RUN, *args], cwd=PIPELINE_ROOT, capture_output=True,
                       text=True, timeout=STEP_TIMEOUT)
    for line in (p.stdout + p.stderr).splitlines()[-12:]:
        job.log.append(line[:300])
    if p.returncode != 0:
        tail = (p.stderr or p.stdout).strip().splitlines()[-1:] or ["failed"]
        raise RuntimeError(f"{label} failed: {tail[0][:300]}")


def _execute(job: Job) -> None:
    from .plan.events import add_ops_area, load_events

    ev = load_events()[job.event]
    job.step = "choosing imagery"
    src = choose_post_source(ev, job.lon, job.lat)
    job.post_source = src
    job.log.append(f"post-event imagery: {src}")
    add_ops_area(job.area, job.event, job.name, job.lon, job.lat)
    if src == "maxar":
        _run(job, "fetching imagery", ["fetch", "--event", ev.maxar_event, "--area", job.area,
                                        "--lat", str(job.lat), "--lon", str(job.lon),
                                        "--event-date", ev.incident_begin.isoformat(), "--name", job.name])
    else:
        args = ["ops-fetch", "--area", job.area, "--lon", str(job.lon), "--lat", str(job.lat),
                "--half-m", str(job.half_m), "--post", src]
        if src == "eri":
            args += ["--eri-prefix", ev.eri_prefix]
        _run(job, "fetching imagery", args)
    _run(job, "assessing structures", ["ops-assess", "--area", job.area])
    _run(job, "estimating people", ["ops-impact", "--area", job.area])
    _run(job, "writing brief", ["ops-brief", "--area", job.area])


def _loop() -> None:
    global _worker
    while True:
        with _lock:
            if not _queue:
                _worker = None
                return
            job = _jobs[_queue.popleft()]
            job.status = "running"
        try:
            _execute(job)
            job.status, job.step = "done", "done"
        except Exception as ex:  # noqa: BLE001
            job.status, job.error = "failed", str(ex)[:500]
            job.log.append(f"FAILED: {job.error}")
            # never leave a half-finished assessment looking like a real one
            try:
                delete_area(job.area)
            except Exception as ex2:  # noqa: BLE001
                job.log.append(f"cleanup failed: {ex2}")
        job.finished = time.time()


def delete_area(area: str) -> list[str]:
    """Remove an OPS area's outputs, imagery and registry entry. Labels are
    kept (they are truth, and cheap) - they just stop matching anything."""
    import shutil

    from .plan.events import event_for_area, remove_ops_area

    found = event_for_area(area)
    if found and found[1].role != "OPS":
        raise PermissionError(f"{area} is a {found[1].role} area; edit config/events.yaml instead")
    from . import DATA_DIR

    data = DATA_DIR
    out = os.path.join(data, "output", "ops")
    removed = []
    for p in (os.path.join(out, f"{area}.geojson"), os.path.join(out, f"{area}.responder.json"),
              os.path.join(out, f"{area}.impact.json")):
        if os.path.exists(p):
            os.remove(p)
            removed.append(os.path.basename(p))
    for d in (os.path.join(out, "exports", area), os.path.join(data, "raw", area)):
        if os.path.realpath(d).startswith(os.path.realpath(data) + os.sep) and os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            removed.append(os.path.relpath(d, data))
    if remove_ops_area(area):
        removed.append("registry entry")
    return removed


def submit(event: str, name: str, lon: float, lat: float, half_m: float = 800.0) -> Job:
    from .geodesy import assert_lonlat_in_nc
    from .plan.events import load_events

    global _worker
    assert_lonlat_in_nc(lon, lat)
    if event not in load_events():
        raise ValueError(f"unknown event {event}")
    if not 200 <= half_m <= 1500:
        raise ValueError("half_m must be 200-1500 m")
    area = f"{slug(name)}_{uuid.uuid4().hex[:4]}"
    job = Job(id=uuid.uuid4().hex[:12], area=area, event=event, name=name.strip()[:60],
              lon=lon, lat=lat, half_m=half_m)
    with _lock:
        active = sum(1 for j in _jobs.values() if j.status in ("queued", "running"))
        if active >= MAX_QUEUE:
            raise OverflowError("assessment queue is full; try again when a job finishes")
        _jobs[job.id] = job
        _queue.append(job.id)
        if _worker is None:
            _worker = threading.Thread(target=_loop, daemon=True, name="ops-jobs")
            _worker.start()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def recent(n: int = 20) -> list[Job]:
    return sorted(_jobs.values(), key=lambda j: -j.created)[:n]
