#!/usr/bin/env python
"""Tune the fusion confidence-tier thresholds for a specific assessed area.

    python scripts/calibrate.py --area <area> [--labels labels.csv] [--write]

Reads pipeline/data/output/<area>.geojson (schema 1.1, needs the `sources` dict
that the fusion backend writes). Sweeps MARGIN_DECISIVE / MARGIN_UNSURE and the
minimum-area cutoff and reports, for each combination:

  - how many buildings land in the `review` tier (the human workload), and
  - if --labels is given (CSV: id,true_class), the precision of the `high` tier
    and the recall of real damage among `high` — i.e. is it safe to auto-accept.

With --write it saves the best combination to pipeline/data/calibration.json,
which fusion.py picks up on the next run (no code change).

Output: pipeline/data/output/<area>_calibration.html
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
OUT = os.path.join(ROOT, "data", "output")

from terratriage import fusion  # noqa: E402

DECISIVE_GRID = [0.14, 0.18, 0.20, 0.24, 0.30]
UNSURE_GRID = [0.06, 0.08, 0.10, 0.12, 0.16]
AREA_GRID = [8.0, 12.0, 16.0, 24.0]


def _load(area: str) -> list[dict]:
    path = os.path.join(OUT, f"{area}.geojson")
    if not os.path.exists(path):
        sys.exit(f"no {path} — run `run.py infer --area {area}` first")
    with open(path) as fh:
        fc = json.load(fh)
    rows = []
    for f in fc["features"]:
        p = f["properties"]
        s = p.get("sources")
        if not s:
            continue
        rows.append({
            "id": p["id"],
            "cnn": int(s["cnn"]),
            "heur": int(s["heuristic"]),
            "margin": float(s["margin"]),
            "area_m2": float(p["area_m2"]),
            "cls": int(p["damage_class"]),
        })
    if not rows:
        sys.exit(f"{area}: no per-building `sources` — re-run infer with the fusion backend")
    return rows


def _tier(row: dict, decisive: float, unsure: float, min_area: float) -> str:
    if row["area_m2"] < min_area:
        return "review"
    if row["margin"] < unsure:
        return "review"
    gap = abs(row["heur"] - row["cnn"])
    if gap == 0:
        return "high"
    if gap == 1 and row["margin"] >= decisive:
        return "high"
    return "review"


def _score(rows, labels, decisive, unsure, min_area):
    review = high = 0
    tp = fp = fn = 0  # among `high`: predicted-damage right/wrong; damage missed to review
    for r in rows:
        t = _tier(r, decisive, unsure, min_area)
        if t == "review":
            review += 1
        else:
            high += 1
        if labels is not None and r["id"] in labels:
            true_dmg = labels[r["id"]] >= 1
            pred_dmg = r["cnn"] >= 1
            if t == "high" and pred_dmg and true_dmg:
                tp += 1
            elif t == "high" and pred_dmg and not true_dmg:
                fp += 1
            elif t == "review" and true_dmg:
                fn += 1
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    return {
        "decisive": decisive, "unsure": unsure, "min_area": min_area,
        "review": review, "high": high, "review_pct": round(100 * review / len(rows), 1),
        "high_precision": None if prec is None else round(prec, 3),
        "damage_recall_in_high": None if rec is None else round(rec, 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", required=True)
    ap.add_argument("--labels", default=None, help="CSV: id,true_class (0-3)")
    ap.add_argument("--write", action="store_true", help="save the best combo to data/calibration.json")
    a = ap.parse_args()

    rows = _load(a.area)
    labels = None
    if a.labels:
        labels = {}
        with open(a.labels) as fh:
            for rec in csv.DictReader(fh):
                try:
                    labels[rec["id"]] = int(rec["true_class"])
                except (KeyError, ValueError):
                    pass
        print(f"[calibrate] {len(labels)} hand labels")

    results = [
        _score(rows, labels, d, u, m)
        for d, u, m in itertools.product(DECISIVE_GRID, UNSURE_GRID, AREA_GRID)
    ]
    # baseline = the current module defaults
    base = _score(rows, labels, fusion.MARGIN_DECISIVE, fusion.MARGIN_UNSURE, fusion.MIN_TRUSTWORTHY_AREA)

    if labels is not None:
        # want high precision in `high`, then low review workload
        ranked = sorted(
            (r for r in results if r["high_precision"] is not None),
            key=lambda r: (-(r["high_precision"] or 0), r["review_pct"]),
        )
    else:
        # no labels: just the combos closest to a 20% review budget
        ranked = sorted(results, key=lambda r: abs(r["review_pct"] - 20))
    best = ranked[0] if ranked else base

    rowhtml = "".join(
        f"<tr><td>{r['decisive']}</td><td>{r['unsure']}</td><td>{r['min_area']}</td>"
        f"<td>{r['review']}</td><td>{r['review_pct']}%</td>"
        f"<td>{r['high_precision']}</td><td>{r['damage_recall_in_high']}</td></tr>"
        for r in sorted(results, key=lambda r: (r["decisive"], r["unsure"], r["min_area"]))
    )
    html = f"""<!doctype html><meta charset=utf-8>
<title>{a.area} — fusion calibration</title>
<style>body{{font:13px/1.5 system-ui;margin:2rem;color:#1a1a1a}}
table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:3px 8px;text-align:right}}
.k{{background:#eef}}</style>
<h1>{a.area} — fusion tier calibration</h1>
<p>{len(rows)} buildings with fused sources{'' if labels is None else f', {len(labels)} hand labels'}.</p>
<p><b>Current defaults</b>: decisive={base['decisive']} unsure={base['unsure']}
min_area={base['min_area']} → {base['review']} review ({base['review_pct']}%),
high precision {base['high_precision']}, damage recall in high {base['damage_recall_in_high']}.</p>
<p><b>Suggested</b>: decisive={best['decisive']} unsure={best['unsure']}
min_area={best['min_area']} → {best['review']} review ({best['review_pct']}%),
high precision {best['high_precision']}.</p>
<table><tr><th>decisive</th><th>unsure</th><th>min_area</th><th>review</th><th>review %</th>
<th>high precision</th><th>damage recall in high</th></tr>{rowhtml}</table>
"""
    out = os.path.join(OUT, f"{a.area}_calibration.html")
    with open(out, "w") as fh:
        fh.write(html)
    print(f"[calibrate] wrote {out}")

    if a.write:
        cfg = {
            "margin_decisive": best["decisive"],
            "margin_unsure": best["unsure"],
            "min_area": best["min_area"],
            "_from": a.area,
        }
        cpath = os.path.join(ROOT, "data", "calibration.json")
        with open(cpath, "w") as fh:
            json.dump(cfg, fh, indent=2)
        print(f"[calibrate] wrote {cpath} — fusion.py will use it next run")


if __name__ == "__main__":
    main()
