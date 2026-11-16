# Helene open data, satellite radar and open models (research record, 2026-10-22)

Two research passes by the original NC Recon session. Every endpoint was called
live without a key on 2026-10-22 unless marked UNVERIFIED. Companion to
`open-sources-any-hazard-2026-10-22.md` (the any-hazard pass).

## What is actionable

| Finding | Use in NC Recon | Status |
|---|---|---|
| Buncombe Helene Visual Damage Assessment points (UNCA NEMAC), 6,401 building-level points, no personal fields | second reference beside SARCOP (positives only: recall-style numbers) | candidate for `field_reference.py` |
| NC 2025 QL1 post-event lidar (NC OneMap DEM03), 12 WNC counties, against USGS 3DEP | ground change in a 2 to 10 m ring around each building (`analyze/ground_change.py`); on Swannanoa 9 of 12 search-team-checked flags were Major or Destroyed, mostly called No damage by imagery | measured on the 3 TUNE areas; channel wiring with the pipeline owner |
| NCGS Helene landslide polygons (source, transport, deposit) | debris-flow evidence (channel H) | being built by the fork session |
| Civil Air Patrol oblique photos (FEMA), each with heading, date and a direct image URL | photos beside each building for Verify reviewers (`collect/cap_photos.py`, `/ops/photos/...`) | built and checked in the browser |
| NCDOT post-Helene bridge inspections and slope failure sites | access and isolation context | candidate map layer |
| AORC hourly rainfall (NOAA on AWS) | storm totals per area for the brief | candidate context |

What does **not** help per building in western NC:

- No NASA/ARIA damage proxy map exists for Helene.
- OPERA DSWx has no coverage here.
- Capella and Umbra have no collects over WNC.
- The only post-peak Sentinel-1 pass over Swannanoa is 2024-10-03, six days after the crest, at 10 to 30 m resolution.

Satellite radar is keyless through Planetary Computer, but it is context only for this event.

On models:

- **SAM 2.1** (Apache-2.0, an ONNX port exists) is the clean next model: roof masks prompted by the footprint, sharpening E2 and E4. Adopting it changes every building's measurements, so it means recalibrating.
- **DINOv3 SAT-493M** has a licence clause covering ITAR and military use. That conflicts with the National Guard path, so skip it.

## A. Helene-specific products (western NC)

NC Recon: open, keyless Helene/WNC data products, live-checked 2026-10-22. All calls anonymous, HTTP 200 unless noted.
AOIs: Swannanoa (S) -82.42..-82.37/35.59..35.62; Marshall (M) -82.70..-82.67/35.79..35.81; Old Fort (OF) -82.20..-82.16/35.62..35.64.
Ranked by how useful each is for per-building damage assessment.

1. Buncombe Helene Visual Damage Assessment points (UNCA NEMAC). REFERENCE/VALIDATION ONLY
URL: https://services1.arcgis.com/PwLrOgCfU0cYShcG/arcgis/rest/services/Damage_Points_(Public_View)/FeatureServer/0
Licence: none stated (public view item d09d5f3ffed3453387ddbb10ca756d32).
Contents: 6,401 points; fields DamageType, GridNumber. Counts: Structure damage (flood) 1958, Landslide (no infra) 924, Tree on House 801, Structure Destroyed (flood) 736, Structure damage/destroyed (landslide) 159/46, Bridge damage/destroyed 163/127, Debris Field 239, plus roads.
Live: S=640, M=0, OF=0 (Buncombe County only).
Use: building-level damage labels made from imagery. Hold these out as truth; do not feed them in as evidence, or the labels leak into the evaluation.
Caveats: the "Sructure" typo is in the source values. No date or method fields. Points are not tied to footprints, so you need a spatial join.

2. NC 2025 QL1 lidar DEMs (post-event) via NC OneMap DEM03. NEW EVIDENCE CHANNEL (lidar dz)
URL: https://services.nconemap.gov/secure/rest/services/Elevation/DEM03/ImageServer (getSamples, exportImage, Download capability). Buncombe raster objectid 1286.
Contents: float32 elevation in feet, NC State Plane ftUS (NAD83 2011), 3.125 ft pixels. Countywide 2025 QL1 rasters exist for Ashe, Avery, Buncombe, Burke, Haywood, Henderson, Jackson, McDowell, Mitchell, Rutherford, Watauga and Yancey. Madison (Marshall) still has only the old "Madison_Ground_3ft". Licence: none stated.
Live: I differenced it against USGS 3DEP 1 m (https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer, 2017 Buncombe QL1), sampling inside the NCGS Helene polygons in S (~900 points):
  Source Area median dz -0.50 m (p10 -1.46); Transport Zone -0.22 m; Deposit +0.33 m (p90 +0.93).
  On stable ground near the Westwood Ave debris flow the median was +0.06 m, so the two surfaces are aligned (both assumed NAVD88).
Use: a per-building scour/burial signal (dz at the footprint and its upslope or channel neighbourhood), plus a map layer.
Caveats: the 2025 flight dates are not stated in the service. The baseline is 2017, an 8-year span, so construction and grading also show up as change. Bare-earth only, so it cannot show roof damage. No 2025 coverage for Madison/Marshall.
3DEP itself (question 6): the TNM and 3DEP index for all three AOIs show only 2014 data and NC_Phase5 2017 QL1 (published 2021). There is no post-event 3DEP lidar.

3. NCGS Landslide Inventory of North Carolina (NCDEQ). EVIDENCE CHANNEL (hazard) + PARTIAL REFERENCE
URL: https://services2.arcgis.com/kCu40SDxsCGcuUWO/arcgis/rest/services/NC_Landslide_Inventory/FeatureServer
Licence: NCDEQ no-charge access with an accuracy disclaimer ("user must ... bear responsibility with respect to errors").
Contents:
  L0 Observations: 8,144 points, 8,111 tagged "2024/09/27 Helene". Fields Impact (Road 5489, Dwelling 375, Building 219), Damage (Destroyed 365, Completely/Partially collapsed, Covered by debris, Displaced from foundation, ...), Fatalities, Comments, SiteVisit.
  L1 Ground Ruptures: 166 lines.
  L2 Landslide Features: 31,376 polygons, 23,201 Helene. Fields FeatureType (Source Area/Transport Zone/Deposit/Outline), LandslideType, Existence/LocationConfidence, Basemap ("2025 UNC Collaboratory Imagery & 2025 NC Geological Survey LCD").
Live, Helene-filtered: S = 141 observations (29 Dwelling/Building), 275 polygons. M = 0. OF = 0. The 1 polygon in M and 5 in OF are pre-Helene, "Dormant".
Use: debris-flow polygons as an evidence channel (footprint intersects a Transport/Deposit zone). Dwelling/Building damage observations are reference only.
Caveats: still being updated. Comments mention fatalities, so be careful if shown publicly.

4. Civil Air Patrol imagery (FEMA). IMAGERY EVIDENCE / MAP LAYER
Photo points: https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/Image_Points_view/FeatureServer (L0 Ground, L1 Aerial Oblique 159,819, L3 Aerial Nadir 704,948). Fields: lon/lat, altitude, heading, exif_photo_date, project="CAP - H-TS Helene 2024", url.
Live: obliques S=60, OF=64, M=0. Nadir S=316, OF=150. A sample JPG (fema-cap-imagery.s3.amazonaws.com/.../DSC_0547.JPG, 2024-09-28) returned HTTP 200.
Orthos: https://disasters.geoplatform.gov/image/rest/services/CAP_Ortho/ImageServer, 4-band, about 8-9 cm. Mosaics SWANNANOA_E/W and MCDOWELL_NW/NE/S cover S and OF; M has only an overview. exportImage returned a 68 KB JPEG over S.
Licence: none stated.
Use: per-building visual evidence (pick obliques by heading toward the footprint), and orthos for VLM review.
Caveats: some nadir EXIF dates are bogus (year 2000). Coverage is mission-driven.

5. NCEM Helene Estimated Flood Inundation (Jan 2025). EVIDENCE CHANNEL (flood extent) / LAYER
URL: https://services1.arcgis.com/YBWrN5qiESVpqi92/arcgis/rest/services/HeleneEstimatedFloodInundation_Jan2025/FeatureServer/0
Contents: 2,082 polygons; fields Floodplain (100/500 year), FIRM_ID. Copyright "NCEM Flood Mapping Program, ICEYE". Licence note: an estimate, NCEM's "best guess"; full field surveys are needed for accuracy.
Live: S=9, M=12, OF=22.
Caveats: built as SFHA polygons intersected with SARCOP, SAR damage points, ICEYE and high-water marks. Because SARCOP went into it, it is circular with NC Recon's existing SARCOP channel.

6. NCDOT structures and slope failures. CONTEXT / LAYER
- Post-Helene structure inspection status: https://services.arcgis.com/NuWFvHYDMVmmxMeM/arcgis/rest/services/2024_NCDOT_SMU_Post_Helene_Structure_Inspection_Status/FeatureServer/0. 7,115 bridges/culverts; fields Status, Damage_Type, Has_Outlet. Live: S=8 (e.g. SR2727 over the Swannanoa River, "Approach Washout"), M=3, OF=14.
- GAM Helene failure sites: https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/NCDOT_GAM_Helene_Failure_Sites/FeatureServer/0. 1,150 points with failure volume and roadway impedance. Live: OF=4, S=0, M=0.
Use: access/isolation context for households, not damage to buildings. Licence: none stated.

7. USGS Hurricane Helene Landslide Inventory (preliminary, DOI 10.5066/P14CHGKS). EVIDENCE / REFERENCE
URL: https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/USGS_Hurricane_Helene_Landslide_Inventory/FeatureServer/0
Contents: 2,217 points; fields Source, Impact (Road 613, River 297, Building 264, ...). Federal data release; the item states no licence beyond a trade-name disclaimer.
Live: S=13, OF=1, M=0.
Mostly overlaps the NCGS inventory and has less detail. The FEMA DR-4827 public landslide map uses it alongside a separate NCGS service, North_Carolina_Post_Helene_Landslide_Inventory.

8. NASA Earthdata GIS Helene rasters. COARSE EVIDENCE / LAYER
- Landslide Proxy Heat Map (Sentinel-1 backscatter change, GSFC; Handwerger 2022): https://gis.earthdata.nasa.gov/portal/rest/services/DISASTERS_202409_HURRICANE_HELENE/202409_ls_proxyheatmap/ImageServer. F32, 10 m. Pre-event stack 2024-01-10..09-26, post-event 09-28..10-17. Values are a relative density, 0 to ~1.6e-4, with no calibrated cutoff. Live: S mean 2.2e-6, max 1.44e-5; sample points in M and OF returned ~1.1e-5 to 1.6e-5 (order not tied to points, so not attributed per AOI). "Not verified in field."
- OPERA DIST-ALERT-HLS (2024-10-02): .../202427_opera_dist_hls/ImageServer, 30 m. VEG-DIST-STATUS codes: 0 none; 1-3 first/provisional/confirmed <50%; 4-6 the same at >=50%; 7 confirmed <50% finished; 8 confirmed >=50% finished; 255 nodata. VEG-ANOM-MAX is 0-100% vegetation loss. Live: S point status 1 / anomaly 31; OF status 7 / anomaly 34. Raw COGs (2-4 MB) are at https://d1z62tir4fw0q0.cloudfront.net/20240926-Hurricane_Helene/DIST/.
- OPERA DSWx-S1 flood extent: footprints reach only lat 31.73 (Florida/Georgia). NO WNC COVERAGE. The pass was 2024-09-26 23:38 UTC, before the WNC crests anyway.
Use: the 30 m and 10 m grids only work as neighbourhood priors.

9. AORC v1.1 hourly precipitation (NOAA, AWS). CONTEXT
URL: https://noaa-nws-aorc-v1-1-1km.s3.amazonaws.com/2024.zarr/APCP_surface (Zarr v2, zstd, int16 x0.1 mm, ~1 km).
Live: I decoded it with python zstandard for 2024-09-24T12Z..09-28T00Z: S 480 mm (18.9 in, peak hour 53 mm); OF 547 mm (21.5 in, peak 64 mm); M 184 mm (7.2 in).
MRMS 72h QPE Pass2 hourly GRIB2 is also listed keyless at noaa-mrms-pds/CONUS/MultiSensor_QPE_72H_Pass2_00.00/20240928/. Values are UNVERIFIED there because I had no GRIB decoder locally.

10. NWS Damage Assessment Toolkit. LOW VALUE
URL: https://services.dat.noaa.gov/arcgis/rest/services/nws_damageassessmenttoolkit/DamageViewer/FeatureServer (layers 0/1/2).
Live: only 11 points, 3 tracks and 1 polygon in the WNC bbox for 09-25..09-28 (EF0-EF1, mostly trees, RNK/GSP offices). Zero in the AOIs.

Also found:
- Burke County NCEM damage assessment: https://services3.arcgis.com/axQ4OCSpcxALIQsV/arcgis/rest/services/NCEM_Damage_Assessment_BC/FeatureServer/119. 456 field points with FEMA categories (affected 30, minor 151, major 257, destroyed 13), Damage_Val, BLDG_Val, REID. Burke only, so none in the AOIs. REFERENCE ONLY.
- FEMA WorldView 2024-10-06: https://disasters.geoplatform.gov/image/rest/services/Hurricane_Helene_2024/Hurricane_Helene_Worldview_20241006/ImageServer, 0.36 m. Strips cover only Boone, Newland, Bakersville, Forest City and upstate SC; NoData in all AOIs. Likely Maxar-licensed; none stated.
- NCDOT 0.25 ft post-event orthos (tiles.arcgis.com/tiles/NuWFvHYDMVmmxMeM/...): the I-40/I-26 (09-29), Asheville, Lake Lure and Haywood extents miss all three AOIs. The NCDOT lidar dz layer covers I-40 in Haywood County only.
- Not usable: "Buildings Footprints Affected by Hurricane Helene" (services1.arcgis.com/pf6KDbd8NVL1IUHa, damage_pct fields) covers only the Florida Big Bend (lat 29.7-29.97).

Excluded:
- SARCOP_v9_SIFS_NC_Damage (services6.arcgis.com/VLA0ImJ33zhtGEaP; 12,891 points, S=2,218) is in the Buncombe County org. It is likely the "Buncombe SARCOP" NC Recon already uses. It contains team_user, email and human_remains fields; do not expose those.

Negatives and UNVERIFIED:
- ARIA/OPERA Damage Proxy Map for Helene: none found.
  - The ARIA-share bucket prefix 20240926-Hurricane_Helene/ holds 13 objects (DIST, DSWx, RTC), none of them a DPM.
  - The NASA Earthdata GIS Helene folder has 9 services, none a DPM.
  - ArcGIS Online "damage proxy" + Helene search: 0 hits.
  - ASF: UNVERIFIED. Making our own InSAR coherence product would need an Earthdata login for Sentinel-1 SLCs, so it would not be keyless.
- Copernicus EMS / International Charter: UNVERIFIED. The CEMS API requires an activation code, and a web search found no Charter record.
- USGS flood-inundation maps specific to Helene: not found beyond STN, which NC Recon already uses.

## B. Keyless satellite and radar access, open models

### Access (Swannanoa bbox, 2024-09-20..10-10)

- **Planetary Computer (VERIFIED).** An anonymous SAS token returns HTTP 200 for sentinel-1-grd, sentinel-1-rtc, sentinel-2-l2a, 3dep-seamless and naip.
  - A range GET with the token returns 206; without the token it returns 409.
  - Tokens last about 45 minutes. Rapid token calls return 429, so cache one token per collection.
  - Omit `datetime` in a search rather than sending null, which returns 500.
  - 3dep-lidar-copc has no NC coverage.
  - NAIP's newest scene here is 2022 (pre-event only).
- **Earth Search v1 (VERIFIED).** Sentinel-2 L2A COGs are plain HTTPS.
  - Sentinel-1 GRD can be read anonymously even though its items say requester-pays, so that access may stop.
  - The GRD is not terrain-corrected.
- **Copernicus Data Space (VERIFIED).** Search is anonymous; every download needs an account (401).
- **Overture buildings 2026-10-21.0 (VERIFIED).** A pyarrow anonymous S3 read of the Swannanoa bbox returns 4,271 buildings in 2.8 s.
  - 4,103 have OSM as their primary geometry, and Microsoft supplies the heights.
  - There are no Google or Esri sources.
  - Licence is ODbL-1.0 (share-alike).
  - Low marginal value over FEMA USA Structures plus OSM.
- **Capella and Umbra open SAR (VERIFIED).** No collects inside lon -85.5..-79.5, lat 33.5..37 for September to November 2024.
- **OPERA DSWx-S1/HLS.** CMR search is keyless, but downloads need Earthdata Login (401). Resolution is 30 m.
- **Timing.** The flash flood peaked about 2024-09-27.
  - Sentinel-1 post-event pass: 2024-10-03 only.
  - Sentinel-2: 10-02 (19% cloud) and 10-07 (10% cloud).
  - Gauge crests (E5) beat any 10 to 30 m flood extent here.

### Open models, ranked for per-building damage at 15 cm

1. **SAM 2.1 hiera-tiny** (`facebook/sam2.1-hiera-tiny`, Apache-2.0; ONNX `onnx-community/sam2.1-hiera-tiny-ONNX`) plus samgeo (MIT). Footprint-prompted roof masks on pre and post imagery. Build next.
2. **DINOv3 ViT-L/16 SAT-493M** (custom DINOv3 License). Pre/post feature distance per footprint; measured 0.26 s per 224 px chip on CPU. The licence has an ITAR/military clause: skip.
3. **Microsoft building-damage-assessment** (MIT). A labelling and fine-tune loop; no pretrained 15 cm model.
4. **AnyChange / torchange** (Apache-2.0). Zero-shot change prototype. ChangeOS has no licence: skip.
5. **Qwen3-VL-4B/8B, granite-vision-3.3-2b** (Apache-2.0). An optional aid for checking disputed calls, not an evidence channel; tens of seconds per image on CPU.
6. **BRIGHT** (optical plus SAR building damage). Needs post-event very-high-resolution SAR, and none exists over WNC.
7. **Clay v1.5, Prithvi-EO-2.0 / TerraMind, ml4floods.** Run at 10 to 30 m (patch level), and ml4floods models are non-commercial. They do not help single buildings.
8. **xView2 first place.** Already in `weights/`.
