"""Standard speech-quality scores used in research, so results mean something outside this app.

* DNSMOS (Microsoft, ITU-T P.835 style): predicts what human listeners would rate, 1-5, without
  needing a clean reference. SIG = voice quality, BAK = background/room, OVRL = overall, P808 = overall
  (P.808 model). Port of the scorer in microsoft/DNS-Challenge and modelscope/ClearerVoice-Studio
  (speechscore/scores/dnsmos/dnsmos.py), with librosa's mel spectrogram re-implemented in numpy because
  librosa can't be installed on Intel Macs.
* PESQ wideband (ITU-T P.862.2): compares with the clean reference; 1 (bad) to 4.6 (identical).
* STOI: intelligibility vs the clean reference, 0-1.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import signal

from .tts import MODEL_DIR

SR = 16000
INPUT_LENGTH = 9.01
DNSMOS_URL = "https://github.com/microsoft/DNS-Challenge/raw/master/DNSMOS/DNSMOS/"


def to_16k(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR:
        return x.astype(np.float32)
    from math import gcd

    g = gcd(SR, sr)
    return signal.resample_poly(x, SR // g, sr // g).astype(np.float32)


# --------------------------------------------------------------------------- mel (librosa-compatible)

def _hz_to_mel(f):
    f = np.asarray(f, dtype=float)
    f_sp, min_log_hz = 200.0 / 3, 1000.0
    min_log_mel, logstep = min_log_hz / f_sp, np.log(6.4) / 27.0
    return np.where(f >= min_log_hz, min_log_mel + np.log(np.maximum(f, 1e-10) / min_log_hz) / logstep, f / f_sp)


def _mel_to_hz(m):
    m = np.asarray(m, dtype=float)
    f_sp, min_log_hz = 200.0 / 3, 1000.0
    min_log_mel, logstep = min_log_hz / f_sp, np.log(6.4) / 27.0
    return np.where(m >= min_log_mel, min_log_hz * np.exp(logstep * (m - min_log_mel)), f_sp * m)


@lru_cache(maxsize=4)
def _mel_basis(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    fft_f = np.fft.rfftfreq(n_fft, 1.0 / sr)
    mel_f = _mel_to_hz(np.linspace(_hz_to_mel(0.0), _hz_to_mel(sr / 2.0), n_mels + 2))
    fdiff = np.diff(mel_f)
    ramps = mel_f[:, None] - fft_f[None, :]
    lower = -ramps[:-2] / fdiff[:-1, None]
    upper = ramps[2:] / fdiff[1:, None]
    w = np.maximum(0, np.minimum(lower, upper))
    w *= (2.0 / (mel_f[2: n_mels + 2] - mel_f[:n_mels]))[:, None]  # slaney norm
    return w


def melspec_db(audio: np.ndarray, n_mels=120, frame_size=320, hop=160, sr=SR) -> np.ndarray:
    n_fft = frame_size + 1
    y = np.pad(audio, n_fft // 2, mode="constant")
    win = signal.get_window("hann", n_fft, fftbins=True)
    frames = np.lib.stride_tricks.sliding_window_view(y, n_fft)[::hop]
    S = np.abs(np.fft.rfft(frames * win, axis=1)) ** 2
    M = S @ _mel_basis(sr, n_fft, n_mels).T
    db = 10 * np.log10(np.maximum(M, 1e-10))
    db -= 10 * np.log10(max(M.max(), 1e-10))
    db = np.maximum(db, db.max() - 80.0)
    return ((db + 40) / 40).astype(np.float32)  # (T, n_mels)


# --------------------------------------------------------------------------- DNSMOS

@lru_cache(maxsize=1)
def _dnsmos_sessions():
    import onnxruntime as ort

    p1, p2 = Path(MODEL_DIR) / "dnsmos_sig_bak_ovr.onnx", Path(MODEL_DIR) / "dnsmos_p808.onnx"
    if not p1.exists() or not p2.exists():
        raise RuntimeError(f"DNSMOS models missing in {MODEL_DIR}: get sig_bak_ovr.onnx and model_v8.onnx from {DNSMOS_URL}")
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    return ort.InferenceSession(str(p1), opts), ort.InferenceSession(str(p2), opts)


def dnsmos(x: np.ndarray, sr: int) -> dict:
    audio = to_16k(x, sr)
    main, p808 = _dnsmos_sessions()
    n = int(INPUT_LENGTH * SR)
    while len(audio) < n:
        audio = np.append(audio, audio)
    hops = int(np.floor(len(audio) / SR) - INPUT_LENGTH) + 1
    sig, bak, ovr, p = [], [], [], []
    p_sig = np.poly1d([-0.08397278, 1.22083953, 0.0052439])
    p_bak = np.poly1d([-0.13166888, 1.60915514, -0.39604546])
    p_ovr = np.poly1d([-0.06766283, 1.11546468, 0.04602535])
    for i in range(hops):
        seg = audio[i * SR: i * SR + n]
        if len(seg) < n:
            continue
        mel = melspec_db(seg[:-160])[:900][None]
        p.append(float(p808.run(None, {"input_1": mel})[0][0][0]))
        s, b, o = main.run(None, {"input_1": seg[None].astype(np.float32)})[0][0]
        sig.append(p_sig(s)); bak.append(p_bak(b)); ovr.append(p_ovr(o))
    return {"SIG": float(np.mean(sig)), "BAK": float(np.mean(bak)), "OVRL": float(np.mean(ovr)),
            "P808": float(np.mean(p))}


# --------------------------------------------------------------------------- reference-based

def pesq_wb(ref: np.ndarray, y: np.ndarray, sr: int) -> float | None:
    from pesq import pesq, PesqError

    try:
        return float(pesq(SR, to_16k(ref, sr), to_16k(y[: len(ref)], sr), "wb"))
    except (PesqError, ValueError):
        return None
