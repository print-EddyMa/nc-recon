"""Temperature scaling (Guo et al. 2017) and split-conformal prediction sets.

Both are *fit on TUNE areas only*. A fit records which areas and how many
labels it used; `fit_temperature` refuses any TEST-area label outright.
Until a fit exists, the pipeline reports `calibration: none` and treats model
probabilities as uncalibrated (it does not pretend otherwise).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import numpy as np

from .. import CONFIG_DIR

CAL_DIR = os.environ.get("NCR_CALIBRATION_DIR") or os.path.join(CONFIG_DIR, "calibration")


def softmax(z: np.ndarray, T: float = 1.0) -> np.ndarray:
    z = np.asarray(z, dtype=float) / T
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _nll_T(logits: np.ndarray, y: np.ndarray, T: float) -> float:
    p = softmax(logits, T)[np.arange(len(y)), y]
    return float(-np.log(np.clip(p, 1e-12, 1)).mean())


def fit_temperature(logits, y, roles: list[str] | None = None) -> float:
    """1-D NLL minimisation over T in [0.05, 20] (golden-section on log T)."""
    if roles is not None and any(r != "TUNE" for r in roles):
        raise ValueError("temperature scaling may only be fit on TUNE-area labels")
    logits, y = np.asarray(logits, dtype=float), np.asarray(y, dtype=int)
    if len(y) < 20:
        raise ValueError(f"need >= 20 labels to fit a temperature, got {len(y)}")
    lo, hi = np.log(0.05), np.log(20.0)
    g = (np.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - g * (b - a), a + g * (b - a)
    for _ in range(80):
        if _nll_T(logits, y, np.exp(c)) < _nll_T(logits, y, np.exp(d)):
            b = d
        else:
            a = c
        c, d = b - g * (b - a), a + g * (b - a)
    return float(np.exp((a + b) / 2))


# --------------------------------------------------------------------------- #
# split-conformal adaptive prediction sets (APS)
# --------------------------------------------------------------------------- #
def aps_scores(probs: np.ndarray, y: np.ndarray, rng: np.random.Generator | None = None) -> np.ndarray:
    """Randomised APS nonconformity score of the true label."""
    rng = rng or np.random.default_rng(0)
    probs = np.asarray(probs, dtype=float)
    order = np.argsort(-probs, axis=1)
    sorted_p = np.take_along_axis(probs, order, axis=1)
    cum = np.cumsum(sorted_p, axis=1)
    rank = np.argmax(order == np.asarray(y)[:, None], axis=1)
    u = rng.random(len(y))
    return cum[np.arange(len(y)), rank] - u * sorted_p[np.arange(len(y)), rank]


def conformal_quantile(scores: np.ndarray, alpha: float = 0.10) -> float:
    n = len(scores)
    if n < 20:
        raise ValueError(f"need >= 20 calibration labels for conformal sets, got {n}")
    q = np.ceil((n + 1) * (1 - alpha)) / n
    return float(np.quantile(scores, min(q, 1.0), method="higher"))


def aps_sets(probs: np.ndarray, qhat: float) -> list[list[int]]:
    """Deterministic APS sets: smallest top-probability prefix with mass >= qhat."""
    probs = np.asarray(probs, dtype=float)
    out = []
    for row in probs:
        order = np.argsort(-row)
        cum = np.cumsum(row[order])
        k = int(np.searchsorted(cum, qhat, side="left")) + 1
        out.append(sorted(int(c) for c in order[: max(1, min(k, len(row)))]))
    return out


# --------------------------------------------------------------------------- #
# persistence
# --------------------------------------------------------------------------- #
def _path(model_id: str) -> str:
    return os.path.join(CAL_DIR, f"{model_id}.json")


def save(model_id: str, fit: dict[str, Any]) -> str:
    os.makedirs(CAL_DIR, exist_ok=True)
    fit = dict(fit)
    fit["fit_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(_path(model_id), "w", encoding="utf-8") as fh:
        json.dump(fit, fh, indent=2)
    return _path(model_id)


def load(model_id: str) -> dict[str, Any] | None:
    p = _path(model_id)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)
