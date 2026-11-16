"""Conditions-map feeds composed by the server from ArcGIS services (FIMAN
gauges, Duke Energy outages, FEMA shelters), against dated fixtures."""
import copy
import json
import os

import pytest

from terratriage.ops.collect import nc_feeds

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def served(monkeypatch):
    """Route http_json to a fixture chosen by the service URL."""
    calls = []

    def fake(url, params=None, **kw):
        calls.append((url, params))
        if url == nc_feeds.FIMAN:
            return _load("fiman_gages_2026-10-07.geojson")
        if url == nc_feeds.DUKE:
            return _load("duke_outages_2026-10-07.geojson")
        if url == nc_feeds.SHELTERS:
            d = copy.deepcopy(_load("fema_shelters_2026-10-07.geojson"))
            # the live list had no NC shelter that night; move one into Marion
            d["features"][0]["geometry"]["coordinates"] = [-82.009, 35.684]
            d["features"][0]["properties"].update({"state": "NC", "city": "Marion", "total_population": 42,
                                                   "post_impact_capacity": 200})
            return d
        raise AssertionError(url)

    monkeypatch.setattr(nc_feeds, "http_json", fake)
    return calls


def test_fiman_gauges_shape_and_order(served):
    fc = nc_feeds.fiman_gauges()
    assert fc["type"] == "FeatureCollection" and fc["generated"] > 0
    feats = fc["features"]
    assert len(feats) == 6
    sevs = [f["properties"]["severity"] for f in feats]
    assert sevs == sorted(sevs, reverse=True) and max(sevs) == 1   # three "near flooding" gauges first
    p = feats[0]["properties"]
    assert p["layer"] == "fiman" and p["id"].startswith("fiman-") and p["category"] == "Near flooding"
    assert "stage" in p["detail"] and "thresholds" in p["detail"] and p["url"].startswith("https://")
    assert "water.weather.gov" not in p["url"]                      # dead AHPS links are not passed through
    assert served[0][1]["where"] == "IN_SERVICE=1" and served[0][1]["f"] == "geojson"


def test_fiman_severity_mapping():
    assert [nc_feeds._fiman_severity(c) for c in (None, 0, 1, 2, 3, 4)] == [-1, 0, 1, 2, 3, 3]


def test_duke_outages_only_counties_with_customers_out(served):
    fc = nc_feeds.duke_outages()
    assert fc["totals"] == {"customers_out": 3200, "customers_served": 10000, "counties_out": 1}
    (f,) = fc["features"]
    p = f["properties"]
    assert p["layer"] == "power" and p["title"] == "Iredell County: 3,200 customers out"
    assert p["severity"] == 2 and p["percent_out"] == 32 and "estimated restoration" in p["detail"]
    assert f["geometry"]["type"] in ("Polygon", "MultiPolygon")
    from terratriage.ops.geodesy import NC_BBOX
    assert served[0][1]["geometry"] == ",".join(str(v) for v in NC_BBOX)   # NC envelope filter on the query


def test_fema_shelters_keep_only_nc_points(served):
    fc = nc_feeds.fema_shelters()
    (f,) = fc["features"]
    p = f["properties"]
    assert p["layer"] == "shelter" and p["value"] == "42 sheltered" and "capacity 200" in p["detail"]
    assert "Marion" in p["detail"]
    assert served[0][1]["where"] == "state='NC'"


def test_arcgis_pagination(monkeypatch):
    pages = [{"type": "FeatureCollection", "features": [{"i": k} for k in range(2)]},
             {"type": "FeatureCollection", "features": [{"i": 2}]}]
    seen = []

    def fake(url, params=None, **kw):
        seen.append(params["resultOffset"])
        return pages[len(seen) - 1]

    monkeypatch.setattr(nc_feeds, "http_json", fake)
    out = nc_feeds._arcgis_features("https://x/arcgis/rest/services/a/FeatureServer/0/query", {}, page=2)
    assert [f["i"] for f in out] == [0, 1, 2] and seen == [0, 2]


def test_arcgis_bad_body(monkeypatch):
    monkeypatch.setattr(nc_feeds, "http_json", lambda *a, **k: {"error": {"code": 400}})
    with pytest.raises(nc_feeds.SchemaError):
        nc_feeds._arcgis_features("https://x/arcgis/rest/services/a/FeatureServer/0/query", {})


def test_server_routes_new_feeds(monkeypatch):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import server
    from fastapi.testclient import TestClient

    monkeypatch.setattr(nc_feeds, "fiman_gauges", lambda: {"type": "FeatureCollection", "features": [], "generated": 1})
    server._FEED_CACHE.pop("fiman", None)
    r = TestClient(server.app).get("/feed/fiman")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    assert r.json()["generated"] == 1
