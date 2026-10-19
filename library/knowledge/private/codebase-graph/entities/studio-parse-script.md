---
type: entity
title: "studio.parse_script"
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
  - "tests/test_studio.py:23"
  - "tests/test_studio.py:35"
tags:
  - entity
  - studio
related: []
sources:
  - "src/naturalvoice/studio.py"
---

# studio.parse_script

## Overview

Converts plain script text into Lines plus a Cast. Speakers are written `NAME: text` or `[Name] text`; untagged lines keep the last Speaker (`src/naturalvoice/studio.py:284-285`).

## Behavior

- Rejects text over `MAX_CHARS` and results over `MAX_LINES` with `StudioError` (`src/naturalvoice/studio.py:286-287`, `:310-311`).
- A leading pause or `break` tag is not a Speaker (`src/naturalvoice/studio.py:297-298`).
- Voices come from the supplied Cast if valid per `VOICE_ID`, else rotate through `DEFAULT_CAST` (`src/naturalvoice/studio.py:304-308`, `:281`).
- Each Line is built by `new_line` with default delivery settings (`src/naturalvoice/studio.py:319-335`).
- Returns `{"lines", "cast": [{speaker, voice}]}` (`src/naturalvoice/studio.py:316`).

## Connections

- used_by: [[studio-api-module]] (`POST /api/studio/parse`)
