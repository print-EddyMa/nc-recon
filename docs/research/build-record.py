"""Condense the research workflow journal into one record for the planning agents."""
import json, os, sys
D = "/Users/eddyma/.claude/projects/-Users-eddyma-terratriage/50863b85-0b86-4738-b859-b22f6e31561a/subagents/workflows/wf_b90917ea-8e2/journal.jsonl"
S = os.path.dirname(os.path.abspath(__file__))
rows = [json.loads(l) for l in open(D) if l.strip()]
dims, verdicts, critic = [], [], None
for r in rows:
    if r.get("type") != "result" or not isinstance(r.get("result"), dict):
        continue
    res = r["result"]
    if "sources" in res and "dimension" in res:
        dims.append(res)
    elif "verdict" in res:
        verdicts.append(res)
    elif "missing_sources" in res:
        critic = res
vmap = {}
for v in verdicts:
    vmap[(v.get("key"), v.get("name"))] = v
    vmap.setdefault(("*", v.get("name")), v)
record = {"dimensions": [], "critic": critic, "counts": {"sources": 0, "high": 0, "verified": len(verdicts)}}
for d in dims:
    key = d.get("key")
    out = {"key": key, "dimension": d.get("dimension"), "sources": [], "insights": d.get("insights", []), "gaps": d.get("gaps", [])}
    for s in d["sources"]:
        v = vmap.get((key, s.get("name"))) or vmap.get(("*", s.get("name")))
        item = {k: s.get(k) for k in ("name", "operator", "url", "what", "access", "auth", "license", "nc_coverage", "cadence", "formats", "phases", "use_in_ncrecon", "priority", "confidence", "caveats")}
        if s.get("priority") == "high":
            item["evidence_urls"] = s.get("evidence_urls", [])[:3]
        if v:
            item["verdict"] = v.get("verdict")
            if v.get("corrections"):
                item["corrections"] = v["corrections"]
            if v.get("notes"):
                item["verifier_notes"] = v["notes"][:600]
        out["sources"].append(item)
        record["counts"]["sources"] += 1
        record["counts"]["high"] += s.get("priority") == "high"
    record["dimensions"].append(out)
json.dump(record, open(os.path.join(S, "research-record.json"), "w"), separators=(",", ":"))
# readable twin
with open(os.path.join(S, "research-record.md"), "w") as fh:
    fh.write(f"# Research record ({record['counts']['sources']} sources, {record['counts']['high']} high priority, {len(verdicts)} verified)\n")
    for d in record["dimensions"]:
        fh.write(f"\n## {d['dimension']}\n")
        for s in d["sources"]:
            vt = f" [verdict: {s.get('verdict')}]" if s.get("verdict") else ""
            fh.write(f"- ({s.get('priority')}/{s.get('confidence')}){vt} **{s['name']}** ({s.get('operator')}) {s.get('url')}\n  {s.get('what')}\n  access: {s.get('access')} | auth: {s.get('auth')} | licence: {s.get('license')} | cadence: {s.get('cadence')} | NC: {s.get('nc_coverage')}\n  use ({','.join(s.get('phases') or [])}): {s.get('use_in_ncrecon')}\n")
            if s.get("caveats"): fh.write(f"  caveats: {s['caveats']}\n")
            if s.get("corrections"): fh.write(f"  corrections: {json.dumps(s['corrections'])}\n")
            if s.get("verifier_notes"): fh.write(f"  verifier: {s['verifier_notes']}\n")
        fh.write("### insights\n" + "\n".join("- " + i for i in d["insights"]) + "\n### gaps\n" + "\n".join("- " + g for g in d["gaps"]) + "\n")
    if critic:
        fh.write("\n## Completeness critic\n" + json.dumps(critic, indent=1) + "\n")
print(record["counts"], "critic:", bool(critic), "bytes json", os.path.getsize(os.path.join(S, "research-record.json")), "md", os.path.getsize(os.path.join(S, "research-record.md")))
