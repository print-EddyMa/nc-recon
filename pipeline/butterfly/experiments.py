"""
Rigor experiments on top of the one-step adjoint nudge (run.py steer).

  taylor     adjoint verification: r(eps) = [J(eps d) - J0] / [eps g.d] -> 1 as eps -> 0
  random     Monte-Carlo null: smooth random nudges under the SAME constraints as the
             adjoint nudge (troposphere, keep-out zone, per-field analysis-error caps)
  steering   physics attribution: deep-layer-mean (850-200 hPa) steering flow around the
             model storm, the quantity NHC-style track reasoning uses
  transfer   the same nudge put into a different model (NeuralGCM 1.4 deg)
  cnop       nonlinear optimal perturbation (Mu et al. 2003): re-linearise at the nudged
             state and step again, staying inside the caps

All results land in work/<case>/experiments_<model>.json (merged, so commands can run
in any order or be re-run).
"""
import json, time
import numpy as np
import jax.numpy as jnp
from .problem import PERTURB, G
from .storm import track, gc_dist_km
from .run import out_dir, unit_nudge, load_grad, ANALYSIS_ERROR, Q_RELATIVE

STEER_LEVELS = (850, 700, 500, 400, 300, 250, 200)


def _results_path(P):
    return out_dir(P.case) / f"experiments_{P.name}.json"


def _save(P, key, value):
    path = _results_path(P)
    doc = json.load(open(path)) if path.exists() else {}
    doc[key] = value
    json.dump(doc, open(path, "w"), indent=1)


def caps(P):
    q = np.asarray(P.inputs["specific_humidity"])
    c = {k: np.full(q.shape, v, dtype=np.float32) for k, v in ANALYSIS_ERROR.items()}
    c["specific_humidity"] = np.maximum(np.minimum(ANALYSIS_ERROR["specific_humidity"], Q_RELATIVE * q), 1e-8)
    return c


def scale_to_caps(P, d):
    """Scale each field so its largest |value|/cap is exactly 1 (same rule as unit_nudge)."""
    c = caps(P)
    return {k: (d[k] / max(float((np.abs(d[k]) / c[k]).max()), 1e-30)).astype(np.float32) for k in d}


def steering(P, preds, tr):
    """Pressure-weighted deep-layer-mean wind (850-200 hPa) averaged in a 200-800 km annulus
    around the model storm at each output time. Returns [(u, v)] in m/s."""
    ks = [int(np.argmin(np.abs(P.levels - p))) for p in STEER_LEVELS]
    w = np.array([P.levels[k] for k in ks]); w = w / w.sum()       # pressure weighting
    LON, LAT = np.meshgrid(P.lon, P.lat, indexing="ij")
    out = []
    for t, p in enumerate(tr):
        d = gc_dist_km(p["lat"], p["lon"], LAT, LON)
        ring = (d > 200) & (d < 800)
        u = sum(wi * preds["u_component_of_wind"][t, k] for wi, k in zip(w, ks))
        v = sum(wi * preds["v_component_of_wind"][t, k] for wi, k in zip(w, ks))
        out.append([round(float(u[ring].mean()), 3), round(float(v[ring].mean()), 3)])
    return out


def run_one(P, delta, label):
    """One full forecast: objective, track, steering flow."""
    t = time.time()
    preds = {k: np.asarray(v) for k, v in P.forecast({k: jnp.asarray(v) for k, v in delta.items()}).items()}
    tr = track(preds["u_component_of_wind"][:, P.k[850]], preds["v_component_of_wind"][:, P.k[850]],
               P.lon, P.lat, P.case.storm0)
    J = P.objective_from(preds)
    i72 = 72 // P.case.every
    r = dict(J=J, track=tr, steering=steering(P, preds, tr),
             dist_target_72h=float(gc_dist_km(tr[i72]["lat"], tr[i72]["lon"], *P.case.target)))
    print(f"[{label}] J={J:.3f}  dist@72h={r['dist_target_72h']:.0f} km  ({time.time()-t:.0f}s)", flush=True)
    return r


def smooth_random(P, seed, sigma_cells=1.5):
    """Spatially smooth Gaussian random field per variable (horizontal ~ sigma_cells grid cells,
    ~3 levels vertical), masked to the troposphere and outside the keep-out zone."""
    rng = np.random.default_rng(seed)
    nl, nx, ny = np.asarray(P.inputs["temperature"]).shape
    kx = np.fft.fftfreq(nx)[None, :, None]; ky = np.fft.fftfreq(ny)[None, None, :]; kz = np.fft.fftfreq(nl)[:, None, None]
    filt = np.exp(-2 * (np.pi * sigma_cells) ** 2 * (kx ** 2 + ky ** 2)) * np.exp(-2 * (np.pi * 1.5) ** 2 * kz ** 2)
    m = P.mask[None] * P.trop[:, None, None]
    out = {}
    for k in PERTURB:
        f = np.real(np.fft.ifftn(np.fft.fftn(rng.standard_normal((nl, nx, ny))) * filt))
        out[k] = f * m
    return scale_to_caps(P, out)


# ------------------------------------------------------------------ commands
def cmd_taylor(P, eps_list=(0.02, 0.05)):
    J0, g = load_grad(P)
    u = unit_nudge(P)
    gd = float(sum(np.sum(g[k] * u[k]) for k in u))
    rows = []
    for e in eps_list:
        r = run_one(P, {k: e * v for k, v in u.items()}, f"taylor eps={e}")
        rows.append(dict(eps=e, J=r["J"], dJ=r["J"] - J0, dJ_linear=e * gd, ratio=(r["J"] - J0) / (e * gd)))
        print(f"   ratio (real/linear) = {rows[-1]['ratio']:.4f}", flush=True)
        _save(P, "taylor", dict(J0=J0, g_dot_d=gd, rows=rows))


def cmd_random(P, n=5):
    path = _results_path(P)
    done = json.load(open(path)).get("random", {}).get("rows", []) if path.exists() else []
    rows = [r for r in done if r["seed"] < n]
    for seed in range(n):
        if any(r["seed"] == seed for r in rows):           # resumable
            print(f"[random #{seed}] (reused)", flush=True)
            continue
        r = run_one(P, smooth_random(P, seed), f"random #{seed}")
        rows.append(dict(seed=seed, J=r["J"], dist_target_72h=r["dist_target_72h"]))
        rows.sort(key=lambda r: r["seed"])
        _save(P, "random", dict(n=len(rows), rows=rows, constraint="same per-field caps as 1x adjoint nudge"))


def cmd_steering(P):
    """Re-run the un-nudged and 1x nudges, keeping the steering-flow diagnostics
    (also a reproducibility check: J must match the earlier run)."""
    u = unit_nudge(P)
    out = {}
    for label, s in [("baseline", 0.0), ("away_1", 1.0), ("toward_1", -1.0)]:
        out[label] = run_one(P, {k: s * v for k, v in u.items()}, f"steering {label}")
        _save(P, "steering", out)


def cmd_cnop(P, iters=1):
    """Re-linearise at the current nudge and take another projected step (per-field caps)."""
    J0, g0 = load_grad(P)
    d = unit_nudge(P)
    hist = []
    for it in range(iters):
        t = time.time()
        Jd, g = P.gradient(d)
        step = scale_to_caps(P, P.descent_direction(g))
        best = None
        for beta in (0.5, 1.0):                      # small line search on the mixing weight
            cand = scale_to_caps(P, {k: d[k] + beta * step[k] for k in d})
            r = run_one(P, cand, f"cnop it{it+1} beta={beta}")
            hist.append(dict(iter=it + 1, beta=beta, J=r["J"], J_start=Jd, dist_target_72h=r["dist_target_72h"]))
            if best is None or r["J"] < best[0]:
                best = (r["J"], cand)
        print(f"[cnop] iteration {it+1}: J {Jd:.2f} -> {best[0]:.2f} ({time.time()-t:.0f}s)", flush=True)
        _save(P, "cnop", dict(J0=J0, history=hist))
        if best[0] >= Jd:
            break
        d = best[1]
    np.savez_compressed(out_dir(P.case) / f"nudge_cnop_{P.name}.npz", **d)


def cmd_transfer(case, src="deterministic_2_8_deg", dst="deterministic_1_4_deg"):
    """Put the 2.8-deg adjoint nudge (pressure-level fields) into the 1.4-deg model by
    bilinear interpolation, and compare the effect. The cap scaling is redone on the
    1.4-deg grid so 1x still means 'at most 1x analysis error'."""
    from .problem import Problem
    Ps = Problem(case, src)
    u_src = unit_nudge(Ps)
    del Ps
    Pd = Problem(case, dst)
    from scipy.interpolate import RegularGridInterpolator
    src_lon = None
    import neuralgcm  # noqa
    from .problem import load_model
    ms = load_model(src).data_coords.horizontal
    slon, slat = np.rad2deg(np.asarray(ms.longitudes)), np.rad2deg(np.asarray(ms.latitudes))
    # periodic padding in longitude
    slon_p = np.concatenate([slon[-1:] - 360, slon, slon[:1] + 360])
    LON, LAT = np.meshgrid(Pd.lon, Pd.lat, indexing="ij")
    pts = np.stack([LON.ravel(), LAT.ravel()], -1)
    nudge = {}
    for k, v in u_src.items():
        vp = np.concatenate([v[:, -1:], v, v[:, :1]], axis=1)
        out = np.empty((v.shape[0],) + LON.shape, dtype=np.float32)
        for l in range(v.shape[0]):
            f = RegularGridInterpolator((slon_p, slat), vp[l], bounds_error=False, fill_value=0.0)
            out[l] = f(pts).reshape(LON.shape)
        nudge[k] = out * Pd.mask[None] * Pd.trop[:, None, None]
    nudge = scale_to_caps(Pd, nudge)
    res = {}
    for label, s in [("baseline", 0.0), ("away_1", 1.0)]:
        r = run_one(Pd, {k: s * v for k, v in nudge.items()}, f"transfer {dst} {label}")
        res[label] = dict(J=r["J"], dist_target_72h=r["dist_target_72h"], track=r["track"])
        doc = dict(model=dst, from_model=src, **res)
        if "baseline" in res and "away_1" in res:
            doc["change_pct"] = 100 * (res["away_1"]["J"] / res["baseline"]["J"] - 1)
        path = out_dir(case) / f"experiments_{src}.json"
        all_ = json.load(open(path)) if path.exists() else {}
        all_["transfer"] = doc
        json.dump(all_, open(path, "w"), indent=1)
