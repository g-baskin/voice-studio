"""Voice Lab: design new Kokoro voices by blending, describing, or matching a recording.

Everything here works inside Kokoro's style space: a voice is a style array of shape (510, 1, 256).
* blend:    weighted average of 2-5 voices, plus character controls (measured style directions)
* describe: keyword -> stock voices chosen by tags and *measured* pitch, plus small random variation
* match:    speaker-embedding search that moves a style toward a reference recording's timbre
None of this is a generative voice model or a true clone.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

import numpy as np

from . import voices as vlib

SR = 24000
EMB_SR = 16000
SPEAKER_MODEL = "3dspeaker_campplus_en_voxceleb_16k.onnx"
SPEAKER_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
               "3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx")
# Fixed line used for stock-voice measurements and for every match-search render.
MEASURE_LINE = ("The morning light settled over the quiet harbour, and everyone stopped to listen. "
                "A small boat drifted past the old stone wall while the gulls circled overhead. "
                "Then the bells rang out across the water, loud and clear, for the very last time.")
SAMPLE_LINES = {
    "en-us": "Hi there. This is how I sound when I read your script out loud.",
    "en-gb": "Hello there. This is how I sound when I read your script out loud.",
    "es": "Hola. Así sueno cuando leo tu guion en voz alta.",
    "fr-fr": "Bonjour. Voici ma voix quand je lis votre texte à voix haute.",
    "hi": "नमस्ते। जब मैं आपकी स्क्रिप्ट पढ़ती हूँ तो मेरी आवाज़ ऐसी होती है।",
    "it": "Ciao. Ecco come suono quando leggo il tuo testo ad alta voce.",
    "pt-br": "Olá. É assim que eu soo quando leio o seu roteiro em voz alta.",
    "ja": "こんにちは。これが台本を読み上げるときの私の声です。",
    "cmn": "你好。这就是我朗读你的稿子时的声音。",
}
MAX_TEXT = 300
FEATURE_VERSION = 2
_lock = threading.Lock()


def data_dir() -> Path:
    return vlib.DATA_DIR


# ---------------------------------------------------------------- rendering + measuring

def render(style: np.ndarray, lang: str, text: str, speed: float = 1.0) -> np.ndarray:
    from .tts import _kokoro

    audio, _ = _kokoro().create(text, voice=np.asarray(style, dtype=np.float32), speed=speed, lang=lang)
    return np.asarray(audio, dtype=np.float32)


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    from math import gcd

    from scipy.signal import resample_poly

    if sr_in == sr_out:
        return x.astype(np.float32)
    g = gcd(sr_in, sr_out)
    return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)


def pitch_hz(x: np.ndarray, sr: int = SR) -> float:
    """Median F0 of voiced frames (autocorrelation, 60-400 Hz)."""
    frame, hop = int(0.04 * sr), int(0.01 * sr)
    lo, hi = int(sr / 400), int(sr / 60)
    if len(x) < frame:
        return 0.0
    thr = 0.1 * np.max(np.abs(x))
    f0 = []
    for s in range(0, len(x) - frame, hop):
        w = x[s:s + frame] - x[s:s + frame].mean()
        if np.sqrt(np.mean(w ** 2)) < thr * 0.3:
            continue
        ac = np.fft.irfft(np.abs(np.fft.rfft(w, 2 * frame)) ** 2)[:frame]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi] / ac[0]
        k = int(np.argmax(seg))
        if seg[k] > 0.5:
            f0.append(sr / (lo + k))
    return float(np.median(f0)) if f0 else 0.0


def brightness_hz(x: np.ndarray, sr: int = SR) -> float:
    """Mean spectral centroid of loud frames."""
    n, hop = 1024, 256
    if len(x) < n:
        return 0.0
    idx = np.arange(0, len(x) - n, hop)[:, None] + np.arange(n)
    fr = x[idx] * np.hanning(n)
    p = np.abs(np.fft.rfft(fr, axis=1)) ** 2
    e = p.sum(1)
    keep = e > 0.05 * e.max()
    f = np.fft.rfftfreq(n, 1 / sr)
    return float(np.mean((p[keep] @ f) / e[keep]))


# ---------------------------------------------------------------- speaker embeddings

def _mel_banks(n_fft=512, n_mels=80, sr=EMB_SR, lo=20.0):
    mel = lambda f: 1127.0 * np.log(1 + np.asarray(f) / 700.0)  # noqa: E731  (Kaldi mel scale)
    hi = sr / 2
    pts = np.linspace(mel(lo), mel(hi), n_mels + 2)
    fm = mel(np.arange(n_fft // 2) * sr / n_fft)
    banks = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float64)
    for m in range(n_mels):
        l, c, r = pts[m], pts[m + 1], pts[m + 2]
        up, down = (fm - l) / (c - l), (r - fm) / (r - c)
        banks[m, :n_fft // 2] = np.maximum(0, np.minimum(up, down))
    return banks


_BANKS = None


def fbank(x: np.ndarray, sr: int = EMB_SR) -> np.ndarray:
    """Kaldi-compatible 80-dim log-mel fbank (25 ms / 10 ms, povey window, no dither), mean-normalised."""
    global _BANKS
    if _BANKS is None:
        _BANKS = _mel_banks()
    flen, hop = 400, 160
    x = np.asarray(x, dtype=np.float64)
    if len(x) < flen:
        x = np.pad(x, (0, flen - len(x)))
    n = 1 + (len(x) - flen) // hop
    fr = x[np.arange(n)[:, None] * hop + np.arange(flen)]
    fr = fr - fr.mean(1, keepdims=True)
    fr = np.concatenate([fr[:, :1] * 0.03, fr[:, 1:] - 0.97 * fr[:, :-1]], axis=1)
    win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(flen) / (flen - 1))) ** 0.85
    spec = np.abs(np.fft.rfft(fr * win, 512)) ** 2
    feats = np.log(np.maximum(spec @ _BANKS.T, np.finfo(np.float32).eps))
    return (feats - feats.mean(0)).astype(np.float32)


_SESSION = None


def _speaker_session():
    global _SESSION
    if _SESSION is None:
        import onnxruntime as ort

        from .tts import MODEL_DIR

        path = MODEL_DIR / SPEAKER_MODEL
        if not path.exists():
            raise RuntimeError(f"Speaker model missing. Download {SPEAKER_URL} into the models folder as {SPEAKER_MODEL}.")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        _SESSION = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
    return _SESSION


def trim_silence(x: np.ndarray, sr: int, floor: float = 0.02) -> np.ndarray:
    """Drop 10 ms frames quieter than `floor` x the loudest frame (leading, trailing and long gaps)."""
    x = np.asarray(x, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=1)
    n = max(1, int(0.01 * sr))
    m = len(x) // n
    if m < 2:
        return x
    fr = x[: m * n].reshape(m, n)
    e = np.sqrt(np.mean(fr ** 2, axis=1))
    keep = e > floor * (e.max() + 1e-12)
    return fr[keep].reshape(-1) if keep.sum() >= 10 else x


def embed(x: np.ndarray, sr: int) -> np.ndarray:
    """Unit-length 512-dim speaker embedding (CAM++, VoxCeleb) of the speech parts."""
    y = resample(trim_silence(x, sr), sr, EMB_SR)
    feats = fbank(y)[None]
    e = _speaker_session().run(None, {"x": feats})[0][0].astype(np.float64)
    return e / (np.linalg.norm(e) + 1e-9)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


# ---------------------------------------------------------------- stock measurements (cached)

def _stock_names() -> list[str]:
    from .tts import _kokoro

    return sorted(_kokoro().get_voices())


SHIPPED_EMB = Path(__file__).with_name("voicelab_embeddings.npz")
_FP: dict[str, str] = {}


def model_fingerprint() -> str:
    """Hash of the Kokoro voices file, speaker model, measure line and feature code version."""
    if MEASURE_LINE not in _FP:
        from .tts import MODEL_DIR

        h = hashlib.sha256(f"{FEATURE_VERSION}|{MEASURE_LINE}".encode())
        for f in ("voices-v1.0.bin", SPEAKER_MODEL):
            with open(MODEL_DIR / f, "rb") as fh:
                while chunk := fh.read(1 << 22):
                    h.update(chunk)
        _FP[MEASURE_LINE] = h.hexdigest()
    return _FP[MEASURE_LINE]


def _load_npz(path: Path, fingerprint: str | None = None) -> dict[str, dict]:
    try:
        z = np.load(path, allow_pickle=False)
        if fingerprint is not None and str(z["fingerprint"]) != fingerprint:
            return {}
        return {str(n): {"emb": z["emb"][i], "pitch": float(z["pitch"][i]), "brightness": float(z["bright"][i])}
                for i, n in enumerate(z["names"])}
    except (OSError, ValueError, KeyError):
        return {}


def save_features(path: Path, feats: dict[str, dict], fingerprint: str = "") -> None:
    ks = sorted(feats)
    tmp = path.with_name(path.stem + ".tmp.npz")
    np.savez(tmp, names=np.array(ks), emb=np.stack([feats[k]["emb"] for k in ks]).astype(np.float32),
             pitch=np.array([feats[k]["pitch"] for k in ks]), bright=np.array([feats[k]["brightness"] for k in ks]),
             fingerprint=np.array(fingerprint))
    tmp.replace(path)


def stock_features(names: list[str] | None = None, progress=None, cancel=None,
                   cached_only: bool = False) -> dict[str, dict]:
    """Per-stock-voice {emb, pitch, brightness} from a render of MEASURE_LINE, cached in DATA_DIR/cache."""
    path = data_dir() / "cache" / f"stock_features_v{FEATURE_VERSION}.npz"
    with _lock:
        cache: dict[str, dict] = {}
        if SHIPPED_EMB.exists():  # shipped with the app; ignored if the models or measure line changed
            try:
                cache.update(_load_npz(SHIPPED_EMB, model_fingerprint()))
            except OSError:
                pass
        if path.exists():
            cache.update(_load_npz(path))
        want = names or _stock_names()
        missing = [] if cached_only else [n for n in want if n not in cache]
        for i, n in enumerate(missing):
            if cancel is not None and cancel.is_set():
                break
            a = render(vlib.style_of(n), "en-us", MEASURE_LINE)
            cache[n] = {"emb": embed(a, SR), "pitch": pitch_hz(a), "brightness": brightness_hz(a)}
            if progress:
                progress(i + 1, len(missing))
        if missing:
            path.parent.mkdir(parents=True, exist_ok=True)
            save_features(path, cache)
        return {n: cache[n] for n in want if n in cache}


# ---------------------------------------------------------------- blend + controls

def normalise_weights(weights) -> np.ndarray:
    w = np.asarray(weights, dtype=np.float64)
    if w.ndim != 1 or not np.isfinite(w).all() or (w < 0).any() or w.sum() <= 0:
        raise ValueError("Weights must be finite, non-negative and not all zero.")
    return w / w.sum()


def blend(styles: list[np.ndarray], weights) -> np.ndarray:
    w = normalise_weights(weights)
    if len(styles) != len(w):
        raise ValueError("One weight per voice.")
    return np.tensordot(w, np.stack(styles).astype(np.float64), axes=1).astype(np.float32)


_AXES: dict[str, np.ndarray] | None = None
# Controls kept after measurement (docs/voicelab.md lists the numbers). Strength 1.0 moves one
# axis length, i.e. the full average female-vs-male difference for 'gender'.
CONTROLS = {
    "gender": {"label": "Masculine ↔ Feminine",
               "help": "Moves along the average difference between Kokoro's female and male voices. "
                       "Right raises pitch and lightens the tone; left lowers and darkens it.",
               "min": -1.0, "max": 1.0, "scale": 0.5},
}


def _axes() -> dict[str, np.ndarray]:
    global _AXES
    if _AXES is None:
        names = _stock_names()
        st = {n: vlib.style_of(n).astype(np.float64) for n in names}
        fem = np.mean([st[n] for n in names if n[1] == "f"], axis=0)
        mal = np.mean([st[n] for n in names if n[1] == "m"], axis=0)
        _AXES = {"gender": (fem - mal).astype(np.float32)}
    return _AXES


def _variation(seed: int, amount: float, shape=vlib.STYLE_SHAPE) -> np.ndarray:
    """Random direction inside the stock voices' spread (so results stay voice-like)."""
    names = _stock_names()
    st = np.stack([vlib.style_of(n) for n in names]).astype(np.float64)
    dev = st - st.mean(0)
    r = np.random.default_rng(seed).normal(size=len(names))
    return (amount * np.tensordot(r, dev, axes=1) / np.sqrt(len(names))).astype(np.float32)


def validate_recipe(recipe: dict) -> dict:
    if not isinstance(recipe, dict):
        raise ValueError("Recipe must be an object.")
    items = recipe.get("voices")
    if not isinstance(items, list) or not 1 <= len(items) <= 5:
        raise ValueError("Pick between 2 and 5 voices to blend.")
    ids, ws = [], []
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("id"), str):
            raise ValueError("Each voice needs an id and a weight.")
        try:
            w = float(it.get("weight", 1))
        except (TypeError, ValueError):
            raise ValueError("Weights must be numbers.") from None
        ids.append(it["id"])
        ws.append(w)
    if len(set(ids)) != len(ids):
        raise ValueError("Each voice can be used once in a blend.")
    var = recipe.get("variation") or {}
    if len(ids) < 2 and not var.get("amount"):
        raise ValueError("Pick between 2 and 5 voices to blend.")
    w = normalise_weights(ws)
    stock = set(_stock_names())
    for i in ids:
        if i not in stock:
            if not i.startswith("custom:"):
                raise ValueError(f"Unknown voice {i[:40]!r}.")
            try:
                vlib.get(i)
            except (KeyError, ValueError):
                raise ValueError(f"Unknown voice {i[:40]!r}.") from None
    controls = {}
    for k, v in (recipe.get("controls") or {}).items():
        if k not in CONTROLS:
            raise ValueError(f"Unknown control {str(k)[:30]!r}.")
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError("Control values must be numbers.") from None
        c = CONTROLS[k]
        if not np.isfinite(v) or not c["min"] <= v <= c["max"]:
            raise ValueError(f"{c['label']} must be between {c['min']} and {c['max']}.")
        controls[k] = v
    try:
        seed, amount = int(var.get("seed", 0)), float(var.get("amount", 0))
    except (TypeError, ValueError):
        raise ValueError("Variation must be numbers.") from None
    if not np.isfinite(amount) or not 0 <= amount <= 0.5 or not 0 <= seed < 2 ** 32:
        raise ValueError("Variation must be between 0 and 0.5.")
    out = {"voices": [{"id": i, "weight": round(float(x), 4)} for i, x in zip(ids, w)], "controls": controls}
    if amount:
        out["variation"] = {"seed": seed, "amount": amount}
    return out


def build_style(recipe: dict) -> tuple[np.ndarray, str]:
    """Validated recipe -> (style, lang). Language follows the heaviest voice."""
    r = validate_recipe(recipe)
    styles = [vlib.style_of(v["id"]) for v in r["voices"]]
    style = blend(styles, [v["weight"] for v in r["voices"]])
    for k, v in r["controls"].items():
        style = style + np.float32(v * CONTROLS[k]["scale"]) * _axes()[k]
    if "variation" in r:
        style = style + _variation(r["variation"]["seed"], r["variation"]["amount"])
    top = max(r["voices"], key=lambda v: v["weight"])["id"]
    return style.astype(np.float32), voice_lang(top)


def voice_lang(voice_id: str) -> str:
    if voice_id.startswith("custom:"):
        return vlib.get(voice_id).get("lang", "en-us")
    return vlib.lang_for(voice_id)


# ---------------------------------------------------------------- library + previews

def library() -> list[dict]:
    out = []
    for r in vlib.catalog():
        r = dict(r)
        if r.get("kind") != "stock":
            meta = r.get("meta") or {}
            r["gender"] = meta.get("gender", "unknown")
            r["language"] = next((vlib.LANG_NAMES[k] for k, v in vlib.LANGS.items() if v == r.get("lang")), "Other")
            r["editable"] = "recipe" in meta
        out.append(r)
    return out


def sample_text(lang: str) -> str:
    return SAMPLE_LINES.get(lang, SAMPLE_LINES["en-us"])


def preview_path(voice_id: str) -> Path:
    key = hashlib.sha1(f"{voice_id}|{FEATURE_VERSION}".encode()).hexdigest()[:20]
    return data_dir() / "previews" / f"{key}.wav"


def render_preview(voice_id: str) -> Path:
    """Render (or reuse) the fixed sample line for a library voice."""
    from . import audio

    p = preview_path(voice_id)
    if p.exists():
        return p
    style, lang = vlib.resolve(voice_id)
    style = vlib.style_of(voice_id) if isinstance(style, str) else style
    a = render(style, lang, sample_text(lang))
    tmp = p.with_suffix(".tmp.wav")
    audio.save(tmp, a, SR)
    tmp.replace(p)
    return p


def drop_preview(voice_id: str) -> None:
    preview_path(voice_id).unlink(missing_ok=True)


# ---------------------------------------------------------------- describe

_CHAR = None


def character_features() -> dict[str, dict]:
    """Shipped pitch/brightness per stock voice (scripts/build_voicelab_features.py)."""
    global _CHAR
    if _CHAR is None:
        try:
            _CHAR = json.loads((Path(__file__).with_name("voicelab_features.json")).read_text())["voices"]
        except (OSError, ValueError, KeyError):
            _CHAR = {}
    return _CHAR


ACCENTS = {  # keyword -> Kokoro language prefix
    "american": "a", "us": "a", "usa": "a", "british": "b", "english": "b", "uk": "b", "london": "b",
    "spanish": "e", "french": "f", "hindi": "h", "indian": "h", "italian": "i", "portuguese": "p",
    "brazilian": "p", "japanese": "j", "chinese": "z", "mandarin": "z",
}
LOW = {"deep", "low", "bass", "baritone", "gravelly", "older", "old", "mature", "elderly", "authoritative", "dark"}
HIGH = {"high", "light", "bright", "young", "youthful", "teen", "childlike", "airy", "thin"}
WARM = {"warm", "soft", "smooth", "gentle", "calm", "soothing", "mellow", "rich"}
CRISP = {"crisp", "clear", "sharp", "energetic", "lively", "upbeat", "excited", "bright"}
FEMALE = {"female", "woman", "women", "girl", "lady", "feminine", "she", "her"}
MALE = {"male", "man", "men", "guy", "boy", "masculine", "he", "him", "gentleman"}


def describe(prompt: str = "", gender: str = "", accent: str = "", age: str = "", energy: str = "",
             count: int = 3, seed: int | None = None) -> dict:
    """Keyword-based voice design: pick matching stock voices using tags and measured pitch/brightness."""
    if len(prompt) > MAX_TEXT:
        raise ValueError(f"Description too long ({MAX_TEXT} characters max).")
    words = set(re.findall(r"[a-z]+", prompt.lower()))
    notes = []
    g = gender if gender in {"female", "male"} else ("female" if words & FEMALE else "male" if words & MALE else "")
    lang = accent if accent in vlib.LANGS else next((ACCENTS[w] for w in re.findall(r"[a-z]+", prompt.lower())
                                                     if w in ACCENTS), "")
    pitch_dir = -1 if (words & LOW or age == "older") else 1 if (words & HIGH or age == "young") else 0
    tone_dir = -1 if (words & WARM or energy == "calm") else 1 if (words & CRISP or energy == "energetic") else 0
    names = _stock_names()
    pool = [n for n in names if (not g or n[1] == g[0]) and (not lang or n[0] == lang)]
    if not pool:
        notes.append("No stock voice matches every filter, so the language filter was relaxed.")
        pool = [n for n in names if not g or n[1] == g[0]]
    if not lang:
        en = [n for n in pool if n[0] in "ab"]
        pool = en or pool
    feats = character_features()
    score = np.zeros(len(pool))
    if (pitch_dir or tone_dir) and not all(n in feats for n in pool):
        notes.append("Pitch and tone words only steer English voices (the measured ones); "
                     "these options are picked by gender and language.")
    elif pitch_dir or tone_dir:
        p = np.array([feats[n]["pitch"] for n in pool])
        b = np.array([feats[n]["brightness"] for n in pool])
        z = lambda v: (v - v.mean()) / (v.std() + 1e-9)  # noqa: E731
        score = pitch_dir * z(p) + 0.6 * tone_dir * z(b)
    order = [pool[i] for i in np.argsort(-score, kind="stable")]
    rng = np.random.default_rng(seed)
    top = order[: max(3, min(6, len(order)))]
    options = []
    for i in range(count):
        k = min(len(top), int(rng.integers(2, 4)))
        pick = list(rng.choice(top, size=k, replace=False)) if len(top) >= 2 else top
        w = rng.dirichlet(np.ones(len(pick)) * 2)
        recipe = {"voices": [{"id": str(n), "weight": round(float(x), 3)} for n, x in zip(pick, w)],
                  "controls": {}, "variation": {"seed": int(rng.integers(0, 2 ** 31)), "amount": 0.12}}
        if g:
            recipe["controls"]["gender"] = 0.2 if g == "female" else -0.2
        options.append({"recipe": validate_recipe(recipe),
                        "summary": "Blend of " + ", ".join(vlib.stock_info(str(n))["name"] for n in pick)})
    understood = [x for x in [g, vlib.LANG_NAMES.get(lang, ""), {-1: "lower pitch", 1: "higher pitch"}.get(pitch_dir),
                              {-1: "warmer tone", 1: "brighter tone"}.get(tone_dir)] if x]
    return {"options": options, "understood": understood, "notes": notes}


# ---------------------------------------------------------------- match a recording

class Cancelled(Exception):
    pass


def match(ref: np.ndarray, ref_sr: int, budget_s: float = 180, candidates: list[str] | None = None,
          top_k: int = 3, progress=None, cancel=None, seed: int = 0) -> dict:
    """Search Kokoro style space for a voice whose rendering sounds like `ref` (cosine on CAM++ embeddings)."""
    t0 = time.time()
    say = progress or (lambda **kw: None)
    ref_emb = embed(ref, ref_sr)
    names = candidates or [n for n in _stock_names() if n[0] in "ab"]
    say(step="Comparing with stock voices", progress=0.02)
    feats = stock_features(names, progress=lambda i, n: say(step=f"Measuring stock voices {i}/{n}",
                                                                      progress=0.02 + 0.18 * i / n), cancel=cancel)
    if cancel is not None and cancel.is_set():
        raise Cancelled
    scores = sorted(((cosine(ref_emb, feats[n]["emb"]), n) for n in feats), reverse=True)
    top = scores[:top_k]
    sims = np.array([s for s, _ in top])
    w = np.exp((sims - sims.max()) / 0.05)
    styles = [vlib.style_of(n) for _, n in top]
    best = blend(styles, w)
    best_sim = cosine(ref_emb, embed(render(best, "en-us", MEASURE_LINE), SR))
    if top[0][0] > best_sim:  # the single best stock voice beat the blend: start from it instead
        best, best_sim = styles[0].copy(), top[0][0]
    start_sim, start_style = best_sim, best.copy()
    # perturbation basis: stock voices' deviations from their mean (stays inside the voice manifold)
    st = np.stack([vlib.style_of(n) for n in _stock_names()]).astype(np.float32)
    dev = st - st.mean(0)
    rng = np.random.default_rng(seed)
    sigma, tries, kept = 0.25, 0, 0
    search_t0 = time.time()
    remaining = max(0.0, budget_s - (search_t0 - t0))
    while time.time() - search_t0 < remaining:
        if cancel is not None and cancel.is_set():
            raise Cancelled
        r = rng.normal(size=len(dev)).astype(np.float32)
        cand = best + sigma * np.tensordot(r, dev, axes=1) / np.sqrt(len(dev))
        sim = cosine(ref_emb, embed(render(cand, "en-us", MEASURE_LINE), SR))
        tries += 1
        if sim > best_sim:
            best, best_sim, kept = cand.astype(np.float32), sim, kept + 1
            sigma = min(0.5, sigma * 1.3)
        else:
            sigma = max(0.03, sigma * 0.93)
        frac = min(1.0, (time.time() - search_t0) / max(remaining, 1e-6))
        say(step=f"Refining: {tries} tries, {kept} improvements", progress=round(0.2 + 0.78 * frac, 3),
            similarity=round(best_sim, 4))
    return {"style": best, "start_style": start_style, "before": round(start_sim, 4), "after": round(best_sim, 4),
            "best_stock": [{"id": n, "similarity": round(s, 4)} for s, n in top],
            "tries": tries, "kept": kept, "seconds": round(time.time() - t0, 1)}
