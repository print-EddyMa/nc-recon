# Phase F status — Finalize TerraTriage

Branch `phase-cd-and-redesign`, working tree. Started 2026-08-31.

## Scope
- F1  live animated visualization (NEXRAD radar loop + time-aware hazard layers)
- F2  NC disaster-history timeline (`#/history`), launch events, graceful era degradation
- F3  full audit (errors / perf / reliability / security / cache / UX)
- F4  standalone backend-showcase Artifact
- F5  final end-to-end validation

## Progress

### F1 — live animation
- [x] F1a  NEXRAD radar loop on NC dashboard — `lib/radar.ts` (IEM `nexrad-n0q-900913` + `-m05m..-m55m`, verified live), `components/map/RadarControl.tsx` (play/pause + scrub + frame clock), 12 raster layers pre-added under the basemap labels, cross-fade on frame change, 600ms cadence, pauses on hidden tab + reduced-motion. Toggle "Rain & storms" in the layer switchboard (off by default). Verified in browser both themes — real precip echoes render, labels stay legible, no console errors.
- [~] F1b  radar covers the "live moving weather" need. Per-feed time animation (rising-gauge pulse, FIRMS 3-day progression, storm-track march) deferred: storm/fire layers are empty on a calm day so there's nothing to animate now, and radar already delivers the requirement. Revisit if an active event lands before recording.
- [x] F1c  slow (2s) low-opacity radar loop behind the Home hero, `lib/radar.ts` reused, single-source setTiles, reduced-motion + hidden-tab aware.

### F2 — timeline
- [x] F2a  `ncFemaHistory` now returns `all` (65 deduped NC declarations), filter widened to `fyDeclared ge 1990`, `declarationType` added, committed `public/data/nc/fema_history_snapshot.json` fallback wired.
- [x] F2b  `screens/History.tsx` — hand-rolled zoomable timeline (px-per-day, 30yr/decade/year/month presets + wheel-zoom-to-cursor + native scroll-pan), year/month gridlines, lane-packed labels, landmark storms always labelled, type-coloured markers, legend + record summary. Route `#/history`, nav tab ("History"), ⌘K entry, `g t` shortcut — all wired in App/CommandMenu/ShortcutsDialog. Lazy-loaded (11KB chunk).
- [x] F2c  detail panel: 2016+ → "Assess an affected area" / open matching damage map; pre-2016 → `HistoricalRadar` (IEM WMS-T archived NEXRAD over NC, 4 day-frames auto-stepping, verified live: Irene 2011 renders real coastal echoes).
- polish note: some empty vertical space below the track on tall viewports; acceptable, could add a decade strip later.

### F3 — audit  (in progress)
- [x] console: full light+dark sweep of all 8 routes → **0 console/page errors** (was: NWPS CORS/429, catalog 503, ~60 tile 404s)
- [x] reliability: new `server.py` `GET /feed/{name}` cached pass-through (nwps 300s / nws 180s / nwis 300s, stale-on-error, real User-Agent) — whitelist only, no user input in URL. `nc.ts` `feedFetch()` prefers it, falls back to direct → committed snapshot. Empty NWPS/NWIS response now forces the snapshot path.
- [x] reliability: tile 404 storm fixed — `server.py /tiles` returns a 1×1 blank PNG for `?empty=1` (the slippy basemap) instead of 404; ReviewQueue crops keep the 404→zoom-out retry but via blank-tile detection (`naturalWidth<=1`) so the console stays clean.
- [x] reliability: `History` fetch has an `alive` cancel guard; wheel-zoom moved to a non-passive native listener (React's `onWheel` is passive → `preventDefault` would warn).
- [x] security: `npm audit` — was 10 high (all one chain: `image-size` DoS via `@deck.gl/geo-layers`→glTF/texture loaders, a path TerraTriage never exercises). Removed unused `deck.gl` meta + `@deck.gl/geo-layers` + `@deck.gl/react` (only `core`/`layers`/`mapbox` are imported). **Now 0 vulnerabilities.** Build + typecheck still clean.
- [x] cache: per-feed TTLs set on the proxy; `feeds live/cached` badge verified truthful (shows "cached" when the sweep tripped NOAA's rate limit).
- [x] perf: 32-nav thrash (monitor↔history↔map↔home, radar on) → JS heap flat/down (−14 MB after GC), no leak. Map + deck overlay + radar layers all dispose. Found & fixed a teardown-race pageerror (`getLayer` on a mid-swap style) — radar effects in NCDashboard + Home now guard `mapRef.current && map.getStyle()` and try/catch.
- [x] UX mobile: History layout was overlapping the detail panel on a 390px viewport (timeline column was `flex-1` fighting the aside) — now `shrink-0 lg:flex-1`, track `h-[360px] sm:h-[min(72vh,560px)]`, aside stacks. Marker sticks capped so labels never clip the `overflow-hidden` track. Landmark set trimmed to storms people actually name.
- [x] bundle: removed dead `deck.gl`/`geo-layers`/`react` deps (see security) — also shrinks install. Home first paint still ~1.39 MB (388 KB gz) index (maplibre for the hero) + lazy chunks.
- [ ] inaccuracies: cross-check Home tiles vs NC panels vs Summary; re-run one /assess end to end  (deferred to F5 walkthrough)

**F3 remaining for F5:** the end-to-end number cross-check folds into the F5 walkthrough.

### F4 — showcase artifact
- [x] `docs/how-it-works.html` — "Inside TerraTriage", single self-contained HTML, **published**:
      https://claude.ai/code/artifact/1788532d-f5c8-4a5d-831e-debcd46092b1
- Design: Archivo display + Public Sans body (US-government typeface — the app runs entirely on US-gov data) + IBM Plex Mono for data; warm-neutral ground, blue accent, the damage ramp as a recurring motif; full 3-state theme tokens; canvas contour backdrop (static under reduced-motion); sticky stage rail (01–05, a real sequence); scroll-reveal.
- Content: 5 stages (ingest / model / risk / render / output) each with a hand-authored inline-SVG mechanism diagram + real-number stat bands. Every figure is from the actual Old Fort run (766 buildings, 307/349/45/65, 37.9% agreement, 459 high / 307 review, 14.4% severe) or the real feed inventory (579 NWPS gauges, 1141 cams, 289 gages, 65 NC declarations, ~850k xBD buildings, 55-event catalogue). No placeholder numbers.
- Verified: light + dark + 390px mobile screenshots, no page errors; fixed a `.wrap`/`.hero-inner` padding-shorthand collision and inline `<span>` bars not taking width (`display:block`).

### F5 — final validation
- [x] scripted full journey (Home → Live map+radar → History → click Floyd 1999 → Assess → Old Fort damage map → Review → Summary): **no console/page errors**. Floyd opens the archived NWS radar for 1999-09-15 06:00Z — the real Floyd rain shield over eastern NC renders.
- [x] re-ran `/assess` end to end after every F change (Elk Park / Avery County, 36.13,-82.43 via Helene) → 1,046 buildings, fusion backend, pre 2023-09-08 / post 2024-10-02, 944 tiles, registry updated. Then removed it. Renamed `spruce_pine_test` display name → "Spruce Pine" (slug unchanged). Registry now: Old Fort + Spruce Pine.
- [x] number cross-check: Old Fort reads 766 / 110 severe / 14% / 307 review identically on the Home card, the damage-map legend, and `/areas/old_fort/summary`. NWPS 579, streamflow 289, FEMA 65-since-1990 all agree across Home, NC dashboard, History, and the showcase artifact.
- [x] all gates: `tsc -b` clean · `oxlint` 4 warnings (all pre-existing: MapView×2, ReviewQueue set-state-in-effect, scripts/_f.mjs) · `vite build` clean · light+dark headless sweep of all 8 routes = 0 errors.

## STATUS: COMPLETE (2026-08-31)

Everything in F1–F5 done. Summary of what Phase F added:
- **Live radar** (`lib/radar.ts`, `components/map/RadarControl.tsx`): animated NEXRAD loop on the NC dashboard (12 five-minute frames, play/scrub, off by default) + a quiet ambient loop behind the Home hero. IEM tiles, verified live.
- **History timeline** (`screens/History.tsx`, route `#/history`, nav + ⌘K + `g t`): zoomable 30yr↔month, 65 real OpenFEMA NC declarations, landmark storms labelled. 2016+ events → assess flow; older → archived IEM radar for that day (back to 1995).
- **Audit**: 0 console errors (added `server.py /feed/{name}` cached proxy for the CORS/rate-limit-prone NOAA feeds + blank-tile for edge basemap tiles); `npm audit` 10 high → **0** (dropped unused `deck.gl`/`geo-layers`/`react`); teardown-race pageerror fixed; mobile History layout fixed; nav-thrash shows no memory leak.
- **Showcase artifact**: `docs/how-it-works.html` → https://claude.ai/code/artifact/1788532d-f5c8-4a5d-831e-debcd46092b1

## Notes / decisions
- F1b per-hazard time-animation (rising-gauge pulse, FIRMS progression, storm march) deferred — radar covers the "live moving weather" need and the other layers are empty on a calm day. Revisit if a live event lands before recording.
- Static-deploy (`VITE_API_URL` unset) still 404s edge basemap tiles — unavoidable without the server; the `?empty=1` blank-tile path only works when the FastAPI service is up (dev + demo both have it).
