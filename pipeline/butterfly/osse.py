"""
Simulated targeted observations (an OSSE-style experiment).

Question: if you could fly one reconnaissance mission three days before landfall,
where should it go to most improve the forecast of the storm's impact on NC?

Set-up
  truth     = the ERA5 state (the un-nudged forecast from it is the "true" outcome)
  analysis  = truth + analysis error e: smooth random fields, tropospheric, RMS
              0.5 K / 1 m/s / 10 % of local humidity (rough ERA5-like magnitudes)
  observe R = assimilate a flight over a disk R (radius 700 km, tapered): the error
              inside R is reduced by ALPHA (70 %), a typical local dropsonde impact
  forecast error of the impact J:  dJ ~= g . e   (linear, from the adjoint)

Strategies for R
  adjoint   centre that maximises the expected error-variance reduction, chosen on
            half of the error samples and scored on the other half (no in-sample bias)
  peak      centre at the maximum of the column sensitivity map (a simple rule)
  storm     centred on the storm itself (what reconnaissance usually samples)
  random    many random centres over the domain (the null distribution)

Linear statistics use thousands of samples at no model cost; a handful of
samples are then verified with full nonlinear forecasts.
"""
import json, time
import numpy as np
import jax.numpy as jnp
from .problem import PERTURB
from .storm import gc_dist_km, track
from .run import out_dir, load_grad
from .experiments import run_one

ALPHA = 0.7
RADIUS_KM = 700.0
TAPER_KM = 200.0
SIGMA = {"temperature": 0.5, "u_component_of_wind": 1.0, "v_component_of_wind": 1.0}
Q_REL = 0.10
DOMAIN = (-130.0, -40.0, 5.0, 55.0)       # w, e, s, n for candidate / random centres


def _filters(shape, sigma_cells=1.5, sigma_levels=1.5):
    nl, nx, ny = shape
    kx = np.fft.fftfreq(nx)[None, :, None]; ky = np.fft.fftfreq(ny)[None, None, :]
    kz = np.fft.fftfreq(nl)[:, None, None]
    return np.exp(-2 * (np.pi * sigma_cells) ** 2 * (kx ** 2 + ky ** 2)) * np.exp(-2 * (np.pi * sigma_levels) ** 2 * kz ** 2)


def error_sample(P, rng, filt, q):
    """One analysis-error realisation: smooth, tropospheric, unit RMS then scaled."""
    trop = P.trop[:, None, None].astype(bool)
    e = {}
    for k in PERTURB:
        f = np.real(np.fft.ifftn(np.fft.fftn(rng.standard_normal(filt.shape)) * filt)) * trop
        f = f / np.sqrt((f[np.broadcast_to(trop, f.shape)] ** 2).mean())
        e[k] = (f * (Q_REL * q) if k == "specific_humidity" else f * SIGMA[k]).astype(np.float32)
    return e


def disk_weight(P, lat, lon):
    LON, LAT = np.meshgrid(P.lon, P.lat, indexing="ij")
    d = gc_dist_km(lat, lon, LAT, LON)
    return np.clip((RADIUS_KM + TAPER_KM - d) / TAPER_KM, 0, 1)        # 1 inside, linear taper


def cmd_osse(P, n_samples=2000, n_verify=3, seed=0):
    t0 = time.time()
    J0, g = load_grad(P)
    rng = np.random.default_rng(seed)
    q = np.asarray(P.inputs["specific_humidity"])
    filt = _filters(q.shape)

    # column "impact maps": m[x] = sum over levels & variables of g * e at column x
    maps = np.empty((n_samples, len(P.lon), len(P.lat)), dtype=np.float64)
    for i in range(n_samples):
        e = error_sample(P, rng, filt, q)
        maps[i] = sum((g[k] * e[k]).sum(0) for k in PERTURB)
    total = maps.reshape(n_samples, -1).sum(1)                         # dJ for each sample (linear)
    print(f"[osse] {n_samples} linear error samples in {time.time()-t0:.0f}s; "
          f"forecast-error std of J = {total.std():.2f} ({100*total.std()/J0:.1f}% of J)", flush=True)

    # candidate centres: every grid column inside the domain
    lon180 = ((P.lon + 180) % 360) - 180
    cands = [(float(la), float(lo)) for lo in lon180 for la in P.lat
             if DOMAIN[0] <= lo <= DOMAIN[1] and DOMAIN[2] <= la <= DOMAIN[3]]
    Wc = np.stack([disk_weight(P, la, lo).ravel() for la, lo in cands])  # [n_cand, cells]
    flat = maps.reshape(n_samples, -1)
    proj = flat @ Wc.T                                                   # [samples, n_cand] = g.(w_c e)
    after = total[:, None] - ALPHA * proj                                # dJ after observing R_c
    train, test = slice(0, n_samples // 2), slice(n_samples // 2, None)

    def reduction(idx, rows):
        return float(1 - after[rows, idx].var() / total[rows].var())

    red_train = 1 - after[train].var(0) / total[train].var()
    best = int(np.argmax(red_train))

    # simple rule: centre at the column-sensitivity maximum (energy norm, troposphere)
    S = sum((g[k][P.trop.astype(bool)] ** 2 / (P.coef[k] * P.wmass[P.trop.astype(bool)])).sum(0) for k in PERTURB)
    Sc = np.array([S[np.argmin(np.abs(lon180 - lo)), np.argmin(np.abs(P.lat - la))] for la, lo in cands])
    peak = int(np.argmax(Sc))
    storm = int(np.argmin([gc_dist_km(la, lo, *P.case.storm0) for la, lo in cands]))
    rand_idx = rng.integers(0, len(cands), 400)
    rand_red = np.array([reduction(int(i), test) for i in rand_idx])

    # second aircraft: the storm is already sampled (routine reconnaissance); where should a
    # second, non-overlapping flight go? (the job of NOAA's G-IV synoptic-surveillance flights)
    far = np.array([gc_dist_km(la, lo, *cands[storm]) > 2 * (RADIUS_KM + TAPER_KM) for la, lo in cands])
    after_storm = total - ALPHA * proj[:, storm]
    after2 = after_storm[:, None] - ALPHA * proj                        # disks don't overlap (far mask)
    red2_train = np.where(far, 1 - after2[train].var(0) / total[train].var(), -np.inf)
    best2 = int(np.argmax(red2_train))
    red_storm = float(1 - after_storm[test].var() / total[test].var())
    def red2(idx):
        return float(1 - after2[test, idx].var() / total[test].var())
    far_idx = np.flatnonzero(far)
    rand2 = np.array([red2(int(i)) for i in rng.choice(far_idx, 400)])
    rand2_pick = int(rng.choice(far_idx))

    lin = dict(
        second=dict(center=cands[best2], reduction_with_storm=red2(best2), storm_only=red_storm,
                    random_median=float(np.median(rand2)), random_p90=float(np.percentile(rand2, 90)),
                    random_center_verified=cands[rand2_pick], random_beats=float((rand2 >= red2(best2)).mean())),
        n_samples=n_samples, alpha=ALPHA, radius_km=RADIUS_KM, error_std=float(total.std()), J0=J0,
        adjoint=dict(center=cands[best], reduction=reduction(best, test)),
        peak=dict(center=cands[peak], reduction=reduction(peak, test)),
        storm=dict(center=cands[storm], reduction=reduction(storm, test)),
        random=dict(median=float(np.median(rand_red)), p90=float(np.percentile(rand_red, 90)),
                    beats_adjoint=float((rand_red >= reduction(best, test)).mean())),
    )
    print(f"[osse] second flight: storm-only {red_storm:.1%} -> storm + adjoint-chosen 2nd "
          f"{lin['second']['reduction_with_storm']:.1%} @ {np.round(lin['second']['center'], 1)}; storm + random 2nd "
          f"median {lin['second']['random_median']:.1%} (90th pct {lin['second']['random_p90']:.1%})", flush=True)
    print(f"[osse] linear, error-variance reduction (held-out samples): adjoint {lin['adjoint']['reduction']:.1%} "
          f"@ {np.round(lin['adjoint']['center'], 1)}, peak-rule {lin['peak']['reduction']:.1%}, "
          f"storm-centred {lin['storm']['reduction']:.1%}, random median {lin['random']['median']:.1%} "
          f"(90th pct {lin['random']['p90']:.1%})", flush=True)
    path = out_dir(P.case) / f"osse_{P.name}.json"
    json.dump(dict(linear=lin), open(path, "w"), indent=1)

    if n_verify == 0:
        return lin
    # ---- nonlinear verification on held-out samples ---------------------------------
    rng_v = np.random.default_rng(seed + 1000)
    # truth = the un-nudged forecast already on disk (identical to re-running it)
    runs = json.load(open(out_dir(P.case) / f"runs_{P.name}.json"))
    base = dict(J=runs["baseline"]["J"], track=runs["baseline"]["track"])
    tr0 = base["track"]
    cache_path = out_dir(P.case) / f"osse_cache_{P.name}.json"
    cache = json.load(open(cache_path)) if cache_path.exists() else {}
    verify = []
    for j in range(n_verify):
        e = error_sample(P, rng_v, filt, q)
        row = {}
        flights = [("analysis", []), ("storm", [lin["storm"]["center"]]),
                   ("storm+adjoint2", [lin["storm"]["center"], lin["second"]["center"]]),
                   ("storm+random2", [lin["storm"]["center"], lin["second"]["random_center_verified"]])]
        for name, cs in flights:
            w = sum(disk_weight(P, *c) for c in cs)[None] if cs else 0
            d = {k: e[k] * (1 - ALPHA * w) for k in PERTURB}
            key = f"{j}:{name}"
            if key in cache:                                   # resumable, one forecast at a time
                r = cache[key]
                print(f"[osse #{j} {name}] (reused)", flush=True)
            else:
                r = run_one(P, d, f"osse #{j} {name}")
                r = dict(J=r["J"], track=r["track"])
                cache[key] = r
                json.dump(cache, open(cache_path, "w"))
            i72 = 72 // P.case.every
            row[name] = dict(J_err=r["J"] - base["J"],
                             track_err_72h=float(gc_dist_km(r["track"][i72]["lat"], r["track"][i72]["lon"],
                                                            tr0[i72]["lat"], tr0[i72]["lon"])))
        verify.append(row)
        json.dump(dict(linear=lin, truth_J=base["J"], verify=verify), open(path, "w"), indent=1)
    print(f"[osse] done in {time.time()-t0:.0f}s", flush=True)
