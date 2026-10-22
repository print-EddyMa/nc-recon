"""Response products (ops/response/): offline, on a synthetic town."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from terratriage.ops.response import AreaRun, access, landing, money, resources, sectors
from terratriage.ops.response_api import plan_kml

LON0, LAT0 = -82.40, 35.60
DLON, DLAT = 0.001 / 0.9, 0.0009   # about 100 m each way


def _bld(i, lon, lat, level, occ=3, residential=True, area=150.0):
    probs = {k: 0.0 for k in ("no_damage", "affected", "minor", "major", "destroyed")}
    probs[level] = 1.0
    d = 0.00005
    ring = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"ncr_id": f"b{i}", "centroid": [lon, lat], "damage_level": level, "damage_probs": probs,
                           "occupants": {"nsi_estimate": occ}, "usng_1m": f"17S LV 7{i % 2}000 40000",
                           "flags": {"residential": residential, "manufactured_home": False},
                           "area_m2": area, "stories": 1, "source_ids": {"nsi_fd_id": 100 + i},
                           "needs_review": level == "destroyed"}}


@pytest.fixture
def town():
    # a main road west-east through the town; a spur north over a bridge to a hamlet
    feats = [_bld(0, LON0, LAT0 + 0.0002, "destroyed"), _bld(1, LON0 + 2 * DLON, LAT0 + 0.0002, "no_damage"),
             _bld(2, LON0 + DLON, LAT0 + 6 * DLAT, "major", occ=5)]
    ev = SimpleNamespace(id="test-flood", hazards=("riverine_flood",), incident_begin=date(2025, 10, 5),
                         state="NC")
    ar = AreaRun("testtown", feats, {"aoi": {"county": "Buncombe"}}, ev,
                 (LON0, LAT0, LON0 + 2 * DLON, LAT0 + 6 * DLAT))
    main = [(LON0 - 60 * DLON + k * DLON, LAT0) for k in range(0, 121)]
    spur = [(LON0 + DLON, LAT0 + k * DLAT) for k in range(0, 7)]
    ways = [{"id": "way/1", "highway": "primary", "name": "Main", "bridge": False, "oneway": False, "access": None,
             "coords": main},
            {"id": "way/2", "highway": "residential", "name": "Spur", "bridge": False, "oneway": False,
             "access": None, "coords": spur[:3]},
            {"id": "way/3", "highway": "residential", "name": "Spur bridge", "bridge": True, "oneway": False,
             "access": None, "coords": spur[2:4]},
            {"id": "way/4", "highway": "residential", "name": "Spur", "bridge": False, "oneway": False,
             "access": None, "coords": spur[3:]}]
    return ar, ways


def test_access_scenarios_separate_known_blocks_from_bridges(town, monkeypatch):
    ar, ways = town
    monkeypatch.setattr(access.osm, "roads", lambda box: ways)
    monkeypatch.setattr(access.osm, "resources", lambda box: [])
    r = access.analyse(ar, pad_km=0.5, resources=[{"kind": "hospital", "name": "H", "id": "n/1",
                                                     "lon": LON0 - 50 * DLON, "lat": LAT0}])
    sc = r["scenarios"]
    assert sc["known_blocks"]["isolated_buildings"] == 0
    assert sc["worst_case"]["isolated_buildings"] == 1          # the hamlet over the bridge
    assert sc["worst_case"]["isolated_people_est"] == 5
    assert r["roads"]["bridge"] >= 1
    assert r["isolated_clusters"] and r["isolated_clusters"][0]["buildings"] == 1
    t = r["per_building"]["b1"]["known_blocks"]["min_to_hospital"]
    assert t is not None and 1 < t < 15


def test_landslide_on_the_road_cuts_off_the_hamlet(town, monkeypatch):
    from shapely.geometry import box

    ar, ways = town
    monkeypatch.setattr(access.osm, "roads", lambda b: ways)
    monkeypatch.setattr(access.osm, "resources", lambda b: [])
    slide = box(LON0 + DLON - 0.0002, LAT0 + 4.5 * DLAT, LON0 + DLON + 0.0002, LAT0 + 4.8 * DLAT)
    r = access.analyse(ar, pad_km=0.5, landslide_polys_ll=[slide], resources=[])
    assert r["roads"]["blocked"] >= 1
    assert r["scenarios"]["known_blocks"]["isolated_buildings"] == 1


def test_facility_status_and_lifeline_colours(town):
    ar, _ = town
    facs = [{"id": "n/9", "kind": "fire_station", "lifeline": "safety_security", "name": "Station 1",
             "lon": LON0 + 0.00003, "lat": LAT0 + 0.0002},
            {"id": "n/8", "kind": "grocery", "lifeline": "food_water_shelter", "name": "Market",
             "lon": LON0 + 2 * DLON, "lat": LAT0 + 0.0002},
            {"id": "n/7", "kind": "school", "lifeline": "food_water_shelter", "name": "Far School",
             "lon": LON0 + 0.05, "lat": LAT0 + 0.05}]
    res = resources.assess(ar, facs, {"n/8": {"known_blocks": {"access": "connected"},
                                               "plus_debris": {"access": "isolated"}}}, {})
    by = {f["id"]: f for f in res["facilities"]}
    assert by["n/9"]["status"] == "disrupted"            # beside a destroyed building
    assert by["n/8"]["status"] == "at_risk"              # cut off only if debris blocks roads
    assert by["n/7"]["status"] == "not_assessed"
    ll = {x["lifeline"]: x["status"] for x in res["lifelines"]}
    assert ll["safety_security"] == "red" and ll["food_water_shelter"] == "yellow"
    assert ll["water_systems"] == "grey"                 # nothing found is unknown, never green


def test_money_uses_level_ranges_and_fema_debris(town, monkeypatch):
    ar, _ = town
    monkeypatch.setattr(money, "county_population", lambda s, c: 279210)
    vals = {100: (200000.0, 100000.0), 101: (200000.0, 100000.0), 102: (100000.0, 50000.0)}
    m = money.estimate(ar, vals)
    # destroyed 300k x 50-100% + major 150k x 25-50%
    assert m["building_loss_usd"]["low"] == round(300000 * 0.5 + 150000 * 0.25, -3)
    assert m["building_loss_usd"]["high"] == round(300000 * 1.0 + 150000 * 0.5, -3)
    ft2 = 150 * money.SQFT_PER_M2
    assert m["debris_cy"]["low"] == round(ft2 * 0.20 * 1.1 + 25, -1)       # destroyed home + flood Major curbside
    assert m["public_assistance_threshold"]["fiscal_year"] == 2026
    assert m["public_assistance_threshold"]["county_threshold_usd"] == round(279210 * 4.86)


def test_sectors_rank_by_people_in_severe_buildings_and_needs(town):
    ar, _ = town
    sec = sectors.sectors(ar)
    assert [s["priority"] for s in sec] == list(range(1, len(sec) + 1))
    assert sec[0]["people_in_severe_expected"] >= sec[-1]["people_in_severe_expected"]
    n = sectors.needs(1000, 200)
    assert n["water_litres_per_day"] == 3600 and n["meals_per_day"] == 2400
    assert n["distribution_points"] == [{"type": "Type III", "count": 1, "people_per_day_each": 5000}]
    assert sectors.needs(26000, 0)["distribution_points"][0]["type"] == "Type I"


def test_landing_finds_open_flat_ground_and_avoids_slopes(town, monkeypatch):
    ar, _ = town

    def dem(bounds, epsg, W, H):
        z = np.zeros((H, W), "float32")
        z[:, W // 2:] = np.arange(W - W // 2, dtype="float32")[None, :] * 5.0   # east half: 26 deg slope
        return z

    monkeypatch.setattr(landing, "_dem", dem)
    monkeypatch.setattr(landing, "_cover", lambda b, e, W, H, c: np.full((H, W), 30, "uint8"))
    r = landing.candidates(ar, pad_km=0.6, targets=[{"lon": LON0, "lat": LAT0, "label": "x", "weight": 1}])
    assert r["candidates"]
    assert all(c["slope_deg"] <= 7.0 for c in r["candidates"])
    assert all(c["lon"] < LON0 + 0.02 for c in r["candidates"])
    assert any("CH-47" in c["fits"] for c in r["candidates"])


def test_plan_kml_is_wellformed_and_escapes_names():
    import xml.etree.ElementTree as ET

    d = {"area": "a&b", "disclaimer": "decision support",
         "sectors": [{"priority": 1, "usng_1km": "17S LV 73 40", "center": [LON0, LAT0],
                      "major_or_destroyed_expected": 2.0, "people_in_severe_expected": 3.0, "cut_off_people": 0.0,
                      "buildings": 4, "review_share": 0.5}],
         "landing": {"candidates": [{"usng": "17S LV 7000 4000", "lon": LON0, "lat": LAT0, "clear_diameter_m": 90,
                                     "slope_deg": 2.0, "cover": "grassland", "fits": ["UH-60", "CH-47"]}]},
         "access": {"isolated_clusters": []},
         "resources": {"facilities": [{"name": "Tom's <Store>", "kind": "grocery", "status": "at_risk",
                                       "reasons": ["x"], "lon": LON0, "lat": LAT0}]}}
    root = ET.fromstring(plan_kml(d))
    names = [e.text for e in root.iter("{http://www.opengis.net/kml/2.2}name")]
    assert "Tom's <Store> (at risk)" in names and any(n.startswith("LZ 1") for n in names)


def test_routes_serve_stored_products_and_kml(tmp_path, monkeypatch):
    import json

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from terratriage.ops import api, response_api

    monkeypatch.setenv("NCR_DEV_OPEN", "1")
    monkeypatch.setattr(api, "OPS_OUT", str(tmp_path))
    monkeypatch.setattr(response_api, "OPS_OUT", str(tmp_path))
    (tmp_path / "town.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": [], "properties": {"aoi": {"id": "town", "name": "Town"}}}))
    app = FastAPI()
    app.include_router(response_api.router)
    c = TestClient(app)
    assert c.get("/ops/areas/town/response").status_code == 404           # not built yet
    assert c.get("/ops/areas/town/response/status").json()["built"] is False
    doc = {"area": "town", "disclaimer": "d", "summary": {}, "sectors": [], "landing": None,
           "access": None, "resources": None}
    (tmp_path / "town.response.json").write_text(json.dumps(doc))
    (tmp_path / "town.response.layers.json").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    assert c.get("/ops/areas/town/response").json()["area"] == "town"
    assert c.get("/ops/areas/town/response/layers").json()["type"] == "FeatureCollection"
    k = c.get("/ops/areas/town/response/plan.kml")
    assert k.status_code == 200 and k.text.startswith("<?xml") and "attachment" in k.headers["content-disposition"]
    assert c.get("/ops/areas/bad..id/response").status_code in (400, 404)


def test_water_systems_and_private_wells(town):
    from shapely.geometry import box

    from terratriage.ops.response import water

    ar, _ = town
    # the system covers the main street, not the hamlet to the north
    sys_ = [{"pwsid": "NC0000001", "name": "Town water", "population_served": 900, "boundary": "Verified",
             "_geom": box(LON0 - 0.01, LAT0 - 0.01, LON0 + 0.01, LAT0 + 3 * DLAT)}]
    w = water.assess(ar, sys_, [{"kind": "wastewater_discharger", "status": "disrupted", "name": "Plant",
                                 "lon": LON0, "lat": LAT0}])
    s = w["systems"][0]
    assert s["buildings_assessed_inside"] == 2 and s["status"] == "at_risk"
    assert any("flood event" in r for r in s["reasons"]) and s["flagged_facilities"]
    assert w["private_wells"]["residential_buildings"] == 1          # the hamlet
    assert "test wells" in w["private_wells"]["advice"]


def test_official_records_win_over_osm_duplicates():
    from terratriage.ops.response.build import _merge

    off = [{"id": "hospital/1", "kind": "hospital", "lon": LON0, "lat": LAT0, "source": "FEMA"}]
    osm_ = [{"id": "way/2", "kind": "hospital", "lon": LON0 + 0.0005, "lat": LAT0},          # ~45 m away
            {"id": "node/3", "kind": "hospital", "lon": LON0 + 0.01, "lat": LAT0},           # ~900 m away
            {"id": "node/4", "kind": "pharmacy", "lon": LON0, "lat": LAT0}]
    ids = [f["id"] for f in _merge(off, osm_)]
    assert ids == ["hospital/1", "node/3", "node/4"]
