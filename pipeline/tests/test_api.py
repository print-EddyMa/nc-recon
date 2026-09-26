import json
import os

import pytest
from fastapi.testclient import TestClient

HERE = os.path.dirname(__file__)


@pytest.fixture(autouse=True)
def _dev_open(monkeypatch):
    # tests exercise responder endpoints; production has no such bypass
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    monkeypatch.setenv("NCR_DEV_OPEN", "1")


@pytest.fixture(scope="module")
def client():
    import sys
    sys.path.insert(0, os.path.join(HERE, ".."))
    import server
    return TestClient(server.app)


def _have(area):
    from terratriage.ops.api import OPS_OUT
    return os.path.exists(os.path.join(OPS_OUT, f"{area}.geojson"))


def test_meta(client):
    r = client.get("/ops/meta")
    assert r.status_code == 200 and "Not an official FEMA" in r.json()["disclaimer"]


def test_bad_area_rejected(client):
    assert client.get("/ops/areas/..%2Fetc").status_code in (400, 404)
    assert client.get("/ops/areas/Bad-Area").status_code == 400


@pytest.mark.skipif(not _have("old_fort"), reason="no ops output for old_fort")
def test_public_geojson_has_no_addresses(client):
    body = client.get("/ops/areas/old_fort").content  # bytes: .text charset-sniffs 4 MB
    assert b'"address"' not in body and b"PROP_ADDR" not in body


@pytest.mark.skipif(not _have("old_fort"), reason="no ops output for old_fort")
def test_responder_needs_token_when_configured(client, monkeypatch):
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret")
    assert client.get("/ops/areas/old_fort/responder").status_code == 401
    r = client.get("/ops/areas/old_fort/responder", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200


@pytest.mark.skipif(not _have("old_fort"), reason="no ops output for old_fort")
def test_label_validation(client, monkeypatch, tmp_path):
    import terratriage.ops.api as api
    monkeypatch.setattr(api, "LABELS", str(tmp_path))
    fc = json.loads(client.get("/ops/areas/old_fort").content)
    nid = fc["features"][0]["properties"]["ncr_id"]
    bad = client.post("/ops/labels", json={"area": "old_fort", "ncr_id": nid, "label": "moderate", "labeler": "a"})
    assert bad.status_code == 422
    ok = client.post("/ops/labels", json={"area": "old_fort", "ncr_id": nid, "label": "minor", "labeler": "a"})
    assert ok.status_code == 200 and ok.json()["aoi_role"] == "TUNE"
    rows = (tmp_path / "old_fort.csv").read_text().splitlines()
    assert len(rows) == 2 and rows[1].startswith(nid)
    _ = json


@pytest.mark.skipif(not _have("old_fort"), reason="no ops output for old_fort")
def test_public_tracts_suppress_small_counts(client):
    body = json.loads(client.get("/ops/areas/old_fort/public.geojson").content)
    assert body["properties"]["suppression_threshold"] == 5
    for f in body["features"]:
        p = f["properties"]
        assert "address" not in p
        for k in p["suppressed_fields"]:
            assert p[k] is None
        for k in ("no_damage", "affected", "minor", "major", "destroyed", "structures"):
            v = p[k]
            assert v is None or v == 0 or v >= 5


@pytest.mark.skipif(not _have("old_fort"), reason="no ops output for old_fort")
def test_building_level_is_responder_only(client, monkeypatch):
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret")
    assert client.get("/ops/areas/old_fort").status_code == 401
    assert client.get("/ops/areas/old_fort/brief.html").status_code == 401
    assert client.get("/ops/areas/old_fort/public.geojson").status_code == 200
    ok = client.get("/ops/areas/old_fort", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_fails_closed_without_token_or_dev_flag(client, monkeypatch):
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    # a request that looks like it came through a same-host reverse proxy
    r = client.get("/ops/areas/old_fort", headers={"X-Forwarded-For": "127.0.0.1"})
    assert r.status_code == 403
    assert client.post("/ops/labels", json={}).status_code in (403, 422)


def test_wrong_token_rejected(client, monkeypatch):
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret")
    r = client.get("/ops/areas/old_fort", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_startup_refuses_exposed_without_token(monkeypatch):
    from terratriage.ops import auth
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    with pytest.raises(SystemExit):
        auth.startup_check("0.0.0.0")
    auth.startup_check("127.0.0.1")
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    with pytest.raises(SystemExit):
        auth.startup_check("0.0.0.0")


def test_provisional_event_and_ops_area(tmp_path, monkeypatch):
    from terratriage.ops.plan import events as ev
    monkeypatch.setenv("NCR_OPS_REGISTRY", str(tmp_path / "reg.yaml"))
    e = ev.add_provisional_event("storm-x", "Storm X", "2026-10-01", eri_prefix="2026_Storm_X")
    assert e.provisional and e.incident_begin.isoformat() == "2026-10-01"
    assert e.pre.end.isoformat() == "2026-09-30"
    a = ev.add_ops_area("town_ab12", "storm-x", "Town", -82.2, 35.6)
    assert a.role == "OPS"
    assert ev.event_for_area("town_ab12")[0].id == "storm-x"
    with pytest.raises(ValueError):
        ev.add_ops_area("town_ab12", "storm-x", "Town", -82.2, 35.6)


def test_assess_requires_auth_and_validates(client, monkeypatch):
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    body = {"event": "helene-2024-nc", "name": "Test", "lon": -82.2, "lat": 35.6}
    assert client.post("/ops/assess", json=body).status_code == 403
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    bad = dict(body, lon=-90.0)
    assert client.post("/ops/assess", json=bad).status_code == 422
    unknown = dict(body, event="nope")
    assert client.post("/ops/assess", json=unknown).status_code == 400


def test_delete_refuses_tune_test_and_removes_ops(tmp_path, monkeypatch, client):
    from terratriage.ops.plan import events as ev
    monkeypatch.setenv("NCR_OPS_REGISTRY", str(tmp_path / "reg.yaml"))
    assert client.delete("/ops/areas/old_fort").status_code == 403       # TUNE area
    ev.add_ops_area("scratch_ab12", "helene-2024-nc", "Scratch", -82.2, 35.6)
    r = client.delete("/ops/areas/scratch_ab12")
    assert r.status_code == 200 and "registry entry" in r.json()["removed"]
    assert ev.event_for_area("scratch_ab12") is None
