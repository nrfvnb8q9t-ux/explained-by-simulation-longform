"""One day's run: take the next finished scripts, render them, check they're unique, upload them as
private and send a notification to your phone for each.

    uv run python -m esim.daily             # what GitHub runs every morning (2 videos)
    uv run python -m esim.daily --dry-run   # render and check, but don't upload
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from esim import notify

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "plan" / "queue.json"
LOG = ROOT / "content-log.md"
VIDEOS_PER_DAY = 2
RESERVE_WARN = 6
UK = ZoneInfo("Europe/London")


def load_queue():
    return json.loads(QUEUE.read_text()) if QUEUE.exists() else []


def save_queue(queue):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(queue, indent=2))


def is_ready(item):
    d = ROOT / "videos" / item["slug"]
    return item.get("status") == "scripted" and (d / "script.json").exists() and (d / "scenes.py").exists()


def render(slug):
    """Run the renderer in its own process. Its output goes to a log file inside the vault, not the
    public GitHub log, because error messages can quote the script."""
    log_dir = ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{date.today()}-{slug}.log"
    with open(log_path, "w") as log:
        code = subprocess.run([sys.executable, "-m", "esim.render", f"videos/{slug}"], cwd=ROOT,
                              stdout=log, stderr=subprocess.STDOUT).returncode
    return code == 0, log_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--count", type=int, default=VIDEOS_PER_DAY)
    args = ap.parse_args()

    from esim import music
    if not music.load_library()["tracks"]:
        notify.send("No video today", "The music library is empty. On your Mac, import YouTube Audio Library "
                    "tracks (see README, step 2) and push.", priority="high", tags=("warning",))
        sys.exit(1)

    queue = load_queue()
    ready = sorted((i for i in queue if is_ready(i)), key=lambda i: i.get("date", ""))
    if not ready:
        notify.send("No video today", "There are no finished scripts in reserve. Check the Claude step "
                    "in today's GitHub run, or write some scripts from your Mac.", priority="high", tags=("warning",))
        sys.exit(1)

    from esim import youtube
    made, attempts = 0, 0
    for item in ready:
        if made >= args.count or attempts >= args.count + 2:  # a couple of spare tries if renders fail
            break
        attempts += 1
        print(f"Rendering video {made + 1} of {args.count}...", flush=True)
        ok, log_path = render(item["slug"])
        if not ok:
            item["status"] = "render_failed"
            item["error_log"] = str(log_path.relative_to(ROOT))
            save_queue(queue)
            print(f"Render failed; details saved in the vault ({log_path.name}).")
            continue
        meta = json.loads((ROOT / "build" / item["slug"] / "meta.json").read_text())
        if args.dry_run:
            print(f"Dry run: rendered a {meta['duration'] / 60:.1f} min video, not uploading.")
            made += 1
            continue
        try:
            video_id = youtube.upload(meta)
        except Exception as e:
            notify.send("Upload failed", f"A video rendered but didn't upload: {type(e).__name__}. "
                        "If this says invalid_grant, the YouTube sign-in needs redoing (see README).",
                        priority="high", tags=("warning",))
            raise
        item.update(status="uploaded", video_id=video_id, uploaded=str(datetime.now(UK).date()), title=meta["title"])
        save_queue(queue)
        with open(LOG, "a") as f:
            f.write(f"{date.today()} | {item['slug']} | {item.get('format', '')} | "
                    f"hook {item.get('hook_formula', '')} | {meta['title']} | {video_id}\n")
        made += 1
        # the "ready to publish" message is sent once, at 7pm, by esim.evening (see .github/workflows/evening.yml)
        shutil.rmtree(ROOT / "build" / item["slug"], ignore_errors=True)  # free disk space for the next render

    if made < args.count:
        notify.send(f"Only {made} of {args.count} videos today",
                    "Some renders failed or the reserve ran out. Error logs are in the vault under data/logs; "
                    "Claude fixes failed scripts on the next run.", priority="high", tags=("warning",))
    if made == 0:
        sys.exit(1)
    print(f"Done: {made} video(s).")


if __name__ == "__main__":
    main()
