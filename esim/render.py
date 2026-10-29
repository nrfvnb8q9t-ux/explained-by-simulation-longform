"""Render a video folder into a finished, upload-ready video.

    uv run python -m esim.render videos/<slug>               # full 1080p render
    uv run python -m esim.render videos/<slug> --preview     # quick half-size, 15 fps check
    uv run python -m esim.render videos/<slug> --scenes 3,4  # only some scenes (for fixing one)

A video folder holds:
    script.json   what's said, scene by scene (written by the yt-script skill)
    scenes.py     how each scene looks and sounds, one @scene function per script scene

Output goes to build/<slug>/: video.mp4, thumbnail.jpg, captions.srt and meta.json.
"""

import argparse
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import skia
import soundfile as sf

from esim import audio, engine, music, unique, voice

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def load_scenes(video_dir):
    """Every scene's drawing function: custom @scene code from scenes.py (the hero moments) where there is
    some, otherwise the scene's template "shot" from script.json."""
    from esim import templates
    video_dir = Path(video_dir)
    engine.SCENES.clear()
    path = video_dir / "scenes.py"
    if path.exists():
        spec = importlib.util.spec_from_file_location(f"scenes_{video_dir.name.replace('-', '_')}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    scenes = dict(engine.SCENES)
    script = json.loads((video_dir / "script.json").read_text())
    for s in script["long"]["scenes"]:
        shot = s.get("shot")
        if s["id"] in scenes or not shot:
            continue
        if shot.get("template") not in templates.TEMPLATES:
            raise ValueError(f"Scene {s['id']}: unknown template '{shot.get('template')}'")
        scenes[s["id"]] = {"fn": (lambda sh: (lambda f: templates.run_shot(f, sh)))(shot),
                           "sfx": templates.shot_sfx(shot), "hold": shot.get("hold", 0.6),
                           "lead": shot.get("lead", 0.35), "edit": shot.get("edit", "auto")}
    return scenes


def _surface(w, h):
    arr = np.zeros((h, w, 4), np.uint8)
    surf = skia.Surface(arr, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
    return arr, surf


# automatic beat-synced editing: (zoom punch per beat, weakest beat that punches, flash on bar lines)
EDIT_LEVELS = {"hype": (0.035, 0.0, 0.07), "mid": (0.016, 1.0, 0.0), "calm": (0.0, 1.0, 0.0)}


def edit_level(edit, intensity):
    if edit in EDIT_LEVELS:
        return edit
    return "hype" if intensity >= 0.6 else "mid" if intensity >= 0.35 else "calm"


def draw_frame(fn, canvas, t, dur, index, seed, scene_id, words, scale, fps,
               beats=(), drops=(), intensity=0.4, edit="calm"):
    """Draw one frame, then the automatic edit layer: zoom punches on the beat, and on a music drop a
    flash, a camera shake and a zoom slam. Returns how much RGB split to apply (0..1)."""
    f = engine.Frame(c=canvas, t=t, dur=dur, index=index, seed=seed, scene_id=scene_id, words=words, fps=fps,
                     beats=list(beats), drops=list(drops), intensity=intensity)
    punch, min_strength, bar_flash = EDIT_LEVELS[edit_level(edit, intensity)]
    zoom = 1 + punch * f.beat_pulse(decay=11, min_strength=min_strength)
    flash = bar_flash * f.beat_pulse(decay=14, min_strength=1.0)
    sx = sy = split = 0.0
    since = f.since_drop()
    if since is not None and since < 0.9 and edit_level(edit, intensity) != "calm":
        k = math.exp(-since * 5)
        zoom += 0.08 * k
        shake = 18 * math.exp(-since * 4)
        sx, sy = shake * math.sin(since * 61), shake * math.cos(since * 47)
        flash = max(flash, 0.7 * math.exp(-since * 8))
        split = k
    canvas.save()
    canvas.clear(skia.ColorBLACK)
    if scale != 1:
        canvas.scale(scale, scale)
    if zoom != 1 or sx:
        canvas.translate(engine.W / 2 + sx, engine.H / 2 + sy)
        canvas.scale(zoom, zoom)
        canvas.translate(-engine.W / 2, -engine.H / 2)
    fn(f)
    canvas.restore()
    if flash > 0.005:
        canvas.drawPaint(skia.Paint(Color=skia.Color4f(1, 1, 1, min(flash, 1)).toColor()))
    return split


def rgb_split(arr, amount, scale):
    """Chromatic aberration: push the red and blue channels apart, the classic edit 'hit' look."""
    k = max(1, int(16 * amount * scale))
    arr[..., 0] = np.roll(arr[..., 0], k, axis=1)
    arr[..., 2] = np.roll(arr[..., 2], -k, axis=1)


def render_scene(job):
    """Worker: render one scene to its own mp4 segment. Runs in a separate process."""
    video_dir, scene_id, dur, words, seed, out_path, scale, fps, preset, beats, drops, intensity = job
    scenes = load_scenes(video_dir)
    fn, edit = scenes[scene_id]["fn"], scenes[scene_id]["edit"]
    w, h = int(engine.W * scale), int(engine.H * scale)
    arr, surf = _surface(w, h)
    canvas = surf.getCanvas()
    n_frames = max(1, int(round(dur * fps)))
    cmd = [FFMPEG, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", preset, "-crf", "19",
           "-pix_fmt", "yuv420p", "-g", str(fps * 2), str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n_frames):
            try:
                split = draw_frame(fn, canvas, i / fps, dur, i, seed, scene_id, words, scale, fps,
                                   beats, drops, intensity, edit)
            except Exception:
                raise RuntimeError(f"Scene {scene_id} crashed at t={i / fps:.2f}s:\n{traceback.format_exc()}")
            if split > 0.05:
                rgb_split(arr, split, scale)
            proc.stdin.write(arr.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    return scene_id, n_frames


def to_srt(words, path, max_words=8, max_gap=0.6):
    """Captions from the narration's word timings: short lines that break at pauses."""
    def ts(sec):
        ms = int(round(sec * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    lines, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w[1] - cur[-1][2] > max_gap or cur[-1][0][-1:] in ".?!"):
            lines.append(cur)
            cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    out = []
    for i, ln in enumerate(lines, 1):
        end = ln[-1][2] + 0.15
        if i < len(lines):
            end = min(end, lines[i][0][1] - 0.01)  # never overlap the next line
        out.append(f"{i}\n{ts(ln[0][1])} --> {ts(end)}\n{' '.join(w[0] for w in ln)}\n")
    Path(path).write_text("\n".join(out))


def fmt_time(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec // 60 % 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def render_thumbnail(video_dir, scenes, spec, timeline, seed, out_path):
    """The thumbnail is a frame from this video's own animation, with big text on top."""
    th = spec.get("thumbnail", {})
    scene_id = th.get("scene", timeline[0]["id"])
    item = next(s for s in timeline if s["id"] == scene_id)
    if "word" in th:  # e.g. {"word": "gone", "offset": -0.5}
        probe = engine.Frame(c=None, t=0, dur=item["dur"], index=0, seed=seed, scene_id=scene_id, words=item["words"])
        t = probe.word(th["word"]) + float(th.get("offset", 0))
    else:
        t = float(th.get("time", item["dur"] * 0.5))
    t = engine.clamp(t, 0, item["dur"] - 0.01)
    arr, surf = _surface(engine.W, engine.H)
    c = surf.getCanvas()
    draw_frame(scenes[scene_id]["fn"], c, t, item["dur"], int(t * engine.FPS), seed, scene_id, item["words"], 1, engine.FPS)
    f = engine.Frame(c=c, t=t, dur=item["dur"], index=0, seed=seed, scene_id="thumb")
    words = th.get("text", "")
    if words:
        size = 190 if len(words) <= 10 else 150
        engine.text(f, words.upper(), engine.W * th.get("x", 0.5), engine.H * th.get("y", 0.86), size=size,
                    color=th.get("color", engine.INK), stroke=26, glow_color=th.get("glow", engine.GOLD))
    from PIL import Image
    img = Image.fromarray(arr[..., :3]).resize((1280, 720), Image.LANCZOS)
    img.save(out_path, quality=92)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video_dir")
    ap.add_argument("--preview", action="store_true", help="half size, 15 fps, fast encode")
    ap.add_argument("--scenes", help="comma-separated scene ids to render (skips audio and checks)")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--skip-unique", action="store_true")
    ap.add_argument("--synth-music", action="store_true", help="tests only: generated music instead of the library")
    args = ap.parse_args()
    if args.synth_music and not args.preview:
        sys.exit("--synth-music is for previews only. Real videos always use tracks from the music library.")

    video_dir = Path(args.video_dir).resolve()
    script = json.loads((video_dir / "script.json").read_text())
    spec = script["long"]
    slug = script["slug"]
    seed = engine.stable_seed(slug, script.get("seed_salt", ""))
    out_dir = ROOT / "build" / slug
    seg_dir = out_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    scale, fps, preset = (0.5, 15, "ultrafast") if args.preview else (1.0, engine.FPS, "veryfast")
    t_start = time.time()

    scenes = load_scenes(video_dir)
    missing = [s["id"] for s in spec["scenes"] if s["id"] not in scenes]
    if missing:
        sys.exit(f"Scene(s) {missing} have neither a \"shot\" in script.json nor an @scene function in scenes.py")

    # 1. narration, which sets every scene's length
    print(f"[1/5] Narration for {len(spec['scenes'])} scenes...", flush=True)
    timeline, cursor = [], 0.0
    for s in spec["scenes"]:
        reg = scenes[s["id"]]
        clip, words = voice.synth(s["narration"], ROOT / "build" / "cache" / "voice",
                                  voice=script.get("voice", voice.DEFAULT_VOICE), speed=script.get("speed", 1.0))
        lead, hold = reg["lead"], reg["hold"]
        dur = lead + len(clip) / voice.KOKORO_SR + hold
        scene_words = [(w, a + lead, b + lead) for w, a, b in words]
        drop_at = lead
        if s.get("drop"):  # the word the music's drop should land on
            probe = engine.Frame(c=None, t=0, dur=dur, index=0, seed=seed, scene_id=s["id"], words=scene_words)
            drop_at = probe.word(s["drop"])
        timeline.append({"id": s["id"], "start": cursor, "dur": dur, "lead": lead, "clip": clip,
                         "words": scene_words, "mood": s.get("mood", "wonder"),
                         "intensity": s.get("intensity", 0.4), "chapter": s.get("chapter"), "drop_at": drop_at})
        cursor += dur
    total = cursor
    print(f"      total length {fmt_time(total)}", flush=True)

    # 1b. soundtrack from the music library, which gives every scene its beats and drops
    placements, beats, drops, usage = None, [], [], None
    if not args.synth_music:
        placements, beats, drops, usage = music.plan_soundtrack(
            timeline, total, np.random.default_rng(engine.stable_seed(seed, "music")))
        print(f"      soundtrack: {len(placements)} track section(s), {len(drops)} drop(s)", flush=True)

    def local(it):
        a, b = it["start"], it["start"] + it["dur"]
        return ([(round(t - a, 3), s) for t, s in beats if a - 0.5 <= t <= b],
                [round(d - a, 3) for d in drops if a - 0.9 <= d <= b])

    # 2. frames, scenes in parallel
    only = {int(x) if x.isdigit() else x for x in args.scenes.split(",")} if args.scenes else None
    jobs = [(str(video_dir), it["id"], it["dur"], it["words"], seed, str(seg_dir / f"{i:03d}.mp4"), scale, fps, preset,
             *local(it), it["intensity"])
            for i, it in enumerate(timeline) if not only or it["id"] in only]
    print(f"[2/5] Rendering {len(jobs)} scenes on {args.workers} cores...", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=get_context("spawn")) as pool:
        futures = [pool.submit(render_scene, j) for j in jobs]
        for fut in as_completed(futures):
            sid, n = fut.result()
            print(f"      scene {sid}: {n} frames", flush=True)
    if only:
        print(f"Rendered scenes {sorted(only, key=str)} into {seg_dir}")
        return

    # 3. sound: voice, effects and music
    print("[3/5] Sound effects, music and mix...", flush=True)
    from scipy.signal import resample_poly
    voice_clips = [(it["start"] + it["lead"], resample_poly(it["clip"], 2, 1).astype(np.float32)) for it in timeline]
    events = []
    for it in timeline:
        f = engine.Frame(c=None, t=0, dur=it["dur"], index=0, seed=seed, scene_id=it["id"], words=it["words"])
        for k, sfx in enumerate(scenes[it["id"]]["sfx"]):
            rng = np.random.default_rng(engine.stable_seed(seed, it["id"], "sfx", k))
            clip = audio.make_sfx(sfx.kind, rng, sfx.dur)
            gain = audio.SFX_GAIN_DB.get(sfx.kind, -16) + sfx.gain_db
            events.append((it["start"] + f.time(sfx.at) + sfx.offset, clip, gain))
    if placements:
        bed = music.build_bed(placements, total, audio.SR)
        master = audio.mix(total, voice_clips, events, bed, np.random.default_rng(seed), music_db=-20, duck_depth=0.62)
    else:  # --synth-music: generated ambient score, for tests only
        moods = [(it["start"], it["mood"], it["intensity"]) for it in timeline]
        bed = audio.score(np.random.default_rng(engine.stable_seed(seed, "music")), total, moods)
        master = audio.mix(total, voice_clips, events, bed, np.random.default_rng(seed))
    wav = out_dir / "audio.wav"
    sf.write(wav, master, audio.SR, subtype="PCM_24")

    # 4. join scenes and add sound
    print("[4/5] Joining scenes...", flush=True)
    listing = out_dir / "segments.txt"
    listing.write_text("".join(f"file '{seg_dir / f'{i:03d}.mp4'}'\n" for i in range(len(timeline))))
    silent = out_dir / "video_silent.mp4"
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", str(silent)], check=True)
    final = out_dir / "video.mp4"
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", str(silent), "-i", str(wav), "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(final)], check=True)
    silent.unlink()

    # 5. captions, thumbnail, metadata, uniqueness
    print("[5/5] Captions, thumbnail, description and uniqueness check...", flush=True)
    all_words = [(w, it["start"] + a, it["start"] + b) for it in timeline for w, a, b in it["words"]]
    to_srt(all_words, out_dir / "captions.srt")
    render_thumbnail(video_dir, scenes, spec, timeline, seed, out_dir / "thumbnail.jpg")
    chapters = [(it["start"], it["chapter"]) for it in timeline if it["chapter"]]
    if chapters and chapters[0][0] > 0:
        chapters.insert(0, (0.0, "Intro"))
    desc = spec.get("description", "").strip()
    if len(chapters) >= 3:  # YouTube needs at least 3 chapters starting at 0:00
        desc += "\n\nChapters\n" + "\n".join(f"{fmt_time(s)} {name}" for s, name in chapters)
    if script.get("sources"):
        desc += "\n\nSources\n" + "\n".join(f"- {s['claim']}: {s['url']}" for s in script["sources"])
    tracks = list(dict.fromkeys(pl["title"] for pl in placements or []))
    credits = {t["title"]: t.get("credit") for t in music.load_library()["tracks"]} if placements else {}
    needed = [credits[t] for t in tracks if credits.get(t)]
    if needed:  # only tracks the Audio Library marks "attribution required"
        desc += "\n\nMusic\n" + "\n".join(needed)
    desc += "\n\nAnimations are simulations and illustrations made for this video, not real footage."
    meta = {"slug": slug, "title": spec["titles"][0], "description": desc, "tags": spec.get("tags", []),
            "duration": round(total, 2), "ai_disclosure": script.get("ai_disclosure", True), "music": tracks,
            "video": str(final), "thumbnail": str(out_dir / "thumbnail.jpg"), "captions": str(out_dir / "captions.srt")}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    if usage is not None and not args.preview:
        music.record_usage(usage)

    if not args.skip_unique and not args.preview:
        hashes = unique.fingerprints(final)
        ok, report = unique.check(slug, hashes, ROOT / "data" / "fingerprints.json")
        print(f"      uniqueness: {'PASS' if ok else 'FAIL'}, {report}")
        if not ok:
            sys.exit("Blocked: this video is too similar to an earlier one. Change the scenes and re-render.")
        unique.record(slug, hashes, ROOT / "data" / "fingerprints.json")
    shutil.rmtree(seg_dir, ignore_errors=True)
    print(f"Done in {time.time() - t_start:.0f}s: {final} ({fmt_time(total)})")


if __name__ == "__main__":
    main()
