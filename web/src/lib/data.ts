import type { AreaConfig, BuildingFeature, DamageClass, DamageCollection } from "./types";
import { isSevere } from "./damage";

export const AREAS: AreaConfig[] = [
  {
    id: "old_fort",
    name: "Old Fort",
    subtitle: "McDowell County, NC",
    center: [-82.1804, 35.6293],
    zoom: 15.2,
    hero: [16, 17807, 25818],
  },
  {
    id: "spruce_pine",
    name: "Spruce Pine",
    subtitle: "Mitchell County, NC",
    center: [-82.0643, 35.9151],
    zoom: 15.4,
    hero: [16, 17827, 25754],
  },
];

export const heroTileUrl = (id: string, kind: "pre" | "post", [z, x, y]: [number, number, number]) =>
  `${import.meta.env.BASE_URL}tiles/${id}/${kind}/${z}/${x}/${y}.jpg`;

export const areaById = (id: string) => AREAS.find((a) => a.id === id) ?? AREAS[0];

export async function loadArea(id: string): Promise<DamageCollection> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${id}.geojson`);
  if (!res.ok) throw new Error(`failed to load ${id}: ${res.status}`);
  return (await res.json()) as DamageCollection;
}

export interface AreaStats {
  total: number;
  counts: Record<DamageClass, number>;
  severe: number;
  severePct: number;
  assessedAreaKm2: number;
}

export function summarize(fc: DamageCollection): AreaStats {
  const counts: Record<DamageClass, number> = { 0: 0, 1: 0, 2: 0, 3: 0 };
  let area = 0;
  for (const f of fc.features) {
    counts[f.properties.damage_class]++;
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
