"""The 7pm message: one ntfy notification saying today's long videos are uploaded and ready to publish.

GitHub runs this at 18:00 and 19:00 UTC; it only sends at 7pm UK time (so it's right in summer and winter).

    uv run --no-project --with cryptography python -m esim.evening          # what GitHub runs
    uv run --no-project --with cryptography python -m esim.evening --now    # send immediately (testing)
    ... python -m esim.evening --now --date 2026-10-29                    # for another day's uploads
"""

import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from esim import notify, vault

UK = ZoneInfo("Europe/London")


def main():
    now = datetime.now(UK)
    if "--now" not in sys.argv and now.hour != 19:
        print(f"It's {now:%H:%M} in the UK, not 7pm; nothing to send.")
        return
    raw = vault.read_member("plan/queue.json")
    queue = json.loads(raw) if raw else []
    today = sys.argv[sys.argv.index("--date") + 1] if "--date" in sys.argv else now.date().isoformat()
    done = [i for i in queue if i.get("status") == "uploaded" and i.get("uploaded") == today and i.get("video_id")]
    ready = sum(1 for i in queue if i.get("status") == "scripted")
    if not done:
        notify.send("No long videos today", "Nothing was uploaded today. Check the GitHub Actions run for what went wrong.",
                    priority="high", tags=("warning",))
        return
    lines = [f"• {i.get('title') or i.get('working_title') or i['slug']}\n  https://studio.youtube.com/video/{i['video_id']}/edit"
             for i in done]
    noun = "video is" if len(done) == 1 else "videos are"
    notify.send(f"{len(done)} long {noun} uploaded and ready to publish",
                "\n".join(lines) + f"\n\nThey're private: check each one, then set it to Public.\n{ready} more in reserve.",
                url=f"https://studio.youtube.com/video/{done[0]['video_id']}/edit", tags=("movie_camera",))
    print(f"Sent the 7pm message for {len(done)} video(s).")


if __name__ == "__main__":
    main()
