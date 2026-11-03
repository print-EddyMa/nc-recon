/**
 * Butterfly - adjoint storm sensitivity (schema `ncrecon.butterfly/1`).
 *
 * Mirrors `pipeline/butterfly/export_web.py`. One JSON per historical storm in
 * `public/data/butterfly/<case>.json`, listed in `index.json`. Everything in it
 * is computed offline by the pipeline from real ERA5 + NOAA IBTrACS through
 * NeuralGCM; the screen only draws it.
 */

/** [west, south, east, north, value] - one model grid cell */
export type Cell = [number, number, number, number, number];
/** [lon, lat, u, v] - a wind-nudge arrow (m/s) */
export type Arrow = [number, number, number, number];

export interface TrackPoint {
  time: string;
  lat: number;
  lon: number;
  /** distance to the NOAA best-track position at the same time */
  err_km?: number;
}

export interface BestTrackPoint {
  time: string;
  lat: number;
  lon: number;
  wind_kt: number | null;
  pres_mb: number | null;
}

export interface ButterflyRun {
  id: "baseline" | "away_0.25" | "away_0.5" | "away_1" | "toward_1" | string;
  label: string;
  /** nudge strength: peak amplitude as a multiple of analysis error; sign = direction */
  s: number;
  /** objective (mean over the window) */
  J: number;
  /** % change vs the un-nudged forecast (full nonlinear re-forecast) */
  change_pct: number;
  /** what the gradient alone predicted (first-order Taylor) - the lie detector */
  linear_change_pct?: number | null;
  track: TrackPoint[];
  energy_J: number | null;
  peak: { T_K: number; wind_ms: number; q_gkg: number } | null;
  /** the objective's field (IVT at one hour, or rain accumulated from `from_hour`) */
  impact: { hour: number; from_hour?: number | null; cells: Cell[] };
}

export interface NudgeLevel {
  level_hpa: number;
  max_abs_T: number;
  max_wind: number;
  /** temperature nudge (K) */
  cells: Cell[];
  arrows: Arrow[];
}

export interface ButterflyCase {
  schema: "ncrecon.butterfly/1";
  generated: string;
  case: {
    id: string;
    name: string;
    init: string;
    storm0: [number, number];
    notes: string;
    target: { lat: number; lon: number; label: string; radius_km: number };
    objective: "ivt" | "wind" | "rain";
    objective_label: string;
    /** short stat label, e.g. "Rain over WNC" */
    objective_short?: string;
    impact_unit?: string;
    window_hours: number[];
    keep_out_km: number;
    model: string;
    analysis_error: { T_K: number; wind_ms: number; q_gkg: number; q_relative?: number };
    /** pressure range the nudge is allowed in, [top, bottom] hPa */
    nudge_levels_hpa?: [number, number];
  };
  best_track: BestTrackPoint[];
  skill: { mean_track_err_km: number | null; window_track_err_km: (number | null)[] };
  runs: ButterflyRun[];
  sensitivity: {
    /** column sensitivity, normalised 0..1 */
    cells: Cell[];
    levels_hpa: number[];
    profile: Record<string, number[]>;
  };
  nudge: { levels: NudgeLevel[] };
  /** pipeline/butterfly/experiments.py - each part optional */
  rigor?: Rigor | null;
  /** an independent reference for the un-nudged forecast (rain cases: ERA5 rainfall) */
  reference?: { era5_rain_mm: number; era5_rain_max_cell_mm: number } | null;
}

export interface Rigor {
  /** real change / gradient-predicted change, by nudge size (Taylor test) */
  taylor?: { s: number; ratio: number }[];
  /** random nudges under the same caps: % change each */
  random?: { change_pct: number[]; constraint: string };
  /** deep-layer-mean steering flow around the storm, mean over `hours` */
  steering?: {
    hours: number[];
    baseline_ms: [number, number];
    baseline_J_repro: number;
    runs: Record<string, { delta_ms: [number, number]; implied_km: number; J_repro: number }>;
  };
  /** same nudge put into a different model */
  transfer?: {
    model: string;
    change_pct: number;
    source_change_pct: number;
    /** how well that model's un-nudged forecast tracks the real storm */
    baseline_track_err_km?: { mean: number; at_72h: number; at_78h: number } | null;
  };
  /** nonlinear optimal perturbation vs the one-step nudge */
  cnop?: { change_pct: number; one_step_change_pct: number; iterations: number };
  /** simulated targeted observations (osse.py) */
  osse?: Osse;
}

export interface Osse {
  radius_km: number;
  alpha: number;
  n_samples: number;
  /** forecast-error std of the impact from analysis error, % of the impact */
  error_std_pct: number;
  /** error-variance reduction (0..1), held-out samples, linear */
  storm: { center: [number, number]; reduction: number };
  adjoint: { center: [number, number]; reduction: number };
  random: { median: number; p90: number };
  second: {
    center: [number, number];
    storm_only: number;
    with_adjoint_second: number;
    random_second_median: number;
    random_second_p90: number;
  };
  /** full nonlinear forecasts: mean |impact error| (%) and 72-h track error (km) */
  verify?: Record<string, { impact_err_pct: number; rms_err_pct: number; track_err_km: number; off_branch: number }>;
  n_verify?: number;
}

export interface ButterflyIndexEntry {
  id: string;
  name: string;
  target: string;
  /** headline numbers for the cross-storm table */
  summary?: {
    objective_short: string;
    model: string;
    change_1x: number | null;
    toward_1x: number | null;
    /** real / gradient-predicted change at 0.1x and 1x */
    ratio_01: number | null;
    ratio_1: number | null;
    random_max_abs: number | null;
    n_random: number;
    track_err_km: number | null;
  };
}

const BASE = `${import.meta.env.BASE_URL}data/butterfly/`;

export async function loadButterflyIndex(): Promise<ButterflyIndexEntry[]> {
  const res = await fetch(`${BASE}index.json`, { signal: AbortSignal.timeout(15_000) });
  if (!res.ok) throw new Error(`butterfly index: ${res.status}`);
  return (await res.json()) as ButterflyIndexEntry[];
}

export async function loadButterflyCase(id: string): Promise<ButterflyCase> {
  const res = await fetch(`${BASE}${encodeURIComponent(id)}.json`, {
    signal: AbortSignal.timeout(15_000),
  });
  if (!res.ok) throw new Error(`butterfly case ${id}: ${res.status}`);
  const doc = (await res.json()) as ButterflyCase;
  if (doc?.schema !== "ncrecon.butterfly/1") throw new Error(`${id}: unexpected schema`);
  return doc;
}

// ---- colour -------------------------------------------------------------------
// Three data ramps, deliberately off both the damage ramp and the NC severity
// ramp (DESIGN.md): a sensitivity map is neither damage nor live risk.

type RGB = [number, number, number];
const lerp = (a: RGB, b: RGB, t: number): RGB => [
  Math.round(a[0] + (b[0] - a[0]) * t),
  Math.round(a[1] + (b[1] - a[1]) * t),
  Math.round(a[2] + (b[2] - a[2]) * t),
];
function ramp(stops: RGB[], t: number): RGB {
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  return lerp(stops[i], stops[i + 1], x - i);
}

/** sensitivity: one hue (violet), light -> dark */
export const SENS_STOPS: RGB[] = [
  [237, 233, 254],
  [196, 181, 253],
  [139, 92, 246],
  [91, 33, 182],
  [59, 7, 100],
];
export const sensRGB = (t: number) => ramp(SENS_STOPS, Math.sqrt(t));

/** moisture transport: one hue (teal), light -> dark */
export const IVT_STOPS: RGB[] = [
  [204, 236, 230],
  [125, 200, 188],
  [47, 158, 143],
  [21, 110, 100],
  [8, 64, 60],
];
export const ivtRGB = (t: number) => ramp(IVT_STOPS, t);

/** temperature nudge: diverging cool <-> warm around a neutral grey */
const COOL: RGB = [59, 111, 182];
const MID: RGB = [200, 200, 196];
const WARM: RGB = [196, 71, 58];
export const tempRGB = (t: number): RGB =>
  t < 0 ? lerp(MID, COOL, Math.min(1, -t)) : lerp(MID, WARM, Math.min(1, t));

/** model runs: un-nudged in the neutral meter grey, "away" runs in the
 * sensitivity hue by strength, the reversed run on the severe red. */
// dark: its own steps (DESIGN.md), stronger = lighter so it holds contrast on dark-matter
const RUN_DARK: RGB[] = [
  [124, 58, 237],
  [167, 139, 250],
  [221, 214, 254],
];
export function runRGB(run: Pick<ButterflyRun, "id" | "s">, dark = false): RGB {
  if (run.s === 0) return dark ? [132, 148, 168] : [100, 116, 139];
  if (run.s < 0) return [209, 73, 91];
  return ramp(dark ? RUN_DARK : SENS_STOPS.slice(1), Math.min(1, run.s));
}
export const css = (c: RGB, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

/** great-circle-ish ring (lon/lat polygon) of a given radius, for the target zone */
export function ring(lat: number, lon: number, km: number, n = 72): [number, number][] {
  const out: [number, number][] = [];
  const R = 6371;
  const p1 = (lat * Math.PI) / 180;
  const l1 = (lon * Math.PI) / 180;
  const d = km / R;
  for (let i = 0; i <= n; i++) {
    const b = (2 * Math.PI * i) / n;
    const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
    const l2 = l1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
    out.push([(l2 * 180) / Math.PI, (p2 * 180) / Math.PI]);
  }
  return out;
}

export const fmtUTC = (iso: string) => {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}:00Z`.replace(/:00:00Z$/, ":00Z"));
  return `${d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })} ${String(d.getUTCHours()).padStart(2, "0")}Z`;
};
