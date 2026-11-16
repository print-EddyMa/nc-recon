"""Damage vocabularies and probabilistic crosswalks (config/crosswalks.yaml)."""
from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
import yaml

from .. import CONFIG_DIR

FEMA = ("no_damage", "affected", "minor", "major", "destroyed")
FEMA_LABEL = {
    "no_damage": "No damage", "affected": "Affected", "minor": "Minor",
    "major": "Major", "destroyed": "Destroyed",
}
# FEMA damage-database spelling for exports (DMG_LEVEL)
FEMA_DB_LEVEL = {
    "no_damage": "No Damage", "affected": "Affected", "minor": "Minor",
    "major": "Major", "destroyed": "Destroyed",
}
K = len(FEMA)
XBD = ("no-damage", "minor-damage", "major-damage", "destroyed")
NC_FIELD = ("unaffected", "affected", "minor", "moderate", "major", "destroyed")


@lru_cache(maxsize=1)
def crosswalks() -> dict:
    with open(os.path.join(CONFIG_DIR, "crosswalks.yaml"), encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if tuple(cfg["fema_classes"]) != FEMA:
        raise ValueError("crosswalks.yaml fema_classes out of sync with classes.FEMA")
    for name in ("xbd_to_fema", "nc_field_to_fema"):
        m = np.asarray(cfg[name]["matrix"], dtype=float)
        if m.shape[1] != K or not np.allclose(m.sum(axis=1), 1.0, atol=1e-6):
            raise ValueError(f"{name} must be row-stochastic with {K} columns")
    return cfg


def xbd_to_fema_matrix() -> np.ndarray:
    return np.asarray(crosswalks()["xbd_to_fema"]["matrix"], dtype=float)


def class_prior() -> np.ndarray:
    p = np.asarray(crosswalks()["class_prior"]["p"], dtype=float)
    return p / p.sum()


def xbd_probs_to_fema(p_xbd: np.ndarray) -> np.ndarray:
    """(N,4) xBD probabilities -> (N,5) FEMA likelihoods."""
    return np.asarray(p_xbd) @ xbd_to_fema_matrix()


def fema_index(label: str) -> int:
    lab = label.strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {"none": "no_damage", "no_damage": "no_damage", "unaffected": "no_damage",
               "nodamage": "no_damage"}
    lab = aliases.get(lab, lab)
    return FEMA.index(lab)


def nc_field_to_fema(label: str, bound: str = "mid") -> np.ndarray:
    """One-hot-ish FEMA distribution for an NC field category.

    bound="lower"/"upper" resolves Moderate to Minor/Major for bounds reporting.
    """
    lab = label.strip().lower()
    if lab == "moderate" and bound in ("lower", "upper"):
        tgt = crosswalks()["nc_field_to_fema"]["moderate_bounds"][bound]
        out = np.zeros(K)
        out[FEMA.index(tgt)] = 1.0
        return out
    m = np.asarray(crosswalks()["nc_field_to_fema"]["matrix"], dtype=float)
    return m[NC_FIELD.index(lab)]
