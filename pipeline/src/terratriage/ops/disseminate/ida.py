"""Initial damage assessment (IDA) packet: `run.py ops-ida --area X`.

What a state, tribe or county sends FEMA before a joint preliminary damage
assessment (PDA), built from one Groma run. It follows FEMA's Preliminary
Damage Assessment Guide (July 2025), which says an SLTT government "may use
Artificial Intelligence (AI) and machine learning" in its IDA and that FEMA
validates an IDA dataset exported "as either an Excel file or a Geospatial
Database file". Contents (exports/<area>_ida/):

  <area>_ida.xlsx        IA homes in FEMA survey fields, a summary, roads cut
                         (with reasons), a site-visit schedule, method and sources
  <area>_ida.gpkg        the same homes, inaccessible roads and sectors as layers
  <area>_pda_narrative.html  FEMA's PDA narrative report (Appendix F) and the IA
                         items of the joint PDA plan of action, pre-filled where
                         imagery can answer; every other item says so
  README.txt

Rules:
* A home's level is always its remote call. FEMA's "inaccessible" means no
  route to the home, so it is reported as a separate count and column, never
  in place of a damage level (the guide: "If the damage is viewable at the
  time of assessment, the appropriate damage category should be assigned").
* Questions imagery cannot answer (utilities out, shelters, fatalities,
  insurance, employers) are left for the local official, never guessed.
* Every page says whether Groma's calls have been measured for this hazard.
"""
from __future__ import annotations

import html
import json
import os
from collections import Counter, defaultdict
from typing import Any

from .. import DISCLAIMER, OPS_OUT
from ..analyze.classes import FEMA, FEMA_LABEL
from ..provenance import utc_now
from . import xlsx
from .exports import FEMA_IA_FIELDS, _flat, fema_ia_rows, state_name

PDA_GUIDE = "https://www.fema.gov/sites/default/files/documents/fema_rd_pda-guide_07012025.pdf"
LEVELS = ("destroyed", "major", "minor", "affected", "unaffected")
DWELLINGS = (("single_family", "Single family"), ("multi_family", "Multi-family"),
             ("manufactured_home", "Manufactured home"), ("", "Type unknown"))
ASK_LOCAL = "Not observed from imagery. To be completed by the local official."
FLOOD = ("riverine_flood", "flash_flood", "coastal_surge")


def _load(name: str) -> Any:
    p = os.path.join(OPS_OUT, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _hazards(fc: dict[str, Any], rsp: dict[str, Any] | None) -> list[str]:
    hz = list(((rsp or {}).get("summary") or {}).get("hazards") or [])
    if hz:
        return hz
    eid = ((fc.get("properties") or {}).get("event") or {}).get("id")
    try:
        from ..plan.events import load_events

        ev = load_events().get(eid)
        return list(getattr(ev, "hazards", []) or [])
    except Exception:  # noqa: BLE001 - the packet still builds without the registry
        return []


TAIL = {
    "state": ("Validate before relying on counts.",
              "Treat these counts as a starting point for the joint PDA, not as validated figures."),
    "owner": ("Treat this call as a starting point, not a confirmed finding.",
              "Treat this call as a starting point, not a confirmed finding."),
    "public": ("Treat these counts as preliminary.", "Treat these counts as preliminary, not as validated figures."),
}


def validation_note(hazards: list[str], audience: str = "state") -> str:
    """What has, and has not, been measured for this hazard. Figures from
    docs/model/MODEL_CARD.md (pre-registered Eaton hold-out, 2,246 buildings)."""
    if "wildfire" in hazards:
        return ("Wildfire: Groma's wildfire image model was scored once on a held-out fire (Eaton, 2025) against "
                "CAL FIRE inspections: for Major or Destroyed, precision 0.957 and recall 0.942 on 2,246 buildings. "
                "The middle levels (Affected, Minor) are weaker, and the full pipeline has not yet been scored on a "
                "new fire. " + TAIL[audience][0])
    from ..hazards import label

    names = ", ".join(label(h) for h in hazards) or "this hazard"
    which = "these hazards" if len(hazards) > 1 else "this hazard"
    return (f"{names[:1].upper()}{names[1:]}: Groma's damage calls have not been validated against field records "
            f"for {which}. " + TAIL[audience][1])


def _streets(layers: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Roads in the response layer that cut access, one row per named road."""
    by: dict[str, dict[str, Any]] = {}
    for f in (layers or {}).get("features") or []:
        p = f.get("properties") or {}
        if p.get("layer") != "road" or p.get("status") not in ("blocked", "debris", "bridge"):
            continue
        name = (p.get("name") or "").strip() or f"Unnamed {p.get('highway') or 'road'} ({p.get('way')})"
        r = by.setdefault(name, {"street": name, "status": set(), "reasons": set(), "segments": 0,
                                 "highway": p.get("highway"), "lon": None, "lat": None})
        r["status"].add(p["status"])
        r["reasons"].update(p.get("why") or [])
        r["segments"] += 1
        if r["lon"] is None:
            (x0, y0), (x1, y1) = f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][-1]
            r["lon"], r["lat"] = round((x0 + x1) / 2, 6), round((y0 + y1) / 2, 6)
    rank = {"blocked": 0, "debris": 1, "bridge": 2}
    out = []
    for r in by.values():
        st = sorted(r["status"], key=rank.get)
        out.append({**r, "status": st[0], "reasons": "; ".join(sorted(r["reasons"])),
                    "confirmed": st[0] == "blocked"})
    return sorted(out, key=lambda r: (rank[r["status"]], -r["segments"], r["street"]))


def build(area: str, out_dir: str | None = None) -> dict[str, Any]:
    fc = _load(f"{area}.geojson")
    if fc is None:
        raise FileNotFoundError(f"no assessment for {area}")
    if not fc["features"]:
        raise ValueError("this assessment found no structures, so there is no IDA to build")
    responder = (_load(f"{area}.responder.json") or {}).get("structures") or {}
    rsp = _load(f"{area}.response.json")
    layers = _load(f"{area}.response.layers.json")
    run = fc["properties"]
    ev = run.get("event") or {}
    aoi = run.get("aoi") or {}
    hazards = _hazards(fc, rsp)
    defaults = next((f["properties"]["fema"] for f in fc["features"] if f["properties"].get("fema")), {})
    flat = [_flat(f["properties"], responder, defaults) for f in fc["features"]]
    ia, ia_feats, non_homes = fema_ia_rows(fc, flat)
    props = {f["properties"]["ncr_id"]: f["properties"] for f in fc["features"]}

    acc = (rsp or {}).get("access") or {}
    iso = acc.get("isolated_ids")
    known = set((iso or {}).get("known_blocks") or [])
    debris = set((iso or {}).get("plus_debris") or []) - known
    for r in ia:
        if iso is None:
            r["ncr_access"] = "not computed"
        elif r["ncr_id"] in known:
            r["ncr_access"] = "inaccessible: no road out"
        elif r["ncr_id"] in debris:
            r["ncr_access"] = "inaccessible if debris blocks roads"
        else:
            r["ncr_access"] = "road access"

    # counts by level and dwelling (most likely level, as FEMA counts homes)
    by = Counter((r["level_of_damage_assessed"] or "not_assessed", r["choose_the_type_of_dwelling"]) for r in ia)
    expected = defaultdict(float)
    for r in ia:
        for c in FEMA:
            expected[c] += (props[r["ncr_id"]].get("damage_probs") or {}).get(c) or 0.0
    lvl_total = {lv: sum(n for (l2, _d), n in by.items() if l2 == lv) for lv in LEVELS + ("not_assessed",)}
    inacc_known = sum(r["ncr_access"] == "inaccessible: no road out" for r in ia)
    inacc_debris = sum(r["ncr_access"] == "inaccessible if debris blocks roads" for r in ia)
    severe_mh = sum(n for (lv, d), n in by.items() if d == "manufactured_home" and lv in ("major", "destroyed"))
    severe = lvl_total["major"] + lvl_total["destroyed"]
    review = sum(r["ncr_needs_review"] == "yes" for r in ia)
    business = Counter(p.get("damage_level") for p in props.values()
                       if str(p.get("occupancy") or "").upper().startswith(("COM", "IND", "AGR"))
                       and p.get("damage_level") in ("affected", "minor", "major", "destroyed"))
    streets = _streets(layers)
    sectors = sorted((rsp or {}).get("sectors") or [], key=lambda s: s.get("priority", 99))
    clusters = acc.get("isolated_clusters") or []
    img_dates = sorted({r["collection_date"] for r in ia if r.get("collection_date")})
    img_range = defaults.get("IMG_DATE_RANGE")
    note = validation_note(hazards)
    state = state_name(fc)
    generated = utc_now()

    d = out_dir or os.path.join(OPS_OUT, "exports", f"{area}_ida")
    os.makedirs(d, exist_ok=True)
    paths: dict[str, str] = {}

    # ---- spreadsheet ----
    ia_cols = list(FEMA_IA_FIELDS) + ["ncr_id", "ncr_access", "ncr_assessment_type", "ncr_probability",
                                      "ncr_needs_review", "ncr_usng_10m", "ncr_lat", "ncr_lon"]
    summary_rows: list[list[Any]] = [["Homes assessed (residential structures)", len(ia), "count"]]
    for lv in LEVELS:
        summary_rows.append([f"Homes {FEMA_LABEL.get(lv if lv != 'unaffected' else 'no_damage')}", lvl_total[lv],
                             "most likely level from imagery"])
    summary_rows.append(["Homes in the inventory but not assessed", lvl_total["not_assessed"],
                         "no footprint seen in the imagery: unknown, not undamaged"])
    for c in ("destroyed", "major", "minor", "affected"):
        summary_rows.append([f"Expected homes {FEMA_LABEL[c]} (sum of probabilities)", round(expected[c], 1),
                             "use as the central estimate"])
    summary_rows += [
        ["Homes inaccessible (no road out, known blocks)", inacc_known if iso is not None else None,
         "FEMA definition: no route to the home" if iso is not None else "run the response products first"],
        ["Homes inaccessible if debris blocks roads", inacc_debris if iso is not None else None, "possible, not confirmed"],
        ["Manufactured homes Major or Destroyed", severe_mh, "most likely level"],
        ["Homes to verify first (needs review)", review, "uncertain or severe calls"],
        ["Businesses with any damage (commercial, industrial, agricultural)", sum(business.values()),
         "occupancy from USACE NSI"],
        ["Non-residential structures left out of the IA rows", non_homes, ""],
        ["Imagery dates", ", ".join(img_dates) or img_range or "unknown", ""],
        ["Validation", note, ""],
    ]
    by_type = [[lab] + [by.get((lv, code), 0) for lv in LEVELS] + [sum(by.get((lv, code), 0) for lv in LEVELS)]
               for code, lab in DWELLINGS]
    street_rows = [[s["street"], {"blocked": "Blocked", "debris": "Possible: debris",
                                  "bridge": "Possible: bridge not verified"}[s["status"]],
                    s["reasons"], s["highway"], s["segments"], s["lat"], s["lon"]] for s in streets]
    sched = [[i + 1, s.get("usng_1km"), s.get("buildings"), s.get("major_or_destroyed_expected"),
              s.get("people_in_severe_expected"), s.get("cut_off_buildings"), s.get("needs_review"),
              (s.get("center") or [None, None])[1], (s.get("center") or [None, None])[0]]
             for i, s in enumerate(sectors)]
    method = [
        ["Method", "Remote assessment from before and after imagery, building footprints, lidar and field "
                   "records where available; each home's level is the most likely of FEMA's five levels."],
        ["Validation", note],
        ["Verification", "Uncertain and severe calls are flagged (ncr_needs_review = yes) for blind review "
                         "and field verification before they are relied on."],
        ["Inaccessible", "From OpenStreetMap roads: a home is inaccessible when no road path leaves the area "
                         "with mapped landslides or reported closures removed. Debris and unverified bridges "
                         "are a second, possible scenario."],
        ["Event", f"{ev.get('name') or ''} ({', '.join(ev.get('declarations') or [])})"],
        ["Area", f"{aoi.get('id') or area}, {aoi.get('county') or ''} County, {state}".strip(", ")],
        ["Run", run.get("run_id")], ["Generated", generated],
        ["FEMA guide", PDA_GUIDE], ["Disclaimer", DISCLAIMER],
    ]
    paths["xlsx"] = xlsx.write(os.path.join(d, f"{area}_ida.xlsx"), [
        ("IA homes", ia_cols, [[r.get(c) for c in ia_cols] for r in ia]),
        ("Summary", ["Item", "Value", "Note"], summary_rows),
        ("Homes by type", ["Dwelling type"] + [FEMA_LABEL.get(lv if lv != "unaffected" else "no_damage")
                                               for lv in LEVELS] + ["Total"], by_type),
        ("Roads cut", ["Street", "Status", "Reasons", "Road class", "Segments", "Lat", "Lon"], street_rows),
        ("Site visit schedule", ["Order", "USNG 1 km", "Buildings", "Expected Major or Destroyed",
                                 "People in severe homes (expected)", "Buildings cut off", "Needs review",
                                 "Lat", "Lon"], sched),
        ("Method and sources", ["Item", "Detail"], method),
    ])

    # ---- geopackage ----
    try:
        import geopandas as gpd
        from shapely.geometry import LineString, Point

        p = os.path.join(d, f"{area}_ida.gpkg")
        if os.path.exists(p):
            os.remove(p)
        if ia:
            g = gpd.GeoDataFrame([{c: r.get(c) for c in ia_cols} for r in ia],
                                 geometry=[Point(r["ncr_lon"], r["ncr_lat"]) for r in ia], crs="EPSG:4326")
            g.astype({c: "string" for c in g.columns if c != "geometry" and g[c].dtype == object}) \
             .to_file(p, layer="ia_homes", driver="GPKG")
        roads = [f for f in (layers or {}).get("features") or []
                 if (f.get("properties") or {}).get("layer") == "road"
                 and f["properties"].get("status") in ("blocked", "debris", "bridge")]
        if roads:
            gpd.GeoDataFrame([{"street": f["properties"].get("name") or "", "status": f["properties"]["status"],
                               "reasons": "; ".join(f["properties"].get("why") or []),
                               "highway": f["properties"].get("highway") or ""} for f in roads],
                             geometry=[LineString(f["geometry"]["coordinates"]) for f in roads],
                             crs="EPSG:4326").to_file(p, layer="inaccessible_roads", driver="GPKG")
        if sectors:
            gpd.GeoDataFrame([{"order": i + 1, "usng_1km": s.get("usng_1km"),
                               "major_or_destroyed_expected": s.get("major_or_destroyed_expected"),
                               "cut_off_buildings": s.get("cut_off_buildings")} for i, s in enumerate(sectors)],
                             geometry=[Point(*s["center"]) for s in sectors], crs="EPSG:4326") \
                .to_file(p, layer="site_visit_sectors", driver="GPKG")
        if os.path.exists(p):
            paths["gpkg"] = p
    except Exception as ex:  # noqa: BLE001 - the spreadsheet is the required format
        print(f"[ida] {area}: GeoPackage skipped ({str(ex)[:120]})")

    # ---- narrative ----
    facts = {"homes": len(ia), "lvl": lvl_total, "expected": dict(expected), "inacc_known": inacc_known,
             "inacc_debris": inacc_debris, "iso_computed": iso is not None, "severe": severe,
             "severe_mh": severe_mh, "review": review, "business": dict(business), "streets": streets,
             "sectors": sectors, "clusters": clusters, "by": by, "hazards": hazards, "note": note,
             "img": ", ".join(img_dates) or img_range or "unknown", "needs": (rsp or {}).get("needs") or {},
             "impact": _load(f"{area}.impact.json") or {}, "props": props}
    p = os.path.join(d, f"{area}_pda_narrative.html")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(narrative_html(area, run, state, generated, facts))
    paths["narrative"] = p

    with open(os.path.join(d, "README.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"Groma IDA packet: {area}\n\n{DISCLAIMER}\n\n{note}\n\n"
                 "Contains street addresses. Share with emergency management only; do not post publicly.\n\n"
                 f"{area}_ida.xlsx: IA homes in FEMA survey fields (sheet 'IA homes'), summary counts, homes by "
                 "type, roads cut, site visit schedule, method and sources.\n"
                 f"{area}_ida.gpkg: the same as GIS layers (ia_homes, inaccessible_roads, site_visit_sectors).\n"
                 f"{area}_pda_narrative.html: FEMA's PDA narrative report and the IA plan of action items, "
                 "pre-filled where imagery can answer. Print or save as PDF from a browser.\n\n"
                 f"Built from run {run.get('run_id')} on {generated}. FEMA PDA guide: {PDA_GUIDE}\n")
    paths["readme"] = os.path.join(d, "README.txt")
    print(f"[ida] {area}: {len(ia)} homes, {severe} Major or Destroyed, {len(streets)} streets -> {d}")
    return {"dir": d, "files": paths, "homes": len(ia), "levels": lvl_total,
            "inaccessible": inacc_known if iso is not None else None, "validation": note}


def _n(k: int, one: str, many: str | None = None) -> str:
    return f"{k} {one if k == 1 else (many or one + 's')}"


def _e(v: Any) -> str:
    return html.escape(str(v), quote=True)


def narrative_html(area: str, run: dict[str, Any], state: str, generated: str, f: dict[str, Any]) -> str:
    ev, aoi = run.get("event") or {}, run.get("aoi") or {}
    lvl = f["lvl"]
    flood = any(h in FLOOD for h in f["hazards"])
    from ..hazards import label

    hz = ", ".join(label(h) for h in f["hazards"]) or "not recorded"
    top = f["sectors"][:5]
    conc = "; ".join(f"USNG {s['usng_1km']}: about {s['major_or_destroyed_expected']:g} of {_n(s['buildings'], 'building')} "
                     "expected Major or Destroyed" for s in top) or "No sector ranking (response products not run)."
    remote = ("If every bridge in the area were out, these groups would have no road out: "
              + "; ".join(f"{_n(c['buildings'], 'building')} near USNG {c['usng']}" for c in f["clusters"][:5])
              + ".") if f["clusters"] else ""
    blocked = [s for s in f["streets"] if s["confirmed"]]
    named = [s for s in blocked if not s["street"].startswith("Unnamed ")]
    unnamed = len(blocked) - len(named)
    inacc_txt = ("Roads cut: " + "; ".join(f"{s['street']} ({s['reasons']})" for s in named[:12])
                 if named else "No mapped landslide or reported closure cuts a named road in this area.")
    if len(named) > 12:
        inacc_txt += f"; and {len(named) - 12} more named roads"
    if unnamed:
        inacc_txt += f"; plus {_n(unnamed, 'unnamed driveway or service road', 'unnamed driveways or service roads')}"
    inacc_txt += ". Full list in the spreadsheet."
    by = f["by"]
    types = ", ".join(f"{lab.lower()} {sum(by.get((lv, code), 0) for lv in LEVELS)}" for code, lab in DWELLINGS)
    stories = Counter(int(p.get("stories")) for p in f["props"].values() if p.get("stories"))
    found = Counter(str(p.get("foundation_type")) for p in f["props"].values() if p.get("foundation_type"))
    struct_txt = (f"Homes by type: {types}."
                  + (f" Stories (USACE NSI): " + ", ".join(f"{k}: {v}" for k, v in sorted(stories.items())) + "."
                     if stories else "")
                  + (f" Foundation codes (USACE NSI): " + ", ".join(f"{k}: {v}" for k, v in found.most_common(4)) + "."
                     if found else ""))
    mh_total = sum(by.get((lv, "manufactured_home"), 0) for lv in LEVELS)
    mh_txt = (f"{f['severe_mh']} of {mh_total} manufactured homes are called Major or Destroyed."
              if mh_total else "No manufactured homes in the inventory for this area.")
    bus = f["business"]
    bus_txt = (f"{sum(bus.values())} commercial, industrial or agricultural structures show damage "
               f"({', '.join(f'{FEMA_LABEL[k]} {v}' for k, v in sorted(bus.items(), key=lambda kv: FEMA.index(kv[0])))})."
               " Employer names are not in the data." if bus else "No damaged commercial structures detected.")
    disp = (f.get("needs") or {}).get("people_displaced_expected")
    disp_txt = (f"About {disp} people expected displaced (homes Major or Destroyed, occupants from USACE NSI). "
                "Where they are staying: " + ASK_LOCAL) if disp is not None else ASK_LOCAL
    svi = [t.get("svi_percentile") for t in (f["impact"].get("tracts") or []) if t.get("svi_percentile") is not None]
    spec_txt = (f"CDC Social Vulnerability Index for the affected tracts: {', '.join(f'{v:.2f}' for v in svi[:6])} "
                "(percentile; higher is more vulnerable). " + ASK_LOCAL) if svi else ASK_LOCAL
    trend = (f"{hz}. Of {f['homes']} homes, {lvl['destroyed']} Destroyed, {lvl['major']} Major, {lvl['minor']} Minor, "
             f"{lvl['affected']} Affected, {lvl['unaffected']} without visible damage and {lvl['not_assessed']} not "
             "assessed (most likely level from imagery).")
    if flood:
        trend += (" Interior flood damage does not show from above, so homes between Minor and Major are candidates "
                  "for a field check.")
    items = [
        ("Event type and description of damage trends observed", trend),
        ("Issues related to sewer backup", ASK_LOCAL),
        ("Areas with utilities out; projected date of restoration", ASK_LOCAL),
        ("Areas of concentrated damage", conc),
        ("Remote areas", remote or "No groups of buildings without a road out were found."),
        ("Major inaccessible areas and reasons", inacc_txt),  # roads cut; homes with another route are not inaccessible
        ("Types of structures surveyed", struct_txt),
        ("Prevalence of damage to manufactured homes or mobile home parks", mh_txt),
        ("Number of businesses impacted", bus_txt),
        ("Names of major employers impacted", ASK_LOCAL),
        ("Other factors that impact tax base", ASK_LOCAL),
        ("Agricultural impact", ASK_LOCAL),
        ("Are there currently shelters open?", ASK_LOCAL),
        ("Estimated number of displaced households and where they are staying", disp_txt),
        ("Sufficient housing and rental resources for the displaced?", ASK_LOCAL),
        ("Local and VOAD activities and agency resources available", ASK_LOCAL),
        ("Significant need for counseling services?", ASK_LOCAL),
        ("Impact on special populations", spec_txt),
        ("Tribal Nations impacted", ASK_LOCAL),
        ("Storm-related fatalities and injuries", ASK_LOCAL),
        ("All other factors affecting the area", ASK_LOCAL),
    ]
    rows = "".join(f'<tr><th scope="row">{i}</th><td><b>{_e(q)}</b><p class="{"ask" if a == ASK_LOCAL else ""}">'
                   f"{_e(a)}</p></td></tr>" for i, (q, a) in enumerate(items, start=1))
    counts = "".join(f"<tr><td>{_e(FEMA_LABEL[c])}</td><td>{lvl[c]}</td><td>{f['expected'].get(c, 0):.1f}</td></tr>"
                     for c in ("destroyed", "major", "minor", "affected"))
    inacc_line = (f"{f['inacc_known']} homes have no road out with known blocks; {f['inacc_debris']} more would be "
                  "cut off if debris also blocks roads." if f["iso_computed"] else
                  "Not computed for this run: run the response products (Respond tab) and rebuild the packet.")
    street_li = "".join(f"<li>{_e(s['street'])}: {_e(s['reasons'])}</li>" for s in named[:40])
    if unnamed:
        street_li += f"<li>{_e(_n(unnamed, 'unnamed driveway or service road', 'unnamed driveways or service roads'))}, listed in the spreadsheet</li>"
    street_li = street_li or "<li>None confirmed. Possible blocks (debris, unverified bridges) are in the spreadsheet.</li>"
    sched_li = "".join(f"<li>USNG {_e(s['usng_1km'])}: {s['major_or_destroyed_expected']:g} expected Major or "
                       f"Destroyed, {s['cut_off_buildings']} cut off, {s['needs_review']} to verify</li>"
                       for s in f["sectors"]) or "<li>Run the response products for a ranked schedule.</li>"
    title = f"Initial damage assessment: {(aoi.get('id') or area).replace('_', ' ').title()}"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_e(title)}</title>
<style>
body{{font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:#1b1814;max-width:52rem;margin:2rem auto;padding:0 1.2rem}}
h1{{font-size:1.6rem;margin:0 0 .3rem}} h2{{font-size:1.15rem;margin:2rem 0 .6rem;border-bottom:1px solid #d9d2c4;padding-bottom:.3rem}}
.meta{{color:#5b544a;font-size:.9rem}} .warn{{background:#fbf3e4;border-left:4px solid #9a6630;padding:.7rem .9rem;margin:1rem 0}}
table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;vertical-align:top;padding:.45rem .5rem;border-bottom:1px solid #e6e0d4}}
th[scope=row]{{width:2.2rem;color:#5b544a;font-weight:500}} td p{{margin:.2rem 0 0}} .ask{{color:#7a7064}}
@media print{{body{{margin:0;max-width:none}} .warn{{break-inside:avoid}} tr{{break-inside:avoid}}}}
</style></head><body>
<h1>{_e(title)}</h1>
<p class="meta">{_e(ev.get('name') or '')} · {_e(', '.join(ev.get('declarations') or []))} · {_e(aoi.get('county') or '')} County, {_e(state)} · imagery {_e(f['img'])} · generated {_e(generated)} · run {_e(run.get('run_id') or '')}</p>
<p class="warn"><b>Remote assessment.</b> {_e(f['note'])} {_e(DISCLAIMER)}</p>

<h2>Joint PDA plan of action: Individual Assistance items</h2>
<p><b>Methodology for validating degree of damage.</b> Groma's remote calls from imagery, with {f['review']} homes flagged to verify first. Validate the flagged homes and a sample of the rest door to door or by windshield survey, highest sectors first.</p>
<table><thead><tr><th>Level</th><th>Homes (most likely level)</th><th>Expected (sum of probabilities)</th></tr></thead><tbody>{counts}</tbody></table>
<p><b>Homes inaccessible.</b> {_e(inacc_line)}</p>
<p><b>Roads with a mapped landslide or reported closure.</b> Homes on them may still have another route; only homes with no route out count as inaccessible above. Possible blocks (debris, unverified bridges) are in the spreadsheet.</p><ul>{street_li}</ul>
<p><b>Streets that have lost utility services:</b> {ASK_LOCAL}</p>
<p><b>Schedule and route:</b> sectors in order, most heavily impacted first.</p><ol>{sched_li}</ol>

<h2>PDA narrative report (FEMA PDA guide, Appendix F)</h2>
<table><tbody>{rows}</tbody></table>
<p class="meta">Built by Groma from public imagery, building inventories and OpenStreetMap roads. FEMA PDA guide: {_e(PDA_GUIDE)}</p>
</body></html>
"""
