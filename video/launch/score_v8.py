"""The sound for the calmer cut: `python video/launch/score_v8.py [--mix-only]` (pipeline venv).

Real product launches were measured first (Cursor 2.0: about 114 bpm, gentle, mids well above the
bass, no big hits). So the music plays as one unbroken take that peaks on the logo, with no drops
or splices, and the sound effects are few and quiet.

Three versions of the same picture, so the choice can be made by ear:
    A  "Horizons" by Scott Buckley: piano and strings over a driving arpeggio, the edit's own track
    B  "Clarion" by Scott Buckley: clarinet and piano building to brass and choir
    C  "What Does Anybody Know About Anything" by Chris Zabriskie: warm modern electronic

Writes build/ncrecon_launch_v8_<A|B|C>_<aspect>.mp4.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import SR, lp, reverb  # noqa: E402
from score_v5 import put, sample  # noqa: E402

BUILD = os.path.join(HERE, "build")
CUES = json.load(open(os.path.join(BUILD, "cues_v7.json")))
BEAT = CUES["beat"]
B = lambda n: n * BEAT  # noqa: E731
DUR = CUES["end"] * BEAT
N = int(DUR * SR)
M = os.path.join(HERE, "assets", "v7", "music")
# name: file, tempo factor, the track second that lands on the logo
VERSIONS = {
    "A": ("SB_sb_horizons.mp3", 0.5625 / (17 / 30), 269.5),
    "B": ("SB_sb_clarion.mp3", 1.0, 178.0),
    "C": ("Chris_Zabriskie_-_Direct_to_Video_-_02_What_Does_Anybody_Know_About_Anything.mp3", 1.0, 219.0),
}


def music(name: str) -> np.ndarray:
    f, tempo, peak = VERSIONS[name]
    af = ["-af", f"atempo={tempo:.5f}"] if tempo != 1.0 else []
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", os.path.join(M, f), *af, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, "float32").reshape(-1, 2)
    i0 = int((peak / tempo - B(112)) * SR)
    seg = x[i0:i0 + N].copy()
    out = np.zeros((N, 2))
    out[:len(seg)] = seg
    n = int(1.2 * SR)
    out[:n] *= np.linspace(0, 1, n)[:, None] ** 2                  # it comes up under the storm
    return out


def hit(buf, name, beat, gain=1.0, dur=None, pitch=1.0, start=0.0, fade=0.05):
    put(buf, sample(name, dur, pitch, fade, start), B(beat), gain)


def effects() -> np.ndarray:
    fx = np.zeros((N, 2))
    hit(fx, "thunder_0", 0, 0.45, dur=3.4, fade=1.4)
    put(fx, sample("wind_1", B(8) + 0.4, fade=0.8), 0.0, 0.22)
    put(fx, sample("rain_1", B(8) + 0.4, start=2.0, fade=0.8), 0.0, 0.16)
    for f, n, _k in CUES["flash"]:                                  # paper on a table
        put(fx, sample("paper_1", 0.14, pitch=1.15 + 0.2 * ((f * 7) % 10) / 10, fade=0.04), f / 30, 0.3)
    hit(fx, "river_1", 20, 0.1, dur=B(12), fade=0.8)
    hit(fx, "impact_1", 40, 0.26, dur=2.2, fade=1.4)
    hit(fx, "whoosh_0", 40, 0.14, dur=2, fade=0.8)
    for b in (72, 74):
        put(fx, sample("shutter_0", 0.09, fade=0.02), B(b), 0.28)
    hit(fx, "impact_1", 112, 0.24, dur=2.4, fade=1.5)
    for i in range(8):
        put(fx, sample("typewriter_0", 0.07, pitch=1.2, fade=0.02), B(117.5 + i * 0.25), 0.12)
    return fx


def main() -> None:
    fx = np.stack([c - lp(c, 45) for c in effects().T], axis=1)
    wetL, _ = reverb(fx[:, 0], seconds=1.4, wet=1.0)
    _, wetR = reverb(fx[:, 1], seconds=1.4, wet=1.0)
    fxw = fx + np.stack([wetL, wetR], axis=1)[:N] * 0.1
    from scipy.io import wavfile
    for name in VERSIONS:
        x = music(name) + fxw
        n = int(2.2 * SR)
        x[-n:] *= np.linspace(1, 0, n)[:, None]
        raw = os.path.join(BUILD, f"mix_v8_{name}_raw.wav")
        wav = os.path.join(BUILD, f"mix_v8_{name}.wav")
        wavfile.write(raw, SR, x.astype("float32"))
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", raw, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
        measured = float(r.rsplit("I:", 1)[1].split("LUFS")[0])
        y = x * 10 ** ((-15.0 - measured) / 20)
        y = 0.84 * np.tanh(y / 0.84)
        wavfile.write(wav, SR, y.astype("float32"))
        print(name, f"measured {measured:.1f} LUFS")
        for aspect in () if "--mix-only" in sys.argv else ("16x9", "9x16"):
            pic = os.path.join(BUILD, f"picture_v7_{aspect}.mp4")
            out = os.path.join(BUILD, f"ncrecon_launch_v8_{name}_{aspect}.mp4")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", out], check=True)
            print("wrote", out)


if __name__ == "__main__":
    main()
