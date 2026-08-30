#!/usr/bin/env python
"""Phase D5 — automated pipeline trigger.

Every run:
  1. refresh the Maxar Open Data event index
  2. diff it against data/cache/events_seen.json  -> newly published events
  3. pull a fresh live-hazard snapshot (USGS quakes + GDACS multi-hazard)
  4. for each new event, check whether it sits near an active hazard
  5. on a match, (unless --dry-run) run  run.py fetch + infer  for a
     bbox-derived AOI and append a line to data/output/auto_runs.log

--dry-run (the default) does everything except step 5's fetch/infer.

Wire it to cron for a hands-off "the LA fires would have triggered this as they
happened" demo:

    */30 * * * *  cd /path/to/terratriage/pipeline && ./.venv/bin/python scripts/poller.py --run
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
CACHE = os.path.join(ROOT, "data", "cache")
OUT = os.path.join(ROOT, "data", "output")
SEEN = os.path.join(CACHE, "events_seen.json")
LOG = os.path.join(OUT, "auto_runs.log")

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"


def _get_json(url: str, timeout: int = 40):
    req = urllib.request.Request(url, headers={"User-Agent": "TerraTriage/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def hazards_snapshot() -> dict:
    """USGS + GDACS as one GeoJSON point FeatureCollection (best-effort)."""
    feats = []
    try:
        for f in _get_json(USGS_URL).get("features", []):
            g = f.get("geometry") or {}
            if g.get("type") == "Point":
                p = f.get("properties", {})
                feats.append({"type": "Feature", "geometry": g, "properties": {
                    "source": "usgs", "hazard_type": "earthquake",
                    "title": p.get("place"), "mag": p.get("mag"), "time": p.get("time"),
                }})
    except Exception as ex:  # noqa: BLE001
        print(f"[poller] USGS fetch failed: {ex}")
    try:
        gd = _get_json(GDACS_URL)
        items = gd.get("features") or gd.get("events") or []
        for it in items:
            g = it.get("geometry")
            pr = it.get("properties", it)
            if not g and "latitude" in pr and "longitude" in pr:
                g = {"type": "Point", "coordinates": [pr["longitude"], pr["latitude"]]}
            if g and g.get("type") == "Point":
                feats.append({"type": "Feature", "geometry": g, "properties": {
                    "source": "gdacs",
                    "hazard_type": (pr.get("eventtype") or pr.get("type") or "").lower() or None,
                    "title": pr.get("name") or pr.get("htmldescription") or pr.get("eventname"),
                    "alertlevel": pr.get("alertlevel"),
                }})
    except Exception as ex:  # noqa: BLE001
        print(f"[poller] GDACS fetch failed: {ex}")
    return {"type": "FeatureCollection", "features": feats}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True,
                   help="report only (default)")
    g.add_argument("--run", dest="dry_run", action="store_false",
                   help="actually fetch + infer on a match")
    ap.add_argument("--radius-km", type=float, default=150.0)
    a = ap.parse_args()

    from terratriage import events

    names = events.list_events(CACHE, refresh=True)
    seen = json.load(open(SEEN)) if os.path.exists(SEEN) else []
    new = [n for n in names if n not in seen]
    print(f"[poller] {len(names)} events, {len(new)} new: {new or '-'}")

    hz = hazards_snapshot()
    print(f"[poller] hazards snapshot: {len(hz['features'])} active points")

    matched = []
    for ev in new:
        try:
            summ = events.event_summary(ev, CACHE)
        except Exception as ex:  # noqa: BLE001
            print(f"[poller] {ev}: summary failed ({ex})")
            continue
        reg = [{"id": ev, "center": summ.get("center"), "bbox": summ.get("bbox")}]
        hits = events.match_hazards(reg, hz, radius_km=a.radius_km)
        if hits:
            matched.append((ev, summ, hits[0]))
            print(f"[poller] MATCH {ev} <- {hits[0]['hazard']} ({hits[0]['distance_km']} km)")

    if not a.dry_run:
        import shutil

        os.makedirs(OUT, exist_ok=True)
        web_data = os.path.join(ROOT, "..", "web", "public", "data")
        for ev, summ, hit in matched:
            c = summ.get("center")
            if not c:
                continue
            area = ev.lower().replace("-", "_")[:40]
            stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            steps = [
                ("run.py", ["fetch", "--event", ev, "--area", area,
                            "--lat", str(c[1]), "--lon", str(c[0])]),
                ("run.py", ["infer", "--area", area]),
                ("make_tiles.py", ["--area", area]),
                ("run.py", ["events", "registry"]),
            ]
            ok = True
            for script, cmd in steps:
                r = subprocess.run(
                    [sys.executable, os.path.join(ROOT, "scripts", script), *cmd],
                    capture_output=True, text=True,
                )
                print(r.stdout[-500:] or r.stderr[-500:])
                if r.returncode != 0:
                    ok = False
                    break
            if ok:
                src = os.path.join(OUT, f"{area}.geojson")
                if os.path.exists(src):
                    os.makedirs(web_data, exist_ok=True)
                    shutil.copy2(src, os.path.join(web_data, f"{area}.geojson"))
            with open(LOG, "a") as fh:
                fh.write(f"{stamp}\t{ev}\t{hit['hazard']}\t{hit['distance_km']}km\t{'ok' if ok else 'FAILED'}\n")

    # remember what we've now seen
    os.makedirs(CACHE, exist_ok=True)
    json.dump(sorted(set(names)), open(SEEN, "w"), indent=2)
    print(f"[poller] {'DRY-RUN — no pipeline run' if a.dry_run else 'done'}; "
          f"{len(matched)} match(es)")


if __name__ == "__main__":
    main()
