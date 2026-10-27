"""Groma damage model v0: frozen encoder features + a linear classifier.

`python -m terratriage.ops.model.linear --boxes palisades_west palisades_east --incident Palisades`

Fine-tuning the Siamese network on a few thousand chips overfit (training
loss 0.14, Palisades validation balanced accuracy 0.74, attempts 1-3 in
docs/model/MODEL_CARD.md). A frozen ImageNet ResNet-18 read of the before and
after chips, plus colour statistics of the chip centre, fed to a regularised
multinomial logistic regression, did far better on the same validation
blocks (0.95). Everything here was chosen on Palisades validation only.

The fitted model is stored as plain arrays (scaler mean and scale,
coefficients, intercepts) in an .npz with a JSON card: no pickles.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

import numpy as np

from . import LEVELS, MODEL_DIR
from .dataset import is_val, labels
from .train import CHIP_M, CHIP_PX, load_box, metrics

C = 0.01


def handcrafted(pre: np.ndarray, post: np.ndarray) -> np.ndarray:
    """Colour statistics of the central 12 m of each chip, and their change."""
    k = pre.shape[-1]
    lo, hi = int(k * 0.31), int(k * 0.69)
    out = []
    for a, b in zip(pre, post):
        f = []
        for img in (a, b):
            c = img[:, lo:hi, lo:hi].astype("float32") / 255
            s = c.max(0) - c.min(0)
            f += list(c.mean((1, 2))) + list(c.std((1, 2))) + [float(s.mean()), float((c.max(0) > 0.8).mean())]
        f.append(float(np.abs(b[:, lo:hi, lo:hi].astype("float32") - a[:, lo:hi, lo:hi]).mean() / 255))
        out.append(f)
    return np.asarray(out, "float32")


def embed(pre: np.ndarray, post: np.ndarray, bs: int = 256) -> np.ndarray:
    """Frozen ImageNet ResNet-18: [post, post - pre] (1024 values) per chip."""
    import torch

    from .net import Siamese

    from .fetch_encoder import encoder_path

    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    # local file only: no download while assessing (fetch_encoder.py stages it)
    m = Siamese(len(LEVELS), pretrained=False, encoder_path=encoder_path()).to(dev).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(pre), bs):
            a = torch.from_numpy(pre[i:i + bs]).float().div(255).to(dev)
            b = torch.from_numpy(post[i:i + bs]).float().div(255).to(dev)
            a = torch.nn.functional.interpolate(a, size=m.min_px, mode="bilinear", align_corners=False)
            b = torch.nn.functional.interpolate(b, size=m.min_px, mode="bilinear", align_corners=False)
            fa, fb = m.enc((a - m.mean) / m.std), m.enc((b - m.mean) / m.std)
            out.append(torch.cat([fb, fb - fa], 1).cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, 1024), "float32")


def features(pre: np.ndarray, post: np.ndarray) -> np.ndarray:
    return np.hstack([embed(pre, post), handcrafted(pre, post)])


def _fit(X: np.ndarray, y: np.ndarray):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    sc = StandardScaler().fit(X)
    clf = LogisticRegression(max_iter=5000, class_weight="balanced", C=C).fit(sc.transform(X), y)
    return sc, clf


def _proba(params: dict[str, np.ndarray], X: np.ndarray) -> np.ndarray:
    z = ((X - params["mean"]) / params["scale"]) @ params["coef"].T + params["intercept"]
    z -= z.max(1, keepdims=True)
    e = np.exp(z)
    p = e / e.sum(1, keepdims=True)
    out = np.zeros((len(X), len(LEVELS)))
    out[:, params["classes"].astype(int)] = p
    return out


def _params(sc, clf) -> dict[str, np.ndarray]:
    return {"mean": sc.mean_, "scale": sc.scale_, "coef": clf.coef_, "intercept": clf.intercept_,
            "classes": clf.classes_}


def fit(boxes: list[str], incident: str, tag: str = "groma-dmg-v0") -> dict[str, Any]:
    t0 = time.time()
    pre, post, pts, sources = [], [], [], []
    for b in boxes:
        d = load_box(b, incident, CHIP_M, CHIP_PX)
        pre.append(d["pre"])
        post.append(d["post"])
        pts += d["points"]
        sources.append({"box": b, **{k: d["meta"][k] for k in ("bbox", "pre", "post", "incident")},
                        "chips": len(d["points"])})
    pre, post = np.concatenate(pre), np.concatenate(post)
    y = labels(pts)
    val = np.array([is_val(p["lon"], p["lat"]) for p in pts])
    X = features(pre, post)
    sc, clf = _fit(X[~val], y[~val])
    val_m = metrics(y[val], _proba(_params(sc, clf), X[val]))
    # the final model also learns from the validation blocks, now that every
    # choice has been made
    sc, clf = _fit(X, y)
    wdir = os.path.join(MODEL_DIR, "weights")
    os.makedirs(wdir, exist_ok=True)
    np.savez(os.path.join(wdir, f"{tag}.npz"), **_params(sc, clf))
    card = {
        "model": tag, "kind": "frozen_linear",
        "architecture": "frozen ImageNet ResNet-18 features of before and after chips ([post, post - pre], "
                        "1024 values) + 15 colour statistics of the chip centre -> standardised multinomial "
                        "logistic regression, balanced class weights, C=" + str(C),
        "chip": {"metres": CHIP_M, "pixels": CHIP_PX}, "classes": list(LEVELS),
        "trained_on": sources, "label_source": f"CAL FIRE DINS (incident {incident})",
        "split": "spatial: 300 m blocks, one in five to validation; validation metrics below come from a fit "
                 "on the other blocks; the stored model was then refit on all blocks",
        "label_counts": {LEVELS[i]: int(c) for i, c in enumerate(np.bincount(y, minlength=len(LEVELS)))},
        "validation": val_m, "held_out_never_read": ["Eaton fire (DR-4856 altadena TEST area)"],
        "fit_seconds": round(time.time() - t0),
    }
    with open(os.path.join(wdir, f"{tag}.json"), "w", encoding="utf-8") as fh:
        json.dump(card, fh, indent=1)
    return card


def load(tag: str = "groma-dmg-v0") -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    wdir = os.path.join(MODEL_DIR, "weights")
    with open(os.path.join(wdir, f"{tag}.json"), encoding="utf-8") as fh:
        card = json.load(fh)
    z = np.load(os.path.join(wdir, f"{tag}.npz"))
    return {k: z[k] for k in z.files}, card


def predict(params: dict[str, np.ndarray], pre: np.ndarray, post: np.ndarray) -> np.ndarray:
    return _proba(params, features(pre, post))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m terratriage.ops.model.linear")
    ap.add_argument("--boxes", nargs="+", required=True)
    ap.add_argument("--incident", required=True)
    ap.add_argument("--tag", default="groma-dmg-v0")
    a = ap.parse_args(argv)
    card = fit(a.boxes, a.incident, a.tag)
    print(json.dumps({k: card[k] for k in ("model", "label_counts", "validation")}, indent=1))


if __name__ == "__main__":
    main()
