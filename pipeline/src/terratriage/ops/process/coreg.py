"""Co-registration of the post image to the pre image, and radiometric matching.

Pixel-level change is meaningless if the two images are misaligned: a 1-pixel
shift along every roof edge reads as "change" everywhere. We estimate a global
sub-pixel shift with phase correlation on *gradient-magnitude* images (edges
survive season and illumination changes far better than raw brightness), on a
grid of sub-windows, and report:

  shift_px     median (dy, dx) of post relative to pre, full-resolution pixels
  residual_px  spread (MAD) of the per-window shifts after removing the median;
               a large spread means the misalignment is not a single shift
               (relief displacement from different off-nadir angles, or
               orthorectification error), which a global shift cannot fix

Rule (context_rules.yaml): residual > 1 px -> E2 unavailable, `MISREGISTERED`.

Radiometric: post is matched to pre with per-band linear gain/offset fit on
pixels that are *not* candidate change (robust to the real damage), falling
back to histogram matching.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.enums import Resampling


@dataclass
class CoregResult:
    shift_px: tuple[float, float]
    residual_px: float
    n_windows: int
    windows: list[tuple[float, float, float]]  # (dy, dx, error)
    downsample: int

    def to_dict(self) -> dict:
        return {
            "shift_px": [round(self.shift_px[0], 2), round(self.shift_px[1], 2)],
            "residual_px": round(self.residual_px, 2),
            "n_windows": self.n_windows,
            "downsample": self.downsample,
        }


def _gray(a: np.ndarray) -> np.ndarray:
    a = a.astype("float32")
    return 0.299 * a[0] + 0.587 * a[1] + 0.114 * a[2]


def _grad(g: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(g)
    m = np.hypot(gx, gy)
    return (m - m.mean()) / (m.std() + 1e-6)


def estimate_shift(pre_path: str, post_path: str, downsample: int = 4, grid: int = 4,
                   win: int = 512, max_shift_px: float = 60.0) -> CoregResult:
    from skimage.registration import phase_cross_correlation

    with rasterio.open(pre_path) as a, rasterio.open(post_path) as b:
        if a.transform != b.transform or a.shape != b.shape:
            raise ValueError("pre/post are not on the same pixel grid; resample first")
        h, w = a.height // downsample, a.width // downsample
        pa = a.read(out_shape=(3, h, w), resampling=Resampling.average)
        pb = b.read(out_shape=(3, h, w), resampling=Resampling.average)
    ga, gb = _grad(_gray(pa)), _grad(_gray(pb))
    valid = (pa.max(axis=0) > 0) & (pb.max(axis=0) > 0)
    res = []
    step_y = max(1, (h - win) // max(1, grid - 1))
    step_x = max(1, (w - win) // max(1, grid - 1))
    for iy in range(grid):
        for ix in range(grid):
            y0, x0 = min(iy * step_y, max(0, h - win)), min(ix * step_x, max(0, w - win))
            sl = (slice(y0, y0 + win), slice(x0, x0 + win))
            if valid[sl].mean() < 0.9:
                continue
            shift, err, _ = phase_cross_correlation(ga[sl], gb[sl], upsample_factor=20)
            res.append((float(shift[0]) * downsample, float(shift[1]) * downsample, float(err)))
    # a phase-correlation peak far outside any plausible misregistration is a
    # failed match (repetitive texture, cloud, water), not a shift
    res = [r for r in res if abs(r[0]) <= max_shift_px and abs(r[1]) <= max_shift_px]
    if not res:
        raise RuntimeError("no valid windows for co-registration")
    arr = np.array([(r[0], r[1]) for r in res])
    med = np.median(arr, axis=0)
    resid = np.median(np.hypot(*(arr - med).T)) * 1.4826
    return CoregResult((float(med[0]), float(med[1])), float(resid), len(res), res, downsample)


def apply_shift(img: np.ndarray, shift_px: tuple[float, float]) -> np.ndarray:
    """Shift a (bands, H, W) chip by (dy, dx) pixels (sub-pixel, bilinear)."""
    from scipy.ndimage import shift as nd_shift

    dy, dx = shift_px
    if abs(dy) < 0.05 and abs(dx) < 0.05:
        return img
    return np.stack([nd_shift(b.astype("float32"), (dy, dx), order=1, mode="nearest") for b in img])


def radiometric_fit(pre: np.ndarray, post: np.ndarray, mask: np.ndarray | None = None,
                    iters: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Per-band gain/offset mapping post -> pre on pseudo-invariant pixels.

    Iteratively reweighted: fit, drop the 20 % of pixels with the largest
    residual (the likely-changed ones), refit. A light-weight stand-in for
    IR-MAD that is robust to a damaged minority.
    """
    bands = pre.shape[0]
    gains, offs = np.ones(bands), np.zeros(bands)
    base = np.ones(pre.shape[1:], bool) if mask is None else mask.copy()
    base &= (pre.max(axis=0) > 0) & (post.max(axis=0) > 0)
    for bnd in range(bands):
        x = post[bnd][base].astype("float64")
        y = pre[bnd][base].astype("float64")
        if x.size < 1000:
            continue
        sel = np.ones(x.size, bool)
        for _ in range(iters):
            A = np.vstack([x[sel], np.ones(sel.sum())]).T
            g, o = np.linalg.lstsq(A, y[sel], rcond=None)[0]
            r = np.abs(y - (g * x + o))
            sel = r <= np.quantile(r, 0.8)
        gains[bnd], offs[bnd] = g, o
    return gains, offs


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def local_shift(pre_g: np.ndarray, post_g: np.ndarray, max_px: float) -> tuple[float, float, float, float]:
    """Per-building alignment on grayscale chips centred on the footprint.

    Returns (dy, dx, edge_ncc_before, edge_ncc_after). The shift is capped at
    `max_px`; if the capped shift does not improve edge correlation it is
    discarded (0, 0). `edge_ncc_after` is the alignment quality: low values mean
    the two chips do not show the same structure in the same place, whether
    from misregistration, lean, cloud, or real destruction - the caller decides.
    """
    from skimage.registration import phase_cross_correlation

    ga, gb = _grad(pre_g), _grad(post_g)
    before = ncc(ga, gb)
    try:
        sh, _, _ = phase_cross_correlation(ga, gb, upsample_factor=10)
    except Exception:  # noqa: BLE001
        return 0.0, 0.0, before, before
    dy, dx = float(sh[0]), float(sh[1])
    if abs(dy) > max_px or abs(dx) > max_px:
        return 0.0, 0.0, before, before
    from scipy.ndimage import shift as nd_shift

    after = ncc(ga, nd_shift(gb, (dy, dx), order=1, mode="nearest"))
    if after <= before:
        return 0.0, 0.0, before, before
    return dy, dx, before, after
