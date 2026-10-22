"""Groma operational mode (Phase J).

Everything under `terratriage.ops` is the "operational GEOINT" path: outputs an
emergency-management analyst can rely on because each one is located
correctly, traceable to a named source and time, checked against ground truth,
and honest about its uncertainty.

Layout follows the GEOINT cycle:

  plan/         event registry (OpenFEMA-sourced), AOIs, pre/post windows
  collect/      data connectors with schema checks + health()
  process/      CRS/datum, resampling, co-registration, masks
  analyze/      evidence channels, fusion, calibration, evaluation, impact
  disseminate/  exports, situation brief

The demo path (`predict_footprints.run`) is untouched. Ops mode is opt-in with
`NCR_OPS_MODE=1` (pipeline) / `VITE_NCR_OPS_MODE=1` (web build).
"""
from __future__ import annotations

import os

DISCLAIMER = (
    "Decision-support tool. Not an official FEMA or state emergency management "
    "damage assessment. Verify on the ground."
)


def ops_mode() -> bool:
    return os.environ.get("NCR_OPS_MODE", "").strip().lower() in ("1", "true", "yes", "on")


PIPELINE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CONFIG_DIR = os.path.join(PIPELINE_ROOT, "config")
DATA_DIR = os.path.join(PIPELINE_ROOT, "data")
OPS_CACHE = os.environ.get("NCR_OPS_CACHE") or os.path.join(DATA_DIR, "cache", "ops")
