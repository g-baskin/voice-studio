"""Shark engine: script planning, honest direction readouts, chunking, and the perform/revise API."""

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from naturalvoice import server, shark, shark_api
from naturalvoice import studio as st

CLONE_TAGS = ["laugh", "sigh", "gasp", "chuckle"]


def plan(script, **kw):
    return shark.plan(script, clone_tags=CLONE_TAGS, **kw)


def test_speaker_turns_and_cast():
    chunks = plan("Ana: Hello there.\nBen: Hi, Ana.\nAna: Shall we?", cast={"ana": "bf_emma"})
    assert [(c.speaker, c.voice) for c in chunks] == [("Ana", "bf_emma"), ("Ben", "am_michael"), ("Ana", "bf_emma")]
    assert [c.pause_after for c in chunks] == [shark.TURN_GAP, shark.TURN_GAP, 0.0]


def test_leading_direction_is_not_a_speaker():
    (chunk,) = plan("[whisper] Come closer.")
    assert chunk.speaker == "" and chunk.text == "Come closer."
    assert chunk.line["volume"] < 0 and chunk.line["speed"] < 1
    assert chunk.readout[0]["tag"] == "whisper" and chunk.readout[0]["status"] == "approximated"


def test_direction_lasts_until_the_next_one():
    chunks = plan("Plain start. [excited] Big news! [calm] Breathe.")
    assert [c.text for c in chunks] == ["Plain start.", "Big news!", "Breathe."]
    assert [c.line["delivery"] for c in chunks] == ["neutral", "excited", "calm"]
    assert chunks[0].readout == [] and chunks[1].readout[0]["status"] == "applied"


def test_unknown_and_clone_only_tags_are_removed_and_reported_for_stock_voices():
    (chunk,) = plan("Hello [sparkle] dear [sigh] friend.")
    assert chunk.text == "Hello dear friend."
    assert {(r["tag"], r["status"]) for r in chunk.readout} == {("sparkle", "unknown"), ("sigh", "unavailable")}


def test_laugh_is_a_sound_for_clones_and_an_approximation_for_stock_voices():
    stock = plan("Hello [laugh] friend.")
    assert [c.text for c in stock] == ["Hello", "friend."]
    assert stock[1].readout[0]["tag"] == "laughing" and stock[1].readout[0]["status"] == "approximated"
    (clone,) = plan("Me: Hello [laugh] friend.", cast={"me": "clone:0123456789ab"})
    assert clone.text == "Hello [laugh] friend." and clone.readout == []


def test_clone_voices_keep_their_sound_tags_and_pauses():
    (chunk,) = plan("Me: Wait [pause 0.5s] what? [laugh] No way.", cast={"me": "clone:0123456789ab"})
    assert "[pause 0.5s]" in chunk.text and "[laugh]" in chunk.text


def test_chunks_prefer_sentences_and_never_split_a_cue():
    text = " ".join(f"Sentence number {i} has a few words in it." for i in range(30))
    pieces = shark.chunk_text(text + " [pause 1.5s] The end.", limit=120)
    assert all(len(p) <= 120 for p in pieces)
    assert all(p.rstrip().endswith((".", "]")) for p in pieces[:-1])
    assert any("[pause 1.5s]" in p for p in pieces)
    assert " ".join(pieces).split() == (text + " [pause 1.5s] The end.").split()


def test_long_sentence_splits_at_clauses_then_words():
    sentence = "one, two, three, " * 30 + "end."
    pieces = shark.chunk_text(sentence, limit=50)
    assert all(len(p) <= 50 for p in pieces) and " ".join(pieces).split() == sentence.split()
    assert shark.chunk_text("Price is 3.14 dollars. " * 20, limit=60)[0].count("3.14") >= 1


def test_leading_unknown_tag_is_reported_not_a_speaker():
    (chunk,) = plan("[sparkle] Hi there.")
    assert chunk.speaker == "" and chunk.text == "Hi there."
    assert chunk.readout == [{"tag": "sparkle", "status": "unknown", "how": "not a direction Shark knows; removed"}]


def test_plan_limits():
    with pytest.raises(shark.SharkError):
        plan("   \n  ")
    with pytest.raises(shark.SharkError, match="only tags"):
        plan("Ana: [whisper] [sparkle]")
    with pytest.raises(shark.SharkError):
        plan("x" * (shark.MAX_CHARS + 1))
    with pytest.raises(shark.SharkError):
        plan("Hi.", voice="../etc")


def test_revise_maps_a_note_to_controls():
    (chunk,) = plan("Hello.")
    line, understood, _ = shark.revise(chunk, "gentler and a bit sadder", CLONE_TAGS)
    assert understood and line["volume"] < 0 and line["speed"] < 1


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(shark_api, "WORK", tmp_path)
    monkeypatch.setattr(st, "clone_emotion_tags", lambda: CLONE_TAGS)
    calls = []

    def fake_render(line, dictionary=None, polish=False):
        calls.append(line)
        if "FAIL" in line["text"]:
            raise st.StudioError("This line has no words to speak.")
        seconds = 0.2 + 0.05 * line.get("take", 0)
        return np.full(int(seconds * st.SR), 0.1 * line["speed"], np.float32), []

    monkeypatch.setattr(st, "render_line", fake_render)
    monkeypatch.setattr(shark_api, "jobs", {})
    client = TestClient(server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    return client, calls


def finish(client, job):
    for _ in range(200):
        state = client.get(f"/api/shark/jobs/{job}").json()
        if state["status"] != "running":
            return state
        time.sleep(0.02)
    raise AssertionError("performance did not finish")


def test_perform_streams_chunks_then_revises_and_assembles(api):
    client, calls = api
    r = client.post("/api/shark/perform", json={"script": "Ana: Hello. [sad] I missed you.\nBen: FAIL here."})
    assert r.status_code == 200
    state = finish(client, r.json()["job"])
    job = state["job"]
    assert [c["state"] for c in state["chunks"]] == ["ready", "ready", "error"]
    assert state["chunks"][2]["error"] == "This line has no words to speak."
    first = client.get(f"/api/shark/jobs/{job}/chunks/0/0.wav")
    assert first.status_code == 200 and first.content[:4] == b"RIFF"

    revised = client.post(f"/api/shark/jobs/{job}/chunks/1/revise", json={"instruction": "much slower"})
    assert revised.status_code == 200 and revised.json()["understood"]
    assert revised.json()["chunk"]["selected"] == 1 and calls[-1]["speed"] < calls[1]["speed"]
    retake = client.post(f"/api/shark/jobs/{job}/chunks/1/revise", json={"retake": True}).json()
    assert retake["version"]["take"] == 1 and retake["chunk"]["selected"] == 2
    assert client.post(f"/api/shark/jobs/{job}/chunks/1/select", json={"version": 0}).json()["selected"] == 0

    mix = client.get(f"/api/shark/jobs/{job}/performance.wav")
    assert mix.status_code == 200 and mix.content[:4] == b"RIFF"
    assert len(mix.content) > len(first.content)


def test_api_rejects_bad_input_and_unknown_jobs(api):
    client, _ = api
    assert client.post("/api/shark/plan", json={"script": "Hi", "voice": "../x"}).status_code == 422
    assert client.post("/api/shark/plan", json={"script": "Hi", "cast": {"a": "nope"}}).status_code == 422
    assert client.post("/api/shark/plan", json={"script": "Hi", "extra": 1}).status_code == 422
    assert client.get("/api/shark/jobs/" + "0" * 32).status_code == 404
    assert client.get("/api/shark/jobs/" + "g" * 32).status_code == 404
    plan_view = client.post("/api/shark/plan", json={"script": "[whisper] Hi."}).json()
    assert plan_view["chunks"][0]["readout"][0]["tag"] == "whisper"


def test_revise_needs_a_recognised_note(api):
    client, _ = api
    job = finish(client, client.post("/api/shark/perform", json={"script": "Hello."}).json()["job"])["job"]
    assert client.post(f"/api/shark/jobs/{job}/chunks/0/revise", json={}).status_code == 400
    assert client.post(f"/api/shark/jobs/{job}/chunks/0/revise", json={"instruction": "zebra"}).status_code == 400
    assert client.post(f"/api/shark/jobs/{job}/chunks/9/revise", json={"retake": True}).status_code == 404


def test_perform_respects_the_shared_render_slot(api):
    client, _ = api
    assert server.processing.acquire(blocking=False)
    try:
        assert client.post("/api/shark/perform", json={"script": "Hello."}).status_code == 429
    finally:
        server.processing.release()


def test_version_cap_holds_even_when_the_unlocked_check_is_passed(api, monkeypatch):
    client, _ = api
    job = finish(client, client.post("/api/shark/perform", json={"script": "Hello."}).json()["job"])["job"]
    for _ in range(shark_api.MAX_VERSIONS - 2):
        assert client.post(f"/api/shark/jobs/{job}/chunks/0/revise", json={"retake": True}).status_code == 200
    entry = shark_api.jobs[job]["chunks"][0]
    assert len(entry["versions"]) == shark_api.MAX_VERSIONS - 1  # one slot left, so the early check passes
    # A racing revision fills that last slot after the early check but before this one takes the lock.
    monkeypatch.setattr(shark_api, "_render_version", _capped(shark_api._render_version, entry))
    r = client.post(f"/api/shark/jobs/{job}/chunks/0/revise", json={"retake": True})
    assert r.status_code == 409 and "versions" in r.json()["detail"]
    assert len(entry["versions"]) == shark_api.MAX_VERSIONS


def _capped(render_version, entry):
    def wrapped(*args):
        entry["versions"].append({"version": len(entry["versions"]), "take": 99, "note": "race", "seconds": 0.1})
        entry["lines"].append(entry["lines"][-1])
        return render_version(*args)

    return wrapped


def test_revision_of_a_pruned_job_is_a_404(api, monkeypatch):
    client, _ = api
    job = finish(client, client.post("/api/shark/perform", json={"script": "Hello."}).json()["job"])["job"]
    real = shark_api._busy

    def busy_then_prune():
        shark_api.jobs.pop(job)  # another performance pruned it while this revision waited
        return real()

    monkeypatch.setattr(shark_api, "_busy", busy_then_prune)
    r = client.post(f"/api/shark/jobs/{job}/chunks/0/revise", json={"retake": True})
    assert r.status_code == 404 and job not in r.json()["detail"]


def test_repeated_tags_each_get_a_readout_entry():
    (chunk,) = plan("Hello [sparkle] there [sparkle] friend.")
    assert chunk.text == "Hello there friend."
    assert [r["tag"] for r in chunk.readout] == ["sparkle", "sparkle"]
