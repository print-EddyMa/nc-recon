// Full-app visual QA: every screen, both themes, real Chrome (WebGL).
// usage: node scripts/qa_shots.mjs [baseURL] [outDir]
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const BASE = process.argv[2] || "http://localhost:5173";
const OUT = process.argv[3] || "/private/tmp/claude-501/-Users-eddyma/891daedb-073c-4385-868a-a9eb1bc955b5/scratchpad/shots";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: false,
  args: ["--no-sandbox", "--window-size=1560,1000", "--hide-crash-restore-bubble"],
  defaultViewport: { width: 1512, height: 950, deviceScaleFactor: 2 },
});
const page = await browser.newPage();
const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push("console: " + m.text().slice(0, 300)));
page.on("pageerror", (e) => errors.push("pageerror: " + e.message.slice(0, 300)));

const routes = [
  ["home", "#/"],
  ["live-monitor", "#/monitor"],
  ["history", "#/history"],
  ["assess", "#/assess"],
  ["about", "#/about"],
  ["damage-map", "#/a/old_fort/map"],
  ["review", "#/a/old_fort/review"],
  ["summary", "#/a/old_fort/stats"],
];

const ONLY = process.argv[4]; // optional: "light" or "dark"
for (const theme of ONLY ? [ONLY] : ["light", "dark"]) {
  for (const [name, hash] of routes) {
    await page.goto(BASE + "/" + hash, { waitUntil: "networkidle2" });
    await page.evaluate((t) => {
      try {
        if (t === "system") localStorage.removeItem("terratriage:theme");
        else localStorage.setItem("terratriage:theme", t);
        document.documentElement.setAttribute("data-theme", t);
      } catch {}
    }, theme);
    await page.reload({ waitUntil: "networkidle2" });
    // maps + live fetches need a beat
    const wait = /monitor|map|assess/.test(name) ? 7500 : 3500;
    await new Promise((r) => setTimeout(r, wait));
    const file = `${OUT}/${theme}-${name}.png`;
    await page.screenshot({ path: file });
    console.log("wrote", file);
  }
}

console.log(errors.length ? "\nERRORS:\n" + [...new Set(errors)].join("\n") : "\nno console/page errors");
await browser.close();
