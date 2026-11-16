"""The sound for the launch film, take three: `python video/launch/score_v7.py [--mix-only]` (pipeline venv).

The film is cut to this track, not the other way round. "Vanguard" by Scott Buckley (CC BY 4.0)
pulses every 0.3 s, and compose_v6.py is built on that pulse. Two runs of the track, one splice:
    film 0.0 to 33.6 s    track 51.0 to 84.6: already driving, its break under the question,
                          its drop on the ring at 20.4 s
    film 33.6 s to end    track 208.55 to the end: the climax, the hard stop on the 96%,
                          the hit on "Free", the last hit on the logo
Real CC0 recordings sit under it as accents. No synth, no tempo change.

Writes build/mix_v7.wav and, if the pictures exist, build/ncrecon_launch_v7_<aspect>.mp4.
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
from score_v5 import load, put, sample, t_  # noqa: E402

BUILD = os.path.join(HERE, "build")
CUES = json.load(open(os.path.join(BUILD, "cues_v6.json")))
BEAT = CUES["beat"]
B = lambda n: n * BEAT  # noqa: E731
DUR = CUES["end"] * BEAT
N = int(DUR * SR)
TRACK = os.path.join(HERE, "assets", "v6", "music", "Vanguard.mp3")
PIECES = [(0.0, 33.6, 50.995), (33.6, DUR, 208.55)]            # film start, film end, track second


def music() -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", TRACK, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, "float32").reshape(-1, 2)
    out = np.zeros((N, 2))
    for a, b, src in PIECES:
        i0, n = int(src * SR), int((b - a) * SR)
        seg = x[i0:i0 + n].copy()
        f = int(0.012 * SR)
        seg[:f] *= np.linspace(0, 1, f)[:, None]
        seg[-f:] *= np.linspace(1, 0, f)[:, None]
        put(out, seg, a)
    return out


def hit(buf, name, beat, gain=1.0, dur=None, pitch=1.0, start=0.0, fade=0.05):
    put(buf, sample(name, dur, pitch, fade, start), B(beat), gain)


def crash(buf, beat, level):
    t = t_(2.2)
    n = np.random.default_rng(int(beat * 10)).standard_normal((len(t), 2))
    x = np.stack([c - lp(c, 3000) for c in n.T], axis=1)
    put(buf, x * (np.exp(-t / 0.5) * level * 0.5)[:, None], B(beat))


def effects() -> np.ndarray:
    fx = np.zeros((N, 2))
    hit(fx, "thunder_0", 0, 0.7, dur=3.2, fade=1.2)
    crash(fx, 0, 0.3)
    put(fx, sample("wind_1", B(12) + 0.3, fade=0.5), 0.0, 0.3)
    put(fx, sample("rain_1", B(12) + 0.3, start=2.0, fade=0.5), 0.0, 0.2)
    hit(fx, "impact_1", 6, 0.32, dur=1.6, fade=0.8)
    for f, n, _k in CUES["flash"]:                                 # each print lands
        t = f / 30
        put(fx, sample("paper_1", 0.12, pitch=1.2 + 0.3 * ((f * 7) % 10) / 10, fade=0.03), t, 0.4 if n >= 4 else 0.22)
        put(fx, sample("stamp_1", 0.1, pitch=1.15, fade=0.03), t, 0.28 if n >= 6 else 0.15)
    crash(fx, 36, 0.3)
    hit(fx, "impact_0", 36, 0.6, dur=3, fade=1.5)
    hit(fx, "debris_0", 36, 0.36, dur=B(6), fade=0.6)
    hit(fx, "river_1", 36, 0.14, dur=B(16), fade=0.4)
    hit(fx, "helicopter_1", 44, 0.22, dur=B(8), fade=0.4, start=3.0)
    hit(fx, "impact_1", 52, 0.36, dur=2, fade=1.2)
    put(fx, sample("reverse_1"), B(68) - len(load("reverse_1")) / SR, 0.12)
    crash(fx, 68, 0.34)
    hit(fx, "impact_0", 68, 0.66, dur=4, fade=2)
    hit(fx, "whoosh_0", 68, 0.36, dur=2, fade=0.6)
    for b in np.arange(69, 80, 1):
        put(fx, sample("typewriter_0", 0.05, pitch=1.5, fade=0.02), B(b), 0.09)
    for b in (86, 89, 92):
        hit(fx, "impact_1", b, 0.3, dur=1, fade=0.5)
    for b, w in ((96, "whoosh_2"), (100, "whoosh_3"), (104, "whoosh_4"), (108, "whoosh_2"), (124, "whoosh_3"), (128, "whoosh_2"), (132, "whoosh_4"), (136, "whoosh_3"), (140, "whoosh_2")):
        hit(fx, w, b - 0.33, 0.4)
    for b in (112, 114, 116, 118):
        put(fx, sample("shutter_0", 0.09, fade=0.02), B(b), 0.5)
    hit(fx, "impact_1", 120, 0.36, dur=1.2, fade=0.6)
    hit(fx, "stamp_0", 120, 0.45, dur=0.4)
    hit(fx, "impact_1", 144, 0.3, dur=2.2, fade=1.5)
    for b in (153.9, 156, 158.5):
        hit(fx, "stamp_0", b, 0.42, dur=0.4)
    crash(fx, 170.5, 0.18)
    hit(fx, "impact_0", 170.5, 0.5, dur=4.5, fade=2.5)
    for i in range(9):
        put(fx, sample("typewriter_0", 0.07, pitch=1.2, fade=0.02), B(180 + i * 0.25), 0.2)
    return fx


def main() -> None:
    m = music()
    fx = np.stack([c - lp(c, 45) for c in effects().T], axis=1)
    wetL, _ = reverb(fx[:, 0], seconds=1.4, wet=1.0)
    _, wetR = reverb(fx[:, 1], seconds=1.4, wet=1.0)
    x = m + fx + np.stack([wetL, wetR], axis=1)[:N] * 0.1
    x[-int(1.4 * SR):] *= np.linspace(1, 0, int(1.4 * SR))[:, None]
    from scipy.io import wavfile
    raw = os.path.join(BUILD, "mix_v7_raw.wav")
    wav = os.path.join(BUILD, "mix_v7.wav")
    wavfile.write(raw, SR, x.astype("float32"))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", raw, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    measured = float(r.rsplit("I:", 1)[1].split("LUFS")[0])
    gain = -14.0 - measured
    y = 0.84 * np.tanh(x * 10 ** (gain / 20) / 0.84)
    wavfile.write(wav, SR, y.astype("float32"))
    print(f"measured {measured:.1f} LUFS, gain {gain:+.1f} dB")
    for aspect in () if "--mix-only" in sys.argv else ("16x9", "9x16"):
        pic = os.path.join(BUILD, f"picture_v6_{aspect}.mp4")
        out = os.path.join(BUILD, f"ncrecon_launch_v7_{aspect}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", out], check=True)
        print("wrote", out)


if __name__ == "__main__":
    main()
