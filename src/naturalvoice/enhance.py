"""Optional neural cleanup with GTCRN (Rong et al., ICASSP 2024): a 48k-parameter speech
enhancement model that runs frame by frame on any CPU (github.com/Xiaobin-Rong/gtcrn, ONNX streaming
model stream/onnx_models/gtcrn_simple.onnx).

GTCRN works at 16 kHz, which would make a 24-48 kHz voice sound muffled. So instead of using its
output directly we read off the *gain* it applies to each frequency band and frame, then apply that
gain to the full-bandwidth original. Above 8 kHz we reuse the gain of the 6-8 kHz band.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import signal

from .quality import to_16k
from .tts import MODEL_DIR

N_FFT, HOP = 512, 256
GTCRN_URL = "https://github.com/Xiaobin-Rong/gtcrn/raw/main/stream/onnx_models/gtcrn_simple.onnx"


def available() -> bool:
    return (Path(MODEL_DIR) / "gtcrn_simple.onnx").exists()


@lru_cache(maxsize=1)
def _session():
    import onnxruntime as ort

    p = Path(MODEL_DIR) / "gtcrn_simple.onnx"
    if not p.exists():
        raise RuntimeError(f"GTCRN model missing: download {GTCRN_URL} into {MODEL_DIR}")
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.log_severity_level = 3
    return ort.InferenceSession(str(p), opts, providers=["CPUExecutionProvider"])


def _stft16(x: np.ndarray) -> np.ndarray:
    win = np.hanning(N_FFT + 1)[:-1] ** 0.5  # periodic sqrt-Hann, as torch.hann_window(512).pow(0.5)
    y = np.pad(x, N_FFT // 2, mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(y, N_FFT)[::HOP]
    return np.fft.rfft(frames * win, axis=1).T  # (257, T)


def gain_mask(x: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run GTCRN; return (gain[257, T], freqs_hz, frame_times_s)."""
    sess = _session()
    X = _stft16(to_16k(x, sr))
    conv = np.zeros([2, 1, 16, 16, 33], np.float32)
    tra = np.zeros([2, 3, 1, 1, 16], np.float32)
    inter = np.zeros([2, 1, 33, 16], np.float32)
    inp = np.stack([X.real, X.imag], axis=-1).astype(np.float32)[None]  # (1, 257, T, 2)
    out = np.empty_like(inp)
    for t in range(inp.shape[2]):
        o, conv, tra, inter = sess.run(
            None, {"mix": inp[:, :, t : t + 1], "conv_cache": conv, "tra_cache": tra, "inter_cache": inter}
        )
        out[:, :, t : t + 1] = o
    E = out[0, ..., 0] + 1j * out[0, ..., 1]
    g = np.abs(E) / (np.abs(X) + 1e-8)
    return np.clip(g, 0.0, 1.0), np.fft.rfftfreq(N_FFT, 1 / 16000), np.arange(X.shape[1]) * HOP / 16000


def ai_clean(x: np.ndarray, sr: int, amount: float, floor_db: float = -20.0) -> np.ndarray:
    if amount <= 0:
        return x
    g16, f16, t16 = gain_mask(x, sr)
    n_fft = int(2 ** np.ceil(np.log2(0.032 * sr)))
    hop = n_fft // 4
    f, t, Z = signal.stft(x, fs=sr, nperseg=n_fft, noverlap=n_fft - hop)
    # carry the 6-8 kHz gain to everything above 8 kHz
    top = g16[(f16 >= 6000) & (f16 <= 7900)].mean(axis=0, keepdims=True)
    # frequency interpolation (per 16 kHz frame) then time interpolation onto our frames
    gf = np.empty((len(f), g16.shape[1]))
    below = f <= f16[-1]
    for k in range(g16.shape[1]):
        gf[below, k] = np.interp(f[below], f16, g16[:, k])
    gf[~below] = top
    G = np.empty((len(f), len(t)))
    for i in range(len(f)):
        G[i] = np.interp(t, t16, gf[i])
    G = np.maximum(G, 10 ** (floor_db / 20))
    G = 1 - amount * (1 - G)
    _, y = signal.istft(Z * G, fs=sr, nperseg=n_fft, noverlap=n_fft - hop)
    y = y[: len(x)]
    if len(y) < len(x):
        y = np.pad(y, (0, len(x) - len(y)))
    return y.astype(np.float32)
