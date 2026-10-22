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


def test_cancel_route(client, monkeypatch):
    from terratriage.ops import jobs
    monkeypatch.setattr(jobs, "_jobs", {})
    monkeypatch.setattr(jobs, "_queue", type(jobs._queue)())
    assert client.delete("/ops/assess/nope").status_code == 404
    j = jobs.Job(id="q1", area="town_ab12", event="helene-2024-nc", name="Town", lon=-82.2, lat=35.6, half_m=300)
    jobs._jobs[j.id] = j
    jobs._queue.append(j.id)
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    assert client.delete("/ops/assess/q1").status_code == 403
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    r = client.delete("/ops/assess/q1")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert [x["id"] for x in client.get("/ops/jobs").json()] == ["q1"]


@pytest.mark.skipif(not _have("old_fort"), reason="no ops output for old_fort")
def test_area_summaries_carry_an_extent(client):
    row = next(a for a in client.get("/ops/areas").json() if a["id"] == "old_fort")
    w, s, e, n = row["bbox"]
    assert -84.5 < w < e < -75.4 and 33.7 < s < n < 36.7
    assert e - w < 0.2 and n - s < 0.2            # a town, not the state


@pytest.mark.skipif(not _have("old_fort"), reason="no ops output for old_fort")
def test_slow_health_refresh_does_not_block_labels(client, monkeypatch, tmp_path):
    """A stale board is served at once while the refresh runs in the background,
    and an analyst's label save never waits on it."""
    import threading
    import time

    import terratriage.ops.api as api
    from terratriage.ops.collect import health as h

    out = tmp_path / "ops"
    out.mkdir()
    board = out / "health.json"
    board.write_text(json.dumps({"checked_utc": "2026-01-01T00:00:00Z", "sources": []}))
    old = time.time() - 3600
    os.utime(board, (old, old))
    release, started = threading.Event(), threading.Event()

    def slow_run(write=True):
        started.set()
        release.wait(10)
        board.write_text(json.dumps({"checked_utc": "2026-01-02T00:00:00Z", "sources": []}))
        return []
    monkeypatch.setattr(h, "run", slow_run)
    real_out = api.OPS_OUT
    monkeypatch.setattr(api, "LABELS", str(tmp_path))
    fc = json.loads(client.get("/ops/areas/old_fort").content)
    nid = fc["features"][0]["properties"]["ncr_id"]
    monkeypatch.setattr(api, "OPS_OUT", str(out))
    try:
        t0 = time.time()
        r = client.get("/ops/health")
        assert r.status_code == 200 and r.json()["checked_utc"].startswith("2026-01-01")
        assert r.json()["refreshing"] is True and time.time() - t0 < 2
        assert started.wait(5)
        monkeypatch.setattr(api, "OPS_OUT", real_out)
        t0 = time.time()
        ok = client.post("/ops/labels", json={"area": "old_fort", "ncr_id": nid, "label": "minor", "labeler": "a"})
        assert ok.status_code == 200 and time.time() - t0 < 2
    finally:
        release.set()
        for _ in range(100):
            if not api._health_busy.is_set():
                break
            time.sleep(0.05)
    monkeypatch.setattr(api, "OPS_OUT", str(out))
    assert client.get("/ops/health").json()["checked_utc"].startswith("2026-01-02")


def test_stored_assessments_agree_with_the_county_table():
    """Every configured TUNE / TEST area names its county; the county read off
    its structures' census blocks must be the same one."""
    from terratriage.ops.api import OPS_OUT
    from terratriage.ops.counties import county_of
    from terratriage.ops.plan.events import load_events

    checked = 0
    for ev in load_events().values():
        for aid, aoi in ev.aois.items():
            p = os.path.join(OPS_OUT, f"{aid}.geojson")
            if not aoi.county or not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as fh:
                feats = json.load(fh)["features"]
            assert county_of(f["properties"].get("cbfips_2010") for f in feats) == aoi.county, aid
            checked += 1
    if not checked:
        pytest.skip("no local ops outputs")


def test_reassess_route(client, monkeypatch, tmp_path):
    monkeypatch.setenv("NCR_OPS_REGISTRY", str(tmp_path / "reg.yaml"))
    assert client.post("/ops/areas/nowhere_0000/reassess").status_code == 404
    assert client.post("/ops/areas/old_fort/reassess").status_code == 403       # TUNE area
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    assert client.post("/ops/areas/old_fort/reassess").status_code == 403       # and never without access


def test_public_extent_is_coarse_and_withheld_for_tiny_areas(client, monkeypatch, tmp_path):
    """The extent box is on an unauthenticated endpoint: it must not locate a home."""
    import terratriage.ops.api as api

    def area(name, pts):
        feats = [{"type": "Feature", "geometry": None, "properties": {"ncr_id": f"i{k}", "centroid": list(c)}}
                 for k, c in enumerate(pts)]
        (tmp_path / f"{name}.geojson").write_text(json.dumps({
            "type": "FeatureCollection", "features": feats,
            "properties": {"aoi": {"id": name, "role": "OPS", "county": "McDowell", "name": name}}}))
    area("two_homes", [(-82.123456, 35.654321), (-82.123999, 35.654999)])
    area("village", [(-82.1234567 + k * 1e-4, 35.6543219 + k * 1e-4) for k in range(6)])
    monkeypatch.setattr(api, "OPS_OUT", str(tmp_path))
    rows = {a["id"]: a for a in client.get("/ops/areas").json()}
    assert rows["two_homes"]["bbox"] is None
    w, s, e, n = rows["village"]["bbox"]
    assert (w, s, e, n) == (-82.124, 35.654, -82.122, 35.655)       # snapped outward to 0.001 degree
    for v in (w, s, e, n):
        assert round(v, 3) == v


@pytest.mark.skipif(not _have("old_fort"), reason="no ops output for old_fort")
def test_imagery_tile_route(client, monkeypatch, tmp_path):
    import mercantile

    from terratriage.ops.disseminate import tiles
    monkeypatch.setattr(tiles, "OPS_CACHE", str(tmp_path))
    t = mercantile.tile(-82.1804, 35.6293, 17)
    url = f"/ops/areas/old_fort/tiles/post/{t.z}/{t.x}/{t.y}"
    for bad in ("/ops/areas/old_fort/tiles/post/99/0/0", f"/ops/areas/old_fort/tiles/post/3/{2 ** 3}/0",
                f"/ops/areas/old_fort/tiles/during/{t.z}/{t.x}/{t.y}"):
        assert client.get(bad).status_code == 400
    assert client.get(f"/ops/areas/nowhere_0000/tiles/post/{t.z}/{t.x}/{t.y}").status_code == 404
    r = client.get(url)
    if r.status_code == 404:
        pytest.skip("old_fort imagery is not on disk")
    assert r.status_code == 200 and r.headers["content-type"] in ("image/jpeg", "image/png")
    assert "private" in r.headers["cache-control"] and len(r.content) > 1000
    far = mercantile.tile(-80.0, 35.0, 17)                           # nowhere near the imagery
    blank = client.get(f"/ops/areas/old_fort/tiles/post/{far.z}/{far.x}/{far.y}")
    assert blank.status_code == 200 and blank.headers["content-type"] == "image/png" and len(blank.content) < 200
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret")                # imagery of homes: responder only
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer s3cret"}).status_code == 200


@pytest.mark.skipif(not _have("old_fort"), reason="no ops output for old_fort")
def test_fema_assistance_route(client, monkeypatch):
    from terratriage.ops.analyze import fema_reference
    from terratriage.ops.collect.base import Layer
    from terratriage.ops.provenance import Provenance

    class Src:
        homepage, license = "h", "l"

        def fetch(self, disaster, zip_code):
            return Layer({"zip": zip_code, "disaster_number": disaster, "cities": [],
                          "owners": {"registrations": 10.0, "approved": 6.0, "approved_over_25k": 1.0,
                                     "max_grants": 0.0, "repair_replace_usd": 0.0, "approved_usd": 0.0},
                          "renters": None}, Provenance("x", "y", "z"))
    monkeypatch.setattr(fema_reference, "HousingAssistance", Src)     # never the network in a test
    r = client.get("/ops/areas/old_fort/fema-assistance")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OK" and body["zips"][0]["fema"]["owners"]["approved"] == 6.0
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret")                # ZIPs come from addresses
    assert client.get("/ops/areas/old_fort/fema-assistance").status_code == 401


def test_health_recheck_is_rate_limited(client, monkeypatch, tmp_path):
    import threading
    import time

    import terratriage.ops.api as api
    from terratriage.ops.collect import health as h

    board = tmp_path / "health.json"
    board.write_text(json.dumps({"checked_utc": "2026-01-01T00:00:00Z", "sources": []}))
    monkeypatch.setattr(api, "OPS_OUT", str(tmp_path))
    ran = threading.Event()
    monkeypatch.setattr(h, "run", lambda write=True: ran.set() or [])
    # checked a moment ago: a recheck request is not honoured, so the public
    # endpoint cannot be used to hammer twelve upstream services
    assert client.get("/ops/health?recheck=1").json()["refreshing"] is False and not ran.is_set()
    old = time.time() - 120
    os.utime(board, (old, old))
    assert client.get("/ops/health").json()["refreshing"] is False     # 2 minutes old: still fresh
    assert client.get("/ops/health?recheck=1").status_code == 200
    assert ran.wait(5)
    for _ in range(100):
        if not api._health_busy.is_set():
            break
        time.sleep(0.05)


def test_field_reference_route(client, monkeypatch, tmp_path):
    import terratriage.ops.api as api
    monkeypatch.setattr(api, "OPS_OUT", str(tmp_path))
    (tmp_path / "zz_area.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [],
                                                           "properties": {"aoi": {"role": "TUNE"}}}))
    assert client.get("/ops/areas/zz_area/field-reference").status_code == 404
    (tmp_path / "zz_area.sarcop_reference.json").write_text(json.dumps({"summary": {"n": 1}, "pairs": [{"ncr_id": "x"}]}))
    r = client.get("/ops/areas/zz_area/field-reference")
    assert r.status_code == 200 and r.json()["summary"]["n"] == 1 and "pairs" not in r.json()
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret")
    assert client.get("/ops/areas/zz_area/field-reference").status_code == 401
