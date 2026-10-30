"""The uniqueness check: blocks an upload if its shots look like any earlier video's.

Samples a frame every 2 seconds, turns each into a 256-bit perceptual hash, and compares them with
the hashes of every past video. Near-empty frames (plain black, faint starfields) are skipped, since
those look alike in any space video, and the burned-in caption strip at the bottom is cropped off first.
A reused clip matches almost bit for bit; two different shots of "a planet in the middle of a dark sky"
don't, which a coarser 64-bit hash couldn't tell apart.
"""

import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np

GW, GH = 136, 128  # 16 rows x 17 columns of 8x8 cells
CAPTION_CROP = 0.86  # keep the top 86% of the frame


def fingerprints(video_path, every=2.0):
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(video_path),
           "-vf", f"fps=1/{every},crop=iw:ih*{CAPTION_CROP}:0:0,scale={GW}:{GH},format=gray",
           "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, GH, GW).astype(np.float32)
    hashes = []
    for fr in frames:
        if fr.std() < 10:  # nothing much on screen
            continue
        small = fr.reshape(16, GH // 16, 17, GW // 17).mean(axis=(1, 3))
        bits = (small[:, 1:] > small[:, :-1]).flatten()
        hashes.append(int("".join("1" if b else "0" for b in bits), 2))
    return hashes


def _hamming(a, b):
    return bin(a ^ b).count("1")


def check(slug, hashes, db_path, max_dist=16, max_share=0.08):
    """Returns (ok, report). Fails if more than `max_share` of this video's shots closely match
    shots from any single earlier video."""
    db_path = Path(db_path)
    db = json.loads(db_path.read_text()) if db_path.exists() else {}
    worst = (0.0, None)
    compared = 0
    for other, old in db.items():
        if other == slug or not old or not hashes:
            continue
        compared += 1
        old_ints = [int(h, 16) for h in old if len(h) == 64]  # skip any old-format (64-bit) hashes
        matches = sum(1 for h in hashes if min(_hamming(h, o) for o in old_ints) <= max_dist)
        share = matches / len(hashes)
        if share > worst[0]:
            worst = (share, other)
    ok = worst[0] <= max_share
    if worst[1]:
        report = f"closest earlier video: {worst[1]} ({worst[0]:.0%} of shots look alike, limit {max_share:.0%})"
    elif compared:
        report = f"compared with {compared} earlier video(s), no matching shots"
    else:
        report = "no earlier videos to compare with"
    return ok, report


def record(slug, hashes, db_path):
    db_path = Path(db_path)
    db = json.loads(db_path.read_text()) if db_path.exists() else {}
    db[slug] = [f"{h:064x}" for h in hashes]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text(json.dumps(db, indent=0))
