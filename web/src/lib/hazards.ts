/**
 * Phase C3 / D4 — live hazard feeds for the Live Monitor.
 *
 * This layer is genuine real-time hazard *detection*. It is NOT damage
 * assessment: building-level damage only exists once a provider publishes
 * post-event imagery (typically 24–72 h later). The UI must not blur the two.
 *
 * USGS + GDACS are fetched live and fall back to a committed snapshot when the
 * network is unavailable (so the demo works offline). NASA FIRMS needs a free
 * key (`VITE_FIRMS_KEY`); without one its layer is disabled with a clear prompt.
 * Sentinel-1 radar is a documented stub — it needs Copernicus credentials.
 */
import type { HazardType } from "./types";

export interface HazardPointProps {
  id: string;
  source: "usgs" | "gdacs" | "firms";
  hazard_type: HazardType | "fire" | null;
  title: string;
  magnitude?: number | null;
  severity?: number; // 0..3, for sizing/sorting
  alert?: string | null;
  time?: number | null; // epoch ms
}

export type HazardFC = GeoJSON.FeatureCollection<GeoJSON.Point, HazardPointProps>;

export interface HazardResult {
  features: HazardFC;
  stale: boolean; // true = served from the committed snapshot, not live
  disabled?: boolean;
  reason?: string;
  source: string;
  fetchedAt: number;
}

const BASE = import.meta.env.BASE_URL;
const empty = (): HazardFC => ({ type: "FeatureCollection", features: [] });

async function snapshot(name: string): Promise<HazardFC> {
  try {
    const r = await fetch(`${BASE}data/live/${name}`);
    if (r.ok) return (await r.json()) as HazardFC;
  } catch {
    /* fallthrough */
  }
  return empty();
}

// --------------------------------------------------------------------------- //
// USGS — real-time earthquakes, no key
// --------------------------------------------------------------------------- //
const USGS_URL =
  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson";

export async function usgsQuakes(): Promise<HazardResult> {
  const now = Date.now();
  try {
    const r = await fetch(USGS_URL, { signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error(String(r.status));
    const raw = (await r.json()) as GeoJSON.FeatureCollection;
    return {
      features: {
        type: "FeatureCollection",
        features: raw.features
          .filter((f) => f.geometry?.type === "Point")
          .map((f) => {
            const p = f.properties ?? {};
            const mag = Number(p.mag) || 0;
            return {
              type: "Feature" as const,
              geometry: f.geometry as GeoJSON.Point,
              properties: {
                id: String(f.id ?? p.code ?? Math.random()),
                source: "usgs" as const,
                hazard_type: "earthquake" as const,
                title: String(p.place ?? "Earthquake"),
                magnitude: mag,
                severity: mag >= 6.5 ? 3 : mag >= 5.5 ? 2 : mag >= 5 ? 1 : 0,
                alert: p.alert ?? null,
                time: Number(p.time) || null,
              },
            };
          }),
      },
      stale: false,
      source: "USGS · M4.5+ past 7 days",
      fetchedAt: now,
    };
  } catch {
    return {
      features: await snapshot("usgs_snapshot.geojson"),
      stale: true,
      source: "USGS · cached snapshot",
      fetchedAt: now,
    };
  }
}

// --------------------------------------------------------------------------- //
// GDACS — multi-hazard (floods, cyclones, quakes, volcanoes, droughts)
// --------------------------------------------------------------------------- //
const GDACS_URL =
  "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH";

const GDACS_TYPE: Record<string, HazardType> = {
  EQ: "earthquake",
  TC: "cyclone",
  FL: "flood",
  VO: "volcano",
  DR: "other",
  WF: "wildfire",
};

export async function gdacsEvents(): Promise<HazardResult> {
  const now = Date.now();
  try {
    const r = await fetch(GDACS_URL, { signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error(String(r.status));
    const raw = (await r.json()) as GeoJSON.FeatureCollection;
    const items = raw.features ?? [];
    return {
      features: {
        type: "FeatureCollection",
        features: items
          .filter((f) => f.geometry?.type === "Point")
          .map((f) => {
            const p = f.properties ?? {};
            const et = String(p.eventtype ?? "").toUpperCase();
            const lvl = String(p.alertlevel ?? "").toLowerCase();
            return {
              type: "Feature" as const,
              geometry: f.geometry as GeoJSON.Point,
              properties: {
                id: String(p.eventid ?? f.id ?? Math.random()),
                source: "gdacs" as const,
                hazard_type: GDACS_TYPE[et] ?? "other",
                title: String(p.name ?? p.htmldescription ?? p.eventname ?? "Hazard"),
                severity: lvl === "red" ? 3 : lvl === "orange" ? 2 : 1,
                alert: p.alertlevel ?? null,
                time: p.fromdate ? Date.parse(String(p.fromdate)) : null,
              },
            };
          }),
      },
      stale: false,
      source: "GDACS · active alerts",
      fetchedAt: now,
    };
  } catch {
    return {
      features: await snapshot("gdacs_snapshot.geojson"),
      stale: true,
      source: "GDACS · cached snapshot",
      fetchedAt: now,
    };
  }
}

// --------------------------------------------------------------------------- //
// NASA FIRMS — active fire hotspots, needs a free key
// --------------------------------------------------------------------------- //
export async function firmsFires(): Promise<HazardResult> {
  const key = import.meta.env.VITE_FIRMS_KEY;
  const now = Date.now();
  if (!key) {
    return {
      features: empty(),
      stale: false,
      disabled: true,
      reason:
        "Add a free NASA FIRMS map key as VITE_FIRMS_KEY to enable near-real-time active-fire hotspots.",
      source: "NASA FIRMS · not configured",
      fetchedAt: now,
    };
  }
  // world VIIRS_SNPP_NRT, last 1 day
  const url = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${key}/VIIRS_SNPP_NRT/-180,-60,180,80/1`;
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(10000) });
    if (!r.ok) throw new Error(String(r.status));
    const text = await r.text();
    const [head, ...rows] = text.trim().split("\n");
    const cols = head.split(",");
    const li = cols.indexOf("latitude");
    const lo = cols.indexOf("longitude");
    const fr = cols.indexOf("frp");
    return {
      features: {
        type: "FeatureCollection",
        features: rows.slice(0, 4000).map((line, i) => {
          const c = line.split(",");
          const frp = Number(c[fr]) || 0;
          return {
            type: "Feature" as const,
            geometry: {
              type: "Point" as const,
              coordinates: [Number(c[lo]), Number(c[li])],
            },
            properties: {
              id: `firms-${i}`,
              source: "firms" as const,
              hazard_type: "fire" as const,
              title: `Fire hotspot · FRP ${frp.toFixed(0)} MW`,
              severity: frp >= 50 ? 3 : frp >= 15 ? 2 : 1,
            },
          };
        }),
      },
      stale: false,
      source: "NASA FIRMS · VIIRS 24 h",
      fetchedAt: now,
    };
  } catch {
    return {
      features: empty(),
      stale: true,
      disabled: true,
      reason: "FIRMS request failed — check the key or network.",
      source: "NASA FIRMS · error",
      fetchedAt: now,
    };
  }
}

// --------------------------------------------------------------------------- //
// Sentinel-1 radar — documented stub (Phase D4)
// --------------------------------------------------------------------------- //
export function sentinel1(): HazardResult {
  return {
    features: empty(),
    stale: false,
    disabled: true,
    reason:
      "Sentinel-1 C-band radar sees through cloud and smoke — a coarse 'something changed here' signal in the hours before optical post-event imagery. Needs Copernicus Data Space credentials; wired as an extension point.",
    source: "Copernicus Sentinel-1 · not configured",
    fetchedAt: Date.now(),
  };
}
