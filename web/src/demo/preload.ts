/**
 * Phase H — gate playback behind a full preload. Nothing in the sequence runs
 * until every asset it touches is already in memory AND the basemap tiles for
 * the whole camera path are already in MapLibre's tile cache.
 *
 * Everything here is served from the app's own origin (public/demo/, public/
 * tiles/) or from the CARTO basemap CDN the app already depends on. During
 * playback there are zero further requests — see scripts/validate_demo.mjs.
 */
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { WARMUP_CAMS, OLDFORT, cameraAt } from "./beats";

const BASE = import.meta.env.BASE_URL;
const D = `${BASE}demo/`;

export interface RadarFrame {
  file: string;
  at: number;
  label: string;
}
export interface RadarManifest {
  bbox4326: [number, number, number, number];
  bbox3857: [number, number, number, number];
  frames: RadarFrame[];
}
export interface Sensor {
  id: string;
  kind: "flood" | "stream";
  sev: number;
  title: string;
  lon: number;
  lat: number;
}
export interface HistoryRow {
  date: string;
  title: string;
  type: string;
  dr: boolean;
}

export interface DemoAssets {
  radar: { manifest: RadarManifest; images: HTMLImageElement[] };
  oldFort: GeoJSON.FeatureCollection;
  ncOutline: GeoJSON.FeatureCollection;
  sensors: Sensor[];
  history: HistoryRow[];
  beforeImg: HTMLImageElement;
  afterImg: HTMLImageElement;
  logo: HTMLImageElement;
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

// A fully self-hosted copy of the CARTO dark-matter style — every vector tile,
// glyph and sprite the camera path crosses lives under public/demo/basemap/
// (baked by scripts/demo_fetch.mjs). Playback makes zero network calls.
async function loadBasemapStyle(): Promise<maplibregl.StyleSpecification> {
  const txt = await (await fetch(`${D}basemap/style.json`)).text();
  // MapLibre loads vector tiles in a Web Worker where `new URL(relative)`
  // throws — the tile/glyph/sprite URLs must be absolute.
  const abs = new URL(BASE, location.href).href;
  return JSON.parse(txt.replaceAll("__BASE__", abs)) as maplibregl.StyleSpecification;
}

export interface PreloadResult {
  assets: DemoAssets;
  map: maplibregl.Map;
  tilesWarmed: number;
}

/**
 * @param container the (hidden) node the live demo map will live in
 * @param onProgress 0..1
 */
export async function preload(
  container: HTMLDivElement,
  onProgress: (p: number, label: string) => void,
): Promise<PreloadResult> {
  const steps = 7;
  let done = 0;
  const tick = (label: string) => onProgress(++done / steps, label);

  onProgress(0, "manifest");
  const manifest = await loadJSON<RadarManifest>(`${D}radar/manifest.json`);
  tick("radar frames");

  const [images, oldFort, ncOutline, sensors, history] = await Promise.all([
    Promise.all(manifest.frames.map((f) => loadImage(`${D}${f.file}`))),
    loadJSON<GeoJSON.FeatureCollection>(`${D}old_fort.geojson`),
    loadJSON<GeoJSON.FeatureCollection>(`${D}nc-outline.json`),
    loadJSON<Sensor[]>(`${D}sensors.json`),
    loadJSON<HistoryRow[]>(`${D}history.json`),
  ]);
  tick("imagery");

  const [beforeImg, afterImg, logo, basemapStyle] = await Promise.all([
    loadImage(`${D}oldfort_pre.png`),
    loadImage(`${D}oldfort_post.png`),
    loadImage(`${D}ncrecon-logo-dark.svg`),
    loadBasemapStyle(),
  ]);
  tick("basemap");

  // --- build the real demo map, hidden. `preserveDrawingBuffer` keeps the
  // WebGL backbuffer readable between renders, which a recording/screenshot
  // capture needs; `maxTileCacheSize` high so the warmup below is not undone.
  const map = new maplibregl.Map({
    container,
    style: basemapStyle,
    center: OLDFORT,
    zoom: 16,
    interactive: false,
    attributionControl: false,
    fadeDuration: 0,
    // keep the WebGL backbuffer readable between renders (recording/screenshots)
    canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
    // the path crosses z5→16; hold onto everything so a pull-back never re-reads
    // a low-zoom tile that a close-up evicted
    maxTileCacheSize: 20000,
    maxTileCacheZoomLevels: 20,
    refreshExpiredTiles: false,
  });
  await new Promise<void>((res) => map.once("load", () => res()));
  tick("warm basemap");

  // The Old Fort imagery is a stitched still drawn by a deck.gl BitmapLayer
  // (see Stage.tsx) — no map raster source, so nothing to warm here.

  // --- step the ACTUAL keyframe cameras (not a flyTo sweep) and wait for idle
  const idle = () =>
    new Promise<void>((res) => {
      if (map.areTilesLoaded()) return res();
      const on = () => {
        if (map.areTilesLoaded()) {
          map.off("idle", on);
          res();
        }
      };
      map.on("idle", on);
      // hard cap so a stuck tile can't wedge the loader
      setTimeout(() => {
        map.off("idle", on);
        res();
      }, 4000);
    });

  const seen = new Set<string>();
  map.on("data", (e: { tile?: { tileID?: { key?: unknown } }; sourceId?: string }) => {
    if (e.tile?.tileID?.key != null) seen.add(`${e.sourceId}:${e.tile.tileID.key}`);
  });
  const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

  // pass 1: walk the whole camera path quickly to fire every tile request the
  // playback will make; MapLibre loads them in parallel into the (huge) cache
  for (let i = 0; i < WARMUP_CAMS.length; i++) {
    const c = WARMUP_CAMS[i];
    map.jumpTo({ center: c.center, zoom: c.zoom, pitch: c.pitch, bearing: c.bearing });
    await sleep(70);
    if (i % 6 === 0) await idle();
    onProgress(0.72 + (0.2 * (i + 1)) / WARMUP_CAMS.length, `warming ${i + 1}/${WARMUP_CAMS.length}`);
  }
  // pass 2: settle at each beat's hold camera so nothing is still in flight
  for (const ms of [200, 3600, 6900, 8000, 10200, 13400]) {
    const c = cameraAt(ms);
    map.jumpTo({ center: c.center, zoom: c.zoom, pitch: c.pitch, bearing: c.bearing });
    await idle();
  }
  const tilesWarmed = seen.size;

  const first = WARMUP_CAMS[0];
  map.jumpTo({ center: first.center, zoom: first.zoom, pitch: 0, bearing: 0 });
  await idle();
  tick("ready");

  return {
    assets: { radar: { manifest, images }, oldFort, ncOutline, sensors, history, beforeImg, afterImg, logo },
    map,
    tilesWarmed,
  };
}
