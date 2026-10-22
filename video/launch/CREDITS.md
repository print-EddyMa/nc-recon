# Groma launch film: credits, licences and sources

72 seconds, 1920x1080, 30 fps. Built by `fetch_assets.py`, `lidar_plate.py`,
`prep.py`, `capture.py`, `compose.py`, `render.py` and `score.py` in this
folder (see README.md). Media and renders are git-ignored; these scripts and
this file are versioned.

Nothing in the picture is stock or generated. Every number on screen is read
from a real output file (listed under *Figures*).

## Picture

| Material | Source | Licence / terms | Where used |
|---|---|---|---|
| Civil Air Patrol oblique photos, Hurricane Helene, mission 24-C-5836 | FEMA `Image_Points_view` / `fema-cap-imagery` S3 (frames DSC_0547 of 2024-09-28; DSC_1453 and DSC_1482 of 2024-09-29; full list in `assets/cap/meta.json`) | No licence text on the layer (federal auxiliary imagery published by FEMA). Credit: Civil Air Patrol / FEMA. | Shots 1 to 3 |
| Pre-event orthoimagery, February 2023 | NC OneMap `Orthoimagery_2020_2023_4band_analysis` (NC CGIA, NC 911 Board) | No licence text; credit NC OneMap | Shots 4 and 5 |
| Post-Helene orthoimagery, spring 2025 | NC OneMap `Orthoimagery_Helene_2025` (NC Collaboratory, UNC Chapel Hill) | No licence text; credit NC OneMap / NC Collaboratory | Shots 4 and 5 |
| 2025 QL1 bare-earth lidar | NC OneMap `Elevation/DEM03`, `Buncombe_QL1_2025_03ft_CountywideRaster` | No licence text; credit NC OneMap | Shot 6 |
| Lidar baseline | USGS 3DEP (2017) | Public domain | Shot 6 |
| Groma app screens | The product itself, captured from a scratch server; Swannanoa (a TUNE area) only for building views | Project | Shots 7 and 8 |
| Map tiles inside the app screens | OpenStreetMap contributors, CARTO | ODbL (OSM data); CARTO basemap attribution required. Credit line on the end card. | Shots 7 and 8 |
| Groma mark | Project (`site/logo.svg`) | Project | Shot 12 |

## Sound

| Element | Source | Licence |
|---|---|---|
| Music and sound design | Original, synthesised by `score.py` (felt-piano additive synthesis, pads, impacts, bell, room tone, UI ticks). No samples. | Owned by the project. No third-party licence. |
| Voiceover | Kokoro-82M text-to-speech (hexgrad), voice `af_heart`, run locally with `kokoro-onnx` 0.6.1; model files `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the kokoro-onnx `model-files-v1.0` release | Model weights Apache-2.0 (commercial use permitted); kokoro-onnx MIT; phonemiser espeak-ng (GPL-3.0, used as a tool only, nothing redistributed) |

A recorded human voiceover can replace the TTS without changing the edit:
drop new `vo1.wav` to `vo8.wav` into `assets/vo/` and rerun `score.py`.

## Type

Marcellus, Public Sans, IBM Plex Mono: SIL Open Font License 1.1 (from `web/node_modules/@fontsource*`).

## Figures on screen and where they come from

| On screen | Source file |
|---|---|
| 893 structures, level counts 518 / 154 / 30 / 23 / 98 | `pipeline/data/output/ops/swannanoa.geojson` |
| 88 seconds | `swannanoa.geojson` properties `runtime_sec` = 88.3 |
| 15 of 19 | `swannanoa.sarcop_reference.json`, `summary_homes.major_or_destroyed` (Buncombe County public SARCOP extract) |
| 808 of 893 with a Civil Air Patrol photo | `collect/cap_photos.py` run over Swannanoa, 2026-10-22 |
| Lidar flags, scour and deposit | `swannanoa.ground_change.json` |
| FEMA survey columns and rows | `disseminate/exports.py` `FEMA_IA_FIELDS`; row values from `swannanoa.geojson` (addresses withheld) |
| "28 September 2024" | CAP frame folder `20240928T232313Z` |

## Not claimed

The film shows 15 of 19 as a comparison with search-team field records, never
as accuracy, and says so on screen.
