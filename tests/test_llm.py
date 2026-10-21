import json
import os
import stat

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from naturalvoice import llm, rewrite, server, voices as vlib

KEY = "TESTKEY-1234567890-abcd"  # obviously fake, and not shaped like a real key so secret scanners stay quiet


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    monkeypatch.setattr(vlib, "DATA_DIR", tmp_path)
    for k in (
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "NATURALVOICE_LLM_URL",
        "NATURALVOICE_LLM_MODEL",
        "NATURALVOICE_LLM_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "ollama_chat_models", lambda: [])


class FakeClient:
    """Stands in for the OpenAI SDK client; records what the app sent."""

    sent: dict[str, object] = {}

    def __init__(self, reply="Hello there.", error=None):
        self.reply, self.error = reply, error
        self.chat = self
        self.completions = self

    def create(self, **kw):
        FakeClient.sent = kw
        if self.error:
            raise self.error
        msg = type("M", (), {"content": self.reply})
        return type("R", (), {"choices": [type("C", (), {"message": msg})]})


def patch_client(monkeypatch, **kw):
    seen = {}

    def make(c, timeout):
        seen["cfg"] = c
        return FakeClient(**kw)

    monkeypatch.setattr(llm, "_client", make)
    return seen


def test_nothing_connected():
    assert llm.status()["available"] is False and llm.config() is None
    with pytest.raises(RuntimeError, match="OpenRouter key"):
        llm.chat("s", "u")


def test_openrouter_env_key_uses_openrouter_defaults(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    seen = patch_client(monkeypatch)
    assert llm.chat("sys", "usr") == "Hello there."
    c = seen["cfg"]
    assert c["base_url"] == "https://openrouter.ai/api/v1" and c["model"] == "openai/gpt-4o-mini"
    assert c["headers"]["X-Title"] == "Voice Studio"
    messages = FakeClient.sent["messages"]
    assert isinstance(messages, list)
    assert messages[0] == {"role": "system", "content": "sys"}
    st = llm.status()
    assert st["available"] and st["provider"] == "openrouter" and st["env_key"] is True
    assert KEY not in json.dumps(st)


def test_model_override_and_provider_order(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "OPENAIKEY-xxxxxxxxxx")
    config = llm.config()
    assert config is not None and config["provider"] == "openai"
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.setenv("NATURALVOICE_LLM_MODEL", "anthropic/claude-haiku-5.5")
    c = llm.config()
    assert c is not None and c["provider"] == "openrouter" and c["model"] == "anthropic/claude-haiku-5.5"
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("NATURALVOICE_LLM_URL", "http://localhost:1234/v1/")
    config = llm.config()
    assert config is not None and config["base_url"] == "http://localhost:1234/v1"
    monkeypatch.delenv("NATURALVOICE_LLM_URL")
    monkeypatch.delenv("NATURALVOICE_LLM_MODEL")
    monkeypatch.setattr(llm, "ollama_chat_models", lambda: ["llama3.2:1b"])
    config = llm.config()
    assert config is not None and config["provider"] == "ollama" and config["model"] == "llama3.2:1b"


def test_saved_key_is_private_and_never_returned(monkeypatch, tmp_path):
    llm.save_key(KEY, "openai/gpt-4o-mini")
    mode = stat.S_IMODE(os.stat(tmp_path / "llm.json").st_mode)
    assert mode == 0o600
    st = llm.status()
    assert st["key_saved"] and st["key_hint"] == "…abcd" and KEY not in json.dumps(st)
    config = llm.config()
    assert config is not None and config["api_key"] == KEY and config["label"].endswith("(saved key)")
    monkeypatch.setenv("OPENROUTER_API_KEY", "ENVKEY-xxxxxxxxxx")  # environment wins over the saved key
    config = llm.config()
    assert config is not None and config["api_key"] == "ENVKEY-xxxxxxxxxx"
    llm.clear_key()
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert llm.config() is None and not (tmp_path / "llm.json").exists()


@pytest.mark.parametrize("bad", ["", "short", "has space in it 12345", "line\nbreak12345", "é" * 12, "x" * 301])
def test_bad_keys_rejected_before_any_request(bad, monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda *a, **k: pytest.fail("no request should be made"))
    with pytest.raises(ValueError):
        llm.connect(bad)
    with pytest.raises(ValueError):
        llm.save_key(bad)


def err(cls, status):
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp = httpx.Response(status, request=req, json={"error": {"message": "secret detail " + KEY}})
    return cls("secret detail " + KEY, response=resp, body=None)


@pytest.mark.parametrize(
    "exc,phrase",
    [
        (err(openai.AuthenticationError, 401), "rejected the API key"),
        (err(openai.RateLimitError, 429), "credit has run out"),
        (err(openai.NotFoundError, 404), "doesn't know the model"),
    ],
)
def test_errors_are_plain_and_never_echo_the_key(monkeypatch, exc, phrase):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    patch_client(monkeypatch, error=exc)
    with pytest.raises(RuntimeError) as e:
        llm.chat("s", "u")
    assert phrase in str(e.value) and KEY not in str(e.value) and "secret detail" not in str(e.value)


def test_api_connect_saves_only_after_a_working_test(monkeypatch, tmp_path):
    c = TestClient(server.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    patch_client(monkeypatch, error=err(openai.AuthenticationError, 401))
    r = c.put("/api/llm/key", json={"api_key": KEY})
    assert r.status_code == 502 and "rejected" in r.json()["detail"] and KEY not in r.text
    assert not (tmp_path / "llm.json").exists(), "a key that failed its test must not be saved"
    assert c.put("/api/llm/key", json={"api_key": "no spaces allowed here"}).status_code == 400
    patch_client(monkeypatch)
    r = c.put("/api/llm/key", json={"api_key": KEY, "model": "openai/gpt-4o-mini"})
    assert r.status_code == 200 and r.json()["key_saved"] and KEY not in r.text
    assert c.get("/api/llm/status").json()["available"] is True
    assert KEY not in c.get("/api/llm/status").text and KEY not in c.get("/api/rewrite/status").text
    assert c.delete("/api/llm/key").json()["key_saved"] is False


def test_rewrite_and_scriptgen_use_the_connection(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    patch_client(
        monkeypatch,
        reply=json.dumps({"title": "T", "lines": [{"speaker": "Narrator", "text": "We have 3 [laugh] ideas."}]}),
    )
    assert rewrite.llm_available() == {"available": True, "via": "OpenRouter (environment key)"}
    from naturalvoice import scriptgen

    out = scriptgen.generate("Tea", "hot", "ad", "calm", 30, ["Narrator"], emotion_tags=True)
    assert out["engine"] == "language model" and out["lines"][0]["text"] == "We have three [laugh] ideas."
    patch_client(monkeypatch, reply="Plain rewritten text.")
    assert rewrite.llm_rewrite("hi", "warm")["engine"] == "language model"
