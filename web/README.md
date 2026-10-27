# Groma web

React 19 + TypeScript + Vite, Tailwind, MapLibre GL 6 with deck.gl 9.4
overlays. Three screens: Operations (`src/screens/Ops.tsx`), Conditions
(`NCDashboard.tsx`), Help.

```bash
npm install
echo "VITE_API_URL=http://127.0.0.1:8000" > .env.development.local   # the pipeline service
npm run dev            # http://localhost:5173
npm run typecheck && npm run lint && npm run build
```

Operations needs the service (`pipeline/server.py`); without `VITE_API_URL`
only Conditions and Help have data. In the container the app is built with
`VITE_SAME_ORIGIN=1` and talks to the server that serves it.

Fonts (Geist, Geist Mono, Source Serif 4) are bundled from `@fontsource-variable`
packages, so the product renders the same with no internet; only the basemap,
the radar tiles and the feed APIs are fetched from other hosts.

## How it fits together

* `src/lib/ops.ts`: every `/ops` call, the FEMA vocabulary and colours, the
  responder token (kept in this browser's localStorage, sent as a bearer
  header, never in a URL).
* `src/lib/nc.ts`: the Conditions feeds (USGS, NWPS, NWS, NHC, DriveNC), each
  with a committed snapshot under `public/data/nc/` as the offline fallback.
  `npm run refresh-nc` rewrites the snapshots.
* `src/lib/useMapLibre.ts`: one map per screen, basemap follows the theme.
* The deck.gl overlay is its own canvas above the map (not interleaved), so
  anything that must sit over the map needs a z-index.
* Structure-level imagery on the Operations map comes from the service as
  tiles (`/ops/areas/<id>/tiles/...`); the token rides in a request header
  via MapLibre's `transformRequest`.

Design rules (tokens, type, copy, what does not animate): [`../DESIGN.md`](../DESIGN.md).

## Intro and pitch demo

Two scripted sequences share one separate build with its own pinned map stack
in `demo-deps/` (maplibre-gl 5, deck.gl 9.3) and are not shipped in the
product image:

* `intro.html` + `src/intro/`: a self-running ~38 s intro that ends on a
  button into the app. Real radar, real imagery, the real Old Fort assessment.
  See [`src/intro/README.md`](src/intro/README.md).
* `demo.html` + `src/demo/`: the 17.8 s hook recorded for the pitch video.

`npm run demo:dev`, `demo:build`, `demo:validate`; `npm run intro:assets`
re-bakes the intro's data from the pipeline's outputs.
