"""
NC Recon · Butterfly - command line.

    python -m butterfly.run adjoint --case helene     # gradient of the NC impact wrt the ERA5 initial state
    python -m butterfly.run steer   --case helene     # nudges from that gradient, verified by full forecasts
    python -m butterfly.run export  --case helene     # -> web/public/data/butterfly/helene.json
    python -m butterfly.run all     --case helene

Every number the web screen shows comes out of `steer` (full nonlinear NeuralGCM
forecasts), not out of the linear gradient.
"""
import argparse, json, time
from pathlib import Path
import numpy as np

from .cases import CASES, WORK, besttrack

# Peak size of a nudge, as a fraction s of typical analysis uncertainty. These are
# rough magnitudes for ERA5 in the tropics/subtropics (order of the ERA5 ensemble
# spread / analysis-minus-observation statistics), used to ask "is the nudge
# smaller than what we don't know anyway?" - not exact error bars.
ANALYSIS_ERROR = {"temperature": 0.5, "u_component_of_wind": 1.0, "v_component_of_wind": 1.0,
                  "specific_humidity": 0.5e-3}
NUDGES = [("baseline", 0.0), ("away_0.25", 0.25), ("away_0.5", 0.5), ("away_1", 1.0), ("toward_1", -1.0)]
WEB = Path(__file__).resolve().parents[2] / "web" / "public" / "data" / "butterfly"


def out_dir(case):
    d = WORK / case.id
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_adjoint(P):
    t = time.time()
    J0, g = P.gradient()
    np.savez(out_dir(P.case) / f"grad_{P.name}.npz", J0=J0, **g)
    print(f"[adjoint] J0 = {J0:.4f}   ({time.time()-t:.0f}s)", flush=True)
    for k, v in g.items():
        print(f"   max |dJ/d {k}| = {np.abs(v).max():.3e}", flush=True)


def unit_nudge(P):
    G = np.load(out_dir(P.case) / f"grad_{P.name}.npz")
    d = P.descent_direction({k: G[k] for k in ANALYSIS_ERROR})
    peak = max(np.abs(d[k]).max() / ANALYSIS_ERROR[k] for k in ANALYSIS_ERROR)
    return {k: (v / peak).astype(np.float32) for k, v in d.items()}      # peak = 1 x analysis error


def cmd_steer(P, only_baseline=False):
    import jax.numpy as jnp
    from .storm import track, gc_dist_km
    case = P.case
    bt = besttrack(case)
    first = (case.storm0[0], case.storm0[1])
    unit = None if only_baseline else unit_nudge(P)
    runs = {}
    path = out_dir(case) / f"runs_{P.name}.json"
    for label, s in (NUDGES[:1] if only_baseline else NUDGES):
        t = time.time()
        delta = {k: jnp.asarray(s * v) for k, v in (unit or {}).items()} if unit else {}
        preds = P.forecast(delta)
        preds = {k: np.asarray(v) for k, v in preds.items()}
        k850 = P.k[850]
        tr = track(preds["u_component_of_wind"][:, k850], preds["v_component_of_wind"][:, k850], P.lon, P.lat, first)
        J = P.objective_from(preds)
        times = np.datetime64(case.init) + np.arange(len(tr)) * np.timedelta64(case.every, "h")
        for p, tt in zip(tr, times):
            p["time"] = str(tt)[:16]
            b = bt[bt.ISO_TIME == np.datetime64(tt)]
            if len(b):
                p["err_km"] = round(float(gc_dist_km(p["lat"], p["lon"], b.LAT.values[0], b.LON.values[0])))
        impact = np.stack([np.asarray(P.impact_field({k: v[i] for k, v in preds.items()})) for i in range(len(tr))])
        np.savez_compressed(out_dir(case) / f"fields_{P.name}_{label}.npz", impact=impact.astype(np.float32),
                            u850=preds["u_component_of_wind"][:, k850].astype(np.float32),
                            v850=preds["v_component_of_wind"][:, k850].astype(np.float32))
        r = dict(s=s, J=J, track=tr)
        if unit:
            r["energy_J"] = P.energy(delta)
            r["peak"] = {k: float(np.abs(np.asarray(v)).max()) for k, v in delta.items()}
            if label == "away_1":
                np.savez_compressed(out_dir(case) / f"nudge_{P.name}.npz", **{k: np.asarray(v) for k, v in delta.items()})
        runs[label] = r
        json.dump(runs, open(path, "w"), indent=1)
        dist = gc_dist_km(tr[-2]["lat"], tr[-2]["lon"], *case.target)
        print(f"[steer] {label:10s} J={J:9.4f}  storm->target @+{case.window[-2]}h: {dist:5.0f} km   ({time.time()-t:.0f}s)",
              flush=True)


def cmd_export(case, name):
    from .export_web import export
    p = export(case, name, out_dir(case), WEB)
    print(f"[export] wrote {p} ({p.stat().st_size/1e3:.0f} kB)")


def main():
    ap = argparse.ArgumentParser(prog="python -m butterfly.run")
    ap.add_argument("cmd", choices=["forecast", "adjoint", "steer", "export", "all"])
    ap.add_argument("--case", default="helene", choices=sorted(CASES))
    ap.add_argument("--model", default="deterministic_2_8_deg")
    a = ap.parse_args()
    case = CASES[a.case]
    if a.cmd == "export":
        return cmd_export(case, a.model)
    from .problem import Problem
    P = Problem(case, a.model)
    if a.cmd == "forecast":
        cmd_steer(P, only_baseline=True)
    if a.cmd in ("adjoint", "all"):
        cmd_adjoint(P)
    if a.cmd in ("steer", "all"):
        cmd_steer(P)
    if a.cmd == "all":
        cmd_export(case, a.model)


if __name__ == "__main__":
    main()
