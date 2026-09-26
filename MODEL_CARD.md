# Model card: NC Recon damage assessment (ops mode, fusion v1)

*Format after Mitchell et al. 2019. Last updated 2026-09-26.*

## Components

| Part | What it is | Status |
|---|---|---|
| E1 optical classifier | xView2 **CMU SEI baseline** damage classifier: ResNet-50 (ImageNet) + small CNN side branch + Dense head ending in `Dense(4, relu)`. Rebuilt layer-by-layer in TF 2.15 to load the original Keras 2.2.5 weights (`pipeline/weights/classification.hdf5`, **SHA-256 `a1f0dff601c8f3582b686ac7ce695f116d339e7913d1928d9ff62ab740e703cd`**). Source: the xView2 baseline repo (github.com/DIUx-xView/xView2_baseline). Trained on xBD. | **Uncalibrated**; label-only mode |
| E2 pixel change | SSIM loss, edge loss and change-vector magnitude inside the footprint + a 4 m debris ring, after per-building alignment and radiometric matching | provisional thresholds |
| E4 blue tarps | HSV tarp-blue share of the roof, minus the pre-event share | provisional threshold |
| E5 flood depth | FEMA PDA Guide (July 2025) Appendix H flood rows applied to first-floor depth, Monte Carlo over WSE / ground / foundation / outlet height | rule (verified transcription); **no WSE source** on current AOIs |
| Fusion v1 | weighted log-linear pooling over 5 FEMA classes, class prior divided out of crosswalk posteriors, abstention rules | provisional; temperature 1 |

## Intended use

Decision support for NC emergency-management analysts after a declared
disaster: triage where to send damage-assessment teams, and a draft
structure-level layer to verify. **Not** an official FEMA / NCEM damage
assessment, not an eligibility determination.

## Known performance (published, not ours)

On the xBD test set, the CMU baseline's published per-class damage F1 is about
no-damage 0.66, minor 0.14, **major ≈ 0.01**, destroyed 0.47 (overall ≈ 0.27).
Strong xView2 models reach ≈ 0.72–0.77 overall, and even they generalise poorly
to unseen areas when whole areas are held out (Gerard et al. 2024).

## Our measured performance

**None yet.** No public structure-level truth exists for Helene in NC (FEMA's
damage database stops at 2020 events). `reports/ACCURACY_REPORT.md` reports
`NO_TRUTH` until labels are collected per `docs/ops/LABELING_PROTOCOL.md`.

## Safety rule while uncalibrated

Every Major or Destroyed call goes to the human review queue
(`UNCALIBRATED_SEVERE_CALL_*`) until temperature scaling has been fit on TUNE
labels. A 12-chip smoke test in Swannanoa found roughly 7 of 12 CNN
"destroyed" calls visibly correct; the prior crosswalk would have claimed 0.80.

## Known limitations

* **The CNN only sees the post-event image** (128×128 chip). It cannot tell a
  pre-existing condition from damage.
* Its softmax is ~1.0 for almost every building (ReLU activations into
  softmax), so its "confidence" is meaningless until temperature-scaled.
* Trained on xBD satellite imagery (≈0.3–0.8 m). Ops mode feeds 0.3 m chips
  from satellite (Maxar) or resampled aerial (NC OneMap, ERI) imagery: a domain
  shift that is **not yet measured**.
* xBD events and landscapes differ from Appalachian hollows; dense canopy hides
  roofs (flagged as `ROOF_UNDER_CANOPY_*`).
* xBD → FEMA crosswalk is a hand-set prior (`config/crosswalks.yaml`,
  `status: prior`). An xBD "minor" call is genuinely ambiguous between FEMA
  Affected and Minor, so those calls land in review.
* Maxar pairs at Old Fort differ by 18.5° off-nadir and 19.4° sun elevation,
  and are January vs October: E2 is down-weighted there (×0.60).

## Licenses

xBD / xView2 data and derived weights: xView2 challenge terms (non-commercial).
Maxar Open Data imagery: CC BY-NC 4.0. See `LICENSES.md`.
