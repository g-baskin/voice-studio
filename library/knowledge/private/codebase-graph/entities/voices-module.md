---
type: entity
title: "voices module (voice library storage)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/voices.py"
language: py
depends_on: []
used_by:
  - "[[entities/studio-module]]"
  - "[[entities/llm-module]]"
  - "[[entities/server-app]]"
  - "[[entities/cli-main]]"
  - "[[entities/voicelab-module]]"
  - "[[entities/sample_library-module]]"
  - "[[entities/clone-module]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/voices.py"
---

# voices module (voice library storage)

## Overview

Storage layer for user-created voices under `NATURALVOICE_DATA/voices` (`src/naturalvoice/voices.py:24-25`). It keeps the two categories distinct: a **custom voice** is a Kokoro voice vector saved as `.npy` with id prefix `custom:` (`voices.py:68-89`), a **cloned voice** is a reference recording `.wav` with id prefix `clone:` (`voices.py:92-110`). Stock voices are not stored here; `style_of` reads them from Kokoro (`voices.py:162-167`).

## Exports

- [[entities/voices-save_custom]] (`voices.py:68`), [[entities/voices-save_clone]] (`voices.py:92`)
- `list_custom` (`:113`), `get` (`:127`), `rename` (`:137`), `delete` (`:147`), `style_of` (`:155`), `reference_audio` (`:170`), `resolve` (`:180`), `favorites`/`set_starred` (`:191`, `:200`), `catalog` (`:210`)
- Constants `DATA_DIR`, `VOICE_DIR`, `STYLE_SHAPE = (510, 1, 256)` (`:24-26`)

## Behavior notes

- `get` accepts only `custom:` or `clone:` ids (`voices.py:128-130`).
- `reference_audio` raises for anything but `clone:` (`voices.py:172-173`); `resolve` returns a vector only for `custom:`, otherwise the stock name (`voices.py:180-184`).
- `list_custom` skips corrupt JSON so one bad file does not hide the library (`voices.py:117-123`).
- Lazy import of [[entities/tts-module]] for stock vectors (`voices.py:162`).

## Connections

- **imported by (evidence: `from . import voices`):** [[entities/server-app]] (`server.py:48`), [[entities/cli-main]] (`cli.py:135`), [[entities/llm-module]] (`llm.py:23`), [[entities/studio-module]] (`studio.py:434`), [[entities/voicelab-module]] (`voicelab.py:22`), [[entities/sample_library-module]] (`sample_library.py:28`), [[entities/clone-module]] (`clone.py:344`)
- **concepts:** [[concepts/voices-voice-categories]]

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
