"""Detailed space-phenomena storyboards: formation, breakups, fields, flares, disks."""

import math
from contextlib import contextmanager
from functools import lru_cache

import numpy as np
import skia

from esim.templates import BODY_KINDS, Sfx, accent, body, pick, rand, shot_camera, template, when
from esim.engine import *  # noqa: F401,F403

TAU = 2 * math.pi


# ---------------------------------------------------------------- shared helpers for this module

def _cues(*items):
    return [s for s in items if s is not None]


def _wrap(a):
    return (a + math.pi) % TAU - math.pi


def _ease_np(x):
    x = np.clip(x, 0, 1)
    return np.where(x < 0.5, 4 * x ** 3, 1 - (-2 * x + 2) ** 3 / 2)


def _scr(f, x, y):
    """Where a point drawn now (inside any cameras) lands on the screen."""
    pt = f.c.getTotalMatrix().mapXY(float(x), float(y))
    return pt.x(), pt.y()


def _scale(f):
    return f.c.getTotalMatrix().mapRadius(1.0)


@contextmanager
def _screen(f):
    """Draw in fixed screen pixels, ignoring every camera (HUDs, labels, punchlines)."""
    f.c.save()
    f.c.resetMatrix()
    try:
        yield
    finally:
        f.c.restore()


# screen areas the HUD uses, which callout text keeps out of: (left, top, right, bottom)
_HUD_BOXES = [(W - 620, 0, W, 310), (0, 0, 980, 160)]


def _place(s, ax, ay, dx, dy, size):
    tw = font(size, "semibold").measureText(s)
    tx, ty = ax + dx, clamp(ay + dy, 180, 860)
    if dx >= 0 and tx + 12 + tw > W - 40:
        tx = ax - abs(dx)
    if dx < 0 and tx - 12 - tw < 40:
        tx = ax + abs(dx)
    tx = min(tx, W - 52 - tw) if tx >= ax else max(tx, 52 + tw)
    left, right = (tx + 12, tx + 12 + tw) if tx >= ax else (tx - 12 - tw, tx - 12)
    for (bl, bt, br, bb) in _HUD_BOXES:
        if right > bl and left < br and ty - size < bb and ty + 10 > bt:
            ty = bb + size + 14
    return tx, ty, (left, ty - size * 0.8, right, ty + size * 0.25)


def _callout(f, s, ax, ay, dx, dy, at, color=INK, a=1.0, size=32, avoid=()):
    """A leader-line label in screen space that keeps its text on screen, out of the HUD and the caption zone.
    `avoid` is a list of screen circles (x, y, r) the text should stay clear of: the best of four mirrored
    offsets is used."""
    if a <= 0.02 or f.t < at:
        return
    best = None
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)) if avoid else ((1, 1),):
        tx, ty, (l_, t_, r_, b_) = _place(s, ax, ay, dx * sx, dy * sy, size)
        score = 0.0
        for (cx_, cy_, cr_) in avoid:
            nx_, ny_ = clamp(cx_, l_, r_), clamp(cy_, t_, b_)
            gap = math.hypot(cx_ - nx_, cy_ - ny_) - cr_
            score += min(gap, 0) * 10 + min(gap, 200)
        score -= 0.3 * abs(ty - (ay + dy * sy))  # prefer offsets that didn't need clamping
        if best is None or score > best[0]:
            best = (score, tx, ty)
    _, tx, ty = best
    if a < 0.98:
        with layer(f, a):
            label(f, s, ax, ay, tx, ty, at, size=size, color=color)
    else:
        label(f, s, ax, ay, tx, ty, at, size=size, color=color)


def _stages(f, names, times, color, x=46, y=40, a=1.0):
    """Storyboard chips along the top: which beat of the story we're in."""
    if a <= 0:
        return
    cur = 0
    for i, t in enumerate(times):
        if f.t >= t:
            cur = i
    fnt = font(30, "medium")
    for i, name in enumerate(names):
        s = f"{i + 1:02d} {name}"
        tw = fnt.measureText(s)
        w, h = tw + 34, 50
        c = f.c
        c.save()
        if i == cur:
            pop = ease_back(clamp((f.t - times[i]) / 0.35)) if i > 0 else 1.0
            sc = lerp(0.6, 1.0, pop) * (1 + 0.04 * f.beat_pulse())
            c.translate(x + w / 2, y + h / 2)
            c.scale(sc, sc)
            c.translate(-(x + w / 2), -(y + h / 2))
            rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), 25, 25)
            c.drawRRect(rr, paint(color, 0.35 * a, blur=10, add=True))
            c.drawRRect(rr, paint(color, 0.92 * a))
            text(f, s, x + 17, y + 36, size=30, color="#05070f", align="left", weight="medium", a=a)
        else:
            rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), 25, 25)
            c.drawRRect(rr, paint("#03060f", 0.5 * a))
            c.drawRRect(rr, paint(INK if i < cur else DIM, (0.45 if i < cur else 0.3) * a, stroke=2))
            text(f, s, x + 17, y + 36, size=30, color=INK if i < cur else DIM, align="left", weight="medium",
                 a=(0.8 if i < cur else 0.55) * a)
        c.restore()
        x += w + 12


def _panel(f, title, rows, color, w=520, x=None, y=40, a=1.0):
    """A small HUD readout: a title and rows of (label, value[, value colour])."""
    if a <= 0:
        return
    x = W - 46 - w if x is None else x
    h = 66 + 46 * len(rows)
    c = f.c
    rect = skia.Rect.MakeXYWH(x, y, w, h)
    c.drawRRect(skia.RRect.MakeRectXY(rect, 14, 14), paint("#03060f", 0.62 * a))
    c.drawRRect(skia.RRect.MakeRectXY(rect, 14, 14), paint(color, 0.4 * a, stroke=2))
    for (px, py, sx, sy) in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        c.drawLine(px, py + sy * 6, px, py + sy * 26, paint(color, a, stroke=3))
        c.drawLine(px + sx * 6, py, px + sx * 26, py, paint(color, a, stroke=3))
    blink = 0.5 + 0.5 * math.sin(f.t * 5)
    c.drawCircle(x + 26, y + 31, 6, paint(color, a * (0.4 + 0.6 * blink)))
    text(f, title, x + 42, y + 42, size=30, color=color, align="left", weight="medium", a=a)
    c.drawLine(x + 18, y + 58, x + w - 18, y + 58, paint(color, 0.3 * a, stroke=1.5))
    for i, row in enumerate(rows):
        lab, val = row[0], row[1]
        vc = row[2] if len(row) > 2 else INK
        yy = y + 66 + 46 * i + 31
        text(f, lab, x + 22, yy, size=30, color=DIM, align="left", weight="body", a=a)
        text(f, val, x + w - 22, yy, size=32, color=vc, align="right", weight="semibold", a=a)


def _note(f, s="NOT TO SCALE", y=138):
    text(f, s, 48, y, size=30, color=DIM, align="left", weight="semibold", a=0.75)


def _ellipse_glow(f, cx, cy, r_out, tilt, pos, colors, alphas, add=True):
    """A radial gradient squashed into a tilted disk: dust disks, rings, glows in a plane."""
    c = f.c
    c.save()
    c.translate(cx, cy)
    c.scale(1, tilt)
    cols = [col(cc, a) for cc, a in zip(colors, alphas)]
    sh = skia.GradientShader.MakeRadial(skia.Point(0, 0), r_out, cols, list(pos))
    pt = skia.Paint(AntiAlias=True, Shader=sh)
    if add:
        pt.setBlendMode(skia.BlendMode.kPlus)
    c.drawCircle(0, 0, r_out, pt)
    c.restore()


def _banded_dots(f, xs, ys, sizes, alphas, u, stops, bands=5, add=True):
    """Dots coloured by u (0..1) through colour stops, in a few batched colour bands."""
    if len(xs) == 0:
        return
    idx = np.minimum((np.clip(u, 0, 0.9999) * bands).astype(int), bands - 1)
    centres = (np.arange(bands) + 0.5) / bands
    rgb = ramp(centres, stops)
    sizes = np.broadcast_to(np.asarray(sizes, np.float32), np.shape(xs))
    alphas = np.broadcast_to(np.asarray(alphas, np.float32), np.shape(xs))
    for b in range(bands):
        sel = idx == b
        if sel.any():
            dots(f, xs[sel], ys[sel], sizes[sel], alphas[sel], tuple(rgb[b]), add=add, buckets=3)


def _lines(f, x0, y0, x1, y1, color, a, width, add=True):
    """Many short line segments in one call."""
    if len(x0) == 0:
        return
    pts = []
    for a_, b_, c_, d_ in zip(x0.tolist(), y0.tolist(), x1.tolist(), y1.tolist()):
        pts.append(skia.Point(a_, b_))
        pts.append(skia.Point(c_, d_))
    f.c.drawPoints(skia.Canvas.kLines_PointMode, pts, paint(color, a, stroke=width, add=add))


def _poly_path(xs, ys, close=False):
    path = skia.Path()
    path.moveTo(float(xs[0]), float(ys[0]))
    for x, y in zip(xs[1:], ys[1:]):
        path.lineTo(float(x), float(y))
    if close:
        path.close()
    return path


@lru_cache(maxsize=6)
def _granules(seed, w=1100, h=300, cell=10):

    """A solar-granulation texture: bright convection cells with dark lanes (Worley noise)."""
    rng = np.random.default_rng(seed)
    gx, gy = w // cell + 2, h // cell + 2
    pts = rng.random((gy, gx, 2)).astype(np.float32)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    cxi = (xs // cell).astype(int)
    cyi = (ys // cell).astype(int)
    d1 = np.full((h, w), 1e9, np.float32)
    d2 = np.full((h, w), 1e9, np.float32)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            nx = np.clip(cxi + ox, 0, gx - 1)
            ny = np.clip(cyi + oy, 0, gy - 1)
            px = (nx + pts[ny, nx, 0]) * cell
            py = (ny + pts[ny, nx, 1]) * cell
            d = (xs - px) ** 2 + (ys - py) ** 2
            d2 = np.minimum(d2, np.maximum(d1, d))
            d1 = np.minimum(d1, d)
    d1, d2 = np.sqrt(d1), np.sqrt(d2)
    lanes = np.clip((d2 - d1) / (cell * 0.32), 0, 1) ** 0.7
    centre = 1 - np.clip(d1 / (cell * 0.75), 0, 1)
    large = fractal_noise(w, h, rng, octaves=4, base=5)
    v = (0.18 + 0.6 * lanes + 0.22 * centre) * (0.75 + 0.5 * large)
    rgb = ramp(np.clip(v, 0, 1), [(0, "#3a0800"), (0.3, "#a3300a"), (0.55, "#ec7418"), (0.75, "#ffb43c"),
                                  (0.92, "#ffe08a"), (1, "#fff6d8")])
    rgba = np.empty((h, w, 4), np.uint8)
    rgba[..., :3] = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    rgba[..., 3] = 255
    return skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType)


def _textured_sun(f, x, y, r, seed_key="sun", glow=1.0, pulse=0.0):
    """A big star drawn from a granulation texture: much faster than a full sphere render at large sizes."""
    c = f.c
    for scale, a in ((4.0, 0.22), (2.2, 0.32), (1.45, 0.5)):
        soft_light(f, x, y, r * scale * (1 + 0.03 * pulse), GOLD, a * glow)
    img = _granules(stable_seed(f.seed, f.scene_id, seed_key))
    c.save()
    clip = skia.Path()
    clip.addCircle(x, y, r)
    c.clipPath(clip, doAntiAlias=True)
    drift = (f.t * 6) % 200
    c.drawImageRect(img, skia.Rect.MakeXYWH(x - r - drift, y - r, 2 * r + 220, 2 * r),
                    skia.SamplingOptions(skia.FilterMode.kLinear))
    limb = skia.GradientShader.MakeRadial(skia.Point(x, y), r, [col("#000000", 0), col("#000000", 0.08),
                                                               col("#3a0800", 0.55), col("#200400", 0.85)],
                                          [0, 0.6, 0.92, 1.0])
    c.drawCircle(x, y, r, skia.Paint(AntiAlias=True, Shader=limb))
    c.restore()
    halo(f, x, y, r * 0.98, r * 1.2, "#fff0c8", 0.55 * glow)


@lru_cache(maxsize=4)
def _molten_tex(seed, w=512, h=256):
    rng = np.random.default_rng(seed)
    n = fractal_noise(w, h, rng, octaves=6, base=4)
    n2 = fractal_noise(w, h, rng, octaves=5, base=9)
    n = (n - n.min()) / (np.ptp(n) + 1e-6)
    crack = np.clip(1 - np.abs(n - 0.5) * 16, 0, 1) ** 1.5 + 0.7 * np.clip(1 - np.abs(n2 - 0.5) * 20, 0, 1) ** 1.5
    pools = np.clip((0.22 - n) * 7, 0, 1) + np.clip((n - 0.86) * 7, 0, 1)
    emis = np.clip(crack + pools, 0, 1).astype(np.float32)
    crust = ramp(n2, [(0, "#140805"), (0.5, "#3a1c12"), (1, "#5e3828")]).astype(np.float32)
    return crust, emis


def _molten_planet(f, x, y, r, rotation=0.0, light=(-0.6, -0.4, 0.7), heat=1.0, alpha=1.0, seed_key="molten"):
    """A freshly formed world: dark crust plates split by glowing cracks and lakes of lava."""
    from esim import engine as _E
    d = max(8, int(min(r * 2, 700)) // 4 * 4)
    nx, ny, nz, lat, lon, edge = _E._sphere_grid(d)
    crust, emis = _molten_tex(stable_seed(f.seed, f.scene_id, seed_key))
    th, tw = emis.shape
    ui = (((lon / TAU + 0.5 + rotation) % 1.0) * (tw - 1)).astype(np.int32)
    vi = ((lat / math.pi + 0.5) * (th - 1)).astype(np.int32)
    L = np.array(light, np.float32)
    L /= np.linalg.norm(L) + 1e-6
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    flick = 0.85 + 0.15 * math.sin(f.t * 3.1)
    e = emis[vi, ui] * heat * flick
    out = crust[vi, ui] * (0.15 + 0.85 * lam)[..., None]
    out = out + e[..., None] * np.array([1.0, 0.5, 0.14], np.float32) * (0.75 + 0.5 * nz)[..., None]
    out = out + (1 - nz)[..., None] ** 2 * np.array([0.5, 0.12, 0.02], np.float32) * heat  # hot glowing limb
    a = edge * alpha
    rgba = np.empty((d, d, 4), np.uint8)
    rgba[..., :3] = (np.clip(out, 0, 1) * a[..., None] * 255).astype(np.uint8)
    rgba[..., 3] = (a * 255).astype(np.uint8)
    img = skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
    f.c.drawImageRect(img, skia.Rect.MakeXYWH(x - r, y - r, 2 * r, 2 * r), skia.SamplingOptions(skia.FilterMode.kLinear))


# ---------------------------------------------------------------- 1. planet formation

_DISK_PALETTES = {
    "ember": [(0, "#fff3d6"), (0.1, "#ffd07a"), (0.32, "#ef7a32"), (0.6, "#a5432e"), (1, "#5a2638")],
    "rose": [(0, "#fff0f6"), (0.1, "#ffc0dc"), (0.32, "#e0609a"), (0.6, "#8a48a8"), (1, "#3c2a6a")],
    "teal": [(0, "#f0fffb"), (0.1, "#b0f2ff"), (0.32, "#58b4d8"), (0.6, "#4a62a8"), (1, "#2c2a60")],
    "sand": [(0, "#fffbe8"), (0.1, "#ffe6a0"), (0.32, "#d8a050"), (0.6, "#8a6a4a"), (1, "#3e3442")],
}


@template("planet_formation", sfx=lambda p: _cues(
    Sfx("rumble", "start", dur=6, gain_db=-10),
    Sfx("shimmer", 0.4, gain_db=-8),
    Sfx("pop", p("clump_at"), gain_db=-4) if p("clump_at") else None,
    Sfx("whoosh", p("gap_at"), gain_db=-3) if p("gap_at") else None,
    Sfx("riser", p("glow_at"), offset=-1.6, dur=1.6, gain_db=-4) if p("glow_at") else None,
    Sfx("impact", p("glow_at") or "end", offset=0 if p("glow_at") else -1.2, gain_db=-4)))
def planet_formation(f, p):
    """How a planet is born, as a 4-beat storyboard: a glowing dusty disk spins around a young star (jets
    firing from its poles); dust clumps into planetesimals that collide and grow; one protoplanet sweeps its
    orbit and clears a dark gap; then the camera dives onto the finished planet, glowing molten-hot.
    HUD counts the system's age, the largest body and the planet's temperature.
    params: clump_at (word dust starts clumping), gap_at (word the planet clears its gap),
    glow_at (word for the payoff: the newborn planet glows), title (slam text on the payoff, default
    "A NEW PLANET", "" for none), star (body kind at the centre, default sun), palette (ember|rose|teal|sand),
    color, hud (false hides the HUD)"""
    c_ = accent(f, p, default=["gold", "orange", "pink", "cyan"])
    pal = _DISK_PALETTES.get(p("palette")) or _DISK_PALETTES[pick(f, "pf_pal", list(_DISK_PALETTES))]
    t1 = when(f, p("clump_at"), 0.24)
    t2 = when(f, p("gap_at"), 0.5)
    t3 = when(f, p("glow_at"), 0.76)
    kc = f.prog(t1, 2.4)
    kg = f.prog(t2, 2.2)
    kh = f.prog(t3, 1.1, ease=ease_out)
    s3 = f.t - t3
    pulse = f.beat_pulse()
    cx, cy = 960, 510
    tilt = rand(f, "pf_tilt", 0.3, 0.38)
    rot = rand(f, "pf_rot", -8, 8)
    rr_ = math.radians(rot)
    Rin, Rout = 92, 840
    Rp = rand(f, "pf_rp", 0.4, 0.5) * Rout
    gapw = 64.0

    def omega(r):
        return 0.5 * (220.0 / r) ** 1.5

    wp = omega(Rp)
    th_pay = math.pi / 2 + rand(f, "pf_th", -0.6, 0.4)
    thp = th_pay + wp * (f.t - t3)  # the planet's orbit puts it on the near side for the payoff

    def to_screen_world(x, y):  # disk frame -> camera-world (rotated about the star)
        dx, dy = x - cx, y - cy
        return cx + dx * math.cos(rr_) - dy * math.sin(rr_), cy + dx * math.sin(rr_) + dy * math.cos(rr_)

    pwx, pwy = to_screen_world(cx + math.cos(thp) * Rp, cy + math.sin(thp) * Rp * tilt)

    # background: a star-forming region
    gradient_bg(f, "#080a1c", "#020309")
    nebula_glow(f, key="pf_neb", alpha=0.5)
    starfield(f, n=360, drift=(rand(f, "pf_dx", -6, 6), 0), key="pf_stars")

    # camera: slow drift and push, then a dive onto the new planet
    dive = ease_in_out(f.prog(t3 - 0.5, 1.5, ease=lambda v: clamp(v)))
    zoom = lerp(1.0 + 0.07 * ease_in_out(f.p), 2.3, dive)
    camx = lerp(cx + 30 * math.sin(f.t * 0.25), pwx, dive)
    camy = lerp(cy + 20 * math.cos(f.t * 0.2), pwy, dive)
    shake = 10 * math.exp(-s3 * 3) if s3 > 0 else 0

    rng = f.rng("pf_dust")
    n = 3800
    u = rng.random(n) ** 1.5
    rad = Rin + (Rout - Rin) * u
    a0 = rng.random(n) * TAU
    ang = a0 + omega(rad) * f.t
    size = 0.7 + rng.random(n) * 1.7
    alpha = (0.25 + 0.6 * rng.random(n)) * (1 + 0.25 * pulse)
    # planetesimal clumps: clump 0 becomes the planet
    rng2 = f.rng("pf_clumps")
    nC = 9
    crs = np.concatenate([[Rp], Rin * 1.7 + rng2.random(nC - 1) * (Rout * 0.88 - Rin * 1.7)])
    crs[1:] = np.where(np.abs(crs[1:] - Rp) < 110, crs[1:] + 220, crs[1:])
    crs = np.minimum(crs, Rout * 0.92)
    cang0 = rng2.random(nC) * TAU
    cang0[0] = thp - wp * f.t
    cang = cang0 + omega(crs) * f.t
    csz = 0.6 + rng2.random(nC) * 0.8
    csz[0] = 1.2
    dr = rad[:, None] - crs[None, :]
    da = (a0[:, None] - cang0[None, :] + math.pi) % TAU - math.pi
    member = (np.abs(dr) < 46) & (np.abs(da) < 0.75)
    has = member.any(axis=1)
    cid = np.argmax(member, axis=1)
    if kc > 0:
        m = has
        dcur = (ang[m] - cang[cid[m]] + math.pi) % TAU - math.pi
        rad = rad.copy()
        ang = ang.copy()
        rad[m] = crs[cid[m]] + dr[m, cid[m]] * (1 - 0.92 * kc)
        ang[m] = cang[cid[m]] + dcur * (1 - 0.95 * kc)
        alpha = alpha * np.where(m, 1 - 0.45 * kc, 1.0)
    if kg > 0:  # the planet eats its clump and pushes the rest of its lane to the gap edges
        planet_m = has & (cid == 0)
        alpha = alpha * np.where(planet_m, 1 - kg, 1.0)
        band = (np.abs(rad - Rp) < gapw) & ~planet_m
        sgn = np.sign(rad - Rp + 1e-3)
        pushed = Rp + sgn * (gapw + 0.35 * np.abs(rad - Rp))
        rad = np.where(band, lerp(rad, pushed, kg), rad)
    xs = cx + np.cos(ang) * rad
    ys = cy + np.sin(ang) * rad * tilt
    front = np.sin(ang) > 0
    ucol = (rad - Rin) / (Rout - Rin)

    # the disk's glow, with the gap carved into it
    pos = np.linspace(0, 1, 44)
    x_in = Rin / Rout
    base = (0.55 + 0.45 * np.clip((pos - x_in * 0.6) / (x_in * 0.5), 0, 1)) * (1 - pos) ** 1.4
    xp = Rp / Rout
    gw = gapw / Rout
    dip = np.exp(-((pos - xp) / (gw * 0.75)) ** 2)
    edge = np.exp(-((np.abs(pos - xp) - gw * 1.15) / (gw * 0.35)) ** 2)
    rings_ = 1 + 0.18 * np.sin(pos * rand(f, "pf_rings", 40, 70))  # faint concentric ringlets, like real disks
    prof = base * rings_ * (1 - 0.85 * kg * dip + 0.5 * kg * edge)
    cols = [tuple(v) for v in ramp((pos - x_in).clip(0, 1) / (1 - x_in), pal)]

    stars_screen = {}
    with camera(f, camx, camy, zoom=zoom, shake=shake):
        f.c.save()
        f.c.rotate(rot, cx, cy)
        _ellipse_glow(f, cx, cy, Rout, tilt, pos, cols, list(prof * (0.85 + 0.15 * pulse)))
        if kg > 0:  # the cleared lane reads as a dark ring
            _ellipse_glow(f, cx, cy, Rout, tilt, pos, ["#000000"] * len(pos), list(0.55 * kg * dip), add=False)
        # back half of the disk, behind the star
        _banded_dots(f, xs[~front], ys[~front], size[~front], alpha[~front] * 0.85, ucol[~front], pal)
        cpos = [(cx + math.cos(cang[j]) * crs[j], cy + math.sin(cang[j]) * crs[j] * tilt) for j in range(nC)]
        # collisions: sparks as planetesimals smash together and grow
        sparks = [(t1 + 0.5 + k * max(t3 - t1 - 0.6, 1.0) / 7, 1 + k % (nC - 1) if k % 3 else 0) for k in range(7)]
        hits = np.zeros(nC)
        for ts, j in sparks:
            if f.t >= ts:
                hits[j] += 1
        crad = np.where(kc > 0, (2.0 + 6.5 * kc * csz) * (1 + 0.18 * hits), 0)

        def draw_clump(j):
            x, y = cpos[j]
            if j == 0 or crad[j] < 0.8:
                return
            if crad[j] < 3:
                dots(f, [x], [y], crad[j], 0.9, "#d8c8b0")
            else:
                planet(f, "rocky", x, y, crad[j], light=(cx - x, cy - y, 0.4 * math.hypot(cx - x, cy - y)),
                       atmosphere=False, seed_key="pf_clump", rotation=j * 0.13, brightness=1.4)

            soft_light(f, x, y, crad[j] * 4, pal[1][1], 0.35 * kc)

        for j in range(nC):
            if math.sin(cang[j]) <= 0:
                draw_clump(j)
        # the young star and its polar jets (the south jet points away from us, behind the near disk)
        jr = f.rng("pf_jet")
        nj = 120
        ju, jv = jr.random(nj), jr.random(nj)
        z = (ju + f.t * 0.45) % 1.0
        for side in (1, -1):
            jy = cy - side * (60 + 430 * z)
            jx = cx + (jv - 0.5) * (6 + 60 * z)
            f.c.drawLine(cx, cy - side * 50, cx, cy - side * 480, paint("#9fe6ff", 0.12, stroke=14, blur=8, add=True))
            dots(f, jx, jy, 1.2 + 1.6 * (1 - z), (1 - z) ** 1.5 * 0.75, "#bff0ff", add=True)
            if side == 1:
                body(f, p("star", "sun"), cx, cy, 50 * (1 + 0.05 * pulse))
                soft_light(f, cx, cy, 260, pal[1][1], 0.25 + 0.25 * pulse)
        stars_screen["star"] = _scr(f, cx, cy - 50)
        # near half of the disk
        _banded_dots(f, xs[front], ys[front], size[front], alpha[front], ucol[front], pal)
        for j in range(nC):
            if math.sin(cang[j]) > 0:
                draw_clump(j)
        for ts, j in sparks:
            s = f.t - ts
            if 0 <= s < 0.7:
                x, y = cpos[j]
                soft_light(f, x, y, 26 + 60 * s, "#fff0c8", 0.9 * (1 - s / 0.7))
                ang_s = np.linspace(0, TAU, 14, endpoint=False) + j
                dots(f, x + np.cos(ang_s) * (4 + 60 * s), y + np.sin(ang_s) * (4 + 60 * s) * 0.6, 1.6,
                     (1 - s / 0.7), "#ffe2a0", add=True)
        if s3 > 0:  # the gap-clearing shock sweeps out through the disk
            for k, (spd, w_) in enumerate(((320, 10), (210, 5))):
                rr = 20 + spd * s3
                aa = clamp(1 - s3 / 1.8)
                f.c.save()
                f.c.translate(*cpos[0])
                f.c.scale(1, tilt)
                ring(f, 0, 0, rr, w_, c_ if k == 0 else INK, 0.7 * aa)
                f.c.restore()
        # where things are on screen, for labels and the planet
        disk_pt = _scr(f, cx + math.cos(0.45) * Rout * 0.5, cy + math.sin(0.45) * Rout * 0.5 * tilt)
        clump_pt = _scr(f, *cpos[2])
        gap_ang = thp + 2.3
        gap_pt = _scr(f, cx + math.cos(gap_ang) * Rp, cy + math.sin(gap_ang) * Rp * tilt)
        p_scr = _scr(f, *cpos[0])
        dev_scale = _scale(f)
        f.c.restore()

    scr = _screen(f)
    scr.__enter__()
    # the planet itself, drawn at screen resolution so it stays crisp in the dive
    pr = ((4 + 11.0 * kc) + 9 * kg + 13 * kh) * dev_scale

    if kc > 0.02:
        px, py = p_scr
        sx, sy = stars_screen["star"]
        L = (sx - px, sy - py, 0.35 * math.hypot(sx - px, sy - py) + 1)
        soft_light(f, px, py, pr * 4, pal[1][1], 0.45 * (1 - kh))
        ring(f, px, py, pr * 1.9, 2, c_, 0.6 * (1 - kh) * clamp(kc * 3))
        if kh < 1:
            planet(f, "rocky", px, py, pr, light=L, atmosphere=False, seed_key="pf_planet", rotation=f.t * 0.04,
                   brightness=1.3)
        if kh > 0:  # freshly assembled: molten all over, glowing from the heat of the collisions
            soft_light(f, px, py, pr * 4.5, "#ff7a2a", 0.45 * kh * (1 + 0.4 * pulse))
            _molten_planet(f, px, py, pr, rotation=f.t * 0.04, light=L, heat=0.6 + 0.6 * kh, alpha=kh)


            halo(f, px, py, pr * 0.98, pr * 1.4, "#ffae5a", 0.7 * kh * (1 + 0.3 * pulse))

    # annotations (screen space)
    fade_lab = 1 - dive
    _callout(f, "YOUNG STAR", *stars_screen["star"], -240, -150, 0.4, a=fade_lab)
    _callout(f, "DUST DISK", *disk_pt, 150, 150, 1.0, a=fade_lab)
    _callout(f, "PLANETESIMALS", *clump_pt, 170, -150, t1 + 0.9, a=fade_lab)
    if kc > 0.05:
        _callout(f, "PROTOPLANET", *p_scr, -200, -170, t2 + 0.2, color=c_, a=fade_lab)
    _callout(f, "GAP", *gap_pt, -160, 140, t2 + 1.1, a=fade_lab)
    if kh > 0:
        _callout(f, "MOLTEN SURFACE", p_scr[0] - pr * 0.6, p_scr[1] + pr * 0.6, -220, 120, t3 + 0.9, color=GOLD)

    if p("hud", True):
        age_log = float(np.interp(f.t, [0, t1, t2, t3, max(f.dur, t3 + 0.1)], [-2.3, -1.0, 0.0, 1.0, 1.3]))
        age = 10 ** age_log
        age_s = f"{age * 1000:,.0f} thousand yrs" if age < 1 else f"{age:.1f} million yrs"
        largest = ["dust grains", "10 km rocks", "moon-sized", "planet-sized"][sum(f.t >= t for t in (t1, t2, t3))]
        temp = "—" if f.t < t2 else f"{lerp(300, 1100, kg) + 900 * kh:,.0f} °C"
        _panel(f, "DISK MONITOR", [("AGE", age_s), ("LARGEST", largest), ("PLANET TEMP", temp, GOLD if kh else INK)],
               c_, w=500)
        _stages(f, ["DISK", "CLUMPS", "GAP", "PLANET"], [0, t1, t2, t3], c_)
        _note(f)
    title = p("title", "A NEW PLANET")
    if title:
        slam_text(f, title, 960, 800, t3 + 0.15, size=130, glow_color=c_, hold=None)
    scr.__exit__(None, None, None)
    flash(f, t3, dur=0.5, color="#fff1d0", peak=0.7)


# ---------------------------------------------------------------- 2. a moon torn apart inside the Roche limit

_RUBBLE = {"ice": "#dceeff", "moon": "#d8cbb6", "rocky": "#cdbba3", "mars": "#e3a47c", "asteroid": "#c9b9a6",
           "frozen_earth": "#e6f0ff"}


@template("roche_breakup", sfx=lambda p: _cues(
    Sfx("rumble", "start", dur=6, gain_db=-8),
    Sfx("glitch", p("crack_at"), gain_db=-4) if p("crack_at") else Sfx("whoosh", 0.3, gain_db=-8),
    Sfx("riser", p("break_at"), offset=-1.5, dur=1.5, gain_db=-4) if p("break_at") else None,
    Sfx("impact", p("break_at") or "end", offset=0 if p("break_at") else -2.0),
    Sfx("shimmer", p("ring_at")) if p("ring_at") else None))
def roche_breakup(f, p):
    """A moon spirals inside its planet's Roche limit and is torn apart, as a 4-beat storyboard: the moon
    spirals in across the dashed Roche-limit line (it flashes red); tides stretch it into an egg and glowing
    fault lines crack across it while it sheds streams of dust; it shatters into rubble; then the rubble
    smears around the orbit into a brand-new ring (inner pieces orbit faster). HUD shows distance in planet
    radii, tidal stretch and status.
    params: cross_at (word the moon crosses the Roche limit), crack_at (word the cracks appear),
    break_at (word it shatters), ring_at (word the ring forms, the payoff), kind (planet, default random
    gas/ice giant), moon (moon kind: moon|rocky|ice|mars|asteroid), title (slam on the payoff, default
    "A NEW RING", "" for none), size (planet radius, default 165), color, hud"""
    c_ = accent(f, p, default=["cyan", "gold", "pink", "orange", "ice"])
    kind = p("kind") or pick(f, "rb_kind", ["saturn", "jupiter", "neptune", "uranus", "gas", "ice"])
    moon = p("moon") or pick(f, "rb_moon", ["moon", "rocky", "ice", "mars", "asteroid"])
    rub = _RUBBLE.get(moon, "#d8cbb6")
    t1 = when(f, p("cross_at"), 0.2)
    t2 = when(f, p("crack_at"), 0.36)
    t3 = when(f, p("break_at"), 0.55)
    t4 = when(f, p("ring_at"), 0.74)
    t2, t3 = max(t2, t1 + 0.2), max(t3, t1 + 0.4)
    t4 = max(t4, t3 + 0.3)
    pulse = f.beat_pulse()
    cx, cy = 960, 505
    R = p("size", 175)
    tilt = rand(f, "rb_tilt", 0.36, 0.44)
    rm = 50.0

    a0, aR, aB = 3.2 * R, 2.0 * R, 1.62 * R

    def a_of(t):
        return np.interp(t, [0, t1, t3], [a0, aR, aB])

    def om_u(a):
        return (aR / a) ** 1.5

    top = max(f.t, t3, t4) + 0.1
    grid = np.linspace(0, top, 500)
    wv = om_u(a_of(grid))
    I = np.concatenate([[0], np.cumsum((wv[1:] + wv[:-1]) * 0.5 * np.diff(grid))])
    span = float(np.interp(t3, grid, I) - np.interp(t1, grid, I))
    W0 = clamp(1.7 / max(span, 1e-3), 0.15, 1.1)  # cross -> break covers ~100 degrees on the near side
    th_cross = 0.05

    def theta(t):
        return th_cross + W0 * (np.interp(t, grid, I) - np.interp(t1, grid, I))

    def om(a):
        return W0 * om_u(a)

    s3 = f.t - t3
    kst = f.prog(t1, t3 - t1, ease=ease_in) if f.t < t3 else 1.0
    stretch = 0.45 * kst
    kcr = f.prog(t2, max(t3 - t2, 0.3), ease=lambda v: clamp(v))
    kr = f.prog(t4, 2.4)
    th_m, a_m = float(theta(f.t)), float(a_of(f.t))
    th_b = float(theta(t3))

    gradient_bg(f)
    nebula_glow(f, key="rb_neb", alpha=rand(f, "rb_neba", 0.4, 0.6))
    starfield(f, n=400, drift=(rand(f, "rb_dx", -6, 6), 0), key="rb_stars")

    # camera: slow push towards the action, a hit on the breakup, and a gentle settle for the ring
    mx = cx + math.cos(th_m) * a_m
    my = cy + math.sin(th_m) * a_m * tilt
    follow = 0.25 * clamp(f.t / max(t3, 0.1)) * (1 - kr)
    zoom = 1.0 + 0.1 * ease_in_out(clamp(f.t / max(t3, 0.1))) - 0.06 * kr
    shake = 18 * math.exp(-s3 * 3) if s3 > 0 else 3 * kcr
    labels = {}
    with camera(f, lerp(cx, mx, follow), lerp(cy, my, follow), zoom=zoom, rotate=lerp(0, 2.5, kr), shake=shake):
        # ---- debris after the breakup (computed first, drawn in back and front halves)
        dr_ = f.rng("rb_debris")
        nd = 2400
        rr0 = np.sqrt(dr_.random(nd))
        aa0 = dr_.random(nd) * TAU
        ur, ut = rr0 * np.cos(aa0), rr0 * np.sin(aa0)
        if s3 >= 0:
            k_sp = f.prog(t3, 1.6, ease=ease_out)
            dr = ur * rm * 1.42 * (1 + 0.3 * kr)
            a_i = aB + dr
            dth = ut * rm * 0.75 / aB * (1 + 1.6 * k_sp)
            T = s3 + 18 * max(0.0, f.t - t4) * kr
            th_i = th_b + dth + om(aB) * s3 + (om(a_i) - om(aB)) * T
            Xp, Yp = np.cos(th_i) * a_i, np.sin(th_i) * a_i
            dx_ = cx + Xp
            dy_ = cy + Yp * tilt
            shadow = (Xp > 0) & (np.abs(Yp) < R)
            d_alpha = (0.3 + 0.55 * dr_.random(nd)) * np.where(shadow, 0.18, 1.0) * (1 + 0.3 * pulse)
            d_size = 0.8 + dr_.random(nd) * 1.6
            d_front = np.sin(th_i) > 0
            hot = dr_.random(nd) < 0.22
        # ring glow once it settles
        rpos = np.linspace(0, 1, 30)
        inner = (aB - rm * 1.42 * 1.3) / (aB + rm * 1.42 * 1.3)
        band_noise = 0.55 + 0.45 * f.rng("rb_bands").random(30)
        ring_a = np.where(rpos > inner, band_noise * np.sin(np.clip((rpos - inner) / (1 - inner), 0, 1) * math.pi), 0)
        ring_r = aB + rm * 1.42 * 1.3

        def ring_half(back):
            if kr <= 0:
                return
            f.c.save()
            f.c.clipRect(skia.Rect.MakeLTRB(0 - 400, cy - 600 if back else cy, W + 400, cy if back else cy + 600))
            pass  # the planet's shadow on the ring is carried by the dimmed debris
            _ellipse_glow(f, cx, cy, ring_r, tilt, rpos, [rub] * 30, list(ring_a * 0.5 * kr))
            f.c.restore()

        def roche_half(back):
            crossed = f.t >= t1
            warn = math.exp(-(f.t - t1) * 2.5) if crossed else 0
            colr = RED if crossed else DIM
            pth = skia.Path()
            pth.addOval(skia.Rect.MakeLTRB(cx - aR, cy - aR * tilt, cx + aR, cy + aR * tilt))
            pt = paint(colr, 0.55 + 0.4 * warn, stroke=3)
            pt.setPathEffect(skia.DashPathEffect.Make([16, 12], -f.t * 30))
            f.c.save()
            f.c.clipRect(skia.Rect.MakeLTRB(0, cy - 800 if back else cy, W, cy if back else cy + 800))
            f.c.drawPath(pth, pt)
            if warn > 0.02:
                f.c.drawPath(pth, paint(RED, 0.5 * warn, stroke=14, blur=8, add=True))
            f.c.restore()

        # ---- back layers
        roche_half(True)
        ring_half(True)
        if s3 >= 0:
            sel = ~d_front
            dots(f, dx_[sel], dy_[sel], d_size[sel], d_alpha[sel] * 0.85, rub, add=True)
        # ---- the moon (before it breaks) and its shed dust
        ns = 420
        sr_ = f.rng("rb_shed")
        tb_i = t1 + 0.3 + sr_.random(ns) * max(t3 - t1 - 0.3, 0.2)
        side = np.where(sr_.random(ns) < 0.5, -1.0, 1.0)
        born = (tb_i <= f.t)
        moon_parts = []
        if born.any():
            ab = a_of(tb_i) + side * rm * (1.0 + 0.5 * sr_.random(ns)) * (1 + stretch)
            th0_ = theta(tb_i) + (sr_.random(ns) - 0.5) * 0.05
            age = np.maximum(f.t - tb_i, 0)
            th_s = th0_ + om(ab) * age
            sx_ = cx + np.cos(th_s) * ab
            sy_ = cy + np.sin(th_s) * ab * tilt
            sa = born * np.clip(1 - age / 6, 0, 1) * 0.7
            moon_parts.append((sx_, sy_, sa, np.sin(th_s) > 0))
            dots(f, sx_[~(np.sin(th_s) > 0)], sy_[~(np.sin(th_s) > 0)], 1.4, sa[~(np.sin(th_s) > 0)], rub, add=True)

        def draw_moon():
            if s3 >= 0.05:
                return
            ang_deg = math.degrees(math.atan2(cy - my, cx - mx))
            arad = math.radians(ang_deg)
            Lx, Ly = -0.8, -0.25
            light = (Lx * math.cos(arad) + Ly * math.sin(arad), -Lx * math.sin(arad) + Ly * math.cos(arad), 0.55)
            jit = 2.5 * kcr * math.sin(f.t * 47)
            c = f.c
            # trail of the inspiral
            pts = [(cx + math.cos(float(theta(tt))) * float(a_of(tt)), cy + math.sin(float(theta(tt))) * float(a_of(tt)) * tilt)
                   for tt in np.linspace(max(0, f.t - 1.6), f.t, 18)]
            trail(f, pts, c_, width=3, a=0.55)
            if kcr > 0:
                soft_light(f, mx, my, rm * 2.6, "#ff6a2a", 0.35 * kcr * (1 + 0.5 * pulse))
            c.save()
            c.translate(mx + jit, my)
            c.rotate(ang_deg)
            c.scale(1 + stretch, 1 - 0.28 * stretch)
            body(f, moon, 0, 0, rm, light=light, seed_key="rb_moon", rotation=0.0)
            if kcr > 0:
                clip = skia.Path()
                clip.addCircle(0, 0, rm)
                c.clipPath(clip, doAntiAlias=True)
                cr = f.rng("rb_cracks")
                for k in range(7):
                    x0, y0 = (cr.random() - 0.5) * rm * 0.9, (cr.random() - 0.5) * rm * 1.6
                    head = math.pi / 2 + (cr.random() - 0.5) * 0.9  # faults run across the stretch axis
                    xsk, ysk = [x0], [y0]
                    for _ in range(9):
                        head += (cr.random() - 0.5) * 0.9
                        x0 += math.cos(head) * rm * 0.16
                        y0 += math.sin(head) * rm * 0.16
                        xsk.append(x0)
                        ysk.append(y0)
                    pth = _poly_path(xsk, ysk)
                    kk = clamp(kcr * 1.6 - k * 0.09)
                    draw_partial(f, pth, kk, paint("#ff6a1f", 0.7 * kk, stroke=7, blur=4, add=True))
                    draw_partial(f, pth, kk, paint("#ffe6a8", 0.95 * kk, stroke=2.2))
            c.restore()
            labels["moon"] = (mx, my)
            labels["moon_s"] = _scr(f, mx, my - rm)
            labels["tip_s"] = _scr(f, mx + (cx - mx) / max(math.hypot(cx - mx, cy - my), 1) * rm * (1 + stretch),
                                   my + (cy - my) / max(math.hypot(cx - mx, cy - my), 1) * rm * (1 + stretch))

        if math.sin(th_m) <= 0:
            draw_moon()
        # ---- the planet
        soft_light(f, cx, cy, R * 3.2, c_, 0.14 + 0.1 * pulse)
        halo(f, cx, cy, R, R * 1.5, c_, 0.25)
        body(f, kind, cx, cy, R, light=(-0.8, -0.25, 0.55), seed_key="rb_planet")
        # ---- front layers
        ring_half(False)
        roche_half(False)
        if moon_parts:
            sx_, sy_, sa, fr = moon_parts[0]
            dots(f, sx_[fr], sy_[fr], 1.4, sa[fr], rub, add=True)
        if math.sin(th_m) > 0:
            draw_moon()
        if s3 >= 0:
            sel = d_front
            dots(f, dx_[sel], dy_[sel], d_size[sel], d_alpha[sel], rub, add=True)
            hk = clamp(1 - s3 / 2.5)
            if hk > 0:
                dots(f, dx_[hot], dy_[hot], d_size[hot] * 1.3, d_alpha[hot] * hk, "#ff8a3d", add=True)
            # chunky rubble: irregular lit polygons that grind down as the ring forms
            ch = f.rng("rb_chunks")
            nch = 60
            for i in range(nch):
                j = int(ch.integers(0, nd))
                sz = (3 + ch.random() ** 2 * 13) * lerp(1, 0.45, kr)
                x, y = float(dx_[j]), float(dy_[j])
                if not d_front[j] and abs(x - cx) < R and abs(y - cy) < R * 0.95:
                    continue  # hidden behind the planet
                nv = 7
                spin = ch.random() * 6 + f.t * (ch.random() - 0.5) * 3
                angs = spin + np.linspace(0, TAU, nv, endpoint=False)
                rad = sz * (0.6 + 0.4 * ch.random(nv))
                pth = _poly_path(x + np.cos(angs) * rad, y + np.sin(angs) * rad, close=True)
                dim = 0.25 if shadow[j] else 1.0
                f.c.drawPath(pth, paint(mix(rub, "#000000", 0.55 + 0.25 * (1 - dim)), 1))
                hl = skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
                    [skia.Point(x - sz, y), skia.Point(x + sz, y)], [col(rub, 0.95 * dim), col(rub, 0)]))
                f.c.drawPath(pth, hl)
            glow(f, cx + math.cos(th_b) * aB, cy + math.sin(th_b) * aB * tilt, 30 * math.exp(-s3 * 1.5) + 4,
                 "#ffd8a0", clamp(1 - s3 * 0.6))
            labels["debris"] = _scr(f, float(dx_[7]), float(dy_[7]))
        shockwave(f, mx, my, t3, speed=650, life=1.6, color=c_, width=18)
        labels["roche"] = _scr(f, cx - aR * math.cos(0.5), cy + aR * math.sin(0.5) * tilt)
        labels["ring"] = _scr(f, cx - ring_r * 0.92, cy + ring_r * 0.3 * tilt)

    scr = _screen(f)
    scr.__enter__()
    if s3 < 0.05:
        _callout(f, "MOON", *labels["moon_s"], 130, -120, 0.3, a=clamp(1 - kst * 2))
        _callout(f, "TIDAL STRETCH", *labels["tip_s"], -170, 160, t1 + 0.5, color=GOLD)
        _callout(f, "FAULT LINES", *labels["moon_s"], 170, -130, t2 + 0.3, color="#ffb070")
    _callout(f, "ROCHE LIMIT", *labels["roche"], -200, 150, 0.7, color=RED if f.t >= t1 else INK)
    if s3 > 0:
        _callout(f, "DEBRIS", *labels["debris"], 170, 140, t3 + 0.6, a=1 - kr)
    if kr > 0:
        _callout(f, "NEW RING", *labels["ring"], -150, -200, t4 + 0.6, color=c_)

    if p("hud", True):
        if s3 < 0:
            dist, status = f"{a_m / R:.2f} radii", ("safe orbit", GREEN) if f.t < t1 else (
                ("inside limit", RED) if f.t < t2 else ("cracking", "#ff8a3d"))
        else:
            dist, status = "1.2–2.1 radii", ("shattered", RED) if f.t < t4 else ("ring forming", c_)
        _panel(f, "TIDAL MONITOR", [("DISTANCE", dist), ("TIDAL STRETCH", f"+{stretch * 100:.0f}%"),
                                    ("STATUS", status[0], status[1]),
                                    ("TIME", "real time" if f.t < t4 else "fast-forward", INK if f.t < t4 else GOLD)],
               c_, w=520)
        _stages(f, ["INSPIRAL", "STRETCH", "BREAKUP", "RING"], [0, t1, t3, t4], c_)
        _note(f)
    title = p("title", "A NEW RING")
    if title:
        slam_text(f, title, 960, 810, t4 + 0.2, size=130, glow_color=c_)
    scr.__exit__(None, None, None)
    flash(f, t3, dur=0.45, color="#fff1d8", peak=0.75)
    flash(f, t4, dur=0.35, color=c_, peak=0.25)


# ---------------------------------------------------------------- 3. magnetosphere vs the solar wind

def _flow_y(X, Yf, b, taper_len, iters=12):
    """Streamlines around a Rankine half-body (uniform flow + source): the shape of a magnetosphere.
    X is distance downstream of the source, Yf the stream's height far upstream; returns its height at X."""
    ay = np.abs(Yf) + 1.0
    taper = 1.0 / (1.0 + 0.55 * np.maximum(X, 0) / taper_len)
    Y = ay + b * taper * 0.5
    for _ in range(iters):
        th = np.arctan2(Y, X)
        Y = 0.5 * Y + 0.5 * (ay + b * taper * (1 - th / math.pi))
    return np.sign(Yf + 1e-6) * Y


@template("magnetosphere", sfx=lambda p: _cues(
    Sfx("rumble", "start", dur=6, gain_db=-10),
    Sfx("whoosh", p("shock_at"), gain_db=-3) if p("shock_at") else Sfx("whoosh", 0.5, gain_db=-6),
    Sfx("shimmer", p("aurora_at")) if p("aurora_at") else Sfx("shimmer", "end", offset=-2.0, gain_db=-6),

    Sfx("power_down", p("collapse_at")) if p("collapse_at") else None,
    Sfx("impact", p("collapse_at"), offset=1.0, gain_db=-4) if p("collapse_at") else None))
def magnetosphere(f, p):
    """A planet's magnetic shield at work: solar-wind particles stream in from the Sun on the left and are
    deflected around the planet's field lines, as a storyboard: the wind streams past the dipole field; the bow
    shock lights up where the wind piles up and heats (magnetotail stretched behind); particles funnel down
    the field lines into the poles and auroras flare. Optional 4th beat (collapse_at or collapse: true): the
    field collapses, the wind slams into the surface and strips the atmosphere away into space.
    params: shock_at (word the bow shock lights up), aurora_at (word the auroras flare), collapse_at (word the
    field dies, optional), collapse (true to include the collapse without a word), kind (planet, default
    earth), title (slam on the last beat, optional), size (planet radius, default 82), color, hud"""
    c_ = accent(f, p, default=["cyan", "purple", "ice", "green"])
    kind = p("kind", "earth")
    collapse = bool(p("collapse_at") or p("collapse"))
    t1 = when(f, p("shock_at"), 0.2)
    t2 = when(f, p("aurora_at"), 0.48)
    t3 = when(f, p("collapse_at"), 0.72) if collapse else 1e9
    ks = f.prog(t1, 1.0)
    ka = f.prog(t2, 1.2)
    kcol = f.prog(t3, 2.0) if collapse else 0.0
    pulse = f.beat_pulse()
    R = p("size", 80)
    pcx, pcy = 1010, 480
    xs_src = pcx + 0.3 * R
    b = 1.95 * R * math.pi * (1 - kcol)  # magnetopause nose ~2 planet radii upstream (really ~10: not to scale)
    b_s = b * 1.32
    tl = 2.6 * R

    gradient_bg(f, "#070a1a", "#02030a")
    nebula_glow(f, key="ms_neb", alpha=0.25)
    starfield(f, n=320, drift=(-3, 0), key="ms_stars")
    # the Sun, just off the left edge
    soft_light(f, -260, pcy, 900, GOLD, 0.35 + 0.1 * pulse)
    soft_light(f, -260, pcy, 420, "#fff0c0", 0.55)

    zoom = 1.0 + 0.05 * ease_in_out(f.p) + 0.12 * ka * (1 - kcol * 0.5)
    shake = (14 * math.exp(-(f.t - t3) * 2) if f.t > t3 else 0) + 4 * kcol
    labels = {}
    with camera(f, lerp(960, pcx, 0.35 * ka), pcy + 20, zoom=zoom, shake=shake):
        # ---- solar wind particles
        wr = f.rng("ms_wind")
        n = 1300
        yf = (wr.random(n) - 0.5) * 1250
        x0 = wr.random(n) * (W + 400)
        spd = 360 * (0.8 + 0.4 * wr.random(n))
        span = W + 400
        x = (x0 + spd * f.t) % span - 200
        X = x - xs_src
        if b > 1:
            y = _flow_y(X, yf, b, tl)
            yp = _flow_y(X - spd * 0.05, yf, b, tl)
            shock_y = _flow_y(X, np.full(n, 0.5), b_s, tl * 1.3)
            sheath = np.abs(y) < np.abs(shock_y)
        else:
            y, yp, sheath = yf.copy(), yf.copy(), np.zeros(n, bool)
        jit = np.sin(x * 0.045 + f.t * 7 + wr.random(n) * 6) * 7 * sheath
        y = y + jit
        yp = yp + jit
        sy, syp = pcy + y, pcy + yp
        xp = x - spd * 0.05
        alive = np.ones(n, bool)
        if kcol > 0:  # no shield: anything aimed at the planet hits it
            hitx = pcx - np.sqrt(np.clip(R ** 2 - y ** 2, 0, None))
            inside = np.abs(y) < R * 0.98
            alive = ~(inside & (x > hitx))
            splash = inside & (x > hitx) & (x < hitx + 90)
            dots(f, hitx[splash], sy[splash], 3, 0.9 * (1 - (x[splash] - hitx[splash]) / 90) * kcol, "#fff0c0", add=True)
            for k in range(5):  # the dayside glows where the wind now slams into the bare atmosphere
                ang = math.pi + (k - 2) * 0.45
                soft_light(f, pcx + math.cos(ang) * R, pcy + math.sin(ang) * R, R * 0.7,
                           "#ffb070", 0.3 * kcol * (0.6 + 0.4 * math.sin(f.t * 9 + k * 2)))
            xp = np.where(inside & (xp > hitx), hitx, xp)
        normal = alive & ~sheath
        heat = alive & sheath
        _lines(f, xp[normal], syp[normal], x[normal], sy[normal], "#ffe2a0", 0.55, 2.0)
        _lines(f, xp[heat], syp[heat], x[heat], sy[heat], "#ff9a6a", 0.85, 2.4)
        # ---- bow shock and magnetopause
        if b > 1:
            Xs = -b_s / math.pi + np.geomspace(0.2, W - xs_src + 300 + b_s / 3, 140)
            Ys = _flow_y(Xs, np.zeros(len(Xs)), b_s, tl * 1.3, iters=60)
            Xm = -b / math.pi + np.geomspace(0.2, W - xs_src + 300 + b / 3, 140)
            Ym = _flow_y(Xm, np.zeros(len(Xm)), b, tl, iters=60)

            for sgn in (1, -1):
                bs = _poly_path(xs_src + np.concatenate([[Xs[0] - 0.5], Xs]), pcy + sgn * np.concatenate([[0], Ys]))
                aa = (0.25 + 0.75 * ks) * (1 - kcol)
                f.c.drawPath(bs, paint(GOLD, 0.35 * aa * (1 + 0.5 * pulse), stroke=18, blur=10, add=True))
                tp = paint("#fff0d0", 0.55 * aa, stroke=3)
                tp.setPathEffect(skia.DiscretePathEffect.Make(10, 3.5, 7 + sgn))
                f.c.drawPath(bs, tp)
                mp = _poly_path(xs_src + np.concatenate([[Xm[0] - 0.5], Xm]), pcy + sgn * np.concatenate([[0], Ym]))
                f.c.drawPath(mp, paint(c_, (0.25 + 0.35 * ks) * (1 - kcol), stroke=2.5))
            j8 = int(np.searchsorted(Xs, -b_s / math.pi + 60))
            labels["shock"] = _scr(f, xs_src + Xs[j8], pcy - Ys[j8])

        # ---- dipole field lines, squashed on the dayside and stretched into a tail
        fa = (0.55 + 0.25 * ks + 0.2 * pulse) * (1 - kcol)
        shrink = 1 - 0.6 * kcol
        if fa > 0.01:
            for L in (1.45, 1.9, 2.5, 3.2):
                for side in (-1, 1):
                    th0 = math.asin(math.sqrt(1 / L))
                    th = np.linspace(th0, math.pi - th0, 60)
                    r = L * R * np.sin(th) ** 2 * shrink
                    lx = side * r * np.sin(th)
                    ly = -r * np.cos(th)
                    if side < 0:
                        lx = lx / (1 + 0.12 * r / R)
                    else:
                        lx = lx * (1 + 0.2 * (r / R) ** 1.4)
                    pth = _poly_path(pcx + lx, pcy + ly)
                    f.c.drawPath(pth, paint(c_, 0.16 * fa, stroke=8, blur=5, add=True))
                    dp = paint(c_, 0.7 * fa, stroke=2)
                    dp.setPathEffect(skia.DashPathEffect.Make([3, 16], -f.t * 40 * side))
                    f.c.drawPath(pth, paint(c_, 0.35 * fa, stroke=1.5))
                    f.c.drawPath(pth, dp)
                    if L == 1.9 and side == 1:
                        labels["field"] = _scr(f, pcx + lx[44], pcy + ly[44])
            for i, lat in enumerate((0.3, 0.42, 0.55)):  # open tail lines from the polar caps
                for sgn in (-1, 1):
                    pth = skia.Path()
                    sx0, sy0 = pcx + R * math.sin(lat), pcy + sgn * R * math.cos(lat)
                    pth.moveTo(sx0, sy0)
                    hy = (1.25 + 0.42 * i) * R * shrink
                    pth.cubicTo(sx0 + R * 0.6, pcy + sgn * (hy + R * 0.9), pcx + R * 3, pcy + sgn * hy,
                                W + 300, pcy + sgn * hy * 0.9)
                    f.c.drawPath(pth, paint(c_, 0.14 * fa, stroke=8, blur=5, add=True))
                    f.c.drawPath(pth, paint(c_, 0.4 * fa, stroke=1.5))
            labels["tail"] = _scr(f, pcx + R * 4.6, pcy - 1.25 * R * shrink * 0.95)
        # ---- the planet and its air
        atm = 1 - 0.75 * f.prog(t3 + 0.5, 3.0) if collapse else 1.0
        halo(f, pcx, pcy, R, R * 1.35, "#9fe6ff", 0.35 * atm)
        body(f, kind, pcx, pcy, R, light=(-0.85, -0.15, 0.5), seed_key="ms_planet")
        if kcol > 0:  # the atmosphere being stripped off downwind
            sr = f.rng("ms_strip")
            ns = 600
            phi = (sr.random(ns) - 0.5) * math.pi * 1.4
            life = (sr.random(ns) + f.t * 0.45) % 1.0
            ox = pcx + R * np.cos(phi) * 0.9
            oy = pcy + R * np.sin(phi)
            px = ox + 700 * life ** 1.3
            py = oy + np.sin(phi) * 160 * life + np.sin(life * 9 + phi * 4) * 12
            dots(f, px, py, 1.2 + 1.5 * sr.random(ns), (1 - life) * 0.75 * kcol, "#bfeaff", add=True)
            labels["strip"] = _scr(f, pcx + R * 2.2, pcy - R * 0.5)
        # ---- auroras: particles funnel down the field into the poles
        if ka > 0 and kcol < 1:
            ak = ka * (1 - kcol)
            cr = f.rng("ms_cusp")
            nc = 170
            cu = (cr.random(nc) + f.t * 0.55) % 1.0
            sg = np.where(cr.random(nc) < 0.5, -1, 1)
            # along a bezier from the dayside cusp to the polar oval
            p0x, p0y = pcx - 2.1 * R, 1.55 * R
            p1x, p1y = pcx - 1.2 * R, 1.6 * R
            p2x, p2y = pcx - 0.4 * R, 1.25 * R
            p3x, p3y = pcx - 0.05 * R, 1.0 * R
            q = 1 - cu
            bx = q ** 3 * p0x + 3 * q * q * cu * p1x + 3 * q * cu * cu * p2x + cu ** 3 * p3x
            by = q ** 3 * p0y + 3 * q * q * cu * p1y + 3 * q * cu * cu * p2y + cu ** 3 * p3y
            dots(f, bx, pcy - sg * by, 2.2, ak * np.sin(cu * math.pi) * 0.8, "#7dffa8", add=True)
            for sgn in (-1, 1):
                oy = pcy + sgn * R * 0.9
                soft_light(f, pcx, oy + sgn * R * 0.25, R * 1.5, "#3dff7a", 0.28 * ak * (1 + 0.5 * pulse))
                soft_light(f, pcx, oy + sgn * R * 0.6, R * 1.1, "#ff4fc8", 0.14 * ak)
                ar = f.rng(f"ms_aur{sgn}")
                na = 38
                ph = np.linspace(0, math.pi, na) + (ar.random(na) - 0.5) * 0.04
                axp = pcx + np.cos(ph) * R * 0.55
                ayp = oy + np.sin(ph) * R * 0.1 * (-sgn)
                flick = 0.55 + 0.45 * np.sin(f.t * (6 + 5 * ar.random(na)) + ar.random(na) * 6)
                hgt = R * (0.35 + 0.45 * ar.random(na)) * flick * ak
                fr = np.sin(ph) > -1  # all strands; the back ones are dimmer below
                _lines(f, axp, ayp, axp, ayp + sgn * hgt * 0.6, "#3dff7a", 0.1 * ak, 9.0)
                _lines(f, axp, ayp, axp, ayp + sgn * hgt * 0.6, "#5dff8c", 0.32 * ak, 2.0)
                _lines(f, axp, ayp + sgn * hgt * 0.6, axp, ayp + sgn * hgt, "#ff4fc8", 0.22 * ak, 2.0)
                c_oval = f.c
                c_oval.save()
                c_oval.translate(pcx, oy)
                c_oval.scale(1, 0.2)
                ring(f, 0, 0, R * 0.55, R * 0.12, "#3dff7a", 0.45 * ak * (0.8 + 0.4 * pulse))
                c_oval.restore()
            labels["aurora"] = _scr(f, pcx, pcy - R * 1.12)
        labels["planet"] = _scr(f, pcx + R * 0.7, pcy + R * 0.7)
        labels["wind"] = _scr(f, 300, pcy + 100)

    scr = _screen(f)
    scr.__enter__()
    _callout(f, "SOLAR WIND", *labels["wind"], 60, -200, 0.3, color=GOLD)
    if "field" in labels:
        _callout(f, "MAGNETIC FIELD", *labels["field"], 140, 200, 0.9, color=c_, a=1 - kcol)
    if "shock" in labels:
        _callout(f, "BOW SHOCK", *labels["shock"], -170, -110, t1 + 0.3, color=GOLD, a=1 - kcol)
    if "tail" in labels:
        _callout(f, "MAGNETOTAIL", *labels["tail"], 90, -140, t1 + 1.1, color=c_, a=1 - kcol)
    if "aurora" in labels:
        _callout(f, "AURORA", *labels["aurora"], 190, -150, t2 + 0.4, color=GREEN, a=1 - kcol)
    if "strip" in labels:
        _callout(f, "AIR STRIPPED AWAY", *labels["strip"], 160, -170, t3 + 1.0, color=RED)

    if p("hud", True):
        rows = [("SOLAR WIND", f"{400 + 25 * math.sin(f.t * 1.3):,.0f} km/s"),
                ("FIELD", f"{100 * (1 - kcol):.0f}%", RED if kcol > 0 else GREEN),
                ("AURORA", "active" if ka > 0 and kcol < 0.5 else "quiet", GREEN if ka > 0 and kcol < 0.5 else DIM)]
        if collapse:
            rows.append(("ATMOSPHERE", f"{100 - 60 * f.prog(t3 + 0.5, 3.0):.0f}%", RED if f.t > t3 else INK))
        _panel(f, "FIELD MONITOR", rows, c_, w=500)
        names, times = ["SOLAR WIND", "BOW SHOCK", "AURORA"], [0, t1, t2]
        if collapse:
            names.append("COLLAPSE")
            times.append(t3)
        _stages(f, names, times, c_)
        _note(f)
    if p("title"):
        slam_text(f, p("title"), 960, 810, (t3 if collapse else t2) + 0.15, size=130, glow_color=RED if collapse else c_)
    scr.__exit__(None, None, None)
    flash(f, t2, dur=0.45, color="#c8ffe0", peak=0.3)
    if collapse:
        flash(f, t3, dur=0.5, color="#ffffff", peak=0.6)


# ---------------------------------------------------------------- 4. solar flare and CME

@template("solar_flare", sfx=lambda p: _cues(
    Sfx("rumble", "start", dur=6, gain_db=-8),
    Sfx("riser", p("snap_at"), offset=-1.5, dur=1.5, gain_db=-4) if p("snap_at") else None,
    Sfx("impact", p("snap_at")) if p("snap_at") else Sfx("impact", 2.2, gain_db=-4),
    Sfx("whoosh", p("cme_at"), gain_db=-2) if p("cme_at") else None,
    Sfx("808", p("arrive_at")) if p("arrive_at") else Sfx("808", "end", offset=-0.8, gain_db=-4)))
def solar_flare(f, p):
    """A solar flare and its CME, as a 4-beat storyboard. A close-up of the Sun's boiling granulated surface,
    sunspots and glowing magnetic loops; the main loop twists and rises under stress; it snaps (reconnection):
    a blinding flare, flare ribbons and a wave across the surface, with a plasma blob torn off; then the camera
    pulls out to a wide shot where the CME bubble balloons across space to a small planet, with distance and
    hours counting up, and hits it (its magnetic shield flares).
    params: loop_at (word the loop starts twisting), snap_at (word it snaps: the flare), cme_at (word for the
    wide shot / CME launch), arrive_at (word the CME hits the planet), planet (body kind, default earth),
    km (distance, default 150000000), hours (travel time, default 40), title (slam on the flare, default
    "SOLAR FLARE", "" for none), hit_title (slam on arrival, default "DIRECT HIT", "" for none), color, hud"""
    c_ = accent(f, p, default=["gold", "orange", "red", "pink"])
    t0 = when(f, p("loop_at"), 0.12)
    t1 = max(when(f, p("snap_at"), 0.36), t0 + 0.3)
    t2 = max(when(f, p("cme_at"), 0.55), t1 + 0.3)
    t3 = max(when(f, p("arrive_at"), 0.86), t2 + 0.5)
    pulse = f.beat_pulse()
    s1 = f.t - t1
    gtex = _granules(stable_seed(f.seed, f.scene_id, "sf_gran"))
    gtex2 = _granules(stable_seed(f.seed, f.scene_id, "sf_gran2"))
    rng = f.rng("sf_layout")
    km_total = float(p("km", 150_000_000))
    hours = float(p("hours", 40))

    if f.t < t2:
        # ================= close-up of the surface
        scx, scy, SR = 960, 2240, 1580
        top = scy - SR

        def ysurf(x):
            return scy - math.sqrt(max(SR ** 2 - (x - scx) ** 2, 0))

        gradient_bg(f, "#12060a", "#050206")
        starfield(f, n=140, drift=(0, 0), key="sf_stars", alpha=0.5)
        shake = 20 * math.exp(-s1 * 3) if s1 > 0 else 2 * f.prog(t0, t1 - t0)
        zoom = 1.0 + 0.06 * ease_in_out(f.t / t2) + (0.05 * math.exp(-s1 * 2) if s1 > 0 else 0)
        labels = {}
        with camera(f, 960 + rand(f, "sf_pan", -30, 30) * f.p, 540, zoom=zoom, shake=shake):
            halo(f, scx, scy, SR * 0.99, SR + 420, "#ff9a50", 0.35 + 0.1 * pulse)
            soft_light(f, 960, top, 900, "#ff7a3a", 0.18)
            c = f.c
            c.save()
            clip = skia.Path()
            clip.addCircle(scx, scy, SR)
            c.clipPath(clip, doAntiAlias=True)
            c.drawPaint(paint("#c0400c"))
            dx = (f.t * 9) % 60
            boil = 0.5 + 0.5 * math.sin(f.t * 0.9)
            c.drawImageRect(gtex, skia.Rect.MakeXYWH(-160 - dx, top - 10, 2300, 627), skia.SamplingOptions(skia.FilterMode.kLinear))
            c.drawImageRect(gtex2, skia.Rect.MakeXYWH(-130 - dx * 0.7, top - 14, 2300, 627),
                            skia.SamplingOptions(skia.FilterMode.kLinear), skia.Paint(Alphaf=0.5 * boil))
            limb = skia.GradientShader.MakeRadial(skia.Point(scx, scy), SR, [col("#000000", 0), col("#000000", 0),
                                                                         col("#5a1000", 0.45), col("#2a0500", 0.8)],
                                                  [0, 0.9, 0.975, 1.0])
            c.drawCircle(scx, scy, SR, skia.Paint(AntiAlias=True, Shader=limb))
            # sunspots under the loop footpoints
            fx1 = 960 - rand(f, "sf_span", 160, 210)
            fx2 = 960 + rand(f, "sf_span2", 160, 210)
            for fx in (fx1, fx2):
                fy = ysurf(fx) + 32
                for rr_, cc, aa in ((60, "#5a1a00", 0.7), (38, "#2a0800", 0.9), (20, "#100200", 1.0)):
                    c.save()
                    c.translate(fx, fy)
                    c.scale(1, 0.32)
                    c.drawCircle(0, 0, rr_, paint(cc, aa, blur=6))
                    c.restore()
            if s1 > 0:  # flare ribbons and a wave rippling across the surface
                rib = math.exp(-s1 * 0.7)
                for fx in (fx1, fx2):
                    c.save()
                    c.translate(fx, ysurf(fx) + 30)
                    c.scale(1, 0.22)
                    soft_light(f, 0, 0, 170, "#fff4d0", 0.9 * rib)
                    c.restore()
                c.save()
                c.translate(960, ysurf(960) + 34)
                c.scale(1, 0.16)
                ring(f, 0, 0, 40 + 760 * s1, 40, "#fff0c0", 0.6 * clamp(1 - s1 / 2.4))
                c.restore()
            c.restore()
            # chromosphere rim and spicules along the limb
            ring(f, scx, scy, SR + 3, 9, "#ff5a3a", 0.7)
            sp = f.rng("sf_spic")
            nsp = 340
            phi = -math.pi / 2 + (sp.random(nsp) - 0.5) * 1.5
            ln = (8 + sp.random(nsp) * 22) * (0.7 + 0.3 * np.sin(f.t * 3 + sp.random(nsp) * 6))
            _lines(f, scx + np.cos(phi) * SR, scy + np.sin(phi) * SR, scx + np.cos(phi) * (SR + ln),
                   scy + np.sin(phi) * (SR + ln), "#ff7a5a", 0.5, 2.0)
            # magnetic loops
            def loop(x1, x2, h, colr, a, width, twist=0.0, strands=4, writhe=0.0, beads=True, key=0):
                y1, y2 = ysurf(x1) + 20, ysurf(x2) + 20
                central = None
                for k in range(strands):
                    o = (k - (strands - 1) / 2) * width * 0.9 + writhe * math.sin(f.t * 9 + k * 1.7)
                    pth = skia.Path()
                    pth.moveTo(x1 + o, y1)
                    hh = h + o * 0.6
                    pth.cubicTo(x1 + o + twist * (k - 1.5), y1 - 1.33 * hh, x2 + o - twist * (k - 1.5), y2 - 1.33 * hh, x2 + o, y2)
                    if k == strands // 2:
                        central = pth
                    c.drawPath(pth, paint(colr, 0.75 * a, stroke=width * 0.55, add=True))
                c.drawPath(central, paint(colr, 0.28 * a, stroke=width * 4, blur=width * 1.5, add=True))
                c.drawPath(central, paint("#fff6dc", 0.6 * a, stroke=width * 0.3, add=True))
                if beads:
                    m = skia.PathMeasure(central, False)
                    Lp = m.getLength()
                    for i in range(6):
                        uu = (i / 6 + f.t * 0.22 * (1 if key % 2 else -1)) % 1.0
                        pos = m.getPosTan(Lp * uu)
                        if pos:
                            soft_light(f, pos[0].x(), pos[0].y(), width * 2.2, "#fff0c0", 0.5 * a)
                return central

            for i in range(6):
                lx = rng.random() * 1700 + 110
                if abs(lx - 960) < 260:
                    lx += 520 if lx > 960 else -520
                spn = 90 + rng.random() * 200
                loop(lx - spn / 2, lx + spn / 2, 60 + rng.random() * 140, pick(f, f"sf_lc{i}", ["#ffb35a", "#ff8a3d", "#ffd27a"]),
                     0.55 + 0.25 * pulse, 7, strands=3, writhe=2, key=i)
            k_rise = f.prog(t0, max(t1 - t0, 0.4), ease=ease_in)
            h0 = 210
            if s1 < 0:
                h = h0 * (1 + 0.8 * k_rise)
                stress = 0.25 + 0.75 * k_rise
                cen = loop(fx1, fx2, h, c_, 0.8 + 0.3 * k_rise + 0.2 * pulse, 12, twist=40 * k_rise * math.sin(f.t * 3),
                           strands=5, writhe=2 + 9 * k_rise, key=9)
                ap = skia.PathMeasure(cen, False)
                labels["loop"] = _scr(f, *(lambda q: (q.x(), q.y()))(ap.getPosTan(ap.getLength() * 0.3)[0]))
            else:
                stress = 0.25
                post = loop(fx1 + 30, fx2 - 30, h0 * 0.5, "#fff0c0", 1.0 * (0.6 + 0.4 * math.exp(-s1)), 12, strands=6, writhe=1.5, key=9)
                # torn-off plasmoid racing upwards
                apex = ysurf(960) + 20 - 1.33 * h0 * 1.8 * 0.75
                py = apex - 220 * s1 - 380 * s1 ** 1.6
                prr = 50 + 160 * s1
                for k in range(3):
                    c.save()
                    c.translate(960 + 20 * math.sin(f.t * 2 + k), py)
                    c.rotate(k * 60 + f.t * 30)
                    c.scale(1, 0.55)
                    c.drawCircle(0, 0, prr, paint(c_, 0.55 * clamp(1.4 - s1 * 0.5), stroke=8, blur=4, add=True))
                    c.restore()
                soft_light(f, 960, py, prr * 1.6, c_, 0.4 * clamp(1.4 - s1 * 0.5))
                xpt_y = ysurf(960) + 20 - h0 * 1.2
                glow(f, 960, xpt_y, 40 * math.exp(-s1 * 1.2) + 8, "#ffffff", clamp(1.2 - s1 * 0.4))
                particles(f, 960, xpt_y, t1, n=260, speed=(200, 1100), life=(0.6, 2.2), size=(2, 5), color=GOLD, key="sf_burst")
                shockwave(f, 960, xpt_y, t1, speed=1100, life=1.6, color=c_, width=22)
                labels["flare"] = _scr(f, 960, xpt_y)
            labels["spot"] = _scr(f, fx2, ysurf(fx2) + 32)
        scr = _screen(f)
        scr.__enter__()
        _callout(f, "SUNSPOT", *labels["spot"], 230, 110, 0.4)
        if "loop" in labels:
            _callout(f, "MAGNETIC LOOP", *labels["loop"], -260, -120, 0.9, color=c_)
        if "flare" in labels:
            _callout(f, "FLARE", *labels["flare"], 250, -60, t1 + 0.5, color=GOLD)
        if p("hud", True):
            temp = "1 million °C" if s1 < 0 else f"{1 + 19 * clamp(s1 / 1.2):.0f} million °C"
            status = ("stable", GREEN) if f.t < t0 else (("twisting", GOLD) if s1 < 0 else ("FLARE", RED))
            _panel(f, "SOLAR MONITOR", [("MAGNETIC STRESS", f"{stress * 100:.0f}%", RED if stress > 0.8 else INK),
                                        ("CORONA TEMP", temp), ("STATUS", status[0], status[1])], c_, w=540)
        title = p("title", "SOLAR FLARE")
        if title:
            slam_text(f, title, 960, 330, t1 + 0.1, size=120, glow_color=c_)
        scr.__exit__(None, None, None)
        flash(f, t1, dur=0.6, color="#fff4dc", peak=0.9)
    else:
        # ================= wide shot: the CME crosses space to the planet
        s2 = f.t - t2
        s3 = f.t - t3
        k_in = f.prog(t2, 1.1, ease=ease_out)
        gradient_bg(f, "#060816", "#010207")
        nebula_glow(f, key="sf_neb", alpha=0.25)
        starfield(f, n=420, drift=(-5, 0), key="sf_wstars")
        sunx, suny, sunr = -150, 500, 400
        limb_x = sunx + sunr
        plx, ply, plr = 1650, 470, 48
        k = clamp(s2 / (t3 - t2)) if s3 < 0 else 1 + s3 * 0.12
        kk = 1 - (1 - min(k, 1)) ** 1.4 if k <= 1 else k
        d = (plx - 2.1 * plr - limb_x) * kk + 30
        zoom = lerp(2.0, 1.0, k_in) * (1 + 0.04 * ease_in_out(clamp(s2 / max(t3 - t2, 0.1))))
        shake = 18 * math.exp(-s3 * 3) if s3 > 0 else 0
        labels = {}
        with camera(f, lerp(limb_x + 60, 960, k_in), 500, zoom=zoom, shake=shake):
            _textured_sun(f, sunx, suny, sunr, seed_key="sf_sun", pulse=pulse)
            # flare afterglow on the limb
            soft_light(f, limb_x - 10, suny, 160, "#fff4d0", 0.6 * math.exp(-s2 * 0.6))
            # the CME: a ballooning bubble of magnetised plasma, its legs still rooted in the Sun
            crr = min(d * 0.4, 330)
            ccx, ccy = limb_x + d - crr, suny - 10
            fade_ = clamp(1.25 - 0.35 * kk)
            leg_a = clamp(1.3 - kk)
            cr = f.rng("sf_cme")
            fill = skia.GradientShader.MakeRadial(skia.Point(ccx + crr * 0.15, ccy), crr,
                                                  [col(c_, 0.04 * fade_), col(c_, 0.12 * fade_), col(c_, 0.3 * fade_),
                                                   col(c_, 0)], [0, 0.6, 0.93, 1])
            f.c.drawCircle(ccx, ccy, crr, skia.Paint(AntiAlias=True, Shader=fill, BlendMode=skia.BlendMode.kPlus))
            for sgn in (-1, 1):
                leg = skia.Path()
                leg.moveTo(limb_x - 10, suny + sgn * 55)
                ex, ey = ccx + math.cos(sgn * 2.3) * crr, ccy + math.sin(sgn * 2.3) * crr
                leg.cubicTo(limb_x + d * 0.1, suny + sgn * 70, ex - crr * 0.15, ey, ex, ey)
                f.c.drawPath(leg, paint(c_, 0.35 * leg_a, stroke=14, blur=8, add=True))
                f.c.drawPath(leg, paint("#ffe0b0", 0.4 * leg_a, stroke=3, add=True))
            for i in range(14):  # twisted flux-rope strands inside the bubble
                fr = 0.45 + 0.5 * cr.random()
                a0_, ext = (cr.random() - 0.5) * 1.4, 0.5 + cr.random() * 1.0
                pth = skia.Path()
                pth.addArc(skia.Rect.MakeLTRB(ccx - crr * fr, ccy - crr * fr, ccx + crr * fr, ccy + crr * fr),
                           math.degrees(a0_ - ext / 2 + 0.2 * math.sin(f.t + i)), math.degrees(ext))
                f.c.drawPath(pth, paint(c_, 0.28 * fade_, stroke=2 + 4 * cr.random(), blur=2, add=True))
            nsh = 2200
            phi = (cr.random(nsh) - 0.5) * 2.1
            thick = 1 - cr.random(nsh) ** 2 * 0.2
            wob = 1 + 0.035 * np.sin(phi * 9 + f.t * 2) + 0.02 * np.sin(phi * 23 - f.t * 3)
            rr = crr * thick * wob
            shx, shy = ccx + np.cos(phi) * rr, ccy + np.sin(phi) * rr
            bright = np.clip(np.cos(phi), 0, 1) ** 0.6 * (0.35 + 0.65 * cr.random(nsh)) * fade_
            dots(f, shx, shy, 1.0 + 1.3 * kk, bright, mix(c_, "#ffffff", 0.35), add=True)
            front = skia.Path()
            front.addArc(skia.Rect.MakeLTRB(ccx - crr, ccy - crr, ccx + crr, ccy + crr), -55, 110)
            f.c.drawPath(front, paint(c_, 0.35 * fade_, stroke=26, blur=14, add=True))
            f.c.drawPath(front, paint("#fff0d0", 0.6 * fade_, stroke=4, blur=2, add=True))
            labels["cme"] = _scr(f, ccx + crr * math.cos(0.55), ccy + crr * math.sin(0.55))
            # the planet and its magnetic bubble
            hitk = math.exp(-s3 * 1.2) if s3 > 0 else 0
            squash = 1 - 0.4 * clamp(s3 * 2) if s3 > 0 else 1
            for sgn in (-1, 1):
                arc = skia.Path()
                arc.moveTo(plx + 30, ply + sgn * 170)
                arc.quadTo(plx - 2.6 * plr * squash, ply + sgn * 40, plx - 2.0 * plr * squash, ply)
                f.c.drawPath(arc, paint(CYAN, 0.35 + 0.6 * hitk, stroke=3 + 6 * hitk, add=True))
            body(f, p("planet", "earth"), plx, ply, plr, light=(-0.9, -0.1, 0.45), seed_key="sf_planet")
            if s3 > 0:
                for sgn in (-1, 1):
                    soft_light(f, plx, ply + sgn * plr * 0.95, plr * 0.8, "#6dff9c", 0.7 * hitk + 0.2)
                shockwave(f, plx - plr, ply, t3, speed=600, life=1.4, color=CYAN, width=14)
            labels["planet"] = _scr(f, plx, ply - plr)
            labels["sun"] = _scr(f, limb_x - 60, suny - 240)
        scr = _screen(f)
        scr.__enter__()
        _callout(f, "SUN", *labels["sun"], 120, -100, t2 + 0.3, color=GOLD)
        _callout(f, "CME", *labels["cme"], -150, 150, t2 + 0.7, color=c_)
        name = (p("planet", "earth") or "planet").replace("_", " ").upper()
        _callout(f, name, *labels["planet"], -150, -150, t2 + 0.5)
        if p("hud", True):
            fr_ = min(kk, 1)
            el = hours * clamp(s2 / (t3 - t2)) if s3 < 0 else hours
            _panel(f, "CME TRACKER", [("DISTANCE", f"{km_total * fr_:,.0f} km"), ("ELAPSED", f"{el:.0f} hours"),
                                      ("SPEED", f"{km_total / max(hours, 0.1) / 3600:,.0f} km/s"),
                                      ("STATUS", "IMPACT" if s3 > 0 else "en route", RED if s3 > 0 else GOLD)], c_, w=560)
            _note(f)
        hit = p("hit_title", "DIRECT HIT")
        if hit:
            slam_text(f, hit, 960, 800, t3 + 0.1, size=130, glow_color=c_)
        scr.__exit__(None, None, None)
        flash(f, t2, dur=0.35, color="#fff4dc", peak=0.8)
        flash(f, t3, dur=0.4, color="#dff6ff", peak=0.45)
    if p("hud", True):
        with _screen(f):
            _stages(f, ["LOOPS", "FLARE", "CME", "IMPACT"], [0, t1, t2, t3], c_)


# ---------------------------------------------------------------- 5. accretion disk

_BH_PALETTES = {
    "gold": [(0, "#2a0600"), (0.25, "#9a2a06"), (0.5, "#ef7a1c"), (0.75, "#ffc867"), (0.92, "#fff1cf"), (1, "#ffffff")],
    "ice": [(0, "#020a2a"), (0.25, "#14348a"), (0.5, "#3a8ae0"), (0.75, "#9fdcff"), (0.92, "#e8f8ff"), (1, "#ffffff")],
    "pink": [(0, "#1a0222"), (0.25, "#6a1060"), (0.5, "#d0408a"), (0.75, "#ffa0c8"), (0.92, "#ffe8f4"), (1, "#ffffff")],
    "ember": [(0, "#200200"), (0.25, "#801400"), (0.5, "#e04a10"), (0.75, "#ff9a40"), (0.92, "#ffe0b0"), (1, "#ffffff")],
}


@lru_cache(maxsize=8)
def _bh_geom(w, h, x0, y0, sc, cx, cy, r, tilt, rin, rout):
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    sx = x0 + (xs + 0.5) / sc - cx
    sy = y0 + (ys + 0.5) / sc - cy
    X, Y = sx, sy / tilt
    rad = np.sqrt(X ** 2 + Y ** 2)
    ang = np.arctan2(Y, X)
    u = (rad - rin) / (rout - rin)
    disk = (u >= 0) & (u <= 1)
    inner = np.clip((rad - rin) / (rin * 0.12), 0, 1)
    outer = np.clip((1 - u) / 0.35, 0, 1) ** 1.5
    base = np.where(disk, (rad / rin) ** -0.7 * inner * outer, 0).astype(np.float32)

    heat = np.clip((rad / rin) ** -0.85, 0, 1).astype(np.float32)
    # the lensed image of the far side of the disk, wrapped over (and under) the shadow
    rr = np.sqrt(sx ** 2 + sy ** 2) / r
    phi = np.arctan2(sy, sx)
    top = sy < 0
    tpar = np.clip(0.5 - sy / (0.7 * r), 0, 1)  # 1 over the top, 0 underneath, blended at the sides
    lo, hi = 1.04 + 0.03 * tpar, 1.34 + 0.41 * tpar
    lu = (rr - lo) / (hi - lo)
    lens_m = (lu >= 0) & (lu <= 1)
    lrad = rin + np.clip(lu, 0, 1) * (rout - rin) * 0.55
    lang = np.where(top, phi, -phi)
    prof = np.clip(np.sin(np.clip(lu, 0, 1) * math.pi), 0, 1) ** 0.6
    lw = np.where(lens_m, (0.5 + 0.5 * tpar) * prof, 0) * (lrad / rin) ** -0.9
    return dict(rad=rad, ang=ang, u=np.clip(u, 0, 1), base=base, heat=heat, back=(sy < 0),
                lrad=lrad, lang=lang, lu=np.clip(lu, 0, 1), lw=lw.astype(np.float32), lheat=np.clip((lrad / rin) ** -0.85, 0, 1))


@lru_cache(maxsize=4)
def _bh_tex(seed):
    rng = np.random.default_rng(seed)
    t = fractal_noise(1024, 160, rng, octaves=6, base=5, stretch=9)
    return ((t - t.min()) / (np.ptp(t) + 1e-6)).astype(np.float32)


@template("accretion_disk", sfx=lambda p: _cues(
    Sfx("rumble", "start", dur=6, gain_db=-6),
    Sfx("shimmer", p("jets_at")) if p("jets_at") else Sfx("shimmer", 0.6, gain_db=-6),
    Sfx("whoosh", p("stream_at"), gain_db=-4) if p("stream_at") else None,
    Sfx("reverse", p("flare_at"), offset=-1.2, dur=1.2) if p("flare_at") else None,
    Sfx("impact", p("flare_at") or "end", offset=0 if p("flare_at") else -1.4)))
def accretion_disk(f, p):
    """A feeding black hole up close, as a 4-beat storyboard: a white-hot accretion disk whirls round the
    shadow (Doppler beaming makes the side coming towards us brighter and bluer, and gravity bends the far side
    of the disk up over the top), with a thin photon ring; the relativistic jets blast out of the poles; streams
    of gas spiral in from outside; then a bright clump falls through the inner disk and the payoff hits: an
    X-ray flare, a wave through the disk and surging jets. HUD counts the clump's speed as a fraction of light
    speed and the brightness.
    params: jets_at (word the jets surge on), stream_at (word the gas streams fall in), flare_at (word the clump
    falls in and flares, the payoff), title (slam on the flare, default "X-RAY FLARE", "" for none),
    size (shadow radius, default 95), palette (gold|ice|pink|ember), tilt (0.18-0.35), color, hud"""
    c_ = accent(f, p, default=["gold", "orange", "pink", "cyan"])
    palname = p("palette") or pick(f, "bh_pal", ["gold", "gold", "ice", "pink", "ember"])
    pal = _BH_PALETTES.get(palname, _BH_PALETTES["gold"])
    t1 = when(f, p("jets_at"), 0.18)
    t2 = when(f, p("stream_at"), 0.4)
    t3 = when(f, p("flare_at"), 0.74)
    kj = f.prog(t1, 0.9, ease=ease_out)
    kst = f.prog(t2, 1.5)
    s3 = f.t - t3
    pulse = f.beat_pulse()
    cx, cy = 960, 470
    r = float(p("size", 100))

    tilt = float(p("tilt") or round(rand(f, "bh_tilt", 0.2, 0.3), 3))
    rin, rout = 1.25 * r, 6.4 * r
    dirn = 1 if pick(f, "bh_dir", [0, 1]) else -1
    w0 = 1.4

    def omega(rad):
        return w0 * (rin / rad) ** 1.5

    # background, with stars pushed outward around the hole by lensing
    gradient_bg(f, "#05040c", "#000000")
    nebula_glow(f, key="bh_neb", alpha=0.22)
    sr = f.rng("bh_stars")
    ns = 520
    sxs, sys_ = sr.random(ns) * W - cx, sr.random(ns) * H - cy
    d = np.hypot(sxs, sys_) + 1e-3
    thE = 1.7 * r
    d2 = (d + np.sqrt(d ** 2 + 4 * thE ** 2)) / 2
    bright = 0.25 + 0.75 * sr.random(ns) ** 2
    dots(f, cx + sxs / d * d2, cy + sys_ / d * d2, 0.6 + 1.6 * sr.random(ns) ** 2,
         bright * (0.75 + 0.25 * np.sin(f.t * 2 + sr.random(ns) * 6)), INK)

    zoom = 1.0 + 0.12 * ease_in_out(f.p) + (0.05 * math.exp(-s3 * 2) if s3 > 0 else 0)
    shake = 16 * math.exp(-s3 * 2.5) if s3 > 0 else 0
    labels = {}
    # the clump: spirals in from the outer disk and is gone at the flare
    tc0 = max(t3 - 2.6, t2 * 0.5)
    kcl = clamp((f.t - tc0) / max(t3 - tc0, 0.1))
    with camera(f, cx, cy, zoom=zoom, rotate=lerp(-1.5, 1.5, f.p), shake=shake):
        sc = 0.5
        x0, y0 = cx - rout - 8, cy - 1.85 * r - 10
        wpx = int((2 * rout + 16) * sc)
        hpx = int((max(rout * tilt, 1.4 * r) + 1.85 * r + 20) * sc)
        g = _bh_geom(wpx, hpx, x0, y0, sc, cx, cy, r, tilt, rin, rout)
        tex = _bh_tex(stable_seed(f.seed, f.scene_id, "bh_tex"))
        na, nr = tex.shape[1], tex.shape[0]
        flare_boost = 1 + (3.5 * math.exp(-s3 * 1.1) if s3 > 0 else 0)

        def shade(rad, ang, u, base, heat):
            ri = (u * (nr - 1)).astype(np.int32)
            ai = (((ang - dirn * omega(rad) * f.t) / TAU) * na).astype(np.int32) % na
            nz = tex[ri, ai]
            D = 1 + 0.3 * dirn * np.cos(ang)
            I = base * (0.35 + 1.4 * nz ** 2) * D ** 2.2 * 1.6
            boost = 1 + (flare_boost - 1) * np.exp(-((rad - rin) / (rin * 0.8)) ** 2)
            if s3 > 0:
                wave = 1.4 * math.exp(-s3 * 0.9) * np.exp(-((rad - (rin + 420 * s3)) / 28) ** 2)
                boost = boost + wave
            I = I * boost * (1 + 0.15 * pulse)
            hc = np.clip(heat * D ** 0.7 * (0.85 + 0.3 * nz) + 0.1 * (boost - 1), 0, 1)
            return ramp(hc, pal) * (1 - np.exp(-1.5 * I))[..., None] * 1.15

        planar = shade(g["rad"], g["ang"], g["u"], g["base"], g["heat"])
        lensed = shade(g["lrad"], g["lang"], g["lu"], g["lw"], g["lheat"])
        backm = g["back"][..., None]
        imgA = np.clip(lensed + planar * backm, 0, 1)
        imgB = np.clip(planar * ~backm, 0, 1)

        def to_img(a):
            rgba = np.empty(a.shape[:2] + (4,), np.uint8)
            rgba[..., :3] = (a * 255).astype(np.uint8)
            rgba[..., 3] = (a.max(axis=-1) * 255).astype(np.uint8)
            return skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)

        dst = skia.Rect.MakeXYWH(x0, y0, wpx / sc, hpx / sc)
        addp = skia.Paint(BlendMode=skia.BlendMode.kPlus)
        samp = skia.SamplingOptions(skia.FilterMode.kLinear)
        soft_light(f, cx, cy, rout * 1.2, pal[3][1], 0.12 * flare_boost ** 0.5)
        # in-falling streams of gas, spiralling in from outside
        gs = f.rng("bh_gas")
        ng = 900
        lane = (gs.random(ng) < 0.5).astype(float)
        uu = (gs.random(ng) + f.t * 0.12) % 1.0
        srad = rout * (2.0 - 1.08 * uu) + (gs.random(ng) - 0.5) * 120 * (1 - uu) ** 1.5
        sang = rand(f, "bh_gas0", 0, TAU) + lane * math.pi + dirn * (1.5 * uu + f.t * 0.15) + (gs.random(ng) - 0.5) * 0.12
        for li in range(2):
            for q in (0.35, 0.6, 0.85):
                qa = rand(f, "bh_gas0", 0, TAU) + li * math.pi + dirn * (1.5 * q + f.t * 0.15)
                qr = rout * (2.0 - 1.08 * q)
                soft_light(f, cx + math.cos(qa) * qr, cy + math.sin(qa) * qr * tilt, 70 + 60 * (1 - q), pal[3][1],
                           (0.06 + 0.12 * kst) * q)
        gx, gy = cx + np.cos(sang) * srad, cy + np.sin(sang) * srad * tilt
        ga = (0.25 + 0.6 * kst) * np.sin(uu * math.pi) * (0.5 + 0.5 * gs.random(ng))
        gfront = np.sin(sang) > 0
        gcol = pal[3][1]
        dots(f, gx[~gfront], gy[~gfront], 1.2 + 1.2 * kst, ga[~gfront], gcol, add=True)
        # the clump's path
        crad = lerp(rout * 0.85, rin * 0.95, ease_in(kcl))
        clump_on = 0 < kcl < 1 and f.t >= tc0
        cang_ = rand(f, "bh_c0", 0, TAU) + dirn * (f.t - tc0) * (0.8 + 2.6 * kcl ** 2)
        clx, cly = cx + math.cos(cang_) * crad, cy + math.sin(cang_) * crad * tilt

        def draw_clump():
            if not clump_on:
                return
            Dc = 1 + 0.42 * dirn * math.cos(cang_)
            pts = []
            for j in range(16):
                tt = f.t - j * 0.04
                kk = clamp((tt - tc0) / max(t3 - tc0, 0.1))
                rr_ = lerp(rout * 0.85, rin * 0.95, ease_in(kk))
                aa = rand(f, "bh_c0", 0, TAU) + dirn * (tt - tc0) * (0.8 + 2.6 * kk ** 2)
                pts.append((cx + math.cos(aa) * rr_, cy + math.sin(aa) * rr_ * tilt))
            trail(f, pts[::-1], "#fff0d0", width=5, a=0.6 * Dc)
            glow(f, clx, cly, 12 + 6 * kcl, "#fff4dc", clamp(0.6 * Dc ** 2))

        if clump_on and math.sin(cang_) <= 0:
            draw_clump()
        f.c.drawImageRect(to_img(imgA), dst, samp, addp)
        # lower jet (points away from us, so the near side of the disk passes in front of it)
        jet_len = (220 + 340 * kj) * (1 + (0.4 * math.exp(-s3 * 1.2) if s3 > 0 else 0))
        jet_a = (0.35 + 0.55 * kj) * (1 + 0.3 * pulse) * (1 + (1.5 * math.exp(-s3) if s3 > 0 else 0))
        jcol = "#a8c8ff" if palname != "ice" else "#e0b0ff"
        jr = f.rng("bh_jet")
        nk = 90
        ku, kv = jr.random(nk), jr.random(nk) - 0.5

        def jet(sgn, length):
            base_y = cy + sgn * r * 1.02
            tip_y = base_y + sgn * length
            pth = skia.Path()
            pth.moveTo(cx - 5, base_y)
            pth.lineTo(cx + 5, base_y)
            pth.lineTo(cx + 34, tip_y)
            pth.lineTo(cx - 34, tip_y)
            pth.close()
            sh = skia.GradientShader.MakeLinear([skia.Point(cx, base_y), skia.Point(cx, tip_y)],
                                                [col(jcol, 0.75 * clamp(jet_a)), col(jcol, 0.25 * clamp(jet_a)), col(jcol, 0)],
                                                [0, 0.5, 1])
            f.c.drawPath(pth, skia.Paint(AntiAlias=True, Shader=sh, BlendMode=skia.BlendMode.kPlus))
            f.c.drawLine(cx, base_y, cx, base_y + sgn * length * 0.8, paint("#ffffff", 0.5 * clamp(jet_a), stroke=3, blur=2, add=True))
            z = (ku + f.t * 1.1) % 1.0
            dots(f, cx + kv * (6 + 50 * z), base_y + sgn * z * length, 1.5 + 2.5 * (1 - z), (1 - z) * clamp(jet_a), "#e8f0ff", add=True)

        jet(1, min(jet_len * 0.45, 210))
        # shadow and photon ring
        f.c.drawCircle(cx, cy, r, paint("#000000", 1))
        ring(f, cx, cy, r * 1.03, 3.5, "#fff4e0", 0.95)
        ring(f, cx, cy, r * 1.09, 6, pal[3][1], 0.35)
        f.c.drawImageRect(to_img(imgB), dst, samp, addp)
        dots(f, gx[gfront], gy[gfront], 1.2 + 1.2 * kst, ga[gfront], gcol, add=True)
        if clump_on and math.sin(cang_) > 0:
            draw_clump()
        jet(-1, jet_len)
        if s3 > 0:
            f.c.save()
            f.c.translate(cx, cy)
            f.c.scale(1, tilt)
            ring(f, 0, 0, rin + 420 * s3, 26, "#ffffff", 0.7 * math.exp(-s3 * 0.9))
            f.c.restore()
            glow(f, cx, cy - r * 1.02, 30 * math.exp(-s3 * 1.5) + 6, "#ffffff", clamp(1 - s3 * 0.4))
        labels["hole"] = _scr(f, cx + r * 0.35, cy - r * 0.55)
        labels["ring"] = _scr(f, cx - r * 1.03 * math.cos(0.75), cy - r * 1.03 * math.sin(0.75))
        labels["disk"] = _scr(f, cx + rout * 0.62, cy + rout * 0.45 * tilt)
        labels["jet"] = _scr(f, cx, cy - r - jet_len * 0.55)
        labels["clump"] = _scr(f, clx, cly)
    scr = _screen(f)
    scr.__enter__()
    _callout(f, "EVENT HORIZON", *labels["hole"], 300, -150, 0.3)
    _callout(f, "PHOTON RING", *labels["ring"], -260, -120, 1.0, color=GOLD)
    _callout(f, "ACCRETION DISK", *labels["disk"], 60, 170, 1.6, color=pal[3][1])
    _callout(f, "JET", *labels["jet"], -180, -60, t1 + 0.4, color=jcol)
    if clump_on:
        _callout(f, "GAS CLUMP", *labels["clump"], 140, 150, tc0 + 0.3, color=INK)
    if p("hud", True):
        rs = r / 2.6  # the shadow is ~2.6 Schwarzschild radii across
        if clump_on:
            rr_s = max(crad / rs, 3.05)
            v = math.sqrt(1 / (2 * (rr_s - 1)))
            vtxt = f"{v:.2f} × light"
        else:
            vtxt = "—" if s3 < 0 else "swallowed"
        bright = flare_boost * (1 + 0.6 * kst + 0.4 * kj)
        _panel(f, "BLACK HOLE MONITOR", [("CLUMP SPEED", vtxt, GOLD if clump_on else INK),
                                         ("BRIGHTNESS", f"×{bright * 10:,.0f}", RED if s3 > 0 else INK),
                                         ("JETS", "surging" if kj > 0 else "steady", jcol)], c_, w=540)
        _stages(f, ["DISK", "JETS", "INFALL", "FLARE"], [0, t1, t2, t3], c_)
        _note(f)
    title = p("title", "X-RAY FLARE")
    if title:
        slam_text(f, title, 960, 810, t3 + 0.1, size=130, glow_color=c_)
    scr.__exit__(None, None, None)
    flash(f, t3, dur=0.55, color="#ffffff", peak=0.85)



# ---------------------------------------------------------------- 6. tidal locking

@template("tidal_lock", sfx=lambda p: _cues(
    Sfx("whoosh", 0.3, gain_db=-8),
    Sfx("pop", p("bulge_at"), gain_db=-3) if p("bulge_at") else None,
    Sfx("power_down", p("slow_at"), dur=2.0, gain_db=-4) if p("slow_at") else None,
    Sfx("808", p("lock_at") or "end", offset=0 if p("lock_at") else -1.4),
    Sfx("shimmer", p("lock_at") or "end", offset=0.1 if p("lock_at") else -1.3)))
def tidal_lock(f, p):
    """Why a moon ends up showing one face to its planet, as a 4-beat storyboard seen from above: the moon
    orbits and spins fast, a marker arrow on it sweeping round; the planet's gravity raises a tidal bulge on it,
    dragged ahead of the planet-moon line by the spin, and the pull on that bulge brakes the spin; the spin
    slows over millions of years (counter); then it locks, the marker points at the planet all the way round
    (ghost moons show it) and "TIDALLY LOCKED" slams in. HUD shows spins per orbit, bulge lag and time.
    params: bulge_at (word the tidal bulge appears), slow_at (word the spin starts slowing), lock_at (word it
    locks, the payoff), kind (planet, default earth), moon (moon kind, default moon), years (millions of
    years the spin-down takes, default 50), spin_ratio (spins per orbit at the start, default 4),
    title (slam on the lock, default "TIDALLY LOCKED", "" for none), color, hud"""
    c_ = accent(f, p, default=["cyan", "gold", "pink", "green", "orange"])
    t1 = when(f, p("bulge_at"), 0.2)
    t2 = max(when(f, p("slow_at"), 0.42), t1 + 0.2)
    t3 = max(when(f, p("lock_at"), 0.74), t2 + 0.5)
    pulse = f.beat_pulse()
    kb = f.prog(t1, 1.0)
    pcx, pcy, PR = 960, 480, 125
    A = 305.0
    rm = 56.0
    n_orb = TAU / 9.0
    ratio0 = float(p("spin_ratio", 4.0))
    e0 = n_orb * (ratio0 - 1)
    th = rand(f, "tl_th0", 0, TAU) + n_orb * f.t
    mx, my = pcx + math.cos(th) * A, pcy + math.sin(th) * A
    # spin angle: phi = th + pi + delta, delta -> 0 exactly as it locks
    if f.t >= t3:
        delta, g = 0.0, 0.0
    elif f.t < t2:
        delta, g = -e0 * ((t2 - f.t) + (t3 - t2) * 0.5), 1.0
    else:
        x = (f.t - t2) / (t3 - t2)
        xs = np.linspace(x, 1, 64)
        vals = 1 - _ease_np(xs)
        delta = -e0 * (t3 - t2) * float(np.sum((vals[1:] + vals[:-1]) * 0.5 * np.diff(xs)))
        g = 1 - ease_in_out(x)
    phi = th + math.pi + delta
    ratio = 1 + (ratio0 - 1) * g
    lag = math.radians(24) * g * kb  # exaggerated so you can see it
    s3 = f.t - t3

    gradient_bg(f, "#070a1a", "#02030a")
    nebula_glow(f, key="tl_neb", alpha=0.3)
    starfield(f, n=380, drift=(rand(f, "tl_dx", -4, 4), 0), key="tl_stars")
    # sunlight from the left
    soft_light(f, -300, pcy, 1100, GOLD, 0.3 + 0.08 * pulse)
    for i in range(7):
        yy = 120 + i * 120 + 30 * math.sin(f.t * 0.3 + i)
        f.c.drawLine(0, yy, W, yy + 20, paint(GOLD, 0.035, stroke=40, blur=20, add=True))

    zoom = 1.0 + 0.06 * ease_in_out(f.p) + 0.06 * f.prog(t3, 1.2)
    camx = pcx + 25 * math.sin(f.t * 0.2) + lerp(0, (mx - pcx) * 0.15, f.prog(t3, 1.2))
    camy = pcy + 15 * math.cos(f.t * 0.17) + lerp(0, (my - pcy) * 0.15, f.prog(t3, 1.2))
    shake = 8 * math.exp(-s3 * 3) if s3 > 0 else 0
    labels = {}
    with camera(f, camx, camy, zoom=zoom, shake=shake):
        c = f.c
        # orbit
        soft_light(f, pcx, pcy, A * 1.35, c_, 0.07)
        ring(f, pcx, pcy, A, 22, c_, 0.10 + 0.06 * pulse)
        orbit(f, pcx, pcy, A, color=c_, a=0.5, width=2)
        # the planet, with its own ocean bulge pointing (slightly ahead of) the moon
        if kb > 0:
            c.save()
            c.translate(pcx, pcy)
            c.rotate(math.degrees(th) + 8)
            c.scale(1.2, 1.0)
            soft_light(f, 0, 0, PR * 1.25, CYAN, 0.25 * kb)
            c.restore()
        body(f, p("kind", "earth"), pcx, pcy, PR, light=(-0.9, 0, 0.42), seed_key="tl_planet", rotation=f.t * 0.06)
        # line from the moon to the planet
        dl = paint(INK, 0.35, stroke=2)
        dl.setPathEffect(skia.DashPathEffect.Make([10, 10], -f.t * 20))
        ux, uy = (pcx - mx) / A, (pcy - my) / A
        c.drawLine(mx + ux * rm * 1.1, my + uy * rm * 1.1, pcx - ux * PR * 1.05, pcy - uy * PR * 1.05, dl)
        # ghost moons at the payoff: every position, same face in
        if s3 > 0:
            for k in range(1, 8):
                kk = ease_back(clamp((s3 - k * 0.1) / 0.35))
                if kk <= 0:
                    continue
                ga = th - k * TAU / 8
                gx, gy = pcx + math.cos(ga) * A, pcy + math.sin(ga) * A
                c.drawCircle(gx, gy, rm * 0.7 * kk, paint("#0a1020", 0.6))
                c.drawCircle(gx, gy, rm * 0.7 * kk, paint(GREEN, 0.55, stroke=2.5))
                d = ga + math.pi
                arrow(f, gx, gy, gx + math.cos(d) * rm * 1.3 * kk, gy + math.sin(d) * rm * 1.3 * kk,
                      p=paint(GREEN, 0.8, stroke=4), head=14)
        # tidal bulge on the moon, dragged ahead by the spin
        bang = th + math.pi + lag
        if kb > 0:
            c.save()
            c.translate(mx, my)
            c.rotate(math.degrees(bang))
            sc = 1 + 0.32 * kb
            c.scale(sc, 1 - 0.06 * kb)
            c.drawCircle(0, 0, rm * 1.08, paint(c_, 0.14 * kb))
            c.drawCircle(0, 0, rm * 1.08, paint(c_, 0.75 * kb, stroke=2.5 / sc))
            c.restore()
            bl = paint(c_, 0.8 * kb, stroke=2.5)
            bl.setPathEffect(skia.DashPathEffect.Make([8, 8], 0))
            ex, ey = math.cos(bang) * rm * 1.75, math.sin(bang) * rm * 1.75
            c.drawLine(mx - ex, my - ey, mx + ex, my + ey, bl)
            if lag > 0.02:  # the lag angle
                arc = skia.Path()
                base_deg = math.degrees(th + math.pi)
                arc.addArc(skia.Rect.MakeXYWH(mx - rm * 1.5, my - rm * 1.5, rm * 3, rm * 3), base_deg, math.degrees(lag))
                c.drawPath(arc, paint(GOLD, 0.9, stroke=3))
            labels["bulge"] = _scr(f, mx - math.cos(bang) * rm * 1.4, my - math.sin(bang) * rm * 1.4)
            labels["lag"] = _scr(f, mx + math.cos(th + math.pi + lag / 2) * rm * 1.55, my + math.sin(th + math.pi + lag / 2) * rm * 1.55)
        # the moon, spun about our line of sight (lighting stays from the left)
        c.save()
        c.translate(mx, my)
        c.rotate(math.degrees(phi))
        light = (-math.cos(phi), math.sin(phi), 0.35)
        body(f, p("moon", "moon"), 0, 0, rm, light=light, seed_key="tl_moon", rotation=0.0)
        mk = GREEN if s3 > 0 else c_
        c.drawCircle(rm * 0.58, 0, 8, paint(mk, 1))
        c.drawCircle(rm * 0.58, 0, 14 + 4 * pulse, paint(mk, 0.6, stroke=3))
        c.restore()
        # marker arrow: which way the marked face points
        mlen = rm * 2.0
        arrow(f, mx + math.cos(phi) * rm * 0.6, my + math.sin(phi) * rm * 0.6, mx + math.cos(phi) * mlen,
              my + math.sin(phi) * mlen, p=paint(mk, 1, stroke=5), head=18)
        soft_light(f, mx + math.cos(phi) * mlen, my + math.sin(phi) * mlen, 30, mk, 0.5)
        # spin arrow and, while braking, the tidal brake arrow against it
        spin_a = 0.6 * g + 0.15
        for sgn, colr, aa, rad_k in ((1, INK, spin_a, 1.5), (-1, RED, 0.9 * g * kb, 1.85)):
            if aa <= 0.03:
                continue
            arc = skia.Path()
            st = math.degrees(phi) + (40 if sgn > 0 else 200)
            arc.addArc(skia.Rect.MakeXYWH(mx - rm * rad_k, my - rm * rad_k, rm * 2 * rad_k, rm * 2 * rad_k), st, 70 * sgn)
            c.drawPath(arc, paint(colr, aa, stroke=4))
            ea = math.radians(st + 70 * sgn)
            hx, hy = mx + math.cos(ea) * rm * rad_k, my + math.sin(ea) * rm * rad_k
            tang = ea + sgn * math.pi / 2
            for side in (-1, 1):
                aa2 = tang + math.pi + side * 0.5
                c.drawLine(hx, hy, hx + math.cos(aa2) * 14, hy + math.sin(aa2) * 14, paint(colr, aa, stroke=4))
            if sgn < 0:
                labels["brake"] = _scr(f, hx, hy)
        if s3 > 0:
            ring(f, mx, my, rm * (1.2 + 1.8 * clamp(s3 / 0.8)), 10, GREEN, 0.8 * clamp(1 - s3 / 0.8))
        labels["marker"] = _scr(f, mx + math.cos(phi) * mlen, my + math.sin(phi) * mlen)
        labels["planet"] = _scr(f, pcx - PR * 0.7, pcy - PR * 0.7)
        sc_ = _scale(f)
        avoid = [(*_scr(f, mx, my), rm * 2.2 * sc_), (*_scr(f, pcx, pcy), PR * 1.15 * sc_)]

    scr = _screen(f)
    scr.__enter__()
    ox, oy = math.cos(th), math.sin(th)
    qx, qy = -oy, ox
    _callout(f, "MARKED FACE", *labels["marker"], 150, 130, 0.5, color=c_, a=1 - f.prog(t3, 0.3), avoid=avoid)
    if "bulge" in labels:
        _callout(f, "TIDAL BULGE", *labels["bulge"], 170, 140, t1 + 0.4, color=c_,
                 a=1 - f.prog(t1 + 1.8, 0.4), avoid=avoid)
    if "brake" in labels and g * kb > 0.2:
        _callout(f, "TIDAL BRAKE", *labels["brake"], 170, 140, t1 + 2.0, color=RED, a=clamp(g * 2), avoid=avoid)
    if p("hud", True):
        years = float(p("years", 50))
        el = years * clamp((f.t - t2) / (t3 - t2))
        status = ("spinning", INK) if f.t < t1 else (("braking", GOLD) if f.t < t3 else ("LOCKED", GREEN))
        _panel(f, "SPIN MONITOR", [("SPINS PER ORBIT", f"{ratio:.1f}", GREEN if s3 > 0 else INK),
                                   ("BULGE LAG", f"{math.degrees(lag):.0f}°"),
                                   ("ELAPSED", f"+{el:,.0f} million yrs" if f.t >= t2 else "today"),
                                   ("STATUS", status[0], status[1])], c_, w=540)
        _stages(f, ["SPIN", "BULGE", "SLOWDOWN", "LOCKED"], [0, t1, t2, t3], c_)
        _note(f)
    title = p("title", "TIDALLY LOCKED")
    if title:
        slam_text(f, title, 960, 810, t3 + 0.15, size=130, glow_color=GREEN)
    scr.__exit__(None, None, None)
    flash(f, t3, dur=0.4, color="#e0ffe8", peak=0.35)
