"""A weight-free stand-in that satisfies the same interface as `ensemble.Ensemble`.

This is NOT the xView2 CNN. It is a transparent change-detection heuristic:

  * localisation  = local structure (gradient energy + high-pass) of the PRE
    image, which lights up roofs/roads/edges in built-up areas;
  * damage        = robustly-normalised pre/post pixel difference mapped onto the
    4-class scale (more change -> more severe).

It exists so the full pipeline (tiling -> fusion -> polygonisation -> GeoJSON)
and the web app can be exercised end-to-end today, and as an honest fallback if
the trained checkpoints can't be obtained. Anything it produces is labelled
`model: "heuristic:change-detection"` in the run metadata so it is never mistaken
for the real thing.
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
    _HAVE_CV2 = True
except Exception:  # pragma: no cover
    _HAVE_CV2 = False


def _gray(rgb: np.ndarray) -> np.ndarray:
    return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]).astype("float32")


def _blur(a: np.ndarray, k: int = 9) -> np.ndarray:
    if _HAVE_CV2:
        return cv2.GaussianBlur(a, (k, k), 0)
    # cheap separable box blur fallback
    pad = k // 2
    ap = np.pad(a, pad, mode="reflect")
    csum = np.cumsum(np.cumsum(ap, axis=0), axis=1)
    csum = np.pad(csum, ((1, 0), (1, 0)))
    s = (csum[k:, k:] - csum[:-k, k:] - csum[k:, :-k] + csum[:-k, :-k])
    return (s / (k * k)).astype("float32")


def _norm(a: np.ndarray, lo=2, hi=98) -> np.ndarray:
    p1, p99 = np.percentile(a, [lo, hi])
    if p99 <= p1:
        return np.zeros_like(a)
    return np.clip((a - p1) / (p99 - p1), 0, 1)


class MockEnsemble:
    name = "heuristic:change-detection"

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self.loc = [object()]   # non-empty so callers that len()-check are happy
        self.cls = [object()]

    def predict_tile(self, pre_rgb: np.ndarray, post_rgb: np.ndarray):
        H, W = pre_rgb.shape[:2]
        gpre, gpost = _gray(pre_rgb), _gray(post_rgb)

        # --- localisation: structure energy of the PRE image ---
        gx = np.gradient(gpre, axis=1)
        gy = np.gradient(gpre, axis=0)
        grad = np.hypot(gx, gy)
        highpass = np.abs(gpre - _blur(gpre, 15))
        struct = _norm(_blur(grad, 7)) * 0.6 + _norm(_blur(highpass, 7)) * 0.4
        # suppress uniform bright vegetation/fields: require local contrast
        loc_prob = np.clip(struct * 1.4, 0, 1).astype("float32")

        # --- damage: normalised pre/post difference ---
        diff_rgb = np.abs(pre_rgb.astype("float32") - post_rgb.astype("float32")).mean(axis=2)
        struct_diff = np.abs(_norm(_blur(np.hypot(*np.gradient(gpre)), 7))
                             - _norm(_blur(np.hypot(*np.gradient(gpost)), 7)))
        change = _norm(_blur(diff_rgb, 9)) * 0.6 + _norm(_blur(struct_diff, 9)) * 0.4
        change = np.clip(change, 0, 1)

        # map change -> class weights (1..4). smooth, monotone in `change`.
        c = change[..., None]
        w1 = np.clip(1.3 - 2.0 * c, 0.02, None)          # no-damage
        w2 = np.clip(1.0 - np.abs(c - 0.33) * 2.4, 0.02, None)
        w3 = np.clip(1.0 - np.abs(c - 0.60) * 2.4, 0.02, None)
        w4 = np.clip(2.0 * (c - 0.55), 0.02, None) ** 1.5  # destroyed
        wsum = w1 + w2 + w3 + w4
        cls_prob = np.concatenate(
            [(1.0 - loc_prob)[..., None], (loc_prob[..., None]) * np.concatenate([w1, w2, w3, w4], axis=2) / wsum],
            axis=2,
        ).astype("float32")
        return loc_prob, cls_prob
