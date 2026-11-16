"""Situation brief as a case file (ops/sitbrief.py): evidence, rules writer,
number tracing, and what the optional Claude writer may see. No network."""
import json
from types import SimpleNamespace

import pytest

from terratriage.ops import sitbrief as sb

AREA = "testvale"
ADDRESS = "217 EXAMPLE STREET, TESTVALE, 28778"


def _write(d, name, obj):
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture
def out(tmp_path, monkeypatch):
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [-82.1, 35.6]},
              "properties": {"ncr_id": f"id-{i}", "centroid": [-82.1 + i * 1e-4, 35.6], "damage_level": "major",
                             "cbfips_2010": "370210030021000", "usng_1m": "17S LV 7367 4046"}} for i in range(5)]
    _write(tmp_path, f"{AREA}.geojson", {"type": "FeatureCollection", "features": feats, "properties": {
        "run_id": "testvale-run-1", "generated_utc": "2026-09-26T05:38:03Z",
        "event": {"id": "helene-2024-nc", "name": "Hurricane Helene (NC)", "declarations": ["DR-4827-NC"],
                  "incident_begin": "2024-09-25"},
        "aoi": {"id": AREA, "role": "TUNE", "county": "Buncombe", "name": "Testvale"},
        "counts": {"no_damage": 500, "affected": 150, "minor": 30, "major": 20, "destroyed": 100},
        "expected_counts": {"no_damage": 388.5, "affected": 206.9, "minor": 108.3, "major": 50.0, "destroyed": 69.2},
        "expected_counts_80pct": {"no_damage": [373, 402], "affected": [192, 222], "minor": [98, 120],
                                  "major": [42, 58], "destroyed": [63, 75]},
        "not_assessed": {"total": 70, "residential": 38}, "n_structures": 893, "n_needs_review": 298,
        "calibration": {"cnn": "none"}, "pair_context": {"pair_gap_days": 683, "reasons": [],
                                                         "post_days_after_incident": [98, 248]},
        "warnings": ["CNN uncalibrated (no TUNE labels yet)"], "runtime_sec": 88.3}})
    _write(tmp_path, f"{AREA}.impact.json", {"run_id": "testvale-run-1",
                                            "expected_displaced": {"p10": 130.7, "median": 144.2, "p90": 157.1},
                                            "unassessed_residential": {"structures": 38, "occupants_nsi": 81.0},
                                            "occupancy_adjustment": "UNADJUSTED (no key)",
                                            "tracts": [{"tract": "37021003002", "expected_displaced": 143.9}]})
    _write(tmp_path, f"{AREA}.response.json", {
        "run_id": "testvale-run-1",
        "summary": {"coverage": 0.922, "landing_zone_candidates": 30, "water_systems_at_risk": 1,
                    "private_well_homes": 27, "reading_notes": ["Buildings not assessed are unknown, never undamaged."],
                    "cut_off": {"known_blocks": {"isolated_buildings": 0, "isolated_people_est": 0},
                                "plus_debris": {"isolated_buildings": 74, "isolated_people_est": 113},
                                "worst_case": {"isolated_buildings": 765, "isolated_people_est": 1028}}},
        "access": {"roads": {"blocked": 532, "debris": 44, "bridge": 105},
                   "hospitals": [{"name": "Testvale Hospital", "lon": -82.53, "lat": 35.56}],
                   "isolated_clusters": [{"usng": "17S LV 736 403", "center": [-82.39, 35.59]}]},
        "resources": {"lifelines": [
            {"lifeline": "safety_security", "label": "Safety and security", "status": "green", "disrupted": 0,
             "at_risk": 0, "first_look": []},
            {"lifeline": "communications", "label": "Communications", "status": "yellow", "disrupted": 2,
             "at_risk": 0, "first_look": [{"name": "comms tower", "lon": -82.39, "lat": 35.61}]}]},
        "landing": {"candidates": [{"lon": -82.39, "lat": 35.59, "usng": "17S LV 7367 4046"}]},
        "sectors": [{"usng_1km": "17S LV 73 40", "priority": 1, "buildings": 458,
                     "major_or_destroyed_expected": 64.2, "people_in_severe_expected": 80.0, "needs_review": 150,
                     "center": [-82.396692, 35.600237]},
                    {"usng_1km": "17S LV 72 40", "priority": 2, "buildings": 160,
                     "major_or_destroyed_expected": 30.5, "people_in_severe_expected": 40.7, "needs_review": 60,
                     "center": [-82.404961, 35.601663]}]})
    _write(tmp_path, f"{AREA}.responder.json", {"run_id": "testvale-run-1",
                                               "structures": {"id-0": {"address": ADDRESS}}})
    monkeypatch.setenv("NCR_OPS_OUT", str(tmp_path))
    monkeypatch.delenv("NCR_OFFLINE", raising=False)
    sb._cache.clear()
    yield tmp_path
    sb._cache.clear()


class FakeClient:
    def __init__(self, items=None, exc=None):
        self.calls = []
        self.items, self.exc = items, exc
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                               content=[SimpleNamespace(type="text", text=json.dumps({"items": self.items}))])


def _ids(ev):
    return {e["label"]: e for e in ev}


# --------------------------------------------------------------------------- evidence
def test_evidence_is_numbered_area_level_and_sourced(out):
    ev = sb.evidence(AREA)
    assert [e["id"] for e in ev] == [f"E{i}" for i in range(1, len(ev) + 1)]
    by = _ids(ev)
    assert by["Area"]["value"] == "Testvale (Buncombe Co.)"
    assert by["Structures in the inventory"]["value"] == 893
    assert by["Structures assessed from imagery"]["value"] == 823
    assert by["Expected Destroyed"]["interval"] == [63, 75]
    sev = by["Expected Major or Destroyed (the two levels added)"]
    assert sev["value"] == 119.2 and sev["interval"] == [105, 133]
    assert by["Calls flagged for human review"]["value"] == 298
    assert by["Share of structures assessed"]["value"] == 92.2
    assert by["Road segments mapped as blocked"]["value"] == 532
    assert by["Lifeline: Communications"]["value"] == "Strained"
    assert by["Priority sector 1: expected Major or Destroyed"]["locator"] == "17S LV 73 40"
    for e in ev:
        assert set(e) <= {"id", "label", "value", "unit", "interval", "source", "locator"}
        assert e["source"].startswith(AREA + ".") and not e["source"].endswith("responder.json")
    blob = json.dumps(ev)
    for banned in ("id-0", "centroid", ADDRESS, "Testvale Hospital", "-82.", "35.6", "17S LV 7367", "37021003002"):
        assert banned not in blob


def test_response_from_another_run_is_not_used(out):
    p = out / f"{AREA}.response.json"
    d = json.loads(p.read_text())
    d["run_id"] = "older-run"
    p.write_text(json.dumps(d))
    by = _ids(sb.evidence(AREA))
    assert "Road segments mapped as blocked" not in by
    assert by["Response products"]["value"].startswith("built from an earlier run")


def test_missing_area_raises(out):
    with pytest.raises(FileNotFoundError):
        sb.evidence("nowhere")


# --------------------------------------------------------------------------- rules brief
def test_rule_brief_items_cite_evidence_and_trace_fully(out):
    r = sb.rule_brief(AREA)
    assert r["written_by"] == "rules" and r["model"] is None and r["ai_error"] is None
    assert 4 <= len(r["items"]) <= 6
    assert [i["kind"] for i in r["items"]] == ["headline", "damage", "access", "search", "unknown", "verify"]
    ids = {e["id"] for e in r["evidence"]}
    for it in r["items"]:
        assert it["evidence"] and set(it["evidence"]) <= ids
        assert "—" not in it["text"] and "–" not in it["text"]
    assert r["total"] > 10 and r["traced"] == r["total"] and r["untraced"] == []
    assert sb.SAFETY in r["items"][-1]["text"]
    head = r["items"][0]["text"]
    assert "about 119 of 823 assessed structures are likely Major or Destroyed (range 105 to 133)" in head
    assert "17S LV 73 40" in r["items"][3]["text"]


def test_rule_brief_without_response_products(out):
    (out / f"{AREA}.response.json").unlink()
    r = sb.rule_brief(AREA)
    access = next(i for i in r["items"] if i["kind"] == "access")
    assert "have not been worked out" in access["text"]
    assert r["traced"] == r["total"]


def test_rule_brief_cache_follows_the_files(out):
    a = sb.rule_brief(AREA)
    assert sb.rule_brief(AREA)["items"] == a["items"]
    p = out / f"{AREA}.response.json"
    d = json.loads(p.read_text())
    d["access"]["roads"]["blocked"] = 600
    p.write_text(json.dumps(d))
    import os
    import time

    os.utime(p, (time.time() + 5, time.time() + 5))
    assert "600 road segments" in sb.rule_brief(AREA)["items"][2]["text"]


# --------------------------------------------------------------------------- tracing
def test_trace_catches_a_planted_number():
    ev = [{"id": "E1", "label": "Expected Major", "value": 50.0, "unit": "structures", "interval": [42, 58]},
          {"id": "E2", "label": "Share assessed", "value": 92.2, "unit": "percent"},
          {"id": "E3", "label": "Loss", "value": 9177000.0, "unit": "usd"}]
    ok = sb.trace_numbers(["About 50 Major (range 42 to 58), 92% assessed, $9.2M (E1, E2, E3)."], ev)
    assert ok == {"total": 5, "traced": 5, "untraced": []}
    bad = sb.trace_numbers(["About 50 Major, and 4321 people cut off."], ev)
    assert bad["total"] == 2 and bad["traced"] == 1 and bad["untraced"] == ["4321"]
    # no small-number exemption: an invented count is caught
    assert sb.trace_numbers(["8 sectors"], ev)["untraced"] == ["8"]
    # precision: 119 matches 119.2, 120 does not
    ev2 = [{"id": "E1", "label": "x", "value": 119.2}]
    assert sb.trace_numbers(["119"], ev2)["untraced"] == []
    assert sb.trace_numbers(["120"], ev2)["untraced"] == ["120"]


# --------------------------------------------------------------------------- Claude writer
GOOD = [
    {"kind": "headline", "text": "Testvale: about 119 of 823 assessed structures are likely Major or Destroyed.",
     "evidence": ["E1", "E7", "E15"]},
    {"kind": "damage", "text": "Destroyed 69 (range 63 to 75) and Major 50.", "evidence": ["E10", "E11"]},
    {"kind": "access", "text": "Debris could cut off 4321 buildings.", "evidence": ["E28"]},
    {"kind": "verify", "text": "298 calls are flagged for review.", "evidence": ["E16"]},
]


def test_ai_brief_sends_only_area_level_evidence_and_drops_untraced(out, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    fake = FakeClient(items=GOOD)
    r = sb.ai_brief(AREA, client=fake)
    assert len(fake.calls) == 1
    kw = fake.calls[0]
    assert kw["model"] == sb.MODEL and "betas" not in kw and "fallbacks" not in kw
    assert kw["output_config"]["format"]["type"] == "json_schema"
    sent = json.dumps(kw)
    for banned in ("ncr_id", "id-0", "centroid", "address", ADDRESS, '"lon"', '"lat"', "usng", "17S",
                   "locator", "Testvale Hospital", "-82.", "35.6", "37021003002", "responder", ".geojson"):
        assert banned not in sent, banned
    assert "Expected Major or Destroyed" in sent and "E15" in sent
    assert r["written_by"] == "claude" and r["model"] == "claude-opus-5-5" and r["ai_error"] is None
    kinds = [i["kind"] for i in r["items"]]
    assert "access" not in kinds and kinds[0] == "headline"
    assert r["dropped"][0]["kind"] == "access" and "4321" in r["dropped"][0]["reason"]
    assert r["total"] > r["traced"] and "4321" in r["untraced"]
    assert sb.SAFETY in r["items"][-1]["text"]


def test_ai_brief_is_gated_by_offline_mode_and_key(out, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("NCR_OFFLINE", "1")
    fake = FakeClient(items=GOOD)
    r = sb.ai_brief(AREA, client=fake)
    assert fake.calls == [] and r["written_by"] == "rules" and "offline" in r["ai_error"]
    assert r["ai_available"] is False
    monkeypatch.delenv("NCR_OFFLINE")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    r = sb.ai_brief(AREA, client=fake)
    assert fake.calls == [] and r["written_by"] == "rules" and "ANTHROPIC_API_KEY" in r["ai_error"]


def test_ai_error_falls_back_and_is_not_cached(out, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    bad = FakeClient(exc=RuntimeError("boom with test-key-not-real inside"))
    r = sb.ai_brief(AREA, client=bad)
    assert r["written_by"] == "rules" and r["ai_error"] == "Claude could not write the brief: RuntimeError"
    assert "test-key-not-real" not in json.dumps(r)
    sb.ai_brief(AREA, client=bad)
    assert len(bad.calls) == 2  # a failed run is never cached
    good = FakeClient(items=GOOD)
    sb.ai_brief(AREA, client=good)
    sb.ai_brief(AREA, client=good)
    assert len(good.calls) == 1  # a good run is


def test_ai_all_untraced_falls_back(out, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    fake = FakeClient(items=[{"kind": "headline", "text": "9999 structures destroyed.", "evidence": ["E1"]}])
    r = sb.ai_brief(AREA, client=fake)
    assert r["written_by"] == "rules" and "traced" in r["ai_error"]


# --------------------------------------------------------------------------- route
def test_route_returns_rules_brief(out, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from terratriage.ops.sitbrief_api import router

    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    r = c.get(f"/ops/areas/{AREA}/sitbrief")
    assert r.status_code == 200
    j = r.json()
    for k in ("items", "evidence", "written_by", "model", "traced", "total", "ai_error", "generated_utc",
              "ai_available"):
        assert k in j
    assert j["written_by"] == "rules" and j["ai_available"] is False
    r = c.get(f"/ops/areas/{AREA}/sitbrief?ai=1")
    assert r.status_code == 200 and r.json()["written_by"] == "rules" and r.json()["ai_error"]
    assert c.get("/ops/areas/Bad-Id/sitbrief").status_code == 400
    assert c.get("/ops/areas/nowhere/sitbrief").status_code == 404


def test_ai_figures_must_be_in_the_evidence_the_item_cites(out, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    # 298 is in the evidence (calls flagged for review) but not in E28, the only item cited
    items = GOOD[:2] + [{"kind": "access", "text": "298 road segments are blocked.", "evidence": ["E28"]}]
    r = sb.ai_brief(AREA, client=FakeClient(items=items))
    assert [i["kind"] for i in r["items"]][:2] == ["headline", "damage"]
    assert r["dropped"] and "298" in r["dropped"][0]["reason"]
    # the run timestamp is not sent, so its digits cannot trace a figure
    assert all(e["label"] != "Assessment generated (UTC)" for e in sb.ai_payload(sb.evidence(AREA)))
