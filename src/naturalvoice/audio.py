"""Loading and saving audio (and pulling audio out of / back into video) via ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg is required for this file type but was not found on PATH.")
    return exe


def load(path: str | Path, sr: int | None = None) -> tuple[np.ndarray, int]:
    """Load any audio/video file as float32 array shaped (samples, channels)."""
    path = Path(path)
    if path.suffix.lower() in {".wav", ".flac", ".ogg", ".aiff", ".aif"} and sr is None:
        data, rate = sf.read(str(path), dtype="float32", always_2d=True)
        return data, rate
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "in.wav"
        cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(path), "-vn", "-acodec", "pcm_f32le"]
        if sr:
            cmd += ["-ar", str(sr)]
        subprocess.run(cmd + [str(tmp)], check=True)
        data, rate = sf.read(str(tmp), dtype="float32", always_2d=True)
    return data, rate


def save(path: str | Path, audio: np.ndarray, sr: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".wav", ".flac"}:
        sf.write(str(path), audio, sr, subtype="PCM_24" if path.suffix.lower() == ".wav" else None)
        return
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "out.wav"
        sf.write(str(tmp), audio, sr, subtype="PCM_24")
        subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-i", str(tmp), str(path)], check=True)


def remux_video(video_in: str | Path, audio: np.ndarray, sr: int, video_out: str | Path) -> None:
    """Put new audio into a copy of the video, keeping the picture untouched."""
    video_out = Path(video_out)
    video_out.parent.mkdir(parents=True, exist_ok=True)
    acodec = ["-c:a", "libopus"] if video_out.suffix.lower() == ".webm" else ["-c:a", "aac", "-b:a", "256k"]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "clean.wav"
        sf.write(str(tmp), audio, sr, subtype="PCM_24")
        subprocess.run(
            [
                _ffmpeg(),
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(video_in),
                "-i",
                str(tmp),
                "-map",
                "0:v?",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                *acodec,
                "-shortest",
                str(video_out),
            ],
            check=True,
        )
