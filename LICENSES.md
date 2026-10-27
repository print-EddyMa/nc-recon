# License ledger

| Component | License | Obligation for Groma outputs |
|---|---|---|
| Groma code, web app and site | Apache-2.0 (`LICENSE`, `NOTICE`) | Keep the licence and notice when redistributing. Data outputs carry the obligations of the sources below. |
| OpenStreetMap footprints (gap-fill) | ODbL 1.0 | Attribution "© OpenStreetMap contributors"; a derived *database* including them must be ODbL. Exports mark `footprint_source = osm`. Open question (OSMF Horizontal Layers guideline): merging OSM and USA Structures outlines in one building layer makes that layer a derivative database; the damage attributes are kept in Groma's own table keyed by footprint id so the county's assessment data is not pulled under ODbL. |
| FEMA USA Structures | CC BY 4.0 (per the Esri item's licence statement, checked 2026-10-07) | Credit FEMA / ORNL with the CC BY notice. Addresses are PII-adjacent: responder mode only. |
| USACE NSI 2022 | US Government work | Credit USACE. |
| Maxar Open Data (Helene) | CC BY-NC 4.0 | Non-commercial use only, with attribution. Products derived from Maxar imagery inherit NC. |
| NC OneMap orthoimagery (2020–2023 program; Helene 2025) | Public (NC OneMap / CGIA / NC 911 Board; NC Collaboratory) | Credit the providers. |
| NOAA NGS ERI | US Government work | Credit NOAA NGS. |
| USGS Water Data, STN, 3DEP | US Government work | Credit USGS. |
| NOAA NWPS / NWS / NHC | US Government work | Credit NOAA. |
| OpenFEMA | US Government work, OpenFEMA terms | No FEMA endorsement implied. |
| Buncombe County SARCOP extract (comparison only) | unstated (county ArcGIS Online item) | Not redistributed; only aggregates and Groma structure ids are stored. Personal fields on the layer are never fetched. |
| Civil Air Patrol aerial photos (FEMA) | unstated (FEMA AGOL item; federal auxiliary imagery) | Shown to responders on the Verify screen; a reduced copy is cached locally, linked to the original. Not redistributed in exports. |
| NC 2025 QL1 lidar (NC OneMap DEM03) and USGS 3DEP | DEM03 unstated (NC OneMap / NC 911 Board); 3DEP public domain | Derived per-building statistics only (ring dz percentiles, a flag); the elevation rasters are cached locally and not redistributed. |
| USDA NAIP (pre-event imagery outside NC) | Public domain (USDA FSA) | Credit USDA FSA NAIP. |
| NIFC WFIGS fire perimeters; USGS ComCat and ShakeMap | US Government work / public domain | Credit NIFC and USGS. Used as context (channel H), cached per area. |
| NC Geological Survey landslide inventory | unstated (NC DEQ / NCGS ArcGIS item) | Used per building as context (channel H); polygons are not redistributed. |
| CAL FIRE DINS (comparison only) | State of California, provided as-is | Not redistributed; only aggregates and Groma structure ids are stored. Addresses, parcel numbers and values on the layer are never fetched. |
| FEMA Historical Geospatial Damage Assessment DB (comparison only) | US Government work | Credit FEMA; only imagery-observed records are compared. |
| Buncombe / UNCA NEMAC Helene damage points (comparison only) | unstated (county ArcGIS item) | Not redistributed; only aggregates and Groma structure ids are stored. |
| OpenStreetMap facilities and roads (response products) | ODbL 1.0 | Attribution "© OpenStreetMap contributors"; the response layers derived from OSM roads and facilities are a derived database: share-alike applies if they are redistributed. |
| FEMA Hospitals (RAPT) | US Government work (FEMA; HIFLD-derived) | Credit FEMA. |
| USACE National Inventory of Dams | US Government work | Credit USACE. |
| EPA EMEF facility points (SEMS, TRI, NPDES) and community water system service areas | US Government work; public domain | Credit EPA. |
| FAA aviation facilities (BTS NTAD) | US Government work | Credit FAA / BTS. |
| DOE/ORNL ODIN outages | unstated | Shown live to responders only; not redistributed or archived until terms are confirmed. |
| ESA WorldCover 2021 | CC BY 4.0 | Attribution "© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium". |
| Census population estimates (Vintage 2024) | US Government work; public domain | Credit US Census Bureau. |
| Groma damage model training data (NAIP via Planetary Computer, NOAA ERI, CAL FIRE DINS labels) | NAIP public domain; ERI US Government work; DINS State of California, as-is | No non-commercial restriction from the data. The ImageNet initialisation of the encoder is recorded in the model card; a from-scratch variant (`--scratch`) avoids it. The trained weights (`pipeline/data/model/weights/groma-dmg-v0.*`) ship with the code under Apache-2.0. |
| CDC/ATSDR SVI 2022 | US Government work | Credit CDC/ATSDR; cache a versioned snapshot. |
| xView2 baseline classifier (CMU SEI) | BSD-3-Clause, Copyright 2019 Carnegie Mellon University (`licenses/xview2-baseline-BSD-3.txt`); distributed as ONNX in the `model-general-v1` release | Keep the BSD-3 notice. Trained on xBD (CC BY-NC-SA 4.0 data): treat its outputs as non-commercial. |
| CARTO basemaps (web) | CARTO attribution terms | Attribution shown on map. |
| MapLibre GL JS, deck.gl, React (web) | BSD-3 / MIT | Bundled; notices in the built assets. |
| onnxruntime | MIT | Runtime for the exported damage model. |
