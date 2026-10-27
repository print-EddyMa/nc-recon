"""Footprint conflation -> one structure table.

Inputs: building polygons (OSM today; Overture / USA Structures / NC OneMap
slot in the same way) and NSI structure points. Output: one row per footprint
with a stable `ncr_id`, every source id, how the NSI point was matched, and the
flags downstream stages need (`residential`, `manufactured_home`, `outbuilding`).

Matching:
  1. NSI point inside the footprint                     match_method=pip,   score 1.0
  2. else nearest NSI point within 15 m (unclaimed)     match_method=near,  score 1 - d/15
  3. else no NSI record                                 match_method=none
One NSI point is claimed by at most one footprint (the one that contains it,
or the nearest), so multi-unit points are not double counted.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import Point, Polygon, shape
from shapely.strtree import STRtree

from ..geodesy import transformer, utm_for

NCR_NS = uuid.UUID("5f1c7f3e-1d7b-4c8e-9a6e-2b2d0c4e7a11")
NEAR_M = 15.0
# Hazus occupancy classes
RESIDENTIAL = {"RES1", "RES2", "RES3A", "RES3B", "RES3C", "RES3D", "RES3E", "RES3F", "RES4", "RES5", "RES6"}
OUTBUILDING_MAX_M2 = 41.8  # 450 ft^2, the USA Structures inclusion floor


@dataclass
class Structure:
    ncr_id: str
    footprint_ll: Polygon
    footprint_source: str
    source_ids: dict[str, Any]
    area_m2: float
    attrs: dict[str, Any] = field(default_factory=dict)  # footprint-source attributes
    nsi: dict[str, Any] | None = None
    match_method: str = "none"
    match_score: float = 0.0
    flags: dict[str, bool] = field(default_factory=dict)

    @property
    def occtype(self) -> str | None:
        return (self.nsi or {}).get("occtype")


def ncr_id(source: str, source_id: str) -> str:
    return str(uuid.uuid5(NCR_NS, f"{source}:{source_id}"))


def conflate(
    footprints_ll: list[Polygon],
    footprint_source: str | list[str],
    footprint_ids: list[str] | None,
    nsi_features: list[dict],
    footprint_attrs: list[dict] | None = None,
) -> list[Structure]:
    if not footprints_ll:
        return []
    c0 = footprints_ll[0].centroid
    fwd = transformer("storage", utm_for(c0.x, c0.y))

    def to_m(g):
        from shapely.ops import transform as st

        return st(fwd.transform, g)

    fps_m = [to_m(p) for p in footprints_ll]
    pts_m = []
    for f in nsi_features:
        x, y = f["geometry"]["coordinates"][:2]
        pts_m.append(Point(fwd.transform(x, y)))
    claimed: dict[int, int] = {}  # nsi idx -> footprint idx

    # pass 1: point in polygon
    if pts_m:
        tree = STRtree(pts_m)
        for i, poly in enumerate(fps_m):
            best = None
            for j in tree.query(poly, predicate="contains"):
                j = int(j)
                if j in claimed:
                    continue
                d = poly.centroid.distance(pts_m[j])
                if best is None or d < best[1]:
                    best = (j, d)
            if best is not None:
                claimed[best[0]] = i
    by_fp = {i: j for j, i in claimed.items()}
    # pass 2: nearest unclaimed within NEAR_M
    if pts_m:
        tree = STRtree(pts_m)
        for i, poly in enumerate(fps_m):
            if i in by_fp:
                continue
            best = None
            for j in tree.query(poly.buffer(NEAR_M)):
                j = int(j)
                if j in claimed:
                    continue
                d = poly.distance(pts_m[j])
                if d <= NEAR_M and (best is None or d < best[1]):
                    best = (j, d)
            if best is not None:
                claimed[best[0]] = i
                by_fp[i] = best[0]

    out: list[Structure] = []
    srcs = footprint_source if isinstance(footprint_source, list) else [footprint_source] * len(footprints_ll)
    for i, (ll, m) in enumerate(zip(footprints_ll, fps_m)):
        sid = (footprint_ids[i] if footprint_ids else None) or f"{m.centroid.x:.1f},{m.centroid.y:.1f}"
        src = srcs[i]
        st = Structure(
            ncr_id=ncr_id(src, sid),
            footprint_ll=ll,
            footprint_source=src,
            source_ids={src: sid},
            area_m2=m.area,
            attrs=(footprint_attrs[i] if footprint_attrs else {}) or {},
        )
        j = by_fp.get(i)
        if j is not None:
            p = nsi_features[j]["properties"]
            st.nsi = p
            st.source_ids["nsi_fd_id"] = p.get("fd_id")
            d = m.distance(pts_m[j])
            st.match_method = "pip" if d == 0 else "near"
            st.match_score = 1.0 if d == 0 else round(max(0.0, 1 - d / NEAR_M), 3)
        # NSI codes carry a stories/basement suffix: RES1-1SNB -> RES1
        occ = (st.occtype or "").split("-")[0]
        usa_occ = (st.attrs.get("OCC_CLS") or "").lower()
        usa_out = str(st.attrs.get("OUTBLDG") or "").strip().lower()
        st.flags = {
            "residential": occ in RESIDENTIAL or (not occ and usa_occ == "residential"),
            "manufactured_home": occ == "RES2" or (st.attrs.get("PRIM_OCC") == "Manufactured Home"),
            "outbuilding": (usa_out not in ("", "none", "null", "0", "no")) if st.attrs
                           else (st.nsi is None and m.area < OUTBUILDING_MAX_M2),
            "unmatched_source": st.nsi is None,
        }
        out.append(st)
    return out


def unmatched_nsi(structures: list[Structure], nsi_features: list[dict]) -> list[dict]:
    """NSI points no footprint claimed: structures missing from the footprint
    source (new builds, rural homes OSM never traced). Reported, never dropped."""
    used = {s.source_ids.get("nsi_fd_id") for s in structures}
    return [f for f in nsi_features if f["properties"].get("fd_id") not in used]


def polys_from_geojson(fc: dict) -> list[Polygon]:
    return [shape(f["geometry"]) for f in fc["features"]]
