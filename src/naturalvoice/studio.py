"""Studio: multi-voice script rendering with delivery direction, music bed, mastering and captions.

Everything here is honest about what the engine can do. Kokoro has no emotion control, so a
"delivery preset" is a named combination of speed, pitch, pause length, gain and a light EQ.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import sys
import threading
import time
import uuid
from typing import Callable, Literal
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import signal

from . import audio as aio
from . import humanize as hz

log = logging.getLogger(__name__)

SR = 24000
MAX_LINES = 500
MAX_CHARS = 50_000
VOICE_ID = re.compile(r"^(?:[a-z]{2}_[a-z0-9_]{1,30}|custom:[0-9a-f]{12}|clone:[0-9a-f]{12})$")
PROJECT_ID = re.compile(r"^[0-9a-f]{12}$")
BREAK_SECONDS = 1.2
TAKE_STYLE_JITTER = 0.03  # alternate takes: style noise as a fraction of the style's spread
SAFE_SPEED = (0.85, 1.2)  # fit-to-time never changes delivery tempo beyond this without warning
STRETCH_FINE = (0.95, 1.05)
ACX_ROOM_TONE_DB = -65.0

# --------------------------------------------------------------------------- delivery presets
# speed/pitch/pause multipliers and gain are applied on top of the line's own settings.
DELIVERY: dict[str, dict] = {
    "neutral": {
        "label": "Neutral",
        "does": "No change: the voice as the model reads it.",
        "speed": 1.0,
        "pitch": 0.0,
        "pause": 1.0,
        "gain": 0.0,
        "eq": [],
    },
    "warm": {
        "label": "Warm",
        "does": "5% slower, half a semitone lower, more low-mid body, softer top.",
        "speed": 0.95,
        "pitch": -0.5,
        "pause": 1.1,
        "gain": 0.0,
        "eq": [("lowshelf", 220, 2.5), ("highshelf", 8000, -1.5)],
    },
    "energetic": {
        "label": "Energetic",
        "does": "10% faster, slightly higher, shorter pauses, presence lift.",
        "speed": 1.1,
        "pitch": 0.5,
        "pause": 0.75,
        "gain": 1.0,
        "eq": [("peak", 3000, 2.0)],
    },
    "calm": {
        "label": "Calm",
        "does": "10% slower, 30% longer pauses, a little quieter and darker.",
        "speed": 0.9,
        "pitch": 0.0,
        "pause": 1.3,
        "gain": -1.0,
        "eq": [("highshelf", 6000, -2.0)],
    },
    "serious": {
        "label": "Serious",
        "does": "5% slower, one semitone lower, longer pauses, low-end weight.",
        "speed": 0.95,
        "pitch": -1.0,
        "pause": 1.15,
        "gain": 0.0,
        "eq": [("lowshelf", 150, 1.5)],
    },
    "excited": {
        "label": "Excited",
        "does": "15% faster, one semitone higher, short pauses, louder and brighter.",
        "speed": 1.15,
        "pitch": 1.0,
        "pause": 0.65,
        "gain": 1.5,
        "eq": [("peak", 3500, 2.5)],
    },
    "soft": {
        "label": "Soft",
        "does": "8% slower, 3 dB quieter, longer pauses, rolled-off top.",
        "speed": 0.92,
        "pitch": 0.0,
        "pause": 1.2,
        "gain": -3.0,
        "eq": [("highshelf", 5000, -3.0)],
    },
}

# Delivery targets. ACX spec: RMS -23..-18 dBFS, peak <= -3 dBFS, noise floor <= -60 dBFS,
# 0.5-1 s room tone at the head and 1-5 s at the tail, MP3 192 kbps+ CBR at 44.1 kHz.
TARGETS: dict[str, dict] = {
    "youtube": {"label": "YouTube / streaming", "lufs": -14.0, "tp": -1.0},
    "podcast": {"label": "Podcast", "lufs": -16.0, "tp": -1.0},
    "broadcast": {"label": "Broadcast (EBU R128)", "lufs": -23.0, "tp": -1.0},
    "acx": {"label": "Audiobook (ACX)", "rms": -20.0, "peak": -3.5, "head": 0.75, "tail": 2.0},
    "raw": {"label": "Raw (no loudness change)"},
}
FORMATS = {"wav": ".wav", "flac": ".flac", "mp3": ".mp3"}
RATES = {24000, 44100, 48000}


class StudioError(ValueError):
    """A problem the user can fix; the message is safe to show."""


# --------------------------------------------------------------------------- inline tags & dictionary
TAG = re.compile(r"\[([^\[\]\n]{1,40})\]")
PAUSE_TAG = re.compile(r"^pause\s+(\d+(?:\.\d+)?)\s*(s|sec|ms)?$", re.I)
MARK = re.compile(r"\u27e6(\d+)\u27e7")  # ⟦n⟧ placeholder for a dictionary word


CLONE_EMOTION_TAGS_FALLBACK: list[str] = []


def clone_emotion_tags() -> list[str]:
    """Tags the clone engine understands (from clone.status()['emotion_tags']); [] if unknown."""
    try:
        from . import clone

        tags = clone.status().get("emotion_tags") or []
        return [str(t).strip("[]").lower() for t in tags if isinstance(t, str)]
    except Exception:
        return list(CLONE_EMOTION_TAGS_FALLBACK)


type InlineSegment = tuple[Literal["text"], str] | tuple[Literal["pause"], float]


def parse_inline(text: str, passthrough: set[str] | frozenset = frozenset()) -> tuple[list[InlineSegment], list[str]]:
    """Split line text into [('text', str) | ('pause', seconds)] plus warnings."""
    out: list[InlineSegment] = []
    warnings: list[str] = []
    pos = 0
    for m in TAG.finditer(text):
        body = m.group(1).strip()
        pm = PAUSE_TAG.match(body)
        if pm:
            sec = float(pm.group(1)) / (1000 if (pm.group(2) or "").lower() == "ms" else 1)
            if not 0.1 <= sec <= 10:
                warnings.append(f"[{body}] is outside 0.1-10 s; used {min(max(sec, 0.1), 10):g} s.")
                sec = min(max(sec, 0.1), 10.0)
            kind: tuple[Literal["pause"], float] = ("pause", sec)
        elif body.lower() == "break":
            kind = ("pause", BREAK_SECONDS)
        elif body.lower() in passthrough:
            continue  # clone emotion tag: left in the text for the engine, no warning
        else:
            warnings.append(f"Unknown tag [{body}] is read as text. Known tags: [pause 1.5s], [break].")
            continue
        if text[pos : m.start()].strip():
            out.append(("text", text[pos : m.start()]))
        out.append(kind)
        pos = m.end()
    if text[pos:].strip():
        out.append(("text", text[pos:]))
    return out, warnings


def is_phoneme_entry(value: str) -> bool:
    return len(value) > 2 and value.startswith("/") and value.endswith("/")


def mark_dictionary(text: str, dictionary: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    """Replace whole-word, case-insensitive dictionary hits by ⟦n⟧; returns (marked text, [(original, value)])."""
    hits: list[tuple[str, str]] = []
    if not dictionary:
        return text, hits
    lookup = {k.lower(): v for k, v in dictionary.items() if k.strip()}
    keys = sorted(lookup, key=len, reverse=True)
    rx = re.compile(r"(?<![\w'])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w'])", re.I)

    def sub(m):
        hits.append((m.group(0), lookup[m.group(0).lower()]))
        return f"\u27e6{len(hits) - 1}\u27e7"

    return rx.sub(sub, text), hits


def display_text(marked: str, hits) -> str:
    return MARK.sub(lambda m: hits[int(m.group(1))][0], marked)


def spoken_text(marked: str, hits) -> str:
    """Text for engines without phoneme input: respellings applied, phoneme entries left as the word."""
    return MARK.sub(
        lambda m: hits[int(m.group(1))][0] if is_phoneme_entry(hits[int(m.group(1))][1]) else hits[int(m.group(1))][1],
        marked,
    )


SUB_TIME = re.compile(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[,.](\d{1,3})")
SUB_CUE = re.compile(r"^\s*(\S+)\s*-->\s*(\S+)")
MAX_SUB_BYTES = 2 * 1024 * 1024


def _sub_time(t: str) -> float:
    m = SUB_TIME.fullmatch(t.strip())
    if not m:
        raise StudioError(f"Bad timestamp {t[:20]!r}.")
    h, mn, sec, ms = m.groups()
    return int(h or 0) * 3600 + int(mn) * 60 + int(sec) + int(ms.ljust(3, "0")) / 1000


def parse_subtitles(text: str, voice: str = "af_heart") -> dict:
    """SRT or WebVTT -> timed lines. Formatting tags are dropped; `<v Name>` / `NAME:` become speakers."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if not text.strip():
        raise StudioError("The subtitle file is empty.")
    blocks = re.split(r"\n\s*\n", text.strip())
    lines, warnings = [], []
    for bi, b in enumerate(blocks, 1):
        rows = [r for r in b.split("\n") if r.strip()]
        ti = next((i for i, r in enumerate(rows) if "-->" in r), None)
        if ti is None:
            if bi == 1 and rows and rows[0].startswith("WEBVTT"):
                continue
            if rows and rows[0].split(" ")[0] in {"NOTE", "STYLE", "REGION"}:
                continue
            warnings.append(f"Block {bi} has no timing line; skipped.")
            continue
        m = SUB_CUE.match(rows[ti])
        if not m:
            warnings.append(f"Block {bi}: unreadable timing; skipped.")
            continue
        try:
            start, end = _sub_time(m.group(1)), _sub_time(m.group(2))
        except StudioError as e:
            warnings.append(f"Block {bi}: {e} Skipped.")
            continue
        if end <= start:
            warnings.append(f"Block {bi}: ends before it starts; skipped.")
            continue
        body = " ".join(r.strip() for r in rows[ti + 1 :])
        speaker = ""
        vm = re.match(r"^<v(?:\.[^ >]*)?\s+([^>]{1,40})>", body)
        if vm:
            speaker = vm.group(1).strip()
        body = re.sub(r"<[^>]{0,80}>", "", body)
        body = re.sub(r"\{\\[^}]*\}", "", body).strip()
        cm = SPEAKER_COLON.match(body)
        if not speaker and cm and cm.group(1).isupper():
            speaker, body = cm.group(1).strip(), cm.group(2).strip()
        if not body:
            continue
        ln = new_line(body[:5000], voice, speaker)
        ln.update(start=round(start, 3), end=round(end, 3), pause=0.0)
        lines.append(ln)
    if not lines:
        raise StudioError(
            "No subtitle cues found. Use an .srt or .vtt file with lines like 00:00:01,000 --> 00:00:03,000."
        )
    if len(lines) > MAX_LINES:
        raise StudioError(f"The file has {len(lines)} cues; {MAX_LINES} max.")
    if sum(len(ln["text"]) for ln in lines) > MAX_CHARS:
        raise StudioError(f"Subtitle text is longer than {MAX_CHARS:,} characters.")
    lines.sort(key=lambda ln: ln["start"])
    return {"lines": lines, "warnings": warnings}


SPEAKER_BRACKET = re.compile(r"^\s*\[([^\[\]\n]{1,40})\]\s*(.*)$")
SPEAKER_COLON = re.compile(r"^\s*([A-Za-z][\w .'\-]{0,39}?)\s*:\s+(.+)$")
DEFAULT_CAST = ["af_heart", "am_michael", "bf_emma", "bm_george", "af_bella", "am_adam", "bf_isabella", "bm_lewis"]


def parse_script(text: str, cast: dict[str, str] | None = None, default_voice: str = "af_heart") -> dict:
    """Plain script -> lines. Speakers: `NARRATOR: text` or `[Narrator] text`; untagged lines keep the last speaker."""
    if len(text) > MAX_CHARS:
        raise StudioError(f"Script is too long ({MAX_CHARS:,} characters max).")
    cast = {k.strip().lower(): v for k, v in (cast or {}).items()}
    speakers: dict[str, str] = {}
    lines: list[dict] = []
    speaker = ""
    for raw in re.split(r"\n\s*\n|\n", text):
        if not raw.strip():
            continue
        body = raw.strip()
        m = SPEAKER_BRACKET.match(body)
        if m and (PAUSE_TAG.match(m.group(1).strip()) or m.group(1).strip().lower() == "break"):
            m = None  # a pause tag at the start is not a speaker
        m = m or SPEAKER_COLON.match(body)
        if m:
            speaker, body = m.group(1).strip(), m.group(2).strip()
        if not body:
            continue
        key = speaker.lower()
        if key not in speakers:
            voice = cast.get(key)
            if not voice or not VOICE_ID.match(voice):
                voice = DEFAULT_CAST[len(speakers) % len(DEFAULT_CAST)] if speaker else default_voice
            speakers[key] = voice
        lines.append(new_line(body, speakers[key], speaker))
    if len(lines) > MAX_LINES:
        raise StudioError(f"Script has {len(lines)} lines; {MAX_LINES} max.")
    names: dict[str, str] = {}
    for ln in lines:
        names.setdefault(ln["speaker"].lower(), ln["speaker"])
    return {"lines": lines, "cast": [{"speaker": names[k], "voice": v} for k, v in speakers.items()]}


def new_line(text: str = "", voice: str = "af_heart", speaker: str = "") -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "text": text,
        "voice": voice,
        "speaker": speaker,
        "speed": 1.0,
        "pitch": 0.0,
        "volume": 0.0,
        "pause": 0.4,
        "delivery": "neutral",
        "take": 0,
        "takes": [0],
        "target": None,
        "start": None,
        "end": None,
    }


def lint_project(project: dict) -> list[str]:
    """Warnings (not errors) about the script: unknown tags, missing text."""
    out = []
    ctags = None
    for i, ln in enumerate(project.get("lines", []), 1):
        pt: frozenset[str] = frozenset()
        if str(ln.get("voice", "")).startswith("clone:"):
            ctags = clone_emotion_tags() if ctags is None else ctags
            pt = frozenset(ctags)
        _, w = parse_inline(ln.get("text", ""), pt)
        out += [f"Line {i}: {x}" for x in w]
        if not ln.get("text", "").strip():
            out.append(f"Line {i}: empty, will be skipped.")
    return out


# --------------------------------------------------------------------------- custom styles
EQ_KINDS = {"lowshelf", "highshelf", "peak"}
MAX_STYLES = 100


def validate_style(st_: dict) -> dict:
    """Normalise a delivery style (built-in shape). Raises StudioError on bad input."""
    if not isinstance(st_, dict):
        raise StudioError("A style must be an object.")
    name = str(st_.get("name") or "").strip()[:60]
    if not name:
        raise StudioError("Give the style a name.")

    def num(k, lo, hi, default):
        v = st_.get(k, default)
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise StudioError(f"Style {k} must be a number.")
        if not np.isfinite(v) or not lo <= v <= hi:
            raise StudioError(f"Style {k} must be between {lo} and {hi}.")
        return round(v, 3)

    eq = []
    for band in (st_.get("eq") or [])[:4]:
        if not isinstance(band, (list, tuple)) or len(band) != 3 or band[0] not in EQ_KINDS:
            raise StudioError("Style EQ bands are [lowshelf|highshelf|peak, Hz, dB].")
        f, g = float(band[1]), float(band[2])
        if not (60 <= f <= 12000 and -6 <= g <= 6):
            raise StudioError("Style EQ: 60-12000 Hz, -6..+6 dB.")
        eq.append([band[0], round(f), round(g, 1)])
    out = {
        "name": name,
        "speed": num("speed", 0.5, 2.0, 1.0),
        "pitch": num("pitch", -4, 4, 0.0),
        "gain": num("gain", -24, 12, 0.0),
        "pause": num("pause", 0.3, 3.0, 1.0),
        "pause_after": num("pause_after", 0.0, 10.0, 0.4),
        "eq": eq,
    }
    sid = st_.get("id")
    if sid is not None:
        if not isinstance(sid, str) or not PROJECT_ID.match(sid):
            raise StudioError("Invalid style id.")
        out["id"] = sid
    return out


def delivery_of(line: dict) -> dict:
    """The delivery recipe for a line: a built-in preset, or the line's custom style (stored by value)."""
    if line.get("delivery") == "custom" and isinstance(line.get("style"), dict):
        s_ = line["style"]
        return {
            "label": s_.get("name", "Custom"),
            "speed": s_["speed"],
            "pitch": s_["pitch"],
            "pause": s_["pause"],
            "gain": s_["gain"],
            "eq": [tuple(b) for b in s_.get("eq", [])],
        }
    return DELIVERY.get(line.get("delivery", "neutral"), DELIVERY["neutral"])


def style_from_line(line: dict, name: str) -> dict:
    """Capture a line's effective settings (its delivery folded with its own speed/pitch/volume) as a style."""
    d = delivery_of(line)
    return validate_style(
        {
            "name": name,
            "speed": float(np.clip(line["speed"] * d["speed"], 0.5, 2)),
            "pitch": float(np.clip(line["pitch"] + d["pitch"], -4, 4)),
            "gain": float(np.clip(line["volume"] + d["gain"], -24, 12)),
            "pause": d["pause"],
            "pause_after": line["pause"],
            "eq": [list(b) for b in d["eq"]],
        }
    )


def styles_path() -> Path:
    from . import voices as vlib

    return vlib.DATA_DIR / "styles.json"


def load_styles() -> list[dict]:
    p = styles_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        try:
            out.append(validate_style(r))
        except (StudioError, TypeError, ValueError):
            continue  # one bad entry must not hide the rest
    return [r for r in out if "id" in r]


def save_styles(styles: list[dict]) -> None:
    p = styles_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".styles-{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(styles, indent=1), encoding="utf-8")
    tmp.replace(p)


# --------------------------------------------------------------------------- director's notes (keyword parser, no AI)
NOTE_RULES: list[tuple[str, dict, str]] = [
    # (regex, effect, readout); effects: speed multiplier, pitch st, volume dB, pause multiplier
    (r"\b(much|really|very) slow(er|ly)?\b", {"speed": 0.85}, "much slower"),
    (r"\bslow(er|ly)?( down)?\b|\bunhurried\b|\btake (your|it) time\b", {"speed": 0.92}, "slower"),
    (r"\brelaxed\b|\blaid[- ]back\b", {"speed": 0.95, "pause": 1.1}, "relaxed: a bit slower, longer pauses"),
    (r"\b(much|really|very) fast(er)?\b", {"speed": 1.15}, "much faster"),
    (r"\bfast(er)?\b|\bquick(er|ly)?\b(?! pause)|\bspeed up\b|\bpacy\b", {"speed": 1.08}, "faster"),
    (
        r"\brush(ed|ing)?\b|\burgent(ly)?\b|\bhurr(y|ied)\b",
        {"speed": 1.12, "pause": 0.8},
        "rushed: faster, shorter pauses",
    ),
    (r"\bhigher\b|\bbrighter\b|\blighter\b", {"pitch": 1.0}, "higher pitch"),
    (r"\blower\b|\bdeeper\b|\bdarker\b", {"pitch": -1.0}, "lower pitch"),
    (r"\bwhisper[- ]?soft\b|\bbarely audible\b", {"volume": -6.0}, "much quieter"),
    (r"\bsoft(ly|er)?\b|\bquiet(ly|er)?\b|\bgentl[ey]\b", {"volume": -3.0}, "quieter"),
    (r"\blouder\b|\bloud\b|\bproject\b", {"volume": 3.0}, "louder"),
    (r"\bpunchy\b|\bconfident\b|\bbold\b", {"volume": 2.0, "speed": 1.03}, "punchy: louder, a touch faster"),
    (r"\bdramatic pause\b|\blong pause\b", {"pause_after": 1.5}, "1.5 s pause after the line"),
    (r"\b(a )?beat\b", {"pause_after": 0.8}, "0.8 s beat after the line"),
    (r"\bquick pause\b|\bno pause\b|\btight\b", {"pause_after": 0.15, "pause": 0.85}, "short pauses"),
]
# emotion words: (regex, clone tag, stock fallback preset, extra effect, readout)
NOTE_EMOTIONS: list[tuple[str, str, str, dict, str]] = [
    (r"\blaugh(ing|s)?\b", "laugh", "excited", {}, "laughing"),
    (r"\bfunny\b|\bamused\b|\bplayful\b|\bchuckl\w*", "chuckle", "warm", {"pitch": 0.5}, "amused"),
    (r"\btired\b|\bsigh(ing|s)?\b|\bweary\b|\bexhausted\b", "sigh", "soft", {"speed": 0.95, "pitch": -0.5}, "tired"),
    (r"\bsurprised?\b|\bshock(ed)?\b|\bastonished\b", "gasp", "excited", {"pitch": 0.5}, "surprised"),
    (r"\bwarm(ly|th)?\b|\bfriendly\b|\bkind\b", "", "warm", {}, "warm"),
    (r"\bexcited\b|\benthusiastic\b|\bthrilled\b", "", "excited", {}, "excited"),
    (r"\benergetic\b|\bupbeat\b|\blively\b", "", "energetic", {}, "energetic"),
    (r"\bcalm(ly)?\b|\bsoothing\b|\bserene\b", "", "calm", {}, "calm"),
    (r"\bserious(ly)?\b|\bgrave\b|\bstern\b|\bsombre\b|\bsomber\b", "", "serious", {}, "serious"),
    (r"\bsad(ly)?\b|\bmelanchol\w*", "", "soft", {"speed": 0.93, "pitch": -0.5}, "sad"),
]
NOTE_STOP = {
    "a",
    "an",
    "the",
    "and",
    "but",
    "with",
    "at",
    "end",
    "of",
    "to",
    "it",
    "bit",
    "slightly",
    "little",
    "more",
    "less",
    "very",
    "really",
    "much",
    "just",
    "touch",
    "in",
    "on",
    "start",
    "down",
    "up",
    "be",
    "please",
    "line",
    "this",
    "voice",
    "read",
    "tone",
    "like",
    "sound",
    "make",
    "keep",
    "not",
    "too",
    "so",
}


def parse_note(note: str, line: dict, clone_tags: list[str] | None = None) -> dict:
    """Map a director's note to control values. Pure; returns new values plus a readout. Nothing is applied here."""
    note = (note or "")[:200]
    low = note.lower()
    clone = str(line.get("voice", "")).startswith("clone:")
    ctags = set(clone_tags or [])
    used_spans: list[tuple[int, int]] = []
    understood: list[str] = []
    speed, pitch, vol, pmul = 1.0, 0.0, 0.0, 1.0
    pause_after = None
    delivery = None
    tags: list[str] = []
    mild = bool(re.search(r"\b(slightly|a bit|a little|a touch|somewhat)\b", low))

    def hit(rx):
        found = None
        for m in re.finditer(rx, low):
            if any(a < m.end() and m.start() < b for a, b in used_spans):
                continue
            found = found or m
            used_spans.append(m.span())
        return found

    for rx, eff, say in NOTE_RULES:
        if hit(rx):
            k = 0.5 if mild else 1.0
            speed *= 1 + (eff.get("speed", 1) - 1) * k
            pitch += eff.get("pitch", 0) * k
            vol += eff.get("volume", 0) * k
            pmul *= 1 + (eff.get("pause", 1) - 1) * k
            if "pause_after" in eff:
                pause_after = eff["pause_after"]
            understood.append(say)
    for rx, tag, preset, eff, say in NOTE_EMOTIONS:
        if not hit(rx):
            continue
        if clone and tag:
            if tag in ctags:
                tags.append(tag)
                understood.append(f"{say}: adds [{tag}] for the cloned voice")
            else:
                understood.append(f"{say}: the clone engine doesn't offer [{tag}], so nothing changed")
            continue
        if delivery is None:
            delivery = preset
            speed *= eff.get("speed", 1)
            pitch += eff.get("pitch", 0)
            understood.append(
                f"{say}: {DELIVERY[preset]['label']} delivery"
                + (f", {eff.get('speed', 1):g}x speed" if "speed" in eff else "")
                + (f", {eff['pitch']:+g} st" if "pitch" in eff else "")
            )
        else:
            understood.append(f"{say}: ignored (already using {DELIVERY[delivery]['label']})")
    used = set()
    for a, b in used_spans:
        used.update(re.findall(r"[a-z']+", low[a:b]))
    unused = [w for w in dict.fromkeys(re.findall(r"[a-z']+", low)) if w not in used and w not in NOTE_STOP]
    new = {
        "speed": round(float(np.clip(line.get("speed", 1) * speed, 0.5, 2.0)), 2),
        "pitch": round(float(np.clip(line.get("pitch", 0) + pitch, -4, 4)) * 2) / 2,
        "volume": round(float(np.clip(line.get("volume", 0) + vol, -24, 12)) * 2) / 2,
        "pause": round(
            float(np.clip(pause_after if pause_after is not None else line.get("pause", 0.4) * pmul, 0, 10)), 2
        ),
        "delivery": delivery or line.get("delivery", "neutral"),
    }
    text = line.get("text", "")
    if tags:
        have = {m.group(1).strip().lower() for m in TAG.finditer(text)}
        add = [t for t in tags if t not in have]
        if add:
            text = " ".join(f"[{t}]" for t in add) + " " + text
    return {**new, "text": text, "tags": tags, "understood": understood, "unused": unused}


# --------------------------------------------------------------------------- synthesis
_cache: OrderedDict[str, tuple[np.ndarray, list]] = OrderedDict()
_cache_lock = threading.Lock()
CACHE_SIZE = 64


def _eq(x: np.ndarray, eq) -> np.ndarray:
    if not eq or not len(x):
        return x
    from pedalboard import HighShelfFilter, LowShelfFilter, PeakFilter, Pedalboard

    kinds = {"lowshelf": LowShelfFilter, "highshelf": HighShelfFilter, "peak": PeakFilter}
    board = Pedalboard([kinds[k](cutoff_frequency_hz=f, gain_db=g, q=0.7 if k != "peak" else 0.9) for k, f, g in eq])
    return board(x[None, :].astype(np.float32), SR)[0]


def _pitch(x: np.ndarray, semitones: float) -> np.ndarray:
    if abs(semitones) < 1e-3 or not len(x):
        return x
    from pedalboard import PitchShift

    y = PitchShift(semitones=float(semitones))(x[None, :].astype(np.float32), SR)[0]
    return y[: len(x)] if len(y) >= len(x) else np.pad(y, (0, len(x) - len(y)))


def line_key(line: dict, dictionary: dict, polish: bool) -> str:
    used = {k: v for k, v in (dictionary or {}).items() if k.lower() in line["text"].lower()}
    blob = json.dumps(
        [
            line["text"],
            line["voice"],
            line["speed"],
            line["pitch"],
            line["volume"],
            line["delivery"],
            used,
            polish,
            int(line.get("take") or 0),
            line.get("style") if line.get("delivery") == "custom" else None,
        ],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _kokoro_phrase(k, marked: str, hits, voice, speed: float, lang: str) -> np.ndarray:
    """One phrase through Kokoro; dictionary phoneme entries are spliced into the phoneme string."""
    if not any(is_phoneme_entry(hits[int(m.group(1))][1]) for m in MARK.finditer(marked)):
        txt = spoken_text(marked, hits)
        audio, _ = k.create(txt, voice=voice, speed=speed, lang=lang)
        return np.asarray(audio, dtype=np.float32)
    parts, pos = [], 0
    for m in MARK.finditer(marked):
        before = marked[pos : m.start()]
        if before.strip():
            parts.append(k.tokenizer.phonemize(spoken_text(before, hits), lang))
        orig, val = hits[int(m.group(1))]
        parts.append(val[1:-1].strip() if is_phoneme_entry(val) else k.tokenizer.phonemize(val, lang))
        pos = m.end()
    if marked[pos:].strip():
        parts.append(k.tokenizer.phonemize(spoken_text(marked[pos:], hits), lang))
    audio, _ = k.create(" ".join(p for p in parts if p), voice=voice, speed=speed, lang=lang, is_phonemes=True)
    return np.asarray(audio, dtype=np.float32)


def render_line(line: dict, dictionary: dict | None = None, polish: bool = False) -> tuple[np.ndarray, list[dict]]:
    """Render one line at 24 kHz. Returns (audio, phrases[{start, end, text}] in seconds within the line)."""
    key = line_key(line, dictionary or {}, polish)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            a, ph = _cache[key]
            return a.copy(), [dict(p) for p in ph]
    from . import tts

    d = delivery_of(line)
    speed = float(np.clip(line["speed"] * d["speed"], 0.5, 2.0))
    pitch = float(np.clip(line["pitch"] + d["pitch"], -4.0, 4.0))
    segments, _ = parse_inline(line["text"])
    rng = np.random.default_rng(int(key[:8], 16))
    pieces: list[np.ndarray] = []
    phrases: list[dict] = []
    cursor = 0
    clone = line["voice"].startswith("clone:")
    if not clone:
        from . import voices as vlib

        k = tts._kokoro()
        voice_arg, lang = vlib.resolve(line["voice"])
        take = int(line.get("take") or 0)
        if take:  # alternate take: tiny, seeded perturbation of the Kokoro style vector
            style = vlib.style_of(line["voice"]) if isinstance(voice_arg, str) else np.asarray(voice_arg, np.float32)
            prng = np.random.default_rng(take)
            voice_arg = (style + prng.normal(0, TAKE_STYLE_JITTER * float(style.std()), style.shape)).astype(np.float32)
    for kind, val in segments:
        if kind == "pause":
            n = int(float(val) * SR)
            pieces.append(np.zeros(n, np.float32))
            cursor += n
            continue
        marked, hits = mark_dictionary(str(val), dictionary or {})
        if clone:
            a, sr = tts.speak(spoken_text(marked, hits), line["voice"], speed, humanize=False)
            if sr != SR:
                a = signal.resample_poly(a, SR, sr).astype(np.float32)
            a = np.asarray(a, np.float32).reshape(-1)
            phrases.append(
                {
                    "start": (cursor + int(0.15 * SR)) / SR,
                    "end": (cursor + max(len(a) - int(0.3 * SR), 1)) / SR,
                    "text": " ".join(TAG.sub(" ", display_text(marked, hits)).split()),
                }
            )  # tags are sounds, not words
            pieces.append(a)
            cursor += len(a)
            continue
        chunks = tts.split_chunks(marked)
        for i, (phrase, pause) in enumerate(chunks):
            sp = float(np.clip(speed * (1 + rng.normal(0, 0.02)), 0.5, 2.0))
            a = _kokoro_phrase(k, phrase, hits, voice_arg, sp, lang)
            phrases.append({"start": cursor / SR, "end": (cursor + len(a)) / SR, "text": display_text(phrase, hits)})
            pieces.append(a)
            cursor += len(a)
            if i < len(chunks) - 1:
                n = int(pause * d["pause"] * (1 + rng.uniform(-0.1, 0.1)) * SR)
                pieces.append(np.zeros(n, np.float32))
                cursor += n
    if not phrases:
        raise StudioError("This line has no words to speak.")
    x = np.concatenate(pieces).astype(np.float32)
    x = _pitch(x, pitch)
    x = _eq(x, d["eq"])
    if polish:
        x = hz.humanize(x, SR, hz.get_settings("light", room_tone=0.0))
    x = (x * 10 ** ((line["volume"] + d["gain"]) / 20)).astype(np.float32)
    with _cache_lock:
        _cache[key] = (x.copy(), [dict(p) for p in phrases])
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return x, phrases


def time_stretch(x: np.ndarray, factor: float) -> np.ndarray:
    """factor > 1 = faster / shorter. High-quality phase vocoder with formants preserved."""
    if abs(factor - 1) < 1e-3 or not len(x):
        return x
    from pedalboard import time_stretch as ts

    return ts(
        x[None, :].astype(np.float32), SR, stretch_factor=float(factor), high_quality=True, preserve_formants=True
    )[0].astype(np.float32)


def _scale_phrases(ph: list[dict], ratio: float) -> list[dict]:
    return [{**p, "start": p["start"] * ratio, "end": p["end"] * ratio} for p in ph]


def fit_line(
    line: dict, seconds: float, dictionary: dict, polish: bool, base=None
) -> tuple[np.ndarray, list[dict], dict]:
    """Render a line to a target length: speed first (safe range), then a fine time-stretch."""
    a, ph = base or render_line(line, dictionary, polish)
    need = len(a) / (seconds * SR)  # >1 means it must get faster
    info: dict[str, float | str | None] = {
        "target": round(seconds, 2),
        "needed_factor": round(need, 3),
        "warning": None,
    }
    f = float(np.clip(need, *SAFE_SPEED))
    if abs(f - 1) > 0.01:
        a, ph = render_line({**line, "speed": float(np.clip(line["speed"] * f, 0.5, 2.0))}, dictionary, polish)
    r = len(a) / (seconds * SR)
    lo, hi = max(STRETCH_FINE[0], SAFE_SPEED[0] / f), min(STRETCH_FINE[1], SAFE_SPEED[1] / f)
    r = float(np.clip(r, min(lo, 1.0), max(hi, 1.0)))
    if abs(r - 1) > 0.002:
        n0 = len(a)
        a = time_stretch(a, r)
        ph = _scale_phrases(ph, len(a) / n0)
    info.update(speed_factor=round(f, 3), stretch=round(r, 3), achieved=round(len(a) / SR, 2))
    if not SAFE_SPEED[0] <= need <= SAFE_SPEED[1]:
        info["warning"] = (
            f"Needs {need:.2f}x tempo to fit {seconds:g} s; capped at the safe "
            f"{SAFE_SPEED[0]}-{SAFE_SPEED[1]}x range. Edit the text or the target."
        )
    return a, ph, info


def room_tone(n: int, sr: int, rms_dbfs: float = ACX_ROOM_TONE_DB, seed: int = 11) -> np.ndarray:
    """Warm, steady noise at an exact RMS level (ACX wants a real noise floor, not digital silence)."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n + sr).astype(np.float64)
    b, a = signal.butter(1, 600 / (sr / 2), btype="low")
    x = signal.lfilter(b, a, x)[sr:]
    x = signal.lfilter(*signal.butter(2, 60 / (sr / 2), btype="high"), x)
    x *= 10 ** (rms_dbfs / 20) / (np.sqrt(np.mean(x**2)) + 1e-12)
    return x.astype(np.float32)


# --------------------------------------------------------------------------- measurement & mastering
def true_peak_db(x: np.ndarray, sr: int) -> float:
    """4x oversampled peak (ITU-R BS.1770 style true-peak estimate)."""
    if not len(x):
        return float("-inf")
    y = signal.resample_poly(np.asarray(x, np.float64), 4, 1)
    return float(20 * np.log10(np.max(np.abs(y)) + 1e-12))


def lufs(x: np.ndarray, sr: int) -> float:
    import pyloudnorm as pyln

    try:
        v = pyln.Meter(sr).integrated_loudness(np.asarray(x, np.float64))
    except ValueError:
        return float("-inf")
    return float(v)


def rms_db(x: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(np.asarray(x, np.float64) ** 2) + 1e-20))


def noise_floor_db(x: np.ndarray, sr: int) -> float:
    """Quietest 500 ms window RMS (how ACX checks the noise floor)."""
    w = int(0.5 * sr)
    if len(x) < w:
        return rms_db(x)
    e = np.convolve(np.asarray(x, np.float64) ** 2, np.ones(w) / w, mode="valid")[:: max(1, w // 10)]
    return float(10 * np.log10(np.min(e) + 1e-20))


def measure(x: np.ndarray, sr: int) -> dict:
    def r(v):
        return round(v, 2) if np.isfinite(v) else None

    return {
        "lufs": r(lufs(x, sr)),
        "true_peak_db": r(true_peak_db(x, sr)),
        "rms_db": r(rms_db(x)),
        "sample_peak_db": r(float(20 * np.log10(np.max(np.abs(x)) + 1e-12))) if len(x) else None,
        "noise_floor_db": r(noise_floor_db(x, sr)),
    }


def master(x: np.ndarray, sr: int, target: str) -> tuple[np.ndarray, float, dict]:
    """Bring the mix to the delivery target. Returns (audio, linear pre-limiter gain, report)."""
    t = TARGETS[target]
    x = np.asarray(x, np.float32)
    if target == "raw" or not np.any(x):
        m = measure(x, sr)
        return (
            x,
            1.0,
            {
                "target": t["label"],
                "measured": m,
                "met": True,
                "note": "Raw: levels untouched."
                + (" Peaks above 0 dBFS will clip." if (m["sample_peak_db"] or -99) > 0 else ""),
            },
        )
    if target == "acx":
        gain = 10 ** ((t["rms"] - rms_db(x)) / 20)
        y = x * gain
        ceiling = t["peak"]
        for _ in range(4):
            y2 = hz.soft_limit(y, sr, ceiling_db=ceiling)
            # limiting lowers RMS a little; correct once, then re-limit
            y2 = hz.soft_limit(y2 * 10 ** ((t["rms"] - rms_db(y2)) / 20), sr, ceiling_db=ceiling)
            if true_peak_db(y2, sr) <= -3.0:
                break
            ceiling -= 0.5
        m = measure(y2, sr)
        ok_rms = m["rms_db"] is not None and -23 <= m["rms_db"] <= -18
        ok_peak = m["true_peak_db"] is not None and m["true_peak_db"] <= -3.0
        nf = m["noise_floor_db"]
        ok_nf = nf is None or nf <= -60
        note = (
            f"ACX: RMS {m['rms_db']} dBFS (needs -23..-18) {'OK' if ok_rms else 'NOT MET'}; "
            f"peak {m['true_peak_db']} dBFS (needs <= -3) {'OK' if ok_peak else 'NOT MET'}; "
            f"noise floor {nf if nf is not None else 'digital silence'} (needs <= -60) {'OK' if ok_nf else 'NOT MET'}. "
            "Pauses are digital silence; ACX reviewers may ask for real room tone. ACX also wants 44.1 kHz MP3 (192 kbps+ CBR)."
        )
        return (
            y2.astype(np.float32),
            float(gain),
            {"target": t["label"], "measured": m, "met": ok_rms and ok_peak and ok_nf, "note": note},
        )
    goal, tp = t["lufs"], t["tp"]
    ceiling = tp - 0.3
    y = x
    gain = 1.0
    for _ in range(6):
        loud = lufs(x, sr)
        if not np.isfinite(loud):
            break
        gain = 10 ** ((goal - loud) / 20)
        y = hz.soft_limit(x * gain, sr, ceiling_db=ceiling)
        for _ in range(4):  # make up what the limiter took, limit again
            l2 = lufs(y, sr)
            if not np.isfinite(l2) or abs(goal - l2) <= 0.3:
                break
            y = hz.soft_limit(y * 10 ** ((goal - l2) / 20), sr, ceiling_db=ceiling)
        if true_peak_db(y, sr) <= tp:
            break
        ceiling -= 0.3
    m = measure(y, sr)
    met = m["lufs"] is not None and abs(m["lufs"] - goal) <= 1.0 and (m["true_peak_db"] or 0) <= tp
    note = f"Integrated {m['lufs']} LUFS (target {goal:g}), true peak {m['true_peak_db']} dBTP (max {tp:g}). " + (
        "Target met." if met else "Target NOT met: the content is too short or too peaky to reach it cleanly."
    )
    return y.astype(np.float32), float(gain), {"target": t["label"], "measured": m, "met": bool(met), "note": note}


# --------------------------------------------------------------------------- music bed
def duck_gain(
    voice: np.ndarray,
    sr: int,
    depth_db: float = 12.0,
    attack_ms: float = 80.0,
    release_ms: float = 400.0,
    threshold_db: float = -40.0,
) -> np.ndarray:
    """Per-sample gain (linear) for the music: drops by depth_db while the voice is speaking."""
    blk = max(1, sr // 100)  # 10 ms
    n = int(np.ceil(len(voice) / blk)) if len(voice) else 0
    if n == 0:
        return np.ones(0, np.float32)
    v = np.pad(np.asarray(voice, np.float64), (0, n * blk - len(voice))).reshape(n, blk)
    lvl = 10 * np.log10(np.mean(v**2, axis=1) + 1e-12)
    speech = lvl > threshold_db
    # hold through short gaps between words, and start ducking a little ahead of speech
    from scipy.ndimage import maximum_filter1d

    speech = maximum_filter1d(speech.astype(np.uint8), size=25, origin=-6).astype(bool)
    target = np.where(speech, -abs(depth_db), 0.0)
    a = np.exp(-10.0 / max(attack_ms, 1.0))
    r = np.exp(-10.0 / max(release_ms, 1.0))
    g = np.empty(n)
    acc = 0.0
    for i, tv in enumerate(target):
        c = a if tv < acc else r
        acc = c * acc + (1 - c) * tv
        g[i] = acc
    gs = np.interp(np.arange(len(voice)), np.arange(n) * blk + blk / 2, g)
    return (10 ** (gs / 20)).astype(np.float32)


def music_bed(
    path: Path,
    length: int,
    voice: np.ndarray,
    sr: int,
    level_db: float = -18.0,
    loop: bool = True,
    duck: bool = True,
    duck_db: float = 12.0,
    attack_ms: float = 80.0,
    release_ms: float = 400.0,
    fade_in: float = 1.0,
    fade_out: float = 2.0,
) -> np.ndarray:
    data, _ = aio.load(path, sr=sr)
    m = data.mean(axis=1).astype(np.float32) if data.ndim == 2 else data.astype(np.float32)
    if not len(m) or not np.any(m):
        raise StudioError("The music file has no audible audio.")
    if len(m) < length:
        m = np.tile(m, int(np.ceil(length / len(m)))) if loop else np.pad(m, (0, length - len(m)))
    m = m[:length]
    # level = music RMS in dBFS before ducking, so different songs sit the same way
    m = m * 10 ** ((level_db - rms_db(m)) / 20)
    if duck:
        m = m * duck_gain(voice, sr, duck_db, attack_ms, release_ms)
    fi, fo = int(fade_in * sr), int(fade_out * sr)
    if fi:
        m[:fi] *= np.linspace(0, 1, min(fi, len(m)))
    if fo:
        k = min(fo, len(m))
        m[len(m) - k :] *= np.linspace(1, 0, k)
    return m.astype(np.float32)


# --------------------------------------------------------------------------- captions
def _ts(t: float, sep: str) -> str:
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    mnt, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{mnt:02d}:{s:02d}{sep}{ms:03d}"


def _wrap(text: str, width: int = 42) -> str:
    words, rows, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    rows.append(cur)
    if len(rows) > 2:  # two-line max: rebalance by halves
        mid = len(words) // 2
        rows = [" ".join(words[:mid]), " ".join(words[mid:])]
    return "\n".join(rows)


def caption_cues(phrases: list[dict], max_chars: int = 84, max_dur: float = 6.0) -> list[dict]:
    """Phrases with absolute times -> readable cues (<= 2 x 42 chars, <= ~6 s). Long phrases are split by words,
    with time shared out by character count."""
    pieces = []
    for p in phrases:
        text = " ".join(p["text"].split())
        if not text:
            continue
        if len(text) <= max_chars:
            pieces.append({"start": p["start"], "end": p["end"], "text": text, "speaker": p.get("speaker", "")})
            continue
        words = text.split()
        parts: list[str] = []
        cur: list[str] = []
        for w in words:
            if cur and len(" ".join(cur + [w])) > max_chars * 0.6:
                parts.append(" ".join(cur))
                cur = [w]
            else:
                cur.append(w)
        parts.append(" ".join(cur))
        total = sum(len(x) for x in parts)
        t = p["start"]
        for x in parts:
            d = (p["end"] - p["start"]) * len(x) / total
            pieces.append({"start": t, "end": t + d, "text": x, "speaker": p.get("speaker", "")})
            t += d
    cues: list[dict] = []
    for pc in pieces:
        last = cues[-1] if cues else None
        if (
            last
            and last["speaker"] == pc["speaker"]
            and len(last["text"]) + 1 + len(pc["text"]) <= max_chars
            and pc["end"] - last["start"] <= max_dur
            and pc["start"] - last["end"] < 0.6
        ):
            last["text"] += " " + pc["text"]
            last["end"] = pc["end"]
        else:
            cues.append(dict(pc))
    return cues


def to_srt(cues: list[dict]) -> str:
    return "".join(
        f"{i}\n{_ts(c['start'], ',')} --> {_ts(c['end'], ',')}\n{_wrap(c['text'])}\n\n" for i, c in enumerate(cues, 1)
    )


def to_vtt(cues: list[dict]) -> str:
    return "WEBVTT\n\n" + "".join(
        f"{i}\n{_ts(c['start'], '.')} --> {_ts(c['end'], '.')}\n{_wrap(c['text'])}\n\n" for i, c in enumerate(cues, 1)
    )


# --------------------------------------------------------------------------- render job
@dataclass
class RenderOptions:
    target: str = "podcast"
    sample_rate: int = 24000
    format: str = "wav"
    stems: bool = False
    line_clips: bool = False
    captions: bool = True
    polish: bool = False
    stop_on_error: bool = False
    music: Path | None = None
    music_level_db: float = -18.0
    music_loop: bool = True
    duck: bool = True
    duck_db: float = 12.0
    attack_ms: float = 80.0
    release_ms: float = 400.0
    fade_in: float = 1.0
    fade_out: float = 2.0
    lead_in: float = 0.3
    target_duration: float | None = None
    room_tone: bool | None = None  # None = on for ACX only
    video: Path | None = None
    video_mode: str = "replace"  # replace | duck (keep original audio ducked under the dub)
    video_level_db: float = -6.0  # original audio level change in duck mode
    video_subs: bool = True
    extra: dict = field(default_factory=dict)


class Cancelled(Exception):
    pass


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")[:60] or "voice"


def write_audio(path_base: Path, x: np.ndarray, sr: int, fmt: str) -> Path:
    path = path_base.with_suffix(FORMATS[fmt])
    if fmt == "mp3":
        tmp = path_base.with_suffix(".tmp.wav")
        aio.save(tmp, x, sr)
        try:
            subprocess.run(
                [
                    aio._ffmpeg(),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(tmp),
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "320k",
                    str(path),
                ],
                check=True,
            )
        finally:
            tmp.unlink(missing_ok=True)
    else:
        aio.save(path, x, sr)
    return path


def _resample(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR:
        return x
    g = np.gcd(sr, SR)
    return signal.resample_poly(x, sr // g, SR // g).astype(np.float32)


def _render_project_lines(
    project: dict,
    opts: RenderOptions,
    prog: Callable[[str, float], None],
    cancel: threading.Event | None,
) -> tuple[list[tuple[int, np.ndarray, list[dict]]], list[dict], list[dict]]:
    """Render individual lines with the existing fitting and per-line error policy."""
    lines = project["lines"]
    dictionary = project.get("dictionary") or {}
    timed = project.get("mode") == "timed"
    rendered: list[tuple[int, np.ndarray, list[dict]]] = []
    errors: list[dict] = []
    line_fits: list[dict] = []
    if timed and not any(ln.get("start") is not None for ln in lines):
        raise StudioError("Timed mode needs start times. Import an .srt/.vtt file or give lines a start time.")
    for i, ln in enumerate(lines):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        prog(f"Rendering line {i + 1} of {len(lines)}", 0.85 * i / max(len(lines), 1))
        if not ln["text"].strip():
            continue
        try:
            slot = timed_slot(lines, i) if timed else None
            if slot is not None and not ln.get("target"):
                a, ph = render_line(ln, dictionary, opts.polish)
                if len(a) / SR > slot + 0.01:
                    a, ph, info = fit_line(ln, slot, dictionary, opts.polish, base=(a, ph))
                    line_fits.append({"line": i + 1, **info})
            elif ln.get("target"):
                a, ph, info = fit_line(ln, float(ln["target"]), dictionary, opts.polish)
                line_fits.append({"line": i + 1, **info})
            else:
                a, ph = render_line(ln, dictionary, opts.polish)
            rendered.append((i, a, ph))
        except Exception as e:  # one bad line must not kill the render unless asked
            expected = isinstance(e, (RuntimeError, ValueError, KeyError))
            if not expected:  # the user sees a generic sentence, so keep the real cause in the log
                log.exception("Studio line %d failed unexpectedly", i + 1)
            msg = str(e) if expected else "The voice engine failed on this line."
            msg = msg.strip("'\"") or "The voice engine failed on this line."
            errors.append({"line": i + 1, "id": ln.get("id"), "error": msg})
            if opts.stop_on_error:
                raise StudioError(f"Line {i + 1}: {msg}")
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    if not rendered:
        raise StudioError("No line could be rendered." + (f" First error: {errors[0]['error']}" if errors else ""))
    return rendered, errors, line_fits


def _place_project_lines(
    project: dict,
    opts: RenderOptions,
    rendered: list[tuple[int, np.ndarray, list[dict]]],
    pauses: list[float],
    head: float,
    tail: float,
) -> tuple[list[tuple[int, int, np.ndarray]], list[dict], list[dict], list[dict], int]:
    """Place rendered audio and caption phrases without changing the samples."""
    lines = project["lines"]
    timed = project.get("mode") == "timed"
    pos = int(head * SR)
    placed, timeline, phrases_abs = [], [], []
    overlaps: list[dict] = []
    for idx, a, ph in rendered:
        ln = lines[idx]
        if timed and ln.get("start") is not None:
            pos = int(round(float(ln["start"]) * SR))
            nxt = next(
                (
                    lines[j]["start"]
                    for j in range(idx + 1, len(lines))
                    if lines[j].get("start") is not None and lines[j]["text"].strip()
                ),
                None,
            )
            end_t = (pos + len(a)) / SR
            limit = ln.get("end") if ln.get("end") is not None else nxt
            if nxt is not None and end_t > nxt + 0.01:
                overlaps.append(
                    {
                        "line": idx + 1,
                        "kind": "overlap",
                        "by": round(end_t - nxt, 2),
                        "message": f"Line {idx + 1} runs {end_t - nxt:.2f} s into line {idx + 2}'s start; both are kept.",
                    }
                )
            elif limit is not None and end_t > limit + 0.01:
                overlaps.append(
                    {
                        "line": idx + 1,
                        "kind": "overrun",
                        "by": round(end_t - limit, 2),
                        "message": f"Line {idx + 1} ends {end_t - limit:.2f} s after its cue end (no overlap).",
                    }
                )
        placed.append((idx, pos, a))
        spk = ln.get("speaker") or ln["voice"]
        timeline.append(
            {
                "line": idx + 1,
                "id": ln.get("id"),
                "speaker": ln.get("speaker", ""),
                "voice": ln["voice"],
                "delivery": ln["delivery"],
                "start": round(pos / SR, 3),
                "end": round((pos + len(a)) / SR, 3),
                "text": ln["text"],
                "phrases": [
                    {"start": round(pos / SR + p["start"], 3), "end": round(pos / SR + p["end"], 3), "text": p["text"]}
                    for p in ph
                ],
            }
        )
        phrases_abs += [
            {"start": pos / SR + p["start"], "end": pos / SR + p["end"], "text": p["text"], "speaker": spk} for p in ph
        ]
        k = len(placed) - 1
        pos += len(a) + (int(round(pauses[k] * SR)) if k < len(pauses) else 0)
    total = max(st_ + len(a_) for _, st_, a_ in placed) + int(tail * SR)
    if timed:
        total = max(total, int(max((ln.get("end") or 0) for ln in lines) * SR) + int(tail * SR))
    video_len = None
    if opts.video is not None:
        video_len = int(round(probe_duration(opts.video) * SR))
        speech_end = max(st_ + len(a_) for _, st_, a_ in placed)
        if speech_end > video_len:
            overlaps.append(
                {
                    "line": placed[-1][0] + 1,
                    "kind": "past_video",
                    "by": round((speech_end - video_len) / SR, 2),
                    "message": f"Speech runs {(speech_end - video_len) / SR:.2f} s past the end of the video; "
                    "the dub keeps it (the picture holds its last frame).",
                }
            )
        total = max(video_len, speech_end)
    return placed, timeline, phrases_abs, overlaps, total


def _mix_project_tracks(
    lines: list[dict],
    opts: RenderOptions,
    placed: list[tuple[int, int, np.ndarray]],
    total: int,
    prog: Callable[[str, float], None],
) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray | None, np.ndarray | None]:
    """Build speaker stems and optional beds at the internal sample rate."""
    stems: dict[str, np.ndarray] = {}
    voice_bus = np.zeros(total, np.float32)
    for idx, start, a in placed:
        ln = lines[idx]
        key = ln.get("speaker") or ln["voice"]
        stems.setdefault(key, np.zeros(total, np.float32))[start : start + len(a)] += a
        voice_bus[start : start + len(a)] += a
    music = None
    if opts.music is not None:
        prog("Adding music bed", 0.88)
        music = music_bed(
            opts.music,
            total,
            voice_bus,
            SR,
            opts.music_level_db,
            opts.music_loop,
            opts.duck,
            opts.duck_db,
            opts.attack_ms,
            opts.release_ms,
            opts.fade_in,
            opts.fade_out,
        )
    original = None
    if opts.video is not None and opts.video_mode == "duck":
        prog("Ducking original audio", 0.89)
        original = original_bed(opts.video, total, voice_bus, opts)
    return voice_bus, stems, music, original


def _master_project_audio(mix: np.ndarray, sr: int, opts: RenderOptions) -> tuple[np.ndarray, float, dict]:
    """Master the mix and retain the optional room-tone compliance report."""
    mastered, gain, report = master(mix, sr, opts.target)
    tone_on = opts.room_tone if opts.room_tone is not None else opts.target == "acx"
    if tone_on and opts.target != "raw":
        mastered = (mastered + room_tone(len(mastered), sr)).astype(np.float32)
        report["measured"] = measure(mastered, sr)
        report["room_tone_db"] = ACX_ROOM_TONE_DB
        if opts.target == "acx":
            m = report["measured"]
            nf = m["noise_floor_db"]
            report["met"] = bool(-23 <= m["rms_db"] <= -18 and m["true_peak_db"] <= -3.0 and nf <= -60)
            report["note"] = (
                f"ACX: RMS {m['rms_db']} dBFS (needs -23..-18), peak {m['true_peak_db']} dBFS (needs <= -3), "
                f"noise floor {nf} dBFS (needs <= -60; room tone at {ACX_ROOM_TONE_DB:g} dBFS RMS fills pauses). "
                + ("All three met." if report["met"] else "NOT all met.")
                + (
                    ""
                    if (opts.format == "mp3" and sr == 44100)
                    else " ACX wants 44.1 kHz MP3 (192 kbps+ CBR) for upload."
                )
            )
    return mastered, gain, report


def render_project(
    project: dict, opts: RenderOptions, out_dir: Path, progress=None, cancel: threading.Event | None = None
) -> dict:
    """Render a validated project into out_dir. Returns a result dict with public file names."""
    t0 = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    prog = progress or (lambda step, f: None)
    lines = project["lines"]
    dictionary = project.get("dictionary") or {}
    warnings = lint_project(project)
    timed = project.get("mode") == "timed"
    rendered, errors, line_fits = _render_project_lines(project, opts, prog, cancel)
    head = TARGETS["acx"]["head"] if opts.target == "acx" else opts.lead_in
    tail = TARGETS["acx"]["tail"] if opts.target == "acx" else 0.5
    pauses = [float(lines[idx]["pause"]) for idx, _, _ in rendered[:-1]]
    fit = None
    if timed:
        head = 0.0
    elif opts.target_duration:
        prog("Fitting to time", 0.8)
        rendered, pauses, fit = fit_project(
            rendered, lines, pauses, head, tail, float(opts.target_duration), dictionary, opts.polish, cancel
        )
    prog("Mixing", 0.86)
    placed, timeline, phrases_abs, overlaps, total = _place_project_lines(project, opts, rendered, pauses, head, tail)
    voice_bus, stems, music, original = _mix_project_tracks(lines, opts, placed, total, prog)
    sr = int(opts.sample_rate)
    mix = voice_bus + (music if music is not None else 0) + (original if original is not None else 0)
    mix = _resample(mix, sr)
    prog("Mastering loudness", 0.9)
    mastered, gain, report = _master_project_audio(mix, sr, opts)
    if fit is not None:
        fit["achieved"] = round(len(mastered) / sr, 2)
        fit["met"] = abs(fit["achieved"] - fit["target"]) <= max(0.1, 0.01 * fit["target"])
    files: list[dict] = []
    title = _safe(project.get("title") or "studio")
    prog("Writing files", 0.94)
    p = write_audio(out_dir / f"{title}-mix", mastered, sr, opts.format)
    files.append({"name": p.name, "kind": "mix"})
    if opts.stems:
        allstems = dict(stems)
        if music is not None:
            allstems["music"] = music
        if original is not None:
            allstems["original"] = original
        for name, s in allstems.items():
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            s = _resample(s, sr) * gain  # same gain as the mix (before the limiter), so stems sum to ~the mix
            s = s[: len(mastered)] if len(s) >= len(mastered) else np.pad(s, (0, len(mastered) - len(s)))
            p = write_audio(out_dir / f"{title}-stem-{_safe(name)}", np.clip(s, -1, 1), sr, opts.format)
            files.append({"name": p.name, "kind": "stem", "speaker": name})
    if opts.line_clips:
        for idx, _, a in placed:
            p = write_audio(
                out_dir / f"{title}-line{idx + 1:03d}", np.clip(_resample(a * gain, sr), -1, 1), sr, opts.format
            )
            files.append({"name": p.name, "kind": "line", "line": idx + 1})
    cues = caption_cues(phrases_abs)
    if opts.captions:
        (out_dir / f"{title}.srt").write_text(to_srt(cues), encoding="utf-8")
        (out_dir / f"{title}.vtt").write_text(to_vtt(cues), encoding="utf-8")
        files += [{"name": f"{title}.srt", "kind": "captions"}, {"name": f"{title}.vtt", "kind": "captions"}]
    duration = len(mastered) / sr
    elapsed = time.time() - t0
    tl = {
        "title": project.get("title", ""),
        "duration": round(duration, 3),
        "sample_rate": sr,
        "target": opts.target,
        "loudness": report,
        "lines": timeline,
        "errors": errors,
        "captions": [{"start": round(c["start"], 3), "end": round(c["end"], 3), "text": c["text"]} for c in cues],
        "fit": fit,
        "line_fits": line_fits,
        "mode": "timed" if timed else "sequential",
        "overlaps": overlaps,
    }
    (out_dir / f"{title}-timeline.json").write_text(json.dumps(tl, indent=2), encoding="utf-8")
    files.append({"name": f"{title}-timeline.json", "kind": "timeline"})
    if opts.video is not None:
        prog("Muxing video", 0.96)
        vname = mux_video(opts.video, mastered, sr, out_dir / f"{title}-dub", cues if opts.video_subs else None)
        files.append({"name": vname, "kind": "video"})
    prog("Packing ZIP", 0.98)
    zip_name = f"{title}.zip"
    with zipfile.ZipFile(out_dir / zip_name, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for f in files:
            if f["kind"] != "line":
                z.write(out_dir / f["name"], f["name"])
            else:
                z.write(out_dir / f["name"], "lines/" + f["name"])
    return {
        "mode": tl["mode"],
        "overlaps": overlaps,
        "fit": fit,
        "line_fits": line_fits,
        "files": files,
        "zip": zip_name,
        "duration": round(duration, 2),
        "elapsed": round(elapsed, 2),
        "realtime_factor": round(duration / max(elapsed, 1e-6), 2),
        "loudness": report,
        "errors": errors,
        "warnings": warnings,
        "captions": tl["captions"],
        "lines": [{k: v for k, v in t.items() if k != "phrases"} for t in timeline],
    }


def timed_slot(lines: list[dict], i: int) -> float | None:
    """Seconds available for timed line i: its cue (start..end), or start..next start if no end."""
    ln = lines[i]
    if ln.get("start") is None:
        return None
    nxt = next(
        (
            lines[j]["start"]
            for j in range(i + 1, len(lines))
            if lines[j].get("start") is not None and lines[j]["text"].strip()
        ),
        None,
    )
    end = ln.get("end")
    if end is None:
        end = nxt
    if end is None:
        return None
    return max(0.3, float(end) - float(ln["start"]))


VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}


def probe_duration(path: Path) -> float:
    """Container duration via ffmpeg (no ffprobe needed)."""
    r = subprocess.run([aio._ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        raise StudioError("Could not read the video's length.")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def probe_streams(path: Path) -> dict:
    r = subprocess.run([aio._ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    return {
        "video": bool(re.search(r"Stream #\S+.*: Video:", r.stderr)),
        "audio": bool(re.search(r"Stream #\S+.*: Audio:", r.stderr)),
    }


def original_bed(video: Path, length: int, voice: np.ndarray, opts) -> np.ndarray | None:
    """The video's own audio at 24 kHz mono, level-adjusted and ducked under the dub."""
    if not probe_streams(video)["audio"]:
        return None
    data, _ = aio.load(video, sr=SR)
    m = data.mean(axis=1).astype(np.float32)
    m = np.pad(m, (0, max(0, length - len(m))))[:length] * 10 ** (opts.video_level_db / 20)
    if opts.duck:
        m = m * duck_gain(voice, SR, opts.duck_db, opts.attack_ms, opts.release_ms)
    return m.astype(np.float32)


def mux_video(video: Path, audio: np.ndarray, sr: int, base: Path, cues: list[dict] | None) -> str:
    """Copy the picture untouched (-c:v copy) and put the dub in as the audio track (+ soft subtitles)."""
    ext = video.suffix.lower()
    out = base.with_suffix(ext)
    tmp_wav = base.with_suffix(".mux.wav")
    tmp_srt = base.with_suffix(".mux.srt")
    import soundfile as sf

    sf.write(str(tmp_wav), audio, sr, subtype="PCM_24")
    cmd = [aio._ffmpeg(), "-y", "-loglevel", "error", "-i", str(video), "-i", str(tmp_wav)]
    maps = ["-map", "0:v", "-map", "1:a"]
    sub_codec: list[str] = []
    if cues:
        tmp_srt.write_text(to_srt(cues), encoding="utf-8")
        cmd += ["-i", str(tmp_srt)]
        maps += ["-map", "2:s"]
        sub_codec = [
            "-c:s",
            {".mp4": "mov_text", ".mov": "mov_text", ".webm": "webvtt", ".mkv": "srt"}[ext],
            "-metadata:s:s:0",
            "language=eng",
        ]
    acodec = ["-c:a", "libopus", "-b:a", "192k"] if ext == ".webm" else ["-c:a", "aac", "-b:a", "256k"]
    try:
        subprocess.run(cmd + maps + ["-c:v", "copy", *acodec, *sub_codec, str(out)], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        out.unlink(missing_ok=True)
        raise StudioError("Could not put the dub into this video. Try an MP4 (H.264) file.")
    finally:
        tmp_wav.unlink(missing_ok=True)
        tmp_srt.unlink(missing_ok=True)
    return out.name


def fit_project(rendered, lines, pauses, head, tail, target, dictionary, polish, cancel=None):
    """Fit the whole mix to `target` seconds: speed (safe range) -> fine stretch -> inter-line pauses."""
    fixed = head + tail
    free = [j for j, (idx, _, _) in enumerate(rendered) if not lines[idx].get("target")]

    def length():
        return fixed + sum(len(a) for _, a, _ in rendered) / SR + sum(pauses)

    start = length()
    locked = sum(len(rendered[j][1]) for j in range(len(rendered)) if j not in free) / SR
    speech = sum(len(rendered[j][1]) for j in free) / SR
    room = target - fixed - sum(pauses) - locked
    need = speech / room if room > 0 else float("inf")
    warn = []
    f = float(np.clip(need, *SAFE_SPEED)) if np.isfinite(need) else SAFE_SPEED[1]
    if not SAFE_SPEED[0] <= need <= SAFE_SPEED[1]:
        warn.append(
            f"Fitting {start:.1f} s into {target:g} s needs {need:.2f}x tempo; capped at the safe "
            f"{SAFE_SPEED[0]}-{SAFE_SPEED[1]}x range, then pauses were adjusted."
        )
    out = list(rendered)
    if abs(f - 1) > 0.01:
        for j in free:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            idx = out[j][0]
            ln = lines[idx]
            a, ph = render_line({**ln, "speed": float(np.clip(ln["speed"] * f, 0.5, 2.0))}, dictionary, polish)
            out[j] = (idx, a, ph)
    rendered[:] = out
    speech2 = sum(len(rendered[j][1]) for j in free) / SR
    r = speech2 / room if room > 0 else STRETCH_FINE[1]
    lo, hi = max(STRETCH_FINE[0], SAFE_SPEED[0] / f), min(STRETCH_FINE[1], SAFE_SPEED[1] / f)
    r = float(np.clip(r, min(lo, 1.0), max(hi, 1.0)))
    if abs(r - 1) > 0.002 and free:
        for j in free:
            idx, a, ph = rendered[j]
            b = time_stretch(a, r)
            rendered[j] = (idx, b, _scale_phrases(ph, len(b) / max(len(a), 1)))
    # last: move the inter-line pauses (each kept between 0.1 s and 3 s, or its own value if larger)
    diff = target - length()
    new = list(pauses)
    if pauses and abs(diff) > 0.005:
        lo_b = [min(p, 0.1) for p in pauses]
        hi_b = [max(p, 3.0) for p in pauses]
        for _ in range(20):
            open_ = [k for k in range(len(new)) if (diff > 0 and new[k] < hi_b[k]) or (diff < 0 and new[k] > lo_b[k])]
            if not open_ or abs(diff) < 0.001:
                break
            step = diff / len(open_)
            for k in open_:
                v = float(np.clip(new[k] + step, lo_b[k], hi_b[k]))
                diff -= v - new[k]
                new[k] = v
    if abs(target - (length() - sum(pauses) + sum(new))) > max(0.1, 0.01 * target):
        warn.append("Could not reach the target within the safe limits; shorten or lengthen the script.")
    return (
        rendered,
        new,
        {
            "target": round(target, 2),
            "start": round(start, 2),
            "speed_factor": round(f, 3),
            "stretch": round(r, 3),
            "pause_change": round(sum(new) - sum(pauses), 2),
            "warnings": warn,
        },
    )


# --------------------------------------------------------------------------- projects on disk
def projects_dir() -> Path:
    from . import voices as vlib

    return vlib.DATA_DIR / "projects"


# --------------------------------------------------------------------------- CLI
def cli_render(a) -> dict:
    """Shared by `naturalvoice render` and `naturalvoice dub`; validates exactly like the API."""
    from pydantic import ValidationError

    from .studio_api import Project

    if a.cmd == "dub":
        src = Path(a.subtitles)
        if src.suffix.lower() not in {".srt", ".vtt"}:
            raise StudioError("Subtitles must be an .srt or .vtt file.")
        if src.stat().st_size > MAX_SUB_BYTES:
            raise StudioError("Subtitle file too large (2 MB max).")
        if not VOICE_ID.match(a.voice):
            raise StudioError(f"Invalid voice id {a.voice!r}.")
        raw = src.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        parsed = parse_subtitles(text, a.voice)
        data = {"title": src.stem, "mode": "timed", "lines": parsed["lines"]}
        base, pre_warn, rate, stems = src, parsed["warnings"], None, False
    else:
        src = Path(a.project)
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except ValueError as e:
            raise StudioError(f"{src.name} is not valid JSON: {e}")
        if isinstance(data, dict) and "project" in data:  # a file saved by the web app
            data = data["project"]
        base, pre_warn, rate, stems = src, [], a.rate, a.stems
    try:
        project = Project.model_validate(data).model_dump()
    except ValidationError as e:
        msgs = "; ".join(f"{'.'.join(map(str, er['loc']))}: {er['msg']}" for er in e.errors()[:5])
        raise StudioError(f"Invalid project: {msgs}")
    if not any(ln["text"].strip() for ln in project["lines"]):
        raise StudioError("The project has no lines with text.")
    video = None
    if a.video:
        video = Path(a.video)
        if video.suffix.lower() not in VIDEO_EXTS or not video.is_file():
            raise StudioError("Video must be an existing MP4, MOV, WebM or MKV file.")
        if not probe_streams(video)["video"]:
            raise StudioError("That file has no video picture.")
    if rate is None:
        rate = 44100 if a.target == "acx" else (48000 if video else 24000)
    out = Path(a.out) if a.out else base.with_name(base.stem + "-render")
    opts = RenderOptions(
        target=a.target, format=a.format, sample_rate=rate, stems=stems, video=video, video_mode=a.video_audio
    )
    res = render_project(project, opts, out, progress=lambda s, f: print(f"[{int(f * 100):3d}%] {s}", file=sys.stderr))
    m = res["loudness"]["measured"]
    return {
        "out_dir": str(out),
        "files": [f["name"] for f in res["files"]] + [res["zip"]],
        "duration": res["duration"],
        "elapsed": res["elapsed"],
        "target": res["loudness"]["target"],
        "target_met": res["loudness"]["met"],
        "lufs": m["lufs"],
        "true_peak_db": m["true_peak_db"],
        "rms_db": m["rms_db"],
        "noise_floor_db": m["noise_floor_db"],
        "note": res["loudness"]["note"],
        "warnings": pre_warn + res["warnings"],
        "errors": res["errors"],
        "overlaps": res["overlaps"],
        "line_fits": res["line_fits"],
    }
