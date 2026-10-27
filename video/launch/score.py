"""Original score, sound design and final mix for the launch film:
`python video/launch/score.py` (pipeline venv: numpy, scipy).

Everything is synthesised here, so the music has no third-party licence:
felt-piano arpeggios (inharmonic additive partials), a filtered pad, soft sub
impacts on the big cuts, a bell for the groma's plumb lines, room tone and
river noise under the opening, UI ticks on the fast cuts. D minor turning to
D major at the close, 84 bpm. The voiceover (Kokoro, assets/vo) is placed on
cue, the music ducks under it, and the mix is loudness-normalised to -16 LUFS.

Writes build/music.wav, build/vo.wav, build/mix.wav and, when build/picture.mp4
exists, build/groma_launch.mp4.
"""
from __future__ import annotations

import json
import os
import subprocess

import numpy as np
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "assets")
BUILD = os.path.join(HERE, "build")
SR = 48000
DUR = 72.0
N = int(DUR * SR)
BEAT = 60 / 84
rng = np.random.default_rng(7)          # seeded: the score renders identically every time

VO_CUES = {"vo1": 5.6, "vo2": 12.6, "vo3": 20.5, "vo4": 27.2, "vo5": 38.9, "vo6": 55.6, "vo7": 60.5, "vo8": 66.6}
NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def hz(name: str) -> float:
    n, o = name[:-1].replace("b", "#") if "b" in name[1:-1] else name[:-1], int(name[-1])
    if "b" in name[:-1] and len(name) == 3:   # flats: Bb -> A#
        n = {"Bb": "A#", "Eb": "D#", "Ab": "G#", "Db": "C#", "Gb": "F#"}[name[:2]]
    return 440.0 * 2 ** ((NOTE[n] + 12 * (o + 1) - 69) / 12)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def place(buf, x, t, gain=1.0):
    i = int(t * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i] * gain


def piano(f, dur=3.2, vel=0.5):
    t = np.arange(int(dur * SR)) / SR
    B = 0.00035
    out = np.zeros_like(t)
    for k in range(1, 9):
        fk = k * f * np.sqrt(1 + B * k * k)
        if fk > 9000:
            break
        tau = 2.6 / k ** 0.65 * (220 / max(f, 80)) ** 0.25
        out += (1 / k ** 1.5) * np.sin(2 * np.pi * fk * t + rng.uniform(0, 6.28)) * np.exp(-t / tau)
    att = np.minimum(1, t / 0.006)
    felt = lp(rng.standard_normal(len(t)) * np.exp(-t / 0.012), 1800) * 0.25
    x = (out * att + felt) * vel
    return lp(x, 2600 + 2500 * vel)


def pad(freqs, dur, att=2.0, rel=2.5, level=0.12, cutoff=900):
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros_like(t)
    for f in freqs:
        for det in (-0.12, 0.0, 0.13):
            ff = f * 2 ** (det / 12)
            for n in range(1, 14):
                if ff * n > 5000:
                    break
                out += np.sin(2 * np.pi * ff * n * t + rng.uniform(0, 6.28)) / n
    env = np.minimum(1, t / att) * np.minimum(1, (dur - t) / rel)
    env *= 1 + 0.08 * np.sin(2 * np.pi * 0.11 * t)
    return lp(out * env, cutoff) * level / max(1, len(freqs))


def boom(level=0.55):
    t = np.arange(int(2.4 * SR)) / SR
    f = 34 + 38 * np.exp(-t / 0.09)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t / 0.75) + 0.3 * lp(rng.standard_normal(len(t)), 140) * np.exp(-t / 0.2)
    return np.tanh(x * 1.6) * level


def bell(f, level=0.18):
    t = np.arange(int(6 * SR)) / SR
    x = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / d)
            for r, a, d in ((1, 1, 3.5), (2.76, .45, 2.0), (5.4, .25, 1.1), (8.93, .12, .6)))
    return lp(x * np.minimum(1, t / 0.004), 5000) * level


def tick(level=0.12):
    t = np.arange(int(0.06 * SR)) / SR
    return bp(rng.standard_normal(len(t)), 2200, 5200) * np.exp(-t / 0.008) * level


def whoosh(dur, level=0.05):
    t = np.arange(int(dur * SR)) / SR
    noise = rng.standard_normal(len(t))
    lo = bp(noise, 300, 900)
    hi = bp(noise, 1200, 3200)
    mix = np.sin(np.pi * t / dur) ** 2
    return (lo * (1 - t / dur) + hi * (t / dur)) * mix * level


def reverb(x, seconds=2.4, wet=0.24):
    t = np.arange(int(seconds * SR)) / SR
    irs = []
    for _ in range(2):
        ir = rng.standard_normal(len(t)) * np.exp(-t / (seconds / 6.5))
        ir = lp(ir, 5200)
        irs.append(ir / np.sqrt(np.sum(ir ** 2)))
    return [x * (1 - wet) + fftconvolve(x, ir)[: len(x)] * wet for ir in irs]


def arp(buf, t0, t1, notes, step, vel=0.32, accent=0.12):
    t, i = t0, 0
    while t < t1 - 0.05:
        v = vel + (accent if i % len(notes) == 0 else 0)
        place(buf, piano(hz(notes[i % len(notes)]), vel=v), t)
        t += step
        i += 1


def music() -> np.ndarray:
    m = np.zeros(N)
    # room tone and river under the opening photographs
    room = lp(rng.standard_normal(N), 650) * 0.035
    river = bp(rng.standard_normal(N), 280, 2400) * 0.02 * (1 + 0.3 * np.sin(2 * np.pi * 0.23 * np.arange(N) / SR))
    env = np.clip((np.arange(N) / SR - 0.3) / 1.7, 0, 1) * np.clip((13.0 - np.arange(N) / SR) / 1.5, 0, 1)
    m += (room + river) * env
    # pads: D minor, Bb for the before/after, D minor, Bb for the lidar, then home to D major
    place(m, pad([hz("D2"), hz("A2"), hz("D3")], 11.2, att=4.0, level=0.14), 1.4)
    place(m, pad([hz("A#1"), hz("F2"), hz("D3")], 8.6, att=1.2, level=0.15), 11.8)
    place(m, pad([hz("D2"), hz("A2"), hz("F3")], 6.5, att=1.0, level=0.13), 19.9)
    place(m, pad([hz("A#1"), hz("F2"), hz("D3")], 6.6, att=1.0, level=0.13), 25.8)
    place(m, pad([hz("D2"), hz("A2"), hz("F3")], 6.4, att=0.6, level=0.15, cutoff=1300), 31.9)
    place(m, pad([hz("F2"), hz("C3"), hz("A3")], 10.4, att=1.6, level=0.09, cutoff=700), 37.9)
    place(m, pad([hz("D2"), hz("A2"), hz("F#3")], 5.6, att=1.4, level=0.12, cutoff=1100), 54.8)
    place(m, pad([hz("G1"), hz("D2"), hz("B3")], 3.2, att=0.5, level=0.12, cutoff=1100), 60.0)
    place(m, pad([hz("A1"), hz("E2"), hz("C#4")], 3.0, att=0.5, level=0.12, cutoff=1100), 62.8)
    place(m, pad([hz("D2"), hz("A2"), hz("F#3"), hz("D4")], 7.2, att=0.4, rel=4.5, level=0.16, cutoff=1500), 65.5)
    # piano
    place(m, piano(hz("D3"), dur=5, vel=0.42), 5.0)
    place(m, piano(hz("A4"), vel=0.28), 17.8)
    place(m, piano(hz("F4"), vel=0.24), 18.5)
    arp(m, 20.0, 26.0, ["D4", "A4", "F4", "A4"], BEAT, 0.26)
    arp(m, 26.0, 32.0, ["A#3", "F4", "D4", "F4"], BEAT, 0.27)
    arp(m, 32.0, 38.0, ["D4", "A4", "F4", "A4", "E4", "A4", "F4", "D5"], BEAT / 2, 0.24, 0.1)
    for k, tt in enumerate(np.arange(32.0, 38.0, BEAT)):
        place(m, boom(0.08 if k % 2 else 0.12)[: int(0.4 * SR)], tt)
    arp(m, 38.0, 47.6, ["F3", "C4", "A4", "C4"], BEAT * 2, 0.2, 0.06)
    place(m, piano(hz("D3"), dur=5, vel=0.3), 50.2)
    arp(m, 55.0, 60.0, ["D4", "F#4", "A4", "F#4"], BEAT, 0.27)
    arp(m, 60.0, 62.8, ["G3", "B3", "D4", "B3"], BEAT, 0.28)
    arp(m, 62.8, 65.4, ["A3", "C#4", "E4", "C#4"], BEAT, 0.3)
    place(m, piano(hz("D3"), dur=6, vel=0.5), 65.5)
    place(m, piano(hz("A3"), dur=6, vel=0.4), 65.52)
    place(m, piano(hz("F#4"), dur=6, vel=0.38), 65.55)
    # impacts, bell, ticks, whoosh
    for tt in (12.0, 26.0, 32.0, 65.5):
        place(m, boom(), tt)
    place(m, bell(hz("D5")), 65.95)
    place(m, bell(hz("A5"), 0.08), 66.25)
    for tt in (34.0, 36.0):
        place(m, tick(0.18), tt)
    for i in range(1, 6):
        place(m, tick(0.08), 56.9 + i * 0.22)
    place(m, whoosh(4.2), 13.3)
    place(m, whoosh(3.0, 0.035), 26.8)
    L, R = reverb(m)
    out = np.stack([L, R], 1)
    fade = np.clip((DUR - np.arange(N) / SR) / 3.0, 0, 1)[:, None]
    return out * fade


def _read(path: str) -> tuple[np.ndarray, int]:
    from scipy.io import wavfile

    sr, x = wavfile.read(path)
    if x.dtype.kind == "i":
        x = x / float(np.iinfo(x.dtype).max)
    return x.astype("float64"), sr


def _write(path: str, x: np.ndarray) -> None:
    from scipy.io import wavfile

    wavfile.write(path, SR, x.astype("float32"))


def vo() -> np.ndarray:
    v = np.zeros(N)
    for name, t in VO_CUES.items():
        x, sr = _read(os.path.join(A, "vo", f"{name}.wav"))
        if sr != SR:
            x = resample_poly(x, SR // 1000, sr // 1000)
        place(v, x, t)
    return v


def main() -> None:
    os.makedirs(BUILD, exist_ok=True)
    m = music()
    m = m / np.max(np.abs(m)) * 0.7
    _write(os.path.join(BUILD, "music.wav"), m)
    _write(os.path.join(BUILD, "vo.wav"), vo())
    mix = os.path.join(BUILD, "mix.wav")
    fc = ("[1:a]highpass=f=90,equalizer=f=220:t=q:w=1:g=-2,equalizer=f=3600:t=q:w=1.2:g=2.5,"
          "acompressor=threshold=-22dB:ratio=3:attack=8:release=160:makeup=2,aformat=channel_layouts=stereo,asplit=2[v][sc];"
          "[0:a]highpass=f=38,equalizer=f=85:t=q:w=1.1:g=-6,equalizer=f=180:t=q:w=1:g=-2[mq];"
          "[mq][sc]sidechaincompress=threshold=0.02:ratio=7:attack=30:release=420[md];"
          "[md][v]amix=inputs=2:weights='0.82 1.0':normalize=0,"
          "loudnorm=I=-16:TP=-1.5:LRA=11[out]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(BUILD, "music.wav"), "-i",
                    os.path.join(BUILD, "vo.wav"), "-filter_complex", fc, "-map", "[out]", "-ar", "48000", mix], check=True)
    pic = os.path.join(BUILD, "picture.mp4")
    if os.path.exists(pic):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-i", mix, "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "256k", "-shortest", "-movflags", "+faststart",
                        os.path.join(BUILD, "groma_launch.mp4")], check=True)
    print(json.dumps({"music": "build/music.wav", "mix": mix, "film": os.path.exists(pic)}))


if __name__ == "__main__":
    main()
