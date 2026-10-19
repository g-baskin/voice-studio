---
type: entity
title: "studio.RenderOptions"
entity_type: data-model
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/studio.py"
language: py
depends_on: []
used_by:
  - "[[studio-render-project]]"
  - "[[studio-api-module]]"
  - "[[studio-cli-render]]"
last_commit_hash: "35c85ddcc30466e8280841dbdfaf7ceb0b22fcba"
tested_by: []
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/studio.py"
---

# studio.RenderOptions

## Overview

Dataclass of render settings consumed by `render_project` (`src/naturalvoice/studio.py:1083-1108`).

## Fields

- Output: `target="podcast"`, `sample_rate=24000`, `format="wav"`, `stems`, `line_clips`, `captions=True`, `polish`, `stop_on_error` (`src/naturalvoice/studio.py:1084-1091`).
- Music bed: `music`, `music_level_db=-18.0`, `music_loop`, `duck`, `duck_db=12.0`, `attack_ms`, `release_ms`, `fade_in`, `fade_out` (`src/naturalvoice/studio.py:1092-1100`).
- Timing: `lead_in=0.3`, `target_duration`, `room_tone` (`src/naturalvoice/studio.py:1101-1103`).
- Video: `video`, `video_mode="replace"`, `video_level_db=-6.0`, `video_subs=True` (`src/naturalvoice/studio.py:1104-1107`).

The API mirrors these with validated ranges in `RenderRequest` (`src/naturalvoice/studio_api.py:126-151`) and copies them field by field (`src/naturalvoice/studio_api.py:438-462`).

## Connections

- used_by: [[studio-render-project]], [[studio-api-module]], [[studio-cli-render]]
