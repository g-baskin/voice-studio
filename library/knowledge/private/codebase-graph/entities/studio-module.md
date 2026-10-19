---
type: entity
title: "studio (module)"
entity_type: module
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/studio.py"
language: py
depends_on:
  - "[[audio-module]]"
  - "[[humanize-module]]"
  - "[[entities/tts-module]]"
  - "[[voices-module]]"
  - "[[clone-module]]"
  - "[[studio-api-module]]"
used_by:
  - "[[studio-api-module]]"
  - "[[entities/cli-main]]"
last_commit_hash: "35c85ddcc30466e8280841dbdfaf7ceb0b22fcba"
tested_by:
  - "tests/test_studio.py"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/studio.py"
---

# studio (module)

## Overview

Core of the Studio workspace: multi-voice script rendering with delivery direction, music bed, mastering and captions (`src/naturalvoice/studio.py:1`). A Delivery preset is a named combination of speed, pitch, pause, gain and light EQ because Kokoro has no emotion control (`src/naturalvoice/studio.py:3-4`).

## Key definitions

- Limits: `SR = 24000`, `MAX_LINES = 500`, `MAX_CHARS = 50000` (`src/naturalvoice/studio.py:29-31`).
- `VOICE_ID` accepts stock ids, `custom:<12hex>` and `clone:<12hex>` (`src/naturalvoice/studio.py:32`).
- `TAKE_STYLE_JITTER = 0.03`, `SAFE_SPEED = (0.85, 1.2)`, `STRETCH_FINE = (0.95, 1.05)`, `ACX_ROOM_TONE_DB = -65.0` (`src/naturalvoice/studio.py:35-38`).
- `DELIVERY` table of Delivery presets (`src/naturalvoice/studio.py:42`); `TARGETS` loudness targets youtube/podcast/broadcast/acx/raw (`src/naturalvoice/studio.py:110-116`).
- `StudioError(ValueError)` user-facing failure (`src/naturalvoice/studio.py:121`); `Cancelled` (`src/naturalvoice/studio.py:1111`).
- Inline tags: `TAG`, `PAUSE_TAG`, `MARK` regexes (`src/naturalvoice/studio.py:126-128`); `parse_inline` (`src/naturalvoice/studio.py:148`).
- Pronunciation dictionary helpers `mark_dictionary`, `display_text`, `spoken_text` (`src/naturalvoice/studio.py:182-207`).
- Delivery style storage: `validate_style`, `delivery_of`, `style_from_line`, `load_styles`, `save_styles` (`src/naturalvoice/studio.py:359-461`).
- Director's note parser `parse_note`, pure, applies nothing (`src/naturalvoice/studio.py:544-545`).
- In-memory line render cache: `OrderedDict`, lock, `CACHE_SIZE = 64` (`src/naturalvoice/studio.py:621-623`).
- Captions: `caption_cues`, `to_srt`, `to_vtt` (`src/naturalvoice/studio.py:1025-1078`).
- Ducked music bed: `duck_gain`, `music_bed` (`src/naturalvoice/studio.py:934-998`).
- Video: `probe_duration`, `probe_streams`, `original_bed`, `mux_video` (`src/naturalvoice/studio.py:1495-1555`).
- `projects_dir()` is `voices.DATA_DIR / "projects"` (`src/naturalvoice/studio.py:1629-1632`).

## Imports

Top level: `audio as aio`, `humanize as hz` (`src/naturalvoice/studio.py:26-27`). Lazy: `clone` (`:137`), `voices` (`:434`, `:705`, `:1630`), `tts` (`:693`), `studio_api.Project` (`:1640`).

## Connections

- **entities:** [[studio-render-line]], [[studio-render-project]], [[studio-fit-project]], [[studio-master]], [[studio-parse-script]], [[studio-parse-subtitles]], [[studio-render-options]], [[studio-cli-render]]
- **other chunks:** [[audio-module]], [[humanize-module]], [[entities/tts-module]], [[entities/cli-main]] (chunk A); [[voices-module]], [[clone-module]] (chunk C)
- **concepts:** [[studio-render-pipeline]]

## History

- Created: `7962b18` (2026-10-18). Last touched: `35c85dd` "Refactor Studio rendering and controls and remove unused dependencies" (2026-10-18).
