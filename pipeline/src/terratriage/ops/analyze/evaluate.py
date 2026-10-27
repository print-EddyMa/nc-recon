"""Honest accuracy: `run.py ops-eval` -> reports/ACCURACY_REPORT.md (+ .json).

Truth comes from `data/labels/*.csv` (see docs/ops/LABELING_PROTOCOL.md):

    ncr_id,label,labeler,protocol,imagery_date,notes

label is a FEMA class (no_damage, affected, minor, major, destroyed) or
`cannot_tell`. Rows with two labelers per building are adjudicated (the row
from labeler "adjudicated" wins; otherwise disagreement -> excluded and
counted) and Cohen's kappa between labelers is reported.

Metrics are computed per AOI role (TUNE vs TEST) and never pooled across
them. CIs are 95 % spatial-cluster bootstrap (250 m grid cells). If there are
no labels, the report says so and prints no accuracy numbers.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
from collections import defaultdict
from typing import Any

import numpy as np

from .. import DATA_DIR, OPS_OUT, PIPELINE_ROOT
from ..plan.events import event_for_area
from . import metrics
from .classes import FEMA, K

LABELS = os.environ.get("NCR_LABELS_DIR") or os.path.join(DATA_DIR, "labels")
REPORTS = os.environ.get("NCR_REPORTS_DIR") or os.path.join(PIPELINE_ROOT, "..", "reports")


def load_labels() -> tuple[dict[str, int], dict[str, Any]]:
    by_id: dict[str, dict[str, str]] = defaultdict(dict)
    for p in sorted(glob.glob(os.path.join(LABELS, "*.csv"))):
        with open(p, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                lab = (r.get("label") or "").strip().lower()
                if not r.get("ncr_id") or not lab:
                    continue
                by_id[r["ncr_id"]][(r.get("labeler") or "unknown").strip()] = lab
    truth: dict[str, int] = {}
    pairs: list[tuple[str, str]] = []
    disagreements = cannot = 0
    for nid, labs in by_id.items():
        if "adjudicated" in labs:
            lab = labs["adjudicated"]
        else:
            vals = list(labs.values())
            if len(vals) >= 2:
                pairs.append((vals[0], vals[1]))
            if len(set(vals)) > 1:
                disagreements += 1
                continue
            lab = vals[0]
        if lab == "cannot_tell":
            cannot += 1
            continue
        if lab in FEMA:
            truth[nid] = FEMA.index(lab)
    stats = {"labeled_buildings": len(by_id), "usable": len(truth),
             "unresolved_disagreements": disagreements, "cannot_tell": cannot,
             "double_labeled": len(pairs), "cohens_kappa": _kappa(pairs)}
    return truth, stats


def _kappa(pairs: list[tuple[str, str]]) -> float | None:
    cats = [*FEMA, "cannot_tell"]
    pairs = [(a, b) for a, b in pairs if a in cats and b in cats]
    if len(pairs) < 10:
        return None
    a = np.array([cats.index(x) for x, _ in pairs])
    b = np.array([cats.index(y) for _, y in pairs])
    po = float((a == b).mean())
    pe = float(sum((a == c).mean() * (b == c).mean() for c in range(len(cats))))
    return None if pe == 1 else (po - pe) / (1 - pe)


def _gather(truth: dict[str, int]) -> dict[str, dict[str, Any]]:
    """Per-role arrays of (y_true, y_pred, probs, lon, lat, needs_review, pset)."""
    out: dict[str, dict[str, list]] = {}
    for path in sorted(glob.glob(os.path.join(OPS_OUT, "*.geojson"))):
        area = os.path.basename(path)[:-8]
        if not re.fullmatch(r"[a-z0-9_]{1,40}", area):
            continue  # sidecars (<area>.<product>.geojson) are not assessments
        found = event_for_area(area)
        role = found[1].role if found else "UNREGISTERED"
        if role not in ("TUNE", "TEST"):
            continue  # operational areas are never evaluation data
        with open(path, encoding="utf-8") as fh:
            fc = json.load(fh)
        for f in fc["features"]:
            p = f["properties"]
            if p["ncr_id"] not in truth:
                continue
            d = out.setdefault(role, defaultdict(list))
            d["areas"].append(area)
            d["y"].append(truth[p["ncr_id"]])
            d["pred"].append(FEMA.index(p["damage_level"]))
            d["probs"].append([p["damage_probs"][c] for c in FEMA])
            d["lon"].append(p["centroid"][0])
            d["lat"].append(p["centroid"][1])
            d["review"].append(bool(p["needs_review"]))
            d["pset"].append(p.get("prediction_set"))
            e1 = next((e for e in p["evidence"] if e["id"] == "E1"), None)
            d["e1_label"].append((e1 or {}).get("detail", {}).get("xbd_label"))
    return out


def _with_ci(y, pred, probs, clusters) -> dict[str, Any]:
    y, pred, probs = np.asarray(y), np.asarray(pred), np.asarray(probs)
    s = metrics.summary(y, pred, K, probs)
    for name, fn in {
        "macro_f1": lambda i: metrics.macro_f1(metrics.confusion(y[i], pred[i], K)),
        "qwk": lambda i: metrics.quadratic_weighted_kappa(y[i], pred[i], K),
        "destroyed_recall": lambda i: metrics.recall_of(y[i], pred[i], K - 1),
        "ge_major_f1": lambda i: metrics.binary_f1(y[i], pred[i], lambda a: a >= K - 2),
        "ece": lambda i: metrics.ece(probs[i], y[i])[0],
    }.items():
        s[f"{name}_ci95"] = metrics.cluster_bootstrap(fn, clusters, n_boot=500)
    return s


def evaluate() -> dict[str, Any]:
    truth, lstats = load_labels()
    report: dict[str, Any] = {"labels": lstats, "roles": {}}
    if not truth:
        report["status"] = "NO_TRUTH"
        return report
    for role, d in _gather(truth).items():
        clusters = metrics.grid_clusters(d["lon"], d["lat"])
        y, pred, probs = np.array(d["y"]), np.array(d["pred"]), np.array(d["probs"])
        rev = np.array(d["review"])
        r: dict[str, Any] = {"areas": sorted(set(d["areas"])), "all": _with_ci(y, pred, probs, clusters)}
        acc = ~rev
        r["abstention_rate"] = float(rev.mean())
        r["accepted"] = metrics.summary(y[acc], pred[acc], K, probs[acc]) if acc.any() else None
        psets = [ps for ps in d["pset"] if ps is not None]
        if psets:
            cov = np.mean([FEMA[t] in ps for t, ps in zip(y, d["pset"]) if ps is not None])
            r["conformal_empirical_coverage"] = float(cov)
        report["roles"][role] = r
    report["status"] = "OK"
    return report


def _fmt(v, pct=False) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:.1f}%" if pct else f"{v:.3f}"


def _ci(ci) -> str:
    if not ci or ci[0] is None:
        return ""
    return f" [{ci[0]:.3f}, {ci[1]:.3f}]"


def write_report(rep: dict[str, Any]) -> str:
    os.makedirs(REPORTS, exist_ok=True)
    jpath = os.path.join(REPORTS, "ACCURACY_REPORT.json")
    with open(jpath, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, default=float)
    L = ["# Groma accuracy report", "",
         "Generated by `python scripts/run.py ops-eval`. Truth: human labels in "
         "`pipeline/data/labels/` following `docs/ops/LABELING_PROTOCOL.md`. "
         "Metrics are reported separately for TUNE areas (used to fit thresholds and "
         "calibration, so optimistic) and TEST areas (held out). 95 % CIs are "
         "spatial-cluster bootstrap over 250 m grid cells.", ""]
    ls = rep["labels"]
    L += ["## Labels", "", f"- buildings labeled: {ls['labeled_buildings']}",
          f"- usable (resolved, not `cannot_tell`): {ls['usable']}",
          f"- double-labeled: {ls['double_labeled']}; Cohen's kappa: {_fmt(ls['cohens_kappa'])}",
          f"- unresolved disagreements (excluded): {ls['unresolved_disagreements']}", ""]
    if rep["status"] == "NO_TRUTH":
        L += ["## Status: no ground truth yet", "",
              "There are no usable labels, so **no accuracy number is reported**. "
              "The model's outputs are unvalidated for this deployment. Public FEMA "
              "structure-level damage data does not cover Helene (the FEMA Historical "
              "Geospatial Damage Assessment Database ends with 2020 events; checked "
              "2026-09-26). Label TUNE and TEST buildings per the protocol, then re-run.", ""]
    for role, r in rep["roles"].items():
        a = r["all"]
        L += [f"## {role} areas: {', '.join(r['areas'])}", "",
              f"n = {a['n']} labeled buildings", "",
              "| metric | value [95% CI] |", "|---|---|",
              f"| accuracy | {_fmt(a['accuracy'])} |",
              f"| macro-F1 | {_fmt(a['macro_f1'])}{_ci(a.get('macro_f1_ci95'))} |",
              f"| quadratic weighted kappa | {_fmt(a['qwk'])}{_ci(a.get('qwk_ci95'))} |",
              f"| Destroyed recall | {_fmt(a['destroyed_recall'])}{_ci(a.get('destroyed_recall_ci95'))} |",
              f"| >= Major F1 | {_fmt(a['ge_major_f1'])}{_ci(a.get('ge_major_f1_ci95'))} |",
              f"| ECE (top-class) | {_fmt(a.get('ece'))}{_ci(a.get('ece_ci95'))} |",
              f"| abstention (needs_review) rate | {_fmt(r['abstention_rate'], True)} |",
              f"| accuracy on accepted (not review) | {_fmt((r['accepted'] or {}).get('accuracy'))} |",
              f"| conformal empirical coverage | {_fmt(r.get('conformal_empirical_coverage'))} |", "",
              "Per class:", "", "| class | precision | recall | F1 | support |", "|---|---|---|---|---|"]
        for c, pc in zip(FEMA, a["per_class"]):
            L.append(f"| {c} | {_fmt(pc['precision'])} | {_fmt(pc['recall'])} | {_fmt(pc['f1'])} | {pc['support']} |")
        L += ["", "Confusion (rows = truth, cols = predicted):", "", "| | " + " | ".join(FEMA) + " |",
              "|---" * (K + 1) + "|"]
        for c, row in zip(FEMA, a["confusion"]):
            L.append(f"| **{c}** | " + " | ".join(str(v) for v in row) + " |")
        L.append("")
    path = os.path.join(REPORTS, "ACCURACY_REPORT.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return path


def calibrate() -> dict[str, Any]:
    """Fit CNN temperature, fusion temperature and conformal qhat on TUNE labels."""
    from . import calibration
    from .fusion import pool

    truth, _ = load_labels()
    rows = []
    for path in sorted(glob.glob(os.path.join(OPS_OUT, "*.geojson"))):
        area = os.path.basename(path)[:-8]
        if not re.fullmatch(r"[a-z0-9_]{1,40}", area):
            continue  # sidecars (<area>.<product>.geojson) are not assessments
        found = event_for_area(area)
        if not found or found[1].role != "TUNE":
            continue  # never fit on TEST
        with open(path, encoding="utf-8") as fh:
            for f in json.load(fh)["features"]:
                p = f["properties"]
                if p["ncr_id"] in truth:
                    rows.append((area, p, truth[p["ncr_id"]]))
    if len(rows) < 20:
        raise SystemExit(f"only {len(rows)} TUNE labels; need >= 20 to calibrate")
    out: dict[str, Any] = {"n": len(rows), "areas": sorted({r[0] for r in rows})}
    # CNN temperature needs xBD-space targets: use the xBD label whose FEMA
    # crosswalk row gives the truth class the most mass
    from .classes import xbd_to_fema_matrix

    W = xbd_to_fema_matrix()
    lg, yx = [], []
    for _, p, y in rows:
        e1 = next((e for e in p["evidence"] if e["id"] == "E1" and e.get("available")), None)
        if e1 and "logits" in e1.get("detail", {}):
            lg.append(e1["detail"]["logits"])
            yx.append(int(np.argmax(W[:, y])))
    if len(lg) >= 20:
        T = calibration.fit_temperature(np.array(lg), np.array(yx), ["TUNE"] * len(lg))
        calibration.save("xview2_cmu_baseline", {"temperature": T, "n": len(lg), "areas": out["areas"]})
        out["cnn_temperature"] = T
    # fusion temperature + conformal on the pooled log-probabilities
    logp = np.log(np.clip(np.array([[p["damage_probs"][c] for c in FEMA] for _, p, _ in rows]), 1e-9, 1))
    y = np.array([r[2] for r in rows])
    Tf = calibration.fit_temperature(logp, y, ["TUNE"] * len(y))
    probs = calibration.softmax(logp, Tf)
    q = calibration.conformal_quantile(calibration.aps_scores(probs, y), alpha=0.10)
    calibration.save("fusion_v1", {"temperature": Tf, "conformal_qhat": q, "alpha": 0.10,
                                   "n": len(y), "areas": out["areas"]})
    out.update(fusion_temperature=Tf, conformal_qhat=q)
    _ = pool
    return out
