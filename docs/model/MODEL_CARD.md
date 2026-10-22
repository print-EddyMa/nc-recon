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
data. That is what lets Groma use it in paid products (see
docs/strategy/BUSINESS_MODEL.md).

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
- **It is uncalibrated outside Palisades:** the temperature was fitted on
  Palisades validation.

## Next

- Add hurricane, flood and tornado events from FEMA's historical geospatial
  damage assessments (imagery-observed records) paired with NOAA ERI imagery
  and NAIP: Michael 2018, Laura 2020, Harvey 2017, Joplin 2011.
- Train the `--scratch` variant.
- Compare with E1 on the same held-out buildings.
