// Mirrors pipeline/src/terratriage/contract.py — the Phase A → Phase B contract.

export type DamageClass = 0 | 1 | 2 | 3;

export interface ImageMeta {
  date: string;
  source: string;
  catalog_id: string | null;
  gsd: number | null;
  url: string | null;
}

export interface RunMeta {
  event: string;
  area: string;
  model: string;
  pre_image: ImageMeta;
  post_image: ImageMeta;
  generated: string;
  schema_version: string;
  tile_size: number;
  notes: string | null;
  counts: Record<string, number>;
  n_buildings: number;
  bounds?: [number, number, number, number]; // [w, s, e, n]
  runtime_sec?: number;
}

export interface BuildingProps {
  id: string;
  damage_class: DamageClass;
  damage_label: string;
  confidence: number;
  area_m2: number;
  centroid: [number, number]; // [lon, lat]
}

export type BuildingFeature = GeoJSON.Feature<GeoJSON.Polygon, BuildingProps>;

export interface DamageCollection
  extends GeoJSON.FeatureCollection<GeoJSON.Polygon, BuildingProps> {
  properties: RunMeta;
}

export interface AreaConfig {
  id: string;
  name: string;
  subtitle: string;
  center: [number, number]; // [lon, lat]
  zoom: number;
  hero: [number, number, number]; // [z, x, y] tile for the landing before/after
}
