/**
 * The full Maxar Open Data catalogue (~55 events) + the on-demand assessment
 * bridge. This is what makes TerraTriage "point it at any disaster" rather than
 * a Helene replay: the Live Monitor cross-references live USGS/GDACS hazards
 * against every event Maxar has imagery for, and — when the local pipeline
 * server is running — can ingest one on the spot.
 *
 * Everything degrades gracefully with no server: matching runs client-side
 * against the committed `maxar_catalog.json`, and the ingest action falls back
 * to showing the exact `run.py` commands.
 */
import type { HazardType } from "./types";
import type { HazardFC } from "./hazards";

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

export interface HazardMatch {
  event: string;
  name: string;
  hazard: string; // live hazard title
  hazard_type: string | null;
  type_match: boolean;
  distance_km: number;
  imagery_age_days: number | null;
  score: number;
  ingested: boolean;
  center: [number, number] | null;
  capture_dates: string[] | null;
}

export const API_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export async function loadCatalog(): Promise<CatalogEvent[]> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/maxar_catalog.json`);
  if (!res.ok) return [];
  return (await res.json()) as CatalogEvent[];
}

/** Is the pipeline server reachable? (short timeout, no throw) */
export async function serverUp(): Promise<boolean> {
  try {
    const r = await fetch(`${API_URL}/catalog`, { signal: AbortSignal.timeout(2500) });
    return r.ok;
  } catch {
    return false;
  }
}

const R = 6371;
function haversineKm(a: [number, number], b: [number, number]) {
  const dLat = ((b[1] - a[1]) * Math.PI) / 180;
  const dLon = ((b[0] - a[0]) * Math.PI) / 180;
  const la1 = (a[1] * Math.PI) / 180;
  const la2 = (b[1] * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

const HZ_ALIGN: Record<string, string> = {
  earthquake: "earthquake",
  cyclone: "cyclone",
  hurricane: "hurricane",
  flood: "flood",
  wildfire: "wildfire",
  fire: "wildfire",
  volcano: "volcano",
};

/** Client-side fallback for /events/match — pair live hazards with catalogue
 * events by proximity + hazard family + imagery recency. */
export function matchClientSide(
  catalog: CatalogEvent[],
  hazards: HazardFC,
  ingestedIds: Set<string>,
  radiusKm = 250,
): HazardMatch[] {
  const now = Date.now();
  const best = new Map<string, HazardMatch>();
  for (const ev of catalog) {
    const c =
      ev.center ??
      (ev.bbox ? ([(ev.bbox[0] + ev.bbox[2]) / 2, (ev.bbox[1] + ev.bbox[3]) / 2] as [number, number]) : null);
    if (!c) continue;
    const latest = ev.capture_dates?.[ev.capture_dates.length - 1];
    const ageDays = latest ? Math.round((now - Date.parse(latest)) / 86_400_000) : null;
    for (const f of hazards.features) {
      const p = f.properties;
      const hc = f.geometry.coordinates as [number, number];
      const d = haversineKm(c, hc);
      if (d > radiusKm) continue;
      const liveHaz = HZ_ALIGN[String(p.hazard_type ?? "")] ?? p.hazard_type ?? null;
      const typeOk = !!liveHaz && liveHaz === ev.hazard;
      const distScore = 1 - d / radiusKm;
      const freshScore = ageDays == null ? 0.1 : ageDays <= 120 ? 1 : ageDays <= 400 ? 0.4 : 0.1;
      const score = 0.5 * distScore + 0.3 * (typeOk ? 1 : 0) + 0.2 * freshScore;
      const m: HazardMatch = {
        event: ev.id,
        name: ev.name,
        hazard: p.title,
        hazard_type: liveHaz,
        type_match: typeOk,
        distance_km: Math.round(d * 10) / 10,
        imagery_age_days: ageDays,
        score: Math.round(score * 1000) / 1000,
        ingested: ingestedIds.has(ev.id),
        center: ev.center,
        capture_dates: ev.capture_dates ?? null,
      };
      const prev = best.get(ev.id);
      if (!prev || m.score > prev.score) best.set(ev.id, m);
    }
  }
  return [...best.values()].sort((a, b) => b.score - a.score);
}

export async function fetchMatches(radiusKm = 250): Promise<HazardMatch[] | null> {
  try {
    const r = await fetch(`${API_URL}/events/match?radius_km=${radiusKm}`, {
      signal: AbortSignal.timeout(30_000),
    });
    if (!r.ok) return null;
    return (await r.json()) as HazardMatch[];
  } catch {
    return null;
  }
}

export interface AssessJob {
  status: "queued" | "running" | "done" | "error";
  step?: string;
  area?: string;
  error?: string;
  log_tail?: string;
}

export async function startAssess(body: {
  event: string;
  lat: number;
  lon: number;
  name?: string;
  subtitle?: string;
}): Promise<{ job_id: string | null; status: string; area: string } | null> {
  try {
    const r = await fetch(`${API_URL}/assess`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    });
    if (!r.ok) return null;
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
    `    --area ${area} --lat ${lat} --lon ${lon}`,
    `./.venv/bin/python scripts/run.py infer --area ${area}`,
    `./.venv/bin/python scripts/make_tiles.py --area ${area}`,
    `./.venv/bin/python scripts/run.py events registry`,
  ].join("\n");
}
