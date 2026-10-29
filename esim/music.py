"""Music from the YouTube Audio Library: import, beat analysis, picking tracks and placing them.

You download tracks from YouTube Studio > Audio library (free to use in YouTube videos). Then:

    uv run python -m esim.music add ~/Downloads/audio-library     # copies + analyses them
    uv run python -m esim.music list                              # what's in the library

Each track is analysed once for its tempo, beats, bar lines (downbeats), drops and energy. When a video
renders, the soundtrack is planned from the scenes' moods: hype sections get high-energy tracks with
the drop landing on the section's first scene, calmer sections get lower-energy ones. The least-used
tracks are picked first so the same track doesn't come back until the others have had a turn.

Audio Library tracks may not be redistributed, so the music folder only ever goes into the repo encrypted.
"""

import json
import re
import os
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = Path(os.environ.get("ESIM_MUSIC_DIR", ROOT / "music"))
LIBRARY = MUSIC_DIR / "library.json"
USAGE = ROOT / "data" / "music-usage.json"
AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg"}
ANALYSIS_SR = 22050


# ---------------------------------------------------------------- analysis

def analyze(path):
    import librosa
    y, sr = librosa.load(str(path), sr=ANALYSIS_SR, mono=True)
    duration = len(y) / sr
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    on_times = librosa.times_like(onset, sr=sr)
    # tempo trackers often lock onto 2/3 or 1/2 of the real tempo; try several starting guesses and
    # keep the beat grid whose beats land hardest on actual hits
    best = None
    for start_bpm in (90, 120, 145, 170):
        tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, start_bpm=start_bpm)
        if len(frames) < 16:
            continue
        fit = float(onset[frames].mean())
        bpm_try = float(np.atleast_1d(tempo)[0])
        fit *= 1.0 if 100 <= bpm_try <= 175 else 0.93  # slight preference for typical hype tempos
        if best is None or fit > best[0]:
            best = (fit, bpm_try, librosa.frames_to_time(frames, sr=sr))
    if best is None:
        raise ValueError("couldn't find a steady beat")
    _, bpm, beats = best
    beats = np.asarray(beats, float)
    # fold double/half-time readings into a usable 75-170 bpm grid
    while bpm > 170 and len(beats) > 32:
        beats, bpm = beats[::2], bpm / 2
    while bpm < 75:
        beats = np.sort(np.concatenate([beats, (beats[:-1] + beats[1:]) / 2]))
        bpm *= 2

    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    times = librosa.times_like(rms, sr=sr, hop_length=hop)
    rms_s = np.convolve(rms, np.ones(9) / 9, mode="same")

    # bar lines: the beat phase (of 4) where the low end hits hardest
    low = librosa.onset.onset_strength(y=y, sr=sr, fmax=300, n_mels=24)
    on_t = librosa.times_like(low, sr=sr)
    at_beats = np.interp(beats, on_t, low)
    phase = int(np.argmax([at_beats[k::4].sum() for k in range(4)]))
    downbeats = beats[phase::4]
    # quiet intros often have no detected beats: extend the bar grid back to the start of the track
    bar_len = float(np.median(np.diff(downbeats))) if len(downbeats) > 2 else 240 / bpm
    early = np.arange(downbeats[0] - bar_len, -0.01, -bar_len)[::-1]
    if len(early):
        downbeats = np.concatenate([early, downbeats])
        beat_len = bar_len / 4
        beats = np.concatenate([np.arange(downbeats[0], beats[0] - beat_len * 0.5, beat_len), beats])

    # energy per bar, 0..1 within the track
    bar_e = np.array([rms_s[(times >= a) & (times < b)].mean() if np.any((times >= a) & (times < b)) else 0
                      for a, b in zip(downbeats[:-1], downbeats[1:])])
    peak = bar_e.max() + 1e-9
    bar_norm = bar_e / peak

    # drops: a bar that's loud and clearly louder than the two before it
    drops = []
    for i in range(2, len(bar_norm)):
        if bar_norm[i] > 0.72 and bar_norm[i] - bar_norm[i - 2:i].mean() > 0.22:
            if not drops or downbeats[i] - drops[-1] > 20:
                drops.append(float(downbeats[i]))

    loud_db = float(20 * np.log10(np.percentile(rms_s, 75) + 1e-9))
    return {
        "duration": round(duration, 2),
        "bpm": round(bpm, 1),
        "beats": [round(float(b), 3) for b in beats],
        "downbeats": [round(float(b), 3) for b in downbeats],
        "drops": [round(d, 3) for d in drops],
        "bar_energy": [round(float(e), 3) for e in bar_norm],
        "loudness_db": round(loud_db, 2),
    }


def load_library():
    return json.loads(LIBRARY.read_text()) if LIBRARY.exists() else {"tracks": []}


HYPE_MOODS = {"ANGRY", "DARK", "DRAMATIC", "FUNKY"}
CALM_MOODS = {"CALM", "INSPIRATIONAL", "BRIGHT", "ROMANTIC", "SAD", "HAPPY"}


def save_library(lib):
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    # Energy score 0..1. When the source labelled a mood (the YouTube Audio Library does), that decides the
    # tier: hype moods get 0.55-1.0, calm moods 0-0.35. Within a tier, tempo, loudness and drops rank them.
    tracks = lib["tracks"]

    def raw(t):
        return t["bpm"] / 180 + (t["loudness_db"] + 30) / 30 + 0.4 * len(t["drops"]) / max(t["duration"] / 60, 1)

    tiers = {"hype": (0.55, 1.0), "calm": (0.0, 0.35), "unknown": (0.0, 1.0)}
    for tier, (lo, hi) in tiers.items():
        group = [t for t in tracks if _tier(t) == tier]
        if not group:
            continue
        ranks = np.array([raw(t) for t in group]).argsort().argsort() / max(len(group) - 1, 1)
        for t, r in zip(group, ranks):
            t["energy"] = round(lo + (hi - lo) * float(r), 3)
    LIBRARY.write_text(json.dumps(lib, indent=1))


def _tier(t):
    mood = (t.get("mood") or "").upper()
    return "hype" if mood in HYPE_MOODS else "calm" if mood in CALM_MOODS else "unknown"


def add(folder, credit=None):
    """Import every track in `folder`. `credit` is a description line for sources that require one,
    e.g. NCS; {title} is replaced with the track name."""
    folder = Path(folder).expanduser()
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in AUDIO_EXT)
    if not files:
        sys.exit(f"No audio files (mp3/wav/flac/ogg) in {folder}")
    lib = load_library()
    known = {t["file"] for t in lib["tracks"]}
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    # optional tracks.json next to the files: [{"title", "artist", "mood"}], e.g. from the Audio Library
    sidecar = folder / "tracks.json"
    moods, credits = {}, {}
    if sidecar.exists():
        for t in json.loads(sidecar.read_text()):
            key = re.sub(r"[^a-z0-9]", "", f"{t['title']} - {t.get('artist', '')}".lower())
            moods[key], credits[key] = t.get("mood"), t.get("credit")
    added = 0
    for p in files:
        name = p.name
        if name in known:
            continue
        try:
            info = analyze(p)
        except Exception as e:
            print(f"  skipped {name}: {e}")
            continue
        shutil.copy2(p, MUSIC_DIR / name) if (MUSIC_DIR / name) != p else None
        key = re.sub(r"[^a-z0-9]", "", p.stem.lower())
        mood = moods.get(key)
        line = credits.get(key) or (credit.format(title=p.stem) if credit else None)
        lib["tracks"].append({"file": name, "title": p.stem, **info, "mood": mood, "credit": line})
        added += 1
        print(f"  + {p.stem}: {info['bpm']:.0f} bpm, {info['duration'] / 60:.1f} min, {len(info['drops'])} drop(s)")
    save_library(lib)
    print(f"Added {added} track(s). Library now has {len(lib['tracks'])}.")


def list_tracks():
    lib = load_library()
    usage = json.loads(USAGE.read_text()) if USAGE.exists() else {}
    print(f"{len(lib['tracks'])} tracks in {MUSIC_DIR}")
    for t in sorted(lib["tracks"], key=lambda t: -t.get("energy", 0)):
        print(f"  energy {t.get('energy', 0):.2f} | {t['bpm']:5.0f} bpm | {len(t['drops'])} drops | "
              f"used {usage.get(t['file'], 0)}x | {t['title']}")


# ---------------------------------------------------------------- planning a soundtrack

def _level(intensity):
    return "hype" if intensity >= 0.6 else "mid" if intensity >= 0.35 else "calm"


def plan_soundtrack(timeline, total, rng, max_section=150.0):
    """Choose and place tracks for a whole video.

    timeline: [{"start", "dur", "intensity", "drop_at" (optional seconds into scene)}].
    Returns (placements, beats, drops) where beats/drops are absolute video times:
      placements: [{"file", "offset", "start", "end", "fade_in", "fade_out"}]
      beats: [(time, strength)] with strength 1.0 on bar lines, 0.5 otherwise
    """
    lib = load_library()["tracks"]
    if not os.environ.get("ESIM_ALLOW_TEST_MUSIC"):
        # never let the test beats from tests/make_test_beats.py anywhere near a real video
        lib = [t for t in lib if "not for upload" not in t["title"].lower()]
    if not lib:
        raise RuntimeError(f"The music library is empty. Import tracks with: uv run python -m esim.music add <folder>")
    usage = json.loads(USAGE.read_text()) if USAGE.exists() else {}

    # group scenes into sections of similar energy, a few minutes at most
    sections = []
    for it in timeline:
        lvl = _level(it["intensity"])
        cur = sections[-1] if sections else None
        if cur and cur["level"] == lvl and (it["start"] + it["dur"] - cur["start"]) <= max_section:
            cur["end"] = it["start"] + it["dur"]
            cur["intensity"] = max(cur["intensity"], it["intensity"])
        else:
            sections.append({"level": lvl, "start": it["start"], "end": it["start"] + it["dur"],
                             "intensity": it["intensity"], "drop_at": it["start"] + it.get("drop_at", 0.0)})
    # merge tiny sections into their neighbour so the music doesn't flip every few seconds
    merged = []
    for s in sections:
        if merged and s["end"] - s["start"] < 25:
            merged[-1]["end"] = s["end"]
        else:
            merged.append(s)
    sections = merged

    placements, beats, drops = [], [], []
    used_this_video = []
    for si, sec in enumerate(sections):
        target = {"hype": 0.85, "mid": 0.5, "calm": 0.2}[sec["level"]]
        cursor = sec["start"]
        while cursor < sec["end"] - 0.5:
            def score(t):
                s = abs(t.get("energy", 0.5) - target) * 2 + usage.get(t["file"], 0) * 0.6
                s += 3 if t["file"] in used_this_video else 0
                s += 0.4 if sec["level"] == "hype" and not t["drops"] else 0
                # NCS is the best-known no-copyright music, so it leads the hype and mid sections
                s -= 0.35 if sec["level"] != "calm" and "NoCopyrightSounds" in (t.get("credit") or "") else 0
                return s + rng.random() * 0.3
            track = min(lib, key=score)
            used_this_video.append(track["file"])
            usage[track["file"]] = usage.get(track["file"], 0) + 1

            if sec["level"] == "hype" and track["drops"] and cursor == sec["start"]:
                # land the track's drop on the section's big moment, with up to 2 bars of build-up
                # before it (overlapping the end of the previous section if needed)
                d = track["drops"][int(rng.integers(0, len(track["drops"])))]
                hit = max(sec["drop_at"], cursor)
                bar = 240 / max(track["bpm"], 60)
                pre = min(d, hit - cursor + 2 * bar, hit)
                start, offset = hit - pre, d - pre
                fade_in = float(np.clip(cursor - start, 0.3, 2.0))
            else:
                skip = [b for b in track["downbeats"] if b > 1.0]  # skip silent intros
                start, offset, fade_in = cursor, (skip[0] if skip else 0.0), 1.0
            length = min(track["duration"] - offset - 0.5, sec["end"] - start)
            if length < 4:
                offset, length = 0.0, min(track["duration"] - 0.5, sec["end"] - start)
            end = start + length
            placements.append({"file": track["file"], "offset": round(offset, 3), "start": round(start, 3),
                               "end": round(end, 3), "fade_in": round(fade_in, 2),
                               "fade_out": 1.5, "title": track["title"]})
            for b in track["beats"]:
                t = start + (b - offset)
                if start <= t < end:
                    beats.append((round(t, 3), 0.5))
            for b in track["downbeats"]:
                t = start + (b - offset)
                if start <= t < end:
                    beats.append((round(t, 3), 1.0))
            for d in track["drops"]:
                t = start + (d - offset)
                if start <= t < end:
                    drops.append(round(t, 3))
            cursor = end
    # one strength per beat time (bar lines win)
    best = {}
    for t, s in beats:
        best[t] = max(best.get(t, 0), s)
    beats = sorted(best.items())
    return placements, beats, sorted(drops), usage


def record_usage(usage):
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    USAGE.write_text(json.dumps(usage, indent=1))


def build_bed(placements, total, sr):
    """Mix the placed tracks into one stereo music bed at `sr`, each track loudness-matched."""
    import librosa
    n = int(total * sr)
    bed = np.zeros((n, 2), np.float32)
    for pl in placements:
        y, _ = librosa.load(str(MUSIC_DIR / pl["file"]), sr=sr, mono=False, offset=pl["offset"],
                            duration=pl["end"] - pl["start"] + 0.1)
        y = np.atleast_2d(y)
        if y.shape[0] == 1:
            y = np.vstack([y, y])
        y = y.T.astype(np.float32)
        rms = np.sqrt(np.mean(y ** 2)) + 1e-9
        y *= 0.12 / rms  # every track at the same level
        k = len(y)
        fi, fo = int(pl["fade_in"] * sr), int(pl["fade_out"] * sr)
        if fi:
            y[:fi] *= np.linspace(0, 1, fi)[:, None]
        if fo and fo < k:
            y[-fo:] *= np.linspace(1, 0, fo)[:, None]
        a = int(pl["start"] * sr)
        b = min(a + k, n)
        bed[a:b] += y[: b - a]
    return bed


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "add":
        add(sys.argv[2], credit=sys.argv[4] if len(sys.argv) >= 5 and sys.argv[3] == "--credit" else None)
    elif len(sys.argv) >= 2 and sys.argv[1] == "list":
        list_tracks()
    else:
        sys.exit(__doc__)
