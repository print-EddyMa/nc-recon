#!/usr/bin/env python
"""TerraTriage Phase A CLI.

  # list every Maxar Open Data event, or (re)write the web event registry
  python scripts/run.py events list
  python scripts/run.py events registry

  # fetch Maxar pre/post imagery for an AOI (writes data/raw/<area>/meta.json)
  python scripts/run.py fetch --event HurricaneHelene-Oct24 --area old_fort \
      --lat 35.6293 --lon -82.1804 --event-date 2024-09-26 \
      --name "Old Fort" --subtitle "McDowell County, NC"

  # footprints pipeline (primary): OSM buildings + damage classifier -> GeoJSON
  python scripts/run.py infer --area old_fort                     # backend=auto
  python scripts/run.py infer --area old_fort --backend fusion    # dual-model + tiers

  # segmentation pipeline (xView2-style masks; MockEnsemble unless --weights-dir)
  python scripts/run.py infer-seg --area old_fort --mock

  # sanity map
  python scripts/run.py validate --area old_fort
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "output")
CACHE = os.path.join(ROOT, "data", "cache")
# where the web app (or the hosted service) reads registries + area GeoJSON.
# Override for container deploys where ../web is not on disk.
WEB_DATA = os.environ.get("TERRATRIAGE_WEB_DATA_DIR") or os.path.join(
    ROOT, "..", "web", "public", "data"
)
os.makedirs(WEB_DATA, exist_ok=True)

DEFAULT_CLS_WEIGHTS = os.path.join(ROOT, "weights", "classification.hdf5")


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


def _area_meta_path(area):
    return os.path.join(RAW, area, "meta.json")


def _load_area_meta(area):
    p = _area_meta_path(area)
    if os.path.exists(p):
        with open(p) as fh:
            return json.load(fh)
    return {}


def _save_area_meta(area, data):
    p = _area_meta_path(area)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    prev = _load_area_meta(area)
    prev.update({k: v for k, v in data.items() if v is not None})
    with open(p, "w") as fh:
        json.dump(prev, fh, indent=2)
    return prev


def _resolve_backend(name, cls_weights):
    if name != "auto":
        return name
    from terratriage.classify import _conda_python

    if os.path.exists(cls_weights) and _conda_python():
        print("[run] backend=auto -> fusion (CNN weights + conda env present)")
        return "fusion"
    if os.path.exists(cls_weights):
        print("[run] backend=auto -> keras (CNN weights present, no conda env)")
        return "keras"
    print("[run] backend=auto -> heuristic (no CNN weights)")
    return "heuristic"


# --------------------------------------------------------------------------- #
def cmd_events(a):
    from terratriage import events

    if a.action == "list":
        names = events.list_events(CACHE, refresh=a.refresh)
        for n in names:
            print(n)
        print(f"\n{len(names)} events")
        return

    if a.action == "catalog":
        cat = events.catalog(CACHE, refresh=a.refresh)
        with open(os.path.join(WEB_DATA, "maxar_catalog.json"), "w") as fh:
            json.dump(cat, fh, indent=2)
        print(f"[events] wrote {os.path.join(WEB_DATA, 'maxar_catalog.json')}: {len(cat)} events")
        return

    if a.action == "match":
        import urllib.request

        cat = events.catalog(CACHE)
        try:
            with urllib.request.urlopen(
                "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson",
                timeout=30,
            ) as r:
                hz = json.load(r)
        except Exception as ex:  # noqa: BLE001
            sys.exit(f"could not fetch USGS feed: {ex}")
        for m in events.match_hazards(cat, hz, radius_km=a.radius_km):
            print(f"{m['distance_km']:8.1f} km  {m['event']:40}  <- {m['hazard']}")
        return

    if a.action == "registry":
        metas = []
        for d in sorted(glob.glob(os.path.join(RAW, "*", "meta.json"))):
            with open(d) as fh:
                m = json.load(fh)
            gj = os.path.join(OUT, f"{m['area']}.geojson")
            if os.path.exists(gj):
                with open(gj, encoding="utf-8") as fh:
                    props = json.load(fh)["properties"]
                m.setdefault("model", props.get("model"))
                m.setdefault("notes", props.get("notes"))
                m["n_buildings"] = props.get("n_buildings")
                m["counts"] = props.get("counts")
                m["review"] = props.get("review")
                m["generated"] = props.get("generated")
                m.setdefault("pre_date", props.get("pre_image", {}).get("date"))
                m.setdefault("post_date", props.get("post_image", {}).get("date"))
            metas.append(m)
        if not metas:
            sys.exit("no data/raw/*/meta.json found - run `fetch` first")
        events.write_registry(metas, CACHE, os.path.join(WEB_DATA, "events.json"))
        return


def cmd_fetch(a):
    import datetime as dt
    from terratriage import download as dl

    rows = dl.fetch_catalog(a.event, CACHE)
    choice = dl.choose_tile(rows, a.area, a.lat, a.lon, dt.date.fromisoformat(a.event_date))
    print(f"[fetch] {a.area}: quadkey {choice.quadkey} epsg {choice.epsg}")
    print(f"        pre  {choice.pre_date}  {choice.pre_url}")
    print(f"        post {choice.post_date}  {choice.post_url}")
    dl.fetch_pair(choice, RAW, lat=a.lat, lon=a.lon)

    _save_area_meta(a.area, {
        "event": a.event,
        "area": a.area,
        "name": a.name or a.area.replace("_", " ").title(),
        "subtitle": a.subtitle,
        "region": a.subtitle,
        "center": [a.lon, a.lat],
        "zoom": a.zoom,
        "event_date": a.event_date,
        "pre_date": choice.pre_date,
        "post_date": choice.post_date,
    })
    print(f"[fetch] wrote {_area_meta_path(a.area)}")


def cmd_infer(a):
    from terratriage import predict_footprints as pf

    m = _load_area_meta(a.area)
    event = a.event or m.get("event") or "HurricaneHelene-Oct24"
    backend = _resolve_backend(a.backend, a.cls_weights)
    pre, post = _pair(a.area)
    fc = pf.run(
        pre, post, os.path.join(OUT, f"{a.area}.geojson"),
        event=event, area=a.area, cache_dir=CACHE,
        backend=backend, cls_weights=a.cls_weights,
        pre_meta=_meta(pre), post_meta=_meta(post), limit=a.limit,
        footprint_source=a.source, nc_context=a.nc_context,
    )
    _save_area_meta(a.area, {
        "model": fc["properties"].get("model"),
        "notes": fc["properties"].get("notes"),
    })


def cmd_infer_seg(a):
    from terratriage import predict

    m = _load_area_meta(a.area)
    event = a.event or m.get("event") or "HurricaneHelene-Oct24"
    pre, post = _pair(a.area)
    predict.run(
        pre, post, os.path.join(OUT, f"{a.area}_seg.geojson"),
        event=event, area=a.area,
        weights_dir=a.weights_dir, preset=a.preset, mock=a.mock,
        pre_meta=_meta(pre), post_meta=_meta(post), limit_tiles=a.limit,
        osm_filter=a.osm_filter, cache_dir=CACHE,
    )


def cmd_validate(a):
    from terratriage import validate as v

    pre, post = _pair(a.area)
    gj = os.path.join(OUT, f"{a.area}.geojson")
    v.build_map(gj, pre, post, os.path.join(OUT, f"{a.area}_check.html"))


def cmd_ops_assess(a):
    from terratriage.ops.pipeline import run_area

    run_area(a.area, limit=a.limit, night=not a.day)


def cmd_ops_event_from_fema(a):
    from terratriage.ops.plan.bootstrap import create_from_declaration, draft_from_declaration

    if a.write:
        ev, d = create_from_declaration(a.disaster, a.id)
        print(f"registered {ev.id}: {ev.name}, hazards {', '.join(ev.hazards)}, "
              f"post sources {', '.join(ev.post_sources)}")
    else:
        d = draft_from_declaration(a.disaster)
    print(json.dumps(d.to_dict(), indent=2))


def cmd_ops_field_reference(a):
    from terratriage.ops.analyze.field_reference import compare_area, format_summary

    print(format_summary(compare_area(a.area, a.source, allow_test=a.allow_test)))


def cmd_ops_ground_change(a):
    from terratriage.ops.analyze import ground_change

    ground_change.main(["--area", a.area] + (["--allow-test"] if a.allow_test else []))


def cmd_ops_fetch(a):
    from terratriage.ops.collect.imagery_fetch import fetch_pair

    kw = {"eri_prefix": a.eri_prefix} if a.eri_prefix else {}
    fetch_pair(a.area, a.lon, a.lat, half_m=a.half_m, pre=a.pre, post=a.post, **kw)


def cmd_ops_health(a):
    from terratriage.ops.collect import health

    res = health.run()
    health.print_table(res)
    if any(h.status == "down" and h.source != "usgs_waterservices_legacy" for h in res):
        sys.exit(1)


def cmd_ops_export(a):
    from terratriage.ops.disseminate.exports import export_area

    export_area(a.area, mode="responder")


def cmd_ops_eval(a):
    from terratriage.ops.analyze import evaluate

    rep = evaluate.evaluate()
    print(evaluate.write_report(rep))
    print(json.dumps(rep["labels"], indent=2))


def cmd_ops_calibrate(a):
    from terratriage.ops.analyze import evaluate

    print(json.dumps(evaluate.calibrate(), indent=2))


def cmd_ops_impact(a):
    from terratriage.ops.analyze import impact

    out = impact.run(a.area)
    print(json.dumps({k: v for k, v in out.items() if k != "tracts"}, indent=2))
    for t in out.get("tracts", [])[:8]:
        print(t)


def cmd_ops_aggregate(a):
    from terratriage.ops.disseminate.aggregate import aggregate

    print(aggregate(a.area))


def cmd_ops_reference(a):
    from terratriage.ops.analyze import fema_reference

    out = fema_reference.run(a.area)
    print(out["caveat"])
    for w in out["warnings"]:
        print(f"WARNING: {w}")
    for r in out["zips"]:
        f = (r["fema"] or {}).get("owners") or {}
        print(f"ZIP {r['zip']}: {r['homes_assessed']} homes assessed here, "
              f"~{r['expected_major_plus']} expected Major or Destroyed | FEMA owners: "
              f"{int(f.get('approved', 0))} approved of {int(f.get('registrations', 0))} registered, "
              f"{int(f.get('approved_over_25k', 0))} over $25,000, {int(f.get('max_grants', 0))} maximum grants")
    print(f"{out['unplaced_structures']} structures have no address and could not be placed in a ZIP code")


def cmd_ops_sarcop(a):
    from terratriage.ops.analyze import sarcop_reference

    r = sarcop_reference.compare_area(a.area, allow_test=a.allow_test)
    print(sarcop_reference.format_summary(r))


def cmd_truth_status(a):
    from terratriage.ops import truth

    print(json.dumps(truth.area_status(a.area) if a.area else truth.metrics(), indent=2))


def cmd_truth_release(a):
    from terratriage.ops import truth

    print(json.dumps(truth.release(a.area), indent=2))


def cmd_truth_export(a):
    from terratriage.ops import truth

    data, sheet = truth.export([a.area] if a.area else None, keep=True)
    out = a.out or "ncrecon-verify-dataset.zip"
    with open(out, "wb") as fh:
        fh.write(data)
    print(f"[truth] {sheet['records']} verified records -> {out}")


def cmd_ops_brief(a):
    from terratriage.ops.disseminate.brief import brief

    print(brief(a.area))


def cmd_ops_backup(a):
    """Archive what cannot be re-derived: truth labels, the ops registry,
    assessment outputs + run manifests. Imagery and caches are re-fetchable."""
    import tarfile
    import time as _t

    out = a.out or os.path.join(ROOT, "data", f"ncrecon-backup-{_t.strftime('%Y%m%dT%H%M%SZ', _t.gmtime())}.tar.gz")
    items = [("data/labels", "labels"), ("data/ops_registry.yaml", "ops_registry.yaml"),
             ("data/audit.log", "audit.log"),
             ("data/output/ops", "output_ops"),
             (os.environ.get("NCR_RUNS_DIR") or "runs", "runs"),
             (os.environ.get("NCR_CALIBRATION_DIR") or "config/calibration", "calibration")]
    n = 0
    with tarfile.open(out, "w:gz") as tar:
        for rel, arc in items:
            p = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
            if os.path.exists(p):
                tar.add(p, arcname=arc)
                n += 1
    print(f"[backup] {n} item(s) -> {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    ev = sub.add_parser("events", help="list Maxar events / write the web registries")
    ev.add_argument("action", choices=["list", "registry", "catalog", "match"])
    ev.add_argument("--refresh", action="store_true", help="re-fetch the event index / catalog")
    ev.add_argument("--radius-km", type=float, default=200.0, help="events match: hazard proximity")
    ev.set_defaults(fn=cmd_events)

    f = sub.add_parser("fetch")
    f.add_argument("--event", default="HurricaneHelene-Oct24")
    f.add_argument("--area", required=True)
    f.add_argument("--lat", type=float, required=True)
    f.add_argument("--lon", type=float, required=True)
    f.add_argument("--event-date", default="2024-09-26")
    f.add_argument("--name", default=None, help="display name, e.g. \"Old Fort\"")
    f.add_argument("--subtitle", default="", help="e.g. \"McDowell County, NC\"")
    f.add_argument("--zoom", type=float, default=15.2)
    f.set_defaults(fn=cmd_fetch)

    i = sub.add_parser("infer")
    i.add_argument("--event", default=None, help="overrides meta.json")
    i.add_argument("--area", required=True)
    i.add_argument(
        "--backend", choices=["auto", "heuristic", "keras", "fusion"], default="auto",
        help="auto: fusion if CNN weights + conda env, else keras, else heuristic",
    )
    i.add_argument("--cls-weights", default=DEFAULT_CLS_WEIGHTS)
    i.add_argument("--limit", type=int, default=None)
    i.add_argument(
        "--source", choices=["auto", "osm", "nc_onemap"], default="auto",
        help="building footprints: auto = NC OneMap in NC (needs "
             "TERRATRIAGE_NC_FOOTPRINTS_URL), else OpenStreetMap",
    )
    i.add_argument(
        "--nc-context", action="store_true",
        help="fold NC flood-stage / FEMA-declaration / terrain priors into the "
             "confidence tiers (network calls; fusion backend only)",
    )
    i.set_defaults(fn=cmd_infer)

    s = sub.add_parser("infer-seg")
    s.add_argument("--event", default=None)
    s.add_argument("--area", required=True)
    s.add_argument("--weights-dir", default=None)
    s.add_argument("--preset", default="fast")
    s.add_argument("--mock", action="store_true")
    s.add_argument("--limit", type=int, default=None)
    s.add_argument("--osm-filter", action="store_true",
                   help="D1: drop/flag predicted footprints that don't overlap an OSM building")
    s.set_defaults(fn=cmd_infer_seg)

    v = sub.add_parser("validate")
    v.add_argument("--area", required=True)
    v.set_defaults(fn=cmd_validate)

    o = sub.add_parser("ops-assess", help="ops mode: fused, calibrated-where-possible, provenance-carrying assessment")
    o.add_argument("--area", required=True)
    o.add_argument("--limit", type=int, default=None)
    o.add_argument("--day", action="store_true", help="use daytime occupant estimates (default: night)")
    o.set_defaults(fn=cmd_ops_assess)

    oe = sub.add_parser("ops-event-from-fema",
                        help="ops mode: draft (or --write) an event for any disaster from its FEMA number")
    oe.add_argument("--disaster", type=int, required=True, help="FEMA disaster number, e.g. 4856")
    oe.add_argument("--id", default=None, help="event id (default: <hazard>-<year>-<state>-dr<number>)")
    oe.add_argument("--write", action="store_true", help="register the event in the ops registry")
    oe.set_defaults(fn=cmd_ops_event_from_fema)

    of = sub.add_parser("ops-fetch", help="ops mode: co-gridded pre/post pair (NC orthos or NAIP -> NC orthos or NOAA ERI)")
    of.add_argument("--area", required=True)
    of.add_argument("--lon", type=float, required=True)
    of.add_argument("--lat", type=float, required=True)
    of.add_argument("--half-m", type=float, default=800.0)
    of.add_argument("--pre", default="nc_2020_2023", choices=["nc_2020_2023", "naip"])
    of.add_argument("--post", default="nc_helene_2025", choices=["nc_helene_2025", "eri"])
    of.add_argument("--eri-prefix", default=None, help="NOAA ERI event folder, e.g. 2024_Hurricane_Helene")
    of.set_defaults(fn=cmd_ops_fetch)

    sub.add_parser("ops-health", help="ops mode: live status of every data source").set_defaults(fn=cmd_ops_health)
    ox = sub.add_parser("ops-export", help="ops mode: GeoJSON/CSV/KML/GPKG/FileGDB/Survey123 (responder)")
    ox.add_argument("--area", required=True)
    ox.set_defaults(fn=cmd_ops_export)
    oi = sub.add_parser("ops-impact", help="ops mode: expected displaced people + tract need index")
    oi.add_argument("--area", required=True)
    oi.set_defaults(fn=cmd_ops_impact)
    og = sub.add_parser("ops-aggregate", help="ops mode: public tract-level product (no PII)")
    og.add_argument("--area", required=True)
    og.set_defaults(fn=cmd_ops_aggregate)
    ob = sub.add_parser("ops-brief", help="ops mode: one-page situation brief (HTML + text)")
    ob.add_argument("--area", required=True)
    ob.set_defaults(fn=cmd_ops_brief)
    tv = sub.add_parser("truth-status", help="Groma Verify: verification progress (one area or all)")
    tv.add_argument("--area")
    tv.set_defaults(fn=cmd_truth_status)
    tr = sub.add_parser("truth-release", help="Groma Verify: write verified consensus into the protocol label file")
    tr.add_argument("--area", required=True)
    tr.set_defaults(fn=cmd_truth_release)
    te = sub.add_parser("truth-export", help="Groma Verify: dataset of verified labels + datasheet (zip)")
    te.add_argument("--area")
    te.add_argument("--out")
    te.set_defaults(fn=cmd_truth_export)
    sp_sar = sub.add_parser("ops-sarcop", help="ops mode: Groma calls beside Buncombe's Helene SAR field categories (comparison, not validation)")
    sp_sar.add_argument("--area", required=True)
    sp_sar.add_argument("--allow-test", action="store_true", help="permit a TEST (hold-out) area")
    sp_sar.set_defaults(fn=cmd_ops_sarcop)
    ofr = sub.add_parser("ops-field-reference",
                         help="ops mode: calls beside published building damage records (CAL FIRE DINS, FEMA, NEMAC, SARCOP)")
    ofr.add_argument("--area", required=True)
    ofr.add_argument("--source", default=None, choices=["dins", "fema_hgda", "nemac", "sarcop"],
                     help="default: chosen from the event's hazard, state and year")
    ofr.add_argument("--allow-test", action="store_true", help="permit a TEST (hold-out) area")
    ofr.set_defaults(fn=cmd_ops_field_reference)
    ogc = sub.add_parser("ops-ground-change",
                         help="ops mode: lidar ground change around each building (NC 2025 QL1 vs 3DEP)")
    ogc.add_argument("--area", required=True)
    ogc.add_argument("--allow-test", action="store_true", help="permit a TEST (hold-out) area")
    ogc.set_defaults(fn=cmd_ops_ground_change)
    orf = sub.add_parser("ops-reference", help="ops mode: FEMA housing assistance by ZIP beside the assessment")
    orf.add_argument("--area", required=True)
    orf.set_defaults(fn=cmd_ops_reference)
    obk = sub.add_parser("ops-backup", help="ops mode: archive labels, registry, outputs")
    obk.add_argument("--out", default=None)
    obk.set_defaults(fn=cmd_ops_backup)
    sub.add_parser("ops-eval", help="ops mode: accuracy report from data/labels").set_defaults(fn=cmd_ops_eval)
    sub.add_parser("ops-calibrate", help="ops mode: fit temperature + conformal on TUNE labels").set_defaults(fn=cmd_ops_calibrate)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
