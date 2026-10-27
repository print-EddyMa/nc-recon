"""Security properties of the Groma service, checked offline.

One place that pins down what must stay true as modules change: responder
data fails closed, inputs that reach files or upstream queries are
constrained, outbound fetches stay on their fixed hosts, files are written
atomically, CSV output cannot carry spreadsheet formulas, and every response
carries the browser security headers. See docs/ops/SECURITY.md.
"""
from __future__ import annotations

import io
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

HERE = os.path.dirname(__file__)


@pytest.fixture(scope="module")
def client():
    sys.path.insert(0, os.path.join(HERE, ".."))
    import server

    return TestClient(server.app)


@pytest.fixture(autouse=True)
def _fresh_limiter():
    from terratriage.ops import guard

    guard.LIMITER.reset()
    yield
    guard.LIMITER.reset()


# --------------------------------------------------------------------------- #
# access control: fails closed
# --------------------------------------------------------------------------- #
RESPONDER_GETS = [
    "/ops/areas/old_fort",
    "/ops/areas/old_fort/responder",
    "/ops/areas/old_fort/brief.html",
    "/ops/areas/old_fort/export.zip",
    "/ops/areas/old_fort/ida.zip",
    "/ops/areas/old_fort/references",
    "/ops/labels/old_fort",
    "/ops/photos/old_fort/0000",
    "/ops/photos/old_fort/thumb/0123456789abcdef.jpg",
]


@pytest.mark.parametrize("path", RESPONDER_GETS)
def test_responder_routes_refuse_without_a_configured_token(client, monkeypatch, path):
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    assert client.get(path).status_code == 403


@pytest.mark.parametrize("path", RESPONDER_GETS)
def test_responder_routes_need_the_exact_bearer_token(client, monkeypatch, path):
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret-token")
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get(path, headers={"Authorization": "s3cret-token"}).status_code == 401


def test_writes_refuse_without_a_token(client, monkeypatch):
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    assert client.post("/ops/events/from-fema", json={"disaster_number": 4827}).status_code == 403
    assert client.post("/ops/labels", json={"area": "old_fort", "ncr_id": "x", "label": "minor",
                                            "labeler": "t"}).status_code in (403, 422)


def test_dev_open_refuses_a_public_bind(monkeypatch):
    from terratriage.ops import auth

    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        auth.startup_check("0.0.0.0")
    monkeypatch.delenv("NCR_DEV_OPEN")
    with pytest.raises(SystemExit):
        auth.startup_check("0.0.0.0")          # no token, no dev mode: refuse
    auth.startup_check("127.0.0.1")


# --------------------------------------------------------------------------- #
# inputs that reach files, URLs or upstream queries
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["..%2F..%2Fetc%2Fpasswd", "Old_Fort", "a" * 41, "x;rm"])
def test_area_ids_are_constrained(client, monkeypatch, bad):
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    r = client.get(f"/ops/areas/{bad}")
    assert r.status_code in (400, 404) and "root:" not in r.text


def test_photo_keys_are_constrained(client, monkeypatch, tmp_path):
    from terratriage.ops.collect import cap_photos as cp

    monkeypatch.setattr(cp, "OPS_CACHE", str(tmp_path))
    for bad in ("../../etc/passwd", "0123456789ABCDEF", "0123456789abcde", ""):
        with pytest.raises(ValueError):
            cp.thumb_path(bad)


def test_from_fema_validates_the_number(client, monkeypatch):
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    for body in ({"disaster_number": 0}, {"disaster_number": 100000}, {"disaster_number": "4827 or 1=1"}, {}):
        assert client.post("/ops/events/from-fema", json=body).status_code == 422


def test_lidar_county_cannot_reach_the_where_clause(monkeypatch):
    from terratriage.ops.collect import nc_lidar

    seen = {}

    def fake(url, params=None, timeout=0):
        seen.update(params or {})
        return {"features": []}

    monkeypatch.setattr(nc_lidar, "http_json", fake)
    assert nc_lidar.county_raster("Bun'combe%' OR '1'='1 County") is None
    w = seen["where"]
    assert w == "name like 'Buncombe OR%' and name like '%2025%'"   # quotes, wildcards, '=' dropped


def test_landslide_storm_keyword_is_sanitised(monkeypatch):
    from terratriage.ops.collect import hazard_footprints as hf

    seen = {}

    def fake(url, params):
        seen.update(params)
        return []

    monkeypatch.setattr(hf, "_arcgis_geojson", fake)
    hf.landslides_ncgs((-82.4, 35.5, -82.3, 35.6), "Helene' OR 1=1 --")
    clause = seen["where"].split("AND FeatureType")[0]
    assert clause.count("'") == 2 and "=" not in clause


def test_overpass_queries_are_built_from_numbers_and_fixed_tags():
    from terratriage.ops.collect import osm

    for k, v, _, _ in osm.RESOURCE_TAGS:
        assert all(c.isalnum() or c in "_:" for c in k + v)
    assert all(c.isalnum() or c == "_" for c in "".join(osm.ROAD_CLASSES))


# --------------------------------------------------------------------------- #
# outbound fetches stay on their hosts
# --------------------------------------------------------------------------- #
def _jpeg(w: int, h: int) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (90, 90, 90)).save(buf, "JPEG")
    return buf.getvalue()


class _Resp(io.BytesIO):
    def __init__(self, body: bytes, final: str):
        super().__init__(body)
        self._final = final

    def geturl(self):
        return self._final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_photo_thumbnails_only_come_from_the_cap_host(monkeypatch, tmp_path):
    from terratriage.ops.collect import cap_photos as cp

    monkeypatch.setattr(cp, "OPS_CACHE", str(tmp_path))
    evil = "https://evil.example.com/a.jpg"
    with pytest.raises(KeyError):           # a URL not on the CAP host is never fetched
        cp.thumbnail(cp.key_of(evil), [{"key": cp.key_of(evil), "url": evil}])
    good = cp.HOST + "x/y.jpg"
    monkeypatch.setattr(cp.urllib.request, "urlopen",
                        lambda req, timeout=0: _Resp(_jpeg(64, 48), "https://evil.example.com/redirected.jpg"))
    with pytest.raises(ValueError):         # nor followed off it by a redirect
        cp.thumbnail(cp.key_of(good), [{"key": cp.key_of(good), "url": good}])
    assert not os.listdir(os.path.join(str(tmp_path), "cap_photos", "thumbs"))


def test_photo_thumbnails_cap_pixels_and_leave_no_temp_files(monkeypatch, tmp_path):
    from terratriage.ops.collect import cap_photos as cp

    monkeypatch.setattr(cp, "OPS_CACHE", str(tmp_path))
    monkeypatch.setattr(cp, "MAX_PIXELS", 1000)
    good = cp.HOST + "big.jpg"
    monkeypatch.setattr(cp.urllib.request, "urlopen", lambda req, timeout=0: _Resp(_jpeg(64, 48), good))
    with pytest.raises(ValueError):
        cp.thumbnail(cp.key_of(good), [{"key": cp.key_of(good), "url": good}])
    monkeypatch.setattr(cp, "MAX_PIXELS", 80_000_000)
    p = cp.thumbnail(cp.key_of(good), [{"key": cp.key_of(good), "url": good}])
    d = os.path.dirname(p)
    assert os.listdir(d) == [os.path.basename(p)]


def test_user_agent_carries_no_personal_contact(monkeypatch):
    import importlib

    from terratriage.ops.collect import base

    monkeypatch.delenv("NCR_CONTACT", raising=False)
    importlib.reload(base)
    assert "@" not in base.USER_AGENT


# --------------------------------------------------------------------------- #
# rate limits for routes that make the server call outside
# --------------------------------------------------------------------------- #
def test_upstream_routes_have_their_own_tight_bucket():
    from terratriage.ops import guard

    assert guard.limit_for("GET", "/ops/coverage")[0] == "upstream"
    assert guard.limit_for("GET", "/ops/photos/a/thumb/0123456789abcdef.jpg")[0] == "upstream"
    assert guard.limit_for("GET", "/ops/photos/a/b")[0] == "read"
    assert guard.limit_for("POST", "/ops/labels")[0] == "write"


def test_upstream_bucket_answers_429(client, monkeypatch):
    from terratriage.ops import guard

    monkeypatch.setattr(guard, "UPSTREAM_PER_MIN", 2)
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    codes = [client.get("/ops/coverage?event=nope&lon=-82.4&lat=35.6").status_code for _ in range(3)]
    assert codes[-1] == 429 and 429 not in codes[:2]


# --------------------------------------------------------------------------- #
# output hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("v,out", [
    ("=HYPERLINK(\"http://x\")", "'=HYPERLINK(\"http://x\")"),
    ("+1 555", "'+1 555"), ("-2+3", "'-2+3"), ("@SUM(A1)", "'@SUM(A1)"), ("\tx", "'\tx"),
    ("roof under trees", "roof under trees"), (-3, -3), (0.5, 0.5), (None, None),
    ("-82.401234", "-82.401234"), ("+1e3", "+1e3"), ("-", "'-"),
])
def test_csv_cells_cannot_carry_formulas(v, out):
    from terratriage.ops.guard import csv_cell

    assert csv_cell(v) == out


def test_area_list_ignores_sidecar_files(client, monkeypatch, tmp_path):
    from terratriage.ops import api

    fc = {"type": "FeatureCollection", "properties": {"aoi": {"role": "OPS"}}, "features": []}
    (tmp_path / "town_ab12.geojson").write_text(json.dumps(fc))
    (tmp_path / "town_ab12.response.geojson").write_text(json.dumps(fc))
    (tmp_path / "Bad Name.geojson").write_text(json.dumps(fc))
    monkeypatch.setattr(api, "OPS_OUT", str(tmp_path))
    api._cache.clear()
    r = client.get("/ops/areas")
    assert r.status_code == 200 and [a["id"] for a in r.json()] == ["town_ab12"]
    api._cache.clear()


def test_every_response_carries_the_security_headers(client):
    for path in ("/health", "/ops/areas", "/ops/does-not-exist"):
        h = client.get(path).headers
        csp = h["content-security-policy"]
        assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp and "default-src 'self'" in csp
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer"
    assert client.get("/ops/areas").headers["cache-control"] == "no-store"


def test_cors_does_not_echo_arbitrary_origins(client):
    r = client.get("/ops/areas", headers={"Origin": "https://evil.example.com"})
    assert r.headers.get("access-control-allow-origin") not in ("*", "https://evil.example.com")


# --------------------------------------------------------------------------- #
# storage: caches and label files
# --------------------------------------------------------------------------- #
def test_cache_keys_cannot_escape_the_cache(monkeypatch, tmp_path):
    from terratriage.ops.collect import base

    monkeypatch.setattr(base, "OPS_CACHE", str(tmp_path))
    c = base.DiskCache("t")
    for bad in ("../x", "a/b", "a\\b", "", "x\x00y"):
        with pytest.raises(ValueError):
            c.put(bad, 1)
    c.put("ok_key", {"a": 1})
    assert c.get("ok_key") == {"a": 1}


def test_concurrent_cache_writes_never_collide(monkeypatch, tmp_path):
    import threading

    from terratriage.ops.collect import base

    monkeypatch.setattr(base, "OPS_CACHE", str(tmp_path))
    c = base.DiskCache("t")
    errors = []

    def w(i):
        try:
            for _ in range(20):
                c.put("same", {"i": i})
        except Exception as ex:  # noqa: BLE001
            errors.append(ex)

    ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors and c.get("same")["i"] in range(8)
    assert sorted(os.listdir(c.dir)) == ["same.json"]          # no stray temp files


def test_coverage_needs_the_responder_token(client, monkeypatch):
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    assert client.get("/ops/coverage?event=nope&lon=-82.4&lat=35.6").status_code == 403


def _old_fort_id():
    from terratriage.ops.api import OPS_OUT

    p = os.path.join(OPS_OUT, "old_fort.geojson")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)["features"][0]["properties"]["ncr_id"]


@pytest.mark.skipif(_old_fort_id() is None, reason="no ops output for old_fort")
def test_label_csv_neutralises_formulas(client, monkeypatch):
    import csv

    from terratriage.ops.truth import labels_dir

    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    nid = _old_fort_id()
    r = client.post("/ops/labels", json={"area": "old_fort", "ncr_id": nid, "label": "minor",
                                         "labeler": "=cmd|' /C calc'!A0", "notes": "@SUM(1+1)"})
    assert r.status_code == 200, r.text
    with open(os.path.join(labels_dir(), "old_fort.csv"), encoding="utf-8") as fh:
        row = [x for x in csv.DictReader(fh) if x["ncr_id"] == nid][-1]
    # the name is sanitised on the way in, the note neutralised on the way out
    assert not row["labeler"].startswith(("=", "+", "-", "@")) and row["notes"].startswith("'@")
    assert labels_dir().startswith(os.environ["NCR_LABELS_DIR"])   # never the live labels


def test_evaluation_ignores_sidecar_geojson(monkeypatch, tmp_path):
    from terratriage.ops.analyze import evaluate

    (tmp_path / "old_fort.response.geojson").write_text("{not json")
    monkeypatch.setattr(evaluate, "OPS_OUT", str(tmp_path))
    evaluate._gather({})                                       # would raise on the sidecar


def test_terrain_tiles_are_allowed_only_by_bucket_path():
    from terratriage.ops import guard

    connect = next(d for d in guard.csp(None).split("; ") if d.startswith("connect-src"))
    srcs = connect.split()[1:]
    assert "https://s3.amazonaws.com/elevation-tiles-prod/" in srcs
    assert not any(x in ("https://s3.amazonaws.com", "https://s3.amazonaws.com/", "https://*.amazonaws.com",
                         "https:", "*") for x in srcs)
