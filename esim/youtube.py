"""Uploads to YouTube as private, with thumbnail and captions, using the official Data API.

One-time setup on your Mac (opens Google's sign-in page in your browser; you click Allow):

    uv run python -m esim.youtube auth path/to/client_secret.json

It prints three values to save as GitHub secrets: YT_CLIENT_ID, YT_CLIENT_SECRET and YT_REFRESH_TOKEN.
"""

import json
import os
import sys
import time

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
SCIENCE_AND_TECH = "28"


def _client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    missing = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing YouTube secrets: {', '.join(missing)}")
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        token_uri="https://oauth2.googleapis.com/token", scopes=SCOPES)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(meta):
    """Upload a rendered video (meta.json from esim.render) as PRIVATE. Returns the video id."""
    from googleapiclient.http import MediaFileUpload
    yt = _client()
    body = {
        "snippet": {"title": meta["title"][:100], "description": meta["description"][:5000],
                    "tags": meta.get("tags", [])[:30], "categoryId": SCIENCE_AND_TECH,
                    "defaultLanguage": "en", "defaultAudioLanguage": "en"},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": bool(meta.get("ai_disclosure", True))},
    }
    media = MediaFileUpload(meta["video"], mimetype="video/mp4", chunksize=16 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response, retries = None, 0
    while response is None:
        try:
            _, response = req.next_chunk()
        except Exception as e:  # network blips: retry a few times with backoff
            retries += 1
            if retries > 5:
                raise
            print(f"upload retry {retries}: {e}")
            time.sleep(2 ** retries)
    video_id = response["id"]
    if meta.get("ai_disclosure", True):  # set the altered/synthetic content label explicitly as well
        try:
            yt.videos().update(part="status", body={"id": video_id, "status": {
                "privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}).execute()
        except Exception as e:
            print(f"AI-content label not set ({e}); tick 'Altered content' in YouTube Studio.")

    try:
        yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(meta["thumbnail"])).execute()
    except Exception as e:
        print(f"Thumbnail not set ({e}). Custom thumbnails need a phone-verified channel.")
    try:
        yt.captions().insert(part="snippet", body={"snippet": {"videoId": video_id, "language": "en",
                                                               "name": "English", "isDraft": False}},
                             media_body=MediaFileUpload(meta["captions"], mimetype="application/octet-stream")).execute()
    except Exception as e:
        print(f"Captions not uploaded ({e}); YouTube will auto-caption instead.")
    return video_id


SECRETS_FILE = ".yt-secrets.json"  # local only (gitignored); values go into GitHub secrets


def auth(client_secret_path):
    """Sign in once in the browser and save the three YouTube secrets to .yt-secrets.json (not printed,
    so they never end up in a terminal log)."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline",
                                  success_message="Done! You can close this tab and go back to Claude.")
    info = json.load(open(client_secret_path))
    info = info.get("installed") or info.get("web")
    secrets = {"YT_CLIENT_ID": info["client_id"], "YT_CLIENT_SECRET": info["client_secret"],
               "YT_REFRESH_TOKEN": creds.refresh_token}
    with open(SECRETS_FILE, "w") as f:
        json.dump(secrets, f)
    os.chmod(SECRETS_FILE, 0o600)
    print(f"Signed in. Saved YT_CLIENT_ID, YT_CLIENT_SECRET and YT_REFRESH_TOKEN to {SECRETS_FILE} "
          "(kept out of git). Add them as GitHub repository secrets.")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "auth":
        auth(sys.argv[2])
    else:
        sys.exit(__doc__)
