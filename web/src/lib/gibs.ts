/**
 * NASA GIBS imagery for the Conditions map (ported from Canary's
 * canary/sources/gibs.py and its satellite loop).
 *
 * GIBS (Global Imagery Browse Services) serves keyless WMTS tiles of NASA and
 * partner satellite products. Every identifier, tile matrix set, format, time
 * step and legend below was read from the EPSG:3857 "best" capabilities
 * document (WMTSCapabilities.xml, fetched 2026-11-16), not guessed.
 *
 * Dates are UTC throughout. The newest available time comes from GIBS's small
 * DescribeDomains XML (not the 5.8 MB capabilities file); each layer's
 * `rule` says how the shown date is chosen.
 *
 * Tiles and domain requests both go to gibs.earthdata.nasa.gov, which the
 * server's CSP lists in connect-src (pipeline/src/terratriage/ops/guard.py).
 * Offline mode must not call anything here.
 */

export const GIBS_ROOT = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best";
const GIBS_LINK =
  '<a href="https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api" target="_blank" rel="noreferrer">NASA GIBS</a>';

export type GibsKey = "goes" | "viirs" | "imerg" | "smap" | "dswx_hls" | "dswx_s1" | "rtc_s1";

/** ISO 8601 time step as GIBS states it */
export type GibsStep = "PT10M" | "PT30M" | "P1D";

export interface GibsLayer {
  key: GibsKey;
  /** GIBS layer identifier */
  id: string;
  /** the product name, as the GIBS capabilities title gives it */
  product: string;
  /** short label for the layer list */
  label: string;
  /** map attribution line: NASA GIBS / the mission */
  credit: string;
  /** plain-words credit for the layer list */
  source: string;
  matrixSet: string;
  maxzoom: number;
  /** drawn only from this zoom in: GIBS's state-zoom tiles of some products are striped */
  minzoom?: number;
  ext: "png" | "jpeg";
  step: GibsStep;
  /** how the date shown is chosen, in plain words */
  rule: string;
  /** earliest date in the capabilities (daily layers; feeds the date picker) */
  since?: string;
  opacity: number;
  /** imagery that covers the basemap sits lowest; data overlays above it */
  kind: "imagery" | "overlay";
  legend?: string;
}

export const GIBS_LAYERS: GibsLayer[] = [
  {
    key: "goes",
    id: "GOES-East_ABI_GeoColor",
    product: "Geo Color (ABI, GOES-East)",
    label: "GOES-East GeoColor",
    credit: `${GIBS_LINK} / NOAA GOES-East ABI`,
    source: "NASA GIBS / NOAA GOES-East",
    matrixSet: "GoogleMapsCompatible_Level7",
    maxzoom: 7,
    ext: "png",
    // Date rule: 10-minute images. The loop takes the images GIBS lists over
    // the 3 hours before its newest one, 20 minutes apart, built from the
    // domain's own time ranges (GIBS has gaps; a computed time could 404).
    step: "PT10M",
    rule: "images 20 minutes apart over the 3 hours before the newest one",
    opacity: 0.95,
    kind: "imagery",
  },
  {
    key: "viirs",
    id: "VIIRS_NOAA20_CorrectedReflectance_TrueColor",
    product: "Corrected Reflectance (True Color, VIIRS, NOAA-20)",
    label: "VIIRS true colour, NOAA-20",
    credit: `${GIBS_LINK} / NOAA-20 VIIRS (NASA LANCE)`,
    source: "NASA GIBS / NOAA-20 VIIRS",
    matrixSet: "GoogleMapsCompatible_Level9",
    maxzoom: 9,
    ext: "jpeg",
    // Date rule: one image per UTC day. NOAA-20 passes over North Carolina in
    // the early afternoon local time and the near-real-time tiles follow a few
    // hours later, so today's date (UTC) is only used from 21:00 UTC; before
    // that the newest complete day is yesterday.
    step: "P1D",
    rule: "newest UTC day with an afternoon pass over North Carolina",
    since: "2018-01-05",
    opacity: 1,
    kind: "imagery",
  },
  {
    key: "imerg",
    id: "IMERG_Precipitation_Rate_30min",
    product: "Precipitation Rate, 30-minute avg. (IMERG)",
    label: "IMERG precipitation rate",
    credit: `${GIBS_LINK} / NASA GPM IMERG`,
    source: "NASA GIBS / GPM IMERG",
    matrixSet: "GoogleMapsCompatible_Level6",
    maxzoom: 6,
    ext: "png",
    // Date rule: the newest half hour GIBS lists. IMERG Early runs hours
    // behind real time, so the label always carries its time.
    step: "PT30M",
    rule: "newest half hour GIBS lists; runs hours behind",
    opacity: 0.8,
    kind: "overlay",
    legend: "https://gibs.earthdata.nasa.gov/legends/GPM_Precipitation_Rate_H.svg",
  },
  {
    key: "smap",
    id: "SMAP_L4_Analyzed_Surface_Soil_Moisture",
    product: "Surface Soil Moisture (L4, 12z Instantaneous, Model Value-Added, SMAP)",
    label: "SMAP surface soil moisture",
    credit: `${GIBS_LINK} / NASA SMAP L4`,
    source: "NASA GIBS / SMAP L4",
    matrixSet: "GoogleMapsCompatible_Level6",
    maxzoom: 6,
    ext: "png",
    // Date rule: one 12z analysis per UTC day; newest day GIBS lists (it runs
    // a few days behind).
    step: "P1D",
    rule: "newest daily 12z analysis GIBS lists",
    since: "2015-03-31",
    opacity: 0.7,
    kind: "overlay",
    legend: "https://gibs.earthdata.nasa.gov/legends/SMAP_Analyzed_Soil_Moisture_H.svg",
  },
  {
    key: "dswx_hls",
    id: "OPERA_L3_Dynamic_Surface_Water_Extent-HLS",
    product: "Dynamic Surface Water Extent (Best, OPERA_L3_DSWx-HLS)",
    label: "OPERA surface water, optical",
    credit: `${GIBS_LINK} / NASA JPL OPERA DSWx-HLS (Landsat, Sentinel-2)`,
    source: "NASA GIBS / OPERA DSWx-HLS",
    matrixSet: "GoogleMapsCompatible_Level12",
    maxzoom: 12,
    ext: "png",
    // Date rule: per UTC day of acquisition; newest day GIBS lists. A day holds
    // only the strips imaged that day, and clouds block optical sensors.
    step: "P1D",
    rule: "UTC day of acquisition; only the strips imaged that day",
    since: "2016-01-07",
    opacity: 0.85,
    kind: "overlay",
    legend: "https://gibs.earthdata.nasa.gov/legends/OPERA_Dynamic_Surface_Water_Extent_H.svg",
  },
  {
    key: "dswx_s1",
    id: "OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1",
    product: "Dynamic Surface Water Extent (Best, OPERA_L3_DSWx-S1)",
    label: "OPERA surface water, radar",
    credit: `${GIBS_LINK} / NASA JPL OPERA DSWx-S1, contains modified Copernicus Sentinel data`,
    source: "NASA GIBS / OPERA DSWx-S1",
    matrixSet: "GoogleMapsCompatible_Level12",
    maxzoom: 12,
    minzoom: 9,
    ext: "png",
    // Date rule: per UTC day of acquisition; newest day GIBS lists. Radar
    // sees through cloud, but a day covers only that day's Sentinel-1 strips.
    step: "P1D",
    rule: "UTC day of acquisition; only the strips imaged that day. Zoom in to see it: GIBS's state-wide tiles of this product are striped",
    since: "2023-12-15",
    opacity: 0.85,
    kind: "overlay",
    legend: "https://gibs.earthdata.nasa.gov/legends/OPERA_Dynamic_Surface_Water_Extent_S1_H.svg",
  },
  {
    key: "rtc_s1",
    id: "OPERA_L2_Radiometric_Terrain_Corrected_SAR_Sentinel-1",
    product:
      "OPERA Radiometric Terrain Corrected SAR Backscatter from Sentinel-1 (False Color, Validated, v1.0, Best)",
    label: "OPERA Sentinel-1 radar",
    credit: `${GIBS_LINK} / NASA JPL OPERA RTC-S1, contains modified Copernicus Sentinel data`,
    source: "NASA GIBS / OPERA RTC-S1",
    matrixSet: "GoogleMapsCompatible_Level12",
    maxzoom: 12,
    minzoom: 9,
    ext: "png",
    // Date rule: per UTC day of acquisition; newest day GIBS lists. A day covers
    // only that day's Sentinel-1 strips.
    step: "P1D",
    rule: "UTC day of acquisition; only the strips imaged that day. Zoom in to see it: GIBS's state-wide tiles of this product are striped",
    since: "2025-01-10",
    opacity: 0.9,
    kind: "imagery",
  },
];

export const gibsLayer = (key: GibsKey) => GIBS_LAYERS.find((l) => l.key === key)!;

const STEP_MS: Record<GibsStep, number> = {
  PT10M: 10 * 60_000,
  PT30M: 30 * 60_000,
  P1D: 86_400_000,
};

/** A time as GIBS wants it: `YYYY-MM-DD` for daily layers, else full UTC. */
export function gibsTime(layer: GibsLayer, ms: number): string {
  const iso = new Date(ms).toISOString();
  return layer.step === "P1D" ? iso.slice(0, 10) : iso.replace(/\.\d{3}Z$/, "Z");
}

/** `{z}/{y}/{x}` tile template for MapLibre. `time` null asks GIBS for its
 * default (newest) image. */
export function gibsTiles(layer: GibsLayer, time: string | null): string {
  const t = time ? `${time}/` : "";
  return `${GIBS_ROOT}/${layer.id}/default/${t}${layer.matrixSet}/{z}/{y}/{x}.${layer.ext}`;
}

export interface Interval {
  start: number;
  end: number;
  step: number;
}

/** The time ranges in a GIBS DescribeDomains reply, e.g.
 * `<Domain>2026-11-15/2026-11-16T02:50:00Z/PT10M,…</Domain>`. */
export function parseDomain(xml: string): Interval[] {
  const m = /<Domain>([^<]*)<\/Domain>/.exec(xml);
  if (!m) return [];
  const out: Interval[] = [];
  for (const part of m[1].split(",")) {
    const [a, b, p] = part.trim().split("/");
    const start = Date.parse(a.length === 10 ? `${a}T00:00:00Z` : a);
    const end = Date.parse(b?.length === 10 ? `${b}T00:00:00Z` : (b ?? a));
    const step = STEP_MS[p as GibsStep] ?? 0;
    if (Number.isFinite(start) && Number.isFinite(end) && step) out.push({ start, end, step });
  }
  return out;
}

/** Every valid time inside the intervals between `from` and `to`, oldest first. */
export function timesIn(intervals: Interval[], from: number, to: number): number[] {
  const out: number[] = [];
  for (const iv of intervals) {
    const first = iv.start + Math.max(0, Math.ceil((from - iv.start) / iv.step)) * iv.step;
    for (let t = first; t <= Math.min(iv.end, to); t += iv.step) out.push(t);
  }
  return [...new Set(out)].sort((a, b) => a - b);
}

async function domain(layer: GibsLayer, from: number, to: number, signal?: AbortSignal) {
  const day = (ms: number) => new Date(ms).toISOString().slice(0, 10);
  const range =
    layer.step === "P1D" ? `${day(from)}--${day(to)}` : `${gibsTime(layer, from)}--${gibsTime(layer, to)}`;
  const url = `${GIBS_ROOT}/1.0.0/${layer.id}/default/${layer.matrixSet}/all/${range}.xml`;
  const r = await fetch(url, { signal: signal ?? AbortSignal.timeout(10_000) });
  if (!r.ok) throw new Error(`GIBS ${r.status}`);
  return parseDomain(await r.text());
}

const latestCache = new Map<GibsKey, Promise<string | null>>();

/**
 * The time a daily or half-hourly layer shows by default, per its date rule.
 * Null when GIBS could not be asked: the tiles then use GIBS's own default.
 */
export function latestTime(layer: GibsLayer, now = Date.now()): Promise<string | null> {
  const hit = latestCache.get(layer.key);
  if (hit) return hit;
  const p = domain(layer, now - 21 * STEP_MS.P1D, now + STEP_MS.P1D)
    .then((ivs) => {
      let last = Math.max(...ivs.map((iv) => iv.end));
      if (!Number.isFinite(last)) return null;
      if (layer.key === "viirs") {
        const today = Date.parse(new Date(now).toISOString().slice(0, 10) + "T00:00:00Z");
        const afternoonDone = now - today >= 21 * 3_600_000;
        if (last >= today && !afternoonDone) last = today - STEP_MS.P1D;
      }
      return gibsTime(layer, last);
    })
    .catch(() => {
      latestCache.delete(layer.key);
      return null;
    });
  latestCache.set(layer.key, p);
  return p;
}

export interface GoesFrame {
  /** GIBS time string */
  time: string;
  at: number;
}

/**
 * The GOES-East loop: images GIBS actually lists, 20 minutes apart, over the
 * 3 hours before the newest one, oldest first (the newest is last and is
 * loaded first). Empty when GIBS could not be asked.
 */
export async function goesFrames(now = Date.now(), signal?: AbortSignal): Promise<GoesFrame[]> {
  const layer = gibsLayer("goes");
  const ivs = await domain(layer, now - 8 * 3_600_000, now + 3_600_000, signal);
  const all = timesIn(ivs, now - 8 * 3_600_000, now + 3_600_000);
  // GIBS can list the newest time a few minutes before its tiles exist (seen
  // 2026-11-16: listed, 404 over North Carolina). Check one zoom-3 tile over
  // NC and fall back to an earlier listed time, at most three steps.
  let newest: number | undefined;
  for (const t of all.slice(-4).reverse()) {
    const probe = gibsTiles(layer, gibsTime(layer, t)).replace("{z}/{y}/{x}", "3/3/2");
    const ok = await fetch(probe, { method: "HEAD", signal })
      .then((r) => r.ok)
      .catch(() => false);
    if (signal?.aborted) return [];
    if (ok) {
      newest = t;
      break;
    }
  }
  newest ??= all[all.length - 1];
  if (newest === undefined) return [];
  // every 20 minutes back from the newest; a time GIBS does not list is
  // skipped, never guessed
  const listed = new Set(all);
  const picked: number[] = [];
  for (let t = newest - 3 * 3_600_000; t <= newest; t += 20 * 60_000) {
    if (listed.has(t)) picked.push(t);
  }
  return picked.map((at) => ({ at, time: gibsTime(layer, at) }));
}

/** Step a GIBS time by n of the layer's own steps. */
export function shiftTime(layer: GibsLayer, time: string, n: number): string {
  const ms = Date.parse(layer.step === "P1D" ? `${time}T00:00:00Z` : time);
  return gibsTime(layer, ms + n * STEP_MS[layer.step]);
}

/** "2026-11-15 21:30 UTC" for a sub-daily time, the date alone for a daily one. */
export function timeLabel(layer: GibsLayer, time: string | null): string {
  if (!time) return "newest";
  if (layer.step === "P1D") return time;
  return `${time.slice(0, 10)} ${time.slice(11, 16)} UTC`;
}
