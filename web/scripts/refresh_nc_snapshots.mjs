// Phase E — seed / refresh the committed offline snapshots the North Carolina
// risk dashboard falls back to when a feed is unavailable or CORS-blocked in the
// browser (NHC and DriveNC send no Access-Control-Allow-Origin, so the browser
// can only read these committed files).
//
//   node scripts/refresh_nc_snapshots.mjs
//
// Writes web/public/data/nc/{nwps,nws,nhc,nwis,ncdot_cameras,drivenc_closures}_snapshot.geojson
// CLOUDS (E1), FIRMS (E8) and OpenFEMA (E9) are fetched live in-app only — not snapshotted
// (CLOUDS/FIRMS need a key; FEMA + NWPS + NWS + NWIS are open + CORS-enabled).
import { writeFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "public", "data", "nc");

// NC bbox [w, s, e, n] — keep in sync with lib/nc.ts
const NC = [-84.55, 33.75, -75.4, 36.7];
const inNC = (lon, lat) => lon >= NC[0] && lon <= NC[2] && lat >= NC[1] && lat <= NC[3];

async function getJSON(url, opts = {}) {
  const r = await fetch(url, { signal: AbortSignal.timeout(20000), ...opts });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return r.json();
}

// --- E2 NWPS ------------------------------------------------------------------
const FLOOD_SEV = { major: 3, moderate: 2, minor: 1, action: 1, no_flooding: 0 };
const FLOOD_LABEL = {
  major: "Major flood",
  moderate: "Moderate flood",
  minor: "Minor flood",
  action: "Action stage",
  no_flooding: "Below flood stage",
};

function nwpsSnapshot(raw) {
  const feats = [];
  for (const g of raw.gauges ?? []) {
    if (typeof g.longitude !== "number" || typeof g.latitude !== "number") continue;
    // the bbox clips corners of GA/SC/TN/VA — keep only genuinely-NC gauges
    const isNC = g.state?.abbreviation === "NC" || /N7$/.test(g.lid ?? "");
    if (!inNC(g.longitude, g.latitude) || !isNC) continue;
    const obs = g.status?.observed;
    const fcst = g.status?.forecast;
    const oc = obs?.floodCategory ?? "";
    const fc = fcst?.floodCategory ?? "";
    const os = oc in FLOOD_SEV ? FLOOD_SEV[oc] : -1;
    const fs = fc in FLOOD_SEV ? FLOOD_SEV[fc] : -1;
    const severity = Math.max(os, fs);
    const worst = fs > os ? fc : oc;
    const stage =
      obs && obs.primary > -900 ? `${obs.primary.toFixed(1)} ${obs.primaryUnit}` : "no reading";
    const fStage =
      fcst && fcst.primary > -900 ? `${fcst.primary.toFixed(1)} ${fcst.primaryUnit}` : null;
    feats.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [g.longitude, g.latitude] },
      properties: {
        id: `nwps-${g.lid}`,
        layer: "gauge",
        title: g.name || g.lid,
        detail:
          fs > os && fs >= 1
            ? `Forecast to rise into ${FLOOD_LABEL[fc] ?? fc} (${fStage ?? "—"})`
            : fStage
              ? `Forecast ${fStage}, ${FLOOD_LABEL[fc] ?? "steady"}`
              : "Observation only — no NWM forecast at this gauge",
        severity,
        value: stage,
        category: FLOOD_LABEL[worst] ?? (severity < 0 ? "Gauge offline" : "Below flood stage"),
        url: `https://water.noaa.gov/gauges/${g.lid}`,
        time: obs?.validTime ? Date.parse(obs.validTime) : null,
      },
    });
  }
  return { type: "FeatureCollection", generated: Date.now(), features: feats };
}

// --- E5 NWS ----------------------------------------------------------------- //
const NWS_SEV = { Extreme: 3, Severe: 3, Moderate: 2, Minor: 1, Unknown: 1 };

function nwsSnapshot(raw) {
  const feats = [];
  for (const f of raw.features ?? []) {
    const p = f.properties ?? {};
    if (!f.geometry) continue;
    const event = String(p.event ?? "Alert");
    const base = NWS_SEV[String(p.severity ?? "Unknown")] ?? 1;
    const priority = /flood|red flag|fire|hurricane|tropical|tornado/i.test(event);
    feats.push({
      type: "Feature",
      geometry: f.geometry,
      properties: {
        id: `nws-${String(f.id ?? p.id ?? Math.random())}`,
        layer: "alert",
        title: event,
        detail: String(p.headline ?? p.areaDesc ?? ""),
        severity: priority ? Math.max(base, 2) : base,
        category: String(p.severity ?? "Unknown"),
        url: String(p.id ?? ""),
        time: p.effective ? Date.parse(String(p.effective)) : null,
      },
    });
  }
  return { type: "FeatureCollection", generated: Date.now(), features: feats };
}

// --- E3 NHC --------------------------------------------------------------- //
const NHC_CLASS = {
  HU: "Hurricane",
  TS: "Tropical Storm",
  TD: "Tropical Depression",
  STS: "Subtropical Storm",
  STD: "Subtropical Depression",
  PTC: "Potential Tropical Cyclone",
  RM: "Remnants",
};

function nhcSnapshot(raw) {
  const feats = [];
  for (const s of raw.activeStorms ?? []) {
    // Atlantic basin only — the ones that can reach NC. (id like "al062024")
    if (!String(s.id ?? "").toLowerCase().startsWith("al")) continue;
    const lon = Number(s.longitudeNumeric);
    const lat = Number(s.latitudeNumeric);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    const cls = NHC_CLASS[s.classification] ?? s.classification ?? "Cyclone";
    const kt = Number(s.intensity);
    const severity = kt >= 96 ? 3 : kt >= 64 ? 3 : kt >= 34 ? 2 : 1;
    feats.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [lon, lat] },
      properties: {
        id: `nhc-${s.id}`,
        layer: "storm",
        title: `${cls} ${s.name}`,
        detail: `${kt || "?"} kt · ${s.pressure || "?"} mb · moving ${s.movementDir ?? "?"}° at ${
          s.movementSpeed ?? "?"
        } kt · adv ${s.publicAdvisory?.advNum ?? "?"}`,
        severity,
        category: cls,
        value: `${kt || "?"} kt`,
        url: s.publicAdvisory?.url ?? "https://www.nhc.noaa.gov/",
        time: s.lastUpdate ? Date.parse(s.lastUpdate) : Date.now(),
      },
    });
  }
  // NOTE: the forecast cone + track line are published only as zipped
  // shapefiles (trackCone.zipFile); parsing them here needs a shapefile dep.
  // The current-position marker is the honest keyless snapshot; wiring the
  // cone polygon is a documented extension point.
  return { type: "FeatureCollection", generated: Date.now(), features: feats };
}

// --- E4 DriveNC ------------------------------------------------------------ //
async function driveNCIcons(kind) {
  // returns [{itemId, location:[lat,lon], title}]
  const d = await getJSON(`https://www.drivenc.gov/map/mapIcons/${kind}`, {
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  return Array.isArray(d.item2) ? d.item2 : [];
}

function iconsToFC(items, layer, titlePrefix) {
  const feats = [];
  for (const it of items) {
    const loc = it.location;
    if (!Array.isArray(loc) || loc.length < 2) continue;
    const [lat, lon] = loc;
    if (!Number.isFinite(lon) || !Number.isFinite(lat) || !inNC(lon, lat)) continue;
    feats.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [lon, lat] },
      properties: {
        id: `${layer}-${it.itemId}`,
        layer,
        title: it.title?.trim() || `${titlePrefix} ${it.itemId}`,
        severity: layer === "closure" ? 3 : 0,
        category: titlePrefix,
        url: `https://www.drivenc.gov/?type=${layer}&id=${it.itemId}`,
      },
    });
  }
  return { type: "FeatureCollection", generated: Date.now(), features: feats };
}

// --- E7 USGS NWIS streamflow --------------------------------------------- //
function nwisSnapshot(raw) {
  const series = raw?.value?.timeSeries ?? [];
  const bySite = new Map();
  for (const ts of series) {
    const code = ts.sourceInfo?.siteCode?.[0]?.value;
    const g = ts.sourceInfo?.geoLocation?.geogLocation;
    if (!code || !g || !inNC(g.longitude, g.latitude)) continue;
    const latest = ts.values?.[0]?.value?.slice(-1)?.[0];
    const v = latest ? Number(latest.value) : NaN;
    const rec = bySite.get(code) ?? { name: ts.sourceInfo.siteName, lon: g.longitude, lat: g.latitude };
    bySite.set(code, rec);
    const param = ts.variable?.variableCode?.[0]?.value;
    if (param === "00060" && Number.isFinite(v) && v > -1e5) rec.q = v;
    else if (param === "00065" && Number.isFinite(v) && v > -900) rec.h = v;
  }
  const feats = [];
  for (const [code, s] of bySite) {
    if (s.q == null && s.h == null) continue;
    const bits = [];
    if (s.q != null) bits.push(`${s.q.toLocaleString()} ft³/s`);
    if (s.h != null) bits.push(`stage ${s.h.toFixed(1)} ft`);
    feats.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      properties: {
        id: `nwis-${code}`,
        layer: "flow",
        title: s.name,
        detail: `USGS ${code} · ${bits.join(" · ")}`,
        severity: 0,
        value: bits[0] ?? "reporting",
        category: "Streamgage",
        url: `https://waterdata.usgs.gov/monitoring-location/${code}/`,
      },
    });
  }
  return { type: "FeatureCollection", generated: Date.now(), features: feats };
}

// --------------------------------------------------------------------------- //
await mkdir(OUT, { recursive: true });

const NWPS_URL =
  `https://api.water.noaa.gov/nwps/v1/gauges?bbox.xmin=${NC[0]}&bbox.ymin=${NC[1]}` +
  `&bbox.xmax=${NC[2]}&bbox.ymax=${NC[3]}&srid=EPSG_4326`;

const jobs = [
  ["nwps_snapshot.geojson", () => getJSON(NWPS_URL).then(nwpsSnapshot)],
  [
    "nws_snapshot.geojson",
    () =>
      getJSON("https://api.weather.gov/alerts/active?area=NC", {
        headers: {
          "User-Agent": "TerraTriage/1.0 (github.com/terratriage)",
          Accept: "application/geo+json",
        },
      }).then(nwsSnapshot),
  ],
  ["nhc_snapshot.geojson", () => getJSON("https://www.nhc.noaa.gov/CurrentStorms.json").then(nhcSnapshot)],
  [
    "nwis_snapshot.geojson",
    () =>
      getJSON(
        "https://waterservices.usgs.gov/nwis/iv/?format=json&stateCd=nc&parameterCd=00060,00065&siteType=ST&siteStatus=active",
      ).then(nwisSnapshot),
  ],
  [
    "ncdot_cameras_snapshot.geojson",
    () => driveNCIcons("Cameras").then((x) => iconsToFC(x, "camera", "Camera")),
  ],
  [
    "drivenc_closures_snapshot.geojson",
    async () => {
      const [cl, inc] = await Promise.all([
        driveNCIcons("Closures").catch(() => []),
        driveNCIcons("Incidents").catch(() => []),
      ]);
      const fc = iconsToFC(cl, "closure", "Road closure");
      const incFC = iconsToFC(inc, "closure", "Incident");
      return {
        type: "FeatureCollection",
        generated: Date.now(),
        features: [...fc.features, ...incFC.features],
      };
    },
  ],
];

for (const [name, run] of jobs) {
  try {
    const snap = await run();
    await writeFile(join(OUT, name), JSON.stringify(snap));
    console.log(`wrote nc/${name}: ${snap.features.length} features`);
  } catch (e) {
    console.error(`FAILED nc/${name}: ${e.message}`);
  }
}
