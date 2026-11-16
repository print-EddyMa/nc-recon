"""Render the launch film picture: `python video/launch/render.py [--stills 3,14,22] [--fps 30]`.

Steps `window.render(t)` in headless Chrome (puppeteer-core from web/node_modules)
frame by frame and pipes JPEG frames into ffmpeg (H.264, yuv420p). --stills
writes PNGs at the given seconds instead, for review.

Writes build/picture.mp4 or build/still_<t>.png.
"""
from __future__ import annotations

import argparse
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BUILD = os.path.join(HERE, "build")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

JS = r"""
import puppeteer from "puppeteer-core";
import { spawn } from "node:child_process";
const [,, html, mode, arg, fps, out, name, vw, vh, sub] = process.argv;
let browser, page;
async function open() {            // also used to start over when Chrome wedges mid-render
  browser = await puppeteer.launch({ executablePath: CHROME_PATH, headless: true,
    args: ["--no-sandbox", "--hide-scrollbars", "--allow-file-access-from-files", "--force-color-profile=srgb",
           "--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist", "--enable-webgl"],
    defaultViewport: { width: +vw, height: +vh, deviceScaleFactor: 1 } });
  page = await browser.newPage();
  await page.goto("file://" + html, { waitUntil: "load" });
  page.on("console", m => { if (m.type() === "error") console.log("page:", m.text()); });
  await page.evaluate(async () => { if (window.READY) await window.READY; await document.fonts.ready;
    await Promise.all([...document.images].map(i => i.decode().catch(() => {}))); });
}
await open();
const dur = await page.evaluate(() => window.DURATION);
if (mode === "check") {           // every slam cue, at its midpoint: does the type fit its mask?
  const bad = await page.evaluate(async () => { const out = []; const els = [...document.querySelectorAll(".t.slam")];
    for (const el of els) { const b = (+el.dataset.a + +el.dataset.z) / 2 * 0.4; await window.render(b);
      const inner = el.querySelector(".in"); const w = Math.max(...[...inner.getClientRects()].map(r => r.width)); const r = document.createRange(); r.selectNodeContents(inner); const tw = r.getBoundingClientRect().width;
      out.push([el.textContent.slice(0, 24), Math.round(tw), inner.scrollWidth, el.clientWidth, inner.scrollWidth > el.clientWidth]); }
    return out; });
  for (const r of bad) console.log(r[4] ? "OVER" : "ok  ", r.join(" | "));
} else if (mode === "stills") {
  for (const t of arg.split(",").map(Number)) {
    await page.evaluate(t => window.render(t), t);
    await page.screenshot({ path: `${out}/still_${name}_${t.toFixed(1)}.png`, omitBackground: true });
  }
} else {
  const n = Math.round(dur * +fps * +sub);
  // a sub-frame count above 1 renders that many steps per output frame and blends the first
  // 3 of every 5, a 216 degree shutter, so anything that moves fast gets real motion blur
  const blur = +sub > 1 ? ["-vf", `tmix=frames=${Math.ceil(+sub * 0.6)},select='eq(mod(n\\,${sub})\\,${Math.ceil(+sub * 0.6) - 1})',setpts=N/(${fps}*TB)`, "-r", fps] : [];
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(+fps * +sub), "-i", "-", ...blur,
    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out + "/" + name],
    { stdio: ["pipe", "inherit", "inherit"] });
  for (let f = 0; f < n; f++) {
    let buf = null;                  // a screenshot can stall in headless Chrome: wait 15 s, ask again, then restart the browser and carry on
    for (let tries = 0; !buf && tries < 8; tries++) {
      const go = (async () => { await page.evaluate(t => window.render(t), f / (+fps * +sub)); return page.screenshot({ type: "jpeg", quality: 94 }); })().catch(() => null);
      buf = await Promise.race([go, new Promise(r => setTimeout(() => r(null), 15000))]);
      if (!buf && tries % 2 === 1) { console.log(`restarting Chrome at step ${f}`); try { browser.process()?.kill("SIGKILL"); } catch {} await open(); }
      else if (!buf) console.log(`retry step ${f}`);
    }
    if (!buf) throw new Error(`no screenshot at step ${f}`);
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
    if (f % 150 === 0) console.log(`frame ${f}/${n}`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on("close", r));
}
await browser.close();
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", default="")
    ap.add_argument("--fps", default="30")
    ap.add_argument("--html", default="composition.html")
    ap.add_argument("--out", default="picture.mp4")
    ap.add_argument("--w", default="1920")
    ap.add_argument("--h", default="1080")
    ap.add_argument("--sub", default="1")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    os.makedirs(BUILD, exist_ok=True)
    js = os.path.join(BUILD, "render.mjs")
    with open(js, "w", encoding="utf-8") as fh:
        fh.write(JS.replace("CHROME_PATH", repr(CHROME)))
    # resolve puppeteer-core from the web app's node_modules
    link = os.path.join(BUILD, "node_modules")
    if not os.path.exists(link):
        os.symlink(os.path.join(ROOT, "web", "node_modules"), link)
    mode, arg = ("stills", a.stills) if a.stills else ("check", "") if a.check else ("film", "")
    subprocess.run(["node", js, os.path.join(BUILD, a.html), mode, arg, a.fps, BUILD, a.out, a.w, a.h, a.sub], check=True)


if __name__ == "__main__":
    main()
