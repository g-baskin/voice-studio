import pytest
from fastapi.testclient import TestClient

from naturalvoice import rewrite as rw, server


@pytest.mark.parametrize(
    "n,words",
    [
        (0, "zero"),
        (13, "thirteen"),
        (21, "twenty-one"),
        (100, "one hundred"),
        (1234, "one thousand two hundred thirty-four"),
        (2500000, "two million five hundred thousand"),
    ],
)
def test_int_words(n, words):
    assert rw.int_to_words(n) == words


def test_ordinals_and_years():
    assert (
        rw.ordinal_words(1) == "first"
        and rw.ordinal_words(22) == "twenty-second"
        and rw.ordinal_words(40) == "fortieth"
    )
    assert rw.year_words(1990) == "nineteen ninety" and rw.year_words(1905) == "nineteen oh five"
    assert rw.year_words(2024) == "twenty twenty-four" and rw.year_words(2005) == "two thousand five"


def test_rule_rewrite_spells_things_out():
    out = rw.rule_rewrite("Dr. Lee paid $5.50 on the 3rd, 25% off, for 1,200 items at 9:30 am & more.")["text"]
    for want in (
        "Doctor Lee",
        "five dollars and fifty cents",
        "third",
        "twenty-five percent",
        "one thousand two hundred items",
        "nine thirty a m",
        "and more",
    ):
        assert want in out.lower() or want.lower() in out.lower(), (want, out)
    assert not any(c.isdigit() for c in out) and "$" not in out and "%" not in out


def test_links_markdown_and_splitting():
    r = rw.rule_rewrite("**Visit** https://example.com now or mail me@site.org. " + "word " * 30 + "and then stop.")
    assert "the link" in r["text"] and "me at site dot org" in r["text"] and "*" not in r["text"]
    assert max(len(s.split()) for s in r["text"].split(".") if s.strip()) <= 32
    assert any("Split" in n for n in r["notes"])


def test_tags_survive_and_noop():
    assert "[laugh]" in rw.rule_rewrite("That was funny [laugh] really.")["text"]
    assert rw.rule_rewrite("Hello there.")["notes"] == ["Nothing needed fixing."]
    assert "don't" in rw.rule_rewrite("We do not mind.", conversational=True)["text"]


def test_api(monkeypatch):
    c = TestClient(server.app)
    assert c.get("/api/rewrite/status").json()["rules"] is True
    r = c.post("/api/rewrite", json={"text": "It costs $3."}).json()
    assert r["text"] == "It costs three dollars." and r["engine"] == "built-in rules"
    assert c.post("/api/rewrite", json={"text": ""}).status_code == 422
    assert c.post("/api/rewrite", json={"text": "x", "mode": "nope"}).status_code == 400
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("NATURALVOICE_LLM_URL", raising=False)
    monkeypatch.setattr(rw, "llm_available", lambda: {"available": False, "via": None})
    r = c.post("/api/rewrite", json={"text": "hi", "mode": "llm"})
    assert r.status_code == 503 and "OPENROUTER_API_KEY" in r.json()["detail"]
    assert c.post("/api/rewrite", json={"text": "hi", "mode": "llm", "tone": "bad"}).status_code in (400, 503)


def test_bracket_tags_are_protected():
    out = rw.rule_rewrite("Save 50% & more [pause 1s] e.g. today [clear throat] 3 items.")["text"]
    assert "[pause 1s]" in out and "[clear throat]" in out
    assert "fifty percent and more" in out and "three items" in out and "ones" not in out


def test_many_tags_all_restored():
    src = " ".join(f"{i} [laugh]" for i in range(15))
    out = rw.rule_rewrite(src)["text"]
    assert out.count("[laugh]") == 15 and not any(c.isdigit() for c in out)


def test_no_is_only_number_before_digits():
    assert rw.rule_rewrite("No. What is it?")["text"].startswith("No. What")
    assert "number five" in rw.rule_rewrite("See No. 5 now.")["text"]
