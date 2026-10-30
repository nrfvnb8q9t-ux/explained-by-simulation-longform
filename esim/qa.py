"""Quality check on rendered scenes: finds stretches where the screen is nearly empty, and scenes that stand
still too long. Run it after a preview render, and fix every scene it lists before the video counts as done.

    uv run python -m esim.render videos/<slug> --preview      # renders every scene into build/<slug>/segments
    uv run python -m esim.qa videos/<slug>                    # lists weak scenes; exit code 1 if there are any

"Empty" means under 1.2% of the frame (caption strip excluded) differs clearly from the background: a
starfield on its own, a lone title, a blank chart waiting for its number. Viewers click away from those.
"""

import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SW, SH = 192, 108          # analysis size
RATE = 4                   # samples per second
CAPTION_CROP = 0.85        # ignore the bottom 15%, where captions go
EMPTY = 0.012              # content share below this = empty frame
MAX_EMPTY_S = 1.0          # allowed empty stretch (transitions and blink-cuts are fine)
STILL = 2.0                # mean pixel change over 2 s below this = nothing moving
MAX_STILL_S = 6.0          # something must visibly change at least this often


def content_share(frame):
    return float((np.abs(frame - np.median(frame)) > 28).mean())


def analyse(path):
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(path),
           "-vf", f"fps={RATE},scale={SW}:{SH},format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, SH, SW).astype(np.float32)[:, : int(SH * CAPTION_CROP)]
    if len(frames) == 0:
        return None
    shares = np.array([content_share(f) for f in frames])
    lag = 2 * RATE  # compare each frame with the one 2 seconds earlier
    change = np.array([99.0] * min(lag, len(frames)) +
                      [float(np.abs(frames[i] - frames[i - lag]).mean()) for i in range(lag, len(frames))])
    dur = len(frames) / RATE
    skip_head, skip_tail = int(0.4 * RATE), int(0.3 * RATE)
    usable = slice(skip_head, max(len(frames) - skip_tail, skip_head))

    def longest(mask):
        best = run = 0
        start = best_start = 0
        for i, m in enumerate(mask):
            if m:
                if run == 0:
                    start = i
                run += 1
                if run > best:
                    best, best_start = run, start
            else:
                run = 0
        return best / RATE, best_start / RATE

    empty_s, empty_at = longest(shares[usable] < EMPTY)
    still_s, still_at = longest(change[usable] < STILL)
    return {"dur": dur, "empty_s": empty_s, "empty_at": empty_at + skip_head / RATE,
            "still_s": still_s, "still_at": still_at + skip_head / RATE, "mean_share": float(shares.mean())}


def main():
    video_dir = Path(sys.argv[1]).resolve()
    script = json.loads((video_dir / "script.json").read_text())
    seg_dir = ROOT / "build" / script["slug"] / "segments"
    scenes = script["long"]["scenes"]
    problems, checked = [], 0
    for i, s in enumerate(scenes):
        seg = seg_dir / f"{i:03d}.mp4"
        if not seg.exists():
            continue
        r = analyse(seg)
        if not r:
            continue
        checked += 1
        what = "custom @scene" if s.get("custom") else f"template {(s.get('shot') or {}).get('template')}"
        if r["empty_s"] > MAX_EMPTY_S:
            problems.append(f"scene {s['id']} ({what}): nearly EMPTY screen for {r['empty_s']:.1f}s starting at "
                            f"{r['empty_at']:.1f}s. Put the main subject on screen from the first frame; triggers "
                            f"should add to it, not reveal it from nothing.")
        if r["still_s"] > MAX_STILL_S:
            problems.append(f"scene {s['id']} ({what}): nothing moves for {r['still_s']:.1f}s starting at "
                            f"{r['still_at']:.1f}s. Add a camera move, a new layer or a beat at least every 3-6s.")
    if not checked:
        sys.exit(f"No rendered segments in {seg_dir}. Run: uv run python -m esim.render {sys.argv[1]} --preview")
    print(f"Checked {checked} scene(s).")
    for p in problems:
        print("  - " + p)
    if problems:
        print(f"{len(problems)} problem(s). Fix them, re-render those scenes with --preview --scenes <ids>, and run this again.")
        sys.exit(1)
    print("All scenes pass: no empty or frozen stretches.")


if __name__ == "__main__":
    main()
