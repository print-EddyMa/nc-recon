"""Any-event bootstrap: hazard profiles + draft/register from a FEMA declaration (offline)."""
from __future__ import annotations

import pytest

from terratriage.ops import hazards as hz
from terratriage.ops.plan import bootstrap as bs
from terratriage.ops.plan import events as ev

ERI = ["2024_Hurricane_Helene", "2024_Hurricane_Debby", "2024_Pre_Event", "2025_California_Fires",
       "2025_Texas_Flood", "2011_Joplin_Tornado"]
MAXAR = ["WildFires-LosAngeles-Jan-2025", "Maui-Hawaii-fires-Aug-23", "Texas-Flooding-July-2025"]


def _decl(number, title, itype, state, begin, areas):
    rows = [{"disasterNumber": number, "femaDeclarationString": f"DR-{number}-{state}",
             "declarationTitle": title, "incidentType": itype, "incidentBeginDate": f"{begin}T00:00:00.000Z",
             "declarationDate": f"{begin}T00:00:00.000Z", "designatedArea": a, "state": state,
             "ihProgramDeclared": True} for a in areas]
    return ev.parse_declaration(rows, "test://openfema")


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("NCR_OPS_REGISTRY", str(tmp_path / "reg.yaml"))
    decls = {
        4856: _decl(4856, "WILDFIRES AND STRAIGHT-LINE WINDS", "Fire", "CA", "2025-01-07", ["Los Angeles (County)"]),
        4876: _decl(4876, "SEVERE STORMS, STRAIGHT-LINE WINDS, AND FLOODING", "Flood", "TX", "2025-07-02",
                    ["Kerr (County)"]),
        9999: _decl(9999, "SEVERE WINTER STORM", "Winter Storm", "VT", "2025-02-01", ["Orange (County)"]),
    }
    real = ev.fetch_declaration                 # config events (Helene) load from cache or seed
    monkeypatch.setattr(bs, "fetch_declaration", lambda n: decls[n])
    monkeypatch.setattr(ev, "fetch_declaration", lambda n: decls[n] if n in decls else real(n))
    monkeypatch.setattr(bs, "eri_events", lambda: ERI)
    monkeypatch.setattr(bs, "maxar_events", lambda: MAXAR)
    return decls


def test_profiles_are_consistent():
    p = hz.profiles()
    assert set(hz.hazards_for_incident("Fire")) == {"wildfire"}
    assert hz.hazards_for_incident("Something new") == ["other"]
    assert "E5" in hz.channels_for(["riverine_flood"]) and "E5" not in hz.channels_for(["wildfire"])
    assert hz.channels_for([]) == set(hz.CHANNELS)          # unknown hazards keep every channel
    for h in p["hazards"].values():
        assert h["post_days"][0] >= 0 and h["post_days"][1] > h["post_days"][0]


def test_wildfire_draft_matches_imagery(offline):
    d = bs.draft_from_declaration(4856)
    assert d.event_id == "wildfire-2025-ca-dr4856"
    assert d.hazards == ["wildfire"] and d.state == "CA" and d.incident_begin == "2025-01-07"
    assert d.eri_prefix == "2025_California_Fires"
    assert d.maxar_event == "WildFires-LosAngeles-Jan-2025"
    assert any("CC BY-NC" in n for n in d.notes)
    assert d.name.startswith("Wildfires and Straight-Line Winds")


def test_wrong_year_and_pre_event_folders_never_match(offline):
    d = bs.draft_from_declaration(4856)
    folders = [c["folder"] for c in d.candidates["eri"]]
    assert "2024_Pre_Event" not in folders and "2011_Joplin_Tornado" not in folders
    assert all(c["folder"] != "Maui-Hawaii-fires-Aug-23" or c["score"] < 4 for c in d.candidates["maxar"])


def test_no_imagery_is_said_plainly(offline):
    d = bs.draft_from_declaration(9999)
    assert d.hazards == ["winter"] and d.eri_prefix is None and d.maxar_event is None
    assert any("no open post-event imagery" in n for n in d.notes)


def test_create_registers_a_loadable_event(offline):
    e, d = bs.create_from_declaration(4876)
    assert e.id == d.event_id and e.state == "TX"
    assert e.eri_prefix == "2025_Texas_Flood" and "eri" in e.post_sources
    assert e.post.end > e.post.start and e.pre.end < e.incident_begin
    assert ev.load_events()[e.id].hazards == ("riverine_flood", "flash_flood")
    with pytest.raises(ValueError):
        bs.create_from_declaration(4876)        # already registered


@pytest.fixture
def client():
    import os
    import sys

    from fastapi.testclient import TestClient

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import server
    return TestClient(server.app)


def test_hazards_route(client):
    r = client.get("/ops/hazards").json()
    assert r["hazards"]["wildfire"]["channels"] == ["E1", "E2", "H", "M1"]
    assert "M1" not in r["hazards"]["riverine_flood"]["channels"]     # wildfire only for now
    assert r["incident_types"]["Fire"] == ["wildfire"]


def test_from_fema_route_drafts_and_registers(client, offline, monkeypatch):
    body = {"disaster_number": 4856}
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    assert client.post("/ops/events/from-fema", json=body).status_code == 403
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    d = client.post("/ops/events/from-fema", json=body).json()
    assert d["event"] is None and d["draft"]["eri_prefix"] == "2025_California_Fires"
    # DR-4856 is already a config event (Altadena): registering it again is refused
    dup = client.post("/ops/events/from-fema", json={**body, "write": True})
    assert dup.status_code == 400 and "already exists" in dup.json()["detail"]
    w = client.post("/ops/events/from-fema", json={"disaster_number": 4876, "write": True}).json()
    assert w["event"]["hazards"] == ["riverine_flood", "flash_flood"] and w["event"]["state"] == "TX"
    assert client.post("/ops/events/from-fema", json={"disaster_number": 0}).status_code == 422
