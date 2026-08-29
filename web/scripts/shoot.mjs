// Headless screenshots of the app for visual QA.
// usage: node scripts/shoot.mjs [baseURL] [outDir]
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const BASE = process.argv[2] || "http://localhost:4173";
const OUT = process.argv[3] || "/tmp/tt_shots_gpu";
const CHROME =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: false,
  args: ["--no-sandbox","--window-size=1500,950"],
  defaultViewport: { width: 1600, height: 1000, deviceScaleFactor: 2 },
});
const page = await browser.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push("console: " + m.text()));
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));

async function shot(name, ms = 6000, action) {
  await page.goto(BASE + "/", { waitUntil: "networkidle2" });
  if (action) await action();
  await new Promise((r) => setTimeout(r, ms));
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log("wrote", `${OUT}/${name}.png`);
}

// landing
await shot("01-landing");

// map view: click "Open the damage map"
await shot("02-map", 5000, async () => {
  await page.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      /damage map/i.test(x.textContent || ""),
    );
    b?.click();
  });
});

// drag the assessment slider to ~40% then screenshot mid-transition
await shot("03-map-blend", 5200, async () => {
  await page.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((x) => /damage map/i.test(x.textContent || ""))
      ?.click();
  });
  await new Promise((r) => setTimeout(r, 2500));
  const slider = await page.$('input[type="range"].ba-range');
  if (slider) {
    await slider.focus();
    for (let i = 0; i < 30; i++) await page.keyboard.press("ArrowLeft");
  }
});

// summary screen
await shot("04-summary", 2600, async () => {
  await page.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((x) => /damage map/i.test(x.textContent || ""))
      ?.click();
  });
  await new Promise((r) => setTimeout(r, 800));
  await page.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((x) => /summary/i.test(x.textContent || ""))
      ?.click();
  });
});

console.log(errors.length ? "\nERRORS:\n" + errors.join("\n") : "\nno console/page errors");
await browser.close();
