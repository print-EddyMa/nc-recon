"""Maxar Open Data event registry (Phase C1).

Phase A/B were hardcoded to one event (`HurricaneHelene-Oct24`). This module
makes the event a lookup: it lists every event the community STAC mirror
(github.com/opengeos/maxar-open-data) publishes, and for any one of them derives
the coverage bbox, capture date range, and whether pre/post captures straddle a
given event date — all from the per-event TSV that `download.py` already knows
how to fetch.

`write_registry` emits `web/public/data/events.json`, the offline contract the
web event picker reads. `match_hazards` cross-references the registry against a
live-hazard snapshot for the Phase C4 / D5 "imagery just dropped near something
you're tracking" prompt.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import urllib.request
from typing import Any

from . import download

GH_CONTENTS = "https://api.github.com/repos/opengeos/maxar-open-data/contents/datasets"

_HAZARD_KEYWORDS = [
    ("wildfire", "wildfire"), ("fire", "wildfire"),
    ("hurricane", "hurricane"), ("typhoon", "hurricane"), ("cyclone", "cyclone"),
    ("flood", "flood"), ("flooding", "flood"),
    ("earthquake", "earthquake"), ("quake", "earthquake"),
    ("tornado", "tornado"), ("volcano", "volcano"), ("eruption", "volcano"),
    ("landslide", "landslide"), ("tsunami", "tsunami"),
]


def guess_hazard(event: str) -> str:
    low = event.lower()
    for kw, label in _HAZARD_KEYWORDS:
        if kw in low:
            return label
    return "other"


def list_events(cache_dir: str, refresh: bool = False) -> list[str]:
    """Every event name in the opengeos/maxar-open-data `datasets/` folder."""
    os.makedirs(cache_dir, exist_ok=True)
    local = os.path.join(cache_dir, "events_index.json")
    if refresh or not os.path.exists(local):
        req = urllib.request.Request(
            GH_CONTENTS, headers={"User-Agent": "TerraTriage/1.0", "Accept": "application/vnd.github+json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            entries = json.load(resp)
        names = sorted(
            e["name"][:-4] for e in entries
            if e["type"] == "file" and e["name"].endswith(".tsv")
        )
        with open(local, "w") as fh:
            json.dump(names, fh, indent=2)
        return names
    with open(local) as fh:
        return json.load(fh)


def _row_bbox_lonlat(row: dict) -> tuple[float, float, float, float]:
    from pyproj import Transformer

    from .download import row_epsg

    epsg = row_epsg(row)
    minx, miny, maxx, maxy = (float(v) for v in row["proj:bbox"].split(","))
    tr = Transformer.from_crs(epsg, 4326, always_xy=True)
    xs, ys = [], []
    for x, y in ((minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)):
        lon, lat = tr.transform(x, y)
        xs.append(lon)
        ys.append(lat)
    return min(xs), min(ys), max(xs), max(ys)


# Hand-verified event dates for the events we actually assess. The
# "widest gap" heuristic below is unreliable when an event has sparse
# historical imagery (Helene has captures from 2019/2020/2022 before 2024, so
# the widest gap lands in 2021, nowhere near the storm).
KNOWN_EVENT_DATES = {
    "HurricaneHelene-Oct24": "2024-09-27",
    "WildFires-LosAngeles-Jan-2025": "2025-01-07",
    "Hurricane-Ian-9-26-2022": "2022-09-28",
    "Hurricane-Milton-Oct-2024": "2024-10-09",
    "Hurricane-Debby-Aug-2024": "2024-08-05",
    "Floods-Spain-Oct24": "2024-10-29",
}


def _infer_event_date(dates: list[str]) -> str | None:
    """Best guess for when the event happened, from the sorted distinct capture
    dates. Post-disaster tasking produces a burst of captures within ~30 days, so
    the event date is the start of the gap that is immediately followed by the
    most captures in the next 30 days (ties broken toward the widest gap)."""
    if not dates:
        return None
    if len(dates) == 1:
        return dates[0]
    ds = [dt.date.fromisoformat(d) for d in dates]
    best_i, best_score = 0, (-1, -1)
    for i in range(len(ds) - 1):
        gap = (ds[i + 1] - ds[i]).days
        if gap < 14:  # not an event boundary
            continue
        after = sum(1 for d in ds[i + 1 :] if (d - ds[i + 1]).days <= 30)
        score = (after, gap)
        if score > best_score:
            best_score, best_i = score, i
    if best_score == (-1, -1):  # no gap >= 14 days — fall back to the widest
        best_i = max(range(len(ds) - 1), key=lambda i: (ds[i + 1] - ds[i]).days)
    # the event sits just after the last pre-event capture
    return (ds[best_i] + dt.timedelta(days=1)).isoformat()


def event_summary(
    event: str, cache_dir: str, event_date: str | dt.date | None = None
) -> dict[str, Any]:
    """Coverage + capture metadata for one event, from its STAC TSV."""
    rows = download.fetch_catalog(event, cache_dir)
    if not rows:
        raise LookupError(f"{event}: empty or missing catalog")

    dates = sorted({r["datetime"][:10] for r in rows if r.get("datetime")})
    quadkeys = sorted({r["quadkey"] for r in rows if r.get("quadkey")})

    w = s = e = n = None
    for r in rows:
        try:
            bw, bs, be, bn = _row_bbox_lonlat(r)
        except Exception:  # noqa: BLE001
            continue
        w = bw if w is None else min(w, bw)
        s = bs if s is None else min(s, bs)
        e = be if e is None else max(e, be)
        n = bn if n is None else max(n, bn)

    # when did the event happen: a hand-verified date if we have one, else infer
    # it from the capture-date pattern (see _infer_event_date)
    suggested = KNOWN_EVENT_DATES.get(event) or _infer_event_date(dates)

    ed = None
    if event_date is not None:
        ed = event_date if isinstance(event_date, dt.date) else dt.date.fromisoformat(str(event_date))
    elif suggested:
        ed = dt.date.fromisoformat(suggested)
    has_pre = has_post = False
    if ed is not None:
        for d in dates:
            if dt.date.fromisoformat(d) < ed:
                has_pre = True
            else:
                has_post = True

    return {
        "event": event,
        "hazard": guess_hazard(event),
        "n_captures": len(rows),
        "n_quadkeys": len(quadkeys),
        "capture_dates": [dates[0], dates[-1]] if dates else [],
        "bbox": None if w is None else [round(w, 5), round(s, 5), round(e, 5), round(n, 5)],
        "center": None if w is None else [round((w + e) / 2, 5), round((s + n) / 2, 5)],
        "event_date": ed.isoformat() if ed else None,
        "suggested_event_date": suggested,
        "has_pre": has_pre,
        "has_post": has_post,
    }


def coverage(event: str, cache_dir: str, event_date: str | None = None) -> dict[str, Any]:
    """The footprint of a Maxar event's *assessable* area — the quadkeys that
    have both a pre-event and a post-event capture. Returns lon/lat cell boxes
    the Assess screen draws so the user clicks where there is real before/after
    imagery."""
    from .download import _has_pre_post

    _bbox = _row_bbox_lonlat  # defined in this module
    rows = download.fetch_catalog(event, cache_dir)
    ed_str = event_date or KNOWN_EVENT_DATES.get(event)
    if not ed_str:
        dates = sorted({r["datetime"][:10] for r in rows if r.get("datetime")})
        ed_str = _infer_event_date(dates)
    ed = dt.date.fromisoformat(ed_str) if ed_str else dt.date(2000, 1, 1)

    by_qk: dict[str, list[dict]] = {}
    for r in rows:
        by_qk.setdefault(r.get("quadkey", ""), []).append(r)

    cells: list[list[float]] = []
    w = s = e = n = None
    for qk, rs in by_qk.items():
        if not qk or not _has_pre_post(rs, ed):
            continue
        try:
            bw, bs, be, bn = _bbox(rs[0])
        except Exception:  # noqa: BLE001
            continue
        cells.append([round(bw, 5), round(bs, 5), round(be, 5), round(bn, 5)])
        w = bw if w is None else min(w, bw)
        s = bs if s is None else min(s, bs)
        e = be if e is None else max(e, be)
        n = bn if n is None else max(n, bn)
    return {
        "event": event,
        "event_date": ed_str,
        "n_cells": len(cells),
        "bbox": None if w is None else [round(w, 5), round(s, 5), round(e, 5), round(n, 5)],
        "cells": cells,
    }


def build_registry(area_metas: list[dict], cache_dir: str) -> list[dict[str, Any]]:
    """Group per-area `meta.json` dicts into the events.json structure.

    Each `area_meta` is what `run.py fetch` writes to data/raw/<area>/meta.json,
    optionally enriched with `model` / `notes` / `n_buildings` from its GeoJSON.
    """
    by_event: dict[str, dict[str, Any]] = {}
    for m in area_metas:
        ev = m["event"]
        slot = by_event.get(ev)
        if slot is None:
            try:
                summ = event_summary(ev, cache_dir, m.get("event_date"))
            except Exception as ex:  # noqa: BLE001
                print(f"[events] {ev}: summary failed ({ex}); using area data only")
                summ = {"hazard": guess_hazard(ev), "bbox": None, "capture_dates": []}
            slot = by_event[ev] = {
                "id": ev,
                "event": ev,
                "name": m.get("event_name") or _pretty(ev),
                "hazard": summ.get("hazard", guess_hazard(ev)),
                "region": m.get("region"),
                "event_date": m.get("event_date"),
                "bbox": summ.get("bbox"),
                "capture_dates": summ.get("capture_dates", []),
                "areas": [],
            }
        slot["areas"].append({
            "id": m["area"],
            "name": m.get("name") or _pretty(m["area"]),
            "subtitle": m.get("subtitle", ""),
            "center": m["center"],
            "zoom": m.get("zoom", 15.2),
            "hero": m.get("hero"),
            "pre_date": m.get("pre_date"),
            "post_date": m.get("post_date"),
            "model": m.get("model"),
            "notes": m.get("notes"),
            "n_buildings": m.get("n_buildings"),
            "counts": m.get("counts"),
            "review": m.get("review"),
            "generated": m.get("generated"),
        })
    return sorted(by_event.values(), key=lambda ev: ev["name"])


def catalog(cache_dir: str, refresh: bool = False, only: list[str] | None = None) -> list[dict]:
    """Compact summary of *every* Maxar Open Data event — the full catalogue the
    Live Monitor cross-references live hazards against. Cached aggregate at
    data/cache/maxar_catalog.json; per-event TSVs are cached by fetch_catalog.
    """
    agg = os.path.join(cache_dir, "maxar_catalog.json")
    if not refresh and only is None and os.path.exists(agg):
        with open(agg) as fh:
            return json.load(fh)

    names = only or list_events(cache_dir, refresh=refresh)
    out: list[dict] = []
    for i, ev in enumerate(names):
        try:
            s = event_summary(ev, cache_dir)
        except Exception as ex:  # noqa: BLE001
            print(f"[events] catalog: {ev} skipped ({ex})")
            continue
        out.append({
            "id": ev,
            "name": _pretty(ev),
            "hazard": s["hazard"],
            "center": s["center"],
            "bbox": s["bbox"],
            "capture_dates": s["capture_dates"],
            "suggested_event_date": s.get("suggested_event_date"),
            "n_captures": s["n_captures"],
            "n_quadkeys": s["n_quadkeys"],
        })
        if (i + 1) % 10 == 0:
            print(f"[events] catalog: {i + 1}/{len(names)}")
    out.sort(key=lambda e: e["capture_dates"][-1] if e["capture_dates"] else "", reverse=True)
    if only is None:
        with open(agg, "w") as fh:
            json.dump(out, fh, indent=2)
        print(f"[events] wrote {agg}: {len(out)} events")
    return out


def write_registry(area_metas: list[dict], cache_dir: str, out_path: str) -> list[dict]:
    reg = build_registry(area_metas, cache_dir)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(reg, fh, indent=2)
    n_areas = sum(len(e["areas"]) for e in reg)
    print(f"[events] wrote {out_path}: {len(reg)} event(s), {n_areas} area(s)")
    return reg


# hand-written display names for events we actually demo; everything else falls
# back to the _pretty() heuristic.
EVENT_NAMES = {
    "HurricaneHelene-Oct24": "Hurricane Helene",
    "WildFires-LosAngeles-Jan-2025": "LA Wildfires (Palisades / Eaton)",
    "Hurricane-Ian-9-26-2022": "Hurricane Ian",
    "Hurricane-Fiona-9-19-2022": "Hurricane Fiona",
    "Maui-Hawaii-fires-Aug-23": "Maui Wildfires",
    "Earthquake-Myanmar-March-2025": "Myanmar Earthquake",
    "Floods-Spain-Oct24": "Spain Floods",
}

_MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept",
           "oct", "nov", "dec"}


def _pretty(slug: str) -> str:
    if slug in EVENT_NAMES:
        return EVENT_NAMES[slug]
    # split camelCase, then on separators
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", slug).replace("-", " ").replace("_", " ")
    words = []
    for w in spaced.split():
        if re.fullmatch(r"\d{1,2}", w) or re.fullmatch(r"20\d{2}", w) or re.fullmatch(r"\d{1,2}", w):
            continue  # drop bare day/year fragments
        if w.lower().rstrip("0123456789") in _MONTHS:
            continue  # drop month tokens like "Oct24"
        words.append(w[:1].upper() + w[1:] if not w.isupper() else w)
    return " ".join(words).strip() or slug


# --------------------------------------------------------------------------- #
# Phase C4 / D5: does a published event sit near a live hazard we're tracking?
# --------------------------------------------------------------------------- #
def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


# GDACS/USGS hazard_type strings -> our hazard label, for agreement scoring
_HZ_ALIGN = {
    "eq": "earthquake", "earthquake": "earthquake",
    "tc": "cyclone", "cyclone": "cyclone", "hurricane": "hurricane", "typhoon": "hurricane",
    "fl": "flood", "flood": "flood",
    "wf": "wildfire", "fire": "wildfire", "wildfire": "wildfire",
    "vo": "volcano", "volcano": "volcano",
}


def match_hazards(
    registry: list[dict], hazards_geojson: dict, radius_km: float = 150.0
) -> list[dict[str, Any]]:
    """Pairs of (catalogue/registry event, live hazard) whose centres are within
    `radius_km`. Each match carries a `score` (0..1, higher = better): closer +
    same hazard family + more recent imagery. Sorted best-first, deduped so each
    event appears once (against its nearest hazard)."""
    import datetime as dt

    hz = []
    for f in hazards_geojson.get("features", []):
        g = f.get("geometry") or {}
        if g.get("type") == "Point":
            hz.append((tuple(g["coordinates"][:2]), f.get("properties", {})))

    today = dt.date.today()
    best: dict[str, dict[str, Any]] = {}
    for ev in registry:
        c = ev.get("center") or (
            [(ev["bbox"][0] + ev["bbox"][2]) / 2, (ev["bbox"][1] + ev["bbox"][3]) / 2]
            if ev.get("bbox") else None
        )
        if not c:
            continue
        ev_haz = ev.get("hazard") or guess_hazard(ev["id"])
        latest = (ev.get("capture_dates") or [None, None])[-1]
        age_days = None
        if latest:
            try:
                age_days = (today - dt.date.fromisoformat(latest)).days
            except ValueError:
                pass
        for (hlon, hlat), props in hz:
            d = _haversine_km((c[0], c[1]), (hlon, hlat))
            if d > radius_km:
                continue
            raw_ht = str(props.get("hazard_type") or props.get("type") or "").lower()
            live_haz = _HZ_ALIGN.get(raw_ht, raw_ht or None)
            type_ok = live_haz is not None and live_haz == ev_haz
            dist_score = 1.0 - d / radius_km
            fresh_score = 1.0 if (age_days is not None and age_days <= 120) else (
                0.4 if (age_days is not None and age_days <= 400) else 0.1
            )
            score = 0.5 * dist_score + 0.3 * (1.0 if type_ok else 0.0) + 0.2 * fresh_score
            m = {
                "event": ev["id"],
                "hazard": props.get("title") or props.get("place") or props.get("eventname") or "hazard",
                "hazard_type": live_haz,
                "type_match": type_ok,
                "distance_km": round(d, 1),
                "imagery_age_days": age_days,
                "score": round(score, 3),
            }
            if ev["id"] not in best or score > best[ev["id"]]["score"]:
                best[ev["id"]] = m
    return sorted(best.values(), key=lambda m: -m["score"])
