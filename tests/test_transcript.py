"""Transcripts: worker protocol (with a fake worker), validation, cleanup picks and hook picks."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from naturalvoice import audio as aio
from naturalvoice import editor as ed
from naturalvoice import transcript as tr
from naturalvoice import voices


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(voices, "DATA_DIR", tmp_path / "data")
    return tmp_path / "data"


def media(tmp_path: Path, seconds: float = 4.0) -> dict:
    src = tmp_path / "talk.wav"
    subprocess.run(
        [aio._ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=f=220:d={seconds}", str(src)], check=True
    )
    record, dest = ed.new_media(src.name)
    dest.write_bytes(src.read_bytes())
    record.update(status="processing", size=dest.stat().st_size)
    ed.save_media(record)
    return ed.process_media(record["id"])


def fake_worker(tmp_path: Path, monkeypatch, body: str) -> None:
    script = tmp_path / "fake_worker.py"
    script.write_text(
        "import json, sys, time, wave\n"
        "req = json.loads(sys.stdin.readline())\n"
        "with wave.open(req['path']) as w:\n"
        "    assert w.getframerate() == 16000 and w.getnchannels() == 1\n" + body,
        encoding="utf-8",
    )
    monkeypatch.setattr(tr, "installed", lambda: True)
    monkeypatch.setattr(tr, "worker_command", lambda: [sys.executable, str(script)])


GOOD = (
    "print(json.dumps({'progress': 0.5}), flush=True)\n"
    "print(json.dumps({'progress': 1.0}), flush=True)\n"
    "print(json.dumps({'duration': 4.0, 'words': [[0.1, 0.4, 'Hello'], [0.5, 0.9, 'world.']]}))\n"
)


def test_transcribe_saves_words_and_levels_and_removes_the_wav(tmp_path, monkeypatch):
    rec = media(tmp_path)
    fake_worker(tmp_path, monkeypatch, GOOD)
    seen: list[float] = []
    data = tr.transcribe(rec["id"], seen.append)
    assert data["words"] == [[0.1, 0.4, "Hello"], [0.5, 0.9, "world."]]
    assert data["model"] == tr.MODEL_ID and data["edited"] is False
    assert tr.read_transcript(rec["id"]) == data
    assert seen == sorted(seen) and seen[-1] == pytest.approx(1.0)
    folder = ed.media_dir(rec["id"])
    assert not (folder / "speech-16k.wav").exists()
    loudness, _ = tr.read_levels(rec["id"])
    assert loudness and all(isinstance(t, float) for t, _ in loudness)


@pytest.mark.parametrize(
    "body",
    [
        "print(json.dumps({'duration': 4, 'words': [[1.0, 1.2, 'b'], [0.5, 0.6, 'a']]}))\n",
        "print(json.dumps({'duration': 4, 'words': [[0.1, 0.2, 'bad\\u0007']]}))\n",
        "print(json.dumps({'duration': 4, 'words': [[0.1, 99.0, 'late']]}))\n",
        "print('not json')\n",
        "print(json.dumps([1, 2]))\n",
        "sys.exit(3)\n",
        "print(json.dumps({'progress': 0.5}))\n",
    ],
)
def test_bad_worker_output_is_refused_and_nothing_is_saved(tmp_path, monkeypatch, body):
    rec = media(tmp_path)
    fake_worker(tmp_path, monkeypatch, body)
    with pytest.raises(ed.EditorError) as caught:
        tr.transcribe(rec["id"])
    assert "Traceback" not in str(caught.value)
    assert tr.read_transcript(rec["id"]) is None
    assert not (ed.media_dir(rec["id"]) / "speech-16k.wav").exists()


def test_transcription_can_be_cancelled(tmp_path, monkeypatch):
    rec = media(tmp_path)
    fake_worker(tmp_path, monkeypatch, "print(json.dumps({'progress': 0.1}), flush=True)\ntime.sleep(30)\n")
    cancel = threading.Event()

    def progress(f: float) -> None:
        if f > 0.12:
            cancel.set()

    with pytest.raises(ed.Cancelled):
        tr.transcribe(rec["id"], progress, cancel)
    assert tr.read_transcript(rec["id"]) is None
    assert not (ed.media_dir(rec["id"]) / "speech-16k.wav").exists()


def test_missing_engine_and_edited_transcripts_are_guarded(tmp_path, monkeypatch):
    rec = media(tmp_path)
    monkeypatch.setattr(tr, "installed", lambda: False)
    with pytest.raises(tr.NotInstalled):
        tr.transcribe(rec["id"])
    saved = tr.save_transcript(rec["id"], [[0.0, 0.3, "Mine"]])
    assert saved["edited"] is True
    fake_worker(tmp_path, monkeypatch, GOOD)
    with pytest.raises(tr.EditedTranscript):
        tr.transcribe(rec["id"])
    kept = tr.read_transcript(rec["id"])
    assert kept is not None and kept["words"] == [[0.0, 0.3, "Mine"]]
    assert tr.transcribe(rec["id"], overwrite=True)["words"][0][2] == "Hello"


def test_validate_words_bounds():
    assert tr.validate_words([[0, 1, " cafe\u0301 "]], 2) == [[0.0, 1.0, "café"]]
    bad = [
        [[0, 3.0, "late"]],
        [[1, 0.5, "backwards"]],
        [[1, 1.2, "a"], [0.9, 1.0, "b"]],
        [[0, 1, ""]],
        [[0, 1, "x" * 49]],
        [[0, 1, "new\nline"]],
        [[0, 1, "\u202eevil"]],
        [[True, 1, "bool"]],
        [[float("nan"), 1, "nan"]],
        [[0, 1]],
        "words",
        [[0, 1, 5]],
    ]
    for words in bad:
        with pytest.raises(ed.EditorError):
            tr.validate_words(words, 2)
    with pytest.raises(ed.EditorError):
        tr.validate_words([[0, 0, "a"]] * (tr.MAX_WORDS + 1), 2)


def test_fillers_include_known_words_and_sounding_gaps_only():
    words = [[0.0, 0.3, "So"], [0.4, 0.6, "Um,"], [0.7, 1.0, "this"], [1.6, 1.9, "is"], [2.6, 2.9, "it."]]
    silences = [(1.0, 1.6)]  # the first long gap is silent; the second has sound
    found = tr.filler_candidates(words, silences)
    assert found == [{"kind": "word", "index": 1}, {"kind": "gap", "t0": 1.9, "t1": 2.6}]
    partly = tr.filler_candidates(words, [(2.0, 2.1)])
    assert {"kind": "gap", "t0": 2.1, "t1": 2.6} in partly and {"kind": "gap", "t0": 1.0, "t1": 1.6} in partly
    phrase = [[0, 0.2, "you"], [0.2, 0.4, "know,"], [0.4, 0.6, "I"], [0.6, 0.8, "like"], [0.8, 1.0, "it"]]
    assert tr.filler_candidates(phrase, []) == []
    assert [f["index"] for f in tr.filler_candidates(phrase, [], extra=True)] == [0, 1, 3]


def test_long_pauses_shrink_to_the_kept_gap():
    words = [[0.0, 0.5, "a"], [0.8, 1.0, "b"], [3.0, 3.2, "c"]]
    assert tr.long_pauses(words, 0.6, 0.25) == [(1.125, 2.875)]
    assert tr.long_pauses(words, 0.2, 0.0) == [(0.5, 0.8), (1.0, 3.0)]


def spoken(text: str, start: float, step: float = 0.35, gap: float = 0.05) -> list[list]:
    words, t = [], start
    for token in text.split():
        words.append([round(t, 3), round(t + step - gap, 3), token])
        t += step
    return words


def test_hooks_prefer_a_question_led_steady_passage_and_keep_sentence_bounds():
    dull = "the meeting covered the agenda items and the minutes were approved by the group. " * 6
    hook = "Why do you never finish your videos? Here are three mistakes that stop you. " * 4
    words = spoken(dull, 0.0, step=0.6) + spoken(hook, 80.0)
    words += [[w[0], w[1], w[2]] for w in spoken(dull, 120.0, step=0.6)]
    hooks = tr.hook_candidates(words, [], [], 15, 40, 3)
    assert hooks and hooks[0]["text"].startswith("Why do you never finish")
    assert "opens with a question" in hooks[0]["reasons"] and hooks[0]["score"] == 100
    starts = {w[0] for i, w in enumerate(words) if i == 0 or str(words[i - 1][2]).endswith((".", "?"))}
    ends = {w[1] for w in words if str(w[2]).endswith((".", "?"))} | {words[-1][1]}
    for h in hooks:
        assert 15 - 1e-6 <= h["end"] - h["start"] <= 40 + 1e-6
        assert h["start"] in starts and h["end"] in ends
    for a in hooks:
        for b in hooks:
            assert a is b or a["end"] <= b["start"] or b["end"] <= a["start"]
    assert [h["id"] for h in hooks] == list(range(len(hooks)))


def test_rank_with_llm_uses_only_known_ids_and_falls_back(monkeypatch):
    candidates = [{"id": i, "text": f"text {i}", "start": i, "end": i + 1} for i in range(3)]
    sent: list[str] = []

    def chat(system, user, **kw):
        sent.append(user)
        return "Best first: [2, 0, 99, true, 2]"

    monkeypatch.setattr(tr.llm, "chat", chat)
    ordered, used = tr.rank_with_llm(candidates)
    assert used and [c["id"] for c in ordered] == [2, 0, 1]
    assert json.loads(sent[0]) == [{"id": i, "text": f"text {i}"} for i in range(3)]
    monkeypatch.setattr(tr.llm, "chat", lambda *a, **k: "I like the second one")
    assert tr.rank_with_llm(candidates) == (candidates, False)
    monkeypatch.setattr(tr.llm, "chat", lambda *a, **k: "[oops")
    assert tr.rank_with_llm(candidates) == (candidates, False)


@pytest.mark.slow
def test_real_speech_model_transcribes_generated_speech(tmp_path):
    from naturalvoice import tts

    if not tr.installed() or not (tts.MODEL_DIR / "kokoro-v1.0.onnx").exists():
        pytest.skip("Run scripts/setup_speech_model.sh and download the stock models for this check.")
    import soundfile as sf

    sentence = "Most people never finish their first video, so here are three simple reasons why."
    speech, rate = tts.speak_kokoro(sentence, "af_heart")
    src = tmp_path / "speech.wav"
    sf.write(src, speech, rate)
    record, dest = ed.new_media(src.name)
    dest.write_bytes(src.read_bytes())
    record.update(status="processing", size=dest.stat().st_size)
    ed.save_media(record)
    ed.process_media(record["id"])
    data = tr.transcribe(record["id"])
    heard = [tr._norm(w[2]) for w in data["words"]]
    expected = [tr._norm(w) for w in sentence.split()]
    assert sum(w in heard for w in expected) >= 0.8 * len(expected)
    starts = [w[0] for w in data["words"]]
    assert starts == sorted(starts) and all(w[0] <= w[1] for w in data["words"])


def test_a_stalled_worker_is_stopped_at_its_deadline(tmp_path, monkeypatch):
    rec = media(tmp_path)
    fake_worker(tmp_path, monkeypatch, "time.sleep(30)\n")
    monkeypatch.setattr(tr, "worker_deadline", lambda duration: 0.5)
    started = time.monotonic()
    with pytest.raises(ed.EditorError, match="took too long"):
        tr.transcribe(rec["id"])
    assert time.monotonic() - started < 15
    assert tr.read_transcript(rec["id"]) is None
    assert not (ed.media_dir(rec["id"]) / "speech-16k.wav").exists()


def test_hook_search_has_a_work_budget_and_counts_pauses_by_overlap(monkeypatch):
    stacked = [[0.0, 0.0, "Hi."] for _ in range(3000)]
    monkeypatch.setattr(tr, "MAX_HOOK_STEPS", 100_000)
    with pytest.raises(ed.EditorError, match="too dense"):
        tr.hook_candidates(stacked, [], [], 15, 90, 5)

    text = "You can do this today. Then rest and try again. " * 4
    words = spoken(text, 0.0) + spoken(text, 40.0)
    overlapping = tr.hook_candidates(words, [], [(2.0, 4.0), (3.0, 6.0), (60.0, 60.5)], 5, 12, 4)
    merged = tr.hook_candidates(words, [], [(2.0, 6.0), (60.0, 60.5)], 5, 12, 4)
    assert overlapping == merged
    # The window over the pause scores below the same words spoken without one.
    score = {h["start"]: h["score"] for h in merged}
    assert score[0.0] < score[40.0]
