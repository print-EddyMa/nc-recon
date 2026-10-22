# Groma Verify: a ground-truth engine for disaster damage

*Concept and first build, 2026-10-21.*

## The idea

Scale AI did not win with a better model. It won by owning the step every model
needed and nobody wanted to do: turning raw data into trusted labels, fast, with
quality control. Disaster damage has the same gap, and it is wider. After
Helene, imagery arrived within days, but only a fraction of damaged buildings
were ever categorized by a person (OSBM), FEMA had 4% of its response workforce
free (GAO), and no public, structure-level, field-verified damage dataset exists
for the event. Models are getting cheap (Google Earth AI and similar); verified
truth is not.

**Groma Verify** turns Groma from a tool that makes calls into an engine
that makes *verified* calls, and keeps every verification as data:

1. **Pick what matters.** After an assessment, rank every building by how much a
   human answer is worth: how unsure the model is, times how much rides on it
   (chance of Major or Destroyed, people living there).
2. **Ask people, blind.** Each chosen building goes to three independent
   verifiers who see only the before and after images. No model guess, no
   probabilities, no "needs review" flag, so the model cannot anchor them.
3. **Agree, with reliability.** Answers are pooled with a weight per verifier,
   learned from how often each agrees with settled answers (a simple
   Dawid-Skene). A building is verified when at least two agree and the pooled
   confidence clears a threshold. "Can't tell" is not a vote; mostly "can't
   tell" means unverifiable. Disagreement goes to an analyst, whose answer
   settles it.
4. **Release, on purpose.** A person runs `run.py truth-release --area X`. Only
   then do verified answers enter the protocol label files, where the existing
   calibration (`ops-calibrate`, development areas only) and evaluation
   (`ops-eval`, held-out areas only) already read them. Labels in, calibration
   out, a shorter review queue next time.
5. **Keep the dataset.** Every release is exported as a versioned dataset with
   a datasheet: building outline, verified level, agreement, judgments, the
   area's role (development or held-out), and the licence of the imagery behind
   it.

## Why this can grow

* **It runs wherever the pipeline runs.** Any town Groma can assess becomes a
  verification job. Bring your own disaster.
* **It compounds.** Each event adds labels with negatives; each label makes the
  next event's calls better calibrated; better calls mean fewer buildings need
  people. The ratio of verified buildings to human minutes should rise every
  event. That is the number to steer by.
* **Three buyers, one asset.**
  * Counties and states: verified damage counts they can defend when federal
    money moves to formulas and block grants (FEMA Review Council, 2026).
  * Insurers, reinsurers and lenders: verified status per address after an
    event.
  * Model builders and researchers: the dataset (free for research; commercial
    use only where the imagery licence allows it).
* **The human network is the moat.** Verifiers can be county staff, trained
  volunteers, analysts in another state through mutual aid, and later paid,
  vetted local adults on the ground with photos. Field verification is the
  scarcest resource in a disaster.

## Rules it keeps

* Blind by design; the Operations review queue (which shows the model) stays a
  separate, non-blind path.
* Development (TUNE) labels feed calibration; held-out (TEST) labels feed
  evaluation only. A test checks a TEST label never reaches calibration.
* Nothing reaches `data/labels` without an explicit release.
* No personal data from verifiers beyond a chosen name; no addresses shown on
  the task.
* Imagery licences travel with every record (Maxar Open Data is CC BY-NC, so
  Old Fort and Spruce Pine labels are non-commercial; NC OneMap and NOAA areas
  are public).

## Built now

* `pipeline/src/terratriage/ops/truth.py`: value-of-information task selection,
  blind judgments, reliability-weighted consensus, escalation, release, dataset
  export, metrics. Store: `data/truth/` (`NCR_TRUTH_DIR`).
* API (responder token for now): `GET /ops/truth/next`, `POST /ops/truth/judgments`,
  `GET /ops/truth/areas/{area}`, `GET /ops/truth/metrics`, `GET /ops/truth/export.zip`.
* CLI: `truth-status`, `truth-release`, `truth-export`.
* Web: a Verify screen (`#/verify`), keyboard-first, blind.
* Civil Air Patrol photos beside each building (`collect/cap_photos.py`,
  `GET /ops/photos/{area}/{ncr_id}`): up to three obliques shot toward the
  building and one overhead frame, taken days after the event (Swannanoa:
  2024-09-28 and 29, months before the spring-2025 orthos). The building is
  not marked; a dashed line shows its direction from the camera's bearing and
  lens. The server fetches each 15 to 20 MB original once and serves a
  1,600 px copy. Reviewer context only: the photos never reach the damage call,
  and they reveal nothing about the model's answer.

## Next

* A verifier role separate from the responder token (identity, per-person
  limits, training and qualification tasks).
* Field tasks: a phone photo at the building, with time, location and
  consent checks.
* Credits per accepted judgment, then payment.
* Public verified counts per event; dataset releases.
