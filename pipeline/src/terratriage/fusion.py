"""Multi-source fusion for per-building confidence tiering (Phase D2).

The single CNN gives one class and a softmax probability. That is opaque: a
building the model is genuinely unsure about looks the same in the output as one
it is confident about. Following the pattern humanitarian mappers use (HOT's
fAIr fuses independent damage sources and routes disagreement to human review),
we run a second, independent pass, the change-detection heuristic, and turn
*agreement between the two* into a tier:

  high    the two backends land within one damage level of each other
  review  they disagree by two or more levels, the footprint is too small to
          classify, or the CNN's softmax is genuinely undecided

`review` buildings are what the Phase D3 web review queue lists for a human to
confirm or override. The reported `damage_class` is still the CNN's — the
heuristic only informs confidence, it does not outvote a trained model.
"""
from __future__ import annotations

import json
import os
from typing import Any

# CNN top1-minus-top2 probability gap. >= DECISIVE and a 1-level disagreement is
# still "high"; < UNSURE forces "review" regardless of agreement.
MARGIN_DECISIVE = 0.20
MARGIN_UNSURE = 0.10
# footprints smaller than this (m^2) are classified off a handful of pixels
MIN_TRUSTWORTHY_AREA = 12.0


def _apply_calibration() -> None:
    """Let `scripts/calibrate.py` tune the tier thresholds without a code edit.

    Reads TERRATRIAGE_CALIBRATION (or pipeline/data/calibration.json):
      {"margin_decisive": 0.22, "margin_unsure": 0.08, "min_area": 12.0}
    """
    global MARGIN_DECISIVE, MARGIN_UNSURE, MIN_TRUSTWORTHY_AREA
    path = os.environ.get("TERRATRIAGE_CALIBRATION") or os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "calibration.json"
    )
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        MARGIN_DECISIVE = float(cfg.get("margin_decisive", MARGIN_DECISIVE))
        MARGIN_UNSURE = float(cfg.get("margin_unsure", MARGIN_UNSURE))
        MIN_TRUSTWORTHY_AREA = float(cfg.get("min_area", MIN_TRUSTWORTHY_AREA))
    except (OSError, ValueError, TypeError) as ex:
        if not isinstance(ex, FileNotFoundError):
            print(f"[fusion] ignoring bad calibration.json: {ex}")
        return
    print(
        f"[fusion] calibration applied: decisive={MARGIN_DECISIVE} "
        f"unsure={MARGIN_UNSURE} min_area={MIN_TRUSTWORTHY_AREA}"
    )


_apply_calibration()


def tier_for(
    heur_cls: int,
    cnn_cls: int,
    cnn_margin: float,
    area_m2: float,
) -> str:
    """Return "high" or "review" for one building.

    The primary signal is agreement between the CNN and the change-detection
    pass. A gap of 0 or 1 level (e.g. minor vs. none) does not change where a
    responder goes, so it stays "high"; a gap of 2+ (e.g. destroyed vs. none)
    is a real conflict about severity and goes to a human.
    """
    if area_m2 < MIN_TRUSTWORTHY_AREA:
        return "review"
    if cnn_margin < MARGIN_UNSURE:
        return "review"
    return "high" if abs(heur_cls - cnn_cls) <= 1 else "review"


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


def retier_with_priors(
    cnn_cls: int,
    cnn_margin: float,
    tier: str,
    sources: dict[str, Any],
    priors: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Nudge one building's tier using NC context priors (see context.nc_priors).

    Priors only move *borderline* calls and never override the CNN's class.
    They act only on a specific, local signal, a real moderate-or-worse flood
    stage at the nearest gauge or steep terrain, not on the fact that the whole
    county sits inside a federal declaration (which would flag almost every
    building):
      - a moderate+ flood stage nearby, the model already says damage, and the
        call is a borderline `review` -> promote to `high` (corroborated)
      - a moderate+ flood stage nearby but the model says "no damage" ->
        demote `high` to `review` for a second look (flood-contradicted)
      - steep terrain plus a "destroyed" call sitting in `review` -> `high`
    """
    if not priors:
        return tier, sources
    flood = priors.get("flood_stage")
    fema = bool(priors.get("in_fema_decl"))
    slope = priors.get("slope_deg")
    flood_signal = isinstance(flood, (int, float)) and flood >= 2
    out = dict(sources)
    out["priors"] = {"flood_stage": flood, "in_fema_decl": fema, "slope_deg": slope}
    new_tier = tier

    if flood_signal and cnn_cls >= 1 and tier == "review" and cnn_margin >= MARGIN_UNSURE:
        new_tier = "high"
        out["prior_effect"] = "corroborated"
    elif flood_signal and cnn_cls == 0 and tier == "high":
        new_tier = "review"
        out["prior_effect"] = "flood-contradicted"
    elif isinstance(slope, (int, float)) and slope >= 20 and cnn_cls == 3 and tier == "review":
        new_tier = "high"
        out["prior_effect"] = "terrain"
    return new_tier, out


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
