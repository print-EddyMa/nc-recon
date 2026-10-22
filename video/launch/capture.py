"""Capture the real Groma app for the launch film:
`python video/launch/capture.py [--base http://localhost:5176]`.

Runs against a scratch API (scratch registry, jobs, truth, labels, audit and
cache; see .claude/launch.json `ncrecon-api-photos`) so nothing in the live data
directory is written. Building-level views use the TUNE area Swannanoa only.

Writes assets/app/{overview,area,queue,verify}.png at 1920x1200, device scale 2.
"""
from __future__ import annotations

import argparse
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BUILD = os.path.join(HERE, "build")
OUT = os.path.join(HERE, "assets", "app")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

JS = r"""
import puppeteer from "puppeteer-core";
const [,, base, out] = process.argv;
const browser = await puppeteer.launch({ executablePath: CHROME_PATH, headless: true,
  args: ["--no-sandbox", "--hide-scrollbars", "--force-color-profile=srgb"],
  defaultViewport: { width: 1920, height: 1200, deviceScaleFactor: 2 } });
const page = await browser.newPage();
await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "dark" }]);
await page.evaluateOnNewDocument(() => { try { localStorage.setItem("terratriage:verifier", "Film"); } catch {} });
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function clickText(sel, text) {
  const ok = await page.evaluate((sel, text) => {
    const el = [...document.querySelectorAll(sel)].find(e => (e.getAttribute("aria-label") || e.textContent || "").trim().startsWith(text));
    if (el) { el.click(); return true; } return false; }, sel, text);
  if (!ok) console.log("not found:", sel, text);
  return ok;
}
async function waitIdle(ms) { try { await page.waitForNetworkIdle({ idleTime: 800, timeout: ms }); } catch {} }
await page.goto(base + "/#/", { waitUntil: "networkidle2" }); await sleep(3500);
await page.screenshot({ path: out + "/overview.png" });
await clickText("button", "Open Swannanoa"); await waitIdle(15000); await sleep(4000);
await page.screenshot({ path: out + "/area.png" });
await clickText("button,[role=tab]", "Review"); await sleep(1800);
await page.screenshot({ path: out + "/queue.png" });
await page.goto(base + "/#/verify", { waitUntil: "networkidle2" }); await sleep(1500);
await page.evaluate(() => {
  const sel = document.querySelector("select"); if (sel) { sel.value = "swannanoa"; sel.dispatchEvent(new Event("change", { bubbles: true })); }
  const inp = document.querySelector("input[placeholder*='name' i], input[placeholder*='initials' i]");
  if (inp && !inp.value) { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    set.call(inp, "Film"); inp.dispatchEvent(new Event("input", { bubbles: true })); inp.dispatchEvent(new Event("blur", { bubbles: true })); inp.blur(); }
});
await waitIdle(90000); await sleep(6000);
await page.screenshot({ path: out + "/verify.png" });
await browser.close();
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:5176")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)
    js = os.path.join(BUILD, "capture.mjs")
    with open(js, "w", encoding="utf-8") as fh:
        fh.write(JS.replace("CHROME_PATH", repr(CHROME)))
    link = os.path.join(BUILD, "node_modules")
    if not os.path.exists(link):
        os.symlink(os.path.join(ROOT, "web", "node_modules"), link)
    subprocess.run(["node", js, a.base, OUT], check=True)
    print(sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
