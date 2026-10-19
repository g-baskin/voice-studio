---
type: entity
title: "rewrite (module) and rewrite_api"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/rewrite.py"
language: py
depends_on:
  - "[[llm-module]]"
used_by:
  - "[[scriptgen-module]]"
  - "[[entities/server-app]]"
  - "[[web-studio-module]]"
last_commit_hash: "9f0eac707a5a90e97985e49e734e916eced025cd"
tested_by:
  - "tests/test_rewrite.py"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/rewrite.py"
---

# rewrite (module) and rewrite_api

## Overview

Rewrites text for speech: deterministic rules plus an optional language-model rewrite.

## `rule_rewrite(text, conversational=False)`

- Parks square-bracket tags as private-use characters so digits inside are not spelled out, then restores them (`src/naturalvoice/rewrite.py:256-263`, `:281`).
- Steps: `clean_symbols`, `expand_abbreviations`, `spell_numbers`, optional `CONTRACTIONS`, `split_long` (`src/naturalvoice/rewrite.py:264-278`).
- Returns `{text, notes, engine: "built-in rules"}` (`src/naturalvoice/rewrite.py:285`).

## LLM path

- `llm_available` and `chat` delegate to [[llm-module]] (`src/naturalvoice/rewrite.py:299-306`).
- `llm_rewrite` checks `TONES` and keeps tags exactly (`src/naturalvoice/rewrite.py:309-325`, `:290`).

## `rewrite_api`

Router `/api/rewrite` (`src/naturalvoice/rewrite_api.py:10`): GET `/status` (`:22`), POST `` with mode `rules|llm`, 400/503 mapping (`src/naturalvoice/rewrite_api.py:27-37`).

## Connections

- depends_on: [[llm-module]]
- used_by: [[scriptgen-module]], [[entities/server-app]], [[web-studio-module]] (`src/naturalvoice/web/studio.js:425`)
