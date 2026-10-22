"""Groma Verify: the ground-truth engine (docs/truth/README.md).

Assessment -> value-of-information task list -> blind judgments from several
verifiers -> reliability-weighted consensus -> explicit release into the
protocol label files -> versioned dataset.

Store (all under `store_dir()`, `NCR_TRUTH_DIR` overrides):
  judgments.jsonl        one line per judgment, append-only
  released/<area>.json   what has been released, so release is idempotent
  exports/               dataset versions

Nothing here writes to the label files except `release()`, which a person runs.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import threading
import time
import zipfile
from collections import Counter, defaultdict
from typing import Any

from . import DATA_DIR, DISCLAIMER
from .analyze.classes import FEMA, FEMA_LABEL
from .guard import csv_cell

K_JUDGMENTS = 3          # independent verifiers per building
RELEASE_MIN_AGREE = 2    # at least this many level votes on the winning level
RELEASE_POSTERIOR = 0.90
PRIOR_RELIABILITY = (7.0, 3.0)   # Beta prior: a new verifier is right ~70% of the time
CANNOT = "cannot_tell"
CHOICES = (*FEMA, CANNOT)
ROLES = ("verifier", "analyst")
KINDS = ("remote", "field")      # field: a photo at the building (schema only for now)
PROTOCOL = "ncr-label-v1"
_NAME = re.compile(r"[^\w .-]")
_lock = threading.Lock()


def store_dir() -> str:
    return os.environ.get("NCR_TRUTH_DIR") or os.path.join(DATA_DIR, "truth")


def labels_dir() -> str:
    return os.environ.get("NCR_LABELS_DIR") or os.path.join(DATA_DIR, "labels")


def ops_out() -> str:
    return os.path.join(DATA_DIR, "output", "ops")


def _judgments_path() -> str:
    return os.path.join(store_dir(), "judgments.jsonl")


# --------------------------------------------------------------------------- #
# areas and tasks
# --------------------------------------------------------------------------- #
def _load_area(area: str) -> dict[str, Any]:
    with open(os.path.join(ops_out(), f"{area}.geojson"), encoding="utf-8") as fh:
        return json.load(fh)


def area_role(area: str, fc: dict[str, Any] | None = None) -> str:
    try:
        from .plan.events import event_for_area

        found = event_for_area(area)
        if found:
            return found[1].role
    except Exception:  # noqa: BLE001 - registry unreadable: fall back to the run's own record
        pass
    return ((fc or {}).get("properties", {}).get("aoi") or {}).get("role") or "UNREGISTERED"


def value_of_information(p: dict[str, Any]) -> float:
    """How much one human answer is worth for this building: model
    uncertainty (normalised entropy) times what rides on it (chance of
    Major or Destroyed, and people living there)."""
    probs = p.get("damage_probs") or {}
    vals = [max(0.0, float(probs.get(k) or 0.0)) for k in FEMA]
    tot = sum(vals) or 1.0
    vals = [v / tot for v in vals]
    h = -sum(v * math.log(v) for v in vals if v > 0) / math.log(len(FEMA))
    severe = vals[FEMA.index("major")] + vals[FEMA.index("destroyed")]
    occ = p.get("occupants") or {}
    people = occ.get("nsi_estimate") or occ.get("usa_structures_median") or 0
    try:
        people = max(0.0, float(people))
    except (TypeError, ValueError):
        people = 0.0
    return round(h * (0.25 + severe) * (1.0 + math.log1p(people)), 6)


def candidates(area: str, fc: dict[str, Any] | None = None, limit: int = 300) -> list[dict[str, Any]]:
    """Assessed buildings in this area ordered by value of information.
    Deterministic: ties break on ncr_id."""
    fc = fc or _load_area(area)
    out = []
    for f in fc["features"]:
        p = f.get("properties") or {}
        if (f.get("geometry") or {}).get("type") != "Polygon" or not p.get("damage_level"):
            continue
        out.append({"area": area, "ncr_id": p["ncr_id"], "voi": value_of_information(p)})
    out.sort(key=lambda t: (-t["voi"], t["ncr_id"]))
    return out[:limit]


# --------------------------------------------------------------------------- #
# judgments
# --------------------------------------------------------------------------- #
def clean_name(v: str) -> str:
    v = _NAME.sub("", v or "").strip()[:40]
    if not v:
        raise ValueError("a verifier name is required")
    return v


def load_judgments(area: str | None = None) -> list[dict[str, Any]]:
    p = _judgments_path()
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                j = json.loads(line)
            except json.JSONDecodeError:
                continue
            if area is None or j.get("area") == area:
                out.append(j)
    return out


def submit(area: str, ncr_id: str, label: str, worker: str, *, role: str = "verifier",
           kind: str = "remote", blind: bool = True, seconds: float | None = None) -> dict[str, Any]:
    if label not in CHOICES:
        raise ValueError(f"label must be one of {CHOICES}")
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    worker = clean_name(worker)
    fc = _load_area(area)
    if not any((f.get("properties") or {}).get("ncr_id") == ncr_id for f in fc["features"]):
        raise LookupError("structure not in this assessment")
    j = {"area": area, "ncr_id": ncr_id, "label": label, "worker": worker, "role": role, "kind": kind,
         "blind": bool(blind), "seconds": None if seconds is None else round(max(0.0, float(seconds)), 1),
         "aoi_role": area_role(area, fc), "run_id": fc.get("properties", {}).get("run_id"),
         "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with _lock:
        prior = [x for x in load_judgments(area) if x["ncr_id"] == ncr_id and x["worker"] == worker]
        if prior:
            raise PermissionError("this verifier already judged this building")
        os.makedirs(store_dir(), exist_ok=True)
        with open(_judgments_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(j) + "\n")
    return j


# --------------------------------------------------------------------------- #
# consensus
# --------------------------------------------------------------------------- #
def _posterior(votes: list[tuple[str, float]]) -> list[float]:
    """One-coin model: a verifier with reliability r names the true level with
    probability r and each other level with (1 - r) / 4. Uniform prior over
    levels: never the model's own probabilities (that would be circular)."""
    k = len(FEMA)
    logp = [0.0] * k
    for lab, r in votes:
        r = min(max(r, 0.05), 0.99)
        for c in range(k):
            logp[c] += math.log(r if FEMA[c] == lab else (1 - r) / (k - 1))
    m = max(logp)
    w = [math.exp(v - m) for v in logp]
    s = sum(w)
    return [v / s for v in w]


def _decide(js: list[dict[str, Any]], rel: dict[str, float]) -> dict[str, Any]:
    # an analyst settles a building only after the verifiers disagreed: before
    # that, an analyst's answer is one more vote (never a single-source label)
    analysts = [j for j in js if j["role"] == "analyst" and j["label"] != CANNOT]
    verifiers = [j for j in js if j["role"] != "analyst"]
    if analysts and len(verifiers) < K_JUDGMENTS:
        js = [{**j, "role": "verifier"} if j["role"] == "analyst" else j for j in js]
        analysts = []
    if analysts:
        last = sorted(analysts, key=lambda j: j["utc"])[-1]
        return {"status": "verified", "label": last["label"], "by": "adjudicated", "posterior": 1.0,
                "agree": sum(j["label"] == last["label"] for j in js), "n": len(js)}
    votes = [(j["label"], rel.get(j["worker"], _prior_rel())) for j in js if j["label"] != CANNOT]
    cannot = sum(j["label"] == CANNOT for j in js)
    if cannot >= 2 and len(votes) < RELEASE_MIN_AGREE:
        return {"status": "unverifiable", "label": None, "by": None, "posterior": None, "agree": 0, "n": len(js)}
    if not votes:
        return {"status": "open", "label": None, "by": None, "posterior": None, "agree": 0, "n": len(js)}
    post = _posterior(votes)
    best = max(range(len(FEMA)), key=lambda c: post[c])
    agree = sum(lab == FEMA[best] for lab, _ in votes)
    if agree >= RELEASE_MIN_AGREE and post[best] >= RELEASE_POSTERIOR:
        return {"status": "verified", "label": FEMA[best], "by": "consensus", "posterior": round(post[best], 4),
                "agree": agree, "n": len(js)}
    status = "escalated" if len(js) >= K_JUDGMENTS else "open"
    return {"status": status, "label": None, "by": None, "posterior": round(post[best], 4),
            "leading": FEMA[best], "agree": agree, "n": len(js)}


def _prior_rel() -> float:
    a, b = PRIOR_RELIABILITY
    return a / (a + b)


def reliabilities(js: list[dict[str, Any]], rounds: int = 4) -> dict[str, dict[str, float]]:
    """Per-verifier reliability: agreement with settled answers on buildings
    others also judged (leave-one-out), Beta-smoothed, iterated a few times."""
    by_b: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for j in js:
        by_b[(j["area"], j["ncr_id"])].append(j)
    rel = {w: _prior_rel() for w in {j["worker"] for j in js}}
    stats: dict[str, dict[str, float]] = {}
    for _ in range(rounds):
        agree: Counter = Counter()
        seen: Counter = Counter()
        for group in by_b.values():
            for j in group:
                if j["label"] == CANNOT or j["role"] == "analyst":
                    continue
                others = [o for o in group if o is not j]
                d = _decide(others, rel) if others else None
                if not d or d["status"] != "verified":
                    continue
                seen[j["worker"]] += 1
                agree[j["worker"]] += j["label"] == d["label"]
        a, b = PRIOR_RELIABILITY
        rel = {w: (agree[w] + a) / (seen[w] + a + b) for w in rel}
        stats = {w: {"reliability": round(rel[w], 3), "scored": int(seen[w]), "agreed": int(agree[w])} for w in rel}
    return stats


def consensus(area: str) -> dict[str, dict[str, Any]]:
    js_all = load_judgments()
    rel = {w: s["reliability"] for w, s in reliabilities(js_all).items()}
    by: dict[str, list[dict]] = defaultdict(list)
    for j in js_all:
        if j["area"] == area:
            by[j["ncr_id"]].append(j)
    return {nid: _decide(js, rel) for nid, js in by.items()}


# --------------------------------------------------------------------------- #
# task routing
# --------------------------------------------------------------------------- #
def _when(i: dict[str, Any]) -> str:
    """Capture date when known, else the program label; plus the source."""
    when = (i.get("acquired_utc") or "")[:10] or (i.get("date_label") or "").split("(")[0].split(";")[0].strip()
    src = i.get("source") or ""
    return f"{when}, {src}" if when and src and when not in src else (when or src or "date unknown")


def next_task(area: str, worker: str, role: str = "verifier") -> dict[str, Any] | None:
    """The most valuable building this verifier has not judged, finishing
    buildings already in progress first. Analysts get escalated buildings
    first. The task carries no model output: verification is blind."""
    worker = clean_name(worker)
    fc = _load_area(area)
    js = load_judgments(area)
    mine = {j["ncr_id"] for j in js if j["worker"] == worker}
    count = Counter(j["ncr_id"] for j in js)
    state = consensus(area)
    released = _released_ids(area)
    cands = candidates(area, fc)
    order = {c["ncr_id"]: i for i, c in enumerate(cands)}

    def open_for(nid: str) -> bool:
        st = state.get(nid, {}).get("status", "open")
        if nid in mine or nid in released or st in ("verified", "unverifiable"):
            return False
        if role == "analyst":
            return st == "escalated"
        return st == "open" and count[nid] < K_JUDGMENTS

    pool = [c for c in cands if open_for(c["ncr_id"])]
    pool.sort(key=lambda c: (-(count[c["ncr_id"]] > 0), order[c["ncr_id"]]))
    if not pool:
        return None
    t = pool[0]
    post = next((i for i in (fc["properties"].get("provenance") or {}).get("imagery", []) if i.get("role") == "post"), {})
    pre = next((i for i in (fc["properties"].get("provenance") or {}).get("imagery", []) if i.get("role") == "pre"), {})
    return {"area": area, "ncr_id": t["ncr_id"], "kind": "remote", "judgments_so_far": count[t["ncr_id"]],
            "needed": K_JUDGMENTS, "remaining_in_area": len(pool),
            "imagery": {"pre": _when(pre), "post": _when(post)},
            "choices": list(CHOICES)}


# --------------------------------------------------------------------------- #
# release, dataset, metrics
# --------------------------------------------------------------------------- #
def _released_path(area: str) -> str:
    return os.path.join(store_dir(), "released", f"{area}.json")


def _released_ids(area: str) -> set[str]:
    p = _released_path(area)
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8") as fh:
        return set(json.load(fh).get("ncr_ids", []))


def _imagery(fc: dict[str, Any]) -> list[dict[str, Any]]:
    return [{k: i.get(k) for k in ("role", "source", "license", "date_label", "acquired_utc")}
            for i in (fc.get("properties", {}).get("provenance") or {}).get("imagery", [])]


def commercial_ok(imagery: list[dict[str, Any]]) -> bool:
    """False when any imagery behind the label carries a non-commercial term."""
    for i in imagery:
        lic = (i.get("license") or "").lower()
        src = (i.get("source") or "").lower()
        if "nc 4.0" in lic or "by-nc" in lic or "noncommercial" in lic or "non-commercial" in lic or "maxar" in src:
            return False
    return True


def release(area: str) -> dict[str, Any]:
    """Write verified consensus into the protocol label file for this area.
    Idempotent: a building is released once."""
    fc = _load_area(area)
    role = area_role(area, fc)
    state = consensus(area)
    done = _released_ids(area)
    post = next((i for i in (fc["properties"].get("provenance") or {}).get("imagery", []) if i.get("role") == "post"), {})
    img_date = post.get("acquired_utc") or post.get("date_label") or post.get("dataset_version") or ""
    new = [(nid, d) for nid, d in sorted(state.items()) if d["status"] == "verified" and nid not in done]
    if new:
        os.makedirs(labels_dir(), exist_ok=True)
        path = os.path.join(labels_dir(), f"{area}.csv")
        first = not os.path.exists(path)
        with _lock, open(path, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if first:
                w.writerow(["ncr_id", "label", "labeler", "protocol", "imagery_date", "aoi_role", "labeled_utc", "notes"])
            stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            for nid, d in new:
                w.writerow([nid, d["label"], csv_cell(d["by"]), PROTOCOL, img_date, role, stamp,
                            f"Groma Verify: {d['agree']} of {d['n']} agree, posterior {d['posterior']}"])
        os.makedirs(os.path.dirname(_released_path(area)), exist_ok=True)
        with open(_released_path(area), "w", encoding="utf-8") as fh:
            json.dump({"area": area, "aoi_role": role, "ncr_ids": sorted(done | {n for n, _ in new})}, fh)
    return {"area": area, "aoi_role": role, "released_now": len(new), "released_total": len(done) + len(new),
            "used_for": "calibration and development" if role == "TUNE" else
                        "held-out evaluation only" if role == "TEST" else "operations (not calibration or evaluation)"}


def dataset(areas: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verified records plus a datasheet. Records carry outline, verified level,
    agreement, role and the imagery licence behind them."""
    js_all = load_judgments()
    areas = sorted(areas or {j["area"] for j in js_all})
    records = []
    for area in areas:
        try:
            fc = _load_area(area)
        except FileNotFoundError:
            continue
        role = area_role(area, fc)
        img = _imagery(fc)
        ok = commercial_ok(img)
        feats = {f["properties"]["ncr_id"]: f for f in fc["features"] if f.get("properties")}
        for nid, d in sorted(consensus(area).items()):
            if d["status"] != "verified" or nid not in feats:
                continue
            f = feats[nid]
            records.append({
                "area": area, "event": (fc["properties"].get("event") or {}).get("id"), "ncr_id": nid,
                "aoi_role": role, "split": {"TUNE": "development", "TEST": "held_out"}.get(role, "operational"),
                "label": d["label"], "label_name": FEMA_LABEL[d["label"]], "settled_by": d["by"],
                "agreeing": d["agree"], "judgments": d["n"], "posterior": d["posterior"],
                "geometry": f["geometry"], "imagery": img, "commercial_use": ok,
            })
    by_split = Counter(r["split"] for r in records)
    sheet = {
        "name": "Groma Verify structure damage labels", "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "records": len(records), "by_split": dict(by_split), "by_label": dict(Counter(r["label"] for r in records)),
        "areas": areas, "commercial_use_records": sum(r["commercial_use"] for r in records),
        "method": (f"Blind remote judgments of before/after imagery, {K_JUDGMENTS} per building, pooled with "
                   "per-verifier reliability (one-coin Dawid-Skene, uniform prior); verified when at least "
                   f"{RELEASE_MIN_AGREE} agree and the pooled probability is at least {RELEASE_POSTERIOR}; "
                   "disagreements settled by an analyst."),
        "levels": [FEMA_LABEL[k] for k in FEMA],
        "caveats": [
            "Labels describe what the imagery shows, under docs/ops/LABELING_PROTOCOL.md; interior flood damage is not visible from above.",
            "Records with commercial_use = false rest on imagery under a non-commercial licence (Maxar Open Data, CC BY-NC 4.0).",
            "held_out records must not be used to tune or calibrate anything evaluated on them.",
            "Building outlines from OpenStreetMap carry the ODbL; check source_ids in the assessment before redistribution.",
        ],
        "disclaimer": DISCLAIMER,
    }
    return records, sheet


def export(areas: list[str] | None = None, keep: bool = False) -> tuple[bytes, dict[str, Any]]:
    records, sheet = dataset(areas)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("labels.jsonl", "".join(json.dumps(r) + "\n" for r in records))
        z.writestr("datasheet.json", json.dumps(sheet, indent=2))
    data = buf.getvalue()
    if keep:  # a versioned copy in the store (the CLI); API downloads are not kept
        d = os.path.join(store_dir(), "exports")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"verify-{sheet['generated_utc'].replace(':', '')}.zip"), "wb") as fh:
            fh.write(data)
    return data, sheet


def area_status(area: str) -> dict[str, Any]:
    fc = _load_area(area)
    js = load_judgments(area)
    st = consensus(area)
    c = Counter(d["status"] for d in st.values())
    secs = sorted(j["seconds"] for j in js if j.get("seconds"))
    cands = candidates(area, fc)
    return {
        "area": area, "aoi_role": area_role(area, fc), "candidates": len(cands),
        "judgments": len(js), "verifiers": len({j["worker"] for j in js}),
        "buildings_touched": len(st), "verified": c.get("verified", 0), "escalated": c.get("escalated", 0),
        "unverifiable": c.get("unverifiable", 0), "in_progress": c.get("open", 0),
        "released": len(_released_ids(area)),
        "verified_by_level": dict(Counter(d["label"] for d in st.values() if d["status"] == "verified")),
        "median_seconds_per_judgment": secs[len(secs) // 2] if secs else None,
    }


def metrics() -> dict[str, Any]:
    js = load_judgments()
    areas = sorted({j["area"] for j in js})
    per = []
    for a in areas:
        try:
            per.append(area_status(a))
        except FileNotFoundError:
            continue
    minutes = sum(j.get("seconds") or 0 for j in js) / 60.0
    verified = sum(p["verified"] for p in per)
    return {"areas": per, "judgments": len(js), "verifiers": reliabilities(js),
            "verified_structures": verified,
            "verified_per_human_minute": round(verified / minutes, 3) if minutes else None}
