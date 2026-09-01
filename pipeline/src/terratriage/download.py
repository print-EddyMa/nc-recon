"""Pick and fetch Maxar Open Data pre/post imagery for a disaster event.

Uses the community STAC catalogue mirror at github.com/opengeos/maxar-open-data
(one TSV per event: catalog_id, quadkey, datetime, proj:epsg, proj:bbox, COG url).
We resolve a lat/lon to the ARD tile(s) that contain it and have captures on both
sides of the event date, then download the `visual` (RGB, 8-bit) COGs.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import urllib.request
from dataclasses import dataclass

CATALOG_URL = "https://raw.githubusercontent.com/opengeos/maxar-open-data/master/datasets/{event}.tsv"


@dataclass
class TileChoice:
    area: str
    quadkey: str
    epsg: int
    grid: str
    pre_date: str
    pre_url: str
    pre_catalog_id: str
    pre_gsd: float
    post_date: str
    post_url: str
    post_catalog_id: str
    post_gsd: float


def fetch_catalog(event: str, cache_dir: str) -> list[dict]:
    os.makedirs(cache_dir, exist_ok=True)
    local = os.path.join(cache_dir, f"{event}.tsv")
    if not os.path.exists(local):
        url = CATALOG_URL.format(event=event)
        print(f"[download] fetching catalog {url}")
        urllib.request.urlretrieve(url, local)
    with open(local) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def row_epsg(row: dict) -> int:
    """EPSG for a catalog row. Older Maxar TSVs have `proj:epsg` (a bare int);
    newer ones only carry `proj:code` ("EPSG:32629") and `utm_zone`."""
    v = row.get("proj:epsg")
    if v:
        return int(v)
    code = row.get("proj:code") or ""
    if code.upper().startswith("EPSG:"):
        return int(code.split(":")[1])
    zone = row.get("utm_zone")
    if zone:
        z = int(zone)
        # hemisphere: infer from the bbox northing (southern UTM uses a false N)
        try:
            _, miny, _, maxy = (float(x) for x in row["proj:bbox"].split(","))
            north = ((miny + maxy) / 2) < 8_000_000  # southern rows are offset +10e6
        except Exception:  # noqa: BLE001
            north = True
        return (32600 if north else 32700) + z
    raise KeyError("row has no proj:epsg / proj:code / utm_zone")


def _contains(row: dict, lat: float, lon: float) -> bool:
    from pyproj import Transformer

    epsg = row_epsg(row)
    x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    minx, miny, maxx, maxy = (float(v) for v in row["proj:bbox"].split(","))
    return minx <= x <= maxx and miny <= y <= maxy


def _row_centroid_lonlat(row: dict) -> tuple[float, float]:
    from pyproj import Transformer

    epsg = row_epsg(row)
    minx, miny, maxx, maxy = (float(v) for v in row["proj:bbox"].split(","))
    lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(
        (minx + maxx) / 2, (miny + maxy) / 2
    )
    return lon, lat


def _has_pre_post(rs: list[dict], event_date: dt.date, slop_days: int = 5) -> bool:
    ds = [dt.datetime.fromisoformat(r["datetime"]).date() for r in rs if r.get("datetime")]
    cut = event_date - dt.timedelta(days=slop_days)
    return any(d < cut for d in ds) and any(d >= cut for d in ds)


def choose_tile(
    rows: list[dict], area: str, lat: float, lon: float, event_date: dt.date
) -> TileChoice:
    """Nearest pre (before the event) + nearest post (on/after the event) for a
    Maxar tile at (lat, lon). Only ever returns a genuine before/after pair
    straddling `event_date`; raises with a helpful message when no covered tile
    near the point has post-event imagery."""
    import math
    from collections import defaultdict

    by_qk: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if _contains(r, lat, lon):
            by_qk[r["quadkey"]].append(r)

    # keep only quadkeys that actually straddle the event
    by_qk = {qk: rs for qk, rs in by_qk.items() if _has_pre_post(rs, event_date)}

    if not by_qk:
        # nearest-quadkey fallback — rank ALL quadkeys that straddle the event by
        # distance to the requested point
        allq: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            allq[r["quadkey"]].append(r)
        ranked = []
        for qk, rs in allq.items():
            if not _has_pre_post(rs, event_date):
                continue
            clon, clat = _row_centroid_lonlat(rs[0])
            d = math.hypot(clon - lon, clat - lat) * 111.0  # deg -> ~km
            ranked.append((d, qk, rs, (clat, clon)))
        ranked.sort(key=lambda t: t[0])
        if not ranked:
            raise LookupError(
                f"{area}: this Maxar event has no before/after imagery pair anywhere"
            )
        nearest_km, _, _, (nclat, nclon) = ranked[0]
        if nearest_km > 35:  # the point is well outside the event's before/after coverage
            raise LookupError(
                f"{area}: no post-event Maxar imagery near ({lat:.3f}, {lon:.3f}). "
                f"Nearest assessable coverage is ~{nearest_km:.0f} km away "
                f"at ({nclat:.3f}, {nclon:.3f})."
            )
        by_qk = {qk: rs for _, qk, rs, _ in ranked[:8]}
        print(
            f"[download] ({lat},{lon}) not inside a covered tile; using the nearest "
            f"assessable quadkey(s), ~{nearest_km:.0f} km away"
        )

    for rs in by_qk.values():
        for r in rs:
            r["_d"] = dt.datetime.fromisoformat(r["datetime"]).date()

    def _pick(split_fn) -> "TileChoice | None":
        """Best pre/post pair across candidate quadkeys, using split_fn(dates)->
        (pre_date, post_date) to decide the boundary per quadkey."""
        chosen: TileChoice | None = None
        chosen_gap = None
        for qk, rs in by_qk.items():
            ds = sorted({r["_d"] for r in rs})
            if len(ds) < 2:
                continue
            split = split_fn(ds)
            if split is None:
                continue
            pre_d, post_d = split
            pre = max((r for r in rs if r["_d"] == pre_d), key=lambda r: float(r.get("gsd") or 9), default=None)
            post = max((r for r in rs if r["_d"] == post_d), key=lambda r: float(r.get("gsd") or 9), default=None)
            if not pre or not post:
                continue
            gap = (post_d - pre_d).days
            if chosen_gap is None or gap < chosen_gap:
                chosen_gap = gap
                chosen = TileChoice(
                    area=area, quadkey=qk, epsg=row_epsg(pre), grid=pre.get("grid:code", ""),
                    pre_date=pre_d.isoformat(), pre_url=pre["visual"],
                    pre_catalog_id=pre["catalog_id"], pre_gsd=float(pre["gsd"]),
                    post_date=post_d.isoformat(), post_url=post["visual"],
                    post_catalog_id=post["catalog_id"], post_gsd=float(post["gsd"]),
                )
        return chosen

    # latest capture before the event + earliest capture on/after it (5-day slop
    # so a capture the same week as landfall still counts as "after")
    cut = event_date - dt.timedelta(days=5)

    def _by_event_date(ds: list[dt.date]):
        pre = [d for d in ds if d < cut]
        post = [d for d in ds if d >= cut]
        return (max(pre), min(post)) if pre and post else None

    best = _pick(_by_event_date)
    if best is None:
        raise LookupError(
            f"{area}: no Maxar tile near ({lat:.3f},{lon:.3f}) has both a pre- and "
            f"post-event capture for this event"
        )
    return best


def download(url: str, dest: str) -> str:
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"[download] have {os.path.basename(dest)}")
        return dest
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    print(f"[download] {url}\n        -> {dest}")
    tmp = dest + ".part"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, dest)
    print(f"[download]    {os.path.getsize(dest) / 1e6:.1f} MB")
    return dest


def fetch_pair(choice: TileChoice, out_dir: str) -> tuple[str, str]:
    d = os.path.join(out_dir, choice.area)
    pre = download(choice.pre_url, os.path.join(d, f"pre_{choice.pre_date}.tif"))
    post = download(choice.post_url, os.path.join(d, f"post_{choice.post_date}.tif"))
    return pre, post
