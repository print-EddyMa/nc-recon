"""M1 (Groma damage model) wiring in the pipeline: hazard gating, modes,
missing weights, unusable chips, replace mode (synthetic rasters, offline)."""
from __future__ import annotations

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from terratriage.ops import pipeline as pl
from terratriage.ops.analyze import channels
from terratriage.ops.model import channel as m1ch

EPSG = 6340          # NAD83(2011) UTM 11N, like the Altadena grid
X0, Y1, RES, N = 394000.0, 3784000.0, 0.3, 700   # 210 m square


def _raster(path, seed):
    rng = np.random.default_rng(seed)
    arr = rng.integers(60, 200, size=(3, N, N), dtype=np.uint8)
    with rasterio.open(path, "w", driver="GTiff", height=N, width=N, count=3, dtype="uint8",
                       crs=f"EPSG:{EPSG}", transform=from_origin(X0, Y1, RES, RES)) as dst:
        dst.write(arr)


@pytest.fixture
def rasters(tmp_path):
    pre, post = str(tmp_path / "pre.tif"), str(tmp_path / "post.tif")
    _raster(pre, 1)
    _raster(post, 2)
    return pre, post


def _mode(monkeypatch, mode):
    r = pl.rules()
    patched = {**r, "channels": {**r["channels"], "M1": {**r["channels"].get("M1", {}), "mode": mode}}}
    monkeypatch.setattr(pl, "rules", lambda: patched)


INSIDE = box(X0 + 100, Y1 - 110, X0 + 112, Y1 - 98)      # centre of the rasters
OUTSIDE = box(X0 + 400, Y1 - 110, X0 + 412, Y1 - 98)     # chip entirely off the rasters


def test_not_applicable_and_off(monkeypatch, rasters):
    w: list[str] = []
    assert pl.m1_for_area({"E1", "E2", "E5"}, *rasters, [INSIDE], w)[2] == "NOT_APPLICABLE_FOR_HAZARD"
    _mode(monkeypatch, "off")
    assert pl.m1_for_area({"E1", "M1"}, *rasters, [INSIDE], w)[2] == "M1_OFF"
    assert w == []


def test_weights_missing_is_never_fatal(monkeypatch, rasters):
    _mode(monkeypatch, "alongside")

    def missing(tag="x"):
        raise FileNotFoundError("data/model/weights/groma-dmg-v0.npz")

    monkeypatch.setattr(m1ch, "load", missing)
    w: list[str] = []
    preds, mode, reason = pl.m1_for_area({"E1", "M1"}, *rasters, [INSIDE], w)
    assert preds is None and reason == "M1_WEIGHTS_MISSING" and "weights not found" in w[0]
    chs = [channels.Channel("E1", True, np.ones(5) / 5, 1.0)]
    pl.add_m1(chs, None, mode, reason)
    assert chs[0].available and chs[-1].id == "M1" and chs[-1].unavailable_reason == "M1_WEIGHTS_MISSING"


def test_model_error_is_never_fatal(monkeypatch, rasters):
    _mode(monkeypatch, "alongside")
    monkeypatch.setattr(m1ch, "load", lambda tag="x": {"tag": "t"})
    monkeypatch.setattr(m1ch, "predict", lambda *a, **k: [])          # wrong length
    w: list[str] = []
    assert pl.m1_for_area({"M1"}, *rasters, [INSIDE], w)[2] == "M1_UNAVAILABLE" and w


def test_real_model_on_synthetic_rasters(monkeypatch, rasters):
    # weights or the image encoder may be absent (CI): load() says so with
    # FileNotFoundError, and nothing is downloaded during a test
    try:
        m1ch.load()
    except FileNotFoundError as ex:
        pytest.skip(f"M1 weights or encoder not on disk: {ex}")
    _mode(monkeypatch, "alongside")
    w: list[str] = []
    preds, mode, reason = pl.m1_for_area({"E1", "M1"}, *rasters, [INSIDE, OUTSIDE], w)
    assert reason == "" and len(preds) == 2 and "1 of 2 buildings scored" in w[0]
    assert preds[1] is None                                    # chip off the rasters: no call
    p = np.asarray(preds[0]["probs"])
    assert p.shape == (5,) and np.isclose(p.sum(), 1.0, atol=1e-3)
    chs: list = []
    pl.add_m1(chs, preds[1], mode, reason)
    assert chs[0].unavailable_reason == "M1_NO_USABLE_CHIP"


def test_replace_mode_records_e1_as_replaced(monkeypatch):
    _mode(monkeypatch, "replace")
    e1 = channels.Channel("E1", True, np.ones(5) / 5, 1.0)
    chs = [e1, channels.Channel("E2", True, np.ones(5) / 5, 0.6)]
    pl.add_m1(chs, {"probs": [0.05, 0.05, 0.1, 0.2, 0.6]}, "replace", "")
    assert chs[0].id == "E1" and chs[0].unavailable_reason == "REPLACED_BY_M1"
    assert chs[-1].id == "M1" and chs[-1].available
    # where M1 has no call, E1 stays
    chs2 = [e1]
    pl.add_m1(chs2, None, "replace", "")
    assert chs2[0].available and chs2[-1].unavailable_reason == "M1_NO_USABLE_CHIP"
    # alongside keeps both voting
    chs3 = [e1]
    pl.add_m1(chs3, {"probs": [0.05, 0.05, 0.1, 0.2, 0.6]}, "alongside", "")
    assert chs3[0].available and chs3[-1].available
