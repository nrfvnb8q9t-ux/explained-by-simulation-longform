---
name: yt-plan
description: Plan a month (or any number of days) of long-form YouTube videos, one per upload day, based on outlier research, rotating formats, and never repeating topics. Writes a readable plan and a queue the automation works through. Use for "plan next month", "content calendar", "what should I make", or when the queue runs low.
---

# YouTube content planner

## Inputs

1. `channel.md`: niche, audience, formats, upload schedule, topics to avoid.
2. The latest `research/*-outliers.md`. If none exists or the newest is over 30 days old, run the
   `yt-outlier-research` skill first.
3. `content-log.md` and `plan/queue.json` (if they exist): everything already made or planned. Never
   plan a topic that's already in either.
4. How many days to plan: whatever the user asked for, otherwise 30. Upload days come from the
   schedule in `channel.md`. If it says `TODO`, assume one long video a day.

## Plan

Use the research to rank ideas. An idea is strong when:
- **It's proven.** It follows the pattern of at least one outlier (title formula, topic type, length).
- **It's ours.** It's a new topic or a clearly different take, not a remake of the outlier.
- **There's enough material.** It can honestly fill the long-form length in `channel.md` without padding.
  If it can't, make it a Short instead.
- **People search for it, or it stays relevant.** Prefer topics people will still look up in a year over news.

Then arrange the calendar:
- Rotate the formats in `channel.md`. Never use the same format two days in a row, and keep the formats
  roughly even across the month.
- Every 3rd-4th video, go back to the topic type that has performed best (once there's data in
  `content-log.md`, use it. Before that, use the research).
- Group related topics into short series of 2-3 videos, so one video leads to the next and the
  end-of-video pointer has somewhere to send people.
- Note 1-2 moments per video that would also work as a Short (the PC pipeline makes those).

## Output

**`plan/<YYYY-MM>.md`**, for the user to skim:
```markdown
# Content plan: <month>
Based on: research/<file> | Formats: deep-dive 8, ranked 8, versus 7, mystery 7

| Date | Format | Working title | Hook formula | Modelled on | Shorts angles |
|---|---|---|---|---|---|
| 2026-11-01 | deep-dive | ... | #1 cold open | <outlier title> | 1) ... 2) ... |

## Series
- <series name>: dates ...

## Why these ideas
2-4 bullet points connecting the plan to what the research found.
```

**`plan/queue.json`**: append to it, don't overwrite items that already exist:
```json
[
  {
    "date": "2026-11-01",
    "slug": "fall-of-the-aztec-capital",
    "format": "deep-dive",
    "working_title": "...",
    "angle": "one sentence: the specific story and why it's interesting",
    "hook_formula": 1,
    "modelled_on": "https://www.youtube.com/watch?v=...",
    "shorts_angles": ["...", "..."],
    "series": null,
    "status": "planned"
  }
]
```
`status` moves from `planned` to `scripting` (yt-script), `animating` (yt-animate), `scripted` (ready to render)
and finally `uploaded` (esim.daily). `render_failed` means yt-animate needs to fix it.
Shorts come from a separate pipeline, so `shorts_angles` is optional and only used as notes.

## Finish

Tell the user how many days were planned, the format split, and the 3 ideas you're most confident
in and why. Point out any idea that depends on facts you weren't able to check.
