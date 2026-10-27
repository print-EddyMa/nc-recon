"""OpenFEMA Housing Assistance Program Data (Owners and Renters, v2), by ZIP.

What FEMA has actually paid out under Individual Assistance for a declared
disaster, summed per ZIP code: valid registrations, households approved, and
how many approvals fell in the top band. It is the only public, official
count of damaged homes below county level, so it is shown next to an
assessment as context.

Read it for what it is:
  * a ZIP code is far larger than an assessed area
  * it counts households that registered and were found eligible, not
    structures, and not the uninsured-loss-ineligible or the unregistered
  * FEMA re-publishes the dataset as claims are processed; figures grow for
    months after an event
  * for DR-4827 the "FEMA inspected damage" columns are all zero in the
    published data, so only registrations and approvals are used

One ZIP can appear on several rows (a row per county it touches, and
occasional duplicate rows): rows are summed.
"""
from __future__ import annotations

import re
from typing import Any

from ..provenance import Provenance
from .base import Connector, DiskCache, Layer, SchemaError, SourceUnavailable, http_json

BASE = "https://www.fema.gov/api/open/v2"
DATASETS = {"owners": "HousingAssistanceOwners", "renters": "HousingAssistanceRenters"}
MAX_AGE_S = 86400
_ZIP = re.compile(r"\d{5}")

OWNER_FIELDS = {
    "registrations": "validRegistrations",
    "approved": "approvedForFemaAssistance",
    "approved_over_25k": "approvedBetween25001AndMax",
    "max_grants": "totalMaxGrants",
    "repair_replace_usd": "repairReplaceAmount",
    "approved_usd": "totalApprovedIhpAmount",
}
RENTER_FIELDS = {
    "registrations": "validRegistrations",
    "approved": "approvedForFemaAssistance",
    "approved_usd": "totalApprovedIhpAmount",
}


def _sum(rows: list[dict[str, Any]], fields: dict[str, str]) -> dict[str, float]:
    return {k: round(sum(float(r.get(src) or 0) for r in rows), 2) for k, src in fields.items()}


class HousingAssistance(Connector):
    name = "fema_housing_assistance"
    license = "US Government work; FEMA OpenFEMA terms (no endorsement)"
    homepage = "https://www.fema.gov/openfema-data-page/housing-assistance-program-data-owners-v2"
    stale_after_s = 30 * 86400

    def __init__(self) -> None:
        self.cache = DiskCache("fema_ha")

    def _rows(self, kind: str, disaster: int, zip_code: str) -> tuple[list[dict[str, Any]], bool]:
        """(rows, stale). Cached for a day; a stale copy beats nothing."""
        key = f"{kind}_{disaster}_{zip_code}"
        rows = self.cache.get(key, max_age_s=MAX_AGE_S)
        if rows is not None:
            return rows, False
        name = DATASETS[kind]
        try:
            d = http_json(f"{BASE}/{name}", params={
                "$filter": f"disasterNumber eq {int(disaster)} and zipCode eq '{zip_code}'", "$top": 1000})
            rows = d.get(name)
            if not isinstance(rows, list):
                raise SchemaError(f"OpenFEMA {name} response has no {name} list")
            for r in rows:
                if "validRegistrations" not in r or "approvedForFemaAssistance" not in r:
                    raise SchemaError(f"OpenFEMA {name} row is missing the registration / approval columns")
            self.cache.put(key, rows)
            return rows, False
        except (SourceUnavailable, SchemaError):
            old = self.cache.get(key)
            if old is None:
                raise
            return old, True

    def fetch(self, disaster: int, zip_code: str) -> Layer:
        if not _ZIP.fullmatch(zip_code or ""):
            raise ValueError(f"bad ZIP code {zip_code!r}")
        own, stale_o = self._rows("owners", disaster, zip_code)
        ren, stale_r = self._rows("renters", disaster, zip_code)
        cities = sorted({str(r.get("city") or "").title() for r in own + ren if r.get("city")})
        data = {"zip": zip_code, "disaster_number": int(disaster), "cities": cities,
                "owners": _sum(own, OWNER_FIELDS) if own else None,
                "renters": _sum(ren, RENTER_FIELDS) if ren else None}
        prov = Provenance(
            source="OpenFEMA Housing Assistance Program Data (Owners v2, Renters v2)",
            source_url=f"{BASE}/{DATASETS['owners']}", license=self.license,
            dataset_version=f"DR-{int(disaster)}", crs="n/a", horizontal_datum="n/a",
            units="households; US dollars", processing_chain=("rows summed per ZIP code",))
        stale = stale_o or stale_r
        return Layer(data, prov, ["OpenFEMA unreachable: showing the last copy fetched"] if stale else [], stale)

    def probe(self) -> float | None:
        d = http_json(f"{BASE}/{DATASETS['owners']}", params={"$top": 1}, timeout=30)
        if not isinstance(d.get(DATASETS["owners"]), list):
            raise SchemaError("OpenFEMA HousingAssistanceOwners: no row list")
        return None
