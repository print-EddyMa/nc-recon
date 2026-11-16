"""E5: flood depth -> FEMA damage category, with uncertainty.

First-floor depth  d_ff = WSE - (ground_elev + foundation_height), all NAVD88
metres through typed heights. The FEMA PDA matrix (config/damage_matrices)
turns d_ff into a class; Monte Carlo over the water-surface elevation, ground
elevation, foundation height and outlet height gives P(class) instead of a
single label.

WSE sources (best first, each with its own sigma and domain of validity):
  1. modeled depth grid for the event (not available for Helene NC)
  2. USGS STN high-water marks on the same reach
  3. gauge crest -> elevation via the gauge datum, for structures on the gauged
     reach within `max_dist_m` of the gauge
A structure outside every source's domain gets E5 *unavailable* with a reason
code - never a guessed depth.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
import yaml

from .. import CONFIG_DIR
from ..heights import Depth, Elevation
from .classes import FEMA, K

MATRIX = "fema_pda_2025-07.yaml"


@lru_cache(maxsize=4)
def matrix(name: str = MATRIX) -> dict[str, Any]:
    with open(os.path.join(CONFIG_DIR, "damage_matrices", name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True)
class WSESource:
    kind: str                 # "depth_grid" | "hwm" | "gauge_crest"
    ref: str                  # id of the HWM / gauge
    lon: float
    lat: float
    wse: Elevation            # water-surface elevation, NAVD88
    sigma_m: float            # 1-sigma uncertainty at the source
    max_dist_m: float         # domain of validity (same reach, near the source)
    sigma_per_km: float = 0.5  # uncertainty growth with distance along the reach


def depth_class(d_ff_m: float, above_ground: bool, manufactured: bool, p: dict[str, Any],
                outlet_in: float) -> int:
    """Deterministic FEMA flood class index for one first-floor depth."""
    ceiling = p["ceiling_height_ft"] * 0.3048
    if not above_ground:
        return FEMA.index("no_damage")
    if manufactured:
        fs = p["manufactured_floor_system_ft"] * 0.3048
        if d_ff_m < -fs:
            return FEMA.index("affected")
        if d_ff_m < 0:
            return FEMA.index("minor")
        if d_ff_m < ceiling:
            return FEMA.index("major")
        return FEMA.index("destroyed")
    if d_ff_m < 0:
        return FEMA.index("affected")
    if d_ff_m < outlet_in * 0.0254:
        return FEMA.index("minor")
    if d_ff_m < ceiling:
        return FEMA.index("major")
    return FEMA.index("destroyed")


def class_probs(
    wse: Elevation, wse_sigma_m: float,
    ground: Elevation, ground_sigma_m: float,
    found_ht: Depth, found_sigma_m: float,
    manufactured: bool,
    *, n: int = 2000, seed: int = 0, outlet_in: float | None = None,
    matrix_name: str = MATRIX,
) -> tuple[np.ndarray, dict[str, float]]:
    """Monte Carlo P(FEMA class) and depth stats for one structure."""
    p = matrix(matrix_name)["params"]
    rng = np.random.default_rng(seed)
    w = wse.m + rng.normal(0, wse_sigma_m, n)
    g = ground.m + rng.normal(0, ground_sigma_m, n)
    f = np.maximum(0.0, found_ht.m + rng.normal(0, found_sigma_m, n))
    outlet = outlet_in if outlet_in is not None else p["outlet_height_in"]
    counts = np.zeros(K)
    minor_i, major_i = FEMA.index("minor"), FEMA.index("major")
    ext = p["minor_extenuating_major_p"]
    for wi, gi, fi in zip(w, g, f):
        c = depth_class(wi - (gi + fi), wi > gi, manufactured, p, outlet)
        if c == minor_i and not manufactured:
            counts[minor_i] += 1 - ext
            counts[major_i] += ext
        else:
            counts[c] += 1
    d_ff = w - (g + f)
    return counts / counts.sum(), {
        "d_ff_m_median": float(np.median(d_ff)),
        "d_ff_m_p10": float(np.percentile(d_ff, 10)),
        "d_ff_m_p90": float(np.percentile(d_ff, 90)),
    }


def pick_source(lon: float, lat: float, sources: list[WSESource]) -> tuple[WSESource, float] | None:
    from ..geodesy import distance_m

    best = None
    for s in sources:
        d = distance_m(lon, lat, s.lon, s.lat)
        if d <= s.max_dist_m:
            sig = float(np.hypot(s.sigma_m, s.sigma_per_km * d / 1000))
            if best is None or sig < best[1]:
                best = (s, sig)
    return best
