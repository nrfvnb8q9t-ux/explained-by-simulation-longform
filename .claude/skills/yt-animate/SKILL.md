---
name: yt-animate
description: Write bespoke animation code (scenes.py) for a scripted video's hero scenes, the 3-6 scenes marked "custom": true, using the esim engine, then test-render the whole video. Template shots handle every other scene. Use after yt-script, for "animate this script", or when a video in plan/queue.json failed to render.
---

# Animate a video's hero scenes

Input: `videos/<slug>/script.json` (from `yt-script`). Most scenes have a template `"shot"` and need no code.
Output: `videos/<slug>/scenes.py`, with one `@scene` function **for each scene marked `"custom": true`**.
These are the hook, the drops and the climax, so make them the best-looking moments in the video. If a
scene has both a shot and an `@scene` function, the function wins.

Before you write anything, look at what the templates already do (`.claude/skills/yt-script/references/templates.md`),
so hero scenes are clearly a step above them rather than a copy of one.

## Rules that never bend

1. **Everything is new for this video.** Don't copy scene code from other videos in `videos/`. You can
   look at one for engine usage, but design new compositions, camera moves, colours and effects that fit
   *this* script. The renderer blocks uploads whose shots look like an earlier video's.
2. **Animate what's being said, when it's said.** Time every key moment to its word with `f.word(...)`
   or `f.prog("word", dur)`. When the narrator says "it explodes", the explosion lands on "explodes".
3. **Something changes every 3-6 seconds:** a camera move, a new object, a label, an effect or a cut to
   the whiteboard. Static frames lose viewers.
4. **Hero scenes are cinematic.** Layer the effects: a planet plus particles plus a shockwave plus a camera
   move plus slam text, timed to the beat and the drop. The templates already cover the plain explanations.
   You can also reuse template building blocks inside a hero scene (`from esim.templates import body,
   draw_black_hole`) and build something bigger around them.
5. **Be honest to the science.** Get sizes, directions and orders of events right where they're
   stated. If the scale is exaggerated so it can be seen, a small `text` note says "not to scale".
6. **Sound design:** give every scene 2-5 `Sfx`. Put an 808 (with a `reverse` swell into it) on the
   biggest word of a hype scene, a whoosh on fast motion, ticks on counters, pops on labels and cards, and
   chalk while drawing. Don't stack more than 2 effects within half a second.
7. **The edit style is hype: phonk edit meets science explainer.** Hype scenes should feel like an edit:
   - things that throb with the beat (`f.beat_pulse()` on glows, planet sizes, text scale)
   - hard visual changes snapped to beats (`f.next_beat(...)`) rather than random times
   - a `slam_text` punchline on the scene's biggest moment
   - fast camera moves and shake on impacts
   Calm and whiteboard scenes are the breather between hits: let the music sit back, and keep them clean
   so the contrast makes the next drop hit harder. The renderer adds beat zoom punches and drop flashes
   automatically from each scene's intensity, so don't recreate those by hand.

## Steps

1. Read `channel.md`, `videos/<slug>/script.json` and `references/engine.md` (in this skill's folder).
2. Plan each scene in a comment at the top of its function: what's on screen, the camera, and the
   moments tied to words.
3. Write `scenes.py`: `from esim.engine import *` (plus `import math`, `import skia` if needed), with
   helper functions at the top for anything used twice.
4. **Test every scene** with a fast preview render. It catches crashes, including misspelt words in
   `f.word(...)`:
   ```bash
   uv run python -m esim.render videos/<slug> --preview --scenes 1,2,3
   ```
   Fix any errors and re-run until all scenes render. Then grab a few frames and look at them:
   ```bash
   uv run python -c "import imageio_ffmpeg,sys;print(imageio_ffmpeg.get_ffmpeg_exe())"
   <ffmpeg> -loglevel error -y -i build/<slug>/segments/000.mp4 -vf "fps=1,scale=640:-1,tile=4x2" -frames:v 1 build/<slug>/check.png
   ```
   Read the image. Check that text is readable, nothing important is off-screen, and nothing is too dark.
5. When every scene renders, set the item's status in `plan/queue.json` to `"scripted"`.

## When fixing a failed render

`plan/queue.json` items with `"status": "render_failed"` have an `error_log` path. Read it, fix
`scenes.py` (usually a word that isn't in the narration, or a typo), re-run the preview for that scene,
then set the status back to `"scripted"`.
