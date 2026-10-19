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
