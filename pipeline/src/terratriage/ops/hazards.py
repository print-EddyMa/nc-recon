"""Hazard profiles (config/hazards.yaml): which evidence applies to which hazard.

The engine is the same for every disaster; a hazard profile says which
evidence channels carry information, where the hazard's footprint comes from,
and the default post-event imagery window.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml

from . import CONFIG_DIR

CHANNELS = ("E1", "E2", "E4", "E5", "E6", "H", "M1")


@lru_cache(maxsize=1)
def profiles() -> dict[str, Any]:
    with open(os.path.join(CONFIG_DIR, "hazards.yaml"), encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    for hid, h in (cfg.get("hazards") or {}).items():
        bad = set(h.get("channels") or []) - set(CHANNELS)
        if bad:
            raise ValueError(f"hazards.yaml: {hid} lists unknown channels {sorted(bad)}")
    for itype, hs in (cfg.get("incident_types") or {}).items():
        unknown = set(hs) - set(cfg.get("hazards") or {})
        if unknown:
            raise ValueError(f"hazards.yaml: incident type {itype} maps to unknown hazards {sorted(unknown)}")
    return cfg


def hazards_for_incident(incident_type: str) -> list[str]:
    """OpenFEMA incidentType -> hazard ids; unknown types fall back to 'other'."""
    table = profiles()["incident_types"]
    if incident_type in table:
        return list(table[incident_type])
    low = {k.lower(): v for k, v in table.items()}
    return list(low.get((incident_type or "").strip().lower(), ["other"]))


def channels_for(hazards: list[str] | tuple[str, ...]) -> set[str]:
    """Union of channels that apply to any of the event's hazards. An event
    with no hazards listed keeps every channel (the pre-profile behaviour)."""
    hs = profiles()["hazards"]
    known = [h for h in hazards if h in hs]
    if not known:
        return set(CHANNELS)
    out: set[str] = set()
    for h in known:
        out.update(hs[h].get("channels") or [])
    return out


def post_days(hazards: list[str] | tuple[str, ...]) -> list[int]:
    """Widest default post window across the event's hazards."""
    hs = profiles()["hazards"]
    spans = [hs[h]["post_days"] for h in hazards if h in hs and hs[h].get("post_days")]
    if not spans:
        return [0, 120]
    return [min(s[0] for s in spans), max(s[1] for s in spans)]


def label(hazard: str) -> str:
    return (profiles()["hazards"].get(hazard) or {}).get("label", hazard.replace("_", " "))
