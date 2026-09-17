/**
 * The Maxar Open Data catalogue (~55 events) + the on-demand assessment bridge.
 * NC Recon is North Carolina-only: the catalogue is filtered to events whose
 * coverage touches NC (`intersectsNC`), and an AOI can be assessed on the spot
 * when the pipeline service is reachable.
 *
 * With no service the Assess screen falls back to showing the exact `run.py`
 * commands. `maxar_catalog.json` is catalogue *metadata*, not sample data, it
 * stays committed.
 */
import type { HazardType } from "./types";

export interface CatalogEvent {
  id: string;
  name: string;
  hazard: HazardType;
  center: [number, number] | null;
  bbox: [number, number, number, number] | null;
  capture_dates: string[]; // [earliest, latest]
  n_captures: number;
  n_quadkeys: number;
}

/**
 * The pipeline service base URL. Set `VITE_API_URL` (in `web/.env.development.local`
 * for dev, or the host's build env) to enable one-click assessment. When it is unset
 * the
 * app runs as a pure static site: the NC risk monitor is fully live, and the
 * Assess screen shows the exact commands to run the pipeline yourself.
 */
export const API_URL: string = import.meta.env.VITE_API_URL || "";

/** North Carolina bounding box [w, s, e, n], the only AOIs this app assesses. */
export const NC_BBOX: [number, number, number, number] = [-84.55, 33.75, -75.4, 36.7];

export const inNC = (lon: number, lat: number) =>
  lon >= NC_BBOX[0] && lon <= NC_BBOX[2] && lat >= NC_BBOX[1] && lat <= NC_BBOX[3];

/**
 * Does a Maxar catalogue event give *meaningful* North Carolina coverage? A
 * hurricane bbox can graze NC's corner while all its imagery is in FL/SC, that
 * is not a useful "assess NC" option, so require a real overlap (~0.25° each way,
 * roughly a county) or a centre inside the state.
 */
export function intersectsNC(ev: CatalogEvent): boolean {
  if (ev.center && inNC(ev.center[0], ev.center[1])) return true;
  if (!ev.bbox) return false;
  const [w, s, e, n] = ev.bbox;
  const lonOverlap = Math.min(e, NC_BBOX[2]) - Math.max(w, NC_BBOX[0]);
  const latOverlap = Math.min(n, NC_BBOX[3]) - Math.max(s, NC_BBOX[1]);
  return lonOverlap >= 0.25 && latOverlap >= 0.25;
}

/**
 * A [lon,lat] inside North Carolina for an event, the centre of the overlap of
 * its bbox with NC (falls back to its own centre when that is already in NC).
 * The ⌘K quick-assess needs an in-NC point since the event centroid of a
 * multi-state event can sit in VA/SC and the service rejects it.
 */
export function ncPointFor(ev: CatalogEvent): [number, number] | null {
  const c = ev.center ?? (ev.bbox ? ([(ev.bbox[0] + ev.bbox[2]) / 2, (ev.bbox[1] + ev.bbox[3]) / 2] as [number, number]) : null);
  if (c && inNC(c[0], c[1])) return c;
  if (!ev.bbox) return null;
  const [w, s, e, n] = ev.bbox;
  const ox0 = Math.max(w, NC_BBOX[0]);
  const oy0 = Math.max(s, NC_BBOX[1]);
  const ox1 = Math.min(e, NC_BBOX[2]);
  const oy1 = Math.min(n, NC_BBOX[3]);
  if (ox0 > ox1 || oy0 > oy1) return null;
  return [(ox0 + ox1) / 2, (oy0 + oy1) / 2];
}

export async function loadCatalog(): Promise<CatalogEvent[]> {
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}data/maxar_catalog.json`, {
      signal: AbortSignal.timeout(8_000),
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? (data as CatalogEvent[]) : [];
  } catch {
    // offline / asset missing - the Assess screen still works (manual commands)
    return [];
  }
}

export interface EventCoverage {
  event: string;
  event_date: string | null;
  n_cells: number;
  bbox: [number, number, number, number] | null;
  cells: [number, number, number, number][]; // [w,s,e,n] lon/lat boxes
}

/** The assessable footprint of an event (quadkeys with a before + after
 * capture). Needs the service; returns null without one. */
export async function loadCoverage(eventId: string): Promise<EventCoverage | null> {
  if (!API_URL) return null;
  try {
    const r = await fetch(`${API_URL}/events/${encodeURIComponent(eventId)}/coverage`, {
      signal: AbortSignal.timeout(20_000),
    });
    if (!r.ok) return null;
    return (await r.json()) as EventCoverage;
  } catch {
    return null;
  }
}

/** GeoJSON polygons for a coverage cell list, for the Assess map overlay. */
export function coverageToGeoJSON(cov: EventCoverage | null): GeoJSON.FeatureCollection {
  const feats: GeoJSON.Feature[] = (cov?.cells ?? []).map(([w, s, e, n], i) => ({
    type: "Feature",
    properties: { i },
    geometry: {
      type: "Polygon",
      coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
    },
  }));
  return { type: "FeatureCollection", features: feats };
}

/** Is [lon,lat] inside (or within `padDeg` of) any coverage cell? */
export function pointCovered(
  cov: EventCoverage | null,
  lon: number,
  lat: number,
  padDeg = 0.05,
): boolean {
  if (!cov?.cells?.length) return true; // unknown → don't block
  return cov.cells.some(
    ([w, s, e, n]) =>
      lon >= w - padDeg && lon <= e + padDeg && lat >= s - padDeg && lat <= n + padDeg,
  );
}

/** Is the pipeline service reachable? (fast /health probe, no throw) */
export async function serverUp(): Promise<boolean> {
  if (!API_URL) return false;
  try {
    const r = await fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(3000) });
    return r.ok;
  } catch {
    return false;
  }
}


export interface AssessJob {
  status: "queued" | "running" | "done" | "error";
  step?: string;
  area?: string;
  error?: string;
  log_tail?: string;
}

/** Optional bearer token for a hosted service that requires auth. */
const API_TOKEN: string = import.meta.env.VITE_API_TOKEN || "";
const authHeaders = (): Record<string, string> =>
  API_TOKEN ? { authorization: `Bearer ${API_TOKEN}` } : {};

export async function startAssess(body: {
  event: string;
  lat: number;
  lon: number;
  name?: string;
  subtitle?: string;
}): Promise<{ job_id: string | null; status: string; area: string; error?: string } | null> {
  if (!API_URL) return null;
  try {
    const r = await fetch(`${API_URL}/assess`, {
      method: "POST",
      headers: { "content-type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    });
    if (!r.ok) {
      let detail: string | undefined;
      try {
        detail = (await r.json())?.detail;
      } catch {
        /* non-JSON error body */
      }
      return { job_id: null, status: "error", area: "", error: detail || `HTTP ${r.status}` };
    }
    return await r.json();
  } catch {
    return null;
  }
}

export async function pollAssess(jobId: string): Promise<AssessJob | null> {
  try {
    const r = await fetch(`${API_URL}/assess/${jobId}`, { signal: AbortSignal.timeout(8000) });
    if (!r.ok) return null;
    return (await r.json()) as AssessJob;
  } catch {
    return null;
  }
}

/** The manual fallback: the commands a user runs when there's no server. */
export function assessCommands(ev: { id: string; center: [number, number] | null; name?: string }) {
  const lat = ev.center ? ev.center[1].toFixed(4) : "<lat>";
  const lon = ev.center ? ev.center[0].toFixed(4) : "<lon>";
  const area = (ev.name ?? ev.id).toLowerCase().replace(/[^a-z0-9_]+/g, "_").slice(0, 40);
  return [
    `./.venv/bin/python scripts/run.py fetch --event ${ev.id} \\`,
    `    --area ${area} --lat ${lat} --lon ${lon} --name ${JSON.stringify(ev.name ?? area)}`,
    `./.venv/bin/python scripts/run.py infer --area ${area} --source auto --nc-context`,
    `./.venv/bin/python scripts/make_tiles.py --area ${area}`,
    `./.venv/bin/python scripts/run.py events registry`,
  ].join("\n");
}
