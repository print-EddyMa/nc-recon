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
Q_RELATIVE = 0.10   # humidity cap is also <= 10 % of the local value (~ RH analysis uncertainty)
NUDGES = [("baseline", 0.0), ("away_0.1", 0.1), ("away_0.25", 0.25), ("away_0.5", 0.5), ("away_1", 1.0),
          ("toward_1", -1.0)]
WEB = Path(__file__).resolve().parents[2] / "web" / "public" / "data" / "butterfly"


def out_dir(case):
    d = WORK / case.id
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_adjoint(P):
    if (out_dir(P.case) / f"grad_{P.name}.npz").exists():      # resumable: a gradient is never recomputed
        print("[adjoint] reused existing gradient", flush=True)
        return
    t = time.time()
    J0, g = P.gradient()
    np.savez(out_dir(P.case) / f"grad_{P.name}.npz", J0=J0, **g)
    print(f"[adjoint] J0 = {J0:.4f}   ({time.time()-t:.0f}s)", flush=True)
    for k, v in g.items():
        print(f"   max |dJ/d {k}| = {np.abs(v).max():.3e}", flush=True)


def load_grad(P):
    G = np.load(out_dir(P.case) / f"grad_{P.name}.npz")
    return float(G["J0"]), {k: G[k] for k in ANALYSIS_ERROR}


def unit_nudge(P):
    """Steepest-descent nudge, each field scaled to its own cap: everywhere |dT| <= 0.5 K,
    |du|,|dv| <= 1 m/s and |dq| <= min(0.5 g/kg, 10 % of local q), each reached at that field's
    most sensitive point ('1x analysis error'). Scaling fields separately keeps every component
    a descent direction (g . d_k < 0); one shared scale let the tight upper-level humidity cap
    throttle temperature and wind to ~1e-4."""
    _, g = load_grad(P)
    d = P.descent_direction(g)
    q = np.asarray(P.inputs["specific_humidity"])
    cap = {k: np.full_like(d[k], v) for k, v in ANALYSIS_ERROR.items()}
    cap["specific_humidity"] = np.maximum(np.minimum(ANALYSIS_ERROR["specific_humidity"], Q_RELATIVE * q), 1e-8)
    return {k: (d[k] / float((np.abs(d[k]) / cap[k]).max())).astype(np.float32) for k in ANALYSIS_ERROR}


def cmd_steer(P, only_baseline=False):
    import jax.numpy as jnp
    from .storm import track, gc_dist_km
    case = P.case
    bt = besttrack(case)
    first = (case.storm0[0], case.storm0[1])
    unit = None if only_baseline else unit_nudge(P)
    J0g, g = (None, None) if only_baseline else load_grad(P)
    path = out_dir(case) / f"runs_{P.name}.json"
    prev = json.load(open(path)) if path.exists() else {}
    runs = {}
    for label, s in (NUDGES[:1] if only_baseline else NUDGES):
        t = time.time()
        # resumable: a finished forecast (result + fields on disk) is reused, not re-run
        if label in prev and (out_dir(case) / f"fields_{P.name}_{label}.npz").exists():
            runs[label] = prev[label]
            print(f"[steer] {label:10s} (reused)", flush=True)
            continue
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
        if unit and s != 0:
            # what the gradient alone predicts (first-order Taylor): the "lie detector" check
            r["J_linear"] = J0g + float(sum(np.sum(g[k] * s * unit[k]) for k in unit))
        if unit:
            r["energy_J"] = P.energy(delta)
            r["peak"] = {k: float(np.abs(np.asarray(v)).max()) for k, v in delta.items()}
            if label == "away_1":
                np.savez_compressed(out_dir(case) / f"nudge_{P.name}.npz", **{k: np.asarray(v) for k, v in delta.items()})
        runs[label] = r
        json.dump(runs, open(path, "w"), indent=1)
        dist = gc_dist_km(tr[-2]["lat"], tr[-2]["lon"], *case.target)
        lin = f" (linear guess {r['J_linear']:9.4f})" if "J_linear" in r else ""
        print(f"[steer] {label:10s} J={J:9.4f}{lin}  storm->target @+{case.window[-2]}h: {dist:5.0f} km   ({time.time()-t:.0f}s)",
              flush=True)


def cmd_export(case, name):
    from .export_web import export
    p = export(case, name, out_dir(case), WEB)
    print(f"[export] wrote {p} ({p.stat().st_size/1e3:.0f} kB)")


def main():
    ap = argparse.ArgumentParser(prog="python -m butterfly.run")
    ap.add_argument("cmd", choices=["forecast", "adjoint", "steer", "export", "all",
                                    "taylor", "random", "steering", "cnop", "transfer", "suite",
                                    "core", "osse"])
    ap.add_argument("--case", default="helene", choices=sorted(CASES))
    ap.add_argument("--model", default=None, help="defaults to the case's model")
    ap.add_argument("--nudges", default=None,
                    help="comma-separated nudge sizes for steer, e.g. 0.1,0.5,1,-1 (default: the full Helene set)")
    ap.add_argument("--random", type=int, default=5, help="random nudges in the null test")
    a = ap.parse_args()
    case = CASES[a.case]
    a.model = a.model or case.model
    if a.nudges:
        global NUDGES
        NUDGES = [("baseline", 0.0)] + [((f"away_{x:g}" if x > 0 else f"toward_{-x:g}"), x)
                                        for x in map(float, a.nudges.split(","))]
    if a.cmd == "export":
        return cmd_export(case, a.model)
    from . import experiments as X
    if a.cmd == "transfer":
        return X.cmd_transfer(case)
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
    if a.cmd in ("taylor", "suite"):
        X.cmd_taylor(P)
    if a.cmd in ("steering", "suite"):
        X.cmd_steering(P)
    if a.cmd == "core":                    # the protocol run for every additional storm
        cmd_adjoint(P); cmd_steer(P); X.cmd_random(P, n=a.random); cmd_export(case, a.model)
    if a.cmd in ("random", "suite"):
        X.cmd_random(P, n=a.random)
    if a.cmd == "cnop":
        X.cmd_cnop(P)
    if a.cmd == "osse":
        from .osse import cmd_osse
        cmd_osse(P)


if __name__ == "__main__":
    main()
