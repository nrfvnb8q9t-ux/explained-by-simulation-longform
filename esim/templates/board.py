"""Whiteboard / chalkboard templates: diagrams drawn stroke by stroke as the narrator explains."""

import math

import skia

from esim.templates import Sfx, accent, pick, rand, template, when
from esim.engine import *  # noqa: F401,F403

BOARDS = {
    "chalk": {"bg": CHALK_BG, "ink": INK, "dim": "#9aa6b2", "colors": [GOLD, CYAN, "#ff8fb1", GREEN]},
    "blueprint": {"bg": "#0b2a4a", "ink": "#e8f4ff", "dim": "#7fb0d9", "colors": ["#ffffff", "#9fe6ff", "#ffd36b", "#ff9f7a"]},
    "dark_grid": {"bg": "#0d0f14", "ink": "#f2f5ff", "dim": "#6b7385", "colors": [CYAN, "#ff5ad1", GOLD, GREEN]},
    "whiteboard": {"bg": "#f4f1ea", "ink": "#1d2230", "dim": "#7a7f8c", "colors": ["#d7263d", "#1b6ca8", "#2e933c", "#f08a24"]},
}


def board(f, p):
    """Draw this scene's board background and return its colour set."""
    style = p("board") or pick(f, "board", ["chalk", "chalk", "blueprint", "dark_grid", "whiteboard"])
    b = BOARDS[style]
    f.c.clear(col(b["bg"]))
    rng = f.rng("smudge")
    if style == "chalk":
        for _ in range(14):
            soft_light(f, rng.random() * W, rng.random() * H, 120 + rng.random() * 380, INK, 0.015 + rng.random() * 0.025, add=False)
    elif style in ("blueprint", "dark_grid"):
        gp = paint(b["dim"], 0.12 if style == "blueprint" else 0.08, stroke=1)
        step = 60
        for x in range(0, W + step, step):
            f.c.drawLine(x, 0, x, H, gp)
        for y in range(0, H + step, step):
            f.c.drawLine(0, y, W, y, gp)
    else:
        for _ in range(8):
            soft_light(f, rng.random() * W, rng.random() * H, 200 + rng.random() * 400, "#000000", 0.02, add=False)
    return b


def pen(f, b, color=None, width=5, k=0):
    """A hand-drawn stroke in this board's style. Different k gives a different wobble."""
    return chalk(color or b["ink"], width, a=0.95, roughness=1.5, seed=(f.seed + k * 7919) % 99991)


def write(f, b, s, x, y, at, size=64, color=None, align="center", dur=None):
    weight = "hand" if b is not BOARDS["dark_grid"] else "medium"
    return text(f, s, x, y, size=size, color=color or b["ink"], align=align, weight=weight,
                reveal=f.prog(at, dur or max(0.4, len(s) * 0.045), ease=lambda v: clamp(v)), a=0.95)


def _step_times(f, items, start=0.4, gap=None):
    gap = gap or max((f.dur - start - 1.0) / max(len(items), 1), 0.5)
    return [f.time(it["at"]) if isinstance(it, dict) and it.get("at") else start + i * gap for i, it in enumerate(items)]


def _chalk_sfx(p, key):
    items = p(key, [])
    return [Sfx("chalk", it.get("at", 0.4 + i * 1.2)) for i, it in enumerate(items[:8]) if isinstance(it, dict)]


# ---------------------------------------------------------------- nodes and arrows

@template("board_diagram", kind="board", sfx=lambda p: _chalk_sfx(p, "nodes"))
def board_diagram(f, p):
    """A hand-drawn diagram: 2-5 labelled things (circles, boxes or sketched planets) joined by labelled arrows,
    each appearing as it's mentioned.
    params: title, nodes [{label, shape (circle|box|planet|star), at}], links [{from, to, label, at}] (indexes),
    layout (row|triangle|arc), board (chalk|blueprint|dark_grid|whiteboard)"""
    b = board(f, p)
    nodes = p("nodes", [{"label": "Sun", "shape": "star"}, {"label": "Earth", "shape": "planet"}])
    n = len(nodes)
    layout = p("layout") or pick(f, "layout", ["row", "arc", "triangle"] if n >= 3 else ["row"])
    if layout == "triangle" and n >= 3:
        pos = [(960, 330), (560, 760), (1360, 760)] + [(960 + 380 * (i - 3), 900) for i in range(3, n)]
    elif layout == "arc":
        pos = [(260 + i * (1400 / max(n - 1, 1)), 620 - 220 * math.sin(math.pi * i / max(n - 1, 1))) for i in range(n)]
    else:
        pos = [(260 + i * (1400 / max(n - 1, 1)), 560) for i in range(n)]
    times = _step_times(f, nodes)
    if p("title"):
        write(f, b, p("title"), 960, 130, 0.2, size=72)
    for i, (nd, (x, y), t0) in enumerate(zip(nodes, pos, times)):
        c_ = b["colors"][i % len(b["colors"])]
        shape = nd.get("shape", "circle")
        pr = f.prog(t0, 0.8)
        pp = pen(f, b, c_, 6, i)
        if pr <= 0:  # dashed ghost of what's coming, so the board is never blank
            gp = paint(b["dim"], 0.75, stroke=6)
            gp.setPathEffect(skia.DashPathEffect.Make([14, 12], f.t * 20))
            if shape == "box":
                f.c.drawRect(skia.Rect.MakeXYWH(x - 130, y - 80, 260, 160), gp)
            else:
                f.c.drawCircle(x, y, 110 if shape in ("star", "circle") else 85, gp)
            text(f, "?", x, y + 30, size=96, color=b["dim"], a=0.8, weight="hand")
        if shape == "box":
            path = skia.Path().addRect(skia.Rect.MakeXYWH(x - 130, y - 80, 260, 160))
        else:
            path = skia.Path().addCircle(x, y, 110 if shape in ("star", "circle") else 85)
        draw_partial(f, path, pr, pp)
        if shape == "star" and pr >= 1:
            for k in range(10):
                a = k / 10 * 6.28
                r0, r1 = 128, 128 + 30 * clamp(f.since(t0) * 3 - 2 - k * 0.05)
                f.c.drawLine(x + math.cos(a) * r0, y + math.sin(a) * r0, x + math.cos(a) * r1, y + math.sin(a) * r1, pp)
        if shape == "planet" and pr >= 1:
            draw_partial(f, line_path([(x - 85, y - 15), (x - 20, y - 40), (x + 40, y - 10), (x + 85, y - 25)], True),
                         f.prog(t0 + 0.6, 0.5), pen(f, b, c_, 4, i + 20))
        write(f, b, nd.get("label", ""), x, y + 180, t0 + 0.3, size=56, color=c_)
    for j, ln in enumerate(p("links", [{"from": i, "to": i + 1} for i in range(n - 1)])):
        a, c2 = pos[ln["from"]], pos[ln["to"]]
        t0 = f.time(ln["at"]) if ln.get("at") else max(times[ln["from"]], times[ln["to"]]) + 0.6
        ang = math.atan2(c2[1] - a[1], c2[0] - a[0])
        off = 140
        arrow(f, a[0] + math.cos(ang) * off, a[1] + math.sin(ang) * off, c2[0] - math.cos(ang) * off,
              c2[1] - math.sin(ang) * off, f.prog(t0, 0.9), pen(f, b, b["ink"], 4, 50 + j))
        if ln.get("label"):
            write(f, b, ln["label"], (a[0] + c2[0]) / 2, (a[1] + c2[1]) / 2 - 40, t0 + 0.5, size=44, color=b["dim"])


# ---------------------------------------------------------------- notes

@template("board_notes", kind="board", sfx=lambda p: _chalk_sfx(p, "lines"))
def board_notes(f, p):
    """Key points written on the board one by one, with the most important one circled or underlined.
    params: title, lines [{text, at}] (2-5), highlight (index to circle), doodle (arrow|circle|underline|star),
    board"""
    b = board(f, p)
    lines = p("lines", [{"text": "Point one"}, {"text": "Point two"}])
    if p("title"):
        write(f, b, p("title"), 180, 170, 0.2, size=84, align="left")
        draw_partial(f, line_path([(180, 200), (980, 205)]), f.prog(0.9, 0.6), pen(f, b, b["colors"][0], 5, 1))
    times = _step_times(f, lines, start=0.8)
    y0 = 330 if p("title") else 240
    gap = min(150, 640 / max(len(lines), 1))
    for i, (ln, t0) in enumerate(zip(lines, times)):
        y = y0 + i * gap
        bullet = f.prog(t0, 0.3)
        if bullet <= 0:
            f.c.drawCircle(210, y - 18, 12, paint(b["dim"], 0.7, stroke=4))
            draw_partial(f, line_path([(260, y - 18), (260 + 620 - i * 60, y - 18)]), 1.0, paint(b["dim"], 0.5, stroke=8))
        if bullet > 0:
            f.c.drawCircle(210, y - 18, 10 * bullet, paint(b["colors"][i % 4], 0.9))
        w = write(f, b, ln["text"], 260, y, t0, size=64, align="left") or 0
        if i == p("highlight"):
            doodle = p("doodle") or pick(f, "doodle", ["circle", "underline", "arrow"])
            dk = f.prog(t0 + 1.0, 0.7)
            hp = pen(f, b, b["colors"][1], 6, 90)
            if doodle == "underline":
                draw_partial(f, line_path([(250, y + 22), (260 + w, y + 28)]), dk, hp)
            elif doodle == "arrow":
                arrow(f, 260 + w + 220, y - 20, 260 + w + 40, y - 20, dk, hp)
            else:
                draw_partial(f, skia.Path().addOval(skia.Rect.MakeLTRB(230, y - 75, 290 + w, y + 30)), dk, hp)


# ---------------------------------------------------------------- timeline

@template("board_timeline", kind="board", sfx=lambda p: [Sfx("chalk", 0.3)] + [Sfx("tick", e.get("at", 1 + i)) for i, e in enumerate(p("events", [])[:8])])
def board_timeline(f, p):
    """A timeline drawn across the board, with events ticked off in order as they're mentioned.
    params: title, events [{when ('8 min', '1 year'), label, at}] (2-7), board"""
    b = board(f, p)
    evs = p("events", [{"when": "Now", "label": "Start"}, {"when": "Later", "label": "End"}])
    if p("title"):
        write(f, b, p("title"), 960, 150, 0.2, size=72)
    x0, x1, y = 180, 1740, 560
    arrow(f, x0, y, x1, y, f.prog(0.2, 1.0), pen(f, b, b["ink"], 5, 3), head=28)
    times = _step_times(f, evs, start=1.0)
    for i, (e, t0) in enumerate(zip(evs, times)):
        x = lerp(x0 + 80, x1 - 120, i / max(len(evs) - 1, 1))
        c_ = b["colors"][i % 4]
        k = f.prog(t0, 0.4)
        f.c.drawLine(x, y - 25 * k, x, y + 25 * k, pen(f, b, c_, 6, 10 + i))
        up = i % 2 == 0
        write(f, b, e.get("when", ""), x, y + (-70 if up else 100), t0 + 0.1, size=54, color=c_)
        write(f, b, e.get("label", ""), x, y + (-140 if up else 170), t0 + 0.4, size=42, color=b["dim"])


# ---------------------------------------------------------------- compare two columns

@template("board_compare", kind="board", sfx=lambda p: [Sfx("chalk", 0.3), Sfx("chalk", 1.2)] + [Sfx("pop", r.get("at", 2 + i)) for i, r in enumerate(p("rows", [])[:6])])
def board_compare(f, p):
    """Two columns compared row by row (e.g. Earth vs Mars), with bars showing which is bigger.
    params: left, right (column headings), rows [{label, left, right (numbers), unit, at}] (1-5), board"""
    b = board(f, p)
    lh, rh = p("left", "A"), p("right", "B")
    write(f, b, lh, 620, 170, 0.2, size=80, color=b["colors"][0])
    write(f, b, rh, 1300, 170, 0.5, size=80, color=b["colors"][1])
    draw_partial(f, line_path([(960, 120), (962, 980)]), f.prog(0.3, 0.8), pen(f, b, b["dim"], 3, 5))
    rows = p("rows", [{"label": "Size", "left": 1, "right": 0.5}])
    times = _step_times(f, rows, start=1.2)
    for i, (r, t0) in enumerate(zip(rows, times)):
        y = 320 + i * 140
        write(f, b, r.get("label", ""), 960, y - 40, t0, size=40, color=b["dim"])
        mx = max(abs(r.get("left", 0)), abs(r.get("right", 0)), 1e-9)
        k = f.prog(t0 + 0.2, 0.8)
        for side, val, c_ in ((-1, r.get("left", 0), b["colors"][0]), (1, r.get("right", 0), b["colors"][1])):
            ln = 520 * abs(val) / mx * k
            x_start = 940 if side < 0 else 980
            f.c.drawLine(x_start, y + 10, x_start + side * ln, y + 10, pen(f, b, c_, 18, 30 + i * 2 + side))
            unit = r.get("unit", "")
            txt = f"{val:,}{unit}" if not isinstance(val, float) or val >= 100 else f"{val:g}{unit}"
            write(f, b, txt, x_start + side * (ln + 20), y + 25, t0 + 0.7, size=44, align="right" if side < 0 else "left")


# ---------------------------------------------------------------- forces on an object

@template("board_forces", kind="board", sfx=lambda p: [Sfx("chalk", 0.3)] + [Sfx("whoosh", fo.get("at", 1 + i), gain_db=-8) for i, fo in enumerate(p("forces", [])[:5])])
def board_forces(f, p):
    """A force diagram: an object with arrows for each force (gravity, thrust, drag...), drawn on one by one.
    params: object (label), shape (circle|box|rocket), forces [{label, direction (up|down|left|right or degrees), size (0.5-2), at}], board"""
    b = board(f, p)
    x, y = 960, 560
    shape = p("shape") or pick(f, "shape", ["circle", "box"])
    pp = pen(f, b, b["ink"], 6, 1)
    if shape == "box":
        draw_partial(f, skia.Path().addRect(skia.Rect.MakeXYWH(x - 110, y - 110, 220, 220)), f.prog(0.2, 0.8), pp)
    elif shape == "rocket":
        draw_partial(f, line_path([(x, y - 160), (x + 60, y - 60), (x + 60, y + 120), (x - 60, y + 120), (x - 60, y - 60), (x, y - 160)]),
                     f.prog(0.2, 1.0), pp)
    else:
        draw_partial(f, skia.Path().addCircle(x, y, 110), f.prog(0.2, 0.8), pp)
    write(f, b, p("object", ""), x, y + 14, 0.8, size=54)
    times = _step_times(f, p("forces", []), start=1.2)
    for i, (fo, t0) in enumerate(zip(p("forces", []), times)):
        d = fo.get("direction", "down")
        ang = {"up": -90, "down": 90, "left": 180, "right": 0}.get(d, d) if isinstance(d, str) else d
        a = math.radians(ang)
        L = 200 * fo.get("size", 1)
        sx, sy = x + math.cos(a) * 140, y + math.sin(a) * 140
        ex, ey = x + math.cos(a) * (140 + L), y + math.sin(a) * (140 + L)
        c_ = b["colors"][i % 4]
        arrow(f, sx, sy, ex, ey, f.prog(t0, 0.7), pen(f, b, c_, 7, 40 + i), head=30)
        write(f, b, fo.get("label", ""), ex + math.cos(a) * 70, ey + math.sin(a) * 60 + 18, t0 + 0.5, size=50, color=c_)


# ---------------------------------------------------------------- orbit sketch

@template("board_orbit", kind="board", sfx=lambda p: [Sfx("chalk", 0.3), Sfx("chalk", 1.4)])
def board_orbit(f, p):
    """A hand-drawn orbit: a central body, an elliptical path, the orbiting body moving round it, with
    arrows for its speed and the pull towards the centre.
    params: center_label, orbiter_label, ellipse (0.4-1, 1 = circle), show_forces (true), board"""
    b = board(f, p)
    cx, cy = 960, 560
    e = p("ellipse") or rand(f, "ell", 0.55, 0.9)
    rx, ry = 620, 620 * e * 0.62
    draw_partial(f, skia.Path().addCircle(cx, cy, 70), f.prog(0.2, 0.6), pen(f, b, b["colors"][0], 6, 1))
    write(f, b, p("center_label", "Sun"), cx, cy + 130, 0.7, size=50, color=b["colors"][0])
    path = skia.Path().addOval(skia.Rect.MakeLTRB(cx - rx, cy - ry, cx + rx, cy + ry))
    draw_partial(f, path, f.prog(0.6, 1.5), pen(f, b, b["dim"], 4, 2))
    if f.t > 2.0:
        ang = (f.t - 2.0) * 0.25 * 2 * math.pi
        ox, oy = cx + math.cos(ang) * rx, cy + math.sin(ang) * ry
        f.c.drawCircle(ox, oy, 30, pen(f, b, b["colors"][1], 5, 3))
        write(f, b, p("orbiter_label", "Earth"), ox, oy - 50, 2.0, size=44, color=b["colors"][1])
        if p("show_forces", True):
            tx, ty = -math.sin(ang) * rx, math.cos(ang) * ry
            n = math.hypot(tx, ty)
            arrow(f, ox, oy, ox + tx / n * 170, oy + ty / n * 170, f.prog(2.4, 0.5), pen(f, b, b["colors"][2], 5, 4))
            gx, gy = cx - ox, cy - oy
            g = math.hypot(gx, gy)
            arrow(f, ox, oy, ox + gx / g * 130, oy + gy / g * 130, f.prog(2.9, 0.5), pen(f, b, b["colors"][3], 5, 5))


# ---------------------------------------------------------------- graph

@template("board_graph", kind="board", sfx=lambda p: [Sfx("chalk", 0.3), Sfx("chalk", p("at", 1.2), dur=2.0)])
def board_graph(f, p):
    """A hand-drawn graph: axes, then a curve sketched on, with a marked point.
    params: title, x_label, y_label, values (list of numbers), x_ticks [[frac, text]], y_ticks [[frac, text]],
    mark (index of a point to circle), mark_label, at (word the curve starts drawing on), board"""
    b = board(f, p)
    vals = p("values", [1, 2, 4, 8, 16])
    if p("title"):
        write(f, b, p("title"), 960, 130, 0.2, size=68)
    x, y, w, h = 300, 220, 1320, 620
    axis = pen(f, b, b["ink"], 5, 1)
    arrow(f, x, y + h, x + w + 40, y + h, f.prog(0.3, 0.7), axis)
    arrow(f, x, y + h, x, y - 40, f.prog(0.5, 0.7), axis)
    write(f, b, p("x_label", ""), x + w, y + h + 80, 1.0, size=46, color=b["dim"], align="right")
    write(f, b, p("y_label", ""), x - 30, y - 60, 1.0, size=46, color=b["dim"], align="left")
    for fr, s in p("x_ticks", []):
        write(f, b, s, x + w * fr, y + h + 60, 1.2, size=38, color=b["dim"])
    for fr, s in p("y_ticks", []):
        write(f, b, s, x - 20, y + h - h * fr + 12, 1.2, size=38, color=b["dim"], align="right")
    lo, hi = min(vals), max(vals)
    pts = [(x + w * i / (len(vals) - 1), y + h - h * (v - lo) / ((hi - lo) or 1) * 0.92) for i, v in enumerate(vals)]
    start = when(f, p("at"), 0.3) if p("at") else 1.4
    k = f.prog(start, max(f.dur - start - 1.2, 1.0), ease=lambda v: clamp(v))
    draw_partial(f, line_path(pts, smooth=True), k, pen(f, b, b["colors"][0], 7, 7))
    m = p("mark")
    if m is not None and k >= (m / max(len(vals) - 1, 1)):
        mx, my = pts[m]
        draw_partial(f, skia.Path().addCircle(mx, my, 34), f.prog(start + k * 0 + 0.1, 0.5), pen(f, b, b["colors"][1], 5, 9))
        if p("mark_label"):
            write(f, b, p("mark_label"), mx + 50, my - 50, start + 0.3, size=48, color=b["colors"][1], align="left")


# ---------------------------------------------------------------- numbered steps

@template("board_steps", kind="board", sfx=lambda p: [Sfx("chalk", s.get("at", 0.5 + i * 1.2)) for i, s in enumerate(p("steps", [])[:6])])
def board_steps(f, p):
    """A process in numbered steps joined by arrows (e.g. how a star forms), each step written as it's said.
    params: title, steps [{text, at}] (2-5), direction (across|down), board"""
    b = board(f, p)
    steps = p("steps", [{"text": "First"}, {"text": "Then"}, {"text": "Finally"}])
    if p("title"):
        write(f, b, p("title"), 960, 120, 0.2, size=70)
    n = len(steps)
    across = (p("direction") or pick(f, "dir", ["across", "down"])) == "across" and n <= 4
    times = _step_times(f, steps, start=0.6)
    for i, (s, t0) in enumerate(zip(steps, times)):
        if across:
            x, y = 230 + i * (1460 / max(n - 1, 1)), 560
        else:
            x, y = 960, 260 + i * (720 / max(n - 1, 1))
        c_ = b["colors"][i % 4]
        k = f.prog(t0, 0.5)
        draw_partial(f, skia.Path().addCircle(x - (0 if across else 520), y - (80 if across else 18), 42), k, pen(f, b, c_, 5, i))
        write(f, b, str(i + 1), x - (0 if across else 520), y - (62 if across else 0), t0, size=56, color=c_)
        write(f, b, s.get("text", ""), x, y + (40 if across else 0) + (0 if across else 0), t0 + 0.3, size=52 if across else 58,
              align="center" if across else "center")
        if i < n - 1:
            nt = times[i + 1]
            if across:
                arrow(f, x + 120, y - 80, x + 1460 / max(n - 1, 1) - 120, y - 80, f.prog(nt - 0.4, 0.4), pen(f, b, b["dim"], 4, 20 + i))
            else:
                arrow(f, 960 - 520, y + 40, 960 - 520, y + 720 / max(n - 1, 1) - 80, f.prog(nt - 0.4, 0.4), pen(f, b, b["dim"], 4, 20 + i))


# ---------------------------------------------------------------- sketched planet with features

@template("board_sketch", kind="board", sfx=lambda p: [Sfx("chalk", 0.2, dur=1.5)] + [Sfx("pop", fe.get("at", 1.5 + i)) for i, fe in enumerate(p("features", [])[:5])])
def board_sketch(f, p):
    """A big hand-sketched planet (or star) with features pointed out: poles, oceans, storms, layers, moons.
    params: title, body_label, features [{label, angle (degrees round the edge), at}] (1-5), hatch (true shades one side), board"""
    b = board(f, p)
    x, y, r = 820, 570, 300
    draw_partial(f, skia.Path().addCircle(x, y, r), f.prog(0.2, 1.2), pen(f, b, b["ink"], 7, 1))
    if p("hatch", True):
        hk = f.prog(1.2, 1.0)
        for i in range(14):
            yy = y - r + (i + 0.5) * (2 * r / 14)
            half = math.sqrt(max(r * r - (yy - y) ** 2, 0))
            xa = x + half * 0.2
            xb = x + half * 0.95
            if hk * 14 > i:
                f.c.drawLine(xa, yy, xb, yy - 20, pen(f, b, b["dim"], 3, 30 + i))
    if p("title"):
        write(f, b, p("title"), 960, 120, 0.2, size=70)
    if p("body_label"):
        write(f, b, p("body_label"), x, y + r + 90, 0.9, size=60, color=b["colors"][0])
    for i, fe in enumerate(p("features", [])):
        a = math.radians(fe.get("angle", -60 + i * 50))
        t0 = f.time(fe["at"]) if fe.get("at") else 1.6 + i * 0.9
        px, py = x + math.cos(a) * r * 0.85, y + math.sin(a) * r * 0.85
        tx, ty = 1300, 260 + i * 140
        arrow(f, tx - 30, ty - 15, px, py, f.prog(t0, 0.6), pen(f, b, b["colors"][(i + 1) % 4], 4, 50 + i))
        write(f, b, fe.get("label", ""), tx, ty, t0 + 0.4, size=50, align="left", color=b["colors"][(i + 1) % 4])
