"""Storyboard sequences: multi-beat cinematic set pieces that tell a small story in one scene."""

import math
import re
from functools import lru_cache

import numpy as np
import skia

from esim.templates import BODY_KINDS, Sfx, accent, body, pick, rand, shot_camera, template, when
from esim.engine import *  # noqa: F401,F403


# ================================================================ shared helpers

def _beats(f, items, lo, hi):
    """Scene times for a list of {at} items: their word, or evenly spread from lo to hi (fractions)."""
    n = len(items)
    return [when(f, it.get("at") if isinstance(it, dict) else None, lo + (hi - lo) * (i / max(n - 1, 1)))
            for i, it in enumerate(items)]


def _sfx_at(item, fallback_s):
    """An Sfx 'at' for a param item: its word, or a seconds guess when it has none."""
    at = item.get("at") if isinstance(item, dict) else None
    return at if at is not None else fallback_s


def _fit(s, max_w, size, weight="bold", min_size=30, max_lines=2):
    """Wrap text into at most max_lines lines no wider than max_w, shrinking it (not below min_size) to fit."""
    words = str(s).split() or [""]
    while True:
        fnt = font(size, weight)
        lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if not cur or fnt.measureText(t) <= max_w:
                cur = t
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        if (len(lines) <= max_lines and all(fnt.measureText(ln) <= max_w for ln in lines)) or size <= min_size:
            return lines[:max_lines + 1], size
        size -= 2


def _rrect(x, y, w, h, r):
    return skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), r, r)


def _panel_box(f, x, y, w, h, color, a=1.0, fill="#05080f", fill_a=0.78, radius=18, brackets=True):
    """A HUD card: dark glassy fill, a thin border and bright corner brackets."""
    c = f.c
    rr = _rrect(x, y, w, h, radius)
    sh = skia.GradientShader.MakeLinear([skia.Point(x, y), skia.Point(x, y + h)],
                                        [col(mix(fill, color, 0.12), fill_a * a), col(fill, fill_a * a)])
    c.drawRRect(rr, skia.Paint(AntiAlias=True, Shader=sh))
    c.drawRRect(rr, paint(color, 0.45 * a, stroke=2))
    if brackets:
        L = min(34, w * 0.2, h * 0.3)
        bp = paint(color, 0.95 * a, stroke=4)
        for cx, cy, dx, dy in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
            c.drawLine(cx, cy + dy * L, cx, cy, bp)
            c.drawLine(cx, cy, cx + dx * L, cy, bp)


def _parallax_stars(f, camx, camy, n=380, key="pstars", alpha=1.0, depth_k=0.35, color_mix=True):
    """Stars that slide with the camera at different depths (near ones move more)."""
    rng = f.rng(key)
    x0, y0 = rng.random(n) * W, rng.random(n) * H
    depth = rng.random(n) ** 2
    xs = (x0 - (camx - W / 2) * depth * depth_k) % W
    ys = (y0 - (camy - H / 2) * depth * depth_k * 0.6) % H
    tw = 0.75 + 0.25 * np.sin(f.t * (0.6 + rng.random(n) * 2.2) + rng.random(n) * 6.28)
    tint = rng.random(n)
    sel = tint > 0.92 if color_mix else np.zeros(n, bool)
    dots(f, xs[~sel], ys[~sel], 0.6 + depth[~sel] * 2.1, (0.25 + 0.7 * depth[~sel]) * tw[~sel] * alpha, INK)
    dots(f, xs[sel], ys[sel], 0.6 + depth[sel] * 2.1, (0.25 + 0.7 * depth[sel]) * tw[sel] * alpha, CYAN)


def _human(v):
    """13800000000 -> '13.8 billion', 2500 -> '2,500', 3.25 -> '3.3'."""
    av = abs(v)
    for div, name in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if av >= div:
            s = f"{v / div:.1f}".rstrip("0").rstrip(".")
            return f"{s} {name}"
    if av >= 100:
        return f"{v:,.0f}"
    if av >= 10:
        return f"{v:.0f}"
    return f"{v:.1f}".rstrip("0").rstrip(".") if av > 0 else "0"


_MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9, "trillion": 1e12}


def _parse_num(s):
    """The first number in a string, with 'million'/'billion' words applied: '~4.6 billion yrs' -> 4.6e9."""
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"(-?\d[\d,]*\.?\d*)\s*(thousand|million|billion|trillion|bn)?", str(s or ""), re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    if m.group(2):
        v *= _MULT[m.group(2).lower()]
    return v


def _split_num(s):
    """'24.1 km/s' -> ('', 24.1, 1 decimal, ' km/s'), so a value can count up while keeping its text."""
    m = re.match(r"^(\D*?)(-?\d[\d,]*\.?\d*)(.*)$", str(s))
    if not m:
        return None
    num = m.group(2)
    dec = len(num.split(".")[1]) if "." in num else 0
    return m.group(1), float(num.replace(",", "")), dec, m.group(3), "," in num


def _count_text(s, k):
    """The value string s with its number counted up to fraction k."""
    sp = _split_num(s)
    if not sp or k >= 1:
        return str(s)
    pre, v, dec, post, commas = sp
    fmt = f"{{:{',' if commas else ''}.{dec}f}}"
    return pre + fmt.format(v * k) + post


# ---------------------------------------------------------------- icons

_ICON_WORDS = [
    ("snow", ["freez", "frozen", "ice", "icy", "snow", "cold", "winter", "glacier", "chill"]),
    ("flame", ["fire", "burn", "heat", "hot", "boil", "melt", "flame", "scorch", "cook", "roast"]),
    ("dark", ["dark", "night", "shadow", "blind", "black", "dim"]),
    ("orbit", ["orbit", "straight", "fling", "path", "drift", "spin", "fall", "escape"]),
    ("atom", ["atom", "fusion", "nuclear", "particle", "quantum", "radiat", "element", "hydrogen", "helium"]),
    ("rocket", ["rocket", "launch", "ship", "probe", "craft", "mission", "fly", "travel", "voyage"]),
    ("life", ["life", "cell", "bacteri", "alive", "dna", "evolv", "species", "plant", "ocean", "creature"]),
    ("bang", ["explo", "boom", "bang", "supernova", "collid", "impact", "deton", "crash", "blast", "burst"]),
    ("storm", ["climate", "weather", "storm", "season", "rain", "wind", "hurrican", "chaos", "haywire", "swing"]),
    ("wave", ["wave", "light", "signal", "sound", "gravit", "tide", "radio", "pulse"]),
    ("warn", ["danger", "warn", "collapse", "extinct", "die", "death", "end", "doom", "lost"]),
]
_GENERIC_BODIES = {"rocky", "gas", "ice", "lava", "asteroid"}


def _icon_for(s):
    words = [w.strip(".,!?:;'\"()").lower() for w in str(s).replace("'s", " ").replace("-", " ").split()]
    for w in words:
        for cand in (w, w[:-1] if w.endswith("s") else None):
            if cand and cand in BODY_KINDS and cand not in _GENERIC_BODIES:
                return ("body", cand)
    if any(w in ("you", "today", "now", "here", "us", "humans", "humanity") for w in words):
        return ("body", "earth")
    if "milky" in words or "galaxy" in words or "galaxies" in words:
        return ("galaxy", None)
    for name, keys in _ICON_WORDS:
        if any(w.startswith(k) for w in words for k in keys):
            return (name, None)
    return ("clock", None)


def _icon(f, icon, x, y, s, color, a=1.0):
    """A small procedural icon in a circle of radius s: a body, or a drawn glyph."""
    if a <= 0.01:
        return
    kind, arg = icon
    c = f.c
    lw = max(2.0, s * 0.09)
    p_ = paint(color, a, stroke=lw)
    if kind == "body":
        if arg in ("sun", "star", "red_giant", "white_dwarf", "neutron_star"):
            body(f, arg, x, y, s * 0.55, alpha=a)
        elif arg == "black_hole":
            body(f, arg, x, y, s * 0.32, alpha=a)
        else:
            body(f, arg, x, y, s * 0.78, alpha=a, light=(-0.6, -0.4, 0.7))
        return
    if kind == "snow":
        for k in range(6):
            ang = k * math.pi / 3 + 0.2 * math.sin(f.t * 0.5)
            ex, ey = x + math.cos(ang) * s * 0.85, y + math.sin(ang) * s * 0.85
            c.drawLine(x, y, ex, ey, p_)
            for side in (-1, 1):
                bx, by = x + math.cos(ang) * s * 0.52, y + math.sin(ang) * s * 0.52
                ba = ang + side * 0.7
                c.drawLine(bx, by, bx + math.cos(ba) * s * 0.28, by + math.sin(ba) * s * 0.28, p_)
        soft_light(f, x, y, s * 1.2, color, 0.25 * a)
    elif kind == "flame":
        fl = 1 + 0.07 * math.sin(f.t * 13) + 0.04 * math.sin(f.t * 21)
        for scale_, colr in ((1.0, "#ff5a2a"), (0.62, GOLD), (0.32, "#fff3c4")):
            ss = s * scale_
            path = skia.Path()
            top = y + s * 0.8 - ss * 1.7 * fl
            path.moveTo(x, top)
            path.cubicTo(x + ss * 0.75, y - ss * 0.2, x + ss * 0.7, y + s * 0.8, x, y + s * 0.8)
            path.cubicTo(x - ss * 0.7, y + s * 0.8, x - ss * 0.75, y - ss * 0.2, x, top)
            c.drawPath(path, paint(colr, a))
        soft_light(f, x, y, s * 1.6, "#ff7a2a", 0.35 * a)
    elif kind == "dark":
        p1 = skia.Path()
        p1.addCircle(x, y, s * 0.72)
        p2 = skia.Path()
        p2.addCircle(x + s * 0.36, y - s * 0.2, s * 0.62)
        cres = skia.Op(p1, p2, skia.PathOp.kDifference_PathOp)
        c.drawPath(cres, paint(color, a))
        rng = f.rng("icon-dark")
        for i in range(4):
            sx, sy = x + (rng.random() - 0.1) * s * 0.9, y + (rng.random() - 0.6) * s * 0.9
            c.drawCircle(sx, sy, 2 + 2 * rng.random(), paint(INK, a * (0.5 + 0.5 * math.sin(f.t * 3 + i))))
    elif kind == "orbit":
        c.save()
        c.translate(x, y)
        c.rotate(-22)
        c.drawOval(skia.Rect.MakeLTRB(-s * 0.9, -s * 0.38, s * 0.9, s * 0.38), paint(color, 0.6 * a, stroke=lw * 0.7))
        ang = f.t * 1.4
        c.drawCircle(math.cos(ang) * s * 0.9, math.sin(ang) * s * 0.38, s * 0.13, paint(INK, a))
        c.restore()
        c.drawCircle(x, y, s * 0.24, paint(GOLD, a))
        soft_light(f, x, y, s * 0.7, GOLD, 0.4 * a)
    elif kind == "atom":
        for k in range(3):
            c.save()
            c.translate(x, y)
            c.rotate(k * 60 + f.t * 20)
            c.drawOval(skia.Rect.MakeLTRB(-s * 0.85, -s * 0.3, s * 0.85, s * 0.3), p_)
            e = f.t * 2.2 + k * 2.1
            c.drawCircle(math.cos(e) * s * 0.85, math.sin(e) * s * 0.3, s * 0.08, paint(INK, a))
            c.restore()
        c.drawCircle(x, y, s * 0.15, paint(color, a))
    elif kind == "rocket":
        c.save()
        c.translate(x, y)
        c.rotate(35)
        hull = skia.Path()
        hull.moveTo(0, -s * 0.9)
        hull.cubicTo(s * 0.35, -s * 0.55, s * 0.3, s * 0.3, s * 0.22, s * 0.5)
        hull.lineTo(-s * 0.22, s * 0.5)
        hull.cubicTo(-s * 0.3, s * 0.3, -s * 0.35, -s * 0.55, 0, -s * 0.9)
        c.drawPath(hull, paint(INK, a))
        c.drawCircle(0, -s * 0.25, s * 0.12, paint(color, a))
        for side in (-1, 1):
            fin = skia.Path()
            fin.moveTo(side * s * 0.24, s * 0.1)
            fin.lineTo(side * s * 0.5, s * 0.6)
            fin.lineTo(side * s * 0.2, s * 0.48)
            fin.close()
            c.drawPath(fin, paint(color, a))
        fl = s * (0.35 + 0.12 * math.sin(f.t * 19))
        flame_p = skia.Path()
        flame_p.moveTo(-s * 0.14, s * 0.52)
        flame_p.lineTo(0, s * 0.52 + fl)
        flame_p.lineTo(s * 0.14, s * 0.52)
        flame_p.close()
        c.drawPath(flame_p, paint(GOLD, a))
        c.restore()
    elif kind == "life":
        path = skia.Path()
        for i in range(41):
            ang = i / 40 * 2 * math.pi
            rr = s * 0.78 * (1 + 0.06 * math.sin(ang * 5 + f.t * 2))
            pt = (x + math.cos(ang) * rr, y + math.sin(ang) * rr)
            path.moveTo(*pt) if i == 0 else path.lineTo(*pt)
        path.close()
        c.drawPath(path, paint(color, 0.18 * a))
        c.drawPath(path, p_)
        c.drawCircle(x + s * 0.12, y - s * 0.08, s * 0.26, paint(color, 0.8 * a))
        rng = f.rng("icon-life")
        for i in range(6):
            ang, rr = rng.random() * 6.28, s * (0.35 + 0.3 * rng.random())
            c.drawCircle(x + math.cos(ang + f.t * 0.3) * rr, y + math.sin(ang + f.t * 0.3) * rr, s * 0.06,
                         paint(INK, 0.8 * a))
    elif kind == "bang":
        path = skia.Path()
        for i in range(21):
            ang = i / 20 * 2 * math.pi + f.t * 0.3
            rr = s * (0.9 if i % 2 == 0 else 0.45) * (1 + 0.05 * math.sin(f.t * 9 + i))
            pt = (x + math.cos(ang) * rr, y + math.sin(ang) * rr)
            path.moveTo(*pt) if i == 0 else path.lineTo(*pt)
        path.close()
        c.drawPath(path, paint(GOLD, a))
        c.drawCircle(x, y, s * 0.3, paint("#fff6d8", a))
        soft_light(f, x, y, s * 1.5, "#ff7a2a", 0.4 * a)
    elif kind == "storm":
        for cxo, cyo, cr in ((-0.32, -0.12, 0.32), (0.05, -0.32, 0.4), (0.38, -0.08, 0.3), (0.0, 0.02, 0.32)):
            c.drawCircle(x + cxo * s, y + cyo * s, cr * s, paint(INK, 0.9 * a))
        bolt = skia.Path()
        for j, (bx, by) in enumerate(((0.08, 0.12), (-0.18, 0.5), (0.04, 0.48), (-0.12, 0.92), (0.3, 0.38), (0.08, 0.4), (0.22, 0.12))):
            (bolt.moveTo if j == 0 else bolt.lineTo)(x + bx * s, y + by * s)
        bolt.close()
        flick = 0.6 + 0.4 * (math.sin(f.t * 17) > 0.2)
        c.drawPath(bolt, paint(GOLD, a * flick))
        soft_light(f, x, y + s * 0.5, s * 0.9, GOLD, 0.35 * a * flick)
    elif kind == "wave":
        pts = [(x - s * 0.9 + s * 1.8 * i / 30, y + s * 0.4 * math.sin(i / 30 * 4 * math.pi - f.t * 5)) for i in range(31)]
        c.drawPath(line_path(pts), p_)
        c.drawPath(line_path(pts), paint(color, 0.3 * a, stroke=lw * 3, add=True))
    elif kind == "warn":
        tri = skia.Path()
        tri.moveTo(x, y - s * 0.8)
        tri.lineTo(x + s * 0.85, y + s * 0.65)
        tri.lineTo(x - s * 0.85, y + s * 0.65)
        tri.close()
        c.drawPath(tri, p_)
        c.drawLine(x, y - s * 0.3, x, y + s * 0.2, paint(color, a, stroke=lw * 1.3))
        c.drawCircle(x, y + s * 0.43, lw * 0.8, paint(color, a))
    elif kind == "galaxy":
        rng = f.rng("icon-gal")
        n = 160
        d = rng.random(n) ** 0.7
        ang = rng.integers(0, 2, n) * math.pi + d * 4 + rng.normal(0, 0.25, n) + f.t * 0.2
        dots(f, x + np.cos(ang) * d * s * 0.9, y + np.sin(ang) * d * s * 0.5, 1 + (1 - d) * 1.5, (1.1 - d) * a,
             color, add=True)
        soft_light(f, x, y, s * 0.6, GOLD, 0.6 * a)
    else:  # clock
        c.drawCircle(x, y, s * 0.8, p_)
        for k in range(12):
            ang = k * math.pi / 6
            c.drawLine(x + math.cos(ang) * s * 0.62, y + math.sin(ang) * s * 0.62,
                       x + math.cos(ang) * s * 0.72, y + math.sin(ang) * s * 0.72, paint(color, 0.7 * a, stroke=lw * 0.6))
        for length, speed, wd in ((0.55, 1.6, 1.0), (0.38, 0.13, 1.3)):
            ang = f.t * speed - math.pi / 2
            c.drawLine(x, y, x + math.cos(ang) * s * length, y + math.sin(ang) * s * length, paint(INK, a, stroke=lw * wd))
        c.drawCircle(x, y, lw, paint(INK, a))


def _zoom_blur(f, amount, cx=None, cy=None, copies=3):
    """Real radial motion blur: re-draw what's on the canvas so far, scaled about the centre, a few times."""
    if amount < 0.004:
        return
    surf = f.c.getSurface()
    if surf is None:
        return
    img = surf.makeImageSnapshot()
    sw, sh = img.width(), img.height()
    px = (cx if cx is not None else W / 2) / W * sw
    py = (cy if cy is not None else H / 2) / H * sh
    f.c.save()
    f.c.resetMatrix()
    for k in range(1, copies + 1):
        s = 1 + amount * k / copies
        rect = skia.Rect.MakeLTRB(px - px * s, py - py * s, px + (sw - px) * s, py + (sh - py) * s)
        f.c.drawImageRect(img, rect, skia.SamplingOptions(skia.FilterMode.kLinear),
                          skia.Paint(Alphaf=0.5 / (k + 0.6)))
    f.c.restore()


# ================================================================ 1. chain reaction

_CHAIN_DEFAULT = [{"text": "Sun vanishes"}, {"text": "Orbit straightens"}, {"text": "Total darkness"},
                  {"text": "Deep freeze"}]


def _chain_sfx(p):
    steps = p("steps") or _CHAIN_DEFAULT
    out = [Sfx("pop", _sfx_at(s, 0.6 + 1.36 * i), gain_db=-3) for i, s in enumerate(steps[:-1][:2])]
    last = steps[-1].get("at")
    out += [Sfx("riser", last if last is not None else "end", offset=-1.5 if last is not None else -2.8, dur=1.5),
            Sfx("impact", last if last is not None else "end", offset=0 if last is not None else -1.3),
            Sfx("808", last if last is not None else "end", offset=0 if last is not None else -1.3)]
    return out


@template("chain_reaction", kind="cinematic", sfx=_chain_sfx)
def chain_reaction(f, p):
    """A cause-and-effect chain told as one tracking shot: glowing event nodes joined by arrows. Each node lights up
    on its word as an energy pulse races down the arrow into it, the camera tracking along the chain; the last node
    detonates (flash, shockwave, shattered ring) and the camera pulls back to show the whole chain lit.
    Great for "and then... and then..." consequences (e.g. Sun vanishes -> orbit straightens -> darkness -> freeze).
    params: steps [{text, at, kind}] (2-6 short events; at = narration word it lights on; kind = optional body
    drawn in the node, otherwise an icon is chosen from the text), title (small HUD heading, default "CHAIN REACTION"),
    payoff (optional slam text on the final detonation), layout (line|zigzag|arc), color"""
    steps = p("steps") or _CHAIN_DEFAULT
    n = max(len(steps), 1)
    c_ = accent(f, p, default=["cyan", "gold", "pink", "orange", "purple"])
    hot = mix(c_, "#ffffff", 0.35)
    times = _beats(f, steps, 0.1, 0.78)
    layout = p("layout") or pick(f, "chain_layout", ["line", "zigzag", "arc"])
    span = 1520 if n > 2 else 1000
    xs = [960 - span / 2 + span * i / max(n - 1, 1) for i in range(n)] if n > 1 else [960]
    if layout == "zigzag":
        ys = [420 if i % 2 == 0 else 570 for i in range(n)]
    elif layout == "arc":
        ys = [560 - 150 * math.sin(math.pi * i / max(n - 1, 1)) for i in range(n)]
    else:
        ys = [470 for _ in range(n)]
    gap = span / max(n - 1, 1)
    R = min(100, gap * 0.27)
    beat = f.beat_pulse()

    # ---- camera: track the node that's lighting up, then pull back on the payoff
    fi = sum(f.prog(times[i] - 0.75, 0.8) for i in range(1, n))
    i0 = min(int(fi), max(n - 2, 0))
    fr = fi - i0
    i1 = min(i0 + 1, n - 1)
    fx, fy = lerp(xs[i0], xs[i1], fr), lerp(ys[i0], ys[i1], fr)
    pull = f.prog(times[-1] + 0.7, 1.8)
    s_last = f.t - times[-1]
    # card geometry first, so the camera can keep every card and node inside the safe area (y 170..900)
    cw = min(gap * 0.92, 470)
    cards = []
    for i, st in enumerate(steps):
        lines, size = _fit(st.get("text", ""), cw - 36, 44 if n <= 4 else 38, "bold", 30, 2)
        ch = len(lines) * size * 1.18 + 30
        above = layout == "zigzag" and i % 2 == 0
        top = (ys[i] - R * 1.32 - 52 - ch) if above else (ys[i] + R * 1.32 + 28)
        cards.append((lines, size, ch, top))
    c_top = min(min(cd[3] for cd in cards), min(ys) - R * 1.32 - 50)
    c_bot = max(max(cd[3] + cd[2] for cd in cards), max(ys) + R * 1.3)
    mid_y = (c_top + c_bot) / 2
    z_track = min(1.2, 600 / (c_bot - c_top))
    z_fit = min(0.92, 600 / (c_bot - c_top), 1450 / (span + cw))
    zoom = lerp(lerp(z_track * 1.08, z_track, f.prog(0, max(times[0], 0.3))), z_fit, pull) * (1 + 0.012 * beat)
    if s_last > 0:
        zoom *= 1 + 0.06 * math.exp(-s_last * 4)
    cx, cy = lerp(fx, 960, pull), mid_y - 5
    shake = 24 * math.exp(-s_last * 3.2) if s_last > 0 else 0.0

    # ---- background: deep space with parallax, nebula tinted by the accent
    gradient_bg(f, "#060914", "#010208")
    nebula_glow(f, key="chain-neb", alpha=0.28)
    soft_light(f, W / 2, H * 0.45, 900, c_, 0.06 + 0.04 * beat)
    _parallax_stars(f, cx, cy, n=360, key="chain-stars")

    # where is the energy right now? (for the grid glow)
    heads = []
    with camera(f, cx, cy, zoom=zoom, shake=shake):
        # energy grid: faint dots that brighten near lit nodes and the travelling pulse
        gx, gy = np.meshgrid(np.arange(-300, 2260, 64, dtype=np.float32), np.arange(40, 1060, 64, dtype=np.float32))
        gx, gy = gx.ravel(), gy.ravel()
        boost = np.zeros_like(gx)
        for i in range(n):
            lit = clamp((f.t - times[i]) / 0.4)
            if lit > 0:
                d2 = (gx - xs[i]) ** 2 + (gy - ys[i]) ** 2
                boost += lit * np.exp(-d2 / (2 * (R * 2.6) ** 2)) * (0.6 + 0.4 * beat)

        # arrows between nodes, with the pulse travelling down them
        for i in range(1, n):
            x0, y0, x1, y1 = xs[i - 1], ys[i - 1], xs[i], ys[i]
            ang = math.atan2(y1 - y0, x1 - x0)
            sx_, sy_ = x0 + math.cos(ang) * (R * 1.32), y0 + math.sin(ang) * (R * 1.32)
            ex_, ey_ = x1 - math.cos(ang) * (R * 1.4), y1 - math.sin(ang) * (R * 1.4)
            bulge = (-1 if i % 2 else 1) * min(70, gap * 0.12)
            mx, my = (sx_ + ex_) / 2 - math.sin(ang) * bulge, (sy_ + ey_) / 2 + math.cos(ang) * bulge
            path = skia.Path()
            path.moveTo(sx_, sy_)
            path.quadTo(mx, my, ex_, ey_)
            base = paint(DIM, 0.35, stroke=3)
            base.setPathEffect(skia.DashPathEffect.Make([10, 12], 0))
            f.c.drawPath(path, base)
            k = clamp((f.t - (times[i] - 0.7)) / 0.7) ** 1.6
            if k <= 0:
                continue
            draw_partial(f, path, k, paint(c_, 0.22, stroke=18, add=True))
            draw_partial(f, path, k, paint(c_, 0.9, stroke=4))
            m = skia.PathMeasure(path, False)
            length = m.getLength()
            if k < 1:
                pos = m.getPosTan(length * k)
                if pos:
                    hx, hy = pos[0].x(), pos[0].y()
                    heads.append((hx, hy))
                    glow(f, hx, hy, 16, hot)
                    soft_light(f, hx, hy, 140, c_, 0.35)
            else:
                flow = paint("#ffffff", 0.55, stroke=3, add=True)
                flow.setPathEffect(skia.DashPathEffect.Make([6, 34], -f.t * 120))
                f.c.drawPath(path, flow)
                pos = m.getPosTan(length)
                if pos:
                    (pt, tn) = pos
                    ta = math.atan2(tn.y(), tn.x())
                    head = skia.Path()
                    head.moveTo(pt.x() + math.cos(ta) * 14, pt.y() + math.sin(ta) * 14)
                    head.lineTo(pt.x() + math.cos(ta + 2.5) * 20, pt.y() + math.sin(ta + 2.5) * 20)
                    head.lineTo(pt.x() + math.cos(ta - 2.5) * 20, pt.y() + math.sin(ta - 2.5) * 20)
                    head.close()
                    f.c.drawPath(head, paint(c_, 1))
        for hx, hy in heads:
            boost += np.exp(-((gx - hx) ** 2 + (gy - hy) ** 2) / (2 * 120.0 ** 2))
        dots(f, gx, gy, 1.6 + 1.4 * np.clip(boost, 0, 1), 0.07 + 0.6 * np.clip(boost, 0, 1), c_, add=True)

        # the nodes
        for i, st in enumerate(steps):
            x, y = xs[i], ys[i]
            s = f.t - times[i]
            lit = clamp(s / 0.3)
            final = i == n - 1
            blown = final and s > 0
            icon = ("body", st["kind"]) if st.get("kind") else _icon_for(st.get("text", ""))
            pop = 1 + 0.18 * math.exp(-max(s, 0) * 6) * (s > 0) + 0.03 * beat * lit
            r = R * pop
            ring_c = mix(DIM, c_, lit)
            soft_light(f, x, y, r * 2.8, c_, (0.18 + 0.12 * beat) * lit)
            if not blown:
                sh = skia.GradientShader.MakeRadial(skia.Point(x, y - r * 0.35), r * 1.25,
                                                    [col(mix("#1a2440", c_, 0.3 * lit)), col("#04060c")])
                f.c.drawCircle(x, y, r, skia.Paint(AntiAlias=True, Shader=sh))
                f.c.drawCircle(x, y, r, paint(ring_c, 0.5 + 0.5 * lit, stroke=3))
                dash = paint(ring_c, 0.35 + 0.5 * lit, stroke=2)
                dash.setPathEffect(skia.DashPathEffect.Make([18, 10], f.t * (30 + 60 * lit) * (1 if i % 2 else -1)))
                f.c.drawCircle(x, y, r * 1.22, dash)
                for k in range(36):  # tick ring, lit ticks sweep round as the node charges
                    a = k / 36 * 2 * math.pi - math.pi / 2
                    on = (k / 36) < clamp(s / 0.5) if s > 0 else False
                    f.c.drawLine(x + math.cos(a) * r * 1.08, y + math.sin(a) * r * 1.08,
                                 x + math.cos(a) * r * (1.15 if k % 3 else 1.19), y + math.sin(a) * r * (1.15 if k % 3 else 1.19),
                                 paint(c_ if on else DIM, 0.9 if on else 0.3, stroke=2))
                _icon(f, icon, x, y, r * 0.62, mix(DIM, c_, lit), 0.35 + 0.65 * lit)
                ring(f, x, y, r * 1.05, 6, c_, 0.6 * lit * (0.6 + 0.4 * beat))
            else:  # the last node shatters: ring shards fly out and the core burns white
                k = 1 - math.exp(-s * 2.2)
                for j in range(10):
                    a0 = j * 36 + rand(f, f"shard{j}", -8, 8)
                    a = math.radians(a0 + 18)
                    d = r * 0.2 + 520 * k * rand(f, f"shd{j}", 0.6, 1.2)
                    ox, oy = x + math.cos(a) * d, y + math.sin(a) * d
                    f.c.save()
                    f.c.translate(ox, oy)
                    f.c.rotate(s * rand(f, f"shr{j}", -200, 200))
                    f.c.drawArc(skia.Rect.MakeLTRB(-r, -r, r, r), -18, 30, False,
                                paint(c_, clamp(1.4 - s * 0.5), stroke=6))
                    f.c.restore()
                glow(f, x, y, r * (0.9 * math.exp(-s * 1.2) + 0.32), "#ffffff", max(clamp(1.3 - s * 0.35), 0.6))
                soft_light(f, x, y, r * 3.2, c_, 0.3 + 0.15 * beat)  # the burnt-out node keeps smouldering
                ring(f, x, y, r * (1.0 + 0.6 * k), 5, c_, 0.5 * (1 - 0.5 * k) + 0.2 * beat)
                _icon(f, icon, x, y, r * 0.62, INK, max(clamp(1 - s * 0.6), 0.5))
            if s > 0:
                shockwave(f, x, y, times[i], speed=520 if not final else 1300, life=0.9 if not final else 1.8,
                          color=c_, width=10 if not final else 28)
                if final:
                    shockwave(f, x, y, times[i] + 0.15, speed=800, life=1.8, color=INK, width=12)
                    particles(f, x, y, times[i], n=300, speed=(250, 1300), life=(0.6, 2.4), size=(2, 6), color=c_,
                              key="chain-boom")
                elif s < 1.0:
                    particles(f, x, y, times[i], n=50, speed=(80, 360), life=(0.3, 0.9), size=(1.5, 3.5), color=c_,
                              key=f"chain-p{i}")
            # index tag and the event card
            text(f, f"{i + 1:02d}", x, y - r * 1.32 - 14, size=30, color=c_ if lit else DIM, weight="semibold",
                 a=0.5 + 0.5 * lit)
            lines, size, ch, top = cards[i]
            card_pop = ease_back(clamp(s / 0.4)) if s > 0 else 0
            with layer(f, 0.55 + 0.45 * lit):
                f.c.save()
                f.c.translate(x, top + ch / 2)
                sc = lerp(0.92, 1.0, card_pop)
                f.c.scale(sc, sc)
                _panel_box(f, -cw / 2, -ch / 2, cw, ch, c_ if lit else DIM, a=1.0, fill_a=0.7)
                if s <= 0:
                    text(f, "• • •", 0, 12, size=40, color=DIM, a=0.6 + 0.3 * math.sin(f.t * 4 + i))
                else:
                    for li, ln in enumerate(lines):
                        yy = -ch / 2 + 15 + size * (li + 0.9) * 1.1
                        text(f, ln, 0, yy, size=size, color=INK, glow_color=c_ if final else None,
                             reveal=clamp((s - li * 0.12) / 0.35))
                f.c.restore()

    # ---- HUD (screen space)
    done = sum(1 for tt in times if f.t >= tt)
    text(f, (p("title") or "CHAIN REACTION").upper(), 190, 140, size=34, color=c_, align="left", weight="semibold")
    f.c.drawLine(190, 160, 190 + 300, 160, paint(c_, 0.5, stroke=2))
    text(f, f"T+ {f.t:05.1f} s", 190, 200, size=30, color=DIM, align="left", weight="semibold")
    text(f, f"STEP {max(done, 0)} / {n}", W - 190, 140, size=34, color=INK, align="right", weight="semibold")
    for i in range(n):  # step pips
        on = f.t >= times[i]
        px = W - 190 - (n - 1 - i) * 34
        f.c.drawCircle(px - 8, 178, 9, paint(c_ if on else DIM, 1 if on else 0.35))
        if on:
            soft_light(f, px - 8, 178, 26, c_, 0.4 + 0.3 * beat)
    if p("payoff"):
        slam_text(f, p("payoff").upper(), 960, 540, times[-1] + 0.1, size=170, glow_color=c_, snap=False, hold=1.6)
    flash(f, times[-1], dur=0.55, color="#ffffff", peak=0.85)


# ================================================================ 2. timeline journey

_TIMELINE_DEFAULT = [
    {"label": "Big Bang", "time_text": "0 years", "value": 0},
    {"label": "First stars ignite", "time_text": "~100 million years", "value": 1e8},
    {"label": "The Sun forms", "time_text": "9.2 billion years", "value": 9.2e9},
    {"label": "You are here", "time_text": "13.8 billion years", "value": 1.38e10},
]


@template("timeline_journey", kind="cinematic",
          sfx=lambda p: [Sfx("whoosh", "start", offset=0.1, gain_db=-4)]
          + [Sfx("tick", _sfx_at(e, 0.72 + 1.44 * i), gain_db=-2) for i, e in enumerate((p("events") or _TIMELINE_DEFAULT)[:-1][:2])]
          + [Sfx("riser", _sfx_at((p("events") or _TIMELINE_DEFAULT)[-1], 5.04), offset=-1.4, dur=1.4),
             Sfx("impact", _sfx_at((p("events") or _TIMELINE_DEFAULT)[-1], 5.04), gain_db=-3)])
def timeline_journey(f, p):
    """A flight along a glowing timeline: the camera races down a neon time-line over a perspective grid while a big
    counter runs (seconds, years, millions of years). Milestone panels with icons pop up as each is reached, the time
    scale visibly accelerates (a 'time warp' readout shows units per second), and the last milestone lands with a flash.
    Use for "8 minutes later... a year later... a million years later" stories, or the history of something.
    params: events [{label, time_text, at, value, kind}] (2-6; at = word its panel pops on; value = number in `unit`
    for the counter, read from time_text if missing; kind = optional body icon), unit (e.g. "years", "seconds",
    "years after the Big Bang"; counter caption), payoff (optional slam text on the last event), color"""
    events = p("events") or _TIMELINE_DEFAULT
    n = max(len(events), 1)
    c_ = accent(f, p, default=["cyan", "pink", "purple", "gold", "orange"])
    unit = p("unit") or ("years after the Big Bang" if events is _TIMELINE_DEFAULT else "")
    times = _beats(f, events, 0.12, 0.84)
    gap = 900.0
    ex = [i * gap for i in range(n)]
    beat = f.beat_pulse()
    LINE_Y = 640

    def cam_at(t):
        if t <= times[0]:
            return lerp(-200, 0, ease_out(t / max(times[0], 0.1)))
        for j in range(n - 1):
            if t < times[j + 1]:
                u = clamp((t - times[j]) / max(times[j + 1] - times[j], 0.1))
                return lerp(ex[j], ex[j + 1], 0.55 * u + 0.45 * ease_in_out(u))  # never fully stops
        return ex[-1] + 160 * ease_out((t - times[-1]) / 3.0)

    vals = [e.get("value") if e.get("value") is not None else _parse_num(e.get("time_text")) for e in events]
    numeric = all(v is not None for v in vals) and all(vals[i + 1] >= vals[i] for i in range(n - 1))

    def value_at(wx):
        if not numeric:
            return None
        if wx <= 0:
            return vals[0]
        j = min(int(wx // gap), n - 2) if n > 1 else 0
        if n == 1 or wx >= ex[-1]:
            return vals[-1]
        u = (wx - ex[j]) / gap
        a, b = vals[j], vals[j + 1]
        return a * (b / a) ** u if a > 0 and b > 0 else lerp(a, b, u)

    camx = cam_at(f.t)
    speed = (cam_at(f.t + 1 / 30) - cam_at(f.t - 1 / 30)) * 15  # px/s
    s_last = f.t - times[-1]
    zoom = 1.0 + 0.012 * beat + (0.05 * math.exp(-s_last * 4) if s_last > 0 else 0)

    # ---- background: space above the line, a perspective neon floor below
    gradient_bg(f, "#05061a", "#020208")
    nebula_glow(f, key="tl-neb", alpha=0.3)
    _parallax_stars(f, camx * 0.5, 540, n=320, key="tl-stars", depth_k=0.3)
    rng = f.rng("tl-streaks")
    ns = 70
    sx0, sy0, sd = rng.random(ns) * (W + 400), 120 + rng.random(ns) * 460, 0.3 + rng.random(ns)
    streak = clamp(abs(speed) / 900)
    if streak > 0.02:
        for i in range(ns):
            x = (sx0[i] - camx * sd[i] * 1.4) % (W + 400) - 200
            ln = 30 + 260 * streak * sd[i]
            f.c.drawLine(x, sy0[i], x + ln, sy0[i], paint(INK if i % 4 else c_, 0.25 * streak * sd[i], stroke=1.5 + sd[i]))
    with camera(f, 960, 540, zoom=zoom, shake=(14 * math.exp(-s_last * 3.5) if s_last > 0 else 0)):
        # floor
        floor = skia.GradientShader.MakeLinear([skia.Point(0, LINE_Y), skia.Point(0, H)],
                                               [col(mix(c_, "#000000", 0.75), 0.55), col("#000000", 0.0)])
        f.c.drawRect(skia.Rect.MakeLTRB(-100, LINE_Y, W + 100, H + 100), skia.Paint(Shader=floor))
        for i in range(1, 11):
            y = LINE_Y + (H + 60 - LINE_Y) * (i / 10) ** 2
            f.c.drawLine(-100, y, W + 100, y, paint(c_, 0.06 + 0.16 * (i / 10), stroke=1.5))
        step = 150.0
        first = math.floor((camx - 2400) / step) * step
        wx = first
        while wx < camx + 2400:
            xt = 960 + (wx - camx) * 1.0
            xb = 960 + (wx - camx) * 3.4
            f.c.drawLine(xt, LINE_Y, xb, H + 60, paint(c_, 0.16, stroke=1.5))
            wx += step
        soft_light(f, 960, LINE_Y, 900, c_, 0.10 + 0.05 * beat)

        # the timeline itself: bright behind the playhead, dimmer ahead
        f.c.drawLine(-100, LINE_Y, W + 100, LINE_Y, paint(c_, 0.18, stroke=22, add=True))
        f.c.drawLine(-100, LINE_Y, 960, LINE_Y, paint(mix(c_, "#ffffff", 0.3), 1, stroke=5))
        f.c.drawLine(960, LINE_Y, W + 100, LINE_Y, paint(c_, 0.45, stroke=4))
        # ticks with running values: the gaps between labels grow, so time visibly accelerates
        minor = 30.0
        wx = math.floor((camx - 1100) / minor) * minor
        while wx < camx + 1100:
            xs_ = 960 + wx - camx
            major = abs(wx / 150 - round(wx / 150)) < 1e-6
            f.c.drawLine(xs_, LINE_Y - (16 if major else 7), xs_, LINE_Y + (16 if major else 7),
                         paint(INK if major else c_, 0.7 if major else 0.4, stroke=2.5 if major else 1.5))
            if numeric and abs(wx / 450 - round(wx / 450)) < 1e-6 and 0 <= wx <= ex[-1]:
                v = value_at(wx)
                text(f, _human(v), xs_, LINE_Y + 58, size=30, color=DIM, weight="semibold",
                     a=clamp(1 - abs(xs_ - 960) / 1100))
            wx += minor
        # motes flowing along the line
        rngm = f.rng("tl-motes")
        nm = 90
        mx = (rngm.random(nm) * (W + 200) - camx * (0.8 + rngm.random(nm) * 0.6) - f.t * 40) % (W + 200) - 100
        my = LINE_Y + rngm.normal(0, 14, nm)
        dots(f, mx, my, 1.5 + rngm.random(nm) * 2.5, 0.3 + 0.5 * rngm.random(nm), c_, add=True)

        # milestones
        for i, ev in enumerate(events):
            sx = 960 + ex[i] - camx
            if abs(sx - 960) > 1500:
                continue
            s = f.t - times[i]
            final = i == n - 1
            if i == 0:
                s = max(s, 1.0)  # the starting milestone is on screen from frame 0 (its shockwave still fires on its word)
            # marker on the line
            dm = 16 if s > 0 else 11
            dia = skia.Path()
            dia.moveTo(sx, LINE_Y - dm)
            dia.lineTo(sx + dm, LINE_Y)
            dia.lineTo(sx, LINE_Y + dm)
            dia.lineTo(sx - dm, LINE_Y)
            dia.close()
            if s > 0:
                f.c.drawPath(dia, paint(INK, 1))
                soft_light(f, sx, LINE_Y, 70, c_, 0.6 + 0.3 * beat)
                shockwave(f, sx, LINE_Y, times[i], speed=600 if not final else 1200, life=1.0 if not final else 1.6,
                          color=c_, width=10 if not final else 22)
            else:
                f.c.drawPath(dia, paint(c_, 0.7, stroke=2.5))
                text(f, "?", sx, LINE_Y - 34, size=34, color=c_, a=0.6)
            if s <= 0:
                continue
            pop = ease_back(clamp(s / 0.45))
            pw, ph = 560, 210
            py = 430 + (16 if i % 2 else -10)
            lead = paint(c_, 0.7, stroke=2)
            lead.setPathEffect(skia.DashPathEffect.Make([8, 8], -f.t * 30))
            f.c.drawLine(sx, py + ph / 2, sx, py + ph / 2 + (LINE_Y - py - ph / 2 - dm) * clamp(s / 0.25), lead)
            f.c.save()
            f.c.translate(sx, py + ph / 2)
            f.c.scale(pop, pop)
            f.c.translate(0, -ph / 2)
            _panel_box(f, -pw / 2, -ph / 2, pw, ph, c_, fill_a=0.82)
            ix, iy = -pw / 2 + 96, 0
            f.c.drawCircle(ix, iy, 66, paint("#000000", 0.5))
            f.c.drawCircle(ix, iy, 66, paint(c_, 0.6, stroke=2))
            icon = ("body", ev["kind"]) if ev.get("kind") else _icon_for(ev.get("label", ""))
            _icon(f, icon, ix, iy, 52, c_)
            tx = -pw / 2 + 188
            ttl, tts = _fit(str(ev.get("time_text", "")).upper(), pw - 188 - 24, 30, "semibold", 24, 1)
            text(f, ttl[0], tx, -ph / 2 + 56, size=tts, color=c_, align="left", weight="semibold", reveal=clamp(s / 0.4))
            lines, size = _fit(ev.get("label", ""), pw - 188 - 30, 46, "bold", 30, 2)
            for li, ln in enumerate(lines):
                text(f, ln, tx, -ph / 2 + 110 + li * size * 1.12, size=size, align="left",
                     reveal=clamp((s - 0.05 - li * 0.08) / 0.25), glow_color=c_ if final else None)
            f.c.restore()
            if final and s > 0:
                particles(f, sx, LINE_Y, times[i], n=220, speed=(200, 1000), life=(0.5, 2.0), size=(2, 5), color=c_,
                          key="tl-boom")

        # the playhead: a beam of light standing on the 'now' point
        beam = skia.GradientShader.MakeLinear([skia.Point(0, 250), skia.Point(0, LINE_Y)],
                                              [col(c_, 0), col(c_, 0.35 + 0.2 * beat)])
        f.c.drawRect(skia.Rect.MakeLTRB(957, 250, 963, LINE_Y), skia.Paint(Shader=beam, BlendMode=skia.BlendMode.kPlus))
        glow(f, 960, LINE_Y, 12 + 4 * beat, mix(c_, "#ffffff", 0.4))

    # ---- HUD: the big counter and the warp readout
    v = value_at(camx)
    if v is not None:
        big = _human(v)
    else:
        done = [e for e, tt in zip(events, times) if f.t >= tt]
        big = str(done[-1].get("time_text", "")) if done else "..."
    lines, size = _fit(big.upper(), 1100, 104, "bold", 60, 1)
    text(f, lines[0], 960, 232, size=size, glow_color=c_, stroke=6)
    if unit:
        text(f, unit.upper(), 960, 286, size=32, color=DIM, weight="semibold")
    if numeric:
        rate = abs(value_at(cam_at(f.t + 0.05)) - value_at(cam_at(f.t - 0.05))) * 10
        text(f, "TIME WARP", W - 190, 140, size=30, color=DIM, align="right", weight="semibold")
        text(f, (_human(rate) + " /s") if rate > 0.05 else ("ARRIVED" if f.t > times[-1] else "READY"), W - 190, 186, size=38, color=c_ if rate > 0.05 else DIM,
             align="right", weight="bold")
        warp_k = clamp(math.log10(rate + 1) / 11)
        for b in range(10):
            on = b / 10 < warp_k
            f.c.drawRect(skia.Rect.MakeXYWH(W - 190 - (10 - b) * 22, 206, 16, 10), paint(c_ if on else DIM, 0.9 if on else 0.25))
    text(f, "TIMELINE", 190, 140, size=30, color=DIM, align="left", weight="semibold")
    passed = max(1, sum(1 for tt in times if f.t >= tt))
    text(f, f"{passed} / {n}", 190, 186, size=38, color=INK, align="left", weight="bold")
    if p("payoff"):
        slam_text(f, p("payoff").upper(), 960, 820, times[-1] + 0.15, size=120, glow_color=c_, snap=False)
    flash(f, times[-1], dur=0.45, color="#ffffff", peak=0.6)


# ================================================================ 3. case file

@lru_cache(maxsize=6)
def _wood_image(seed):
    rng = np.random.default_rng(seed)
    w, h = 640, 360
    n = fractal_noise(w, h, rng, octaves=5, base=3, stretch=10)
    lat = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    grain = 0.5 + 0.5 * np.sin(lat * rng.uniform(55, 80) + n * 16)
    v = np.clip(0.55 * grain + 0.45 * n, 0, 1)
    rgb = ramp(v, [(0, "#140b05"), (0.45, "#2e1b0e"), (0.75, "#4a2d17"), (1, "#5e3a1f")])
    rgba = np.empty((h, w, 4), np.uint8)
    rgba[..., :3] = (rgb * 255).astype(np.uint8)
    rgba[..., 3] = 255
    return skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType)


@lru_cache(maxsize=6)
def _paper_image(seed, tone):
    rng = np.random.default_rng(seed)
    w, h = 580, 370
    n = fractal_noise(w, h, rng, octaves=6, base=6)
    fib = rng.random((h, w)).astype(np.float32)
    v = 0.85 + 0.1 * n + 0.05 * fib
    edge_y = np.minimum(np.linspace(0, 1, h), np.linspace(1, 0, h))[:, None]
    edge_x = np.minimum(np.linspace(0, 1, w), np.linspace(1, 0, w))[None, :]
    v *= 0.93 + 0.07 * np.clip(np.minimum(edge_x, edge_y) * 12, 0, 1)  # slightly aged edges
    base = np.array(tone, np.float32)
    rgb = np.clip(v[..., None] * base, 0, 1)
    rgba = np.empty((h, w, 4), np.uint8)
    rgba[..., :3] = (rgb * 255).astype(np.uint8)
    rgba[..., 3] = 255
    return skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType)


_CASE_DEFAULT_LINES = [
    {"text": "SUBJECT: a planet with no star"},
    {"text": "LOCATION: drifting between stars"},
    {"text": "SURFACE: frozen, about -230 °C"},
    {"text": "ORIGIN: thrown out of its home system"},
]
_STAMP_INK = {"UNSOLVED": "#c62a22", "CONFIRMED": "#1f7a3e", "DEBUNKED": "#c62a22", "CLASSIFIED": "#c62a22",
              "PROVEN": "#1f7a3e", "POSSIBLE": "#c4801a", "UNKNOWN": "#2b4fb0"}


@template("case_file", kind="cinematic",
          sfx=lambda p: [Sfx("whoosh", "start", offset=0.05, gain_db=-6),
                         Sfx("tick", _sfx_at((p("lines") or _CASE_DEFAULT_LINES)[0], 0.9), gain_db=-4),
                         Sfx("glitch", p("redact_at") or "end", offset=0 if p("redact_at") else -2.0, gain_db=-6),
                         Sfx("impact", p("stamp_at") or "end", offset=0 if p("stamp_at") else -1.1),
                         Sfx("808", p("stamp_at") or "end", offset=0 if p("stamp_at") else -1.1)])
def case_file(f, p):
    """A mystery dossier on a dark wooden desk under a warm lamp: a case file with a polaroid of the subject (a
    procedurally drawn planet, star or black hole), lines typing out one by one, a redaction bar that wipes off to
    reveal the key line (with red marker circling the photo), then a rubber stamp SLAMS down: UNSOLVED, CONFIRMED,
    DEBUNKED... Use for "the case of...", real mysteries, myth-busting and verdicts.
    params: title (case name), subject_kind (body in the photo: earth, mars, ice, black_hole, red_giant...),
    lines [{text, at}] (2-5 short typed lines; at = word each types on), redact (index of the hidden line,
    default the last), redact_at (word the bar wipes off), stamp (UNSOLVED|CONFIRMED|DEBUNKED|any short word),
    stamp_at (word it slams on), note (handwritten scribble, default "?!"), case_no, color"""
    lines_ = p("lines") or _CASE_DEFAULT_LINES
    n = len(lines_)
    title = p("title") or "The Rogue Planet"
    subject = p("subject_kind") or ("ice" if not p("lines") else pick(f, "case_subj", ["ice", "mars", "rocky", "gas", "lava"]))
    stamp = str(p("stamp") or "CONFIRMED").upper()
    ink = _STAMP_INK.get(stamp, "#c62a22")
    times = _beats(f, lines_, 0.14, 0.5)
    redact_i = int(p("redact", n - 1)) % max(n, 1)
    t_red = when(f, p("redact_at"), 0.64)
    t_stamp = when(f, p("stamp_at"), 0.8)
    beat = f.beat_pulse()
    s_st = f.t - t_stamp
    rot = rand(f, "case_rot", -2.4, 2.4)
    lamp_x = pick(f, "case_lamp", [520, 1400])
    seed = f.seed * 31 + 7

    # ---- camera: slow push down onto the file, punch and shake on the stamp
    zoom = lerp(1.0, 1.07, ease_in_out(f.p)) * (1 + (0.05 * math.exp(-s_st * 7) if s_st > 0 else 0))
    shake = 16 * math.exp(-s_st * 6) if s_st > 0 else 0
    slide = 0.12 * (1 - ease_out(f.prog(0, 0.9)))  # a small settle, the file is on the desk from frame 0
    with camera(f, 960 + lerp(-20, 20, f.p), 540, zoom=zoom, rotate=lerp(-0.6, 0.6, f.p), shake=shake):
        # desk
        f.c.drawImageRect(_wood_image(seed % 100000), skia.Rect.MakeLTRB(-120, -80, W + 120, H + 80),
                          skia.SamplingOptions(skia.FilterMode.kLinear))
        # props: an older photo, a pen, a mug with steam
        f.c.save()
        f.c.translate(250, 300)
        f.c.rotate(-13)
        f.c.drawRect(skia.Rect.MakeXYWH(-140, -150, 280, 320), paint("#000000", 0.45, blur=14))
        f.c.drawRect(skia.Rect.MakeXYWH(-130, -160, 260, 300), paint("#d9d3c6", 1))
        f.c.drawRect(skia.Rect.MakeXYWH(-112, -142, 224, 210), paint("#1c2130", 1))
        soft_light(f, -20, -50, 120, "#9fb8ff", 0.25)
        f.c.restore()
        f.c.save()
        f.c.translate(1720, 820)
        f.c.drawCircle(8, 12, 96, paint("#000000", 0.5, blur=12))
        mug = skia.GradientShader.MakeRadial(skia.Point(-25, -25), 120, [col("#f0ebe2"), col("#8f877c")])
        f.c.drawRRect(_rrect(70, -22, 70, 44, 20), paint("#bdb5aa", 1, stroke=14))
        f.c.drawCircle(0, 0, 92, skia.Paint(AntiAlias=True, Shader=mug))
        f.c.drawCircle(0, 0, 74, paint("#2a140a", 1))
        f.c.drawOval(skia.Rect.MakeLTRB(-46, -40, 10, -18), paint("#ffffff", 0.12))
        f.c.restore()
        for k in range(3):  # steam wisps
            pts = [(1720 + (k - 1) * 26 + 18 * math.sin(f.t * 1.6 + j * 0.5 + k * 2), 790 - j * 14) for j in range(14)]
            f.c.drawPath(line_path(pts, smooth=True), paint("#ffffff", 0.07, stroke=10, blur=4))
        f.c.save()
        f.c.translate(1620, 300)
        f.c.rotate(62)
        f.c.drawRRect(_rrect(-14, -200, 28, 400, 12), paint("#000000", 0.4, blur=8))
        f.c.drawRRect(_rrect(-11, -195, 22, 390, 11), paint("#16161b", 1))
        f.c.drawRect(skia.Rect.MakeXYWH(-11, -110, 22, 14), paint("#c9a74a", 1))
        f.c.drawRect(skia.Rect.MakeXYWH(-3, -190, 6, 100), paint("#c9a74a", 1))
        f.c.restore()

        # the folder and paper slide in, then sit still (with a jolt when stamped)
        jolt = (6 * math.exp(-s_st * 9) * math.sin(s_st * 60)) if s_st > 0 else 0
        f.c.save()
        f.c.translate(960 + slide * 260, 515 + slide * 420 + jolt)
        f.c.rotate(rot - slide * 8)
        PW, PH = 1160, 740
        L, T = -PW / 2, -PH / 2
        f.c.save()
        f.c.rotate(2.2)
        f.c.drawRRect(_rrect(L - 30, T - 40, PW + 60, PH + 70, 14), paint("#000000", 0.55, blur=22))
        f.c.drawRRect(_rrect(L - 22, T - 30, PW + 44, PH + 54, 12), paint("#b8925a", 1))
        f.c.drawRRect(_rrect(L + 40, T - 74, 300, 70, 12), paint("#b8925a", 1))
        text(f, "EVIDENCE", L + 190, T - 26, size=30, color="#5b4426", weight="semibold")
        f.c.restore()
        f.c.drawRect(skia.Rect.MakeXYWH(L + 8, T + 10, PW, PH), paint("#000000", 0.35, blur=10))
        f.c.drawImageRect(_paper_image(seed % 100000, (0.94, 0.9, 0.8)), skia.Rect.MakeXYWH(L, T, PW, PH),
                          skia.SamplingOptions(skia.FilterMode.kLinear))
        inkc = "#2b2721"
        # coffee ring stain
        stain_x, stain_y = L + PW * rand(f, "stx", 0.55, 0.85), T + PH * rand(f, "sty", 0.7, 0.85)
        f.c.drawCircle(stain_x, stain_y, 70, paint("#6b4a2a", 0.13, stroke=7))
        f.c.drawCircle(stain_x + 4, stain_y - 2, 66, paint("#6b4a2a", 0.06, stroke=3))
        # header
        text(f, "CASE FILE", L + 56, T + 72, size=30, color="#6b5a44", align="left", weight="semibold")
        cno = p("case_no") or f"No. {int(rand(f, 'cno', 100, 999))}-{chr(65 + int(rand(f, 'cnl', 0, 26)))}"
        text(f, str(cno), L + PW - 56, T + 72, size=30, color="#6b5a44", align="right", weight="semibold")
        tl, tsize = _fit(title.upper(), PW - 112, 62, "bold", 40, 1)
        text(f, tl[0], L + 56, T + 148, size=tsize, color=inkc, align="left", weight="bold")
        f.c.drawLine(L + 56, T + 172, L + PW - 56, T + 172, paint("#8c2a20", 0.8, stroke=3))
        f.c.drawLine(L + 56, T + 180, L + PW - 56, T + 180, paint("#8c2a20", 0.5, stroke=1.5))

        # polaroid of the subject
        f.c.save()
        f.c.translate(L + 225, T + 400)
        f.c.rotate(-3.5)
        f.c.drawRect(skia.Rect.MakeXYWH(-160, -186, 330, 384), paint("#000000", 0.4, blur=10))
        f.c.drawRect(skia.Rect.MakeXYWH(-165, -190, 330, 380), paint("#f6f3ec", 1))
        f.c.save()
        f.c.clipRect(skia.Rect.MakeXYWH(-145, -170, 290, 290))
        f.c.drawPaint(paint("#04060d", 1))
        rngp = f.rng("case-photo")
        dots(f, -145 + rngp.random(90) * 290, -170 + rngp.random(90) * 290, 0.6 + rngp.random(90) * 1.4,
             0.3 + 0.6 * rngp.random(90), INK)
        body(f, subject, 0, -25, 102, rotation=f.t * 0.01, light=(-0.7, -0.4, 0.6), seed_key="case")
        f.c.drawPaint(paint("#ffcf8a", 0.10))  # warm print tint
        gr = f.rng(f"case-grain{f.index % 4}")  # film grain that crawls (4 patterns cycling)
        dots(f, -145 + gr.random(260) * 290, -170 + gr.random(260) * 290, 0.8, 0.12, "#ffffff")
        f.c.restore()
        text(f, p("photo_label") or "fig. 1 - subject", 0, 166, size=40, color="#3a3530", weight="hand")
        for tx_, ty_, tr_ in ((-150, -190, -30), (150, -190, 30)):  # tape
            f.c.save()
            f.c.translate(tx_, ty_)
            f.c.rotate(tr_)
            f.c.drawRect(skia.Rect.MakeXYWH(-48, -16, 96, 32), paint("#f3e9c6", 0.55))
            f.c.restore()
        # red marker circling the subject once the redaction lifts
        mk = f.prog(t_red + 0.2, 0.6, ease=ease_out)
        if mk > 0:
            oval = skia.Path()
            oval.addOval(skia.Rect.MakeLTRB(-135, -150, 135, 105))
            draw_partial(f, oval, mk, chalk("#c62a22", 6, 0.85, roughness=2.2, seed=3))
        f.c.restore()
        if f.prog(t_red + 0.6, 0.5) > 0:
            f.c.save()
            f.c.translate(L + 330, T + 212)
            f.c.rotate(-9)
            nl_, ns_ = _fit(str(p("note") or "?!"), 260, 64, "hand", 40, 1)
            text(f, nl_[0], 0, 0, size=ns_, color="#c62a22", weight="hand",
                 reveal=f.prog(t_red + 0.6, 0.5, ease=lambda v: clamp(v)))
            f.c.restore()

        # typed lines
        lx = L + 440
        max_w = PW - 440 - 60
        for i, ln in enumerate(lines_):
            s = f.t - times[i]
            y = T + 260 + i * 84
            txt = str(ln.get("text", ""))
            tl2, size = _fit(txt, max_w, 36, "medium", 30, 1)
            f.c.drawLine(lx, y + 18, lx + max_w, y + 18, paint("#9a8f7c", 0.35, stroke=1.5))
            if s <= 0:
                continue
            dur_ = 0.03 * len(txt) + 0.2
            rev = clamp(s / dur_)
            wtxt = text(f, tl2[0], lx, y, size=size, color=inkc, align="left", weight="medium", reveal=rev)
            if rev < 1 and int(f.t * 8) % 2 == 0:
                cxp = lx + (wtxt or 0) * rev + 4
                f.c.drawRect(skia.Rect.MakeXYWH(cxp, y - size * 0.75, size * 0.5, size * 0.9), paint(inkc, 0.8))
            if i == redact_i:
                full_w = font(size, "medium").measureText(tl2[0])
                key_w = font(size, "medium").measureText(tl2[0].split(":")[0] + ":") if ":" in tl2[0] else 0
                bx0 = lx + key_w + (10 if key_w else -6)
                bx1 = lx + full_w + 8
                wipe = f.prog(t_red, 0.55, ease=ease_in_out)
                left_edge = lerp(bx0, bx1, wipe)
                if left_edge < bx1 - 1:
                    f.c.drawRect(skia.Rect.MakeLTRB(left_edge, y - size * 0.88, bx1, y + size * 0.3), paint("#0b0b0d", 0.96))
                    if 0 < wipe < 1:
                        soft_light(f, left_edge, y - size * 0.3, 60, "#ffffff", 0.5)
                        f.c.drawLine(left_edge, y - size * 0.95, left_edge, y + size * 0.38, paint("#ffffff", 0.8, stroke=3))
                if wipe <= 0:
                    text(f, "REDACTED", (bx0 + bx1) / 2, y - 4, size=30, color="#4a4a50", weight="semibold")

        # the stamp: a shadow drops first, then it slams
        sw_ = font(116, "bold").measureText(stamp)
        sx, sy = L + 800, T + 500  # over the typed lines, like a real stamp
        if -0.25 < s_st <= 0:
            k = 1 + s_st / 0.25
            f.c.drawRRect(_rrect(sx - sw_ / 2 - 40 + 30 * (1 - k), sy - 90 + 30 * (1 - k), sw_ + 80, 170, 18),
                          paint("#000000", 0.35 * k, blur=30 * (1 - k) + 6))
        if s_st > 0:
            f.c.save()
            f.c.translate(sx, sy)
            f.c.rotate(-13)
            sc = lerp(1.7, 1.0, ease_out(clamp(s_st / 0.09)))
            f.c.scale(sc, sc)
            a = clamp(s_st / 0.05)
            fit = min(1.0, 640 / max(sw_, 1))
            f.c.scale(fit, fit)
            box = _rrect(-sw_ / 2 - 36, -82, sw_ + 72, 160, 16)
            f.c.drawRRect(box, paint(ink, 0.9 * a, stroke=10))
            f.c.drawRRect(_rrect(-sw_ / 2 - 22, -68, sw_ + 44, 132, 10), paint(ink, 0.6 * a, stroke=3))
            text(f, stamp, 0, 42, size=116, color=ink, a=0.92 * a)
            rngs = f.rng("stamp-wear")  # worn rubber: paper-coloured speckles through the ink
            dots(f, (rngs.random(420) - 0.5) * (sw_ + 72), (rngs.random(420) - 0.5) * 160, 1 + rngs.random(420) * 2.5,
                 0.75, "#efe6d0")
            f.c.restore()
            if s_st < 1.2:  # ink splatter and a puff of dust on contact
                rngd = f.rng("stamp-splat")
                ang = rngd.random(36) * 6.28
                d = (sw_ * 0.5 + 40) * (0.9 + 0.5 * rngd.random(36)) * ease_out(clamp(s_st / 0.12))
                dots(f, sx + np.cos(ang) * d, sy + np.sin(ang) * d * 0.4, 2 + rngd.random(36) * 4, 0.7, ink)
        f.c.restore()  # paper

        if s_st > 0:
            particles(f, sx + 960, sy + 515, t_stamp, n=90, speed=(100, 420), life=(0.4, 1.2), size=(2, 4),
                      color="#e8dcc0", key="stamp-dust", spread=(160, 380))

        # lamp light: warm pool, dark edges, a faint beam and dust motes in it
        shade = skia.GradientShader.MakeRadial(skia.Point(lamp_x, 300), 1500,
                                              [col("#000000", 0.0), col("#000000", 0.35), col("#000000", 0.86)],
                                              [0.0, 0.42, 1.0])
        f.c.drawRect(skia.Rect.MakeLTRB(-200, -200, W + 200, H + 200), skia.Paint(Shader=shade))
        soft_light(f, lamp_x, 320, 1000, "#ffcf8a", 0.10 + 0.03 * beat + 0.01 * math.sin(f.t * 17))
        rngm = f.rng("case-motes")
        nm = 110
        mx = lamp_x - 450 + (rngm.random(nm) * 900 + 12 * f.t * (rngm.random(nm) - 0.5)) % 900
        my = (rngm.random(nm) * 900 - f.t * (6 + 10 * rngm.random(nm))) % 900
        tw = 0.5 + 0.5 * np.sin(f.t * (1 + rngm.random(nm) * 2) + rngm.random(nm) * 6)
        dots(f, mx, my, 1 + rngm.random(nm) * 1.8, 0.35 * tw, "#ffe2b0", add=True)

    flash(f, t_stamp, dur=0.3, color=ink, peak=0.22)


# ================================================================ 4. mission control

_MC_DEFAULT_READOUTS = [
    {"label": "VELOCITY", "value": "24.1 km/s"},
    {"label": "DISTANCE", "value": "54.6 M km"},
    {"label": "SIGNAL DELAY", "value": "3 min 2 s"},
    {"label": "FUEL", "value": "12 %"},
]
_MC_LIGHTS = ["PWR", "NAV", "COMMS", "THRM", "O2", "FUEL", "ATT", "LINK"]


@template("mission_control", kind="cinematic",
          sfx=lambda p: [Sfx("glitch", "start", offset=0.1, gain_db=-6)]
          + [Sfx("tick", _sfx_at(r, 1.2 + 0.7 * i), gain_db=-4) for i, r in enumerate((p("readouts") or _MC_DEFAULT_READOUTS)[:2])]
          + [Sfx("riser", p("alert_at") or "end", offset=-1.6 if p("alert_at") else -3.3, dur=1.6),
             Sfx("impact", p("alert_at") or "end", offset=0 if p("alert_at") else -1.7)])
def mission_control(f, p):
    """A full mission-control console: panels boot up, a trajectory map shows the craft gliding from its home planet
    towards the target, telemetry graphs scroll, readouts count up on their words and status lights flip green ->
    amber as a countdown runs... then ALERT: everything goes red, the screen shakes, the graphs spike and the craft
    veers off its planned path. Use for missions, probes, "what would NASA see", near misses and emergencies.
    params: craft (name, e.g. "Voyager 1"), origin_kind (default earth), target_kind (body the craft heads for),
    readouts [{label, value, at}] (2-5; numbers in value count up), alert_text (default "ALERT"),
    alert_at (word the alarm hits on), status (small line under the alert, optional), color"""
    f.c.clear(col("#02050a"))
    gradient_bg(f, "#0a1726", "#03060c")
    with camera(f, 960, 540, zoom=0.86):  # the whole console sits inside the safe area
        _mission_body(f, p)


def _mission_body(f, p):
    """The console itself, drawn at 1920x1080 (mission_control scales it into the safe area)."""
    c_ = accent(f, p, default=["cyan", "green", "ice"])
    craft = str(p("craft") or pick(f, "mc_craft", ["ARES-1", "HORIZON", "PATHFINDER II", "ODYSSEY", "LONGSHOT"]))
    target = p("target_kind") or "mars"
    origin = p("origin_kind") or "earth"
    readouts = p("readouts") or _MC_DEFAULT_READOUTS
    t_alert = when(f, p("alert_at"), 0.72)
    r_times = _beats(f, readouts, 0.16, 0.55)
    sa = f.t - t_alert
    alert = clamp(sa / 0.15) if sa > 0 else 0.0
    esc = clamp((f.t - (t_alert - 2.8)) / 2.8)  # escalation before the alert
    blink = 1.0 if int(f.t * 4) % 2 == 0 else 0.35
    beat = f.beat_pulse()
    red_mix = lambda base: mix(base, RED, alert)  # noqa: E731
    shake = (20 * math.exp(-sa * 3) + 2.5) if sa > 0 else 1.2 * esc

    soft_light(f, 600, 400, 1100, c_, 0.06)
    with camera(f, 960, 540, zoom=1.0 + 0.01 * beat + (0.04 * math.exp(-sa * 4) if sa > 0 else 0), shake=shake):
        # ---- trajectory map
        MX, MY, MW, MH = 40, 116, 1110, 590
        boot = [-1.0, -1.0, -1.0, -1.0]  # everything is on screen from frame 0
        if f.t > boot[0]:
            k = ease_out(clamp((f.t - boot[0]) / 0.4))
            f.c.save()
            f.c.clipRect(skia.Rect.MakeXYWH(MX - 6, MY - 6, MW + 12, (MH + 12) * k))
            _panel_box(f, MX, MY, MW, MH, red_mix(c_), fill="#0b1c2e", fill_a=0.95)
            f.c.save()
            f.c.clipRect(skia.Rect.MakeXYWH(MX + 4, MY + 4, MW - 8, MH - 8))
            for gx in range(MX, MX + MW, 55):
                f.c.drawLine(gx, MY, gx, MY + MH, paint(c_, 0.05, stroke=1))
            for gy in range(MY, MY + MH, 55):
                f.c.drawLine(MX, gy, MX + MW, gy, paint(c_, 0.05, stroke=1))
            rngs = f.rng("mc-stars")
            dots(f, MX + rngs.random(120) * MW, MY + rngs.random(120) * MH, 0.6 + rngs.random(120), 0.35, INK)
            ox, oy, orr = MX + 170, MY + 450, 46
            tx, ty, trr = MX + 900, MY + 210, 74
            sunx, suny = MX - 60, MY + MH + 140  # the Sun sits off the map; both planets ride its orbits
            soft_light(f, sunx, suny, 700, GOLD, 0.22)
            body(f, "sun", sunx, suny, 120)
            for (bx_, by_) in ((ox, oy), (tx, ty)):
                rr_ = math.hypot(bx_ - sunx, by_ - suny)
                op_ = paint(DIM, 0.35, stroke=2)
                op_.setPathEffect(skia.DashPathEffect.Make([3, 9], 0))
                f.c.drawCircle(sunx, suny, rr_, op_)
            text(f, "SUN", sunx + 150, suny - 120, size=30, color=GOLD, weight="semibold", align="left")
            for rr in (130, 190, 260):
                rp = paint(red_mix(c_), 0.18, stroke=1.5)
                rp.setPathEffect(skia.DashPathEffect.Make([6, 10], f.t * 10))
                f.c.drawCircle(tx, ty, rr, rp)
            body(f, origin, ox, oy, orr, light=(0.7, -0.4, 0.6), seed_key="mc-o")
            body(f, target, tx, ty, trr, light=(-0.7, -0.3, 0.6), seed_key="mc-t")
            p0, p3 = (ox + 40, oy - 40), (tx - 85, ty + 40)
            c1, c2 = (ox + 220, oy - 330), (tx - 420, ty - 150)
            path = skia.Path()
            path.moveTo(*p0)
            path.cubicTo(*c1, *c2, *p3)
            plan = paint(DIM, 0.55, stroke=2.5)
            plan.setPathEffect(skia.DashPathEffect.Make([12, 10], -f.t * 25))
            f.c.drawPath(path, plan)
            prog = 0.06 + 0.74 * ease_in_out(clamp(f.t / max(t_alert, 0.5))) + (0.04 * clamp(sa / 3) if sa > 0 else 0)
            draw_partial(f, path, prog, paint(red_mix(c_), 0.25, stroke=14, add=True))
            draw_partial(f, path, prog, paint(red_mix(c_), 1, stroke=3.5))
            m = skia.PathMeasure(path, False)
            pos = m.getPosTan(m.getLength() * prog)
            if pos:
                (pt, tn) = pos
                px_, py_ = pt.x(), pt.y()
                ta = math.atan2(tn.y(), tn.x())
                if sa > 0:  # the predicted path veers off
                    dv = paint(RED, 0.9 * blink, stroke=3)
                    dv.setPathEffect(skia.DashPathEffect.Make([10, 8], -f.t * 60))
                    vp = skia.Path()
                    vp.moveTo(px_, py_)
                    va = ta + 0.75
                    vp.quadTo(px_ + math.cos(ta) * 140, py_ + math.sin(ta) * 140,
                              px_ + math.cos(va) * 300, py_ + math.sin(va) * 300)
                    draw_partial(f, vp, clamp(sa / 0.8), dv)
                cr = red_mix(INK)
                tri = skia.Path()
                tri.moveTo(px_ + math.cos(ta) * 18, py_ + math.sin(ta) * 18)
                tri.lineTo(px_ + math.cos(ta + 2.4) * 13, py_ + math.sin(ta + 2.4) * 13)
                tri.lineTo(px_ + math.cos(ta - 2.4) * 13, py_ + math.sin(ta - 2.4) * 13)
                tri.close()
                glow(f, px_, py_, 10, red_mix(c_), 0.8 if sa <= 0 else blink)
                f.c.drawPath(tri, paint(cr, 1))
                ring(f, px_, py_, 26 + 10 * ((f.t * 1.5) % 1), 3, red_mix(c_), 0.7 * (1 - (f.t * 1.5) % 1))
                near = px_ > MX + 560  # close to the target: put the tag on the other side
                tx_off, al = (-34, "right") if near else (34, "left")
                tag_y = py_ + (40 if near else -26)
                text(f, craft.upper(), px_ + tx_off, tag_y, size=30, color=cr, align=al, weight="semibold", stroke=4)
                rem = 1 - prog
                text(f, f"{rem * 100:.0f}% TO GO", px_ + tx_off, tag_y + 38, size=30, color=DIM, align=al,
                     weight="semibold", stroke=4)
            text(f, origin.replace("_", " ").upper(), ox, oy + orr + 42, size=30, color=DIM, weight="semibold")
            label(f, target.replace("_", " ").upper(), tx - trr * 0.7, ty - trr * 0.7, tx - 190, ty - 120, -5.0,
                  size=32, color=INK, line_color=red_mix(c_))
            text(f, "TRAJECTORY  /  NOT TO SCALE", MX + 28, MY + 50, size=30, color=red_mix(c_), align="left",
                 weight="semibold")
            f.c.restore()
            f.c.restore()

        # ---- readouts
        RX, RY, RW, RH = 1180, 116, 700, 330
        if f.t > boot[1]:
            k = ease_out(clamp((f.t - boot[1]) / 0.4))
            f.c.save()
            f.c.clipRect(skia.Rect.MakeXYWH(RX - 6, RY - 6, RW + 12, (RH + 12) * k))
            _panel_box(f, RX, RY, RW, RH, red_mix(c_), fill="#0b1c2e", fill_a=0.95)
            text(f, "TELEMETRY", RX + 28, RY + 50, size=30, color=red_mix(c_), align="left", weight="semibold")
            nr = min(len(readouts), 5)
            row = (RH - 80) / max(nr, 1)
            for i, rd in enumerate(readouts[:5]):
                s = f.t - r_times[i]
                y = RY + 80 + row * (i + 0.62)
                f.c.drawLine(RX + 28, y + 16, RX + RW - 28, y + 16, paint(c_, 0.12, stroke=1.5))
                if s <= 0:
                    text(f, str(rd.get("label", "")).upper(), RX + 28, y, size=30, color=DIM, align="left",
                         weight="semibold", a=0.35)
                    text(f, "--", RX + RW - 28, y, size=36, color=DIM, align="right", a=0.4)
                    continue
                flick = 1 if s > 0.25 else (0.3 if int(s * 30) % 2 else 1)
                text(f, str(rd.get("label", "")).upper(), RX + 28, y, size=30, color=DIM, align="left",
                     weight="semibold", a=flick)
                val = _count_text(rd.get("value", ""), ease_out(clamp(s / 0.8)))
                vl, vs = _fit(val, RW * 0.55, 40, "bold", 30, 1)
                text(f, vl[0], RX + RW - 28, y + 2, size=vs, color=red_mix(INK) if sa > 0 else INK, align="right",
                     weight="bold", a=flick, glow_color=c_ if s < 0.6 else None)
            f.c.restore()

        # ---- status lights
        SX, SY, SW, SH = 1180, 466, 700, 240
        if f.t > boot[2]:
            k = ease_out(clamp((f.t - boot[2]) / 0.4))
            f.c.save()
            f.c.clipRect(skia.Rect.MakeXYWH(SX - 6, SY - 6, SW + 12, (SH + 12) * k))
            _panel_box(f, SX, SY, SW, SH, red_mix(c_), fill="#0b1c2e", fill_a=0.95)
            text(f, "SYSTEMS", SX + 28, SY + 50, size=30, color=red_mix(c_), align="left", weight="semibold")
            order = list(f.rng("mc-lights").permutation(len(_MC_LIGHTS)))
            for j, name in enumerate(_MC_LIGHTS):
                cx_, cy_ = SX + 50 + (j % 4) * 166, SY + 110 + (j // 4) * 80
                rank = order.index(j)
                amber_t = t_alert - 2.6 + rank * 0.35
                if sa > 0:
                    lc, la = RED, (blink if (j + int(f.t * 4)) % 2 else 1.0)
                elif f.t > amber_t and rank < 5:
                    lc, la = GOLD, 0.7 + 0.3 * math.sin(f.t * 8 + j)
                else:
                    lc, la = GREEN, 0.75 + 0.25 * beat
                f.c.drawCircle(cx_, cy_, 15, paint("#000000", 0.8))
                f.c.drawCircle(cx_, cy_, 12, paint(lc, la))
                soft_light(f, cx_, cy_, 42, lc, 0.45 * la)
                text(f, name, cx_ + 26, cy_ + 11, size=30, color=INK if lc != GREEN else DIM, align="left",
                     weight="semibold")
            f.c.restore()

        # ---- telemetry graphs scrolling along the bottom
        GY, GH = 728, 172
        if f.t > boot[3]:
            k = ease_out(clamp((f.t - boot[3]) / 0.4))
            names = [("VELOCITY", "km/s", 24.1), ("HULL TEMP", "°C", 18.0), ("SIGNAL", "dB", -92.0)]
            for gi, rd in enumerate(readouts[:3]):  # graph the readouts themselves when they're numbers
                sp = _split_num(rd.get("value", ""))
                if sp:
                    names[gi] = (str(rd.get("label", "")).upper(), sp[3].strip(), sp[1])
            gw = (1840 - 2 * 20) / 3
            rngg = f.rng("mc-graphs")
            for gi, (gname, gunit, gbase) in enumerate(names):
                gx = 40 + gi * (gw + 20)
                f.c.save()
                f.c.clipRect(skia.Rect.MakeXYWH(gx - 6, GY - 6, gw + 12, (GH + 12) * k))
                gc = mix(c_, GOLD, esc * 0.6) if sa <= 0 else RED
                _panel_box(f, gx, GY, gw, GH, gc, fill="#0b1c2e", fill_a=0.95, brackets=False)
                fr = rngg.random(3) * 2 + 0.8
                ph = rngg.random(3) * 6.28
                npts = 90
                u = f.t - (1 - np.linspace(0, 1, npts)) * 4.0  # the last 4 seconds of data
                amp = 0.25 + 0.35 * esc + (1.2 * np.exp(-np.clip(u - t_alert, 0, None) * 1.5) * (u > t_alert))
                sig = (np.sin(u * fr[0] * 2 + ph[0]) * 0.5 + np.sin(u * fr[1] * 5 + ph[1]) * 0.3
                       + np.sin(u * fr[2] * 11 + ph[2]) * 0.2 * (1 + esc * 2))
                vy = np.clip(sig * amp, -1.2, 1.2)
                ptsx = gx + 16 + np.linspace(0, 1, npts) * (gw - 32)
                ptsy = GY + GH * 0.62 - vy * GH * 0.28
                pth = line_path(list(zip(ptsx.tolist(), ptsy.tolist())))
                f.c.drawPath(pth, paint(gc, 0.25, stroke=9, add=True))
                f.c.drawPath(pth, paint(gc, 0.95, stroke=2.5))
                glow(f, float(ptsx[-1]), float(ptsy[-1]), 6, gc)
                gl, gs = _fit(gname, gw * 0.45, 30, "semibold", 26, 1)
                text(f, gl[0], gx + 20, GY + 44, size=gs, color=gc, align="left", weight="semibold")
                cur = gbase * (1 + 0.02 * float(vy[-1]))
                vl_, vs_ = _fit(f"{cur:,.1f} {gunit}", gw * 0.5, 30, "semibold", 26, 1)
                text(f, vl_[0], gx + gw - 20, GY + 44, size=vs_, color=INK, align="right", weight="semibold")
                f.c.restore()

    # ---- top bar (screen space): mission name, countdown, LIVE
    text(f, "MISSION CONTROL", 40, 58, size=30, color=DIM, align="left", weight="semibold")
    text(f, craft.upper(), 40 + font(30, "semibold").measureText("MISSION CONTROL") + 24, 60, size=40,
         color=red_mix(INK), align="left", weight="bold")
    if sa <= 0:
        rem = max(t_alert - f.t, 0)
        clock = f"T-{int(rem // 60):02d}:{rem % 60:04.1f}"
        cc = mix(c_, GOLD, esc)
    else:
        clock = f"T+{int(sa // 60):02d}:{sa % 60:04.1f}"
        cc = RED
    text(f, clock, 960, 72, size=58, color=cc, glow_color=cc if esc > 0.3 else None)
    f.c.drawCircle(W - 150, 48, 10, paint(RED, blink))
    text(f, "LIVE", W - 40, 60, size=34, color=INK, align="right", weight="bold")
    if 0.4 < esc and sa <= 0 and int(f.t * 3) % 2 == 0:
        text(f, "ANOMALY DETECTED", 1180 + 350, 98 + 2, size=30, color=GOLD, weight="semibold")
    # scanlines
    sl = paint("#000000", 0.18, stroke=1)
    for y in range(0, H, 4):
        f.c.drawLine(0, y, W, y, sl)

    # ---- the payoff: ALERT
    if sa > 0:
        edge = skia.GradientShader.MakeRadial(skia.Point(W / 2, H / 2), W * 0.7,
                                             [col(RED, 0), col(RED, (0.32 + 0.2 * beat) * blink)], [0.45, 1.0])
        f.c.drawPaint(skia.Paint(Shader=edge, BlendMode=skia.BlendMode.kPlus))
        band_k = ease_out(clamp(sa / 0.2))
        by0, by1 = 330, 500
        f.c.save()
        f.c.clipRect(skia.Rect.MakeLTRB(0, lerp(415, by0, band_k), W, lerp(415, by1, band_k)))
        f.c.drawPaint(paint("#120203", 0.86))
        stripes = paint(RED, 0.5 * blink + 0.2, stroke=26, cap_round=False)
        off = (f.t * 120) % 80
        for xx in range(-200, W + 200, 80):
            f.c.drawLine(xx + off, by0, xx + off + 170, by1, stripes)
        f.c.drawRect(skia.Rect.MakeLTRB(0, by0 + 20, W, by1 - 20), paint("#120203", 0.82))
        f.c.restore()
        slam_text(f, str(p("alert_text") or "ALERT").upper(), 960, 386, t_alert, size=150, glow_color=RED, snap=False)
        if p("status"):
            text(f, str(p("status")).upper(), 960, 468, size=32, color=INK, weight="semibold", a=f.prog(t_alert + 0.4, 0.3))
    flash(f, t_alert, dur=0.4, color=RED, peak=0.5)


# ================================================================ 5. scale dive

_SCALE_DEFAULT = [
    {"label": "You", "size_text": "about 2 m"},
    {"label": "Your city", "size_text": "about 20 km"},
    {"label": "Your country", "size_text": "about 1,000 km"},
    {"label": "Earth", "size_text": "12,742 km"},
    {"label": "The Moon's orbit", "size_text": "770,000 km"},
    {"label": "Earth's orbit", "size_text": "300 million km"},
]
_SCALE_STEP = 7.0
_SCALE_BASE = 250.0


def _scale_kind(label_):
    w = str(label_).lower()
    words = [x.strip(".,!?'\"") for x in w.replace("'s", " ").split()]
    if "orbit" in w:
        return "orbit"
    if "solar system" in w:
        return "solar"
    if "galax" in w or "milky" in w:
        return "galaxy"
    if any(x in words for x in ("you", "me", "person", "human", "people", "astronaut", "kid", "man", "woman")):
        return "person"
    if any(x.startswith(k) for x in words for k in ("city", "cities", "town", "village", "london", "tokyo", "paris")):
        return "city"
    if any(x.startswith(k) for x in words for k in ("country", "continent", "nation", "state", "island", "usa",
                                                     "europe", "africa", "america", "australia", "region", "uk")):
        return "country"
    for x in words:
        if x in BODY_KINDS:
            return "body:" + x
    return "ring"


def _engulf_color(kind):
    if kind.startswith("body:"):
        return {"earth": "#0d2f63", "moon": "#5e5852", "mars": "#8f3d22", "sun": "#ffb347", "jupiter": "#b58a5f",
                "black_hole": "#000000"}.get(kind[5:], "#2a2a33")
    return {"city": "#141821", "country": "#2f5a2c"}.get(kind)


@template("scale_dive", kind="cinematic",
          sfx=lambda p: [Sfx("riser", "start", dur=1.2, gain_db=-8)]
          + [Sfx("whoosh", _sfx_at(lv, 0.5 + 0.9 * (i + 1)), offset=-0.5, gain_db=-3)
             for i, lv in enumerate((p("levels") or _SCALE_DEFAULT)[1:4])]
          + [Sfx("808", _sfx_at((p("levels") or _SCALE_DEFAULT)[-1], 5.0))])
def scale_dive(f, p):
    """One continuous 'powers of ten' zoom through nested scales from the human world outward (person -> city ->
    country -> Earth -> the Moon's orbit -> Earth's orbit), or inward with direction "in". Each scale is drawn
    procedurally (a person, city blocks and lights, a coastline, planets, orbit rings, a galaxy), the zoom has real
    motion blur, and a HUD shows the name, a size bar with the real size and a ladder of all the levels.
    Differs from zoom_scale (planet -> galaxy): this one starts at human size and shows sizes.
    params: levels [{label, size_text, at, kind}] (2-7, smallest first; at = word the zoom arrives on; kind
    optional: person|city|country|orbit|solar|galaxy|ring|any body kind, otherwise guessed from label),
    direction (out|in), color"""
    levels = list(p("levels") or _SCALE_DEFAULT)
    n = len(levels)
    c_ = accent(f, p, default=["cyan", "gold", "ice", "pink"])
    direction = p("direction") or "out"
    shown = levels if direction == "out" else list(reversed(levels))
    times_shown = _beats(f, shown, 0.08, 0.84)
    # geometry is built smallest -> largest; L counts levels zoomed out
    if direction == "out":
        geo, times = levels, times_shown
    else:
        geo, times = levels, list(reversed(times_shown))
    kinds = [lv.get("kind") or _scale_kind(lv.get("label", "")) for lv in geo]
    kinds = [("body:" + k if k in BODY_KINDS else k) for k in kinds]

    def level_at(t):
        L = 0.0
        if direction == "out":
            for i in range(1, n):
                L += f.prog(times[i] - 0.85, 1.05)
            return L
        L = float(n - 1)
        for j in range(1, n):  # shown[j] = geo[n-1-j]
            L -= f.prog(times_shown[j] - 0.85, 1.05)
        return L

    L = level_at(f.t)
    dL = (level_at(f.t + 1 / 30) - level_at(f.t - 1 / 30)) * 15
    beat = f.beat_pulse()

    # child offsets: where level i-1 sits inside level i (in units of level i's radius)
    rng = f.rng("scale-offsets")
    centres = [(0.0, 0.0)]
    for i in range(1, n):
        k = kinds[i]
        child = str(geo[i - 1].get("label", "")).lower().replace("'s", "").split()
        ang = rng.random() * 2 * math.pi
        if k == "orbit":
            on_ring = any(w in str(geo[i].get("label", "")).lower() for w in child if len(w) > 2)
            d = 1.0 if on_ring else 0.0
            if on_ring:
                kinds[i] = "orbit_ring"
        elif k == "solar":
            d = 0.033
        elif k == "galaxy":
            d = 0.52
        elif k == "city":
            d, ang = 0.17, math.atan2(1, 2)
        elif k.startswith("body:"):
            d = 0.38
        else:
            d = 0.3
        R = _SCALE_STEP ** i
        px, py = centres[-1]
        centres.append((px - math.cos(ang) * d * R, py - math.sin(ang) * d * R))

    zoom = _SCALE_STEP ** (-L) * _SCALE_BASE
    i_lo = min(int(L), n - 1)
    i_hi = min(i_lo + 1, n - 1)
    fr = L - i_lo
    foc = (lerp(centres[i_lo][0], centres[i_hi][0], fr), lerp(centres[i_lo][1], centres[i_hi][1], fr))
    cam = (foc[0] * 0.55, foc[1] * 0.55)
    CX, CY = 960, 500

    def scr(i):
        return CX + (centres[i][0] - cam[0]) * zoom, CY + (centres[i][1] - cam[1]) * zoom, (_SCALE_STEP ** i) * zoom

    # ---- background: space, unless something fills the whole screen
    engulf = None
    for i in range(n):
        x, y, r = scr(i)
        ec = _engulf_color(kinds[i])
        if ec and math.hypot(max(abs(x - CX) - 0, 0), abs(y - CY)) + 1250 < r * (0.9 if kinds[i] in ("city", "country") else 1.0):
            engulf = i
            break
    gradient_bg(f, "#040616", "#010106")
    nebula_glow(f, key="scale-neb", alpha=0.3)
    starfield(f, n=360, drift=(0, 0), key="scale-stars")
    # radial dust streaks: they rush inward on a zoom out, outward on a zoom in
    rngs = f.rng("scale-dust")
    nd = 160
    ang = rngs.random(nd) * 2 * math.pi
    u = (rngs.random(nd) + L * 0.9) % 1.0
    rad = 80 + (1 - u) ** 1.5 * 1300
    spd = clamp(abs(dL) / 1.2)
    if spd > 0.03:
        for j in range(nd):
            r0 = rad[j]
            r1 = r0 * (1 + 0.35 * spd)
            f.c.drawLine(CX + math.cos(ang[j]) * r0, CY + math.sin(ang[j]) * r0,
                         CX + math.cos(ang[j]) * r1, CY + math.sin(ang[j]) * r1,
                         paint(INK if j % 5 else c_, 0.35 * spd, stroke=1.5))
    start = 0
    if engulf is not None:
        f.c.drawPaint(paint(_engulf_color(kinds[engulf]), 1))
        if kinds[engulf] == "country":  # a hint of terrain
            soft_light(f, 500, 300, 900, "#6d8f4a", 0.25)
            soft_light(f, 1500, 800, 800, "#2a4a2a", 0.3)
        elif kinds[engulf].startswith("body:earth"):
            soft_light(f, 600, 400, 900, "#1d5fa8", 0.35)
        start = engulf

    # ---- the nested scales, biggest first
    for i in range(n - 1, -1, -1):
        if engulf is not None and i > engulf:  # hidden behind the level that fills the screen
            continue
        x, y, r = scr(i)
        if r < 1.2 or r > 30000:
            continue
        if r > 2400 and i != engulf and not kinds[i].startswith("body:"):
            continue  # far too big to read yet: it appears one step before it's named
        a = clamp((r - 2) / 10) * (1 if i != engulf or kinds[i] in ("city", "country") else 0)
        if a <= 0:
            continue
        _scale_glyph(f, kinds[i], x, y, r, a, c_, i, beat)

    _zoom_blur(f, clamp(abs(dL) * 0.07, 0, 0.14), CX, CY)

    # ---- HUD
    cur = int(round(L))
    cur = min(max(cur, 0), n - 1)
    lv = geo[cur]
    sw_t = abs(L - cur)
    pop = 1 + 0.15 * math.exp(-8 * max(0.5 - sw_t, 0)) if sw_t < 0.5 else 1
    lines, size = _fit(str(lv.get("label", "")).upper(), 1300, 70, "bold", 40, 1)
    f.c.save()
    f.c.translate(CX, 190)
    f.c.scale(pop * (1 + 0.02 * beat), pop * (1 + 0.02 * beat))
    text(f, lines[0], 0, 24, size=size, glow_color=c_, stroke=6)
    f.c.restore()
    # size bar: spans the current level's real width on screen
    bar = (_SCALE_STEP ** (cur - L)) * _SCALE_BASE * 2
    bar = clamp(bar, 60, 900)
    by = 812
    f.c.drawLine(CX - bar / 2, by, CX + bar / 2, by, paint(c_, 0.3, stroke=14, add=True))
    f.c.drawLine(CX - bar / 2, by, CX + bar / 2, by, paint(INK, 1, stroke=3))
    for sx in (CX - bar / 2, CX + bar / 2):
        f.c.drawLine(sx, by - 16, sx, by + 16, paint(INK, 1, stroke=3))
    if lv.get("size_text"):
        text(f, str(lv["size_text"]), CX, by - 26, size=38, color=INK, weight="bold", stroke=5)
    # ladder of levels on the right
    lx, ly0, ly1 = W - 200, 740, 280
    shade = skia.GradientShader.MakeLinear([skia.Point(W - 480, 0), skia.Point(W, 0)], [col("#000000", 0), col("#000000", 0.6)])
    f.c.drawRect(skia.Rect.MakeLTRB(W - 480, ly1 - 60, W, ly0 + 50), skia.Paint(Shader=shade))
    f.c.drawLine(lx, ly0, lx, ly1, paint(DIM, 0.5, stroke=2))
    for i in range(n):
        y = lerp(ly0, ly1, i / max(n - 1, 1))
        on = i == cur
        f.c.drawLine(lx - 12, y, lx + 12, y, paint(c_ if on else DIM, 1 if on else 0.6, stroke=3))
        lab, ls = _fit(str(geo[i].get("label", "")), 300, 30, "semibold", 30, 1)
        text(f, lab[0], lx - 26, y + 10, size=ls, color=INK if on else "#b4bbd6", align="right", weight="semibold",
             a=1 if on else 0.8, stroke=4)
    my_ = lerp(ly0, ly1, L / max(n - 1, 1))
    tri = skia.Path()
    tri.moveTo(lx + 16, my_)
    tri.lineTo(lx + 36, my_ - 12)
    tri.lineTo(lx + 36, my_ + 12)
    tri.close()
    f.c.drawPath(tri, paint(c_, 1))
    glow(f, lx, my_, 7, c_)
    text(f, f"ZOOM  1 : {_human(_SCALE_STEP ** L)}", 190, 140, size=30, color=DIM, align="left", weight="semibold")
    text(f, "not to scale: each step is really far bigger", 190, 874, size=30, color="#b4bbd6", align="left", weight="body",
         a=0.8, stroke=4)


def _scale_glyph(f, kind, x, y, r, a, c_, idx, beat):
    c = f.c
    if x + r < -200 or x - r > W + 200 or y + r < -200 or y - r > H + 200:
        if kind not in ("orbit", "orbit_ring", "solar", "galaxy"):
            return
    if kind == "person":
        if r < 6:
            glow(f, x, y, 4, c_, a)
            return
        h = r * 1.6
        soft_light(f, x, y + h * 0.48, r * 0.9, "#000000", 0.0)
        c.drawOval(skia.Rect.MakeLTRB(x - r * 0.45, y + h * 0.44, x + r * 0.45, y + h * 0.56), paint("#000000", 0.45 * a))
        soft_light(f, x, y, r * 1.4, c_, 0.2 * a)
        pp = paint(INK, a)
        c.drawCircle(x, y - h * 0.38, h * 0.1, pp)
        c.drawRRect(_rrect(x - h * 0.11, y - h * 0.26, h * 0.22, h * 0.36, h * 0.07), pp)
        lp = paint(INK, a, stroke=h * 0.075)
        c.drawLine(x - h * 0.05, y + h * 0.08, x - h * 0.08, y + h * 0.46, lp)
        c.drawLine(x + h * 0.05, y + h * 0.08, x + h * 0.08, y + h * 0.46, lp)
        sw = 0.1 * math.sin(f.t * 2)
        c.drawLine(x - h * 0.1, y - h * 0.22, x - h * (0.2 + sw), y + h * 0.05, paint(INK, a, stroke=h * 0.06))
        c.drawLine(x + h * 0.1, y - h * 0.22, x + h * 0.22, y - h * (0.42 + 0.03 * math.sin(f.t * 5)),
                   paint(INK, a, stroke=h * 0.06))  # waving
        ring(f, x, y, r * 1.15, 4, c_, 0.5 * a * (0.6 + 0.4 * beat))
    elif kind == "city":
        if r < 90:  # far away a city is a cluster of lights
            rng = f.rng(f"cityfar{idx}")
            soft_light(f, x, y, r * 2.0, GOLD, 0.5 * a)
            dots(f, x + rng.normal(0, 0.35, 80) * r, y + rng.normal(0, 0.35, 80) * r, max(1.0, r * 0.04), 0.9 * a,
                 "#ffd98a", add=True)
            glow(f, x, y, max(r * 0.18, 3), "#fff1c4", a)
            return
        rng = f.rng(f"city{idx}")
        c.drawCircle(x, y, r * 0.95, paint("#161b26", a))
        soft_light(f, x, y, r * 1.05, "#2a3142", 0.5 * a, add=False)
        cell = 0.12
        g = np.arange(-1, 1 + 1e-6, cell)
        bx, by = np.meshgrid(g[:-1], g[:-1])
        bx, by = bx.ravel(), by.ravel()
        keep = (bx + cell / 2) ** 2 + (by + cell / 2) ** 2 < (0.85 + 0.15 * rng.random(len(bx))) ** 2
        shade = rng.random(len(bx))
        for j in np.nonzero(keep)[0]:
            x0, y0 = x + (bx[j] + 0.012) * r, y + (by[j] + 0.012) * r
            if x0 > W + 50 or y0 > H + 50 or x0 + cell * r < -50 or y0 + cell * r < -50:
                continue
            c.drawRect(skia.Rect.MakeXYWH(x0, y0, (cell - 0.024) * r, (cell - 0.024) * r),
                       paint(mix("#1e2533", "#3a4256", shade[j]), a))
        nl = 700
        lxs = x + (rng.random(nl) * 2 - 1) * r * 0.85
        lys = y + (rng.random(nl) * 2 - 1) * r * 0.85
        inside = (lxs - x) ** 2 + (lys - y) ** 2 < (r * 0.85) ** 2
        tw = 0.5 + 0.5 * np.sin(f.t * 2 + rng.random(nl) * 6)
        dots(f, lxs[inside], lys[inside], clamp(r * 0.004, 1.0, 2.6), (0.3 + 0.4 * tw[inside]) * a, GOLD, add=True)
        for k in range(-1, 2):  # main avenues with moving car lights
            yy = y + k * 0.36 * r
            c.drawLine(x - r * 0.9, yy, x + r * 0.9, yy, paint("#ffcf7a", 0.35 * a, stroke=max(2, r * 0.012), add=True))
            cars = (rng.random(12) + f.t * 0.05 * (1 if k % 2 else -1)) % 1.0
            dots(f, x - r * 0.9 + cars * r * 1.8, np.full(12, yy), max(1.5, r * 0.006), 0.9 * a, "#ffffff", add=True)
        soft_light(f, x, y, r * 1.2, GOLD, 0.15 * a)
    elif kind == "country":
        rng = f.rng(f"country{idx}")
        harm = [(k, rng.normal(0, 0.12 / k), rng.random() * 6.28) for k in range(2, 9)]
        path = skia.Path()
        for j in range(97):
            th = j / 96 * 2 * math.pi
            rr = r * (0.82 + sum(am * math.cos(k * th + ph) for k, am, ph in harm))
            pt = (x + math.cos(th) * rr, y + math.sin(th) * rr * 0.86)
            path.moveTo(*pt) if j == 0 else path.lineTo(*pt)
        path.close()
        land = skia.GradientShader.MakeRadial(skia.Point(x - r * 0.3, y - r * 0.3), r * 1.4,
                                             [col("#6f8f45", a), col("#3f6b32", a), col("#7a6a48", a)], [0, 0.6, 1])
        c.drawPath(path, paint("#bfe6ff", 0.25 * a, stroke=max(2, r * 0.03), add=True))
        c.drawPath(path, skia.Paint(AntiAlias=True, Shader=land))
        c.drawPath(path, paint("#e8f4ff", 0.6 * a, stroke=max(1.5, r * 0.006)))
        bp = paint("#ffffff", 0.3 * a, stroke=max(1.0, r * 0.004))
        bp.setPathEffect(skia.DashPathEffect.Make([max(4, r * 0.02), max(4, r * 0.02)], 0))
        for k in range(3):
            a0 = rng.random() * 6.28
            pts = [(x + math.cos(a0) * r * 0.75 * (1 - j / 10) + rng.normal(0, r * 0.03),
                    y + math.sin(a0) * r * 0.65 * (1 - j / 10) + rng.normal(0, r * 0.03)) for j in range(11)]
            c.drawPath(line_path(pts, smooth=True), bp)
        nl = 14
        lxs, lys = x + rng.normal(0, 0.35, nl) * r, y + rng.normal(0, 0.3, nl) * r
        dots(f, lxs, lys, clamp(r * 0.012, 1.5, 5.0), 0.8 * a, GOLD, add=True)
    elif kind.startswith("body:"):
        bk = kind[5:]
        if r > 2600:
            return
        if r > 420:  # render big bodies at a capped size and scale the canvas up (keeps it fast)
            k = r / 420
            c.save()
            c.translate(x, y)
            c.scale(k, k)
            body(f, bk, 0, 0, 420, light=(-0.6, -0.35, 0.7), alpha=a, seed_key=f"scale{idx}")
            c.restore()
        else:
            body(f, bk, x, y, max(r, 2), light=(-0.6, -0.35, 0.7), alpha=a, seed_key=f"scale{idx}")
    elif kind in ("orbit", "orbit_ring", "solar"):
        if kind == "solar":
            fracs = [0.013, 0.024, 0.033, 0.05, 0.17, 0.32, 0.64, 1.0]
        else:
            fracs = [1.0]
        for k, fr_ in enumerate(fracs):
            rr = r * fr_
            if rr < 3 or rr > 6000:
                continue
            op = paint(c_ if fr_ == 1.0 else DIM, 0.7 * a, stroke=2.5)
            op.setPathEffect(skia.DashPathEffect.Make([14, 12], -f.t * 25))
            c.drawCircle(x, y, rr, op)
            c.drawCircle(x, y, rr, paint(c_, 0.12 * a, stroke=10, add=True))
            ang = f.t * 0.25 / (fr_ ** 0.5 + 0.2) + k * 1.7 + idx
            if kind == "orbit":  # the body that travels this orbit
                ang = math.pi * 0.25 + f.t * 0.2
            mx, my = x + math.cos(ang) * rr, y + math.sin(ang) * rr
            if kind == "orbit" and -50 < mx < W + 50 and -50 < my < H + 50:  # e.g. the Moon on the Moon's orbit
                body(f, "moon", mx, my, max(6, r * 0.03), alpha=a, seed_key="scale-moon")
        if kind in ("solar", "orbit_ring"):  # the star at the centre (its size exaggerated so it shows)
            soft_light(f, x, y, r * 0.6, GOLD, 0.12 * a)
            sr = max(10, r * (0.014 if kind == "orbit_ring" else 0.004))  # exaggerated a few times so it shows
            body(f, "sun", x, y, sr, alpha=a)
            if kind == "orbit_ring" and r > 60:
                text(f, "SUN", x, y + sr + 46, size=30, color=GOLD, weight="semibold", a=a)
    elif kind == "galaxy":
        rng = f.rng(f"gal{idx}")
        nn = 5000
        d = rng.random(nn) ** 0.7
        arms = rng.integers(0, 4, nn)
        ang = arms * math.pi / 2 + d * 5.0 + rng.normal(0, 0.22 + 0.2 * (1 - d), nn) + f.t * 0.02
        gx, gy = x + np.cos(ang) * d * r * 1.25, y + np.sin(ang) * d * r * 0.7
        soft_light(f, x, y, r * 1.3, "#7a5cff", 0.18 * a)
        warm = rng.random(nn) < 0.35
        dots(f, gx[~warm], gy[~warm], 0.6 + (1 - d[~warm]) * 1.2, a * (0.2 + 0.6 * (1.05 - d[~warm])), c_, add=True)
        dots(f, gx[warm], gy[warm], 0.6 + (1 - d[warm]) * 1.2, a * (0.2 + 0.6 * (1.05 - d[warm])), "#ffd9a0", add=True)
        soft_light(f, x, y, r * 0.5, GOLD, 0.6 * a)
        glow(f, x, y, r * 0.08, "#fff1c4", 0.8 * a)
    else:
        ring(f, x, y, r, max(3, r * 0.02), c_, 0.8 * a)
        rp = paint(c_, 0.3 * a, stroke=1.5)
        rp.setPathEffect(skia.DashPathEffect.Make([8, 10], 0))
        c.drawCircle(x, y, r * 0.7, rp)
        c.drawLine(x - r, y, x + r, y, rp)
        c.drawLine(x, y - r, x, y + r, rp)


# ================================================================ 6. versus showdown

_VS_DEFAULT_ROUNDS = [
    {"stat": "Diameter", "left": 12742, "right": 6779, "left_text": "12,742 km", "right_text": "6,779 km"},
    {"stat": "Gravity", "left": 9.8, "right": 3.7, "left_text": "9.8 m/s²", "right_text": "3.7 m/s²"},
    {"stat": "Air pressure", "left": 1013, "right": 6, "left_text": "1,013 mbar", "right_text": "6 mbar"},
    {"stat": "Moons", "left": 1, "right": 2, "left_text": "1", "right_text": "2"},
]
_VS_COLORS = [(CYAN, RED), ("#9b7bff", GOLD), (GREEN, "#ff5ad1"), (CYAN, "#ff8a3d"), ("#9fe6ff", "#ff5ad1")]


@template("versus_showdown", kind="cinematic",
          sfx=lambda p: [Sfx("808", p("vs_at") or 0.5)]
          + [Sfx("whoosh", _sfx_at(r, 1.2 + 0.85 * i), gain_db=-6) for i, r in enumerate((p("rounds") or _VS_DEFAULT_ROUNDS)[:2])]
          + [Sfx("riser", p("winner_at") or "end", offset=-1.3 if p("winner_at") else -2.2, dur=1.2),
             Sfx("impact", p("winner_at") or "end", offset=0 if p("winner_at") else -0.9)])
def versus_showdown(f, p):
    """A fight-night face-off between two bodies: split-colour arena, a lightning 'VS' slam, then round by round a
    stat appears and both bars fill and compare (the round's winner flares and scores a point). On the winner beat
    the loser's bars drain and it dims, and the winner gets a spotlight, a halo and a WINNER slam.
    Use for "Earth vs Mars", "Jupiter vs the Sun", "which would win" comparisons with 2-5 numbers.
    params: left {name, kind}, right {name, kind}, rounds [{stat, left, right, left_text, right_text, better, at}]
    (2-5; left/right are numbers for the bars, *_text how they're shown, better = "lower" if smaller wins;
    at = word the round appears on), winner (left|right, default whoever won most rounds), vs_at, winner_at, color"""
    left = p("left") or {"name": "Earth", "kind": "earth"}
    right = p("right") or {"name": "Mars", "kind": "mars"}
    rounds = p("rounds") or _VS_DEFAULT_ROUNDS
    nr = len(rounds)
    lc, rc = _VS_COLORS[int(rand(f, "vs_cols", 0, len(_VS_COLORS) - 1e-6))]
    if p("color"):
        lc = accent(f, p)
    t_vs = when(f, p("vs_at"), 0.07)
    r_times = _beats(f, rounds, 0.22, 0.68)
    t_win = when(f, p("winner_at"), 0.82)
    beat = f.beat_pulse()

    # who wins each round
    wins = []
    for rd in rounds:
        lv, rv = _parse_num(rd.get("left")), _parse_num(rd.get("right"))
        lv, rv = (lv or 0.0), (rv or 0.0)
        better_low = str(rd.get("better", "higher")).lower().startswith("low")
        wins.append(0 if lv == rv else (("L" if lv < rv else "R") if better_low else ("L" if lv > rv else "R")))
    winner = p("winner")
    if winner not in ("left", "right"):
        winner = "left" if wins.count("L") >= wins.count("R") else "right"
    wsym = "L" if winner == "left" else "R"
    sw = f.t - t_win
    won = clamp(sw / 0.3) if sw > 0 else 0.0
    s_vs = f.t - t_vs

    LX, RX, BY, BR = 360, 1560, 420, 178
    wx = LX if winner == "left" else RX
    shake = (22 * math.exp(-s_vs * 4) if s_vs > 0 else 0) + (18 * math.exp(-sw * 3.5) if sw > 0 else 0)
    zoom = 1.0 + 0.012 * beat + (0.03 * ease_in_out(clamp(sw / 2)) if sw > 0 else 0)
    camx = 960 + ((wx - 960) * 0.12 * ease_in_out(clamp(sw / 2)) if sw > 0 else 0)

    # ---- arena: two colour fields split by a slanted seam
    f.c.clear(col("#030308"))
    for side, colr in ((0, lc), (1, rc)):
        f.c.save()
        clip = skia.Path()
        if side == 0:
            clip.moveTo(-50, -50); clip.lineTo(1040, -50); clip.lineTo(880, H + 50); clip.lineTo(-50, H + 50)
        else:
            clip.moveTo(1040, -50); clip.lineTo(W + 50, -50); clip.lineTo(W + 50, H + 50); clip.lineTo(880, H + 50)
        clip.close()
        f.c.clipPath(clip, doAntiAlias=True)
        sh = skia.GradientShader.MakeRadial(skia.Point(LX if side == 0 else RX, BY), 1100,
                                           [col(mix(colr, "#000000", 0.55)), col(mix(colr, "#000000", 0.9)), col("#020205")],
                                           [0, 0.5, 1])
        f.c.drawPaint(skia.Paint(Shader=sh))
        starfield(f, n=170, drift=(-6 if side == 0 else 6, 0), key=f"vs-stars{side}", alpha=0.7)
        f.c.restore()
    # embers rising on both sides
    rnge = f.rng("vs-embers")
    ne = 140
    ex_ = rnge.random(ne) * W
    ey_ = (rnge.random(ne) * 1200 - f.t * (40 + 90 * rnge.random(ne))) % 1200 - 60
    sel = ex_ < 960
    dots(f, ex_[sel] + 12 * np.sin(f.t + ey_[sel] * 0.01), ey_[sel], 1 + 2 * rnge.random(sel.sum()), 0.5, lc, add=True)
    dots(f, ex_[~sel] + 12 * np.sin(f.t + ey_[~sel] * 0.01), ey_[~sel], 1 + 2 * rnge.random((~sel).sum()), 0.5, rc, add=True)

    with camera(f, camx, 540, zoom=zoom, shake=shake):
        # the seam, crackling with lightning on the VS slam
        f.c.drawLine(1040, -50, 880, H + 50, paint(INK, 0.25, stroke=18, add=True))
        f.c.drawLine(1040, -50, 880, H + 50, paint(INK, 0.8, stroke=3))
        if 0 < s_vs < 1.6:
            rngl = f.rng(f"vs-bolt{int(f.t * 12)}")
            pts = []
            for j in range(19):
                yy = -40 + j * (H + 80) / 18
                xx = lerp(1040, 880, j / 18) + rngl.normal(0, 26)
                pts.append((xx, yy))
            bolt_a = clamp(1.6 - s_vs)
            f.c.drawPath(line_path(pts), paint("#ffffff", 0.35 * bolt_a, stroke=16, add=True))
            f.c.drawPath(line_path(pts), paint("#ffffff", bolt_a, stroke=3.5))

        # the contenders
        for side, spec, x, colr in ((0, left, LX, lc), (1, right, RX, rc)):
            is_w = (side == 0) == (winner == "left")
            enter = 1.0  # both contenders are in place from frame 0; they just settle in
            bx = x + (1 - ease_out(f.prog(0, 0.8))) * (-70 if side == 0 else 70)
            bob = 8 * math.sin(f.t * 1.3 + side * 2)
            lose = won if not is_w else 0
            r = BR * (1 + 0.03 * beat) * (1 - 0.12 * lose)
            by = BY + bob + 30 * lose
            if is_w and won > 0:  # spotlight from above
                cone = skia.Path()
                cone.moveTo(x - 70, -40); cone.lineTo(x + 70, -40); cone.lineTo(x + 330, BY + 260); cone.lineTo(x - 330, BY + 260)
                cone.close()
                csh = skia.GradientShader.MakeLinear([skia.Point(0, -40), skia.Point(0, BY + 260)],
                                                    [col("#ffffff", 0.32 * won), col("#ffffff", 0.0)])
                f.c.drawPath(cone, skia.Paint(AntiAlias=True, Shader=csh, BlendMode=skia.BlendMode.kPlus))
                for k in range(12):  # slow rays behind the winner
                    a = k / 12 * 2 * math.pi + f.t * 0.25
                    f.c.drawLine(x + math.cos(a) * r * 1.2, by + math.sin(a) * r * 1.2,
                                 x + math.cos(a) * r * 2.3, by + math.sin(a) * r * 2.3,
                                 paint(GOLD, 0.25 * won, stroke=10, add=True))
            soft_light(f, bx, by, r * 2.2, colr, 0.25 + 0.1 * beat)
            body(f, spec.get("kind", "rocky"), bx, by, r, light=(0.75 if side == 0 else -0.75, -0.35, 0.55),
                 seed_key=f"vs{side}", brightness=1 - 0.55 * lose)
            halo(f, bx, by, r * 0.98, r * 1.25, colr, 0.5 * (1 - lose))
            if lose > 0:
                f.c.drawCircle(bx, by, r, paint("#000000", 0.45 * lose))
            if is_w and won > 0:
                ring(f, bx, by, r * 1.18 + 6 * beat, 10, GOLD, 0.85 * won)
                shockwave(f, bx, by, t_win, speed=900, life=1.5, color=GOLD, width=22)
                particles(f, bx, by, t_win, n=200, speed=(200, 900), life=(0.6, 2.2), size=(2, 5), color=GOLD,
                          key="vs-confetti", gravity=(0, 300))
            nl, ns = _fit(str(spec.get("name", "")).upper(), 460, 60, "bold", 34, 1)
            text(f, nl[0], bx, BY + BR + 92, size=ns, color=INK if not lose else DIM, glow_color=colr, a=enter, stroke=5)
            # running score
            score = sum(1 for i, w_ in enumerate(wins) if w_ == ("L" if side == 0 else "R") and f.t > r_times[i] + 0.6)
            text(f, str(score), bx, BY + BR + 180, size=72, color=colr, weight="bold", a=enter, stroke=5)

        # the rounds: stat bars that fill from the centre outwards
        top = 300
        row = min(125, 420 / max(nr, 1))
        shown = sum(1 for tt in r_times if f.t > tt)
        if shown:  # a glass column behind the stats keeps them readable over the seam
            col_h = (shown - 1) * row + 110
            f.c.drawRRect(_rrect(575, top - 62, 770, col_h, 22), paint("#04040a", 0.55))
            f.c.drawRRect(_rrect(575, top - 62, 770, col_h, 22), paint(INK, 0.12, stroke=2))
        for i, rd in enumerate(rounds):
            s = f.t - r_times[i]
            if s <= 0:
                continue
            y = top + i * row
            ap = clamp(s / 0.25)
            lv, rv = abs(_parse_num(rd.get("left")) or 0.0), abs(_parse_num(rd.get("right")) or 0.0)
            mx_ = max(lv, rv, 1e-9)
            use_log = min(lv, rv) > 0 and mx_ / max(min(lv, rv), 1e-9) > 40
            if use_log:
                lo = min(lv, rv) / 10
                fl, frr = (math.log(lv / lo) / math.log(mx_ / lo), math.log(rv / lo) / math.log(mx_ / lo))
            else:
                fl, frr = lv / mx_, rv / mx_
            fill = ease_out(clamp((s - 0.15) / 0.8))
            drain = ease_in_out(clamp(sw / 0.8)) if sw > 0 else 0
            fl_now = fl * fill * (1 - drain if winner == "right" else 1)
            fr_now = frr * fill * (1 - drain if winner == "left" else 1)
            stat = str(rd.get("stat", "")).upper() + (" (LOG)" if use_log else "")
            sl, ss = _fit(stat, 300, 34, "semibold", 30, 1)
            pw_ = font(ss, "semibold").measureText(sl[0]) + 40
            f.c.drawRRect(_rrect(960 - pw_ / 2, y - 34, pw_, 48, 24), paint("#000000", 0.6 * ap))
            f.c.drawRRect(_rrect(960 - pw_ / 2, y - 34, pw_, 48, 24), paint(INK, 0.35 * ap, stroke=2))
            text(f, sl[0], 960, y + 2, size=ss, weight="semibold", a=ap)
            BW, gap_ = 310, 40
            yb = y + 34
            for side, frac, colr in ((0, fl_now, lc), (1, fr_now, rc)):
                x0 = 960 - gap_ if side == 0 else 960 + gap_
                dirn = -1 if side == 0 else 1
                f.c.drawRRect(_rrect(min(x0, x0 + dirn * BW), yb - 10, BW, 20, 10), paint("#ffffff", 0.07 * ap))
                if frac > 0.002:
                    x1 = x0 + dirn * BW * frac
                    rr = _rrect(min(x0, x1), yb - 10, abs(x1 - x0), 20, 10)
                    won_round = wins[i] == ("L" if side == 0 else "R") and s > 0.95
                    f.c.drawRRect(rr, paint(colr, 0.95))
                    if won_round:
                        f.c.drawRRect(rr, paint("#ffffff", 0.35 * math.exp(-(s - 0.95) * 3) + 0.1 * beat))
                        soft_light(f, x1, yb, 60, colr, 0.6)
                    glow(f, x1, yb, 6, colr, 0.8)
                vt = rd.get("left_text" if side == 0 else "right_text") or _human(lv if side == 0 else rv)
                vtl, vts = _fit(str(vt), 210, 34, "bold", 30, 1)
                text(f, vtl[0], 960 + dirn * 190, y + 2, size=vts, color=colr if wins[i] == ("L" if side == 0 else "R") else INK,
                     align="right" if side == 0 else "left", weight="bold", a=ap * clamp((s - 0.4) / 0.3))

    # ---- VS slam, then it tucks up above the rounds
    tuck = f.prog(r_times[0] - 0.5, 0.5) if nr else 0
    vs_size = lerp(230, 100, tuck)
    vy = lerp(500, 172, tuck)
    if s_vs > 0:
        slam_text(f, "VS", 960, vy, t_vs, size=vs_size, glow_color=mix(lc, rc, 0.5), snap=False)
    if sw > 0:
        slam_text(f, "WINNER", wx, 190, t_win, size=110, glow_color=GOLD, snap=False)
    text(f, "sizes not to scale", 190, 868, size=30, color=DIM, align="left", weight="body", a=0.7)
    flash(f, t_vs, dur=0.3, color="#ffffff", peak=0.6)
    flash(f, t_win, dur=0.4, color="#fff1c4", peak=0.55)
