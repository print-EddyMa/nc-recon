import json
import os

import pytest
from fastapi.testclient import TestClient

HERE = os.path.dirname(__file__)


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
