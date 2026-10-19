---
type: entity
title: "studio.parse_subtitles"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/studio.py"
language: py
depends_on:
  - "[[studio-module]]"
used_by:
  - "[[studio-api-module]]"
last_commit_hash: "35c85ddcc30466e8280841dbdfaf7ceb0b22fcba"
tested_by:
  - "tests/test_studio.py:301"
  - "tests/test_studio.py:317"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/studio.py"
---

# studio.parse_subtitles

## Overview

Converts SRT or WebVTT into timed Lines for Timed placement and Dubbing. Formatting tags are dropped; `<v Name>` and `NAME:` become Speakers (`src/naturalvoice/studio.py:223-224`).

## Behavior

- Normalises line endings and BOM, rejects empty input with `StudioError` (`src/naturalvoice/studio.py:225-227`).
- Splits blocks on blank lines and finds the `-->` cue row (`src/naturalvoice/studio.py:228-232`); time regex `SUB_TIME`, cue regex `SUB_CUE` (`src/naturalvoice/studio.py:210-211`).
- Upload size cap `MAX_SUB_BYTES = 2 MiB` (`src/naturalvoice/studio.py:212`).

## Connections

- used_by: [[studio-api-module]] (`POST /api/studio/subtitles`), [[studio-cli-render]] (dub path)
- concepts: [[studio-render-pipeline]]
