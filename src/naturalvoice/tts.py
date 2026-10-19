"""Text-to-speech that sounds human: free offline Kokoro by default, optional paid engines.

Natural-ness tricks on top of the raw model:
* speaks sentence by sentence with tiny speed variation (people don't talk at one fixed rate),
* inserts real-length pauses for commas, sentence ends and paragraphs,
* runs the 'light' humanize chain to remove vocoder metallic tone and add room tone.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import humanize as hz

MODEL_DIR = Path(os.environ.get("NATURALVOICE_MODELS", Path(__file__).resolve().parents[2] / "models"))
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"

PAUSE = {",": 0.18, ";": 0.25, ":": 0.25, ".": 0.38, "!": 0.38, "?": 0.42, "\n": 0.7}


@lru_cache(maxsize=1)
def _kokoro():
    from kokoro_onnx import Kokoro

    onnx, voices = MODEL_DIR / "kokoro-v1.0.onnx", MODEL_DIR / "voices-v1.0.bin"
    if not onnx.exists() or not voices.exists():
        raise RuntimeError(
            f"Voice model files missing in {MODEL_DIR}. Download kokoro-v1.0.onnx and voices-v1.0.bin from {MODEL_URL}"
        )
    return Kokoro(str(onnx), str(voices))


def voices() -> list[str]:
    return sorted(_kokoro().get_voices())


def split_chunks(text: str) -> list[tuple[str, float]]:
    """Split into (phrase, pause_after_seconds)."""
    text = re.sub(r"[ \t]+", " ", text.strip())
    parts = re.split(r"(\n\s*\n|[.!?]+[\"')\]]?\s+|[,;:]\s+)", text + " ")
    out: list[tuple[str, float]] = []
    for i in range(0, len(parts), 2):
        phrase = parts[i].strip()
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        if not phrase:
            continue
        key = "\n" if "\n" in sep else (sep.strip()[:1] or ".")
        # keep the punctuation on the phrase so the model gets the right intonation
        lead = sep.strip().rstrip("\"')]")
        punct = lead[:1] if lead[:1] in ".!?,;:" else "."
        if punct and punct[0] in ",;:":
            punct = ","  # comma intonation; the pause is added separately
        out.append((phrase + (punct or ""), PAUSE.get(key, 0.3)))
    # merge very short comma pieces into the next so prosody isn't choppy
    merged: list[tuple[str, float]] = []
    for ph, p in out:
        if merged and len(merged[-1][0]) < 18 and merged[-1][0].endswith(","):
            merged[-1] = (merged[-1][0] + " " + ph, p)
        else:
            merged.append((ph, p))
    return merged


def speak_kokoro(text: str, voice: str = "af_heart", speed: float = 1.0, seed: int = 0) -> tuple[np.ndarray, int]:
    from . import voices as vlib

    k = _kokoro()
    style, lang = vlib.resolve(voice)
    rng = np.random.default_rng(seed)
    pieces, sr = [], 24000
    for phrase, pause in split_chunks(text):
        sp = float(np.clip(speed * (1 + rng.normal(0, 0.025)), 0.5, 2.0))
        audio, sr = k.create(phrase, voice=style, speed=sp, lang=lang)
        pieces.append(np.asarray(audio, dtype=np.float32))
        jitter = pause * (1 + rng.uniform(-0.15, 0.15))
        pieces.append(np.zeros(int(jitter * sr), dtype=np.float32))
    if not pieces:
        raise ValueError("No text to speak.")
    return np.concatenate(pieces[:-1] or pieces), sr


def speak_elevenlabs(text: str, voice: str, api_key: str) -> tuple[np.ndarray, int]:
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=pcm_24000",
        data=json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode(),
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        pcm = np.frombuffer(r.read(), dtype="<i2").astype(np.float32) / 32768
    return pcm, 24000


def speak_openai(text: str, voice: str, api_key: str) -> tuple[np.ndarray, int]:
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=json.dumps(
            {"model": "gpt-4o-mini-tts", "voice": voice or "alloy", "input": text, "response_format": "pcm"}
        ).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        pcm = np.frombuffer(r.read(), dtype="<i2").astype(np.float32) / 32768
    return pcm, 24000


def speak(
    text: str,
    voice: str = "af_heart",
    speed: float = 1.0,
    engine: str = "kokoro",
    humanize: bool = True,
    settings: hz.Settings | None = None,
) -> tuple[np.ndarray, int]:
    if engine == "kokoro" and voice.startswith("clone:"):
        engine = "clone"
    if engine == "clone":
        try:
            from . import clone
        except ImportError as e:
            raise RuntimeError("The voice cloning engine is not installed.") from e
        audio, sr = clone.speak(text, voice, speed)
    elif engine == "kokoro":
        audio, sr = speak_kokoro(text, voice, speed)
    elif engine == "elevenlabs":
        key = os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            raise RuntimeError("Set ELEVENLABS_API_KEY to use the ElevenLabs engine.")
        audio, sr = speak_elevenlabs(text, voice, key)
    elif engine == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("Set OPENAI_API_KEY to use the OpenAI engine.")
        audio, sr = speak_openai(text, voice, key)
    else:
        raise ValueError(f"Unknown engine {engine!r}")
    # short fade-in/out and lead/tail silence like a real recording
    pad = np.zeros(int(0.15 * sr), dtype=np.float32)
    audio = np.concatenate([pad, audio, pad * 2])
    if humanize:
        audio = hz.humanize(audio, sr, settings or hz.get_settings("light"))
    return audio, sr
