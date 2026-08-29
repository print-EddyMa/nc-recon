# TerraTriage — Phase A (model & data pipeline)

Turns a **pre/post satellite image pair** of a disaster area into a **GeoJSON of
building footprints, each tagged with a 0–3 damage class**, geo-referenced to real
lon/lat. That GeoJSON is the only thing Phase B (the web app) consumes — see
[`src/terratriage/contract.py`](src/terratriage/contract.py) for the exact schema.

Demo case: **Hurricane Helene**, western North Carolina, Sept–Oct 2024
(Old Fort & Spruce Pine).

## Quick start

```bash
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/pip install torch torchvision            # only for the segmentation path

# 1. pull Maxar Open Data pre/post imagery for an AOI
./.venv/bin/python scripts/run.py fetch --area old_fort --lat 35.6293 --lon -82.1804
./.venv/bin/python scripts/run.py fetch --area spruce_pine --lat 35.9151 --lon -82.0643

# 2. run the pipeline  -> data/output/<area>.geojson
./.venv/bin/python scripts/run.py infer --area old_fort            # heuristic scorer
./.venv/bin/python scripts/run.py infer --area old_fort --backend keras   # xView2 baseline CNN (needs TF env, see below)

# 3. eyeball it  -> data/output/<area>_check.html
./.venv/bin/python scripts/run.py validate --area old_fort
```

## How it works

```
pre.tif + post.tif
   │
   ├─ footprints.py   OSM buildings (Overpass) for the AOI, clipped, in raster CRS
   │
   ├─ classify.py     per-building 128 px pre/post crop  ─►  damage class 0..3
   │                     backend=heuristic : structure-loss change detection (offline)
   │                     backend=keras     : xView2 CMU baseline (ResNet50+CNN head)
   │
   └─ predict_footprints.py   footprints + classes  ─►  contract.collection()  ─►  GeoJSON
```

There is a second, fully-built path — `scripts/run.py infer-seg` — that runs the
**xView2 1st-place architecture** (Siamese U-Nets, 4 encoder families, ported to
torch 2.x in `src/terratriage/models/`) as a tiled segmentation ensemble. It is
wired and smoke-tested but **parked**: the published weights are offline (see
STATUS below). With `--mock` it runs a heuristic ensemble so the tiling /
stitching / fusion / polygonisation code stays exercised.

## Status / what's blocked

See [`../docs/PHASE_A_STATUS.md`](../docs/PHASE_A_STATUS.md) for the full account.
Short version:

| Component | State |
|---|---|
| Maxar Helene imagery download | ✅ working (Old Fort, Spruce Pine, pre+post) |
| Tiling + geo-referencing + polygonisation + contract | ✅ working, tested |
| OSM footprints | ✅ working (766 buildings Old Fort, 139 Spruce Pine) |
| Heuristic damage scorer | ✅ working end-to-end on real imagery |
| xView2 **1st-place** weights | ⛔ `vdurnov.s3` returns AccessDenied; Wayback copy exists but archive.org unreachable here. Architecture ported & ready if the zip turns up. |
| xView2 **baseline** classifier weights | ⚠️ downloaded (`weights/classification.hdf5`), but it's Keras 2.2.5 weights-only with a ResNet50 **v1** whose layer layout doesn't match TF2's `keras.applications.ResNet50` (v1.5). Loader in `_keras_infer.py`; needs a hand-built ResNet50-v1 to finish. |
| xView2 **baseline** localisation weights | ⚠️ `weights/localization.h5` is a **Chainer** `save_npz` (dead framework) — superseded by OSM footprints. |

## TF env for `--backend keras`

```bash
conda create -y -n terratriage-tf python=3.11
conda run -n terratriage-tf pip install "tensorflow==2.15.1" "numpy<2" pillow
```
`classify.py` shells out to this env automatically.
