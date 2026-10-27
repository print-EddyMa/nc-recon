"""One-page situation brief: `run.py ops-brief --area X` -> exports/<area>/<area>_brief.html

Self-contained, printable (Save as PDF from any browser), no external requests,
no addresses. Sections: BLUF, map, structures by level with 80% ranges,
people and need by tract, data gaps and confidence, sources with timestamps,
disclaimer. A plain-text twin (`_brief.txt`) is written for low-bandwidth
relay (radio / SMS / email).
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone

from .. import DISCLAIMER, OPS_OUT
from ..analyze.classes import FEMA, FEMA_LABEL
from .exports import COLORS



def _svg_map(fc: dict, w: int = 640, h: int = 420) -> str:
    pts = [f["properties"]["centroid"] for f in fc["features"]]
    if not pts:
        return '<p class="meta">No map: no structures were found in this area.</p>'
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    import math

    kx = math.cos(math.radians((y0 + y1) / 2))
    sx = (x1 - x0) * kx or 1e-6
    sy = (y1 - y0) or 1e-6
    s = min((w - 20) / sx, (h - 20) / sy)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Map of assessed structures">',
           f'<rect width="{w}" height="{h}" fill="#f7f6f2"/>']
    order = sorted(fc["features"], key=lambda f: FEMA.index(f["properties"]["damage_level"])
                   if f["properties"]["damage_level"] else -1)
    for f in order:
        p = f["properties"]
        cx = 10 + (p["centroid"][0] - x0) * kx * s
        cy = h - 10 - (p["centroid"][1] - y0) * s
        col = COLORS.get(p["damage_level"], COLORS[None])
        r = 1.6 if p["damage_level"] in (None, "no_damage") else 2.6
        stroke = ' stroke="#2563eb" stroke-width="0.9"' if p.get("needs_review") and p["damage_level"] else ""
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{col}"{stroke}/>')
    # scale bar: 500 m
    m_per_deg = 111_320 * kx
    bar = 500 / m_per_deg * kx * s
    out.append(f'<line x1="14" y1="{h - 14}" x2="{14 + bar:.1f}" y2="{h - 14}" stroke="#222" stroke-width="2"/>'
               f'<text x="14" y="{h - 20}" font-size="10" fill="#222">500 m</text></svg>')
    return "".join(out)


def brief(area: str) -> str:
    with open(os.path.join(OPS_OUT, f"{area}.geojson"), encoding="utf-8") as fh:
        fc = json.load(fh)
    imp_p = os.path.join(OPS_OUT, f"{area}.impact.json")
    imp = json.load(open(imp_p, encoding="utf-8")) if os.path.exists(imp_p) else None
    P = fc["properties"]
    ec, rng = P["expected_counts"], P.get("expected_counts_80pct") or {}
    sev = ec["major"] + ec["destroyed"]
    sev_lo = sum((rng.get(c) or [0, 0])[0] for c in ("major", "destroyed"))
    sev_hi = sum((rng.get(c) or [0, 0])[1] for c in ("major", "destroyed"))
    assessed = P["n_structures"] - P["not_assessed"]["total"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # operational area ids end in a random 4-hex suffix ("marion_df23"): not part of the name
    stem = re.sub(r"_[0-9a-f]{4}$", "", area) if P["aoi"].get("role") == "OPS" else area
    name = P["aoi"].get("name") or stem.replace("_", " ").title()
    from ..counties import county_of

    county = P["aoi"].get("county") or county_of(f["properties"].get("cbfips_2010") for f in fc["features"])
    where = html.escape(f"{name} ({county} Co.)" if county else name)
    bluf = (f"{where}: about <b>{round(sev)}</b> of {assessed:,} assessed "
            f"structures are likely Major or Destroyed (80% range {sev_lo}-{sev_hi}). "
            f"{P['n_needs_review']:,} calls need human verification before use.")
    if not fc["features"]:
        bluf = (f"{where}: <b>no structures</b> were found in this area in FEMA USA Structures, "
                "OpenStreetMap or the USACE National Structure Inventory, so there is nothing to assess. "
                "If buildings are known to be here, the inventories are incomplete: verify on the ground.")
    if imp and imp.get("expected_displaced"):
        d = imp["expected_displaced"]
        ua = imp.get("unassessed_residential") or {}
        bluf += (f" Roughly <b>{round(d['median'])}</b> people may be displaced "
                 f"({round(d['p10'])}-{round(d['p90'])}) from assessed homes; another "
                 f"{ua.get('structures', 0)} homes (~{round(ua.get('occupants_nsi', 0))} residents) could not be "
                 "assessed. Seasonal homes are " + ("not " if "UNADJUSTED" in imp["occupancy_adjustment"] else "")
                 + "adjusted for.")
    rows = "".join(
        f'<tr><td><span class="sw" style="background:{COLORS[c]}"></span>{FEMA_LABEL[c]}</td>'
        f'<td class="n">{round(ec[c])}</td><td class="n">{"-".join(map(str, rng.get(c, [])))}</td></tr>'
        for c in FEMA)
    tracts = ""
    if imp:
        tracts = "".join(
            f'<tr><td>{html.escape((t.get("location") or t["tract"]).split(";")[0])}</td>'
            f'<td class="n">{t["expected_displaced"]}</td><td class="n">'
            f'{"n/a" if t["svi_percentile"] is None else f"{t["svi_percentile"]:.2f}"}</td>'
            f'<td class="n">{t["need_index"] if t["need_index"] is not None else "n/a"}</td></tr>'
            for t in imp["tracts"][:6])
    gaps = [html.escape(w) for w in P.get("warnings", [])] + [html.escape(r) for r in P["pair_context"]["reasons"]]
    unavail: dict[str, int] = {}
    for f in fc["features"]:
        for k, v in (f["properties"].get("evidence_unavailable") or {}).items():
            unavail[f"{k}: {v}"] = unavail.get(f"{k}: {v}", 0) + 1
    gaps += [f"{html.escape(k)} ({n:,} structures)" for k, n in sorted(unavail.items(), key=lambda kv: -kv[1])[:6]]
    srcs = []
    prov = P.get("provenance") or {}
    for i in prov.get("imagery", []):
        srcs.append(f"Imagery ({i.get('role')}): {html.escape(str(i.get('source')))}, "
                    f"{html.escape(str(i.get('acquired_utc') or i.get('date_label') or i.get('dataset_version') or ''))}")
    for fsrc in prov.get("footprints", []):
        srcs.append(f"Footprints: {html.escape(fsrc['source'])} ({fsrc.get('count')})")
    st = prov.get("structures") or {}
    if st:
        srcs.append(f"Structure attributes: {html.escape(st.get('source', ''))} ({html.escape(str(st.get('dataset_version')))})")
    srcs.append(f"Declaration: {', '.join(P['event']['declarations'])} (OpenFEMA), incident began {P['event']['incident_begin']}")
    srcs.append(f"Run {P['run_id']}, generated {P['generated_utc']}")
    calib = "uncalibrated (no ground-truth labels yet)" if P["calibration"].get("cnn") == "none" else "calibrated on TUNE labels"
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Situation brief: {html.escape(name)}</title>
<style>
body{{font:13px/1.45 Georgia,serif;color:#1c1d21;max-width:760px;margin:24px auto;padding:0 16px}}
h1{{font-size:20px;margin:0}} h2{{font-size:14px;margin:18px 0 6px;border-bottom:1px solid #ddd}}
.meta{{color:#555;font:12px system-ui,sans-serif}} .bluf{{background:#fff8e6;border-left:4px solid #bd0026;padding:8px 10px}}
table{{border-collapse:collapse;width:100%;font:12px system-ui,sans-serif}} td,th{{padding:3px 6px;border-bottom:1px solid #eee;text-align:left}}
.n{{text-align:right;font-variant-numeric:tabular-nums}} .sw{{display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:middle}}
.disc{{font:12px system-ui,sans-serif;border:1px solid #bd0026;padding:6px 8px;margin-top:14px}}
ul{{font:12px system-ui,sans-serif;padding-left:18px}}
.print{{float:right;font:13px system-ui,sans-serif;padding:5px 10px;border:1px solid #888;border-radius:6px;background:#fff;cursor:pointer}}
@media print{{body{{margin:0}} .print{{display:none}}}}
</style></head><body>
<button class="print" type="button" onclick="window.print()">Print or save as PDF</button>
<h1>Situation brief: {html.escape(name)}</h1>
<div class="meta">{html.escape(P['event']['name'])} · {', '.join(P['event']['declarations'])} · AOI role {P['aoi']['role']} · {now}</div>
<div class="disc">{html.escape(DISCLAIMER)}</div>
<h2>Bottom line</h2><p class="bluf">{bluf}</p>
<h2>Map</h2>{_svg_map(fc)}
<p class="meta">Dots = structures, coloured by most likely FEMA level (grey = no damage, dark = not assessed); blue ring = needs review.</p>
<h2>Structures by damage level</h2>
<table><tr><th>Level</th><th class="n">Expected</th><th class="n">80% range*</th></tr>{rows}</table>
<p class="meta">* Ranges reflect sampling from the per-structure probabilities and are conditional on them; the probabilities are not yet calibrated, so true uncertainty is wider.</p>
<p class="meta">{P['not_assessed']['total']:,} inventory structures had no footprint and were not assessed ({P['not_assessed']['residential']} residential). Probabilities are {calib}.</p>
{"<h2>People and need by census tract</h2><table><tr><th>Tract</th><th class='n'>Displaced (exp.)</th><th class='n'>SVI</th><th class='n'>Need index</th></tr>" + tracts + "</table><p class='meta'>Need index = expected displaced x (1 + SVI percentile). Prioritization aid, not an eligibility determination. Road-isolation and power-outage terms not yet included.</p>" if imp else ""}
<h2>Data gaps and confidence</h2><ul>{"".join(f"<li>{g}</li>" for g in gaps)}</ul>
<h2>Sources</h2><ul>{"".join(f"<li>{s}</li>" for s in srcs)}</ul>
</body></html>"""
    d = os.path.join(OPS_OUT, "exports", area)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{area}_brief.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    txt = [f"SITUATION BRIEF {name.upper()} {now}", DISCLAIMER,
           html.unescape(bluf.replace("<b>", "").replace("</b>", "")),
           "LEVELS (expected / 80%): " + "; ".join(f"{FEMA_LABEL[c]} {round(ec[c])} ({'-'.join(map(str, rng.get(c, [])))})" for c in FEMA),
           f"NEEDS REVIEW: {P['n_needs_review']}  NOT ASSESSED: {P['not_assessed']['total']}",
           f"RUN {P['run_id']}"]
    with open(os.path.join(d, f"{area}_brief.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(txt) + "\n")
    return path
