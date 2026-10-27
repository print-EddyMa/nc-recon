"""IDA packet in FEMA's PDA formats (disseminate/ida.py) and the small xlsx writer."""
import json
import zipfile
from xml.etree import ElementTree as ET

import pytest

from terratriage.ops.disseminate import exports, ida, xlsx

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _feat(i, lvl, flags, occ=None, prim=None, review=False, probs=None):
    x = -82.40 + i * 1e-3
    ring = [[x, 35.60], [x + 1e-4, 35.60], [x + 1e-4, 35.6001], [x, 35.6001], [x, 35.60]]
    p = {"ncr_id": f"s{i}", "centroid": [x, 35.60005], "usng_1m": "17S LV 7300 4000", "usng_10m": f"17S LV {i}",
         "damage_level": lvl, "damage_probs": probs or ({lvl: 0.7, "no_damage": 0.3} if lvl else {}),
         "confidence": 0.7, "needs_review": review, "review_reasons": [], "flags": flags,
         "occupancy": occ, "primary_occupancy": prim, "stories": 1,
         "fema": {"DMG_LEVEL": "x", "ASMT_TYPE": "Remote Sensing", "IMG_DATE": "2024-10-06",
                  "EVENT_NAME": "Test storm", "EVENT_DATE": "2024-09-25", "DIS_NUMBER": "DR-4999-SC",
                  "SOURCE": "Groma"}}
    geom = {"type": "Polygon", "coordinates": [ring]} if lvl else {"type": "Point", "coordinates": p["centroid"]}
    return {"type": "Feature", "geometry": geom, "properties": p}


@pytest.fixture
def area(tmp_path, monkeypatch):
    out = tmp_path / "ops"
    out.mkdir()
    for m in (exports, ida):
        monkeypatch.setattr(m, "OPS_OUT", str(out))
    feats = [
        _feat(0, "destroyed", {"residential": True}, "RES1-1SNB", "Single Family Dwelling", review=True),
        _feat(1, "major", {"residential": True, "manufactured_home": True}, "RES2", "Manufactured Home"),
        _feat(2, "no_damage", {"residential": True}, "RES1-1SNB"),
        _feat(3, "minor", {}, "COM1", "Retail Trade"),            # a business, not a home
        _feat(4, "affected", {"residential": True}, "RES3A", "Multi - Family Dwelling"),
    ]
    fc = {"type": "FeatureCollection", "features": feats,
          "properties": {"generated_utc": "2026-10-09T12:00:00Z", "run_id": "t-run",
                         "event": {"id": "test-2024", "name": "Test storm", "declarations": ["DR-4999-SC"],
                                   "incident_begin": "2024-09-25"},
                         "aoi": {"id": "t", "role": "TUNE", "county": "Greenville"}}}
    (out / "t.geojson").write_text(json.dumps(fc))
    (out / "t.responder.json").write_text(json.dumps({"structures": {"s0": {"address": "1 MAIN ST, X, 29601"}}}))
    (out / "t.response.json").write_text(json.dumps({
        "summary": {"hazards": ["riverine_flood"]},
        "access": {"isolated_ids": {"known_blocks": ["s1"], "plus_debris": ["s1", "s4"]},
                   "isolated_clusters": [{"buildings": 2, "usng": "17S LV 730 400"}]},
        "sectors": [{"priority": 1, "usng_1km": "17S LV 73 40", "buildings": 5, "major_or_destroyed_expected": 1.4,
                     "people_in_severe_expected": 2.0, "cut_off_buildings": 1, "needs_review": 1,
                     "center": [-82.398, 35.6]}],
        "needs": {"people_displaced_expected": 3}}))
    (out / "t.response.layers.json").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-82.4, 35.6], [-82.401, 35.6]]},
         "properties": {"layer": "road", "status": "blocked", "why": ["mapped landslide of this storm on the road"],
                        "way": "way/1", "highway": "residential", "name": "River Road"}},
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-82.4, 35.6], [-82.402, 35.6]]},
         "properties": {"layer": "road", "status": "open", "why": [], "way": "way/2", "highway": "residential",
                        "name": "Open Lane"}}]}))
    return out


def _row(r):
    """Cells by column (the writer leaves empty cells out)."""
    out = {}
    for c in r:
        col = "".join(ch for ch in c.get("r") if ch.isalpha())
        idx = 0
        for ch in col:
            idx = idx * 26 + ord(ch) - 64
        out[idx - 1] = "".join(t.text or "" for t in c.iter(f"{{{NS['s']}}}t")) or (c.findtext("s:v", "", NS))
    return [out.get(i, "") for i in range(max(out) + 1)] if out else []


def test_state_comes_from_the_declaration():
    assert exports.state_name({"properties": {"event": {"declarations": ["DR-4856-CA"]}}}) == "California"
    assert exports.state_name({"properties": {"event": {}, "aoi": {"state": "TX"}}}) == "Texas"
    assert exports.state_name({"properties": {}}) == ""


def test_packet_counts_access_and_files(area):
    out = ida.build("t")
    assert set(out["files"]) >= {"xlsx", "narrative", "readme"}
    assert out["homes"] == 4                                  # the shop is left out
    lv = out["levels"]
    assert (lv["destroyed"], lv["major"], lv["affected"], lv["unaffected"]) == (1, 1, 1, 1)
    assert out["inaccessible"] == 1
    assert "not been validated" in out["validation"]
    with zipfile.ZipFile(out["files"]["xlsx"]) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        names = [s.get("name") for s in wb.find("s:sheets", NS)]
        assert names[:2] == ["IA homes", "Summary"] and "Roads cut" in names
        rows = ET.fromstring(z.read("xl/worksheets/sheet1.xml")).find("s:sheetData", NS)
        cells = [_row(r) for r in rows]
    header = cells[0]
    assert header[:len(exports.FEMA_IA_FIELDS)] == list(exports.FEMA_IA_FIELDS)
    body = {r[header.index("ncr_id")]: r + [""] * (len(header) - len(r)) for r in cells[1:]}
    mh = body["s1"]
    # inaccessible is its own column: the remote level stays (FEMA: assign it when the damage is viewable)
    assert mh[header.index("level_of_damage_assessed")] == "major"
    assert mh[header.index("ncr_access")] == "inaccessible: no road out"
    assert body["s4"][header.index("ncr_access")] == "inaccessible if debris blocks roads"
    assert body["s0"][header.index("stateterritory")] == "South Carolina"
    html = open(out["files"]["narrative"], encoding="utf-8").read()
    assert "River Road" in html and "Open Lane" not in html
    assert ida.ASK_LOCAL in html and "—" not in html
    assert "1 MAIN ST" not in html                            # the narrative never lists addresses


def test_wildfire_note_states_what_was_measured():
    n = ida.validation_note(["wildfire"])
    assert "0.957" in n and "0.942" in n and "not yet been scored on a new fire" in n


def test_missing_access_is_said_not_guessed(area):
    (area / "t.response.json").unlink()
    out = ida.build("t")
    assert out["inaccessible"] is None
    assert "Not computed for this run" in open(out["files"]["narrative"], encoding="utf-8").read()


def test_xlsx_neutralises_formulas_and_bad_xml(tmp_path):
    p = xlsx.write(str(tmp_path / "x.xlsx"), [("A/B: c", ["h"], [["=HYPERLINK(1)"], ["ok\x01"], [3.5], [None]])])
    with zipfile.ZipFile(p) as z:
        assert "A B  c" in z.read("xl/workbook.xml").decode()
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
    assert "'=HYPERLINK(1)" in sheet and "\x01" not in sheet and "<v>3.5</v>" in sheet
