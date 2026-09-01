# NCResQ — web

Control-room damage map for the NCResQ pipeline. React + TypeScript + Vite,
Tailwind, MapLibre GL + deck.gl.

```bash
npm install
npm run sync-data     # copy pipeline/data/output/*.geojson into public/data/
npm run dev
```

`npm run build` → `dist/`. `npm run shoot` → headless screenshots (needs Chrome
at the macOS default path).

## Data

- `public/data/<area>.geojson` — Phase A output (the contract). Regenerate with
  `pipeline/scripts/run.py infer` then `npm run sync-data`.
- `public/tiles/<area>/<pre|post>/z/x/y.jpg` — pre/post imagery tiles.
  Regenerate with `pipeline/scripts/make_tiles.py`. Git-ignored by default
  (committed for the demo).

## Notes

- **maplibre-gl is pinned to v5.** deck.gl 9.3's `@deck.gl/mapbox` `MapboxOverlay`
  does not render with maplibre-gl v6 (no tiles requested, overlay silent). v5 is
  the supported pairing.
- deck.gl overlay runs in **overlaid** (not interleaved) mode — its own canvas
  above the map — which is robust across maplibre versions.
- Map overlay panels are `z-20`; `.panel` uses a translucent bg + backdrop-blur
  so they stay legible over bright post-event imagery.
