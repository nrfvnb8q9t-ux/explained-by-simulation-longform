"""Data templates: numbers, charts and rankings that make facts hit."""

import math

import skia

from esim.templates import Sfx, accent, body, pick, rand, shot_camera, template, when
from esim.engine import *  # noqa: F401,F403


def _bg(f, p):
    style = p("background") or pick(f, "dbg", ["space", "grid", "nebula"])
    if style == "grid":
        gradient_bg(f, "#070a14", "#020306")
        gp = paint(DIM, 0.07, stroke=1)
        for x in range(0, W + 80, 80):
            f.c.drawLine(x, 0, x, H, gp)
        for y in range(0, H + 80, 80):
            f.c.drawLine(0, y, W, y, gp)
    elif style == "nebula":
        gradient_bg(f)
        nebula_glow(f, alpha=0.45)
        starfield(f, n=200, drift=(-3, 0), alpha=0.6)
    else:
        gradient_bg(f)
        starfield(f, n=260, drift=(-4, 0), alpha=0.7)


def _fmt(v, decimals=0):
    return f"{v:,.{decimals}f}"


@template("chart", kind="data", sfx=lambda p: [Sfx("whoosh", p("at", 0.4), gain_db=-8)] + ([Sfx("pop", p("highlight_at"))] if p("highlight_at") else []))
def chart_t(f, p):
    """A glowing line chart that draws itself, with an optional highlighted point and callout.
    params: title, values (numbers), x_labels [[frac, text]], y_labels [[frac, text]], y_range [lo, hi],
    zero_line, highlight (index), highlight_label, highlight_at, at (word it starts drawing on), color, background"""
    _bg(f, p)
    vals = p("values", [1, 3, 2, 5, 8])
    c_ = accent(f, p)
    start = when(f, p("at"), 0.1) if p("at") else 0.4
    k = f.prog(start, max(f.dur - start - 1.5, 1.5))
    rect = (260, 260, 1400, 560)
    with layer(f, alpha=f.prog(0, 0.5)):
        line_chart(f, rect, vals, k, color=c_, y_range=p("y_range"), x_labels=p("x_labels", []),
                   y_labels=p("y_labels", []), title=p("title"), zero_line=p("zero_line"))
    hi = p("highlight")
    if hi is not None and p("highlight_label"):
        lo_, hi_ = p("y_range") or (min(vals), max(vals))
        x = rect[0] + rect[2] * hi / (len(vals) - 1)
        y = rect[1] + rect[3] - rect[3] * (vals[hi] - lo_) / ((hi_ - lo_) or 1)
        label(f, p("highlight_label"), x, y, x + (160 if hi < len(vals) / 2 else -160), y - 120,
              p("highlight_at", start + 1.5), size=40)


@template("bars", kind="data", sfx=lambda p: [Sfx("pop", it.get("at", 0.5 + i * 0.5)) for i, it in enumerate(p("items", [])[:8])])
def bars(f, p):
    """Horizontal bars that grow to their values one by one, biggest highlighted. Good for rankings and comparisons.
    params: title, items [{label, value, at}] (2-8), unit, sort (true), log (true for huge ranges), color, background"""
    _bg(f, p)
    items = list(p("items", [{"label": "A", "value": 3}, {"label": "B", "value": 7}]))
    if p("sort", True):
        items.sort(key=lambda it: it["value"], reverse=True)
    c_ = accent(f, p)
    if p("title"):
        text(f, p("title"), 160, 140, size=60, align="left", a=f.prog(0, 0.5))
    mx = max(it["value"] for it in items) or 1
    use_log = p("log", mx / max(min(it["value"] for it in items), 1e-9) > 200)
    n = len(items)
    gap = min(110, 760 / n)
    for i, it in enumerate(items):
        y = 240 + i * gap
        t0 = f.time(it["at"]) if it.get("at") else 0.5 + i * 0.45
        k = f.prog(t0, 0.9, ease=ease_out)
        frac = (math.log10(max(it["value"], 1e-9)) / math.log10(mx) if use_log and mx > 1 else it["value"] / mx)
        w = 1100 * max(frac, 0.02) * k
        text(f, it["label"], 560, y + gap * 0.42, size=min(44, gap * 0.45), align="right", weight="semibold", a=clamp(k * 3))
        rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(590, y + 6, w, gap * 0.55), 10, 10)
        top = i == 0
        f.c.drawRRect(rr, paint(c_ if top else DIM, 0.95 if top else 0.6))
        if top:
            soft_light(f, 590 + w, y + gap * 0.3, 80, c_, 0.4 * k)
        text(f, _fmt(it["value"] * k, 0 if it["value"] >= 10 else 2) + p("unit", ""), 610 + w, y + gap * 0.45,
             size=min(40, gap * 0.4), align="left", weight="bold", a=clamp(k * 3))
    if use_log:
        text(f, "log scale", W - 60, H - 40, size=24, color=DIM, align="right", weight="body")


@template("big_number", kind="data", sfx=lambda p: [Sfx("riser", p("at", 0.3), dur=1.8, gain_db=-6), Sfx("808", p("at", 0.3), offset=1.8)])
def big_number(f, p):
    """A huge number that counts up (or down) to its value and lands with a hit, with a caption under it.
    params: value, from (start value, default 0), unit (e.g. ' km/s'), prefix, decimals, caption, at (word the count starts on),
    count_seconds (default 1.8), color, background"""
    _bg(f, p)
    c_ = accent(f, p)
    start = when(f, p("at"), 0.15) if p("at") else 0.3
    dur = p("count_seconds", 1.8)
    k = f.prog(start, dur, ease=ease_out)
    v = lerp(p("from", 0), p("value", 100), k)
    s = f.t - (start + dur)
    scale = 1 + (0.12 * math.exp(-s * 8) if s > 0 else 0) + 0.03 * f.beat_pulse()
    f.c.save()
    f.c.translate(960, 520)
    f.c.scale(scale, scale)
    txt = p("prefix", "") + _fmt(v, p("decimals", 0)) + p("unit", "")
    size = 220 if len(txt) <= 8 else 160 if len(txt) <= 12 else 120
    waiting = f.t < start  # before its word, the number waits dimmed, so the screen is never empty
    text(f, txt, 0, size * 0.35, size=size, glow_color=None if waiting else c_, stroke=size * 0.06,
         a=f.prog(0.1, 0.4) * (0.35 if waiting else 1))
    f.c.restore()
    if waiting:
        ring(f, 960, 520, 300 + 12 * math.sin(f.t * 2), 4, c_, 0.25 + 0.2 * f.beat_pulse())
    if p("caption"):
        text(f, p("caption"), 960, 760, size=50, color=DIM, weight="semibold", a=f.prog(start + dur * 0.6, 0.5))
    if s > 0:
        ring(f, 960, 520, 200 + s * 900, 10, c_, 0.5 * clamp(1 - s))


@template("rank_card", kind="data", sfx=lambda p: [Sfx("reverse", 0.4, dur=0.8), Sfx("808", 1.2), Sfx("pop", 1.8)])
def rank_card(f, p):
    """A ranked-list entry: a huge '#3', the item's name, a spinning body and 1-3 quick facts.
    params: rank, name, kind (body to show, or none), facts [text] (0-3), color, background"""
    _bg(f, p)
    c_ = accent(f, p, default=["gold", "red", "cyan", "pink"])
    side = pick(f, "rside", ["left", "right"])
    bx = 1350 if side == "left" else 570
    tx = 160 if side == "left" else 1060
    if p("kind", "earth") != "none":
        with shot_camera(f, p, bx, 540, strength=0.4):
            body(f, p("kind", "earth"), bx, 540, 260 * ease_back(f.prog(0.3, 0.9)), light=(-0.6, -0.3, 0.7))
    slam_text(f, f"#{p('rank', 1)}", tx + 160, 330, 1.2, size=240, glow_color=c_, snap=True)
    text(f, p("name", ""), tx, 560, size=78, align="left", a=f.prog(1.6, 0.4), weight="bold")
    for i, fact in enumerate(p("facts", [])[:3]):
        text(f, "• " + fact, tx, 660 + i * 70, size=40, align="left", color=DIM, weight="semibold", a=f.prog(2.0 + i * 0.4, 0.4))


@template("countdown", kind="data", sfx=lambda p: [Sfx("tick", 0.5 + i * 0.5) for i in range(int(min(p("ticks", 6), 10)))])
def countdown(f, p):
    """A big digital clock counting time passing (or down), e.g. '8:20' of light travel or 'Day 365'.
    params: seconds (end value, e.g. 500 for 8:20), mode (clock|days|years), down (true counts down), caption, at, color, background"""
    _bg(f, p)
    c_ = accent(f, p, default=["red", "cyan", "gold"])
    start = when(f, p("at"), 0.1) if p("at") else 0.4
    k = f.prog(start, max(f.dur - start - 1.0, 1.0), ease=lambda v: clamp(v))
    total = p("seconds", 500)
    v = total * (1 - k) if p("down") else total * k
    mode = p("mode", "clock")
    if mode == "days":
        txt = f"DAY {int(v):,}"
    elif mode == "years":
        txt = f"YEAR {int(v):,}"
    else:
        s = int(v)
        txt = f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if total >= 3600 else f"{s // 60}:{s % 60:02d}"
    rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(460, 330, 1000, 360), 40, 40)
    f.c.drawRRect(rr, paint("#000000", 0.5))
    f.c.drawRRect(rr, paint(c_, 0.7 + 0.3 * f.beat_pulse(), stroke=4))
    text(f, txt, 960, 580, size=190 if len(txt) < 8 else 150, glow_color=c_, weight="bold")
    if p("caption"):
        text(f, p("caption"), 960, 800, size=48, color=DIM, weight="semibold", a=f.prog(start, 0.5))


@template("stat_grid", kind="data", sfx=lambda p: [Sfx("pop", s.get("at", 0.5 + i * 0.6)) for i, s in enumerate(p("stats", [])[:6])])
def stat_grid(f, p):
    """2-6 fact tiles popping in one at a time, each a big number with a label. Great for "by the numbers" moments.
    Keep each value SHORT: a number or 1-3 words ("8 min", "4x", "-73°C"). Long values wrap and lose impact.
    params: title, stats [{value (text), label, at}], color, background"""
    _bg(f, p)
    c_ = accent(f, p)
    stats = p("stats", [{"value": "8 min", "label": "light travel"}, {"value": "150M km", "label": "distance"}])
    n = len(stats)
    cols = 3 if n > 4 else 2 if n > 1 else 1
    rows = math.ceil(n / cols)
    if p("title"):
        text(f, p("title"), 960, 140, size=64, a=f.prog(0, 0.5))
    tw = min(520, (1760 - 50 * (cols - 1)) / cols)
    th = 260
    # one value size for every tile, shrunk until the longest value and label fit inside their tile
    vsize = 84
    while vsize > 48 and max(font(vsize, "bold").measureText(s.get("value", "")) for s in stats) > tw - 50:
        vsize -= 4

    def wrap(s, size, width):
        lines, cur = [], ""
        for word in s.split():
            trial = f"{cur} {word}".strip()
            if cur and font(size, "bold").measureText(trial) > width:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        return lines + [cur] if cur else lines
    lsize = 34
    while lsize > 20 and max(font(lsize, "semibold").measureText(s.get("label", "")) for s in stats) > tw - 40:
        lsize -= 2
    for i, s in enumerate(stats):
        r_, c2 = divmod(i, cols)
        x = 960 + (c2 - (cols - 1) / 2) * (tw + 50)
        y = 560 + (r_ - (rows - 1) / 2) * (th + 50)
        t0 = f.time(s["at"]) if s.get("at") else 0.5 + i * 0.6
        k = f.prog(t0, 0.5, ease=ease_back)
        if k <= 0:
            continue
        f.c.save()
        f.c.translate(x, y)
        f.c.scale(k, k)
        rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(-tw / 2, -th / 2, tw, th), 28, 28)
        f.c.drawRRect(rr, paint("#000000", 0.55))
        f.c.drawRRect(rr, paint(c_, 0.6, stroke=3))
        vlines = wrap(s.get("value", ""), vsize, tw - 50)[:3]
        vs = vsize if len(vlines) == 1 else min(vsize, 52)
        vlines = wrap(s.get("value", ""), vs, tw - 50)[:3]
        for li, line in enumerate(vlines):
            text(f, line, 0, 10 - (len(vlines) - 1) * vs * 0.55 + li * vs * 1.1, size=vs, glow_color=c_)
        text(f, s.get("label", ""), 0, 80 + (len(vlines) - 1) * vs * 0.3, size=lsize, color=DIM, weight="semibold")
        f.c.restore()


@template("percent_ring", kind="data", sfx=lambda p: [Sfx("riser", p("at", 0.4), dur=1.6, gain_db=-8), Sfx("pop", p("at", 0.4), offset=1.6)])
def percent_ring(f, p):
    """A ring that fills up to a percentage, with the number in the middle (e.g. '99.8%' of the solar system's mass).
    params: percent, caption, at, color, background"""
    _bg(f, p)
    c_ = accent(f, p)
    start = when(f, p("at"), 0.15) if p("at") else 0.4
    k = f.prog(start, 1.6, ease=ease_out)
    pct = p("percent", 50)
    r = 260
    f.c.drawCircle(960, 500, r, paint(DIM, 0.25, stroke=34))
    path = skia.Path()
    path.addArc(skia.Rect.MakeLTRB(960 - r, 500 - r, 960 + r, 500 + r), -90, 360 * pct / 100 * k)
    f.c.drawPath(path, paint(c_, 0.35, stroke=60, add=True))
    f.c.drawPath(path, paint(c_, 1, stroke=34))
    text(f, f"{pct * k:.1f}%" if pct < 100 and pct != int(pct) else f"{pct * k:.0f}%", 960, 540, size=120, glow_color=c_)
    if p("caption"):
        text(f, p("caption"), 960, 880, size=48, color=INK, weight="semibold", a=f.prog(start + 1, 0.5))


@template("thermometer", kind="data", sfx=lambda p: [Sfx("rumble", p("at", 0.4), dur=3, gain_db=-8), Sfx("tick", "end", offset=-1.2)])
def thermometer(f, p):
    """A thermometer whose level rises or falls to a temperature, glowing hot red or icy blue.
    params: from_c, to_c (degrees Celsius), range [lo, hi], caption, at, background"""
    _bg(f, p)
    lo, hi = p("range", [-100, 60])
    a_, b_ = p("from_c", 15), p("to_c", -73)
    start = when(f, p("at"), 0.15) if p("at") else 0.5
    k = f.prog(start, max(f.dur - start - 1.5, 1.5))
    v = lerp(a_, b_, k)
    frac = clamp((v - lo) / (hi - lo))
    hot = mix("#4fb3ff", "#ff4f3a", clamp((v + 20) / 80))
    x, top, bot = 760, 180, 820
    tube = skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(x - 50, top, x + 50, bot), 50, 50)
    f.c.drawRRect(tube, paint("#000000", 0.5))
    f.c.drawRRect(tube, paint(INK, 0.6, stroke=4))
    f.c.drawCircle(x, bot + 40, 90, paint(hot, 1))
    soft_light(f, x, bot + 40, 220, hot, 0.4)
    lvl = bot - (bot - top - 30) * frac
    f.c.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(x - 28, lvl, x + 28, bot + 20), 28, 28), paint(hot, 1))
    for t_ in range(int(math.ceil(lo / 20) * 20), hi + 1, 20):
        yy = bot - (bot - top - 30) * (t_ - lo) / (hi - lo)
        f.c.drawLine(x + 60, yy, x + 90, yy, paint(DIM, 0.7, stroke=2))
        text(f, f"{t_}°", x + 110, yy + 12, size=30, color=DIM, align="left", weight="body")
    text(f, f"{v:.0f}°C", 1300, 560, size=190, glow_color=hot)
    if p("caption"):
        text(f, p("caption"), 1300, 700, size=46, color=DIM, weight="semibold", a=f.prog(start, 0.5))


@template("gauge", kind="data", sfx=lambda p: [Sfx("riser", p("at", 0.4), dur=2.0, gain_db=-8), Sfx("impact", p("at", 0.4), offset=2.0, gain_db=-8)])
def gauge(f, p):
    """A speedometer-style dial whose needle swings up to a value (speed, pressure, force...).
    params: value, max, unit, caption, at, color, background"""
    _bg(f, p)
    c_ = accent(f, p, default=["red", "gold", "cyan"])
    start = when(f, p("at"), 0.15) if p("at") else 0.4
    k = f.prog(start, 2.0, ease=ease_out)
    mx = p("max", 100)
    v = p("value", 70) * k
    cx, cy, r = 960, 640, 380
    arc = skia.Path()
    arc.addArc(skia.Rect.MakeLTRB(cx - r, cy - r, cx + r, cy + r), 180, 180)
    f.c.drawPath(arc, paint(DIM, 0.3, stroke=30, cap_round=False))
    fill = skia.Path()
    fill.addArc(skia.Rect.MakeLTRB(cx - r, cy - r, cx + r, cy + r), 180, 180 * clamp(v / mx))
    f.c.drawPath(fill, paint(c_, 0.4, stroke=56, add=True, cap_round=False))
    f.c.drawPath(fill, paint(c_, 1, stroke=30, cap_round=False))
    jitter = 0.6 * math.sin(f.t * 40) * clamp(k * 2) * (1 - k * 0.5)
    ang = math.radians(180 + 180 * clamp(v / mx) + jitter)
    f.c.drawLine(cx, cy, cx + math.cos(ang) * (r - 60), cy + math.sin(ang) * (r - 60), paint(INK, 1, stroke=10))
    f.c.drawCircle(cx, cy, 26, paint(INK, 1))
    text(f, f"{v:,.0f}{p('unit', '')}", cx, cy - 110, size=110, glow_color=c_)
    if p("caption"):
        text(f, p("caption"), cx, cy + 120, size=46, color=DIM, weight="semibold", a=f.prog(start + 1, 0.5))
