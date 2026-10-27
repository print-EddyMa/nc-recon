"""Original score and mix for launch film v2: `python video/launch/score_v2.py` (pipeline venv).

112 bpm, every section on a beat that matches compose_v2.py. All synthesised
here (no samples, no third-party licence): kick, clap, hats, sub bass on the
chord roots, plucked arpeggios, pads, risers into the drops, impacts and a
bell for the groma. Dm, Bb, F, C; the anatomy and proof sections break down;
the close resolves to D major. Voiceover from assets/vo2 (Kokoro, Apache-2.0),
music ducked under it, mastered to -14 LUFS.

Writes build/music_v2.wav, build/vo_v2.wav, build/mix_v2.wav and, with
build/picture_v2.mp4, build/groma_launch_v2.mp4.
"""
from __future__ import annotations

import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import (SR, _read, _write, bell, boom, bp, hz, lp, pad, piano, place, resample_poly,  # noqa: E402
                   reverb, tick)

A = os.path.join(HERE, "assets")
BUILD = os.path.join(HERE, "build")
BPM = 112
B = 60 / BPM
DUR = 140 * B
N = int(DUR * SR) + SR
rng = np.random.default_rng(11)
CHORDS = [("D", ["D", "F", "A"]), ("A#", ["A#", "D", "F"]), ("F", ["F", "A", "C"]), ("C", ["C", "E", "G"])]
VO = {"v1": 4.6, "v2": 11.3, "v3": 19.7, "v4": 26.0, "v5": 32.5, "v6": 36.7, "v7": 43.1, "v8": 47.5,
      "v9": 51.6, "v10": 58.1, "v11": 67.2}


def t(beat: float) -> float:
    return beat * B


def kick(level=0.9):
    tt = np.arange(int(0.45 * SR)) / SR
    f = 46 + 110 * np.exp(-tt / 0.035)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.16)
    click = bp(rng.standard_normal(len(tt)), 1500, 6000) * np.exp(-tt / 0.004) * 0.25
    return np.tanh((x + click) * 1.8) * level


def clap(level=0.5):
    tt = np.arange(int(0.32 * SR)) / SR
    env = np.exp(-tt / 0.09) * (1 + 0.6 * ((tt < 0.012) | ((tt > 0.018) & (tt < 0.026))))
    x = bp(rng.standard_normal(len(tt)), 900, 5200) * env + 0.25 * np.sin(2 * np.pi * 190 * tt) * np.exp(-tt / 0.05)
    return x * level


def hat(open_=False, level=0.16):
    tt = np.arange(int((0.22 if open_ else 0.06) * SR)) / SR
    x = rng.standard_normal(len(tt))
    x = x - lp(x, 7000)
    return x * np.exp(-tt / (0.07 if open_ else 0.014)) * level


def sub(f, dur, level=0.32):
    tt = np.arange(int(dur * SR)) / SR
    x = np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)
    env = np.minimum(1, tt / 0.008) * np.exp(-tt / (dur * 0.7))
    return lp(np.tanh(x * env * 1.4), 900) * level


def pluck(f, level=0.18):
    tt = np.arange(int(0.6 * SR)) / SR
    x = sum(np.sin(2 * np.pi * f * k * tt) / k ** 1.3 * np.exp(-tt * (6 + 3 * k)) for k in range(1, 6))
    return lp(x * np.minimum(1, tt / 0.003), 5200) * level


def riser(dur, level=0.12):
    tt = np.arange(int(dur * SR)) / SR
    x = rng.standard_normal(len(tt))
    out = np.zeros_like(x)
    seg = 2048
    for i in range(0, len(x), seg):
        k = i / len(x)
        lo = 300 + 3000 * k
        out[i:i + seg] = bp(x[i:i + seg + 512], lo, lo * 2.2)[:len(x[i:i + seg])]
    return out * (np.linspace(0, 1, len(x)) ** 2) * level


def crash(level=0.16):
    tt = np.arange(int(2.2 * SR)) / SR
    x = rng.standard_normal(len(tt))
    return (x - lp(x, 4500)) * np.exp(-tt / 0.6) * level


def build_music() -> np.ndarray:
    drums, music = np.zeros(N), np.zeros(N)
    nb = 140
    for b in range(nb):
        bar = (b // 4) % 4
        root, triad = CHORDS[bar]
        groove = (8 <= b < 36) or (48 <= b < 60) or (68 <= b < 108)
        half = 60 <= b < 68
        intro = b < 8
        if groove:
            place(drums, kick(), t(b))
            place(drums, hat(level=0.10), t(b + 0.5))
            if b >= 16:
                place(drums, hat(level=0.06), t(b + 0.25))
                place(drums, hat(level=0.06), t(b + 0.75))
            if b >= 16 and b % 2 == 1:
                place(drums, clap(), t(b))
            if b % 4 == 3 and b >= 24:
                place(drums, hat(True, 0.08), t(b + 0.5))
            for e in (0, 0.5):
                place(music, sub(hz(root + "1"), B * 0.45), t(b + e))
        if half and b % 2 == 0:
            place(drums, kick(0.75), t(b))
            if b % 4 == 2:
                place(drums, clap(0.35), t(b))
        if intro and b % 2 == 0:
            place(drums, kick(0.55), t(b))
        # arps
        if (16 <= b < 36) or (48 <= b < 60) or (68 <= b < 108):
            for k, e in enumerate((0, 0.5)):
                n = triad[(b * 2 + k) % 3]
                place(music, pluck(hz(n + "4")), t(b + e))
        if 36 <= b < 48:
            for k in range(4):
                n = triad[(b * 4 + k) % 3]
                place(music, pluck(hz(n + ("5" if k % 2 else "4")), 0.12), t(b + k * 0.25))
    # pads per bar
    for bb in range(0, 124, 4):
        root, triad = CHORDS[(bb // 4) % 4]
        lvl = 0.10 if (36 <= bb < 48 or 60 <= bb < 68) else 0.07
        place(music, pad([hz(root + "2"), hz(triad[1] + "3"), hz(triad[2] + "3")], 4 * B + 0.4, att=0.3, rel=0.5, level=lvl,
                         cutoff=1400), t(bb))
    # proof: piano chords, sub hits
    for bb, (root, triad) in ((108, CHORDS[0]), (112, CHORDS[1]), (116, CHORDS[2]), (120, CHORDS[3])):
        for k, n in enumerate(triad):
            place(music, piano(hz(n + "3"), dur=4, vel=0.34), t(bb) + k * 0.02)
    for bb in (108, 116):
        place(drums, boom(0.5), t(bb))
    # close: D major, bell on the plumb lines
    place(music, pad([hz("D2"), hz("A2"), hz("F#3"), hz("D4")], 9.0, att=0.2, rel=5.0, level=0.16, cutoff=1800), t(124))
    for k, n in enumerate(["D3", "A3", "F#4", "D5"]):
        place(music, piano(hz(n), dur=7, vel=0.45), t(124) + k * 0.03)
    place(music, bell(hz("D5")), t(124.6))
    place(music, bell(hz("A5"), 0.08), t(124.9))
    # impacts, risers, crashes, ticks
    for bb in (0, 8, 16, 36, 48, 68, 76, 96, 100, 104, 124):
        place(drums, boom(0.55), t(bb))
    for bb in (8, 16, 30, 48, 68, 80, 96, 100, 104):
        place(drums, crash(), t(bb))
    for b0, b1 in ((4, 8), (12, 16), (44, 48), (64, 68), (92, 96), (120, 124)):
        place(music, riser(t(b1) - t(b0)), t(b0))
    for k in range(7):
        place(drums, tick(0.16), t(38) + k * 0.5)
    for s in (t(69), t(69.5), t(70), t(70.5)):
        place(drums, tick(0.2), s)
    for s in np.arange(t(116.2), t(118.5), 0.09):
        place(drums, tick(0.05), s)
    # network denied: the music drops to a muffled band for two beats
    i0, i1 = int(t(80) * SR), int(t(82) * SR)
    music[i0:i1] = lp(music[i0:i1], 500)
    drums[i0:i1] = lp(drums[i0:i1], 400)
    Lm, Rm = reverb(music, 2.0, 0.22)
    L, R = Lm + drums * 0.9, Rm + drums * 0.9
    out = np.stack([L, R], 1)[: int(DUR * SR)]
    fade = np.clip((DUR - np.arange(len(out)) / SR) / 2.5, 0, 1)[:, None]
    return out * fade


def build_vo() -> np.ndarray:
    v = np.zeros(int(DUR * SR))
    for name, s in VO.items():
        x, sr = _read(os.path.join(A, "vo2", f"{name}.wav"))
        if sr != SR:
            x = resample_poly(x, SR // 1000, sr // 1000)
        place(v, x, s)
    return v


def main() -> None:
    os.makedirs(BUILD, exist_ok=True)
    m = build_music()
    m = m / np.max(np.abs(m)) * 0.8
    _write(os.path.join(BUILD, "music_v2.wav"), m)
    _write(os.path.join(BUILD, "vo_v2.wav"), build_vo())
    mix = os.path.join(BUILD, "mix_v2.wav")
    fc = ("[1:a]highpass=f=90,equalizer=f=220:t=q:w=1:g=-2,equalizer=f=3600:t=q:w=1.2:g=3,"
          "acompressor=threshold=-22dB:ratio=3.5:attack=6:release=150:makeup=2.5,aformat=channel_layouts=stereo,asplit=2[v][sc];"
          "[0:a]highpass=f=30,equalizer=f=80:t=q:w=1:g=-2,acompressor=threshold=-14dB:ratio=2.5:attack=10:release=120[mq];"
          "[mq][sc]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=300[md];"
          "[md][v]amix=inputs=2:weights='0.9 1.0':normalize=0,loudnorm=I=-14:TP=-1.0:LRA=9[out]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(BUILD, "music_v2.wav"), "-i",
                    os.path.join(BUILD, "vo_v2.wav"), "-filter_complex", fc, "-map", "[out]", "-ar", "48000", mix], check=True)
    pic = os.path.join(BUILD, "picture_v2.mp4")
    if os.path.exists(pic):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-i", mix, "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "256k", "-shortest", "-movflags", "+faststart",
                        os.path.join(BUILD, "groma_launch_v2.mp4")], check=True)
    print("mix", mix, "film", os.path.exists(pic))


if __name__ == "__main__":
    main()
