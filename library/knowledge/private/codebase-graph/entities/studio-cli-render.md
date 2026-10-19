---
type: entity
title: "studio.cli_render"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/studio.py"
language: py
depends_on:
  - "[[studio-api-module]]"
  - "[[studio-render-project]]"
  - "[[studio-parse-subtitles]]"
used_by:
  - "[[entities/cli-main]]"
last_commit_hash: "35c85ddcc30466e8280841dbdfaf7ceb0b22fcba"
tested_by:
  - "tests/test_studio.py:402"
  - "tests/test_studio.py:429"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/studio.py"
---

# studio.cli_render

## Overview

Shared by `naturalvoice render` and `naturalvoice dub`; validates exactly like the API (`src/naturalvoice/studio.py:1636-1637`).

## Behavior

- Imports the pydantic `Project` model from `studio_api` (`src/naturalvoice/studio.py:1640`) and validates input with it (`src/naturalvoice/studio.py:1668`).
- `dub` command branch (`src/naturalvoice/studio.py:1642`); video must have an allowed extension and a picture stream (`src/naturalvoice/studio.py:1675-1680`).
- Called from the CLI at `src/naturalvoice/cli.py:108`.

## Connections

- depends_on: [[studio-api-module]], [[studio-render-project]]
- used_by: [[entities/cli-main]]
