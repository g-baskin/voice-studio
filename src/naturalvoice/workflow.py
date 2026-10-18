"""Preview, advisory recommendations, exported-file scoring and listening copies."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pyloudnorm as pyln

from . import audio, analyze, humanize as hz


def segment(src: Path, dst: Path, start: float, seconds: float) -> tuple[np.ndarray, int]:
    # Decode only the selected window, not an entire video. Never interpolate shell commands.
    subprocess.run(
        [
            audio._ffmpeg(),
            "-y",
            "-loglevel",
            "error",
            "-ss",
            str(start),
            "-i",
            str(src),
            "-t",
            str(seconds),
            "-vn",
            "-ac",
            "2",
            "-ar",
            "24000",
            "-acodec",
            "pcm_f32le",
            str(dst),
        ],
        check=True,
        timeout=120,
        capture_output=True,
    )
    data, sr = audio.load(dst)
    if len(data) < sr * 0.1:
        raise ValueError("This section is empty or too short. Choose an earlier start time.")
    return data, sr


def recommend(data: np.ndarray, sr: int) -> dict:
    """Conservative heuristics, not a trained classifier or a verified diagnosis."""
    x = data.mean(axis=1) if data.ndim == 2 else data
    if len(x) < sr or float(np.max(np.abs(x))) < 1e-5:
        return {
            "template": "clean",
            "reason": "Too little audible speech to assess. Start gently and listen.",
            "confidence": "low",
        }
    ring = analyze.metallic(x, sr)
    rt = hz.estimate_rt60(x, sr)
    pause = analyze.echo_db(x, sr)
    _, z = hz._stft(x, sr)
    power = np.abs(z) ** 2 + 1e-12
    quiet = power.sum(axis=0) <= np.percentile(power.sum(axis=0), 20)
    flatness = float(np.median(np.exp(np.mean(np.log(power[:, quiet]), axis=0)) / np.mean(power[:, quiet], axis=0)))
    if ring > 2.5:
        key, reason = "metallic", "Persistent narrow peaks suggest ringing. Try the metallic template first."
    elif pause > -35 and flatness > 0.15:
        key, reason = "noise", "The quieter sections contain broadband energy, which may be hiss or background noise."
    elif pause > -45 and rt > 0.6:
        key, reason = (
            "echo",
            "Slow decays and energy between phrases may indicate room echo; noise or music can look similar.",
        )
    elif pause < -50 and ring < 1.5:
        key, reason = "clean", "Quiet pauses and little detected ringing suggest starting with gentle processing."
    else:
        key, reason = "ad", "There is no clear single problem. Balanced cleanup is a starting point, not a diagnosis."
    return {
        "template": key,
        "reason": reason,
        "confidence": "low",
        "evidence": {"ringing_db": round(ring, 2), "pause_db": round(pause, 1), "decay_estimate_s": round(rt, 2)},
    }


def warnings(before: dict, after: dict, room_tone: float) -> list[str]:
    notes = []
    for key, label in [("listener", "Overall listener"), ("voice", "Voice-quality")]:
        b, a = before.get(key), after.get(key)
        if b is not None and a is not None and a < b - 0.1:
            notes.append(f"{label} prediction fell by {b - a:.2f}. Try a gentler template and compare by ear.")
    if before.get("listener") is not None and after.get("listener") is not None:
        if abs(after["listener"] - before["listener"]) < 0.1:
            notes.append("The listener-score change is small; it is not strong evidence of an audible improvement.")
    if after["echo_db"] > before["echo_db"] + 6:
        notes.append(
            "Pauses are louder relative to speech. This may be room tone, noise, or a level change, not necessarily echo."
        )
    if room_tone > 0:
        notes.append("Added room tone is on and can raise the pause level.")
    notes.append(
        "Predicted ratings are not human listening tests. Pause level and brightness have no universal better direction."
    )
    return notes


def matched_copies(before: np.ndarray, after: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, dict]:
    """Match integrated loudness without boosting peaks into clipping; preserve stereo."""
    arrays = [np.array(before, dtype=np.float32), np.array(after, dtype=np.float32)]
    levels = []
    for x in arrays:
        try:
            level = float(pyln.Meter(sr).integrated_loudness(x.astype(float)))
        except ValueError:
            level = float("-inf")
        levels.append(level)
    if not all(np.isfinite(levels)):
        return (
            arrays[0],
            arrays[1],
            {"matched": False, "note": "Too short or too quiet for loudness matching; original playback levels used."},
        )
    target = min(-20.0, *levels)
    # Find a common target that also respects both recordings' peak headroom.
    for x, level in zip(arrays, levels):
        peak_db = 20 * np.log10(max(float(np.max(np.abs(x))), 1e-10))
        target = min(target, level - peak_db - 1.0)
    scaled = [x * 10 ** ((target - level) / 20) for x, level in zip(arrays, levels)]
    return (
        scaled[0],
        scaled[1],
        {
            "matched": True,
            "target_lufs": round(target, 2),
            "note": "Loudness-matched listening copies. Switching preserves position; downloads keep their original output level.",
        },
    )


def process(src: Path, dst: Path, settings, mode: str, start: float, seconds: float, progress) -> dict:
    if mode in {"preview", "analyze"}:
        data, sr = segment(src, src.parent / "section.wav", start, seconds)
    else:
        data, sr = audio.load(src)
    if len(data) < sr * 0.1 or not np.isfinite(data).all():
        raise ValueError("Audio must contain at least 0.1 seconds of finite samples.")
    if mode == "analyze":
        return {"suggestion": recommend(data, sr), "start": start, "seconds": round(len(data) / sr, 2)}
    progress("Cleaning selected section" if mode == "preview" else "Cleaning", 0.1)
    before = analyze.report(data, sr)
    out = hz.humanize(data, sr, settings, progress)
    if mode == "clean" and audio.is_video(src):
        audio.remux_video(src, out, sr, dst)
    else:
        audio.save(dst, out, sr)
    progress("Scoring exported audio and matching playback", 0.95)
    exported, out_sr = audio.load(dst)
    # Score the actual export, including room tone and any lossy video encoding.
    after = analyze.report(exported, out_sr)
    if out_sr != sr:
        exported, _ = audio.load(dst, sr=sr)
    length = min(len(data), len(exported))
    a, b, matching = matched_copies(data[:length], exported[:length], sr)
    audio.save(src.parent / "compare-before.wav", a, sr)
    audio.save(src.parent / "compare-after.wav", b, sr)
    return {
        "before": before,
        "after": after,
        "warnings": warnings(before, after, settings.room_tone),
        "matching": matching,
        "mode": mode,
        "start": start if mode == "preview" else 0,
        "seconds": round(length / sr, 2),
        "settings": settings.to_dict(),
    }
