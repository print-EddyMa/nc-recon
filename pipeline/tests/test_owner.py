"""Owner evidence record links and the public banded check (ops/owner.py, owner_api.py)."""
import json
import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

from terratriage.ops import api, guard, owner

HERE = os.path.dirname(__file__)
IDS = [str(uuid.UUID(int=i + 1)) for i in range(30)]


def _feat(i, lvl, probs):
    x, y = -82.40 + (i % 6) * 2e-4, 35.60 + (i // 6) * 2e-4
    p = {"ncr_id": IDS[i], "centroid": [x, y], "usng_10m": f"17S LV {i}", "damage_level": lvl,
         "damage_probs": probs, "needs_review": lvl == "destroyed", "footprint_image_date": "2023-02-01",
         "fema": {"IMG_DATE": "2025-03-01"},
         "evidence": [{"id": "E1", "available": True, "weight": 1.0, "likelihood": [0, 0, 0.1, 0.2, 0.7]},
                      {"id": "E2", "available": True, "weight": 0.6, "likelihood": [.1, .2, .3, .2, .2],
                       "detail": {"z": 2.4}},
                      {"id": "E5", "available": False, "weight": 1.0, "unavailable_reason": "NO_WSE_SOURCE_ON_REACH"}]}
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]}, "properties": p}


def _write(out, name, role):
    sev = {"no_damage": .05, "affected": .05, "minor": .1, "major": .3, "destroyed": .5}
    ok = {"no_damage": .9, "affected": .05, "minor": .05, "major": 0, "destroyed": 0}
    feats = [_feat(i, "destroyed" if i < 10 else "no_damage", sev if i < 10 else ok) for i in range(30)]
    fc = {"type": "FeatureCollection", "features": feats,
          "properties": {"run_id": "r", "generated_utc": "2026-10-01T00:00:00Z",
                         "event": {"id": "e", "name": "Test flood", "declarations": ["DR-4999-SC"]},
                         "aoi": {"id": name, "role": role, "county": "Greenville"}}}
    (out / f"{name}.geojson").write_text(json.dumps(fc))
    (out / f"{name}.responder.json").write_text(json.dumps(
        {"structures": {IDS[0]: {"address": "12 River Road, Town, 29601"}}}))


@pytest.fixture
def ops(tmp_path, monkeypatch):
    out = tmp_path / "ops"
    out.mkdir()
    for m in (api, owner):
        monkeypatch.setattr(m, "OPS_OUT", str(out))
    monkeypatch.setenv("NCR_TRUTH_DIR", str(tmp_path / "truth"))
    monkeypatch.setenv("NCR_OWNER_REVOKED", str(tmp_path / "revoked.json"))
    monkeypatch.setenv("NCR_OWNER_SECRET", "test-secret")
    monkeypatch.setenv("NCR_AUDIT_LOG", str(tmp_path / "audit.log"))
    monkeypatch.setattr("terratriage.ops.audit.PATH", str(tmp_path / "audit.log"))
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    _write(out, "town", "TUNE")
    _write(out, "heldout", "TEST")
    guard.LIMITER.reset()
    api._cache.clear()
    yield out
    guard.LIMITER.reset()


@pytest.fixture
def client():
    sys.path.insert(0, os.path.join(HERE, ".."))
    import server
    return TestClient(server.app)


def test_links_sign_expire_and_revoke(ops):
    t = owner.issue("town", IDS[0], days=7, now=1_000_000)
    c = owner.verify(t["token"], now=1_000_000 + 86400)
    assert (c["a"], c["b"]) == ("town", IDS[0])
    with pytest.raises(owner.LinkError, match="expired"):
        owner.verify(t["token"], now=1_000_000 + 8 * 86400)
    body, sig = t["token"].split(".")
    forged = owner._b64(json.dumps({"a": "town", "b": IDS[1], "x": 9e12, "j": "0" * 16}).encode())
    with pytest.raises(owner.LinkError):
        owner.verify(f"{forged}.{sig}", now=1_000_000)
    owner.revoke(t["id"])
    with pytest.raises(owner.LinkError, match="withdrawn"):
        owner.verify(t["token"], now=1_000_000)


def test_links_refused_without_a_secret(ops, monkeypatch):
    monkeypatch.delenv("NCR_OWNER_SECRET")
    monkeypatch.delenv("NCR_DEV_OPEN")
    with pytest.raises(owner.LinkError, match="not configured"):
        owner.issue("town", IDS[0])


def test_record_in_plain_words(ops):
    r = owner.record("town", IDS[0])
    assert r["level_label"] == "Destroyed" and r["probability"] == 0.5
    assert r["address"].startswith("12 River Road") and r["state"] == "South Carolina"
    assert r["field_confirmed"] is False and "not been confirmed" in r["disclaimer"]
    says = {e["channel"]: e["says"] for e in r["evidence"]}
    assert says["Flood depth against the first floor"].startswith("Not available: no published river level")
    assert "+2.4 standard deviations" in says["Pixel change inside the outline"]
    assert "not been validated" in r["validation"]


def test_public_answer_is_banded_and_never_names_a_building(ops):
    a = owner.nearby("town", -82.3995, 35.6004)
    assert a["answer"] == "banded" and a["severe_band"] in ("some", "many") and a["any_damage_band"]
    blob = json.dumps(a)
    assert not any(i in blob for i in IDS) and "probab" not in blob
    far = owner.nearby("town", -80.0, 35.0)
    assert far["answer"] == "too_few"


def test_address_match_gives_a_point_only(ops):
    assert owner.find_address("town", "12 river rd") == (-82.40, 35.60)
    assert owner.find_address("town", "River Road") is None      # no house number: no match
    assert owner.find_address("town", "99 Nowhere St") is None


def test_api_link_flow(ops, client):
    r = client.post("/ops/owner/links", json={"area": "town", "ncr_id": IDS[0], "days": 14})
    assert r.status_code == 200 and r.json()["path"].startswith("#/record/")
    tok = r.json()["token"]
    rec = client.post("/ops/owner/record", json={"token": tok})
    assert rec.status_code == 200 and rec.json()["level_label"] == "Destroyed"
    assert client.post("/ops/owner/record", json={"token": tok[:-2] + "xx"}).status_code == 403
    assert client.post("/ops/owner/links/revoke", json={"id": r.json()["id"]}).status_code == 200
    assert client.post("/ops/owner/record", json={"token": tok}).status_code == 403
    log = open(ops.parent / "audit.log", encoding="utf-8").read()
    assert "owner_link_issued" in log and tok not in log


def test_api_issue_needs_responder_token(ops, client, monkeypatch):
    monkeypatch.delenv("NCR_DEV_OPEN")
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret")
    assert client.post("/ops/owner/links", json={"area": "town", "ncr_id": IDS[0]}).status_code == 401


def test_test_areas_are_refused(ops, client):
    assert client.post("/ops/owner/links", json={"area": "heldout", "ncr_id": IDS[0]}).status_code == 409
    assert client.post("/ops/lookup", json={"area": "heldout", "lon": -82.4, "lat": 35.6}).status_code == 409


def test_api_lookup(ops, client):
    r = client.post("/ops/lookup", json={"area": "town", "q": "12 River Road"})
    j = r.json()
    assert r.status_code == 200 and j["answer"] == "banded" and j["center"] == [-82.4, 35.6]
    assert client.post("/ops/lookup", json={"area": "town", "q": "1 Elm St"}).json()["answer"] == "not_found"


def test_index_is_public_and_building_free(ops, client, monkeypatch):
    from terratriage.ops.disseminate import index

    monkeypatch.setattr(index, "OPS_OUT", str(ops))
    lst = client.get("/ops/index").json()
    assert [a["area"] for a in lst["areas"]] == ["town"]          # the TEST area is left out
    r = client.get("/ops/index/town").json()
    assert r["schema"] == "groma.index/1" and r["status"] == "preliminary"
    assert r["damage"]["destroyed"]["expected"] == 5.0
    lo, hi = r["major_or_destroyed"]["range_80"]
    assert lo <= r["major_or_destroyed"]["expected"] <= hi
    assert "preliminary" in r["validation"]
    blob = json.dumps(r)
    assert not any(i in blob for i in IDS) and "River Road" not in blob
    assert client.get("/ops/index/heldout").status_code == 404
