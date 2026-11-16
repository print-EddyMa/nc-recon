# NC Recon launch film: credits, licences and sources

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
| NC Recon app screens | The product itself, captured from a scratch server; Swannanoa (a TUNE area) only for building views | Project | Shots 7 and 8 |
| Map tiles inside the app screens | OpenStreetMap contributors, CARTO | ODbL (OSM data); CARTO basemap attribution required. Credit line on the end card. | Shots 7 and 8 |
| NC Recon mark | Project (`site/logo.svg`) | Project | Shot 12 |

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

---

# Version 2 (75 s, 112 bpm)

Built by `capture_v2.py`, `compose_v2.py`, `render.py --html composition_v2.html --out picture_v2.mp4`
and `score_v2.py`. Renders: `build/ncrecon_launch_v2.mp4` (master), `_web.mp4`, `_preview.mp4`.

## Additional picture

| Material | Source | Licence / terms | Where used |
|---|---|---|---|
| Swannanoa valley in 3D | Rebuilt in three.js 0.160 (MIT, loaded from jsDelivr at render time) from the site's baked assets in `site/assets/terrain/`: USGS 3DEP elevation (public domain), NC OneMap pre and post imagery, smoothed damage density, published roads, USNG sectors and landing-zone candidates (`layers.json`), OpenStreetMap rivers (ODbL). Contours traced from the DEM at 20 m. | As listed | 0:04 to 0:16, 0:26 to 0:30 |
| App 3D orbit, Respond, stepper, overview, Verify | The product, captured frame by frame from a scratch server (`ncrecon-film-api`, scratch registry, jobs, truth, labels, audit, cache) via the app's `?rec=1` camera hook; building views Swannanoa (TUNE) only | Project; basemap © OpenStreetMap contributors, CARTO | 0:16 to 0:19, 0:30 to 0:43 |
| Offline packs (beta) | Swannanoa pack imported into a scratch install and served with `NCR_OFFLINE=1` under macOS `sandbox-exec` with all outbound network denied (outbound test returned no connection; 255 requests, all local). Basemap from the pack: USGS The National Map topo (public domain) | Project | 0:43 to 0:47 |
| Anatomy of a call | `site/assets/chips.json` (NC OneMap chips of record 17S LV 7253 4080), `anatomy_change.jpg`, `anatomy_ground.png`, evidence from `layers.json` `anatomy` | As above | 0:19 to 0:26 |
| Wildfire area view | App overview, Altadena at area level only (no building views; Altadena is a TEST area) | Project | 0:41 to 0:43 |

Type: Barlow Condensed, Overpass, Overpass Mono (SIL OFL 1.1), loaded from Google Fonts at render time, as the site does.

## Sound

- Music: original, synthesised by `score_v2.py`, with no samples: drums, sub bass, plucks, pads, risers, impacts and a bell. Owned by the project; no third-party licence.
- Voiceover: Kokoro-82M (Apache-2.0), voice `af_heart`, 11 lines in `assets/vo2/lines.json`.

## Figures on screen (v2)

| On screen | Source file |
|---|---|
| 532 road segments likely blocked | `pipeline/data/output/ops/swannanoa.response.json` `access.roads.blocked` |
| 9 search sectors, 1 km USNG | `swannanoa.response.json` `sectors` (9 entries) |
| 30 landing-zone candidates | `swannanoa.response.json` / `layers.json` `response_summary.landing_zone_candidates` |
| 74 buildings, about 113 people cut off if debris also blocks roads | `swannanoa.response.json` `summary.cut_off.plus_debris` |
| Destroyed 76%, Major 22%, Minor 3%, change z +2.8, ring max 0.31 m, search team Destroyed | `site/assets/terrain/layers.json` `anatomy` (from `swannanoa.geojson` and the SARCOP comparison) |
| 4856, Wildfires and Straight-Line Winds (CA, DR-4856-CA), incident 2025-01-07 | Captured from the app's lookup (OpenFEMA) |
| ~1,417 expected at Major or Destroyed, Altadena (area level) | `pipeline/data/output/ops/altadena.geojson` via the app overview |
| 15 of 19 severe calls agreed with county search teams | `swannanoa.sarcop_reference.json` `summary_homes.major_or_destroyed` (15 both, 19 called) |
| 95.7% of the wildfire model's Major or Destroyed calls matched CAL FIRE inspections; 2,246 buildings | `docs/model/MODEL_CARD.md`, pre-registered M1 evaluation on Altadena (precision 0.957, 2,246 matched); standalone model, not yet fused, stated on screen |
| Damage density | `site/assets/terrain/heat.png`, expected Major + Destroyed per building smoothed 70 m |

Nothing unbuilt is described in the present tense; offline packs are labelled (beta).

---

# Version 3, the story cut (98 s)

Script and research: [SCRIPT_v3.md](SCRIPT_v3.md). Built by `compose_v3.py`, `render.py --html composition_v3.html --out picture_v3.mp4` and `score_v3.py` (captures from `capture_v2.py`, including `area.png`). Renders: `build/ncrecon_launch_v3.mp4`, `_web.mp4`, `_preview.mp4` (101 s).

- **No voice.** Dated text cards carry the story. Type: Source Serif 4 (SIL OFL 1.1), from `web/node_modules/@fontsource-variable/source-serif-4`.
- **Music and ambience:** original, synthesised by `score_v3.py` (rain and river, piano, low strings, bell). No samples, no third-party licence.
- **Per-building damage** appears only for the showcase home the public site already shows (17S LV 7253 4080). The app screens are Swannanoa (TUNE).
- **New pictures:** Civil Air Patrol frame DSC_1463, 2024-09-29, mission 24-C-5836: crews mustering at a staging site. Captioned as "crews and search teams" because the people in it cannot be identified further.

| Card | Source |
|---|---|
| September 27, 2024: Helene floods the Swannanoa valley | NCEM Peak_Stage_Helene crest times (2024-09-27), DATA_SOURCES.md |
| Civil Air Patrol, September 28 and 29, 2024 | CAP frame folders `20240928T232313Z`, `20240929T171054Z` |
| More than 100 teams, 80,000 damage assessments by early October | DHS Science and Technology, 2024-10-07 (docs/research/responder-workflows-2026-10-22.md) |
| 4% of FEMA's incident workforce available after Helene and Milton | GAO-25-108598 |
| Destroyed, 76% likely; Major 22%; Minor 3% | `site/assets/terrain/layers.json` `anatomy` |
| 893 buildings in 88 seconds | `swannanoa.geojson` (893 features; `runtime_sec` 88.3) |
| 2,246 buildings checked by CAL FIRE inspectors; agreed 96% of the time when NC Recon called a building destroyed or badly damaged (95.7%) | `docs/model/MODEL_CARD.md`, pre-registered held-out evaluation of the wildfire model on Altadena (Eaton fire): 2,246 matched, Major or Destroyed precision 0.957. Replaced the Swannanoa 15 of 19 card, which was hard to read. |

---

# Version 4, "The scan" (70 s, plus a 31 s teaser)

Script and references: [SCRIPT_v4.md](SCRIPT_v4.md). Built by `clips_v4.py`, `prep_v4.py`, `logo_reveal.py`, `compose_v4.py <16x9|9x16>`, `render.py` and `score_v4.py`. Renders: `build/ncrecon_launch_v4_16x9.mp4`, `_9x16.mp4`, `_teaser_16x9.mp4`, `_teaser_9x16.mp4`.

- **Footage:** DVIDS, marked public domain: "Hurricane Helene Debris Swannanoa" (dvidshub.net/video/943308, taken 2024-11-01), NC National Guard aircrew (939562) and aviation b-roll (939345). Stated on the end card and to be stated in every post: no Department of Defense endorsement is implied.
- **Type:** Archivo variable (SIL OFL 1.1), `assets/fonts/archivo-latin-standard-normal.woff2`.
- **Music:** original, synthesised by `score_v4.py`. No samples, no voice, no third-party licence.
- **Terrain and imagery:** `site/assets/terrain` (USGS 3DEP elevation, NC OneMap imagery, OpenStreetMap roads). Building outlines from `prep_v4.py` are shown neutral, never by damage level.
- **Per-building damage** appears only for the showcase home the public site already shows (17S LV 7253 4080). App shots stay on panels, because the map panes carry per-building colours.
- **Logo:** "the odd one out", `docs/brand/`, rendered in Blender by `logo_reveal.py`.

| On screen | Source |
|---|---|
| September 27, 2024 | NCEM Peak_Stage_Helene crest times, DATA_SOURCES.md |
| Swannanoa, five weeks after | DVIDS 943308, taken 2024-11-01 |
| More than 100 search teams, 80,000 damage assessments | DHS Science and Technology, 2024-10-07 |
| 4% of FEMA's incident workforce available, after Helene and Milton | GAO-25-108598 |
| 893 buildings, 88 seconds | `swannanoa.geojson` (893 features; `runtime_sec` 88.3), run on one laptop |
| Destroyed, 76% | `site/assets/terrain/layers.json` `anatomy` |
| 96%; precision 95.7%, recall 94.2%; 2,246 buildings | `docs/model/MODEL_CARD.md`, pre-registered held-out evaluation of the wildfire model on Altadena (Eaton fire) |
| Free, open source | `LICENSE` (Apache-2.0) |

---

# Version 5, the launch cut (72 s)

Script and study notes: [SCRIPT_v5.md](SCRIPT_v5.md). Built by `fetch_v5_goes.py`, `fetch_v5_sfx.py`, `prep_v5.py`, `compose_v7.py <16x9|9x16>`, `render.py --sub 5` (motion blur) and `score_v8.py`. Renders: `build/ncrecon_launch_v8_<A|B|C>_<16x9|9x16>.mp4`.

- **Satellite:** NOAA GOES-16 ABI band 2, mesoscale sector 1, September 26, 2024 (`noaa-goes16` open data). Public domain.
- **Footage:** DVIDS, as in v4. Public domain. No Department of Defense endorsement implied.
- **Photographs in the flash:** Civil Air Patrol obliques, mission 24-C-5836 (FEMA `fema-cap-imagery`), and frames from DVIDS 943308, shown in black and white. Public domain.
- **3D models:** NVIDIA SimReady, CC BY 4.0, https://huggingface.co/datasets/nvidia/simready-assets, in the compressed copies at https://huggingface.co/datasets/codepawl/simready-glb.
- **Type:** Archivo variable (SIL OFL 1.1).
- **Music:** version A, 'Horizons' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au. Version B, 'Clarion' by Scott Buckley, same terms. Version C, "What Does Anybody Know About Anything" by Chris Zabriskie, from the album Direct to Video, CC BY 4.0, chriszabriskie.com. Placed by `score_v8.py`. Earlier scores dropped: the synthesised `score_v5.py`, then 'Hyperion' (`score_v6.py`) and 'Vanguard' (`score_v7.py`). Scott Buckley requires his credit in every YouTube description.
- **Per-building damage** appears only for the showcase home. The film's other buildings are neutral outlines.

## Sound effects (CC0, found through Openverse, hosted on Freesound)

- Thunder, Close, by Fission9: https://freesound.org/people/Fission9/sounds/505113
- Thunderclap, by Fission9: https://freesound.org/people/Fission9/sounds/534023
- Cinematic Impact Boom Metalic, by EminYILDIRIM: https://freesound.org/people/EminYILDIRIM/sounds/535413
- Low impact.wav, by AudioPapkin: https://freesound.org/people/AudioPapkin/sounds/430978
- R03-03-Cold Wind on Ship.wav, by craigsmith: https://freesound.org/people/craigsmith/sounds/481139
- Thunder, by blimp66: https://freesound.org/people/blimp66/sounds/332543
- Page Turn, by davidbain: https://freesound.org/people/davidbain/sounds/136778
- Camera Shutter Click, by Kodack: https://freesound.org/people/Kodack/sounds/271010
- es-stamp.wav, by eddies2000: https://freesound.org/people/eddies2000/sounds/448474
- Thump.mp3, by mpuffenbarger: https://freesound.org/people/mpuffenbarger/sounds/683031
- Reverse Mapex Ride.mp3, by MarcusGraham325: https://freesound.org/people/MarcusGraham325/sounds/240712
- cymbal-reversed-glassy-resonance.wav, by burnttoys: https://freesound.org/people/burnttoys/sounds/9523
- R29-04-Crashing Collapse of Wood Building.wav, by craigsmith: https://freesound.org/people/craigsmith/sounds/487142
- Rapidly Flowing Water (loopable).wav, by Osiruswaltz: https://freesound.org/people/Osiruswaltz/sounds/530168
- Helicopter Flyby, by Wonko_7: https://freesound.org/people/Wonko_7/sounds/723158
- cutting_tree.wav, by fkurz: https://freesound.org/people/fkurz/sounds/169127
- Four Heartbeats HQ_BeatSmith.wav, by Lunardrive: https://freesound.org/people/Lunardrive/sounds/22416
- SUB A# 2 secs.wav, by uzerx: https://freesound.org/people/uzerx/sounds/63138
- SUB OCEANO C.wav, by uzerx: https://freesound.org/people/uzerx/sounds/81147
- Impact, by chriskalos: https://freesound.org/people/chriskalos/sounds/172779
- Whip 9, by Geoff-Bremner-Audio: https://freesound.org/people/Geoff-Bremner-Audio/sounds/734692
- Whip 10, by Geoff-Bremner-Audio: https://freesound.org/people/Geoff-Bremner-Audio/sounds/734687
- Whip 8, by Geoff-Bremner-Audio: https://freesound.org/people/Geoff-Bremner-Audio/sounds/734691
- Typewriter's Key, by PerMagnusLindborg: https://freesound.org/people/PerMagnusLindborg/sounds/335898
- Hi-Hat Closed Hit - Clean, by TheEndOfACycle: https://freesound.org/people/TheEndOfACycle/sounds/674296
- DR Snare 135, by deadrobotmusic: https://freesound.org/people/deadrobotmusic/sounds/577106
- soft noise clap, by Saltbearer: https://freesound.org/people/Saltbearer/sounds/477808
- BELL.wav, by kgeshev: https://freesound.org/people/kgeshev/sounds/378799

| On screen | Source |
|---|---|
| Hurricane Helene headed for the mountains | NOAA GOES-16 frames; NHC track |
| The tally running to 80,000 | Illustrative count; the total is DHS Science and Technology, 2024-10-07 |
| 100+ search teams, 80,000 damage assessments | DHS Science and Technology, 2024-10-07 |
| 4% of FEMA's incident workforce available after Helene and Milton | GAO-25-108598 |
| 893 buildings, 88 seconds | `swannanoa.geojson`, `runtime_sec` 88.3 |
| Destroyed, 76% | `site/assets/terrain/layers.json` `anatomy` |
| 96%; precision 95.7%, recall 94.2%; 2,246 buildings | `docs/model/MODEL_CARD.md` |
