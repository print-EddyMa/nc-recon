"""Bake the figures and image crops for the backend explainer from a real run.

Run from pipeline/:  .venv/bin/python ../docs/backend-explainer/build_data.py
Then:                python3 ../docs/backend-explainer/build.py
"""
import sys, json, glob, os, re, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from chips import *

FEMA = ["no_damage", "affected", "minor", "major", "destroyed"]
P = FC["properties"]
feats = FC["features"]
byid = {f["properties"]["ncr_id"]: f for f in feats}
def find(prefix): return next(f for k, f in byid.items() if k.startswith(prefix))

# ---- every structure, for the hero field, the census grid and the map ----
xs = [f["properties"]["centroid"][0] for f in feats]; ys = [f["properties"]["centroid"][1] for f in feats]
w, e, s, n = min(xs), max(xs), min(ys), max(ys)
kx = np.cos(np.radians((s + n) / 2))
aspect = ((e - w) * kx) / (n - s)
S = [[round((f["properties"]["centroid"][0] - w) / (e - w) * 1000), round((n - f["properties"]["centroid"][1]) / (n - s) * 1000),
      FEMA.index(f["properties"]["damage_level"]) if f["properties"]["damage_level"] else -1,
      int(bool(f["properties"]["needs_review"]) and bool(f["properties"]["damage_level"]))] for f in feats]

assessed = [f["properties"] for f in feats if f["properties"].get("damage_probs")]
conf = np.array([p["confidence"] for p in assessed])
conf_hist = np.histogram(conf, bins=np.linspace(0.2, 1.0, 33))[0].tolist()
ev = lambda p: {c["id"]: c for c in p["evidence"]}
z = np.array([ev(p)["E2"]["detail"]["z"] for p in assessed if ev(p)["E2"]["available"]])
z_hist = np.histogram(np.clip(z, -3, 9), bins=np.linspace(-3, 9, 49))[0].tolist()

al = [(p["measurements"]["alignment"]["post"]["dx_m"], p["measurements"]["alignment"]["post"]["dy_m"], int(p["measurements"]["alignment"]["post"]["weak"]))
      for p in assessed if p["footprint_source"] == "usa_structures"]
rng = np.random.default_rng(0)
idx = rng.choice(len(al), size=min(700, len(al)), replace=False)
align_pts = [[al[i][0], al[i][1], al[i][2]] for i in idx]

rv = collections.Counter()
for p in assessed:
    for r in p["review_reasons"]:
        rv[re.sub(r"_[-+]?\d+(\.\d+)?$", "", r)] += 1
ctx = collections.Counter()
for p in assessed:
    for r in p["reason_codes"]:
        for key in ("ROOF_UNDER_CANOPY", "POSSIBLE_CLOUD_OR_HAZE", "POSSIBLE_CLOUD_", "IMAGE_NODATA", "MISREGISTERED", "FOOTPRINT_ALIGNMENT_WEAK", "E4_TARP"):
            if r.startswith(key): ctx[key] += 1
cnn = collections.Counter(ev(p)["E1"]["detail"]["xbd_label"] for p in assessed if ev(p)["E1"]["available"])

man = json.load(open(glob.glob(f"runs/{P['run_id']}/manifest.json")[0]))
imp = json.load(open(f"data/output/ops/{AREA}.impact.json"))
health = json.load(open("data/output/ops/health.json"))

areas = []
for path in sorted(glob.glob("data/output/ops/*.geojson")):
    fc = json.load(open(path)); Q = fc["properties"]; aid = os.path.basename(path)[:-8]
    ec, r80 = Q["expected_counts"], Q.get("expected_counts_80pct") or {}
    ip = path[:-8] + ".impact.json"
    areas.append({"name": re.sub(r"_[0-9a-f]{4}$", "", aid).replace("_", " ").title(), "role": Q["aoi"]["role"],
                  "n": Q["n_structures"], "assessed": Q["n_structures"] - Q["not_assessed"]["total"],
                  "sev": round(ec["major"] + ec["destroyed"]), "lo": sum((r80.get(c) or [0, 0])[0] for c in ("major", "destroyed")),
                  "hi": sum((r80.get(c) or [0, 0])[1] for c in ("major", "destroyed")), "review": Q["n_needs_review"],
                  "rt": Q.get("runtime_sec"), "disp": round(json.load(open(ip))["expected_displaced"]["median"]) if os.path.exists(ip) else None})
areas.sort(key=lambda a: -a["sev"])

def example(prefix, tag, note):
    f = find(prefix); p = f["properties"]; E = ev(p)
    out = {"tag": tag, "note": note, "level": FEMA.index(p["damage_level"]), "conf": p["confidence"],
           "probs": [p["damage_probs"][c] for c in FEMA], "review": p["review_reasons"], "area": round(p["area_m2"]),
           "src": p["footprint_source"], "ch": []}
    for k in ("E1", "E2", "E4", "E5"):
        c = E.get(k)
        out["ch"].append({"id": k, "ok": bool(c and c["available"]), "w": c.get("weight") if c else None,
                          "L": c.get("likelihood") if c and c["available"] else None, "status": c.get("status") if c else None,
                          "why": (c or {}).get("unavailable_reason"), "reasons": (c or {}).get("reasons", []),
                          "xbd": ((c or {}).get("detail") or {}).get("xbd_label"), "z": ((c or {}).get("detail") or {}).get("z")})
    for kind in ("pre", "post"):
        img, ring, raw, width = chip(f, kind, size=220)
        out[kind] = b64(img); out[kind + "_ring"] = ring; out[kind + "_raw"] = raw; out["width_m"] = width
    out["al"] = p["measurements"]["alignment"]["post"]
    return out

EX = [
    example("59a5bf3f", "No damage", "A clear roof in both images. The classifier and the change measure agree, so the call is not sent for review."),
    example("aecb1b5d", "Affected", "The classifier's \"minor damage\" label straddles two FEMA levels, so the result is split and falls under the 50% bar."),
    example("a4ace218", "Minor", "Change evidence pushes a \"minor damage\" label up the scale, but not far enough to be sure."),
    example("92715668", "Major", "Where a house stood there is bare ground. A severe call is never trusted before calibration: it goes to a person."),
    example("4d99c95c", "Destroyed", "The structure is gone from the after image. Every Destroyed call is reviewed until the model is calibrated."),
    example("08fcf962", "Under cloud", "The after image is cloud. Both imagery channels say so and drop out; with no classifier reading the structure goes to review."),
    example("13e90372", "Under trees", "More than 40% of the roof is under canopy, so both imagery channels count for less."),
]
ALIGN = example("68b7eab6", "Alignment", "")

D = {
    "run": {"id": P["run_id"], "runtime": P["runtime_sec"], "generated": P["generated_utc"], "git": man.get("git_sha")},
    "aspect": round(float(aspect), 4), "S": S,
    "counts": P["counts"], "expected": P["expected_counts"], "range": P["expected_counts_80pct"],
    "n": P["n_structures"], "assessed": len(assessed), "review": P["n_needs_review"], "not_assessed": P["not_assessed"],
    "footprints": {"usa": P["provenance"]["footprints"][0]["count"], "osm": P["provenance"]["footprints"][1]["count"], "nsi_only": P["not_assessed"]["total"]},
    "conf_hist": conf_hist, "z_hist": z_hist, "align_pts": align_pts, "align_consensus": P["footprint_alignment"],
    "coreg": P["coregistration"], "pair": P["pair_context"], "e2_base": P["e2_baseline"],
    "review_reasons": dict(rv), "context": dict(ctx), "cnn": dict(cnn),
    "timings": man["timings_sec"], "impact": {k: imp[k] for k in ("residential_structures_assessed", "expected_displaced", "sensitivity_w_minor", "unassessed_residential", "tracts")},
    "health": [{"s": h["source"], "st": h["status"], "ms": h["latency_ms"]} for h in health["sources"]], "health_at": health["checked_utc"],
    "areas": areas, "ex": EX, "alignex": ALIGN,
    "dates": {"pre": "2022-01-07", "post": "2024-10-02", "incident": P["event"]["incident_begin"]},
    "prior": [float(x) for x in __import__("terratriage.ops.analyze.classes", fromlist=["class_prior"]).class_prior()],
}

def _size(p):
    p = os.path.join("data", p)
    if not os.path.exists(p): return None
    if os.path.isfile(p): return os.path.getsize(p)
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p) for f in fs if os.path.exists(os.path.join(d, f)))
D["store"] = {k: _size(k) for k in ["labels", "ops_registry.yaml", "audit.log", "jobs.json", "output/ops", "raw", "cache"]}
D["store_at"] = __import__("datetime").date.today().isoformat()
json.dump(D, open(os.path.join(HERE, "data.json"), "w"), separators=(",", ":"))
print("data bytes", os.path.getsize(os.path.join(HERE, "data.json")))
print({k: (len(json.dumps(v)) if not isinstance(v, (int, float, str)) else v) for k, v in D.items()})
print("reasons", dict(rv), "ctx", dict(ctx), "cnn", dict(cnn))
print([(x["tag"], x["level"], round(x["conf"], 2), x["review"], [(c["id"], c["ok"], c["w"], c["why"]) for c in x["ch"]]) for x in EX])
print("align ex", ALIGN["al"], ALIGN["src"])
