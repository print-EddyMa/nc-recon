# Groma damage model v0 (`groma-dmg-v0`): model card

*Status: research model. It is not wired into assessments. The xView2-trained
E1 classifier remains the optical channel until this model is better on
held-out events.*

## What it is

- **Inputs:** a before chip and an after chip of the same building, each 32 m
  square at 0.5 m, centred on the building.
- **Features:** a frozen ResNet-18 (ImageNet weights) reads both chips. The model
  uses 1,024 features (the after features and their difference from the
  before features), plus 15 colour statistics of the chip centre.
- **Classifier:** a standardised multinomial logistic regression with balanced
  class weights and C = 0.01.
- **Output:** a probability for each of FEMA's five damage levels: No damage,
  Affected, Minor, Major and Destroyed.
- **Code:** `ops/model/linear.py`, which stores the classifier as plain arrays
  in an `.npz` file; no pickles.

Code: `pipeline/src/terratriage/ops/model/` (imagery, dataset, net, train,
evaluate). Weights and data live in `pipeline/data/model/`, which is
git-ignored; they are not in the repository.

## Why it exists

E1 is trained on xBD, whose terms are non-commercial. A model trained only on
public-domain imagery and public labels carries no such restriction from its
data. That is what lets Groma use it in paid products later.

## Training data (every source and its licence)

| Role | Source | Licence |
|---|---|---|
| Before imagery | USDA NAIP 2022 (0.6 m, flown May 2022), via Microsoft Planetary Computer's open COGs | Public domain (USDA Farm Service Agency) |
| After imagery | NOAA NGS Emergency Response Imagery, flight 2025-01-28 (`2025_California_Fires`), read at 0.3 m from its overviews | US Government work (NOAA NGS) |
| Labels | CAL FIRE Damage Inspection (DINS), incident "Palisades" (January 2025) | State of California, provided as-is |

- **Encoder initialisation:** torchvision's ImageNet ResNet-18 weights. The
  torchvision code is BSD-3-Clause; the ImageNet images carry their own
  research terms. `--scratch` trains with no ImageNet initialisation for a
  strictly public-domain lineage.
- **Fields requested:** only damage level, structure type and incident name
  are requested from DINS. The layer's addresses, parcel numbers and assessed
  values are never fetched.
- **Training boxes:** two boxes in Pacific Palisades, `palisades_west` and
  `palisades_east`, each about 2.8 × 3.4 km. Before and after imagery are
  co-gridded on NAD83(2011) UTM 11N at 0.5 m.
- **Registration:** pre/post misregistration, measured by phase correlation at
  eight places, was under 1 m.

## Held-out rules

- **Eaton fire was never used for training or for any choice.** That includes
  the Altadena area (`altadena`, TEST in config/events.yaml).
- **Model selection used Palisades only:** the epoch, the chip size, the
  sampling and the temperature were all chosen on a spatial validation split
  of Palisades (300 m blocks, one in five).
- **Eaton was scored once,** after training was final, by
  `python -m terratriage.ops.model.evaluate`. That script refuses to overwrite
  an existing score, and no threshold or weight was chosen after seeing it.
- **Three failed attempts are recorded, not hidden.** All three were found on
  Palisades validation, never on Eaton. Their weights are kept under the names
  below.

  | Attempt | What it was | What went wrong | Kept as |
  |---|---|---|---|
  | 1 | Fine-tuned Siamese network, 48 m chips, class-weighted loss | Learned "burned street means Destroyed": 9 of 294 undamaged buildings recognised | `-attempt1-48m` |
  | 2 | Same, 32 m chips and balanced sampling | Still mostly Destroyed: 33 of 294 | `-attempt2-32m` |
  | 3 | Same, upsampled input and balanced-accuracy selection | Overfit: training loss 0.14, validation balanced accuracy 0.735 | `-attempt3-finetune` |

- **Choosing v0.** Three options were compared on the same validation blocks:

  | Option | Balanced accuracy, Destroyed vs rest |
  |---|---|
  | Colour statistics alone | 0.887 |
  | Frozen ImageNet features | 0.946 |
  | Both | 0.954 |

  The combination became v0 (C = 0.01 was also picked here). After every choice
  was made, the stored model was refit on all Palisades blocks.

## Results

Validation on Palisades (spatial blocks held out from that fit; 1,625
buildings):

| Measure | Value |
|---|---|
| Destroyed vs the rest, balanced accuracy | 0.948 (Destroyed recall 0.951, not-Destroyed recall 0.945) |
| Major or Destroyed | precision 0.975, recall 0.946, F1 0.96 |
| Five-level accuracy | 0.854; macro F1 over present levels 0.40 |

**Held-out: Eaton fire, Altadena (scored once, 2026-10-22).**
- **Imagery:** the Altadena TEST area's own imagery (NAIP May 2022 before, NOAA ERI
  2025-01-28 after, 0.3 m).
- **Labels:** CAL FIRE DINS "Eaton".
- **Coverage:** 3,373 inspections in the box, 3,079 scored. The rest had too
  little imagery around the point.

| Measure | All structures (3,079) | Homes only (1,872) |
|---|---|---|
| Major or Destroyed precision | 0.963 | 0.971 |
| Major or Destroyed recall | 0.938 | 0.955 |
| Major or Destroyed F1 | 0.95 | 0.963 |
| Destroyed vs the rest, balanced accuracy | 0.919 | 0.937 |
| Five-level accuracy | 0.839 | 0.846 |
| Macro F1 over present levels | 0.37 | 0.38 |

Of 600 inspections labelled No Damage in the Eaton box, 381 are called No
Damage and 42 are called Destroyed. The middle levels (Affected, Minor,
Major) are mostly confused with each other and with No Damage.

**Beside the current pipeline.** On the same area, the assessment pipeline (E1
xView2 classifier plus fusion, matched to DINS by footprint) scores Major or
Destroyed precision 0.906, recall 0.781, F1 0.839 (homes: F1 0.855). Its
figures come from `data/output/ops/altadena.field_reference.json`.

The two are not computed identically. The pipeline is scored building by
building after footprint matching (2,246 matched). This model is scored on
chips centred on the DINS points, which skips footprint matching and its
errors. A like-for-like comparison runs this model inside the pipeline on the
same footprints. That is the next step before it can replace E1.

## Pre-registered evaluation: M1 on the pipeline's footprints (Altadena)

Written 2026-10-22, before the run. One run; its result is reported
whatever it shows, and nothing below changes after it.

**Question.** On the wildfire TEST area Altadena, using the same buildings,
the same CAL FIRE DINS records and the same matching rule as the pipeline's
current comparison, is v0 (as evidence channel M1) better than the current
optical chain? If so, M1 replaces E1 in the wildfire hazard profile.

**Mode evaluated: replace, in its plainest form.** M1's own call stands in
for the optical chain's call. M1 is not fused with E2, H or the rest, and
"alongside" is not evaluated here.

**Exclusion statement.** No Eaton or Altadena structure, label or imagery was
used for training, feature or chip-size choice, checkpoint selection,
thresholds or temperature; all of these were fixed on Palisades. (v0 has no
temperature. Its regularisation strength was also fixed on Palisades.)

**What is already known (disclosed).** Before this pre-registration, v0 was
scored once on Eaton chips centred on DINS points (Major-or-Destroyed F1
0.95, above). That score chose nothing: the weights, chip size and features
were all fixed on Palisades. This run asks a different question: v0 on the
pipeline's own footprints and matching.

**Frozen inputs (sha256).**

| Item | sha256 |
|---|---|
| `data/model/weights/groma-dmg-v0.npz` | 5abdb8362259713af9ff074a93129e897b228b41f914ce9d9c7e4af05d2e7222 |
| `data/model/weights/groma-dmg-v0.json` | 3c92fa924d0f59553c8d7316691a0c7d1fcb789dec1fd699ba50b00b9012b77c |
| torchvision `resnet18-f37072fd.pth` (frozen encoder) | f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec |
| `data/raw/altadena/pre_2022-05-05_2022-05-11.tif` | 5a4590edc3e3cdf67694e9e8f877f8e383092949044990d13e4dc45200712808 |
| `data/raw/altadena/post_2025-01-28.tif` | 60703e449388d93e3bb94a290e48a2886c526321d9b281328f2c9791dc2b4164 |
| `data/output/ops/altadena.geojson` (the pipeline's footprints and calls) | 28dc55775cd551ce5ebee6cd7f26dc69cc038ccfc2e9d690df7fafb53138e5b3 |
| `data/output/ops/altadena.field_reference.json` (baseline) | 1ab2d3f6918ae17d7a3c903a1ad56cff91293e63a3bf16ed1e6f9570c83cbbb6 |
| `ops/model/channel.py` | 32b847e68b2d827bd942142b478c26664a0aa855d8f2211a56106e51944d6daa |
| `ops/model/linear.py` | e6abe6f6012e99988bd2679dd10b0f03059b297514b2667035f38b06158044a1 |
| `ops/model/dataset.py` | c720604e6005080ced484c18d944b86b8b3b30bd5aaa836de44a2b22c1414a4f |
| `ops/analyze/field_reference.py` | 9252bf2d6d5f6187ab98012318cfd35ceec5b3fd6c197b2bc5821831759093d7 |
| `ops/analyze/sarcop_reference.py` | bdcd9bc43292b2fb7f056c4c0e9de683830bb1f63143d8582229fd22ba3791a6 |

The two comparison files differ from HEAD 5117723 only in where they read
their output folder (`NCR_OPS_OUT`). Their matching logic is the logic that
produced the baseline.

**Procedure.**
1. **Scratch environment.** Set NCR_OPS_OUT, NCR_OPS_REGISTRY, NCR_JOBS_FILE,
   NCR_LABELS_DIR, NCR_TRUTH_DIR and NCR_AUDIT_LOG to a fresh scratch
   directory. Copy `altadena.geojson` there. The live data/output/ops is only
   read, and is checked byte-identical afterwards.
2. **Score.** For every building with a footprint, call
   `channel.m1_probs(pre, post, footprints)`. Chips are 32 m at 64 px, centred on
   the footprint centroid, with no per-building shift and max no-data 0.2.
3. **Replace the calls.** In the scratch copy, replace each building's
   `damage_probs` with M1's probabilities and `damage_level` with their
   argmax. This is M1 standalone, with no fusion and no abstention. A building
   with no usable M1 chip keeps the pipeline's call, so the matched set
   stays identical.
4. **Compare.** Run `field_reference.compare_area("altadena", "dins",
   allow_test=True)` on the scratch copy. That reuses the cached DINS points
   (same event and bounding box key), the 15 m match and "latest record wins".

**Measures.**
- **Primary:** Major-or-Destroyed F1 over all matched structures
  (`summary.major_or_destroyed.f1`).
- **Also reported:** that measure's precision and recall, and five-level
  agreement (`summary.same_level`).
- **Fallback count (reported, decides nothing):** the number and share of
  matched buildings with no usable M1 chip, which kept the pipeline's call.
- **Baseline:** F1 0.839 (precision 0.906, recall 0.781), five-level agreement
  0.747, 2,246 matched.

**Decision rule (wildfire only, fixed now).**
- **Replace E1 with M1 in the wildfire profile** if both hold: M1's F1 ≥
  0.869 (baseline + 0.03), and M1's precision ≥ 0.886 (baseline − 0.02).
- **Otherwise keep E1.**
- Homes-only F1, same-level agreement and kappa are reported but decide
  nothing.

**What a "replace" does and does not claim.** It compares M1 alone with the
current fused chain on one TEST area. A pipeline with M1 fused in must still
be scored on a fresh fire before any accuracy claim.

**After this run, Altadena is no longer a clean hold-out** for M1's next
version or for any fused pipeline that uses it.

### Result (run once, 2026-10-22)

| Measure | M1 standalone | Current chain (baseline) |
|---|---|---|
| Matched structures | 2,246 | 2,246 |
| Major or Destroyed precision | **0.957** | 0.906 |
| Major or Destroyed recall | **0.942** | 0.781 |
| Major or Destroyed F1 (primary) | **0.949** | 0.839 |
| Five-level agreement | 0.824 | 0.747 |
| Kappa | 0.613 | 0.459 |
| Homes only (1,533): Major or Destroyed F1 | 0.962 (P 0.969, R 0.955) | 0.855 (P 0.934, R 0.789) |
| Homes only: five-level agreement | 0.834 | 0.763 |

**Fallback:** 14 of 2,246 matched buildings (0.6%) had no usable M1 chip and
kept the pipeline's call. Across all 2,558 assessed buildings, 24 had no
usable chip.

**Decision under the pre-registered rule:** F1 0.949 ≥ 0.869 and precision
0.957 ≥ 0.886, so the decision is **replace**. M1 replaces E1 in the wildfire
hazard profile.

Where M1 still misses, by DINS level (rows) and M1's call (columns):
- **DINS No Damage (544):** 310 called No Damage, 135 Affected, 56 Minor,
  6 Major, 37 Destroyed.
- **DINS Destroyed (1,602):** 1,515 called Destroyed, 31 No Damage, 36 Affected,
  20 Minor.
- **The middle levels stay weak**, as on Palisades.

**Run record:**
- The result is in `data/model/weights/groma-dmg-v0.prereg.altadena.json`
  (sha256 74979064a90ac93525487a8ebc7d19dff55c132f1d44774c22dcdbe73129abc3).
- The run happened in a scratch output folder. The live `data/output/ops` (37
  files) had identical sha256 hashes before and after.

**What this does not show:**
- It is M1 alone against the fused chain on one TEST area, which shares the
  windstorm, the ERI flight and the NAIP vintage with the training fire.
- The fused pipeline with M1 in "replace" mode still has to be scored on a
  fresh wildfire before any accuracy claim.
- Altadena is now spent as a hold-out for M1.

## Encoder weights

- **Where they come from:** v0's frozen encoder is torchvision's ImageNet
  ResNet-18, file `resnet18-f37072fd.pth` (sha256
  f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec, about
  45 MB). It is not in the repository: it is torchvision's file, under its
  own terms.
- **No download while assessing.** `channel.load()` looks for the file only on
  disk (`$TORCH_HOME/hub/checkpoints/`, else `~/.cache/torch/hub/checkpoints/`)
  and checks its sha256. When the file is absent or wrong it raises
  FileNotFoundError ("resnet18 encoder weights not on this machine"), and the
  pipeline marks M1 unavailable (`M1_WEIGHTS_MISSING`); E1 then carries the
  optical evidence.
- **Staging a machine:** once, on a networked machine:

  ```
  python -m terratriage.ops.model.fetch_encoder
  ```

  It downloads the file and installs it only if the sha256 matches. To stage
  an offline laptop or an offline pack, copy the file into the same folder
  there.
- **Unchanged features:** loading from the local file gives the same
  features as before; the maximum difference on test input was 0.0.

## Release and licence (launch, 2026-10-26)

* **Groma's wildfire model** (`pipeline/data/model/weights/groma-dmg-v0.npz`
  and `.json`) ships with the code under Apache-2.0. Its encoder is the
  torchvision ResNet-18 ImageNet checkpoint (BSD-3), downloaded and
  SHA-256-checked at install (`terratriage.ops.model.fetch_encoder`); the
  Docker image builds it in.
* **The general image model** used for flood and wind (xView2 CMU baseline,
  trained on xBD) is not redistributed: the Docker build downloads it from the
  public xView2 baseline release, checks its SHA-256 and converts it to ONNX.
  Its terms are non-commercial, which fits Groma while it is free. **Before any
  paid plan**, flood and wind need a model trained only on commercially usable
  data, the way the wildfire model was.
* **What is measured:** only the wildfire model, once, on Eaton (above). The
  full pipeline with it has not yet been scored on a new fire, and flood,
  wind, earthquake and landslide calls are not validated. Every product says
  so where its numbers appear.

## Limits

- **One hazard, one region:** wildfire, Southern California, one post-event
  flight. It has not been tested on wind, flood or earthquake damage.
- **Eaton is a separate fire, not a separate domain.** Both fires burned in the
  same January 2025 windstorm, the after imagery for both comes from the same
  NOAA ERI flight (2025-01-28), and the before imagery is the same NAIP
  vintage. The Eaton scores show the model works on unseen buildings in that
  setting; expect lower scores on another event, sensor or season.
- **The middle levels are rare in DINS** (Affected, Minor and Major are a few
  percent of inspections), so the model mostly separates Destroyed from the
  rest. Read its Minor and Major probabilities as weak.
- **The labels have their own limits.** DINS points sit on or near the
  structure. Outbuildings ("Utility Misc Structure") are in the labels and are
  harder to see.
- **The resolutions differ.** NAIP before (0.6 m, leaf-on) and ERI after
  (0.3 m resampled to 0.5 m) come from different sensors. Colour and gain
  augmentation stand in for that, and only partly.
- **Its probabilities are fitted on Palisades:** the logistic regression was
  fit there with balanced class weights, and they are not calibrated
  elsewhere.

## Next

- Add hurricane, flood and tornado events from FEMA's historical geospatial
  damage assessments (imagery-observed records) paired with NOAA ERI imagery
  and NAIP: Michael 2018, Laura 2020, Harvey 2017, Joplin 2011.
- Train the `--scratch` variant.
- Compare with E1 on the same held-out buildings.
