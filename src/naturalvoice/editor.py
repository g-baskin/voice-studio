"""Editor: a local media bin, saved sequences and ffmpeg export of a multi-track timeline."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from xml.sax.saxutils import escape

import numpy as np
from pydantic import BaseModel, Field, model_validator

from . import audio as aio
from . import voices
from .sample_library import atomic_json

MAX_BYTES = 2 * 1024**3
MAX_SECONDS = 4 * 3600
MAX_LAYERS = 200
VIDEO_EXTS = frozenset({".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"})
AUDIO_EXTS = frozenset({".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aif", ".aiff"})
IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
EXTS = VIDEO_EXTS | AUDIO_EXTS | IMAGE_EXTS
PEAKS_PER_SECOND = 50
THUMB_W, THUMB_H = 96, 54
MAX_THUMBS = 200
PROXY_HEIGHT = 540
SAMPLE_RATE = 48000
FPS_RATES = {23.976: "24000/1001", 24.0: "24", 25.0: "25", 29.97: "30000/1001", 30.0: "30", 50.0: "50"}
FPS_RATES |= {59.94: "60000/1001", 60.0: "60"}
QUALITY = {"high": ("medium", 18), "standard": ("veryfast", 22), "draft": ("ultrafast", 28)}
_ID = re.compile(r"[0-9a-f]{32}")
# Uploaded files must be real media: playlist and concat demuxers could make ffmpeg fetch URLs or read other files.
INPUT_GUARD = [
    "-protocol_whitelist",
    "file",
    "-format_whitelist",
    "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,wav,mp3,aac,flac,ogg,aiff,image2,png_pipe,jpeg_pipe,webp_pipe",
]
_SHORT_ID = r"^[A-Za-z0-9_-]{1,24}$"


class EditorError(Exception):
    """A user-facing problem with media, a sequence or an export."""


class Cancelled(EditorError):
    pass


def root() -> Path:
    return voices.DATA_DIR / "editor"


def identifier(value: str) -> str:
    if not _ID.fullmatch(value):
        raise EditorError("Invalid identifier.")
    return value


def media_dir(media_id: str) -> Path:
    return root() / "media" / identifier(media_id)


def sequence_path(sequence_id: str) -> Path:
    return root() / "sequences" / f"{identifier(sequence_id)}.json"


# --------------------------------------------------------------------------- sequence model
class Track(BaseModel):
    id: str = Field(pattern=_SHORT_ID)
    kind: Literal["video", "audio"]
    name: str = Field(min_length=1, max_length=40)
    muted: bool = False
    hidden: bool = False
    locked: bool = False
    volume: float = Field(0, ge=-60, le=12)
    duck: bool = False
    # Timeline row height in pixels; None keeps the default for the track kind.
    height: int | None = Field(None, ge=24, le=240)


class Transition(BaseModel):
    kind: Literal["dissolve"] = "dissolve"
    duration: float = Field(1.0, ge=0.04, le=5)


class Clip(BaseModel):
    id: str = Field(pattern=_SHORT_ID)
    track: str = Field(pattern=_SHORT_ID)
    media: str = Field(pattern=r"^[0-9a-f]{32}$")
    start: float = Field(ge=0, le=MAX_SECONDS)
    source_in: float = Field(ge=0, le=MAX_SECONDS)
    source_out: float = Field(gt=0, le=MAX_SECONDS)
    speed: float = Field(1, ge=0.25, le=4)
    volume: float = Field(0, ge=-60, le=12)
    muted: bool = False
    fade_in: float = Field(0, ge=0, le=10)
    fade_out: float = Field(0, ge=0, le=10)
    transition: Transition | None = None
    fit: Literal["fit", "fill"] = "fit"
    scale: float = Field(1, ge=0.1, le=5)
    x: float = Field(0, ge=-2, le=2)
    y: float = Field(0, ge=-2, le=2)
    opacity: float = Field(1, ge=0, le=1)

    @property
    def duration(self) -> float:
        return (self.source_out - self.source_in) / self.speed

    @property
    def end(self) -> float:
        return self.start + self.duration


class Marker(BaseModel):
    time: float = Field(ge=0, le=MAX_SECONDS)
    label: str = Field("", max_length=60)


class Sequence(BaseModel):
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=80)
    width: int = Field(1920, ge=128, le=4096, multiple_of=2)
    height: int = Field(1080, ge=128, le=4096, multiple_of=2)
    fps: float = 30.0
    duck_db: float = Field(12, ge=0, le=30)
    loudness: float | None = Field(None, ge=-30, le=-9)
    range_in: float | None = Field(None, ge=0, le=MAX_SECONDS)
    range_out: float | None = Field(None, ge=0, le=MAX_SECONDS)
    tracks: list[Track] = Field(min_length=1, max_length=16)
    clips: list[Clip] = Field(default_factory=list, max_length=2000)
    markers: list[Marker] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _consistent(self) -> Sequence:
        if self.fps not in FPS_RATES:
            raise ValueError("Unsupported frame rate.")
        tracks = {t.id: t for t in self.tracks}
        if len(tracks) != len(self.tracks):
            raise ValueError("Track ids must be unique.")
        if len({c.id for c in self.clips}) != len(self.clips):
            raise ValueError("Clip ids must be unique.")
        frame = 1 / self.fps
        for clip in self.clips:
            if clip.track not in tracks:
                raise ValueError("A clip refers to a missing track.")
            if clip.source_out <= clip.source_in or clip.duration < frame / 2:
                raise ValueError("Every clip must be at least one frame long.")
            if clip.end > MAX_SECONDS:
                raise ValueError("Sequences are limited to 4 hours.")
        for track in self.tracks:
            on_track = sorted((c for c in self.clips if c.track == track.id), key=lambda c: c.start)
            for a, b in zip(on_track, on_track[1:]):
                if b.start < a.end - 1e-3:
                    raise ValueError(f"Clips overlap on {track.name}.")
        if self.range_in is not None and self.range_out is not None and self.range_out <= self.range_in:
            raise ValueError("The out point must come after the in point.")
        return self

    @property
    def duration(self) -> float:
        return max((c.end for c in self.clips), default=0.0)


# --------------------------------------------------------------------------- media bin
def probe(path: Path) -> dict:
    """Streams and size via ffmpeg's own report (ffprobe is not required)."""
    r = subprocess.run([aio._ffmpeg(), "-hide_banner", *INPUT_GUARD, "-i", str(path)], capture_output=True, text=True)
    text = r.stderr
    found = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    duration = int(found[1]) * 3600 + int(found[2]) * 60 + float(found[3]) if found else None
    video_line = next(
        (m[1] for m in re.finditer(r"Stream #\S+.*?: Video: (.*)", text) if "attached pic" not in m[1]), None
    )
    width = height = 0
    fps = 0.0
    if video_line:
        size = re.search(r"\b(\d{2,5})x(\d{2,5})\b", video_line)
        if size:
            width, height = int(size[1]), int(size[2])
        rate = re.search(r"([\d.]+) (?:fps|tbr)", video_line)
        fps = float(rate[1]) if rate else 0.0
        rotation = re.search(r"rotation of (-?[\d.]+) degrees", text)
        # ffmpeg applies the rotation when decoding, so the picture's shape follows it.
        if rotation and round(abs(float(rotation[1]))) % 180 == 90:
            width, height = height, width
    return {
        "duration": duration,
        "video": bool(video_line and width and height),
        "audio": bool(re.search(r"Stream #\S+.*?: Audio:", text)),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
    }


def media_record(media_id: str) -> dict:
    path = media_dir(media_id) / "media.json"
    if not path.is_file():
        raise EditorError("That media is not in the bin.")
    return json.loads(path.read_text(encoding="utf-8"))


def list_media() -> list[dict]:
    base = root() / "media"
    if not base.is_dir():
        return []
    found = []
    for folder in sorted(base.iterdir()):
        meta = folder / "media.json"
        if _ID.fullmatch(folder.name) and meta.is_file():
            found.append(json.loads(meta.read_text(encoding="utf-8")))
    return sorted(found, key=lambda m: (m["created"], m["id"]))


def kind_for(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in VIDEO_EXTS:
        return "video"
    if suffix in AUDIO_EXTS:
        return "audio"
    if suffix in IMAGE_EXTS:
        return "image"
    raise EditorError("Use a video (MP4, MOV, WebM, MKV), audio (WAV, MP3, M4A, FLAC) or image (PNG, JPG) file.")


def new_media(name: str, now: float | None = None) -> tuple[dict, Path]:
    """Create a media folder for an upload; returns its record and the path to write the file to."""
    clean = Path(name).name.strip()[:120] or "Untitled"
    kind = kind_for(clean)
    media_id = uuid.uuid4().hex
    folder = media_dir(media_id)
    folder.mkdir(parents=True)
    record = {
        "id": media_id,
        "name": clean,
        "kind": kind,
        "file": "source" + Path(clean).suffix.lower(),
        "status": "uploading",
        "error": None,
        "created": time.time() if now is None else now,
        "size": 0,
        "duration": None,
        "width": 0,
        "height": 0,
        "fps": 0.0,
        "has_audio": False,
        "has_video": False,
        "thumbs": None,
        "peaks_per_second": PEAKS_PER_SECOND,
    }
    return record, folder / str(record["file"])


def save_media(record: dict) -> None:
    atomic_json(media_dir(record["id"]) / "media.json", record)


def _run(cmd: list[str], message: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise EditorError(message)


def peaks(path: Path, duration: float) -> list[int]:
    """Peak level per 1/50 s (0 to 255) of the file's first audio stream, read as a stream."""
    rate = 8000
    block = rate // PEAKS_PER_SECOND
    proc = subprocess.Popen(
        [aio._ffmpeg(), "-v", "error", *INPUT_GUARD, "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", str(rate)]
        + ["-f", "s16le", "pipe:1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert proc.stdout is not None
    out: list[int] = []
    rest = np.zeros(0, dtype=np.int16)
    limit = math.ceil(duration * PEAKS_PER_SECOND) + PEAKS_PER_SECOND
    try:
        while chunk := proc.stdout.read(block * 2 * 4096):
            data = np.concatenate([rest, np.frombuffer(chunk[: len(chunk) // 2 * 2], dtype=np.int16)])
            whole = len(data) // block * block
            if whole:
                levels = np.abs(data[:whole].astype(np.int32)).reshape(-1, block).max(axis=1)
                out.extend(np.minimum(255, levels * 255 // 32767).astype(int).tolist())
            rest = data[whole:]
            if len(out) > limit:
                break
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()
    if len(rest):
        out.append(min(255, int(np.abs(rest.astype(np.int32)).max()) * 255 // 32767))
    return out[:limit]


def thumbnail_plan(duration: float) -> tuple[float, int]:
    interval = max(1.0, duration / MAX_THUMBS)
    return interval, max(1, math.ceil(duration / interval))


def process_media(media_id: str) -> dict:
    """Probe an upload and build its preview proxy, filmstrip and waveform."""
    record = media_record(media_id)
    folder = media_dir(media_id)
    source = folder / record["file"]
    ff = aio._ffmpeg()
    info = probe(source)
    kind = record["kind"]
    if kind == "video" and not info["video"]:
        kind = "audio"  # a container holding only sound, such as an exported podcast
    if kind == "audio" and not info["audio"]:
        raise EditorError("That file has no sound.")
    if kind == "image" and not info["video"]:
        raise EditorError("Could not read that image.")
    if kind != "image" and not info["duration"]:
        raise EditorError("Could not read the file's length.")
    if kind != "image" and info["duration"] > MAX_SECONDS:
        raise EditorError("Media longer than 4 hours is not supported.")
    fit = f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=decrease,pad={THUMB_W}:{THUMB_H}:(ow-iw)/2:(oh-ih)/2"
    thumbs = None
    if kind == "video":
        _run(
            [ff, "-y", "-v", "error", *INPUT_GUARD, "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", "-vf"]
            + [f"scale=-2:'min({PROXY_HEIGHT},ih)':flags=bicubic,format=yuv420p", "-c:v", "libx264"]
            + ["-preset", "veryfast", "-crf", "26", "-g", "15", "-c:a", "aac", "-b:a", "128k", "-ac", "2"]
            + ["-movflags", "+faststart", str(folder / "proxy.mp4")],
            "Could not prepare a preview of that video.",
        )
        interval, count = thumbnail_plan(info["duration"])
        _run(
            [ff, "-y", "-v", "error", *INPUT_GUARD, "-i", str(folder / "proxy.mp4"), "-vf"]
            + [f"fps=1/{interval:.6f},{fit},tile={count}x1", "-frames:v", "1", "-q:v", "5", str(folder / "thumbs.jpg")],
            "Could not make the video's filmstrip.",
        )
        thumbs = {"count": count, "interval": interval, "width": THUMB_W, "height": THUMB_H}
    elif kind == "audio":
        _run(
            [
                ff,
                "-y",
                "-v",
                "error",
                *INPUT_GUARD,
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-ac",
                "2",
            ]
            + ["-movflags", "+faststart", str(folder / "proxy.m4a")],
            "Could not prepare a preview of that audio.",
        )
    else:
        _run(
            [ff, "-y", "-v", "error", *INPUT_GUARD, "-i", str(source), "-vf", fit, "-frames:v", "1", "-q:v", "4"]
            + [str(folder / "thumbs.jpg")],
            "Could not make the image's thumbnail.",
        )
        thumbs = {"count": 1, "interval": 1.0, "width": THUMB_W, "height": THUMB_H}
    has_audio = kind != "image" and info["audio"]
    levels = peaks(source, info["duration"]) if has_audio else []
    atomic_json(folder / "peaks.json", {"peaks_per_second": PEAKS_PER_SECOND, "peaks": levels})
    record.update(
        kind=kind,
        status="ready",
        error=None,
        duration=None if kind == "image" else round(info["duration"], 3),
        width=info["width"],
        height=info["height"],
        fps=info["fps"],
        has_audio=has_audio,
        has_video=kind != "audio",
        thumbs=thumbs,
    )
    save_media(record)
    return record


def proxy_file(media_id: str) -> Path:
    record = media_record(media_id)
    folder = media_dir(media_id)
    name = {"video": "proxy.mp4", "audio": "proxy.m4a"}.get(record["kind"], record["file"])
    path = folder / name
    if record["status"] != "ready" or not path.is_file():
        raise EditorError("That media is not ready yet.")
    return path


def users_of(media_id: str) -> list[str]:
    return sorted(s["name"] for s in list_sequences(full=True) if any(c["media"] == media_id for c in s["clips"]))


def delete_media(media_id: str) -> None:
    folder = media_dir(media_id)
    media_record(media_id)
    used = users_of(media_id)
    if used:
        raise EditorError("Remove it from these sequences first: " + ", ".join(used[:5]))
    shutil.rmtree(folder)


# --------------------------------------------------------------------------- sequences
def list_sequences(full: bool = False) -> list[dict]:
    base = root() / "sequences"
    if not base.is_dir():
        return []
    found = []
    for path in sorted(base.glob("*.json")):
        if not _ID.fullmatch(path.stem):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        found.append(data if full else {k: data[k] for k in ("id", "name", "updated")})
    return sorted(found, key=lambda s: (-s["updated"], s["id"]))


def read_sequence(sequence_id: str) -> dict:
    path = sequence_path(sequence_id)
    if not path.is_file():
        raise EditorError("That sequence no longer exists.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_sequence(sequence: Sequence, sequence_id: str | None = None, now: float | None = None) -> dict:
    if sequence_id is not None and not sequence_path(sequence_id).is_file():
        raise EditorError("That sequence no longer exists.")
    sequence_id = sequence_id or uuid.uuid4().hex
    record = sequence.model_dump() | {"id": sequence_id, "updated": time.time() if now is None else now}
    atomic_json(sequence_path(sequence_id), record)
    return record


def delete_sequence(sequence_id: str) -> None:
    path = sequence_path(sequence_id)
    if not path.is_file():
        raise EditorError("That sequence no longer exists.")
    path.unlink()


# --------------------------------------------------------------------------- render plan
@dataclass(frozen=True)
class Layer:
    """One clip's contribution to the render, including transition handles."""

    clip: Clip
    media: dict
    z: int
    t0: float  # timeline time where the layer starts, including a transition lead-in
    t1: float
    src0: float  # source time shown at t0
    fade_in: float  # picture
    fade_out: float
    afade_in: float  # sound
    afade_out: float
    picture: bool
    sound: bool
    gain_db: float
    duck: bool

    @property
    def length(self) -> float:
        return self.t1 - self.t0


def handles(clip: Clip, media: dict) -> tuple[float, float]:
    """Timeline seconds of unused source media before the in point and after the out point."""
    if media["kind"] == "image":
        return math.inf, math.inf
    after = max(0.0, (media["duration"] or 0) - clip.source_out) / clip.speed
    return clip.source_in / clip.speed, after


def transition_half(prev: Clip, prev_media: dict, clip: Clip, media: dict, fps: float) -> float:
    """Half the usable dissolve length, centred on the cut and limited by both clips' handles."""
    if clip.transition is None or abs(prev.end - clip.start) > 1 / fps:
        return 0.0
    half = min(clip.transition.duration / 2, handles(prev, prev_media)[1], handles(clip, media)[0])
    half = min(half, prev.duration, clip.duration)
    return half if half >= 0.5 / fps else 0.0


def plan(seq: Sequence, media: dict[str, dict]) -> list[Layer]:
    order = {t.id: i for i, t in enumerate(reversed(seq.tracks))}  # first track draws on top
    layers: list[Layer] = []
    for track in seq.tracks:
        clips = sorted((c for c in seq.clips if c.track == track.id), key=lambda c: c.start)
        lead = [0.0] * len(clips)
        for i in range(1, len(clips)):
            lead[i] = transition_half(clips[i - 1], media[clips[i - 1].media], clips[i], media[clips[i].media], seq.fps)
        for i, clip in enumerate(clips):
            m = media[clip.media]
            tail = lead[i + 1] if i + 1 < len(clips) else 0.0
            picture = track.kind == "video" and m["kind"] != "audio" and not track.hidden
            sound = m["has_audio"] and not clip.muted and not track.muted
            if not picture and not sound:
                continue
            layers.append(
                Layer(
                    clip=clip,
                    media=m,
                    z=order[track.id],
                    t0=clip.start - lead[i],
                    t1=clip.end + tail,
                    src0=clip.source_in - lead[i] * clip.speed,
                    fade_in=2 * lead[i] if lead[i] else clip.fade_in,
                    fade_out=0.0 if tail else clip.fade_out,  # the incoming clip dissolves over this one
                    afade_in=2 * lead[i] if lead[i] else clip.fade_in,
                    afade_out=2 * tail if tail else clip.fade_out,
                    picture=picture,
                    sound=sound,
                    gain_db=clip.volume + track.volume,
                    duck=track.kind == "audio" and track.duck,
                )
            )
    return sorted(layers, key=lambda layer: (layer.z, layer.t0, layer.clip.id))


def placement(seq: Sequence, clip: Clip, media: dict) -> tuple[int, int, int, int]:
    """Scaled size and top-left position of a picture on the output frame."""
    mw, mh = media["width"], media["height"]
    base = (min if clip.fit == "fit" else max)(seq.width / mw, seq.height / mh)
    w = max(2, round(mw * base * clip.scale / 2) * 2)
    h = max(2, round(mh * base * clip.scale / 2) * 2)
    x = round((seq.width - w) / 2 + clip.x * seq.width)
    y = round((seq.height - h) / 2 + clip.y * seq.height)
    return w, h, x, y


def atempo(speed: float) -> list[str]:
    steps = []
    while speed > 2.0:
        steps.append("atempo=2")
        speed /= 2.0
    while speed < 0.5:
        steps.append("atempo=0.5")
        speed /= 0.5
    if abs(speed - 1.0) > 1e-6:
        steps.append(f"atempo={_n(speed)}")
    return steps


def export_range(seq: Sequence, in_out: bool) -> tuple[float, float]:
    end = seq.duration
    if not in_out:
        return 0.0, end
    start = seq.range_in or 0.0
    stop = min(seq.range_out if seq.range_out is not None else end, end)
    return start, stop


def _n(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def build_command(
    seq: Sequence, media: dict[str, dict], out: Path, in_out: bool = False, quality: str = "standard"
) -> tuple[list[str], str, float]:
    """The ffmpeg arguments, the filter graph and the output length for one export."""
    start, stop = export_range(seq, in_out)
    total = stop - start
    if total < 1 / seq.fps:
        raise EditorError("There is nothing to export. Add clips, or move the in and out points apart.")
    layers = [layer for layer in plan(seq, media) if layer.t1 > start and layer.t0 < stop]
    if len(layers) > MAX_LAYERS:
        raise EditorError(f"This range uses more than {MAX_LAYERS} clips. Export a shorter in-to-out range.")
    rate = FPS_RATES[seq.fps]
    W, H = seq.width, seq.height
    args = [aio._ffmpeg(), "-y", "-v", "error", "-nostats", "-progress", "pipe:1"]
    args += ["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={rate}:d={_n(total)}"]
    args += ["-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=stereo:d={_n(total)}"]
    graph: list[str] = []
    pictures: list[tuple[str, int, int]] = []
    sounds: list[tuple[str, bool]] = []
    for k, layer in enumerate(layers, start=2):
        clip, m = layer.clip, layer.media
        cut = max(0.0, start - layer.t0)  # part of the layer before the export range
        keep = min(layer.t1, stop) - layer.t0
        offset = max(layer.t0, start) - start
        path = media_dir(m["id"]) / m["file"]
        if m["kind"] == "image":
            args += ["-loop", "1", "-framerate", rate, "-t", _n(keep * clip.speed), *INPUT_GUARD, "-i", str(path)]
        else:
            args += ["-ss", _n(max(0.0, layer.src0)), "-t", _n(keep * clip.speed + 0.1), *INPUT_GUARD, "-i", str(path)]
        if layer.picture:
            w, h, x, y = placement(seq, clip, m)
            chain = [f"setpts=(PTS-STARTPTS)/{_n(clip.speed)}", f"fps={rate}", f"trim=end={_n(keep)}"]
            chain += [f"scale={w}:{h}", "setsar=1", "format=yuva420p"]
            if layer.fade_in:
                chain.append(f"fade=t=in:st=0:d={_n(layer.fade_in)}:alpha=1")
            if layer.fade_out and keep >= layer.length - 1e-6:
                chain.append(f"fade=t=out:st={_n(layer.length - layer.fade_out)}:d={_n(layer.fade_out)}:alpha=1")
            if clip.opacity < 1:
                chain.append(f"colorchannelmixer=aa={_n(clip.opacity)}")
            if cut:
                chain.append(f"trim=start={_n(cut)}")
            chain.append(f"setpts=PTS-STARTPTS+{_n(offset)}/TB")
            graph.append(f"[{k}:v]{','.join(chain)}[v{k}]")
            pictures.append((f"v{k}", x, y))
        if layer.sound:
            chain = [f"aresample={SAMPLE_RATE}", "aformat=sample_fmts=fltp:channel_layouts=stereo"]
            chain += atempo(clip.speed) + [f"atrim=end={_n(keep)}", "asetpts=PTS-STARTPTS"]
            chain.append(f"volume={_n(layer.gain_db)}dB")
            if layer.afade_in:
                chain.append(f"afade=t=in:st=0:d={_n(layer.afade_in)}:curve=tri")
            if layer.afade_out and keep >= layer.length - 1e-6:
                chain.append(f"afade=t=out:st={_n(layer.length - layer.afade_out)}:d={_n(layer.afade_out)}:curve=tri")
            if cut:
                chain += [f"atrim=start={_n(cut)}", "asetpts=PTS-STARTPTS"]
            delay = round(offset * 1000)
            if delay:
                chain.append(f"adelay={delay}:all=1")
            graph.append(f"[{k}:a]{','.join(chain)}[a{k}]")
            sounds.append((f"a{k}", layer.duck))
    last = "0:v"
    for i, (label, x, y) in enumerate(pictures):
        graph.append(f"[{last}][{label}]overlay=x={x}:y={y}:eof_action=pass:format=auto[o{i}]")
        last = f"o{i}"
    graph.append(f"[{last}]format=yuv420p[vout]")

    def mix(labels: list[str], name: str) -> str:
        if len(labels) == 1:
            graph.append(f"[{labels[0]}]anull[{name}]")
        else:
            joined = "".join(f"[{s}]" for s in labels)
            graph.append(f"{joined}amix=inputs={len(labels)}:normalize=0:duration=longest:dropout_transition=0[{name}]")
        return name

    speech = [s for s, duck in sounds if not duck]
    music = [s for s, duck in sounds if duck]
    parts = ["1:a"]
    if speech and music and seq.duck_db > 0:
        mix(speech, "speech")
        mix(music, "music")
        graph.append("[speech]asplit=2[speech_out][speech_key]")
        amount = 1 - 10 ** (-seq.duck_db / 20)
        graph.append(
            "[music][speech_key]sidechaincompress=threshold=0.02:ratio=20:attack=20:release=400"
            f":mix={_n(amount)}[ducked]"
        )
        parts += ["speech_out", "ducked"]
    else:
        parts += speech + music
    mix(parts, "mixed")
    tail = ["[mixed]"]
    if seq.loudness is not None:
        tail.append(f"loudnorm=I={_n(seq.loudness)}:TP=-1.5:LRA=11,aresample={SAMPLE_RATE},")
    # A brick-wall limiter keeps the mix from clipping when tracks add up past full scale.
    tail.append(f"alimiter=limit=0.891:level=false,apad,atrim=end={_n(total)}[aout]")
    graph.append("".join(tail))
    preset, crf = QUALITY[quality]
    args += ["-/filter_complex", str(out.with_suffix(".graph.txt")), "-map", "[vout]", "-map", "[aout]"]
    args += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", rate]
    args += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", _n(total), str(out)]
    return args, ";\n".join(graph), total


def media_for(seq: Sequence) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for clip in seq.clips:
        if clip.media in found:
            continue
        try:
            record = media_record(clip.media)
        except EditorError:
            raise EditorError("A clip's media is missing from the bin. Remove or replace that clip.") from None
        if record["status"] != "ready":
            raise EditorError(f"{record['name']} is still being prepared. Wait, then export again.")
        found[clip.media] = record
    return found


def render(
    seq: Sequence,
    out: Path,
    in_out: bool,
    quality: str,
    progress: Callable[[float], None],
    cancel: threading.Event,
) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    args, graph, total = build_command(seq, media_for(seq), out, in_out, quality)
    out.with_suffix(".graph.txt").write_text(graph, encoding="utf-8")
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None and proc.stderr is not None
    errors: list[str] = []
    reader = threading.Thread(target=lambda: errors.extend(proc.stderr.readlines()), daemon=True)  # type: ignore[union-attr]
    reader.start()
    try:
        for line in proc.stdout:
            if cancel.is_set():
                proc.terminate()
                break
            if line.startswith("out_time_us="):
                value = line.split("=", 1)[1].strip()
                if value.isdigit():
                    progress(min(0.99, int(value) / 1e6 / total))
        proc.wait()
        reader.join(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        out.with_suffix(".graph.txt").unlink(missing_ok=True)
    if cancel.is_set():
        out.unlink(missing_ok=True)
        raise Cancelled("Export cancelled.")
    if proc.returncode or not out.is_file():
        out.unlink(missing_ok=True)
        detail = errors[-1].strip() if errors else "unknown ffmpeg error"
        raise EditorError(f"Export failed: {detail[:300]}")
    return out


# --------------------------------------------------------------------------- Premiere Pro (FCP 7 XML)
def _frames(seconds: float, fps: float) -> int:
    return round(seconds * fps)


def _rate(fps: float) -> str:
    ntsc = "TRUE" if fps in (23.976, 29.97, 59.94) else "FALSE"
    return f"<rate><timebase>{round(fps)}</timebase><ntsc>{ntsc}</ntsc></rate>"


def premiere_xml(seq: Sequence, media: dict[str, dict]) -> str:
    """An FCP 7 XML (xmeml v4) sequence that Premiere Pro imports with cuts, tracks and dissolves."""
    fps = seq.fps
    rate = _rate(fps)
    written: set[str] = set()
    counter = iter(range(1, 1_000_000))

    def file_element(m: dict) -> str:
        fid = f"file-{m['id'][:12]}"
        if fid in written:
            return f'<file id="{fid}"/>'
        written.add(fid)
        path = (media_dir(m["id"]) / m["file"]).resolve()
        length = _frames(m["duration"], fps) if m["duration"] else _frames(MAX_SECONDS, fps)
        parts = [f'<file id="{fid}"><name>{escape(m["name"])}</name>']
        parts.append(f"<pathurl>file://localhost{quote(str(path))}</pathurl>{rate}<duration>{length}</duration><media>")
        if m["has_video"]:
            parts.append(
                f"<video><samplecharacteristics>{rate}<width>{m['width']}</width><height>{m['height']}</height>"
                "</samplecharacteristics></video>"
            )
        if m["has_audio"]:
            parts.append(
                f"<audio><samplecharacteristics><depth>16</depth><samplerate>{SAMPLE_RATE}</samplerate>"
                "</samplecharacteristics><channelcount>2</channelcount></audio>"
            )
        parts.append("</media></file>")
        return "".join(parts)

    def effect(name: str, effect_id: str, category: str, kind: str, mediatype: str, params: str) -> str:
        return (
            f"<filter><effect><name>{name}</name><effectid>{effect_id}</effectid><effectcategory>{category}"
            f"</effectcategory><effecttype>{kind}</effecttype><mediatype>{mediatype}</mediatype>{params}"
            "</effect></filter>"
        )

    def param(pid: str, name: str, lo: float, hi: float, value: float) -> str:
        return (
            f"<parameter><parameterid>{pid}</parameterid><name>{name}</name><valuemin>{_n(lo)}</valuemin>"
            f"<valuemax>{_n(hi)}</valuemax><value>{_n(value)}</value></parameter>"
        )

    def clipitem(clip: Clip, m: dict, mediatype: str, gain_db: float) -> str:
        start = _frames(clip.start, fps)
        end = _frames(clip.end, fps)
        # Retimed clips state in/out in sequence frames; the speed filter maps them back to the source.
        src_in = _frames(clip.source_in / clip.speed, fps)
        src_out = src_in + (end - start)
        length = _frames((m["duration"] or MAX_SECONDS) / clip.speed, fps)
        parts = [
            f'<clipitem id="clipitem-{next(counter)}"><name>{escape(m["name"])}</name><enabled>TRUE</enabled>',
            f"<duration>{length}</duration>{rate}<start>{start}</start><end>{end}</end>",
            f"<in>{src_in}</in><out>{src_out}</out>{file_element(m)}",
        ]
        if mediatype == "audio":
            parts.append("<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>")
        if abs(clip.speed - 1) > 1e-6:
            parts.append(
                effect(
                    "Time Remap",
                    "timeremap",
                    "motion",
                    "motion",
                    "video",
                    param("speed", "speed", -100000, 100000, clip.speed * 100),
                )
            )
        if mediatype == "video" and clip.opacity < 1:
            parts.append(
                effect(
                    "Opacity",
                    "opacity",
                    "motion",
                    "motion",
                    "video",
                    param("opacity", "opacity", 0, 100, clip.opacity * 100),
                )
            )
        if mediatype == "audio" and abs(gain_db) > 1e-6:
            level = min(3.98109, 10 ** (gain_db / 20))
            parts.append(
                effect(
                    "Audio Levels",
                    "audiolevels",
                    "audiolevels",
                    "audiolevels",
                    "audio",
                    param("level", "Level", 0, 3.98109, level),
                )
            )
        parts.append("</clipitem>")
        return "".join(parts)

    def dissolve(prev: Clip, clip: Clip, mediatype: str) -> str:
        half = transition_half(prev, media[prev.media], clip, media[clip.media], fps)
        if not half:
            return ""
        name = "Cross Dissolve" if mediatype == "video" else "Cross Fade (+3dB)"
        category = "Dissolve" if mediatype == "video" else "crossfade"
        return (
            f"<transitionitem>{rate}<start>{_frames(clip.start - half, fps)}</start>"
            f"<end>{_frames(clip.start + half, fps)}</end><alignment>center</alignment><effect><name>{name}</name>"
            f"<effectid>{name}</effectid><effectcategory>{category}</effectcategory>"
            f"<effecttype>transition</effecttype><mediatype>{mediatype}</mediatype></effect></transitionitem>"
        )

    def track_xml(track: Track, mediatype: str, clips: list[Clip]) -> str:
        items = []
        for i, clip in enumerate(clips):
            if i and clip.transition:
                items.append(dissolve(clips[i - 1], clip, mediatype))
            items.append(clipitem(clip, media[clip.media], mediatype, clip.volume + track.volume))
        enabled = "FALSE" if (track.hidden if mediatype == "video" else track.muted) else "TRUE"
        locked = "TRUE" if track.locked else "FALSE"
        return f"<track>{''.join(items)}<enabled>{enabled}</enabled><locked>{locked}</locked></track>"

    def on(track: Track) -> list[Clip]:
        return sorted((c for c in seq.clips if c.track == track.id), key=lambda c: c.start)

    video_tracks = [t for t in reversed(seq.tracks) if t.kind == "video"]  # V1 is the bottom track
    audio_tracks = [t for t in seq.tracks if t.kind == "audio"]
    video = [track_xml(t, "video", [c for c in on(t) if media[c.media]["has_video"]]) for t in video_tracks]
    audio = []
    for t in video_tracks:
        sound = [c for c in on(t) if media[c.media]["has_audio"] and not c.muted]
        if sound:
            audio.append(track_xml(t, "audio", sound))
    audio += [
        track_xml(t, "audio", [c for c in on(t) if media[c.media]["has_audio"] and not c.muted]) for t in audio_tracks
    ]
    markers = "".join(
        f"<marker><name>{escape(m.label)}</name><comment></comment><in>{_frames(m.time, fps)}</in><out>-1</out></marker>"
        for m in sorted(seq.markers, key=lambda m: m.time)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">'
        f'<sequence id="sequence-1"><name>{escape(seq.name)}</name><duration>{_frames(seq.duration, fps)}</duration>'
        f"{rate}<media><video><format><samplecharacteristics>{rate}<width>{seq.width}</width>"
        f"<height>{seq.height}</height><pixelaspectratio>square</pixelaspectratio></samplecharacteristics></format>"
        f"{''.join(video)}</video><audio><numOutputChannels>2</numOutputChannels><format><samplecharacteristics>"
        f"<depth>16</depth><samplerate>{SAMPLE_RATE}</samplerate></samplecharacteristics></format>{''.join(audio)}"
        f"</audio></media>{markers}</sequence></xmeml>\n"
    )
