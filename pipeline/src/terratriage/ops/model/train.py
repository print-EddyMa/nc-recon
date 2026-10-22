"""Fit the damage model on TRAIN boxes; select and calibrate on a spatial split.

`python -m terratriage.ops.model.train --boxes palisades_west palisades_east --incident Palisades`

Model selection (best epoch) and the temperature that calibrates the
probabilities both use only the validation blocks of the TRAIN boxes. The
held-out event (Eaton) is never read here.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

import numpy as np

from . import LEVELS, MODEL_DIR
from .dataset import dins_points, is_val, labels, read_chips

# A building fills the middle of the chip; at 48 m an undamaged house in a
# burned street is mostly burned neighbours, and the model learned the street
# (Palisades validation, 2026-10-22). 32 m keeps the building dominant.
CHIP_M, CHIP_PX = 32.0, 64


def load_box(name: str, incident: str, chip_m: float = CHIP_M, px: int = CHIP_PX) -> dict[str, Any]:
    d = os.path.join(MODEL_DIR, "imagery", name)
    cache = os.path.join(MODEL_DIR, "chips", f"{name}_{int(chip_m)}m_{px}px.npz")
    with open(os.path.join(d, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True)
        return {"pre": z["pre"], "post": z["post"], "points": list(z["points"]), "meta": meta}
    pts = dins_points(tuple(meta["bbox"]), incident)
    pre, post, kept = read_chips(os.path.join(d, "pre.tif"), os.path.join(d, "post.tif"), pts, chip_m=chip_m, px=px)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    np.savez_compressed(cache, pre=pre, post=post, points=np.array(kept, dtype=object))
    return {"pre": pre, "post": post, "points": kept, "meta": meta}


def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    """y true levels, p (N, 5) probabilities."""
    k = len(LEVELS)
    pred = p.argmax(1)
    cm = np.zeros((k, k), int)
    for a, b in zip(y, pred):
        cm[a, b] += 1
    present = [i for i in range(k) if cm[i].sum()]
    f1s = []
    for i in present:
        tp = cm[i, i]
        prec = tp / max(1, cm[:, i].sum())
        rec = tp / max(1, cm[i].sum())
        f1s.append(0.0 if tp == 0 else 2 * prec * rec / (prec + rec))
    sev_t = y >= 3
    sev_p = pred >= 3
    tp = int((sev_t & sev_p).sum())
    prec = tp / max(1, int(sev_p.sum()))
    rec = tp / max(1, int(sev_t.sum()))
    nll = float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-9, 1))))
    d_t, d_p = y == 4, pred == 4
    tpr = float((d_t & d_p).sum() / max(1, d_t.sum()))
    tnr = float((~d_t & ~d_p).sum() / max(1, (~d_t).sum()))
    return {"n": int(len(y)), "accuracy": round(float((pred == y).mean()), 3),
            "destroyed_vs_rest_balanced_accuracy": round((tpr + tnr) / 2, 3),
            "destroyed_recall": round(tpr, 3), "not_destroyed_recall": round(tnr, 3),
            "macro_f1_present_levels": round(float(np.mean(f1s)), 3),
            "major_or_destroyed": {"precision": round(prec, 3), "recall": round(rec, 3),
                                   "f1": round(0.0 if tp == 0 else 2 * prec * rec / (prec + rec), 3),
                                   "true": int(sev_t.sum()), "called": int(sev_p.sum())},
            "nll": round(nll, 4), "confusion_rows_true_cols_pred": cm.tolist(), "levels": list(LEVELS)}


def _augment(pre, post, rng):
    import torch

    k = int(rng.integers(4))
    pre, post = torch.rot90(pre, k, (2, 3)), torch.rot90(post, k, (2, 3))
    if rng.random() < 0.5:
        pre, post = pre.flip(3), post.flip(3)
    # the two sensors differ in colour and gain; and alignment is never perfect
    for t in (pre, post):
        t.mul_(torch.empty(t.shape[0], 1, 1, 1).uniform_(0.8, 1.2)).add_(
            torch.empty(t.shape[0], 1, 1, 1).uniform_(-0.06, 0.06)).clamp_(0, 1)
    dx, dy = (int(v) for v in rng.integers(-4, 5, size=2))
    post = torch.roll(post, (dy, dx), (2, 3))
    return pre, post


def predict(model, pre: np.ndarray, post: np.ndarray, device, T: float = 1.0, bs: int = 128) -> np.ndarray:
    import torch

    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(pre), bs):
            a = torch.from_numpy(pre[i:i + bs]).float().div(255).to(device)
            b = torch.from_numpy(post[i:i + bs]).float().div(255).to(device)
            out.append(torch.softmax(model(a, b) / T, 1).cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, len(LEVELS)))


def fit_temperature(logp_fn, y) -> float:
    best, bt = 1e9, 1.0
    for T in np.linspace(0.5, 8.0, 76):
        p = logp_fn(T)
        nll = float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-9, 1))))
        if nll < best:
            best, bt = nll, float(T)
    return bt


def _balanced(idx: np.ndarray, y: np.ndarray, rng) -> np.ndarray:
    """An epoch's order with Destroyed and everything else drawn equally often:
    the burned majority would otherwise teach "always Destroyed"."""
    sev = idx[y[idx] == 4]
    rest = idx[y[idx] != 4]
    n = max(len(sev), len(rest))
    take = np.concatenate([rng.choice(sev, n, replace=len(sev) < n), rng.choice(rest, n, replace=len(rest) < n)])
    return rng.permutation(take)


def train(boxes: list[str], incident: str, *, epochs: int = 12, pretrained: bool = True,
          seed: int = 0, tag: str = "groma-dmg-v0") -> dict[str, Any]:
    import torch
    from torch import nn

    from .net import Siamese

    t0 = time.time()
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    pre, post, pts = [], [], []
    sources = []
    for b in boxes:
        d = load_box(b, incident)
        pre.append(d["pre"])
        post.append(d["post"])
        pts += d["points"]
        sources.append({"box": b, **{k: d["meta"][k] for k in ("bbox", "pre", "post", "incident")},
                        "chips": len(d["points"])})
    pre, post = np.concatenate(pre), np.concatenate(post)
    y = labels(pts)
    val = np.array([is_val(p["lon"], p["lat"]) for p in pts])
    tr_idx, va_idx = np.nonzero(~val)[0], np.nonzero(val)[0]
    counts = np.bincount(y[tr_idx], minlength=len(LEVELS)).astype(float)
    w = np.where(counts > 0, 1.0 / np.sqrt(np.maximum(counts, 1)), 0.0)
    w = w / w[counts > 0].mean()
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = Siamese(len(LEVELS), pretrained=pretrained).to(device)
    opt = torch.optim.AdamW([{"params": model.enc.parameters(), "lr": 5e-5},
                             {"params": model.head.parameters(), "lr": 5e-4}], weight_decay=1e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    # balanced sampling already evens Destroyed against the rest; mild weights
    # keep the rare middle levels from vanishing
    loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(np.sqrt(w), dtype=torch.float32, device=device))
    best = {"score": -1.0}
    out_dir = os.path.join(MODEL_DIR, "weights")
    os.makedirs(out_dir, exist_ok=True)
    wpath = os.path.join(out_dir, f"{tag}.pt")
    history = []
    for ep in range(epochs):
        model.train()
        perm = _balanced(tr_idx, y, rng)
        tot = 0.0
        for i in range(0, len(perm), 64):
            j = perm[i:i + 64]
            a = torch.from_numpy(pre[j]).float().div(255)
            b = torch.from_numpy(post[j]).float().div(255)
            a, b = _augment(a, b, rng)
            logits = model(a.to(device), b.to(device))
            loss = loss_fn(logits, torch.from_numpy(y[j]).to(device))
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss) * len(j)
        sched.step()
        pv = predict(model, pre[va_idx], post[va_idx], device)
        m = metrics(y[va_idx], pv)
        # balanced accuracy, Destroyed vs the rest: "always Destroyed" scores 0.5
        score = m["destroyed_vs_rest_balanced_accuracy"] + 0.25 * m["macro_f1_present_levels"]
        history.append({"epoch": ep + 1, "train_loss": round(tot / max(1, len(perm)), 4), "val": {
            k: m[k] for k in ("accuracy", "destroyed_vs_rest_balanced_accuracy", "destroyed_recall",
                              "not_destroyed_recall", "macro_f1_present_levels", "nll")}})
        print(json.dumps(history[-1]), flush=True)
        if score > best["score"]:
            best = {"score": score, "epoch": ep + 1}
            torch.save(model.state_dict(), wpath)
    model.load_state_dict(torch.load(wpath, map_location=device))
    T = fit_temperature(lambda t: predict(model, pre[va_idx], post[va_idx], device, T=t), y[va_idx])
    val_m = metrics(y[va_idx], predict(model, pre[va_idx], post[va_idx], device, T=T))
    card = {
        "model": tag, "architecture": "Siamese ResNet-18 encoder (shared), head on [post, post - pre]",
        "init": "torchvision ImageNet weights" if pretrained else "random (from scratch)",
        "chip": {"metres": CHIP_M, "pixels": CHIP_PX}, "classes": list(LEVELS), "temperature": T,
        "trained_on": sources, "label_source": "CAL FIRE DINS (incident " + incident + ")",
        "split": "spatial: 300 m blocks, one in five to validation",
        "sampling": "balanced: Destroyed and all other levels drawn equally often each epoch",
        "train_chips": int(len(tr_idx)), "val_chips": int(len(va_idx)),
        "train_label_counts": {LEVELS[i]: int(c) for i, c in enumerate(counts)},
        "best_epoch": best["epoch"], "validation": val_m, "history": history,
        "held_out_never_read": ["Eaton fire (DR-4856 altadena TEST area)"],
        "device": str(device), "train_seconds": round(time.time() - t0),
    }
    with open(os.path.join(out_dir, f"{tag}.json"), "w", encoding="utf-8") as fh:
        json.dump(card, fh, indent=1)
    return card


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m terratriage.ops.model.train")
    ap.add_argument("--boxes", nargs="+", required=True)
    ap.add_argument("--incident", required=True)
    ap.add_argument("--epochs", type=int, default=14)
    ap.add_argument("--scratch", action="store_true", help="no ImageNet initialisation")
    ap.add_argument("--tag", default="groma-dmg-v0")
    a = ap.parse_args(argv)
    card = train(a.boxes, a.incident, epochs=a.epochs, pretrained=not a.scratch, tag=a.tag)
    print(json.dumps({k: card[k] for k in ("model", "best_epoch", "temperature", "validation")}, indent=1))


if __name__ == "__main__":
    main()
