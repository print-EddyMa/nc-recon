# Data sources register (ops mode)

Every source was called live on **2026-09-26** before it was wired in. Fixtures
of trimmed responses are in `pipeline/tests/fixtures/` (dated). Live status of
each connector: `python scripts/run.py ops-health` (also `GET /ops/health`, and
the Collection-status panel on the Operations screen).

| Source | Used for | Access | License | CRS / datum | Status and caveats (2026-09-26) |
|---|---|---|---|---|---|
| **USGS Water Data OGC API** `api.waterdata.usgs.gov/ogcapi/v1` | 290 NC stream gauges (discharge 00060, gage height 00065), gauge datum elevations, peak flows | keyless; `NCR_USGS_API_KEY` raises limits | US Gov | WGS 84 as served; gauge `altitude` + `vertical_datum` (often NAVD88) | Replaces legacy NWIS WaterServices, which **returned 503** on 2026-09-26 (decommission Q1 2027). `latest-continuous` has no state field: bbox query joined to `monitoring-locations` (state 37, site type ST). Links moved `v0` → `v1`. |
| USGS legacy WaterServices | nothing (shown on the health board only) | n/a | US Gov | n/a | **Down (503).** A test fails if any code calls it. |
| **NOAA NWPS** `api.water.noaa.gov/nwps/v1` | flood categories, forecasts, gauge datums, crest history | keyless | US Gov | stage ft above gauge datum | In-town gauges exist (MICN7 Mill Creek at Old Fort, datum NAVD88 1444 ft; SOTN7 N Toe R at Spruce Pine) but **crest history has no Helene crest** (latest 2015 / 2017). |
| **USGS peaks** (OGC `peaks`) | Helene crests | keyless | US Gov | stage ft | Has 2024-09-27 peaks (e.g. 02137727 Catawba R nr Pleasant Gardens 21.82 ft / 42,400 cfs) but on reaches ~11 km from the AOIs, so not used for building depth there. |
| **USGS STN** `stn.wim.usgs.gov` | high-water marks | keyless | US Gov | `vdatum_id` 2 = NAVD88; HWM quality ±0.05–0.4 ft | Helene = event 346, 321 HWMs; **none within 5 km** of any current AOI (they cluster near the SC line). |
| **OpenFEMA DisasterDeclarationsSummaries v2** | event registry (incident period, designated areas) | keyless | US Gov | n/a | DR-4827-NC: incident began **2024-09-25**, declared 2024-09-28, 40 designated areas. IA shows up as **`ihProgramDeclared`** (IHP-era), not `iaProgramDeclared`. |
| FEMA Historical Geospatial Damage Assessment DB (FEMA_MAC FeatureServer) | ground truth | keyless | US Gov | points WGS 84 | Live, but **newest event is 2020**: no Helene / DR-4827 rows. NC has 9,413 modeled rows for Matthew 2016 (usable for an E5 backtest). |
| **USACE NSI 2022** `nsi.sec.usace.army.mil/nsiapi` | occupancy (Hazus), stories, foundation type/height, ground elevation, day/night population | keyless | US Gov | WGS 84; `grnd_elv_m` NAVD88 (3DEP); `found_ht` ft | Occupancy codes carry suffixes (`RES1-1SNB`). `cbfips` are **2010** blocks (we spatially join to 2020 tracts instead of crosswalking). `-9999` sentinels nulled. |
| **FEMA USA Structures** (Esri Federal Data view) | primary footprints, occupancy, outbuilding, height, population median + 95% CI, address | keyless ArcGIS | US Gov | WGS 84 | Old Fort box: **1,395 footprints vs 760 in OSM**. Footprints digitised from **2014–2019** imagery (newer homes missing). Addresses kept out of public outputs. |
| OpenStreetMap (Overpass) | gap-fill footprints | keyless | **ODbL** | WGS 84 | Used only where no USA Structures footprint overlaps (≥30% of the OSM polygon). Ids are OSM element ids. |
| **Maxar Open Data** (Helene) | pre/post satellite imagery (Old Fort, Spruce Pine) | S3 COGs + STAC TSV | **CC BY-NC 4.0** | WGS 84 UTM 17N ARD | NC coverage is **only two clusters** (Old Fort–Marion, Spruce Pine); a third cluster is Erwin, TN. Per-capture off-nadir / sun / cloud % from the TSV feed the context rules. |
| **NC OneMap `Orthoimagery_2020_2023_4band_analysis`** | pre-event aerial (all NC) | keyless ImageServer `exportImage` (≤2,500 px per request; 4,000 px returns an HTML error page) | NC OneMap / CGIA / NC 911 Board | EPSG:6543 (ftUS) native; served resampled to our UTM grid | "Analysis" service: compression "minimizes the alteration of individual pixel values", so it is usable for change detection. The catalog query returns 500, so the **per-tile acquisition date is not exposed**; recorded as "2020–2023 cycle, leaf-off". |
| **NC OneMap `Orthoimagery_Helene_2025`** | post-event aerial, 13 WNC counties | keyless ImageServer | NC Collaboratory / UNC | EPSG:6543 | Spring 2025, leaf-off, 6 in. Counties: Alexander, Ashe, Watauga, Avery, Mitchell, Burke, Yancey, McDowell, Rutherford, Buncombe, Henderson, Haywood, Jackson (**not Madison**). Seamline edits focused on major roads; smears possible elsewhere. |
| **NOAA NGS ERI** `noaa-eri-pds` | post-event aerial (Oct 5–8 2024 over WNC) | public S3; tile names encode centre coords | US Gov | EPSG:4326 tiles, ~0.15 m, 512 px blocks + overviews | 9,576 Helene tiles, **4,131 over WNC**; covers Swannanoa, Chimney Rock, Marshall, Asheville. Indexed from the bucket listing alone. |
| **CDC/ATSDR SVI 2022** (ArcGIS, tract layer 2) | need index | keyless | US Gov | WGS 84 | Used via spatial join on 2020 tracts. `RPL_THEMES` −999 = no data. Snapshot cached under `data/cache/ops/svi/`. |
| **Census ACS API** | occupied / seasonal share (B25002, B25004) | **now requires a key** (`NCR_CENSUS_API_KEY`): keyless requests redirect to `missing_key.html` | US Gov | 2020 tracts | Without a key, displacement is reported as an **unadjusted upper bound**. |
| NC DEQ "Helene flood extents" (ArcGIS layer) | context only | keyless | **unstated** | Web Mercator | Covers Old Fort (3 polygons), but has no method or license statement, so it is not used as evidence. |
| Google Earth Engine | (future) Sentinel-2/HLS/CCDC | account + project | per dataset | — | Unconfigured (`NCR_GEE_PROJECT`). |
| NASA Earthdata (OPERA DSWx/DIST, HLS, NISAR) | (future) SAR / optical time series | Earthdata Login | NASA open | — | Unconfigured (`~/.netrc`). |

## Geodesy facts verified here

* NAD83(2011) → ITRF2014 at Old Fort, epoch 2026.7: **1.163 m horizontal, 1.326 m vertical** (PROJ 9.5.1, 14-parameter time-dependent Helmert; not a ballpark transform). Test: `tests/test_geodesy.py`.
* Maxar ARD is WGS 84 / UTM 17N; NC OneMap is NAD83(2011) / SPCS ftUS; ERI is EPSG:4326. The ~1 m realization gap between them is absorbed by per-building local alignment (±6 m search), and each building's measured shift is recorded (`measurements.local_shift_m`).
