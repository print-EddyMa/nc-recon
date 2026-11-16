"""The sound for the hype cut, take two: `python video/launch/score_v6.py [--mix-only]` (pipeline venv).

Replaces score_v5's synthesised trap track, which was wrong in tone for a real disaster and far
too bass-heavy. Measured against real launch films (Anduril Fight Unfair, Claude Fable 5, OpenAI
Codex): their mids carry the sound, their level holds steady, and bass is kept for a moment or two.

Music: "Hyperion" by Scott Buckley, CC BY 4.0, slowed 3% to lock to the film's grid and cut in four
pieces so its own events land on the picture:
    beats 0 to 44    the slow build, its first entry on beat 28 (the 80,000)
    beats 44 to 54   the quiet solo strings, under the 4% and the question
    beats 54 to 96   the closing theme, ending on its hard stop as the 96% appears
    beats 96 to 130  the gentle coda, under the proof and the logo
Sound effects: real CC0 recordings. No synth, no 808.

Writes build/mix_v6.wav and, if the pictures exist, build/ncrecon_launch_v6_<aspect>.mp4.
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
from score_v5 import BEAT, B, BUILD, CUES, N, DUR, crash, hit, put, sample  # noqa: E402

TRACK = os.path.join(HERE, "assets", "v6", "music", "Hyperion.mp3")
STRETCH = 75 / 77.4                       # atempo: the track's 77.4 bpm onto the film's 75
K = 1 / STRETCH                           # film seconds per track second
# film beat, end beat, track second that lands on the first beat
CUTS = [(0, 44, 37.58 - B(28) / K), (44, 54, 112.36 - B(10) / K), (54, 96, 204.38), (96, 130, 225.35)]


def music() -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", TRACK, "-af", f"atempo={STRETCH:.5f}", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, "float32").reshape(-1, 2)
    out = np.zeros((N, 2))
    for b0, b1, src in CUTS:
        i0, n = int(src * K * SR), int(B(b1 - b0) * SR)
        seg = x[i0:i0 + n].copy()
        f = int(0.012 * SR)                                                    # short fades: these are hard cuts, not crossfades
        seg[:f] *= np.linspace(0, 1, f)[:, None]
        seg[-f:] *= np.linspace(1, 0, f)[:, None]
        put(out, seg, B(b0))
    return out


def effects() -> np.ndarray:
    fx = np.zeros((N, 2))
    # the storm
    hit(fx, "thunder_0", 0, 0.8, dur=3.4, fade=1.2)
    crash(fx, 0, 0.3)
    put(fx, sample("wind_1", B(8) + 0.4, fade=0.5), 0.0, 0.34)
    put(fx, sample("rain_1", B(8) + 0.4, start=2.0, fade=0.5), 0.0, 0.26)
    hit(fx, "impact_1", 4, 0.3, dur=1.6, fade=0.8)
    # each print lands: light, like paper on a table, so the music stays on top
    for f, n, _kind in CUES["flash"]:
        t = f / 30
        put(fx, sample("paper_1", 0.12, pitch=1.2 + 0.3 * ((f * 7) % 10) / 10, fade=0.03), t, 0.42 if n >= 4 else 0.24)
        put(fx, sample("stamp_1", 0.1, pitch=1.15, fade=0.03), t, 0.26 if n >= 6 else 0.15)
    # the damage
    hit(fx, "impact_0", 28, 0.55, dur=3, fade=1.5)
    hit(fx, "debris_0", 28, 0.42, dur=B(5), fade=0.6)
    hit(fx, "river_1", 28, 0.2, dur=B(16), fade=0.4)
    hit(fx, "helicopter_1", 36, 0.3, dur=B(8), fade=0.4, start=3.0)
    # the fact, the question
    hit(fx, "impact_1", 44, 0.34, dur=2.2, fade=1.5)
    hit(fx, "heartbeat_0", 50, 0.36, dur=B(4), fade=0.1)
    # the ring
    crash(fx, 54, 0.32)
    hit(fx, "impact_0", 54, 0.6, dur=4, fade=2)
    hit(fx, "whoosh_0", 54, 0.4, dur=2.2, fade=0.6)
    for b in np.arange(55, 64, 1):
        put(fx, sample("typewriter_0", 0.05, pitch=1.5, fade=0.02), B(b), 0.1)
    for b in (67, 69, 71):
        hit(fx, "impact_1", b, 0.3, dur=1, fade=0.5)
    for b, w in ((72, "whoosh_2"), (74, "whoosh_3"), (76, "whoosh_4"), (78, "whoosh_2"), (86, "whoosh_3"), (88, "whoosh_2"), (90, "whoosh_4"), (92, "whoosh_3"), (94, "whoosh_2")):
        hit(fx, w, b - 0.25, 0.42)
    for b in (80, 81, 82, 83):
        put(fx, sample("shutter_0", 0.09, fade=0.02), B(b), 0.55)
    hit(fx, "stamp_0", 84, 0.5, dur=0.4)
    for b in np.arange(88, 89, 0.25):
        put(fx, sample("typewriter_0", 0.06, pitch=1.3, fade=0.02), B(b), 0.2)
    # the proof and the logo
    hit(fx, "impact_1", 96, 0.26, dur=2.2, fade=1.5)
    for b in (104, 105):
        hit(fx, "stamp_0", b, 0.5, dur=0.4)
    hit(fx, "impact_0", 113, 0.6, dur=4.5, fade=2.5)
    crash(fx, 113, 0.14)
    for i in range(9):
        put(fx, sample("typewriter_0", 0.07, pitch=1.2, fade=0.02), B(120.5 + i * 0.25), 0.2)
    return fx


def bus(x, cut=45):
    return np.stack([c - lp(c, cut) for c in x.T], axis=1)


def main() -> None:
    m = music()
    fx = bus(effects())
    # the music is the track; it only comes up where the composer's own level is low for a phone
    db = np.zeros(N)
    for b0, b1, g in ((0, 28, 3), (28, 44, 3), (44, 54, 3), (54, 96, 0), (96, 104, 3), (104, 113, 8), (113, 130, 9)):
        db[int(B(b0) * SR):int(B(b1) * SR)] = g
    m = m * (10 ** (lp(db, 30) / 20))[:, None]
    wetL, _ = reverb(fx[:, 0], seconds=1.4, wet=1.0)
    _, wetR = reverb(fx[:, 1], seconds=1.4, wet=1.0)
    x = m + fx + np.stack([wetL, wetR], axis=1)[:N] * 0.1
    x[-int(1.6 * SR):] *= np.linspace(1, 0, int(1.6 * SR))[:, None]
    from scipy.io import wavfile
    raw = os.path.join(BUILD, "mix_v6_raw.wav")
    wav = os.path.join(BUILD, "mix_v6.wav")
    wavfile.write(raw, SR, x.astype("float32"))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", raw, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    measured = float(r.rsplit("I:", 1)[1].split("LUFS")[0])
    gain = -14.0 - measured
    y = x * 10 ** (gain / 20)
    y = 0.84 * np.tanh(y / 0.84)
    wavfile.write(wav, SR, y.astype("float32"))
    print(f"measured {measured:.1f} LUFS, gain {gain:+.1f} dB, stretch {STRETCH:.4f}")
    for aspect in () if "--mix-only" in sys.argv else ("16x9", "9x16"):
        pic = os.path.join(BUILD, f"picture_v5_{aspect}.mp4")
        out = os.path.join(BUILD, f"ncrecon_launch_v6_{aspect}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", out], check=True)
        print("wrote", out)


if __name__ == "__main__":
    main()
