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
const [,, html, mode, arg, fps, out] = process.argv;
const browser = await puppeteer.launch({ executablePath: CHROME_PATH, headless: true,
  args: ["--no-sandbox", "--hide-scrollbars", "--allow-file-access-from-files", "--force-color-profile=srgb"],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 } });
const page = await browser.newPage();
await page.goto("file://" + html, { waitUntil: "load" });
await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map(i => i.decode().catch(() => {}))); });
const dur = await page.evaluate(() => window.DURATION);
if (mode === "stills") {
  for (const t of arg.split(",").map(Number)) {
    await page.evaluate(t => window.render(t), t);
    await page.screenshot({ path: `${out}/still_${t.toFixed(1)}.png` });
  }
} else {
  const n = Math.round(dur * +fps);
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", fps, "-i", "-",
    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out + "/picture.mp4"],
    { stdio: ["pipe", "inherit", "inherit"] });
  for (let f = 0; f < n; f++) {
    await page.evaluate(t => window.render(t), f / +fps);
    const buf = await page.screenshot({ type: "jpeg", quality: 94 });
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
    a = ap.parse_args()
    os.makedirs(BUILD, exist_ok=True)
    js = os.path.join(BUILD, "render.mjs")
    with open(js, "w", encoding="utf-8") as fh:
        fh.write(JS.replace("CHROME_PATH", repr(CHROME)))
    # resolve puppeteer-core from the web app's node_modules
    link = os.path.join(BUILD, "node_modules")
    if not os.path.exists(link):
        os.symlink(os.path.join(ROOT, "web", "node_modules"), link)
    mode, arg = ("stills", a.stills) if a.stills else ("film", "")
    subprocess.run(["node", js, os.path.join(BUILD, "composition.html"), mode, arg, a.fps, BUILD], check=True)


if __name__ == "__main__":
    main()
