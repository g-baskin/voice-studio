"""Sample collection persistence, permission boundaries and reference version regressions."""

import io
import json
import os
import subprocess
import threading

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from naturalvoice import sample_library as lib, sample_library_api as api, voices
from naturalvoice.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(voices, "DATA_DIR", tmp_path)
    monkeypatch.setattr(voices, "VOICE_DIR", tmp_path / "voices")
    monkeypatch.setattr(lib, "installed", lambda: True)
    monkeypatch.setattr(api, "launch", lambda key: api.processing().release())
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))


def audio(seconds=8):
    rate = 44100
    t = np.arange(int(rate * seconds)) / rate
    x = (0.2 * np.sin(t * 2 * np.pi * 160)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, np.column_stack([x, x]), rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def imported(client):
    result = client.post("/api/samples/sources", data={"consent": "true"}, files={"file": ("test.wav", audio())})
    assert result.status_code == 202, result.text
    key = result.json()["id"]
    folder = lib.location("sources", key)
    for name in ("original.wav", "dialogue.wav"):
        (folder / name).write_bytes(audio())
    record = lib.read("sources", key)
    record.update(status="done", duration=8, segments=[{"start": 0, "end": 8, "speaker": 0, "overlap": False}])
    lib.atomic_json(folder / "record.json", record)
    return key


def person(client, name="Test speaker"):
    result = client.post("/api/samples/people", json={"name": name, "consent": True})
    assert result.status_code == 201, result.text
    return result.json()["id"]


def sample(client, who, source, start=0, end=6, **kwargs):
    return client.post(
        f"/api/samples/people/{who}/samples",
        json={
            "source": source,
            "start": start,
            "end": end,
            "consent": True,
            **kwargs,
        },
    )


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "https://example.com"},
        {"host": "hostile.example"},
        {"sec-fetch-site": "cross-site"},
    ],
)
def test_browser_boundary(client, headers):
    assert client.get("/api/samples", headers=headers).status_code == 403


def test_same_origin(client):
    assert client.get("/api/samples", headers={"origin": "http://127.0.0.1"}).status_code == 200


def test_remote_peer_cannot_claim_local_host(client):
    remote = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.20", 50000))
    assert remote.get("/api/samples").status_code == 403
    assert remote.post("/api/samples/people", json={"name": "Not local", "consent": True}).status_code == 403


@pytest.mark.parametrize(
    "url",
    [
        "http://youtube.com/watch?v=abcdefghijk",
        "https://127.0.0.1/video",
        "file:///tmp/video",
        "https://youtube.com.evil.test/watch?v=abcdefghijk",
        "https://user@youtube.com/watch?v=abcdefghijk",
        "https://youtube.com:9000/watch?v=abcdefghijk",
        "https://youtube.com/playlist?list=x",
        "https://youtu.be/../../private",
        "https://youtube.com/watch?v=x",
    ],
)
def test_url_restriction(url):
    with pytest.raises(ValueError):
        lib.youtube_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://youtu.be/abcdefghijk?t=1",
        "https://www.youtube.com/watch?v=abcdefghijk&list=anything",
        "https://youtube.com/shorts/abcdefghijk",
    ],
)
def test_canonical_video_only(url):
    assert lib.youtube_url(url) == "https://www.youtube.com/watch?v=abcdefghijk"


def test_consent_name_and_upload_validation(client, monkeypatch):
    assert client.post("/api/samples/people", json={"name": "Speaker"}).status_code == 400
    assert client.post("/api/samples/people", json={"name": " ", "consent": True}).status_code == 400
    assert client.post("/api/samples/sources", files={"file": ("x.wav", audio())}).status_code == 400
    for name, content in (("x.exe", b"a"), ("x.wav", b"")):
        assert (
            client.post("/api/samples/sources", data={"consent": True}, files={"file": (name, content)}).status_code
            == 400
        )
    monkeypatch.setattr(lib, "MAX_BYTES", 10)
    assert (
        client.post("/api/samples/sources", data={"consent": True}, files={"file": ("x.wav", audio())}).status_code
        == 413
    )
    assert api.processing().acquire(blocking=False)
    api.processing().release()
    assert list((lib.root() / "sources").glob("*/record.json")) == []


def test_upload_rejected_before_multipart_spooling(client, monkeypatch):
    monkeypatch.setattr(lib, "MAX_BYTES", 10)
    response = client.post("/api/samples/sources", content=b"", headers={"content-length": "1000000"})
    assert response.status_code == 413
    body = b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="x.wav"\r\n\r\n' + b"x" * 70000
    response = client.post(
        "/api/samples/sources",
        content=iter([body]),
        headers={"content-type": "multipart/form-data; boundary=boundary"},
    )
    assert response.status_code == 413
    assert not lib.root().exists()


def test_time_and_engine_validation(client, monkeypatch):
    for data in ({"start": "nan"}, {"seconds": "inf"}, {"seconds": "121"}, {"speakers": "17"}):
        result = client.post("/api/samples/sources", data={"consent": True, **data}, files={"file": ("x.wav", audio())})
        assert result.status_code == 400
    monkeypatch.setattr(lib, "installed", lambda: False)
    assert (
        client.post("/api/samples/sources", data={"consent": True}, files={"file": ("x.wav", audio())}).status_code
        == 503
    )


def test_processing_lock_and_quota(client, monkeypatch):
    assert api.processing().acquire(blocking=False)
    try:
        assert (
            client.post("/api/samples/sources", data={"consent": True}, files={"file": ("x.wav", audio())}).status_code
            == 429
        )
    finally:
        api.processing().release()
    monkeypatch.setattr(lib, "QUOTA", 10)
    assert (
        client.post("/api/samples/sources", data={"consent": True}, files={"file": ("x.wav", audio())}).status_code
        == 400
    )


def test_add_sources_build_versions_and_rollback(client):
    who = person(client)
    first, second = imported(client), imported(client)
    original = (lib.location("sources", first) / "original.wav").read_bytes()
    a = sample(client, who, first, 0, 6).json()
    b = sample(client, who, second, 1, 7).json()
    one = client.post(f"/api/samples/people/{who}/versions", json={"samples": [a["id"]]})
    assert one.status_code == 201, one.text
    before = voices.reference_audio(one.json()["id"]).read_bytes()
    two = client.post(f"/api/samples/people/{who}/versions", json={"samples": [a["id"], b["id"]]})
    assert two.status_code == 201, two.text
    assert two.json()["meta"]["reference_version"] == 2
    assert sf.info(voices.reference_audio(two.json()["id"])).duration == pytest.approx(12)
    for version in (two.json(), one.json()):
        result = client.post(f"/api/samples/people/{who}/active", json={"voice": version["id"]})
        assert result.status_code == 200
        assert client.get(f"/api/samples/people/{who}").json()["active"] == version["id"]
    assert voices.reference_audio(one.json()["id"]).read_bytes() == before
    assert (lib.location("sources", first) / "original.wav").read_bytes() == original
    assert len(client.get(f"/api/samples/people/{who}").json()["samples"]) == 2
    assert client.get(f"/api/samples/audio/{a['id']}").status_code == 200
    assert client.get(f"/api/samples/sources/{first}/audio/original").status_code == 200
    assert client.get(f"/api/samples/sources/{first}/audio/input").status_code == 404


def test_cross_person_and_length_boundaries(client):
    a, b = person(client, "A"), person(client, "B")
    source = imported(client)
    selection = sample(client, a, source).json()["id"]
    assert client.post(f"/api/samples/people/{b}/versions", json={"samples": [selection]}).status_code == 400
    assert client.post(f"/api/samples/people/{a}/versions", json={"samples": [selection, selection]}).status_code == 400
    short = sample(client, a, source, 0, 1).json()["id"]
    assert client.post(f"/api/samples/people/{a}/versions", json={"samples": [short]}).status_code == 400
    version = client.post(f"/api/samples/people/{a}/versions", json={"samples": [selection]}).json()
    assert client.post(f"/api/samples/people/{b}/active", json={"voice": version["id"]}).status_code == 400
    assert sample(client, a, source, 7, 9).status_code == 400
    assert sample(client, a, source, consent=False).status_code == 400
    assert sample(client, a, source, 0, 0.2).status_code == 400


def test_overlap_and_silence_rejected(client):
    who, source = person(client), imported(client)
    record = lib.read("sources", source)
    record["segments"][0]["overlap"] = True
    record["segments"].append({"start": 0, "end": 8, "speaker": 1, "overlap": True})
    lib.atomic_json(lib.location("sources", source) / "record.json", record)
    assert sample(client, who, source).status_code == 400
    record["segments"][0]["overlap"] = False
    record["segments"].pop()
    lib.atomic_json(lib.location("sources", source) / "record.json", record)
    sf.write(lib.location("sources", source) / "dialogue.wav", np.zeros((44100 * 8, 2)), 44100)
    assert sample(client, who, source).status_code == 400


def test_partial_overlap_preserves_solo_selection(client):
    who, source = person(client), imported(client)
    record = lib.read("sources", source)
    record["segments"] = [
        {"start": 0, "end": 8, "speaker": 0, "overlap": True},
        {"start": 6, "end": 8, "speaker": 1, "overlap": True},
    ]
    lib.atomic_json(lib.location("sources", source) / "record.json", record)
    assert sample(client, who, source, 0, 6).status_code == 201
    assert sample(client, who, source, 5, 7).status_code == 400


def test_interrupted_source_and_retry(client):
    key = imported(client)
    record = lib.read("sources", key)
    record.update(status="running", pid=os.getpid() + 100000)
    lib.atomic_json(lib.location("sources", key) / "record.json", record)
    assert client.get(f"/api/samples/sources/{key}").json()["status"] == "error"
    assert client.post(f"/api/samples/sources/{key}/retry").status_code == 202
    result = client.get(f"/api/samples/sources/{key}").json()
    assert result["status"] == "running"
    assert "pid" not in result and "input" not in result


def test_failed_analysis_keeps_source(client, monkeypatch):
    key = imported(client)
    original = lib.location("sources", key) / "input.wav"
    content = original.read_bytes()

    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("private/path", 1)

    monkeypatch.setattr(lib, "decode", fail)
    lib.process_source(key)
    record = lib.read("sources", key)
    assert record["status"] == "error" and "private/path" not in record["error"]
    assert original.read_bytes() == content


def test_decode_rejects_disguised_playlist(tmp_path):
    target = tmp_path / "private.wav"
    target.write_bytes(audio())
    disguised = tmp_path / "upload.mp4"
    disguised.write_text(f"ffconcat version 1.0\nfile '{target}'\n")
    with pytest.raises(subprocess.CalledProcessError):
        lib.decode(disguised, tmp_path / "decoded.wav", 0, 5)
    assert not (tmp_path / "decoded.wav").exists()


def test_atomic_publication_preserves_previous_on_failure(client, monkeypatch):
    who = person(client)
    path = lib.location("people", who) / "record.json"
    before = path.read_bytes()

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(lib.os, "replace", fail)
    with pytest.raises(OSError):
        lib.atomic_json(path, {"name": "changed"})
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".pending-*"))


def test_concurrent_version_numbers(client):
    who, source = person(client), imported(client)
    key = sample(client, who, source).json()["id"]
    results = []

    def build():
        results.append(lib.build_version(who, [key]))

    threads = [threading.Thread(target=build) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(v["meta"]["reference_version"] for v in results) == [1, 2]


def test_identifiers(client):
    assert client.get("/api/samples/people/not-an-id").status_code == 400
    assert client.get("/api/samples/people/" + "0" * 32).status_code == 404
    with pytest.raises(ValueError):
        lib.location("sources", "../outside")


def test_decode_real_ffmpeg(client, tmp_path):
    src, dst = tmp_path / "input.wav", tmp_path / "window.wav"
    src.write_bytes(audio())
    lib.decode(src, dst, 1, 5)
    assert sf.info(dst).duration == pytest.approx(5)
    assert sf.info(dst).channels == 2


def test_process_worker_result(client, monkeypatch):
    key = imported(client)
    monkeypatch.setattr(lib, "decode", lambda *args: None)
    result = {"duration": 8, "segments": [{"start": 0, "end": 8, "speaker": 0, "overlap": False}]}
    monkeypatch.setattr(
        lib.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, json.dumps(result))
    )
    lib.process_source(key)
    assert lib.read("sources", key)["status"] == "done"
