"""Measure a track: tempo, and level and band balance over time. `analyze_music.py <file> [step]`."""
import subprocess, sys
import numpy as np
SR = 22050
def load(p):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", p, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, "float32")
def bands(x, hop=2205):
    n = len(x) // hop
    out = np.zeros((n, 4))
    w = np.hanning(hop * 2)
    fr = np.fft.rfftfreq(hop * 2, 1 / SR)
    lo, mi, hi = fr < 120, (fr >= 120) & (fr < 2000), fr >= 2000
    for i in range(n - 1):
        f = np.abs(np.fft.rfft(x[i * hop:i * hop + hop * 2] * w)) ** 2 + 1e-12
        out[i] = 10 * np.log10(np.sum(x[i * hop:i * hop + hop * 2] ** 2) / (hop * 2) + 1e-12), 10 * np.log10(f[lo].sum()), 10 * np.log10(f[mi].sum()), 10 * np.log10(f[hi].sum())
    return out
def tempo(x, a=0, b=None):
    hop = 256
    s = x[int(a * SR):int(b * SR) if b else None]
    n = len(s) // hop
    e = np.array([np.sqrt((s[i * hop:(i + 1) * hop] ** 2).mean()) for i in range(n)])
    o = np.clip(np.diff(np.log(e + 1e-4)), 0, None); o -= o.mean()
    ac = np.fft.irfft(np.abs(np.fft.rfft(o, 2 * len(o))) ** 2)[:len(o)]
    d = hop / SR
    r = [(ac[int(round(60 / b_ / d))], b_) for b_ in np.arange(60, 181, 0.5)]
    return [t for _, t in sorted(r, reverse=True)[:4]]
if __name__ == "__main__":
    x = load(sys.argv[1]); step = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    b = bands(x); k = int(step / 0.1)
    print(sys.argv[1], "dur", round(len(x) / SR, 1), "tempo", tempo(x))
    for i in range(0, len(b), k):
        c = b[i:i + k].mean(axis=0)
        print(f"{i * 0.1:6.1f}  rms {c[0]:6.1f}  low {c[1]:6.1f}  mid {c[2]:6.1f}  hi {c[3]:6.1f}  {'#' * max(0, int((c[0] + 40) / 2))}")
