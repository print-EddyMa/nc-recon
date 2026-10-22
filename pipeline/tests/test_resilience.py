"""A secondary-source outage during an event must never cost the primary output."""
import json
import os

import pytest

from terratriage.ops import jobs
from terratriage.ops.collect.base import SourceUnavailable


class _Ev:
    post_sources = ("nc_helene_2025",)
    eri_prefix = None
    maxar_event = None


def _job():
    return jobs.Job(id="t", area="town_ab12", event="helene-2024-nc", name="Town", lon=-82.2, lat=35.6, half_m=300)


def test_secondary_step_failure_keeps_assessment(monkeypatch):
    calls, deleted = [], []
    monkeypatch.setattr(jobs, "choose_post_source", lambda ev, lon, lat: "nc_helene_2025")
    monkeypatch.setattr("terratriage.ops.plan.events.load_events", lambda: {"helene-2024-nc": _Ev()})
    monkeypatch.setattr("terratriage.ops.plan.events.add_ops_area", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "delete_area", lambda a: deleted.append(a))

    def fake_run(job, label, args):
        calls.append(label)
        if label == "estimating people":
            raise RuntimeError("CDC SVI unreachable")
    monkeypatch.setattr(jobs, "_run", fake_run)
    j = _job()
    jobs.run_job(j)
    assert j.status == "done" and not deleted
    assert any("estimating people" in w for w in j.warnings)
    assert "writing brief" in calls


def test_assess_failure_fails_and_cleans(monkeypatch):
    deleted = []
    monkeypatch.setattr(jobs, "choose_post_source", lambda ev, lon, lat: "nc_helene_2025")
    monkeypatch.setattr("terratriage.ops.plan.events.load_events", lambda: {"helene-2024-nc": _Ev()})
    monkeypatch.setattr("terratriage.ops.plan.events.add_ops_area", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "delete_area", lambda a: deleted.append(a))

    def fake_run(job, label, args):
        if label == "assessing structures":
            raise RuntimeError("boom")
    monkeypatch.setattr(jobs, "_run", fake_run)
    j = _job()
    jobs.run_job(j)
    assert j.status == "failed" and deleted == ["town_ab12"]


@pytest.mark.skipif(not os.path.exists(os.path.join(os.path.dirname(__file__), "..", "data", "output", "ops",
                                                    "chimney_rock.geojson")), reason="needs a local ops output")
def test_impact_survives_svi_outage(monkeypatch, tmp_path):
    from terratriage.ops.analyze import impact

    def down(bbox):
        raise SourceUnavailable("services3.arcgis.com unreachable")
    monkeypatch.setattr(impact, "svi_tracts", down)
    src = os.path.join(impact.OPS_OUT, "chimney_rock.geojson")
    monkeypatch.setattr(impact, "OPS_OUT", str(tmp_path))
    (tmp_path / "chimney_rock.geojson").write_text(open(src).read())
    out = impact.run("chimney_rock", n_mc=50)
    assert out["svi_status"].startswith("unavailable")
    assert out["expected_displaced"]["median"] >= 0
    assert all(t["need_index"] is None for t in out["tracts"])


def test_openfema_outage_on_fresh_volume_uses_seed(monkeypatch, tmp_path):
    from terratriage.ops.plan import events as ev

    monkeypatch.setattr("terratriage.ops.collect.base.OPS_CACHE", str(tmp_path))
    def down(*a, **k):
        raise SourceUnavailable("www.fema.gov unreachable")
    monkeypatch.setattr(ev, "http_json", down)
    d = ev.fetch_declaration(4827, max_age_s=0)
    assert d.fema_id == "DR-4827-NC" and d.incident_begin.isoformat() == "2024-09-25"


def test_audit_log_records_responder_actions(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from fastapi.testclient import TestClient

    import server
    from terratriage.ops import audit
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    monkeypatch.setattr(audit, "PATH", str(tmp_path / "audit.log"))
    c = TestClient(server.app)
    if c.get("/ops/areas/chimney_rock").status_code != 200:
        pytest.skip("needs a local ops output")
    c.get("/ops/areas/chimney_rock/brief.html", headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"})
    rows = [json.loads(l) for l in (tmp_path / "audit.log").read_text().splitlines()]
    assert [r["action"] for r in rows] == ["view_area", "brief"]
    assert rows[1]["client"] == "203.0.113.7"


def test_public_impact_is_suppressed(monkeypatch):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from fastapi.testclient import TestClient

    import server
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret")
    c = TestClient(server.app)
    r = c.get("/ops/areas/marshall/impact")
    if r.status_code != 200:
        pytest.skip("needs a local impact output")
    for t in r.json()["tracts"]:
        assert t.get("suppressed") or (t["structures"] or 0) >= 5
    full = c.get("/ops/areas/marshall/impact", headers={"Authorization": "Bearer s3cret"}).json()
    assert not any(t.get("suppressed") for t in full["tracts"])


def test_importing_the_server_touches_no_live_state(monkeypatch):
    """Recovery (mark lost jobs, prune half-registered areas) belongs to server
    start-up. Importing the module, as every test and script does, must not run
    it: it once deleted the imagery of an assessment another process was running."""
    import importlib
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    called = []
    monkeypatch.setattr(jobs, "prune_orphans", lambda: called.append("prune") or [])
    monkeypatch.setattr(jobs, "restore", lambda: called.append("restore") or [])
    import server
    importlib.reload(server)
    assert called == []
    from fastapi.testclient import TestClient
    with TestClient(server.app):            # start-up runs the recovery, once
        assert called == ["restore", "prune"]


def test_test_run_does_not_use_the_live_registry():
    from terratriage.ops import DATA_DIR, audit
    from terratriage.ops.plan.events import registry_path
    assert not registry_path().startswith(DATA_DIR)
    assert not jobs.store_path().startswith(DATA_DIR)
    assert not audit.PATH.startswith(DATA_DIR)


def test_job_errors_carry_no_terminal_escape_codes(monkeypatch, tmp_path):
    import subprocess
    import sys
    monkeypatch.setenv("NCR_JOBS_FILE", str(tmp_path / "jobs.json"))
    real = subprocess.Popen
    code = "import sys; sys.stderr.write('\\x1b[1;35mRasterioIOError\\x1b[0m: \\x1b[35mRead failed\\x1b[0m\\n'); sys.exit(1)"
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda cmd, **kw: real([sys.executable, "-c", code], **kw))
    j = _job()
    with pytest.raises(RuntimeError) as ex:
        jobs._run(j, "assessing structures", ["ops-assess"])
    assert str(ex.value) == "assessing structures failed: RasterioIOError: Read failed"
    assert not any("\x1b" in line for line in j.log)
