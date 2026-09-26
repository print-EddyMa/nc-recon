"""Footprint-to-image alignment.

Footprints and imagery disagree by metres: footprint sources were digitised on
other imagery (USA Structures from 2014-2019 captures, OSM from whatever
basemap the mapper had), and every capture has its own orthorectification error
and relief displacement (Maxar Old Fort pre: 27 deg off-nadir). Measured at Old
Fort, the unaligned USA Structures outline often lands on the neighbour's lawn,
and the CNN then scores grass, which reads as "destroyed".

Two stages, run separately for the pre and the post image:

1. **Consensus offset** for the AOI and footprint source: for a sample of
   footprints, correlate the footprint *outline* with the image gradient
   magnitude over a +-15 m search window (FFT), z-normalise each surface and
   sum them. Individual surfaces peak on neighbours and roads; the sum peaks on
   the shared systematic shift.
2. **Per-building refinement** within +-3 m of the consensus. Its gain (peak
   edge score over score at the consensus) is recorded; a building whose
   outline never finds crisp edges keeps the consensus offset and gets
   `FOOTPRINT_ALIGNMENT_WEAK`.

Offsets are in the raster CRS (metres), applied by translating the polygon.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds
from scipy.signal import fftconvolve
from shapely.affinity import translate


@dataclass
class Offset:
    dx: float
    dy: float
    peak_z: float = 0.0
    n: int = 0

    def to_dict(self) -> dict:
        return {"dx_m": round(self.dx, 2), "dy_m": round(self.dy, 2),
                "peak_z": round(self.peak_z, 2), "n": self.n}


def _grad(ds, poly, R: float):
    minx, miny, maxx, maxy = poly.bounds
    win = from_bounds(minx - R - 2, miny - R - 2, maxx + R + 2, maxy + R + 2, ds.transform)
    win = win.round_offsets().round_lengths()
    a = ds.read(indexes=[1, 2, 3], window=win, boundless=True, fill_value=0).astype("float32")
    g = a.mean(axis=0)
    gy, gx = np.gradient(g)
    return np.hypot(gx, gy), ds.window_transform(win), (a.max(axis=0) > 0)


def _surface(ds, poly, R: float) -> tuple[np.ndarray, float] | None:
    """Edge score of the outline at every integer-pixel shift within +-R m.
    Returns (surface[(2r+1),(2r+1)] indexed [dy_px + r, dx_px + r], res)."""
    res = abs(ds.transform.a)
    gm, wt, valid = _grad(ds, poly, R)
    if valid.mean() < 0.8:
        return None
    ring = rasterize([(poly.boundary.buffer(res * 1.2), 1)], out_shape=gm.shape, transform=wt).astype("float32")
    if ring.sum() < 8:
        return None
    r = int(round(R / res))
    # correlation: sum over ring pixels of gm shifted -> convolve gm with flipped ring
    corr = fftconvolve(gm, ring[::-1, ::-1], mode="same") / ring.sum()
    cy, cx = gm.shape[0] // 2, gm.shape[1] // 2
    # centre of the ring mask vs window centre: the mask is centred by construction
    # (window built around the polygon), so offset k px -> index centre + k
    oy, ox = _mask_centre_offset(ring)
    cy, cx = cy - oy, cx - ox
    if cy - r < 0 or cx - r < 0 or cy + r + 1 > corr.shape[0] or cx + r + 1 > corr.shape[1]:
        return None
    s = corr[cy - r: cy + r + 1, cx - r: cx + r + 1]
    return s, res


def _mask_centre_offset(mask: np.ndarray) -> tuple[int, int]:
    """For an odd-free 'same' convolution the zero-shift response sits at the
    array centre only when the kernel is centred; correct for the ring's bbox
    centre vs the array centre (off by <= 1 px, but measured, not assumed)."""
    ys, xs = np.nonzero(mask)
    my = (ys.min() + ys.max()) / 2 - (mask.shape[0] - 1) / 2
    mx = (xs.min() + xs.max()) / 2 - (mask.shape[1] - 1) / 2
    return int(round(my)), int(round(mx))


def consensus(path: str, polys, sample: int = 250, R: float = 15.0, seed: int = 0) -> Offset:
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(polys), min(sample, len(polys)), replace=False) if len(polys) else []
    acc, n, res = None, 0, None
    with rasterio.open(path) as ds:
        for i in idx:
            out = _surface(ds, polys[int(i)], R)
            if out is None:
                continue
            s, res = out
            z = (s - s.mean()) / (s.std() + 1e-6)
            acc = z if acc is None else acc + z
            n += 1
    if acc is None or n < 10:
        return Offset(0.0, 0.0, 0.0, n)
    r = acc.shape[0] // 2
    iy, ix = np.unravel_index(int(np.argmax(acc)), acc.shape)
    peak = float((acc.max() - acc.mean()) / (acc.std() + 1e-6))
    # row index grows southward: +1 row = -res metres in y
    return Offset((ix - r) * res, -(iy - r) * res, peak, n)


def refine(path_or_ds, polys, base: Offset, R: float = 3.0, min_gain: float = 1.10):
    """Per-building offsets near `base`. Returns list of (dx, dy, gain, weak)."""
    ds = rasterio.open(path_or_ds) if isinstance(path_or_ds, str) else path_or_ds
    out = []
    try:
        for p in polys:
            q = translate(p, base.dx, base.dy)
            got = _surface(ds, q, R)
            if got is None:
                out.append((base.dx, base.dy, 1.0, True))
                continue
            s, res = got
            r = s.shape[0] // 2
            iy, ix = np.unravel_index(int(np.argmax(s)), s.shape)
            gain = float(s[iy, ix] / max(s[r, r], 1e-6))
            if gain < min_gain:
                out.append((base.dx, base.dy, gain, s.max() < 2.0))
            else:
                out.append((base.dx + (ix - r) * res, base.dy - (iy - r) * res, gain, False))
    finally:
        if isinstance(path_or_ds, str):
            ds.close()
    return out
