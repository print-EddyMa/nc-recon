"""Per-building damage classification: given footprints + a pre/post image pair,
attach a 0..3 damage class and a confidence to each polygon.

Backends
--------
heuristic : change-detection on the pre/post crop (offline, always available)
keras     : the xView2 baseline CMU classifier (ResNet50 + small CNN head) run in
            the `terratriage-tf` conda env via `_keras_infer.py`. 128px POST crop,
            reference `rescale=1.4` preprocessing.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.enums import Resampling

CROP = 128
DAMAGE_ENCODING = {0: "no-damage", 1: "minor-damage", 2: "major-damage", 3: "destroyed"}


def _read_crop(ds, cx, cy, half_m, size=CROP):
    """Square crop centred on (cx, cy) in raster CRS, resampled to size x size RGB."""
    win = from_bounds(cx - half_m, cy - half_m, cx + half_m, cy + half_m, ds.transform)
    arr = ds.read(
        indexes=[1, 2, 3], window=win, boundless=True, fill_value=0,
        out_shape=(3, size, size), resampling=Resampling.bilinear,
    )
    return np.transpose(arr, (1, 2, 0)).astype("uint8")


def extract_crops(pre_path: str, post_path: str, polys, dst_crs, pad: float = 1.35):
    """Yield (idx, pre_crop, post_crop, area_m2, centroid_xy) for each polygon."""
    with rasterio.open(pre_path) as pre_ds, rasterio.open(post_path) as post_ds:
        for i, poly in enumerate(polys):
            minx, miny, maxx, maxy = poly.bounds
            cx, cy = poly.centroid.x, poly.centroid.y
            half = max((maxx - minx), (maxy - miny), 10.0) * 0.5 * pad
            yield (
                i,
                _read_crop(pre_ds, cx, cy, half),
                _read_crop(post_ds, cx, cy, half),
                poly.area,
                (cx, cy),
            )


# --------------------------------------------------------------------------- #
# heuristic backend
# --------------------------------------------------------------------------- #
def _heuristic_scores(crops) -> list[tuple[int, float]]:
    """Structural-loss change detection, calibrated per-AOI.

    Raw colour difference over a multi-year / cross-season pre/post pair is
    dominated by vegetation and illumination, not damage. We instead score the
    *loss of built structure*: edge/texture energy that was present on the
    building in the PRE image and is gone in the POST image (roof removed,
    collapse, scour). Scores are then ranked within the AOI so the class mix is
    plausible rather than keyed to absolute thresholds that don't transfer.
    """
    from .models.mock import _gray, _norm, _blur

    raw = []
    for _, pre, post, _area, _c in crops:
        gpre, gpost = _gray(pre), _gray(post)
        e_pre = _blur(np.hypot(*np.gradient(gpre)), 5)
        e_post = _blur(np.hypot(*np.gradient(gpost)), 5)
        # structure lost (pre had an edge, post doesn't), ignore structure gained
        lost = np.clip(_norm(e_pre) - _norm(e_post), 0, 1).mean()
        # colour/brightness collapse (debris fields, water, mud) as a secondary cue
        drop = np.clip((gpre.mean() - gpost.mean()) / 128.0, 0, 1)
        raw.append(0.75 * float(lost) + 0.25 * float(drop))

    if not raw:
        return []
    arr = np.asarray(raw)
    # rank-normalise; most buildings survive, a tail is damaged
    order = arr.argsort().argsort() / max(len(arr) - 1, 1)   # 0..1 percentile
    out = []
    for pct, r in zip(order, arr):
        if pct < 0.55:
            cls = 0
        elif pct < 0.80:
            cls = 1
        elif pct < 0.94:
            cls = 2
        else:
            cls = 3
        conf = float(np.clip(0.45 + 0.5 * abs(pct - 0.5) + 0.3 * r, 0.3, 0.98))
        out.append((cls, conf))
    return out


# --------------------------------------------------------------------------- #
# keras baseline backend (runs in the terratriage-tf conda env)
# --------------------------------------------------------------------------- #
def _conda_python(env: str = "terratriage-tf") -> str | None:
    for base in ("/opt/miniconda3", os.path.expanduser("~/miniconda3"), os.path.expanduser("~/anaconda3")):
        p = os.path.join(base, "envs", env, "bin", "python")
        if os.path.exists(p):
            return p
    return None


def _keras_scores(crops, weights_path: str) -> list[tuple[int, float]]:
    py = _conda_python()
    if not py:
        raise RuntimeError("terratriage-tf conda env not found; run scripts/setup_tf_env.sh")
    crops = list(crops)
    post_stack = np.stack([c[2] for c in crops]).astype("uint8")  # (N,128,128,3) POST
    here = os.path.dirname(__file__)
    with tempfile.TemporaryDirectory() as td:
        inp = os.path.join(td, "crops.npy")
        outp = os.path.join(td, "pred.npy")
        np.save(inp, post_stack)
        r = subprocess.run(
            [py, os.path.join(here, "_keras_infer.py"), weights_path, inp, outp],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"_keras_infer.py failed:\n{r.stdout}\n{r.stderr}")
        pred = np.load(outp)  # (N,4) activations
    probs = np.exp(pred - pred.max(axis=1, keepdims=True))
    probs /= probs.sum(axis=1, keepdims=True)
    idx = probs.argmax(axis=1)
    return [(int(k), float(probs[i, k])) for i, k in enumerate(idx)]


# --------------------------------------------------------------------------- #
def score_buildings(pre_path, post_path, polys, dst_crs, *, backend="heuristic",
                    weights_path=None) -> list[tuple[int, float]]:
    crops = list(extract_crops(pre_path, post_path, polys, dst_crs))
    if backend == "keras":
        if not weights_path or not os.path.exists(weights_path):
            raise FileNotFoundError(f"keras backend needs classification weights at {weights_path!r}")
        try:
            return _keras_scores(crops, weights_path)
        except Exception as ex:  # noqa: BLE001
            print(f"[classify] keras backend failed ({ex}); falling back to heuristic")
            return _heuristic_scores(crops)
    return _heuristic_scores(crops)
