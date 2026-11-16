"""SARCOP field-category comparison (analyze/sarcop_reference)."""
import json
import os

import numpy as np
import pytest

from terratriage.ops.analyze import sarcop_reference as s

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _square(cx, cy, half_m=6.0):
    dx = half_m / (111320.0 * np.cos(np.radians(cy)))
    dy = half_m / 110540.0
    return [[cx - dx, cy - dy], [cx + dx, cy - dy], [cx + dx, cy + dy], [cx - dx, cy + dy], [cx - dx, cy - dy]]


def _feat(i, lvl, probs, review=False, cx=-82.40, cy=35.60):
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [_square(cx + i * 0.001, cy)]},
            "properties": {"ncr_id": f"s{i}", "damage_level": lvl, "damage_probs": probs, "needs_review": review}}


def _pt(lon, lat, wp, cat="structure", t=1):
    return {"id": 1, "lon": lon, "lat": lat, "waypoint": wp, "category": cat, "program_type": "single_family",
            "acc_m": 4.7, "t": t, "source": "quickcapture"}


def test_credible_set_and_kappa():
    probs = {"no_damage": 0.5, "affected": 0.35, "minor": 0.1, "major": 0.05, "destroyed": 0.0}
    assert s.credible_set(probs) == ["no_damage", "affected"]
    assert s.credible_set({"major": 1.0}) == ["major"]
    perfect = np.diag([3, 2, 1, 4, 5])
    assert s.kappa(perfect) == pytest.approx(1.0) and s.kappa(perfect, "linear") == pytest.approx(1.0)
    assert s.kappa(np.zeros((5, 5), int)) is None


def test_match_inside_nearest_superseded_and_skips():
    feats = [_feat(0, "destroyed", {"destroyed": 0.9, "major": 0.1}),
             _feat(1, "no_damage", {"no_damage": 0.9, "affected": 0.1}),
             {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-82.398, 35.60]},
              "properties": {"ncr_id": "p", "damage_level": None}}]
    pts = [
        _pt(-82.40, 35.60, "destroyed", t=5),            # inside s0
        _pt(-82.40, 35.60, "major", t=2),                 # older visit to s0: superseded
        _pt(-82.399, 35.60009, "unaffected"),             # ~4 m north of s1's edge: nearest within 10 m
        _pt(-82.395, 35.60, "major"),                     # far from anything: unmatched
        _pt(-82.40, 35.60, "destroyed", cat="vehicle"),   # not a structure
        _pt(-82.40, 35.60, "moderate"),                   # not a FEMA level on this layer
    ]
    pairs, counts = s.match(pts, feats)
    assert counts == {"waypoints": 6, "not_structure": 1, "unmapped_category": 1, "unmatched": 1,
                      "matched": 2, "superseded_visits": 1}
    by = {p["ncr_id"]: p for p in pairs}
    assert by["s0"]["sar"] == "destroyed" and by["s0"]["dist_m"] == 0.0
    assert by["s1"]["sar"] == "no_damage" and 0 < by["s1"]["dist_m"] <= s.MATCH_M


def test_summary_counts_and_severe_metrics():
    pairs = [
        {"sar": "destroyed", "ncr": "destroyed", "probs": {"destroyed": 0.8, "major": 0.2}, "needs_review": True},
        {"sar": "major", "ncr": "no_damage", "probs": {"no_damage": 0.6, "affected": 0.3, "major": 0.1}, "needs_review": False},
        {"sar": "no_damage", "ncr": "no_damage", "probs": {"no_damage": 0.9}, "needs_review": False},
        {"sar": "no_damage", "ncr": "major", "probs": {"major": 0.5, "minor": 0.4}, "needs_review": True},
    ]
    r = s.summarise(pairs)
    assert r["n"] == 4 and r["same_level"] == 0.5
    m = r["major_or_destroyed"]
    assert (m["both_count"], m["sar_count"], m["ncr_most_likely_count"], m["precision"], m["recall"]) == (1, 2, 2, 0.5, 0.5)
    assert m["ncr_expected_count"] == pytest.approx(1.6, abs=0.05)
    assert r["sar_level_in_80pct_set"] == 0.5
    assert r["by_review"]["sent_to_review"]["n"] == 2
    assert sum(r["sar_counts"].values()) == sum(r["ncr_counts"].values()) == 4


def test_fixture_has_no_personal_fields():
    fx = json.load(open(os.path.join(FIX, "sarcop_swannanoa_2026-10-09.json"), encoding="utf-8"))
    allowed = {"id", "lon", "lat", "waypoint", "category", "program_type", "acc_m", "t", "source"}
    assert fx["points"] and all(set(p) <= allowed for p in fx["points"])
    assert "email" not in s.FIELDS and "address" not in s.FIELDS and "team_user" not in s.FIELDS


def test_compare_area_refuses_test_and_writes(tmp_path, monkeypatch):
    out = tmp_path / "ops"
    out.mkdir()
    monkeypatch.setattr(s, "OPS_OUT", str(out))
    fx = json.load(open(os.path.join(FIX, "sarcop_swannanoa_2026-10-09.json"), encoding="utf-8"))["points"]
    monkeypatch.setattr(s, "fetch_points", lambda bbox, **kw: fx)
    feats = [_feat(i, "no_damage", {"no_damage": 1.0}, cx=p["lon"], cy=p["lat"]) for i, p in enumerate(fx[:10])]
    for i, f in enumerate(feats):  # one polygon per waypoint, centred on it
        f["geometry"]["coordinates"] = [_square(fx[i]["lon"], fx[i]["lat"])]
    fc = {"type": "FeatureCollection", "features": feats,
          "properties": {"run_id": "t", "aoi": {"id": "t", "role": "TEST", "county": "Buncombe"}}}
    (out / "t.geojson").write_text(json.dumps(fc))
    with pytest.raises(SystemExit):
        s.compare_area("t")
    r = s.compare_area("t", allow_test=True)
    assert r["counts"]["matched"] >= 1 and os.path.exists(out / "t.sarcop_reference.json")
    assert any("not an accuracy figure" in c for c in r["caveats"])
    assert r["summary_homes"]["n"] <= r["summary"]["n"]
    assert "Swannanoa" not in json.dumps(r["pairs"])   # pairs carry ids and categories only
