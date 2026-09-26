"""Turn raw measurements into evidence channels (likelihood + weight + reasons)."""
from __future__ import annotations

from typing import Any

import numpy as np

from .classes import FEMA, XBD, class_prior, xbd_to_fema_matrix
from .evidence import BuildingEvidence, change_score
from .fusion import Channel, rules


def _context_weight(ev: BuildingEvidence) -> float:
    cfg = rules()["canopy"]
    if ev.m.get("canopy_frac", 0.0) > cfg["downweight_frac"]:
        return float(cfg["downweight"])
    return 1.0


def e1(ev: BuildingEvidence, logits: np.ndarray | None, T: float | None) -> Channel:
    """Optical CNN. Calibrated mode: softmax(logits/T) @ crosswalk. Uncalibrated
    (no fitted T): label-only - the crosswalk row of the CNN's argmax."""
    cfg = rules()["channels"]["E1"]
    if "E1" in ev.unavailable:
        return Channel("E1", False, unavailable_reason=ev.unavailable["E1"])
    if logits is None:
        return Channel("E1", False, unavailable_reason="MODEL_NOT_RUN")
    W = xbd_to_fema_matrix()
    lab = int(np.argmax(logits))
    # crosswalk rows are P(fema | xbd label) - posteriors that already contain a
    # class prior. Pooling multiplies by the prior again, so divide it out:
    # P(xbd label | fema) is proportional to P(fema | xbd) / P(fema).
    prior = class_prior()
    if T is not None:
        from .calibration import softmax

        p_xbd = softmax(logits[None, :], T)[0]
        L, status = (p_xbd @ W) / prior, "calibrated"
    else:
        L, status = W[lab] / prior, "label_only"
    L = L / L.sum()
    w = cfg["weight"] * _context_weight(ev)
    if (ev.m.get("alignment") or {}).get("post", {}).get("weak"):
        # the CNN may be looking at the neighbour's lawn
        w *= rules()["channels"]["E1"].get("weak_alignment_weight", 0.5)
    return Channel("E1", True, L, w, status, [f"E1_CNN_{XBD[lab].upper().replace('-', '_')}"],
                   detail={"xbd_label": XBD[lab], "logits": [round(float(v), 3) for v in logits]})


def e2_baseline(evs: list[BuildingEvidence]) -> tuple[float, float] | None:
    """Robust (median, scaled MAD) of the change score across the AOI."""
    xs = np.array([v for v in (change_score(e.m) for e in evs if "E2" not in e.unavailable) if v is not None])
    if len(xs) < 30:
        return None
    med = float(np.median(xs))
    mad = float(np.median(np.abs(xs - med))) * 1.4826
    return med, max(mad, 1e-3)


def e2(ev: BuildingEvidence, pair_weight: float, baseline: tuple[float, float] | None = None) -> Channel:
    cfg = rules()["channels"]["E2"]
    if "E2" in ev.unavailable:
        return Channel("E2", False, unavailable_reason=ev.unavailable["E2"])
    s = change_score(ev.m)
    if s is None:
        return Channel("E2", False, unavailable_reason="FOOTPRINT_TOO_SMALL")
    if baseline is None:
        return Channel("E2", False, unavailable_reason="TOO_FEW_STRUCTURES_FOR_BASELINE")
    z = (s - baseline[0]) / baseline[1]
    b = int(np.searchsorted(cfg["bins"], z, side="right"))
    L = np.asarray(cfg["likelihood"][b], float)
    w = cfg["weight"] * pair_weight * _context_weight(ev)
    ncc = ev.m.get("edge_ncc", 1.0)
    return Channel("E2", True, L, w, "provisional", [f"E2_CHANGE_Z{z:+.1f}"],
                   detail={"score": round(s, 3), "z": round(z, 2), "edge_ncc": ncc})


def e4(ev: BuildingEvidence) -> Channel:
    cfg = rules()["channels"]["E4"]
    if "E4" in ev.unavailable:
        return Channel("E4", False, unavailable_reason=ev.unavailable["E4"])
    t = ev.m.get("tarp_frac_new")
    if t is None:
        return Channel("E4", False, unavailable_reason="NOT_MEASURED")
    if t >= cfg["min_new_tarp_frac"]:
        return Channel("E4", True, np.asarray(cfg["likelihood_tarp"], float), cfg["weight"],
                       "provisional", [f"E4_TARP_{t * 100:.0f}PCT"], detail={"tarp_frac_new": t})
    # no tarp is not evidence of no damage: flat likelihood, recorded for audit
    return Channel("E4", True, np.ones(len(FEMA)) / len(FEMA), 0.0, "provisional", [],
                   detail={"tarp_frac_new": t})


def e5_unavailable(reason: str) -> Channel:
    return Channel("E5", False, unavailable_reason=reason)


def e5(probs: np.ndarray, depth: dict[str, Any], source_ref: str) -> Channel:
    cfg = rules()["channels"]["E5"]
    med = depth["d_ff_m_median"]
    return Channel("E5", True, probs, cfg["weight"], "rule",
                   [f"FIRST_FLOOR_DEPTH_{med:.1f}M_P10_{depth['d_ff_m_p10']:.1f}_P90_{depth['d_ff_m_p90']:.1f}"],
                   detail={**{k: round(v, 3) for k, v in depth.items()}, "wse_source": source_ref})
