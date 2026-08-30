"""Multi-source fusion for per-building confidence tiering (Phase D2).

The single CNN gives one class and a softmax probability. That is opaque: a
building the model is genuinely unsure about looks the same in the output as one
it is confident about. Following the pattern humanitarian mappers use (HOT's
fAIr fuses independent damage sources and routes disagreement to human review),
we run a second, independent pass — the change-detection heuristic — and turn
*agreement between the two* plus the CNN's own margin into a tier:

  high    both backends agree (or agree within one level and the CNN is decisive)
  review  they disagree, or the CNN is not decisive, or the footprint is tiny

`review` buildings are what the Phase D3 web review queue lists for a human to
confirm or override. The reported `damage_class` is still the CNN's — the
heuristic only informs confidence, it does not outvote a trained model.
"""
from __future__ import annotations

from typing import Any

# CNN top1-minus-top2 probability gap. >= DECISIVE and a 1-level disagreement is
# still "high"; < UNSURE forces "review" regardless of agreement.
MARGIN_DECISIVE = 0.20
MARGIN_UNSURE = 0.10
# footprints smaller than this (m^2) are classified off a handful of pixels
MIN_TRUSTWORTHY_AREA = 12.0


def tier_for(
    heur_cls: int,
    cnn_cls: int,
    cnn_margin: float,
    area_m2: float,
) -> str:
    """Return "high" or "review" for one building."""
    if area_m2 < MIN_TRUSTWORTHY_AREA:
        return "review"
    if cnn_margin < MARGIN_UNSURE:
        return "review"
    gap = abs(heur_cls - cnn_cls)
    if gap == 0:
        return "high"
    if gap == 1 and cnn_margin >= MARGIN_DECISIVE:
        return "high"
    return "review"


def fuse_one(
    heur: tuple[int, float],
    cnn: tuple[int, float],
    area_m2: float,
    cnn_margin: float | None = None,
) -> tuple[int, float, str, dict[str, Any]]:
    """Fuse one building's two backend results.

    heur / cnn are (class, confidence). `cnn_margin` is the CNN softmax
    top1-top2 gap when the caller has it; otherwise we approximate it from the
    CNN confidence (prob of the winning class -> gap vs. an even split of the
    rest).

    Returns (final_class, fused_confidence, tier, sources).
    """
    heur_cls, heur_conf = int(heur[0]), float(heur[1])
    cnn_cls, cnn_conf = int(cnn[0]), float(cnn[1])
    if cnn_margin is None:
        # p_win - (1 - p_win)/3  == (4 * p_win - 1) / 3, clamped to [0, 1]
        cnn_margin = max(0.0, min(1.0, (4.0 * cnn_conf - 1.0) / 3.0))

    tier = tier_for(heur_cls, cnn_cls, cnn_margin, area_m2)
    # fused confidence: CNN confidence, nudged up on agreement, down on conflict
    if heur_cls == cnn_cls:
        fused = min(1.0, cnn_conf + 0.10 * (1.0 - cnn_conf))
    else:
        fused = cnn_conf * (0.85 if abs(heur_cls - cnn_cls) == 1 else 0.7)
    sources = {
        "heuristic": heur_cls,
        "cnn": cnn_cls,
        "margin": round(cnn_margin, 4),
    }
    return cnn_cls, round(fused, 4), tier, sources


def fuse_scores(
    heur_scores: list[tuple[int, float]],
    cnn_scores: list[tuple[int, float]],
    areas_m2: list[float],
    cnn_margins: list[float] | None = None,
) -> list[tuple[int, float, str, dict[str, Any]]]:
    """Vectorised `fuse_one` over aligned per-building lists."""
    n = len(cnn_scores)
    if not (len(heur_scores) == len(areas_m2) == n):
        raise ValueError(
            f"fuse_scores length mismatch: heur={len(heur_scores)} "
            f"cnn={n} areas={len(areas_m2)}"
        )
    margins = cnn_margins or [None] * n
    return [
        fuse_one(heur_scores[i], cnn_scores[i], areas_m2[i], margins[i])
        for i in range(n)
    ]
