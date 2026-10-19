"""One bounded media job per process; no network, model training or main-app imports."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx as sherpa

MODELS = Path(__file__).resolve().parent / "models"


def read_audio(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as src:
        if src.getsampwidth() != 2 or src.getnchannels() != 2 or src.getframerate() != 44100:
            raise ValueError("Expected stereo 44.1 kHz PCM16 audio.")
        if src.getnframes() > 121 * 44100:
            raise ValueError("Media window exceeds 120 seconds.")
        rate = src.getframerate()
        data = np.frombuffer(src.readframes(src.getnframes()), dtype="<i2").reshape(-1, 2)
    return data.astype(np.float32) / 32768, rate


def write_audio(path: Path, data: np.ndarray, rate: int) -> None:
    with wave.open(str(path), "wb") as dst:
        dst.setnchannels(2)
        dst.setsampwidth(2)
        dst.setframerate(rate)
        dst.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())


def separate(data: np.ndarray, rate: int) -> np.ndarray:
    config = sherpa.OfflineSourceSeparationConfig(
        model=sherpa.OfflineSourceSeparationModelConfig(
            spleeter=sherpa.OfflineSourceSeparationSpleeterModelConfig(
                vocals=str(MODELS / "vocals.onnx"), accompaniment=str(MODELS / "accompaniment.onnx")
            ),
            num_threads=2,
            provider="cpu",
        )
    )
    if not config.validate():
        raise ValueError("Separation models are unavailable.")
    engine = sherpa.OfflineSourceSeparation(config)
    # Overlapping context avoids hard inference edges without changing the source timeline.
    result = np.zeros_like(data)
    chunk, context = 10 * rate, rate
    for start in range(0, len(data), chunk):
        end = min(start + chunk, len(data))
        left, right = max(0, start - context), min(len(data), end + context)
        # Spleeter rounds its output down to an STFT hop. Tail padding keeps every
        # original sample available, including the final partial hop of the window.
        padded = np.pad(data[left:right], ((0, 2048), (0, 0)))
        output = engine.process(sample_rate=rate, samples=np.ascontiguousarray(padded.T))
        vocals = np.asarray(output.stems[0].data).T
        if output.sample_rate != rate or len(vocals) < end - left:
            raise ValueError("Unexpected separation timeline.")
        result[start:end] = vocals[start - left : end - left]
    return result


def analyze(path: Path, clean: bool, speakers: int) -> dict:
    data, rate = read_audio(path)
    if clean:
        data = separate(data, rate)
    write_audio(path.parent / "dialogue.wav", data, rate)
    mono = data.mean(axis=1)
    mono = np.interp(np.arange(0, len(mono), rate / 16000), np.arange(len(mono)), mono).astype(np.float32)
    config = sherpa.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(MODELS / "segmentation.onnx")),
            num_threads=2,
            provider="cpu",
        ),
        embedding=sherpa.SpeakerEmbeddingExtractorConfig(
            model=str(MODELS / "embedding.onnx"), num_threads=2, provider="cpu"
        ),
        clustering=sherpa.FastClusteringConfig(num_clusters=speakers if speakers else -1, threshold=0.5),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise ValueError("Speaker models are unavailable.")
    engine = sherpa.OfflineSpeakerDiarization(config)
    turns = engine.process(mono).sort_by_start_time()
    duration = len(data) / rate
    segments = [
        {
            "start": round(max(0.0, float(t.start)), 3),
            "end": round(min(duration, float(t.end)), 3),
            "speaker": int(t.speaker),
        }
        for t in turns
        if t.end > t.start
    ]
    for item in segments:
        item["overlap"] = any(
            other["speaker"] != item["speaker"] and other["start"] < item["end"] and other["end"] > item["start"]
            for other in segments
        )
    return {"duration": duration, "segments": segments}


def main() -> None:
    request = json.loads(sys.stdin.readline(8192))
    result = analyze(Path(request["path"]), bool(request["separate"]), int(request["speakers"]))
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
