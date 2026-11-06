import json

import pytest
from fastapi.testclient import TestClient

from naturalvoice import rewrite, scriptgen as sg, server


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setattr(rewrite, "llm_available", lambda: {"available": False, "via": None})


def test_template_every_kind_and_length():
    for kind in sg.KINDS:
        s = sg.sample(kind)
        out = sg.generate(s["topic"], s["brief"], kind, "friendly", 30, ["Narrator"], s["cta"])
        assert out["engine"] == "built-in outline" and out["lines"] and out["title"]
        assert all(line["text"] and line["speaker"] for line in out["lines"])
        assert out["estimated_seconds"] <= 30 * 1.2, (kind, out["estimated_seconds"])
        assert not any(c.isdigit() for line in out["lines"] for c in line["text"])
        assert "template, not an AI" in out["notes"][0]


def test_dialogue_uses_two_speakers_and_trims_to_budget():
    out = sg.generate("an app", "one; two; three; four; five; six", "dialogue", "funny", 10, ["Ann"])
    assert {line["speaker"] for line in out["lines"]} == {"Alex", "Sam"}
    assert out["estimated_seconds"] <= 12
    long = sg.generate("X", "a thing", "ad", "calm", 120)
    assert any("Shorter than" in n for n in long["notes"])


def test_validation_and_speaker_cleaning():
    for bad in ({"kind": "poem"}, {"tone": "angry"}, {"seconds": 5}, {"seconds": 999}, {"mode": "x"}):
        with pytest.raises(ValueError):
            sg.generate("t", "b", **bad)
    out = sg.generate("t", "b", speakers=["<b>Bob</b>", "", "A" * 80])
    assert all("<" not in line["speaker"] and len(line["speaker"]) <= 30 for line in out["lines"])


def test_llm_path_parses_json_and_fixes_unknown_speakers(monkeypatch):
    monkeypatch.setattr(rewrite, "llm_available", lambda: {"available": True, "via": "test"})
    seen = {}

    def fake(system, user, temperature=0.4, timeout=90):
        seen["system"] = system
        return "Sure!\n" + json.dumps(
            {
                "title": "Cool",
                "lines": [
                    {"speaker": "Ann", "text": "We have 3 options [pause 1s] today."},
                    {"speaker": "Stranger", "text": "Great."},
                ],
            }
        )

    monkeypatch.setattr(rewrite, "chat", fake)
    out = sg.generate("t", "b", "dialogue", "friendly", 30, ["Ann", "Bo"], emotion_tags=True)
    assert out["engine"] == "language model" and out["title"] == "Cool"
    assert out["lines"][0]["text"] == "We have three options [pause 1s] today."
    assert out["lines"][1]["speaker"] == "Ann"
    assert "[chuckle]" in seen["system"] and "Ann, Bo" in seen["system"]
    monkeypatch.setattr(rewrite, "chat", lambda *a, **k: "Ann: Hello there.\nBo: Hi!")
    assert [line["speaker"] for line in sg.generate("t", "b", speakers=["Ann", "Bo"])["lines"]] == ["Ann", "Bo"]


def test_auto_falls_back_when_llm_fails_but_explicit_llm_errors(monkeypatch):
    monkeypatch.setattr(rewrite, "llm_available", lambda: {"available": True, "via": "test"})

    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(rewrite, "chat", boom)
    out = sg.generate("Tea", "hot; fresh")
    assert out["engine"] == "built-in outline" and "didn't answer" in out["notes"][0]
    with pytest.raises(RuntimeError):
        sg.generate("Tea", "hot", mode="llm")


def test_api():
    c = TestClient(server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    st = c.get("/api/scriptgen/status").json()
    assert st["llm"]["available"] is False and "ad" in st["kinds"]
    assert c.get("/api/scriptgen/sample?kind=story").json()["kind"] == "story"
    r = c.post("/api/scriptgen", json={"topic": "Sunrise Coffee", "brief": "fresh beans; free shipping"})
    assert r.status_code == 200 and r.json()["lines"]
    assert c.post("/api/scriptgen", json={}).status_code == 400
    assert c.post("/api/scriptgen", json={"topic": "x", "kind": "poem"}).status_code == 400
    assert c.post("/api/scriptgen", json={"topic": "x", "mode": "llm"}).status_code == 503
    assert c.post("/api/scriptgen", json={"topic": "x", "speakers": list("abcde")}).status_code == 422
