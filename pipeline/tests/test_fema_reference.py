"""FEMA housing assistance by ZIP, shown beside an assessment as context."""
import json

import pytest

from terratriage.ops.analyze import fema_reference as ref
from terratriage.ops.collect import fema_ha
from terratriage.ops.collect.base import Layer, SchemaError, SourceUnavailable
from terratriage.ops.provenance import Provenance

OWNER_ROWS = [  # one ZIP on three rows: two counties and a duplicate, as OpenFEMA publishes it
    {"county": "McDowell (County)", "city": "OLD FORT", "zipCode": "28762", "validRegistrations": 1654,
     "approvedForFemaAssistance": 1190, "approvedBetween25001AndMax": 217, "totalMaxGrants": 33,
     "repairReplaceAmount": 5_100_000.5, "totalApprovedIhpAmount": 8_000_000.25},
    {"county": "Buncombe (County)", "city": "OLD FORT", "zipCode": "28762", "validRegistrations": 5,
     "approvedForFemaAssistance": 3, "approvedBetween25001AndMax": 1, "totalMaxGrants": 0,
     "repairReplaceAmount": 11_789.24, "totalApprovedIhpAmount": 21_996.24},
    {"county": "McDowell (County)", "city": "OLDFORT", "zipCode": "28762", "validRegistrations": 5,
     "approvedForFemaAssistance": 4, "approvedBetween25001AndMax": 0, "totalMaxGrants": 0,
     "repairReplaceAmount": 0, "totalApprovedIhpAmount": 3000},
]
RENTER_ROWS = [{"county": "McDowell (County)", "city": "OLD FORT", "zipCode": "28762", "validRegistrations": 507,
                "approvedForFemaAssistance": 274, "totalApprovedIhpAmount": 696_002.83}]


@pytest.fixture
def ha(tmp_path, monkeypatch):
    monkeypatch.setattr("terratriage.ops.collect.base.OPS_CACHE", str(tmp_path / "cache"))
    calls = []

    def fake(url, params=None, **kw):
        calls.append(url)
        name = url.rsplit("/", 1)[1]
        return {name: OWNER_ROWS if name.endswith("Owners") else RENTER_ROWS}
    monkeypatch.setattr(fema_ha, "http_json", fake)
    return fema_ha.HousingAssistance(), calls


def test_rows_for_one_zip_are_summed(ha):
    src, calls = ha
    d = src.fetch(4827, "28762").data
    assert d["owners"] == {"registrations": 1664.0, "approved": 1197.0, "approved_over_25k": 218.0,
                           "max_grants": 33.0, "repair_replace_usd": 5_111_789.74,
                           "approved_usd": 8_024_996.49}
    assert d["renters"]["approved"] == 274.0 and d["cities"] == ["Old Fort", "Oldfort"]
    src.fetch(4827, "28762")
    assert len(calls) == 2                      # owners + renters once; the repeat came from the cache


def test_outage_serves_the_last_copy_and_says_so(ha, monkeypatch):
    src, _ = ha
    src.fetch(4827, "28762")
    monkeypatch.setattr(fema_ha, "MAX_AGE_S", -1)          # the cached copy is now too old

    def down(*a, **k):
        raise SourceUnavailable("www.fema.gov unreachable")
    monkeypatch.setattr(fema_ha, "http_json", down)
    layer = src.fetch(4827, "28762")
    assert layer.stale and layer.data["owners"]["approved"] == 1197.0 and layer.warnings
    with pytest.raises(SourceUnavailable):
        src.fetch(4827, "28752")                           # never fetched: nothing to fall back on


def test_schema_change_is_an_error_not_zeros(ha, monkeypatch):
    src, _ = ha
    monkeypatch.setattr(fema_ha, "http_json", lambda url, **k: {url.rsplit("/", 1)[1]: [{"zipCode": "28762"}]})
    with pytest.raises(SchemaError):
        src.fetch(4827, "28752")
    with pytest.raises(ValueError):
        src.fetch(4827, "2876; drop")


def test_zip_parsing():
    assert ref.zip_of("1469 CATAWBA RIVER ROAD, 28762") == "28762"
    assert ref.zip_of("6 RIVER CREEK PLACE, SWANNANOA, 28778-1234") == "28778"
    assert ref.zip_of("28762 MAIN STREET") is None and ref.zip_of(None) is None


class _Src:
    def __init__(self, fail=()):
        self.fail, self.asked = set(fail), []

    def fetch(self, disaster, zip_code):
        self.asked.append((disaster, zip_code))
        if zip_code in self.fail:
            raise SourceUnavailable("www.fema.gov unreachable")
        return Layer({"zip": zip_code, "disaster_number": disaster, "cities": ["Old Fort"],
                      "owners": {"registrations": 100.0, "approved": 60.0, "approved_over_25k": 9.0,
                                 "max_grants": 1.0, "repair_replace_usd": 1.0, "approved_usd": 2.0},
                      "renters": None}, Provenance("x", "y", "z"))


def _area(tmp_path, monkeypatch, declarations=("DR-4827-NC",)):
    monkeypatch.setattr(ref, "OPS_OUT", str(tmp_path))

    def feat(i, residential=True, probs=(0.2, 0.3)):
        p = {"ncr_id": f"id{i}", "flags": {"residential": residential},
             "damage_probs": None if probs is None else {"major": probs[0], "destroyed": probs[1]}}
        return {"type": "Feature", "geometry": None, "properties": p}
    feats = [feat(0), feat(1), feat(2, residential=False), feat(3, probs=None), feat(4), feat(5)]
    (tmp_path / "town.geojson").write_text(json.dumps({"properties": {
        "run_id": "r1", "event": {"declarations": list(declarations)}}, "features": feats}))
    (tmp_path / "town.responder.json").write_text(json.dumps({"structures": {
        "id0": {"address": "1 A ST, 28762"}, "id1": {"address": "2 A ST, 28762"},
        "id2": {"address": "3 A ST, 28762"}, "id3": {"address": "4 A ST, 28762"},
        "id4": {"address": "9 B RD, 28752"}}}))


def test_reference_pairs_each_zip_with_fema(tmp_path, monkeypatch):
    _area(tmp_path, monkeypatch)
    src = _Src()
    out = ref.run("town", src)
    assert out["status"] == "OK" and out["unplaced_structures"] == 1        # id5 has no address
    a, b = out["zips"]
    # commercial (id2) and unassessed (id3) structures count as structures, not as homes assessed
    assert (a["zip"], a["structures"], a["homes_assessed"], a["expected_major_plus"]) == ("28762", 4, 2, 1.0)
    assert (b["zip"], b["structures"], b["homes_assessed"], b["expected_major_plus"]) == ("28752", 1, 1, 0.5)
    assert a["fema"]["owners"]["approved"] == 60.0 and sorted(src.asked) == [(4827, "28752"), (4827, "28762")]
    assert "not a check" in out["caveat"]


def test_reference_survives_an_outage_and_a_missing_declaration(tmp_path, monkeypatch):
    _area(tmp_path, monkeypatch)
    out = ref.run("town", _Src(fail={"28752"}))
    assert out["status"] == "OK" and out["zips"][1]["fema"] is None
    assert any("28752" in w for w in out["warnings"])
    out = ref.run("town", _Src(fail={"28752", "28762"}))
    assert out["status"] == "NO_FEMA_DATA" and len(out["zips"]) == 2

    _area(tmp_path, monkeypatch, declarations=())                           # provisional event
    src = _Src()
    out = ref.run("town", src)
    assert out["status"] == "NO_DECLARATION" and src.asked == [] and all(z["fema"] is None for z in out["zips"])


def test_reference_reports_a_changed_fema_format(tmp_path, monkeypatch):
    from terratriage.ops.collect.base import SchemaError

    _area(tmp_path, monkeypatch)

    class Changed(_Src):
        def fetch(self, disaster, zip_code):
            raise SchemaError("row is missing the registration / approval columns")
    out = ref.run("town", Changed())
    assert out["status"] == "NO_FEMA_DATA" and all(z["fema"] is None for z in out["zips"])
    assert any("expected form" in w for w in out["warnings"])
