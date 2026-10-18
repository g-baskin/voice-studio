"""Speaker-embedding cosine similarity (WeSpeaker ResNet34-LM, VoxCeleb, Apache-2.0, ONNX).

Usage: engines/chatterbox/.venv/bin/python engines/eval/speaker_sim.py ref.wav a.wav [b.wav ...]
Prints cosine(ref, x) for each file. Model: https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM
(fetch voxceleb_resnet34_LM.onnx into engines/eval/models/, sha256 7bb2f06e…c068).
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import onnxruntime as ort

MODEL = Path(__file__).resolve().parent / "models" / "voxceleb_resnet34_LM.onnx"


def read(path: str, sr: int = 16000) -> np.ndarray:
    with wave.open(path, "rb") as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    dt = {2: "<i2", 4: "<i4"}[width]
    x = np.frombuffer(raw, dtype=dt).astype(np.float32) / (2 ** (8 * width - 1))
    x = x.reshape(-1, ch).mean(axis=1)
    if rate != sr:  # linear resample is fine for an embedding comparison
        t = np.arange(0, len(x) / rate, 1 / sr)
        x = np.interp(t, np.arange(len(x)) / rate, x).astype(np.float32)
    return x


def fbank(x: np.ndarray, sr: int = 16000, n_mels: int = 80) -> np.ndarray:
    """Kaldi-style log-mel filterbank, 25 ms / 10 ms, with mean normalisation."""
    x = x * 32768
    flen, hop, nfft = 400, 160, 512
    n = 1 + (len(x) - flen) // hop
    frames = np.stack([x[i * hop:i * hop + flen] for i in range(n)])
    frames = frames - frames.mean(axis=1, keepdims=True)
    frames = np.concatenate([frames[:, :1], frames[:, 1:] - 0.97 * frames[:, :-1]], axis=1)
    frames *= np.hamming(flen) ** 0.85  # povey window
    spec = np.abs(np.fft.rfft(frames, nfft)) ** 2
    mel = lambda f: 1127 * np.log(1 + f / 700)
    pts = np.linspace(mel(20), mel(sr / 2), n_mels + 2)
    freqs = mel(np.fft.rfftfreq(nfft, 1 / sr))
    fb = np.zeros((n_mels, len(freqs)))
    for m in range(n_mels):
        l, c, r = pts[m:m + 3]
        fb[m] = np.clip(np.minimum((freqs - l) / (c - l), (r - freqs) / (r - c)), 0, None)
    feats = np.log(np.maximum(spec @ fb.T, 1.19e-7))
    return (feats - feats.mean(axis=0)).astype(np.float32)


def embed(sess, path: str) -> np.ndarray:
    e = sess.run(None, {"feats": fbank(read(path))[None]})[0][0]
    return e / np.linalg.norm(e)


def main(argv):
    sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    ref = embed(sess, argv[0])
    for p in argv[1:]:
        print(f"{float(ref @ embed(sess, p)):.3f}  {Path(p).name}")


if __name__ == "__main__":
    main(sys.argv[1:])
