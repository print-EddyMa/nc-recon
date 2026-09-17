# Phase H - the hook sequence (`/demo.html`)

A separate, hardcoded ~17.8s sequence for the opening of a pitch video. It is
**not** the interactive app: its own Vite entry (`web/demo.html` →
`src/demo/main.tsx`), its own MapLibre instance, and it never touches the
app's live data-fetching code paths.

Every visual is **real data, pre-fetched and baked** into `web/public/demo/`:

| beat | what | source (baked) |
| --- | --- | --- |
| 1 Descent | dark map, NC outline glows, camera drops into the state | `nc-outline.json` |
| 2 Radar timelapse | Helene's rain shield crossing NC, 26-27 Sep 2024 | `radar/*.png` - archived IEM NEXRAD |
| 3 Snap | fast swoop into Old Fort / McDowell County | camera path |
| 4 Before / after | Maxar 2022 vs 2024 wipe of Old Fort | `oldfort_pre.jpg` / `oldfort_post.jpg` (z17, 3200x2000) |
| 5 Damage model | 764 buildings extrude, coloured by xView2 class | `old_fort.geojson` (the real assessment) |
| 6 Sensor network | camera pulls out, gauges cascade in radially | `sensors.json` - real NWPS + NWIS locations |
| 7 Flood flash | a western-NC river reach, rising-level indicator | picked from `sensors.json` |
| 8 History scrub | Fran → Floyd → … → Matthew → Florence → Helene fly past | `history.json` - real OpenFEMA declarations |
| 9 Title card | the NC Recon logo, flat, no glow | `ncrecon-logo-dark.svg` |

The CARTO dark-matter basemap is **self-hosted** under `public/demo/basemap/`
(style + every vector tile / glyph / sprite the camera path crosses) so
playback makes **zero external network calls**.

### Preload gate (`src/demo/preload.ts`)

The "SPACE" prompt is held back until the run genuinely cannot pop-in:

1. `await document.fonts.ready` - the stage `@import`s Geist from Google Fonts;
   wait so no lower-third reflows mid-sequence.
2. **HTTP-cache prewarm** - `fetch()` every file listed in
   `public/demo/basemap/tiles/manifest.json` (~880 tiles + glyph ranges,
   written by `demo_fetch.mjs`). `vite.config.ts` serves everything under
   `demo/basemap/` `immutable`, so MapLibre's later requests are pure
   in-memory hits - no revalidation round-trips stacking up behind the camera.
3. **Warm walk** - step the real camera path at 60 ms and dwell to idle at each
   sample, so every tile parses into MapLibre's tile cache.
4. **Verification lap** - re-walk the whole path and require a lap that loads
   *zero* new tiles (the honest "everything is resident" signal). Bounded; the
   debug HUD shows `verified in N lap(s)` or `verify budget hit`.

Even with every tile resident, a z6→z16 plunge in ~1 s outruns MapLibre's
per-frame vector-tile upload, so **beat 3 (snap) is 2400 ms**, widened from
1800 ms (time taken from the reveal, which holds under the full-frame wipe).

## Recording

- open `http://localhost:4173/demo.html` (after `npm run build && npm run preview`)
  or `http://localhost:5173/demo.html` (`npm run dev`)
- wait for the **SPACE** prompt - see the preload-gate steps above
- **Space / K** play-pause · **R** restart from frame 0 (instant, no reload) ·
  **F** browser fullscreen · **D** toggle the debug HUD
- the stage is chrome-free with `cursor: none`; `?autoplay=1` starts on load,
  `?debug=1` shows the timecode HUD, `?fixed=1` uses a fixed 60fps step -
  **use `?fixed=1` for frame-capture recording** so a slow capture frame slows
  the playhead instead of letting the camera outrun the tile loader

## Regenerating / checking

```bash
npm run demo:assets      # re-bake public/demo/ + basemap/tiles/manifest.json
                          # (network; ~1-2 min)
npm run demo:validate     # cold first play fetches ZERO map tiles, then 10x
                          #   back-to-back: completes, zero external calls,
                          #   zero console errors, frame-identical
npm run demo:shots        # screenshot each beat to a folder for review
```

`public/demo/basemap/` is git-ignored (regenerated, not committed). If you have
an older `basemap/` without `tiles/manifest.json`, re-run `demo:assets` - the
preload falls back to warm-only (no HTTP prewarm) when the manifest is absent.

Geography constants (`OLDFORT`, the camera keyframes, `OLDFORT_IMG_BOUNDS`) live
in `src/demo/beats.ts` and **must stay in lockstep** with the path/grid math in
`scripts/demo_fetch.mjs`.
