"""One place that talks to a language model, through the official OpenAI Python SDK.

OpenRouter exposes an OpenAI-compatible API, so the same SDK serves OpenRouter (the default), OpenAI itself,
any other OpenAI-compatible server (set NATURALVOICE_LLM_URL) and a local Ollama chat model.

Where the key comes from, in order:
  1. OPENROUTER_API_KEY environment variable
  2. a key saved from the app (Studio -> Write a script -> Connect AI), stored in data/llm.json with
     owner-only permissions, never returned by the API and never logged
  3. OPENAI_API_KEY
  4. NATURALVOICE_LLM_URL (+ optional OPENAI_API_KEY / NATURALVOICE_LLM_KEY)
  5. a local Ollama server that has a chat model installed
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from . import voices as vlib

OPENROUTER_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "openai/gpt-4o-mini"
OLLAMA_URL = "http://127.0.0.1:11434/v1"
SITE_URL = "https://github.com/g-baskin/voice-studio"
SITE_NAME = "Voice Studio"
_KEY_OK = re.compile(r"^[\x21-\x7e]{8,300}$")  # printable ASCII, no spaces


def _path():
    return vlib.DATA_DIR / "llm.json"


def _saved() -> dict:
    try:
        d = json.loads(_path().read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_key(api_key: str, model: str = "") -> None:
    api_key = (api_key or "").strip()
    model = (model or "").strip()
    if not _KEY_OK.match(api_key):
        raise ValueError("That doesn't look like an API key. Paste the whole key with no spaces.")
    if model and not re.match(r"^[\w./:@+-]{1,100}$", model):
        raise ValueError("Model names use letters, numbers and . / : - only.")
    vlib.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path().with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # owner-only from the first byte
    with os.fdopen(fd, "w") as fh:
        json.dump({"provider": "openrouter", "api_key": api_key, "model": model}, fh)
    os.replace(tmp, _path())


def clear_key() -> None:
    _path().unlink(missing_ok=True)


def _mask(key: str) -> str:
    return ("…" + key[-4:]) if len(key) >= 8 else ""


def ollama_chat_models() -> list[str]:
    """Installed Ollama models that can chat (embedding-only models such as all-minilm don't count)."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=0.6) as r:
            models = json.loads(r.read()).get("models", [])
    except (urllib.error.URLError, OSError, ValueError):
        return []
    out = []
    for m in models:
        caps = m.get("capabilities")
        family = (m.get("details") or {}).get("family", "")
        if caps is not None and "completion" not in caps:
            continue
        if caps is None and family in {"bert", "nomic-bert"}:
            continue
        if m.get("name"):
            out.append(m["name"])
    return out


def config() -> dict | None:
    """The connection to use right now, or None. Never include this dict in an API response (it holds the key)."""
    saved = _saved()
    model_env = os.environ.get("NATURALVOICE_LLM_MODEL", "").strip()
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    src = "OpenRouter (environment key)"
    if not key and saved.get("api_key"):
        key, src = saved["api_key"], "OpenRouter (saved key)"
    if key:
        return {"base_url": OPENROUTER_URL, "api_key": key, "provider": "openrouter", "label": src,
                "model": model_env or saved.get("model") or OPENROUTER_MODEL, "headers": {
                    "HTTP-Referer": SITE_URL, "X-Title": SITE_NAME}}
    if os.environ.get("OPENAI_API_KEY"):
        return {"base_url": "https://api.openai.com/v1", "api_key": os.environ["OPENAI_API_KEY"], "provider": "openai",
                "label": "OpenAI (environment key)", "model": model_env or "gpt-4o-mini", "headers": {}}
    url = os.environ.get("NATURALVOICE_LLM_URL", "").strip().rstrip("/")
    if url:
        return {"base_url": url, "api_key": os.environ.get("NATURALVOICE_LLM_KEY", "none"), "provider": "custom",
                "label": "your LLM server", "model": model_env or "default", "headers": {}}
    models = ollama_chat_models()
    if models:
        return {"base_url": OLLAMA_URL, "api_key": "ollama", "provider": "ollama",
                "label": "local Ollama (" + models[0] + ")", "model": model_env or models[0], "headers": {}}
    return None


def status() -> dict:
    """Safe to send to the browser: never contains the key (only the last 4 characters of a saved one)."""
    c = config()
    saved = _saved()
    out = {"available": c is not None, "via": c["label"] if c else None,
           "provider": c["provider"] if c else None, "model": c["model"] if c else OPENROUTER_MODEL,
           "key_saved": bool(saved.get("api_key")), "key_hint": _mask(saved.get("api_key", "")),
           "env_key": bool(os.environ.get("OPENROUTER_API_KEY", "").strip()), "default_model": OPENROUTER_MODEL}
    return out


def _client(c: dict, timeout: float):
    from openai import OpenAI

    return OpenAI(base_url=c["base_url"], api_key=c["api_key"], default_headers=c["headers"] or None,
                  timeout=timeout, max_retries=1)


def _explain(e: Exception, c: dict) -> str:
    import openai

    who = {"openrouter": "OpenRouter", "openai": "OpenAI"}.get(c["provider"], "The language model")
    if isinstance(e, openai.AuthenticationError):
        return f"{who} rejected the API key. Check it and try again."
    if isinstance(e, openai.RateLimitError):
        return f"{who} says the limit or credit has run out. Check your account, then try again."
    if isinstance(e, openai.NotFoundError):
        return f"{who} doesn't know the model \"{c['model']}\". Pick another model name."
    if isinstance(e, openai.APITimeoutError):
        return f"{who} took too long to answer. Try again."
    if isinstance(e, openai.APIConnectionError):
        return f"Couldn't reach {who.lower() if who.startswith('The') else who}. Check the internet connection."
    return f"{who} could not answer. Try again in a moment."


def chat(system: str, user: str, temperature: float = 0.4, timeout: float = 90, max_tokens: int | None = None) -> str:
    c = config()
    if c is None:
        raise RuntimeError("No AI is connected. Add an OpenRouter key in Studio, or set OPENROUTER_API_KEY.")
    try:
        kw = {"max_tokens": max_tokens} if max_tokens else {}
        r = _client(c, timeout).chat.completions.create(
            model=c["model"], temperature=temperature, **kw,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        out = (r.choices[0].message.content or "").strip()
    except Exception as e:  # SDK errors are mapped to plain sentences; the key never appears in them
        raise RuntimeError(_explain(e, c)) from None
    if not out:
        raise RuntimeError("The language model returned nothing. Try again.")
    return out


def connect(api_key: str, model: str = "") -> dict:
    """Validate with a tiny real request, and only then save. Returns the safe status."""
    if not _KEY_OK.match((api_key or "").strip()):
        raise ValueError("That doesn't look like an API key. Paste the whole key with no spaces.")
    probe = {"base_url": OPENROUTER_URL, "api_key": api_key.strip(), "provider": "openrouter", "label": "",
             "model": (model or "").strip() or OPENROUTER_MODEL,
             "headers": {"HTTP-Referer": SITE_URL, "X-Title": SITE_NAME}}
    try:
        _client(probe, 30).chat.completions.create(
            model=probe["model"], max_tokens=5, messages=[{"role": "user", "content": "Say OK."}])
    except Exception as e:
        raise RuntimeError(_explain(e, probe)) from None
    save_key(api_key, model)
    return status()
