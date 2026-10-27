"""Groma's own building damage model (licence-clean by construction).

Trained only on public-domain imagery and public labels:
  pre    USDA NAIP (public domain), latest collection before the incident,
         from Microsoft Planetary Computer's open COGs
  post   NOAA NGS Emergency Response Imagery (US Government work)
  labels CAL FIRE Damage Inspection (DINS) records (State of California,
         public), with FEMA-style levels

so, unlike the xView2/xBD-trained E1 classifier (non-commercial terms), the
weights carry no non-commercial restriction from their data. See
docs/model/MODEL_CARD.md for the training data, the held-out evaluation and
the limits.

  imagery   build co-gridded pre/post mosaics for a training or test box
  dataset   cut a chip pair around each labelled building
  net       the ResNet-18 encoder (fine-tuned Siamese attempts; frozen in v0)
  train     fine-tuning loop and shared metrics (attempts 1-3, overfit)
  linear    v0: frozen encoder features + colour statistics -> logistic
            regression (Eaton held-out Major-or-Destroyed F1 0.95)
  evaluate  score once on a held-out event

Data and weights live in data/model/ (git-ignored; large).
"""
from __future__ import annotations

import os

from .. import DATA_DIR

MODEL_DIR = os.environ.get("NCR_MODEL_DIR") or os.path.join(DATA_DIR, "model")
LEVELS = ("no_damage", "affected", "minor", "major", "destroyed")
