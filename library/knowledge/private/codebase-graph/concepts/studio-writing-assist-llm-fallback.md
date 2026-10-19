---
type: concept
title: "Studio writing assist and LLM fallback"
complexity: basic
domain: studio
aliases: []
created: 2026-10-19
updated: 2026-10-19
status: developing
tags:
  - concept
related:
  - "[[llm-module]]"
  - "[[rewrite-module]]"
  - "[[scriptgen-module]]"
sources:
  - "src/naturalvoice/llm.py"
---

# Studio writing assist and LLM fallback

## Definition

Script writing help in Studio works without any cloud provider: deterministic rules and templates are always available, and a language model is optional.

## How it works

- [[llm-module]] picks a provider in order OpenRouter, OpenAI, custom URL, local Ollama, or none (`src/naturalvoice/llm.py:88-134`).
- [[scriptgen-module]] in `auto` mode falls back to templates with a note when the model fails; explicit `llm` mode surfaces the error (`src/naturalvoice/scriptgen.py:256-266`).
- [[rewrite-module]] rules mode never calls a model (`src/naturalvoice/rewrite_api.py:32-33`).
- API routers map `RuntimeError` to 503 (rewrite, scriptgen) or 502 (key connect) (`src/naturalvoice/rewrite_api.py:36-37`, `src/naturalvoice/llm_api.py:29-30`).
- Keys never leave the server: `status()` returns only a masked hint (`src/naturalvoice/llm.py:137-151`).

## Connections

[[llm-api-module]], [[web-studio-module]]
