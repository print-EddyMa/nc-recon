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
import { BEATS, OLDFORT, cameraAt, type Cam } from "./beats";

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

interface TileManifest {
  tiles: string[];
  glyphs: string[];
}

/**
 * Pull every baked basemap tile + glyph range into the browser HTTP cache
 * BEFORE the map is even built. During playback MapLibre re-requests these from
 * its Web Worker; with the bytes already cached each request is an instant hit
 * (a ~1ms 304 on the dev server), so the camera never flies over a tile that is
 * still downloading. `demo_fetch.mjs` writes the manifest from the exact set it
 * bakes — see scripts/demo_fetch.mjs §6c.
 */
async function prewarmHttpCache(onStep: (frac: number) => void): Promise<number> {
  let manifest: TileManifest;
  try {
    manifest = await loadJSON<TileManifest>(`${D}basemap/tiles/manifest.json`);
  } catch {
    // no manifest baked yet — the warm/verify passes below still gate playback,
    // just without the HTTP-cache head start
    return 0;
  }
  const urls = [
    ...manifest.tiles.map((t) => `${D}basemap/tiles/${t}.mvt`),
    ...manifest.glyphs.map((g) => `${D}basemap/glyphs/${g}.pbf`),
  ];
  let done = 0;
  const BATCH = 48;
  for (let i = 0; i < urls.length; i += BATCH) {
    await Promise.all(
      urls.slice(i, i + BATCH).map((u) =>
        fetch(u)
          .then((r) => r.arrayBuffer())
          .catch(() => {})
          .finally(() => {
            done++;
          }),
      ),
    );
    onStep(done / urls.length);
  }
  return urls.length;
}

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
  /** how many verification laps it took to get a clean pass (0 = budget hit) */
  verifyLaps: number;
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * @param container the (hidden) node the live demo map will live in
 * @param onProgress 0..1
 */
export async function preload(
  container: HTMLDivElement,
  onProgress: (p: number, label: string) => void,
): Promise<PreloadResult> {
  // progress is carved into weighted phases so the bar tracks real work:
  // fonts+data 0→12%, http-cache prewarm 12→40%, style+map 40→50%,
  // warm walk 50→82%, verification lap 82→100%.
  const phase = (lo: number, hi: number) => (f: number, label: string) =>
    onProgress(lo + (hi - lo) * Math.max(0, Math.min(1, f)), label);

  // 0. fonts — the stage CSS @imports Geist/Geist Mono from Google Fonts; wait
  // for them here so no lower-third or telemetry text reflows mid-sequence.
  onProgress(0, "fonts");
  await Promise.race([
    (document as Document & { fonts?: { ready?: Promise<unknown> } }).fonts?.ready ?? Promise.resolve(),
    sleep(4000),
  ]);

  // 1. data + imagery
  const manifest = await loadJSON<RadarManifest>(`${D}radar/manifest.json`);
  phase(0, 0.12)(0.3, "data");
  const [images, oldFort, ncOutline, sensors, history] = await Promise.all([
    Promise.all(manifest.frames.map((f) => loadImage(`${D}${f.file}`))),
    loadJSON<GeoJSON.FeatureCollection>(`${D}old_fort.geojson`),
    loadJSON<GeoJSON.FeatureCollection>(`${D}nc-outline.json`),
    loadJSON<Sensor[]>(`${D}sensors.json`),
    loadJSON<HistoryRow[]>(`${D}history.json`),
  ]);
  const [beforeImg, afterImg, logo] = await Promise.all([
    loadImage(`${D}oldfort_pre.png`),
    loadImage(`${D}oldfort_post.png`),
    loadImage(`${D}ncrecon-logo-dark.svg`),
  ]);
  phase(0, 0.12)(1, "data");

  // 2. pull EVERY baked basemap tile + glyph into the HTTP cache up front
  const prewarmProg = phase(0.12, 0.4);
  const prewarmed = await prewarmHttpCache((f) => prewarmProg(f, "caching basemap"));

  // 3. style + hidden map
  const basemapStyle = await loadBasemapStyle();
  phase(0.4, 0.5)(0.4, "basemap");
  // `preserveDrawingBuffer` keeps the WebGL backbuffer readable between renders
  // (recording/screenshots need it); the big tile cache means a close-up push
  // never evicts a low-zoom tile the later pull-back reuses.
  const map = new maplibregl.Map({
    container,
    style: basemapStyle,
    center: OLDFORT,
    zoom: 16,
    interactive: false,
    attributionControl: false,
    fadeDuration: 0,
    canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
    maxTileCacheSize: 20000,
    maxTileCacheZoomLevels: 20,
    refreshExpiredTiles: false,
  });
  await new Promise<void>((res) => map.once("load", () => res()));
  phase(0.4, 0.5)(1, "basemap");

  // The Old Fort imagery is a stitched still drawn by a deck.gl BitmapLayer
  // (see Stage.tsx) — no map raster source, so nothing to warm here.

  // count every tile that finishes parsing into MapLibre's own cache
  const seen = new Set<string>();
  map.on("data", (e: { tile?: { tileID?: { key?: unknown } }; sourceId?: string }) => {
    if (e.tile?.tileID?.key != null) seen.add(`${e.sourceId}:${e.tile.tileID.key}`);
  });

  // The playback camera path, sampled every 60ms across the whole map-visible
  // span (0 → end of the flood beat; B7/B8 only hold statewide, B9 hides the
  // map). 60ms is tight enough that even the fast B3 swoop / B6 pull-back can't
  // skip an integer zoom level between samples — the old 120ms sampling did,
  // which is how z8/z11 tiles never got warmed and the frame flew over black.
  const PATH: Cam[] = [];
  for (let ms = 0; ms <= BEATS[6].t1; ms += 60) PATH.push(cameraAt(ms));

  // Move to a camera and wait until MapLibre is genuinely idle THERE — i.e. the
  // NEXT idle event after this jump, not whatever stale state a sync check would
  // see one tick after jumpTo. `idle` already implies "all requested tiles
  // loaded"; the areTilesLoaded() re-check is just belt-and-braces. capMs only
  // bounds a genuinely wedged tile.
  const jumpAndSettle = (c: Cam, capMs: number) =>
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
      map.jumpTo({ center: c.center, zoom: c.zoom, pitch: c.pitch, bearing: c.bearing });
    });

  // 4. warm pass — walk the dense path once, dwelling until idle at each step so
  // every tile the playback camera will cross is fetched (from the primed HTTP
  // cache) and parsed into MapLibre's own tile cache.
  const warmProg = phase(0.5, 0.82);
  for (let i = 0; i < PATH.length; i++) {
    await jumpAndSettle(PATH[i], 2000);
    if (i % 8 === 0) warmProg((i + 1) / PATH.length, `warming ${i + 1}/${PATH.length}`);
  }

  // 5. verification lap — re-walk the whole path and require a lap that loads
  // NOT ONE new tile: the honest signal that everything the run touches is
  // already resident. The `seen`-set delta is the gate (it needs no tile to
  // reach a terminal state); areTilesLoaded() is only logged. Retry a couple of
  // times, bounded, so a genuinely wedged tile can't hang the gate forever.
  const verifyProg = phase(0.82, 1);
  const VERIFY_BUDGET_MS = 12000;
  const vStart = performance.now();
  let verifyLaps = 0; // stays 0 until a lap comes back genuinely clean
  for (let lap = 1; lap <= 3; lap++) {
    const before = seen.size;
    let allLoaded = true;
    for (let i = 0; i < PATH.length; i++) {
      await jumpAndSettle(PATH[i], 1500);
      if (!map.areTilesLoaded()) allLoaded = false;
      if (i % 8 === 0) verifyProg((lap - 1 + (i + 1) / PATH.length) / 3, `verifying ${lap}·${i + 1}`);
    }
    if (seen.size === before) {
      verifyLaps = lap;
      break;
    }
    if (performance.now() - vStart > VERIFY_BUDGET_MS) {
      console.warn(
        `[demo] preload verification hit its ${VERIFY_BUDGET_MS}ms budget after ${lap} lap(s); ` +
          `${seen.size - before} tile(s) still resolving (areTilesLoaded=${allLoaded}) — ` +
          `the first playthrough may show brief pop-in (a second play is always clean)`,
      );
      break;
    }
  }

  // 6. park on the opening frame, fully painted
  await jumpAndSettle({ ...PATH[0], pitch: 0, bearing: 0 }, 2500);
  onProgress(1, prewarmed ? `ready · ${seen.size} tiles` : "ready");

  return {
    assets: { radar: { manifest, images }, oldFort, ncOutline, sensors, history, beforeImg, afterImg, logo },
    map,
    tilesWarmed: seen.size,
    verifyLaps,
  };
}
