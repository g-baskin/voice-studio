"""Real CPU inference smoke test using generated stock speech, never user recordings."""

import json
import subprocess

import numpy as np
import pytest
import soundfile as sf

from naturalvoice import sample_library as lib, tts


@pytest.mark.slow
def test_real_media_models(tmp_path):
    if not lib.installed() or not (tts.MODEL_DIR / "kokoro-v1.0.onnx").exists():
        pytest.skip("Install media and stock models for the CPU integration check.")
    segments = []
    for voice in ("af_heart", "am_michael"):
        speech, rate = tts.speak_kokoro("This is a generated recording for a local speaker detection test.", voice)
        segments.extend([speech, np.zeros(rate, dtype=np.float32)])
    signal = np.concatenate(segments)
    # Add quiet accompaniment to exercise the actual separation model, not just the worker protocol.
    signal += 0.015 * np.sin(np.arange(len(signal)) / rate * 2 * np.pi * 440)
    source = tmp_path / "input.wav"
    sf.write(source, signal, rate)
    lib.decode(source, tmp_path / "original.wav", 0, 30)
    result = subprocess.run(
        [str(lib.ENGINE / ".venv/bin/python"), str(lib.ENGINE / "worker.py")],
        input=json.dumps({"path": str(tmp_path / "original.wav"), "separate": True, "speakers": 2}),
        capture_output=True,
        text=True,
        timeout=900,
        check=True,
    )
    analysis = json.loads(result.stdout)
    assert 5 < analysis["duration"] <= 30
    assert len(analysis["segments"]) >= 2
    assert len({turn["speaker"] for turn in analysis["segments"]}) == 2
    before, sr = sf.read(tmp_path / "original.wav")
    after, out_sr = sf.read(tmp_path / "dialogue.wav")
    assert sr == out_sr == 44100
    assert before.shape == after.shape
    assert np.isfinite(after).all() and np.max(np.abs(after)) > 0.01
    assert not np.array_equal(before, after)


def load_transcriber():
    import importlib.util

    spec = importlib.util.spec_from_file_location("media_transcribe", lib.ENGINE / "transcribe.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_words_from_tokens_joins_pieces_and_punctuation():
    asr = load_transcriber()
    tokens = [",", "▁Hello", ",", "▁wor", "ld", ".", "▁Um"]
    starts = [0.0, 0.0, 0.4, 0.5, 0.7, 0.9, 1.5]
    durations = [0.04, 0.32, 0.08, 0.16, 0.16, 0.08, 0.24]
    assert asr.words_from_tokens(tokens, starts, durations, 10.0) == [
        [10.0, 10.32, "Hello,"],
        [10.5, 10.86, "world."],
        [11.5, 11.74, "Um"],
    ]


def test_words_from_tokens_without_durations_uses_next_start_capped():
    asr = load_transcriber()
    tokens = ["▁Hi", "▁there", "▁now"]
    words = asr.words_from_tokens(tokens, [0.0, 2.0, 2.4], [], 1.0, limit=2.9)
    assert words == [[1.0, 2.0, "Hi"], [3.0, 3.4, "there"], [3.4, 3.9, "now"]]


def test_quiet_cut_picks_quiet_frame_in_tail():
    asr = load_transcriber()
    rate = 16000
    noise = np.random.default_rng(1).uniform(-0.5, 0.5, 30 * rate).astype(np.float32)
    noise[27 * rate : 27 * rate + 320] = 0
    cut = asr.quiet_cut(noise, rate)
    assert 27 * rate <= cut <= 27 * rate + 320
    noise[1 * rate : 1 * rate + 320] = 0
    assert asr.quiet_cut(noise, rate) >= 25 * rate


def test_read_windows_streams_contiguous_bounded_windows(tmp_path):
    asr = load_transcriber()
    rate = 16000
    signal = np.random.default_rng(2).uniform(-0.3, 0.3, 70 * rate)
    path = tmp_path / "speech.wav"
    sf.write(path, signal, rate, subtype="PCM_16")
    windows = list(asr.read_windows(path))
    assert len(windows) == 3
    position = 0
    for offset, samples in windows:
        assert offset == position / rate
        assert len(samples) <= 30 * rate
        position += len(samples)
    assert position == len(signal)
    stereo = tmp_path / "stereo.wav"
    sf.write(stereo, np.zeros((rate, 2)), rate, subtype="PCM_16")
    with pytest.raises(ValueError):
        list(asr.read_windows(stereo))
