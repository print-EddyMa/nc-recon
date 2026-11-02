"""Export a case's results to one compact JSON the NC Recon web app reads
(`web/public/data/butterfly/<case>.json`). Schema: `ncrecon.butterfly/1`
(mirrored in `web/src/lib/butterfly.ts`)."""
import json, datetime, re
import numpy as np
from .cases import besttrack
from .problem import PERTURB, CP, TR, LV, TROPOSPHERE_TOP_HPA

SENS_BBOX = (-135.0, -35.0, 0.0, 62.0)       # w, e, s, n: where the sensitivity map is drawn
IMPACT_BBOX = (-100.0, -66.0, 14.0, 44.0)    # Gulf / SE US / western Atlantic
RUN_LABELS = {
    "baseline": "No nudge (NeuralGCM from ERA5)",
    "away_0.1": "Nudged away · 0.1× analysis error",
    "away_0.25": "Nudged away · 0.25× analysis error",
    "away_0.5": "Nudged away · 0.5× analysis error",
    "away_1": "Nudged away · 1× analysis error",
    "toward_1": "Reversed nudge (toward NC) · 1×",
}


def _grid(name):
    import neuralgcm  # noqa: F401  (grid only; no ERA5 / no run)
    from .problem import load_model
    m = load_model(name)
    g = m.data_coords.horizontal
    lon = np.rad2deg(np.asarray(g.longitudes)); lat = np.rad2deg(np.asarray(g.latitudes))
    levels = np.asarray(m.data_coords.vertical.centers, dtype=float)
    return lon, lat, levels


def _edges(lon, lat):
    dl = lon[1] - lon[0]
    lat_e = np.concatenate([[-90], (lat[1:] + lat[:-1]) / 2, [90]])
    return dl, lat_e


def _cells(field, lon, lat, bbox, keep=lambda v: True, digits=3):
    """[lon, lat] field -> [[w, s, e, n, value], ...] inside bbox (lon in -180..180)."""
    dl, lat_e = _edges(lon, lat)
    w, e, s, n = bbox
    out = []
    for i, lo in enumerate(lon):
        L = ((lo + 180) % 360) - 180
        if not (w <= L <= e):
            continue
        for j in range(len(lat)):
            if not (s <= lat[j] <= n):
                continue
            v = float(field[i, j])
            if keep(v):
                out.append([round(L - dl / 2, 2), round(float(lat_e[j]), 2), round(L + dl / 2, 2),
                            round(float(lat_e[j + 1]), 2), round(v, digits)])
    return out


def model_label(name):
    """deterministic_2_8_deg -> 'NeuralGCM 2.8° (deterministic)'"""
    m = re.match(r"(\w+?)_(\d)_(\d)_deg$", name)
    return f"NeuralGCM {m.group(2)}.{m.group(3)}° ({m.group(1).replace('_', ' ')})" if m else f"NeuralGCM {name}"


def _rigor(work, name, runs, case):
    """Summaries of experiments.py results (each part optional)."""
    p = work / f"experiments_{name}.json"
    if not p.exists():
        return None
    X = json.load(open(p))
    J0 = runs["baseline"]["J"]
    out = {}
    if "taylor" in X:
        rows = [dict(s=r["eps"], ratio=round(r["ratio"], 4)) for r in X["taylor"]["rows"]]
        for rid, r in runs.items():                       # the steer runs extend the curve
            if r.get("J_linear") is not None and r["s"] > 0:
                rows.append(dict(s=r["s"], ratio=round((r["J"] - J0) / (r["J_linear"] - J0), 4)))
        out["taylor"] = sorted(rows, key=lambda r: r["s"])
    if "random" in X:
        out["random"] = dict(change_pct=[round(100 * (r["J"] / J0 - 1), 2) for r in X["random"]["rows"]],
                             constraint=X["random"]["constraint"])
    if "steering" in X:
        S = X["steering"]
        hours = [h for h in (36, 48, 54, 60, 66) if h // case.every < len(S["baseline"]["steering"])]
        def mean_uv(run):
            a = np.array([S[run]["steering"][h // case.every] for h in hours]); return a.mean(0)
        b = mean_uv("baseline")
        out["steering"] = dict(hours=hours, baseline_ms=b.round(2).tolist(), runs={
            r: dict(delta_ms=(mean_uv(r) - b).round(2).tolist(),
                    implied_km=round(float(np.hypot(*(mean_uv(r) - b)) * (hours[-1] - hours[0] + case.every) * 3.6), 0),
                    J_repro=round(S[r]["J"], 3))
            for r in S if r != "baseline"})
        out["steering"]["baseline_J_repro"] = round(S["baseline"]["J"], 3)
    if "transfer" in X and "change_pct" in X["transfer"]:
        T = X["transfer"]
        out["transfer"] = dict(model=model_label(T["model"]), change_pct=round(T["change_pct"], 2),
                               source_change_pct=round(100 * (runs["away_1"]["J"] / J0 - 1), 2),
                               baseline_track_err_km=T.get("baseline_track_err_km"))
    if "cnop" in X:
        best = min(X["cnop"]["history"], key=lambda h: h["J"])
        out["cnop"] = dict(change_pct=round(100 * (best["J"] / J0 - 1), 2),
                           one_step_change_pct=round(100 * (runs["away_1"]["J"] / J0 - 1), 2),
                           iterations=max(h["iter"] for h in X["cnop"]["history"]))
    po = work / f"osse_{name}.json"
    if po.exists():
        O = json.load(open(po)); L = O["linear"]
        o = dict(radius_km=L["radius_km"], alpha=L["alpha"], n_samples=L["n_samples"],
                 error_std_pct=round(100 * L["error_std"] / L["J0"], 2),
                 storm=dict(center=L["storm"]["center"], reduction=round(L["storm"]["reduction"], 4)),
                 adjoint=dict(center=L["adjoint"]["center"], reduction=round(L["adjoint"]["reduction"], 4)),
                 random=dict(median=round(L["random"]["median"], 4), p90=round(L["random"]["p90"], 4)),
                 second=dict(center=L["second"]["center"], storm_only=round(L["second"]["storm_only"], 4),
                             with_adjoint_second=round(L["second"]["reduction_with_storm"], 4),
                             random_second_median=round(L["second"]["random_median"], 4),
                             random_second_p90=round(L["second"]["random_p90"], 4)))
        if O.get("verify"):
            keys = O["verify"][0].keys()
            o["verify"] = {k: dict(impact_err_pct=round(float(np.mean([abs(v[k]["J_err"]) for v in O["verify"]])) / O["truth_J"] * 100, 2),
                                   track_err_km=round(float(np.mean([v[k]["track_err_72h"] for v in O["verify"]])))) for k in keys}
            o["n_verify"] = len(O["verify"])
        out["osse"] = o
    return out or None


def _reference(work):
    p = work / "era5_rain.json"
    return json.load(open(p)) if p.exists() else None


def export(case, name, work, web_dir):
    lon, lat, levels = _grid(name)
    LON, LAT = np.meshgrid(lon, lat, indexing="ij")
    runs = json.load(open(work / f"runs_{name}.json"))
    G = np.load(work / f"grad_{name}.npz")
    N = np.load(work / f"nudge_{name}.npz")
    coef = {"u_component_of_wind": 1.0, "v_component_of_wind": 1.0, "temperature": CP / TR,
            "specific_humidity": LV ** 2 / (CP * TR)}
    dp = np.abs(np.gradient(levels)) * 100.0
    area = np.cos(np.deg2rad(LAT))                                    # relative area weight
    wmass = dp[:, None, None] * area[None]

    # sensitivity density: energy-norm magnitude of the gradient per tropospheric column, per unit area
    trop = levels >= TROPOSPHERE_TOP_HPA
    S = sum((G[k][trop] ** 2 / (coef[k] * wmass[trop])).sum(0) for k in PERTURB)
    S = np.sqrt(S / area)
    S = S / S.max()
    profile = {k: (lambda p: (p / p.max()).round(4).tolist() if p.max() > 0 else p.tolist())(
        np.sqrt((G[k][trop] ** 2 / (coef[k] * wmass[trop])).sum((1, 2)))) for k in PERTURB}

    def nudge_level(hpa):
        k = int(np.argmin(np.abs(levels - hpa)))
        T, u, v = N["temperature"][k], N["u_component_of_wind"][k], N["v_component_of_wind"][k]
        sp = np.hypot(u, v)
        arrows = [[round(((float(lon[i]) + 180) % 360) - 180, 2), round(float(lat[j]), 2), round(float(u[i, j]), 3),
                   round(float(v[i, j]), 3)] for i in range(len(lon)) for j in range(len(lat))
                  if sp[i, j] > 0.2 * sp.max() and SENS_BBOX[0] <= ((lon[i] + 180) % 360) - 180 <= SENS_BBOX[1]
                  and SENS_BBOX[2] <= lat[j] <= SENS_BBOX[3]]
        return dict(level_hpa=int(levels[k]), max_abs_T=round(float(np.abs(T).max()), 3),
                    max_wind=round(float(sp.max()), 3),
                    cells=_cells(T, lon, lat, SENS_BBOX, keep=lambda x: abs(x) > 0.05 * np.abs(T).max()),
                    arrows=arrows)

    J0 = runs["baseline"]["J"]
    k_peak = case.window.index(72) if 72 in case.window else len(case.window) // 2
    t_idx = case.window[k_peak] // case.every
    out_runs = []
    for rid, r in runs.items():
        F = np.load(work / f"fields_{name}_{rid}.npz")
        if case.objective == "rain":     # rain accumulated over the window (mm)
            imp = F["impact"][case.window[-1] // case.every] - F["impact"][case.window[0] // case.every]
        else:
            imp = F["impact"][t_idx]
        out_runs.append(dict(
            id=rid, label=RUN_LABELS.get(rid, rid), s=r["s"], J=round(r["J"], 4),
            change_pct=round(100 * (r["J"] / J0 - 1), 2),
            linear_change_pct=None if "J_linear" not in r else round(100 * (r["J_linear"] / J0 - 1), 2),
            track=[{k: p[k] for k in ("time", "lat", "lon", "err_km") if k in p} for p in r["track"]],
            energy_J=r.get("energy_J"),
            peak=None if ("peak" not in r or r["s"] == 0) else dict(
                T_K=round(r["peak"]["temperature"], 3),
                wind_ms=round(max(r["peak"]["u_component_of_wind"], r["peak"]["v_component_of_wind"]), 3),
                q_gkg=round(1e3 * r["peak"]["specific_humidity"], 3)),
            impact=dict(hour=case.window[-1] if case.objective == "rain" else case.window[k_peak],
                        from_hour=case.window[0] if case.objective == "rain" else None,
                        cells=_cells(imp, lon, lat, IMPACT_BBOX, keep=lambda x: x > 0.35 * float(imp.max()), digits=1)),
        ))
    bt = besttrack(case)
    base_track = runs["baseline"]["track"]
    errs = [p["err_km"] for p in base_track if "err_km" in p]
    win_errs = [p.get("err_km") for i, p in enumerate(base_track) if i * case.every in case.window]
    doc = dict(
        schema="ncrecon.butterfly/1",
        generated=datetime.date.today().isoformat(),
        case=dict(id=case.id, name=case.name, init=case.init, storm0=case.storm0, notes=case.notes,
                  target=dict(lat=case.target[0], lon=case.target[1], label=case.target_label, radius_km=case.radius_km),
                  objective=case.objective, objective_label=case.objective_label, window_hours=list(case.window),
                  objective_short=case.objective_short, impact_unit=case.impact_unit,
                  keep_out_km=case.keep_out_km, model=model_label(name),
                  analysis_error=dict(T_K=0.5, wind_ms=1.0, q_gkg=0.5, q_relative=0.10),
                  nudge_levels_hpa=[int(levels[trop].min()), int(levels[trop].max())]),
        best_track=[dict(time=str(t)[:16], lat=float(a), lon=float(b), wind_kt=None if np.isnan(w) else float(w),
                         pres_mb=None if np.isnan(p) else float(p))
                    for t, a, b, w, p in zip(bt.ISO_TIME, bt.LAT, bt.LON, bt.USA_WIND, bt.USA_PRES)],
        skill=dict(mean_track_err_km=round(float(np.mean(errs))) if errs else None,
                   window_track_err_km=win_errs),
        runs=out_runs,
        sensitivity=dict(cells=_cells(S, lon, lat, SENS_BBOX, keep=lambda x: x > 0.04),
                         levels_hpa=levels[trop].astype(int).tolist(), profile=profile),
        nudge=dict(levels=[nudge_level(500), nudge_level(850)]),
        rigor=_rigor(work, name, runs, case),
        reference=_reference(work),
    )
    web_dir.mkdir(parents=True, exist_ok=True)
    p = web_dir / f"{case.id}.json"
    p.write_text(json.dumps(doc, separators=(",", ":")))
    idx = web_dir / "index.json"
    cases = json.loads(idx.read_text()) if idx.exists() else []
    cases = [c for c in cases if c["id"] != case.id] + [dict(id=case.id, name=case.name, target=case.target_label)]
    idx.write_text(json.dumps(cases, indent=1))
    return p
