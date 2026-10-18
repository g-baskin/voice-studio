import io
import time
import zipfile

import numpy as np
import pyloudnorm as pyln
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from naturalvoice import analyze, workflow, server, quality


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WORK", tmp_path)
    monkeypatch.setattr(server, "jobs", {})
    monkeypatch.setattr(quality, "dnsmos", lambda x, sr: {"OVRL": 3.2, "SIG": 3.3})
    # Focus API workflow tests on slicing/exporting; the real DSP has its own suite.
    monkeypatch.setattr(workflow.hz, "humanize", lambda x, sr, settings, progress: x * 0.5)
    return TestClient(server.app)


def wav(seconds=22):
    sr = 24000
    t = np.arange(int(seconds * sr)) / sr
    x = (0.15 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 0.6 * t) > -0.5)).astype(np.float32)
    out = io.BytesIO()
    sf.write(out, x, sr, format="WAV", subtype="PCM_24")
    return out.getvalue()


def submit(client, data=None, name="speech.wav", payload=None):
    return client.post(
        "/api/clean", data=data or {}, files={"file": (name, payload if payload is not None else wav(), "audio/wav")}
    )


def finish(client, job):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = client.get(f"/api/jobs/{job}").json()
        if state["status"] != "running":
            return state
        time.sleep(0.02)
    raise AssertionError("Job did not finish")


def test_preview_real_segment_and_matched_downloads(client):
    r = submit(client, {"mode": "preview", "start": 5, "seconds": 10})
    assert r.status_code == 200
    job = r.json()["job"]
    state = finish(client, job)
    assert state["status"] == "done", state
    result = state["result"]
    assert result["start"] == 5 and result["seconds"] == 10
    assert result["mode"] == "preview" and result["matching"]["matched"]
    assert "small" in " ".join(result["warnings"])
    for which in ["result", "compare-before", "compare-after"]:
        response = client.get(f"/api/jobs/{job}/{which}")
        assert response.status_code == 200
        samples, rate = sf.read(io.BytesIO(response.content))
        assert len(samples) / rate == 10
    assert client.post("/api/batch-download", json={"jobs": [job]}).status_code == 400


def test_short_preview_and_invalid_start(client):
    job = submit(client, {"mode": "preview", "seconds": 10}, payload=wav(2)).json()["job"]
    assert finish(client, job)["result"]["seconds"] == 2
    job = submit(client, {"mode": "preview", "start": 30, "seconds": 10}, payload=wav(2)).json()["job"]
    assert finish(client, job)["status"] == "error"
    # Errors release the worker slot.
    job = submit(client, {"mode": "analyze"}, payload=wav(2)).json()["job"]
    assert finish(client, job)["status"] == "done"


def test_suggestion_is_advisory_and_has_no_output(client):
    job = submit(client, {"mode": "analyze", "seconds": 10}).json()["job"]
    result = finish(client, job)["result"]
    assert result["suggestion"]["template"] in {"clean", "ad", "metallic", "echo", "noise"}
    assert result["suggestion"]["confidence"] == "low"
    assert result["suggestion"]["reason"]
    assert client.get(f"/api/jobs/{job}/result").status_code == 404
    assert client.get(f"/api/jobs/{job}/compare-before").status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        {"ai_clean": "nan"},
        {"room_tone": "2"},
        {"warmth": "-0.1"},
        {"mode": "delete"},
        {"start": "-1"},
        {"start": "nan"},
        {"seconds": "21"},
        {"seconds": "inf"},
    ],
)
def test_invalid_controls_and_sections(client, data):
    assert submit(client, data, payload=b"not audio").status_code == 400


def test_limits_empty_type_and_busy(client):
    assert submit(client, payload=b"").status_code == 400
    assert submit(client, name="speech.exe", payload=b"x").status_code == 400
    assert server.processing.acquire(blocking=False)
    try:
        assert submit(client, payload=wav(1)).status_code == 429
    finally:
        server.processing.release()
    assert client.post("/api/batch-download", json={"jobs": []}).status_code == 422
    assert client.post("/api/batch-download", json={"jobs": ["../file"]}).status_code == 400


def test_zip_completed_only_safe_unique_names(client):
    ids = []
    for _ in range(2):
        job = submit(client, name="../../same.wav", payload=wav(1)).json()["job"]
        assert finish(client, job)["status"] == "done"
        ids.append(job)
    r = client.post("/api/batch-download", json={"jobs": ids})
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        assert archive.namelist() == ["01-same.natural.wav", "02-same.natural.wav"]
        assert all(archive.read(name).startswith(b"RIFF") for name in archive.namelist())
    assert not list(server.WORK.glob("batch-*.zip")), "ZIP temporary file cleaned after download"
    assert client.post("/api/batch-download", json={"jobs": [ids[0], "f" * 32]}).status_code == 400


def test_matched_copies_match_loudness_without_clipping():
    sr = 24000
    t = np.arange(sr * 2) / sr
    x = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    a, b, meta = workflow.matched_copies(x, x * 3, sr)
    meter = pyln.Meter(sr)
    assert abs(meter.integrated_loudness(a) - meter.integrated_loudness(b)) < 0.01
    assert max(np.max(np.abs(a)), np.max(np.abs(b))) < 0.9
    assert meta["matched"]
    _, _, meta = workflow.matched_copies(x * 0, x * 0, sr)
    assert not meta["matched"]


def test_quality_warnings_and_silence():
    b = {"listener": 3.4, "voice": 3.5, "echo_db": -100}
    a = {"listener": 3.1, "voice": 3.2, "echo_db": -60}
    text = " ".join(workflow.warnings(b, a, 0.3))
    assert "Try a gentler" in text and "not necessarily echo" in text and "room tone is on" in text
    assert workflow.recommend(np.zeros(24000), 24000)["template"] == "clean"
    assert analyze.report(np.zeros(24000), 24000)["listener"] is None


def test_export_scoring_uses_saved_samples(client, monkeypatch):
    # Force clipping on export: reported results must describe the file, not the >1 internal signal.
    monkeypatch.setattr(workflow.hz, "humanize", lambda x, sr, settings, progress: x * 20)
    observed = []
    real_report = analyze.report

    def report(x, sr):
        observed.append(float(np.max(np.abs(x))))
        return real_report(x, sr)

    monkeypatch.setattr(analyze, "report", report)
    job = submit(client, payload=wav(1)).json()["job"]
    assert finish(client, job)["status"] == "done"
    assert len(observed) == 2 and observed[1] <= 1.0
