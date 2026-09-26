"""Provenance carried by every layer, feature and export row.

A value without a source and a time is a rumour. Every connector returns a
`Provenance` next to its data, and every derived product appends a step to
`processing_chain`, so an analyst can always answer "where did this come from,
how old is it, and what was done to it".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_utc_z(value: str | datetime | None) -> str | None:
    """Normalise any ISO timestamp (or datetime) to UTC 'YYYY-MM-DDTHH:MM:SSZ'.

    Naive values are rejected: a timestamp without a zone is ambiguous by up to
    five hours in North Carolina, which is the difference between "before the
    crest" and "after it".
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if len(s) == 10:  # a bare date is a date, not an instant - keep it
            datetime.fromisoformat(s)
            return s
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    else:
        dt = value
    if dt.tzinfo is None:
        raise ValueError(f"naive timestamp {value!r}: attach a timezone")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Provenance:
    source: str
    source_url: str
    license: str
    retrieved_utc: str = field(default_factory=utc_now)
    dataset_version: str | None = None
    acquired_utc: str | None = None
    crs: str = "EPSG:4326"
    horizontal_datum: str = "WGS 84"
    epoch: float | None = None
    vertical_datum: str | None = None
    units: str | None = None
    processing_chain: tuple[str, ...] = ()

    def step(self, what: str) -> "Provenance":
        """Return a copy with one more processing step recorded."""
        return replace(self, processing_chain=(*self.processing_chain, what))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["processing_chain"] = list(self.processing_chain)
        return d


REQUIRED_FIELDS = (
    "source", "source_url", "license", "retrieved_utc", "crs", "horizontal_datum",
)


def check(prov: dict[str, Any]) -> list[str]:
    """Problems with a provenance dict ([] == complete)."""
    return [f"provenance missing {k}" for k in REQUIRED_FIELDS if not prov.get(k)]
