"""Phone notifications through ntfy.sh (free, no account). Install the ntfy app, subscribe to the
topic name saved in the NTFY_TOPIC secret, and you'll get a push whenever a video is ready or a run fails.
Pick a long random topic name, since anyone who knows it can read the notifications."""

import json
import os
import urllib.request

PRIORITY = {"low": 2, "default": 3, "high": 4}


def send(title, message, url=None, priority="default", tags=("tv",)):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print(f"[notify] {title}: {message}")
        return
    body = {"topic": topic, "title": title, "message": message, "tags": list(tags),
            "priority": PRIORITY.get(priority, 3)}
    if url:
        body["click"] = url
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:
        print(f"[notify] failed to send: {e}")
