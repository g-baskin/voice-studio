"""Rough, explainable measurements of 'AI-ness' so before/after can be compared.

These are heuristics, not lab measurements:
* echo_db       - how loud the pauses between words are vs. the speech (dB). Echo fills the pauses.
* metallic      - average height (dB) of narrow resonance peaks in 0.9-11 kHz.
* harshness_db  - 4-9 kHz energy relative to the 200-3000 Hz voice body.
"""
from __future__ import annotations

import numpy as np

from .humanize import find_resonances, _stft


def echo_db(x: np.ndarray, sr: int) -> float:
    """Level of the quietest 15% of 20 ms frames (pauses) relative to the loudest 20% (speech)."""
    win = int(0.02 * sr)
    if len(x) < win * 20:
        return 0.0
    f = np.lib.stride_tricks.sliding_window_view(x, win)[:: win // 2]
    e = np.sort(10 * np.log10(np.mean(f ** 2, axis=1) + 1e-12))
    n = len(e)
    return float(np.mean(e[: max(1, int(0.15 * n))]) - np.mean(e[int(0.8 * n):]))


def metallic(x: np.ndarray, sr: int) -> float:
    peaks = find_resonances(x, sr, thresh_db=2.0, max_peaks=10)
    return float(sum(p[1] for p in peaks) / 10.0)


def harshness_db(x: np.ndarray, sr: int) -> float:
    f, Z = _stft(x, sr)
    m2 = np.abs(Z) ** 2
    h = m2[(f >= 4000) & (f <= 9000)].sum()
    b = m2[(f >= 200) & (f <= 3000)].sum()
    return float(10 * np.log10((h + 1e-12) / (b + 1e-12)))


def listener_score(x: np.ndarray, sr: int, max_seconds: float = 60.0) -> float | None:
    """DNSMOS overall (predicted listener rating 1-5) on up to the first minute; None if models missing."""
    from . import quality

    try:
        return round(quality.dnsmos(x[: int(max_seconds * sr)], sr)["OVRL"], 2)
    except RuntimeError:
        return None


def report(audio: np.ndarray, sr: int) -> dict:
    x = audio if audio.ndim == 1 else audio.mean(axis=1)
    from . import quality
    scores = {}
    if len(x) and np.max(np.abs(x)) > 1e-8:
        try:
            scores = quality.dnsmos(x[:int(60 * sr)], sr)
        except RuntimeError:
            pass  # Optional scoring models are not installed.
    return {
        "listener": round(scores["OVRL"], 2) if scores else None,
        "voice": round(scores["SIG"], 2) if scores else None,
        "score_seconds": round(min(len(x) / sr, 60), 2),
        "echo_db": round(echo_db(x, sr), 1),
        "metallic": round(metallic(x, sr), 2),
        "harshness_db": round(harshness_db(x, sr), 2),
        "seconds": round(len(x) / sr, 2),
    }
