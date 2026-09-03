import type { BuildingFeature, DamageClass, DamageCollection } from "./types";
import { isSevere } from "./damage";
import { API_URL } from "./catalog";

/**
 * Where per-area assessment output lives. With no `VITE_API_URL` the app is a
 * static site and reads tiles + GeoJSON from `public/`; with one set, a fresh
 * assessment is served by the pipeline service, which the container writes to
 * its own volume, so read it from there.
 */
export const tilesBase = () =>
  API_URL ? `${API_URL}/tiles/` : `${import.meta.env.BASE_URL}tiles/`;

export const heroTileUrl = (id: string, kind: "pre" | "post", [z, x, y]: [number, number, number]) =>
  `${tilesBase()}${id}/${kind}/${z}/${x}/${y}.jpg`;

/** XYZ tile + within-tile fractional offset for a lon/lat, used by the review
 * queue to show a tight pre/post crop of one building from the committed tiles. */
export function tileForLonLat(lon: number, lat: number, z: number) {
  const n = 2 ** z;
  const xf = ((lon + 180) / 360) * n;
  const latRad = (lat * Math.PI) / 180;
  const yf = ((1 - Math.asinh(Math.tan(latRad)) / Math.PI) / 2) * n;
  const x = Math.floor(xf);
  const y = Math.floor(yf);
  return { z, x, y, fx: xf - x, fy: yf - y };
}

export async function loadArea(id: string): Promise<DamageCollection> {
  const url = API_URL
    ? `${API_URL}/areas/${encodeURIComponent(id)}`
    : `${import.meta.env.BASE_URL}data/${id}.geojson`;
  // a bare fetch here hangs forever if the assessment service accepts the
  // connection but never responds — the area screens then sit on a skeleton
  // with no way out. Bound it, and let the caller show a retry.
  const res = await fetch(url, { signal: AbortSignal.timeout(15_000) });
  if (!res.ok) throw new Error(`failed to load ${id}: ${res.status}`);
  const fc = (await res.json()) as DamageCollection;
  if (fc?.type !== "FeatureCollection" || !Array.isArray(fc.features)) {
    throw new Error(`${id}: not a GeoJSON FeatureCollection`);
  }
  // keep only well-formed building features so one bad row can't crash a screen
  fc.features = fc.features.filter(
    (f): f is BuildingFeature =>
      !!f &&
      f.geometry?.type === "Polygon" &&
      Number.isInteger(f.properties?.damage_class) &&
      f.properties.damage_class >= 0 &&
      f.properties.damage_class <= 3 &&
      Array.isArray(f.properties.centroid),
  );
  return fc;
}

export interface AreaStats {
  total: number;
  counts: Record<DamageClass, number>;
  severe: number;
  severePct: number;
  assessedAreaKm2: number;
}

export function summarize(
  fc: DamageCollection,
  overrides?: Record<string, DamageClass>,
): AreaStats {
  const counts: Record<DamageClass, number> = { 0: 0, 1: 0, 2: 0, 3: 0 };
  let area = 0;
  for (const f of fc.features) {
    const c = overrides?.[f.properties.id] ?? f.properties.damage_class;
    counts[c]++;
    area += f.properties.area_m2;
  }
  const total = fc.features.length;
  const severe = counts[2] + counts[3];
  return {
    total,
    counts,
    severe,
    severePct: total ? (severe / total) * 100 : 0,
    assessedAreaKm2: area / 1e6,
  };
}

export interface Hotspot {
  key: string;
  label: string;
  center: [number, number];
  count: number;
  severe: number;
  score: number;
  members: string[];
}

/**
 * Grid-cluster the buildings and rank cells by a damage-weighted score, so the
 * side panel can offer "hardest-hit areas" with a camera fly-to per cell.
 */
export function hotspots(fc: DamageCollection, cellMeters = 220, limit = 6): Hotspot[] {
  const [lon0, lat0] = fc.features[0]?.geometry.coordinates[0][0] ?? [0, 0];
  const mPerDegLat = 111_320;
  const mPerDegLon = 111_320 * Math.cos((lat0 * Math.PI) / 180);
  const cells = new Map<string, BuildingFeature[]>();

  for (const f of fc.features) {
    const [lon, lat] = f.properties.centroid;
    const gx = Math.floor(((lon - lon0) * mPerDegLon) / cellMeters);
    const gy = Math.floor(((lat - lat0) * mPerDegLat) / cellMeters);
    const k = `${gx}:${gy}`;
    (cells.get(k) ?? cells.set(k, []).get(k)!).push(f);
  }

  const weight: Record<DamageClass, number> = { 0: 0, 1: 1, 2: 4, 3: 9 };
  const out: Hotspot[] = [];
  for (const [k, members] of cells) {
    if (members.length < 3) continue;
    let score = 0;
    let severe = 0;
    let lon = 0;
    let lat = 0;
    for (const m of members) {
      score += weight[m.properties.damage_class];
      if (isSevere(m.properties.damage_class)) severe++;
      lon += m.properties.centroid[0];
      lat += m.properties.centroid[1];
    }
    out.push({
      key: k,
      label: "",
      center: [lon / members.length, lat / members.length],
      count: members.length,
      severe,
      score,
      members: members.map((m) => m.properties.id),
    });
  }
  out.sort((a, b) => b.score - a.score);
  const top = out.slice(0, limit);
  top.forEach((h, i) => (h.label = `Cluster ${String.fromCharCode(65 + i)}`));
  return top;
}
