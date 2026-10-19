---
type: entity
title: "clone module (cloning engine client)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/clone.py"
language: py
depends_on:
  - "[[entities/voices-module]]"
  - "[[entities/audio-module]]"
  - "[[entities/humanize-module]]"
  - "[[entities/chatterbox_worker-main]]"
used_by:
  - "[[entities/clone_api-module]]"
  - "[[entities/studio-module]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/clone.py"
---

# clone module (cloning engine client)

## Overview

Main-app side of the isolated Chatterbox-Turbo cloning engine (`src/naturalvoice/clone.py:23-32`). Prepares reference recordings, speaks text and performs voice conversion in a **cloned voice** by calling [[entities/clone-_Worker]].

## Exports (selected)

- `installed()` checks engine venv, worker and ONNX files (`clone.py:83-91`); `status()` (`:207-219`); `stop()` (`:203`)
- `prepare_reference(src, dst)` makes mono 24 kHz trimmed, loudness-normalised WAV, 5 to 60 s in, at most 20 s kept (`:252-279`, limits `:30`)
- `speak(text, voice_id, ...)` (`:343-384`), `convert(...)` voice conversion (`:432-468`), `speak_language` (`:513-544`)
- `clean_tags`, `EMOTION_TAGS` (`:37`, `:51`)

## Behavior

- `speak` requires a `clone:` id (`clone.py:346-347`), sends one `speak` request per sentence with `timeout=60 + 3 * len(sentence)` (`:365-368`), reads back `.npy` output (`:369`).

## Connections

- **imports:** [[entities/voices-module]] (`:344`), lazy [[entities/audio-module]] and [[entities/humanize-module]] (`:254-255`)
- **used_by:** [[entities/clone_api-module]] (`clone_api.py:42`, `:55`, `:104`), [[entities/studio-module]] (`studio.py:137`)
- **process boundary:** [[entities/chatterbox_worker-main]] via [[concepts/voices-isolated-engines]]
- **ADR:** `docs/adr/0001-isolate-the-cloning-engine.md`

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
