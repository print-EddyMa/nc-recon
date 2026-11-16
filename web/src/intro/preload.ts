/**
 * Everything the intro touches is in memory before it plays, and the basemap
 * tiles along its camera path are already in MapLibre's cache. All of it is
 * served from this origin (public/demo/ and public/intro/): no API, no CDN
 * tiles. The intro shares the pitch demo's baked assets and adds three of its
 * own (scripts/intro_bake.py).
 *
 * Built by vite.demo.config.ts, so maplibre-gl / @deck.gl resolve to the
 * pinned copies in demo-deps/ (the interleaved overlay needs that pairing).
 */
import * as maplibregl from "maplibre-gl";
import type { RadarManifest } from "../demo/preload";
import { B, cameraAt, fitFlat, type Cam } from "./beats";

const BASE = import.meta.env.BASE_URL;
const D = `${BASE}demo/`;
const I = `${BASE}intro/`;

/** One Old Fort structure as baked: centroid, FEMA level index (-1 = in the
 * inventory but not assessed), review flag, outline ring (absent for points). */
export interface Structure {
  c: [number, number];
  l: number;
  v: number;
  r?: [number, number][];
}

export interface AreaRow {
  id: string;
  name: string;
  county: string;
  center: [number, number];
  structures: number;
  assessed: number;
  severe: number;
  severe_lo: number;
  severe_hi: number;
  review: number;
  displaced: number | null;
  runtime_s: number | null;
  expected: Record<string, number>;
  pre_date: string | null;
  post_date: string | null;
}

export interface AreasFile {
  areas: AreaRow[];
  total: { areas: number; structures: number; severe: number; review: number; max_runtime_s: number };
  focus: AreaRow;
}

export interface IntroAssets {
  radar: { manifest: RadarManifest; images: HTMLImageElement[] };
  ncOutline: GeoJSON.FeatureCollection;
  structures: Structure[];
  areas: AreasFile;
  beforeImg: HTMLImageElement;
  afterImg: HTMLImageElement;
  wideImg: HTMLImageElement;
  /** [west, south, east, north] of wideImg */
  wideBounds: [number, number, number, number];
}

const loadImage = (src: string) =>
  new Promise<HTMLImageElement>((res, rej) => {
    const im = new Image();
    im.decoding = "sync";
    im.onload = () => res(im);
    im.onerror = () => rej(new Error(`image failed: ${src}`));
    im.src = src;
  });

const loadJSON = async <T>(src: string): Promise<T> => {
  const r = await fetch(src);
  if (!r.ok) throw new Error(`${r.status} ${src}`);
  return r.json() as Promise<T>;
};

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

async function basemapStyle(): Promise<maplibregl.StyleSpecification> {
  const r = await fetch(`${D}basemap/style.json`);
  if (!r.ok)
    throw new Error("the offline basemap is not baked yet: run `npm run demo:assets` in web/");
  // tile / glyph / sprite URLs must be absolute: MapLibre fetches them in a worker
  const abs = new URL(BASE, location.href).href;
  return JSON.parse((await r.text()).replaceAll("__BASE__", abs)) as maplibregl.StyleSpecification;
}

export async function preloadIntro(
  container: HTMLDivElement,
  onProgress: (p: number, label: string) => void,
  /** dense warm walk for frame-capture recording (?prewarm=1) */
  dense: boolean,
): Promise<{ assets: IntroAssets; map: maplibregl.Map }> {
  fitFlat(container.clientWidth, container.clientHeight);
  onProgress(0, "fonts");
  await Promise.race([
    (document as Document & { fonts?: { ready?: Promise<unknown> } }).fonts?.ready ??
      Promise.resolve(),
    sleep(4000),
  ]);

  onProgress(0.05, "data");
  const manifest = await loadJSON<RadarManifest>(`${D}radar/manifest.json`);
  const [images, ncOutline, st, areas, wide] = await Promise.all([
    Promise.all(manifest.frames.map((f) => loadImage(`${D}${f.file}`))),
    loadJSON<GeoJSON.FeatureCollection>(`${D}nc-outline.json`),
    loadJSON<{ structures: Structure[] }>(`${I}structures.json`),
    loadJSON<AreasFile>(`${I}areas.json`),
    loadJSON<{ bounds: [number, number, number, number] }>(`${I}oldfort_wide.json`),
  ]);
  onProgress(0.2, "imagery");
  const [beforeImg, afterImg, wideImg] = await Promise.all([
    loadImage(`${D}oldfort_pre.jpg`),
    loadImage(`${D}oldfort_post.jpg`),
    loadImage(`${I}oldfort_wide.jpg`),
  ]);

  onProgress(0.4, "basemap");
  const map = new maplibregl.Map({
    container,
    style: await basemapStyle(),
    center: cameraAt(0).center,
    zoom: cameraAt(0).zoom,
    interactive: false,
    attributionControl: false,
    fadeDuration: 0,
    canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
    maxTileCacheSize: 20000,
    maxTileCacheZoomLevels: 20,
    refreshExpiredTiles: false,
  });
  await new Promise<void>((res) => map.once("load", () => res()));

  // Walk the camera path once, settling at each sample, so playback never
  // flies over a tile that is still parsing.
  const settle = (c: Cam, capMs: number) =>
    new Promise<void>((res) => {
      let fin = false;
      const done = () => {
        if (fin) return;
        fin = true;
        map.off("idle", check);
        clearTimeout(timer);
        res();
      };
      const check = () => {
        if (map.areTilesLoaded()) done();
      };
      const timer = setTimeout(done, capMs);
      map.on("idle", check);
      map.jumpTo(c);
    });
  // A viewer should not wait long for an intro: the default walk is coarse
  // (the tiles are local files and load in a frame or two anyway). Recording
  // uses the dense walk so not one frame flies over an unparsed tile.
  const step = dense ? 60 : 700;
  const path: Cam[] = [];
  for (let ms = 0; ms <= B.region.t1; ms += step) path.push(cameraAt(ms));
  for (let i = 0; i < path.length; i++) {
    await settle(path[i], dense ? 2000 : 500);
    if (i % 6 === 0) onProgress(0.45 + 0.55 * ((i + 1) / path.length), "map");
  }
  await settle(cameraAt(0), 2000);
  onProgress(1, "ready");

  return {
    assets: {
      radar: { manifest, images },
      ncOutline,
      structures: st.structures,
      areas,
      beforeImg,
      afterImg,
      wideImg,
      wideBounds: wide.bounds,
    },
    map,
  };
}
