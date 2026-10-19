---
type: entity
title: "voicelab module (Voice Lab engine)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/voicelab.py"
language: py
depends_on:
  - "[[entities/voices-module]]"
  - "[[entities/tts-module]]"
used_by:
  - "[[entities/voicelab_api-module]]"
last_commit_hash: "0a207b37dc9809791194e8b796c9113351ebfb6e"
tested_by: []
tags:
  - entity
  - voices
related: []
sources:
  - "src/naturalvoice/voicelab.py"
---

# voicelab module (Voice Lab engine)

## Overview

Voice Lab logic: designing custom voices from a voice recipe ([[entities/voicelab-build_style]], `voicelab.py:400`), describing voices from text (`describe`, `voicelab.py:507-580`), and **voice matching** ([[entities/voicelab-match]], `voicelab.py:590`). All results are Kokoro voice vectors; nothing here clones.

## Exports (selected)

- `render`, `embed`, `cosine`, `pitch_hz`, `brightness_hz` (`voicelab.py:60`, `:188`, `:196`, `:78`, `:100`)
- [[entities/voicelab-stock_features]] (`:254`), `model_fingerprint` (`:213`)
- `validate_recipe` (`:345`), [[entities/voicelab-build_style]] (`:400`), `blend` (`:293`), `CONTROLS` (`:313`)
- `library`, `render_preview` (`:422`, `:444`), `describe` (`:507`), `Cancelled` (`:586`), [[entities/voicelab-match]] (`:590`)
- `FEATURE_VERSION = 2` (`:49`), `SPEAKER_MODEL` CAM++ ONNX (`:26`)

## Imports

- `from . import voices as vlib` (`voicelab.py:22`); lazy `from .tts import MODEL_DIR` (`voicelab.py:216`).

## Connections

- **used_by:** [[entities/voicelab_api-module]] (`voicelab_api.py:18`)
- **frontend:** `src/naturalvoice/web/voicelab.js`, `voicelab.html` call `/api/voicelab` routes (router prefix `voicelab_api.py:21`).
- **concepts:** [[concepts/voices-voice-categories]]

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
