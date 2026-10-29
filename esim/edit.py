"""The edit layer drawn over every scene: burned-in captions and scene transitions.

Captions: the narration, a few words at a time, big and bold at the bottom of the screen, with the word being
spoken highlighted and popping in (the short-form edit style). Kept in the bottom ~140px; scenes keep that clear.

Transitions: every scene opens with one and hype scenes punch out of themselves. Which one is picked from the
scene's energy (or set with "transition" in script.json):
    hype: glitch, zoom_punch, flash, whip        calm: fade, light_leak, slide, iris
"""

import math
from types import SimpleNamespace

import numpy as np
import skia

from esim import engine
from esim.engine import (CYAN, GOLD, H, INK, W, clamp, col, ease_in, ease_out, font, lerp, mix, paint,
                         soft_light, stable_seed)

T_IN = 0.42
T_OUT = 0.28
HYPE = ["glitch", "zoom_punch", "flash", "whip", "spin", "shutter"]
MID = ["whip", "zoom_punch", "shutter", "glitch", "spin"]
CALM = ["whip", "shutter", "light_leak", "iris", "zoom_punch"]
TRANSITION_SFX = {"glitch": ("glitch", -6), "zoom_punch": ("whoosh", -4), "whip": ("whoosh", -2),
                  "flash": ("reverse", -8), "light_leak": ("shimmer", -10), "slide": ("whoosh", -12),
                  "iris": ("whoosh", -8), "fade": None, "spin": ("whoosh", -2), "shutter": ("808", -10)}
CAPTION_Y = H - 72
CAPTION_SIZE = 60
HIGHLIGHT = "#ffd84a"


def pick_transition(seed, scene_id, level, override=None, first=False):
    if override:
        return override
    if first:
        return "fade"
    options = {"hype": HYPE, "mid": MID}.get(level, CALM)
    return options[stable_seed(seed, scene_id, "transition") % len(options)]


# ---------------------------------------------------------------- captions

def caption_chunks(words, max_words=4, max_gap=0.4):
    """Group the narration's words into short on-screen phrases that break at pauses and punctuation."""
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w[1] - cur[-1][2] > max_gap or cur[-1][0][-1:] in ".?!,;:"):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def draw_captions(c, t, chunks, accent=HIGHLIGHT):
    chunk = None
    for ch in chunks:
        if ch[0][1] - 0.06 <= t <= ch[-1][2] + 0.25:
            chunk = ch
            break
    if not chunk:
        return
    labels = [w[0].upper() for w in chunk]
    size = CAPTION_SIZE
    fnt = font(size, "bold")
    gap = size * 0.32
    widths = [fnt.measureText(s) for s in labels]
    total = sum(widths) + gap * (len(widths) - 1)
    if total > W - 240:
        size = size * (W - 240) / total
        fnt = font(size, "bold")
        widths = [fnt.measureText(s) for s in labels]
        gap = size * 0.32
        total = sum(widths) + gap * (len(widths) - 1)
    appear = clamp((t - (chunk[0][1] - 0.06)) / 0.1)
    x = W / 2 - total / 2
    stroke = paint("#000000", 0.92 * appear, stroke=size * 0.16, cap_round=False)
    for (word, s, e), label, wd in zip(chunk, labels, widths):
        speaking = s <= t <= e + 0.05
        pop = 1 + (0.14 * math.exp(-(t - s) * 16) if t >= s else 0)
        colour = accent if speaking else INK
        a = appear * (1 if t >= s - 0.02 else 0.55)
        cx = x + wd / 2
        c.save()
        c.translate(cx, CAPTION_Y)
        c.scale(pop, pop)
        c.drawString(label, -wd / 2, size * 0.35, fnt, stroke)
        c.drawString(label, -wd / 2, size * 0.35, fnt, paint(colour, a))
        c.restore()
        x += wd + gap


# ---------------------------------------------------------------- transitions

def transition_state(kind, t, dur, level):
    """What the transition does at time t: a pre-draw camera change and post-draw overlays."""
    st = {"zoom": 1.0, "dx": 0.0, "dy": 0.0, "flash": 0.0, "black": 0.0, "leak": 0.0, "iris": None,
          "split": 0.0, "slices": 0.0, "rotate": 0.0, "shutter": 0.0}
    if t < T_IN:
        k = t / T_IN
        inv = 1 - ease_out(k)
        if kind == "glitch":
            st.update(split=min(1, inv * 1.3), slices=min(1, inv * 1.3), flash=0.35 * inv ** 2, zoom=1 + 0.05 * inv)
        elif kind == "zoom_punch":
            st.update(zoom=1 + 0.42 * inv, flash=0.6 * inv ** 2, split=0.6 * inv)
        elif kind == "flash":
            st.update(flash=1.0 * inv ** 1.2, zoom=1 + 0.1 * inv)
        elif kind == "whip":
            st.update(dx=W * 0.45 * inv, flash=0.25 * inv, split=0.5 * inv)
        elif kind == "spin":
            st.update(rotate=-14 * inv, zoom=1 + 0.35 * inv, flash=0.3 * inv ** 2)
        elif kind == "shutter":
            st.update(shutter=inv, flash=0.15 * inv)
        elif kind == "fade":
            st.update(black=inv)
        elif kind == "light_leak":
            st.update(leak=inv, black=0.4 * inv)
        elif kind == "slide":
            st.update(dy=70 * inv, black=0.7 * inv)
        elif kind == "iris":
            st.update(iris=ease_out(k))
    if t > dur - T_OUT:  # every scene punches out into the next one
        k = (t - (dur - T_OUT)) / T_OUT
        st["zoom"] *= 1 + (0.16 if level == "hype" else 0.09) * ease_in(k)
        st["flash"] = max(st["flash"], (0.45 if level == "hype" else 0.2) * k ** 2)
    return st


def draw_transition_overlays(c, st, t, seed):
    if st["shutter"] > 0.01:  # black bars slam in from top and bottom, then open
        bar = H / 2 * st["shutter"]
        c.drawRect(skia.Rect.MakeLTRB(0, 0, W, bar), paint("#000000", 1))
        c.drawRect(skia.Rect.MakeLTRB(0, H - bar, W, H), paint("#000000", 1))
        c.drawLine(0, bar, W, bar, paint(CYAN, 0.9 * st["shutter"], stroke=4))
        c.drawLine(0, H - bar, W, H - bar, paint(CYAN, 0.9 * st["shutter"], stroke=4))
    if st["leak"] > 0.01:
        for i, (hue, x, y) in enumerate(((GOLD, 0.2, 0.3), ("#ff6a3d", 0.75, 0.6), ("#ffd1e8", 0.5, 0.2))):
            r = 900 + 200 * math.sin(t * 3 + i)
            soft_light(SimpleNamespace(c=c), W * x + 300 * t, H * y, r, hue, 0.65 * st["leak"])
    if st["iris"] is not None:
        r = lerp(10, math.hypot(W, H) * 0.55, st["iris"])
        path = skia.Path()
        path.setFillType(skia.PathFillType.kEvenOdd)
        path.addRect(skia.Rect.MakeWH(W, H))
        path.addCircle(W / 2, H / 2, r)
        c.drawPath(path, paint("#000000", 1))
        c.drawCircle(W / 2, H / 2, r, paint(CYAN, 0.6 * (1 - st["iris"]), stroke=6))
    if st["black"] > 0.005:
        c.drawPaint(paint("#000000", min(st["black"], 1)))
    if st["flash"] > 0.005:
        c.drawPaint(paint("#ffffff", min(st["flash"], 1)))


def glitch_slices(arr, amount, seed, index, scale):
    """Horizontal bands of the picture shoved sideways: the digital-glitch transition."""
    if amount < 0.05:
        return
    rng = np.random.default_rng(stable_seed(seed, "glitch", index))
    h = arr.shape[0]
    for _ in range(int(3 + 9 * amount)):
        y0 = int(rng.random() * h)
        bh = int((8 + rng.random() * 70) * scale)
        shift = int((rng.random() - 0.5) * 220 * amount * scale)
        arr[y0:y0 + bh] = np.roll(arr[y0:y0 + bh], shift, axis=1)
