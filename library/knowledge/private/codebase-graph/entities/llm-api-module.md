---
type: entity
title: "llm_api (module)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/llm_api.py"
language: py
depends_on:
  - "[[llm-module]]"
used_by:
  - "[[entities/server-app]]"
  - "[[web-studio-module]]"
last_commit_hash: "9f0eac707a5a90e97985e49e734e916eced025cd"
tested_by:
  - "tests/test_llm.py:146"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/llm_api.py"
---

# llm_api (module)

Router at `/api/llm` (`src/naturalvoice/llm_api.py:10`), mounted at `src/naturalvoice/server.py:241`.

- GET `/status` returns `llm.status()` (`src/naturalvoice/llm_api.py:19-20`).
- PUT `/key` calls `llm.connect`; `ValueError` maps to 400, `RuntimeError` to 502 (`src/naturalvoice/llm_api.py:24-30`). Body `KeyBody` api_key <=400, model <=100 (`src/naturalvoice/llm_api.py:13-15`).
- DELETE `/key` clears the saved key (`src/naturalvoice/llm_api.py:34-36`).

Connections: depends_on [[llm-module]]; used_by [[entities/server-app]], [[web-studio-module]] (`src/naturalvoice/web/studio.js:1164`, `:1190`).
