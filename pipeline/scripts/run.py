#!/usr/bin/env python
"""TerraTriage Phase A CLI.

  # fetch Maxar pre/post imagery for an AOI
  python scripts/run.py fetch --event HurricaneHelene-Oct24 --area old_fort \
      --lat 35.6293 --lon -82.1804 --event-date 2024-09-26

  # footprints pipeline (primary): OSM buildings + damage classifier -> GeoJSON
  python scripts/run.py infer --area old_fort --backend heuristic
  python scripts/run.py infer --area old_fort --backend keras \
      --cls-weights weights/classification.hdf5

  # segmentation pipeline (xView2-style masks; MockEnsemble unless --weights-dir)
  python scripts/run.py infer-seg --area old_fort --mock

  # sanity map
  python scripts/run.py validate --area old_fort
"""
import argparse
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "output")
CACHE = os.path.join(ROOT, "data", "cache")


def _pair(area):
    pre = sorted(glob.glob(os.path.join(RAW, area, "pre_*.tif")))
    post = sorted(glob.glob(os.path.join(RAW, area, "post_*.tif")))
    if not pre or not post:
        sys.exit(f"no pre/post tif for {area} in {os.path.join(RAW, area)} - run `fetch` first")
    return pre[0], post[0]


def _meta(path):
    base = os.path.basename(path)
    date = base.split("_", 1)[1].rsplit(".", 1)[0]
    return {"date": date, "source": "Maxar Open Data"}


def cmd_fetch(a):
    import datetime as dt
    from terratriage import download as dl

    rows = dl.fetch_catalog(a.event, CACHE)
    choice = dl.choose_tile(rows, a.area, a.lat, a.lon, dt.date.fromisoformat(a.event_date))
    print(f"[fetch] {a.area}: quadkey {choice.quadkey} epsg {choice.epsg}")
    print(f"        pre  {choice.pre_date}  {choice.pre_url}")
    print(f"        post {choice.post_date}  {choice.post_url}")
    dl.fetch_pair(choice, RAW)


def cmd_infer(a):
    from terratriage import predict_footprints as pf

    backend = a.backend
    if backend == "auto":
        backend = "keras" if os.path.exists(a.cls_weights) else "heuristic"
        print(f"[run] backend=auto -> {backend}")
    pre, post = _pair(a.area)
    pf.run(
        pre, post, os.path.join(OUT, f"{a.area}.geojson"),
        event=a.event, area=a.area, cache_dir=CACHE,
        backend=backend, cls_weights=a.cls_weights,
        pre_meta=_meta(pre), post_meta=_meta(post), limit=a.limit,
    )


def cmd_infer_seg(a):
    from terratriage import predict

    pre, post = _pair(a.area)
    predict.run(
        pre, post, os.path.join(OUT, f"{a.area}_seg.geojson"),
        event=a.event, area=a.area,
        weights_dir=a.weights_dir, preset=a.preset, mock=a.mock,
        pre_meta=_meta(pre), post_meta=_meta(post), limit_tiles=a.limit,
    )


def cmd_validate(a):
    from terratriage import validate as v

    pre, post = _pair(a.area)
    gj = os.path.join(OUT, f"{a.area}.geojson")
    v.build_map(gj, pre, post, os.path.join(OUT, f"{a.area}_check.html"))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch")
    f.add_argument("--event", default="HurricaneHelene-Oct24")
    f.add_argument("--area", required=True)
    f.add_argument("--lat", type=float, required=True)
    f.add_argument("--lon", type=float, required=True)
    f.add_argument("--event-date", default="2024-09-26")
    f.set_defaults(fn=cmd_fetch)

    i = sub.add_parser("infer")
    i.add_argument("--event", default="HurricaneHelene-Oct24")
    i.add_argument("--area", required=True)
    i.add_argument(
        "--backend", choices=["auto", "heuristic", "keras"], default="auto",
        help="auto: xView2 baseline CNN if classification.hdf5 is present, else heuristic",
    )
    i.add_argument("--cls-weights", default=os.path.join(ROOT, "weights", "classification.hdf5"))
    i.add_argument("--limit", type=int, default=None)
    i.set_defaults(fn=cmd_infer)

    s = sub.add_parser("infer-seg")
    s.add_argument("--event", default="HurricaneHelene-Oct24")
    s.add_argument("--area", required=True)
    s.add_argument("--weights-dir", default=None)
    s.add_argument("--preset", default="fast")
    s.add_argument("--mock", action="store_true")
    s.add_argument("--limit", type=int, default=None)
    s.set_defaults(fn=cmd_infer_seg)

    v = sub.add_parser("validate")
    v.add_argument("--area", required=True)
    v.set_defaults(fn=cmd_validate)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
