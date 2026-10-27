"""Ground change from the 2025 lidar (collect/nc_lidar.py,
analyze/ground_change.py) on synthetic surfaces: no network."""
import json

import numpy as np
import pytest

from terratriage.ops.analyze import ground_change as gc
from terratriage.ops.collect import nc_lidar as nl
from terratriage.ops.collect.base import SchemaError, SourceUnavailable

X0, Y0 = 380000.0, 3940000.0          # a UTM 17N corner near Swannanoa
W = H = 200


def _tif(path, arr):
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(path, "w", driver="GTiff", width=W, height=H, count=1, dtype="float32",
                       crs="EPSG:32617", transform=from_origin(X0, Y0 + H, 1.0, 1.0), nodata=nl.NODATA) as d:
        d.write(arr.astype("float32"), 1)


def _square(cx, cy, half=6.0):
    from pyproj import Transformer

    tr = Transformer.from_crs(32617, 4326, always_xy=True).transform
    ring = [tr(cx + dx, cy + dy) for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half), (-half, -half))]
    return {"type": "Polygon", "coordinates": [[list(p) for p in ring]]}


@pytest.fixture
def surfaces(tmp_path):
    base = np.full((H, W), 700.0)
    post_m = base + 0.05                                  # typical vintage offset
    rows, cols = np.mgrid[0:H, 0:W]
    yy, xx = Y0 + H - rows - 0.5, X0 + cols + 0.5
    near_a = (np.abs(xx - (X0 + 50)) < 14) & (np.abs(yy - (Y0 + 50)) < 14)
    post_m[near_a] += 2.0                                 # debris piled around building A
    near_b = (np.abs(xx - (X0 + 150)) < 14) & (np.abs(yy - (Y0 + 150)) < 14)
    post_m[near_b] -= 1.8                                 # ground scoured around building B
    post_m[0, 0] = np.nan
    post_ft = post_m / nl.FT_TO_M
    post_ft[0, 0] = nl.NODATA
    p, b = tmp_path / "post.tif", tmp_path / "base.tif"
    _tif(p, post_ft)
    _tif(b, base)
    return {"post": str(p), "base": str(b)}


def test_dz_converts_feet_and_masks_nodata(surfaces):
    dz, tr = nl.dz(surfaces)
    assert np.isnan(dz[0, 0])
    assert abs(np.nanmedian(dz) - 0.05) < 1e-3


def test_ring_flags_deposit_and_scour_but_not_ordinary_ground(surfaces):
    feats = [{"geometry": _square(X0 + 50, Y0 + 50), "properties": {"ncr_id": "a"}},
             {"geometry": _square(X0 + 150, Y0 + 150), "properties": {"ncr_id": "b"}}]
    feats += [{"geometry": _square(X0 + 20 + 15 * (i % 8), Y0 + 110 + 10 * (i // 8) % 30, 3.0),
               "properties": {"ncr_id": f"q{i}"}} for i in range(40)]
    polys = gc._utm(feats)
    dz, tr = nl.dz(surfaces)
    stats = gc.ring_stats(dz, tr, polys)
    off = gc.typical(stats)
    assert off is not None and abs(off - 0.05) < 0.05
    assert gc.flag(stats["a"], off) == "deposit"
    assert gc.flag(stats["b"], off) == "scour"
    quiet = [k for k in stats if k.startswith("q") and gc.flag(stats[k], off)]
    assert len(quiet) <= 2                    # only rings that clip the disturbed patches


def test_typical_needs_enough_buildings():
    assert gc.typical({str(i): {"median_m": 0.0} for i in range(5)}) is None


def test_likelihoods_lean_severe_and_are_distributions():
    for v in gc.LIKELIHOOD.values():
        assert abs(sum(v) - 1.0) < 1e-9 and v[3] + v[4] > 0.6


def test_county_raster_picks_the_2025_ql1(monkeypatch):
    monkeypatch.setattr(nl, "http_json", lambda url, params=None, **kw: {"features": [
        {"attributes": {"objectid": 1286, "name": "Buncombe_QL1_2025_03ft_CountywideRaster"}}]})
    assert nl.county_raster("Buncombe County") == (1286, "Buncombe_QL1_2025_03ft_CountywideRaster")
    monkeypatch.setattr(nl, "http_json", lambda url, params=None, **kw: {"features": [
        {"attributes": {"objectid": 1332, "name": "Madison_Ground_3ft"}}]})
    assert nl.county_raster("Madison") is None
    with pytest.raises(SourceUnavailable):
        nl.surfaces("Madison", (0, 0, 10, 10))


def test_export_rejects_non_tiff(monkeypatch, tmp_path):
    import io

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(nl.urllib.request, "urlopen", lambda req, timeout=0: R(b'{"error": "nope"}'))
    with pytest.raises(SchemaError):
        nl._export(nl.DEM03, (0, 0, 10, 10), 10, 10, None, str(tmp_path / "x.tif"))


def test_export_stitches_tiles(monkeypatch, tmp_path):
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    monkeypatch.setattr(nl, "TILE_PX", 4)
    calls = []

    def tile(url, bbox, w, h, mosaic):
        calls.append((w, h))
        a = np.full((h, w), bbox[0], dtype="float32")         # each tile filled with its west edge
        with MemoryFile() as mf:
            with mf.open(driver="GTiff", width=w, height=h, count=1, dtype="float32", crs="EPSG:32617",
                         transform=from_origin(bbox[0], bbox[3], 1, 1)) as d:
                d.write(a, 1)
            return mf.read()

    monkeypatch.setattr(nl, "_fetch_tile", tile)
    p = str(tmp_path / "s.tif")
    nl._export(nl.DEP3, (100.0, 0.0, 110.0, 6.0), 10, 6, None, p)
    assert sorted(calls) == sorted([(4, 4), (4, 4), (2, 4), (4, 2), (4, 2), (2, 2)])
    with rasterio.open(p) as d:
        a = d.read(1)
        assert d.transform.c == 100.0 and d.transform.f == 6.0
    assert a[0, 0] == 100 and a[0, 4] == 104 and a[5, 9] == 108


def test_compare_area_refuses_test_areas(monkeypatch, tmp_path):
    monkeypatch.setattr(gc, "OPS_OUT", str(tmp_path))
    (tmp_path / "zz.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [],
                                                     "properties": {"aoi": {"role": "TEST", "county": "Buncombe"}}}))
    with pytest.raises(SystemExit):
        gc.compare_area("zz", write=False)
