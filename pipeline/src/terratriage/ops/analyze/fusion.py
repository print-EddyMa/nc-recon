"""Fusion v1: weighted log-linear pooling of channel likelihoods, with abstention.

    log P(c | evidence) = log prior(c) + sum_k  w_k * log L_k(c)   (then softmax / T)

w_k = channel weight x quality x context. Each channel's contribution to the
winning class vs. the runner-up becomes a reason code, so every call can be
explained. A building is routed to human review (`needs_review`) when:
  * the top probability is below tau
  * the two most likely classes are not adjacent and the 2nd is substantial
  * the conformal prediction set (once fit) holds >= 3 classes
  * a key channel for the hazard is unavailable
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np
import yaml

from .. import CONFIG_DIR
from .classes import FEMA, K, class_prior

EPS = 1e-4


@lru_cache(maxsize=1)
def rules() -> dict[str, Any]:
    with open(os.path.join(CONFIG_DIR, "context_rules.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass
class Channel:
    id: str
    available: bool
    likelihood: np.ndarray | None = None      # (K,)
    weight: float = 1.0                        # config weight x quality x context
    status: str = "provisional"                # calibrated | provisional | rule | label_only
    reasons: list[str] = field(default_factory=list)
    unavailable_reason: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id, "available": self.available, "status": self.status,
            "weight": round(self.weight, 3), "reasons": self.reasons,
        }
        if self.likelihood is not None:
            d["likelihood"] = [round(float(v), 4) for v in self.likelihood]
        if self.unavailable_reason:
            d["unavailable_reason"] = self.unavailable_reason
        if self.detail:
            d["detail"] = self.detail
        return d


@dataclass
class Verdict:
    probs: np.ndarray
    label: int
    confidence: float
    needs_review: bool
    review_reasons: list[str]
    reasons: list[str]
    prediction_set: list[int] | None
    channels: list[Channel]

    def to_props(self) -> dict[str, Any]:
        return {
            "damage_level": FEMA[self.label],
            "damage_probs": {c: round(float(p), 4) for c, p in zip(FEMA, self.probs)},
            "confidence": round(self.confidence, 4),
            "needs_review": self.needs_review,
            "review_reasons": self.review_reasons,
            "prediction_set": None if self.prediction_set is None else [FEMA[i] for i in self.prediction_set],
            "reason_codes": self.reasons,
            "evidence": [c.to_dict() for c in self.channels],
            "evidence_unavailable": {c.id: c.unavailable_reason for c in self.channels if not c.available},
        }


def pool(channels: list[Channel], prior: np.ndarray | None = None, T: float = 1.0) -> np.ndarray:
    logp = np.log(prior if prior is not None else class_prior())
    for ch in channels:
        if ch.available and ch.likelihood is not None and ch.weight > 0:
            L = np.clip(np.asarray(ch.likelihood, float), EPS, None)
            L = L / L.sum()
            logp = logp + ch.weight * np.log(L)
    z = logp / T
    z = z - z.max()
    p = np.exp(z)
    return p / p.sum()


def _contribution_codes(channels: list[Channel], top: int, second: int) -> list[str]:
    out = []
    for ch in channels:
        if not ch.available or ch.likelihood is None or ch.weight <= 0:
            continue
        L = np.clip(np.asarray(ch.likelihood, float), EPS, None)
        L = L / L.sum()
        lo = ch.weight * (np.log(L[top]) - np.log(L[second]))
        if abs(lo) >= 0.1:
            sign = "FOR" if lo > 0 else "AGAINST"
            out.append(f"{ch.id}_{sign}_{FEMA[top].upper()}_{abs(lo):.2f}")
    return out


def decide(
    channels: list[Channel],
    *,
    key_channels: list[str] | None = None,
    T: float | None = None,
    qhat: float | None = None,
    extra_reasons: list[str] | None = None,
) -> Verdict:
    cfg = rules()["fusion"]
    ab = cfg["abstain"]
    T = T if T is not None else float(cfg.get("temperature", 1.0))
    probs = pool(channels, T=T)
    order = np.argsort(-probs)
    top, second = int(order[0]), int(order[1])
    review: list[str] = []
    if probs[top] < ab["tau"]:
        review.append(f"LOW_CONFIDENCE_{probs[top]:.2f}")
    if abs(top - second) > 1 and probs[second] >= ab["nonadjacent_top2_min"]:
        review.append(f"NONADJACENT_{FEMA[top].upper()}_VS_{FEMA[second].upper()}")
    pset = None
    if qhat is not None:
        from .calibration import aps_sets

        pset = aps_sets(probs[None, :], qhat)[0]
        if len(pset) > ab["conformal_max_set"]:
            review.append(f"PREDICTION_SET_{len(pset)}_CLASSES")
    keys = key_channels if key_channels is not None else cfg["key_channels"]["default"]
    by_id = {c.id: c for c in channels}
    for k in keys:
        c = by_id.get(k)
        if c is None or not c.available:
            review.append(f"KEY_CHANNEL_{k}_UNAVAILABLE")
    reasons = list(extra_reasons or [])
    for c in channels:
        reasons.extend(c.reasons)
        if not c.available and c.unavailable_reason:
            reasons.append(f"{c.id}_UNAVAILABLE_{c.unavailable_reason}")
    reasons.extend(_contribution_codes(channels, top, second))
    # de-duplicate, keep order
    seen: set[str] = set()
    reasons = [r for r in reasons if not (r in seen or seen.add(r))]
    return Verdict(probs, top, float(probs[top]), bool(review), review, reasons, pset, channels)


def expected_class(probs: np.ndarray) -> float:
    return float(np.dot(probs, np.arange(K)))
