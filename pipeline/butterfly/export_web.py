"""Export a case's results to one compact JSON the NC Recon web app reads
(`web/public/data/butterfly/<case>.json`). Schema: `ncrecon.butterfly/1`
(mirrored in `web/src/lib/butterfly.ts`)."""
import json, datetime
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
        imp = F["impact"][t_idx]
        out_runs.append(dict(
            id=rid, label=RUN_LABELS.get(rid, rid), s=r["s"], J=round(r["J"], 4),
            change_pct=round(100 * (r["J"] / J0 - 1), 2),
            linear_change_pct=None if "J_linear" not in r else round(100 * (r["J_linear"] / J0 - 1), 2),
            track=[{k: p[k] for k in ("time", "lat", "lon", "err_km") if k in p} for p in r["track"]],
            energy_J=r.get("energy_J"),
            peak=None if "peak" not in r else dict(
                T_K=round(r["peak"]["temperature"], 3),
                wind_ms=round(max(r["peak"]["u_component_of_wind"], r["peak"]["v_component_of_wind"]), 3),
                q_gkg=round(1e3 * r["peak"]["specific_humidity"], 3)),
            impact=dict(hour=case.window[k_peak],
                        cells=_cells(imp, lon, lat, IMPACT_BBOX, keep=lambda x: x > 0.15 * float(imp.max()), digits=1)),
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
                  keep_out_km=case.keep_out_km, model=f"NeuralGCM {name.replace('_', ' ').replace(' deg', '°')}",
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
    )
    web_dir.mkdir(parents=True, exist_ok=True)
    p = web_dir / f"{case.id}.json"
    p.write_text(json.dumps(doc, separators=(",", ":")))
    idx = web_dir / "index.json"
    cases = json.loads(idx.read_text()) if idx.exists() else []
    cases = [c for c in cases if c["id"] != case.id] + [dict(id=case.id, name=case.name, target=case.target_label)]
    idx.write_text(json.dumps(cases, indent=1))
    return p
