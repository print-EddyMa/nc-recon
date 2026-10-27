# Open data and models for any hazard (research record, 2026-10-22)

Two research passes, every endpoint called live without a key on 2026-10-22
unless marked UNVERIFIED. Purpose: let NC Recon (Groma) assess any US disaster,
not only Helene, and validate itself on more than one hazard.

## Building-level ground truth (validation and calibration)

| Source | Endpoint | Hazard | Size | Notes |
|---|---|---|---|---|
| CAL FIRE DINS master | `services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0` | wildfire | 132,522 points, 2013-2025; Eaton 18,428 | DAMAGE uses FEMA-like levels (No Damage, Affected 1-9%, Minor, Major, Destroyed >50%, Inaccessible); structure type, roof, eaves, vents, year built. As-is disclaimer. |
| FEMA Historical Geospatial Damage Assessment DB | `services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/FEMA_Historical_Geospatial_Damage_Assessment_Database/FeatureServer/0` | hurricane, flood, tornado, earthquake | 930,839 points, 19 events 2011-2020 | Filter `ASMT_TYPE='RS'` (266k imagery-observed); 664k are modelled from depth grids. Events with ERI imagery: Joplin, Sandy, Harvey, Irma, Maria, Michael, Laura, Matthew, Nate, Isaac, Nashville. |
| NWS Damage Assessment Toolkit | `services.dat.noaa.gov/arcgis/rest/services/nws_damageassessmenttoolkit/DamageViewer/FeatureServer` (0 points, 1 tracks, 2 polygons) | tornado, wind | 240,667 points | EF damage indicator and degree of damage per building; tracks double as footprints. St. Louis 2025-05-16: 10,914 points. |
| NCGS Landslide Inventory | `services2.arcgis.com/kCu40SDxsCGcuUWO/arcgis/rest/services/NC_Landslide_Inventory/FeatureServer` | landslide (Helene) | 8,109 observations, 31,376 polygons | Observations record dwelling impact and damage; polygons are source, transport and deposit zones. Swannanoa: 141 observations, 287 polygons. |
| USGS Helene Landslide Inventory | `services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/USGS_Hurricane_Helene_Landslide_Inventory/FeatureServer/0` | landslide | 2,217 points, 264 building impacts | Public domain, DOI 10.5066/P14CHGKS. |
| Copernicus EMS Rapid Mapping | `rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSR773` | any (outside US) | per activation | Grading layers per building; listing activations is not keyless. |

## Hazard footprints (where the hazard reached, how hard)

| Hazard | Source | Endpoint |
|---|---|---|
| Earthquake | USGS ComCat + ShakeMap | `earthquake.usgs.gov/fdsnws/event/1/query?eventid=<id>&format=geojson`, then `products.shakemap[0].contents["download/cont_mmi.json"]` (MMI contours) and `grid.xml` |
| Wildfire | NIFC WFIGS perimeters | `services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters/FeatureServer/0` (42,876 since 2016; key on `attr_UniqueFireIdentifier`) |
| Tornado and wind | NWS DAT tracks; SPC reports | as above; `spc.noaa.gov/climo/reports/YYMMDD_rpts_torn.csv` |
| Hurricane wind | NHC best track archive | `nhc.noaa.gov/gis/best_track/<storm>_best_track.zip` (`_windswath`, `_radii`) |
| Flood | USGS STN events and high-water marks | `api.waterdata.usgs.gov/stnservices/events/` and `.../hwms/?event=<id>` (the old `stn.wim.usgs.gov` base now redirects to a web app) |
| Flood-prone context | FEMA NFHL | `hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28` |
| Global event detection | GDACS | `gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=EQ;TC;FL;WF` |

## Imagery for any event

* **NOAA ERI** (`noaa-eri-pds`): 53 event folders, 2005 Wilma to 2026 Isaias,
  including tornadoes (Joplin, Nashville), floods (Midwest, Texas 2025) and
  the 2025 California fires (flight 2025-01-28 covers Altadena and Palisades).
  Newer events also publish a parquet index.
* **Maxar Open Data**: 55 events, CC BY-NC (never in paid products).
* **NAIP**: USGS National Map ImageServer (latest statewide year only, keyless)
  and Planetary Computer STAC (all years, COGs readable anonymously today).
* **Sentinel-2 L2A**: Earth Search and Planetary Computer, anonymous reads.
* **Sentinel-1 RTC**: Planetary Computer, anonymous SAS token (cache it; the
  token endpoint rate-limits after about 7 calls).
* **Civil Air Patrol image points**: `services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/Image_Points_view/FeatureServer`,
  geotagged obliques and nadir frames with keyless JPG links (Swannanoa: 60
  oblique, 316 nadir), for reviewers.
* **Umbra open SAR**: one Helene collect over south-east Asheville
  (2024-09-29, 0.25 m, CC BY 4.0); none over the assessed towns.
* **Post-Helene lidar**: NC OneMap `Elevation/DEM03` holds 2025 QL1 rasters
  for 12 WNC counties (feet); 3DEP has the 2017 surface (metres). Madison
  County was not reflown.

## Structures anywhere

* **Overture Maps buildings** (release `2026-10-21.0`): anonymous pyarrow
  reads from `s3://overturemaps-us-west-2/release/<rel>/theme=buildings/`,
  pruning row groups by bbox statistics (6.3 s for 4,271 buildings in
  Swannanoa). ODbL: share-alike obligations on derived footprint layers.

## Models (ranked for per-building damage)

1. **ChangeOS Swin-T on xView2** (Apache code and weights; trained on xBD, so
   non-commercial in practice): independent multi-hazard second opinion to E1,
   about 0.8 s per 512 px tile on CPU, ONNX-exportable.
2. **BRIGHT baselines** (optical pre plus SAR post, 14 events, 7 hazards):
   only route to all-weather building damage when open VHR SAR exists.
3. **HOT DINOv3 damage model** (ONNX ready, CC BY-NC-SA): evaluation only.
4. **SAM 2.1 tiny** (Apache): refit footprints on post imagery; structural
   loss cue for any hazard. Licence-clean.
5. **Microsoft building-damage-assessment** (MIT): workflow to fine-tune a
   licence-clean head on our own labels.
6. **TerraMind Flood/Fire** (Apache, 10 m): area-level hazard extent, not
   buildings. Prithvi, xBD-S12 and Sen1Floods11 likewise only area-level.

What does not help: any 10-30 m model for single buildings; generic
remote-sensing chat models as evidence (at most an explanation aid on flagged
buildings).

## Helene-specific findings

* No ARIA damage proxy map exists for Helene over WNC.
* Only two Sentinel-1 passes (Sep 21, Oct 3) and cloud on Sep 27; flash floods
  had drained before clear optical passes. Gauge crests (E5) stay the better
  flood evidence in the mountains.
* NCEM's estimated flood inundation layer is built partly from SARCOP, so it
  is circular with the SARCOP comparison.
