// Phase H — bake every asset the /demo hook sequence needs into
// web/public/demo/ as static files. Run once (network required); after that
// the demo plays back with zero live calls.
//
//   node scripts/demo_fetch.mjs
//
// Produces:
//   public/demo/radar/00.png .. NN.png + manifest.json  (real archived NEXRAD,
//       Hurricane Helene crossing NC, 2024-09-26/27, from the IEM archive)
//   public/demo/nc-outline.json      (real NC state polygon)
//   public/demo/old_fort.geojson     (copy of the real 764-building assessment)
//   public/demo/sensors.json         (real NC flood + stream gauge locations)
//   public/demo/history.json         (real NC FEMA disaster declarations)
//   public/demo/aircraft.json        (real ADS-B point-in-time snapshot over NC —
//       Phase J "god's-eye" beat; re-run this script to refresh it)
//   public/demo/cameras.json         (real NCDOT DriveNC camera locations, from
//       the committed public/data/nc snapshot — Phase J)
//   public/demo/oldfort_pre.jpg / oldfort_post.jpg
//       (real Maxar Open Data imagery of Old Fort, stitched from the committed
//        tile pyramid at the exact camera the sequence uses)
//   public/demo/basemap/  (the CARTO dark-matter style + every vector tile,
//        glyph range and sprite the camera path crosses, so playback makes
//        ZERO network calls — see scripts/validate_demo.mjs)

import { mkdirSync, writeFileSync, readFileSync, existsSync, cpSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import puppeteer from "puppeteer-core";

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(__dirname, "..");
const OUT = resolve(WEB, "public/demo");
const DATA = resolve(WEB, "public/data");
const TILES = resolve(WEB, "public/tiles");
mkdirSync(OUT, { recursive: true });
mkdirSync(resolve(OUT, "radar"), { recursive: true });

const CHROME =
  process.env.CHROME_PATH ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

// ---- shared geography (keep in lockstep with src/demo/beats.ts) -------------
// Old Fort, McDowell County — the B3/B4/B5 camera.
const OLDFORT = { lon: -82.1804, lat: 35.6293, zoom: 16 };
// Phase J — 4K pass: stitched at z17 (real tile detail, not upscaled) over
// double the z16 pixel dimensions so the geographic extent — and therefore
// beats.ts OLDFORT_IMG_BOUNDS — is unchanged. Keep SHOT_W/H and stitchMaxar's
// internal zoom in lockstep with beats.ts's imgBounds(...) call.
const SHOT_W = 3200;
const SHOT_H = 2000;
// Beat-2 NEXRAD plate box in EPSG:3857. Deliberately WIDER than NC so Helene is
// seen sweeping in and out over GA / SC / TN / VA / the Atlantic with NC still
// the framed focus. MUST match RADAR_BBOX in src/demo/Stage.tsx.
const RADAR_BBOX4326 = [-88, 30, -74, 39.5];
const R = 6378137;
const merc = (lon, lat) => [
  (lon * Math.PI * R) / 180,
  R * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)),
];
const [ncX0, ncY0] = merc(RADAR_BBOX4326[0], RADAR_BBOX4326[1]);
const [ncX1, ncY1] = merc(RADAR_BBOX4326[2], RADAR_BBOX4326[3]);

const IEM_WMST =
  "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0r-t.cgi";
// Phase J — same keyless ADS-B endpoint as src/lib/nc.ts AIRCRAFT_URL, baked
// once instead of polled live (the hook makes zero network calls at playback).
const AIRCRAFT_URL = "https://api.adsb.lol/v2/point/35.55/-79.2/250";
const NC_BBOX = [-84.55, 33.75, -75.4, 36.7];

async function getBuf(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${url}`);
  return Buffer.from(await res.arrayBuffer());
}

// ---- 1. archived NEXRAD radar: Helene's approach + crossing of NC ----------
async function radar() {
  // late Sep 2024: storm rain shield moves across NC through the night of the
  // 26th into the 27th. One frame every 90 min.
  const start = Date.parse("2024-09-26T15:00:00Z");
  const end = Date.parse("2024-09-27T21:00:00Z");
  const step = 90 * 60 * 1000;
  const frames = [];
  let i = 0;
  for (let t = start; t <= end; t += step, i++) {
    const iso = new Date(t).toISOString().replace(/\.\d{3}Z$/, "Z");
    // match the EPSG:3857 bbox aspect so the reflectivity isn't squished
    const aspect = (ncX1 - ncX0) / (ncY1 - ncY0);
    const H = 720; // a touch higher-res since the plate now covers more ground
    const W = Math.round(H * aspect);
    const q = new URLSearchParams({
      SERVICE: "WMS",
      VERSION: "1.1.1",
      REQUEST: "GetMap",
      LAYERS: "nexrad-n0r-wmst",
      STYLES: "",
      FORMAT: "image/png",
      TRANSPARENT: "TRUE",
      SRS: "EPSG:3857",
      WIDTH: String(W),
      HEIGHT: String(H),
      TIME: iso,
      BBOX: `${ncX0},${ncY0},${ncX1},${ncY1}`,
    });
    const name = String(i).padStart(2, "0") + ".png";
    process.stdout.write(`  radar ${name}  ${iso} ... `);
    const buf = await getBuf(`${IEM_WMST}?${q.toString()}`);
    writeFileSync(resolve(OUT, "radar", name), buf);
    console.log(`${(buf.length / 1024) | 0} KB`);
    frames.push({
      file: `radar/${name}`,
      at: t,
      label: new Date(t).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZone: "America/New_York",
      }),
    });
  }
  writeFileSync(
    resolve(OUT, "radar/manifest.json"),
    JSON.stringify(
      { bbox3857: [ncX0, ncY0, ncX1, ncY1], bbox4326: RADAR_BBOX4326, frames },
      null,
      2,
    ),
  );
  console.log(`  ${frames.length} radar frames -> public/demo/radar/`);
}

// ---- 2. real NC state outline --------------------------------------------
async function ncOutline() {
  const src =
    "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json";
  const gj = JSON.parse((await getBuf(src)).toString());
  const nc = gj.features.find((f) => /north carolina/i.test(f.properties?.name ?? ""));
  if (!nc) throw new Error("NC not found in us-states.json");
  writeFileSync(
    resolve(OUT, "nc-outline.json"),
    JSON.stringify({ type: "FeatureCollection", features: [nc] }),
  );
  console.log("  nc-outline.json  ok");
}

// ---- 3/4. copy the real committed data ----------------------------------
// Phase J — a one-time real ADS-B point query over NC (same source as the
// live NCDashboard "god's-eye" aircraft layer, credited in About), downsampled
// to a deterministic, render-light set: [lon, lat, track_deg, isMilitary].
async function aircraft() {
  const res = await fetch(AIRCRAFT_URL);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${AIRCRAFT_URL}`);
  const raw = await res.json();
  const inNC = (lon, lat) =>
    lon >= NC_BBOX[0] && lon <= NC_BBOX[2] && lat >= NC_BBOX[1] && lat <= NC_BBOX[3];
  const pts = [];
  for (const a of raw.ac ?? []) {
    if (typeof a.lat !== "number" || typeof a.lon !== "number" || !inNC(a.lon, a.lat)) continue;
    const mil = ((a.dbFlags ?? 0) & 1) === 1 ? 1 : 0;
    const track = typeof a.track === "number" ? a.track : (a.nav_heading ?? 0);
    pts.push([+a.lon.toFixed(3), +a.lat.toFixed(3), +track.toFixed(1), mil]);
  }
  const step = Math.max(1, Math.floor(pts.length / 90));
  const sample = pts.filter((_, i) => i % step === 0);
  writeFileSync(resolve(OUT, "aircraft.json"), JSON.stringify(sample));
  console.log(`  aircraft.json  ${sample.length}/${pts.length} in-state aircraft`);
}

function copyData() {
  cpSync(resolve(DATA, "old_fort.geojson"), resolve(OUT, "old_fort.geojson"));
  console.log("  old_fort.geojson  copied");

  // Phase J — real NCDOT DriveNC camera locations (already a committed
  // snapshot for the main app's offline fallback); slimmed to [lon, lat].
  const cams = JSON.parse(readFileSync(resolve(DATA, "nc/ncdot_cameras_snapshot.geojson"), "utf8"));
  const camPts = cams.features
    .filter((f) => f.geometry?.type === "Point")
    .map((f) => [+f.geometry.coordinates[0].toFixed(4), +f.geometry.coordinates[1].toFixed(4)]);
  const camStep = Math.max(1, Math.floor(camPts.length / 500));
  const camSample = camPts.filter((_, i) => i % camStep === 0);
  writeFileSync(resolve(OUT, "cameras.json"), JSON.stringify(camSample));
  console.log(`  cameras.json  ${camSample.length}/${camPts.length} DOT cameras`);

  // trim the two gauge snapshots to id/lon/lat/kind/severity/title
  const pick = (path, kind) => {
    const gj = JSON.parse(readFileSync(path, "utf8"));
    return gj.features
      .filter((f) => f.geometry?.type === "Point")
      .map((f) => ({
        id: f.properties.id,
        kind,
        sev: f.properties.severity ?? 0,
        title: f.properties.title ?? "",
        lon: +f.geometry.coordinates[0].toFixed(4),
        lat: +f.geometry.coordinates[1].toFixed(4),
      }));
  };
  const sensors = [
    ...pick(resolve(DATA, "nc/nwps_snapshot.geojson"), "flood"),
    ...pick(resolve(DATA, "nc/nwis_snapshot.geojson"), "stream"),
  ].filter((s) => s.lon < -75 && s.lon > -85 && s.lat > 33 && s.lat < 37);
  writeFileSync(resolve(OUT, "sensors.json"), JSON.stringify(sensors));
  console.log(`  sensors.json  ${sensors.length} points`);

  // FEMA history -> the landmark storms for the B8 scrub
  const hist = JSON.parse(readFileSync(resolve(DATA, "nc/fema_history_snapshot.json"), "utf8"));
  const slim = hist
    .filter((d) => d.declarationDate)
    .map((d) => ({
      date: d.declarationDate.slice(0, 10),
      title: d.declarationTitle,
      type: d.incidentType,
      dr: d.declarationType === "DR",
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
  writeFileSync(resolve(OUT, "history.json"), JSON.stringify(slim));
  console.log(`  history.json  ${slim.length} declarations`);
}

// ---- 5. stitch the real Maxar tiles into pre/post stills ----------------
function tileXY(lon, lat, z) {
  const n = 2 ** z;
  const x = ((lon + 180) / 360) * n;
  const latR = (lat * Math.PI) / 180;
  const y = ((1 - Math.asinh(Math.tan(latR)) / Math.PI) / 2) * n;
  return { x, y };
}

async function stitchMaxar() {
  const z = 17; // Phase J 4K pass — see SHOT_W/H comment above
  const { x: cx, y: cy } = tileXY(OLDFORT.lon, OLDFORT.lat, z);
  // pixel position of the AOI centre within the world at this zoom
  const centrePxX = cx * 256;
  const centrePxY = cy * 256;
  const originPxX = centrePxX - SHOT_W / 2;
  const originPxY = centrePxY - SHOT_H / 2;
  const x0 = Math.floor(originPxX / 256);
  const y0 = Math.floor(originPxY / 256);
  const x1 = Math.floor((originPxX + SHOT_W) / 256);
  const y1 = Math.floor((originPxY + SHOT_H) / 256);

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: "new",
    args: ["--no-sandbox"],
  });
  try {
    for (const kind of ["pre", "post"]) {
      const cells = [];
      for (let tx = x0; tx <= x1; tx++) {
        for (let ty = y0; ty <= y1; ty++) {
          const p = resolve(TILES, `old_fort/${kind}/${z}/${tx}/${ty}.jpg`);
          if (!existsSync(p)) continue;
          const b64 = readFileSync(p).toString("base64");
          const left = tx * 256 - originPxX;
          const top = ty * 256 - originPxY;
          cells.push(
            `<img src="data:image/jpeg;base64,${b64}" style="position:absolute;left:${left}px;top:${top}px;width:256px;height:256px">`,
          );
        }
      }
      const html = `<!doctype html><meta charset=utf8><style>html,body{margin:0}#s{position:relative;width:${SHOT_W}px;height:${SHOT_H}px;background:#0f1115;overflow:hidden}</style><div id=s>${cells.join("")}</div>`;
      const page = await browser.newPage();
      await page.setViewport({ width: SHOT_W, height: SHOT_H, deviceScaleFactor: 1 });
      await page.setContent(html, { waitUntil: "networkidle0" });
      await page.$eval("#s", () => {});
      const el = await page.$("#s");
      // JPEG, not PNG: the source tiles are already JPEG, and at 3200x2000
      // a lossless PNG of satellite photography is ~11MB for no visible gain
      // over quality-92 JPEG (~1-2MB) — this is a page-load asset.
      await el.screenshot({ path: resolve(OUT, `oldfort_${kind}.jpg`), type: "jpeg", quality: 92 });
      await page.close();
      console.log(`  oldfort_${kind}.jpg  (${cells.length} tiles, z${z})`);
    }
  } finally {
    await browser.close();
  }
}

// ---- 6. self-host the basemap: style + every vector tile / glyph / sprite --
// the camera path crosses, so playback is fully offline. --------------------

// camera path (keep in lockstep with src/demo/beats.ts SEGS)
const easeOut = (t) => 1 - Math.pow(1 - t, 3);
const easeOutExpo = (t) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t));
const easeOutQuint = (t) => 1 - Math.pow(1 - t, 5);
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const lin = (t) => t;
const NC_C = [-79.2, 35.55];
const OF_C = [-82.1804, 35.6293];
const PATH = [
  { u: 2000, a: [[-80.6, 37.7], 4.7], b: [NC_C, 6.32], e: easeOutExpo },
  { u: 5200, a: [NC_C, 6.32], b: [NC_C, 6.42], e: lin },
  { u: 7000, a: [NC_C, 6.42], b: [OF_C, 16], e: easeOut },
  { u: 9200, a: [OF_C, 16], b: [OF_C, 16], e: lin },
  { u: 11200, a: [OF_C, 16], b: [OF_C, 16.4], e: easeInOut },
  { u: 13400, a: [OF_C, 16.4], b: [NC_C, 6.28], e: easeOutQuint },
];
const camAt = (ms) => {
  let t0 = 0;
  for (const s of PATH) {
    if (ms <= s.u || s === PATH[PATH.length - 1]) {
      const p = s.e(Math.max(0, Math.min(1, (ms - t0) / (s.u - t0))));
      return [
        [s.a[0][0] + (s.b[0][0] - s.a[0][0]) * p, s.a[0][1] + (s.b[0][1] - s.a[0][1]) * p],
        s.a[1] + (s.b[1] - s.a[1]) * p,
      ];
    }
    t0 = s.u;
  }
  return [NC_C, 6.28];
};
const lon2x = (lon, z) => Math.floor(((lon + 180) / 360) * 2 ** z);
const lat2y = (lat, z) =>
  Math.floor(
    ((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * 2 ** z,
  );

async function basemap() {
  const OUTB = resolve(OUT, "basemap");
  mkdirSync(OUTB, { recursive: true });
  const STYLE_URL = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
  const style = JSON.parse((await getBuf(STYLE_URL)).toString());

  // 6a. sprite (1x + 2x, .png + .json)
  mkdirSync(resolve(OUTB, "sprite-src"), { recursive: true });
  for (const suf of ["", "@2x"]) {
    for (const ext of ["png", "json"]) {
      const b = await getBuf(`${style.sprite}${suf}.${ext}`);
      writeFileSync(resolve(OUTB, `sprite${suf}.${ext}`), b);
    }
  }
  console.log("  basemap sprite  ok");

  // 6b. glyphs — every fontstack the style uses, ranges that cover US labels
  const stacks = new Set();
  for (const l of style.layers) {
    const f = l.layout && l.layout["text-font"];
    if (Array.isArray(f)) stacks.add(f.join(","));
  }
  const glyphTpl = style.glyphs;
  const glyphManifest = [];
  for (const stack of stacks) {
    const dir = resolve(OUTB, "glyphs", stack);
    mkdirSync(dir, { recursive: true });
    for (const range of ["0-255", "256-511", "8192-8447"]) {
      const url = glyphTpl
        .replace("{fontstack}", encodeURIComponent(stack))
        .replace("{range}", range);
      try {
        writeFileSync(resolve(dir, `${range}.pbf`), await getBuf(url));
        glyphManifest.push(`${stack}/${range}`);
      } catch {
        /* some ranges 404 — fine */
      }
    }
  }
  console.log(`  basemap glyphs  ${glyphManifest.length} files, ${stacks.size} fontstacks`);

  // 6c. vector tiles for the whole camera path
  const srcKey = Object.keys(style.sources)[0];
  const src = style.sources[srcKey];
  const tj = src.url ? JSON.parse((await getBuf(src.url)).toString()) : src;
  const tileTpl = (tj.tiles || src.tiles)[0];
  const maxZ = tj.maxzoom ?? 14;
  const minZ = tj.minzoom ?? 0;

  const want = new Set();
  for (let ms = 0; ms <= 13400; ms += 90) {
    const [[lon, lat], zoom] = camAt(ms);
    for (let dz = -1; dz <= 1; dz++) {
      const z = Math.max(minZ, Math.min(maxZ, Math.floor(zoom) + dz));
      // viewport half-span in degrees, generous margin for pitch/bearing
      const spanLon = ((360 / 2 ** z) * (SHOT_W / 512)) * 0.85;
      const spanLat = spanLon * 0.75;
      const x0t = lon2x(lon - spanLon, z);
      const x1t = lon2x(lon + spanLon, z);
      const y0t = lat2y(lat + spanLat, z);
      const y1t = lat2y(lat - spanLat, z);
      for (let x = x0t; x <= x1t; x++)
        for (let y = y0t; y <= y1t; y++) if (x >= 0 && y >= 0) want.add(`${z}/${x}/${y}`);
    }
  }
  let ok = 0;
  let bytes = 0;
  const list = [...want];
  const tileManifest = [];
  for (let i = 0; i < list.length; i += 24) {
    await Promise.all(
      list.slice(i, i + 24).map(async (k) => {
        const [z, x, y] = k.split("/");
        const url = tileTpl.replace("{z}", z).replace("{x}", x).replace("{y}", y);
        try {
          const b = await getBuf(url);
          const d = resolve(OUTB, "tiles", z, x);
          mkdirSync(d, { recursive: true });
          writeFileSync(resolve(d, `${y}.mvt`), b);
          ok++;
          bytes += b.length;
          tileManifest.push(`${z}/${x}/${y}`);
        } catch {
          /* edge tile 404 — MapLibre tolerates a missing tile */
        }
      }),
    );
    process.stdout.write(`\r  basemap tiles  ${ok}/${list.length}  (${(bytes / 1e6).toFixed(1)} MB)`);
  }
  console.log("");

  // 6c-2. the manifest src/demo/preload.ts reads to pull every one of these
  // files into the browser HTTP cache BEFORE playback is unlocked.
  tileManifest.sort();
  glyphManifest.sort();
  writeFileSync(
    resolve(OUTB, "tiles/manifest.json"),
    JSON.stringify({ generated: new Date().toISOString().slice(0, 10), tiles: tileManifest, glyphs: glyphManifest }),
  );
  console.log(`  basemap manifest  ${tileManifest.length} tiles + ${glyphManifest.length} glyph ranges`);

  // 6d. rewrite the style to point at the local files
  style.sprite = "__BASE__demo/basemap/sprite";
  style.glyphs = "__BASE__demo/basemap/glyphs/{fontstack}/{range}.pbf";
  style.sources[srcKey] = {
    type: "vector",
    tiles: ["__BASE__demo/basemap/tiles/{z}/{x}/{y}.mvt"],
    minzoom: minZ,
    maxzoom: maxZ,
  };
  writeFileSync(resolve(OUTB, "style.json"), JSON.stringify(style));
  console.log("  basemap style.json  ok  (__BASE__ placeholder resolved at load)");
}

console.log("Phase H demo assets ->", OUT);
await radar();
await ncOutline();
copyData();
await aircraft();
await stitchMaxar();
await basemap();
console.log("done.");
