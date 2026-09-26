# Ground-truth labeling protocol (`ncr-label-v1`)

Labels are the only thing that turns NC Recon's probabilities into validated
numbers. Until enough exist, `run.py ops-eval` reports **no accuracy figure**.

## Where

Operations screen (`#/ops/<area>`) → pick a structure (the review queue is
already ordered by P(≥ Major) × occupants) → press a label. Keys: `0`–`4` =
No damage, Affected, Minor, Major, Destroyed; `x` = can't tell; `j`/`k` =
next/previous. Labels append to `pipeline/data/labels/<area>.csv` with the
labeler, protocol version, post-image date, AOI role (TUNE/TEST) and a UTC
timestamp. They need the responder token (or localhost).

## What to label: what the imagery shows, nothing else

Use FEMA's July 2025 PDA Guide definitions (Appendix H), restricted to what is
visible from above in the before/after chips:

| Label | Visible evidence |
|---|---|
| **No damage** | Roof and surroundings unchanged. |
| **Affected** | Cosmetic only: a few missing shingles, debris or mud in the yard, downed trees that don't touch the structure, damage to a detached shed/carport. |
| **Minor** | Non-structural roof damage (missing covering over part of the roof, a blue tarp), a tree on the roof without visible collapse, mud/water line evident around the structure. |
| **Major** | Part of the roof structure gone or collapsed, wall failure visible, the structure shifted on its foundation, a manufactured home displaced or tilted. |
| **Destroyed** | Only the foundation or a debris pile remains, the structure is gone (scoured), or it has been carried off its site. |
| **Can't tell** | Canopy, cloud, shadow, misalignment or image quality prevent a call. **Use it freely**: a wrong confident label is worse than none. |

Rules:

1. Flood damage inside a home is usually **invisible** from above. Don't guess
   Minor/Major from flood context alone; label what you see and add a note.
2. Late post imagery (spring 2025) shows cleared lots: a missing house on a
   clean slab is **Destroyed**, not "No damage".
3. Outbuildings are labeled like anything else, but don't let a destroyed shed
   make the house next to it Destroyed.
4. Never look at the model's call before deciding. The card shows it, so
   cover it, or label from the chips first.
5. **Double-label** at least 20% of each area: a second person labels the same
   structures independently. Cohen's kappa is reported. Disagreements are
   excluded until someone writes an `adjudicated` row.
6. TEST areas (`config/events.yaml`) are **never** used to change thresholds,
   crosswalks or calibration. Their labels only measure.

## Targets for a first honest baseline

* ≥ 300 labeled structures per TUNE area, ≥ 200 per TEST area.
* Oversample the rare classes: label the whole review queue top-down
  (it is severity-ordered), then a random sample of the rest.
* Then run `run.py ops-eval` and, if ≥ 20 TUNE labels, `run.py ops-calibrate`.
