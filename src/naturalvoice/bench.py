"""Benchmark: does the cleanup really make AI voices sound better, by standard measures?

Method
------
1. Make clean reference speech with the offline voice model (3 voices, cached in bench/refs).
2. Damage it in realistic, repeatable ways (simulated rooms, phase-loss 'metallic' resynthesis,
   resonant ringing, low-bitrate codec, and all of them together like a cheap AI ad).
3. Run each cleanup method on the damaged audio.
4. Score against the clean reference with standard measures (see quality.py) plus our own.

Scores (arrow = which way is better)
* OVRL ^  DNSMOS overall: predicted listener rating, 1-5. The headline number.
* SIG  ^  DNSMOS voice quality, 1-5 (drops when the voice itself is damaged or over-processed).
* BAK  ^  DNSMOS background, 1-5 (rises when echo / noise is removed).
* PESQ ^  wideband PESQ vs the clean voice, 1-4.6.
* STOI ^  intelligibility vs the clean voice, 0-1.
* echo v  energy left in pauses relative to speech, dB.
* metal v average height of persistent narrow spectral peaks, dB.
* rtf  v  processing time / audio length (below 1 = faster than real time).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

import numpy as np
from scipy import signal

from . import analyze, audio, humanize as hz, quality

SENTENCES = [
    ("af_heart", "Hi there! Thanks for stopping by. Today I want to show you something that will save you hours every week."),
    ("am_michael", "Our new app is simple, fast, and honestly, kind of fun to use. Try it free for thirty days, no card needed."),
    ("bf_emma", "When the weather turns, you'll want a coat that keeps up. This one is light, warm, and built to last."),
]


# --------------------------------------------------------------------------- damage

def _room(x, sr, rt60, dims, seed=1):
    """Image-source + ray-traced room (pyroomacoustics), talker ~1.5-3 m from the mic."""
    import pyroomacoustics as pra

    e_abs, max_order = pra.inverse_sabine(rt60, dims)
    room = pra.ShoeBox(dims, fs=sr, materials=pra.Material(e_abs), max_order=min(max_order, 17),
                       use_rand_ism=True, max_rand_disp=0.05)
    rng = np.random.default_rng(seed)
    src = [dims[0] * 0.3, dims[1] * 0.4 + rng.uniform(-0.2, 0.2), 1.6]
    mic = [dims[0] * 0.3 + min(2.5, dims[0] * 0.4), dims[1] * 0.55, 1.4]
    room.add_source(src, signal=x)
    room.add_microphone(mic)
    room.simulate()
    y = room.mic_array.signals[0]
    # remove propagation delay so it lines up with the reference
    d = int(np.argmax(np.abs(room.rir[0][0])))
    return y[d: d + len(x)]


def _reverb(x, sr, rt60, wet_db, seed=1):
    """Simple exponential-noise reverb (fast; used by unit tests)."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(min(1.5, rt60 * 1.3) * sr)) / sr
    tail = rng.standard_normal(len(t)) * np.exp(-6.9 * t / rt60)
    tail[: int(0.004 * sr)] = 0
    b, a = signal.butter(1, 6000 / (sr / 2))
    tail = signal.lfilter(b, a, tail)
    tail *= np.sqrt(10 ** (wet_db / 10) / np.sum(tail ** 2))
    tail[0] += 1.0
    return signal.fftconvolve(x, tail)[: len(x)]


def _griffin_lim(x, sr, iters=24, seed=0):
    """Throw away the phase and rebuild it: the classic 'metallic / phasey' vocoder sound."""
    n = 1024
    _, _, Z = signal.stft(x, sr, nperseg=n, noverlap=n * 3 // 4)
    mag = np.abs(Z)
    rng = np.random.default_rng(seed)
    P = np.exp(2j * np.pi * rng.random(mag.shape))
    for _ in range(iters):
        _, y = signal.istft(mag * P, sr, nperseg=n, noverlap=n * 3 // 4)
        _, _, Z2 = signal.stft(y[: len(x)], sr, nperseg=n, noverlap=n * 3 // 4)
        P = np.exp(1j * np.angle(Z2[:, : mag.shape[1]]))
    _, y = signal.istft(mag * P, sr, nperseg=n, noverlap=n * 3 // 4)
    y = y[: len(x)]
    return np.pad(y, (0, max(0, len(x) - len(y))))


def _resonances(x, sr, freqs=(1900, 3100, 4700, 6800), gain_db=9.0, q=14.0):
    for f0 in freqs:
        b, a = signal.iirpeak(f0, q, fs=sr)
        x = x + (10 ** (gain_db / 20) - 1) * signal.lfilter(b, a, x)
    return x


def _codec(x, sr, kbps=32):
    """Round-trip through a low-bitrate MP3, as happens to voices re-uploaded to social/ad platforms."""
    with tempfile.TemporaryDirectory() as td:
        a, b, c = Path(td) / "a.wav", Path(td) / "b.mp3", Path(td) / "c.wav"
        audio.save(a, x.astype(np.float32), sr)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(a), "-b:a", f"{kbps}k", str(b)], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(b), "-ar", str(sr), "-ac", "1", str(c)], check=True)
        y, _ = audio.load(c)
    y = y[:, 0]
    # MP3 adds a fixed encoder delay; align by cross-correlation
    lag = int(np.argmax(signal.correlate(y[: sr * 2], x[: sr * 2], mode="full", method="fft")) - (sr * 2 - 1))
    y = y[lag:] if lag > 0 else np.pad(y, (-lag, 0))
    y = y[: len(x)]
    return np.pad(y, (0, len(x) - len(y)))


DAMAGE: dict[str, Callable[[np.ndarray, int], np.ndarray]] = {
    "clean (no-harm check)": lambda x, sr: x,
    "small room echo": lambda x, sr: _room(x, sr, 0.45, [4.0, 3.5, 2.7]),
    "big hall echo": lambda x, sr: _room(x, sr, 1.0, [14.0, 10.0, 6.0]),
    "metallic (phase loss)": lambda x, sr: _griffin_lim(x, sr),
    "ringing resonances": lambda x, sr: _resonances(x, sr),
    "low-bitrate codec": lambda x, sr: _codec(x, sr, 32),
    "typical AI ad (all)": lambda x, sr: _codec(_room(_resonances(_griffin_lim(x, sr, 32), sr, gain_db=6),
                                                     sr, 0.6, [6.0, 5.0, 3.0]), sr, 48),
}


# --------------------------------------------------------------------------- methods

def methods() -> dict[str, Callable[[np.ndarray, int], np.ndarray]]:
    from . import enhance

    m = {
        "untouched": lambda x, sr: x,
        "classic (before AI)": lambda x, sr: hz.humanize(x, sr, hz.get_settings("standard", ai_clean=0.0, dereverb=0.8,
                                                                                  room_tone=0.0)),
    }
    if enhance.available():
        m["AI cleanup only"] = lambda x, sr: hz.normalize(enhance.ai_clean(x, sr, 1.0), sr, -16)
        for p in ("standard", "strong"):
            m[f"app: {p}"] = (lambda p: lambda x, sr: hz.humanize(x, sr, hz.get_settings(p, room_tone=0.0)))(p)
    return m


# --------------------------------------------------------------------------- scoring

def _frames_db(x, sr):
    win = int(0.02 * sr)
    f = np.lib.stride_tricks.sliding_window_view(x, win)[:: win // 2]
    return 10 * np.log10(np.mean(f ** 2, axis=1) + 1e-12)


def score(ref: np.ndarray, y: np.ndarray, sr: int, full: bool = True) -> dict:
    from pystoi import stoi

    y = y[: len(ref)]
    y = y * np.sqrt(np.mean(ref ** 2) / (np.mean(y ** 2) + 1e-12))  # level-match
    er = _frames_db(ref, sr)
    gaps = er < er.max() - 50
    speech = er > er.max() - 25
    ey = _frames_db(y, sr)
    out = {
        "echo": round(float(np.mean(ey[gaps]) - np.mean(ey[speech])), 1) if gaps.any() else None,
        "metal": round(analyze.metallic(y, sr), 2),
        "STOI": round(float(stoi(ref, y, sr, extended=False)), 3),
    }
    if full:
        d = quality.dnsmos(y, sr)
        p = quality.pesq_wb(ref, y, sr)
        out.update(OVRL=round(d["OVRL"], 2), SIG=round(d["SIG"], 2), BAK=round(d["BAK"], 2),
                   PESQ=round(p, 2) if p is not None else None)
    return out


HIGHER_BETTER = {"OVRL", "SIG", "BAK", "PESQ", "STOI"}
COLUMNS = ["OVRL", "SIG", "BAK", "PESQ", "STOI", "echo", "metal"]


# --------------------------------------------------------------------------- runner

def references(out_dir: Path, voices: int = 3) -> list[tuple[str, np.ndarray, int]]:
    from . import tts

    out_dir.mkdir(parents=True, exist_ok=True)
    refs = []
    for voice, text in SENTENCES[:voices]:
        p = out_dir / f"{voice}.wav"
        if not p.exists():
            a, sr = tts.speak(text, voice, humanize=False)
            audio.save(p, a, sr)
        a, sr = audio.load(p)
        refs.append((voice, a[:, 0], sr))
    return refs


def run(out_dir: str | Path = "bench", quick: bool = False, save_audio: bool = True, log=print) -> dict:
    out = Path(out_dir)
    refs = references(out / "refs", 1 if quick else 3)
    meths = methods()
    rows = []
    for name, damage in DAMAGE.items():
        log(f"- {name}")
        for voice, ref, sr in refs:
            bad = damage(ref, sr)
            bad = (bad * (0.7 / (np.abs(bad).max() + 1e-9))).astype(np.float32)
            for mname, fn in meths.items():
                t0 = time.perf_counter()
                y = fn(bad, sr)
                rtf = (time.perf_counter() - t0) / (len(bad) / sr)
                rows.append({"damage": name, "voice": voice, "method": mname,
                             "rtf": round(rtf, 3), **score(ref, y, sr)})
                if save_audio and voice == refs[0][0]:
                    slug = name.split(" (")[0].replace(" ", "-")
                    audio.save(out / "audio" / slug / f"{mname.split(' (')[0].replace(' ', '-')}.wav", y, sr)
    result = summarize(rows, list(meths))
    (out / "results.json").write_text(json.dumps(result, indent=2))
    (out / "REPORT.md").write_text(render(result))
    return result


def _mean(vals):
    v = [x for x in vals if x is not None]
    return round(float(np.mean(v)), 3) if v else None


def summarize(rows: list[dict], method_names: list[str]) -> dict:
    damages = list(dict.fromkeys(r["damage"] for r in rows))
    table = {}
    for d in damages:
        table[d] = {}
        for m in method_names:
            rs = [r for r in rows if r["damage"] == d and r["method"] == m]
            if rs:
                table[d][m] = {c: _mean([r.get(c) for r in rs]) for c in COLUMNS + ["rtf"]}
    overall = {}
    for m in method_names:
        rs = [r for r in rows if r["method"] == m and not r["damage"].startswith("clean")]
        overall[m] = {c: _mean([r.get(c) for r in rs]) for c in COLUMNS + ["rtf"]}
    return {"table": table, "overall": overall, "methods": method_names, "rows": rows}


def _fmt(v):
    return "–" if v is None else f"{v:g}"


def render(r: dict) -> str:
    methods_ = r["methods"]
    base = r["overall"].get("untouched", {})
    lines = ["# Voice Studio benchmark", "",
             "Standard measures: **OVRL / SIG / BAK** = Microsoft DNSMOS predicted listener ratings (1-5), "
             "**PESQ** = ITU-T P.862.2 wideband (1-4.6), **STOI** = intelligibility (0-1). "
             "Own measures: **echo** = level in pauses (dB, lower is better), **metal** = persistent ringing peaks "
             "(dB, lower is better). Averaged over the voices tested. Best value per row in bold.", "",
             "## Overall (all damaged cases)", "",
             "| Method | " + " | ".join(COLUMNS) + " | speed (x real time) |",
             "|---|" + "---|" * (len(COLUMNS) + 1)]
    for m in methods_:
        o = r["overall"][m]
        cells = []
        for c in COLUMNS:
            v, b = o.get(c), base.get(c)
            delta = ""
            if m != "untouched" and v is not None and b is not None:
                dv = v - b
                delta = f" ({'+' if dv >= 0 else ''}{dv:.2f})"
            cells.append(_fmt(v) + delta)
        lines.append(f"| {m} | " + " | ".join(cells) + f" | {_fmt(o.get('rtf'))} |")
    lines += ["", "## By problem", ""]
    for d, ms in r["table"].items():
        lines += [f"### {d}", "", "| Method | " + " | ".join(COLUMNS) + " |", "|---|" + "---|" * len(COLUMNS)]
        best = {}
        for c in COLUMNS:
            vals = [(ms[m][c], m) for m in ms if ms[m].get(c) is not None]
            if vals:
                best[c] = (max if c in HIGHER_BETTER else min)(vals)[1]
        for m, o in ms.items():
            cells = [(f"**{_fmt(o[c])}**" if best.get(c) == m and m != "untouched" else _fmt(o[c])) for c in COLUMNS]
            lines.append(f"| {m} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["Listen: `bench/audio/<problem>/<method>.wav` (first voice)."]
    return "\n".join(lines) + "\n"
