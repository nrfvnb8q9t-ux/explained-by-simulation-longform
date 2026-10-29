# esim engine reference

`from esim.engine import *` gives you everything below. The canvas is 1920x1080 (`W`, `H`), 30 fps.
Coordinates are pixels, y points down. Each scene function receives `f` (a Frame) and draws ONE frame
at time `f.t`. It must be a pure function of time: no state kept between frames, and no randomness
except `f.rng(...)`.

## Frame `f`
| | |
|---|---|
| `f.t`, `f.dur`, `f.p` | seconds into the scene, scene length, progress 0..1 |
| `f.word("gone")` | time the word starts being spoken (punctuation ignored). Raises if it isn't in the narration. `nth=1` for the 2nd occurrence |
| `f.prog(start, dur, ease=ease_in_out)` | eased 0..1 for an animation starting at `start` (seconds or a word) lasting `dur` |
| `f.since(at)` | seconds since `at` (negative before it) |
| `f.rng("key")` | numpy Generator, identical every frame of this scene, different in every video |
| `f.c` | the skia canvas, for anything custom (`skia.Path`, `drawLine`, etc.) |
| `f.beat_pulse(decay=9, min_strength=0)` | 1.0 on a music beat, fading before the next (bar lines 1.0, other beats 0.5). Make things throb: `r * (1 + 0.06 * f.beat_pulse())` |
| `f.next_beat(at)` | the first beat at or after `at`, to snap a hit onto the music |
| `f.since_drop()` | seconds since the latest music drop in this scene, or None |
| `f.intensity` | this scene's intensity from script.json |

## Scene registration
```python
@scene(3, sfx=[Sfx("808", "boom"), Sfx("reverse", "boom", offset=-1.4, dur=1.4)], hold=0.6, lead=0.35, edit="auto")
def s03(f): ...
```
- `scene(id)` must match the id in script.json. `hold` = extra seconds after the narration ends, `lead` = before it.
- `edit` = the automatic beat-synced edit layer applied on top of the scene: `"hype"` (zoom punch every
  beat, flash on bar lines), `"mid"` (punch on bar lines), `"calm"` (none) or `"auto"` (from intensity:
  0.6+ hype, 0.35+ mid). On a music drop, non-calm scenes also get a white flash, a zoom slam, a shake and an
  RGB split automatically. Don't add your own full-screen flash on a drop, or it doubles up.
- `Sfx(kind, at, offset=0, dur=None, gain_db=0)`. `at` is seconds, a word, "start" or "end".
  Kinds: `808` (distorted bass boom, the phonk hit; use on big words and drops), `reverse` (reversed cymbal
  swell into a hit; negative offset equal to its dur), `glitch` (digital stutter, for cuts and "error"
  moments), `whoosh` (movement, transitions), `impact` (collisions, big reveals), `rumble` (tension, quakes),
  `riser` (builds to a moment; negative offset so it peaks on the word), `tick` (numbers, timers),
  `shimmer` (wonder, sparkle), `power_down` (things switching off or dying), `pop` (labels, cards appearing),
  `chalk` (drawing on the board). Every effect is synthesised fresh with this scene's seed.

## Maths and easing
`clamp(x, lo, hi)`, `lerp(a, b, x)`, `ease_in_out`, `ease_out`, `ease_in`, `ease_back` (overshoots, for pops),
`orbit_point(cx, cy, rx, ry, turns)` gives (x, y) on an ellipse.

## Camera and layers
```python
with camera(f, cx, cy, zoom=1.2, rotate=0, shake=0):   # look at (cx, cy); shake in px (smooth rumble)
    ...
with layer(f, alpha=0.5):   # fade a group as one
    ...
with bloom(f, sigma=10, strength=1) as g:   # draw on g to make soft glowing light
    ...
```

## Backgrounds and finishing
`space(f, drift=(-4, 0), stars=420, nebula=True)`: channel's deep-space backdrop.
`gradient_bg(f, top, bottom)`, `starfield(f, n, drift, key=...)`, `nebula_glow(f, key=..., alpha=...)`,
`chalkboard(f)`: the whiteboard look. `vignette(f, 0.55)`, `fade(f, fade_in=0.4, fade_out=0.4)`,
`flash(f, at, dur=0.5, color, peak)`.

## Bodies
- `planet(f, kind, x, y, radius, rotation=turns, light=(lx, ly, lz), seed_key=None, atmosphere=True,
  night_lights=0, brightness=1, tint=None, alpha=1)`. kinds: `earth`, `frozen_earth`, `rocky`, `mars`,
  `gas`, `ice`, `lava`, `star`. Surfaces are procedural and unique. Pass the same `seed_key` (e.g. "earth")
  in every scene where the same planet should keep its continents. `light` points from the planet towards the light
  (x right, y down, z towards the viewer).
- `sun(f, x, y, radius, intensity=1)`: glowing star. Animate `intensity` to 0 to make it vanish.

## Effects
`glow(f, x, y, r, color, a)`, `soft_light(f, x, y, r, color, a)`, `halo(f, x, y, inner, outer, color, a)`,
`ring(f, x, y, r, width, color, a)`, `shockwave(f, x, y, at, speed=900, life=2, color, width=18)`,
`particles(f, x, y, at, n=220, speed=(lo, hi), life=(lo, hi), size=(lo, hi), color, gravity=(gx, gy),
spread=(deg0, deg1), key=..., drag=0.6)`, `trail(f, [(x, y), ...], color, width)`, `dots(f, xs, ys, sizes, alphas, color)`.

## Lines, whiteboard and text
- `draw_partial(f, path, progress, paint)`: draws the first part of any skia.Path (pen-drawing effect)
- `chalk(color, width, a, roughness, seed)`: hand-drawn stroke paint. Vary `seed` per stroke
- `paint(color, a, stroke=None, blur=0, add=False)`: plain skia paint
- `line_path(points, smooth=False)`, `arrow(f, x0, y0, x1, y1, progress, paint, head=22)`
- `orbit(f, cx, cy, rx, ry, color, a, width, dashed=True, progress=1, tilt=deg)`
- `text(f, s, x, y, size=64, color, a, align="center", weight="bold", reveal=1, glow_color=None, stroke=None)`
  weights: `bold`, `medium` (Space Grotesk), `body`, `semibold` (Inter), `hand`, `hand-light` (Caveat handwriting)
- `slam_text(f, s, x, y, at, size=150, color, glow_color=RED, hold=None, snap=True)`: edit-style text that
  slams in huge and crunches down with a jolt, snapped to the next beat. Use for the 1-4 word punchline of a
  big moment ("GONE.", "-73°C", "30 KM/S"). At most one every 20-30 seconds, or it stops hitting
- `handwrite(f, s, x, y, at, dur=1, size=64, color)`: text that writes itself on
- `label(f, s, x, y, tx, ty, at, size=36)`: callout with a leader line from a point
- `caption_card(f, title, sub, at, x, y, hold=None, color)`: lower-third fact card (big number + explanation)
- `counter(f, x, y, value, size, fmt="{:,.0f}", suffix="")`: a number (animate `value` yourself)
- `line_chart(f, (x, y, w, h), values, progress, color, y_range, x_labels=[(frac, "text")],
  y_labels=[(frac, "text")], title, zero_line, chalky=False)`

## Colours
`INK` (white text), `DIM` (grey), `CYAN`, `GOLD`, `RED`, `GREEN`, `CHALK_BG`, `BG_TOP`, `BG_BOTTOM`, or any `"#rrggbb"`.
`mix(c1, c2, x)` blends two colours.

## Speed budget
Aim for under 80 ms per frame. Planets cost the most (about 20 ms at radius 260), so use 1-3 big ones per
scene. Don't loop over thousands of skia calls per frame; use `dots()` for many points.
