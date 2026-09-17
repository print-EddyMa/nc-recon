/**
 * Phase E. North Carolina risk backbone.
 *
 * Phase C/D gave every location a lean global hazard layer (USGS / GDACS /
 * FIRMS). This module makes North Carolina a deeply-instrumented flagship view:
 * current sensor conditions, river-flood *forecasts*, active-storm tracking,
 * official watches/warnings, and DOT ground-truth (cameras / closures).
 *
 * It is still the "risk" half of the app, what could happen or is happening,
 * as opposed to the damage-assessment pipeline (what already happened).
 *
 * Access model, mirroring `hazards.ts`:
 *   - NWPS (E2) and NWS alerts (E5) are open, keyless, CORS-enabled → fetched
 *     live, with a committed offline snapshot fallback.
 *   - NHC active storms (E3), nhc.noaa.gov sends no CORS header, so the browser
 *     reads a committed snapshot that `refresh_nc_snapshots.mjs` keeps current.
 *     The layer only appears when a storm is actually active.
 *   - DriveNC cameras + closures (E4), same CORS story; served from the
 *     committed snapshot, refreshed by the same script.
 *   - CLOUDS API (E1) needs a free user "hash"; paste it in-app (Layers → key)
 *     and ECONet/RAWS current conditions come in live.
 */
import { getSetting } from "./settings";
import { API_URL } from "./catalog";

/**
 * Fetch a keyless NC feed through the pipeline server's cached pass-through when
 * one is configured (`/feed/<name>` - keeps the console clean past NOAA's flaky
 * CORS + rate limits and adds a polite User-Agent), else hit the upstream
 * directly. Callers still fall back to the committed snapshot on any failure.
 */
async function feedFetch(
  name: string,
  directUrl: string,
  init?: RequestInit,
): Promise<Response> {
  if (API_URL) {
    try {
      // the proxy caps its own upstream at 20s (USGS NWIS can genuinely take
      // ~18s cold, then it's cached 5 min) - give it headroom past that so a
      // slow first load still lands live instead of dropping to the snapshot
      const r = await fetch(`${API_URL}/feed/${name}`, {
        signal: AbortSignal.timeout(26000),
      });
      if (r.ok) return r;
    } catch {
      /* server down or slow - fall through to the upstream */
    }
  }
  return fetch(directUrl, { signal: AbortSignal.timeout(15000), ...init });
}

// NC bounding box [w, s, e, n] and a sensible default map centre.
export const NC_BBOX: [number, number, number, number] = [
  -84.55, 33.75, -75.4, 36.7,
];
export const NC_CENTER: [number, number] = [-79.2, 35.55];

export interface NCPointProps {
  id: string;
  layer:
    | "climate"
    | "gauge"
    | "alert"
    | "storm"
    | "camera"
    | "closure"
    | "fire"
    | "flow"
    | "aircraft";
  title: string;
  detail?: string;
  /** -1 = offline/no-data, 0 = normal, 1 = watch, 2 = elevated, 3 = severe */
  severity: number;
  value?: string; // formatted headline reading
  category?: string; // flood category / alert event / storm classification
  url?: string;
  time?: number | null;
}

export type NCPointFC = GeoJSON.FeatureCollection<GeoJSON.Point, NCPointProps>;
export type NCGeomFC = GeoJSON.FeatureCollection<
  | GeoJSON.Polygon
  | GeoJSON.MultiPolygon
  | GeoJSON.LineString
  | GeoJSON.MultiLineString
  | GeoJSON.Point,
  NCPointProps
>;

export interface NCResult<T = NCPointFC> {
  data: T;
  stale: boolean; // served from the committed snapshot, not a live fetch
  disabled?: boolean;
  reason?: string;
  source: string;
  fetchedAt: number;
  /** short headline for the dashboard panel, e.g. "3 at moderate+" */
  headline?: string;
}

const BASE = import.meta.env.BASE_URL;
const emptyPts = (): NCPointFC => ({ type: "FeatureCollection", features: [] });
const emptyGeom = (): NCGeomFC => ({ type: "FeatureCollection", features: [] });

async function snapshot<T>(name: string, fallback: () => T): Promise<T> {
  try {
    const r = await fetch(`${BASE}data/nc/${name}`);
    if (r.ok) return (await r.json()) as T;
  } catch {
    /* offline, no committed snapshot */
  }
  return fallback();
}

/**
 * A small TTL cache shared by the feed loaders. The Home screen and the Live-map
 * dashboard both pull the same NOAA / USGS / FEMA feeds on mount; without this,
 * every navigation between them re-hits ~6 endpoints and re-flashes skeletons.
 * The TTL is well under the dashboard's 5-minute live-refresh interval, so a
 * genuine periodic refresh still gets fresh data.
 */
const FEED_TTL = 90_000;
const _feedCache = new Map<string, { at: number; p: Promise<unknown> }>();
function memoFeed<T>(key: string, fn: () => Promise<T>): Promise<T> {
  const hit = _feedCache.get(key);
  if (hit && Date.now() - hit.at < FEED_TTL) return hit.p as Promise<T>;
  const p = fn();
  _feedCache.set(key, { at: Date.now(), p });
  // a rejected fetch shouldn't be cached - let the next caller retry
  p.catch(() => {
    if (_feedCache.get(key)?.p === p) _feedCache.delete(key);
  });
  return p;
}

const inNC = (lon: number, lat: number) =>
  lon >= NC_BBOX[0] &&
  lon <= NC_BBOX[2] &&
  lat >= NC_BBOX[1] &&
  lat <= NC_BBOX[3];

// --------------------------------------------------------------------------- //
// E2. NOAA National Water Prediction Service: river stage + flood *forecast*
// --------------------------------------------------------------------------- //
const NWPS_URL =
  `https://api.water.noaa.gov/nwps/v1/gauges?bbox.xmin=${NC_BBOX[0]}&bbox.ymin=${NC_BBOX[1]}` +
  `&bbox.xmax=${NC_BBOX[2]}&bbox.ymax=${NC_BBOX[3]}&srid=EPSG_4326`;

const FLOOD_SEVERITY: Record<string, number> = {
  major: 3,
  moderate: 2,
  minor: 1,
  action: 1,
  no_flooding: 0,
};
const FLOOD_LABEL: Record<string, string> = {
  major: "Major flood",
  moderate: "Moderate flood",
  minor: "Minor flood",
  action: "Action stage",
  no_flooding: "Below flood stage",
};

interface NWPSStatusPart {
  primary: number;
  primaryUnit: string;
  floodCategory: string;
  validTime: string;
}
interface NWPSGauge {
  lid: string;
  name: string;
  latitude: number;
  longitude: number;
  state?: { abbreviation?: string };
  status?: { observed?: NWPSStatusPart; forecast?: NWPSStatusPart };
}

/** the bbox clips corners of GA/SC/TN/VA, keep only genuinely-NC gauges */
const isNCGauge = (g: NWPSGauge) =>
  g.state?.abbreviation === "NC" || /N7$/.test(g.lid ?? "");

function nwpsToFC(gauges: NWPSGauge[]): NCPointFC {
  const feats: NCPointFC["features"] = [];
  for (const g of gauges) {
    if (typeof g.longitude !== "number" || typeof g.latitude !== "number")
      continue;
    if (!inNC(g.longitude, g.latitude) || !isNCGauge(g)) continue;
    const obs = g.status?.observed;
    const fcst = g.status?.forecast;
    const obsCat = obs?.floodCategory ?? "";
    const fcstCat = fcst?.floodCategory ?? "";
    const obsSev = obsCat in FLOOD_SEVERITY ? FLOOD_SEVERITY[obsCat] : -1;
    const fcstSev = fcstCat in FLOOD_SEVERITY ? FLOOD_SEVERITY[fcstCat] : -1;
    const severity = Math.max(obsSev, fcstSev);
    const rising = fcstSev > obsSev && fcstSev >= 1;
    // headline category: the worse of observed / forecast
    const worstCat = fcstSev > obsSev ? fcstCat : obsCat;
    const stage =
      obs && obs.primary > -900
        ? `${obs.primary.toFixed(1)} ${obs.primaryUnit}`
        : "no reading";
    const forecastStage =
      fcst && fcst.primary > -900
        ? `${fcst.primary.toFixed(1)} ${fcst.primaryUnit}`
        : null;
    feats.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [g.longitude, g.latitude] },
      properties: {
        id: `nwps-${g.lid}`,
        layer: "gauge",
        title: g.name || g.lid,
        detail: rising
          ? `Forecast to rise into ${FLOOD_LABEL[fcstCat] ?? fcstCat} (${forecastStage ?? "-"} by ${fcst?.validTime ? fcst.validTime.slice(11, 16) + " UTC" : "next window"})`
          : forecastStage
            ? `Forecast ${forecastStage}, ${FLOOD_LABEL[fcstCat] ?? "steady"}`
            : "Observation only, no NWM forecast at this gauge",
        severity,
        value: stage,
        category:
          FLOOD_LABEL[worstCat] ??
          (severity < 0 ? "Gauge offline" : "Below flood stage"),
        url: `https://water.noaa.gov/gauges/${g.lid}`,
        time: obs?.validTime ? Date.parse(obs.validTime) : null,
      },
    });
  }
  return { type: "FeatureCollection", features: feats };
}

async function _ncFloodForecasts(): Promise<NCResult<NCPointFC>> {
  const now = Date.now();
  try {
    const r = await feedFetch("nwps", NWPS_URL);
    if (!r.ok) throw new Error(String(r.status));
    const raw = (await r.json()) as { gauges?: NWPSGauge[] };
    const data = nwpsToFC(raw.gauges ?? []);
    // NC always has ~579 NWPS gauges; an empty result means the fetch was
    // rate-limited / proxied-empty - use the committed snapshot instead
    if (!data.features.length) throw new Error("empty NWPS response");
    return {
      data,
      stale: false,
      source: "NOAA NWPS · National Water Model",
      fetchedAt: now,
      headline: headlineFor(data.features),
    };
  } catch {
    const data = await snapshot("nwps_snapshot.geojson", emptyPts);
    return {
      data,
      stale: true,
      source: "NOAA NWPS · cached snapshot",
      fetchedAt: now,
      headline: headlineFor(data.features),
    };
  }
}

// --------------------------------------------------------------------------- //
// E5. NWS official watches / warnings / advisories, filtered to NC
// --------------------------------------------------------------------------- //
const NWS_URL = "https://api.weather.gov/alerts/active?area=NC";

const NWS_SEVERITY: Record<string, number> = {
  Extreme: 3,
  Severe: 3,
  Moderate: 2,
  Minor: 1,
  Unknown: 1,
};

export const ncFloodForecasts = () => memoFeed("flood", _ncFloodForecasts);

async function _ncAlerts(): Promise<NCResult<NCGeomFC>> {
  const now = Date.now();
  try {
    const r = await feedFetch("nws", NWS_URL, {
      headers: { Accept: "application/geo+json" },
    });
    if (!r.ok) throw new Error(String(r.status));
    const raw = (await r.json()) as GeoJSON.FeatureCollection;
    const data = nwsToFC(raw);
    return {
      data,
      stale: false,
      source: "NWS · active alerts",
      fetchedAt: now,
      headline: alertHeadline(data.features),
    };
  } catch {
    const data = await snapshot("nws_snapshot.geojson", emptyGeom);
    return {
      data,
      stale: true,
      source: "NWS · cached snapshot",
      fetchedAt: now,
      headline: alertHeadline(data.features),
    };
  }
}

function nwsToFC(raw: GeoJSON.FeatureCollection): NCGeomFC {
  const feats: NCGeomFC["features"] = [];
  (raw.features ?? []).forEach((f, i) => {
    const p = (f.properties ?? {}) as Record<string, unknown>;
    const event = String(p.event ?? "Alert");
    const sev = NWS_SEVERITY[String(p.severity ?? "Unknown")] ?? 1;
    // fire-weather / flood events get bumped, they're the ones this app cares about
    const isPriority = /flood|red flag|fire|hurricane|tropical|tornado/i.test(
      event,
    );
    const geom = f.geometry as NCGeomFC["features"][number]["geometry"] | null;
    if (!geom) return; // zone-only alerts have null geometry; skip the polygon
    feats.push({
      type: "Feature",
      geometry: geom,
      properties: {
        // f.id (the alert URL) is normally present; fall back to a stable
        // index so the id never changes between renders of the same fetch
        id: `nws-${String(f.id ?? p.id ?? `idx${i}`)}`,
        layer: "alert",
        title: event,
        detail: String(p.headline ?? p.areaDesc ?? ""),
        severity: isPriority ? Math.max(sev, 2) : sev,
        category: String(p.severity ?? "Unknown"),
        url: String(p.id ?? ""),
        time: p.effective ? Date.parse(String(p.effective)) : null,
      },
    });
  });
  return { type: "FeatureCollection", features: feats };
}

// --------------------------------------------------------------------------- //
// E3. NHC active-storm tracking (cone + track). CORS-blocked in the browser,
// so this is served from the committed snapshot the refresh script maintains.
// The layer only shows up when a storm is actually active.
// --------------------------------------------------------------------------- //
export const ncAlerts = () => memoFeed("alerts", _ncAlerts);

async function _ncStormTracks(): Promise<NCResult<NCGeomFC>> {
  const now = Date.now();
  const data = await snapshot<NCGeomFC>("nhc_snapshot.geojson", emptyGeom);
  const active = data.features.length > 0;
  return {
    data,
    stale: true, // always snapshot-served
    disabled: !active,
    reason: active
      ? undefined
      : "No active Atlantic storms. NHC forecast cone, track line and watch/warning zones appear here during a storm.",
    source: active ? "NHC · committed snapshot" : "NHC · no active storms",
    fetchedAt: now,
    headline: active ? `${data.features.length} active` : undefined,
  };
}

// --------------------------------------------------------------------------- //
// E4. NCDOT DriveNC cameras + road closures. CORS-blocked; committed snapshot.
// --------------------------------------------------------------------------- //
export const ncStormTracks = () => memoFeed("storm", _ncStormTracks);

async function _ncCameras(): Promise<NCResult<NCPointFC>> {
  const now = Date.now();
  const data = await snapshot("ncdot_cameras_snapshot.geojson", emptyPts);
  return {
    data,
    stale: true,
    disabled: data.features.length === 0,
    reason:
      data.features.length === 0
        ? "Run `npm run refresh-nc` to pull the DriveNC camera set. Cameras give a literal ground-truth view next to a flood or fire risk area."
        : undefined,
    source: "NCDOT DriveNC · committed snapshot",
    fetchedAt: now,
    headline: data.features.length
      ? `${data.features.length} statewide`
      : undefined,
  };
}

export const ncCameras = () => memoFeed("cameras", _ncCameras);

async function _ncClosures(): Promise<NCResult<NCPointFC>> {
  const now = Date.now();
  const data = await snapshot("drivenc_closures_snapshot.geojson", emptyPts);
  return {
    data,
    stale: true,
    disabled: data.features.length === 0,
    reason:
      data.features.length === 0
        ? "Run `npm run refresh-nc` to pull DriveNC road closures + incidents."
        : undefined,
    source: "NCDOT DriveNC · committed snapshot",
    fetchedAt: now,
    headline: data.features.length
      ? `${data.features.length} on the network`
      : undefined,
  };
}
export const ncClosures = () => memoFeed("closures", _ncClosures);

// --------------------------------------------------------------------------- //
// E1. NC State Climate Office CLOUDS API: ECONet + RAWS current conditions.
// Needs a free user hash; without one the layer is disabled with a prompt.
// --------------------------------------------------------------------------- //
const CLOUDS_BASE = "https://api.climate.ncsu.edu/data";

interface CloudsFeatureProps {
  [k: string]: unknown;
}

/** CLOUDS `output=geojson` for one network, most recent minute observation. */
async function cloudsNetwork(
  hash: string,
  net: "ECONET" | "RAWS",
  vars: string,
): Promise<GeoJSON.Feature<GeoJSON.Point, CloudsFeatureProps>[]> {
  const qs = new URLSearchParams({
    hash,
    loc: `state=NC;type=${net}`,
    var: vars,
    start: "-90 minutes",
    end: "now",
    obtype: "H,O",
    output: "geojson",
  });
  const r = await fetch(`${CLOUDS_BASE}?${qs}`, {
    signal: AbortSignal.timeout(15000),
  });
  if (!r.ok) throw new Error(`${net} ${r.status}`);
  const fc = (await r.json()) as GeoJSON.FeatureCollection<
    GeoJSON.Point,
    CloudsFeatureProps
  >;
  if (fc?.type !== "FeatureCollection") throw new Error(`${net}: not GeoJSON`);
  return fc.features.filter((f) => f.geometry?.type === "Point");
}

function numField(p: CloudsFeatureProps, ...names: string[]): number | null {
  for (const n of names) {
    const v = p[n];
    if (typeof v === "number" && Number.isFinite(v)) return v;
    if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v)))
      return Number(v);
  }
  return null;
}
function strField(p: CloudsFeatureProps, ...names: string[]): string | null {
  for (const n of names) {
    const v = p[n];
    if (typeof v === "string" && v.trim() !== "") return v;
  }
  return null;
}

async function _ncClimate(): Promise<NCResult<NCPointFC>> {
  const now = Date.now();
  const hash = getSetting("cloudsKey");
  if (!hash) {
    return {
      data: emptyPts(),
      stale: false,
      disabled: true,
      reason:
        "Add a free NC State Climate Office CLOUDS API key (Layers → key icon) to stream ECONet + RAWS current conditions, temperature, wind, rainfall, and RAWS fuel readings for the mountain fire-weather stations.",
      source: "CLOUDS API · not configured",
      fetchedAt: now,
    };
  }
  try {
    // allSettled so a RAWS failure doesn't throw away good ECONet data
    const settled = await Promise.allSettled([
      cloudsNetwork(hash, "ECONET", "temp2m,rh2m,windspeed10m,precip1m").catch(
        () => cloudsNetwork(hash, "ECONET", "temp2m,precip1m"),
      ),
      cloudsNetwork(
        hash,
        "RAWS",
        "temp2m,windspeed10m,fuelmoisture,precip1m",
      ).catch(() => cloudsNetwork(hash, "RAWS", "temp2m,precip1m")),
    ]);
    const val = (i: number) =>
      settled[i].status === "fulfilled"
        ? (
            settled[i] as PromiseFulfilledResult<
              GeoJSON.Feature<GeoJSON.Point, CloudsFeatureProps>[]
            >
          ).value
        : [];
    const econet = val(0);
    const raws = val(1);
    if (settled.every((s) => s.status === "rejected")) {
      const why = (settled[0] as PromiseRejectedResult).reason;
      throw new Error(String(why));
    }
    const feats: NCPointFC["features"] = [];
    for (const [net, list] of [
      ["ECONet", econet],
      ["RAWS", raws],
    ] as const) {
      for (const f of list) {
        const [lon, lat] = f.geometry.coordinates;
        if (!Number.isFinite(lon) || !Number.isFinite(lat) || !inNC(lon, lat))
          continue;
        const p = f.properties ?? {};
        const name =
          strField(p, "name", "location_name", "location", "station", "loc") ??
          "Station";
        const temp = numField(
          p,
          "temp2m",
          "temperature",
          "airtemp1m",
          "airtemp",
        );
        const wind = numField(
          p,
          "windspeed10m",
          "windspeed2m",
          "windspeed",
          "wind",
        );
        const rain = numField(p, "precip1m", "precip", "rain");
        const fuel = numField(p, "fuelmoisture", "fuel_moisture", "fm10");
        const bits: string[] = [];
        if (temp != null) bits.push(`${temp.toFixed(0)}°F`);
        if (wind != null) bits.push(`wind ${wind.toFixed(0)} mph`);
        if (rain != null && rain > 0) bits.push(`rain ${rain.toFixed(2)}"`);
        if (fuel != null) bits.push(`fuel ${fuel.toFixed(0)}%`);
        // fire-weather flag: RAWS with low fuel moisture + wind
        const fireRisk =
          fuel != null && fuel <= 8 && (wind == null || wind >= 10);
        feats.push({
          type: "Feature",
          geometry: { type: "Point", coordinates: [lon, lat] },
          properties: {
            id: `clouds-${net}-${name}`.replace(/\s+/g, "_"),
            layer: "climate",
            title: `${name}`,
            detail: `${net}${bits.length ? " · " + bits.join(" · ") : " · reporting"}`,
            severity: fireRisk ? 2 : 0,
            value: bits[0] ?? "reporting",
            category:
              net === "RAWS" ? "Fire-weather station" : "Research station",
          },
        });
      }
    }
    return {
      data: { type: "FeatureCollection", features: feats },
      stale: false,
      source: `CLOUDS API · ${feats.length} stations`,
      fetchedAt: now,
      headline: `${feats.length} reporting`,
    };
  } catch (e) {
    return {
      data: emptyPts(),
      stale: false,
      disabled: true,
      reason: `CLOUDS request failed (${String(e).slice(0, 80)}). Check the key at api.climate.ncsu.edu.`,
      source: "CLOUDS API · error",
      fetchedAt: now,
    };
  }
}

// keyed by the CLOUDS hash so pasting a new key re-fetches instead of serving
// the cached "not configured" result; keyless callers share one cache entry
export const ncClimate = () =>
  memoFeed(`climate:${getSetting("cloudsKey") ?? ""}`, _ncClimate);

// --------------------------------------------------------------------------- //
// E7. USGS streamflow (NWIS instantaneous values), NC statewide.
// Open, keyless, CORS-enabled. Discharge (00060) + gage height (00065).
// --------------------------------------------------------------------------- //
const NWIS_URL =
  "https://waterservices.usgs.gov/nwis/iv/?format=json&stateCd=nc" +
  "&parameterCd=00060,00065&siteType=ST&siteStatus=active";

interface NWISValue {
  value: { value: string; dateTime: string }[];
}
interface NWISTimeSeries {
  sourceInfo: {
    siteName: string;
    siteCode: { value: string }[];
    geoLocation: { geogLocation: { latitude: number; longitude: number } };
  };
  variable: { variableCode: { value: string }[]; unit: { unitCode: string } };
  values: NWISValue[];
}

async function _ncStreamflow(): Promise<NCResult<NCPointFC>> {
  const now = Date.now();
  try {
    const r = await feedFetch("nwis", NWIS_URL);
    if (!r.ok) throw new Error(String(r.status));
    const raw = (await r.json()) as {
      value?: { timeSeries?: NWISTimeSeries[] };
    };
    const series = raw.value?.timeSeries ?? [];
    if (!series.length) throw new Error("empty NWIS response"); // → committed snapshot
    // fold the per-parameter series into one point per site
    const bySite = new Map<
      string,
      {
        name: string;
        lon: number;
        lat: number;
        q?: number;
        qUnit?: string;
        h?: number;
        hUnit?: string;
        t?: number;
      }
    >();
    for (const ts of series) {
      const code = ts.sourceInfo.siteCode[0]?.value;
      if (!code) continue;
      const g = ts.sourceInfo.geoLocation?.geogLocation;
      if (!g || !inNC(g.longitude, g.latitude)) continue;
      const vals = ts.values?.[0]?.value ?? [];
      const latest = vals[vals.length - 1];
      const v = latest ? Number(latest.value) : NaN;
      const rec =
        bySite.get(code) ??
        bySite
          .set(code, {
            name: ts.sourceInfo.siteName,
            lon: g.longitude,
            lat: g.latitude,
          })
          .get(code)!;
      if (latest) rec.t = Math.max(rec.t ?? 0, Date.parse(latest.dateTime));
      const param = ts.variable.variableCode[0]?.value;
      if (param === "00060" && Number.isFinite(v) && v > -1e5) {
        rec.q = v;
        rec.qUnit = ts.variable.unit.unitCode;
      } else if (param === "00065" && Number.isFinite(v) && v > -900) {
        rec.h = v;
        rec.hUnit = ts.variable.unit.unitCode;
      }
    }
    const feats: NCPointFC["features"] = [];
    for (const [code, s] of bySite) {
      if (s.q == null && s.h == null) continue;
      const bits: string[] = [];
      if (s.q != null)
        bits.push(`${s.q.toLocaleString()} ${s.qUnit ?? "ft³/s"}`);
      if (s.h != null) bits.push(`stage ${s.h.toFixed(1)} ${s.hUnit ?? "ft"}`);
      feats.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [s.lon, s.lat] },
        properties: {
          id: `nwis-${code}`,
          layer: "flow",
          title: s.name,
          detail: `USGS ${code} · ${bits.join(" · ")}`,
          severity: 0, // informational; NWPS carries the flood-category signal
          value: bits[0] ?? "reporting",
          category: "Streamgage",
          url: `https://waterdata.usgs.gov/monitoring-location/${code}/`,
          time: s.t ?? null,
        },
      });
    }
    return {
      data: { type: "FeatureCollection", features: feats },
      stale: false,
      source: `USGS NWIS · ${feats.length} gages`,
      fetchedAt: now,
      headline: `${feats.length} gages reporting`,
    };
  } catch {
    const data = await snapshot("nwis_snapshot.geojson", emptyPts);
    return {
      data,
      stale: true,
      source: "USGS NWIS · cached snapshot",
      fetchedAt: now,
      headline: data.features.length
        ? `${data.features.length} gages (cached)`
        : undefined,
    };
  }
}

export const ncStreamflow = () => memoFeed("streamflow", _ncStreamflow);

// --------------------------------------------------------------------------- //
// E8. NASA FIRMS active-fire hotspots, clipped to NC. Needs a free map key
// (same key as the global layer; paste under Layers → key, or VITE_FIRMS_KEY).
// --------------------------------------------------------------------------- //
async function _ncFires(): Promise<NCResult<NCPointFC>> {
  const now = Date.now();
  const key = getSetting("firmsKey") || import.meta.env.VITE_FIRMS_KEY;
  if (!key) {
    return {
      data: emptyPts(),
      stale: false,
      disabled: true,
      reason:
        "Add a free NASA FIRMS map key (key icon below) for near-real-time active-fire detections over North Carolina, the mountains and the sandhills both carry real wildfire risk.",
      source: "NASA FIRMS · not configured",
      fetchedAt: now,
    };
  }
  const [w, s, e, n] = NC_BBOX;
  const url = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${key}/VIIRS_SNPP_NRT/${w},${s},${e},${n}/1`;
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(12000) });
    if (!r.ok) throw new Error(String(r.status));
    const text = (await r.text()).trim();
    const lines = text.split("\n").filter(Boolean);
    const head = lines.shift();
    if (!head) throw new Error("empty FIRMS response");
    const cols = head.split(",");
    const li = cols.indexOf("latitude");
    const lo = cols.indexOf("longitude");
    const fr = cols.indexOf("frp");
    const dt = cols.indexOf("acq_date");
    const feats: NCPointFC["features"] = [];
    for (const line of lines) {
      const c = line.split(",");
      const lon = Number(c[lo]);
      const lat = Number(c[li]);
      if (!Number.isFinite(lon) || !Number.isFinite(lat) || !inNC(lon, lat))
        continue;
      const frp = Number(c[fr]) || 0;
      feats.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [lon, lat] },
        properties: {
          id: `firms-${lat.toFixed(4)}-${lon.toFixed(4)}-${c[dt] ?? ""}`,
          layer: "fire",
          title: `Active fire · FRP ${frp.toFixed(0)} MW`,
          detail: `VIIRS 375 m detection, ${c[dt] ?? "past 24 h"}`,
          severity: frp >= 50 ? 3 : frp >= 15 ? 2 : 1,
          value: `${frp.toFixed(0)} MW`,
          category: "VIIRS hotspot",
        },
      });
    }
    return {
      data: { type: "FeatureCollection", features: feats },
      stale: false,
      disabled: feats.length === 0,
      reason:
        feats.length === 0
          ? "No active-fire detections in NC in the past 24 h."
          : undefined,
      source: `NASA FIRMS · ${feats.length} detections`,
      fetchedAt: now,
      headline: feats.length ? `${feats.length} in past 24 h` : undefined,
    };
  } catch (err) {
    return {
      data: emptyPts(),
      stale: false,
      disabled: true,
      reason: `FIRMS request failed (${String(err).slice(0, 60)}). Check the key.`,
      source: "NASA FIRMS · error",
      fetchedAt: now,
    };
  }
}

// keyed by the FIRMS key so pasting one re-fetches; shared entry when keyless
export const ncFires = () =>
  memoFeed(
    `fires:${getSetting("firmsKey") || import.meta.env.VITE_FIRMS_KEY || ""}`,
    _ncFires,
  );

// --------------------------------------------------------------------------- //
// E9. OpenFEMA federally-declared disasters in NC. Open, keyless, CORS-enabled.
// This is the "history" layer: what has actually happened to North Carolina.
// --------------------------------------------------------------------------- //
export interface FemaDeclaration {
  disasterNumber: number;
  declarationTitle: string;
  incidentType: string;
  declarationDate: string;
  fyDeclared: number;
  incidentBeginDate: string | null;
  /** DR = major disaster, EM = emergency, FM = fire management */
  declarationType?: string;
}

export interface NCHistory {
  total: number;
  sinceYear: number;
  byType: { type: string; count: number }[];
  recent: FemaDeclaration[];
  /** every deduped NC declaration, newest first - feeds the history timeline */
  all: FemaDeclaration[];
  stale: boolean;
  source: string;
  fetchedAt: number;
}

// one row per (disaster, county, program). NC has ~8k rows lifetime, so pull a
// wide page and dedupe by disasterNumber client-side. $top max is 10000.
const FEMA_SINCE_YEAR = 1990;
const FEMA_URL =
  "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries" +
  `?$filter=state%20eq%20%27NC%27%20and%20fyDeclared%20ge%20${FEMA_SINCE_YEAR}` +
  "&$orderby=declarationDate%20desc&$select=disasterNumber,declarationTitle," +
  "incidentType,declarationDate,fyDeclared,incidentBeginDate,declarationType&$top=10000";

const titleCase = (s: string) =>
  s.toLowerCase().replace(/\b([a-z])/g, (_, c: string) => c.toUpperCase());

/** dedupe raw rows (one per disaster/county/program) to one per disasterNumber */
function dedupeFema(rows: FemaDeclaration[]): FemaDeclaration[] {
  const seen = new Set<number>();
  const uniq: FemaDeclaration[] = [];
  for (const d of rows) {
    if (seen.has(d.disasterNumber)) continue;
    seen.add(d.disasterNumber);
    uniq.push({ ...d, declarationTitle: titleCase(d.declarationTitle || "") });
  }
  return uniq;
}

function femaFromRows(
  rows: FemaDeclaration[],
  stale: boolean,
  source: string,
): NCHistory {
  const uniq = dedupeFema(rows);
  const counts = new Map<string, number>();
  for (const d of uniq)
    counts.set(d.incidentType, (counts.get(d.incidentType) ?? 0) + 1);
  return {
    total: uniq.length,
    sinceYear: FEMA_SINCE_YEAR,
    byType: [...counts.entries()]
      .map(([type, count]) => ({ type, count }))
      .sort((a, b) => b.count - a.count),
    recent: uniq.slice(0, 6),
    all: uniq,
    stale,
    source,
    fetchedAt: Date.now(),
  };
}

async function _ncFemaHistory(): Promise<NCHistory> {
  try {
    const r = await fetch(FEMA_URL, { signal: AbortSignal.timeout(15000) });
    if (!r.ok) throw new Error(String(r.status));
    const raw = (await r.json()) as {
      DisasterDeclarationsSummaries?: FemaDeclaration[];
    };
    return femaFromRows(
      raw.DisasterDeclarationsSummaries ?? [],
      false,
      "OpenFEMA · Disaster Declarations",
    );
  } catch {
    // committed offline copy, same shape as the API rows
    const rows = await snapshot<FemaDeclaration[]>(
      "fema_history_snapshot.json",
      () => [],
    );
    if (rows.length)
      return femaFromRows(rows, true, "OpenFEMA · cached snapshot");
    return {
      total: 0,
      sinceYear: FEMA_SINCE_YEAR,
      byType: [],
      recent: [],
      all: [],
      stale: true,
      source: "OpenFEMA · unavailable",
      fetchedAt: Date.now(),
    };
  }
}
export const ncFemaHistory = () => memoFeed("fema", _ncFemaHistory);

// --------------------------------------------------------------------------- //
// E10. Live aircraft over NC (ADS-B). Keyless; a single 250nm point query
// centred on the state, via adsb.lol through the server's cached pass-through,
// covers NC edge to edge. Situational awareness during a disaster: Guard
// rotary-wing, medevac and post-storm aerial survey flights show up here same
// as any other traffic. Same source used by github.com/bilawalsidhu/gods-eye-view,
// credited in About.
// --------------------------------------------------------------------------- //
const AIRCRAFT_URL = "https://api.adsb.lol/v2/point/35.55/-79.2/250";

interface AdsbAircraft {
  hex: string;
  flight?: string;
  r?: string;
  t?: string;
  alt_baro?: number | "ground";
  gs?: number;
  lat?: number;
  lon?: number;
  dbFlags?: number;
}

async function _ncAircraft(): Promise<NCResult<NCPointFC>> {
  const now = Date.now();
  try {
    const r = await feedFetch("aircraft", AIRCRAFT_URL);
    if (!r.ok) throw new Error(String(r.status));
    const raw = (await r.json()) as { ac?: AdsbAircraft[] };
    const feats: NCPointFC["features"] = [];
    for (const a of raw.ac ?? []) {
      if (
        typeof a.lat !== "number" ||
        typeof a.lon !== "number" ||
        !inNC(a.lon, a.lat)
      )
        continue;
      const military = ((a.dbFlags ?? 0) & 1) === 1;
      const alt =
        typeof a.alt_baro === "number"
          ? `${a.alt_baro.toLocaleString()} ft`
          : "on ground";
      const speed = typeof a.gs === "number" ? `${a.gs.toFixed(0)} kt` : null;
      const title = (a.flight ?? a.r ?? a.hex).trim() || a.hex;
      feats.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [a.lon, a.lat] },
        properties: {
          id: `adsb-${a.hex}`,
          layer: "aircraft",
          title,
          detail: [military ? "Military" : a.t, alt, speed]
            .filter(Boolean)
            .join(" · "),
          severity: 0,
          value: alt,
          category: military ? "Military" : (a.t ?? "Aircraft"),
        },
      });
    }
    return {
      data: { type: "FeatureCollection", features: feats },
      stale: false,
      disabled: feats.length === 0,
      reason:
        feats.length === 0
          ? "No aircraft currently broadcasting position over North Carolina."
          : undefined,
      source: `ADS-B · adsb.lol · ${feats.length} tracked`,
      fetchedAt: now,
      headline: feats.length ? `${feats.length} in flight` : undefined,
    };
  } catch (err) {
    return {
      data: emptyPts(),
      stale: false,
      disabled: true,
      reason: `Live feed unavailable right now (${String(err).slice(0, 60)}).`,
      source: "ADS-B · unavailable",
      fetchedAt: now,
    };
  }
}

export const ncAircraft = () => memoFeed("aircraft", _ncAircraft);

// --------------------------------------------------------------------------- //
// helpers
// --------------------------------------------------------------------------- //
function headlineFor(feats: NCPointFC["features"]): string {
  const elevated = feats.filter((f) => f.properties.severity >= 2).length;
  const watch = feats.filter((f) => f.properties.severity === 1).length;
  if (elevated) return `${elevated} at moderate+ flood`;
  if (watch) return `${watch} at action/minor`;
  const live = feats.filter((f) => f.properties.severity >= 0).length;
  return `${live} gauges below flood stage`;
}

function alertHeadline(feats: NCGeomFC["features"]): string {
  if (!feats.length) return "No active NC alerts";
  const top = feats.filter((f) => f.properties.severity >= 3).length;
  return top
    ? `${feats.length} active · ${top} severe`
    : `${feats.length} active`;
}

/** severity → palette (shared with the dashboard legend) */
export const NC_SEV_COLOR: Record<number, [number, number, number]> = {
  [-1]: [90, 102, 115], // offline
  0: [90, 124, 134], // normal (meter)
  1: [245, 215, 110], // watch (dmg0)
  2: [232, 137, 74], // elevated (dmg1)
  3: [209, 73, 91], // severe (dmg2)
};
export const NC_SEV_LABEL = [
  "offline",
  "normal",
  "watch",
  "elevated",
  "severe",
];
