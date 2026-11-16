"""Civil Air Patrol photos for Verify reviewers (collect/cap_photos.py,
ops/photos_api.py), against a dated fixture of the real Swannanoa rows."""
import io
import json
import os
from datetime import date

import pytest

from terratriage.ops.collect import cap_photos as cp

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "cap_photos_swannanoa_2026-10-22.json")


def _raw():
    with open(FIX, encoding="utf-8") as fh:
        return json.load(fh)


class _NoCache:
    def get(self, key, max_age_s=None):
        return None

    def put(self, key, value):
        pass


@pytest.fixture
def served(monkeypatch):
    raw = _raw()
    monkeypatch.setattr(cp, "DiskCache", lambda ns: _NoCache())

    def fake(url, params=None, **kw):
        assert url.startswith(cp.BASE) and "H-TS Helene 2024" in params["where"]
        layer = int(url.rsplit("/", 2)[-2])
        kind = "oblique" if layer == cp.LAYERS["oblique"] else "nadir"
        return {"features": [{"attributes": a} for a in raw[kind]]}

    monkeypatch.setattr(cp, "http_json", fake)
    return raw


def test_capture_date_falls_back_to_folder_when_exif_is_bogus():
    url = cp.HOST + "Images/X/Source/m/A0046B_Aerial_Nadir/20241004T014015Z/0_000_01_049.jpg"
    assert cp.capture_date(946696995000, url) == date(2024, 10, 4)      # EXIF says 2000-01-01
    assert cp.capture_date(1727545883000, url) == date(2024, 9, 28)     # plausible EXIF wins
    assert cp.capture_date(None, cp.HOST + "no/date/here.jpg") is None


def test_points_keep_dated_cap_frames_only(served):
    bx, by = served["_building"]
    pts = cp.points("helene-2024-nc", (bx, by, bx, by), date(2024, 9, 25))
    assert pts and all(p["url"].startswith(cp.HOST) for p in pts)
    assert {p["kind"] for p in pts} == {"oblique", "nadir"}
    assert min(p["date"] for p in pts) >= "2024-09-25"
    assert cp.points("some-other-event", (bx, by, bx, by)) == []


def test_near_the_real_building_returns_pointing_obliques(served):
    bx, by = served["_building"]
    out = cp.near(bx, by, cp.points("helene-2024-nc", (bx, by, bx, by), date(2024, 9, 25)))
    obl = [p for p in out if p["kind"] == "oblique"]
    assert 1 <= len(obl) <= 3
    assert all(cp.OBLIQUE_M[0] <= p["dist_m"] <= cp.OBLIQUE_M[1] for p in obl)
    assert all(0.0 <= p["x_frac"] <= 1.0 for p in obl)
    assert [p["dist_m"] for p in obl] == sorted(p["dist_m"] for p in obl)


def _pt(dx_m, dy_m, heading, t=0, mission="m1", kind="oblique", focal=65):
    lon0, lat0 = -82.4, 35.6
    import math
    return {"kind": kind, "lon": lon0 - dx_m / (111320 * math.cos(math.radians(lat0))), "lat": lat0 - dy_m / 110540,
            "url": cp.HOST + f"x/{t}.jpg", "date": "2024-09-28", "heading": heading, "focal_mm": focal,
            "mission": mission, "t": t, "key": cp.key_of(cp.HOST + f"x/{t}.jpg")}


def test_near_geometry_bearing_distance_and_bursts():
    b = (-82.4, 35.6)
    facing = _pt(0, 800, 0, t=1)                 # 800 m south, looking north: in view, centred
    away = _pt(0, 800, 90, t=100_000)            # looking east: out of view
    close = _pt(0, 100, 0, t=200_000)            # too close for an oblique
    burst = _pt(5, 800, 0, t=5_000)              # same burst as `facing`
    other = _pt(300, 900, 0, t=900_000, mission="m2")   # off to the side, still inside a 31 degree lens
    out = cp.near(*b, [away, close, burst, facing, other])
    keys = [p["key"] for p in out]
    assert facing["key"] in keys or burst["key"] in keys
    assert not (facing["key"] in keys and burst["key"] in keys)
    assert away["key"] not in keys and close["key"] not in keys
    centred = next(p for p in out if p["key"] in (facing["key"], burst["key"]))
    assert abs(centred["x_frac"] - 0.5) < 0.05
    nadir = _pt(50, 50, -1, t=1, kind="nadir")
    assert cp.near(*b, [nadir])[0]["kind"] == "nadir"
    assert cp.near(*b, [_pt(400, 0, -1, kind="nadir")]) == []


def test_thumbnail_only_fetches_known_cap_frames(monkeypatch, tmp_path):
    from PIL import Image

    monkeypatch.setattr(cp, "OPS_CACHE", str(tmp_path))
    with pytest.raises(ValueError):
        cp.thumbnail("../../etc/passwd", [])
    with pytest.raises(KeyError):
        cp.thumbnail("0123456789abcdef", [])
    url = cp.HOST + "a/b.jpg"
    buf = io.BytesIO()
    Image.new("RGB", (4000, 3000), (120, 90, 60)).save(buf, "JPEG")

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    seen = []
    monkeypatch.setattr(cp.urllib.request, "urlopen", lambda req, timeout=0: seen.append(req.full_url) or R(buf.getvalue()))
    p = cp.thumbnail(cp.key_of(url), [{"key": cp.key_of(url), "url": url}])
    assert seen == [url] and max(Image.open(p).size) == cp.THUMB_PX
    cp.thumbnail(cp.key_of(url), [{"key": cp.key_of(url), "url": url}])
    assert seen == [url]                                   # cached


def test_photo_routes(monkeypatch, tmp_path):
    import sys

    from fastapi.testclient import TestClient

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import server
    import terratriage.ops.api as api
    import terratriage.ops.photos_api as papi

    monkeypatch.delenv("TERRATRIAGE_TOKEN", raising=False)
    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    monkeypatch.setattr(api, "OPS_OUT", str(tmp_path))
    bx, by = -82.4, 35.6                      # where _pt's cameras are laid out
    fc = {"type": "FeatureCollection", "properties": {"aoi": {"role": "TUNE", "name": "Z", "county": "Buncombe"}},
          "features": [{"type": "Feature", "geometry": None,
                        "properties": {"ncr_id": "abc", "centroid": [bx, by], "cbfips_2010": "370210001001000"}}]}
    (tmp_path / "zz_area.geojson").write_text(json.dumps(fc))
    pts = [_pt(0, 800, 0, t=1)]
    monkeypatch.setattr(papi, "_area_points", lambda area, fc: (pts, None))
    c = TestClient(server.app)
    r = c.get("/ops/photos/zz_area/abc")
    assert r.status_code == 200
    j = r.json()
    assert j["photos"] and "damage_level" not in json.dumps(j) and "probs" not in json.dumps(j)
    assert c.get("/ops/photos/zz_area/nope").status_code == 404
    assert c.get("/ops/photos/zz_area/thumb/0123456789abcdef.jpg").status_code == 404
    assert c.get("/ops/photos/zz_area/thumb/NOTHEX.jpg").status_code == 400
    monkeypatch.delenv("NCR_DEV_OPEN", raising=False)
    monkeypatch.setenv("TERRATRIAGE_TOKEN", "s3cret")
    assert c.get("/ops/photos/zz_area/abc").status_code == 401


@pytest.mark.live
def test_live_probe():
    assert cp.CAPPhotos().health().status == "ok"
