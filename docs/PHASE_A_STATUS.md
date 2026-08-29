# Phase A status — 2026-08-29

## TL;DR

The pipeline runs end-to-end on **real Hurricane Helene Maxar imagery** and emits
contract-compliant GeoJSON for Old Fort and Spruce Pine, NC. The damage classes
currently come from a **change-detection heuristic**, not a trained CNN, because
both published xView2 model releases are unusable as-is from this machine. Every
output is labelled with which scorer produced it (`model` field in the GeoJSON
`properties`), so nothing is passed off as more than it is.

## What works

- **Data acquisition** (`src/terratriage/download.py`) — resolves a lat/lon to
  the Maxar ARD tile(s) covering it via the opengeos/maxar-open-data STAC TSV,
  picks the nearest pre- and post-event captures, downloads the `visual` COGs.
  Verified:
  - Old Fort: pre 2022-01-07, post 2024-10-05 (quadkey 031133303032, UTM 17N)
  - Spruce Pine: pre 2024-02-03, post 2024-10-05 (quadkey 031133301300)
- **Footprints** (`footprints.py`) — OSM buildings via Overpass, clipped to the
  raster footprint, reprojected to the raster CRS. 766 / 139 buildings for the
  two AOIs.
- **Geo core** (`geo.py`) — 1024 px tiling that tracks each tile's affine
  transform; feathered mask stitching; connected-component polygonisation with
  per-component majority damage class; reprojection to EPSG:4326.
- **Contract** (`contract.py`) — schema, damage scale + colour ramp, `validate()`.
- **Two pipelines**:
  - `predict_footprints.py` (primary) — footprints + `classify.py` per-building.
  - `predict.py` (segmentation) — tiled loc+cls ensemble → fuse → polygonise.
- **xView2 1st-place architecture port** (`models/unet.py`, `models/ensemble.py`)
  — all six architectures (res34 / se_resnext50 / dpn92 / senet154, Loc + Double)
  rebuilt on torch 2.13, forward-pass verified. Checkpoint loader matches the
  reference (`module.` strip, size-tolerant). Ready the moment real weights exist.

## What's blocked, and why

### 1. xView2 1st-place weights — dead link

`https://vdurnov.s3.amazonaws.com/xview2_1st_weights.zip` → `403 AccessDenied`
(bucket owner revoked public read). Confirmed against the us-west-1 endpoint too.
The mirror repo, `xView2-deploy`, and `xView2_FDNY` all point at the same URL.
The Wayback Machine has two 200 snapshots (2020-09-04, 2020-12-12) but
`web.archive.org` is unreachable from this environment (curl, WebFetch, and the
browser extension all fail). **If someone downloads that zip on a normal network
and drops it in `pipeline/weights/`, the segmentation path lights up with no
further work** (`scripts/run.py infer-seg --area old_fort --weights-dir weights`).

Also: even with the weights, the original repo needs `torch==1.1` + NVIDIA
`apex` + 2×12 GB GPUs. Our port removes the apex/old-torch dependency; on this
CPU-only ARM Mac the `fast` preset (2 models) is the only practical one, ~minutes
per 1024 tile.

### 2. xView2 baseline classifier — framework/arch mismatch

`weights/classification.hdf5` (474 MB) downloaded fine from the live GitHub
release. It is **Keras 2.2.5, weights-only** (no architecture in the file). The
model is `ResNet50(imagenet, frozen) ‖ 3-conv CNN → concat → Dense[2024,524,124,4]`.

Blocker: the file's ResNet50 uses **v1** block structure and old layer names
(`res2a_branch2a`, `bn_conv1`, …); TF 2.15's `keras.applications.ResNet50` is
**v1.5** (stride moved to the 3×3) with new names (`conv2_block1_1_conv`, …).
`load_weights(by_name=False)` needs an exact topology match; `by_name=True`
misaligns and silently drops most tensors. Reconstruction attempt in
`src/terratriage/_keras_infer.py`.

**To finish it:** hand-build ResNet50-**v1** in `_keras_infer.py` (stride on the
first 1×1 of each stage's conv block; layer names matching the h5 groups) and
load with `by_name=True`. ~1–2 h, mechanical. Not done because Phase B is the
bigger risk to the deliverable and the heuristic keeps the pipeline honest and
working in the meantime.

### 3. xView2 baseline localisation — Chainer

`weights/localization.h5` is a Chainer `save_npz` archive (`c1/W.npy`,
`bnc0/beta.npy`, …) — motokimura's SpaceNet U-Net. Chainer is EOL. Not pursued:
OSM footprints are more accurate and current than this model would be, and carry
no framework baggage. The `.npy` arrays could be loaded into a hand-written
NumPy/torch U-Net forward pass if a learned localiser is ever wanted.

## Recommended next steps (in order)

1. **Get the 1st-place zip** onto the machine out-of-band → segmentation path
   works, best accuracy.
2. Else **finish the baseline classifier** (ResNet50-v1 rebuild) → real trained
   damage classes on OSM footprints.
3. Else **fine-tune** `Dhyanesh18/xview2-damage-assesment-siamese-unet` (modern
   PyTorch Siamese U-Net, MPS-capable) on an xBD flood subset — few hours.
4. Recalibrate the heuristic against the validation maps regardless; it's the
   safety net.
