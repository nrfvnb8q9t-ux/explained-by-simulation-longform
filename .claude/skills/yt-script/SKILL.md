---
name: yt-script
description: Write a complete long-form YouTube script (15-25 min, built to hold viewers) with titles, description, chapters, tags, thumbnail and sources, as videos/<slug>/script.json for the esim renderer. Use for "write a script", "next video", or a topic or plan item to script. Follow it with yt-animate.
---

# YouTube script writer (long-form)

Shorts are made by a separate pipeline on the user's PC. This skill writes long-form only.

## Before writing

1. Read `channel.md` for the niche, narrator persona, lengths and things to avoid.
2. Pick the topic:
   - If the user gave one, use it.
   - Otherwise take the earliest item with `"status": "planned"` from `plan/queue.json` (made by `yt-plan`),
     and set it to `"scripting"`.
3. Read the most recent `research/*-outliers.md` if one exists, and the outlier this plan item is
   modelled on. Use its **pattern** (title formula, structure, length), never its content.
4. Read `content-log.md` (if it exists) so you don't repeat a topic, a hook formula or a title
   pattern used in the last 10 videos.
5. Read `references/hooks.md` and `references/retention.md` in this skill's folder.
6. **Research the facts.** Use web search. Note the source of every number, date, name and quote. If you
   can't confirm a claim, cut it or word it as an estimate ("one estimate says...", "physicists think...").
   Never invent quotes, statistics or sources.

## Write

Follow the structure in `retention.md`. Target the word count in `channel.md` (150 words per minute).

Split the narration into **scenes of 15-45 seconds** (about 40-110 words each), usually 30-60 per video.
Each scene is one visual idea the animator can build. End a scene where the picture should change.

- Write numbers the way they should be spoken ("eight minutes and twenty seconds", "minus seventy three").
  The voice reads exactly what's written.
- Use short sentences. Put the word that matters most where a visual can land on it ("...and then it **explodes**.").
- Give each scene a `mood` (`wonder`, `calm`, `tense`, `mystery`, `epic`) and an `intensity` from 0 to 1.
  The music and the edit follow them (see "Edit style" in `channel.md`):
  - 0.6+ is a **hype** scene: high-energy music, with beat punches, flashes and slam text.
  - Under 0.35 is a **breather**: whiteboard explanations, charts, calmer music.
  - The hook (scene 1) is always hype, and it ends on a shocking fact or image within 20 seconds.
  - **A shock drop every 60-90 seconds.** That's a jaw-dropping fact revealed on one word ("...and it would be
    **one million** times brighter than the Sun"). Build up to it for 1-2 sentences first ("Here's where it gets
    insane.", "Now look at the number."), put the `drop` on the reveal word, and use the `reveal` template or a
    custom hero scene. Aim for 8-12 drops in a 12-15 minute video.
  - Between drops, breathers explain the science so the next drop lands. Several hype scenes in a row merge
    into one music section, so put a breather between drops whenever you can.
  - Escalate: each drop bigger than the last, with the biggest kept for the climax near the end.
- On a hype scene's biggest word, add `"drop": "<word>"`. The music's drop lands exactly on that word
  (e.g. `"drop": "gone"` for "Just... gone."). The word must appear in that scene's narration.
- Don't add pause markers or extra punctuation for timing. The narrator's natural pacing is used as-is.
- Put a `chapter` name on the first scene of each chapter, 5-10 chapters per video.
- **All ages:** no gore, no swearing, nothing frightening for its own sake. Describe disasters through
  physics and scale, not suffering.

## Shots: how each scene looks

Every scene gets a `"shot"` that picks one of the 48 templates in `references/templates.md` and fills it in
with this scene's facts, numbers and labels. The renderer draws it, with no code needed. Read that file before
you write the shots.

```json
"shot": {
  "template": "impact",
  "params": {"target": "earth", "impactor": "asteroid", "at": "hits", "from": "left"},
  "slam": {"text": "BOOM", "at": "hits", "color": "gold"},
  "cards": [{"title": "20 km/s", "sub": "impact speed", "at": "twenty"}],
  "note": "not to scale",
  "sfx": [{"kind": "glitch", "at": "hits", "offset": 0.2}]
}
```
- Every `at` is a word from **that scene's** narration (or seconds into the scene). Templates add their own
  sound design, and `sfx` adds extra on top.
- `slam` is the big punchline text for a hype moment (1-3 words). `cards` are fact cards for key numbers.
- Leave out params you don't care about. Anything left out (layout, colours, camera move, board style) is picked
  at random for this video, which is how videos stay different.
- **Variety rules:** don't use the same template more than 3 times in one video, or twice in a row. Mix space
  simulations, whiteboard scenes (`board_*`), data scenes and cinematic scenes. Open each chapter with a
  `title_card`, `warp`, `kinetic_text` or `question_card`. Check `content-log.md` and lean towards templates the
  last few videos didn't use much.
- **Hero scenes:** mark the **5-7 biggest moments** (the hook, the biggest drops and the climax) with `"custom": true`
  and no shot. `yt-animate` writes bespoke animation code for exactly those. Keep it to 7 at most, because custom code
  uses far more of the daily Claude budget than templates do. Other drops use the `reveal` template.
- **Transitions:** every scene gets an automatic transition (glitch, zoom punch, flash, whip, spin, shutter, iris or
  light leak), picked from its energy. To choose one, add `"transition": "<name>"` to the scene. Give chapter openings
  and drops the big ones (`flash`, `glitch`, `shutter`).
- **Captions are burned in automatically** along the bottom of every scene (except `kinetic_text`). Add
  `"captions": false` only to a scene whose own on-screen text would clash.

**Packaging:**
- 5 title options (under 70 characters, strongest first). Use different formulas, front-load the most
  interesting word, and make sure each one matches what the video actually delivers.
- Thumbnail: which scene and which word to freeze on (pick a dramatic moment), plus 2-4 words of big text
  that add to the title rather than repeating it.
- Description: the first two lines restate the hook (they show in search). The renderer adds the chapters,
  sources and a simulation disclaimer.
- 8-15 tags.

## Output: `videos/<slug>/script.json`

```json
{
  "slug": "what-if-the-moon-was-twice-as-close",
  "format": "timeline-what-if",
  "voice": "am_puck",
  "modelled_on": "https://www.youtube.com/watch?v=...",
  "long": {
    "titles": ["...", "...", "...", "...", "..."],
    "thumbnail": {"scene": 7, "word": "tides", "offset": 0.5, "text": "TIDES 30 M HIGH"},
    "description": "...",
    "tags": ["..."],
    "scenes": [
      {
        "id": 1,
        "chapter": "The Moon moves in",
        "mood": "tense",
        "intensity": 0.7,
        "drop": "closer",
        "narration": "Exactly what the voice says, including the drop word: closer.",
        "custom": true,
        "visual": "for custom scenes: what the hero animation should show"
      },
      {
        "id": 2,
        "mood": "mystery",
        "intensity": 0.3,
        "narration": "...",
        "shot": {"template": "board_diagram", "params": {"nodes": [{"label": "Earth", "shape": "planet", "at": "Earth"}]}}
      }
    ]
  },
  "sources": [{"claim": "...", "url": "..."}],
  "realistic_content": false
}
```
Leave `"realistic_content": false`. This channel's videos are clearly animated simulations with a generic narrator, which YouTube doesn't require an AI label for. Only set it to `true` if a video shows something realistic enough to be mistaken for real footage of a real person, event or place.
The slug is lowercase words joined by hyphens, and it must be new (check `videos/` and `content-log.md`).
Set `"voice"` to the narrator voice named in `channel.md` (currently `am_puck`).

Check the shots render before moving on (it catches misspelt `at` words and bad params):
```bash
uv run python -m esim.render videos/<slug> --preview --scenes <ids of the shot scenes>
```
Then set the plan item's status to `"animating"` and run the `yt-animate` skill for the custom scenes.

## Quality check before finishing

Fix anything that fails:
- [ ] The hook's specific promise is paid off in the video
- [ ] There's a re-hook at least every 4 minutes of runtime
- [ ] Every number, date and quote is in `sources`
- [ ] No sentence that could be cut without losing anything
- [ ] Total word count is within 10% of the target
- [ ] Nothing is copied from the outlier video beyond its general pattern
- [ ] Every scene has a shot or `"custom": true`, with 3-6 custom at most
- [ ] No template used more than 3 times, none twice in a row
- [ ] Suitable for all ages
