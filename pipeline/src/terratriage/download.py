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


def choose_tile(
    rows: list[dict], area: str, lat: float, lon: float, event_date: dt.date
) -> TileChoice:
    """Nearest pre (before event) + nearest post (on/after event) for the tile
    containing (lat, lon). If no tile contains the point, fall back to the
    quadkey nearest the point that still has a usable pre/post pair. Raises only
    if the whole event has no pre/post pair anywhere."""
    from collections import defaultdict

    by_qk: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if _contains(r, lat, lon):
            by_qk[r["quadkey"]].append(r)
    if not by_qk:
        # nearest-quadkey fallback: group ALL rows, keep those with a pre+post,
        # pick the group whose centroid is closest to the requested point
        import math

        allq: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            allq[r["quadkey"]].append(r)
        ranked = []
        for qk, rs in allq.items():
            clon, clat = _row_centroid_lonlat(rs[0])
            d = math.hypot(clon - lon, clat - lat)
            ranked.append((d, qk, rs))
        ranked.sort(key=lambda t: t[0])
        by_qk = {}
        for _, qk, rs in ranked[:8]:
            by_qk[qk] = rs
        if not by_qk:
            raise LookupError(f"{area}: event has no tiles at all")
        print(f"[download] ({lat},{lon}) not inside any tile; using nearest quadkey(s)")

    best: TileChoice | None = None
    best_gap = None
    for qk, rs in by_qk.items():
        for r in rs:
            r["_d"] = dt.datetime.fromisoformat(r["datetime"]).date()
        pre = sorted([r for r in rs if r["_d"] < event_date], key=lambda r: -(r["_d"].toordinal()))
        post = sorted([r for r in rs if r["_d"] >= event_date], key=lambda r: r["_d"].toordinal())
        if not pre or not post:
            continue
        gap = (post[0]["_d"] - pre[0]["_d"]).days
        if best_gap is None or gap < best_gap:
            best_gap = gap
            p, q = pre[0], post[0]
            best = TileChoice(
                area=area, quadkey=qk, epsg=row_epsg(p), grid=p.get("grid:code", ""),
                pre_date=p["_d"].isoformat(), pre_url=p["visual"],
                pre_catalog_id=p["catalog_id"], pre_gsd=float(p["gsd"]),
                post_date=q["_d"].isoformat(), post_url=q["visual"],
                post_catalog_id=q["catalog_id"], post_gsd=float(q["gsd"]),
            )
    if best is None:
        raise LookupError(f"{area}: tile(s) found but none have both a pre- and post-event capture")
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
