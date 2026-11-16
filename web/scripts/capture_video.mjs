// Generic frame-accurate capture harness for the shot-list clips.
// Drives the app via ?rec=1 (exposes window.__ttMap, see lib/useMapLibre.ts)
// and screenshots one PNG per output frame so ffmpeg can stitch a
// jitter-free 3840x2160/24fps mov, matching the closing render's specs.
//
// usage: node scripts/capture_video.mjs <beat> [outDir]
import { mkdirSync } from "node:fs";
import puppeteer from "puppeteer-core";

const BEAT = process.argv[2];
const OUT = process.argv[3] || `/private/tmp/claude-501/-Users-eddyma/65537aee-f864-4055-8c12-fdb067d7d77a/scratchpad/frames/${BEAT}`;
const BASE = "http://localhost:4173";
const FPS = 24;
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: false,
  args: ["--no-sandbox", "--window-size=1960,1180", "--hide-scrollbars"],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 2 },
});
const page = await browser.newPage();
page.on("pageerror", (e) => console.log("  pageerror:", e.message));

let frameIdx = 0;
async function shot() {
  const name = `f_${String(frameIdx).padStart(5, "0")}.png`;
  await page.screenshot({ path: `${OUT}/${name}` });
  frameIdx++;
  if (frameIdx % 24 === 0) console.log("wrote", name);
}

async function waitTilesSettled() {
  await page
    .waitForFunction(() => !window.__ttMap || window.__ttMap.areTilesLoaded(), { timeout: 4000 })
    .catch(() => {});
}

/** Ease-in-out camera pan/zoom over `ms`, one jumpTo() + screenshot per output frame. */
async function panCamera(from, to, ms, ease = (t) => t * t * (3 - 2 * t)) {
  const n = Math.round((ms / 1000) * FPS);
  for (let i = 0; i <= n; i++) {
    const t = ease(i / n);
    const cam = {
      center: [
        from.center[0] + (to.center[0] - from.center[0]) * t,
        from.center[1] + (to.center[1] - from.center[1]) * t,
      ],
      zoom: from.zoom + (to.zoom - from.zoom) * t,
      bearing: (from.bearing ?? 0) + ((to.bearing ?? 0) - (from.bearing ?? 0)) * t,
      pitch: (from.pitch ?? 0) + ((to.pitch ?? 0) - (from.pitch ?? 0)) * t,
    };
    await page.evaluate((c) => window.__ttMap && window.__ttMap.jumpTo(c), cam);
    await sleep(30);
    await shot();
  }
  return to;
}

/** Hold the current frame for `ms` (repeats real screenshots; state is static). */
async function hold(ms) {
  const n = Math.round((ms / 1000) * FPS);
  for (let i = 0; i < n; i++) await shot();
}

async function clickByText(selector, text) {
  return page.evaluate(
    (sel, txt) => {
      const el = [...document.querySelectorAll(sel)].find((x) =>
        (x.textContent || "").toLowerCase().includes(txt.toLowerCase()),
      );
      if (!el) return false;
      const input = el.tagName === "INPUT" ? el : el.querySelector("input");
      (input || el).click();
      return true;
    },
    selector,
    text,
  );
}

async function setSlider(selector, value01) {
  await page.evaluate(
    (sel, v) => {
      const input = document.querySelector(sel);
      if (!input) return false;
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(input, String(Math.round(v * 100)));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      return true;
    },
    selector,
    value01,
  );
}

/** ease assessment 0->1 over `ms` (React-controlled range input, one dispatch + screenshot per frame). */
async function animateSlider(selector, from, to, ms, ease = (t) => t * t * (3 - 2 * t)) {
  const n = Math.round((ms / 1000) * FPS);
  for (let i = 0; i <= n; i++) {
    await setSlider(selector, from + (to - from) * ease(i / n));
    await sleep(20);
    await shot();
  }
}

async function clickAtLngLat(lon, lat) {
  const pt = await page.evaluate(
    (lo, la) => {
      if (!window.__ttMap) return null;
      const p = window.__ttMap.project([lo, la]);
      return { x: p.x, y: p.y };
    },
    lon,
    lat,
  );
  if (!pt) return false;
  await page.mouse.click(pt.x, pt.y);
  return true;
}

const OLD_FORT_CENTER = [-82.1804, 35.6293];
const RED_BUILDING = [-82.180765, 35.631443]; // old_fort-000371, destroyed, high-confidence

// ---------------------------------------------------------------------------

if (BEAT === "beat03") {
  await page.goto(`${BASE}/?rec=1#/monitor`, { waitUntil: "networkidle2" });
  await page.waitForFunction(() => window.__ttMap, { timeout: 30_000 });
  await sleep(1200);
  await waitTilesSettled();

  // 1) pan the statewide map
  const camA = { center: [-80.6, 34.9], zoom: 6.6, bearing: 0, pitch: 0 };
  const camB = { center: [-77.6, 36.1], zoom: 6.9, bearing: 0, pitch: 0 };
  await page.evaluate((c) => window.__ttMap && window.__ttMap.jumpTo(c), camA);
  await sleep(400);
  await waitTilesSettled();
  await panCamera(camA, camB, 3200);

  // 2) toggle a couple of left-rail layers: flood forecast, NWS alerts
  // (both default ON, so off->on shows real motion and ends in the pitch-good state)
  // Timings sized to the CAC "Before the storm" VO (21 words @ 150wpm = 8.4s).
  await clickByText("label", "river flood forecast"); // off
  await sleep(200);
  await hold(600);
  await clickByText("label", "river flood forecast"); // on
  await sleep(200);
  await hold(900);
  await clickByText("label", "official alerts"); // off
  await sleep(200);
  await hold(600);
  await clickByText("label", "official alerts"); // on
  await sleep(200);
  await hold(900);

  // 3) hold on the right panel ranking risk
  await hold(3200);
} else if (BEAT === "beat04") {
  await page.goto(`${BASE}/?rec=1#/a/old_fort/map`, { waitUntil: "networkidle2" });
  await page.waitForFunction(() => window.__ttMap, { timeout: 30_000 });
  await sleep(800);

  // start flat: imagery only, no 3-D
  await page.evaluate((c) => window.__ttMap.jumpTo(c), {
    center: OLD_FORT_CENTER,
    zoom: 15.2,
    pitch: 0,
    bearing: 0,
  });
  await setSlider(".ba-range", 0);
  await sleep(500);
  await waitTilesSettled();
  await hold(500);

  // the before/after slider snaps imagery -> full 3-D damage model, extrusion
  // rising as pitch eases in alongside it
  const n = Math.round((1300 / 1000) * FPS);
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const ease = t * t * (3 - 2 * t);
    await setSlider(".ba-range", ease);
    await page.evaluate(
      (p) => window.__ttMap.jumpTo({ center: p.center, zoom: p.zoom, bearing: 0, pitch: p.pitch }),
      { center: OLD_FORT_CENTER, zoom: 15.2, pitch: 55 * ease },
    );
    await sleep(20);
    await shot();
  }
  await hold(500);

  // rotate the camera around the 3-D extrusion
  await panCamera(
    { center: OLD_FORT_CENTER, zoom: 15.2, pitch: 55, bearing: 0 },
    { center: OLD_FORT_CENTER, zoom: 15.2, pitch: 55, bearing: 130 },
    3000,
    (t) => t, // linear - a steady sweep, not an ease-snap
  );
  await hold(400);

  // recenter on the target building before clicking - project() is accurate
  // anywhere on screen, but GPU picking on a *neighboring* extrusion at
  // pitch 55 is easy to miss by parallax if it isn't near screen center
  await page.evaluate(
    (c) => window.__ttMap.jumpTo(c),
    { center: RED_BUILDING, zoom: 15.2, pitch: 55, bearing: 130 },
  );
  await sleep(300);
  await shot();

  // click one building, hold on its score card
  const clicked = await clickAtLngLat(...RED_BUILDING);
  console.log("clicked building:", clicked);
  await sleep(500);
  await hold(2200);
} else if (BEAT === "ic04") {
  // "Why It Matters": its own live take, not a crop of beat04 -
  // wide on the field, then a slow push-in on the red building.
  // Timings sized to the Idea Challenge VO (41 words @ 150wpm = 16.4s):
  //   "That's the difference... day 4."        6.8s -> wide hold
  //   "That's the difference... disaster."      6.0s -> the push-in
  //   "For the family... everything."           3.6s -> tight on the building
  await page.goto(`${BASE}/?rec=1#/a/old_fort/map`, { waitUntil: "networkidle2" });
  await page.waitForFunction(() => window.__ttMap, { timeout: 30_000 });
  await sleep(800);
  await setSlider(".ba-range", 1); // scene already at full 3-D, per the shot list
  const wide = { center: OLD_FORT_CENTER, zoom: 14.6, pitch: 50, bearing: 20 };
  await page.evaluate((c) => window.__ttMap.jumpTo(c), wide);
  await sleep(400);
  await waitTilesSettled();
  await hold(6800);

  await panCamera(wide, { center: RED_BUILDING, zoom: 19, pitch: 68, bearing: 20 }, 6000, (t) =>
    t * t * (3 - 2 * t),
  );
  await hold(3600);
} else if (BEAT === "beat05") {
  // Timings sized to the CAC "Validation" VO (36 words @ 150wpm = 14.4s):
  //   "A wrong guess... that collapsed."          6.8s -> hold on the hero + confidence split
  //   "NC Recon runs two independent models..."   4.0s -> browse into the flagged rows
  //   "Low-confidence scans are flagged..."        3.6s -> settle on a disagreeing row
  await page.goto(`${BASE}/?rec=1#/a/old_fort/review`, { waitUntil: "networkidle2" });
  await sleep(1200);
  await hold(6800);

  const n = Math.round((2500 / 1000) * FPS);
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const ease = t * t * (3 - 2 * t);
    await page.evaluate((y) => window.scrollTo(0, y), 460 * ease);
    await sleep(20);
    await shot();
  }
  await sleep(500); // let the newly-revealed pre/post crop <img> tags finish loading
  await hold(4600);
} else if (BEAT === "beat06-artifact") {
  // Timings sized to the CAC "How it's built" VO (36 words @ 150wpm = 14.4s).
  const artifactPath = process.env.ARTIFACT_HTML;
  const scrollMs = Number(process.env.SCROLL_MS || 12000);
  await page.goto(`file://${artifactPath}`, { waitUntil: "networkidle2" });
  await sleep(1500); // let the count-up/reveal animations settle
  const height = await page.evaluate(() => document.body.scrollHeight - window.innerHeight);
  console.log("scrollable height:", height, "scrollMs:", scrollMs);
  await hold(900);
  const n = Math.round((scrollMs / 1000) * FPS);
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; // smooth in-out
    await page.evaluate((y) => window.scrollTo(0, y), height * ease);
    await sleep(15);
    await shot();
  }
  await hold(1500);
} else if (BEAT === "beat04v2") {
  // Full VO-timed take: Assess screen (click -> event -> run) into the
  // damage map (slider -> extrusion -> rotate -> building click).
  // Segment lengths derived from the CAC "After the storm" VO word count
  // (~87 words @ 150wpm = 34.8s), +buffer for the un-narrated score-card beat.
  await page.goto(`${BASE}/?rec=1#/assess`, { waitUntil: "networkidle2" });
  await page.waitForFunction(() => window.__ttMap, { timeout: 30_000 });
  await sleep(1000);
  await waitTilesSettled();

  // P1 (~9s) - "After the storm... so we skip the road." wide establishing
  // pan across the NC AOI coverage, before any interaction.
  const wideA = { center: [-82.6, 35.75], zoom: 8.3, bearing: 0, pitch: 0 };
  const wideB = { center: [-81.9, 35.55], zoom: 8.7, bearing: 0, pitch: 0 };
  await page.evaluate((c) => window.__ttMap.jumpTo(c), wideA);
  await sleep(300);
  await hold(700);
  await panCamera(wideA, wideB, 9200, (t) => t);

  // P2 (~11s) - "Point NC Recon at an area... spot damage." click, confirm
  // the picked event, run it.
  const clicked = await clickAtLngLat(...OLD_FORT_CENTER);
  console.log("assess: clicked point", clicked);
  await sleep(500);
  await waitTilesSettled();
  await hold(2200);
  // Name the AOI "Old Fort" - the server keys the assessed-area slug off this
  // field (not proximity), so this is what makes "Assess this area" resolve
  // instantly via the existing old_fort.geojson instead of kicking off a
  // real, brand-new pipeline run (fetch + infer + tile) against Maxar.
  await page.evaluate(() => {
    const input = document.querySelector("aside input");
    if (!input) return;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    setter.call(input, "Old Fort");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await sleep(300);
  await hold(700);
  const evText = await page.evaluate(() => document.querySelector("aside select")?.selectedOptions?.[0]?.textContent ?? null);
  console.log("assess: picked event ->", evText);
  await hold(500);
  const ranClick = await page.evaluate(() => {
    const b = [...document.querySelectorAll("aside button")].find((x) => /assess this area/i.test(x.textContent || ""));
    if (!b || b.disabled) return false;
    b.click();
    return true;
  });
  console.log("assess: clicked run ->", ranClick);
  await hold(3600); // the real "already assessed" resolve, held for pacing

  // P3 (~3s) - "Watch: Old Fort, McDowell County." jump to the results.
  await page.evaluate(() => {
    location.hash = "#/a/old_fort/map";
  });
  await sleep(1200);
  await page.waitForFunction(() => window.__ttMap, { timeout: 15_000 });
  await waitTilesSettled();
  await hold(1600);

  // P4 (~4s) - "764 buildings, scored in about a minute on a laptop."
  // before/after slider snaps imagery -> full 3-D damage model.
  await page.evaluate((c) => window.__ttMap.jumpTo(c), {
    center: OLD_FORT_CENTER,
    zoom: 15.2,
    pitch: 0,
    bearing: 0,
  });
  await setSlider(".ba-range", 0);
  await sleep(400);
  await waitTilesSettled();
  {
    const n = Math.round((3600 / 1000) * FPS);
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      const ease = t * t * (3 - 2 * t);
      await setSlider(".ba-range", ease);
      await page.evaluate(
        (p) => window.__ttMap.jumpTo({ center: p.center, zoom: p.zoom, bearing: 0, pitch: p.pitch }),
        { center: OLD_FORT_CENTER, zoom: 15.2, pitch: 55 * ease },
      );
      await sleep(20);
      await shot();
    }
  }

  // P5 (~2.5s) - "The worst damage isn't spread evenly." settle at full 3-D.
  await hold(2500);

  // P6 (~6s) - "It clusters right along the creek..." rotate to reveal it.
  await panCamera(
    { center: OLD_FORT_CENTER, zoom: 15.2, pitch: 55, bearing: 0 },
    { center: OLD_FORT_CENTER, zoom: 15.2, pitch: 55, bearing: 150 },
    7000,
    (t) => t,
  );

  // P7 (~3s, un-narrated punctuation) - click one building, hold score card.
  await page.evaluate(
    (c) => window.__ttMap.jumpTo(c),
    { center: RED_BUILDING, zoom: 15.2, pitch: 55, bearing: 150 },
  );
  await sleep(300);
  await shot();
  const built = await clickAtLngLat(...RED_BUILDING);
  console.log("map: clicked building ->", built);
  await sleep(400);
  await hold(3400);
} else if (BEAT === "beat03-idle-check") {
  // debug helper: just load and screenshot once
  await page.goto(`${BASE}/?rec=1#/monitor`, { waitUntil: "networkidle2" });
  await sleep(2500);
  await shot();
} else {
  console.error("unknown beat:", BEAT);
  process.exit(1);
}

console.log("done, frames:", frameIdx);
await browser.close();
