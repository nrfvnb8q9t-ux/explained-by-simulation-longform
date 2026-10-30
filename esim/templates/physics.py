"""Physics simulations that show the mechanism: falling, cannons, tides, warped spacetime, time."""

import math
from functools import lru_cache

import numpy as np
import skia

from esim.templates import Sfx, accent, body, pick, rand, shot_camera, template, when
from esim.engine import *  # noqa: F401,F403
from esim import engine as E


# ---------------------------------------------------------------- shared helpers

# run_shot films every template through a slow ambient camera (zoom up to ~1.15 plus drift), so anything that
# matters stays inside this box (in template coordinates) and clear of the caption zone.
SAFE_L, SAFE_R, SAFE_T, SAFE_B = 170, 1750, 110, 860

def _beats(f, p, spec, gap=0.5):
    """[(param, fraction)] -> beat times in seconds, kept in order with a small gap between them."""
    out, last = [], -1e9
    for key, frac in spec:
        t = max(when(f, p(key), frac), last + gap)
        out.append(t)
        last = t
    return out


def _k(f, t0, dur=1.0, fn=ease_in_out):
    """Eased 0..1 progress of a change that starts at t0 seconds."""
    return fn((f.t - t0) / dur) if dur > 0 else float(f.t >= t0)


def _sstep(ts, t0, dur):
    """Vectorised smoothstep progress for an array of times."""
    x = np.clip((ts - t0) / max(dur, 1e-3), 0, 1)
    return x * x * (3 - 2 * x)


def _panel(f, x, y, w, h, color, a=1.0):
    """A dark HUD panel with an accent outline and corner brackets."""
    rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), 16, 16)
    f.c.drawRRect(rr, paint("#03060f", 0.66 * a))
    f.c.drawRRect(rr, paint(color, 0.35 * a, stroke=2))
    bp = paint(color, 0.95 * a, stroke=3)
    for cx_, cy_, dx, dy in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        f.c.drawLine(cx_ + dx * 8, cy_ + dy * 8, cx_ + dx * 34, cy_ + dy * 8, bp)
        f.c.drawLine(cx_ + dx * 8, cy_ + dy * 8, cx_ + dx * 8, cy_ + dy * 34, bp)


def _readout(f, x, y, lab, val, color, size=50, a=1.0, align="left", val_color=INK):
    text(f, lab, x, y, size=30, color=DIM, a=a, align=align, weight="semibold")
    text(f, val, x, y + size + 4, size=size, color=val_color, a=a, align=align, glow_color=color)


def _note(f, s, x=SAFE_R, y=150, align="right"):
    text(f, s, x, y, size=30, color=DIM, a=0.8, align=align, weight="body")


def _poly(points):
    path = skia.Path()
    if len(points) > 1:
        path.addPoly([skia.Point(float(x), float(y)) for x, y in points], False)
    return path


def _arrow(f, x0, y0, x1, y1, color, width=6, a=1.0, head=None, glow_a=0.3):
    """A clean glowing vector arrow."""
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 2 or a <= 0:
        return
    head = head or min(26, L * 0.45)
    ang = math.atan2(y1 - y0, x1 - x0)
    bx, by = x1 - math.cos(ang) * head * 0.8, y1 - math.sin(ang) * head * 0.8
    f.c.drawLine(x0, y0, bx, by, paint(color, glow_a * a, stroke=width * 3, add=True))
    f.c.drawLine(x0, y0, bx, by, paint(color, a, stroke=width))
    tri = skia.Path()
    tri.moveTo(x1, y1)
    for side in (-1, 1):
        aa = ang + math.pi + side * 0.42
        tri.lineTo(x1 + math.cos(aa) * head, y1 + math.sin(aa) * head)
    tri.close()
    f.c.drawPath(tri, paint(color, a))


def _bh_clean(f, x, y, r, color=GOLD, a=1.0, tilt=0.28, spin=1.0):
    """A smooth black hole: glowing accretion disk with turning streaks, the lensed arc over the top, photon ring."""
    c = f.c
    soft_light(f, x, y, r * 6, color, 0.28 * a)

    def disk():
        c.save()
        c.translate(x, y)
        c.scale(1, tilt)
        ring(f, 0, 0, r * 2.3, r * 1.05, color, 0.8 * a)
        ring(f, 0, 0, r * 1.9, r * 0.4, "#fff3dc", 0.85 * a)
        rng = f.rng("bhc_streaks")
        for i in range(14):
            rr = r * (1.45 + 1.9 * rng.random())
            start = (rng.random() * 360 + f.t * spin * 160 * (r * 1.6 / rr) ** 1.5) % 360
            sweep = 30 + rng.random() * 70
            c.drawArc(skia.Rect.MakeLTRB(-rr, -rr, rr, rr), start, sweep, False,
                      paint("#fff1d6" if i % 3 == 0 else color, (0.5 + 0.4 * rng.random()) * a, stroke=1.5 + 2.5 * rng.random(), add=True))
        c.restore()

    c.save()
    c.clipRect(skia.Rect.MakeLTRB(x - r * 6, y - r * 6, x + r * 6, y))
    disk()
    c.restore()
    c.drawCircle(x, y, r * 1.32, paint(color, 0.5 * a, stroke=r * 0.2, add=True))
    c.drawCircle(x, y, r * 1.32, paint("#fff1d6", 0.5 * a, stroke=r * 0.05, add=True))
    c.drawCircle(x, y, r, paint("#000000", a))
    ring(f, x, y, r * 1.04, r * 0.08, "#fff1d6", 0.95 * a)
    c.save()
    c.clipRect(skia.Rect.MakeLTRB(x - r * 6, y, x + r * 6, y + r * 6))
    disk()
    c.restore()


# ================================================================ 1. Newton's cannon

_ORBIT_KMS = {"earth": 7.9, "frozen_earth": 7.9, "moon": 1.7, "mars": 3.6, "mercury": 3.0, "venus": 7.3,
              "jupiter": 42.1, "saturn": 25.1, "uranus": 15.1, "neptune": 16.6, "pluto": 0.85}


@lru_cache(maxsize=32)
def _cannon_path(v, ground):
    """Launch horizontally from r=1 with speed v (in units of circular speed). GM=1. Velocity Verlet."""
    dt = 0.004
    x, y, vx, vy = 0.0, 1.0, v, 0.0
    r3 = 1.0
    ax, ay = -x / r3, -y / r3
    pts = [(x, y)]
    landed = False
    for _ in range(int(2 * math.pi / dt) + 2):
        vx += 0.5 * dt * ax
        vy += 0.5 * dt * ay
        x += dt * vx
        y += dt * vy
        r = math.hypot(x, y)
        ax, ay = -x / r ** 3, -y / r ** 3
        vx += 0.5 * dt * ax
        vy += 0.5 * dt * ay
        pts.append((x, y))
        if r < ground:
            landed = True
            break
        if r > 5.5:
            break
    return np.array(pts, np.float32), landed


def _mountain(f, cx, cy, R, top, key="mtn"):
    rng = f.rng(key)
    base = math.radians(19)
    n = 41
    angs = np.linspace(-base, base, n)
    edge = 1 - np.abs(angs) / base
    h = (top - R + 6) * np.minimum(1, edge / 0.8) ** 1.4
    h = h + (rng.random(n) - 0.5) * 9 * edge * (edge < 0.8)
    rr = R - 6 + h
    path = skia.Path()
    path.moveTo(cx + math.sin(-base) * (R - 14), cy - math.cos(-base) * (R - 14))
    for a, r in zip(angs, rr):
        path.lineTo(cx + math.sin(a) * r, cy - math.cos(a) * r)
    path.lineTo(cx + math.sin(base) * (R - 14), cy - math.cos(base) * (R - 14))
    path.close()
    shade = skia.GradientShader.MakeLinear([skia.Point(cx - 60, 0), skia.Point(cx + 60, 0)],
                                           [col("#a2927f"), col("#5d5146"), col("#231c17")], [0, 0.5, 1])
    f.c.drawPath(path, skia.Paint(AntiAlias=True, Shader=shade))
    f.c.save()
    f.c.clipPath(path, doAntiAlias=True)
    for i in range(9):  # gullies and crags, darker on the shadow side
        a0 = (i - 4) * base / 5 + (rng.random() - 0.5) * 0.04
        r0 = top - 4 - rng.random() * 10
        path_g = skia.Path()
        path_g.moveTo(cx + math.sin(a0 * 0.35) * r0, cy - r0)
        path_g.quadTo(cx + math.sin(a0 * 0.8) * (R + 20), cy - (R + 22) - rng.random() * 8,
                      cx + math.sin(a0 * 1.1) * R, cy - R + 4)
        f.c.drawPath(path_g, paint("#000000", 0.18 + 0.2 * (a0 > 0), stroke=2.5 + rng.random() * 2))
    for i in range(30):
        a0 = (rng.random() - 0.5) * 2 * base
        r0 = R + rng.random() * (top - R)
        f.c.drawCircle(cx + math.sin(a0) * r0, cy - math.cos(a0) * r0, 1 + rng.random() * 2.5,
                       paint("#000000" if rng.random() < 0.6 else "#d8c8b0", 0.25))
    pk_y = cy - top
    snow = skia.Path()
    snow.moveTo(cx - 40, pk_y + 4)
    for j in range(9):
        snow.lineTo(cx - 40 + j * 10 + 5, pk_y + 14 + (rng.random() * 12 if j % 2 else 4))
    snow.lineTo(cx + 46, pk_y + 4)
    snow.lineTo(cx + 46, pk_y - 20)
    snow.lineTo(cx - 40, pk_y - 20)
    snow.close()
    f.c.drawPath(snow, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
        [skia.Point(cx - 40, 0), skia.Point(cx + 46, 0)], [col("#ffffff"), col("#c8d3e2"), col("#7d8798")])))
    f.c.restore()
    f.c.drawPath(path, paint("#000000", 0.35, stroke=1.5))


def _cannon(f, x, y, recoil=0.0):
    """A little cannon with its muzzle at (x, y), pointing right."""
    c = f.c
    x -= recoil
    c.drawCircle(x - 26, y + 10, 10, paint("#3a2a1c"))
    c.drawCircle(x - 26, y + 10, 10, paint("#c7a57a", 0.9, stroke=2.5))
    c.drawCircle(x - 26, y + 10, 2.5, paint("#c7a57a"))
    rect = skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(x - 50, y - 7, x, y + 7), 5, 5)
    sh = skia.GradientShader.MakeLinear([skia.Point(0, y - 7), skia.Point(0, y + 7)],
                                        [col("#d8dee8"), col("#6b7380"), col("#20242b")], [0, 0.45, 1])
    c.drawRRect(rect, skia.Paint(AntiAlias=True, Shader=sh))
    c.drawRect(skia.Rect.MakeLTRB(x - 4, y - 8.5, x + 1, y + 8.5), paint("#9aa3b0"))
    c.drawRect(skia.Rect.MakeLTRB(x - 52, y - 8.5, x - 46, y + 8.5), paint("#9aa3b0"))


@template("newtons_cannon", sfx=lambda p: [
    Sfx("808", p("shot1_at") or 0.6, gain_db=-4), Sfx("808", p("shot2_at") or 1.7, gain_db=-2),
    Sfx("whoosh", p("orbit_at") or 2.8), Sfx("riser", p("escape_at") or "end", offset=-1.6 if p("escape_at") else -3.4, dur=1.5),
    Sfx("impact", p("escape_at") or "end", offset=0.0 if p("escape_at") else -1.8)])
def newtons_cannon(f, p):
    """Newton's cannon: a cannon on a mountain fires faster and faster. The first two shots arc down and land
    ('falls back'), the third falls all the way round without hitting the ground ('orbit'), the last flies off for
    good ('escape'). Trajectories are traced and stay on screen; a HUD counts the launch speed against the orbit and
    escape speeds, and the camera pulls out from the mountain to the whole planet.
    params: planet (body kind, default earth), shot1_at, shot2_at (words the two falling shots fire on),
    orbit_at (word the orbit shot fires on), escape_at (word the escape shot fires on, the payoff),
    orbit_speed (km/s, default from the planet: earth 7.9, moon 1.7, mars 3.6...), payoff (slam text on the escape,
    default 'ESCAPE VELOCITY', '' for none), color"""
    c_ = accent(f, p, default=["cyan", "green", "ice"])
    esc_c = "#9b7bff" if c_ in ("#ff5ad1",) else "#ff5ad1"
    kind = p("planet", "earth")
    v_orb = float(p("orbit_speed", _ORBIT_KMS.get(kind, 7.9)))
    times = _beats(f, p, [("shot1_at", 0.1), ("shot2_at", 0.28), ("orbit_at", 0.46), ("escape_at", 0.7)])
    fracs = [0.62, 0.86, 1.0, 1.45]
    cols = [GOLD, "#ff8a3d", c_, esc_c]
    names = ["falls back", "falls back", "orbit", "escape"]
    S, ground, cx, cy = 300.0, 0.8, 960.0, 540.0
    R = S * ground
    TS, dt = 0.5, 0.004  # scene seconds per sim time unit; sim step
    pulse = f.beat_pulse()

    space(f, drift=(rand(f, "nc_dx", -10, -3), 0), stars=460)

    # camera: starts tight on the cannon, pulls out with every shot
    kfs = [(times[0] + 0.25, cx + 70, cy - S + 110, 1.42), (times[1] + 0.25, cx + 30, cy - 120, 1.12),
           (times[2] + 0.15, cx + 20, cy - 60, 0.92), (times[3] + 0.3, cx + 60, cy - 116, 0.82)]
    kx, ky, kz = cx + 10, cy - S + 40, 1.78 + 0.08 * _k(f, 0, max(times[0], 0.5))
    for t0, x1, y1, z1 in kfs:
        k = _k(f, t0, 1.6)
        kx, ky, kz = lerp(kx, x1, k), lerp(ky, y1, k), lerp(kz, z1, k)
    kx += 10 * math.sin(f.t * 0.35)
    ky += 6 * math.cos(f.t * 0.27)
    shake = sum((5 + 6 * (i == 3)) * math.exp(-(f.t - ti) * 6) for i, ti in enumerate(times) if f.t > ti)

    v_disp, regime, reg_c = 0.0, "READY", DIM
    for i, ti in enumerate(times):
        if f.t >= ti:
            prev = fracs[i - 1] * v_orb if i else 0.0
            v_disp = lerp(prev, fracs[i] * v_orb, _k(f, ti, 0.45, ease_out))
            regime, reg_c = names[i].upper(), cols[i]

    with camera(f, kx, ky, zoom=kz, shake=shake):
        soft_light(f, cx, cy, R * 1.9, c_, 0.10 + 0.06 * pulse)
        projectiles = []
        for i, ti in enumerate(times):
            s = f.t - ti
            if s < 0:
                continue
            path, landed = _cannon_path(fracs[i], ground)
            n = len(path)
            steps = s / TS / dt
            idx = int(min(steps, n - 1))
            pts = np.stack([cx + path[:, 0] * S, cy - path[:, 1] * S], 1)
            if i == 2 and steps >= n - 1:
                idx = n - 1
            seg = pts[:idx + 1:3]
            if len(seg) > 1:
                pth = _poly(seg.tolist() + [pts[idx].tolist()])
                done = steps >= n - 1
                f.c.drawPath(pth, paint(cols[i], 0.16 + 0.08 * pulse, stroke=12, add=True))
                f.c.drawPath(pth, paint(cols[i], 0.55 if done else 0.9, stroke=3.2))
            if i == 2:  # the orbit keeps going round
                j = int(steps) % (n - 1)
                projectiles.append((i, pts[j], pts[max(j - 1, 0)] if j else pts[-2], None))
            elif steps < n - 1:
                projectiles.append((i, pts[idx], pts[max(idx - 2, 0)], None))
            else:
                t_land = ti + (n - 1) * dt * TS
                projectiles.append((i, pts[-1], None, t_land if landed else None))
        body(f, kind, cx, cy, R, light=(-0.75, -0.35, 0.55), rotation=f.t * 0.01, seed_key="nc_planet")
        _mountain(f, cx, cy, R, S - 16)
        recoil = sum(8 * math.exp(-(f.t - ti) * 9) for ti in times if f.t > ti)
        _cannon(f, cx, cy - S, recoil)
        for i, ti in enumerate(times):  # muzzle flash and smoke
            s = f.t - ti
            if 0 <= s < 0.6:
                glow(f, cx + 6, cy - S, 26 * (1 - s / 0.6) + 4, "#ffd08a", 1 - s / 0.6)
                particles(f, cx + 4, cy - S, ti, n=60, speed=(160, 620), life=(0.2, 0.7), size=(1.2, 3.5),
                          color=GOLD, spread=(-28, 28), key=f"nc_fire{i}", drag=2.5)
            if 0 <= s < 3.0:
                rng = f.rng(f"nc_smoke{i}")
                m = 18
                ang = rng.random(m) * 2.4 - 1.2 - 0.3
                d = (10 + 110 * rng.random(m)) * (1 - math.exp(-s * 2.2))
                sx = cx + 8 + np.cos(ang) * d
                sy = cy - S - 6 + np.sin(ang) * d - 16 * s
                rad = 10 + 26 * s * (0.5 + rng.random(m))
                for x_, y_, r_ in zip(sx.tolist(), sy.tolist(), rad.tolist()):
                    soft_light(f, x_, y_, r_, "#cdd2dc", 0.28 * (1 - s / 3.0), add=False)
        for i, pos, prev, t_land in projectiles:
            x, y = float(pos[0]), float(pos[1])
            if t_land is not None:
                sl = f.t - t_land
                soft_light(f, x, y, 60, cols[i], 0.5 * math.exp(-sl * 0.8) + 0.12)
                if sl < 1.6:
                    particles(f, x, y, t_land, n=50, speed=(40, 240), life=(0.4, 1.4), size=(1.5, 4),
                              color=cols[i], key=f"nc_land{i}", drag=2.0)
                    shockwave(f, x, y, t_land, speed=160, life=0.9, color=cols[i], width=6)
                f.c.drawCircle(x, y, 5, paint(cols[i], 0.9))
                nx_, ny_ = (x - cx) / R, (y - cy) / R
                tx_, ty_ = (x + nx_ * 110 + 20, y + ny_ * 90 - 10) if i == 0 else (x + nx_ * 60 + 40, y + ny_ * 60 + 130)
                label(f, names[i], x, y, tx_, ty_, t_land + 0.1, size=38, color=cols[i], line_color=cols[i])
            else:
                glow(f, x, y, 8 * (1 + 0.35 * pulse), cols[i], 1.0)
            if i == 2 and f.t - times[2] > 0.9:  # gravity and velocity vectors on the orbiting shot
                k = _k(f, times[2] + 0.9, 0.5)
                gx, gy = (cx - x) / S, (cy - y) / S
                _arrow(f, x, y, x + gx * 70 * k, y + gy * 70 * k, GOLD, width=4, a=0.9 * k)
                if prev is not None:
                    tx_, ty_ = x - float(prev[0]), y - float(prev[1])
                    L = math.hypot(tx_, ty_) or 1
                    _arrow(f, x, y, x + tx_ / L * 80 * k, y + ty_ / L * 80 * k, c_, width=4, a=0.9 * k)
        # orbit and escape labels
        if f.t > times[2]:
            label(f, "orbit", cx - S, cy, cx - S - 80, cy + 90,
                  times[2] + 0.78 * TS * 2 * math.pi, size=40, color=c_, line_color=c_)
        if f.t > times[3]:
            path, _ = _cannon_path(fracs[3], ground)
            j = int(np.argmax(np.hypot(path[:, 0], path[:, 1]) > 1.45))
            ex, ey = cx + path[j, 0] * S, cy - path[j, 1] * S
            label(f, "escape", ex, ey, ex + 90, ey - 120, times[3] + 0.5, size=42, color=esc_c, line_color=esc_c)

    # HUD
    _panel(f, SAFE_L, SAFE_T, 600, 250, c_)
    text(f, "LAUNCH SPEED", SAFE_L + 32, SAFE_T + 54, size=30, color=DIM, align="left", weight="semibold")
    text(f, regime, SAFE_L + 572, SAFE_T + 54, size=34, color=reg_c, align="right", weight="bold")
    text(f, f"{v_disp:.1f} km/s", SAFE_L + 32, SAFE_T + 134, size=72, align="left", glow_color=reg_c if v_disp else None)
    bx, by, bw = SAFE_L + 32, SAFE_T + 166, 536
    vmax = v_orb * 1.75
    f.c.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(bx, by, bw, 14), 7, 7), paint("#ffffff", 0.08))
    fill_w = bw * clamp(v_disp / vmax)
    if fill_w > 1:
        sh = skia.GradientShader.MakeLinear([skia.Point(bx, 0), skia.Point(bx + bw, 0)],
                                            [col(GOLD), col(c_), col(esc_c)], [0.3, 0.57, 0.82])
        f.c.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(bx, by, fill_w, 14), 7, 7),
                      skia.Paint(AntiAlias=True, Shader=sh))
        soft_light(f, bx + fill_w, by + 7, 30, reg_c, 0.6)
    for frac, lab, cc in ((1 / 1.75, f"ORBIT {v_orb:.1f}", c_), (math.sqrt(2) / 1.75, f"ESCAPE {v_orb * math.sqrt(2):.1f}", esc_c)):
        tx = bx + bw * frac
        f.c.drawLine(tx, by - 6, tx, by + 20, paint(cc, 0.95, stroke=3))
    text(f, "ORBIT", bx + bw / 1.75, by + 56, size=30, color=c_, weight="semibold")
    text(f, "ESCAPE", bx + bw * math.sqrt(2) / 1.75, by + 56, size=30, color=esc_c, weight="semibold")
    _note(f, "mountain not to scale")
    flash(f, times[3], dur=0.45, color="#ffe9f6", peak=0.55)
    if p("payoff", "ESCAPE VELOCITY"):
        slam_text(f, p("payoff", "ESCAPE VELOCITY"), 960, 815, times[3] + 0.3, size=100, glow_color=esc_c, hold=2.4)


# ================================================================ 2. spacetime as a rubber sheet

def _st_project(X, Y, Z, yaw, pitch, dist, focal, ox, oy):
    cyw, syw = math.cos(yaw), math.sin(yaw)
    Xr = X * cyw - Y * syw
    Yr = X * syw + Y * cyw
    cp, sp = math.cos(pitch), math.sin(pitch)
    dy = Yr + dist * cp
    dz = Z - dist * sp
    depth = dy * cp - dz * sp
    up = dy * sp + dz * cp
    dd = np.maximum(depth, 0.4)
    return ox + focal * Xr / dd, oy - focal * up / dd, depth, Yr


def _st_add_lines(back, front, sx, sy, yr):
    """Add projected polylines (rows of arrays) to a back and front path, split where they cross the centre plane."""
    for xs, ys, ws in zip(sx, sy, yr):
        sign = ws > 0
        cuts = np.nonzero(sign[1:] != sign[:-1])[0] + 1
        start = 0
        for end in list(cuts) + [len(xs)]:
            e = min(end + 1, len(xs))
            if e - start > 1:
                target = back if sign[start] else front
                target.addPoly([skia.Point(a, b) for a, b in zip(xs[start:e].tolist(), ys[start:e].tolist())], False)
            start = end


@template("spacetime_grid", sfx=lambda p: [
    Sfx("rumble", "start", dur=5, gain_db=-8), Sfx("whoosh", p("orbit_at") or 1.4, gain_db=-4),
    Sfx("riser", p("grow_at") or 2.6, dur=2.0, gain_db=-4),
    Sfx("power_down", p("collapse_at") or "end", offset=-0.5 if p("collapse_at") else -2.2, dur=0.8),
    Sfx("808", p("collapse_at") or "end", offset=0.1 if p("collapse_at") else -1.6)])
def spacetime_grid(f, p):
    """Spacetime as a rubber sheet, in 3D: a star sits in a dip in a glowing grid. A small world rolls in and
    settles into orbit by following the curve; then the star gains mass and the dip deepens (the orbit tightens);
    the payoff: it collapses into a black hole and the middle of the grid funnels down into a bottomless throat,
    while the orbit far away doesn't change. A HUD tracks mass, radius and escape speed (which hits light speed).
    params: orbit_at (word the small world rolls in on), grow_at (word the star starts gaining mass),
    collapse_at (word it collapses, the payoff), mass (final mass in Suns, default 20), orbiter (body kind, default
    moon), payoff (slam text, default 'BLACK HOLE', '' for none), color"""
    c_ = accent(f, p, default=["cyan", "purple", "ice", "green"])
    t_orb, t_grow, t_col = _beats(f, p, [("orbit_at", 0.12), ("grow_at", 0.4), ("collapse_at", 0.68)], gap=1.0)
    m_end = float(p("mass", 20))
    pulse = f.beat_pulse()

    def state(ts):
        ts = np.asarray(ts, np.float64)
        g = _sstep(ts, t_grow, 1.8)
        cl = np.clip((ts - t_col) / 0.6, 0, 1) ** 2
        M = 2.0 * (1 + 1.0 * g)
        soft = (1.05 + 0.3 * g) * (1 - 0.88 * cl)
        cap = 2.8 + 3.6 * _sstep(ts, t_col, 0.9)
        return M, soft, cap, g, cl

    M, soft, cap, g, cl = (float(v) for v in state(f.t))

    # orbiter: rolls in from far away, its angle integrated so speed changes stay smooth
    tg = np.linspace(0, max(f.t, 1e-3), 400)
    Mg, _, _, _, _ = state(tg)
    r_set = 4.3 * (2.0 / Mg) ** 0.3
    app = np.clip((tg - t_orb) / 2.8, 0, 1)
    rg = np.where(tg < t_orb, 17.0, 17.0 + (r_set - 17.0) * (1 - (1 - app) ** 3))
    om = np.where(tg < t_orb, 0.0, 6.0 * np.sqrt(Mg) / rg ** 1.5)
    phig = math.radians(rand(f, "st_phi0", 25, 55)) + np.concatenate([[0], np.cumsum((om[1:] + om[:-1]) / 2 * np.diff(tg))])

    def sheet(X, Y, t_now=f.t):
        r = np.hypot(X, Y)
        z = -M * (1 / np.sqrt(r * r + soft * soft) - 1 / math.sqrt(900 + soft * soft))
        z = -cap * np.tanh(-z / cap)
        for t0, amp in ((0.0, 0.14), (t_col, 0.9), (t_grow, 0.35)):
            s = t_now - t0 + (1.2 if t0 == 0 else 0)
            if 0 < s < 6:
                front_ = 4.0 * s
                z = z + amp * math.exp(-s * 0.55) * np.exp(-((r - front_) / 1.8) ** 2) * np.sin((r - front_) * 2.0)
        return z

    yaw = lerp(rand(f, "st_yaw0", -0.3, -0.12), rand(f, "st_yaw1", 0.12, 0.3), ease_in_out(f.p)) + 0.02 * math.sin(f.t * 0.5)
    pitch = lerp(0.44, 0.62, ease_in_out(f.p))
    dist = lerp(18.5, 15.0, ease_in_out(f.p))
    focal, ox, oy = 1150.0, 960.0, lerp(470, 420, f.p)
    cam = (yaw, pitch, dist, focal, ox, oy)

    space(f, drift=(-3, 0), stars=420)
    s_col = f.t - t_col
    shake = 16 * math.exp(-s_col * 3.0) if s_col > 0 else 0.0
    zoom = 1 + (0.06 * math.exp(-s_col * 2.5) if s_col > 0 else 0)
    with camera(f, 960, 540, zoom=zoom, shake=shake):
        # grid lines, densest near the middle so the funnel stays smooth
        u = np.linspace(-1, 1, 151)
        dense = np.sign(u) * np.abs(u) ** 1.7
        Xs = np.arange(-26, 26.01, 1.0)
        Ys = np.arange(-11, 16.01, 1.0)
        yline = np.where(u < 0, 11 * dense, 16 * dense)
        LX, LY = np.meshgrid(dense * 28, Ys)          # rows of constant Y
        CY, CX = np.meshgrid(yline, Xs)               # rows of constant X
        rings_r = np.array([0.35, 0.6, 0.9, 1.3, 1.8, 2.5, 3.3])
        th = np.linspace(0, 2 * math.pi, 97)
        RX, RY = rings_r[:, None] * np.cos(th)[None], rings_r[:, None] * np.sin(th)[None]
        back, front = skia.Path(), skia.Path()
        for X, Y in ((LX, LY), (CX, CY)):
            sx, sy, dep, yr = _st_project(X, Y, sheet(X, Y), *cam)
            _st_add_lines(back, front, sx, sy, yr)
        ring_back, ring_front = skia.Path(), skia.Path()
        sx, sy, dep, yr = _st_project(RX, RY, sheet(RX, RY), *cam)
        _st_add_lines(ring_back, ring_front, sx, sy, yr)
        _, far_y, _, _ = _st_project(np.array([0.0]), np.array([16.0]), np.array([0.0]), *cam)
        wx, wy, wdep, _ = _st_project(np.array([0.0]), np.array([0.0]), np.array([float(sheet(np.array(0.0), np.array(0.0)))]), *cam)
        wx, wy, wdep = float(wx[0]), float(wy[0]), float(wdep[0])
        _, top_y, _, _ = _st_project(np.array([0.0]), np.array([0.0]), np.array([0.0]), *cam)
        top_y = float(top_y[0])
        fy = float(far_y[0])
        # darken the space under the sheet a little so the grid reads
        f.c.drawRect(skia.Rect.MakeLTRB(-100, fy, W + 100, H + 100), skia.Paint(Shader=skia.GradientShader.MakeLinear(
            [skia.Point(0, fy), skia.Point(0, H)], [col("#000000", 0), col("#02030a", 0.55)])))
        fog = skia.GradientShader.MakeLinear([skia.Point(0, fy - 5), skia.Point(0, H)],
                                             [col(mix(c_, INK, 0.4), 0), col(mix(c_, INK, 0.4), 0.38), col(mix(c_, INK, 0.3), 0.62)],
                                             [0, clamp(265 / max(H - fy + 5, 1), 0.01, 0.99), 1])
        glow_sh = skia.GradientShader.MakeRadial(skia.Point(wx, top_y), 620,
                                                 [col(c_, 0.95), col(c_, 0.45), col(c_, 0)], [0, 0.4, 1],
                                                 localMatrix=skia.Matrix().setScale(1.0, 0.55, wx, top_y))
        fog_p = skia.Paint(AntiAlias=True, Shader=fog, StrokeWidth=1.6, Style=skia.Paint.kStroke_Style)
        glow_p = skia.Paint(AntiAlias=True, Shader=glow_sh, StrokeWidth=2.2, Style=skia.Paint.kStroke_Style,
                            BlendMode=skia.BlendMode.kPlus, Alphaf=0.75 + 0.25 * pulse)
        wide_p = skia.Paint(AntiAlias=True, Shader=glow_sh, StrokeWidth=9, Style=skia.Paint.kStroke_Style,
                            BlendMode=skia.BlendMode.kPlus, Alphaf=0.12 + 0.08 * pulse)
        ring_a = clamp(0.25 + 0.75 * _k(f, t_col, 0.8))
        ring_p = skia.Paint(AntiAlias=True, Shader=glow_sh, StrokeWidth=2.0, Style=skia.Paint.kStroke_Style,
                            BlendMode=skia.BlendMode.kPlus, Alphaf=ring_a)

        def draw_grid(pth, rpth):
            f.c.drawPath(pth, wide_p)
            f.c.drawPath(pth, fog_p)
            f.c.drawPath(pth, glow_p)
            f.c.drawPath(rpth, ring_p)

        # orbiter position
        phi = float(phig[-1])
        r_now = float(rg[-1])
        ob = None
        if f.t >= t_orb:
            OX, OY = np.array([r_now * math.cos(phi)]), np.array([r_now * math.sin(phi)])
            osx, osy, odep, oyr = _st_project(OX, OY, sheet(OX, OY) + 0.32, *cam)
            hist = np.linspace(max(t_orb, f.t - 1.6), f.t, 26)
            hp = np.interp(hist, tg, phig)
            hr = np.interp(hist, tg, rg)
            HX, HY = hr * np.cos(hp), hr * np.sin(hp)
            hsx, hsy, _, _ = _st_project(HX, HY, sheet(HX, HY) + 0.32, *cam)
            ob = (float(osx[0]), float(osy[0]), float(odep[0]), float(oyr[0]), list(zip(hsx.tolist(), hsy.tolist())))

        def draw_orbiter():
            if ob is None:
                return
            x, y, dep, _, hist_pts = ob
            trail(f, hist_pts, color=mix(c_, INK, 0.3), width=3, a=0.8)
            rr = max(6, focal * 0.34 / max(dep, 1))
            soft_light(f, x, y, rr * 3, c_, 0.25)
            body(f, p("orbiter", "moon"), x, y, rr, light=(-0.4, -0.7, 0.6), seed_key="st_orbiter")

        draw_grid(back, ring_back)
        if ob and ob[3] > 0:
            draw_orbiter()
        # the central mass
        star_r = focal * (0.7 + 0.3 * g) / max(wdep, 1) * (1 - cl) * (1 + 0.04 * pulse)
        sx_, sy_ = wx, wy - star_r * 0.75
        if star_r > 1.5:
            soft_light(f, sx_, sy_, star_r * 5, mix(GOLD, "#9fd4ff", g), 0.25 + 0.1 * pulse)
            if g < 0.99:
                body(f, "sun", sx_, sy_, star_r, alpha=1 - g)
            if g > 0.01:
                body(f, "neutron_star", sx_, sy_, star_r, alpha=g)
        if s_col > 0:
            bh_r = 44 * ease_back(clamp((s_col - 0.35) / 0.5)) * (1 + 0.03 * pulse)
            if bh_r > 1:
                _bh_clean(f, wx, wy - 14, bh_r, a=clamp((s_col - 0.35) / 0.3), color=mix(GOLD, c_, 0.25), tilt=0.32)
            if s_col < 1.2:
                glow(f, wx, wy - 10, 60 * (1 - s_col / 1.2) + 10, "#ffffff", 1 - s_col / 1.2)
        draw_grid(front, ring_front)
        if ob and ob[3] <= 0:
            draw_orbiter()
        # annotations
        if g < 0.6:
            with layer(f, 1 - _k(f, t_orb + 0.9, 0.5)):
                rx_, ry_, _, _ = _st_project(np.array([2.2]), np.array([-1.2]), sheet(np.array(2.2), np.array(-1.2)), *cam)
                label(f, "mass curves spacetime", float(rx_[0]), float(ry_[0]), wx + 160, wy - 250,
                      0.3, size=38, color=INK, line_color=c_)
        if ob is not None:
            with layer(f, 1 - _k(f, t_col - 0.3, 0.4) if f.t < t_col + 1.5 else _k(f, t_col + 1.5, 0.5)):
                lab = "it just follows the curve" if f.t < t_col else "orbit unchanged"
                label(f, lab, ob[0], ob[1], ob[0] + (220 if ob[0] < 1250 else -220), ob[1] + (-150 if f.t < t_col else 130),
                      t_orb + 1.4 if f.t < t_col else t_col + 1.5, size=36, color=INK, line_color=c_)
        if s_col > 0:
            label(f, "event horizon", wx + 40, wy - 14, wx + 330, wy - 60, t_col + 0.6, size=38, color=INK, line_color=GOLD)

    # HUD: mass, radius, escape speed
    m_suns = 1 + (m_end - 1) * g
    r_star = 696000 * (1 + 7 * g)
    r_bh = 2.95 * m_end
    radius = math.exp(lerp(math.log(r_star), math.log(r_bh), cl))
    v_esc = min(617.7 * math.sqrt(m_suns / (radius / 696000)), 299792)
    _panel(f, SAFE_L, SAFE_T, 450, 310, c_)
    _readout(f, SAFE_L + 32, SAFE_T + 54, "MASS", f"{m_suns:,.1f} Suns", c_, size=46)
    _readout(f, SAFE_L + 32, SAFE_T + 148, "RADIUS", f"{radius:,.0f} km", c_, size=46)
    light = v_esc >= 299791
    _readout(f, SAFE_L + 32, SAFE_T + 242, "ESCAPE SPEED", f"{v_esc:,.0f} km/s" if not light else "LIGHT SPEED", RED if light else c_,
             size=46, val_color=RED if light else INK)
    _note(f, "a 2D slice of curved spacetime")
    flash(f, t_col, dur=0.5, color="#ffffff", peak=0.8)
    if p("payoff", "BLACK HOLE"):
        slam_text(f, p("payoff", "BLACK HOLE"), 1220, 250, t_col + 0.15, size=120, glow_color=c_, hold=2.6)


# ================================================================ 3. free fall through the atmosphere

@lru_cache(maxsize=16)
def _fall_sim(h0_km, vt0):
    """Drop from rest at h0 km. Drag ~ rho(h) v^2 tuned so terminal speed at sea level is vt0 m/s."""
    g, Hs, dt = 9.81, 8500.0, 0.1
    k = g / vt0 ** 2
    h, v, t = h0_km * 1000.0, 0.0, 0.0
    ts, hs, vs = [0.0], [h], [0.0]
    while h > 0 and t < 4000:
        a = g - k * math.exp(-h / Hs) * v * abs(v)
        v += a * dt
        h -= v * dt
        t += dt
        ts.append(t)
        hs.append(h)
        vs.append(v)
    ts, hs, vs = np.array(ts), np.array(hs), np.array(vs)
    # after the peak the speed tracks the local terminal speed down into thicker air; the curve flattens into the
    # plateau once it's within ~50% of the sea-level terminal speed
    i_pk = int(np.argmax(vs))
    after = np.nonzero((np.arange(len(vs)) > i_pk) & (vs <= 1.5 * vt0))[0]
    i_term = int(after[0]) if len(after) else len(vs) - 1
    s_pk, s_term = ts[i_pk], ts[i_term]
    s_end = max(min(s_term + 0.6 * (ts[-1] - s_term), ts[-1] - 2), s_term + 1)
    return ts, hs, vs, s_pk, s_term, s_end


def _air_temp(h_km):
    pts = [(0, 288), (11, 217), (20, 217), (32, 229), (47, 271), (51, 271), (71, 215), (86, 187), (100, 195), (130, 470)]
    return float(np.interp(h_km, [a for a, _ in pts], [b for _, b in pts]))


_SKY = [(0, "#6aaee8"), (5, "#3f86d0"), (12, "#1f56a6"), (25, "#0e2d6e"), (40, "#081a48"), (55, "#050f30"),
        (75, "#03081c"), (95, "#02040c"), (300, "#010207")]
_LAYERS = [(100, "KARMAN LINE", "edge of space"), (85, "MESOSPHERE", "below 85 km"), (50, "STRATOSPHERE", "below 50 km"),
           (12, "TROPOSPHERE", "below 12 km")]


def _layer_name(h):
    return "THERMOSPHERE" if h > 85 else "MESOSPHERE" if h > 50 else "STRATOSPHERE" if h > 12 else "TROPOSPHERE"


def _capsule(f, x, y, s, heat):
    """A blunt re-entry capsule, heat shield down, with panel lines, a window and thrusters."""
    c = f.c
    path = skia.Path()
    path.moveTo(x - 0.3 * s, y - 0.6 * s)
    path.lineTo(x + 0.3 * s, y - 0.6 * s)
    path.lineTo(x + 0.6 * s, y + 0.3 * s)
    path.quadTo(x, y + 0.5 * s, x - 0.6 * s, y + 0.3 * s)
    path.close()
    sh = skia.GradientShader.MakeLinear([skia.Point(x - 0.6 * s, 0), skia.Point(x + 0.6 * s, 0)],
                                        [col("#f4f6fa"), col("#b9c0cc"), col("#5a6170"), col("#1c2028")], [0, 0.3, 0.65, 1])
    c.drawPath(path, skia.Paint(AntiAlias=True, Shader=sh))
    c.save()
    c.clipPath(path, doAntiAlias=True)
    for i in range(1, 5):  # panel seams
        yy = y - 0.6 * s + i * 0.18 * s
        c.drawLine(x - s, yy, x + s, yy, paint("#000000", 0.22, stroke=1.5))
    for i in range(-3, 4):
        c.drawLine(x + i * 0.09 * s, y - 0.6 * s, x + i * 0.19 * s, y + 0.4 * s, paint("#000000", 0.14, stroke=1.2))
    c.drawRect(skia.Rect.MakeLTRB(x - 0.6 * s, y + 0.12 * s, x + 0.6 * s, y + 0.5 * s),
               paint(mix("#ff6a1f", "#ffd9a0", heat), 0.55 * heat, add=True))
    c.restore()
    shield = skia.Path()
    shield.moveTo(x + 0.62 * s, y + 0.29 * s)
    shield.quadTo(x, y + 0.5 * s, x - 0.62 * s, y + 0.29 * s)
    shield.quadTo(x, y + 0.66 * s, x + 0.62 * s, y + 0.29 * s)
    c.drawPath(shield, paint(mix("#3b2a20", "#ffc27a", heat), 1))
    c.drawPath(shield, paint("#ffe6c0", 0.8 * heat, stroke=3, add=True))
    win = skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(x - 0.3 * s, y - 0.34 * s, x - 0.12 * s, y - 0.16 * s), 6, 6)
    c.drawRRect(win, paint("#0b1a2c"))
    c.drawRRect(win, paint("#9fd4ff", 0.85, stroke=2.5))
    c.drawLine(x - 0.27 * s, y - 0.2 * s, x - 0.17 * s, y - 0.3 * s, paint("#ffffff", 0.5, stroke=2))
    hatch = skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(x + 0.02 * s, y - 0.42 * s, x + 0.26 * s, y - 0.02 * s), 5, 5)
    c.drawRRect(hatch, paint("#000000", 0.35, stroke=2))
    c.drawCircle(x + 0.2 * s, y - 0.22 * s, 3, paint("#20242b"))
    text(f, "ESIM-1", x + 0.02 * s, y + 0.2 * s, size=max(14, 0.11 * s), color="#20242b", align="center", weight="bold", a=0.7)
    for side in (-1, 1):  # thruster blocks
        c.drawRect(skia.Rect.MakeLTRB(x + side * 0.42 * s - 6, y - 0.05 * s, x + side * 0.42 * s + 6, y + 0.04 * s), paint("#2b2f38"))
    c.drawRect(skia.Rect.MakeLTRB(x - 0.18 * s, y - 0.7 * s, x + 0.18 * s, y - 0.6 * s), paint("#8b93a1"))
    c.drawRect(skia.Rect.MakeLTRB(x - 0.18 * s, y - 0.7 * s, x + 0.18 * s, y - 0.6 * s), paint("#000000", 0.4, stroke=1.5))


@template("free_fall", sfx=lambda p: [
    Sfx("pop", p("release_at") or 0.6), Sfx("whoosh", p("release_at") or 0.6, offset=0.3, dur=2.0),
    Sfx("rumble", p("release_at") or 0.6, offset=0.8, dur=5, gain_db=-6), Sfx("impact", p("peak_at") or 2.7, gain_db=-4),
    Sfx("808", p("terminal_at") or "end", offset=0.0 if p("terminal_at") else -1.5)])
def free_fall(f, p):
    """An object dropped from the edge of space falls through the atmosphere's layers (a real drag simulation): it
    speeds up in the thin air, air streaks and a shock cone grow, its nose glows hot at max speed, then the thickening
    air slows it to terminal velocity, shown as a plateau on a live speed-vs-time graph. Earth's curved horizon flattens
    as it drops. HUD: altitude, speed, Mach, nose temperature, the current layer, and a scrolling altitude ruler.
    params: release_at (word it's let go on), peak_at (word it hits max speed), terminal_at (word it settles to
    terminal velocity, the payoff), from_km (drop height, default 100), object (capsule|rock), terminal (sea-level
    terminal speed m/s, default 90), payoff (slam text, default 'TERMINAL VELOCITY', '' for none), color"""
    c_ = accent(f, p, default=["cyan", "gold", "orange", "ice"])
    t_rel, t_pk, t_term = _beats(f, p, [("release_at", 0.1), ("peak_at", 0.45), ("terminal_at", 0.75)], gap=0.8)
    h0 = float(p("from_km", 100))
    ts, hs, vs, s_pk, s_term, s_end = _fall_sim(h0, float(p("terminal", 90)))
    obj = p("object") or pick(f, "ff_obj", ["capsule", "capsule", "rock"])
    pulse = f.beat_pulse()
    kx = [0.0, t_rel, t_pk, t_term, max(f.dur, t_term + 0.5)]
    ky = [0.0, 0.0, s_pk, s_term, s_end]

    def sim_t(t):
        return np.interp(t, kx, ky)

    st = float(sim_t(f.t))
    h = float(np.interp(st, ts, hs)) / 1000
    v = float(np.interp(st, ts, vs))
    rho = math.exp(-h / 8.5)
    T_air = _air_temp(h)
    mach = v / (20.05 * math.sqrt(T_air))
    T_nose = T_air + 0.9 * v * v / 2010
    heat = clamp((T_nose - 420) / 650) * clamp(math.sqrt(rho / 0.003))
    q = 0.5 * rho * v * v
    q_max = float(np.max(0.5 * np.exp(-hs / 8500) * vs ** 2))
    ox, oy = 960.0, 470.0
    pxkm = 40.0

    def ys(alt):
        return oy - (alt - h) * pxkm

    # sky gradient sampled at screen rows
    rows = np.linspace(-200, H + 200, 10)
    alts = h + (oy - rows) / pxkm
    stops = np.array([a for a, _ in _SKY])
    rgb = [np.interp(alts, stops, [E._rgb(c)[i] for _, c in _SKY]) for i in range(3)]
    sky = [col((float(rgb[0][j]), float(rgb[1][j]), float(rgb[2][j]))) for j in range(len(rows))]
    f.c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeLinear([skia.Point(0, -200), skia.Point(0, H + 200)], sky)))
    starfield(f, n=420, drift=(0, 0), alpha=clamp((h - 25) / 40))
    # Earth far below: a curved limb with a thin bright atmosphere from high up; lower down the horizon flattens,
    # the haze thickens and farmland spreads out in perspective
    hz = clamp(h / 100)
    Rl = lerp(26000, 2300, hz ** 0.6)
    top = lerp(610, 790, hz)
    cyl = top + Rl
    low = clamp((30 - h) / 22)
    inner = mix("#0b2a55", "#2c4a2a", low)
    f.c.drawCircle(960, cyl, Rl, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeRadial(
        skia.Point(960, cyl), Rl, [col("#06142a"), col(inner), col(mix("#1d5a9e", "#6f8f8a", low)), col(mix("#9fdcff", "#d6e8f2", low))],
        [0, 1 - 420 / Rl, 1 - (40 + 50 * low) / Rl, 1])))
    f.c.drawCircle(960, cyl, Rl + 6, paint("#8fd8ff", 0.6 * (1 - low * 0.6), stroke=10, add=True))
    f.c.drawCircle(960, cyl, Rl + 22 + 40 * low, paint(mix("#3f8fff", "#cfe6ff", low), 0.16 + 0.12 * low,
                                                       stroke=36 + 60 * low, add=True))
    rng = f.rng("ff_limb")
    f.c.save()
    f.c.clipPath(skia.Path.Circle(960, cyl, Rl), doAntiAlias=True)
    if low > 0.01:  # perspective fields: rows at fixed ground distances rise towards the horizon as it drops
        fpx = 1100.0
        hk = max(h, 0.4)
        Ds = np.geomspace(1.2, 260, 26)
        rows_y = top + fpx * hk / Ds
        Xs = np.arange(-60, 61, 3.0)
        greens = ["#3d6b34", "#557a35", "#6b7f3a", "#2f5a2c", "#7a7442", "#4a6e3e"]
        with layer(f, low):
            for i in range(len(Ds) - 1):
                y0_, y1_ = float(rows_y[i]), float(rows_y[i + 1])
                if y1_ > H + 300:
                    continue
                for j in range(len(Xs) - 1):
                    xa0 = 960 + (y0_ - top) * Xs[j] / hk
                    xb0 = 960 + (y0_ - top) * Xs[j + 1] / hk
                    xa1 = 960 + (y1_ - top) * Xs[j] / hk
                    xb1 = 960 + (y1_ - top) * Xs[j + 1] / hk
                    if max(xa0, xa1) > W + 400 or min(xb0, xb1) < -400:
                        continue
                    qd = skia.Path()
                    qd.moveTo(xa0, y0_)
                    qd.lineTo(xb0, y0_)
                    qd.lineTo(xb1, y1_)
                    qd.lineTo(xa1, y1_)
                    qd.close()
                    f.c.drawPath(qd, paint(greens[(i * 7 + j * 3 + (i * j) % 5) % len(greens)], 0.9))
            haze = skia.GradientShader.MakeLinear([skia.Point(0, top), skia.Point(0, top + 260)],
                                                  [col("#d6e8f2", 0.95), col("#d6e8f2", 0)])
            f.c.drawRect(skia.Rect.MakeLTRB(0, top - 2, W, top + 260), skia.Paint(Shader=haze))
    for i in range(26):  # cloud decks on the far surface, foreshortened near the horizon
        ang = math.radians(-90 + (rng.random() - 0.5) * 50)
        rr_ = Rl - 20 - rng.random() ** 1.5 * 420
        sx_, sy_ = 960 + math.cos(ang) * rr_, cyl + math.sin(ang) * rr_
        f.c.save()
        f.c.translate(sx_, sy_)
        f.c.scale(1, 0.18 + 0.5 * (Rl - rr_) / 420)
        soft_light(f, 0, 0, 60 + rng.random() * 200, "#ffffff", 0.22 * (1 - 0.5 * low), add=False)
        f.c.restore()
    f.c.restore()
    shake = 7 * (q / q_max) ** 0.7 + (10 * math.exp(-(f.t - t_pk) * 4) if f.t > t_pk else 0)
    with shot_camera(f, p, ox, 520, strength=0.25):
        with camera(f, 960, 540, shake=shake):
            soft_light(f, 1500, ys(h + 6) - 60, 700, "#ffe2b0", 0.12 * clamp(h / 40))
            rng = f.rng("ff_clouds")
            for i in range(22):
                ca = 1.5 + rng.random() * 9
                cxp = rng.random() * (W + 400) - 200
                cyp = ys(ca)
                if -150 < cyp < H + 150:
                    for j in range(5):
                        soft_light(f, cxp + (j - 2) * 70 + rng.random() * 30, cyp + rng.random() * 26,
                                   90 + rng.random() * 70, "#ffffff", 0.18, add=False)
            for alt, name, sub in _LAYERS:
                yb = ys(alt)
                if -40 < yb < H + 40:
                    lp = paint(INK, 0.5, stroke=2)
                    lp.setPathEffect(skia.DashPathEffect.Make([18, 14], 0))
                    f.c.drawLine(-200, yb, W + 200, yb, lp)
                    f.c.drawLine(-200, yb, W + 200, yb, paint(c_, 0.15, stroke=10, add=True))
                    if 590 < yb + 46 < 840:
                        text(f, name, SAFE_L + 20, yb + 46, size=36, color=INK, align="left", weight="bold", a=0.95, stroke=4)
                        text(f, sub, SAFE_L + 20, yb + 84, size=30, color=DIM, align="left", weight="body", a=0.95)
            # air streaks: they move at the object's real speed and fade out in thin air
            rng = f.rng("ff_streaks")
            n = 170
            sx0 = rng.random(n) * (W + 200) - 100
            sy0 = rng.random(n) * (H + 600)
            depth = 0.4 + rng.random(n) * 0.6
            tg = np.linspace(0, max(f.t, 1e-3), 300)
            vg = np.interp(sim_t(tg), ts, vs)
            travel = float(np.trapezoid(vg, tg)) * 2.6
            sy = (sy0 - travel * depth) % (H + 600) - 300
            ln = v * 0.28 * depth + 6
            sa = clamp(rho ** 0.25 * 1.1) * clamp(v / 250)
            if sa > 0.02:
                sp = skia.Path()
                for x_, y_, l_ in zip(sx0.tolist(), sy.tolist(), ln.tolist()):
                    sp.moveTo(x_, y_)
                    sp.lineTo(x_, y_ + l_)
                f.c.drawPath(sp, paint("#dfeeff", 0.35 * sa, stroke=2.2))
                f.c.drawPath(sp, paint(c_, 0.12 * sa, stroke=7, add=True))
            if f.t < t_rel + 0.5:  # tether, cut on release
                k = _k(f, t_rel, 0.5, ease_in)
                ty_ = lerp(oy - 110, -40, k)
                f.c.drawLine(ox, -40, ox, ty_, paint("#d6dbe4", 0.9, stroke=3))
                f.c.drawLine(ox - 16, ty_, ox + 16, ty_, paint("#d6dbe4", 0.9, stroke=6))
                if f.t < t_rel:
                    text(f, "HOLDING", ox + 40, oy - 120, size=30, color=GOLD, align="left", weight="bold",
                         a=0.6 + 0.4 * math.sin(f.t * 6))
            # shock cone trailing back from the nose once supersonic
            if mach > 1:
                ma = clamp(mach - 1) * (0.35 + 0.65 * clamp(rho ** 0.3 * 2.5))
                half = math.asin(1 / mach)
                tip = oy + 92
                for side in (-1, 1):
                    pth = skia.Path()
                    pth.moveTo(ox + side * 4, tip)
                    pth.quadTo(ox + side * 80, tip - 10, ox + side * (80 + 330 * math.cos(half)), tip - 330 * math.sin(half) - 30)
                    sh = skia.GradientShader.MakeLinear([skia.Point(ox, tip), skia.Point(ox + side * 360, tip - 260)],
                                                        [col(INK, 0.85 * ma), col(INK, 0)])
                    f.c.drawPath(pth, skia.Paint(AntiAlias=True, Shader=sh, Style=skia.Paint.kStroke_Style, StrokeWidth=3))
                    sh2 = skia.GradientShader.MakeLinear([skia.Point(ox, tip), skia.Point(ox + side * 300, tip - 220)],
                                                         [col(c_, 0.3 * ma), col(c_, 0)])
                    f.c.drawPath(pth, skia.Paint(AntiAlias=True, Shader=sh2, Style=skia.Paint.kStroke_Style, StrokeWidth=12,
                                                 BlendMode=skia.BlendMode.kPlus))
                arc = skia.Path()
                arc.addArc(skia.Rect.MakeLTRB(ox - 120, tip - 50, ox + 120, tip + 30), 20, 140)
                f.c.drawPath(arc, paint(INK, 0.6 * ma, stroke=3))
            if heat > 0.01:  # leading-edge heating and a stream of hot sparks
                soft_light(f, ox, oy + 70, 260 * (0.5 + heat), "#ff7a2a", 0.55 * heat)
                soft_light(f, ox, oy + 80, 110 * (0.6 + heat), "#fff1c8", 0.8 * heat)
                rng = f.rng("ff_wake")
                m = 70
                age = (f.t * 1.6 + rng.random(m)) % 1.0
                wx_ = ox + (rng.random(m) - 0.5) * 2 * (70 + 90 * age)
                wy_ = oy + 30 - age * 520
                sp = skia.Path()
                for x_, y_, a_ in zip(wx_.tolist(), wy_.tolist(), age.tolist()):
                    sp.moveTo(x_, y_)
                    sp.lineTo(x_, y_ + 18 + 30 * (1 - a_))
                f.c.drawPath(sp, paint("#ffb35a", 0.7 * heat, stroke=3, add=True))
                f.c.drawPath(sp, paint("#ff6a1f", 0.25 * heat, stroke=9, add=True))
            if obj == "rock":
                body(f, "asteroid", ox, oy, 68, rotation=f.t * 0.07, light=(-0.6, -0.5, 0.6), seed_key="ff_rock")
                if heat > 0.01:
                    f.c.drawCircle(ox, oy, 68, paint("#ff7a2a", 0.35 * heat, stroke=6, add=True))
            else:
                soft_light(f, ox - 30, oy - 30, 200, "#ffffff", 0.06)
                _capsule(f, ox, oy, 160, heat)
            if f.t > t_pk:
                shockwave(f, ox, oy, t_pk, speed=700, life=1.0, color=GOLD, width=14)

    # altitude ruler on the right
    rx = SAFE_R - 20
    f.c.save()
    f.c.clipRect(skia.Rect.MakeLTRB(1500, 480, W, SAFE_B))
    f.c.drawLine(rx, 480, rx, SAFE_B, paint(INK, 0.5, stroke=2))
    for km in range(int(h) - 12, int(h) + 13):
        if km < 0:
            continue
        yy = ys(km)
        major = km % 5 == 0
        f.c.drawLine(rx - (26 if major else 12), yy, rx, yy, paint(INK, 0.8 if major else 0.4, stroke=2))
        if major:
            text(f, f"{km} km", rx - 38, yy + 11, size=30, color=INK, align="right", weight="semibold", a=0.9, stroke=4)
    f.c.restore()
    _arrow(f, rx + 34, oy, rx + 6, oy, c_, width=3)

    # HUD
    _panel(f, SAFE_L, SAFE_T, 380, 410, c_)
    x0 = SAFE_L + 30
    _readout(f, x0, SAFE_T + 52, "ALTITUDE", f"{h:,.1f} km", c_, size=46)
    _readout(f, x0, SAFE_T + 146, "SPEED", f"{v * 3.6:,.0f} km/h", c_, size=46,
             val_color=GOLD if t_pk - 0.3 < f.t < t_pk + 1.2 else INK)
    _readout(f, x0, SAFE_T + 240, "MACH", f"{mach:.1f}", c_, size=46, val_color=GOLD if mach > 1 else INK)
    _readout(f, x0, SAFE_T + 334, "NOSE TEMP", f"{T_nose - 273:,.0f} °C", "#ff7a2a", size=46,
             val_color=mix(INK, "#ffb35a", clamp(heat * 1.5)))
    text(f, _layer_name(h), 960, SAFE_T + 46, size=40, color=INK, glow_color=c_, weight="bold", stroke=4)
    text(f, "time sped up", 960, SAFE_T + 86, size=30, color=DIM, weight="body", a=0.85 if f.t > t_rel else 0)
    gx, gy0, gw, gh = SAFE_R - 470, SAFE_T, 470, 340
    _panel(f, gx, gy0, gw, gh, c_)
    text(f, "SPEED vs TIME", gx + 30, gy0 + 50, size=30, color=DIM, align="left", weight="semibold")
    px0, py0, pw, ph = gx + 40, gy0 + 82, gw - 80, gh - 120
    f.c.drawLine(px0, py0 + ph, px0 + pw, py0 + ph, paint(DIM, 0.8, stroke=2))
    f.c.drawLine(px0, py0, px0, py0 + ph, paint(DIM, 0.8, stroke=2))
    vmax = float(vs.max()) * 1.12

    def gpt(s_, v_):
        return px0 + pw * s_ / s_end, py0 + ph - ph * v_ / vmax

    if st > 0:
        ss = np.linspace(0, st, 160)
        gv = np.interp(ss, ts, vs)
        pts = [gpt(a, b) for a, b in zip(ss, gv)]
        pth = _poly(pts)
        f.c.drawPath(pth, paint(c_, 0.35, stroke=12, add=True))
        f.c.drawPath(pth, paint(c_, 1, stroke=4))
        glow(f, pts[-1][0], pts[-1][1], 8 * (1 + 0.4 * pulse), c_)
    if f.t > t_pk:
        mx, my = gpt(s_pk, float(np.interp(s_pk, ts, vs)))
        k = _k(f, t_pk, 0.3, ease_back)
        f.c.drawCircle(mx, my, 9 * k, paint(GOLD))
        text(f, "MAX SPEED", mx - 16, my + 8, size=30, color=GOLD, align="right", weight="bold", a=clamp(k))
    if f.t > t_term:
        k = _k(f, t_term, 0.6)
        v_t = float(np.interp(s_end, ts, vs))
        _, ty = gpt(0, v_t)
        dp = paint(GREEN, 0.9, stroke=3)
        dp.setPathEffect(skia.DashPathEffect.Make([12, 9], -f.t * 30))
        f.c.drawLine(px0, ty, px0 + pw * k, ty, dp)
        soft_light(f, px0 + pw * 0.8, ty, 120, GREEN, 0.25 * k + 0.1 * pulse)
        text(f, "TERMINAL", px0 + pw, ty - 14, size=30, color=GREEN, align="right", weight="bold", a=k)
    flash(f, t_pk, dur=0.35, color="#fff1d0", peak=0.3)
    flash(f, t_term, dur=0.4, color="#eafff0", peak=0.35)
    if p("payoff", "TERMINAL VELOCITY"):
        slam_text(f, p("payoff", "TERMINAL VELOCITY"), 960, 790, t_term + 0.1, size=96, glow_color=GREEN, hold=2.6)


# ================================================================ 4. tides

@lru_cache(maxsize=8)
def _topdown_grid(d):
    r = d / 2
    ys_, xs_ = np.mgrid[0:d, 0:d].astype(np.float32)
    nx = (xs_ + 0.5 - r) / r
    ny = (ys_ + 0.5 - r) / r
    rr = np.sqrt(nx ** 2 + ny ** 2)
    nz = np.sqrt(np.clip(1 - rr ** 2, 0, 1))
    phi = np.arctan2(ny, nx)
    lat = np.arccos(np.clip(rr, 0, 1))
    edge = np.clip((1 - rr) * r, 0, 1)
    return nx, ny, nz, phi, lat, edge


def _earth_from_above(f, x, y, R, rot, light):
    """Earth seen from above the North Pole: continents turn around the pole, ice cap, day and night, city lights."""
    d = int(R * 2) // 4 * 4
    nx, ny, nz, phi, lat, edge = _topdown_grid(d)
    tex = E._planet_texture("earth", stable_seed(f.seed, "tides-earth"))
    u = (((phi / (2 * np.pi)) + rot) % 1.0) * (tex.w - 1)
    v = (0.5 - lat / np.pi) * (tex.h - 1)
    rgb = tex.rgb[v.astype(np.int32), u.astype(np.int32)]
    wob = 1.6 * np.sin(phi * 3 + rot * 6.28 + 1.1) + 1.1 * np.sin(phi * 5 + rot * 6.28 * 2 + 0.4)
    ice = np.clip((np.degrees(lat) - 75 + wob) / 2.0, 0, 1)[..., None]
    rgb = rgb * (1 - ice) + ice * np.array([0.93, 0.96, 1.0], np.float32)
    L = np.array(light, np.float32)
    L /= np.linalg.norm(L)
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    shade = 0.035 + 0.965 * lam ** 0.85
    Hh = L + np.array([0, 0, 1], np.float32)
    Hh /= np.linalg.norm(Hh)
    spec = np.clip(nx * Hh[0] + ny * Hh[1] + nz * Hh[2], 0, 1) ** 70 * (rgb[..., 2] > rgb[..., 0] + 0.12)
    out = rgb * shade[..., None] + spec[..., None] * 0.7
    land = (rgb[..., 1] > 0.28) & (rgb[..., 2] < 0.45) & (ice[..., 0] < 0.5)
    dark = np.clip(1 - lam * 5, 0, 1)
    ui, vi = u.astype(np.int64), v.astype(np.int64)
    hsh = ((ui // 4 * 73856093) ^ (vi // 4 * 19349663)) % 1000 / 1000.0
    lights = dark * land * (hsh > 0.965) * 0.9
    out = out + lights[..., None] * np.array([1.0, 0.7, 0.35], np.float32)
    rgba = np.empty((d, d, 4), np.uint8)
    rgba[..., :3] = (np.clip(out, 0, 1) * edge[..., None] * 255).astype(np.uint8)
    rgba[..., 3] = (edge * 255).astype(np.uint8)
    img = skia.Image.fromarray(rgba, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
    halo(f, x, y, R, R * 1.16, CYAN, 0.4)
    f.c.drawImageRect(img, skia.Rect.MakeXYWH(x - R, y - R, 2 * R, 2 * R), skia.SamplingOptions(skia.FilterMode.kLinear))


@template("tides", sfx=lambda p: [
    Sfx("shimmer", 0.4, gain_db=-6), Sfx("tick", p("arrows_at") or 1.4), Sfx("whoosh", p("stretch_at") or 2.6, gain_db=-4),
    Sfx("riser", p("closer_at") or "end", offset=0.1 if p("closer_at") else -2.8, dur=1.2),
    Sfx("808", p("closer_at") or "end", offset=1.3 if p("closer_at") else -1.6)])
def tides(f, p):
    """Why there are two tides a day, seen from above the North Pole: the oceans bulge towards the Moon and away from
    it, the Moon orbits and the bulges follow while Earth spins underneath (a marked coast sweeps through high and low
    tide on a gauge). A faint field of arrows shows the Moon's stretching (tidal) pull all around. Gravity arrows show
    the near side pulled hardest and the far side least; then the differences, which stretch the ocean both ways.
    Payoff: the Moon moves much closer and the bulges balloon (tides grow with 1/distance cubed).
    params: arrows_at (word the gravity arrows appear), stretch_at (word they turn into the stretching
    'difference' arrows), closer_at (word the Moon moves closer, the payoff), closer (new distance as a fraction,
    default 0.65), payoff (slam text, default computed like '3.6x HIGHER TIDES', '' for none), color"""
    c_ = accent(f, p, default=["cyan", "ice", "purple", "green"])
    t_arr, t_str, t_cl = _beats(f, p, [("arrows_at", 0.16), ("stretch_at", 0.4), ("closer_at", 0.66)], gap=1.0)
    frac = float(p("closer", 0.65))
    fac = (1 / frac) ** 3
    pulse = f.beat_pulse()
    ex, ey, R, mr = 960.0, 490.0, 120.0, 32.0
    d0 = 380.0
    light = (-0.85, -0.2, 0.45)
    # moon distance and angle (closer orbits are faster), integrated so the motion stays smooth
    tg = np.linspace(0, max(f.t, 1e-3), 300)
    dg = d0 * (1 - (1 - frac) * _sstep(tg, t_cl, 1.5))
    om = 0.32 * (d0 / dg) ** 1.5
    th0 = math.radians(rand(f, "td_th0", -40, 20))
    theta = th0 - float(np.trapezoid(om, tg))
    d = float(dg[-1])
    amp_fac = (d0 / d) ** 3
    tb = theta - 0.12  # Earth's spin drags the bulges a little ahead of the Moon
    A = min(21 * amp_fac, d - R - mr - 34)
    mx, my = ex + d * math.cos(theta), ey + d * math.sin(theta)
    ux, uy = math.cos(tb), math.sin(tb)
    k_arr = _k(f, t_arr, 0.6) * (1 - _k(f, t_cl, 0.5))
    k_str = _k(f, t_str, 0.8)

    s_cl = f.t - t_cl
    zoom = 1.0 + 0.1 * _k(f, t_cl, 1.5)
    shake = 12 * math.exp(-(s_cl - 1.3) * 3) if s_cl > 1.3 else 0
    space(f, drift=(-3, 1), stars=460)
    with shot_camera(f, p, ex, ey, strength=0.35):
        with camera(f, ex, ey + 10, zoom=zoom, shake=shake):
            soft_light(f, -300, ey, 1300, "#ffe2b0", 0.22)  # sunlight from the left
            soft_light(f, ex, ey, 620, c_, 0.10 + 0.05 * pulse)
            # tidal field: stretch along the Earth-Moon line, squeeze across it (grows with distance from Earth)
            gxs, gys = np.meshgrid(np.arange(160, 1780, 110.0), np.arange(80, 920, 105.0))
            rx_, ry_ = gxs - ex, gys - ey
            rr_ = np.hypot(rx_, ry_)
            par = rx_ * ux + ry_ * uy
            ax_ = 3 * par * ux - rx_
            ay_ = 3 * par * uy - ry_
            mag = np.hypot(ax_, ay_) + 1e-6
            keep = (rr_ > R + A + 50) & (np.hypot(gxs - mx, gys - my) > 90)
            Ls = np.clip(mag / 520, 0.2, 1) * (26 + 10 * k_str + 6 * min(amp_fac - 1, 1))
            fa = (0.2 + 0.14 * k_str + 0.06 * min(amp_fac - 1, 1)) * np.clip(1.4 - rr_ / 900, 0.3, 1)
            fp = skia.Path()
            for x_, y_, dx_, dy_, l_, kp in zip(gxs.ravel(), gys.ravel(), (ax_ / mag).ravel(), (ay_ / mag).ravel(),
                                               Ls.ravel(), keep.ravel()):
                if not kp:
                    continue
                x1_, y1_ = x_ + dx_ * l_ / 2, y_ + dy_ * l_ / 2
                fp.moveTo(x_ - dx_ * l_ / 2, y_ - dy_ * l_ / 2)
                fp.lineTo(x1_, y1_)
                for sd in (-1, 1):
                    aa = math.atan2(dy_, dx_) + math.pi + sd * 0.5
                    fp.moveTo(x1_, y1_)
                    fp.lineTo(x1_ + math.cos(aa) * 9, y1_ + math.sin(aa) * 9)
            fpaint = paint(mix(c_, INK, 0.4), float(np.mean(fa)), stroke=2.2)
            f.c.drawPath(fp, fpaint)
            orbit(f, ex, ey, d, d, color=DIM, a=0.5, width=2)
            # ocean shell (the two bulges)
            n = 220
            ph = np.linspace(0, 2 * math.pi, n, endpoint=False)
            rr = R + 7 + A * (0.5 + 0.5 * np.cos(2 * (ph - tb)))
            shell = _poly(list(zip((ex + rr * np.cos(ph)).tolist(), (ey + rr * np.sin(ph)).tolist())))
            shell.close()
            outer = R + 7 + A
            wsh = skia.GradientShader.MakeRadial(skia.Point(ex, ey), outer + 4,
                                                 [col("#0c3f8a"), col("#0c3f8a"), col("#1f7fd6", 0.92), col("#8fe0ff", 0.85)],
                                                 [0, R / (outer + 4), (R + 7 + A * 0.45) / (outer + 4), 1])
            f.c.drawPath(shell, skia.Paint(AntiAlias=True, Shader=wsh))
            f.c.drawPath(shell, paint("#d6f6ff", 0.75, stroke=2.5))
            f.c.drawPath(shell, paint(c_, 0.22 + 0.12 * pulse, stroke=14, add=True))
            rng = f.rng("td_spark")
            m = 140
            sa = rng.random(m) * 2 * math.pi + f.t * 0.25 * (rng.random(m) - 0.5)
            srr = R + 4 + (7 + A * (0.5 + 0.5 * np.cos(2 * (sa - tb)))) * rng.random(m)
            dots(f, ex + srr * np.cos(sa), ey + srr * np.sin(sa), 1 + 1.6 * rng.random(m),
                 0.35 + 0.35 * np.sin(f.t * 3 + rng.random(m) * 6), "#e8fbff", add=True)
            _earth_from_above(f, ex, ey, R, f.t * 0.16, light)
            for sgn in (1, -1):  # the bulges tint the disc too
                soft_light(f, ex + sgn * R * 0.8 * ux, ey + sgn * R * 0.8 * uy, R * 0.7, "#4fc3ff",
                           0.10 + 0.05 * min(amp_fac, 3))
            # a coast riding on the spinning Earth
            cang = -2 * math.pi * f.t * 0.16 + rand(f, "td_city", 0, 6.28)
            cx_, cy_ = ex + R * 0.72 * math.cos(cang), ey + R * 0.72 * math.sin(cang)
            tide = math.cos(2 * (cang - tb))
            f.c.drawCircle(cx_, cy_, 9 + 2 * pulse, paint(GOLD))
            f.c.drawCircle(cx_, cy_, 16, paint(GOLD, 0.85, stroke=3))
            body(f, "moon", mx, my, mr, light=light, seed_key="td_moon")
            soft_light(f, mx, my, 110, INK, 0.08)
            # gravity arrows: ~1/r^2 at the near side, the centre and the far side; then minus the centre's pull
            mux, muy = math.cos(theta), math.sin(theta)
            vx_, vy_ = -muy, mux
            gc = 95.0
            g_near, g_far, g_c = gc * (d / (d - R)) ** 2, gc * (d / (d + R)) ** 2, gc
            if k_arr > 0:
                for (px_, py_), gl, lab in (((ex + mux * R, ey + muy * R), g_near, "strongest"), ((ex, ey), g_c, ""),
                                            ((ex - mux * R, ey - muy * R), g_far, "weakest")):
                    L = lerp(gl, gl - g_c, k_str)
                    colr = GOLD if k_str < 0.5 else c_
                    a_c = k_arr * (1 - k_str) if lab == "" else k_arr
                    if abs(L) > 4 and a_c > 0.01:
                        _arrow(f, px_, py_, px_ + mux * L * k_arr, py_ + muy * L * k_arr, colr, width=7, a=a_c)
                    if lab:
                        sgn = 1 if lab == "strongest" else -1
                        tx_ = px_ + mux * sgn * 40 + vx_ * 70
                        ty_ = py_ + muy * sgn * 40 + vy_ * 70 + 10
                        text(f, lab if k_str < 0.5 else ("pulled most" if sgn > 0 else "left behind"), tx_, ty_,
                             size=34, color=colr, weight="bold", a=k_arr, stroke=6)
                if k_str > 0:  # and the squeeze at the sides
                    for sgn in (1, -1):
                        px_, py_ = ex + vx_ * (R + 80) * sgn, ey + vy_ * (R + 80) * sgn
                        _arrow(f, px_, py_, px_ - vx_ * 55 * sgn, py_ - vy_ * 55 * sgn, c_, width=5, a=k_arr * k_str * 0.9)
            k_lab = (1 - _k(f, t_arr, 0.4)) if f.t < t_cl + 1.0 else _k(f, t_cl + 1.4, 0.5)
            if k_lab > 0.02:
                pvx, pvy = (-uy, ux) if -uy > 0 else (uy, -ux)  # perpendicular, pointing right
                with layer(f, k_lab):
                    for sgn in (1, -1):
                        px_, py_ = ex + sgn * ux * (R + 7 + A), ey + sgn * uy * (R + 7 + A)
                        tx_ = min(max(px_ + sgn * ux * 40 + pvx * 190, SAFE_L + 40), SAFE_R - 260)
                        ty_ = min(max(py_ + sgn * uy * 40 + pvy * 190, SAFE_T + 260), SAFE_B - 90)
                        label(f, "high tide", px_, py_, tx_, ty_,
                              0.3 if sgn > 0 else 0.7, size=36, color=INK, line_color=c_)
            sw = f.t - (t_cl + 1.3)
            if 0 < sw < 1.5:
                rr_w = R + A + 20 + 560 * sw
                ring(f, ex, ey, rr_w, 30, c_, 0.5 * (1 - sw / 1.5))
                ring(f, ex, ey, rr_w, 5, "#ffffff", 0.8 * (1 - sw / 1.5))

    # HUD: moon distance, tidal strength, tide gauge
    _panel(f, SAFE_L, SAFE_T, 430, 214, c_)
    _readout(f, SAFE_L + 30, SAFE_T + 52, "MOON DISTANCE", f"{384400 * d / d0:,.0f} km", c_, size=46)
    _readout(f, SAFE_L + 30, SAFE_T + 142, "TIDAL STRETCH", f"x{amp_fac:.1f}", c_, size=46,
             val_color=GOLD if amp_fac > 1.05 else INK)
    gxp = SAFE_R - 380
    _panel(f, gxp, SAFE_T, 380, 260, GOLD)
    text(f, "TIDE AT", gxp + 30, SAFE_T + 52, size=30, color=DIM, align="left", weight="semibold")
    f.c.drawCircle(gxp + 176, SAFE_T + 42, 8, paint(GOLD))
    f.c.drawCircle(gxp + 176, SAFE_T + 42, 14, paint(GOLD, 0.85, stroke=3))
    hgt = 0.5 * amp_fac * tide
    text(f, f"{hgt:+.1f} m", gxp + 30, SAFE_T + 128, size=56, color=INK, align="left", glow_color=GOLD)
    rising = math.sin(2 * (cang - tb)) < 0
    text(f, "HIGH TIDE" if tide > 0.6 else "LOW TIDE" if tide < -0.6 else ("RISING" if rising else "FALLING"),
         gxp + 30, SAFE_T + 178, size=34, color=GOLD if tide > 0.6 else c_, align="left", weight="bold")
    text(f, "two tides a day", gxp + 30, SAFE_T + 228, size=30, color=DIM, align="left", weight="body")
    bxx, byy, bh = gxp + 322, SAFE_T + 30, 200
    f.c.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(bxx, byy, 24, bh), 12, 12), paint("#ffffff", 0.1))
    lvl = clamp(0.5 + 0.5 * tide * min(amp_fac, 4) / 4)
    f.c.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(bxx, byy + bh * (1 - lvl), 24, bh * lvl), 12, 12),
                  paint("#2f9df0", 0.95))
    soft_light(f, bxx + 12, byy + bh * (1 - lvl), 26, "#8fe0ff", 0.6)
    _note(f, "not to scale", x=SAFE_L, y=SAFE_B, align="left")
    flash(f, t_cl + 1.3, dur=0.4, color="#e8fbff", peak=0.4)
    payoff = p("payoff")
    if payoff is None:
        payoff = (f"{fac:.1f}x" if fac < 10 else f"{fac:.0f}x") + " HIGHER TIDES"
    if payoff:
        slam_text(f, payoff, 960, 815, t_cl + 1.3, size=96, glow_color=c_, hold=2.6)


# ================================================================ 5. time dilation

def _clock_face(f, x, y, r, T, color, hand_c, a=1.0):
    c = f.c
    soft_light(f, x, y, r * 1.9, color, 0.16 * a)
    face = skia.GradientShader.MakeRadial(skia.Point(x - r * 0.25, y - r * 0.3), r * 1.3,
                                          [col("#1a2440"), col("#0a0f1e"), col("#03050b")], [0, 0.6, 1])
    c.drawCircle(x, y, r, skia.Paint(AntiAlias=True, Shader=face))
    c.drawCircle(x, y, r, paint(color, 0.95 * a, stroke=7))
    c.drawCircle(x, y, r + 7, paint(color, 0.3 * a, stroke=16, add=True))
    c.drawCircle(x, y, r * 0.93, paint(color, 0.35 * a, stroke=1.5))
    for i in range(60):
        ang = i / 60 * 2 * math.pi
        major = i % 5 == 0
        r0 = r * (0.8 if major else 0.86)
        c.drawLine(x + math.cos(ang) * r0, y + math.sin(ang) * r0, x + math.cos(ang) * r * 0.91,
                   y + math.sin(ang) * r * 0.91, paint(INK, (0.95 if major else 0.4) * a, stroke=4 if major else 1.5))
    for i, num in ((0, "12"), (3, "3"), (6, "6"), (9, "9")):
        ang = i / 12 * 2 * math.pi - math.pi / 2
        text(f, num, x + math.cos(ang) * r * 0.64, y + math.sin(ang) * r * 0.64 + 11, size=32, color=INK, a=0.9 * a)
    for frac, length, width, colr in ((T / 12, 0.5, 9, INK), (T, 0.74, 6, INK), (T * 12, 0.84, 2.5, hand_c)):
        ang = (frac % 1) * 2 * math.pi - math.pi / 2
        c.drawLine(x - math.cos(ang) * r * 0.12, y - math.sin(ang) * r * 0.12, x + math.cos(ang) * r * length,
                   y + math.sin(ang) * r * length, paint(colr, a, stroke=width))
    c.drawCircle(x, y, 9, paint(hand_c, a))
    gl = skia.GradientShader.MakeLinear([skia.Point(x - r, y - r), skia.Point(x, y)], [col("#ffffff", 0.12 * a), col("#ffffff", 0)])
    c.drawCircle(x, y, r * 0.95, skia.Paint(AntiAlias=True, Shader=gl))


@template("time_dilation", sfx=lambda p: [
    Sfx("tick", 0.3, gain_db=-6), Sfx("power_down", p("slow_at") or 1.1, dur=1.2, gain_db=-4),
    Sfx("reverse", p("extreme_at") or 2.7, dur=1.0), Sfx("riser", p("payoff_at") or "end", offset=-1.5 if p("payoff_at") else -3.0, dur=1.5),
    Sfx("808", p("payoff_at") or "end", offset=0.0 if p("payoff_at") else -1.5)])
def time_dilation(f, p):
    """Two clocks side by side: one far away, one near a black hole (or moving close to light speed). They start in
    step; as the second one goes deeper (or faster) its hands and digital counter fall behind, its signal rings get
    stretched apart and reddened, and its 'time rate' drops; at the extreme it almost freezes. Payoff: the gap between
    the two clocks slams onto the screen.
    params: mode (gravity|speed), slow_at (word clock B starts slowing), extreme_at (word it gets extreme: at the
    horizon / 99.5% of light speed), payoff_at (word the time difference slams in), unit (years|days|hours|minutes,
    default years), per_second (clock A's units per second of screen time, default 1), a_label, b_label,
    payoff (slam text, default computed like '9.4 YEARS APART', '' for none), color"""
    c_ = accent(f, p, default=["cyan", "ice", "green", "purple"])
    mode = p("mode") or pick(f, "td_mode", ["gravity", "gravity", "speed"])
    t_slow, t_ext, t_pay = _beats(f, p, [("slow_at", 0.18), ("extreme_at", 0.45), ("payoff_at", 0.75)], gap=1.0)
    unit = str(p("unit", "years"))
    rate = float(p("per_second", 1.0))
    pulse = f.beat_pulse()

    def depth(ts):
        return 0.6 * _sstep(ts, t_slow, 1.8) + 0.4 * _sstep(ts, t_ext, 1.6)

    def ratio(ts):
        u = depth(ts)
        if mode == "speed":
            beta = np.where(u < 0.6, u / 0.6 * 0.8, 0.8 + (u - 0.6) / 0.4 * 0.195)
            return np.sqrt(1 - beta ** 2), beta
        lx = np.where(u < 0.6, np.log(200) + (np.log(2.2) - np.log(200)) * u / 0.6,
                      np.log(2.2) + (np.log(1.02) - np.log(2.2)) * (u - 0.6) / 0.4)
        xr = np.exp(lx)
        return np.sqrt(1 - 1 / xr), xr

    def clock_b(t_):
        tg = np.linspace(0, max(t_, 1e-3), 360)
        rt, _ = ratio(tg)
        return tg, rt, np.concatenate([[0], np.cumsum((rt[1:] + rt[:-1]) / 2 * np.diff(tg))]) * rate

    tg, rt, TBg = clock_b(f.t)
    TA, TB = f.t * rate, float(TBg[-1])
    r_now, aux = (float(v) for v in ratio(np.array(f.t)))
    _, _, TBp = clock_b(t_pay)
    diff_pay = t_pay * rate - float(TBp[-1])

    gradient_bg(f, "#060a18", "#020309")
    starfield(f, n=300, drift=(-3, 0), alpha=0.8)
    s_pay = f.t - t_pay
    shake = 14 * math.exp(-s_pay * 3) if s_pay > 0 else 0
    ax, ay, cr = 560.0, 490.0, 145.0
    u_now = float(depth(np.array(f.t)))
    if mode == "speed":
        bx, by = 1345.0, 490.0
    else:
        bx, by = lerp(1290, 1400, u_now), lerp(470, 500, u_now)
    b_col = mix(c_, "#ff3b2f", (1 - r_now) ** 0.6)
    with shot_camera(f, p, 960, 540, strength=0.18):
        with camera(f, 960, 540, shake=shake):
            # right half: the black hole and its warped grid, or speed streaks
            f.c.save()
            f.c.clipRect(skia.Rect.MakeLTRB(960, -100, W + 200, H + 200))
            f.c.drawPaint(paint("#120608" if mode == "gravity" else "#060b18", 0.5))
            if mode == "gravity":
                hx, hy, hr = 1650.0, 500.0, 80.0
                gp = skia.Path()
                for xi in np.arange(980, 1960, 60):
                    ys_ = np.linspace(-40, 1120, 70)
                    xs_ = np.full_like(ys_, xi)
                    dxv, dyv = hx - xs_, hy - ys_
                    dd = np.hypot(dxv, dyv) + 1
                    s = np.minimum(0.85, (hr * 1.6 / dd) ** 1.1)
                    gp.addPoly([skia.Point(a, b) for a, b in zip((xs_ + dxv * s).tolist(), (ys_ + dyv * s).tolist())], False)
                for yi in np.arange(-20, 1120, 60):
                    xs_ = np.linspace(970, 1960, 70)
                    ys_ = np.full_like(xs_, yi)
                    dxv, dyv = hx - xs_, hy - ys_
                    dd = np.hypot(dxv, dyv) + 1
                    s = np.minimum(0.85, (hr * 1.6 / dd) ** 1.1)
                    gp.addPoly([skia.Point(a, b) for a, b in zip((xs_ + dxv * s).tolist(), (ys_ + dyv * s).tolist())], False)
                f.c.drawPath(gp, paint(mix(GOLD, RED, 0.3), 0.16, stroke=1.5))
                _bh_clean(f, hx, hy, hr * (1 + 0.03 * pulse), color=mix(GOLD, RED, 0.25), tilt=0.26)
            else:
                rng = f.rng("td_streak")
                n = 120
                sx0, sy0 = rng.random(n) * 1100 + 960, rng.random(n) * H
                tgv = np.linspace(0, max(f.t, 1e-3), 200)
                _, bg = ratio(tgv)
                trav = float(np.trapezoid(bg, tgv)) * 1800
                depthv = 0.3 + rng.random(n) * 0.7
                sx = (sx0 - 960 - trav * depthv) % 1100 + 960
                ln = 4 + aux * 260 * depthv
                sp = skia.Path()
                for x_, y_, l_ in zip(sx.tolist(), sy0.tolist(), ln.tolist()):
                    sp.moveTo(x_, y_)
                    sp.lineTo(x_ + l_, y_)
                f.c.drawPath(sp, paint(INK, 0.6, stroke=2))
                # the clock rides in a ship's porthole; the engine flame grows with speed
                back, nose, hh = bx - 300, bx + 300, 96
                fl = 40 + 420 * aux
                flame = skia.Path()
                flame.moveTo(back + 4, by - hh * 0.55)
                flame.quadTo(back - fl * 0.6, by - hh * 0.35, back - fl, by)
                flame.quadTo(back - fl * 0.6, by + hh * 0.35, back + 4, by + hh * 0.55)
                flame.close()
                f.c.drawPath(flame, skia.Paint(AntiAlias=True, BlendMode=skia.BlendMode.kPlus, Shader=skia.GradientShader.MakeLinear(
                    [skia.Point(back, 0), skia.Point(back - fl, 0)], [col("#ffffff", 0.95), col(c_, 0.8), col(c_, 0)], [0, 0.35, 1])))
                soft_light(f, back - 30, by, 200 + 160 * aux, c_, 0.3 + 0.4 * aux)
                hull = skia.Path()
                hull.moveTo(back, by - hh)
                hull.lineTo(bx + 150, by - hh)
                hull.quadTo(nose - 20, by - hh * 0.8, nose, by)
                hull.quadTo(nose - 20, by + hh * 0.8, bx + 150, by + hh)
                hull.lineTo(back, by + hh)
                hull.close()
                for sd in (-1, 1):
                    fin = skia.Path()
                    fin.moveTo(back + 20, by + sd * hh)
                    fin.lineTo(back - 30, by + sd * (hh + 70))
                    fin.lineTo(back + 110, by + sd * hh)
                    fin.close()
                    f.c.drawPath(fin, paint("#3a4252"))
                    f.c.drawPath(fin, paint(c_, 0.6, stroke=2))
                f.c.drawPath(hull, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
                    [skia.Point(0, by - hh), skia.Point(0, by + hh)], [col("#e8edf5"), col("#8f98a8"), col("#2b313c")], [0, 0.4, 1])))
                for k_ in range(1, 5):
                    xx = back + k_ * 90
                    f.c.drawLine(xx, by - hh, xx, by + hh, paint("#000000", 0.18, stroke=2))
                f.c.drawPath(hull, paint(c_, 0.5, stroke=2))
                f.c.drawRect(skia.Rect.MakeLTRB(back - 14, by - hh * 0.6, back + 2, by + hh * 0.6), paint("#20242c"))
            f.c.restore()
            f.c.drawLine(960, 0, 960, H, paint(c_, 0.6, stroke=3))
            soft_light(f, 960, 540, 260, c_, 0.12 + 0.1 * pulse)
            # signal rings: each clock sends a ring every tick of its own time
            tick = 0.5 * rate
            for (x0, y0, clip, T_hist, colr) in (
                    (ax, ay, (-100, 958), None, c_), (bx, by, (962, W + 100), TBg, b_col)):
                f.c.save()
                f.c.clipRect(skia.Rect.MakeLTRB(clip[0], -100, clip[1], H + 100))
                if T_hist is None:
                    kk = np.arange(1, int(TA / tick) + 1) * tick
                    te = kk / rate
                else:
                    kk = np.arange(1, int(TB / tick) + 1) * tick
                    te = np.interp(kk, TBg, tg)
                for t_e in te[::-1]:
                    rad = 260 * (f.t - t_e) + cr
                    if rad > 900:
                        break
                    aa = max(0.0, 1 - (rad - cr) / 740) ** 1.3
                    rc = colr if T_hist is None else mix(c_, "#ff3b2f", (1 - float(np.interp(t_e, tg, rt))) ** 0.6)
                    f.c.drawCircle(x0, y0, rad, paint(rc, 0.18 * aa, stroke=12, add=True))
                    f.c.drawCircle(x0, y0, rad, paint(rc, 0.7 * aa, stroke=2.5))
                f.c.restore()
            _clock_face(f, ax, ay, cr * (1 + 0.02 * pulse), TA, c_, c_)
            _clock_face(f, bx, by, cr * 0.94, TB, b_col, b_col)
    # labels and readouts
    with shot_camera(f, p, 960, 540, strength=0.18):  # same move as the clocks, so the readouts stay under them
        lx_a, lx_b = 560, 1345
        text(f, p("a_label", "FAR AWAY"), lx_a, 300, size=40, color=INK, weight="bold", glow_color=c_, stroke=5)
        text(f, p("b_label", "NEAR A BLACK HOLE" if mode == "gravity" else "NEAR LIGHT SPEED"), lx_b, 300, size=40,
             color=INK, weight="bold", glow_color=b_col, stroke=5)
        U = unit.upper()
        text(f, f"{TA:,.2f} {U}", lx_a, 712, size=58, color=INK, glow_color=c_, stroke=5)
        text(f, f"{TB:,.2f} {U}", lx_b, 712, size=58, color=INK, glow_color=b_col, stroke=5)
        text(f, "TIME RATE 100%", lx_a, 756, size=32, color=DIM, weight="semibold")
        text(f, f"TIME RATE {r_now * 100:.0f}%", lx_b, 756, size=32, color=b_col if r_now < 0.95 else DIM, weight="semibold")
        sub = f"{aux:.2f}x the horizon distance" if mode == "gravity" else f"speed {aux * 100:.1f}% of light"
        text(f, sub, lx_b, 794, size=30, color=DIM, weight="body")
    _panel(f, 740, SAFE_T, 440, 104, c_)
    text(f, "TIME DIFFERENCE", 960, SAFE_T + 40, size=30, color=DIM, weight="semibold")
    text(f, f"{TA - TB:,.2f} {U}", 960, SAFE_T + 88, size=42, color=INK if TA - TB < 0.05 * rate else GOLD, glow_color=c_)
    flash(f, t_pay, dur=0.45, color="#ffffff", peak=0.6)
    payoff = p("payoff")
    if payoff is None:  # counts on live while it's on screen, so it never disagrees with the clocks
        payoff = f"{max(TA - TB, diff_pay):,.1f} {U} APART"
    if payoff:
        slam_text(f, payoff, 960, 852, t_pay, size=84, glow_color=b_col, hold=2.6)


# ================================================================ 6. Doppler shift

def _wl_rgb(nm):
    """Approximate colour of light of wavelength nm (dim violet/red outside the visible range)."""
    if nm < 380:
        return mix("#3a1a66", "#6a2cff", clamp((nm - 200) / 180))
    if nm > 750:
        return mix("#a01818", "#3a0808", clamp((nm - 750) / 600))
    stops = [(380, "#6a2cff"), (440, "#2a4bff"), (490, "#00c8ff"), (530, "#36ff6a"), (580, "#ffe83a"),
             (620, "#ff8a1a"), (680, "#ff2a1a"), (750, "#a01818")]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if nm <= b:
            return mix(ca, cb, (nm - a) / (b - a))
    return E._rgb("#a01818")


def _spectrum_bar(f, x, y, w, h, value, factor, mode, title, sub_c):
    """A spectrum (light) or pitch (sound) bar with a marker at the received value and shifted absorption lines."""
    if mode == "light":
        lo, hi = 250.0, 1000.0
        samples = np.linspace(lo, hi, 40)
        cols = [col(_wl_rgb(s), 1.0 if 380 <= s <= 750 else 0.55) for s in samples]
        pos = lambda v_: x + w * (v_ - lo) / (hi - lo)  # noqa: E731
    else:
        lo, hi = math.log(110), math.log(3520)
        cols = [col(mix("#2a1466", "#ffd23a", i / 10)) for i in range(11)]
        pos = lambda v_: x + w * (math.log(max(v_, 1)) - lo) / (hi - lo)  # noqa: E731
    rr = skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), 8, 8)
    f.c.drawRRect(rr, skia.Paint(AntiAlias=True, Shader=skia.GradientShader.MakeLinear(
        [skia.Point(x, 0), skia.Point(x + w, 0)], cols)))
    f.c.drawRRect(rr, paint(INK, 0.5, stroke=2))
    if mode == "light":
        f.c.save()
        f.c.clipRRect(rr, doAntiAlias=True)
        for base in (434, 486, 656):  # hydrogen lines, shifted
            lx = pos(base * factor)
            f.c.drawLine(lx, y, lx, y + h, paint("#000000", 0.75, stroke=4))
        f.c.restore()
        for edge in (380, 750):
            f.c.drawLine(pos(edge), y - 6, pos(edge), y + h + 6, paint(INK, 0.7, stroke=2))
        text(f, "UV", (x + pos(380)) / 2, y + h - 6, size=30, color=INK, weight="bold", a=0.8)
        text(f, "IR", (pos(750) + x + w) / 2, y + h - 6, size=30, color=INK, weight="bold", a=0.8)
    vx = pos(value)
    off = vx < x or vx > x + w
    vx = min(max(vx, x), x + w)
    mc = _wl_rgb(value) if mode == "light" else mix("#9b7bff", "#ffd23a", clamp((vx - x) / w))
    soft_light(f, vx, y + h / 2, 60, mc, 0.8)
    f.c.drawLine(vx, y - 14, vx, y + h + 14, paint(INK, 1, stroke=4))
    tri = skia.Path()
    tri.moveTo(vx, y - 8)
    tri.lineTo(vx - 11, y - 26)
    tri.lineTo(vx + 11, y - 26)
    tri.close()
    f.c.drawPath(tri, paint(INK))
    text(f, title, x, y - 40, size=30, color=DIM, align="left", weight="semibold")
    if mode == "light":
        name = "ULTRAVIOLET" if value < 380 else "INFRARED" if value > 750 else ""
        val = f"{value:,.0f} nm" + (f" {name}" if name else "")
    else:
        val = "SHOCK WAVE" if value > 1e6 else f"{value:,.0f} Hz"
    text(f, ("<< " if off and vx <= x else "") + val + (" >>" if off and vx >= x + w else ""), x, y + h + 48, size=36,
         color=sub_c, align="left", weight="bold", stroke=5)


@template("doppler_shift", sfx=lambda p: [
    Sfx("shimmer", 0.3, gain_db=-6), Sfx("whoosh", p("move_at") or 1.0), Sfx("whoosh", p("fast_at") or 2.4, gain_db=2),
    Sfx("riser", p("extreme_at") or "end", offset=-1.4 if p("extreme_at") else -3.2, dur=1.4),
    Sfx("impact", p("extreme_at") or "end", offset=0.0 if p("extreme_at") else -1.8)])
def doppler_shift(f, p):
    """The Doppler effect: a source sends out wave rings; once it moves they bunch up ahead and stretch out behind.
    Two spectrum bars (ahead and behind) show the received light shifting blue and red, with shifted absorption
    lines (or, for sound, the pitch rising and falling). The payoff: the speed goes extreme, the rings pile into a
    wall ahead and the colours slide right off the visible spectrum (sound: it breaks the sound barrier, a Mach cone).
    params: mode (light|sound), move_at (word it starts moving), fast_at (word it speeds up), extreme_at (word it
    goes extreme, the payoff), speed (first speed as a fraction of the wave speed, default 0.3), fast_speed (0.6),
    top_speed (0.9 for light, 1.4 for sound), payoff (slam text, default 'BLUESHIFT' / 'SONIC BOOM', '' for none), color"""
    mode = p("mode", "light")
    c_ = accent(f, p, default=["cyan", "purple", "ice", "pink"])
    t_mv, t_fast, t_ext = _beats(f, p, [("move_at", 0.15), ("fast_at", 0.4), ("extreme_at", 0.66)], gap=1.0)
    b1, b2 = float(p("speed", 0.3)), float(p("fast_speed", 0.6))
    b3 = float(p("top_speed", 0.9 if mode == "light" else 1.4))
    pulse = f.beat_pulse()
    cpx, T0 = 330.0, 0.24
    pre = 9.0  # the source has been sending rings since before the scene started

    def beta(ts):
        return b1 * _sstep(ts, t_mv, 1.2) + (b2 - b1) * _sstep(ts, t_fast, 1.2) + (b3 - b2) * _sstep(ts, t_ext, 1.0)

    tg = np.linspace(-pre, max(f.t, 0) + 1e-3, 900)
    bg = beta(tg)
    xg = np.concatenate([[0], np.cumsum((bg[1:] + bg[:-1]) / 2 * np.diff(tg))]) * cpx
    gam = 1 / np.sqrt(np.clip(1 - bg ** 2, 1e-4, 1)) if mode == "light" else np.ones_like(bg)
    phase = np.concatenate([[0], np.cumsum(((1 / gam)[1:] + (1 / gam)[:-1]) / 2 * np.diff(tg))]) / T0
    b_now = float(bg[-1])
    x_src = float(xg[-1])
    scr_x = 960 - 120 * clamp(b_now)
    sy = 600.0
    if mode == "light":
        fwd = math.sqrt((1 - min(b_now, 0.999)) / (1 + b_now))
        lam0 = 530.0
        ahead, behind = lam0 * fwd, lam0 / fwd
    else:
        f0 = 440.0
        ahead = f0 / (1 - b_now) if b_now < 0.999 else 1e9
        behind = f0 / (1 + b_now)

    # background
    if mode == "light":
        gradient_bg(f)
        nebula_glow(f, alpha=0.3)
        off = -(x_src * 0.12)
        starfield(f, n=380, drift=(off / max(f.t, 1e-3), 0) if f.t > 0 else (0, 0), alpha=0.9)
    else:
        gradient_bg(f, "#101a2e", "#05070d")
        f.c.drawRect(skia.Rect.MakeLTRB(0, 820, W, H), paint("#0a0f18"))
        rng = f.rng("dp_ground")
        gx = (rng.random(40) * W * 2 - (x_src * 0.9) % (W * 2)) % (W * 2) - W / 2
        for x_ in gx.tolist():
            f.c.drawLine(x_, 820, x_ - 40, 860, paint(DIM, 0.25, stroke=2))
        f.c.drawLine(0, 820, W, 820, paint(DIM, 0.6, stroke=2))
    s_ext = f.t - t_ext
    shake = 16 * math.exp(-s_ext * 3) if s_ext > 0 else 0
    with shot_camera(f, p, 960, sy, strength=0.25):
        with camera(f, 960, 540, shake=shake):
            # tint: blue ahead, red behind, stronger with speed
            k = clamp(b_now / max(b3, 0.01))
            mid = mix(c_, INK, 0.45)
            tint = skia.GradientShader.MakeLinear([skia.Point(scr_x - 900, 0), skia.Point(scr_x + 900, 0)],
                                                  [col(mix(mid, "#ff3a2a", k)), col(mix(mid, "#ff7a5a", k * 0.7)), col(mid),
                                                   col(mix(mid, "#5a9bff", k * 0.7)), col(mix(mid, "#3a5bff", k))],
                                                  [0, 0.3, 0.5, 0.7, 1])
            if mode == "sound":
                tint = skia.GradientShader.MakeLinear([skia.Point(scr_x - 1000, 0), skia.Point(scr_x + 1000, 0)],
                                                      [col("#9b7bff"), col(c_), col("#ffd23a")])
            glow_p = skia.Paint(AntiAlias=True, Shader=tint, Style=skia.Paint.kStroke_Style, StrokeWidth=14,
                                BlendMode=skia.BlendMode.kPlus)
            core_p = skia.Paint(AntiAlias=True, Shader=tint, Style=skia.Paint.kStroke_Style, StrokeWidth=3)
            ks = np.arange(1, int(phase[-1]) + 1)
            te = np.interp(ks, phase, tg)
            xe = np.interp(te, tg, xg)
            for t_e, x_e in zip(te[::-1].tolist(), xe[::-1].tolist()):
                rad = cpx * (f.t - t_e)
                if rad > 2600:
                    break
                cx_ = x_e - x_src + scr_x
                aa = clamp(1.25 - rad / 1900) * (0.85 + 0.15 * pulse)
                glow_p.setAlphaf(0.16 * aa * (0.6 + 0.4 * k))
                core_p.setAlphaf(0.85 * aa)
                f.c.drawCircle(cx_, sy, rad, glow_p)
                f.c.drawCircle(cx_, sy, rad, core_p)
            if mode == "sound" and b_now > 1:
                half = math.asin(1 / b_now)
                for sg in (-1, 1):
                    ex_, ey_ = scr_x - math.cos(half) * 1800, sy + sg * math.sin(half) * 1800
                    f.c.drawLine(scr_x, sy, ex_, ey_, paint(INK, 0.8, stroke=4))
                    f.c.drawLine(scr_x, sy, ex_, ey_, paint(GOLD, 0.3, stroke=22, add=True))
            # the source, with a little flash each time it emits
            since = (phase[-1] % 1) * T0
            src_c = "#fff1c8" if mode == "light" else c_
            if b_now > 0.02:
                tr = [(scr_x - (x_src - float(np.interp(f.t - j * 0.05, tg, xg))), sy) for j in range(14, -1, -1)]
                trail(f, tr, color=c_, width=6, a=clamp(b_now * 2))
            soft_light(f, scr_x, sy, 160 * (1 + 0.2 * pulse), src_c, 0.35)
            body(f, "sun" if mode == "light" else "white_dwarf", scr_x, sy, 30 * (1 + 0.06 * pulse))
            ring(f, scr_x, sy, 30 + since * 120, 6, INK, 0.7 * (1 - since / T0))
            if b_now > 0.05:
                _arrow(f, scr_x + 46, sy, scr_x + 46 + 60 + 120 * clamp(b_now), sy, INK, width=5, a=0.9)
            if s_ext > 0:
                shockwave(f, scr_x, sy, t_ext, speed=1300, life=1.4, color=c_, width=24)
            if b_now > 0.1:
                lam_a = cpx * T0 * (1 - min(b_now, 1)) * (float(gam[-1]) if mode == "light" else 1)
                label(f, "squashed", scr_x + 40 + lam_a * 0.5 + 30, sy - 8, scr_x + 300, sy - 170, t_mv + 0.6, size=36,
                      color="#9fc0ff" if mode == "light" else GOLD, line_color=INK)
                label(f, "stretched", scr_x - 160, sy + 10, scr_x - 360, sy + 180, t_mv + 1.0, size=36,
                      color="#ff9a8a" if mode == "light" else "#b9a6ff", line_color=INK)

    # observers at the edges, fixed to the screen (outside the camera moves)
    for ox_, val, lab in ((SAFE_L + 40, behind, "BEHIND"), (SAFE_R - 40, ahead, "AHEAD")):
        oc = _wl_rgb(val) if mode == "light" else (mix("#9b7bff", "#ffd23a", clamp(math.log(max(val, 1) / 110) / 3.5)))
        soft_light(f, ox_, sy, 90, oc, 0.75 + 0.2 * pulse)
        f.c.drawCircle(ox_, sy, 24, paint("#05070d"))
        f.c.drawCircle(ox_, sy, 24, paint(oc, 1, stroke=5))
        f.c.drawCircle(ox_, sy, 9, paint(oc))
        text(f, lab, ox_, sy + 78, size=30, color=INK, weight="bold", stroke=5)
    # HUD: spectrum (or pitch) bars and speed
    title = "LIGHT RECEIVED" if mode == "light" else "PITCH HEARD"
    _spectrum_bar(f, SAFE_L + 20, SAFE_T + 60, 700, 36, behind, (behind / 530 if mode == "light" else 1), mode, f"BEHIND: {title}",
                  "#ff8a7a" if mode == "light" else "#b9a6ff")
    _spectrum_bar(f, SAFE_R - 720, SAFE_T + 60, 700, 36, ahead, (ahead / 530 if mode == "light" else 1), mode, f"AHEAD: {title}",
                  "#9fc0ff" if mode == "light" else GOLD)
    _panel(f, 760, 300, 400, 120, c_)
    text(f, "SOURCE SPEED", 960, 344, size=30, color=DIM, weight="semibold")
    sp_txt = f"{b_now:.2f} c" if mode == "light" else f"MACH {b_now:.2f}"
    text(f, sp_txt, 960, 400, size=50, color=INK, glow_color=c_ if b_now < 0.85 * b3 else RED)
    _note(f, "colour at rest: green, 530 nm" if mode == "light" else "pitch at rest: 440 Hz", x=SAFE_L, y=SAFE_B, align="left")
    flash(f, t_ext, dur=0.45, color="#e8f0ff", peak=0.55)
    payoff = p("payoff")
    if payoff is None:
        payoff = "BLUESHIFT" if mode == "light" else ("SONIC BOOM" if b3 >= 1 else "HIGHER PITCH")
    if payoff:
        slam_text(f, payoff, 960, 812, t_ext + 0.1, size=104, glow_color=c_, hold=2.6)
