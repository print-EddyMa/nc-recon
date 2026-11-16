# NC Recon pipeline and service

Python 3.13. Two things live here:

* `src/terratriage/ops/`, the operational pipeline (what the product runs), and
  `server.py`, the FastAPI service that exposes it under `/ops` and serves the
  built web app.
* The older demo path (`run.py fetch | infer | infer-seg | validate`,
  `predict_footprints.py`, `models/`): the 4-class xView2 pipeline behind the
  offline pitch demo. Kept working, not used by the product.

Root [`README.md`](../README.md) covers deployment; this file is for working
on the pipeline.

## Set up and run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp /path/to/xview2_cmu_classifier.onnx weights/      # damage model, not in git

NCR_DEV_OPEN=1 .venv/bin/python server.py           # http://127.0.0.1:8000, auth off (local only)
.venv/bin/python -m pytest tests -q                  # offline; `-m live` hits the real upstreams
```

The tests read the committed config and any assessment outputs on disk, but
keep their registry, job list and audit log in a temporary directory. They are
safe to run beside a working server.

## One assessment, by hand

The service runs these same commands as a job (`ops/jobs.py`):

```bash
R=".venv/bin/python scripts/run.py"
$R ops-health                                        # every data source: ok / stale / down
$R ops-fetch  --area town --lon -82.009 --lat 35.684 --half-m 400 --post nc_helene_2025
$R ops-assess --area town                            # -> data/output/ops/town.geojson
$R ops-impact --area town                            # people, tract need index
$R ops-brief  --area town                            # one-page brief (HTML + text)
$R ops-export --area town                            # GeoJSON, CSV, KML, GPKG, FileGDB, Survey123
$R ops-aggregate --area town                         # public tract product, small counts withheld
```

`ops-assess` needs the area in `config/events.yaml` (TUNE / TEST) or in the
operational registry (`data/ops_registry.yaml`, written by the service when an
analyst starts an assessment). After labeling: `ops-eval`, then `ops-calibrate`
(TUNE labels only). `ops-backup` archives labels, registry and outputs.

## Layout

```
server.py                    FastAPI app: /ops API, live-feed proxy, static web app
scripts/run.py               CLI for every step above
config/
  events.yaml                events, imagery windows, TUNE / TEST areas
  context_rules.yaml         evidence weights, masks, review rules (provisional until labels exist)
  crosswalks.yaml            xBD -> FEMA classes, class prior
  damage_matrices/           FEMA PDA flood-depth matrix
  seeds/                     OpenFEMA declarations shipped for offline start
src/terratriage/ops/
  plan/events.py             event registry, incident dates from OpenFEMA, window checks
  collect/                   connectors (USGS, NWPS, NWS, OpenFEMA, NSI, USA Structures,
                             NC OneMap orthos, NOAA ERI), each with a health probe
  process/                   imagery pairs, co-registration, footprint alignment, structures
  analyze/                   evidence channels, fusion, calibration, evaluation, impact
  disseminate/               exports, brief, public aggregates, map tiles
  pipeline.py                ops-assess: one area end to end
  jobs.py                    assessment queue: one at a time, persisted, cancellable
  api.py auth.py audit.py    HTTP API, fail-closed access control, audit trail
data/                        runtime state (git-ignored): raw imagery, outputs, labels,
                             registry, jobs.json, audit.log, caches
tests/                       pytest
```

## Things that will bite you

* **One server per data directory.** At start-up the server treats any
  half-registered operational area as left over from a crash and removes it.
* **Dates are asserted, not assumed.** A pre image must be before the
  incident and a post image on or after it, or the run stops
  (`plan/events.py`). Incident dates come from the federal declaration.
* **Hold-out areas.** TEST areas (`config/events.yaml`) are never used to
  choose a threshold, and their image chips are not looked at before they are
  labeled. See `docs/ops/LABELING_PROTOCOL.md`.
* **Nothing is measured in Web Mercator.** Analysis runs in the imagery's
  projected CRS; `ops/geodesy.py` refuses otherwise. The map tiles in
  `disseminate/tiles.py` are pictures only.
* **Structure ids are stable.** `ncr_id` is a UUID5 of source + source id
  (multi-part buildings: `<id>/1`, ...). Labels are keyed by it and survive a
  re-run.

## Demo path (legacy)

`run.py fetch` pulls a Maxar Open Data pair, `run.py infer` writes the 4-class
contract GeoJSON (`contract.py`) from OSM footprints and the xView2 baseline
classifier, `scripts/make_tiles.py` cuts its imagery tiles. `infer-seg` runs
the ported xView2 1st-place Siamese U-Nets when their weights are present in
`weights/` (see `weights/README.md`); with `--mock` it exercises the tiling
and polygonising code without them. The Keras fallback for the classifier
needs the `terratriage-tf` conda env (TensorFlow 2.15); the ONNX model does
not.
