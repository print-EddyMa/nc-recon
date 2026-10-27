# NC Recon: plan for real NC emergency offices (outline, 2026-10-07)

This is the outline and the load-bearing findings for the full plan; the plan
itself is still to be written (the drafting workflow in this folder was prepared
but not run). Every figure below comes from the research record in this folder
or from the code; nothing is validated by NCEM yet.

## 1. Where the tool stands

See `current-state-2026-10-07.md`. One container, no database, no paid services,
150+ offline tests. No accuracy number exists because no analyst labels exist.

## 2. How NC emergency management works, and where the tool fits

* Counties own emergency management and the initial damage assessment
  (G.S. 166A-19.15); NCEM's three branches and 15 Area Coordinators are the
  liaison; WebEOC (NC SPARTA) is the system of record; everything geospatial is
  Esri (state ELA, Survey123 damage surveys, ArcGIS Online).
* NCEM's Helene after-action review found no common operating picture, WebEOC
  overloaded, days without ground truth from counties, and recommends a unified
  database with NCDIT as partner. NC Recon should feed that picture (exports and
  an API into WebEOC/ArcGIS), not be another silo.
* FEMA's July 2025 PDA Guide accepts AI/ML-derived SLTT damage data, virtual
  sensing and SLTT drone imagery, and defines the damage levels by waterline
  against outlets and ceiling. Exports must carry the IDA fields (address or GPS,
  degree of damage, peril, home type, owner/renter, insurance) as Excel or
  geodatabase.
* Likely owners: NCEM Risk Management (footprints, first-floor elevations, FIMAN,
  FRIS), Operations/Information and Planning (SEOC picture), Hazard Mitigation
  (HMGP 5 percent initiative), Office of Partnership Engagement (universities).

## 3. Pre-disaster readiness

* Standing per-structure baseline: NCEM Composite Building Footprints (5.4 M
  rooflines from the 2020-2023 orthos, BLDG_ID) and NC_Risk_Building_Footprints
  (first-floor elevation, foundation, flood zone, replacement value), NC OneMap
  parcels and AddressNC, FEMA NRI and NFHL/FRIS zones, HHS emPOWER counts, CMS and
  DHSR facility lists, mobile home parks.
* Pre-event imagery: NC OneMap 4-band analysis orthos by region (next mountain
  flights 2026), NOAA ERI pre-event folders, Sentinel-2 composites.
* Triggers that pre-arm areas: NHC cone and wind probabilities, WPC excessive
  rainfall outlook, NWPS forecast crests, FIMAN gauge conditions, SERT activation.
* Offline packs per county on laptops and USB (PMTiles basemap and imagery,
  footprints, parcels); exercises and NCEM/FEMA damage-assessment training.

## 4. During the event

* Conditions map (now with FIMAN, Duke outages, shelters) plus MRMS rainfall,
  NWS flash-flood polygons, NWC inundation services, FCC DIRS county telecom
  status, NCDOT structure inspections and TIMS; an event recorder that archives
  feed snapshots and FIMAN peak stages so crests with datums exist afterwards.
* Imagery arrival: NOAA ERI the same day it is flown, CAP obliques within hours
  (public S3), Maxar/Vantor open data when activated, Sentinel-1 flood extent
  (OPERA DSWx-S1) when optical is clouded; activation checklist for USGS/Charter
  and NASA Disasters requests through NCEM GIS.
* Drone imagery: ingest from SD cards (sneakernet is the norm), OpenDroneMap in
  the compose stack, registration to NC OneMap orthos and lidar, FAA SGI and
  NC drone statutes recorded with each mission, coverage layer to stop duplicate
  flights.

## 5. Post-event assessment and recovery

* Evidence to add: flood depth from published crests (built), NWS FIM depth
  grids at 17 NC gauges, lidar difference from the 2025 Collaboratory lidar
  against 2017 Phase 5, landslide inventories (USGS CC0, NCGS), OPERA
  DIST-ALERT, blue-tarp persistence; per-event few-shot recalibration from
  reviewer labels (the pattern every operational system uses).
* Validation: Buncombe's public SARCOP waypoints (12,891 with FEMA categories
  including negatives) and ATC-45 surveys, NWS DAT points for wind, OpenFEMA IHP
  registrations at block-group level, NCEM's statewide SAR database under an MOU.
  Realistic expectations from the literature: binary damaged precision 0.8 to
  0.9, five-level macro F1 0.55 to 0.65, middle classes weakest.
* Recovery: GROW NC quarterly metrics, Renew NC, HMGP acquisitions, parcel
  revaluations (2027), permits where published, hand-off to NC 211, DCM and
  county LTRGs.

## 6. UI design

One view per audience (analyst, director, PIO, wall), FEMA lifeline colours and
"as of" operational periods, ICS 209 block-30 table in the brief, USNG grid and
search, colour-blind-safe ramp with shapes, WCAG 2.1 AA by April 2027, Spanish,
offline-first field capture compatible with Survey123 IA schema, explicit
"Inaccessible" state.

## 7. Security, privacy and legal

Per-user SSO (NCID SAML or Entra OIDC) with MFA and four roles replacing the
shared token; audit records kept two years in UTC; data classified Confidential
for structure-level records and Public for suppressed tract summaries;
k-of-10 suppression; signed images, SBOM with hashes, security.txt and a
disclosure policy; restic backups with a tested restore (RTO 4 h, RPO 1 h);
CISA Cyber Hygiene scanning; NC public records design (an export profile that is
safe to release); licence handling for Maxar CC BY-NC and OSM ODbL.

## 8. Deployment, procurement and funding

Self-hosted in NCDIT or a county (avoids the GovRAMP gate that a SaaS would face
from April 2027); VRAR and NIST 800-53 Moderate control statement; EMPG
sustainment (damage-assessment software is allowable), HMGP 5 percent initiative,
NC Collaboratory university evaluation; county services need no bidding under
state law but follow 2 CFR 200.320 when grant-funded; keep pilots under the
$100,000 state IT delegation.

## 9. Roadmap (to be detailed with exit criteria)

1. Validation first: SARCOP/ATC-45 comparison on Swannanoa and Buncombe, analyst
   labels on TUNE areas, first accuracy report.
2. Identity and roles, audit retention, backups, signed releases.
3. Baseline and triggers (footprints with FFE, parcels, NRI, pre-arming).
4. Event recorder and the extra live layers; drone ingest with OpenDroneMap.
5. Flood depth from FIM libraries and lidar difference; landslide channel.
6. Exports for WebEOC, ArcGIS Damage Assessment and FEMA IDA; ICS 209 brief.
7. Offline packs, field capture, Spanish, accessibility conformance report.
8. Pilot with one county and NCEM Risk Management; HMGP/EMPG funding path.

## Open questions for NCEM

Terms for FIMAN, NCEM AGOL layers and inundation libraries; statewide SAR
damage database access; NCID onboarding for a locally hosted tool; whether
county EM offices qualify for EAGLE-I; the FACT successor for IDA submissions.
