---
type: entity
title: "voicelab.build_style"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/voicelab.py"
language: py
depends_on:
  - "[[entities/voicelab-module]]"
  - "[[entities/voices-module]]"
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

# voicelab.build_style

## Overview

Turns a validated **voice recipe** into a Kokoro voice vector plus language (`src/naturalvoice/voicelab.py:400-410`). Produces a custom voice candidate, not a cloned voice.

## Signature / Definition

```py
def build_style(recipe: dict) -> tuple[np.ndarray, str]
```

## Behavior

- Validates via `validate_recipe` (`voicelab.py:402`), blends stock/custom vectors by weight (`:403-404`).
- Adds character-control axes scaled by `CONTROLS[k]["scale"]` (`:405-406`) and optional seeded variation (`:407-408`).
- Language follows the heaviest-weighted source voice (`:409-410`).

## Connections

- **used_by:** `_build` in [[entities/voicelab_api-module]] (`voicelab_api.py:178-184`)
- **concepts:** [[concepts/voices-voice-categories]]

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
