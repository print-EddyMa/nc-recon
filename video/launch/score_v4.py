"""Score and mix for launch film v4, "The scan": `python video/launch/score_v4.py` (pipeline venv).

100 bpm in D minor, synthesised here, no samples and no voice. River and a low pulse under
the footage; everything drops out for the basketballs and the toy car; a riser under
"What if the map came first?"; the full hit when the ring ignites; the kit and bass under
the scan; silence on the proof; a sub hit when the tile on the logo is knocked out of line.

Writes build/mix_v4.wav, then muxes whichever pictures exist:
build/ncrecon_launch_v4_16x9.mp4, _9x16.mp4, and the 31 s teasers _teaser_16x9.mp4 and
_teaser_9x16.mp4 (beats 24 to 56 and 96 to 116, cut on the bar).
"""
from __future__ import annotations

import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import SR, _read, _write, bell, boom, bp, hz, lp, pad, piano, place, reverb, tick, whoosh  # noqa: E402,F401

BUILD = os.path.join(HERE, "build")
BEAT = 0.6
B = lambda n: n * BEAT  # noqa: E731
DUR = 116 * BEAT
N = int(DUR * SR)
tt = np.arange(N) / SR
rng = np.random.default_rng(100)


def gate(a, b, fi=0.02, fo=0.02):
    return np.clip((tt - B(a)) / fi, 0, 1) * np.clip((B(b) - tt) / fo, 0, 1)


def kick(level=0.8):
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    f = 44 + 110 * np.exp(-t / 0.035)
    return level * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.13) + level * 0.18 * rng.standard_normal(n) * np.exp(-t / 0.003)


def hat(level=0.05, dec=0.03):
    n = int(0.16 * SR)
    x = rng.standard_normal(n)
    return level * (x - lp(x, 7000)) * np.exp(-np.arange(n) / SR / dec)


def clap(level=0.16):
    n = int(0.3 * SR)
    x = bp(rng.standard_normal(n), 900, 4200)
    t = np.arange(n) / SR
    e = np.exp(-t / 0.09) + 0.8 * np.exp(-((t - 0.012) / 0.003) ** 2) + 0.7 * np.exp(-((t - 0.024) / 0.003) ** 2)
    return level * x * e


def bass(f, dur, level=0.26):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.45 * np.tanh(2.2 * np.sin(2 * np.pi * f * t)) + 0.2 * np.sin(4 * np.pi * f * t)
    e = np.clip(t / 0.006, 0, 1) * np.clip((dur - t) / 0.04, 0, 1)
    return level * lp(x, 520) * e


def stab(notes, dur=0.9, level=0.09, cutoff=2400):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f in notes:
        for d in (-0.007, 0.0, 0.007):
            x += 2 * ((f * (1 + d) * t) % 1) - 1
    return level * lp(x, cutoff) * np.exp(-t / (dur * 0.35)) / len(notes) * 2


def riser(a, b, level=0.11):
    """Filtered noise and a rising tone from beat a to b."""
    n = int(B(b - a) * SR)
    k = np.linspace(0, 1, n)
    x = rng.standard_normal(n)
    chunks = [bp(c, 200 + 3400 * float(k[i * len(k) // 24]) ** 2, 900 + 7000 * float(k[i * len(k) // 24]) ** 2)
              for i, c in enumerate(np.array_split(x, 24))]
    noise = np.concatenate(chunks) * k ** 2.2 * level * 1.4
    tone = np.sin(2 * np.pi * np.cumsum(70 * 2 ** (k * 3)) / SR) * k ** 3 * level * 0.5
    return noise + tone


CHORDS = [("D2", ["D3", "A3", "F4"]), ("A#1", ["A#2", "F3", "D4"]), ("F2", ["F3", "C4", "A4"]), ("C2", ["C3", "G3", "E4"])]


def score() -> np.ndarray:
    m = np.zeros(N)

    # B0 to B11: the river, a heartbeat on the bar, one piano note
    river = bp(rng.standard_normal(N), 120, 900) * 0.035 * (1 + 0.25 * np.sin(2 * np.pi * 0.17 * tt))
    m += river * np.clip(tt / 1.2, 0, 1) * np.clip((B(11) - tt) / 0.1, 0, 1)
    m += river * 0.5 * gate(17, 23, 1.0, 0.1)
    for b in range(0, 11, 2):
        place(m, kick(0.34), B(b))
        place(m, kick(0.22), B(b) + 0.2)
    place(m, pad([hz("D2"), hz("A2"), hz("F3")], B(11) + 0.6, att=2.0, rel=0.8, level=0.10, cutoff=800), 0.0)
    for b, n in ((3, "D3"), (5, "F3"), (7, "A2"), (9, "A#2")):
        place(m, piano(hz(n), dur=3.4, vel=0.36), B(b))

    # B11 to B17: the drop. The basketballs and the toy car get a piano and nothing else.
    for b, n, v in ((11, "D4", 0.30), (13, "A3", 0.24), (14, "F4", 0.28), (16, "E4", 0.22)):
        place(m, piano(hz(n), dur=4.0, vel=v), B(b))

    # B17 to B23: the response, pulse in eighths, chords rising
    for b in range(17, 23):
        place(m, kick(0.46), B(b))
        place(m, hat(0.03), B(b + 0.5))
    place(m, pad([hz("A#1"), hz("F2"), hz("D3")], B(4), att=0.3, rel=0.6, level=0.12, cutoff=1100), B(17))
    place(m, pad([hz("C2"), hz("G2"), hz("E3")], B(2) + 0.4, att=0.2, rel=0.5, level=0.13, cutoff=1300), B(21))
    place(m, boom(0.34), B(23))

    # B23 to B30: the fact on black, one held note and a clock
    place(m, pad([hz("D2"), hz("A2")], B(7) + 0.2, att=0.6, rel=0.4, level=0.09, cutoff=420), B(23))
    for b in range(24, 30):
        place(m, tick(0.09), B(b))
    place(m, bell(hz("A5"), 0.05), B(27))

    # B30 to B36: terrain in the dark; the riser
    place(m, pad([hz("D1"), hz("D2"), hz("A2")], B(6) + 0.2, att=1.6, rel=0.1, level=0.14, cutoff=560), B(30))
    place(m, riser(30, 36, 0.12), B(30))
    for b in (34, 35, 35.5):
        place(m, kick(0.42), B(b))

    # B36: the ring ignites
    place(m, boom(0.8), B(36))
    place(m, kick(1.0), B(36))
    place(m, whoosh(1.4, 0.07), B(36))

    # B36 to B56: the scan. Four-bar loop, then the kit opens at B44.
    for bar in range(5):
        b0 = 36 + bar * 4
        root, tones = CHORDS[bar % 4]
        place(m, pad([hz(t) for t in tones], B(4) + 0.3, att=0.08, rel=0.3, level=0.075, cutoff=1500 + 500 * bar), B(b0))
        for i in range(8):                   # bass in eighths with the ghost notes left out
            if i not in (3, 7):
                place(m, bass(hz(root) * (2 if i in (2, 6) else 1), BEAT * 0.46, 0.20 + 0.012 * bar), B(b0 + i / 2))
        for b in (0, 1.5, 2.5):              # stabs on the off-beats
            place(m, stab([hz(t) * 2 for t in tones], 0.8, 0.075), B(b0 + b))
    for b in range(37, 56):
        if b >= 44 or b % 2 == 0:
            place(m, kick(0.76), B(b))
        if b >= 40:
            place(m, hat(0.05), B(b + 0.5))
        if b >= 44:
            place(m, hat(0.03, 0.015), B(b + 0.25))
            place(m, hat(0.03, 0.015), B(b + 0.75))
            if b % 2 == 1:
                place(m, clap(0.16), B(b))
    for b in (50, 52, 54):                   # "893 buildings." "88 seconds." "One laptop."
        place(m, boom(0.5), B(b))

    # B56 to B64: the layers, half-time and airy, one bell per layer
    for bar, (root, tones) in enumerate(CHORDS[:2]):
        b0 = 56 + bar * 4
        place(m, pad([hz(root)] + [hz(t) for t in tones], B(4) + 0.4, att=0.2, rel=0.5, level=0.10, cutoff=1400), B(b0))
        for b in (0, 2.5):
            place(m, bass(hz(root), BEAT * 0.9, 0.2), B(b0 + b))
    for b, n in ((56, "A5"), (58, "F5"), (60, "D5"), (62, "E5")):
        place(m, bell(hz(n), 0.13), B(b))
    for b in range(56, 64):
        place(m, kick(0.5 if b % 2 == 0 else 0.3), B(b))
        place(m, hat(0.03), B(b + 0.5))

    # B64 to B72: before, after. The cut to After is a hit with nothing behind it.
    place(m, pad([hz("D2"), hz("A2"), hz("D3")], B(2) + 0.1, att=0.5, rel=0.1, level=0.09, cutoff=700), B(64))
    place(m, boom(0.6), B(66))
    place(m, piano(hz("D3"), dur=4.5, vel=0.5), B(66))
    place(m, piano(hz("A3"), dur=4.0, vel=0.3), B(68))
    place(m, piano(hz("F4"), dur=4.0, vel=0.3), B(70))

    # B72 to B80: the product, driving again
    for bar, (root, tones) in enumerate((CHORDS[2], CHORDS[3])):
        b0 = 72 + bar * 4
        place(m, pad([hz(t) for t in tones], B(4) + 0.2, att=0.05, rel=0.2, level=0.08, cutoff=2200), B(b0))
        for i in range(8):
            if i not in (3, 7):
                place(m, bass(hz(root) * (2 if i in (2, 6) else 1), BEAT * 0.46, 0.22), B(b0 + i / 2))
        for b in (0, 1.5, 2.5):
            place(m, stab([hz(t) * 2 for t in tones], 0.8, 0.08), B(b0 + b))
    for b in range(72, 80):
        place(m, kick(0.74), B(b))
        place(m, hat(0.05), B(b + 0.5))
        if b % 2 == 1:
            place(m, clap(0.15), B(b))
    place(m, riser(78, 80, 0.07), B(78))

    # B80 to B88: the proof, in silence. One low note.
    place(m, boom(0.5), B(80))
    place(m, piano(hz("D2"), dur=5, vel=0.42), B(82))

    # B88 to B96: free, open source, built here
    place(m, kick(0.8), B(88))
    place(m, kick(0.8), B(90))
    place(m, pad([hz("D2"), hz("A2"), hz("F3"), hz("A3")], B(8) + 0.1, att=0.1, rel=0.1, level=0.12, cutoff=1700), B(88))
    place(m, bell(hz("D5"), 0.12), B(88))
    place(m, bell(hz("F5"), 0.12), B(90))
    place(m, piano(hz("A4"), dur=3.6, vel=0.32), B(92))
    place(m, piano(hz("D5"), dur=3.6, vel=0.32), B(93))

    # B96 to the end: the ring sweeps the logo, the tile is knocked out
    place(m, pad([hz("D1"), hz("D2"), hz("A2")], B(6), att=0.6, rel=0.1, level=0.14, cutoff=500), B(96))
    place(m, riser(97, 102, 0.11), B(97))
    place(m, boom(0.95), B(102))
    place(m, kick(1.0), B(102))
    place(m, bell(hz("D5"), 0.2), B(102))
    place(m, bell(hz("A5"), 0.1), B(102) + 0.02)
    place(m, pad([hz("D2"), hz("A2"), hz("F3"), hz("A3"), hz("D4")], DUR - B(102), att=0.04, rel=2.0, level=0.10, cutoff=1500), B(102))
    place(m, bell(hz("D6"), 0.08), B(107))
    return m


def automation() -> np.ndarray:
    """Section gains in dB, stepped on the beat: the film needs its quiet parts to be quiet."""
    steps = [(0, -9), (11, -14), (17, -4), (23, -8), (30, -2), (36, 0), (56, -2), (64, -6), (72, 0), (80, -16), (88, -3), (102, 0)]
    db = np.full(N, 0.0)
    for (b0, g), (b1, _) in zip(steps, steps[1:] + [(1e9, 0)]):
        db[(tt >= B(b0)) & (tt < B(b1))] = g
    return 10 ** (lp(db, 40) / 20)


def mux(picture: str, audio: str, out: str, extra=()) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", picture, "-i", audio, *extra, "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
                    "-movflags", "+faststart", "-shortest", out], check=True)


def teaser(aspect: str) -> None:
    """Beats 24 to 56 and 96 to 116, re-encoded, with a short audio crossfade at the join."""
    src = os.path.join(BUILD, f"ncrecon_launch_v4_{aspect}.mp4")
    a0, a1, c0, c1 = B(24), B(56), B(96), B(116)
    fc = (f"[0:v]trim={a0}:{a1},setpts=PTS-STARTPTS[v0];[0:v]trim={c0}:{c1},setpts=PTS-STARTPTS[v1];[v0][v1]concat=n=2:v=1:a=0[v];"
          f"[0:a]atrim={a0}:{a1 + 0.03},asetpts=PTS-STARTPTS[a0];[0:a]atrim={c0}:{c1},asetpts=PTS-STARTPTS[a1];"
          f"[a0][a1]acrossfade=d=0.03[a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k",
                    "-movflags", "+faststart", os.path.join(BUILD, f"ncrecon_launch_v4_teaser_{aspect}.mp4")], check=True)


def main() -> None:
    m = score() * automation()
    x = np.tanh(np.stack(reverb(m, seconds=2.2, wet=0.14), axis=1) * 1.25) * 0.9
    x[-int(1.4 * SR):] *= np.linspace(1, 0, int(1.4 * SR))[:, None]
    raw = os.path.join(BUILD, "mix_v4_raw.wav")
    wav = os.path.join(BUILD, "mix_v4.wav")
    _write(raw, x)
    # Static gain, not loudnorm's dynamic mode: that would fill in the silences the film depends on.
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", raw, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    measured = float(r.rsplit("I:", 1)[1].split("LUFS")[0])
    gain = -14.0 - measured
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", f"volume={gain:.2f}dB,alimiter=limit=0.84:level=disabled:attack=2:release=60",
                    "-ar", "48000", "-c:a", "pcm_s24le", wav], check=True)
    print(f"measured {measured:.1f} LUFS, gain {gain:+.1f} dB")
    for aspect in () if "--mix-only" in sys.argv else ("16x9", "9x16"):
        pic = os.path.join(BUILD, f"picture_v4_{aspect}.mp4")
        if os.path.exists(pic):
            out = os.path.join(BUILD, f"ncrecon_launch_v4_{aspect}.mp4")
            mux(pic, wav, out)
            teaser(aspect)
            print("wrote", out)
    print("wrote", wav)


if __name__ == "__main__":
    main()
