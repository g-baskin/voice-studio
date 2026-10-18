"""Voice cloning: API validation (fast) and one real render (slow, needs the engine installed)."""
import io
import time

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from naturalvoice import clone, voices
from naturalvoice.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def tmp_library(tmp_path, monkeypatch):
    monkeypatch.setattr(voices, "DATA_DIR", tmp_path)
    monkeypatch.setattr(voices, "VOICE_DIR", tmp_path / "voices")
    return tmp_path


def wav_bytes(seconds: float, sr: int = 16000) -> bytes:
    """Speech-like test signal: voiced bursts with pauses (not just a sine)."""
    t = np.arange(int(seconds * sr)) / sr
    env = (np.sin(2 * np.pi * 2.5 * t) > -0.3).astype(np.float32)
    x = 0.3 * env * (np.sin(2 * np.pi * 140 * t) + 0.5 * np.sin(2 * np.pi * 280 * t))
    buf = io.BytesIO()
    sf.write(buf, x.astype(np.float32), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def post(data=None, content=None, fname="ref.wav"):
    data = {"name": "Me", "consent": "true", **(data or {})}
    content = wav_bytes(8) if content is None else content
    return client.post("/api/clone/voices", data=data, files={"file": (fname, content, "audio/wav")})


def test_status_shape():
    s = client.get("/api/clone/status").json()
    assert s["license"] == "MIT" and s["sample_rate"] == 24000 and s["device"] == "cpu"
    assert isinstance(s["installed"], bool)


def test_consent_required():
    for c in ("", "false", "no"):
        r = post({"consent": c})
        assert r.status_code == 400 and "permission" in r.json()["detail"]


def test_name_required():
    assert post({"name": "  "}).status_code == 400
    assert post({"name": "x" * 61}).status_code == 400


def test_type_allowlist():
    r = post(fname="ref.exe")
    assert r.status_code == 400 and "Unsupported" in r.json()["detail"]


def test_empty_and_garbage():
    assert post(content=b"").status_code == 400
    r = post(content=b"not audio at all" * 100)
    assert r.status_code == 400 and "/" not in r.json()["detail"].replace("WAV, MP3", "")


def test_too_large(monkeypatch):
    from naturalvoice import clone_api

    monkeypatch.setattr(clone_api, "MAX_BYTES", 1000)
    assert post().status_code == 413


def test_duration_limits():
    assert "5 to 60" in post(content=wav_bytes(3)).json()["detail"]
    assert post(content=wav_bytes(61)).status_code == 400


def test_create_and_preview_validation(tmp_library):
    r = post({"transcript": "hello"})
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["id"].startswith("clone:") and rec["kind"] == "clone"
    assert rec["meta"]["consent"] is True and rec["meta"]["transcript"] == "hello"
    ref = voices.reference_audio(rec["id"])
    info = sf.info(str(ref))
    assert ref.parent == tmp_library / "voices" and info.samplerate == 24000 and info.channels == 1
    assert str(tmp_library) not in r.text  # no path leaks
    p = lambda **d: client.post("/api/clone/preview", data={"voice": rec["id"], "text": "Hi.", **d})
    assert p(text="").status_code == 400
    assert p(text="a" * 501).status_code == 400
    assert p(speed="9").status_code == 400
    assert p(voice="af_heart").status_code == 400
    assert p(voice="clone:000000000000").status_code == 404
    assert p(voice="clone:../../etc").status_code == 400
    assert client.get("/api/clone/preview/" + "0" * 32).status_code == 404
    assert client.get("/api/clone/preview/nope/audio").status_code == 404


def test_preview_busy(monkeypatch):
    from naturalvoice import server

    rec = post().json()
    monkeypatch.setattr(clone, "installed", lambda: True)
    assert server.processing.acquire(blocking=False)
    try:
        r = client.post("/api/clone/preview", data={"voice": rec["id"], "text": "Hi."})
        assert r.status_code == 429
    finally:
        server.processing.release()


def test_split_sentences():
    parts = clone.split_sentences("Hi. This is a longer second sentence here.\n\nNew paragraph?")
    assert [p for p, _ in parts][-1].endswith("?") and parts[-2][1] == 0.75


@pytest.mark.slow
@pytest.mark.skipif(not clone.installed(), reason="cloning engine not installed (scripts/setup_clone_engine.sh)")
def test_real_render_via_api():
    """SLOW (~1 min on a 4-core Intel CPU): clone a Kokoro voice and preview one short sentence."""
    from naturalvoice import tts

    a, sr = tts.speak_kokoro("The old lighthouse keeper climbed the stairs every evening at dusk. "
                             "He polished the great lens and watched the ships drift past the point.", "am_michael")
    buf = io.BytesIO()
    sf.write(buf, a, sr, format="WAV")
    rec = post(content=buf.getvalue()).json()
    job = client.post("/api/clone/preview", data={"voice": rec["id"], "text": "Nice to meet you."}).json()["job"]
    for _ in range(170):
        s = client.get(f"/api/clone/preview/{job}").json()
        if s["status"] != "running":
            break
        time.sleep(1)
    assert s["status"] == "done", s
    out, osr = sf.read(io.BytesIO(client.get(f"/api/clone/preview/{job}/audio").content), dtype="float32")
    assert osr == 24000 and 0.5 < len(out) / osr < 6 and np.sqrt(np.mean(out ** 2)) > 0.01


# --------------------------------------------------------------------------- voice changer

def conv(voice, data=None, content=None, fname="perf.wav"):
    data = {"voice": voice, "consent": "true", **(data or {})}
    content = wav_bytes(3) if content is None else content
    return client.post("/api/clone/convert", data=data, files={"file": (fname, content, "audio/wav")})


def test_convert_validation(monkeypatch):
    from naturalvoice import clone_api

    vid = post().json()["id"]
    monkeypatch.setattr(clone, "installed", lambda: True)
    r = conv(vid, {"consent": ""})
    assert r.status_code == 400 and "rights" in r.json()["detail"]
    assert conv(vid, fname="perf.txt").status_code == 400
    assert conv("af_heart").status_code == 400
    assert conv("clone:000000000000").status_code == 404
    assert conv(vid, content=b"").status_code == 400
    assert "1 to 60" in conv(vid, content=wav_bytes(0.5)).json()["detail"]
    assert conv(vid, content=wav_bytes(61)).status_code == 400
    monkeypatch.setattr(clone_api, "MAX_BYTES", 1000)
    assert conv(vid).status_code == 413
    assert client.get("/api/clone/convert/" + "0" * 32).status_code == 404


def test_convert_busy(monkeypatch):
    from naturalvoice import server

    vid = post().json()["id"]
    monkeypatch.setattr(clone, "installed", lambda: True)
    assert server.processing.acquire(blocking=False)
    try:
        assert conv(vid).status_code == 429
    finally:
        server.processing.release()


def test_cut_points():
    x = np.ones(int(50 * 24000), dtype=np.float32)
    x[int(8 * 24000):int(8.1 * 24000)] = 0
    cuts = clone._cut_points(x, 24000)
    assert cuts[0] == 0 and cuts[-1] == len(x) and all(b - a <= 20 * 24000 for a, b in zip(cuts, cuts[1:]))
    assert all(b - a <= 10 * 24000 for a, b in zip(cuts, cuts[1:]))


@pytest.mark.slow
@pytest.mark.skipif(not clone.installed(), reason="cloning engine not installed (scripts/setup_clone_engine.sh)")
def test_real_conversion_via_api():
    """SLOW (~30 s): re-voice a short af_heart performance in an am_michael clone."""
    from naturalvoice import tts

    def wavb(text, voice):
        a, sr = tts.speak_kokoro(text, voice)
        buf = io.BytesIO()
        sf.write(buf, a, sr, format="WAV")
        return buf.getvalue(), len(a) / sr
    ref, _ = wavb("The old lighthouse keeper climbed the stairs every evening at dusk. "
                  "He polished the great lens and watched the ships drift past the point.", "am_michael")
    vid = post(content=ref).json()["id"]
    perf, secs = wavb("Wow, we actually did it!", "af_heart")
    job = conv(vid, content=perf).json()["job"]
    for _ in range(170):
        s = client.get(f"/api/clone/convert/{job}").json()
        if s["status"] != "running":
            break
        time.sleep(1)
    assert s["status"] == "done", s
    out, osr = sf.read(io.BytesIO(client.get(f"/api/clone/convert/{job}/audio").content), dtype="float32")
    assert osr == 24000 and abs(len(out) / osr - secs) < 1.0 and np.sqrt(np.mean(out ** 2)) > 0.01


def test_crossfade_has_no_click():
    sr = 24000
    t = np.arange(sr) / sr
    a = 0.5 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
    b = 0.5 * np.sin(2 * np.pi * 220 * t + 2.0).astype(np.float32)  # phase jump if simply butted
    inner = np.max(np.abs(np.diff(a)))
    naive = np.concatenate([a, b])
    assert np.abs(np.diff(naive))[len(a) - 1] > 3 * inner  # the test signal really would click
    n = int(0.04 * sr)
    j = clone.crossfade(a, b, n)
    assert len(j) == 2 * sr - n
    # equal-power gain can lift correlated signals by up to sqrt(2) mid-fade: a smooth bump, never a step
    assert np.max(np.abs(np.diff(j))) <= inner * np.sqrt(2) * 1.01


def test_fade_into_pause_has_no_click():
    sr = 24000
    x = np.full(sr // 2, 0.6, dtype=np.float32)  # worst case: clip ends at a high level
    j = np.concatenate([clone.fade(x, sr), np.zeros(sr // 4, np.float32), clone.fade(x, sr)])
    assert np.max(np.abs(np.diff(j))) < 0.6 / 50


# --------------------------------------------------------------------------- emotion tags

def test_emotion_tags_exported():
    assert clone.EMOTION_TAGS == ["[clear throat]", "[sigh]", "[shush]", "[cough]", "[groan]", "[sniff]",
                                  "[gasp]", "[chuckle]", "[laugh]"]
    assert client.get("/api/clone/status").json()["emotion_tags"] == clone.EMOTION_TAGS


def test_clean_tags():
    text, removed = clone.clean_tags("That is [LAUGH] funny [bogus] ok [Clear  Throat]. [x] [] end")
    assert text == "That is [laugh] funny ok [clear throat]. end"
    assert removed == ["[bogus]", "[x]", "[]"]
    assert clone.clean_tags("No tags here.") == ("No tags here.", [])


def test_tags_stay_with_their_sentence():
    parts = [p for p, _ in clone.split_sentences("Hi there my friend. [sigh]\n\nWow. [laugh] That was great, honestly.")]
    assert parts == ["Hi there my friend. [sigh]", "Wow. [laugh] That was great, honestly."]
    long = "It was " + "very " * 50 + "long [clear throat] and done."
    joined = " ".join(p for p, _ in clone.split_sentences(long))
    assert "[clear throat]" in joined and all(p.count("[") == p.count("]") for p, _ in clone.split_sentences(long))


def test_preview_strips_unknown_tags(monkeypatch):
    rec = post().json()
    monkeypatch.setattr(clone, "installed", lambda: True)
    seen = {}

    def fake_speak(text, voice, speed=1.0, progress=None):
        seen["text"] = text
        return np.full(2400, 0.1, dtype=np.float32), 24000
    monkeypatch.setattr(clone, "speak", fake_speak)
    r = client.post("/api/clone/preview", data={"voice": rec["id"], "text": "Ha [laugh] ok [evil cackle] go."})
    assert r.status_code == 202 and "[evil cackle]" in r.json()["warning"]
    job = r.json()["job"]
    for _ in range(50):
        s = client.get(f"/api/clone/preview/{job}").json()
        if s["status"] != "running":
            break
        time.sleep(0.05)
    assert s["status"] == "done" and "[evil cackle]" in s["warning"]
    assert seen["text"] == "Ha [laugh] ok go."
    only_bad = client.post("/api/clone/preview", data={"voice": rec["id"], "text": "[bogus]"})
    assert only_bad.status_code == 400


@pytest.mark.slow
@pytest.mark.skipif(not clone.installed(), reason="cloning engine not installed (scripts/setup_clone_engine.sh)")
def test_real_render_with_tag(tmp_library):
    """SLOW (~40 s): a [laugh] tag adds a non-speech event, so the render is longer than without it."""
    from naturalvoice import tts

    a, sr = tts.speak_kokoro("The old lighthouse keeper climbed the stairs every evening at dusk. "
                             "He polished the great lens and watched the ships drift past the point.", "am_michael")
    buf = io.BytesIO()
    sf.write(buf, a, sr, format="WAV")
    vid = post(content=buf.getvalue()).json()["id"]
    plain, sr1 = clone.speak("That's hilarious, anyway, let's go.", vid)
    tagged, sr2 = clone.speak("That's hilarious [laugh] anyway, let's go.", vid)
    assert sr1 == sr2 == 24000 and np.sqrt(np.mean(tagged ** 2)) > 0.01
    assert len(tagged) > len(plain) + 0.15 * sr1


# --------------------------------------------------------------------------- other languages

def test_languages_in_status_and_validation(monkeypatch):
    langs = [l["code"] for l in client.get("/api/clone/status").json()["languages"]]
    assert langs[0] == "en" and {"es", "fr"} <= set(langs)
    rec = post().json()
    monkeypatch.setattr(clone, "installed", lambda: True)
    for bad in ("de", "xx", "../en"):
        r = client.post("/api/clone/preview", data={"voice": rec["id"], "text": "Hola.", "language": bad})
        assert r.status_code == 400 and "language" in r.json()["detail"]
    seen = {}
    monkeypatch.setattr(clone, "speak_language", lambda t, v, l, s=1.0, progress=None: (
        seen.update(lang=l) or (np.full(2400, 0.1, np.float32), 24000)))
    r = client.post("/api/clone/preview", data={"voice": rec["id"], "text": "Hola.", "language": "ES"})
    assert r.status_code == 202
    for _ in range(50):
        if client.get(f"/api/clone/preview/{r.json()['job']}").json()["status"] != "running":
            break
        time.sleep(0.05)
    assert seen["lang"] == "es"


def test_gender_estimate():
    sr = 24000
    t = np.arange(sr * 2) / sr
    low = 0.3 * np.sign(np.sin(2 * np.pi * 115 * t)).astype(np.float32)
    high = 0.3 * np.sign(np.sin(2 * np.pi * 210 * t)).astype(np.float32)
    assert abs(clone._median_f0(low, sr) - 115) < 5 and abs(clone._median_f0(high, sr) - 210) < 8
    with pytest.raises(ValueError):
        clone.speak_language("Hola.", "clone:000000000000", "de")


@pytest.mark.slow
@pytest.mark.skipif(not clone.installed(), reason="cloning engine not installed (scripts/setup_clone_engine.sh)")
def test_real_spanish_render():
    """SLOW (~40 s): Spanish via Kokoro + voice changer, in a male clone (picks em_alex by pitch)."""
    from naturalvoice import tts

    a, sr = tts.speak_kokoro("The old lighthouse keeper climbed the stairs every evening at dusk. "
                             "He polished the great lens and watched the ships drift past the point.", "am_michael")
    buf = io.BytesIO()
    sf.write(buf, a, sr, format="WAV")
    vid = post(content=buf.getvalue()).json()["id"]
    assert clone.clone_gender(vid) == "male"
    w, osr = clone.speak_language("Buenos días, ¿cómo estás?", vid, "es")
    assert osr == 24000 and 0.8 < len(w) / osr < 5 and np.sqrt(np.mean(w ** 2)) > 0.01
