"""Test-only phonk-style beats, so the music system can be tested before real Audio Library
tracks are imported. These are never used in uploaded videos.

    uv run python tests/make_test_beats.py build/test-music
"""

import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

SR = 44100


def beat(bpm, seed, bars_plan):
    rng = np.random.default_rng(seed)
    spb = 60 / bpm
    total_bars = sum(n for n, _ in bars_plan)
    n = int(total_bars * 4 * spb * SR) + SR
    out = np.zeros(n, np.float32)

    def put(x, t, gain=1.0):
        a = int(t * SR)
        b = min(a + len(x), n)
        if a < n:
            out[a:b] += x[: b - a] * gain

    tt = lambda d: np.arange(int(d * SR)) / SR
    kick = np.sin(2 * np.pi * (50 + 120 * np.exp(-tt(0.4) * 35)) * tt(0.4)) * np.exp(-tt(0.4) * 7)
    clap = signal.lfilter(*signal.butter(2, [900, 3000], "band", fs=SR), rng.standard_normal(int(0.2 * SR))) * np.exp(-tt(0.2) * 25) * 3
    hat = signal.lfilter(*signal.butter(2, 7000, "high", fs=SR), rng.standard_normal(int(0.05 * SR))) * np.exp(-tt(0.05) * 90)

    def cowbell(freq, d=0.25):
        t = tt(d)
        x = np.sign(np.sin(2 * np.pi * freq * t)) + np.sign(np.sin(2 * np.pi * freq * 1.48 * t))
        x = signal.lfilter(*signal.butter(2, [freq * 0.8, freq * 4], "band", fs=SR), x)
        return x * np.exp(-t * 9) * 0.5

    def bass808(f0, f1, d):
        t = tt(d)
        f = f1 + (f0 - f1) * np.exp(-t * 6)
        return np.tanh(2.5 * np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t * 1.2) * 0.7

    root = rng.choice([41.2, 43.65, 46.25, 49.0])
    melody = rng.choice([1, 1.189, 1.335, 1.498, 1.782], size=16) * 520
    bar0 = 0
    for count, section in bars_plan:
        for bar in range(count):
            t0 = (bar0 + bar) * 4 * spb
            full = section == "drop"
            for step in range(16):  # 16th notes
                ts = t0 + step * spb / 4
                if section != "silence":
                    put(cowbell(melody[(step + bar) % 16]), ts, 0.35 if full else 0.18) if step % 2 == 0 else None
                if full:
                    put(hat, ts, 0.25 if step % 2 else 0.4)
                    if step in (0, 6, 10):
                        put(kick, ts, 0.9)
                    if step in (4, 12):
                        put(clap, ts, 0.5)
                    if step == 0:
                        put(bass808(root * 2, root, 4 * spb), ts, 0.8)
        bar0 += count
    out /= np.max(np.abs(out)) + 1e-9
    return np.stack([out, out], axis=1) * 0.9


if __name__ == "__main__":
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "build/test-music")
    dest.mkdir(parents=True, exist_ok=True)
    sf.write(dest / "Test Beat A (not for upload).wav", beat(130, 1, [(8, "intro"), (16, "drop"), (8, "intro"), (16, "drop")]), SR)
    sf.write(dest / "Test Beat B (not for upload).wav", beat(140, 2, [(4, "intro"), (24, "drop"), (4, "intro"), (16, "drop")]), SR)
    sf.write(dest / "Test Calm (not for upload).wav", beat(90, 3, [(48, "intro")]), SR)
    print(f"Wrote 3 test beats to {dest}")
