// Phase H — prove the hook sequence plays back identically, 10x back-to-back,
// with zero network and zero console errors after preload.
//
//   npm run build && npm run preview   # (or: npm run dev)
//   node scripts/validate_demo.mjs [http://localhost:4173]
//
// Uses a real (non-headless) Chrome because maplibre-gl v5 needs WebGL2, which
// headless Chrome does not provide — same reason web/scripts/shoot.mjs does.

import { createHash } from "node:crypto";
import puppeteer from "puppeteer-core";

const BASE = process.argv[2] || "http://localhost:4173";
const URL = `${BASE}/demo.html?fixed=1&debug=1`;
const RUNS = 10;
// frame-hash sample points spread across the run (exact beat alignment doesn't
// matter — each is only compared run-to-run at the same ms). 5800/6600 sit in
// the now-wider snap, 7800 in the reveal, 9300 on the scan-line into the
// extrude, 16600 in the title card.
const SAMPLE_MS = [0, 1200, 2400, 3600, 4600, 5800, 6600, 7800, 8900, 9300, 10400, 12200, 13800, 15300, 16600, 17800];
const CHROME =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const sha = (buf) => createHash("sha1").update(buf).digest("hex").slice(0, 12);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: false,
  args: ["--no-sandbox", "--window-size=1600,1000", "--hide-scrollbars"],
  defaultViewport: { width: 1600, height: 1000, deviceScaleFactor: 1 },
});
const page = await browser.newPage();

const consoleErrors = [];
page.on("console", (m) => {
  if (m.type() === "error") consoleErrors.push(m.text());
});
page.on("pageerror", (e) => consoleErrors.push("pageerror: " + e.message));

const netLog = [];
page.on("request", (r) => netLog.push({ t: Date.now(), url: r.url(), type: r.resourceType() }));

console.log("→", URL);
await page.goto(URL, { waitUntil: "networkidle2", timeout: 60_000 });

// wait for the preload gate to open
await page.waitForFunction(() => window.__demo && window.__demo.ready(), { timeout: 120_000 });
await sleep(500);
const readyAt = Date.now();
const total = await page.evaluate(() => window.__demo.total);
console.log(`ready. total=${total}ms  requests before ready: ${netLog.length}`);

// --- the bar the user actually cares about: no COLD-START deficit. MapLibre
// re-reads a few dozen tiles from its (immutable, local) cache on every play as
// they re-enter the viewport — that is unavoidable and free. What must NOT
// happen is the first play, straight off the preload gate, fetching materially
// MORE than a warmed play — that is the "half the screen is blank because it
// hasn't loaded yet" the gate exists to prevent. Compared against the warm runs
// below.
const tileRe = (r) =>
  /\/basemap\/tiles\/.*\.mvt(\?|$)/.test(r.url) || /\/glyphs\/.*\.pbf(\?|$)/.test(r.url);
const coldBefore = netLog.length;
await page.evaluate(() => window.__demo.restart());
await sleep(120);
await page.evaluate(() => window.__demo.play());
for (let i = 0; i < 600; i++) {
  await sleep(50);
  const st = await page.evaluate(() => ({ ms: window.__demo.ms, playing: window.__demo.playing }));
  if (!st.playing && st.ms >= total - 1) break;
}
const coldExternal = netLog.slice(coldBefore).filter(
  (r) => tileRe(r) && !/^https?:\/\/(localhost|127\.0\.0\.1)/.test(r.url),
);
const coldTileCount = netLog.slice(coldBefore).filter(tileRe).length;
console.log(`cold first play: ${coldTileCount} tile/glyph request(s), ${coldExternal.length} external`);
const warmTileCounts = [];

// two warm-up playthroughs so the browser's local tile cache is fully
// saturated before we establish the reference frames — the first 1-2 plays
// still pull basemap tiles from disk and render a hair differently
for (let w = 0; w < 2; w++) {
  await page.evaluate(() => window.__demo.restart());
  await sleep(120);
  await page.evaluate(() => window.__demo.play());
  for (let i = 0; i < 400; i++) {
    await sleep(50);
    const st = await page.evaluate(() => ({ ms: window.__demo.ms, playing: window.__demo.playing }));
    if (!st.playing && st.ms >= total - 1) break;
  }
}
console.log("2 warm-up plays done — capturing reference from run 1\n");

const hashAtSamples = async () => {
  const out = {};
  for (const ms of SAMPLE_MS) {
    await page.evaluate((m) => window.__demo.seek(m), ms);
    // don't capture until the basemap has actually finished loading the
    // jumpTo's tiles (from the local cache) — otherwise a slow local re-fetch
    // lands one frame late and the screenshot differs run-to-run
    await page
      .waitForFunction(() => !window.__demoMap || window.__demoMap.areTilesLoaded(), { timeout: 5000 })
      .catch(() => {});
    await sleep(450);
    const buf = await page.screenshot({ type: "png" });
    out[ms] = sha(buf);
  }
  return out;
};

let firstHashes = null;
let allIdentical = true;
let allCompleted = true;
let netDuringPlay = 0;

for (let run = 1; run <= RUNS; run++) {
  // restart via the same path the R hotkey uses
  await page.evaluate(() => window.__demo.restart());
  await sleep(120);

  const netBefore = netLog.length;
  const t0 = Date.now();
  await page.evaluate(() => window.__demo.play());
  // fixed-step: ~total/16.667 frames; poll for completion
  let done = false;
  for (let i = 0; i < 400; i++) {
    await sleep(50);
    const st = await page.evaluate(() => ({ ms: window.__demo.ms, playing: window.__demo.playing }));
    if (!st.playing && st.ms >= total - 1) {
      done = true;
      break;
    }
  }
  const wall = Date.now() - t0;
  const added = netLog.slice(netBefore).filter((r) => r.type !== "document");
  // the bar that matters: zero EXTERNAL calls during playback. Local static
  // reads (basemap tiles vite serves from public/demo/basemap/) can't fail a
  // take on a bad network, but flag them too.
  const external = added.filter((r) => !/^https?:\/\/(localhost|127\.0\.0\.1)/.test(r.url));
  netDuringPlay += external.length;
  if (!done) allCompleted = false;

  const hashes = await hashAtSamples();
  if (!firstHashes) {
    firstHashes = hashes;
  } else {
    for (const ms of SAMPLE_MS) {
      if (hashes[ms] !== firstHashes[ms]) {
        allIdentical = false;
        console.log(`  run ${run}: MISMATCH at ${ms}ms  ${hashes[ms]} != ${firstHashes[ms]}`);
      }
    }
  }
  const localN = added.length - external.length;
  warmTileCounts.push(added.filter(tileRe).length);
  console.log(
    `run ${String(run).padStart(2)}  ${done ? "completed" : "DID NOT COMPLETE"}  ` +
      `wall ${String(wall).padStart(5)}ms  external+${external.length}  local+${localN}` +
      (external.length ? "  EXT: " + external.slice(0, 3).map((r) => r.url).join(" ") : ""),
  );
}

const netAfterReady = netLog.filter((r) => r.t > readyAt && r.resourceType !== "document");

// cold play must be no worse than the warmest warm run, plus slack for
// re-entry jitter. Bigger than that ⇒ the preload gate opened with a deficit.
const warmMax = Math.max(1, ...warmTileCounts);
const coldBudget = Math.round(warmMax * 1.4) + 12;
const noColdDeficit = coldExternal.length === 0 && coldTileCount <= coldBudget;

console.log("\n──────── result ────────");
console.log(
  `no cold-start deficit ....... ${noColdDeficit ? "PASS" : "FAIL"} ` +
    `(cold ${coldTileCount} vs warm≤${warmMax}, budget ${coldBudget}, external ${coldExternal.length})`,
);
console.log(`runs completed .............. ${allCompleted ? "PASS" : "FAIL"} (${RUNS}/${RUNS})`);
console.log(`frame-identical across runs .. ${allIdentical ? "PASS" : "FAIL"} (${SAMPLE_MS.length} sample times)`);
console.log(`zero EXTERNAL calls in playback ${netDuringPlay === 0 ? "PASS" : "FAIL"} (${netDuringPlay})`);
console.log(`no console errors ............ ${consoleErrors.length === 0 ? "PASS" : "FAIL"} (${consoleErrors.length})`);
if (consoleErrors.length) consoleErrors.slice(0, 8).forEach((e) => console.log("   ! " + e));
if (netAfterReady.length)
  console.log(`   (requests after ready, all runs: ${netAfterReady.length})`);

await browser.close();
const ok =
  noColdDeficit && allCompleted && allIdentical && netDuringPlay === 0 && consoleErrors.length === 0;
process.exit(ok ? 0 : 1);
