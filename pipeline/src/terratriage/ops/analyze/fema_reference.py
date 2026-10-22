"""FEMA assistance beside an assessment: `run.py ops-reference --area X`.

For each ZIP code the assessed structures fall in, two things side by side:

  this assessment   structures in the area with that ZIP, homes assessed, and
                    the expected number at Major or Destroyed (sum of
                    P(major) + P(destroyed))
  FEMA              households approved under Individual Assistance in the
                    whole ZIP code (collect/fema_ha.py)

This is context, not validation. The two numbers differ in kind (structures
seen from above in part of a ZIP; households that registered across all of
it), so no ratio or "agreement" figure is computed. What the pairing can show
is gross disagreement: an area called heavily damaged in a ZIP where FEMA
approved almost nobody, or the reverse, deserves a second look.

ZIP codes come from the responder address sidecar (FEMA USA Structures
addresses), so the product is responder-only. Structures with no address
(OpenStreetMap-only outlines, inventory points) are reported as unplaced.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from .. import DATA_DIR, DISCLAIMER
from ..collect.base import SchemaError, SourceUnavailable
from ..collect.fema_ha import HousingAssistance
from ..provenance import utc_now

OPS_OUT = os.path.join(DATA_DIR, "output", "ops")
_ZIP_AT_END = re.compile(r"(\d{5})(?:-\d{4})?\s*$")
CAVEAT = ("FEMA figures cover the whole ZIP code, which is larger than this area, and count households "
          "that registered and were approved, not structures. Context for the estimate, not a check of it.")


def zip_of(address: str | None) -> str | None:
    m = _ZIP_AT_END.search(address or "")
    return m.group(1) if m else None


def run(area: str, source: HousingAssistance | None = None) -> dict[str, Any]:
    with open(os.path.join(OPS_OUT, f"{area}.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    rsp_path = os.path.join(OPS_OUT, f"{area}.responder.json")
    addresses: dict[str, Any] = {}
    if os.path.exists(rsp_path):
        with open(rsp_path, encoding="utf-8") as fh:
            addresses = json.load(fh).get("structures") or {}
    by_zip: dict[str, dict[str, Any]] = {}
    unplaced = 0
    for f in fc["features"]:
        p = f["properties"]
        z = zip_of((addresses.get(p["ncr_id"]) or {}).get("address"))
        if z is None:
            unplaced += 1
            continue
        row = by_zip.setdefault(z, {"zip": z, "structures": 0, "homes_assessed": 0, "expected_major_plus": 0.0})
        row["structures"] += 1
        probs = p.get("damage_probs")
        if probs and (p.get("flags") or {}).get("residential"):
            row["homes_assessed"] += 1
            row["expected_major_plus"] += float(probs["major"]) + float(probs["destroyed"])
    event = fc["properties"]["event"]
    numbers = [int(m.group(1)) for m in (re.search(r"(\d{4})", d) for d in event.get("declarations", [])) if m]
    out: dict[str, Any] = {
        "area": area, "run_id": fc["properties"]["run_id"], "generated_utc": utc_now(),
        "declarations": event.get("declarations", []), "unplaced_structures": unplaced,
        "caveat": CAVEAT, "disclaimer": DISCLAIMER, "warnings": [], "zips": [],
        "source": {"name": "OpenFEMA Housing Assistance Program Data (Owners v2, Renters v2)",
                   "url": HousingAssistance.homepage, "license": HousingAssistance.license},
    }
    if not numbers:
        out["status"] = "NO_DECLARATION"
        out["warnings"].append("No federal declaration for this event yet: FEMA has published no assistance data")
    src = source or HousingAssistance()
    for z, row in sorted(by_zip.items(), key=lambda kv: -kv[1]["structures"]):
        row["expected_major_plus"] = round(row["expected_major_plus"], 1)
        row["fema"] = None
        for n in numbers:
            try:
                layer = src.fetch(n, z)
            except SourceUnavailable as ex:
                out["warnings"].append(f"OpenFEMA unreachable for ZIP {z}: {str(ex)[:120]}")
                continue
            except SchemaError as ex:
                # FEMA changed the dataset: say so rather than show zeros
                out["warnings"].append(f"OpenFEMA data for ZIP {z} is not in the expected form: {str(ex)[:120]}")
                continue
            out["warnings"].extend(w for w in layer.warnings if w not in out["warnings"])
            row["fema"] = _merge(row["fema"], layer.data)
        out["zips"].append(row)
    out.setdefault("status", "OK" if any(r["fema"] for r in out["zips"]) else "NO_FEMA_DATA")
    return out


def _merge(acc: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    """Sum a second declaration's figures into the first (multi-declaration events)."""
    if acc is None:
        return {"cities": new["cities"], "owners": new["owners"], "renters": new["renters"]}
    for k in ("owners", "renters"):
        if new[k] is None:
            continue
        acc[k] = new[k] if acc[k] is None else {f: round(acc[k][f] + new[k][f], 2) for f in new[k]}
    acc["cities"] = sorted(set(acc["cities"]) | set(new["cities"]))
    return acc
