"""Content-addressed cache keys.

Bug class guarded here: the v2 footprint cache was keyed by AOI *name*, so a
re-assessment at a different spot with a reused name silently loaded the old
polygons. A key is now SHA-256 over everything that determines the result:
source id, dataset version, the normalized AOI geometry, the time window, the
processing parameters and the code version. Two different geometries can never
share a key, whatever they are called.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from functools import lru_cache
from typing import Any

from . import PIPELINE_ROOT


def _normalize_geom(geom: Any) -> Any:
    """Shapely geometry / bbox tuple / GeoJSON dict -> canonical JSON-able form."""
    if geom is None:
        return None
    if hasattr(geom, "wkb"):
        from shapely import normalize, set_precision

        g = set_precision(normalize(geom), 1e-7)  # ~1 cm in lon/lat
        return g.wkt
    if isinstance(geom, (tuple, list)) and len(geom) == 4 and all(isinstance(v, (int, float)) for v in geom):
        return [round(float(v), 7) for v in geom]
    if isinstance(geom, dict):
        from shapely.geometry import shape

        return _normalize_geom(shape(geom))
    raise TypeError(f"cannot normalize geometry of type {type(geom).__name__}")


@lru_cache(maxsize=1)
def code_version() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", PIPELINE_ROOT, "rev-parse", "--short=12", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def cache_key(
    source_id: str,
    *,
    geometry: Any = None,
    dataset_version: str | None = None,
    time_window: tuple[str | None, str | None] | None = None,
    params: dict[str, Any] | None = None,
    include_code_version: bool = False,
) -> str:
    payload = {
        "source": source_id,
        "version": dataset_version,
        "geom": _normalize_geom(geometry),
        "window": list(time_window) if time_window else None,
        "params": params or {},
    }
    if include_code_version:
        payload["code"] = code_version()
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
