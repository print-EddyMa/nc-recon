# Assessing any disaster

Groma started on Hurricane Helene in western North Carolina. The engine is
not specific to either: an event is a FEMA declaration (or a manual incident
date), a hazard profile says which evidence applies, and the imagery and
structure sources cover the whole country.

## 1. Start the event from its FEMA number

```
python scripts/run.py ops-event-from-fema --disaster 4856            # draft only
python scripts/run.py ops-event-from-fema --disaster 4856 --write    # register it
```

Same thing over the API: `POST /ops/events/from-fema {"disaster_number": 4856, "write": false}`.

The draft fills in:

* incident date, state and designated counties (OpenFEMA)
* hazards, from the incident type (`config/hazards.yaml`): a fire declaration
  is `wildfire`, a hurricane is `wind`, `riverine_flood` and `coastal_surge`
* the post-event imagery window: the widest default across those hazards
* matching NOAA Emergency Response Imagery and Maxar Open Data folders,
  scored by name and year, with the reasons shown. A folder is picked only
  when its score is clear and not tied; otherwise the draft says so.

## 2. Assess an area

Pick a point in the operations screen or call `POST /ops/assess`. Imagery is
chosen per point:

| Side | Source | Rule |
|---|---|---|
| Before | NC Orthoimagery Program (NC), else USDA NAIP | must be flown inside the event's pre window; NAIP holds only the latest year, so a collection flown after the incident is refused |
| After | the event's `post_sources`, in order | the first that covers the point (NOAA ERI, Maxar, NC post-Helene orthos) |

`GET /ops/coverage?event=&lon=&lat=` answers both before anything is fetched.

## 3. Evidence by hazard

| Channel | What it reads | Hazards |
|---|---|---|
| E1 | optical damage classifier on the after image | all |
| E2 | pixel change, before vs after | all |
| E4 | new blue tarps on roofs | flood, wind, tornado, surge |
| E5 | flood depth against the first floor (gauge crests) | river and flash flood |
| E6 | lidar ground change around the building (deposit or scour) | flood, landslide (NC 2025 lidar counties) |
| H | where the hazard reached: inside or outside a fire perimeter, ShakeMap shaking at the building, inside a mapped landslide | wildfire, earthquake, landslide |
| M1 | Groma's own damage model (`ops/model`), before and after chips | wildfire, in place of E1 wherever it has a usable chip (`channels.M1.mode: replace`) |

For wildfire, M1 replaces E1 under the rule fixed before its evaluation
(`docs/model/MODEL_CARD.md`). That evaluation scored M1 on its own; the fused
pipeline with M1 has not been scored yet and needs a fresh wildfire, because
Altadena is now spent as a hold-out for M1.

A channel that does not apply is recorded as `NOT_APPLICABLE_FOR_HAZARD`. A
source that is down or has nothing there is recorded as unavailable with a
reason, and the assessment carries on without it. Every likelihood is
provisional (hand-set from definitions) until analysts label under the
protocol.

## 4. Compare with published records

```
python scripts/run.py ops-field-reference --area <area> [--source dins|fema_hgda|nemac|sarcop] [--allow-test]
```

| Source | Hazard | What it is |
|---|---|---|
| `dins` | wildfire (California) | CAL FIRE ground inspections, five FEMA-style levels |
| `fema_hgda` | hurricanes, floods, tornadoes, earthquakes 2011-2020 | FEMA's imagery-observed damage points |
| `nemac` | Helene, Buncombe County | damaged and destroyed buildings only (recall-style) |
| `sarcop` | Helene, Buncombe County | search-and-rescue structure categories |

These are comparisons, not accuracy figures. TEST (hold-out) areas need
`--allow-test`, and nothing is tuned on them.

## What is not built yet

* Hurricane wind swaths (NHC) and tornado tracks (NWS) as footprints. The NWS
  survey points are also the natural tornado reference, so one source cannot
  be both.
* USGS high-water marks as an E5 source outside NC.
* Overture building footprints for places FEMA USA Structures does not cover.
* Radar (Sentinel-1) for cloud-covered events.

Sources and live checks: `docs/ops/DATA_SOURCES.md` and
`docs/research/open-sources-any-hazard-2026-10-22.md`.
