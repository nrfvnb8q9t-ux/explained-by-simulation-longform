"""Drawing toolkit for scenes.

A video's scenes.py registers one function per scene with @scene. The renderer calls each function
once per frame with a Frame, and the function draws that moment from scratch. Scenes are pure
functions of time, so any frame can be rendered on its own and scenes render in parallel.

    from esim.engine import *

    @scene(1, sfx=[Sfx("impact", "gone")])
    def s01(f):
        space(f)
        x = lerp(400, 960, f.prog(0, 3))
        planet(f, "earth", x, 540, 220, rotation=f.t * 0.02)
"""

import bisect
import math
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import skia

W, H = 1920, 1080
FPS = 30
ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Brand palette. Scenes may tint and mix these, but the channel keeps one look.
BG_TOP = "#070b1a"
BG_BOTTOM = "#02030a"
INK = "#f2f5ff"
DIM = "#8a93b5"
CYAN = "#4fd1ff"
GOLD = "#ffb347"
RED = "#ff5a4f"
GREEN = "#6dff9c"
CHALK_BG = "#111a22"


# ---------------------------------------------------------------- scene registry

@dataclass
class Sfx:
    """A sound effect placed in a scene. `at` is seconds into the scene, a word from the narration
    (its start time), "start" or "end". `offset` shifts it, e.g. Sfx("riser", "boom", offset=-2)."""
    kind: str
    at: object = "start"
    offset: float = 0.0
    dur: float = None
    gain_db: float = 0.0


SCENES = {}


def scene(scene_id, sfx=(), hold=0.6, lead=0.35, edit="auto"):
    """Register a scene. `hold` is extra time after the narration ends, `lead` the time before it starts.
    `edit` sets the automatic beat-synced editing: "hype" (zoom punch on every beat, hits on drops),
    "mid" (punch on bar lines), "calm" (none), or "auto" (from the scene's intensity in script.json)."""
    def deco(fn):
        SCENES[scene_id] = {"fn": fn, "sfx": list(sfx), "hold": hold, "lead": lead, "edit": edit}
        return fn
    return deco


# ---------------------------------------------------------------- time and maths

def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def lerp(a, b, x):
    return a + (b - a) * x


def ease_in_out(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out(x):
    return 1 - (1 - clamp(x)) ** 3


def ease_in(x):
    return clamp(x) ** 3


def ease_back(x):
    """Overshoots slightly then settles: good for things popping in."""
    x = clamp(x)
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def stable_seed(*parts):
    return zlib.crc32("|".join(map(str, parts)).encode()) & 0x7FFFFFFF


@dataclass
class Frame:
    c: skia.Canvas
    t: float
    dur: float
    index: int
    seed: int
    scene_id: object
    words: list = field(default_factory=list)  # [(word, start, end)] in scene time
    fps: int = FPS
    w: int = W
    h: int = H
    beats: list = field(default_factory=list)  # [(time, strength)] in scene time; 1.0 = bar line, 0.5 = beat
    drops: list = field(default_factory=list)  # music drops, in scene time
    intensity: float = 0.4

    @property
    def p(self):
        return clamp(self.t / self.dur) if self.dur else 1.0

    def beat_pulse(self, decay=9.0, min_strength=0.0):
        """1.0 right on a beat, fading towards 0 before the next. Bar lines hit 1.0, other beats 0.5.
        Use it to make things throb with the music: scale = 1 + 0.05 * f.beat_pulse()."""
        i = bisect.bisect_right(self.beats, (self.t, 9.9)) - 1
        while i >= 0 and self.beats[i][1] < min_strength:
            i -= 1
        if i < 0:
            return 0.0
        t, s = self.beats[i]
        return s * math.exp(-(self.t - t) * decay)

    def next_beat(self, after, min_strength=0.0):
        """The first beat at or after `after` (seconds or a word), to snap a hit onto the music."""
        a = self.time(after)
        for t, s in self.beats:
            if t >= a - 0.04 and s >= min_strength:
                return t
        return a

    def since_drop(self):
        """Seconds since the most recent music drop, or None if there hasn't been one in this scene."""
        past = [d for d in self.drops if d <= self.t]
        return self.t - past[-1] if past else None

    def rng(self, key="main"):
        """Random numbers that are identical on every frame of this scene, and different in every video."""
        return np.random.default_rng(stable_seed(self.seed, self.scene_id, key))

    def word(self, w, nth=0, default=None):
        """Scene time at which the nth occurrence of word `w` starts being spoken."""
        target = _norm(w)
        hits = [s for word, s, _ in self.words if _norm(word) == target]
        if len(hits) > nth:
            return hits[nth]
        if default is not None:
            return default
        spoken = " ".join(word for word, _, _ in self.words)
        raise ValueError(f"Scene {self.scene_id}: the word '{w}' (occurrence {nth + 1}) isn't in the narration. "
                         f"Spoken words: {spoken}")

    def time(self, at):
        if isinstance(at, str):
            return {"start": 0.0, "end": self.dur}.get(at, None) if at in ("start", "end") else self.word(at)
        return float(at)

    def prog(self, start, dur, ease=ease_in_out):
        """Eased 0..1 progress of an animation starting at `start` (seconds or a word) lasting `dur`."""
        s = self.time(start)
        return ease((self.t - s) / dur) if dur > 0 else float(self.t >= s)

    def since(self, at):
        return self.t - self.time(at)


def _norm(w):
    return "".join(ch for ch in w.lower() if ch.isalnum())


# ---------------------------------------------------------------- colour and paint

@lru_cache(maxsize=512)
def _rgb(hex_color):
    if not isinstance(hex_color, str):  # already an (r, g, b) tuple, e.g. from mix()
        return tuple(float(v) for v in hex_color[:3])
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def col(c, a=1.0):
    """skia colour from '#rrggbb' (or an (r,g,b) 0..1 tuple) with alpha a."""
    r, g, b = _rgb(c) if isinstance(c, str) else c
    return skia.Color4f(r, g, b, clamp(a)).toColor()


def mix(c1, c2, x):
    a, b = (_rgb(c) if isinstance(c, str) else c for c in (c1, c2))
    return tuple(lerp(a[i], b[i], clamp(x)) for i in range(3))


def paint(color=INK, a=1.0, stroke=None, blur=0.0, add=False, cap_round=True):
    p = skia.Paint(AntiAlias=True, Color=col(color, a))
    if stroke is not None:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(stroke)
        if cap_round:
            p.setStrokeCap(skia.Paint.kRound_Cap)
            p.setStrokeJoin(skia.Paint.kRound_Join)
    if blur > 0:
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
    if add:
        p.setBlendMode(skia.BlendMode.kPlus)
    return p


# ---------------------------------------------------------------- camera

@contextmanager
def camera(f, cx=W / 2, cy=H / 2, zoom=1.0, rotate=0.0, shake=0.0):
    """Everything drawn inside is seen through a camera centred on (cx, cy).
    `shake` is in pixels; it's smooth noise, not jitter, so it reads as a rumble."""
    c = f.c
    c.save()
    sx = sy = 0.0
    if shake:
        t = f.t
        sx = shake * (math.sin(t * 23.1) * 0.6 + math.sin(t * 41.7 + 1.3) * 0.4)
        sy = shake * (math.sin(t * 19.3 + 2.1) * 0.6 + math.sin(t * 37.9 + 0.4) * 0.4)
    c.translate(W / 2 + sx, H / 2 + sy)
    c.scale(zoom, zoom)
    if rotate:
        c.rotate(rotate)
    c.translate(-cx, -cy)
    try:
        yield c
    finally:
        c.restore()


@contextmanager
def bloom(f, sigma=10, strength=1.0, scale=0.25):
    """Anything drawn on the yielded frame becomes soft glowing light. It's drawn at quarter size,
    blurred and scaled back up, which is fast and looks like real lens bloom."""
    sw, sh = int(W * scale), int(H * scale)
    s1 = skia.Surface(sw, sh)
    c1 = s1.getCanvas()
    c1.clear(skia.ColorTRANSPARENT)
    c1.scale(scale, scale)
    c1.concat(f.c.getTotalMatrix())  # follow the camera
    g = Frame(c=c1, t=f.t, dur=f.dur, index=f.index, seed=f.seed, scene_id=f.scene_id, words=f.words, fps=f.fps)
    try:
        yield g
    finally:
        s2 = skia.Surface(sw, sh)
        s2.getCanvas().clear(skia.ColorTRANSPARENT)
        blur = skia.ImageFilters.Blur(sigma * scale, sigma * scale)
        s2.getCanvas().drawImage(s1.makeImageSnapshot(), 0, 0, skia.SamplingOptions(), skia.Paint(ImageFilter=blur))
        f.c.save()
        f.c.resetMatrix()
        f.c.drawImageRect(s2.makeImageSnapshot(), skia.Rect.MakeWH(W, H),
                          skia.SamplingOptions(skia.FilterMode.kLinear),
                          skia.Paint(BlendMode=skia.BlendMode.kPlus, Alphaf=clamp(strength)))
        f.c.restore()


@contextmanager
def layer(f, alpha=1.0):
    """Group drawing so it fades as one (avoids overlaps showing through)."""
    f.c.saveLayer(paint=skia.Paint(Alphaf=clamp(alpha)))
    try:
        yield f.c
    finally:
        f.c.restore()


# ---------------------------------------------------------------- backgrounds

def gradient_bg(f, top=BG_TOP, bottom=BG_BOTTOM):
    shader = skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(0, H)], [col(top), col(bottom)])
    f.c.drawPaint(skia.Paint(Shader=shader))


def dots(f, xs, ys, sizes, alphas, color=INK, add=False, buckets=4):
    """Draw many round dots fast by batching them into a few size/alpha groups."""
    if len(xs) == 0:
        return
    xs = np.atleast_1d(np.asarray(xs, np.float32))  # plain lists and single numbers are fine too
    ys = np.atleast_1d(np.asarray(ys, np.float32))
    sizes = np.broadcast_to(np.asarray(sizes, np.float32), xs.shape)
    alphas = np.broadcast_to(np.asarray(alphas, np.float32), xs.shape)
    sizes = np.asarray(sizes, np.float32)
    alphas = np.clip(np.asarray(alphas, np.float32), 0, 1)
    s_lo, s_hi = float(sizes.min()), float(sizes.max()) + 1e-6
    s_idx = np.minimum(((sizes - s_lo) / (s_hi - s_lo) * buckets).astype(int), buckets - 1)
    a_idx = np.minimum((alphas * buckets).astype(int), buckets - 1)
    for si in range(buckets):
        for ai in range(buckets):
            sel = (s_idx == si) & (a_idx == ai)
            if not sel.any():
                continue
            width = (s_lo + (si + 0.5) / buckets * (s_hi - s_lo)) * 2
            alpha = (ai + 0.5) / buckets
            p = paint(color, alpha, stroke=width, add=add)
            pts = [skia.Point(float(x), float(y)) for x, y in zip(xs[sel], ys[sel])]
            f.c.drawPoints(skia.Canvas.kPoints_PointMode, pts, p)


def starfield(f, n=420, drift=(0.0, 0.0), twinkle=True, key="stars", alpha=1.0, parallax=1.0):
    """Stars at fixed random positions for this scene. `drift` is pixels/sec for the nearest layer;
    farther stars move less (parallax)."""
    rng = f.rng(key)
    xs, ys = rng.random(n) * W, rng.random(n) * H
    depth = rng.random(n) ** 2  # most stars far away
    size = 0.6 + depth * 2.2
    bright = 0.25 + depth * 0.75
    phase = rng.random(n) * 6.28
    speed = 0.5 + rng.random(n) * 2.5
    tint = rng.random(n)
    dx, dy = drift[0] * f.t * parallax, drift[1] * f.t * parallax
    xs = (xs + dx * (0.2 + depth)) % W
    ys = (ys + dy * (0.2 + depth)) % H
    if twinkle:
        bright = bright * (0.75 + 0.25 * np.sin(f.t * speed + phase))
    for colour, sel in ((CYAN, tint > 0.93), (GOLD, tint < 0.05), (INK, (tint >= 0.05) & (tint <= 0.93))):
        dots(f, xs[sel], ys[sel], size[sel], bright[sel] * alpha, colour)


def space(f, drift=(-4.0, 0.0), stars=420, nebula=True):
    """The channel's default deep-space backdrop, different in every video."""
    gradient_bg(f)
    if nebula:
        nebula_glow(f)
    starfield(f, n=stars, drift=drift)


def nebula_glow(f, key="nebula", alpha=0.35):
    rng = f.rng(key)
    c = f.c
    for i in range(4):
        x, y = rng.random() * W, rng.random() * H
        r = 300 + rng.random() * 500
        hue = [CYAN, "#7a5cff", "#ff4fa3", GOLD][int(rng.integers(0, 4))]
        wobble = 1 + 0.05 * math.sin(f.t * 0.3 + i)
        shader = skia.GradientShader.MakeRadial(skia.Point(x, y), r * wobble,
                                               [col(hue, alpha * (0.4 + rng.random() * 0.6)), col(hue, 0)])
        c.drawCircle(x, y, r * wobble, skia.Paint(Shader=shader, BlendMode=skia.BlendMode.kPlus))


def chalkboard(f, key="board"):
    """A dark slate board with faint smudges, for whiteboard-style explanations."""
    f.c.clear(col(CHALK_BG))
    rng = f.rng(key)
    for _ in range(14):
        x, y, r = rng.random() * W, rng.random() * H, 120 + rng.random() * 380
        soft_light(f, x, y, r, INK, 0.015 + rng.random() * 0.025, add=False)


def vignette(f, strength=0.55):
    shader = skia.GradientShader.MakeRadial(skia.Point(W / 2, H / 2), W * 0.75,
                                           [col("#000000", 0), col("#000000", strength)], [0.55, 1.0])
    f.c.drawPaint(skia.Paint(Shader=shader))


def fade(f, fade_in=0.4, fade_out=0.4):
    """Fade from/to black at the scene's edges."""
    a = 0.0
    if fade_in and f.t < fade_in:
        a = 1 - f.t / fade_in
    if fade_out and f.t > f.dur - fade_out:
        a = max(a, (f.t - (f.dur - fade_out)) / fade_out)
    if a > 0:
        f.c.drawPaint(paint("#000000", a))


def flash(f, at, dur=0.5, color="#ffffff", peak=0.9):
    """A full-screen flash of light starting at `at`."""
    s = f.since(at)
    if 0 <= s <= dur:
        f.c.drawPaint(paint(color, peak * (1 - s / dur) ** 2))


# ---------------------------------------------------------------- noise and procedural textures

def _value_noise(w, h, rng, cells_x, cells_y):
    grid = rng.random((cells_y + 1, cells_x)).astype(np.float32)
    xs = np.linspace(0, cells_x, w, endpoint=False)
    ys = np.linspace(0, cells_y, h)
    x0 = np.floor(xs).astype(int)
    y0 = np.minimum(np.floor(ys).astype(int), cells_y - 1)
    fx = xs - x0
    fy = ys - y0
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    x1 = (x0 + 1) % cells_x  # wraps horizontally so planets can spin seamlessly
    y1 = y0 + 1
    a = grid[y0][:, x0]
    b = grid[y0][:, x1]
    c = grid[y1][:, x0]
    d = grid[y1][:, x1]
    top = a + (b - a) * fx[None, :]
    bot = c + (d - c) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def fractal_noise(w, h, rng, octaves=6, base=4, stretch=1.0):
    """Seamless-in-x fractal noise in 0..1. `stretch` > 1 squashes it into horizontal bands."""
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cx = base * 2 ** o
        cy = max(2, int(cx * h / w * 2 / stretch))
        out += amp * _value_noise(w, h, rng, cx, cy)
        total += amp
        amp *= 0.5
    return out / total


def ramp(values, stops):
    """Map 0..1 values through colour stops [(pos, '#hex'), ...] to an RGB float array."""
    pos = [p for p, _ in stops]
    rgb = np.array([_rgb(c) for _, c in stops], np.float32)
    return np.stack([np.interp(values, pos, rgb[:, i]) for i in range(3)], axis=-1)


PLANET_STYLES = {
    "earth": dict(stops=[(0, "#0b2a5b"), (0.52, "#1d5fa8"), (0.555, "#d9c58f"), (0.6, "#3f7d3a"),
                         (0.75, "#2c5a2a"), (0.86, "#8a7a5c"), (0.93, "#f4f6fb"), (1, "#ffffff")],
                  clouds=True, atmosphere=CYAN),
    "rocky": dict(stops=[(0, "#3b3735"), (0.45, "#7b736b"), (0.7, "#a59a8f"), (1, "#d8d0c6")],
                  craters=True, atmosphere=None),
    "mars": dict(stops=[(0, "#5a2412"), (0.45, "#a4472a"), (0.7, "#c96a3d"), (0.9, "#e3a27a"), (1, "#fff1e6")],
                 craters=True, atmosphere="#ff9f7a"),
    "gas": dict(stops=[(0, "#6b4a2f"), (0.3, "#c79a6b"), (0.5, "#f1dcc0"), (0.7, "#b5764a"), (1, "#f6eadb")],
                stretch=14, atmosphere=GOLD),
    "ice": dict(stops=[(0, "#2a4c6b"), (0.5, "#7fb3d5"), (0.8, "#d6ecf7"), (1, "#ffffff")],
                stretch=6, atmosphere="#9fe6ff"),
    "lava": dict(stops=[(0, "#ffd36b"), (0.08, "#ff6a1f"), (0.14, "#3a1208"), (0.6, "#1d0b06"), (1, "#3d2a22")],
                 emissive_below=0.12, atmosphere=RED),
    "frozen_earth": dict(stops=[(0, "#1b2f45"), (0.52, "#3b5a78"), (0.555, "#c9d6e2"), (1, "#ffffff")],
                         atmosphere="#bcd7ff"),
    "star": dict(stops=[(0, "#8f2a06"), (0.3, "#d9520e"), (0.5, "#f28a17"), (0.68, "#f9b233"), (0.85, "#fde08a"), (1, "#fff6d8")],
                 emissive=True, atmosphere=GOLD),
}


class _PlanetTexture:
    def __init__(self, kind, seed, tex_w=1024, tex_h=512):
        style = PLANET_STYLES[kind]
        rng = np.random.default_rng(seed)
        height = fractal_noise(tex_w, tex_h, rng, octaves=7, base=3, stretch=style.get("stretch", 1.0))
        if style.get("stretch", 1.0) > 1:
            # bands: mostly latitude, warped by noise
            lat = np.linspace(0, 1, tex_h, dtype=np.float32)[:, None]
            bands = 0.5 + 0.5 * np.sin(lat * rng.uniform(18, 30) + height * 6)
            height = 0.65 * bands + 0.35 * height
        height = (height - height.min()) / (np.ptp(height) + 1e-6)
        rgb = ramp(height, style["stops"])
        if style.get("craters"):
            yy, xx = np.mgrid[0:tex_h, 0:tex_w].astype(np.float32)
            for _ in range(70):
                cx, cy = rng.random() * tex_w, rng.random() * tex_h
                r = rng.random() ** 2 * 40 + 4
                d = np.sqrt(np.minimum(np.abs(xx - cx), tex_w - np.abs(xx - cx)) ** 2 + (yy - cy) ** 2) / r
                rim = np.exp(-((d - 1) ** 2) * 40) * 0.25
                bowl = np.where(d < 1, -0.18 * (1 - d ** 2), 0)
                rgb *= (1 + rim + bowl)[..., None]
        if style.get("clouds"):
            cl = fractal_noise(tex_w, tex_h, rng, octaves=6, base=5)
            cl = np.clip((cl - 0.55) * 3.5, 0, 1)[..., None]
            rgb = rgb * (1 - cl * 0.85) + cl * 0.95
        self.emissive = np.zeros((tex_h, tex_w), np.float32)
        if "emissive_below" in style:
            self.emissive = np.clip((style["emissive_below"] - height) / style["emissive_below"], 0, 1)
        if style.get("emissive"):
            self.emissive[:] = 1.0
        self.rgb = np.clip(rgb, 0, 1).astype(np.float32)
        self.h, self.w = tex_h, tex_w


@lru_cache(maxsize=24)
def _planet_texture(kind, seed):
    return _PlanetTexture(kind, seed)


@lru_cache(maxsize=64)
def _sphere_grid(d):
    """Per-pixel sphere geometry for a disc of diameter d: normals, latitude, longitude, edge alpha."""
    r = d / 2
    ys, xs = np.mgrid[0:d, 0:d].astype(np.float32)
    nx = (xs + 0.5 - r) / r
    ny = (ys + 0.5 - r) / r
    rr = nx ** 2 + ny ** 2
    inside = rr <= 1.0
    nz = np.sqrt(np.clip(1 - rr, 0, 1))
    lat = np.arcsin(np.clip(ny, -1, 1))
    lon = np.arctan2(nx, np.maximum(nz, 1e-4))
    edge = np.clip((1 - np.sqrt(rr)) * r, 0, 1)  # 1px anti-aliased rim
    return nx, ny, nz, lat, lon, edge * inside


def planet(f, kind, x, y, radius, rotation=0.0, light=(-0.7, -0.25, 0.65), seed_key=None,
           atmosphere=True, night_lights=0.0, brightness=1.0, tint=None, alpha=1.0):
    """A shaded, spinning procedural planet. rotation is in turns (1.0 = full spin).
    Each scene and video gets a unique surface unless the same seed_key is passed."""
    style = PLANET_STYLES[kind]
    tex = _planet_texture(kind, stable_seed(f.seed, seed_key or (f.scene_id, kind)))
    radius = max(radius, 2)
    d = int(min(radius * 2, 1400))  # render big planets at a capped size and scale up
    if d < 200:
        d = max(8, d // 4 * 4)  # small bodies share cached sphere grids
    nx, ny, nz, lat, lon, edge = _sphere_grid(d)
    u = ((lon / (2 * np.pi) + 0.5 + rotation) % 1.0) * (tex.w - 1)
    v = (lat / np.pi + 0.5) * (tex.h - 1)
    ui, vi = u.astype(np.int32), v.astype(np.int32)
    rgb = tex.rgb[vi, ui]
    emis = tex.emissive[vi, ui]
    if style.get("emissive"):
        limb = 0.42 + 0.58 * nz ** 0.55  # stars darken towards the edge
        shade = limb
    else:
        L = np.array(light, np.float32)
        L /= np.linalg.norm(L)
        lambert = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
        shade = 0.03 + 0.97 * lambert ** 0.9
        if night_lights > 0:
            dark = np.clip(1 - lambert * 4, 0, 1)
            emis = np.maximum(emis, dark * night_lights * (rgb[..., 1] > 0.3) * (rgb[..., 2] < 0.5))
    out = rgb * shade[..., None] * brightness
    if tint is not None:
        out = out * np.array(_rgb(tint), np.float32)
    out = out + emis[..., None] * np.array([1.0, 0.55, 0.2], np.float32)
    rgba = np.empty((d, d, 4), np.uint8)
    a = edge * alpha
    rgba[..., :3] = (np.clip(out, 0, 1) * a[..., None] * 255).astype(np.uint8)  # premultiplied
    rgba[..., 3] = (a * 255).astype(np.uint8)
    img = skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)

    atm = style.get("atmosphere") if atmosphere else None
    if atm:
        halo(f, x, y, radius, radius * 1.18, atm, 0.45 * alpha)
    f.c.drawImageRect(img, skia.Rect.MakeXYWH(x - radius, y - radius, radius * 2, radius * 2),
                      skia.SamplingOptions(skia.FilterMode.kLinear))
    if atm:
        # thin rim of atmosphere hugging the edge
        rim = skia.GradientShader.MakeRadial(skia.Point(x, y), radius,
                                            [col(atm, 0), col(atm, 0), col(atm, 0.45 * alpha)], [0, 0.9, 1])
        f.c.drawCircle(x, y, radius, skia.Paint(AntiAlias=True, Shader=rim, BlendMode=skia.BlendMode.kPlus))


def soft_light(f, x, y, r, color, a=1.0, add=True):
    """A gaussian-looking blob of light made from a radial gradient (much faster than blurring)."""
    if a <= 0 or r <= 0:
        return
    stops = [0, 0.2, 0.45, 0.7, 1]
    falloff = [1, 0.62, 0.25, 0.07, 0]
    shader = skia.GradientShader.MakeRadial(skia.Point(x, y), r, [col(color, a * k) for k in falloff], stops)
    p = skia.Paint(AntiAlias=True, Shader=shader)
    if add:
        p.setBlendMode(skia.BlendMode.kPlus)
    f.c.drawCircle(x, y, r, p)


def halo(f, x, y, inner, outer, color, a=1.0):
    """A glow that starts at radius `inner` and fades out by `outer`, e.g. an atmosphere."""
    k = inner / outer
    shader = skia.GradientShader.MakeRadial(skia.Point(x, y), outer,
                                           [col(color, 0), col(color, a), col(color, a * 0.3), col(color, 0)],
                                           [k * 0.98, k, k + (1 - k) * 0.35, 1])
    f.c.drawCircle(x, y, outer, skia.Paint(AntiAlias=True, Shader=shader, BlendMode=skia.BlendMode.kPlus))


def ring(f, x, y, r, width, color, a=1.0):
    """A soft-edged glowing ring of radius r."""
    outer = r + width
    if outer <= 0:
        return
    k_in = max(r - width, 0) / outer
    k_mid = r / outer
    shader = skia.GradientShader.MakeRadial(skia.Point(x, y), outer,
                                           [col(color, 0), col(color, a), col(color, 0)], [k_in, k_mid, 1])
    f.c.drawCircle(x, y, outer, skia.Paint(AntiAlias=True, Shader=shader, BlendMode=skia.BlendMode.kPlus))


def sun(f, x, y, radius, intensity=1.0, rotation=None):
    """A glowing, churning star. intensity 0 makes it vanish."""
    if intensity <= 0.001 or radius < 0.5:
        return
    for k, (scale, a) in enumerate([(5.0, 0.22), (2.6, 0.35), (1.6, 0.5)]):
        pulse = 1 + 0.02 * math.sin(f.t * (1.3 + k) + k)
        soft_light(f, x, y, radius * scale * pulse, GOLD, a * intensity)
    planet(f, "star", x, y, radius, rotation=f.t * 0.01 if rotation is None else rotation,
           atmosphere=False, brightness=0.92, alpha=clamp(intensity))
    halo(f, x, y, radius * 0.97, radius * 1.25, "#fff4d6", 0.55 * intensity)


# ---------------------------------------------------------------- effects

def glow(f, x, y, r, color=CYAN, a=1.0):
    """A soft light source."""
    soft_light(f, x, y, r * 3, color, 0.35 * a)
    soft_light(f, x, y, r, color, 0.9 * a)
    soft_light(f, x, y, r * 0.4, "#ffffff", a)


def shockwave(f, x, y, at, speed=900, life=2.0, color=CYAN, width=18):
    """An expanding ring that starts at `at` (seconds or word)."""
    s = f.since(at)
    if not 0 <= s <= life:
        return
    r = speed * s
    a = (1 - s / life) ** 1.5
    ring(f, x, y, r, width * 3, color, a * 0.6)
    ring(f, x, y, r, width * 0.5, "#ffffff", a * 0.9)


def particles(f, x, y, at, n=220, speed=(120, 700), life=(0.8, 2.6), size=(1.5, 5), color=GOLD,
              gravity=(0, 0), spread=(0, 360), key="particles", drag=0.6):
    """A burst of glowing debris from (x, y) starting at `at`. Positions are computed exactly for
    time t, so the burst looks the same however it's rendered."""
    s = f.since(at)
    if s < 0:
        return
    rng = f.rng(key)
    ang = np.radians(spread[0] + rng.random(n) * (spread[1] - spread[0]))
    spd = speed[0] + rng.random(n) ** 1.5 * (speed[1] - speed[0])
    lf = life[0] + rng.random(n) * (life[1] - life[0])
    sz = size[0] + rng.random(n) * (size[1] - size[0])
    alive = s < lf
    if not alive.any():
        return
    # motion with drag: distance = v * (1 - e^(-k t)) / k
    dist = spd * (1 - np.exp(-drag * s)) / drag
    px = x + np.cos(ang) * dist + 0.5 * gravity[0] * s * s
    py = y + np.sin(ang) * dist + 0.5 * gravity[1] * s * s
    fade_a = np.clip(1 - s / lf, 0, 1) ** 1.2
    px, py, sz, fade_a = px[alive], py[alive], sz[alive], fade_a[alive]
    with bloom(f, sigma=size[1] * 2.5, strength=1.0) as g:
        dots(g, px, py, sz * 1.6, fade_a, color, add=True)
    dots(f, px, py, sz * 0.9, fade_a * 0.8, color, add=True)
    dots(f, px, py, sz * 0.45, fade_a, "#ffffff", add=True)


def trail(f, points, color=CYAN, width=4, a=1.0):
    """A glowing trail through a list of (x, y) points, fading towards the start."""
    n = len(points)
    for i in range(1, n):
        k = i / n
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        f.c.drawLine(x0, y0, x1, y1, paint(color, a * k * 0.25, stroke=width * 3 * (0.3 + 0.7 * k), add=True))
        f.c.drawLine(x0, y0, x1, y1, paint(color, a * k * 0.9, stroke=width * (0.3 + 0.7 * k), add=True))


def orbit(f, cx, cy, rx, ry=None, color=DIM, a=0.6, width=2, dashed=True, progress=1.0, tilt=0.0):
    ry = rx if ry is None else ry
    path = skia.Path()
    path.addOval(skia.Rect.MakeLTRB(cx - rx, cy - ry, cx + rx, cy + ry))
    p = paint(color, a, stroke=width)
    if dashed:
        p.setPathEffect(skia.DashPathEffect.Make([14, 12], f.t * -20))
    f.c.save()
    if tilt:
        f.c.rotate(tilt, cx, cy)
    draw_partial(f, path, progress, p)
    f.c.restore()


def orbit_point(cx, cy, rx, ry, angle_turns):
    a = angle_turns * 2 * math.pi
    return cx + math.cos(a) * rx, cy + math.sin(a) * ry


# ---------------------------------------------------------------- lines, whiteboard and text

def draw_partial(f, path, progress, p):
    """Draw the first `progress` (0..1) of a path, as if a pen is drawing it."""
    progress = clamp(progress)
    if progress <= 0:
        return
    if progress >= 1:
        f.c.drawPath(path, p)
        return
    measure = skia.PathMeasure(path, False)
    while True:
        length = measure.getLength()
        seg = skia.Path()
        measure.getSegment(0, length * progress, seg, True)
        f.c.drawPath(seg, p)
        if not measure.nextContour():
            break


def chalk(color=INK, width=5, a=0.92, roughness=1.6, seed=0):
    """A hand-drawn chalk stroke paint. Different seeds give different wobbles."""
    p = paint(color, a, stroke=width)
    p.setPathEffect(skia.DiscretePathEffect.Make(6, roughness, seed))
    return p


def line_path(points, smooth=False):
    path = skia.Path()
    path.moveTo(*points[0])
    if smooth and len(points) > 2:
        for i in range(1, len(points) - 1):
            mx = (points[i][0] + points[i + 1][0]) / 2
            my = (points[i][1] + points[i + 1][1]) / 2
            path.quadTo(points[i][0], points[i][1], mx, my)
        path.lineTo(*points[-1])
    else:
        for pt in points[1:]:
            path.lineTo(*pt)
    return path


def arrow(f, x0, y0, x1, y1, progress=1.0, p=None, head=22):
    """A line with an arrowhead that's drawn on as progress goes 0 to 1."""
    p = p or chalk()
    progress = clamp(progress)
    if progress <= 0:
        return
    ex, ey = lerp(x0, x1, progress), lerp(y0, y1, progress)
    f.c.drawLine(x0, y0, ex, ey, p)
    if progress > 0.85:
        ang = math.atan2(y1 - y0, x1 - x0)
        k = (progress - 0.85) / 0.15
        for side in (-1, 1):
            a = ang + math.pi + side * 0.45
            f.c.drawLine(ex, ey, ex + math.cos(a) * head * k, ey + math.sin(a) * head * k, p)


@lru_cache(maxsize=16)
def _typeface(name):
    return skia.Typeface.MakeFromFile(str(ASSETS / "fonts" / f"{name}.ttf"))


def font(size, weight="bold"):
    name = {"bold": "SpaceGrotesk-700", "medium": "SpaceGrotesk-500",
            "body": "Inter-400", "semibold": "Inter-600",
            "hand": "Caveat-700", "hand-light": "Caveat-500"}.get(weight, weight)
    fnt = skia.Font(_typeface(name), size)
    fnt.setSubpixel(True)
    fnt.setEdging(skia.Font.Edging.kSubpixelAntiAlias)
    return fnt


def text(f, s, x, y, size=64, color=INK, a=1.0, align="center", weight="bold", reveal=1.0,
         glow_color=None, stroke=None):
    """Draw text. reveal 0..1 writes it on left to right; align is left/center/right."""
    if a <= 0 or reveal <= 0:
        return
    fnt = font(size, weight)
    width = fnt.measureText(s)
    left = x - width / 2 if align == "center" else x - width if align == "right" else x
    c = f.c
    c.save()
    if reveal < 1:
        c.clipRect(skia.Rect.MakeLTRB(left - 4, y - size * 1.2, left + width * reveal + 2, y + size * 0.5))
    if glow_color:
        c.drawString(s, left, y, fnt, paint(glow_color, a * 0.7, blur=size * 0.18, add=True))
    if stroke:
        c.drawString(s, left, y, fnt, paint("#000000", a * 0.85, stroke=stroke, cap_round=False))
    c.drawString(s, left, y, fnt, paint(color, a))
    c.restore()
    return width


def slam_text(f, s, x, y, at, size=150, color=INK, glow_color=RED, hold=None, snap=True, weight="bold"):
    """Edit-style text that SLAMS onto the screen: starts huge, crunches down with a jolt and a glow.
    With snap=True it lands on the first beat at or after `at`, so it hits with the music."""
    start = f.next_beat(at) if snap and f.beats else f.time(at)
    s_t = f.t - start
    width = font(size, weight).measureText(s)
    if width > W - 200:  # long punchlines shrink to fit the screen
        size = size * (W - 200) / width
    if s_t < 0 or (hold is not None and s_t > hold + 0.25):
        return
    k = clamp(s_t / 0.16)
    scale = lerp(1.9, 1.0, ease_out(k)) * (1 + 0.04 * math.exp(-max(s_t - 0.16, 0) * 14))
    a = clamp(s_t / 0.06) * (clamp((hold + 0.25 - s_t) / 0.25) if hold is not None else 1)
    jolt = 10 * math.exp(-s_t * 18) * math.sin(s_t * 90)
    f.c.save()
    f.c.translate(x + jolt, y)
    f.c.scale(scale, scale)
    f.c.rotate(-2.5 * math.exp(-s_t * 10))
    text(f, s, 0, size * 0.35, size=size, color=color, a=a, weight=weight, glow_color=glow_color, stroke=size * 0.1)
    f.c.restore()


def handwrite(f, s, x, y, at, dur=1.0, size=64, color=INK, align="center", weight="hand"):
    """Text that writes itself onto the board starting at `at`."""
    return text(f, s, x, y, size=size, color=color, align=align, weight=weight,
                reveal=f.prog(at, dur, ease=lambda v: clamp(v)), a=0.95)


def counter(f, x, y, value, size=96, color=INK, fmt="{:,.0f}", suffix="", weight="bold", glow_color=None):
    return text(f, fmt.format(value) + suffix, x, y, size=size, color=color, weight=weight, glow_color=glow_color)


def label(f, s, x, y, tx, ty, at, size=36, color=INK, line_color=DIM):
    """A callout: a leader line from a point (x, y) to text at (tx, ty), drawn in at `at`."""
    pr = f.prog(at, 0.6)
    if pr <= 0:
        return
    f.c.drawCircle(x, y, 6 * ease_back(pr), paint(color, 1))
    mx = lerp(x, tx, min(pr * 1.6, 1))
    my = lerp(y, ty, min(pr * 1.6, 1))
    f.c.drawLine(x, y, mx, my, paint(line_color, 0.9, stroke=2.5))
    text(f, s, tx + (12 if tx >= x else -12), ty + size * 0.35, size=size, color=color,
         align="left" if tx >= x else "right", weight="semibold", reveal=clamp((pr - 0.5) * 2))


def caption_card(f, title, sub, at, x=W / 2, y=H - 150, hold=None, color=CYAN):
    """A lower-third fact card: a big number or phrase, with a small explanation under it."""
    s = f.since(at)
    if s < 0 or (hold is not None and s > hold + 0.5):
        return
    a = clamp(s / 0.35) * (clamp((hold + 0.5 - s) / 0.5) if hold is not None else 1)
    rise = (1 - ease_out(s / 0.5)) * 30
    fnt = font(72, "bold")
    w = max(fnt.measureText(title), font(34, "body").measureText(sub)) + 90
    rect = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x - w / 2, y - 95 + rise, w, 150), 22, 22)
    f.c.drawRRect(rect, paint("#000000", 0.55 * a))
    f.c.drawRRect(rect, paint(color, 0.6 * a, stroke=2))
    text(f, title, x, y - 10 + rise, size=72, color=INK, a=a, glow_color=color)
    text(f, sub, x, y + 38 + rise, size=34, color=DIM, a=a, weight="body")


# ---------------------------------------------------------------- charts

def line_chart(f, rect, ys, progress, color=CYAN, y_range=None, x_labels=(), y_labels=(),
               title=None, zero_line=None, chalky=False):
    """A line chart drawn on as progress goes 0..1. rect = (x, y, w, h). ys are data values.
    x_labels / y_labels are lists of (fraction 0..1, text)."""
    x, y, w, h = rect
    lo, hi = y_range or (min(ys), max(ys))
    axis = chalk(DIM, 3, 0.8, roughness=1.0) if chalky else paint(DIM, 0.8, stroke=2.5)
    f.c.drawLine(x, y + h, x + w, y + h, axis)
    f.c.drawLine(x, y, x, y + h, axis)
    for frac, s in x_labels:
        text(f, s, x + w * frac, y + h + 46, size=30, color=DIM, weight="body")
    for frac, s in y_labels:
        yy = y + h - h * frac
        f.c.drawLine(x - 8, yy, x, yy, axis)
        text(f, s, x - 18, yy + 10, size=30, color=DIM, align="right", weight="body")
    if zero_line is not None:
        yy = y + h - h * (zero_line - lo) / (hi - lo)
        zp = paint(DIM, 0.5, stroke=1.5)
        zp.setPathEffect(skia.DashPathEffect.Make([10, 10], 0))
        f.c.drawLine(x, yy, x + w, yy, zp)
    if title:
        text(f, title, x, y - 30, size=38, color=INK, align="left", weight="semibold")
    pts = [(x + w * i / (len(ys) - 1), y + h - h * (v - lo) / (hi - lo)) for i, v in enumerate(ys)]
    path = line_path(pts, smooth=True)
    line = chalk(color, 6, roughness=1.2) if chalky else paint(color, 1, stroke=6)
    draw_partial(f, path, progress, paint(color, 0.4, stroke=18, blur=8, add=True))
    draw_partial(f, path, progress, line)
    # glowing pen tip
    if 0 < progress < 1:
        m = skia.PathMeasure(path, False)
        pos = m.getPosTan(m.getLength() * progress)
        if pos:
            pt = pos[0]
            glow(f, pt.x(), pt.y(), 10, color)
