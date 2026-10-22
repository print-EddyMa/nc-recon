"""Evidence channel M1: Groma damage model v0 on the pipeline's own imagery.

    probs = m1_probs(pre_path, post_path, footprints_ll)          # (N, 5), NaN rows = unavailable
    ch    = m1_channel(probs[i])                                  # fusion Channel "M1"

For each building, the before and after chips are centred on the footprint
centroid in the stored, co-gridded rasters (data/raw/<area>/pre_*.tif and
post_*.tif), cut at the size the model was trained on, and scored by
`linear.predict`. A building whose chips are more than 20% no-data gets a NaN
row, and its channel is unavailable.

Likelihood. v0 was fit with balanced class weights, so its outputs are close
to P(level | image) under a flat prior. Read that way, the output is
proportional to P(image | level), and the channel's likelihood is the model's
probability vector as is. Fusion multiplies in the class prior once
(fusion.pool).

E1 stays the default optical channel. M1 is enabled per hazard by the
pipeline owner (config/hazards.yaml), and only after the pre-registered
evaluation in docs/model/MODEL_CARD.md says so.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from . import LEVELS

TAG = "groma-dmg-v0"
_cache: dict[str, Any] = {}


def _model(tag: str = TAG):
    if tag not in _cache:
        from . import linear

        _cache[tag] = linear.load(tag)
    return _cache[tag]


def m1_probs(pre_path: str, post_path: str, footprints_ll: Sequence[Any], tag: str = TAG,
             max_nodata: float = 0.2) -> np.ndarray:
    """(N, 5) FEMA-level probabilities in LEVELS order; NaN rows where the
    chips are unusable. `footprints_ll` are shapely polygons in lon/lat."""
    from . import linear
    from .dataset import read_chips

    params, card = _model(tag)
    chip = card["chip"]
    pts = [{"id": i, "lon": float(p.centroid.x), "lat": float(p.centroid.y)} for i, p in enumerate(footprints_ll)]
    out = np.full((len(pts), len(LEVELS)), np.nan)
    if not pts:
        return out
    pre, post, kept = read_chips(pre_path, post_path, pts, chip_m=float(chip["metres"]), px=int(chip["pixels"]),
                                 max_nodata=max_nodata)
    if kept:
        out[[k["id"] for k in kept]] = linear.predict(params, pre, post)
    return out


def m1_channel(probs: np.ndarray, weight: float = 1.0):
    """Fusion Channel for one building from its m1_probs row."""
    from ..analyze.fusion import Channel

    if probs is None or not np.all(np.isfinite(probs)):
        return Channel("M1", False, unavailable_reason="M1_NO_USABLE_CHIP")
    p = np.clip(np.asarray(probs, float), 1e-6, 1.0)
    lab = int(np.argmax(p))
    return Channel("M1", True, p / p.sum(), weight, "held_out_evaluated",
                   [f"M1_GROMA_V0_{LEVELS[lab].upper()}"],
                   detail={"model": TAG, "probs": [round(float(v), 4) for v in p]})


# --------------------------------------------------------------------------- #
# Interface used by the pipeline (gated per hazard; mode off|alongside|replace)
# --------------------------------------------------------------------------- #
def load(tag: str = TAG) -> dict[str, Any]:
    """Handle for predict(). FileNotFoundError when the weights are missing."""
    import os

    from . import MODEL_DIR

    from .fetch_encoder import encoder_path

    for ext in ("npz", "json"):
        p = os.path.join(MODEL_DIR, "weights", f"{tag}.{ext}")
        if not os.path.exists(p):
            raise FileNotFoundError(p)
    encoder_path()     # FileNotFoundError("resnet18 encoder weights not on this machine") when absent
    params, card = _model(tag)
    return {"tag": tag, "params": params, "card": card}


def predict(handle: dict[str, Any], pre_path: str, post_path: str,
            footprints_raster_crs: Sequence[Any], max_nodata: float = 0.2) -> list[dict[str, Any] | None]:
    """One entry per building: None (no usable chip) or
    {"probs": [no_damage, affected, minor, major, destroyed], "status", "detail"}.
    Footprints are in the rasters' CRS; chips are centred on their centroids."""
    import rasterio
    from shapely.geometry import Point

    from ..geodesy import transformer

    with rasterio.open(pre_path) as ds:
        to_ll = transformer(ds.crs.to_epsg(), "storage").transform
    ll = [Point(*to_ll(p.centroid.x, p.centroid.y)) for p in footprints_raster_crs]
    probs = m1_probs(pre_path, post_path, ll, tag=handle["tag"], max_nodata=max_nodata)
    out: list[dict[str, Any] | None] = []
    for row in probs:
        if not np.all(np.isfinite(row)):
            out.append(None)
            continue
        out.append({"probs": [round(float(v), 6) for v in row], "status": "provisional",
                    "detail": {"model": handle["tag"], "chip_m": handle["card"]["chip"]["metres"],
                               "argmax": LEVELS[int(np.argmax(row))]}})
    return out
