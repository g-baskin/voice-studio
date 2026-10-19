"""Local, append-only media sources, reviewed samples and versioned clone references.

User audio remains under NATURALVOICE_DATA. New files precede atomic metadata publication;
old references are never overwritten. Back up the whole data directory, not just JSON.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from . import voices

ENGINE = Path(__file__).resolve().parents[2] / "engines" / "media"
MAX_BYTES = 250 * 1024 * 1024
QUOTA = 2 * 1024**3
_ID = re.compile(r"[0-9a-f]{32}")
EXTS = frozenset({".wav", ".mp3", ".mp4", ".m4a", ".flac", ".webm", ".ogg", ".mov", ".mkv", ".opus"})


def root() -> Path:
    return voices.DATA_DIR / "sample-library"


def identifier(value: str) -> str:
    if not _ID.fullmatch(value):
        raise ValueError("Invalid library identifier.")
    return value


def location(kind: str, key: str) -> Path:
    if kind not in {"sources", "people", "samples"}:
        raise ValueError("Invalid library category.")
    return root() / kind / identifier(key)


def atomic_json(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(record, stream, allow_nan=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def read(kind: str, key: str) -> dict:
    try:
        return json.loads((location(kind, key) / "record.json").read_text())
    except FileNotFoundError:
        raise KeyError("Library item not found.") from None


def records(kind: str) -> list[dict]:
    result = []
    for path in sorted((root() / kind).glob("*/record.json")):
        result.append(read(kind, path.parent.name))
    return sorted(result, key=lambda rec: (rec["created"], rec["id"]), reverse=True)


@contextlib.contextmanager
def writing() -> Iterator[None]:
    """Serialize publication across threads and local server processes."""
    root().mkdir(parents=True, exist_ok=True)
    with (root() / ".write.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def capacity(reserve: int = MAX_BYTES + 100 * 1024**2) -> None:
    root().mkdir(parents=True, exist_ok=True)
    used = sum(path.stat().st_size for path in root().rglob("*") if path.is_file())
    if used + reserve > QUOTA:
        raise ValueError(
            "Sample library reached its 2 GB budget. Back up and move the data directory before importing more."
        )
    if shutil.disk_usage(root()).free < reserve + 1024**3:
        raise ValueError("Keep at least 1 GB of free disk space after this operation.")


def installed() -> bool:
    return (ENGINE / ".venv/bin/python").is_file() and all(
        (ENGINE / "models" / name).is_file()
        for name in ("segmentation.onnx", "embedding.onnx", "vocals.onnx", "accompaniment.onnx")
    )


def youtube_url(value: str) -> str:
    """Only canonical public YouTube video IDs ever reach the downloader."""
    try:
        url = urlsplit(value.strip())
        if url.scheme != "https" or url.username or url.password or url.port not in (None, 443):
            raise ValueError
        if url.hostname == "youtu.be":
            key = url.path.removeprefix("/")
        elif url.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if url.path == "/watch":
                key = parse_qs(url.query).get("v", [""])[0]
            elif url.path.startswith(("/shorts/", "/embed/")):
                key = url.path.split("/")[-1]
            else:
                raise ValueError
        else:
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", key):
            raise ValueError
    except ValueError:
        raise ValueError("Use an HTTPS YouTube video link, not a playlist or another website.") from None
    return f"https://www.youtube.com/watch?v={key}"


def validate_window(start: float, seconds: float) -> None:
    if not math.isfinite(start) or not 0 <= start <= 28800:
        raise ValueError("Start must be between 0 and 28,800 seconds.")
    if not math.isfinite(seconds) or not 5 <= seconds <= 120:
        raise ValueError("Analyze 5 to 120 seconds per import.")


def decode(src: Path, dst: Path, start: float, seconds: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-format_whitelist",
            "wav,mp3,mov,matroska,webm,ogg,flac,aac",
            "-ss",
            str(start),
            "-i",
            str(src),
            "-t",
            str(seconds),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(dst),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=90,
    )
    if sf.info(dst).duration < 0.5:
        raise ValueError("No playable audio in that time range.")


def download(url: str, folder: Path) -> Path:
    subprocess.run(
        [
            str(ENGINE / ".venv/bin/python"),
            str(ENGINE / "download.py"),
            "--ignore-config",
            "--no-playlist",
            "--no-cache-dir",
            "--no-progress",
            "--no-warnings",
            "--quiet",
            "--no-part",
            "--no-continue",
            "--socket-timeout",
            "15",
            "--retries",
            "1",
            "--max-filesize",
            str(MAX_BYTES),
            "--match-filter",
            "duration <= 1800 & !is_live",
            "--use-extractors",
            "youtube",
            "-f",
            "bestaudio[protocol=https][filesize<250M]/bestaudio[protocol=https][filesize_approx<250M]",
            "-o",
            str(folder / "input.%(ext)s"),
            "--",
            youtube_url(url),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=300,
    )
    files = list(folder.glob("input.*"))
    if len(files) != 1 or files[0].suffix not in EXTS or not 0 < files[0].stat().st_size <= MAX_BYTES:
        raise ValueError("Could not import this public YouTube video. Upload a permitted local copy instead.")
    return files[0]


def process_source(key: str) -> None:
    record = read("sources", key)
    folder = location("sources", key)
    try:
        src = download(record["url"], folder) if record["url"] else folder / record["input"]
        record["input"] = src.name
        record["step"] = "Extracting the selected audio window"
        atomic_json(folder / "record.json", record)
        decode(src, folder / "original.wav", record["start"], record["seconds"])
        record["step"] = "Separating background and detecting speakers" if record["separate"] else "Detecting speakers"
        atomic_json(folder / "record.json", record)
        result = subprocess.run(
            [str(ENGINE / ".venv/bin/python"), str(ENGINE / "worker.py")],
            input=json.dumps(
                {"path": str(folder / "original.wav"), "separate": record["separate"], "speakers": record["speakers"]}
            ),
            text=True,
            capture_output=True,
            check=True,
            timeout=900,
        )
        analysis = json.loads(result.stdout)
        duration = float(analysis["duration"])
        if not math.isfinite(duration) or not 0 < duration <= 121 or len(analysis["segments"]) > 2000:
            raise ValueError("Invalid analysis result.")
        for turn in analysis["segments"]:
            if not (0 <= turn["start"] < turn["end"] <= duration + 0.01 and 0 <= turn["speaker"] < 100):
                raise ValueError("Invalid speaker timeline.")
        record.update(analysis, status="done", step="Ready for review")
    except Exception:
        # Do not expose subprocess output (paths, downloaded metadata) or discard source recordings.
        record.update(
            status="error",
            step="Import failed",
            error="Could not analyze this media. Check the engine setup and audio range, then retry. "
            "For unavailable YouTube videos, upload a permitted local copy.",
        )
    atomic_json(folder / "record.json", record)


def public_source(record: dict) -> dict:
    result = {k: v for k, v in record.items() if k not in {"input", "pid"}}
    if result["status"] == "running" and record.get("pid") != os.getpid():
        result.update(status="error", error="The server restarted during this import. Retry the saved source.")
    return result


def create_person(name: str, consent: bool) -> dict:
    name = name.strip()
    if not name or len(name) > 60:
        raise ValueError("Give this person a name (1 to 60 characters).")
    if not consent:
        raise ValueError("Confirm that you own this voice or have permission to clone it.")
    key = uuid.uuid4().hex
    record = {"id": key, "name": name, "created": time.time(), "consent": True, "active": None}
    with writing():
        capacity(4096)
        atomic_json(location("people", key) / "record.json", record)
    return record


def add_sample(person: str, source: str, start: float, end: float, cleaned: bool, consent: bool) -> dict:
    if not consent:
        raise ValueError("Listen to the selection and confirm it contains only the permitted person's voice.")
    if not all(math.isfinite(v) for v in (start, end)) or not 0.5 <= end - start <= 60 or start < 0:
        raise ValueError("Select 0.5 to 60 seconds of one person's speech.")
    with writing():
        read("people", person)
        origin = read("sources", source)
        if origin["status"] != "done" or end > origin["duration"] + 0.001:
            raise ValueError("Select a range inside a completed source.")
        turns = origin["segments"]
        if any(
            a["speaker"] != b["speaker"] and max(start, a["start"], b["start"]) < min(end, a["end"], b["end"])
            for index, a in enumerate(turns)
            for b in turns[index + 1 :]
        ):
            raise ValueError("This selection includes detected overlapping voices. Trim to solo speech.")
        capacity(12 * 1024**2)
        path = location("sources", source) / ("dialogue.wav" if cleaned else "original.wav")
        with sf.SoundFile(path) as audio:
            audio.seek(round(start * audio.samplerate))
            data = audio.read(round((end - start) * audio.samplerate), dtype="float32", always_2d=True)
            rate = audio.samplerate
        mono = data.mean(axis=1)
        if len(mono) < 0.5 * rate or not np.isfinite(mono).all() or np.max(np.abs(mono)) < 0.0001:
            raise ValueError("The selection is empty or silent. Choose audible solo speech.")
        key = uuid.uuid4().hex
        folder = location("samples", key)
        folder.mkdir(parents=True)
        sf.write(folder / "audio.wav", mono, rate, subtype="PCM_16")
        record = {
            "id": key,
            "person": person,
            "source": source,
            "source_name": origin["name"],
            "start": start,
            "end": end,
            "seconds": len(mono) / rate,
            "cleaned": cleaned,
            "created": time.time(),
            "consent": True,
            "rms_db": round(20 * math.log10(max(float(np.sqrt(np.mean(mono**2))), 1e-9)), 1),
            "clipped": bool(np.mean(np.abs(mono) >= 0.999) > 0.001),
        }
        atomic_json(folder / "record.json", record)
    return record


def versions(person: str) -> list[dict]:
    identifier(person)
    return [v for v in voices.list_custom() if v.get("meta", {}).get("sample_person") == person]


def build_version(person: str, sample_ids: list[str]) -> dict:
    if not 1 <= len(sample_ids) <= 40 or len(set(sample_ids)) != len(sample_ids):
        raise ValueError("Select 1 to 40 distinct samples.")
    with writing():
        who = read("people", person)
        selected = [read("samples", key) for key in sample_ids]
        if any(s["person"] != person for s in selected):
            raise ValueError("Every sample must belong to this person.")
        total = sum(s["seconds"] for s in selected)
        if not 5 <= total <= 20:
            raise ValueError("Select 5 to 20 seconds total. Add shorter selections to control the reference length.")
        capacity(2 * 1024**2)
        parts = []
        for sample in selected:
            x, rate = sf.read(location("samples", sample["id"]) / "audio.wav", dtype="float32")
            x = resample_poly(x, 24000 // math.gcd(rate, 24000), rate // math.gcd(rate, 24000)).astype(np.float32)
            n = min(192, len(x) // 2)
            x[:n] *= np.linspace(0, 1, n)
            x[-n:] *= np.linspace(1, 0, n)
            parts.append(x)
        data = np.concatenate(parts)
        sequence = max((v["meta"]["reference_version"] for v in versions(person)), default=0) + 1
        with tempfile.TemporaryDirectory(dir=root()) as temp:
            ref = Path(temp) / "reference.wav"
            sf.write(ref, data, 24000, subtype="PCM_16")
            return voices.save_clone(
                f"{who['name'][:48]} v{sequence}",
                ref,
                {
                    "sample_person": person,
                    "sample_ids": sample_ids,
                    "reference_version": sequence,
                    "consent": True,
                    "consent_at": time.time(),
                    "seconds": len(data) / 24000,
                    "engine": "Chatterbox-Turbo (ONNX)",
                    "method": "reference-selection-not-training",
                },
            )


def activate(person: str, voice: str) -> dict:
    with writing():
        record = read("people", person)
        if voice not in {v["id"] for v in versions(person)}:
            raise ValueError("Choose a reference version belonging to this person.")
        record["active"] = voice
        atomic_json(location("people", person) / "record.json", record)
    return record
