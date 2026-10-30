"""Space simulation templates."""

import math

import numpy as np
import skia

from esim.templates import (ACCENTS, BODY_KINDS, Sfx, P, accent, body, draw_black_hole, pick, rand, shot_camera, template,
                            when)
from esim.engine import *  # noqa: F401,F403


def _bg(f, p, drift=None):
    style = p("background") or pick(f, "bg", ["space", "space", "deep", "nebula"])
    d = drift or (rand(f, "dx", -8, 8), rand(f, "dy", -3, 3))
    if style == "deep":
        space(f, drift=d, nebula=False, stars=520)
    elif style == "nebula":
        gradient_bg(f)
        nebula_glow(f, alpha=0.55)
        starfield(f, n=380, drift=d)
    else:
        space(f, drift=d)


def _light_from(f, p, default=None):
    side = p("light") or default or pick(f, "light", ["left", "right", "top_left", "top_right"])
    return {"left": (-0.85, -0.2, 0.5), "right": (0.85, -0.2, 0.5), "top_left": (-0.6, -0.6, 0.55),
            "top_right": (0.6, -0.6, 0.55), "front": (0.1, -0.1, 1), "back": (0, 0, -0.2)}.get(side, (-0.7, -0.3, 0.6))


def _labels(f, p, x, y, r):
    for i, lab in enumerate(p("labels", [])):
        ang = lab.get("angle", rand(f, f"lab{i}", -150, -30) if i % 2 == 0 else rand(f, f"lab{i}", 20, 150))
        a = math.radians(ang)
        px, py = x + math.cos(a) * r, y + math.sin(a) * r
        tx, ty = x + math.cos(a) * (r + 140), y + math.sin(a) * (r + 110)
        label(f, lab["text"], px, py, tx, ty, lab.get("at", 0.5 + i * 0.8), size=lab.get("size", 36))


# ---------------------------------------------------------------- 1. a planet in close-up

@template("planet_hero", sfx=lambda p: [Sfx("rumble", "start", dur=4, gain_db=-8)] +
          ([Sfx("power_down" if p("event") in ("darken", "freeze") else "shimmer", p("event_at"))] if p("event_at") else []))
def planet_hero(f, p):
    """One big planet, slowly spinning, with an optional change part-way through.
    params: kind (earth, mars, moon, jupiter, ...), side (left|center|right), size (radius px, default 330),
    light (left|right|top_left|top_right|front), event (freeze|darken|burn|lights|vents|glow), event_at (word),
    labels [{text, at}], camera, background (space|deep|nebula)"""
    _bg(f, p)
    side = p("side") or pick(f, "side", ["left", "center", "right"])
    x = {"left": 650, "center": 960, "right": 1270}[side]
    r = p("size", 330)
    kind = p("kind", "earth")
    ev, ev_at = p("event"), p("event_at")
    k = f.prog(ev_at, 2.5) if ev_at else 0.0
    light = _light_from(f, p)
    with shot_camera(f, p, x, 540):
        bright = lerp(1, 0.28, k) if ev in ("darken", "freeze") else 1.0
        body(f, kind, x, 540, r, rotation=f.t * rand(f, "spin", 0.008, 0.02), light=light, brightness=bright,
             night_lights=k if ev == "lights" else 0, alpha=1 - (k if ev in ("freeze", "burn") else 0))
        if ev == "freeze" and k > 0:
            body(f, "frozen_earth", x, 540, r, rotation=f.t * 0.012, light=light, brightness=bright, alpha=k,
                 seed_key=kind)
        if ev == "burn" and k > 0:
            body(f, "lava", x, 540, r, rotation=f.t * 0.012, light=light, alpha=k, seed_key=kind)
            soft_light(f, x, 540, r * 1.6, RED, 0.35 * k)
        if ev in ("vents", "glow") and k > 0:
            rng = f.rng("vents")
            for i in range(12):
                rr, a = r * 0.85 * math.sqrt(rng.random()), rng.random() * 6.28
                glow(f, x + math.cos(a) * rr, 540 + math.sin(a) * rr, 7, GOLD if ev == "vents" else accent(f, p),
                     k * (0.55 + 0.45 * math.sin(f.t * 2.3 + i)))
        _labels(f, p, x, 540, r)


# ---------------------------------------------------------------- 2. two bodies side by side

@template("two_bodies", sfx=lambda p: [Sfx("whoosh", 0.2)] + ([Sfx("impact", p("verdict_at"), gain_db=-6)] if p("verdict_at") else []))
def two_bodies(f, p):
    """Two bodies side by side for a comparison or 'versus', with names and an optional winner.
    params: a {kind, label, size}, b {kind, label, size}, vs (true shows a VS slam), winner (a|b),
    verdict_at (word the winner lights up on), camera"""
    _bg(f, p)
    a, b = p("a", {"kind": "earth", "label": "Earth"}), p("b", {"kind": "mars", "label": "Mars"})
    ra, rb = a.get("size", 230), b.get("size", 230)
    ax, bx = 560, 1360
    win, vat = p("winner"), p("verdict_at")
    with shot_camera(f, p):
        for i, (bd, x, r) in enumerate(((a, ax, ra), (b, bx, rb))):
            enter = f.prog(0.1 + i * 0.35, 0.8, ease=ease_back)
            yy = 520 + (1 - enter) * 500
            body(f, bd.get("kind", "rocky"), x, yy, r, light=(0.6 if i == 0 else -0.6, -0.3, 0.7))
            text(f, bd.get("label", ""), x, 520 + max(ra, rb) + 90, size=58, a=enter, weight="bold")
            if win == ("a" if i == 0 else "b") and vat:
                wk = f.prog(vat, 0.5)
                ring(f, x, yy, r * 1.12, 14, GOLD, 0.8 * wk * (0.7 + 0.3 * f.beat_pulse()))
        if p("vs", True):
            slam_text(f, "VS", 960, 520, 0.9, size=130, glow_color=accent(f, p), snap=False)


# ---------------------------------------------------------------- 3. a star system with orbits

@template("orbit_system", sfx=lambda p: [Sfx("whoosh", 0.3, gain_db=-4)] +
          ([Sfx("reverse", p("event_at"), offset=-1.3, dur=1.3), Sfx("power_down", p("event_at"))] if p("event_at") else []))
def orbit_system(f, p):
    """A star with planets on tilted orbits. Can make the star vanish, or a planet leave its orbit.
    params: star (sun|red_giant|white_dwarf|black_hole|none), planets (count 2-8, or list of kinds),
    highlight (index of a planet to label), highlight_label, event (star_vanish|planet_leave), event_at, tilt (0.2-0.6), camera"""
    _bg(f, p)
    cx, cy = 960, 540
    tilt = p("tilt") or rand(f, "tilt", 0.25, 0.5)
    plist = p("planets", 5)
    kinds = plist if isinstance(plist, list) else [pick(f, f"pk{i}", ["rocky", "mars", "earth", "gas", "ice", "moon"])
                                                   for i in range(int(plist))]
    ev, ev_at = p("event"), p("event_at")
    k = f.prog(ev_at, 0.5, ease=ease_in) if ev_at else 0
    with shot_camera(f, p, cx, cy):
        radii = [170 + i * (520 / max(len(kinds), 1)) for i in range(len(kinds))]
        bodies = []
        for i, (kind, rx) in enumerate(zip(kinds, radii)):
            orbit(f, cx, cy, rx, rx * tilt, a=0.3, progress=f.prog(0.1 + i * 0.1, 1.2))
            spd = 0.06 * (170 / rx) ** 1.5
            ang = rand(f, f"ph{i}", 0, 1) + f.t * spd
            x, y = orbit_point(cx, cy, rx, rx * tilt, ang)
            if ev == "planet_leave" and i == p("highlight", 0) and ev_at and f.t > f.time(ev_at):
                s = f.since(ev_at)
                a2 = ang * 2 * math.pi
                x += -math.sin(a2) * 260 * s
                y += math.cos(a2) * 260 * s * tilt
            bodies.append((y, x, kind, 8 + 18 * (i % 3 + 1) / 3, i))
        star = p("star", "sun")
        for y, x, kind, size, i in sorted(bodies):
            if y < cy:
                body(f, kind, x, y, size, light=(cx - x, cy - y, 160))
        if star != "none":
            alpha = 1 - k if ev == "star_vanish" else 1
            if alpha > 0.01:
                body(f, star, cx, cy, 95 * (alpha if ev == "star_vanish" else 1), alpha=alpha)
        for y, x, kind, size, i in sorted(bodies):
            if y >= cy:
                body(f, kind, x, y, size, light=(cx - x, cy - y, 160))
            if i == p("highlight") and p("highlight_label"):
                label(f, p("highlight_label"), x, y - size, x + 120, y - size - 100, 1.0, size=34)


# ---------------------------------------------------------------- 4. size comparison

@template("size_scale", sfx=lambda p: [Sfx("whoosh", 0.2)] + [Sfx("pop", 0.6 + i * 0.6) for i in range(min(len(p("bodies", [])), 6))])
def size_scale(f, p):
    """Bodies lined up by size, the camera sweeping from smallest to largest.
    params: bodies [{kind, label, radius_km}] (2-6, any order), log (true squashes huge differences), camera ignored"""
    gradient_bg(f)
    starfield(f, n=300, drift=(-12, 0))
    items = sorted(p("bodies", [{"kind": "moon", "label": "Moon", "radius_km": 1737},
                                {"kind": "earth", "label": "Earth", "radius_km": 6371},
                                {"kind": "jupiter", "label": "Jupiter", "radius_km": 69911}]),
                   key=lambda b: b.get("radius_km", 1))
    biggest = max(b.get("radius_km", 1) for b in items)
    use_log = p("log", biggest / min(b.get("radius_km", 1) for b in items) > 40)

    def rad(b):
        v = b.get("radius_km", 1)
        return 40 + 310 * (math.log(v) / math.log(biggest) if use_log else v / biggest)

    xs, x = [], 200
    for b in items:
        r = rad(b)
        x += r
        xs.append(x)
        x += r + 120
    span = max(x - 200, W)
    pan = lerp(0, span - W + 200, ease_in_out(f.p)) if span > W else 0
    zoom = lerp(1.25, 0.95, ease_in_out(f.p)) if span <= W else 1.0
    with camera(f, W / 2 + pan, 500, zoom=zoom):
        for i, (b, cx) in enumerate(zip(items, xs)):
            r = rad(b)
            a = f.prog(0.4 + i * 0.6, 0.6)
            body(f, b.get("kind", "rocky"), cx, 500, r * lerp(0.6, 1, ease_back(a)), light=(-0.6, -0.3, 0.7), alpha=a)
            text(f, b.get("label", ""), cx, 500 + r + 70, size=44, a=a)
            if b.get("radius_km"):
                text(f, f"{b['radius_km']:,} km radius", cx, 500 + r + 118, size=28, color=DIM, weight="body", a=a)
    if use_log:
        text(f, "sizes on a log scale", 40, H - 36, size=24, color=DIM, align="left", weight="body", a=0.7)


# ---------------------------------------------------------------- 5. impact

@template("impact", sfx=lambda p: [Sfx("whoosh", p("at", "end"), offset=-1.2), Sfx("reverse", p("at", "end"), offset=-1.0, dur=1.0),
                                   Sfx("impact", p("at", "end")), Sfx("rumble", p("at", "end"), dur=4)])
def impact(f, p):
    """Something slams into a planet: approach trail, flash, shockwave, debris and a glowing crater.
    params: target (planet kind), impactor (asteroid|moon|comet|planet kind), at (word it hits on),
    from (left|right|top), size (impactor radius, default 40), camera"""
    _bg(f, p)
    tx, ty, tr = 1100, 600, p("target_size", 320)
    hit = when(f, p("at"), 0.55)
    side = p("from") or pick(f, "from", ["left", "top", "right"])
    sx, sy = {"left": (-200, 160), "top": (500, -250), "right": (2200, 100)}[side]
    ang = math.atan2(ty - sy, tx - sx)
    ix, iy = tx - math.cos(ang) * tr * 0.92, ty - math.sin(ang) * tr * 0.92
    k = clamp((f.t - (hit - 2.2)) / 2.2)
    s = f.since(hit)
    shake = 22 * math.exp(-s * 3) if s > 0 else 0
    with camera(f, lerp(960, tx, 0.3), 540, zoom=1.05 + (0.08 * math.exp(-s * 4) if s > 0 else 0), shake=shake):
        body(f, p("target", "earth"), tx, ty, tr, light=(-0.7, -0.3, 0.6))
        if s < 0:
            px, py = lerp(sx, ix, ease_in(k)), lerp(sy, iy, ease_in(k))
            trail(f, [(lerp(sx, px, j / 20), lerp(sy, py, j / 20)) for j in range(21)], GOLD, width=6, a=k)
            body(f, p("impactor", "asteroid"), px, py, p("size", 40), light=(0.6, -0.4, 0.7))
            soft_light(f, px, py, 90, "#ffb070", 0.5 * k)
        else:
            glow(f, ix, iy, 40 * math.exp(-s * 0.6) + 10, "#ffcf7a", clamp(1.2 - s * 0.25))
            soft_light(f, ix, iy, 260 * clamp(1 - s * 0.3), RED, 0.4 * clamp(1 - s * 0.3))
            shockwave(f, ix, iy, hit, speed=700, life=2.2, color=GOLD, width=22)
            particles(f, ix, iy, hit, n=280, speed=(150, 900), life=(0.8, 3.0), size=(2, 6), color=GOLD,
                      spread=(math.degrees(ang) + 100, math.degrees(ang) + 260), gravity=(0, 60))
    flash(f, hit, dur=0.5, color="#fff1d0", peak=0.8)


# ---------------------------------------------------------------- 6. explosion / supernova

@template("explosion", sfx=lambda p: [Sfx("riser", p("at", "end"), offset=-2.5, dur=2.5), Sfx("impact", p("at", "end")),
                                      Sfx("808", p("at", "end")), Sfx("rumble", p("at", "end"), dur=5)])
def explosion(f, p):
    """A star or planet blows apart: building glow, blinding flash, rings, debris and an expanding nebula.
    params: kind (sun|red_giant|planet kind), at (word it explodes on), color (accent), size (default 150), camera"""
    _bg(f, p)
    x, y = 960, 540
    boom = when(f, p("at"), 0.4)
    col_ = accent(f, p, default=["gold", "pink", "cyan", "purple", "orange"])
    r = p("size", 150)
    s = f.since(boom)
    with camera(f, x, y, zoom=1 + (0.12 * math.exp(-s * 2) if s > 0 else 0.06 * clamp(f.t / boom)),
                shake=(25 * math.exp(-s * 2.5) if s > 0 else 3 * clamp(f.t / max(boom, 0.1)))):
        if s < 0:
            pulse = 1 + 0.08 * math.sin(f.t * (6 + 10 * clamp(f.t / boom)))
            body(f, p("kind", "red_giant"), x, y, r * pulse)
            soft_light(f, x, y, r * 4, col_, 0.3 * clamp(f.t / boom))
        else:
            for k, delay in enumerate((0, 0.25, 0.6)):
                shockwave(f, x, y, boom + delay, speed=900 - k * 200, life=3, color=col_ if k != 1 else INK, width=26 - k * 6)
            neb = clamp(s / 4)
            rng = f.rng("neb")
            for i in range(10):
                a, d = rng.random() * 6.28, (150 + rng.random() * 350) * ease_out(neb)
                soft_light(f, x + math.cos(a) * d, y + math.sin(a) * d * 0.8, 180 + 200 * neb,
                           [col_, "#7a5cff", RED][i % 3], 0.22 * (1 - neb * 0.4))
            particles(f, x, y, boom, n=380, speed=(200, 1100), life=(1, 4), size=(2, 6), color=col_)
            glow(f, x, y, 60 * math.exp(-s * 0.8) + 12, "#ffffff", clamp(1.3 - s * 0.3))
    flash(f, boom, dur=0.7, color="#ffffff", peak=0.95)


# ---------------------------------------------------------------- 7. flyby at speed

@template("flyby", sfx=lambda p: [Sfx("whoosh", 0.3), Sfx("whoosh", "end", offset=-1.5, gain_db=-4)])
def flyby(f, p):
    """The camera races past a body at high speed: streaking stars and speed lines.
    params: kind (body), direction (left|right), speed_text (e.g. '30 km/s', shown as a counter), size, camera ignored"""
    gradient_bg(f)
    d = -1 if (p("direction") or pick(f, "dir", ["left", "right"])) == "left" else 1
    rng = f.rng("streaks")
    n = 160
    ys, x0 = rng.random(n) * H, rng.random(n) * W
    sp = 600 + rng.random(n) * 1800
    ln = 40 + rng.random(n) * 220
    for i in range(n):
        x = (x0[i] - d * sp[i] * f.t) % (W + 300) - 150
        f.c.drawLine(x, ys[i], x + d * ln[i], ys[i], paint(INK, 0.15 + 0.5 * (sp[i] / 2400), stroke=1.5 + sp[i] / 1600))
    r = p("size", 260)
    bx = lerp(W + r if d < 0 else -r, -r if d < 0 else W + r, f.p)
    body(f, p("kind", "jupiter"), bx, 560 + 40 * math.sin(f.t * 0.6), r, light=(d * -0.6, -0.3, 0.7))
    if p("speed_text"):
        text(f, p("speed_text"), W - 80, 120, size=64, align="right", glow_color=accent(f, p), a=f.prog(0.3, 0.5))


# ---------------------------------------------------------------- 8. black hole

@template("black_hole", sfx=lambda p: [Sfx("rumble", "start", dur=6, gain_db=-4)] +
          ([Sfx("reverse", p("consume_at"), offset=-1.4, dur=1.4), Sfx("808", p("consume_at"))] if p("consume_at") else []))
def black_hole(f, p):
    """A black hole with a glowing accretion disk. Can pull something in and swallow it.
    params: size (shadow radius, default 110), spin (0.5-2), color (accent), consume (body kind to fall in),
    consume_at (word it gets swallowed on), camera"""
    _bg(f, p, drift=(-3, 0))
    x, y = 960, 540
    r = p("size", 110)
    with shot_camera(f, p, x, y, strength=0.7):
        if p("consume"):
            gone = when(f, p("consume_at"), 0.7)
            k = clamp(f.t / max(gone, 0.1))
            a = rand(f, "cang", 0, 6.28) + k * 9
            d = lerp(620, r * 0.9, ease_in(k))
            ox, oy = x + math.cos(a) * d, y + math.sin(a) * d * 0.35
            if f.t < gone:
                body(f, p("consume"), ox, oy, lerp(46, 6, ease_in(k)), light=(x - ox, y - oy, 100))
                trail(f, [(x + math.cos(a - j * 0.06) * (d + j * 6), y + math.sin(a - j * 0.06) * (d + j * 6) * 0.35)
                          for j in range(20, -1, -1)], accent(f, p), width=4, a=0.7)
            else:
                glow(f, x, y - r * 1.05, 18, "#ffffff", clamp(1 - f.since(gone) * 1.5))
        draw_black_hole(f, x, y, r, spin=p("spin", 1.0), color=accent(f, p, default=["gold", "orange", "pink"]))


# ---------------------------------------------------------------- 9. gravity between two bodies

@template("gravity_pull", sfx=lambda p: [Sfx("rumble", "start", dur=5, gain_db=-6)])
def gravity_pull(f, p):
    """Two bodies tugging on each other: pulsing field lines and a stretched (tidal) bulge.
    params: a (big body kind), b (smaller body kind), distance (0.3-1, closer = stronger pull), label, camera"""
    _bg(f, p)
    dist = p("distance", 0.7)
    ax, bx = 700, 700 + 280 + 600 * dist
    ra, rb = 230, 70
    col_ = accent(f, p)
    with shot_camera(f, p):
        stretch = 1 + 0.12 / max(dist, 0.2)
        f.c.save()
        f.c.translate(ax, 540)
        f.c.scale(stretch * 1.02, 1 / stretch * 1.02 + 0.02)
        soft_light(f, 0, 0, ra * 1.35, col_, 0.25)
        f.c.restore()
        body(f, p("a", "earth"), ax, 540, ra, light=(0.7, -0.3, 0.6))
        body(f, p("b", "moon"), bx, 540, rb, light=(-0.7, -0.3, 0.6))
        for i in range(7):
            off = (i - 3) * 38
            pts = [(lerp(ax + ra, bx - rb, j / 20), 540 + off * math.sin(math.pi * j / 20) * 1.8) for j in range(21)]
            path = line_path(pts, smooth=True)
            pr = paint(col_, 0.35 + 0.4 * f.beat_pulse(), stroke=2.5)
            pr.setPathEffect(skia.DashPathEffect.Make([16, 14], -f.t * 60))
            f.c.drawPath(path, pr)
        if p("label"):
            text(f, p("label"), (ax + bx) / 2, 300, size=46, a=f.prog(0.6, 0.6))


# ---------------------------------------------------------------- 10. light travelling between two places

@template("light_travel", sfx=lambda p: [Sfx("whoosh", p("at", 0.6)), Sfx("tick", "end", offset=-1.0)])
def light_travel(f, p):
    """A pulse of light (or anything) crossing from one body to another, with a running timer.
    params: a, b (body kinds), a_label, b_label, distance_label ('150 million km'), seconds (real travel time,
    for the timer, e.g. 500), at (word it sets off on), color, camera"""
    _bg(f, p)
    ax, bx, y = 300, 1620, 520
    col_ = accent(f, p, default=["gold", "cyan"])
    with shot_camera(f, p, strength=0.5):
        # a body named only by its label ("Earth") is drawn as that body, not the default
        guess = lambda lab, dflt: (lab or "").strip().lower().replace(" ", "_") if (lab or "").strip().lower().replace(" ", "_") in BODY_KINDS else dflt
        body(f, p("a") or guess(p("a_label"), "sun"), ax, y, 120)
        body(f, p("b") or guess(p("b_label"), "earth"), bx, y, 60, light=(-1, -0.2, 0.4))
        for x, lab in ((ax, p("a_label")), (bx, p("b_label"))):
            if lab:
                text(f, lab, x, y + 200, size=44)
        dl = paint(DIM, 0.6, stroke=2)
        dl.setPathEffect(skia.DashPathEffect.Make([12, 12], 0))
        f.c.drawLine(ax + 150, y, bx - 80, y, dl)
        if p("distance_label"):
            text(f, p("distance_label"), (ax + bx) / 2, y - 60, size=48, glow_color=col_, a=f.prog(0.3, 0.6))
        start = when(f, p("at"), 0.15)
        k = clamp((f.t - start) / max(f.dur - start - 1.0, 0.5))
        if f.t >= start:
            lx = lerp(ax + 150, bx - 80, k)
            trail(f, [(lerp(ax + 150, lx, j / 15), y) for j in range(16)], col_, width=5)
            glow(f, lx, y, 16, col_)
            if p("seconds"):
                secs = int(p("seconds") * k)
                h, m, s = secs // 3600, secs // 60 % 60, secs % 60
                txt = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                text(f, txt, (ax + bx) / 2, y + 230, size=120, glow_color=col_)


# ---------------------------------------------------------------- 11. top-down orbit

@template("orbit_topdown", sfx=lambda p: [Sfx("whoosh", 0.4, gain_db=-6)] + ([Sfx("glitch", p("release_at")), Sfx("whoosh", p("release_at"), offset=0.3)] if p("release_at") else []))
def orbit_topdown(f, p):
    """Looking down on an orbit. The orbiting body can break free and fly off in a straight line.
    params: center (sun|black_hole|earth|none), orbiter (body kind), radius (default 360), release_at (word),
    speed_label (e.g. '30 km/s'), camera ignored"""
    _bg(f, p, drift=(-2, 0))
    cx, cy, R = 960, 540, p("radius", 360)
    om = 0.05
    rel = f.time(p("release_at")) if p("release_at") else None
    a0 = rand(f, "a0", 0, 1)

    def pos(t):
        if rel is None or t <= rel:
            return orbit_point(cx, cy, R, R, a0 + om * t)
        a = (a0 + om * rel) * 2 * math.pi
        x0, y0 = cx + math.cos(a) * R, cy + math.sin(a) * R
        s = t - rel
        d = 2 * math.pi * R * om * s + 25 * s * s
        return x0 - math.sin(a) * d, y0 + math.cos(a) * d

    ex, ey = pos(f.t)
    fol = f.prog(rel, 2.5) if rel is not None else 0
    with camera(f, lerp(cx, ex, fol * 0.6), lerp(cy, ey, fol * 0.6), zoom=lerp(1, 0.75, f.prog(rel, 4)) if rel else 1):
        orbit(f, cx, cy, R, a=0.55 * (1 - (f.prog(rel, 1.5) if rel else 0)), progress=f.prog(0, 1.2))
        center = p("center", "sun")
        if center != "none":
            body(f, center, cx, cy, 90 if center == "sun" else 70)
        pts = [pos(f.t - k * 0.05) for k in range(40, -1, -1) if f.t - k * 0.05 >= 0]
        trail(f, pts, accent(f, p), width=5)
        body(f, p("orbiter", "earth"), ex, ey, 44, light=(cx - ex, cy - ey, 120))
        if p("speed_label"):
            text(f, p("speed_label"), ex, ey - 80, size=40, glow_color=accent(f, p), a=f.prog(rel or 1, 0.6))


# ---------------------------------------------------------------- 12. cutaway of a planet's layers

@template("cutaway", sfx=lambda p: [Sfx("glitch", 0.5)] + [Sfx("pop", l.get("at", 1 + i)) for i, l in enumerate(p("layers", [])[:6])])
def cutaway(f, p):
    """A planet with a wedge cut out to show its layers, each labelled as it's mentioned.
    params: kind (body), layers [{name, color, depth (0-1 from the surface), at}], side (left|right), camera"""
    _bg(f, p)
    x = 760 if (p("side") or "left") == "left" else 1160
    r = p("size", 340)
    layers = p("layers", [{"name": "Crust", "color": "#8a7a5c", "depth": 0.0},
                          {"name": "Mantle", "color": "#d9672e", "depth": 0.1},
                          {"name": "Outer core", "color": "#f6a23a", "depth": 0.45},
                          {"name": "Inner core", "color": "#fff1b0", "depth": 0.8}])
    open_k = f.prog(0.4, 1.2)
    with shot_camera(f, p, x, 540, strength=0.5):
        body(f, p("kind", "earth"), x, 540, r, light=(-0.6, -0.4, 0.7))
        sweep = 90 * open_k
        if sweep > 0.5:
            for i, lay in enumerate(layers):
                rr = r * (1 - lay.get("depth", i / len(layers)))
                path = skia.Path()
                path.moveTo(x, 540)
                path.arcTo(skia.Rect.MakeLTRB(x - rr, 540 - rr, x + rr, 540 + rr), -90, sweep, False)
                path.close()
                shade = skia.GradientShader.MakeRadial(skia.Point(x, 540), rr, [col(lay["color"]), col(mix(lay["color"], "#000000", 0.35))])
                f.c.drawPath(path, skia.Paint(AntiAlias=True, Shader=shade))
            for i, lay in enumerate(layers):
                rr = r * (1 - lay.get("depth", i / len(layers)))
                mid = r * (1 - (lay.get("depth", 0) + (layers[i + 1].get("depth", 1) if i + 1 < len(layers) else 1)) / 2)
                ang = math.radians(-90 + sweep * 0.5)
                px, py = x + math.cos(ang) * mid, 540 + math.sin(ang) * mid
                label(f, lay["name"], px, py, x + r + 120, 220 + i * 120, lay.get("at", 1.4 + i * 0.7), size=38)


# ---------------------------------------------------------------- 13. view from a planet's surface

@template("surface_view", sfx=lambda p: [Sfx("rumble", "start", dur=5, gain_db=-10), Sfx("shimmer", 0.8)])
def surface_view(f, p):
    """Standing on a world's surface, looking at the sky: a body rising or hanging huge above the horizon.
    params: sky (day|sunset|night|alien), ground (rocky|ice|desert|grass|lava), sky_body (body kind),
    sky_body_size (radius, default 220), rise (true animates it rising), camera ignored"""
    sky = p("sky") or pick(f, "sky", ["night", "sunset", "alien", "day"])
    tops = {"day": ("#2f6fd6", "#9fd0ff"), "sunset": ("#26174f", "#ff8a4c"), "night": ("#02030a", "#101a3a"),
            "alien": ("#1a0630", "#3fbf9a")}[sky]
    gradient_bg(f, tops[0], tops[1])
    if sky in ("night", "alien"):
        starfield(f, n=300, drift=(-2, 0), alpha=0.9)
    r = p("sky_body_size", 220)
    rise = f.prog(0, f.dur * 0.8) if p("rise", True) else 1
    bx, by = 1180, lerp(900, 360, rise)
    body(f, p("sky_body", "moon"), bx, by, r, light=(-0.6, -0.2, 0.7))
    if sky in ("day", "sunset"):
        f.c.drawPaint(paint(tops[1], 0.18))
    ground = p("ground") or pick(f, "ground", ["rocky", "ice", "desert", "lava"])
    gcol = {"rocky": ("#2b2622", "#4a413a"), "ice": ("#9fb8cf", "#e6f2ff"), "desert": ("#7a4a22", "#c48a4f"),
            "grass": ("#1f3a1c", "#3f6a2c"), "lava": ("#1a0a06", "#3a1608")}[ground]
    rng = f.rng("hills")
    for layer_i, base in enumerate((760, 840, 930)):
        path = skia.Path()
        path.moveTo(-50, H)
        amp = 60 - layer_i * 12
        ph = rng.random() * 6.28
        for x in range(-50, W + 60, 30):
            y = base + amp * math.sin(x * 0.004 + ph) + amp * 0.4 * math.sin(x * 0.013 + ph * 2)
            path.lineTo(x, y)
        path.lineTo(W + 60, H)
        path.close()
        f.c.drawPath(path, paint(mix(gcol[0], gcol[1], layer_i / 2), 1))
    if ground == "lava":
        rng2 = f.rng("lava")
        for i in range(18):
            glow(f, rng2.random() * W, 900 + rng2.random() * 160, 6, "#ff7a2a", 0.6 + 0.4 * math.sin(f.t * 2 + i))


# ---------------------------------------------------------------- 14. asteroid field

@template("asteroid_field", sfx=lambda p: [Sfx("rumble", "start", dur=5, gain_db=-8), Sfx("whoosh", 1.0)])
def asteroid_field(f, p):
    """Flying through a field of tumbling rocks, with one picked out and labelled.
    params: count (20-60), highlight_label, density (0.5-2), camera ignored"""
    gradient_bg(f)
    starfield(f, n=300, drift=(-10, 0))
    rng = f.rng("rocks")
    n = int(p("count", 36))
    rocks = sorted([(rng.random(), rng.random(), rng.random() * 2 - 1, rng.random()) for _ in range(n)], key=lambda r: r[3])
    for i, (x0, y0, spin, depth) in enumerate(rocks):
        size = 8 + depth ** 2 * 90
        speed = 40 + depth * 260
        x = (x0 * (W + 400) - speed * f.t) % (W + 400) - 200
        y = y0 * H + math.sin(f.t * 0.5 + i) * 10
        if size < 30:  # distant rocks: a shaded disc is indistinguishable and far cheaper
            shade = skia.GradientShader.MakeRadial(skia.Point(x - size * 0.35, y - size * 0.35), size * 1.3,
                                                  [col("#a89a8c", 0.5 + 0.5 * depth), col("#1a1612", 1)])
            f.c.drawCircle(x, y, size, skia.Paint(AntiAlias=True, Shader=shade))
            continue
        body(f, "asteroid", x, y, size, rotation=spin * f.t * 0.2, light=(-0.6, -0.4, 0.6),
             seed_key=f"rock{i % 6}", atmosphere=False, brightness=0.5 + 0.5 * depth)
        if i == n - 1 and p("highlight_label"):
            label(f, p("highlight_label"), x, y - size, x + 140, y - size - 120, 1.0, size=36)


# ---------------------------------------------------------------- 15. ringed planet

@template("ring_system", sfx=lambda p: [Sfx("shimmer", 0.5)] + ([Sfx("rumble", p("event_at"), dur=4)] if p("event_at") else []))
def ring_system(f, p):
    """A planet with glittering rings. The rings can form from debris or break apart.
    params: kind (planet), tilt (0.15-0.45), ring_color, event (form|break), event_at, camera"""
    _bg(f, p)
    x, y, r = 960, 540, p("size", 230)
    tilt = p("tilt") or rand(f, "tilt", 0.18, 0.38)
    rcol = p("ring_color") or pick(f, "rcol", ["#e8d6b0", "#bfe6ff", "#ffd1e8", "#d8ffd0"])
    ev, at = p("event"), p("event_at")
    k = f.prog(at, 3) if at else 0
    rng = f.rng("ring")
    n = 1600
    rad = r * (1.35 + 0.9 * rng.random(n))
    ang = rng.random(n) * 6.28 + f.t * 0.25 * (r * 1.4 / rad) ** 1.5
    if ev == "form":
        rad = rad * lerp(2.6, 1, ease_out(k)) + (1 - k) * rng.random(n) * 200
    if ev == "break":
        rad = rad + k * rng.random(n) * 600
    xs, ys = x + np.cos(ang) * rad, y + np.sin(ang) * rad * tilt
    front = np.sin(ang) > 0
    sizes = 0.8 + rng.random(n) * 1.6
    alphas = 0.35 + 0.5 * rng.random(n)
    with shot_camera(f, p, x, y):
        dots(f, xs[~front], ys[~front], sizes[~front], alphas[~front] * 0.8, rcol)
        body(f, p("kind", "saturn"), x, y, r, light=(-0.6, -0.4, 0.7))
        dots(f, xs[front], ys[front], sizes[front], alphas[front], rcol)


# ---------------------------------------------------------------- 16. atmosphere escaping

@template("atmosphere_escape", sfx=lambda p: [Sfx("whoosh", 0.5, dur=2.0), Sfx("rumble", "start", dur=6, gain_db=-6)])
def atmosphere_escape(f, p):
    """A planet's air being stripped away into space in glowing streams.
    params: kind (planet), wind_from (left|right), color, at (word it starts on), camera"""
    _bg(f, p)
    x, y, r = 900, 560, p("size", 280)
    d = -1 if (p("wind_from") or "left") == "left" else 1
    col_ = accent(f, p, default=["cyan", "ice", "purple"])
    start = when(f, p("at"), 0.15)
    s = max(f.t - start, 0)
    with shot_camera(f, p, x, y, strength=0.6):
        body(f, p("kind", "mars"), x, y, r, light=(d * 0.7, -0.3, 0.6))
        if s > 0:
            rng = f.rng("gas")
            n = 500
            ang = rng.random(n) * 6.28
            t0 = rng.random(n) * 4
            age = (s + t0) % 4
            px = x + np.cos(ang) * r * 1.02 - d * age * (120 + rng.random(n) * 260)
            py = y + np.sin(ang) * r * 1.02 + (rng.random(n) - 0.5) * age * 40
            a = np.clip(1 - age / 4, 0, 1) * clamp(s)
            dots(f, px, py, 1 + rng.random(n) * 2.5, a * 0.8, col_, add=True)


# ---------------------------------------------------------------- 17. a star's life stages

@template("star_lifecycle", sfx=lambda p: [Sfx("riser", s.get("at", 1.5 + 2 * i), offset=-1.5, dur=1.5) for i, s in enumerate(p("stages", [])[1:4])])
def star_lifecycle(f, p):
    """A star changing through stages (e.g. Sun to red giant to white dwarf), each named as it happens.
    params: stages [{kind (sun|red_giant|white_dwarf|neutron_star|black_hole), name, size, at}], camera"""
    _bg(f, p)
    stages = p("stages", [{"kind": "sun", "name": "The Sun today", "size": 110},
                          {"kind": "red_giant", "name": "Red giant", "size": 300},
                          {"kind": "white_dwarf", "name": "White dwarf", "size": 30}])
    times = [f.time(s["at"]) if s.get("at") else f.dur * i / len(stages) for i, s in enumerate(stages)]
    cur = max(i for i, t in enumerate(times) if f.t >= t or i == 0)
    nxt = min(cur + 1, len(stages) - 1)
    k = f.prog(times[nxt], 1.5) if nxt != cur else 0
    a, b = stages[cur], stages[nxt]
    size = lerp(a.get("size", 120), b.get("size", 120), k)
    with shot_camera(f, p, strength=0.5):
        body(f, a["kind"] if k < 0.5 else b["kind"], 960, 520, size)
        if k > 0.3 and k < 0.7:
            flash(f, times[nxt] + 0.6, dur=0.5, peak=0.4)
    text(f, (a if k < 0.5 else b).get("name", ""), 960, 120, size=60, glow_color=accent(f, p))


# ---------------------------------------------------------------- 18. comet

@template("comet", sfx=lambda p: [Sfx("whoosh", 0.8, dur=2.0), Sfx("shimmer", 1.5)])
def comet(f, p):
    """A comet swinging past a star, its glowing tail always pointing away from the star.
    params: star (sun|none), color, camera"""
    _bg(f, p)
    sx, sy = 300, 540
    col_ = accent(f, p, default=["cyan", "ice", "green"])
    t = f.p
    cx, cy = lerp(1800, 500, t), 540 + 330 * math.sin(math.pi * t) * -1
    with shot_camera(f, p, strength=0.4):
        if p("star", "sun") != "none":
            body(f, "sun", sx, sy, 90)
        ang = math.atan2(cy - sy, cx - sx)
        rng = f.rng("tail")
        n = 400
        L = rng.random(n) ** 0.7 * 520
        spread = (rng.random(n) - 0.5) * 0.35 * (L / 520)
        px = cx + np.cos(ang + spread) * L
        py = cy + np.sin(ang + spread) * L
        dots(f, px, py, 1 + (1 - L / 520) * 3, (1 - L / 520) * 0.7, col_, add=True)
        glow(f, cx, cy, 14, col_)
        body(f, "asteroid", cx, cy, 10, atmosphere=False, light=(sx - cx, sy - cy, 50))


# ---------------------------------------------------------------- 19. eclipse / transit

@template("eclipse", sfx=lambda p: [Sfx("rumble", "start", dur=6, gain_db=-6), Sfx("shimmer", p("at", 2.0))])
def eclipse(f, p):
    """A body slides in front of a star, the light dims and the corona flares out around it.
    params: star (sun|red_giant), blocker (moon|planet kind), at (word of totality), camera"""
    gradient_bg(f)
    starfield(f, n=260, drift=(-2, 0))
    x, y, r = 960, 520, 200
    total = when(f, p("at"), 0.55)
    k = clamp(f.t / max(total, 0.1))
    bx = lerp(960 - 760, 960, ease_out(k))
    after = f.since(total)
    if after > 0:
        bx = 960 + after * 25
    cover = clamp(1 - abs(bx - x) / (r * 2))
    with shot_camera(f, p, strength=0.4):
        body(f, p("star", "sun"), x, y, r, alpha=1 - 0.6 * cover)
        if cover > 0.85:
            for i in range(14):
                a = i / 14 * 6.28 + f.t * 0.05
                soft_light(f, x + math.cos(a) * r * 1.15, y + math.sin(a) * r * 1.15, r * 0.7, "#fff4d6", 0.15 * cover)
        f.c.drawCircle(bx, y, r * 1.0, paint("#05060c", 1))
        ring(f, bx, y, r * 1.0, 3, "#fff4d6", 0.6 * cover)


# ---------------------------------------------------------------- 20. spiral galaxy

@template("galaxy", sfx=lambda p: [Sfx("shimmer", 0.6), Sfx("rumble", "start", dur=6, gain_db=-10)])
def galaxy(f, p):
    """A spiral galaxy of thousands of stars, slowly turning, with an optional 'you are here' marker.
    params: arms (2-4), color, here_label (e.g. 'You are here'), here_at, tilt (0.4-1), camera"""
    gradient_bg(f)
    starfield(f, n=200, drift=(-1, 0))
    rng = f.rng("gal")
    arms = int(p("arms") or rng.integers(2, 5))
    n = 5000
    arm = rng.integers(0, arms, n)
    d = rng.random(n) ** 0.6
    ang = arm * (2 * math.pi / arms) + d * 4.2 + rng.normal(0, 0.28, n) * (1 - d * 0.5) + f.t * 0.03
    rad = d * 460
    tilt = p("tilt") or rand(f, "tilt", 0.5, 0.85)
    xs = 960 + np.cos(ang) * rad
    ys = 540 + np.sin(ang) * rad * tilt
    col_ = accent(f, p, default=["cyan", "purple", "pink", "gold"])
    with shot_camera(f, p):
        soft_light(f, 960, 540, 260, GOLD, 0.6)
        dots(f, xs, ys, 0.6 + rng.random(n) * 1.6, (0.25 + 0.6 * rng.random(n)) * (1.1 - d), col_, add=True)
        dots(f, xs[::7], ys[::7], 0.8 + rng.random(len(xs[::7])), 0.8, INK, add=True)
        if p("here_label"):
            hx, hy = xs[17], ys[17]
            label(f, p("here_label"), hx, hy, hx + 160, hy - 140, p("here_at", 1.0), size=36)


# ---------------------------------------------------------------- 21. zoom out through scales

@template("zoom_scale", sfx=lambda p: [Sfx("whoosh", s.get("at", 1.5 + 2.2 * i)) for i, s in enumerate(p("stages", [])[1:5])])
def zoom_scale(f, p):
    """A 'powers of ten' zoom-out: from a planet, to its system, to the galaxy and beyond, each stage named.
    params: stages [{name, at}] (2-4 names for: planet, orbit, star neighbourhood, galaxy), kind (start body)"""
    stages = p("stages", [{"name": "Earth"}, {"name": "The solar system"}, {"name": "The Milky Way"}])
    times = [f.time(s["at"]) if s.get("at") else f.dur * i / len(stages) for i, s in enumerate(stages)]
    level = 0.0
    for i in range(1, len(stages)):
        level += f.prog(times[i] - 0.8, 1.6)
    gradient_bg(f)
    starfield(f, n=380, drift=(0, 0))
    zoom = 1 / (6 ** min(level, 1.6))
    with camera(f, 960, 540, zoom=1):
        er = 300 * zoom * 6 ** 0
        if er > 1:
            body(f, p("kind", "earth"), 960, 540, er, light=(-0.6, -0.3, 0.7))
        if level > 0.2:
            orb = 300 * 6 * zoom * 0.5
            orbit(f, 960 - orb, 540, orb, orb * 0.4, a=0.5 * clamp(level) * clamp(3 - level), progress=1)
            if orb < 2000:
                body(f, "sun", 960 - orb, 540, max(30 * 6 * zoom, 3))
        if level > 1.2:
            g = clamp((level - 1.2) * 1.5)
            rng = f.rng("zgal")
            n = 3500
            dd = rng.random(n) ** 0.6
            ang = rng.integers(0, 2, n) * math.pi + dd * 4.2 + rng.normal(0, 0.3, n) + f.t * 0.02
            sc = 480 * 6 ** min(2.0 - level, 1.5)  # grows from a far-off speck to filling the screen
            if level < 2:
                soft_light(f, 960, 540, max(sc * 0.4, 6), GOLD, 0.5 * g)
            dots(f, 960 + np.cos(ang) * dd * sc, 540 + np.sin(ang) * dd * sc * 0.6, 0.6 + dd * 1.2,
                 g * (0.3 + 0.6 * (1.1 - dd)), accent(f, p, default=["cyan", "purple", "gold"]), add=True)
    idx = min(int(level + 0.5), len(stages) - 1)
    text(f, stages[idx]["name"], 960, 120, size=62, glow_color=accent(f, p))
