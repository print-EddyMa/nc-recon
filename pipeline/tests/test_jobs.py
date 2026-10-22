"""Assessment jobs: the list survives a restart, and a job can be cancelled."""
import json
import subprocess
import sys
import threading
import time

import pytest

from terratriage.ops import jobs


@pytest.fixture(autouse=True)
def _clean_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("NCR_JOBS_FILE", str(tmp_path / "jobs.json"))
    monkeypatch.setattr(jobs, "_jobs", {})
    monkeypatch.setattr(jobs, "_queue", type(jobs._queue)())
    monkeypatch.setattr(jobs, "_procs", {})
    monkeypatch.setattr(jobs, "delete_area", lambda a: [])


class _Ev:
    post_sources = ("nc_helene_2025",)
    eri_prefix = None
    maxar_event = None


def _job(**kw):
    d = dict(id="j1", area="town_ab12", event="helene-2024-nc", name="Town", lon=-82.2, lat=35.6, half_m=300)
    return jobs.Job(**(d | kw))


def _stub_plan(monkeypatch):
    monkeypatch.setattr(jobs, "choose_post_source", lambda ev, lon, lat: "nc_helene_2025")
    monkeypatch.setattr(jobs, "choose_pre_source", lambda ev, lon, lat: "nc_2020_2023")
    monkeypatch.setattr("terratriage.ops.plan.events.load_events", lambda: {"helene-2024-nc": _Ev()})
    monkeypatch.setattr("terratriage.ops.plan.events.add_ops_area", lambda *a, **k: None)


def test_finished_job_is_persisted_and_restored(monkeypatch, tmp_path):
    _stub_plan(monkeypatch)
    monkeypatch.setattr(jobs, "_run", lambda job, label, args: None)
    j = _job()
    jobs._jobs[j.id] = j
    jobs.run_job(j)
    rows = json.loads((tmp_path / "jobs.json").read_text())
    assert [r["status"] for r in rows] == ["done"] and rows[0]["post_source"] == "nc_helene_2025"

    monkeypatch.setattr(jobs, "_jobs", {})          # "restart"
    assert jobs.restore() == []
    back = jobs.get("j1")
    assert back.status == "done" and back.area == "town_ab12" and back.finished


def test_interrupted_jobs_come_back_lost(tmp_path, monkeypatch):
    jobs._jobs.update({"a": _job(id="a", status="running", step="assessing structures"),
                       "b": _job(id="b", status="queued"),
                       "c": _job(id="c", status="done")})
    jobs._save()
    monkeypatch.setattr(jobs, "_jobs", {})
    assert sorted(jobs.restore()) == ["a", "b"]
    assert jobs.get("a").status == "lost" and "restarted" in jobs.get("a").error
    assert jobs.get("a").step == "assessing structures"     # where it stopped is kept
    assert jobs.get("c").status == "done"
    # the file now says lost too, so a second restart does not resurrect them
    assert {r["id"]: r["status"] for r in json.loads((tmp_path / "jobs.json").read_text())} == {
        "a": "lost", "b": "lost", "c": "done"}


def test_restore_tolerates_a_corrupt_file(tmp_path):
    (tmp_path / "jobs.json").write_text("{not json")
    assert jobs.restore() == [] and jobs.recent() == []


def test_old_finished_jobs_are_trimmed(monkeypatch):
    monkeypatch.setattr(jobs, "KEEP", 3)
    for i in range(6):
        jobs._jobs[f"d{i}"] = _job(id=f"d{i}", status="done", created=float(i))
    jobs._jobs["live"] = _job(id="live", status="running", created=0.5)
    with jobs._lock:
        jobs._trim()
    assert sorted(jobs._jobs) == ["d3", "d4", "d5", "live"]


def test_cancel_queued_job_leaves_the_queue():
    j = _job(status="queued")
    jobs._jobs[j.id] = j
    jobs._queue.append(j.id)
    out = jobs.cancel("j1")
    assert out.status == "cancelled" and out.finished and not jobs._queue
    assert jobs.cancel("nope") is None


def test_cancel_running_job_stops_the_step_and_cleans_up(monkeypatch):
    _stub_plan(monkeypatch)
    deleted = []
    monkeypatch.setattr(jobs, "delete_area", lambda a: deleted.append(a))
    real_popen = subprocess.Popen

    def slow_popen(cmd, **kw):       # stands in for a long `run.py ops-fetch`
        return real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kw)
    monkeypatch.setattr(jobs.subprocess, "Popen", slow_popen)
    j = _job(status="running")
    jobs._jobs[j.id] = j
    t = threading.Thread(target=jobs.run_job, args=(j,))
    t0 = time.time()
    t.start()
    while "j1" not in jobs._procs and time.time() - t0 < 10:
        time.sleep(0.02)
    jobs.cancel("j1")
    t.join(timeout=15)
    assert not t.is_alive() and time.time() - t0 < 20
    assert j.status == "cancelled" and j.error is None and deleted == ["town_ab12"]
    assert j.step == "fetching imagery"


def test_cancel_after_finish_changes_nothing():
    j = _job(status="done")
    jobs._jobs[j.id] = j
    assert jobs.cancel("j1").status == "done"


def test_step_timeout_fails_the_job(monkeypatch):
    _stub_plan(monkeypatch)
    monkeypatch.setattr(jobs, "STEP_TIMEOUT", 0.3)
    real_popen = subprocess.Popen
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda cmd, **kw: real_popen(
        [sys.executable, "-c", "import time; time.sleep(60)"], **kw))
    j = _job(status="running")
    jobs._jobs[j.id] = j
    jobs.run_job(j)
    assert j.status == "failed" and "timed out" in j.error


# --------------------------------------------------------------------------- #
# re-running an existing operational area
# --------------------------------------------------------------------------- #
@pytest.fixture
def ops_area(tmp_path, monkeypatch):
    from terratriage.ops.plan import events as ev

    monkeypatch.setenv("NCR_OPS_REGISTRY", str(tmp_path / "reg.yaml"))
    monkeypatch.setattr(jobs, "DATA_DIR", str(tmp_path))
    ev.add_ops_area("town_ab12", "helene-2024-nc", "Town centre", -82.2, 35.6)
    (tmp_path / "raw" / "town_ab12").mkdir(parents=True)
    monkeypatch.setattr(jobs, "_worker", object())      # nothing actually starts
    return "town_ab12"


def test_reassess_runs_analysis_only_and_keeps_the_area_on_failure(ops_area, monkeypatch):
    j = jobs.submit_reassess(ops_area)
    assert j.kind == "reassess" and j.name == "Town centre" and j.status == "queued"
    calls, deleted = [], []
    monkeypatch.setattr(jobs, "delete_area", lambda a: deleted.append(a))

    def fake_run(job, label, args):
        calls.append((label, args[0]))
        if label == "assessing structures":
            raise RuntimeError("boom")
    monkeypatch.setattr(jobs, "_run", fake_run)
    jobs.run_job(j)
    assert calls == [("assessing structures", "ops-assess")]          # no imagery fetch
    assert j.status == "failed" and deleted == []                     # the old result stays

    calls.clear()
    monkeypatch.setattr(jobs, "_run", lambda job, label, args: calls.append(label))
    j2 = jobs.submit_reassess(ops_area)
    jobs.run_job(j2)
    assert j2.status == "done" and calls == ["assessing structures", "estimating people", "writing brief"]


def test_reassess_refusals(ops_area, tmp_path):
    with pytest.raises(LookupError):
        jobs.submit_reassess("nowhere_0000")
    with pytest.raises(PermissionError, match="TUNE"):
        jobs.submit_reassess("old_fort")                # evaluation areas: command line only
    jobs.submit_reassess(ops_area)
    with pytest.raises(ValueError, match="already"):
        jobs.submit_reassess(ops_area)                  # one at a time per area
    jobs._jobs.clear()
    (tmp_path / "raw" / "town_ab12").rmdir()
    with pytest.raises(ValueError, match="imagery"):
        jobs.submit_reassess(ops_area)
