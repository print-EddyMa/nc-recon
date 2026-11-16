export const meta = {
  name: 'ncrecon-deploy-research',
  description: 'Deep web sweep of open data, live feeds, drone/3D sources and NC EM practice for NC Recon, with verification and a completeness critic',
  phases: [
    { title: 'Sweep', detail: '12 research agents, one per dimension, web search + fetch' },
    { title: 'Verify', detail: 'skeptic re-checks every high-priority source: real, accessible, licensed as claimed' },
    { title: 'Critic', detail: 'what is missing across the whole sweep' },
  ],
}

const TODAY = args?.today || '2026-10-06'

const CONTEXT = `
You are researching for NC Recon, an open-source disaster damage decision-support tool for North Carolina emergency management (NCEM and county EM offices). Today is ${TODAY}.

What NC Recon does now (Python 3.13 FastAPI + React, one Docker container, no paid services):
- After an event, an analyst points it at a town. It pulls before/after imagery (NC OneMap 2020-2023 orthos, NC OneMap Helene 2025 orthos, NOAA NGS Emergency Response Imagery, Maxar Open Data), finds every structure (FEMA USA Structures, OpenStreetMap, USACE National Structure Inventory), aligns outlines to roofs, and gives each structure a FEMA damage level (No damage / Affected / Minor / Major / Destroyed) with a probability from fused evidence: an xView2 CNN on ONNX Runtime, pixel change, blue-tarp detection, flood depth (no water-surface source yet). Uncertain and severe calls go to a human review queue; analysts label ground truth; nothing is validated yet.
- It estimates people displaced (NSI occupancy x damage probabilities) and ranks census tracts by need (CDC SVI). Exports GeoJSON, CSV with USNG, KML, GeoPackage, FileGDB, a Survey123 field sheet, a one-page brief, a public tract summary with small counts suppressed.
- A Conditions map shows live USGS gauges (OGC API), NOAA NWPS flood forecasts, NWS alerts, NHC storms, NCDOT DriveNC closures and cameras.
- Already evaluated and documented: OpenFEMA declarations and Housing Assistance data, FEMA historical geospatial damage DB (no Helene rows), USGS STN high-water marks, USGS peaks, Census ACS (needs key), NC DEQ Helene flood extents (no license), Google Earth Engine and NASA Earthdata (unconfigured).
- Not built yet: road isolation, nighttime-lights outage, lidar DEM of difference, shadow/height, wind, field-report ingest, coverage-gap analysis, offline PWA packs, QGIS project, Spanish UI, satellite collection planner.
- Security today: fail-closed bearer token for responder routes, audit log, HTTPS via Caddy, no SSO.

Goal of the whole research effort: a thorough plan to make NC Recon ready for real NC emergency offices across pre-disaster, during and post-disaster use: data sources, live tracking and monitoring, drone imagery, 3D/lidar, functionality, UI design, security, deployment and procurement.

Rules for your research:
- Use WebSearch and WebFetch (load them with ToolSearch "select:WebSearch,WebFetch" if they are deferred). Fetch the primary page for anything you report; do not report from memory alone. Prefer official sources (agency pages, API docs, dataset landing pages, GitHub repos).
- Be concrete: exact product names, URLs, access method (REST API, ArcGIS FeatureServer/ImageServer, STAC, S3 bucket, download portal, email request), auth or key requirements, licence (US Gov public domain, CC BY, ODbL, proprietary, unstated), update cadence, formats, North Carolina coverage specifically, and cost.
- Flag anything that is paid, requires an MOU/account, or has unclear licensing. Flag dead or decommissioned services.
- Say which disaster phase each item serves (pre, during, post) and how exactly NC Recon would use it (an evidence channel, a map layer, a trigger, a ground-truth source, a distribution channel).
- Mark priority for NC Recon (high = should be in the deployment plan, medium = worth it later, low = note only) and your confidence (high = fetched primary docs that confirm every field, medium = partly confirmed, low = secondary sources only).
- Record evidence URLs for every source. Record gaps: things you looked for and could not find.
- Do not invent datasets, endpoints or figures. If a detail is unknown, say unknown.
Your final output is data for a planning step, not prose for a person.`

const SOURCE_SCHEMA = {
  type: 'object',
  properties: {
    dimension: { type: 'string' },
    sources: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          operator: { type: 'string' },
          url: { type: 'string' },
          what: { type: 'string', description: 'what the data or service is, in one or two sentences' },
          access: { type: 'string', description: 'REST API / ArcGIS service / STAC / S3 / portal download / request-only / commercial' },
          auth: { type: 'string', description: 'none, free key, account, MOU, paid' },
          license: { type: 'string' },
          nc_coverage: { type: 'string', description: 'North Carolina coverage specifically, with dates where known' },
          cadence: { type: 'string', description: 'update frequency or latency, e.g. real time, hourly, per event, static' },
          formats: { type: 'string' },
          phases: { type: 'array', items: { type: 'string', enum: ['pre', 'during', 'post'] } },
          use_in_ncrecon: { type: 'string', description: 'exactly how NC Recon would use it' },
          priority: { type: 'string', enum: ['high', 'medium', 'low'] },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
          evidence_urls: { type: 'array', items: { type: 'string' } },
          caveats: { type: 'string' },
        },
        required: ['name', 'operator', 'url', 'what', 'access', 'auth', 'license', 'nc_coverage', 'phases', 'use_in_ncrecon', 'priority', 'confidence', 'evidence_urls'],
      },
    },
    insights: { type: 'array', items: { type: 'string' }, description: 'facts that are not a dataset: processes, standards, who uses what, numbers with their source URL in the text' },
    gaps: { type: 'array', items: { type: 'string' }, description: 'what you looked for and could not find or confirm' },
  },
  required: ['dimension', 'sources', 'insights', 'gaps'],
}

const DIMENSIONS = [
  { key: 'satellite', prompt: `Dimension: satellite imagery and emergency activation programs that an NC agency can use at no cost.
Cover at least: Maxar Open Data Program (current status, how events are activated, STAC, licence CC BY-NC 4.0 implications for government use); Planet (disaster data program, NICFI, education and research program, any public-sector no-cost paths); Umbra, Capella and ICEYE open SAR data programs; Copernicus Sentinel-1 and Sentinel-2 (Copernicus Data Space Ecosystem, STAC, revisit over NC, cloud-free odds in a hurricane week); Copernicus Emergency Management Service rapid mapping (can a US state request it?); the International Charter Space and Major Disasters (US activation path via USGS); USGS Hazards Data Distribution System (HDDS) and EROS event support; NASA Disasters program and NASA ARIA damage proxy maps (was one made for Helene?); NASA HLS and Landsat; OPERA products (DSWx flood extent, DIST-ALERT) and their latency; Microsoft Planetary Computer, AWS Open Data and Google Earth Engine as access layers; commercial tasking options and typical prices only as context. For Hurricane Helene specifically, document what satellite data existed over western North Carolina and when.` },
  { key: 'aerial-drone', prompt: `Dimension: aerial and drone imagery, and the drone operations ecosystem in North Carolina.
Cover at least: NOAA NGS Emergency Response Imagery (how fast after an event, tile index, formats); Civil Air Patrol imagery and where FEMA/CAP photos are published (FEMA GeoPlatform, CAP imagery portals); NC OneMap post-event orthoimagery programs and the Helene 2025 collection; NCDOT's UAS program and NC Emergency Management drone operations (teams, aircraft, how imagery is shared, any public products from Helene); county and municipal drone teams in western NC; NC State Highway Patrol or NC National Guard aerial collections; OpenAerialMap (what Helene drone data exists there); OpenDroneMap / WebODM and NodeODM for turning drone photos into orthomosaics, DSMs and 3D models (licence, hardware needs); FAA Part 107, emergency Special Governmental Interest (SGI) waivers and TFRs during disasters and how they affected Helene drone flights; DRONERESPONDERS and the AIRT; data formats and metadata standards for drone products (COG, EXIF, GeoTIFF, LAS); privacy constraints on drone imagery in NC. Also find how drone orthomosaics could be registered to the NC OneMap basemap for before/after comparison.` },
  { key: 'lidar-3d', prompt: `Dimension: 3D, lidar, elevation, buildings and flood models for building-level damage work in North Carolina.
Cover at least: NC statewide QL2 lidar (NC Emergency Management Spatial Data Download, years, formats, DEM/DSM availability, any post-Helene 2024-2025 lidar collections and who flew them); USGS 3DEP (coverage over NC, 1 m DEMs, point clouds in Entwine/EPT on AWS); NC Floodplain Mapping Program and the Flood Risk Information System (FRIS): what building-level flood data it has (first-floor elevations, flood depth grids, structure inventories, risk assessment per building); FEMA National Flood Hazard Layer; NC's building footprint datasets (NC OneMap statewide buildings, with heights?); Microsoft, Google Open Buildings and Overture Maps building footprints (coverage/quality in rural WNC, licences); 3D: Cesium 3D Tiles, Google Photorealistic 3D Tiles (licence for government, cost), OSM Buildings, open 3D city models in NC, drone-derived point clouds and Gaussian splats; DEM of Difference / lidar change detection methods for debris flows and washed-out structures; landslide inventories from Helene (NC Geological Survey, USGS) and debris-flow susceptibility; NOAA SLOSH and the NWS/NOAA National Water Model, HEC-RAS 2D models that exist for WNC rivers; FIMAN flood inundation libraries (pre-computed inundation per gauge stage). State for each what NC Recon could do with it (flood depth evidence E5, lidar difference E6, height/shadow E3, exposure modelling before an event).` },
  { key: 'live-hazards', prompt: `Dimension: live hazard monitoring feeds for North Carolina (rivers, rain, wind, landslides, dams, fire) with their APIs.
Cover at least: FIMAN, North Carolina's Flood Inundation Mapping and Alert Network (how many gauges, whether there is an API or data export, what the inundation libraries contain, who operates it); USGS Water Data OGC API and USGS WaterAlert; NOAA NWPS API (official and known limits); NWS API alerts and the Flash Flood Warning polygons; NOAA MRMS and QPE radar rainfall products and how to fetch them programmatically (grib2, AWS buckets); NWS WPC excessive rainfall outlooks; NHC products and GIS feeds (cone, wind swath, surge); NC State Climate Office ECONet/CRONOS stations and their API terms; NC dam safety data (NC DEQ dam inventory, National Inventory of Dams API, emergency action plans) and dam failure alerts during Helene; landslide monitoring and alerts (NC Geological Survey, USGS landslide hazards, any real-time rainfall-threshold system in WNC); wildfire (NC Forest Service, NIFC open data, NASA FIRMS); tornado and wind: NWS Damage Assessment Toolkit (DAT) data access and what structure-level damage points it publishes; NOAA storm events database; earthquake (USGS) only briefly. For each, give endpoint URLs, auth, rate limits, formats and latency. Note which of these NC Recon already uses (USGS OGC API, NWPS, NWS alerts, NHC) and what is new.` },
  { key: 'infrastructure', prompt: `Dimension: infrastructure and lifeline status feeds for North Carolina during a disaster.
Cover at least: electric outages (Duke Energy outage map and any undocumented JSON endpoints, the NC electric cooperatives, PowerOutage.us API and pricing, EIA-417 and EAGLE-I from DOE/ORNL and whether states can get it, NASA Black Marble nighttime lights for outage proxy); telecom (FCC Disaster Information Reporting System public reports, cell site outage percentages by county); roads and bridges (NCDOT DriveNC/TIMS API that NC Recon already uses, NCDOT bridge inventory, NCDOT GIS open data, Waze for Cities / Waze data partnership, HERE/TomTom only as context); water and wastewater systems (NC DEQ, EPA SDWIS, boil-water notices); fuel availability (GasBuddy tracker, EIA); hospitals and health (HHS emPOWER, NC DHHS, hospital bed status, dialysis); shelters (American Red Cross National Shelter System open data or FEMA/NSS feeds, NC DHHS shelter lists, ReadyNC); 911 and PSAP outages; airports and NOTAMs; rail; schools closures; mail. For each: endpoint, auth, license, latency, NC coverage, and what NC Recon would do with it (road-isolation evidence E8, nighttime-lights outage proxy, lifeline overlays on the Conditions map, need index terms).` },
  { key: 'impact-truth', prompt: `Dimension: human-impact data and structure-level ground truth that could validate or calibrate automated damage assessment in North Carolina.
Cover at least: all OpenFEMA datasets relevant to a damage tool (Individual Assistance housing registrants and valid registrations by ZIP/county, IHP, Public Assistance funded projects, NFIP claims and policies, Preliminary Damage Assessment data, Disaster Declarations, FEMA Mission Assignments, and whether any FEMA dataset has structure- or address-level damage for Helene DR-4827-NC); FEMA GeoPlatform damage assessment layers; USACE Operation Blue Roof data; NWS DAT damage points; NC Emergency Management's own damage assessment process for Helene (did counties use Survey123 / ArcGIS damage assessment, is any county-level or parcel-level damage data public, e.g. Buncombe, Henderson, McDowell, Yancey county GIS open data); NC Office of Recovery and Resiliency / Division of Community Revitalization and GROW NC data; NC OSBM Helene damage and needs assessment reports with the dollar and structure counts they cite; county property tax reassessments after Helene (parcel-level damage adjustments published by county tax offices); building permit open data for rebuild tracking; Crisis Cleanup (open source, what data could be shared); 211 and Red Cross casework; Humanitarian OpenStreetMap Team Helene mapping; academic Helene damage datasets (NC State, UNC, App State, USGS landslide inventory); insurance (NC Department of Insurance claims statistics); hospital, school and nursing-home impacts. For each: what exactly the unit of record is (household, parcel, structure, ZIP), whether it can serve as a label, its lag, access, licence.` },
  { key: 'nc-em-practice', prompt: `Dimension: how North Carolina emergency management actually operates and buys software, so a tool can fit in.
Cover at least: NC Emergency Management organisation (branches, the State EOC, activation levels, the county EM director role, regional coordinators), the information systems NCEM and counties use (WebEOC, the NC SPARTA system, Everbridge or other alerting, ArcGIS Online and the state Esri enterprise agreement, NC OneMap, the NC Geographic Information Coordinating Council, NC CGIA, ReadyNC), NCEM's damage assessment doctrine and forms, the FEMA Preliminary Damage Assessment process and the FEMA Damage Assessment Operations Manual (current edition, damage categories, what evidence is accepted, remote/virtual PDA guidance after Helene), FEMA's own geospatial tools used in PDA; Helene after-action findings about damage assessment, situational awareness and data sharing (NCEM, FEMA, GAO, NC General Assembly reports); funding paths for a tool like this (EMPG, HMGP 5% initiative, BRIC status, FEMA Regional partners, NC General Assembly Helene appropriations, NC Collaboratory, university partnerships); state IT governance for a web tool (NC DIT, the Statewide Information Security Manual, NCID / NC Identity Management for SSO, hosting options like NC DIT cloud, AWS GovCloud, Azure Government, StateRAMP or FedRAMP expectations, procurement thresholds and the NC eProcurement rules); legal: NC Public Records law and exemptions for sensitive security information, the NC Identity Theft Protection Act, Section 508 / WCAG 2.1 AA obligations, records retention schedules; EMAC and mutual aid implications for sharing data with other states. Give the names of the specific offices or programmes that would own a tool like this and any published contacts or RFP patterns.` },
  { key: 'security', prompt: `Dimension: security, privacy and resilience requirements for a self-hosted web tool that holds building-level damage data and addresses for responders in North Carolina.
Cover at least: threat model for emergency-management software (CISA guidance for state and local government, CISA KEV, Cyber Essentials, the DHS/CISA emergency services sector guidance); identity: SSO options that NC agencies actually have (NCID, Microsoft Entra ID, Okta), OpenID Connect integration patterns, MFA requirements under the NC Statewide Information Security Manual, role-based access (public, analyst, responder, administrator), break-glass access during outages; data classification of structure-level damage with addresses (is it PII, is it sensitive security information, what the NC public records exemptions say), small-count suppression and k-anonymity norms in public outputs; audit logging and retention; encryption at rest and in transit, key management for a single-container deployment; supply chain: SBOM (CycloneDX/SPDX), pip and npm audit, pinned ONNX model hashes, container image signing (cosign), distroless images; container hardening (read-only filesystem, non-root, seccomp), rate limiting, DDoS exposure of a public endpoint, Caddy/nginx hardening, security headers; secrets management; backups and disaster recovery for the tool itself (RPO/RTO expectations in an EOC), offline and degraded operation (Starlink, air-gapped laptop kits, PWA caches); vulnerability disclosure and patch cadence; compliance frameworks that NC or FEMA might ask for (StateRAMP, FedRAMP Moderate, NIST 800-53 moderate baseline, NIST CSF 2.0, SOC 2) and what a small open-source tool can realistically attest to; accessibility (Section 508, WCAG 2.1 AA) as a procurement requirement; licensing of the tool itself and of its inputs (CC BY-NC Maxar for government, ODbL share-alike for OSM-derived outputs). For each: the controlling document, the concrete requirement, and what NC Recon should implement.` },
  { key: 'ui-ux', prompt: `Dimension: UI and UX for emergency operations centres and field damage assessment, and what comparable tools look like.
Cover at least: common operating picture design (big-screen EOC dashboards, ArcGIS Dashboards conventions, FEMA GeoPlatform, NIMS/ICS roles and what each needs to see: EM director, planning section, GIS unit, field assessment teams, PIO, logistics), situation report standards (ICS 209, FEMA sitrep, NCEM sitreps), FEMA and NCEM map symbology and the US National Grid, colour and accessibility (colour-blind safe damage ramps, WCAG contrast, dark rooms, 24-hour shifts, cognitive load findings), field data apps that assessors use (ArcGIS Survey123, Field Maps, QuickCapture, Crisis Cleanup, FEMA's own IA inspection apps) and offline-first patterns (PWA, map tile packs, sync conflict handling), shift handover and "as of" time display, printing and PDF briefs, Spanish and other language needs in WNC, low-bandwidth design (Starlink, satellite phones), mobile vs desktop vs wall display. Comparable products to learn from, with what they do well and badly: Esri Damage Assessment solution, Esri Emergency Management solutions, Crisis Cleanup, Palantir and Planet for FEMA, Microsoft AI for Good building damage assessment, Google/WFP SKAI, Tomorrow.io, Ladris, Perimeter, Pano AI, DisasterAWARE (PDC), Juvare WebEOC dashboards, Genasys, Hazard Hub, 'NC Hazards' apps. Note public demos, screenshots or docs you fetched. Also find published usability research or after-action lessons on damage-assessment UI (FEMA, NASEM, academic HCI).` },
  { key: 'ml-sota', prompt: `Dimension: state of the art in automated building damage assessment and what NC Recon should adopt, with evidence.
Cover at least: xView2 / xBD lineage (baseline and winning models, reported F1s, licences of weights), Microsoft AI for Good building damage assessment and its Turkey/Maui/Helene uses, Google/WFP SKAI (open source, how it is used by WFP and FEMA), NASA/IBM Prithvi and other geospatial foundation models (Clay, SatlasPretrain, DOFA, Copernicus FM) and whether damage fine-tunes exist, Segment Anything for footprints, SAR damage proxy maps (NASA ARIA, Sentinel-1 coherence) with Helene examples, OPERA DIST-ALERT and DSWx for vegetation disturbance and water, blue tarp detection literature, flood depth estimation per structure from HWMs/gauges and DEMs (USGS, FEMA Hazus methods), lidar change detection for debris flows, drone-imagery damage models, uncertainty calibration and abstention practices in disaster ML (conformal prediction, human-in-the-loop), FEMA's position on remote damage assessment and what evidence counts for a PDA, published accuracy expectations for aerial vs satellite assessment, GPU vs CPU inference costs, the Helene-specific datasets and papers (any labeled Helene imagery, NASA/Microsoft/Planet Helene case studies, USGS landslide inventory). For each: repo or paper URL, licence, input requirements, reported performance, and a concrete recommendation for NC Recon (adopt, evaluate, skip) with reasoning.` },
  { key: 'pre-disaster', prompt: `Dimension: pre-disaster readiness data and functionality: what a tool should hold before the storm so it is useful the hour after.
Cover at least: hazard and exposure baselines (FEMA National Risk Index, Hazus inventories, FEMA NFHL flood zones, NC FRIS building-level flood risk, NC OneMap statewide parcels and NC address points and their licences, NC911 Board data, HIFLD open critical infrastructure (hospitals, schools, nursing homes, shelters, fire stations, water plants, cell towers, substations), CMS nursing home and dialysis data, HHS emPOWER medical-equipment dependents, mobile home park locations, LandScan and Meta population layers, NC DMV or Census vehicle data only as context); vulnerability and equity data (CDC SVI already, CEJST, NC DHHS data); pre-event imagery baselines (NC OneMap orthos cadence and the next statewide flights, NAIP, Sentinel-2 cloud-free composites, HLS) and the idea of a standing per-structure baseline; collection planning (predicted satellite passes, Maxar tasking lead times, NOAA ERI typical timing, CAP), pre-positioning data on laptops, exercise and training programmes (NCEM exercises, FEMA IS courses on damage assessment), hazard mitigation plan data (county HMPs, HMGP project data), building code and NC Building Code enforcement data, historical events for calibration (Matthew 2016, Florence 2018, Fred 2021, Helene 2024: what imagery and damage data exists for each), forecast-driven triggers (NHC cone, WPC rainfall, NWPS forecasts) that should pre-arm an assessment. For each: access, licence, cadence, NC coverage and how NC Recon would use it before an event.` },
  { key: 'post-recovery', prompt: `Dimension: post-disaster recovery data and long-term tracking (weeks to years), beyond the first damage call.
Cover at least: FEMA Individual Assistance and Public Assistance data flows (OpenFEMA IHP registrations, large-loss, PA projects), NFIP claims, SBA disaster loans data, USACE Operation Blue Roof and debris mission data (NC Helene debris volumes, ADMS data), NCDOT debris and road rebuild tracking, temporary housing (FEMA Direct Housing, NC's programmes), NC Division of Community Revitalisation / NCORR data and Helene recovery dashboards (OSBM, GROW NC, NC General Assembly reports with structure counts), county building permit open data for rebuild tracking (Buncombe, Henderson, Haywood, McDowell, Watauga and others), parcel reassessment data, imagery time series for recovery monitoring (Planet NICFI status, Sentinel-2, HLS, NC OneMap next flights, Google Earth historical imagery licence), blue tarp persistence as a recovery indicator (literature), displacement tracking (Census PEP, school enrollment changes, USPS change-of-address counts, mobile location data vendors as context only), economic recovery data (BLS, NC Commerce, sales tax), public health (NC DHHS), long-term landslide and river channel change (USGS, NCGS), lessons from Helene recovery reporting (what metrics agencies actually report), and how a damage tool should hand off to recovery case management (Crisis Cleanup, NC 211, VOADs). For each: access, licence, lag, unit of record and what NC Recon should do with it (recovery dashboard, re-assessment schedules, hand-off exports).` },
]

phase('Sweep')
const sweep = await parallel(DIMENSIONS.map(d => () =>
  agent(`${CONTEXT}\n\n${d.prompt}\n\nBe exhaustive within this dimension: aim for 15 to 30 sources where they exist, each with fetched evidence. Return the structured result.`,
    { label: `sweep:${d.key}`, phase: 'Sweep', schema: SOURCE_SCHEMA })
    .then(r => r && ({ ...r, key: d.key }))))
const dims = sweep.filter(Boolean)
log(`Sweep done: ${dims.length}/${DIMENSIONS.length} dimensions, ${dims.reduce((n, d) => n + d.sources.length, 0)} sources`)

phase('Verify')
const VERDICT = {
  type: 'object',
  properties: {
    name: { type: 'string' },
    exists: { type: 'boolean', description: 'the source is real and the url (or a corrected one) resolves' },
    access_confirmed: { type: 'boolean' },
    license_confirmed: { type: 'boolean' },
    nc_coverage_confirmed: { type: 'boolean' },
    corrections: { type: 'object', additionalProperties: { type: 'string' }, description: 'field name -> corrected value, for any field that was wrong' },
    live_check: { type: 'string', description: 'what you fetched and what it returned, e.g. endpoint + status + sample fields' },
    verdict: { type: 'string', enum: ['confirmed', 'corrected', 'doubtful', 'refuted'] },
    notes: { type: 'string' },
  },
  required: ['name', 'exists', 'access_confirmed', 'license_confirmed', 'nc_coverage_confirmed', 'corrections', 'live_check', 'verdict'],
}
// Verification budget: every high-priority source would be ~200 agents at
// half an hour each. Check the ones the plan will act on and that the team has
// not already verified live: skip sources already in NC Recon's register,
// doctrine and standards documents (low risk of being wrong), and cap per
// dimension, preferring lower-confidence claims.
const KNOWN = /usgs water data|nwps|national water prediction|api\.weather\.gov|nws api|openfema disaster|housing assistance program|usace nsi|national structure inventory|usa structures|openstreetmap|overpass|maxar|vantor|nc onemap orthoimagery|orthoimagery_|noaa ngs|emergency response imagery|cdc\/atsdr|social vulnerability index|census acs|fiman|duke energy|open shelters|peak_stage|drivenc|tims statewide/i
const DOCTRINE = /guide|doctrine|ics 209|nims|wcag|statute|g\.s\. |policy|standard|rfc 9116|nist sp|cpg|colorbrewer|okabe|public records|after action|damage and needs assessment|records schedule|ada title ii/i
const rank = s => (s.confidence === 'low' ? 0 : s.confidence === 'medium' ? 1 : 2)
const high = dims.flatMap(d => d.sources
  .filter(s => s.priority === 'high' && !KNOWN.test(s.name + ' ' + s.url) && !DOCTRINE.test(s.name))
  .sort((a, b) => rank(a) - rank(b))
  .slice(0, 5)
  .map(s => ({ ...s, key: d.key })))
const skipped = dims.reduce((n, d) => n + d.sources.filter(s => s.priority === 'high').length, 0) - high.length
log(`Verifying ${high.length} high-priority sources (${skipped} high-priority sources skipped: already verified by the team, doctrine documents, or beyond 5 per dimension; medium and low priority are not re-checked)`)
const verified = await parallel(high.map((s, i) => () =>
  agent(`You are a skeptical verifier with a small budget: at most 8 tool calls, then decide. Today is ${TODAY}. A researcher reported this source for use by a North Carolina emergency-management damage tool:\n${JSON.stringify(s, null, 2)}\n\nTry to REFUTE it. Use WebFetch (load it with ToolSearch "select:WebFetch" if deferred; WebSearch only if the url is dead) to fetch the url and at most two evidence urls. Check: does the service exist today and is it still operating; is the access method and auth as stated (hit an endpoint or API doc); is the licence stated as claimed; does it cover North Carolina as claimed; is the cadence real. Put corrected values in corrections. If you cannot confirm a field from a primary page, set its confirmed flag false and say so in notes; do not assume. Default to 'doubtful' when uncertain. Return the structured verdict.`,
    { label: `verify:${s.key}:${i}`, phase: 'Verify', schema: VERDICT })
    .then(v => v && ({ ...v, key: s.key, original: s }))))
const verdicts = verified.filter(Boolean)
log(`Verify done: ${verdicts.filter(v => v.verdict === 'confirmed').length} confirmed, ${verdicts.filter(v => v.verdict === 'corrected').length} corrected, ${verdicts.filter(v => v.verdict === 'doubtful').length} doubtful, ${verdicts.filter(v => v.verdict === 'refuted').length} refuted`)

phase('Critic')
const CRITIC = {
  type: 'object',
  properties: {
    missing_sources: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, why: { type: 'string' }, url: { type: 'string' } }, required: ['name', 'why'] } },
    missing_topics: { type: 'array', items: { type: 'string' } },
    weak_claims: { type: 'array', items: { type: 'string' }, description: 'claims in the sweep that look wrong, outdated or unsupported, with the dimension key' },
    contradictions: { type: 'array', items: { type: 'string' } },
    plan_risks: { type: 'array', items: { type: 'string' }, description: 'things a deployment plan for NC emergency offices must address that the research does not yet cover' },
  },
  required: ['missing_sources', 'missing_topics', 'weak_claims', 'contradictions', 'plan_risks'],
}
const summaryForCritic = dims.map(d => ({ key: d.key, sources: d.sources.map(s => `${s.name} (${s.operator}) [${s.priority}/${s.confidence}] ${s.access}; ${s.license}; NC: ${s.nc_coverage}`), insights: d.insights, gaps: d.gaps }))
const critic = await agent(`${CONTEXT}\n\nYou are the completeness critic for a 12-dimension research sweep. Here is what it found (condensed):\n${JSON.stringify(summaryForCritic, null, 1)}\n\nAnd the verification verdicts for high-priority sources:\n${JSON.stringify(verdicts.map(v => ({ name: v.name, key: v.key, verdict: v.verdict, notes: v.notes, corrections: v.corrections })), null, 1)}\n\nAsk: what is missing for a plan to deploy this tool to real NC emergency offices for pre, during and post disaster use? Which important sources, programmes, standards or constraints did no dimension cover? Which claims look wrong or stale (use WebSearch/WebFetch to spot-check up to ten of them)? Which findings contradict each other? What must the plan address that the research does not inform? Be specific and name URLs where you fetched them.`,
  { label: 'critic', phase: 'Critic', schema: CRITIC })

return { today: TODAY, dims, verdicts, critic }
