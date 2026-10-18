"""Shared voice library: stock Kokoro voices plus user-created voices.

Voice ids used everywhere (CLI, Studio, Voice Lab, API):
* ``af_heart``          stock Kokoro voice (name from voices-v1.0.bin)
* ``custom:<id>``       a Kokoro style vector made in the Voice Lab (blend / design / sample match)
* ``clone:<id>``        a voice for the zero-shot cloning engine (reference audio stored with it)

Custom voices live in DATA_DIR/voices as ``<id>.json`` (metadata) plus ``<id>.npy`` (Kokoro style,
shape (510, 1, 256)) or ``<id>.wav`` (clone reference). DATA_DIR defaults to ``<project>/data`` and can be
moved with NATURALVOICE_DATA.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

import numpy as np

DATA_DIR = Path(os.environ.get("NATURALVOICE_DATA", Path(__file__).resolve().parents[2] / "data"))
VOICE_DIR = DATA_DIR / "voices"
STYLE_SHAPE = (510, 1, 256)
_ID = re.compile(r"^[0-9a-f]{12}$")

LANGS = {"a": "en-us", "b": "en-gb", "e": "es", "f": "fr-fr", "h": "hi", "i": "it", "p": "pt-br", "j": "ja", "z": "cmn"}
LANG_NAMES = {
    "a": "American English",
    "b": "British English",
    "e": "Spanish",
    "f": "French",
    "h": "Hindi",
    "i": "Italian",
    "p": "Brazilian Portuguese",
    "j": "Japanese",
    "z": "Mandarin Chinese",
}


def lang_for(voice: str) -> str:
    return LANGS.get(voice[:1], "en-us")


def stock_info(name: str) -> dict:
    return {
        "id": name,
        "name": name[3:].replace("_", " ").title(),
        "kind": "stock",
        "gender": "female" if name[1:2] == "f" else "male",
        "language": LANG_NAMES.get(name[:1], "Other"),
        "lang": lang_for(name),
    }


def _paths(vid: str) -> tuple[Path, Path, Path]:
    if not _ID.match(vid):
        raise ValueError("Invalid voice id.")
    return VOICE_DIR / f"{vid}.json", VOICE_DIR / f"{vid}.npy", VOICE_DIR / f"{vid}.wav"


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def save_custom(
    name: str,
    style: np.ndarray,
    meta: dict | None = None,
    lang: str = "en-us",
    kind: str = "custom",
    vid: str | None = None,
) -> dict:
    """Save a Kokoro style vector as a reusable voice; returns its record."""
    style = np.asarray(style, dtype=np.float32)
    if style.shape != STYLE_SHAPE or not np.isfinite(style).all():
        raise ValueError(f"Style must be a finite array of shape {STYLE_SHAPE}.")
    name = (name or "").strip()[:60]
    if not name:
        raise ValueError("Give the voice a name.")
    vid = vid or new_id()
    meta_p, npy_p, _ = _paths(vid)
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"id": f"custom:{vid}", "name": name, "kind": kind, "lang": lang, "created": time.time(), "meta": meta or {}}
    np.save(npy_p, style)
    meta_p.write_text(json.dumps(rec, indent=2))
    return rec


def save_clone(name: str, wav_bytes_path: Path, meta: dict | None = None, lang: str = "en-us") -> dict:
    """Register a cloning-engine voice; the reference audio file is moved into the library."""
    name = (name or "").strip()[:60]
    if not name:
        raise ValueError("Give the voice a name.")
    vid = new_id()
    meta_p, _, wav_p = _paths(vid)
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    Path(wav_bytes_path).replace(wav_p)
    rec = {
        "id": f"clone:{vid}",
        "name": name,
        "kind": "clone",
        "lang": lang,
        "created": time.time(),
        "meta": meta or {},
    }
    meta_p.write_text(json.dumps(rec, indent=2))
    return rec


def list_custom() -> list[dict]:
    if not VOICE_DIR.exists():
        return []
    out = []
    for p in sorted(VOICE_DIR.glob("*.json")):
        try:
            rec = json.loads(p.read_text())
            if isinstance(rec, dict) and isinstance(rec.get("id"), str):
                out.append(rec)
        except (OSError, ValueError):
            continue  # one corrupt file must not hide the rest of the library
    return sorted(out, key=lambda r: r.get("created", 0), reverse=True)


def get(voice_id: str) -> dict:
    kind, _, vid = voice_id.partition(":")
    if kind not in {"custom", "clone"}:
        raise ValueError("Not a library voice.")
    meta_p, _, _ = _paths(vid)
    if not meta_p.exists():
        raise KeyError(f"Voice {voice_id} not found.")
    return json.loads(meta_p.read_text())


def rename(voice_id: str, name: str) -> dict:
    rec = get(voice_id)
    name = (name or "").strip()[:60]
    if not name:
        raise ValueError("Give the voice a name.")
    rec["name"] = name
    _paths(voice_id.partition(":")[2])[0].write_text(json.dumps(rec, indent=2))
    return rec


def delete(voice_id: str) -> None:
    get(voice_id)
    if voice_id in favorites():
        set_starred(voice_id, False)
    for p in _paths(voice_id.partition(":")[2]):
        p.unlink(missing_ok=True)


def style_of(voice_id: str) -> np.ndarray:
    """Kokoro style array (510, 1, 256) for a stock or custom voice."""
    if voice_id.startswith("custom:"):
        _, npy_p, _ = _paths(voice_id.partition(":")[2])
        if not npy_p.exists():
            raise KeyError(f"Voice {voice_id} not found.")
        return np.load(npy_p).astype(np.float32)
    from .tts import _kokoro

    k = _kokoro()
    if voice_id not in k.voices:
        raise KeyError(f"Unknown voice {voice_id!r}.")
    return np.asarray(k.voices[voice_id], dtype=np.float32)


def reference_audio(voice_id: str) -> Path:
    """Reference recording of a clone voice."""
    if not voice_id.startswith("clone:"):
        raise ValueError("Not a clone voice.")
    _, _, wav_p = _paths(voice_id.partition(":")[2])
    if not wav_p.exists():
        raise KeyError(f"Voice {voice_id} not found.")
    return wav_p


def resolve(voice_id: str) -> tuple[np.ndarray | str, str]:
    """(voice argument for Kokoro, language code)."""
    if voice_id.startswith("custom:"):
        return style_of(voice_id), get(voice_id).get("lang", "en-us")
    return voice_id, lang_for(voice_id)


def _fav_path() -> Path:
    return DATA_DIR / "favorites.json"


def favorites() -> set[str]:
    """Ids of starred voices (stored beside the library so every page and the CLI see the same stars)."""
    try:
        data = json.loads(_fav_path().read_text())
        return {v for v in data if isinstance(v, str)} if isinstance(data, list) else set()
    except (OSError, ValueError):
        return set()


def set_starred(voice_id: str, starred: bool) -> bool:
    favs = favorites()
    (favs.add if starred else favs.discard)(voice_id)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _fav_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(favs)))
    tmp.replace(_fav_path())  # atomic: a crash can't leave a half-written favourites file
    return starred


def catalog() -> list[dict]:
    """Every usable voice: stock first, then the user's library. Each record has ``starred``."""
    from .tts import _kokoro

    favs = favorites()
    stock = [stock_info(v) for v in sorted(_kokoro().get_voices())]
    return [{**r, "starred": r["id"] in favs} for r in stock + list_custom()]
