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
  args: ["--no-sandbox", "--window-size=1560,1000", "--hide-crash-restore-bubble",
    ...(process.env.QA_INSECURE ? ["--ignore-certificate-errors"] : [])],
  acceptInsecureCerts: !!process.env.QA_INSECURE,
  defaultViewport: { width: 1512, height: 950, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push("console: " + m.text().slice(0, 300)));
page.on("pageerror", (e) => errors.push("pageerror: " + e.message.slice(0, 300)));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

for (const theme of ["light", "dark"]) {
  await page.goto(BASE + "/#/", { waitUntil: "networkidle2" });
  await page.evaluate((t, tok) => {
    localStorage.setItem("terratriage:theme", t);
    if (tok) localStorage.setItem("terratriage:responderToken", tok);
  }, theme, process.env.QA_TOKEN || "");
  await page.reload({ waitUntil: "networkidle2" });
  await sleep(4000);
  await page.screenshot({ path: `${OUT}/${theme}-ops-home.png` });
  await page.goto(BASE + "/#/ops/" + (process.env.QA_AREA || "old_fort"), { waitUntil: "networkidle2" });
  await page.reload({ waitUntil: "networkidle2" });
  await sleep(8000);
  await page.screenshot({ path: `${OUT}/${theme}-ops-oldfort.png` });
  // open the top review-queue item
  const clicked = await page.evaluate(() => {
    const sec = [...document.querySelectorAll("section")].find((s) => s.querySelector("h2")?.textContent === "Review queue");
    const b = sec?.querySelector("li button");
    if (b) { b.click(); return true; }
    return false;
  });
  await sleep(4000);
  await page.screenshot({ path: `${OUT}/${theme}-ops-card.png` });
  console.log(theme, "queue item clicked:", clicked);
}
for (const [name, hash] of [["conditions", "#/conditions"], ["help", "#/help"]]) {
  await page.goto(BASE + "/" + hash, { waitUntil: "networkidle2" });
  await sleep(6000);
  await page.screenshot({ path: `${OUT}/dark-${name}.png` });
}
// tablet width: new-assessment panel open
await page.setViewport({ width: 1024, height: 768, deviceScaleFactor: 1 });
await page.goto(BASE + "/#/", { waitUntil: "networkidle2" });
await sleep(3000);
await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent === "New assessment")?.click());
await sleep(2000);
await page.screenshot({ path: `${OUT}/tablet-new-assessment.png` });
console.log(errors.length ? "\nERRORS:\n" + [...new Set(errors)].join("\n") : "\nno console/page errors");
await browser.close();
