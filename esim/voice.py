"""Narration with Kokoro, a free text-to-speech model that runs offline after its first download.

Returns the audio plus the start and end time of every word, so animations and sound effects can
land exactly on the word they belong to.
"""

import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np

KOKORO_SR = 24000
VOICES = ["af_heart", "am_puck", "am_michael"]  # the narrators the channel uses
DEFAULT_VOICE = os.environ.get("ESIM_VOICE", "am_puck")
CACHE_VERSION = "v4"
_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        import warnings
        warnings.filterwarnings("ignore")
        from kokoro import KPipeline
        _pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    return _pipeline


def synth(text, cache_dir, voice=DEFAULT_VOICE, speed=1.0):
    """Speak `text`. Returns (audio float32 at 24 kHz, [(word, start_sec, end_sec), ...]).
    Results are cached by text, so re-rendering a video doesn't re-record unchanged lines."""
    text = re.sub(r"\s*\[pause[^\]]*\]\s*", " ", text).strip()  # old scripts may still have pause markers
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{CACHE_VERSION}|{voice}|{speed}|{text}".encode()).hexdigest()[:16]
    wav_path, words_path = cache_dir / f"{key}.npy", cache_dir / f"{key}.json"
    if wav_path.exists() and words_path.exists():
        return np.load(wav_path), [tuple(w) for w in json.loads(words_path.read_text())]

    pipe = _get_pipeline()
    chunks, words, offset = [], [], 0.0
    for result in pipe(text, voice=voice, speed=speed):
        audio = result.audio.numpy().astype(np.float32)
        for tok in result.tokens or []:
            if not any(ch.isalnum() for ch in tok.text):
                if words and tok.text.strip():  # keep punctuation on the word before it, for captions
                    w, s, e = words[-1]
                    words[-1] = (w + tok.text.strip(), s, e)
                continue
            if tok.start_ts is not None:
                words.append((tok.text, offset + float(tok.start_ts), offset + float(tok.end_ts or tok.start_ts)))
        chunks.append(audio)
        offset += len(audio) / KOKORO_SR
    audio = np.concatenate(chunks) if chunks else np.zeros(1, np.float32)
    np.save(wav_path, audio)
    words_path.write_text(json.dumps(words))
    return audio, words
