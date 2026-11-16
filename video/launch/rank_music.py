"""Rank candidate tracks against what product launch films measured. `rank_music.py <files>`"""
import sys
import numpy as np
from scipy.signal import butter, sosfilt
from analyze_music import load, bands, SR
def pulse(x):
    y = sosfilt(butter(3, [800, 9000], 'bp', fs=SR, output='sos'), x)
    hop = 110; dt = hop / SR
    e = np.sqrt(np.convolve(y ** 2, np.ones(hop) / hop, 'same')[::hop]); o = np.clip(np.diff(np.log(e + 1e-3)), 0, None); o -= o.mean()
    ac = np.fft.irfft(np.abs(np.fft.rfft(o, 2 * len(o))) ** 2)[:len(o)]
    lags = np.arange(int(.25 / dt), int(1.2 / dt)); v = ac[lags] / ac[0]
    i = int(np.argmax(v))
    return round(60 / (lags[i] * dt), 1), round(float(v[i]), 3)
print(f"{'track':46s}{'dur':>5}{'bpm':>7}{'pulse':>7}{'rms':>6}{'low-mid':>8}{'hi-mid':>7}{'lra':>5}{'build':>6}")
for f in sys.argv[1:]:
    x = load(f); b = bands(x)
    if len(b) < 200: continue
    act = b[:, 0] > b[:, 0].max() - 25
    bpm, str_ = pulse(x)
    k = len(b) // 4
    n = f.split('/')[-1].replace('.mp3', '')[-44:]
    print(f"{n:46s}{len(x)/SR:5.0f}{bpm:7.1f}{str_:7.3f}{b[act,0].mean():6.1f}{(b[act,1]-b[act,2]).mean():8.1f}{(b[act,3]-b[act,2]).mean():7.1f}{np.percentile(b[act,0],95)-np.percentile(b[act,0],10):5.0f}{b[k*2:k*3,0].mean()-b[:k,0].mean():6.1f}")
