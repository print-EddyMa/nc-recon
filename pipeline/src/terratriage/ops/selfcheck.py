"""Self-checks: every assessment checks itself and says how much margin it has.

    report = run_checks("swannanoa")          # dict, JSON-safe

Ported from Margin's verification vocabulary (simulate_anything/checks.py and
create_anything/scenarios.py, MIT, same author):

* A check is one question the assessment asks of its own outputs. Its status
  is pass, warn, fail or skip. A check is never dropped: when it cannot be
  answered it is recorded as skip with the reason, so the report always shows
  what was and was not checked.
* A skip is either not applicable (by design: a TEST area is held out, no
  response products were built) or a gap (something that should be checked
  could not be, such as "not yet validated for this hazard").
* Verdict: "failed" if any check failed; "passed_with_warnings" if any warned
  or any skip is a gap; otherwise "verified".
* Load is the share of a limit used: a maximum is (value - base) / (limit -
  base), a minimum requirement is required / actual. Margin = 1 / load - 1:
  +0.25 is 25% to spare, 0 is exactly at the limit, negative is over it.
* Every limit names where it comes from (`source`). Where no threshold is
  stated anywhere in the code, config or docs, the check reports the value
  with status warn and source "no stated threshold yet"; it never invents one.
* Where it can, a check computes its quantity by a second route from the one
  that produced it (totals recounted from the buildings, the image model
  against the change signal), which is Margin's main rule.

Checks read only what an assessment already wrote to OPS_OUT:
<area>.geojson, and where present <area>.response.json, .impact.json,
.responder.json, .ground_change.json, .sarcop_reference.json and
.field_reference.json, plus the label CSV for the same area. They never open
imagery or per-building chips.

Hold-out rule: for a TEST area every check that would read labels, truth or
reference comparisons returns skip, "TEST area: held out", before any of
those files is opened.

Checks label an assessment. They never block an export.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import CONFIG_DIR, DATA_DIR, OPS_OUT, PIPELINE_ROOT
from .provenance import utc_now

SCHEMA = "ncr-selfcheck-1"
PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"
VERIFIED, WITH_WARNINGS, FAILED = "verified", "passed_with_warnings", "failed"
MAX_LOAD = 99.0           # cap so a load is always a finite JSON number
NO_THRESHOLD = "no stated threshold yet"
HELD_OUT = "TEST area: held out"
LEVELS = ("no_damage", "affected", "minor", "major", "destroyed")
SEVERE = frozenset({"major", "destroyed"})
_AREA = re.compile(r"[a-z0-9_]{1,40}")    # same rule as api._area

# The TEST areas as registered in config/events.yaml (docs/ops/PHASE_J_STATUS.md,
# "Hold-out hygiene"). The registry is the authority; this set only keeps the
# hold-out when the registry cannot be read. A role of TEST from either wins.
TEST_AREAS = frozenset({"chimney_rock", "canton", "burnsville", "marshall", "altadena"})

# Released model hashes, as published in pipeline/weights/README.md (the ONNX
# one is also ONNX_SHA256 in ops/pipeline.py).
RELEASED_WEIGHTS = {
    "xview2_cmu_classifier.onnx": "711fbdd47d99c4e1d5e7d6a84ec5c8d1c8a5eaeb84ea90d1969e10cd02fdb18f",
    "classification.hdf5": "a1f0dff601c8f3582b686ac7ce695f116d339e7913d1928d9ff62ab740e703cd",
}
WEIGHTS_README = os.path.join(PIPELINE_ROOT, "weights", "README.md")

# Landing-zone planning defaults, used only when a response file predates
# recording them (response/landing.py PARAMS).
_LZ_DEFAULTS = {"min_diameter_m": 50.0, "ch47_diameter_m": 80.0, "max_slope_deg": 7.0}
LZ_SOURCE = ("response/landing.py PARAMS: single-ship landing point 50 m cleared diameter for a "
             "UH-60, 80 m for a CH-47, up to 7 degrees of slope (Army air assault handbook citing "
             "FM 3-21.38); planning defaults, the aviation unit's own standard governs")


# --------------------------------------------------------------------------- #
# margin math (Margin: create_anything/scenarios.py load_of / margin_of)
# --------------------------------------------------------------------------- #
def load_of(value: float | None, limit: float | None, kind: str, base: float = 0.0) -> float | None:
    """Share of the allowance a result uses: 1 is exactly at the limit, 0.5 half
    of it, 2 twice over. A maximum is measured from `base`; a minimum (a
    required size) is required / actual. None when it has no meaning."""
    if value is None or limit is None:
        return None
    try:
        value, limit, base = float(value), float(limit), float(base)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (value, limit, base)):
        return None
    if kind == "min":
        if value <= 0 or limit <= 0:
            return None
        out = limit / value
    elif kind == "max":
        span = limit - base
        if span <= 0:
            return None
        out = max(0.0, (value - base) / span)
    else:
        return None
    return float(min(out, MAX_LOAD))


def margin_of(load: float | None) -> float | None:
    """Margin of safety from a load: allowable / actual - 1."""
    if load is None:
        return None
    return MAX_LOAD if load <= 1.0 / (MAX_LOAD + 1) else float(1.0 / load - 1.0)


def metric(label: str, value: float | None, limit: float | None, kind: str, unit: str = "",
           base: float = 0.0, slack: float = 0.0, source: str = "") -> dict[str, Any]:
    """One measured quantity against one limit. `slack` absorbs stored rounding."""
    ok = None
    if value is not None and limit is not None:
        ok = (value + slack >= limit) if kind == "min" else (value - slack <= limit)
    load = load_of(value, limit, kind, base)
    out = {"label": label, "value": _num(value), "limit": _num(limit), "unit": unit, "kind": kind,
           "base": _num(base), "ok": ok, "load": load, "margin": margin_of(load)}
    if source:
        out["source"] = source
    return out


def _num(v: Any) -> float | int | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return int(f) if float(f).is_integer() and abs(f) < 2 ** 53 and isinstance(v, int) else f


def spare(load: float | None) -> str:
    """Plain words for a margin: '15% to spare', 'at the limit', '4.7 times the limit'."""
    m = margin_of(load)
    if m is None:
        return "no margin can be computed"
    if load is not None and load > 1:
        return f"{load:.1f} times the limit" if load >= 2 else f"over the limit by {round((load - 1) * 100)}%"
    if m > 3:
        return "more than 300% to spare"
    p = round(m * 100)
    return "at the limit" if p == 0 else f"{p}% to spare"


def _n(v: float | int) -> str:
    return f"{v:,}" if isinstance(v, int) else f"{v:,.2f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- #
# vocabulary
# --------------------------------------------------------------------------- #
@dataclass
class Check:
    id: str
    title: str
    category: str
    status: str
    finding: str
    source: str = ""
    value: float | None = None
    limit: float | None = None
    unit: str = ""
    kind: str | None = None          # "max" | "min" | None (identity or unthresholded)
    base: float = 0.0
    load: float | None = None
    reason: str | None = None        # skip only
    not_applicable: bool = False     # skip only: True = by design, False = a gap
    metrics: list[dict[str, Any]] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    note: str = ""                   # caveats that qualify the one-line finding

    def to_dict(self) -> dict[str, Any]:
        load = self.load
        if load is None and self.status in (PASS, FAIL, WARN) and self.kind in ("max", "min"):
            load = load_of(self.value, self.limit, self.kind, self.base)
        d = {"id": self.id, "title": self.title, "category": self.category, "status": self.status,
             "finding": self.finding, "source": self.source, "value": _num(self.value),
             "limit": _num(self.limit), "unit": self.unit, "kind": self.kind, "base": _num(self.base),
             "load": load, "margin": margin_of(load), "note": self.note, "metrics": self.metrics,
             "detail": self.detail}
        if self.status == SKIP:
            d["reason"] = self.reason or "not stated"
            d["not_applicable"] = bool(self.not_applicable)
        return d


def skip(cid: str, title: str, category: str, reason: str, *, not_applicable: bool,
         source: str = "") -> Check:
    return Check(cid, title, category, SKIP, f"Not checked: {reason}.", source=source, reason=reason,
                 not_applicable=not_applicable)


def verdict_of(checks: list[dict[str, Any]]) -> str:
    st = [c["status"] for c in checks]
    if FAIL in st:
        return FAILED
    if WARN in st or any(c["status"] == SKIP and not c.get("not_applicable") for c in checks):
        return WITH_WARNINGS
    return VERIFIED


_VERDICT_WORDS = {VERIFIED: "Verified", WITH_WARNINGS: "Passed with warnings", FAILED: "Failed"}


def summarise(area: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {s: sum(c["status"] == s for c in checks) for s in (PASS, WARN, FAIL, SKIP)}
    gaps = sum(c["status"] == SKIP and not c.get("not_applicable") for c in checks)
    v = verdict_of(checks)
    loaded = [c for c in checks if c.get("load") is not None and c["status"] != SKIP]
    worst = max(loaded, key=lambda c: c["load"]) if loaded else None
    text = (f"{_VERDICT_WORDS[v]}: {counts[PASS]} passed, {counts[WARN]} with warnings, "
            f"{counts[FAIL]} failed, {counts[SKIP]} not checked")
    if gaps:
        text += f" ({gaps} of them gaps)"
    return {"verdict": v, "summary": text, "counts": counts | {"gaps": gaps},
            "limiting": None if worst is None else
            {"id": worst["id"], "title": worst["title"], "load": worst["load"], "margin": worst["margin"]}}


# --------------------------------------------------------------------------- #
# reading what the assessment wrote
# --------------------------------------------------------------------------- #
def _read_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _read_yaml(path: str) -> dict[str, Any]:
    try:
        import yaml

        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except (OSError, ImportError, ValueError):
        return {}
    except Exception:  # noqa: BLE001 - yaml.YAMLError and friends: treat as unreadable
        return {}


def _rules() -> dict[str, Any]:
    return _read_yaml(os.path.join(CONFIG_DIR, "context_rules.yaml"))


def registry_role(area: str) -> str | None:
    """Role from config/events.yaml (TUNE/TEST) or the operational registry (OPS),
    read straight from the YAML files: no network (building Event objects
    fetches OpenFEMA declarations)."""
    try:
        from .plan.events import _config_path, registry_path
    except Exception:  # noqa: BLE001
        return None
    cfg = _read_yaml(_config_path())
    for spec in (cfg.get("events") or {}).values():
        a = ((spec or {}).get("aois") or {}).get(area)
        if a:
            return str(a.get("role", "")).upper() or None
    if area in (_read_yaml(registry_path()).get("aois") or {}):
        return "OPS"
    return None


def area_role(area: str, props: dict[str, Any]) -> str:
    """TEST if the registry, the run's own record or the hold-out list says so."""
    reg = registry_role(area)
    own = str(((props.get("aoi") or {}).get("role")) or "").upper() or None
    if "TEST" in (reg, own) or area in TEST_AREAS:
        return "TEST"
    return reg or own or "UNREGISTERED"


def _ev(p: dict[str, Any], cid: str) -> dict[str, Any] | None:
    for e in p.get("evidence") or []:
        if e.get("id") == cid:
            return e
    return None


def _favoured_level(e: dict[str, Any] | None) -> str | None:
    """The level an available channel's stored likelihood favours."""
    if not e or not e.get("available"):
        return None
    lk = e.get("likelihood")
    if not isinstance(lk, list) or len(lk) != len(LEVELS):
        return None
    try:
        vals = [float(v) for v in lk]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in vals) or max(vals) <= 0:
        return None
    return LEVELS[max(range(len(vals)), key=lambda i: vals[i])]


def _parse_date(s: Any) -> date | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# the checks
# --------------------------------------------------------------------------- #
CAT_EVERY, CAT_IMAGERY, CAT_ROUTE, CAT_MODEL, CAT_VALID, CAT_RESPONSE = (
    "every assessment", "imagery", "second route", "model", "validation", "response products")


def check_conserved(props, feats) -> Check:
    t = "Every building is accounted for"
    counts = props.get("counts") or {}
    na = (props.get("not_assessed") or {}).get("total")
    n = props.get("n_structures")
    if not counts or na is None or n is None:
        return skip("buildings_conserved", t, CAT_EVERY, "the run did not record counts, not_assessed "
                    "and n_structures", not_applicable=False)
    assessed = int(sum(int(v) for v in counts.values()))
    feat_na = sum(1 for f in feats if not (f.get("properties") or {}).get("damage_level"))
    ok = assessed + int(na) == int(n) == len(feats) and feat_na == int(na)
    if ok:
        msg = (f"{_n(assessed)} assessed plus {_n(int(na))} not assessed makes {_n(int(n))}, every "
               f"structure in the area, and the map holds the same {_n(len(feats))}.")
    else:
        msg = (f"{_n(assessed)} assessed plus {_n(int(na))} not assessed makes {_n(assessed + int(na))}, "
               f"but the area has {_n(int(n))} structures and the map holds {_n(len(feats))} "
               f"({_n(feat_na)} of them without a call). Some buildings are missing or counted twice.")
    return Check("buildings_conserved", t, CAT_EVERY, PASS if ok else FAIL, msg,
                 source="identity: each structure is either assessed or listed as not assessed "
                        "(counts, not_assessed and n_structures in ops/pipeline.py)",
                 value=assessed + int(na), limit=int(n), unit="structures",
                 detail={"assessed": assessed, "not_assessed": int(na), "n_structures": int(n),
                         "features": len(feats), "features_without_call": feat_na})


def check_totals(props, feats) -> Check:
    t = "Headline totals match the buildings"
    counts = props.get("counts") or {}
    exp = props.get("expected_counts") or {}
    n_rev = props.get("n_needs_review")
    assessed = [f.get("properties") or {} for f in feats if (f.get("properties") or {}).get("damage_level")]
    if not counts:
        return skip("totals_recomputed", t, CAT_ROUTE, "the run did not record counts", not_applicable=False)
    recount = Counter(p["damage_level"] for p in assessed)
    count_bad = [c for c in LEVELS if int(counts.get(c, 0)) != recount.get(c, 0)]
    rev = sum(1 for p in assessed if p.get("needs_review"))
    rev_bad = n_rev is not None and int(n_rev) != rev
    metrics_: list[dict[str, Any]] = []
    worst_diff, tol = None, None
    prob_err = 0.0
    if exp:
        sums = {c: 0.0 for c in LEVELS}
        for p in assessed:
            pr = p.get("damage_probs") or {}
            s = 0.0
            for c in LEVELS:
                v = float(pr.get(c) or 0.0)
                sums[c] += v
                s += v
            prob_err = max(prob_err, abs(s - 1.0))
        # expected counts are rounded to 0.1; each probability to 4 decimals
        tol = 0.05 + 0.00005 * len(assessed)
        worst_diff = max(abs(sums[c] - float(exp.get(c, 0.0))) for c in LEVELS)
        metrics_.append(metric("expected counts recomputed from building probabilities", round(worst_diff, 4),
                               round(tol, 4), "max", "buildings",
                               source="rounding in ops/analyze/fusion.py (4 decimals) and ops/pipeline.py (0.1)"))
        metrics_.append(metric("largest gap between a building's probabilities and 1", round(prob_err, 6),
                               0.00025, "max", "",
                               source="five probabilities each rounded to 4 decimals (ops/analyze/fusion.py)"))
    over = [m for m in metrics_ if m["ok"] is False]
    ok = not count_bad and not rev_bad and not over
    parts = []
    parts.append("The class counts match a recount of the buildings" if not count_bad else
                 "The class counts do not match a recount of the buildings (" +
                 ", ".join(f"{c.replace('_', ' ')} {counts.get(c, 0)} recorded, {recount.get(c, 0)} counted"
                           for c in count_bad) + ")")
    if n_rev is not None:
        parts.append(f"the review count matches ({_n(rev)})" if not rev_bad else
                     f"the review count says {_n(int(n_rev))} but {_n(rev)} assessed buildings are flagged")
    if worst_diff is not None:
        parts.append(f"expected counts match the summed probabilities within {worst_diff:.2f} "
                     f"(rounding allows {tol:.2f})" if worst_diff <= tol else
                     f"expected counts are off the summed probabilities by {worst_diff:.2f} "
                     f"(rounding allows {tol:.2f})")
    msg = "; ".join(parts) + "."
    return Check("totals_recomputed", t, CAT_ROUTE, PASS if ok else FAIL, msg,
                 source="identity, recomputed from the buildings; tolerance from stored rounding",
                 value=None if worst_diff is None else round(worst_diff, 4),
                 limit=None if tol is None else round(tol, 4), unit="buildings",
                 kind="max" if worst_diff is not None else None, metrics=metrics_,
                 detail={"count_mismatch": count_bad, "review_recount": rev, "n_needs_review": n_rev})


def check_dates(props, feats) -> Check:
    t = "Post-event imagery postdates the event"
    src = ("ops/plan/events.py check_image_pair: the pre image must predate the incident begin "
           "and the post image must not")
    pc = props.get("pair_context") or {}
    begin = _parse_date((props.get("event") or {}).get("incident_begin"))
    pd = pc.get("post_days_after_incident")
    lo = hi = None
    if isinstance(pd, (int, float)):
        lo = hi = float(pd)
    elif isinstance(pd, list) and pd and all(isinstance(v, (int, float)) for v in pd):
        lo, hi = float(min(pd)), float(max(pd))
    # second route: the image date written on each building's FEMA record
    fema_days = None
    if begin:
        for f in feats:
            fm = (f.get("properties") or {}).get("fema") or {}
            d = _parse_date(fm.get("IMG_DATE")) or _parse_date(str(fm.get("IMG_DATE_RANGE") or "").split("..")[0])
            if d:
                fema_days = (d - begin).days
                break
    if lo is None and fema_days is not None:
        lo = hi = float(fema_days)
    if lo is None:
        return skip("imagery_dates", t, CAT_IMAGERY, "the run did not record when the post image was taken",
                    not_applicable=False, source=src)
    gap = pc.get("pair_gap_days")
    pre_before = (float(gap) - lo) if isinstance(gap, (int, float)) else None
    agree = fema_days is None or abs(fema_days - lo) <= 1
    ok = lo >= 0 and (pre_before is None or pre_before > 0) and agree
    when = (f"{_n(int(lo))} days" if lo == hi else f"{_n(int(lo))} to {_n(int(hi))} days")
    msg = f"The post-event image was taken {when} after the event start"
    msg += f" ({begin.isoformat()})" if begin else ""
    if lo < 0:
        msg = f"The post-event image starts {_n(int(-lo))} days before the event start; it cannot show this damage"
    if pre_before is not None:
        msg += (f"; the pre-event image ends at least {_n(int(pre_before))} days before it" if pre_before > 0
                else "; the pre-event image does not predate the event")
    if not agree:
        msg += (f". The buildings' FEMA records give {fema_days} days instead, so the two records disagree")
    elif fema_days is not None:
        msg += ", and the buildings' FEMA records agree"
    return Check("imagery_dates", t, CAT_IMAGERY, PASS if ok else FAIL, msg + ".", source=src,
                 value=lo, limit=0, unit="days after the event start", kind="min",
                 detail={"post_days_after_incident": pd, "pre_days_before_incident_min": pre_before,
                         "fema_record_days": fema_days})


def check_geometry(props, rules) -> Check:
    t = "Before and after views match"
    lim = rules.get("geometry_limit_deg")
    src = "config/context_rules.yaml geometry_limit_deg (off-nadir or sun-elevation difference)"
    if lim is None:
        lim, src = 15.0, "ops/process/imagery.py pair_context default geometry_limit_deg"
    pc = props.get("pair_context") or {}
    dn, ds = pc.get("off_nadir_diff_deg"), pc.get("sun_elev_diff_deg")
    if dn is None and ds is None:
        aerial = "AERIAL_ORTHO_GEOMETRY_UNRECORDED" in (pc.get("reasons") or [])
        why = ("view and sun angles are not published for these aerial orthomosaics" if aerial
               else "the run did not record view and sun angles")
        return skip("pair_geometry", t, CAT_IMAGERY, why, not_applicable=False, source=src)
    ms = [metric("off-nadir angle difference", dn, lim, "max", "degrees", source=src),
          metric("sun elevation difference", ds, lim, "max", "degrees", source=src)]
    ms = [m for m in ms if m["value"] is not None]
    worst = max(ms, key=lambda m: m["load"] or 0)
    over = [m for m in ms if m["ok"] is False]
    w = pc.get("e2_geometry_weight")
    msg = " and ".join(f"{m['label'].replace(' difference', '')}s differ by {float(m['value']):.1f} degrees"
                       for m in ms).capitalize()
    note = ""
    if over:
        msg += f", over the {lim:g} degree limit"
        note = ("The change signal was weighted down" + (f" to {float(w):g}" if w is not None else "")
                + " for it, as the pipeline does for any pair over the limit.")
    else:
        msg += f", within the {lim:g} degree limit ({spare(worst['load'])})"
    return Check("pair_geometry", t, CAT_IMAGERY, WARN if over else PASS, msg + ".", source=src, note=note,
                 value=worst["value"], limit=lim, unit="degrees", kind="max", metrics=ms,
                 detail={"e2_geometry_weight": w})


def check_coreg(props, feats) -> Check:
    t = "After image lines up with the before image"
    src = ("ops/process/coreg.py and config/context_rules.yaml coreg_residual_max_px: a residual over "
           "1 px switches the change signal (E2) off (enforced in ops/pipeline.py from rules 2026-11-15.1)")
    cr = props.get("coregistration") or {}
    r = cr.get("residual_px")
    if r is None:
        return skip("coregistration", t, CAT_IMAGERY, "the run did not record a co-registration residual",
                    not_applicable=False, source=src)
    lim = 1.0
    load = load_of(r, lim, "max")
    e2_on = sum(1 for f in feats if (_ev(f.get("properties") or {}, "E2") or {}).get("available"))
    nwin = cr.get("n_windows")
    win = f" over {nwin} windows" if nwin else ""
    if float(r) <= lim:
        msg = f"Residual misalignment after the global shift is {float(r):.2f} px{win}, within 1 px ({spare(load)})."
        note = ""
        st = PASS
    elif e2_on == 0:
        # the pipeline did the documented thing: E2 is off, the image model carries the calls
        msg = (f"Residual misalignment after the global shift is {float(r):.2f} px{win}, over 1 px, "
               "so the change signal (E2) was switched off: these calls rest on the image model only.")
        note = "A better-matched pair of images would bring the change signal back."
        st = WARN
    else:
        msg = (f"Residual misalignment after the global shift is {float(r):.2f} px{win}, "
               f"{spare(load)} of 1 px: one shift does not line the images up.")
        note = (f"The change signal (E2) was still used for {_n(e2_on)} buildings, so treat its calls here with care. "
                "Runs since 2026-11-15 switch it off; reassess this area to apply that.")
        st = FAIL
    return Check("coregistration", t, CAT_IMAGERY, st, msg, source=src, note=note, value=float(r), limit=lim,
                 unit="px",
                 kind="max", detail={"shift_px": cr.get("shift_px"), "n_windows": nwin,
                                     "e2_available": e2_on})


def check_alignment(props, feats) -> Check:
    t = "Footprints line up with the imagery"
    src = ("ops/process/align.py consensus: offsets are searched within +-15 m (R=15.0) and need "
           "at least 10 footprints, else no offset is applied; peak strength has no stated threshold")
    fa = props.get("footprint_alignment") or {}
    if not fa:
        return skip("footprint_alignment", t, CAT_IMAGERY, "the run did not record footprint alignment",
                    not_applicable=False, source=src)
    ms, notes, warn = [], [], False
    for key, o in sorted(fa.items()):
        if not isinstance(o, dict):
            continue
        off = max(abs(float(o.get("dx_m") or 0)), abs(float(o.get("dy_m") or 0)))
        n = int(o.get("n") or 0)
        name = key.replace("usa_structures", "USA Structures").replace("osm", "OSM").replace(":", ", ")
        m_off = metric(f"{name}: offset", round(off, 2), 15.0, "max", "m")
        m_n = metric(f"{name}: footprints sampled", n, 10, "min", "footprints")
        ms += [m_off, m_n]
        if n < 10:
            warn = True
            notes.append(f"{name} had {n} footprints, too few to fit an offset, so none was applied")
        elif off >= 15.0:
            warn = True
            notes.append(f"{name} offset sits on the edge of the search window, so the true offset may be larger")
    assessed = [f.get("properties") or {} for f in feats if (f.get("properties") or {}).get("damage_level")]
    weak = sum(1 for p in assessed if "FOOTPRINT_ALIGNMENT_WEAK" in (p.get("reason_codes") or [])
               or "FOOTPRINT_ALIGNMENT_WEAK" in (p.get("review_reasons") or []))
    loads = [m["load"] for m in ms if m["load"] is not None]
    worst = max(loads) if loads else None
    pz = [float(o.get("peak_z")) for o in fa.values() if isinstance(o, dict) and o.get("peak_z") is not None]
    offs = [m for m in ms if m["unit"] == "m"]
    big = max(offs, key=lambda m: m["value"] or 0) if offs else None
    msg = (f"{len(fa)} footprint offsets fitted; the largest, {big['value']:g} m, is inside the 15 m "
           f"search window ({spare(big['load'])})." if big and not warn else "; ".join(notes).capitalize() + ".")
    note = []
    if pz:
        note.append(f"Peak strength ranges {min(pz):.1f} to {max(pz):.1f} ({NO_THRESHOLD}).")
    if assessed:
        note.append(f"{_n(weak)} of {_n(len(assessed))} assessed buildings never found crisp roof edges.")
    lim_m = max(ms, key=lambda m: m["load"] or 0) if loads else None
    return Check("footprint_alignment", t, CAT_IMAGERY, WARN if warn else PASS, msg, source=src,
                 note=" ".join(note),
                 value=None if lim_m is None else lim_m["value"], limit=None if lim_m is None else lim_m["limit"],
                 unit="" if lim_m is None else lim_m["unit"], kind=None if lim_m is None else lim_m["kind"],
                 load=worst, metrics=ms,
                 detail={"weak_buildings": weak, "assessed": len(assessed)})


def check_independent(props, feats) -> Check:
    t = "Image model and change signal agree on severe damage"
    src = (f"{NO_THRESHOLD}. Severe means the level a channel's stored likelihood favours is Major or "
           "Destroyed (config/crosswalks.yaml for the image model, config/context_rules.yaml E2 rows "
           "for the change signal, where that is a z-score of 3.5 or more)")
    both = a_sev = b_sev = both_sev = agree = raised = 0
    model = None
    for f in feats:
        p = f.get("properties") or {}
        if not p.get("damage_level"):
            continue
        m1 = _ev(p, "M1")
        img = m1 if (m1 or {}).get("available") else _ev(p, "E1")
        la, lb = _favoured_level(img), _favoured_level(_ev(p, "E2"))
        if la is None or lb is None:
            continue
        model = model or img.get("id")
        both += 1
        sa, sb = la in SEVERE, lb in SEVERE
        if sa:
            raised += lb != "no_damage"
        a_sev += sa
        b_sev += sb
        both_sev += sa and sb
        agree += sa == sb
    if not both:
        return skip("independent_route", t, CAT_ROUTE, "no building had both the image model and the "
                    "change signal available", not_applicable=False, source=src)
    name = "the NC Recon damage model (M1)" if model == "M1" else "the image model (E1)"
    raw = agree / both
    pe = (a_sev * b_sev + (both - a_sev) * (both - b_sev)) / (both * both)
    kappa = None if pe >= 1 else round((raw - pe) / (1 - pe), 4) + 0.0
    either = a_sev + b_sev - both_sev
    pos = both_sev / either if either else None
    if pos is None:
        msg = (f"Of {_n(both)} buildings read by both, neither {name} nor the change signal (E2) calls any "
               f"severe, so they agree on all of them.")
    else:
        msg = (f"Of {_n(both)} buildings read by both, {name} calls {_n(a_sev)} severe and the change signal "
               f"(E2) {_n(b_sev)}; they agree on {_n(both_sev)}, {round(100 * pos)}% of the buildings either "
               f"calls severe (kappa {abs(kappa) if abs(kappa) < 0.005 else kappa:.2f}, overall agreement "
               f"{round(100 * raw)}%).")
    note = ""
    if a_sev:
        note = (f"Where the image model calls severe, the change signal favours a level above no damage "
                f"for {_n(raised)} of {_n(a_sev)}. ")
    note += ("The change signal favours Major or Destroyed only at a z-score of 3.5 or more, so it rarely "
             "calls severe. Both read the same post image, so this is a second route, not a fully "
             "independent one.")
    return Check("independent_route", t, CAT_ROUTE, WARN, msg, source=src, note=note,
                 value=None if pos is None else round(pos, 4), unit="share of severe calls shared",
                 detail={"image_channel": model, "both_available": both, "image_severe": a_sev,
                         "change_severe": b_sev, "both_severe": both_sev,
                         "change_raised_where_image_severe": raised,
                         "overall_agreement": round(raw, 4),
                         "kappa": kappa})


def check_review(props, feats, rules) -> Check:
    t = "Share of calls needing human review"
    counts = props.get("counts") or {}
    assessed = int(sum(int(v) for v in counts.values())) if counts else 0
    n_rev = props.get("n_needs_review")
    if n_rev is None:
        n_rev = sum(1 for f in feats if (f.get("properties") or {}).get("damage_level")
                    and (f.get("properties") or {}).get("needs_review"))
    if not assessed:
        return skip("review_share", t, CAT_EVERY, "no building was assessed", not_applicable=False,
                    source=NO_THRESHOLD)
    share = int(n_rev) / assessed
    msg = f"{_n(int(n_rev))} of {_n(assessed)} assessed buildings ({round(100 * share)}%) need a person to check them."
    abst = ((rules.get("fusion") or {}).get("abstain") or {})
    note = ("Until probabilities are calibrated, every Major or Destroyed call goes to review."
            if abst.get("review_severe_until_calibrated") else "")
    return Check("review_share", t, CAT_EVERY, WARN, msg, note=note,
                 source=f"{NO_THRESHOLD} (no review ceiling is set in config or docs)",
                 value=round(share, 4), unit="share of assessed buildings",
                 detail={"n_needs_review": int(n_rev), "assessed": assessed})


def _readme_has(h: str) -> bool | None:
    try:
        with open(WEIGHTS_README, encoding="utf-8") as fh:
            return h in fh.read()
    except OSError:
        return None


def check_weights(props, feats) -> Check:
    t = "Image model weights match the release"
    src = "pipeline/weights/README.md (released SHA-256 of each weights file); ONNX_SHA256 in ops/pipeline.py"
    m = (props.get("provenance") or {}).get("model") or {}
    e1 = [_ev(f.get("properties") or {}, "E1") or {} for f in feats if (f.get("properties") or {}).get("damage_level")]
    e1_ran = any(e.get("available") for e in e1)
    replaced = any(e.get("unavailable_reason") == "REPLACED_BY_M1" for e in e1)
    applied = ((props.get("provenance") or {}).get("hazards") or {}).get("channels_applied")
    if isinstance(applied, list) and "E1" not in applied:
        return skip("model_weights", t, CAT_MODEL, "the image model does not apply to this hazard",
                    not_applicable=True, source=src)
    if not e1_ran and not replaced:
        why = Counter(e.get("unavailable_reason") for e in e1 if e.get("unavailable_reason")).most_common(1)
        return skip("model_weights", t, CAT_MODEL, "the image model did not run"
                    + (f" ({why[0][0]})" if why else ""), not_applicable=False, source=src)
    if not m:
        return skip("model_weights", t, CAT_MODEL, "the run did not record which model weights it used",
                    not_applicable=False, source=src)
    fname = os.path.basename(str(m.get("file") or m.get("weights") or ""))
    got = str(m.get("sha256") or "").lower()
    want = RELEASED_WEIGHTS.get(fname)
    detail = {"file": fname, "recorded_sha256": got or None, "released_sha256": want}
    if want is None:
        return Check("model_weights", t, CAT_MODEL, WARN,
                     f"The run used {fname or 'an unnamed file'}, which has no released hash to compare with.",
                     source=src, detail=detail)
    in_readme = _readme_has(want)
    ok = got == want and in_readme is not False
    if ok:
        msg = f"The hash the run recorded for {fname} ({got[:12]}...) matches the released one."
    elif got != want:
        msg = (f"The run recorded {got[:12] or 'no hash'}... for {fname}, but the release is {want[:12]}...: "
               f"these are not the released weights.")
    else:
        msg = f"The released hash for {fname} is no longer in pipeline/weights/README.md; the record cannot be confirmed."
    return Check("model_weights", t, CAT_MODEL, PASS if ok else FAIL, msg, source=src, detail=detail,
                 note="This compares the hash the run recorded; it does not re-hash the weights file.")


def check_weights_m1(feats) -> Check:
    t = "NC Recon damage model weights match the release"
    ran = any((_ev(f.get("properties") or {}, "M1") or {}).get("available") for f in feats)
    if not ran:
        return skip("model_weights_m1", t, CAT_MODEL, "the NC Recon damage model (M1) did not run here",
                    not_applicable=True)
    return skip("model_weights_m1", t, CAT_MODEL, "no released hash is recorded for ncrecon-dmg-v0 "
                "(pipeline/data/model/weights/ncrecon-dmg-v0.json carries none) and the run records none",
                not_applicable=False, source=NO_THRESHOLD)


def _label_agreement(path: str, by_id: dict[str, str]) -> dict[str, Any] | None:
    """Agreement with analyst labels in <labels>/<area>.csv (ops/analyze/evaluate.py format)."""
    if not os.path.exists(path):
        return None
    labs: dict[str, dict[str, str]] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                nid, lab = (r.get("ncr_id") or "").strip(), (r.get("label") or "").strip().lower()
                if nid and lab:
                    labs.setdefault(nid, {})[(r.get("labeler") or "unknown").strip()] = lab
    except (OSError, csv.Error):
        return None
    pairs = []
    for nid, ls in labs.items():
        lab = ls.get("adjudicated") or (next(iter(ls.values())) if len(set(ls.values())) == 1 else None)
        if lab in LEVELS and by_id.get(nid) in LEVELS:
            pairs.append((lab, by_id[nid]))
    if not pairs:
        return None
    same = sum(a == b for a, b in pairs) / len(pairs)
    tp = sum(a in SEVERE and b in SEVERE for a, b in pairs)
    fp = sum(a not in SEVERE and b in SEVERE for a, b in pairs)
    fn = sum(a in SEVERE and b not in SEVERE for a, b in pairs)
    f1 = (2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) else None
    return {"n": len(pairs), "same_level": round(same, 4), "major_or_destroyed_f1": None if f1 is None else round(f1, 4)}


def check_calibration(area, role, props, feats, out_dir, labels_dir) -> Check:
    t = "Agreement with ground truth"
    if role == "TEST":
        return skip("calibration", t, CAT_VALID, HELD_OUT, not_applicable=True,
                    source="config/events.yaml role TEST (docs/ops/PHASE_J_STATUS.md, hold-out hygiene)")
    if role == "OPS":
        return skip("calibration", t, CAT_VALID, "operational area: never used for evaluation",
                    not_applicable=True, source="ops/plan/events.py ROLES")
    cal = props.get("calibration") or {}
    fitted = {k: v for k, v in cal.items() if v and v != "none"}
    by_id = {(f.get("properties") or {}).get("ncr_id"): (f.get("properties") or {}).get("damage_level")
             for f in feats}
    lab = _label_agreement(os.path.join(labels_dir, f"{area}.csv"), by_id)
    refs = {}
    for suffix in ("sarcop_reference", "field_reference"):
        d = _read_json(os.path.join(out_dir, f"{area}.{suffix}.json"))
        if isinstance(d, dict) and str(d.get("role", "")).upper() != "TEST" and d.get("summary"):
            refs[suffix] = d
    if not lab and not refs and not fitted:
        return skip("calibration", t, CAT_VALID, "not yet validated for this hazard", not_applicable=False)
    parts, value, unit = [], None, ""
    if lab:
        value, unit = lab["same_level"], "share at the same level as analyst labels"
        parts.append(f"{_n(lab['n'])} analyst labels: {round(100 * lab['same_level'])}% at the same level"
                     + (f", Major-or-Destroyed F1 {lab['major_or_destroyed_f1']:.2f}"
                        if lab["major_or_destroyed_f1"] is not None else ""))
    sar = refs.get("sarcop_reference")
    if sar:
        s = sar["summary"]
        md = s.get("major_or_destroyed") or {}
        if value is None and md.get("f1") is not None:
            value, unit = md["f1"], "Major-or-Destroyed F1 against SAR field categories"
        parts.append(f"{_n(int(s.get('n', 0)))} search and rescue field calls: "
                     f"{round(100 * float(s.get('same_level', 0)))}% at the same level"
                     + (f", Major-or-Destroyed F1 {float(md['f1']):.2f}" if md.get("f1") is not None else ""))
    fld = refs.get("field_reference")
    if fld:
        s = fld["summary"]
        r = s.get("ncr_major_or_destroyed_at_destroyed")
        if value is None and r is not None:
            value, unit = r, "share of field-destroyed buildings called Major or Destroyed"
        parts.append(f"{_n(int(s.get('n', 0)))} county damage points"
                     + (f": {round(100 * float(r))}% of destroyed points called Major or Destroyed" if r is not None else ""))
    stale = [k.replace("_", " ") for k, d in refs.items() if d.get("run_id") and d["run_id"] != props.get("run_id")]
    msg = "; ".join(parts) + "."
    note = ("Probabilities are not calibrated." if not fitted else
            "Calibrated: " + ", ".join(f"{k} {v}" for k, v in fitted.items()) + ".")
    if stale:
        note += f" The {' and '.join(stale)} compared an earlier run."
    note += " This is a TUNE area, so none of this is a held-out result."
    return Check("calibration", t, CAT_VALID, WARN, msg, note=note,
                 source=f"{NO_THRESHOLD} (the M1 decision rule in docs/model/MODEL_CARD.md is for wildfire "
                        "at Altadena only)",
                 value=value, unit=unit,
                 detail={"labels": lab, "calibration": cal,
                         "references": {k: {"n": d["summary"].get("n"), "run_id": d.get("run_id")}
                                        for k, d in refs.items()}})


def check_products(area, props, out_dir) -> Check:
    t = "Side products come from this run"
    rid = props.get("run_id")
    found, stale, missing = [], [], []
    for suffix, name in (("response.json", "response"), ("impact.json", "people estimate"),
                         ("responder.json", "responder addresses"), ("ground_change.json", "lidar ground change")):
        d = _read_json(os.path.join(out_dir, f"{area}.{suffix}"))
        if not isinstance(d, dict):
            missing.append(name)
            continue
        found.append(name)
        if d.get("run_id") != rid:
            stale.append(f"{name} ({d.get('run_id') or 'no run id'})")
    src = "identity: every product records the run_id it was built from"
    if not found:
        return skip("products_match_run", t, CAT_RESPONSE, "no side products were built for this area",
                    not_applicable=True, source=src)
    if stale:
        msg = (f"Built from an earlier run, so their figures do not describe this assessment: "
               f"{', '.join(stale)}. Rebuild them.")
        st = FAIL
    else:
        names = found[0] if len(found) == 1 else ", ".join(found[:-1]) + " and " + found[-1]
        msg = f"The {names} {'come' if len(found) > 1 else 'comes'} from this run ({rid})."
        st = PASS
    note = f"Not built: {', '.join(missing)}." if missing else ""
    return Check("products_match_run", t, CAT_RESPONSE, st, msg, source=src, note=note,
                 detail={"run_id": rid, "found": found, "stale": stale, "missing": missing})


def check_people(area, props, feats, out_dir) -> Check:
    t = "People estimate covers every assessed home"
    src = "identity with ops/analyze/impact.py: assessed homes with an occupant estimate feed the estimate"
    imp = _read_json(os.path.join(out_dir, f"{area}.impact.json"))
    if not isinstance(imp, dict):
        return skip("people_estimate", t, CAT_RESPONSE, "no people estimate was built for this area",
                    not_applicable=True, source=src)
    if imp.get("status") == "NO_RESIDENTIAL_STRUCTURES" or imp.get("residential_structures_assessed") is None:
        return skip("people_estimate", t, CAT_RESPONSE, "the area has no assessed homes", not_applicable=True,
                    source=src)
    homes = with_occ = 0
    for f in feats:
        p = f.get("properties") or {}
        if not (p.get("flags") or {}).get("residential") or not p.get("damage_probs"):
            continue
        homes += 1
        o = p.get("occupants") or {}
        if o.get("nsi_estimate") is not None or o.get("usa_structures_median") is not None:
            with_occ += 1
    used = int(imp["residential_structures_assessed"])
    un_imp = (imp.get("unassessed_residential") or {}).get("structures")
    un_run = (props.get("not_assessed") or {}).get("residential")
    bad = used != with_occ or (un_imp is not None and un_run is not None and int(un_imp) != int(un_run))
    no_occ = homes - with_occ
    if bad:
        msg = (f"The people estimate used {_n(used)} homes, but {_n(with_occ)} assessed homes have an occupant "
               f"estimate" + (f"; it lists {un_imp} homes not assessed against {un_run} in the run" if
                              un_imp is not None and un_run is not None and int(un_imp) != int(un_run) else "")
               + ". It may be stale or incomplete.")
        st = FAIL
    else:
        msg = f"The people estimate uses all {_n(used)} assessed homes that have an occupant estimate"
        if un_imp is not None:
            msg += f" and counts the {_n(int(un_imp))} homes not assessed separately"
        if no_occ:
            msg += (f"; {_n(no_occ)} assessed home{'s have' if no_occ > 1 else ' has'} no occupant estimate "
                    f"and {'are' if no_occ > 1 else 'is'} left out of it")
            st = WARN
        else:
            st = PASS
        msg += "."
    return Check("people_estimate", t, CAT_RESPONSE, st, msg, source=src, value=used, limit=with_occ,
                 unit="homes", detail={"assessed_homes": homes, "with_occupant_estimate": with_occ,
                                       "used": used, "no_occupant_estimate": no_occ})


def landing_zone_margins(resp: dict[str, Any] | None) -> dict[str, Any] | None:
    """Per candidate: clear diameter against each aircraft it is said to fit,
    and slope against the slope limit. None when there is no landing block."""
    land = (resp or {}).get("landing")
    if not isinstance(land, dict):
        return None
    P = {**_LZ_DEFAULTS, **{k: v for k, v in (land.get("params") or {}).items() if k in _LZ_DEFAULTS}}
    recorded = bool(land.get("params"))
    out = []
    for c in land.get("candidates") or []:
        d, s = c.get("clear_diameter_m"), c.get("slope_deg")
        fits = list(c.get("fits") or [])
        ms = []
        if "UH-60" in fits or not fits:
            # clear_diameter_m is rounded to 1 m; the pick used the unrounded value
            ms.append(metric("UH-60 clear diameter", d, P["min_diameter_m"], "min", "m", slack=0.5))
        if "CH-47" in fits:
            ms.append(metric("CH-47 clear diameter", d, P["ch47_diameter_m"], "min", "m", slack=0.5))
        ms.append(metric("slope", s, P["max_slope_deg"], "max", "degrees", slack=0.05))
        loads = [m["load"] for m in ms if m["load"] is not None]
        load = max(loads) if loads else None
        bad = [m for m in ms if m["ok"] is False]
        limiting = max(ms, key=lambda m: m["load"] or 0)["label"] if loads else None
        out.append({"usng": c.get("usng"), "lon": c.get("lon"), "lat": c.get("lat"), "fits": fits,
                    "marginal": bool(c.get("marginal")), "cover": c.get("cover"),
                    "status": FAIL if bad else PASS, "load": load, "margin": margin_of(load),
                    "limiting": limiting, "metrics": ms})
    return {"params": P, "params_recorded": recorded, "source": LZ_SOURCE, "candidates": out,
            "caveat": land.get("caveat")}


def check_landing(lz: dict[str, Any] | None, has_response: bool) -> Check:
    t = "Landing-zone candidates meet the aircraft limits"
    if not has_response or lz is None:
        return skip("landing_zones", t, CAT_RESPONSE, "no response products were built for this area",
                    not_applicable=True, source=LZ_SOURCE)
    cs = lz["candidates"]
    if not cs:
        return skip("landing_zones", t, CAT_RESPONSE, "no landing-zone candidate was found in the area",
                    not_applicable=True, source=LZ_SOURCE)
    bad = [c for c in cs if c["status"] == FAIL]
    worst = max(cs, key=lambda c: c["load"] or 0)
    wm = max(worst["metrics"], key=lambda m: m["load"] or 0)
    if bad:
        msg = (f"{len(bad)} of {len(cs)} candidates miss a stated limit, first {bad[0]['usng']} "
               f"({', '.join(m['label'] for m in bad[0]['metrics'] if m['ok'] is False)}).")
    else:
        msg = (f"All {len(cs)} candidates meet the limits for the aircraft they are listed for; the tightest, "
               f"{worst['usng']}, has {wm['label']} {_n(wm['value'])} {wm['unit']} against "
               f"{_n(wm['limit'])} {wm['unit']} ({spare(worst['load'])}).")
    note = "Candidates are picked against these limits, so this confirms the stored list, not the ground."
    if not lz.get("params_recorded"):
        note += " The response file did not record its limits; the defaults were used."
    return Check("landing_zones", t, CAT_RESPONSE, FAIL if bad else PASS, msg, source=LZ_SOURCE, note=note,
                 value=wm["value"], limit=wm["limit"], unit=wm["unit"], kind=wm["kind"], load=worst["load"],
                 detail={"candidates": len(cs), "failing": len(bad), "tightest": worst["usng"]})


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def run_checks(area: str, out_dir: str | None = None, fc: dict[str, Any] | None = None,
               labels_dir: str | None = None) -> dict[str, Any]:
    """Self-check report for one assessed area. FileNotFoundError when the
    area has no assessment; ValueError on a bad area id."""
    if not _AREA.fullmatch(area or ""):
        raise ValueError("bad area id")
    out_dir = out_dir or OPS_OUT
    # same location ops/analyze/evaluate.py and ops/api.py read labels from
    labels_dir = labels_dir or os.environ.get("NCR_LABELS_DIR") or os.path.join(DATA_DIR, "labels")
    if fc is None:
        fc = _read_json(os.path.join(out_dir, f"{area}.geojson"))
        if not isinstance(fc, dict):
            raise FileNotFoundError(f"no ops assessment for {area}")
    props = fc.get("properties") or {}
    feats = fc.get("features") or []
    role = area_role(area, props)
    rules = _rules()
    resp = _read_json(os.path.join(out_dir, f"{area}.response.json"))
    lz = landing_zone_margins(resp if isinstance(resp, dict) else None)
    checks: list[Check] = []
    plan = (("buildings_conserved", lambda: check_conserved(props, feats)),
            ("totals_recomputed", lambda: check_totals(props, feats)),
            ("imagery_dates", lambda: check_dates(props, feats)),
            ("pair_geometry", lambda: check_geometry(props, rules)),
            ("coregistration", lambda: check_coreg(props, feats)),
            ("footprint_alignment", lambda: check_alignment(props, feats)),
            ("independent_route", lambda: check_independent(props, feats)),
            ("review_share", lambda: check_review(props, feats, rules)),
            ("model_weights", lambda: check_weights(props, feats)),
            ("model_weights_m1", lambda: check_weights_m1(feats)),
            ("calibration", lambda: check_calibration(area, role, props, feats, out_dir, labels_dir)),
            ("products_match_run", lambda: check_products(area, props, out_dir)),
            ("people_estimate", lambda: check_people(area, props, feats, out_dir)),
            ("landing_zones", lambda: check_landing(lz, isinstance(resp, dict))))
    for cid, fn in plan:
        try:
            checks.append(fn())
        except Exception as ex:  # noqa: BLE001 - a broken check is recorded, never dropped or fatal
            checks.append(Check(cid, "A check could not run", CAT_EVERY, FAIL,
                                f"The {cid.replace('_', ' ')} check could not run on these outputs "
                                f"({type(ex).__name__}: {str(ex)[:160]}).",
                                source="ops/selfcheck.py"))
    rows = [c.to_dict() for c in checks]
    return {"schema": SCHEMA, "area": area, "run_id": props.get("run_id"), "role": role,
            "generated_utc": utc_now(), "assessment_generated_utc": props.get("generated_utc"),
            **summarise(area, rows), "checks": rows, "landing_zones": lz,
            "note": "Checks label this assessment. They never block an export."}
