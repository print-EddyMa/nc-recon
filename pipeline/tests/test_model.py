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


def test_m1_channel_interface(tmp_path, monkeypatch):
    from pyproj import Transformer
    from shapely.geometry import box

    from terratriage.ops import model as mdl
    from terratriage.ops.model import channel, linear

    a = np.full((3, 400, 400), 120, "uint8")
    _tif(tmp_path / "pre.tif", a)
    _tif(tmp_path / "post.tif", a)
    fake = ({"x": np.zeros(1)}, {"chip": {"metres": 32.0, "pixels": 64}})
    monkeypatch.setattr(channel, "_model", lambda tag="x": fake)
    monkeypatch.setattr(linear, "predict", lambda params, pre, post: np.tile([0.1, 0.1, 0.1, 0.2, 0.5], (len(pre), 1)))
    # in the raster's CRS: one footprint inside, one far outside
    fps = [box(400090, 3779890, 400110, 3779910), box(390000, 3779890, 390020, 3779910)]
    with pytest.raises(FileNotFoundError):
        monkeypatch.setattr(mdl, "MODEL_DIR", str(tmp_path / "none"))
        channel.load()
    h = {"tag": "groma-dmg-v0", "params": fake[0], "card": fake[1]}
    out = channel.predict(h, str(tmp_path / "pre.tif"), str(tmp_path / "post.tif"), fps)
    assert out[1] is None
    assert out[0]["probs"] == [0.1, 0.1, 0.1, 0.2, 0.5] and out[0]["detail"]["argmax"] == "destroyed"
    to_ll = Transformer.from_crs(32611, 4326, always_xy=True).transform
    ll = [box(*to_ll(400090, 3779890), *to_ll(400110, 3779910))]
    p = channel.m1_probs(str(tmp_path / "pre.tif"), str(tmp_path / "post.tif"), ll)
    ch = channel.m1_channel(p[0])
    assert ch.id == "M1" and ch.available and ch.likelihood.argmax() == 4
    assert not channel.m1_channel(np.full(5, np.nan)).available


def test_encoder_is_local_only(tmp_path, monkeypatch):
    from terratriage.ops.model import fetch_encoder as fe

    monkeypatch.setenv("TORCH_HOME", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="not on this machine"):
        fe.encoder_path()
    d = tmp_path / "hub" / "checkpoints"
    d.mkdir(parents=True)
    (d / fe.FILE).write_bytes(b"not the weights")
    with pytest.raises(FileNotFoundError, match="sha256"):
        fe.encoder_path()


def test_channel_load_refuses_without_encoder(tmp_path, monkeypatch):
    from terratriage.ops import model as mdl
    from terratriage.ops.model import channel

    w = tmp_path / "weights"
    w.mkdir()
    (w / "groma-dmg-v0.npz").write_bytes(b"x")
    (w / "groma-dmg-v0.json").write_text("{}")
    monkeypatch.setattr(mdl, "MODEL_DIR", str(tmp_path))
    monkeypatch.setenv("TORCH_HOME", str(tmp_path / "torch"))
    with pytest.raises(FileNotFoundError, match="encoder"):
        channel.load()
