# Phase A status — 2026-08-29

## TL;DR

The pipeline runs end-to-end on **real Hurricane Helene Maxar imagery** and emits
contract-compliant GeoJSON for Old Fort and Spruce Pine, NC. Damage classes now
come from the **xView2 CMU baseline classifier** (ResNet50-v1 + CNN head, trained
on xBD) — its weights-only Keras 2.2.5 HDF5 was successfully reconstructed and
loaded (see "Baseline classifier — RESOLVED" below). A change-detection heuristic
remains as an offline fallback. Every output is labelled with which scorer
produced it (`model` field in the GeoJSON `properties`).

Current outputs (auto backend = keras):
- Old Fort — 766 buildings: 345 none / 275 minor / 78 major / 68 destroyed (19% severe)
- Spruce Pine — 139 buildings: 104 / 33 / 1 / 1 (1% severe)

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

### 2. xView2 baseline classifier — RESOLVED

`weights/classification.hdf5` (474 MB) is **Keras 2.2.5, weights-only**. The model
is `ResNet50-v1(imagenet, frozen) ‖ 3-conv CNN → concat → Dense[2024,524,124,4]`,
input a single 128×128 **post**-disaster crop, `relu` output + argmax.

The blocker was that TF 2.15's `keras.applications.ResNet50` is **v1.5** (stride on
the 3×3, new layer names), incompatible with the file's **v1** ResNet50
(`res2a_branch2a`, `bn_conv1`, stride on the first 1×1, every conv has a bias).

Fixed by hand-rebuilding ResNet50-v1 in `src/terratriage/_keras_infer.py`,
name-for-name against the 106 HDF5 sublayers, wrapped as a submodel `resnet50`,
loaded with `by_name=True`. `_keras_verify.py` confirms every checked tensor
(stem, stage-3/5 convs, BN, custom convs, all 4 Dense) matches the HDF5 exactly
(maxΔ = 0). Runs on CPU: ~60 s for 766 buildings.

Preprocessing replicates `model/damage_inference.py`: `ImageDataGenerator(rescale=1.4)`
on raw pixels, fed to both branches (no caffe `preprocess_input`).

Caveats: this is the *baseline* (single-image post-only classifier), not the
1st-place Siamese ensemble; trained on xBD, so a 2022→2024 cross-season pre/post
pair is off-distribution. Still, it is the genuine trained model, faithfully
loaded.

### 3. xView2 baseline localisation — Chainer

`weights/localization.h5` is a Chainer `save_npz` archive (`c1/W.npy`,
`bnc0/beta.npy`, …) — motokimura's SpaceNet U-Net. Chainer is EOL. Not pursued:
OSM footprints are more accurate and current than this model would be, and carry
no framework baggage. The `.npy` arrays could be loaded into a hand-written
NumPy/torch U-Net forward pass if a learned localiser is ever wanted.

## Recommended next steps (in order)

1. ~~Finish the baseline classifier~~ — **DONE**, it's the default backend now.
2. **Get the 1st-place zip** onto the machine out-of-band → the Siamese
   segmentation ensemble (`scripts/run.py infer-seg`) lights up; highest accuracy,
   uses pre *and* post. Architectures already ported.
3. Optionally **fine-tune** `Dhyanesh18/xview2-damage-assesment-siamese-unet`
   (modern PyTorch Siamese U-Net, MPS-capable) on an xBD flood subset for a
   pre/post model without the framework baggage — few hours.
4. Compare the baseline-classifier map against news coverage of Old Fort /
   Spruce Pine (validation HTMLs in `data/output/`) and tune the crop size /
   `pad` in `classify.extract_crops` if footprints look mis-cropped.
