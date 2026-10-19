---
type: entity
title: "scriptgen (module) and scriptgen_api"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/scriptgen.py"
language: py
depends_on:
  - "[[rewrite-module]]"
used_by:
  - "[[entities/server-app]]"
  - "[[web-studio-module]]"
last_commit_hash: "9f0eac707a5a90e97985e49e734e916eced025cd"
tested_by:
  - "tests/test_scriptgen.py"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/scriptgen.py"
---

# scriptgen (module) and scriptgen_api

## Overview

Script generator for ads, social videos, podcast intros and more. `KINDS` and `TONES` (`src/naturalvoice/scriptgen.py:18`, `:26`); budget `WORDS_PER_SECOND = 2.5` (`src/naturalvoice/scriptgen.py:17`).

## `generate`

- Validates kind, tone, 10..300 seconds and mode `auto|llm|template` (`src/naturalvoice/scriptgen.py:242-249`); cleans up to 4 speaker names; dialogue gets two (`src/naturalvoice/scriptgen.py:250-253`).
- Uses `llm_script` when mode is `llm` or `auto` with an LLM available; `auto` falls back to `template_script` with a note on `RuntimeError` (`src/naturalvoice/scriptgen.py:256-266`).
- Every Line text passes through `rewrite.rule_rewrite` (`src/naturalvoice/scriptgen.py:268-269`).
- `llm_script` prompts with speaker names and optional clone emotion tags `CLONE_TAGS` (`src/naturalvoice/scriptgen.py:188-206`, `:27`).

## `scriptgen_api`

Router `/api/scriptgen` (`src/naturalvoice/scriptgen_api.py:10`): GET `/status` (`:27`), GET `/sample` (`:38`), POST `` runs `generate`, 400 on ValueError, 503 on RuntimeError (`src/naturalvoice/scriptgen_api.py:43-51`).

## Connections

- depends_on: [[rewrite-module]], [[llm-module]] (API status)
- used_by: [[entities/server-app]], [[web-studio-module]] (`src/naturalvoice/web/studio.js:1264`)
- concepts: [[studio-writing-assist-llm-fallback]]
