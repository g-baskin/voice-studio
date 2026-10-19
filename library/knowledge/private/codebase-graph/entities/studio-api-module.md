---
type: entity
title: "studio_api (module)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/studio_api.py"
language: py
depends_on:
  - "[[studio-module]]"
  - "[[entities/server-app]]"
  - "[[audio-module]]"
used_by:
  - "[[entities/server-app]]"
  - "[[web-studio-module]]"
  - "[[studio-cli-render]]"
last_commit_hash: "9f0eac707a5a90e97985e49e734e916eced025cd"
tested_by:
  - "tests/test_studio.py:125"
  - "tests/test_studio.py:198"
  - "tests/test_studio.py:216"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/studio_api.py"
---

# studio_api (module)

## Overview

FastAPI router for Studio under `/api/studio` (`src/naturalvoice/studio_api.py:24`), mounted by the server (`src/naturalvoice/server.py:230-236`).

## Data models

- `Line` (pydantic): id, text <=5000, voice, speaker, speed 0.5..2, pitch -4..4, volume -24..12, pause, delivery, take, takes <=5, target, start, end, note, style (`src/naturalvoice/studio_api.py:37-54`).
- `Project`: title, lines <= `MAX_LINES`, dictionary, cast, `mode: sequential | timed` (`src/naturalvoice/studio_api.py:87-93`).
- `RenderRequest`, `PreviewRequest`, `ParseRequest`, `StyleIn`, `NoteIn` (`src/naturalvoice/studio_api.py:126-277`).

## Routes

| Route | Handler | Line |
|---|---|---|
| GET /presets | presets | `:181` |
| POST /parse | parse ([[studio-parse-script]]) | `:190` |
| POST /lint | lint | `:200` |
| POST /preview | preview ([[studio-render-line]]) | `:205` |
| GET/POST/DELETE /styles | list_styles, save_style, delete_style | `:235-271` |
| POST /note | understand_note | `:281` |
| POST /music, /video, /subtitles | uploads | `:289`, `:356`, `:385` |
| POST /render | render ([[studio-render-project]]) | `:419` |
| GET /render/{job}, POST cancel, GET /renders, GET file | status/cancel/list/file | `:497-547` |
| /projects CRUD + duplicate | list/create/get/update/duplicate/delete | `:580-629` |

## Behavior

- `_busy` acquires the server-wide `processing` lock non-blocking and returns HTTP 429 when held (`src/naturalvoice/studio_api.py:171-176`).
- Render runs in a daemon thread, updating the in-memory `jobs` dict; `Cancelled`/`StudioError`/other errors clean the output dir and always release the lock (`src/naturalvoice/studio_api.py:464-486`).
- Scratch dir `WORK` under the system temp dir; keeps `KEEP_RENDERS = 8` (`src/naturalvoice/studio_api.py:26-29`).
- Projects persist atomically as JSON in `studio.projects_dir()` via tmp file plus replace (`src/naturalvoice/studio_api.py:569-576`); damaged files return 422 (`src/naturalvoice/studio_api.py:557-566`).

## Connections

- depends_on: [[studio-module]], [[entities/server-app]] (lock), [[audio-module]] (lazy, `:310`)
- used_by: [[entities/server-app]], [[web-studio-module]], [[studio-cli-render]]
