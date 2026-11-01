# Butterfly - storm sensitivity for NC Recon

> *Which small differences in the weather three days earlier would have changed
> what Hurricane Helene did to western North Carolina?*

NC Recon's risk monitor shows **what** is coming and the damage pipeline shows
**what happened**. Butterfly asks **why**: how sensitive an NC storm impact was
to the state of the atmosphere days before. It backpropagates through a real,
differentiable weather model (**NeuralGCM**) started from the real atmosphere
(**ERA5**), and then checks every answer with full forecasts.

That is the question operational forecasters answer when deciding where extra
observations (hurricane-hunter aircraft, dropsondes) would improve a forecast
most. It is a sensitivity diagnostic, **not a weather-control tool**.

The web screen is `#/butterfly` (**g** then **b**); it reads
`web/public/data/butterfly/<case>.json`, written by this package.

## What it does

```
ERA5 (real atmosphere, 37 levels, 0.25°)  ─ regrid ─►  NeuralGCM 2.8° encode
        │                                                     │  78 h forecast (hourly, checkpointed)
        │                                                     ▼
        │                                     J = mean over +60…78 h of moisture transport (IVT)
        │                                         into western NC (Gaussian, 220 km, Asheville/Old Fort)
        │                                                     │
        └──────────── ∂J / ∂(T, u, v, q at t0)  ◄── adjoint ──┘     (problem.py)
                              │
          steepest-descent nudge in the moist total-energy norm,
          zero within 600 km of the storm, peak ≤ s × analysis error
                              │
          full nonlinear re-forecasts for s = 0.25, 0.5, 1 and the reversed nudge   (run.py steer)
                              │
          export ─► web/public/data/butterfly/helene.json                           (export_web.py)
```

- **Observable-space perturbations.** The nudge is applied to the ERA5 fields
  themselves (temperature, winds, humidity on pressure levels), so its size is
  stated in K, m/s and g/kg and compared with typical analysis uncertainty
  (~0.5 K, 1 m/s, 0.5 g/kg; rough ERA5 tropical magnitudes, not exact error bars).
- **Energy norm.** Gradients are turned into directions with the moist
  total-energy norm (Ehrendorfer et al. 1999), the norm ECMWF uses for singular
  vectors, so K, m/s and kg/kg are comparable.
- **Gradient checkpointing.** Plain reverse-mode through 78 h of NeuralGCM
  needs ~124 GB; stepping hour-by-hour under `jax.checkpoint` inside a
  `lax.scan` brings it under ~10 GB on CPU.
- **Verified, not linearised.** Every number on the web screen comes from a full
  nonlinear forecast with the nudge put back in.

## Run it

```bash
cd pipeline
python -m venv .venv-butterfly && ./.venv-butterfly/bin/pip install -r butterfly/requirements.txt
mkdir -p butterfly/work/models
gsutil cp gs://neuralgcm/models/v1/deterministic_2_8_deg.pkl butterfly/work/models/

./.venv-butterfly/bin/python -m butterfly.run forecast --case helene   # hindcast only (~10 min CPU)
./.venv-butterfly/bin/python -m butterfly.run all --case helene        # adjoint + 5 forecasts + export
```

ERA5 is read anonymously from Google's public ARCO-ERA5 bucket (~1 GB per
start time, cached in `work/era5/`); the NOAA IBTrACS best track is downloaded
and cached on first use. CPU timings (4 cores): one 78-h forecast ≈ 8-10 min,
the adjoint ≈ 30-60 min.

Cases live in `cases.py`: `helene` (the NC case shown in the app) and `milton`
(an out-of-state validation case: wind energy over Tampa Bay).

### Safety note on checkpoints

NeuralGCM checkpoints are Python pickles. `safe_load.py` loads them with a
whitelist unpickler that only allows numpy's array reconstructor, `ndarray`
and `dtype` (what a static `pickletools` scan of the published files shows they
contain) and raises on anything else, instead of a bare `pickle.load`.

### Version pins that matter

`neuralgcm` 1.2.2 works with `jax` 0.6.x on CPU. `encode()` / `advance()` /
`decode()` take forcings **without** a time axis (they add their own);
`unroll()` takes them **with** one.

## The toy model ("lie detector")

`toy/` is where the method was developed: a 2-D β-plane vortex "atmosphere"
where the exact adjoint is available, so an AI emulator's gradients can be
graded against the truth. Findings (8 unseen storms; figures in `docs/butterfly/`):

- optimised nudges at 0.1-1 % of the storm's energy move it 6-8× further than
  random nudges of the same energy;
- searching through the AI emulator recovers ~75-100 % of what the exact adjoint
  finds, but **systematically over-promises** by 5-10 points;
- a good forecast does not guarantee a good gradient: on one storm the
  emulator tracked well, yet its sensitivity map had cosine similarity −0.03
  with the truth.

```bash
cd pipeline/butterfly/toy
python data.py && python emulator.py && python experiments.py && python hero.py && python render.py
```

## Limits (read before quoting a number)

- **2.8° (~300 km) model.** Track and large-scale moisture are meaningful;
  the storm's core and intensity are not resolved.
- **Same-model check.** Nudges are verified by the model that designed them.
  The independent check is a physics model (WRF), not yet run.
- **One NC storm** is a case study, not a statistic.
- Nudges are idealised changes to the initial state; nothing here says any
  real-world intervention could produce them.
