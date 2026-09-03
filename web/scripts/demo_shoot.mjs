// Phase H dev helper — screenshot the hook sequence at a set of timecodes so
// the beats can be eyeballed.  node scripts/demo_shoot.mjs [base] [outDir]
import { mkdirSync } from "node:fs";
import puppeteer from "puppeteer-core";

const BASE = process.argv[2] || "http://localhost:4173";
const OUT = process.argv[3] || "/tmp/demo-shots";
const MS = process.env.MS
  ? process.env.MS.split(",").map(Number)
  : [400, 1400, 2400, 3400, 4400, 5400, 6100, 6900, 7600, 8400, 9100, 9800, 10600, 11400, 12300, 13100, 13900, 14400, 15200, 16100, 16800, 17100, 17700];
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: false,
  args: ["--no-sandbox", "--window-size=1600,1000", "--hide-scrollbars"],
  defaultViewport: { width: 1600, height: 1000, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
page.on("console", (m) => m.type() === "error" && console.log("  console.error:", m.text()));
page.on("pageerror", (e) => console.log("  pageerror:", e.message));
await page.goto(`${BASE}/demo.html?fixed=1${process.env.DEBUG ? "&debug=1" : ""}`, { waitUntil: "networkidle2" });
await page.waitForFunction(() => window.__demo && window.__demo.ready(), { timeout: 60_000 });
await sleep(600);
for (const ms of MS) {
  await page.evaluate((m) => window.__demo.seek(m), ms);
  // let the basemap settle so a seek screenshot isn't caught mid tile-load
  await page
    .waitForFunction(() => !window.__demoMap || window.__demoMap.areTilesLoaded(), { timeout: 4000 })
    .catch(() => {});
  await sleep(260);
  const beat = await page.evaluate(() => window.__demo.beat);
  const name = `${String(ms).padStart(5, "0")}-${beat}.png`;
  await page.screenshot({ path: `${OUT}/${name}` });
  console.log("wrote", name);
}
await browser.close();
