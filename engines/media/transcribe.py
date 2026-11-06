"""One local speech-to-text job per process; no network or main-app imports."""

from __future__ import annotations

import json
import sys
import unicodedata
import wave
from collections.abc import Iterator
from pathlib import Path

import numpy as np

ASR = Path(__file__).resolve().parent / "models" / "asr"
RATE = 16000
MAX_SECONDS = 4 * 3600
WINDOW = 30.0
SEARCH = 5.0
FRAME = 0.02


def audio_frames(src: wave.Wave_read) -> int:
    if src.getsampwidth() != 2 or src.getnchannels() != 1 or src.getframerate() != RATE:
        raise ValueError("Expected mono 16 kHz PCM16 audio.")
    if src.getnframes() > MAX_SECONDS * RATE:
        raise ValueError("Media exceeds four hours.")
    return src.getnframes()


def quiet_cut(samples: np.ndarray, rate: int) -> int:
    size = max(1, int(rate * FRAME))
    start = max(0, len(samples) - int(SEARCH * rate))
    frames = (len(samples) - start) // size
    if frames == 0:
        return len(samples)
    region = samples[start : start + frames * size].astype(np.float64).reshape(frames, size)
    quietest = int(np.argmin((region**2).mean(axis=1)))
    return start + quietest * size + size // 2


def read_windows(path: Path, window: float = WINDOW) -> Iterator[tuple[float, np.ndarray]]:
    with wave.open(str(path), "rb") as src:
        total = audio_frames(src)
        size = int(window * RATE)
        offset, carry, read = 0, np.zeros(0, dtype=np.float32), 0
        while True:
            want = min(size - len(carry), total - read)
            chunk = np.frombuffer(src.readframes(want), dtype="<i2").astype(np.float32) / 32768
            read += len(chunk)
            data = np.concatenate([carry, chunk])
            if read >= total or len(chunk) < want:
                if len(data):
                    yield offset / RATE, data
                return
            # Cut where speech is least likely so no word straddles two windows.
            cut = quiet_cut(data, RATE)
            yield offset / RATE, data[:cut]
            offset += cut
            carry = data[cut:]


def punctuation(text: str) -> bool:
    return bool(text) and all(unicodedata.category(ch).startswith("P") for ch in text)


def words_from_tokens(
    tokens: list[str], timestamps: list[float], durations: list[float], offset: float, limit: float | None = None
) -> list[list[float | str]]:
    timed = len(durations) == len(tokens)
    groups: list[list[int]] = []
    for i, token in enumerate(tokens[: len(timestamps)]):
        starts = token.startswith(("▁", " "))
        text = token.lstrip("▁ ")
        if not text:
            continue
        if punctuation(text) or not (starts or not groups):
            if groups:
                groups[-1].append(i)
            continue
        groups.append([i])
    words: list[list[float | str]] = []
    for n, group in enumerate(groups):
        t0 = float(timestamps[group[0]])
        # Parakeet emits trailing punctuation late, so it must not stretch the spoken end.
        spoken = [i for i in group if not punctuation(tokens[i].lstrip("▁ "))] or group
        end_token = spoken[-1]
        last = float(timestamps[end_token])
        nxt = float(timestamps[groups[n + 1][0]]) if n + 1 < len(groups) else None
        if timed:
            t1 = last + max(0.0, float(durations[end_token]))
        else:
            ends = [last + 1.0] + ([nxt] if nxt is not None else []) + ([limit] if limit is not None else [])
            t1 = min(ends)
        if nxt is not None:
            t1 = min(t1, nxt)
        t1 = max(t0, t1)
        text = "".join(tokens[i].lstrip("▁ ") for i in group)
        words.append([round(offset + t0, 3), round(offset + t1, 3), unicodedata.normalize("NFC", text)])
    return words


def recognizer():  # sherpa_onnx is untyped and only installed in the engine env
    import sherpa_onnx as sherpa

    names = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
    if not all((ASR / name).is_file() for name in names):
        raise ValueError("Speech model is unavailable.")
    return sherpa.OfflineRecognizer.from_transducer(
        encoder=str(ASR / names[0]),
        decoder=str(ASR / names[1]),
        joiner=str(ASR / names[2]),
        tokens=str(ASR / names[3]),
        num_threads=2,
        provider="cpu",
        decoding_method="greedy_search",
        model_type="nemo_transducer",
    )


def main() -> None:
    request = json.loads(sys.stdin.readline(8192))
    path = Path(request["path"])
    with wave.open(str(path), "rb") as src:
        duration = audio_frames(src) / RATE
    engine = recognizer()
    words: list[list[float | str]] = []
    for offset, samples in read_windows(path):
        stream = engine.create_stream()
        stream.accept_waveform(RATE, samples)
        engine.decode_stream(stream)
        result = stream.result
        durations = list(getattr(result, "durations", None) or [])
        words += words_from_tokens(list(result.tokens), list(result.timestamps), durations, offset, len(samples) / RATE)
        done = min(1.0, (offset + len(samples) / RATE) / duration) if duration else 1.0
        print(json.dumps({"progress": round(done, 4)}), flush=True)
    print(json.dumps({"duration": round(duration, 3), "words": words}, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
