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
1. Operations → Data sources: every source green (or know which are red).
2. Operations → New assessment → "Event not listed? Register one": name +
   expected incident start date. Add the FEMA disaster number(s) and the NOAA
   emergency-imagery folder once they exist (re-register with the number; the
   event id is derived from name + year). Windows are derived from the start
   date and enforced: no image from before the incident can be used as "after".
3. Conditions: watch river forecasts (NWPS), NWS alerts, NHC storms.

## T0 to T+48 h
1. Conditions: gauges, closures (DriveNC), alerts. Label anything shared as
   "exposure / early evidence": no damage layer exists yet.

## T+2 to T+10 days (imagery arrives)
1. Operations → New assessment for each town: pick the point, **Check
   imagery** (NC OneMap post-event orthos, NOAA emergency aerials, or Maxar
   satellite, in the event's order of preference), **Run assessment**. One
   runs at a time; the rest queue.
2. Open the area: brief the numbers from the expected counts with ranges, not
   from coloured-building counts. Read "Data caveats".
3. Work the review queue (most severe × most occupied first). Every label is
   ground truth.
4. **GIS export** for GIS / field teams (Survey123 sheet included);
   **Situation brief** for leadership; **Public summary** (tract level, no
   addresses) for public maps.

## T+2 to T+6 weeks
1. `run.py ops-eval` → accuracy report (TUNE and TEST separately).
2. `run.py ops-calibrate` (TUNE labels only) → calibrated probabilities and
   conformal sets; re-run assessments.
3. `run.py ops-backup` and keep the labels safe.
4. Update `BIAS_AUDIT.md` with stratified results.

## Reading the output
* Headline totals: **expected counts with the 80% range**.
* `needs_review` + reasons: why a human must look. Until calibration every
  Major/Destroyed call is reviewed.
* "Evidence unavailable": what could not be checked (e.g. no water-surface
  source on this reach).
* "Not assessed": inventory structures without a building outline.
