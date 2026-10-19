---
type: entity
title: "llm (module)"
entity_type: service
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/llm.py"
language: py
depends_on:
  - "[[voices-module]]"
used_by:
  - "[[rewrite-module]]"
  - "[[scriptgen-module]]"
  - "[[llm-api-module]]"
  - "[[entities/scriptgen-module]]"
  - "[[entities/rewrite-module]]"
last_commit_hash: "9f0eac707a5a90e97985e49e734e916eced025cd"
tested_by:
  - "tests/test_llm.py"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/llm.py"
---

# llm (module)

## Overview

Optional language-model connection for writing help (OpenAI SDK). Provider order lives in `config()`, which must never be sent to a client because it holds the key (`src/naturalvoice/llm.py:88-89`).

## Provider order (`config`)

1. `OPENROUTER_API_KEY` env, else a saved OpenRouter key (`src/naturalvoice/llm.py:92-95`); default model `openai/gpt-4o-mini` (`src/naturalvoice/llm.py:26`).
2. `OPENAI_API_KEY` (`src/naturalvoice/llm.py:105`).
3. `NATURALVOICE_LLM_URL` with optional `NATURALVOICE_LLM_KEY` (`src/naturalvoice/llm.py:114-119`).
4. Local Ollama models at `127.0.0.1:11434` (`src/naturalvoice/llm.py:124-132`, `:27`).
5. Otherwise `None`. `NATURALVOICE_LLM_MODEL` overrides the model (`src/naturalvoice/llm.py:91`).

## Public API

- `status()`: browser-safe, only a masked key hint (`src/naturalvoice/llm.py:137-151`).
- `chat(system, user, ...)`: raises `RuntimeError` with plain text; SDK errors are mapped by `_explain` so the key never appears (`src/naturalvoice/llm.py:183-200`).
- `save_key`: validates format, writes under `voices.DATA_DIR` with mode 0600 and atomic replace (`src/naturalvoice/llm.py:45-57`). `clear_key` (`:60`). `connect` tests then saves (`:203`).

## Connections

- depends_on: [[voices-module]] (DATA_DIR)
- used_by: [[rewrite-module]], [[entities/scriptgen-module]], [[entities/rewrite-module]], [[llm-api-module]]
- concepts: [[studio-writing-assist-llm-fallback]]
