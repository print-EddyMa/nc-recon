"""Score and mix for the hype cut: `python video/launch/score_v5.py [--mix-only]` (pipeline venv).

150 bpm, half-time, D minor. Original music synthesised here (808, bass, horns, plucks, one
four-note motif that returns as the sound logo) over real CC0 recordings found through
Openverse: thunder, flood water, a collapsing building, a helicopter, a chainsaw, paper, a
camera shutter, a stamp, a heartbeat. Hits come from build/cues_v5.json, the same list that
drives the picture, and every print in the flash lands with its own thud.

Writes build/mix_v5.wav and, if the pictures exist, build/ncrecon_launch_v5_16x9.mp4 and
_9x16.mp4. Mastered to -13 LUFS with a limiter: static gain, so the silences stay silent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score import SR, bp, hz, lp, reverb  # noqa: E402

BUILD = os.path.join(HERE, "build")
SFX = os.path.join(HERE, "assets", "v5", "sfx")
CUES = json.load(open(os.path.join(BUILD, "cues_v5.json")))
BEAT = CUES["beat"]
END = CUES["end"]
B = lambda n: n * BEAT  # noqa: E731
DUR = B(END)
N = int(DUR * SR)
tt = np.arange(N) / SR
rng = np.random.default_rng(150)
_cache: dict[str, np.ndarray] = {}


def load(name: str) -> np.ndarray:
    """Decode a sample to stereo float, skip its leading silence, peak at 1."""
    if name not in _cache:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", os.path.join(SFX, name + ".mp3"), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
        x = np.frombuffer(raw, "float32").reshape(-1, 2).copy()
        on = np.argmax(np.abs(x).max(axis=1) > 0.02 * np.abs(x).max())
        x = x[on:]
        _cache[name] = x / (np.abs(x).max() + 1e-9)
    return _cache[name]


def put(buf: np.ndarray, x: np.ndarray, t: float, gain: float = 1.0) -> None:
    i = int(t * SR)
    if i >= len(buf) or i < 0:
        return
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    n = min(len(x), len(buf) - i)
    buf[i:i + n] += x[:n] * gain


def sample(name: str, dur: float | None = None, pitch: float = 1.0, fade: float = 0.05, start: float = 0.0) -> np.ndarray:
    x = load(name)[int(start * SR):]
    if pitch != 1.0:
        idx = np.arange(0, len(x) - 1, pitch)
        x = np.stack([np.interp(idx, np.arange(len(x)), x[:, c]) for c in (0, 1)], axis=1)
    if dur is not None:
        x = x[:int(dur * SR)].copy()
    f = min(int(fade * SR), len(x))
    x = x.copy()
    x[-f:] *= np.linspace(1, 0, f)[:, None]
    return x


def hit(buf, name, beat, gain=1.0, dur=None, pitch=1.0, start=0.0, fade=0.05):
    put(buf, sample(name, dur, pitch, fade, start), B(beat), gain)


def t_(dur):
    return np.arange(int(dur * SR)) / SR


def kick(level=1.0):
    t = t_(0.34)
    f = 46 + 170 * np.exp(-t / 0.028)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.11) + 0.22 * rng.standard_normal(len(t)) * np.exp(-t / 0.0025)
    return level * np.tanh(x * 1.6)


def bass808(f, dur, level=0.8, glide_from=None):
    t = t_(dur)
    ff = np.full(len(t), f, "float64")
    if glide_from:
        ff = f + (glide_from - f) * np.exp(-t / 0.05)
    x = np.sin(2 * np.pi * np.cumsum(ff * (1 + 0.8 * np.exp(-t / 0.012))) / SR)
    e = np.clip(t / 0.003, 0, 1) * np.clip((dur - t) / 0.03, 0, 1) * np.exp(-t / (dur * 1.4))
    return 0.42 * level * np.tanh(x * 5.0) * 0.8 * e


def saws(freqs, dur, cut0=500, cut1=3500, level=0.2, att=0.015, rel=0.2):
    """Detuned saws through a sweeping filter: horns when low, a stab when short."""
    t = t_(dur)
    x = np.zeros((len(t), 2))
    for f in freqs:
        for d, pan in ((-0.009, 0.15), (-0.003, 0.4), (0.003, 0.6), (0.009, 0.85)):
            s = 2 * ((f * (1 + d) * t + rng.random()) % 1) - 1
            x[:, 0] += s * (1 - pan)
            x[:, 1] += s * pan
    x /= len(freqs) * 2
    chunks = 24
    out = np.zeros_like(x)
    for i, idx in enumerate(np.array_split(np.arange(len(t)), chunks)):
        c = cut0 + (cut1 - cut0) * (i / chunks) ** 0.7
        out[idx, 0] = lp(x[idx, 0], c)
        out[idx, 1] = lp(x[idx, 1], c)
    e = np.clip(t / att, 0, 1) * np.clip((dur - t) / rel, 0, 1)
    return level * out * e[:, None]


def pluck(f, dur=0.5, level=0.2):
    t = t_(dur)
    x = 2 * ((f * t) % 1) - 1 + 0.6 * (2 * ((f * 2.005 * t) % 1) - 1)
    return level * lp(x, 2600) * np.exp(-t / 0.13)


def riser(dur, level=0.3):
    t = t_(dur)
    k = t / dur
    noise = rng.standard_normal(len(t))
    parts = np.array_split(np.arange(len(t)), 30)
    out = np.zeros(len(t))
    for i, idx in enumerate(parts):
        q = i / 30
        out[idx] = bp(noise[idx], 300 + 4500 * q ** 2, 1200 + 9000 * q ** 2)
    tone = np.sin(2 * np.pi * np.cumsum(60 * 2 ** (k * 4)) / SR) * 0.4
    return level * (out * 0.8 + tone) * k ** 2.4


def bell(f, dur=2.2, level=0.3):
    t = t_(dur)
    x = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t / 0.3) + 0.25 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t / 0.12)
    return level * x * np.exp(-t / 0.7)


CHORDS = [("D", ["D4", "F4", "A4"]), ("A#", ["A#3", "D4", "F4"]), ("F", ["F3", "A3", "C4"]), ("C", ["C4", "E4", "G4"])]
MOTIF = [(0, "D5"), (0.75, "F5"), (1.5, "A5"), (3, "G5"), (4, "D5"), (4.75, "F5"), (5.5, "C6"), (7, "A5")]


def crash(buf, beat, level=0.7):
    t = t_(2.4)
    n = rng.standard_normal((len(t), 2))
    x = np.stack([c - lp(c, 3000) for c in n.T], axis=1)
    put(buf, x * (np.exp(-t / 0.5) * level * 0.5)[:, None], B(beat))


def groove(mus, kicks, b0, b1, full=True, snare=True):
    """Half-time trap: snare on the third beat of each four, 808 under the chord roots."""
    for bar, b in enumerate(np.arange(b0, b1, 8)):
        for off, c, nb in ((0, 0, 1.5), (1.5, 0, 2.0), (4, 1, 1.5), (5.5, 2, 1.25), (7, 3, 1.0)):
            if b + off >= b1:
                continue
            root = hz(CHORDS[c][0] + "1")
            put(kicks, kick(1.0), B(b + off))
            put(mus, bass808(root, B(nb), 0.72, glide_from=root * 1.5 if off in (5.5, 7) else None), B(b + off))
        if snare:
            for off in (2, 6):
                if b + off < b1:
                    hit(mus, "snare_1", b + off, 0.95, pitch=0.9)
                    hit(mus, "clap_0", b + off, 0.55, dur=0.25)
        if full:
            for k in np.arange(0, 8, 0.5):
                if b + k < b1:
                    hit(mus, "hat_1", b + k, 0.5 if k % 1 == 0 else 0.34)
            for k in np.arange(6.5, 7, 0.0833):                     # the hat roll
                if b + k < b1:
                    hit(mus, "hat_1", b + k, 0.36)


def horns(mus, b0, b1, level=0.13):
    for i, b in enumerate(np.arange(b0, b1, 4)):
        _r, tones = CHORDS[i % 4]
        fs = [hz(n) / 2 for n in tones]
        put(mus, saws(fs, B(min(4, b1 - b)) + 0.1, 700, 3200, level * 2.8), B(b))


def motif(mus, b0, gain=1.0, oct_=1.0):
    for k, n in MOTIF:
        put(mus, saws([hz(n) * oct_, hz(n) * oct_ / 2], BEAT * 0.9, 1800, 4800, 0.6 * gain, att=0.008, rel=0.06), B(b0 + k))


def score():
    mus = np.zeros((N, 2))
    fx = np.zeros((N, 2))
    kicks = np.zeros((N, 2))

    # ---------------- HOOK, beats 0 to 8: the storm
    hit(fx, "thunder_0", 0, 0.85, dur=3.2, fade=1.0)
    crash(fx, 0, 0.5)
    hit(fx, "impact_0", 0, 0.7, dur=3.0, fade=1.0)
    put(kicks, kick(1.0), B(0))
    put(mus, bass808(hz("D1"), B(4), 0.8), B(0))
    put(mus, saws([hz("D2"), hz("A2"), hz("D3")], B(4), 300, 1200, 0.2, att=0.04, rel=0.5), B(0))
    put(fx, sample("wind_1", B(8), fade=0.2), 0.0, 0.3)
    put(fx, sample("rain_1", B(8), start=2.0, fade=0.2), 0.0, 0.22)
    put(kicks, kick(0.9), B(4))
    hit(fx, "impact_1", 4, 0.6, dur=2.0, fade=0.8)
    put(mus, bass808(hz("A#0"), B(4), 0.8), B(4))
    put(mus, saws([hz("A#1"), hz("F2"), hz("D3")], B(4), 300, 1600, 0.2, att=0.04, rel=0.3), B(4))

    # ---------------- FLASH, beats 8 to 28: gets faster until it breaks
    for f, n, kind in CUES["flash"]:                                           # every print lands
        t = f / 30
        put(fx, sample("stamp_1", 0.14, pitch=1.0 + rng.random() * 0.3, fade=0.03), t, 0.75 if n >= 6 else 0.5)
        put(fx, sample("paper_1", 0.12, pitch=1.3 + rng.random() * 0.4, fade=0.03), t, 0.6 if n >= 4 else 0.3)
    for b in np.arange(8, 28, 2):
        put(kicks, kick(0.75), B(b))
    for b in np.arange(16, 24, 1):
        put(kicks, kick(0.75), B(b))
    for b in np.arange(24, 26, 0.5):
        put(kicks, kick(0.8), B(b))
    for b in np.arange(26, 27.5, 0.25):
        hit(mus, "snare_1", b, 0.3 + 0.3 * (b - 26) / 1.5)
    notes = ["D4", "F4", "A4", "D5"]
    for i, b in enumerate(np.arange(8, 27.5, 0.5)):
        put(mus, pluck(hz(notes[i % 4]) * (2 if b >= 20 else 1), 0.42, 0.24 + 0.14 * (b - 8) / 20), B(b))
    for i, b in enumerate(np.arange(8, 28, 4)):
        put(mus, saws([hz(n) for n in CHORDS[i % 4][1]], B(4) + 0.1, 300, 900 + 2200 * (b - 8) / 20, 0.06 + 0.07 * (b - 8) / 20), B(b))
    put(mus, np.stack([riser(B(8), 0.26)] * 2, axis=1), B(20))
    put(fx, sample("reverse_1"), B(27.5) - len(load("reverse_1")) / SR, 0.5)

    # ---------------- IMPACT, beats 28 to 44
    crash(fx, 28)
    hit(fx, "impact_0", 28, 0.8, dur=4, fade=1.5)
    hit(fx, "debris_0", 28, 0.8, dur=B(6), fade=0.6)
    hit(fx, "thunder_1", 28, 0.5, dur=3, fade=1)
    hit(fx, "river_1", 28, 0.34, dur=B(16), fade=0.4)
    hit(fx, "helicopter_1", 36, 0.5, dur=B(8), fade=0.4, start=3.0)
    hit(fx, "chainsaw_0", 40, 0.26, dur=B(4), start=3.0, fade=0.2)
    put(mus, saws([hz("D2"), hz("A2"), hz("D3"), hz("F3")], B(8), 350, 2600, 0.2, rel=0.3), B(28))
    groove(mus, kicks, 28, 44)
    horns(mus, 36, 44, 0.12)
    for b in (32, 36, 40):
        hit(fx, "stamp_1", b, 0.7, fade=0.03)
    hit(fx, "tapestop_1", 42.5, 0.0, dur=0.01)

    # ---------------- THE FACT and THE QUESTION, beats 44 to 54: everything stops
    hit(fx, "impact_1", 44, 0.5, dur=2.5, fade=1.5)
    put(mus, bass808(hz("D1"), B(6), 0.5), B(44))
    for b in range(45, 50):
        put(fx, sample("shutter_0", 0.05, pitch=0.8, fade=0.02), B(b), 0.3)
    hit(fx, "heartbeat_0", 50, 0.75, dur=B(4), fade=0.1)
    put(mus, np.stack([riser(B(3.5), 0.14)] * 2, axis=1), B(50.5))
    put(fx, sample("reverse_0"), B(54) - len(load("reverse_0")) / SR, 0.45)

    # ---------------- THE RING, beats 54 to 72
    crash(fx, 54)
    hit(fx, "impact_0", 54, 0.8, dur=5, fade=2)
    hit(fx, "sub_2", 54, 0.5)
    hit(fx, "whoosh_0", 54, 0.7, dur=2.4, fade=0.6)
    put(mus, saws([hz("D2"), hz("A2"), hz("D3"), hz("F3"), hz("A3")], B(8), 400, 3200, 0.2, rel=0.3), B(54))
    groove(mus, kicks, 54, 72)
    horns(mus, 62, 72, 0.13)
    motif(mus, 54, 0.9)
    motif(mus, 62, 1.1)
    for b in np.arange(55, 64, 0.5):
        put(fx, sample("typewriter_0", 0.05, pitch=1.6, fade=0.02), B(b), 0.14)   # the count running
    for b in (67, 69, 71):
        hit(fx, "impact_1", b, 0.8, dur=1.2, fade=0.5)
        put(kicks, kick(1.0), B(b))

    # ---------------- EVERY PRODUCT, beats 72 to 96
    groove(mus, kicks, 72, 80)
    horns(mus, 72, 80, 0.12)
    motif(mus, 72, 1.0, 2.0)
    for b, w in ((72, "whoosh_2"), (74, "whoosh_3"), (76, "whoosh_4"), (78, "whoosh_2")):
        hit(fx, w, b - 0.25, 0.7)
        put(mus, bell(hz({72: "A5", 74: "F5", 76: "D5", 78: "E5"}[b]), 1.4, 0.13), B(b))
    for b in (80, 81, 82, 83):
        put(fx, sample("shutter_0", 0.09, fade=0.02), B(b), 1.0)
        crash(fx, b, 0.18)
        put(kicks, kick(0.9), B(b))
        put(mus, bass808(hz("D1"), BEAT * 0.8, 0.6), B(b))
    hit(fx, "impact_0", 84, 0.8, dur=2, fade=1)
    hit(fx, "stamp_0", 84, 0.8, dur=0.5)
    groove(mus, kicks, 84, 96)
    horns(mus, 84, 96, 0.13)
    motif(mus, 88, 1.1)
    for b, w in ((86, "whoosh_3"), (88, "whoosh_2"), (90, "whoosh_4"), (92, "whoosh_3"), (94, "whoosh_2")):
        hit(fx, w, b - 0.25, 0.6)
    for b in np.arange(88, 89, 0.25):
        put(fx, sample("typewriter_0", 0.06, pitch=1.3, fade=0.02), B(b), 0.3)
    for b in (94, 95, 95.5):
        hit(fx, "stamp_1", b, 0.7)

    # ---------------- THE PROOF, beats 96 to 104: almost nothing
    hit(fx, "impact_1", 96, 0.5, dur=2.5, fade=1.5)
    put(mus, bass808(hz("D1"), B(8), 0.42), B(96))
    put(mus, bell(hz("D5"), 2.6, 0.12), B(98))
    put(mus, bell(hz("A5"), 2.6, 0.1), B(100))

    # ---------------- FREE. OPEN SOURCE.
    for b in (104, 105):
        hit(fx, "stamp_0", b, 0.8, dur=0.4)
        put(kicks, kick(1.0), B(b))
        put(mus, bass808(hz("D1"), BEAT, 0.7), B(b))

    # ---------------- THE LOGO: the ring crosses, the tile is knocked out, the name resolves
    put(mus, np.stack([riser(B(7), 0.1)] * 2, axis=1), B(106))
    put(mus, saws([hz("D2"), hz("A2"), hz("D3")], B(7), 300, 1500, 0.2, att=0.3, rel=0.2), B(106))
    put(fx, sample("reverse_1"), B(113) - len(load("reverse_1")) / SR, 0.5)
    crash(fx, 113, 0.5)
    hit(fx, "impact_0", 113, 0.45, dur=5, fade=2.5)
    hit(fx, "sub_0", 113, 0.5)
    put(kicks, kick(1.0), B(113))
    for k, n in MOTIF[:4]:                                                     # the sound logo
        put(mus, bell(hz(n), 3.0, 0.24), B(113 + k))
    put(mus, saws([hz("D3"), hz("A3"), hz("D4"), hz("F4")], DUR - B(113), 700, 2600, 0.2, att=0.05, rel=2.4), B(113))
    for i in range(9):
        put(fx, sample("typewriter_0", 0.07, pitch=1.2, fade=0.02), B(120.5 + i * 0.25), 0.34)
    hit(fx, "bell_0", 122.5, 0.26, dur=3.0, fade=1.5)
    return mus, fx, kicks


def automation():
    """Section gains in dB on the music bus, stepped on the beat."""
    steps = [(0, -2), (8, -1), (20, 0), (28, 0), (44, -8), (50, -14), (54, 0), (96, -10), (104, 0), (106, -3), (113, -2)]
    db = np.zeros(N)
    for (b0, g), (b1, _) in zip(steps, steps[1:] + [(1e9, 0)]):
        db[(tt >= B(b0)) & (tt < B(b1))] = g
    return (10 ** (lp(db, 40) / 20))[:, None]


def main() -> None:
    mus, fx, kicks = score()
    env = lp(np.abs(kicks).max(axis=1), 16)
    duck = (1 - 0.5 * np.clip(env * 1.8, 0, 1))[:, None]                       # the pump: kick ducks the music
    m = (mus * duck + kicks * 0.33) * automation()
    wetL, _ = reverb((fx[:, 0] + m[:, 0] * 0.3), seconds=1.6, wet=1.0)
    _, wetR = reverb((fx[:, 1] + m[:, 1] * 0.3), seconds=1.6, wet=1.0)
    x = m + fx + np.stack([wetL, wetR], axis=1)[:N] * 0.12
    x = np.stack([c - lp(c, 34) for c in x.T], axis=1)                         # nothing a phone cannot use below 34 Hz
    x = x + 0.6 * np.stack([c - lp(c, 3200) for c in x.T], axis=1)             # air, for phone speakers
    x = np.tanh(x * 1.1) * 0.92
    x[-int(1.6 * SR):] *= np.linspace(1, 0, int(1.6 * SR))[:, None]
    raw = os.path.join(BUILD, "mix_v5_raw.wav")
    wav = os.path.join(BUILD, "mix_v5.wav")
    from scipy.io import wavfile
    wavfile.write(raw, SR, x.astype("float32"))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", raw, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    measured = float(r.rsplit("I:", 1)[1].split("LUFS")[0])
    gain = -13.0 - measured
    y = x * 10 ** (gain / 20)
    y = 0.84 * np.tanh(y / 0.84)                                               # soft ceiling at -1.5 dBFS, so platform re-encodes do not clip
    wavfile.write(wav, SR, y.astype("float32"))
    print(f"measured {measured:.1f} LUFS, gain {gain:+.1f} dB")
    for aspect in () if "--mix-only" in sys.argv else ("16x9", "9x16"):
        pic = os.path.join(BUILD, f"picture_v5_{aspect}.mp4")
        out = os.path.join(BUILD, f"ncrecon_launch_v5_{aspect}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pic, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", out], check=True)
        print("wrote", out)


if __name__ == "__main__":
    main()
