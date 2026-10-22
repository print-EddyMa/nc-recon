# Groma response products

What responders do with a damage assessment. Built for any assessed area, any
hazard, from open data; every number is a planning estimate with its source
and assumptions attached. Confirm on the ground before acting.

```
python -m terratriage.ops.response --area <area>          # all products, ~1 min
GET  /ops/areas/<area>/response              summary + every product (JSON)
GET  /ops/areas/<area>/response/layers       map layers (GeoJSON)
GET  /ops/areas/<area>/response/plan.kml     sectors, landing-zone candidates, cut-off
                                             clusters, flagged facilities (Google Earth,
                                             ATAK/WinTAK, ArcGIS)
POST /ops/areas/<area>/response              rebuild in the background
```

All routes are responder-only. Outputs: `data/output/ops/<area>.response.json`
and `<area>.response.layers.json`.

## Who uses what

| Product | Question it answers | First users |
|---|---|---|
| Lifelines | Which of FEMA's eight Community Lifelines look disrupted, and which facilities to call first | EOC planning section, situation unit |
| Access | Which roads are blocked, who is cut off, how far to a hospital | EOC, National Guard, US&R, EMS |
| Landing zones | Where a helicopter could land near people cut off by road | National Guard aviation, state air ops |
| Sectors | Which 1 km USNG squares to search and assign first | US&R, Guard task forces, damage assessment teams |
| Water | Which drinking water systems serve the damage; which homes are on private wells | Health department, state drinking water program |
| Needs | Water, meals, shelter space and distribution points for the people displaced or cut off | Logistics section, mass care |
| Money | Expected building losses, debris volume, the county's Public Assistance threshold | Recovery, finance, PDA teams, insurers |

## Lifelines

Facilities come from official layers where they exist and OpenStreetMap
otherwise. An OpenStreetMap record within 150 m of an official one of the same
kind is dropped.
- **Hospitals:** FEMA Hospitals, with beds, trauma level and helipad.
- **Dams:** the USACE National Inventory of Dams, with hazard potential and
  condition.
- **Hazardous materials and wastewater:** EPA facility points (Superfund, Toxics
  Release Inventory, NPDES dischargers).
- **Heliports:** FAA facilities.
- **Everything else from OpenStreetMap:** fire, EMS, police, schools, shelters,
  grocery, fuel, substations, towers, water works.

HIFLD Open shut down in August 2025, so none of its layers are used.

Each facility is checked against the assessment and the hazard data:
- **disrupted:** severe damage within 60 m, inside a mapped landslide, or cut off
  by known road blocks;
- **at risk:** inside a fire perimeter, damage likely nearby, cut off if debris
  blocks roads, or a high-hazard dam in a flood event;
- **no evidence:** nothing in the open data says it is affected;
- **not assessed:** outside the assessed buildings and no hazard data covers it.

Lifeline colours are FEMA's, estimated:
- **red:** a critical facility is disrupted.
- **yellow:** any facility is disrupted or at risk.
- **green:** facilities were found and none is flagged.
- **grey:** unknown. Grey is never shown as green.

Transportation is rated from the road analysis. Water systems are rated from
the water product.

## Access

The road network comes from OpenStreetMap. Each segment is marked:
- **blocked:** a mapped landslide of this storm crosses it (NCGS inventory for
  Helene), or there is a reported closure;
- **debris:** it runs beside a building called Destroyed;
- **bridge:** it is a bridge in a flood event, unverified until inspected.

Three scenarios:
- known blocks;
- plus debris;
- plus every bridge, the worst case, which is a planning bound and not a finding.

A building is cut off when its road cannot reach the edge of a box padded 6 km
around the area. Travel time to the nearest hospital uses typical speeds per
road class. A hospital beyond the box is reached at a straight line ×1.4 at
50 km/h from the exit.

## Landing-zone candidates

The analysis runs on a 10 m grid built from three inputs:
- **Slope:** from USGS 3DEP elevation.
- **Ground cover:** from ESA WorldCover 2021, where grass, cropland and bare
  ground are open and shrubland and built-up are marginal.
- **Building clearance:** assessed footprints, kept 20 m clear.

A candidate is the centre of a circle of usable ground at least 50 m across
for a UH-60 (80 m for a CH-47), at no more than 7° of slope. Those figures are
from the Army air assault handbook, citing FM 3-21.38. Candidates are ranked by
closeness to people cut off and to likely Major or Destroyed buildings.

These are candidates for reconnaissance, never approved landing zones. Wires,
poles, tree edges, soft ground and debris do not show in 10 m data. The
aviation unit's own standard governs.

## Sectors and needs

Sectors are 1 km US National Grid squares, FEMA's standard grid for land
operations (Directive 092-5). Each carries:
- buildings likely Major or Destroyed;
- people in them at night (USACE NSI);
- people cut off by road;
- the share still sent to review.

Squares are ranked by people in likely Major or Destroyed buildings.

Needs use FEMA's generic planning factors for a 72-96 hour requirement:
- 3 litres of water and 2 meals per person per day;
- 40 square feet of shelter per person (20 for an evacuation shelter);
- distribution points of Type I (about 20,000 people a day), II (10,000) and
  III (5,000).

## Water

The water product uses EPA community water system service areas, some of
which are modelled rather than mapped; each record carries its verification
status. It reports:
- **Systems:** for each one serving assessed buildings, how much damage lies
  inside it, whether its water or wastewater facilities are flagged, and
  whether the event floods.
- **Private wells:** residential buildings inside no community system's service
  area are reported as likely on private wells. After a flood, wells and septic
  systems need testing before use. More than 300,000 people near Helene's
  flooded areas used private wells.

Only the system and the state drinking water program can issue or lift a
boil-water notice.

## Money

- **Building losses:** USACE NSI structure plus contents value multiplied by
  each damage level's share. The shares follow CAL FIRE's inspection
  definitions: Affected 1-10%, Minor 10-25%, Major 25-50%, Destroyed over 50%
  (taken as 50-100%). The result is reported as a low-high range. Buildings
  without an NSI value are counted, not guessed.
- **Debris:** FEMA 329 (Debris Estimating Field Guide). A destroyed home is
  length × width × stories × 0.20 × a vegetation multiplier of 1.1-1.5, in cubic
  yards. A manufactured home is 290 or 415 CY. In a flood event a home at Major
  adds 25-30 CY put to the curb. FEMA gives no coefficient for other levels, so
  none is invented.
- **Public Assistance threshold:** the countywide per-capita indicator for the
  fiscal year the incident began, times Census 2024 county population. FY2025
  is $4.72 and FY2026 is $4.86 (statewide $1.89 and $1.94). The threshold counts
  public costs, so it is context for the debris line, not a comparison with
  private losses.

## Power

Power uses DOE/ORNL ODIN county outages. That feed is live only, so it is used
only while an event is current (21 days). About 50 utilities report to it, so a
county with no row is not necessarily powered.

## Sources

| Source | Endpoint | Licence |
|---|---|---|
| OpenStreetMap (Overpass) | overpass-api.de | ODbL 1.0 |
| FEMA Hospitals (RAPT) | services.arcgis.com/XG15cJAlne2vxtgt/.../Hospitals_RAPT/FeatureServer/6 | US Government |
| USACE National Inventory of Dams | geospatial.sec.usace.army.mil/dls/rest/services/NID/... | US Government |
| EPA EMEF facility points | geopub.epa.gov/arcgis/rest/services/EMEF/efpoints/MapServer | public domain |
| EPA water system boundaries | services.arcgis.com/cJ9YHowT8TU7DUyn/.../Water_System_Boundaries/FeatureServer/0 | public domain |
| FAA aviation facilities (NTAD) | services.arcgis.com/xOi1kZaI0eWDREZv/.../NTAD_Aviation_Facilities/FeatureServer/0 | US Government |
| DOE/ORNL ODIN outages | ornl.opendatasoft.com/.../odin-real-time-outages-county | no licence text |
| USGS 3DEP elevation | elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer | public domain |
| ESA WorldCover 2021 | esa-worldcover.s3.eu-central-1.amazonaws.com | CC BY 4.0 |
| Census county population (Vintage 2024) | www2.census.gov/programs-surveys/popest/... | public domain |
| NCGS landslide inventory (Helene) | services2.arcgis.com/kCu40SDxsCGcuUWO/.../NC_Landslide_Inventory | NC DEQ public service |
| FEMA PA per-capita indicator | fema.gov/assistance/public/applicants/per-capita-impact-indicator | |
