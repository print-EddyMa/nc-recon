# Phase J status: operational upgrade

*Branch `phase-j-ops`. Demo frozen at tag `cac-v2-demo-stable`. Updated 2026-10-01.*

Scope change from the brief: the CAC material (student builds, AI-usage log,
judge Q&A, milestone dates) is dropped. The goal is a tool NC emergency
management analysts can use. Everything below runs behind ops mode; the v2
demo path (`run.py infer`, the Damage map / Review / Summary screens, the
scripted hook) is unchanged. Re-running `infer` on Old Fort reproduces v2's
features exactly (764 buildings, 305/349/45/65, 161 review).

## Final operational version (2026-09-26)

Built for use by NC emergency offices, no paid services:

* **One container** (`Dockerfile`, `docker-compose.yml` with Caddy HTTPS):
  web app + API + assessment worker, same origin. Verified from a clean
  image: health board all green incl. the damage model; a new assessment
  (Lake Lure) ran end to end inside the container in 53 s; export
  (FileGDB/GPKG/CSV/KML/Survey123), brief and public summary served through
  the proxy; building-level data 401 without the token.
* **Access fails closed** (`ops/auth.py`): token required, no localhost trust,
  refuses to start exposed without a token.
* **Damage model on ONNX Runtime**: no TensorFlow at deploy time.
* **UI**: Operations (home) / Conditions / Help. New assessments from the UI
  (point, imagery check, queued job with progress), provisional events,
  delete for operational areas, "as of" times, larger type, no animation.
  The xView2-vocabulary demo screens and the TomTom / aircraft layers are
  gone; the pitch demo is a separate offline build with pinned libraries.
* **Security**: maplibre-gl 6 / deck.gl 9.4 in the product, `npm audit` 0.
* **CI**: `.github/workflows/ci.yml` (tests, typecheck, lint, build, image).
* **Outage-tolerant**: secondary sources (NSI, SVI, Census, OSM, OpenFEMA)
  degrade to warnings; verified in-container with those hosts blackholed on a
  fresh volume. Audit log of responder actions.

## Reliability and analyst-workflow pass (2026-10-01)

Found by running the product end to end (a new assessment from the UI on a
second server beside the first) rather than by reading it:

* **A test run could destroy a live assessment.** Importing `server.py` ran
  the "prune half-registered areas" clean-up, and every test imports it. With
  an assessment in progress on the same data directory, `pytest` deleted that
  area's imagery mid-read (`RasterioIOError: Read failed`) and removed its
  registry entry. Recovery now runs at server start-up only, and the test
  suite keeps its registry, job list and audit log in a throwaway directory
  (it had also been appending `testclient` rows to the real `data/audit.log`).
* **Multi-part buildings shared one structure id.** A USA Structures
  MultiPolygon was assessed part by part under a single `BUILD_ID`, so two
  structures got the same `ncr_id` and would have shared one label. Parts now
  get their own ids (`<id>/1`, ...; the largest keeps the bare id, so
  single-part ids are unchanged) and a run fails loudly on any duplicate.
  Affected stored outputs until re-run: Spruce Pine (2 pairs), Marion (2).
* **Jobs were invisible and unrecoverable.** `/ops/jobs` existed but the UI
  never called it: closing the form lost the only reference to a running
  assessment, and a restart turned it into a 404. Jobs are now written to
  `data/jobs.json`, listed for every analyst under **In progress** (step, run
  time, warnings, error), can be **cancelled** (queued or running; the running
  step is terminated and partial output removed), and come back as
  "interrupted" after a restart. Job errors no longer carry terminal colour
  codes.
* **Label saves could wait on the health check.** One lock covered the
  12-source health refresh and the label CSV. They are separate now, and the
  board is served stale-while-refreshing with a **Check again** button.
* **Operations map**: the overview marks every assessed area (name, expected
  Major+Destroyed, extent box); a new assessment previews the square it will
  cover before it runs; inside an area the assessment's own **Before / After
  imagery** sits under the structures (tiles cut on demand from the stored
  GeoTIFFs, responder-only, dates shown as recorded). The legend no longer
  gets painted over by structures; medium-width and phone layouts scroll.
* Operational areas now carry their **county**, read from the structures'
  census blocks (the brief used to print "Marion ( Co.)"). The brief has a
  **Print or save as PDF** button.
* Imagery sidecars record absolute paths; a pair is now also found beside its
  sidecar, so a restored backup or a laptop-to-container move still opens.
* Requests to federal APIs send a User-Agent with a contact (`NCR_CONTACT`).
* **An area with no structures** (forest, open water) used to finish "done"
  and then crash the brief, the people estimate, the export and the public
  summary. It now says so on the map and in the brief; the export answers with
  a plain reason.
* **Public tract product leaked small counts.** Structure counts under 5 were
  withheld, but `expected_displaced` and `need_index` for the same tract were
  published. They are now withheld together (and when fewer than 5 assessed
  homes stand behind the people estimate).
* **Run again** re-assesses an operational area on its stored imagery (after
  a calibration or a fix such as the structure-id one). A failed or cancelled
  re-run leaves the previous result in place. Areas keep the name the analyst
  typed.
* **FEMA assistance by ZIP code** (`ops-reference`, panel on each area):
  owner and renter households FEMA approved in each ZIP the area touches,
  beside the homes the assessment expects at Major or Destroyed there. The
  one item taken from the "not built yet" list. It is context, not validation,
  and no agreement figure is computed.
* Labels can carry a short note; the review queue pages past its first 150.
* The Operations home now lists **every assessed area worst first** with
  totals (structures, expected Major or Destroyed, calls awaiting review).
* The public area list carries each area's extent for the overview map,
  snapped outward to about 100 m and withheld under 5 structures, so it never
  locates a home.

Not verified in this pass: the container image build (no Docker daemon on the
development machine; CI builds it). Still to do by hand: **Run again** on
Marion, and `run.py ops-assess --area spruce_pine`, to clear the duplicate
structure ids in their stored outputs.

## Groma Verify: the ground-truth engine (2026-10-21)

Concept: `docs/truth/README.md`. Groma makes calls; Verify turns them into
verified labels and keeps them as data. `ops/truth.py`:

* **Tasks by value of information:** model uncertainty (normalised entropy)
  times what rides on it (P(Major or Destroyed), occupants); deterministic;
  in-progress buildings finish first; nobody sees a building twice.
* **Blind:** a task carries the building and imagery dates only, never the
  model's level, probabilities or review flag. The Operations review queue
  stays the non-blind path.
* **Consensus:** three verifiers per building, one-coin Dawid-Skene with
  per-verifier reliability learned leave-one-out from settled answers
  (Beta(7,3) prior, uniform level prior so the model is never its own judge).
  Verified at two agreeing and pooled probability 0.9; "can't tell" is not a
  vote; disagreement escalates to an analyst, whose answer is the adjudication.
* **Release is explicit** (`run.py truth-release --area X`): writes the
  protocol label CSV (labeler `consensus` or `adjudicated`, role tagged),
  idempotent. TUNE labels feed `ops-calibrate`, TEST labels only `ops-eval`
  (tested). Store `data/truth/` (`NCR_TRUTH_DIR`); label dir now honours
  `NCR_LABELS_DIR`; both isolated in tests.
* **Dataset:** `truth-export` / `GET /ops/truth/export.zip`: JSONL with
  outline, verified level, agreement, split (development / held_out) and the
  imagery licence (`commercial_use` false for Maxar-based areas) plus a
  datasheet.
* **Metrics:** verified structures and verified per human minute
  (`GET /ops/truth/metrics`).
* **Web:** Verify screen (`#/verify`): name, area, before/after chips,
  keys 0 to 4 and x, analyst mode, area progress. Checked in the browser on Old
  Fort (TUNE) against a scratch store: two verifiers settled a building and the
  release wrote only the scratch label file.
* Deferred: a verifier role separate from the responder token, field photo
  tasks, credits and payment, public verified counts.
* Tests: 182 pass offline.

## Built for county outreach (2026-10-09)

* **FEMA IA layout export** (`<area>_fema_ia.csv` / `.geojson` in every GIS
  export): residential structures as points with the question names of FEMA's
  Individual Assistance damage survey as deployed in Survey123 (form V2.7,
  read from a public deployment because FEMA's v4.1.0 template page was not
  reachable), plus `ncr_` columns; verify-first rows on top. To confirm against
  NCEM's authoritative survey (ask in `docs/outreach/PLAN.md`).
* **Field-sheet categories fixed:** the Survey123 sheet offered "moderate",
  which is not a FEMA level; it now offers unaffected, affected, minor, major,
  destroyed, inaccessible.
* **Comparison with Helene search-team calls** (`run.py ops-sarcop --area X`,
  `analyze/sarcop_reference.py`, `GET /ops/areas/{area}/field-reference`,
  area panel "Compared with search teams' field calls"). Buncombe County's
  public SARCOP extract has FEMA-level categories, negatives included; only
  non-personal fields are requested. Swannanoa (TUNE): 370 waypoints, 262
  matched to an assessed structure (inside the footprint or within 10 m),
  same level 36%, within one level 56%, kappa 0.02. When Groma's most likely
  level was Major or Destroyed, the teams agreed 22 of 27 times; it found 22 of
  the 114 buildings the teams called Major or Destroyed. Homes only (178 of the
  262; the rest are shops, churches and the like): agreed 15 of 19, found 15
  of 64. The misses are mostly homes NC
  Recon called No damage, which fits interior flood damage that a roof does not
  show (E5 is unavailable in Swannanoa: its gauges stopped before the crest)
  and the months between the team visits and the spring 2025 imagery. Kept out
  of `data/labels` and the accuracy report; TEST areas are refused.
* **Outreach plan, email and one-pager** in `docs/outreach/`.
* Tests: 173 pass offline.

## First water-surface source for flood depth (2026-10-07)

E5 (flood depth against the FEMA waterline matrix) had been unavailable on every
structure because no high-water mark or crest with a datum sat on an assessed
reach. NCEM's published `Peak_Stage_Helene` layer (222 gauges with peak
elevation, datum, peak time and a stopped-reporting flag) is now read by
`collect/ncem_peak_stage.py` and fed to `analyze.flood` automatically by
`run_area` (`flood_depth_sources` in the run manifest and summary). Gauges that
stopped reporting before the crest are skipped with a warning; a crest is
NAVD88-verified only when FIMAN's gauge record agrees with the layer's datum.
On the current areas this makes E5 available near the Pigeon River at Canton
and the French Broad at Marshall once they are re-run; Old Fort's and
Swannanoa's gauges stopped before the crest, so E5 stays unavailable there and
the output says why. Health probe `ncem_peak_stage`; tests
`tests/test_flood_sources.py`. Not re-run on any area yet.

## Three more live feeds on the Conditions map (2026-10-07)

Found by the deployment-research sweep and checked live before wiring in
(`docs/ops/DATA_SOURCES.md` has the caveats):

* **NC FIMAN gauges** (`/feed/fiman`): 791 in-service NCEM, NCDOT, county and
  USGS gauges with FIMAN flood categories, forecast peaks, 24 h rain and road
  miles flooded; about 500 of them are gauges NWPS and the USGS API do not
  carry. Public ArcGIS service with no stated terms, so marked provisional.
* **Duke Energy outages by county** (`/feed/power`): customers out and share
  out, about every 20 minutes, Duke territory only.
* **FEMA ESF6 open shelters** (`/feed/shelters`): open shelters in NC with
  population and capacity, synced daily with the Red Cross list.

Each is a server-composed feed with a cache and stale fallback, a health-board
probe (`fiman`, `duke_outages`, `fema_shelters`), a dated fixture and offline
tests (`tests/test_nc_feeds.py`); the layers are on by default and say in
plain words when they are off (no server, nothing open, nobody out).

## Public-surface hardening (2026-10-07)

* **Per-client rate limits** (`ops/guard.py`): 30 writes, 600 reads, 120 feed
  requests a minute per client address, 429 with `Retry-After` beyond that.
  The client address comes from `X-Forwarded-For` only when
  `NCR_TRUST_PROXY=1` (compose sets it for the bundled Caddy); otherwise the
  header is ignored. Exempt: `/health`, preflight.
* **Content Security Policy and headers on every response**: scripts only
  from this origin plus the hash of the theme bootstrap in `index.html`
  (computed from the built file at start-up), direct browser connections only
  to the basemap, radar and federal feed hosts the app uses
  (`NCR_CSP_CONNECT` adds a self-hosted basemap), no framing, no referrer,
  `nosniff`, `Permissions-Policy`, `no-store` on API paths. Verified in a
  browser against the built app served by the API: Operations, an area with
  imagery and chips, Conditions with radar on; no CSP violations.
* **CI**: `pip-audit --strict` on runtime requirements (clean today),
  `npm audit --omit=dev --audit-level=high` (clean today; the remaining seven
  advisories are in the Tailwind 3 dev toolchain and need Tailwind 4),
  CycloneDX SBOMs for Python (18 components) and the shipped web bundle (64)
  as build artifacts.
* **Fonts bundled** (`@fontsource-variable` Geist, Geist Mono, Source Serif 4)
  instead of Google Fonts, so the UI renders identically with no internet;
  the browser now needs no host but this one, the basemap, the radar and the
  feed APIs. The frozen pitch demo (`demo.css`) still uses Google Fonts.
* Tests: 150 pass offline (7 new in `tests/test_guard.py`).

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
| Deployment | Dockerfile (Node build + Python 3.13 slim), compose + Caddy, fail-closed auth, backups | `docs/ops/DEPLOYMENT.md` |
| Web | Operations screen: FEMA 5-class map (YlOrRd, opacity = confidence), review queue by P(≥Major) × occupants, keyboard labeling, evidence card with pre/post chips, collection board, accuracy panel, people panel, disclaimer | `web/src/screens/Ops.tsx` |
| Docs | DATA_SOURCES, OPERATIONS, LABELING_PROTOCOL, MODEL_CARD, BIAS_AUDIT, LICENSES, ACCURACY_REPORT | `docs/ops/`, repo root, `reports/` |

## Current assessments (all unvalidated; see the accuracy report)

| Area | Role | Imagery | Structures (not assessed) | ≥ Major expected (80%*) | Needs review | Displaced from assessed homes | + homes not assessed |
|---|---|---|---|---|---|---|---|
| Old Fort | TUNE | Maxar 2022-01-07 → 2024-10-02 | 2,206 (513) | 244 (222–266) | 1,160 | ~318 | 307 homes (~760 people) |
| Spruce Pine | TUNE | Maxar 2024-02-03 → 2024-10-02 | 1,982 (390) | 233 (208–257) | 1,267 | ~369 | 278 homes (~525 people) |
| Swannanoa | TUNE (was TEST) | NC orthos 2023-02-18 → spring 2025 | 893 (70) | 119 (105–133) | 298 | ~144 | 38 homes (~81 people) |
| Chimney Rock | TEST | NC orthos 2023-02-14 → spring 2025 | 216 (23) | 49 (40–57) | 85 | ~26 | 12 homes (~18) |
| Canton | TEST | NC orthos → spring 2025 | 1,046 (242) | 42 (34–51) | 246 | ~83 | 134 homes (~330) |
| Burnsville | TEST | NC orthos → spring 2025 | 674 (65) | 48 (39–57) | 213 | ~90 | 33 homes (~93) |
| Marshall | TEST | NC orthos 2022-02-10 → **NOAA ERI 2024-10-07** | 291 (37) | 48 (38–57) | 131 | ~41 | 14 homes (~42) |

\* Ranges are conditional on the per-structure probabilities, which are not
yet calibrated; true uncertainty is wider. Displacement counts seasonal homes
as occupied (no Census key) and excludes homes that could not be assessed, so
it is neither a lower nor an upper bound. The ERI post-imagery path (`ops-fetch
--post eri`) was verified end to end on Marshall.

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

## Hold-out hygiene (2026-09-26)

Swannanoa was registered TEST, but its imagery was inspected and drove three
rule changes (E2 robust z-score, the haze thresholds, and the severe-call
review rule) before any labels existed. It is therefore **re-roled TUNE**.
Fresh TEST areas: **Canton** (Haywood) and **Burnsville** (Yancey), both in
the Helene 2025 ortho collection and away from existing AOIs, plus
**Marshall** (Madison; ERI post-only). Their chips have not been viewed and
must not be before labels exist. Chimney Rock stays TEST (nothing was tuned on it).

## Dates and access (2026-09-26)

* NC OneMap pre-event dates now come from the tile names (e.g. Swannanoa
  2023-02-18); the service's own `date` field is only a year placeholder.
  The Helene 2025 tiles carry no date, so post dates are the range the
  service description supports (2025-01-01..2025-05-31). Window checks use
  the whole range, reason codes say `POST_IMAGE_98-248D_AFTER_INCIDENT`, and
  FEMA `IMG_DATE` stays empty unless the date is exact (`IMG_DATE_RANGE`
  carries the range). No invented days.
* Building-level data (area GeoJSON, chips, brief) is responder-only. Public
  users get area summaries, tract products and impact.

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
E9 field-report ingest + `gnss_quality.py`, coverage-gap analysis, offline
PWA packs, QGIS project, Spanish UI, collection planner (satellite passes).

Blocked on inputs only the team can supply, not on code: a Census API key
(seasonal-home adjustment), Earthdata / GEE accounts (OPERA, HLS), analyst
labels (every accuracy number, calibration, the stronger-model decision), and
post-Helene lidar (E6).
