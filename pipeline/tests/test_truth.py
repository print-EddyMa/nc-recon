"""Groma Verify: task selection, blind judgments, consensus, release,
dataset and hold-out isolation (terratriage.ops.truth)."""
import csv
import io
import json
import os
import zipfile

import pytest

from terratriage.ops import truth

IDS = [f"00000000-0000-0000-0000-{i:012d}" for i in range(8)]
# real ncr_ids are unique per structure; give the held-out area its own
HOLD = [f"11111111-0000-0000-0000-{i:012d}" for i in range(8)]


def _feat(i, probs, people=2, ids=IDS):
    ring = [[-82.4 + i * 1e-3, 35.6], [-82.4 + i * 1e-3 + 1e-4, 35.6], [-82.4 + i * 1e-3 + 1e-4, 35.6001],
            [-82.4 + i * 1e-3, 35.6001], [-82.4 + i * 1e-3, 35.6]]
    lvl = max(probs, key=probs.get)
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"ncr_id": ids[i], "damage_level": lvl, "damage_probs": probs,
                           "occupants": {"nsi_estimate": people}}}


def _area(path, name, role, imagery_licence="public", ids=IDS):
    feats = [
        _feat(0, {"no_damage": 0.2, "affected": 0.2, "minor": 0.2, "major": 0.2, "destroyed": 0.2}, 4, ids),  # most uncertain
        _feat(1, {"no_damage": 0.97, "affected": 0.03}, 2, ids),                                              # sure: low value
        _feat(2, {"major": 0.5, "destroyed": 0.5}, 3, ids),
        _feat(3, {"minor": 0.6, "major": 0.4}, 2, ids),
    ]
    fc = {"type": "FeatureCollection", "features": feats,
          "properties": {"run_id": "t", "aoi": {"id": name, "role": role}, "event": {"id": "ev"},
                         "provenance": {"imagery": [
                             {"role": "pre", "source": "NC OneMap", "license": "public", "date_label": "2023"},
                             {"role": "post", "source": "post source", "license": imagery_licence, "date_label": "2025"}]}}}
    (path / f"{name}.geojson").write_text(json.dumps(fc))


@pytest.fixture
def ops(tmp_path, monkeypatch):
    out = tmp_path / "ops"
    out.mkdir()
    monkeypatch.setattr(truth, "ops_out", lambda: str(out))
    monkeypatch.setenv("NCR_TRUTH_DIR", str(tmp_path / "truth"))
    monkeypatch.setenv("NCR_LABELS_DIR", str(tmp_path / "labels"))
    _area(out, "dev", "TUNE")
    _area(out, "hold", "TEST", ids=HOLD)
    _area(out, "mx", "TUNE", imagery_licence="CC BY-NC 4.0 (Maxar Open Data)",
          ids=[f"22222222-0000-0000-0000-{i:012d}" for i in range(8)])
    return tmp_path


def test_value_of_information_orders_tasks(ops):
    order = [c["ncr_id"] for c in truth.candidates("dev")]
    assert order[0] == IDS[0] and order[-1] == IDS[1]          # most uncertain first, near-certain last
    assert truth.candidates("dev") == truth.candidates("dev")  # deterministic


def test_tasks_are_blind_and_finish_in_progress_first(ops):
    t = truth.next_task("dev", "ana")
    assert t["ncr_id"] == IDS[0]
    assert not {"damage_level", "damage_probs", "needs_review", "confidence"} & set(t)
    truth.submit("dev", IDS[0], "major", "ana")
    assert truth.next_task("dev", "ana")["ncr_id"] != IDS[0]   # never the same building twice
    assert truth.next_task("dev", "ben")["ncr_id"] == IDS[0]   # finish in-progress buildings first
    with pytest.raises(PermissionError):
        truth.submit("dev", IDS[0], "minor", "ana")
    with pytest.raises(ValueError):
        truth.submit("dev", IDS[0], "moderate", "ben")


def test_consensus_rules(ops):
    # two agree: verified
    truth.submit("dev", IDS[0], "major", "ana")
    truth.submit("dev", IDS[0], "major", "ben")
    assert truth.consensus("dev")[IDS[0]]["status"] == "verified"
    # three disagree: escalated, then an analyst settles it
    for w, lab in (("ana", "minor"), ("ben", "major"), ("cy", "affected")):
        truth.submit("dev", IDS[2], lab, w)
    assert truth.consensus("dev")[IDS[2]]["status"] == "escalated"
    assert truth.next_task("dev", "dee", role="analyst")["ncr_id"] == IDS[2]
    truth.submit("dev", IDS[2], "major", "dee", role="analyst")
    d = truth.consensus("dev")[IDS[2]]
    assert d["status"] == "verified" and d["by"] == "adjudicated" and d["label"] == "major"
    # mostly cannot tell: unverifiable, and no longer offered
    truth.submit("dev", IDS[3], "cannot_tell", "ana")
    truth.submit("dev", IDS[3], "cannot_tell", "ben")
    assert truth.consensus("dev")[IDS[3]]["status"] == "unverifiable"
    assert truth.next_task("dev", "zed")["ncr_id"] not in (IDS[0], IDS[2], IDS[3])


def test_analyst_only_settles_escalations(ops):
    assert truth.next_task("dev", "dee", role="analyst") is None   # nothing escalated yet
    truth.submit("dev", IDS[0], "major", "dee", role="analyst")     # an analyst on a fresh building
    assert truth.consensus("dev")[IDS[0]]["status"] == "open"       # is one vote, not a label


def test_reliability_rewards_agreement(ops):
    for i in (0, 2, 3):
        truth.submit("dev", IDS[i], "major", "ana")
        truth.submit("dev", IDS[i], "major", "ben")
        truth.submit("dev", IDS[i], "no_damage", "odd")
    rel = truth.reliabilities(truth.load_judgments())
    assert rel["ana"]["reliability"] > rel["odd"]["reliability"]
    assert rel["odd"]["scored"] == 3 and rel["odd"]["agreed"] == 0


def test_release_is_explicit_idempotent_and_role_tagged(ops):
    truth.submit("dev", IDS[0], "major", "ana")
    truth.submit("dev", IDS[0], "major", "ben")
    labels = ops / "labels" / "dev.csv"
    assert not labels.exists()                                  # judging alone never writes labels
    r = truth.release("dev")
    assert r["released_now"] == 1 and r["aoi_role"] == "TUNE"
    assert truth.release("dev")["released_now"] == 0          # idempotent
    rows = list(csv.DictReader(open(labels, encoding="utf-8")))
    assert rows == [{**rows[0], "ncr_id": IDS[0], "label": "major", "labeler": "consensus", "aoi_role": "TUNE"}]
    assert truth.next_task("dev", "cy")["ncr_id"] != IDS[0]   # released buildings leave the queue


def test_test_labels_never_reach_calibration(ops, monkeypatch):
    from terratriage.ops.analyze import evaluate

    for w in ("ana", "ben"):
        truth.submit("hold", HOLD[0], "destroyed", w)
    assert truth.release("hold")["used_for"] == "held-out evaluation only"
    monkeypatch.setattr(evaluate, "LABELS", str(ops / "labels"))
    monkeypatch.setattr(evaluate, "OPS_OUT", str(ops / "ops"))
    roles = {"hold": "TEST", "dev": "TUNE", "mx": "TUNE"}

    class _A:
        def __init__(self, role):
            self.role = role

    monkeypatch.setattr(evaluate, "event_for_area", lambda a: (None, _A(roles[a])) if a in roles else None)
    with pytest.raises(SystemExit, match="only 0 TUNE labels"):
        evaluate.calibrate()
    for w in ("ana", "ben"):
        truth.submit("dev", IDS[0], "major", w)
    truth.release("dev")
    with pytest.raises(SystemExit, match="only 1 TUNE labels"):
        evaluate.calibrate()


def test_dataset_carries_split_and_licence(ops):
    first = {"dev": IDS[0], "hold": HOLD[0], "mx": "22222222-0000-0000-0000-000000000000"}
    for area in ("dev", "hold", "mx"):
        for w in ("ana", "ben"):
            truth.submit(area, first[area], "major", w)
    data, sheet = truth.export()
    z = zipfile.ZipFile(io.BytesIO(data))
    recs = [json.loads(line) for line in z.read("labels.jsonl").decode().splitlines()]
    by = {r["area"]: r for r in recs}
    assert by["dev"]["split"] == "development" and by["hold"]["split"] == "held_out"
    assert by["dev"]["commercial_use"] is True and by["mx"]["commercial_use"] is False
    assert sheet["records"] == 3 and sheet["commercial_use_records"] == 2
    assert "geometry" in by["dev"] and json.loads(z.read("datasheet.json"))["method"]


def test_metrics(ops):
    truth.submit("dev", IDS[0], "major", "ana", seconds=12)
    truth.submit("dev", IDS[0], "major", "ben", seconds=8)
    m = truth.metrics()
    assert m["verified_structures"] == 1 and m["judgments"] == 2
    assert m["verified_per_human_minute"] == pytest.approx(3.0)
    s = truth.area_status("dev")
    assert s["verified"] == 1 and s["verifiers"] == 2 and s["median_seconds_per_judgment"] in (8, 12)


def test_api_requires_token_and_round_trips(ops, monkeypatch):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import server
    import terratriage.ops.api as api
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api, "OPS_OUT", str(ops / "ops"))
    c = TestClient(server.app)
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    t = c.get("/ops/truth/next", params={"area": "dev", "worker": "ana"}).json()
    assert t["ncr_id"] == IDS[0] and "damage_probs" not in t
    r = c.post("/ops/truth/judgments", json={"area": "dev", "ncr_id": IDS[0], "label": "major", "worker": "ana"})
    assert r.status_code == 200
    assert c.post("/ops/truth/judgments", json={"area": "dev", "ncr_id": IDS[0], "label": "major",
                                                "worker": "ana"}).status_code == 409
    assert c.get("/ops/truth/areas/dev").json()["judgments"] == 1
    assert c.get("/ops/truth/export.zip").status_code == 200
    monkeypatch.delenv("NCR_DEV_OPEN")
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret")
    assert c.get("/ops/truth/next", params={"area": "dev", "worker": "ana"}).status_code == 401
