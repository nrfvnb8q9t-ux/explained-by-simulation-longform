---
name: yt-outlier-research
description: Find the YouTube videos in the channel's niche that massively outperformed their channel's size, and work out why (title, thumbnail, hook, structure, length). Use before planning or scripting videos, when asked what's working in the niche, or for "research", "outliers" or "viral videos in my niche".
---

# YouTube outlier research

An outlier is a video with far more views than its channel's subscriber count predicts. Big
channels get views because of their audience. A small channel only gets an outlier when the
**idea and packaging** work, and those are the parts worth learning from.

## Steps

1. **Read `channel.md`** at the repo root for the niche and search terms. If the search terms are
   still `TODO`, think of 3-5 phrases from the niche and tell the user which ones you used.

2. **Run the finder.** It needs the `YOUTUBE_API_KEY` environment variable (a free key).
   ```bash
   python3 .claude/skills/yt-outlier-research/scripts/find_outliers.py \
     --channel-md channel.md --days 120 --out research/outliers-$(date +%F).json
   ```
   - Long-form research: add `--duration long` (over 20 min) or `--duration medium` (4-20 min).
   - Shorts research: add `--duration short` and look at rows where `is_short` is true.
   - Each search term costs 100 of the 10,000 daily quota units, and uploads need 1,600 each.
     Keep to 5 terms or fewer per run, and never run it more than once a day.

3. **Pick the 8-10 strongest outliers.** Prefer a score of 5x or more, recent videos, and ones that
   fit the channel's formats. Skip clickbait that doesn't match its title, and skip news that is
   already stale.

4. **Look at each one.** Download the thumbnail and view it:
   `curl -s -o research/thumbs/<id>.jpg <thumbnail url>`, then read the image. From the JSON,
   use the title, description, chapters and tags. Work out:
   - **Title pattern**: the formula behind it, not the exact words (e.g. "The [adjective] Reason
     [surprising thing] Happened", "I Ranked Every [X] by [Y]", "Why Nobody [does X] Anymore").
   - **Thumbnail**: the main image, the text on it (how many words), the emotion, the colours, and
     what it leaves out to make people curious.
   - **Promise**: what the viewer expects to get from clicking, in one sentence.
   - **Structure**: from the chapters if it has them. Note the order of the beats and how long the
     intro runs before the first payoff.
   - **Length**: how the length suits the topic.
   - **Why it worked**: your best guess at why this beat the channel's normal results, in 1-2 lines.

5. **Write `research/<date>-outliers.md`** using the template below. This is what `yt-plan` and
   `yt-script` read.

## Output template

```markdown
# Outlier research: <date>
Search terms: ... | Window: last N days | Quota used: ~N units

## Patterns that keep showing up
- Titles: ...
- Thumbnails: ...
- Lengths: ...
- Topics: ...

## Outliers
### 1. <title> (<score>x, <views> views, <length>)
<url>
- Title pattern: ...
- Thumbnail: ...
- Promise: ...
- Structure: ...
- Why it worked: ...
- **Our original angle:** a different video *we* could make using the same pattern
```

## Rules

- **Copy the pattern, never the content.** Our angle must be a new topic or a genuinely
  different take on one. Reusing another creator's title, script or thumbnail word for word
  breaks YouTube's rules on reused and inauthentic content, which blocks monetisation.
- Don't claim to know a video's retention or click-through rate. Only the creator can see those.
  Call those guesses "inferred".
- If the API errors with `quotaExceeded`, stop and say so. Don't retry until the next day
  (quota resets at midnight Pacific time).
