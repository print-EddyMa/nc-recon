import csv
import json

import numpy as np

from terratriage.ops.analyze import calibration, evaluate
from terratriage.ops.analyze.classes import FEMA


def _ops_file(path, n, seed, noise):
    rng = np.random.default_rng(seed)
    feats, truth = [], {}
    for i in range(n):
        y = int(rng.choice(5, p=[0.4, 0.2, 0.2, 0.12, 0.08]))
        pred = int(np.clip(y + rng.choice([-1, 0, 1], p=[noise, 1 - 2 * noise, noise]), 0, 4))
        p = np.full(5, 0.05)
        p[pred] = 0.8
        nid = f"00000000-0000-0000-0000-{seed:04d}{i:08d}"
        truth[nid] = FEMA[y]
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]},
                      "properties": {"ncr_id": nid, "damage_level": FEMA[pred],
                                     "damage_probs": dict(zip(FEMA, p.tolist())),
                                     "centroid": [-82.18 + rng.uniform(0, 0.03), 35.62 + rng.uniform(0, 0.03)],
                                     "needs_review": bool(rng.random() < 0.2), "prediction_set": None,
                                     "evidence": [{"id": "E1", "available": True,
                                                   "detail": {"logits": (np.eye(4)[min(pred, 3)] * 8).tolist()}}]}})
    path.write_text(json.dumps({"type": "FeatureCollection", "properties": {}, "features": feats}))
    return truth


def test_eval_end_to_end(tmp_path, monkeypatch):
    out, labels, cal = tmp_path / "ops", tmp_path / "labels", tmp_path / "cal"
    out.mkdir(); labels.mkdir()
    tune = _ops_file(out / "old_fort.geojson", 300, 1, 0.15)
    test = _ops_file(out / "chimney_rock.geojson", 200, 2, 0.25)
    with open(labels / "x.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ncr_id", "label", "labeler"])
        for i, (k, v) in enumerate({**tune, **test}.items()):
            w.writerow([k, v, "a"])
            if i % 5 == 0:                              # 20% double-labeled
                w.writerow([k, v if i % 10 else "cannot_tell", "b"])
    monkeypatch.setattr(evaluate, "OPS_OUT", str(out))
    monkeypatch.setattr(evaluate, "LABELS", str(labels))
    monkeypatch.setattr(evaluate, "REPORTS", str(tmp_path / "reports"))
    monkeypatch.setattr(calibration, "CAL_DIR", str(cal))
    rep = evaluate.evaluate()
    assert rep["status"] == "OK"
    assert set(rep["roles"]) == {"TUNE", "TEST"}
    assert rep["labels"]["unresolved_disagreements"] == 50   # 100 double-labeled, half disagree
    assert rep["labels"]["cohens_kappa"] is not None
    t, s = rep["roles"]["TUNE"]["all"], rep["roles"]["TEST"]["all"]
    assert t["accuracy"] > s["accuracy"]                       # noisier TEST set
    lo, hi = t["macro_f1_ci95"]
    assert lo < t["macro_f1"] < hi
    md = open(evaluate.write_report(rep)).read()
    assert "## TEST areas: chimney_rock" in md and "Destroyed recall" in md
    fit = evaluate.calibrate()
    assert fit["areas"] == ["old_fort"]                        # TEST never used for fitting
    assert 0.05 < fit["fusion_temperature"] < 20
