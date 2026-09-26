# Phase J status: operational upgrade

*Branch `phase-j-ops`. Demo frozen at tag `cac-v2-demo-stable`. Updated 2026-09-26.*

Scope change from the brief: the CAC material (student builds, AI-usage log,
judge Q&A, milestone dates) is dropped. The goal is a tool NC emergency
management analysts can use. Everything below runs behind ops mode; the v2
demo path (`run.py infer`, the Damage map / Review / Summary screens, the
scripted hook) is unchanged. Re-running `infer` on Old Fort reproduces v2's
features exactly (764 buildings, 305/349/45/65, 161 review).

## What exists now

| Area | Built | Where |
|---|---|---|
| Event registry | Incident periods from OpenFEMA (DR-4827: begins 2024-09-25), TUNE/TEST AOIs, hard window assertions; the v2 mis-dating bug is a failing test | `ops/plan/events.py`, `config/events.yaml` |
| Geodesy | CRS registry (config-overridable for NSRS 2022), `always_xy`, Web Mercator measurement refused, datum offset (Old Fort 1.163 m H / 1.326 m V at 2026.7), ftUS vs ft, USNG 1 m / 10 m, typed heights | `ops/geodesy.py`, `ops/heights.py` |
| Connectors + health | USGS Water Data API, NWPS, NWS, OpenFEMA, NSI, USA Structures, NC OneMap orthos, NOAA ERI, SVI, legacy USGS (down), GEE / Earthdata (unconfigured) | `ops/collect/`, `run.py ops-health` |
| USGS migration | Server, web and snapshot script off legacy NWIS (which was 503) | `server.py`, `web/src/lib/nc.ts` |
| Imagery for all WNC | NC OneMap 2020–23 analysis orthos (pre) + NC Collaboratory Helene 2025 orthos or NOAA ERI (post), co-gridded at 0.3 m | `run.py ops-fetch` |
| Structures | USA Structures primary + OSM gap-fill + NSI attributes; stable `ncr_id`; inventory points without footprints emitted as "not assessed" | `ops/process/structures.py` |
| Alignment | AOI consensus + per-building footprint-to-image offsets, per image; per-building post→pre shift; radiometric matching | `ops/process/align.py`, `coreg.py` |
| Evidence | E1 CNN (label-only until calibrated), E2 change (robust z within AOI), E4 tarps, E5 flood depth (FEMA PDA July 2025 matrix) | `ops/analyze/` |
| Context / masks | cloud, **haze / cloud shadow**, canopy, no-data, misregistration, view-geometry and season penalties | `ops/analyze/evidence.py`, `config/context_rules.yaml` |
| Fusion v1 | log-linear pooling over 5 FEMA classes, abstention, reason codes, expected counts with 80% interval | `ops/analyze/fusion.py` |
| Evaluation | metrics (sklearn-checked), spatial-cluster bootstrap CIs, ECE, TUNE/TEST separation, temperature scaling, split-conformal APS | `run.py ops-eval`, `ops-calibrate` |
| Impact | expected displaced (Monte Carlo), SVI tract need index, public tract product with small-count suppression | `run.py ops-impact`, `ops-aggregate` |
| Dissemination | GeoJSON (RFC 7946), CSV with USNG, KML, GeoPackage, File Geodatabase, Survey123 sheet, provenance sidecar, license README; addresses only in a responder sidecar | `run.py ops-export`, `/ops/*` |
| Brief | One-page printable situation brief (BLUF, map, ranges, tracts, gaps, sources) + text twin | `run.py ops-brief`, `/ops/areas/<id>/brief.html` |
| Web | Operations screen: FEMA 5-class map (YlOrRd, opacity = confidence), review queue by P(≥Major) × occupants, keyboard labeling, evidence card with pre/post chips, collection board, accuracy panel, people panel, disclaimer | `web/src/screens/Ops.tsx` |
| Docs | DATA_SOURCES, OPERATIONS, LABELING_PROTOCOL, MODEL_CARD, BIAS_AUDIT, LICENSES, ACCURACY_REPORT | `docs/ops/`, repo root, `reports/` |

## Current assessments (all unvalidated; see the accuracy report)

| Area | Role | Imagery | Structures (not assessed) | ≥ Major expected (80%) | Needs review | Displaced (upper bound) |
|---|---|---|---|---|---|---|
| Old Fort | TUNE | Maxar 2022-01 → 2024-10 | 2,206 (513) | 244 (222–266) | 1,160 | ~318 (291–346) |
| Spruce Pine | TUNE | Maxar 2024-02 → 2024-10 | 1,982 (390) | 233 (208–257) | 1,267 | ~369 (337–405) |
| Swannanoa | TEST | NC orthos 2020–23 → 2025 | 893 (70) | 119 (105–133) | 298 | ~144 (131–157) |
| Chimney Rock | TEST | NC orthos 2020–23 → 2025 | 216 (23) | 49 (40–57) | 85 | ~26 (22–30) |

The Maxar areas send 69% and 80% of assessed structures to review, the NC-ortho areas
36% and 44%: the Maxar pairs have haze, 18–19° geometry differences, a season
change and a 7 px co-registration residual (NC orthos: 0.9 px). Old Fort's
argmax "destroyed" count dropped from 129 to 52 once haze masking and
footprint alignment went in. v2 reported 764 structures at Old Fort from OSM
alone.

Demo check: `npm run demo:validate` passes 10/10 runs, 0 external calls, 0
console errors. Its frame-identical check fails, and fails identically when
the `cac-v2-demo-stable` tag itself is built and validated, so this is
pre-existing, not a Phase J regression.

## What we learned (where the brief was wrong or out of date)

1. **Legacy USGS WaterServices was already down** (503), not just "at risk".
2. **Census API now requires a key**; keyless calls redirect to a missing-key page.
3. **FEMA's damage database has no Helene rows**: it ends with 2020 events.
   There is no public structure-level truth for DR-4827; truth must be labeled.
4. **DR-4827 marks individual assistance as `ihProgramDeclared`**, not
   `iaProgramDeclared` (which is false for every row).
5. The **FEMA PDA Guide was reissued July 2025**; it *does* define a
   depth-based Destroyed (waterline at/above the ceiling), unlike the brief's
   2021 + 2024-errata summary.
6. **OSM has about half the building stock** at Old Fort (760 vs 1,395 USA
   Structures vs ~1,900 NSI points). v2's 764-building count was an undercount.
7. **Maxar Open Data covers only Old Fort and Spruce Pine in NC** (the third
   cluster is Erwin, TN). None of the brief's suggested TEST towns has Maxar
   post imagery. NC OneMap + NOAA ERI cover the rest of WNC.
8. The CNN's last layer is `Dense(4, relu)`, so its softmax is ~1.0 for almost
   every building; v2's "high confidence" carried no information.
9. **Footprints miss their roofs by metres** on Maxar (Old Fort pre: ~4 m W,
   3 m N as a consensus; some buildings far more), which fed the CNN lawn and
   produced false "Destroyed". Now aligned per image.
10. **Thin cloud / haze read as "Destroyed"**: 4 of 12 sampled Old Fort
    Destroyed calls were haze. Now detected relative to the pre image.
11. **Absolute change thresholds don't transfer between sensor pairs**
    (median change score 0.46 on the NC ortho pair). E2 now uses a robust
    z-score within the AOI.
12. No Helene water-surface source (HWM, crest with datum) lies on the same
    reach as any current AOI, so **E5 is unavailable everywhere so far**,
    and the output says so per structure.
13. The xBD→FEMA crosswalk makes a CNN "minor" call ambiguous between Affected
    and Minor; those land in review until calibration.
14. **Smoke test, not a metric**: of 12 random Swannanoa CNN-"destroyed" calls
    (NC ortho pair), about 7 visibly show the structure gone and 3-4 show it
    standing. The crosswalk's 0.80 was overconfident, so until calibration
    **every Major/Destroyed call is routed to review**
    (`review_severe_until_calibrated`).

## Open decisions (need the team)

1. **Census API key** (free) → seasonal-home adjustment of displacement.
   Without it the people estimate is an upper bound.
2. **Label budget**: the protocol targets ≥300 TUNE and ≥200 TEST labels per
   area, 20% double-labeled. Nothing is validated until this happens.
3. **Stronger model** (Siamese U-Net / xView2 strong baseline, both pre and
   post): only after the labeled baseline exists, and only if it beats it on TEST.
4. **Earthdata / GEE accounts** to enable OPERA DSWx / DIST and HLS baselines.
5. **Deployment**: a shared server needs `TERRATRIAGE_TOKEN` and HTTPS before
   any responder data leaves localhost.

## Not built yet (in priority order)

E8 road isolation + Black Marble outage (the need index's β/γ terms), E6
lidar DEM of Difference (post-Helene 2025 lidar), E3 shadow/height, E7 wind,
E9 field-report ingest + `gnss_quality.py`, OpenFEMA housing-assistance
ZIP comparison, coverage-gap analysis, offline PWA packs, situation brief
PDF export button (print-to-PDF works today), QGIS project, Spanish UI, collection planner (satellite passes).
