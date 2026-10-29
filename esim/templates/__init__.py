"""Scene templates: ready-made, randomised scene types that a script picks and fills in.

A scene in script.json can carry a "shot" instead of custom code:

    "shot": {
      "template": "impact",
      "params": {"target": "earth", "at": "hits"},
      "slam": {"text": "BOOM", "at": "hits"},
      "cards": [{"title": "20 km/s", "sub": "impact speed", "at": "twenty"}],
      "note": "not to scale",
      "sfx": [{"kind": "808", "at": "hits"}],
      "edit": "auto"
    }

Anything a template isn't told, it picks at random from this video's seed (layout, colours, camera
move, effect styles), so the same template never looks the same twice. Words in "at" fields must be in
the scene's narration; the render fails loudly if they aren't.

    uv run python -m esim.templates           # prints the reference of every template and its params
"""

import math
from contextlib import contextmanager

import numpy as np

from esim.engine import *  # noqa: F401,F403
from esim import engine as E

TEMPLATES = {}

ACCENTS = {"cyan": CYAN, "gold": GOLD, "red": RED, "green": GREEN, "purple": "#9b7bff", "pink": "#ff5ad1",
           "orange": "#ff8a3d", "white": INK, "ice": "#9fe6ff"}
CAMERAS = ["push_in", "pull_out", "pan_left", "pan_right", "drift", "orbit", "rise", "static"]

# friendly body names -> how to draw them
BODY_KINDS = {
    "earth": ("earth", None), "frozen_earth": ("frozen_earth", None), "moon": ("rocky", None),
    "mercury": ("rocky", "#d9c9b8"), "venus": ("gas", "#ffe2a8"), "mars": ("mars", None),
    "jupiter": ("gas", None), "saturn": ("gas", "#ffe9c2"), "uranus": ("ice", "#c6fbff"),
    "neptune": ("ice", "#7fa4ff"), "pluto": ("ice", "#f1dccb"), "rocky": ("rocky", None), "gas": ("gas", None),
    "ice": ("ice", None), "lava": ("lava", None), "asteroid": ("rocky", "#b9ab9c"), "star": ("star", None),
    "sun": ("sun", None), "black_hole": ("black_hole", None), "red_giant": ("sun", "#ff6a3d"),
    "white_dwarf": ("sun", "#e8f4ff"), "neutron_star": ("sun", "#bfe3ff"),
}


def template(name, sfx=None, kind="space"):
    """Register a template. `sfx(p)` returns default sound effects for a filled-in shot."""
    def deco(fn):
        TEMPLATES[name] = {"fn": fn, "sfx": sfx or (lambda p: []), "doc": (fn.__doc__ or "").strip(), "kind": kind}
        return fn
    return deco


class P(dict):
    """Template params with defaults: p("size", 300)."""
    def __call__(self, key, default=None):
        v = self.get(key)
        return default if v is None else v


# ---------------------------------------------------------------- shared helpers

def pick(f, key, options):
    """A choice that's random per video and scene, and identical on every frame."""
    rng = f.rng(f"pick:{key}")
    return options[int(rng.integers(0, len(options)))]


def rand(f, key, lo, hi):
    return float(lo + (hi - lo) * f.rng(f"rand:{key}").random())


def accent(f, p, key="accent", default=None):
    name = p(key)
    if name:
        return ACCENTS.get(name, name)
    return ACCENTS[pick(f, key, default or ["cyan", "gold", "pink", "purple", "green", "orange"])]


def when(f, at, frac=0.5):
    """Seconds into the scene for `at` (a word or seconds), or a fraction of the scene if not given."""
    return f.time(at) if at is not None else f.dur * frac


@contextmanager
def shot_camera(f, p, cx=W / 2, cy=H / 2, strength=1.0):
    """The camera move for a shot: p("camera") or a random one."""
    kind = p("camera") or pick(f, "camera", CAMERAS)
    k = ease_in_out(f.p)
    s = strength
    zoom, rot, x, y = 1.0, 0.0, cx, cy
    if kind == "push_in":
        zoom = lerp(1.0, 1.0 + 0.28 * s, k)
    elif kind == "pull_out":
        zoom = lerp(1.0 + 0.3 * s, 1.0, k)
    elif kind == "pan_left":
        x = cx + lerp(160, -160, k) * s
        zoom = 1.08
    elif kind == "pan_right":
        x = cx + lerp(-160, 160, k) * s
        zoom = 1.08
    elif kind == "rise":
        y = cy + lerp(120, -60, k) * s
        zoom = 1.06
    elif kind == "orbit":
        rot = lerp(-4, 4, k) * s
        zoom = lerp(1.05, 1.15, k)
    elif kind == "drift":
        x = cx + 40 * math.sin(f.t * 0.3) * s
        y = cy + 25 * math.cos(f.t * 0.23) * s
        zoom = 1.04 + 0.03 * math.sin(f.t * 0.2)
    with camera(f, x, y, zoom=zoom, rotate=rot):
        yield


def body(f, kind, x, y, r, rotation=None, light=(-0.7, -0.25, 0.65), seed_key=None, alpha=1.0, **kw):
    """Draw any named body: planets, moons, stars, the Sun or a black hole."""
    style, tint = BODY_KINDS.get(kind, (kind if kind in PLANET_STYLES else "rocky", None))
    tint = kw.pop("tint", None) or tint
    rotation = f.t * 0.015 if rotation is None else rotation
    if style == "sun":
        if tint:
            soft_light(f, x, y, r * 3.2, tint, 0.35 * alpha)
            planet(f, "star", x, y, r, rotation=rotation, atmosphere=False, tint=tint, alpha=alpha)
            halo(f, x, y, r * 0.97, r * 1.3, tint, 0.5 * alpha)
        else:
            sun(f, x, y, r, intensity=alpha, rotation=rotation)
    elif style == "black_hole":
        draw_black_hole(f, x, y, r, alpha=alpha)
    else:
        planet(f, style, x, y, r, rotation=rotation, light=light, tint=tint, seed_key=seed_key or kind,
               alpha=alpha, **kw)


def draw_black_hole(f, x, y, r, spin=1.0, alpha=1.0, tilt=0.28, color=GOLD):
    """An accretion disk, photon ring and shadow. r is the shadow's radius."""
    c = f.c
    rng = f.rng("bh-disk")
    n = 700
    rad = r * (1.6 + 2.6 * rng.random(n) ** 1.4)
    ang0 = rng.random(n) * 2 * math.pi
    speed = 1.6 * spin * (r * 1.6 / rad) ** 1.5
    ang = ang0 + f.t * speed
    xs = x + np.cos(ang) * rad
    ys = y + np.sin(ang) * rad * tilt
    heat = np.clip(1.4 - (rad - r * 1.6) / (r * 2.6), 0.2, 1)
    front = np.sin(ang) > 0
    soft_light(f, x, y, r * 5, color, 0.25 * alpha)
    # back half of the disk (seen above the shadow, lensed)
    for sel in (~front,):
        dots(f, xs[sel], ys[sel], 1.2 + heat[sel] * 2.2, heat[sel] * 0.8 * alpha, color, add=True)
    # lensed arc over the top
    c.drawCircle(x, y, r * 1.35, paint(color, 0.35 * alpha, stroke=r * 0.18, add=True))
    c.drawCircle(x, y, r * 1.06, paint("#000000", alpha))
    ring(f, x, y, r * 1.08, r * 0.08, "#fff1d6", 0.9 * alpha)
    dots(f, xs[front], ys[front], 1.2 + heat[front] * 2.2, heat[front] * alpha, color, add=True)
    dots(f, xs[front], ys[front], 0.6 + heat[front], heat[front] * alpha, "#ffffff", add=True)


def overlays(f, shot):
    """The extras any shot can have: fact cards, a slam-text punchline, a note."""
    for card in shot.get("cards", []):
        caption_card(f, card["title"], card.get("sub", ""), card["at"], hold=card.get("hold"),
                     x=W * card.get("x", 0.5), y=H * card.get("y", 0.74),
                     color=ACCENTS.get(card.get("color", "cyan"), card.get("color", CYAN)))
    slam = shot.get("slam")
    if slam:
        slam_text(f, slam["text"], W * slam.get("x", 0.5), H * slam.get("y", 0.5), slam["at"],
                  size=slam.get("size", 170), hold=slam.get("hold", 1.6),
                  glow_color=ACCENTS.get(slam.get("color", "red"), slam.get("color", RED)))
    if shot.get("note"):
        text(f, shot["note"], 40, H - 36, size=26, color=DIM, align="left", weight="body", a=0.8)


def run_shot(f, shot):
    tpl = TEMPLATES.get(shot["template"])
    if not tpl:
        raise ValueError(f"Unknown template '{shot['template']}'. Run `uv run python -m esim.templates` for the list.")
    tpl["fn"](f, P(shot.get("params", {})))
    overlays(f, shot)
    if tpl["kind"] != "board":
        vignette(f, 0.5)


def shot_sfx(shot):
    tpl = TEMPLATES[shot["template"]]
    out = list(tpl["sfx"](P(shot.get("params", {}))))
    if shot.get("slam"):
        out.append(Sfx("808", shot["slam"]["at"]))
    for card in shot.get("cards", []):
        out.append(Sfx("pop", card["at"]))
    for s in shot.get("sfx", []):
        out.append(Sfx(s["kind"], s.get("at", "start"), s.get("offset", 0.0), s.get("dur"), s.get("gain_db", 0.0)))
    return out


def reference():
    """Markdown reference of every template, from the docstrings."""
    groups = {}
    for name, t in TEMPLATES.items():
        groups.setdefault(t["kind"], []).append((name, t["doc"]))
    out = []
    for kind in ("space", "board", "data", "cinematic"):
        out.append(f"\n## {kind.title()} templates\n")
        for name, doc in sorted(groups.get(kind, [])):
            out.append(f"### `{name}`\n{doc}\n")
    return "\n".join(out)


# Register the templates. importlib, because a plain `from esim.templates import space` would find the
# engine's space() drawing function (star-imported above) instead of the space.py module.
import importlib  # noqa: E402

for _mod in ("space", "board", "data", "cinematic"):
    importlib.import_module(f"esim.templates.{_mod}")
space = E.space  # keep the drawing function under its usual name
