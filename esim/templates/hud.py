"""Data and HUD scenes: leaderboards, races, pictograms, spectra and dashboards."""

import functools
import math
from functools import lru_cache

import numpy as np
import skia

from esim.templates import BODY_KINDS, Sfx, accent, body, pick, rand, shot_camera, template, when
from esim.engine import *  # noqa: F401,F403
from esim.engine import stable_seed


# ================================================================ shared HUD pieces

def _late(f, at, back=3.0, lo=0.62):
    """Time of a payoff beat: the word if given, else `back` s before the end (so default sfx can use
    Sfx(kind, "end", offset=-back)), but never earlier than `lo` of the way through a short scene."""
    return f.time(at) if at is not None else max(f.dur - back, f.dur * lo)


FIT, FIT_CY = 0.9, 480


def _fit_begin(f):
    """HUD content is drawn 10% smaller about (960, 480): run_shot's ambient camera zooms every shot up to ~1.15x,
    so this keeps the screen furniture off the cropped edges and everything above the caption zone, while the
    background (drawn before this) still bleeds to the edges. Close with f.c.restore()."""
    f.c.save()
    f.c.translate(W / 2, FIT_CY)
    f.c.scale(FIT, FIT)
    f.c.translate(-W / 2, -FIT_CY)


def _hud(fn):
    """Restore the canvas after a HUD template (closes _fit_begin)."""
    @functools.wraps(fn)
    def wrapper(f, p):
        n = f.c.getSaveCount()
        try:
            fn(f, p)
        finally:
            f.c.restoreToCount(n)
    return wrapper


def _decimals(v):
    v = abs(float(v))
    if v >= 100 or v == int(v):
        return 0
    return 1 if v >= 10 else 2


def _fmt(v, ref=None):
    """Commas, with the number of decimals the final value `ref` needs (so counters don't jitter)."""
    return f"{v:,.{_decimals(v if ref is None else ref)}f}"


def _short(v):
    av = abs(v)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if av >= div * 0.9995:
            x = v / div
            return (f"{x:.0f}" if abs(x) >= 100 else f"{x:.1f}".rstrip("0").rstrip(".")) + suf
    if av >= 10 or v == int(v):
        return f"{v:.0f}"
    return f"{v:.2g}"


def _sig(v, digits=2):
    """Round to `digits` significant figures and add commas: 440871 -> '440,000'."""
    if v <= 0:
        return "0"
    e = math.floor(math.log10(v)) - digits + 1
    r = round(v / 10 ** e) * 10 ** e
    return f"{r:,.0f}" if r >= 10 else f"{r:.{max(-e, 0)}f}"


_TIME_UNITS = [(3.156e16, "billion years"), (3.156e13, "million years"), (3.156e7, "years"), (86400, "days"),
               (3600, "hours"), (60, "minutes"), (1, "seconds"), (1e-3, "milliseconds"), (1e-6, "microseconds")]


def _human_time(s):
    for u, name in _TIME_UNITS:
        if s >= u * 0.9999 or u == 1e-6:
            v = s / u
            txt = f"{v:,.0f}" if v >= 100 else f"{v:.1f}".rstrip("0").rstrip(".")
            if txt == "1" and " " not in name:
                name = name[:-1]
            return f"{txt} {name}"


def _unit(u):
    if not u:
        return ""
    return u if u[0] in " %°" else " " + u


@lru_cache(maxsize=8)
def _haze_img(seed):
    rng = np.random.default_rng(seed)
    n = fractal_noise(480, 272, rng, octaves=5, base=5)
    n = (n - n.min()) / (np.ptp(n) + 1e-6)
    a = (n ** 2.2 * 255).astype(np.uint8)
    rgba = np.empty((272, 480, 4), np.uint8)
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = rgba[..., 3] = a  # premultiplied white
    return skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)


def _haze(f, color, a=0.1):
    """A drifting cloudy texture tinted with the accent: gives the dark HUD background depth."""
    img = _haze_img(stable_seed(f.seed, f.scene_id, "haze"))
    pt = skia.Paint(Alphaf=clamp(a), BlendMode=skia.BlendMode.kPlus,
                    ColorFilter=skia.ColorFilters.Blend(col(color), skia.BlendMode.kModulate))
    dx, dy = 40 * math.sin(f.t * 0.11), 25 * math.cos(f.t * 0.09)
    f.c.drawImageRect(img, skia.Rect.MakeXYWH(-90 + dx, -60 + dy, W + 180, H + 120),
                      skia.SamplingOptions(skia.FilterMode.kLinear), pt)


def _hex_dots(f, color):
    sp = 46
    ys, xs = np.mgrid[0:H // 40 + 2, 0:W // sp + 2].astype(np.float32)
    xs = xs * sp + (ys % 2) * sp / 2
    ys = ys * 40
    d = np.hypot(xs - W / 2, ys - H / 2)
    front = (f.t * 260) % 1500
    a = 0.06 + 0.3 * np.exp(-((d - front) / 80) ** 2) + 0.12 * f.beat_pulse() * np.exp(-d / 500)
    dots(f, xs.ravel(), ys.ravel(), 1.7, a.ravel(), color)


def _hud_bg(f, p, c_, key="hbg"):
    """Dark HUD backdrop: gradient, stars or nebula, tinted haze, a grid or hex lattice and a soft centre light."""
    style = p("background") or pick(f, key, ["grid", "hex", "space", "nebula"])
    gradient_bg(f, "#060a17", "#010207")
    if style == "nebula":
        nebula_glow(f, alpha=0.38)
    starfield(f, n=320 if style in ("space", "nebula") else 150, drift=(-5, 0),
              alpha=0.75 if style in ("space", "nebula") else 0.35)
    _haze(f, c_, 0.11 if style != "nebula" else 0.06)
    if style == "grid":
        thin, bold = paint(c_, 0.045, stroke=1), paint(c_, 0.10, stroke=1.3)
        for i, x in enumerate(range(0, W + 1, 60)):
            f.c.drawLine(x, 0, x, H, bold if i % 4 == 0 else thin)
        for i, y in enumerate(range(0, H + 1, 60)):
            f.c.drawLine(0, y, W, y, bold if i % 4 == 0 else thin)
    elif style == "hex":
        _hex_dots(f, c_)
    soft_light(f, W * 0.5, H * 0.47, 1050, c_, 0.05 + 0.04 * f.beat_pulse())
    return style


def _chrome(f, c_, tag, title=None, live=True, readouts=()):
    """Screen furniture: corner brackets, a tag + title top left, LIVE + timecode top right, a slow scanline.
    readouts: [(text, color)] stacked under the timecode."""
    m, L = 44, 64
    pp = paint(c_, 0.75, stroke=3, cap_round=False)
    for x, y, sx, sy in ((m, m, 1, 1), (W - m, m, -1, 1), (m, 884, 1, -1), (W - m, 884, -1, -1)):
        f.c.drawLine(x, y, x + sx * L, y, pp)
        f.c.drawLine(x, y, x, y + sy * L, pp)
    text(f, tag.upper(), 98, 100, size=33, color=c_, align="left", weight="semibold", a=0.95)
    tw = font(33, "semibold").measureText(tag.upper())
    f.c.drawLine(110 + tw, 90, 110 + tw + 120 * f.prog(0, 0.8), 90, paint(c_, 0.5, stroke=2))
    if title:
        size = 54
        w = font(size, "bold").measureText(title)
        if w > 1060:
            size = max(36, size * 1060 / w)
        text(f, title, 98, 162, size=size, align="left", weight="bold", reveal=clamp(0.55 + f.t / 0.5),
             stroke=5)
    if live:
        blink = 1.0 if (f.t * 1.6) % 1 < 0.6 else 0.25
        f.c.drawCircle(W - 412, 90, 9, paint(RED, blink))
        soft_light(f, W - 412, 90, 26, RED, 0.5 * blink)
        text(f, "LIVE", W - 394, 101, size=33, color=INK, align="left", weight="semibold")
        text(f, f"T+{int(f.t // 60):02d}:{f.t % 60:05.2f}", W - 98, 101, size=33, color=DIM, align="right",
             weight="medium")
    for i, (s, colr) in enumerate(readouts):
        text(f, s, W - 98, 148 + i * 42, size=33, color=colr, align="right", weight="semibold")
    sy = (f.t * 120) % 1000 - 40
    sh = skia.GradientShader.MakeLinear([skia.Point(0, sy - 40), skia.Point(0, sy + 4)],
                                        [col(c_, 0), col(c_, 0.05)])
    f.c.drawRect(skia.Rect.MakeLTRB(0, sy - 40, W, sy + 4), skia.Paint(Shader=sh, BlendMode=skia.BlendMode.kPlus))


def _panel(f, x, y, w, h, color, a=1.0, fill=0.72, radius=16, glow_a=0.0, corner=22):
    """A glass HUD panel with a bright border, corner accents and a top sheen."""
    if a <= 0.003:
        return
    rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), radius, radius)
    sh = skia.GradientShader.MakeLinear([skia.Point(x, y), skia.Point(x, y + h)],
                                        [col(mix("#15214a", color, 0.22), fill * a), col(mix("#03060f", color, 0.06), fill * a)])
    f.c.drawRRect(rr, skia.Paint(AntiAlias=True, Shader=sh))
    if glow_a > 0:
        f.c.drawRRect(rr, paint(color, clamp(glow_a * a), stroke=10, blur=14, add=True))
    f.c.drawRRect(rr, paint(color, 0.42 * a, stroke=2))
    cp = paint(color, 0.95 * a, stroke=3.5, cap_round=False)
    k = corner
    for cx, cy, sx, sy in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        f.c.drawLine(cx, cy + sy * radius * 0.4, cx, cy + sy * (k + radius * 0.4), cp)
        f.c.drawLine(cx + sx * radius * 0.4, cy, cx + sx * (k + radius * 0.4), cy, cp)
    f.c.drawLine(x + radius, y + 2, x + w * 0.5, y + 2, paint("#ffffff", 0.16 * a, stroke=1.5))


def _chip(f, s, x, y, color, a=1.0, align="right", filled=False):
    """A small status chip like [ WARNING ]."""
    if a <= 0:
        return
    fnt = font(33, "semibold")
    w = fnt.measureText(s) + 30
    left = x - w if align == "right" else x - w / 2 if align == "center" else x
    rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(left, y - 32, w, 45), 8, 8)
    f.c.drawRRect(rr, paint(color, (0.85 if filled else 0.14) * a))
    f.c.drawRRect(rr, paint(color, 0.9 * a, stroke=2))
    text(f, s, left + w / 2, y + 1, size=33, color="#05070d" if filled else color, a=a, weight="semibold")


def _tri(f, x, y, s, color, a=1.0, up=True):
    path = skia.Path()
    d = -1 if up else 1
    path.moveTo(x, y + d * s)
    path.lineTo(x - s * 0.9, y - d * s * 0.6)
    path.lineTo(x + s * 0.9, y - d * s * 0.6)
    path.close()
    f.c.drawPath(path, paint(color, a))


def _hglow(f, x, y, w, h, color, a):
    """An elongated soft glow (a soft_light squashed into an ellipse)."""
    if a <= 0:
        return
    f.c.save()
    f.c.translate(x, y)
    f.c.scale(w / 300, h / 300)
    soft_light(f, 0, 0, 300, color, a)
    f.c.restore()


def _crown(f, x, y, s, a=1.0, glow_a=0.6):
    pts = [(-1, 0.55), (1, 0.55), (1.08, -0.55), (0.52, -0.05), (0, -0.8), (-0.52, -0.05), (-1.08, -0.55)]
    path = skia.Path()
    path.moveTo(x + pts[0][0] * s, y + pts[0][1] * s)
    for px, py in pts[1:]:
        path.lineTo(x + px * s, y + py * s)
    path.close()
    soft_light(f, x, y, s * 3.2, GOLD, glow_a * a)
    sh = skia.GradientShader.MakeLinear([skia.Point(x, y - s), skia.Point(x, y + s * 0.6)],
                                        [col("#fff2b8", a), col(GOLD, a), col("#9a5a10", a)], [0, 0.5, 1])
    f.c.drawPath(path, skia.Paint(AntiAlias=True, Shader=sh))
    f.c.drawPath(path, paint("#fff6d8", 0.8 * a, stroke=max(1.5, s * 0.07)))
    f.c.drawRect(skia.Rect.MakeLTRB(x - s, y + s * 0.38, x + s, y + s * 0.62), paint("#9a5a10", 0.9 * a))
    for px, py in ((1.08, -0.55), (0, -0.8), (-1.08, -0.55)):
        f.c.drawCircle(x + px * s, y + py * s, s * 0.14, paint("#ffffff", a))
    f.c.drawCircle(x, y + s * 0.15, s * 0.13, paint(RED, a))


# ---------------------------------------------------------------- small vector icons for things that aren't planets

def _guess_icon(name):
    n = (name or "").lower()
    table = ((("bullet",), "bullet"), (("jet", "plane", "sr-71", "concorde", "fighter", "aircraft", "airliner"), "jet"),
             (("iss", "space station", "satellite", "hubble"), "iss"),
             (("rocket", "saturn v", "starship", "falcon", "apollo"), "rocket"),
             (("probe", "voyager", "parker", "new horizons", "juno", "pioneer"), "probe"),
             (("light", "photon", "laser", "radio wave"), "light"), (("sound", "mach"), "sound"))
    for keys, kind in table:
        if any(k in n for k in keys):
            return kind
    key = n.replace(" ", "_").replace("'s", "")
    for k in sorted(BODY_KINDS, key=len, reverse=True):
        if k in key and k not in ("gas", "ice", "star", "rocky"):
            return k
    return "dot"


def _path(pts, x, y, r):
    path = skia.Path()
    path.moveTo(x + pts[0][0] * r, y + pts[0][1] * r)
    for px, py in pts[1:]:
        path.lineTo(x + px * r, y + py * r)
    path.close()
    return path


def _vshade(y0, y1, colors, pos=None, a=1.0):
    sh = skia.GradientShader.MakeLinear([skia.Point(0, y0), skia.Point(0, y1)], [col(c, a) for c in colors], pos)
    return skia.Paint(AntiAlias=True, Shader=sh)


def _glyph(f, kind, x, y, r, color=CYAN, a=1.0):
    """Draw a small icon facing right, about 2r long: bullet, jet, iss, rocket, probe, light, sound, dot,
    or any body kind (drawn as a planet)."""
    c = f.c
    if a <= 0.01:
        return
    if kind in BODY_KINDS:
        if kind in ("sun", "red_giant", "white_dwarf", "neutron_star", "star"):
            soft_light(f, x, y, r * 2.2, GOLD if kind in ("sun", "star") else BODY_KINDS[kind][1] or GOLD, 0.5 * a)
        body(f, kind, x, y, r * 0.82, light=(-0.5, -0.45, 0.75), alpha=a)
        return
    if kind == "bullet":
        path = skia.Path()
        path.moveTo(x - r, y - 0.3 * r)
        path.lineTo(x + 0.1 * r, y - 0.3 * r)
        path.cubicTo(x + 0.6 * r, y - 0.3 * r, x + 0.95 * r, y - 0.1 * r, x + r, y)
        path.cubicTo(x + 0.95 * r, y + 0.1 * r, x + 0.6 * r, y + 0.3 * r, x + 0.1 * r, y + 0.3 * r)
        path.lineTo(x - r, y + 0.3 * r)
        path.close()
        c.drawPath(path, _vshade(y - 0.3 * r, y + 0.3 * r, ["#fff0c4", "#d9a24a", "#6a4214"], [0, 0.45, 1], a))
        c.drawLine(x + 0.1 * r, y - 0.3 * r, x + 0.1 * r, y + 0.3 * r, paint("#4a2c0a", 0.8 * a, stroke=r * 0.06))
        c.drawLine(x - 0.9 * r, y - 0.15 * r, x + 0.45 * r, y - 0.15 * r, paint("#ffffff", 0.55 * a, stroke=r * 0.06))
    elif kind == "jet":
        top = [(1.0, 0), (0.62, -0.07), (0.15, -0.11), (-0.25, -0.72), (-0.45, -0.72), (-0.35, -0.12),
               (-0.78, -0.10), (-0.95, -0.4), (-1.05, -0.4), (-0.98, 0)]
        pts = top + [(px, -py) for px, py in reversed(top[1:-1])]
        soft_light(f, x - 1.05 * r, y, r * 0.7, "#ff9a3d", 0.8 * a)
        c.drawPath(_path(pts, x, y, r), _vshade(y - 0.7 * r, y + 0.7 * r, ["#f4f7ff", "#9aa6c0", "#4a5470"], None, a))
        c.drawOval(skia.Rect.MakeXYWH(x + 0.38 * r, y - 0.06 * r, 0.3 * r, 0.12 * r), paint(CYAN, 0.9 * a))
    elif kind == "iss":
        for sx in (-0.75, -0.45, 0.45, 0.75):
            for sy in (-1, 1):
                rect = skia.Rect.MakeLTRB(x + (sx - 0.12) * r, y + min(sy * 0.14, sy * 0.85) * r,
                                          x + (sx + 0.12) * r, y + max(sy * 0.14, sy * 0.85) * r)
                c.drawRect(rect, _vshade(rect.top(), rect.bottom(), ["#e0b54a", "#7a5a18"], None, a))
                for k in range(1, 4):
                    yy = rect.top() + rect.height() * k / 4
                    c.drawLine(rect.left(), yy, rect.right(), yy, paint("#3a2a08", 0.7 * a, stroke=1))
        c.drawLine(x - r, y, x + r, y, paint("#d8dde8", a, stroke=max(2, r * 0.1)))
        c.drawRect(skia.Rect.MakeLTRB(x - 0.16 * r, y - 0.32 * r, x + 0.16 * r, y + 0.32 * r),
                   _vshade(y - 0.32 * r, y + 0.32 * r, ["#ffffff", "#8a93a8"], None, a))
    elif kind == "rocket":
        flick = 0.85 + 0.15 * math.sin(f.t * 40)
        soft_light(f, x - 1.0 * r, y, r * 0.9 * flick, "#ff9a3d", 0.9 * a)
        c.drawPath(_path([(-0.72, -0.12), (-1.25 * flick, 0), (-0.72, 0.12)], x, y, r), paint("#fff1c0", a))
        c.drawPath(_path([(-0.7, -0.2), (-0.95, -0.5), (-0.45, -0.2)], x, y, r), paint(RED, a))
        c.drawPath(_path([(-0.7, 0.2), (-0.95, 0.5), (-0.45, 0.2)], x, y, r), paint(RED, a))
        path = skia.Path()
        path.moveTo(x - 0.72 * r, y - 0.2 * r)
        path.lineTo(x + 0.5 * r, y - 0.2 * r)
        path.quadTo(x + 0.92 * r, y - 0.12 * r, x + r, y)
        path.quadTo(x + 0.92 * r, y + 0.12 * r, x + 0.5 * r, y + 0.2 * r)
        path.lineTo(x - 0.72 * r, y + 0.2 * r)
        path.close()
        c.drawPath(path, _vshade(y - 0.2 * r, y + 0.2 * r, ["#ffffff", "#c4cad8", "#5a6278"], [0, 0.4, 1], a))
        c.drawCircle(x + 0.25 * r, y, 0.08 * r, paint(CYAN, a))
    elif kind == "probe":
        c.drawOval(skia.Rect.MakeLTRB(x + 0.45 * r, y - 0.75 * r, x + 0.75 * r, y + 0.75 * r),
                   _vshade(y - 0.75 * r, y + 0.75 * r, ["#ffffff", "#d0d4dc", "#6a7080"], None, a))
        c.drawRect(skia.Rect.MakeLTRB(x - 0.4 * r, y - 0.3 * r, x + 0.45 * r, y + 0.3 * r),
                   _vshade(y - 0.3 * r, y + 0.3 * r, ["#ffd88a", "#9a6a20"], None, a))
        for sy in (-1, 1):
            c.drawRect(skia.Rect.MakeLTRB(x - 0.25 * r, y + sy * 0.3 * r, x + 0.05 * r, y + sy * 0.85 * r),
                       paint("#3a5aa8", 0.95 * a))
        c.drawLine(x - 0.4 * r, y, x - r, y, paint("#d8dde8", a, stroke=max(1.5, r * 0.05)))
    elif kind == "light":
        pts = [(x - r * 3.2 + i * r * 0.1, y + r * 0.35 * math.sin(i * 0.9 - f.t * 30) * (i / 32)) for i in range(33)]
        f.c.drawPath(line_path(pts), paint(color, 0.5 * a, stroke=r * 0.18, add=True))
        soft_light(f, x, y, r * 2.4, color, 0.6 * a)
        soft_light(f, x, y, r * 1.0, "#ffffff", 0.95 * a)
        c.drawCircle(x, y, r * 0.28, paint("#ffffff", a))
    elif kind == "sound":
        for k in range(3):
            ph = (f.t * 1.5 + k / 3) % 1
            c.drawArc(skia.Rect.MakeXYWH(x - r * ph, y - r * ph, 2 * r * ph, 2 * r * ph), -50, 100, False,
                      paint(color, a * (1 - ph), stroke=r * 0.12))
        c.drawCircle(x - r * 0.2, y, r * 0.22, paint(color, a))
    else:
        soft_light(f, x, y, r * 1.8, color, 0.5 * a)
        c.drawCircle(x, y, r * 0.55, _vshade(y - r * 0.55, y + r * 0.55, ["#ffffff", color, mix(color, "#000000", 0.6)],
                                             [0, 0.4, 1], a))
        c.drawOval(skia.Rect.MakeLTRB(x - r, y - r * 0.25, x + r, y + r * 0.25), paint(color, 0.7 * a, stroke=2))


# ================================================================ 1. leaderboard

_LB_DEFAULT = [
    {"name": "Mars", "value": 3390, "kind": "mars"},
    {"name": "Earth", "value": 6371, "kind": "earth"},
    {"name": "Neptune", "value": 24622, "kind": "neptune"},
    {"name": "Uranus", "value": 25362, "kind": "uranus"},
    {"name": "Saturn", "value": 58232, "kind": "saturn"},
    {"name": "Jupiter", "value": 69911, "kind": "jupiter"},
    {"name": "The Sun", "value": 696340, "kind": "sun"},
]


def _lb_sfx(p):
    rows = p("rows") or []
    out = [Sfx("whoosh", "start", gain_db=-8)]
    if rows:
        out += [Sfx("pop", r["at"], gain_db=-4) for r in rows[:-1] if r.get("at")]
    else:
        out += [Sfx("tick", 0.4 + 0.5 * i, gain_db=-6) for i in range(5)]
    last = rows[-1].get("at") if rows else None
    base, off = (last, 0.0) if last else ("end", -3.0)
    return out + [Sfx("riser", base, offset=off - 1.2, dur=1.4, gain_db=-4), Sfx("whoosh", base, offset=off + 0.45),
                  Sfx("impact", base, offset=off + 0.9), Sfx("808", base, offset=off + 0.9)]


@template("leaderboard", kind="data", sfx=_lb_sfx)
@_hud
def leaderboard(f, p):
    """A live, broadcast-style leaderboard: ranked glass rows (planet/icon, name, glowing value bar, counting
    number) slide in one by one, each new entry entering at the bottom and climbing past the others as the
    board re-sorts. A gold crown sits on #1. Payoff: the LAST row is the surprise, it hesitates at the bottom,
    then rockets to #1 with a flash and shake, the crown jumps to it and every other bar collapses to show how
    much bigger it is. List rows in the order they're mentioned.
    params: title, rows [{name, value (number), kind (body kind or bullet|jet|iss|rocket|probe|light, optional),
    at (word it appears on)}] (3-7, last = the surprise), unit (e.g. 'km'), slam (payoff text, default 'NEW #1'),
    sort (high = biggest is #1, default; low = smallest is #1, e.g. shortest day), log (true: log-scaled bars),
    color, background (grid|hex|space|nebula)"""
    c_ = accent(f, p, default=["gold", "cyan", "pink", "green", "orange"])
    rows = list(p("rows") or _LB_DEFAULT)
    custom = bool(p("rows"))
    unit = _unit(p("unit", "" if custom else "km"))
    title = p("title", None if custom else "Biggest bodies in the Solar System")
    n = len(rows)
    vals = [float(r.get("value", 1)) for r in rows]
    low = str(p("sort", "high")).lower() in ("low", "asc", "lowest", "smallest")
    pay_default = _late(f, None)
    times = []
    for i, r in enumerate(rows):
        if r.get("at") is not None:
            times.append(f.time(r["at"]))
        elif i == n - 1 and n > 1:
            times.append(pay_default)
        else:
            times.append(lerp(-0.8, max(pay_default - 1.5, 0.5), i / max(n - 2, 1)))
    order = sorted(range(n), key=lambda i: times[i])
    ranks, maxv, delays, durs = [], [], [], []
    for k in range(n):
        s = sorted(order[:k + 1], key=lambda j: vals[j] if low else -vals[j])
        ranks.append({j: idx for idx, j in enumerate(s)})
        maxv.append(max(vals[j] for j in order[:k + 1]))
        last = k == n - 1 and n > 1
        delays.append(0.5 if last else 0.15)
        durs.append(0.75 if last else 0.6)
    surprise = order[-1]
    land = times[surprise] + delays[-1] + durs[-1] * 0.55  # the surprise reaches the top

    def slot(i, t):
        k0 = order.index(i)
        if times[i] > t:
            return None
        pos, prev = float(k0), k0
        for k in range(k0, n):
            tk = times[order[k]]
            if tk > t:
                break
            tgt = ranks[k][i]
            pos += (tgt - prev) * ease_in_out((t - tk - delays[k]) / durs[k])
            prev = tgt
        return pos

    # bar scale follows the biggest value on the board, shrinking everyone when a giant arrives
    m = maxv[0]
    for k in range(1, n):
        tk = times[order[k]]
        m += (maxv[k] - maxv[k - 1]) * ease_in_out((f.t - tk - delays[k] - durs[k] * 0.6) / 0.8)
    use_log = p("log", False)

    def frac(v):
        if use_log:
            return clamp(math.log10(1 + v) / math.log10(1 + max(m, 1e-9)))
        return clamp(v / m) if m else 0

    # leader + when the crown last changed hands
    crown_owner, crown_t = order[0], times[order[0]]
    for k in range(n):
        tk = times[order[k]]
        if tk > f.t:
            break
        lead = min(ranks[k], key=ranks[k].get)
        tc = tk + delays[k] + durs[k] * 0.55
        if lead != crown_owner and f.t >= tc:
            crown_owner, crown_t = lead, tc
    s_land = f.t - land
    shake = 16 * math.exp(-s_land * 3.2) if s_land > 0 else 0
    punch = 0.03 * math.exp(-s_land * 4) if s_land > 0 else 0

    _hud_bg(f, p, c_)
    _fit_begin(f)
    X0, PW = 150, 1620
    top, bottom = 250, 880
    hs = min(118, (bottom - top) / max(n, 1))
    BX, BW = X0 + 660, 640
    _hglow(f, 960, 570, 1100, 420, c_, 0.10 + 0.05 * f.beat_pulse())
    with camera(f, 960 + 22 * math.sin(f.t * 0.23), 560, zoom=1.0 + 0.035 * ease_in_out(f.p) + punch, shake=shake):
        # scale ticks above the bars (labels morph as the scale changes)
        for k in range(5):
            fr = k / 4
            x = BX + BW * fr
            f.c.drawLine(x, top - 8, x, top + hs * n, paint(c_, 0.10, stroke=1.5))
            lab = "0" if k == 0 else _short((10 ** (fr * math.log10(1 + m)) - 1) if use_log else m * fr)
            text(f, lab, x, top - 18, size=33, color=DIM, weight="medium")
        text(f, "RANK", X0 + 10, top - 18, size=33, color=DIM, align="left", weight="semibold")
        text(f, "NAME", X0 + 205, top - 18, size=33, color=DIM, align="left", weight="semibold")
        arrived = sum(1 for tt in times if tt <= f.t)
        for k in range(arrived, n):  # empty slots waiting for their entry
            y = top + k * hs
            hh = hs - 14
            _panel(f, X0, y, PW, hh, "#4a5a86", a=0.9, fill=0.55)
            f.c.drawCircle(X0 + 150, y + hh / 2, hh * 0.28, paint(DIM, 0.5, stroke=2))
            text(f, "?", X0 + 150, y + hh / 2 + 12, size=34, color=DIM, a=0.7)
            text(f, f"#{k + 1}", X0 + 62, y + hh / 2 + 16, size=min(46, hh * 0.45), color=DIM, a=0.6)
            text(f, "AWAITING ENTRY", X0 + 205, y + hh / 2 + 11, size=33, color=DIM, align="left",
                 weight="semibold", a=0.6 + 0.25 * math.sin(f.t * 4 + k))
            f.c.save()
            f.c.clipRect(skia.Rect.MakeXYWH(BX, y + hh * 0.32, BW, hh * 0.36))
            sweep = BX + ((f.t * 0.5 + k * 0.21) % 1.3) * (BW + 300) - 150
            _hglow(f, sweep, y + hh / 2, 120, hh * 0.4, c_, 0.18)
            f.c.restore()
            f.c.drawRect(skia.Rect.MakeXYWH(BX, y + hh * 0.32, BW, hh * 0.36), paint(DIM, 0.25, stroke=1.5))
        vis = []
        for i in range(n):
            pos = slot(i, f.t)
            if pos is None:
                continue
            p_prev = slot(i, f.t - 0.06)
            vel = abs(pos - (p_prev if p_prev is not None else pos))
            vis.append((vel, i, pos))
        vis.sort()
        for vel, i, pos in vis:
            r = rows[i]
            age = f.t - times[i]
            a = clamp(age / 0.25)
            dx = (1 - ease_out(age / 0.45)) * 520
            y = top + pos * hs
            hh = hs - 14
            cy = y + hh / 2
            leader = i == crown_owner
            fresh = clamp(1 - age / 1.2)
            colr = GOLD if leader else mix("#5a6c96", c_, fresh)
            pulse = f.beat_pulse()
            if leader:
                _hglow(f, X0 + PW / 2, cy, PW * 0.65, hh * 1.4, GOLD, (0.10 + 0.10 * pulse) * a)
            if vel > 0.02:  # motion ghosts while it climbs
                for g in range(1, 5):
                    pg = slot(i, f.t - 0.035 * g)
                    if pg is not None:
                        rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(X0 + dx, top + pg * hs, PW, hh), 16, 16)
                        f.c.drawRRect(rr, paint(c_, 0.10 * (5 - g) / 4, stroke=3))
                _hglow(f, X0 + PW / 2, cy + 40, PW * 0.5, hh, c_, 0.25)
            _panel(f, X0 + dx, y, PW, hh, colr, a=a, glow_a=(0.5 * pulse if leader else 0.6 * fresh))
            x0 = X0 + dx
            rank_now = int(round(pos)) + 1
            rs = min(54, hh * 0.52)
            text(f, f"#{rank_now}", x0 + 62, cy + rs * 0.36, size=rs, color=GOLD if leader else INK, a=a,
                 glow_color=GOLD if leader else None)
            kind = r.get("kind") or _guess_icon(r.get("name"))
            _glyph(f, kind, x0 + 150, cy, hh * 0.34, color=c_, a=a)
            name = r.get("name", "?")
            ns = clamp(hh * 0.42, 30, 46)
            nw = font(ns, "semibold").measureText(name)
            if nw > 420:
                ns = max(30, ns * 420 / nw)
            text(f, name, x0 + 205, cy + ns * 0.36, size=ns, align="left", weight="semibold", a=a)
            # climbing badge
            k_in = order.index(i)
            gained = k_in - (ranks[n - 1][i] if f.t > times[order[-1]] else
                             ranks[max(k for k in range(n) if times[order[k]] <= f.t)][i])
            if gained > 0 and age < 2.2:
                ba = a * clamp((2.2 - age) / 0.4) * clamp((age - delays[k_in]) / 0.2)
                _tri(f, x0 + 112, cy - hh * 0.28, 9, GREEN, ba)
                text(f, f"+{gained}", x0 + 124, cy - hh * 0.28 + 11, size=33, color=GREEN, align="left", a=ba)
            # value bar
            grow = ease_out((age - 0.1) / 0.8)
            bw = max(BW * frac(vals[i]) * grow, 6 * grow)
            bh = hh * 0.36
            by = cy - bh / 2
            track = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(BX + dx, by, BW, bh), bh / 2, bh / 2)
            f.c.drawRRect(track, paint("#000000", 0.35 * a))
            bar = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(BX + dx, by, bw, bh), bh / 2, bh / 2)
            bcol = GOLD if leader else c_
            sh = skia.GradientShader.MakeLinear([skia.Point(BX + dx, 0), skia.Point(BX + dx + bw + 1, 0)],
                                                [col(mix(bcol, "#000000", 0.45), a), col(bcol, a),
                                                 col(mix(bcol, "#ffffff", 0.45), a)], [0, 0.8, 1])
            f.c.drawRRect(bar, skia.Paint(AntiAlias=True, Shader=sh))
            f.c.save()
            f.c.clipRRect(bar, doAntiAlias=True)
            sweep = BX + dx + ((f.t * 0.6 + i * 0.37) % 1.4) * (BW + 200) - 100
            _hglow(f, sweep, cy, 90, bh * 1.3, "#ffffff", 0.35 * a)
            f.c.drawLine(BX + dx + bh / 2, by + bh * 0.25, BX + dx + bw - bh / 2, by + bh * 0.25,
                         paint("#ffffff", 0.35 * a, stroke=2))
            f.c.restore()
            soft_light(f, BX + dx + bw, cy, bh * 1.6, bcol, 0.6 * a)
            vs = clamp(hh * 0.40, 30, 44)
            vtxt = _fmt(vals[i] * grow, vals[i]) + unit
            vw = font(vs, "bold").measureText(vtxt)
            text(f, vtxt, x0 + PW - 28, cy + vs * 0.36, size=vs if vw < 270 else vs * 270 / vw, align="right",
                 a=a, color=GOLD if leader else INK)
            if fresh > 0 and i != surprise:
                _chip(f, "NEW", BX + dx - 24, cy + 6, c_, a=fresh * a)
        # the crown on whoever is on top
        if vis:
            pos = slot(crown_owner, f.t)
            if pos is not None:
                y = top + pos * hs + (hs - 14) / 2
                k = ease_back(clamp((f.t - crown_t) / 0.4))
                bob = 4 * math.sin(f.t * 3) - 5 * f.beat_pulse()
                _crown(f, X0 + 4, y - hs * 0.42 + bob, 22 * k, a=clamp(k * 2), glow_a=0.5 + 0.4 * f.beat_pulse())
        if s_land > 0:
            sy = top + (hs - 14) / 2
            shockwave(f, X0 + 4, sy - hs * 0.4, land, speed=1300, life=1.4, color=GOLD, width=20)
            particles(f, X0 + 300, sy, land, n=180, speed=(200, 1100), life=(0.5, 1.8), size=(2, 5), color=GOLD,
                      key="lb-burst", spread=(-80, 80))
    _chrome(f, c_, "LIVE RANKING", title,
            readouts=[(f"ENTRIES {sum(1 for t in times if t <= f.t)}/{n}", DIM)])
    flash(f, land, dur=0.45, color="#fff4d6", peak=0.55)
    slam_text(f, p("slam", "NEW #1" if ranks[-1][surprise] == 0 else f"#{ranks[-1][surprise] + 1}"),
              1180, 560, land, size=150, glow_color=GOLD, hold=1.5, snap=False)


# ================================================================ 2. speed race

_RACE_DEFAULT = [
    {"name": "Fighter jet", "speed": 0.68, "unit_text": "0.68 km/s"},
    {"name": "Rifle bullet", "speed": 1.0, "unit_text": "1 km/s"},
    {"name": "ISS", "speed": 7.66, "unit_text": "7.7 km/s"},
    {"name": "Earth's orbit", "speed": 29.8, "unit_text": "29.8 km/s"},
    {"name": "Parker Solar Probe", "speed": 192, "unit_text": "192 km/s"},
    {"name": "Light", "speed": 299792, "unit_text": "299,792 km/s"},
]


def _race_sfx(p):
    go, pay = p("go_at"), p("payoff_at")
    gb, go_off = (go, 0.0) if go else (1.0, 0.0)
    pb, off = (pay, 0.0) if pay else ("end", -3.0)
    return [Sfx("tick", gb, offset=go_off - 0.75), Sfx("tick", gb, offset=go_off - 0.5),
            Sfx("tick", gb, offset=go_off - 0.25), Sfx("whoosh", gb), Sfx("riser", pb, offset=off - 1.0, dur=1.2),
            Sfx("impact", pb, offset=off + 0.9), Sfx("808", pb, offset=off + 0.9)]


@template("speed_race", kind="data", sfx=_race_sfx)
@_hud
def speed_race(f, p):
    """A drag race of speeds on glowing lanes: start lights, GO, and everything launches with motion streaks.
    Distances are honest (each racer's position is its speed x time), so the camera keeps zooming out to track
    the leader: slow racers fall back to the start line while faster ones scream in from off-screen, a distance
    ruler morphs and a TRACKING readout names who the camera follows. Payoff: the camera finally locks onto the
    fastest, everything else collapses into a pile at the start, and the 'N x FASTER' ratio slams in.
    params: racers [{name, speed (number, same unit for all), unit_text (label, e.g. '7.7 km/s'),
    icon (bullet|jet|iss|rocket|probe|light|sound|dot or a body kind, optional)}] (2-6, any order),
    unit (speed unit, default 'km/s', used for the ruler), go_at (word the race starts on),
    payoff_at (word the fastest takes over), slam (payoff text), title, color, background"""
    c_ = accent(f, p, default=["cyan", "pink", "green", "ice", "orange"])
    racers = sorted(list(p("racers") or _RACE_DEFAULT), key=lambda r: float(r.get("speed", 1)))
    n = len(racers)
    custom = bool(p("racers"))
    title = p("title", None if custom else "How fast is fast?")
    unit = p("unit", "km/s")
    dist_unit = unit.split("/")[0].strip() or "km"
    v = [max(float(r.get("speed", 1)), 1e-9) for r in racers]
    lv = [math.log10(x) for x in v]
    go = f.time(p("go_at")) if p("go_at") is not None else min(1.0, f.dur * 0.15)
    pay = _late(f, p("payoff_at"))
    t = f.t
    # who the camera tracks: racer 0, then each faster one in turn, then (payoff) the fastest
    m = max(n - 1, 1)
    Ta, Tb = go + 1.0, max(pay - 0.4, go + 1.1)

    def focus_log(tt):
        if n == 1:
            return lv[0]
        if tt <= Ta or m == 1:
            lf = lv[0]
        elif tt < Tb:
            u = (tt - Ta) / (Tb - Ta) * (m - 1)
            k = min(int(u), m - 2)
            lf = lerp(lv[k], lv[k + 1], ease_in_out((u - k - 0.4) / 0.6))
        else:
            lf = lv[m - 1]
        return lerp(lf, lv[n - 1], ease_in_out((tt - pay) / 1.1))

    X0, XF = 250, 1350
    top, bottom = 268, 868
    hl = min(125, (bottom - top) / n)

    def xs_at(tt):
        vf = 10 ** focus_log(tt)
        g = ease_in_out((tt - go) / 1.4)
        return [X0 + (vi / vf) * (XF - X0) * g for vi in v], g, vf

    xs, g, vf = xs_at(t)
    xs_prev, _, _ = xs_at(t - 1 / 30)
    lf_now = focus_log(t)
    pan = 260 * max(t - go, 0) * g + 900 * (lf_now - lv[0])
    s_pay = t - (pay + 0.9)
    shake = (14 * math.exp(-s_pay * 3) if s_pay > 0 else 0) + 2.5 * g * (1 - clamp(s_pay + 1))

    _hud_bg(f, p, c_, key="rbg")
    _fit_begin(f)
    with camera(f, 960, 560, zoom=1.02 + 0.02 * f.beat_pulse() + (0.04 * math.exp(-s_pay * 3) if s_pay > 0 else 0),
                shake=shake):
        # speed lines streaming past
        rng = f.rng("race-lines")
        k = 46
        lx, ly, ls = rng.random(k) * (W + 600), top + rng.random(k) * (bottom - top), 0.4 + rng.random(k)
        lx = (lx - pan * ls * 1.4) % (W + 600) - 300
        streak = 40 + 160 * g
        for i in range(k):
            f.c.drawLine(float(lx[i]), float(ly[i]), float(lx[i] + streak * ls[i]), float(ly[i]),
                         paint(c_, 0.10 * g * float(ls[i]), stroke=2))
        # lanes (fastest on top)
        for li in range(n):
            i = n - 1 - li
            y0 = top + li * hl
            cy = y0 + hl / 2
            f.c.drawRect(skia.Rect.MakeXYWH(0, y0 + 4, W, hl - 8), paint("#0a1228" if li % 2 else "#070d1e", 0.55))
            dp = paint(c_, 0.22, stroke=2, cap_round=False)
            dp.setPathEffect(skia.DashPathEffect.Make([40, 30], pan % 70))
            f.c.drawLine(X0, y0 + 4, W, y0 + 4, dp)
            for j in range(10):  # chevrons on the lane floor
                cx = (j * 220 - pan * 0.9) % (W + 220) - 110
                if cx > X0 + 20:
                    f.c.drawPath(_path([(-0.4, -1), (0.4, 0), (-0.4, 1), (-0.1, 0)], cx, cy, hl * 0.18),
                                 paint(c_, 0.05))
        # start line, checkered
        for li in range(int((bottom - top) / 16) + 1):
            for cx in range(2):
                if (li + cx) % 2 == 0:
                    f.c.drawRect(skia.Rect.MakeXYWH(X0 - 16 + cx * 8, top + li * 16 * 0.5 * 2 / 2, 8, 8),
                                 paint(INK, 0.55))
        f.c.drawLine(X0, top, X0, bottom, paint(INK, 0.5, stroke=2))
        # distance ruler with ticks that morph as the camera zooms out
        tau = max(t - go, 0)
        if g > 0.15 and tau > 0.05:
            px_per = (XF - X0) * g / (vf * tau)
            span = (W - X0) / px_per
            e = math.floor(math.log10(span))
            for lev in range(e - 2, e + 1):
                step = 10.0 ** lev
                sp = step * px_per
                ta, la = clamp((sp - 10) / 40), clamp((sp - 190) / 90)
                if ta <= 0:
                    continue
                kk = 1
                while True:
                    x = X0 + kk * sp
                    if x > W + 10:
                        break
                    if kk % 10:
                        f.c.drawLine(x, top - 6, x, top - 6 - (14 if la > 0 else 8), paint(INK, 0.5 * ta, stroke=2))
                        if la > 0 and x < W - 300:
                            text(f, f"{_short(kk * step)} {dist_unit}", x, top - 30, size=33, color=DIM, a=la,
                                 weight="medium")
                    kk += 1
                    if kk > 400:
                        break
            text(f, "0", X0, top - 30, size=33, color=DIM, weight="medium")
        f.c.drawLine(X0, top - 6, W, top - 6, paint(INK, 0.3, stroke=2))
        # before the start: each lane shows its top speed on a log bar, so the line-up reads at a glance
        pa = 1 - clamp((t - go) / 0.6)
        if pa > 0 and n > 1:
            grow = ease_out(clamp(0.55 + t / 0.6))
            span = max(lv[-1] - lv[0], 1e-9)
            text(f, "TOP SPEED · LOG SCALE", X0 + 340, top - 30, size=33, color=DIM, align="left",
                 weight="semibold", a=pa)
            for li in range(n):
                i = n - 1 - li
                cy = top + li * hl + hl / 2
                Lb = (140 + (lv[i] - lv[0]) / span * 1050) * grow
                x0 = X0 + 340
                sh = skia.GradientShader.MakeLinear([skia.Point(x0, 0), skia.Point(x0 + Lb + 1, 0)],
                                                    [col(c_, 0.15 * pa), col(c_, 0.9 * pa)])
                f.c.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x0, cy - 7, Lb, 14), 7, 7),
                              skia.Paint(AntiAlias=True, Shader=sh))
                soft_light(f, x0 + Lb, cy, 40, c_, 0.6 * pa)
                f.c.drawCircle(x0 + Lb, cy, 6, paint("#ffffff", pa))
                text(f, f"×{_short(v[i] / v[0])}", x0 + Lb + 22, cy + 12, size=33, color=INK, align="left",
                     weight="semibold", a=pa)
        # racers
        r_ic = hl * 0.30
        for li in range(n):
            i = n - 1 - li
            rc = racers[i]
            cy = top + li * hl + hl / 2
            x = xs[i]
            kind = rc.get("icon") or _guess_icon(rc.get("name"))
            colr = INK if kind == "light" else c_
            name, sp_txt = rc.get("name", "?"), rc.get("unit_text") or f"{_fmt(v[i])} {unit}"
            off = x > W - 170
            if off:  # off the right edge: chevrons + tag
                for j in range(3):
                    ph = (f.t * 3 + j / 3) % 1
                    f.c.drawPath(_path([(-0.5, -1), (0.5, 0), (-0.5, 1), (-0.2, 0)], W - 150 + j * 30, cy, 16),
                                 paint(c_, 0.35 + 0.6 * (1 - ph)))
                text(f, name, W - 190, cy - 2, size=32, align="right", weight="semibold")
                text(f, sp_txt + "  ahead", W - 190, cy + 34, size=33, color=c_, align="right", weight="medium")
                continue
            vx = (x - xs_prev[i]) * 30
            length = clamp((x - X0) * 0.55, 0, 520) * g + clamp(abs(vx) * 0.05, 0, 200)
            if length > 4:
                sh = skia.GradientShader.MakeLinear([skia.Point(x - length, 0), skia.Point(x, 0)],
                                                    [col(colr, 0), col(colr, 0.55)])
                f.c.drawRect(skia.Rect.MakeLTRB(x - length, cy - r_ic * 0.35, x, cy + r_ic * 0.35),
                             skia.Paint(AntiAlias=True, Shader=sh, BlendMode=skia.BlendMode.kPlus))
                f.c.drawLine(x - length * 0.8, cy, x, cy, paint("#ffffff", 0.35, stroke=2, add=True))
            if kind == "light" and s_pay > -0.9:  # the beam blasting across on the payoff
                ba = clamp((s_pay + 0.9) / 0.3) * (0.6 + 0.4 * math.exp(-max(s_pay, 0) * 2))
                f.c.drawLine(X0, cy, x, cy, paint(c_, 0.5 * ba, stroke=r_ic * 1.2, blur=10, add=True))
                f.c.drawLine(X0, cy, x, cy, paint("#ffffff", 0.9 * ba, stroke=4, add=True))
            _glyph(f, kind, x, cy, r_ic, color=colr)
            right = x > 1290
            tx = x - r_ic - 18 - (length * 0.15 if right else 0) if right else x + r_ic + 22
            al = "right" if right else "left"
            text(f, name, tx, cy - 2, size=32, align=al, weight="semibold", stroke=4)
            text(f, sp_txt, tx, cy + 34, size=33, color=c_, align=al, weight="medium", stroke=4)
        if s_pay > 0:
            particles(f, X0 + 10, top + (bottom - top) / 2, pay + 0.9, n=160, speed=(150, 700), life=(0.5, 1.6),
                      size=(2, 5), color=c_, key="race-pile", spread=(-70, 70))
    # start lights
    la = 1 - clamp((t - go - 1.2) / 0.4)
    if la > 0:
        for j in range(3):
            lx = 960 + (j - 1) * 70
            lit_red = t >= go - 0.75 + j * 0.25 and t < go
            green = t >= go
            colr = GREEN if green else RED if lit_red else "#30364a"
            f.c.drawCircle(lx, 108, 24, paint("#05070d", 0.9 * la))
            f.c.drawCircle(lx, 108, 20, paint(colr, la))
            if green or lit_red:
                soft_light(f, lx, 108, 70, colr, 0.6 * la)
        if t >= go:
            text(f, "GO", 960, 182, size=50, color=GREEN, a=la * clamp((t - go) / 0.1), glow_color=GREEN)
    fi = min(range(n), key=lambda i: abs(lv[i] - lf_now))
    zoom_out = 10 ** (lf_now - lv[0])
    _chrome(f, c_, "SPEED TRIAL", title, readouts=[(f"TRACKING  {racers[fi].get('name', '?').upper()}", c_),
                                                   (f"ZOOM OUT ×{_short(zoom_out)}", DIM)])
    text(f, "positions to scale, icons not", 98, 880, size=33, color=DIM, align="left", weight="body", a=0.8)
    flash(f, pay + 0.9, dur=0.4, color="#ffffff", peak=0.6)
    if n > 1:
        ratio = v[-1] / v[0]
        slam_text(f, p("slam", f"{_sig(ratio)}× FASTER"), 960, 560, pay + 0.95, size=140, glow_color=c_,
                  hold=1.6, snap=False)


# ================================================================ 3. pictogram

def _icon_path(kind, s):
    """An icon centred on (0, 0), about 2s tall."""
    path = skia.Path()
    if kind == "person":
        path.addCircle(0, -0.62 * s, 0.3 * s)
        path.addRRect(skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(-0.48 * s, -0.22 * s, 0.48 * s, 0.95 * s),
                                            0.4 * s, 0.4 * s))
    elif kind == "star":
        for i in range(8):
            a = i * math.pi / 4 - math.pi / 2
            rr = s * (0.95 if i % 2 == 0 else 0.32)
            pt = (math.cos(a) * rr, math.sin(a) * rr)
            path.moveTo(*pt) if i == 0 else path.lineTo(*pt)
        path.close()
    elif kind == "planet":
        path.addCircle(0, 0, 0.55 * s)
        ringp = skia.Path()
        ringp.addOval(skia.Rect.MakeLTRB(-0.98 * s, -0.26 * s, 0.98 * s, 0.26 * s))
        stroke = skia.Paint(Style=skia.Paint.kStroke_Style, StrokeWidth=0.12 * s)
        ring_fill = skia.Path()
        stroke.getFillPath(ringp, ring_fill)
        path = skia.Op(path, ring_fill, skia.PathOp.kUnion_PathOp) or path
    else:
        path.addCircle(0, 0, 0.6 * s)
    return path


@lru_cache(maxsize=16)
def _icon_tile(kind, color, glow=False):
    T = 128
    surf = skia.Surface(T, T)
    c = surf.getCanvas()
    c.clear(skia.ColorTRANSPARENT)
    c.translate(T / 2, T / 2)
    path = _icon_path(kind, T * 0.38)
    if glow:
        c.drawPath(path, paint(color, 0.8, blur=10))
    sh = skia.GradientShader.MakeLinear([skia.Point(0, -T * 0.33), skia.Point(0, T * 0.33)],
                                        [col(mix(color, "#ffffff", 0.35)), col(color), col(mix(color, "#000000", 0.35))],
                                        [0, 0.5, 1])
    c.drawPath(path, skia.Paint(AntiAlias=True, Shader=sh))
    return surf.makeImageSnapshot().withDefaultMipmaps()


_MIP = skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear)


def _pict_sfx(p):
    hl, rv = p("highlight_at"), p("reveal_at")
    rb, off = (rv, 0.0) if rv else ("end", -2.5)
    return [Sfx("shimmer", 0.2, gain_db=-6), Sfx("pop", hl or 1.4), Sfx("whoosh", rb, offset=off - 1.6, dur=1.6),
            Sfx("riser", rb, offset=off - 2.0, dur=2.0, gain_db=-6), Sfx("808", rb, offset=off + 0.1),
            Sfx("impact", rb, offset=off + 0.1, gain_db=-4)]


@template("pictogram", kind="data", sfx=_pict_sfx)
@_hud
def pictogram(f, p):
    """A ratio you can feel ('1 in 10,000'). Starts close up on a few big icons (people, planets, stars or
    dots) popping in around one, which lights up in the accent colour and pulses with a tag. Then the camera
    pulls back and back as thousands more icons pop in at the edges and a counter climbs, until the whole grid
    is revealed, the highlighted few glow and the caption slams in. Up to 40,000 icons are drawn; above that
    each icon stands for several (shown on screen).
    params: total (whole group, e.g. 10000), highlight (how many are special, e.g. 1), icon (person|planet|star|dot),
    caption (payoff text, default '1 in 10,000'), label (tag on the highlighted icon, e.g. 'you'),
    highlight_at (word the special one lights up), zoom_at (word the pull-back starts), reveal_at (word the
    whole grid is shown), title, unit (what an icon is, e.g. 'people'), color, background"""
    c_ = accent(f, p, default=["gold", "cyan", "pink", "green", "orange"])
    total = max(int(p("total", 10000)), 1)
    hl_n = min(max(int(p("highlight", 1)), 0), total)
    kind = p("icon") or pick(f, "picon", ["person", "planet", "star", "dot", "person"])
    per = max(1, math.ceil(total / 40000))
    N = math.ceil(total / per)
    H_n = min(N, max(1 if hl_n else 0, round(hl_n / per)))
    cols = max(1, math.ceil(math.sqrt(N * 2.6)))
    rows = math.ceil(N / cols)
    S = 100.0
    rng = f.rng("pict")
    # the first highlighted icon sits near the middle so the pull-back reveals in every direction
    c0 = int(lerp(0.3, 0.7, rng.random()) * cols)
    r0 = int(lerp(0.3, 0.7, rng.random()) * max(rows - 1, 0)) if rows > 1 else 0
    first = min(r0 * cols + c0, N - 1)
    mask = np.zeros(N, bool)
    if H_n:
        mask[first] = True
        if H_n > 1:
            others = rng.choice(np.delete(np.arange(N), first), size=H_n - 1, replace=False)
            mask[others] = True
    hx, hy = (first % cols + 0.5) * S, (first // cols + 0.5) * S
    gx, gy = cols * S / 2, rows * S / 2
    VW, VH, VY = 1760, 600, 560
    z_fit = min(VW / (cols * S), VH / (rows * S))
    z0 = max(140 / S, z_fit * 1.6)
    hl_t = when(f, p("highlight_at"), 0.2)
    rv = _late(f, p("reveal_at"), 2.5)
    zs = f.time(p("zoom_at")) if p("zoom_at") is not None else min(hl_t + 1.0, rv - 1.2)
    zs = max(min(zs, rv - 0.6), 0.0)
    t = f.t
    if t < zs:
        z = z0 * lerp(0.92, 1.0, ease_out(t / max(zs, 0.1)))
    else:
        kz = ease_in_out((t - zs) / max(rv - zs, 0.1))
        z = math.exp(lerp(math.log(z0), math.log(z_fit), kz))
        z *= lerp(1.0, 0.95, ease_out((t - rv) / 4.0)) if t > rv else 1.0
    z *= 1 + 0.012 * f.beat_pulse()
    u = clamp((1 / z - 1 / z0) / (1 / z_fit - 1 / z0)) if z0 != z_fit else 1.0
    cx, cy = lerp(hx, gx, u), lerp(hy, gy, u)
    cs = S * z  # screen size of one cell

    # fill-in wave around the highlighted icon, keeping just ahead of the view edges
    view_r = math.hypot(cx - hx, cy - hy) + math.hypot(W / 2, H / 2) / z
    R = S * (4.6 + 4.5 * ease_out(t / 1.4))
    if t > zs:
        R = max(R, view_r * 0.9)
    if t > rv:
        R = 1e12
    band = 2.6 * S

    s_rv = t - rv
    _hud_bg(f, p, c_, key="pbg")
    _fit_begin(f)
    # visible cells
    xl, xr = cx - (W / 2 + 40) / z, cx + (W / 2 + 40) / z
    yt, yb = cy - (VY + 40) / z, cy + (H - VY + 40) / z
    c_lo, c_hi = max(int(xl // S), 0), min(int(xr // S) + 1, cols)
    r_lo, r_hi = max(int(yt // S), 0), min(int(yb // S) + 1, rows)
    base_a = lerp(0.9, 0.7, clamp(s_rv / 0.8))
    shown = 0
    with camera(f, cx, cy + (H / 2 - VY) / z, zoom=z, shake=(12 * math.exp(-s_rv * 3) if s_rv > 0 else 0)):
        if c_hi > c_lo and r_hi > r_lo:
            cc, rr = np.meshgrid(np.arange(c_lo, c_hi), np.arange(r_lo, r_hi))
            idx = (rr * cols + cc).ravel()
            ok = idx < N
            idx = idx[ok]
            px, py = (cc.ravel()[ok] + 0.5) * S, (rr.ravel()[ok] + 0.5) * S
            d = np.hypot(px - hx, py - hy)
            filled = d < R
            shown = int(filled.sum())
            inner = d < R - band
            # interior: one pattern-filled path of whole cells (row runs), fast at any count
            tile = _icon_tile(kind, "#aab6d8")
            sh = tile.makeShader(skia.TileMode.kRepeat, skia.TileMode.kRepeat, _MIP,
                                 skia.Matrix.Scale(S / 128, S / 128))
            clip = skia.Path()
            ri = (py // S).astype(int)
            ci = (px // S).astype(int)
            if inner.any():
                for row in np.unique(ri[inner]):
                    sel = inner & (ri == row)
                    a0, a1 = ci[sel].min(), ci[sel].max()
                    clip.addRect(skia.Rect.MakeLTRB(a0 * S, row * S, (a1 + 1) * S, (row + 1) * S))
                f.c.drawPath(clip, skia.Paint(Shader=sh, Alphaf=base_a))
            # the band at the wave front pops in icon by icon
            bsel = filled & ~inner
            if bsel.any():
                bx, by, bd = px[bsel], py[bsel], d[bsel]
                k = np.clip((R - bd) / band, 0, 1)
                sc = np.array([ease_back(float(q)) for q in k]) if len(k) < 4000 else k
                if cs >= 14 and len(bx) < 2500:
                    for x, y, s_ in zip(bx, by, sc):
                        h = S * 0.5 * float(s_)
                        f.c.drawImageRect(tile, skia.Rect.MakeLTRB(x - h, y - h, x + h, y + h), _MIP,
                                          skia.Paint(Alphaf=base_a))
                else:
                    dots(f, bx, by, S * 0.22 * sc, base_a, "#aab6d8")
            # the special ones
            hsel = filled & mask[idx]
            if hsel.any():
                hx_, hy_ = px[hsel], py[hsel]
                lit = clamp((t - hl_t) / 0.3)
                pulse = 0.5 + 0.5 * math.sin(t * 5) + 0.6 * f.beat_pulse()
                if lit > 0:
                    gt = _icon_tile(kind, c_, True)
                    many = len(hx_) > 300 or cs < 6
                    glow_r = max(S * 1.1, 34 / z) * (1 + 0.15 * pulse)
                    for x, y in list(zip(hx_, hy_))[:60]:
                        soft_light(f, float(x), float(y), glow_r * (2.2 if s_rv > 0 else 1.3), c_,
                                   (0.35 + 0.2 * pulse) * lit)
                    if many:
                        dots(f, hx_, hy_, max(S * 0.3, 5 / z), lit, c_)
                        dots(f, hx_, hy_, max(S * 0.12, 2.2 / z), lit, "#ffffff")
                    else:
                        sc = 1 + 0.12 * pulse * lit
                        for x, y in zip(hx_, hy_):
                            h = S * 0.5 * sc * max(1.0, 7 / cs)
                            f.c.drawImageRect(gt, skia.Rect.MakeLTRB(x - h, y - h, x + h, y + h), _MIP,
                                              skia.Paint(Alphaf=lit))
            shockwave(f, hx, hy, hl_t, speed=260 / z * 1.0, life=1.2, color=c_, width=10 / z)
            if s_rv > 0:
                shockwave(f, gx, gy, rv, speed=1400 / z, life=1.4, color=c_, width=22 / z)
    # tag on the first special icon (screen space so it stays readable as it shrinks)
    sx, sy = (hx - cx) * z + W / 2, (hy - cy) * z + VY
    la = clamp((t - hl_t - 0.2) / 0.4) * (1 - clamp(s_rv / 0.5) * 0.6)
    if la > 0 and H_n:
        rad = max(cs * 0.55, 10)
        ring(f, sx, sy, rad * (1.1 + 0.08 * math.sin(t * 5)), 4, c_, 0.9 * la)
        tx, ty = sx + 170, max(sy - 140, 250)
        if tx > W - 420:
            tx = sx - 170
        f.c.drawLine(sx + (rad if tx > sx else -rad), sy, tx, ty + 14, paint(c_, 0.9 * la, stroke=2.5))
        lab = p("label", "THIS ONE").upper()
        text(f, lab, tx + (14 if tx > sx else -14), ty + 26, size=40, color=INK, a=la,
             align="left" if tx > sx else "right", weight="bold", stroke=6)
    unit_s = p("unit", "people" if kind == "person" else "")
    shown_n = total if s_rv > 0 else min(shown * per, total)
    reads = [(f"SHOWN  {shown_n:,}", INK), (f"SPECIAL  {hl_n:,}", c_)]
    if per > 1:
        reads.append((f"1 ICON = {per:,}{_unit(unit_s)}", DIM))
    _chrome(f, c_, "SAMPLE", p("title"), readouts=reads)
    if s_rv < 0 and t > zs:
        text(f, f"×{_short(z0 / z)}", 98, 880, size=34, color=DIM, align="left", weight="semibold")
    cap = p("caption") or (f"1 in {_sig(total / max(hl_n, 1), 3)}" if hl_n <= 1 or total / hl_n >= 2
                           else f"{hl_n:,} in {total:,}")
    flash(f, rv, dur=0.45, color=c_, peak=0.35)
    slam_text(f, cap.upper(), 960, 560, rv + 0.05, size=170, glow_color=c_, hold=1.6, snap=False)
    if s_rv > 1.8:
        a = clamp((s_rv - 1.8) / 0.4)
        w = font(56, "bold").measureText(cap.upper()) + 70
        rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(960 - w / 2, 786, w, 84), 42, 42)
        f.c.drawRRect(rr, paint("#03050c", 0.8 * a))
        f.c.drawRRect(rr, paint(c_, 0.9 * a, stroke=2.5))
        text(f, cap.upper(), 960, 848, size=56, a=a, glow_color=c_)


# ================================================================ 4. electromagnetic spectrum

# (key, display name, log10 wavelength in metres at the long end, at the short end, colour, example)
_BANDS = [("radio", "Radio", 3.0, -1.0, "#9b7bff", "radio & TV"),
          ("microwave", "Microwave", -1.0, -3.0, "#5d8bff", "ovens, wifi"),
          ("infrared", "Infrared", -3.0, -6.15, "#ff5a4f", "heat"),
          ("visible", "Visible", -6.15, -6.4, "#ffffff", "your eyes"),
          ("ultraviolet", "Ultraviolet", -6.4, -8.0, "#b56bff", "sunburn"),
          ("xray", "X-ray", -8.0, -11.0, "#4fd1ff", "bones"),
          ("gamma", "Gamma", -11.0, -13.0, "#6dff9c", "exploding stars")]
_BAND_LABELS = {"radio": "Waves as long as buildings", "microwave": "What heats your dinner",
                "infrared": "Heat you can feel", "visible": "All the light your eyes can see",
                "ultraviolet": "What gives you sunburn", "xray": "Passes straight through skin",
                "gamma": "Born in exploding stars"}
_RAINBOW = ["#ff2a2a", "#ff8a1f", "#ffe23a", "#4dff6a", "#2fd5ff", "#3a5bff", "#9b3aff"]


def _spec_sfx(p):
    at = p("at")
    b, off = (at, 0.0) if at else ("end", -4.5)
    return [Sfx("glitch", 0.0, gain_db=-6), Sfx("shimmer", 0.5, gain_db=-8),
            Sfx("riser", b, offset=off - 1.3, dur=1.3, gain_db=-6), Sfx("pop", b, offset=off),
            Sfx("whoosh", b, offset=off + 0.35), Sfx("808", b, offset=off + 1.75)]


def _wl_text(lw):
    m = 10 ** lw
    for scale, name in ((1e3, "km"), (1, "m"), (1e-2, "cm"), (1e-3, "mm"), (1e-6, "µm"), (1e-9, "nm"), (1e-12, "pm")):
        if m >= scale * 0.9999:
            return f"{_fmt(m / scale)} {name}" if m / scale < 1000 else f"{m / scale:,.0f} {name}"
    return f"{m / 1e-12:.2g} pm"


@template("spectrum", kind="data", sfx=_spec_sfx)
@_hud
def spectrum(f, p):
    """The electromagnetic spectrum as a HUD instrument: a band strip from radio to gamma with its true
    log-wavelength scale, a glowing wave above it that gets shorter and shorter left to right, photons riding
    it, and energy arrows. A scanning marker sweeps back and forth reading out the wavelength, then locks onto
    the band being discussed; the others dim, the camera zooms right into that band (visible light turns into a
    rainbow, and you see how thin it really is) and the band name slams in with a label card.
    params: band (radio|microwave|infrared|visible|ultraviolet|xray|gamma), label (one line about it),
    at (word the marker locks on), label_at (word the label appears, optional), title, color, background"""
    keys = [b[0] for b in _BANDS]
    band = p("band") or pick(f, "band", keys)
    band = band.lower().replace("-", "").replace(" ", "").replace("light", "").replace("rays", "").replace("ray", "")
    band = {"xrays": "xray", "uv": "ultraviolet", "ir": "infrared", "gammas": "gamma"}.get(band, band)
    bi = keys.index(band) if band in keys else 3
    B = _BANDS[bi]
    c_ = accent(f, p, default=["cyan", "ice", "purple", "pink"])
    lock = _late(f, p("at"), 4.5, 0.35)
    z0t, z1t = lock + 0.35, lock + 1.75
    pay = f.time(p("label_at")) if p("label_at") is not None else z1t
    t = f.t
    SX0, SW = 120.0, 1680.0

    def wx(lw):  # log wavelength -> world x
        return SX0 + (3.0 - lw) / 16.0 * SW

    bx0, bx1 = wx(B[2]), wx(B[3])
    zt = clamp(1150 / (bx1 - bx0), 1.4, 12)
    kz = ease_in_out((t - z0t) / (z1t - z0t))
    z = math.exp(lerp(0, math.log(zt), kz))
    uu = clamp((1 - 1 / z) / (1 - 1 / zt)) if zt > 1 else 1
    ccx = lerp(960, (bx0 + bx1) / 2, uu)

    def sx(xw):
        return (xw - ccx) * z + 960

    # scanning marker (in u = 0..1 along the strip)
    u_t = ((bx0 + bx1) / 2 - SX0) / SW
    sweep = 0.5 - 0.47 * math.cos(math.pi * max(t - 0.3, 0) / 2.4)
    um = lerp(sweep, u_t, ease_in_out((t - (lock - 1.3)) / 1.3)) if t > lock - 1.3 else sweep
    mxw = SX0 + um * SW
    locked = t >= lock
    s_pay = t - pay

    _hud_bg(f, p, c_, key="sbg")
    _fit_begin(f)
    sy0, sy1 = 600, 700 + 30 * kz
    WY, AMP = 445, 72
    dim = lerp(1, 0.35, clamp((t - lock) / 0.4))
    with camera(f, 960, 540, shake=(10 * math.exp(-s_pay * 3) if s_pay > 0 else 0)):
        # energy arrows, fading as we zoom in
        ea = (1 - kz)
        if ea > 0:
            for side in (-1, 1):
                x0, x1 = (900, 140) if side < 0 else (1020, 1780)
                f.c.drawLine(x0, 312, x1, 312, paint(DIM, 0.6 * ea, stroke=2))
                _tri(f, x1, 312, 12, DIM, 0.8 * ea, up=None) if False else None
                hp = _path([(0, -1), (1.6 * (1 if side > 0 else -1), 0), (0, 1)], x1, 312, 9)
                f.c.drawPath(hp, paint(DIM, 0.8 * ea))
            text(f, "LONGER WAVES · LOWER ENERGY", 140, 292, size=33, color=DIM, align="left", weight="semibold",
                 a=ea)
            text(f, "SHORTER WAVES · HIGHER ENERGY", 1780, 292, size=33, color=c_, align="right",
                 weight="semibold", a=ea)
        # band strip
        for k, b in enumerate(_BANDS):
            x0, x1 = sx(wx(b[2])), sx(wx(b[3]))
            if x1 < -50 or x0 > W + 50:
                continue
            a = (1 if k == bi else dim)
            rect = skia.Rect.MakeLTRB(x0, sy0, x1, sy1)
            if b[0] == "visible":
                sh = skia.GradientShader.MakeLinear([skia.Point(x0, 0), skia.Point(x1, 0)],
                                                    [col(cc, 0.95 * a) for cc in _RAINBOW])
                f.c.drawRect(rect, skia.Paint(Shader=sh))
            else:
                f.c.drawRect(rect, _vshade(sy0, sy1, [b[4], mix(b[4], "#000000", 0.75)], None, 0.55 * a))
                f.c.drawRect(rect, paint(b[4], 0.05 * a, stroke=None, add=True))
            f.c.drawLine(x0, sy0, x0, sy1, paint("#ffffff", 0.35 * a, stroke=2))
            wpx = x1 - x0
            bn = b[1].upper()
            name_w = font(36, "bold").measureText(bn)
            if wpx <= name_w + 24:
                bn = {"Microwave": "MICRO", "Ultraviolet": "UV"}.get(b[1], bn)
                name_w = font(36, "bold").measureText(bn)
            if wpx > name_w + 24:
                text(f, bn, (max(x0, 0) + min(x1, W)) / 2, sy0 + 46, size=36,
                     color="#05070d" if b[0] == "visible" else INK, a=a)
                if wpx > name_w + 120 and sy1 - sy0 > 104:
                    text(f, b[5], (max(x0, 0) + min(x1, W)) / 2, sy0 + 92, size=33,
                         color="#05070d" if b[0] == "visible" else DIM, a=a * kz, weight="semibold")
            elif b[0] == "visible" and kz < 0.5:  # too thin to name: a callout
                mid = (x0 + x1) / 2
                ca = (1 - kz * 2)
                f.c.drawLine(mid, sy0 - 6, mid, sy0 - 50, paint(INK, 0.7 * ca, stroke=2))
                text(f, "VISIBLE", mid, sy0 - 60, size=33, color=INK, a=ca, weight="semibold")
        # target band highlight
        if locked:
            x0, x1 = sx(bx0), sx(bx1)
            pulse = f.beat_pulse()
            hr = skia.Rect.MakeLTRB(x0, sy0, x1, sy1)
            f.c.drawRect(hr, paint(c_, 0.9, stroke=4 + 3 * pulse))
            f.c.drawRect(hr, paint(c_, 0.4 + 0.3 * pulse, stroke=16, blur=12, add=True))
        # grain on the strip
        f.c.save()
        f.c.clipRect(skia.Rect.MakeLTRB(sx(SX0), sy0, sx(SX0 + SW), sy1))
        _haze(f, "#ffffff", 0.10)
        f.c.restore()
        # wavelength axis
        ay = sy1 + 26
        f.c.drawLine(max(sx(SX0), 0), ay, min(sx(SX0 + SW), W), ay, paint(DIM, 0.7, stroke=2))
        ppd = SW / 16 * z
        for d in range(-13, 4):
            x = sx(wx(d))
            if -20 < x < W + 20:
                f.c.drawLine(x, ay, x, ay + 14, paint(DIM, 0.8, stroke=2))
                if ppd > 40:
                    for mn in range(2, 10):
                        xm = sx(wx(d + math.log10(mn)))
                        f.c.drawLine(xm, ay, xm, ay + 7, paint(DIM, 0.4 * clamp((ppd - 40) / 60), stroke=1.5))
        labels = [(3, 1), (0, 1), (-2, 1), (-3, 1), (-6, 1), (-9, 1), (-12, 1)] + \
                 [(d, 2) for d in (2, 1, -1, -4, -5, -7, -8, -10, -11, -13)] + \
                 [(math.log10(7e-7), 3), (math.log10(4e-7), 3), (math.log10(5.5e-7), 3)]
        for lw, prio in labels:
            x = sx(wx(lw))
            thr = {1: 0, 2: 190, 3: 900}[prio]
            a = clamp((ppd - thr) / 60) if prio > 1 else 1
            if a > 0 and 90 < x < W - 90:
                text(f, _wl_text(lw), x, ay + 50, size=33, color=DIM, a=a, weight="medium")
        # the wave: wavelength shrinks exponentially along the strip (not to scale)
        xs_ = np.arange(-10, W + 12, 1.25, dtype=np.float64)
        xw_ = (xs_ - 960) / z + ccx
        lam0, lam1 = 430.0, 17.0
        bb = math.log(lam0 / lam1) / SW
        phase = 2 * math.pi * (np.exp(bb * (xw_ - SX0)) - 1) / (bb * lam0) - t * 5.0
        env = np.clip((xw_ - SX0 + 60) / 60, 0, 1) * np.clip((SX0 + SW + 60 - xw_) / 60, 0, 1)
        draw_k = clamp(0.45 + t / 1.6)
        xmax = lerp(-10, W + 12, draw_k)
        sel = xs_ <= xmax
        ys_ = WY + AMP * env * np.sin(phase)
        if sel.sum() > 2:
            pts = [skia.Point(float(a), float(b)) for a, b in zip(xs_[sel], ys_[sel])]
            path = skia.Path()
            path.addPoly(pts, False)
            stops, cols_ = [], []
            for b in _BANDS:
                for lw_, cc in (((b[2] + b[3]) / 2, b[4]),) if b[0] != "visible" else \
                        [(lerp(b[2], b[3], q / 6), _RAINBOW[q]) for q in range(7)]:
                    stops.append(clamp(sx(wx(lw_)) / W))
                    cols_.append(col(cc, 1))
            sh = skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(W, 0)], cols_, stops)
            f.c.drawPath(path, skia.Paint(AntiAlias=True, Shader=sh, Style=skia.Paint.kStroke_Style, StrokeWidth=11,
                                          Alphaf=0.2, BlendMode=skia.BlendMode.kPlus))
            f.c.drawPath(path, skia.Paint(AntiAlias=True, Shader=sh, Style=skia.Paint.kStroke_Style, StrokeWidth=4))
            # photons riding the wave
            rng = f.rng("photons")
            k = 34
            pxw = SX0 + ((rng.random(k) + t * (0.05 + 0.05 * rng.random(k))) % 1.0) * SW
            ppx = (pxw - ccx) * z + 960
            pph = 2 * math.pi * (np.exp(bb * (pxw - SX0)) - 1) / (bb * lam0) - t * 5.0
            ppy = WY + AMP * np.sin(pph)
            ok = (ppx < xmax) & (ppx > -20) & (ppx < W + 20)
            dots(f, ppx[ok], ppy[ok], 9, 0.25, c_, add=True)
            dots(f, ppx[ok], ppy[ok], 3, 0.95, "#ffffff", add=True)
        # the scanning marker
        mx = sx(mxw)
        ma = 1.0
        if ma > 0:
            mcol = c_ if locked else INK
            f.c.drawLine(mx, 345, mx, sy1 + 10, paint(mcol, 0.35 * ma, stroke=10, blur=8, add=True))
            f.c.drawLine(mx, 345, mx, sy1 + 10, paint(mcol, 0.95 * ma, stroke=2.5))
            _tri(f, mx, 352, 14, mcol, ma, up=False)
            soft_light(f, mx, WY, 90, mcol, 0.35 * ma)
            if locked:
                ring(f, mx, (sy0 + sy1) / 2, 40 + 8 * math.sin(t * 6), 4, c_, 0.8)
                shockwave(f, mx, (sy0 + sy1) / 2, lock, speed=700, life=1.0, color=c_, width=10)
        lw_m = 3.0 - (mxw - SX0) / SW * 16
        bname = next((b[1] for b in _BANDS if b[2] >= lw_m >= b[3]), "")
        rd = f"WAVELENGTH {_wl_text(lw_m)}  ·  {bname.upper()}"
        rw = font(34, "semibold").measureText(rd) + 50
        rx = clamp(mx - rw / 2, 60, W - 60 - rw)
        if ma > 0:
            rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(rx, 818, rw, 66), 12, 12)
            f.c.drawRRect(rr, paint("#03050c", 0.8 * ma))
            f.c.drawRRect(rr, paint(c_ if locked else DIM, 0.9 * ma, stroke=2))
            text(f, rd, rx + rw / 2, 862, size=34, color=c_ if locked else INK, a=ma, weight="semibold")
        # energy meter next to the readout
        if ma > 0:
            ex = rx + rw + 18 if rx + rw + 60 < W - 60 else rx - 40
            f.c.drawRect(skia.Rect.MakeXYWH(ex, 818, 22, 66), paint(DIM, 0.6 * ma, stroke=2))
            fill = clamp((mxw - SX0) / SW)
            f.c.drawRect(skia.Rect.MakeLTRB(ex + 3, 881 - 60 * fill, ex + 19, 881), paint(c_, 0.9 * ma))
    # label card
    if s_pay > 0:
        a = clamp(s_pay / 0.35)
        lab = p("label", _BAND_LABELS[B[0]])
        bcx = clamp(sx((bx0 + bx1) / 2), 300, W - 300)
        lw = max(font(44, "bold").measureText(lab), 300) + 70
        lx = clamp(bcx - lw / 2, 70, W - 70 - lw)
        rise = (1 - ease_out(s_pay / 0.5)) * 30
        f.c.drawLine(bcx, sy0 - 4, bcx, 330 + rise, paint(c_, 0.8 * a, stroke=2.5))
        f.c.drawCircle(bcx, sy0 - 4, 6, paint(c_, a))
        rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(lx, 236 + rise, lw, 94), 16, 16)
        f.c.drawRRect(rr, paint("#03050c", 0.85 * a))
        f.c.drawRRect(rr, paint(c_, 0.9 * a, stroke=2.5))
        text(f, lab, lx + lw / 2, 298 + rise, size=44, a=a, glow_color=c_ if s_pay < 1 else None)
    _chrome(f, c_, "SPECTRUM SCAN", p("title"), readouts=[("TARGET LOCKED" if locked else "SCANNING…", c_ if locked else DIM),
                                                         (f"ZOOM ×{z:.1f}", DIM)])
    text(f, "wave sizes not to scale", 98, 880, size=33, color=DIM, align="left", weight="body", a=0.8)
    flash(f, pay, dur=0.4, color=B[4] if B[0] != "visible" else "#ffffff", peak=0.4)
    name = {"xray": "X-RAYS", "gamma": "GAMMA RAYS", "visible": "VISIBLE LIGHT"}.get(B[0], B[1].upper())
    slam_text(f, name, 960, 520, pay + 0.05, size=150, glow_color=c_, hold=1.4, snap=False)


# ================================================================ 5. log timeline

_TL_DEFAULT = [
    {"label": "Light from the Moon", "seconds": 1.3},
    {"label": "Light from the Sun", "seconds": 499},
    {"label": "One trip round the Sun", "seconds": 3.156e7},
    {"label": "The pyramids", "seconds": 4500 * 3.156e7},
    {"label": "The dinosaurs", "seconds": 66e6 * 3.156e7},
    {"label": "Age of the Universe", "seconds": 13.8e9 * 3.156e7},
]
_TL_ANCHORS = [(-3, "1 millisecond", 2), (0, "1 second", 1), (1.778, "1 minute", 1), (3.556, "1 hour", 1),
               (4.936, "1 day", 1), (5.782, "1 week", 3), (6.415, "1 month", 3), (7.499, "1 year", 1),
               (8.499, "10 years", 3), (9.499, "1 century", 2), (10.499, "1,000 years", 2),
               (11.499, "10,000 years", 3), (12.499, "100,000 years", 3), (13.499, "1 million yrs", 1),
               (14.499, "10 million yrs", 3), (15.499, "100 million yrs", 2), (16.499, "1 billion yrs", 1),
               (17.499, "10 billion yrs", 2)]
_TL_ERAS = [(-4, 1.778, "SECONDS"), (1.778, 3.556, "MINUTES"), (3.556, 4.936, "HOURS"), (4.936, 7.499, "DAYS"),
            (7.499, 10.499, "YEARS"), (10.499, 13.499, "THOUSANDS OF YEARS"), (13.499, 16.499, "MILLIONS OF YEARS"),
            (16.499, 19, "BILLIONS")]


def _tl_sfx(p):
    ev = p("events") or []
    out = [Sfx("shimmer", 0.2, gain_db=-8)]
    out += [Sfx("tick", e["at"], offset=0.9) for e in ev[:-1] if e.get("at")]
    out += [Sfx("whoosh", e["at"], offset=0.1, gain_db=-8) for e in ev[:-1] if e.get("at")]
    last = ev[-1].get("at") if ev else None
    b, off = (last, 0.0) if last else ("end", -3.0)
    return out + [Sfx("riser", b, offset=off - 1.0, dur=1.2, gain_db=-4), Sfx("impact", b, offset=off + 0.95),
                  Sfx("808", b, offset=off + 0.95)]


@template("timeline_log", kind="data", sfx=_tl_sfx)
@_hud
def timeline_log(f, p):
    """Deep time on a logarithmic axis (each step is 10x longer). Event pins drop onto the axis one at a time,
    each with a card ('Light from the Sun - 8.3 minutes'); whenever the next event is too far away to fit, the
    camera slides and zooms out by whole decades, older events squash to the left and the tick labels morph
    from seconds to hours to years to billions of years. Payoff: the last, biggest event lands with a flash
    and its duration slams in. List events in the order they're mentioned.
    params: events [{label, seconds (duration or time ago, in seconds), at (word it drops on)}] (2-7),
    title, slam (payoff text, default the last event's duration), color, background"""
    c_ = accent(f, p, default=["cyan", "gold", "purple", "pink", "green"])
    events = list(p("events") or _TL_DEFAULT)
    custom = bool(p("events"))
    title = p("title", None if custom else "From seconds to billions of years")
    n = len(events)
    L = [math.log10(max(float(e.get("seconds", 1)), 1e-6)) for e in events]
    last_t = _late(f, None)
    times = []
    for i, e in enumerate(events):
        if e.get("at") is not None:
            times.append(f.time(e["at"]))
        elif i == n - 1 and n > 1:
            times.append(last_t)
        else:
            times.append(lerp(-1.6, max(last_t - 1.6, 0.4), i / max(n - 2, 1)))
    order = sorted(range(n), key=lambda i: times[i])
    first_word = times[order[0]] if n else 0.0
    if n and times[order[0]] < 1.6:
        times[order[0]] = min(times[order[0]], -1.6)  # on screen from the first frame
    rank_L = {j: r for r, j in enumerate(sorted(range(n), key=lambda i: L[i]))}

    def win_for(k):
        sel = [L[j] for j in order[:k + 1]]
        lo, hi = min(sel) - 0.9, max(sel) + 0.9
        if hi - lo < 3.5:
            c = (lo + hi) / 2
            lo, hi = c - 1.75, c + 1.75
        return lo, hi

    lo, hi = win_for(0)
    lo -= 0.2
    hi = lo + 3.2
    for k in range(n):
        tk = times[order[k]]
        if f.t < tk:
            break
        prev = (lo, hi)
        tgt = win_for(k)
        e = ease_in_out((f.t - tk) / 1.3)
        lo, hi = lerp(prev[0], tgt[0], e), lerp(prev[1], tgt[1], e)
        if e < 1:
            # if a later event already started moving, keep chaining from here
            pass
    X0, X1, AX = 130, 1790, 650

    def xof(lw):
        return X0 + (lw - lo) / (hi - lo) * (X1 - X0)

    ppd = (X1 - X0) / (hi - lo)
    final = order[-1]
    land_final = times[final] + 0.95
    s_fin = f.t - land_final
    shake = 16 * math.exp(-s_fin * 3) if s_fin > 0 else 0

    _hud_bg(f, p, c_, key="tbg")
    _fit_begin(f)
    with camera(f, 960, 540, zoom=1.0 + 0.025 * math.sin(f.t * 0.3) + (0.03 * math.exp(-s_fin * 4) if s_fin > 0 else 0),
                shake=shake):
        # parallax star streaks that slide with the window
        rng = f.rng("tl-dust")
        k = 70
        dx = rng.random(k) * W
        dy = 230 + rng.random(k) * 650
        dd = 0.3 + rng.random(k)
        dx = (dx - (lo + hi) * 40 * dd) % W
        dots(f, dx, dy, 1.5 + dd * 1.5, 0.25 + 0.3 * dd, c_)
        # a receding floor grid under the axis that slides with the view
        hz, fb = AX + 6, 884
        for j in range(14):
            q = ((j + (f.t * 0.35) % 1) / 14) ** 1.7
            y = hz + (fb - hz) * q
            f.c.drawLine(0, y, W, y, paint(c_, 0.03 + 0.12 * q, stroke=1.5))
        off = ((lo + hi) * 0.5 * 140) % 160
        for k in range(-14, 15):
            xb = 960 + k * 160 - off
            f.c.drawLine(960 + (xb - 960) * 0.18, hz, xb, fb, paint(c_, 0.09, stroke=1.5))
        # and a faint mirrored glow column above each landed event
        # the axis
        _hglow(f, 960, AX, 1100, 160, c_, 0.10 + 0.06 * f.beat_pulse())
        f.c.drawLine(X0 - 50, AX, X1 + 60, AX, paint(c_, 0.35, stroke=14, blur=10, add=True))
        sh = skia.GradientShader.MakeLinear([skia.Point(X0 - 50, 0), skia.Point(X1 + 60, 0)],
                                            [col(c_, 0.3), col(INK, 1), col(c_, 1)], [0, 0.5, 1])
        f.c.drawLine(X0 - 50, AX, X1 + 60, AX, skia.Paint(AntiAlias=True, Shader=sh, Style=skia.Paint.kStroke_Style,
                                                          StrokeWidth=4))
        f.c.drawPath(_path([(0, -1), (1.8, 0), (0, 1)], X1 + 60, AX, 11), paint(c_, 1))
        # decade ticks + minor ticks
        for d in range(int(math.floor(lo)) - 1, int(math.ceil(hi)) + 2):
            x = xof(d)
            if X0 - 60 < x < X1 + 60:
                f.c.drawLine(x, AX - 12, x, AX + 12, paint(INK, 0.85, stroke=2.5))
            ma = clamp((ppd - 50) / 80)
            if ma > 0:
                for mn in range(2, 10):
                    xm = xof(d + math.log10(mn))
                    if X0 - 60 < xm < X1 + 60:
                        f.c.drawLine(xm, AX - 5, xm, AX + 5, paint(INK, 0.45 * ma, stroke=1.5))
        # friendly labels that fade in and out with the zoom
        for j, (lw, s, prio) in enumerate(_TL_ANCHORS):
            x = xof(lw)
            thr = {1: 40, 2: 110, 3: 230}[prio]
            a = clamp((ppd - thr) / 50)
            if a > 0 and X0 - 40 < x < X1 + 30:
                row = j % 2
                f.c.drawLine(x, AX + 12, x, AX + 22 + row * 44, paint(DIM, 0.6 * a, stroke=1.5))
                text(f, s, x, AX + 52 + row * 44, size=33, color=DIM, a=a, weight="medium")
        # era strip: which everyday unit each stretch of the axis is measured in
        ey0, ey1 = AX + 122, AX + 172
        hues = [c_, "#7a5cff", "#ff4fa3", GOLD, GREEN, CYAN, "#ff8a3d", RED]
        for j, (e0, e1, nm) in enumerate(_TL_ERAS):
            x0, x1 = max(xof(e0), X0 - 50), min(xof(e1), X1 + 60)
            if x1 <= x0 + 2:
                continue
            hue = hues[j % len(hues)]
            f.c.drawRect(skia.Rect.MakeLTRB(x0, ey0, x1, ey1), _vshade(ey0, ey1, [hue, mix(hue, "#000000", 0.7)], None, 0.42))
            f.c.drawLine(x0, ey0, x0, ey1, paint("#ffffff", 0.4, stroke=2))
            wdt = font(33, "semibold").measureText(nm)
            if x1 - x0 > wdt + 20:
                text(f, nm, (x0 + x1) / 2, ey0 + 36, size=33, color=INK, weight="semibold", a=clamp((x1 - x0 - wdt - 20) / 60))
        f.c.drawRect(skia.Rect.MakeLTRB(X0 - 50, ey0, X1 + 60, ey1), paint(c_, 0.5, stroke=1.5))
        # event pins and cards
        for k_, i in enumerate(order):
            t0 = times[i]
            s = f.t - t0
            if s < 0.35:
                continue
            x = xof(L[i])
            fall = clamp((s - 0.35) / 0.6)
            y = lerp(-80, AX, ease_in(fall))
            if fall >= 1:
                y = AX - 26 * abs(math.sin((s - 0.95) * 9)) * math.exp(-(s - 0.95) * 6)
            newest = k_ == max(kk for kk in range(n) if times[order[kk]] <= f.t)
            colr = c_ if newest else mix(c_, INK, 0.5)
            if fall >= 1:
                level = rank_L[i] % 3
                cy_bot = [575, 452, 329][level]
                sa = clamp((s - 0.95) / 0.3)
                stem_top = lerp(AX, cy_bot, ease_out(sa))
                f.c.drawLine(x, AX, x, stem_top, paint(colr, 0.8, stroke=2.5))
                lab = events[i].get("label", "")
                dur_s = _human_time(float(events[i].get("seconds", 1)))
                w = max(font(34, "semibold").measureText(lab), font(33, "medium").measureText(dur_s)) + 40
                cx = clamp(x, 100 + w / 2, W - 100 - w / 2)
                ca = clamp((s - 1.05) / 0.3) * (1.0 if newest else 0.85)
                if ca > 0:
                    rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(cx - w / 2, cy_bot - 92, w, 92), 14, 14)
                    f.c.drawRRect(rr, paint("#03050c", 0.82 * ca))
                    if newest:
                        f.c.drawRRect(rr, paint(c_, 0.35 * ca * (0.6 + 0.4 * f.beat_pulse()), stroke=12, blur=10,
                                                add=True))
                    f.c.drawRRect(rr, paint(colr, 0.9 * ca, stroke=2.5))
                    text(f, lab, cx, cy_bot - 50, size=34, a=ca, weight="semibold",
                         reveal=f.prog(t0 + 1.05, 0.4, ease=lambda q: clamp(q)))
                    text(f, dur_s, cx, cy_bot - 14, size=33, color=c_, a=ca, weight="medium")
            # the pin itself
            diamond = _path([(0, -1), (0.7, 0), (0, 1), (-0.7, 0)], x, y, 16)
            soft_light(f, x, y, 60, colr, 0.5)
            f.c.drawPath(diamond, paint(colr, 1))
            f.c.drawPath(diamond, paint("#ffffff", 0.9, stroke=2))
            if fall < 1:
                f.c.drawLine(x, y - 90, x, y - 14, paint(colr, 0.5, stroke=3, add=True))
            land = t0 + 0.95
            shockwave(f, x, AX, land, speed=420, life=0.9, color=colr, width=8)
            if i == order[0] and first_word > t0 + 1:  # pre-placed first event still pings on its word
                shockwave(f, x, AX, first_word, speed=420, life=0.9, color=c_, width=8)
            if i == final and n > 1:
                particles(f, x, AX, land, n=200, speed=(200, 1000), life=(0.5, 1.8), size=(2, 5), color=c_,
                          key="tl-final", spread=(180, 360))
    # zoom-out readout when the window widens
    for k in range(1, n):
        tk = times[order[k]]
        widen = (win_for(k)[1] - win_for(k)[0]) - (win_for(k - 1)[1] - win_for(k - 1)[0])
        s = f.t - tk
        if widen > 0.3 and 0 <= s < 1.6:
            a = clamp(s / 0.15) * clamp((1.6 - s) / 0.4)
            text(f, f"ZOOM OUT ×{_short(10 ** widen)}", X1 + 40, AX - 40, size=40, color=c_, align="right", a=a,
                 glow_color=c_)
    _chrome(f, c_, "DEEP TIME · LOG SCALE", title,
            readouts=[(f"VIEW  {_human_time(10 ** max(lo, -6))}", DIM), (f"TO  {_human_time(10 ** hi)}", INK)])
    text(f, "log scale: each big tick is 10× longer", 98, 880, size=33, color=DIM, align="left", weight="body", a=0.8)
    flash(f, land_final, dur=0.45, color="#ffffff", peak=0.5)
    if n > 1:
        slam = p("slam", _human_time(float(events[final].get("seconds", 1))).upper())
        slam_text(f, slam, 960, 470, land_final + 0.05, size=140, glow_color=c_, hold=1.5, snap=False)


# ================================================================ 6. dashboard

_DASH_DEFAULT = [
    {"kind": "gauge", "label": "Surface temp", "value": 15, "max": 60, "unit": "°C"},
    {"kind": "sparkline", "label": "CO2", "value": 420, "unit": " ppm"},
    {"kind": "counter", "label": "Population", "value": 8.1e9},
    {"kind": "ring", "label": "Oxygen", "value": 21, "max": 100, "unit": "%"},
]


def _dash_sfx(p):
    panels = p("panels") or []
    out = [Sfx("glitch", 0.1, gain_db=-6)]
    out += [Sfx("pop", pn["at"], gain_db=-4) for pn in panels if pn.get("at")] or \
           [Sfx("pop", 0.3 + 0.45 * i, gain_db=-6) for i in range(4)]
    ca = p("critical_at")
    b, off = (ca, 0.0) if ca else ("end", -3.0)
    return out + [Sfx("riser", b, offset=off - 1.6, dur=1.6, gain_db=-4), Sfx("glitch", b, offset=off),
                  Sfx("808", b, offset=off), Sfx("impact", b, offset=off, gain_db=-4)]


def _noise1(t, seed):
    """Smooth deterministic wobble in about -1..1."""
    return 0.5 * math.sin(t * 1.7 + seed) + 0.3 * math.sin(t * 3.9 + seed * 2.1) + 0.2 * math.sin(t * 7.3 + seed * 0.7)


@template("dashboard", kind="data", sfx=_dash_sfx)
@_hud
def dashboard(f, p):
    """Mission-control status board for a planet: a spinning planet in a rotating targeting reticle, with four
    live panels flying in around it (a needle gauge, a scrolling sparkline, a rolling counter and a segmented
    ring), wired to the planet. Values tick live. Escalation: one panel starts flashing WARNING; payoff on
    critical_at: that panel's value spikes, it turns red with hazard stripes, the planet gets a red halo,
    the screen shakes and CRITICAL slams in.
    params: title, kind (planet, default earth), panels [{kind (gauge|sparkline|counter|ring), label, value,
    max (gauge/ring), unit, at (word it appears on)}] (exactly 4 look best), critical (index 0-3 of the panel
    that fails), critical_value (what its value spikes or drops to), critical_at (word), slam (default 'CRITICAL'),
    color, background"""
    c_ = accent(f, p, default=["cyan", "green", "ice", "gold"])
    panels = list(p("panels") or _DASH_DEFAULT)[:4]
    n = len(panels)
    custom = bool(p("panels"))
    kind = p("kind", "earth")
    title = p("title", None if custom else "Earth · planet status")
    crit = p("critical")
    if crit is None:
        cands = [i for i, pn in enumerate(panels) if pn.get("kind") != "counter"] or list(range(n))
        crit = cands[int(f.rng("dcrit").integers(0, len(cands)))]
    crit = int(crit) % max(n, 1)
    ct = _late(f, p("critical_at"))
    s_c = f.t - ct
    warn = clamp((f.t - (ct - 1.8)) / 0.3) if s_c < 0 else 0
    t = f.t
    pulse = f.beat_pulse()
    shake = 14 * math.exp(-s_c * 2.6) if s_c > 0 else 0
    shown_at = []
    for i, pn in enumerate(panels):
        shown_at.append(f.time(pn["at"]) if pn.get("at") is not None else i * 0.4 - 0.8)

    _hud_bg(f, p, c_, key="dbg")
    _fit_begin(f)
    PX = [(80, 222), (80, 570), (1320, 222), (1320, 570)]
    PWd, PHd = 520, 300
    cx, cy, R = 960, 548, 200
    with camera(f, 960, 540, zoom=1.0 + 0.03 * ease_in_out(f.p) + (0.03 * math.exp(-s_c * 4) if s_c > 0 else 0),
                shake=shake):
        # the planet + reticle
        red = clamp(s_c / 0.5) if s_c > 0 else 0
        soft_light(f, cx, cy, R * 2.4, mix(c_, RED, red), 0.18 + 0.1 * pulse)
        body(f, kind, cx, cy, R * (1 + 0.01 * pulse), rotation=t * 0.02, light=(-0.6, -0.35, 0.7))
        if red > 0:
            halo(f, cx, cy, R, R * 1.35, RED, 0.6 * red * (0.7 + 0.3 * math.sin(t * 8)))
            f.c.drawCircle(cx, cy, R, paint(RED, 0.18 * red, add=True))
        f.c.save()
        f.c.clipPath(skia.Path().addCircle(cx, cy, R), doAntiAlias=True)
        scan = cy - R + (t * 160) % (2 * R)
        f.c.drawLine(cx - R, scan, cx + R, scan, paint(c_ if not red else RED, 0.6, stroke=2, add=True))
        _hglow(f, cx, scan, R, 30, c_ if not red else RED, 0.3)
        f.c.restore()
        rc = mix(c_, RED, red)
        ticks = skia.Path()
        rot = t * 12
        for k in range(120):
            a = math.radians(k * 3 + rot)
            l = 18 if k % 10 == 0 else 8
            ticks.moveTo(cx + math.cos(a) * (R + 36), cy + math.sin(a) * (R + 36))
            ticks.lineTo(cx + math.cos(a) * (R + 36 + l), cy + math.sin(a) * (R + 36 + l))
        f.c.drawPath(ticks, paint(rc, 0.55, stroke=2))
        for k in range(3):
            st = -rot * 1.6 + k * 120
            f.c.drawArc(skia.Rect.MakeXYWH(cx - R - 18, cy - R - 18, 2 * R + 36, 2 * R + 36), st, 70, False,
                        paint(rc, 0.85, stroke=3))
        sweep_sh = skia.GradientShader.MakeSweep(cx, cy, [col(rc, 0), col(rc, 0), col(rc, 0.35)], [0, 0.8, 1])
        f.c.save()
        f.c.rotate((t * 70) % 360, cx, cy)
        f.c.drawCircle(cx, cy, R + 30, skia.Paint(AntiAlias=True, Shader=sweep_sh, Style=skia.Paint.kStroke_Style,
                                                  StrokeWidth=22, BlendMode=skia.BlendMode.kPlus))
        f.c.restore()
        rng = f.rng("dash-sats")
        for k in range(5):  # little data satellites orbiting
            a = rng.random() * 6.28 + t * (0.3 + rng.random() * 0.4)
            rr = R + 70 + rng.random() * 30
            x, y = cx + math.cos(a) * rr, cy + math.sin(a) * rr * 0.92
            f.c.drawCircle(x, y, 3.5, paint(rc, 0.9))
            soft_light(f, x, y, 16, rc, 0.5)
        # panels
        for i, pn in enumerate(panels):
            px, py = PX[i]
            s = t - shown_at[i]
            if s < 0:  # standby: the frame is there, waiting for its signal
                _panel(f, px, py, PWd, PHd, "#3a4668", a=0.8, fill=0.45)
                text(f, pn.get("label", "").upper(), px + 30, py + 58, size=32, color=DIM, align="left",
                     weight="semibold", a=0.7)
                _chip(f, "STANDBY", px + PWd - 26, py + 56, DIM, a=0.5 + 0.3 * math.sin(t * 4 + i))
                nrng = np.random.default_rng(int(t * 15) + i * 1000)
                dots(f, px + 30 + nrng.random(160) * (PWd - 60), py + 90 + nrng.random(160) * (PHd - 120), 1.6,
                     0.25 + 0.3 * nrng.random(160), DIM)
                text(f, "NO SIGNAL", px + PWd / 2, py + PHd / 2 + 30, size=40, color=DIM, a=0.55)
                continue
            k = ease_back(clamp(s / 0.55))
            side = -1 if px < 960 else 1
            jit = 14 * math.sin(t * 83 + i) * clamp(1 - s / 0.35)
            if s_c > 0 and i != crit:
                jit += 9 * math.sin(t * 97 + i * 3) * math.exp(-s_c * 5)
            x = px + side * (1 - k) * 70 + jit
            y = py
            a = clamp(s / 0.25)
            is_c = i == crit
            cr = clamp(s_c / 0.25) if (is_c and s_c > 0) else 0
            blink = 1 if (t * 3) % 1 < 0.55 else 0.35
            pc = RED if cr > 0 else (mix(c_, GOLD, warn) if is_c and warn > 0 else c_)
            glow_a = (0.5 + 0.5 * pulse) * cr + (0.35 * warn * blink if is_c else 0) + 0.15 * pulse
            # connector to the planet
            ex = x + (PWd if side < 0 else 0)
            ey = y + PHd / 2
            ang = math.atan2(ey - cy, ex - cx)
            tx, ty = cx + math.cos(ang) * (R + 60), cy + math.sin(ang) * (R + 60)
            ca = a * f.prog(shown_at[i] + 0.3, 0.4)
            if ca > 0:
                mxp = ex - side * 50
                cpath = line_path([(ex, ey), (mxp, ey), (lerp(mxp, tx, ca), lerp(ey, ty, ca))])
                f.c.drawPath(cpath, paint(pc, 0.55 * ca, stroke=2.5))
                f.c.drawCircle(ex, ey, 6, paint(pc, ca))
                if ca >= 1:
                    f.c.drawCircle(tx, ty, 5, paint(pc, 1))
                    for q in range(2 if cr else 1):  # data packets travelling to the planet
                        ph = (t * (1.6 if cr else 0.8) + q * 0.5 + i * 0.27) % 1
                        if ph < 0.4:
                            qx, qy = lerp(ex, mxp, ph / 0.4), ey
                        else:
                            qx, qy = lerp(mxp, tx, (ph - 0.4) / 0.6), lerp(ey, ty, (ph - 0.4) / 0.6)
                        soft_light(f, qx, qy, 16, pc, 0.9)
            _panel(f, x, y, PWd, PHd, pc, a=a, glow_a=glow_a)
            if cr > 0:  # hazard stripes along the top
                f.c.save()
                f.c.clipRect(skia.Rect.MakeXYWH(x + 4, y + 4, PWd - 8, 16))
                off = (t * 80) % 40
                for q in range(-1, PWd // 20 + 2):
                    xx = x + q * 40 - off
                    f.c.drawPath(_path([(0, 0), (20, 0), (36, 16), (16, 16)], xx, y + 4, 1), paint(RED, 0.85 * cr))
                f.c.restore()
            ia = a * clamp((s - 0.2) / 0.3)
            if ia <= 0:
                continue
            label = pn.get("label", "").upper()
            text(f, label, x + 30, y + 58, size=32, color=pc, align="left", weight="semibold", a=ia)
            if cr > 0:
                _chip(f, "CRITICAL", x + PWd - 26, y + 56, RED, a=ia * blink, filled=True)
            elif is_c and warn > 0:
                _chip(f, "WARNING", x + PWd - 26, y + 56, GOLD, a=ia * warn * blink)
            else:
                _chip(f, "NOMINAL", x + PWd - 26, y + 56, GREEN, a=ia * 0.85)
            val = float(pn.get("value", 50))
            vmax = float(pn.get("max", val * 1.6 if val > 0 else 100))
            cv = p("critical_value")
            pk = pn.get("kind", "gauge")
            if cv is None:
                cv = {"gauge": vmax * 0.97, "ring": val * 0.25, "sparkline": val * 2.2, "counter": val * 0.5}.get(pk, val * 2)
            cv = float(cv)
            live = val + (vmax if pk in ("gauge", "ring") else abs(val)) * 0.012 * _noise1(t, i * 1.7)
            if is_c and s_c > -1.8:
                live += (cv - val) * 0.08 * clamp((s_c + 1.8) / 1.8)  # the creep before it fails
            if is_c and s_c > 0:
                live = lerp(live, cv + (vmax if pk in ("gauge", "ring") else abs(cv)) * 0.01 * _noise1(t * 3, i),
                            ease_out(s_c / 0.8))
            grow = ease_out(clamp((s - 0.25) / 1.2))
            unit = pn.get("unit", "")
            ccol = RED if cr > 0 else INK
            if pk == "gauge":
                gx, gy, gr = x + PWd / 2, y + 205, 112
                oval = skia.Rect.MakeLTRB(gx - gr, gy - gr, gx + gr, gy + gr)
                for z0, z1, zc in ((0, 0.6, GREEN), (0.6, 0.85, GOLD), (0.85, 1.0, RED)):
                    f.c.drawArc(oval, 150 + 240 * z0, 240 * (z1 - z0), False, paint(zc, 0.55 * ia, stroke=10,
                                                                                  cap_round=False))
                tp = skia.Path()
                for q in range(25):
                    a_ = math.radians(150 + 240 * q / 24)
                    l = 16 if q % 4 == 0 else 8
                    tp.moveTo(gx + math.cos(a_) * (gr - 12), gy + math.sin(a_) * (gr - 12))
                    tp.lineTo(gx + math.cos(a_) * (gr - 12 - l), gy + math.sin(a_) * (gr - 12 - l))
                f.c.drawPath(tp, paint(INK, 0.6 * ia, stroke=2))
                fr = clamp(live / vmax if vmax else 0) * grow
                a_ = math.radians(150 + 240 * fr)
                nx, ny = gx + math.cos(a_) * (gr - 20), gy + math.sin(a_) * (gr - 20)
                f.c.drawLine(gx, gy, nx, ny, paint(pc, 0.5 * ia, stroke=10, blur=6, add=True))
                f.c.drawLine(gx, gy, nx, ny, paint("#ffffff", ia, stroke=4))
                f.c.drawCircle(gx, gy, 10, paint(pc, ia))
                text(f, f"{_fmt(live * grow, val)}{unit}", gx, y + PHd - 26, size=44, color=ccol, a=ia,
                     glow_color=RED if cr else None)
            elif pk == "sparkline":
                ax0, ay0, aw, ah = x + 30, y + 110, PWd - 60, PHd - 170
                npt = 60
                j = np.arange(npt)
                ts = t - (npt - 1 - j) / 6.0
                ser = val * (1 + 0.035 * (np.sin(ts * 1.9 + i) * 0.6 + np.sin(ts * 4.7 + i * 2) * 0.4))
                if is_c:
                    ser = ser + (cv - val) * 0.08 * np.clip((ts - (ct - 1.8)) / 1.8, 0, 1)
                    ser = ser + (cv - ser) * np.clip((ts - ct) / 1.0, 0, 1) ** 1.5
                lo_v = min(val * 0.85, float(ser.min()))
                hi_v = max(val * 1.15, float(ser.max()) * 1.05)
                vis_n = max(2, int(npt * grow))
                xs = ax0 + aw * j[:vis_n] / (npt - 1)
                ys = ay0 + ah - ah * (ser[:vis_n] - lo_v) / (hi_v - lo_v)
                for q in range(4):
                    gy_ = ay0 + ah * q / 3
                    f.c.drawLine(ax0, gy_, ax0 + aw, gy_, paint(INK, 0.08 * ia, stroke=1))
                pts = list(zip(xs.tolist(), ys.tolist()))
                area = line_path(pts + [(pts[-1][0], ay0 + ah), (pts[0][0], ay0 + ah)])
                f.c.drawPath(area, _vshade(ay0, ay0 + ah, [pc, pc], None, 0.0) if False else
                             skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
                                 [skia.Point(0, ay0), skia.Point(0, ay0 + ah)], [col(pc, 0.35 * ia), col(pc, 0)])))
                lp = line_path(pts)
                f.c.drawPath(lp, paint(pc, 0.35 * ia, stroke=10, blur=5, add=True))
                f.c.drawPath(lp, paint(pc, ia, stroke=3))
                glow(f, pts[-1][0], pts[-1][1], 7, pc, ia)
                text(f, f"{_fmt(float(ser[vis_n - 1]), val)}{unit}", x + PWd - 30, y + PHd - 24, size=44,
                     color=ccol, align="right", a=ia, glow_color=RED if cr else None)
                text(f, "LIVE FEED", x + 30, y + PHd - 26, size=33, color=DIM, align="left", weight="medium", a=ia)
            elif pk == "counter":
                rate = float(pn.get("rate", max(1.0, abs(val) * 1e-5)))
                cur = (val * grow + rate * max(s - 1.45, 0)) if not (is_c and s_c > 0) else live
                digits = f"{cur:,.0f}"
                size = min(72, (PWd - 70) / (len(digits) * 0.6))
                cw = size * 0.6
                total_w = cw * len(digits)
                x_ = x + PWd / 2 - total_w / 2
                for q, ch in enumerate(digits):
                    roll = ch.isdigit() and q >= len(digits) - 3 and grow >= 1
                    yoff = 6 * math.sin(t * 40 + q) if roll else 0
                    text(f, ch, x_ + cw * (q + 0.5), y + 205 + yoff, size=size, color=ccol, a=ia,
                         glow_color=pc if q == len(digits) - 1 else None)
                f.c.drawLine(x + 40, y + 228, x + PWd - 40, y + 228, paint(pc, 0.4 * ia, stroke=2))
                text(f, f"+{_short(rate)} / sec{_unit(unit)}" if not cr else "FALLING", x + PWd / 2, y + PHd - 26,
                     size=33, color=DIM if not cr else RED, a=ia, weight="medium")
            else:  # ring
                rx, ry, rr_ = x + PWd / 2, y + 190, 88
                oval = skia.Rect.MakeLTRB(rx - rr_, ry - rr_, rx + rr_, ry + rr_)
                tp = paint(INK, 0.14 * ia, stroke=16, cap_round=False)
                tp.setPathEffect(skia.DashPathEffect.Make([10, 4], 0))
                f.c.drawArc(oval, -90, 360, False, tp)
                fr = clamp(live / vmax if vmax else 0) * grow
                fp = paint(pc, ia, stroke=16, cap_round=False)
                fp.setPathEffect(skia.DashPathEffect.Make([10, 4], 0))
                f.c.drawArc(oval, -90, 360 * fr, False, fp)
                f.c.drawArc(oval, -90, 360 * fr, False, paint(pc, 0.3 * ia, stroke=26, blur=8, add=True))
                inner = paint(pc, 0.5 * ia, stroke=2)
                inner.setPathEffect(skia.DashPathEffect.Make([6, 10], t * 30))
                f.c.drawCircle(rx, ry, rr_ - 26, inner)
                text(f, f"{_fmt(live * grow, val)}{unit}", rx, ry + 16, size=44, color=ccol, a=ia,
                     glow_color=RED if cr else None)
                text(f, f"of {_fmt(vmax)}{unit}" if unit != "%" else "", rx, y + PHd - 14, size=33, color=DIM, a=ia,
                     weight="medium")
        if s_c > 0:
            particles(f, cx, cy, ct, n=140, speed=(150, 800), life=(0.5, 1.6), size=(2, 5), color=RED,
                      key="dash-crit")
            shockwave(f, cx, cy, ct, speed=1200, life=1.3, color=RED, width=20)
    # status line under the planet
    status_a = f.prog(0.5, 0.5)
    if s_c > 0:
        st = f"{panels[crit].get('label', 'SYSTEM').upper()} CRITICAL" if n else "CRITICAL"
        text(f, st, cx, 868, size=40, color=RED, a=status_a * (1 if (t * 3) % 1 < 0.6 else 0.4), glow_color=RED)
    elif warn > 0:
        text(f, "ANOMALY DETECTED", cx, 868, size=40, color=GOLD, a=status_a * (1 if (t * 3) % 1 < 0.6 else 0.4))
    else:
        text(f, "ALL SYSTEMS NOMINAL", cx, 868, size=40, color=GREEN, a=status_a * 0.9)
    _chrome(f, c_ if s_c <= 0 else RED, "PLANET STATUS", title,
            readouts=[(f"SYNC {min(99.9, 60 + t * 9):.1f}%", DIM)])
    if s_c > 0:
        f.c.drawPaint(paint(RED, 0.10 * (0.5 + 0.5 * math.sin(t * 8)) * clamp(s_c / 0.3)))
    flash(f, ct, dur=0.45, color=RED, peak=0.45)
    slam_text(f, p("slam", "CRITICAL"), 960, 548, ct + 0.05, size=160, glow_color=RED, hold=1.5, snap=False)
