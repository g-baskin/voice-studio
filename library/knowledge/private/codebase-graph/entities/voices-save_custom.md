---
type: entity
title: "voices.save_custom"
entity_type: function
status: developing
created: 2026-10-19
updated: 2026-10-19
path: "src/naturalvoice/voices.py"
language: py
depends_on:
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
  - "src/naturalvoice/voices.py"
---

# voices.save_custom

## Overview

Persists a **custom voice**: a Kokoro voice vector, never a recording (`src/naturalvoice/voices.py:68-89`).

## Signature / Definition

```py
def save_custom(name: str, style: np.ndarray, meta: dict | None = None, lang: str = "en-us", kind: str = "custom", vid: str | None = None) -> dict
```

## Behavior

- Rejects any array not of `STYLE_SHAPE` or non-finite (`voices.py:77-79`).
- Name trimmed to 60 chars, required (`voices.py:80-82`).
- Writes `<vid>.npy` then JSON record with id `custom:<vid>` (`voices.py:86-88`).

## Connections

- **depends_on:** [[entities/voices-module]]
- **callers:** design and match save routes in [[entities/voicelab_api-module]] (calls at `voicelab_api.py:209` and `:372`).
- **concepts:** [[concepts/voices-voice-categories]]

## History

- **Last touched:** commit `0a207b3` (feat: add local voice sample collections) by AutomationGod on 2026-10-18, per `git log`.
