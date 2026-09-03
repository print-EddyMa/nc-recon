# Phase H — the hook sequence (`/demo.html`)

A separate, hardcoded ~17.8s sequence for the opening of a pitch video. It is
**not** the interactive app: its own Vite entry (`web/demo.html` →
`src/demo/main.tsx`), its own MapLibre instance, and it never touches the
app's live data-fetching code paths.

Every visual is **real data, pre-fetched and baked** into `web/public/demo/`:

| beat | what | source (baked) |
| --- | --- | --- |
| 1 Descent | dark map, NC outline glows, camera drops into the state | `nc-outline.json` |
| 2 Radar timelapse | Helene's rain shield crossing NC, 26–27 Sep 2024 | `radar/*.png` — archived IEM NEXRAD |
| 3 Snap | fast swoop into Old Fort / McDowell County | camera path |
| 4 Before / after | Maxar 2022 vs 2024 wipe of Old Fort | `oldfort_pre.png` / `oldfort_post.png` |
| 5 Damage model | 764 buildings extrude, coloured by xView2 class | `old_fort.geojson` (the real assessment) |
| 6 Sensor network | camera pulls out, gauges cascade in radially | `sensors.json` — real NWPS + NWIS locations |
| 7 Flood flash | a western-NC river reach, rising-level indicator | picked from `sensors.json` |
| 8 History scrub | Fran → Floyd → … → Matthew → Florence → Helene fly past | `history.json` — real OpenFEMA declarations |
| 9 Title card | the NC Recon logo, flat, no glow | `ncrecon-logo-dark.svg` |

The CARTO dark-matter basemap is **self-hosted** under `public/demo/basemap/`
(style + every vector tile / glyph / sprite the camera path crosses) so
playback makes **zero external network calls**.

## Recording

- open `http://localhost:4173/demo.html` (after `npm run build && npm run preview`)
  or `http://localhost:5173/demo.html` (`npm run dev`)
- a full preload gates playback — the "SPACE" prompt appears only when every
  asset is in memory and the basemap is warmed
- **Space / K** play-pause · **R** restart from frame 0 (instant, no reload) ·
  **F** browser fullscreen · **D** toggle the debug HUD
- the stage is chrome-free with `cursor: none`; `?autoplay=1` starts on load,
  `?debug=1` shows the timecode HUD, `?fixed=1` uses a fixed 60fps step

## Regenerating / checking

```bash
npm run demo:assets      # re-bake public/demo/ (network; ~1–2 min)
npm run demo:validate     # 10x back-to-back: completes, zero external calls,
                          #   zero console errors, frame-identical
npm run demo:shots        # screenshot each beat to a folder for review
```

Geography constants (`OLDFORT`, the camera keyframes, `OLDFORT_IMG_BOUNDS`) live
in `src/demo/beats.ts` and **must stay in lockstep** with the path/grid math in
`scripts/demo_fetch.mjs`.
