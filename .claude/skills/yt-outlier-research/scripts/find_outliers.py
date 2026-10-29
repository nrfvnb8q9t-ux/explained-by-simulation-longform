#!/usr/bin/env python3
"""Find outlier videos: ones that got far more views than their channel's size predicts.

Uses only the free YouTube Data API v3 and the Python standard library.

    export YOUTUBE_API_KEY=...
    python3 find_outliers.py --channel-md channel.md --out research/outliers.json
    python3 find_outliers.py -q "history documentary" -q "fall of rome" --days 180

Quota: each search term costs 100 units (daily free quota is 10,000; an upload costs 1,600).
The stats lookups cost 1 unit per 50 videos, so a run with 3 terms costs roughly 305 units.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://www.googleapis.com/youtube/v3/"
SEARCH_COST = 100


def api_get(endpoint, params, key):
    params = {**params, "key": key}
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.exit(f"YouTube API error {e.code} on {endpoint}: {body[:500]}")


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def queries_from_channel_md(path):
    """Read the lines under '## Search terms for research', skipping TODOs and HTML comments."""
    text = open(path, encoding="utf-8").read()
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    match = re.search(r"^## Search terms for research\s*$(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    if not match:
        return []
    lines = [ln.strip().lstrip("-* ").strip() for ln in match.group(1).splitlines()]
    return [ln for ln in lines if ln and not ln.upper().startswith("TODO")]


def parse_duration(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def fmt_duration(seconds):
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def chapters(description):
    """Timestamped lines in the description, e.g. '03:15 The siege begins'."""
    return [ln.strip() for ln in description.splitlines()
            if re.match(r"^\s*\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s+\S", ln)][:30]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-q", "--query", action="append", default=[], help="search term (repeatable)")
    ap.add_argument("--channel-md", help="read search terms from this channel.md")
    ap.add_argument("--days", type=int, default=120, help="only videos published in the last N days")
    ap.add_argument("--duration", choices=["any", "short", "medium", "long"], default="any",
                    help="YouTube's buckets: short <4 min, medium 4-20 min, long >20 min")
    ap.add_argument("--max-queries", type=int, default=5, help="cap on search terms, to protect quota")
    ap.add_argument("--min-views", type=int, default=20000)
    ap.add_argument("--top", type=int, default=25, help="how many outliers to keep")
    ap.add_argument("--out", help="write full results as JSON here")
    args = ap.parse_args()

    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        sys.exit("Set YOUTUBE_API_KEY (a free key from Google Cloud Console > APIs & Services > Credentials).")

    queries = list(args.query)
    if args.channel_md:
        queries += queries_from_channel_md(args.channel_md)
    queries = list(dict.fromkeys(queries))[:args.max_queries]
    if not queries:
        sys.exit("No search terms. Pass -q, or fill in '## Search terms for research' in channel.md.")

    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    units = 0
    found = {}  # video id -> search term that found it
    for q in queries:
        params = {"part": "snippet", "q": q, "type": "video", "order": "viewCount",
                  "publishedAfter": since, "maxResults": 50}
        if args.duration != "any":
            params["videoDuration"] = args.duration
        data = api_get("search", params, key)
        units += SEARCH_COST
        for item in data.get("items", []):
            found.setdefault(item["id"]["videoId"], q)

    videos = []
    for batch in chunks(list(found), 50):
        data = api_get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)}, key)
        units += 1
        videos += data.get("items", [])

    channel_ids = list({v["snippet"]["channelId"] for v in videos})
    subs = {}
    for batch in chunks(channel_ids, 50):
        data = api_get("channels", {"part": "statistics", "id": ",".join(batch)}, key)
        units += 1
        for ch in data.get("items", []):
            st = ch.get("statistics", {})
            subs[ch["id"]] = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0))

    now = datetime.now(timezone.utc)
    rows = []
    for v in videos:
        sn, st = v["snippet"], v.get("statistics", {})
        views = int(st.get("viewCount", 0))
        if views < args.min_views:
            continue
        published = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
        age_days = max((now - published).days, 1)
        channel_subs = subs.get(sn["channelId"])
        seconds = parse_duration(v.get("contentDetails", {}).get("duration"))
        thumbs = sn.get("thumbnails", {})
        thumb = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("default") or {}).get("url")
        rows.append({
            "id": v["id"],
            "url": f"https://www.youtube.com/watch?v={v['id']}",
            "title": sn["title"],
            "channel": sn["channelTitle"],
            "channel_subs": channel_subs,
            "views": views,
            "likes": int(st["likeCount"]) if "likeCount" in st else None,
            "comments": int(st["commentCount"]) if "commentCount" in st else None,
            "published": sn["publishedAt"][:10],
            "age_days": age_days,
            "views_per_day": round(views / age_days),
            # Views per subscriber. Floor subs at 1,000 so tiny channels with one lucky video don't dominate.
            "outlier_score": round(views / max(channel_subs, 1000), 1) if channel_subs is not None else None,
            "duration": fmt_duration(seconds),
            "duration_seconds": seconds,
            "is_short": seconds <= 60,
            "thumbnail": thumb,
            "tags": sn.get("tags", [])[:20],
            "description": sn.get("description", "")[:1500],
            "chapters": chapters(sn.get("description", "")),
            "found_by": found[v["id"]],
        })

    rows.sort(key=lambda r: (r["outlier_score"] is not None, r["outlier_score"] or 0, r["views_per_day"]),
              reverse=True)
    rows = rows[:args.top]

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"generated": now.isoformat(timespec="seconds"), "queries": queries,
                       "days": args.days, "quota_units_used": units, "videos": rows}, f, indent=2)

    print(f"Searched {len(queries)} term(s), {len(videos)} videos checked, ~{units} quota units used.\n")
    print("| # | Score | Views | Views/day | Subs | Length | Title | Channel |")
    print("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        score = f"{r['outlier_score']}x" if r["outlier_score"] is not None else "?"
        subs_txt = f"{r['channel_subs']:,}" if r["channel_subs"] is not None else "hidden"
        title = r["title"].replace("|", "/")
        print(f"| {i} | {score} | {r['views']:,} | {r['views_per_day']:,} | {subs_txt} | {r['duration']} "
              f"| [{title}]({r['url']}) | {r['channel']} |")
    if args.out:
        print(f"\nFull details (descriptions, chapters, tags, thumbnails) saved to {args.out}")


if __name__ == "__main__":
    main()
