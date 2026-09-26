"""Acquisition metadata for an AOI's pre/post pair and the context it implies.

The Maxar Open Data STAC TSV records, per capture: platform, native GSD,
off-nadir angle, sun elevation/azimuth, view azimuth and cloud %. These decide
how far pixel-level change can be trusted (Phase J context rules):

  * off-nadir or sun-elevation difference > 15 deg  -> buildings lean / shadows
    move differently between dates -> pixel change (E2) down-weighted
  * different season (leaf-off vs leaf-on)           -> vegetation change is not
    damage evidence
  * cloud % > 0 on the post capture                  -> per-building cloud check
"""
from __future__ import annotations

import csv
import glob
import math
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

import rasterio

from .. import DATA_DIR
from ..provenance import to_utc_z

CACHE = os.path.join(DATA_DIR, "cache")


@dataclass(frozen=True)
class ImageInfo:
    role: str
    date: str
    acquired_utc: str | None
    platform: str | None
    catalog_id: str | None
    gsd_m: float | None
    off_nadir_deg: float | None
    sun_elevation_deg: float | None
    sun_azimuth_deg: float | None
    view_azimuth_deg: float | None
    clouds_pct: float | None
    url: str | None
    path: str
    date_min: str | None = None   # acquisition may be known only as a range
    date_max: str | None = None
    date_source: str | None = None

    @property
    def dmin(self) -> date:
        return date.fromisoformat(self.date_min or self.date)

    @property
    def dmax(self) -> date:
        return date.fromisoformat(self.date_max or self.date)

    @property
    def exact(self) -> bool:
        return self.dmin == self.dmax

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _season(d: date, lat: float = 35.6) -> str:
    """Coarse leaf state for the southern Appalachians / Piedmont."""
    m = d.month
    if m in (12, 1, 2, 3):
        return "leaf-off"
    if m in (5, 6, 7, 8, 9):
        return "leaf-on"
    return "transition"


def _row_contains(row: dict, x: float, y: float) -> bool:
    try:
        minx, miny, maxx, maxy = (float(v) for v in row["proj:bbox"].split(","))
    except (KeyError, ValueError):
        return False
    return minx <= x <= maxx and miny <= y <= maxy


def image_info(path: str, role: str, event: str) -> ImageInfo:
    """Look up the capture behind a pre_/post_ GeoTIFF in the event's STAC TSV."""
    d = os.path.basename(path).split("_", 1)[1].rsplit(".", 1)[0]
    with rasterio.open(path) as ds:
        cx = (ds.bounds.left + ds.bounds.right) / 2
        cy = (ds.bounds.bottom + ds.bounds.top) / 2
        epsg = ds.crs.to_epsg()
    row = None
    tsv = os.path.join(CACHE, f"{event}.tsv")
    if os.path.exists(tsv):
        with open(tsv, encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                if (r.get("datetime", "")[:10] == d and str(r.get("proj:epsg") or "") in ("", str(epsg))
                        and _row_contains(r, cx, cy)):
                    row = r
                    break
    r = row or {}
    acq = r.get("datetime")
    return ImageInfo(
        role=role, date=d,
        acquired_utc=to_utc_z(acq.replace(" ", "T")) if acq else None,
        platform=r.get("platform"), catalog_id=r.get("catalog_id"),
        gsd_m=_f(r.get("gsd")), off_nadir_deg=_f(r.get("view:off_nadir")),
        sun_elevation_deg=_f(r.get("view:sun_elevation")),
        sun_azimuth_deg=_f(r.get("view:sun_azimuth")),
        view_azimuth_deg=_f(r.get("view:azimuth")),
        clouds_pct=_f(r.get("tile:clouds_percent")),
        url=r.get("visual"), path=path,
    )


def _from_sidecar(meta: dict, role: str) -> ImageInfo:
    m = meta[role]
    prov = m.get("provenance") or {}
    lo = m.get("date_min") or m.get("date")
    hi = m.get("date_max") or m.get("date")
    return ImageInfo(
        role=role, date=lo if lo == hi else f"{lo}..{hi}", acquired_utc=None,
        platform=f"aerial:{m['source']}", catalog_id=None, gsd_m=None,
        off_nadir_deg=None, sun_elevation_deg=None, sun_azimuth_deg=None,
        view_azimuth_deg=None, clouds_pct=None, url=prov.get("source_url"), path=m["path"],
        date_min=lo, date_max=hi, date_source=m.get("date_source"),
    )


def sidecar(raw_dir: str, area: str) -> dict | None:
    import json

    p = os.path.join(raw_dir, area, "imagery.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def pair_for_area(raw_dir: str, area: str, event: str) -> tuple[ImageInfo, ImageInfo]:
    meta = sidecar(raw_dir, area)
    if meta:  # ops-fetch pair (NC orthos / ERI)
        return _from_sidecar(meta, "pre"), _from_sidecar(meta, "post")
    pre = sorted(glob.glob(os.path.join(raw_dir, area, "pre_*.tif")))
    post = sorted(glob.glob(os.path.join(raw_dir, area, "post_*.tif")))
    if not pre or not post:
        raise FileNotFoundError(f"no pre/post imagery for {area}")
    return image_info(pre[0], "pre", event), image_info(post[0], "post", event)


def pair_context(pre: ImageInfo, post: ImageInfo, geometry_limit_deg: float = 15.0) -> dict[str, Any]:
    """Pair-level context + reason codes consumed by the context rules."""
    reasons: list[str] = []
    d_nadir = (abs(pre.off_nadir_deg - post.off_nadir_deg)
               if pre.off_nadir_deg is not None and post.off_nadir_deg is not None else None)
    d_sun = (abs(pre.sun_elevation_deg - post.sun_elevation_deg)
             if pre.sun_elevation_deg is not None and post.sun_elevation_deg is not None else None)
    aerial = (pre.platform or "").startswith("aerial:") and (post.platform or "").startswith("aerial:")
    if (d_nadir is None or d_sun is None) and aerial:
        # orthorectified aerial mosaics: near-nadir per frame but not true orthos,
        # so tall objects lean differently along seamlines; angles not published
        reasons.append("AERIAL_ORTHO_GEOMETRY_UNRECORDED")
    elif d_nadir is None or d_sun is None:
        reasons.append("VIEW_GEOMETRY_UNKNOWN")
    if d_nadir is not None and d_nadir > geometry_limit_deg:
        reasons.append(f"OFF_NADIR_DIFF_{d_nadir:.0f}DEG")
    if d_sun is not None and d_sun > geometry_limit_deg:
        reasons.append(f"SUN_ELEV_DIFF_{d_sun:.0f}DEG")
    s_pre = _season(pre.dmax)
    s_post = _season(post.dmin)
    if s_pre != s_post:
        reasons.append(f"SEASON_{s_pre.upper().replace('-', '_')}_VS_{s_post.upper().replace('-', '_')}")
    gap_days = (post.dmin - pre.dmax).days   # lower bound when dates are ranges
    if gap_days > 365:
        reasons.append(f"PRE_IMAGE_{'GE_' if not (pre.exact and post.exact) else ''}{gap_days // 365}Y_OLD")
    if not pre.exact or not post.exact:
        reasons.append("ACQUISITION_DATE_IS_A_RANGE")
    # geometry penalty for pixel-level change: 1 when matched, -> 0.3 when both
    # angles differ by >= 2x the limit
    pen = 1.0
    for dv in (d_nadir, d_sun):
        if dv is not None and dv > geometry_limit_deg:
            pen *= max(0.3, 1 - (dv - geometry_limit_deg) / (2 * geometry_limit_deg))
    if s_pre != s_post:
        pen *= 0.8
    # relief displacement a building of height h shows at off-nadir angle a: h*tan(a)
    lean_per_10m = {k: (round(10 * math.tan(math.radians(v)), 2) if v is not None else None)
                    for k, v in (("pre", pre.off_nadir_deg), ("post", post.off_nadir_deg))}
    return {
        "off_nadir_diff_deg": d_nadir, "sun_elev_diff_deg": d_sun,
        "season_pre": s_pre, "season_post": s_post, "pair_gap_days": gap_days,
        "roof_lean_m_per_10m_height": lean_per_10m,
        "e2_geometry_weight": round(pen, 3),
        "post_clouds_pct": post.clouds_pct,
        "reasons": reasons,
    }


def days_after(post: ImageInfo, t: datetime | date) -> float | None:
    if not post.acquired_utc:
        return None
    acq = datetime.fromisoformat(post.acquired_utc.replace("Z", "+00:00"))
    if isinstance(t, datetime):
        return (acq - t).total_seconds() / 86400
    return (acq.date() - t).days
