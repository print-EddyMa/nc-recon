# Bias audit (ops mode)

For each bias: direction, how measured, mitigation, residual risk. "Not yet
measured" means exactly that: stratified metrics need labels
(`docs/ops/LABELING_PROTOCOL.md`).

| Bias | Direction | Measured? | Mitigation | Residual risk |
|---|---|---|---|---|
| **Footprint completeness (OSM)** | Undercounts structures, especially rural and manufactured homes | **Yes**: Old Fort box OSM 760 vs USA Structures 1,395 vs NSI ≈1,900 points | USA Structures primary + OSM gap-fill; NSI points without any footprint are emitted as **"not assessed"** features and counted (513 at Old Fort) | Footprints digitised 2014–2019; post-2019 homes missing |
| USA Structures excludes < 450 ft² | Misses small homes / cabins | Partly (NSI unmatched count) | OSM gap-fill; unmatched NSI points reported | Tiny dwellings without NSI rows are invisible |
| Canopy over roofs (dense in WNC) | Damage hidden, leaning "no damage" | Per building: `canopy_frac`, reason code | E1/E2 weight ×0.4 above 40% canopy | Heuristic RGB excess-green, no NIR/lidar CHM yet |
| Post imagery timing | Maxar/ERI 1–2 weeks after: floodwater gone, interior damage invisible; spring 2025: debris cleared, repairs done | Recorded (`POST_IMAGE_<n>D_AFTER_INCIDENT`) | E5 carries flood evidence where a WSE exists | No WSE on current AOIs, so flood-only damage is under-detected |
| Off-nadir / sun / season mismatch | False change | Yes, per pair | E2 down-weighted (Old Fort ×0.60) | Relief displacement varies across the scene |
| Model domain (xBD ≠ Appalachia; post-only CNN) | Unknown | **Not yet** | Label-only mode, review routing | Could be systematically biased by roof type |
| Truth bias (future labels) | Field teams / labelers see accessible, visible damage | Kappa reported | Protocol, can't-tell option, double labeling | — |
| FEMA registrations (area-level comparison, planned) | Undercount renters, older adults, low-connectivity households | Not yet | Planned: compare per ZIP/ZCTA, report residuals, not totals | — |
| Seasonal / second homes | Overcounts displaced people | **Yes, flagged**: ACS adjustment unavailable without a Census key | Output labelled "UNADJUSTED ... upper bound" | Until a key is set |
| Population disaggregation (NSI modelled) | Error in hollows | Range reported (NSI vs USA Structures CI) | Ranges, not points | — |
| English-only UI | Excludes Spanish speakers | — | Not done | Open item |
| Tribal data sovereignty (EBCI, DR-4827 designated area) | Building-level display on tribal land without consent | — | **No EBCI AOI is registered**; do not add one without the tribe's agreement | Policy enforced by process, not code |
