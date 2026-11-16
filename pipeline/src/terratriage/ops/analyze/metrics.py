"""Evaluation metrics for ordinal damage classes, with spatial-cluster bootstrap CIs.

Everything takes integer class arrays (0..K-1) and, where relevant, (N,K)
probability arrays. Nothing here invents a number: a metric that cannot be
computed (e.g. recall of a class with no truth examples) is None.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np


def confusion(y_true, y_pred, k: int) -> np.ndarray:
    m = np.zeros((k, k), dtype=int)
    for t, p in zip(y_true, y_pred):
        m[int(t), int(p)] += 1
    return m


def per_class(cm: np.ndarray) -> list[dict[str, float | None]]:
    out = []
    for c in range(cm.shape[0]):
        tp = cm[c, c]
        fp = cm[:, c].sum() - tp
        fn = cm[c, :].sum() - tp
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else (0.0 if (prec is not None and rec is not None) else None)
        out.append({"precision": prec, "recall": rec, "f1": f1, "support": int(cm[c, :].sum())})
    return out


def macro_f1(cm: np.ndarray) -> float | None:
    f = [r["f1"] for r in per_class(cm) if r["support"] > 0 and r["f1"] is not None]
    return float(np.mean(f)) if f else None


def quadratic_weighted_kappa(y_true, y_pred, k: int) -> float | None:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    if len(y_true) == 0:
        return None
    o = confusion(y_true, y_pred, k).astype(float)
    w = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)], dtype=float) / (k - 1) ** 2
    e = np.outer(o.sum(axis=1), o.sum(axis=0)) / o.sum()
    denom = (w * e).sum()
    return None if denom == 0 else float(1 - (w * o).sum() / denom)


def binary_f1(y_true, y_pred, positive: Callable[[np.ndarray], np.ndarray]) -> float | None:
    t, p = positive(np.asarray(y_true)), positive(np.asarray(y_pred))
    tp = int((t & p).sum())
    fp = int((~t & p).sum())
    fn = int((t & ~p).sum())
    if tp + fp == 0 or tp + fn == 0:
        return None
    prec, rec = tp / (tp + fp), tp / (tp + fn)
    return 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)


def recall_of(y_true, y_pred, cls: int) -> float | None:
    t = np.asarray(y_true) == cls
    if not t.any():
        return None
    return float((np.asarray(y_pred)[t] == cls).mean())


def ece(probs: np.ndarray, y_true, n_bins: int = 10) -> tuple[float | None, list[dict[str, Any]]]:
    """Expected calibration error of the top-class probability + reliability bins."""
    probs = np.asarray(probs, dtype=float)
    y_true = np.asarray(y_true)
    if len(y_true) == 0:
        return None, []
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    correct = pred == y_true
    edges = np.linspace(0, 1, n_bins + 1)
    total, bins = 0.0, []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if not m.any():
            bins.append({"lo": lo, "hi": hi, "n": 0, "conf": None, "acc": None})
            continue
        c, a = float(conf[m].mean()), float(correct[m].mean())
        total += m.mean() * abs(c - a)
        bins.append({"lo": round(lo, 2), "hi": round(hi, 2), "n": int(m.sum()), "conf": c, "acc": a})
    return float(total), bins


def nll(probs: np.ndarray, y_true) -> float:
    p = np.clip(np.asarray(probs)[np.arange(len(y_true)), np.asarray(y_true)], 1e-12, 1)
    return float(-np.log(p).mean())


def summary(y_true, y_pred, k: int, probs: np.ndarray | None = None,
            destroyed: int | None = None, major: int | None = None) -> dict[str, Any]:
    y_true, y_pred = np.asarray(y_true, dtype=int), np.asarray(y_pred, dtype=int)
    destroyed = k - 1 if destroyed is None else destroyed
    major = k - 2 if major is None else major
    cm = confusion(y_true, y_pred, k)
    out: dict[str, Any] = {
        "n": int(len(y_true)),
        "accuracy": float((y_true == y_pred).mean()) if len(y_true) else None,
        "confusion": cm.tolist(),
        "per_class": per_class(cm),
        "macro_f1": macro_f1(cm),
        "qwk": quadratic_weighted_kappa(y_true, y_pred, k),
        "destroyed_recall": recall_of(y_true, y_pred, destroyed),
        "ge_major_f1": binary_f1(y_true, y_pred, lambda a: a >= major),
    }
    if probs is not None and len(y_true):
        e, bins = ece(probs, y_true)
        out["ece"] = e
        out["reliability"] = bins
        out["nll"] = nll(probs, y_true)
    return out


def cluster_bootstrap(
    stat: Callable[[np.ndarray], float | None],
    clusters,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float | None, float | None]:
    """(lo, hi) percentile CI of `stat(idx)` resampling whole spatial clusters.

    Buildings next to each other share imagery, terrain and damage; resampling
    them independently gives CIs that are far too narrow.
    """
    clusters = np.asarray(clusters)
    uniq = np.unique(clusters)
    if len(uniq) < 2:
        return None, None
    members = {c: np.flatnonzero(clusters == c) for c in uniq}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([members[c] for c in pick])
        v = stat(idx)
        if v is not None and np.isfinite(v):
            vals.append(v)
    if len(vals) < n_boot * 0.5:
        return None, None
    return float(np.quantile(vals, alpha / 2)), float(np.quantile(vals, 1 - alpha / 2))


def grid_clusters(lons, lats, cell_m: float = 250.0) -> np.ndarray:
    """Assign each point to a ~cell_m square grid cell (spatial blocks for bootstrap)."""
    lons, lats = np.asarray(lons), np.asarray(lats)
    lat0 = float(np.mean(lats)) if len(lats) else 35.5
    dx = cell_m / (111_320 * np.cos(np.radians(lat0)))
    dy = cell_m / 110_574
    gx = np.floor(lons / dx).astype(np.int64)
    gy = np.floor(lats / dy).astype(np.int64)
    return gx * 1_000_003 + gy
