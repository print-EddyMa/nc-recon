# Phase C + D status — 2026-08-29

## TL;DR

The app is no longer hardcoded to Hurricane Helene. It reads an **event
registry** (`web/public/data/events.json`, written by
`run.py events registry`), and the same pipeline commands run any Maxar Open
Data event. Two events are ingested end-to-end and render from the in-app event
picker with **no code change between them**:

| Event | Area | Buildings | Severe (2+3) | Review-tier | Pre / Post |
|--|--|--|--|--|--|
| `HurricaneHelene-Oct24` | Old Fort, NC | 766 | 146 (19%) | 199 | 2022-01-07 / 2024-10-05 |
| `HurricaneHelene-Oct24` | Spruce Pine, NC | 139 | 2 (1%) | 28 | 2024-02-03 / 2024-10-05 |
| `WildFires-LosAngeles-Jan-2025` | Pacific Palisades, CA | 1038 | 92 (9%) | 273 | 2024-12-21 / 2025-01-13 |

Contract bumped to **schema 1.1**: every building carries `confidence_tier`
(`high` / `review`), a `sources` dict (`{heuristic, cnn, margin}`), and
`footprint_source`; the collection gains a `review` roll-up
(`total_review`, `total_high`, `model_agreement_pct`).

## Phase C — generalize + live monitor

### C1 Event registry — `src/terratriage/events.py`
- `list_events()` — the full `datasets/` list from the opengeos/maxar-open-data
  GitHub contents API (55 events as of today), cached to
  `data/cache/events_index.json`.
- `event_summary(event, ...)` — coverage bbox (reprojected from each TSV row's
  `proj:bbox`), capture date range, quadkey count, pre/post availability around
  an event date, hazard type guessed from the name.
- `build_registry` / `write_registry` — groups the per-area `meta.json` files
  (written by `run.py fetch`) into `events.json` for the web app.
- `match_hazards(registry, hazards_geojson, radius_km)` — used by the C4 bridge
  and D5 poller.
- `run.py events list | registry` subcommand.

### C2 Event/area model
- `run.py fetch` now writes `data/raw/<area>/meta.json`
  (`event, area, name, subtitle, center, zoom, event_date, pre/post dates`);
  `infer` / `validate` read it instead of the hardcoded Helene default.
- Web: `lib/events.ts` (`loadEvents`, `eventById`, `areaRef`, `hazardGlyph`),
  `components/EventPicker.tsx` (searchable), `App.tsx` state is now
  `{ eventId, areaId }`. Area IDs stay globally unique / directories flat, so
  no tile files moved.

### C3 Live Monitor — `screens/LiveMonitor.tsx` + `lib/hazards.ts`
- **USGS** M4.5+/7-day and **GDACS** `geteventlist/SEARCH` fetched live, each
  with a committed offline snapshot fallback
  (`web/public/data/live/*_snapshot.geojson`, seeded by
  `npm run refresh-live`). A "cached · offline" chip shows when stale.
- **NASA FIRMS** wired but gated on `VITE_FIRMS_KEY`; without it the layer is
  disabled with a prompt.
- Own MapLibre globe + deck.gl `ScatterplotLayer`; layer toggles, a ranked
  "active now" list with fly-to, and a permanent banner stating this is hazard
  *detection*, not damage assessment (24–72 h until imagery).

### C4 Bridge
- `LiveMonitor` runs a client-side haversine of each ingested event's bbox
  centre against the visible hazards; within 250 km it shows an "imagery
  available near a live hazard → open assessment" prompt.

## Phase D — fusion + review + deeper live + automation

### D1 OSM footprint constraint
- `footprints.filter_by_osm(pred, osm, min_iou)` (STRtree IoU) + `load_osm_polys`.
- Wired into the **segmentation** pipeline (`predict.py --osm-filter`): predicted
  footprints that don't overlap a mapped building are tagged `footprint_source:
  "model"` and `confidence_tier: "review"`. The primary footprints pipeline
  starts from OSM so every building passes by construction (`footprint_source:
  "osm"`).

### D2 Multi-source fusion — `src/terratriage/fusion.py`
- `classify.score_buildings(backend="fusion")` runs the heuristic pass **and**
  the keras CNN, then `fusion.fuse_scores`:
  - `high` when both agree, or agree within one level and CNN margin ≥ 0.20.
  - `review` when they disagree, or CNN margin < 0.10, or footprint < 12 m².
  - reported class is always the CNN's; the heuristic only informs the tier.
- `run.py infer --backend auto` ladder: `fusion` (CNN weights + conda env) →
  `keras` → `heuristic`.
- Helene model agreement ≈ 35%, LA ≈ 47% — the heuristic (rank-normalised change
  detection) and the post-only CNN genuinely diverge on cross-season pairs, so
  the review tier is doing real work rather than rubber-stamping.

### D3 Review queue — `screens/ReviewQueue.tsx` + `lib/review.ts`
- Lists `confidence_tier === "review"` buildings, largest first, with a pre/post
  crop pair rendered from the committed XYZ tiles (`tileForLonLat` +
  `object-position`) and a target reticle.
- Approve / Reject / Override→class; decisions persist per-viewer in
  `localStorage` (`terratriage:review:<areaId>`).
- Overrides flow to `DeckMap` (building redraws its corrected class), `MapView`
  ("N reviewed" chip), and `Stats` ("severe X → Y after review").
- Nav gains a **Review** tab with an open-count badge.

### D4 Deeper live layer
- GDACS (floods / cyclones / volcanoes) already in C3.
- **Sentinel-1** radar is a documented disabled toggle (`hazards.sentinel1()`) —
  needs Copernicus Data Space credentials; the extension point is wired.

### C4+ Point it at any live disaster — `scripts/run.py events catalog` + `server.py`

Beyond the ingested events, the app now knows the **whole Maxar Open Data
catalogue** (55 events) and can ingest one on demand:

- `run.py events catalog` → `web/public/data/maxar_catalog.json` (id, hazard,
  centre, bbox, capture date range, **suggested event date** = midpoint of the
  widest gap between captures, so an arbitrary event gets a sane pre/post split).
- `run.py events match` / `server.py GET /events/match?radius_km=` — live
  USGS + GDACS hazards paired with a catalogue event that covers them, scored
  `0.5·proximity + 0.3·hazard-type-agreement + 0.2·imagery-freshness`, deduped
  best-first, each flagged `ingested`.
- `server.py POST /assess {event, lat, lon, name}` → background thread runs
  `fetch → infer → make_tiles → events registry`; `GET /assess/{job}` streams
  `{status, step, log_tail}`. `download.choose_tile` now falls back to the
  nearest quadkey with a usable pre/post pair when the point isn't inside a tile.
- Web: the **main event picker** (top bar *and* landing page) now lists the
  ingested events ("Assessed · ready") **and** every other Maxar event
  ("Maxar Open Data catalogue"), one search box over all of it — searching
  "flood" / "earthquake" / a country works. Non-ingested rows carry an **Ingest**
  button (server on → runs the job and switches to the event) or **How** (no
  server → shows the `run.py` commands). Shared job state lives in
  `lib/useAssess.ts`; `components/AssessPanel.tsx` in the Live Monitor is the
  hazard-matched view of the same thing.
- The `/assess` worker copies the contract GeoJSON from `data/output/` to
  `web/public/data/` after inference so the new event is immediately loadable
  (previously it was registered but 404'd).
- Landing page gained a **"What it's built on"** credibility band: xBD training
  size (~850k buildings / ~45,000 km² / 19 disasters), the ResNet-50 model, the
  2-model + OSM fusion, and the 55-event live coverage, with the Gupta et al.
  2019 citation.
- Verified end-to-end: `/assess` on `Vanuatu-Earthquake-Dec17` at an arbitrary
  point ran fetch → fusion infer (3281 buildings) → tiles → registry and the new
  event appeared in the picker with no restart.

The hard limit stays **imagery coverage**: only the ~55 curated Maxar events
have post-event optical imagery (big disasters are usually added within 1–3
days). The panel is explicit about the imagery date so a 2015 baseline near a
2026 quake reads as "baseline imagery exists here," not "fresh post-event."

### D5 Automated trigger — `scripts/poller.py`
- Refresh event index → diff `data/cache/events_seen.json` → for each new event
  pull a USGS+GDACS snapshot → `events.match_hazards` → on a match (and only with
  `--run`, not the default `--dry-run`) shell out to `run.py fetch` + `infer`
  and append to `data/output/auto_runs.log`.
- Cron line documented in the README; no cron installed.

## What's still open / caveats

- **Committed data**: `web/public/data/events.json` and
  `web/public/data/live/*.geojson` are tracked. The Palisades GeoJSON + ~1086
  tile JPEGs (15 MB) match the existing `.gitignore` rules for
  `web/public/tiles/` and `web/public/data/*.geojson` and must be force-added the
  same way Old Fort / Spruce Pine were, or the LA event 404s on a fresh clone.
- The damage **classes** are still the xView2 baseline CNN's — off-distribution
  on cross-season optical pairs. Fusion improves *honesty* (which calls to
  trust), not raw accuracy. The 1st-place Siamese path is still the accuracy
  upgrade if its weights ever land (see `PHASE_A_STATUS.md`).
- LA AOI is one 2.9 km Maxar quadkey (`031311102213`, Palisades Highlands).
  Add `altadena` (Eaton fire) with the same `fetch`/`infer`/`make_tiles` trio
  for a second AOI.
- FIRMS + Sentinel-1 are unconfigured (no keys in this environment).
