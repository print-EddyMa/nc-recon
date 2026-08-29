"""Load the xView2 1st-place checkpoints into the modern (ported) architectures
and run tiled, test-time-augmented inference on CPU or GPU.

The original solution is a 16-model ensemble (4 encoder families x 3-4 folds, for
both localisation and damage classification) that expects 2x12GB GPUs. That is
not runnable here as-is, so this module:

  * reconstructs each architecture with `terratriage.models.unet` (pure torch, no
    apex, no imagenet download),
  * loads the published `state_dict`s (DataParallel `module.` prefix stripped,
    size-mismatched tensors skipped exactly as the reference `predict*.py` does),
  * exposes small, named PRESETS so a laptop can run a 2-model subset in ~seconds
    per tile while the full paper ensemble stays one flag away.

Preprocessing and the loc/cls fusion match the reference bit-for-bit
(`utils.preprocess_inputs`, `create_submission.process_image`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

import numpy as np
import torch

from .unet import (
    Res34_Unet_Loc, Res34_Unet_Double,
    SeResNext50_Unet_Loc, SeResNext50_Unet_Double,
    Dpn92_Unet_Loc, Dpn92_Unet_Double,
    SeNet154_Unet_Loc, SeNet154_Unet_Double,
)

# checkpoint basename (from the weights zip) -> architecture class
LOC_MODELS = {
    "res34_loc_{s}_1_best": Res34_Unet_Loc,
    "res50_loc_{s}_tuned_best": SeResNext50_Unet_Loc,
    "dpn92_loc_{s}_tuned_best": Dpn92_Unet_Loc,
    "se154_loc_{s}_1_best": SeNet154_Unet_Loc,
}
CLS_MODELS = {
    "res34_cls2_{s}_tuned_best": Res34_Unet_Double,
    "res50_cls_cce_{s}_tuned_best": SeResNext50_Unet_Double,
    "dpn92_cls_cce_{s}_tuned_best": Dpn92_Unet_Double,
    "se154_cls_cce_{s}_tuned_best": SeNet154_Unet_Double,
}

# preset -> (loc basename patterns, cls basename patterns, seeds)
PRESETS: dict[str, dict] = {
    "fast":     {"loc": ["res34_loc_{s}_1_best"],
                 "cls": ["res34_cls2_{s}_tuned_best"],
                 "seeds": [0]},
    "balanced": {"loc": ["res34_loc_{s}_1_best", "res50_loc_{s}_tuned_best"],
                 "cls": ["res34_cls2_{s}_tuned_best", "res50_cls_cce_{s}_tuned_best"],
                 "seeds": [0]},
    "strong":   {"loc": list(LOC_MODELS),
                 "cls": ["res34_cls2_{s}_tuned_best", "res50_cls_cce_{s}_tuned_best",
                         "dpn92_cls_cce_{s}_tuned_best"],
                 "seeds": [0, 1, 2]},
    "full":     {"loc": list(LOC_MODELS), "cls": list(CLS_MODELS), "seeds": [0, 1, 2]},
}

# _thr from create_submission.py
LOC_THR = (0.38, 0.13, 0.14)


def _strip_module(sd: dict) -> dict:
    return {k[7:] if k.startswith("module.") else k: v for k, v in sd.items()}


def load_checkpoint(model: torch.nn.Module, path: str) -> torch.nn.Module:
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    loaded = _strip_module(ckpt["state_dict"] if "state_dict" in ckpt else ckpt)
    tgt = model.state_dict()
    kept = 0
    for k in tgt:
        if k in loaded and tgt[k].size() == loaded[k].size():
            tgt[k] = loaded[k]
            kept += 1
    model.load_state_dict(tgt)
    if kept / max(len(tgt), 1) < 0.5:
        raise RuntimeError(f"{os.path.basename(path)}: only {kept}/{len(tgt)} tensors matched "
                           "- architecture/checkpoint mismatch")
    model.eval()
    return model


def preprocess(img: np.ndarray) -> np.ndarray:
    """(H,W,C) uint8 -> float32 in [-1, 1], the reference `x/127 - 1`."""
    x = img.astype("float32")
    x /= 127.0
    x -= 1.0
    return x


def _tta_batch(x: np.ndarray) -> torch.Tensor:
    """x: (H,W,C) -> (4,C,H,W): identity, flip-ud, flip-lr, rot180."""
    variants = [x, x[::-1, ...], x[:, ::-1, ...], x[::-1, ::-1, ...]]
    arr = np.ascontiguousarray(np.stack(variants).transpose(0, 3, 1, 2))
    return torch.from_numpy(arr).float()


def _untta(pred: np.ndarray) -> np.ndarray:
    """pred: (4,C,H,W) probs -> mean over the un-flipped variants, (C,H,W)."""
    out = np.stack([
        pred[0],
        pred[1, :, ::-1, :],
        pred[2, :, :, ::-1],
        pred[3, :, ::-1, ::-1],
    ])
    return out.mean(axis=0)


@dataclass
class Ensemble:
    loc: list[torch.nn.Module]
    cls: list[torch.nn.Module]
    device: str = "cpu"
    to_bgr: bool = True   # reference reads with cv2 (BGR); match that channel order

    def _prep_pair(self, pre_rgb: np.ndarray, post_rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        pre = pre_rgb[..., ::-1] if self.to_bgr else pre_rgb
        post = post_rgb[..., ::-1] if self.to_bgr else post_rgb
        return preprocess(pre), preprocess(post)

    @torch.no_grad()
    def predict_tile(self, pre_rgb: np.ndarray, post_rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Returns (loc_prob (H,W) in [0,1], cls_prob (H,W,5) in [0,1])."""
        pre, post = self._prep_pair(pre_rgb, post_rgb)
        H, W = pre.shape[:2]

        loc_acc = np.zeros((H, W), "float32")
        for m in self.loc:
            batch = _tta_batch(pre).to(self.device)
            p = torch.sigmoid(m(batch)).cpu().numpy()          # (4,1,H,W)
            loc_acc += _untta(p)[0]
        loc_prob = loc_acc / max(len(self.loc), 1)

        cls_acc = np.zeros((5, H, W), "float32")
        for m in self.cls:
            x6 = np.concatenate([pre, post], axis=2)
            batch = _tta_batch(x6).to(self.device)
            p = torch.sigmoid(m(batch)).cpu().numpy()          # (4,5,H,W)
            cls_acc += _untta(p)
        cls_prob = (cls_acc / max(len(self.cls), 1)).transpose(1, 2, 0)  # (H,W,5)

        return loc_prob, cls_prob


def fuse(loc_prob: np.ndarray, cls_prob: np.ndarray, thr=LOC_THR):
    """Reference fusion from create_submission.process_image.

    Returns (loc_mask uint8 0/1, dmg_mask uint8 0..4, dmg_conf float 0..1).
    """
    from skimage.morphology import square, dilation

    dmg = cls_prob[..., 1:].argmax(axis=2) + 1                 # 1..4
    loc_mask = (
        (loc_prob > thr[0])
        | ((loc_prob > thr[1]) & (dmg > 1) & (dmg < 4))
        | ((loc_prob > thr[2]) & (dmg > 1))
    ).astype("uint8")
    dmg = dmg * loc_mask
    m2 = dmg == 2
    if m2.sum() > 0:
        m2 = dilation(m2, square(5))
        dmg[m2 & (dmg == 1)] = 2
    conf = cls_prob[..., 1:].max(axis=2)
    return loc_mask, dmg.astype("uint8"), conf.astype("float32")


def build(weights_dir: str, preset: str = "fast", device: str = "cpu") -> Ensemble:
    if preset not in PRESETS:
        raise KeyError(f"unknown preset {preset!r}; choose from {list(PRESETS)}")
    if not os.path.isdir(weights_dir):
        raise FileNotFoundError(
            f"weights dir {weights_dir!r} not found. Unzip xview2_1st_weights.zip there "
            "(see pipeline/weights/README.md)."
        )
    cfg = PRESETS[preset]
    torch.set_num_threads(max(1, min(4, (os.cpu_count() or 4))))

    def _load(patterns, table):
        out = []
        for pat in patterns:
            for s in cfg["seeds"]:
                name = pat.format(s=s)
                path = os.path.join(weights_dir, name)
                if not os.path.exists(path):
                    # some folds only ship one seed; skip quietly unless nothing loads
                    continue
                out.append(load_checkpoint(table[pat](), path).to(device))
        return out

    loc = _load(cfg["loc"], LOC_MODELS)
    cls = _load(cfg["cls"], CLS_MODELS)
    if not loc or not cls:
        have = sorted(os.listdir(weights_dir))[:20]
        raise RuntimeError(
            f"preset {preset!r}: loaded {len(loc)} loc / {len(cls)} cls models. "
            f"weights dir contains: {have} ..."
        )
    return Ensemble(loc=loc, cls=cls, device=device)
