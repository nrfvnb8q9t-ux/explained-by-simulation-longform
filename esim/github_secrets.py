"""Builds the ESIM_SECRETS bundle for GitHub and puts it on the clipboard, without printing it.

    uv run python -m esim.github_secrets    # then paste into GitHub as the ESIM_SECRETS secret

It gathers the vault key (.content-key), the YouTube tokens and research key (.yt-secrets.json) and the
ntfy topic (.ntfy-topic). All of those files stay on this Mac and out of git.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEEDED = ["CONTENT_KEY", "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN", "YOUTUBE_API_KEY", "NTFY_TOPIC"]


def bundle():
    out = {}
    if (ROOT / ".content-key").exists():
        out["CONTENT_KEY"] = (ROOT / ".content-key").read_text().strip()
    if (ROOT / ".yt-secrets.json").exists():
        out.update(json.loads((ROOT / ".yt-secrets.json").read_text()))
    if (ROOT / ".ntfy-topic").exists():
        out["NTFY_TOPIC"] = (ROOT / ".ntfy-topic").read_text().strip()
    return out


if __name__ == "__main__":
    b = bundle()
    missing = [k for k in NEEDED if not b.get(k)]
    if missing:
        sys.exit(f"Missing: {', '.join(missing)}")
    subprocess.run(["pbcopy"], input=json.dumps({k: b[k] for k in NEEDED}).encode(), check=True)
    print(f"ESIM_SECRETS ({len(NEEDED)} values) is on the clipboard. Paste it into GitHub, then copy something "
          "else to clear it.")
