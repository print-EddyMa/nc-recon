"""Capture the Groma app for launch film v2:
`python3 video/launch/capture_v2.py [--base http://localhost:8003] [--only orbit,respond,...]`.

Runs against a scratch server only (`groma-film-api` in .claude/launch.json:
scratch registry, jobs, truth, labels, audit, cache) and, for the offline
shot, a scratch offline install served with outbound network denied. Never
the user's :8000/:5173. Building-level views use the TUNE area Swannanoa
only; the wildfire event is shown at area level (stepper and overview), never
a building in Altadena.

Writes assets/app2/:
  orbit/0000.png ...   frame-exact 3D orbit of Swannanoa (app's ?rec=1 hook)
  respond.png          Respond tab: lifelines, landing zones, sectors
  stepper_*.png        typing a FEMA disaster number; the declaration it finds
  area.png             Swannanoa assessed (Overview tab)
  overview.png         every assessed area, worst first (area level)
  verify.png           blind review with a Civil Air Patrol photo
  export.png           export menu: FEMA survey, KML, GeoPackage, File Geodatabase
  offline_*.png        the same area served with the network denied (--base-offline)
"""
from __future__ import annotations

import argparse
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BUILD = os.path.join(HERE, "build")
OUT = os.path.join(HERE, "assets", "app2")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

JS = r"""
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";
const [,, base, offlineBase, out, only] = process.argv;
const want = k => !only || only.split(",").includes(k);
const browser = await puppeteer.launch({ executablePath: CHROME_PATH, headless: true,
  args: ["--no-sandbox", "--hide-scrollbars", "--force-color-profile=srgb", "--use-angle=metal", "--enable-gpu"] });
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function newPage(dpr) {
  const p = await browser.newPage();
  await p.setViewport({ width: 1920, height: 1080, deviceScaleFactor: dpr });
  await p.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "dark" }]);
  await p.evaluateOnNewDocument(() => { try { localStorage.setItem("terratriage:verifier", "Film"); } catch {} });
  return p;
}
async function click(p, pred) {
  const ok = await p.evaluate((src) => { const f = new Function("e", "return " + src);
    const el = [...document.querySelectorAll("button,[role=tab],label,a")].find(e => f(e)); if (el) { el.click(); return true; } return false; }, pred);
  if (!ok) console.log("not found:", pred);
  return ok;
}
const aria = s => `(e.getAttribute('aria-label')||e.title||'').startsWith(${JSON.stringify(s)})`;
const text = s => `(e.textContent||'').trim().startsWith(${JSON.stringify(s)})`;
async function idle(p, ms = 8000) { try { await p.waitForNetworkIdle({ idleTime: 700, timeout: ms }); } catch {} }
async function openArea(p, b, area) {
  await p.goto(b + "/?rec=1#/", { waitUntil: "networkidle2" }); await sleep(2500);
  await click(p, aria("Open " + area)); await idle(p, 20000); await sleep(3500);
}
async function mapIdle(p, ms = 6000) {
  await p.evaluate(ms => new Promise(r => { const m = window.__ttMap; if (!m) return r();
    let done = false; const fin = () => { if (!done) { done = true; r(); } };
    if (m.loaded() && m.areTilesLoaded()) setTimeout(fin, 60); else m.once("idle", fin); setTimeout(fin, ms); }), ms);
}

if (want("orbit")) {
  const p = await newPage(1);
  await openArea(p, base, "Swannanoa");
  await click(p, aria("Buildings at inventory height")); await sleep(1500);
  await click(p, text("Terrain")); await sleep(2000);
  await click(p, aria("Fold the legend")); await sleep(500);
  mkdirSync(out + "/orbit", { recursive: true });
  const N = 120, c = [-82.3985, 35.6035];
  for (let i = 0; i < N; i++) {
    const k = i / (N - 1), e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k+2, 2)/2;
    await p.evaluate((c, e) => window.__ttMap && window.__ttMap.jumpTo({ center: [c[0] - 0.004 + 0.008*e, c[1] - 0.001 + 0.002*e],
      zoom: 15.25 + 0.75*e, pitch: 62 - 4*e, bearing: -58 + 52*e }), c, e);
    await mapIdle(p);
    await p.screenshot({ path: `${out}/orbit/${String(i).padStart(4, "0")}.png` });
  }
  await p.close();
}
if (want("area")) {
  const p = await newPage(2);
  await openArea(p, base, "Swannanoa");
  await p.screenshot({ path: out + "/area.png" });
  await p.close();
}
if (want("respond")) {
  const p = await newPage(2);
  await openArea(p, base, "Swannanoa");
  await click(p, text("Respond")); await sleep(3500);
  await p.screenshot({ path: out + "/respond.png" });
  await click(p, aria("GeoJSON, CSV with USNG")); await sleep(1500);
  await p.screenshot({ path: out + "/export.png" });
  await p.close();
}
if (want("stepper")) {
  const p = await newPage(2);
  await p.goto(base + "/#/", { waitUntil: "networkidle2" }); await sleep(2500);
  await click(p, aria("New assessment")); await sleep(1200);
  await click(p, text("Event not listed?")); await sleep(1000);
  const sel = "input[placeholder='4856']";
  await p.screenshot({ path: out + "/stepper_0.png" });
  const digits = "4856";
  for (let i = 0; i < digits.length; i++) { await p.type(sel, digits[i]); await sleep(150); await p.screenshot({ path: `${out}/stepper_${i + 1}.png` }); }
  await click(p, text("Look up")); await idle(p, 20000); await sleep(1500);
  await p.screenshot({ path: out + "/stepper_found.png" });
  await p.close();
}
if (want("overview")) {
  const p = await newPage(2);
  await p.goto(base + "/#/", { waitUntil: "networkidle2" }); await sleep(4000);
  await p.screenshot({ path: out + "/overview.png" });
  await p.close();
}
if (want("verify")) {
  const p = await newPage(2);
  await p.goto(base + "/#/verify", { waitUntil: "networkidle2" }); await sleep(1500);
  await p.evaluate(() => {
    const s = document.querySelector("select"); if (s) { s.value = "swannanoa"; s.dispatchEvent(new Event("change", { bubbles: true })); }
    const inp = document.querySelector("input[placeholder*='initials' i]");
    if (inp && !inp.value) { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      set.call(inp, "Film"); inp.dispatchEvent(new Event("input", { bubbles: true })); inp.dispatchEvent(new Event("blur", { bubbles: true })); inp.blur(); }
  });
  await idle(p, 90000); await sleep(6000);
  await p.screenshot({ path: out + "/verify.png" });
  await p.close();
}
if (want("offline") && offlineBase !== "-") {
  const p = await newPage(2);
  await openArea(p, offlineBase, "Swannanoa");
  await p.screenshot({ path: out + "/offline_map.png" });
  await click(p, aria("Buildings at inventory height")); await sleep(2500);
  await p.screenshot({ path: out + "/offline_3d.png" });
  await p.close();
}
await browser.close();
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8003")
    ap.add_argument("--base-offline", default="-")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)
    js = os.path.join(BUILD, "capture_v2.mjs")
    with open(js, "w", encoding="utf-8") as fh:
        fh.write(JS.replace("CHROME_PATH", repr(CHROME)))
    link = os.path.join(BUILD, "node_modules")
    if not os.path.exists(link):
        os.symlink(os.path.join(ROOT, "web", "node_modules"), link)
    subprocess.run(["node", js, a.base, a.base_offline, OUT, a.only], check=True)
    print(sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
