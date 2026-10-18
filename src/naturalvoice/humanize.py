"""The cleanup chain that takes the 'AI' out of an AI voice.

What makes synthetic speech sound fake, and what each stage does about it:

* Echo / hollow room tail   -> WPE dereverberation (removes late reflections).
* Metallic ringing          -> finds narrow, persistent resonance peaks in the
                               long-term spectrum and notches them out.
* Harsh, fizzy top end      -> dynamic de-harsh on 4-9 kHz plus a gentle high shelf
                               cut where vocoder aliasing lives.
* Thin, 'digital' body      -> low-mid warmth and very light soft saturation.
* Residual artifact hiss    -> light spectral noise reduction.
* Dead digital silence      -> optional, very quiet room tone under the voice.
* Uneven level              -> loudness normalisation (-16 LUFS) with a peak limiter.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, replace

import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter1d, median_filter


@dataclass(frozen=True)
class Settings:
    ai_clean: float = 0.0  # 0..1 neural cleanup (GTCRN); needs models/gtcrn_simple.onnx
    dereverb: float = 0.8  # 0..1 how much echo to remove
    demetal: float = 0.7  # 0..1 how hard to cut metallic resonances
    deharsh: float = 0.6  # 0..1 taming of fizzy 4-9 kHz
    warmth: float = 0.5  # 0..1 low-mid body + soft saturation
    denoise: float = 0.0  # 0..1 residual hiss/artifact removal
    room_tone: float = 0.3  # 0..1 quiet natural room tone (0 = off)
    loudness: float = -16.0  # target LUFS

    def to_dict(self) -> dict:
        return asdict(self)


# Tuned with `naturalvoice bench` (DNSMOS / PESQ / STOI on realistic damage). Findings:
# the neural cleanup gives the biggest listener-rating gain and only works well at full strength;
# de-metal, de-harsh and warmth are neutral-to-positive; the classic echo remover raises clarity
# (STOI/PESQ) but slightly lowers the predicted rating, so it is used lightly by default.
PRESETS: dict[str, Settings] = {
    # Freshly generated TTS: dry already, just de-metal and warm up.
    "light": Settings(ai_clean=0.0, dereverb=0.0, demetal=0.5, deharsh=0.4, warmth=0.5, denoise=0.0, room_tone=0.3),
    # Typical AI voice-over in ads / videos.
    "standard": Settings(ai_clean=1.0, dereverb=0.3),
    # Badly processed, very echoey or robotic voices: favour clarity.
    "strong": Settings(ai_clean=1.0, dereverb=0.6, demetal=1.0, deharsh=0.9, warmth=0.7, denoise=0.0, room_tone=0.3),
}


def get_settings(preset: str = "standard", **overrides) -> Settings:
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset {preset!r}; choose from {', '.join(PRESETS)}")
    clean = {k: v for k, v in overrides.items() if v is not None}
    return replace(PRESETS[preset], **clean)


# --------------------------------------------------------------------------- helpers


def _stft_params(sr: int) -> tuple[int, int]:
    n_fft = 512 if sr <= 16000 else 1024 if sr <= 24000 else 2048
    return n_fft, n_fft // 4


def _stft(x: np.ndarray, sr: int):
    n_fft, hop = _stft_params(sr)
    f, _, Z = signal.stft(x, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, boundary="even", padded=True)
    return f, Z


def _istft(Z: np.ndarray, sr: int, length: int) -> np.ndarray:
    n_fft, hop = _stft_params(sr)
    _, x = signal.istft(Z, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, boundary=True)
    x = x[:length]
    if len(x) < length:
        x = np.pad(x, (0, length - len(x)))
    return x.astype(np.float32)


def _db(x):
    return 20 * np.log10(np.maximum(x, 1e-10))


# --------------------------------------------------------------------------- stages


def estimate_rt60(x: np.ndarray, sr: int) -> float:
    """Blind decay-time estimate: median slope of the energy envelope right after speech stops."""
    hop = int(0.01 * sr)
    win = int(0.03 * sr)
    if len(x) < win * 20:
        return 0.5
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::hop]
    e = 10 * np.log10(np.mean(frames**2, axis=1) + 1e-12)
    e = uniform_filter1d(e, 3)
    peak = np.percentile(e, 95)
    slopes = []
    i = 1
    while i < len(e) - 40:
        if e[i] > peak - 15 and e[i] >= e[i - 1] and e[i + 1] < e[i]:
            seg = e[i : i + 40]  # 400 ms
            j = 1
            while j < len(seg) and seg[j] < seg[j - 1] + 0.5:
                j += 1
            seg = seg[:j]
            if len(seg) >= 6 and seg[0] - seg[-1] > 10:
                # fit the decay between -5 and -25 dB below the start (the 'tail' part)
                m = (seg < seg[0] - 5) & (seg > seg[0] - 25)
                if m.sum() >= 3:
                    t = np.nonzero(m)[0] * 0.01
                    k = np.polyfit(t, seg[m], 1)[0]
                    if k < -1:
                        slopes.append(-60.0 / k)
            i += max(j, 1)
            continue
        i += 1
    if len(slopes) < 2:
        return 0.5
    return float(np.clip(np.median(slopes), 0.2, 1.5))


def dereverb(x: np.ndarray, sr: int, amount: float, rt60: float | None = None, gate: float = 1.0) -> np.ndarray:
    """Remove echo: (1) late-reverb spectral subtraction (Lebart-style, decay-time based),
    then (2) a soft gate that pulls the leftover tail down in pauses between words."""
    if amount <= 0:
        return x
    rt = rt60 or estimate_rt60(x, sr)
    # Only act as hard as the room is echoey: dry voices (rt < ~0.3 s) are left almost alone.
    amount = amount * float(np.clip((rt - 0.28) / 0.25, 0.0, 1.0))
    if amount <= 0.02:
        return x
    n_fft, hop = _stft_params(sr)
    _, Z = _stft(x, sr)
    P = uniform_filter1d(np.abs(Z) ** 2, size=3, axis=1)
    td = 0.03
    d = max(1, int(round(td * sr / hop)))
    delta = 3 * np.log(10) / rt
    late = np.zeros_like(P)
    late[:, d:] = np.exp(-2 * delta * d * hop / sr) * P[:, :-d]
    over = 1.0 + 0.6 * amount
    floor = 10 ** ((-8 - 17 * amount) / 10)
    g = np.sqrt(np.maximum(1 - over * late / (P + 1e-12), floor))
    g = uniform_filter1d(uniform_filter1d(g, 3, axis=1), 3, axis=0)
    Z = Z * g

    # Soft gate on the decaying tail: frames far below recent speech level are attenuated.
    e = 10 * np.log10((np.abs(Z) ** 2).sum(axis=0) + 1e-12)
    look = max(1, int(0.25 * sr / hop))
    from scipy.ndimage import maximum_filter1d

    recent = maximum_filter1d(e, size=2 * look + 1, origin=look // 2)  # mostly looks back
    below = recent - e
    start, rng = 18.0, 20.0
    att_db = -np.clip((below - start) / rng, 0, 1) * (24.0 * amount * gate)
    # fast attack (open instantly when speech returns), slow-ish release
    sm = np.empty_like(att_db)
    acc = 0.0
    rel = np.exp(-hop / (0.06 * sr))
    for t, a in enumerate(att_db):
        acc = a if a > acc else rel * acc + (1 - rel) * a
        sm[t] = acc
    Z = Z * (10 ** (sm / 20))[None, :]
    return _istft(Z, sr, len(x))


def find_resonances(x: np.ndarray, sr: int, fmin=900.0, fmax=11000.0, thresh_db=2.0, max_peaks=10):
    """Return [(freq_hz, excess_db, width_hz)] of *persistent* narrow spectral peaks.

    Natural formants move from vowel to vowel; metallic ringing (vocoder or processing artefacts)
    sits at the same frequency in every frame. So: per-frame excess over a local spectral envelope,
    then the median across all active frames. Only peaks that are there nearly all the time survive.
    """
    f, Z = _stft(x, sr)
    mag2 = np.abs(Z) ** 2
    e = mag2.sum(axis=0)
    active = e > np.percentile(e, 40)
    if active.sum() < 4:
        return []
    L = 10 * np.log10(mag2[:, active] + 1e-20)
    L = uniform_filter1d(L, 3, axis=0)  # smear individual harmonics
    df = f[1] - f[0]
    w = max(5, int(900 / df) | 1)
    excess = np.median(L - median_filter(L, size=(w, 1), mode="nearest"), axis=1)
    band = (f >= fmin) & (f <= min(fmax, sr * 0.45))
    masked = np.where(band, excess, 0.0)  # 0 = 'no excess' (a large negative value would wreck peak widths)
    peaks, props = signal.find_peaks(masked, height=thresh_db, width=(1, int(500 / df) + 1), wlen=int(2000 / df))
    order = np.argsort(props["peak_heights"])[::-1][:max_peaks]
    return [
        (float(f[peaks[i]]), float(props["peak_heights"][i]), float(max(props["widths"][i] * df, 2 * df)))
        for i in order
    ]


def demetal(x: np.ndarray, sr: int, amount: float) -> np.ndarray:
    """Notch out persistent metallic resonances and smooth vocoder 'buzz' above 5 kHz."""
    if amount <= 0:
        return x
    f, Z = _stft(x, sr)
    gain_db = np.zeros(len(f))
    for fc, excess, width in find_resonances(x, sr):
        cut = min(excess * (0.6 + 0.4 * amount), 14.0) * amount
        sigma = max(width / 2.0, f[1] - f[0])
        gain_db -= cut * np.exp(-0.5 * ((f - fc) / sigma) ** 2)
    Z = Z * (10 ** (gain_db / 20))[:, None]

    # Vocoder buzz: frame-to-frame magnitude flicker in the top band. Smoothing the
    # magnitude over time (keeping phase) softens the 'robotic' flutter.
    hi = f >= 5000
    if hi.any():
        mag = np.abs(Z[hi])
        k = 1 + int(round(2 * amount))  # 1..3 frames
        sm = uniform_filter1d(mag, size=2 * k + 1, axis=1, mode="nearest")
        newmag = (1 - 0.6 * amount) * mag + 0.6 * amount * np.minimum(sm, mag * 1.5)
        Z[hi] = Z[hi] / np.maximum(mag, 1e-10) * newmag
    return _istft(Z, sr, len(x))


def deharsh(x: np.ndarray, sr: int, amount: float) -> np.ndarray:
    """Dynamic reduction of 4-9 kHz when it gets too loud relative to the body of the voice."""
    if amount <= 0:
        return x
    f, Z = _stft(x, sr)
    mag2 = np.abs(Z) ** 2
    harsh = (f >= 4000) & (f <= 9000)
    body = (f >= 200) & (f <= 3000)
    if not harsh.any() or not body.any():
        return x
    body_e = mag2[body].sum(0) + 1e-12
    ratio_db = 10 * np.log10((mag2[harsh].sum(0) + 1e-12) / body_e)
    # Only voiced frames (strong body energy). Natural 's'/'sh' sounds are unvoiced and must stay crisp;
    # vocoder fizz rides on top of voiced sounds, where 4-9 kHz is normally 12+ dB below the body.
    body_db = 10 * np.log10(body_e)
    voiced = body_db > np.percentile(body_db, 98) - 20
    thresh = -12.0 + 4.0 * (1 - amount)
    over = np.where(voiced, np.clip(ratio_db - thresh, 0, None), 0.0)
    red_db = -np.minimum(over * (0.5 + 0.4 * amount), 9.0 * amount)
    red_db = uniform_filter1d(red_db, size=5, mode="nearest")  # avoid pumping
    weight = np.zeros(len(f))
    weight[harsh] = np.hanning(harsh.sum() + 2)[1:-1] ** 0.5
    Z = Z * 10 ** ((weight[:, None] * red_db[None, :]) / 20)
    return _istft(Z, sr, len(x))


def tone(x: np.ndarray, sr: int, warmth: float, deharsh_amt: float) -> np.ndarray:
    from pedalboard import Pedalboard, Plugin, HighpassFilter, LowShelfFilter, HighShelfFilter, PeakFilter

    fx: list[Plugin] = [HighpassFilter(cutoff_frequency_hz=70)]
    if warmth > 0:
        fx += [
            LowShelfFilter(cutoff_frequency_hz=220, gain_db=2.5 * warmth, q=0.7),
            PeakFilter(cutoff_frequency_hz=3000, gain_db=-1.0 * warmth, q=0.8),
        ]
    if deharsh_amt > 0 and sr > 22000:
        fx.append(HighShelfFilter(cutoff_frequency_hz=10000, gain_db=-3.0 * deharsh_amt, q=0.7))
    y = Pedalboard(fx)(x[None, :].astype(np.float32), sr)[0]
    if warmth > 0:  # very light tape-style saturation adds natural harmonics
        peak = np.max(np.abs(y)) + 1e-9
        k = 1.5
        sat = np.tanh(k * y / peak) / np.tanh(k) * peak
        y = (1 - 0.25 * warmth) * y + 0.25 * warmth * sat
    return y.astype(np.float32)


def denoise(x: np.ndarray, sr: int, amount: float) -> np.ndarray:
    if amount <= 0:
        return x
    import noisereduce as nr

    y = nr.reduce_noise(y=x, sr=sr, stationary=True, prop_decrease=0.35 + 0.5 * amount, n_fft=_stft_params(sr)[0])
    return y.astype(np.float32)


def add_room_tone(x: np.ndarray, sr: int, amount: float, seed: int = 7) -> np.ndarray:
    """Very quiet warm noise (-58 dB below the voice at full) so pauses aren't dead digital silence."""
    if amount <= 0:
        return x
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(len(x)).astype(np.float32)
    b, a = signal.butter(1, 400 / (sr / 2), btype="low")  # warm, roomy
    n = signal.lfilter(b, a, n).astype(np.float32)
    n /= np.sqrt(np.mean(n**2)) + 1e-9
    level = np.sqrt(np.mean(x**2)) + 1e-9
    return x + n * level * (10 ** (-58 / 20)) * amount


def soft_limit(
    x: np.ndarray, sr: int, ceiling_db: float = -1.0, lookahead_ms: float = 5.0, release_ms: float = 150.0
) -> np.ndarray:
    """Look-ahead peak limiter: gain drops just before a peak and recovers slowly (no distortion)."""
    from scipy.ndimage import minimum_filter1d

    ceil = 10 ** (ceiling_db / 20)
    blk = max(1, int(sr / 1000))  # 1 ms control blocks
    n = int(np.ceil(len(x) / blk))
    pad = np.pad(np.abs(x), (0, n * blk - len(x)))
    need = np.minimum(1.0, ceil / (pad.reshape(n, blk).max(axis=1) + 1e-9))
    la = max(1, int(round(lookahead_ms)))
    need = minimum_filter1d(need, size=2 * la + 1)
    rel = np.exp(-1.0 / release_ms)  # per 1 ms block
    g = np.empty(n)
    acc = 1.0
    for i, v in enumerate(need):  # instant attack (already look-ahead), slow release
        acc = v if v < acc else rel * acc + (1 - rel) * v
        g[i] = acc
    g = uniform_filter1d(g, size=la)
    gs = np.interp(np.arange(n * blk), np.arange(n) * blk + blk / 2, g)[: len(x)]
    return np.clip(x * gs, -ceil, ceil).astype(np.float32)


def normalize(x: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
    import pyloudnorm as pyln
    from pedalboard import Pedalboard, Compressor

    x = Pedalboard([Compressor(threshold_db=-26, ratio=1.4, attack_ms=20, release_ms=200)])(x[None, :], sr)[0]
    try:
        loud = pyln.Meter(sr).integrated_loudness(x.astype(np.float64))
        if np.isfinite(loud):
            gain_db = target_lufs - loud
            # Never drive peaks more than 3 dB into the limiter: squashed peaks sound processed.
            # Very spiky voices end up a little under target instead.
            peak_db = 20 * np.log10(np.max(np.abs(x)) + 1e-9)
            gain_db = min(gain_db, -1.0 + 3.0 - peak_db)
            x = x * 10 ** (gain_db / 20)
    except ValueError:  # too short to measure
        pass
    return soft_limit(x.astype(np.float32), sr)


# --------------------------------------------------------------------------- chain


def process_mono(x: np.ndarray, sr: int, s: Settings, progress=None) -> np.ndarray:
    from . import enhance

    steps = [
        ("AI cleanup", lambda y: enhance.ai_clean(y, sr, s.ai_clean) if s.ai_clean > 0 and enhance.available() else y),
        ("Removing echo", lambda y: dereverb(y, sr, s.dereverb)),
        ("Removing metallic tone", lambda y: demetal(y, sr, s.demetal)),
        ("Taming harshness", lambda y: deharsh(y, sr, s.deharsh)),
        ("Cleaning artifacts", lambda y: denoise(y, sr, s.denoise)),
        ("Adding warmth", lambda y: tone(y, sr, s.warmth, s.deharsh)),
        ("Room tone", lambda y: add_room_tone(y, sr, s.room_tone)),
        ("Levelling loudness", lambda y: normalize(y, sr, s.loudness)),
    ]
    y = x.astype(np.float32)
    for i, (name, fn) in enumerate(steps):
        if progress:
            progress(name, i / len(steps))
        y = fn(y)
    if progress:
        progress("Done", 1.0)
    return y


def humanize(audio: np.ndarray, sr: int, settings: Settings | None = None, progress=None) -> np.ndarray:
    """Process (samples,) or (samples, channels). Stereo is processed as mid/side-safe mono+stereo width."""
    s = settings or Settings()
    if audio.ndim == 1:
        return process_mono(audio, sr, s, progress)
    if audio.shape[1] == 1:
        return process_mono(audio[:, 0], sr, s, progress)[:, None]
    # Voices are near-mono: process the mid channel fully, keep a tamed side for width.
    mid = audio.mean(axis=1)
    side = (audio[:, 0] - audio[:, 1]) / 2
    mid_p = process_mono(mid, sr, s, progress)
    gain = np.sqrt(np.mean(mid_p**2) / (np.mean(mid**2) + 1e-12))
    side_p = side * gain * 0.5  # side carries most of the echo; reduce it
    return np.stack([mid_p + side_p, mid_p - side_p], axis=1).clip(-0.99, 0.99).astype(np.float32)
