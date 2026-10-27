"""FEMA IA damage-survey layout in the GIS export (disseminate/exports._fema_ia)."""
import csv
import json
import os

import pytest

from terratriage.ops.disseminate import exports


def _feat(i, lvl, flags, occ=None, prim=None, review=False, probs=None):
    ring = [[-82.40 + i * 1e-3, 35.60], [-82.40 + i * 1e-3 + 1e-4, 35.60], [-82.40 + i * 1e-3 + 1e-4, 35.6001],
            [-82.40 + i * 1e-3, 35.6001], [-82.40 + i * 1e-3, 35.60]]
    p = {"ncr_id": f"s{i}", "centroid": [-82.40 + i * 1e-3, 35.60005], "usng_1m": "x", "usng_10m": f"17S LV {i}",
         "damage_level": lvl, "damage_probs": probs or ({lvl: 0.7} if lvl else {}), "confidence": 0.7,
         "needs_review": review, "review_reasons": ["LOW_CONFIDENCE_0.45"] if review else [],
         "flags": flags, "occupancy": occ, "primary_occupancy": prim,
         "fema": {"DMG_LEVEL": "x", "ASMT_TYPE": "Remote Sensing", "IMG_DATE": "2024-10-06",
                  "EVENT_NAME": "Hurricane / Tropical Storm Helene (NC)", "EVENT_DATE": "2024-09-25",
                  "DIS_NUMBER": "DR-4827-NC", "SOURCE": "Groma"}}
    geom = {"type": "Polygon", "coordinates": [ring]} if lvl else {"type": "Point", "coordinates": p["centroid"]}
    return {"type": "Feature", "geometry": geom, "properties": p}


@pytest.fixture
def area(tmp_path, monkeypatch):
    out = tmp_path / "ops"
    out.mkdir()
    monkeypatch.setattr(exports, "OPS_OUT", str(out))
    feats = [
        _feat(0, "destroyed", {"residential": True}, "RES1-1SNB", "Single Family Dwelling", review=True),
        _feat(1, "no_damage", {"residential": True, "manufactured_home": True}, "RES2", "Manufactured Home"),
        _feat(2, "major", {"residential": True}, "RES3A", "Multi - Family Dwelling"),
        _feat(3, "minor", {"outbuilding": True}),                       # a shed: not a home
        _feat(4, "affected", {}, "COM1", "Retail Trade"),               # a shop: not a home
        _feat(5, None, {"residential": True, "not_assessed": True}, "RES1-1SNB"),  # inventory point only
        _feat(6, "affected", {"residential": True}),                    # a home, type unknown
    ]
    fc = {"type": "FeatureCollection", "features": feats,
          "properties": {"generated_utc": "2026-10-09T12:00:00Z", "run_id": "t",
                         "event": {"id": "helene-2024-nc", "name": "Hurricane / Tropical Storm Helene (NC)",
                                   "declarations": ["DR-4827-NC"], "incident_begin": "2024-09-25"},
                         "aoi": {"id": "t", "role": "TUNE", "county": "Buncombe"}}}
    (out / "t.geojson").write_text(json.dumps(fc))
    (out / "t.responder.json").write_text(json.dumps({"structures": {
        "s0": {"address": "59 RIVER MEADOWS DR, SWANNANOA, 28778"}, "s2": {"address": "144 CENTRAL AVE"}}}))
    return out


def test_fema_ia_rows_fields_and_order(area):
    paths = exports.export_area("t", out_dir=str(area / "x"))
    with open(paths["fema_ia_csv"], newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0].keys())[:len(exports.FEMA_IA_FIELDS)] == list(exports.FEMA_IA_FIELDS)
    assert [r["ncr_id"] for r in rows] == ["s0", "s2", "s6", "s1", "s5"]   # verify-first, then severity; homes only
    s0, s2, s6, s1, s5 = rows
    assert s6["choose_the_type_of_dwelling"] == "" and s6["level_of_damage_assessed"] == "affected"
    assert s0["level_of_damage_assessed"] == "destroyed" and s0["ncr_needs_review"] == "yes"
    assert s0["street_address"] == "59 RIVER MEADOWS DR" and s0["zipcode"] == "28778"
    assert s0["choose_the_type_of_dwelling"] == "single_family" and s0["county"] == "Buncombe"
    assert s0["incident_id_number"] == "DR-4827-NC" and s0["what_event_type_caused_the_dama"] == "Hurricane"
    assert s0["owner_or_renter"] == s0["is_there_insurance"] == "unknown"
    assert "verify first" in s0["additional_narrative"] and "Not field verified" in s0["additional_narrative"]
    assert s1["level_of_damage_assessed"] == "unaffected" and s1["choose_the_type_of_dwelling"] == "manufactured_home"
    assert s2["choose_the_type_of_dwelling"] == "multi_family" and s2["zipcode"] == ""
    assert s5["level_of_damage_assessed"] == "" and "not assessed" in s5["additional_narrative"]
    assert all(r["level_of_damage_assessed"] in exports.FEMA_IA_LEVELS + ("",) for r in rows)


def test_fema_ia_geojson_points_and_provenance(area):
    paths = exports.export_area("t", out_dir=str(area / "x"))
    gj = json.load(open(paths["fema_ia_geojson"], encoding="utf-8"))
    assert len(gj["features"]) == 5 and all(f["geometry"]["type"] == "Point" for f in gj["features"])
    prov = json.load(open(paths["provenance"], encoding="utf-8"))
    assert prov["fema_ia_excluded_non_residential"] == 2
    readme = open(os.path.join(area / "x", "README.txt"), encoding="utf-8").read()
    assert "FEMA IA layout" in readme and "confirm it" in readme


def test_field_sheet_offers_only_fema_levels(area):
    exports.export_area("t", out_dir=str(area / "x"))
    with open(area / "x" / "survey123_choices.csv", newline="", encoding="utf-8") as fh:
        names = [r["name"] for r in csv.DictReader(fh) if r["list_name"] == "field_damage_category"]
    assert names == list(exports.FEMA_IA_LEVELS) and "moderate" not in names
