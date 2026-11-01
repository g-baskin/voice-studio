"""Shark engine: directed, chunked, streamable performances on the local voices.

The interaction design follows ideas Fish Audio published for its speech models: speaker turns,
inline [directions] anywhere in the text, sentence-first chunking that never cuts a cue in half,
audio that arrives chunk by chunk, retakes, and spoken revisions such as "gentler, a bit sadder".
None of their code or models are used. Kokoro and Chatterbox have no emotion model, so every
direction is performed with the controls they do have and reported as applied, approximated or
not available, instead of pretending.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

import numpy as np

from . import studio as st

MAX_CHARS = 20_000
MAX_CHUNKS = 200
MAX_SPEAKERS = 20
CHUNK_CHARS = 280  # long enough for natural phrasing, short enough to hear the first chunk quickly
SENTENCE_GAP = 0.25  # seconds between chunks of one turn
TURN_GAP = 0.45  # seconds between speaker turns

# Bracketed spans are never split: directions, [pause 1s], [break] and clone sound tags.
PROTECTED = re.compile(r"\[[^\[\]\n]{0,40}\]")
SENTENCE_END = re.compile(r"(?<=[.!?…])[\"')\]]?\s+")
CLAUSE_END = re.compile(r"(?<=[,;:])\s+")


@dataclass(frozen=True)
class Direction:
    note: str  # a director's note studio.parse_note understands
    exact: bool  # False when the voice can only approximate it (no real whisper, shout or tears)


# Our own vocabulary. Each maps to the delivery, speed, pitch and loudness controls the engines have.
DIRECTIONS: dict[str, Direction] = {
    "whisper": Direction("barely audible, slower, calm", exact=False),
    "soft": Direction("softly, calm", exact=True),
    "gentle": Direction("gently, calm", exact=True),
    "calm": Direction("calm", exact=True),
    "warm": Direction("warm", exact=True),
    "happy": Direction("upbeat, brighter", exact=False),
    "cheerful": Direction("upbeat, brighter", exact=False),
    "excited": Direction("excited", exact=True),
    "energetic": Direction("energetic", exact=True),
    "sad": Direction("sad, slower", exact=False),
    "serious": Direction("serious", exact=True),
    "angry": Direction("stern, louder, faster", exact=False),
    "shout": Direction("louder, energetic", exact=False),
    "tired": Direction("tired", exact=False),
    "surprised": Direction("surprised", exact=False),
    "laughing": Direction("laughing", exact=False),
    "slow": Direction("slower", exact=True),
    "fast": Direction("faster", exact=True),
    "louder": Direction("louder", exact=True),
    "quieter": Direction("quieter", exact=True),
    "deeper": Direction("deeper", exact=True),
    "higher": Direction("higher", exact=True),
}
ALIASES = {
    "whispering": "whisper",
    "softly": "soft",
    "gently": "gentle",
    "sadly": "sad",
    "angrily": "angry",
    "shouting": "shout",
    "yelling": "shout",
    "laugh": "laughing",
    "slower": "slow",
    "faster": "fast",
    "quiet": "quieter",
    "loud": "louder",
    "gentler": "gentle",
    "softer": "soft",
    "calmer": "calm",
    "warmer": "warm",
    "sadder": "sad",
    "happier": "happy",
    "angrier": "angry",
}


class SharkError(ValueError):
    """A problem with the script the user can fix; the message is safe to show."""


@dataclass
class Chunk:
    index: int
    speaker: str
    voice: str
    text: str
    line: dict  # studio line controls this chunk renders with
    readout: list[dict] = field(default_factory=list)
    pause_after: float = SENTENCE_GAP

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "speaker": self.speaker,
            "voice": self.voice,
            "text": self.text,
            "readout": self.readout,
            "pause_after": self.pause_after,
            "controls": {k: self.line[k] for k in ("speed", "pitch", "volume", "delivery")},
        }


def direction_name(tag: str) -> str | None:
    body = tag.strip().lower()
    body = ALIASES.get(body, body)
    return body if body in DIRECTIONS else None


def split_turns(script: str) -> list[tuple[str, str]]:
    """(speaker, text) turns. `Name: text` starts a turn; other lines continue the current speaker.

    Unlike Studio, a leading `[word]` is never a speaker here: in Speak it is always a direction or
    cue, so `[whisper] Hello` and an unknown `[sparkle] Hello` are both read and reported as tags.
    """
    turns: list[tuple[str, str]] = []
    speaker = ""
    for raw in script.splitlines():
        body = raw.strip()
        if not body:
            continue
        m = st.SPEAKER_COLON.match(body)
        if m:
            speaker, body = m.group(1).strip(), m.group(2).strip()
            if body:
                turns.append((speaker, body))
            continue
        if turns and turns[-1][0] == speaker:
            turns[-1] = (speaker, turns[-1][1] + " " + body)
        else:
            turns.append((speaker, body))
    return turns


def _pieces(text: str) -> list[tuple[str, bool]]:
    """Text split into (piece, protected) so cue spans stay whole."""
    out, pos = [], 0
    for m in PROTECTED.finditer(text):
        if m.start() > pos:
            out.append((text[pos : m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def _split_free(text: str, rx: re.Pattern[str]) -> list[str]:
    parts, pos = [], 0
    for m in rx.finditer(text):
        parts.append(text[pos : m.end()])
        pos = m.end()
    parts.append(text[pos:])
    return [p for p in parts if p]


def _atoms(text: str, limit: int) -> list[str]:
    """Smallest units to pack: sentences, then clauses, then words, never splitting a protected span."""
    atoms: list[str] = []
    for piece, protected in _pieces(text):
        if protected:
            atoms.append(piece)
            continue
        for sentence in _split_free(piece, SENTENCE_END):
            if len(sentence) <= limit:
                atoms.append(sentence)
                continue
            for clause in _split_free(sentence, CLAUSE_END):
                atoms += [clause] if len(clause) <= limit else re.findall(r"\S+\s*", clause)
    return atoms


def chunk_text(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Pack text into chunks of at most `limit` characters, preferring sentence ends.

    A chunk that would be only a cue, such as [pause 1s], joins the next chunk, and a single word or
    cue longer than the limit stays whole rather than being cut.
    """
    text = " ".join(text.split())
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    current = ""
    for atom in _atoms(text, limit):
        sentence_ended = bool(re.search(r"[.!?…][\"')\]]?\s*$", current))
        if current and len(current) + len(atom) > limit:
            chunks.append(current)
            current = ""
        elif current and sentence_ended and len(current) >= limit * 0.6:
            chunks.append(current)
            current = ""
        current += atom
    if current.strip():
        chunks.append(current)
    # A chunk ending in a cue would move the cue away from the words it directs.
    merged: list[str] = []
    for chunk in (c.strip() for c in chunks):
        if merged and PROTECTED.fullmatch(merged[-1]):
            merged[-1] = f"{merged[-1]} {chunk}"
        else:
            merged.append(chunk)
    return [c for c in merged if c]


def _runs(text: str, sound_tags: set[str]) -> list[tuple[list[str], str]]:
    """Text split at direction tags: [(directions in force, text)]. A direction lasts to the next one.

    Tags in `sound_tags` (a cloned voice's own sounds, such as [laugh]) stay inline as sounds.
    """
    runs: list[tuple[list[str], str]] = []
    active: list[str] = []
    pending: list[str] = []
    pos = 0
    for m in PROTECTED.finditer(text):
        body = m.group(0)[1:-1].strip().lower()
        name = None if body in sound_tags else direction_name(body)
        if name is None:
            continue
        before = text[pos : m.start()]
        if before.strip():
            runs.append((active, before))
            pending = []
        pending.append(name)
        active = list(dict.fromkeys(pending))
        pos = m.end()
    if text[pos:].strip():
        runs.append((active, text[pos:]))
    return runs


def _readout(name: str, understood: list[str], clone: bool) -> dict:
    d = DIRECTIONS[name]
    status = "applied" if d.exact else "approximated"
    how = "; ".join(understood) or "no change was possible"
    if not d.exact and not clone:
        how += f". Built-in voices can't truly perform [{name}]; this is the closest delivery."
    return {"tag": name, "status": status, "how": how}


def _remove_unusable(text: str, clone: bool, clone_tags: set[str]) -> tuple[str, list[dict]]:
    """Drop bracketed tags this voice can't use, so they are not read aloud, and say why."""
    notes: list[dict] = []

    def sub(m: re.Match[str]) -> str:
        body = m.group(0)[1:-1].strip()
        low = body.lower()
        if low in clone_tags and clone:
            return m.group(0)  # the cloned voice makes this sound itself
        if direction_name(low) or st.PAUSE_TAG.match(low) or low == "break":
            return m.group(0)
        if low in clone_tags:
            notes.append({"tag": low, "status": "unavailable", "how": "only cloned voices can make this sound"})
            return " "
        notes.append({"tag": body, "status": "unknown", "how": "not a direction Shark knows; removed"})
        return " "

    return " ".join(PROTECTED.sub(sub, text).split()), notes


def plan(
    script: str,
    cast: dict[str, str] | None = None,
    voice: str = "af_heart",
    clone_tags: list[str] | None = None,
) -> list[Chunk]:
    """Script -> chunks with their controls and an honest readout. Renders nothing."""
    if len(script) > MAX_CHARS:
        raise SharkError(f"Script is too long ({MAX_CHARS:,} characters max).")
    if not st.VOICE_ID.match(voice):
        raise SharkError("Unknown default voice.")
    ctags = {t.lower() for t in (clone_tags if clone_tags is not None else st.clone_emotion_tags())}
    cast_by_key = {k.strip().lower(): v for k, v in (cast or {}).items() if st.VOICE_ID.match(v)}
    turns = split_turns(script)
    if not turns:
        raise SharkError("Write something for Shark to perform.")
    assigned: dict[str, str] = {}
    chunks: list[Chunk] = []
    for t, (speaker, body) in enumerate(turns):
        key = speaker.lower()
        if key not in assigned:
            if len(assigned) >= MAX_SPEAKERS:
                raise SharkError(f"Use at most {MAX_SPEAKERS} speakers.")
            fallback = st.DEFAULT_CAST[len(assigned) % len(st.DEFAULT_CAST)] if speaker else voice
            assigned[key] = cast_by_key.get(key, fallback)
        voice_id = assigned[key]
        clone = voice_id.startswith("clone:")
        text, notes = _remove_unusable(body, clone, ctags)
        turn_chunks: list[Chunk] = []
        for directions, run_text in _runs(text, ctags if clone else set()):
            line = st.new_line(run_text, voice_id, speaker)
            readout = list(notes)
            notes = []
            if directions:
                note = ", ".join(DIRECTIONS[d].note for d in directions)
                res = st.parse_note(note, line, sorted(ctags))
                line.update({k: res[k] for k in ("speed", "pitch", "volume", "delivery", "text")})
                readout += [_readout(d, res["understood"], clone) for d in directions]
            for piece in chunk_text(line["text"]):
                c = Chunk(len(chunks) + len(turn_chunks), speaker, voice_id, piece, {**line, "text": piece}, readout)
                readout = []
                turn_chunks.append(c)
        if turn_chunks and t < len(turns) - 1:
            turn_chunks[-1].pause_after = TURN_GAP
        chunks += turn_chunks
        if len(chunks) > MAX_CHUNKS:
            raise SharkError(f"Script is too long to perform at once ({MAX_CHUNKS} chunks max). Split it up.")
    if not chunks:
        raise SharkError("There are no words to perform, only tags. Add some text after them.")
    chunks[-1].pause_after = 0.0
    return chunks


def _note_words(instruction: str) -> str:
    """Rewrite direction words ("whisper", "sadder") as notes studio.parse_note understands."""

    def sub(m: re.Match[str]) -> str:
        name = direction_name(m.group(0))
        return DIRECTIONS[name].note if name else m.group(0)

    return re.sub(r"[A-Za-z]+", sub, instruction)


def revise(chunk: Chunk, instruction: str, clone_tags: list[str] | None = None) -> tuple[dict, list[str], list[str]]:
    """New controls for a chunk from a plain-language note such as "gentler, a bit sadder"."""
    ctags = clone_tags if clone_tags is not None else st.clone_emotion_tags()
    res = st.parse_note(_note_words(instruction), chunk.line, ctags)
    line = {**chunk.line, **{k: res[k] for k in ("speed", "pitch", "volume", "delivery", "text")}}
    return line, res["understood"], res["unused"]


def render(line: dict, take: int = 0) -> np.ndarray:
    """One chunk at studio.SR, through the same cached renderer as Studio."""
    audio, _ = st.render_line({**line, "take": take})
    return audio


def assemble(parts: list[tuple[np.ndarray, float]]) -> np.ndarray:
    """Chunks joined with their pauses, as one track at studio.SR."""
    pieces: list[np.ndarray] = []
    for audio, pause in parts:
        pieces.append(np.asarray(audio, np.float32))
        if pause > 0:
            pieces.append(np.zeros(int(pause * st.SR), np.float32))
    return np.concatenate(pieces) if pieces else np.zeros(0, np.float32)


def new_job_id() -> str:
    return uuid.uuid4().hex
