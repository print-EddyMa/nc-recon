# Phase E status — 2026-08-30

## TL;DR

North Carolina now has a dedicated **NC monitor** tab — a deeply-instrumented
*risk* dashboard that sits alongside (not instead of) the Phase C/D global Live
Monitor. It answers "what could happen / is happening" (forecasts, warnings,
sensors, storm tracks, road state), the mirror image of the damage pipeline's
"what already happened".

New in the web app:

| File | Role |
|--|--|
| `web/src/lib/nc.ts` | NC data backbone — one module, six feeds |
| `web/src/screens/NCDashboard.tsx` | the unified NC risk view (E6) |
| `web/scripts/refresh_nc_snapshots.mjs` | `npm run refresh-nc` — offline snapshots |
| `web/public/data/nc/*.geojson` | committed NWPS / NWS / NHC / DriveNC snapshots |

Wired into `App.tsx` as screen `"nc"` (deep-link `#/nc`, nav tab **NC monitor**,
**⌘K** entry, **g n** shortcut). The global event picker, Live Monitor, damage
map, review queue and summary are untouched (E7).

## Access model (why some feeds are live and some are snapshots)

Same pattern as `hazards.ts`: fetch live where the API is open + CORS-enabled,
fall back to a committed snapshot otherwise.

| Feed | Phase | In-browser | Notes |
|--|--|--|--|
| NOAA NWPS gauges + flood-category forecast | E2 | **live**, snapshot fallback | `access-control-allow-origin: *` |
| NWS `/alerts/active?area=NC` | E5 | **live**, snapshot fallback | GeoJSON, CORS `*` |
| NC CLOUDS API (ECONet / RAWS) | E1 | **live once a free hash is pasted** | CORS `*`, `output=geojson`; key-gated like FIRMS |
| NHC `CurrentStorms.json` | E3 | **snapshot only** | nhc.noaa.gov sends no CORS header |
| NCDOT DriveNC cameras / closures | E4 | **snapshot only** | drivenc.gov sends no CORS header |

`refresh_nc_snapshots.mjs` (Node, no CORS restriction) fetches all five and
commits them so the dashboard is fully populated offline. As of this run:
NWPS **579** NC gauges, DriveNC **1141** cameras / **125** closures + incidents,
NWS **0** active (nothing warned in NC today), NHC **0** (no active Atlantic
storm).

## E1 — CLOUDS API backbone

`ncClimate()` in `lib/nc.ts`. One module, two network pulls (`type=ECONET`,
`type=RAWS`) against `api.climate.ncsu.edu/data` with `output=geojson`,
`start=-90 minutes`, most-recent obs. Parses defensively (variable names vary by
station) and surfaces temperature / wind / rainfall, plus RAWS fuel-moisture; a
station with low fuel moisture + wind is flagged as fire-weather risk and shown
on the ramp. No hash → the layer is disabled with an inline "add a key" form
(Layers → key), identical to the FIRMS flow. `settings.cloudsKey` in
`lib/settings.ts`, localStorage only.

## E2 — NWPS flood forecasts

`ncFloodForecasts()`. One bbox call to `api.water.noaa.gov/nwps/v1/gauges` over
NC. Each gauge carries `status.observed` **and** `status.forecast`, each with a
`floodCategory` (`no_flooding` / `action` / `minor` / `moderate` / `major`).
Severity is the worse of the two; a gauge forecast to rise above its observed
category is called out ("Forecast to rise into Moderate flood by 18:00 UTC").
The dashboard's "Flood forecast" panel ranks every gauge at action+ with a
fly-to. Border gauges from the rectangular bbox are dropped via
`state.abbreviation === "NC"` / `lid` ending `N7`.

## E3 — Hurricane tracking

`ncStormTracks()` reads the committed `nhc_snapshot.geojson`. The refresh script
pulls `CurrentStorms.json`, keeps Atlantic-basin storms (`id` starts `al`), and
writes a current-position marker per storm with classification, intensity,
pressure and motion. The layer and its right-panel section only render when a
storm is active (`disabled` otherwise, with a "appears during a storm" reason) —
per the brief, no always-on empty panel. The forecast **cone polygon + track
line** are published by NHC only as zipped shapefiles; parsing those needs a
shapefile dependency and is left as a documented extension point in the refresh
script.

## E4 — NCDOT cameras + road closures

`ncCameras()` / `ncClosures()` read committed snapshots. The refresh script uses
DriveNC's public `/map/mapIcons/{Cameras,Closures,Incidents}` endpoints (point
data: id + lat/lon). Cameras and closures are **not** on the hazard-severity
ramp — they get their own fixed marks (faint hollow dot / amber ring) so the
ramp keeps meaning "flood risk". The dashboard computes the worst current risk
point (top flood gauge, else a fire-weather RAWS station) and lists the nearest
closures (≤120 km) and cameras (≤80 km) as "Ground truth near the risk" — the
"I-40 Pigeon River Gorge closure would have shown here in real time" narrative.
The keyed DriveNC v2 API (per-event detail, camera stills) is an extension
point.

## E5 — NWS alerts, NC-filtered

`ncAlerts()`. `api.weather.gov/alerts/active?area=NC`, GeoJSON, rendered as
translucent polygons + a de-duplicated ranked list. Flood / red-flag / fire /
tropical / tornado events are bumped to at least "elevated" so they read against
the sensor noise.

## E6 — Unified NC risk dashboard

`screens/NCDashboard.tsx`. Own MapLibre map centred on NC + a deck.gl overlay
(GeoJsonLayer for alert / storm polygons, ScatterplotLayer for the point feeds).
Left: layer toggles with per-feed counts + source + an "offline" chip that only
trips when a *live-capable* feed (gauge / alert / climate) fell back to a
snapshot; the CLOUDS key form; a severity legend. Right: **Current conditions**
(CLOUDS headline + fire-weather flag), **Flood forecast** (ranked), **Official
alerts** (ranked), **Active storm** (only when relevant), **Ground truth near
the risk** (closures + cameras). A permanent header banner states this is the
risk half — forecasts + conditions — not a damage claim, and links across to the
global monitor ("built with NC depth, architected to generalize").

Toggle state persists to `localStorage["terratriage:nc-layers"]`. Live feeds
refresh every 5 min; CLOUDS re-fetches on key change. `prefers-reduced-motion`
is respected (fly-to duration 0).

## E7 — Global mode intact

No change to the event registry, picker, Live Monitor, damage map, review queue
or summary. NC is an added tab, available with or without a disaster selected
(same as the global Live Monitor). Deep-link grammar extended with `#/nc` only.

## E8 — Validation

- **Build**: `tsc -b` + `vite build` clean; `oxlint` shows only the pre-existing
  set-state-in-effect warnings elsewhere in the tree.
- **Headless render** (`#/nc`, no pipeline server): map + all six layers draw,
  no new console errors (the two `:8000/catalog` + GDACS failures are the
  unrelated Phase C/D feeds).
- **E1–E2 sanity check** (the called-for checkpoint): NWPS returned 579 NC
  gauges; on 2026-08-30 exactly one is above normal — **Cape Fear River at
  Wilmington** at *action stage, 4.9 ft* — which the dashboard ranks first and
  which the "ground truth near the risk" panel correctly anchors the nearest
  Wilmington-area cameras + the US-74/76 closures to. Every other NC forecast
  gauge is below flood stage, matching a quiet-weather day. NWS returned zero
  active NC alerts (correct — nothing warned). Numbers are sane for a
  hand-checkable day.
- CLOUDS (E1) needs a real hash to exercise end-to-end; the parser degrades to a
  clear "couldn't parse / check the key" disabled state on any unexpected shape.

## Hardening + shared components (second pass)

Bug / hole / inefficiency review of the Phase E code, plus a component-extraction
pass in the shadcn / 21st.dev idiom the app already uses (the 21st MCP itself
is not configured in this repo, so these are hand-built to the same contract).

**Fixed**

- **Inefficiency** — the NC dashboard was re-fetching the *committed* NHC /
  DriveNC snapshots on the same 5-minute timer as the live feeds. Split: the
  three snapshot-backed feeds fetch once on mount; only NWPS + NWS poll.
- **Data loss** — `ncClimate()` used `Promise.all`, so a RAWS-network failure
  threw away good ECONet data. Now `Promise.allSettled`: partial data survives,
  and the layer only goes to the error state if *both* networks fail.
- **Hole (mobile)** — the right-hand risk panel was `hidden md:flex` with no
  fallback, so a phone showed the map and nothing else. Added a bottom state
  strip (flood + alert headline) that expands to the full panel set.
- **Correctness** — alert de-dup key handled an `undefined` detail; `focusPoint`
  now also falls back to the centroid of the most severe NWS alert when no gauge
  or fire-weather station is elevated, so "ground truth near the risk" still
  anchors during a wind/tornado event.
- **Visual** — NHC storm markers were near-invisible (fill α 26 → 55, radius
  5 → 7).

**New reusable components** (`src/components/`)

| Component | Used by |
|--|--|
| `ui/StatTile` | NC "current conditions" (the 21st "stat card for a damage dashboard" shape) |
| `ui/KeyForm` | NC CLOUDS key **and** Live Monitor FIRMS key — one component, was duplicated |
| `map/LayerToggles` | NC dashboard layer switchboard (Live Monitor share-ready) |
| `map/RankedList` | NC flood / alert / ground-truth lists (Live Monitor "active now" share-ready) |
| `map/FeatureCallout` | NC selected-feature panel (Live Monitor share-ready) |

**Theme / colour** — added the `accent-ink` token (`#05171a`, the near-black
teal used for text on an accent fill) to `tailwind.config.js` and replaced all
11 hard-coded `text-[#05171a]` / `bg-[#05171a]` occurrences across the app plus
the two in `index.css`. Fonts (Archivo / Geist / Geist Mono) and the
canvas/surface/ink + `dmg0–3` ramp were already consistent and unchanged; NC
severity reuses the ramp via `NC_SEV_COLOR` in `lib/nc.ts`.

**Re-verified** — `tsc -b` + `vite build` clean; `oxlint src/` shows only the
three pre-existing `set-state-in-effect` warnings (MapView / EventPicker /
ReviewQueue), none in Phase E or the new components. Headless smoke of all six
screens + the LA event + NC on a 390px viewport: every screen renders content
with zero console or page errors.

## Re-generating

```bash
cd web
npm run refresh-nc     # NWPS + NWS + NHC + DriveNC -> public/data/nc/*.geojson
npm run build
```

Put `refresh-nc` on a cron (alongside `refresh-live`) to keep the offline storm
/ camera / closure sets current between deploys.
