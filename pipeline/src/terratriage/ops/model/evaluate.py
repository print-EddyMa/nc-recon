"""Score the model once on a held-out event's imagery against its labels.

`python -m terratriage.ops.model.evaluate --pre <pre.tif> --post <post.tif>
     --bbox W S E N --incident Eaton --name eaton_altadena`

Writes data/model/weights/<tag>.eval.<name>.json. Run it once per held-out
set, after training is final: re-running after changes would turn the
held-out event into a tuning set.
"""
from __future__ import annotations

import argparse
import json
import os

from . import LEVELS, MODEL_DIR
from .dataset import dins_points, labels, read_chips
from .train import metrics, predict


def load(tag: str):
    import torch

    from .net import Siamese

    wdir = os.path.join(MODEL_DIR, "weights")
    with open(os.path.join(wdir, f"{tag}.json"), encoding="utf-8") as fh:
        card = json.load(fh)
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = Siamese(len(LEVELS), pretrained=False).to(device)
    model.load_state_dict(torch.load(os.path.join(wdir, f"{tag}.pt"), map_location=device))
    return model, card, device


def evaluate(pre: str, post: str, bbox, incident: str, name: str, tag: str = "groma-dmg-v0") -> dict:
    path = os.path.join(MODEL_DIR, "weights", f"{tag}.eval.{name}.json")
    if os.path.exists(path):
        raise SystemExit(f"{path} exists: a held-out set is scored once. Delete it only if the model changed "
                         "for reasons that did not involve this set.")
    with open(os.path.join(MODEL_DIR, "weights", f"{tag}.json"), encoding="utf-8") as fh:
        kind = json.load(fh).get("kind")
    pts = dins_points(tuple(bbox), incident)
    if kind == "frozen_linear":
        from . import linear

        params, card = linear.load(tag)
        chip = card["chip"]
        a, b, kept = read_chips(pre, post, pts, chip_m=float(chip["metres"]), px=int(chip["pixels"]))
        p = linear.predict(params, a, b)
    else:
        model, card, device = load(tag)
        chip = card.get("chip") or {}
        a, b, kept = read_chips(pre, post, pts, chip_m=float(chip.get("metres", 32)), px=int(chip.get("pixels", 64)))
        p = predict(model, a, b, device, T=card["temperature"])
    m = metrics(labels(kept), p)
    homes = [i for i, q in enumerate(kept) if "residence" in str(q.get("structure_type") or "").lower()
             or "home" in str(q.get("structure_type") or "").lower()]
    out = {"model": tag, "held_out": name, "incident": incident, "bbox": list(bbox),
           "pre": pre, "post": post, "labels": "CAL FIRE DINS", "points": len(pts), "scored": len(kept),
           "all_structures": m, "homes_only": metrics(labels([kept[i] for i in homes]), p[homes]) if homes else None}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m terratriage.ops.model.evaluate")
    ap.add_argument("--pre", required=True)
    ap.add_argument("--post", required=True)
    ap.add_argument("--bbox", nargs=4, type=float, required=True)
    ap.add_argument("--incident", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--tag", default="groma-dmg-v0")
    a = ap.parse_args(argv)
    r = evaluate(a.pre, a.post, a.bbox, a.incident, a.name, a.tag)
    print(json.dumps({k: r[k] for k in ("held_out", "points", "scored", "all_structures", "homes_only")}, indent=1))


if __name__ == "__main__":
    main()
