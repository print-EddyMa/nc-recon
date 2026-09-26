# Event-time playbook (ops mode)

Prereqs: `pipeline/.venv`, the `terratriage-tf` conda env (CNN), and
`web` built with `VITE_API_URL` set (the Operations tab appears when an API is
configured or `VITE_NCR_OPS_MODE=1`). Set `TERRATRIAGE_TOKEN` on any server
reachable beyond localhost: it gates addresses, labels and exports.

```bash
cd pipeline
.venv/bin/python scripts/run.py ops-health          # every source green/amber/red
.venv/bin/python server.py                           # API incl. /ops/*
```

## T−72 h to landfall
1. `ops-health`: fix red sources before you need them.
2. Register a **provisional** event in `config/events.yaml` (no disaster
   number yet: add it at declaration; windows are derived from OpenFEMA's
   `incidentBeginDate` and asserted: `pre.end < incident.begin <= post.start`).
3. Add AOIs with a TUNE/TEST role. Keep at least one TEST AOI per event.
4. Pre-cache pre-event imagery and structures: `ops-fetch` can't run without a
   post source yet, so warm the NSI / USA Structures caches by running
   `ops-assess` on a prior event's AOI near each town, or wait for T0.

## T0 to T+48 h
1. River gauges: the Live map (NWPS flood categories + USGS streamflow).
2. Road closures: DriveNC layer.
3. Label every brief "exposure / early evidence": no damage layer exists yet.

## T+2 to T+10 days (imagery arrives)
1. Maxar Open Data event: `run.py fetch` (existing path).
2. NOAA ERI flights: `run.py ops-fetch --area <id> --lon .. --lat .. --post eri`
   (post-only aerials; pairs with NC OneMap pre-event orthos).
3. `run.py ops-assess --area <id>`, then `ops-impact --area <id>`.
4. Work the review queue on the Operations screen. Every label is truth for
   calibration (TUNE) or measurement (TEST).
5. `ops-export --area <id>` (or the Export button) for GIS / Survey123 teams.

## T+2 to T+6 weeks
1. `run.py ops-eval` → `reports/ACCURACY_REPORT.md`.
2. `run.py ops-calibrate` (TUNE labels only) → temperature + conformal sets.
3. Re-run `ops-assess` so outputs carry calibrated probabilities.
4. Update `BIAS_AUDIT.md` with stratified results.

## Reading the output
* Headline totals: use **expected counts with the 80% range**, not argmax counts.
* `needs_review` + `review_reasons`: why a human must look.
* `evidence_unavailable`: what could not be checked (e.g. `E5: NO_WSE_SOURCE_ON_REACH`).
* "Not assessed" points: inventory structures with no footprint, so imagery was never read for them.
