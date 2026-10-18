"""Zero-shot voice cloning: speak any text in the voice of a short reference recording.

Engine: Chatterbox-Turbo (Resemble AI, MIT licence) as ONNX, run in an isolated project-local
environment under ``engines/chatterbox`` by a persistent worker process (JSON lines over stdin/stdout,
models loaded once, stopped after an idle timeout). Install with ``scripts/setup_clone_engine.sh``.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIR = Path(os.environ.get("NATURALVOICE_CLONE_ENGINE", ROOT / "engines" / "chatterbox"))
MODEL_NAME = "Chatterbox-Turbo (ONNX)"
LICENSE = "MIT"
SR = 24000
IDLE_SECS = float(os.environ.get("NATURALVOICE_CLONE_IDLE", 600))
LOAD_TIMEOUT = 300.0
REF_MIN, REF_MAX, REF_KEEP = 5.0, 60.0, 20.0  # accepted upload length; seconds kept as the reference
SETUP_HINT = "Run scripts/setup_clone_engine.sh in the app folder to install it (about 3.3 GB, one time)."
_REQUIRED = ("speech_encoder", "embed_tokens", "language_model", "conditional_decoder")


# Paralinguistic tags Chatterbox-Turbo was trained on; each is one special token in tokenizer.json
# (upstream EVENT_TAGS in resemble-ai/chatterbox gradio_tts_turbo_app.py).
EMOTION_TAGS = ["[clear throat]", "[sigh]", "[shush]", "[cough]", "[groan]", "[sniff]", "[gasp]",
                "[chuckle]", "[laugh]"]
_TAG = re.compile(r"\[([^\[\]\n]{0,40})\]")


def clean_tags(text: str) -> tuple[str, list[str]]:
    """Keep supported tags (normalised to their canonical spelling), drop any other [bracketed] text.
    Returns (clean text, removed tags)."""
    known = {t[1:-1]: t for t in EMOTION_TAGS}
    removed: list[str] = []

    def sub(m):
        key = re.sub(r"\s+", " ", m.group(1).strip().lower())
        if key in known:
            return " " + known[key] + " "
        removed.append(m.group(0))
        return " "
    out = _TAG.sub(sub, text or "")
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r" +([,.!?;:])", r"\1", out)
    return out.strip(), removed


class EngineMissing(RuntimeError):
    pass


def _python() -> Path:
    return ENGINE_DIR / ".venv" / "bin" / "python"


def _dtype() -> str:
    p = ENGINE_DIR / "models" / "DTYPE"
    return p.read_text().strip() if p.exists() else "fp32"


def installed() -> bool:
    suffix = "" if _dtype() == "fp32" else "_quantized"
    onnx = ENGINE_DIR / "models" / "onnx"
    return (_python().exists() and (ENGINE_DIR / "worker.py").exists()
            and (ENGINE_DIR / "models" / "tokenizer.json").exists()
            and all((onnx / f"{n}{suffix}.onnx_data").exists() for n in _REQUIRED))


# --------------------------------------------------------------------------- worker

class _Worker:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.lines: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.last = 0.0
        self.next_id = 1
        self.timer: threading.Timer | None = None

    def _read(self, proc):
        for line in proc.stdout:
            self.lines.put(line)
        self.lines.put(None)  # EOF

    def _wait(self, rid: int, timeout: float) -> dict:
        end = time.time() + timeout
        while True:
            try:
                line = self.lines.get(timeout=max(0.1, end - time.time()))
            except queue.Empty:
                self._kill()
                raise RuntimeError("The cloning engine timed out.") from None
            if line is None:
                self._kill()
                raise RuntimeError("The cloning engine stopped unexpectedly.")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == rid:
                return msg
            if time.time() > end:
                self._kill()
                raise RuntimeError("The cloning engine timed out.")

    def _start(self):
        if not installed():
            raise EngineMissing("The voice cloning engine is not installed. " + SETUP_HINT)
        self.lines = queue.Queue()
        self.proc = subprocess.Popen([str(_python()), str(ENGINE_DIR / "worker.py")], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                     cwd=str(ENGINE_DIR))
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        msg = self._wait(0, LOAD_TIMEOUT)
        if not msg.get("ok"):
            self._kill()
            raise RuntimeError(msg.get("error") or "The cloning engine failed to load.")

    def _kill(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.stdin.close()
                p.wait(timeout=5)
            except Exception:
                p.kill()

    def _arm_idle(self):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(IDLE_SECS, self._idle)
        self.timer.daemon = True
        self.timer.start()

    def _idle(self):
        with self.lock:
            if time.time() - self.last >= IDLE_SECS - 1:
                self._kill()

    def call(self, req: dict, timeout: float) -> dict:
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                self._start()
            rid = self.next_id
            self.next_id += 1
            self.proc.stdin.write(json.dumps({**req, "id": rid}) + "\n")
            self.proc.stdin.flush()
            msg = self._wait(rid, timeout)
            self.last = time.time()
            self._arm_idle()
        if not msg.get("ok"):
            raise RuntimeError(f"Cloning engine error: {msg.get('error', 'unknown')}")
        return msg

    @property
    def running(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def stop(self):
        with self.lock:
            self._kill()


_worker = _Worker()


def stop() -> None:
    _worker.stop()


def status() -> dict:
    return {"installed": installed(), "model": MODEL_NAME, "license": LICENSE, "sample_rate": SR,
            "device": "cpu", "precision": _dtype(), "emotion_tags": EMOTION_TAGS,
            "languages": [{"code": k, "name": v} for k, v in LANGUAGE_NAMES.items()], "warm": _worker.running,
            "setup": None if installed() else SETUP_HINT}


# --------------------------------------------------------------------------- reference prep

def _resample(x: np.ndarray, sr: int, target: int) -> np.ndarray:
    if sr == target:
        return x.astype(np.float32)
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(sr, target)
    return resample_poly(x, target // g, sr // g).astype(np.float32)


def _trim(x: np.ndarray, sr: int, thresh_db: float = -40.0, keep: float = 0.12) -> np.ndarray:
    """Trim leading/trailing silence relative to the loudest 20 ms frame."""
    hop = int(0.02 * sr)
    n = len(x) // hop
    if n < 2:
        return x
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms / (rms.max() + 1e-12))
    on = np.flatnonzero(db > thresh_db)
    if not on.size:
        return x[:0]
    a = max(0, on[0] * hop - int(keep * sr))
    b = min(len(x), (on[-1] + 1) * hop + int(keep * sr))
    return x[a:b]


def prepare_reference(src: Path, dst: Path) -> dict:
    """Decode any upload, check its length, make it mono 24 kHz, trimmed and loudness-normalised."""
    from . import audio
    from . import humanize as hz

    try:
        data, sr = audio.load(src)
    except Exception as e:
        raise ValueError("Could not read this recording. Try WAV, MP3, M4A, WebM or OGG.") from e
    x = np.asarray(data, dtype=np.float32)
    x = x.mean(axis=1) if x.ndim == 2 else x
    if not x.size or not np.isfinite(x).all():
        raise ValueError("The recording contains no playable audio.")
    raw = len(x) / sr
    if raw < REF_MIN - 0.05 or raw > REF_MAX + 0.5:
        raise ValueError(f"The recording must be {REF_MIN:.0f} to {REF_MAX:.0f} seconds long (got {raw:.1f} s).")
    x = _resample(x, sr, SR)
    x = _trim(x, SR)
    if len(x) / SR < 3.0 or np.sqrt(np.mean(x ** 2)) < 1e-4:
        raise ValueError("Not enough speech in the recording. Record at least 5 seconds of clear talking.")
    x = x[: int(REF_KEEP * SR)]
    x = x - float(np.mean(x))
    x = hz.normalize(x, SR, -20.0)
    x = np.clip(x, -1, 1)
    import soundfile as sf

    sf.write(str(dst), x, SR, subtype="PCM_16")
    return {"duration": round(raw, 2), "reference_seconds": round(len(x) / SR, 2), "sample_rate": SR}


# --------------------------------------------------------------------------- joins

def fade(x: np.ndarray, sr: int, ms: float = 8.0) -> np.ndarray:
    """Short raised-cosine fade in and out so a clip can butt against silence without a click."""
    x = np.asarray(x, dtype=np.float32).copy()
    n = min(int(sr * ms / 1000), len(x) // 2)
    if n > 0:
        ramp = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n))).astype(np.float32)
        x[:n] *= ramp
        x[-n:] *= ramp[::-1]
    return x


def crossfade(a: np.ndarray, b: np.ndarray, n: int) -> np.ndarray:
    """Join a and b overlapping their last/first n samples with an equal-power (sin/cos) crossfade."""
    n = min(n, len(a), len(b))
    if n <= 0:
        return np.concatenate([a, b]).astype(np.float32)
    t = np.linspace(0, np.pi / 2, n, dtype=np.float32)
    mid = a[-n:] * np.cos(t) + b[:n] * np.sin(t)
    return np.concatenate([a[:-n], mid, b[n:]]).astype(np.float32)


# --------------------------------------------------------------------------- speaking

def split_sentences(text: str, max_chars: int = 220) -> list[tuple[str, float]]:
    """(sentence, pause_after). Short sentences are joined; long ones split at commas/semicolons."""
    out: list[tuple[str, float]] = []
    text = re.sub(r"\[([^\[\]\n]*)\]", lambda m: "[" + m.group(1).replace(" ", "\x00") + "]", text)  # keep tags whole
    for pi, para in enumerate(p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()):
        para = re.sub(r"\s+", " ", para).strip()
        sents = [s.strip() for s in re.split(r"(?<=[.!?])[\"')\]]?\s+", para) if s.strip()]
        pieces: list[str] = []
        for s in sents:
            while len(s) > max_chars:
                cut = max(s.rfind(",", 0, max_chars), s.rfind(";", 0, max_chars), s.rfind(" ", 0, max_chars))
                cut = cut if cut > 20 else max_chars
                pieces.append(s[: cut + 1].strip())
                s = s[cut + 1:].strip()
            if s:
                pieces.append(s)
        merged: list[str] = []
        for s in pieces:
            if merged and _TAG.fullmatch(s.replace("\x00", " ").strip(" .")):
                merged[-1] += " " + s  # a lone tag belongs to the sentence before it
            elif merged and len(merged[-1]) < 40 and len(merged[-1]) + len(s) < max_chars:
                merged[-1] += " " + s
            else:
                merged.append(s)
        if out:
            out[-1] = (out[-1][0], 0.75)
        for s in merged:
            s = s.replace("\x00", " ")
            if s[-1] not in ".!?,;:]":
                s += "."
            out.append((s, 0.42 if s.endswith("?") else 0.34))
    return out


def speak(text: str, voice_id: str, speed: float = 1.0, progress=None) -> tuple[np.ndarray, int]:
    from . import voices

    if not voice_id.startswith("clone:"):
        raise ValueError("Not a clone voice.")
    voices.get(voice_id)
    ref = voices.reference_audio(voice_id)
    text, _ = clean_tags(text or "")
    parts = split_sentences(text)
    if parts and all(_TAG.fullmatch(p.strip(" .")) or not _TAG.sub("", p).strip(" .,!?;:") for p, _ in parts):
        raise ValueError("Add some words to speak around the tags.")
    if not parts:
        raise ValueError("No text to speak.")
    if not installed():
        raise EngineMissing("The voice cloning engine is not installed. " + SETUP_HINT)
    rng = np.random.default_rng(len(text))
    pieces: list[np.ndarray] = []
    with tempfile.TemporaryDirectory(prefix="nv-clone-") as td:
        for i, (sentence, pause) in enumerate(parts):
            if progress:
                progress(i / len(parts), f"Speaking sentence {i + 1} of {len(parts)}")
            out = Path(td) / f"{uuid.uuid4().hex}.npy"
            _worker.call({"op": "speak", "text": sentence, "ref": str(ref), "out": str(out), "seed": i},
                         timeout=60 + 3 * len(sentence))
            wav = _trim(np.load(out).astype(np.float32), SR, thresh_db=-45, keep=0.04)
            pieces.append(fade(wav, SR))
            pieces.append(np.zeros(int(pause * (1 + rng.uniform(-0.15, 0.15)) * SR), dtype=np.float32))
    audio = np.concatenate(pieces[:-1])
    speed = float(speed or 1.0)
    if not np.isfinite(speed):
        speed = 1.0
    speed = float(np.clip(speed, 0.5, 2.0))
    if abs(speed - 1.0) > 0.02:
        from pedalboard import time_stretch

        audio = time_stretch(audio[None, :], SR, stretch_factor=speed)[0].astype(np.float32)
    peak = float(np.max(np.abs(audio)) + 1e-9)
    if peak > 0.98:
        audio = audio * (0.98 / peak)
    return audio.astype(np.float32), SR


# --------------------------------------------------------------------------- voice changer

SRC_MIN, SRC_MAX, CHUNK = 1.0, 60.0, 10.0  # parts >~10 s lose the target timbre mid-way (measured)
XFADE = 0.04  # seconds of overlap between converted parts


def prepare_source(src: Path, dst: Path) -> dict:
    """Decode a performance to mono 24 kHz 16-bit WAV, keeping its own dynamics (no trimming of pauses)."""
    from . import audio

    try:
        data, sr = audio.load(src)
    except Exception as e:
        raise ValueError("Could not read this recording. Try WAV, MP3, M4A, WebM or OGG.") from e
    x = np.asarray(data, dtype=np.float32)
    x = x.mean(axis=1) if x.ndim == 2 else x
    if not x.size or not np.isfinite(x).all():
        raise ValueError("The recording contains no playable audio.")
    raw = len(x) / sr
    if raw < SRC_MIN - 0.05 or raw > SRC_MAX + 0.5:
        raise ValueError(f"The performance must be {SRC_MIN:.0f} to {SRC_MAX:.0f} seconds long (got {raw:.1f} s).")
    x = _trim(_resample(x, sr, SR), SR, thresh_db=-50, keep=0.15)
    if len(x) / SR < 0.5 or np.sqrt(np.mean(x ** 2)) < 1e-4:
        raise ValueError("No speech found in the recording.")
    peak = float(np.max(np.abs(x)))
    x = x * (0.9 / peak) if peak > 0.9 or peak < 0.3 else x
    import soundfile as sf

    sf.write(str(dst), x, SR, subtype="PCM_16")
    return {"duration": round(raw, 2)}


def _cut_points(x: np.ndarray, sr: int, max_len: float = CHUNK) -> list[int]:
    """Split long audio at the quietest 20 ms frame in the last 4 s before each max_len boundary."""
    cuts, start, hop = [0], 0, int(0.02 * sr)
    while len(x) - start > max_len * sr:
        lo, hi = start + int(max_len * 0.6 * sr), start + int(max_len * sr)
        seg = x[lo:hi]
        n = len(seg) // hop
        e = np.sqrt(np.mean(seg[: n * hop].reshape(n, hop) ** 2, axis=1))
        start = lo + int(np.argmin(e)) * hop + hop // 2
        cuts.append(start)
    return cuts + [len(x)]


def convert(source_audio_path, voice_id: str, progress=None) -> tuple[np.ndarray, int]:
    """Speech-to-speech: re-voice a prepared 24 kHz mono performance in a clone voice's timbre."""
    import soundfile as sf

    from . import voices

    if not voice_id.startswith("clone:"):
        raise ValueError("Not a clone voice.")
    voices.get(voice_id)
    ref = voices.reference_audio(voice_id)
    if not installed():
        raise EngineMissing("The voice cloning engine is not installed. " + SETUP_HINT)
    x, sr = sf.read(str(source_audio_path), dtype="float32")
    if sr != SR or x.ndim != 1:
        raise ValueError("Source must be prepared with prepare_source first.")
    cuts = _cut_points(x, SR)
    h = int(XFADE * SR / 2)  # each part reaches h samples past its cut, giving 2h of overlap to crossfade
    audio = np.zeros(0, dtype=np.float32)
    with tempfile.TemporaryDirectory(prefix="nv-vc-") as td:
        for i in range(len(cuts) - 1):
            if progress:
                progress(i / (len(cuts) - 1), f"Converting part {i + 1} of {len(cuts) - 1}")
            a = cuts[i] - (h if i > 0 else 0)
            b = cuts[i + 1] + (h if i + 1 < len(cuts) - 1 else 0)
            seg_p, out = Path(td) / f"s{i}.wav", Path(td) / f"o{i}.npy"
            sf.write(str(seg_p), x[a:b], SR, subtype="PCM_16")
            _worker.call({"op": "convert", "src": str(seg_p), "ref": str(ref), "out": str(out)},
                         timeout=60 + 8 * (b - a) / SR)
            w = np.load(out).astype(np.float32)
            # the decoder keeps timing (25 tokens/s); pin to the source length so parts line up exactly
            w = np.pad(w, (0, max(0, (b - a) - len(w))))[: b - a]
            audio = w if i == 0 else crossfade(audio, w, 2 * h)
    peak = float(np.max(np.abs(audio)) + 1e-9)
    if peak > 0.98:
        audio = audio * (0.98 / peak)
    return audio.astype(np.float32), SR


# --------------------------------------------------------------------------- other languages (via the voice changer)

# language -> (Kokoro lang code, female source voice, male source voice). es/fr measured; it/pt same method, unmeasured.
LANGUAGES = {
    "en": ("en-us", None, None),  # direct Chatterbox path
    "es": ("es", "ef_dora", "em_alex"),
    "fr": ("fr-fr", "ff_siwis", "ff_siwis"),  # Kokoro has no French male voice; timbre comes from the clone anyway
    "it": ("it", "if_sara", "im_nicola"),
    "pt": ("pt-br", "pf_dora", "pm_alex"),
}
LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "fr": "French", "it": "Italian", "pt": "Brazilian Portuguese"}


def _median_f0(x: np.ndarray, sr: int) -> float | None:
    """Rough median pitch of voiced 40 ms frames (autocorrelation, 70-400 Hz)."""
    n, f0s = int(0.04 * sr), []
    lo, hi = int(sr / 400), int(sr / 70)
    for i in range(0, len(x) - n, n):
        f = x[i:i + n] - x[i:i + n].mean()
        if np.sqrt(np.mean(f ** 2)) < 0.02:
            continue
        ac = np.correlate(f, f, "full")[n - 1:]
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > 0.4 * ac[0]:
            f0s.append(sr / lag)
    return float(np.median(f0s)) if len(f0s) >= 5 else None


def clone_gender(voice_id: str) -> str:
    """'male' or 'female' from metadata, else estimated from the reference pitch (< 165 Hz -> male)."""
    import soundfile as sf

    from . import voices

    g = (voices.get(voice_id).get("meta") or {}).get("gender")
    if g in {"male", "female"}:
        return g
    x, sr = sf.read(str(voices.reference_audio(voice_id)), dtype="float32")
    f0 = _median_f0(x if x.ndim == 1 else x.mean(axis=1), sr)
    return "male" if f0 is not None and f0 < 165 else "female"


def speak_language(text: str, voice_id: str, lang: str, speed: float = 1.0, progress=None) -> tuple[np.ndarray, int]:
    """Speak in another language: a built-in Kokoro voice reads the text, then the voice changer re-voices it
    in the clone's timbre. Pronunciation and prosody come from the built-in voice."""
    import soundfile as sf

    from . import tts, voices

    if lang not in LANGUAGES:
        raise ValueError(f"Unsupported language {lang!r}.")
    if lang == "en":
        return speak(text, voice_id, speed, progress=progress)
    if not voice_id.startswith("clone:"):
        raise ValueError("Not a clone voice.")
    voices.get(voice_id)
    if not installed():
        raise EngineMissing("The voice cloning engine is not installed. " + SETUP_HINT)
    text, _ = clean_tags(text or "")
    text = _TAG.sub(" ", text).strip()  # emotion tags only work on the direct English path
    if not text:
        raise ValueError("No text to speak.")
    kcode, female, male = LANGUAGES[lang]
    src_voice = male if clone_gender(voice_id) == "male" else female
    if progress:
        progress(0.05, f"Reading the text in {LANGUAGE_NAMES[lang]}")
    a, sr = tts._kokoro().create(text, voice=src_voice, speed=float(np.clip(speed or 1.0, 0.5, 2.0)), lang=kcode)
    x = _resample(np.asarray(a, dtype=np.float32), sr, SR)
    if len(x) / SR > SRC_MAX:
        raise ValueError(f"Text too long for this language mode ({SRC_MAX:.0f} s of speech max).")
    with tempfile.TemporaryDirectory(prefix="nv-lang-") as td:
        p = Path(td) / "src.wav"
        sf.write(str(p), fade(x, SR), SR, subtype="PCM_16")
        return convert(p, voice_id, progress=(lambda f, s: progress(0.1 + 0.9 * f, s)) if progress else None)
