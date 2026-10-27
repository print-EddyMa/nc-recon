"""Ground change around each building from the 2025 lidar (collect/nc_lidar.py):
`python -m terratriage.ops.analyze.ground_change --area X`.

For each footprint, the bare-earth change dz (2025 QL1 minus 3DEP) is read on
a ring of ground 2 to 10 m outside the walls (bare earth has the building
removed, so the footprint itself says nothing). The area's own typical change
(the median over all rings, which absorbs any datum or vintage offset) is
subtracted, then:

  deposit   ring p90 more than 1 m above typical: debris or sediment piled
            against the building
  scour     ring p10 more than 1 m below typical: ground eroded or slid away

Anything else is no evidence, never evidence of no damage: flood water that
filled a house and drained leaves the ground where it was.

What it showed on Swannanoa (TUNE, 2026-10-22): 893 buildings, ring medians
tight (p50 +0.05 m, p99 +0.20 m). 15 buildings flagged; 12 of them have a
search-team call, and 9 of those 12 were Major or Destroyed, while the imagery
channels had called most of the 15 No damage. Rare, specific, and
complementary to the imagery. The likelihood below is provisional (hand-set
from that look and the physics; not fitted), as is every channel until
analyst labels exist.

Caveats carried into every output: the 3DEP baseline is 2017, so building,
grading and paving between 2017 and 2025 also show as change; the 2025 flight
dates are not published; bare earth says nothing about the roof.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import numpy as np

from .. import DISCLAIMER, OPS_OUT
from ..provenance import utc_now

RING_M = (2.0, 10.0)
THRESH_M = 1.0
MIN_PIXELS = 20
# P(flag | FEMA level), provisional; flat (no evidence) when not flagged
LIKELIHOOD = {
    "deposit": [0.08, 0.10, 0.17, 0.30, 0.35],
    "scour": [0.06, 0.08, 0.16, 0.30, 0.40],
}
CAVEATS = [
    "The baseline is USGS 3DEP (western NC: 2017). Construction, grading and paving since then also show as change.",
    "Bare-earth lidar removes buildings: this measures the ground around a structure, never its roof or walls.",
    "No flag is not evidence of no damage: flood water that filled a house and drained leaves the ground in place.",
    "The 2025 survey's flight dates are not published in the service.",
    "Provisional rule (1 m beyond the area's typical change), not fitted on labels.",
]


def _utm(features: list[dict]):
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as stf

    tr = Transformer.from_crs(4326, 32617, always_xy=True).transform
    polys = {}
    for f in features:
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        if g.get("type") in ("Polygon", "MultiPolygon") and p.get("ncr_id"):
            polys[p["ncr_id"]] = stf(tr, shape(g))
    return polys


def ring_stats(dz: np.ndarray, transform, polys: dict[str, Any]) -> dict[str, dict[str, float]]:
    """Per-building dz statistics on the 2-10 m ring (metres)."""
    from affine import Affine
    from rasterio.features import geometry_mask

    H, W = dz.shape
    out: dict[str, dict[str, float]] = {}
    for nid, p in polys.items():
        ring = p.buffer(RING_M[1]).difference(p.buffer(RING_M[0]))
        x0, y0, x1, y1 = ring.bounds
        c0 = max(int((x0 - transform.c) / transform.a), 0)
        c1 = min(int((x1 - transform.c) / transform.a) + 1, W)
        r0 = max(int((y1 - transform.f) / transform.e), 0)
        r1 = min(int((y0 - transform.f) / transform.e) + 1, H)
        if c1 <= c0 or r1 <= r0:
            continue
        sub = dz[r0:r1, c0:c1]
        m = geometry_mask([ring], out_shape=sub.shape, transform=transform @ Affine.translation(c0, r0), invert=True)
        v = sub[m]
        v = v[np.isfinite(v)]
        if v.size < MIN_PIXELS:
            continue
        out[nid] = {"n": int(v.size), "median_m": round(float(np.median(v)), 3),
                    "p10_m": round(float(np.percentile(v, 10)), 3), "p90_m": round(float(np.percentile(v, 90)), 3)}
    return out


def typical(stats: dict[str, dict[str, float]]) -> float | None:
    meds = [s["median_m"] for s in stats.values()]
    return float(np.median(meds)) if len(meds) >= 30 else None


def flag(s: dict[str, float], offset: float) -> str | None:
    if s["p90_m"] - offset > THRESH_M:
        return "deposit"
    if s["p10_m"] - offset < -THRESH_M:
        return "scour"
    return None


def measure(features: list[dict], county: str) -> dict[str, Any]:
    """Fetch the surfaces for these structures and measure every ring."""
    from ..collect import nc_lidar

    polys = _utm(features)
    if not polys:
        raise ValueError("no footprints to measure")
    xs = [p.bounds for p in polys.values()]
    pad = RING_M[1] + 50
    bbox = (min(b[0] for b in xs) - pad, min(b[1] for b in xs) - pad,
            max(b[2] for b in xs) + pad, max(b[3] for b in xs) + pad)
    s = nc_lidar.surfaces(county, bbox)
    dz, tr = nc_lidar.dz(s)
    stats = ring_stats(dz, tr, polys)
    off = typical(stats)
    flags = {} if off is None else {k: f for k, v in stats.items() if (f := flag(v, off))}
    return {"stats": stats, "typical_m": None if off is None else round(off, 3), "flags": flags,
            "grid": {k: s[k] for k in ("bbox_utm", "width", "height", "res_m", "crs")},
            "provenance": s["provenance"]}


def compare_area(area: str, *, allow_test: bool = False, write: bool = True) -> dict[str, Any]:
    with open(os.path.join(OPS_OUT, f"{area}.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    run = fc.get("properties") or {}
    aoi = run.get("aoi") or {}
    if aoi.get("role") == "TEST" and not allow_test:
        raise SystemExit(f"{area} is a TEST (hold-out) area; refusing to measure it unless --allow-test")
    county = aoi.get("county")
    if not county:
        from ..counties import county_of

        county = county_of(f["properties"].get("cbfips_2010") for f in fc["features"])
    t0 = time.time()
    m = measure(fc["features"], county)
    props = {f["properties"]["ncr_id"]: f["properties"] for f in fc["features"] if f.get("properties")}
    flagged = [{"ncr_id": k, "kind": v, **m["stats"][k], "ncr": (props.get(k) or {}).get("damage_level")}
               for k, v in sorted(m["flags"].items())]
    out = {
        "area": area, "role": aoi.get("role"), "county": county, "generated_utc": utc_now(),
        "run_id": run.get("run_id"), "disclaimer": DISCLAIMER,
        "rule": f"ring {RING_M[0]:g}-{RING_M[1]:g} m outside the footprint; deposit if p90 is more than "
                f"{THRESH_M:g} m above the area's typical change, scour if p10 is more than {THRESH_M:g} m below",
        "typical_change_m": m["typical_m"], "measured": len(m["stats"]), "structures": len(props),
        "flag_counts": {k: sum(1 for x in flagged if x["kind"] == k) for k in LIKELIHOOD},
        "flagged": flagged,
        "flagged_by_ncr_level": _count(x["ncr"] for x in flagged),
        "likelihood_when_flagged": LIKELIHOOD,
        "grid": m["grid"], "provenance": m["provenance"], "caveats": CAVEATS,
        "runtime_sec": round(time.time() - t0, 1),
    }
    if write:
        p = os.path.join(OPS_OUT, f"{area}.ground_change.json")
        with open(p + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        os.replace(p + ".tmp", p)
    return out


def _count(xs) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        k = str(x)
        out[k] = out.get(k, 0) + 1
    return out


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Ground change around each building from the 2025 lidar")
    ap.add_argument("--area", required=True)
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    r = compare_area(a.area, allow_test=a.allow_test, write=not a.no_write)
    print(f"{r['area']} ({r['role']}, {r['county']} County): measured {r['measured']} of {r['structures']}, "
          f"typical change {r['typical_change_m']} m; flagged {r['flag_counts']}; "
          f"Groma level of flagged: {r['flagged_by_ncr_level']}")
    for c in r["caveats"]:
        print("  -", c)


if __name__ == "__main__":
    main()
