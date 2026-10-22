"""Channel H (hazard footprints), ShakeMap grids, ArcGIS paging, NAIP upsampling,
field-reference adapters and the NSI fallback placement (offline)."""
from __future__ import annotations

import ast
import json
import os

import numpy as np
import pytest
from shapely.geometry import Polygon, box

from terratriage.ops.analyze import field_reference as fr
from terratriage.ops.analyze import hazard_prior as hp
from terratriage.ops.analyze.classes import FEMA
from terratriage.ops.collect import hazard_footprints as hf
from terratriage.ops.collect import nc_orthos
from terratriage.ops.provenance import Provenance

PROV = Provenance(source="test", source_url="test://", license="test")
D = FEMA.index("destroyed")
N = FEMA.index("no_damage")


def _ctx(**projected):
    ctx = hp.HazardContext()
    for h, g in projected.items():
        ctx.footprints[h] = hf.Footprint(h, PROV, geom=g)
        ctx.projected[h] = g
    return ctx


def test_wildfire_inside_outside_and_edge():
    perim = box(0, 0, 1000, 1000)
    ctx = _ctx(wildfire=perim)
    inside = hp.channel(ctx, hp.measure(ctx, box(400, 400, 420, 420), (0, 0)))
    far = hp.channel(ctx, hp.measure(ctx, box(1300, 0, 1320, 20), (0, 0)))
    near = hp.channel(ctx, hp.measure(ctx, box(1030, 0, 1050, 20), (0, 0)))
    assert inside.available and inside.likelihood[D] > inside.likelihood[N]
    assert far.available and far.likelihood[N] > 0.5 and "H_OUTSIDE_FIRE_PERIMETER_300M" in far.reasons
    # inside the mapping-uncertainty band: recorded, but carries no weight
    assert near.weight == 0.0 and near.reasons == ["H_NEAR_FIRE_PERIMETER_30M"]


def test_landslide_only_counts_inside():
    ctx = _ctx(landslide=box(0, 0, 50, 50))
    hit = hp.channel(ctx, hp.measure(ctx, box(40, 40, 60, 60), (0, 0)))
    miss = hp.channel(ctx, hp.measure(ctx, box(200, 200, 210, 210), (0, 0)))
    assert hit.available and hit.likelihood[D] > hit.likelihood[N] and "H_IN_MAPPED_LANDSLIDE" in hit.reasons
    assert miss.weight == 0.0                     # outside an incomplete inventory is not evidence


def test_unavailable_and_not_applicable():
    assert hp.channel(None, None).unavailable_reason == "NOT_APPLICABLE_FOR_HAZARD"
    ctx = hp.HazardContext(unavailable={"wildfire": "NO_FOOTPRINT_IN_AREA"})
    ch = hp.channel(ctx, hp.measure(ctx, box(0, 0, 1, 1), (0, 0)))
    assert not ch.available and "wildfire: NO_FOOTPRINT_IN_AREA" in ch.unavailable_reason


GRID = """<?xml version="1.0"?>
<shakemap_grid xmlns="http://earthquake.usgs.gov/eqcenter/shakemap" event_id="x">
<grid_specification lon_min="-120.0" lat_min="34.0" lon_max="-119.0" lat_max="35.0"
  nominal_lon_spacing="0.5" nominal_lat_spacing="0.5" nlon="3" nlat="3"/>
<grid_field index="1" name="LON" units="dd"/>
<grid_field index="2" name="LAT" units="dd"/>
<grid_field index="3" name="MMI" units="intensity"/>
<grid_data>
-120.0 35.0 5.0 -119.5 35.0 6.0 -119.0 35.0 7.0
-120.0 34.5 6.0 -119.5 34.5 7.0 -119.0 34.5 8.0
-120.0 34.0 7.0 -119.5 34.0 8.0 -119.0 34.0 9.0
</grid_data>
</shakemap_grid>"""


def test_shakemap_grid_and_mmi_bins():
    g = hf.ShakeGrid.parse(GRID)
    assert g.at(-120.0, 35.0) == pytest.approx(5.0)
    assert g.at(-119.25, 34.25) == pytest.approx(8.0)      # bilinear between four corners
    assert g.at(-121.0, 34.5) is None                        # off the grid
    ctx = hp.HazardContext()
    ctx.footprints["earthquake"] = hf.Footprint("earthquake", PROV, grid=g)
    weak = hp.channel(ctx, hp.measure(ctx, box(0, 0, 1, 1), (-120.0, 35.0)))
    strong = hp.channel(ctx, hp.measure(ctx, box(0, 0, 1, 1), (-119.0, 34.0)))
    assert weak.likelihood[N] > strong.likelihood[N] and strong.likelihood[D] > weak.likelihood[D]


def test_arcgis_paging_fetches_every_page(monkeypatch):
    calls = []

    def fake(url, params, timeout):
        calls.append(params["resultOffset"])
        n = 1000 if params["resultOffset"] == 0 else 457
        return {"features": [{"id": params["resultOffset"] + i} for i in range(n)]}

    monkeypatch.setattr(hf, "http_json", fake)
    feats = hf._arcgis_geojson("test://layer/query", {"where": "1=1"})
    assert len(feats) == 1457 and calls == [0, 1000]


def test_naip_is_fetched_coarse_and_upsampled(monkeypatch):
    seen = []

    def fake_at(service, bounds, epsg, res):
        seen.append(res)
        h, w = nc_orthos._shape(bounds, res)
        return np.full((3, h, w), 7, dtype="uint8")

    monkeypatch.setattr(nc_orthos, "export_window_at", fake_at)
    arr = nc_orthos.export_window("naip", (0.0, 0.0, 60.0, 30.0), 6340, 0.3)
    assert seen == [0.6] and arr.shape == (3, 100, 200) and int(arr.max()) == 7


def test_dins_adapter_maps_levels_and_drops_other_fires(monkeypatch):
    class Ev:
        from datetime import date
        incident_begin = date(2025, 1, 7)
    t0 = 1736208000000  # 2025-01-07 UTC
    rows = [
        {"attributes": {"OBJECTID": 1, "DAMAGE": "Destroyed (>50%)", "STRUCTURETYPE": "Single Family Residence Single Story",
                        "INCIDENTNAME": "Eaton", "INCIDENTSTARTDATE": t0 + 3600_000}, "geometry": {"x": -118.1, "y": 34.2}},
        {"attributes": {"OBJECTID": 2, "DAMAGE": "No Damage", "STRUCTURETYPE": "Utility Misc Structure",
                        "INCIDENTNAME": "Eaton", "INCIDENTSTARTDATE": t0}, "geometry": {"x": -118.1, "y": 34.2}},
        {"attributes": {"OBJECTID": 3, "DAMAGE": "Destroyed (>50%)", "STRUCTURETYPE": "Mobile Home Single Wide",
                        "INCIDENTNAME": "Old fire", "INCIDENTSTARTDATE": t0 - 400 * 86400_000},
         "geometry": {"x": -118.1, "y": 34.2}},
    ]
    monkeypatch.setattr(fr, "_page", lambda url, params: rows)
    pts = fr.fetch_dins((-118.2, 34.1, -118.0, 34.3), Ev())
    assert [(p["id"], p["waypoint"], p["program_type"]) for p in pts] == [
        (1, "destroyed", "single_family"), (2, "unaffected", None)]


def test_field_reference_refuses_test_areas_and_pairs_dins(tmp_path, monkeypatch):
    from datetime import date

    from terratriage.ops.plan import events as evmod

    class Ev:
        id, hazards, state, declarations = "fire-x", ("wildfire",), "CA", ()
        incident_begin = date(2025, 1, 7)

    ring = [[-118.10, 34.20], [-118.0999, 34.20], [-118.0999, 34.2001], [-118.10, 34.2001], [-118.10, 34.20]]
    fc = {"type": "FeatureCollection", "properties": {"run_id": "r", "aoi": {"role": "TEST", "county": "LA"}},
          "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                        "properties": {"ncr_id": "a", "damage_level": "destroyed", "needs_review": False,
                                       "damage_probs": {"destroyed": 0.9, "major": 0.1}}}]}
    monkeypatch.setattr(fr, "OPS_OUT", str(tmp_path))
    (tmp_path / "x.geojson").write_text(json.dumps(fc))
    monkeypatch.setattr(evmod, "event_for_area", lambda a: (Ev(), None))
    monkeypatch.setenv("NCR_DATA_DIR_CACHE_BUST", "1")
    pts = [{"id": 1, "lon": -118.09995, "lat": 34.20005, "category": "structure", "waypoint": "destroyed",
            "program_type": "single_family", "t": 1}]
    with pytest.raises(SystemExit):
        fr.compare_area("x", "dins", write=False, fetch=lambda b, e: pts)
    r = fr.compare_area("x", "dins", allow_test=True, write=False, fetch=lambda b, e: pts)
    assert r["counts"]["matched"] == 1 and r["summary"]["same_level"] == 1.0
    assert any("hold-out" in c for c in r["caveats"])


def test_e6_lidar_flag_is_evidence_and_no_flag_is_not():
    from terratriage.ops.analyze import channels
    from terratriage.ops.analyze.ground_change import LIKELIHOOD

    stats = {"median_m": 0.1, "p10_m": -0.2, "p90_m": 1.8}
    dep = channels.e6(stats, "deposit", LIKELIHOOD)
    none = channels.e6(stats, None, LIKELIHOOD)
    assert dep.available and dep.weight > 0 and dep.likelihood[D] > dep.likelihood[N]
    assert none.available and none.weight == 0.0
    assert not channels.e6(None, None, LIKELIHOOD).available


def test_nsi_fallback_stays_in_its_except_block():
    """Regression (2026-10-22): the NSI 'unavailable' fallback once sat after the
    E5 block, so every normal run dropped all NSI data. It must only run when
    the NSI fetch raised."""
    path = os.path.join(os.path.dirname(fr.__file__), "..", "pipeline.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple):
            names = [getattr(t, "id", None) for t in node.targets[0].elts]
            if names == ["nsi_feats", "nsi_prov"]:
                hits.append(node)
    assert hits, "NSI fallback assignment not found"
    handlers = [h for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)]
    for n in hits:
        assert any(n in ast.walk(h) for h in handlers), "NSI fallback must live inside the except block"


_ = Polygon


def test_manifest_names_resolve():
    """Regression (2026-10-22): _manifest read `wse_prov`, a local of run_area,
    so every assessment crashed at its last step with a NameError."""
    import builtins

    from terratriage.ops import pipeline as pl

    fn = pl._manifest
    code = fn.__code__
    known = set(code.co_varnames) | set(vars(pl)) | set(dir(builtins))
    missing = [n for n in code.co_names if n not in known and not hasattr(pl, n)]
    # co_names also lists attribute names; keep only bare names used as variables
    tree = ast.parse(__import__("inspect").getsource(fn))
    bare = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    assert not [n for n in missing if n in bare], missing
