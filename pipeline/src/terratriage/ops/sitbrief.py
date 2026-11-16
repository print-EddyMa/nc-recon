"""Situation brief as a case file: short items, every figure traced to evidence.

The pattern comes from Canary's case file (canary/detective.py): gather the
facts into a numbered evidence list first (E1, E2, ...), write from that list
only, then let code, not the writer, check that every figure in the text can
be found in the evidence.

  evidence(area)    area-level facts only, from the area's outputs
  rule_brief(area)  the default: 4 to 6 items written by fixed rules
  ai_brief(area)    optional: Claude writes the items from the evidence list
                    alone; untraced items are dropped; any failure falls back
                    to the rules brief and says why

What is read: `<area>.geojson` top-level properties (never a structure),
`<area>.impact.json` area totals and `<area>.response.json` counts (roads,
cut-off scenarios, lifelines, landing-zone count, sector totals). What is
never read: `<area>.responder.json` (addresses), `*.field_reference.json`,
`*.sarcop_reference.json`, the labels and truth directories (TEST areas stay
held out). Sector grid references (1 km USNG) are kept in a `locator` field
that the rules text and the console may show; they never go to Claude.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

from . import DISCLAIMER, OPS_OUT
from .analyze.classes import FEMA, FEMA_LABEL

SAFETY = "Decision support. Verify on the ground."
MODEL = os.environ.get("NCR_SITBRIEF_MODEL", "claude-opus-5-5")
KINDS = ("headline", "damage", "access", "search", "unknown", "verify")
TITLES = {"headline": "Headline", "damage": "Damage", "access": "Access",
          "search": "Where to search first", "unknown": "Not known yet", "verify": "What to verify"}
LIFELINE_WORD = {"green": "Stable", "yellow": "Strained", "red": "Disrupted", "grey": "Unknown"}

_cache: dict[tuple, tuple[tuple, dict]] = {}
_ai_lock = threading.Lock()


def _out(out_dir: str | None) -> str:
    # NCR_OPS_OUT is read at call time too, so a scratch directory works
    # even when the package was imported first
    return out_dir or os.environ.get("NCR_OPS_OUT") or OPS_OUT


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _r1(v: float | int | None) -> float | int | None:
    if v is None:
        return None
    return int(v) if float(v).is_integer() else round(float(v), 1)


# --------------------------------------------------------------------------- #
# evidence
# --------------------------------------------------------------------------- #
class _Locker:
    def __init__(self) -> None:
        self.items: list[dict] = []
        self.by_key: dict[str, dict] = {}

    def add(self, key: str, label: str, value: Any, source: str, unit: str | None = None,
            interval: list | None = None, locator: str | None = None) -> dict:
        item = {"id": f"E{len(self.items) + 1}", "label": label, "value": value, "unit": unit,
                "interval": interval, "source": source}
        if locator:
            item["locator"] = locator
        self.items.append(item)
        self.by_key[key] = item
        return item


def _gather(area: str, out_dir: str | None = None) -> tuple[list[dict], dict[str, dict], dict]:
    out = _out(out_dir)
    gj = f"{area}.geojson"
    fc = _read(os.path.join(out, gj))
    if fc is None:
        raise FileNotFoundError(f"no ops assessment for {area}")
    P = fc.get("properties") or {}
    L = _Locker()
    aoi = P.get("aoi") or {}
    name = aoi.get("name")
    if not name:
        try:
            from .plan.events import area_name

            name = area_name(area)
        except Exception:  # noqa: BLE001 - a display name must not sink the brief
            name = area.replace("_", " ").title()
    county = aoi.get("county")
    if not county:
        from .counties import county_of

        county = county_of(f.get("properties", {}).get("cbfips_2010") for f in fc.get("features") or [])
    where = f"{name} ({county} Co.)" if county else name
    ev = P.get("event") or {}
    L.add("area", "Area", where, gj)
    if ev.get("name"):
        L.add("event", "Event", ev["name"], gj)
    if ev.get("declarations"):
        L.add("declarations", "Disaster declarations", ", ".join(ev["declarations"]), gj)
    if ev.get("incident_begin"):
        L.add("incident_begin", "Incident began", ev["incident_begin"], gj)
    if P.get("generated_utc"):
        L.add("generated", "Assessment generated (UTC)", P["generated_utc"], gj)

    n = int(P.get("n_structures") or 0)
    na = P.get("not_assessed") or {}
    na_total = int(na.get("total") or 0)
    L.add("n_structures", "Structures in the inventory", n, gj, "structures")
    L.add("assessed", "Structures assessed from imagery", n - na_total, gj, "structures")
    L.add("not_assessed", "Structures not assessed (no footprint in any source)", na_total, gj, "structures")
    if na.get("residential") is not None:
        L.add("not_assessed_res", "Homes among the structures not assessed", int(na["residential"]), gj, "homes")
    ec = P.get("expected_counts") or {}
    rng = P.get("expected_counts_80pct") or {}
    for c in reversed(FEMA):
        if c in ec:
            L.add(f"exp_{c}", f"Expected {FEMA_LABEL[c]}", _r1(ec[c]), gj, "structures, with 80% range",
                  list(rng[c]) if rng.get(c) else None)
    if "major" in ec and "destroyed" in ec:
        lo = sum((rng.get(c) or [0, 0])[0] for c in ("major", "destroyed"))
        hi = sum((rng.get(c) or [0, 0])[1] for c in ("major", "destroyed"))
        L.add("severe", "Expected Major or Destroyed (the two levels added)", _r1(ec["major"] + ec["destroyed"]),
              gj, "structures; range is the two 80% ranges added", [lo, hi])
    if P.get("n_needs_review") is not None:
        L.add("needs_review", "Calls flagged for human review", int(P["n_needs_review"]), gj, "structures")
    calib = (P.get("calibration") or {}).get("cnn")
    if calib is not None:
        L.add("calibrated", "Damage probabilities calibrated on ground-truth labels",
              "no" if calib == "none" else "yes", gj)
    pc = P.get("pair_context") or {}
    if pc.get("pair_gap_days") is not None:
        L.add("pair_gap", "Days between the pre-event and post-event images", int(pc["pair_gap_days"]), gj, "days")
    pdi = pc.get("post_days_after_incident")
    if isinstance(pdi, list) and len(pdi) == 2:
        L.add("post_days", "Post-event image taken after the incident", f"{pdi[0]} to {pdi[1]}", gj, "days")
    for i, w in enumerate(P.get("warnings") or []):
        L.add(f"warning_{i}", "Data warning", str(w), gj)
    if P.get("runtime_sec") is not None:
        L.add("runtime", "Assessment run time", _r1(P["runtime_sec"]), gj, "seconds")

    run_id = P.get("run_id")
    files = [gj]

    def _same_run(d: dict | None, fname: str, what: str) -> dict | None:
        if d is None:
            return None
        files.append(fname)
        if d.get("run_id") and run_id and d["run_id"] != run_id:
            L.add(f"{what}_stale", f"{what.title()} products", "built from an earlier run; not used", fname)
            return None
        return d

    ij = f"{area}.impact.json"
    imp = _same_run(_read(os.path.join(out, ij)), ij, "impact")
    if imp:
        d = imp.get("expected_displaced") or {}
        if d.get("median") is not None:
            L.add("displaced", "People who may be displaced from assessed homes", round(d["median"]), ij,
                  "people, with 10th to 90th percentile",
                  [round(d["p10"]), round(d["p90"])] if d.get("p10") is not None else None)
        ua = imp.get("unassessed_residential") or {}
        if ua.get("occupants_nsi") is not None:
            L.add("unassessed_people", "Residents of homes not assessed (NSI estimate)",
                  round(ua["occupants_nsi"]), ij, "people")
        if imp.get("occupancy_adjustment"):
            L.add("occupancy", "Seasonal and vacant homes adjusted for",
                  "no" if "UNADJUSTED" in imp["occupancy_adjustment"] else "yes", ij)

    rj = f"{area}.response.json"
    resp = _same_run(_read(os.path.join(out, rj)), rj, "response")
    if resp is None and "response_stale" not in L.by_key:
        L.add("response_missing", "Road access, lifelines and landing zones", "not built for this area yet", rj)
    if resp:
        s = resp.get("summary") or {}
        if s.get("coverage") is not None:
            L.add("coverage", "Share of structures assessed", round(100 * s["coverage"], 1), rj, "percent")
        roads = (resp.get("access") or {}).get("roads") or {}
        if roads.get("blocked") is not None:
            L.add("roads_blocked", "Road segments mapped as blocked", roads["blocked"], rj, "segments")
        if roads.get("debris") is not None:
            L.add("roads_debris", "Road segments beside a Destroyed building (possible debris)", roads["debris"], rj,
                  "segments")
        if roads.get("bridge") is not None:
            L.add("bridges", "Bridges not yet verified", roads["bridge"], rj, "bridges")
        cut = s.get("cut_off") or (resp.get("access") or {}).get("scenarios") or {}
        for sc, lab in (("known_blocks", "known road blocks"), ("plus_debris", "known blocks plus debris"),
                        ("worst_case", "worst case, every flagged road shut")):
            c = cut.get(sc) or {}
            if c.get("isolated_buildings") is not None:
                L.add(f"cut_{sc}_b", f"Buildings cut off by {lab}", c["isolated_buildings"], rj, "buildings")
                L.add(f"cut_{sc}_p", f"People cut off by {lab} (estimate)", _r1(c.get("isolated_people_est")), rj,
                      "people")
        if s.get("landing_zone_candidates") is not None:
            L.add("lz", "Landing zone candidates (for reconnaissance, not approved)", s["landing_zone_candidates"], rj,
                  "sites")
        lifelines = (resp.get("resources") or {}).get("lifelines") or s.get("lifelines") or []
        if lifelines:
            off = [ll for ll in lifelines if ll.get("status") != "green"]
            L.add("lifelines_total", "Community lifelines checked", len(lifelines), rj, "lifelines")
            L.add("lifelines_off", "Lifelines not stable", len(off), rj, "lifelines")
            for ll in lifelines:
                k = ll.get("lifeline") or ll.get("label")
                L.add(f"ll_{k}", f"Lifeline: {ll.get('label')}", LIFELINE_WORD.get(ll.get("status"), "Unknown"), rj)
                if ll.get("disrupted"):
                    L.add(f"ll_{k}_dis", f"{ll.get('label')}: facilities disrupted", ll["disrupted"], rj, "facilities")
                if ll.get("at_risk"):
                    L.add(f"ll_{k}_risk", f"{ll.get('label')}: facilities at risk", ll["at_risk"], rj, "facilities")
        if s.get("water_systems_at_risk") is not None:
            L.add("water_at_risk", "Public water systems at risk", s["water_systems_at_risk"], rj, "systems")
        if s.get("private_well_homes") is not None:
            L.add("wells", "Homes on private wells", s["private_well_homes"], rj, "homes")
        secs = sorted(resp.get("sectors") or [], key=lambda x: x.get("priority") or 99)[:3]
        if secs:
            L.add("sectors_n", "Search sectors ranked (1 km grid)", len(resp.get("sectors") or []), rj, "sectors")
        for sec in secs:
            p = sec.get("priority")
            loc = sec.get("usng_1km")
            L.add(f"sec{p}_sev", f"Priority sector {p}: expected Major or Destroyed",
                  _r1(sec.get("major_or_destroyed_expected")), rj, "structures", locator=loc)
            L.add(f"sec{p}_ppl", f"Priority sector {p}: people in buildings likely Major or Destroyed",
                  _r1(sec.get("people_in_severe_expected")), rj, "people", locator=loc)
            if sec.get("needs_review") is not None:
                L.add(f"sec{p}_rev", f"Priority sector {p}: calls flagged for review", sec["needs_review"], rj,
                      "structures", locator=loc)
        for i, note in enumerate(s.get("reading_notes") or []):
            L.add(f"note_{i}", "Reading note", str(note), rj)

    mtimes = tuple((f, os.path.getmtime(os.path.join(out, f))) for f in files)
    meta = {"area": area, "run_id": run_id, "where": where, "n_features": len(fc.get("features") or []),
            "fingerprint": (run_id, mtimes)}
    return L.items, L.by_key, meta


def evidence(area: str, out_dir: str | None = None) -> list[dict]:
    """The numbered evidence list for an area (area-level facts only)."""
    return _gather(area, out_dir)[0]


# --------------------------------------------------------------------------- #
# number tracing (ported from Canary's detective.trace_numbers)
# --------------------------------------------------------------------------- #
_NUMBER = re.compile(r"(?<![A-Za-z0-9.])[-+−]?\d[\d,]*(?:\.\d+)?")
_SCALE = re.compile(r"\s?(k|thousand|m|million|b|billion)\b", re.I)
_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}
_EID = re.compile(r"\bE\d+\b")


def _numbers_in(obj: Any) -> set[float]:
    found: set[float] = set()
    if isinstance(obj, bool) or obj is None:
        return found
    if isinstance(obj, (int, float)):
        found.add(abs(float(obj)))
    elif isinstance(obj, str):
        for m in _NUMBER.findall(obj):
            try:
                found.add(abs(float(m.replace(",", "").replace("−", "-"))))
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for value in obj.values():
            found |= _numbers_in(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            found |= _numbers_in(value)
    return found


def _known(evidence_items: list[dict]) -> set[float]:
    return _numbers_in([{k: v for k, v in e.items() if k not in ("id", "source")} for e in evidence_items])


def trace_numbers(texts: list[str], evidence_items: list[dict]) -> dict:
    """Check that every figure in the texts appears in the evidence.

    A written figure matches an evidence number when they agree at the
    precision the text used (so 119 matches 119.2, 120 does not). A figure
    followed by % may also match a fraction, and one followed by k, M or B
    (thousand, million, billion) is scaled first. Evidence ids are not
    figures. Unlike Canary there is no small-number exemption: an invented
    "8 sectors" is caught.
    """
    known = _known(evidence_items)
    checked, untraced = 0, []
    for text in texts:
        cleaned = _EID.sub(" ", text or "")
        for m in _NUMBER.finditer(cleaned):
            raw = m.group(0)
            token = raw.replace(",", "").replace("−", "-")
            try:
                value = abs(float(token))
            except ValueError:
                continue
            decimals = len(token.split(".")[1]) if "." in token else 0
            tol = 0.5 * 10 ** (-decimals) + 1e-9
            rest = cleaned[m.end():]
            cands = [(value, tol)]
            if rest.startswith("%"):
                cands.append((value / 100, tol / 100))
            sm = _SCALE.match(rest)
            if sm:
                k = _MULT[sm.group(1).lower()]
                cands.append((value * k, tol * k))
            checked += 1
            if not any(abs(kn - v) <= t for v, t in cands for kn in known):
                untraced.append(raw.strip())
    return {"total": checked, "traced": checked - len(untraced), "untraced": untraced[:20]}


def trace_item(text: str, cites: list[str], evidence_items: list[dict]) -> dict:
    """Trace one item against the evidence it cites, not the whole list: a
    figure that happens to appear somewhere else in the evidence does not
    count, which keeps small invented numbers from tracing by accident."""
    cited = set(cites)
    return trace_numbers([text], [e for e in evidence_items if e["id"] in cited])


def _sum_traces(traces: list[dict]) -> dict:
    untraced = [u for t in traces for u in t["untraced"]]
    total = sum(t["total"] for t in traces)
    return {"total": total, "traced": total - len(untraced), "untraced": untraced[:20]}


# --------------------------------------------------------------------------- #
# the rules writer
# --------------------------------------------------------------------------- #
def _n(v: Any) -> str:
    return f"{round(v):,}" if isinstance(v, (int, float)) else str(v)


def _clean(text: str) -> str:
    """House style: no em or en dashes, single spaces."""
    text = text.replace(" — ", ", ").replace("—", ", ").replace(" – ", " to ").replace("–", " to ")
    return re.sub(r"\s{2,}", " ", text).strip()


def _write_rules(K: dict[str, dict], meta: dict) -> list[dict]:
    def v(key: str) -> Any:
        return K[key]["value"] if key in K else None

    def ids(*keys: str) -> list[str]:
        return sorted({K[k]["id"] for k in keys if k in K}, key=lambda i: int(i[1:]))

    def rng(key: str) -> str:
        iv = K.get(key, {}).get("interval")
        return f" (range {_n(iv[0])} to {_n(iv[1])})" if iv else ""

    items: list[dict] = []
    where = v("area")
    if meta["n_features"] == 0:
        items.append({"kind": "headline", "text": f"{where}: no structures were found in the footprint inventories, "
                      "so nothing was assessed. If buildings are known to be here, the inventories are incomplete.",
                      "evidence": ids("area", "n_structures")})
    else:
        items.append({"kind": "headline", "text": f"{where}: about {_n(v('severe'))} of {_n(v('assessed'))} assessed "
                      f"structures are likely Major or Destroyed{rng('severe')}.",
                      "evidence": ids("area", "severe", "assessed")})
        parts = [f"{FEMA_LABEL[c]} {_n(v(f'exp_{c}'))}" + (rng(f"exp_{c}") if c in ("destroyed", "major") else "")
                 for c in reversed(FEMA) if f"exp_{c}" in K]
        text = "Expected structures by FEMA level: " + ", ".join(parts) + "."
        keys = [f"exp_{c}" for c in reversed(FEMA)]
        if "displaced" in K:
            text += f" About {_n(v('displaced'))} people may be displaced from assessed homes{rng('displaced')}."
            keys.append("displaced")
        items.append({"kind": "damage", "text": text, "evidence": ids(*keys)})

    if "roads_blocked" in K or "cut_plus_debris_b" in K:
        bits, keys = [], []
        if "roads_blocked" in K:
            s = f"{_n(v('roads_blocked'))} road segments are mapped as blocked"
            keys.append("roads_blocked")
            if "bridges" in K:
                s += f" and {_n(v('bridges'))} bridges are not yet verified"
                keys.append("bridges")
            bits.append(s + ".")
        if "cut_known_blocks_b" in K:
            kb = v("cut_known_blocks_b")
            bits.append(f"{_n(kb)} buildings (about {_n(v('cut_known_blocks_p'))} people) are cut off by known "
                        "road blocks." if kb else "No building is cut off by known road blocks alone.")
            keys += ["cut_known_blocks_b", "cut_known_blocks_p"]
        if "cut_plus_debris_b" in K:
            bits.append(f"If debris blocks the roads beside Destroyed buildings, {_n(v('cut_plus_debris_b'))} buildings "
                        f"(about {_n(v('cut_plus_debris_p'))} people) may be cut off.")
            keys += ["cut_plus_debris_b", "cut_plus_debris_p"]
        off = [e for k, e in K.items() if k.startswith("ll_") and k.count("_") >= 1 and e["label"].startswith(
            "Lifeline: ") and e["value"] != "Stable"]
        if "lifelines_off" in K and v("lifelines_off"):
            names = "; ".join(e["label"].removeprefix("Lifeline: ") + f" ({e['value'].lower()})" for e in off)
            bits.append(f"{_n(v('lifelines_off'))} of {_n(v('lifelines_total'))} lifelines are not stable: {names}.")
            keys += ["lifelines_off", "lifelines_total"]
        items.append({"kind": "access", "text": " ".join(bits),
                      "evidence": sorted(set(ids(*keys)) | {e["id"] for e in off}, key=lambda i: int(i[1:]))})
    elif "response_missing" in K or "response_stale" in K:
        k = "response_missing" if "response_missing" in K else "response_stale"
        items.append({"kind": "access", "text": "Road access, lifelines and landing zones have not been worked out "
                      "for this run yet. Build the response products to add them.", "evidence": ids(k)})

    if "sec1_sev" in K:
        s1 = K["sec1_sev"]
        text = (f"Start in priority sector 1 ({s1.get('locator')}): about {_n(v('sec1_sev'))} structures expected "
                f"Major or Destroyed and about {_n(v('sec1_ppl'))} people in them.")
        keys = ["sec1_sev", "sec1_ppl"]
        nxt = [f"sector {p} ({K[f'sec{p}_sev'].get('locator')}, about {_n(v(f'sec{p}_sev'))})"
               for p in (2, 3) if f"sec{p}_sev" in K]
        if nxt:
            text += " Then " + " and ".join(nxt) + "."
            keys += [f"sec{p}_sev" for p in (2, 3)]
        if "lz" in K:
            text += f" {_n(v('lz'))} landing zone candidates are mapped for reconnaissance, not approved for use."
            keys.append("lz")
        items.append({"kind": "search", "text": text, "evidence": ids(*keys)})
    elif meta["n_features"]:
        items.append({"kind": "search", "text": "No search sectors are ranked for this run. Start where the map shows "
                      "structures likely Destroyed or Major, then work outward.", "evidence": ids("severe")})

    bits, keys = [], []
    if "not_assessed" in K and v("not_assessed"):
        s = f"{_n(v('not_assessed'))} structures"
        if "not_assessed_res" in K:
            s += f" ({_n(v('not_assessed_res'))} homes"
            if "unassessed_people" in K:
                s += f", about {_n(v('unassessed_people'))} residents"
                keys.append("unassessed_people")
            s += ")"
            keys.append("not_assessed_res")
        bits.append(s + " had no footprint and were not assessed: treat them as unknown, never undamaged.")
        keys.append("not_assessed")
    if v("calibrated") == "no":
        bits.append("Damage probabilities are not yet calibrated on ground-truth labels, so the true spread is wider "
                    "than the ranges shown.")
        keys.append("calibrated")
    if "pair_gap" in K:
        bits.append(f"The pre-event and post-event images are {_n(v('pair_gap'))} days apart, so older changes can "
                    "read as damage.")
        keys.append("pair_gap")
    if v("occupancy") == "no":
        bits.append("Seasonal and vacant homes are counted as occupied, so people counts run high.")
        keys.append("occupancy")
    if bits:
        items.append({"kind": "unknown", "text": " ".join(bits), "evidence": ids(*keys)})

    bits, keys = [], []
    if "needs_review" in K:
        bits.append(f"{_n(v('needs_review'))} of {_n(v('assessed'))} assessed calls are flagged for human review "
                    "before use.")
        keys += ["needs_review", "assessed"]
    if "note_0" in K:
        bits.append(str(v("note_0")))
        keys.append("note_0")
    bits.append(SAFETY)
    items.append({"kind": "verify", "text": " ".join(bits), "evidence": ids(*keys)})
    for it in items:
        it["title"] = TITLES[it["kind"]]
        it["text"] = _clean(it["text"])
    return items[:6]


def _result(meta: dict, ev: list[dict], items: list[dict], written_by: str, model: str | None,
            tr: dict, **extra: Any) -> dict:
    return {"area": meta["area"], "run_id": meta["run_id"], "items": items, "evidence": ev,
            "written_by": written_by, "model": model, "traced": tr["traced"], "total": tr["total"],
            "untraced": tr["untraced"], "dropped": [], "ai_error": None, "ai_available": ai_status()[0],
            "generated_utc": _now(), "disclaimer": SAFETY, "notice": DISCLAIMER, **extra}


def rule_brief(area: str, out_dir: str | None = None) -> dict:
    """The default brief: fixed rules over the evidence list. Cached per area
    and per output run (run id plus the mtimes of the files read)."""
    ev, K, meta = _gather(area, out_dir)
    key = (area, "rules", _out(out_dir))
    hit = _cache.get(key)
    if hit and hit[0] == meta["fingerprint"]:
        return {**hit[1], "ai_available": ai_status()[0], "ai_error": None}
    items = _write_rules(K, meta)
    tr = _sum_traces([trace_item(i["text"], i["evidence"], ev) for i in items])
    res = _result(meta, ev, items, "rules", None, tr)
    _cache[key] = (meta["fingerprint"], res)
    return res


# --------------------------------------------------------------------------- #
# the Claude writer (optional)
# --------------------------------------------------------------------------- #
SYSTEM = (
    "You write the situation brief that an emergency operations center reads first after a disaster. "
    "You get a numbered evidence list (E1, E2, ...) of area-level facts from a satellite and aerial damage "
    "assessment. Write 4 to 6 short items, at most one per kind, in this order of kinds: headline, damage, "
    "access, search, unknown, verify. Leave out access or search when the evidence has nothing for it.\n"
    "Rules:\n"
    "- Use only figures that appear in the evidence, written as digits, either exactly or rounded to a whole "
    "number. No other numbers, no sums or percentages of your own, no numbers spelled out as words.\n"
    "- Cite in `evidence` the ids of every fact the item uses.\n"
    "- One or two plain sentences per item. Sentence case. No em dashes. No hype, no hedging filler.\n"
    "- Damage levels are FEMA's five, spelled exactly: No damage, Affected, Minor, Major, Destroyed.\n"
    "- Give ranges as 'range X to Y'. Structures not assessed are unknown, never undamaged.\n"
    "- Name search sectors only as 'priority sector 1', 'priority sector 2' and so on.\n"
    "- The verify item says what field teams should check first. This is decision support: "
    "everything is verified on the ground."
)
SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "text": {"type": "string", "description": "One or two plain sentences."},
            "evidence": {"type": "array", "items": {"type": "string"}, "description": "Evidence ids such as E1, E4."},
        },
        "required": ["kind", "text", "evidence"],
        "additionalProperties": False,
    }}},
    "required": ["items"],
    "additionalProperties": False,
}


class _AIError(Exception):
    pass


def ai_status() -> tuple[bool, str | None]:
    """(available, why not). Needs ANTHROPIC_API_KEY, a server that is not in
    offline mode, and the anthropic package."""
    from .offline import offline_mode

    if offline_mode():
        return False, "the server is running offline (NCR_OFFLINE=1)"
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return False, "no ANTHROPIC_API_KEY is set on the server"
    import importlib.util

    if importlib.util.find_spec("anthropic") is None:
        return False, "the anthropic package is not installed"
    return True, None


# no brief item needs the run timestamp, and its digits would let small
# invented numbers trace
_NOT_FOR_AI = {"Assessment generated (UTC)"}


def ai_payload(ev: list[dict]) -> list[dict]:
    """What Claude sees: id, label, value, unit, interval. Never `locator`
    (sector grid references) or the source file."""
    return [{k: e[k] for k in ("id", "label", "value", "unit", "interval") if e.get(k) is not None}
            for e in ev if e["label"] not in _NOT_FOR_AI]


def _client():
    import anthropic  # lazy: the app runs without it

    return anthropic.Anthropic(timeout=60.0, max_retries=1)


def _err(e: Exception) -> str:
    if isinstance(e, _AIError):
        return str(e)
    sc = getattr(e, "status_code", None)
    return type(e).__name__ + (f" (HTTP {sc})" if sc else "")


def _call(client, ev: list[dict]) -> tuple[list[dict], str]:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": "Evidence list (JSON):\n" + json.dumps(ai_payload(ev), indent=1)
                   + "\n\nWrite the brief."}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise _AIError(f"Claude stopped early ({resp.stop_reason})")
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), None)
    if not text:
        raise _AIError("Claude returned no text")
    data = json.loads(text)
    return list(data.get("items") or []), getattr(resp, "model", None) or MODEL


def ai_brief(area: str, out_dir: str | None = None, client=None) -> dict:
    """Claude writes the items from the evidence list alone; code traces every
    figure. Items with an untraced figure are dropped (listed in `dropped`);
    `traced` / `total` count every figure Claude wrote, each checked against
    the evidence its item cites (an item citing nothing traces nothing). Any failure returns
    the rules brief with `ai_error`. Only successful runs are cached."""
    ev, K, meta = _gather(area, out_dir)
    ok, why = ai_status()
    if client is not None:
        from .offline import offline_mode  # an injected client still obeys the gate

        if offline_mode():
            ok, why = False, "the server is running offline (NCR_OFFLINE=1)"
        elif not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            ok, why = False, "no ANTHROPIC_API_KEY is set on the server"
        else:
            ok, why = True, None
    if not ok:
        return {**rule_brief(area, out_dir), "ai_error": f"Claude is not available: {why}"}
    key = (area, "claude", _out(out_dir))
    with _ai_lock:
        hit = _cache.get(key)
        if hit and hit[0] == meta["fingerprint"]:
            return {**hit[1], "ai_available": True}
        try:
            raw, model = _call(client or _client(), ev)
            payload = ai_payload(ev)
            valid = {e["id"] for e in payload}
            items, dropped, traces = [], [], []
            seen: set[str] = set()
            for it in raw:
                kind = it.get("kind")
                text = _clean(str(it.get("text") or ""))
                cites = [i for i in (it.get("evidence") or []) if i in valid]
                t = trace_item(text, cites, payload)
                traces.append(t)
                reason = None
                if kind not in KINDS or kind in seen:
                    reason = "not one of the six kinds, or a second item of the same kind"
                elif not cites:
                    reason = "cites no evidence in the list"
                elif t["untraced"]:
                    reason = "figures not in the evidence it cites: " + ", ".join(t["untraced"])
                if reason:
                    dropped.append({"kind": kind, "text": text, "reason": reason})
                    continue
                seen.add(kind)
                items.append({"kind": kind, "title": TITLES[kind], "text": text, "evidence": cites})
            if not items:
                raise _AIError("no item Claude wrote could be traced to the evidence")
            items.sort(key=lambda i: KINDS.index(i["kind"]))
            items = items[:6]
            if not any(SAFETY in i["text"] for i in items):
                last = items[-1] if items[-1]["kind"] == "verify" else None
                if last:
                    last["text"] = f"{last['text']} {SAFETY}"
                else:
                    items.append({"kind": "verify", "title": TITLES["verify"], "text": SAFETY, "evidence": []})
            tr = _sum_traces(traces)
            res = _result(meta, ev, items, "claude", model, tr, dropped=dropped)
        except Exception as e:  # noqa: BLE001 - any failure falls back to rules, never a 500
            return {**rule_brief(area, out_dir), "ai_error": f"Claude could not write the brief: {_err(e)}"}
        _cache[key] = (meta["fingerprint"], res)
        return res


def sitbrief(area: str, ai: bool = False, out_dir: str | None = None) -> dict:
    return ai_brief(area, out_dir) if ai else rule_brief(area, out_dir)
