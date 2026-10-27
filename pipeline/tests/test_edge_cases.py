"""An assessment over ground with no structures, and small-count disclosure."""
import json

import pytest

from terratriage.ops.analyze import impact
from terratriage.ops.disseminate import aggregate as agg
from terratriage.ops.disseminate import brief as brief_mod
from terratriage.ops.disseminate import exports

RUN = {
    "schema": "ops-1.0", "run_id": "forest-1", "generated_utc": "2026-10-01T04:09:10Z",
    "event": {"id": "helene-2024-nc", "name": "Helene", "declarations": ["DR-4827-NC"],
              "incident_begin": "2024-09-25"},
    "aoi": {"id": "forest_ab12", "role": "OPS", "county": "", "center": [-82.26, 35.74]},
    "pair_context": {"reasons": []},
    "counts": {c: 0 for c in ("no_damage", "affected", "minor", "major", "destroyed")},
    "expected_counts": {c: 0.0 for c in ("no_damage", "affected", "minor", "major", "destroyed")},
    "expected_counts_80pct": {}, "n_structures": 0, "n_needs_review": 0,
    "not_assessed": {"total": 0, "residential": 0},
    "calibration": {"cnn": "none", "fusion": "none", "conformal": "none"},
    "warnings": [], "provenance": {},
}


@pytest.fixture
def out(tmp_path, monkeypatch):
    for mod in (impact, agg, brief_mod, exports):
        monkeypatch.setattr(mod, "OPS_OUT", str(tmp_path))
    return tmp_path


def _write(out, area, features, **props):
    (out / f"{area}.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "properties": RUN | props, "features": features}))


def test_area_with_no_structures_degrades_cleanly(out, monkeypatch):
    _write(out, "forest_ab12", [])
    assert impact.run("forest_ab12")["status"] == "NO_STRUCTURES"
    html = open(brief_mod.brief("forest_ab12")).read()
    assert "no structures" in html and "Forest (" not in html and "<h1>Situation brief: Forest</h1>" in html
    monkeypatch.setattr(agg, "svi_tracts", lambda bbox: pytest.fail("no tract lookup needed"))
    body = json.load(open(agg.aggregate("forest_ab12")))
    assert body["features"] == []
    with pytest.raises(ValueError, match="no structures"):
        exports.export_area("forest_ab12")


def _home(i, lon, lat, p_major=0.9):
    probs = {"no_damage": round(1 - p_major, 2), "affected": 0, "minor": 0, "major": p_major, "destroyed": 0}
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"ncr_id": f"id{i}", "centroid": [lon, lat], "damage_level": "major",
                           "damage_probs": probs, "needs_review": True}}


def _tract(fips, w, s, e, n):
    ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"FIPS": fips, "LOCATION": f"Census Tract {fips}"}}


def test_people_figures_are_withheld_with_small_counts(out, monkeypatch):
    """A tract with under 5 structures hides its counts; its displaced-people
    and need figures describe the same few homes and must be hidden too."""
    few = [_home(i, -82.05 + i * 1e-4, 35.55) for i in range(2)]           # tract A: 2 homes
    many = [_home(10 + i, -81.95 + i * 1e-4, 35.55) for i in range(8)]     # tract B: 8 homes
    _write(out, "town", few + many)
    (out / "town.impact.json").write_text(json.dumps({"tracts": [
        {"tract": "A", "structures": 2, "expected_displaced": 4.6, "need_index": 7.1, "svi_percentile": 0.5},
        {"tract": "B", "structures": 8, "expected_displaced": 18.2, "need_index": 30.0, "svi_percentile": 0.6}]}))
    monkeypatch.setattr(agg, "svi_tracts", lambda bbox: [_tract("A", -82.1, 35.5, -82.0, 35.6),
                                                         _tract("B", -82.0, 35.5, -81.9, 35.6)])
    feats = {f["properties"]["tract"]: f["properties"]
             for f in json.load(open(agg.aggregate("town")))["features"]}
    a, b = feats["A"], feats["B"]
    assert a["structures"] is None and a["expected_displaced"] is None and a["need_index"] is None
    assert {"structures", "expected_displaced", "need_index"} <= set(a["suppressed_fields"])
    assert a["svi_percentile"] == 0.5                      # a published tract statistic, not ours
    assert b["structures"] == 8 and b["expected_displaced"] == 18.2 and b["need_index"] == 30.0


def test_people_figures_follow_the_residential_count(out, monkeypatch):
    """Ten structures in the tract but only three assessed homes behind the
    people estimate: the estimate is still about three households."""
    _write(out, "town", [_home(i, -82.05 + i * 1e-4, 35.55) for i in range(10)])
    (out / "town.impact.json").write_text(json.dumps({"tracts": [
        {"tract": "A", "structures": 3, "expected_displaced": 6.0, "need_index": 9.0, "svi_percentile": 0.5}]}))
    monkeypatch.setattr(agg, "svi_tracts", lambda bbox: [_tract("A", -82.1, 35.5, -82.0, 35.6)])
    p = json.load(open(agg.aggregate("town")))["features"][0]["properties"]
    assert p["structures"] == 10 and p["expected_displaced"] is None and p["need_index"] is None
