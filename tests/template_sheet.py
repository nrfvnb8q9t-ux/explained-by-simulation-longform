"""Render every scene template at three moments into contact sheets, to check they all work and look right.

    uv run python tests/template_sheet.py build/template-sheets [template_name ...]
"""

import sys
import time
import traceback
from pathlib import Path

import numpy as np
import skia
from PIL import Image

from esim import engine
from esim.templates import TEMPLATES, run_shot

DUR = 6.0
TIMES = (1.2, 3.4, 5.4)
THUMB = (480, 270)
PER_SHEET = 8


def frame(name, t, seed):
    arr = np.zeros((engine.H, engine.W, 4), np.uint8)
    surf = skia.Surface(arr, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
    c = surf.getCanvas()
    c.clear(skia.ColorBLACK)
    beats = [(round(b * 0.46, 3), 1.0 if i % 4 == 0 else 0.5) for i, b in enumerate(range(14))]
    f = engine.Frame(c=c, t=t, dur=DUR, index=int(t * 30), seed=seed, scene_id=name, words=[], beats=beats)
    run_shot(f, {"template": name, "params": {}})
    return Image.fromarray(arr[..., :3]).resize(THUMB, Image.LANCZOS)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/template-sheets")
    out.mkdir(parents=True, exist_ok=True)
    names = sys.argv[2:] or sorted(TEMPLATES)
    rows, failures, timings = [], [], {}
    for name in names:
        row = Image.new("RGB", (THUMB[0] * 3, THUMB[1] + 30), (20, 20, 20))
        t0 = time.time()
        try:
            for i, t in enumerate(TIMES):
                row.paste(frame(name, t, seed=1234), (i * THUMB[0], 30))
        except Exception:
            failures.append((name, traceback.format_exc()))
            continue
        timings[name] = (time.time() - t0) / len(TIMES) * 1000
        from PIL import ImageDraw
        ImageDraw.Draw(row).text((8, 6), f"{name}  ({timings[name]:.0f} ms/frame)", fill=(255, 255, 255))
        rows.append(row)
    for s in range(0, len(rows), PER_SHEET):
        chunk = rows[s:s + PER_SHEET]
        sheet = Image.new("RGB", (THUMB[0] * 3, (THUMB[1] + 30) * len(chunk)))
        for i, r in enumerate(chunk):
            sheet.paste(r, (0, i * (THUMB[1] + 30)))
        sheet.save(out / f"sheet-{s // PER_SHEET + 1}.png")
    print(f"{len(rows)} templates rendered, {len(failures)} failed")
    slow = sorted(timings.items(), key=lambda kv: -kv[1])[:6]
    print("slowest:", ", ".join(f"{n} {ms:.0f}ms" for n, ms in slow))
    for name, tb in failures:
        print(f"\n--- {name} ---\n{tb[-1500:]}")


if __name__ == "__main__":
    main()
