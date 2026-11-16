"""Self-checks (ops/selfcheck.py): vocabulary, verdict rules, margin math,
the hold-out rule and the API route. Every fixture is built in tmp_path."""
import json
import os

import pytest

from terratriage.ops import selfcheck as sc

LEVELS = sc.LEVELS
E1_ROWS = {  # likelihood rows as the pipeline stores them (favoured level = argmax)
    "no_damage": [0.53, 0.38, 0.09, 0.0, 0.0],
    "destroyed": [0.0, 0.0, 0.02, 0.24, 0.74],
}
E2_ROWS = {"low": [0.40, 0.30, 0.17, 0.09, 0.04], "high": [0.05, 0.10, 0.20, 0.30, 0.35]}


def _feature(i, level, e1, e2, review=False, residential=True, occupants=2):
    probs = {c: (1.0 if c == level else 0.0) for c in LEVELS} if level else None
    ev = []
    if level:
        ev = [{"id": "E1", "available": True, "status": "label_only", "likelihood": E1_ROWS[e1]},
              {"id": "E2", "available": True, "status": "provisional", "likelihood": E2_ROWS[e2]}]
    return {"type": "Feature", "geometry": None, "properties": {
        "ncr_id": f"id-{i}", "damage_level": level, "damage_probs": probs, "needs_review": review,
        "reason_codes": [], "review_reasons": [], "evidence": ev,
        "flags": {"residential": residential}, "occupants": {"nsi_estimate": occupants},
        "fema": {"IMG_DATE": "2024-10-02"} if level else {}}}


def _area(role="TUNE", area="tune_area"):
    feats = ([_feature(i, "no_damage", "no_damage", "low") for i in range(6)]
             + [_feature(6, "destroyed", "destroyed", "high", review=True),
                _feature(7, "destroyed", "destroyed", "high", review=True),
                _feature(8, None, None, None)])
    counts = {c: 0 for c in LEVELS}
    for f in feats:
        if f["properties"]["damage_level"]:
            counts[f["properties"]["damage_level"]] += 1
    props = {
        "run_id": f"{area}-run1", "generated_utc": "2026-11-01T00:00:00Z",
        "event": {"id": "ev", "incident_begin": "2024-09-25"},
        "aoi": {"id": area, "role": role},
        "pair_context": {"off_nadir_diff_deg": 3.0, "sun_elev_diff_deg": 6.0, "pair_gap_days": 400,
                         "post_days_after_incident": 7, "e2_geometry_weight": 1.0, "reasons": []},
        "coregistration": {"shift_px": [0.1, 0.2], "residual_px": 0.5, "n_windows": 16},
        "footprint_alignment": {"usa_structures:pre": {"dx_m": 1.0, "dy_m": -1.5, "peak_z": 8.0, "n": 200},
                                "usa_structures:post": {"dx_m": 0.5, "dy_m": 0.5, "peak_z": 7.0, "n": 200}},
        "counts": counts, "expected_counts": {c: float(v) for c, v in counts.items()},
        "not_assessed": {"total": 1, "residential": 1}, "n_structures": len(feats), "n_needs_review": 2,
        "calibration": {"cnn": "none", "fusion": "none", "conformal": "none"},
        "provenance": {"model": {"id": "xview2_cmu_baseline", "file": "xview2_cmu_classifier.onnx",
                                 "sha256": sc.RELEASED_WEIGHTS["xview2_cmu_classifier.onnx"]}},
    }
    return {"type": "FeatureCollection", "properties": props, "features": feats}


@pytest.fixture
def out(tmp_path, monkeypatch):
    # roles come from the file in these tests, never from the live registry
    monkeypatch.setattr(sc, "registry_role", lambda area: None)
    d = tmp_path / "ops_out"
    d.mkdir()
    return d


def _write(out, area, fc):
    (out / f"{area}.geojson").write_text(json.dumps(fc))


def _run(out, area="tune_area", fc=None, labels=None):
    _write(out, area, fc or _area(area=area))
    return sc.run_checks(area, out_dir=str(out), labels_dir=str(labels or out / "labels"))


def _by_id(rep):
    return {c["id"]: c for c in rep["checks"]}


# --------------------------------------------------------------------------- #
# margin math
# --------------------------------------------------------------------------- #
def test_margin_math():
    # a maximum: share of the limit used, measured from the base
    assert sc.load_of(0.87, 1.0, "max") == pytest.approx(0.87)
    assert sc.margin_of(0.87) == pytest.approx(1 / 0.87 - 1)
    assert sc.load_of(30, 50, "max", base=20) == pytest.approx(1 / 3)
    # a minimum requirement: required / actual
    assert sc.load_of(100, 50, "min") == pytest.approx(0.5)
    assert sc.margin_of(0.5) == pytest.approx(1.0)
    assert sc.load_of(40, 50, "min") == pytest.approx(1.25)
    assert sc.margin_of(1.25) < 0
    assert sc.margin_of(1.0) == 0
    # no meaning -> None, never NaN; capped so JSON stays finite
    assert sc.load_of(None, 1, "max") is None
    assert sc.load_of(1, 0, "max") is None
    assert sc.load_of(0, 50, "min") is None
    assert sc.load_of(float("nan"), 1, "max") is None
    assert sc.load_of(1e9, 1, "max") == sc.MAX_LOAD
    assert sc.margin_of(None) is None
    assert sc.margin_of(0.0) == sc.MAX_LOAD
    m = sc.metric("slope", 7.04, 7.0, "max", "degrees", slack=0.05)
    assert m["ok"] is True and m["load"] > 1
    assert sc.spare(0.5) == "100% to spare" and sc.spare(1.0) == "at the limit"
    assert "over the limit" in sc.spare(1.2)


# --------------------------------------------------------------------------- #
# vocabulary and verdict
# --------------------------------------------------------------------------- #
def _row(status, na=False):
    r = {"id": status, "title": status, "status": status, "load": None}
    if status == sc.SKIP:
        r["not_applicable"] = na
    return r


def test_verdict_rules():
    assert sc.verdict_of([_row("pass"), _row("pass")]) == sc.VERIFIED
    assert sc.verdict_of([_row("pass"), _row("skip", na=True)]) == sc.VERIFIED
    assert sc.verdict_of([_row("pass"), _row("skip", na=False)]) == sc.WITH_WARNINGS
    assert sc.verdict_of([_row("pass"), _row("warn")]) == sc.WITH_WARNINGS
    assert sc.verdict_of([_row("warn"), _row("fail"), _row("skip", na=True)]) == sc.FAILED


def test_clean_area_report(out):
    rep = _run(out)
    json.dumps(rep, allow_nan=False)      # JSON-safe
    c = _by_id(rep)
    for cid in ("buildings_conserved", "totals_recomputed", "imagery_dates", "pair_geometry",
                "coregistration", "footprint_alignment", "model_weights"):
        assert c[cid]["status"] == "pass", (cid, c[cid]["finding"])
    # no stated thresholds -> warn, never an invented limit
    assert c["review_share"]["status"] == "warn" and c["review_share"]["source"].startswith(sc.NO_THRESHOLD)
    assert c["review_share"]["value"] == pytest.approx(2 / 8)
    assert c["independent_route"]["status"] == "warn"
    assert c["independent_route"]["value"] == pytest.approx(1.0)   # both severe calls shared
    assert c["calibration"]["status"] == "skip" and c["calibration"]["reason"] == "not yet validated for this hazard"
    assert c["calibration"]["not_applicable"] is False
    assert rep["verdict"] == sc.WITH_WARNINGS
    # coregistration margin is the Margin formula on the stored residual
    assert c["coregistration"]["load"] == pytest.approx(0.5)
    assert c["coregistration"]["margin"] == pytest.approx(1.0)
    # every check names where its threshold comes from, and every skip says why
    for row in rep["checks"]:
        assert row["finding"]
        if row["status"] == "skip":
            assert row["reason"]
        elif row["limit"] is not None or row["kind"]:
            assert row["source"], row["id"]
        assert "\u2014" not in row["finding"] + row["note"]          # copy rule: no em dashes
    assert rep["note"].startswith("Checks label")


def test_conservation_fail(out):
    fc = _area()
    fc["properties"]["not_assessed"]["total"] = 0     # one structure vanishes
    c = _by_id(_run(out, fc=fc))
    assert c["buildings_conserved"]["status"] == "fail"


def test_totals_second_route_fail(out):
    fc = _area()
    fc["properties"]["counts"]["destroyed"] = 5
    fc["properties"]["counts"]["no_damage"] = 3      # same total, wrong split
    fc["properties"]["expected_counts"]["destroyed"] = 4.0
    rep = _run(out, fc=fc)
    c = _by_id(rep)
    assert c["buildings_conserved"]["status"] == "pass"
    assert c["totals_recomputed"]["status"] == "fail"
    assert rep["verdict"] == sc.FAILED


def test_coregistration_over_limit_fails(out):
    fc = _area()
    fc["properties"]["coregistration"]["residual_px"] = 6.71
    c = _by_id(_run(out, fc=fc))["coregistration"]
    assert c["status"] == "fail" and c["load"] == pytest.approx(6.71) and c["margin"] < 0
    assert "coreg.py" in c["source"]


def test_coregistration_over_limit_with_e2_switched_off_warns(out):
    # the pipeline gate (rules 2026-11-15.1) switches E2 off above 1 px; the check then only warns
    fc = _area()
    fc["properties"]["coregistration"]["residual_px"] = 6.71
    for f in fc["features"]:
        for e in f["properties"]["evidence"]:
            if e["id"] == "E2":
                e.update(available=False, unavailable_reason="MISREGISTERED", likelihood=None)
    c = _by_id(_run(out, fc=fc))["coregistration"]
    assert c["status"] == "warn" and c["margin"] < 0
    assert "switched off" in c["finding"]


def test_coregistration_missing_is_a_gap(out):
    fc = _area()
    del fc["properties"]["coregistration"]
    c = _by_id(_run(out, fc=fc))["coregistration"]
    assert c["status"] == "skip" and c["not_applicable"] is False and c["reason"]


def test_dates(out):
    fc = _area()
    fc["properties"]["pair_context"]["post_days_after_incident"] = [98, 248]
    for f in fc["features"]:
        f["properties"]["fema"] = {"IMG_DATE_RANGE": "2025-01-01..2025-05-31"}
    assert _by_id(_run(out, fc=fc))["imagery_dates"]["status"] == "pass"
    fc = _area()
    fc["properties"]["pair_context"]["post_days_after_incident"] = -3
    for f in fc["features"]:
        f["properties"]["fema"] = {"IMG_DATE": "2024-09-22"}
    assert _by_id(_run(out, fc=fc))["imagery_dates"]["status"] == "fail"
    # the two records disagree
    fc = _area()
    for f in fc["features"]:
        f["properties"]["fema"] = {"IMG_DATE": "2025-03-01"}
    assert _by_id(_run(out, fc=fc))["imagery_dates"]["status"] == "fail"


def test_geometry_warn_and_skip(out):
    fc = _area()
    fc["properties"]["pair_context"].update(off_nadir_diff_deg=18.5, e2_geometry_weight=0.6)
    c = _by_id(_run(out, fc=fc))["pair_geometry"]
    assert c["status"] == "warn" and c["limit"] == 15 and c["load"] == pytest.approx(18.5 / 15)
    fc = _area()
    fc["properties"]["pair_context"].update(off_nadir_diff_deg=None, sun_elev_diff_deg=None,
                                            reasons=["AERIAL_ORTHO_GEOMETRY_UNRECORDED"])
    c = _by_id(_run(out, fc=fc))["pair_geometry"]
    assert c["status"] == "skip" and "aerial" in c["reason"]


def test_alignment_too_few_footprints_warns(out):
    fc = _area()
    fc["properties"]["footprint_alignment"]["osm:post"] = {"dx_m": 0, "dy_m": 0, "peak_z": 0, "n": 4}
    c = _by_id(_run(out, fc=fc))["footprint_alignment"]
    assert c["status"] == "warn" and "too few" in c["finding"]


def test_weights(out):
    fc = _area()
    fc["properties"]["provenance"]["model"]["sha256"] = "0" * 64
    assert _by_id(_run(out, fc=fc))["model_weights"]["status"] == "fail"
    fc = _area()
    fc["properties"]["provenance"]["model"] = {"weights": "classification.hdf5",
                                               "sha256": sc.RELEASED_WEIGHTS["classification.hdf5"]}
    assert _by_id(_run(out, fc=fc))["model_weights"]["status"] == "pass"
    fc["properties"]["provenance"]["model"] = {"file": "other.onnx", "sha256": "1" * 64}
    assert _by_id(_run(out, fc=fc))["model_weights"]["status"] == "warn"


def test_released_hashes_are_the_documented_ones():
    with open(sc.WEIGHTS_README, encoding="utf-8") as fh:
        text = fh.read()
    for h in sc.RELEASED_WEIGHTS.values():
        assert h in text


def test_tune_labels_report_agreement(out, tmp_path):
    labels = tmp_path / "labels"
    labels.mkdir()
    (labels / "tune_area.csv").write_text(
        "ncr_id,label,labeler,protocol,imagery_date,notes\n"
        "id-0,no_damage,a,ncr-label-v1,,\n"
        "id-1,minor,a,ncr-label-v1,,\n"
        "id-6,destroyed,a,ncr-label-v1,,\n"
        "id-7,major,a,ncr-label-v1,,\n")
    c = _by_id(_run(out, labels=labels))["calibration"]
    assert c["status"] == "warn" and c["source"].startswith(sc.NO_THRESHOLD)
    assert c["detail"]["labels"]["n"] == 4
    assert c["value"] == pytest.approx(0.5)
    assert c["detail"]["labels"]["major_or_destroyed_f1"] == pytest.approx(1.0)
    assert "none of this is a held-out result" in c["finding"] + c["note"]


@pytest.mark.parametrize("area,role", [("test_area", "TEST"), ("canton", "TUNE")])
def test_test_area_is_held_out(out, tmp_path, monkeypatch, area, role):
    """TEST from the file's role, or a registered hold-out name: the
    validation check skips before any label or reference file is opened."""
    labels = tmp_path / "labels"
    labels.mkdir()
    (labels / f"{area}.csv").write_text("ncr_id,label,labeler\nid-0,no_damage,a\n")
    (out / f"{area}.sarcop_reference.json").write_text(json.dumps({"role": "TUNE", "summary": {"n": 1}}))
    (out / f"{area}.field_reference.json").write_text(json.dumps({"role": "TUNE", "summary": {"n": 1}}))
    opened = []
    real = sc._read_json

    def spy(path):
        opened.append(os.path.basename(path))
        return real(path)

    def no_labels(*a, **k):
        raise AssertionError("labels opened for a TEST area")

    monkeypatch.setattr(sc, "_read_json", spy)
    monkeypatch.setattr(sc, "_label_agreement", no_labels)
    rep = _run(out, area=area, fc=_area(role=role, area=area), labels=labels)
    c = _by_id(rep)["calibration"]
    assert rep["role"] == "TEST"
    assert c["status"] == "skip" and c["reason"] == sc.HELD_OUT and c["not_applicable"] is True
    assert not [p for p in opened if "reference" in p]


def test_registry_test_role_wins(out, monkeypatch):
    monkeypatch.setattr(sc, "registry_role", lambda area: "TEST")
    rep = _run(out, fc=_area(role="TUNE"))
    assert rep["role"] == "TEST"
    assert _by_id(rep)["calibration"]["reason"] == sc.HELD_OUT


def test_registry_reads_roles_without_network():
    # the committed registry: Swannanoa is TUNE, Canton is TEST (config/events.yaml)
    assert sc.registry_role("swannanoa") == "TUNE"
    assert sc.registry_role("canton") == "TEST"


def _response(cands, run_id="tune_area-run1", params=True):
    land = {"candidates": cands}
    if params:
        land["params"] = {"min_diameter_m": 50.0, "ch47_diameter_m": 80.0, "max_slope_deg": 7.0}
    return {"run_id": run_id, "landing": land}


def test_landing_zone_margins(out):
    good = {"usng": "A", "clear_diameter_m": 100, "slope_deg": 3.5, "fits": ["UH-60", "CH-47"]}
    uh = {"usng": "B", "clear_diameter_m": 62, "slope_deg": 1.0, "fits": ["UH-60"]}
    (out / "tune_area.response.json").write_text(json.dumps(_response([good, uh])))
    rep = _run(out)
    lz = rep["landing_zones"]
    a, b = lz["candidates"]
    # CH-47 needs 80 m of a 100 m clearing: load 0.8, margin 25%
    assert a["load"] == pytest.approx(0.8) and a["margin"] == pytest.approx(0.25)
    assert a["limiting"] == "CH-47 clear diameter"
    slope = [m for m in a["metrics"] if m["label"] == "slope"][0]
    assert slope["load"] == pytest.approx(0.5)
    assert b["load"] == pytest.approx(50 / 62) and b["status"] == "pass"
    c = _by_id(rep)["landing_zones"]
    assert c["status"] == "pass" and c["load"] == pytest.approx(50 / 62)
    assert "landing.py" in c["source"]


def test_landing_zone_over_limit_fails(out):
    bad = {"usng": "C", "clear_diameter_m": 70, "slope_deg": 2.0, "fits": ["UH-60", "CH-47"]}
    (out / "tune_area.response.json").write_text(json.dumps(_response([bad])))
    rep = _run(out)
    cand = rep["landing_zones"]["candidates"][0]
    assert cand["status"] == "fail" and cand["margin"] < 0
    assert _by_id(rep)["landing_zones"]["status"] == "fail"


def test_no_response_is_not_applicable(out):
    c = _by_id(_run(out))["landing_zones"]
    assert c["status"] == "skip" and c["not_applicable"] is True


def test_stale_products_fail(out):
    (out / "tune_area.response.json").write_text(json.dumps(_response([], run_id="tune_area-run0")))
    (out / "tune_area.impact.json").write_text(json.dumps({"run_id": "tune_area-run1",
                                                           "residential_structures_assessed": 8,
                                                           "unassessed_residential": {"structures": 1}}))
    c = _by_id(_run(out))
    assert c["products_match_run"]["status"] == "fail"
    assert c["people_estimate"]["status"] == "pass"


def test_people_estimate_mismatch(out):
    (out / "tune_area.impact.json").write_text(json.dumps({"run_id": "tune_area-run1",
                                                           "residential_structures_assessed": 5}))
    assert _by_id(_run(out))["people_estimate"]["status"] == "fail"


def test_bad_area_and_missing(out):
    with pytest.raises(ValueError):
        sc.run_checks("../etc", out_dir=str(out))
    with pytest.raises(FileNotFoundError):
        sc.run_checks("nowhere", out_dir=str(out))


def test_api_route(out, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from terratriage.ops import api, selfcheck_api

    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    monkeypatch.setattr(api, "OPS_OUT", str(out))
    _write(out, "tune_area", _area())
    app = FastAPI()
    app.include_router(selfcheck_api.router)
    client = TestClient(app)
    r = client.get("/ops/areas/tune_area/checks")
    assert r.status_code == 200
    body = r.json()
    assert body["area"] == "tune_area" and body["verdict"] in (sc.VERIFIED, sc.WITH_WARNINGS, sc.FAILED)
    assert client.get("/ops/areas/BAD!/checks").status_code in (400, 404)
    assert client.get("/ops/areas/nowhere/checks").status_code == 404
    monkeypatch.delenv("NCR_DEV_OPEN")
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "t0ken")
    assert client.get("/ops/areas/tune_area/checks").status_code in (401, 403)


def test_a_broken_check_is_recorded_not_dropped(out, monkeypatch):
    def boom(*a, **k):
        raise KeyError("x")

    monkeypatch.setattr(sc, "check_coreg", boom)
    rep = _run(out)
    c = _by_id(rep)["coregistration"]
    assert c["status"] == "fail" and "could not run" in c["finding"]
    assert len(rep["checks"]) == 14


def test_image_model_off_is_a_gap_unless_not_applied(out):
    fc = _area()
    for f in fc["features"]:
        for e in f["properties"]["evidence"]:
            if e["id"] == "E1":
                e.update(available=False, unavailable_reason="MODEL_MISSING")
    c = _by_id(_run(out, fc=fc))["model_weights"]
    assert c["status"] == "skip" and c["not_applicable"] is False and "MODEL_MISSING" in c["reason"]
    fc["properties"]["provenance"]["hazards"] = {"channels_applied": ["E2", "H"]}
    c = _by_id(_run(out, fc=fc))["model_weights"]
    assert c["status"] == "skip" and c["not_applicable"] is True


def test_values_are_physical_quantities(out):
    good = {"usng": "A", "clear_diameter_m": 100, "slope_deg": 3.5, "fits": ["UH-60", "CH-47"]}
    (out / "tune_area.response.json").write_text(json.dumps(_response([good])))
    c = _by_id(_run(out))
    assert (c["landing_zones"]["value"], c["landing_zones"]["limit"], c["landing_zones"]["unit"]) == (100, 80, "m")
    fa = c["footprint_alignment"]
    assert fa["unit"] in ("m", "footprints") and fa["limit"] in (15.0, 10)
    assert all(r["finding"].count(". ") <= 1 for r in c.values()), [r["finding"] for r in c.values()]


def test_misregistration_gate_switches_e2_off_end_to_end(out):
    # the pipeline gate, the E2 channel and the self-check, together
    from terratriage.ops.analyze import channels
    from terratriage.ops.analyze.evidence import BuildingEvidence
    from terratriage.ops.analyze.fusion import rules
    from terratriage.ops.pipeline import gate_misregistered

    limit = rules()["coreg_residual_max_px"]
    assert limit == 1.0
    evs, warnings = [BuildingEvidence(0), BuildingEvidence(1)], []
    assert not gate_misregistered(evs, {"residual_px": 0.9}, rules(), warnings)
    assert all("E2" not in e.unavailable for e in evs) and not warnings
    assert gate_misregistered(evs, {"residual_px": 6.71}, rules(), warnings)
    chans = [channels.e2(e, 1.0, (0.0, 1.0)) for e in evs]
    assert all(not c.available and c.unavailable_reason == "MISREGISTERED" for c in chans)
    assert "switched off" in warnings[0]

    fc = _area()
    fc["properties"]["coregistration"]["residual_px"] = 6.71
    for f, c in zip(fc["features"], chans * len(fc["features"])):
        f["properties"]["evidence"] = [e if e["id"] != "E2" else c.to_dict() for e in f["properties"]["evidence"]]
    assert _by_id(_run(out, fc=fc))["coregistration"]["status"] == "warn"
