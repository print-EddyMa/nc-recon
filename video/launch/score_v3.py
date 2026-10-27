"""Score and mix for launch film v3 (the story cut): `python video/launch/score_v3.py` (pipeline venv).

No voice. Rain and river under the opening photographs, single low piano
notes under the dated facts, a piano and low-string theme from the park on,
near silence under the proof, D major on the valley and a bell on the mark.
All synthesised here; no samples, no third-party licence. Mastered to -16 LUFS.
Writes build/mix_v3.wav and, with build/picture_v3.mp4, build/groma_launch_v3.mp4.
"""
from __future__ import annotations

import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import SR, _write, bell, bp, hz, lp, pad, piano, place, reverb  # noqa: E402

BUILD = os.path.join(HERE, "build")
DUR = 101.0
N = int(DUR * SR)
rng = np.random.default_rng(23)


def env(a, b, fi, fo):
    tt = np.arange(N) / SR
    return np.clip((tt - a) / fi, 0, 1) * np.clip((b - tt) / fo, 0, 1)


def arp(buf, t0, t1, notes, step, vel=0.26):
    t, i = t0, 0
    while t < t1 - 0.05:
        place(buf, piano(hz(notes[i % len(notes)]), dur=4.5, vel=vel + (0.06 if i % len(notes) == 0 else 0)), t)
        t += step
        i += 1


def music() -> np.ndarray:
    m = np.zeros(N)
    noise = rng.standard_normal(N)
    rain = lp(noise - lp(noise, 1800), 6500) * 0.009
    river = bp(rng.standard_normal(N), 120, 900) * 0.032 * (1 + 0.25 * np.sin(2 * np.pi * 0.17 * np.arange(N) / SR))
    m += (rain + river) * env(0.3, 34.0, 2.0, 3.0)
    for s, n, v in ((7.4, "D3", 0.36), (17.6, "A2", 0.34), (27.8, "D2", 0.40)):
        place(m, piano(hz(n), dur=6, vel=v), s)
    # the park onward
    beat = 60 / 66
    place(m, pad([hz("D2"), hz("A2"), hz("F3")], 19.5, att=4.0, rel=3.0, level=0.10, cutoff=900), 33.0)
    arp(m, 34.2, 45.0, ["D4", "A4", "F4", "A4"], beat * 2, 0.22)
    place(m, bell(hz("A5"), 0.06), 45.4)
    arp(m, 45.4, 52.2, ["A#3", "F4", "D4", "F4"], beat * 2, 0.22)
    place(m, pad([hz("A#1"), hz("F2"), hz("D3")], 9.0, att=1.5, rel=2.0, level=0.10, cutoff=1000), 51.8)
    arp(m, 52.2, 60.2, ["F3", "C4", "A4", "C4"], beat, 0.20)
    place(m, pad([hz("F2"), hz("C3"), hz("A3")], 8.5, att=1.0, rel=2.0, level=0.09, cutoff=1000), 59.8)
    arp(m, 60.2, 66.2, ["C4", "G4", "E4", "G4"], beat, 0.22)
    place(m, pad([hz("C2"), hz("G2"), hz("E3")], 8.6, att=1.0, rel=2.5, level=0.09, cutoff=900), 65.9)
    arp(m, 66.2, 74.0, ["D4", "A4", "F4", "A4"], beat * 2, 0.20)
    # proof: near silence
    place(m, pad([hz("D2"), hz("A2")], 12.0, att=2.0, rel=3.0, level=0.05, cutoff=600), 74.4)
    place(m, piano(hz("D3"), dur=6, vel=0.26), 75.0)
    # the valley resolves
    place(m, pad([hz("D2"), hz("A2"), hz("F#3"), hz("D4")], 15.5, att=2.0, rel=6.0, level=0.13, cutoff=1500), 85.8)
    arp(m, 86.2, 94.4, ["D4", "F#4", "A4", "F#4"], beat * 2, 0.24)
    for k, n in enumerate(["D3", "A3", "F#4", "D5"]):
        place(m, piano(hz(n), dur=6.5, vel=0.36), 94.8 + k * 0.03)
    place(m, bell(hz("D5"), 0.12), 94.9)
    L, R = reverb(m, 2.8, 0.28)
    out = np.stack([L, R], 1)
    return out * np.clip((DUR - np.arange(N) / SR) / 3.0, 0, 1)[:, None]


def main() -> None:
    os.makedirs(BUILD, exist_ok=True)
    m = music()
    m = m / np.max(np.abs(m)) * 0.7
    raw = os.path.join(BUILD, "music_v3.wav")
    _write(raw, m)
    mix = os.path.join(BUILD, "mix_v3.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af",
                    "highpass=f=35,equalizer=f=90:t=q:w=1:g=-3,loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", mix], check=True)
    pic = os.path.join(BUILD, "picture_v3.mp4")
    if os.path.exists(pic):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-i", mix, "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
                        "-shortest", "-movflags", "+faststart", os.path.join(BUILD, "groma_launch_v3.mp4")], check=True)
    print("mix", mix, "film", os.path.exists(pic))


if __name__ == "__main__":
    main()
