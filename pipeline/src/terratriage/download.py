"""Pick and fetch Maxar Open Data pre/post imagery for a disaster event.

Uses the community STAC catalogue mirror at github.com/opengeos/maxar-open-data
(one TSV per event: catalog_id, quadkey, datetime, proj:epsg, proj:bbox, COG url).
We resolve a lat/lon to the ARD tile(s) that contain it and have captures on both
sides of the event date, then download the `visual` (RGB, 8-bit) COGs.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache

CATALOG_URL = "https://raw.githubusercontent.com/opengeos/maxar-open-data/master/datasets/{event}.tsv"

# --------------------------------------------------------------------------- #
# HTTP: every network read here goes through _http_stream so a stalled S3
# connection fails fast (with retry + resume) instead of hanging the whole
# assessment. urllib.request.urlretrieve, which this replaces, honours no
# timeout at all — a trickling socket blocks until the caller is killed.
# --------------------------------------------------------------------------- #
HTTP_TIMEOUT = 30          # per-read socket timeout, seconds
HTTP_RETRIES = 4
HTTP_BACKOFF = 2.0         # sleep = HTTP_BACKOFF * attempt between tries
MIN_THROUGHPUT_BPS = 64 * 1024   # abort a stream slower than this once warmed up

# GDAL/vsicurl tuning for windowed HTTP range reads of the COGs.
_GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_TIMEOUT": "30",
    "GDAL_HTTP_CONNECTTIMEOUT": "10",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "VSI_CACHE": "TRUE",
    "CPL_VSIL_CURL_CHUNK_SIZE": "1048576",
    "GDAL_INGESTED_BYTES_AT_OPEN": "32768",
}

# half-width (metres) of the AOI window cut from each Maxar ARD tile. A full ARD
# tile is ~5 km / 17408 px a side; the damage map only ever shows a neighbourhood,
# so a ~2.4 km box keeps the raster ~14x smaller and every downstream step faster.
AOI_HALF_M = 1200


@lru_cache(maxsize=64)
def _tx(src_epsg, dst_epsg):
    """Cached pyproj transformer — choose_tile calls this once per catalog row."""
    from pyproj import Transformer

    return Transformer.from_crs(src_epsg, dst_epsg, always_xy=True)


def _have(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0


def _http_stream(url: str, dest: str, *, timeout: int = HTTP_TIMEOUT, retries: int = HTTP_RETRIES) -> str:
    """Stream `url` to `dest` with a socket timeout, retry + backoff, and
    resume-within-call from a `.part` file. Raises RuntimeError on final failure.
    Resume never spans separate pipeline runs — callers discard a stale `.part`
    before the first attempt."""
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    part = dest + ".part"
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        req = urllib.request.Request(url)
        mode = "ab" if have else "wb"
        if have:
            req.add_header("Range", f"bytes={have}-")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                if have and getattr(r, "status", 200) != 206:
                    have, mode = 0, "wb"          # server ignored Range — restart
                started = time.monotonic()
                with open(part, mode) as fh:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        fh.write(chunk)
                        have += len(chunk)
                        elapsed = time.monotonic() - started
                        if elapsed > 20 and have / elapsed < MIN_THROUGHPUT_BPS:
                            raise TimeoutError(
                                f"stalled: {have / 1e6:.1f} MB in {elapsed:.0f}s"
                            )
            if not _have(part):
                raise RuntimeError("empty response body")
            os.replace(part, dest)
            return dest
        except Exception as ex:  # noqa: BLE001
            last_err = ex
            print(f"[download] attempt {attempt}/{retries} failed: {ex}")
            if attempt < retries:
                time.sleep(HTTP_BACKOFF * attempt)
    if os.path.exists(part):
        try:
            os.remove(part)          # leave nothing half-written for the next run
        except OSError:
            pass
    raise RuntimeError(f"could not download {url}: {last_err}")


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
    if not _have(local):
        url = CATALOG_URL.format(event=event)
        print(f"[download] fetching catalog {url}")
        _http_stream(url, local, timeout=20, retries=3)
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
    epsg = row_epsg(row)
    x, y = _tx(4326, epsg).transform(lon, lat)
    minx, miny, maxx, maxy = (float(v) for v in row["proj:bbox"].split(","))
    return minx <= x <= maxx and miny <= y <= maxy


def _row_centroid_lonlat(row: dict) -> tuple[float, float]:
    epsg = row_epsg(row)
    minx, miny, maxx, maxy = (float(v) for v in row["proj:bbox"].split(","))
    lon, lat = _tx(epsg, 4326).transform((minx + maxx) / 2, (miny + maxy) / 2)
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
    if _have(dest):
        print(f"[download] have {os.path.basename(dest)}")
        return dest
    part = dest + ".part"
    if os.path.exists(part):
        try:
            os.remove(part)          # stale partial from an earlier, killed run
        except OSError:
            pass
    print(f"[download] {url}\n        -> {dest}")
    _http_stream(url, dest)
    print(f"[download]    {os.path.getsize(dest) / 1e6:.1f} MB")
    return dest


def _window_pair(
    pre_url: str, post_url: str, lon: float, lat: float,
    dest_pre: str, dest_post: str, half_m: float = AOI_HALF_M,
) -> tuple[str, str]:
    """Cut a (2*half_m) box around (lon,lat) straight out of each COG with HTTP
    range reads and write two small, grid-aligned GeoTIFFs. Maxar ARD tiles for
    one quadkey share an exact pixel grid, so a single snapped world box yields
    identical windows for pre and post; we assert that before writing."""
    import rasterio
    from rasterio.windows import bounds as _win_bounds, from_bounds

    with rasterio.Env(**_GDAL_ENV):
        with rasterio.open("/vsicurl/" + pre_url) as a, rasterio.open("/vsicurl/" + post_url) as b:
            if a.crs != b.crs:
                raise ValueError(f"CRS mismatch: {a.crs} vs {b.crs}")
            cx, cy = _tx(4326, a.crs.to_epsg()).transform(lon, lat)
            # clamp the AOI box to the overlap of the two rasters
            left = max(cx - half_m, a.bounds.left, b.bounds.left)
            right = min(cx + half_m, a.bounds.right, b.bounds.right)
            bot = max(cy - half_m, a.bounds.bottom, b.bounds.bottom)
            top = min(cy + half_m, a.bounds.top, b.bounds.top)
            if right - left < 200 or top - bot < 200:
                raise ValueError("AOI window falls outside the imagery pair")
            # snap to pre's pixel grid, then reuse that exact world box for both
            wa = from_bounds(left, bot, right, top, a.transform).round_offsets().round_lengths()
            wbox = _win_bounds(wa, a.transform)
            wa = from_bounds(*wbox, a.transform).round_offsets().round_lengths()
            wb = from_bounds(*wbox, b.transform).round_offsets().round_lengths()
            # pre + post are independent network reads — overlap them
            with ThreadPoolExecutor(max_workers=2) as pool:
                fa = pool.submit(a.read, indexes=[1, 2, 3], window=wa, boundless=True, fill_value=0)
                fb = pool.submit(b.read, indexes=[1, 2, 3], window=wb, boundless=True, fill_value=0)
                pa, pb = fa.result(), fb.result()
            ta, tb = a.window_transform(wa), b.window_transform(wb)
            if pa.shape != pb.shape or ta != tb:
                raise RuntimeError(f"pre/post windows did not align ({pa.shape} vs {pb.shape})")
            if pa.max() == 0 or pb.max() == 0:
                raise RuntimeError("AOI window is all nodata in one of the captures")
            # JPEG/YCbCr to match the Maxar source — a DEFLATE re-encode of RGB
            # aerial imagery is both far larger on disk and CPU-bound to write
            prof = {
                "driver": "GTiff", "height": pa.shape[1], "width": pa.shape[2],
                "count": 3, "dtype": "uint8", "crs": a.crs, "transform": ta,
                "tiled": True, "blockxsize": 512, "blockysize": 512,
                "compress": "JPEG", "photometric": "YCBCR", "jpeg_quality": 92,
            }
            for dest, arr in ((dest_pre, pa), (dest_post, pb)):
                os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
                with rasterio.open(dest, "w", **prof) as dst:
                    dst.write(arr)
    return dest_pre, dest_post


def fetch_pair(
    choice: TileChoice, out_dir: str,
    lat: float | None = None, lon: float | None = None,
) -> tuple[str, str]:
    d = os.path.join(out_dir, choice.area)
    os.makedirs(d, exist_ok=True)
    pre_dest = os.path.join(d, f"pre_{choice.pre_date}.tif")
    post_dest = os.path.join(d, f"post_{choice.post_date}.tif")
    if _have(pre_dest) and _have(post_dest):
        print("[download] have pre + post")
        return pre_dest, post_dest

    # primary path: read only the AOI window from each COG. Much less data on the
    # wire and a ~14x smaller raster for infer + make_tiles to process.
    if lat is not None and lon is not None:
        try:
            t0 = time.monotonic()
            _window_pair(choice.pre_url, choice.post_url, lon, lat, pre_dest, post_dest)
            print(
                f"[download] AOI window cut in {time.monotonic() - t0:.1f}s "
                f"({os.path.getsize(pre_dest) / 1e6:.1f} + "
                f"{os.path.getsize(post_dest) / 1e6:.1f} MB)"
            )
            return pre_dest, post_dest
        except Exception as ex:  # noqa: BLE001
            print(f"[download] windowed read failed ({ex}); falling back to full COGs")
            for p in (pre_dest, post_dest):
                if os.path.exists(p):
                    os.remove(p)

    # fallback: pull the whole COGs, pre and post in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_pre = pool.submit(download, choice.pre_url, pre_dest)
        f_post = pool.submit(download, choice.post_url, post_dest)
        return f_pre.result(), f_post.result()
