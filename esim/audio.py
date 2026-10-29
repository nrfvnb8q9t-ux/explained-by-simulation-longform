"""Sound effects, music and the final mix, all synthesised from scratch.

Every sound is generated from random parameters seeded by the video, so no two videos share a
sound file. Nothing is loaded from a sample library.
"""

import math

import numpy as np
from scipy import signal

SR = 48000


def _t(dur):
    return np.arange(int(dur * SR), dtype=np.float32) / SR


def _noise(n, rng, kind="white"):
    x = rng.standard_normal(n).astype(np.float32)
    if kind == "pink":
        b, a = [0.049922, -0.095993, 0.050612, -0.004408], [1, -2.494956, 2.017265, -0.522189]
        x = signal.lfilter(b, a, x).astype(np.float32) * 4
    elif kind == "brown":
        x = np.cumsum(x) / 60
        x = signal.sosfilt(signal.butter(1, 20, "highpass", fs=SR, output="sos"), x).astype(np.float32)
    return x


def _filt(x, kind, freq, order=4):
    sos = signal.butter(order, freq, kind, fs=SR, output="sos")
    return signal.sosfilt(sos, x, axis=0).astype(np.float32)


def _sweep_filter(x, f_start, f_end, curve=None, q=1.4, blocks=48):
    """Band-pass x with a centre frequency that moves from f_start to f_end (log scale),
    using overlapping filtered blocks."""
    n = len(x)
    hop = n // blocks
    win = np.hanning(hop * 2).astype(np.float32)
    out = np.zeros(n + hop * 2, np.float32)
    for i in range(blocks):
        k = i / max(blocks - 1, 1)
        k = curve(k) if curve else k
        fc = f_start * (f_end / f_start) ** k
        lo, hi = fc / q, min(fc * q, SR / 2 - 100)
        seg = x[i * hop: i * hop + hop * 2]
        if len(seg) < 16:
            continue
        y = _filt(seg, "bandpass", [lo, hi], order=2)
        out[i * hop: i * hop + len(y)] += y * win[:len(y)]
    return out[:n]


def _env(n, attack, release, shape=2.0):
    t = np.linspace(0, 1, n, dtype=np.float32)
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.clip((1 - t) / max(release, 1e-4), 0, 1)
    return (a * r) ** shape


def _stereo(mono, pan):
    """Constant-power pan; pan can be a number (-1 left .. 1 right) or an array the same length."""
    pan = np.clip(pan, -1, 1)
    ang = (pan + 1) * math.pi / 4
    return np.stack([mono * np.cos(ang), mono * np.sin(ang)], axis=1).astype(np.float32)


def _norm(x, peak=0.9):
    m = np.max(np.abs(x)) + 1e-9
    return (x / m * peak).astype(np.float32)


# ---------------------------------------------------------------- sound effects

def whoosh(rng, dur=None):
    dur = dur or rng.uniform(0.7, 1.5)
    n = int(dur * SR)
    peak = rng.uniform(0.45, 0.7)
    curve = lambda k: (k / peak) if k < peak else 1 - (k - peak) / (1 - peak) * 0.6
    x = _sweep_filter(_noise(n, rng, "pink"), rng.uniform(250, 450), rng.uniform(2500, 5000), curve, q=1.6)
    t = np.linspace(0, 1, n, dtype=np.float32)
    env = np.where(t < peak, (t / peak) ** 2.2, ((1 - t) / (1 - peak)) ** 1.6)
    d = rng.choice([-1, 1])
    return _stereo(_norm(x * env), d * (t * 1.4 - 0.7))


def impact(rng, dur=None):
    dur = dur or rng.uniform(2.0, 3.2)
    t = _t(dur)
    f0 = rng.uniform(55, 80)
    phase = 2 * np.pi * np.cumsum(f0 * np.exp(-t * rng.uniform(5, 9)) + rng.uniform(28, 38)) / SR
    boom = np.sin(phase) * np.exp(-t * rng.uniform(1.6, 2.6))
    crack = _filt(_noise(len(t), rng), "lowpass", rng.uniform(1500, 3500)) * np.exp(-t * rng.uniform(14, 24))
    tail = _filt(_noise(len(t), rng, "brown"), "lowpass", 200) * np.exp(-t * 1.2) * 0.6
    x = _norm(boom * 1.0 + crack * 0.35 + tail)
    x[: int(0.004 * SR)] *= np.linspace(0, 1, int(0.004 * SR))
    return _stereo(x, 0) + _stereo(_filt(x, "highpass", 300) * 0.2, rng.uniform(-0.5, 0.5))


def rumble(rng, dur=None):
    dur = dur or rng.uniform(3, 5)
    n = int(dur * SR)
    x = _filt(_noise(n, rng, "brown"), "lowpass", rng.uniform(90, 160))
    t = _t(dur)
    lfo = 0.6 + 0.4 * np.sin(2 * np.pi * rng.uniform(0.2, 0.8) * t + rng.uniform(0, 6))
    return _stereo(_norm(x * lfo * _env(n, 0.25, 0.35, 1.0)), 0)


def riser(rng, dur=None):
    dur = dur or rng.uniform(2.5, 4)
    t = _t(dur)
    n = len(t)
    k = t / dur
    noise = _sweep_filter(_noise(n, rng, "pink"), 300, rng.uniform(5000, 8000), lambda v: v ** 1.5, q=1.8)
    base = rng.uniform(90, 140)
    freq = base * 2 ** (k ** 1.6 * rng.uniform(1.5, 2.5))
    tone = sum(np.sin(2 * np.pi * np.cumsum(freq * m) / SR) / m for m in (1, 1.5, 2.01))
    env = k ** 2.5
    env[-int(0.03 * SR):] *= np.linspace(1, 0, int(0.03 * SR))
    return _stereo(_norm((noise * 0.8 + tone * 0.35) * env), 0)


def tick(rng, dur=None):
    dur = 0.18
    t = _t(dur)
    f0 = rng.uniform(1800, 3200)
    x = np.sin(2 * np.pi * f0 * t) * np.exp(-t * rng.uniform(40, 70))
    x += _filt(_noise(len(t), rng), "highpass", 4000) * np.exp(-t * 300) * 0.5
    return _stereo(_norm(x, 0.6), rng.uniform(-0.3, 0.3))


def shimmer(rng, dur=None):
    dur = dur or rng.uniform(2, 3.5)
    t = _t(dur)
    out = np.zeros((len(t), 2), np.float32)
    for _ in range(int(rng.integers(10, 18))):
        f0 = rng.uniform(1800, 7000)
        start = rng.uniform(0, dur * 0.6)
        tt = np.clip(t - start, 0, None)
        x = np.sin(2 * np.pi * f0 * tt) * np.exp(-tt * rng.uniform(2, 5)) * (t >= start)
        out += _stereo(x.astype(np.float32), rng.uniform(-0.8, 0.8))
    return _norm(out, 0.5)


def power_down(rng, dur=None):
    """A falling 'switching off' tone, e.g. the Sun vanishing."""
    dur = dur or rng.uniform(1.6, 2.6)
    t = _t(dur)
    f = rng.uniform(500, 900) * np.exp(-t * rng.uniform(1.8, 2.8)) + 30
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3.01 * ph)
    x = _filt(x, "lowpass", 2500) * np.exp(-t * 1.2) * _env(len(t), 0.01, 0.2, 1)
    return _stereo(_norm(x), 0)


def pop(rng, dur=None):
    """A soft UI 'pop' for labels and cards appearing."""
    dur = 0.25
    t = _t(dur)
    f = rng.uniform(500, 800) * (1 + 2 * np.exp(-t * 60))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * rng.uniform(25, 40))
    return _stereo(_norm(x, 0.6), rng.uniform(-0.2, 0.2))


def chalk_scratch(rng, dur=None):
    """Chalk on a board, for whiteboard drawing."""
    dur = dur or rng.uniform(0.8, 1.6)
    n = int(dur * SR)
    t = _t(dur)
    strokes = (np.sin(2 * np.pi * rng.uniform(5, 9) * t) > rng.uniform(-0.3, 0.3)).astype(np.float32)
    strokes = _filt(strokes, "lowpass", 60, order=2)
    x = _filt(_noise(n, rng), "bandpass", [rng.uniform(1500, 2500), rng.uniform(5000, 7000)], order=2)
    return _stereo(_norm(x * np.clip(strokes, 0, 1) * _env(n, 0.05, 0.1, 1), 0.35), rng.uniform(-0.3, 0.3))


def bass_808(rng, dur=None):
    """A distorted 808 boom that slides down in pitch: the phonk hit."""
    dur = dur or rng.uniform(1.2, 2.0)
    t = _t(dur)
    f0, f1 = rng.uniform(90, 130), rng.uniform(38, 50)
    f = f1 + (f0 - f1) * np.exp(-t * rng.uniform(5, 9))
    x = np.tanh(rng.uniform(2, 4) * np.sin(2 * np.pi * np.cumsum(f) / SR)) * np.exp(-t * rng.uniform(1.0, 1.8))
    x[: int(0.003 * SR)] *= np.linspace(0, 1, int(0.003 * SR))
    return _stereo(_norm(x), 0)


def glitch(rng, dur=None):
    """Digital stutters: chopped, bit-crushed noise and tones."""
    dur = dur or rng.uniform(0.35, 0.7)
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    pos = 0
    while pos < n:
        seg = int(rng.uniform(0.015, 0.06) * SR)
        if rng.random() < 0.7:
            tt = np.arange(seg) / SR
            src = np.sin(2 * np.pi * rng.uniform(200, 3000) * tt) if rng.random() < 0.5 else rng.standard_normal(seg)
            steps = rng.choice([4, 8, 16])
            out[pos:pos + seg] = (np.round(src * steps) / steps)[: n - pos] * rng.uniform(0.4, 1)
        pos += seg
    return _stereo(_norm(out, 0.5), rng.uniform(-0.6, 0.6))


def reverse_swell(rng, dur=None):
    """A reversed cymbal swell that sucks into the next moment. Place it with a negative offset."""
    dur = dur or rng.uniform(1.0, 1.8)
    n = int(dur * SR)
    t = _t(dur)
    cymbal = _filt(_noise(n, rng), "highpass", rng.uniform(3000, 6000)) * np.exp(-t * rng.uniform(2.5, 4))
    wet = reverb(rng, _stereo(cymbal, rng.uniform(-0.3, 0.3)), rt=1.2, mix=0.5)
    return _norm(np.ascontiguousarray(wet[::-1]), 0.6)  # played backwards, it swells up into the hit


SFX = {"whoosh": whoosh, "impact": impact, "rumble": rumble, "riser": riser, "tick": tick,
       "shimmer": shimmer, "power_down": power_down, "pop": pop, "chalk": chalk_scratch,
       "808": bass_808, "glitch": glitch, "reverse": reverse_swell}

SFX_GAIN_DB = {"whoosh": -14, "impact": -8, "rumble": -12, "riser": -14, "tick": -20,
               "shimmer": -20, "power_down": -12, "pop": -18, "chalk": -24,
               "808": -10, "glitch": -20, "reverse": -16}


def make_sfx(kind, rng, dur=None):
    if kind not in SFX:
        raise ValueError(f"Unknown sound effect '{kind}'. Available: {', '.join(SFX)}")
    return SFX[kind](rng, dur)


# ---------------------------------------------------------------- music

MODES = {
    "wonder": [0, 2, 4, 6, 7, 9, 11],   # lydian: bright, floating
    "calm": [0, 2, 4, 7, 9],            # major pentatonic
    "tense": [0, 1, 3, 5, 7, 8, 10],    # phrygian: dark
    "mystery": [0, 2, 3, 5, 7, 8, 10],  # aeolian
    "epic": [0, 2, 3, 5, 7, 9, 10],     # dorian
}

PROGRESSIONS = [[0, 5, 3, 4], [0, 3, 5, 4], [0, 4, 5, 3], [0, 2, 5, 4], [0, 5, 2, 3], [0, 3, 1, 4]]


def _midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _chord(scale, root_midi, degree, size=4):
    notes = []
    for k in range(size):
        idx = degree + k * 2
        octave, step = divmod(idx, len(scale))
        notes.append(root_midi + scale[step] + 12 * octave)
    return notes


def _pad_note(freq, n, rng, brightness):
    """An airy pad voice: resonant filtered noise plus a quiet detuned sine pair."""
    noise = _noise(n, rng, "pink")
    bw = 1.012
    x = _filt(noise, "bandpass", [freq / bw, freq * bw], order=2) * 9
    x += _filt(noise, "bandpass", [2 * freq / bw, 2 * freq * bw], order=2) * 4 * brightness
    t = np.arange(n, dtype=np.float32) / SR
    det = rng.uniform(0.15, 0.5)
    x += 0.05 * (np.sin(2 * np.pi * freq * t) + np.sin(2 * np.pi * (freq + det) * t))
    return x.astype(np.float32)


def score(rng, total_sec, moods):
    """An ambient soundtrack for the whole video.
    `moods` is a list of (start_sec, mood, intensity 0..1) describing each section."""
    n_total = int(total_sec * SR)
    out = np.zeros((n_total, 2), np.float32)
    root = int(rng.integers(43, 51))  # G2..D3
    prog = PROGRESSIONS[int(rng.integers(0, len(PROGRESSIONS)))]
    chord_len = float(rng.uniform(7, 10))
    bpm = float(rng.uniform(56, 72))

    def mood_at(sec):
        cur = moods[0]
        for m in moods:
            if m[0] <= sec:
                cur = m
        return cur

    n_chords = int(math.ceil(total_sec / chord_len)) + 1
    release = 3.0
    for ci in range(n_chords):
        start = ci * chord_len
        if start >= total_sec:
            break
        _, mood, inten = mood_at(start)
        scale = MODES.get(mood, MODES["wonder"])
        degree = prog[ci % len(prog)] % len(scale)
        notes = _chord(scale, root, degree, size=4)
        seg_n = int((chord_len + release) * SR)
        seg = np.zeros((seg_n, 2), np.float32)
        for j, m in enumerate(notes):
            voice = _pad_note(_midi_hz(m + 12 * (j % 2)), seg_n, rng, 0.3 + inten * 0.7)
            seg += _stereo(voice, rng.uniform(-0.6, 0.6))
        # sub bass on the chord root
        t = np.arange(seg_n, dtype=np.float32) / SR
        bass = np.sin(2 * np.pi * _midi_hz(notes[0] - 12) * t) * (0.25 + inten * 0.35)
        seg += _stereo(bass.astype(np.float32), 0)
        seg *= _env(seg_n, 2.2 / (chord_len + release), release / (chord_len + release), 1.0)[:, None]
        # sparse plucks that get busier as intensity rises
        beat = 60 / bpm
        for b in range(int(chord_len / beat)):
            if rng.random() < 0.15 + inten * 0.45:
                m = notes[int(rng.integers(0, len(notes)))] + 24
                pl_n = int(1.6 * SR)
                tt = np.arange(pl_n, dtype=np.float32) / SR
                f0 = _midi_hz(m)
                pl = (np.sin(2 * np.pi * f0 * tt) + 0.3 * np.sin(4 * np.pi * f0 * tt)) * np.exp(-tt * 3.5)
                off = int(b * beat * SR + rng.uniform(-0.02, 0.02) * SR)
                if 0 <= off < seg_n - pl_n:
                    seg[off:off + pl_n] += _stereo(pl.astype(np.float32) * 0.18, rng.uniform(-0.7, 0.7))
        # a low pulse under tense sections
        if mood in ("tense", "epic") and inten > 0.5:
            for b in range(int(chord_len / beat)):
                off = int(b * beat * SR)
                pl_n = int(0.5 * SR)
                if off + pl_n < seg_n:
                    tt = np.arange(pl_n, dtype=np.float32) / SR
                    thump = np.sin(2 * np.pi * (45 + 40 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 9)
                    seg[off:off + pl_n] += _stereo(thump.astype(np.float32) * 0.35 * inten, 0)
        a = int(start * SR)
        b_end = min(a + seg_n, n_total)
        out[a:b_end] += seg[: b_end - a]
    out = reverb(rng, out, rt=float(rng.uniform(2.5, 4.0)), mix=0.45)
    fade_n = int(min(4, total_sec / 4) * SR)
    out[:fade_n] *= np.linspace(0, 1, fade_n)[:, None]
    out[-fade_n:] *= np.linspace(1, 0, fade_n)[:, None]
    return _norm(out, 0.9)


def reverb(rng, x, rt=2.0, mix=0.3):
    """A synthetic hall: convolve with exponentially decaying stereo noise."""
    ir_n = int(rt * SR)
    t = np.arange(ir_n, dtype=np.float32) / SR
    decay = np.exp(-6.9 * t / rt)
    out = np.empty_like(x)
    for ch in range(x.shape[1]):
        ir = _filt(rng.standard_normal(ir_n).astype(np.float32), "lowpass", 6000) * decay
        ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
        wet = signal.oaconvolve(x[:, ch], ir, mode="full")[: len(x)]
        out[:, ch] = x[:, ch] * (1 - mix) + wet.astype(np.float32) * mix
    return out


# ---------------------------------------------------------------- mix

def db(v):
    return 10 ** (v / 20)


def rms_db(x):
    return 20 * math.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12)


def mix(total_sec, voice_clips, sfx_events, music, rng, music_db=-27, duck_depth=0.55):
    """voice_clips: [(start_sec, mono float32 at SR)]; sfx_events: [(start_sec, stereo, gain_db)].
    music_db is the music's level between lines; duck_depth how far it dips under the voice.
    Returns a stereo master at SR, loudness-normalised for YouTube."""
    n = int(total_sec * SR)
    voice = np.zeros(n, np.float32)
    for start, clip in voice_clips:
        a = int(start * SR)
        b = min(a + len(clip), n)
        voice[a:b] += clip[: b - a]
    voice = _filt(voice, "highpass", 70, order=2)
    if np.any(voice):
        voice *= db(-18 - rms_db(voice[voice != 0]))  # voice sits at about -18 dBFS RMS

    # duck the music under the voice
    env = _filt(np.abs(voice), "lowpass", 4, order=2)
    env = np.clip(env / (np.percentile(env, 95) + 1e-9), 0, 1)
    duck = 1 - duck_depth * env
    music = music[:n] if len(music) >= n else np.pad(music, ((0, n - len(music)), (0, 0)))
    music = music * db(music_db - rms_db(music)) * duck[:, None]

    fx = np.zeros((n, 2), np.float32)
    for start, clip, gain in sfx_events:
        a = int(max(start, 0) * SR)
        b = min(a + len(clip), n)
        if a < n:
            fx[a:b] += clip[: b - a] * db(gain)

    master = _stereo(voice, 0) * 1.41 + music + fx
    master = np.tanh(master * 1.2) / 1.2  # gentle limiter
    master *= db(-14.5 - rms_db(master))  # close to YouTube's -14 LUFS target
    peak = np.max(np.abs(master))
    if peak > db(-1):
        master *= db(-1) / peak
    return master.astype(np.float32)
