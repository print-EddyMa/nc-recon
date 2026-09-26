// Ops-mode visual QA: Operations screen, area map, structure card, both themes.
// usage: node scripts/qa_ops.mjs [baseURL] [outDir]
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const BASE = process.argv[2] || "http://localhost:5173";
const OUT = process.argv[3] || "./qa-ops";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: false,
  args: ["--no-sandbox", "--window-size=1560,1000", "--hide-crash-restore-bubble"],
  defaultViewport: { width: 1512, height: 950, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push("console: " + m.text().slice(0, 300)));
page.on("pageerror", (e) => errors.push("pageerror: " + e.message.slice(0, 300)));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

for (const theme of ["light", "dark"]) {
  await page.goto(BASE + "/#/ops", { waitUntil: "networkidle2" });
  await page.evaluate((t) => localStorage.setItem("terratriage:theme", t), theme);
  await page.goto(BASE + "/#/ops/old_fort", { waitUntil: "networkidle2" });
  await page.reload({ waitUntil: "networkidle2" });
  await sleep(8000);
  await page.screenshot({ path: `${OUT}/${theme}-ops-oldfort.png` });
  // open the top review-queue item
  const clicked = await page.evaluate(() => {
    const sec = [...document.querySelectorAll("section")].find((s) => s.textContent?.startsWith("Review queue"));
    const b = sec?.querySelector("li button");
    if (b) { b.click(); return true; }
    return false;
  });
  await sleep(4000);
  await page.screenshot({ path: `${OUT}/${theme}-ops-card.png` });
  console.log(theme, "queue item clicked:", clicked);
}
await page.goto(BASE + "/#/ops/chimney_rock", { waitUntil: "networkidle2" });
await sleep(7000);
await page.screenshot({ path: `${OUT}/dark-ops-chimney.png` });
console.log(errors.length ? "\nERRORS:\n" + [...new Set(errors)].join("\n") : "\nno console/page errors");
await browser.close();
