"""Cinematic templates: titles, kinetic text and stylised sci-fi visuals for transitions and hooks."""

import math

import numpy as np
import skia

from esim.templates import BODY_KINDS, Sfx, accent, body, pick, rand, shot_camera, template, when
from esim.engine import *  # noqa: F401,F403


@template("title_card", kind="cinematic", sfx=lambda p: [Sfx("reverse", 0.0, dur=0.6), Sfx("808", 0.6), Sfx("whoosh", "end", offset=-0.8, gain_db=-6)])
def title_card(f, p):
    """A chapter title: big text slamming in over a glowing nebula and drifting particles, then a slow push-in
    with beat-pulsing glow, light sweeps and the chapter's planet rising behind it, so it never sits still.
    params: title, number (chapter number, optional), sub, color, style (slam|type|glitch), kind (body behind it, optional)"""
    gradient_bg(f)
    nebula_glow(f, alpha=0.6)
    starfield(f, n=300, drift=(-14 - 30 * f.p, 0))
    c_ = accent(f, p)
    kind = p("kind")
    if kind is None:  # "Number Nine: Earth" -> Earth rises behind the title
        words = [w.strip(":,.!?").lower() for w in p("title", "").split()]
        kind = next((w for w in reversed(words) if w in BODY_KINDS and w not in ("rocky", "gas", "ice", "star")), None)
    pulse = f.beat_pulse() if hasattr(f, "beat_pulse") else 0.0
    zoom = 1.0 + 0.10 * ease_in_out(f.p)
    with camera(f, 960, 540, zoom=zoom, rotate=lerp(-1.2, 1.2, f.p)):
        if kind:
            # a huge planet rising up from the bottom edge, its top arc staying below the subtitle
            r = 560 + 20 * pulse
            body(f, kind, 960 + lerp(-80, 80, f.p), lerp(1700, 1360, ease_out(f.prog(0.3, 3.0))), r,
                 alpha=0.75 * f.prog(0.3, 1.2))
        soft_light(f, 960, 540, 700, c_, 0.12 + 0.18 * pulse)
        # a light sweep across the title every few seconds
        sweep = (f.t % 4.0) / 4.0
        soft_light(f, lerp(200, 1720, sweep), 560, 260, INK, 0.10 * math.sin(math.pi * sweep))
        rng = f.rng("tc_sparks")
        n = 60
        sx, sp = rng.random(n) * 1920, 40 + rng.random(n) * 80
        sy = (rng.random(n) * 1100 - f.t * sp) % 1100
        dots(f, sx, sy, 2 + rng.random(n) * 3, 0.5, color=c_)
        if p("number") is not None:
            text(f, f"CHAPTER {p('number')}", 960, 400, size=40, color=c_, weight="semibold", a=f.prog(0.2, 0.4))
        title = p("title", "Chapter")
        size = 150 if len(title) < 14 else 110
        style = p("style") or pick(f, "tstyle", ["slam", "type", "glitch"])
        if style == "slam":
            slam_text(f, title.upper(), 960, 540, 0.6, size=size, glow_color=c_, snap=False)
        elif style == "type":
            text(f, title.upper(), 960, 590, size=size - 10, glow_color=c_,
                 reveal=f.prog(0.4, 1.0, ease=lambda v: clamp(v)), stroke=8)
        else:
            jit = 14 * math.exp(-max(f.t - 0.6, 0) * 4) * math.sin(f.t * 70) + 6 * pulse
            for dx, colr, a in ((-6 - jit, RED, 0.6), (6 + jit, CYAN, 0.6), (0, INK, 1)):
                text(f, title.upper(), 960 + dx, 590, size=size - 10, color=colr, a=a * f.prog(0.4, 0.2))
        if p("sub"):
            text(f, p("sub"), 960, 700, size=44, color=DIM, weight="semibold", a=f.prog(1.2, 0.5))


@template("kinetic_text", kind="cinematic", sfx=lambda p: [Sfx("pop", w.get("at", 0.3 + i * 0.35), gain_db=-4) for i, w in enumerate(p("words", [])[:8])])
def kinetic_text(f, p):
    """Kinetic typography: a key line's words punching onto the screen one by one, on the beat.
    params: words [{text, at, color}] (2-8 short words/phrases), background (space|black|nebula), color"""
    bg = p("background") or pick(f, "kbg", ["black", "space", "nebula"])
    if bg == "black":
        f.c.clear(col("#050508"))
    elif bg == "nebula":
        gradient_bg(f)
        nebula_glow(f, alpha=0.5)
    else:
        space(f, drift=(-6, 0), nebula=False)
    c_ = accent(f, p)
    words = p("words", [{"text": "NO"}, {"text": "WARNING"}])
    n = len(words)
    # Flow layout: measure every word, wrap into lines no wider than the screen, and shrink the type until the
    # whole block fits, so long words never overlap.
    labels = [w["text"].upper() for w in words]
    size, gap, max_w = 150, 50, 1640
    while True:
        widths = [font(size, "bold").measureText(s) for s in labels]
        lines, cur, cur_w = [], [], 0
        for i, wd in enumerate(widths):
            if cur and cur_w + gap + wd > max_w:
                lines.append(cur)
                cur, cur_w = [], 0
            cur_w += (gap if cur else 0) + wd
            cur.append(i)
        lines.append(cur)
        if (len(lines) <= 3 and max(widths) <= max_w) or size <= 60:
            break
        size -= 10
    line_h = size * 1.25
    top = 540 - (len(lines) - 1) * line_h / 2
    pos = {}
    for li, line in enumerate(lines):
        total = sum(widths[i] for i in line) + gap * (len(line) - 1)
        x = 960 - total / 2
        for i in line:
            pos[i] = (x + widths[i] / 2, top + li * line_h)
            x += widths[i] + gap
    for i, w in enumerate(words):
        t0 = f.next_beat(w["at"]) if w.get("at") and f.beats else (f.time(w["at"]) if w.get("at") else 0.3 + i * 0.35)
        s = f.t - t0
        x, y = pos[i]
        if s < 0:  # not spoken yet: a dim outline holds its place
            text(f, labels[i], x, y + size * 0.35, size=size, color=c_ if i == n - 1 else DIM, a=0.22, stroke=size * 0.03)
            continue
        k = clamp(s / 0.12)
        sc = lerp(1.5, 1, ease_out(k))
        f.c.save()
        f.c.translate(x, y)
        f.c.scale(sc, sc)
        text(f, labels[i], 0, size * 0.35, size=size,
             color=w.get("color", INK if i % 3 else c_), glow_color=c_ if i == n - 1 else None, stroke=size * 0.07, a=k)
        f.c.restore()


@template("split_compare", kind="cinematic", sfx=lambda p: [Sfx("whoosh", p("at", 0.6)), Sfx("glitch", p("at", 0.6), offset=0.3)])
def split_compare(f, p):
    """Before and after, side by side: the screen splits with a sliding divider (e.g. Earth now vs Earth frozen).
    params: left {kind, label}, right {kind, label}, at (word the divider sweeps in on), color"""
    c_ = accent(f, p)
    left, right = p("left", {"kind": "earth", "label": "Now"}), p("right", {"kind": "frozen_earth", "label": "After"})
    start = when(f, p("at"), 0.2) if p("at") else 0.6
    k = f.prog(start, 1.0)
    div = lerp(W + 10, W / 2, k)
    space(f, drift=(-4, 0), nebula=False)
    for side, spec, x in ((0, left, 560), (1, right, 1360)):
        f.c.save()
        f.c.clipRect(skia.Rect.MakeLTRB(0, 0, div, H) if side == 0 else skia.Rect.MakeLTRB(div, 0, W, H))
        if side == 1:
            f.c.drawPaint(paint("#0a1020", 0.6))
        body(f, spec.get("kind", "earth"), x if k > 0.5 or side == 1 else 960, 520, 280,
             light=(-0.6, -0.3, 0.7), seed_key="split")
        text(f, spec.get("label", "").upper(), x, 860, size=64, glow_color=c_ if side else None, a=1 if side == 0 else k)
        f.c.restore()
    if k > 0:
        f.c.drawLine(div, 0, div, H, paint(c_, 0.9, stroke=6))
        soft_light(f, div, H / 2, 300, c_, 0.25)


@template("hologram_scan", kind="cinematic", sfx=lambda p: [Sfx("glitch", 0.2), Sfx("shimmer", 0.6), Sfx("tick", 1.5), Sfx("tick", 2.2)])
def hologram_scan(f, p):
    """A sci-fi hologram: a wireframe body being scanned, with a HUD of readouts appearing line by line.
    params: kind (body), readouts [{label, value, at}] (1-5), color"""
    f.c.clear(col("#03070c"))
    c_ = accent(f, p, default=["cyan", "green", "ice"])
    gp = paint(c_, 0.06, stroke=1)
    for x in range(0, W, 60):
        f.c.drawLine(x, 0, x, H, gp)
    x, y, r = 700, 540, 300
    with layer(f, 0.85):
        body(f, p("kind", "earth"), x, y, r, light=(0, 0, 1), tint=c_, brightness=0.9)
    for i in range(-6, 7):
        lat = i / 7 * math.pi / 2
        ry = r * math.cos(lat)
        f.c.drawLine(x - ry, y + r * math.sin(lat), x + ry, y + r * math.sin(lat), paint(c_, 0.25, stroke=1.5))
    for i in range(8):
        a = i / 8 * math.pi + f.t * 0.4
        w = abs(math.cos(a)) * r
        f.c.drawOval(skia.Rect.MakeLTRB(x - w, y - r, x + w, y + r), paint(c_, 0.2, stroke=1.5))
    scan = y - r + (f.t * 220) % (2 * r)
    f.c.drawLine(x - r - 40, scan, x + r + 40, scan, paint(c_, 0.9, stroke=3, add=True))
    soft_light(f, x, scan, 120, c_, 0.25)
    for i, rd in enumerate(p("readouts", [{"label": "RADIUS", "value": "6,371 km"}])):
        t0 = f.time(rd["at"]) if rd.get("at") else 0.6 + i * 0.6
        a = f.prog(t0, 0.25)
        yy = 300 + i * 120
        f.c.drawLine(1150, yy + 20, 1150 + 560 * a, yy + 20, paint(c_, 0.6, stroke=2))
        text(f, rd.get("label", "").upper(), 1150, yy - 10, size=30, color=c_, align="left", weight="semibold", a=a)
        text(f, rd.get("value", ""), 1710, yy - 10, size=44, color=INK, align="right", weight="bold",
             reveal=f.prog(t0 + 0.1, 0.5, ease=lambda v: clamp(v)))


@template("warp", kind="cinematic", sfx=lambda p: [Sfx("riser", 0.0, dur=1.6), Sfx("whoosh", 1.4), Sfx("808", p("arrive_at", "end"), offset=-0.2 if not p("arrive_at") else 0)])
def warp(f, p):
    """A hyperspace jump: stars stretch into streaks rushing past, then snap back as we arrive somewhere new.
    params: destination (text shown on arrival), arrive_at (word), color, kind (body we arrive at, optional)"""
    c_ = accent(f, p, default=["cyan", "purple", "ice"])
    arrive = when(f, p("arrive_at"), 0.75) if p("arrive_at") else f.dur * 0.75
    if f.t > arrive:
        space(f, drift=(-4, 0))  # arriving somewhere: the stars settle back to normal
    else:
        f.c.clear(col("#020208"))
    speed = clamp(f.t / 1.2) * (1 - f.prog(arrive, 0.4))
    rng = f.rng("warp")
    n = 420
    ang = rng.random(n) * 6.28
    z = (rng.random(n) + f.t * (0.2 + speed * 1.6)) % 1.0
    r0 = 40 + z ** 3 * 1400
    r1 = r0 * (1 + speed * 0.6 * z)
    for i in range(0, n, 1):
        x0, y0 = 960 + math.cos(ang[i]) * r0[i], 540 + math.sin(ang[i]) * r0[i]
        x1, y1 = 960 + math.cos(ang[i]) * r1[i], 540 + math.sin(ang[i]) * r1[i]
        colr = c_ if i % 5 == 0 else INK
        f.c.drawLine(x0, y0, x1, y1, paint(colr, 0.3 + 0.7 * float(z[i]), stroke=1 + 2 * float(z[i])))
    soft_light(f, 960, 540, 300, c_, 0.3 * speed)
    if f.t > arrive:
        kind = p("kind") or ((p("destination") or "").strip().lower().replace(" ", "_") or None)
        if kind in BODY_KINDS:  # arriving at a named planet: it swells into view and keeps slowly growing
            grow = ease_back(f.prog(arrive, 0.6)) * (1 + 0.08 * f.prog(arrive, max(f.dur - arrive, 0.1)))
            body(f, kind, 960, 470, 280 * grow, light=(-0.6, -0.3, 0.7))
        if p("destination"):
            slam_text(f, p("destination").upper(), 960, 820, arrive + 0.2, size=100, glow_color=c_, snap=False)
    flash(f, arrive, dur=0.4, peak=0.7)


@template("particle_gas", kind="cinematic", sfx=lambda p: [Sfx("rumble", "start", dur=5, gain_db=-10)] + ([Sfx("power_down", p("change_at"))] if p("change_at") else []))
def particle_gas(f, p):
    """Molecules bouncing in a box. Their speed shows temperature: they can slow to a crawl (freezing) or go wild (heating).
    params: count (40-200), temp (0-1 start), to_temp (0-1), change_at (word), label, color"""
    gradient_bg(f, "#05070d", "#020306")
    c_ = accent(f, p, default=["cyan", "gold", "red"])
    box = skia.Rect.MakeLTRB(360, 160, 1560, 900)
    f.c.drawRect(box, paint(DIM, 0.5, stroke=3))
    rng = f.rng("gas")
    n = int(p("count", 120))
    x0, y0 = rng.random(n), rng.random(n)
    vx, vy = rng.normal(0, 1, n), rng.normal(0, 1, n)
    t_a, t_b = p("temp", 0.8), p("to_temp", p("temp", 0.8))
    ch = f.time(p("change_at")) if p("change_at") else None
    # distance travelled = integral of speed; speed eases between the two temperatures
    if ch is None or f.t < ch:
        dist = t_a * f.t
        temp = t_a
    else:
        k_dur = 2.0
        s = f.t - ch
        kk = clamp(s / k_dur)
        dist = t_a * ch + t_a * min(s, k_dur) + (t_b - t_a) * (min(s, k_dur) * kk / 2) + t_b * max(s - k_dur, 0)
        temp = lerp(t_a, t_b, kk)
    w, h = box.width() - 30, box.height() - 30
    px = (x0 * w + vx * dist * 260) % (2 * w)
    py = (y0 * h + vy * dist * 260) % (2 * h)
    px = np.where(px > w, 2 * w - px, px) + box.left() + 15
    py = np.where(py > h, 2 * h - py, py) + box.top() + 15
    colr = mix("#4fb3ff", "#ff5a3a", temp)
    dots(f, px, py, np.full(n, 9.0), np.full(n, 0.95), colr)
    dots(f, px, py, np.full(n, 18.0), np.full(n, 0.15), colr, add=True)
    if p("label"):
        text(f, p("label"), 960, 120, size=52, a=f.prog(0.2, 0.5))


@template("waves", kind="cinematic", sfx=lambda p: [Sfx("shimmer", 0.4)] + ([Sfx("whoosh", p("change_at"))] if p("change_at") else []))
def waves(f, p):
    """Glowing waves travelling across the screen (light, sound, gravitational waves), which can change
    frequency or size part-way through.
    params: label, count (1-3 waves), wavelength (px, default 260), to_wavelength, amplitude, to_amplitude, change_at, color"""
    gradient_bg(f)
    starfield(f, n=200, drift=(-3, 0), alpha=0.6)
    c_ = accent(f, p)
    n = int(p("count", 2))
    ch = f.time(p("change_at")) if p("change_at") else None
    k = f.prog(ch, 1.5) if ch is not None else 0
    wl = lerp(p("wavelength", 260), p("to_wavelength", p("wavelength", 260)), k)
    amp = lerp(p("amplitude", 120), p("to_amplitude", p("amplitude", 120)), k)
    for j in range(n):
        y0 = 540 + (j - (n - 1) / 2) * 260
        pts = [(x, y0 + amp / (1 + j * 0.4) * math.sin(2 * math.pi * (x / wl - f.t * 0.6) + j)) for x in range(-20, W + 40, 12)]
        path = line_path(pts)
        f.c.drawPath(path, paint(c_ if j == 0 else INK, 0.25, stroke=18, add=True))
        f.c.drawPath(path, paint(c_ if j == 0 else INK, 0.9, stroke=4))
    if p("label"):
        text(f, p("label"), 960, 140, size=56, a=f.prog(0.2, 0.5))


@template("question_card", kind="cinematic", sfx=lambda p: [Sfx("reverse", 0.0, dur=0.8), Sfx("impact", 0.8, gain_db=-6), Sfx("shimmer", 1.4)])
def question_card(f, p):
    """A big mystery question with a pulsing question mark, for opening a 'real mystery' section.
    params: question (one short line), color"""
    space(f, drift=(-3, 0))
    c_ = accent(f, p, default=["purple", "cyan", "pink"])
    q = p("question", "Why?")
    pulse = 1 + 0.06 * f.beat_pulse() + 0.03 * math.sin(f.t * 3) + 0.10 * f.p
    rp = paint(c_, 0.35, stroke=4)
    rp.setPathEffect(skia.DashPathEffect.Make([30, 22], f.t * 60))
    f.c.drawCircle(960, 420, 330 + 15 * math.sin(f.t * 0.8), rp)
    rp2 = paint(c_, 0.2, stroke=2)
    rp2.setPathEffect(skia.DashPathEffect.Make([8, 18], -f.t * 40))
    f.c.drawCircle(960, 420, 400, rp2)
    rng = f.rng("q_embers")
    n = 90
    ex = rng.random(n) * 1920
    ey = (rng.random(n) * 1000 - f.t * (25 + rng.random(n) * 50)) % 1000
    dots(f, ex, ey, 1.5 + rng.random(n) * 3, 0.25 + 0.4 * rng.random(n), color=c_)
    soft_light(f, 960, 420, 420, c_, 0.12 + 0.12 * f.beat_pulse())
    f.c.save()
    f.c.translate(960, 420)
    f.c.scale(pulse * ease_back(f.prog(0.6, 0.6)), pulse * ease_back(f.prog(0.6, 0.6)))
    text(f, "?", 0, 160, size=460, color=c_, glow_color=c_, a=0.9)
    f.c.restore()
    text(f, q, 960, 850, size=72 if len(q) < 28 else 56, reveal=f.prog(1.0, 1.0, ease=lambda v: clamp(v)), stroke=6)


@template("radar_scan", kind="cinematic", sfx=lambda p: [Sfx("tick", 0.6 + i * 0.9) for i in range(4)])
def radar_scan(f, p):
    """A radar sweep picking up objects one by one (asteroids, signals, planets), each tagged as it's found.
    params: targets [{label, at}] (1-5), color"""
    f.c.clear(col("#020805"))
    c_ = accent(f, p, default=["green", "cyan"])
    cx, cy, r = 960, 560, 420
    for rr in (r * 0.33, r * 0.66, r):
        f.c.drawCircle(cx, cy, rr, paint(c_, 0.3, stroke=2))
    f.c.drawLine(cx - r, cy, cx + r, cy, paint(c_, 0.2, stroke=1))
    f.c.drawLine(cx, cy - r, cx, cy + r, paint(c_, 0.2, stroke=1))
    sweep = (f.t * 120) % 360
    for k in range(30):
        a = math.radians(sweep - k * 2)
        f.c.drawLine(cx, cy, cx + math.cos(a) * r, cy + math.sin(a) * r, paint(c_, 0.5 * (1 - k / 30), stroke=4))
    rng = f.rng("radar")
    for i, tg in enumerate(p("targets", [{"label": "OBJECT"}])):
        t0 = f.time(tg["at"]) if tg.get("at") else 0.8 + i * 0.9
        if f.t < t0:
            continue
        a, d = rng.random() * 6.28, (0.3 + rng.random() * 0.6) * r
        x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
        glow(f, x, y, 10, c_, 0.6 + 0.4 * math.sin(f.t * 5 + i))
        text(f, tg.get("label", "").upper(), x + 24, y - 18, size=30, color=c_, align="left", weight="semibold",
             reveal=f.prog(t0, 0.4, ease=lambda v: clamp(v)))


@template("reveal", kind="cinematic", sfx=lambda p: [Sfx("rumble", "start", dur=4, gain_db=-6),
                                                      Sfx("reverse", p("at", "end"), offset=-1.2, dur=1.2),
                                                      Sfx("impact", p("at", "end")), Sfx("808", p("at", "end"))])
def reveal(f, p):
    """The shock drop. Darkness and a heartbeat glow while the narration builds, then on the key word a blinding
    hit and the reveal slams in: a body or a huge number, with a shockwave, debris and a punchline.
    Use it for the 2-4 most jaw-dropping facts in a video, with the scene's "drop" on the same word.
    params: at (the reveal word, required), kind (body to reveal, e.g. black_hole, red_giant, earth),
    number (text instead of a body, e.g. "1,300,000x"), title (punchline, 1-4 words), sub (one line), color, size"""
    c_ = accent(f, p, default=["red", "gold", "cyan", "pink"])
    hit = when(f, p("at"), 0.55)
    s = f.since(hit)
    gradient_bg(f, "#02030a", "#000000")
    if s < 0:  # the build: almost black, a slow heartbeat of light, stars barely there
        k = clamp(f.t / max(hit, 0.1))
        starfield(f, n=160, drift=(0, 0), alpha=0.25 + 0.3 * k)
        beat = abs(math.sin(f.t * (2.2 + 4 * k)))
        soft_light(f, 960, 540, 200 + 300 * k, c_, (0.08 + 0.25 * k) * beat)
        ring(f, 960, 540, 120 + 30 * beat, 3, c_, 0.25 * k * beat)
        return
    shake = 26 * math.exp(-s * 3.2)
    zoom = 1 + 0.25 * math.exp(-s * 2.5)
    with camera(f, 960, 540, zoom=zoom, shake=shake):
        starfield(f, n=420, drift=(-40 * math.exp(-s), 0), alpha=0.9)
        nebula_glow(f, alpha=0.35 * clamp(s))
        r = p("size", 230)
        if p("number"):
            text(f, p("number"), 960, 590, size=220 if len(p("number")) < 9 else 150, glow_color=c_, stroke=14)
        else:
            body(f, p("kind", "black_hole"), 960, 520, r * ease_back(clamp(s / 0.45)), light=(-0.6, -0.3, 0.7))
        shockwave(f, 960, 540, hit, speed=1400, life=1.6, color=c_, width=30)
        shockwave(f, 960, 540, hit + 0.18, speed=900, life=1.8, color=INK, width=12)
        particles(f, 960, 540, hit, n=320, speed=(300, 1500), life=(0.6, 2.5), size=(2, 6), color=c_)
    if p("title"):
        slam_text(f, p("title"), 960, 840 if p("number") else 880, hit + 0.15, size=150, glow_color=c_, snap=False)
    if p("sub"):
        text(f, p("sub"), 960, 950, size=40, color=DIM, weight="semibold", a=f.prog(hit + 0.9, 0.5))
    flash(f, hit, dur=0.55, color="#ffffff", peak=1.0)
