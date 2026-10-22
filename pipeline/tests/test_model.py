"""Groma damage model plumbing (ops/model/), offline and fast."""
from __future__ import annotations

import numpy as np
import pytest

from terratriage.ops.model import LEVELS, dataset, train


def _tif(path, arr, epsg=32611, x0=400000.0, y1=3780000.0, res=0.5):
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=3,
                       dtype="uint8", crs=f"EPSG:{epsg}", transform=from_origin(x0, y1, res, res)) as dst:
        dst.write(arr)


def test_read_chips_resamples_and_drops_empty(tmp_path):
    from pyproj import Transformer

    a = np.full((3, 400, 400), 120, "uint8")
    b = np.full((3, 400, 400), 60, "uint8")
    _tif(tmp_path / "pre.tif", a)
    _tif(tmp_path / "post.tif", b)
    to_ll = Transformer.from_crs(32611, 4326, always_xy=True).transform
    inside = to_ll(400100.0, 3779900.0)
    outside = to_ll(390000.0, 3779900.0)
    pts = [{"id": "a", "lon": inside[0], "lat": inside[1], "level": "destroyed"},
           {"id": "b", "lon": outside[0], "lat": outside[1], "level": "no_damage"}]
    pre, post, kept = dataset.read_chips(str(tmp_path / "pre.tif"), str(tmp_path / "post.tif"), pts)
    assert [k["id"] for k in kept] == ["a"]
    assert pre.shape == (1, 3, dataset.CHIP_PX, dataset.CHIP_PX) and int(pre.mean()) == 120 and int(post.mean()) == 60


def test_spatial_split_is_deterministic_and_blockwise():
    lon, lat = -118.53, 34.05
    assert dataset.is_val(lon, lat) == dataset.is_val(lon, lat)
    assert dataset.block_of(lon, lat) == dataset.block_of(lon + 0.0001, lat + 0.0001)
    share = np.mean([dataset.is_val(lon + i * 0.004, lat + j * 0.004) for i in range(20) for j in range(20)])
    assert 0.1 < share < 0.3


def test_metrics_counts_severe_and_levels():
    y = np.array([0, 0, 4, 4, 3])
    p = np.zeros((5, len(LEVELS)))
    p[[0, 1, 2, 3, 4], [0, 4, 4, 0, 3]] = 1.0
    m = train.metrics(y, p)
    assert m["major_or_destroyed"]["true"] == 3 and m["major_or_destroyed"]["called"] == 3
    assert m["major_or_destroyed"]["precision"] == pytest.approx(2 / 3, abs=1e-3)
    assert m["confusion_rows_true_cols_pred"][0][4] == 1


def test_siamese_forward_shape():
    torch = pytest.importorskip("torch")
    from terratriage.ops.model.net import Siamese

    m = Siamese(len(LEVELS), pretrained=False).eval()
    with torch.no_grad():
        out = m(torch.rand(2, 3, 96, 96), torch.rand(2, 3, 96, 96))
    assert tuple(out.shape) == (2, len(LEVELS))
